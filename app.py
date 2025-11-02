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
logger = logging.getLogger("yt_downloader")

app = Flask(__name__)

# --------------------------------
# Global Constants
# --------------------------------
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50 MB


# --------------------------------
# Helper Functions
# --------------------------------
def send_telegram_message(chat_id, text, parse_mode='Markdown', reply_to_message_id=None):
    """Format Telegram reply JSON"""
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
    """Get video info safely using yt_dlp"""
    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
        'skip_download': True,
        'extract_flat': False,
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            if not info:
                logger.warning("yt-dlp returned None for video info.")
            return info
    except yt_dlp.utils.DownloadError as e:
        logger.error(f"yt-dlp DownloadError: {str(e)}")
        return None
    except Exception as e:
        logger.error(f"Video info extraction error: {e}")
        return None


def download_video(url):
    """Download video to a temporary folder"""
    temp_dir = tempfile.mkdtemp()
    ydl_opts = {
        'outtmpl': os.path.join(temp_dir, '%(title).100s.%(ext)s'),
        # fallback formats, allows mp4/webm
        'format': 'bestvideo+bestaudio/best[ext=mp4]/best',
        'merge_output_format': 'mp4',
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
            if not video_file:
                logger.error("No video file found in temp directory.")
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
    if not seconds:
        return "অজানা"
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
# Routes
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

        # Simple GET for Render health display
        if request.method == 'GET':
            return jsonify({
                'status': '✅ YouTube Downloader Bot is running on Render',
                'max_file_size': '50MB',
                'platform': 'Render'
            })

        # Handle Telegram webhook POST
        update = request.get_json()
        if not update:
            return jsonify({'error': 'Invalid JSON data'}), 400

        logger.info(f"Update received: {update}")

        message = update.get('message', {})
        chat_id = message.get('chat', {}).get('id')
        text = message.get('text', '')
        msg_id = message.get('message_id')

        if not chat_id:
            return jsonify({'error': 'Chat ID missing'}), 400

        # START command
        if text.startswith('/start'):
            welcome = (
                "🎬 *YouTube Downloader Bot*\n\n"
                "📌 শুধু YouTube লিংক পাঠান — ভিডিও ফেরত পাবেন!\n\n"
                "⚙️ সীমা:\n"
                "• সর্বোচ্চ 50MB\n"
                "• কেবল YouTube ভিডিও সাপোর্ট\n\n"
                "🚀 শুরু করতে একটি লিংক পাঠান।"
            )
            return jsonify(send_telegram_message(chat_id, welcome))

        # HELP command
        if text.startswith('/help'):
            help_msg = (
                "🆘 *সাহায্য*\n\n"
                "🎯 শুধু YouTube লিংক পাঠান:\n"
                "https://youtu.be/VIDEO_ID\n\n"
                "/start - শুরু\n"
                "/help - সাহায্য\n\n"
                "⚡ সীমা: 50MB পর্যন্ত"
            )
            return jsonify(send_telegram_message(chat_id, help_msg))

        # YouTube URL check
        if is_valid_youtube_url(text):
            info = get_video_info(text)
            if not info:
                return jsonify(send_telegram_message(
                    chat_id,
                    "❌ ভিডিও তথ্য পাওয়া যায়নি। লিংকটি সঠিক আছে কি না চেক করুন।",
                    reply_to_message_id=msg_id
                ))

            # Download process start message
            logger.info(f"Downloading video: {info.get('title', 'Unknown')}")
            video_file, info = download_video(text)

            if not video_file or not os.path.exists(video_file):
                return jsonify(send_telegram_message(
                    chat_id,
                    "❌ ভিডিও ডাউনলোড ব্যর্থ। ভিডিওটি হয়তো বড় বা প্রাইভেট।",
                    reply_to_message_id=msg_id
                ))

            file_size = os.path.getsize(video_file)
            if file_size > MAX_FILE_SIZE:
                shutil.rmtree(os.path.dirname(video_file), ignore_errors=True)
                return jsonify(send_telegram_message(
                    chat_id,
                    f"⚠️ ভিডিওটি অনেক বড় ({format_file_size(file_size)}). সর্বোচ্চ 50MB অনুমোদিত।",
                    reply_to_message_id=msg_id
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
                'reply_to_message_id': msg_id
            }

            # Cleanup
            shutil.rmtree(os.path.dirname(video_file), ignore_errors=True)
            return jsonify(response)

        # Invalid command
        return jsonify(send_telegram_message(
            chat_id,
            "❌ অবৈধ ইনপুট। শুধু YouTube লিংক পাঠান অথবা /help লিখুন।",
            reply_to_message_id=msg_id
        ))

    except Exception as e:
        logger.exception("Unhandled error:")
        return jsonify({'error': 'Processing failed', 'details': str(e)}), 500


@app.route('/health', methods=['GET'])
def health_check():
    return jsonify({
        'status': 'healthy',
        'service': 'YouTube Downloader Bot',
        'platform': 'Render'
    })


if __name__ == '__main__':
    # works both locally and on Render
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port)
