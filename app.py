from flask import Flask, request, jsonify
import os
import logging
import yt_dlp
import requests
from urllib.parse import urlparse
import tempfile
import shutil
import json

# লগিং কনফিগারেশন
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# টেম্পোরারি ডিরেক্টরি সেটআপ
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB

def send_telegram_message(chat_id, text, parse_mode='Markdown', reply_to_message_id=None):
    """
    Telegram-এ মেসেজ সেন্ড করার জন্য সহায়ক ফাংশন
    """
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
    """
    ইউটিউব URL ভ্যালিডেশন
    """
    if not url:
        return False
    parsed = urlparse(url)
    return any(domain in parsed.netloc for domain in 
               ['youtube.com', 'www.youtube.com', 'youtu.be', 'm.youtube.com'])

def get_video_info(url):
    """
    yt-dlp ব্যবহার করে ভিডিও ইনফো পাওয়া
    """
    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
    }
    
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            return info
    except Exception as e:
        logger.error(f"Video info extraction error: {e}")
        return None

def download_video(url):
    """
    ভিডিও ডাউনলোড করা - Render-এর জন্য অপ্টিমাইজড
    """
    temp_dir = tempfile.mkdtemp()
    
    ydl_opts = {
        'outtmpl': os.path.join(temp_dir, '%(title).100s.%(ext)s'),
        'format': 'best[filesize<50M][ext=mp4]',
        'quiet': False,
        'no_warnings': False,
        'writethumbnail': True,
        'embedthumbnail': False,
        'noplaylist': True,
    }
    
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            
            # ডাউনলোড করা ফাইল খুঁজে বের করা
            for file in os.listdir(temp_dir):
                file_path = os.path.join(temp_dir, file)
                if os.path.isfile(file_path):
                    if file.endswith(('.mp4', '.webm', '.mkv')):
                        video_file = file_path
                    elif file.endswith(('.jpg', '.webp', '.png')):
                        thumb_file = file_path
            
            return video_file, thumb_file, info
        
    except Exception as e:
        logger.error(f"Download error: {e}")
        # ক্লিনআপ
        shutil.rmtree(temp_dir, ignore_errors=True)
        return None, None, None

def format_file_size(size_bytes):
    """
    ফাইল সাইজ ফরম্যাট করা
    """
    if size_bytes >= 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.1f} MB"
    elif size_bytes >= 1024:
        return f"{size_bytes / 1024:.1f} KB"
    else:
        return f"{size_bytes} bytes"

def format_duration(seconds):
    """
    ডুরেশন ফরম্যাট করা
    """
    if seconds < 60:
        return f"{seconds} সেকেন্ড"
    elif seconds < 3600:
        minutes = seconds // 60
        return f"{minutes} মিনিট {seconds % 60} সেকেন্ড"
    else:
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        return f"{hours} ঘন্টা {minutes} মিনিট"

@app.route('/', methods=['GET', 'POST'])
def handle_request():
    try:
        # URL থেকে টোকেন নেওয়া
        token = request.args.get('token')
        
        if not token:
            return jsonify({
                'error': 'Token required',
                'solution': 'Add ?token=YOUR_BOT_TOKEN to URL',
                'example': 'https://your-app.onrender.com/?token=123456:ABC-DEF'
            }), 400

        # GET request হ্যান্ডেল
        if request.method == 'GET':
            return jsonify({
                'status': 'YouTube Downloader Bot is running on Render',
                'token_received': True if token else False,
                'max_file_size': '50MB',
                'platform': 'Render'
            })

        # POST request হ্যান্ডেল (Telegram Webhook)
        if request.method == 'POST':
            update = request.get_json()
            
            if not update:
                return jsonify({'error': 'Invalid JSON data'}), 400
            
            logger.info(f"Update received: {update}")
            
            # মেসেজ ডেটা এক্সট্র্যাক্ট
            chat_id = None
            message_text = ''
            message_id = None
            
            if 'message' in update:
                chat_id = update['message']['chat']['id']
                message_text = update['message'].get('text', '')
                message_id = update['message'].get('message_id')
            elif 'callback_query' in update:
                # Callback query হ্যান্ডেল (ভবিষ্যতের জন্য)
                return jsonify({'ok': True})
            else:
                return jsonify({'ok': True})

            if not chat_id:
                return jsonify({'error': 'Chat ID not found'}), 400

            # /start কমান্ড হ্যান্ডেল
            if message_text.startswith('/start'):
                welcome_text = """
🎬 *YouTube Video Downloader*

এই বটের মাধ্যমে আপনি YouTube ভিডিও ডাউনলোড করতে পারবেন।

📌 *ব্যবহার 방법:*
1. YouTube ভিডিওর লিংক পাঠান
2. বট স্বয়ংক্রিয়ভাবে ভিডিও ডাউনলোড করবে
3. ভিডিওটি আপনাকে ফেরত দেওয়া হবে

⚡ *সীমাবদ্ধতা:*
• সর্বোচ্চ ফাইল সাইজ: 50MB
• শুধুমাত্র YouTube লিংক সাপোর্টেড

🚀 *শুরু করতে একটি YouTube লিংক পাঠান*
                """
                
                return jsonify(send_telegram_message(
                    chat_id=chat_id,
                    text=welcome_text
                ))

            # /help কমান্ড
            elif message_text.startswith('/help'):
                help_text = """
📌 *YouTube Video Downloader - সাহায্য*

🤖 *কমান্ডস:*
/start - বট শুরু করুন
/help - সাহায্য দেখুন

📥 *ডাউনলোড করতে:*
শুধুমাত্র একটি YouTube ভিডিও লিংক পাঠান

🌐 *সাপোর্টেড লিংক ফরম্যাট:*
• https://youtube.com/watch?v=...
• https://youtu.be/...
• https://m.youtube.com/watch?v=...

⚡ *সীমাবদ্ধতা:*
• সর্বোচ্চ 50MB সাইজ
• শুধুমাত্র ভিডিও ডাউনলোড

🔧 *হোস্টেড: Render*
                """
                
                return jsonify(send_telegram_message(
                    chat_id=chat_id,
                    text=help_text
                ))

            # YouTube URL চেক করা
            elif is_valid_youtube_url(message_text):
                # ভিডিও ইনফো পাওয়া
                video_info = get_video_info(message_text)
                if not video_info:
                    return jsonify(send_telegram_message(
                        chat_id=chat_id,
                        text="❌ ভিডিও তথ্য পাওয়া যায়নি। লিংকটি চেক করুন।",
                        reply_to_message_id=message_id
                    ))
                
                # প্রসেসিং মেসেজ
                processing_msg = send_telegram_message(
                    chat_id=chat_id,
                    text="⏳ ভিডিও ডাউনলোড প্রসেস হচ্ছে...",
                    reply_to_message_id=message_id
                )
                
                # ভিডিও ডাউনলোড
                video_file, thumb_file, info = download_video(message_text)
                
                if not video_file or not os.path.exists(video_file):
                    # ক্লিনআপ
                    if 'temp_dir' in locals():
                        shutil.rmtree(os.path.dirname(video_file), ignore_errors=True)
                    return jsonify(send_telegram_message(
                        chat_id=chat_id,
                        text="❌ ভিডিও ডাউনলোড করা যায়নি। ভিডিওটি খুব বড় হতে পারে (50MB+) অথবা এক্সেস রেস্ট্রিক্টেড।",
                        reply_to_message_id=message_id
                    ))
                
                # ফাইল সাইজ চেক
                file_size = os.path.getsize(video_file)
                if file_size > MAX_FILE_SIZE:
                    # ক্লিনআপ
                    shutil.rmtree(os.path.dirname(video_file), ignore_errors=True)
                    return jsonify(send_telegram_message(
                        chat_id=chat_id,
                        text=f"❌ ভিডিওটি খুব বড় ({format_file_size(file_size)})। সর্বোচ্চ 50MB সাইজের ভিডিও ডাউনলোড করা যাবে।",
                        reply_to_message_id=message_id
                    ))
                
                # ভিডিও তথ্য প্রস্তুত
                title = info.get('title', 'Unknown Title')
                duration = info.get('duration', 0)
                uploader = info.get('uploader', 'Unknown Uploader')
                views = info.get('view_count', 0)
                
                # ক্যাপশন তৈরি
                caption = f"""
🎬 *{title}*

📊 *বিস্তারিত:*
• 📺 চ্যানেল: {uploader}
• ⏱️ সময়: {format_duration(duration)}
• 👀 ভিউ: {views:,}
• 📦 সাইজ: {format_file_size(file_size)}

✅ @YouTubeDownloaderBot
                """
                
                # Telegram-এ ভিডিও সেন্ড করার রেস্পন্স
                response = {
                    'method': 'sendVideo',
                    'chat_id': chat_id,
                    'caption': caption,
                    'parse_mode': 'Markdown',
                    'reply_to_message_id': message_id
                }
                
                # ক্লিনআপ
                shutil.rmtree(os.path.dirname(video_file), ignore_errors=True)
                
                return jsonify(response)

            # অন্য মেসেজের জন্য
            else:
                help_text = """
❌ *ইনভ্যালিড কমান্ড*

📌 সঠিকভাবে ব্যবহার করতে:
1. শুধুমাত্র YouTube ভিডিও লিংক পাঠান
2. অথবা /start বা /help কমান্ড ব্যবহার করুন

🌐 *উদাহরণ:*
https://youtube.com/watch?v=VIDEO_ID
https://youtu.be/VIDEO_ID
                """
                
                return jsonify(send_telegram_message(
                    chat_id=chat_id,
                    text=help_text,
                    reply_to_message_id=message_id
                ))

    except Exception as e:
        logger.error(f'Error: {str(e)}')
        return jsonify({'error': 'Processing failed', 'details': str(e)}), 500

@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint for Render"""
    return jsonify({
        'status': 'healthy',
        'service': 'YouTube Downloader Bot',
        'platform': 'Render'
    })

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port, debug=False)