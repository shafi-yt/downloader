from flask import Flask, request, jsonify
import os
import logging
import requests
import re
import tempfile
import threading
import time
import json
import urllib.parse

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

def is_video_url(url):
    """Check if the URL points to a video file"""
    try:
        # Check file extension first (faster)
        video_extensions = ['.mp4', '.mpeg', '.ogg', '.webm', '.avi', '.mov', '.mkv', '.flv', '.wmv', '.m4v', '.3gp']
        parsed_url = urllib.parse.urlparse(url)
        path = parsed_url.path.lower()
        
        for ext in video_extensions:
            if path.endswith(ext):
                return True
        
        # If no clear extension, check content-type
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Range': 'bytes=0-1'  # Just get first bytes to check type
        }
        
        response = requests.get(url, headers=headers, timeout=10, stream=True)
        content_type = response.headers.get('content-type', '').lower()
        
        video_types = ['video/mp4', 'video/mpeg', 'video/ogg', 'video/webm', 'video/avi', 'video/quicktime', 'video/x-msvideo']
        
        # Check if content-type indicates video
        for video_type in video_types:
            if video_type in content_type:
                return True
                
        return False
        
    except Exception as e:
        logger.error(f"Error checking video URL: {e}")
        # If we can't check, assume it might be a video and let download attempt happen
        return True

def get_video_info(url):
    """Get video information from URL"""
    try:
        # If it's a YouTube URL, use the worker endpoint
        youtube_id = extract_youtube_id(url)
        if youtube_id:
            worker_url = f"{WORKER_ENDPOINT}?url=https://youtu.be/{youtube_id}"
            logger.info(f"🔍 Checking YouTube video: {worker_url}")
            
            response = requests.head(worker_url, allow_redirects=True, timeout=30)
            
            logger.info(f"📡 YouTube Response Status: {response.status_code}")
            
            if response.status_code == 200:
                content_length = response.headers.get('content-length', 0)
                content_type = response.headers.get('content-type', 'unknown')
                
                logger.info(f"✅ YouTube video available - Size: {content_length}, Type: {content_type}")
                
                return {
                    'success': True,
                    'download_url': worker_url,
                    'original_url': url,
                    'type': 'youtube',
                    'content_type': content_type,
                    'content_length': content_length,
                    'video_id': youtube_id
                }
            else:
                error_msg = f"YouTube video not available - Status: {response.status_code}"
                logger.error(f"❌ {error_msg}")
                return {'success': False, 'error': error_msg}
        
        # For direct video URLs - USE GET instead of HEAD to avoid 403 issues
        else:
            logger.info(f"🔍 Checking direct video URL: {url}")
            
            # Use GET request with range header to avoid downloading entire file
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
                'Range': 'bytes=0-999'  # Get first 1000 bytes to check
            }
            
            response = requests.get(url, headers=headers, timeout=30, stream=True)
            
            logger.info(f"📡 Direct URL Response Status: {response.status_code}")
            logger.info(f"📡 Content-Type: {response.headers.get('content-type', 'unknown')}")
            
            if response.status_code in [200, 206]:  # 206 is Partial Content
                content_type = response.headers.get('content-type', 'unknown')
                content_length = response.headers.get('content-length', 0)
                
                # For direct URLs, we'll try to download anyway even if content-type check fails
                # Some servers don't provide proper content-type headers
                logger.info(f"✅ Direct video accessible - Size: {content_length}, Type: {content_type}")
                
                return {
                    'success': True,
                    'download_url': url,
                    'original_url': url,
                    'type': 'direct',
                    'content_type': content_type,
                    'content_length': content_length,
                    'requires_streaming': True
                }
            else:
                error_msg = f"Direct video not accessible - Status: {response.status_code}"
                logger.error(f"❌ {error_msg}")
                return {'success': False, 'error': error_msg}
            
    except requests.exceptions.Timeout:
        error_msg = "Request timeout - Endpoint not responding"
        logger.error(f"❌ {error_msg}")
        return {'success': False, 'error': error_msg}
    except requests.exceptions.ConnectionError:
        error_msg = "Connection error - Cannot reach endpoint"
        logger.error(f"❌ {error_msg}")
        return {'success': False, 'error': error_msg}
    except Exception as e:
        error_msg = f"Unexpected error: {str(e)}"
        logger.error(f"❌ {error_msg}")
        return {'success': False, 'error': error_msg}

def download_video_with_progress(download_url, chat_id, message_id, token, is_direct_url=False):
    """Download video with progress tracking"""
    try:
        logger.info(f"📥 Starting download from: {download_url}")
        
        # Update progress
        download_progress[chat_id] = {'status': 'downloading', 'progress': 0}
        
        # Send initial progress
        send_progress_update(chat_id, message_id, token, 0, "Starting download...")
        
        # Set headers for the download
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Accept': 'video/mp4,video/webm,video/ogg,video/*;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'identity',
            'Connection': 'keep-alive',
        }
        
        # For direct URLs, add referer and other headers to avoid restrictions
        if is_direct_url:
            headers.update({
                'Referer': 'https://www.google.com/',
                'Origin': 'https://www.google.com',
                'Sec-Fetch-Dest': 'video',
                'Sec-Fetch-Mode': 'no-cors',
                'Sec-Fetch-Site': 'cross-site',
            })
        
        # Download the video with GET request
        response = requests.get(download_url, headers=headers, stream=True, timeout=60)
        response.raise_for_status()
        
        total_size = int(response.headers.get('content-length', 0))
        logger.info(f"📦 Total size: {total_size} bytes")
        
        # Determine file extension from content-type or URL
        content_type = response.headers.get('content-type', '')
        file_extension = '.mp4'  # default
        
        if 'video/mp4' in content_type:
            file_extension = '.mp4'
        elif 'video/webm' in content_type:
            file_extension = '.webm'
        elif 'video/ogg' in content_type:
            file_extension = '.ogg'
        elif 'video/avi' in content_type:
            file_extension = '.avi'
        elif 'video/quicktime' in content_type:
            file_extension = '.mov'
        else:
            # Try to get extension from URL
            parsed_url = urllib.parse.urlparse(download_url)
            path = parsed_url.path.lower()
            for ext in ['.mp4', '.webm', '.ogg', '.avi', '.mov', '.mkv']:
                if path.endswith(ext):
                    file_extension = ext
                    break
        
        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=file_extension)
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
                'caption': f"🎥 Downloaded Video\n\n🔗 Source: {original_url[:100]}...",
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

def start_download_thread(chat_id, video_url, message_id, token):
    """Start download in separate thread"""
    def download_job():
        try:
            logger.info(f"🎬 Processing video URL: {video_url}")
            
            # Get video info with detailed logging
            video_info = get_video_info(video_url)
            
            if not video_info['success']:
                # Even if get_video_info fails, try direct download for certain URLs
                if 'googlevideo.com' in video_url or 'video' in video_url.lower():
                    logger.info("🔄 Trying direct download despite initial check failure...")
                    video_info = {
                        'success': True,
                        'download_url': video_url,
                        'original_url': video_url,
                        'type': 'direct',
                        'content_type': 'video/mp4',
                        'content_length': 0,
                        'requires_streaming': True
                    }
                else:
                    error_details = f"""
❌ <b>Could not fetch video information</b>

🔍 <b>Error Details:</b>
• <b>URL:</b> <code>{video_url[:100]}...</code>
• <b>Error:</b> {video_info['error']}
• <b>Type:</b> {'YouTube' if extract_youtube_id(video_url) else 'Direct Video'}

📝 <b>Possible Solutions:</b>
• Check if the video is available
• Try a different URL
• The video might be restricted or private
• Make sure the URL points directly to a video file
                    """
                    send_telegram_message_direct(chat_id, token, error_details)
                    return
            
            # Send video info to user
            video_type = "YouTube" if video_info['type'] == 'youtube' else "Direct Video"
            file_size_mb = int(video_info.get('content_length', 0)) / (1024*1024) if video_info.get('content_length', 0) else 0
            
            info_text = f"""
✅ <b>Video Found!</b>

📹 <b>Video Information:</b>
• <b>Type:</b> {video_type}
• <b>Content Type:</b> {video_info.get('content_type', 'Unknown')}
• <b>File Size:</b> {file_size_mb:.2f} MB if available

⏳ <b>Starting download...</b>
            """
            send_telegram_message_direct(chat_id, token, info_text)
            
            # Download video
            is_direct_url = video_info['type'] == 'direct'
            video_path = download_video_with_progress(
                video_info['download_url'], 
                chat_id, 
                message_id,
                token,
                is_direct_url=is_direct_url
            )
            
            if not video_path:
                send_telegram_message_direct(chat_id, token, "❌ Download failed. Please try again later.")
                return
            
            # Send uploading status
            send_progress_update(chat_id, message_id, token, 100, "Uploading to Telegram...")
            
            # Send video to Telegram
            upload_success = send_video_to_telegram(chat_id, video_path, video_url, token)
            
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
• <b>URL:</b> <code>{video_url[:100]}...</code>

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
                'status': 'Universal Video Downloader Bot is running',
                'endpoint': WORKER_ENDPOINT,
                'token_received': True,
                'message': 'Use POST method for Telegram webhook'
            })

        # POST request হ্যান্ডেল
        if request.method == 'POST':
            update = request.get_json()
            
            if not update:
                return jsonify({'error': 'Invalid JSON data'}), 400
            
            logger.info(f"📩 Update received")
            
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
🎬 <b>Universal Video Downloader Bot</b>

I can download videos from various sources and send them to you!

📌 <b>How to use:</b>
1. Send any YouTube URL
2. Send any direct video URL
3. Use /download command with URL

🔗 <b>Supported Sources:</b>
• YouTube (all formats)
• Direct video links (.mp4, .webm, etc.)
• Google Video links
• Any URL that points to a video file

⚡ <b>Commands:</b>
/start - Show this help
/download [URL] - Download video from URL

📝 <b>Examples:</b>
<code>https://youtu.be/FbcHYg4Qx7o</code>
<code>/download https://example.com/video.mp4</code>
<code>/download https://googlevideo.com/...long_url...</code>

⚠️ <b>Note:</b> Some videos might not be available due to restrictions.
                """
                
                return jsonify(send_telegram_message(
                    chat_id=chat_id,
                    text=welcome_text
                ))

            # /download command handler
            elif message_text.startswith('/download'):
                parts = message_text.split(' ', 1)
                if len(parts) < 2:
                    return jsonify(send_telegram_message(
                        chat_id=chat_id,
                        text="❌ <b>Usage:</b> <code>/download URL</code>\n\nExample: <code>/download https://example.com/video.mp4</code>"
                    ))
                
                video_url = parts[1].strip()
                return process_video_download(chat_id, video_url, token)

            # Direct URL processing (without /download command)
            elif extract_youtube_id(message_text) or 'video' in message_text.lower() or any(ext in message_text.lower() for ext in ['.mp4', '.webm', '.avi', '.mov']):
                return process_video_download(chat_id, message_text, token)

            # Unknown message
            else:
                return jsonify(send_telegram_message(
                    chat_id=chat_id,
                    text="❌ Please send a valid video URL or use /download command.\n\nUse /start to see supported formats."
                ))

    except Exception as e:
        logger.error(f'❌ Main handler error: {e}')
        return jsonify({'error': 'Processing failed', 'details': str(e)}), 500

def process_video_download(chat_id, video_url, token):
    """Process video download request"""
    try:
        # Send initial processing message
        processing_msg = send_telegram_message(
            chat_id=chat_id,
            text=f"🔍 Processing video URL...\n\n<code>{video_url[:100]}...</code>"
        )
        
        # Send the processing message and get its message ID
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        response = requests.post(url, json=processing_msg, timeout=10)
        
        if response.status_code == 200:
            processing_msg_id = response.json()['result']['message_id']
            
            # Start download in background thread
            start_download_thread(chat_id, video_url, processing_msg_id, token)
            
            return jsonify({'ok': True})
        else:
            return jsonify(send_telegram_message(
                chat_id=chat_id,
                text="❌ Failed to start download process. Please try again."
            ))
    except Exception as e:
        logger.error(f"Error processing video download: {e}")
        return jsonify(send_telegram_message(
            chat_id=chat_id,
            text=f"❌ Error: {str(e)}"
        ))

@app.route('/debug', methods=['GET'])
def debug_endpoint():
    """ডিবাগিং এন্ডপয়েন্ট"""
    url = request.args.get('url')
    
    if not url:
        return jsonify({'error': 'URL parameter required'})
    
    # Get video info
    video_info = get_video_info(url)
    
    return jsonify({
        'input_url': url,
        'is_youtube': bool(extract_youtube_id(url)),
        'is_video_url': is_video_url(url),
        'video_info': video_info
    })

@app.route('/health', methods=['GET'])
def health_check():
    """হেলথ চেক এন্ডপয়েন্ট"""
    return jsonify({
        'status': 'healthy',
        'service': 'Universal Video Downloader Bot',
        'worker_endpoint': WORKER_ENDPOINT,
        'timestamp': time.time()
    })

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
        data = {'url': f"{webhook_url}?token={token}"}
        response = requests.post(set_webhook_url, data=data, timeout=10)
        
        return jsonify(response.json())
        
    except Exception as e:
        logger.error(f'Webhook error: {e}')
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port, debug=False)