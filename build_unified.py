"""build_unified.py — consolida ideas_mined.jsonl (ultima versao por canal) em um DOCUMENTO
UNIFICADO de producao: produtos/afiliados citados, taticas e ideias de TODOS os canais/videos.
Sempre inclui o que chegou de novo. Gera AETHER_UNIFICADO.json + AETHER_UNIFICADO.md.
"""
import json, os, time, collections
IN = "ideas_mined.jsonl"; OJ = "AETHER_UNIFICADO.json"; OM = "AETHER_UNIFICADO.md"

def main():
    latest = {}
    if os.path.exists(IN):
        for l in open(IN, encoding="utf-8", errors="replace"):
            try:
                r = json.loads(l); c = r.get("canal")
                if c: latest[c] = r  # ultima versao vence
            except Exception:
                pass
    prods = collections.Counter(); tats = []; ideas = []; per = []; total_videos = 0
    for c, r in latest.items():
        total_videos += int(r.get("videos", 0) or 0)
        for p in (r.get("produtos_afiliados") or []):
            k = str(p).strip()
            if k: prods[k.lower()] += 1
        for t in (r.get("taticas") or []): tats.append({"canal": c, "tatica": t})
        for i in (r.get("ideias") or []): ideas.append({"canal": c, "ideia": i})
        per.append({"canal": c, "videos": r.get("videos", 0), "modelo": r.get("modelo", "")})
    resumo = {"canais": len(latest), "videos_cobertos": total_videos,
              "total_taticas": len(tats), "total_ideias": len(ideas),
              "gerado": time.strftime("%Y-%m-%dT%H:%M:%S")}
    json.dump({"resumo": resumo, "produtos_afiliados": prods.most_common(),
               "taticas": tats, "ideias": ideas, "por_canal": per},
              open(OJ, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    with open(OM, "w", encoding="utf-8") as f:
        f.write("# AETHER - Documento Unificado de Ideias (producao)\n\n")
        f.write("Canais: %d | videos cobertos: %d | taticas: %d | ideias: %d | %s\n\n"
                % (len(latest), total_videos, len(tats), len(ideas), resumo["gerado"]))
        f.write("## Produtos/afiliados mais citados\n\n")
        for name, ct in prods.most_common(80): f.write("- %s (%d)\n" % (name, ct))
        f.write("\n## Ideias acionaveis (amostra)\n\n")
        for it in ideas[:500]: f.write("- **%s**: %s\n" % (it["canal"], str(it["ideia"])[:300]))
    print("unificado:", len(latest), "canais |", len(ideas), "ideias |", sum(prods.values()), "mencoes produto")

if __name__ == "__main__":
    main()
