#!/usr/bin/env python3
"""fast_interlink.py — le TODOS os transcripts de TODOS os canais em PARALELO (multiprocessing,
usa todos os nucleos do runner 16GB) MUITO mais rapido, e INTERLIGA tudo com o que ja existe.
Constroi co-ocorrencia entre nichos/termos across canais -> INTERLINK.json (alimenta o cerebro).
Offline, gratis. Cada arquivo processado 1x por worker; agrega no fim."""
import os, json, glob, re, time
from collections import Counter
from multiprocessing import Pool, cpu_count

TDIR = "transcripts"
CATMAP = {}
try: CATMAP = json.load(open("AETHER_CANAIS_CATEGORIAS.json", encoding="utf-8"))
except Exception: pass
RE_W = re.compile(r"[a-zA-Zprtime0-9]{4,}")
STOP = set("that this with have your from they what will just they there their about como para essa esse voce mais isso muito quando porque entao agora tambem".split())
KEYS = ["afili","comiss","convers","venda","lucro","dolar","ads","cliqu","trafego","nicho","viral","curiosidad",
        "supplement","weight","health","crypto","nft","arbitrag","psicolog","automacao","renda","afiliado"]

def niche_of(fname):
    base = os.path.basename(fname).split(".")[0].split("_")[0]
    return (CATMAP.get(base) or CATMAP.get(base.lower()) or "geral")

def work(fname):
    terms = Counter(); keyhits = Counter(); recs = 0
    niche = niche_of(fname)
    try:
        with open(fname, encoding="utf-8", errors="replace") as f:
            for ln in f:
                recs += 1
                s = ln.lower()
                for k in KEYS:
                    if k in s: keyhits[k] += 1
                for w in RE_W.findall(s):
                    if w not in STOP and not w.isdigit(): terms[w] += 1
    except Exception:
        pass
    return (niche, recs, dict(terms.most_common(40)), dict(keyhits))

def main():
    files = glob.glob(os.path.join(TDIR, "*.jsonl"))
    if not files:
        json.dump({"note": "sem transcripts ainda"}, open("INTERLINK.json", "w")); print("FAST_INTERLINK: 0 arquivos"); return
    t0 = time.time()
    n = min(cpu_count(), 8)
    with Pool(n) as p:
        results = p.map(work, files, chunksize=4)
    niche_terms = {}; niche_recs = Counter(); niche_keys = {}; total = 0
    for niche, recs, terms, keys in results:
        total += recs; niche_recs[niche] += recs
        nt = niche_terms.setdefault(niche, Counter()); nt.update(terms)
        nk = niche_keys.setdefault(niche, Counter()); nk.update(keys)
    # INTERLIGA: co-ocorrencia de termos entre nichos diferentes = pontes de ideias
    top_by_niche = {ni: [w for w, _ in c.most_common(15)] for ni, c in niche_terms.items()}
    bridges = []
    niches = list(top_by_niche)
    for i in range(len(niches)):
        for j in range(i + 1, len(niches)):
            shared = set(top_by_niche[niches[i]]) & set(top_by_niche[niches[j]])
            shared = [w for w in shared if len(w) > 4]
            if len(shared) >= 2:
                bridges.append({"a": niches[i], "b": niches[j], "shared": sorted(shared)[:6]})
    bridges.sort(key=lambda x: -len(x["shared"]))
    # INTERLIGA com o que ja tem (unificado anterior)
    prev = {}
    try: prev = json.load(open("AETHER_UNIFICADO.json", encoding="utf-8"))
    except Exception: pass
    out = {"ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
           "arquivos": len(files), "registros": total, "segundos": round(time.time() - t0, 1),
           "nucleos": n, "por_nicho_registros": dict(niche_recs.most_common()),
           "termos_por_nicho": {ni: [w for w, _ in c.most_common(12)] for ni, c in niche_terms.items()},
           "sinais_economicos_por_nicho": {ni: dict(c) for ni, c in niche_keys.items()},
           "pontes_entre_nichos": bridges[:40],
           "ideias_previas": len(prev.get("ideias", []))}
    json.dump(out, open("INTERLINK.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("FAST_INTERLINK: %d arquivos, %d registros em %ss (%d nucleos) | %d pontes entre nichos" %
          (len(files), total, out["segundos"], n, len(bridges)))

if __name__ == "__main__":
    main()
