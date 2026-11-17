"""ربط يوتيوب من غير متصفح على السيرفر.

  python yt_auth.py url              -> يطبع لينك تفتحه على موبايلك وتوافق
  python yt_auth.py finish "<URL>"   -> تديله اللينك اللي فتح بعد الموافقة (http://localhost/?code=...)
"""
import json, sys
from pathlib import Path
from google_auth_oauthlib.flow import Flow

CRED = Path(__file__).resolve().parent / "credentials"
SCOPES = ["https://www.googleapis.com/auth/youtube.upload", "https://www.googleapis.com/auth/youtube"]
STATE = CRED / "oauth_pending.json"


def make_flow(**kw):
    return Flow.from_client_secrets_file(str(CRED / "client_secret.json"), scopes=SCOPES,
                                         redirect_uri="http://localhost", **kw)


if sys.argv[1] == "url":
    flow = make_flow(autogenerate_code_verifier=True)
    url, state = flow.authorization_url(access_type="offline", prompt="consent", include_granted_scopes="true")
    STATE.write_text(json.dumps({"state": state, "verifier": flow.code_verifier}))
    print(url)
else:
    st = json.loads(STATE.read_text())
    flow = make_flow(state=st["state"], code_verifier=st["verifier"])
    flow.fetch_token(authorization_response=sys.argv[2].replace("http://", "https://", 1))
    (CRED / "youtube_token.json").write_text(flow.credentials.to_json())
    STATE.unlink()
    print("✔ youtube_token.json saved")
