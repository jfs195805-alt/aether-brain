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
SO_VIDEO = os.environ.get("EXTRAI_VIDEO", "").strip()   # roda SO este video (teste)
MAXV = int(os.environ.get("EXTRAI_MAXV", "60"))
CHUNK = int(os.environ.get("EXTRAI_CHUNK", "3000"))   # bloco menor = mais detalhe captado
MAXCHUNKS = int(os.environ.get("EXTRAI_MAXCHUNKS", "0"))  # 0 = SEM TETO: video INTEIRO
MAXCALLS = int(os.environ.get("EXTRAI_MAXCALLS", "1400"))
TEMPO_MAX = int(os.environ.get("EXTRAI_TEMPO_MAX", "1500"))  # segundos (25 min)
MAXTENT = int(os.environ.get("EXTRAI_MAXTENT", "3"))   # tentativas antes de aceitar parcial
T0 = time.time()
VERSAO = 15

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
    import ai_providers as _AP
except Exception:
    ask = None
    _AP = None

# ---- MODELO FORTE para o AGENTE 2 ----
# O Agente 1 faz trabalho MECANICO (listar o que esta escrito) -> modelo rapido serve.
# O Agente 2 faz o trabalho DIFICIL (descobrir o padrao que ninguem escreveu) -> merece o melhor.
GEM_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
MODELOS_FORTES = [m for m in (os.environ.get("GEMINI_PRO_MODEL", ""),
                              os.environ.get("AI_MODELO_FORTE", ""),
                              "gemini-2.5-pro", "gemini-2.0-flash") if m]


def ask_forte(prompt, max_tokens=1600):
    """Usado SO pelo AGENTE 2. Tenta o modelo forte; se nao houver, cai na ordem normal."""
    k = os.environ.get("GEMINI_API_KEY")
    if k and _AP is not None:
        for m in MODELOS_FORTES:
            try:
                t = _AP._call("gemini", GEM_URL, k, m, prompt, max_tokens=max_tokens, timeout=70)
                if t and t.strip():
                    return t
            except Exception:
                continue
    return ask(prompt, max_tokens=max_tokens)

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



# ---------- VALIDADOR ANTI-COPIA (o Agente 2 copiou o gabarito uma vez; nunca mais) ----------
# ERRO REAL: num video sobre INTESTINO, o Agente 2 respondeu "ranking de 16 micro carros
# eletricos, preco explicito no fecho" - copiou o exemplo do prompt em vez de olhar os dados.
# Este validador compara a sintese com os topicos REAIS. Se a sintese fala de coisa que nao
# existe nos topicos, e cópia/alucinacao -> REJEITA.
_PALAVRA = re.compile(r"[a-zA-ZÀ-ÿ]{5,}")
_NUMERO = re.compile(r"\d[\d.,]*")


def valida_sintese(sintese, v_top, ntop):
    """Rejeita sintese COPIADA/ALUCINADA. Criterio: ANCORAGEM, nao vocabulario.
    Uma sintese honesta FALA DO VIDEO -> suas palavras de conteudo aparecem nos topicos.
    A fraude real ("ranking de 16 micro carros" num video de intestino) nao ancora em nada.
    Devolve (ok, motivo)."""
    if not isinstance(sintese, dict):
        return False, "resposta nao e JSON"

    base_txt = norm(" ".join(
        (t.get("topico", "") + " " + t.get("ensina_a_fazer", "") + " " + t.get("como", "") + " " +
         t.get("deve_ser_copiado", "") + " " + " ".join(t.get("produtos", [])) + " " +
         " ".join(t.get("numeros", []))) for t in v_top))
    base_pref = {w[:5] for w in _PALAVRA.findall(base_txt)}
    base_nums = set(_NUMERO.findall(base_txt))

    # texto para ANCORAGEM (inclui evidencia: e texto normal)
    sint_txt = " ".join([str(sintese.get("entendimento_do_video", "")),
                         str(sintese.get("padrao_que_se_repete", "")),
                         " ".join(str(a.get("o_que", "")) + " " + str(a.get("como_aplicar", "")) +
                                  " " + str(a.get("evidencia", ""))
                                  for a in (sintese.get("agregar") or []) if isinstance(a, dict))])
    # texto para checar NUMERO INVENTADO -> NUNCA inclui 'evidencia' (la os numeros sao
    # indices de topico, e legitimo citar "topicos 1, 4 e 9"). Bug real: o validador
    # rejeitava a sintese honesta por causa disso.
    sint_num_txt = " ".join([str(sintese.get("entendimento_do_video", "")),
                             str(sintese.get("padrao_que_se_repete", "")),
                             " ".join(str(a.get("o_que", "")) + " " + str(a.get("como_aplicar", ""))
                                      for a in (sintese.get("agregar") or []) if isinstance(a, dict))])
    sw = _PALAVRA.findall(norm(sint_txt))
    if not sw:
        return False, "sintese vazia"

    # ESTRUTURAIS: palavras de forma (nao sao conteudo do video) - nao contam nem a favor nem contra
    ESTRUT = set(("video", "topico", "topicos", "produto", "produtos", "conteudo", "formato",
                  "estrutura", "publico", "canal", "projeto", "afiliado", "roteiro", "gancho",
                  "titulo", "aplicar", "funciona", "repete", "molde", "espectador", "audiencia",
                  "comando", "ciencia", "ponto", "entrada", "minimo", "passo", "passos", "item",
                  "itens", "aparece", "ensina", "explicito", "fechamento", "abertura", "secao",
                  "sempre", "nunca", "ainda", "tambem", "assim", "cada", "todos", "todas",
                  "melhor", "maior", "menor", "quando", "depois", "antes", "durante", "porque",
                  "criar", "adicionar", "incluir", "comecar", "usar", "fazer", "primeiro"))
    conteudo = [w for w in sw if w not in ESTRUT]
    if not conteudo:
        return True, "ok (so estrutura)"

    ancorados = [w for w in conteudo if w[:5] in base_pref]
    taxa = len(ancorados) / float(len(conteudo))

    # ANCORAGEM: a sintese TEM que falar do que esta nos topicos
    if len(ancorados) < 3 or taxa < 0.25:
        estranhas = sorted(set(w for w in conteudo if w[:5] not in base_pref))[:8]
        return False, ("nao ancora nos topicos (so %d/%d palavras de conteudo batem, %d%%) - "
                       "fala de: %s" % (len(ancorados), len(conteudo), int(100 * taxa), estranhas))

    # NUMEROS inventados (fora da evidencia). Inteiro pequeno (<= ntop) pode ser referencia
    # a topico dentro do texto -> nao conta como invencao.
    fora = []
    for n in set(_NUMERO.findall(sint_num_txt)):
        nn = n.strip(".,")
        if not nn or nn in base_nums:
            continue
        try:
            if int(nn) <= ntop:      # "os 5 passos", "topico 3" - referencia legitima
                continue
        except Exception:
            pass
        fora.append(nn)
    if fora:
        return False, "cita numeros que nao estao nos topicos: %s" % fora[:5]

    # EVIDENCIA tem que apontar para topico que EXISTE
    for a in (sintese.get("agregar") or []):
        if not isinstance(a, dict):
            continue
        for n in _NUMERO.findall(str(a.get("evidencia", ""))):
            try:
                if int(n) > ntop:
                    return False, "evidencia cita 'topico %s' mas so existem %d topicos" % (n, ntop)
            except Exception:
                pass
    return True, "ok (%d%% ancorado)" % int(100 * taxa)


TIPOS_OK = ("estrutura_roteiro", "gancho", "argumento_de_venda", "titulo_seo", "cta",
             "objecao", "pauta_de_video", "produto_afiliado", "automacao")


def limpa_tipo(t):
    """O modelo as vezes devolve o enum inteiro. Pega o primeiro tipo valido; senao 'outro'."""
    t = (t or "").strip().lower()
    if t in TIPOS_OK:
        return t
    for x in TIPOS_OK:              # "estrutura_roteiro|gancho|..." -> pega o 1o valido citado
        if x in t:
            return x
    return "outro"


def filtra_agregar(sintese, v_top):
    """Descarta ITEM A ITEM o que nao ancora nos topicos deste video.
    ERRO REAL: num video sobre morte por anabolizante o modelo propos 'contagem regressiva com
    faixa de preco' - copiado de uma lista de pendencias que eu mesmo tinha dado. Item
    contaminado pegava carona no texto ancorado e passava. Agora cada item responde por si."""
    base_txt = norm(" ".join(
        (t.get("topico", "") + " " + t.get("ensina_a_fazer", "") + " " + t.get("como", "") + " " +
         t.get("deve_ser_copiado", "")) for t in v_top))
    base_pref = {w[:5] for w in _PALAVRA.findall(base_txt)}
    ESTRUT2 = set(("video", "topico", "topicos", "produto", "produtos", "conteudo", "formato",
                   "estrutura", "publico", "canal", "projeto", "afiliado", "roteiro", "gancho",
                   "titulo", "aplicar", "incluir", "criar", "adicionar", "usar", "fazer",
                   "secao", "abertura", "fechamento", "padrao", "molde", "item", "itens",
                   "review", "reviews", "link", "espectador", "audiencia", "mensagem"))
    bons, cortados = [], []
    for a in (sintese.get("agregar") or []):
        if not isinstance(a, dict):
            continue
        txt = norm(str(a.get("o_que", "")) + " " + str(a.get("como_aplicar", "")))
        cw = [w for w in _PALAVRA.findall(txt) if w not in ESTRUT2]
        if not cw:
            cortados.append((a.get("o_que", "?"), "sem conteudo"))
            continue
        anc = [w for w in cw if w[:5] in base_pref]
        if len(anc) < 2 or (len(anc) / float(len(cw))) < 0.30:
            cortados.append((a.get("o_que", "?"),
                             "so %d/%d palavras ancoram no video" % (len(anc), len(cw))))
            continue
        a["tipo"] = limpa_tipo(a.get("tipo"))
        bons.append(a)
    sintese["agregar"] = bons
    return cortados


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

# PROGRESSO PARCIAL por video: {video_id: {"blocos_ok": [1,3,4], "topicos": [...]}}
# ERRO REAL: a regra "100% ou nada" jogava 3m39s de trabalho fora quando 1 bloco de 5 falhava.
# Agora o que deu certo FICA GRAVADO e o proximo ciclo retenta SO o bloco que faltou.
parcial = base.setdefault("parcial", {})

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
PROMPT2 = """Voce ja leu este video em pedacos e listou o que ele ensina. Agora leia o video
INTEIRO, de uma vez, e olhe para ele como um todo.

MODELO (a ideia do que procurar - feito sobre OUTRO video; o conteudo dele nao e deste video):
{modelo}

{projeto}

O QUE MEU PROJETO JA TEM (nao repita):
{ja_tenho}

=================== A TRANSCRICAO BRUTA COMPLETA DO VIDEO ===================
{transcricao}
=============================================================================

O QUE VOCE JA TIROU DELE:
{topicos}

Agora, olhando o VIDEO INTEIRO:

- Como ele comeca? Como ele termina? O que ele faz no meio?
- Existe um MOLDE que ele repete? (nao olhe a lista acima - olhe a transcricao)
- Onde entra o produto/venda? Logo no comeco, ou depois de entregar valor de graca?
- O que faz ESTE video funcionar?

Responda SO com JSON puro:

{{"entendimento_do_video": "o que ESTE video e e por que funciona",
 "padrao_que_se_repete": "o molde que ele repete NA TRANSCRICAO (nao na lista); \"\" se nao houver",
 "agregar": [
   {{"o_que": "a tatica concreta que eu devo copiar para o meu projeto",
     "como_aplicar": "o passo a passo pratico",
     "tipo": "estrutura_roteiro|gancho|argumento_de_venda|titulo_seo|cta|objecao|pauta_de_video|produto_afiliado|automacao",
     "evidencia": "o trecho do video que prova isso",
     "ja_tenho_parecido": "sim/nao"}}
 ],
 "nada_novo": "se nao houver nada a agregar, o motivo; senao \"\""}}
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
        if SO_VIDEO and vid != SO_VIDEO:
            continue
        txt = limpa(r.get("transcript") or "")
        if len(txt) < 400:
            continue

        parts = blocos(txt)
        if not parts:
            continue

        pv = parcial.setdefault(vid, {"blocos_ok": [], "topicos": [], "prod": [], "num": []})
        ja_ok = set(pv["blocos_ok"])          # blocos que ciclos anteriores ja leram
        ok_ia = bool(ja_ok)
        blocos_ok = len(ja_ok)
        if ja_ok:
            print("  [%s] %s -> retomando: %d/%d blocos ja lidos, falta %s"
                  % (canal[:18], vid, len(ja_ok), len(parts),
                     [i for i in range(1, len(parts) + 1) if i not in ja_ok]), flush=True)
        v_top, v_prod, v_num = [], [], []
        v_apl = []   # preenchido pelo AGENTE 2
        blocos_com_topico = set()
        v_nicho = Counter()
        seen_t, seen_a, seen_pr, seen_n = set(), set(), set(), set()

        for bi, parte in enumerate(parts):
            if (bi + 1) in ja_ok:            # bloco ja lido em ciclo anterior -> nao gasta IA de novo
                continue
            if chamadas >= (ORC_NICHO if eh_nicho else MAXCALLS) or (time.time() - T0) > TEMPO_MAX:
                break
            try:
                resp = ask(PROMPT.format(modelo=MODELO_A1, bloco=bi + 1, total=len(parts),
                                         txt=parte[:CHUNK + 500]), max_tokens=1400)
            except Exception as e:
                falhas_ia += 1
                print("      bloco %d/%d: FALHA na IA (%s)" % (bi + 1, len(parts), str(e)[:60]), flush=True)
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
                print("      bloco %d/%d: resposta sem JSON" % (bi + 1, len(parts)), flush=True)
                continue
            try:
                d = json.loads(m.group(0))
            except Exception as e:
                falhas_ia += 1
                print("      bloco %d/%d: JSON invalido (%s)" % (bi + 1, len(parts), str(e)[:50]), flush=True)
                continue
            ok_ia = True
            blocos_ok += 1
            pv["blocos_ok"].append(bi + 1)      # <<< GRAVA NA HORA: nunca mais perde este bloco
            if d.get("nicho"):
                v_nicho[d["nicho"]] += 1
            for t in (d.get("topicos") or []):
                if not isinstance(t, dict) or not (t.get("topico") or "").strip():
                    continue
                k = norm(t.get("topico", ""))[:70]
                if k and k not in seen_t:
                    seen_t.add(k)
                    blocos_com_topico.add(bi + 1)
                    _t = {"topico": t["topico"].strip(),
                          "ensina_a_fazer": (t.get("ensina_a_fazer") or "").strip(),
                          "como": (t.get("como") or "").strip(),
                          "deve_ser_copiado": (t.get("deve_ser_copiado") or "").strip(),
                          "produtos": [str(x).strip() for x in (t.get("produtos") or [])],
                          "numeros": [str(x).strip() for x in (t.get("numeros") or [])],
                          "bloco": bi + 1, "de_blocos": len(parts)}
                    pv["topicos"].append(_t)      # <<< PERSISTE NA HORA (nunca perde)
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

        # reconstitui a lista de topicos a partir do que esta PERSISTIDO (todos os ciclos)
        v_top = []
        seen_tt = set()
        for _t in sorted(pv["topicos"], key=lambda x: x.get("bloco", 0)):
            k = norm(_t.get("topico", ""))[:70]
            if k and k not in seen_tt:
                seen_tt.add(k)
                v_top.append(dict(_t, n=len(v_top) + 1))
        blocos_ok = len(set(pv["blocos_ok"]))
        blocos_com_topico = {t.get("bloco") for t in v_top if t.get("bloco")}
        v_prod = sorted({p for t in v_top for p in t.get("produtos", []) if p})
        v_num = [n for t in v_top for n in t.get("numeros", []) if n]

        # NAO DEIXAR PASSAR NADA: o video so e dado como MAPEADO se TODOS os blocos foram lidos.
        # Se algum bloco falhou, o video volta para a fila (ate MAXTENT tentativas).
        tent = base.setdefault("tentativas", {})
        completo = (blocos_ok == len(parts))
        if ok_ia and not completo:
            t = tent.get(vid, 0) + 1
            tent[vid] = t
            if t < MAXTENT:
                incompletos += 1
                print("  [%s] %s -> INCOMPLETO (%d/%d blocos, %d topicos JA SALVOS) - retenta so o que falta (tentativa %d)"
                      % (canal[:18], vid, blocos_ok, len(parts), len(v_top), t), flush=True)
                base["ts"] = time.strftime("%FT%TZ", time.gmtime())
                json.dump(base, open(OUT, "w", encoding="utf-8"), ensure_ascii=False)   # SALVA o parcial
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
        if v_top and blocos_ok == len(parts):
            # PROSA, sem rotulos repetidos: o modelo antes olhava "ENSINA:/COMO:/COPIAR:"
            # repetido N vezes e dizia "o padrao e ENSINA/COMO/COPIAR". Padrao falso, criado
            # por mim no proprio input. Agora vai como texto corrido.
            resumo_top = "\n".join(
                "%d. %s - %s (%s)" % (t["n"], t["topico"], t["ensina_a_fazer"], t["como"])
                for t in v_top)
            try:
                r2 = ask_forte(PROMPT2.format(modelo=MODELO_A2, projeto=PROJETO, ja_tenho=JA_TENHO,
                                              transcricao=txt[:14000],   # <<< O VIDEO INTEIRO
                                              topicos=resumo_top[:6000]), max_tokens=1600)
                chamadas += 1
                if eh_nicho:
                    ch_nicho += 1
                else:
                    ch_resto += 1
                m2 = re.search(r"\{.*\}", r2 or "", re.S)
                if m2:
                    cand = json.loads(m2.group(0))
                    ok, motivo = valida_sintese(cand, v_top, len(v_top))
                    if ok:
                        sintese = cand
                        for oq, motivo in filtra_agregar(sintese, v_top):
                            print("      item CORTADO (nao e deste video): %s [%s]"
                                  % (str(oq)[:60], motivo), flush=True)
                    else:
                        print("      AGENTE 2 REJEITADO: %s -> refazendo" % motivo, flush=True)
                        r2b = ask_forte(PROMPT2.format(modelo=MODELO_A2, projeto=PROJETO, ja_tenho=JA_TENHO,
                                                       transcricao=txt[:14000],
                                                       topicos=resumo_top[:6000]) +
                                        "\n\nATENCAO: sua resposta anterior foi REJEITADA porque %s. "
                                        "Olhe SO os topicos acima. Nao invente nada." % motivo,
                                        max_tokens=1600)
                        chamadas += 1
                        m2b = re.search(r"\{.*\}", r2b or "", re.S)
                        if m2b:
                            cand2 = json.loads(m2b.group(0))
                            ok2, motivo2 = valida_sintese(cand2, v_top, len(v_top))
                            if ok2:
                                sintese = cand2
                                for oq, motivo in filtra_agregar(sintese, v_top):
                                    print("      item CORTADO (nao e deste video): %s [%s]"
                                          % (str(oq)[:60], motivo), flush=True)
                                print("      AGENTE 2: passou na 2a tentativa", flush=True)
                            else:
                                print("      AGENTE 2 REJEITADO 2x (%s) -> sintese DESCARTADA" % motivo2, flush=True)
            except Exception as e:
                print("      AGENTE 2: erro (%s)" % str(e)[:60], flush=True)
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


# ---------- MODO TESTE: imprime o resultado do video no log ----------
if SO_VIDEO and todos_videos:
    v = todos_videos[0]
    print("\n" + "=" * 78)
    print("RESULTADO REAL — video %s (%s)" % (v["video"], v["canal"]))
    print("%d chars | %d blocos | LIDOS %d/%d = %.0f%%"
          % (v["chars"], v["blocos"], v["blocos_lidos"], v["blocos"], v["cobertura_pct"]))
    print("=" * 78)
    print("\n--- AGENTE 1 (TOPICADOR): %d topicos ---" % v["total_topicos"])
    for t in v["TOPICOS"]:
        print("\n%d. [bloco %d/%d] %s" % (t["n"], t["bloco"], t["de_blocos"], t["topico"]))
        print("   ENSINA A FAZER: %s" % t["ensina_a_fazer"])
        print("   COMO: %s" % t["como"])
        if t.get("deve_ser_copiado"):
            print("   DEVE SER COPIADO: %s" % t["deve_ser_copiado"])
        if t.get("numeros"):
            print("   NUMEROS: %s" % ", ".join(t["numeros"]))
    sx = v.get("SINTESE_DO_VIDEO") or {}
    print("\n\n--- AGENTE 2 (SINTETIZADOR) ---")
    print("\nENTENDIMENTO DO VIDEO:\n   %s" % (sx.get("entendimento") or "(vazio)"))
    print("\nPADRAO QUE SE REPETE:\n   %s" % (sx.get("padrao_que_se_repete") or "(nao encontrou)"))
    print("\nO QUE AGREGAR NO MEU PROJETO:")
    if not v.get("AGREGAR_NO_MEU_PROJETO"):
        print("   (nada) motivo: %s" % (sx.get("nada_novo") or "-"))
    for a in v.get("AGREGAR_NO_MEU_PROJETO", []):
        ja = a.get("ja_tenho_parecido", "")
        flag = "  <<< JA TENHO - descartar" if ja.lower().startswith("sim") else ""
        print("\n   [%s] %s%s" % (a.get("tipo", "?"), a["o_que"], flag))
        print("      COMO APLICAR: %s" % a.get("como_aplicar", ""))
        print("      EVIDENCIA   : %s" % a.get("evidencia", ""))
    print("\n" + "=" * 78)
