from flask import Flask, request, jsonify
import os, re, tempfile, threading, subprocess, shlex, glob, logging, json, requests

# ---------- Logging ----------
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger("app")

app = Flask(__name__)

# ---------- Helpers ----------
YOUTUBE_RE = re.compile(r'(https?://)?(www\.)?(youtube\.com|youtu\.be)/\S+', re.I)
TARGET_LIMIT_MB = 50
HARD_LIMIT_BYTES = 48 * 1024 * 1024  # buffer under 50MB

def webhook_reply_send_message(chat_id, text, parse_mode=None):
    """Return a Telegram-style JSON to execute sendMessage inline (fallback)."""
    payload = {
        'method': 'sendMessage',
        'chat_id': chat_id,
        'text': text
    }
    if parse_mode:
        payload['parse_mode'] = parse_mode
    return payload

def tg_api_base(bot_token: str) -> str:
    return f"https://api.telegram.org/bot{bot_token}"

def tg_send_message_api(bot_token: str, chat_id: int, text: str, **kwargs):
    data = {"chat_id": chat_id, "text": text, **kwargs}
    try:
        r = requests.post(f"{tg_api_base(bot_token)}/sendMessage", json=data, timeout=30)
        logger.info("sendMessage status=%s body=%s", getattr(r, 'status_code', None), getattr(r, 'text', None)[:400])
        return r
    except Exception as e:
        logger.exception("sendMessage failed: %s", e)

def tg_send_video_api(bot_token: str, chat_id: int, file_path: str, caption: str = ""):
    with open(file_path, "rb") as f:
        files = {"video": (os.path.basename(file_path), f, "video/mp4")}
        data = {"chat_id": chat_id, "caption": caption}
        r = requests.post(f"{tg_api_base(bot_token)}/sendVideo", files=files, data=data, timeout=600)
        logger.info("sendVideo status=%s body=%s", getattr(r, 'status_code', None), getattr(r, 'text', None)[:400])
        return r

def tg_send_audio_api(bot_token: str, chat_id: int, file_path: str, caption: str = ""):
    with open(file_path, "rb") as f:
        files = {"audio": (os.path.basename(file_path), f)}
        data = {"chat_id": chat_id, "caption": caption}
        r = requests.post(f"{tg_api_base(bot_token)}/sendAudio", files=files, data=data, timeout=600)
        logger.info("sendAudio status=%s body=%s", getattr(r, 'status_code', None), getattr(r, 'text', None)[:400])
        return r

def safe_filename(s: str) -> str:
    return re.sub(r'[^A-Za-z0-9\-\.\_\s]+', '_', s).strip()[:120] or "video"

def guess_file_by_ext(tmpdir: str, exts):
    candidates = []
    for ext in exts:
        candidates.extend(glob.glob(os.path.join(tmpdir, f"*.{ext}")))
    if not candidates:
        return None
    return max(candidates, key=os.path.getsize)

def guess_video_file(tmpdir: str):
    return guess_file_by_ext(tmpdir, ["mp4", "mkv", "webm", "mov"])

def guess_audio_file(tmpdir: str):
    return guess_file_by_ext(tmpdir, ["m4a", "mp3", "opus", "aac"])


# ---------- YouTube anti-bot helpers ----------
COOKIES_B64 = os.getenv("YTDLP_COOKIES_B64", "").strip()

def get_cookiefile_path():
    \"\"\"Write Netscape-format cookies from base64 env to a temp file, return path or None.\"\"\"
    global COOKIES_B64
    if not COOKIES_B64:
        return None
    try:
        import tempfile, base64
        raw = base64.b64decode(COOKIES_B64.encode("utf-8"))
        # Persist for process lifetime
        path = os.path.join(tempfile.gettempdir(), "cookies_youtube.txt")
        if not os.path.exists(path) or os.path.getsize(path) != len(raw):
            with open(path, "wb") as f:
                f.write(raw)
        return path
    except Exception as e:
        logger.exception("Failed to load cookies from YTDLP_COOKIES_B64: %s", e)
        return None

# ---------- yt-dlp CLI ----------
def ytdlp_cli_cmd(url: str, outdir: str, title_hint="youtube", fmt=None, audio=False):
    outtmpl = os.path.join(outdir, safe_filename(title_hint) + ".%(ext)s")
    # Use valid format filters; avoid regex operators that changed in newer yt-dlp
    default_video_fmt = (
        "best[ext=mp4][vcodec^=avc][filesize<48M]"
        "/best[ext=mp4][height<=480][filesize<48M]"
        "/best[ext=mp4][height<=720][filesize<48M]"
        "/best[ext=mp4][filesize<48M]"
        "/best[filesize<48M]"
    )
    if audio:
        fmt = fmt or "bestaudio[ext=m4a][filesize<48M]/bestaudio[filesize<48M]"
    else:
        fmt = fmt or default_video_fmt

    cookiefile = get_cookiefile_path()
    base = [
        "yt-dlp",
        "-o", outtmpl,
        "-f", fmt,
        "--max-filesize", "48M",
        "--no-playlist",
        "--restrict-filenames",
        url
    ]
    # Prefer Android client to reduce bot checks
    base.extend(["--extractor-args", "youtube:player_client=android"])
    if cookiefile:
        base.extend(["--cookies", cookiefile])
    return base

def run_cli(cmd, cwd):
    logger.info("Running: %s", " ".join(shlex.quote(c) for c in cmd))
    cp = subprocess.run(cmd, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    logger.info(cp.stdout)
    if cp.returncode != 0:
        raise RuntimeError("yt-dlp CLI failed")

# ---------- Download methods ----------
def download_with_ytdlp_cli(url: str, outdir: str, fmt=None):
    run_cli(ytdlp_cli_cmd(url, outdir, "youtube", fmt=fmt), outdir)
    return guess_video_file(outdir)

def download_audio_cli(url: str, outdir: str):
    run_cli(ytdlp_cli_cmd(url, outdir, "audio", audio=True), outdir)
    return guess_audio_file(outdir)

def download_with_ytdlp_api(url: str, outdir: str):
    import yt_dlp
    outtmpl = os.path.join(outdir, "youtube.%(ext)s")
    ydl_opts = {
        "outtmpl": outtmpl,
        "noplaylist": True,
        "restrictfilenames": True,
        "format": "best[ext=mp4][filesize<48M]/best[filesize<48M]",
        "max_filesize": HARD_LIMIT_BYTES,
        "merge_output_format": "mp4",
        "postprocessors": [],
        "cookiefile": get_cookiefile_path(),
        "extractor_args": {"youtube": {"player_client": ["android"]}},
        "quiet": True,
        "no_warnings": True,
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([url])
    return guess_video_file(outdir)

def download_with_pytube(url: str, outdir: str):
    try:
        from pytubefix import YouTube
    except Exception:
        from pytube import YouTube  # fallback
    yt = YouTube(url, use_po_token=True)
    title = safe_filename(getattr(yt, "title", None) or "youtube")
    stream = (yt.streams.filter(progressive=True, file_extension="mp4", res="480p").first()
              or yt.streams.filter(progressive=True, file_extension="mp4", res="360p").first()
              or yt.streams.filter(progressive=True, file_extension="mp4").order_by("filesize").first())
    if not stream:
        raise RuntimeError("No suitable progressive stream found")
    fp = stream.download(output_path=outdir, filename=title + ".mp4")
    if os.path.getsize(fp) > HARD_LIMIT_BYTES:
        raise RuntimeError("File exceeds ~50MB limit")
    return fp

# ---------- Worker ----------
def process_and_upload(bot_token: str, chat_id: int, url: str, mode: str):
    with tempfile.TemporaryDirectory() as tmp:
        try:
            if mode == "ytdlp_cli":
                path = download_with_ytdlp_cli(url, tmp)
            elif mode == "ytdlp_api":
                path = download_with_ytdlp_api(url, tmp)
            elif mode == "pytube":
                path = download_with_pytube(url, tmp)
            elif mode == "audio":
                apath = download_audio_cli(url, tmp)
                if not apath:
                    raise RuntimeError("Audio not found")
                if os.path.getsize(apath) > HARD_LIMIT_BYTES:
                    raise RuntimeError("Audio exceeds ~50MB")
                tg_send_audio_api(bot_token, chat_id, apath, caption="🎧 Extracted audio")
                return
            elif mode == "360":
                fmt = "best[ext=mp4][height<=360][filesize<48M]/best[ext=mp4][filesize<48M]"
                path = download_with_ytdlp_cli(url, tmp, fmt=fmt)
            elif mode == "720":
                fmt = "best[ext=mp4][height<=720][filesize<48M]/best[ext=mp4][filesize<48M]"
                path = download_with_ytdlp_cli(url, tmp, fmt=fmt)
            elif mode == "best":
                path = download_with_ytdlp_cli(url, tmp, fmt=None)
            else:
                path = download_with_ytdlp_cli(url, tmp)

            if not path:
                tg_send_message_api(bot_token, chat_id, "⚠️ ফাইল খুঁজে পাইনি। অন্য মেথড চেষ্টা করুন (/ytdlpa, /pytube).")
                return

            size_mb = os.path.getsize(path) / (1024 * 1024)
            if size_mb > (TARGET_LIMIT_MB - 0.5):
                tg_send_message_api(bot_token, chat_id, f"⚠️ ফাইল {size_mb:.1f}MB — সীমা পার হচ্ছে। `/360` বা `/audio` চেষ্টা করুন।")
                return

            tg_send_video_api(bot_token, chat_id, path, caption=f"📥 {mode} ▶ Telegram")
        except Exception as e:
            logger.exception("Processing error")
            tg_send_message_api(bot_token, chat_id, f"❌ ব্যর্থ: {e}")

# ---------- Command help ----------
HELP_TEXT = (
    "👋 লিংক দিন এই কমান্ডগুলোর সাথে:\n"
    "/ytdlp <url> – yt-dlp (CLI), ~50MB MP4\n"
    "/ytdlpa <url> – yt_dlp Python API\n"
    "/pytube <url> – pytube/pytubefix fallback\n"
    "/audio <url> – m4a/mp3 (অডিও)\n"
    "/360 <url> – 360p টার্গেট\n"
    "/720 <url> – 720p টার্গেট\n"
    "/best <url> – সীমার মধ্যে সেরা সম্ভব\n\n"
    "ℹ️ বড় ভিডিও হলে সীমায় আটকাতে পারে। তখন /360 বা /audio ব্যবহার করুন।"
)

def parse_cmd(text: str):
    if not text:
        return None, None
    parts = text.split(maxsplit=1)
    cmd = parts[0].lower()
    arg = parts[1].strip() if len(parts) > 1 else ""
    return cmd, arg

def first_url(s: str):
    m = YOUTUBE_RE.search(s or "")
    return m.group(0) if m else None

# ---------- Single endpoint (GET/POST) with ?token=BOT_TOKEN ----------
@app.route('/', methods=['GET', 'HEAD', 'POST'])
def handle_request():
    try:
        token = request.args.get('token')

        # Health checks
        if request.method in ('GET', 'HEAD'):
            return jsonify({'ok': True, 'service': 'telegram-ytdlp-bot'})

        # For incoming updates we require ?token= to know which bot to call
        if not token:
            return jsonify({
                'error': 'Token required',
                'solution': 'Add ?token=YOUR_BOT_TOKEN to webhook URL'
            }), 400

        # POST update
        update = request.get_json(silent=True)
        if not update:
            return jsonify({'error': 'Invalid JSON data'}), 400

        logger.info("Update received: %s", json.dumps(update)[:2000])

        chat_id = None
        message_text = ''
        user_info = {}

        if 'message' in update:
            msg = update['message']
        elif 'edited_message' in update:
            msg = update['edited_message']
        else:
            # ignore channel_post etc.
            return jsonify({'ok': True})

        chat = msg.get('chat') or {}
        chat_id = chat.get('id')
        message_text = (msg.get('text') or "").strip()
        user_info = msg.get('from', {})

        if not chat_id:
            return jsonify({'error': 'Chat ID not found'}), 400

        # Commands with optional @Bot suffix
        if re.match(r'^/start(?:@\w+)?\b', message_text):
            first_name = user_info.get('first_name', 'অজানা')
            last_name = user_info.get('last_name', '')
            username = user_info.get('username', 'অজানা')
            user_id = user_info.get('id', 'অজানা')
            language_code = user_info.get('language_code', 'অজানা')
            full_name = (first_name + (" " + last_name if last_name else ""))
            profile_text = (
                "🤖 আপনার প্রোফাইল তথ্য\n\n"
                f"👤 পূর্ণ নাম: {full_name}\n"
                f"• ইউজারনেম: @{username}\n"
                f"• ইউজার আইডি: {user_id}\n"
                f"• ভাষা: {language_code}\n\n"
                f"💬 চ্যাট আইডি: {chat_id}\n\n"
                "🎬 ব্যবহার:\n"
                "/ytdlp <url>, /ytdlpa <url>, /pytube <url>, /audio <url>, /360 <url>, /720 <url>, /best <url>\n"
            )
            tg_send_message_api(token, chat_id, profile_text)
            return jsonify({'ok': True})

        if re.match(r'^/help(?:@\w+)?\b', message_text):
            tg_send_message_api(token, chat_id, HELP_TEXT)
            return jsonify({'ok': True})

        # Router
        cmd, arg = parse_cmd(message_text)
        supported = {
            "/ytdlp": "ytdlp_cli", "/ytdlpa": "ytdlp_api",
            "/pytube": "pytube", "/audio": "audio",
            "/360": "360", "/720": "720", "/best": "best"
        }

        if cmd in supported:
            url = first_url(arg)
            if not url:
                tg_send_message_api(token, chat_id, f"🔗 ব্যবহার: {cmd} <youtube-url>")
                return jsonify({'ok': True})
            tg_send_message_api(token, chat_id, f"⏳ প্রসেসিং শুরু… ({supported[cmd]})")
            threading.Thread(target=process_and_upload, args=(token, chat_id, url, supported[cmd]), daemon=True).start()
            return jsonify({'ok': True})

        # If just a YouTube URL, default to ytdlp_cli
        url = first_url(message_text)
        if url:
            tg_send_message_api(token, chat_id, "⏳ প্রসেসিং শুরু… (ytdlp_cli)")
            threading.Thread(target=process_and_upload, args=(token, chat_id, url, "ytdlp_cli"), daemon=True).start()
            return jsonify({'ok': True})

        # Fallback
        tg_send_message_api(token, chat_id, "❓ কমান্ড/লিংক বুঝিনি। /help দেখুন।")
        return jsonify({'ok': True})

    except Exception as e:
        logger.exception("Error: %s", e)
        return jsonify({'error': 'Processing failed'}), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port, debug=False)
