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
import random

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

# Session for persistent connections
session = requests.Session()

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
        
        # If URL contains video keywords, assume it's video
        video_keywords = ['videoplayback', 'video', 'mp4', 'stream']
        if any(keyword in url.lower() for keyword in video_keywords):
            return True
            
        return False
        
    except Exception as e:
        logger.error(f"Error checking video URL: {e}")
        return True

def get_direct_video_url(url):
    """Get direct video URL using the worker endpoint for any URL"""
    try:
        # Use worker endpoint to get direct video URL
        worker_url = f"{WORKER_ENDPOINT}?url={urllib.parse.quote(url)}"
        logger.info(f"🔍 Getting direct URL via worker: {worker_url}")
        
        # Follow redirects to get final URL
        response = session.head(worker_url, allow_redirects=True, timeout=30)
        
        if response.status_code == 200:
            final_url = response.url
            logger.info(f"✅ Worker returned URL: {final_url}")
            
            # Check if it's a video
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
                'Range': 'bytes=0-999'
            }
            
            video_response = session.get(final_url, headers=headers, stream=True, timeout=30)
            content_type = video_response.headers.get('content-type', '')
            
            if 'video' in content_type or any(ext in final_url for ext in ['.mp4', '.webm']):
                return {
                    'success': True,
                    'download_url': final_url,
                    'original_url': url,
                    'type': 'direct',
                    'content_type': content_type,
                    'content_length': video_response.headers.get('content-length', 0)
                }
        
        return {'success': False, 'error': 'Could not get direct video URL'}
        
    except Exception as e:
        logger.error(f"Error getting direct URL: {e}")
        return {'success': False, 'error': str(e)}

def get_video_info(url):
    """Get video information from URL"""
    try:
        # If it's a YouTube URL, use the worker endpoint
        youtube_id = extract_youtube_id(url)
        if youtube_id:
            worker_url = f"{WORKER_ENDPOINT}?url=https://youtu.be/{youtube_id}"
            logger.info(f"🔍 Checking YouTube video: {worker_url}")
            
            response = session.head(worker_url, allow_redirects=True, timeout=30)
            
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
        
        # For Google Video URLs, use worker to get direct link
        elif 'googlevideo.com' in url:
            logger.info(f"🔄 Processing Google Video URL via worker...")
            return get_direct_video_url(url)
        
        # For other direct video URLs
        else:
            logger.info(f"🔍 Checking direct video URL: {url}")
            
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
                'Range': 'bytes=0-1999',
                'Accept': 'video/mp4,video/*;q=0.9,*/*;q=0.8',
                'Referer': 'https://www.youtube.com/'
            }
            
            try:
                response = session.get(url, headers=headers, timeout=45, stream=True)
                
                logger.info(f"📡 Direct URL Response Status: {response.status_code}")
                
                if response.status_code in [200, 206]:
                    content_type = response.headers.get('content-type', 'unknown')
                    content_length = response.headers.get('content-length', 0)
                    
                    logger.info(f"✅ Direct video accessible - Size: {content_length}, Type: {content_type}")
                    
                    return {
                        'success': True,
                        'download_url': url,
                        'original_url': url,
                        'type': 'direct',
                        'content_type': content_type,
                        'content_length': content_length
                    }
                else:
                    # Try using worker as fallback
                    logger.info("🔄 Trying worker as fallback...")
                    return get_direct_video_url(url)
                    
            except requests.exceptions.Timeout:
                logger.warning("⚠️ Direct check timeout, trying worker...")
                return get_direct_video_url(url)
            except Exception as e:
                logger.warning(f"⚠️ Direct check failed: {e}, trying worker...")
                return get_direct_video_url(url)
            
    except Exception as e:
        error_msg = f"Unexpected error: {str(e)}"
        logger.error(f"❌ {error_msg}")
        return {'success': False, 'error': error_msg}

def download_video_with_progress(download_url, chat_id, message_id, token, video_info):
    """Download video with progress tracking"""
    try:
        logger.info(f"📥 Starting download from: {download_url}")
        
        download_progress[chat_id] = {'status': 'downloading', 'progress': 0}
        send_progress_update(chat_id, message_id, token, 0, "Connecting to video server...")
        
        # Enhanced headers for video download
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'video/mp4,video/webm,video/ogg,video/*;q=0.9,application/octet-stream;q=0.8,*/*;q=0.7',
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept-Encoding': 'identity',
            'Connection': 'keep-alive',
            'Referer': 'https://www.youtube.com/',
            'Origin': 'https://www.youtube.com',
            'Sec-Fetch-Dest': 'video',
            'Sec-Fetch-Mode': 'no-cors',
            'Sec-Fetch-Site': 'cross-site',
            'DNT': '1',
            'Upgrade-Insecure-Requests': '1'
        }
        
        # Use session for persistent connection
        timeout = 120
        logger.info(f"⏳ Setting download timeout: {timeout} seconds")
        
        response = session.get(download_url, headers=headers, stream=True, timeout=timeout)
        response.raise_for_status()
        
        total_size = int(response.headers.get('content-length', 0))
        logger.info(f"📦 Total size: {total_size} bytes")
        
        if total_size == 0:
            raise Exception("Content length is 0 - possibly blocked")
        
        # Determine file extension
        content_type = response.headers.get('content-type', '')
        file_extension = '.mp4'
        
        if 'video/mp4' in content_type:
            file_extension = '.mp4'
        elif 'video/webm' in content_type:
            file_extension = '.webm'
        elif 'video/ogg' in content_type:
            file_extension = '.ogg'
        
        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=file_extension)
        downloaded_size = 0
        last_progress_update = 0
        chunk_count = 0
        
        send_progress_update(chat_id, message_id, token, 0, "Downloading video...")
        
        start_time = time.time()
        
        for chunk in response.iter_content(chunk_size=8192 * 4):  # 32KB chunks
            if chunk:
                temp_file.write(chunk)
                downloaded_size += len(chunk)
                chunk_count += 1
                
                # Update progress every 2 seconds or 5% progress
                current_time = time.time()
                if total_size > 0:
                    progress = (downloaded_size / total_size) * 100
                    current_progress = int(progress)
                    
                    if (current_progress >= last_progress_update + 5 or 
                        current_time - start_time >= 2 or 
                        current_progress == 100):
                        
                        download_speed = downloaded_size / (current_time - start_time) if current_time > start_time else 0
                        speed_text = f"({download_speed/1024/1024:.1f} MB/s)" if download_speed > 0 else ""
                        
                        download_progress[chat_id] = {
                            'status': 'downloading', 
                            'progress': current_progress,
                            'downloaded_mb': downloaded_size / (1024*1024),
                            'total_mb': total_size / (1024*1024)
                        }
                        
                        send_progress_update(chat_id, message_id, token, current_progress, 
                                           f"Downloading: {downloaded_size/(1024*1024):.1f}MB / {total_size/(1024*1024):.1f}MB {speed_text}")
                        last_progress_update = current_progress
                        start_time = current_time
        
        temp_file.close()
        
        # Verify download
        file_size = os.path.getsize(temp_file.name)
        logger.info(f"💾 File downloaded: {file_size} bytes")
        
        if file_size == 0:
            raise Exception("Downloaded file is empty")
        
        if total_size > 0 and abs(file_size - total_size) > 10000:  # Allow 10KB difference
            logger.warning(f"⚠️ File size mismatch: expected {total_size}, got {file_size}")
        
        download_progress[chat_id] = {'status': 'completed', 'progress': 100}
        return temp_file.name
        
    except requests.exceptions.Timeout:
        error_msg = "Download timeout - Server took too long to respond"
        logger.error(f"❌ {error_msg}")
        download_progress[chat_id] = {'status': 'error', 'error': error_msg}
        send_progress_update(chat_id, message_id, token, 0, f"❌ {error_msg}")
        return None
    except requests.exceptions.HTTPError as e:
        error_msg = f"HTTP Error {e.response.status_code if e.response else 'Unknown'}"
        logger.error(f"❌ {error_msg}")
        download_progress[chat_id] = {'status': 'error', 'error': error_msg}
        send_progress_update(chat_id, message_id, token, 0, f"❌ {error_msg}")
        return None
    except Exception as e:
        logger.error(f"❌ Download error: {e}")
        download_progress[chat_id] = {'status': 'error', 'error': str(e)}
        send_progress_update(chat_id, message_id, token, 0, f"❌ Download Error")
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
        session.post(url, json=data, timeout=10)
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
        response = session.post(url, json=data, timeout=10)
        return response.json()
    except Exception as e:
        logger.error(f"Direct message error: {e}")
        return None

def send_video_to_telegram(chat_id, video_path, original_url, token):
    """Send video file to Telegram"""
    try:
        url = f"https://api.telegram.org/bot{token}/sendVideo"
        
        file_size = os.path.getsize(video_path)
        logger.info(f"📤 Uploading video: {file_size} bytes")
        
        timeout = 300  # 5 minutes for large files
        
        with open(video_path, 'rb') as video_file:
            files = {'video': video_file}
            data = {
                'chat_id': chat_id,
                'caption': f"🎥 Downloaded Video\n\n🔗 Source: {original_url[:100]}...",
                'parse_mode': 'HTML',
                'supports_streaming': True
            }
            response = session.post(url, files=files, data=data, timeout=timeout)
            
        logger.info(f"📤 Upload response: {response.status_code}")
        
        if response.status_code == 200:
            return True
        else:
            logger.error(f"❌ Video upload failed: {response.text}")
            # Try sending as document if video fails
            return send_as_document(chat_id, video_path, original_url, token)
            
    except Exception as e:
        logger.error(f"❌ Video upload error: {e}")
        # Try sending as document as fallback
        return send_as_document(chat_id, video_path, original_url, token)

def send_as_document(chat_id, file_path, original_url, token):
    """Send file as document if video upload fails"""
    try:
        url = f"https://api.telegram.org/bot{token}/sendDocument"
        
        with open(file_path, 'rb') as file:
            files = {'document': file}
            data = {
                'chat_id': chat_id,
                'caption': f"📁 Video File (Sent as Document)\n\n🔗 Source: {original_url[:100]}...",
                'parse_mode': 'HTML'
            }
            response = session.post(url, files=files, data=data, timeout=300)
            
        return response.status_code == 200
        
    except Exception as e:
        logger.error(f"❌ Document upload also failed: {e}")
        return False

def start_download_thread(chat_id, video_url, message_id, token):
    """Start download in separate thread"""
    def download_job():
        try:
            logger.info(f"🎬 Processing video URL: {video_url}")
            
            send_telegram_message_direct(chat_id, token, "🔍 Analyzing video URL...")
            
            # Get video info
            video_info = get_video_info(video_url)
            
            if not video_info['success']:
                error_details = f"""
❌ <b>Could not process video URL</b>

🔍 <b>Error Details:</b>
• <b>URL:</b> <code>{video_url[:100]}...</code>
• <b>Error:</b> {video_info['error']}

📝 <b>Possible Solutions:</b>
• Check if the video is available
• Try a different URL
• The video might be restricted
                """
                send_telegram_message_direct(chat_id, token, error_details)
                return
            
            # Send video info
            video_type = "YouTube" if video_info['type'] == 'youtube' else "Direct Video"
            file_size_mb = int(video_info.get('content_length', 0)) / (1024*1024) if video_info.get('content_length', 0) else 0
            
            info_text = f"""
✅ <b>Video Found!</b>

📹 <b>Video Information:</b>
• <b>Type:</b> {video_type}
• <b>Content Type:</b> {video_info.get('content_type', 'Unknown')}
• <b>File Size:</b> {file_size_mb:.2f} MB

⏳ <b>Starting download...</b>
            """
            
            send_telegram_message_direct(chat_id, token, info_text)
            
            # Download video
            video_path = download_video_with_progress(
                video_info['download_url'], 
                chat_id, 
                message_id,
                token,
                video_info
            )
            
            if not video_path:
                send_telegram_message_direct(chat_id, token, 
                    "❌ Download failed. This could be due to:\n• Video restrictions\n• Network issues\n• Server timeout\n\nPlease try again or use a different URL.")
                return
            
            # Upload to Telegram
            send_progress_update(chat_id, message_id, token, 100, "Uploading to Telegram...")
            
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
                session.post(url, json=data, timeout=10)
            except:
                pass
            
            if upload_success:
                send_telegram_message_direct(chat_id, token, "✅ <b>Video successfully sent!</b>")
            else:
                send_telegram_message_direct(chat_id, token, "❌ <b>Upload failed. Video might be too large.</b>")
                
        except Exception as e:
            logger.error(f"❌ Download thread error: {e}")
            error_text = f"""
❌ <b>Download Failed</b>

🔍 <b>Error:</b> {str(e)}

📝 <b>Please try:</b>
• Another video URL
• Shorter video
• Different format
            """
            send_telegram_message_direct(chat_id, token, error_text)
        finally:
            if chat_id in download_progress:
                del download_progress[chat_id]
    
    thread = threading.Thread(target=download_job)
    thread.daemon = True
    thread.start()

# ... (Flask routes remain the same as previous version)

@app.route('/', methods=['GET', 'POST'])
def handle_request():
    try:
        token = request.args.get('token')
        
        if not token:
            return jsonify({
                'error': 'Token required',
                'solution': 'Add ?token=YOUR_BOT_TOKEN to URL'
            }), 400

        if request.method == 'GET':
            return jsonify({
                'status': 'Universal Video Downloader Bot is running',
                'endpoint': WORKER_ENDPOINT,
                'token_received': True,
                'message': 'Use POST method for Telegram webhook'
            })

        if request.method == 'POST':
            update = request.get_json()
            
            if not update:
                return jsonify({'error': 'Invalid JSON data'}), 400
            
            logger.info(f"📩 Update received")
            
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

            if message_text.startswith('/start'):
                welcome_text = """
🎬 <b>Universal Video Downloader Bot</b>

I can download videos from various sources and send them to you!

📌 <b>How to use:</b>
Just send me any video URL or use /download command

🔗 <b>Supported Sources:</b>
• YouTube videos
• Direct video links
• Google Video links
• Streaming videos

⚡ <b>Commands:</b>
/start - Show this help
/download [URL] - Download video from URL

📝 <b>Examples:</b>
<code>https://youtu.be/FbcHYg4Qx7o</code>
<code>/download https://example.com/video.mp4</code>

⚠️ <b>Note:</b> Some videos might have restrictions.
                """
                
                return jsonify(send_telegram_message(chat_id, welcome_text))

            elif message_text.startswith('/download'):
                parts = message_text.split(' ', 1)
                if len(parts) < 2:
                    return jsonify(send_telegram_message(
                        chat_id,
                        "❌ <b>Usage:</b> <code>/download URL</code>\n\nExample: <code>/download https://example.com/video.mp4</code>"
                    ))
                
                video_url = parts[1].strip()
                return process_video_download(chat_id, video_url, token)

            elif (extract_youtube_id(message_text) or 
                  'video' in message_text.lower() or 
                  any(ext in message_text.lower() for ext in ['.mp4', '.webm', '.avi', '.mov']) or 
                  'googlevideo.com' in message_text):
                return process_video_download(chat_id, message_text, token)

            else:
                return jsonify(send_telegram_message(
                    chat_id,
                    "❌ Please send a valid video URL or use /download command.\n\nUse /start to see supported formats."
                ))

    except Exception as e:
        logger.error(f'❌ Main handler error: {e}')
        return jsonify({'error': 'Processing failed', 'details': str(e)}), 500

def process_video_download(chat_id, video_url, token):
    """Process video download request"""
    try:
        processing_msg = send_telegram_message(
            chat_id,
            f"🔍 Processing video URL...\n\n<code>{video_url[:100]}...</code>"
        )
        
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        response = session.post(url, json=processing_msg, timeout=10)
        
        if response.status_code == 200:
            processing_msg_id = response.json()['result']['message_id']
            start_download_thread(chat_id, video_url, processing_msg_id, token)
            return jsonify({'ok': True})
        else:
            return jsonify(send_telegram_message(
                chat_id,
                "❌ Failed to start download process. Please try again."
            ))
    except Exception as e:
        logger.error(f"Error processing video download: {e}")
        return jsonify(send_telegram_message(
            chat_id,
            f"❌ Error: {str(e)}"
        ))

@app.route('/debug', methods=['GET'])
def debug_endpoint():
    url = request.args.get('url')
    
    if not url:
        return jsonify({'error': 'URL parameter required'})
    
    video_info = get_video_info(url)
    
    return jsonify({
        'input_url': url,
        'is_youtube': bool(extract_youtube_id(url)),
        'video_info': video_info
    })

@app.route('/health', methods=['GET'])
def health_check():
    return jsonify({
        'status': 'healthy',
        'service': 'Universal Video Downloader Bot',
        'timestamp': time.time()
    })

@app.route('/webhook', methods=['POST'])
def set_webhook():
    try:
        token = request.args.get('token')
        webhook_url = request.args.get('url')
        
        if not token or not webhook_url:
            return jsonify({'error': 'Token and URL required'}), 400
        
        set_webhook_url = f"https://api.telegram.org/bot{token}/setWebhook"
        data = {'url': f"{webhook_url}?token={token}"}
        response = session.post(set_webhook_url, data=data, timeout=10)
        
        return jsonify(response.json())
        
    except Exception as e:
        logger.error(f'Webhook error: {e}')
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port, debug=False)