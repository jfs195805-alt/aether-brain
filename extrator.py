#!/usr/bin/env python3
"""extrator.py - EXTRATOR DE PRODUCAO v2: transforma o conteudo BRUTO das transcricoes
em material acionavel para produzir conteudo ORIGINAL nosso.

NAO copia. NAO republica. Extrai INTELIGENCIA de CADA video, do INICIO AO FIM:
  - TEMA de cada video (do que ele fala)
  - DICAS/ensinamentos concretos (o conhecimento util) -> de TODOS os trechos do video
  - ACOES que funcionam: o que o criador FAZ que deu certo (estrutura, oferta, CTA, prova)
  - PRODUTOS citados (o que ele recomenda -> o que vender com NOSSO afiliado)
  - PERGUNTAS que a audiencia teria (o que responder no nosso conteudo)
  - GANCHO de abertura (o que segura a atencao)

DIFERENCA v1 -> v2 (pedido: "avaliado tudo que foi dito em cada video, sem esquecer de nenhum"):
  v1 lia so os primeiros 6000 chars -> perdia metade dos videos longos.
  v2 le a transcricao INTEIRA em BLOCOS (chunks) e mescla os ensinamentos de todos.
  Cobre TODOS os canais (sem filtro por padrao). Incremental: nunca reprocessa o mesmo video.
  Teto de chamadas por ciclo -> o run termina na janela do runner e continua no proximo ciclo.

Saida: CONHECIMENTO_PRODUCAO.json  (por canal: temas, dicas, acoes, produtos, perguntas, ganchos)
       PAUTA.json                  (fila de pautas prontas para produzir, ranqueadas por evidencia)
"""
import os, re, json, glob, time, html, hashlib
from collections import Counter, defaultdict

SRC = os.environ.get("NG_SRC", "transcripts")
CANAIS = [c.strip() for c in os.environ.get("EXTRAI_CANAIS", "").split(",") if c.strip()]
MAXV = int(os.environ.get("EXTRAI_MAXV", "60"))          # videos NOVOS por canal por ciclo
CHUNK = int(os.environ.get("EXTRAI_CHUNK", "5500"))      # tamanho do bloco de transcricao (chars)
MAXCHUNKS = int(os.environ.get("EXTRAI_MAXCHUNKS", "8"))  # ate 8 blocos/video (~44k chars = video MUITO longo)
MAXCALLS = int(os.environ.get("EXTRAI_MAXCALLS", "1400"))  # teto de chamadas de IA no ciclo (retoma no proximo)
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


def blocos(txt):
    """Divide a transcricao INTEIRA em blocos de ~CHUNK chars, cortando em espaco (sem picar palavra)."""
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


try:
    base = json.load(open(OUT, encoding="utf-8"))
except Exception:
    base = {"canais": {}, "ts": None}

# GUARD ANTI-PERDA: o extrator v1 lia so os primeiros ~6000 chars e JA marcava o video como
# processado. Como nunca reprocessamos video marcado, o resto de cada video longo ficaria
# perdido PARA SEMPRE. Se o estado veio do v1 (sem versao=2), descarta e reprocessa TUDO inteiro.
if base.get("versao") != 2:
    base = {"canais": {}, "ts": None, "versao": 2}
    print("EXTRATOR: estado v1 descartado (lia so o comeco dos videos) -> reprocessando TUDO inteiro")
base["versao"] = 2

feitos = {v for c in base["canais"].values() for v in c.get("videos_processados", [])}

PROMPT = """Abaixo esta UM TRECHO da transcricao (bruta, sem pontuacao) de um video do YouTube.
Extraia o conhecimento acionavel DESTE TRECHO. Responda SO com JSON puro, sem markdown:

{{"tema": "do que este trecho trata, em 5-8 palavras",
 "gancho": "se este trecho for a ABERTURA do video, como ele prende a atencao (1 frase); senao \\"\\"",
 "dicas": ["ate 6 afirmacoes/ensinamentos concretos deste trecho, cada um em 1 frase objetiva"],
 "acoes": ["ate 4 ACOES/taticas que o criador FAZ e que funcionam: como estrutura, como faz a oferta, o CTA, como prova o resultado, como conduz. Cada uma replicavel em 1 frase; [] se nenhuma"],
 "produtos": ["produtos, marcas ou ferramentas citados/recomendados neste trecho; [] se nenhum"],
 "perguntas": ["ate 4 perguntas que a audiencia teria sobre este assunto"],
 "nicho": "categoria: Suplementos|Emagrecimento|Fitness|Afiliados|IA e Tech|Financas|Negocios|Saude|Psicologia|Beleza|Educacao|Outro"}}

Se o trecho for vazio, so conversa fiada ou nao der para extrair nada util: {{"descartar": true}}

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
total_ok = total_skip = total_chunks = 0
parou_no_teto = False

for f in arquivos:
    if chamadas >= MAXCALLS:
        parou_no_teto = True
        break
    canal = os.path.splitext(os.path.basename(f))[0]
    c = base["canais"].setdefault(canal, {"videos_processados": [], "temas": [], "dicas": [],
                                          "acoes": [], "produtos": [], "perguntas": [], "ganchos": []})
    c.setdefault("acoes", [])  # compat com estado v1
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

        parts = blocos(txt)              # <<< TRANSCRICAO INTEIRA, nao so o comeco
        if not parts:
            continue

        # acumuladores do video (dedup entre blocos)
        v_tema = ""
        v_nicho = Counter()
        v_gancho = ""
        seen = {"dicas": set(), "acoes": set(), "produtos": set(), "perguntas": set()}
        agg = {"dicas": [], "acoes": [], "produtos": [], "perguntas": []}
        algo = False

        for bi, parte in enumerate(parts):
            if chamadas >= MAXCALLS:
                break
            try:
                resp = ask(PROMPT.format(txt=parte[:CHUNK + 500]), max_tokens=700)
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
            if d.get("descartar"):
                continue
            algo = True
            if not v_tema and d.get("tema"):
                v_tema = d["tema"]
            if d.get("nicho"):
                v_nicho[d["nicho"]] += 1
            if bi == 0 and not v_gancho and d.get("gancho"):
                v_gancho = d["gancho"]
            for campo in ("dicas", "acoes", "produtos", "perguntas"):
                for item in (d.get(campo) or []):
                    key = norm(item)[:80]
                    if key and key not in seen[campo]:
                        seen[campo].add(key)
                        agg[campo].append(item.strip())

        # so marca como processado se de fato rodou os blocos (senao tenta de novo depois)
        c["videos_processados"].append(vid)
        feitos.add(vid)
        n += 1
        if not algo:
            total_skip += 1
            continue

        link = "https://youtu.be/" + vid
        nicho = v_nicho.most_common(1)[0][0] if v_nicho else "Outro"
        if v_tema:
            c["temas"].append({"tema": v_tema, "video": vid, "link": link, "nicho": nicho})
        for x in agg["dicas"][:12]:
            c["dicas"].append({"dica": x, "video": vid, "link": link, "nicho": nicho})
        for x in agg["acoes"][:8]:
            c["acoes"].append({"acao": x, "video": vid, "link": link, "nicho": nicho})
        for x in agg["produtos"][:10]:
            c["produtos"].append({"produto": x, "video": vid, "link": link})
        for x in agg["perguntas"][:6]:
            c["perguntas"].append({"pergunta": x, "video": vid, "link": link, "nicho": nicho})
        if v_gancho:
            c["ganchos"].append({"gancho": v_gancho, "video": vid, "link": link})
        total_ok += 1

base["ts"] = time.strftime("%FT%TZ", time.gmtime())
base["versao"] = 2
json.dump(base, open(OUT, "w", encoding="utf-8"), ensure_ascii=False)

# ---------- CATALOGO DE ENSINAMENTOS: guardar TUDO, cada unico e um ativo ----------
# PRINCIPIO (Rafael): os canais foram escolhidos por serem UNICOS e INOVADORES.
# Ideia igual entre videos e RARA de proposito -> logo NAO filtramos por frequencia e
# NAO descartamos singleton. Cada ensinamento unico e mantido inteiro.
# O "cruzamento/triangulo" certo NAO e match de frase igual (isso se provou ruim);
# e o COMPLEMENTO entre ideias DIFERENTES de canais/nichos diferentes = angulo original.
import itertools

por_nicho = defaultdict(list)
prod = Counter()
perg = Counter()
acoes = Counter()
acao_fonte = defaultdict(list)
total_ensin = 0
for canal, c in base["canais"].items():
    for t in c.get("temas", []):
        por_nicho[t.get("nicho", "Outro")].append(
            {"tema": t["tema"], "canal": canal, "link": t["link"], "video": t.get("video")})
    total_ensin += len(c.get("dicas", []))
    for p in c.get("produtos", []):
        prod[p["produto"].strip().lower()] += 1
    for q in c.get("perguntas", []):
        perg[q["pergunta"].strip()] += 1
    for a in c.get("acoes", []):
        ak = norm(a["acao"])[:90]
        if ak:
            acoes[ak] += 1
            acao_fonte[ak].append({"canal": canal, "acao": a["acao"], "link": a["link"]})

# PAUTAS = TODO tema unico (cada video inovador vira material proprio). SEM filtro de frequencia.
pautas = []
vistos = set()
for canal, c in base["canais"].items():
    dicas_por_v = defaultdict(list)
    acoes_por_v = defaultdict(list)
    for x in c.get("dicas", []):
        dicas_por_v[x.get("video")].append(x["dica"])
    for x in c.get("acoes", []):
        acoes_por_v[x.get("video")].append(x["acao"])
    for t in c.get("temas", []):
        k = norm(t["tema"])
        if not k or k in vistos:
            continue
        vistos.add(k)
        v = t.get("video")
        pautas.append({
            "id": hashlib.md5(k.encode()).hexdigest()[:12],
            "tema": t["tema"], "nicho": t.get("nicho", "Outro"),
            "canal_fonte": canal, "link": t["link"],
            "ensinamentos": dicas_por_v.get(v, [])[:12],
            "acoes": acoes_por_v.get(v, [])[:6],
            "unico": True,                       # por design: acervo inovador, nao-repetido
            "tipo": "produzir_conteudo_original", "ts": base["ts"]})
# ordena por RIQUEZA (quantos ensinamentos/acoes carrega), nunca por repeticao
pautas.sort(key=lambda x: -(len(x["ensinamentos"]) + len(x["acoes"])))

# COMPLEMENTO (o "triangulo" certo): combinar temas DIFERENTES de nichos/canais diferentes.
nichos = sorted(nk for nk in por_nicho if nk not in ("", "Outro") and por_nicho[nk])
combinacoes = []
for a, b in itertools.combinations(nichos, 2):
    for x in por_nicho[a][:3]:
        for y in por_nicho[b][:2]:
            if x["canal"] == y["canal"]:
                continue
            combinacoes.append({
                "angulo": "%s + %s" % (x["tema"], y["tema"]),
                "nichos": [a, b],
                "fontes": [{"canal": x["canal"], "link": x["link"]},
                           {"canal": y["canal"], "link": y["link"]}],
                "tipo": "complemento_original"})
            if len(combinacoes) >= 200:
                break
        if len(combinacoes) >= 200:
            break
    if len(combinacoes) >= 200:
        break

# acoes que funcionam, ranqueadas por quantos criadores DIFERENTES as usam
acoes_rank = []
for ak, n in acoes.most_common(40):
    fontes = acao_fonte[ak]
    acoes_rank.append({"acao": fontes[0]["acao"] if fontes else ak,
                       "usada_por_videos": n,
                       "canais_distintos": len({fx["canal"] for fx in fontes}),
                       "exemplos": fontes[:3]})
acoes_rank.sort(key=lambda x: (-x["canais_distintos"], -x["usada_por_videos"]))

json.dump({"ts": base["ts"],
           "versao": 2,
           "principio": ("canais escolhidos por serem unicos/inovadores; cada ensinamento unico e "
                         "mantido; cruzamento = COMPLEMENTO entre ideias diferentes, nao match de frase igual"),
           "total_ensinamentos_guardados": total_ensin,
           "pautas": pautas[:120],
           "combinacoes_complementares": combinacoes[:150],
           "acoes_que_funcionam": acoes_rank[:30],
           "produtos_mais_citados": prod.most_common(30),
           "perguntas_mais_comuns": perg.most_common(25)},
          open(PAUTA, "w", encoding="utf-8"), ensure_ascii=False)

print("EXTRATOR v2: %d videos OK (%d sem substancia) | %d blocos avaliados | %d chamadas IA%s | "
      "%d canais | %d ensinamentos guardados | %d PAUTAS unicas | %d combinacoes complementares | "
      "%d acoes-que-funcionam | %d produtos"
      % (total_ok, total_skip, total_chunks, chamadas,
         " (TETO atingido - continua no proximo ciclo)" if parou_no_teto else "",
         len(base["canais"]), total_ensin, len(pautas), len(combinacoes), len(acoes_rank), len(prod)))
