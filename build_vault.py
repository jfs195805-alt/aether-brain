"""build_vault.py — transforma o conhecimento unificado em VAULT OBSIDIAN ETERNO (interligado por
[[wikilinks]]) + GRAPH.JSON p/ o Graphiti. Liga IDEIAS -> CANAIS -> PRODUTOS -> EXECUCOES (videos
publicados). Regenera do AETHER_UNIFICADO (que acumula), entao o vault cresce sozinho."""
import json, os, time, glob

UJ = "AETHER_UNIFICADO.json"
V = "vault"
os.makedirs(V, exist_ok=True)

def slug(s):
    return "".join(ch if ch.isalnum() else "-" for ch in str(s).lower())[:60].strip("-") or "x"

data = {}
if os.path.exists(UJ):
    try:
        data = json.load(open(UJ, encoding="utf-8"))
    except Exception:
        data = {}
res = data.get("resumo", {}) or {}
prods = data.get("produtos_afiliados", []) or []
ideas = data.get("ideias", []) or []
per = data.get("por_canal", []) or []
chmap = {p.get("canal"): p for p in per if p.get("canal")}
# categorizacao (15 categorias + 6 focos) e seguidores
CATS = {}
try:
    _cz = json.load(open("AETHER_CANAIS_CATEGORIAS.json", encoding="utf-8"))
    CATS = _cz.get("canais", {}) or {}
    CATLIST = _cz.get("categorias", []) or []
    FOCLIST = _cz.get("focos", []) or []
except Exception:
    CATLIST = []; FOCLIST = []
RANKS = {}
try:
    RANKS = json.load(open("channel_ranks.json", encoding="utf-8"))
except Exception:
    RANKS = {}
now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

with open(V + "/INDEX.md", "w", encoding="utf-8") as f:
    f.write("# AETHER BRAIN — Vault Eterno (Obsidian) + Graphiti\n\n")
    f.write("Atualizado: %s\n\n" % now)
    f.write("- Canais: %s | Videos: %s | Taticas: %s | Ideias: %s\n\n"
            % (res.get("canais"), res.get("videos_cobertos"), res.get("total_taticas"), res.get("total_ideias")))
    f.write("Mapas: [[PRODUCTS]] - [[CATEGORIES]] - [[CHANNELS]] - [[IDEAS]] - [[MONEY_IDEAS]] - [[STORIES]] - [[EXECUCOES]] - graph.json (Graphiti)\n")

with open(V + "/PRODUCTS.md", "w", encoding="utf-8") as f:
    f.write("# Produtos/Afiliados citados (conhecimento geral)\n\n")
    for name, ct in prods:
        f.write("- **%s** - %d mencoes\n" % (name, ct))

with open(V + "/CHANNELS.md", "w", encoding="utf-8") as f:
    f.write("# Canais minerados (modelo de negocio)\n\n")
    for c, p in chmap.items():
        f.write("## [[%s]]\n\n- videos: %s\n- modelo: %s\n\n" % (c, p.get("videos"), str(p.get("modelo"))[:400]))

with open(V + "/IDEAS.md", "w", encoding="utf-8") as f:
    f.write("# Ideias acionaveis (ideia -> [[canal]])\n\n")
    for it in ideas[:2000]:
        f.write("- [[%s]] :: %s\n" % (it.get("canal"), str(it.get("ideia"))[:300]))
# MONEY_IDEAS: prioriza ideias com EVIDENCIA de ganho real ($/R$/euro/comissao/faturamento)
_MONEY = ["$", "r$", "dolar", "dolares", "dollar", "euro", "reais", "faturamento", "faturou",
          "receita", "comissao", "comissoes", "lucro", "monetiz", "renda", "earn", "revenue",
          "profit", "payout", "pagamento", "vendas", "afiliad", "cpm", "rpm"]
_scored = []
for it in ideas:
    s = str(it.get("ideia", "")).lower()
    sc = sum(1 for k in _MONEY if k in s)
    if sc:
        _scored.append((sc, it))
_scored.sort(key=lambda x: -x[0])
with open(V + "/MONEY_IDEAS.md", "w", encoding="utf-8") as f:
    f.write("# MONEY IDEAS — ideias com evidencia de GANHO REAL (varios nichos/moedas)\n\n")
    f.write("Foco: psicologia, noise/relax, afiliados, dinheiro online, e descobertas de alto CPM. ")
    f.write("REGRA: dinheiro vem de CONTEUDO + AFILIADO. NUNCA executar trade nem dar conselho de ")
    f.write("investimento (crypto/NFT/arbitragem entram so como TEMA de conteudo, nao operacao).\n\n")
    for sc, it in _scored[:400]:
        f.write("- (%d) [[%s]] :: %s\n" % (sc, it.get("canal"), str(it.get("ideia"))[:300]))

# STORIES: historias geradas (metodo canal dark) acumuladas
import glob as _g
_stories = sorted(_g.glob("AETHER_STORY_*.json"))
with open(V + "/STORIES.md", "w", encoding="utf-8") as f:
    f.write("# Historias (canal dark / storytelling) — geradas pelo diretor automatico\n\n")
    for _sp in _stories[-200:]:
        try:
            _sd = json.load(open(_sp, encoding="utf-8"))
            f.write("## %s\n\n- tema: %s\n- personagens: %d | cenas: %d\n\n"
                    % (_sd.get("title", _sp), _sd.get("_theme", ""),
                       len(_sd.get("characters", [])), len(_sd.get("scenes", []))))
        except Exception:
            pass

pub = []
for pf in ["data/products_published.json", "data/shorts_published.json"]:
    try:
        j = json.load(open(pf, encoding="utf-8"))
        for it in j.get("published", []):
            if isinstance(it, dict):
                pub.append(it)
    except Exception:
        pass
with open(V + "/EXECUCOES.md", "w", encoding="utf-8") as f:
    f.write("# Execucoes (ideia -> BACKEND CONCRETO: videos publicados)\n\n")
    for it in pub[-800:]:
        f.write("- %s | yt=%s | %s\n" % (it.get("slug"), it.get("video_id"), it.get("ts")))

# CATEGORIES.md — interliga centenas de canais por categoria + foco (nacional/internacional)
import collections as _col
_bycat = _col.defaultdict(list)
_allch = set(list(chmap.keys()) + list(CATS.keys()))
for _h in _allch:
    _meta = CATS.get(_h, {}) or {}
    _cat = _meta.get("cat", "Outros")
    _subs = int((RANKS.get(_h) or {}).get("subs", 0))
    _bycat[_cat].append((_h, _subs, _meta.get("focos", [])))
with open(V + "/CATEGORIES.md", "w", encoding="utf-8") as f:
    f.write("# Categorias (interligadas) — canais por categoria, ordenados por seguidores\n\n")
    for _cat in sorted(_bycat, key=lambda k: -sum(s for _, s, _ in _bycat[k])):
        f.write("## %s\n\n" % _cat)
        for _h, _s, _fo in sorted(_bycat[_cat], key=lambda x: -x[1]):
            f.write("- [[%s]] — %s seguidores%s\n" % (_h, _s, (" · foco: " + ", ".join(_fo)) if _fo else ""))
        f.write("\n")

nodes, edges = [], []
for name, ct in prods:
    nodes.append({"id": "prod:" + slug(name), "type": "product", "label": name, "weight": ct})
for _cat in CATLIST:
    nodes.append({"id": "cat:" + slug(_cat), "type": "category", "label": _cat})
for _fo in FOCLIST:
    nodes.append({"id": "foco:" + slug(_fo), "type": "foco", "label": _fo})
for c, p in chmap.items():
    _m = CATS.get(c, {}) or {}
    nodes.append({"id": "chan:" + slug(c), "type": "channel", "label": c,
                  "videos": p.get("videos"), "subs": int((RANKS.get(c) or {}).get("subs", 0)),
                  "cat": _m.get("cat", "")})
    if _m.get("cat"):
        edges.append({"src": "chan:" + slug(c), "rel": "categoria", "dst": "cat:" + slug(_m["cat"])})
    for _fo in (_m.get("focos") or []):
        edges.append({"src": "chan:" + slug(c), "rel": "foco", "dst": "foco:" + slug(_fo)})
for it in ideas[:3000]:
    iid = "idea:" + slug(str(it.get("ideia"))[:40])
    nodes.append({"id": iid, "type": "idea", "label": str(it.get("ideia"))[:140]})
    edges.append({"src": "chan:" + slug(it.get("canal", "")), "rel": "gera", "dst": iid})
for it in pub:
    if it.get("slug"):
        edges.append({"src": "exec:" + slug(it.get("slug")), "rel": "publicou", "dst": "prod:" + slug(it.get("slug"))})
json.dump({"generated": now, "nodes": nodes, "edges": edges},
          open(V + "/graph.json", "w", encoding="utf-8"), ensure_ascii=False)
print("VAULT: %d produtos | %d canais | %d ideias | %d nodes | %d execucoes"
      % (len(prods), len(chmap), len(ideas), len(nodes), len(pub)))
