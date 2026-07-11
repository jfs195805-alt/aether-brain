"""brain_memory.py — CEREBRO INTERNO que ACUMULA aprendizado (offline, gratis, sem internet, sem IA).
Junta dados FRESCOS (profit_model + results + ideias mineradas) com a MEMORIA anterior, atualiza
HIPOTESES por nicho (media movel/EWMA), cruza ideias em HIPOTESES COMPOSTAS, decide o NEXT BEST
por matematica, e ESCREVE na memoria que cresce sozinha. Liga no Obsidian (vault) e no grafo (Graphiti).
IA e opcional: isto roda sem token nenhum, sempre."""
import os, json, time, math

def load(p, d=None):
    try: return json.load(open(p, encoding="utf-8"))
    except Exception: return d

prof = load("PROFIT_MODEL.json", {}) or {}
res = load("RESULTS.json", {}) or {}
uni = load("AETHER_UNIFICADO.json", {}) or {}
mem = load("BRAIN_MEMORY.json", {}) or {"hypotheses": {}, "history": [], "cycles": 0}

# --- dados frescos ---
niche_profit = {str(x.get("niche", "")).lower(): float(x.get("exp_organic_per_1000", 0)) for x in prof.get("niches", [])}
niche_views = {}
for v in res.get("videos", []):
    n = (v.get("niche") or "").lower()
    if n: niche_views[n] = niche_views.get(n, 0) + int(v.get("views", 0))
idea_support = {}
for it in uni.get("ideias", []):
    s = str(it.get("ideia", "")).lower()
    for n in niche_profit:
        if n and any(w in s for w in n.split("/")[0].split()):
            idea_support[n] = idea_support.get(n, 0) + 1

# --- atualiza HIPOTESES (acumula com EWMA) ---
hyp = mem.get("hypotheses", {})
for n, pf in niche_profit.items():
    h = hyp.setdefault(n, {"n": 0, "profit_ewma": pf, "views": 0, "support": 0, "score": 0.0})
    h["profit_ewma"] = round(0.6 * float(h.get("profit_ewma", pf)) + 0.4 * pf, 1)
    h["views"] = int(niche_views.get(n, 0))
    h["support"] = int(idea_support.get(n, 0))
    conf = min(1.0, h["support"] / 50.0)
    h["score"] = round(h["profit_ewma"] * (0.5 + 0.5 * conf) * (1 + math.log1p(h["views"]) / 10.0), 1)
    h["n"] = int(h.get("n", 0)) + 1
mem["hypotheses"] = hyp

ranked = sorted(hyp.items(), key=lambda kv: -kv[1]["score"])
top = [n for n, _ in ranked[:6]]

# --- HIPOTESES COMPOSTAS (cruzamento de ideias) ---
inter = load("INTERLINK.json", {}) or {}
BRIDGES = inter.get("pontes_entre_nichos", [])
HOOKS = ["curiosity-gap hook", "price-shock POV", "'3 things nobody tells you'", "before/after proof", "silent try-on (no voice)"]
compounds = []
for n, _ in ranked[:4]:
    for hk in HOOKS[:3]:
        compounds.append("%s -> aplicar em %s" % (hk, n))
for b in BRIDGES[:8]:
    compounds.append("ponte %s x %s via %s" % (b.get("a"), b.get("b"), ", ".join(b.get("shared", [])[:3])))
mem["compostas"] = compounds[:20]

# --- NEXT BEST (decisao offline, sem IA) ---
mem["next_best"] = ranked[0][0] if ranked else ""
mem["next_best_score"] = ranked[0][1]["score"] if ranked else 0
mem["cycles"] = int(mem.get("cycles", 0)) + 1
mem["ts"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
hist = mem.get("history", [])
hist.append({"ts": mem["ts"], "top": top[:3], "next_best": mem["next_best"], "score": mem["next_best_score"]})
mem["history"] = hist[-200:]

json.dump(mem, open("BRAIN_MEMORY.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
os.makedirs("vault", exist_ok=True)
with open("vault/BRAIN_MEMORY.md", "w", encoding="utf-8") as f:
    f.write("# BRAIN MEMORY — aprendizado acumulado (offline, cresce sozinho)\n\n")
    f.write("Ciclos: %d | atualizado: %s | NEXT BEST: **%s** (score %.1f)\n\n" % (mem["cycles"], mem["ts"], mem["next_best"], mem["next_best_score"]))
    f.write("## Hipoteses por nicho (score = lucro x confianca x views)\n\n")
    for n, h in ranked[:15]:
        f.write("- **%s** — score %.1f | lucro/1k $%.0f | views %d | ideias %d\n" % (n, h["score"], h["profit_ewma"], h["views"], h["support"]))
    f.write("\n## Hipoteses compostas (cruzamento p/ testar)\n\n")
    for cpd in mem["compostas"]:
        f.write("- %s\n" % cpd)

# --- liga no GRAFO (Graphiti): adiciona nodes de hipotese ---
try:
    g = load("vault/graph.json", {"nodes": [], "edges": []})
    ex = set(x.get("id") for x in g.get("nodes", []))
    for n, h in ranked[:15]:
        nid = "hyp:" + n.replace(" ", "-")[:40]
        if nid not in ex:
            g["nodes"].append({"id": nid, "type": "hypothesis", "label": n, "score": h["score"]})
        g["edges"].append({"src": nid, "rel": "lucro", "dst": "cat:" + n.replace(" ", "-")[:40]})
    json.dump(g, open("vault/graph.json", "w", encoding="utf-8"), ensure_ascii=False)
except Exception:
    pass

print("BRAIN_MEMORY: ciclo %d | NEXT BEST=%s ($%.0f/1k score %.1f) | top: %s"
      % (mem["cycles"], mem["next_best"], hyp.get(mem["next_best"], {}).get("profit_ewma", 0), mem["next_best_score"], ", ".join(top[:3])))
