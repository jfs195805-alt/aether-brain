"""governor.py — GOVERNADOR AUTONOMO (persona tipo Jarvis). Le TODO o conhecimento (unificado,
money ideas, ranking, seguidores), CALCULA as ideias de maior lucro real (afiliado/ad), DECIDE e
DISPARA sozinho as acoes (publicar produto/short/historia) via AETHER_PAT, registra em GOVERNOR_LOG.md
e FALA um briefing por voz (Edge TTS). Age sem pedir. Cooldown evita over-post. Nunca faz trade."""
import os, json, glob, time, urllib.request, urllib.parse, urllib.error

REPO = "globalsuplementsofficial-lang/aether-offload"
def load(p, d=None):
    try: return json.load(open(p, encoding="utf-8"))
    except Exception: return d

uni = load("AETHER_UNIFICADO.json", {}) or {}
ideas = uni.get("ideias", []) or []
prods = uni.get("produtos_afiliados", []) or []
ranks = load("channel_ranks.json", {}) or {}
gstate = load("governor_state.json", {}) or {}
resdata = load("RESULTS.json", {}) or {}
profit = load("PROFIT_MODEL.json", {}) or {}
brain = load("BRAIN_MEMORY.json", {}) or {}
_next_best = str(brain.get("next_best", "")).lower()
_brain_line = "NEXT BEST=%s (score %.1f, ciclo %d)" % (brain.get("next_best", "-"), brain.get("next_best_score", 0), brain.get("cycles", 0))
_profit_niches = [str(x.get("niche", "")).lower() for x in profit.get("niches", [])[:3]]
_profit_line = " ; ".join("%s $%.0f/1k" % (x.get("niche"), x.get("exp_organic_per_1000", 0)) for x in profit.get("niches", [])[:3])
# APRENDIZADO: nichos com mais VIEWS reais (o que funciona)
_niche_views = {}
for v in resdata.get("videos", []):
    n = (v.get("niche") or "").lower()
    if n:
        _niche_views[n] = _niche_views.get(n, 0) + int(v.get("views", 0))
_top_niches = [n for n, _ in sorted(_niche_views.items(), key=lambda kv: -kv[1])[:4]]
now = time.time()

MONEY = ["$","r$","dolar","dollar","euro","reais","comiss","fatur","receita","lucro","monetiz",
         "afili","cpm","rpm","venda","payout","renda","earn","revenue","profit","dropship","gumroad",
         "kiwify","clickbank","hotmart","adsense"]
scored = []
for it in ideas:
    s = str(it.get("ideia", "")).lower()
    sc = sum(1 for k in MONEY if k in s)
    if sc:
        subs = int((ranks.get(it.get("canal")) or {}).get("subs", 0))
        learn = 4 if any(tn and tn in s for tn in _top_niches) else 0
        prof = 5 if any(pn and any(w in s for w in pn.split()) for pn in _profit_niches) else 0
        nb = 6 if _next_best and any(w in s for w in _next_best.split()) else 0
        scored.append((sc * 3 + subs // 100000 + learn + prof + nb, sc, subs, it))
scored.sort(key=lambda x: -x[0])
top = scored[:10]

# --- DECISAO (heuristica + LLM p/ o briefing) com COOLDOWN p/ nao floodar ---
def cooled(key, hours):
    last = float(gstate.get(key, 0))
    return (now - last) > hours * 3600

actions = []
if cooled("publish_products", 3):
    actions.append(("publish_products.yml", "Review de produto com link de afiliado (comissao real)")); gstate["publish_products"] = now
if cooled("publish_shorts", 2):
    actions.append(("publish_shorts.yml", "Short magnetico/silencioso -> alcance -> afiliado")); gstate["publish_shorts"] = now
if glob.glob("AETHER_STORY_*.json") and cooled("story_video", 8):
    actions.append(("story_video.yml", "Historia (canal dark) -> novo canal de alto CPM")); gstate["story_video"] = now

brief = ""
try:
    import ai_providers
    ch = resdata.get("channel", {})
    res_line = ("RESULTS so far: %s subs, %s total views; top niches by views: %s. Sales: %s.\n"
                % (ch.get("subs", "?"), ch.get("views", "?"), ", ".join(_top_niches) or "n/a",
                   json.dumps(resdata.get("vendas", {}))[:120]))
    ctx = res_line + ("PROFIT MODEL top nichos por lucro/1000: %s.\n" % (_profit_line or "calculando")) + "Top mined money ideas (points, subscribers):\n" + "\n".join(
        "- (%d pts / %d subs) %s" % (x[0], x[2], str(x[3].get("ideia"))[:120]) for x in top[:8])
    brief = ai_providers.ask(
        "You are AETHER, an autonomous growth governor (like Jarvis) for a faceless operation that earns "
        "REAL money via affiliate links (ClickBank, Amazon, Awin) and ad revenue on supplement reviews and "
        "storytelling channels. In 4 calm, concrete sentences (spoken English), brief the owner on today's "
        "highest-profit moves you are executing right now and why. No investing advice, no trading.\n" + ctx,
        max_tokens=280) or ""
except Exception:
    brief = ""
if not brief:
    prod_top = ", ".join(n for n, _ in prods[:3]) if prods else "our top products"
    brief = ("AETHER governor here. I'm keeping the money engine running: publishing an honest review with "
             "the affiliate link for %s, plus a magnetic short for reach. I'm also preparing a storytelling "
             "video to open a higher-CPM channel. Focus stays on real commissions and views, no risk." % prod_top)

# --- AGE SOZINHO: dispara os workflows ---
GPAT = os.environ.get("AETHER_PAT", "")
def dispatch(wf):
    if not GPAT:
        return "sem-PAT"
    req = urllib.request.Request(
        "https://api.github.com/repos/%s/actions/workflows/%s/dispatches" % (REPO, wf),
        data=json.dumps({"ref": "main"}).encode(), method="POST",
        headers={"Authorization": "Bearer " + GPAT, "Accept": "application/vnd.github+json", "User-Agent": "gov"})
    try:
        return str(urllib.request.urlopen(req, timeout=30).status)
    except urllib.error.HTTPError as e:
        return "err %s" % e.code
results = [(wf, why, dispatch(wf)) for wf, why in actions]

# ENFILEIRA tarefas de navegador (UI-only) na allowlist da marca -> bot Playwright na VM
def enqueue_browser(new):
    import time as _t, json as _j
    q = load("BROWSER_TASKS.json", {"queue": []}) or {"queue": []}
    have = set(t.get("id") for t in q.get("queue", []))
    ALLOW = ["studio.youtube.com", "business.facebook.com", "business.tiktok.com", "ads.google.com", "instagram.com"]
    DENY = ["rafaelroberto"]
    added = 0
    for t in new:
        u = (t.get("url", "") or "").lower()
        if t.get("id") in have: continue
        if any(d in u for d in DENY) or not any(a in u for a in ALLOW): continue
        q["queue"].append(t); added += 1
    q["queue"] = q["queue"][-100:]
    _j.dump(q, open("BROWSER_TASKS.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    return added
import time as _time
_ts = _time.strftime("%Y%m%d%H%M", _time.gmtime())
_bt = []
if any(wf == "publish_products.yml" for wf, _w in actions):
    _bt.append({"id": "audit_yt_" + _ts, "action": "screenshot", "url": "https://studio.youtube.com", "note": "auditar canal apos publicar (leitura)"})
if _next_best:
    _bt.append({"id": "nb_" + _ts, "action": "screenshot", "url": "https://studio.youtube.com", "note": "checar performance p/ NEXT BEST: " + _next_best})
_browser_added = enqueue_browser(_bt)

# --- LOG + estado ---
ts = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
with open("GOVERNOR_LOG.md", "a", encoding="utf-8") as f:
    f.write("\n## %s\n\n> %s\n\n" % (ts, brief))
    if results:
        for wf, why, r in results:
            f.write("- EXECUTOU: **%s** -> %s (dispatch %s)\n" % (wf, why, r))
    else:
        f.write("- (cooldown) nenhuma acao nova neste ciclo; motor ja rodando.\n")
    ch = resdata.get("channel", {})
    f.write("\n**Resultados reais:** %s subs | %s views totais | top nichos: %s\n"
            % (ch.get("subs", "?"), ch.get("views", "?"), ", ".join(_top_niches) or "coletando"))
    f.write("\n**PROFIT MODEL:** %s\n**CEREBRO ACUMULADO:** %s\n" % (_profit_line or "calculando", _brain_line))
    f.write("\n**Ideias de maior lucro calculado:**\n")
    for x in top:
        f.write("- (%d pts, %d subs) [%s] %s\n" % (x[0], x[2], x[3].get("canal"), str(x[3].get("ideia"))[:160]))
json.dump(gstate, open("governor_state.json", "w"), ensure_ascii=False)

# --- FALA (Edge TTS, voz Jarvis) ---
try:
    import edge_tts, asyncio
    os.makedirs(os.path.join("out", "briefings"), exist_ok=True)
    mp3 = os.path.join("out", "briefings", "governor_%s.mp3" % time.strftime("%Y%m%d-%H%M", time.gmtime()))
    async def _s():
        await edge_tts.Communicate(brief, "en-US-AndrewNeural").save(mp3)
    asyncio.run(_s())
    print("[VOZ] briefing:", mp3)
except Exception as e:
    print("[VOZ] falhou:", str(e)[:70])

print("GOVERNOR: acoes=%d | money_ideas=%d | browser_tasks=%d" % (len(results), len(top), _browser_added))
print("BRIEFING:", brief[:220])
