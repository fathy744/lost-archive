# الأرشيف المفقود: سيستم فيديوهات بالذكاء الاصطناعي (مجاني)

## الأدوات المستخدمة
| المرحلة | الأداة | التكلفة |
|---|---|---|
| السكريبت | Claude (بيكتب ملف المشروع JSON) | — |
| التعليق الصوتي | Microsoft Edge TTS، صوت «شاكر» المصري `ar-EG-ShakirNeural` | مجاني |
| الصور | Pollinations.ai (موديل Flux) | مجاني |
| المونتاج والحركة والترجمة والموسيقى | FFmpeg | مجاني |
| الصورة المصغرة | Pillow | مجاني |
| النشر | YouTube Data API و Facebook Graph API | مجاني |

## صناعة فيديو
```bash
pip install edge-tts pillow requests google-api-python-client google-auth-oauthlib
python pipeline.py projects/alexander_tomb.json
```
النتيجة بتتحفظ في `output/<slug>/`، وجواها: `long.mp4` و`short_1.mp4` و`thumbnail.jpg` و`meta.json`.

لعمل فيديو جديد: انسخ ملف من `projects/` وغيّر فيه `slug` والعنوان والمشاهد. كل مشهد عبارة عن نص بيتقري، ووصف بالإنجليزي للصورة.

## إعداد يوتيوب (مرة واحدة)
1. ادخل على https://console.cloud.google.com وابدأ **مشروع جديد**.
2. من **APIs & Services ← Library** فعّل **YouTube Data API v3**.
3. من **OAuth consent screen** اختار External، واكتب اسم التطبيق، وضيف إيميلك في **Test users**.
4. من **Credentials ← Create Credentials ← OAuth client ID** اختار النوع **Desktop app**، ونزّل ملف JSON.
5. حط الملف في `credentials/client_secret.json`، وشغّل الأمر ده **على جهازك** لأنه هيفتح المتصفح:
   ```bash
   python publish.py --youtube-login
   ```
   هيطلع ملف `credentials/youtube_token.json`، وده اللي السيستم بيستخدمه بعد كده.
6. علشان الصورة المصغرة المخصصة تشتغل، وثّق القناة برقم الموبايل من https://www.youtube.com/verify

> الحصة المجانية من يوتيوب حوالي **6 رفعات في اليوم** (كل رفعة بـ 1600 وحدة من 10,000).

## إعداد فيسبوك (مرة واحدة)
1. ادخل على https://developers.facebook.com وابدأ تطبيق جديد من نوع **Business**.
2. من **Graph API Explorer** اختار صفحتك، وادّي الصلاحيات دي:
   `pages_manage_posts`, `pages_read_engagement`, `pages_show_list`, `publish_video`
3. حوّل التوكن لتوكن طويل المدى من **Access Token Debugger ← Extend**، وبعدين هات **Page Access Token** للصفحة.
4. حطهم كمتغيرات بيئة:
   ```bash
   export FB_PAGE_ID=...
   export FB_PAGE_TOKEN=...
   ```

## النشر
```bash
# ارفع كـ Private علشان تراجع (الافتراضي)
python publish.py output/alexander_tomb --youtube --facebook

# جدولة النشر
python publish.py output/alexander_tomb --youtube --schedule 2026-11-20T18:00:00+02:00
```

⚠️ اقفل المجلد `credentials/` ومتشاركهوش مع حد، ومترفعهوش على GitHub.
