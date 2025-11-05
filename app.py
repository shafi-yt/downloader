from flask import Flask, request, jsonify
import os
import logging
import requests
import re
import tempfile
import threading
import time
import urllib.parse
from urllib.parse import urlencode

# লগিং কনফিগারেশন
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Worker endpoint from your provided link
WORKER_ENDPOINT = "https://utubdbot.shafitest.workers.dev/"

# Store download progress and user sessions
download_progress = {}
user_sessions = {}

def send_telegram_message(chat_id, text, parse_mode='HTML', reply_markup=None):
    """
    Telegram-এ মেসেজ সেন্ড করার জন্য সহায়ক ফাংশন
    """
    message_data = {
        'method': 'sendMessage',
        'chat_id': chat_id,
        'text': text,
        'parse_mode': parse_mode
    }
    
    if reply_markup:
        message_data['reply_markup'] = reply_markup
    
    return message_data

def send_telegram_video(chat_id, video_path, caption=None):
    """
    Telegram-এ ভিডিও সেন্ড করার জন্য ফাংশন
    """
    return {
        'method': 'sendVideo',
        'chat_id': chat_id,
        'video': open(video_path, 'rb'),
        'caption': caption,
        'parse_mode': 'HTML'
    }

def create_keyboard(buttons):
    """
    টেলিগ্রাম কীবোর্ড তৈরি করার ফাংশন
    """
    keyboard = {
        'keyboard': buttons,
        'resize_keyboard': True,
        'one_time_keyboard': False
    }
    return keyboard

def extract_youtube_id(url):
    """Extract YouTube video ID from various URL formats"""
    patterns = [
        r'(?:youtube\.com\/watch\?v=|youtu\.be\/)([^&\n?#]+)',
        r'youtube\.com\/embed\/([^&\n?#]+)',
        r'youtube\.com\/v\/([^&\n?#]+)'
    ]
    
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    return None

def get_video_info(video_id):
    """Get video information using the worker endpoint"""
    try:
        # Construct the worker URL
        worker_url = f"{WORKER_ENDPOINT}?url=https://youtu.be/{video_id}.mp4"
        
        # Get video info (we'll use HEAD request to check availability)
        response = requests.head(worker_url, allow_redirects=True, timeout=30)
        
        if response.status_code == 200:
            return {
                'success': True,
                'download_url': worker_url,
                'video_id': video_id,
                'content_type': response.headers.get('content-type', 'video/mp4'),
                'content_length': response.headers.get('content-length', 0)
            }
        else:
            return {'success': False, 'error': 'Video not available'}
            
    except Exception as e:
        logger.error(f"Error getting video info: {e}")
        return {'success': False, 'error': str(e)}

def download_video_with_progress(download_url, chat_id, message_id, token):
    """Download video with progress tracking"""
    try:
        # Update progress
        download_progress[chat_id] = {'status': 'downloading', 'progress': 0}
        
        # Send initial progress
        send_progress_update(chat_id, message_id, token, 0, "Downloading...")
        
        # Download the video
        response = requests.get(download_url, stream=True, timeout=60)
        total_size = int(response.headers.get('content-length', 0))
        
        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.mp4')
        downloaded_size = 0
        
        for chunk in response.iter_content(chunk_size=8192):
            if chunk:
                temp_file.write(chunk)
                downloaded_size += len(chunk)
                
                # Update progress every 5%
                if total_size > 0:
                    progress = (downloaded_size / total_size) * 100
                    if int(progress) % 5 == 0 or progress == 100:
                        download_progress[chat_id] = {
                            'status': 'downloading', 
                            'progress': int(progress)
                        }
                        send_progress_update(chat_id, message_id, token, int(progress), "Downloading...")
        
        temp_file.close()
        download_progress[chat_id] = {'status': 'completed', 'progress': 100}
        
        return temp_file.name
        
    except Exception as e:
        logger.error(f"Download error: {e}")
        download_progress[chat_id] = {'status': 'error', 'error': str(e)}
        send_progress_update(chat_id, message_id, token, 0, f"Error: {str(e)}")
        return None

def send_progress_update(chat_id, message_id, token, progress, status):
    """Send progress update to Telegram"""
    try:
        progress_bar = "🟩" * (progress // 10) + "⬜" * (10 - (progress // 10))
        text = f"📥 {status}\n\n{progress_bar} {progress}%"
        
        url = f"https://api.telegram.org/bot{token}/editMessageText"
        data = {
            'chat_id': chat_id,
            'message_id': message_id,
            'text': text
        }
        requests.post(url, json=data, timeout=10)
    except Exception as e:
        logger.error(f"Progress update error: {e}")

def start_download_thread(chat_id, youtube_url, message_id, token):
    """Start download in separate thread"""
    def download_job():
        try:
            # Extract video ID
            video_id = extract_youtube_id(youtube_url)
            if not video_id:
                send_telegram_message_direct(chat_id, token, "❌ Invalid YouTube URL")
                return
            
            # Get video info
            video_info = get_video_info(video_id)
            if not video_info['success']:
                send_telegram_message_direct(chat_id, token, "❌ Could not fetch video information")
                return
            
            # Download video
            video_path = download_video_with_progress(
                video_info['download_url'], 
                chat_id, 
                message_id,
                token
            )
            
            if not video_path:
                send_telegram_message_direct(chat_id, token, "❌ Download failed")
                return
            
            # Send uploading status
            send_progress_update(chat_id, message_id, token, 100, "Uploading to Telegram...")
            
            # Send video to Telegram
            send_video_to_telegram(chat_id, video_path, youtube_url, token)
            
            # Clean up
            try:
                os.unlink(video_path)
            except:
                pass
                
            # Delete progress message
            try:
                url = f"https://api.telegram.org/bot{token}/deleteMessage"
                data = {'chat_id': chat_id, 'message_id': message_id}
                requests.post(url, json=data, timeout=10)
            except:
                pass
                
        except Exception as e:
            logger.error(f"Download thread error: {e}")
            send_telegram_message_direct(chat_id, token, f"❌ Error: {str(e)}")
        finally:
            # Clean up progress data
            if chat_id in download_progress:
                del download_progress[chat_id]
    
    thread = threading.Thread(target=download_job)
    thread.daemon = True
    thread.start()

def send_telegram_message_direct(chat_id, token, text, parse_mode='HTML'):
    """Send message directly to Telegram"""
    try:
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        data = {
            'chat_id': chat_id,
            'text': text,
            'parse_mode': parse_mode
        }
        requests.post(url, json=data, timeout=10)
    except Exception as e:
        logger.error(f"Direct message error: {e}")

def send_video_to_telegram(chat_id, video_path, original_url, token):
    """Send video file to Telegram"""
    try:
        url = f"https://api.telegram.org/bot{token}/sendVideo"
        
        with open(video_path, 'rb') as video_file:
            files = {'video': video_file}
            data = {
                'chat_id': chat_id,
                'caption': f"🎥 Downloaded YouTube Video\n\n🔗 Original: {original_url}",
                'parse_mode': 'HTML'
            }
            response = requests.post(url, files=files, data=data, timeout=60)
            
        if response.status_code != 200:
            logger.error(f"Video send error: {response.text}")
            send_telegram_message_direct(chat_id, token, "❌ Failed to upload video")
        else:
            send_telegram_message_direct(chat_id, token, "✅ Video sent successfully!")
            
    except Exception as e:
        logger.error(f"Video upload error: {e}")
        send_telegram_message_direct(chat_id, token, f"❌ Upload error: {str(e)}")

@app.route('/', methods=['GET', 'POST'])
def handle_request():
    try:
        # URL থেকে টোকেন নেওয়া
        token = request.args.get('token')
        
        if not token:
            return jsonify({
                'error': 'Token required',
                'solution': 'Add ?token=YOUR_BOT_TOKEN to URL'
            }), 400

        # GET request হ্যান্ডেল
        if request.method == 'GET':
            return jsonify({
                'status': 'YouTube Downloader Bot is running',
                'endpoint': WORKER_ENDPOINT,
                'token_received': True
            })

        # POST request হ্যান্ডেল
        if request.method == 'POST':
            update = request.get_json()
            
            if not update:
                return jsonify({'error': 'Invalid JSON data'}), 400
            
            logger.info(f"Update received: {update}")
            
            # মেসেজ ডেটা এক্সট্র্যাক্ট
            chat_id = None
            message_text = ''
            message_id = None
            user_info = {}
            
            if 'message' in update:
                chat_id = update['message']['chat']['id']
                message_text = update['message'].get('text', '')
                message_id = update['message'].get('message_id')
                user_info = update['message'].get('from', {})
            else:
                return jsonify({'ok': True})

            if not chat_id:
                return jsonify({'error': 'Chat ID not found'}), 400

            # Main menu keyboard
            main_keyboard = create_keyboard([
                ["📥 Download YouTube Video"],
                ["ℹ️ Help", "❌ Cancel"]
            ])

            # /start কমান্ড হ্যান্ডেল
            if message_text.startswith('/start'):
                welcome_text = """
🎬 <b>YouTube Video Downloader Bot</b>

I can download YouTube videos and send them to you!

📌 <b>How to use:</b>
1. Send any YouTube video URL
2. Or click <b>Download YouTube Video</b>
3. I'll download and send you the video

🔗 <b>Supported formats:</b>
• youtube.com/watch?v=...
• youtu.be/...
• youtube.com/embed/...

⚠️ <b>Note:</b> Maximum video size 50MB
                """
                
                return jsonify(send_telegram_message(
                    chat_id=chat_id,
                    text=welcome_text,
                    reply_markup=main_keyboard
                ))

            # Help command
            elif message_text == 'ℹ️ Help':
                return jsonify(send_telegram_message(
                    chat_id=chat_id,
                    text="Send me a YouTube URL or click 'Download YouTube Video' to start!",
                    reply_markup=main_keyboard
                ))

            # Cancel command
            elif message_text == '❌ Cancel':
                if chat_id in download_progress:
                    del download_progress[chat_id]
                if chat_id in user_sessions:
                    del user_sessions[chat_id]
                    
                return jsonify(send_telegram_message(
                    chat_id=chat_id,
                    text="❌ Operation cancelled.",
                    reply_markup=main_keyboard
                ))

            # Download YouTube Video button
            elif message_text == '📥 Download YouTube Video':
                return jsonify(send_telegram_message(
                    chat_id=chat_id,
                    text="🔗 <b>Send YouTube URL</b>\n\nPlease send me the YouTube video link you want to download.",
                    reply_markup=create_keyboard([["❌ Cancel"]])
                ))

            # YouTube URL processing
            elif extract_youtube_id(message_text):
                youtube_url = message_text
                
                # Send initial processing message
                processing_msg = send_telegram_message(
                    chat_id=chat_id,
                    text="🔍 Processing YouTube video..."
                )
                
                # Send the processing message and get its message ID
                url = f"https://api.telegram.org/bot{token}/sendMessage"
                response = requests.post(url, json=processing_msg, timeout=10)
                
                if response.status_code == 200:
                    processing_msg_id = response.json()['result']['message_id']
                    
                    # Start download in background thread
                    start_download_thread(chat_id, youtube_url, processing_msg_id, token)
                    
                    return jsonify({'ok': True})
                else:
                    return jsonify(send_telegram_message(
                        chat_id=chat_id,
                        text="❌ Failed to start download process"
                    ))

            # Unknown message
            else:
                return jsonify(send_telegram_message(
                    chat_id=chat_id,
                    text="❌ Please send a valid YouTube URL or use the menu buttons.",
                    reply_markup=main_keyboard
                ))

    except Exception as e:
        logger.error(f'Error: {e}')
        return jsonify({'error': 'Processing failed'}), 500

@app.route('/webhook', methods=['POST'])
def set_webhook():
    """টেলিগ্রাম ওয়েবহুক সেটআপ করার জন্য এন্ডপয়েন্ট"""
    try:
        token = request.args.get('token')
        webhook_url = request.args.get('url')
        
        if not token or not webhook_url:
            return jsonify({'error': 'Token and URL required'}), 400
        
        # Set webhook
        set_webhook_url = f"https://api.telegram.org/bot{token}/setWebhook"
        data = {'url': webhook_url}
        response = requests.post(set_webhook_url, data=data, timeout=10)
        
        return jsonify(response.json())
        
    except Exception as e:
        logger.error(f'Webhook error: {e}')
        return jsonify({'error': str(e)}), 500

@app.route('/health', methods=['GET'])
def health_check():
    """হেলথ চেক এন্ডপয়েন্ট"""
    return jsonify({
        'status': 'healthy',
        'service': 'YouTube Telegram Bot',
        'worker_endpoint': WORKER_ENDPOINT
    })

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port, debug=False)