import os
import logging
import requests
import yt_dlp
from flask import Flask, request, jsonify

# 🔹 Flask App
app = Flask(__name__)

# 🔹 Logging config
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# 🔹 Bot Token (Environment Variable থেকে নাও)
BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise ValueError("❌ BOT_TOKEN environment variable missing!")

# 🔹 Telegram API Base
TELEGRAM_API = f"https://api.telegram.org/bot{BOT_TOKEN}"

# 🔹 সর্বোচ্চ অনুমোদিত সাইজ (Telegram limit)
MAX_FILE_SIZE_MB = 50


def send_message(chat_id, text, reply_to=None):
    """সহজ মেসেজ সেন্ডার"""
    data = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "Markdown"
    }
    if reply_to:
        data["reply_to_message_id"] = reply_to
    requests.post(f"{TELEGRAM_API}/sendMessage", data=data)


def send_stream_video(chat_id, youtube_url, reply_to=None):
    """YouTube → Stream → Telegram Upload"""
    try:
        logger.info(f"🎬 Processing video: {youtube_url}")

        ydl_opts = {
            "quiet": True,
            "no_warnings": True,
            "format": "best[height<=360][ext=mp4]"  # safe for streaming
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(youtube_url, download=False)

        video_url = info.get("url")
        title = info.get("title", "Untitled")
        uploader = info.get("uploader", "Unknown")
        duration = info.get("duration", 0)

        if not video_url:
            send_message(chat_id, "❌ ভিডিওর stream URL পাওয়া যায়নি।", reply_to)
            return

        caption = f"""
🎬 *{title}*
📺 {uploader}
⏱️ {duration} seconds

⚡ Powered by Render
"""

        logger.info("📡 স্ট্রিম শুরু হচ্ছে...")
        stream = requests.get(video_url, stream=True, timeout=60)

        # Telegram এ সরাসরি স্ট্রিম পাঠানো
        files = {
            "video": ("video.mp4", stream.raw, "video/mp4")
        }
        data = {
            "chat_id": chat_id,
            "caption": caption,
            "parse_mode": "Markdown"
        }

        logger.info("🚀 Telegram এ আপলোড হচ্ছে...")
        res = requests.post(f"{TELEGRAM_API}/sendVideo", data=data, files=files)

        if res.status_code != 200:
            logger.error(f"❌ Telegram upload failed: {res.text}")
            send_message(chat_id, "❌ ভিডিও আপলোড ব্যর্থ। হতে পারে ভিডিওটি বড় বা রেস্ট্রিক্টেড।", reply_to)
        else:
            logger.info("✅ ভিডিও সফলভাবে পাঠানো হয়েছে!")

    except Exception as e:
        logger.exception("❌ ভিডিও আপলোডে ত্রুটি ঘটেছে।")
        send_message(chat_id, f"❌ ভিডিও ডাউনলোড ব্যর্থ। ভিডিওটি হয়তো বড়, প্রাইভেট, বা রেস্ট্রিক্টেড।\n\n📋 Error: {e}", reply_to)


@app.route("/", methods=["GET", "POST"])
def webhook():
    """Main Webhook handler"""
    if request.method == "GET":
        return jsonify({
            "status": "✅ YouTube Stream Bot is running!",
            "platform": "Render",
            "max_file_size": f"{MAX_FILE_SIZE_MB}MB"
        })

    if request.method == "POST":
        update = request.get_json()
        logger.info(f"📩 Update received: {update}")

        if not update or "message" not in update:
            return jsonify({"ok": True})

        message = update["message"]
        chat_id = message["chat"]["id"]
        text = message.get("text", "")
        msg_id = message.get("message_id")

        if text.startswith("/start"):
            send_message(chat_id, "🎬 স্বাগতম!\n\nYouTube ভিডিও লিংক পাঠান, আমি সরাসরি Telegram-এ পাঠাবো!", msg_id)
        elif text.startswith("/help"):
            send_message(chat_id, "📖 শুধু YouTube ভিডিও লিংক দিন (50MB এর নিচে)।", msg_id)
        elif "youtube.com" in text or "youtu.be" in text:
            send_message(chat_id, "⏳ ভিডিও প্রসেস হচ্ছে...", msg_id)
            send_stream_video(chat_id, text, msg_id)
        else:
            send_message(chat_id, "❌ শুধু YouTube লিংক দিন অথবা /start ব্যবহার করুন।", msg_id)

        return jsonify({"ok": True})


@app.route("/health", methods=["GET"])
def health():
    """Render health check endpoint"""
    return jsonify({"status": "healthy", "service": "YouTube Stream Bot"})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
