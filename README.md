# Telegram YouTube Downloader (Flask Webhook) — GitHub + Render Ready

- `/start` ⇒ downloads **DEFAULT_URL** at ~**360p**, uploads to Telegram, cleans temp dir.
- Fallback chain: **yt-dlp (cookies+UA)** → **pytube (progressive 360p)** → **yt-dlp (best, cookies+UA)**.
- **cookies.txt** is included in this repo — paste Netscape-format cookies there.
- Health check: `GET /health`

## One-Click with Render Blueprint
1. Push this repo to GitHub.
2. In Render, **New +** → **Blueprint** → paste your GitHub repo URL.
3. Render will read `render.yaml` and create a **Web Service**.
4. Add env var **BOT_TOKEN** in Render (required). Others have defaults.

### Webhook
Replace `<TOKEN>` and `<YOUR-URL>` accordingly:
```
curl "https://api.telegram.org/bot<TOKEN>/setWebhook?url=https://<YOUR-URL>/?token=<TOKEN>"
```
> Note the **`?token=<TOKEN>`** is required so the server knows your bot token for each webhook call.

## Env Vars
- `BOT_TOKEN` (required)
- `DEFAULT_URL` (default: `https://youtu.be/BfLPuDRgjPw`)
- `MAX_FILE_MB` (default: `1950`)
- `YT_UA` (default: a desktop Chrome UA; override if needed)
- `YT_COOKIES_PATH` (default: `cookies.txt` in repo root)
- `YT_COOKIES_B64` (optional alternative to provide cookies)

## cookies.txt (Netscape format)
Use the **Get cookies.txt** browser extension while logged into YouTube, then paste the exported contents into `cookies.txt` (this repo includes the file).  
Health endpoint shows whether cookies are detected:

```
GET https://<YOUR-URL>/health
-> {"ok": true, "cookies": true, ...}
```

## Local Dev
```
python -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
export BOT_TOKEN=123456:ABC...
python app.py
```
Then set webhook to `http://localhost:10000/?token=<BOT_TOKEN>` via **ngrok** if testing externally.

## Notes
- Max Telegram upload ~2GB; use 360p default to keep files small.
- If you hit "Sign in to confirm you’re not a bot", make sure cookies are present.
- This server uses a temp dir per request and deletes files after upload.
