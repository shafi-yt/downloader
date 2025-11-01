from flask import Flask, request, jsonify
import telegram
import yt_dlp
import os
import tempfile
import requests
import threading
import time
from urllib.parse import urlparse

app = Flask(__name__)

# কনফিগারেশন
BOT_TOKEN = "7628222622:AAHd6XbuWQw1TaurMGu0QWdsJaLF0rIlcj4"
WEBHOOK_URL = "https://your-app-name.onrender.com/webhook"  # আপনার Render URL
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB

# বট ইনিশিয়ালাইজ
bot = telegram.Bot(token=BOT_TOKEN)

def is_youtube_url(text):
    """YouTube URL চেক করে"""
    return any(domain in text.lower() for domain in ['youtube.com', 'youtu.be'])

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
            }
    except Exception as e:
        print(f"Video info error: {e}")
        return None

def download_and_upload(chat_id, youtube_url):
    """ব্যাকগ্রাউন্ডে ডাউনলোড এবং আপলোড করে"""
    try:
        # ভিডিও তথ্য
        bot.send_message(chat_id, "🔄 Processing YouTube video...")
        video_info = get_video_info(youtube_url)
        
        if not video_info:
            bot.send_message(chat_id, "❌ Could not fetch video information")
            return
        
        bot.send_message(chat_id, f"📹 Found: {video_info['title']}\n⬇️ Downloading...")
        
        # টেম্পোরারি ডাউনলোড
        temp_dir = tempfile.gettempdir()
        ydl_opts = {
            'outtmpl': os.path.join(temp_dir, '%(title).100s.%(ext)s'),
            'format': 'best[height<=360]',  # ছোট সাইজ
            'quiet': True,
        }
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(youtube_url, download=True)
            file_path = ydl.prepare_filename(info)
        
        # ফাইল সাইজ চেক
        file_size = os.path.getsize(file_path)
        if file_size > MAX_FILE_SIZE:
            bot.send_message(chat_id, "❌ Video file is too large")
            os.remove(file_path)
            return
        
        # আপলোড
        bot.send_message(chat_id, f"📤 Uploading ({file_size//1024//1024}MB)...")
        
        caption = f"🎬 {video_info['title']}\n👤 {video_info['uploader']}\n🔗 {youtube_url}"
        
        with open(file_path, 'rb') as video_file:
            bot.send_video(
                chat_id=chat_id,
                video=video_file,
                caption=caption,
                supports_streaming=True,
                timeout=120
            )
        
        # ক্লিনআপ
        os.remove(file_path)
        bot.send_message(chat_id, "✅ Video uploaded successfully!")
        
    except Exception as e:
        bot.send_message(chat_id, f"❌ Error: {str(e)}")
        print(f"Upload error: {e}")

@app.route('/')
def home():
    return "YouTube Video Bot is Running!"

@app.route('/webhook', methods=['POST'])
def webhook():
    """Telegram webhook handler"""
    update = telegram.Update.de_json(request.get_json(), bot)
    
    if update.message and update.message.text:
        text = update.message.text
        chat_id = update.message.chat.id
        
        if is_youtube_url(text):
            # ব্যাকগ্রাউন্ডে প্রসেস শুরু করুন
            thread = threading.Thread(
                target=download_and_upload, 
                args=(chat_id, text)
            )
            thread.daemon = True
            thread.start()
            
            return jsonify({"status": "processing"})
    
    return jsonify({"status": "ok"})

@app.route('/set_webhook', methods=['GET'])
def set_webhook():
    """Webhook সেটআপ"""
    try:
        bot.set_webhook(WEBHOOK_URL)
        return "Webhook set successfully!"
    except Exception as e:
        return f"Error setting webhook: {e}"

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False)