from flask import Flask, request, jsonify
import os
import re
import requests
import yt_dlp
import time
import logging
from threading import Thread, Lock
from urllib.parse import urlparse

# লগিং সেটআপ
logging.basicConfig(
    level=logging.INFO, 
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('bot.log', encoding='utf-8')
    ]
)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# কনফিগারেশন - environment variable থেকে নেওয়া নিরাপদ
BOT_TOKEN = os.environ.get('BOT_TOKEN', "7628222622:AAHd6XbuWQw1TaurMGu0QWdsJaLF0rIlcj4")
TELEGRAM_API_URL = f"https://api.telegram.org/bot{BOT_TOKEN}"

# লং পোলিং এর জন্য শেষ আপডেট ID
last_update_id = 0
update_lock = Lock()

# Rate limiting
user_requests = {}
MAX_REQUESTS_PER_MINUTE = 5

def is_rate_limited(chat_id):
    """Rate limiting চেক করে"""
    current_time = time.time()
    if chat_id in user_requests:
        # ১ মিনিটের পুরানো requests remove করুন
        user_requests[chat_id] = [
            req_time for req_time in user_requests[chat_id] 
            if current_time - req_time < 60
        ]
        
        # যদি limit exceed করে
        if len(user_requests[chat_id]) >= MAX_REQUESTS_PER_MINUTE:
            return True
        
        user_requests[chat_id].append(current_time)
    else:
        user_requests[chat_id] = [current_time]
    
    return False

def is_valid_youtube_url(text):
    """YouTube URL validation উন্নত version"""
    if not text or not isinstance(text, str):
        return False
    
    # Regex pattern for YouTube URLs
    youtube_regex = (
        r'(https?://)?(www\.)?'
        r'(youtube|youtu|youtube-nocookie)\.(com|be)/'
        r'(watch\?v=|embed/|v/|.+\?v=)?([^&=%\?]{11})'
    )
    
    youtube_match = re.match(youtube_regex, text.strip())
    if youtube_match:
        return True
    
    # Additional check for common YouTube domains
    youtube_domains = [
        'youtube.com',
        'youtu.be',
        'www.youtube.com',
        'm.youtube.com',
        'youtube-nocookie.com'
    ]
    
    try:
        parsed_url = urlparse(text.strip())
        if parsed_url.netloc in youtube_domains:
            return True
    except Exception:
        pass
    
    return False

def send_telegram_message(chat_id, text, parse_mode="HTML", reply_markup=None):
    """Telegram এ মেসেজ সেন্ড করে - improved version"""
    url = f"{TELEGRAM_API_URL}/sendMessage"
    data = {
        'chat_id': chat_id,
        'text': text,
        'parse_mode': parse_mode,
        'disable_web_page_preview': True
    }
    
    if reply_markup:
        data['reply_markup'] = reply_markup
    
    try:
        logger.info(f"Sending message to chat_id: {chat_id}")
        response = requests.post(url, json=data, timeout=30)
        response.raise_for_status()
        result = response.json()
        
        if not result.get('ok', False):
            logger.error(f"Telegram API error: {result}")
            return False
            
        logger.info("Message sent successfully")
        return True
        
    except requests.exceptions.RequestException as e:
        logger.error(f"Network error sending message: {e}")
        return False
    except Exception as e:
        logger.error(f"Unexpected error sending message: {e}")
        return False

def send_telegram_photo(chat_id, photo_url, caption=""):
    """Telegram এ ফটো সেন্ড করে - improved version"""
    url = f"{TELEGRAM_API_URL}/sendPhoto"
    data = {
        'chat_id': chat_id,
        'photo': photo_url,
        'caption': caption,
        'parse_mode': 'HTML',
        'disable_notification': False
    }
    
    try:
        response = requests.post(url, data=data, timeout=30)
        response.raise_for_status()
        result = response.json()
        return result.get('ok', False)
    except requests.exceptions.RequestException as e:
        logger.error(f"Network error sending photo: {e}")
        return False
    except Exception as e:
        logger.error(f"Unexpected error sending photo: {e}")
        return False

def get_video_info(youtube_url):
    """ভিডিও তথ্য সংগ্রহ করে - improved error handling"""
    ydl_opts = {
        'quiet': True, 
        'no_warnings': True,
        'socket_timeout': 30,
        'extract_flat': False
    }
    
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(youtube_url, download=False)
            
            # Description truncate করা
            description = info.get('description', '')
            if description and len(description) > 300:
                description = description[:300] + "..."
            else:
                description = description or "No description available"
            
            return {
                'title': info.get('title', 'Unknown Title'),
                'duration': info.get('duration', 0),
                'uploader': info.get('uploader', 'Unknown Channel'),
                'view_count': info.get('view_count', 0),
                'webpage_url': info.get('webpage_url', youtube_url),
                'thumbnail': info.get('thumbnail', ''),
                'description': description,
                'upload_date': info.get('upload_date', ''),
                'categories': info.get('categories', [])
            }
    except yt_dlp.DownloadError as e:
        logger.error(f"YouTube DL error: {e}")
        raise Exception("Could not fetch video information. Please check the URL.")
    except Exception as e:
        logger.error(f"Unexpected video info error: {e}")
        raise Exception("Error processing video information.")

def format_duration(seconds):
    """সময় ফরম্যাট করে"""
    if not seconds or seconds <= 0:
        return "Unknown"
    
    try:
        minutes, seconds = divmod(int(seconds), 60)
        hours, minutes = divmod(minutes, 60)
        
        if hours > 0:
            return f"{hours}:{minutes:02d}:{seconds:02d}"
        else:
            return f"{minutes}:{seconds:02d}"
    except (TypeError, ValueError):
        return "Unknown"

def format_views(view_count):
    """View count ফরম্যাট করে"""
    if not view_count:
        return "0"
    
    try:
        return f"{int(view_count):,}"
    except (TypeError, ValueError):
        return str(view_count)

def process_youtube_link(chat_id, youtube_url):
    """YouTube লিংক প্রসেস করে - improved version"""
    try:
        # Rate limiting check
        if is_rate_limited(chat_id):
            send_telegram_message(
                chat_id, 
                "⏳ Please wait a moment before making another request."
            )
            return

        # Step 1: ভিডিও তথ্য সংগ্রহ
        send_telegram_message(chat_id, "🔄 Processing YouTube video... Please wait.")
        video_info = get_video_info(youtube_url)
        
        if not video_info:
            send_telegram_message(chat_id, "❌ Could not fetch video information. Please check the URL.")
            return
        
        # Step 2: ভিডিও ইনফো ফরম্যাট করা
        duration_str = format_duration(video_info['duration'])
        views_str = format_views(video_info['view_count'])
        
        # Upload date format করা (যদি থাকে)
        upload_date = video_info.get('upload_date', '')
        if upload_date and len(upload_date) == 8:  # YYYYMMDD format
            formatted_date = f"{upload_date[6:8]}/{upload_date[4:6]}/{upload_date[0:4]}"
        else:
            formatted_date = "Unknown"
        
        caption = f"""
🎬 <b>{video_info['title']}</b>

👤 <b>Channel:</b> {video_info['uploader']}
⏰ <b>Duration:</b> {duration_str}
👀 <b>Views:</b> {views_str}
📅 <b>Uploaded:</b> {formatted_date}

📝 <b>Description:</b>
{video_info['description']}

🔗 <a href="{video_info['webpage_url']}">Watch on YouTube</a>

#YouTube #VideoInfo
        """.strip()
        
        # থাম্বনেল সহ সেন্ড করার চেষ্টা করুন
        thumbnail_sent = False
        if video_info['thumbnail']:
            thumbnail_sent = send_telegram_photo(chat_id, video_info['thumbnail'], caption)
        
        # যদি থাম্বনেল send না হয়, শুধু message send করুন
        if not thumbnail_sent:
            send_telegram_message(chat_id, caption)
        
        logger.info(f"Successfully processed video for chat_id: {chat_id}")
        
    except Exception as e:
        logger.error(f"Process error for chat_id {chat_id}: {e}")
        error_msg = f"❌ Error: {str(e)}"
        send_telegram_message(chat_id, error_msg)

def handle_message(message):
    """মেসেজ হ্যান্ডল করে - improved version"""
    try:
        text = message.get('text', '').strip()
        chat_id = message.get('chat', {}).get('id')
        message_id = message.get('message_id')
        
        logger.info(f"Handling message - chat_id: {chat_id}, text: {text[:100]}...")
        
        if not chat_id:
            logger.warning("No chat_id found in message")
            return
        
        # কমান্ড হ্যান্ডলিং
        if text.startswith('/'):
            if text == '/start':
                welcome_msg = """
🤖 <b>YouTube Video Info Bot</b>

Send me any YouTube link and I will provide detailed information about the video.

<b>Features:</b>
• 📊 Video information & statistics
• 🖼️ Thumbnail preview  
• ⚡ Fast processing
• 📝 Description summary

<b>How to use:</b>
1. Copy any YouTube video URL
2. Paste it here
3. I will send you the complete video information

<b>Supported URLs:</b>
• youtube.com/watch?v=...
• youtu.be/...
• youtube.com/shorts/...
• m.youtube.com/...

<b>Commands:</b>
/start - Start the bot
/help - Show help guide  
/status - Check bot status

Just paste a YouTube URL and I'll handle the rest!
                """.strip()
                
                send_telegram_message(chat_id, welcome_msg)
                    
            elif text == '/help':
                help_msg = """
📖 <b>Help Guide</b>

<b>How to use:</b>
1. Copy any YouTube video URL
2. Paste it in this chat
3. I will process and send you detailed video information

<b>Supported URL formats:</b>
• https://youtube.com/watch?v=ABCD1234
• https://youtu.be/ABCD1234  
• https://youtube.com/shorts/ABCD1234
• https://m.youtube.com/watch?v=ABCD1234

<b>What information you'll get:</b>
• Video title and channel name
• Duration and view count
• Upload date
• Thumbnail image
• Video description

<b>Note:</b> Please ensure the URL is correct and the video is publicly accessible.
                """.strip()
                
                send_telegram_message(chat_id, help_msg)
                
            elif text == '/status':
                status_msg = "✅ <b>Bot Status</b>\n\n🟢 Active and running\n⚡ Long Polling method\n📊 Ready to process YouTube URLs"
                send_telegram_message(chat_id, status_msg)
                
            else:
                unknown_cmd = "❌ Unknown command. Use /help for available commands."
                send_telegram_message(chat_id, unknown_cmd)
        
        # YouTube URL প্রসেসিং
        elif is_valid_youtube_url(text):
            logger.info(f"YouTube URL detected: {text}")
            
            # ব্যাকগ্রাউন্ডে প্রসেস শুরু করুন
            thread = Thread(
                target=process_youtube_link, 
                args=(chat_id, text.strip()),
                name=f"YT-Processor-{chat_id}-{int(time.time())}"
            )
            thread.daemon = True
            thread.start()
        
        # যদি কোনো কমান্ড বা YouTube URL না হয়
        elif text:
            unknown_msg = """
❌ <b>Invalid Input</b>

Please send a valid YouTube URL or use one of the commands:

• <b>YouTube URL</b> - Paste any YouTube video link
• <b>/help</b> - Show instructions
• <b>/status</b> - Check bot status

Examples of valid YouTube URLs:
• https://youtube.com/watch?v=dQw4w9WgXcQ
• https://youtu.be/dQw4w9WgXcQ
• https://youtube.com/shorts/ABC123
            """.strip()
            
            send_telegram_message(chat_id, unknown_msg)
    
    except Exception as e:
        logger.error(f"Message handle error: {e}")

def get_updates():
    """Telegram updates পেতে লং পোলিং ব্যবহার করে - improved version"""
    global last_update_id
    
    try:
        url = f"{TELEGRAM_API_URL}/getUpdates"
        params = {
            'offset': last_update_id + 1,
            'timeout': 25,  # Reduced timeout for better responsiveness
            'allowed_updates': ['message', 'edited_message']
        }
        
        response = requests.get(url, params=params, timeout=30)
        response.raise_for_status()
        data = response.json()
        
        if data.get('ok') and data.get('result'):
            with update_lock:
                for update in data['result']:
                    last_update_id = update['update_id']
                    
                    if 'message' in update and 'text' in update['message']:
                        # নতুন থ্রেডে মেসেজ হ্যান্ডল করুন
                        thread = Thread(
                            target=handle_message, 
                            args=(update['message'],),
                            name=f"Msg-Handler-{update['update_id']}"
                        )
                        thread.daemon = True
                        thread.start()
            
            return True
        else:
            logger.error(f"GetUpdates API error: {data}")
            return False
            
    except requests.exceptions.Timeout:
        logger.info("GetUpdates timeout (normal) - retrying...")
        return True
    except requests.exceptions.RequestException as e:
        logger.error(f"GetUpdates network error: {e}")
        time.sleep(5)  # Network error হলে wait করুন
        return False
    except Exception as e:
        logger.error(f"GetUpdates unexpected error: {e}")
        time.sleep(5)
        return False

def polling_worker():
    """লং পোলিং ওয়ার্কার - improved version"""
    logger.info("Starting Telegram polling worker...")
    
    consecutive_errors = 0
    max_consecutive_errors = 5
    
    while True:
        try:
            success = get_updates()
            
            if success:
                consecutive_errors = 0
            else:
                consecutive_errors += 1
                logger.warning(f"Consecutive errors: {consecutive_errors}")
                
                if consecutive_errors >= max_consecutive_errors:
                    logger.error("Too many consecutive errors, waiting 30 seconds...")
                    time.sleep(30)
                    consecutive_errors = 0
                else:
                    time.sleep(2)  # Short wait before retry
                    
        except Exception as e:
            logger.error(f"Polling worker error: {e}")
            consecutive_errors += 1
            time.sleep(5)

@app.route('/')
def home():
    return jsonify({
        "status": "active",
        "service": "YouTube Telegram Bot",
        "timestamp": time.time(),
        "method": "Long Polling",
        "version": "2.0",
        "endpoints": {
            "home": "/ (GET)",
            "test": "/test (GET)",
            "send_test": "/send_test_message (GET)",
            "bot_info": "/bot_info (GET)",
            "health": "/health (GET)"
        }
    })

@app.route('/test', methods=['GET'])
def test():
    """টেস্ট এন্ডপয়েন্ট"""
    return jsonify({
        "status": "active",
        "timestamp": time.time(),
        "service": "YouTube Telegram Bot",
        "polling": "running",
        "last_update_id": last_update_id
    })

@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    try:
        # বটের status check করুন
        url = f"{TELEGRAM_API_URL}/getMe"
        response = requests.get(url, timeout=10)
        bot_online = response.json().get('ok', False)
        
        return jsonify({
            "status": "healthy" if bot_online else "degraded",
            "bot_online": bot_online,
            "timestamp": time.time(),
            "update_id": last_update_id
        })
    except Exception as e:
        return jsonify({
            "status": "unhealthy",
            "error": str(e),
            "timestamp": time.time()
        }), 500

@app.route('/send_test_message', methods=['GET'])
def send_test_message():
    """টেস্ট মেসেজ সেন্ড - improved version"""
    try:
        chat_id = request.args.get('chat_id')
        if not chat_id:
            return jsonify({
                "status": "error", 
                "message": "chat_id parameter required",
                "example": "/send_test_message?chat_id=123456789"
            })
        
        # Validate chat_id
        try:
            chat_id = int(chat_id)
        except ValueError:
            return jsonify({
                "status": "error", 
                "message": "chat_id must be a valid integer"
            })
        
        test_msg = """
✅ <b>Test Message</b>

This is a test message from YouTube Video Info Bot.

<b>Bot Status:</b> 🟢 Active
<b>Time:</b> {timestamp}

If you can see this message, the bot is working correctly!
        """.strip().format(timestamp=time.strftime("%Y-%m-%d %H:%M:%S"))
        
        if send_telegram_message(chat_id, test_msg):
            return jsonify({
                "status": "success", 
                "message": "Test message sent successfully",
                "chat_id": chat_id
            })
        else:
            return jsonify({
                "status": "error", 
                "message": "Failed to send test message"
            })
            
    except Exception as e:
        logger.error(f"Test message error: {e}")
        return jsonify({
            "status": "error", 
            "message": str(e)
        }), 500

@app.route('/bot_info', methods=['GET'])
def bot_info():
    """বট ইনফো - improved version"""
    try:
        url = f"{TELEGRAM_API_URL}/getMe"
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        result = response.json()
        
        if result.get('ok'):
            bot_user = result['result']
            return jsonify({
                "status": "success",
                "bot_info": {
                    "id": bot_user.get('id'),
                    "username": bot_user.get('username'),
                    "first_name": bot_user.get('first_name'),
                    "is_bot": bot_user.get('is_bot'),
                    "can_join_groups": bot_user.get('can_join_groups'),
                    "can_read_all_group_messages": bot_user.get('can_read_all_group_messages'),
                    "supports_inline_queries": bot_user.get('supports_inline_queries')
                }
            })
        else:
            return jsonify({
                "status": "error",
                "message": "Failed to get bot info from Telegram"
            }), 500
        
    except Exception as e:
        logger.error(f"Bot info error: {e}")
        return jsonify({
            "status": "error",
            "message": str(e)
        }), 500

# Error handlers
@app.errorhandler(404)
def not_found(error):
    return jsonify({
        "status": "error",
        "message": "Endpoint not found"
    }), 404

@app.errorhandler(500)
def internal_error(error):
    return jsonify({
        "status": "error",
        "message": "Internal server error"
    }), 500

if __name__ == '__main__':
    # Warning messages for security
    if BOT_TOKEN == "7628222622:AAHd6XbuWQw1TaurMGu0QWdsJaLF0rIlcj4":
        logger.warning("Using default BOT_TOKEN! For production, set BOT_TOKEN environment variable.")
    
    # লং পোলিং ওয়ার্কার শুরু করুন
    poll_thread = Thread(target=polling_worker, name="Polling-Worker")
    poll_thread.daemon = True
    poll_thread.start()
    
    port = int(os.environ.get('PORT', 5000))
    host = os.environ.get('HOST', '0.0.0.0')
    
    logger.info(f"Starting server on {host}:{port}")
    logger.info("YouTube Telegram Bot is running with improved Long Polling method")
    
    # Production এ debug=False রাখুন
    debug_mode = os.environ.get('DEBUG', 'false').lower() == 'true'
    app.run(host=host, port=port, debug=debug_mode, use_reloader=False)