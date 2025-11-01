from flask import Flask, request, jsonify
import os
import requests
import yt_dlp
import tempfile
import threading
import time
import logging

# লগিং সেটআপ
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

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

@app.route('/')
def home():
    return jsonify({
        "status": "active",
        "service": "YouTube Telegram Bot",
        "timestamp": time.time(),
        "bot_token": BOT_TOKEN[:10] + "..." if BOT_TOKEN else "missing",
        "endpoints": {
            "webhook": "/webhook (POST)",
            "test": "/test (GET)",
            "set_webhook": "/set_webhook (GET)",
            "delete_webhook": "/delete_webhook (GET)",
            "webhook_info": "/webhook_info (GET)"
        }
    })

@app.route('/webhook', methods=['POST', 'GET'])
def webhook():
    """Telegram webhook handler"""
    try:
        logger.info(f"Webhook received: {request.method}")
        
        if request.method == 'GET':
            return jsonify({"status": "webhook_active", "method": "use POST"})
        
        data = request.get_json()
        logger.info(f"Webhook data: {data}")
        
        if not data:
            logger.warning("No JSON data received")
            return jsonify({"status": "no data"})
        
        # মেসেজ চেক
        message = data.get('message', {})
        text = message.get('text', '')
        chat_id = message.get('chat', {}).get('id')
        
        logger.info(f"Message received - chat_id: {chat_id}, text: {text}")
        
        if not chat_id:
            logger.warning("No chat_id found")
            return jsonify({"status": "invalid message"})
        
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
                
                if send_telegram_message(chat_id, welcome_msg):
                    logger.info("Start command processed successfully")
                    return jsonify({"status": "welcome sent"})
                else:
                    logger.error("Failed to send welcome message")
                    return jsonify({"status": "send failed"})
                    
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
                return jsonify({"status": "help sent"})
                
            elif text == '/status':
                status_msg = "✅ Bot is active and running!"
                send_telegram_message(chat_id, status_msg)
                return jsonify({"status": "status sent"})
        
        # YouTube URL প্রসেসিং
        if is_youtube_url(text):
            logger.info(f"YouTube URL detected: {text}")
            
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
        
        # যদি কোনো কমান্ড বা YouTube URL না হয়
        if text and not text.startswith('/'):
            unknown_msg = "❌ Please send a valid YouTube URL or use /help for instructions"
            send_telegram_message(chat_id, unknown_msg)
        
        return jsonify({"status": "ignored", "message": "Not a YouTube link or command"})
    
    except Exception as e:
        logger.error(f"Webhook error: {e}")
        return jsonify({"status": "error", "message": str(e)})

@app.route('/set_webhook', methods=['GET'])
def set_webhook():
    """Webhook সেটআপ"""
    try:
        webhook_url = f"https://{request.host}/webhook"
        url = f"{TELEGRAM_API_URL}/setWebhook"
        data = {'url': webhook_url}
        
        logger.info(f"Setting webhook to: {webhook_url}")
        response = requests.post(url, data=data, timeout=10)
        result = response.json()
        
        logger.info(f"Webhook set result: {result}")
        
        return jsonify({
            "status": "success" if result.get('ok') else "failed",
            "webhook_url": webhook_url,
            "result": result
        })
    except Exception as e:
        logger.error(f"Webhook set error: {e}")
        return jsonify({
            "status": "error",
            "message": str(e)
        })

@app.route('/delete_webhook', methods=['GET'])
def delete_webhook():
    """Webhook ডিলিট"""
    try:
        url = f"{TELEGRAM_API_URL}/deleteWebhook"
        response = requests.post(url, timeout=10)
        result = response.json()
        
        return jsonify({
            "status": "success" if result.get('ok') else "failed",
            "result": result
        })
    except Exception as e:
        return jsonify({
            "status": "error",
            "message": str(e)
        })

@app.route('/webhook_info', methods=['GET'])
def webhook_info():
    """Webhook ইনফো"""
    try:
        url = f"{TELEGRAM_API_URL}/getWebhookInfo"
        response = requests.get(url, timeout=10)
        result = response.json()
        
        return jsonify({
            "status": "success",
            "webhook_info": result
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
        "bot_token_set": True,
        "host": request.host
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

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    logger.info(f"Starting server on port {port}")
    app.run(host='0.0.0.0', port=port, debug=False)