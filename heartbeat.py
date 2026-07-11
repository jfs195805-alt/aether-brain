"""heartbeat.py — pulso do cerebro (lado GitHub). Escreve HEARTBEAT.json a cada ciclo.
Permite ao espelho da VM verificar sincronizacao em tempo real."""
import json, time, os
def load(p, d):
    try: return json.load(open(p, encoding="utf-8"))
    except Exception: return d
h = load("HEARTBEAT.json", {"cycle": 0})
h["cycle"] = int(h.get("cycle", 0)) + 1
h["source"] = "github"
h["ts"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
bm = load("BRAIN_MEMORY.json", {})
h["next_best"] = bm.get("next_best", "")
h["brain_cycles"] = bm.get("cycles", 0)
json.dump(h, open("HEARTBEAT.json", "w"), ensure_ascii=False, indent=1)
print("HEARTBEAT: github ciclo %d next_best=%s" % (h["cycle"], h["next_best"]))
