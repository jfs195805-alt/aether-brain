#!/usr/bin/env python3
"""channel_watch.py - MONITORA PARA SEMPRE todos os canais e descobre o que falta.

Para cada canal do corpus, lista TODOS os videos do canal (yt-dlp --flat-playlist, sem baixar)
e compara com o que ja foi transcrito -> descobre exatamente os videos FALTANTES e os NOVOS.

Incremental: revisa WATCH_BATCH canais por rodada (rotativo), entao em poucas rodadas
todos os 592 canais sao revisados, e o ciclo recomeca -> monitoramento perpetuo.

Escreve: COBERTURA.json
  {canal: {total, transcritos, faltando: [ids], ultima_revisao}}  + resumo global
"""
import os, json, glob, subprocess, time

SRC = os.environ.get("NG_SRC", "transcripts")
OUT = os.environ.get("COV_OUT", "COBERTURA.json")
BATCH = int(os.environ.get("WATCH_BATCH", "60"))
MAXV = int(os.environ.get("WATCH_MAXV", "300"))   # ate 300 videos por canal listados

cov = {}
if os.path.exists(OUT):
    try:
        cov = json.load(open(OUT, encoding="utf-8")).get("canais", {})
    except Exception:
        cov = {}

# o que ja temos transcrito, por canal
tenho = {}
for f in sorted(glob.glob(os.path.join(SRC, "*.jsonl"))):
    canal = os.path.splitext(os.path.basename(f))[0]
    ids = set()
    for ln in open(f, encoding="utf-8", errors="ignore"):
        if not ln.strip():
            continue
        try:
            ids.add(json.loads(ln)["video_id"])
        except Exception:
            pass
    tenho[canal] = ids

# CANAIS NOVOS incluidos manualmente pelo site (NOVOS_CANAIS.json) entram na fila com prioridade
try:
    novos_manuais = json.load(open("NOVOS_CANAIS.json", encoding="utf-8")).get("canais", [])
except Exception:
    novos_manuais = []
for c in novos_manuais:
    if c not in tenho:
        tenho[c] = set()          # canal virgem: tudo dele esta "faltando"

# rotacao: canais novos primeiro, depois quem esta ha mais tempo sem revisao
canais = sorted(tenho.keys(), key=lambda c: (c not in novos_manuais or c in cov,
                                             cov.get(c, {}).get("ultima_revisao", "")))
alvo = canais[:BATCH]

novos_total = 0
for canal in alvo:
    try:
        r = subprocess.run(
            ["yt-dlp", "--flat-playlist", "--quiet", "--no-warnings",
             "--print", "%(id)s", "--playlist-end", str(MAXV),
             "https://www.youtube.com/@%s/videos" % canal],
            capture_output=True, text=True, timeout=90)
        ids = [x.strip() for x in r.stdout.splitlines() if x.strip()]
        if not ids:
            continue
        temos = tenho.get(canal, set())
        faltam = [v for v in ids if v not in temos]
        antes = set(cov.get(canal, {}).get("faltando", []))
        novos = [v for v in faltam if v not in antes]
        novos_total += len(novos)
        cov[canal] = {"total": len(ids), "transcritos": len(temos),
                      "faltando": faltam[:200], "n_faltando": len(faltam),
                      "novos_detectados": len(novos),
                      "ultima_revisao": time.strftime("%FT%TZ", time.gmtime())}
    except Exception:
        continue

tot = sum(v.get("total", 0) for v in cov.values())
tr = sum(v.get("transcritos", 0) for v in cov.values())
fal = sum(v.get("n_faltando", 0) for v in cov.values())
out = {"ts": time.strftime("%FT%TZ", time.gmtime()),
       "canais_monitorados": len(cov), "canais_revisados_agora": len(alvo),
       "videos_no_youtube": tot, "ja_transcritos": tr, "faltando": fal,
       "novos_detectados_agora": novos_total,
       "cobertura_pct": round(100.0 * tr / tot, 1) if tot else 0.0,
       "canais": cov}
json.dump(out, open(OUT, "w", encoding="utf-8"), ensure_ascii=False)
print("MONITOR: %d canais | %d videos no YouTube | %d transcritos | %d FALTANDO | +%d novos detectados | cobertura %.1f%%"
      % (len(cov), tot, tr, fal, novos_total, out["cobertura_pct"]))
