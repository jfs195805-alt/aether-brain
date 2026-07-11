#!/usr/bin/env python3
"""backfill_ts.py - recupera os TIMESTAMPS REAIS de cada fala dos videos ja transcritos.

O corpus atual guarda a transcricao como texto corrido (sem tempos). Este script busca a
transcricao SEGMENTADA (o YouTube devolve start+texto de cada fala, de graca, sem API key)
e grava em transcripts_ts/<canal>.jsonl  ->  {video_id, segments: [[start, texto], ...]}

Incremental: processa LOTE videos por execucao (barato, roda toda rodada no GitHub Actions).
Assim, a cada rodada mais frases do grafo ganham timestamp real e link direto youtu.be/ID?t=SEG.
"""
import os, json, glob, time, random

SRC   = os.environ.get("NG_SRC", "transcripts")
TSDIR = os.environ.get("NG_TS", "transcripts_ts")
LOTE  = int(os.environ.get("TS_BATCH", "250"))

os.makedirs(TSDIR, exist_ok=True)

# ja processados
feitos = set()
for f in glob.glob(os.path.join(TSDIR, "*.jsonl")):
    for ln in open(f, encoding="utf-8", errors="ignore"):
        try:
            feitos.add(json.loads(ln)["video_id"])
        except Exception:
            pass

# fila: videos do corpus que ainda nao tem timestamps
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
        vid = r.get("video_id")
        if vid and vid not in feitos:
            fila.append((canal, vid))

random.shuffle(fila)
fila = fila[:LOTE]
if not fila:
    print("TIMESTAMPS: nada pendente (todos os videos ja tem tempos reais)")
    raise SystemExit

try:
    from youtube_transcript_api import YouTubeTranscriptApi
except Exception:
    print("TIMESTAMPS: youtube_transcript_api indisponivel")
    raise SystemExit

ok = err = 0
buf = {}
for canal, vid in fila:
    try:
        tr = None
        try:
            tr = YouTubeTranscriptApi.get_transcript(vid, languages=["pt", "pt-BR", "en", "es"])
        except Exception:
            lst = YouTubeTranscriptApi.list_transcripts(vid)
            for t in lst:
                tr = t.fetch()
                break
        if not tr:
            err += 1
            continue
        segs = [[round(float(s.get("start", 0)), 1), (s.get("text") or "").strip()]
                for s in tr if (s.get("text") or "").strip()]
        if not segs:
            err += 1
            continue
        buf.setdefault(canal, []).append({"video_id": vid, "segments": segs,
                                          "ts": time.strftime("%FT%TZ", time.gmtime())})
        ok += 1
    except Exception:
        err += 1
    time.sleep(0.15)   # educado com o YouTube

for canal, rows in buf.items():
    with open(os.path.join(TSDIR, canal + ".jsonl"), "a", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")

restante = 0
print("TIMESTAMPS: +%d videos com tempos reais de cada fala (%d falharam) -> %s/"
      % (ok, err, TSDIR))
