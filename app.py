
from flask import Flask, request, jsonify
import os, logging, requests, tempfile, shutil, mimetypes

from downloader import smart_download, human_size

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger("autostart_direct_upload")

app = Flask(__name__)

BOT_TOKEN = os.environ.get("BOT_TOKEN")
MAX_FILE_MB = int(os.environ.get("MAX_FILE_MB", "1950"))
# default quality (can be overridden by QUALITY env)
QUALITY = os.environ.get("QUALITY", "360p")
# Hardcoded default URL; can override with DEFAULT_URL env or by sending a plain text URL later
DEFAULT_URL = os.environ.get("DEFAULT_URL", "https://youtu.be/BfLPuDRgjPw")

def tg_api(token, method):
    return f"https://api.telegram.org/bot{token}/{method}"

def tg_send_message(token, chat_id, text):
    try:
        requests.post(tg_api(token, "sendMessage"), json={"chat_id": chat_id, "text": text}, timeout=20)
    except Exception as e:
        logger.error(f"sendMessage failed: {e}")

def tg_send_video(token, chat_id, file_path, caption=None):
    try:
        with open(file_path, "rb") as f:
            files={"video": (os.path.basename(file_path), f)}
            data={"chat_id": chat_id, "caption": caption or os.path.basename(file_path)}
            requests.post(tg_api(token, "sendVideo"), data=data, files=files, timeout=600)
    except Exception as e:
        logger.error(f"sendVideo failed: {e}")

def tg_send_document(token, chat_id, file_path, caption=None):
    try:
        with open(file_path, "rb") as f:
            files={"document": (os.path.basename(file_path), f)}
            data={"chat_id": chat_id, "caption": caption or os.path.basename(file_path)}
            requests.post(tg_api(token, "sendDocument"), data=data, files=files, timeout=600)
    except Exception as e:
        logger.error(f"sendDocument failed: {e}")

def is_video(path:str)->bool:
    mt, _ = mimetypes.guess_type(path)
    if mt and mt.startswith("video/"):
        return True
    return os.path.splitext(path)[1].lower() in {".mp4",".mkv",".webm",".mov",".avi"}

def process_and_upload(token, chat_id, url):
    tg_send_message(token, chat_id, f"Starting download:\n{url}\nQuality: {QUALITY}\n(Will auto-fallback if needed.)")
    temp_dir = tempfile.mkdtemp(prefix=f"tg_{chat_id}_")
    try:
        files = smart_download(url, temp_dir, quality=QUALITY, audio_only=False, to_mp3=False, playlist=False,
                               progress_cb=lambda ln: (("[download]" in ln or "Merging formats" in ln) and tg_send_message(token, chat_id, ln[:200])))
        if not files:
            tg_send_message(token, chat_id, "Failed to produce output after all attempts 🤔")
            return

        max_bytes = MAX_FILE_MB * 1024 * 1024
        sent = 0
        for p in files:
            size=os.path.getsize(p)
            if size<=max_bytes:
                if is_video(p):
                    tg_send_video(token, chat_id, p)
                else:
                    tg_send_document(token, chat_id, p)
                sent+=1
            else:
                tg_send_message(token, chat_id, f"⚠️ Skipped {os.path.basename(p)} — size {human_size(size)} > limit {MAX_FILE_MB} MB. Try lower QUALITY env.")
        if sent==0:
            tg_send_message(token, chat_id, "Nothing uploaded (files too large?). Set QUALITY=480p or 360p and try again.")
    finally:
        try:
            shutil.rmtree(temp_dir, ignore_errors=True)
        except Exception as e:
            logger.error(f"Cleanup failed: {e}")

@app.route("/", methods=["GET","POST"])
def webhook():
    token = request.args.get("token") or BOT_TOKEN
    if not token:
        return jsonify({"error":"Token required","solution":"Add ?token=YOUR_BOT_TOKEN or set BOT_TOKEN"}), 400

    if request.method=="GET":
        return jsonify({"status":"ok","default_url": DEFAULT_URL, "quality": QUALITY})

    update = request.get_json(silent=True)
    if not update:
        return jsonify({"ok": True})

    # /start -> directly download DEFAULT_URL and upload
    msg = update.get("message")
    if not msg:
        return jsonify({"ok": True})
    chat_id = msg["chat"]["id"]
    text = msg.get("text","")

    if text.startswith("/start"):
        process_and_upload(token, chat_id, DEFAULT_URL)
        return jsonify({"ok": True})

    # If user sends another URL, process that one directly too
    if text.startswith("http://") or text.startswith("https://"):
        process_and_upload(token, chat_id, text.strip())
        return jsonify({"ok": True})

    # Generic reply
    tg_send_message(token, chat_id, "Send /start to download the default video, or send any YouTube URL to download it directly.")
    return jsonify({"ok": True})

if __name__ == "__main__":
    port=int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port, debug=False)
