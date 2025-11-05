from flask import Flask, request, jsonify
import os
import logging
import requests
import re
import tempfile
import threading
import time
import json

# লগিং কনফিগারেশন
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Worker endpoint from your provided link
WORKER_ENDPOINT = "https://utubdbot.shafitest.workers.dev/"

# Store download progress
download_progress = {}

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
        # Construct the worker URL - FIXED: removed .mp4 extension from YouTube URL
        worker_url = f"{WORKER_ENDPOINT}?url=https://youtu.be/{video_id}"
        
        logger.info(f"🔍 Checking video info for: {worker_url}")
        
        # Get video info with detailed debugging
        response = requests.head(worker_url, allow_redirects=True, timeout=30)
        
        logger.info(f"📡 Response Status: {response.status_code}")
        logger.info(f"📡 Response Headers: {dict(response.headers)}")
        
        if response.status_code == 200:
            content_length = response.headers.get('content-length', 0)
            content_type = response.headers.get('content-type', 'unknown')
            
            logger.info(f"✅ Video available - Size: {content_length}, Type: {content_type}")
            
            return {
                'success': True,
                'download_url': worker_url,
                'video_id': video_id,
                'content_type': content_type,
                'content_length': content_length
            }
        else:
            error_msg = f"Video not available - Status: {response.status_code}"
            logger.error(f"❌ {error_msg}")
            return {'success': False, 'error': error_msg}
            
    except requests.exceptions.Timeout:
        error_msg = "Request timeout - Worker endpoint not responding"
        logger.error(f"❌ {error_msg}")
        return {'success': False, 'error': error_msg}
    except requests.exceptions.ConnectionError:
        error_msg = "Connection error - Cannot reach worker endpoint"
        logger.error(f"❌ {error_msg}")
        return {'success': False, 'error': error_msg}
    except Exception as e:
        error_msg = f"Unexpected error: {str(e)}"
        logger.error(f"❌ {error_msg}")
        return {'success': False, 'error': error_msg}

def download_video_with_progress(download_url, chat_id, message_id, token):
    """Download video with progress tracking"""
    try:
        logger.info(f"📥 Starting download from: {download_url}")
        
        # Update progress
        download_progress[chat_id] = {'status': 'downloading', 'progress': 0}
        
        # Send initial progress
        send_progress_update(chat_id, message_id, token, 0, "Starting download...")
        
        # Download the video with GET request
        response = requests.get(download_url, stream=True, timeout=60)
        response.raise_for_status()
        
        total_size = int(response.headers.get('content-length', 0))
        logger.info(f"📦 Total size: {total_size} bytes")
        
        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.mp4')
        downloaded_size = 0
        
        for chunk in response.iter_content(chunk_size=8192):
            if chunk:
                temp_file.write(chunk)
                downloaded_size += len(chunk)
                
                # Update progress
                if total_size > 0:
                    progress = (downloaded_size / total_size) * 100
                    current_progress = int(progress)
                    
                    # Update progress every 10% or when complete
                    if current_progress % 10 == 0 or current_progress == 100:
                        download_progress[chat_id] = {
                            'status': 'downloading', 
                            'progress': current_progress
                        }
                        send_progress_update(chat_id, message_id, token, current_progress, "Downloading...")
        
        temp_file.close()
        
        # Check if file was actually downloaded
        file_size = os.path.getsize(temp_file.name)
        logger.info(f"💾 File downloaded: {file_size} bytes")
        
        if file_size == 0:
            raise Exception("Downloaded file is empty")
        
        download_progress[chat_id] = {'status': 'completed', 'progress': 100}
        
        return temp_file.name
        
    except Exception as e:
        logger.error(f"❌ Download error: {e}")
        download_progress[chat_id] = {'status': 'error', 'error': str(e)}
        send_progress_update(chat_id, message_id, token, 0, f"Download Error: {str(e)}")
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

def send_telegram_message_direct(chat_id, token, text, parse_mode='HTML'):
    """Send message directly to Telegram"""
    try:
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        data = {
            'chat_id': chat_id,
            'text': text,
            'parse_mode': parse_mode
        }
        response = requests.post(url, json=data, timeout=10)
        return response.json()
    except Exception as e:
        logger.error(f"Direct message error: {e}")
        return None

def send_video_to_telegram(chat_id, video_path, original_url, token):
    """Send video file to Telegram"""
    try:
        url = f"https://api.telegram.org/bot{token}/sendVideo"
        
        # Get file size for logging
        file_size = os.path.getsize(video_path)
        logger.info(f"📤 Uploading video: {file_size} bytes")
        
        with open(video_path, 'rb') as video_file:
            files = {'video': video_file}
            data = {
                'chat_id': chat_id,
                'caption': f"🎥 Downloaded YouTube Video\n\n🔗 Original: {original_url}",
                'parse_mode': 'HTML'
            }
            response = requests.post(url, files=files, data=data, timeout=120)
            
        logger.info(f"📤 Upload response: {response.status_code}")
        
        if response.status_code == 200:
            return True
        else:
            logger.error(f"❌ Video upload failed: {response.text}")
            return False
            
    except Exception as e:
        logger.error(f"❌ Video upload error: {e}")
        return False

def start_download_thread(chat_id, youtube_url, message_id, token):
    """Start download in separate thread"""
    def download_job():
        try:
            # Extract video ID
            video_id = extract_youtube_id(youtube_url)
            if not video_id:
                send_telegram_message_direct(chat_id, token, "❌ Invalid YouTube URL. Please check the URL format.")
                return
            
            logger.info(f"🎬 Processing YouTube video: {video_id}")
            
            # Get video info with detailed logging
            video_info = get_video_info(video_id)
            
            if not video_info['success']:
                error_details = f"""
❌ <b>Could not fetch video information</b>

🔍 <b>Error Details:</b>
• <b>Video ID:</b> <code>{video_id}</code>
• <b>Error:</b> {video_info['error']}
• <b>Worker Endpoint:</b> {WORKER_ENDPOINT}

📝 <b>Possible Solutions:</b>
• Check if the video is available on YouTube
• Try a different YouTube URL
• The video might be restricted or private
                """
                send_telegram_message_direct(chat_id, token, error_details)
                return
            
            # Send video info to user
            info_text = f"""
✅ <b>Video Found!</b>

📹 <b>Video Information:</b>
• <b>Video ID:</b> <code>{video_info['video_id']}</code>
• <b>Content Type:</b> {video_info['content_type']}
• <b>File Size:</b> {int(video_info['content_length']) / (1024*1024):.2f} MB

⏳ <b>Starting download...</b>
            """
            send_telegram_message_direct(chat_id, token, info_text)
            
            # Download video
            video_path = download_video_with_progress(
                video_info['download_url'], 
                chat_id, 
                message_id,
                token
            )
            
            if not video_path:
                send_telegram_message_direct(chat_id, token, "❌ Download failed. Please try again later.")
                return
            
            # Send uploading status
            send_progress_update(chat_id, message_id, token, 100, "Uploading to Telegram...")
            
            # Send video to Telegram
            upload_success = send_video_to_telegram(chat_id, video_path, youtube_url, token)
            
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
            
            if upload_success:
                send_telegram_message_direct(chat_id, token, "✅ <b>Video successfully sent!</b>")
            else:
                send_telegram_message_direct(chat_id, token, "❌ <b>Failed to upload video to Telegram.</b>")
                
        except Exception as e:
            logger.error(f"❌ Download thread error: {e}")
            error_text = f"""
❌ <b>Download Failed</b>

🔍 <b>Error Details:</b>
• <b>Error Type:</b> {type(e).__name__}
• <b>Error Message:</b> {str(e)}

📝 <b>Please try again later or contact support.</b>
            """
            send_telegram_message_direct(chat_id, token, error_text)
        finally:
            # Clean up progress data
            if chat_id in download_progress:
                del download_progress[chat_id]
    
    thread = threading.Thread(target=download_job)
    thread.daemon = True
    thread.start()

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
                'token_received': True,
                'message': 'Use POST method for Telegram webhook'
            })

        # POST request হ্যান্ডেল
        if request.method == 'POST':
            update = request.get_json()
            
            if not update:
                return jsonify({'error': 'Invalid JSON data'}), 400
            
            logger.info(f"📩 Update received: {json.dumps(update, indent=2)}")
            
            # মেসেজ ডেটা এক্সট্র্যাক্ট
            chat_id = None
            message_text = ''
            message_id = None
            
            if 'message' in update:
                chat_id = update['message']['chat']['id']
                message_text = update['message'].get('text', '')
                message_id = update['message'].get('message_id')
            else:
                return jsonify({'ok': True})

            if not chat_id:
                return jsonify({'error': 'Chat ID not found'}), 400

            # /start কমান্ড হ্যান্ডেল
            if message_text.startswith('/start'):
                welcome_text = """
🎬 <b>YouTube Video Downloader Bot</b>

I can download YouTube videos and send them to you!

📌 <b>How to use:</b>
Just send me any YouTube video URL and I'll download it for you.

🔗 <b>Supported URL formats:</b>
• https://youtu.be/FbcHYg4Qx7o
• https://www.youtube.com/watch?v=FbcHYg4Qx7o
• https://youtube.com/embed/FbcHYg4Qx7o

⚠️ <b>Note:</b> Some videos might not be available due to restrictions.

🔍 <b>Debug Info:</b>
• Worker Endpoint: <code>{}</code>
• Bot Status: ✅ Running

📝 <b>Just send a YouTube URL to get started!</b>
                """.format(WORKER_ENDPOINT)
                
                return jsonify(send_telegram_message(
                    chat_id=chat_id,
                    text=welcome_text
                ))

            # YouTube URL processing
            youtube_id = extract_youtube_id(message_text)
            if youtube_id:
                youtube_url = message_text
                
                # Send initial processing message
                processing_msg = send_telegram_message(
                    chat_id=chat_id,
                    text="🔍 Processing YouTube video...\n\n📝 Checking video availability..."
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
                        text="❌ Failed to start download process. Please try again."
                    ))

            # Unknown message
            else:
                return jsonify(send_telegram_message(
                    chat_id=chat_id,
                    text="❌ Please send a valid YouTube URL.\n\nUse /start to see supported formats."
                ))

    except Exception as e:
        logger.error(f'❌ Main handler error: {e}')
        return jsonify({'error': 'Processing failed', 'details': str(e)}), 500

@app.route('/debug', methods=['GET'])
def debug_endpoint():
    """ডিবাগিং এন্ডপয়েন্ট"""
    token = request.args.get('token')
    url = request.args.get('url')
    
    if not url:
        return jsonify({'error': 'URL parameter required'})
    
    youtube_id = extract_youtube_id(url)
    if not youtube_id:
        return jsonify({'error': 'Invalid YouTube URL'})
    
    # Get video info
    video_info = get_video_info(youtube_id)
    
    return jsonify({
        'youtube_url': url,
        'youtube_id': youtube_id,
        'worker_url': f"{WORKER_ENDPOINT}?url=https://youtu.be/{youtube_id}",
        'video_info': video_info
    })

@app.route('/health', methods=['GET'])
def health_check():
    """হেলথ চেক এন্ডপয়েন্ট"""
    return jsonify({
        'status': 'healthy',
        'service': 'YouTube Telegram Bot',
        'worker_endpoint': WORKER_ENDPOINT,
        'timestamp': time.time()
    })

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port, debug=False)