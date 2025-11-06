# Streaming Video Downloader (Render + Telegram Bot)

A minimal streaming video downloader bot that **does not use `yt-dlp`**.  
It supports direct/streaming links (e.g., `googlevideo.com/videoplayback`) and sends the file to Telegram.

> **Note:** HLS/DASH manifests (`.m3u8`/`.mpd`) are **not** handled in this build (no ffmpeg on Render).  
> For those, add an ffmpeg worker or use a different deployment target.

## Features
- SSRF-safe URL validation (blocks private/loopback IPs)
- Per-thread `requests.Session()` with retries & backoff
- Size cap (default ~1.9GB) to fit Telegram upload limits
- Debounced progress updates (reduce API spam)
- Concurrency limit (default 3 downloads)
- Render/GitHub friendly (gunicorn, `render.yaml`, `Procfile`)

## Deploy on Render
1. Fork this repo to your GitHub.
2. On Render: **New Web Service** → Connect repo.
3. Use `render.yaml` or set:
   - **Build Command:** `pip install -r requirements.txt`
   - **Start Command:** `gunicorn -w 1 -k gthread -t 180 app:app`
4. Add env vars:
   - `TELEGRAM_BOT_TOKEN` (required if you don’t pass `?token=` in webhook URL)
   - `MAX_BYTES_MB` (optional, default 1900)
   - `MAX_CONCURRENT_DOWNLOADS` (optional)
   - `LOG_LEVEL` (optional)

## Telegram Setup
- Set webhook to your Render URL: