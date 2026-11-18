"""التشغيل اليومي: ياخد أول مشروع من projects/queue، يعمل الفيديو، ويرفعه على يوتيوب مجدول.

  - الفيديو الطويل: Public الساعة 7:00 مساءً بتوقيت القاهرة
  - الشورت:        Public الساعة 10:00 مساءً بتوقيت القاهرة
  - 3 شورتس معلومات من projects/facts_queue.json: الساعة 3:00 م، 5:00 م، 9:00 م (في نفس يوم التشغيل،
    ولو ميعاد فات بيتنقل لأول ميعاد فاضي بعده)
بعد النشر المشروع بيتنقل لـ projects/done ومعاه لينكات الفيديوهات.
حصة يوتيوب اليومية ~10,000 وحدة، والرفعة الواحدة ~1,600، فالمجموع اليومي (5 رفعات) جوه الحد.
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
FACT_TIMES = [(15, 0), (17, 0), (21, 0)]   # مواعيد شورتس المعلومات (عددها = عدد الشورتس في اليوم)
FACTS_PER_RUN = 3                            # حد الرفع في التشغيل الواحد (حصة يوتيوب)
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


def post_facts(yt, now):
    """يعمل ويرفع شورتس المعلومات في أقرب المواعيد الفاضية (من النهارده)."""
    queue, done = load(FACTS_QUEUE, []), load(FACTS_DONE, [])
    per_day = {}
    for d in done:
        dd = datetime.fromisoformat(d["published_at"]).astimezone(CAIRO).date()
        per_day[dd] = per_day.get(dd, 0) + 1
    uploaded_today = sum(1 for d in done if d.get("uploaded_on") == now.date().isoformat())
    if uploaded_today >= FACTS_PER_RUN:  # حصة النهارده من الرفع خلصت، نكمّل بكرة
        return f"  ✔ شورتس المعلومات اترفعت النهارده خلاص — فاضل في الطابور: {len(queue)}"
    slots, day = [], now.date()
    while len(slots) < FACTS_PER_RUN - uploaded_today and day <= now.date() + timedelta(days=1):  # النهارده وبكرة بس
        free = len(FACT_TIMES) - per_day.get(day, 0)
        for hm in FACT_TIMES:
            at = datetime.combine(day, datetime.min.time(), CAIRO).replace(hour=hm[0], minute=hm[1])
            if free > 0 and at - now >= timedelta(minutes=45) and len(slots) < FACTS_PER_RUN - uploaded_today:
                slots.append(at)
                free -= 1
        day += timedelta(days=1)
    lines = []
    for at in slots:
        if not queue:
            lines.append("  ⚠ طابور شورتس المعلومات فاضي")
            break
        f = queue[0]
        print(f"▶ شورت معلومة: {f['slug']}")
        out = ROOT / "output" / "facts" / f"{f['slug']}.mp4"
        out.parent.mkdir(parents=True, exist_ok=True)
        pipeline.build_video(f["scenes"], ROOT / "work" / "facts" / f["slug"], out, True, f.get("seed", 9000))
        try:
            vid = publish.youtube_upload(yt, out, f["title"], f["description"], f["tags"] + ["shorts"],
                                         at.isoformat(), False)
        except Exception as e:  # غالباً حصة يوتيوب خلصت: نكمّل التشغيل الجاي
            lines.append(f"  ⚠ وقف رفع الشورتس: {str(e)[:200]}")
            break
        f["published_at"], f["youtube"] = at.isoformat(), f"https://youtu.be/{vid}"
        f["uploaded_on"] = now.date().isoformat()
        done.append(f)
        queue.pop(0)
        save(FACTS_QUEUE, queue)
        save(FACTS_DONE, done)
        lines.append(f"  شورت {at:%m-%d %H:%M}: {f['youtube']}  {f['title'][:50]}")
    lines.append(f"  فاضل في طابور شورتس المعلومات: {len(queue)}")
    return "\n".join(lines)


def main():
    queue = sorted(QUEUE.glob("*.json"))
    yt = publish.yt_client()
    if not queue:
        report = "❌ طابور الفيديوهات الطويلة فاضي: اطلب من Claude يكتب مواضيع جديدة.\n" + post_facts(yt, datetime.now(CAIRO))
        print(report)
        (ROOT / "last_run.txt").write_text(report + "\n", encoding="utf-8")
        sys.exit(1)
    now = datetime.now(CAIRO)
    if next_free_slot(now).date() > now.date() + timedelta(days=1):
        report = "✔ فيديو بكرة متجدول خلاص.\n" + post_facts(yt, now)
        print(report)
        (ROOT / "last_run.txt").write_text(report + "\n", encoding="utf-8")
        return
    proj = queue[0]
    print(f"▶ المشروع: {proj.name} — فاضل في الطابور بعده: {len(queue) - 1}")
    pipeline.main(proj)

    p = json.loads(proj.read_text(encoding="utf-8"))
    out = ROOT / "output" / p["slug"]
    meta = json.loads((out / "meta.json").read_text(encoding="utf-8"))
    now = datetime.now(CAIRO)
    long_at = next_free_slot(now)
    short_at = long_at.replace(hour=SHORT_AT[0], minute=SHORT_AT[1])

    ids = {"long": publish.youtube_upload(yt, out / "long.mp4", meta["title"], meta["description"], meta["tags"],
                                          long_at.isoformat(), False, out / "thumbnail.jpg")}
    for i, (s, sm) in enumerate(zip(sorted(out.glob("short_*.mp4")), meta["shorts"]), 1):
        ids[f"short_{i}"] = publish.youtube_upload(yt, s, sm["title"], sm["description"],
                                                   meta["tags"] + ["shorts"], short_at.isoformat(), False)

    p["published"] = {"long_at": long_at.isoformat(), "short_at": short_at.isoformat(),
                      "youtube": {k: f"https://youtu.be/{v}" for k, v in ids.items()}}
    DONE.mkdir(parents=True, exist_ok=True)
    (DONE / proj.name).write_text(json.dumps(p, ensure_ascii=False, indent=2), encoding="utf-8")
    proj.unlink()
    summary = f"✔ {p['title']}\n  ينزل {long_at:%Y-%m-%d %H:%M} القاهرة\n" + \
              "\n".join(f"  {k}: {v}" for k, v in p["published"]["youtube"].items())
    summary += f"\n  فاضل في الطابور: {len(queue) - 1}\n" + post_facts(yt, datetime.now(CAIRO))
    print(summary)
    Path(ROOT / "last_run.txt").write_text(summary + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
