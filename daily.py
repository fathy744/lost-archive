"""التشغيل اليومي: ياخد أول مشروع من projects/queue، يعمل الفيديو، ويرفعه على يوتيوب مجدول.

  - الفيديو الطويل: Public الساعة 7:00 مساءً بتوقيت القاهرة
  - الشورت:        Public الساعة 10:00 مساءً بتوقيت القاهرة
بعد النشر المشروع بيتنقل لـ projects/done ومعاه لينكات الفيديوهات.
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


def slot(hour_min, now):
    t = now.replace(hour=hour_min[0], minute=hour_min[1], second=0, microsecond=0)
    if t - now < timedelta(minutes=45):  # لو الوقت فات أو قرّب، خليه بكرة
        t += timedelta(days=1)
    return t


def main():
    queue = sorted(QUEUE.glob("*.json"))
    if not queue:
        sys.exit("❌ الطابور فاضي: مفيش سكريبتات في projects/queue. اطلب من Claude يكتب مواضيع جديدة.")
    proj = queue[0]
    print(f"▶ المشروع: {proj.name} — فاضل في الطابور بعده: {len(queue) - 1}")
    pipeline.main(proj)

    p = json.loads(proj.read_text(encoding="utf-8"))
    out = ROOT / "output" / p["slug"]
    meta = json.loads((out / "meta.json").read_text(encoding="utf-8"))
    now = datetime.now(CAIRO)
    long_at = slot(LONG_AT, now)
    short_at = long_at.replace(hour=SHORT_AT[0], minute=SHORT_AT[1])

    yt = publish.yt_client()
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
    print(summary)
    Path(ROOT / "last_run.txt").write_text(summary + f"\n  فاضل في الطابور: {len(queue) - 1}\n", encoding="utf-8")


if __name__ == "__main__":
    main()
