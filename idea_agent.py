#!/usr/bin/env python3
"""idea_agent.py - AGENTE PENSADOR: transforma as figuras neurais em IDEIAS E DECISOES REAIS.

Ele NAO inventa. Ele recebe as figuras que o cerebro descobriu (conjuntos de frases reais de
videos diferentes que se sustentam matematicamente) e usa IA GRATIS para transformar cada uma
numa oportunidade concreta e ancorada:

   nicho real · gancho substantivo · titulo · angulo · por que funciona · provas (link+timestamp)

Regras duras:
  - so usa as frases fornecidas como fonte (nada de alucinar produto/fato)
  - descarta a ideia se vier vazia, generica ou so com palavra vazia
  - toda ideia carrega os links dos videos de origem como PROVA
  - IA 100% gratis (pollinations/nvidia/groq via ai_providers)

Saida: IDEIAS.json (para o site)  +  entrada na fila do governador (PENDING_ACTIONS.json)
"""
import json, os, re, time, hashlib

MAX = int(os.environ.get("IDEIA_MAX", "8"))
STOP = set(("aqui gente video videos coisa fazer bem tudo agora hoje pessoal cara galera muito "
            "mais menos ser ter estar isso esse essa outros outro the and for you this that with").split())

def L(f, d):
    try:
        return json.load(open(f, encoding="utf-8"))
    except Exception:
        return d

syn = L("SINAPSES.json", {})
figs = (syn.get("top_insights") or []) + (syn.get("top_conceitos") or [])
if not figs:
    print("PENSADOR: sem figuras neurais ainda (o motor de sinapses precisa rodar primeiro)")
    raise SystemExit

# IA gratis
try:
    from ai_providers import ask
except Exception:
    ask = None
if ask is None:
    print("PENSADOR: ai_providers indisponivel")
    raise SystemExit

PROMPT = """Voce e um estrategista de conteudo. Abaixo estao AFIRMACOES REAIS extraidas de
transcricoes de videos diferentes do YouTube. Um motor matematico descobriu que elas se
conectam entre si (mesmo vindo de canais e categorias diferentes).

AFIRMACOES (unica fonte permitida - nao invente nada fora delas):
{fontes}

CATEGORIAS QUE ESSAS AFIRMACOES CRUZAM: {cats}

Gere UMA oportunidade de conteudo em JSON puro, sem markdown, com estas chaves:
{{"nicho": "categoria principal, especifica (ex: Suplementos, Emagrecimento, Afiliados)",
 "gancho": "3 a 6 palavras com substancia, nunca palavras vazias",
 "titulo": "titulo de video/short chamativo e honesto, max 70 caracteres",
 "angulo": "em 1 frase, o insight que conecta essas afirmacoes e que ninguem esta falando",
 "porque_funciona": "1 frase, por que isso gera atencao e conversao",
 "formato": "short | video | pressell"}}

Se as afirmacoes forem vagas demais para gerar algo util, responda exatamente: {{"descartar": true}}
"""

pend = L("PENDING_ACTIONS.json", {"queue": []})
existentes = {a.get("id") for a in pend.get("queue", [])}
ideias, ok, desc = [], 0, 0

for f in figs[:MAX]:
    pontos = f.get("pontos") or f.get("provas") or []
    fontes = [p.get("frase", "")[:180] for p in pontos if p.get("frase")]
    if len(fontes) < 2:
        continue
    cats = f.get("categorias") or []
    if isinstance(cats, list) and cats and isinstance(cats[0], (list, tuple)):
        cats = [c[0] for c in cats]
    provas = [p.get("link") for p in pontos if p.get("link")]
    canais = list({p.get("canal") for p in pontos if p.get("canal")})

    try:
        r = ask(PROMPT.format(fontes="\n".join("- " + s for s in fontes[:4]),
                              cats=", ".join(map(str, cats[:4])) or "variadas"))
    except Exception as e:
        continue
    m = re.search(r"\{.*\}", r or "", re.S)
    if not m:
        continue
    try:
        d = json.loads(m.group(0))
    except Exception:
        continue
    if d.get("descartar") or not d.get("gancho") or not d.get("nicho"):
        desc += 1
        continue
    termos = [t.strip().lower() for t in re.split(r"[+×,\s]", d["gancho"]) if t.strip()]
    if not termos or all(t in STOP for t in termos):
        desc += 1
        continue
    if (d.get("nicho") or "").strip().lower() in ("", "outros", "geral"):
        desc += 1
        continue

    iid = hashlib.md5((d["gancho"] + d["nicho"]).encode()).hexdigest()[:12]
    ideia = {"id": iid, "nicho": d["nicho"], "gancho": d["gancho"],
             "titulo": d.get("titulo", "")[:90], "angulo": d.get("angulo", ""),
             "porque_funciona": d.get("porque_funciona", ""),
             "formato": d.get("formato", "short"),
             "fontes": fontes[:3], "provas": provas[:3], "canais": canais[:3],
             "categorias": cats[:4], "score_figura": f.get("score") or f.get("forca"),
             "ts": time.strftime("%FT%TZ", time.gmtime())}
    ideias.append(ideia)
    ok += 1

    if iid not in existentes:
        pend["queue"].append({
            "id": iid, "tipo": "conteudo_oportunidade", "nicho": d["nicho"],
            "gancho": d["gancho"], "titulo": ideia["titulo"], "angulo": ideia["angulo"],
            "descricao_fonte": fontes[:3], "provas": provas[:3],
            "lucro_1k": 0, "score": f.get("score") or 0,
            "ideias_cruzadas": syn.get("espaco_pares_grafo", 0),
            "origem": "agente pensador (IA gratis) sobre figura neural de %s pontos" % (f.get("n") or f.get("n_pontos")),
            "ts": ideia["ts"]})
        existentes.add(iid)

json.dump({"ts": time.strftime("%FT%TZ", time.gmtime()),
           "geradas": ok, "descartadas": desc, "ideias": ideias},
          open("IDEIAS.json", "w", encoding="utf-8"), ensure_ascii=False)
json.dump(pend, open("PENDING_ACTIONS.json", "w", encoding="utf-8"), ensure_ascii=False)
print("PENSADOR: %d ideias REAIS geradas (ancoradas em frases de video), %d descartadas por vagueza | fila do governador: %d"
      % (ok, desc, len(pend["queue"])))
