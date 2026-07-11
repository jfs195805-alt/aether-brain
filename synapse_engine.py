#!/usr/bin/env python3
"""synapse_engine.py v2 - CEREBRO NEURAL MATEMATICO: pares -> triangulos -> CLIQUES (figuras de N pontos).

Nao para nos pares nem nos triangulos. Enumera as FIGURAS reais da rede:

  CLIQUES MAXIMAIS (Bron-Kerbosch com pivo): conjuntos onde TODOS os pontos se ligam a TODOS.
  Um clique de 7 pontos = 7 afirmacoes de videos/canais diferentes que se sustentam mutuamente.
  Isso e uma IDEIA COMPOSTA, exata, nao amostrada. Sao milhares delas.

  INSIGHT RARO = clique grande (>=4) cruzando >=3 CATEGORIAS e >=3 CANAIS diferentes.
  Ninguem tem esse cruzamento porque ninguem cruzou 1 milhao de frases de 592 canais.

  CONCEITOS   = comunidades (label propagation).
  MEMORIA     = KNOWLEDGE_ETERNO.json: reforca (EWMA) o que reaparece, decai o que nao se
                confirma. Acumula para sempre.
  PRODUCAO    = as melhores figuras entram sozinhas na fila do governador (PENDING_ACTIONS.json).

Saidas: SINAPSES.json, KNOWLEDGE_ETERNO.json, PENDING_ACTIONS.json
"""
import os, json, time, math, hashlib, sys
from collections import defaultdict, Counter
from itertools import combinations

sys.setrecursionlimit(10000)

NG = "NEURAL_GRAPH.json"
KE = "KNOWLEDGE_ETERNO.json"
PA = "PENDING_ACTIONS.json"
OUT = "SINAPSES.json"
TOP_OPP = int(os.environ.get("SYN_OPP", "15"))
MAX_CLIQUES = int(os.environ.get("SYN_MAXC", "200000"))
LIMIAR = float(os.environ.get("SYN_LIMIAR", "0.30"))
ALPHA = 0.30

try:
    from classify_phrases import classifica
except Exception:
    def classifica(_):
        return (None, 0)

try:
    g = json.load(open(NG, encoding="utf-8"))
except Exception:
    print("SINAPSES: sem grafo"); raise SystemExit
nodes, edges = g.get("nodes", []), g.get("edges", [])
if not nodes or not edges:
    print("SINAPSES: grafo vazio"); raise SystemExit

lucro = {}
try:
    pm = json.load(open("PROFIT_MODEL.json", encoding="utf-8"))
    lucro = pm.get("por_categoria", pm) or {}
except Exception:
    pass
def lucro_de(c):
    v = lucro.get(c, 0)
    return float((v.get("lucro_1k", 0) if isinstance(v, dict) else v) or 0)

cat = {}
for n in nodes:
    c, _ = classifica(n.get("frase", ""))
    cat[n["id"]] = c or "Geral"

adj = defaultdict(set)
w = {}
for a, b, s in edges:
    adj[a].add(b); adj[b].add(a)
    w[(min(a, b), max(a, b))] = float(s)
def sim(a, b):
    return w.get((min(a, b), max(a, b)), 0.0)

# ---------- CLIQUES MAXIMAIS (Bron-Kerbosch com pivo) ----------
cliques = []
def bk(R, P, X):
    if len(cliques) >= MAX_CLIQUES:
        return
    if not P and not X:
        if len(R) >= 3:
            cliques.append(sorted(R))
        return
    pivo = max(P | X, key=lambda u: len(adj[u]))
    for v in list(P - adj[pivo]):
        bk(R | {v}, P & adj[v], X & adj[v])
        P.remove(v); X.add(v)
        if len(cliques) >= MAX_CLIQUES:
            return
bk(set(), set(adj.keys()), set())

tam = Counter(len(c) for c in cliques)
maior = max(tam) if tam else 0

# triangulos (subconjunto: figuras de 3) - contagem exata
n_tri = 0
for (a, b) in w:
    n_tri += len(adj[a] & adj[b])
n_tri //= 3

# ---------- FIGURAS pontuadas: insight raro ----------
def figura(c):
    cats = {cat[i] for i in c}
    cans = {nodes[i].get("canal") for i in c if nodes[i].get("canal")}
    s = [sim(a, b) for a, b in combinations(c, 2)]
    ms = sum(s) / len(s) if s else 0
    div = 0.5 * min(len(cats), 5) / 5.0 + 0.5 * min(len(cans), 5) / 5.0
    lu = max([lucro_de(x) for x in cats] or [0])
    score = ms * (0.4 + 0.6 * div) * (1 + math.log1p(len(c)) / 2.2) * (1 + math.log1p(lu) / 6.0)
    return {"n": len(c), "score": round(score, 4), "sim_media": round(ms, 3),
            "categorias": sorted(cats), "canais": sorted(cans)[:6],
            "n_categorias": len(cats), "n_canais": len(cans), "lucro_1k": lu,
            "pontos": [{"frase": nodes[i]["frase"][:170], "canal": nodes[i].get("canal"),
                        "video": nodes[i].get("video"), "t": nodes[i].get("t"),
                        "link": nodes[i].get("link"), "categoria": cat[i]} for i in c[:8]],
            "ids": c}

figs = [figura(c) for c in cliques]
figs.sort(key=lambda x: -x["score"])
insights = [f for f in figs if f["n"] >= 4 and f["n_categorias"] >= 3 and f["n_canais"] >= 3]
pontes = [f for f in figs if f["n_categorias"] >= 2 and f["n_canais"] >= 2]

# ---------- CONCEITOS (comunidades) ----------
lab = {n["id"]: n["id"] for n in nodes}
for _ in range(8):
    mud = 0
    for n in nodes:
        i = n["id"]
        if not adj[i]:
            continue
        cnt = Counter()
        for j in adj[i]:
            cnt[lab[j]] += sim(i, j)
        nv = cnt.most_common(1)[0][0]
        if nv != lab[i]:
            lab[i] = nv; mud += 1
    if not mud:
        break
grp = defaultdict(list)
for i, l in lab.items():
    grp[l].append(i)
conceitos = []
for l, m in grp.items():
    if len(m) < 3:
        continue
    forca = sum(sim(a, b) for a, b in combinations(m[:12], 2))
    conceitos.append({"id": hashlib.md5("|".join(sorted(nodes[i]["frase"][:40] for i in m[:5])).encode()).hexdigest()[:12],
                      "n_pontos": len(m), "forca": round(forca, 2),
                      "categorias": Counter(cat[i] for i in m).most_common(3),
                      "canais": len({nodes[i].get("canal") for i in m}),
                      "provas": [{"frase": nodes[i]["frase"][:150], "link": nodes[i].get("link"),
                                  "t": nodes[i].get("t"), "canal": nodes[i].get("canal")} for i in m[:4]]})
conceitos.sort(key=lambda x: -x["forca"])

# ---------- MEMORIA ETERNA ----------
try:
    ke = json.load(open(KE, encoding="utf-8"))
except Exception:
    ke = {"conceitos": {}, "figuras": {}, "ciclos": 0}
ke.setdefault("figuras", {})
agora = time.strftime("%FT%TZ", time.gmtime())
novos = ref = 0
for cc in conceitos[:100]:
    k = cc["id"]
    if k in ke["conceitos"]:
        o = ke["conceitos"][k]
        o["peso"] = round((1 - ALPHA) * o["peso"] + ALPHA * cc["forca"], 3)
        o["visto"] = o.get("visto", 1) + 1; o["ultima"] = agora; ref += 1
    else:
        ke["conceitos"][k] = {"peso": round(cc["forca"], 3), "visto": 1, "primeira": agora,
                              "ultima": agora, "categorias": cc["categorias"], "provas": cc["provas"][:2]}
        novos += 1
vistos = {c["id"] for c in conceitos[:100]}
for k, v in ke["conceitos"].items():
    if k not in vistos:
        v["peso"] = round(v["peso"] * 0.97, 3)
# figuras raras tambem viram memoria permanente
for f in insights[:60]:
    fid = hashlib.md5("|".join(sorted(p["frase"][:40] for p in f["pontos"])).encode()).hexdigest()[:12]
    if fid in ke["figuras"]:
        ke["figuras"][fid]["visto"] += 1
        ke["figuras"][fid]["score"] = round((1 - ALPHA) * ke["figuras"][fid]["score"] + ALPHA * f["score"], 4)
        ke["figuras"][fid]["ultima"] = agora
    else:
        ke["figuras"][fid] = {"n": f["n"], "score": f["score"], "visto": 1, "primeira": agora,
                              "ultima": agora, "categorias": f["categorias"],
                              "provas": [{"frase": p["frase"], "link": p["link"]} for p in f["pontos"][:3]]}
ke["ciclos"] = ke.get("ciclos", 0) + 1
ke["ts"] = agora
json.dump(ke, open(KE, "w", encoding="utf-8"), ensure_ascii=False)

# ---------- PRODUCAO AUTOMATICA ----------
try:
    pend = json.load(open(PA, encoding="utf-8"))
except Exception:
    pend = {"queue": []}
exist = {a.get("id") for a in pend.get("queue", [])}
fila = 0
espaco_pares = len(nodes) * (len(nodes) - 1) // 2
for f in (insights + pontes)[:TOP_OPP * 2]:
    if fila >= TOP_OPP or f["score"] < LIMIAR:
        continue
    gid = hashlib.md5("|".join(sorted(p["frase"][:40] for p in f["pontos"])).encode()).hexdigest()[:12]
    if gid in exist:
        continue
    pend["queue"].append({
        "id": gid, "tipo": "conteudo_oportunidade",
        "nicho": f["categorias"][0],
        "gancho": " × ".join(f["categorias"][:3]),
        "descricao_fonte": [p["frase"][:120] for p in f["pontos"][:4]],
        "provas": [p["link"] for p in f["pontos"] if p.get("link")][:4],
        "lucro_1k": f["lucro_1k"], "score": f["score"],
        "ideias_cruzadas": espaco_pares,
        "origem": "figura neural de %d pontos cruzando %d categorias e %d canais"
                  % (f["n"], f["n_categorias"], f["n_canais"]),
        "ts": agora})
    exist.add(gid); fila += 1
json.dump(pend, open(PA, "w", encoding="utf-8"), ensure_ascii=False)

N = len(nodes)
f_ = float(g.get("frases_reais", 0) or 0)
espaco_trios_corpus = int(f_ * (f_ - 1) * (f_ - 2) / 6) if f_ > 2 else 0
out = {"ts": agora, "pontos": N, "pares_ligados": len(edges),
       "triangulos_reais": n_tri,
       "figuras_cliques": len(cliques),
       "maior_figura": maior,
       "distribuicao_figuras": {str(k): v for k, v in sorted(tam.items())},
       "insights_raros": len(insights),
       "pontes_entre_categorias": len(pontes),
       "conceitos": len(conceitos),
       "espaco_pares_grafo": espaco_pares,
       "espaco_trios_corpus": espaco_trios_corpus,
       "memoria_conceitos": len(ke["conceitos"]), "memoria_figuras": len(ke["figuras"]),
       "memoria_ciclos": ke["ciclos"], "novos": novos, "reforcados": ref,
       "oportunidades_em_producao": fila,
       "top_insights": insights[:8], "top_conceitos": conceitos[:8]}
json.dump(out, open(OUT, "w", encoding="utf-8"), ensure_ascii=False)
print("SINAPSES v2: %d figuras (cliques) | maior=%d pontos | %d triangulos | %d INSIGHTS RAROS "
      "(>=4 pontos, >=3 categorias, >=3 canais) | %d conceitos | memoria: %d conceitos + %d figuras "
      "(ciclo %d) | %d oportunidades -> producao"
      % (len(cliques), maior, n_tri, len(insights), len(conceitos),
         len(ke["conceitos"]), len(ke["figuras"]), ke["ciclos"], fila))
