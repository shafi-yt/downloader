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

def is_streaming_url(url):
    """Check if URL is a streaming URL"""
    streaming_indicators = [
        'videoplayback',
        'googlevideo.com',
        'stream',
        'm3u8',
        'mpd',
        'segment',
        'chunk'
    ]
    
    url_lower = url.lower()
    return any(indicator in url_lower for indicator in streaming_indicators)

def get_streaming_headers():
    """Get headers for streaming requests"""
    return {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': '*/*',
        'Accept-Language': 'en-US,en;q=0.9',
        'Accept-Encoding': 'identity',
        'Connection': 'keep-alive',
        'Referer': 'https://www.youtube.com/',
        'Origin': 'https://www.youtube.com',
        'Sec-Fetch-Dest': 'video',
        'Sec-Fetch-Mode': 'no-cors',
        'Sec-Fetch-Site': 'cross-site',
        'Range': 'bytes=0-',
        'DNT': '1'
    }

def test_streaming_url(url):
    """Test if streaming URL is accessible"""
    try:
        headers = get_streaming_headers()
        
        # Test with HEAD request first
        response = session.head(url, headers=headers, timeout=30, allow_redirects=True)
        
        if response.status_code in [200, 206]:
            content_type = response.headers.get('content-type', '')
            content_length = response.headers.get('content-length')
            
            logger.info(f"✅ Streaming URL accessible - Status: {response.status_code}, Type: {content_type}, Size: {content_length}")
            
            return {
                'success': True,
                'url': url,
                'content_type': content_type,
                'content_length': content_length,
                'headers': dict(response.headers)
            }
        else:
            # Try with GET request for partial content
            headers['Range'] = 'bytes=0-999'
            response = session.get(url, headers=headers, timeout=30, stream=True)
            
            if response.status_code in [200, 206]:
                return {
                    'success': True,
                    'url': url,
                    'content_type': response.headers.get('content-type', ''),
                    'content_length': response.headers.get('content-length'),
                    'headers': dict(response.headers)
                }
            else:
                return {
                    'success': False,
                    'error': f'HTTP {response.status_code}',
                    'details': 'Streaming server rejected the request'
                }
                
    except requests.exceptions.Timeout:
        return {
            'success': False,
            'error': 'Connection timeout',
            'details': 'Streaming server is not responding'
        }
    except requests.exceptions.ConnectionError:
        return {
            'success': False,
            'error': 'Connection failed',
            'details': 'Cannot connect to streaming server'
        }
    except Exception as e:
        return {
            'success': False,
            'error': str(e),
            'details': 'Unexpected error occurred'
        }

def download_streaming_video(stream_url, chat_id, message_id, token):
    """Download streaming video with progress tracking"""
    try:
        logger.info(f"📥 Starting streaming download from: {stream_url}")
        
        download_progress[chat_id] = {'status': 'downloading', 'progress': 0}
        send_progress_update(chat_id, message_id, token, 0, "Connecting to streaming server...")
        
        headers = get_streaming_headers()
        
        # Remove range header for full download
        if 'Range' in headers:
            del headers['Range']
        
        # Set longer timeout for streaming
        timeout = 180  # 3 minutes
        
        logger.info(f"⏳ Starting streaming download (timeout: {timeout}s)")
        
        response = session.get(stream_url, headers=headers, stream=True, timeout=timeout)
        response.raise_for_status()
        
        total_size = int(response.headers.get('content-length', 0))
        logger.info(f"📦 Streaming content size: {total_size} bytes")
        
        if total_size == 0:
            # For streaming without known size, we'll download until completion
            logger.info("⚠️ Unknown content size - streaming until completion")
            total_size = 100  # Placeholder for progress calculation
        
        # Create temp file
        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.mp4')
        downloaded_size = 0
        chunk_count = 0
        start_time = time.time()
        
        send_progress_update(chat_id, message_id, token, 0, "Downloading streaming content...")
        
        for chunk in response.iter_content(chunk_size=8192 * 8):  # 64KB chunks for streaming
            if chunk:
                temp_file.write(chunk)
                downloaded_size += len(chunk)
                chunk_count += 1
                
                # Update progress
                if total_size > 100:  # Only show progress if we know the size
                    progress = min(99, (downloaded_size / total_size) * 100)
                    current_progress = int(progress)
                    
                    # Update every 2MB or 5% progress
                    if chunk_count % 50 == 0 or current_progress % 5 == 0:
                        download_speed = downloaded_size / (time.time() - start_time) if (time.time() - start_time) > 0 else 0
                        speed_text = f"({download_speed/1024/1024:.1f} MB/s)" if download_speed > 0 else ""
                        
                        download_progress[chat_id] = {
                            'status': 'downloading', 
                            'progress': current_progress,
                            'downloaded_mb': downloaded_size / (1024*1024),
                            'total_mb': total_size / (1024*1024) if total_size > 100 else 0
                        }
                        
                        if total_size > 100:
                            status_text = f"Streaming: {downloaded_size/(1024*1024):.1f}MB / {total_size/(1024*1024):.1f}MB {speed_text}"
                        else:
                            status_text = f"Streaming: {downloaded_size/(1024*1024):.1f}MB {speed_text}"
                        
                        send_progress_update(chat_id, message_id, token, current_progress, status_text)
        
        temp_file.close()
        
        # Verify download
        file_size = os.path.getsize(temp_file.name)
        logger.info(f"💾 Streaming download completed: {file_size} bytes")
        
        if file_size == 0:
            raise Exception("Streaming download resulted in empty file")
        
        download_progress[chat_id] = {'status': 'completed', 'progress': 100}
        return temp_file.name
        
    except requests.exceptions.Timeout:
        error_msg = "Streaming download timeout - Server took too long"
        logger.error(f"❌ {error_msg}")
        download_progress[chat_id] = {'status': 'error', 'error': error_msg}
        send_progress_update(chat_id, message_id, token, 0, f"❌ {error_msg}")
        return None
    except requests.exceptions.ChunkedEncodingError:
        error_msg = "Streaming connection interrupted"
        logger.error(f"❌ {error_msg}")
        download_progress[chat_id] = {'status': 'error', 'error': error_msg}
        send_progress_update(chat_id, message_id, token, 0, f"❌ {error_msg}")
        return None
    except Exception as e:
        logger.error(f"❌ Streaming download error: {e}")
        download_progress[chat_id] = {'status': 'error', 'error': str(e)}
        send_progress_update(chat_id, message_id, token, 0, f"❌ Streaming Error")
        return None

def handle_streaming_url(url):
    """Handle streaming URL processing"""
    try:
        logger.info(f"🎬 Processing streaming URL: {url}")
        
        # Test the streaming URL
        test_result = test_streaming_url(url)
        
        if test_result['success']:
            return {
                'success': True,
                'download_url': url,
                'original_url': url,
                'type': 'streaming',
                'content_type': test_result['content_type'],
                'content_length': test_result['content_length'],
                'is_streaming': True
            }
        else:
            # Try alternative approach - direct download without testing
            logger.info("🔄 Trying direct streaming approach...")
            return {
                'success': True,
                'download_url': url,
                'original_url': url,
                'type': 'streaming',
                'content_type': 'video/mp4',
                'content_length': 0,
                'is_streaming': True,
                'direct_stream': True
            }
            
    except Exception as e:
        logger.error(f"❌ Streaming URL handling error: {e}")
        return {
            'success': False,
            'error': f"Streaming processing failed: {str(e)}",
            'details': 'Cannot process this streaming URL'
        }

def get_video_info(url):
    """Get video information from URL"""
    try:
        # Check if it's a streaming URL
        if is_streaming_url(url):
            return handle_streaming_url(url)
        
        # For regular URLs, try direct access
        headers = get_streaming_headers()
        
        try:
            response = session.head(url, headers=headers, timeout=30, allow_redirects=True)
            
            if response.status_code == 200:
                content_type = response.headers.get('content-type', '')
                content_length = response.headers.get('content-length', 0)
                
                if 'video' in content_type:
                    return {
                        'success': True,
                        'download_url': url,
                        'original_url': url,
                        'type': 'direct',
                        'content_type': content_type,
                        'content_length': content_length
                    }
                    
        except Exception as e:
            logger.warning(f"⚠️ Direct check failed: {e}")
        
        # If all else fails, treat as streaming
        return handle_streaming_url(url)
            
    except Exception as e:
        error_msg = f"URL processing error: {str(e)}"
        logger.error(f"❌ {error_msg}")
        return {'success': False, 'error': error_msg}

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
        
        timeout = 300
        
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
            return send_as_document(chat_id, video_path, original_url, token)
            
    except Exception as e:
        logger.error(f"❌ Video upload error: {e}")
        return send_as_document(chat_id, video_path, original_url, token)

def send_as_document(chat_id, file_path, original_url, token):
    """Send file as document if video upload fails"""
    try:
        url = f"https://api.telegram.org/bot{token}/sendDocument"
        
        with open(file_path, 'rb') as file:
            files = {'document': file}
            data = {
                'chat_id': chat_id,
                'caption': f"📁 Video File\n\n🔗 Source: {original_url[:100]}...",
                'parse_mode': 'HTML'
            }
            response = session.post(url, files=files, data=data, timeout=300)
            
        return response.status_code == 200
        
    except Exception as e:
        logger.error(f"❌ Document upload failed: {e}")
        return False

def start_download_thread(chat_id, video_url, message_id, token):
    """Start download in separate thread"""
    def download_job():
        try:
            logger.info(f"🎬 Processing URL: {video_url}")
            
            send_telegram_message_direct(chat_id, token, "🔍 Analyzing URL...")
            
            # Get video info
            video_info = get_video_info(video_url)
            
            if not video_info['success']:
                error_details = f"""
❌ <b>Could not process URL</b>

🔍 <b>Details:</b>
• <b>URL:</b> <code>{video_url[:100]}...</code>
• <b>Error:</b> {video_info['error']}

📝 <b>Trying alternative method...</b>
                """
                send_telegram_message_direct(chat_id, token, error_details)
                
                # Try direct streaming as fallback
                video_info = {
                    'success': True,
                    'download_url': video_url,
                    'original_url': video_url,
                    'type': 'streaming',
                    'content_type': 'video/mp4',
                    'content_length': 0,
                    'is_streaming': True,
                    'direct_stream': True
                }
            
            # Send video info
            video_type = "Streaming" if video_info.get('is_streaming') else "Direct"
            file_size_mb = int(video_info.get('content_length', 0)) / (1024*1024) if video_info.get('content_length', 0) else "Unknown"
            
            info_text = f"""
✅ <b>URL Accepted</b>

📹 <b>Information:</b>
• <b>Type:</b> {video_type}
• <b>Content Type:</b> {video_info.get('content_type', 'Unknown')}
• <b>File Size:</b> {file_size_mb if file_size_mb != 'Unknown' else 'Unknown'} MB

⏳ <b>Starting download...</b>
            """
            
            send_telegram_message_direct(chat_id, token, info_text)
            
            # Download video
            video_path = download_streaming_video(
                video_info['download_url'], 
                chat_id, 
                message_id,
                token
            )
            
            if not video_path:
                send_telegram_message_direct(chat_id, token, 
                    "❌ Download failed. Possible reasons:\n• URL expired\n• Server restrictions\n• Network issues\n\nPlease try a fresh URL.")
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
                send_telegram_message_direct(chat_id, token, "❌ <b>Upload failed. File might be too large or corrupted.</b>")
                
        except Exception as e:
            logger.error(f"❌ Download thread error: {e}")
            error_text = f"""
❌ <b>Processing Failed</b>

🔍 <b>Error:</b> {str(e)}

📝 <b>Please try:</b>
• Fresh URL
• Different video
• Shorter content
            """
            send_telegram_message_direct(chat_id, token, error_text)
        finally:
            if chat_id in download_progress:
                del download_progress[chat_id]
    
    thread = threading.Thread(target=download_job)
    thread.daemon = True
    thread.start()

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
                'status': 'Streaming Video Downloader Bot is running',
                'features': 'Supports streaming URLs, direct videos, and Google Video links',
                'token_received': True
            })

        if request.method == 'POST':
            update = request.get_json()
            
            if not update:
                return jsonify({'error': 'Invalid JSON data'}), 400
            
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
🎬 <b>Streaming Video Downloader Bot</b>

I can download videos from streaming URLs and direct links!

📌 <b>How to use:</b>
Just send me any video URL

🔗 <b>Supported:</b>
• Google Video links
• Streaming URLs
• Direct video links
• YouTube URLs

⚡ <b>Commands:</b>
/start - Show this help
/download [URL] - Download from URL

📝 <b>Examples:</b>
<code>https://googlevideo.com/videoplayback?...</code>
<code>/download https://example.com/video.mp4</code>

⚠️ <b>Note:</b> Some URLs may expire quickly.
                """
                
                return jsonify(send_telegram_message(chat_id, welcome_text))

            elif message_text.startswith('/download'):
                parts = message_text.split(' ', 1)
                if len(parts) < 2:
                    return jsonify(send_telegram_message(
                        chat_id,
                        "❌ <b>Usage:</b> <code>/download URL</code>"
                    ))
                
                video_url = parts[1].strip()
                return process_video_download(chat_id, video_url, token)

            elif message_text.strip().startswith('http'):
                return process_video_download(chat_id, message_text, token)

            else:
                return jsonify(send_telegram_message(
                    chat_id,
                    "❌ Please send a valid URL starting with http:// or https://"
                ))

    except Exception as e:
        logger.error(f'❌ Main handler error: {e}')
        return jsonify({'error': 'Processing failed', 'details': str(e)}), 500

def process_video_download(chat_id, video_url, token):
    """Process video download request"""
    try:
        processing_msg = send_telegram_message(
            chat_id,
            f"🔍 Processing URL...\n\n<code>{video_url[:100]}...</code>"
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
                "❌ Failed to start download process."
            ))
    except Exception as e:
        logger.error(f"Error processing download: {e}")
        return jsonify(send_telegram_message(
            chat_id,
            f"❌ Error: {str(e)}"
        ))

@app.route('/health', methods=['GET'])
def health_check():
    return jsonify({
        'status': 'healthy',
        'service': 'Streaming Video Downloader',
        'timestamp': time.time()
    })

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port, debug=False)