
from flask import Flask, request, jsonify
import os, logging, json, re, requests
from typing import Dict

from downloader import (ytdlp_download, pytube_download, ensure_dir, human_size, has_ffmpeg)

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger("flask_yt_pytube")

app = Flask(__name__)

BOT_TOKEN_ENV = os.environ.get("BOT_TOKEN")
DOWNLOAD_DIR = os.environ.get("DOWNLOAD_DIR", "downloads")
MAX_FILE_MB = int(os.environ.get("MAX_FILE_MB", "1950"))
ensure_dir(DOWNLOAD_DIR)

URL_RE = re.compile(r"https?://\S+")

# per-chat in-memory settings
class Settings:
    def __init__(self):
        self.engine = "yt-dlp"   # or 'pytube'
        self.mode = "video"      # 'video' or 'audio'
        self.quality = "best"    # best/1080p/720p/480p/360p
        self.playlist = False    # yt-dlp only
        self.to_mp3 = True       # when audio

USER_SETTINGS: Dict[int, Settings] = {}

def get_settings(chat_id:int)->Settings:
    return USER_SETTINGS.get(chat_id, Settings())

def set_settings(chat_id:int, s:Settings):
    USER_SETTINGS[chat_id]=s

def tg_api(token, method):
    return f"https://api.telegram.org/bot{token}/{method}"

def tg_send_message(token, chat_id, text, reply_markup=None, parse_mode="Markdown"):
    payload={"chat_id": chat_id, "text": text, "parse_mode": parse_mode}
    if reply_markup:
        payload["reply_markup"]=reply_markup
    try:
        requests.post(tg_api(token, "sendMessage"), json=payload, timeout=15)
    except Exception as e:
        logger.error(f"sendMessage failed: {e}")

def tg_send_document(token, chat_id, file_path, caption=None):
    try:
        with open(file_path, "rb") as f:
            files={"document": (os.path.basename(file_path), f)}
            data={"chat_id": chat_id, "caption": caption or os.path.basename(file_path)}
            requests.post(tg_api(token, "sendDocument"), data=data, files=files, timeout=600)
    except Exception as e:
        logger.error(f"sendDocument failed: {e}")

def keyboards(settings:Settings):
    # inline keyboard with callback_data handled locally via text commands for simplicity
    # We'll simulate buttons by sending quick command hints.
    kb = {
        "inline_keyboard": [
            [
                {"text": ("✅ " if settings.engine=='yt-dlp' else "") + "yt-dlp", "callback_data": "engine:yt-dlp"},
                {"text": ("✅ " if settings.engine=='pytube' else "") + "pytube", "callback_data": "engine:pytube"},
            ],
            [
                {"text": ("✅ " if settings.mode=='video' else "") + "Video", "callback_data": "mode:video"},
                {"text": ("✅ " if settings.mode=='audio' else "") + "Audio", "callback_data": "mode:audio"},
            ],
            [
                {"text": ("✅ " if settings.quality=='best' else "") + "best", "callback_data": "quality:best"},
                {"text": ("✅ " if settings.quality=='1080p' else "") + "1080p", "callback_data": "quality:1080p"},
                {"text": ("✅ " if settings.quality=='720p' else "") + "720p", "callback_data": "quality:720p"},
            ],
            [
                {"text": ("✅ " if settings.quality=='480p' else "") + "480p", "callback_data": "quality:480p"},
                {"text": ("✅ " if settings.quality=='360p' else "") + "360p", "callback_data": "quality:360p"},
                {"text": ("✅ " if settings.playlist else "") + ("Playlist:On" if settings.playlist else "Playlist:Off"),
                 "callback_data": "playlist:toggle"},
            ],
            [
                {"text": ("✅ " if settings.to_mp3 else "") + ("MP3" if has_ffmpeg() else "MP3 (needs ffmpeg)"),
                 "callback_data": "mp3:toggle"},
            ],
        ]
    }
    return kb

def apply_button(chat_id:int, data:str):
    s=get_settings(chat_id)
    if data.startswith("engine:"):
        s.engine=data.split(":",1)[1]
    elif data.startswith("mode:"):
        s.mode=data.split(":",1)[1]
    elif data.startswith("quality:"):
        s.quality=data.split(":",1)[1]
    elif data.startswith("playlist:toggle"):
        s.playlist = not s.playlist
    elif data.startswith("mp3:toggle"):
        s.to_mp3 = not s.to_mp3
    set_settings(chat_id, s)
    return s

@app.route("/", methods=["GET","POST"])
def webhook():
    # token can come from query or env
    token = request.args.get("token") or BOT_TOKEN_ENV
    if not token:
        return jsonify({"error":"Token required","solution":"Add ?token=YOUR_BOT_TOKEN or set BOT_TOKEN env"}), 400

    if request.method=="GET":
        return jsonify({
            "status":"Bot is running",
            "ffmpeg": has_ffmpeg(),
            "usage":"Set telegram webhook to this URL with ?token=..."
        })

    update = request.get_json(silent=True)
    if not update:
        return jsonify({"error":"Invalid JSON"}), 400

    logger.info(f"Update: {update}")

    # callback query (buttons)
    if "callback_query" in update:
        cq = update["callback_query"]
        chat_id = cq["message"]["chat"]["id"]
        data = cq.get("data","")
        s = apply_button(chat_id, data)
        tg_send_message(token, chat_id, f"Updated settings:\nengine={s.engine}\nmode={s.mode}\nquality={s.quality}\nplaylist={s.playlist}\nto_mp3={s.to_mp3}", reply_markup=keyboards(s))
        return jsonify({"ok": True})

    if "message" not in update:
        return jsonify({"ok": True})

    msg = update["message"]
    chat_id = msg["chat"]["id"]
    text = msg.get("text","")

    s = get_settings(chat_id)

    # commands
    if text.startswith("/start"):
        tg_send_message(token, chat_id,
                        "Send a URL and choose options.\nYou can tap buttons to change defaults.",
                        reply_markup=keyboards(s))
        return jsonify({"ok": True})

    if text.startswith("/settings"):
        tg_send_message(token, chat_id, "Adjust settings:", reply_markup=keyboards(s))
        return jsonify({"ok": True})

    # treat as URL
    m = URL_RE.search(text)
    if not m:
        tg_send_message(token, chat_id, "Please send a valid URL or use /settings")
        return jsonify({"ok": True})

    url = m.group(0)
    tg_send_message(token, chat_id, f"Got URL.\nEngine: {s.engine}\nMode: {s.mode}\nQuality: {s.quality}\nPlaylist: {s.playlist}\nTo MP3: {s.to_mp3 and s.mode=='audio'}\nWorking…")

    out_dir = os.path.join(DOWNLOAD_DIR, str(chat_id))
    ensure_dir(out_dir)
    audio_only = (s.mode=="audio")

    files=[]
    try:
        if s.engine=="yt-dlp":
            files = ytdlp_download(url, out_dir, quality=s.quality, audio_only=audio_only, to_mp3=s.to_mp3 and audio_only, playlist=s.playlist,
                                   progress_cb=lambda ln: (('[download]' in ln) and tg_send_message(token, chat_id, ln[:200])))
        else:
            try:
                files = pytube_download(url, out_dir, quality=s.quality, audio_only=audio_only, to_mp3=s.to_mp3 and audio_only,
                                        progress_cb=None)
            except Exception as e:
                tg_send_message(token, chat_id, f"pytube failed: {e}\nFalling back to yt-dlp…")
                files = ytdlp_download(url, out_dir, quality=s.quality, audio_only=audio_only, to_mp3=s.to_mp3 and audio_only, playlist=False,
                                       progress_cb=lambda ln: (('[download]' in ln) and tg_send_message(token, chat_id, ln[:200])))
    except Exception as e:
        tg_send_message(token, chat_id, f"Download error: {e}")
        return jsonify({"ok": True})

    if not files:
        tg_send_message(token, chat_id, "No output files were produced 🤔")
        return jsonify({"ok": True})

    max_bytes = MAX_FILE_MB * 1024 * 1024
    sent=0
    for p in files:
        try:
            size=os.path.getsize(p)
        except FileNotFoundError:
            continue
        if size<=max_bytes:
            tg_send_document(token, chat_id, p, caption=os.path.basename(p))
            sent+=1
        else:
            tg_send_message(token, chat_id, f"⚠️ Skipped {os.path.basename(p)} — size {human_size(size)} exceeds limit {MAX_FILE_MB} MB.")
    if sent==0:
        tg_send_message(token, chat_id, "Nothing uploaded (files too large?). Try lower quality.")

    return jsonify({"ok": True})

if __name__ == "__main__":
    port=int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port, debug=False)
