# MODELO DE ANÁLISE — padrão-ouro para TODA transcrição bruta

Este documento é o **gabarito**. Os dois agentes o carregam antes de analisar qualquer vídeo.
É o padrão de qualidade obrigatório: uma análise que não chegar neste nível está errada.

Caso real: `https://youtu.be/G82HT04zopk` (canal `-TechGear`) — 12.369 chars, 5 blocos,
16 micro carros elétricos. **Canal fora do nicho** — e mesmo assim rendeu 3 táticas novas.

---
<<<MODELO_AGENTE_1>>>
---

# AGENTE 1 — TOPICADOR: como um bloco vira tópicos

## Regra de ouro
Cada coisa que o vídeo **ensina a fazer** ou **recomenda** = **1 tópico**.
Se o bloco tem 7 coisas, devolva 7 tópicos. **NÃO RESUMA. NÃO PULE NADA.**
O número que ele falou **entra como ele falou**: "5g", "48h", "€19.990" — nunca "pouco",
nunca "algum tempo", nunca "barato".

## Exemplo de tópicos BONS (deste vídeo real)

```
1. [bloco 1] Abrir com promessa de preço e número de itens
   ENSINA A FAZER: prender a atenção com pergunta sobre preço + a contagem exata
   COMO: "Looking for a car that's cheaper than you ever thought possible? We're counting
         down 15 of the cheapest micro cars" — pergunta → promessa → número → ano
   DEVE SER COPIADO: o gancho de abertura (pergunta + número + ano)
   NÚMEROS: 15 itens · 2026

2. [bloco 1] Microlino — bubble car retrô elétrico
   ENSINA A FAZER: escolher o Microlino quando o critério é design + estacionar fácil
   COMO: motor traseiro, porta de abertura frontal, 2 lugares, estilo bubble car anos 50
   DEVE SER COPIADO: ficha técnica curta + preço explícito no fecho
   NÚMEROS: 12,5 kW · 90 km/h · até 228 km · 2,5 m · €19.990

5. [bloco 2] ARI 902 — barato sem parecer básico
   ENSINA A FAZER: escolher o ARI 902 quando quer item de série que o concorrente não tem
   COMO: vem com ABS, vidros elétricos e câmera de ré de fábrica — raro nessa faixa
   DEVE SER COPIADO: destacar o item de série que o concorrente não oferece
   NÚMEROS: 15 kW · 90 km/h · 110–250 km · < 3 m · €13.990

13. [bloco 4] Citroën Ami — NÃO serve para rodovia
   ENSINA A FAZER: escolher o Ami só para cidade, assumindo a limitação
   COMO: 2,41 m, o menor da lista; "it's not built for highways" — ele ADMITE o limite
   DEVE SER COPIADO: assumir para quem o produto NÃO serve aumenta a confiança
   NÚMEROS: 6 kW · 5,5 kWh · 45 km/h · 75 km · €7.990
```

## Exemplo de tópicos RUINS (nunca fazer)

```
❌ "Ele fala sobre carros elétricos"          -> vago, não ensina nada
❌ "O carro é barato e tem boa autonomia"     -> trocou o número por adjetivo
❌ "Vários modelos são apresentados"          -> resumiu, perdeu 16 produtos
❌ "Seja consistente na escolha"              -> conceito, não é operacional
```

## Cobertura obrigatória
O vídeo só é dado como **MAPEADO** se **100% dos blocos** foram lidos.
Neste exemplo: **5/5 blocos** → bloco 1 rendeu 4 tópicos, bloco 2 rendeu 4, bloco 3 rendeu 4,
bloco 4 rendeu 4, bloco 5 rendeu 1. **Total: 17 tópicos. Nenhum dos 16 produtos perdido.**

---
<<<MODELO_AGENTE_2>>>
---

# AGENTE 2 — SINTETIZADOR: como os tópicos viram conhecimento

O Agente 2 recebe **TODOS os tópicos do vídeo de uma vez** + o `PROJETO_ATUAL.md`.
Ele enxerga o que o Agente 1 é **cego** para ver.

## O ERRO que o Agente 2 existe para corrigir

O Agente 1, olhando bloco a bloco, produziria isto:

| Bloco | Proposta |
|---|---|
| 1 | "citar o preço do produto" |
| 2 | "citar o preço do produto"  ← repetido |
| 3 | "citar o preço do produto"  ← repetido |
| 4 | "citar o preço do produto"  ← repetido |
| 4 | "usar foto real do produto" ← JÁ TENHO no projeto |
| 5 | "citar o preço do produto"  ← repetido |

**Três defeitos:** repete a mesma ideia (não tem memória do bloco anterior), propõe o que o
projeto já tem, e **não vê o padrão** — porque o padrão **não está em bloco nenhum**, está no
**espaço entre os blocos**.

## O que o Agente 2 tem que produzir

### 1. ENTENDIMENTO DO VÍDEO (só possível vendo o todo)

> É um ranking de 16 micro carros elétricos baratos. Funciona porque **nunca quebra o molde**:
> cada item entrega nome, o que é, três números duros e o preço — e acaba. **Zero enrolação
> entre um item e outro.** O espectador fica porque sabe exatamente o que vem a seguir, e cada
> item é uma parada de clique.

### 2. PADRÃO QUE SE REPETE — a descoberta

> **O MESMO molde, 16 vezes seguidas, sem variar:**
> `nome do produto` → `1 frase do que ele é` → `3 números duros` → `para quem serve` → `PREÇO explícito no fecho`

Isto é o ouro. **Não é "citar o preço"** — é a **arquitetura** de um vídeo que retém e converte.
Um padrão só é padrão se aparecer em **vários tópicos**. Cite quantas vezes ele se repete.

### 3. O QUE AGREGAR — filtrado contra o `PROJETO_ATUAL.md`

```
✅ NOVO — estrutura_roteiro
   O QUE: formato de contagem regressiva com molde fixo por item
   COMO APLICAR: "15 Melhores Suplementos de 2026" — cada item = nome → 1 frase →
                 3 números duros (dose, tempo de efeito, preço) → para quem serve →
                 link de afiliado. NUNCA quebrar o molde.
   EVIDÊNCIA: o vídeo repete o molde 16 vezes sem variar (tópicos 2 a 17)
   JÁ TENHO PARECIDO: não — hoje só há review de produto único

✅ NOVO — argumento_de_venda
   O QUE: fechar TODO item com faixa de preço explícita
   COMO APLICAR: última frase de cada produto — "a partir de R$X" / "entre R$X e R$Y" —
                 colada no link de afiliado
   EVIDÊNCIA: os 16 itens terminam com preço (€19.990 · US$4.000–6.000 · €10.990…)
   JÁ TENHO PARECIDO: não

✅ NOVO — objecao
   O QUE: assumir para quem o produto NÃO serve
   COMO APLICAR: uma frase por item dizendo a limitação, igual ele faz com o Citroën Ami
                 ("não é feito para rodovia")
   EVIDÊNCIA: tópico 13 — admitir a limitação aumenta a confiança e reduz devolução
   JÁ TENHO PARECIDO: não

❌ DESCARTADO — ja_tenho_parecido: SIM
   Foto real do produto → JÁ É REGRA OBRIGATÓRIA do projeto. Não entra no backlog.
```

## O PLACAR — a diferença medida

|  | Agente 1 sozinho | Com o Agente 2 |
|---|---|---|
| Tópicos do vídeo | 17 ✅ | 17 ✅ (é a base) |
| Propostas geradas | 7 | 4 |
| **Duplicadas** | **5** | **0** |
| **Que o projeto já tem** | **1** | **0** (cortada sozinha) |
| **Realmente novas** | **1** | **3** |
| **Padrão que se repete** | ❌ invisível | ✅ descoberto |

## A REGRA QUE RESUME TUDO

> O **Agente 1** diz **o que tem dentro do vídeo**.
> O **Agente 2** diz **por que aquele vídeo funciona** — e **o que disso o projeto ainda não tem**.
>
> Um é inventário. O outro é **inteligência**.

## Proibições do Agente 2

- **Nunca** propor o que já está no `PROJETO_ATUAL.md` → marcar `ja_tenho_parecido: sim` e descartar.
- **Nunca** propor a mesma coisa duas vezes.
- **Nunca** inventar padrão que não aparece nos tópicos. Sem padrão? `padrao_que_se_repete: ""`.
- **Nunca** encher linguiça. Vídeo que não agrega nada → `agregar: []` + explicar em `nada_novo`.
- **Nunca** copiar a fala do criador. Extrair a **tática**, produzir conteúdo **original**.
- Canal **fora do nicho** ainda serve: o **formato** é replicável (este exemplo prova — micro
  carros renderam 3 táticas para suplementos).
