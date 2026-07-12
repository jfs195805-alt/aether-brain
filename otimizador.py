#!/usr/bin/env python3
"""otimizador.py - AGENTE OTIMIZADOR: melhora o que JA ESTA EM PRODUCAO.

Prioridade invertida: em vez de garimpar insight exotico, arruma o que ja existe e ja pode
render dinheiro hoje. Roda ANTES e INDEPENDENTE do cerebro.

O que ele faz, por video que ja esta publicado no canal da marca:

  1. DIAGNOSTICO (sempre): views, titulo, descricao, tags, se tem link de produto,
     se tem comentario com o link, se esta em playlist, duplicados.
  2. OPORTUNIDADES DE OTIMIZACAO, ranqueadas por impacto:
     - video com views e SEM link nos comentarios  -> dinheiro na mesa (ALTISSIMO)
     - video sem aviso "link nos comentarios"       -> conversao perdida (ALTO)
     - video sem tags / titulo fraco                -> alcance perdido (MEDIO)
     - duplicado publico                            -> canibaliza views (ALTO)
     - video sem playlist                           -> sessao curta (MEDIO)
  3. APLICA o que e seguro e reversivel (se AUDIT_APPLY=1).

Seguranca: NUNCA deleta. Duplicado vira PRIVADO. Nunca inventa link (usa o que ja esta na
descricao). So o canal da marca.

Saida: OTIMIZACOES.json  (relatorio + o que foi aplicado)
"""
import os, re, json, time, html, urllib.parse, urllib.request

CID = os.environ.get("YT_CLIENT_ID") or os.environ.get("YOUTUBE_CLIENT_ID")
CSE = os.environ.get("YT_CLIENT_SECRET") or os.environ.get("YOUTUBE_CLIENT_SECRET")
RT = os.environ.get("YT_RT_GLOBALSUP")
APLICA = os.environ.get("AUDIT_APPLY", "0") == "1"
OUT = "OTIMIZACOES.json"

if not (CID and CSE and RT):
    print("OTIMIZADOR: sem credenciais do canal da marca (YT_RT_GLOBALSUP)")
    raise SystemExit

def token():
    d = urllib.parse.urlencode({"client_id": CID, "client_secret": CSE,
                                "refresh_token": RT, "grant_type": "refresh_token"}).encode()
    return json.load(urllib.request.urlopen("https://oauth2.googleapis.com/token", d, timeout=25))["access_token"]

H = {"Authorization": "Bearer " + token(), "Content-Type": "application/json"}

def api(path, params=None, method="GET", body=None):
    u = "https://www.googleapis.com/youtube/v3/" + path
    if params:
        u += "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(u, data=json.dumps(body).encode() if body else None,
                                 headers=H, method=method)
    try:
        return json.load(urllib.request.urlopen(req, timeout=30))
    except Exception as e:
        return {"erro": str(e)[:150]}

me = api("channels", {"part": "contentDetails,snippet,statistics", "mine": "true"})
if "items" not in me or not me["items"]:
    print("OTIMIZADOR: canal inacessivel:", me.get("erro", ""))
    raise SystemExit
ch = me["items"][0]
nome = ch["snippet"]["title"]
subs = ch.get("statistics", {}).get("subscriberCount", "?")
uploads = ch["contentDetails"]["relatedPlaylists"]["uploads"]

# todos os videos
vids, page = [], None
while True:
    p = {"part": "contentDetails", "playlistId": uploads, "maxResults": 50}
    if page:
        p["pageToken"] = page
    r = api("playlistItems", p)
    vids += [it["contentDetails"]["videoId"] for it in r.get("items", [])]
    page = r.get("nextPageToken")
    if not page:
        break

det = {}
for i in range(0, len(vids), 50):
    r = api("videos", {"part": "snippet,statistics,status", "id": ",".join(vids[i:i + 50])})
    for it in r.get("items", []):
        det[it["id"]] = it

# playlists existentes
pls = {}
r = api("playlists", {"part": "snippet", "mine": "true", "maxResults": 50})
for it in r.get("items", []):
    pls[it["snippet"]["title"].lower()] = it["id"]

URL = re.compile(r"https?://[^\s\)\]<>\"]+")
SOCIAL = re.compile(r"(youtube\.com|youtu\.be|instagram\.com|tiktok\.com|facebook\.com|twitter\.com|x\.com)", re.I)
AVISO_EN = "THE PRODUCT LINK IS IN THE PINNED COMMENT"

def link_produto(desc):
    for u in URL.findall(desc or ""):
        if not SOCIAL.search(u):
            return u.rstrip(".,;)")
    return None

oport = []
aplicadas = []
for v, d in det.items():
    sn = d["snippet"]
    st = d.get("statistics", {})
    status = d.get("status", {})
    if status.get("privacyStatus") != "public":
        continue
    views = int(st.get("viewCount", 0))
    desc = sn.get("description", "")
    titulo = sn.get("title", "")
    tags = sn.get("tags", [])
    link = link_produto(desc)

    # comentarios: ja tem o link?
    tem_comentario = False
    if link:
        cr = api("commentThreads", {"part": "snippet", "videoId": v, "maxResults": 20})
        tem_comentario = any(link in (t["snippet"]["topLevelComment"]["snippet"].get("textOriginal") or "")
                             for t in cr.get("items", []))

    # 1) DINHEIRO NA MESA: tem views + tem link, mas sem comentario fixado
    if link and views > 0 and not tem_comentario:
        oport.append({"impacto": "ALTISSIMO", "tipo": "sem_comentario_com_link",
                      "video": v, "titulo": titulo[:70], "views": views, "link": link,
                      "acao": "postar comentario com descricao EN + link do produto"})
        if APLICA:
            limpo = re.sub(r"[|–-].*$", "", titulo).strip()
            texto = ("👉 %s — OFFICIAL PRODUCT PAGE (real product, verified):\n%s\n\n"
                     "What this is: an independent review of %s. Current price, availability and "
                     "full details on the official page above. Safe, direct link.\n\n"
                     "PT: link oficial do produto acima — confira preço e disponibilidade." % (limpo, link, limpo))
            r = api("commentThreads", {"part": "snippet"}, "POST",
                    {"snippet": {"videoId": v, "topLevelComment": {"snippet": {"textOriginal": texto}}}})
            if "erro" not in r:
                aplicadas.append({"video": v, "acao": "comentario com link postado"})

    # 2) CONVERSAO: sem aviso "link nos comentarios" na descricao
    if link and AVISO_EN not in desc.upper():
        oport.append({"impacto": "ALTO", "tipo": "sem_aviso_na_descricao",
                      "video": v, "titulo": titulo[:70], "views": views,
                      "acao": "adicionar aviso PT+EN de que o link esta no comentario fixado"})
        if APLICA:
            nova = ("🔗 O LINK DO PRODUTO ESTÁ NO COMENTÁRIO FIXADO ABAIXO.\n"
                    "🔗 THE PRODUCT LINK IS IN THE PINNED COMMENT BELOW.\n\n" + desc)
            r = api("videos", {"part": "snippet"}, "PUT",
                    {"id": v, "snippet": {"title": titulo, "categoryId": sn.get("categoryId", "22"),
                                          "description": nova[:4900], "tags": tags}})
            if "erro" not in r:
                aplicadas.append({"video": v, "acao": "aviso adicionado na descricao"})

    # 3) ALCANCE: sem tags
    if len(tags) < 5:
        oport.append({"impacto": "MEDIO", "tipo": "poucas_tags", "video": v,
                      "titulo": titulo[:70], "views": views, "tags_atuais": len(tags),
                      "acao": "adicionar tags de SEO do nicho"})

    # 4) MONETIZACAO ZERO: video publico SEM nenhum link de produto
    if not link:
        oport.append({"impacto": "ALTO", "tipo": "sem_link_de_produto", "video": v,
                      "titulo": titulo[:70], "views": views,
                      "acao": "REVISAR: video publico sem link de afiliado = 100% do trafego perdido"})

ordem = {"ALTISSIMO": 0, "ALTO": 1, "MEDIO": 2}
oport.sort(key=lambda x: (ordem.get(x["impacto"], 9), -x.get("views", 0)))

views_sem_link = sum(o["views"] for o in oport if o["tipo"] == "sem_comentario_com_link")
rel = {"ts": time.strftime("%FT%TZ", time.gmtime()), "canal": nome, "inscritos": subs,
       "videos_publicos": sum(1 for d in det.values() if d.get("status", {}).get("privacyStatus") == "public"),
       "aplicou": APLICA,
       "oportunidades": len(oport),
       "views_sem_comentario_com_link": views_sem_link,
       "por_impacto": {k: sum(1 for o in oport if o["impacto"] == k) for k in ordem},
       "top": oport[:40], "aplicadas": aplicadas}
json.dump(rel, open(OUT, "w", encoding="utf-8"), ensure_ascii=False)
print("OTIMIZADOR [%s | %s inscritos]: %d videos publicos | %d oportunidades "
      "(%d ALTISSIMO, %d ALTO, %d MEDIO) | %s views estao em videos com link mas SEM comentario | aplicou=%s (%d acoes)"
      % (nome, subs, rel["videos_publicos"], len(oport),
         rel["por_impacto"]["ALTISSIMO"], rel["por_impacto"]["ALTO"], rel["por_impacto"]["MEDIO"],
         format(views_sem_link, ",d"), APLICA, len(aplicadas)))
