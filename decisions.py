#!/usr/bin/env python3
"""decisions.py - transforma OPORTUNIDADES em DECISOES + grava na memoria eterna.

FILTRO DE QUALIDADE (novo): so vira decisao o que tem substancia.
Rejeita:
  - gancho feito de stopwords ("aqui + gente")
  - nicho generico ("outros", vazio)
  - acao sem frase-fonte nem prova (link de video)
Prioriza as oportunidades do synapse_engine (figuras neurais com prova real).
"""
import json, time, os, re

STOP = set(("aqui gente video videos coisa fazer faz bem tudo agora hoje pessoal cara galera "
            "muito mais menos ser ter estar isso esse essa esta este outro outra outros outras "
            "the and for you this that with your what how why when just very really thing things").split())

def L(f, d):
    try:
        return json.load(open(f, encoding="utf-8"))
    except Exception:
        return d

pend = L("PENDING_ACTIONS.json", {"queue": []})
mass = L("MASS_IDEAS.json", {})
syn  = L("SINAPSES.json", {})
prev = L("DECISIONS.json", {"decisoes": []})

n_cross = syn.get("espaco_pares_grafo") or mass.get("pares_avaliados", 0)

def qualidade(a):
    """retorna (ok, motivo)"""
    nicho = (a.get("nicho") or "").strip().lower()
    if nicho in ("", "outros", "geral", "-"):
        return False, "nicho generico"
    g = (a.get("gancho") or "")
    termos = [t.strip().lower() for t in re.split(r"[+×x,]", g) if t.strip()]
    if not termos:
        return False, "sem gancho"
    if all(t in STOP for t in termos):
        return False, "gancho e so palavra vazia (%s)" % g
    tem_fonte = bool(a.get("descricao_fonte")) or bool(a.get("provas"))
    if not tem_fonte and a.get("tipo") != "conteudo_oportunidade":
        return False, "sem frase-fonte nem prova"
    return True, ""

seen = {d["id"] for d in prev.get("decisoes", [])}
dec = prev.get("decisoes", [])
novas = rejeitadas = 0
mem = open("DECISIONS_ETERNAS.md", "a", encoding="utf-8")
fila_limpa = []

for a in pend.get("queue", []):
    ok, motivo = qualidade(a)
    if not ok:
        rejeitadas += 1
        continue                      # descarta o lixo da fila
    fila_limpa.append(a)
    aid = a.get("id")
    if not aid or aid in seen:
        continue
    g = a.get("gancho") or ""
    nicho = a.get("nicho", "")
    lucro = a.get("lucro_1k", 0)
    tipo = a.get("tipo", "publicar")
    fontes = a.get("descricao_fonte") or []
    provas = [p for p in (a.get("provas") or []) if p]
    origem = a.get("origem", "")
    desc = "%s: %s (%s)%s" % (tipo.replace("_", " "), g, nicho,
                              " — $%s/1k" % int(lucro or 0) if lucro else "")
    d = {"id": aid, "tipo": tipo, "descricao": desc, "gancho": g, "nicho": nicho,
         "lucro_1k": lucro, "ideias_cruzadas": a.get("ideias_cruzadas") or n_cross,
         "descricao_fonte": fontes[:3], "provas": provas[:3], "origem": origem,
         "ts": time.strftime("%FT%TZ", time.gmtime()), "memoria_escrita": False}
    mem.write("- [%s] %s | %s | cruzou %s combinacoes%s\n"
              % (d["ts"], desc, origem or "sinapse",
                 format(d["ideias_cruzadas"], ",d"),
                 " | provas: " + ", ".join(provas[:2]) if provas else ""))
    mem.flush()
    d["memoria_escrita"] = True
    dec.append(d)
    seen.add(aid)
    novas += 1
mem.close()

# a fila fica so com o que tem qualidade
pend["queue"] = fila_limpa
json.dump(pend, open("PENDING_ACTIONS.json", "w", encoding="utf-8"), ensure_ascii=False)

out = {"ts": time.strftime("%FT%TZ", time.gmtime()), "total_decisoes": len(dec),
       "novas": novas, "rejeitadas_por_qualidade": rejeitadas,
       "cruzamentos_por_decisao": n_cross, "decisoes": dec[-60:]}
json.dump(out, open("DECISIONS.json", "w", encoding="utf-8"), ensure_ascii=False)
print("DECISOES: %d validas (+%d novas) | %d REJEITADAS por qualidade (stopword/nicho generico/sem prova)"
      % (len(dec), novas, rejeitadas))
