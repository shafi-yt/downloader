
import os
import asyncio
import logging
import re
from dataclasses import dataclass, asdict
from typing import Optional, Dict, Any

from downloader import download_with_ytdlp, download_with_pytube, ensure_dir, human_size, has_ffmpeg

from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.constants import ChatAction
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler, CallbackQueryHandler,
    ContextTypes, filters
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
log = logging.getLogger("bot_plus")

URL_RE = re.compile(r"https?://\S+")

@dataclass
class Settings:
    engine: str = "yt-dlp"  # or 'pytube'
    mode: str = "video"     # 'video' or 'audio'
    quality: str = "best"   # best / 1080p / 720p / 480p / 360p
    playlist: bool = False  # yt-dlp only
    to_mp3: bool = True     # audio format preference

DEFAULTS = Settings()

# In-memory per-chat settings
USER_SETTINGS: Dict[int, Settings] = {}

def get_settings(chat_id: int) -> Settings:
    return USER_SETTINGS.get(chat_id, DEFAULTS)

def set_settings(chat_id: int, s: Settings):
    USER_SETTINGS[chat_id] = s

def env(key: str, default: str = "") -> str:
    return os.environ.get(key, default)

DOWNLOAD_DIR = env("DOWNLOAD_DIR", "downloads")
MAX_FILE_MB = int(env("MAX_FILE_MB", "1950"))  # Telegram ~2GB
ensure_dir(DOWNLOAD_DIR)

def engine_keyboard(selected: Optional[Settings]=None):
    s = selected or DEFAULTS
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(("✅ " if s.engine=="yt-dlp" else "") + "yt-dlp", callback_data="engine:yt-dlp"),
            InlineKeyboardButton(("✅ " if s.engine=="pytube" else "") + "pytube", callback_data="engine:pytube"),
        ],
        [
            InlineKeyboardButton(("✅ " if s.mode=="video" else "") + "Video", callback_data="mode:video"),
            InlineKeyboardButton(("✅ " if s.mode=="audio" else "") + "Audio", callback_data="mode:audio"),
        ],
        [
            InlineKeyboardButton(("✅ " if s.quality=='best' else "") + "best", callback_data="quality:best"),
            InlineKeyboardButton(("✅ " if s.quality=='1080p' else "") + "1080p", callback_data="quality:1080p"),
            InlineKeyboardButton(("✅ " if s.quality=='720p' else "") + "720p", callback_data="quality:720p"),
        ],
        [
            InlineKeyboardButton(("✅ " if s.quality=='480p' else "") + "480p", callback_data="quality:480p"),
            InlineKeyboardButton(("✅ " if s.quality=='360p' else "") + "360p", callback_data="quality:360p"),
            InlineKeyboardButton(("✅ " if s.playlist else "") + "Playlist:On" if s.playlist else "Playlist:Off", callback_data="playlist:toggle"),
        ],
        [
            InlineKeyboardButton(("✅ " if s.to_mp3 else "") + ("MP3" if has_ffmpeg() else "MP3 (needs ffmpeg)"), callback_data="mp3:toggle"),
        ],
        [ InlineKeyboardButton("✅ Save Defaults", callback_data="save:yes") ]
    ])

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    s = get_settings(update.effective_chat.id)
    await update.message.reply_text(
        "Send me a URL and choose options.\n\n"
        f"Current defaults:\nEngine: {s.engine}\nMode: {s.mode}\nQuality: {s.quality}\nPlaylist: {s.playlist}\nTo MP3: {s.to_mp3}",
        reply_markup=engine_keyboard(s)
    )

async def settings_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    s = get_settings(update.effective_chat.id)
    await update.message.reply_text("Adjust your defaults:", reply_markup=engine_keyboard(s))

async def on_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    chat_id = query.message.chat_id
    s = get_settings(chat_id)

    data = query.data
    if data.startswith("engine:"):
        s.engine = data.split(":",1)[1]
    elif data.startswith("mode:"):
        s.mode = data.split(":",1)[1]
    elif data.startswith("quality:"):
        s.quality = data.split(":",1)[1]
    elif data.startswith("playlist:toggle"):
        s.playlist = not s.playlist
    elif data.startswith("mp3:toggle"):
        s.to_mp3 = not s.to_mp3
    elif data.startswith("save:yes"):
        set_settings(chat_id, s)
        await query.edit_message_text("Saved defaults ✅\nNow send me a URL.", reply_markup=engine_keyboard(s))
        return

    set_settings(chat_id, s)
    await query.edit_message_reply_markup(reply_markup=engine_keyboard(s))

async def handle_url(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message or update.message
    text = msg.text or ""
    m = URL_RE.search(text)
    if not m:
        return
    url = m.group(0)
    chat_id = update.effective_chat.id
    s = get_settings(chat_id)

    await msg.reply_chat_action(ChatAction.TYPING)
    await msg.reply_text(f"Got URL.\nEngine: {s.engine}\nMode: {s.mode}\nQuality: {s.quality}\nPlaylist: {s.playlist}\nConverting to MP3: {s.to_mp3 and s.mode=='audio'}\n\nWorking…")

    def progress_cb(line: str):
        # Stream minimal progress to chat every so often
        if '[download]' in line or 'Merging formats' in line:
            try:
                context.application.create_task(msg.reply_text(line[:200]))
            except Exception:
                pass

    out_dir = os.path.join(DOWNLOAD_DIR, str(chat_id))
    ensure_dir(out_dir)

    audio_only = (s.mode == "audio")

    files = []
    try:
        if s.engine == "yt-dlp":
            files = download_with_ytdlp(
                url=url,
                out_dir=out_dir,
                quality=s.quality,
                audio_only=audio_only,
                to_mp3=s.to_mp3 and audio_only,
                playlist=s.playlist,
                progress_cb=progress_cb
            )
        else:
            # pytube (single video). On failure, fallback to yt-dlp.
            try:
                files = download_with_pytube(
                    url=url,
                    out_dir=out_dir,
                    quality=s.quality,
                    audio_only=audio_only,
                    to_mp3=s.to_mp3 and audio_only,
                    progress_cb=progress_cb
                )
            except Exception as e:
                await msg.reply_text(f"pytube failed: {e}\nFalling back to yt-dlp…")
                files = download_with_ytdlp(
                    url=url,
                    out_dir=out_dir,
                    quality=s.quality,
                    audio_only=audio_only,
                    to_mp3=s.to_mp3 and audio_only,
                    playlist=False,
                    progress_cb=progress_cb
                )
    except Exception as e:
        await msg.reply_text(f"Download error: {e}")
        return

    if not files:
        await msg.reply_text("No output files were produced 🤔")
        return

    # Send files up to MAX_FILE_MB
    max_bytes = MAX_FILE_MB * 1024 * 1024
    sent = 0
    for p in files:
        try:
            size = os.path.getsize(p)
        except FileNotFoundError:
            continue
        if size <= max_bytes:
            await msg.reply_chat_action(ChatAction.UPLOAD_DOCUMENT)
            try:
                await msg.reply_document(open(p, "rb"), caption=os.path.basename(p))
                sent += 1
            except Exception as e:
                await msg.reply_text(f"Failed to upload {os.path.basename(p)}: {e}")
        else:
            await msg.reply_text(f"⚠️ Skipped {os.path.basename(p)} — size {human_size(size)} exceeds limit {MAX_FILE_MB} MB.")
    if sent == 0:
        await msg.reply_text("Nothing uploaded (files too large?). You can fetch them from the server path or lower quality.")

async def main():
    token = os.environ.get("BOT_TOKEN")
    if not token:
        print("Please set BOT_TOKEN in environment or .env file.")
        return

    app = ApplicationBuilder().token(token).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("settings", settings_cmd))
    app.add_handler(CallbackQueryHandler(on_buttons))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_url))

    log.info("Bot started.")
    await app.run_polling(close_loop=False)

if __name__ == "__main__":
    # Load .env if present
    if os.path.exists(".env"):
        for line in open(".env"):
            line=line.strip()
            if not line or line.startswith("#") or "=" not in line: 
                continue
            k,v = line.split("=",1)
            os.environ.setdefault(k.strip(), v.strip())
    asyncio.run(main())
