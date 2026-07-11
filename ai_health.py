#!/usr/bin/env python3
"""ai_health.py - monitora em tempo real quais IAs GRATIS estao vivas/rapidas e ranqueia.
Escreve AETHER_AI_ORDER.txt (melhor ordem) + AI_HEALTH.json. O git_brain/ai_providers usa a melhor."""
import os,json,time,urllib.request
HOME=os.path.expanduser("~/aether")
def load_env():
    for f in [HOME+"/.env","/home/tafita1981novo/projetocode/.env"]:
        try:
            for ln in open(f):
                ln=ln.strip()
                if "=" in ln and not ln.startswith("#"):
                    k,v=ln.split("=",1); os.environ.setdefault(k.strip(),v.strip().strip('"').strip("'"))
        except Exception: pass
def probe(name):
    e=os.environ
    P={
     "pollinations":("https://text.pollinations.ai/openai",{"model":"openai","messages":[{"role":"user","content":"ok"}]},{}),
     "nvidia":("https://integrate.api.nvidia.com/v1/chat/completions",{"model":"meta/llama-3.1-70b-instruct","messages":[{"role":"user","content":"ok"}],"max_tokens":2},{"Authorization":"Bearer "+e.get("NVIDIA_API_KEY","")}),
     "groq":("https://api.groq.com/openai/v1/chat/completions",{"model":"llama-3.1-8b-instant","messages":[{"role":"user","content":"ok"}],"max_tokens":2},{"Authorization":"Bearer "+e.get("GROQ_API_KEY","")}),
    }
    if name not in P: return {"alive":False,"latency":99}
    url,body,hdr=P[name]; h={"Content-Type":"application/json"}; h.update({k:v for k,v in hdr.items() if v and "Bearer " not in (v[:7]+"x")*0 or v})
    t0=time.time()
    try:
        r=urllib.request.Request(url,data=json.dumps(body).encode(),headers=h)
        x=urllib.request.urlopen(r,timeout=12); d=x.read().decode()
        return {"alive":x.status==200 and len(d)>5,"latency":round(time.time()-t0,2)}
    except Exception as ex:
        return {"alive":False,"latency":99,"err":str(ex)[:30]}
def main():
    load_env()
    while True:
        health={n:probe(n) for n in ["pollinations","nvidia","groq"]}
        order=sorted([n for n,h in health.items() if h["alive"]],key=lambda n:health[n]["latency"])
        order += [n for n in ["gemini","hf","pollinations"] if n not in order]
        json.dump({"ts":time.strftime("%FT%TZ",time.gmtime()),"health":health,"best_order":order},open(HOME+"/AI_HEALTH.json","w"))
        open(HOME+"/AETHER_AI_ORDER.txt","w").write(",".join(order))
        time.sleep(45)
def once():
    load_env()
    import os,json,time
    health={n:probe(n) for n in ["pollinations","nvidia","groq"]}
    order=sorted([n for n,h in health.items() if h["alive"]],key=lambda n:health[n]["latency"]) + [n for n in ["gemini","hf","pollinations"] if n not in [k for k,h in health.items() if h["alive"]]]
    print(",".join(order))
if __name__=="__main__":
    import os
    (once() if os.environ.get("AI_ONCE") else main())
