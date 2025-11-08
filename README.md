# Telegram YouTube Downloader Bot (Flask, Render)

**Webhook style compatible** — একই `"/"` এন্ডপয়েন্টে `?token=YOUR_BOT_TOKEN` কুয়েরি প্যারাম লাগবে (আপনার পুরনো কোডের মতো)।
- POST আপডেট এলে সঙ্গে সঙ্গে webhook JSON–এ `sendMessage` দিয়ে ACK দেয়
- ব্যাকগ্রাউন্ড থ্রেডে ডাউনলোড করে **Multipart** দিয়ে ভিডিও/অডিও আপলোড করে

> ⚠️ কেবলমাত্র আইনত অনুমোদিত/নিজস্ব কনটেন্টে ব্যবহার করুন। YouTube TOS মেনে চলুন।

## Commands
- `/ytdlp <url>` – yt-dlp (CLI), ~50MB MP4
- `/ytdlpa <url>` – yt_dlp Python API
- `/pytube <url>` – pytubefix/pytube fallback
- `/audio <url>` – m4a/mp3 (অডিও)
- `/360 <url>` – 360p টার্গেট
- `/720 <url>` – 720p টার্গেট
- `/best <url>` – সীমার মধ্যে সেরা সম্ভব
- `/help` – সাহায্য

## Deploy (Render)
1. এই রিপো GitHub-এ পুশ করুন
2. Render → **New** → **Web Service** → রিপো সিলেক্ট
3. **Build Command**: `pip install -r requirements.txt`  
   **Start Command**: `gunicorn -w 2 -b 0.0.0.0:$PORT app:app`
4. Env Vars: (কিছু লাগবে না—এই অ্যাপ টোকেন URL-কোয়েরি থেকেই নেয়)
5. BotFather থেকে বট তৈরি করুন → TOKEN নিন
6. Telegram webhook সেটআপ করুন (TOKEN কুয়েরি দিয়ে):
   ```bash
   curl -X POST "https://api.telegram.org/bot<YOUR_TOKEN>/setWebhook" \
        -d "url=https://your-app.onrender.com/?token=<YOUR_TOKEN>"
   ```
   > আপনার বট তখন Telegram → আপনার URL–এ POST পাঠাবে। আমরা `?token=` পড়ে একই টোকেন দিয়ে API কল করব।

## Local run
```bash
export PORT=10000
python app.py
```
Webhook পরীক্ষায় `ngrok` টানেল করে উপরের মতো `setWebhook` দিন।
