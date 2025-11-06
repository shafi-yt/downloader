import os
import re
import time
import json
import socket
import urllib.parse
import ipaddress
import tempfile
import threading
import logging

from flask import Flask, request, jsonify
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from urllib.parse import urlparse, parse_qs

# ----------------------------
# Logging
# ----------------------------
logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("stream-dl")

# ----------------------------
# Flask app
# ----------------------------
app = Flask(__name__)

# ----------------------------
# Globals / Config
# ----------------------------
ALLOWED_SCHEMES = {"http", "https"}
MAX_BYTES = int(os.getenv("MAX_BYTES_MB", "1900")) * 1024 * 1024  # ~1.9GB default
MAX_CONCURRENT = int(os.getenv("MAX_CONCURRENT_DOWNLOADS", "3"))
DL_SEM = threading.Semaphore(MAX_CONCURRENT)

# Progress memory (lightweight)
download_progress = {}  # chat_id -> dict

# ----------------------------
# Helpers: Network safety
# ----------------------------
def is_private_ip(host: str) -> bool:
    """Resolve host to IPs and check if any is private/loopback/etc."""
    try:
        infos = socket.getaddrinfo(host, None)
        for family, _, _, _, sockaddr in infos:
            ip = sockaddr[0]
            ip_obj = ipaddress.ip_address(ip)
            if (
                ip_obj.is_private
                or ip_obj.is_loopback
                or ip_obj.is_reserved
                or ip_obj.is_link_local
                or ip_obj.is_multicast
            ):
                return True
        return False
    except Exception:
        # If resolution fails, be safe and block.
        return True


def validate_url_safe(url: str) -> bool:
    try:
        u = urllib.parse.urlparse(url)
        if u.scheme not in ALLOWED_SCHEMES or not u.netloc:
            return False
        host = u.hostname
        if not host or is_private_ip(host):
            return False
        return True
    except Exception:
        return False


# ----------------------------
# HTTP Session factory
# ----------------------------
def get_streaming_headers(referer: str | None = None):
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept": "*/*",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "identity",
        "Connection": "keep-alive",
        "DNT": "1",
    }
    if referer:
        ru = urllib.parse.urlparse(referer)
        headers["Referer"] = referer
        headers["Origin"] = f"{ru.scheme}://{ru.netloc}"
    return headers


def make_session():
    s = requests.Session()
    retry = Retry(
        total=5, connect=3, read=3,
        backoff_factor=0.6,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["HEAD", "GET", "POST"]
    )
    adapter = HTTPAdapter(max_retries=retry, pool_connections=50, pool_maxsize=100)
    s.mount("http://", adapter)
    s.mount("https://", adapter)
    return s


# ----------------------------
# URL helpers
# ----------------------------
def is_streaming_url(url: str) -> bool:
    streaming_indicators = [
        "videoplayback",
        "googlevideo.com",
        "stream",
        "m3u8",
        "mpd",
        "segment",
        "chunk",
    ]
    ul = url.lower()
    return any(ind in ul for ind in streaming_indicators)


def is_manifest(url: str) -> bool:
    ul = url.lower()
    return (ul.endswith(".m3u8") or ".m3u8" in ul or ul.endswith(".mpd") or ".mpd" in ul)


def is_ip_bound_googlevideo(url: str) -> bool:
    try:
        q = parse_qs(urlparse(url).query)
        # ip=, spc=, expire= থাকলে সাধারণত সাইনেচার time/IP bound
        return any(k in q for k in ("ip", "spc", "expire"))
    except Exception:
        return False


# ----------------------------
# Google Video special headers
# ----------------------------
ANDROID_YT_UA = (
    "com.google.android.youtube/19.32.39 (Linux; U; Android 13) gzip, ExoPlayerLib/2.19"
)

def build_googlevideo_headers(url: str):
    """
    Google Video লিংকের জন্য একটু 'realistic' হেডার।
    """
    h = get_streaming_headers(referer="https://www.youtube.com/")
    h["User-Agent"] = ANDROID_YT_UA
    h["Origin"] = "https://www.youtube.com"
    h["Sec-Fetch-Dest"] = "video"
    h["Sec-Fetch-Mode"] = "no-cors"
    h["Sec-Fetch-Site"] = "cross-site"
    h["Range"] = "bytes=0-"
    return h


# ----------------------------
# Telegram helpers
# ----------------------------
def safe_telegram_post(session, url, **kwargs):
    try:
        resp = session.post(url, timeout=(5, 20), **kwargs)
        data = None
        if "application/json" in resp.headers.get("content-type", ""):
            data = resp.json()
        return resp, data
    except Exception as e:
        logger.warning(f"Telegram post parse error: {e}")
        return None, None


def send_telegram_message_payload(chat_id, text, parse_mode="HTML", reply_markup=None):
    p = {
        "method": "sendMessage",
        "chat_id": chat_id,
        "text": text,
        "parse_mode": parse_mode,
    }
    if reply_markup:
        p["reply_markup"] = reply_markup
    return p


def send_progress_update(session, chat_id, message_id, token, progress, status):
    try:
        progress_bar = "🟩" * (progress // 10) + "⬜" * (10 - (progress // 10))
        text = f"📥 {status}\n\n{progress_bar} {progress}%"
        url = f"https://api.telegram.org/bot{token}/editMessageText"
        data = {
            "chat_id": chat_id,
            "message_id": message_id,
            "text": text
        }
        session.post(url, json=data, timeout=(5, 10))
    except Exception as e:
        logger.error(f"Progress update error: {e}")


def send_telegram_message_direct(session, chat_id, token, text, parse_mode="HTML"):
    try:
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        data = {
            "chat_id": chat_id,
            "text": text[:1024],  # safety
            "parse_mode": parse_mode
        }
        resp, j = safe_telegram_post(session, url, json=data)
        return j
    except Exception as e:
        logger.error(f"Direct message error: {e}")
        return None


def send_video_to_telegram(session, chat_id, video_path, original_url, token):
    try:
        url = f"https://api.telegram.org/bot{token}/sendVideo"
        file_size = os.path.getsize(video_path)
        logger.info(f"📤 Uploading video: {file_size} bytes")
        timeout = 300
        with open(video_path, "rb") as vf:
            files = {"video": vf}
            data = {
                "chat_id": chat_id,
                "caption": f"🎥 Downloaded Video\n\n🔗 Source: {original_url[:100]}...",
                "parse_mode": "HTML",
                "supports_streaming": True
            }
            resp = session.post(url, files=files, data=data, timeout=timeout)
        logger.info(f"📤 Upload response: {resp.status_code}")
        if resp.status_code == 200:
            return True
        else:
            logger.error(f"❌ Video upload failed: {resp.text}")
            return send_as_document(session, chat_id, video_path, original_url, token)
    except Exception as e:
        logger.error(f"❌ Video upload error: {e}")
        return send_as_document(session, chat_id, video_path, original_url, token)


def send_as_document(session, chat_id, file_path, original_url, token):
    try:
        url = f"https://api.telegram.org/bot{token}/sendDocument"
        with open(file_path, "rb") as f:
            files = {"document": f}
            data = {
                "chat_id": chat_id,
                "caption": f"📁 Video File\n\n🔗 Source: {original_url[:100]}...",
                "parse_mode": "HTML"
            }
            resp = session.post(url, files=files, data=data, timeout=300)
        return resp.status_code == 200
    except Exception as e:
        logger.error(f"❌ Document upload failed: {e}")
        return False


# ----------------------------
# Probing & Download
# ----------------------------
def test_streaming_url(session, url, referer=None):
    try:
        # googlevideo হলে স্পেশাল হেডার, নইলে জেনেরিক
        if "googlevideo.com" in url:
            headers = build_googlevideo_headers(url)
        else:
            headers = get_streaming_headers(referer)

        probe_headers = dict(headers)
        probe_headers["Range"] = "bytes=0-1023"

        r = session.get(url, headers=probe_headers, timeout=(10, 20), stream=True, allow_redirects=True)
        if r.status_code in (200, 206):
            return {
                "success": True,
                "url": url,
                "content_type": r.headers.get("content-type", ""),
                "content_length": r.headers.get("content-length"),
                "headers": dict(r.headers),
            }
        elif r.status_code == 403 and "googlevideo.com" in url:
            reason = "IP-bound/expired Google Video URL (403). Send a fresh link."
            return {"success": False, "error": "403 Forbidden", "details": reason}
        return {
            "success": False,
            "error": f"HTTP {r.status_code}",
            "details": "Streaming server rejected the probe",
        }
    except requests.exceptions.Timeout:
        return {"success": False, "error": "Connection timeout", "details": "Streaming server timeout"}
    except requests.exceptions.ConnectionError:
        return {"success": False, "error": "Connection failed", "details": "Cannot connect to streaming server"}
    except Exception as e:
        return {"success": False, "error": str(e), "details": "Unexpected error during probe"}


def detect_extension_from_ctype(ctype: str) -> str:
    c = (ctype or "").lower()
    if "webm" in c:
        return ".webm"
    if "x-matroska" in c or "mkv" in c:
        return ".mkv"
    if "quicktime" in c or "mov" in c:
        return ".mov"
    if "mp4" in c or "mpeg4" in c or "video/" in c:
        return ".mp4"
    return ".mp4"


def stream_to_file(session, stream_url, chat_id, message_id, token, referer=None):
    # হেডার বাছাই
    if "googlevideo.com" in stream_url:
        headers = build_googlevideo_headers(stream_url)
    else:
        headers = get_streaming_headers(referer)
        headers["Range"] = "bytes=0-"

    r = session.get(stream_url, headers=headers, stream=True, timeout=(15, 180))
    if r.status_code == 403 and "googlevideo.com" in stream_url:
        send_telegram_message_direct(session, chat_id, token,
            "❌ 403 Forbidden.\n\n🔒 This Google Video link is likely IP-bound or expired.\n"
            "Please provide a fresh link generated for this server, or another direct video URL.")
        raise requests.HTTPError("403 Forbidden (likely IP-bound)")

    r.raise_for_status()

    total = r.headers.get("content-length")
    try:
        total = int(total) if total is not None else None
    except Exception:
        total = None

    ext = detect_extension_from_ctype(r.headers.get("content-type", ""))

    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=ext)
    path = tmp.name

    downloaded = 0
    last_push = 0.0
    start = time.time()

    for chunk in r.iter_content(chunk_size=1024 * 256):  # 256KB
        if not chunk:
            continue
        tmp.write(chunk)
        downloaded += len(chunk)

        if downloaded > MAX_BYTES:
            tmp.close()
            os.unlink(path)
            raise Exception("File exceeds size limit for Telegram.")

        now = time.time()
        if now - last_push >= 2:  # debounce ~2s
            if total:
                pct = min(99, int(downloaded * 100 / total))
                speed = downloaded / max(1, now - start)
                send_progress_update(
                    session, chat_id, message_id, token, pct,
                    f"Streaming: {downloaded/(1024*1024):.1f}MB / {total/(1024*1024):.1f}MB ({speed/1024/1024:.1f} MB/s)"
                )
            else:
                pct = min(99, int((now - start) % 100))
                send_progress_update(
                    session, chat_id, message_id, token, pct,
                    f"Streaming: {downloaded/(1024*1024):.1f}MB (size unknown)"
                )
            last_push = now

    tmp.close()
    return path, total


def handle_streaming_url(session, url, referer=None):
    try:
        if is_manifest(url):
            return {
                "success": False,
                "error": "Stream manifest (.m3u8/.mpd) not supported on this build.",
                "details": "Transmuxing requires ffmpeg which is not enabled."
            }

        # IP-bound googlevideo হলে আগেই সতর্ক করি (তবু probe করব)
        if "googlevideo.com" in url and is_ip_bound_googlevideo(url):
            logger.info("Likely IP-bound Google Video URL; will probe.")

        probe = test_streaming_url(session, url, referer=referer)
        if probe.get("success"):
            return {
                "success": True,
                "download_url": url,
                "original_url": url,
                "type": "streaming",
                "content_type": probe.get("content_type"),
                "content_length": probe.get("content_length"),
                "is_streaming": True,
            }
        else:
            return {
                "success": False,
                "error": probe.get("error", "Probe failed"),
                "details": probe.get("details", "Unknown")
            }
    except Exception as e:
        logger.error(f"Streaming URL handling error: {e}")
        return {
            "success": False,
            "error": f"Streaming processing failed: {str(e)}",
            "details": "Cannot process URL"
        }


def get_video_info(session, url):
    try:
        if not validate_url_safe(url):
            return {"success": False, "error": "Unsafe or invalid URL (SSRF protection)"}

        if is_streaming_url(url):
            return handle_streaming_url(session, url)

        # Try HEAD to detect direct video
        headers = get_streaming_headers()
        try:
            r = session.head(url, headers=headers, timeout=(10, 20), allow_redirects=True)
            if r.status_code == 200:
                ctype = r.headers.get("content-type", "")
                clen = r.headers.get("content-length", 0)
                if "video" in (ctype or ""):
                    return {
                        "success": True,
                        "download_url": url,
                        "original_url": url,
                        "type": "direct",
                        "content_type": ctype,
                        "content_length": clen,
                    }
        except Exception as e:
            logger.warning(f"Direct check failed: {e}")

        # Else treat as streaming
        return handle_streaming_url(session, url)
    except Exception as e:
        return {"success": False, "error": f"URL processing error: {str(e)}"}


# ----------------------------
# Download Thread
# ----------------------------
def start_download_thread(chat_id, video_url, message_id, token):
    def download_job():
        acquired = DL_SEM.acquire(blocking=False)
        local_session = make_session()

        if not acquired:
            send_telegram_message_direct(local_session, chat_id, token,
                "⏳ Too many downloads in progress. Please try again shortly.")
            return

        try:
            logger.info(f"🎬 Processing URL: {video_url}")
            send_telegram_message_direct(local_session, chat_id, token, "🔍 Analyzing URL...")

            video_info = get_video_info(local_session, video_url)
            if not video_info.get("success"):
                extra = ""
                if ("googlevideo.com" in video_url) and (
                    "403" in str(video_info.get("error","")) or "IP-bound" in str(video_info.get("details",""))
                ):
                    extra = ("\n\n💡 Tip: Many Google Video links are bound to the original client IP and expire quickly. "
                             "Please fetch a fresh link (from the same server) or use a different direct video URL.")
                msg = f"""❌ <b>Could not process URL</b>

🔍 <b>Details:</b>
• <b>URL:</b> <code>{video_url[:100]}...</code>
• <b>Error:</b> {video_info.get('error', 'Unknown')}
• <b>Info:</b> {video_info.get('details','')}{extra}
"""
                send_telegram_message_direct(local_session, chat_id, token, msg)
                return

            vtype = "Streaming" if video_info.get("is_streaming") else "Direct"
            try:
                clen = int(video_info.get("content_length", 0)) if video_info.get("content_length") else None
            except Exception:
                clen = None
            size_mb = f"{clen/(1024*1024):.1f} MB" if clen else "Unknown"

            info_text = f"""✅ <b>URL Accepted</b>

📹 <b>Information:</b>
• <b>Type:</b> {vtype}
• <b>Content Type:</b> {video_info.get('content_type', 'Unknown')}
• <b>File Size:</b> {size_mb}

⏳ <b>Starting download...</b>
"""
            send_telegram_message_direct(local_session, chat_id, token, info_text)

            # Download
            video_path = None
            try:
                video_path, _ = stream_to_file(local_session, video_info["download_url"], chat_id, message_id, token)
            except requests.exceptions.Timeout:
                send_telegram_message_direct(local_session, chat_id, token, "❌ Download timeout.")
                return
            except requests.exceptions.ChunkedEncodingError:
                send_telegram_message_direct(local_session, chat_id, token, "❌ Streaming connection interrupted.")
                return
            except Exception as e:
                logger.error(f"Streaming download error: {e}")
                send_telegram_message_direct(local_session, chat_id, token, f"❌ Download error: {str(e)}")
                return

            if not video_path or not os.path.exists(video_path):
                send_telegram_message_direct(local_session, chat_id, token,
                    "❌ Download failed. Possible reasons:\n• URL expired\n• Server restrictions\n• Network issues\n\nTry a fresh URL.")
                return

            send_progress_update(local_session, chat_id, message_id, token, 100, "Uploading to Telegram...")
            ok = send_video_to_telegram(local_session, chat_id, video_path, video_url, token)

            # Delete progress message
            try:
                del_url = f"https://api.telegram.org/bot{token}/deleteMessage"
                local_session.post(del_url, json={"chat_id": chat_id, "message_id": message_id}, timeout=(5, 10))
            except Exception:
                pass

            if ok:
                send_telegram_message_direct(local_session, chat_id, token, "✅ <b>Video successfully sent!</b>")
            else:
                send_telegram_message_direct(local_session, chat_id, token, "❌ <b>Upload failed.</b> File may be too large or corrupted.")
        except Exception as e:
            logger.error(f"Download thread error: {e}")
            send_telegram_message_direct(local_session, chat_id, token, f"❌ Processing Failed\n\n<b>Error:</b> {str(e)}")
        finally:
            if chat_id in download_progress:
                try:
                    del download_progress[chat_id]
                except Exception:
                    pass
            try:
                pass
            finally:
                if acquired:
                    DL_SEM.release()

    t = threading.Thread(target=download_job, daemon=True)
    t.start()


# ----------------------------
# Routes
# ----------------------------
@app.route("/", methods=["GET", "POST"])
def handle_request():
    try:
        # Token may come via query or env for convenience
        token = request.args.get("token") or os.getenv("TELEGRAM_BOT_TOKEN")
        if not token:
            return jsonify({
                "error": "Token required",
                "solution": "Add ?token=YOUR_BOT_TOKEN to URL or set TELEGRAM_BOT_TOKEN env var."
            }), 400

        if request.method == "GET":
            return jsonify({
                "status": "Streaming Video Downloader Bot is running",
                "features": "Supports streaming URLs, direct videos, and Google Video links (no HLS/DASH transmux).",
                "token_received": True
            })

        if request.method == "POST":
            update = request.get_json(silent=True)
            if not update:
                return jsonify({"error": "Invalid JSON data"}), 400

            chat_id = None
            message_text = ""
            message_id = None

            if "message" in update:
                msg = update["message"]
                chat_id = msg["chat"]["id"]
                message_text = msg.get("text", "") or ""
                message_id = msg.get("message_id")
            else:
                return jsonify({"ok": True})

            local_session = make_session()

            if message_text.startswith("/start"):
                welcome_text = """
🎬 <b>Streaming Video Downloader Bot</b>

I can download videos from streaming URLs and direct links!

📌 <b>How to use:</b>
Send me any public video URL (http/https)

🔗 <b>Supported:</b>
• Google Video links
• Streaming URLs
• Direct video links
• (No HLS/DASH transmux in this build)

⚡ <b>Commands:</b>
/start - Show this help
/download [URL] - Download from URL

📝 <b>Examples:</b>
<code>https://googlevideo.com/videoplayback?...</code>
<code>/download https://example.com/video.mp4</code>

⚠️ <b>Note:</b> Some URLs may expire quickly. Private/Local URLs are blocked for safety.
                """.strip()
                return jsonify(send_telegram_message_payload(chat_id, welcome_text))

            elif message_text.startswith("/download"):
                parts = message_text.split(" ", 1)
                if len(parts) < 2:
                    return jsonify(send_telegram_message_payload(
                        chat_id, "❌ <b>Usage:</b> <code>/download URL</code>"
                    ))
                video_url = parts[1].strip()
                return process_video_download(local_session, chat_id, video_url, token)

            elif message_text.strip().startswith("http"):
                return process_video_download(local_session, chat_id, message_text.strip(), token)

            else:
                return jsonify(send_telegram_message_payload(
                    chat_id, "❌ Please send a valid URL starting with http:// or https://"
                ))

    except Exception as e:
        logger.error(f"Main handler error: {e}")
        return jsonify({"error": "Processing failed", "details": str(e)}), 500


def process_video_download(session, chat_id, video_url, token):
    try:
        if not validate_url_safe(video_url):
            return jsonify(send_telegram_message_payload(
                chat_id, "❌ Unsafe or invalid URL. Public http/https only."
            ))

        processing_msg = send_telegram_message_payload(
            chat_id, f"🔍 Processing URL...\n\n<code>{video_url[:100]}...</code>"
        )
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        resp = session.post(url, json=processing_msg, timeout=(5, 10))
        if resp.status_code == 200:
            j = resp.json()
            processing_msg_id = j["result"]["message_id"]
            start_download_thread(chat_id, video_url, processing_msg_id, token)
            return jsonify({"ok": True})
        else:
            return jsonify(send_telegram_message_payload(
                chat_id, "❌ Failed to start download process."
            ))
    except Exception as e:
        logger.error(f"Error processing download: {e}")
        return jsonify(send_telegram_message_payload(
            chat_id, f"❌ Error: {str(e)}"
        ))


@app.route("/health", methods=["GET"])
def health_check():
    return jsonify({
        "status": "healthy",
        "service": "Streaming Video Downloader",
        "timestamp": time.time(),
        "active_downloads": MAX_CONCURRENT - DL_SEM._value  # approximate
    })


if __name__ == "__main__":
    port = int(os.getenv("PORT", "10000"))
    app.run(host="0.0.0.0", port=port, debug=False)