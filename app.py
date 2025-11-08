from flask import Flask, request, jsonify
import os, re, tempfile, threading, subprocess, shlex, glob, logging, json, requests, base64

# ---------- Config ----------
MAX_FILE_MB = 48
HARD_LIMIT_BYTES = MAX_FILE_MB * 1024 * 1024
YTDLP_COOKIES_B64 = os.getenv("YTDLP_COOKIES_B64", "").strip()  # Base64 of Netscape cookies.txt
PTF_PO_TOKEN = os.getenv("PTF_PO_TOKEN", "").strip()  # optional for pytubefix

# ---------- Logging ----------
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger("litebot")

app = Flask(__name__)

# ---------- Helpers ----------
YOUTUBE_RE = re.compile(r'(https?://)?(www\.)?(youtube\.com|youtu\.be)/\S+', re.I)

def get_cookiefile_path():
    if not YTDLP_COOKIES_B64:
        return None
    try:
        import tempfile, base64
        raw = base64.b64decode(YTDLP_COOKIES_B64.encode("utf-8"))
        path = os.path.join(tempfile.gettempdir(), "cookies_youtube.txt")
        # write if missing or changed
        if not os.path.exists(path) or os.path.getsize(path) != len(raw):
            with open(path, "wb") as f:
                f.write(raw)
        return path
    except Exception as e:
        logger.exception("Failed to load cookies: %s", e)
        return None

def safe_filename(s: str) -> str:
    return re.sub(r'[^A-Za-z0-9\-\._\s]+', '_', (s or "")).strip()[:120] or "video"

def guess_file_by_ext(tmpdir: str, exts):
    candidates = []
    for ext in exts:
        candidates.extend(glob.glob(os.path.join(tmpdir, f"*.{ext}")))
    if not candidates:
        return None
    return max(candidates, key=os.path.getsize)

def guess_video_file(tmpdir: str):
    return guess_file_by_ext(tmpdir, ["mp4", "mkv", "webm"])

def guess_audio_file(tmpdir: str):
    return guess_file_by_ext(tmpdir, ["m4a", "mp3", "opus", "aac"])

def tg_api_base(bot_token: str) -> str:
    return f"https://api.telegram.org/bot{bot_token}"

def tg_send_message_api(bot_token: str, chat_id: int, text: str):
    data = {"chat_id": chat_id, "text": text}
    try:
        r = requests.post(f"{tg_api_base(bot_token)}/sendMessage", json=data, timeout=30)
        logger.info("sendMessage status=%s body=%s", getattr(r, "status_code", None), getattr(r, "text", None)[:400])
        return r
    except Exception as e:
        logger.exception("sendMessage failed: %s", e)

def tg_send_video_api(bot_token: str, chat_id: int, file_path: str, caption: str = ""):
    with open(file_path, "rb") as f:
        files = {"video": (os.path.basename(file_path), f, "video/mp4")}
        data = {"chat_id": chat_id, "caption": caption}
        r = requests.post(f"{tg_api_base(bot_token)}/sendVideo", files=files, data=data, timeout=600)
        logger.info("sendVideo status=%s body=%s", getattr(r, "status_code", None), getattr(r, "text", None)[:400])
        return r

def tg_send_audio_api(bot_token: str, chat_id: int, file_path: str, caption: str = ""):
    with open(file_path, "rb") as f:
        files = {"audio": (os.path.basename(file_path), f)}
        data = {"chat_id": chat_id, "caption": caption}
        r = requests.post(f"{tg_api_base(bot_token)}/sendAudio", files=files, data=data, timeout=600)
        logger.info("sendAudio status=%s body=%s", getattr(r, "status_code", None), getattr(r, "text", None)[:400])
        return r

# ---------- yt-dlp CLI (Lite) ----------
def get_ytdlp_base_cmd(url: str, outtmpl: str, fmt: str, cookiefile: str = None, client: str = "android"):
    cmd = [
        "yt-dlp",
        "-o", outtmpl,
        "-f", fmt,
        "--max-filesize", f"{MAX_FILE_MB}M",
        "--no-playlist",
        "--restrict-filenames",
        url
    ]
    # extractor client hint and cookies (if provided)
    cmd.extend(["--extractor-args", f"youtube:player_client={client}"])
    if cookiefile:
        cmd.extend(["--cookies", cookiefile])
    return cmd

def run_cli(cmd, cwd):
    logger.info("Running: %s", " ".join(shlex.quote(c) for c in cmd))
    cp = subprocess.run(cmd, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    logger.info(cp.stdout)
    if cp.returncode != 0:
        raise RuntimeError("yt-dlp CLI failed:\n" + (cp.stdout or ""))

# ---------- Download methods (Lite) ----------
def download_with_ytdlp_cli(url: str, outdir: str, fmt=None):
    # Lite bot: prefer small formats: 360p then 480p then fallback
    formats = [
        "best[ext=mp4][height<=360][filesize<48M]",
        "best[ext=mp4][height<=480][filesize<48M]",
        "best[ext=mp4][filesize<48M]",
    ]
    cookiefile = get_cookiefile_path()
    last_err = None
    for client in ("android", "web_safari"):
        for f in formats:
            outtmpl = os.path.join(outdir, "youtube.%(ext)s")
            cmd = get_ytdlp_base_cmd(url, outtmpl, f, cookiefile=cookiefile, client=client)
            try:
                run_cli(cmd, outdir)
                return guess_video_file(outdir)
            except Exception as e:
                last_err = e
                logger.info("yt-dlp attempt client=%s format=%s failed: %s", client, f, e)
    raise last_err

def download_audio_cli(url: str, outdir: str):
    cookiefile = get_cookiefile_path()
    cmd = get_ytdlp_base_cmd(url, os.path.join(outdir, "audio.%(ext)s"), "bestaudio[ext=m4a][filesize<48M]", cookiefile=cookiefile)
    run_cli(cmd, outdir)
    return guess_audio_file(outdir)

# ---------- Process & upload worker ----------
def process_and_upload(bot_token: str, chat_id: int, url: str, mode: str):
    with tempfile.TemporaryDirectory() as tmp:
        try:
            if mode == "audio":
                apath = download_audio_cli(url, tmp)
                if not apath:
                    raise RuntimeError("Audio not found")
                if os.path.getsize(apath) > HARD_LIMIT_BYTES:
                    raise RuntimeError("Audio exceeds limit")
                tg_send_audio_api(bot_token, chat_id, apath, caption="🎧 Extracted audio")
                return
            else:
                path = download_with_ytdlp_cli(url, tmp)
            if not path:
                tg_send_message_api(bot_token, chat_id, "⚠️ ফাইল খুঁজে পাইনি। অন্য মেথড চেষ্টা করুন।")
                return
            size_mb = os.path.getsize(path) / (1024 * 1024)
            if size_mb > MAX_FILE_MB:
                tg_send_message_api(bot_token, chat_id, f"⚠️ ফাইল {size_mb:.1f}MB — সীমা পার হচ্ছে। /audio বা /360 চেষ্টা করুন।")
                return
            tg_send_video_api(bot_token, chat_id, path, caption="📥 Downloaded (Lite)")
        except Exception as e:
            logger.exception("Processing error")
            msg = str(e)
            if "Sign in to confirm" in msg or "bot" in msg.lower():
                tg_send_message_api(bot_token, chat_id, "🛑 YouTube anti-bot detected. Set YTDLP_COOKIES_B64 (Base64 of cookies.txt) in Render env and redeploy.")
            else:
                tg_send_message_api(bot_token, chat_id, f"❌ ব্যর্থ: {e}")

# ---------- Help text ----------
HELP_TEXT = (
    "👋 Lite bot (360/480 target)\n"
    "/ytdlp <url> - try to download small MP4 (360/480)\n"
    "/360 <url> - force 360p\n"
    "/audio <url> - m4a audio extraction\n"
    "/start - profile info\n"
    "/help - this message\n\n"
    "🔒 If YouTube asks to sign in, set YTDLP_COOKIES_B64 env var with your cookies.txt (Base64)."
)

def first_url(s: str):
    m = YOUTUBE_RE.search(s or "")
    return m.group(0) if m else None

def parse_cmd(text: str):
    if not text:
        return None, None
    parts = text.split(maxsplit=1)
    cmd = parts[0].lower()
    arg = parts[1].strip() if len(parts) > 1 else ""
    return cmd, arg

# ---------- Single endpoint ----------
@app.route('/', methods=['GET', 'HEAD', 'POST'])
def handle_request():
    try:
        token = request.args.get('token')
        if request.method in ('GET', 'HEAD'):
            return jsonify({'ok': True, 'service': 'telegram-ytdlp-lite'})
        if not token:
            return jsonify({'error':'Token required','solution':'Add ?token=BOT_TOKEN to webhook URL'}), 400

        update = request.get_json(silent=True)
        if not update:
            return jsonify({'error':'Invalid JSON'}), 400
        logger.info("Update received: %s", json.dumps(update)[:2000])

        if 'message' in update:
            msg = update['message']
        elif 'edited_message' in update:
            msg = update['edited_message']
        else:
            return jsonify({'ok': True})

        chat = msg.get('chat') or {}
        chat_id = chat.get('id')
        message_text = (msg.get('text') or "").strip()
        user = msg.get('from', {})

        if not chat_id:
            return jsonify({'error':'Chat ID not found'}), 400

        # start/help
        if re.match(r'^/start(?:@\w+)?\b', message_text):
            first_name = user.get('first_name','অজানা')
            username = user.get('username','অজানা')
            profile = f"🤖 Hi {first_name}\\n• username: @{username}\\n• chat_id: {chat_id}\\nUse /ytdlp <url>"
            tg_send_message_api(token, chat_id, profile)
            return jsonify({'ok': True})

        if re.match(r'^/help(?:@\w+)?\b', message_text):
            tg_send_message_api(token, chat_id, HELP_TEXT)
            return jsonify({'ok': True})

        cmd, arg = parse_cmd(message_text)
        supported = {"/ytdlp":"ytdlp", "/360":"ytdlp", "/audio":"audio"}

        if cmd in supported:
            url = first_url(arg)
            if not url:
                tg_send_message_api(token, chat_id, f"🔗 ব্যবহার: {cmd} <youtube-url>")
                return jsonify({'ok': True})
            mode = supported[cmd]
            tg_send_message_api(token, chat_id, f"⏳ প্রসেসিং শুরু… ({mode})")
            threading.Thread(target=process_and_upload, args=(token, chat_id, url, mode), daemon=True).start()
            return jsonify({'ok': True})

        # fallback: if message is URL
        url = first_url(message_text)
        if url:
            tg_send_message_api(token, chat_id, "⏳ প্রসেসিং শুরু… (ytdlp)")
            threading.Thread(target=process_and_upload, args=(token, chat_id, url, "ytdlp"), daemon=True).start()
            return jsonify({'ok': True})

        tg_send_message_api(token, chat_id, "❓ কমান্ড/লিংক বুঝিনি। /help দেখুন।")
        return jsonify({'ok': True})

    except Exception as e:
        logger.exception("Error: %s", e)
        return jsonify({'error':'Processing failed'}), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port, debug=False)
