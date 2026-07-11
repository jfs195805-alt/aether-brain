#!/usr/bin/env python3
"""GRAFO NEURAL REAL, FRASE-A-FRASE, COM PRE-JUNCAO (RAM 16GB do GitHub Actions).

PRE-JUNCAO: legenda automatica vem picada e sem pontuacao. As falas consecutivas sao
JUNTADAS ate formarem uma afirmacao COMPLETA e autocontida. Em TODOS os videos de TODOS
os canais. Cada PONTO = afirmacao real (video, canal, timestamp real quando disponivel).
Cada LINHA = cruzamento estatistico real entre duas afirmacoes (cosseno TF-IDF).
"""
import os
import re
import json
import glob
import time
import numpy as np
from collections import Counter

SRC = os.environ.get("NG_SRC", "transcripts")
TSDIR = os.environ.get("NG_TS", "transcripts_ts")
OUT = os.environ.get("NG_OUT", "NEURAL_GRAPH.json")
MAXR = int(os.environ.get("NG_RECS", "1000"))
V = int(os.environ.get("NG_V", "4000"))
CAND = int(os.environ.get("NG_CAND", "3000"))
NODES = int(os.environ.get("NG_NODES", "800"))
EDGES = int(os.environ.get("NG_EDGES", "6000"))

MINW = 9
MAXW = 32
MINC = 5

STOP = set(("a o e de da do das dos que em um uma para com nao os as no na por mais como mas ao se ou ja "
            "isso esse essa este esta muito voce tem ser sao foi vai pode entao aqui tudo todo toda bem "
            "ainda pra pro sobre quando onde qual quais eu meu minha nos eles elas ele ela cara gente coisa "
            "fazer faz feito ter tinha seu sua the of and to in is it you that this for on with are be as at "
            "your we can will have has from they our my me just about what which who them there their more "
            "than then would could should music applause").split())

DANGLE = set(("e ou mas que porque pois se de da do para com por em na no ao as os um uma the a an and or but "
              "that because if of to for with in on at is are was were be been as by from than then so which "
              "who when where while my your our their his her its this these those").split())

LIXO = re.compile(r"\[(music|musica|applause|aplausos|risos|laughter)[^\]]*\]", re.I)
TERM = re.compile(r"[a-zA-ZA-ÿ]{4,}")


def conteudo(fr):
    return [w for w in TERM.findall(fr.lower()) if w not in STOP]


def limpa_inicio(fr):
    """tira conectivo pendurado no comeco: 'and cheap to...' -> 'cheap to...'"""
    w = fr.split()
    while w and w[0].strip(".,;:").lower() in DANGLE:
        w.pop(0)
    return " ".join(w)


MAXB = 3          # ate 3 frases por bloco de ideia
MAXBW = 70        # ate ~70 palavras por bloco
COESAO = 0.12     # sobreposicao minima de termos p/ considerar continuacao da mesma ideia


def subagrupa(frases_video):
    """[(frase, start)] do MESMO video -> [(bloco_de_ideia, start_do_bloco)]

    Junta frases consecutivas que falam da mesma coisa (sobreposicao de termos de conteudo),
    formando uma ideia completa e autocontida. Frase isolada e um bloco de 1.
    """
    blocos = []
    cur = []
    curset = set()
    start = None
    for fr, st in frases_video:
        t = set(conteudo(fr))
        if not cur:
            cur, curset, start = [fr], set(t), st
            continue
        inter = len(curset & t)
        uni = len(curset | t) or 1
        jac = inter / uni
        palavras = sum(len(x.split()) for x in cur) + len(fr.split())
        if jac >= COESAO and len(cur) < MAXB and palavras <= MAXBW:
            cur.append(fr)
            curset |= t
        else:
            blocos.append((" ".join(cur), start))
            cur, curset, start = [fr], set(t), st
    if cur:
        blocos.append((" ".join(cur), start))
    return blocos


def coerentiza(unidades):
    """[(texto, start|None)] -> [(afirmacao_completa, start|None)]"""
    out = []
    buf = []
    start = None
    for txt, st in unidades:
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


def main():
    TS = {}
    for f in glob.glob(os.path.join(TSDIR, "**", "*.jsonl"), recursive=True):
        for ln in open(f, encoding="utf-8", errors="ignore"):
            if not ln.strip():
                continue
            try:
                r = json.loads(ln)
                TS[r["video_id"]] = r.get("segments") or []
            except Exception:
                pass

    frases = []
    nv = 0
    canais = set()
    for f in sorted(glob.glob(os.path.join(SRC, "**", "*.jsonl"), recursive=True)):
        canal = os.path.splitext(os.path.basename(f))[0]
        canais.add(canal)
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
            vid = r.get("video_id", "")
            segs = TS.get(vid)
            if segs:
                unid = [(s[1], float(s[0])) for s in segs if len(s) >= 2]
            else:
                txt = r.get("transcript") or r.get("text") or ""
                if isinstance(txt, list):
                    txt = " ".join(str(x) for x in txt)
                if len(txt) < 80:
                    continue
                unid = [(txt, None)]
            nv += 1
            fv = coerentiza(unid)
            for fr, st in subagrupa(fv):
                frases.append((fr, vid, canal, int(st) if st is not None else None))

    if not frases:
        json.dump({"nodes": [], "edges": [], "erro": "sem corpus"}, open(OUT, "w"))
        return

    df = Counter()
    toks_all = []
    for fr, _, _, _ in frases:
        t = set(conteudo(fr))
        toks_all.append(t)
        df.update(t)
    vocab = [w for w, _ in df.most_common(V) if df[w] >= 3]
    idx = {w: i for i, w in enumerate(vocab)}
    N = float(len(frases))
    IDF = np.array([np.log(N / (1.0 + df[w])) for w in vocab], dtype=np.float32)

    score = np.zeros(len(frases), dtype=np.float32)
    for i, t in enumerate(toks_all):
        sc = 0.0
        for w in t:
            j = idx.get(w)
            if j is not None:
                sc += float(IDF[j])
        score[i] = sc / (1.0 + 0.02 * len(t))

    ordem = np.argsort(-score)
    porc = Counter()
    cand = []
    lim = max(3, CAND // max(1, len(canais)) + 3)
    for i in ordem:
        c = frases[i][2]
        if porc[c] >= lim:
            continue
        porc[c] += 1
        cand.append(int(i))
        if len(cand) >= CAND:
            break

    X = np.zeros((len(cand), len(vocab)), dtype=np.float32)
    for r, i in enumerate(cand):
        for w in toks_all[i]:
            j = idx.get(w)
            if j is not None:
                X[r, j] = IDF[j]
    X = X / (np.linalg.norm(X, axis=1, keepdims=True) + 1e-9)
    SIM = X @ X.T
    np.fill_diagonal(SIM, -1)
    pares_frases = len(cand) * (len(cand) - 1) // 2
    pares_termos = len(vocab) * (len(vocab) - 1) // 2

    iu = np.triu_indices(len(cand), 1)
    vals = SIM[iu]
    mask = np.where(vals > 0.08)[0]
    top = mask[np.argsort(-vals[mask])][:EDGES]
    raw = [(int(iu[0][t]), int(iu[1][t]), float(vals[t])) for t in top]

    usados = {}
    ordem_nos = []
    for a, b, _ in raw:
        for x in (a, b):
            if x not in usados:
                usados[x] = len(ordem_nos)
                ordem_nos.append(x)
        if len(ordem_nos) >= NODES:
            break

    nodes = []
    for k, r in enumerate(ordem_nos):
        i = cand[r]
        fr, vid, canal, st = frases[i]
        link = ""
        if vid:
            link = "https://youtu.be/" + vid + ("?t=%d" % st if st is not None else "")
        nodes.append({"id": k, "frase": fr, "video": vid, "canal": canal, "t": st,
                      "link": link, "peso": round(float(score[i]), 2)})
    edges = [[usados[a], usados[b], round(w, 3)] for a, b, w in raw if a in usados and b in usados]

    com_ts = sum(1 for x in frases if x[3] is not None)
    out = {"ts": time.strftime("%FT%TZ", time.gmtime()),
           "videos": nv, "canais": len(canais),
           "frases_reais": len(frases),
           "frases_com_timestamp": com_ts,
           "frases_cruzadas": len(cand),
           "pares_frases_avaliados": pares_frases,
           "pares_termos_avaliados": pares_termos,
           "vocab": len(vocab),
           "pre_juncao": {"min_palavras": MINW, "max_palavras": MAXW, "min_conteudo": MINC},
           "subagrupamento": {"max_frases_por_bloco": MAXB, "max_palavras": MAXBW, "coesao_min": COESAO},
           "nodes": nodes, "edges": edges}
    json.dump(out, open(OUT, "w", encoding="utf-8"), ensure_ascii=False)
    print("GRAFO: %d blocos de ideia (pre-juncao + subagrupamento por video) de %d videos / %d canais | %d cruzadas (%d pares) "
          "| %d pontos, %d sinapses | %d com timestamp real"
          % (len(frases), nv, len(canais), len(cand), pares_frases, len(nodes), len(edges), com_ts))


if __name__ == "__main__":
    main()
