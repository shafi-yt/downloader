# v8 — Dynamic format selection (<=360p)

Fixes `Requested format is not available` by **probing formats** first (`yt-dlp -J`), then choosing:
1) progressive mp4 <=360p (h264) if available
2) any progressive <=360p
3) adaptive best video<=360p (prefer avc1/mp4) + best audio (m4a/aac)
4) last resort: best single

Cookies + UA + android client extractor args included. Temp dir per request, upload then cleanup.

## Webhook
curl "https://api.telegram.org/bot<TOKEN>/setWebhook?url=https://<YOUR-URL>/?token=<TOKEN>"
