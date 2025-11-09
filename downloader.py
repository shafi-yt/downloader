
import os, json, subprocess, tempfile
from typing import List, Optional

DEFAULT_UA = os.environ.get("YT_UA",
"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

def human_size(num_bytes:int)->str:
    for unit in ["B","KB","MB","GB","TB"]:
        if num_bytes<1024: return f"{num_bytes:.1f}{unit}"
        num_bytes/=1024
    return f"{num_bytes:.1f}PB"

def _cookies_path_or_default()->Optional[str]:
    path = os.environ.get("YT_COOKIES_PATH", "cookies.txt")
    if path and os.path.exists(path): return path
    b64 = os.environ.get("YT_COOKIES_B64")
    if b64:
        import base64
        try:
            data = base64.b64decode(b64)
            tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".cookies.txt")
            tmp.write(data); tmp.close()
            return tmp.name
        except Exception:
            pass
    return None

def _run(cmd:list)->str:
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    out=[]
    for ln in p.stdout or []:
        out.append(ln)
    p.wait()
    return "".join(out)

def _common_args()->list:
    args=["--geo-bypass","--add-header", f"User-Agent: {DEFAULT_UA}","--extractor-args","youtube:player_client=android"]
    ck=_cookies_path_or_default()
    if ck: args+=["--cookies", ck]
    return args

def probe_formats(url:str)->dict:
    cmd=["yt-dlp","-J","--no-download"]+_common_args()+[url]
    txt=_run(cmd)
    try:
        data=json.loads(txt)
        return data
    except Exception:
        # Some yt-dlp builds print extra lines; try to parse last JSON block
        last_brace=txt.rfind("}")
        first_brace=txt.find("{")
        if first_brace!=-1 and last_brace!=-1 and last_brace>first_brace:
            try:
                return json.loads(txt[first_brace:last_brace+1])
            except Exception:
                pass
    raise RuntimeError("Failed to parse format JSON. Output:\n"+txt[:1000])

def pick_best_360(data:dict)->str:
    """
    Return an explicit format selector for yt-dlp -f:
    - Prefer progressive (has both acodec & vcodec) with height<=360, ext mp4
    - Else progressive any <=360
    - Else adaptive: best video<=360 (prefer mp4/h264) + best audio (m4a/aac)
    - Else best single
    """
    formats=data.get("formats") or []
    # normalize
    def height(f): return (f.get("height") or 0) or 0
    def ext(f): return (f.get("ext") or "").lower()
    def vcodec(f): return (f.get("vcodec") or "none").lower()
    def acodec(f): return (f.get("acodec") or "none").lower()
    def fid(f): return f.get("format_id")

    progs=[f for f in formats if vcodec(f)!="none" and acodec(f)!="none"]
    progs_360=[f for f in progs if height(f) and height(f)<=360]
    # mp4 first
    mp4_360=[f for f in progs_360 if ext(f)=="mp4"]
    if mp4_360:
        # pick highest height<=360, then bitrate
        mp4_360.sort(key=lambda f:(height(f), f.get("tbr") or 0), reverse=True)
        return fid(mp4_360[0])
    if progs_360:
        progs_360.sort(key=lambda f:(height(f), f.get("tbr") or 0), reverse=True)
        return fid(progs_360[0])
    # adaptive fallback
    vids=[f for f in formats if vcodec(f)!="none" and acodec(f)=="none"]
    vids_360=[f for f in vids if height(f) and height(f)<=360]
    # prefer avc1/h264 mp4
    def vscore(f):
        c=vcodec(f)
        s=0
        if "avc1" in c or "h264" in c: s+=3
        if ext(f)=="mp4": s+=2
        return (s, height(f), f.get("tbr") or 0)
    if vids_360:
        vids_360.sort(key=lambda f: vscore(f), reverse=True)
        v=vids_360[0]
        auds=[f for f in formats if vcodec(f)=="none" and acodec(f)!="none"]
        # prefer m4a/aac
        def ascore(a):
            s=0
            if "m4a" in ext(a): s+=2
            if "aac" in acodec(a): s+=2
            return (s, a.get("abr") or 0, a.get("tbr") or 0)
        if auds:
            auds.sort(key=lambda a: ascore(a), reverse=True)
            a=auds[0]
            return f"{fid(v)}+{fid(a)}"
    # last resort: best single
    singles=[f for f in formats if fid(f)]
    if singles:
        singles.sort(key=lambda f:(height(f), f.get("tbr") or 0), reverse=True)
        return fid(singles[0])
    # fallback to generic
    return "best"

def download_with_format(url:str, out_dir:str, fmt:str, progress_cb=None)->List[str]:
    os.makedirs(out_dir, exist_ok=True)
    out_tmpl=os.path.join(out_dir, "%(title).200s-%(id)s.%(ext)s")
    cmd=["yt-dlp","-f",fmt,"-o",out_tmpl,"--no-part","--print","after_move:filepath","--newline","--progress"]+_common_args()+[url]
    p=subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    files=[]
    for ln in p.stdout or []:
        if progress_cb and any(k in ln for k in ("[download]","Merging formats","Destination","ERROR")):
            try: progress_cb(ln[:400])
            except: pass
        ln=ln.strip()
        if ln.startswith(out_dir):
            files.append(ln)
    p.wait()
    if not files:
        # scan dir
        cands=[os.path.join(out_dir,f) for f in os.listdir(out_dir) if os.path.isfile(os.path.join(out_dir,f))]
        cands.sort(key=lambda p: os.path.getmtime(p))
        files=cands
    return files

def dynamic_download_360(url:str, out_dir:str, progress_cb=None)->List[str]:
    # 1) Probe formats
    data=probe_formats(url)
    # 2) Pick best available <=360p (progressive preferred)
    fmt=pick_best_360(data)
    # 3) Download exactly that
    return download_with_format(url, out_dir, fmt, progress_cb=progress_cb)
