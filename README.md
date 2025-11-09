
# Telegram YouTube Downloader — Lite (Complete)

This package contains a ready-to-deploy 'Lite' version of the Telegram YouTube downloader bot.
It targets small downloads (360/480) and includes anti-bot cookie support.

## Files
- app.py: Flask app
- requirements.txt: Python deps (yt-dlp pinned)
- render.yaml: example Render service config
- README.md: this file

## Deploy on Render
1. Push repository to GitHub.
2. Create a new Web Service on Render pointing to the repo.
3. Add env var (optional but recommended):
   - YTDLP_COOKIES_B64 : base64 of your cookies.txt (Netscape format)
4. Set webhook (replace <TOKEN> and <APP_URL>):
   curl -X POST "https://api.telegram.org/bot<TOKEN>/setWebhook" -d "url=https://<APP_URL>/?token=<TOKEN>"

## Notes
- Keep cookies private.
- If yt-dlp errors with anti-bot, add cookies (see above) and redeploy.
