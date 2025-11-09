# Flask Telegram Webhook — Temp Folder Downloads

- Each request uses a **temporary directory** (`tempfile.mkdtemp`) for downloads.
- After uploading to Telegram, the temp directory is **deleted**.
- Robust fallback chain: yt-dlp → pytube → yt-dlp(best).
- Uses `sendVideo` for videos, `sendDocument` otherwise.

## Run
pip install -r requirements.txt
python app.py
