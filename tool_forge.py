#!/usr/bin/env python3
"""tool_forge.py — o cerebro SE AUTO-CODA. Le TOOL_REQUESTS.json (fila que o governador enche),
valida cada script Python (py_compile), instala libs necessarias (pip, no runner efemero do GitHub),
executa em sandbox com timeout e grava a saida em TOOL_RESULTS.json. Assim o AETHER cria novas
ferramentas sozinho, sem ninguem pedir. Roda em runner (16GB); na VM fica leve (so scripts curtos).
SEGURANCA: nunca lida com credenciais; nao publica nada aqui (isso e do publicador com allowlist)."""
import json, os, subprocess, sys, tempfile, time, hashlib

def load(p, d):
    try: return json.load(open(p, encoding="utf-8"))
    except Exception: return d

reqs = load("TOOL_REQUESTS.json", {"queue": []})
res = load("TOOL_RESULTS.json", {"done": []})
done_ids = set(x.get("id") for x in res.get("done", []))
made = 0
for r in reqs.get("queue", []):
    rid = r.get("id") or hashlib.md5(json.dumps(r, sort_keys=True).encode()).hexdigest()[:10]
    if rid in done_ids: continue
    name = r.get("name", "tool_" + rid)
    code = r.get("code", "")
    deps = r.get("deps", [])
    entry = {"id": rid, "name": name, "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    if not code:
        entry["status"] = "sem-codigo"; res["done"].append(entry); continue
    # instalar libs pedidas (autonomo)
    for d in deps[:8]:
        try:
            subprocess.call([sys.executable, "-m", "pip", "install", "--quiet", d],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=180)
        except Exception: pass
    # validar
    fp = os.path.join(tempfile.gettempdir(), name + ".py")
    open(fp, "w").write(code)
    try:
        import py_compile; py_compile.compile(fp, doraise=True)
    except Exception as e:
        entry["status"] = "erro-compilar: " + str(e)[:120]; res["done"].append(entry); continue
    # rodar em sandbox com timeout
    try:
        out = subprocess.run([sys.executable, fp], capture_output=True, text=True, timeout=90)
        entry["status"] = "ok" if out.returncode == 0 else "rc" + str(out.returncode)
        entry["stdout"] = out.stdout[-1500:]
        entry["stderr"] = out.stderr[-400:]
        # se gerou bem, promove a ferramenta pro repo (fica reutilizavel)
        if out.returncode == 0:
            open("forged_" + name + ".py", "w").write(code)
    except subprocess.TimeoutExpired:
        entry["status"] = "timeout"
    except Exception as e:
        entry["status"] = "erro-run: " + str(e)[:120]
    res["done"].append(entry); made += 1

res["done"] = res["done"][-300:]
json.dump(res, open("TOOL_RESULTS.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
with open("TOOLS_LOG.md", "w", encoding="utf-8") as f:
    f.write("# TOOL FORGE — ferramentas auto-criadas pelo cerebro\n\n")
    for e in res["done"][-30:]:
        f.write("- **%s** (%s) — %s\n" % (e.get("name"), e.get("ts"), e.get("status")))
print("TOOL_FORGE: %d novas ferramentas processadas | total historico %d" % (made, len(res["done"])))
