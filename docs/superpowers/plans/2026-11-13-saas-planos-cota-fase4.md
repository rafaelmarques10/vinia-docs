# Vinia SaaS — Fase 4: Planos, trial com prazo, cota e consumo — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Encerrar o trial no prazo, limitar e medir a Sofia por plano (cota por ciclo), mostrar o consumo ao gestor com alertas e deixar o admin assinar restaurantes à mão.

**Architecture:** Duas tabelas novas: `subscriptions` (uma por restaurante, estado **derivado das datas ao ler** por `SubscriptionService::state()`) e `ai_usage` (uma linha por consulta, tokens de entrada e saída, custo; a cota usada é a soma no ciclo). Uma única porta `QuotaGate` antes de criar a consulta (tablet e celular). Todos os bloqueios leem o estado derivado, não `restaurants.active`. Sem cron novo.

**Tech Stack:** Laravel 13, Livewire 4, PHPUnit (SQLite em memória; CI também MySQL 8), notificações em fila (`database`).

**Spec:** `docs/superpowers/specs/2026-11-13-vinia-planos-cota-fase4-design.md` (e o estudo `2026-11-12-vinia-saas-precificacao.md`). Em conflito, vale o design da Fase 4.

## Global Constraints

- Caminhos relativos a `vinia-src`; código em `backend/`. Testes: `cd backend && php artisan test --filter=<Classe>`; suíte completa `php artisan test` (baseline 1160). SQLite **e** MySQL 8: nenhum teste usa aspas de identificador nem SQL de um banco só.
- Hostinger compartilhada: **sem Redis, sem `schedule:run`, sem worker contínuo; esta fase não cria cron novo.** Migrations retomáveis (`hasTable`/`hasColumn`; backfill fora do guard e idempotente); nada de `->change()`.
- `ai_usage`: **sem `device_id`** e **sem FK em cascata** para `comensal_sessions` nem `ai_interactions` (o expurgo LGPD da 9.3 não pode apagá-la); `restaurant_id` e `interaction_id` são colunas indexadas simples.
- Estado e cota **derivados ao ler**; todo ponto de bloqueio (middleware do backoffice, autenticação do tablet, rota pública, `QuotaGate`) lê `SubscriptionService`, nunca só `restaurants.active`.
- **Legado:** restaurante com `subscriptions.legacy = true` não tem cota nem limite de rótulos; todo restaurante existente nasce legado; restaurante novo (trial ou assinado no painel) nunca.
- Trial: **14 dias**, teto de **150 consultas**, limite de **100 rótulos**; depois do fim, **7 dias de carência** (carta visível, Sofia desligada) e então `ended` (página "teste encerrado", nada apagado). Cota de ciclo: **30 dias**, renova sozinho até o admin cancelar. Cancelado: mesma carência de 7 dias.
- Planos (`config/plans.php`): `starter` Início R$ 147, 500 consultas, 1 tablet, 100 rótulos; `standard` Pro R$ 297, 2.000, 3 tablets, 150 rótulos; `premium` Rede R$ 597, 6.000, 6 tablets, 150 rótulos; `trial` 150 consultas, 1 tablet, 100 rótulos. `TabletService::PLAN_LIMITS` passa a ler `config('plans')`.
- Consulta que falha: não gasta cota. Se falhar **depois** de o provedor cobrar, a linha de `ai_usage` fica com `counted = false` (custo real sim, cota não).
- Mensagens ao usuário em português com acentos; commits convencionais com `[Story 9.5]` e `Co-Authored-By`; só na branch de trabalho (`git branch --show-current`; nunca `checkout/switch/stash`); nunca `git push`. Telas com dado de restaurante usam o `restaurant_id` do usuário logado e têm teste A×B; consultas cruas entram no `RawQueryAuditTest::ALLOWED` com justificativa. Testes existentes só mudam quando o comportamento antigo foi trocado de propósito (lista no Dev Agent Record).
- Aviso: não editar `DEPLOY-HOSTINGER.md` (alterações do Rafael).

## Review Focus

1. **Cliente antigo bloqueado de surpresa:** restaurante legado (ou sem assinatura) nunca recebe `QUOTA_EXHAUSTED`, nunca é inativado nem limitado em rótulos (Task 2, 5, 6, 7).
2. **Corrida de requisições:** duas consultas simultâneas na última unidade da cota não passam muito acima dela; o ciclo vira exatamente no 30º dia (Task 2 e 5).
3. **Trial:** dia 14, carência de 7 dias e `ended` nas bordas (segundo exato), com `TrialService` e o estado derivado concordando; tablet recusa só em `ended` (Task 3 e 6).
4. **Custo:** consulta que falha antes e depois da cobrança do provedor; tokens zero/ausentes na resposta; modelo desconhecido em `ai_pricing` (Task 4).
5. **Isolamento e papéis:** consumo de A não aparece em B; sommelier não vê o consumo; `ai_usage` sobrevive ao `comensal-sessions:purge` (Task 8 e 9).

---

### Task 1: Dados e configuração

**Files:**
- Create: `backend/config/plans.php`, `backend/config/ai_pricing.php`, `backend/app/Models/Subscription.php`, `backend/app/Models/AiUsage.php`, migrations `2026_11_14_000001_create_subscriptions_table.php`, `2026_11_14_000002_create_ai_usage_table.php`
- Modify: `backend/app/Models/Restaurant.php` (`subscription()` hasOne), `backend/app/Services/TabletService.php`
- Test: `backend/tests/Feature/Migrations/PlansMigrationsTest.php`, `backend/tests/Unit/Models/SubscriptionTest.php`

**Interfaces:**
- Produces `config('plans')`: mapa `plano => ['label', 'price', 'quota', 'tablets', 'labels']` com os valores das Global Constraints e `'trial_days' => 14`, `'grace_days' => 7`, `'cycle_days' => 30`, `'cost_alert_ratio' => 0.30`.
- Produces `config('ai_pricing')`: `['usd_brl' => 5.5, 'models' => ['openai/gpt-oss-120b' => ['in' => 0.15, 'out' => 0.60]], 'default' => ['in' => 0.15, 'out' => 0.60]]` (US$ por milhão de tokens).
- Produces tabela `subscriptions`: `restaurant_id` (único, FK `cascadeOnDelete`), `plan` string, `status` string (`trial|active|canceled`), `legacy` boolean default false, `trial_started_at`, `trial_ends_at`, `cycle_started_at`, `canceled_at` (todos timestamp nullable), `quota_override` unsigned int nullable, `alert_80_cycle`, `alert_100_cycle`, `cost_alert_cycle` (timestamp nullable: o `cycle_started_at` do ciclo em que o aviso saiu), timestamps. Model `Subscription` **sem** `BelongsToRestaurant` (consultado por middlewares sem contexto), `$guarded = []`, casts de data e booleano.
- Produces tabela `ai_usage`: `id`, `restaurant_id` (índice, sem FK), `interaction_id` nullable (índice, sem FK), `provider` string 20, `model` string 80, `tokens_in`/`tokens_out` unsigned int, `cost_brl` decimal(12,6), `counted` boolean default true, `created_at` (índice composto `restaurant_id, created_at`). Model `AiUsage` com `BelongsToRestaurant`, sem `updated_at`.
- **Backfill (migration 000001, fora do guard, idempotente):** para cada restaurante sem assinatura: se existir `trial_claims` do restaurante, cria `status = trial`, `plan = trial`, `legacy = false`, `trial_started_at = claim.started_at`, `trial_ends_at = claim.ends_at` (e, se `ended_at` não for nulo, `trial_ends_at = ended_at`); senão cria `status = active`, `plan = restaurants.plan`, `legacy = true`, `cycle_started_at = now()`.

- [ ] **Step 1: Write the failing tests** — `PlansMigrationsTest`: tabelas e colunas existem; `ai_usage` **não** tem coluna `device_id` nem FK (`Schema::getForeignKeys('ai_usage')` vazio); backfill: restaurante criado à mão vira `active` + `legacy`; restaurante com `trial_claims` vira `trial` com as datas do claim (e `ended_at` encerra); rodar `up()` de novo não duplica; `down()` reverte. `SubscriptionTest`: `Restaurant::subscription` relaciona; `config('plans.standard.quota') === 2000`; `TabletService::PLAN_LIMITS['premium'] === 6` e `['trial'] === 1` vêm de `config('plans')`.
- [ ] **Step 2: Run** `--filter="PlansMigrations|SubscriptionTest"` → FAIL.
- [ ] **Step 3: Implement** migrations (o backfill usa `DB::table`, sem models), models, configs, relação e `TabletService::PLAN_LIMITS` lendo a config (a constante vira método/atributo calculado; manter `PLAN_LIMITS` como constante derivada **não** é possível com `config()`: troque os usos por `TabletService::limitFor(string $plan): int` e ajuste `RestaurantPlanList` e a view; o teste existente de limite de tablets segue verde).
- [ ] **Step 4: Run** a suíte completa → verde (se um teste fixar `TabletService::PLAN_LIMITS`, atualize-o deliberadamente e registre).
- [ ] **Step 5: Commit** `feat(backend): assinaturas, ai_usage e configuração de planos [Story 9.5]`.

### Task 2: `SubscriptionService` (estado derivado e cota)

**Files:**
- Create: `backend/app/Services/SubscriptionService.php`, `backend/app/Support/Plans/SubscriptionState.php`
- Test: `backend/tests/Feature/Plans/SubscriptionServiceTest.php`

**Interfaces:**
- Consumes: `Subscription`, `AiUsage`, `config('plans')`.
- Produces `SubscriptionState` (readonly): `string $status` (`trial|active|grace|ended`), `string $kind` (`trial|paid`), `bool $sofiaAllowed`, `bool $cartaAllowed`, `bool $restaurantUsable`, `?int $quota` (null = sem cota), `int $used`, `?CarbonImmutable $cycleStart`, `?CarbonImmutable $cycleEnd`, `bool $legacy`, `?int $labelLimit`.
- Produces `SubscriptionService::state(Restaurant $restaurant, ?CarbonInterface $at = null): SubscriptionState`. Regras: sem assinatura → tratado como **legado ativo** (defensivo). Legado → `active`, `quota = null`, `labelLimit = null`, tudo permitido. Trial: `now < trial_ends_at` → `trial` (quota = plans.trial.quota contada desde `trial_started_at`); até `+grace_days` → `grace` (`sofiaAllowed = false`, `cartaAllowed = true`, `restaurantUsable = true`); depois → `ended` (`restaurantUsable = false`, `cartaAllowed = false`). `canceled`: `grace` por `grace_days` a partir de `canceled_at`, depois `ended`. `active` não legado: ciclo corrente = `cycle_started_at + floor(dias/30)*30 dias` até `+30` (renovação automática), `quota = quota_override ?? plans[plan].quota`, `used` = soma de `ai_usage.counted = true` no ciclo. `sofiaAllowed = status in (trial, active) && (quota === null || used < quota)`.
- Produces `SubscriptionService::used(Restaurant, CarbonInterface $from, CarbonInterface $to): int`.

- [ ] **Step 1: Write the failing tests** — por estado: legado sem cota nem limite; restaurante sem assinatura = legado; trial no dia 13 (`trial`), no segundo exato do fim (`grace`), `fim + 7d` (`ended`); trial usa o teto 150 e o limite de rótulos 100; ativo `starter` com 499 usos → `sofiaAllowed`, com 500 → não; `counted = false` não soma; `quota_override` vence o plano; ciclo: no dia 29 ainda o ciclo 1, no dia 30 começa o ciclo 2 e `used` zera; cancelado: carência de 7 dias e depois `ended`; uso de outro restaurante não conta (A×B).
- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement** (consulta de soma com `where restaurant_id`, `counted` e faixa de datas; sem cache).
- [ ] **Step 4: Run** → PASS; suíte completa verde.
- [ ] **Step 5: Commit** `feat(backend): estado derivado da assinatura e cota do ciclo [Story 9.5]`.

### Task 3: Assinatura no ciclo de vida do trial

**Files:**
- Modify: `backend/app/Services/TrialService.php`, `backend/app/Services/SignupService.php` (se preciso), `backend/app/Livewire/Onboarding/Wizard.php` (só se necessário)
- Test: `backend/tests/Feature/Plans/TrialSubscriptionTest.php`

**Interfaces:**
- Consumes: `Subscription`, `TrialService::start/endBecauseCnpjUsed` (Fase 3).
- Produces: `TrialService::start()` cria (ou reaproveita) a `Subscription` do restaurante com `status = trial`, `plan = trial`, `trial_started_at`/`trial_ends_at` iguais às do claim, `legacy = false`; quando a trava bloqueia (claim nasce encerrado) a assinatura nasce com `trial_ends_at = now` e `trial_started_at = now`. `endBecauseCnpjUsed()` que encerra o teste também põe `trial_ends_at = now()` na assinatura (vira `grace`/`ended` pelo estado derivado). O claim continua sendo a trava contra reuso; **a assinatura é a fonte das datas** lidas pelo estado.

- [ ] **Step 1: Write the failing tests** — verificar o e-mail cria a assinatura `trial` com o fim em ~14 dias e `state()` = `trial`; cadastro bloqueado por trava (CPF já usado) nasce `ended`; CNPJ do passo 1 já usado encerra a assinatura; `start()` duas vezes não duplica; o restaurante do auto-cadastro NUNCA fica `legacy`; restaurante manual sem claim segue `active`/legado.
- [ ] **Step 2: Run** → FAIL. **Step 3: Implement.** **Step 4:** suíte completa verde (os testes de `TrialServiceTest`/`WizardTest` seguem verdes). **Step 5: Commit** `feat(backend): assinatura de trial criada pela verificação e encerrada pela trava [Story 9.5]`.

### Task 4: Medição (tokens de entrada e saída, custo)

**Files:**
- Create: `backend/app/Services/AiCostCalculator.php`, `backend/app/Services/AiUsageRecorder.php`
- Modify: `backend/app/DTOs/AiResponse.php`, `backend/app/Services/GroqService.php`, `backend/app/Services/GeminiService.php`, `backend/app/Jobs/ProcessAiRecommendationJob.php`
- Test: `backend/tests/Unit/Services/AiCostCalculatorTest.php`, `backend/tests/Feature/Plans/AiUsageRecordingTest.php`

**Interfaces:**
- Produces `AiResponse(string $content, int $tokensUsed, int $tokensIn = 0, int $tokensOut = 0)` (`tokensUsed` continua a soma; os dois serviços preenchem entrada/saída das respostas da API). `AiCostCalculator::costBrl(string $model, int $tokensIn, int $tokensOut): float` (`(in/1e6*priceIn + out/1e6*priceOut) * usd_brl`, modelo desconhecido usa `default`, tokens nulos = 0). `AiUsageRecorder::record(AiInteraction $interaction, string $provider, string $model, AiResponse $r, bool $counted = true): AiUsage`; `AiUsageRecorder::markUncounted(AiInteraction $interaction): void`.
- O job grava `ai_usage` **imediatamente depois** de `complete()` (provedor já cobrou), e, se a atualização da interação lançar depois disso, marca a linha `counted = false` no `catch`. Falha do provedor (exceção de `complete()`) não grava nada.

- [ ] **Step 1: Write the failing tests** — calculadora: 1.000 tokens de entrada e 500 de saída no modelo padrão = `(1000/1e6*0.15 + 500/1e6*0.60) * 5.5`; modelo desconhecido usa o padrão; zeros custam 0. Serviços: resposta fake da Groq/Gemini com `usage` devolve `tokensIn`/`tokensOut` separados e `tokensUsed` = soma; resposta sem `usage` = 0/0. Job: sucesso grava 1 linha (`tokens_in`, `tokens_out`, `cost_brl`, `counted = true`, `interaction_id`, `restaurant_id` da interação); falha do provedor (HTTP 500) não grava linha e a interação fica `failed`; falha **depois** do `complete()` (simule lançando no `update` da interação) deixa a linha com `counted = false`; reprocessar interação `done` não grava de novo (idempotência); a linha nunca carrega `device_id`.
- [ ] **Step 2: Run** → FAIL. **Step 3: Implement.** **Step 4:** suíte completa verde (testes de `GroqService`/`GeminiService`/job existentes seguem verdes; se um comparar `AiResponse` por igualdade, atualize deliberadamente). **Step 5: Commit** `feat(backend): medição de tokens de entrada e saída e custo por consulta [Story 9.5]`.

### Task 5: `QuotaGate` na criação da consulta

**Files:**
- Create: `backend/app/Services/QuotaGate.php`
- Modify: `backend/app/Http/Controllers/Api/AiInteractionController.php`, `backend/tests/Feature/Api/*` (somente se um teste fixar o comportamento antigo)
- Test: `backend/tests/Feature/Plans/QuotaGateTest.php`

**Interfaces:**
- Consumes: `SubscriptionService::state`.
- Produces `QuotaGate::check(Restaurant): ?array` devolvendo `null` (passa) ou `['status' => int, 'code' => string, 'message' => string]`: estado `grace`/`ended` → 403 `SOFIA_UNAVAILABLE` ("A Sofia está indisponível neste momento. Chame o nosso sommelier."); cota do ciclo/trial esgotada → 429 `QUOTA_EXHAUSTED` ("A Sofia atingiu o limite de consultas do restaurante neste período. Chame o nosso sommelier."); legado/sem cota → `null`. **Reserva contra corrida:** a checagem conta `ai_usage` **mais** as interações `pending|processing` do restaurante no ciclo (ainda sem linha em `ai_usage`), de modo que consultas em andamento ocupam a cota; a margem aceita é só a de requisições exatamente simultâneas.
- O controller chama o gate **depois** dos tetos existentes (rajada, sessão, diário do celular) e **antes** de montar o prompt e criar a `AiInteraction`; vale para tablet e celular.

- [ ] **Step 1: Write the failing tests** — trial com 150 usos recusa a 151ª com `QUOTA_EXHAUSTED` e **nenhuma** `AiInteraction` criada; `starter` ativo com 500; interações `pending` contam como ocupadas; `counted = false` não conta; `grace` e `ended` recusam com `SOFIA_UNAVAILABLE` (403); legado nunca recusa mesmo com 10.000 usos; tablet e celular (restaurante assinado) recebem o mesmo; teto por sessão/rajada continuam vindo antes (códigos existentes intactos); a carta (`GET /api/v1/wines`) segue 200 em `grace`.
- [ ] **Step 2: Run** → FAIL. **Step 3: Implement.** **Step 4:** suíte completa verde. **Step 5: Commit** `feat(backend): porta de cota da Sofia no tablet e no celular [Story 9.5]`.

### Task 6: Bloqueios leem o estado derivado

**Files:**
- Modify: `backend/app/Http/Middleware/EnsureRestaurantUsable.php`, `backend/app/Http/Middleware/TabletAuthentication.php`, `backend/app/Http/Middleware/ResolvePublicRestaurant.php`, `backend/resources/views/backoffice/trial-ended.blade.php`
- Test: `backend/tests/Feature/Plans/DerivedStateBlockingTest.php`

**Interfaces:**
- Consumes: `SubscriptionService::state` (`restaurantUsable`, `cartaAllowed`).
- Comportamento: `TabletAuthentication` recusa (401 igual a token inválido) quando `restaurants.active = false` **ou** `state.restaurantUsable = false`; em `grace` o tablet autentica (carta visível). `ResolvePublicRestaurant` idem para a carta pública (404 quando não utilizável). `EnsureRestaurantUsable` redireciona o dono/gerente/sommelier **verificado** de restaurante `ended` (qualquer causa: trial vencido, cancelado) a `backoffice.trial.ended`, sem depender de `restaurants.active` nem de `trial_claims`; em `grace` o backoffice segue aberto, com **faixa** "Seu teste/assinatura terminou: a Sofia está desligada" (partial incluído nos dois layouts). A página "teste encerrado" mostra texto próprio para cancelado ("Sua assinatura foi encerrada…"). Admin e legado nunca são afetados.

- [ ] **Step 1: Write the failing tests** — trial vencido há 8 dias: tablet 401, carta pública 404, dono redirecionado; vencido há 3 dias (`grace`): tablet 200 na carta, Sofia 403, dono entra e vê a faixa; cancelado há 3 e há 8 dias; legado e restaurante manual nunca bloqueados; usuário não verificado não é redirecionado (mantém a regra da Fase 3); ação do Livewire (`default-livewire.update`) de dono em `ended` é redirecionada; sem `trial_claims`, o cancelado `ended` também é redirecionado.
- [ ] **Step 2: Run** → FAIL. **Step 3: Implement.** **Step 4:** suíte completa verde (os testes `InactiveRestaurantTest` da Fase 3 seguem verdes; se algum fixar a leitura do claim, atualize deliberadamente). **Step 5: Commit** `feat(backend): bloqueios leem o estado derivado da assinatura [Story 9.5]`.

### Task 7: Limite de rótulos por plano

**Files:**
- Modify: `backend/app/Services/WineService.php`, `backend/app/Services/WineImportService.php`, `backend/app/Livewire/WineForm.php`, `backend/app/Livewire/WineImport.php`
- Test: `backend/tests/Feature/Plans/LabelLimitTest.php`

**Interfaces:**
- Produces `WineService::assertCanAdd(Restaurant, int $adding = 1): void` lançando `\DomainException('Seu plano permite até N rótulos. Fale com a gente para trocar de plano.')` quando `contagem atual + $adding > state.labelLimit` (rótulos = vinhos não excluídos, **inclui** os de exemplo). Legado e sem limite: nunca lança. A importação processa linha a linha: acima do limite as linhas novas viram erros no `ImportResult` ("limite de rótulos do plano") e as que atualizam vinho existente continuam passando. O limite **nunca apaga nem esconde** vinho existente.

- [ ] **Step 1: Write the failing tests** — trial com 100 vinhos recusa o 101º (`WineForm` mostra a mensagem); `starter` 100, `standard` 150; legado com 500 vinhos adiciona sem erro; importação de 120 linhas em restaurante `starter` com 90 vinhos importa 10 e reporta 20 erros; atualizar vinho existente acima do limite funciona; carta de exemplo (10 vinhos) conta; excluir vinho libera vaga; rebaixar de plano com 200 vinhos mantém os 200 visíveis e só bloqueia novos; A×B.
- [ ] **Step 2: Run** → FAIL. **Step 3: Implement.** **Step 4:** suíte completa verde. **Step 5: Commit** `feat(backend): limite de rótulos por plano sem esconder vinho existente [Story 9.5]`.

### Task 8: Consumo (serviço e tela)

**Files:**
- Create: `backend/app/Services/ConsumptionService.php`, `backend/app/Livewire/Consumption.php`, `backend/resources/views/livewire/consumption.blade.php`
- Modify: `backend/routes/web.php` (`backoffice.consumption`, `GET /backoffice/consumo`, `can:manage-team`), layouts do backoffice (item "Consumo" para dono e gerente)
- Test: `backend/tests/Feature/Plans/ConsumptionTest.php`, `backend/tests/Feature/Isolation/ConsumptionIsolationTest.php`

**Interfaces:**
- Consumes: `SubscriptionService::state`, `AiUsage`.
- Produces `ConsumptionService::forRestaurant(Restaurant, ?CarbonInterface $at = null): array` com `['quota' => ?int, 'used' => int, 'percent' => ?int, 'cycle_start', 'cycle_end', 'days_left' => ?int, 'today' => int, 'week' => int, 'month' => int, 'daily' => [data => int] (últimos 14 dias), 'status' => string]`; conta só `counted = true`. A tela mostra um medidor (barra com `role="progressbar"`, texto "X de Y consultas"), os números de hoje, semana e mês, o fim do ciclo e, para legado, "Sem limite de consultas". **Sommelier não acessa** (403); admin não tem restaurante (403 como as demais telas de restaurante).

- [ ] **Step 1: Write the failing tests** — contagens por dia/semana/mês e `percent`; `counted = false` ignorado; legado mostra sem cota; trial mostra 150; A×B (uso do restaurante B não aparece; payload Livewire não aceita id); sommelier 403, dono e gerente 200; item de menu só para quem pode; tela passa pela guarda `ThemeViewsTest` (só tokens `bo-*`).
- [ ] **Step 2: Run** → FAIL. **Step 3: Implement.** **Step 4:** suíte completa verde. **Step 5: Commit** `feat(backend): painel de consumo da Sofia [Story 9.5]`.

### Task 9: Alertas de cota e de custo

**Files:**
- Create: `backend/app/Services/QuotaAlertService.php`, `backend/app/Notifications/QuotaAlertNotification.php`, `backend/app/Notifications/CostAlertNotification.php`, `backend/resources/views/backoffice/partials/quota-banner.blade.php`
- Modify: `backend/app/Services/AiUsageRecorder.php` (chama o serviço de alertas depois de gravar), layouts do backoffice (inclui a faixa)
- Test: `backend/tests/Feature/Plans/QuotaAlertTest.php`

**Interfaces:**
- Produces `QuotaAlertService::check(Restaurant): void`: ao cruzar **80%** e **100%** da cota do ciclo (ou do trial), notifica o dono (fila) **uma vez por ciclo e por limiar** (grava `alert_80_cycle`/`alert_100_cycle` = `cycle_started_at` do ciclo); legado e sem cota nunca alertam. Alerta interno: quando o custo (`SUM(cost_brl)`, inclui `counted = false`) do ciclo passar de `cost_alert_ratio` do preço do plano, `Log::warning` e `Notification::route('mail', config('onboarding.contact_email'))` uma vez por ciclo (`cost_alert_cycle`); trial usa o preço do plano `starter` como referência. A faixa no backoffice (dono/gerente) aparece a partir de 80% e some no ciclo seguinte.

- [ ] **Step 1: Write the failing tests** — `Notification::fake()`: 399 usos = nada; o 400º (80% de 500) envia ao dono; repetir não reenvia; o 500º envia o de 100%; novo ciclo reenvia; legado nunca; trial alerta em 120 e 150; custo acima de 30% do preço envia o alerta interno uma vez por ciclo e `counted = false` entra na soma; faixa aparece para dono e some para sommelier; a notificação não carrega e-mail de cliente final nem texto de consulta.
- [ ] **Step 2: Run** → FAIL. **Step 3: Implement.** **Step 4:** suíte completa verde. **Step 5: Commit** `feat(backend): alertas de cota (80% e 100%) e de custo [Story 9.5]`.

### Task 10: Admin assina o restaurante

**Files:**
- Modify: `backend/app/Livewire/RestaurantPlanList.php`, `backend/resources/views/livewire/restaurant-plan-list.blade.php`
- Create: `backend/app/Services/SubscriptionAdminService.php`
- Test: `backend/tests/Feature/Backoffice/SubscriptionAdminTest.php`

**Interfaces:**
- Produces `SubscriptionAdminService::subscribe(User $actor, Restaurant $restaurant, string $plan, ?CarbonInterface $cycleStart = null): Subscription` (cria/atualiza: `status = active`, `plan`, `legacy = false`, `cycle_started_at = $cycleStart ?? now()`, `canceled_at = null`, atualiza `restaurants.plan` e `active = true`), `cancel(User, Restaurant): void` (`status = canceled`, `canceled_at = now()`), `setLegacy(User, Restaurant, bool): void`, `setQuotaOverride(User, Restaurant, ?int): void`. Todos reautorizam `manage-plans` (só admin) e auditam no canal `audit` só com ids. Trocar de plano no meio do ciclo mantém `cycle_started_at` e aplica a cota nova. A tela de planos mostra, por restaurante: estado, plano, fim do ciclo/do trial, consultas usadas/cota, custo do ciclo, marca legado e as ações acima. Plano `trial` não é escolhível pelo admin (some da lista de planos assináveis).

- [ ] **Step 1: Write the failing tests** — só admin (dono recebe 403 em cada ação); `subscribe` cria assinatura ativa não legado com ciclo agora, liga o restaurante e zera `canceled_at`; mudar de plano mantém o ciclo; `cancel` leva a `grace` e depois `ended`; `setLegacy(false)` passa a aplicar a cota; `setQuotaOverride` vale; a lista mostra uso e custo do ciclo; plano `trial` não aparece; ação com id de restaurante inexistente dá 404; auditoria sem e-mail.
- [ ] **Step 2: Run** → FAIL. **Step 3: Implement.** **Step 4:** suíte completa verde (`RestaurantPlanTest` da fase anterior segue verde ou é atualizado deliberadamente). **Step 5: Commit** `feat(backend): admin assina, cancela e define cota por restaurante [Story 9.5]`.

### Task 11: Mensagens no frontend (tablet e celular)

**Files:**
- Modify: `frontend/src/pages/AssistantPage.tsx`, `frontend/src/services/phoneSession.ts` (só se o tipo de código exigir)
- Test: `frontend/src/pages/AssistantPage.test.tsx`, `frontend/src/pages/AssistantPage.phone.test.tsx`

**Interfaces:**
- O frontend trata os códigos novos de `POST /ai/recommend`: `QUOTA_EXHAUSTED` ("A Sofia atingiu o limite de consultas do restaurante neste período. Chame o nosso sommelier.") e `SOFIA_UNAVAILABLE` ("A Sofia está indisponível neste momento. Chame o nosso sommelier."), sem repetir a consulta e sem encerrar a carta (a conversa mostra a mensagem e o resto do app segue). Mesmo texto da API (sem inventar).

- [ ] **Step 1: Write the failing tests** — com `api.recommend` rejeitando 429 `QUOTA_EXHAUSTED` e 403 `SOFIA_UNAVAILABLE`, a tela mostra a mensagem certa, não repete a chamada e permite voltar; no celular o retry de 401 não dispara para esses códigos; o tablet segue idêntico para os demais erros.
- [ ] **Step 2: Run** `cd frontend && npm test -- --run src/pages` → FAIL. **Step 3: Implement.** **Step 4:** `npm test -- --run && npm run typecheck && npm run lint` verdes (741 + novos). **Step 5: Commit** `feat(frontend): mensagens de cota esgotada e Sofia indisponível [Story 9.5]`.

### Task 12: Fecho (controlador)

Não é tarefa de implementador. O controlador: suíte completa em SQLite **e** num MySQL 8 descartável; frontend; ponta a ponta no Chromium (trial no dia 14 com Sofia desligando e carência de 7 dias com a carta visível; cota esgotando no tablet; consumo e alertas; admin assinando e cancelando; legado intocado; `ai_usage` sobrevive ao `comensal-sessions:purge`); revisão final da branch (opus) com **uma** onda de correção; story 9.5, cofre e grafo; **perguntar ao Rafael** antes do merge na `main`. Na story, para o Rafael: tirar a marca "legado" de cada cliente antigo depois de combinar valores; conferir `config/ai_pricing.php` (câmbio e preços do modelo); a **Fase 4b** (atalho de ≤ 40 vinhos e cache de entrada) vem depois e remove o limite de rótulos.
