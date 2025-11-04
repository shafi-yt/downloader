from flask import Flask, request, jsonify
import os
import logging
import yt_dlp
import requests
from urllib.parse import urlparse
import tempfile
import shutil
import json

# লগিং কনফিগারেশন
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# টেম্পোরারি ডিরেক্টরি সেটআপ
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB

def send_telegram_message(chat_id, text, parse_mode='Markdown', reply_to_message_id=None):
    """
    Telegram-এ মেসেজ সেন্ড করার জন্য সহায়ক ফাংশন
    """
    data = {
        'method': 'sendMessage',
        'chat_id': chat_id,
        'text': text,
        'parse_mode': parse_mode
    }
    if reply_to_message_id:
        data['reply_to_message_id'] = reply_to_message_id
    return data

def is_valid_youtube_url(url):
    """
    ইউটিউব URL ভ্যালিডেশন - উন্নত সংস্করণ
    """
    if not url:
        return False
    
    # সাধারণ টেক্সট ফিল্টার
    if ' ' in url and not url.startswith(('http://', 'https://')):
        return False
    
    parsed = urlparse(url)
    
    # ডোমেইন চেক
    valid_domains = ['youtube.com', 'www.youtube.com', 'youtu.be', 'm.youtube.com']
    domain_valid = any(domain in parsed.netloc for domain in valid_domains)
    
    # পাথ চেক (youtu.be এর জন্য)
    path_valid = False
    if parsed.netloc == 'youtu.be' and len(parsed.path) > 1:
        path_valid = True
    elif 'youtube.com' in parsed.netloc and ('/watch' in parsed.path or '/shorts' in parsed.path):
        path_valid = True
    
    return domain_valid and path_valid

def extract_video_id(url):
    """
    URL থেকে ভিডিও আইডি এক্সট্র্যাক্ট করা
    """
    try:
        parsed = urlparse(url)
        if parsed.netloc == 'youtu.be':
            return parsed.path[1:]
        elif 'youtube.com' in parsed.netloc:
            if 'v=' in parsed.query:
                return parsed.query.split('v=')[1].split('&')[0]
            elif '/shorts/' in parsed.path:
                return parsed.path.split('/shorts/')[1]
    except Exception as e:
        logger.error(f"Video ID extraction error: {e}")
    return None

def get_video_info(url):
    """
    yt-dlp ব্যবহার করে ভিডিও ইনফো পাওয়া - উন্নত সংস্করণ
    """
    ydl_opts = {
        'quiet': True,
        'no_warnings': False,
    }
    
    try:
        logger.info(f"Extracting info for URL: {url}")
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            
            if info:
                logger.info(f"Successfully extracted info: {info.get('title', 'No title')}")
                return info
            else:
                logger.error("No info returned from yt-dlp")
                return None
                
    except yt_dlp.utils.DownloadError as e:
        logger.error(f"DownloadError in get_video_info: {e}")
        return None
    except yt_dlp.utils.ExtractorError as e:
        logger.error(f"ExtractorError in get_video_info: {e}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error in get_video_info: {e}")
        return None

def create_video_info_message(video_info, download_success=False):
    """
    ভিডিও ইনফো থেকে ডিটেইল্ড মেসেজ তৈরি করা
    """
    title = video_info.get('title', 'Unknown Title')
    duration = video_info.get('duration', 0)
    uploader = video_info.get('uploader', 'Unknown Uploader')
    view_count = video_info.get('view_count', 0)
    like_count = video_info.get('like_count', 0)
    upload_date = video_info.get('upload_date', '')
    description = video_info.get('description', '')[:200] + "..." if len(video_info.get('description', '')) > 200 else video_info.get('description', '')
    
    # ফাইল সাইজ তথ্য
    filesize = video_info.get('filesize') or video_info.get('filesize_approx', 0)
    
    if download_success:
        status_icon = "✅"
        status_text = "ভিডিও সফলভাবে ডাউনলোড হয়েছে!"
    else:
        status_icon = "📊"
        status_text = "ভিডিও ডাউনলোড করা যায়নি, কিন্তু ইনফো পাওয়া গেছে:"
    
    message = f"""
{status_icon} *ভিডিও তথ্য*

📝 *টাইটেল:* {title}
📺 *চ্যানেল:* {uploader}
⏱️ *সময়:* {format_duration(duration)}
👀 *ভিউ:* {view_count:,}
👍 *লাইক:* {like_count:, if like_count else 'N/A'}
📅 *আপলোড তারিখ:* {format_upload_date(upload_date)}
📦 *আনুমানিক সাইজ:* {format_file_size(filesize) if filesize else 'অজানা'}

📋 *বর্ণনা:* 
{description if description else 'কোন বর্ণনা নেই'}

{status_text}
"""
    
    if not download_success and filesize > MAX_FILE_SIZE:
        message += f"\n❌ *সীমাবদ্ধতা:* ভিডিওটি খুব বড় ({format_file_size(filesize)})। সর্বোচ্চ 50MB সাইজের ভিডিও ডাউনলোড করা যাবে।"
    
    return message

def format_upload_date(upload_date):
    """
    আপলোড তারিখ ফরম্যাট করা
    """
    if not upload_date:
        return "অজানা"
    
    try:
        # YYYYMMDD ফরম্যাট
        if len(upload_date) == 8:
            year = upload_date[:4]
            month = upload_date[4:6]
            day = upload_date[6:8]
            return f"{day}-{month}-{year}"
    except:
        pass
    
    return upload_date

def download_video(url):
    """
    ভিডিও ডাউনলোড করা - Render-এর জন্য অপ্টিমাইজড
    """
    temp_dir = tempfile.mkdtemp()
    
    ydl_opts = {
        'outtmpl': os.path.join(temp_dir, '%(title).100s.%(ext)s'),
        'format': 'best[filesize<50M]',
        'quiet': True,
        'no_warnings': False,
        'writethumbnail': True,
        'embedthumbnail': False,
        'noplaylist': True,
    }
    
    try:
        logger.info(f"Starting download for: {url}")
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            
            video_file = None
            thumb_file = None
            
            # ডাউনলোড করা ফাইল খুঁজে বের করা
            for file in os.listdir(temp_dir):
                file_path = os.path.join(temp_dir, file)
                if os.path.isfile(file_path):
                    if file.endswith(('.mp4', '.webm', '.mkv', '.avi', '.mov')):
                        video_file = file_path
                        logger.info(f"Found video file: {video_file}")
                    elif file.endswith(('.jpg', '.webp', '.png', '.jpeg')):
                        thumb_file = file_path
                        logger.info(f"Found thumbnail file: {thumb_file}")
            
            if not video_file:
                logger.error("No video file found after download")
                return None, None, None
            
            return video_file, thumb_file, info
        
    except Exception as e:
        logger.error(f"Download error: {e}")
        # ক্লিনআপ
        shutil.rmtree(temp_dir, ignore_errors=True)
        return None, None, None

def format_file_size(size_bytes):
    """
    ফাইল সাইজ ফরম্যাট করা
    """
    if not size_bytes:
        return "অজানা"
    
    if size_bytes >= 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.1f} MB"
    elif size_bytes >= 1024:
        return f"{size_bytes / 1024:.1f} KB"
    else:
        return f"{size_bytes} bytes"

def format_duration(seconds):
    """
    ডুরেশন ফরম্যাট করা
    """
    if not seconds:
        return "অজানা"
    
    if seconds < 60:
        return f"{seconds} সেকেন্ড"
    elif seconds < 3600:
        minutes = seconds // 60
        return f"{minutes} মিনিট {seconds % 60} সেকেন্ড"
    else:
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        return f"{hours} ঘন্টা {minutes} মিনিট"

@app.route('/', methods=['GET', 'POST'])
def handle_request():
    try:
        # URL থেকে টোকেন নেওয়া
        token = request.args.get('token')
        
        if not token:
            return jsonify({
                'error': 'Token required',
                'solution': 'Add ?token=YOUR_BOT_TOKEN to URL',
                'example': 'https://your-app.onrender.com/?token=123456:ABC-DEF'
            }), 400

        # GET request হ্যান্ডেল
        if request.method == 'GET':
            return jsonify({
                'status': 'YouTube Downloader Bot is running on Render',
                'token_received': True if token else False,
                'max_file_size': '50MB',
                'platform': 'Render',
                'version': '2.0'
            })

        # POST request হ্যান্ডেল (Telegram Webhook)
        if request.method == 'POST':
            update = request.get_json()
            
            if not update:
                return jsonify({'error': 'Invalid JSON data'}), 400
            
            logger.info(f"Update received")
            
            # মেসেজ ডেটা এক্সট্র্যাক্ট
            chat_id = None
            message_text = ''
            message_id = None
            
            if 'message' in update:
                chat_id = update['message']['chat']['id']
                message_text = update['message'].get('text', '').strip()
                message_id = update['message'].get('message_id')
            elif 'callback_query' in update:
                return jsonify({'ok': True})
            else:
                return jsonify({'ok': True})

            if not chat_id:
                return jsonify({'error': 'Chat ID not found'}), 400

            # /start কমান্ড হ্যান্ডেল
            if message_text.startswith('/start'):
                welcome_text = """
🎬 *YouTube Video Downloader*

এই বটের মাধ্যমে আপনি YouTube ভিডিও ডাউনলোড করতে পারবেন।

📌 *ব্যবহার 방법:*
1. YouTube ভিডিওর লিংক পাঠান
2. বট স্বয়ংক্রিয়ভাবে ভিডিও ডাউনলোড করবে
3. ভিডিওটি আপনাকে ফেরত দেওয়া হবে

⚡ *সীমাবদ্ধতা:*
• সর্বোচ্চ ফাইল সাইজ: 50MB
• শুধুমাত্র YouTube লিংক সাপোর্টেড

📊 *ভিডিও না পেলে:* বিস্তারিত ইনফো দেখাবে

🚀 *শুরু করতে একটি YouTube লিংক পাঠান*
                """
                
                return jsonify(send_telegram_message(
                    chat_id=chat_id,
                    text=welcome_text
                ))

            # /help কমান্ড
            elif message_text.startswith('/help'):
                help_text = """
📌 *YouTube Video Downloader - সাহায্য*

🤖 *কমান্ডস:*
/start - বট শুরু করুন
/help - সাহায্য দেখুন
/test - টেস্ট লিংক
/info - শুধু ভিডিও ইনফো দেখাবে

📥 *ডাউনলোড করতে:*
শুধুমাত্র একটি YouTube ভিডিও লিংক পাঠান

📊 *শুধু ইনফো দেখাতে:*
/info কমান্ড দিয়ে তারপর লিংক পাঠান

🌐 *সাপোর্টেড লিংক ফরম্যাট:*
• https://youtube.com/watch?v=...
• https://youtu.be/...
• https://m.youtube.com/watch?v=...
• YouTube Shorts লিংক

⚡ *সীমাবদ্ধতা:*
• সর্বোচ্চ 50MB সাইজ
• শুধুমাত্র ভিডিও ডাউনলোড

🔧 *হোস্টেড: Render*
                """
                
                return jsonify(send_telegram_message(
                    chat_id=chat_id,
                    text=help_text
                ))

            # /test কমান্ড - টেস্ট লিংক
            elif message_text.startswith('/test'):
                test_links = """
🧪 *টেস্ট লিংক:*

🎵 *ছোট ভিডিও:*
https://youtu.be/dQw4w9WgXcQ

🎬 *সাধারণ ভিডিও:*
https://www.youtube.com/watch?v=jNQXAC9IVRw

📱 *Shorts:*
https://www.youtube.com/shorts/abcdefg

এই লিংকগুলো টেস্ট করতে পারেন!
                """
                
                return jsonify(send_telegram_message(
                    chat_id=chat_id,
                    text=test_links
                ))

            # /info কমান্ড - শুধু ইনফো দেখাবে
            elif message_text.startswith('/info'):
                info_text = """
📊 *শুধু ভিডিও ইনফো মোড*

এখন একটি YouTube লিংক পাঠান, আমি শুধু ভিডিওর তথ্য দেখাব (ডাউনলোড করব না)।

ভিডিওর টাইটেল, চ্যানেল, সময়, ভিউ, লাইক এবং বর্ণনা দেখাবে।
                """
                
                return jsonify(send_telegram_message(
                    chat_id=chat_id,
                    text=info_text
                ))

            # YouTube URL চেক করা (সাধারণ ডাউনলোড)
            elif is_valid_youtube_url(message_text):
                return handle_youtube_download(chat_id, message_text, message_id, download=True)

            # /info এর পর লিংক (শুধু ইনফো)
            elif message_text.startswith('http') and any(cmd in message_text for cmd in ['youtube', 'youtu.be']):
                # যদি আগের মেসেজ /info ছিল
                return handle_youtube_download(chat_id, message_text, message_id, download=False)

            # অন্য মেসেজের জন্য
            else:
                help_text = """
❌ *ইনভ্যালিড ইনপুট*

📌 সঠিকভাবে ব্যবহার করতে:
1. শুধুমাত্র YouTube ভিডিও লিংক পাঠান
2. অথবা নিচের কমান্ড ব্যবহার করুন:

🤖 *কমান্ডস:*
/start - বট শুরু করুন
/help - সাহায্য দেখুন
/test - টেস্ট লিংক
/info - শুধু ভিডিও ইনফো দেখাবে

🌐 *উদাহরণ লিংক:*
https://youtube.com/watch?v=VIDEO_ID
https://youtu.be/VIDEO_ID
https://youtube.com/shorts/VIDEO_ID
                """
                
                return jsonify(send_telegram_message(
                    chat_id=chat_id,
                    text=help_text,
                    reply_to_message_id=message_id
                ))

    except Exception as e:
        logger.error(f'Error: {str(e)}')
        error_msg = f"""
🚨 *সিস্টেম এরর*

❌ এরর: {str(e)}

💡 *সমাধান:*
• কিছুক্ষণ পর আবার চেষ্টা করুন
• /test কমান্ড দিয়ে টেস্ট করুন
• অন্য লিংক ট্রাই করুন
        """
        return jsonify(send_telegram_message(
            chat_id=chat_id,
            text=error_msg
        ))

def handle_youtube_download(chat_id, url, message_id, download=True):
    """
    YouTube ডাউনলোড বা ইনফো হ্যান্ডেল করা
    """
    try:
        logger.info(f"{'Downloading' if download else 'Getting info for'}: {url}")
        
        # প্রথমে ভিডিও ইনফো চেক
        processing_msg = send_telegram_message(
            chat_id=chat_id,
            text="🔍 ভিডিও তথ্য চেক করা হচ্ছে..." if download else "🔍 ভিডিও তথ্য সংগ্রহ করা হচ্ছে...",
            reply_to_message_id=message_id
        )
        
        video_info = get_video_info(url)
        
        if not video_info:
            error_msg = """
❌ *ভিডিও তথ্য পাওয়া যায়নি*

🚨 *সম্ভাব্য কারণ:*
• ভিডিওটি প্রাইভেট বা ডিলিটেড
• নেটওয়ার্ক সমস্যা
• ভিডিও সাইজ খুব বড় (50MB+)
• ভিডিও রেস্ট্রিক্টেড

💡 *সমাধান:*
• ভিডিওটি পাবলিক কিনা চেক করুন
• অন্য লিংক ট্রাই করুন
• /test কমান্ড দিয়ে টেস্ট করুন
            """
            return jsonify(send_telegram_message(
                chat_id=chat_id,
                text=error_msg,
                reply_to_message_id=message_id
            ))
        
        # যদি শুধু ইনফো চায়
        if not download:
            info_message = create_video_info_message(video_info, download_success=False)
            return jsonify(send_telegram_message(
                chat_id=chat_id,
                text=info_message,
                reply_to_message_id=message_id
            ))
        
        # ভিডিও টাইটেল সহ কনফার্মেশন
        filesize = video_info.get('filesize') or video_info.get('filesize_approx', 0)
        
        if filesize > MAX_FILE_SIZE:
            # ভিডিও বড় হলে শুধু ইনফো দেখাবে
            info_message = create_video_info_message(video_info, download_success=False)
            info_message += "\n\n⚠️ *ভিডিওটি খুব বড় হওয়ায় ডাউনলোড করা যায়নি, কিন্তু উপরের তথ্য দেখানো হলো*"
            return jsonify(send_telegram_message(
                chat_id=chat_id,
                text=info_message,
                reply_to_message_id=message_id
            ))
        
        confirm_text = f"""
🎬 *ভিডিও পাওয়া গেছে!*

📝 *টাইটেল:* {video_info.get('title', 'Unknown Title')}
⏱️ *সময়:* {format_duration(video_info.get('duration', 0))}
📦 *আনুমানিক সাইজ:* {format_file_size(filesize) if filesize else 'অজানা'}

⏳ *ডাউনলোড শুরু হচ্ছে...*
        """
        
        # কনফার্মেশন মেসেজ
        jsonify(send_telegram_message(
            chat_id=chat_id,
            text=confirm_text,
            reply_to_message_id=message_id
        ))
        
        # ভিডিও ডাউনলোড
        video_file, thumb_file, download_info = download_video(url)
        
        if not video_file or not os.path.exists(video_file):
            # ডাউনলোড失败 হলে শুধু ইনফো দেখাবে
            info_message = create_video_info_message(video_info, download_success=False)
            info_message += "\n\n❌ *ভিডিও ডাউনলোড করা যায়নি, কিন্তু উপরের তথ্য দেখানো হলো*"
            
            # ক্লিনআপ
            if video_file:
                shutil.rmtree(os.path.dirname(video_file), ignore_errors=True)
            
            return jsonify(send_telegram_message(
                chat_id=chat_id,
                text=info_message,
                reply_to_message_id=message_id
            ))
        
        # ফাইল সাইজ চেক
        file_size = os.path.getsize(video_file)
        if file_size > MAX_FILE_SIZE:
            # ফাইল বড় হলে শুধু ইনফো দেখাবে
            info_message = create_video_info_message(video_info, download_success=False)
            info_message += f"\n\n❌ *ভিডিওটি খুব বড় ({format_file_size(file_size)}) হওয়ায় ডাউনলোড করা যায়নি*"
            
            # ক্লিনআপ
            shutil.rmtree(os.path.dirname(video_file), ignore_errors=True)
            return jsonify(send_telegram_message(
                chat_id=chat_id,
                text=info_message,
                reply_to_message_id=message_id
            ))
        
        # সফল ডাউনলোড হলে ইনফো সহ মেসেজ
        success_message = create_video_info_message(download_info, download_success=True)
        
        # ক্লিনআপ
        shutil.rmtree(os.path.dirname(video_file), ignore_errors=True)
        
        return jsonify(send_telegram_message(
            chat_id=chat_id,
            text=success_message,
            reply_to_message_id=message_id
        ))
        
    except Exception as e:
        logger.error(f"Error in handle_youtube_download: {e}")
        
        # এরর হলেও ভিডিও ইনফো দেখানোর চেষ্টা করবে
        try:
            video_info = get_video_info(url)
            if video_info:
                error_info_message = create_video_info_message(video_info, download_success=False)
                error_info_message += f"\n\n❌ *ডাউনলোড এরর:* {str(e)}"
                return jsonify(send_telegram_message(
                    chat_id=chat_id,
                    text=error_info_message,
                    reply_to_message_id=message_id
                ))
        except:
            pass
        
        error_msg = f"""
🚨 *ডাউনলোড এরর*

❌ এরর: {str(e)}

💡 *সমাধান:*
• কিছুক্ষণ পর আবার চেষ্টা করুন
• অন্য লিংক ট্রাই করুন
• /info কমান্ড দিয়ে শুধু ইনফো দেখুন
        """
        return jsonify(send_telegram_message(
            chat_id=chat_id,
            text=error_msg,
            reply_to_message_id=message_id
        ))

@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint for Render"""
    return jsonify({
        'status': 'healthy',
        'service': 'YouTube Downloader Bot',
        'platform': 'Render',
        'version': '2.0'
    })

@app.route('/test-url', methods=['GET'])
def test_url():
    """URL টেস্ট করার এন্ডপয়েন্ট"""
    url = request.args.get('url')
    if not url:
        return jsonify({'error': 'URL parameter required'}), 400
    
    result = {
        'url': url,
        'is_valid_youtube': is_valid_youtube_url(url),
        'video_id': extract_video_id(url)
    }
    
    if result['is_valid_youtube']:
        info = get_video_info(url)
        if info:
            result['video_info'] = {
                'title': info.get('title'),
                'duration': info.get('duration'),
                'uploader': info.get('uploader'),
                'view_count': info.get('view_count'),
                'filesize': info.get('filesize') or info.get('filesize_approx')
            }
        else:
            result['error'] = 'Could not fetch video info'
    
    return jsonify(result)

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port, debug=False)from flask import Flask, request, jsonify
import os
import logging
import yt_dlp
import requests
from urllib.parse import urlparse
import tempfile
import shutil
import json

# লগিং কনফিগারেশন
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# টেম্পোরারি ডিরেক্টরি সেটআপ
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB

def send_telegram_message(chat_id, text, parse_mode='Markdown', reply_to_message_id=None):
    """
    Telegram-এ মেসেজ সেন্ড করার জন্য সহায়ক ফাংশন
    """
    data = {
        'method': 'sendMessage',
        'chat_id': chat_id,
        'text': text,
        'parse_mode': parse_mode
    }
    if reply_to_message_id:
        data['reply_to_message_id'] = reply_to_message_id
    return data

def is_valid_youtube_url(url):
    """
    ইউটিউব URL ভ্যালিডেশন - উন্নত সংস্করণ
    """
    if not url:
        return False
    
    # সাধারণ টেক্সট ফিল্টার
    if ' ' in url and not url.startswith(('http://', 'https://')):
        return False
    
    parsed = urlparse(url)
    
    # ডোমেইন চেক
    valid_domains = ['youtube.com', 'www.youtube.com', 'youtu.be', 'm.youtube.com']
    domain_valid = any(domain in parsed.netloc for domain in valid_domains)
    
    # পাথ চেক (youtu.be এর জন্য)
    path_valid = False
    if parsed.netloc == 'youtu.be' and len(parsed.path) > 1:
        path_valid = True
    elif 'youtube.com' in parsed.netloc and ('/watch' in parsed.path or '/shorts' in parsed.path):
        path_valid = True
    
    return domain_valid and path_valid

def extract_video_id(url):
    """
    URL থেকে ভিডিও আইডি এক্সট্র্যাক্ট করা
    """
    try:
        parsed = urlparse(url)
        if parsed.netloc == 'youtu.be':
            return parsed.path[1:]
        elif 'youtube.com' in parsed.netloc:
            if 'v=' in parsed.query:
                return parsed.query.split('v=')[1].split('&')[0]
            elif '/shorts/' in parsed.path:
                return parsed.path.split('/shorts/')[1]
    except Exception as e:
        logger.error(f"Video ID extraction error: {e}")
    return None

def get_video_info(url):
    """
    yt-dlp ব্যবহার করে ভিডিও ইনফো পাওয়া - উন্নত সংস্করণ
    """
    ydl_opts = {
        'quiet': True,
        'no_warnings': False,
    }
    
    try:
        logger.info(f"Extracting info for URL: {url}")
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            
            if info:
                logger.info(f"Successfully extracted info: {info.get('title', 'No title')}")
                return info
            else:
                logger.error("No info returned from yt-dlp")
                return None
                
    except yt_dlp.utils.DownloadError as e:
        logger.error(f"DownloadError in get_video_info: {e}")
        return None
    except yt_dlp.utils.ExtractorError as e:
        logger.error(f"ExtractorError in get_video_info: {e}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error in get_video_info: {e}")
        return None

def create_video_info_message(video_info, download_success=False):
    """
    ভিডিও ইনফো থেকে ডিটেইল্ড মেসেজ তৈরি করা
    """
    title = video_info.get('title', 'Unknown Title')
    duration = video_info.get('duration', 0)
    uploader = video_info.get('uploader', 'Unknown Uploader')
    view_count = video_info.get('view_count', 0)
    like_count = video_info.get('like_count', 0)
    upload_date = video_info.get('upload_date', '')
    description = video_info.get('description', '')[:200] + "..." if len(video_info.get('description', '')) > 200 else video_info.get('description', '')
    
    # ফাইল সাইজ তথ্য
    filesize = video_info.get('filesize') or video_info.get('filesize_approx', 0)
    
    if download_success:
        status_icon = "✅"
        status_text = "ভিডিও সফলভাবে ডাউনলোড হয়েছে!"
    else:
        status_icon = "📊"
        status_text = "ভিডিও ডাউনলোড করা যায়নি, কিন্তু ইনফো পাওয়া গেছে:"
    
    message = f"""
{status_icon} *ভিডিও তথ্য*

📝 *টাইটেল:* {title}
📺 *চ্যানেল:* {uploader}
⏱️ *সময়:* {format_duration(duration)}
👀 *ভিউ:* {view_count:,}
👍 *লাইক:* {like_count:, if like_count else 'N/A'}
📅 *আপলোড তারিখ:* {format_upload_date(upload_date)}
📦 *আনুমানিক সাইজ:* {format_file_size(filesize) if filesize else 'অজানা'}

📋 *বর্ণনা:* 
{description if description else 'কোন বর্ণনা নেই'}

{status_text}
"""
    
    if not download_success and filesize > MAX_FILE_SIZE:
        message += f"\n❌ *সীমাবদ্ধতা:* ভিডিওটি খুব বড় ({format_file_size(filesize)})। সর্বোচ্চ 50MB সাইজের ভিডিও ডাউনলোড করা যাবে।"
    
    return message

def format_upload_date(upload_date):
    """
    আপলোড তারিখ ফরম্যাট করা
    """
    if not upload_date:
        return "অজানা"
    
    try:
        # YYYYMMDD ফরম্যাট
        if len(upload_date) == 8:
            year = upload_date[:4]
            month = upload_date[4:6]
            day = upload_date[6:8]
            return f"{day}-{month}-{year}"
    except:
        pass
    
    return upload_date

def download_video(url):
    """
    ভিডিও ডাউনলোড করা - Render-এর জন্য অপ্টিমাইজড
    """
    temp_dir = tempfile.mkdtemp()
    
    ydl_opts = {
        'outtmpl': os.path.join(temp_dir, '%(title).100s.%(ext)s'),
        'format': 'best[filesize<50M]',
        'quiet': True,
        'no_warnings': False,
        'writethumbnail': True,
        'embedthumbnail': False,
        'noplaylist': True,
    }
    
    try:
        logger.info(f"Starting download for: {url}")
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            
            video_file = None
            thumb_file = None
            
            # ডাউনলোড করা ফাইল খুঁজে বের করা
            for file in os.listdir(temp_dir):
                file_path = os.path.join(temp_dir, file)
                if os.path.isfile(file_path):
                    if file.endswith(('.mp4', '.webm', '.mkv', '.avi', '.mov')):
                        video_file = file_path
                        logger.info(f"Found video file: {video_file}")
                    elif file.endswith(('.jpg', '.webp', '.png', '.jpeg')):
                        thumb_file = file_path
                        logger.info(f"Found thumbnail file: {thumb_file}")
            
            if not video_file:
                logger.error("No video file found after download")
                return None, None, None
            
            return video_file, thumb_file, info
        
    except Exception as e:
        logger.error(f"Download error: {e}")
        # ক্লিনআপ
        shutil.rmtree(temp_dir, ignore_errors=True)
        return None, None, None

def format_file_size(size_bytes):
    """
    ফাইল সাইজ ফরম্যাট করা
    """
    if not size_bytes:
        return "অজানা"
    
    if size_bytes >= 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.1f} MB"
    elif size_bytes >= 1024:
        return f"{size_bytes / 1024:.1f} KB"
    else:
        return f"{size_bytes} bytes"

def format_duration(seconds):
    """
    ডুরেশন ফরম্যাট করা
    """
    if not seconds:
        return "অজানা"
    
    if seconds < 60:
        return f"{seconds} সেকেন্ড"
    elif seconds < 3600:
        minutes = seconds // 60
        return f"{minutes} মিনিট {seconds % 60} সেকেন্ড"
    else:
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        return f"{hours} ঘন্টা {minutes} মিনিট"

@app.route('/', methods=['GET', 'POST'])
def handle_request():
    try:
        # URL থেকে টোকেন নেওয়া
        token = request.args.get('token')
        
        if not token:
            return jsonify({
                'error': 'Token required',
                'solution': 'Add ?token=YOUR_BOT_TOKEN to URL',
                'example': 'https://your-app.onrender.com/?token=123456:ABC-DEF'
            }), 400

        # GET request হ্যান্ডেল
        if request.method == 'GET':
            return jsonify({
                'status': 'YouTube Downloader Bot is running on Render',
                'token_received': True if token else False,
                'max_file_size': '50MB',
                'platform': 'Render',
                'version': '2.0'
            })

        # POST request হ্যান্ডেল (Telegram Webhook)
        if request.method == 'POST':
            update = request.get_json()
            
            if not update:
                return jsonify({'error': 'Invalid JSON data'}), 400
            
            logger.info(f"Update received")
            
            # মেসেজ ডেটা এক্সট্র্যাক্ট
            chat_id = None
            message_text = ''
            message_id = None
            
            if 'message' in update:
                chat_id = update['message']['chat']['id']
                message_text = update['message'].get('text', '').strip()
                message_id = update['message'].get('message_id')
            elif 'callback_query' in update:
                return jsonify({'ok': True})
            else:
                return jsonify({'ok': True})

            if not chat_id:
                return jsonify({'error': 'Chat ID not found'}), 400

            # /start কমান্ড হ্যান্ডেল
            if message_text.startswith('/start'):
                welcome_text = """
🎬 *YouTube Video Downloader*

এই বটের মাধ্যমে আপনি YouTube ভিডিও ডাউনলোড করতে পারবেন।

📌 *ব্যবহার 방법:*
1. YouTube ভিডিওর লিংক পাঠান
2. বট স্বয়ংক্রিয়ভাবে ভিডিও ডাউনলোড করবে
3. ভিডিওটি আপনাকে ফেরত দেওয়া হবে

⚡ *সীমাবদ্ধতা:*
• সর্বোচ্চ ফাইল সাইজ: 50MB
• শুধুমাত্র YouTube লিংক সাপোর্টেড

📊 *ভিডিও না পেলে:* বিস্তারিত ইনফো দেখাবে

🚀 *শুরু করতে একটি YouTube লিংক পাঠান*
                """
                
                return jsonify(send_telegram_message(
                    chat_id=chat_id,
                    text=welcome_text
                ))

            # /help কমান্ড
            elif message_text.startswith('/help'):
                help_text = """
📌 *YouTube Video Downloader - সাহায্য*

🤖 *কমান্ডস:*
/start - বট শুরু করুন
/help - সাহায্য দেখুন
/test - টেস্ট লিংক
/info - শুধু ভিডিও ইনফো দেখাবে

📥 *ডাউনলোড করতে:*
শুধুমাত্র একটি YouTube ভিডিও লিংক পাঠান

📊 *শুধু ইনফো দেখাতে:*
/info কমান্ড দিয়ে তারপর লিংক পাঠান

🌐 *সাপোর্টেড লিংক ফরম্যাট:*
• https://youtube.com/watch?v=...
• https://youtu.be/...
• https://m.youtube.com/watch?v=...
• YouTube Shorts লিংক

⚡ *সীমাবদ্ধতা:*
• সর্বোচ্চ 50MB সাইজ
• শুধুমাত্র ভিডিও ডাউনলোড

🔧 *হোস্টেড: Render*
                """
                
                return jsonify(send_telegram_message(
                    chat_id=chat_id,
                    text=help_text
                ))

            # /test কমান্ড - টেস্ট লিংক
            elif message_text.startswith('/test'):
                test_links = """
🧪 *টেস্ট লিংক:*

🎵 *ছোট ভিডিও:*
https://youtu.be/dQw4w9WgXcQ

🎬 *সাধারণ ভিডিও:*
https://www.youtube.com/watch?v=jNQXAC9IVRw

📱 *Shorts:*
https://www.youtube.com/shorts/abcdefg

এই লিংকগুলো টেস্ট করতে পারেন!
                """
                
                return jsonify(send_telegram_message(
                    chat_id=chat_id,
                    text=test_links
                ))

            # /info কমান্ড - শুধু ইনফো দেখাবে
            elif message_text.startswith('/info'):
                info_text = """
📊 *শুধু ভিডিও ইনফো মোড*

এখন একটি YouTube লিংক পাঠান, আমি শুধু ভিডিওর তথ্য দেখাব (ডাউনলোড করব না)।

ভিডিওর টাইটেল, চ্যানেল, সময়, ভিউ, লাইক এবং বর্ণনা দেখাবে।
                """
                
                return jsonify(send_telegram_message(
                    chat_id=chat_id,
                    text=info_text
                ))

            # YouTube URL চেক করা (সাধারণ ডাউনলোড)
            elif is_valid_youtube_url(message_text):
                return handle_youtube_download(chat_id, message_text, message_id, download=True)

            # /info এর পর লিংক (শুধু ইনফো)
            elif message_text.startswith('http') and any(cmd in message_text for cmd in ['youtube', 'youtu.be']):
                # যদি আগের মেসেজ /info ছিল
                return handle_youtube_download(chat_id, message_text, message_id, download=False)

            # অন্য মেসেজের জন্য
            else:
                help_text = """
❌ *ইনভ্যালিড ইনপুট*

📌 সঠিকভাবে ব্যবহার করতে:
1. শুধুমাত্র YouTube ভিডিও লিংক পাঠান
2. অথবা নিচের কমান্ড ব্যবহার করুন:

🤖 *কমান্ডস:*
/start - বট শুরু করুন
/help - সাহায্য দেখুন
/test - টেস্ট লিংক
/info - শুধু ভিডিও ইনফো দেখাবে

🌐 *উদাহরণ লিংক:*
https://youtube.com/watch?v=VIDEO_ID
https://youtu.be/VIDEO_ID
https://youtube.com/shorts/VIDEO_ID
                """
                
                return jsonify(send_telegram_message(
                    chat_id=chat_id,
                    text=help_text,
                    reply_to_message_id=message_id
                ))

    except Exception as e:
        logger.error(f'Error: {str(e)}')
        error_msg = f"""
🚨 *সিস্টেম এরর*

❌ এরর: {str(e)}

💡 *সমাধান:*
• কিছুক্ষণ পর আবার চেষ্টা করুন
• /test কমান্ড দিয়ে টেস্ট করুন
• অন্য লিংক ট্রাই করুন
        """
        return jsonify(send_telegram_message(
            chat_id=chat_id,
            text=error_msg
        ))

def handle_youtube_download(chat_id, url, message_id, download=True):
    """
    YouTube ডাউনলোড বা ইনফো হ্যান্ডেল করা
    """
    try:
        logger.info(f"{'Downloading' if download else 'Getting info for'}: {url}")
        
        # প্রথমে ভিডিও ইনফো চেক
        processing_msg = send_telegram_message(
            chat_id=chat_id,
            text="🔍 ভিডিও তথ্য চেক করা হচ্ছে..." if download else "🔍 ভিডিও তথ্য সংগ্রহ করা হচ্ছে...",
            reply_to_message_id=message_id
        )
        
        video_info = get_video_info(url)
        
        if not video_info:
            error_msg = """
❌ *ভিডিও তথ্য পাওয়া যায়নি*

🚨 *সম্ভাব্য কারণ:*
• ভিডিওটি প্রাইভেট বা ডিলিটেড
• নেটওয়ার্ক সমস্যা
• ভিডিও সাইজ খুব বড় (50MB+)
• ভিডিও রেস্ট্রিক্টেড

💡 *সমাধান:*
• ভিডিওটি পাবলিক কিনা চেক করুন
• অন্য লিংক ট্রাই করুন
• /test কমান্ড দিয়ে টেস্ট করুন
            """
            return jsonify(send_telegram_message(
                chat_id=chat_id,
                text=error_msg,
                reply_to_message_id=message_id
            ))
        
        # যদি শুধু ইনফো চায়
        if not download:
            info_message = create_video_info_message(video_info, download_success=False)
            return jsonify(send_telegram_message(
                chat_id=chat_id,
                text=info_message,
                reply_to_message_id=message_id
            ))
        
        # ভিডিও টাইটেল সহ কনফার্মেশন
        filesize = video_info.get('filesize') or video_info.get('filesize_approx', 0)
        
        if filesize > MAX_FILE_SIZE:
            # ভিডিও বড় হলে শুধু ইনফো দেখাবে
            info_message = create_video_info_message(video_info, download_success=False)
            info_message += "\n\n⚠️ *ভিডিওটি খুব বড় হওয়ায় ডাউনলোড করা যায়নি, কিন্তু উপরের তথ্য দেখানো হলো*"
            return jsonify(send_telegram_message(
                chat_id=chat_id,
                text=info_message,
                reply_to_message_id=message_id
            ))
        
        confirm_text = f"""
🎬 *ভিডিও পাওয়া গেছে!*

📝 *টাইটেল:* {video_info.get('title', 'Unknown Title')}
⏱️ *সময়:* {format_duration(video_info.get('duration', 0))}
📦 *আনুমানিক সাইজ:* {format_file_size(filesize) if filesize else 'অজানা'}

⏳ *ডাউনলোড শুরু হচ্ছে...*
        """
        
        # কনফার্মেশন মেসেজ
        jsonify(send_telegram_message(
            chat_id=chat_id,
            text=confirm_text,
            reply_to_message_id=message_id
        ))
        
        # ভিডিও ডাউনলোড
        video_file, thumb_file, download_info = download_video(url)
        
        if not video_file or not os.path.exists(video_file):
            # ডাউনলোড失败 হলে শুধু ইনফো দেখাবে
            info_message = create_video_info_message(video_info, download_success=False)
            info_message += "\n\n❌ *ভিডিও ডাউনলোড করা যায়নি, কিন্তু উপরের তথ্য দেখানো হলো*"
            
            # ক্লিনআপ
            if video_file:
                shutil.rmtree(os.path.dirname(video_file), ignore_errors=True)
            
            return jsonify(send_telegram_message(
                chat_id=chat_id,
                text=info_message,
                reply_to_message_id=message_id
            ))
        
        # ফাইল সাইজ চেক
        file_size = os.path.getsize(video_file)
        if file_size > MAX_FILE_SIZE:
            # ফাইল বড় হলে শুধু ইনফো দেখাবে
            info_message = create_video_info_message(video_info, download_success=False)
            info_message += f"\n\n❌ *ভিডিওটি খুব বড় ({format_file_size(file_size)}) হওয়ায় ডাউনলোড করা যায়নি*"
            
            # ক্লিনআপ
            shutil.rmtree(os.path.dirname(video_file), ignore_errors=True)
            return jsonify(send_telegram_message(
                chat_id=chat_id,
                text=info_message,
                reply_to_message_id=message_id
            ))
        
        # সফল ডাউনলোড হলে ইনফো সহ মেসেজ
        success_message = create_video_info_message(download_info, download_success=True)
        
        # ক্লিনআপ
        shutil.rmtree(os.path.dirname(video_file), ignore_errors=True)
        
        return jsonify(send_telegram_message(
            chat_id=chat_id,
            text=success_message,
            reply_to_message_id=message_id
        ))
        
    except Exception as e:
        logger.error(f"Error in handle_youtube_download: {e}")
        
        # এরর হলেও ভিডিও ইনফো দেখানোর চেষ্টা করবে
        try:
            video_info = get_video_info(url)
            if video_info:
                error_info_message = create_video_info_message(video_info, download_success=False)
                error_info_message += f"\n\n❌ *ডাউনলোড এরর:* {str(e)}"
                return jsonify(send_telegram_message(
                    chat_id=chat_id,
                    text=error_info_message,
                    reply_to_message_id=message_id
                ))
        except:
            pass
        
        error_msg = f"""
🚨 *ডাউনলোড এরর*

❌ এরর: {str(e)}

💡 *সমাধান:*
• কিছুক্ষণ পর আবার চেষ্টা করুন
• অন্য লিংক ট্রাই করুন
• /info কমান্ড দিয়ে শুধু ইনফো দেখুন
        """
        return jsonify(send_telegram_message(
            chat_id=chat_id,
            text=error_msg,
            reply_to_message_id=message_id
        ))

@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint for Render"""
    return jsonify({
        'status': 'healthy',
        'service': 'YouTube Downloader Bot',
        'platform': 'Render',
        'version': '2.0'
    })

@app.route('/test-url', methods=['GET'])
def test_url():
    """URL টেস্ট করার এন্ডপয়েন্ট"""
    url = request.args.get('url')
    if not url:
        return jsonify({'error': 'URL parameter required'}), 400
    
    result = {
        'url': url,
        'is_valid_youtube': is_valid_youtube_url(url),
        'video_id': extract_video_id(url)
    }
    
    if result['is_valid_youtube']:
        info = get_video_info(url)
        if info:
            result['video_info'] = {
                'title': info.get('title'),
                'duration': info.get('duration'),
                'uploader': info.get('uploader'),
                'view_count': info.get('view_count'),
                'filesize': info.get('filesize') or info.get('filesize_approx')
            }
        else:
            result['error'] = 'Could not fetch video info'
    
    return jsonify(result)

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port, debug=False)