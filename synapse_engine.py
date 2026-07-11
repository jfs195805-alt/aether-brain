#!/usr/bin/env python3
"""synapse_engine.py - REDE NEURAL DE VERDADE: pontos -> pares -> TRIANGULOS -> conceitos -> OPORTUNIDADES.

Nao para nos pares. Constroi associacoes de ordem superior sobre o grafo real de frases:

 1) PARES     : ja avaliados (cosseno TF-IDF) - milhoes, exatos.
 2) TRIANGULOS: enumeracao EXATA de todo trio A-B-C mutuamente ligado (3 pontos que se
                complementam). Matematica real, sem amostragem.
 3) PONTES    : triangulos cujos pontos vem de CATEGORIAS e CANAIS diferentes -> insight que
                nenhum canal sozinho tem. Score = similaridade x diversidade x lucro.
 4) CONCEITOS : comunidades (label propagation) = blocos de conhecimento com prova
                (frase + video + timestamp + link).
 5) MEMORIA   : KNOWLEDGE_ETERNO.json acumula PARA SEMPRE; conceito que reaparece ganha peso
                (EWMA), o que nao se confirma decai. Nada e perdido.
 6) PRODUCAO  : as melhores oportunidades entram sozinhas na fila do governador
                (PENDING_ACTIONS.json) -> ele publica com as regras de marca/QA/foto real.

Saidas: SINAPSES.json (site), KNOWLEDGE_ETERNO.json (memoria), PENDING_ACTIONS.json (producao)
"""
import os, json, time, math, hashlib
from collections import defaultdict, Counter
from itertools import combinations

NG = "NEURAL_GRAPH.json"
KE = "KNOWLEDGE_ETERNO.json"
PA = "PENDING_ACTIONS.json"
OUT = "SINAPSES.json"
TOP_OPP = int(os.environ.get("SYN_OPP", "12"))
ALPHA = 0.30          # EWMA do reforco
LIMIAR_PROD = float(os.environ.get("SYN_LIMIAR", "0.35"))

try:
    from classify_phrases import classifica
except Exception:
    def classifica(_):
        return (None, 0)

try:
    g = json.load(open(NG, encoding="utf-8"))
except Exception:
    print("SINAPSES: sem grafo ainda")
    raise SystemExit
nodes = g.get("nodes", [])
edges = g.get("edges", [])
if not nodes or not edges:
    print("SINAPSES: grafo vazio")
    raise SystemExit

lucro = {}
try:
    pm = json.load(open("PROFIT_MODEL.json", encoding="utf-8"))
    lucro = pm.get("por_categoria", pm) or {}
except Exception:
    pass
def lucro_de(c):
    v = lucro.get(c, 0)
    if isinstance(v, dict):
        v = v.get("lucro_1k", 0)
    return float(v or 0)

# categoria de cada ponto (pela FRASE, nao pelo canal)
cat = {}
for n in nodes:
    c, _ = classifica(n.get("frase", ""))
    cat[n["id"]] = c or "Geral"

# adjacencia
adj = defaultdict(set)
w = {}
for a, b, s in edges:
    adj[a].add(b); adj[b].add(a)
    w[(min(a, b), max(a, b))] = float(s)

# ---------- 2) TRIANGULOS EXATOS ----------
tri = []
for (a, b), s_ab in w.items():
    comum = adj[a] & adj[b]
    for cn in comum:
        if cn > b:                      # cada triangulo uma vez
            s_ac = w.get((min(a, cn), max(a, cn)), 0)
            s_bc = w.get((min(b, cn), max(b, cn)), 0)
            tri.append((a, b, cn, (s_ab + s_ac + s_bc) / 3.0))
tri.sort(key=lambda x: -x[3])

# espaco combinatorio REAL (o que existe, mesmo sem enumerar tudo)
N = len(nodes)
espaco_pares = N * (N - 1) // 2
espaco_trios = N * (N - 1) * (N - 2) // 6
espaco_frases = g.get("frases_reais", 0)
espaco_trios_corpus = 0
if espaco_frases > 2:
    # C(frases,3) - o tamanho real do espaco de associacoes de 3 pontos do corpus
    f = float(espaco_frases)
    espaco_trios_corpus = int(f * (f - 1) * (f - 2) / 6)

# ---------- 3) PONTES entre categorias/canais ----------
def npx(i):
    return nodes[i]

pontes = []
for a, b, c, s in tri:
    cats = {cat[a], cat[b], cat[c]}
    cans = {npx(a).get("canal"), npx(b).get("canal"), npx(c).get("canal")}
    if len(cats) < 2 or len(cans) < 2:
        continue
    div = (len(cats) - 1) / 2.0 * 0.6 + (len(cans) - 1) / 2.0 * 0.4
    lu = max(lucro_de(x) for x in cats)
    score = s * (0.55 + 0.45 * div) * (1.0 + math.log1p(lu) / 6.0)
    pontes.append({"score": round(score, 4), "sim": round(s, 3),
                   "categorias": sorted(cats), "canais": sorted(x for x in cans if x),
                   "lucro_1k": lu,
                   "pontos": [{"frase": npx(i)["frase"][:170], "canal": npx(i).get("canal"),
                               "video": npx(i).get("video"), "t": npx(i).get("t"),
                               "link": npx(i).get("link"), "categoria": cat[i]} for i in (a, b, c)]})
pontes.sort(key=lambda x: -x["score"])

# ---------- 4) CONCEITOS (comunidades, label propagation) ----------
lab = {n["id"]: n["id"] for n in nodes}
for _ in range(8):
    mudou = 0
    for n in nodes:
        i = n["id"]
        if not adj[i]:
            continue
        cnt = Counter()
        for j in adj[i]:
            cnt[lab[j]] += w.get((min(i, j), max(i, j)), 0)
        novo = cnt.most_common(1)[0][0]
        if novo != lab[i]:
            lab[i] = novo
            mudou += 1
    if not mudou:
        break
grupos = defaultdict(list)
for i, l in lab.items():
    grupos[l].append(i)
conceitos = []
for l, membros in grupos.items():
    if len(membros) < 3:
        continue
    cs = Counter(cat[i] for i in membros)
    cans = {npx(i).get("canal") for i in membros}
    forca = sum(w.get((min(a, b), max(a, b)), 0) for a, b in combinations(membros[:12], 2))
    conceitos.append({
        "id": hashlib.md5(("|".join(sorted(npx(i)["frase"][:40] for i in membros[:5]))).encode()).hexdigest()[:12],
        "n_pontos": len(membros), "categorias": cs.most_common(3),
        "canais": len(cans), "forca": round(forca, 2),
        "provas": [{"frase": npx(i)["frase"][:150], "link": npx(i).get("link"),
                    "t": npx(i).get("t"), "canal": npx(i).get("canal")} for i in membros[:4]]})
conceitos.sort(key=lambda x: -x["forca"])

# ---------- 5) MEMORIA ETERNA (acumula e reforca) ----------
try:
    ke = json.load(open(KE, encoding="utf-8"))
except Exception:
    ke = {"conceitos": {}, "ciclos": 0}
agora = time.strftime("%FT%TZ", time.gmtime())
novos = reforcados = 0
for cc in conceitos[:80]:
    k = cc["id"]
    if k in ke["conceitos"]:
        old = ke["conceitos"][k]
        old["peso"] = round((1 - ALPHA) * old["peso"] + ALPHA * cc["forca"], 3)
        old["visto"] = old.get("visto", 1) + 1
        old["ultima"] = agora
        reforcados += 1
    else:
        ke["conceitos"][k] = {"peso": round(cc["forca"], 3), "visto": 1,
                              "primeira": agora, "ultima": agora,
                              "categorias": cc["categorias"], "provas": cc["provas"][:2]}
        novos += 1
# decaimento do que nao reapareceu (esquece devagar, nunca apaga)
vistos = {c["id"] for c in conceitos[:80]}
for k, v in ke["conceitos"].items():
    if k not in vistos:
        v["peso"] = round(v["peso"] * 0.97, 3)
ke["ciclos"] = ke.get("ciclos", 0) + 1
ke["ts"] = agora
json.dump(ke, open(KE, "w", encoding="utf-8"), ensure_ascii=False)

# ---------- 6) PRODUCAO AUTOMATICA (fila do governador) ----------
try:
    pend = json.load(open(PA, encoding="utf-8"))
except Exception:
    pend = {"queue": []}
existentes = {a.get("id") for a in pend.get("queue", [])}
enfileiradas = 0
for p in pontes[:TOP_OPP]:
    if p["score"] < LIMIAR_PROD:
        continue
    gid = hashlib.md5(("|".join(x["frase"][:40] for x in p["pontos"])).encode()).hexdigest()[:12]
    if gid in existentes:
        continue
    gancho = " + ".join(x["categorias"] if isinstance(x, str) else "" for x in [])  # placeholder
    tema = " × ".join(p["categorias"])
    pend["queue"].append({
        "id": gid, "tipo": "conteudo_oportunidade",
        "nicho": p["categorias"][0],
        "gancho": tema,
        "descricao_fonte": [x["frase"][:120] for x in p["pontos"]],
        "provas": [x.get("link") for x in p["pontos"] if x.get("link")],
        "lucro_1k": p["lucro_1k"], "score": p["score"],
        "ideias_cruzadas": espaco_pares,
        "origem": "synapse_engine(triangulo cruzando %d categorias / %d canais)" % (len(p["categorias"]), len(p["canais"])),
        "ts": agora})
    existentes.add(gid)
    enfileiradas += 1
json.dump(pend, open(PA, "w", encoding="utf-8"), ensure_ascii=False)

out = {"ts": agora,
       "pontos": N, "pares_ligados": len(edges),
       "triangulos_reais": len(tri),
       "pontes_entre_categorias": len(pontes),
       "conceitos": len(conceitos),
       "espaco_pares": espaco_pares,
       "espaco_trios_grafo": espaco_trios,
       "espaco_trios_corpus": espaco_trios_corpus,
       "memoria_conceitos_acumulados": len(ke["conceitos"]),
       "memoria_ciclos": ke["ciclos"],
       "novos_conceitos": novos, "conceitos_reforcados": reforcados,
       "oportunidades_em_producao": enfileiradas,
       "top_pontes": pontes[:10], "top_conceitos": conceitos[:10]}
json.dump(out, open(OUT, "w", encoding="utf-8"), ensure_ascii=False)
print("SINAPSES: %d triangulos reais | %d pontes entre categorias | %d conceitos | memoria: %d acumulados (+%d novos, %d reforcados) | %d oportunidades -> producao | espaco de trios no corpus: %.3e"
      % (len(tri), len(pontes), len(conceitos), len(ke["conceitos"]), novos, reforcados, enfileiradas, espaco_trios_corpus))
