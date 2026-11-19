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

## التشغيل اليومي (GitHub Actions)
- كل يوم **الساعة 11:00 UTC** (1 الضهر بتوقيت القاهرة في الشتا)، الملف `.github/workflows/daily.yml` بياخد أول سكريبت من `projects/queue/`، ويعمل الفيديو، ويرفعه على يوتيوب.
- الفيديو الطويل بيتجدول ينزل **Public الساعة 7:00 مساءً** بتوقيت القاهرة، والشورت **الساعة 10:00 مساءً**.
- بعد النشر، السكريبت بيتنقل لـ `projects/done/` ومعاه لينكات الفيديوهات، وآخر نتيجة بتتكتب في `last_run.txt`.
- **بيانات يوتيوب:** محفوظة في GitHub Secret اسمه `YT_CREDENTIALS`.
- **لما الطابور يفضى:** اطلب من Claude يكتب مواضيع جديدة في `projects/queue/`.
- **تشغيل يدوي:** من تبويب Actions، اختار daily-video، ودوس Run workflow.

## شورتس المعلومات اليومية
- كل يوم بينزل **4 شورتس معلومات** من `projects/facts_queue.json`، في المواعيد دي بتوقيت القاهرة: **3:00 م، و5:00 م، و9:00 م، و11:00 م**. وده غير شورت الإعلان بتاع الفيديو الطويل اللي بينزل 10:00 م.
- الشورتس اللي اتنشرت بتتنقل لـ `projects/facts_done.json` ومعاها لينكاتها.
- **حصة يوتيوب:** كل يوم فيه 6 رفعات (فيديو + 5 شورتس)، يعني حوالي 9,650 وحدة، وده أقصى حاجة من الحصة المجانية اللي هي 10,000. لو عايز شورتس أكتر، لازم تطلب زيادة الحصة من يوتيوب.
- **لو الحصة خلصت:** الشورتس اللي ماترفعتش بتفضل في الطابور، وبتترفع في التشغيل اللي بعده.
