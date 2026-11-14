# Fase 5a — assinar e pagar pelo Asaas — Plano de Implementação

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** O dono assina um plano e paga pelo link do Asaas; o pagamento (e só ele) renova o acesso e a falta dele desliga a Sofia no prazo; a nota fiscal pode sair pelo Asaas por configuração.

**Architecture:** Interface `PaymentGateway` com `AsaasGateway` (API v3, HTTP do Laravel) e `FakeGateway`; `BillingService` (assinar, trocar, cancelar, aplicar pagamento de forma idempotente) e `BillingSyncService`; webhook em `/api/webhooks/asaas` que confere o token e **reconsulta a cobrança no Asaas** antes de agir; estado derivado em `SubscriptionService` por `paid_through`; tela Livewire "Meu plano" para o dono.

**Tech Stack:** Laravel 13, Livewire 4, PHPUnit (SQLite; CI MySQL 8). Backend em `vinia-src/backend`. Credenciais do sandbox no `.env` do Rafael.

**Spec:** `vinia-docs/docs/superpowers/specs/2026-11-14-vinia-cobranca-asaas-fase5a-design.md` (aprovado). Contexto: Stories 9.4 a 9.6. Story desta fase: **9.7**, escrita no fim (Task 8).

## Global Constraints

- Segredos só no `.env`: `BILLING_GATEWAY` (`fake`|`asaas`, padrão `fake`), `ASAAS_API_KEY`, `ASAAS_ENV` (`sandbox`|`production`), `ASAAS_WEBHOOK_TOKEN` (32 a 255 caracteres, diferente da chave da API), `ASAAS_NFSE_ENABLED` (padrão `false`) e os dados fiscais em `config/billing.php`. Nada disso em log, banco ou resposta.
- **Nunca gravar** CPF, CNPJ digitado para assinar, cartão, chave da API nem token do webhook, em tabela ou log. O documento vai direto ao Asaas.
- URLs do Asaas: `https://api-sandbox.asaas.com/v3` (sandbox) e `https://api.asaas.com/v3` (produção); a chave vai no cabeçalho `access_token`. O webhook traz o token no cabeçalho `asaas-access-token`, conferido com `hash_equals`.
- Estado: assinatura **sem** gateway = como na Fase 4 (renova sozinha); **com** gateway = `active` até `paid_through`, depois `grace` por `config('plans.grace_days')` (7 dias) e `ended`. Cancelar mantém o acesso até `paid_through`.
- Cada cobrança renova **uma única vez**; `paid_through` nunca anda para trás; ciclo de `config('plans.cycle_days')` (30 dias) a partir do vencimento pago.
- Webhook responde **200** também para evento que não conhece ou cobrança que não é de assinatura do Vinia; **401** só para token errado ou ausente. Nada muda sem a reconsulta ao Asaas confirmar.
- Legado e assinatura feita à mão pelo admin (sem gateway) nunca mudam de estado por esta fase.
- Sem cron novo; avisos por notificação em fila (existente). Suíte verde em SQLite **e** MySQL 8; isolamento A×B.
- Commits em português, convencionais, `[Story 9.7]`, terminando com `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>`. Sem push.
- Comando de teste: `cd backend && php artisan test --compact [--filter=...]`. Chamadas HTTP ao Asaas nos testes sempre com `Http::fake`.

## Review Focus

- Webhook com token errado ou ausente: 401 e nada muda; token certo mas a reconsulta mostra cobrança **não paga** (ou de outra assinatura): não renova (Task 5).
- O mesmo pagamento em dois avisos, `RECEIVED` antes de `CONFIRMED`, ou o mesmo `event_id` reenviado: `paid_through` avança **uma vez** (Tasks 4 e 5).
- Aviso cujo id de assinatura pertence ao restaurante B não altera o A; o dono de A não vê faturas de B (Tasks 5 e 6).
- Falha da API do Asaas ao assinar (timeout, 400 com CPF inválido): nada fica pela metade (cliente criado e assinatura não: a nova tentativa reaproveita o cliente), mensagem em português, e falha na reconsulta do webhook não perde o aviso (fica registrado e o `sync` resolve) (Tasks 4 e 5).
- Cliente legado ou assinado à mão: o estado não muda e o admin não consegue assinar/cancelar à mão uma assinatura gerida pelo gateway (Tasks 3 e 7).

---

### Task 1: Gateway (interface, Asaas, simulado) e configuração

**Files:**
- Create: `backend/config/billing.php`, `backend/app/Services/Billing/PaymentGateway.php`, `backend/app/Services/Billing/GatewayPayment.php`, `backend/app/Services/Billing/GatewaySubscription.php`, `backend/app/Services/Billing/AsaasGateway.php`, `backend/app/Services/Billing/FakeGateway.php`, `backend/app/Console/Commands/BillingSandboxCheck.php`
- Modify: `backend/app/Providers/AppServiceProvider.php` (bind do gateway), `backend/.env.example` (chaves novas, sem valores)
- Test: `backend/tests/Unit/Billing/AsaasGatewayTest.php`, `backend/tests/Unit/Billing/FakeGatewayTest.php`

**Interfaces:**
- Produces:
  - `interface PaymentGateway { createCustomer(string $name, string $email, string $document): string; createSubscription(string $customerId, string $plan, float $value, string $billingType = 'UNDEFINED'): GatewaySubscription; updateSubscriptionValue(string $subscriptionId, float $value): void; cancelSubscription(string $subscriptionId): void; getPayment(string $paymentId): GatewayPayment; listSubscriptionPayments(string $subscriptionId): array /* list<GatewayPayment> */; configureInvoices(string $subscriptionId, array $fiscal): void; }`
  - `final class GatewaySubscription { string $id; ?string $firstPaymentUrl; }`
  - `final class GatewayPayment { string $id; ?string $subscriptionId; string $status /* PENDING|CONFIRMED|RECEIVED|OVERDUE|REFUNDED|CHARGEBACK|OTHER */; float $value; ?CarbonImmutable $dueDate; ?CarbonImmutable $paidAt; ?string $invoiceUrl; bool isPaid(): bool /* CONFIRMED ou RECEIVED */ }`
  - Binding: `PaymentGateway::class` → `FakeGateway` quando `config('billing.gateway') === 'fake'`, `AsaasGateway` quando `asaas`.
  - `FakeGateway` guarda estado em memória do processo e expõe `markPaid(string $paymentId, ?CarbonImmutable $at = null)`, `markOverdue(string $paymentId)`, `payments(): array` e `failNext(string $method)` para simular erro.
  - `php artisan billing:sandbox-check`: só roda com `BILLING_GATEWAY=asaas`; cria cliente e assinatura de teste no sandbox (documento de teste lido do argumento `--document=`), imprime o link da primeira cobrança e o tipo de cobrança usado, sem imprimir segredos.

- [ ] **Step 1: testes que falham.** `AsaasGatewayTest` com `Http::fake`: `createCustomer` faz `POST {base}/customers` com cabeçalho `access_token` e devolve o `id`; `createSubscription` faz `POST {base}/subscriptions` com `customer`, `billingType`, `value`, `nextDueDate` (hoje), `cycle` `MONTHLY` e `description` com o nome do plano, e o link da primeira cobrança vem de `GET {base}/subscriptions/{id}/payments` (`invoiceUrl`); `getPayment` mapeia `status` do Asaas (`PENDING`, `CONFIRMED`, `RECEIVED`, `OVERDUE`, `REFUNDED`, `CHARGEBACK_REQUESTED`→`CHARGEBACK`, outros→`OTHER`) e `subscription`; `cancelSubscription` faz `DELETE`; resposta 4xx/5xx lança `GatewayException` com mensagem em português **sem** CPF, chave nem corpo bruto; a base muda com `ASAAS_ENV`. `FakeGateway`: ciclo completo criar cliente→assinar→cobrança `PENDING`→`markPaid`→`isPaid()`; `failNext` lança.
- [ ] **Step 2: rodar e ver falhar.** `--filter='AsaasGatewayTest|FakeGatewayTest'`. Expected: FAIL (classes inexistentes).
- [ ] **Step 3: implementar** conforme as interfaces, o `config/billing.php` (gateway, urls por ambiente, chave, token do webhook, `nfse` com `enabled`, `municipal_service_id`, `iss_percent`, `pis_cofins_cst`) e o comando de verificação do sandbox. `GatewayException` em `App\Exceptions\GatewayException`.
- [ ] **Step 4: rodar** o mesmo filtro. Expected: PASS.
- [ ] **Step 5: commit** `feat(backend): gateway de pagamento (interface, Asaas e simulado) [Story 9.7]`.

### Task 2: Dados da cobrança

**Files:**
- Create: `backend/database/migrations/2026_11_16_000001_add_billing_columns_to_subscriptions.php`, `backend/database/migrations/2026_11_16_000002_create_billing_tables.php`, `backend/app/Models/BillingPayment.php`, `backend/app/Models/BillingEvent.php`
- Modify: `backend/app/Models/Subscription.php` (casts `paid_through`, relação `payments`), `backend/app/Models/Restaurant.php` (relação `billingPayments` se útil)
- Test: `backend/tests/Feature/Billing/BillingSchemaTest.php`

**Interfaces:**
- Produces: `subscriptions.gateway` (string 20 nula), `gateway_customer_id` (string 64 nula), `gateway_subscription_id` (string 64 nula, índice único), `paid_through` (timestamp nulo); `billing_payments` (`payment_id` único, `restaurant_id` indexado, `subscription_gateway_id`, `status`, `value` decimal 10,2, `due_date` date nula, `paid_at` timestamp nulo, `invoice_url` text nula, `applied_at` timestamp nulo, timestamps); `billing_events` (`event_id` único, `restaurant_id` nulo indexado, `event` string, `payment_id` nulo, `result` string 30, `created_at`). **Sem colunas de documento, cartão ou corpo bruto.** Models com `restaurant_id` usam o trait/escopo do projeto quando consultados pelo dono (isolamento).

- [ ] **Step 1: teste que falha.** `BillingSchemaTest`: as colunas existem; `payment_id` e `event_id` são únicos (segundo insert igual falha); nenhuma coluna de `billing_payments`/`billing_events` contém `document`, `cpf`, `cnpj`, `card` ou `payload`; migrations rodam em banco com assinaturas existentes sem mudar nenhuma linha.
- [ ] **Step 2: rodar e ver falhar.** `--filter=BillingSchemaTest`. Expected: FAIL.
- [ ] **Step 3: implementar** as migrations aditivas e retomáveis (`hasColumn`/`hasTable`) e os models (`$guarded = []`, atribuição só pelos serviços).
- [ ] **Step 4: rodar** `--filter=BillingSchemaTest`. Expected: PASS.
- [ ] **Step 5: commit** `feat(backend): tabelas e colunas da cobrança [Story 9.7]`.

### Task 3: Estado derivado pelo pagamento

**Files:**
- Modify: `backend/app/Support/Plans/SubscriptionState.php` (campos finais opcionais `?CarbonImmutable $paidThrough = null` e `bool $cancelScheduled = false`, depois de `$plan`), `backend/app/Services/SubscriptionService.php`
- Test: `backend/tests/Feature/Billing/PaidThroughStateTest.php`

**Interfaces:**
- Consumes: colunas da Task 2.
- Produces: `SubscriptionService::state()` trata `gateway_subscription_id !== null` por `paid_through`: antes dele `active` (cota e ciclo como na Fase 4; `status = canceled` com `paid_through` no futuro continua `active` com `cancelScheduled = true`); de `paid_through` até `+ grace_days` → `grace` (carta visível, Sofia desligada); depois → `ended` (`restaurantUsable = false`). Sem `paid_through` (assinou mas ainda não pagou) a assinatura gerida não existe como paga: o estado segue o do trial/cancelado anterior.

- [ ] **Step 1: testes que falham.** Fronteiras com `travelTo`: um segundo antes de `paid_through` → `active`; em `paid_through` → `grace`; `+7 dias` menos um segundo → `grace`; `+7 dias` → `ended`; cancelada com `paid_through` futuro → `active` e `cancelScheduled`; cancelada depois do prazo → `grace` e depois `ended`; assinatura sem gateway e legado ficam **idênticos** à Fase 4 (renovam sozinhos); trial inalterado; assinatura gerida sem `paid_through` e com trial vigente continua `trial`.
- [ ] **Step 2: rodar e ver falhar.** `--filter=PaidThroughStateTest`. Expected: FAIL.
- [ ] **Step 3: implementar** o ramo novo no início de `state()` sem tocar nos ramos existentes; usar os parâmetros posicionais atuais mais os dois novos no fim.
- [ ] **Step 4: rodar a suíte inteira.** `php artisan test --compact`. Expected: PASS (o estado sem gateway não muda).
- [ ] **Step 5: commit** `feat(backend): estado da assinatura derivado de paid_through [Story 9.7]`.

### Task 4: BillingService e BillingSyncService

**Files:**
- Create: `backend/app/Services/Billing/BillingService.php`, `backend/app/Services/Billing/BillingSyncService.php`
- Modify: `backend/app/Services/SubscriptionAdminService.php` (bloqueio de ação manual em assinatura gerida)
- Test: `backend/tests/Feature/Billing/BillingServiceTest.php`, `backend/tests/Feature/Billing/BillingSyncTest.php`

**Interfaces:**
- Consumes: `PaymentGateway`, `GatewayPayment`, tabelas da Task 2, estado da Task 3, validador de CPF/CNPJ da Fase 3 (`Document`).
- Produces:
  - `BillingService::subscribe(User $owner, string $plan, string $name, string $document): string` (devolve o link do primeiro pagamento): reautoriza (`manage-billing`), valida plano assinável e documento, reaproveita `gateway_customer_id` se já existir, cria cliente e assinatura, liga a emissão de nota se `billing.nfse.enabled`, grava `gateway`, ids e `plan` pretendido **sem** mudar o estado de acesso; falha do gateway → `BillingException` em português e nada pela metade.
  - `BillingService::changePlan(User $owner, string $plan): void`: plano e cota novos na hora, `updateSubscriptionValue` para as próximas cobranças.
  - `BillingService::cancel(User $owner): void`: cancela no gateway, `status = canceled`, `canceled_at = now()`, mantém `paid_through`.
  - `BillingService::applyPayment(GatewayPayment $p, ?string $eventId = null): bool`: localiza a assinatura por `p->subscriptionId`; faz upsert em `billing_payments`; se `isPaid()` e `applied_at` nulo, **renova uma vez**: `status = active`, `legacy = false`, `plan` pretendido, `paid_through = max(paid_through, vencimento + cycle_days)`, `cycle_started_at`, restaurante `active = true` e `plan`; devolve se renovou; cobrança que não é de assinatura conhecida não faz nada.
  - `BillingSyncService::sync(Restaurant $r): int`: lista as cobranças da assinatura e aplica cada uma por `applyPayment`; devolve quantas renovaram.
  - `SubscriptionAdminService`: `subscribe`, `cancel` e `changePlan` lançam `\DomainException` clara quando a assinatura tem `gateway_subscription_id`.

- [ ] **Step 1: testes que falham** (com `FakeGateway`): assinar cria cliente e assinatura e devolve link sem mudar o acesso; assinar de novo reaproveita o cliente; documento inválido recusado antes de chamar o gateway; falha do gateway na assinatura não grava ids; pagamento aplicado renova uma vez (segundo `applyPayment` do mesmo id devolve `false` e não anda `paid_through`); duas cobranças em sequência andam 30 dias cada; pagamento `PENDING` ou `OVERDUE` não renova; `paid_through` nunca recua com cobrança antiga; cobrança de assinatura desconhecida é ignorada; cobrança da assinatura do restaurante B não altera A; trocar plano muda cota e valor; cancelar mantém `paid_through`; `sync` aplica cobranças pagas que faltavam; admin é barrado em assinatura gerida e livre nas sem gateway; **nenhum log nem linha** contém o documento digitado.
- [ ] **Step 2: rodar e ver falhar.** `--filter='BillingServiceTest|BillingSyncTest'`. Expected: FAIL.
- [ ] **Step 3: implementar** conforme as interfaces, auditando só com ids em `Log::channel('audit')`.
- [ ] **Step 4: rodar** `--filter='BillingServiceTest|BillingSyncTest|SubscriptionAdminTest'`. Expected: PASS.
- [ ] **Step 5: commit** `feat(backend): assinar, trocar, cancelar e aplicar pagamento [Story 9.7]`.

### Task 5: Webhook do Asaas

**Files:**
- Create: `backend/app/Http/Controllers/Api/AsaasWebhookController.php`
- Modify: `backend/routes/api.php` (`POST /webhooks/asaas`, fora do grupo do tablet), `backend/app/Providers/AppServiceProvider.php` (limitador `asaas-webhook`)
- Test: `backend/tests/Feature/Billing/AsaasWebhookTest.php`

**Interfaces:**
- Consumes: `BillingService::applyPayment`, `PaymentGateway::getPayment`, `BillingEvent`.
- Produces: `POST /api/webhooks/asaas` (corpo do Asaas: `id` do evento, `event`, `payment.id`). Token ausente ou diferente de `config('billing.asaas.webhook_token')` (comparação em tempo constante) → 401 sem gravar nada. Com token: grava `billing_events` por `event_id` (evento repetido → 200 `duplicate` sem reprocessar); para `PAYMENT_CONFIRMED`, `PAYMENT_RECEIVED`, `PAYMENT_OVERDUE`, `PAYMENT_REFUNDED` e `PAYMENT_CHARGEBACK_REQUESTED` **reconsulta** `getPayment($payment.id)` e age pelo que volta de lá, não pelo corpo; falha da reconsulta registra `result = unverified` e responde 200; `SUBSCRIPTION_DELETED` cancela a assinatura local; evento desconhecido registra `ignored` e responde 200. Atraso envia `PaymentOverdueNotification` (Task 7) uma vez por cobrança; chargeback e estorno registram em log de aviso e no `billing_events`.

- [ ] **Step 1: testes que falham.** Token errado e sem token → 401 e `billing_events` vazio; token certo + cobrança confirmada pelo `FakeGateway` → renova e responde 200; token certo mas a reconsulta diz `PENDING` → 200, **não** renova; mesmo `event_id` duas vezes → uma renovação; `RECEIVED` antes de `CONFIRMED` e depois repetido → `paid_through` avança uma vez; cobrança de assinatura de outro restaurante → só o dono certo muda; reconsulta com erro → 200 e `unverified`, e `BillingSyncService::sync` depois renova; evento desconhecido → 200; `PAYMENT_OVERDUE` → aviso uma vez e a carência corre pela data; a rota não exige CSRF nem sessão; o limitador responde 429 acima do teto.
- [ ] **Step 2: rodar e ver falhar.** `--filter=AsaasWebhookTest`. Expected: FAIL.
- [ ] **Step 3: implementar** o controller fino (valida, registra, delega ao `BillingService`) e o limitador (120 por minuto por IP).
- [ ] **Step 4: rodar** `--filter='AsaasWebhookTest|BillingServiceTest'`. Expected: PASS.
- [ ] **Step 5: commit** `feat(backend): webhook do Asaas com token e reconsulta da cobrança [Story 9.7]`.

### Task 6: Tela "Meu plano"

**Files:**
- Create: `backend/app/Livewire/MyPlan.php`, `backend/resources/views/livewire/my-plan.blade.php`
- Modify: `backend/routes/web.php` (`GET /backoffice/plano`, nome `backoffice.plan`, `can:manage-billing`), `backend/app/Providers/AppServiceProvider.php` (Gate `manage-billing`: só `owner` com restaurante), `backend/app/Http/Middleware/EnsureRestaurantUsable.php` (`backoffice.plan` em `ALLOWED`), `backend/resources/views/components/backoffice-layout.blade.php` e `backend/resources/views/backoffice/layouts/app.blade.php` (item de menu "Meu plano"), `backend/resources/views/backoffice/trial-ended.blade.php` (botão "Assinar" para o dono), `backend/resources/views/backoffice/partials` (faixas de teste, carência e cota apontam para `backoffice.plan`)
- Test: `backend/tests/Feature/Billing/MyPlanTest.php`

**Interfaces:**
- Consumes: `BillingService`, `BillingSyncService`, `SubscriptionService::state`, `config('plans.plans')`.
- Produces: Livewire `MyPlan` (restaurante sempre o do usuário logado; nenhuma propriedade pública com id): estado (dias de teste, plano, pago até, "cancelamento agendado"), lista de planos com preço da `config/plans.php`, formulário de assinatura (nome ou razão social e CPF ou CNPJ, validação em português), ações `subscribe` (redireciona para o link do pagamento), `changePlan`, `cancel` (com confirmação) e a lista de faturas (`billing_payments` do restaurante, com link). Ao montar chama `BillingSyncService::sync` com tolerância a falha (nunca derruba a tela).

- [ ] **Step 1: testes que falham.** Só o dono acessa (gerente, sommelier e admin recebem 403; visitante vai ao login); dono com teste encerrado ainda alcança `/backoffice/plano` e a página "teste encerrado" tem o botão; assinar com documento inválido mostra erro em português e não chama o gateway; assinar válido redireciona ao link do `FakeGateway`; o documento **não** aparece em sessão, `old input`, log nem banco; trocar de plano e cancelar chamam o serviço; lista só as faturas do próprio restaurante (A não vê as de B); falha do gateway mostra mensagem amigável; o menu mostra "Meu plano" só para o dono.
- [ ] **Step 2: rodar e ver falhar.** `--filter=MyPlanTest`. Expected: FAIL.
- [ ] **Step 3: implementar** o componente e a view seguindo os tokens `bo-*` do backoffice; `document` entra em `dontFlash` (já está) e nunca vira propriedade renderizada de volta.
- [ ] **Step 4: rodar a suíte inteira.** `php artisan test --compact`. Expected: PASS (testes de menu e de rotas permitidas atualizados de propósito, anotados no commit).
- [ ] **Step 5: commit** `feat(backend): tela Meu plano com assinatura, troca, cancelamento e faturas [Story 9.7]`.

### Task 7: Avisos e admin

**Files:**
- Create: `backend/app/Notifications/PaymentConfirmedNotification.php`, `backend/app/Notifications/PaymentOverdueNotification.php`, `backend/app/Notifications/SubscriptionCanceledNotification.php`
- Modify: `backend/app/Services/Billing/BillingService.php` (dispara os avisos), `backend/app/Livewire/RestaurantPlanList.php` e `backend/resources/views/livewire/restaurant-plan-list.blade.php` (coluna Cobrança, botão Sincronizar, ações manuais bloqueadas em assinatura gerida), `backend/app/Notifications/TrialReminderNotification.php` e `backend/app/Notifications/QuotaAlertNotification.php` (botão aponta para `backoffice.plan`)
- Test: `backend/tests/Feature/Billing/BillingNotificationsTest.php`, `backend/tests/Feature/Billing/AdminBillingTest.php`

**Interfaces:**
- Consumes: `BillingService`, `BillingSyncService`.
- Produces: três notificações de e-mail em português e em fila, enviadas ao dono (`owner`) do restaurante: pagamento confirmado (plano, valor, pago até), pagamento em atraso (Sofia desligada, carta segue por 7 dias, botão "Ver meu plano") e assinatura cancelada (acesso até a data). Admin: coluna **Cobrança** (Manual ou Asaas, pago até, último evento), botão **Sincronizar** (`BillingSyncService::sync`) e botões manuais desabilitados com aviso quando a assinatura é gerida.

- [ ] **Step 1: testes que falham.** `Notification::fake`: pagamento confirmado envia uma vez (reaplicar o mesmo pagamento não reenvia); atraso envia uma vez por cobrança; cancelar envia; destinatário é o dono do restaurante certo e nenhum outro; textos em português sem placeholders; admin vê a coluna e o botão, o botão chama `sync`, ações manuais em assinatura gerida mostram o aviso; gerente e dono não acessam a tela do admin.
- [ ] **Step 2: rodar e ver falhar.** `--filter='BillingNotificationsTest|AdminBillingTest'`. Expected: FAIL.
- [ ] **Step 3: implementar** conforme as interfaces, reaproveitando o estilo de `QuotaAlertNotification`.
- [ ] **Step 4: rodar a suíte inteira.** `php artisan test --compact`. Expected: PASS.
- [ ] **Step 5: commit** `feat(backend): avisos de cobrança e coluna de cobrança no admin [Story 9.7]`.

### Task 8: Verificação e registro

**Files:**
- Create: `vinia-docs/docs/stories/9.7.story.md`
- Modify: cofre Obsidian (Status e Índice Vinia, Índice Mestre, decisão de cobrança)

- [ ] **Step 1: sandbox de verdade (se `ASAAS_API_KEY` e `BILLING_GATEWAY=asaas` estiverem no `.env` de desenvolvimento).** Rodar `php artisan billing:sandbox-check --document=<CPF de teste>`, abrir o link da primeira cobrança, pagar no sandbox e confirmar que o webhook chega (túnel público) ou que `sync` renova. Registrar o tipo de cobrança que funcionou (`UNDEFINED` versus `CREDIT_CARD`), como obter o link e qualquer diferença do esperado; ajustar o `AsaasGateway` com teste vermelho antes. Sem credenciais, registrar "não verificado".
- [ ] **Step 2: suítes.** Backend em SQLite e em MySQL 8 (um contêiner descartável por rodada, em porta livre), frontend `npm test` se algo do frontend mudou.
- [ ] **Step 3: revisão final** do branch por subagente opus e ponta a ponta no navegador (assinar com o `FakeGateway`, simular o webhook com `curl`, ver "Meu plano" nos estados: teste, ativo, atraso, cancelado), corrigindo Critical e Important em uma onda, cada correção com teste vermelho antes.
- [ ] **Step 4: story 9.7** (ACs, rulings, backlog, "para publicar": variáveis do `.env`, cadastrar o webhook no painel do Asaas com a URL e o token, produção versus sandbox, nota fiscal pela contabilidade), cofre e `/graphify . --update`.
- [ ] **Step 5: commits finais** e parar: merge e push só com autorização do Rafael.
