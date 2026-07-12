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
VERSAO = 7

PROJETO = os.environ.get("EXTRAI_PROJETO", """MEU PROJETO (Global Supplements):
- Canal no YouTube + site de reviews. Publico: quem busca suplemento, emagrecimento, saude e fitness.
- RECEITA: (1) monetizacao de conteudo e (2) COMISSAO DE AFILIADO de produto real (ClickBank/BuyGoods/Amazon).
- Preciso de: pauta de video, gancho de abertura, estrutura de roteiro, produto para promover com
  link de afiliado, argumento de venda com prova, titulo/SEO, CTA, e taticas replicaveis.
- REGRA: conteudo ORIGINAL nosso (nunca copiar a fala do criador), foto REAL do produto,
  link de afiliado rastreavel. Nada de conselho de investimento nem promessa de cura.""")
MODELO_FILE = os.environ.get("EXTRAI_MODELO", "MODELO_ANALISE.md")
try:
    _mod = open(MODELO_FILE, encoding="utf-8").read()
except Exception:
    _mod = ""
# o documento inteiro e o padrao-ouro. Cada agente recebe a sua secao (marcada no arquivo).
if "<<<MODELO_AGENTE_2>>>" in _mod:
    MODELO_A1 = _mod.split("<<<MODELO_AGENTE_2>>>")[0]
    MODELO_A2 = _mod.split("<<<MODELO_AGENTE_2>>>")[1]
else:
    MODELO_A1 = MODELO_A2 = _mod
if os.environ.get("EXTRAI_MODELO_COMPLETO") == "1":   # injeta o documento INTEIRO nos dois
    MODELO_A1 = MODELO_A2 = _mod
if not _mod:
    MODELO_A1 = MODELO_A2 = "(modelo de analise nao encontrado - siga as regras do prompt)"

JA_TENHO_FILE = os.environ.get("EXTRAI_JA_TENHO", "PROJETO_ATUAL.md")
try:
    JA_TENHO = open(JA_TENHO_FILE, encoding="utf-8").read()[:3000]
except Exception:
    JA_TENHO = "(ainda nao ha registro do que o projeto ja tem - considere tudo como novo)"

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

PROMPT = """AGENTE 1 - TOPICADOR. Voce le UM BLOCO da transcricao bruta de um video e o
transforma em TOPICOS. Voce NAO opina sobre projeto nenhum - outro agente fara isso depois.

===================== MODELO DE ANALISE (padrao-ouro obrigatorio) =====================
Analise abaixo do nivel deste modelo esta ERRADA. Siga-o.

{modelo}
=======================================================================================

Este e o BLOCO {bloco} de {total}. Voce (ou outra instancia sua) vera TODOS os blocos.

REGRA: cada coisa que o video ENSINA A FAZER ou RECOMENDA = 1 topico.
NAO RESUMA. NAO PULE NADA. Se o bloco tem 7 coisas, devolva 7 topicos.
Guarde o DETALHE EXATO como ele falou: numero, dose, prazo, preco, spec, ordem, criterio.
Nunca troque numero por "pouco" ou "algum tempo".
Se o bloco for so vinheta/despedida/enrolacao, devolva "topicos": [] - sem inventar.

Responda SO com JSON puro, sem markdown:

{{"topicos": [
   {{"topico": "titulo curto do topico (4-8 palavras)",
     "ensina_a_fazer": "a acao/recomendacao que ele passa, em 1 frase",
     "como": "o detalhe EXATO: numeros, valores, ordem, configuracao, criterio, specs",
     "deve_ser_copiado": "o que exatamente daqui merece ser copiado como TATICA (formato, gancho, argumento, estrutura, prova); vazio se nada",
     "produtos": ["produtos/marcas/ferramentas citados NESTE topico; [] se nenhum"],
     "numeros": ["numeros/valores/prazos/doses/precos/specs citados NESTE topico, com contexto"]}}
 ],
 "nicho": "Suplementos|Emagrecimento|Fitness|Saude|Afiliados|IA e Tech|Financas|Negocios|Beleza|Educacao|Automoveis|Outro"}}

BLOCO {bloco}/{total}:
{txt}
"""


# ---------- AGENTE 2: SINTETIZADOR (le o VIDEO INTEIRO via os topicos) ----------
PROMPT2 = """AGENTE 2 - SINTETIZADOR. O AGENTE 1 leu a transcricao bruta INTEIRA deste video e a
transformou nos TOPICOS abaixo. Voce agora ve o VIDEO COMO UM TODO - coisa que o Agente 1,
que lia bloco a bloco, nao conseguia enxergar.

===================== MODELO DE ANALISE (padrao-ouro obrigatorio) =====================
Este e o nivel que a sua sintese TEM que atingir. Estude o exemplo e faca igual.

{modelo}
=======================================================================================

{projeto}

O QUE JA EXISTE NO MEU PROJETO (nao repetir - eu ja tenho isto):
{ja_tenho}

VIDEO: {link} | canal: {canal} | {nblocos} blocos lidos (100% da transcricao) | {ntop} topicos

TOPICOS DO VIDEO INTEIRO:
{topicos}

Sua tarefa:
1) ENTENDER O VIDEO COMO UM TODO: qual o PADRAO que se repete? qual a ESTRUTURA que ele usa do
   inicio ao fim? o que faz esse video funcionar? (isso so se ve olhando todos os topicos juntos)
2) DIZER O QUE AGREGAR AO MEU PROJETO EXISTENTE: conhecimento NOVO, que eu ainda NAO tenho.
   Se o video nao agrega nada novo, devolva "agregar": [] - e diga por que em "nada_novo".

Responda SO com JSON puro, sem markdown:

{{"entendimento_do_video": "o que este video E e por que ele funciona, em 2-3 frases, olhando o todo",
 "padrao_que_se_repete": "o molde/estrutura que ele repete do inicio ao fim (ex: 'mesmo formato 16 vezes: nome -> 1 frase -> 3 numeros -> preco'); vazio se nao houver",
 "agregar": [
   {{"o_que": "o conhecimento/tatica NOVA que eu devo agregar ao meu projeto",
     "como_aplicar": "o passo a passo pratico no MEU projeto",
     "tipo": "estrutura_roteiro|gancho|argumento_de_venda|titulo_seo|cta|objecao|pauta_de_video|produto_afiliado|automacao",
     "evidencia": "o que NESTE video prova que funciona (cite o topico/numero)",
     "ja_tenho_parecido": "sim/nao - e se sim, o que muda em relacao ao que ja tenho"}}
 ],
 "nada_novo": "se nao houver nada a agregar, explique por que; senao vazio"}}
"""

if ask is None:
    print("EXTRATOR: ai_providers indisponivel")
    raise SystemExit

arquivos = sorted(glob.glob(os.path.join(SRC, "*.jsonl")))
if CANAIS:
    arquivos = [f for f in arquivos if os.path.splitext(os.path.basename(f))[0] in CANAIS]



# ---------- FILA: NICHO PRIMEIRO, MAS TODOS OS CANAIS SAO COBERTOS ----------
# Faz os 2: canais do meu nicho vao na frente (a IA gratis e o gargalo), MAS uma fatia do
# orcamento fica reservada para o resto, com ROTACAO -> nenhum canal fica na fome.
NICHO_PCT = float(os.environ.get("EXTRAI_NICHO_PCT", "0.70"))   # 70% do orcamento p/ o nicho

KW_NICHO = ("supplement", "suplement", "vitamin", "protein", "creatin", "nutrition", "nutri",
            "weight", "emagrec", "diet", "keto", "fat", "slim", "burn", "detox",
            "fit", "gym", "muscle", "workout", "treino", "musculac", "body", "health", "saude",
            "wellness", "afiliad", "affiliate", "marketing", "clickbank", "dropship", "ecom",
            "renda", "income", "money", "biohack", "longevity", "testosterone", "collagen")


def prioridade_canal(nome, estado):
    """2 = nicho confirmado pelos videos ja lidos | 1 = nome do canal bate | 0 = fora do nicho."""
    c = (estado.get("canais") or {}).get(nome) or {}
    nichos = [v.get("nicho", "") for v in c.get("por_video", [])]
    if any(n in ("Suplementos", "Emagrecimento", "Fitness", "Saude", "Afiliados") for n in nichos):
        return 2
    low = nome.lower()
    if any(k in low for k in KW_NICHO):
        return 1
    return 0


ciclo = int(base.get("ciclo", 0)) + 1
base["ciclo"] = ciclo

_pri = [f for f in arquivos if prioridade_canal(os.path.splitext(os.path.basename(f))[0], base) > 0]
_res = [f for f in arquivos if prioridade_canal(os.path.splitext(os.path.basename(f))[0], base) == 0]
_pri.sort(key=lambda f: -prioridade_canal(os.path.splitext(os.path.basename(f))[0], base))
# ROTACAO: cada ciclo comeca o "resto" num ponto diferente -> cobertura de TODOS ao longo do tempo
if _res:
    off = (ciclo * 20) % len(_res)
    _res = _res[off:] + _res[:off]

ORC_NICHO = int(MAXCALLS * NICHO_PCT)     # orcamento reservado ao nicho
arquivos = _pri + _res
print("FILA: %d canais do NICHO primeiro (%d chamadas reservadas) + %d canais do resto "
      "(rotacao, ciclo %d) = %d canais no total, nenhum de fora"
      % (len(_pri), ORC_NICHO, len(_res), ciclo, len(arquivos)), flush=True)
_nicho_set = set(_pri)

chamadas = 0
ch_nicho = ch_resto = 0
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
    eh_nicho = f in _nicho_set
    # TETO DO NICHO: o nicho nao pode comer 100% do orcamento, senao o resto nunca roda.
    # Ao bater ORC_NICHO, para de gastar em canal de nicho e libera o restante para os demais.
    if eh_nicho and chamadas >= ORC_NICHO:
        continue
    c = base["canais"].setdefault(canal, {"videos_processados": [], "videos": [],
                                          "aplicacoes": [], "produtos": [],
                                          "numeros": [], "por_video": []})
    n = 0
    for ln in open(f, encoding="utf-8", errors="ignore"):
        teto = ORC_NICHO if eh_nicho else MAXCALLS
        if n >= MAXV or chamadas >= teto or (time.time() - T0) > TEMPO_MAX:
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
        v_top, v_prod, v_num = [], [], []
        v_apl = []   # preenchido pelo AGENTE 2
        blocos_com_topico = set()
        v_nicho = Counter()
        seen_t, seen_a, seen_pr, seen_n = set(), set(), set(), set()

        for bi, parte in enumerate(parts):
            if chamadas >= (ORC_NICHO if eh_nicho else MAXCALLS) or (time.time() - T0) > TEMPO_MAX:
                break
            try:
                resp = ask(PROMPT.format(modelo=MODELO_A1, bloco=bi + 1, total=len(parts),
                                         txt=parte[:CHUNK + 500]), max_tokens=1400)
            except Exception as e:
                falhas_ia += 1
                continue
            chamadas += 1
            total_chunks += 1
            if eh_nicho:
                ch_nicho += 1
            else:
                ch_resto += 1
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
            for t in (d.get("topicos") or []):
                if not isinstance(t, dict) or not (t.get("topico") or "").strip():
                    continue
                k = norm(t.get("topico", ""))[:70]
                if k and k not in seen_t:
                    seen_t.add(k)
                    blocos_com_topico.add(bi + 1)
                    v_top.append({"n": len(v_top) + 1,
                                  "topico": t["topico"].strip(),
                                  "ensina_a_fazer": (t.get("ensina_a_fazer") or "").strip(),
                                  "como": (t.get("como") or "").strip(),
                                  "deve_ser_copiado": (t.get("deve_ser_copiado") or "").strip(),
                                  "produtos": [str(x).strip() for x in (t.get("produtos") or [])],
                                  "numeros": [str(x).strip() for x in (t.get("numeros") or [])],
                                  "bloco": bi + 1, "de_blocos": len(parts)})
                    for x in (t.get("produtos") or []):
                        kk = norm(str(x))[:50]
                        if kk and kk not in seen_pr:
                            seen_pr.add(kk)
                            v_prod.append(str(x).strip())
                    for x in (t.get("numeros") or []):
                        kk = norm(str(x))[:60]
                        if kk and kk not in seen_n:
                            seen_n.add(kk)
                            v_num.append(str(x).strip())

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
                               "canal_do_meu_nicho": eh_nicho,
                               "topicos": len(v_top),
                               "aplicacoes_no_projeto": len(v_apl),
                               "blocos_do_video": len(parts), "blocos_lidos_ok": blocos_ok,
                               "chars_transcricao": len(txt),
                               "cobertura": round(100.0 * blocos_ok / max(1, len(parts)), 1)})
        if not v_top:
            videos_vazios += 1
            continue

        # ================= AGENTE 2: SINTETIZADOR (le o VIDEO INTEIRO) =================
        # O Agente 1 leu bloco a bloco. Agora o Agente 2 ve TODOS os topicos juntos e enxerga
        # o padrao que se repete - coisa impossivel de ver olhando um bloco isolado.
        sintese = {}
        if v_top:
            resumo_top = "\n".join(
                "%d. %s | ENSINA: %s | COMO: %s%s"
                % (t["n"], t["topico"], t["ensina_a_fazer"], t["como"],
                   (" | COPIAR: " + t["deve_ser_copiado"]) if t.get("deve_ser_copiado") else "")
                for t in v_top)
            try:
                r2 = ask(PROMPT2.format(modelo=MODELO_A2, projeto=PROJETO, ja_tenho=JA_TENHO,
                                        link=link, canal=canal,
                                        nblocos=len(parts), ntop=len(v_top),
                                        topicos=resumo_top[:9000]), max_tokens=1600)
                chamadas += 1
                if eh_nicho:
                    ch_nicho += 1
                else:
                    ch_resto += 1
                m2 = re.search(r"\{.*\}", r2 or "", re.S)
                if m2:
                    sintese = json.loads(m2.group(0))
            except Exception:
                sintese = {}

        for a in (sintese.get("agregar") or []):
            if not isinstance(a, dict) or not (a.get("o_que") or "").strip():
                continue
            v_apl.append({"o_que": a["o_que"].strip(),
                          "como_aplicar": (a.get("como_aplicar") or "").strip(),
                          "tipo": (a.get("tipo") or "").strip(),
                          "evidencia": (a.get("evidencia") or "").strip(),
                          "ja_tenho_parecido": (a.get("ja_tenho_parecido") or "").strip()})

        c.setdefault("videos", []).append({
            "video": vid, "link": link, "nicho": nicho, "canal": canal,
            "chars": len(txt), "blocos": len(parts), "blocos_lidos": blocos_ok,
            "cobertura_pct": round(100.0 * blocos_ok / max(1, len(parts)), 1),
            "blocos_que_renderam_topico": sorted(blocos_com_topico),
            "total_topicos": len(v_top),
            "TOPICOS": v_top,                       # <<< AGENTE 1: o video virou indice de topicos
            "SINTESE_DO_VIDEO": {                   # <<< AGENTE 2: entendeu o video INTEIRO
                "entendimento": (sintese.get("entendimento_do_video") or "").strip(),
                "padrao_que_se_repete": (sintese.get("padrao_que_se_repete") or "").strip(),
                "nada_novo": (sintese.get("nada_novo") or "").strip()},
            "AGREGAR_NO_MEU_PROJETO": v_apl,
            "produtos": v_prod, "numeros": v_num})
        for pr in v_prod:
            c["produtos"].append({"produto": pr, "video": vid, "link": link, "nicho": nicho})
        for nu in v_num:
            c["numeros"].append({"numero": nu, "video": vid, "link": link, "nicho": nicho})
        videos_ok += 1
        print("  [%s] %s -> %d TOPICOS, %d aplicacoes | %d/%d blocos lidos (%.0f%%) | topicos vieram de %d blocos"
          % (canal[:18], vid, len(v_top), len(v_apl), blocos_ok, len(parts),
             100.0 * blocos_ok / max(1, len(parts)), len(blocos_com_topico)), flush=True)

        # CHECKPOINT: run cancelada no meio nao pode perder o que ja foi captado
        if videos_ok % 10 == 0:
            base["ts"] = time.strftime("%FT%TZ", time.gmtime())
            json.dump(base, open(OUT, "w", encoding="utf-8"), ensure_ascii=False)
            print("  checkpoint: %d videos salvos (%d chamadas)" % (videos_ok, chamadas), flush=True)

base["ts"] = time.strftime("%FT%TZ", time.gmtime())
base["versao"] = VERSAO
json.dump(base, open(OUT, "w", encoding="utf-8"), ensure_ascii=False)

# ---------- SAIDA ----------
TOPICOS_OUT = "TOPICOS_POR_VIDEO.json"

backlog = []
prod = Counter()
nums = []
vistos = set()
por_tipo = Counter()
todos_videos = []
tot_top = tot_apl = 0

for canal, c in base["canais"].items():
    for v in c.get("videos", []):
        for a in v.get("AGREGAR_NO_MEU_PROJETO", []):
            tot_apl += 1
            k = norm(a["o_que"])[:70]
            if k in vistos:
                continue
            vistos.add(k)
            por_tipo[a.get("tipo", "outro")] += 1
            backlog.append({"id": hashlib.md5(k.encode()).hexdigest()[:12],
                            "o_que_agregar": a["o_que"], "como_aplicar": a.get("como_aplicar", ""),
                            "tipo": a.get("tipo", ""), "evidencia": a.get("evidencia", ""),
                            "ja_tenho_parecido": a.get("ja_tenho_parecido", ""),
                            "canal_fonte": canal, "link_fonte": v.get("link", ""),
                            "video": v.get("video", ""), "status": "pendente"})
    for p in c.get("produtos", []):
        prod[p["produto"].strip().lower()] += 1
    for nu in c.get("numeros", []):
        nums.append(nu)
    for v in c.get("videos", []):
        tot_top += v.get("total_topicos", 0)
        todos_videos.append(v)

todos_videos.sort(key=lambda v: -v.get("total_topicos", 0))

# 1) CADA VIDEO = INDICE DE TOPICOS do que ele ensina a fazer (100% da transcricao)
json.dump({"ts": base["ts"], "versao": VERSAO,
           "o_que_e": "cada video virou uma lista ordenada de TOPICOS do que ele ensina a fazer, "
                      "lida do primeiro ao ultimo bloco da transcricao bruta",
           "videos_mapeados": len(todos_videos),
           "topicos_totais": tot_top,
           "media_topicos_por_video": round(tot_top / float(len(todos_videos) or 1), 2),
           "videos": todos_videos},
          open(TOPICOS_OUT, "w", encoding="utf-8"), ensure_ascii=False)

# 2) o que EU faco + insumos
json.dump({"ts": base["ts"], "versao": VERSAO,
           "metrica": "topicos do que o video ensina a fazer, sobre 100% da transcricao bruta",
           "videos_mapeados": len(todos_videos),
           "topicos_totais": tot_top,
           "aplicacoes_no_projeto_total": tot_apl,
           "backlog_do_meu_projeto": backlog[:300],
           "backlog_por_tipo": por_tipo.most_common(),
           "produtos_mais_citados": prod.most_common(40),
           "numeros_duros": nums[:200],
           "cobertura": [{"video": v["video"], "canal": v["canal"], "link": v["link"],
                          "chars": v["chars"], "blocos": v["blocos"],
                          "blocos_lidos": v["blocos_lidos"], "cobertura_pct": v["cobertura_pct"],
                          "topicos": v["total_topicos"]} for v in todos_videos[:200]]},
          open(PAUTA, "w", encoding="utf-8"), ensure_ascii=False)

completos = sum(1 for v in todos_videos if v["cobertura_pct"] >= 100.0)
print("EXTRATOR v5: [fila: %d chamadas NICHO + %d resto] %d videos -> %d TOPICOS "
      "(media %.1f/video) | %d/%d videos com 100%% da transcricao lida | %d aplicacoes no projeto | "
      "%d chamadas IA%s | %d nao marcados (falha IA) | %d incompletos (voltam p/ fila)"
      % (ch_nicho, ch_resto, len(todos_videos), tot_top,
         tot_top / float(len(todos_videos) or 1), completos, len(todos_videos),
         tot_apl, chamadas, " (TETO - continua no proximo ciclo)" if parou_no_teto else "",
         nao_marcados, incompletos))
