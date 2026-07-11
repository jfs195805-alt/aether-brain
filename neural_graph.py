#!/usr/bin/env python3
"""neural_graph.py - GRAFO NEURAL REAL, FRASE-A-FRASE (RAM 16GB do GitHub Actions).

Cada PONTO  = uma FRASE REAL da transcricao de um video (com video_id, canal e, quando
              disponivel no corpus de segmentos, o TIMESTAMP real + link direto).
Cada LINHA  = cruzamento estatistico REAL entre duas frases (cosseno sobre TF-IDF dos termos),
              calculado vetorizado em numpy sobre todo o corpus.

Le:  transcripts/*.jsonl        (registros: video_id, handle, transcript)
     transcripts_ts/*.jsonl     (opcional: video_id, segments [[start, texto], ...])  <- timestamps reais
Escreve: NEURAL_GRAPH.json
"""
import os, re, json, glob, time
import numpy as np
from collections import Counter

SRC   = os.environ.get("NG_SRC", "transcripts")
TSDIR = os.environ.get("NG_TS", "transcripts_ts")
OUT   = os.environ.get("NG_OUT", "NEURAL_GRAPH.json")
MAXR  = int(os.environ.get("NG_RECS", "400"))     # videos por canal
V     = int(os.environ.get("NG_V", "4000"))       # vocabulario de termos
CAND  = int(os.environ.get("NG_CAND", "3000"))    # frases candidatas (todas cruzadas entre si)
NODES = int(os.environ.get("NG_NODES", "800"))    # frases exibidas no grafo
EDGES = int(os.environ.get("NG_EDGES", "6000"))   # sinapses exibidas

STOP = set(("a o e de da do das dos que em um uma para com nao os as no na por mais como mas ao se ou ja "
            "isso esse essa este esta muito voce tem ser sao foi vai pode entao aqui tudo todo toda bem "
            "ainda pra pro sobre quando onde qual quais eu meu minha nos eles elas ele ela cara gente coisa "
            "fazer faz feito ter tinha seu sua the of and to in is it you that this for on with are be as at "
            "your we can will have has from they our my me just about what which who them there their more "
            "than then would could should music").split())
W    = re.compile(r"[a-zA-ZÀ-ÿ]{4,}")
SPLIT = re.compile(r"(?<=[.!?])\s+|\n+")

# ---------- 1) carrega TIMESTAMPS reais (se ja existirem) ----------
TS = {}   # video_id -> [(start, texto), ...]
for f in glob.glob(os.path.join(TSDIR, "**", "*.jsonl"), recursive=True):
    for ln in open(f, encoding="utf-8", errors="ignore"):
        if not ln.strip():
            continue
        try:
            r = json.loads(ln)
            TS[r["video_id"]] = r.get("segments") or []
        except Exception:
            pass

def ts_for(vid, frase):
    """timestamp REAL da frase (via segmentos). None se o corpus ainda nao tem os tempos."""
    segs = TS.get(vid)
    if not segs:
        return None
    key = frase[:28].lower()
    for s in segs:
        try:
            if key and key in str(s[1]).lower():
                return int(float(s[0]))
        except Exception:
            continue
    return None

# ---------- 2) TODAS as frases de TODOS os videos ----------
frases = []          # (texto, video_id, canal)
total_frases = 0
nv = 0
canais = set()
for f in sorted(glob.glob(os.path.join(SRC, "**", "*.jsonl"), recursive=True)):
    canal = os.path.splitext(os.path.basename(f))[0]
    canais.add(canal)
    try:
        lines = open(f, encoding="utf-8", errors="ignore").read().split("\n")[:MAXR]
    except Exception:
        continue
    for ln in lines:
        if not ln.strip():
            continue
        try:
            r = json.loads(ln)
        except Exception:
            continue
        txt = r.get("transcript") or r.get("text") or ""
        if isinstance(txt, list):
            txt = " ".join(str(x) for x in txt)
        if len(txt) < 80:
            continue
        nv += 1
        vid = r.get("video_id", "")
        for s in SPLIT.split(txt):
            s = s.strip()
            if 45 <= len(s) <= 240:
                total_frases += 1
                frases.append((s, vid, canal))

if not frases:
    json.dump({"nodes": [], "edges": [], "erro": "sem corpus"}, open(OUT, "w"))
    raise SystemExit

# ---------- 3) vocabulario + TF-IDF de TODAS as frases ----------
df = Counter()
toks_all = []
for s, _, _ in frases:
    t = set(w for w in W.findall(s.lower()) if w not in STOP)
    toks_all.append(t)
    df.update(t)
vocab = [w for w, _ in df.most_common(V) if df[w] >= 3]
idx = {w: i for i, w in enumerate(vocab)}
N = float(len(frases))
IDF = np.array([np.log(N / (1.0 + df[w])) for w in vocab], dtype=np.float32)

# score de informacao de cada frase = soma do