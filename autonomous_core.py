#!/usr/bin/env python3
"""autonomous_core.py — CEREBRO AUTONOMO DE VERDADE. Roda em loop, OFFLINE, sem depender de
API/IA-gratis/GitHub para PENSAR. A cada ciclo encadeia os motores locais (leitura em massa +
cruzamento vetorizado + calculo de lucro + memoria acumulada), gera IDEIAS e ACOES concretas,
acumula tudo local, e SO usa GitHub/API para a acao pontual final QUANDO estiver liberado
(flush best-effort com backoff). Se nao houver conexao/token, continua pensando e enfileirando.
SEGURANCA: acoes so na marca (allowlist); nunca move dinheiro; nunca lida com credenciais."""
import os, json, time, subprocess, hashlib

HERE = os.path.dirname(os.path.abspath(__file__)) or "."
INTERVAL = int(os.environ.get("CORE_INTERVAL", "30"))
ENGINES = ["fast_interlink.py", "mass_ideas.py", "profit_engine.py", "brain_memory.py"]

def load(p, d):
    try: return json.load(open(os.path.join(HERE, p), encoding="utf-8"))
    except Exception: return d

def run_engine(s):
    try:
        subprocess.run(["python3", os.path.join(HERE, s)], cwd=HERE,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=300)
        return True
    except Exception:
        return False

def gen_actions(mass, brain, profit):
    """transforma as ideias cruzadas em ACOES concretas (conteudo na marca)."""
    acts = []
    nb = str(brain.get("next_best", "") or "")
    for it in (mass.get("top_ideias", []) or [])[:8]:
        combo = it.get("combo", ["", ""])
        aid = "idea_" + hashlib.md5(("".join(combo)).encode()).hexdigest()[:10]
        acts.append({"id": aid, "tipo": "publicar_short",
                     "ideia": it.get("ideia", ""),
                     "gancho": "%s + %s" % (combo[0], combo[1]),
                     "nicho": it.get("ancora_nicho", nb),
                     "lucro_1k": it.get("lucro_estimado_por_1000", 0),
                     "marca": True, "criado": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())})
    return acts

def flush_github(files):
    """best-effort: sobe estado + acoes num UNICO commit se houver token e conexao. Nunca trava."""
    try:
        import gh_safe
        gh_safe.commit_many(files, "cerebro autonomo: ideias+acoes offline (flush pontual)")
        return "flushed"
    except Exception as e:
        return "offline/aguardando (" + str(e)[:40] + ")"

def main():
    once = os.environ.get("CORE_ONCE") == "1"
    cyc = 0
    while True:
        cyc += 1
        for e in ENGINES:
            if os.path.exists(os.path.join(HERE, e)): run_engine(e)
        mass = load("MASS_IDEAS.json", {}); brain = load("BRAIN_MEMORY.json", {}); profit = load("PROFIT_MODEL.json", {})
        # acumula acoes (fila local, dedup)
        pend = load("PENDING_ACTIONS.json", {"queue": []})
        have = set(a.get("id") for a in pend.get("queue", []))
        new = [a for a in gen_actions(mass, brain, profit) if a["id"] not in have]
        pend["queue"] = (pend.get("queue", []) + new)[-500:]
        json.dump(pend, open(os.path.join(HERE, "PENDING_ACTIONS.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        state = {"cycle": cyc, "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                 "next_best": brain.get("next_best", ""), "pares_avaliados": mass.get("pares_avaliados", 0),
                 "registros": mass.get("registros", 0), "acoes_novas": len(new), "fila_acoes": len(pend["queue"]),
                 "top_ideias": ["%s+%s" % (tuple(i.get("combo", ["", ""]))[0], tuple(i.get("combo", ["", ""]))[1]) for i in mass.get("top_ideias", [])[:5]]}
        json.dump(state, open(os.path.join(HERE, "CORE_STATE.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        st = flush_github({"CORE_STATE.json": json.dumps(state, ensure_ascii=False, indent=1),
                           "PENDING_ACTIONS.json": json.dumps(pend, ensure_ascii=False, indent=1),
                           "MASS_IDEAS.md": open(os.path.join(HERE, "MASS_IDEAS.md")).read() if os.path.exists(os.path.join(HERE, "MASS_IDEAS.md")) else ""})
        print("[core %d] registros=%s pares=%s acoes_novas=%d fila=%d | github=%s | top: %s"
              % (cyc, state["registros"], f'{state["pares_avaliados"]:,}', len(new), len(pend["queue"]), st,
                 ", ".join(state["top_ideias"][:3])), flush=True)
        if once: break
        time.sleep(INTERVAL)

if __name__ == "__main__":
    main()
