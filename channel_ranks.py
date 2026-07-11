"""channel_ranks.py — mede SEGUIDORES de cada canal (yt-dlp) p/ priorizar quem tem mais na
transcricao. Cacheia em channel_ranks.json (resumavel, orcamento por run)."""
import os, json, glob, subprocess, time
TDIR = "transcripts"; OUT = "channel_ranks.json"
BUDGET = int(os.environ.get("RANK_BUDGET", "120"))

ranks = {}
if os.path.exists(OUT):
    try:
        ranks = json.load(open(OUT, encoding="utf-8"))
    except Exception:
        ranks = {}

def cid_of(path):
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

def subs(cid):
    try:
        r = subprocess.run(["yt-dlp", "--flat-playlist", "--playlist-items", "1", "--no-warnings",
                            "--print", "%(channel_follower_count)s",
                            "https://www.youtube.com/channel/" + cid],
                           capture_output=True, text=True, timeout=60)
        for x in (r.stdout or "").splitlines():
            x = x.strip()
            if x.isdigit():
                return int(x)
    except Exception:
        pass
    return 0

files = sorted(glob.glob(TDIR + "/*.jsonl"))
done = 0
for path in files:
    h = os.path.basename(path)[:-6]
    if ranks.get(h, {}).get("subs", 0) > 0:
        continue
    if done >= BUDGET:
        break
    cid = cid_of(path)
    if not cid:
        continue
    ranks[h] = {"subs": subs(cid), "cid": cid, "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    done += 1; time.sleep(0.2)
json.dump(ranks, open(OUT, "w", encoding="utf-8"), ensure_ascii=False)
top = sorted(ranks.items(), key=lambda kv: -kv[1].get("subs", 0))[:12]
print("RANKS: %d canais medidos | +%d neste run" % (len(ranks), done))
for k, v in top:
    print("  %s: %s seguidores" % (k, v.get("subs")))
