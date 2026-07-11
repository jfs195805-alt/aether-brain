#!/usr/bin/env python3
"""backfill_ts.py - TIMESTAMPS REAIS de cada fala, via yt-dlp (resiste a IP de datacenter).

O youtube_transcript_api e bloqueado nos runners do GitHub (IP de nuvem). O yt-dlp baixa a
legenda automatica em VTT, que traz o tempo de CADA fala. Parseamos o VTT -> segments.

Grava transcripts_ts/<canal>.jsonl -> {video_id, segments: [[start_seg, texto], ...]}
Incremental: TS_BATCH videos por rodada (roda toda execucao, vai cobrindo o corpus todo).
"""
import os, json, glob, time, random, subprocess, re, shutil, tempfile

SRC = os.environ.get("NG_SRC", "transcripts")
TSDIR = os.environ.get("NG_TS", "transcripts_ts")
LOTE = int(os.environ.get("TS_BATCH", "200"))
os.makedirs(TSDIR, exist_ok=True)

feitos = set()
for f in glob.glob(os.path.join(TSDIR, "*.jsonl")):
    for ln in open(f, encoding="utf-8", errors="ignore"):
        try:
            feitos.add(json.loads(ln)["video_id"])
        except Exception:
            pass

fila = []
for f in sorted(glob.glob(os.path.join(SRC, "*.jsonl"))):
    canal = os.path.splitext(os.path.basename(f))[0]
    for ln in open(f, encoding="utf-8", errors="ignore"):
        if not ln.strip():
            continue
        try:
            r = json.loads(ln)
        except Exception:
            continue
        v = r.get("video_id")
        if v and v not in feitos:
            fila.append((canal, v))

random.shuffle(fila)
fila = fila[:LOTE]
if not fila:
    print("TIMESTAMPS: corpus completo (todos os videos ja tem os tempos de cada fala)")
    raise SystemExit

TS = re.compile(r"(\d\d):(\d\d):(\d\d)\.(\d\d\d)\s+-->")


def parse_vtt(path):
    """VTT -> [[segundos, texto], ...]  (dedup de linhas repetidas das legendas rolantes)"""
    segs = []
    cur = None
    visto = set()
    for ln in open(path, encoding="utf-8", errors="ignore"):
        ln = ln.rstrip("\n")
        m = TS.search(ln)
        if m:
            h, mi, s, ms = m.groups()
            cur = int(h) * 3600 + int(mi) * 60 + int(s) + int(ms) / 1000.0
            continue
        if cur is None or not ln.strip():
            continue
        txt = re.sub(r"<[^>]+>", "", ln).strip()
        if not txt or txt.startswith(("WEBVTT", "Kind:", "Language:")):
            continue
        if txt in visto:
            continue
        visto.add(txt)
        segs.append([round(cur, 1), txt])
    return segs


ok = err = 0
buf = {}
tmp = tempfile.mkdtemp()
for canal, vid in fila:
    try:
        out = os.path.join(tmp, vid)
        cmd = ["yt-dlp", "--quiet", "--no-warnings", "--skip-download",
               "--write-auto-sub", "--write-sub", "--sub-lang", "pt,pt-BR,en,es",
               "--sub-format", "vtt", "--socket-timeout", "20",
               "-o", out + ".%(ext)s", "https://www.youtube.com/watch?v=" + vid]
        subprocess.run(cmd, timeout=70, capture_output=True)
        vtts = glob.glob(out + "*.vtt")
        if not vtts:
            err += 1
            continue
        segs = parse_vtt(vtts[0])
        for v in vtts:
            try:
                os.remove(v)
            except Exception:
                pass
        if not segs:
            err += 1
            continue
        buf.setdefault(canal, []).append({"video_id": vid, "segments": segs,
                                          "ts": time.strftime("%FT%TZ", time.gmtime())})
        ok += 1
    except Exception:
        err += 1
shutil.rmtree(tmp, ignore_errors=True)

for canal, rows in buf.items():
    with open(os.path.join(TSDIR, canal + ".jsonl"), "a", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")

total = len(feitos) + ok
print("TIMESTAMPS: +%d videos com o tempo de cada fala (%d falharam) | acumulado: %d videos com timestamp real"
      % (ok, err, total))
