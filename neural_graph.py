#!/usr/bin/env python3
"""neural_graph.py - GRAFO NEURAL REAL (roda na RAM de 16GB do GitHub Actions).

Pontos  = frases/afirmacoes REAIS extraidas dos milhares de videos (cada no carrega a frase e o canal).
Sinapses= cruzamento estatistico REAL entre esses pontos: co-ocorrencia + PMI (associacao),
          calculado vetorizado em numpy sobre todo o corpus (milhoes de pares avaliados).
Saida   : NEURAL_GRAPH.json  {nodes:[{id,label,frase,canal,peso}], edges:[[i,j,pmi,co]], ...}
"""
import os, re, json, glob, time
import numpy as np
from collections import Counter

SRC   = os.environ.get("NG_SRC", "transcripts")
OUT   = os.environ.get("NG_OUT", "NEURAL_GRAPH.json")
MAXR  = int(os.environ.get("NG_RECS", "250"))
V     = int(os.environ.get("NG_V", "1500"))
NODES = int(os.environ.get("NG_NODES", "700"))
EDGES = int(os.environ.get("NG_EDGES", "6000"))

STOP = set(("a o e de da do das dos que em um uma para com nao os as no na por mais como mas ao se ou ja "
            "isso esse essa este esta muito voce tem ser sao foi vai pode entao aqui tudo todo toda bem "
            "ainda pra pro sobre quando onde qual quais eu meu minha nos eles elas ele ela cara gente coisa "
            "fazer faz feito ter tinha seu sua the of and to in is it you that this for on with are be as at "
            "your we can will have has from they our my me just about what which who them there their more "
            "than then would could should").split())
W    = re.compile(r"[a-zA-ZÀ-ÿ]{4,}")
SENT = re.compile(r"[^.!?\n]{40,190}[.!?]")

files = sorted(glob.glob(os.path.join(SRC, "**", "*.jsonl"), recursive=True))
docs = []
sent_by_term = {}
nv = 0
canais = set()

for f in files:
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
        txt = r.get("text") or r.get("transcript") or r.get("desc") or ""
        if isinstance(txt, list):
            txt = " ".join(str(x) for x in txt)
        if len(txt) < 80:
            continue
        nv += 1
        toks = set(w for w in W.findall(txt.lower()) if w not in STOP)
        if len(toks) < 8:
            continue
        docs.append(toks)
        for s in SENT.findall(txt)[:8]:
            s = s.strip()
            for w in set(W.findall(s.lower())):
                if w in STOP or w in sent_by_term:
                    continue
                sent_by_term[w] = (s, canal)

if not docs:
    json.dump({"nodes": [], "edges": [], "erro": "sem corpus"}, open(OUT, "w"))
    raise SystemExit

cnt = Counter()
for d in docs:
    cnt.update(d)
vocab = [w for w, _ in cnt.most_common(V)]
idx = {w: i for i, w in enumerate(vocab)}

# matriz documento-termo -> co-ocorrencia real entre TODOS os pares (vetorizado)
M = np.zeros((len(docs), len(vocab)), dtype=np.float32)
for r, d in enumerate(docs):
    for w in d:
        j = idx.get(w)
        if j is not None:
            M[r, j] = 1.0
CO = M.T @ M
N = float(len(docs))
p = np.diag(CO) / N
P = CO / N
with np.errstate(divide="ignore", invalid="ignore"):
    PMI = np.log(P / (np.outer(p, p) + 1e-12) + 1e-12)
np.fill_diagonal(PMI, -99)
pares = len(vocab) * (len(vocab) - 1) // 2

order = np.argsort(-np.diag(CO))[:NODES]
nodes = []
for k, j in enumerate(order):
    w = vocab[j]
    fr, canal = sent_by_term.get(w, ("", ""))
    nodes.append({"id": int(k), "label": w, "frase": fr[:170], "canal": canal, "peso": int(CO[j, j])})

oj = [int(x) for x in order]
sub = PMI[np.ix_(oj, oj)]
subco = CO[np.ix_(oj, oj)]
iu = np.triu_indices(len(oj), 1)
vals = sub[iu]
cos = subco[iu]
vi = np.where(cos >= 3)[0]
top = vi[np.argsort(-vals[vi])][:EDGES]
edges = [[int(iu[0][t]), int(iu[1][t]), round(float(vals[t]), 3), int(cos[t])] for t in top]

out = {"ts": time.strftime("%FT%TZ", time.gmtime()), "videos_amostrados": nv, "canais": len(canais),
       "vocab": len(vocab), "pares_avaliados": pares, "docs": len(docs), "nodes": nodes, "edges": edges}
json.dump(out, open(OUT, "w", encoding="utf-8"), ensure_ascii=False)
print("GRAFO REAL: %d pontos, %d sinapses | %d videos, %d canais, %d pares avaliados"
      % (len(nodes), len(edges), nv, len(canais), pares))
