
import os
import subprocess
import sys
from typing import List, Optional

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
            if progress_cb and ('[download]' in line or 'Merging formats' in line or 'Destination' in line or 'ERROR' in line):
                try: progress_cb(line[:500])
                except: pass
        proc.wait()
    finally:
        try:
            if proc.stdout: proc.stdout.close()
        except: pass
    return lines

def ytdlp_download_progressive_first(url:str, out_dir:str, max_h:int=360, progress_cb=None)->List[str]:
    """
    Prefer progressive MP4 to avoid ffmpeg merge requirement.
    Fallback to best under max_h.
    """
    os.makedirs(out_dir, exist_ok=True)
    out_tmpl=os.path.join(out_dir, "%(title).200s-%(id)s.%(ext)s")
    # format tries (left-to-right):
    # 1) progressive mp4 <= max_h
    # 2) any progressive <= max_h
    # 3) single-file best <= max_h (muxed)
    # 4) anything best (last resort)
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
         url]
    lines=_run(cmd, progress_cb=progress_cb)
    files=[ln for ln in lines if ln.startswith(out_dir)]
    if not files:
        # fallback: directory scan
        cands=[os.path.join(out_dir,f) for f in os.listdir(out_dir) if os.path.isfile(os.path.join(out_dir,f))]
        cands.sort(key=lambda p: os.path.getmtime(p))
        files=cands
    return files

def pytube_download(url:str, out_dir:str, target_h:int=360, audio_only:bool=False)->list:
    from pytube import YouTube
    os.makedirs(out_dir, exist_ok=True)
    yt=YouTube(url)
    if audio_only:
        stream=yt.streams.filter(only_audio=True).order_by("abr").desc().first()
        fp=stream.download(output_path=out_dir, filename_prefix="pytube-")
        return [fp]
    # Prefer progressive streams up to target_h
    stream=yt.streams.filter(progressive=True, res=f"{target_h}p").first()
    if stream is None:
        cand=yt.streams.filter(progressive=True).order_by("resolution").desc()
        stream=next((s for s in cand if s.resolution and int(s.resolution[:-1])<=target_h), None)
    if stream is None:
        # Any progressive
        stream=yt.streams.filter(progressive=True).order_by("resolution").desc().first()
    if stream is None:
        # Final fallback: any video
        stream=yt.streams.order_by("resolution").desc().first()
    if stream is None:
        raise RuntimeError("No suitable stream via pytube.")
    fp=stream.download(output_path=out_dir, filename_prefix="pytube-")
    return [fp]

def smart_download_video_default360(url, out_dir, progress_cb=None)->List[str]:
    """
    Order:
      1) pytube progressive 360p
      2) yt-dlp progressive-first <=360p
      3) yt-dlp best
    """
    # 1) pytube first
    try:
        f=pytube_download(url, out_dir, target_h=360, audio_only=False)
        f=[p for p in f if os.path.isfile(p)]
        if f: return f
    except Exception as e:
        if progress_cb: progress_cb(f"pytube failed: {e}")
    # 2) yt-dlp progressive-first
    try:
        f=ytdlp_download_progressive_first(url, out_dir, max_h=360, progress_cb=progress_cb)
        f=[p for p in f if os.path.isfile(p)]
        if f: return f
    except Exception as e:
        if progress_cb: progress_cb(f"yt-dlp (progressive-first) failed: {e}")
    # 3) yt-dlp best (last resort)
    try:
        f=ytdlp_download_progressive_first(url, out_dir, max_h=4320, progress_cb=progress_cb)
        f=[p for p in f if os.path.isfile(p)]
        if f: return f
    except Exception as e:
        if progress_cb: progress_cb(f"yt-dlp (best) failed: {e}")
    return []
