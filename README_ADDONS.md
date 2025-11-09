# Telegram Downloader Bot — yt-dlp + pytube Add‑ons

This drop-in add‑on gives you both **yt-dlp** and **pytube** download options, plus:
- Inline keyboard to choose **engine** (yt-dlp / pytube)
- **Video quality** selector (best / 1080p / 720p / 480p / 360p)
- **Audio‑only** (MP3 / M4A) with auto‑fallback if ffmpeg is unavailable
- **Playlist** support (yt-dlp engine)
- Per‑chat default **settings** with `/settings`
- Graceful **fallback** to yt-dlp if pytube fails
- Basic **rate limit** and progress updates

> You can keep your existing bot files. This is a separate `bot_plus.py` you can run alongside, or merge into your current bot.

---

## Quick start

1) Create a `.env` file (or copy `config_example.env` to `.env`) and set:
```
BOT_TOKEN=123456:ABC-DEFyourTelegramBotToken
DOWNLOAD_DIR=downloads
MAX_FILE_MB=1950
```
2) Install deps (recommend a virtualenv):
```
pip install -r requirements.txt
```
3) Ensure **ffmpeg** is installed (optional but recommended for MP3).  
   - If not present, audio will fallback to **.m4a** or **.webm**.
4) Run the bot:
```
python bot_plus.py
```

---

## Usage

- Send a **URL** (YouTube, Vimeo, etc.). The bot will ask for:
  1) Engine: `yt-dlp` or `pytube`
  2) Mode: `Video` or `Audio`
  3) Quality: `best`, `1080p`, `720p`, `480p`, `360p`
  4) (yt-dlp only) `Playlist?` Yes/No

- Or set defaults with `/settings` so next time it downloads immediately.

---

## Files

- `bot_plus.py` — Telegram bot entrypoint.
- `downloader.py` — download helpers for yt-dlp and pytube.
- `requirements.txt` — dependencies.
- `config_example.env` — sample configuration.
- `README_ADDONS.md` — this guide.

---

## Notes

- Telegram bots can send files up to **~2 GB**. `MAX_FILE_MB` caps the upload; larger files will be left on disk and a warning is sent.
- For MP3, we use yt-dlp's postprocessor (needs `ffmpeg`). With pytube, we attempt conversion via `ffmpeg` if found; otherwise, we keep the best audio stream.
- Playlists are supported through **yt-dlp**. Pytube path will download only the single video.
- This add‑on is intentionally self‑contained. You can move functions from `downloader.py` into your existing codebase if desired.
