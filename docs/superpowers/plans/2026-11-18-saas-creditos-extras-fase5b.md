# Créditos extras de consultas (Fase 5b, Story 9.8) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** O dono com plano ativo compra pacotes pré-pagos de 500 consultas pelo Asaas; o saldo passa de mês, é gasto depois da cota do plano e a Sofia só consome crédito pago.

**Architecture:** Nova tabela `credit_purchases` (compras e cortesias) e marca `ai_usage.from_credit`; saldo derivado (`créditos creditados − consultas counted e from_credit`). O pacote é uma cobrança avulsa no Asaas (nova operação `createPayment` no `PaymentGateway`); o webhook da 5a reconhece a cobrança pelo id em `credit_purchases` e credita uma única vez. `QuotaGate` continua a única porta e passa a liberar até `cota + saldo`.

**Tech Stack:** Laravel 13, Livewire 4, PHPUnit (SQLite em memória e MySQL 8), Asaas API v3 (sandbox), `FakeGateway` nos testes.

**Spec:** `vinia-docs/docs/superpowers/specs/2026-11-18-vinia-creditos-extras-fase5b-design.md` (e, como base, `2026-11-14-vinia-cobranca-asaas-fase5a-design.md`). Todo caminho de código abaixo é relativo a `vinia-src/backend`.

## Global Constraints

- Branch nova `feat/creditos-extras-fase5b-9.8` a partir da `main` local (`07b3aef`); commits convencionais em português com `[Story 9.8]` e o trailer `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>`. Sem `git push` (só @devops) e sem merge sem escolha explícita do Rafael.
- Pacote: **500 consultas**; preço **R$ 49,00**, ou **R$ 79,00** quando a carta tem **mais de 200** vinhos não removidos; aviso de saldo baixo em **100 consultas ou menos**. Todos esses valores ficam em `config/billing.php` (chave `credits`), nunca no código.
- Só o dono compra (gate `manage-billing`), só com assinatura gerida pelo gateway, estado `active` e plano com cota. Teste, carência, encerrada e legado: recusa com mensagem clara.
- Saldo não expira nem zera; fica congelado fora de `active` e volta a valer quando a assinatura volta a `active`. Sem reembolso automático. O gate ignora o saldo fora de `active`.
- Cobrança de pacote nunca altera `paid_through`, `plan`, `status` nem `cycle_started_at`.
- Segurança: nada de CPF, CNPJ, cartão, chave da API ou token em log ou tabela; auditoria só com ids (`Log::channel('audit')`); isolamento A×B em saldo, compras e webhook.
- Sem cron novo. Suíte verde em SQLite **e** MySQL 8 (container descartável na porta 3327; env `DB_CONNECTION=mysql DB_HOST=127.0.0.1 DB_PORT=3327 DB_DATABASE=vinia_test DB_USERNAME=root DB_PASSWORD=secret`).
- TDD: cada teste nasce vermelho, e a vermelhidão é lida antes do código. Comandos rodam em `vinia-src/backend`.

## Review Focus

Entradas e condições que o spec implica e nenhuma tarefa exercita por si só; cada linha tem o teste na tarefa dona:

1. Pacote pago **depois** de a assinatura ser cancelada ou encerrada: credita o saldo, não toca em `paid_through`/`status`, e a Sofia segue bloqueada (Task 5).
2. O mesmo pagamento chegando em dois avisos com `event_id` diferentes (reenvio, ou webhook e sincronização ao mesmo tempo): credita uma vez só (Task 5).
3. Consultas em andamento disputando o último crédito: `used + inFlight >= cota + saldo` bloqueia a seguinte (Task 3).
4. Consulta dentro da cota que falha e sai da contagem enquanto outra já gastou crédito: o saldo volta (Task 3).
5. Fronteira de preço: 200 vinhos = R$ 49, 201 = R$ 79, vinho removido (soft delete) não conta, e `pending` de preço antigo é fechada e recriada (Task 4).

## File Structure

- Criar: `database/migrations/2026_11_18_000001_create_credit_purchases_and_credit_columns.php`, `app/Models/CreditPurchase.php`, `app/Services/Credits/CreditService.php`, `app/Services/Credits/CreditAlertService.php`, `app/Notifications/CreditsConfirmedNotification.php`, `app/Notifications/CreditsLowNotification.php`, `app/Notifications/CreditsEmptyNotification.php`.
- Modificar: `config/billing.php`, `app/Services/Billing/{PaymentGateway,AsaasGateway,FakeGateway}.php`, `app/Services/{QuotaGate,AiUsageRecorder}.php`, `app/Services/Billing/BillingSyncService.php`, `app/Http/Controllers/Api/AsaasWebhookController.php`, `app/Livewire/{MyPlan,RestaurantPlanList}.php` + views, `app/Notifications/QuotaAlertNotification.php`, `app/Models/{AiUsage,Subscription}.php`, `app/Console/Commands/BillingSandboxCheck.php`.
- Testes novos em `tests/Feature/Credits/` (`CreditsTestCase`, `CreditSchemaTest`, `CreditConsumptionTest`, `CreditPurchaseTest`, `CreditPaymentTest`, `CreditAlertTest`, `CreditUiTest`) e `tests/Unit/Billing/CreditGatewayTest`.

---

### Task 1: Esquema, config, modelo e saldo derivado

**Files:**
- Create: `database/migrations/2026_11_18_000001_create_credit_purchases_and_credit_columns.php`, `app/Models/CreditPurchase.php`, `app/Services/Credits/CreditService.php` (só `balance` e `usedInCycle` nesta tarefa), `tests/Feature/Credits/CreditsTestCase.php`, `tests/Feature/Credits/CreditSchemaTest.php`
- Modify: `config/billing.php` (chave `credits`), `app/Models/AiUsage.php` (cast `from_credit`)

**Interfaces:**
- Produces: tabela `credit_purchases` (`id`, `restaurant_id` FK cascade, `kind` `purchase|grant`, `status` `pending|paid|reversed|canceled`, `credits` unsigned int, `price` decimal(10,2) nullable, `gateway_payment_id` string(64) nullable unique, `invoice_url` text nullable, `credited_at` timestamp nullable, `note` string(200) nullable, `granted_by` unsignedBigInteger nullable, timestamps); `ai_usage.from_credit` boolean default false com índice composto `(restaurant_id, from_credit, counted)`; `subscriptions.credit_low_alert_at` e `subscriptions.credit_zero_alert_at` timestamps nullable.
- Produces: `App\Models\CreditPurchase` (mesmo padrão de tenant de `BillingPayment`; `casts`: `credited_at` datetime, `price` decimal:2); `CreditService::balance(Restaurant $r): int` = soma de `credits` das linhas com `credited_at` não nulo **menos** contagem de `ai_usage` com `counted = true` e `from_credit = true` (sem escopo de tenant, por `restaurant_id`); `CreditService::usedInCycle(Restaurant $r, CarbonInterface $from, CarbonInterface $to): int` (mesma contagem de `from_credit` no intervalo).
- Produces: `CreditsTestCase` (estende `Tests\Feature\Billing\BillingTestCase`) com helper `activeRestaurant(string $plan = 'starter'): array{0: Restaurant, 1: User, 2: Subscription}` que cria restaurante, dono e assinatura gerida `active` com `gateway_subscription_id`, `gateway_customer_id`, `paid_through = now()+20 dias`, `cycle_started_at = now()`; e `credit(Restaurant $r, int $credits): CreditPurchase` que insere uma compra `paid` já creditada.

- [ ] **Step 1: Criar a branch e escrever os testes de esquema (RED).** `git checkout -b feat/creditos-extras-fase5b-9.8` e `tests/Feature/Credits/CreditSchemaTest.php` com: `test_credit_purchases_table_and_columns_exist` (colunas e `ai_usage.from_credit` default `false`); `test_balance_is_credited_minus_counted_from_credit` (compra de 500 creditada + 3 linhas `ai_usage` `from_credit` `counted` + 1 `from_credit` com `counted = false` + 1 sem `from_credit` → `balance` = 497); `test_pending_and_uncredited_purchases_do_not_count` (linha `pending` sem `credited_at` → 0); `test_balance_is_isolated_between_restaurants`.
- [ ] **Step 2: Rodar `php artisan test --filter=CreditSchemaTest`.** Esperado: FALHA (tabela/classe inexistente).
- [ ] **Step 3: Implementar a migration** (retomável com `Schema::hasTable`/`hasColumn`, no estilo de `2026_11_16_000002`), o modelo, `config('billing.credits')` (`pack_size` 500, `price` 49.0, `price_large` 79.0, `large_carta_labels` 200, `low_threshold` 100), o cast e `balance`/`usedInCycle`.
- [ ] **Step 4: Rodar `php artisan test --filter=CreditSchemaTest`.** Esperado: PASS.
- [ ] **Step 5: Commit** `feat(backend): saldo de créditos extras e esquema de compras [Story 9.8]`.

---

### Task 2: Cobrança avulsa no gateway

**Files:**
- Modify: `app/Services/Billing/PaymentGateway.php`, `app/Services/Billing/AsaasGateway.php`, `app/Services/Billing/FakeGateway.php`
- Test: `tests/Unit/Billing/CreditGatewayTest.php`

**Interfaces:**
- Produces: `PaymentGateway::createPayment(string $customerId, float $value, string $description, string $billingType = 'UNDEFINED'): GatewayPayment` (retorna id, `subscriptionId` nulo, status `PENDING`, `value`, `dueDate` hoje, `invoiceUrl`).
- Produces (FakeGateway): `createPayment` cria o pagamento em memória sem assinatura, respeita `failNext('createPayment')`, e `markPaid`/`markOverdue`/`getPayment` funcionam sobre ele (`getPayment` devolve `subscriptionId = null`).

- [ ] **Step 1: Testes (RED)** em `CreditGatewayTest`: `test_fake_create_payment_returns_pending_payment_without_subscription` (id `pay_fake_…`, `subscriptionId === null`, `value 49.0`, `invoiceUrl` começa com `https://`); `test_fake_paid_one_off_payment_is_readable_via_get_payment` (após `markPaid`, `getPayment()->isPaid()` verdadeiro); `test_fake_create_payment_can_fail` (`failNext('createPayment')` lança `GatewayException`); `test_asaas_create_payment_posts_one_off_charge` (com `Http::swap(new Factory)` e fake de `POST /payments`: o corpo tem `customer`, `billingType` `UNDEFINED`, `value` 49, `dueDate` de hoje e `description`, e **não** tem `subscription`/`cycle`; o resultado traz o `invoiceUrl` da resposta); `test_asaas_create_payment_failure_is_a_generic_gateway_exception` (resposta 400 com corpo contendo CPF não aparece na mensagem).
- [ ] **Step 2: Rodar `php artisan test --filter=CreditGatewayTest`.** Esperado: FALHA (método inexistente).
- [ ] **Step 3: Implementar** a assinatura na interface, em `AsaasGateway` (usa `send('createPayment', …)` e `mapPayment`, igual às outras operações) e em `FakeGateway` (reutiliza a estrutura `payments`, com `subscription` nulo).
- [ ] **Step 4: Rodar `php artisan test --filter=CreditGatewayTest` e `php artisan test --filter=Billing`.** Esperado: PASS (a suíte de billing da 5a segue verde).
- [ ] **Step 5: Commit** `feat(backend): cobrança avulsa no gateway (Asaas e fake) [Story 9.8]`.

---

### Task 3: Consumo do saldo no gate e no recorder

**Files:**
- Modify: `app/Services/QuotaGate.php`, `app/Services/AiUsageRecorder.php`
- Test: `tests/Feature/Credits/CreditConsumptionTest.php`

**Interfaces:**
- Consumes: `CreditService::balance` (Task 1); `SubscriptionService::state()` (campos `status`, `quota`, `used`, `cycleStart`, `cycleEnd`).
- Produces: `QuotaGate::check` libera enquanto `used + inFlight < quota + saldoEfetivo`, onde `saldoEfetivo` = `balance` só se `state->status === 'active'`, senão 0; continua devolvendo `403 SOFIA_UNAVAILABLE` e `429 QUOTA_EXHAUSTED` com os mesmos códigos e mensagens.
- Produces: `AiUsageRecorder::record` grava `from_credit = true` quando o estado é `active`, a cota não é nula e `state->used >= state->quota` **antes** de gravar a linha; `markUncounted` desmarca a linha da consulta e, se ela **não** era `from_credit`, a `from_credit` `counted` mais antiga do ciclo atual perde a marca (`from_credit = false`).

- [ ] **Step 1: Testes (RED)** em `CreditConsumptionTest` (todos com `activeRestaurant()` e cota do plano `starter` = 500; usar `AiUsage` inseridos para chegar a 500): `test_gate_blocks_when_quota_is_exhausted_and_no_balance` (429 `QUOTA_EXHAUSTED`); `test_gate_allows_after_quota_when_there_is_balance` (500 usadas + saldo 500 → `null`); `test_gate_blocks_at_quota_plus_balance` (1000 usadas, saldo 500 → 429); `test_in_flight_interactions_compete_for_the_last_credit` (500 usadas, saldo 1, uma `AiInteraction` `pending` criada agora → 429); `test_balance_is_ignored_outside_active_state` (assinatura em carência com saldo → 403 `SOFIA_UNAVAILABLE`; trial com `credit()` → bloqueia ao esgotar os 150); `test_record_flags_from_credit_only_after_the_quota_is_spent` (a consulta 500 não tem a marca, a 501 tem); `test_mark_uncounted_of_a_credit_consultation_returns_the_balance` (`balance` sobe 1); `test_mark_uncounted_of_an_in_quota_consultation_shifts_the_flag` (500 usadas + 1 `from_credit`; `markUncounted` de uma das 500 → a `from_credit` perde a marca e `balance` sobe 1); `test_legacy_restaurant_without_quota_still_passes`.
- [ ] **Step 2: Rodar `php artisan test --filter=CreditConsumptionTest`.** Esperado: FALHA nos casos de saldo e marca.
- [ ] **Step 3: Implementar** a injeção de `CreditService` no `QuotaGate` e a lógica descrita; o cálculo de `from_credit` e o deslocamento em `markUncounted` ficam no `AiUsageRecorder`, dentro de uma transação curta.
- [ ] **Step 4: Rodar `php artisan test --filter=CreditConsumptionTest` e `php artisan test tests/Feature/Plans`.** Esperado: PASS (QuotaGate, alertas e uso em cache da Fase 4 seguem verdes).
- [ ] **Step 5: Commit** `feat(backend): Sofia consome o saldo de créditos depois da cota do plano [Story 9.8]`.

---

### Task 4: Compra do pacote e cortesia

**Files:**
- Modify: `app/Services/Credits/CreditService.php`
- Test: `tests/Feature/Credits/CreditPurchaseTest.php`

**Interfaces:**
- Consumes: `PaymentGateway::createPayment` (Task 2); `BillingException` e o gate `manage-billing`/`manage-plans` da 5a.
- Produces: `CreditService::priceFor(Restaurant $r): float` (79.0 se `Wine::count()` do restaurante, sem removidos, `> large_carta_labels`; senão 49.0); `CreditService::refusalFor(Restaurant $r): ?string` (mensagem em português para teste, carência, encerrada, legado, plano sem cota ou assinatura sem gateway; `null` se pode comprar); `CreditService::purchase(User $owner): string` (devolve o link de pagamento; lança `BillingException`); `CreditService::grant(User $admin, Restaurant $r, int $credits, string $note): CreditPurchase` (`kind = grant`, `status = paid`, `credited_at` agora, auditada).

- [ ] **Step 1: Testes (RED)** em `CreditPurchaseTest`: `test_purchase_creates_a_pending_one_off_payment_and_returns_the_link` (uma compra `pending`, `credits` 500, `price` 49.00, `gateway_payment_id` preenchido, `invoice_url` retornada começa com `https://`, saldo continua 0); `test_purchase_reuses_an_open_pending_purchase_with_the_same_price` (duas chamadas → uma só `credit_purchases` e um só pagamento no `FakeGateway`); `test_purchase_closes_a_pending_with_a_stale_price_and_creates_a_new_one` (cria pendente a R$ 49, a carta passa de 200, nova chamada → a antiga `canceled`, a nova a R$ 79); `test_price_boundary_200_vs_201_labels_and_soft_deleted_do_not_count` (200 → 49; 201 → 79; 201 com 2 removidos → 49); `test_purchase_is_refused_for_trial_grace_ended_legacy_and_no_gateway_subscription` (cada caso lança `BillingException`, nenhuma cobrança criada); `test_only_the_owner_can_purchase` (`manager` recebe `AuthorizationException`); `test_purchase_gateway_failure_leaves_no_purchase` (`failNext('createPayment')`); `test_grant_requires_manage_plans_and_credits_immediately` (admin concede 100 → saldo 100, `kind grant`; owner não pode); `test_purchase_never_logs_the_document_or_tokens` (nenhum log de auditoria contém CPF/CNPJ); `test_purchase_is_isolated_between_restaurants`.
- [ ] **Step 2: Rodar `php artisan test --filter=CreditPurchaseTest`.** Esperado: FALHA.
- [ ] **Step 3: Implementar** `priceFor`, `refusalFor`, `purchase` (reaproveita o `gateway_customer_id` da assinatura, `description` "Vinia — pacote de 500 consultas", reutilização/fechamento de `pending` pelo preço calculado agora) e `grant`.
- [ ] **Step 4: Rodar `php artisan test --filter=CreditPurchaseTest`.** Esperado: PASS.
- [ ] **Step 5: Commit** `feat(backend): compra de pacote de créditos e cortesia do admin [Story 9.8]`.

---

### Task 5: Pagamento do pacote (webhook e sincronização)

**Files:**
- Modify: `app/Services/Credits/CreditService.php`, `app/Http/Controllers/Api/AsaasWebhookController.php`, `app/Services/Billing/BillingSyncService.php`
- Create: `app/Notifications/CreditsConfirmedNotification.php`
- Test: `tests/Feature/Credits/CreditPaymentTest.php`

**Interfaces:**
- Consumes: `CreditPurchase`, `GatewayPayment`, `Subscription` (estado), `CreditAlertService::rearm` (Task 6 cria; nesta tarefa chamar via `app()` dentro de `try/catch (\Throwable)` para não depender da ordem de implementação — ou deixar o gancho para a Task 6).
- Produces: `CreditService::owns(GatewayPayment $p): bool` (existe `credit_purchases` com `gateway_payment_id` = `$p->id`); `CreditService::applyPayment(GatewayPayment $p): bool` (verdadeiro se creditou agora): `isPaid()` → reivindica `credited_at` de forma atômica (`whereNull('credited_at')->update`), `status = paid`, avisa o dono (`CreditsConfirmedNotification(int $credits, int $balance)`, na fila, depois de gravar), audita; `OVERDUE` → `status = canceled` se ainda não creditada; `REFUNDED`/`CHARGEBACK` → `status = reversed` se já creditada (saldo mantido) e `canceled` se não, com `Log::channel('audit')->warning('billing.payment_reversed', …)`; `CreditService::sync(Restaurant $r): int` (reconsulta no gateway as compras `pending` do restaurante e aplica); `BillingSyncService::sync` passa a chamar `CreditService::sync` e soma o que creditou ao retorno.
- Produces (webhook): antes do caminho de assinatura, se `CreditService::owns($payment)` o controlador chama `applyPayment` e responde `credited`, `recorded`, `refunded` ou `chargeback`, com o `restaurant_id` da compra; qualquer outra cobrança segue o caminho da 5a, intocado.

- [ ] **Step 1: Testes (RED)** em `CreditPaymentTest` (webhook com `hook()` no estilo de `AsaasWebhookTest`, token certo): `test_confirmed_payment_credits_500_once` (saldo 500, compra `paid`, e-mail enfileirado ao dono); `test_same_payment_twice_with_different_event_ids_credits_once` (dois avisos, `event_id` distintos → saldo 500); `test_webhook_and_sync_together_credit_once` (webhook e `BillingSyncService::sync` sobre o mesmo pagamento → 500); `test_payment_after_the_subscription_ended_credits_the_frozen_balance_without_touching_the_subscription` (assinatura `canceled` e `paid_through` no passado: saldo 500, `paid_through`/`status`/`plan`/`cycle_started_at` iguais ao antes; `QuotaGate` ainda 403); `test_package_payment_does_not_renew_the_subscription` (`paid_through` não avança); `test_overdue_package_is_canceled_and_credits_nothing`; `test_reversed_package_keeps_the_balance_and_marks_the_purchase_and_logs_a_warning`; `test_unknown_payment_still_follows_the_subscription_path_untouched` (a renovação da 5a continua funcionando); `test_wrong_token_is_still_401_and_credits_nothing`; `test_credit_of_restaurant_a_never_appears_in_b`; `test_sync_credits_a_package_whose_webhook_was_lost`.
- [ ] **Step 2: Rodar `php artisan test --filter=CreditPaymentTest`.** Esperado: FALHA.
- [ ] **Step 3: Implementar** `owns`, `applyPayment`, `sync`, a notificação (mesmo molde de `PaymentConfirmedNotification`, botão "Ver meu plano") e o desvio no controlador do webhook; a reconsulta do pagamento no Asaas (`getPayment`) já existe e continua sendo a fonte da verdade.
- [ ] **Step 4: Rodar `php artisan test --filter=CreditPaymentTest` e `php artisan test --filter=Billing`.** Esperado: PASS (`AsaasWebhookTest` e `BillingSyncTest` seguem verdes).
- [ ] **Step 5: Commit** `feat(backend): pagamento do pacote credita o saldo pelo webhook e pela sincronização [Story 9.8]`.

---

### Task 6: Avisos de saldo baixo e zerado

**Files:**
- Create: `app/Services/Credits/CreditAlertService.php`, `app/Notifications/CreditsLowNotification.php`, `app/Notifications/CreditsEmptyNotification.php`
- Modify: `app/Services/AiUsageRecorder.php` (chamada dentro do `try` que já protege `QuotaAlertService`), `app/Services/Credits/CreditService.php` (chamar `rearm` em `applyPayment` e `grant`), `app/Models/Subscription.php` (casts dos dois campos)
- Test: `tests/Feature/Credits/CreditAlertTest.php`

**Interfaces:**
- Produces: `CreditAlertService::check(Restaurant $r): void` (só para assinatura `active` com cota e `from_credit` em uso: se `balance <= low_threshold` e `> 0` e `credit_low_alert_at` nulo → avisa o dono com `CreditsLowNotification(int $balance)` e grava a marca; se `balance == 0` e `credit_zero_alert_at` nulo → `CreditsEmptyNotification` e marca); `CreditAlertService::rearm(Restaurant $r): void` (se `balance > low_threshold` zera as duas marcas).
- Notificações: e-mail ao dono, na fila, texto em português com o botão "Comprar créditos" apontando para `route('backoffice.plan')`.

- [ ] **Step 1: Testes (RED)** em `CreditAlertTest` (`Notification::fake()`): `test_low_balance_alert_is_sent_once_when_crossing_100`; `test_empty_balance_alert_is_sent_once_when_reaching_zero`; `test_no_alert_while_the_plan_quota_is_still_being_used` (consultas dentro da cota não disparam); `test_a_purchase_above_the_threshold_rearms_both_alerts` (nova queda avisa de novo); `test_a_grant_above_the_threshold_rearms_the_alerts_too`; `test_restaurant_with_only_a_grant_and_no_purchase_is_alerted`; `test_alerts_never_break_the_sofia_response` (notificação que lança exceção não derruba `AiUsageRecorder::record`); `test_trial_and_legacy_never_get_credit_alerts`.
- [ ] **Step 2: Rodar `php artisan test --filter=CreditAlertTest`.** Esperado: FALHA.
- [ ] **Step 3: Implementar** o serviço (a decisão de "em uso de crédito" é `balance` calculado com pelo menos uma linha `from_credit` ou uma compra creditada, para não avisar quem nunca comprou nem recebeu), as duas notificações e as ligações em `record`, `applyPayment` e `grant`.
- [ ] **Step 4: Rodar `php artisan test --filter=CreditAlertTest` e `php artisan test tests/Feature/Plans`.** Esperado: PASS.
- [ ] **Step 5: Commit** `feat(backend): avisos de saldo baixo e zerado dos créditos [Story 9.8]`.

---

### Task 7: Tela "Meu plano" e admin

**Files:**
- Modify: `app/Livewire/MyPlan.php`, `resources/views/livewire/my-plan.blade.php`, `app/Livewire/RestaurantPlanList.php` e a view da lista, `app/Notifications/QuotaAlertNotification.php`
- Test: `tests/Feature/Credits/CreditUiTest.php`

**Interfaces:**
- Consumes: `CreditService::{balance, priceFor, refusalFor, purchase, grant, usedInCycle}`.
- Produces: `MyPlan::buyCredits(CreditService $credits)` (reautoriza `manage-billing`, redireciona ao link `https://` de pagamento; erro de `BillingException` vira `addError('credits', mensagem)`); `RestaurantPlanList::grantCredits(int $restaurantId, ?string $value, CreditService $credits)` (valor inteiro entre 1 e 5000, nota fixa "Cortesia do admin", `$notice` de sucesso ou erro).
- UI "Meu plano": seção "Créditos extras" com saldo, preço do pacote, botão "Comprar pacote de 500 consultas (R$ 49,00)" (oculto quando `refusalFor` não é nulo, mostrando o motivo), link da compra `pending` aberta, histórico das últimas compras e cortesias (data, créditos, valor, estado; `grant` como "cortesia") e "Consultas extras usadas neste ciclo". Admin: coluna "Saldo" e campo/botão de cortesia. O e-mail de 100% da cota (`QuotaAlertNotification`) ganha, quando o plano é ativo, a frase de que dá para comprar créditos em "Meu plano".

- [ ] **Step 1: Testes (RED)** em `CreditUiTest` (Livewire): `test_owner_sees_balance_price_and_buy_button` (R$ 49,00, saldo, botão); `test_buy_redirects_to_the_payment_link` (`assertRedirect` a um `https://`); `test_buy_button_hidden_with_reason_for_trial_and_grace`; `test_history_lists_purchases_and_grants_with_labels` ("cortesia", "Paga", "Pendente"); `test_pending_purchase_shows_the_payment_link`; `test_manager_cannot_open_buy_action` (403); `test_admin_grant_credits_updates_the_balance_column_and_notice`; `test_admin_grant_rejects_zero_negative_and_non_numeric`; `test_quota_alert_email_mentions_credits_only_for_active_plans`.
- [ ] **Step 2: Rodar `php artisan test --filter=CreditUiTest`.** Esperado: FALHA.
- [ ] **Step 3: Implementar** os métodos e as views com os tokens `bo-*` e o mesmo cuidado de acessibilidade da 5a (rótulos, `role="status"`/`alert`, links `https://` com `rel="noopener noreferrer"`).
- [ ] **Step 4: Rodar `php artisan test --filter=CreditUiTest` e `php artisan test --filter=MyPlanTest`.** Esperado: PASS.
- [ ] **Step 5: Commit** `feat(backend): créditos extras em Meu plano e cortesia no admin [Story 9.8]`.

---

### Task 8: Verificação de ponta a ponta e story

**Files:**
- Modify: `app/Console/Commands/BillingSandboxCheck.php`
- Create: `vinia-docs/docs/stories/9.8.story.md`

- [ ] **Step 1: Estender `billing:sandbox-check`** para, depois do fluxo da assinatura, criar uma cobrança avulsa (`createPayment`, R$ 49), simulá-la paga com `POST /payments/{id}/receiveInCash` e conferir que `getPayment` devolve `RECEIVED` sem `subscription`; a saída nunca imprime chave nem documento. Rodar com `BILLING_GATEWAY=asaas ASAAS_ENV=sandbox` e a chave do `.env` já configurada (não ler nem imprimir o `.env`); se a chave não estiver disponível, registrar "não verificado no sandbox" na story.
- [ ] **Step 2: Rodar a suíte completa** `php artisan test` em SQLite e depois em MySQL 8 (container descartável na porta 3327). Esperado: tudo verde, sem regressão nos testes da 5a (`tests/Feature/Billing`, `tests/Feature/Plans`).
- [ ] **Step 3: Ponta a ponta local** com `BILLING_GATEWAY=fake`: assinatura ativa → consumir a cota → 429 → comprar pacote → `markPaid` + webhook → Sofia volta → saldo cai com `from_credit` → aviso de saldo baixo. Registrar o resultado.
- [ ] **Step 4: Escrever `9.8.story.md`** (ACs a partir da seção 8 do spec, Dev Agent Record, rulings, minors adiados, "para publicar", decisões em aberto) e commitar em `vinia-docs`.
- [ ] **Step 5: Commit** `chore(backend): verificação do sandbox para créditos extras [Story 9.8]`.
