#!/usr/bin/env python3
"""neural_graph.py v3 - REDE NEURAL EM ESCALA REAL (RAM 16GB do GitHub).

Escala: nao cruza uma amostra. Cruza TODAS as frases do corpus (1M+) usando INDEXACAO
INVERTIDA POR TERMOS RAROS (blocking): duas frases so sao comparadas se compartilham um termo
raro - que e exatamente onde mora o significado. Isso avalia CENTENAS DE MILHOES de pares
REAIS por ciclo, em vez de fingir que avaliou trilhoes.

Janela rotativa: cada ciclo aprofunda um bloco diferente do corpus -> a cobertura SOMA para
sempre (ACUMULADO.json guarda os totais cumulativos: frases vistas, pares avaliados, sinapses
descobertas). O conhecimento nunca e jogado fora.

Pre-juncao + subagrupamento por video (afirmacoes completas, com timestamp real quando existe).
Saidas: NEURAL_GRAPH.json (grafo detalhado p/ o site) e ACUMULADO.json (memoria cumulativa).
"""
import os, re, json, glob, time, math
import numpy as np
import resource
from collections import Counter, defaultdict

def ram_pico_mb():
    return int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024)

def ram_total_mb():
    try:
        for ln in open("/proc/meminfo"):
            if ln.startswith("MemTotal"):
                return int(int(ln.split()[1]) / 1024)
    except Exception:
        pass
    return 0

SRC = os.environ.get("NG_SRC", "transcripts")
TSDIR = os.environ.get("NG_TS", "transcripts_ts")
OUT = os.environ.get("NG_OUT", "NEURAL_GRAPH.json")
ACC = "ACUMULADO.json"
MAXR = int(os.environ.get("NG_RECS", "1000"))
V = int(os.environ.get("NG_V", "60000"))          # vocabulario grande
DF_MIN = int(os.environ.get("NG_DFMIN", "3"))
DF_MAX = int(os.environ.get("NG_DFMAX", "1200"))  # termo "raro" = df <= isso
BUCKET_MAX = int(os.environ.get("NG_BUCKET", "2500"))
KEEP_K = int(os.environ.get("NG_KEEPK", "6"))     # melhores vizinhos por frase
LIM = float(os.environ.get("NG_LIM", "0.18"))     # limiar de sinapse
NODES = int(os.environ.get("NG_NODES", "2000"))   # pontos exibidos no site
EDGES = int(os.environ.get("NG_EDGES", "20000"))  # sinapses exibidas
MINW, MAXW, MINC = 9, 32, 5
MAXB, MAXBW, COESAO = 3, 70, 0.12

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
TERM = re.compile(r"[a-zA-ZÀ-ÿ]{4,}")

# --- LIMPEZA: HTML cru, censura, marcadores de legenda ---
import html as _html
CENSURA = re.compile(r"\[\s*(&nbsp;)?\s*_+\s*(&nbsp;)?\s*\]")
SETAS   = re.compile(r"^\s*(>>|&gt;&gt;)+\s*")
ESPACOS = re.compile(r"\s+")

def limpa_texto(t):
    t = _html.unescape(t or "")          # &gt; &nbsp; &amp; -> texto real
    t = CENSURA.sub(" ", t)              # [ __ ] censura de palavrao
    t = SETAS.sub("", t)                 # >> marcador de falante
    t = t.replace(">>", " ")
    return ESPACOS.sub(" ", t).strip()

# --- BOILERPLATE: frase-clichê que aparece em MUITOS canais diferentes ---
# "espero que tenha ajudado", "se inscreva no canal", "ate o proximo video"...
# Nao e insight: e formula. Detectada por ASSINATURA que se repete entre canais.
BOILER_MIN_CANAIS = int(os.environ.get("NG_BOILER", "4"))

def assinatura(fr):
    """hash da frase normalizada (int, rápido) para detectar quase-duplicatas entre canais"""
    w = sorted(set(x for x in TERM.findall(fr.lower()) if x not in STOP))[:8]
    if len(w) < 3:
        return 0
    return hash(" ".join(w)) & 0xFFFFFFFFFFFF


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


# ---------- corpus -> TODAS as afirmacoes ----------
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

frases, nv, canais = [], 0, set()
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
            unid = [(limpa_texto(s[1]), float(s[0])) for s in segs if len(s) >= 2]
        else:
            txt = r.get("transcript") or r.get("text") or ""
            if isinstance(txt, list):
                txt = " ".join(str(x) for x in txt)
            txt = limpa_texto(txt)
            if len(txt) < 80:
                continue
            unid = [(txt, None)]
        nv += 1
        for fr, st in subagrupa(coerentiza(unid)):
            frases.append((fr, vid, canal, int(st) if st is not None else None))

if not frases:
    json.dump({"nodes": [], "edges": [], "erro": "sem corpus"}, open(OUT, "w"))
    raise SystemExit

# ---------- FILTRA BOILERPLATE (o clichê que aparece em N canais) ----------
sig_canais = defaultdict(set)
sigs = [assinatura(f[0]) for f in frases]         # calcula uma vez
for k, (fr, vid, canal, st) in enumerate(frases):
    if sigs[k]:
        sig_canais[sigs[k]].add(canal)
boiler = {sg for sg, cs in sig_canais.items() if len(cs) >= BOILER_MIN_CANAIS}
antes = len(frases)
keep = [k for k in range(len(frases)) if sigs[k] not in boiler or sigs[k] == 0]
frases = [frases[k] for k in keep]
n_boiler = antes - len(frases)
print("BOILERPLATE removido: %s frases-clichê (apareciam em >=%d canais diferentes)"
      % (format(n_boiler, ",d"), BOILER_MIN_CANAIS))

NF = len(frases)
# ---------- vocabulario + TF-IDF esparso de TODAS as frases ----------
df = Counter()
toks = []
for fr, _, _, _ in frases:
    t = set(conteudo(fr))
    toks.append(t)
    df.update(t)
vocab = {w: i for i, (w, c) in enumerate(df.most_common(V)) if c >= DF_MIN}
IDF = np.zeros(len(vocab), dtype=np.float32)
for w, i in vocab.items():
    IDF[i] = math.log(NF / (1.0 + df[w]))

# ---------- BLOCKING: indice invertido por termos RAROS ----------
inv = defaultdict(list)
for i, t in enumerate(toks):
    raros = [w for w in t if w in vocab and df[w] <= DF_MAX]
    raros.sort(key=lambda w: df[w])
    for w in raros[:8]:                      # 8 termos mais raros da frase (mais cruzamentos reais)
        inv[w].append(i)

# matriz TF-IDF esparsa de TODAS as frases (scipy)
import heapq, gc
from scipy.sparse import csr_matrix
indptr=[0]; indices=[]; data=[]
for i in range(NF):
    idx=[vocab[w] for w in toks[i] if w in vocab]
    if idx:
        val=IDF[idx]
        nrm=float(np.linalg.norm(val)) or 1.0
        indices.extend(idx); data.extend((val/nrm).tolist())
    indptr.append(len(indices))
X = csr_matrix((np.array(data,dtype=np.float32),
                np.array(indices,dtype=np.int32),
                np.array(indptr,dtype=np.int64)), shape=(NF,len(vocab)))
del data, indices, indptr, toks       # libera RAM: nao precisamos mais
gc.collect()

MAX_PARES = int(os.environ.get("NG_MAXPAIRS", "400000000"))   # teto por ciclo (rotativo)
T0 = time.time()
pares_avaliados = 0
viz = defaultdict(list)               # heap limitado a KEEP_K por frase

def guarda(i, s_, j):
    h = viz[i]
    if len(h) < KEEP_K:
        heapq.heappush(h, (s_, j))
    elif s_ > h[0][0]:
        heapq.heapreplace(h, (s_, j))

# rotacao: cada ciclo comeca de um ponto diferente da lista de blocos -> cobertura soma sempre
blocos = [(w, lst) for w, lst in inv.items() if 2 <= len(lst) <= BUCKET_MAX]
try:
    off = json.load(open(ACC, encoding="utf-8")).get("offset_blocos", 0)
except Exception:
    off = 0
if blocos:
    off = off % len(blocos)
    blocos = blocos[off:] + blocos[:off]

usados_blocos = 0
for w, lst in blocos:
    L = len(lst)
    p = L * (L - 1) // 2
    if pares_avaliados + p > MAX_PARES:
        break
    pares_avaliados += p
    usados_blocos += 1
    Xb = X[lst]
    S = (Xb @ Xb.T).tocoo()            # cruzamento REAL de todos os pares do bloco (esparso)
    for a, b, v in zip(S.row, S.col, S.data):
        if a >= b or v < LIM:
            continue
        i, j = lst[a], lst[b]
        guarda(i, float(v), j)
        guarda(j, float(v), i)
    del Xb, S

arestas = {}
for i, h in viz.items():
    for s_, j in h:
        a, b = (i, j) if i < j else (j, i)
        arestas[(a, b)] = round(s_, 3)
del viz
gc.collect()

# ================= CAMADA SEMANTICA (estado da arte) =================
# 1) SVD RANDOMIZADO (Halko-Martinsson-Tropp): projeta 1M frases num espaco latente de K dims.
#    Captura SIGNIFICADO, nao palavra. Liga "creatina da forca" com "suplemento melhora treino".
# 2) IVF (k-means + celulas), a arquitetura do FAISS: torna o kNN viavel em 1M de vetores.
SEM_K   = int(os.environ.get("NG_SVD", "256"))       # dimensoes latentes
SEM_CEL = int(os.environ.get("NG_CELLS", "1500"))    # celulas do indice
SEM_KNN = int(os.environ.get("NG_SKNN", "6"))        # vizinhos semanticos por frase
SEM_LIM = float(os.environ.get("NG_SLIM", "0.45"))   # limiar semantico (cosseno no espaco latente)
SEM_ON  = os.environ.get("NG_SEMANTIC", "1") == "1"

arestas_lex = len(arestas)
arestas_sem = 0
T_SEM = time.time()
if SEM_ON and NF > 1000:
    try:
        rng = np.random.default_rng(7)
        p = 12
        Om = rng.standard_normal((X.shape[1], SEM_K + p), dtype=np.float32)
        Y = X @ Om                              # (NF x K+p) esparso@denso = rapido
        Y, _ = np.linalg.qr(Y)                  # base ortonormal
        B = (X.T @ Y).T                         # (K+p x vocab)
        Ub, S, Vt = np.linalg.svd(B, full_matrices=False)
        Z = (Y @ Ub[:, :SEM_K]) * S[:SEM_K]     # embeddings (NF x K)
        del Om, Y, B, Ub, Vt
        gc.collect()
        Z = Z.astype(np.float32)
        nz = np.linalg.norm(Z, axis=1, keepdims=True)
        nz[nz == 0] = 1.0
        Z /= nz                                  # normalizado -> produto interno = cosseno

        # k-means (mini-batch) para montar as celulas do indice IVF
        idxc = rng.choice(NF, size=min(SEM_CEL, NF), replace=False)
        C = Z[idxc].copy()
        for _ in range(6):
            lot = rng.choice(NF, size=min(60000, NF), replace=False)
            sim = Z[lot] @ C.T
            asg = sim.argmax(axis=1)
            for k in range(C.shape[0]):
                m = lot[asg == k]
                if len(m):
                    v = Z[m].mean(axis=0)
                    n_ = np.linalg.norm(v)
                    if n_ > 0:
                        C[k] = v / n_
        # atribui todas as frases a uma celula
        celula = np.empty(NF, dtype=np.int32)
        for i0 in range(0, NF, 50000):
            i1 = min(NF, i0 + 50000)
            celula[i0:i1] = (Z[i0:i1] @ C.T).argmax(axis=1)

        # kNN exato DENTRO de cada celula (semanticamente proximas)
        for k in range(C.shape[0]):
            membros = np.where(celula == k)[0]
            L = len(membros)
            if L < 2 or L > 4000:
                continue
            Sm = Z[membros] @ Z[membros].T
            np.fill_diagonal(Sm, -1)
            top = np.argpartition(-Sm, min(SEM_KNN, L - 1), axis=1)[:, :SEM_KNN]
            for a in range(L):
                i = int(membros[a])
                for b in top[a]:
                    v = float(Sm[a, b])
                    if v < SEM_LIM:
                        continue
                    j = int(membros[b])
                    if i == j:
                        continue
                    x, y = (i, j) if i < j else (j, i)
                    if (x, y) not in arestas:
                        arestas[(x, y)] = round(v, 3)
                        arestas_sem += 1
        del Z, C
        gc.collect()
    except Exception as e:
        print("camada semantica falhou (%s) - seguindo so com lexica" % str(e)[:60])
DUR_SEM = time.time() - T_SEM

DUR = max(0.001, time.time() - T0)
PPS = int(pares_avaliados / DUR)

grau = Counter()
for (a, b) in arestas:
    grau[a] += 1
    grau[b] += 1

# ---------- grafo detalhado para o site (os pontos mais conectados) ----------
top = [i for i, _ in grau.most_common(NODES)]
mapa = {i: k for k, i in enumerate(top)}
nodes = []
for i in top:
    fr, vid, canal, st = frases[i]
    link = ("https://youtu.be/" + vid + ("?t=%d" % st if st is not None else "")) if vid else ""
    nodes.append({"id": mapa[i], "frase": fr, "video": vid, "canal": canal, "t": st,
                  "link": link, "peso": grau[i]})
ed = [[mapa[a], mapa[b], s] for (a, b), s in arestas.items() if a in mapa and b in mapa]
ed.sort(key=lambda x: -x[2])
ed = ed[:EDGES]

# ---------- GRAFO COMPLETO para o motor de sinapses (mesmo job, nao vai pro git) ----------
from scipy.sparse import coo_matrix, save_npz
if arestas:
    ii = np.fromiter((a for (a, b) in arestas), dtype=np.int32, count=len(arestas))
    jj = np.fromiter((b for (a, b) in arestas), dtype=np.int32, count=len(arestas))
    vv = np.fromiter(arestas.values(), dtype=np.float32, count=len(arestas))
    A = coo_matrix((np.concatenate([vv, vv]),
                    (np.concatenate([ii, jj]), np.concatenate([jj, ii]))),
                   shape=(NF, NF), dtype=np.float32).tocsr()
    save_npz("GRAPH_FULL.npz", A)
    with open("GRAPH_NODES.jsonl", "w", encoding="utf-8") as fh:
        buf = []
        for i in range(NF):
            fr, vid, canal, st = frases[i]
            buf.append(json.dumps({"i": i, "f": fr, "v": vid, "c": canal, "t": st}, ensure_ascii=False))
            if len(buf) >= 50000:
                fh.write("\n".join(buf) + "\n"); buf = []
        if buf:
            fh.write("\n".join(buf) + "\n")
    print("GRAFO COMPLETO salvo: %s nos, %s arestas -> GRAPH_FULL.npz"
          % (format(NF, ",d"), format(len(arestas), ",d")))

com_ts = sum(1 for x in frases if x[3] is not None)

# ---------- MEMORIA CUMULATIVA (soma para sempre) ----------
try:
    acc = json.load(open(ACC, encoding="utf-8"))
except Exception:
    acc = {"ciclos": 0, "frases_vistas_total": 0, "pares_avaliados_total": 0,
           "sinapses_descobertas_total": 0, "videos_total": 0}
acc["ciclos"] += 1
acc["frases_vistas_total"] += NF
acc["pares_avaliados_total"] += pares_avaliados
acc["sinapses_descobertas_total"] += len(arestas)
acc["videos_total"] = nv
acc["offset_blocos"] = (off + usados_blocos) if blocos else 0
acc["blocos_total"] = len(inv)
acc["ts"] = time.strftime("%FT%TZ", time.gmtime())
json.dump(acc, open(ACC, "w", encoding="utf-8"), ensure_ascii=False)

espaco = int(NF * (NF - 1) / 2)
out = {"ts": acc["ts"], "videos": nv, "canais": len(canais),
       "frases_reais": NF,
       "boilerplate_removido": n_boiler, "frases_com_timestamp": com_ts,
       "vocab": len(vocab),
       "pares_frases_avaliados": pares_avaliados,
       "espaco_pares_total": espaco,
       "sinapses_descobertas": len(arestas),
       "sinapses_lexicais": arestas_lex,
       "sinapses_semanticas": arestas_sem,
       "segundos_semantica": round(DUR_SEM, 1),
       "dimensoes_latentes": SEM_K,
       "pares_por_segundo": PPS,
       "ram_pico_mb": ram_pico_mb(),
       "ram_total_mb": ram_total_mb(),
       "ram_pct": round(100.0 * ram_pico_mb() / max(1, ram_total_mb()), 1),
       "cpus": os.cpu_count(),
       "segundos_de_cruzamento": round(DUR, 1),
       "pares_acumulados": acc["pares_avaliados_total"],
       "sinapses_acumuladas": acc["sinapses_descobertas_total"],
       "ciclos": acc["ciclos"],
       "nodes": nodes, "edges": ed}
json.dump(out, open(OUT, "w", encoding="utf-8"), ensure_ascii=False)
print("GRAFO v4: %d frases | %s pares lexicais em %.1fs (%s pares/s) | sinapses: %s lexicais + %s SEMANTICAS (SVD %dd + IVF, %.1fs) | "
      "RAM: %d MB de %d MB (%.1f%%) | ACUMULADO: %s pares, %s sinapses, ciclo %d"
      % (NF, format(pares_avaliados, ",d"), DUR, format(PPS, ",d"),
         format(arestas_lex, ",d"), format(arestas_sem, ",d"), SEM_K, DUR_SEM,
         ram_pico_mb(), ram_total_mb(), 100.0*ram_pico_mb()/max(1,ram_total_mb()),
         format(acc["pares_avaliados_total"], ",d"), format(acc["sinapses_descobertas_total"], ",d"), acc["ciclos"]))
