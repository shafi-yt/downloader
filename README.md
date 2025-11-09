# Telegram Webhook Bot (Flask) — yt-dlp + pytube + pydub

Features:
- Flask webhook endpoint (`/`) for Telegram updates
- Inline keyboard to pick engine (yt-dlp / pytube), mode (Video/Audio), quality (best/1080p/720p/480p/360p)
- Audio-only with MP3 (needs ffmpeg) via yt-dlp postprocessor or pydub/ffmpeg
- Playlist download (yt-dlp)
- Per-chat settings in memory
- Progress messages (coarse)
- Document upload back to Telegram (files under ~2GB)

## Env
- `BOT_TOKEN` (required if not using querystring)
- `DOWNLOAD_DIR` (default `downloads`)
- `MAX_FILE_MB` (default `1950`)

## Webhook set
```
https://api.telegram.org/bot<token>/setWebhook?url=https://YOUR-DOMAIN?token=<token>
```

## Run
```
pip install -r requirements.txt
python app.py
```
