from flask import Flask, request, jsonify
import os
import requests
import yt_dlp
import time
import logging
from threading import Thread

# লগিং সেটআপ
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = Flask(__name__)

# কনফিগারেশন
BOT_TOKEN = "7628222622:AAHd6XbuWQw1TaurMGu0QWdsJaLF0rIlcj4"
TELEGRAM_API_URL = f"https://api.telegram.org/bot{BOT_TOKEN}"

# লং পোলিং এর জন্য শেষ আপডেট ID
last_update_id = 0

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
        logger.info(f"Sending message to chat_id: {chat_id}")
        response = requests.post(url, data=data, timeout=30)
        result = response.json()
        logger.info(f"Telegram API response: {result}")
        return result.get('ok', False)
    except Exception as e:
        logger.error(f"Message send error: {e}")
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
        logger.error(f"Photo send error: {e}")
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
        logger.error(f"Video info error: {e}")
        return None

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

def process_youtube_link(chat_id, youtube_url):
    """YouTube লিংক প্রসেস করে"""
    try:
        # Step 1: ভিডিও তথ্য সংগ্রহ
        send_telegram_message(chat_id, "🔄 Processing YouTube video...")
        video_info = get_video_info(youtube_url)
        
        if not video_info:
            send_telegram_message(chat_id, "❌ Could not fetch video information")
            return
        
        # Step 2: ভিডিও ইনফো সেন্ড
        duration_str = format_duration(video_info['duration'])
        
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
        
        send_telegram_message(chat_id, "✅ Video information sent successfully!")
        
    except Exception as e:
        logger.error(f"Process error: {e}")
        send_telegram_message(chat_id, f"❌ Error: {str(e)}")

def handle_message(message):
    """মেসেজ হ্যান্ডল করে"""
    try:
        text = message.get('text', '')
        chat_id = message.get('chat', {}).get('id')
        
        logger.info(f"Handling message - chat_id: {chat_id}, text: {text}")
        
        if not chat_id:
            logger.warning("No chat_id found")
            return
        
        # কমান্ড হ্যান্ডলিং
        if text.startswith('/'):
            if text == '/start':
                welcome_msg = """
🤖 <b>YouTube Video Bot</b>

Send me any YouTube link and I will process it for you.

<b>Features:</b>
• Video information
• Thumbnail preview  
• Fast processing

<b>How to use:</b>
1. Copy any YouTube video URL
2. Paste it here
3. I will send you the video information

<b>Supported formats:</b>
• youtube.com/watch?v=...
• youtu.be/...
• youtube.com/shorts/...

Just paste a YouTube URL and I'll handle the rest!
                """.strip()
                
                send_telegram_message(chat_id, welcome_msg)
                    
            elif text == '/help':
                help_msg = """
📖 <b>Help Guide</b>

<b>How to use:</b>
1. Copy any YouTube video URL
2. Paste it here
3. I will process and send you the video information

<b>Supported URLs:</b>
• https://youtube.com/watch?v=ABCD1234
• https://youtu.be/ABCD1234  
• https://youtube.com/shorts/ABCD1234

<b>Note:</b> I will send video title, thumbnail, duration, and description.
                """.strip()
                
                send_telegram_message(chat_id, help_msg)
                
            elif text == '/status':
                status_msg = "✅ Bot is active and running!"
                send_telegram_message(chat_id, status_msg)
        
        # YouTube URL প্রসেসিং
        elif is_youtube_url(text):
            logger.info(f"YouTube URL detected: {text}")
            
            # ব্যাকগ্রাউন্ডে প্রসেস শুরু করুন
            thread = Thread(
                target=process_youtube_link, 
                args=(chat_id, text.strip())
            )
            thread.daemon = True
            thread.start()
        
        # যদি কোনো কমান্ড বা YouTube URL না হয়
        elif text:
            unknown_msg = "❌ Please send a valid YouTube URL or use /help for instructions"
            send_telegram_message(chat_id, unknown_msg)
    
    except Exception as e:
        logger.error(f"Message handle error: {e}")

def get_updates():
    """Telegram updates পেতে লং পোলিং ব্যবহার করে"""
    global last_update_id
    
    try:
        url = f"{TELEGRAM_API_URL}/getUpdates"
        params = {
            'offset': last_update_id + 1,
            'timeout': 30,
            'allowed_updates': ['message']
        }
        
        response = requests.get(url, params=params, timeout=35)
        
        if response.status_code == 200:
            data = response.json()
            
            if data.get('ok') and data.get('result'):
                for update in data['result']:
                    last_update_id = update['update_id']
                    
                    if 'message' in update:
                        # নতুন থ্রেডে মেসেজ হ্যান্ডল করুন
                        thread = Thread(target=handle_message, args=(update['message'],))
                        thread.daemon = True
                        thread.start()
            
            return True
        else:
            logger.error(f"GetUpdates error: {response.status_code}")
            return False
            
    except requests.exceptions.Timeout:
        # টাইমআউট স্বাভাবিক, শুধু লগ করুন
        logger.info("GetUpdates timeout (normal)")
        return True
    except Exception as e:
        logger.error(f"GetUpdates error: {e}")
        return False

def polling_worker():
    """লং পোলিং ওয়ার্কার"""
    logger.info("Starting Telegram polling worker...")
    
    while True:
        try:
            if not get_updates():
                # যদি error হয়, 5 সেকেন্ড অপেক্ষা করুন
                time.sleep(5)
        except Exception as e:
            logger.error(f"Polling worker error: {e}")
            time.sleep(5)

@app.route('/')
def home():
    return jsonify({
        "status": "active",
        "service": "YouTube Telegram Bot",
        "timestamp": time.time(),
        "method": "Long Polling",
        "endpoints": {
            "home": "/ (GET)",
            "test": "/test (GET)",
            "send_test": "/send_test_message (GET)"
        }
    })

@app.route('/test', methods=['GET'])
def test():
    """টেস্ট এন্ডপয়েন্ট"""
    return jsonify({
        "status": "active",
        "timestamp": time.time(),
        "service": "YouTube Telegram Bot",
        "polling": "running"
    })

@app.route('/send_test_message', methods=['GET'])
def send_test_message():
    """টেস্ট মেসেজ সেন্ড"""
    try:
        chat_id = request.args.get('chat_id')
        if not chat_id:
            return jsonify({"status": "error", "message": "chat_id parameter required"})
        
        test_msg = "✅ Test message from YouTube Bot!\n\nThis confirms the bot is working properly."
        
        if send_telegram_message(chat_id, test_msg):
            return jsonify({"status": "success", "message": "Test message sent"})
        else:
            return jsonify({"status": "error", "message": "Failed to send test message"})
            
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})

@app.route('/bot_info', methods=['GET'])
def bot_info():
    """বট ইনফো"""
    try:
        url = f"{TELEGRAM_API_URL}/getMe"
        response = requests.get(url, timeout=10)
        result = response.json()
        
        return jsonify({
            "status": "success",
            "bot_info": result
        })
    except Exception as e:
        return jsonify({
            "status": "error",
            "message": str(e)
        })

if __name__ == '__main__':
    # লং পোলিং ওয়ার্কার শুরু করুন
    poll_thread = Thread(target=polling_worker)
    poll_thread.daemon = True
    poll_thread.start()
    
    port = int(os.environ.get('PORT', 5000))
    logger.info(f"Starting server on port {port}")
    logger.info("Bot is running with Long Polling method")
    app.run(host='0.0.0.0', port=port, debug=False)