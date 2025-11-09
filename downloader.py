
import os
import subprocess
import tempfile
from typing import List, Optional

DEFAULT_UA = os.environ.get("YT_UA",
"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

def has_ffmpeg()->bool:
    from shutil import which
    return which("ffmpeg") is not None

def human_size(num_bytes:int)->str:
    for unit in ["B","KB","MB","GB","TB"]:
        if num_bytes<1024:
            return f"{num_bytes:.1f}{unit}"
        num_bytes/=1024
    return f"{num_bytes:.1f}PB"

def _run(cmd:list, progress_cb=None)->List[str]:
    proc=subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
    lines=[]
    try:
        for line in proc.stdout or []:
            line=line.rstrip("\n")
            lines.append(line)
            if progress_cb and any(k in line for k in ("[download]", "Merging formats", "Destination", "ERROR")):
                try: progress_cb(line[:500])
                except: pass
        proc.wait()
    finally:
        try:
            if proc.stdout: proc.stdout.close()
        except: pass
    return lines

def _cookies_path_or_default()->Optional[str]:
    """
    Pick cookies file path from env:
    - YT_COOKIES_PATH if exists (default 'cookies.txt')
    - OR YT_COOKIES_B64 (base64) -> write to temp file
    """
    path = os.environ.get("YT_COOKIES_PATH", "cookies.txt")
    if path and os.path.exists(path):
        return path
    b64 = os.environ.get("YT_COOKIES_B64")
    if b64:
        import base64, tempfile
        try:
            data = base64.b64decode(b64)
            tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".cookies.txt")
            tmp.write(data); tmp.close()
            return tmp.name
        except Exception:
            pass
    return None

def ytdlp_download_progressive_first(url:str, out_dir:str, max_h:int=360, progress_cb=None)->List[str]:
    """
    Prefer progressive/single-file; pass cookies & UA & extractor-args to dodge consent/age walls.
    """
    os.makedirs(out_dir, exist_ok=True)
    out_tmpl=os.path.join(out_dir, "%(title).200s-%(id)s.%(ext)s")

    fstr = (
        f'best[ext=mp4][vcodec!*=av01][height<={max_h}][fps<=30]/'
        f'best[height<={max_h}][fps<=30][is_live!=1]/'
        f'best[height<={max_h}]/'
        f'best'
    )

    cmd=["yt-dlp",
         "-f", fstr,
         "-o", out_tmpl,
         "--no-part",
         "--no-abort-on-unavailable-fragment",
         "--print", "after_move:filepath",
         "--newline", "--progress",
         "--geo-bypass",
         "--add-header", f"User-Agent: {DEFAULT_UA}",
         "--extractor-args", "youtube:player_client=android",
         url]

    cookies_path = _cookies_path_or_default()
    if cookies_path:
        cmd += ["--cookies", cookies_path]

    lines=_run(cmd, progress_cb=progress_cb)
    files=[ln for ln in lines if ln.startswith(out_dir)]
    if not files:
        # scan dir fallback
        cands=[os.path.join(out_dir,f) for f in os.listdir(out_dir) if os.path.isfile(os.path.join(out_dir,f))]
        cands.sort(key=lambda p: os.path.getmtime(p))
        files=cands
    return files

def pytube_download(url:str, out_dir:str, target_h:int=360)->list:
    """
    pytube fallback (no cookies). Prefers progressive.
    """
    from pytube import YouTube
    os.makedirs(out_dir, exist_ok=True)
    yt=YouTube(url)
    stream=yt.streams.filter(progressive=True, res=f"{target_h}p").first()
    if stream is None:
        cand=yt.streams.filter(progressive=True).order_by("resolution").desc()
        stream=next((s for s in cand if s.resolution and int(s.resolution[:-1])<=target_h), None)
    if stream is None:
        stream=yt.streams.filter(progressive=True).order_by("resolution").desc().first()
    if stream is None:
        stream=yt.streams.order_by("resolution").desc().first()
    if stream is None:
        raise RuntimeError("No suitable stream via pytube.")
    fp=stream.download(output_path=out_dir, filename_prefix="pytube-")
    return [fp]

def smart_download_video_360(url, out_dir, progress_cb=None)->List[str]:
    """
    Order:
      1) yt-dlp (<=360p, cookies+UA)
      2) pytube (360p progressive)
      3) yt-dlp (best, cookies+UA)
    """
    try:
        f=ytdlp_download_progressive_first(url, out_dir, max_h=360, progress_cb=progress_cb)
        f=[p for p in f if os.path.isfile(p)]
        if f: return f
    except Exception as e:
        if progress_cb: progress_cb(f"yt-dlp(<=360) failed: {e}")
    try:
        f=pytube_download(url, out_dir, target_h=360)
        f=[p for p in f if os.path.isfile(p)]
        if f: return f
    except Exception as e:
        if progress_cb: progress_cb(f"pytube failed: {e}")
    try:
        f=ytdlp_download_progressive_first(url, out_dir, max_h=4320, progress_cb=progress_cb)
        f=[p for p in f if os.path.isfile(p)]
        if f: return f
    except Exception as e:
        if progress_cb: progress_cb(f"yt-dlp(best) failed: {e}")
    return []
