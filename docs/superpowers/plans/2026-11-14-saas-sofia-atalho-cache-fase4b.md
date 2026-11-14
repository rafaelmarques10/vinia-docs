# Fase 4b — prompt estável, cache de entrada e atalho de seleção — Plano de Implementação

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A Sofia recebe um prompt estável (cache da Groq acerta), o custo desconta os tokens em cache, cartas acima de 60 vinhos viram uma seleção de 40 e o limite de rótulos por plano deixa de existir.

**Architecture:** `GroqService` monta a carta ordenada por `id` em JSON compacto; uma classe `WineSelector` decide quais vinhos entram (todos até 60, senão 40 por pontuação determinística); o controller guarda o pedido bruto em `ai_interactions.raw_input` para o job usar na seleção e o job o apaga ao terminar; `ai_usage.tokens_cached` e `ai_pricing.cached_in` alimentam o custo; o limite de rótulos é removido de `WineService`, `SubscriptionState` e `config/plans.php`.

**Tech Stack:** Laravel 13, PHPUnit (SQLite memória; CI MySQL 8), Groq `openai/gpt-oss-120b`. Backend em `vinia-src/backend`.

**Spec:** `vinia-docs/docs/superpowers/specs/2026-11-14-vinia-sofia-atalho-cache-fase4b-design.md` (aprovado). Contexto: Story 9.5 (mergeada local na `main`), estudo `2026-11-12-vinia-saas-precificacao.md`. Story desta fase: **9.6**, escrita no fim (Task 5).

## Global Constraints

- Carta no prompt: vinhos `available` do restaurante, **ordenados por `id`**, JSON **compacto** (sem indentação, sem campos nulos ou vazios); nada que varie por consulta no início do prompt.
- Teto: `config('sofia.prompt_full_carta_max')` = **60**; acima, seleção de `config('sofia.prompt_selection_size')` = **40**, sem segunda chamada à IA.
- Preço de entrada em cache do `openai/gpt-oss-120b`: **US$ 0,075 por milhão** (`cached_in`); entrada normal 0,15; saída 0,60.
- Custo: `(tokens_in − tokens_cached) × in + tokens_cached × cached_in + tokens_out × out`; `tokens_in` é o total de entrada; campo ausente = 0 cache (preço cheio).
- Limite de rótulos sai por completo (trial incluso). Nada existente é apagado.
- `raw_input` é apagado (`null`) quando o job termina, com sucesso ou falha.
- Sem cron novo; suíte verde em SQLite **e** MySQL 8; isolamento A×B; migrations aditivas.
- Commits em português, convencionais, `[Story 9.6]`, terminando com `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>`. Sem push.
- Comando de teste: `cd backend && php artisan test --compact [--filter=...]`.

## Review Focus

- Carta com exatamente 60 vinhos (tudo) e com 61 (seleção de 40): fronteira testada na Task 3.
- Vinho `available = false` e vinho de outro restaurante nunca entram, nem na carta inteira nem na seleção (Tasks 2 e 3).
- Resposta da Groq sem `prompt_tokens_details`, ou com `cached_tokens` maior que `prompt_tokens`: custo nunca negativo (Task 1).
- Comparar e pergunta sobre um vinho com o vinho citado fora das primeiras posições de uma carta grande: ele entra sempre (Task 3).
- Pedido com maiúsculas e acentos (“Salmão”, “PEIXE”) e restaurante sem nenhum vinho disponível (lista `[]`, sem erro) (Tasks 2 e 3).

---

### Task 1: Custo com tokens em cache

**Files:**
- Create: `backend/database/migrations/2026_11_15_000001_add_tokens_cached_to_ai_usage.php`
- Modify: `backend/app/DTOs/AiResponse.php`, `backend/app/Services/GroqService.php` (método `complete`), `backend/app/Models/AiUsage.php`, `backend/config/ai_pricing.php`, `backend/app/Services/AiCostCalculator.php`, `backend/app/Services/AiUsageRecorder.php`
- Test: `backend/tests/Unit/Services/AiCostCalculatorTest.php`, `backend/tests/Feature/Plans/AiUsageCachedTest.php` (novo)

**Interfaces:**
- Produces: `AiResponse::$tokensCached` (int, padrão 0, último parâmetro do construtor); `AiCostCalculator::costBrl(string $model, int $tokensIn, int $tokensOut, int $tokensCached = 0): float`; coluna `ai_usage.tokens_cached` (unsigned int, padrão 0, fillable).

- [ ] **Step 1: testes que falham.** Em `AiCostCalculatorTest`: com `gpt-oss-120b`, `costBrl(m, 10000, 500, 8000)` é menor que `costBrl(m, 10000, 500, 0)` e igual a `((2000×0.15 + 8000×0.075)/1e6 + 500×0.60/1e6) × usd_brl`; `tokensCached` maior que `tokensIn` é limitado a `tokensIn` (custo nunca negativo); modelo desconhecido sem `cached_in` usa o preço de entrada normal para o cache. Em `AiUsageCachedTest`: `Http::fake` da Groq com `usage.prompt_tokens=1000, completion_tokens=100, prompt_tokens_details.cached_tokens=800` → `complete()` devolve `tokensCached = 800`; sem `prompt_tokens_details` → 0; `AiUsageRecorder::record` grava `tokens_cached` e o custo reduzido.
- [ ] **Step 2: rodar e ver falhar.** `php artisan test --compact --filter='AiCostCalculatorTest|AiUsageCachedTest'`. Expected: FAIL (parâmetro/coluna inexistentes).
- [ ] **Step 3: implementar.** Migration aditiva (`unsignedInteger('tokens_cached')->default(0)` depois de `tokens_out`); `AiResponse` ganha `int $tokensCached = 0`; `GroqService::complete` lê `usage.prompt_tokens_details.cached_tokens`; `config/ai_pricing.php` ganha `'cached_in' => 0.075` no modelo e no `default`; `AiCostCalculator` aplica a fórmula das Global Constraints com o limite `min($tokensCached, $tokensIn)`; `AiUsageRecorder` passa e grava `tokens_cached`.
- [ ] **Step 4: rodar e ver passar** (mesmo filtro). Expected: PASS.
- [ ] **Step 5: commit** `feat(backend): custo da IA desconta tokens de entrada em cache [Story 9.6]`.

### Task 2: Prompt estável

**Files:**
- Modify: `backend/app/Services/GroqService.php` (`buildSystemPrompt`, `buildWinesJson`), `backend/tests/Feature/Api/AiInteractionTest.php` (asserções do JSON compacto, linhas ~42-75 e ~392)
- Test: `backend/tests/Feature/Plans/StablePromptTest.php` (novo)

**Interfaces:**
- Consumes: nada novo.
- Produces: `GroqService::buildSystemPrompt(Restaurant $restaurant, ?Collection $wines = null): string` (quando `$wines` é nulo, usa os vinhos disponíveis do restaurante ordenados por `id`); `buildWinesJson(Collection $wines): string` compacto, sem chaves cujo valor seja `null`, `''` ou `[]`.

- [ ] **Step 1: testes que falham.** `StablePromptTest`: (a) duas chamadas de `buildSystemPrompt` para o mesmo restaurante são idênticas byte a byte, mesmo criando os vinhos fora de ordem; (b) o JSON não contém quebras de linha de indentação nem `null`; um vinho sem `tasting_notes` não tem a chave; (c) vinho `available = false` e vinho de outro restaurante não aparecem; (d) restaurante sem vinhos gera `[]` sem erro; (e) com `Http::fake` e dois `ProcessAiRecommendationJob` de entradas diferentes do mesmo restaurante, o `messages[0].content` enviado é idêntico nas duas requisições.
- [ ] **Step 2: rodar e ver falhar.** `php artisan test --compact --filter=StablePromptTest`. Expected: FAIL (ordem indefinida e JSON com indentação).
- [ ] **Step 3: implementar** `->orderBy('id')` na busca, `json_encode` sem `JSON_PRETTY_PRINT` e filtro de valores vazios por vinho; ajustar as asserções antigas de `AiInteractionTest` que dependiam de indentação ou de chaves nulas, registrando a mudança no commit.
- [ ] **Step 4: rodar** `--filter='StablePromptTest|AiInteractionTest'`. Expected: PASS.
- [ ] **Step 5: commit** `feat(backend): carta do prompt da Sofia em ordem fixa e JSON compacto [Story 9.6]`.

### Task 3: Seleção de vinhos para cartas grandes

**Files:**
- Create: `backend/app/Services/WineSelector.php`, `backend/database/migrations/2026_11_15_000002_add_raw_input_to_ai_interactions.php`
- Modify: `backend/config/sofia.php` (`prompt_full_carta_max` = 60, `prompt_selection_size` = 40, ambos por env), `backend/app/Models/AiInteraction.php` (fillable e cast `array` de `raw_input`), `backend/app/Http/Controllers/Api/AiInteractionController.php` (grava `raw_input` ao criar), `backend/app/Jobs/ProcessAiRecommendationJob.php`, `backend/app/Services/GroqService.php` (`buildSystemPrompt` aceita o contexto)
- Test: `backend/tests/Unit/Services/WineSelectorTest.php`, `backend/tests/Feature/Plans/PromptSelectionTest.php` (novos)

**Interfaces:**
- Consumes: `buildSystemPrompt(Restaurant, ?Collection $wines)` e `buildWinesJson` da Task 2.
- Produces: `WineSelector::select(Collection $available, string $type, array $input): Collection` (devolve todos se `count ≤ prompt_full_carta_max`; senão `prompt_selection_size` vinhos, ordenados por `id`); coluna `ai_interactions.raw_input` (json, nulo); o job chama `$service->buildSystemPrompt($restaurant, $selector->select($available, $interaction->type, $interaction->raw_input ?? []))`.

Regras da seleção (acima de 60): vinhos citados entram sempre primeiro (`compare`: `wine_a_id` e `wine_b_id`; `about_wine`: `wine_id`); pontos por tipo compatível (`recommend_palate`: `color_preference`, `surpresa` não pontua; `recommend_dish`: dica por palavras do prato, ex. peixe, salmão, bacalhau, camarão, frutos do mar, ostra, sushi → branco, espumante, rosé; carne, churrasco, costela, picanha, cordeiro, bife, feijoada → tinto; usar os valores de `type` do `Wine`), por preço dentro de `price_range` (`0-200`, `200-500`, `500-1000`, `1000+`) e por palavras do pedido (`dish`, `question`) presentes em `pairings`, `tasting_notes`, `name` e uvas; comparação sem acento nem caixa; empate e preenchimento por `id`.

- [ ] **Step 1: testes que falham.** `WineSelectorTest`: 60 vinhos → os 60; 61 → exatamente 40; resultado ordenado por `id`; determinístico (duas chamadas iguais); `compare` com vinhos de `id` alto em carta de 100 → ambos presentes; `about_wine` idem; `recommend_palate` com `tinto` e `200-500` em carta com 70 brancos e 30 tintos → os tintos dessa faixa entram; `recommend_dish` com "Salmão" e "PEIXE" puxa brancos/espumantes; poucos pontuados → completa por `id`; nunca vazio. `PromptSelectionTest`: com `Http::fake`, carta de 100 vinhos disponíveis e a interação criada pelo controller (`POST` com tipo `compare`) → o corpo enviado à Groq contém os dois vinhos citados e no máximo 40 entradas; `raw_input` é `null` depois do job (sucesso e falha); carta de 50 vai inteira; vinho de outro restaurante e indisponível nunca aparecem.
- [ ] **Step 2: rodar e ver falhar.** `--filter='WineSelectorTest|PromptSelectionTest'`. Expected: FAIL (classe e coluna inexistentes).
- [ ] **Step 3: implementar** a migration aditiva, o seletor puro (sem I/O além dos vinhos recebidos, com `grapes` já carregado), a gravação de `raw_input` no `store` do controller (`'raw_input' => $request->input`), o uso no job com limpeza de `raw_input` nos dois ramos finais e a config.
- [ ] **Step 4: rodar** `--filter='WineSelectorTest|PromptSelectionTest|AiInteractionTest|StablePromptTest'`. Expected: PASS.
- [ ] **Step 5: commit** `feat(backend): carta inteira até 60 vinhos e seleção de 40 acima disso [Story 9.6]`.

### Task 4: Remover o limite de rótulos

**Files:**
- Modify: `backend/app/Services/WineService.php` (remove `assertCanAdd` e a chamada em `create`), `backend/app/Support/Plans/SubscriptionState.php` (remove `labelLimit` e o comentário), `backend/app/Services/SubscriptionService.php` (remove o argumento posicional e `labels()`), `backend/config/plans.php` (remove `labels` e o comentário), e os `catch (\DomainException)` de `WineForm`, `WineImportService` e `SampleCartaService` só se nada mais os lançar
- Test: `backend/tests/Feature/Plans/LabelLimitTest.php` (substituir por `NoLabelLimitTest.php`), `backend/tests/Feature/Plans/SubscriptionServiceTest.php`, `backend/tests/Feature/Plans/ReviewFixes95Test.php`

**Interfaces:**
- Consumes: nada.
- Produces: `SubscriptionState` sem `labelLimit`; atenção ao reordenar os argumentos posicionais de `new SubscriptionState(...)` em `SubscriptionService` (linhas ~32, 49, 60, 73, 78).

- [ ] **Step 1: testes que falham.** `NoLabelLimitTest`: trial, `starter` e `standard` com 200 vinhos criam mais um por `WineService::create`, por importação e por `SampleCartaService`, sem exceção, e nenhum vinho existente muda; legado igual. Remover de `SubscriptionServiceTest` e `ReviewFixes95Test` as asserções de `labelLimit` (100/150/null) trocando-as por `assertFalse(property_exists(SubscriptionState::class, 'labelLimit'))`.
- [ ] **Step 2: rodar e ver falhar.** `--filter='NoLabelLimitTest'`. Expected: FAIL (limite de 100 ainda barra).
- [ ] **Step 3: implementar a remoção** e procurar sobras: `grep -rn "labelLimit\|plans\.\(plans\.\)\?.*labels\|permite até" backend/app backend/config backend/resources backend/lang frontend/src` não pode retornar nada.
- [ ] **Step 4: rodar a suíte inteira.** `php artisan test --compact`. Expected: PASS sem falha nova; qualquer teste antigo que dependia do limite é trocado de propósito e anotado no commit.
- [ ] **Step 5: commit** `feat(backend): remove o limite de rótulos por plano [Story 9.6]`.

### Task 5: Verificação e registro

**Files:**
- Create: `vinia-docs/docs/stories/9.6.story.md`
- Modify: cofre Obsidian (Status e Índice Vinia, Índice Mestre, decisão de planos), `backend/config/ai_pricing.php` se a chamada real mostrar outro nome de campo

- [ ] **Step 1: chamada real da Groq (se `GROQ_API_KEY` existir no `.env` de desenvolvimento).** Duas consultas seguidas com o mesmo prompt de sistema longo (≥ 1.100 tokens) e conferir se `usage.prompt_tokens_details.cached_tokens` vem na segunda. Registrar o resultado na story; sem chave, registrar "não verificado" e a instrução para o Rafael conferir no primeiro deploy.
- [ ] **Step 2: suítes.** Backend em SQLite e em MySQL 8 (um contêiner descartável por rodada), frontend `npm test`. Expected: tudo verde.
- [ ] **Step 3: revisão final** do branch inteiro por subagente opus e ponta a ponta (carta de 50 e de 100 vinhos pelo tablet, comparar com vinho de `id` alto, custo em `ai_usage` com `tokens_cached`), corrigindo Critical e Important em uma onda, cada um com teste vermelho antes.
- [ ] **Step 4: story 9.6** (ACs, rulings, backlog, "para publicar"), atualização do cofre e `/graphify . --update`.
- [ ] **Step 5: commits finais** e parar: merge e push só com autorização do Rafael.
