import os
import re
import requests
import tempfile
import urllib.parse
from telebot import TeleBot, types
from telebot.types import InputFile
import threading
import time

# ==== CONFIG ====
BOT_TOKEN = "7628222622:AAHd6XbuWQw1TaurMGu0QWdsJaLF0rIlcj4"  # Replace with your actual bot token
bot = TeleBot(BOT_TOKEN, parse_mode="HTML")

# Worker endpoint from your provided link
WORKER_ENDPOINT = "https://utubdbot.shafitest.workers.dev/"

# Store download progress
download_progress = {}

# ==== KEYBOARDS ====
def main_menu_kb():
    kb = types.ReplyKeyboardMarkup(row_width=1, resize_keyboard=True)
    kb.add("📥 Download YouTube Video")
    kb.add("ℹ️ Help")
    return kb

def cancel_kb():
    kb = types.ReplyKeyboardMarkup(row_width=1, resize_keyboard=True)
    kb.add("❌ Cancel")
    return kb

# ==== UTILITY FUNCTIONS ====
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
        response = requests.head(worker_url, allow_redirects=True)
        
        if response.status_code == 200:
            return {
                'success': True,
                'download_url': worker_url,
                'video_id': video_id
            }
        else:
            return {'success': False, 'error': 'Video not available'}
            
    except Exception as e:
        return {'success': False, 'error': str(e)}

def download_video_with_progress(download_url, chat_id, filename):
    """Download video with progress tracking"""
    try:
        # Update progress
        download_progress[chat_id] = {'status': 'downloading', 'progress': 0}
        
        # Download the video
        response = requests.get(download_url, stream=True)
        total_size = int(response.headers.get('content-length', 0))
        
        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.mp4')
        downloaded_size = 0
        
        for chunk in response.iter_content(chunk_size=8192):
            if chunk:
                temp_file.write(chunk)
                downloaded_size += len(chunk)
                
                # Update progress
                if total_size > 0:
                    progress = (downloaded_size / total_size) * 100
                    download_progress[chat_id] = {
                        'status': 'downloading', 
                        'progress': int(progress)
                    }
        
        temp_file.close()
        download_progress[chat_id] = {'status': 'completed', 'progress': 100}
        
        return temp_file.name
        
    except Exception as e:
        download_progress[chat_id] = {'status': 'error', 'error': str(e)}
        return None

def send_progress_message(chat_id, message_id=None):
    """Send or update progress message"""
    progress_data = download_progress.get(chat_id, {})
    
    if progress_data.get('status') == 'downloading':
        progress_bar = "🟩" * (progress_data['progress'] // 10) + "⬜" * (10 - (progress_data['progress'] // 10))
        text = f"📥 Downloading...\n\n{progress_bar} {progress_data['progress']}%"
        
        if message_id:
            try:
                bot.edit_message_text(text, chat_id, message_id)
            except:
                pass
        else:
            msg = bot.send_message(chat_id, text)
            return msg.message_id
            
    elif progress_data.get('status') == 'uploading':
        text = "📤 Uploading to Telegram..."
        if message_id:
            try:
                bot.edit_message_text(text, chat_id, message_id)
            except:
                pass
        else:
            msg = bot.send_message(chat_id, text)
            return msg.message_id
            
    return message_id

# ==== HANDLERS ====
@bot.message_handler(commands=["start", "help"])
def cmd_start(message):
    chat_id = message.chat.id
    text = (
        "🎬 <b>YouTube Video Downloader Bot</b>\n\n"
        "I can download YouTube videos and send them to you!\n\n"
        "📌 <b>How to use:</b>\n"
        "1. Send any YouTube video URL\n"
        "2. Or click <b>Download YouTube Video</b>\n"
        "3. I'll download and send you the video\n\n"
        "🔗 <b>Supported formats:</b>\n"
        "• youtube.com/watch?v=...\n"
        "• youtu.be/...\n"
        "• youtube.com/embed/...\n\n"
        "⚠️ <b>Note:</b> Maximum video size 50MB"
    )
    bot.send_message(chat_id, text, reply_markup=main_menu_kb())

@bot.message_handler(func=lambda message: message.text == "📥 Download YouTube Video")
def ask_for_url(message):
    chat_id = message.chat.id
    text = (
        "🔗 <b>Send YouTube URL</b>\n\n"
        "Please send me the YouTube video link you want to download.\n\n"
        "Examples:\n"
        "• https://youtu.be/FbcHYg4Qx7o\n"
        "• https://www.youtube.com/watch?v=FbcHYg4Qx7o"
    )
    bot.send_message(chat_id, text, reply_markup=cancel_kb())
    bot.register_next_step_handler(message, process_youtube_url)

@bot.message_handler(func=lambda message: message.text == "ℹ️ Help")
def show_help(message):
    cmd_start(message)

@bot.message_handler(func=lambda message: message.text == "❌ Cancel")
def cancel_operation(message):
    chat_id = message.chat.id
    if chat_id in download_progress:
        del download_progress[chat_id]
    bot.send_message(chat_id, "❌ Operation cancelled.", reply_markup=main_menu_kb())

@bot.message_handler(func=lambda message: True)
def handle_all_messages(message):
    chat_id = message.chat.id
    text = message.text
    
    # Check if it's a YouTube URL
    youtube_id = extract_youtube_id(text)
    if youtube_id:
        process_youtube_url(message)
    else:
        bot.send_message(chat_id, 
                        "❌ Please send a valid YouTube URL or use the menu buttons.",
                        reply_markup=main_menu_kb())

def process_youtube_url(message):
    chat_id = message.chat.id
    url = message.text
    
    if url == "❌ Cancel":
        cancel_operation(message)
        return
    
    youtube_id = extract_youtube_id(url)
    if not youtube_id:
        bot.send_message(chat_id, 
                        "❌ Invalid YouTube URL. Please send a valid YouTube link.",
                        reply_markup=main_menu_kb())
        return
    
    # Send initial processing message
    processing_msg = bot.send_message(chat_id, "🔍 Processing YouTube video...")
    
    # Get video info
    video_info = get_video_info(youtube_id)
    
    if not video_info['success']:
        bot.edit_message_text("❌ Error: Could not fetch video information.", 
                            chat_id, processing_msg.message_id)
        return
    
    # Start download in separate thread
    def download_thread():
        try:
            # Update status
            bot.edit_message_text("⬇️ Starting download...", 
                                chat_id, processing_msg.message_id)
            
            # Start progress tracking
            progress_msg_id = processing_msg.message_id
            download_progress[chat_id] = {'status': 'downloading', 'progress': 0}
            
            # Send progress updates every 2 seconds
            def progress_updater():
                for _ in range(30):  # Max 60 seconds
                    if chat_id not in download_progress:
                        break
                    if download_progress[chat_id]['status'] in ['completed', 'error', 'uploading']:
                        break
                    send_progress_message(chat_id, progress_msg_id)
                    time.sleep(2)
            
            progress_thread = threading.Thread(target=progress_updater)
            progress_thread.start()
            
            # Download video
            filename = f"youtube_{youtube_id}.mp4"
            video_path = download_video_with_progress(
                video_info['download_url'], 
                chat_id, 
                filename
            )
            
            if not video_path:
                bot.edit_message_text("❌ Download failed.", 
                                    chat_id, progress_msg_id)
                return
            
            # Update status to uploading
            download_progress[chat_id] = {'status': 'uploading'}
            send_progress_message(chat_id, progress_msg_id)
            
            # Send video to Telegram
            with open(video_path, 'rb') as video_file:
                bot.send_video(
                    chat_id,
                    video_file,
                    caption=f"🎥 Downloaded YouTube Video\n\n🔗 Original: {url}",
                    reply_markup=main_menu_kb()
                )
            
            # Clean up
            os.unlink(video_path)
            if chat_id in download_progress:
                del download_progress[chat_id]
                
            # Delete progress message
            try:
                bot.delete_message(chat_id, progress_msg_id)
            except:
                pass
                
        except Exception as e:
            bot.send_message(chat_id, f"❌ Error: {str(e)}", reply_markup=main_menu_kb())
            if chat_id in download_progress:
                del download_progress[chat_id]
    
    # Start download thread
    thread = threading.Thread(target=download_thread)
    thread.start()

# ==== ERROR HANDLER ====
@bot.message_handler(func=lambda message: True, content_types=['audio', 'photo', 'voice', 'video', 'document', 'location', 'contact', 'sticker'])
def handle_unsupported(message):
    chat_id = message.chat.id
    bot.send_message(chat_id, 
                    "❌ I only process YouTube URLs. Please send a YouTube link.",
                    reply_markup=main_menu_kb())

if __name__ == "__main__":
    print("🤖 YouTube Video Downloader Bot is running...")
    print("📍 Use /start to begin")
    bot.infinity_polling()