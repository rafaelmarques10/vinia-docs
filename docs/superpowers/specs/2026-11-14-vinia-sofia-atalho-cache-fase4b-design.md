# Vinia SaaS — Fase 4b: prompt estável, cache de entrada e atalho de seleção (design)

**Data:** 2026-11-14 · **Autor:** Rafael (decisões) + controlador (calls marcadas **[CALL]**)
**Status:** abordagem B aprovada pelo Rafael em 2026-11-14; este documento aguarda a aprovação dele. Deriva do estudo `2026-11-12-vinia-saas-precificacao.md` (§2, §6, §7) e da Fase 4 (Story 9.5, mergeada local na `main` em `77e93d6`).

## 1. Intenção e por quê

A Sofia manda a carta inteira em toda consulta, e o custo cresce com o tamanho da carta (R$ 0,0036 com 11 vinhos, R$ 0,0408 com 300). O estudo de preços só sustenta os preços e as cotas da Fase 4 com duas proteções: um teto de vinhos por consulta e o desconto de 50% da Groq na entrada em cache. Sem elas, a Fase 4 limita os planos a 100/150 rótulos, o que trava a venda para cartas maiores. As cartas do Rafael hoje têm até ~50 vinhos, então a prioridade é o cache; o atalho de seleção é proteção para cartas grandes.

## 2. Objetivos

1. **Prompt estável:** o início do prompt (sistema + carta) é byte a byte idêntico entre consultas do mesmo restaurante enquanto a carta não muda, para o cache automático da Groq acertar (a Groq dá 50% de desconto só no trecho inicial idêntico).
2. **Custo exato:** `ai_usage` grava os tokens vindos do cache e o custo usa o preço reduzido para eles.
3. **Carta inteira até 60 vinhos.** Acima disso, a Sofia recebe uma seleção de 40.
4. **Sem limite de rótulos por plano:** o limite da 9.5 (100/150, inclusive no trial) deixa de existir.

## 3. Não objetivos e anti-objetivos

**Não objetivos:** segunda chamada à IA para escolher vinhos, embeddings, busca vetorial, mudar o modelo, o texto/tom da Sofia ou as cotas e preços da Fase 4, Gemini/Anthropic (não usados pelo job), excedente e cobrança (Fase 5).

**Anti-objetivos (falha mesmo funcionando):** a Sofia recomendar vinho que não está na carta enviada; a seleção voltar vazia ou sem o vinho que o comensal citou (comparar, pergunta sobre um vinho); qualquer dado que muda a cada consulta (hora, id da consulta, sessão) entrar no início do prompt e anular o cache; o custo gravado ficar acima ou abaixo do real por causa do cache; carta de restaurante A aparecer no prompt do B; quebrar a ordem/numeração dos testes existentes sem registrar.

## 4. Decisões do Rafael

- Abordagem **B**: cache primeiro; carta inteira até 60 vinhos; acima, seleção simples de 40, sem segunda chamada à IA.
- O limite de rótulos por plano sai nesta fase (o estudo já previa).
- Cartas atuais: no máximo ~50 vinhos.

## 5. Abordagem

Três ideias foram comparadas: **A** atalho de 40 como no estudo (trava o custo, mas é a parte mais complexa e quase nunca roda para o público atual), **B** cache primeiro com teto de 60 e seleção só acima disso (escolhida) e **C** só cache (cartas grandes seguem caras). Escolhida B: a Sofia vê a carta inteira nos casos reais, o custo cai pelo cache e a seleção fica como rede de segurança.

## 6. Comportamento

**Prompt estável.** O prompt de sistema continua começando pelo texto fixo da Sofia, com o nome do restaurante e depois a carta; a pergunta do comensal vai só na mensagem do usuário. A carta é montada com os vinhos disponíveis **ordenados por `id`** e em **JSON compacto** (sem indentação e sem campos nulos ou vazios) **[CALL]**: menos tokens e ordem determinística. Nada que varie por consulta entra no início. Mudar a carta muda o prompt e perde o cache uma vez; isso é esperado.

**Cache e custo.** `AiResponse` ganha `tokensCached` (lido de `usage.prompt_tokens_details.cached_tokens`, 0 se o campo não vier); `ai_usage` ganha `tokens_cached` (inteiro, padrão 0); `config/ai_pricing.php` ganha o preço de entrada em cache por modelo (US$ 0,075 por milhão para o `gpt-oss-120b`). O custo é `(tokens_in − tokens_cached) × preço_in + tokens_cached × preço_cache + tokens_out × preço_out`. `tokens_in` continua sendo o total de entrada (o cache é um subconjunto). Se a Groq não informar o campo, o custo segue no preço cheio (conservador). A primeira tarefa confirma o nome do campo com uma chamada real repetida.

**Carta no prompt.** `config('sofia.prompt_full_carta_max')` = 60 e `config('sofia.prompt_selection_size')` = 40. Até 60 vinhos disponíveis: todos, como acima. Acima de 60: seleção de 40 **[CALL]**, escolhida por pontuação simples e determinística, sem IA:

- vinhos que o pedido cita (comparar: os dois; pergunta sobre um vinho: esse) entram sempre e primeiro;
- pontos por tipo compatível (paladar: `color_preference`; prato: dica de tipo por palavras do prato, como peixe e frutos do mar para branco/espumante, carnes para tinto), por preço dentro da faixa pedida e por palavras do pedido que aparecem em harmonização, notas, nome e uvas;
- empate e preenchimento por `id`; se poucos pontuarem, completa até 40 por `id`;
- o resultado sai reordenado por `id`.

A Sofia continua instruída a recomendar apenas o que está na carta enviada; nada no texto diz que é uma seleção.

**Limite de rótulos.** Sai de `WineService::assertCanAdd`, da importação e da carta de exemplo; `config/plans.php` perde a chave e o `SubscriptionState` perde o campo; mensagens e textos da tela que citavam o limite saem. Nada que já exista é apagado.

## 7. Restrições

Hostinger compartilhada, sem cron novo. Suíte verde em SQLite **e** MySQL 8; isolamento A×B no prompt e na seleção; a migration da coluna é aditiva e segura com `ai_usage` já populada. Os testes existentes de limite de rótulos são trocados de propósito e registrados na story. Fluxo AIOX: story em `vinia-docs` (9.6), push/PR só do @devops.

## 8. Sucesso

Duas consultas seguidas do mesmo restaurante geram o mesmo início de prompt byte a byte; o custo gravado desconta os tokens em cache; uma carta de 50 vinhos vai inteira e uma de 300 envia 40 com os vinhos citados; ninguém é barrado por quantidade de rótulos; suíte verde.

## 9. Deixado ao construtor

Nomes de métodos e classes (por exemplo uma classe própria para a seleção), a lista exata de palavras-chave de prato e o formato do `price_range` aceito pela seleção (seguir o que o frontend já envia), os valores de configuração, textos de teste e a ordem das tarefas.
