"""mine_channel.py — minera transcricoes -> IDEIAS de negocio (GitHub 16GB, Gemini gratis).
Le transcripts/*.jsonl, por canal extrai modelo/taticas/produtos/ideias. Anexa em ideas_mined.jsonl.
RE-MINERA canais que ganharam videos novos (compara contagem). stdlib + urllib.
"""
import os, json, glob, urllib.request, urllib.error

OUT = "ideas_mined.jsonl"

def _llm(prompt, max_tokens=1600):
    g = os.environ.get("GEMINI_API_KEY")
    if g:
        try:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={g}"
            body = {"contents": [{"parts": [{"text": prompt}]}], "generationConfig": {"maxOutputTokens": max_tokens, "temperature": 0.5}}
            r = urllib.request.Request(url, data=json.dumps(body).encode(), headers={"content-type": "application/json"})
            d = json.loads(urllib.request.urlopen(r, timeout=120).read().decode())
            return "".join(p.get("text", "") for p in d["candidates"][0]["content"]["parts"])
        except Exception:
            pass
    gk = os.environ.get("GROQ_API_KEY")
    if gk:
        try:
            r = urllib.request.Request("https://api.groq.com/openai/v1/chat/completions",
                data=json.dumps({"model": "llama-3.3-70b-versatile", "messages": [{"role": "user", "content": prompt[:24000]}], "max_tokens": max_tokens}).encode(),
                headers={"Authorization": "Bearer " + gk, "content-type": "application/json"})
            return json.loads(urllib.request.urlopen(r, timeout=100).read().decode())["choices"][0]["message"]["content"]
        except Exception:
            pass
    nv = os.environ.get("NVIDIA_API_KEY")
    if nv:
        try:
            r = urllib.request.Request("https://integrate.api.nvidia.com/v1/chat/completions",
                data=json.dumps({"model": "meta/llama-3.1-70b-instruct", "messages": [{"role": "user", "content": prompt[:20000]}], "max_tokens": max_tokens}).encode(),
                headers={"Authorization": "Bearer " + nv, "content-type": "application/json"})
            return json.loads(urllib.request.urlopen(r, timeout=100).read().decode())["choices"][0]["message"]["content"]
        except Exception:
            pass
    return None

def _corpus(path, cap=700000):
    parts = []
    for line in open(path, encoding="utf-8", errors="replace"):
        try:
            j = json.loads(line)
            t = j.get("text") or j.get("transcript") or j.get("content") or ""
            vid = j.get("video_id") or j.get("id") or ""
            if t:
                parts.append(f"[{vid}] {t}")
        except Exception:
            pass
        if sum(len(x) for x in parts) > cap:
            break
    return "\n".join(parts)[:cap], len(parts)

PROMPT = """Voce e analista de modelos de negocio digitais. A partir destas transcricoes do canal
"{canal}" ({nv} videos), extraia SO do que esta nas transcricoes (cite [video_id]):
- o MODELO DE NEGOCIO do criador,
- TATICAS acionaveis,
- PRODUTOS / AFILIADOS / ferramentas citados,
- 3 IDEIAS de receita cruzando com os ativos do dono (psicologia @psidanicoelho, 5 canais noise,
  afiliados ClickBank tafita1981 / Amazon globalsup-20 / Awin, loja Global Supplements /products/).
So fatos reais. Responda SO JSON:
{{"canal":"{canal}","modelo":"","taticas":[],"produtos_afiliados":[],"ideias":[]}}

TRANSCRICOES:
{corpus}"""

def _done_counts():
    """canal -> maior contagem de videos ja minerada (para re-minerar quando cresce)."""
    d = {}
    if os.path.exists(OUT):
        for l in open(OUT, encoding="utf-8", errors="replace"):
            try:
                r = json.loads(l); c = r.get("canal")
                if c: d[c] = max(d.get(c, 0), int(r.get("videos", 0) or 0))
            except Exception:
                pass
    return d

import ai_providers
def _llm(prompt, max_tokens=1600):
    return ai_providers.ask(prompt, max_tokens)


def main():
    limit = int(os.environ.get("MINE_COUNT", "100"))
    done = _done_counts()
    files = sorted(glob.glob("transcripts/*.jsonl"), key=lambda p: os.path.getsize(p), reverse=True)
    print(f"canais no disco: {len(files)} | ja minerados: {len(done)} | re-minera se ganhou video")
    n = 0
    for path in files:
        canal = os.path.basename(path)[:-6]
        corp, nv = _corpus(path)
        if nv == 0:
            continue
        if done.get(canal, -1) >= nv:
            continue  # ja minerado com essa contagem — nada novo
        out = _llm(PROMPT.format(canal=canal, nv=nv, corpus=corp))
        if out:
            o = out.strip()
            if o.startswith("```"):
                o = o.split("\n", 1)[-1].rsplit("```", 1)[0]
            a, b = o.find("{"), o.rfind("}")
            try:
                rec = json.loads(o[a:b + 1]); rec["videos"] = nv
            except Exception:
                rec = {"canal": canal, "videos": nv, "raw": out[:2000]}
        else:
            rec = {"canal": canal, "videos": nv, "raw": None, "erro": "LLM sem retorno"}
        with open(OUT, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        tag = "RE-minerado" if canal in done else "minerado"
        print(f"{tag}: {canal} ({nv} videos)")
        n += 1
        if n >= limit:
            break
    print("TOTAL_MINERADO_ESTE_RUN =", n)

if __name__ == "__main__":
    main()
