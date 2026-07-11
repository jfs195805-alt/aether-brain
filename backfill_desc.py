import os, json, time, subprocess, glob

TDIR = "transcripts"
BUDGET = int(os.environ.get("BF_BUDGET", "400"))
CAP = int(os.environ.get("BF_DESC_CAP", "20000"))  # descricao COMPLETA, sem resumir
HANDLE = os.environ.get("BF_HANDLE", "ALL")
CID = os.environ.get("BF_CID", "")
CURSOR = "desc_cursor.txt"

def uploads(cid):
    up = "https://www.youtube.com/playlist?list=UU" + cid[2:]
    try:
        p = subprocess.run(["yt-dlp", "--flat-playlist", "--no-warnings", "--ignore-errors",
                            "--print", "%(id)s\t%(title)s", up],
                           capture_output=True, text=True, timeout=600)
        out = []
        for line in p.stdout.splitlines():
            if "\t" in line:
                a, b = line.split("\t", 1); out.append((a.strip(), b.strip()))
        return out
    except Exception:
        return []

def cid_from_jsonl(path):
    try:
        for line in open(path, encoding="utf-8", errors="ignore"):
            try:
                j = json.loads(line)
                if j.get("channel_id"):
                    return j["channel_id"]
            except Exception:
                pass
    except Exception:
        pass
    return None

def get_desc(vid):
    try:
        r = subprocess.run(["yt-dlp", "--skip-download", "--no-warnings", "--no-playlist",
                            "--print", "%(description)s", "https://youtu.be/" + vid],
                           capture_output=True, text=True, timeout=60)
        return (r.stdout or "").strip()[:CAP]
    except Exception:
        return ""

def done_desc(path):
    s = set()
    if os.path.exists(path):
        for line in open(path, encoding="utf-8", errors="ignore"):
            try:
                j = json.loads(line); v = j.get("video_id", "")
                if v.endswith("_desc"):
                    s.add(v[:-5])
            except Exception:
                pass
    return s

def backfill_channel(handle, cid, path, budget):
    if budget <= 0:
        return 0
    done = done_desc(path)
    cid = cid or cid_from_jsonl(path)
    if not cid:
        return 0
    vids = uploads(cid)
    added = 0
    with open(path, "a", encoding="utf-8") as f:
        for vid, title in vids:
            if vid in done:
                continue
            if added >= budget:
                break
            d = get_desc(vid)
            ok = len(d) >= 15
            rec = {"video_id": vid + "_desc", "handle": handle, "title": title,
                   "transcript": ("[DESCRIPTION] " + d) if ok else "",
                   "description": d if ok else "", "chars": len(d),
                   "kind": "description", "ts": time.strftime("%Y-%m-%dT%H:%M:%S")}
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            added += 1; time.sleep(0.2)
    if added:
        print("  %s: +%d descricoes (canal=%d videos)" % (handle, added, len(vids)))
    return added

if HANDLE != "ALL":
    backfill_channel(HANDLE, CID, os.path.join(TDIR, HANDLE + ".jsonl"), BUDGET)
else:
    files = sorted(glob.glob(TDIR + "/*.jsonl"))
    files = [f for f in files if "extraction_index" not in f]
    n = len(files) or 1
    start = 0
    if os.path.exists(CURSOR):
        try:
            start = int(open(CURSOR).read().strip()) % n
        except Exception:
            start = 0
    total = 0; i = 0
    while total < BUDGET and i < n:
        path = files[(start + i) % n]
        handle = os.path.basename(path)[:-6]
        total += backfill_channel(handle, "", path, BUDGET - total)
        i += 1
    newcur = (start + i) % n
    open(CURSOR, "w").write(str(newcur))
    print("ROTACAO desc: canais visitados=%d | descricoes+=%d | cursor->%d/%d" % (i, total, newcur, n))

# ===== TESTE/VERIFICACAO: conta transcricoes e descricoes reais e grava status =====
tot_tr = 0; tot_desc = 0; ch = 0
for path in glob.glob(TDIR + "/*.jsonl"):
    if "extraction_index" in path:
        continue
    ch += 1
    for line in open(path, encoding="utf-8", errors="ignore"):
        try:
            j = json.loads(line); v = j.get("video_id", "")
            if v.endswith("_desc"):
                if j.get("description"):
                    tot_desc += 1
            elif j.get("transcript"):
                tot_tr += 1
        except Exception:
            pass
print("[TESTE] canais=%d | transcricoes=%d | descricoes=%d" % (ch, tot_tr, tot_desc))
with open("transcripts_status.md", "w", encoding="utf-8") as f:
    f.write("# AETHER corpus status (auto)\n\n")
    f.write("- canais: %d\n- transcricoes: %d\n- descricoes: %d\n- atualizado: %s\n"
            % (ch, tot_tr, tot_desc, time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())))
