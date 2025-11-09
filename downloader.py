
import os
import subprocess
from typing import List, Optional

def ensure_dir(p:str):
    os.makedirs(p, exist_ok=True)

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
            if progress_cb and ('[download]' in line or 'Merging formats' in line or 'Destination' in line):
                try: progress_cb(line[:200])
                except: pass
        proc.wait()
    finally:
        try:
            if proc.stdout: proc.stdout.close()
        except: pass
    return lines

# ---------------- yt-dlp ----------------

def _quality_to_format(quality:str, audio_only:bool)->str:
    q=(quality or "best").lower()
    if audio_only:
        return "bestaudio/best"
    mapping={
        "best":"bestvideo*+bestaudio/best",
        "1080p":"bestvideo[height<=1080]+bestaudio/best[height<=1080]",
        "720p":"bestvideo[height<=720]+bestaudio/best[height<=720]",
        "480p":"bestvideo[height<=480]+bestaudio/best[height<=480]",
        "360p":"bestvideo[height<=360]+bestaudio/best[height<=360]",
    }
    return mapping.get(q, mapping["best"])

def ytdlp_download(url:str, out_dir:str, quality:str="best", audio_only:bool=False, to_mp3:bool=True, playlist:bool=False, progress_cb=None)->List[str]:
    ensure_dir(out_dir)
    out_tmpl=os.path.join(out_dir, "%(title).200s-%(id)s.%(ext)s")

    cmd=["yt-dlp",
         "-f", _quality_to_format(quality, audio_only),
         "-o", out_tmpl,
         "--no-part",
         "--no-abort-on-unavailable-fragment",
         "--print", "after_move:filepath",
         url]

    if audio_only:
        cmd+=["-x"]
        if to_mp3 and has_ffmpeg():
            cmd+=["--audio-format","mp3","--audio-quality","0"]
    cmd+=["--yes-playlist" if playlist else "--no-playlist"]
    cmd+=["--newline","--progress"]

    lines=_run(cmd, progress_cb=progress_cb)
    files=[ln for ln in lines if ln.startswith(out_dir)]
    if not files:
        candidates=[os.path.join(out_dir,f) for f in os.listdir(out_dir) if os.path.isfile(os.path.join(out_dir,f))]
        candidates.sort(key=lambda p: os.path.getmtime(p))
        files=candidates
    return files

# ---------------- pytube ----------------

def pytube_single(url:str, out_dir:str, quality:str="best", audio_only:bool=False, to_mp3:bool=True)->Optional[str]:
    from pytube import YouTube
    ensure_dir(out_dir)
    yt=YouTube(url)
    if audio_only:
        stream=yt.streams.filter(only_audio=True).order_by("abr").desc().first()
    else:
        qmap={"1080p":1080,"720p":720,"480p":480,"360p":360}
        target=qmap.get((quality or "best").lower())
        if target:
            stream=yt.streams.filter(progressive=True, res=f"{target}p").first()
            if stream is None:
                cand=yt.streams.filter(progressive=True).order_by("resolution").desc()
                stream=next((s for s in cand if s.resolution and int(s.resolution[:-1])<=target), None)
        else:
            stream=yt.streams.filter(progressive=True).order_by("resolution").desc().first()
        if stream is None:
            stream=yt.streams.order_by("resolution").desc().first()
    if stream is None:
        raise RuntimeError("No suitable stream via pytube.")
    file_path=stream.download(output_path=out_dir, filename_prefix="pytube-")
    if audio_only and to_mp3:
        _convert_to_mp3(file_path)
        root,_=os.path.splitext(file_path)
        mp3=root+".mp3"
        if os.path.exists(mp3):
            file_path=mp3
    return file_path

def _convert_to_mp3(path:str):
    try:
        from pydub import AudioSegment
        AudioSegment.from_file(path).export(os.path.splitext(path)[0]+".mp3", format="mp3")
    except Exception:
        if has_ffmpeg():
            out=os.path.splitext(path)[0]+".mp3"
            subprocess.run(["ffmpeg","-y","-i",path,"-vn","-codec:a","libmp3lame","-qscale:a","0",out],
                           check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

def pytube_download(url:str, out_dir:str, quality:str="best", audio_only:bool=False, to_mp3:bool=True)->list:
    f=pytube_single(url, out_dir, quality, audio_only, to_mp3)
    return [f] if f else []

def smart_download(url:str, out_dir:str, quality:str, audio_only:bool, to_mp3:bool, playlist:bool, progress_cb=None)->List[str]:
    try:
        files=ytdlp_download(url, out_dir, quality=quality, audio_only=audio_only, to_mp3=to_mp3, playlist=playlist, progress_cb=progress_cb)
        files=[p for p in files if os.path.isfile(p)]
        if files: return files
    except Exception as e:
        if progress_cb: progress_cb(f"yt-dlp failed: {e}")
    try:
        files=pytube_download(url, out_dir, quality=quality, audio_only=audio_only, to_mp3=to_mp3)
        files=[p for p in files if os.path.isfile(p)]
        if files: return files
    except Exception as e:
        if progress_cb: progress_cb(f"pytube failed: {e}")
    try:
        files=ytdlp_download(url, out_dir, quality="best", audio_only=audio_only, to_mp3=to_mp3, playlist=False, progress_cb=progress_cb)
        files=[p for p in files if os.path.isfile(p)]
        if files: return files
    except Exception as e:
        if progress_cb: progress_cb(f"yt-dlp fallback failed: {e}")
    return []
