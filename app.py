from flask import Flask, request, jsonify
import os
import requests
import yt_dlp
import tempfile
import threading
import time

app = Flask(__name__)

# কনফিগারেশন
BOT_TOKEN = "7628222622:AAHd6XbuWQw1TaurMGu0QWdsJaLF0rIlcj4"
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB
TELEGRAM_API_URL = f"https://api.telegram.org/bot{BOT_TOKEN}"

def is_youtube_url(text):
    """YouTube URL চেক করে"""
    if not text:
        return False
    return any(domain in text.lower() for domain in ['youtube.com', 'youtu.be'])

def send_telegram_message(chat_id, text, parse_mode="HTML"):
    """Telegram এ মেসেজ সেন্ড করে"""
    url = f"{TELEGRAM_API_URL}/sendMessage"
    data = {
        'chat_id': chat_id,
        'text': text,
        'parse_mode': parse_mode
    }
    
    try:
        response = requests.post(url, data=data, timeout=30)
        return response.json().get('ok', False)
    except Exception as e:
        print(f"Message send error: {e}")
        return False

def send_telegram_photo(chat_id, photo_url, caption=""):
    """Telegram এ ফটো সেন্ড করে"""
    url = f"{TELEGRAM_API_URL}/sendPhoto"
    data = {
        'chat_id': chat_id,
        'photo': photo_url,
        'caption': caption,
        'parse_mode': 'HTML'
    }
    
    try:
        response = requests.post(url, data=data, timeout=30)
        return response.json().get('ok', False)
    except Exception as e:
        print(f"Photo send error: {e}")
        return False

def send_telegram_video(chat_id, video_path, caption=""):
    """Telegram এ ভিডিও আপলোড করে"""
    url = f"{TELEGRAM_API_URL}/sendVideo"
    
    try:
        with open(video_path, 'rb') as video_file:
            files = {'video': video_file}
            data = {
                'chat_id': chat_id,
                'caption': caption,
                'parse_mode': 'HTML',
                'supports_streaming': True
            }
            response = requests.post(url, files=files, data=data, timeout=120)
            return response.json().get('ok', False)
    except Exception as e:
        print(f"Video upload error: {e}")
        return False

def get_video_info(youtube_url):
    """ভিডিও তথ্য সংগ্রহ করে"""
    ydl_opts = {'quiet': True, 'no_warnings': True}
    
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(youtube_url, download=False)
            return {
                'title': info.get('title', 'Unknown Title'),
                'duration': info.get('duration', 0),
                'uploader': info.get('uploader', 'Unknown Channel'),
                'view_count': info.get('view_count', 0),
                'webpage_url': info.get('webpage_url', youtube_url),
                'thumbnail': info.get('thumbnail', ''),
                'description': info.get('description', '')[:300] + "..." if info.get('description') else "No description"
            }
    except Exception as e:
        print(f"Video info error: {e}")
        return None

def download_video(youtube_url, quality='360'):
    """ভিডিও ডাউনলোড করে"""
    temp_dir = tempfile.gettempdir()
    
    ydl_opts = {
        'outtmpl': os.path.join(temp_dir, '%(title).100s.%(ext)s'),
        'format': f'best[height<={quality}]',
        'quiet': True,
    }
    
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(youtube_url, download=True)
            filename = ydl.prepare_filename(info)
            
            # ফাইল সাইজ চেক
            file_size = os.path.getsize(filename)
            if file_size > MAX_FILE_SIZE:
                os.remove(filename)
                return None, "File too large"
            
            return filename, "Success"
            
    except Exception as e:
        print(f"Download error: {e}")
        return None, str(e)

def format_duration(seconds):
    """সময় ফরম্যাট করে"""
    if not seconds:
        return "Unknown"
    
    minutes, seconds = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    
    if hours > 0:
        return f"{hours}:{minutes:02d}:{seconds:02d}"
    else:
        return f"{minutes}:{seconds:02d}"

def format_file_size(size_bytes):
    """ফাইল সাইজ ফরম্যাট করে"""
    if not size_bytes:
        return "Unknown"
    
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size_bytes < 1024.0:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.1f} TB"

def cleanup_file(file_path):
    """ফাইল ডিলিট করে"""
    try:
        if file_path and os.path.exists(file_path):
            os.remove(file_path)
            print(f"Cleaned up: {file_path}")
    except Exception as e:
        print(f"Cleanup error: {e}")

def process_youtube_link(chat_id, youtube_url):
    """YouTube লিংক প্রসেস করে"""
    try:
        # Step 1: ভিডিও তথ্য সংগ্রহ
        send_telegram_message(chat_id, "🔄 Processing YouTube video...")
        video_info = get_video_info(youtube_url)
        
        if not video_info:
            send_telegram_message(chat_id, "❌ Could not fetch video information")
            return
        
        # Step 2: ইউজারকে ইনফো দিন
        duration_str = format_duration(video_info['duration'])
        send_telegram_message(chat_id, f"📹 Found: {video_info['title']}")
        
        # Step 3: ভিডিও ডাউনলোড করার অপশন
        download_option = "⬇️ Downloading video..."
        send_telegram_message(chat_id, download_option)
        
        # Step 4: ভিডিও ডাউনলোড
        downloaded_file, status = download_video(youtube_url, '360')
        
        if downloaded_file:
            # Step 5: ভিডিও আপলোড
            file_size = os.path.getsize(downloaded_file)
            size_str = format_file_size(file_size)
            
            caption = f"""
🎬 <b>{video_info['title']}</b>

👤 <b>Channel:</b> {video_info['uploader']}
⏰ <b>Duration:</b> {duration_str}
👀 <b>Views:</b> {video_info['view_count']:,}
💾 <b>Size:</b> {size_str}

📝 {video_info['description']}

🔗 <b>Original:</b> {youtube_url}

#YouTube #Video
            """.strip()
            
            send_telegram_message(chat_id, f"📤 Uploading {size_str}...")
            
            # ভিডিও আপলোড
            if send_telegram_video(chat_id, downloaded_file, caption):
                send_telegram_message(chat_id, "✅ Video successfully uploaded!")
            else:
                send_telegram_message(chat_id, "❌ Failed to upload video")
            
            # ক্লিনআপ
            cleanup_file(downloaded_file)
            
        else:
            # যদি ডাউনলোড না হয়, শুধু ইনফো সেন্ড
            send_telegram_message(chat_id, "🔄 Sending video information...")
            
            caption = f"""
🎬 <b>{video_info['title']}</b>

👤 <b>Channel:</b> {video_info['uploader']}
⏰ <b>Duration:</b> {duration_str}
👀 <b>Views:</b> {video_info['view_count']:,}

📝 {video_info['description']}

🔗 <b>Watch Here:</b> {youtube_url}

#YouTube #Video
            """.strip()
            
            # থাম্বনেল সহ সেন্ড
            if video_info['thumbnail']:
                if not send_telegram_photo(chat_id, video_info['thumbnail'], caption):
                    send_telegram_message(chat_id, caption)
            else:
                send_telegram_message(chat_id, caption)
            
            send_telegram_message(chat_id, "✅ Video information sent!")
        
    except Exception as e:
        print(f"Process error: {e}")
        send_telegram_message(chat_id, f"❌ Error: {str(e)}")

@app.route('/')
def home():
    return jsonify({
        "status": "active",
        "service": "YouTube Telegram Bot",
        "timestamp": time.time(),
        "endpoints": {
            "webhook": "/webhook (POST)",
            "test": "/test (GET)",
            "set_webhook": "/set_webhook (GET)"
        }
    })

@app.route('/webhook', methods=['POST'])
def webhook():
    """Telegram webhook handler"""
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({"status": "no data"})
        
        # মেসেজ চেক
        message = data.get('message', {})
        text = message.get('text', '')
        chat_id = message.get('chat', {}).get('id')
        
        if not chat_id or not text:
            return jsonify({"status": "invalid message"})
        
        # কমান্ড হ্যান্ডলিং
        if text.startswith('/'):
            if text == '/start':
                welcome_msg = """
🤖 YouTube Video Bot

Send me any YouTube link and I will process it for you.

Features:
• Video information
• Thumbnail preview  
• Video download (if possible)
• Fast processing

Just paste a YouTube URL and I'll handle the rest!
                """.strip()
                send_telegram_message(chat_id, welcome_msg)
                return jsonify({"status": "welcome sent"})
            elif text == '/help':
                help_msg = """
📖 Help Guide

How to use:
1. Copy any YouTube video URL
2. Paste it here
3. I will process and send you the video

Supported formats:
• youtube.com/watch?v=...
• youtu.be/...
• youtube.com/shorts/...

Note: Large videos may take time to process.
                """.strip()
                send_telegram_message(chat_id, help_msg)
                return jsonify({"status": "help sent"})
        
        # YouTube URL প্রসেসিং
        if is_youtube_url(text):
            # ব্যাকগ্রাউন্ডে প্রসেস শুরু করুন
            thread = threading.Thread(
                target=process_youtube_link, 
                args=(chat_id, text.strip())
            )
            thread.daemon = True
            thread.start()
            
            return jsonify({
                "status": "processing", 
                "message": "YouTube link detected and processing started"
            })
        
        return jsonify({"status": "ignored", "message": "Not a YouTube link"})
    
    except Exception as e:
        print(f"Webhook error: {e}")
        return jsonify({"status": "error", "message": str(e)})

@app.route('/set_webhook', methods=['GET'])
def set_webhook():
    """Webhook সেটআপ"""
    try:
        webhook_url = f"https://{request.host}/webhook"
        url = f"{TELEGRAM_API_URL}/setWebhook"
        data = {'url': webhook_url}
        
        response = requests.post(url, data=data, timeout=10)
        result = response.json()
        
        return jsonify({
            "status": "success" if result.get('ok') else "failed",
            "webhook_url": webhook_url,
            "result": result
        })
    except Exception as e:
        return jsonify({
            "status": "error",
            "message": str(e)
        })

@app.route('/test', methods=['GET'])
def test():
    """টেস্ট এন্ডপয়েন্ট"""
    return jsonify({
        "status": "active",
        "timestamp": time.time(),
        "service": "YouTube Telegram Bot",
        "bot_token": "configured" if BOT_TOKEN else "missing"
    })

@app.route('/info', methods=['GET'])
def info():
    """বট ইনফো"""
    try:
        url = f"{TELEGRAM_API_URL}/getMe"
        response = requests.get(url, timeout=10)
        bot_info = response.json()
        
        return jsonify({
            "bot_info": bot_info,
            "webhook_url": f"https://{request.host}/webhook",
            "status": "operational"
        })
    except Exception as e:
        return jsonify({"error": str(e)})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)