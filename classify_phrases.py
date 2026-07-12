#!/usr/bin/env python3
"""classify_phrases.py v2 - CLASSIFICA TODAS AS FRASES DE TODOS OS CANAIS, de verdade.

O v1 exigia 2 palavras exatas de uma listinha -> classificava 0,8% do corpus. Lixo.

v2 (estatistico, scipy):
  1. Le TODAS as frases (mesma pre-juncao/subagrupamento do grafo).
  2. TF-IDF esparso de tudo.
  3. SEMENTES por categoria (termos obvios) -> EXPANDIDAS PELO PROPRIO CORPUS:
     cada semente puxa os termos que mais co-ocorrem com ela (vizinhanca semantica real),
     virando um vetor rico de ~150 termos por categoria, aprendido dos seus 592 canais.
  4. Cada frase e classificada pelo cosseno com os vetores de categoria (multi-rotulo).
  5. Frase que nao bate com nada fica "sem categoria" - honesto, sem forcar.

Saida: FRASES_CATEGORIAS.json (contagem real por categoria + cobertura + exemplos com prova)
"""
import os, re, json, glob, time, math
import numpy as np
from collections import Counter, defaultdict
from scipy.sparse import csr_matrix

SRC = os.environ.get("NG_SRC", "transcripts")
NG = "NEURAL_GRAPH.json"
OUT = "FRASES_CATEGORIAS.json"
MAXR = int(os.environ.get("CLS_RECS", "1000"))     # todos os videos
EXP = int(os.environ.get("CLS_EXPAND", "150"))     # termos por categoria apos expansao
LIM = float(os.environ.get("CLS_LIM", "0.10"))     # limiar de pertencimento

SEM = {
 "Suplementos": "suplemento suplementos whey creatina proteina proteinas vitamina vitaminas colageno omega magnesio zinco multivitaminico dosagem miligramas supplement protein creatine vitamin capsula",
 "Emagrecimento": "emagrecer emagrecimento gordura dieta jejum calorias deficit metabolismo peso obesidade queimar magro barriga weight fat diet",
 "Fitness": "treino treinos musculo musculos hipertrofia academia exercicio exercicios serie repeticoes agachamento cardio workout muscle gym training",
 "Afiliados": "afiliado afiliados comissao link vendas funil conversao trafego copy oferta hotmart monetizar afiliacao affiliate commission funnel",
 "IA e Tech": "inteligencia artificial chatgpt modelo algoritmo automacao software prompt agente aplicativo programacao tecnologia machine learning",
 "Financas": "investir investimento renda dinheiro juros acoes bolsa dolar economia salario financeiro poupanca lucro invest money",
 "Cripto": "bitcoin cripto criptomoeda blockchain token carteira ethereum nft exchange trading satoshi crypto wallet",
 "Negocios": "empresa negocio negocios cliente clientes vendas faturamento empreendedor mercado marca produto equipe business revenue",
 "Saude": "saude medico doenca sintoma tratamento exame remedio imunidade sono estresse inflamacao health disease",
 "Psicologia": "mente emocao emocoes ansiedade habito habitos disciplina foco motivacao comportamento cerebro autoestima anxiety",
 "Beleza": "pele cabelo rosto rugas beleza skincare creme unha maquiagem estetica hair skin beauty",
 "Educacao": "estudar estudo curso faculdade aprender aula prova carreira diploma professor college learn",
 "Culinaria": "receita comida cozinhar ingrediente sabor tempero prato refeicao food recipe cook",
 "Games": "jogo jogos game gameplay console jogar personagem fase steam",
 "Noticias": "governo politica presidente lei imposto eleicao noticia pais congresso",
}

STOP = set(("a o e de da do das dos que em um uma para com nao os as no na por mais como mas ao se ou ja "
            "isso esse essa este esta muito voce tem ser sao foi vai pode entao aqui tudo todo toda bem "
            "ainda pra pro sobre quando onde qual quais eu meu minha nos eles elas ele ela cara gente coisa "
            "the of and to in is it you that this for on with are be as at your we can will have has from").split())
TERM = re.compile(r"[a-zA-ZÀ-ÿ]{4,}")
MINW, MAXW, MINC = 9, 32, 5
MAXB, MAXBW, COESAO = 3, 70, 0.12
DANGLE = set(("e ou mas que porque pois se de da do para com por em na no ao as os um uma the a an and or but "
              "that because if of to for with in on at is are was were be been as by from than then so").split())
LIXO = re.compile(r"\[(music|musica|applause|aplausos|risos|laughter)[^\]]*\]", re.I)


def conteudo(fr):
    return [w for w in TERM.findall(fr.lower()) if w not in STOP]

def limpa_inicio(fr):
    w = fr.split()
    while w and w[0].strip(".,;:").lower() in DANGLE:
        w.pop(0)
    return " ".join(w)

def coerentiza(unid):
    out, buf, start = [], [], None
    for txt, st in unid:
        txt = LIXO.sub(" ", txt or "").strip()
        if not txt:
            continue
        if start is None:
            start = st
        buf.extend(txt.split())
        while True:
            nw = len(buf)
            if nw < MINW:
                break
            corte = None
            for i in range(MINW - 1, min(nw, MAXW)):
                if buf[i].endswith((".", "!", "?")):
                    corte = i + 1
                    break
            if corte is None and nw >= MAXW:
                corte = MAXW
                while corte > MINW and buf[corte - 1].strip(".,;:").lower() in DANGLE:
                    corte -= 1
            if corte is None:
                break
            fr = limpa_inicio(" ".join(buf[:corte]).strip(" ,;:-"))
            buf = buf[corte:]
            if len(conteudo(fr)) >= MINC and len(fr) >= 45:
                out.append((fr, start))
            start = st if buf else None
    if buf:
        fr = limpa_inicio(" ".join(buf).strip(" ,;:-"))
        if len(conteudo(fr)) >= MINC and len(fr) >= 45:
            out.append((fr, start))
    return out

def subagrupa(fv):
    blocos, cur, cs, start = [], [], set(), None
    for fr, st in fv:
        t = set(conteudo(fr))
        if not cur:
            cur, cs, start = [fr], set(t), st
            continue
        jac = len(cs & t) / (len(cs | t) or 1)
        pal = sum(len(x.split()) for x in cur) + len(fr.split())
        if jac >= COESAO and len(cur) < MAXB and pal <= MAXBW:
            cur.append(fr); cs |= t
        else:
            blocos.append((" ".join(cur), start)); cur, cs, start = [fr], set(t), st
    if cur:
        blocos.append((" ".join(cur), start))
    return blocos

# ---------- 1) TODAS as frases ----------
frases = []
for f in sorted(glob.glob(os.path.join(SRC, "*.jsonl"))):
    canal = os.path.splitext(os.path.basename(f))[0]
    try:
        lines = open(f, encoding="utf-8", errors="ignore").read().split("\n")[:MAXR]
    except Exception:
        continue
    for ln in lines:
        if not ln.strip():
            continue
        try:
            r = json.loads(ln)
        except Exception:
            continue
        txt = r.get("transcript") or ""
        if len(txt) < 80:
            continue
        vid = r.get("video_id", "")
        for fr, _ in subagrupa(coerentiza([(txt, None)])):
            frases.append((fr, vid, canal))

NF = len(frases)
if not NF:
    json.dump({"erro": "sem corpus"}, open(OUT, "w")); raise SystemExit

# ---------- 2) TF-IDF ----------
toks = [set(conteudo(f[0])) for f in frases]
df = Counter()
for t in toks:
    df.update(t)
vocab = {w: i for i, (w, c) in enumerate(df.most_common(60000)) if c >= 3}
IDF = np.zeros(len(vocab), dtype=np.float32)
for w, i in vocab.items():
    IDF[i] = math.log(NF / (1.0 + df[w]))

indptr, indices, data = [0], [], []
for t in toks:
    idx = [vocab[w] for w in t if w in vocab]
    if idx:
        val = IDF[idx]
        nrm = float(np.linalg.norm(val)) or 1.0
        indices.extend(idx); data.extend((val / nrm).tolist())
    indptr.append(len(indices))
X = csr_matrix((np.array(data, dtype=np.float32), np.array(indices, dtype=np.int32),
                np.array(indptr, dtype=np.int64)), shape=(NF, len(vocab)))

# ---------- 3) SEMENTES EXPANDIDAS PELO CORPUS ----------
# termo-termo: quais palavras vivem junto das sementes nas frases reais
XT = X.T.tocsr()
CATV = {}
expandido = {}
for cat, sem in SEM.items():
    seeds = [w for w in sem.split() if w in vocab]
    if not seeds:
        continue
    rows = [vocab[w] for w in seeds]
    # frases que contem alguma semente
    mask = np.zeros(NF, dtype=bool)
    for r in rows:
        mask[XT[r].indices] = True
    sub = X[mask]
    if sub.shape[0] < 5:
        continue
    peso = np.asarray(sub.sum(axis=0)).ravel()      # termos que mais aparecem junto
    top = np.argsort(-peso)[:EXP]
    v = np.zeros(len(vocab), dtype=np.float32)
    v[top] = peso[top]
    for r in rows:
        v[r] = max(v[r], peso.max())                 # semente pesa no maximo
    n = np.linalg.norm(v) or 1.0
    CATV[cat] = v / n
    inv = {i: w for w, i in vocab.items()}
    expandido[cat] = [inv[i] for i in top[:12]]

if not CATV:
    json.dump({"erro": "sem categorias"}, open(OUT, "w")); raise SystemExit

cats = list(CATV.keys())
M = np.vstack([CATV[c] for c in cats])              # (categorias x vocab)

# ---------- 4) classifica TODAS as frases (em lotes) ----------
cont = Counter()
sem_cat = 0
exemplos = defaultdict(list)
B = 20000
for i0 in range(0, NF, B):
    S = (X[i0:i0 + B] @ M.T)                        # (lote x categorias)
    S = np.asarray(S.todense()) if hasattr(S, "todense") else np.asarray(S)
    best = S.argmax(axis=1)
    val = S.max(axis=1)
    for k in range(S.shape[0]):
        if val[k] < LIM:
            sem_cat += 1
            continue
        c = cats[best[k]]
        cont[c] += 1
        if len(exemplos[c]) < 8:
            fr, vid, canal = frases[i0 + k]
            exemplos[c].append({"frase": fr[:200], "canal": canal, "video": vid,
                                "link": ("https://youtu.be/" + vid) if vid else "",
                                "score": round(float(val[k]), 3)})

classificadas = sum(cont.values())
out = {"ts": time.strftime("%FT%TZ", time.gmtime()),
       "frases_varridas": NF,
       "frases_classificadas": classificadas,
       "sem_categoria": sem_cat,
       "cobertura_pct": round(100.0 * classificadas / NF, 1),
       "ranking": [c for c, _ in cont.most_common()],
       "categorias": {c: {"n_frases_corpus": cont.get(c, 0),
                          "termos_top": expandido.get(c, [])[:10],
                          "exemplos": exemplos.get(c, [])} for c in cats}}
json.dump(out, open(OUT, "w", encoding="utf-8"), ensure_ascii=False)
print("CATEGORIAS v2: %s frases varridas | %s CLASSIFICADAS (%.1f%%) | %s sem categoria | top: %s"
      % (format(NF, ",d"), format(classificadas, ",d"), out["cobertura_pct"], format(sem_cat, ",d"),
         ", ".join("%s=%s" % (c, format(n, ",d")) for c, n in cont.most_common(5))))
