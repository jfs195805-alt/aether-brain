# AETHER — MEMÓRIA ETERNA (arquitetura completa, sem resumir)

Cérebro autônomo, 24/7, 100% grátis, que minera transcrições de 592+ canais do YouTube,
constrói uma **rede neural matemática real** sobre 1 milhão de frases, descobre insights que
ninguém tem cruzando canais/categorias diferentes, e publica conteúdo/pressells de afiliado —
sozinho, dentro da Regra Zero.

---

## 0. PRINCÍPIO CENTRAL

> **O conhecimento vem das transcrições reais. A matemática cruza tudo. A IA grátis só
> transforma o que a matemática descobriu em ideia — nunca inventa fato.**

Fluxo em uma linha:

```
transcrições reais → frases (afirmações) → grafo (léxico + semântico) → triângulos/cliques
→ figuras neurais → IA grátis vira ideia (com prova) → filtro de qualidade → governador → publica
```

---

## 1. INFRAESTRUTURA FÍSICA

| Peça | Papel |
|---|---|
| **GitHub Actions (repo público)** | RAM 16 GB, 4 vCPUs. Faz TODO o trabalho pesado. Grátis e ilimitado em repo público. |
| **Google Drive (rclone)** | Armazena o corpus (`AETHER_TRANSCRIPTS/youtube/*.jsonl` texto; `youtube_ts/*.jsonl` segmentos com timestamp). |
| **VM Google Cloud (969 MB, 2 vCPU)** | SÓ relay/leve. Túnel do dashboard, git-brain, memória → Supabase. NADA de cálculo pesado. IP 34.148.152.96, user `tafita1981novo`, SSH portas 443/22/2222/8443, Ed25519. |
| **Supabase (projeto V27, tpjvalzwkqwttvmszvie)** | Canal de memória em tempo real (`system_state`, `brain_memory`). |
| **Túnel Cloudflare (trycloudflare, sem conta)** | Expõe o estado da VM na porta 8099 com CORS, para o site ler ao vivo (SSE). |
| **GitHub Pages** | Hospeda o dashboard (`index.html`). |

**Conta GitHub:** usar conta LIMPA (`jfs195805-alt`) — a antiga (user ID 301879733) está
sinalizada com rate-limit de abuso (60/h REST + Actions suprimido). git funciona nas duas.

---

## 2. O PIPELINE (workflow `brain.yml`) — DOIS AGENTES EM PARALELO

Separado em 2 jobs que rodam ao mesmo tempo, sem um travar o outro:

### AGENTE COLETOR (colhe)
1. checkout · deps (`numpy scipy yt-dlp youtube-transcript-api`) · corpus do Drive
2. **TIMESTAMPS REAIS** (`backfill_ts.py`) — `timeout 600`, salva na hora
3. **MONITOR PERPÉTUO** (`channel_watch.py`) — lista TODOS os vídeos de cada canal, salva na hora
4. **BAIXA AUTOMÁTICO** (`scrape_missing.py`) — `timeout 720`, lote 60, prioridade por lucro×falta

### AGENTE PENSADOR (pensa)
1. checkout · deps · corpus
2. **escolher melhor IA grátis** (`ai_health.py AI_ONCE=1`)
3. **GRAFO NEURAL** (`neural_graph.py`) — léxico + semântico, salva `NEURAL_GRAPH.json` +
   `GRAPH_FULL.npz` + `GRAPH_NODES.jsonl`, commit imediato
4. **CLASSIFICA FRASES** (`classify_phrases.py`) — salva na hora
5. **SINAPSES** (`synapse_engine.py`) — triângulos/cliques/Monte Carlo, salva na hora
6. **AGENTE PENSADOR** (`idea_agent.py`) — IA grátis vira ideia com prova, salva na hora
7. reclassificar · cruzamento em massa · **AUTOCHECAGEM DO CANAL** · ffmpeg
8. **GOVERNADOR + PUBLICAR** · commit + push (re-dispara o loop)

`on: push` (self-chain) + `workflow_dispatch` + `schedule */10min`.
`concurrency: cancel-in-progress: true`. `paths-ignore` em todo JSON/HTML/MD de estado.

---

## 3. DA TRANSCRIÇÃO À FRASE (pré-processamento)

O corpus original guarda transcrição como **texto corrido, sem pontuação** (legenda
automática). Antes de virar ponto do grafo:

### 3.1 Coerentização (`coerentiza`)
Junta as falas picadas até formar **afirmação completa e autocontida**:
- fecha em pontuação final se já tem ≥ **MINW=9** palavras
- fecha ao atingir **MAXW=32** palavras, mas **nunca pendurada em conectivo** (DANGLE)
- descarta o que não tem **MINC=5** palavras de conteúdo (fora stopwords) e < 45 chars
- `limpa_inicio()` remove conectivo pendurado no começo ("and cheap to…" → "cheap to…")

### 3.2 Subagrupamento por vídeo (`subagrupa`)
Junta frases **consecutivas do mesmo vídeo** que falam da mesma coisa
(Jaccard de termos ≥ **COESAO=0.12**, até **MAXB=3** frases / **MAXBW=70** palavras) →
cada ponto do grafo é um **bloco de ideia**, não um fragmento solto.

### 3.3 Timestamps reais (`backfill_ts.py`)
`youtube_transcript_api` é **bloqueado em IP de datacenter** (runners GitHub). Solução:
**yt-dlp** baixa a legenda **VTT** (que traz `start` de cada fala) → `segments: [[seg, texto]]`.
Cada ponto ganha `link = youtu.be/ID?t=SEGUNDO`.

---

## 4. O GRAFO NEURAL (`neural_graph.py`) — DUAS CAMADAS

### 4.1 Camada LÉXICA — blocking por termos raros
Não compara 1M×1M (10¹² — inviável). Usa **indexação invertida por termos raros**:
- TF-IDF esparso (scipy `csr_matrix`) de todas as frases; vocab até 60.000, df ≥ 3
- para cada frase, indexa pelos **8 termos mais raros** (df ≤ `NG_DFMAX=1200`)
- só compara frases que compartilham um termo raro (é onde mora o significado)
- por bloco (≤ `NG_BUCKET=2500`): `S = Xb @ Xb.T` (produto esparso) → pares acima de `NG_LIM=0.18`
- **heap de tamanho fixo por nó** (`KEEP_K=10`) — memória constante, NÃO acumula todos os pares
- **teto `NG_MAXPAIRS=1.5e9`** por ciclo + **rotação de blocos** (`offset_blocos` salvo em
  `ACUMULADO.json`) → cada ciclo processa um trecho, cobertura **soma para sempre**

### 4.2 Camada SEMÂNTICA — SVD randomizado + IVF (o pulo do gato)
Liga frases que dizem a mesma coisa **com palavras diferentes** (a léxica é cega a isso):

**a) SVD randomizado (Halko–Martinsson–Tropp, 2011):**
```
Ω = matriz gaussiana aleatória (vocab × (K+p)), K=256 dims latentes, p=12 oversampling
Y = X @ Ω            # esparso @ denso — rápido; captura o subespaço dominante
Y, _ = qr(Y)         # base ortonormal
B = (X.T @ Y).T      # projeta os dados nessa base
Ub, S, Vt = svd(B)   # SVD pequeno (K+p × vocab)
Z = (Y @ Ub[:,:K]) * S[:K]   # embeddings NF×256, normalizados → produto interno = cosseno
```
É o algoritmo que substituiu o SVD clássico em escala (mesma família do LSA/embeddings).

**b) Índice IVF (arquitetura FAISS/Meta):**
- **k-means mini-batch** (6 iterações, `NG_CELLS=1500` células) agrupa o espaço latente
- cada frase é atribuída à célula mais próxima
- **kNN exato DENTRO de cada célula** (bloco pequeno) — `NG_SKNN=6` vizinhos, cosseno ≥ `NG_SLIM=0.45`
- torna o kNN em 1M de vetores viável (senão seriam 10¹² comparações)

**c) União:** arestas léxicas ∪ arestas semânticas → grafo muito mais rico, com pontes
entre domínios. Relatadas separadas: `sinapses_lexicais` + `sinapses_semanticas`.

### 4.3 Saídas
- `NEURAL_GRAPH.json` — recorte para o site (top `NODES=2000` nós, `EDGES=20000` arestas)
  com frase/canal/vídeo/link/timestamp por nó
- `GRAPH_FULL.npz` — **grafo INTEIRO** (scipy esparso, binário, não vai pro git) para o
  motor de sinapses no mesmo job
- `GRAPH_NODES.jsonl` — metadados de todos os nós
- `ACUMULADO.json` — memória cumulativa: `pares_avaliados_total`, `sinapses_descobertas_total`,
  `ciclos`, `offset_blocos`
- métricas medidas: `ram_pico_mb` (via `resource.getrusage`), `ram_total_mb`, `pares_por_segundo`

---

## 5. SINAPSES DE ORDEM SUPERIOR (`synapse_engine.py`) — sobre o grafo INTEIRO

**Erro corrigido:** o motor antigo só via os 2.000 nós do recorte → 0 figuras. Agora carrega
`GRAPH_FULL.npz` (1M nós) e opera com matemática de grafo em escala.

### 5.1 Triângulos — contagem EXATA por álgebra esparsa
```
T = (1/6) · Σ ( (A · A) ⊙ A )     # processado em blocos de 20.000 linhas
```
Conta TODO trio A-B-C mutuamente ligado do grafo inteiro. Sem amostragem. Forma canônica
de contar triângulos em grafos de milhões de nós.

### 5.2 Cliques (figuras de N pontos) — Bron-Kerbosch + degenerescência
Algoritmo **Eppstein–Löffler–Strash** (estado da arte para cliques maximais em grafos
esparsos gigantes):
- ordenação de degenerescência (aprox. por grau crescente)
- para cada nó `v`, BK só sobre os **vizinhos posteriores** na ordem → corta a explosão
  exponencial para tratável
- pivô = vizinho de maior interseção (minimiza ramos)
- teto `SYN_MAXC=500000` cliques
Encontra figuras de 3, 5, 12, 40 pontos onde **todos se ligam a todos** = ideia composta exata.

### 5.3 Comunidades — propagação de rótulos vetorizada sobre a matriz esparsa

### 5.4 Pontuação com MONTE CARLO (incerteza real)
Cada figura: `monte_carlo(sims, div, lu, n)` com **SYN_MC=400** amostras:
- similaridades das arestas são medidas ruidosas → reamostra `N(média, sd/√n)`
- `score = clip(amostra,0,1) · (0.4+0.6·diversidade) · (1+ln(n)/2.2) · (1+ln(lucro)/6)`
- devolve **média, p05, p95** e **confiança = 1 − (p95−p05)/score**
- só vai para produção se **p05 ≥ LIMIAR·0.6** (o pior cenário se sustenta)

### 5.5 INSIGHT RARO
Figura com **≥4 pontos, ≥3 categorias E ≥3 canais diferentes** = cruzamento que ninguém tem
(porque ninguém cruzou 1M de frases de 592 canais). Vira card roxo no site.

### 5.6 Memória eterna (`KNOWLEDGE_ETERNO.json`)
Reforço **EWMA (α=0.30)**: figura/conceito que reaparece ganha peso; o que não se confirma
decai (×0.97). Nunca apaga. Acumula para sempre. `visto`, `primeira`, `ultima`, `provas`.

---

## 6. CLASSIFICAÇÃO DE FRASES (`classify_phrases.py` v2)

**Erro corrigido:** v1 exigia 2 palavras exatas de lista fixa → classificava 0,8% (7.977 de 1M).

v2 (estatístico):
1. TF-IDF esparso de TODAS as frases
2. **Sementes expandidas pelo corpus**: cada categoria começa com termos óbvios
   ("creatina", "whey") e o motor busca, nas frases reais, os ~150 termos que **mais
   co-ocorrem** com as sementes → vetor de categoria aprendido dos 592 canais
3. classificação **vetorial** (cosseno frase × vetor-categoria), multi-rótulo, limiar 0.10
4. frase que não bate nada fica **"sem categoria"** (honesto, não força)
15 categorias: Suplementos, Emagrecimento, Fitness, Afiliados, IA e Tech, Finanças, Cripto,
Negócios, Saúde, Psicologia, Beleza, Educação, Culinária, Games, Notícias.

---

## 7. AGENTE PENSADOR (`idea_agent.py`) — IA grátis vira ideia real

Recebe as **figuras neurais** (conjuntos de frases reais que a matemática ligou) e manda para
IA grátis (`ai_providers.ask`) com regra dura: *"use SÓ estas afirmações como fonte, não
invente nada"*. Devolve JSON: `nicho` específico, `gancho` substantivo, `titulo`, `angulo`
(o insight que ninguém fala), `porque_funciona`, `formato`. Descarta se vier vago/stopword/
nicho genérico. Cada ideia carrega os **links dos vídeos de origem como prova**.
Saída: `IDEIAS.json` + entrada em `PENDING_ACTIONS.json`.

---

## 8. IA GRÁTIS (`ai_providers.py`) — 100% sem custo

- `_pollinations_text` (keyless), NVIDIA/Groq/HF (free tier), reordenados por
  `AETHER_AI_ORDER` que o `ai_health.py` atualiza probando quem está vivo + latência a cada 45 s
- `ask(prompt, max_tokens, max_cycles)` tenta os provedores na ordem do momento
- imagem: Pollinations (keyless). Voz: Edge TTS (keyless). **Nunca gasta em API paga.**

---

## 9. AUTOCHECAGEM DO CANAL (`channel_audit.py`)

Só no canal da marca (`YT_RT_GLOBALSUP`). Nunca conta pessoal. A cada ciclo:
1. **Duplicados** (mesmo produto) → mantém o de mais views, os outros vira **PRIVADO**
   (NUNCA deleta). Lista no relatório para decisão humana.
2. **Sem link de produto** → marca para revisão.
3. **Comentário fixado** com descrição breve EM INGLÊS + o link REAL do presell
   (o mesmo que já está na descrição — nunca inventa URL).
4. **Aviso na descrição** (PT+EN): "o link do produto está no comentário fixado".

---

## 10. GOVERNADOR + FILA (`governor.py`, `decisions.py`, `PENDING_ACTIONS.json`)

`decisions.py` transforma oportunidade em decisão **com filtro de qualidade** (Regra Zero §7):
rejeita stopword/nicho genérico/sem prova. Grava cada decisão válida em
`DECISIONS_ETERNAS.md` (append-only) **antes** de marcar `memoria_escrita=true`.
Governador publica só com marca correta, foto real, QA ≥ 80, cooldowns.

---

## 11. DASHBOARD (`index.html` + túnel + Supabase)

- **Carga imediata** ao abrir (não espera SSE) + **SSE push** + **fallback** a cada 3 s.
- `no-cache` no header + carimbo de **build vAAAAMMDD-HHMM** (para detectar cache do navegador).
- Campos: **busca** (instantânea, na memória local + servidor) e **incluir canal** (POST
  `/add_channel` → grava `NOVOS_CANAIS.json` → git → o monitor integra sozinho).
- **Filtro global interligado**: clicar em canal/termo/categoria/nó filtra TUDO em tempo real
  (grafo acende os nós que batem, resto apaga; canais/categorias/insights/decisões filtrados).
- Painéis: KPIs, insights raros (cards roxos), decisões em produção, **rede neural (canvas
  próprio, sempre viva)**, monitoramento perpétuo, **vídeos por canal `transcritos/total no
  YouTube` + faltando + posição na fila**, categorias, matemática da rede, autochecagem,
  lucro/categoria, melhor IA, acumulado eterno.
- Endpoints do túnel: `/live.json`, `/graph`, `/stream` (SSE), `/search?q=`, `/add_channel` (POST).
  Vigia (`endpoint_guard.sh`, cron) republica a URL do túnel se ela mudar.

---

## 12. ESTADO MEDIDO (marco: 2026-07-12, ciclo 5)

**Corpus:** 592 canais · 8.155 vídeos · **1.000.280 frases reais**

**Grafo (por ciclo):**
- pares léxicos avaliados: **648.902.341** em 450 s (~1,44 M pares/s)
- sinapses **léxicas**: **6.286.688**
- sinapses **SEMÂNTICAS** (SVD 256d + IVF): **820.380** em apenas **56 s**
- total: **7.107.068** sinapses/ciclo
- **RAM: 11.993 MB de 15.989 MB (75% dos 16 GB)** — a camada espectral é o que ocupa a máquina

**Acumulado eterno (ciclo 5):**
- **2.995.378.934 pares** avaliados (≈3 bilhões)
- **29.179.877 sinapses** descobertas

**Sinapses de ordem superior (sobre o grafo inteiro):**
- **TRIÂNGULOS EXATOS: 7.792.786** (7,8 milhões) — calculados em **11,1 s** por álgebra esparsa
- **CLIQUES (figuras): 500.000** (teto batido) · maior figura: **10 pontos**
- **Conceitos (comunidades): 42.903**
- Insights raros: 36 · Oportunidades em produção: 12

**Espaço combinatório:** C(1.000.280, 3) ≈ **1,67 × 10¹⁷** trios possíveis.
O motor não enumera esse absurdo (ninguém pode) — percorre exatamente os que a estatística
provou existirem.

---

## 12-B. ANTI-CLICHÊ — a lição mais importante do projeto

> **Num grafo de texto, o nó mais conectado NÃO é o mais valioso — é o mais genérico.**

Quando o motor rodou pela primeira vez sobre o grafo inteiro, os "insights raros" foram:
- *"Espero que esse vídeo tenha te ajudado"* (8 pontos, 3 categorias, 4 canais)
- *"[__] que pariu"* (palavrão censurado, 9 pontos, 8 canais)

A matemática estava **correta**: essas frases realmente se conectam com tudo, em todos os
canais. O problema é que **fórmula de encerramento não é conhecimento**.

**As três defesas (obrigatórias em qualquer projeto do tipo):**

1. **Limpeza de texto** (`limpa_texto`): `html.unescape` (`&gt;`, `&nbsp;`, `&amp;`),
   remover censura `[ __ ]`, remover marcador de falante `>>`.
2. **Filtro de boilerplate**: calcular a *assinatura* de cada frase (conjunto ordenado dos
   seus termos de conteúdo). Se a mesma assinatura aparece em **≥ N canais diferentes**
   (N=4), é **fórmula** → remover do grafo. Isso mata "se inscreva", "bom dia pessoal",
   "até o próximo vídeo" automaticamente, sem lista negra manual.
3. **Diversidade lexical na figura**: uma figura só é insight se seus pontos **falam coisas
   diferentes** — Jaccard médio de termos entre os pontos **< 0.55**. Senão é a mesma frase
   repetida em canais diferentes.

## 13. ERROS REAIS COMETIDOS E CORRIGIDOS (aprender com eles)

| Erro | Sintoma | Correção |
|---|---|---|
| numpy pesado na VM 969 MB | load 118, SSH inacessível | todo cálculo no GitHub |
| avalanche de cron sem flock | 599 processos, VM morta | flock em tudo, `MAILTO=""`, exim4 mask |
| guardas em loop de 0.5s/2s | thrashing de I/O | 15 s / 30 s + flock |
| `concurrency: cancel-in-progress:false` | runs presas em pending eterno | mudar para `true` |
| `git push || true` no grafo | resultado v3 descartado em silêncio | pull --rebase + reportar falha |
| só commit no passo final | run interrompida = tudo perdido | cada passo salva na hora |
| grafo só salvava 2000 nós | motor de sinapses achava 0 figuras | `GRAPH_FULL.npz` inteiro no job |
| classificador de 2 palavras exatas | 0,8% classificado | sementes expandidas + vetorial |
| `youtube_transcript_api` | bloqueado em IP de nuvem | yt-dlp VTT |
| contador de animação como métrica | "165 sinapses/s" fake | throughput real medido |
| decisões de stopword | "aqui + gente" ia publicar | filtro de qualidade |
| OOM no grafo v3 | processo morto por RAM | heap fixo por nó + teto + rotação |
| service key no navegador | risco de vazar banco | anon/publishable só no cliente |
| **`yaml.dump` gravou `true:`** | PyYAML lê a chave `on` como booleano → workflow inválido → runs falham **sem nenhum job** | após reescrever YAML de workflow com Python, **sempre** trocar `true:` de volta por `on:` |
| **CLICHÊ vira "insight"** | os 500k cliques mais conectados eram *"espero que esse vídeo tenha te ajudado"*, *"até o próximo vídeo"* e palavrão censurado. **O mais conectado é o mais genérico** — armadilha clássica de grafo de texto | 3 defesas: (1) `limpa_texto` remove HTML (`&gt;&gt;`, `&nbsp;`) e censura `[__]`; (2) **filtro de boilerplate** — frase cuja assinatura aparece em **≥4 canais diferentes** é fórmula, não conhecimento → removida do grafo; (3) **exigir diversidade lexical** na figura (Jaccard médio entre os pontos < 0.55) |
| classificação em 8,3% | limiar do cosseno alto demais | baixar `CLS_LIM` para 0.06 + limpar o texto antes |

---

## 14. GLOSSÁRIO PROBABILÍSTICO/ESPECTRAL (sem misticismo)

- **Não há computação quântica.** GitHub Actions não tem QPU. O nome correto do que se faz é
  **probabilístico + espectral**.
- **Espectral** = usa autovalores/valores singulares da matriz (SVD) para achar o
  subespaço de significado. LSA é o exemplo clássico.
- **Randomizado (Halko et al.)** = aproxima o SVD com projeção aleatória — inviável fazer SVD
  exato de 1M×60k, viável com projeção randômica.
- **Probabilístico** = Monte Carlo propaga incerteza; cada score vira distribuição com p05/p95.
- **IVF (inverted file index)** = a estrutura do FAISS; particiona o espaço em células
  (k-means) e busca vizinhos dentro delas — vizinho aproximado em escala.
- **Blocking** = só compara itens que compartilham uma chave (termo raro); reduz o custo
  quadrático do all-pairs.
