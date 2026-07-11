#!/usr/bin/env python3
"""reclassify.py - reclassifica TODOS os canais pelo conteudo real."""
import os,json,glob
from collections import Counter
NICHES={
 "Suplementos / Saude":["supplement","vitamin","health","weight","diet","nutrition","gut","detox","collagen","keto","metabolism","emagre","saude","suplement"],
 "Afiliados / Marketing Digital":["affiliate","funnel","clickbank","commission","dropship","ecom","conversion","copywriting","afiliad","marketing"],
 "IA / Tecnologia / Automacao":["automation","chatbot","python","software","machine learning","agent","automac","intelig","tecnolog","openai","llm"],
 "Psicologia / Desenvolvimento Pessoal":["mindset","psychology","habit","discipline","motivation","stoic","anxiety","dopamine","psicolog","desenvolv"],
 "Financas / Investimentos":["invest","stock","crypto","bitcoin","trading","finance","wealth","dividend","financ","dinheiro","cripto"],
 "Noticias / Politica":["news","politic","government","election","president","economy","noticia"],
 "Emagrecimento":["weight loss","lose weight","fat loss","belly","emagrecer","dieta"],
}
def main():
    cats={}
    for f in glob.glob("transcripts/*.jsonl"):
        ch=os.path.basename(f).split(".")[0]; cnt=Counter()
        try:
            for i,ln in enumerate(open(f,encoding="utf-8",errors="replace")):
                if i>4000: break
                s=ln.lower()
                for n,kws in NICHES.items():
                    for k in kws:
                        if k in s: cnt[n]+=1
        except Exception: pass
        cats[ch]= (cnt.most_common(1)[0][0] if cnt else "geral")
    json.dump(cats,open("AETHER_CANAIS_CATEGORIAS.json","w",encoding="utf-8"),ensure_ascii=False,indent=1)
    print("RECLASSIFY: %d canais | dist %s"%(len(cats),dict(Counter(cats.values()).most_common(8))))
if __name__=="__main__": main()
