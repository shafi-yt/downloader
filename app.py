from flask import Flask, request, jsonify
import os
import yt_dlp
import tempfile
import shutil
import logging
from urllib.parse import urlparse

# ──────────────────────────────
# 🔹 লগ কনফিগারেশন
# ──────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

app = Flask(__name__)

MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB limit


# ──────────────────────────────
# 🔸 সহায়ক ফাংশনসমূহ
# ──────────────────────────────

def send_telegram_message(chat_id, text, parse_mode='Markdown', reply_to_message_id=None):
    """Telegram API এর জন্য JSON রেসপন্স"""
    data = {
        'method': 'sendMessage',
        'chat_id': chat_id,
        'text': text,
        'parse_mode': parse_mode
    }
    if reply_to_message_id:
        data['reply_to_message_id'] = reply_to_message_id
    return data


def is_valid_youtube_url(url):
    """YouTube লিংক যাচাই"""
    if not url:
        return False
    parsed = urlparse(url)
    return any(domain in parsed.netloc for domain in [
        'youtube.com', 'youtu.be', 'www.youtube.com', 'm.youtube.com'
    ])


def format_file_size(size_bytes):
    """ফাইল সাইজ সুন্দরভাবে দেখানো"""
    if size_bytes >= 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.1f} MB"
    elif size_bytes >= 1024:
        return f"{size_bytes / 1024:.1f} KB"
    else:
        return f"{size_bytes} bytes"


def format_duration(seconds):
    """ভিডিও সময় সুন্দরভাবে দেখানো"""
    if not seconds:
        return "অজানা সময়"
    if seconds < 60:
        return f"{seconds} সেকেন্ড"
    elif seconds < 3600:
        minutes = seconds // 60
        return f"{minutes} মিনিট {seconds % 60} সেকেন্ড"
    else:
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        return f"{hours} ঘন্টা {minutes} মিনিট"


# ──────────────────────────────
# 🔸 ভিডিও ইনফো পাওয়া (ডাউনলোড ছাড়াই)
# ──────────────────────────────
def get_video_info(url):
    """yt-dlp দিয়ে শুধু ইনফো পাওয়া"""
    try:
        with yt_dlp.YoutubeDL({'quiet': True, 'no_warnings': True}) as ydl:
            return ydl.extract_info(url, download=False)
    except Exception as e:
        logger.error(f"❌ ভিডিও ইনফো পাওয়া যায়নি: {e}")
        return None


# ──────────────────────────────
# 🔸 360p ভিডিও ডাউনলোড (FFmpeg ছাড়া)
# ──────────────────────────────
def download_video_360p(url):
    """Render-এ 360p ভিডিও ডাউনলোড"""
    temp_dir = tempfile.mkdtemp(dir="/tmp")
    logger.info(f"📁 Temporary directory created: {temp_dir}")

    ydl_opts = {
        "format": "best[height<=360][ext=mp4]",
        "outtmpl": os.path.join(temp_dir, "%(title)s.%(ext)s"),
        "quiet": True,
        "no_warnings": True,
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info)

        if not os.path.exists(filename):
            logger.error("❌ ভিডিও ফাইল পাওয়া যায়নি।")
            return None, None

        logger.info(f"✅ ভিডিও ডাউনলোড সম্পূর্ণ: {filename}")
        return filename, info

    except Exception as e:
        logger.exception(f"❌ ডাউনলোড ত্রুটি: {e}")
        return None, None
    finally:
        logger.info("🧹 Temporary directory ready for cleanup.")


# ──────────────────────────────
# 🔸 Flask Telegram Webhook হ্যান্ডলার
# ──────────────────────────────
@app.route("/", methods=["POST", "GET"])
def index():
    if request.method == "GET":
        return jsonify({
            "status": "YouTube Downloader Bot running",
            "max_file_size": "50MB",
            "platform": "Render"
        })

    if request.method == "POST":
        update = request.get_json()
        if not update:
            return jsonify({"error": "Invalid JSON data"}), 400

        logger.info(f"📩 Update received: {update}")

        message = update.get("message", {})
        chat_id = message.get("chat", {}).get("id")
        message_id = message.get("message_id")
        text = message.get("text", "")

        if not chat_id:
            return jsonify({"error": "Chat ID not found"}), 400

        # /start
        if text.startswith("/start"):
            return jsonify(send_telegram_message(
                chat_id,
                "🎬 *YouTube Downloader Bot*\n\nYouTube ভিডিওর লিংক পাঠান, বট 360p ভিডিও ডাউনলোড করবে।\n\n📦 সর্বোচ্চ সাইজ: 50MB",
                reply_to_message_id=message_id
            ))

        # /help
        if text.startswith("/help"):
            return jsonify(send_telegram_message(
                chat_id,
                "ℹ️ শুধু YouTube ভিডিও লিংক পাঠান, বট স্বয়ংক্রিয়ভাবে 360p ভিডিও পাঠাবে।",
                reply_to_message_id=message_id
            ))

        # YouTube লিংক
        if is_valid_youtube_url(text):
            # ইনফো আগে নিয়ে নিই
            info_preview = get_video_info(text)
            if info_preview:
                title = info_preview.get("title", "Untitled")
                uploader = info_preview.get("uploader", "Unknown")
                duration = format_duration(info_preview.get("duration", 0))
                logger.info(f"🎥 Video found: {title} ({uploader})")

            # প্রসেসিং মেসেজ
            processing_msg = send_telegram_message(
                chat_id,
                f"⏳ ডাউনলোড শুরু হচ্ছে...\n🎬 *{info_preview.get('title', 'ভিডিও')}*\n📺 *{info_preview.get('uploader', 'Unknown')}*",
                reply_to_message_id=message_id
            )

            # ডাউনলোড ট্রাই
            video_path, info = download_video_360p(text)

            # ব্যর্থ হলে ইনফোসহ রিপোর্ট
            if not video_path:
                fail_msg = f"❌ ভিডিও ডাউনলোড ব্যর্থ।\n\n📌 *তথ্য:*\n🎬 {title}\n📺 {uploader}\n⏱️ {duration}\n\n⚠️ ভিডিওটি হয়তো বড়, প্রাইভেট, বা রেস্ট্রিক্টেড।"
                return jsonify(send_telegram_message(
                    chat_id, fail_msg, reply_to_message_id=message_id
                ))

            # সাইজ চেক
            size = os.path.getsize(video_path)
            if size > MAX_FILE_SIZE:
                shutil.rmtree(os.path.dirname(video_path), ignore_errors=True)
                return jsonify(send_telegram_message(
                    chat_id,
                    f"❌ ভিডিওটি খুব বড় ({format_file_size(size)}). সর্বোচ্চ 50MB অনুমোদিত।",
                    reply_to_message_id=message_id
                ))

            # ক্যাপশন
            caption = f"""
🎬 *{info.get('title', 'Untitled')}*
📺 *চ্যানেল:* {info.get('uploader', 'Unknown')}
⏱️ *সময়:* {format_duration(info.get('duration', 0))}
📦 *সাইজ:* {format_file_size(size)}
✅ ডাউনলোড সম্পূর্ণ!
"""

            response = {
                "method": "sendVideo",
                "chat_id": chat_id,
                "caption": caption,
                "parse_mode": "Markdown",
                "reply_to_message_id": message_id
            }

            shutil.rmtree(os.path.dirname(video_path), ignore_errors=True)
            return jsonify(response)

        # অন্য ইনপুট
        else:
            return jsonify(send_telegram_message(
                chat_id,
                "❌ অনুগ্রহ করে একটি বৈধ YouTube ভিডিও লিংক পাঠান।",
                reply_to_message_id=message_id
            ))


@app.route("/health", methods=["GET"])
def health():
    return jsonify({
        "status": "healthy",
        "service": "YouTube Downloader Bot",
        "platform": "Render"
    })


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port, debug=False)
