from flask import Flask, request, jsonify
import os
import logging
import yt_dlp
import tempfile
import shutil
from urllib.parse import urlparse

# --------------------------------
# Logging Configuration
# --------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# --------------------------------
# Flask App Initialization
# --------------------------------
app = Flask(__name__)

# --------------------------------
# Global Constants
# --------------------------------
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB


# --------------------------------
# Helper Functions
# --------------------------------
def send_telegram_message(chat_id, text, parse_mode='Markdown', reply_to_message_id=None):
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
    if not url:
        return False
    parsed = urlparse(url)
    return any(domain in parsed.netloc for domain in
               ['youtube.com', 'www.youtube.com', 'youtu.be', 'm.youtube.com'])


def get_video_info(url):
    ydl_opts = {'quiet': True, 'no_warnings': True}
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            return info
    except Exception as e:
        logger.error(f"Video info extraction error: {e}")
        return None


def download_video(url):
    temp_dir = tempfile.mkdtemp()
    ydl_opts = {
        'outtmpl': os.path.join(temp_dir, '%(title).100s.%(ext)s'),
        'format': 'best[filesize<50M][ext=mp4]/best[ext=mp4]/best',
        'quiet': True,
        'no_warnings': True,
        'noplaylist': True,
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            video_file = None
            for file in os.listdir(temp_dir):
                if file.endswith(('.mp4', '.webm', '.mkv')):
                    video_file = os.path.join(temp_dir, file)
                    break
            return video_file, info
    except Exception as e:
        logger.error(f"Download error: {e}")
        shutil.rmtree(temp_dir, ignore_errors=True)
        return None, None


def format_file_size(size_bytes):
    if size_bytes >= 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.1f} MB"
    elif size_bytes >= 1024:
        return f"{size_bytes / 1024:.1f} KB"
    else:
        return f"{size_bytes} bytes"


def format_duration(seconds):
    if seconds < 60:
        return f"{seconds} সেকেন্ড"
    elif seconds < 3600:
        minutes = seconds // 60
        return f"{minutes} মিনিট {seconds % 60} সেকেন্ড"
    else:
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        return f"{hours} ঘন্টা {minutes} মিনিট"


# --------------------------------
# Flask Routes
# --------------------------------
@app.route('/', methods=['GET', 'POST'])
def handle_request():
    try:
        token = request.args.get('token')
        if not token:
            return jsonify({
                'error': 'Token required',
                'solution': 'Add ?token=YOUR_BOT_TOKEN to URL',
                'example': 'https://your-app.onrender.com/?token=123456:ABC-DEF'
            }), 400

        if request.method == 'GET':
            return jsonify({
                'status': 'YouTube Downloader Bot is running on Render 🚀',
                'token_received': True,
                'max_file_size': '50MB',
                'platform': 'Render'
            })

        update = request.get_json()
        if not update:
            return jsonify({'error': 'Invalid JSON data'}), 400

        logger.info(f"Update received: {update}")

        message = update.get('message', {})
        chat_id = message.get('chat', {}).get('id')
        message_text = message.get('text', '')
        message_id = message.get('message_id')

        if not chat_id:
            return jsonify({'error': 'Chat ID not found'}), 400

        # START Command
        if message_text.startswith('/start'):
            welcome_text = (
                "🎬 *YouTube Video Downloader Bot*\n\n"
                "এই বটের মাধ্যমে আপনি YouTube ভিডিও ডাউনলোড করতে পারবেন।\n\n"
                "📌 *ব্যবহার পদ্ধতি:*\n"
                "1️⃣ YouTube ভিডিও লিংক পাঠান\n"
                "2️⃣ বট ভিডিও ডাউনলোড করবে\n\n"
                "⚡ *সীমাবদ্ধতা:*\n"
                "• সর্বোচ্চ ফাইল সাইজ: 50MB\n"
                "• শুধুমাত্র YouTube ভিডিও সাপোর্টেড\n\n"
                "🚀 শুরু করতে একটি লিংক পাঠান।"
            )
            return jsonify(send_telegram_message(chat_id, welcome_text))

        # HELP Command
        if message_text.startswith('/help'):
            help_text = (
                "📘 *YouTube Downloader Help*\n\n"
                "/start - শুরু করুন\n"
                "/help - সাহায্য দেখুন\n\n"
                "📥 শুধু YouTube লিংক পাঠান:\n"
                "https://youtube.com/watch?v=...\n"
                "https://youtu.be/...\n\n"
                "⚡ সীমা: সর্বোচ্চ 50MB"
            )
            return jsonify(send_telegram_message(chat_id, help_text))

        # YouTube Link
        if is_valid_youtube_url(message_text):
            video_info = get_video_info(message_text)
            if not video_info:
                return jsonify(send_telegram_message(
                    chat_id, "❌ ভিডিও তথ্য পাওয়া যায়নি। লিংকটি চেক করুন।",
                    reply_to_message_id=message_id
                ))

            video_file, info = download_video(message_text)
            if not video_file or not os.path.exists(video_file):
                return jsonify(send_telegram_message(
                    chat_id, "❌ ভিডিও ডাউনলোড ব্যর্থ। ভিডিওটি হয়তো বড় বা প্রাইভেট।",
                    reply_to_message_id=message_id
                ))

            file_size = os.path.getsize(video_file)
            if file_size > MAX_FILE_SIZE:
                shutil.rmtree(os.path.dirname(video_file), ignore_errors=True)
                return jsonify(send_telegram_message(
                    chat_id, f"⚠️ ভিডিওটি অনেক বড় ({format_file_size(file_size)}). সর্বোচ্চ 50MB অনুমোদিত।",
                    reply_to_message_id=message_id
                ))

            caption = (
                f"🎬 *{info.get('title', 'Unknown Title')}*\n"
                f"📺 চ্যানেল: {info.get('uploader', 'Unknown')}\n"
                f"⏱ সময়: {format_duration(info.get('duration', 0))}\n"
                f"👁️ ভিউ: {info.get('view_count', 0):,}\n"
                f"📦 সাইজ: {format_file_size(file_size)}\n\n"
                "✅ @YouTubeDownloaderBot"
            )

            response = {
                'method': 'sendVideo',
                'chat_id': chat_id,
                'caption': caption,
                'parse_mode': 'Markdown',
                'reply_to_message_id': message_id
            }

            shutil.rmtree(os.path.dirname(video_file), ignore_errors=True)
            return jsonify(response)

        # Invalid Message
        invalid_text = (
            "❌ *অবৈধ কমান্ড*\n\n"
            "শুধুমাত্র YouTube লিংক পাঠান অথবা /help কমান্ড ব্যবহার করুন।"
        )
        return jsonify(send_telegram_message(chat_id, invalid_text))

    except Exception as e:
        logger.error(f"Error: {e}")
        return jsonify({'error': 'Processing failed', 'details': str(e)}), 500


@app.route('/health', methods=['GET'])
def health_check():
    return jsonify({
        'status': 'healthy',
        'service': 'YouTube Downloader Bot',
        'platform': 'Render'
    })


# --------------------------------
# Entry Point for Render
# --------------------------------
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port)
