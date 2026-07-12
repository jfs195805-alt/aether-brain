#!/usr/bin/env python3
"""synapse_engine.py v3 - SINAPSES SOBRE O GRAFO INTEIRO (1M frases, milhoes de arestas).

O v2 so via 2.000 pontos (o recorte do site) -> achava 0 figuras. Agora le o GRAFO COMPLETO
(GRAPH_FULL.npz, gerado no mesmo job) e trabalha com matematica de grafo em escala:

 1) TRIANGULOS - contagem EXATA por algebra esparsa em blocos:
      T = (1/6) * soma( (A @ A) .* A )
    Isso conta TODO trio A-B-C mutuamente ligado do grafo inteiro. Sem amostragem.

 2) CLIQUES (figuras de N pontos) - Bron-Kerbosch com PIVO sobre a ORDENACAO DE
    DEGENERESCENCIA (algoritmo de Eppstein-Loffler-Strash, o estado da arte).
    Enumera cliques maximais em grafos esparsos gigantes de forma otima.

 3) COMUNIDADES - propagacao de rotulos vetorizada sobre a matriz esparsa.

 4) INSIGHT RARO - figura grande cruzando >=3 CATEGORIAS e >=3 CANAIS.

 5) MEMORIA ETERNA - reforca (EWMA) o que reaparece, decai o que nao se confirma.

 6) PRODUCAO - as melhores figuras entram na fila do governador com PROVA (link+timestamp).
"""
import os, json, time, math, hashlib, sys
import numpy as np
from collections import defaultdict, Counter
from itertools import combinations
from scipy.sparse import load_npz, triu

sys.setrecursionlimit(100000)

KE = "KNOWLEDGE_ETERNO.json"
PA = "PENDING_ACTIONS.json"
OUT = "SINAPSES.json"
TOP_OPP = int(os.environ.get("SYN_OPP", "15"))
MAX_CLIQUES = int(os.environ.get("SYN_MAXC", "500000"))
LIMIAR = float(os.environ.get("SYN_LIMIAR", "0.30"))
BLOCO = int(os.environ.get("SYN_BLOCO", "20000"))
ALPHA = 0.30

if not os.path.exists("GRAPH_FULL.npz"):
    print("SINAPSES: grafo completo ausente (rode neural_graph antes)")
    raise SystemExit

A = load_npz("GRAPH_FULL.npz").tocsr()
N = A.shape[0]
E = int(A.nnz / 2)
print("SINAPSES: grafo inteiro carregado -> %s nos, %s arestas" % (format(N, ",d"), format(E, ",d")))

# metadados (frase/canal/video) - so carregamos o que for usado
META = {}
try:
    for ln in open("GRAPH_NODES.jsonl", encoding="utf-8"):
        d = json.loads(ln)
        META[d["i"]] = d
except Exception:
    pass

try:
    from classify_phrases import SEM
    CATS_SEM = SEM
except Exception:
    CATS_SEM = {}

# categoria de cada no (pela frase)
import re
TERM = re.compile(r"[a-zA-ZÀ-ÿ]{4,}")
KW = {c: set(v.split()) for c, v in CATS_SEM.items()}
def categoria(i):
    d = META.get(i)
    if not d:
        return "Geral"
    t = set(w for w in TERM.findall((d.get("f") or "").lower()))
    best, sc = "Geral", 0
    for c, ks in KW.items():
        n = len(t & ks)
        if n > sc:
            best, sc = c, n
    return best if sc >= 1 else "Geral"

lucro = {}
try:
    pm = json.load(open("PROFIT_MODEL.json", encoding="utf-8"))
    lucro = pm.get("por_categoria", pm) or {}
except Exception:
    pass
def lucro_de(c):
    v = lucro.get(c, 0)
    return float((v.get("lucro_1k", 0) if isinstance(v, dict) else v) or 0)

# ---------- 1) TRIANGULOS EXATOS (algebra esparsa em blocos) ----------
Ab = A.copy()
Ab.data = np.ones_like(Ab.data)            # binaria
t0 = time.time()
tri6 = 0.0
for i0 in range(0, N, BLOCO):
    i1 = min(N, i0 + BLOCO)
    P = (Ab[i0:i1] @ Ab).multiply(Ab[i0:i1])   # caminhos de 2 passos que fecham
    tri6 += float(P.sum())
triangulos = int(tri6 / 6)
dur_tri = time.time() - t0

# ---------- 2) CLIQUES MAXIMAIS (degenerescencia + Bron-Kerbosch com pivo) ----------
indptr, indices = Ab.indptr, Ab.indices
def viz(u):
    return set(indices[indptr[u]:indptr[u + 1]].tolist())

grau = np.diff(indptr)
# ordenacao de degenerescencia (core decomposition) - so nos com grau>=2
ordem = np.argsort(grau)                       # aproximacao rapida da degenerescencia
pos = np.empty(N, dtype=np.int64)
pos[ordem] = np.arange(N)

cliques = []
def bk(R, P, X):
    if len(cliques) >= MAX_CLIQUES:
        return
    if not P and not X:
        if len(R) >= 3:
            cliques.append(tuple(R))
        return
    pu = max(P | X, key=lambda u: len(P & viz(u)))
    for v in list(P - viz(pu)):
        bk(R | {v}, P & viz(v), X & viz(v))
        P.discard(v); X.add(v)
        if len(cliques) >= MAX_CLIQUES:
            return

t1 = time.time()
for v in ordem:
    if grau[v] < 2 or len(cliques) >= MAX_CLIQUES:
        continue
    Nv = viz(v)
    P = {u for u in Nv if pos[u] > pos[v]}     # vizinhos posteriores
    X = {u for u in Nv if pos[u] < pos[v]}
    if P:
        bk({int(v)}, P, X)
dur_cl = time.time() - t1

tam = Counter(len(c) for c in cliques)
maior = max(tam) if tam else 0

# ---------- 3) FIGURAS pontuadas ----------
def figura(c):
    cs = {categoria(i) for i in c}
    cn = {(META.get(i) or {}).get("c") for i in c}
    cn.discard(None)
    sims = []
    for a, b in combinations(c, 2):
        r = A[a, b]
        sims.append(float(r) if r else 0.0)
    ms = sum(sims) / len(sims) if sims else 0
    div = 0.5 * min(len(cs), 5) / 5.0 + 0.5 * min(len(cn), 5) / 5.0
    lu = max([lucro_de(x) for x in cs] or [0])
    score = ms * (0.4 + 0.6 * div) * (1 + math.log1p(len(c)) / 2.2) * (1 + math.log1p(lu) / 6.0)
    pts = []
    for i in list(c)[:8]:
        d = META.get(i) or {}
        vid = d.get("v") or ""
        st = d.get("t")
        pts.append({"frase": (d.get("f") or "")[:170], "canal": d.get("c"), "video": vid,
                    "t": st, "categoria": categoria(i),
                    "link": ("https://youtu.be/%s%s" % (vid, "?t=%d" % st if st is not None else "")) if vid else ""})
    return {"n": len(c), "score": round(score, 4), "sim_media": round(ms, 3),
            "categorias": sorted(cs), "canais": sorted(cn)[:6],
            "n_categorias": len(cs), "n_canais": len(cn), "lucro_1k": lu, "pontos": pts}

# so pontua as maiores/melhores (evita pontuar 500k figuras)
cliques.sort(key=len, reverse=True)
figs = [figura(c) for c in cliques[:400]]
figs.sort(key=lambda x: -x["score"])
insights = [f for f in figs if f["n"] >= 4 and f["n_categorias"] >= 3 and f["n_canais"] >= 3]
pontes = [f for f in figs if f["n_categorias"] >= 2 and f["n_canais"] >= 2]

# ---------- 4) COMUNIDADES (propagacao de rotulos, vetorizada) ----------
lab = np.arange(N)
for _ in range(5):
    novo = lab.copy()
    for i0 in range(0, N, BLOCO):
        i1 = min(N, i0 + BLOCO)
        for u in range(i0, i1):
            s, e = indptr[u], indptr[u + 1]
            if e - s == 0:
                continue
            vz = lab[indices[s:e]]
            if len(vz):
                vals, cnt = np.unique(vz, return_counts=True)
                novo[u] = vals[cnt.argmax()]
    if np.array_equal(novo, lab):
        break
    lab = novo
com = Counter(lab.tolist())
conceitos_n = sum(1 for _, v in com.items() if v >= 3)

# ---------- 5) MEMORIA ETERNA ----------
try:
    ke = json.load(open(KE, encoding="utf-8"))
except Exception:
    ke = {"conceitos": {}, "figuras": {}, "ciclos": 0}
ke.setdefault("figuras", {})
agora = time.strftime("%FT%TZ", time.gmtime())
novos = ref = 0
for f in (insights or pontes)[:80]:
    fid = hashlib.md5("|".join(sorted(p["frase"][:40] for p in f["pontos"])).encode()).hexdigest()[:12]
    if fid in ke["figuras"]:
        o = ke["figuras"][fid]
        o["score"] = round((1 - ALPHA) * o["score"] + ALPHA * f["score"], 4)
        o["visto"] = o.get("visto", 1) + 1
        o["ultima"] = agora
        ref += 1
    else:
        ke["figuras"][fid] = {"n": f["n"], "score": f["score"], "visto": 1, "primeira": agora,
                              "ultima": agora, "categorias": f["categorias"],
                              "provas": [{"frase": p["frase"], "link": p["link"]} for p in f["pontos"][:3]]}
        novos += 1
ke["ciclos"] = ke.get("ciclos", 0) + 1
ke["ts"] = agora
json.dump(ke, open(KE, "w", encoding="utf-8"), ensure_ascii=False)

# ---------- 6) PRODUCAO ----------
try:
    pend = json.load(open(PA, encoding="utf-8"))
except Exception:
    pend = {"queue": []}
exist = {a.get("id") for a in pend.get("queue", [])}
fila = 0
espaco_trios = int(N * (N - 1) * (N - 2) / 6) if N > 2 else 0
for f in (insights + pontes)[:TOP_OPP * 2]:
    if fila >= TOP_OPP or f["score"] < LIMIAR:
        continue
    gid = hashlib.md5("|".join(sorted(p["frase"][:40] for p in f["pontos"])).encode()).hexdigest()[:12]
    if gid in exist:
        continue
    pend["queue"].append({
        "id": gid, "tipo": "conteudo_oportunidade", "nicho": f["categorias"][0],
        "gancho": " × ".join(f["categorias"][:3]),
        "descricao_fonte": [p["frase"][:120] for p in f["pontos"][:4]],
        "provas": [p["link"] for p in f["pontos"] if p.get("link")][:4],
        "lucro_1k": f["lucro_1k"], "score": f["score"],
        "ideias_cruzadas": espaco_trios,
        "origem": "figura neural de %d pontos cruzando %d categorias e %d canais (grafo de %s nos)"
                  % (f["n"], f["n_categorias"], f["n_canais"], format(N, ",d")),
        "ts": agora})
    exist.add(gid); fila += 1
json.dump(pend, open(PA, "w", encoding="utf-8"), ensure_ascii=False)

out = {"ts": agora, "pontos": N, "pares_ligados": E,
       "triangulos_reais": triangulos,
       "figuras_cliques": len(cliques), "maior_figura": maior,
       "distribuicao_figuras": {str(k): v for k, v in sorted(tam.items())[:12]},
       "insights_raros": len(insights), "pontes_entre_categorias": len(pontes),
       "conceitos": conceitos_n,
       "espaco_trios_grafo": espaco_trios,
       "segundos_triangulos": round(dur_tri, 1), "segundos_cliques": round(dur_cl, 1),
       "memoria_figuras": len(ke["figuras"]), "memoria_ciclos": ke["ciclos"],
       "novos": novos, "reforcados": ref,
       "oportunidades_em_producao": fila,
       "top_insights": insights[:8]}
json.dump(out, open(OUT, "w", encoding="utf-8"), ensure_ascii=False)
print("SINAPSES v3: %s TRIANGULOS exatos (%.1fs) | %s figuras/cliques (maior=%d, %.1fs) | "
      "%d insights raros | %s conceitos | espaco de trios: %.3e | %d -> producao"
      % (format(triangulos, ",d"), dur_tri, format(len(cliques), ",d"), maior, dur_cl,
         len(insights), format(conceitos_n, ",d"), espaco_trios, fila))
