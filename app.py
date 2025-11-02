from flask import Flask, request, jsonify
import os
import yt_dlp
import tempfile
import shutil
import logging
from urllib.parse import urlparse

# 🔹 লগ কনফিগারেশন (Render লগে দেখা যাবে)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# 🔹 সর্বোচ্চ ফাইল সাইজ (50MB)
MAX_FILE_SIZE = 50 * 1024 * 1024


# ──────────────────────────────
# 🔸 সহায়ক ফাংশনসমূহ
# ──────────────────────────────

def send_telegram_message(chat_id, text, parse_mode='Markdown', reply_to_message_id=None):
    """Telegram API এর জন্য JSON রেসপন্স তৈরি করে"""
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
# 🔸 yt-dlp ভিত্তিক 360p ডাউনলোড
# ──────────────────────────────

def download_video_360p(url):
    """Render-এ 360p ভিডিও ডাউনলোড (FFmpeg ছাড়াই)"""
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
        logger.exception(f"❌ yt-dlp ত্রুটি: {e}")
        return None, None
    finally:
        # ⚠️ Render টেম্প ফাইল ক্লিনআপ করে না, তাই নিজে ম্যানেজ করো
        logger.info("🧹 Temporary directory ready for cleanup if needed.")


# ──────────────────────────────
# 🔸 Flask Webhook হ্যান্ডলার
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

        # /start কমান্ড
        if text.startswith("/start"):
            return jsonify(send_telegram_message(
                chat_id, "🎬 *YouTube Downloader Bot*\n\nYouTube ভিডিওর লিংক পাঠান এবং বট 360p ভিডিও পাঠাবে।\n\n📦 সর্বোচ্চ সাইজ: 50MB",
                reply_to_message_id=message_id
            ))

        # /help কমান্ড
        if text.startswith("/help"):
            return jsonify(send_telegram_message(
                chat_id, "ℹ️ শুধু YouTube ভিডিও লিংক পাঠান। বট 360p ভিডিও পাঠাবে।",
                reply_to_message_id=message_id
            ))

        # YouTube লিংক হ্যান্ডেল
        if is_valid_youtube_url(text):
            processing = send_telegram_message(
                chat_id, "⏳ ভিডিও ডাউনলোড হচ্ছে, অনুগ্রহ করে অপেক্ষা করুন...",
                reply_to_message_id=message_id
            )

            # ডাউনলোড শুরু
            video_path, info = download_video_360p(text)

            if not video_path:
                return jsonify(send_telegram_message(
                    chat_id,
                    "❌ ভিডিও তথ্য পাওয়া যায়নি। 🔍 লিংকটি সঠিক আছে কি না চেক করুন।",
                    reply_to_message_id=message_id
                ))

            size = os.path.getsize(video_path)
            if size > MAX_FILE_SIZE:
                shutil.rmtree(os.path.dirname(video_path), ignore_errors=True)
                return jsonify(send_telegram_message(
                    chat_id,
                    f"❌ ভিডিওটি খুব বড় ({format_file_size(size)}). সর্বোচ্চ 50MB পর্যন্ত অনুমোদিত।",
                    reply_to_message_id=message_id
                ))

            caption = f"""
🎬 *{info.get('title', 'Untitled')}*
📺 *চ্যানেল:* {info.get('uploader', 'Unknown')}
⏱️ *সময়:* {format_duration(info.get('duration', 0))}
📦 *সাইজ:* {format_file_size(size)}
✅ ডাউনলোড সম্পূর্ণ!
            """

            # Telegram sendVideo মেথড JSON রিটার্ন
            response = {
                "method": "sendVideo",
                "chat_id": chat_id,
                "caption": caption,
                "parse_mode": "Markdown",
                "reply_to_message_id": message_id
            }

            # Render ephemeral storage cleanup
            shutil.rmtree(os.path.dirname(video_path), ignore_errors=True)
            return jsonify(response)

        # অন্য ইনপুট হ্যান্ডেল
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
