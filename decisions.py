#!/usr/bin/env python3
"""decisions.py - transforma acoes em DECISOES ricas p/ o site + GRAVA na memoria eterna.
Roda no diretorio do clone (le PENDING_ACTIONS/MASS_IDEAS/BRAIN_MEMORY, escreve DECISIONS.json + DECISIONS_ETERNAS.md)."""
import json,time,os
def L(f,d):
    try: return json.load(open(f,encoding="utf-8"))
    except Exception: return d
pend=L("PENDING_ACTIONS.json",{"queue":[]}); mass=L("MASS_IDEAS.json",{}); brain=L("BRAIN_MEMORY.json",{})
prev=L("DECISIONS.json",{"decisoes":[]})
n_cross=mass.get("pares_avaliados",0) or len(mass.get("top_ideias",[]))
seen={d["id"] for d in prev.get("decisoes",[])}
dec=prev.get("decisoes",[])
novas=0
mem=open("DECISIONS_ETERNAS.md","a",encoding="utf-8")
for a in pend.get("queue",[]):
    aid=a.get("id")
    if not aid or aid in seen: continue
    g=a.get("gancho") or " + ".join(a.get("combo",[])) or a.get("ideia","")
    nicho=a.get("nicho",""); lucro=a.get("lucro_1k",0); tipo=a.get("tipo","publicar")
    desc="%s cruzando '%s' no nicho %s (lucro est. $%s/1k)"%(tipo.replace('_',' '),g,nicho,int(lucro or 0))
    d={"id":aid,"tipo":tipo,"descricao":desc,"gancho":g,"nicho":nicho,"lucro_1k":lucro,
       "ideias_cruzadas":n_cross,"ts":time.strftime("%FT%TZ",time.gmtime()),"memoria_escrita":False}
    # GRAVA na memoria eterna (garante escrita p/ reinterligacao)
    mem.write("- [%s] %s | cruzou %d combinacoes | id=%s\n"%(d["ts"],desc,n_cross,aid)); mem.flush()
    d["memoria_escrita"]=True
    dec.append(d); seen.add(aid); novas+=1
mem.close()
out={"ts":time.strftime("%FT%TZ",time.gmtime()),"total_decisoes":len(dec),"novas":novas,
     "cruzamentos_por_decisao":n_cross,"decisoes":dec[-60:]}
json.dump(out,open("DECISIONS.json","w",encoding="utf-8"),ensure_ascii=False)
print("DECISIONS: %d total (+%d novas), cada uma cruzou %d combinacoes, gravadas na memoria eterna"%(len(dec),novas,n_cross))
