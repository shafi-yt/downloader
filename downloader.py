
import os, json, subprocess, tempfile

DEFAULT_UA = os.environ.get("YT_UA",
"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

def human_size(num_bytes:int)->str:
    for unit in ["B","KB","MB","GB","TB"]:
        if num_bytes<1024: return f"{num_bytes:.1f}{unit}"
        num_bytes/=1024
    return f"{num_bytes:.1f}PB"

def _cookies_path_or_default():
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

def _common_args()->list:
    args=["--geo-bypass","--add-header", f"User-Agent: {DEFAULT_UA}","--extractor-args","youtube:player_client=android"]
    ck=_cookies_path_or_default()
    if ck: args+=["--cookies", ck]
    return args

def run_capture(cmd:list, progress_cb=None)->str:
    """Run a command, stream lines to progress_cb, and return full output text."""
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
    buf=[]
    for ln in p.stdout or []:
        buf.append(ln)
        if progress_cb:
            try:
                progress_cb(ln.rstrip("\n"))
            except Exception:
                pass
    p.wait()
    return "".join(buf)

def probe_formats(url:str, progress_cb=None)->dict:
    cmd=["yt-dlp","-J","--no-download"]+_common_args()+[url]
    txt=run_capture(cmd, progress_cb=progress_cb)
    # try robust JSON parse
    try:
        return json.loads(txt)
    except Exception:
        last=txt.rfind("}")
        first=txt.find("{")
        if first!=-1 and last!=-1 and last>first:
            try:
                return json.loads(txt[first:last+1])
            except Exception as e:
                raise RuntimeError(f"Failed to parse JSON: {e}\n---RAW START---\n{txt[:4000]}\n---RAW END---")
        raise RuntimeError(f"Unexpected probe output.\n---RAW START---\n{txt[:4000]}\n---RAW END---")

def pick_best_360(data:dict)->str:
    formats=data.get("formats") or []
    def height(f): return (f.get("height") or 0) or 0
    def ext(f): return (f.get("ext") or "").lower()
    def vcodec(f): return (f.get("vcodec") or "none").lower()
    def acodec(f): return (f.get("acodec") or "none").lower()
    def fid(f): return f.get("format_id")

    progs=[f for f in formats if vcodec(f)!="none" and acodec(f)!="none"]
    progs_360=[f for f in progs if height(f) and height(f)<=360]
    mp4_360=[f for f in progs_360 if ext(f)=="mp4"]
    if mp4_360:
        mp4_360.sort(key=lambda f:(height(f), f.get("tbr") or 0), reverse=True)
        return fid(mp4_360[0])
    if progs_360:
        progs_360.sort(key=lambda f:(height(f), f.get("tbr") or 0), reverse=True)
        return fid(progs_360[0])
    vids=[f for f in formats if vcodec(f)!="none" and acodec(f)=="none"]
    vids_360=[f for f in vids if height(f) and height(f)<=360]
    def vscore(f):
        c=vcodec(f); s=0
        if "avc1" in c or "h264" in c: s+=3
        if ext(f)=="mp4": s+=2
        return (s, height(f), f.get("tbr") or 0)
    if vids_360:
        vids_360.sort(key=lambda f:vscore(f), reverse=True)
        v=vids_360[0]
        auds=[f for f in formats if vcodec(f)=="none" and acodec(f)!="none"]
        def ascore(a):
            s=0
            if "m4a" in ext(a): s+=2
            if "aac" in acodec(a): s+=2
            return (s, a.get("abr") or 0, a.get("tbr") or 0)
        if auds:
            auds.sort(key=lambda a:ascore(a), reverse=True)
            a=auds[0]
            return f"{fid(v)}+{fid(a)}"
    singles=[f for f in formats if fid(f)]
    if singles:
        singles.sort(key=lambda f:(height(f), f.get("tbr") or 0), reverse=True)
        return fid(singles[0])
    return "best"

def download_with_format(url:str, out_dir:str, fmt:str, progress_cb=None)->list:
    os.makedirs(out_dir, exist_ok=True)
    out_tmpl=os.path.join(out_dir, "%(title).200s-%(id)s.%(ext)s")
    cmd=["yt-dlp","-f",fmt,"-o",out_tmpl,"--no-part","--print","after_move:filepath","--newline","--progress"]+_common_args()+[url]
    full = run_capture(cmd, progress_cb=progress_cb)
    files=[ln for ln in full.splitlines() if ln.startswith(out_tmpl[:out_tmpl.rfind("%")]) or os.path.isabs(ln)]
    if not files:
        cands=[os.path.join(out_dir,f) for f in os.listdir(out_dir) if os.path.isfile(os.path.join(out_dir,f))]
        cands.sort(key=lambda p: os.path.getmtime(p))
        files=cands
    return files, full

def dynamic_download_360(url:str, out_dir:str, progress_cb=None)->tuple:
    # 1) Probe
    probe_log=[]
    def pcb(l):
        probe_log.append(l)
        if progress_cb: progress_cb(l)
    data=probe_formats(url, progress_cb=pcb)
    fmt=pick_best_360(data)
    # 2) Download
    files, dl_full = download_with_format(url, out_dir, fmt, progress_cb=progress_cb)
    # 3) Return files + logs
    return files, fmt, "\n".join(probe_log), dl_full, data
