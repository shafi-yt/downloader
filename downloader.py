
import os
import shutil
import subprocess
import uuid
from typing import Optional, Dict, Any, Tuple, List

def _which(cmd: str) -> Optional[str]:
    from shutil import which
    return which(cmd)

def has_ffmpeg() -> bool:
    return _which("ffmpeg") is not None

def ensure_dir(path: str):
    os.makedirs(path, exist_ok=True)

def human_size(num_bytes: int) -> str:
    for unit in ["B","KB","MB","GB","TB"]:
        if num_bytes < 1024.0:
            return f"{num_bytes:.1f}{unit}"
        num_bytes /= 1024.0
    return f"{num_bytes:.1f}PB"

# ----------------------------- yt-dlp path -----------------------------

def _quality_to_format(quality: str, audio_only: bool) -> str:
    q = (quality or "best").lower()
    if audio_only:
        # best audio; postprocess to mp3 if ffmpeg exists
        return "bestaudio/best"
    # Map common qualities; fallback to best
    mapping = {
        "best": "bestvideo*+bestaudio/best",
        "1080p": "bestvideo[height<=1080]+bestaudio/best[height<=1080]",
        "720p": "bestvideo[height<=720]+bestaudio/best[height<=720]",
        "480p": "bestvideo[height<=480]+bestaudio/best[height<=480]",
        "360p": "bestvideo[height<=360]+bestaudio/best[height<=360]",
    }
    return mapping.get(q, mapping["best"])

def download_with_ytdlp(
    url: str,
    out_dir: str,
    quality: str = "best",
    audio_only: bool = False,
    to_mp3: bool = True,
    playlist: bool = False,
    progress_cb=None,
) -> List[str]:
    """
    Returns list of output file paths.
    """
    ensure_dir(out_dir)
    out_tmpl = os.path.join(out_dir, "%(title).200s-%(id)s.%(ext)s")
    ytdlp_cmd = ["yt-dlp", "-f", _quality_to_format(quality, audio_only), "-o", out_tmpl, url]

    postprocessors = []
    if audio_only:
        ytdlp_cmd += ["-x"]
        if to_mp3 and has_ffmpeg():
            postprocessors += ["--audio-format", "mp3", "--audio-quality", "0"]
        else:
            # default extract audio (usually m4a or webm)
            pass

    if not playlist:
        ytdlp_cmd += ["--no-playlist"]
    else:
        ytdlp_cmd += ["--yes-playlist"]

    if progress_cb:
        ytdlp_cmd += ["--newline", "--progress"]

    # Run process and optionally stream progress lines
    proc = subprocess.Popen(ytdlp_cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
    outputs = []
    try:
        for line in proc.stdout:
            if progress_cb:
                try:
                    progress_cb(line.rstrip())
                except Exception:
                    pass
        proc.wait()
    finally:
        if proc.stdout:
            proc.stdout.close()

    # Collect output files from out_dir by mtime
    files = sorted([os.path.join(out_dir, f) for f in os.listdir(out_dir)], key=lambda p: os.path.getmtime(os.path.join(out_dir, p)))
    return files

# ----------------------------- pytube path -----------------------------

def _pytube_download_single(
    url: str,
    out_dir: str,
    quality: str = "best",
    audio_only: bool = False,
    to_mp3: bool = True,
    progress_cb=None,
) -> Optional[str]:
    from pytube import YouTube
    ensure_dir(out_dir)
    yt = YouTube(url, on_progress_callback=None)

    if audio_only:
        stream = yt.streams.filter(only_audio=True).order_by("abr").desc().first()
    else:
        # try exact quality first
        target_h = {"1080p":1080,"720p":720,"480p":480,"360p":360}.get((quality or "best").lower(), None)
        if target_h:
            stream = yt.streams.filter(progressive=True, res=f"{target_h}p").first()
            if stream is None:
                # fallback to closest lower progressive
                candidates = yt.streams.filter(progressive=True).order_by("resolution").desc()
                stream = next((s for s in candidates if s.resolution and int(s.resolution[:-1]) <= target_h), None)
        else:
            stream = yt.streams.filter(progressive=True).order_by("resolution").desc().first()

        if stream is None:
            # fallback to best available (may be adaptive; then we'll skip merge)
            stream = yt.streams.order_by("resolution").desc().first()

    if stream is None:
        raise RuntimeError("No suitable stream found via pytube.")

    outfile = stream.download(output_path=out_dir, filename_prefix="pytube-")
    # Convert to mp3 if requested and possible
    if audio_only and to_mp3 and has_ffmpeg():
        root, ext = os.path.splitext(outfile)
        mp3_path = root + ".mp3"
        cmd = ["ffmpeg", "-y", "-i", outfile, "-vn", "-codec:a", "libmp3lame", "-qscale:a", "0", mp3_path]
        subprocess.run(cmd, check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if os.path.exists(mp3_path):
            try:
                os.remove(outfile)
            except Exception:
                pass
            outfile = mp3_path
    return outfile

def download_with_pytube(
    url: str,
    out_dir: str,
    quality: str = "best",
    audio_only: bool = False,
    to_mp3: bool = True,
    progress_cb=None,
) -> list:
    """
    Single video via pytube. Returns list with one file path (if succeeded).
    """
    f = _pytube_download_single(url, out_dir, quality, audio_only, to_mp3, progress_cb)
    return [f] if f else []

