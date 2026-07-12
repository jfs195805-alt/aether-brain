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
CHUNK = int(os.environ.get("EXTRAI_CHUNK", "3000"))   # bloco menor = mais detalhe captado
MAXCHUNKS = int(os.environ.get("EXTRAI_MAXCHUNKS", "0"))  # 0 = SEM TETO: video INTEIRO
MAXCALLS = int(os.environ.get("EXTRAI_MAXCALLS", "1400"))
TEMPO_MAX = int(os.environ.get("EXTRAI_TEMPO_MAX", "1500"))  # segundos (25 min)
MAXTENT = int(os.environ.get("EXTRAI_MAXTENT", "3"))   # tentativas antes de aceitar parcial
T0 = time.time()
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
    while i < n and (MAXCHUNKS <= 0 or len(out) < MAXCHUNKS):
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

PROMPT = """Abaixo esta UM TRECHO da transcricao bruta de UM video do YouTube.

Sua tarefa: MAPEAR TUDO que este trecho ensina. NAO RESUMA. NAO GENERALIZE. NAO PULE NADA.
Cada coisa que a pessoa ensina, cada numero que ela diz, cada configuracao, cada ordem de
passos, cada produto, cada criterio - vira um item. Se ela ensina 12 coisas, devolva 12 itens.

Prefira o DETALHE OPERACIONAL (o COMO) ao conceito. Se ela disser "use 5g", registre "5g".
Se disser "espere 48h", registre "48h". Nao troque numero por "pouco" ou "algum tempo".

Responda SO com JSON puro, sem markdown:

{{"passos": [
   {{"acao": "O QUE fazer - verbo + objeto concreto",
     "como": "o DETALHE EXATO como ele falou: valores, numeros, ordem, onde, configuracao, criterio",
     "ferramenta": "ferramenta/plataforma/produto/marca usado; vazio se nenhum",
     "resultado": "o que isso entrega/produz, como ele falou"}}
 ],
 "tarefas_projeto": ["tarefas OBJETIVAS e EXECUTAVEIS que eu deveria fazer no MEU projeto de conteudo/afiliado com base neste trecho"],
 "produtos": ["TODOS os produtos, marcas, ferramentas e sites citados neste trecho; [] se nenhum"],
 "numeros": ["TODO numero/valor/prazo/dose/preco/metrica citado, com o contexto. ex: '5g por dia', 'CTR abaixo de 1%', '20 reais/dia'"],
 "nicho": "Suplementos|Emagrecimento|Fitness|Afiliados|IA e Tech|Financas|Negocios|Saude|Psicologia|Beleza|Educacao|Outro"}}

NAO DESCARTE NADA. Melhor devolver um item a mais do que perder um ensinamento.
Se o trecho tiver pouco detalhe, registre mesmo assim o que ele ensina.

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
falhas_ia = nao_marcados = incompletos = 0
parou_no_teto = False
abortou = False

for f in arquivos:
    if abortou:
        break
    if chamadas >= MAXCALLS or (time.time() - T0) > TEMPO_MAX:
        parou_no_teto = True
        break
    canal = os.path.splitext(os.path.basename(f))[0]
    c = base["canais"].setdefault(canal, {"videos_processados": [], "passos": [],
                                          "tarefas": [], "produtos": [], "numeros": [],
                                          "por_video": []})
    n = 0
    for ln in open(f, encoding="utf-8", errors="ignore"):
        if n >= MAXV or chamadas >= MAXCALLS or (time.time() - T0) > TEMPO_MAX:
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

        ok_ia = False       # so marca o video como FEITO se a IA respondeu de verdade
        blocos_ok = 0       # quantos blocos deste video a IA leu com sucesso
        v_passos, v_tarefas, v_prod, v_num = [], [], [], []
        v_nicho = Counter()
        seen_p, seen_t, seen_pr, seen_n = set(), set(), set(), set()

        for parte in parts:
            if chamadas >= MAXCALLS or (time.time() - T0) > TEMPO_MAX:
                break
            try:
                resp = ask(PROMPT.format(txt=parte[:CHUNK + 500]), max_tokens=900)
            except Exception as e:
                falhas_ia += 1
                continue
            chamadas += 1
            total_chunks += 1
            m = re.search(r"\{.*\}", resp or "", re.S)
            if not m:
                falhas_ia += 1
                continue
            try:
                d = json.loads(m.group(0))
            except Exception:
                falhas_ia += 1
                continue
            ok_ia = True
            blocos_ok += 1
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
            for nu in (d.get("numeros") or []):
                k = norm(nu)[:60]
                if k and k not in seen_n:
                    seen_n.add(k)
                    v_num.append(nu.strip())

        # NAO DEIXAR PASSAR NADA: o video so e dado como MAPEADO se TODOS os blocos foram lidos.
        # Se algum bloco falhou, o video volta para a fila (ate MAXTENT tentativas).
        tent = base.setdefault("tentativas", {})
        completo = (blocos_ok == len(parts))
        if ok_ia and not completo:
            t = tent.get(vid, 0) + 1
            tent[vid] = t
            if t < MAXTENT:
                incompletos += 1
                print("  [%s] %s -> INCOMPLETO (%d/%d blocos) - volta para a fila (tentativa %d)"
                      % (canal[:18], vid, blocos_ok, len(parts), t), flush=True)
                continue

        if not ok_ia:
            # IA nao respondeu para NENHUM bloco deste video -> NAO marca como feito,
            # senao o video seria pulado para sempre e o ensinamento dele se perderia.
            nao_marcados += 1
            if falhas_ia >= 40 and chamadas == 0:
                print("EXTRATOR: IA gratis nao respondeu em %d tentativas -> abortando ciclo "
                      "(nenhum video marcado, nada perdido)" % falhas_ia, flush=True)
                abortou = True
                break
            continue

        c["videos_processados"].append(vid)
        feitos.add(vid)
        n += 1
        link = "https://youtu.be/" + vid
        nicho = v_nicho.most_common(1)[0][0] if v_nicho else "Outro"

        c["por_video"].append({"video": vid, "link": link, "nicho": nicho,
                               "ensinamentos_captados": len(v_passos),
                               "tarefas": len(v_tarefas),
                               "blocos_do_video": len(parts), "blocos_lidos_ok": blocos_ok,
                               "chars_transcricao": len(txt),
                               "cobertura": round(100.0 * blocos_ok / max(1, len(parts)), 1)})
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
        for nu in v_num:
            c.setdefault("numeros", []).append({"numero": nu, "video": vid, "link": link, "nicho": nicho})
        videos_ok += 1
        print("  [%s] %s -> %d ensinamentos | %d/%d blocos lidos (%.0f%% do video, %d chars)"
          % (canal[:18], vid, len(v_passos), blocos_ok, len(parts),
             100.0 * blocos_ok / max(1, len(parts)), len(txt)), flush=True)

        # CHECKPOINT: run cancelada no meio nao pode perder o que ja foi captado
        if videos_ok % 10 == 0:
            base["ts"] = time.strftime("%FT%TZ", time.gmtime())
            json.dump(base, open(OUT, "w", encoding="utf-8"), ensure_ascii=False)
            print("  checkpoint: %d videos salvos (%d chamadas)" % (videos_ok, chamadas), flush=True)

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

print("EXTRATOR v3 (SEM FILTRO): %d videos com ensinamento (%d sem nada extraivel, %d NAO marcados por falha de IA -> serao retentados) | %d blocos lidos | "
      "%d chamadas IA%s | %d ensinamentos captados | media %.2f por video | "
      "%d passos no backlog executavel | %d tarefas do projeto"
      % (videos_ok, videos_vazios, nao_marcados, total_chunks, chamadas,
         " (TETO - continua no proximo ciclo)" if parou_no_teto else "",
         total_ensin, media, len(backlog), len(tarefas_rank)))
