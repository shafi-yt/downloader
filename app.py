
from flask import Flask, request, jsonify
import os, logging, re, requests, mimetypes, tempfile, shutil
from typing import Dict

from downloader import (smart_download, ensure_dir, human_size, has_ffmpeg)

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger("flask_yt_pytube_v3_tmpdl")

app = Flask(__name__)

BOT_TOKEN_ENV = os.environ.get("BOT_TOKEN")
MAX_FILE_MB = int(os.environ.get("MAX_FILE_MB", "1950"))

URL_RE = re.compile(r"https?://\\S+")

class Settings:
    def __init__(self):
        self.engine = "yt-dlp"
        self.mode = "video"
        self.quality = "1080p"
        self.playlist = False
        self.to_mp3 = True

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
        requests.post(tg_api(token, "sendMessage"), json=payload, timeout=20)
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

def tg_send_video(token, chat_id, file_path, caption=None):
    try:
        with open(file_path, "rb") as f:
            files={"video": (os.path.basename(file_path), f)}
            data={"chat_id": chat_id, "caption": caption or os.path.basename(file_path)}
            requests.post(tg_api(token, "sendVideo"), data=data, files=files, timeout=600)
    except Exception as e:
        logger.error(f"sendVideo failed: {e}")

def guess_is_video(path:str)->bool:
    mt, _ = mimetypes.guess_type(path)
    if mt and mt.startswith("video/"):
        return True
    return os.path.splitext(path)[1].lower() in {".mp4",".mkv",".webm",".mov",".avi"}

def keyboards(settings:Settings):
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
                {"text": ("✅ " if settings.to_mp3 else "") + "MP3", "callback_data": "mp3:toggle"},
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
    token = request.args.get("token") or BOT_TOKEN_ENV
    if not token:
        return jsonify({"error":"Token required","solution":"Add ?token=YOUR_BOT_TOKEN or set BOT_TOKEN"}), 400

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

    # Buttons
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

    if text.startswith("/start"):
        tg_send_message(token, chat_id,
                        "Send a URL and choose options. I download to a temporary folder, upload to Telegram, then delete files.",
                        reply_markup=keyboards(s))
        return jsonify({"ok": True})

    if text.startswith("/settings"):
        tg_send_message(token, chat_id, "Adjust settings:", reply_markup=keyboards(s))
        return jsonify({"ok": True})

    m = URL_RE.search(text or "")
    if not m:
        tg_send_message(token, chat_id, "Please send a valid URL or use /settings")
        return jsonify({"ok": True})

    url = m.group(0)
    audio_only = (s.mode=="audio")
    tg_send_message(token, chat_id, f"Got URL.\nEngine: {s.engine} (auto-fallback enabled)\nMode: {s.mode}\nQuality: {s.quality}\nPlaylist: {s.playlist}\nTo MP3: {s.to_mp3 and audio_only}\nWorking…")

    # --- Temporary folder per request ---
    temp_dir = tempfile.mkdtemp(prefix=f"tg_{chat_id}_")
    try:
        def progress(line:str):
            if "[download]" in line or "Merging formats" in line or "Destination" in line:
                tg_send_message(token, chat_id, line[:200])

        files = smart_download(url, temp_dir, quality=s.quality, audio_only=audio_only, to_mp3=(s.to_mp3 and audio_only), playlist=s.playlist, progress_cb=progress)

        if not files:
            tg_send_message(token, chat_id, "No output files were produced after all attempts 🤔")
            return jsonify({"ok": True})

        max_bytes = MAX_FILE_MB * 1024 * 1024
        sent = 0
        for p in files:
            try:
                size=os.path.getsize(p)
            except FileNotFoundError:
                continue
            if size<=max_bytes:
                if not audio_only and guess_is_video(p):
                    tg_send_video(token, chat_id, p, caption=os.path.basename(p))
                else:
                    tg_send_document(token, chat_id, p, caption=os.path.basename(p))
                sent+=1
            else:
                tg_send_message(token, chat_id, f"⚠️ Skipped {os.path.basename(p)} — size {human_size(size)} exceeds limit {MAX_FILE_MB} MB. Try lower quality (/settings).")
        if sent==0:
            tg_send_message(token, chat_id, "Nothing uploaded (files too large?). Try lower quality.")
    finally:
        # Cleanup temporary directory
        try:
            shutil.rmtree(temp_dir, ignore_errors=True)
        except Exception as e:
            logger.error(f"Temp cleanup failed: {e}")

    return jsonify({"ok": True})

# helpers used above
import mimetypes
def guess_is_video(path:str)->bool:
    mt, _ = mimetypes.guess_type(path)
    if mt and mt.startswith("video/"):
        return True
    return os.path.splitext(path)[1].lower() in {".mp4",".mkv",".webm",".mov",".avi"}

if __name__ == "__main__":
    port=int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port, debug=False)
