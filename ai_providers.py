# -*- coding: utf-8 -*-
"""ai_providers.py — camada de IA resiliente: testa TODAS as gratis, usa a MELHOR viva (best-first)
para analise, com fallback ciclico infinito. Reutilizavel em tudo. Nunca imprime a chave.
Ordem = qualidade/gratis-primeiro. DeepSeek/OpenRouter entram se houver chave.
"""
import os, json, time, urllib.request, urllib.error

PROVIDERS = [
 ("groq", "openai", "https://api.groq.com/openai/v1/chat/completions", "GROQ_API_KEY",
   ["llama-3.3-70b-versatile", "openai/gpt-oss-120b", "openai/gpt-oss-20b", "llama-3.1-8b-instant", "gemma2-9b-it"]),
 ("openrouter", "openai", "https://openrouter.ai/api/v1/chat/completions", "OPENROUTER_API_KEY",
   ["deepseek/deepseek-r1:free", "deepseek/deepseek-chat-v3.1:free", "qwen/qwen-2.5-72b-instruct:free", "meta-llama/llama-3.3-70b-instruct:free"]),
 ("deepseek", "openai", "https://api.deepseek.com/v1/chat/completions", "DEEPSEEK_API_KEY",
   ["deepseek-chat", "deepseek-reasoner"]),
 ("hf", "openai", "https://router.huggingface.co/v1/chat/completions", "HF_TOKEN",
   ["Qwen/Qwen2.5-72B-Instruct", "meta-llama/Llama-3.3-70B-Instruct", "Qwen/Qwen2.5-7B-Instruct", "meta-llama/Llama-3.1-8B-Instruct"]),
 ("nvidia", "openai", "https://integrate.api.nvidia.com/v1/chat/completions", "NVIDIA_API_KEY",
   ["nvidia/llama-3.1-nemotron-70b-instruct", "meta/llama-3.3-70b-instruct", "meta/llama-3.1-70b-instruct",
    "mistralai/mixtral-8x22b-instruct-v0.1", "meta/llama-3.1-8b-instruct"]),
 ("gemini", "gemini", "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent", "GEMINI_API_KEY",
   ["gemini-2.0-flash", "gemini-2.5-flash", "gemini-1.5-flash"]),
 ("openai", "openai", "https://api.openai.com/v1/chat/completions", "OPENAI_API_KEY",
   ["gpt-4o-mini"]),   # PAGO (barato) — so em ultimo caso
]
_ALIVE = None
_LAST = 0.0
_RETEST_S = int(os.environ.get("AI_RETEST_SECONDS", "120"))  # re-testa em tempo real

def _call(kind, url, key, model, prompt, max_tokens=300, timeout=25):
    if kind == "openai":
        r = urllib.request.Request(url, data=json.dumps({"model": model,
            "messages": [{"role": "user", "content": prompt}], "max_tokens": max_tokens,
            "temperature": 0.1}).encode(),
            headers={"Authorization": "Bearer " + key, "content-type": "application/json"})
        return json.loads(urllib.request.urlopen(r, timeout=timeout).read())["choices"][0]["message"]["content"]
    if kind == "gemini":
        u = url.format(model=model) + "?key=" + key
        r = urllib.request.Request(u, data=json.dumps({"contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"maxOutputTokens": max_tokens, "temperature": 0.1}}).encode(),
            headers={"content-type": "application/json"})
        d = json.loads(urllib.request.urlopen(r, timeout=timeout).read())
        return "".join(p.get("text", "") for p in d["candidates"][0]["content"]["parts"])
    return None

def test_all(verbose=True):
    alive = []
    if verbose: print("== TESTE DE IAs GRATIS (usar so as vivas, melhor primeiro) ==")
    for name, kind, url, env, models in PROVIDERS:
        key = os.environ.get(env)
        if not key:
            if verbose: print("  [%s] sem chave" % name)
            continue
        hit = None
        for m in models:
            try:
                t = _call(kind, url, key, m, "reply with the word OK", max_tokens=5, timeout=15)
                if t and t.strip():
                    hit = m; break
            except urllib.error.HTTPError as e:
                body = ""
                try: body = e.read().decode()[:80]
                except Exception: pass
                if verbose: print("  [%s] %s -> HTTP %s %s" % (name, m, e.code, body.replace(chr(10), " ")))
            except Exception as e:
                if verbose: print("  [%s] %s -> %s" % (name, m, str(e)[:60]))
        if hit:
            alive.append((name, kind, url, key, hit))
            if verbose: print("  [%s] VIVO  modelo=%s" % (name, hit))
    if verbose: print("VIVAS (melhor primeiro):", [(n, m) for n, _, _, _, m in alive] or "NENHUMA")
    return alive

def _ensure(force=False):
    global _ALIVE, _LAST
    if force or _ALIVE is None or (_RETEST_S and (time.time() - _LAST) > _RETEST_S):
        _ALIVE = test_all(verbose=(_ALIVE is None)); _LAST = time.time()
    return _ALIVE

def _pollinations_text(prompt, timeout=35):
    """IA de texto GRATIS e SEM CHAVE (last resort). POST openai-compat e GET."""
    import urllib.parse
    try:
        body = json.dumps({"model": "openai", "messages": [{"role": "user", "content": prompt[:6000]}]}).encode()
        req = urllib.request.Request("https://text.pollinations.ai/openai", data=body,
                                     headers={"Content-Type": "application/json", "User-Agent": "aether"})
        r = urllib.request.urlopen(req, timeout=timeout).read().decode("utf-8", "replace")
        try:
            return json.loads(r)["choices"][0]["message"]["content"]
        except Exception:
            return r
    except Exception:
        pass
    try:
        q = urllib.parse.quote(prompt[:1500])
        req = urllib.request.Request("https://text.pollinations.ai/" + q + "?model=openai", headers={"User-Agent": "aether"})
        return urllib.request.urlopen(req, timeout=timeout).read().decode("utf-8", "replace")
    except Exception:
        return None


def ask(prompt, max_tokens=300, max_cycles=3):
    for cycle in range(max_cycles):
        alive = _ensure(force=(cycle > 0))
        for name, kind, url, key, model in alive:      # best-first (qualidade)
            try:
                t = _call(kind, url, key, model, prompt, max_tokens=max_tokens, timeout=30)
                if t and t.strip():
                    return t
            except Exception:
                pass
        # nenhuma viva respondeu: varre a lista COMPLETA (ultimo recurso), depois re-testa
        for name, kind, url, env, models in PROVIDERS:
            key = os.environ.get(env)
            if not key: continue
            for m in models:
                try:
                    t = _call(kind, url, key, m, prompt, max_tokens=max_tokens, timeout=25)
                    if t and t.strip(): return t
                except Exception:
                    pass
        time.sleep(2)
    # ULTIMO recurso: IA de texto sem chave (Pollinations)
    try:
        t = _pollinations_text(prompt, timeout=40)
        if t and t.strip():
            print("[ai] fallback: Pollinations text (gratis, sem chave)")
            return t
    except Exception:
        pass
    return None

def alive_names():
    return [n for n, _, _, _, _ in _ensure()]

if __name__ == "__main__":
    test_all()
