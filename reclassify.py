#!/usr/bin/env python3
"""reclassify.py - reclassifica TODOS os canais pelo CONTEUDO das transcricoes (NAO pelo nome).
15+ categorias, ponderado por frequencia. Corrige milhares de canais mal-rotulados."""
import os,json,glob
from collections import Counter
CATS={
 "Suplementos / Saude":["supplement","vitamin","health","nutrition","gut health","detox","collagen","keto","metabolism","immune","wellness","suplemento","saude"],
 "Emagrecimento":["lose weight","weight loss","fat loss","belly fat","fasting","calorie","emagrecer","dieta","gordura"],
 "Afiliados / Marketing Digital":["affiliate","funnel","clickbank","commission","dropship","ecommerce","conversion","copywriting","email list","afiliado","marketing digital"],
 "IA / Tecnologia / Automacao":["artificial intelligence","chatgpt","automation","chatbot","python","machine learning","llm","no-code","automacao","inteligencia artificial","software"],
 "Psicologia / Desenvolvimento":["mindset","psychology","habit","discipline","motivation","stoic","anxiety","dopamine","self improvement","psicologia","desenvolvimento"],
 "Financas / Investimentos":["invest","stock market","dividend","portfolio","retirement","finance","wealth","financas","investimento"],
 "Cripto / NFT / Web3":["crypto","bitcoin","ethereum","blockchain","nft","web3","defi","altcoin","cripto"],
 "Noticias / Politica":["breaking news","politics","government","election","president","policy","noticia","politica"],
 "Negocios / Empreendedorismo":["startup","business","entrepreneur","revenue","scale","saas","negocio","empreendedor"],
 "Fitness / Musculacao":["workout","muscle","gym","training","protein","bodybuilding","treino","musculacao"],
 "Beleza / Skincare":["skincare","makeup","beauty","serum","anti-aging","beleza","pele"],
 "Culinaria / Receitas":["recipe","cooking","ingredient","meal","bake","receita","cozinha"],
 "Educacao / Idiomas":["learn english","language","grammar","study","course","tutorial","aprender","idioma"],
 "Games / Entretenimento":["gameplay","gaming","stream","console","jogo","game"],
 "Relacionamento / Dating":["relationship","dating","attraction","couple","marriage","relacionamento"],
}
def main():
    cats={}; conf={}
    for f in glob.glob("transcripts/*.jsonl"):
        ch=os.path.basename(f).split(".")[0]; sc=Counter()
        try:
            for i,ln in enumerate(open(f,encoding="utf-8",errors="replace")):
                if i>5000: break
                s=ln.lower()
                for cat,kws in CATS.items():
                    for k in kws:
                        if k in s: sc[cat]+=1
        except Exception: pass
        if sc:
            top=sc.most_common(1)[0]; cats[ch]=top[0]; conf[ch]=top[1]
        else:
            cats[ch]="geral"; conf[ch]=0
    json.dump(cats,open("AETHER_CANAIS_CATEGORIAS.json","w",encoding="utf-8"),ensure_ascii=False,indent=1)
    json.dump(conf,open("AETHER_CANAIS_CONFIANCA.json","w",encoding="utf-8"),ensure_ascii=False)
    print("RECLASSIFY(conteudo): %d canais | %s"%(len(cats),dict(Counter(cats.values()).most_common(15))))
if __name__=="__main__": main()
