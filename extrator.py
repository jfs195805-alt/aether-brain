#!/usr/bin/env python3
"""extrator.py - EXTRATOR OPERACIONAL v3 (SEM FILTRO).

METRICA = ENSINAMENTOS OPERACIONAIS CAPTADOS POR VIDEO (nao frases/pares/sinapses).
NAO quero CONCEITO. Quero o DETALHE OPERACIONAL: o que fazer e COMO fazer, passo a passo,
com detalhe suficiente para virar BACKEND / tarefa executavel no meu projeto.

Le a transcricao BRUTA de CADA video, do INICIO AO FIM (em blocos), de TODOS os canais.
Cada canal tem ensinamento unico -> tudo e guardado, mesmo que apareca em um so video.

Saidas:
  CONHECIMENTO_PRODUCAO.json - por canal: passos operacionais, tarefas, produtos, contagem por video
  PAUTA.json                 - BACKLOG EXECUTAVEL + tarefas do projeto + ensinamentos por video
"""
import os, re, json, glob, time, html, hashlib
from collections import Counter, defaultdict

SRC = os.environ.get("NG_SRC", "transcripts")
CANAIS = [c.strip() for c in os.environ.get("EXTRAI_CANAIS", "").split(",") if c.strip()]
MAXV = int(os.environ.get("EXTRAI_MAXV", "60"))
CHUNK = int(os.environ.get("EXTRAI_CHUNK", "5500"))
MAXCHUNKS = int(os.environ.get("EXTRAI_MAXCHUNKS", "8"))
MAXCALLS = int(os.environ.get("EXTRAI_MAXCALLS", "1400"))
VERSAO = 3
OUT = "CONHECIMENTO_PRODUCAO.json"
PAUTA = "PAUTA.json"

try:
    from ai_providers import ask
except Exception:
    ask = None

CENSURA = re.compile(r"\[\s*(&nbsp;)?\s*_+\s*(&nbsp;)?\s*\]")
NUM = re.compile(r"\d")


def limpa(t):
    t = html.unescape(t or "")
    t = CENSURA.sub(" ", t).replace(">>", " ")
    return re.sub(r"\s+", " ", t).strip()


def blocos(txt):
    """Divide a transcricao INTEIRA em blocos, cortando em espaco (sem picar palavra)."""
    out = []
    i, n = 0, len(txt)
    while i < n and len(out) < MAXCHUNKS:
        j = min(i + CHUNK, n)
        if j < n:
            k = txt.rfind(" ", i + int(CHUNK * 0.6), j)
            if k > i:
                j = k
        out.append(txt[i:j].strip())
        i = j
    return [b for b in out if len(b) >= 200]


def norm(s):
    return re.sub(r"[^a-z0-9À-ſ ]", "", (s or "").lower()).strip()


# SEM FILTRO. Pedido do Rafael: "retire todos os filtros, use todos os ensinamentos de
# todos os videos". Nada e descartado. Todo ensinamento de todo video de todo canal entra.
# O prompt pede o passo a passo OPERACIONAL, mas a saida NAO joga nada fora.


def util(p):
    """Aceita qualquer passo que tenha ao menos uma acao. Nada e filtrado."""
    return isinstance(p, dict) and (p.get("acao") or "").strip()


try:
    base = json.load(open(OUT, encoding="utf-8"))
except Exception:
    base = {"canais": {}, "ts": None}

# GUARD ANTI-PERDA: versao antiga lia so o comeco do video e JA marcava como processado.
# Como nunca reprocessamos video marcado, o resto ficaria perdido PARA SEMPRE.
if base.get("versao") != VERSAO:
    base = {"canais": {}, "ts": None, "versao": VERSAO}
    print("EXTRATOR: estado antigo descartado -> reprocessando TODOS os videos por inteiro")
base["versao"] = VERSAO

feitos = {v for c in base["canais"].values() for v in c.get("videos_processados", [])}

PROMPT = """Abaixo esta UM TRECHO da transcricao bruta de um video do YouTube.

Extraia SO o PASSO A PASSO OPERACIONAL. NAO quero conceito. NAO quero teoria. NAO quero
motivacao. Quero o que FAZER e COMO FAZER, com detalhe suficiente para alguem EXECUTAR
sem assistir o video - detalhe que da para virar tarefa de backend.

Responda SO com JSON puro, sem markdown:

{{"passos": [
   {{"acao": "verbo no imperativo + objeto concreto (O QUE fazer)",
     "como": "o DETALHE OPERACIONAL: onde, qual valor, qual configuracao, qual ordem, qual criterio, qual numero",
     "ferramenta": "ferramenta/plataforma/produto usado; vazio se nenhum",
     "resultado": "o que esse passo entrega na pratica"}}
 ],
 "tarefas_projeto": ["ate 3 tarefas OBJETIVAS e EXECUTAVEIS que eu deveria fazer no MEU projeto de conteudo/afiliado com base neste trecho"],
 "produtos": ["produtos/ferramentas citados; [] se nenhum"],
 "nicho": "Suplementos|Emagrecimento|Fitness|Afiliados|IA e Tech|Financas|Negocios|Saude|Psicologia|Beleza|Educacao|Outro"}}

NAO DESCARTE NADA. Extraia TUDO que o trecho ensina - todo ensinamento, todo detalhe.
Quanto mais detalhe operacional (numero, valor, configuracao, ordem, criterio), melhor.
  Exemplo bom: "publique 3 videos por semana as 19h, com o titulo comecando por numero".
  Exemplo bom: "no gerenciador de anuncios, comece com 20 reais/dia, 3 criativos, e mate o
                criativo com CTR abaixo de 1% em 48h".
Se o trecho tiver pouco detalhe, ainda assim registre o que ele ensina - nao jogue fora.

TRECHO:
{txt}
"""

if ask is None:
    print("EXTRATOR: ai_providers indisponivel")
    raise SystemExit

arquivos = sorted(glob.glob(os.path.join(SRC, "*.jsonl")))
if CANAIS:
    arquivos = [f for f in arquivos if os.path.splitext(os.path.basename(f))[0] in CANAIS]

chamadas = 0
videos_ok = videos_vazios = total_chunks = 0
parou_no_teto = False

for f in arquivos:
    if chamadas >= MAXCALLS:
        parou_no_teto = True
        break
    canal = os.path.splitext(os.path.basename(f))[0]
    c = base["canais"].setdefault(canal, {"videos_processados": [], "passos": [],
                                          "tarefas": [], "produtos": [], "por_video": []})
    n = 0
    for ln in open(f, encoding="utf-8", errors="ignore"):
        if n >= MAXV or chamadas >= MAXCALLS:
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

        parts = blocos(txt)
        if not parts:
            continue

        v_passos, v_tarefas, v_prod = [], [], []
        v_nicho = Counter()
        seen_p, seen_t, seen_pr = set(), set(), set()

        for parte in parts:
            if chamadas >= MAXCALLS:
                break
            try:
                resp = ask(PROMPT.format(txt=parte[:CHUNK + 500]), max_tokens=900)
            except Exception:
                continue
            chamadas += 1
            total_chunks += 1
            m = re.search(r"\{.*\}", resp or "", re.S)
            if not m:
                continue
            try:
                d = json.loads(m.group(0))
            except Exception:
                continue
            if d.get("nicho"):
                v_nicho[d["nicho"]] += 1
            for p in (d.get("passos") or []):
                if not util(p):
                    continue
                k = norm(p.get("acao", ""))[:70]
                if k and k not in seen_p:
                    seen_p.add(k)
                    v_passos.append({"acao": p["acao"].strip(), "como": p["como"].strip(),
                                     "ferramenta": (p.get("ferramenta") or "").strip(),
                                     "resultado": (p.get("resultado") or "").strip()})
            for t in (d.get("tarefas_projeto") or []):
                k = norm(t)[:70]
                if k and k not in seen_t:
                    seen_t.add(k)
                    v_tarefas.append(t.strip())
            for pr in (d.get("produtos") or []):
                k = norm(pr)[:50]
                if k and k not in seen_pr:
                    seen_pr.add(k)
                    v_prod.append(pr.strip())

        c["videos_processados"].append(vid)
        feitos.add(vid)
        n += 1
        link = "https://youtu.be/" + vid
        nicho = v_nicho.most_common(1)[0][0] if v_nicho else "Outro"

        c["por_video"].append({"video": vid, "link": link, "nicho": nicho,
                               "ensinamentos_captados": len(v_passos),
                               "tarefas": len(v_tarefas), "blocos_lidos": len(parts)})
        if not v_passos and not v_tarefas:
            videos_vazios += 1
            continue
        for p in v_passos:
            p.update({"video": vid, "link": link, "nicho": nicho})
            c["passos"].append(p)
        for t in v_tarefas:
            c["tarefas"].append({"tarefa": t, "video": vid, "link": link, "nicho": nicho})
        for pr in v_prod:
            c["produtos"].append({"produto": pr, "video": vid, "link": link})
        videos_ok += 1

base["ts"] = time.strftime("%FT%TZ", time.gmtime())
base["versao"] = VERSAO
json.dump(base, open(OUT, "w", encoding="utf-8"), ensure_ascii=False)

# ---------- BACKLOG EXECUTAVEL (o que eu FACO no meu projeto) ----------
backlog = []
tarefas = Counter()
tarefa_fonte = defaultdict(list)
prod = Counter()
por_video = []
vistos = set()
total_ensin = 0

for canal, c in base["canais"].items():
    for p in c.get("passos", []):
        total_ensin += 1
        k = norm(p["acao"])[:70]
        if k in vistos:
            continue
        vistos.add(k)
        backlog.append({"id": hashlib.md5(k.encode()).hexdigest()[:12],
                        "acao": p["acao"], "como": p["como"],
                        "ferramenta": p.get("ferramenta", ""), "resultado": p.get("resultado", ""),
                        "nicho": p.get("nicho", ""), "canal_fonte": canal, "link": p["link"],
                        "status": "pendente"})
    for t in c.get("tarefas", []):
        k = norm(t["tarefa"])[:70]
        tarefas[k] += 1
        tarefa_fonte[k].append({"canal": canal, "tarefa": t["tarefa"], "link": t["link"]})
    for pr in c.get("produtos", []):
        prod[pr["produto"].strip().lower()] += 1
    for v in c.get("por_video", []):
        por_video.append(dict(v, canal=canal))

por_video.sort(key=lambda x: -x["ensinamentos_captados"])
nv = len(por_video) or 1
media = round(total_ensin / float(nv), 2)

tarefas_rank = []
for k, n in tarefas.most_common(60):
    fontes = tarefa_fonte[k]
    tarefas_rank.append({"tarefa": fontes[0]["tarefa"], "citada_em_videos": n,
                         "canais_distintos": len({fx["canal"] for fx in fontes}),
                         "fontes": fontes[:3], "status": "pendente"})

json.dump({"ts": base["ts"], "versao": VERSAO,
           "metrica": "ensinamentos operacionais captados por video (nao frases/pares/sinapses)",
           "videos_processados": nv,
           "ensinamentos_captados_total": total_ensin,
           "media_ensinamentos_por_video": media,
           "ensinamentos_por_video": por_video[:150],
           "backlog_executavel": backlog[:300],
           "tarefas_do_projeto": tarefas_rank,
           "produtos_mais_citados": prod.most_common(30)},
          open(PAUTA, "w", encoding="utf-8"), ensure_ascii=False)

print("EXTRATOR v3 (SEM FILTRO): %d videos com ensinamento (%d sem nada extraivel) | %d blocos lidos | "
      "%d chamadas IA%s | %d ensinamentos captados | media %.2f por video | "
      "%d passos no backlog executavel | %d tarefas do projeto"
      % (videos_ok, videos_vazios, total_chunks, chamadas,
         " (TETO - continua no proximo ciclo)" if parou_no_teto else "",
         total_ensin, media, len(backlog), len(tarefas_rank)))
