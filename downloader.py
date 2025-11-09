
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
    tmpl=os.path.join(out_dir, "%(title).200s-%(id)s.%(ext)s")
    cmd=["yt-dlp","-f",_quality_to_format(quality,audio_only),"-o",tmpl,url]
    if audio_only:
        cmd+=["-x"]
        if to_mp3 and has_ffmpeg():
            cmd+=["--audio-format","mp3","--audio-quality","0"]
    cmd+=["--yes-playlist" if playlist else "--no-playlist"]
    if progress_cb:
        cmd+=["--newline","--progress"]
    proc=subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
    try:
        if proc.stdout and progress_cb:
            for line in proc.stdout:
                try: progress_cb(line.strip())
                except: pass
        proc.wait()
    finally:
        try:
            if proc.stdout: proc.stdout.close()
        except: pass
    # return newest files from out_dir
    files=[os.path.join(out_dir,f) for f in os.listdir(out_dir)]
    files.sort(key=lambda p: os.path.getmtime(p))
    return files

# ---------------- pytube ----------------

def pytube_single(url:str, out_dir:str, quality:str="best", audio_only:bool=False, to_mp3:bool=True, progress_cb=None)->Optional[str]:
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
        if os.path.exists(mp3): file_path=mp3
    return file_path

def _convert_to_mp3(path:str):
    try:
        from pydub import AudioSegment
        AudioSegment.from_file(path).export(os.path.splitext(path)[0]+".mp3", format="mp3")
    except Exception:
        # fallback to ffmpeg cli if available
        if has_ffmpeg():
            out=os.path.splitext(path)[0]+".mp3"
            subprocess.run(["ffmpeg","-y","-i",path,"-vn","-codec:a","libmp3lame","-qscale:a","0",out],
                           check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

def pytube_download(url:str, out_dir:str, quality:str="best", audio_only:bool=False, to_mp3:bool=True, progress_cb=None)->list:
    f=pytube_single(url, out_dir, quality, audio_only, to_mp3, progress_cb)
    return [f] if f else []
