"""scrape_incremental.py — BACKFILL COMPLETO 24/7: lista TODOS os videos de cada canal (yt-dlp,
sem cota) e baixa a transcricao de TODOS os que faltam (nao so os 15 do RSS). Dedupe por video_id.
Orcamento por execucao + cursor: cobre o historico inteiro ao longo de varias execucoes sem estourar
o tempo do runner. Grava published quando disponivel (date-aware). Roda no GitHub Actions.
"""
import os, re, json, glob, time, subprocess, urllib.request

TDIR = "transcripts"
CURSOR = "scrape_cursor.txt"
PER_RUN_CH = int(os.environ.get("SCRAPE_PER_RUN", "600"))          # canais por execucao
MAX_VIDEOS_RUN = int(os.environ.get("SCRAPE_MAX_VIDEOS_RUN", "700"))  # teto de transcricoes/execucao
MAX_PER_CH = int(os.environ.get("SCRAPE_MAX_PER_CH", "300"))       # teto de novos por canal/visita
UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"}

def http(url, timeout=25):
    return urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout).read().decode("utf-8", "replace")

def channel_id_from_handle(handle):
    for u in ("https://www.youtube.com/@%s/videos" % handle, "https://www.youtube.com/@%s" % handle):
        try:
            html = http(u)
            m = re.search(r'"channelId":"(UC[0-9A-Za-z_-]{22})"', html) or re.search(r'/channel/(UC[0-9A-Za-z_-]{22})', html)
            if m:
                return m.group(1)
        except Exception:
            pass
    return None

def all_uploads(channel_id):
    """TODOS os videos do canal via yt-dlp flat-playlist (playlist de uploads UU...)."""
    if not channel_id or not channel_id.startswith("UC"):
        return []
    pl = "https://www.youtube.com/playlist?list=UU" + channel_id[2:]
    try:
        p = subprocess.run(["yt-dlp", "--flat-playlist", "--no-warnings", "--ignore-errors",
                            "--print", "%(id)s\t%(title)s", pl],
                           capture_output=True, text=True, timeout=180)
        rows = []
        for line in p.stdout.splitlines():
            if "\t" in line:
                vid, tit = line.split("\t", 1)
                vid = vid.strip()
                if len(vid) == 11:
                    rows.append((vid, tit.strip()))
        return rows
    except Exception:
        return []

def rss_videos(channel_id):
    try:
        xml = http("https://www.youtube.com/feeds/videos.xml?channel_id=%s" % channel_id)
    except Exception:
        return []
    out = []
    for e in re.findall(r"<entry>(.*?)</entry>", xml, re.S):
        v = re.search(r"<yt:videoId>([^<]+)</yt:videoId>", e)
        t = re.search(r"<title>([^<]+)</title>", e)
        p = re.search(r"<published>([^<]+)</published>", e)
        if v:
            out.append((v.group(1), (t.group(1) if t else "").strip(), (p.group(1) if p else "").strip()))
    return out

def existing(path):
    ids, cid = set(), None
    if os.path.exists(path):
        for line in open(path, encoding="utf-8", errors="ignore"):
            try:
                j = json.loads(line)
            except Exception:
                continue
            vv = j.get("video_id") or j.get("id")
            if vv:
                ids.add(vv)
            cid = cid or j.get("channel_id")
    return ids, cid

def fetch_transcript(vid):
    try:
        from youtube_transcript_api import YouTubeTranscriptApi
        tr = YouTubeTranscriptApi.get_transcript(vid, languages=["pt", "pt-BR", "en", "en-US", "es", "hi"])
        return " ".join(x["text"] for x in tr if x.get("text"))
    except Exception:
        return None

def fetch_description(vid):
    """Descricao do video via yt-dlp (nunca lanca). Cap 6000 chars."""
    try:
        r = subprocess.run(["yt-dlp", "--skip-download", "--no-warnings", "--no-playlist",
                            "--print", "%(description)s", "https://youtu.be/" + vid],
                           capture_output=True, text=True, timeout=60)
        return (r.stdout or "").strip()[:20000]
    except Exception:
        return ""


def main():
    files = sorted(glob.glob(TDIR + "/*.jsonl"))
    files = [f for f in files if "extraction_index" not in f]
    # PRIORIZAR canais com MAIS seguidores (channel_ranks.json); cursor segue rotacionando -> eterno p/ TODOS
    try:
        _rk = json.load(open("channel_ranks.json", encoding="utf-8")) if os.path.exists("channel_ranks.json") else {}
        files.sort(key=lambda p: -int((_rk.get(os.path.basename(p)[:-6]) or {}).get("subs", 0)))
    except Exception:
        pass
    n = len(files)
    if n == 0:
        print("sem transcripts/ ainda"); return
    start = 0
    if os.path.exists(CURSOR):
        try:
            start = int(open(CURSOR).read().strip()) % n
        except Exception:
            start = 0
    total_new, ch_touched, processed = 0, 0, 0
    stop_at = None
    k = min(PER_RUN_CH, n)
    for i in range(k):
        gidx = (start + i) % n
        path = files[gidx]
        if total_new >= MAX_VIDEOS_RUN:
            stop_at = gidx  # retoma aqui na proxima execucao
            break
        handle = os.path.basename(path)[:-6]
        ids, cid = existing(path)
        if not cid:
            cid = channel_id_from_handle(handle)
        if not cid:
            processed += 1
            continue
        uploads = all_uploads(cid)
        pubmap = {}
        if not uploads:
            rss = rss_videos(cid)
            uploads = [(v, t) for v, t, p in rss]
            pubmap = {v: p for v, t, p in rss}
        missing = [(v, t) for v, t in uploads if v not in ids]
        added = 0
        for v, t in missing:
            if added >= MAX_PER_CH or total_new >= MAX_VIDEOS_RUN:
                break
            txt = fetch_transcript(v)
            if not txt or len(txt) < 50:
                continue
            desc = fetch_description(v)
            txt_full = txt + (("\n[DESCRIPTION] " + desc) if desc else "")
            rec = {"video_id": v, "title": t, "published": pubmap.get(v, ""), "channel": handle,
                   "channel_id": cid, "transcript": txt_full, "description": desc,
                   "chars": len(txt_full), "ts": time.strftime("%Y-%m-%dT%H:%M:%S")}
            with open(path, "a", encoding="utf-8") as f:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            ids.add(v); added += 1; total_new += 1
            time.sleep(0.5)
        if added:
            ch_touched += 1
            print("+%d/%d faltando  %s" % (added, len(missing), handle))
        # se a fome de budget parou no meio deste canal, retoma nele
        if total_new >= MAX_VIDEOS_RUN and added < len(missing):
            stop_at = gidx
            break
        processed += 1
    newcur = stop_at if stop_at is not None else (start + processed) % n
    open(CURSOR, "w").write(str(newcur % n))
    print("RESUMO: canais visitados=%d | com novidade=%d | transcricoes novas=%d | cursor->%d/%d"
          % (processed, ch_touched, total_new, newcur % n, n))

if __name__ == "__main__":
    main()
