"""profit_engine.py — MOTOR INTERNO DE INTELIGENCIA (offline, gratis, sem internet, sem chave).
Le TODAS as transcricoes (milhares de videos), EXTRAI numeros economicos reais que criadores citaram
(comissao %, preco do produto, taxa de conversao, custo por clique/CPC, ganhos) e roda ESTATISTICA
PROBABILISTICA (Monte Carlo) p/ estimar o LUCRO ESPERADO por nicho/produto, com intervalo de confianca.
Deterministico o suficiente p/ o governador priorizar com MATEMATICA. Roda infinito, sem rede."""
import os, json, glob, re, random, statistics, time

TDIR = "transcripts"
random.seed(42)

def load(p, d=None):
    try: return json.load(open(p, encoding="utf-8"))
    except Exception: return d

# nicho por canal (categorizacao)
CATS = (load("AETHER_CANAIS_CATEGORIAS.json", {}) or {}).get("canais", {}) or {}
def niche_of(handle):
    m = CATS.get(handle) or {}
    return (m.get("cat") or "Outros")

# ---- extracao de numeros economicos das transcricoes ----
RE_PCT = re.compile(r'(\d{1,3})\s?%')
RE_USD = re.compile(r'(?:us\$|\$|usd)\s?(\d{1,5})(?:[.,](\d{1,2}))?', re.I)
RE_BRL = re.compile(r'r\$\s?(\d{1,5})(?:[.,](\d{1,2}))?', re.I)

def windows(text, keys, span=60):
    out = []
    tl = text.lower()
    for k in keys:
        i = 0
        while True:
            j = tl.find(k, i)
            if j < 0: break
            out.append(text[max(0, j-span): j+span]); i = j+1
    return out

def collect():
    pools = {}  # niche -> {commission:[], price:[], conversion:[], cpc:[], earn:[]}
    files = glob.glob(TDIR + "/*.jsonl")
    for path in files:
        handle = os.path.basename(path)[:-6]
        nic = niche_of(handle)
        p = pools.setdefault(nic, {"commission": [], "price": [], "conversion": [], "cpc": [], "earn": []})
        try:
            for line in open(path, encoding="utf-8", errors="ignore"):
                try:
                    t = json.loads(line).get("transcript", "")
                except Exception:
                    continue
                if not t: continue
                tl = t.lower()
                # comissao %: perto de comiss/afili/commission
                for w in windows(tl, ["comiss", "afili", "commission", "%", "porcento", "por cento"], 45):
                    for mm in RE_PCT.findall(w):
                        v = int(mm)
                        if any(k in w for k in ["comiss", "afili", "commission"]) and 5 <= v <= 90:
                            p["commission"].append(v)
                        elif any(k in w for k in ["convers", "conversion", "taxa"]) and 0 < v <= 30:
                            p["conversion"].append(v)
                # preco $ / R$
                for mm in RE_USD.findall(tl):
                    v = int(mm[0])
                    if 7 <= v <= 500: p["price"].append(v)
                    elif v >= 500: p["earn"].append(v)
                for mm in RE_BRL.findall(tl):
                    v = int(mm[0])
                    if 20 <= v <= 2000: p["price"].append(v/5.0)  # aprox BRL->USD
                # cpc: perto de clique/cpc
                for w in windows(tl, ["cpc", "custo por clique", "por clique", "cost per click"], 40):
                    for mm in RE_USD.findall(w):
                        c = float(mm[0]) + (float("0." + (mm[1] or "0")) if mm[1] else 0)
                        if 0.05 <= c <= 5: p["cpc"].append(c)
        except Exception:
            pass
    return pools

def samp(pool, lo, hi):
    """Amostra do empirico se houver dados suficientes; senao usa prior uniforme (faixa realista)."""
    if pool and len(pool) >= 3:
        return random.choice(pool)
    return random.uniform(lo, hi)

# --- dado REAL do Google Ads (se conector ligado) substitui a estimativa ---
def _load_ads_real():
    try:
        import json as _j
        d = _j.load(open("ADS_REAL.json", encoding="utf-8"))
        if d.get("status") == "ok" and d.get("totals", {}).get("clicks", 0) > 0:
            return d["totals"].get("avg_cpc", 0), d["totals"].get("conv_rate", 0)
    except Exception:
        pass
    return None, None
ADS_REAL_CPC, ADS_REAL_CONV = _load_ads_real()

def montecarlo(p, trials=3000):
    org, ads, ppos = [], [], 0
    _rcpc, _rconv = ADS_REAL_CPC, ADS_REAL_CONV
    for _ in range(trials):
        price = samp(p["price"], 30, 90)
        comm = samp(p["commission"], 35, 70) / 100.0
        conv = _rconv if _rconv else samp(p["conversion"], 1.0, 4.0) / 100.0
        cpc = _rcpc if _rcpc else samp(p["cpc"], 0.25, 1.5)
        clicks = 1000.0
        revenue = clicks * conv * price * comm
        ad_cost = clicks * cpc
        org.append(revenue)               # nosso modelo faceless organico (sem custo de ad)
        prof_ads = revenue - ad_cost      # cenario com ads pagos
        ads.append(prof_ads)
        if prof_ads > 0: ppos += 1
    return {
        "exp_organic_per_1000": round(statistics.mean(org), 2),
        "exp_ads_profit_per_1000": round(statistics.mean(ads), 2),
        "p_ads_profitable": round(ppos / float(trials), 3),
        "ci_organic": [round(sorted(org)[int(trials*0.1)], 2), round(sorted(org)[int(trials*0.9)], 2)],
    }

def main():
    pools = collect()
    model = {"ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "niches": []}
    for nic, p in pools.items():
        n_data = sum(len(v) for v in p.values())
        mc = montecarlo(p)
        mc["niche"] = nic
        mc["data_points"] = n_data
        mc["confidence"] = "alta" if n_data >= 40 else ("media" if n_data >= 12 else "baixa")
        mc["evidencia"] = {k: (round(statistics.median(v), 1) if v else None) for k, v in p.items()}
        model["niches"].append(mc)
    model["niches"].sort(key=lambda x: -x["exp_organic_per_1000"])
    json.dump(model, open("PROFIT_MODEL.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    with open("PROFIT_MODEL.md", "w", encoding="utf-8") as f:
        f.write("# PROFIT MODEL — lucro esperado por nicho (Monte Carlo sobre numeros REAIS das transcricoes)\n\n")
        f.write("Offline, gratis, sem internet. Lucro organico faceless por 1000 cliques/views (comissao real).\n\n")
        f.write("| Nicho | $ organico/1000 | IC80% | $ com ads/1000 | P(ads da lucro) | dados | confianca |\n")
        f.write("|---|---|---|---|---|---|---|\n")
        for x in model["niches"]:
            f.write("| %s | $%.0f | $%.0f-$%.0f | $%.0f | %.0f%% | %d | %s |\n" % (
                x["niche"], x["exp_organic_per_1000"], x["ci_organic"][0], x["ci_organic"][1],
                x["exp_ads_profit_per_1000"], x["p_ads_profitable"]*100, x["data_points"], x["confidence"]))
        f.write("\n## Evidencia mediana extraida (por nicho)\n\n")
        for x in model["niches"][:12]:
            f.write("- **%s**: %s\n" % (x["niche"], json.dumps(x["evidencia"], ensure_ascii=False)))
    top = model["niches"][:3]
    print("PROFIT_MODEL: %d nichos | TOP: %s" % (len(model["niches"]),
          ", ".join("%s=$%.0f/1k" % (t["niche"], t["exp_organic_per_1000"]) for t in top)))

if __name__ == "__main__":
    main()
