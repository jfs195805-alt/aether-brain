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
VERSAO = 4

PROJETO = os.environ.get("EXTRAI_PROJETO", """MEU PROJETO (Global Supplements):
- Canal no YouTube + site de reviews. Publico: quem busca suplemento, emagrecimento, saude e fitness.
- RECEITA: (1) monetizacao de conteudo e (2) COMISSAO DE AFILIADO de produto real (ClickBank/BuyGoods/Amazon).
- Preciso de: pauta de video, gancho de abertura, estrutura de roteiro, produto para promover com
  link de afiliado, argumento de venda com prova, titulo/SEO, CTA, e taticas replicaveis.
- REGRA: conteudo ORIGINAL nosso (nunca copiar a fala do criador), foto REAL do produto,
  link de afiliado rastreavel. Nada de conselho de investimento nem promessa de cura.""")
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

PROMPT = """Voce e o analista do meu projeto. Abaixo esta UM TRECHO da transcricao bruta de um
video do YouTube (de um canal que funciona). Sua tarefa tem DUAS METADES.

{projeto}

=== METADE 1: O QUE O VIDEO ACONSELHA ===
Capture TUDO que o video recomenda, aconselha ou ensina neste trecho. NAO RESUMA, NAO PULE NADA.
Se ele recomenda 8 coisas, devolva 8. Guarde o DETALHE EXATO (numero, dose, prazo, preco, spec,
criterio) como ele falou - nunca troque numero por "pouco" ou "algum".

=== METADE 2: O QUE EU FACO COM ISSO NO MEU PROJETO ===
Para cada conselho relevante, diga o que EU devo fazer, de forma concreta e executavel.
Nao e teoria: e tarefa. Ex: "gravar video X", "promover produto Y como afiliado",
"usar este gancho no titulo", "copiar esta estrutura de roteiro", "responder esta objecao".
Se o trecho nao servir para o meu projeto, devolva "aplicacao_no_meu_projeto": [] - sem inventar.

Responda SO com JSON puro, sem markdown:

{{"sobre": "do que este trecho trata, 1 frase",
 "conselhos": [
   {{"conselho": "o que ele aconselha/recomenda/ensina",
     "porque": "a razao ou o beneficio que ele da",
     "detalhe": "numeros, doses, prazos, precos, specs, criterios EXATOS que ele citou",
     "produto": "produto/marca/ferramenta citado; vazio se nenhum",
     "para_quem": "para qual pessoa ou situacao esse conselho serve"}}
 ],
 "aplicacao_no_meu_projeto": [
   {{"acao": "o que EU faco (verbo no imperativo + objeto concreto)",
     "como": "o passo a passo pratico de como executar",
     "tipo": "pauta_de_video|produto_afiliado|gancho|estrutura_roteiro|argumento_de_venda|titulo_seo|cta|objecao|automacao",
     "por_que_funciona": "a evidencia que veio deste video"}}
 ],
 "formato_do_video": {{"gancho": "como ele prende a atencao (se este trecho for a abertura; senao vazio)",
                      "estrutura": "como ele organiza o conteudo neste trecho",
                      "cta": "a chamada para acao que ele faz; vazio se nenhuma"}},
 "produtos": ["TODOS os produtos/marcas/ferramentas/sites citados; [] se nenhum"],
 "numeros": ["TODO numero/valor/prazo/dose/preco/spec/metrica citado, com contexto. ex: '5g por dia', '228 km de autonomia', 'R$13.000'"],
 "nicho": "Suplementos|Emagrecimento|Fitness|Saude|Afiliados|IA e Tech|Financas|Negocios|Beleza|Educacao|Automoveis|Outro"}}

NAO DESCARTE NADA na METADE 1. Melhor um item a mais do que perder um conselho.
Na METADE 2, so escreva o que REALMENTE serve para o meu projeto - qualidade, nao enchimento.

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
    c = base["canais"].setdefault(canal, {"videos_processados": [], "conselhos": [],
                                          "aplicacoes": [], "formatos": [], "produtos": [],
                                          "numeros": [], "por_video": []})
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
        v_cons, v_apl, v_fmt, v_prod, v_num = [], [], [], [], []
        v_nicho = Counter()
        seen_c, seen_a, seen_pr, seen_n = set(), set(), set(), set()

        for parte in parts:
            if chamadas >= MAXCALLS or (time.time() - T0) > TEMPO_MAX:
                break
            try:
                resp = ask(PROMPT.format(projeto=PROJETO, txt=parte[:CHUNK + 500]), max_tokens=1200)
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
            for p in (d.get("conselhos") or []):
                if not isinstance(p, dict) or not (p.get("conselho") or "").strip():
                    continue
                k = norm(p.get("conselho", ""))[:70]
                if k and k not in seen_c:
                    seen_c.add(k)
                    v_cons.append({"conselho": p["conselho"].strip(),
                                   "porque": (p.get("porque") or "").strip(),
                                   "detalhe": (p.get("detalhe") or "").strip(),
                                   "produto": (p.get("produto") or "").strip(),
                                   "para_quem": (p.get("para_quem") or "").strip()})
            for a in (d.get("aplicacao_no_meu_projeto") or []):
                if not isinstance(a, dict) or not (a.get("acao") or "").strip():
                    continue
                k = norm(a.get("acao", ""))[:70]
                if k and k not in seen_a:
                    seen_a.add(k)
                    v_apl.append({"acao": a["acao"].strip(),
                                  "como": (a.get("como") or "").strip(),
                                  "tipo": (a.get("tipo") or "").strip(),
                                  "por_que_funciona": (a.get("por_que_funciona") or "").strip()})
            fm = d.get("formato_do_video") or {}
            if isinstance(fm, dict) and any((fm.get(x) or "").strip() for x in ("gancho", "estrutura", "cta")):
                v_fmt.append({"gancho": (fm.get("gancho") or "").strip(),
                              "estrutura": (fm.get("estrutura") or "").strip(),
                              "cta": (fm.get("cta") or "").strip()})
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
                               "conselhos_captados": len(v_cons),
                               "aplicacoes_no_projeto": len(v_apl),
                               "blocos_do_video": len(parts), "blocos_lidos_ok": blocos_ok,
                               "chars_transcricao": len(txt),
                               "cobertura": round(100.0 * blocos_ok / max(1, len(parts)), 1)})
        if not v_cons and not v_apl:
            videos_vazios += 1
            continue
        for x in v_cons:
            x.update({"video": vid, "link": link, "nicho": nicho})
            c["conselhos"].append(x)
        for x in v_apl:
            x.update({"video": vid, "link": link, "nicho": nicho, "canal_fonte": canal})
            c["aplicacoes"].append(x)
        for x in v_fmt:
            x.update({"video": vid, "link": link})
            c["formatos"].append(x)
        for pr in v_prod:
            c["produtos"].append({"produto": pr, "video": vid, "link": link, "nicho": nicho})
        for nu in v_num:
            c["numeros"].append({"numero": nu, "video": vid, "link": link, "nicho": nicho})
        videos_ok += 1
        print("  [%s] %s -> %d conselhos, %d aplicacoes no projeto | %d/%d blocos (%.0f%% do video)"
          % (canal[:18], vid, len(v_cons), len(v_apl), blocos_ok, len(parts),
             100.0 * blocos_ok / max(1, len(parts))), flush=True)

        # CHECKPOINT: run cancelada no meio nao pode perder o que ja foi captado
        if videos_ok % 10 == 0:
            base["ts"] = time.strftime("%FT%TZ", time.gmtime())
            json.dump(base, open(OUT, "w", encoding="utf-8"), ensure_ascii=False)
            print("  checkpoint: %d videos salvos (%d chamadas)" % (videos_ok, chamadas), flush=True)

base["ts"] = time.strftime("%FT%TZ", time.gmtime())
base["versao"] = VERSAO
json.dump(base, open(OUT, "w", encoding="utf-8"), ensure_ascii=False)

# ---------- SAIDA: o que EU faco + o que os videos aconselham ----------
backlog = []          # aplicacoes no MEU projeto (o que fazer)
conselhos_cat = []    # tudo que os videos aconselham (catalogo bruto, nada descartado)
prod = Counter()
nums = []
formatos = []
por_video = []
vistos = set()
tot_cons = tot_apl = 0
por_tipo = Counter()

for canal, c in base["canais"].items():
    for a in c.get("aplicacoes", []):
        tot_apl += 1
        k = norm(a["acao"])[:70]
        if k in vistos:
            continue
        vistos.add(k)
        por_tipo[a.get("tipo", "outro")] += 1
        backlog.append({"id": hashlib.md5(k.encode()).hexdigest()[:12],
                        "acao": a["acao"], "como": a.get("como", ""),
                        "tipo": a.get("tipo", ""), "por_que_funciona": a.get("por_que_funciona", ""),
                        "nicho": a.get("nicho", ""), "canal_fonte": canal,
                        "link_fonte": a.get("link", ""), "status": "pendente"})
    for x in c.get("conselhos", []):
        tot_cons += 1
        conselhos_cat.append(dict(x, canal_fonte=canal))
    for p in c.get("produtos", []):
        prod[p["produto"].strip().lower()] += 1
    for nu in c.get("numeros", []):
        nums.append(nu)
    for fm in c.get("formatos", []):
        formatos.append(dict(fm, canal_fonte=canal))
    for v in c.get("por_video", []):
        por_video.append(dict(v, canal=canal))

por_video.sort(key=lambda x: -x.get("conselhos_captados", 0))
nv = len(por_video) or 1

json.dump({"ts": base["ts"], "versao": VERSAO,
           "metrica": "conselhos captados e aplicacoes no meu projeto, por video (100% do video lido)",
           "videos_mapeados": nv,
           "conselhos_captados_total": tot_cons,
           "aplicacoes_no_projeto_total": tot_apl,
           "media_conselhos_por_video": round(tot_cons / float(nv), 2),
           "backlog_do_meu_projeto": backlog[:300],
           "backlog_por_tipo": por_tipo.most_common(),
           "conselhos_dos_videos": conselhos_cat[:400],
           "formatos_que_funcionam": formatos[:60],
           "produtos_mais_citados": prod.most_common(40),
           "numeros_duros": nums[:200],
           "cobertura_por_video": por_video[:150]},
          open(PAUTA, "w", encoding="utf-8"), ensure_ascii=False)

print("EXTRATOR v4: %d videos mapeados (%d sem nada, %d NAO marcados por falha de IA, %d incompletos) | "
      "%d blocos lidos | %d chamadas IA%s | %d CONSELHOS captados | %d APLICACOES no meu projeto | "
      "%d produtos | %d numeros duros"
      % (videos_ok, videos_vazios, nao_marcados, incompletos, total_chunks, chamadas,
         " (TETO - continua no proximo ciclo)" if parou_no_teto else "",
         tot_cons, tot_apl, len(prod), len(nums)))
