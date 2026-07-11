#!/usr/bin/env python3
"""scrape_missing.py - BAIXA AUTOMATICAMENTE tudo que falta, priorizando o que mais importa.

Le COBERTURA.json (produzido pelo channel_watch) e baixa a transcricao dos videos FALTANTES
via yt-dlp (legenda VTT) -> ja grava JUNTO o texto corrido E os segmentos com TIMESTAMP REAL.
Assim, todo video novo ja entra completo no cerebro (frase + tempo + link).

Prioridade (auto-otimizacao): canais com maior lucro estimado primeiro, depois os de menor
cobertura -> o cerebro gasta o tempo escasso onde ha mais dinheiro/conhecimento a ganhar.

Escreve: transcripts/<canal>.jsonl  (texto)  e  transcripts_ts/<canal>.jsonl  (segmentos)
"""
import os, json, glob, subprocess, time, re, tempfile, shutil

SRC = os.environ.get("NG_SRC", "transcripts")
TSDIR = os.environ.get("NG_TS", "transcripts_ts")
COV = os.environ.get("COV_OUT", "COBERTURA.json")
BATCH = int(os.environ.get("SCRAPE_BATCH", "120"))

os.makedirs(SRC, exist_ok=True)
os.makedirs(TSDIR, exist_ok=True)

if not os.path.exists(COV):
    print("SCRAPE: sem COBERTURA.json (rode channel_watch antes)")
    raise SystemExit
cov = json.load(open(COV, encoding="utf-8"))["canais"]

# lucro por categoria (auto-otimizacao) + categoria de cada canal
lucro = {}
cat = {}
try:
    pm = json.load(open("PROFIT_MODEL.json", encoding="utf-8"))
    lucro = pm.get("por_categoria", pm) or {}
except Exception:
    pass
try:
    cat = json.load(open("AETHER_CANAIS_CATEGORIAS.json", encoding="utf-8"))
except Exception:
    pass

def valor(canal):
    c = cat.get(canal) if isinstance(cat.get(canal), str) else (cat.get(canal, {}) or {}).get("categoria", "")
    v = lucro.get(c, 0)
    if isinstance(v, dict):
        v = v.get("lucro_1k", 0)
    falta = cov[canal].get("n_faltando", 0)
    return (float(v or 0) * 10) + min(falta, 50)   # lucro pesa mais; falta desempata

alvos = [c for c in cov if cov[c].get("faltando")]
alvos.sort(key=valor, reverse=True)

TS = re.compile(r"(\d\d):(\d\d):(\d\d)\.(\d\d\d)\s+-->")

def parse_vtt(path):
    segs, cur, visto = [], None, set()
    for ln in open(path, encoding="utf-8", errors="ignore"):
        ln = ln.rstrip("\n")
        m = TS.search(ln)
        if m:
            h, mi, s, ms = m.groups()
            cur = int(h) * 3600 + int(mi) * 60 + int(s) + int(ms) / 1000.0
            continue
        if cur is None or not ln.strip():
            continue
        t = re.sub(r"<[^>]+>", "", ln).strip()
        if not t or t.startswith(("WEBVTT", "Kind:", "Language:")) or t in visto:
            continue
        visto.add(t)
        segs.append([round(cur, 1), t])
    return segs

tmp = tempfile.mkdtemp()
feitos = err = 0
por_canal_txt, por_canal_ts = {}, {}
for canal in alvos:
    if feitos >= BATCH:
        break
    for vid in cov[canal]["faltando"]:
        if feitos >= BATCH:
            break
        try:
            out = os.path.join(tmp, vid)
            subprocess.run(["yt-dlp", "--quiet", "--no-warnings", "--skip-download",
                            "--write-auto-sub", "--write-sub", "--sub-lang", "pt,pt-BR,en,es",
                            "--sub-format", "vtt", "--socket-timeout", "20",
                            "-o", out + ".%(ext)s",
                            "https://www.youtube.com/watch?v=" + vid],
                           timeout=70, capture_output=True)
            vtts = glob.glob(out + "*.vtt")
            if not vtts:
                err += 1
                continue
            segs = parse_vtt(vtts[0])
            for v in vtts:
                try:
                    os.remove(v)
                except Exception:
                    pass
            if not segs:
                err += 1
                continue
            texto = " ".join(s[1] for s in segs)
            agora = time.strftime("%FT%TZ", time.gmtime())
            por_canal_txt.setdefault(canal, []).append(
                {"video_id": vid, "handle": canal, "chars": len(texto),
                 "transcript": texto, "ts": agora})
            por_canal_ts.setdefault(canal, []).append(
                {"video_id": vid, "segments": segs, "ts": agora})
            feitos += 1
        except Exception:
            err += 1
shutil.rmtree(tmp, ignore_errors=True)

for canal, rows in por_canal_txt.items():
    with open(os.path.join(SRC, canal + ".jsonl"), "a", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
for canal, rows in por_canal_ts.items():
    with open(os.path.join(TSDIR, canal + ".jsonl"), "a", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")

print("SCRAPE AUTO: +%d videos NOVOS transcritos JA COM TIMESTAMP (%d falharam) em %d canais | fila restante: %d"
      % (feitos, err, len(por_canal_txt),
         sum(c.get("n_faltando", 0) for c in cov.values()) - feitos))
