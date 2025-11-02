from flask import Flask, request, jsonify
import os
import requests
import yt_dlp
import tempfile
import shutil
import logging
from urllib.parse import urlparse

# ──────────────────────────────
# 🔹 লগ কনফিগারেশন
# ──────────────────────────────
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

app = Flask(__name__)
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB limit


# ──────────────────────────────
# 🔸 সহায়ক ফাংশন
# ──────────────────────────────
def send_message(chat_id, text, reply_to=None):
    return {
        "method": "sendMessage",
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "Markdown",
        **({"reply_to_message_id": reply_to} if reply_to else {})
    }

def is_valid_youtube_url(url):
    if not url:
        return False
    parsed = urlparse(url)
    return any(domain in parsed.netloc for domain in ["youtube.com", "youtu.be", "m.youtube.com"])

def format_size(size):
    if size >= 1024 * 1024:
        return f"{size / (1024 * 1024):.1f} MB"
    elif size >= 1024:
        return f"{size / 1024:.1f} KB"
    return f"{size} bytes"

def format_duration(seconds):
    if not seconds:
        return "অজানা সময়"
    if seconds < 60:
        return f"{seconds} সেকেন্ড"
    elif seconds < 3600:
        m, s = divmod(seconds, 60)
        return f"{m} মিনিট {s} সেকেন্ড"
    else:
        h, rem = divmod(seconds, 3600)
        m = rem // 60
        return f"{h} ঘন্টা {m} মিনিট"


# ──────────────────────────────
# 🔸 ভিডিও ইনফো পাওয়া
# ──────────────────────────────
def get_video_info(url):
    try:
        with yt_dlp.YoutubeDL({'quiet': True, 'no_warnings': True}) as ydl:
            return ydl.extract_info(url, download=False)
    except Exception as e:
        logger.error(f"ভিডিও ইনফো পাওয়া যায়নি: {e}")
        return None


# ──────────────────────────────
# 🔸 360p ভিডিও ডাউনলোড
# ──────────────────────────────
def download_video(url):
    temp_dir = tempfile.mkdtemp(dir="/tmp")
    ydl_opts = {
        "format": "best[height<=360][ext=mp4]",
        "outtmpl": os.path.join(temp_dir, "%(title)s.%(ext)s"),
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "geo_bypass": True,
        "http_headers": {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                          "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
        },
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info)
        if not os.path.exists(filename):
            return None, None
        return filename, info
    except Exception as e:
        logger.error(f"ডাউনলোড ত্রুটি: {e}")
        return None, None


# ──────────────────────────────
# 🔸 Telegram Upload Helper
# ──────────────────────────────
def send_video_to_telegram(bot_token, chat_id, video_path, caption):
    try:
        with open(video_path, "rb") as f:
            res = requests.post(
                f"https://api.telegram.org/bot{bot_token}/sendVideo",
                data={"chat_id": chat_id, "caption": caption, "parse_mode": "Markdown"},
                files={"video": f},
                timeout=120
            )
        logger.info(f"Telegram upload: {res.status_code}")
        return res.json()
    except Exception as e:
        logger.error(f"Telegram upload ব্যর্থ: {e}")
        return None


# ──────────────────────────────
# 🔸 Flask Routes
# ──────────────────────────────
@app.route("/", methods=["POST", "GET"])
def index():
    if request.method == "GET":
        return jsonify({"status": "Bot Running", "max_file_size": "50MB", "platform": "Render"})

    if request.method == "POST":
        update = request.get_json()
        if not update:
            return jsonify({"error": "Invalid JSON"}), 400

        bot_token = request.args.get("token")
        if not bot_token:
            return jsonify({"error": "Missing bot token (?token=YOUR_BOT_TOKEN)"}), 400

        message = update.get("message", {})
        chat_id = message.get("chat", {}).get("id")
        msg_id = message.get("message_id")
        text = message.get("text", "")

        if not chat_id:
            return jsonify({"error": "No chat_id"}), 400

        # /start
        if text.startswith("/start"):
            return jsonify(send_message(chat_id, "🎬 *YouTube Downloader*\n\nYouTube লিংক পাঠান, আমি 360p ভিডিও পাঠাবো।", msg_id))

        # /help
        if text.startswith("/help"):
            return jsonify(send_message(chat_id, "ℹ️ শুধু YouTube ভিডিও লিংক পাঠান।", msg_id))

        # YouTube লিংক
        if is_valid_youtube_url(text):
            info = get_video_info(text)
            if not info:
                return jsonify(send_message(chat_id, "❌ ভিডিও তথ্য পাওয়া যায়নি। লিংকটি সঠিক কিনা দেখুন।", msg_id))

            title = info.get("title", "Untitled")
            uploader = info.get("uploader", "Unknown")
            duration = format_duration(info.get("duration"))
            logger.info(f"🎥 Downloading: {title}")

            send_msg = send_message(chat_id, f"⏳ ডাউনলোড হচ্ছে...\n🎬 {title}\n📺 {uploader}", msg_id)
            video_path, info = download_video(text)

            if not video_path:
                return jsonify(send_message(chat_id, f"❌ ভিডিও ডাউনলোড ব্যর্থ।\n🎬 {title}\n📺 {uploader}", msg_id))

            size = os.path.getsize(video_path)
            if size > MAX_FILE_SIZE:
                shutil.rmtree(os.path.dirname(video_path), ignore_errors=True)
                return jsonify(send_message(chat_id, f"⚠️ ভিডিওটি বড় ({format_size(size)}). সর্বোচ্চ 50MB অনুমোদিত।", msg_id))

            caption = f"🎬 *{title}*\n📺 *{uploader}*\n⏱️ {duration}\n📦 {format_size(size)}"

            send_video_to_telegram(bot_token, chat_id, video_path, caption)
            shutil.rmtree(os.path.dirname(video_path), ignore_errors=True)
            return jsonify(send_message(chat_id, "✅ ভিডিও পাঠানো হয়েছে!", msg_id))

        # Invalid input
        return jsonify(send_message(chat_id, "❌ অনুগ্রহ করে সঠিক YouTube লিংক পাঠান।", msg_id))


@app.route("/health")
def health():
    return jsonify({"status": "healthy", "platform": "Render"})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port, debug=False)
