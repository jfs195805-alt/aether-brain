#!/usr/bin/env python3
"""limpa_zero.py - RESET TOTAL da analise antiga (pedido do Rafael: "comece do zero").

APAGA tudo que foi DERIVADO da estrategia velha (frases, pares, grafo, sinapses,
triangulos, insights, classificacoes, memoria de analise).

NAO TOCA no que e FONTE ou INVENTARIO:
  - transcripts/        (transcricoes BRUTAS - a materia-prima, 8k+ videos)
  - COBERTURA.json      (o que ainda falta baixar de cada canal)
  - CANAIS_STATS.json   (inventario de canais)
  - codigo, workflow, docs

Idempotente: se ja limpou, nao faz nada. Git guarda o historico - nada e irrecuperavel.
"""
import os, shutil

DERIVADOS = [
    # grafo / pares / sinapses / triangulos
    "NEURAL_GRAPH.json", "GRAPH_FULL.npz", "GRAPH_NODES.jsonl", "ACUMULADO.json",
    "SINAPSES.json", "KNOWLEDGE_ETERNO.json", "INTERLINK.json",
    # classificacao de frases / ideias em massa / memoria de analise
    "FRASES_CATEGORIAS.json", "MASS_IDEAS.json", "BRAIN_MEMORY.json",
    "AETHER_CANAIS_CATEGORIAS.json", "AETHER_CANAIS_CONFIANCA.json",
    # fila/logs vindos da estrategia velha
    "PENDING_ACTIONS.json", "GOVERNOR_LOG.md", "RESULTS.json", "AUDITORIA_CANAL.json",
    # saida do extrator (recomeca do zero)
    "CONHECIMENTO_PRODUCAO.json", "PAUTA.json",
    # scripts mortos da estrategia de pares/grafo (ficam no historico do git)
    "neural_graph.py", "synapse_engine.py", "classify_phrases.py", "idea_agent.py",
    "mass_ideas.py", "fast_interlink.py", "build_vault.py", "reclassify.py",
]
PASTAS = ["vault", "out", "__pycache__"]

# blindagem: jamais apagar a fonte
PROIBIDO = ("transcripts", "transcripts_ts", "COBERTURA.json", "CANAIS_STATS.json")

apagados = []
for f in DERIVADOS:
    if f in PROIBIDO:
        continue
    if os.path.isfile(f):
        os.remove(f)
        apagados.append(f)
for d in PASTAS:
    if d in PROIBIDO:
        continue
    if os.path.isdir(d):
        shutil.rmtree(d)
        apagados.append(d + "/")

# prova de que a fonte continua intacta
n_canais = len([x for x in os.listdir("transcripts")]) if os.path.isdir("transcripts") else 0
print("LIMPA_ZERO: %d artefatos apagados -> %s" % (len(apagados), ", ".join(apagados) or "nada (ja limpo)"))
print("LIMPA_ZERO: FONTE INTACTA -> transcripts/ com %d arquivos de canal" % n_canais)
