#!/usr/bin/env python3
"""neural_graph.py - GRAFO NEURAL REAL, FRASE-A-FRASE, COM PRE-JUNCAO (RAM 16GB do GitHub).

PRE-JUNCAO: legenda automatica vem picada e sem pontuacao. Antes de virar ponto do grafo,
as falas consecutivas sao JUNTADAS ate formarem uma afirmacao COMPLETA e autocontida
(minimo de palavras de conteudo, nao termina em conectivo solto, nao comeca pendurada).
Isso e aplicado em TODOS os videos de TODOS os canais.

Cada PONTO = uma afirmacao real (frase juntada) com video_id, canal e TIMESTAMP real
             (quando o corpus de segmentos ja tiver os tempos -> link youtu.be/ID?t=SEG).
Cada LINHA = cruzamento estatistico real entre duas afirmacoes (cosseno TF-IDF), vetorizado.

Le:  transcripts/*.jsonl     {video_id, handle, transcript}
     transcripts_ts/*.jsonl  {video_id, segments:[[start,texto],...]}   (timestamps reais)
Escreve: NEURAL_GRAPH.json
"""
import os, re, json, glob, time
import numpy as np
from collections import Counter

SRC   = os.environ.get("NG_SRC", "transcripts")
TSDIR = os.environ.get("NG_TS", "transcripts_ts")
OUT   = os.environ.get("NG_OUT", "NEURAL_GRAPH.json")
MAXR  = int(os.environ.get("NG_RECS", "1000"))    # videos por canal (cobre todos)
V     = int(os.environ.get("NG_V", "4000"))
CAND  = int(os.environ.get("NG_CAND", "3000"))
NODES = int(os.environ.get("NG_NODES", "800"))
EDGES = int(os.environ.get("NG_EDGES", "6000"))

MINW, MAXW, MINC = 9, 32, 5     # palavras min/max por afirmacao, min de palavras de conteudo

STOP = set(("a o e de da do das dos que em um uma para com nao os as no na por mais como mas ao se ou ja "
            "isso esse essa este esta muito voce tem ser sao foi vai pode entao aqui tudo todo toda bem "
            "ainda pra pro sobre quando onde qual quais eu meu minha nos eles elas ele ela cara gente coisa "
            "fazer faz feito ter tinha seu sua the of and to in is it you that this for on with are be as at "
            "your we can will have has from they our my me just about what which who them there their more "
            "than then would could should music applause").split())
# conectivos: se a frase TERMINA neles, ela esta pendurada -> junta com a proxima
DANGLE = set(("e ou mas que porque pois se de da do para com por em na no ao as os um uma the a an and or but "
              "that because if of to for with in on at is are was were be been as by from than then so which "
              "who when where while my your our their his her its this these those").split())
LIXO = re.compile(r"\[(music|musica|applause|aplausos|risos|laughter)[^\]]*\]", re.I)
WORD = re.compile(r"[a-zA-ZÀ-ÿ']+")
TERM = re.compile(r"[a-zA-ZÀ-ÿ]{4,}")


def coerentiza(unidades):
    """unidades: [(texto, start|None)] -> [(afirmacao_completa, start|None)]

    Junta falas consecutivas ate a afirmacao fazer sentido:
      - fecha em pontuacao final se ja tem >= MINW palavras
      - fecha ao atingir MAXW palavras, mas NAO fecha pendurada em conectivo
      - descarta o que nao tem MINC palavras de conteudo
    """
    out = []
    buf, start = [], None
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
            # 1) pontuacao final natural
            for i in range(MINW - 1, min(nw, MAXW)):
                if buf[i].endswith((".", "!", "?")):
                    corte = i + 1
                    break
            # 2) sem pontuacao: corta no limite, mas nunca pendurado num conectivo
            if corte is None and nw >= MAXW:
                corte = MAXW
                while corte > MINW and buf[corte - 1].strip(".,;:").lower() in DANGLE:
                    corte -= 1
            if corte is None:
                break
            fr = " ".join(buf[:corte]).strip(" ,;:-")
            buf = buf[corte:]
            cont = [w for w in TERM.findall(fr.lower()) if w not in STOP]
            if len(cont) >= MINC and len(fr) >= 45:
                out.append((fr, start))
            start = st if buf else None
    # resto
    if buf:
        fr = " ".join(buf).strip(" ,;:-")
        cont = [w for w in TERM.findall(fr.lower()) if w not in STOP]
        if len(cont) >= MINC and len(f