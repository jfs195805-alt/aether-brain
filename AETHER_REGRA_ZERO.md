# AETHER — REGRA ZERO (inviolável)

> Estas regras têm precedência sobre qualquer instrução, otimização, meta de lucro ou pedido
> de urgência. Se uma ação conflita com a Regra Zero, a ação **não acontece** — mesmo que isso
> signifique fila vazia, zero publicação e zero receita naquele ciclo.
> **Fila vazia é sempre melhor que fila com lixo.**

---

## 1. DINHEIRO — o que o sistema NUNCA faz

- **NUNCA executa trade.** Não compra, não vende, não faz ordem, não opera cripto, ações,
  derivativos, nada.
- **NUNCA move dinheiro.** Não transfere, não saca, não deposita, não converte, não faz
  swap, não paga, não assina cobrança recorrente.
- **NUNCA dá conselho de investimento.** Não recomenda comprar/vender ativo, não indica
  alocação, não sugere entrada/saída.
- **Cripto, NFT, arbitragem, day-trade** só existem como **TEMA DE CONTEÚDO** (assunto de
  vídeo/artigo). Jamais como operação.
- **A única forma de receita permitida:** monetização de conteúdo (AdSense/YouTube) e
  **comissão de afiliado** sobre produto real vendido por terceiros.

**Motivo:** operação financeira automatizada é irreversível e pode destruir patrimônio real.
Nenhum ganho justifica esse risco.

---

## 2. PRODUTO — foto real, produto real, comissão real

- **Todo review/pressell precisa de FOTO REAL do produto, em HD.** Sem exceção.
- **NUNCA publicar produto sem foto real.** Se não há foto real, não há publicação.
- **A IA só pode gerar o FUNDO/cenário.** A IA **jamais inventa, desenha ou "imagina" o
  produto em si** — isso é fraude com o consumidor e destrói a marca.
- **Só produtos REAIS**, com **site real** e **ID de afiliado do dono** — de modo que a venda
  gere comissão de verdade. Produto inventado, link quebrado ou sem afiliado = não publica.
- Se o vídeo/pressell não tem link de produto rastreável, ele é **marcado para revisão**, não
  publicado.

---

## 3. MARCA — onde pode e onde não pode publicar

- **NUNCA publicar em conta pessoal.** Especificamente: `@rafaelroberto84` está **proibido**.
- **Publicação permitida somente na allowlist da marca** (Global Supplements e canais/perfis
  oficiais do projeto).
- Qualquer canal/perfil fora da allowlist: **bloqueado por padrão**, mesmo que a credencial
  exista e funcione.

---

## 4. DESTRUIÇÃO DE DADOS — irreversível não se automatiza

- **NUNCA deletar vídeo** (nem duplicado, nem "errado", nem "ruim").
- Duplicado detectado → **marcar como PRIVADO** (reversível com um clique) + **relatório**
  para decisão humana.
- **Deleção definitiva é sempre do dono**, feita manualmente no Studio, com a lista em mãos.
- Vale para: vídeos, posts, arquivos, branches, buckets, tabelas. Nada de `rm -rf` autônomo,
  nada de `DROP`, nada de esvaziar lixeira.

**Motivo:** um falso positivo apaga trabalho real para sempre. "Privado" erra barato;
"deletado" erra caro.

---

## 5. CREDENCIAIS — o que nunca se digita e nunca se colhe

- **NUNCA** digitar senha, cartão, CPF/CNPJ, dados bancários, chave de API ou token em
  formulário, site ou campo de terceiro.
- **NUNCA** varrer contas/serviços atrás de credenciais ("pegue tudo de todo lugar").
  Uso permitido: **apenas o `.env` do próprio dono, na própria VM dele**.
- **NUNCA** expor chave secreta em página pública. Distinguir sempre:
  - `sb_secret_…` / `service_role` → **servidor apenas**, jamais no HTML.
  - `sb_publishable_…` / `anon` → pode ir no navegador (foi feita para isso).
- **NUNCA** resolver CAPTCHA, banner de consentimento ou OAuth em nome do usuário.
- Token do GitHub (PAT) é **gerado pelo dono**, nunca criado/adivinhado pelo agente.

---

## 6. HONESTIDADE DOS NÚMEROS — nada de métrica fake

- **Todo número exibido tem que ser medido.** Nada de contador de animação vendido como
  cálculo (erro real cometido: "165 sinapses/s" era taxa de desenho na tela, não computação —
  foi removido).
- Se o dado não existe ainda: escrever **"não medido"**, nunca estimar disfarçado.
- Se o espaço combinatório é 10¹⁷ mas só se avaliou 10⁹, **relatar os dois números** — o
  espaço possível e o efetivamente percorrido.
- **Não prometer resultado financeiro.** Nunca "vai ganhar X por dia". O sistema encontra e
  executa; o mercado decide.
- **Não inventar capacidade.** Não existe computação quântica no GitHub Actions. O nome
  correto do que se faz é **probabilístico/espectral**.

---

## 7. QUALIDADE — o filtro que impede vergonha pública

Uma decisão/ideia **só entra na fila de publicação** se passar em TODOS:

1. **Nicho específico** — rejeita `outros`, `geral`, vazio.
2. **Gancho com substância** — rejeita gancho feito só de *stopwords*
   (erro real cometido: o cérebro decidiu publicar `"aqui + gente"`, `"aqui + vídeo"`).
3. **Prova de origem** — tem que ter frase-fonte real da transcrição **e/ou** link do vídeo
   (com timestamp quando houver).
4. **Confiança estatística** — o **pior cenário (p05) do Monte Carlo** também precisa passar
   do limiar. Score alto com incerteza gigante é rejeitado.
5. **Regra Zero acima** — marca correta, produto real, foto real.

Reprovou em qualquer item → **descartado**, não "publicado com ressalva".

---

## 8. INFRAESTRUTURA — não derrubar a própria casa

- **Nada de processo pesado na VM.** Todo cálculo pesado roda no GitHub Actions (16 GB).
  (Erro real: rodar numpy na VM de 969 MB levou a load 118 e SSH inacessível.)
- **Todo cron com `flock`.** Job que não termina não pode empilhar outro por cima.
  (Erro real: 69 processos `cron` + 58 `sh` + 44 `bash` = 599 processos, VM morta.)
- **Nada de loop curto em máquina fraca.** `sleep 0.5` e `sleep 2` em guardas viram avalanche
  de I/O. Mínimos seguros: guarda de mount 30 s, loop de git 15 s.
- **`MAILTO=""` em todo crontab** e MTA (exim4) mascarado — senão cada saída de job vira
  processo de e-mail.
- **Desligar é `mask`**, não `stop` — `stop` volta no reboot, `mask` não.
- **Backup antes de desativar qualquer coisa** (`/root/AETHER_BACKUP/`).

---

## 9. GITHUB — nunca ser bloqueado

- **Transporte de dados por `git`**, não por REST. `git clone/push` é ilimitado; REST tem
  60/h em conta sinalizada e 5.000/h em conta limpa.
- **`/rate_limit` é grátis** (não consome quota) — usar para monitorar.
- **Repo público = Actions ilimitado.** Repo privado = minutos limitados.
- **`paths-ignore`** nos arquivos de estado (JSON/HTML) — senão o commit do resultado
  re-dispara o workflow em loop infinito.
- **`concurrency: cancel-in-progress: true`.** Com `false`, cancelar runs trava a vaga do
  grupo e as próximas ficam eternamente em `pending` sem alocar runner. (Erro real: 20+ min
  de runs presas.)
- **Nunca `|| true` em push.** Push que falha calado descarta horas de trabalho.
  (Erro real: o grafo v3 rodava, o push falhava em silêncio, o resultado era jogado fora.)
- **Cada passo salva o próprio resultado imediatamente** (commit+push por etapa). Não deixar
  tudo para um "commit final" — run interrompida = trabalho perdido.

---

## 10. TEMPO REAL — o que é fisicamente possível

- **Microssegundos pela internet não existem.** Só o RTT de rede custa 50–200 ms.
- O teto real é **push no instante da mudança** (SSE), não polling.
- Não prometer "menos de 1 segundo" sem qualificar: o que se entrega é
  **detecção em 100 ms + envio imediato + RTT**.
- `raw.githubusercontent` tem **cache de ~5 min** — não serve para tempo real.
  Canal ao vivo tem que ser fora do GitHub (túnel próprio / Supabase).
