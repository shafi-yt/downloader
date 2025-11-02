from flask import Flask, request, jsonify
import os
import yt_dlp
import tempfile
import shutil
import logging
import requests
from urllib.parse import urlparse

# ────────────── 🔹 CONFIG ──────────────
BOT_TOKEN = os.getenv("BOT_TOKEN")  # Telegram bot token
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB limit

# ────────────── 🔹 LOGGING ──────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# ────────────── 🔹 HELPER FUNCTIONS ──────────────
def is_valid_youtube_url(url: str) -> bool:
    if not url:
        return False
    parsed = urlparse(url)
    return any(domain in parsed.netloc for domain in ['youtube.com', 'youtu.be', 'www.youtube.com', 'm.youtube.com'])

def format_size(size_bytes):
    if size_bytes >= 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.1f} MB"
    elif size_bytes >= 1024:
        return f"{size_bytes / 1024:.1f} KB"
    return f"{size_bytes} bytes"

def format_duration(seconds):
    if not seconds:
        return "অজানা সময়"
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    if h:
        return f"{h} ঘন্টা {m} মিনিট"
    return f"{m} মিনিট {s} সেকেন্ড"

def send_message(chat_id, text, reply_to=None):
    data = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "Markdown"
    }
    if reply_to:
        data["reply_to_message_id"] = reply_to
    requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage", json=data)

def send_video(chat_id, video_path, caption, reply_to=None):
    with open(video_path, "rb") as f:
        files = {"video": f}
        data = {
            "chat_id": chat_id,
            "caption": caption,
            "parse_mode": "Markdown"
        }
        if reply_to:
            data["reply_to_message_id"] = reply_to
        res = requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendVideo", data=data, files=files)
    return res.json()

# ────────────── 🔹 GET VIDEO INFO ──────────────
def get_video_info(url):
    try:
        with yt_dlp.YoutubeDL({'quiet': True, 'no_warnings': True}) as ydl:
            return ydl.extract_info(url, download=False)
    except Exception as e:
        logger.error(f"ভিডিও ইনফো পাওয়া যায়নি: {e}")
        return None

# ────────────── 🔹 DOWNLOAD 360P ──────────────
def download_video_360p(url):
    temp_dir = tempfile.mkdtemp(dir="/tmp")
    ydl_opts = {
        "format": "best[height<=360][ext=mp4]",
        "outtmpl": os.path.join(temp_dir, "%(title)s.%(ext)s"),
        "quiet": True,
        "no_warnings": False,
        "noplaylist": True,
        "geo_bypass": True,
        "cookiefile": "/tmp/cookies.txt" if os.path.exists("/tmp/cookies.txt") else None,
        "http_headers": {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                          "AppleWebKit/537.36 (KHTML, like Gecko) "
                          "Chrome/126.0 Safari/537.36"
        }
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            filepath = ydl.prepare_filename(info)
        if not os.path.exists(filepath):
            logger.error("ভিডিও ফাইল তৈরি হয়নি।")
            return None, None
        return filepath, info
    except Exception as e:
        logger.error(f"ডাউনলোড ব্যর্থ: {e}")
        return None, str(e)
    finally:
        logger.info("Cleanup ready.")

# ────────────── 🔹 MAIN TELEGRAM HANDLER ──────────────
@app.route("/", methods=["POST", "GET"])
def webhook():
    if request.method == "GET":
        return jsonify({"status": "YouTube Downloader Bot running ✅", "platform": "Render"})

    update = request.get_json(force=True)
    if not update:
        return jsonify({"error": "No update received"}), 400

    message = update.get("message", {})
    chat_id = message.get("chat", {}).get("id")
    msg_id = message.get("message_id")
    text = message.get("text", "")

    if not chat_id:
        return jsonify({"error": "chat_id missing"}), 400

    if text.startswith("/start"):
        send_message(chat_id, "🎬 *YouTube Downloader Bot*\n\nYouTube ভিডিও লিংক পাঠান, আমি 360p তে পাঠিয়ে দেব!", msg_id)
        return jsonify({"ok": True})

    if not is_valid_youtube_url(text):
        send_message(chat_id, "❌ অনুগ্রহ করে একটি বৈধ YouTube লিংক পাঠান।", msg_id)
        return jsonify({"ok": True})

    send_message(chat_id, "⏳ ভিডিও ইনফো আনা হচ্ছে...", msg_id)

    info = get_video_info(text)
    if not info:
        send_message(chat_id, "❌ ভিডিও তথ্য পাওয়া যায়নি। 🔍 লিংকটি সঠিক আছে কি না চেক করুন।", msg_id)
        return jsonify({"ok": True})

    title = info.get("title", "Untitled")
    uploader = info.get("uploader", "Unknown")
    duration = format_duration(info.get("duration", 0))
    send_message(chat_id, f"🎬 *{title}*\n📺 {uploader}\n⏱️ {duration}\n\n📥 ডাউনলোড শুরু হচ্ছে...", msg_id)

    path, error = download_video_360p(text)

    if not path:
        if error and "Sign in to confirm" in error:
            send_message(chat_id, "⚠️ এই ভিডিওটি দেখতে লগইন প্রয়োজন (বয়স সীমা / প্রাইভেসি সীমাবদ্ধতা)।", msg_id)
        else:
            send_message(chat_id, f"❌ ভিডিও ডাউনলোড ব্যর্থ।\n\n📋 {error}", msg_id)
        return jsonify({"ok": True})

    size = os.path.getsize(path)
    if size > MAX_FILE_SIZE:
        send_message(chat_id, f"❌ ভিডিওটি খুব বড় ({format_size(size)}), সর্বোচ্চ 50MB অনুমোদিত।", msg_id)
        shutil.rmtree(os.path.dirname(path), ignore_errors=True)
        return jsonify({"ok": True})

    caption = f"🎬 *{title}*\n📺 {uploader}\n⏱️ {duration}\n📦 {format_size(size)}\n✅ ডাউনলোড সম্পূর্ণ!"
    send_video(chat_id, path, caption, msg_id)

    shutil.rmtree(os.path.dirname(path), ignore_errors=True)
    return jsonify({"ok": True})

# ────────────── 🔹 HEALTH ROUTE ──────────────
@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "healthy", "service": "YouTube Bot"})

# ────────────── 🔹 MAIN ──────────────
if __name__ == "__main__":
    port = int(os.getenv("PORT", 10000))
    app.run(host="0.0.0.0", port=port)