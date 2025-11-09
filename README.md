# Autostart Direct Upload (Flask webhook)

- `/start` দিলে সরাসরি **https://youtu.be/BfLPuDRgjPw** ডাউনলোড করে টেলিগ্রামে আপলোড হবে
- টেম্প ফোল্ডারে ডাউনলোড → আপলোড শেষেই ক্লিনআপ
- yt-dlp → pytube → yt-dlp(best) fallback চেইন
- ডিফল্ট কোয়ালিটি: `QUALITY=720p` (env দিয়ে `1080p/480p/360p/best` করা যাবে)

## Quick start
pip install -r requirements.txt
export BOT_TOKEN=123456:ABC...
# optional: export QUALITY=1080p
# optional: export DEFAULT_URL=https://youtu.be/BfLPuDRgjPw
python app.py

# webhook
https://api.telegram.org/bot<token>/setWebhook?url=https://YOUR-DOMAIN?token=<token>
