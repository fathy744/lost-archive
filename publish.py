"""
نشر فيديوهات الأرشيف المفقود على يوتيوب وفيسبوك.

    python publish.py output/alexander_tomb --youtube --facebook [--schedule 2026-11-20T18:00:00+02:00] [--public]

الإعداد مرة واحدة (التفاصيل في README.md):
  يوتيوب : credentials/client_secret.json  ثم  python publish.py --youtube-login
  فيسبوك : متغيرين FB_PAGE_ID و FB_PAGE_TOKEN (توكن صفحة طويل المدى)
"""
import argparse, json, os, sys, time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent
CRED = ROOT / "credentials"
YT_SCOPES = ["https://www.googleapis.com/auth/youtube.upload", "https://www.googleapis.com/auth/youtube"]
GRAPH = "https://graph.facebook.com/v21.0"


# ------------------------------------------------------------------ YouTube
def yt_client():
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build
    tok = CRED / "youtube_token.json"
    if not tok.exists():
        sys.exit("مفيش توكن يوتيوب. شغّل: python publish.py --youtube-login")
    creds = Credentials.from_authorized_user_file(str(tok), YT_SCOPES)
    if not creds.valid:
        creds.refresh(Request())
        tok.write_text(creds.to_json())
    return build("youtube", "v3", credentials=creds)


def youtube_login():
    from google_auth_oauthlib.flow import InstalledAppFlow
    flow = InstalledAppFlow.from_client_secrets_file(str(CRED / "client_secret.json"), YT_SCOPES)
    creds = flow.run_local_server(port=0, open_browser=True)  # شغّلها على جهازك مرة واحدة
    (CRED / "youtube_token.json").write_text(creds.to_json())
    print("✔ تم حفظ توكن يوتيوب في credentials/youtube_token.json")


def youtube_upload(yt, video, title, desc, tags, schedule=None, public=False, thumb=None):
    from googleapiclient.http import MediaFileUpload
    status = {"privacyStatus": "public" if public and not schedule else "private",
              "selfDeclaredMadeForKids": False, "containsSyntheticMedia": True}
    if schedule:
        status["publishAt"] = schedule  # بينزل public تلقائي في الميعاد ده
    body = {"snippet": {"title": title[:100], "description": desc[:5000], "tags": tags,
                        "categoryId": "27", "defaultLanguage": "ar", "defaultAudioLanguage": "ar"},
            "status": status}
    req = yt.videos().insert(part="snippet,status", body=body,
                             media_body=MediaFileUpload(str(video), chunksize=8 * 1024 * 1024, resumable=True))
    resp = None
    while resp is None:
        st, resp = req.next_chunk()
        if st:
            print(f"  يوتيوب {int(st.progress()*100)}%")
    vid = resp["id"]
    if thumb and Path(thumb).exists():
        try:
            yt.thumbnails().set(videoId=vid, media_body=MediaFileUpload(str(thumb))).execute()
        except Exception as e:  # الصورة المصغرة بتحتاج قناة متوثقة برقم موبايل
            print("  ⚠ الصورة المصغرة اترفضت (لازم توثّق القناة برقم موبايل):", e)
    print(f"  ✔ https://youtu.be/{vid}")
    return vid


# ------------------------------------------------------------------ Facebook
def fb_env():
    pid, tok = os.environ.get("FB_PAGE_ID"), os.environ.get("FB_PAGE_TOKEN")
    if not pid or not tok:
        sys.exit("محتاج FB_PAGE_ID و FB_PAGE_TOKEN")
    return pid, tok


def facebook_video(video, title, desc, schedule_ts=None):
    pid, tok = fb_env()
    data = {"title": title, "description": desc, "access_token": tok}
    if schedule_ts:
        data.update(published="false", scheduled_publish_time=str(schedule_ts))
    with open(video, "rb") as f:
        r = requests.post(f"https://graph-video.facebook.com/v21.0/{pid}/videos",
                          data=data, files={"source": f}, timeout=1800)
    r.raise_for_status()
    print("  ✔ فيسبوك فيديو:", r.json().get("id"))


def facebook_reel(video, desc):
    pid, tok = fb_env()
    r = requests.post(f"{GRAPH}/{pid}/video_reels", data={"upload_phase": "start", "access_token": tok}, timeout=60)
    r.raise_for_status()
    vid, up = r.json()["video_id"], r.json()["upload_url"]
    size = os.path.getsize(video)
    with open(video, "rb") as f:
        r = requests.post(up, data=f, timeout=1800, headers={
            "Authorization": f"OAuth {tok}", "offset": "0", "file_size": str(size)})
    r.raise_for_status()
    r = requests.post(f"{GRAPH}/{pid}/video_reels", timeout=60, data={
        "upload_phase": "finish", "video_id": vid, "video_state": "PUBLISHED",
        "description": desc, "access_token": tok})
    r.raise_for_status()
    print("  ✔ فيسبوك ريلز:", vid)


# ------------------------------------------------------------------ main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("folder", nargs="?")
    ap.add_argument("--youtube", action="store_true")
    ap.add_argument("--facebook", action="store_true")
    ap.add_argument("--public", action="store_true", help="انشر فوراً بدل Private")
    ap.add_argument("--schedule", help="ميعاد النشر ISO مثل 2026-11-20T18:00:00+02:00")
    ap.add_argument("--youtube-login", action="store_true")
    a = ap.parse_args()
    if a.youtube_login:
        return youtube_login()
    folder = Path(a.folder)
    meta = json.loads((folder / "meta.json").read_text(encoding="utf-8"))
    shorts = sorted(folder.glob("short_*.mp4"))
    ts = None
    if a.schedule:
        from datetime import datetime
        ts = int(datetime.fromisoformat(a.schedule).timestamp())

    if a.youtube:
        print("▶ يوتيوب")
        yt = yt_client()
        youtube_upload(yt, folder / "long.mp4", meta["title"], meta["description"], meta["tags"],
                       a.schedule, a.public, folder / "thumbnail.jpg")
        for s, sm in zip(shorts, meta["shorts"]):
            youtube_upload(yt, s, sm["title"], sm["description"], meta["tags"] + ["shorts"], a.schedule, a.public)
    if a.facebook:
        print("▶ فيسبوك")
        facebook_video(folder / "long.mp4", meta["title"], meta["description"], ts)
        for s, sm in zip(shorts, meta["shorts"]):
            facebook_reel(s, sm["title"] + "\n\n" + sm["description"])


if __name__ == "__main__":
    main()
