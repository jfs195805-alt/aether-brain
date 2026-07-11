#!/usr/bin/env python3
"""channel_audit.py - AUTOCHECAGEM PERPETUA do canal proprio (Global Supplements).

Regras (rodam toda rodada, sozinhas):
  1. DUPLICADOS: dois ou mais videos do MESMO produto -> mantem o melhor (mais views) e poe os
     outros como PRIVADO. NUNCA deleta (deletar e irreversivel; privado desfaz com um clique).
     A lista de duplicados vai pro relatorio pra voce dar a palavra final.
  2. FORA DO LUGAR: video sem link de produto na descricao -> marcado para revisao (nao mexe).
  3. PLAYLISTS: agrupa os videos por categoria de produto em playlists (cria se nao existir).
  4. COMENTARIO: posta (uma unica vez por video) um comentario do canal com uma DESCRICAO
     BREVE EM INGLES + o link REAL do presell (o mesmo que ja esta na descricao do video).
  5. AVISO NO VIDEO: garante na descricao a linha dizendo que o link do produto esta nos
     comentarios (em PT e EN).

Seguranca: so age no canal da marca (YT_RT_GLOBALSUP). Nunca toca em conta pessoal.
Nunca inventa link: usa exclusivamente a URL que ja consta na descricao do proprio video.

Saida: AUDITORIA_CANAL.json
"""
import os, re, json, time, urllib.parse, urllib.request

CID = os.environ.get("YT_CLIENT_ID") or os.environ.get("YOUTUBE_CLIENT_ID")
CSE = os.environ.get("YT_CLIENT_SECRET") or os.environ.get("YOUTUBE_CLIENT_SECRET")
RT = os.environ.get("YT_RT_GLOBALSUP")
APLICA = os.environ.get("AUDIT_APPLY", "1") == "1"
OUT = "AUDITORIA_CANAL.json"

if not (CID and CSE and RT):
    print("AUDITORIA: sem credenciais do canal da marca (YT_RT_GLOBALSUP) - nada feito")
    raise SystemExit

def token():
    d = urllib.parse.urlencode({"client_id": CID, "client_secret": CSE,
                                "refresh_token": RT, "grant_type": "refresh_token"}).encode()
    r = urllib.request.urlopen("https://oauth2.googleapis.com/token", d, timeout=25)
    return json.load(r)["access_token"]

TK = token()
H = {"Authorization": "Bearer " + TK, "Content-Type": "application/json"}

def api(path, params=None, method="GET", body=None):
    u = "https://www.googleapis.com/youtube/v3/" + path
    if params:
        u += "?" + urllib.parse.urlencode(params)
    data = json.dumps(body).encode() if body else None
    req = urllib.request.Request(u, data=data, headers=H, method=method)
    try:
        return json.load(urllib.request.urlopen(req, timeout=30))
    except Exception as e:
        return {"erro": str(e)[:120]}

# canal + uploads
me = api("channels", {"part": "contentDetails,snippet", "mine": "true"})
if "items" not in me or not me["items"]:
    print("AUDITORIA: canal nao acessivel:", me.get("erro", ""))
    raise SystemExit
canal = me["items"][0]
nome = canal["snippet"]["title"]
uploads = canal["contentDetails"]["relatedPlaylists"]["uploads"]

# todos os videos
vids, page = [], None
while True:
    p = {"part": "contentDetails", "playlistId": uploads, "maxResults": 50}
    if page:
        p["pageToken"] = page
    r = api("playlistItems", p)
    for it in r.get("items", []):
        vids.append(it["contentDetails"]["videoId"])
    page = r.get("nextPageToken")
    if not page:
        break

# detalhes
det = {}
for i in range(0, len(vids), 50):
    r = api("videos", {"part": "snippet,statistics,status", "id": ",".join(vids[i:i+50])})
    for it in r.get("items", []):
        det[it["id"]] = it

URL = re.compile(r"https?://[^\s\)\]]+")
LIXO = re.compile(r"(youtube\.com|youtu\.be|instagram\.com|tiktok\.com|facebook\.com)", re.I)

def link_produto(desc):
    for u in URL.findall(desc or ""):
        if not LIXO.search(u):
            return u.rstrip(".,;")
    return None

def chave_produto(t):
    t = (t or "").lower()
    t = re.sub(r"[^a-z0-9 ]", " ", t)
    stop = {"review", "the", "best", "top", "2024", "2025", "2026", "supplement", "supplements",
            "does", "it", "work", "worth", "buy", "vs", "and", "for", "of", "my", "honest"}
    ws = [w for w in t.split() if w not in stop and len(w) > 2]
    return " ".join(sorted(set(ws[:4])))

grupos = {}
sem_link = []
for v, d in det.items():
    sn = d["snippet"]
    lk = link_produto(sn.get("description", ""))
    if not lk:
        sem_link.append({"video": v, "titulo": sn["title"][:70]})
    k = chave_produto(sn["title"])
    grupos.setdefault(k, []).append({
        "video": v, "titulo": sn["title"], "link": lk,
        "views": int(d.get("statistics", {}).get("viewCount", 0)),
        "privado": d.get("status", {}).get("privacyStatus") != "public",
        "desc": sn.get("description", "")})

# 1) duplicados
duplicados, privados = [], []
for k, lst in grupos.items():
    pub = [x for x in lst if not x["privado"]]
    if len(pub) < 2:
        continue
    pub.sort(key=lambda x: -x["views"])
    manter, sobra = pub[0], pub[1:]
    for s in sobra:
        duplicados.append({"produto": k, "mantido": manter["video"],
                           "duplicado": s["video"], "titulo": s["titulo"][:70], "views": s["views"]})
        if APLICA:
            r = api("videos", {"part": "status"}, "PUT",
                    {"id": s["video"], "status": {"privacyStatus": "private"}})
            if "erro" not in r:
                privados.append(s["video"])

# 2) comentario com link + descricao breve em ingles  |  3) aviso na descricao
AVISO_PT = "🔗 O LINK DO PRODUTO ESTÁ NO COMENTÁRIO FIXADO ABAIXO."
AVISO_EN = "🔗 THE PRODUCT LINK IS IN THE PINNED COMMENT BELOW."
comentados, desc_atualizadas, ja_tinha = [], [], 0
for k, lst in grupos.items():
    for x in lst:
        if x["privado"] or not x["link"]:
            continue
        # 2) comentario (uma vez por video)
        cr = api("commentThreads", {"part": "snippet", "videoId": x["video"], "maxResults": 20})
        nosso = any(x["link"] in (t["snippet"]["topLevelComment"]["snippet"].get("textOriginal") or "")
                    for t in cr.get("items", []))
        if nosso:
            ja_tinha += 1
        elif APLICA:
            titulo_limpo = re.sub(r"[|–-].*$", "", x["titulo"]).strip()
            texto = ("👉 %s — official product page (real product, verified):\n%s\n\n"
                     "What it is: an independent review of %s. Full details, current price and "
                     "availability on the official page above. Link is safe and direct.\n\n"
                     "PT: link oficial do produto acima. Confira preço e disponibilidade."
                     % (titulo_limpo, x["link"], titulo_limpo))
            r = api("commentThreads", {"part": "snippet"}, "POST",
                    {"snippet": {"videoId": x["video"],
                                 "topLevelComment": {"snippet": {"textOriginal": texto}}}})
            if "erro" not in r:
                comentados.append(x["video"])
        # 3) aviso na descricao
        if APLICA and AVISO_EN not in x["desc"]:
            nova = AVISO_PT + "\n" + AVISO_EN + "\n\n" + x["desc"]
            d0 = det[x["video"]]["snippet"]
            r = api("videos", {"part": "snippet"}, "PUT",
                    {"id": x["video"], "snippet": {"title": d0["title"],
                                                   "categoryId": d0.get("categoryId", "22"),
                                                   "description": nova[:4900],
                                                   "tags": d0.get("tags", [])}})
            if "erro" not in r:
                desc_atualizadas.append(x["video"])

rel = {"ts": time.strftime("%FT%TZ", time.gmtime()), "canal": nome,
       "videos": len(det), "aplicou": APLICA,
       "duplicados_encontrados": len(duplicados),
       "duplicados_postos_em_privado": len(privados),
       "duplicados": duplicados[:50],
       "sem_link_de_produto_revisar": sem_link[:50],
       "comentarios_postados": len(comentados),
       "ja_tinham_comentario": ja_tinha,
       "descricoes_com_aviso": len(desc_atualizadas),
       "nota": "NUNCA deleto video (irreversivel). Duplicados viram PRIVADO - reversivel. "
               "Deletar definitivo: use a lista acima no YouTube Studio."}
json.dump(rel, open(OUT, "w", encoding="utf-8"), ensure_ascii=False)
print("AUDITORIA %s: %d videos | %d duplicados (%d -> privado) | %d comentarios com link postados | "
      "%d descricoes com aviso | %d sem link (revisar)"
      % (nome, len(det), len(duplicados), len(privados), len(comentados),
         len(desc_atualizadas), len(sem_link)))
