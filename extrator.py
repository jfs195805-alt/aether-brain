#!/usr/bin/env python3
"""extrator.py - EXTRATOR DE PRODUCAO: transforma o conteudo BRUTO das transcricoes em
material acionavel para produzir conteudo ORIGINAL nosso.

NAO copia. NAO republica. Extrai INTELIGENCIA:
  - TEMA de cada video (do que ele fala)
  - AFIRMACOES/DICAS que ele ensina (o conhecimento util)
  - PRODUTOS citados (o que ele recomenda -> o que vender)
  - PERGUNTAS que ele responde (o que a audiencia quer saber)
  - GANCHO de abertura (o que segura a atencao nos primeiros segundos)

Sobre isso, o sistema produz conteudo NOSSO, original, com NOSSOS afiliados.

Roda canal por canal, video por video, com IA gratis. Incremental: guarda o que ja processou.
Saida: CONHECIMENTO_PRODUCAO.json  (por canal: temas, dicas, produtos, perguntas, ganchos)
       PAUTA.json                  (fila de pautas prontas para produzir, ranqueadas)
"""
import os, re, json, glob, time, html, hashlib
from collections import Counter, defaultdict

SRC = os.environ.get("NG_SRC", "transcripts")
CANAIS = [c.strip() for c in os.environ.get("EXTRAI_CANAIS", "").split(",") if c.strip()]
MAXV = int(os.environ.get("EXTRAI_MAXV", "40"))      # videos por canal por ciclo
OUT = "CONHECIMENTO_PRODUCAO.json"
PAUTA = "PAUTA.json"

try:
    from ai_providers import ask
except Exception:
    ask = None

CENSURA = re.compile(r"\[\s*(&nbsp;)?\s*_+\s*(&nbsp;)?\s*\]")
def limpa(t):
    t = html.unescape(t or "")
    t = CENSURA.sub(" ", t).replace(">>", " ")
    return re.sub(r"\s+", " ", t).strip()

try:
    base = json.load(open(OUT, encoding="utf-8"))
except Exception:
    base = {"canais": {}, "ts": None}
feitos = {v for c in base["canais"].values() for v in c.get("videos_processados", [])}

PROMPT = """Abaixo esta a transcricao (bruta, sem pontuacao) de UM video do YouTube.
Extraia o conhecimento acionavel dele. Responda SO com JSON puro, sem markdown:

{{"tema": "do que o video trata, em 5-8 palavras",
 "gancho": "como ele abre o video / o que promete nos primeiros segundos, 1 frase",
 "dicas": ["3 a 6 afirmacoes/ensinamentos concretos que ele passa, cada um em 1 frase objetiva"],
 "produtos": ["produtos, marcas ou ferramentas que ele cita ou recomenda; [] se nenhum"],
 "perguntas": ["2 a 4 perguntas que a audiencia teria sobre esse tema"],
 "nicho": "categoria: Suplementos|Emagrecimento|Fitness|Afiliados|IA e Tech|Financas|Negocios|Saude|Psicologia|Beleza|Educacao|Outro"}}

Se a transcricao for vazia, so conversa fiada ou nao der para extrair nada util, responda: {{"descartar": true}}

TRANSCRICAO:
{txt}
"""

if ask is None:
    print("EXTRATOR: ai_providers indisponivel")
    raise SystemExit

arquivos = sorted(glob.glob(os.path.join(SRC, "*.jsonl")))
if CANAIS:
    arquivos = [f for f in arquivos
                if os.path.splitext(os.path.basename(f))[0] in CANAIS]

total_ok = total_skip = 0
for f in arquivos:
    canal = os.path.splitext(os.path.basename(f))[0]
    c = base["canais"].setdefault(canal, {"videos_processados": [], "temas": [], "dicas": [],
                                          "produtos": [], "perguntas": [], "ganchos": []})
    n = 0
    for ln in open(f, encoding="utf-8", errors="ignore"):
        if n >= MAXV:
            break
        if not ln.strip():
            continue
        try:
            r = json.loads(ln)
        except Exception:
            continue
        vid = r.get("video_id")
        if not vid or vid in feitos:
            continue
        txt = limpa(r.get("transcript") or "")
        if len(txt) < 400:
            continue
        try:
            resp = ask(PROMPT.format(txt=txt[:6000]), max_tokens=700)
        except Exception:
            continue
        m = re.search(r"\{.*\}", resp or "", re.S)
        if not m:
            continue
        try:
            d = json.loads(m.group(0))
        except Exception:
            continue
        c["videos_processados"].append(vid)
        feitos.add(vid)
        n += 1
        if d.get("descartar"):
            total_skip += 1
            continue
        link = "https://youtu.be/" + vid
        if d.get("tema"):
            c["temas"].append({"tema": d["tema"], "video": vid, "link": link, "nicho": d.get("nicho", "")})
        for dica in (d.get("dicas") or [])[:6]:
            c["dicas"].append({"dica": dica, "video": vid, "link": link, "nicho": d.get("nicho", "")})
        for p in (d.get("produtos") or [])[:6]:
            c["produtos"].append({"produto": p, "video": vid, "link": link})
        for q in (d.get("perguntas") or [])[:4]:
            c["perguntas"].append({"pergunta": q, "video": vid, "link": link, "nicho": d.get("nicho", "")})
        if d.get("gancho"):
            c["ganchos"].append({"gancho": d["gancho"], "video": vid, "link": link})
        total_ok += 1

base["ts"] = time.strftime("%FT%TZ", time.gmtime())
json.dump(base, open(OUT, "w", encoding="utf-8"), ensure_ascii=False)

# ---------- PAUTA: o que produzir, ranqueado por evidencia ----------
temas = Counter()
tema_fonte = defaultdict(list)
prod = Counter()
perg = Counter()
for canal, c in base["canais"].items():
    for t in c["temas"]:
        k = (t["tema"].strip().lower(), t.get("nicho", ""))
        temas[k] += 1
        tema_fonte[k].append({"canal": canal, "link": t["link"]})
    for p in c["produtos"]:
        prod[p["produto"].strip().lower()] += 1
    for q in c["perguntas"]:
        perg[q["pergunta"].strip()] += 1

pautas = []
for (tema, nicho), n in temas.most_common(60):
    if nicho in ("", "Outro"):
        continue
    pautas.append({
        "id": hashlib.md5((tema + nicho).encode()).hexdigest()[:12],
        "tema": tema, "nicho": nicho,
        "evidencia": n,                       # quantos videos de canais que funcionam falam disso
        "fontes": tema_fonte[(tema, nicho)][:4],
        "perguntas_a_responder": [q for q, _ in perg.most_common(50)][:3],
        "tipo": "produzir_conteudo_original",
        "ts": base["ts"]})
pautas.sort(key=lambda x: -x["evidencia"])

json.dump({"ts": base["ts"], "pautas": pautas[:40],
           "produtos_mais_citados": prod.most_common(25),
           "perguntas_mais_comuns": perg.most_common(20)},
          open(PAUTA, "w", encoding="utf-8"), ensure_ascii=False)

print("EXTRATOR: %d videos processados (%d descartados) | %d canais | %d PAUTAS geradas | "
      "%d produtos citados | %d perguntas da audiencia"
      % (total_ok, total_skip, len(base["canais"]), len(pautas), len(prod), len(perg)))
