#!/usr/bin/env python3
"""classify_phrases.py - CLASSIFICA CADA FRASE em categoria (nao o canal: a FRASE).

Le o grafo (NEURAL_GRAPH.json) + o corpus e classifica cada afirmacao pelo seu CONTEUDO
em categorias de negocio. Junta as frases por categoria -> o cerebro passa a saber
"o que se sabe sobre Suplementos", "sobre Emagrecimento", etc., com prova (video + tempo).

Escreve: FRASES_CATEGORIAS.json
  {categorias: {cat: {n_frases, exemplos:[{frase,canal,video,link,t}], termos_top:[..]}}, ...}
"""
import os, re, json, glob, time
from collections import Counter, defaultdict

NG = os.environ.get("NG_OUT", "NEURAL_GRAPH.json")
SRC = os.environ.get("NG_SRC", "transcripts")
OUT = "FRASES_CATEGORIAS.json"
MAXR = int(os.environ.get("CLS_RECS", "120"))

CATS = {
  "Suplementos": "suplemento whey creatina proteina vitamina colageno omega magnesio zinco multivitaminico dose miligrama supplement protein creatine vitamin",
  "Emagrecimento": "emagrecer emagrecimento gordura dieta jejum calorias deficit metabolismo peso obesidade queima weight loss fat diet",
  "Fitness": "treino musculo hipertrofia academia exercicio serie repeticao agachamento cardio workout muscle gym training",
  "Afiliados": "afiliado comissao link venda funil conversao trafego copy oferta hotmart monetizar affiliate commission funnel",
  "IA e Tech": "inteligencia artificial chatgpt modelo algoritmo automacao software prompt api agente machine learning ai tool",
  "Financas": "investir renda dinheiro juros acao bolsa dolar economia salario financeiro poupanca invest money income",
  "Cripto": "bitcoin cripto blockchain token carteira ethereum nft exchange satoshi crypto wallet",
  "Negocios": "empresa negocio cliente vendas faturamento lucro empreendedor mercado marca produto business revenue",
  "Saude": "saude medico doenca sintoma tratamento exame remedio imunidade sono estresse health disease",
  "Psicologia": "mente emocao ansiedade habito disciplina foco motivacao comportamento cerebro mind anxiety habit",
  "Beleza": "pele cabelo rosto rugas colageno beleza skincare creme unha hair skin beauty",
  "Educacao": "estudar curso faculdade aprender aula prova carreira degree college learn study",
  "Culinaria": "receita comida cozinhar ingrediente sabor tempero prato food recipe cook",
  "Games": "jogo game gameplay console jogar personagem fase",
  "Noticias": "governo politica presidente lei imposto eleicao noticia pais",
}
KW = {c: set(v.split()) for c, v in CATS.items()}
W = re.compile(r"[a-zA-ZÀ-ÿ]{4,}")


def classifica(frase):
    t = set(w for w in W.findall(frase.lower()))
    best, score = None, 0
    for c, ks in KW.items():
        s = len(t & ks)
        if s > score:
            best, score = c, s
    return (best, score) if score >= 2 else (None, 0)


try:
    g = json.load(open(NG, encoding="utf-8"))
except Exception:
    g = {"nodes": []}

por_cat = defaultdict(list)
termos = defaultdict(Counter)
n_class = 0
n_total = 0

# 1) frases do grafo (as mais informativas) -> exemplos com prova
for n in g.get("nodes", []):
    n_total += 1
    c, s = classifica(n.get("frase", ""))
    if not c:
        continue
    n_class += 1
    por_cat[c].append({"frase": n["frase"][:200], "canal": n.get("canal"),
                       "video": n.get("video"), "t": n.get("t"),
                       "link": n.get("link"), "peso": n.get("peso")})
    termos[c].update(w for w in W.findall(n["frase"].lower()) if w in KW[c])

# 2) varre o corpus para CONTAR o volume real de frases por categoria
SPLIT = re.compile(r"(?<=[.!?])\s+|\n+")
contagem = Counter()
frases_vistas = 0
for f in sorted(glob.glob(os.path.join(SRC, "*.jsonl"))):
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
        for fr in SPLIT.split(txt):
            if len(fr) < 45:
                continue
            frases_vistas += 1
            c, s = classifica(fr)
            if c:
                contagem[c] += 1

cats = {}
for c in CATS:
    ex = sorted(por_cat.get(c, []), key=lambda x: -(x.get("peso") or 0))[:8]
    cats[c] = {"n_frases_corpus": contagem.get(c, 0),
               "n_no_grafo": len(por_cat.get(c, [])),
               "termos_top": [w for w, _ in termos[c].most_common(8)],
               "exemplos": ex}

out = {"ts": time.strftime("%FT%TZ", time.gmtime()),
       "frases_varridas": frases_vistas,
       "frases_classificadas": sum(contagem.values()),
       "pontos_grafo_classificados": n_class,
       "ranking": [c for c, _ in contagem.most_common()],
       "categorias": cats}
json.dump(out, open(OUT, "w", encoding="utf-8"), ensure_ascii=False)
print("CATEGORIAS: %d frases varridas | %d classificadas | top: %s"
      % (frases_vistas, sum(contagem.values()),
         ", ".join("%s=%d" % (c, n) for c, n in contagem.most_common(5))))
