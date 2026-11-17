"""
الأرشيف المفقود - سيستم صناعة الفيديوهات بالذكاء الاصطناعي (مجاني بالكامل)

الاستخدام:
    python pipeline.py projects/alexander_tomb.json

بيطلّع في output/<slug>/ :
    long.mp4        الفيديو الطويل 16:9
    short_1.mp4 ... الشورتس / الريلز 9:16
    thumbnail.jpg   الصورة المصغرة
    meta.json       العنوان والوصف والتاجات للنشر
"""
import asyncio, json, os, random, shutil, ssl, subprocess, sys, time, urllib.parse, urllib.request
from pathlib import Path

import edge_tts
import edge_tts.communicate as _etc
from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parent
CA = "/root/.ccr/ca-bundle.crt"
PROXY = os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy")
if os.path.exists(CA):
    _etc._SSL_CTX = ssl.create_default_context(cafile=CA)

CHANNEL_NAME = "الأرشيف المفقود"
VOICE = "ar-EG-ShakirNeural"          # صوت مصري مجاني من Microsoft Edge
VOICE_RATE = "-4%"
VOICE_PITCH = "-4Hz"
FPS = 30
FONT_BOLD = "/usr/share/fonts/truetype/noto/NotoSansArabic-Bold.ttf"
SUB_FONT_NAME = "Noto Naskh Arabic"   # الخط ده بيعرض لام-ألف صح في libass
IMG_STYLE = ("cinematic dramatic lighting, dark mysterious atmosphere, documentary film still, "
             "highly detailed, volumetric light, 35mm, no text, no watermark")


def sh(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        sys.stderr.write(r.stderr[-3000:])
        raise RuntimeError("command failed: " + " ".join(map(str, cmd[:6])))
    return r.stdout


def duration(path):
    return float(sh(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)]).strip())


# ---------------------------------------------------------------- الصوت
async def _tts(text, out_mp3):
    com = edge_tts.Communicate(text, VOICE, rate=VOICE_RATE, pitch=VOICE_PITCH, proxy=PROXY)
    sentences = []
    with open(out_mp3, "wb") as f:
        async for ch in com.stream():
            if ch["type"] == "audio":
                f.write(ch["data"])
            elif ch["type"] in ("SentenceBoundary", "WordBoundary"):
                sentences.append((ch["offset"] / 1e7, (ch["offset"] + ch["duration"]) / 1e7, ch["text"]))
    return sentences


def tts(text, out_mp3):
    for attempt in range(4):
        try:
            return asyncio.run(_tts(text, out_mp3))
        except Exception as e:  # الشبكة أحياناً بتقطع
            print("  tts retry", attempt + 1, e)
            time.sleep(3 * (attempt + 1))
    raise RuntimeError("TTS failed")


# ---------------------------------------------------------------- الصور
def gen_image(prompt, out, w, h, seed):
    if out.exists() and out.stat().st_size > 10000:
        return
    q = urllib.parse.quote(f"{prompt}, {IMG_STYLE}")
    url = f"https://image.pollinations.ai/prompt/{q}?width={w}&height={h}&seed={seed}&nologo=true"
    for attempt in range(6):
        try:
            with urllib.request.urlopen(url, timeout=180) as r:
                data = r.read()
            if len(data) > 10000:
                out.write_bytes(data)
                return
        except Exception as e:
            print("  image retry", attempt + 1, e)
        time.sleep(5 * (attempt + 1))
    raise RuntimeError("image generation failed: " + prompt)


# ---------------------------------------------------------------- الترجمة
def chunk_subs(sentences, offset, max_words=6):
    """يقسّم كل جملة لقطع صغيرة متوزعة زمنياً على عدد الحروف."""
    out = []
    for s, e, text in sentences:
        words = text.split()
        groups = [words[i:i + max_words] for i in range(0, len(words), max_words)] or [[]]
        total = sum(len(" ".join(g)) for g in groups) or 1
        t = s
        for g in groups:
            seg = (e - s) * len(" ".join(g)) / total
            out.append((offset + t, offset + t + seg, " ".join(g)))
            t += seg
    return out


def ass_time(t):
    h, rem = divmod(max(t, 0), 3600)
    m, s = divmod(rem, 60)
    return f"{int(h)}:{int(m):02d}:{s:05.2f}"


def write_ass(subs, path, vertical):
    W, H = (1080, 1920) if vertical else (1920, 1080)
    size, margin, align = (96, 700, 2) if vertical else (74, 70, 2)
    head = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {W}
PlayResY: {H}
WrapStyle: 0

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,{SUB_FONT_NAME},{size},&H00FFFFFF,&H00FFFFFF,&H00000000,&H96000000,-1,0,0,0,100,100,0,0,1,5,2,{align},80,80,{margin},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    lines = [f"Dialogue: 0,{ass_time(a)},{ass_time(b)},Default,,0,0,0,,{t}" for a, b, t in subs if t.strip()]
    Path(path).write_text(head + "\n".join(lines) + "\n", encoding="utf-8")


# ---------------------------------------------------------------- الحركة
MOTIONS = ["zoom_in", "pan_lr", "zoom_out", "pan_rl"]


def zoompan_expr(kind, frames):
    D = max(frames, 1)
    c = "iw/2-(iw/zoom/2)", "ih/2-(ih/zoom/2)"
    return {
        "zoom_in": (f"1+0.18*on/{D}", *c),
        "zoom_out": (f"1.18-0.18*on/{D}", *c),
        "pan_lr": ("1.18", f"(iw-iw/zoom)*on/{D}", c[1]),
        "pan_rl": ("1.18", f"(iw-iw/zoom)*(1-on/{D})", c[1]),
    }[kind]


def render_scene(img, audio, out, dur, motion, vertical):
    W, H = (1080, 1920) if vertical else (1920, 1080)
    frames = int(round(dur * FPS))
    z, x, y = zoompan_expr(motion, frames)
    vf = (f"crop=iw:ih*0.93:0:0,scale={W*2}:{H*2}:force_original_aspect_ratio=increase:flags=lanczos,crop={W*2}:{H*2},"
          f"zoompan=z='{z}':x='{x}':y='{y}':d={frames}:s={W}x{H}:fps={FPS},"
          f"eq=contrast=1.06:saturation=0.92,vignette=PI/4.5,"
          f"fade=t=in:st=0:d=0.35,fade=t=out:st={dur-0.35:.2f}:d=0.35,format=yuv420p")
    sh(["ffmpeg", "-y", "-loop", "1", "-i", str(img), "-i", str(audio),
        "-filter_complex", f"[0:v]{vf}[v];[1:a]apad,aresample=44100[a]",
        "-map", "[v]", "-map", "[a]", "-t", f"{dur:.3f}", "-r", str(FPS),
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-c:a", "aac", "-b:a", "192k", "-ac", "2", str(out)])


def make_music(out, dur):
    """موسيقى غموض خلفية متولدة (Drone) - مفيش حقوق ملكية."""
    sh(["ffmpeg", "-y",
        "-f", "lavfi", "-i", f"anoisesrc=color=brown:amplitude=0.25:d={dur}",
        "-f", "lavfi", "-i", f"sine=f=55:d={dur}",
        "-f", "lavfi", "-i", f"sine=f=82.41:d={dur}",
        "-f", "lavfi", "-i", f"sine=f=130.81:d={dur}",
        "-filter_complex",
        "[0]lowpass=f=220,volume=0.6[n];[1]volume=0.5,tremolo=f=0.15:d=0.6[a];"
        "[2]volume=0.3,tremolo=f=0.11:d=0.7[b];[3]volume=0.12,tremolo=f=0.23:d=0.9[c];"
        f"[n][a][b][c]amix=inputs=4:normalize=0,aecho=0.8:0.7:900|1400:0.35|0.25,"
        f"afade=t=in:d=3,afade=t=out:st={max(dur-4,0)}:d=4,volume=0.55[m]",
        "-map", "[m]", "-ac", "2", "-ar", "44100", str(out)])


def watermark_png(out, vertical):
    W = 1080 if vertical else 1920
    font = ImageFont.truetype(FONT_BOLD, 34 if vertical else 30)
    im = Image.new("RGBA", (W, 120), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    txt = CHANNEL_NAME
    bw = d.textlength(txt, font=font, direction="rtl")
    d.text((W - bw - 40, 30), txt, font=font, fill=(255, 210, 60, 170), direction="rtl",
           stroke_width=2, stroke_fill=(0, 0, 0, 170))
    im.save(out)


def build_video(scenes, workdir, out, vertical, seed_base):
    workdir.mkdir(parents=True, exist_ok=True)
    W, H = (576, 1024) if vertical else (1024, 576)
    clips, subs, t = [], [], 0.0
    for i, sc in enumerate(scenes):
        print(f"  مشهد {i+1}/{len(scenes)}")
        img = workdir / f"img_{i:02d}.jpg"
        aud = workdir / f"voice_{i:02d}.mp3"
        clip = workdir / f"clip_{i:02d}.mp4"
        cache = workdir / f"scene_{i:02d}.json"
        if cache.exists() and clip.exists() and json.loads(cache.read_text(encoding="utf-8"))["text"] == sc["text"]:
            c = json.loads(cache.read_text(encoding="utf-8"))  # المشهد معمول قبل كده
            sents, dur = c["sents"], c["dur"]
        else:
            gen_image(sc["image"], img, W, H, seed_base + i)
            sents = tts(sc["text"], aud)
            dur = duration(aud) + 0.45
            render_scene(img, aud, clip, dur, MOTIONS[i % len(MOTIONS)], vertical)
            cache.write_text(json.dumps({"text": sc["text"], "sents": sents, "dur": dur}, ensure_ascii=False), encoding="utf-8")
        subs += chunk_subs(sents, t + 0.1)
        clips.append(clip)
        t += dur
    lst = workdir / "list.txt"
    lst.write_text("".join(f"file '{c.name}'\n" for c in clips))
    joined = workdir / "joined.mp4"
    sh(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(lst), "-c", "copy", str(joined)])
    ass = workdir / "subs.ass"
    write_ass(subs, ass, vertical)
    music = workdir / "music.wav"
    make_music(music, t + 1)
    wm = workdir / "wm.png"
    watermark_png(wm, vertical)
    # الدمج النهائي: لوجو القناة + الترجمة + الموسيقى + توحيد مستوى الصوت
    cwd = os.getcwd()
    os.chdir(workdir)  # فلتر subtitles بيحتاج مسار بسيط
    try:
        sh(["ffmpeg", "-y", "-i", joined.name, "-i", music.name, "-i", wm.name,
            "-filter_complex",
            f"[0:v][2:v]overlay=0:0,subtitles={ass.name}:fontsdir=/usr/share/fonts/truetype/noto[v];"
            "[1:a]volume=0.22[m];[0:a][m]amix=inputs=2:duration=first:normalize=0,loudnorm=I=-14:TP=-1.5[a]",
            "-map", "[v]", "-map", "[a]", "-c:v", "libx264", "-preset", "medium", "-crf", "19",
            "-c:a", "aac", "-b:a", "192k", "-ar", "44100", "-movflags", "+faststart", str(out.resolve())])
    finally:
        os.chdir(cwd)
    return t


# ---------------------------------------------------------------- الصورة المصغرة
def thumbnail(cfg, workdir, out, seed):
    W, H = 1280, 720
    base = workdir / "thumb_bg.jpg"
    gen_image(cfg["image"], base, W, H, seed)
    im = Image.open(base).convert("RGB")
    im = im.crop((0, 0, im.width, int(im.height * 0.93))).resize((W, H), Image.LANCZOS)  # شيل العلامة
    # تغميق جهة النص (اليمين) علشان الكلام يبان
    grad = Image.new("L", (W, H))
    gd = ImageDraw.Draw(grad)
    for x in range(W):
        gd.line([(x, 0), (x, H)], fill=int(200 * max(0, (x - W * 0.35) / (W * 0.65)) ** 1.3))
    im = Image.composite(Image.new("RGB", (W, H), (0, 0, 0)), im, grad)
    d = ImageDraw.Draw(im)
    y = 40
    for text, color in zip(cfg["lines"], [(255, 214, 0), (255, 255, 255), (255, 60, 50)]):
        size = 110
        while True:
            font = ImageFont.truetype(FONT_BOLD, size)
            w = d.textlength(text, font=font, direction="rtl")
            if w <= W * 0.6 or size < 50:
                break
            size -= 4
        d.text((W - 40 - w, y), text, font=font, fill=color, direction="rtl",
               stroke_width=9, stroke_fill=(0, 0, 0))
        y += int(size * 1.55)
    if cfg.get("arrow"):  # سهم أحمر بيشاور على السر
        (x1, y1), (x2, y2) = cfg["arrow"]
        import math
        ang = math.atan2(y2 - y1, x2 - x1)
        def pt(dx, dy):
            return (x2 + dx * math.cos(ang) - dy * math.sin(ang), y2 + dx * math.sin(ang) + dy * math.cos(ang))
        L = math.hypot(x2 - x1, y2 - y1)
        poly = [pt(-L, -14), pt(-60, -14), pt(-60, -42), pt(0, 0), pt(-60, 42), pt(-60, 14), pt(-L, 14)]
        sd = Image.new("RGBA", (W, H)); ImageDraw.Draw(sd).polygon(poly, fill=(0, 0, 0, 200))
        im.paste(sd.filter(ImageFilter.GaussianBlur(6)), (6, 6), sd.filter(ImageFilter.GaussianBlur(6)))
        d.polygon(poly, fill=(235, 20, 20), outline=(255, 255, 255), width=4)
    im.save(out, quality=92)


# ---------------------------------------------------------------- التشغيل
def main(project_path):
    p = json.loads(Path(project_path).read_text(encoding="utf-8"))
    slug = p["slug"]
    out = ROOT / "output" / slug
    work = ROOT / "work" / slug
    out.mkdir(parents=True, exist_ok=True)
    work.mkdir(parents=True, exist_ok=True)
    seed = p.get("seed", random.randint(1, 10**6))
    t0 = time.time()

    print("▶ الصورة المصغرة")
    thumbnail(p["thumbnail"], work, out / "thumbnail.jpg", seed + 999)

    print("▶ الفيديو الطويل")
    dur = build_video(p["scenes"], work / "long", out / "long.mp4", False, seed)

    for k, short in enumerate(p.get("shorts", []), 1):
        print(f"▶ شورت {k}")
        build_video(short["scenes"], work / f"short_{k}", out / f"short_{k}.mp4", True, seed + 100 * k)

    meta = {"title": p["title"], "description": p["description"], "tags": p["tags"],
            "shorts": [{"title": s["title"], "description": s.get("description", p["description"])}
                       for s in p.get("shorts", [])]}
    (out / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"✔ خلص في {time.time()-t0:.0f} ثانية — مدة الفيديو {dur/60:.1f} دقيقة — {out}")


if __name__ == "__main__":
    main(sys.argv[1])
