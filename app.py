
from flask import Flask, request, jsonify
import os, logging, requests, tempfile, shutil, mimetypes, json

from downloader import dynamic_download_360, human_size

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger("yt_tg_webhook_v9")

app = Flask(__name__)

BOT_TOKEN = os.environ.get("BOT_TOKEN")
MAX_FILE_MB = int(os.environ.get("MAX_FILE_MB", "1950"))
DEFAULT_URL = os.environ.get("DEFAULT_URL", "https://youtu.be/BfLPuDRgjPw")
VERBOSE_DEFAULT = os.environ.get("VERBOSE_CHAT", "0") == "1"

# per-chat verbose toggle
VERBOSE = {}

def tg_api(token, method):
    return f"https://api.telegram.org/bot{token}/{method}"

def tg_send_message(token, chat_id, text):
    try:
        # Telegram limit ~4096 chars; chunk if needed
        chunks = [text[i:i+3500] for i in range(0, len(text), 3500)] or [""]
        for c in chunks:
            requests.post(tg_api(token, "sendMessage"), json={"chat_id": chat_id, "text": c}, timeout=30)
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

def is_video(path:str)->bool:
    mt, _ = mimetypes.guess_type(path)
    if mt and mt.startswith("video/"):
        return True
    return os.path.splitext(path)[1].lower() in {".mp4",".mkv",".webm",".mov",".avi"}

@app.get("/health")
def health():
    have_cookies = bool(os.path.exists(os.environ.get("YT_COOKIES_PATH","cookies.txt")) or os.environ.get("YT_COOKIES_B64"))
    return jsonify({"ok": True, "default_url": DEFAULT_URL, "cookies": have_cookies})

def process_and_upload(token, chat_id, url):
    verbose = VERBOSE.get(chat_id, VERBOSE_DEFAULT)
    def progress(line:str):
        if verbose:
            tg_send_message(token, chat_id, line)
    temp_dir = tempfile.mkdtemp(prefix=f"tg_{chat_id}_")
    try:
        tg_send_message(token, chat_id, "Probing formats (<=360p progressive preferred)…")
        files, fmt, probe_log, dl_full, data = dynamic_download_360(url, temp_dir, progress_cb=progress)
        # always send a short summary
        tg_send_message(token, chat_id, f"Chosen format: `{fmt}`")
        # attach logs as files
        probe_path = os.path.join(temp_dir, "probe.log")
        with open(probe_path,"w") as f:
            f.write(probe_log)
        dl_path = os.path.join(temp_dir, "download.log")
        with open(dl_path,"w") as f:
            f.write(dl_full)
        json_path = os.path.join(temp_dir, "formats.json")
        with open(json_path,"w") as f:
            json.dump(data, f, indent=2)
        tg_send_document(token, chat_id, probe_path, caption="probe.log")
        tg_send_document(token, chat_id, dl_path, caption="download.log")
        tg_send_document(token, chat_id, json_path, caption="formats.json")

        if not files:
            tg_send_message(token, chat_id, "Failed to download any available format.")
            return

        max_bytes = MAX_FILE_MB * 1024 * 1024
        sent = 0
        for p in files:
            try:
                size=os.path.getsize(p)
            except FileNotFoundError:
                continue
            if size<=max_bytes:
                if is_video(p):
                    tg_send_video(token, chat_id, p)
                else:
                    tg_send_document(token, chat_id, p)
                sent+=1
            else:
                tg_send_message(token, chat_id, f"⚠️ Skipped {os.path.basename(p)} — size {human_size(size)} > limit {MAX_FILE_MB} MB.")
        if sent==0:
            tg_send_message(token, chat_id, "Nothing uploaded (files too large?).")
    finally:
        try: shutil.rmtree(temp_dir, ignore_errors=True)
        except Exception as e: logger.error(f"Cleanup failed: {e}")

@app.route("/", methods=["GET","POST"])
def webhook():
    token = request.args.get("token") or BOT_TOKEN
    if not token:
        return jsonify({"error":"Token required","solution":"Add ?token=YOUR_BOT_TOKEN or set BOT_TOKEN"}), 400

    if request.method=="GET":
        have_cookies = bool(os.path.exists(os.environ.get("YT_COOKIES_PATH","cookies.txt")) or os.environ.get("YT_COOKIES_B64"))
        return jsonify({"status":"ok","default_url": DEFAULT_URL, "quality":"<=360p dynamic", "cookies": have_cookies})
    update = request.get_json(silent=True)
    if not update:
        return jsonify({"ok": True})

    msg = update.get("message")
    if not msg:
        return jsonify({"ok": True})
    chat_id = msg["chat"]["id"]
    text = (msg.get("text") or "").strip()

    if text == "/debuglog on":
        VERBOSE[chat_id] = True
        tg_send_message(token, chat_id, "Verbose chat logs: ON")
        return jsonify({"ok": True})
    if text == "/debuglog off":
        VERBOSE[chat_id] = False
        tg_send_message(token, chat_id, "Verbose chat logs: OFF")
        return jsonify({"ok": True})
    if text == "/formats":
        # run probe only and send JSON & summary
        temp_dir = tempfile.mkdtemp(prefix=f"probe_{chat_id}_")
        try:
            from downloader import probe_formats, pick_best_360
            tg_send_message(token, chat_id, "Probing formats…")
            data = probe_formats(DEFAULT_URL)
            best = pick_best_360(data)
            summary = []
            for f in (data.get("formats") or [])[:50]:
                fid = f.get("format_id"); h=f.get("height"); ext=f.get("ext"); vc=f.get("vcodec"); ac=f.get("acodec")
                summary.append(f"{fid}\t{h or '-'}p\t{ext}\t{vc}/{ac}")
            tg_send_message(token, chat_id, "Top formats (first 50):\n" + "\n".join(summary[:50]))
            fp = os.path.join(temp_dir,"formats.json")
            import json
            open(fp,"w").write(json.dumps(data, indent=2))
            tg_send_document(token, chat_id, fp, caption=f"formats.json (best<=360: {best})")
        finally:
            try: shutil.rmtree(temp_dir, ignore_errors=True)
            except: pass
        return jsonify({"ok": True})

    if text.startswith("/start"):
        process_and_upload(token, chat_id, DEFAULT_URL)
        return jsonify({"ok": True})
    if text.startswith("http://") or text.startswith("https://"):
        process_and_upload(token, chat_id, text)
        return jsonify({"ok": True})

    tg_send_message(token, chat_id, "Commands:\n/start – download DEFAULT_URL\n/formats – list formats for DEFAULT_URL\n/debuglog on|off – toggle verbose logs\nOr send any YouTube URL to download.")
    return jsonify({"ok": True})

if __name__ == "__main__":
    port=int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port, debug=False)
