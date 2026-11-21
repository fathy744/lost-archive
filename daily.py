"""التشغيل اليومي: ياخد أول مشروع من projects/queue، يعمل الفيديو، ويرفعه على يوتيوب مجدول.

  - الفيديو الطويل: Public الساعة 7:00 مساءً بتوقيت القاهرة
  - الشورت:        Public الساعة 10:00 مساءً بتوقيت القاهرة
  - 4 شورتس معلومات يومياً: الساعة 3:00 م، 5:00 م، 9:00 م، 11:00 م (بيملا أقرب المواعيد الفاضية لحد بعد بكرة) (في نفس يوم التشغيل،
    ولو ميعاد فات بيتنقل لأول ميعاد فاضي بعده)
بعد النشر المشروع بيتنقل لـ projects/done ومعاه لينكات الفيديوهات.
حصة يوتيوب اليومية ~10,000 وحدة، والرفعة الواحدة ~1,600، فالمجموع اليومي (6 رفعات ≈ 9,650 وحدة) جوه الحد بالعافية.
"""
import json, shutil, sys
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pipeline
import publish

ROOT = Path(__file__).resolve().parent
QUEUE, DONE = ROOT / "projects" / "queue", ROOT / "projects" / "done"
CAIRO = ZoneInfo("Africa/Cairo")
LONG_AT, SHORT_AT = (19, 0), (22, 0)
FACT_TIMES = [(15, 0), (17, 0), (21, 0), (23, 0)]   # مواعيد شورتس المعلومات (عددها = عدد الشورتس في اليوم)
MAX_UPLOADS = 6                              # حصة يوتيوب: 10,000 وحدة ÷ ~1,600 للرفعة
PACIFIC = ZoneInfo("America/Los_Angeles")
UPLOADS_LOG = ROOT / "projects" / "uploads_log.json"
FACTS_QUEUE, FACTS_DONE = ROOT / "projects" / "facts_queue.json", ROOT / "projects" / "facts_done.json"


def slot(hour_min, now):
    t = now.replace(hour=hour_min[0], minute=hour_min[1], second=0, microsecond=0)
    if t - now < timedelta(minutes=45):  # لو الوقت فات أو قرّب، خليه بكرة
        t += timedelta(days=1)
    return t


def next_free_slot(now):
    """أول يوم فاضي: علشان لو اشتغل أكتر من مرة في نفس اليوم، الفيديوهات متنزلش مع بعض."""
    t = slot(LONG_AT, now)
    taken = set()
    for f in DONE.glob("*.json"):
        at = json.loads(f.read_text(encoding="utf-8")).get("published", {}).get("long_at")
        if at:
            taken.add(datetime.fromisoformat(at).astimezone(CAIRO).date())
    while t.date() in taken:
        t += timedelta(days=1)
    return t


def load(path, default):
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default


def save(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def pt_day():
    """حصة يوتيوب بتتجدد الساعة 12 بالليل بتوقيت كاليفورنيا (10 الصبح بتوقيت القاهرة)."""
    return datetime.now(PACIFIC).date().isoformat()


def uploads_left():
    return MAX_UPLOADS - load(UPLOADS_LOG, {}).get(pt_day(), 0)


def count_upload():
    log = load(UPLOADS_LOG, {})
    log = {k: v for k, v in log.items() if k >= (datetime.now(PACIFIC).date() - timedelta(days=7)).isoformat()}
    log[pt_day()] = log.get(pt_day(), 0) + 1
    save(UPLOADS_LOG, log)


def next_fact_slot(done):
    """أقرب ميعاد فاضي لشورت معلومة (النهارده وبعدها بيومين)، بشرط يكون بعد نص ساعة على الأقل."""
    per_day = {}
    for d in done:
        dd = datetime.fromisoformat(d["published_at"]).astimezone(CAIRO).date()
        per_day[dd] = per_day.get(dd, 0) + 1
    now = datetime.now(CAIRO)
    for k in range(3):
        day = now.date() + timedelta(days=k)
        if per_day.get(day, 0) >= len(FACT_TIMES):
            continue
        taken = {datetime.fromisoformat(d["published_at"]).astimezone(CAIRO).strftime("%H:%M")
                 for d in done if datetime.fromisoformat(d["published_at"]).astimezone(CAIRO).date() == day}
        for hm in FACT_TIMES:
            at = datetime.combine(day, datetime.min.time(), CAIRO).replace(hour=hm[0], minute=hm[1])
            if at.strftime("%H:%M") not in taken and at - now >= timedelta(minutes=30):
                return at
    return None


def post_facts(yt, n):
    """يعمل ويرفع لحد n شورتس معلومات في أقرب المواعيد الفاضية."""
    queue, done = load(FACTS_QUEUE, []), load(FACTS_DONE, [])
    lines = []
    for _ in range(n):
        if not queue:
            lines.append("  ⚠ طابور شورتس المعلومات فاضي")
            break
        f = queue[0]
        print(f"▶ شورت معلومة: {f['slug']}")
        out = ROOT / "output" / "facts" / f"{f['slug']}.mp4"
        out.parent.mkdir(parents=True, exist_ok=True)
        pipeline.build_video(f["scenes"], ROOT / "work" / "facts" / f["slug"], out, True, f.get("seed", 9000))
        at = next_fact_slot(done)  # بعد البناء علشان الميعاد ميكونش فات
        if not at:
            lines.append("  ✔ مواعيد الشورتس متجدولة لحد بعد بكرة")
            break
        try:
            vid = publish.youtube_upload(yt, out, f["title"], f["description"], f["tags"] + ["shorts"],
                                         at.isoformat(), False)
        except Exception as e:  # غالباً حصة يوتيوب خلصت: نكمّل التشغيل الجاي
            lines.append(f"  ⚠ وقف رفع الشورتس: {str(e)[:200]}")
            break
        count_upload()
        f["published_at"], f["youtube"] = at.isoformat(), f"https://youtu.be/{vid}"
        f["uploaded_on"] = datetime.now(CAIRO).date().isoformat()
        done.append(f)
        queue.pop(0)
        save(FACTS_QUEUE, queue)
        save(FACTS_DONE, done)
        lines.append(f"  شورت {at:%m-%d %H:%M}: {f['youtube']}  {f['title'][:50]}")
    lines.append(f"  فاضل في طابور شورتس المعلومات: {len(queue)}")
    return "\n".join(lines)


def make_long(yt, proj):
    print(f"▶ المشروع: {proj.name}")
    pipeline.main(proj)
    p = json.loads(proj.read_text(encoding="utf-8"))
    out = ROOT / "output" / p["slug"]
    meta = json.loads((out / "meta.json").read_text(encoding="utf-8"))
    yt = publish.yt_client()  # اتصال جديد: القديم بيقفل بعد نص ساعة من بناء الفيديو
    long_at = next_free_slot(datetime.now(CAIRO))
    short_at = long_at.replace(hour=SHORT_AT[0], minute=SHORT_AT[1])
    ids = {"long": publish.youtube_upload(yt, out / "long.mp4", meta["title"], meta["description"], meta["tags"],
                                          long_at.isoformat(), False, out / "thumbnail.jpg")}
    count_upload()
    for i, (s, sm) in enumerate(zip(sorted(out.glob("short_*.mp4")), meta["shorts"]), 1):
        ids[f"short_{i}"] = publish.youtube_upload(yt, s, sm["title"], sm["description"],
                                                   meta["tags"] + ["shorts"], short_at.isoformat(), False)
        count_upload()
    p["published"] = {"long_at": long_at.isoformat(), "short_at": short_at.isoformat(),
                      "youtube": {k: f"https://youtu.be/{v}" for k, v in ids.items()}}
    DONE.mkdir(parents=True, exist_ok=True)
    (DONE / proj.name).write_text(json.dumps(p, ensure_ascii=False, indent=2), encoding="utf-8")
    proj.unlink()
    return f"✔ {p['title']}\n  ينزل {long_at:%Y-%m-%d %H:%M} القاهرة\n" + \
           "\n".join(f"  {k}: {v}" for k, v in p["published"]["youtube"].items())


def main():
    """الترتيب: شورتس المعلومات الأول (سريعة ومواعيدها قريبة)، وبعدين فيديو بكرة الطويل لو لسه متعملش.
    الحصة محسوبة بيوم كاليفورنيا، فأي تشغيل متأخر من GitHub بيكمّل اللي ناقص من غير ما يتعدى الحصة."""
    yt = publish.yt_client()
    queue = sorted(QUEUE.glob("*.json"))
    now = datetime.now(CAIRO)
    need_long = bool(queue) and next_free_slot(now).date() <= now.date() + timedelta(days=1)
    reserve = 2 if need_long else 0
    report = [post_facts(yt, max(0, uploads_left() - reserve))]
    if need_long and uploads_left() >= 2:
        report.insert(0, make_long(yt, queue[0]) + f"\n  فاضل في طابور الفيديوهات الطويلة: {len(queue) - 1}")
    elif not queue:
        report.insert(0, "❌ طابور الفيديوهات الطويلة فاضي: اطلب من Claude يكتب مواضيع جديدة.")
    else:
        report.insert(0, f"✔ فيديو بكرة متجدول خلاص — فاضل في طابور الفيديوهات الطويلة: {len(queue)}")
    report.append(f"  رفعات متبقية في حصة النهارده: {uploads_left()}")
    text = "\n".join(report)
    print(text)
    (ROOT / "last_run.txt").write_text(text + "\n", encoding="utf-8")
    if not queue:
        sys.exit(1)


if __name__ == "__main__":
    main()
