# v9 — Full logs to Telegram + /formats + /debuglog

- `/debuglog on` → yt-dlp probe & download **every line** streams to chat
- `/formats` → runs `yt-dlp -J`, sends a summary + attaches `formats.json`
- On `/start` or URL, bot uploads `probe.log`, `download.log`, and `formats.json` for the job
- Uses dynamic format selection (<=360p progressive preferred), cookies, UA, android client args

## Env
- BOT_TOKEN (required)
- YT_COOKIES_PATH=cookies.txt (optional but recommended)
- VERBOSE_CHAT=1 to default verbose on (optional)

## Webhook
curl "https://api.telegram.org/bot<TOKEN>/setWebhook?url=https://<YOUR-URL>/?token=<TOKEN>"
