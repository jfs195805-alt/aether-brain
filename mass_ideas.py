#!/usr/bin/env python3
"""mass_ideas.py — ULTRAVELOCIDADE offline (sem API). Le TODAS as transcricoes em paralelo,
monta uma matriz termo x contexto e usa algebra vetorizada (numpy) para pontuar MILHOES/BILHOES
de cruzamentos de termos de uma vez, cruzando nichos diferentes, e ranqueia IDEIAS concretas por
potencial de lucro (peso economico real: comissao/conversao/preco/cpc detectados no texto).
Zero chamadas externas. -> MASS_IDEAS.json / MASS_IDEAS.md"""
import os, json, glob, re, time, math
from collections import Counter
from multiprocessing import Pool, cpu_count
try:
    import numpy as np; HAVE_NP = True
except Exception:
    HAVE_NP = False

TDIR = "transcripts"
CATMAP = {}
try: CATMAP = json.load(open("AETHER_CANAIS_CATEGORIAS.json", encoding="utf-8"))
except Exception: pass
RE_W = re.compile(r"[a-z][a-z0-9]{3,}")
STOP = set("that this with have your from they what will just there their about como para essa esse voce mais isso muito quando porque entao agora tambem seu sua dos das uma este esta pra por que the and for you are".split())
ECON = ["afili","comiss","convers","venda","lucro","dolar","ads","cliqu","trafego","funil","oferta",
        "desconto","preco","cupom","checkout","upsell","recorren","assinatura","curiosid","gatilho",
        "dopamin","escassez","urgenc","prova","depoim","garantia","nicho","viral","retenc","reels","short"]
V = int(__import__("os").environ.get("MASS_V","1600"))          # tamanho do vocabulario (termos mais relevantes)
TOPK = 14         # termos-chave por registro (contexto de cruzamento)

def niche_of(fname):
    b = os.path.basename(fname).split(".")[0].split("_")[0]
    return CATMAP.get(b) or CATMAP.get(b.lower()) or "geral"

def scan(fname):
    """1 passada: frequencia de termos + peso economico (termo em linha com sinal econ pesa +)."""
    freq = Counter(); econ = Counter(); niche = niche_of(fname); recs = []
    try:
        with open(fname, encoding="utf-8", errors="replace") as f:
            for ln in f:
                s = ln.lower()
                is_econ = any(k in s for k in ECON)
                toks = [w for w in RE_W.findall(s) if w not in STOP]
                if not toks: continue
                for w in toks:
                    freq[w] += 1
                    if is_econ: econ[w] += 1
                recs.append(toks[:40])
    except Exception:
        pass
    return niche, dict(freq), dict(econ), recs

def main():
    files = glob.glob(os.path.join(TDIR, "*.jsonl"))
    if not files:
        json.dump({"note": "sem transcripts"}, open("MASS_IDEAS.json", "w")); print("MASS_IDEAS: 0 arquivos"); return
    t0 = time.time()
    nproc = min(cpu_count(), 8)
    with Pool(nproc) as p:
        results = p.map(scan, files, chunksize=4)
    gfreq = Counter(); geconf = Counter(); niche_terms = {}; all_recs = []; nrec = 0
    for niche, freq, econ, recs in results:
        gfreq.update(freq); geconf.update(econ)
        nt = niche_terms.setdefault(niche, Counter()); nt.update(freq)
        for r in recs: all_recs.append((niche, r)); nrec += 1
    # vocabulario: termos mais frequentes com algum peso economico priorizado
    scored_vocab = sorted(gfreq.items(), key=lambda kv: -(kv[1] + 5 * geconf.get(kv[0], 0)))
    vocab = [w for w, _ in scored_vocab[:V]]
    vidx = {w: i for i, w in enumerate(vocab)}
    Vn = len(vocab)
    # peso economico por termo (0..1)
    emax = max([geconf.get(w, 0) for w in vocab] + [1])
    ew = [geconf.get(w, 0) / emax for w in vocab]
    # nichos
    niches = sorted(niche_terms)
    nix = {n: i for i, n in enumerate(niches)}

    if HAVE_NP:
        ew = np.array(ew, dtype="float32")
        cooc = np.zeros((Vn, Vn), dtype="float32")           # matriz de cruzamento termo x termo
        nichevec = np.zeros((Vn, len(niches)), dtype="float32")  # em quais nichos cada termo aparece
        for niche, r in all_recs:
            idx = list({vidx[w] for w in r if w in vidx})
            if len(idx) < 2: 
                for i in idx: nichevec[i, nix[niche]] += 1
                continue
            a = np.array(idx)
            cooc[np.ix_(a, a)] += 1.0                          # cruzamentos deste contexto (vetorizado)
            nichevec[a, nix[niche]] += 1
        np.fill_diagonal(cooc, 0)
        # espalhamento entre nichos: termo que aparece em varios nichos = ponte de ideia
        spread = (nichevec > 0).sum(axis=1).astype("float32")
        spread = spread / max(1.0, spread.max())
        # score do par (a,b) = cruzamento * peso_econ(a) * peso_econ(b) * (ponte entre nichos)
        base = cooc * ew[:, None] * ew[None, :]
        bridge = (spread[:, None] + spread[None, :]) * 0.5 + 0.1
        score = base * bridge
        pares_avaliados = int((cooc > 0).sum())
        # top pares (triangular superior)
        iu = np.triu_indices(Vn, k=1)
        flat = score[iu]
        order = np.argsort(flat)[::-1][:80]
        pairs = [(vocab[iu[0][o]], vocab[iu[1][o]], float(flat[o])) for o in order if flat[o] > 0]
    else:
        pares_avaliados = 0; pairs = []

    # nicho de maior lucro (do profit_model) p/ ancorar as ideias
    prof = {}
    try:
        pm = json.load(open("PROFIT_MODEL.json", encoding="utf-8"))
        prof = {x["niche"].lower(): x.get("exp_organic_per_1000", 0) for x in pm.get("niches", [])}
    except Exception: pass
    top_niche = max(prof, key=prof.get) if prof else (niches[0] if niches else "geral")
    top_val = prof.get(top_niche, 0)

    ideas = []
    for a, b, sc in pairs[:50]:
        ideas.append({
            "combo": [a, b], "score": round(sc, 2),
            "ideia": "Conteudo cruzando '%s' + '%s' (gancho -> oferta afiliado)" % (a, b),
            "lucro_estimado_por_1000": round(top_val, 0), "ancora_nicho": top_niche})
    out = {"ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
           "arquivos": len(files), "registros": nrec, "vocab": Vn, "nichos": len(niches),
           "pares_avaliados": pares_avaliados, "segundos": round(time.time() - t0, 2),
           "numpy": HAVE_NP, "top_ideias": ideas}
    json.dump(out, open("MASS_IDEAS.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    with open("MASS_IDEAS.md", "w", encoding="utf-8") as f:
        f.write("# MASS IDEAS — cruzamento em massa (offline, sem API)\n\n")
        f.write("%d arquivos, %d registros, vocab %d, **%s cruzamentos avaliados** em %ss (numpy=%s).\n\n"
                % (len(files), nrec, Vn, f"{pares_avaliados:,}", out["segundos"], HAVE_NP))
        f.write("Top ideias (combo -> lucro estimado/1000, ancorado no nicho de maior retorno):\n\n")
        for it in ideas[:30]:
            f.write("- **%s + %s** — score %.1f — $%.0f/1k (%s)\n"
                    % (it["combo"][0], it["combo"][1], it["score"], it["lucro_estimado_por_1000"], it["ancora_nicho"]))
    print("MASS_IDEAS: %d arquivos, %d registros, %s cruzamentos avaliados em %ss (numpy=%s) | top: %s"
          % (len(files), nrec, f"{pares_avaliados:,}", out["segundos"], HAVE_NP,
             ", ".join("%s+%s" % (i["combo"][0], i["combo"][1]) for i in ideas[:3])))

if __name__ == "__main__":
    main()
