# Vinia SaaS — Fase 1: endurecer o multi-tenant — Plano de Implementação

> **Para quem executa:** SUB-SKILL OBRIGATÓRIA: usar superpowers:subagent-driven-development (recomendado) ou superpowers:executing-plans, tarefa a tarefa. Os passos usam checkbox (`- [ ]`).

**Goal:** Garantir, por código e por testes no CI, que um restaurante nunca lê, altera ou apaga dados de outro.

**Architecture:** O banco já tem `restaurant_id` e os filtros são manuais (`where('restaurant_id', ...)`) mais Policies. Esta fase adiciona uma camada automática: um `CurrentRestaurant` (resolve o restaurante da requisição), um global scope `RestaurantScope` e o trait `BelongsToRestaurant`, aplicados a `Wine`, `Tablet`, `ComensalSession` e `AiInteraction`. Os filtros manuais ficam (defesa em profundidade). Uma suíte de testes de isolamento e um teste que audita consultas cruas fecham o critério "pronto quando".

**Tech Stack:** Laravel (PHP), Livewire, PHPUnit (SQLite em memória nos testes, MySQL em produção), GitHub Actions (`php artisan test` já roda no `deploy.yml`).

**Spec:** `vinia-docs/docs/superpowers/specs/2026-11-10-vinia-saas-design.md` (§5 auditoria, §7 arquitetura, Fase 1 do §8).

**Story / branch:** Story 9.1 (Epic 9 — Vinia SaaS), a ser criada por @sm no Task 1. Branch local `feat/saas-multitenant-9.1`. `git push` e PR são do @devops.

## Global Constraints

- Código em `vinia-src/backend`, documentação e stories em `vinia-docs` (nunca docs no `vinia-src`).
- Banco único com `restaurant_id`; **não** introduzir banco por cliente.
- Funcionar na Hostinger compartilhada (MySQL, sem Redis/Horizon) e em SQLite nos testes.
- `User` **não** recebe o scope (login e auth resolvem o usuário antes de existir contexto de restaurante).
- Perfil `admin` enxerga todos os restaurantes (como hoje, `User::isAdmin()`).
- Mensagens e rótulos de UI em português com acentuação correta.
- Commits convencionais com `[Story 9.1]`; suíte completa (`php artisan test`, hoje 470+ testes) verde ao fim de cada task.
- Nada de `DB::table`/`whereRaw` novo sem entrar na lista revisada do Task 6.

## Review Focus

1. Usuário autenticado **não admin e sem `restaurant_id`** não pode ver dados de nenhum restaurante (falha fechada, não aberta).
2. Criar registro com `restaurant_id` de outro restaurante, estando com contexto ativo, deve falhar (não gravar em silêncio).
3. Id de outro restaurante via route-model binding responde **404** (nunca 403 nem 200) em vinhos, tablets, sessões e interações.
4. Admin sem restaurante continua vendo o agregado de todos no dashboard (`DashboardStats::SCOPE_ALL`) e a lista de usuários de todos.
5. Contexto do tablet não vaza entre requisições na mesma aplicação (testes e workers): limpa ao terminar a requisição.

---

### Task 1: Story 9.1 e branch

**Files:**
- Create: `vinia-docs/docs/stories/9.1.story.md`

**Interfaces:**
- Produces: story 9.1 (Draft) com os CAs abaixo, referenciada nos commits.

- [ ] **Step 1:** Criar a branch `feat/saas-multitenant-9.1` em `vinia-src` a partir de `main` (`git checkout -b feat/saas-multitenant-9.1`). O `.gitignore` modificado do working tree não entra nos commits desta branch.
- [ ] **Step 2:** Criar `9.1.story.md` no formato das stories existentes (ver `8.4.story.md`), status Draft, com os CAs: CA01 escopo automático em Wine/Tablet/ComensalSession/AiInteraction; CA02 falha fechada para não admin sem restaurante; CA03 `ai_interactions.restaurant_id` com backfill; CA04 suíte de isolamento A×B (leitura, edição, exclusão → 404); CA05 auditoria de consultas cruas em teste; CA06 suíte completa verde.
- [ ] **Step 3: Commit** (em `vinia-docs`): `docs: story 9.1 multi-tenant (Epic 9 SaaS)`.

---

### Task 2: `CurrentRestaurant`, `RestaurantScope` e trait `BelongsToRestaurant`

**Files:**
- Create: `backend/app/Support/Tenancy/CurrentRestaurant.php`
- Create: `backend/app/Models/Scopes/RestaurantScope.php`
- Create: `backend/app/Models/Concerns/BelongsToRestaurant.php`
- Modify: `backend/app/Providers/AppServiceProvider.php` (registrar `CurrentRestaurant` como `singleton`)
- Test: `backend/tests/Unit/Tenancy/CurrentRestaurantTest.php`, `backend/tests/Unit/Tenancy/BelongsToRestaurantTest.php`

**Interfaces:**
- Produces `CurrentRestaurant`:
  - `use(?int $restaurantId): void` — contexto explícito (usado pelo tablet); sobrepõe o usuário logado.
  - `forget(): void` — remove o contexto explícito.
  - `isRestricted(): bool` — `true` quando há contexto explícito, ou usuário autenticado **não admin**.
  - `id(): ?int` — id do restaurante quando restrito; `null` quando restrito sem restaurante (não admin sem `restaurant_id`) ou quando irrestrito.
  - Resolução, nesta ordem: contexto explícito → usuário autenticado (`admin` = irrestrito; senão restrito a `restaurant_id`, possivelmente `null`) → sem usuário (console, jobs, rotas públicas) = irrestrito. A leitura do usuário é **preguiçosa** (por chamada, via `auth()`), para funcionar nas requisições do Livewire sem middleware.
- Produces `RestaurantScope implements Illuminate\Database\Eloquent\Scope`: se `isRestricted()` e `id()` não nulo, `where("{table}.restaurant_id", id)`; se restrito e `id()` nulo, `whereIn("{table}.restaurant_id", [])` (resultado vazio); se irrestrito, não filtra.
- Produces trait `BelongsToRestaurant`: registra o `RestaurantScope`; no evento `creating`, se `restaurant_id` for nulo e houver restaurante no contexto, preenche; se vier preenchido e **diferente** do contexto restrito, lança `\LogicException` com mensagem em português.

- [ ] **Step 1: Escrever os testes que falham.** `CurrentRestaurantTest`: (a) sem usuário e sem contexto → `isRestricted() === false`; (b) `use(5)` → restrito, `id() === 5`; `forget()` volta a irrestrito; (c) `actingAs` usuário `owner` com `restaurant_id` 7 → `id() === 7`; (d) `actingAs` admin → irrestrito; (e) `actingAs` `manager` com `restaurant_id` nulo → restrito e `id() === null`; (f) contexto explícito vence o usuário logado. `BelongsToRestaurantTest` usando `Wine`: (g) com contexto 1, `Wine::factory()->create(['restaurant_id' => 2])` lança `LogicException`; (h) com contexto 1 e `restaurant_id` omitido, o vinho nasce com `restaurant_id = 1`; (i) com contexto 1, `Wine::query()` não traz vinho do restaurante 2; (j) falha fechada: usuário não admin sem restaurante → `Wine::count() === 0` mesmo com vinhos no banco; (k) sem contexto → `Wine::count()` conta todos.
- [ ] **Step 2: Rodar para ver falhar.** `cd backend && php artisan test --filter=Tenancy` → FAIL (classes inexistentes). Em (a)–(k), `Wine` ainda não usa o trait: aplicar o trait em `Wine` faz parte do Task 3, então em (g)–(k) usar um model de teste anônimo ou aplicar o trait em `Wine` já neste passo, só o necessário para a unidade; decisão: **aplicar em `Wine` aqui** e o Task 3 cobre os demais models.
- [ ] **Step 3: Implementar** as três classes com as assinaturas acima e registrar o singleton. `isRestricted()` não pode consultar o banco além do que `auth()->user()` já carregou.
- [ ] **Step 4: Rodar** `php artisan test --filter=Tenancy` → PASS.
- [ ] **Step 5: Rodar a suíte completa** `php artisan test` e corrigir regressões causadas pelo scope em `Wine` (testes que usam `actingAs` e depois consultam `Wine::` de outro restaurante passam a precisar de `Auth::logout()` ou `Wine::withoutGlobalScopes()`; ajustar o teste, não o scope).
- [ ] **Step 6: Commit:** `feat(backend): escopo automático por restaurante em Wine [Story 9.1]`.

---

### Task 3: Aplicar o escopo em `Tablet` e `ComensalSession`; contexto do tablet na API

**Files:**
- Modify: `backend/app/Models/Tablet.php`, `backend/app/Models/ComensalSession.php` (usar o trait)
- Modify: `backend/app/Http/Middleware/TabletAuthentication.php`
- Test: `backend/tests/Feature/Api/TabletTenancyContextTest.php`

**Interfaces:**
- Consumes: `CurrentRestaurant::use(?int)`, `forget()`; trait `BelongsToRestaurant`.
- Produces: `TabletAuthentication` localiza o tablet com `Tablet::withoutGlobalScopes()` (ainda não há contexto nesse ponto), chama `CurrentRestaurant::use($tablet->restaurant_id)` e tem método `terminate(Request, Response): void` que chama `forget()`.

- [ ] **Step 1: Escrever os testes que falham.** (a) com o token do tablet A, `GET /api/v1/wines` só devolve vinhos de A; (b) duas requisições seguidas no mesmo teste, tablet A e depois tablet B, cada uma vê só o seu restaurante; (c) depois de uma requisição de tablet, `app(CurrentRestaurant::class)->isRestricted()` é `false` (limpo no `terminate`); (d) token inválido continua 401; (e) `ComensalSession::create` sem `restaurant_id` dentro do contexto do tablet herda o restaurante.
- [ ] **Step 2: Rodar** `php artisan test --filter=TabletTenancyContextTest` → FAIL.
- [ ] **Step 3: Implementar** o trait nos dois models e o ajuste do middleware conforme a Interface. `TabletList` (Livewire) e `DashboardStats` seguem com os filtros manuais.
- [ ] **Step 4: Rodar** o teste novo → PASS, depois `php artisan test` completo → verde.
- [ ] **Step 5: Commit:** `feat(backend): contexto de restaurante do tablet e escopo em Tablet/ComensalSession [Story 9.1]`.

---

### Task 4: `ai_interactions.restaurant_id` e escopo em `AiInteraction`

**Files:**
- Create: `backend/database/migrations/2026_11_10_000001_add_restaurant_id_to_ai_interactions_table.php`
- Modify: `backend/app/Models/AiInteraction.php` (trait + `restaurant_id` no `$fillable` + relação `restaurant()`)
- Modify: `backend/app/Http/Controllers/Api/AiInteractionController.php` (`store` grava `restaurant_id` da sessão; `show` passa a responder 404 também por escopo)
- Modify: `backend/database/factories/` (criar `AiInteractionFactory` se não existir, com `session_id` e `restaurant_id` coerentes)
- Test: `backend/tests/Feature/Migrations/AiInteractionRestaurantMigrationTest.php`, ajustes em `backend/tests/Feature/Api/AiInteractionTest.php`

**Interfaces:**
- Produces: coluna `ai_interactions.restaurant_id` (FK para `restaurants`, índice, `NOT NULL` depois do backfill).

- [ ] **Step 1: Escrever os testes que falham.** Migração: com interações existentes ligadas a sessões de restaurantes 1 e 2, após `up()` cada interação tem o `restaurant_id` da sua sessão e nenhuma fica nula; `down()` remove a coluna. API: `POST /api/v1/ai/recommend` cria a interação com `restaurant_id` do tablet.
- [ ] **Step 2: Rodar** → FAIL.
- [ ] **Step 3: Implementar a migração** em três movimentos compatíveis com MySQL e SQLite: adicionar coluna anulável; preencher com `UPDATE ... SET restaurant_id = (SELECT restaurant_id FROM comensal_sessions WHERE id = session_id)` via query builder; tornar `NOT NULL` com FK e índice. Depois o model e o controller conforme a lista de arquivos.
- [ ] **Step 4: Rodar** os testes novos e a suíte completa → verde (incluindo `SofiaResilienceTest`, que dispara o job pós-resposta dentro da requisição do tablet).
- [ ] **Step 5: Commit:** `feat(backend): restaurant_id em ai_interactions com backfill e escopo [Story 9.1]`.

---

### Task 5: Suíte de isolamento A × B

**Files:**
- Create: `backend/tests/Feature/Isolation/ApiIsolationTest.php`
- Create: `backend/tests/Feature/Isolation/BackofficeIsolationTest.php`
- Create: `backend/tests/Feature/Isolation/AdminVisibilityTest.php`

**Interfaces:**
- Consumes: factories de `Restaurant`, `User`, `Wine`, `Tablet`, `ComensalSession`, `AiInteraction`.
- Convenção: cada teste monta dois restaurantes (A e B) com um registro de cada tipo e age como usuário/tablet de A.

- [ ] **Step 1: Escrever os testes** (devem passar se os Tasks 2–4 estiverem corretos; qualquer falha é bug real a corrigir no código, não no teste).
  - `ApiIsolationTest` (tablet A): `GET /wines/{vinho de B}` → 404; `GET /wines` não contém vinho de B; `PATCH /sessions/{sessão de B}` → 403 ou 404; `POST /ai/recommend` com `session_id` de B → 403; `GET /ai/interactions/{interação de B}` → 404; `compare`/`about_wine` com id de vinho de B → erro de validação ou 404, nunca dados de B.
  - `BackofficeIsolationTest` (owner de A): `GET /backoffice/wines/{vinho de B}/edit` → 404 ou 403; exclusão de vinho de B pelo componente `WineList` falha sem alterar o registro; `TabletList` não revoga/exclui tablet de B; `GET /backoffice/wines/export` traz só vinhos de A; `WineImport` grava só em A; `RestaurantSettings` edita só A; `UserList` de owner não mostra usuários de B.
  - `AdminVisibilityTest`: admin sem restaurante vê o agregado de todos no dashboard e todos os usuários; **não admin sem restaurante** não vê nenhum vinho/tablet/sessão (Review Focus 1 e 4).
- [ ] **Step 2: Rodar** `php artisan test --filter=Isolation` → PASS (se falhar, corrigir o código que vazou e repetir).
- [ ] **Step 3: Commit:** `test(backend): suíte de isolamento entre restaurantes [Story 9.1]`.

---

### Task 6: Auditoria de consultas cruas, cache e jobs; fechamento

**Files:**
- Create: `backend/tests/Feature/Isolation/RawQueryAuditTest.php`
- Modify: `vinia-docs/docs/stories/9.1.story.md` (checkboxes, File List, status InReview)

**Interfaces:**
- Produz `RawQueryAuditTest::ALLOWED`: lista `arquivo => quantidade` revisada hoje: `app/Livewire/UserList.php` → 1 `whereRaw` (busca por nome, sem dados de tenant), `app/Services/DashboardStats.php` → 2 `selectRaw` (agregados sobre `Wine`/`Tablet` já filtrados por `$scoped`).

- [ ] **Step 1: Escrever o teste:** percorre `app/**/*.php`, conta ocorrências de `DB::table(`, `DB::select(`, `DB::statement(`, `whereRaw(`, `selectRaw(`, `orderByRaw(`, `fromRaw(` e falha se houver arquivo ou contagem fora de `ALLOWED`, com a mensagem "Consulta crua nova: revise o isolamento por restaurante e inclua em ALLOWED".
- [ ] **Step 2: Rodar** → PASS. Introduzir temporariamente um `whereRaw` novo em um arquivo e confirmar que o teste falha; desfazer.
- [ ] **Step 3: Revisão de cache e filas (sem mudança de código esperada).** `ImportWinesJob` usa chave `wine_import_result_{userId}` (por usuário, que pertence a um só restaurante) e recebe o `Restaurant` explicitamente; `ProcessAiRecommendationJob` carrega a interação por id. Registrar essa conclusão em uma seção "Revisão de cache e filas" da story. Se algum dos dois lê modelo escopado fora de requisição, garantir que o `restaurant_id` vem do próprio registro, não do contexto.
- [ ] **Step 4: Verificação final:** `cd backend && php artisan test` completo verde; `php artisan route:list` sem rota nova sem escopo; atualizar a story (CAs marcados, File List, InReview).
- [ ] **Step 5: Commit:** `test(backend): auditoria de consultas cruas e fechamento da Story 9.1 [Story 9.1]`.

---

## Self-Review

- **Cobertura do spec (Fase 1 do §8):** escopo global (Tasks 2–4), `restaurant_id` em `ai_interactions` (4), testes de isolamento no CI (5; `deploy.yml` já executa `php artisan test`), revisão de consultas cruas (6), cache/jobs/filas (6). **Fora desta fase, por decisão:** tabela `restaurant_user`, papel `sommelier` e slug público `/r/{slug}` (spec §7: usuário em um só restaurante na v1; `/r/{slug}` entra na Fase 2).
- **Consistência de tipos:** `CurrentRestaurant::use/forget/isRestricted/id` iguais em Tasks 2 e 3; `BelongsToRestaurant` igual em 2, 3 e 4.
- **Proporção:** plano menor que o código que descreve; corpos de implementação ficam com quem executa.
- **Ponto de atenção para o executor:** testes existentes que combinam `actingAs` com consultas diretas a models escopados podem precisar de ajuste (Task 2, passo 5).
