# Vinia SaaS — Fase 2: acesso do comensal pelo celular — Plano de Implementação

> **Para quem executa:** SUB-SKILL OBRIGATÓRIA: usar superpowers:subagent-driven-development (recomendado) ou superpowers:executing-plans, tarefa a tarefa. Os passos usam checkbox (`- [ ]`).

**Goal:** O cliente do restaurante abre a carta pelo QR no próprio celular, sem conta, e usa a Sofia só dentro de uma sessão curta e limitada, de modo que o custo de IA do restaurante não escape do controle.

**Architecture:** A mesma PWA React atende dois modos: `tablet` (token Bearer, como hoje) e `phone` (carta pública por slug + sessão curta da Sofia). Backend novo em `/api/public/r/{slug}/...`: um middleware resolve o restaurante pelo slug (mesmo `CurrentRestaurant` da Fase 1) e, nas rotas da Sofia, autentica a sessão por token opaco com validade. Um `ComensalActor` (tablet ou sessão de celular) deixa os controllers existentes servirem as duas famílias de rota sem duplicar a lógica da Sofia. O gestor liga o acesso por celular, escolhe QR mensal ou permanente e gera/baixa o QR numa tela nova do backoffice.

**Tech Stack:** Laravel + Livewire (backoffice, `simplesoftwareio/simple-qrcode` já instalado), PHPUnit (SQLite nos testes, MySQL 8 em produção); React 19 + Vite + vite-plugin-pwa (Workbox) + Vitest.

**Spec:** `vinia-docs/docs/superpowers/specs/2026-11-10-vinia-saas-design.md` (§6.2 a §6.4, §7 e Fase 2 do §8).

**Story / branch:** Story 9.2 (Epic 9), criada pelo @sm e **validada pelo @po** no Task 1. Branch local `feat/saas-comensal-celular-9.2`, criada a partir de `feat/saas-multitenant-9.1` (a 9.1 ainda não foi para a `main`; o @devops precisa integrar a 9.1 antes). `git push` e PR são do @devops.

## Decisões deste plano (revise)

Itens marcados **[CALL]** são escolhas minhas; o Rafael pode trocar qualquer uma antes da execução.

1. **[CALL] Celular desligado por padrão.** `restaurants.phone_access_enabled = false`: restaurantes de hoje não ganham URL pública sem o gestor ligar.
2. **[CALL] A carta é pública por slug; a chave do QR só autoriza criar sessão da Sofia.** Carta com QR expirado continua abrindo (sem custo de IA); só a Sofia deixa de iniciar.
3. **[CALL] QR mensal = chave que expira em 30 dias; permanente = sem expiração.** Regenerar invalida a chave anterior na hora. Trocar de modo não troca a chave (só a validade). Aviso no backoffice 7 dias antes de expirar; sem e-mail (não há SMTP).
4. **[CALL] Chave e token na `sessionStorage`**, não na `localStorage`: fechar a aba descarta os dois, então o cliente que sai do restaurante não continua com a Sofia liberada (preocupação do Rafael). O `?k=` é removido da URL ao carregar. Só o id do aparelho (UUID aleatório) fica em `localStorage`.
5. **[CALL] Valores das travas (calibráveis em `config/sofia.php`, com env):** sessão de 180 min; 15 consultas por sessão (tablet segue 25); 3 sessões por aparelho por dia; 60 sessões por IP por hora (folga para o wifi do restaurante); **teto provisório de 500 consultas/dia por restaurante via celular** (cobre o anti-objetivo "custo sem teto" até a cota da Fase 4 existir); carta pública 300 req/min por IP. IP **não** é gravado no banco (LGPD); limites usam o cache.
6. **[CALL] A PWA do celular roda em `/tablet/r/{slug}`**, dentro do escopo do service worker atual; `/r/{slug}` (o endereço do QR) redireciona para lá. Evita um segundo service worker e cabeçalho `Service-Worker-Allowed` (que `php artisan serve` não aplica). No celular, o `<link rel="manifest">` é removido (o manifest do tablet exige token e quebraria "adicionar à tela inicial").
7. **[CALL] Tablet intocado**, inclusive o `InactivityGuard` de 3 min. No celular não há reset por inatividade (a sessão expira por TTL).

**Fora da Fase 2** (registrados, não implementados): cache de perguntas frequentes e medição de custo (Fase 4, junto de `ai_usage`); cota mensal, painel e alertas (Fase 4); excedente pós-pago (Fase 5); app instalável no celular; QR por mesa; cache offline de fotos; limpeza de sessões expiradas; e-mail de aviso de expiração do QR.

## Global Constraints

- Código em `vinia-src/backend` e `vinia-src/frontend`; docs e stories em `vinia-docs` (nunca docs no `vinia-src`).
- Banco único com `restaurant_id`; toda rota pública passa pelo contexto de restaurante da Fase 1 (`CurrentRestaurant`, `forget()` no `terminate`, middleware antes do `SubstituteBindings`).
- Funcionar na Hostinger compartilhada (MySQL, cache em banco, sem Redis) e em SQLite nos testes. `env()` só dentro de `config/*.php` (com `config:cache` fora dele devolve null).
- Migrations retomáveis (`hasColumn`/`hasIndex`), como a da 9.1.
- Sessão de celular nunca vale na API do tablet, e token de tablet nunca vale na API pública.
- Formato de erro existente: `{"error": {"code": "...", "message": "..."}}`, mensagens em português com acentuação.
- Não gravar IP em tabela. O token de sessão é gravado só como `hash('sha256', token)`; o texto do token aparece uma vez, na resposta de criação.
- O fluxo do tablet não muda: a suíte de 733 testes da 9.1 continua verde ao fim de cada task.
- Commits convencionais com `[Story 9.2]`. **Só commitar com a autorização do Rafael registrada no ledger** (preferência dele no cofre); sem ela, deixar no working tree e reportar.

## Review Focus

1. Sessão vencida, encerrada ou desconhecida não executa a Sofia: 401 `SESSION_EXPIRED`/`UNAUTHORIZED`, sem consumir cota; fechar a aba descarta chave e token.
2. QR expirado ou regenerado: a carta continua abrindo; só nova sessão falha (`QR_EXPIRED`/`QR_INVALID`); o QR antigo morre assim que o gestor regenera.
3. Slug de A com token de sessão, vinho, interação ou chave de B: resposta idêntica à de "não existe" (401/404/403 `QR_INVALID`), nunca revela B.
4. Restaurante com celular desligado ou inativo: `/r/{slug}` e `/api/public/r/{slug}/*` dão 404 (sessões já abertas param de funcionar).
5. Tetos de custo: 16ª consulta da sessão, 4ª sessão do aparelho no dia e 501ª consulta do dia no restaurante dão 429 com código próprio, e nenhum deles afeta o tablet.

---

### Task 1: Story 9.2, validação do @po e branch

**Files:**
- Create: `vinia-docs/docs/stories/9.2.story.md`

**Interfaces:**
- Produces: story 9.2 com status Ready (após o GO do @po), referenciada nos commits.

- [ ] **Step 1:** Em `vinia-src`: `git checkout feat/saas-multitenant-9.1 && git checkout -b feat/saas-comensal-celular-9.2`. O `.gitignore` modificado do working tree não entra nos commits.
- [ ] **Step 2 (@sm / `aiox-sm`):** criar `9.2.story.md` no formato das stories existentes (ver `9.1.story.md`), status Draft, com os CAs: CA01 gestor liga/desliga o celular e escolhe QR mensal ou permanente, com explicação de risco; CA02 `/r/{slug}` abre a carta pública (404 se desligado, inativo ou inexistente), sem custo de IA; CA03 Sofia no celular só em sessão criada com a chave do QR, expira em 3 h, chave inválida ou expirada dá erro claro e a carta segue; CA04 travas (15 consultas/sessão, 3 sessões/dia/aparelho, 60 sessões/h/IP, 500 consultas/dia/restaurante provisório); CA05 isolamento A×B nas rotas públicas; CA06 tablet inalterado e suíte verde; CA07 carta abre offline com os dados da última visita, e a Sofia nunca sai do cache; CA08 gestor vê QR, link e validade, regenera, baixa o SVG e recebe aviso de expiração.
- [ ] **Step 3 (@po / `aiox-po`):** validar a story (checklist de 10 pontos). Só segue com GO (≥ 7); corrigir o que o @po pedir antes do Task 2.
- [ ] **Step 4: Commit** (em `vinia-docs`, se autorizado): `docs: story 9.2 acesso do comensal pelo celular (Epic 9 SaaS)`.

---

### Task 2: Dados do acesso por celular e `PhoneAccessService`

**Files:**
- Create: `backend/database/migrations/2026_11_11_000001_add_phone_access_to_restaurants_table.php`
- Create: `backend/database/migrations/2026_11_11_000002_add_phone_fields_to_comensal_sessions_table.php`
- Create: `backend/app/Services/PhoneAccessService.php`, `backend/app/Exceptions/QrKeyException.php`
- Modify: `backend/app/Models/Restaurant.php`, `backend/app/Models/ComensalSession.php`, `backend/database/factories/ComensalSessionFactory.php`, `backend/database/factories/RestaurantFactory.php`, `backend/config/sofia.php`
- Test: `backend/tests/Unit/Services/PhoneAccessServiceTest.php`, `backend/tests/Feature/Migrations/PhoneAccessMigrationsTest.php`

**Interfaces:**
- Produces, colunas: `restaurants.phone_access_enabled` bool default false; `restaurants.qr_mode` string(16) default `'monthly'`; `restaurants.qr_key` text nullable (cast `encrypted`); `restaurants.qr_key_expires_at` timestamp nullable. `comensal_sessions.tablet_id` passa a nullable; novas: `source` string(10) default `'tablet'`, `token_hash` string(64) nullable unique, `expires_at` timestamp nullable, `device_id` string(36) nullable; índice `(restaurant_id, source, started_at)`.
- Produces, `ComensalSession`: `isPhone(): bool`, `isExpired(): bool` (`expires_at` vencido **ou** `ended_at` preenchido).
- Produces, `config('sofia.phone')`: `session_ttl_minutes` 180, `queries_per_session` 15, `sessions_per_device_per_day` 3, `sessions_per_ip_per_hour` 60, `queries_per_restaurant_per_day` 500, `carta_requests_per_minute` 300, `qr_monthly_days` 30, `qr_expiring_days` 7 (cada um com `env('SOFIA_PHONE_...')`).
- Produces, `PhoneAccessService`:
  - `enable(Restaurant, string $mode = 'monthly'): void`: liga, define o modo e gera a chave se não houver.
  - `disable(Restaurant): void`.
  - `setMode(Restaurant, string $mode): void`: `monthly` dá validade de agora + 30 dias; `permanent` zera a validade; chave inalterada; outro valor lança `InvalidArgumentException`.
  - `regenerateKey(Restaurant): string`: chave nova de 32 hex (`bin2hex(random_bytes(16))`), validade conforme o modo.
  - `keyState(Restaurant): string`: `'off' | 'valid' | 'expiring' | 'expired'` (`expiring` = faltam ≤ 7 dias; permanente é sempre `valid`).
  - `assertKeyAllowsSession(Restaurant, ?string $key): void`: lança `QrKeyException` com `errorCode` `QR_INVALID` (ausente ou diferente, comparação com `hash_equals`) ou `QR_EXPIRED` (chave certa, vencida).
  - `entryUrl(Restaurant): ?string`: `url('/r/{slug}').'?k={key}'`, ou `null` se desligado/sem chave.
- Produces, `RestaurantFactory::withPhoneAccess(string $mode = 'monthly')` e `ComensalSessionFactory::phone()` (`tablet_id` null, `source` `'phone'`, `token_hash` de um token conhecido, `expires_at` +180 min).

- [ ] **Step 1: Testes que falham.** `PhoneAccessServiceTest`: (a) `enable` mensal grava `phone_access_enabled`, chave de 32 hex e validade ≈ agora + 30 dias; (b) `enable` permanente deixa `qr_key_expires_at` nulo; (c) `setMode` mensal→permanente zera a validade e mantém a chave, e permanente→mensal põe agora + 30 dias, mantendo a chave; modo inválido lança; (d) `regenerateKey` troca a chave e a antiga passa a dar `QR_INVALID`; (e) `keyState` com `Carbon::setTestNow`: `off`, `valid`, `expiring` no dia 24, `expired` no dia 31, permanente sempre `valid`; (f) `assertKeyAllowsSession`: certa passa; nula e errada dão `QR_INVALID`; certa e vencida dá `QR_EXPIRED`; (g) `entryUrl` contém `/r/{slug}?k=`, e é nulo com o celular desligado; (h) o valor cru de `qr_key` no banco (`DB::table`) é diferente da chave. `PhoneAccessMigrationsTest`: (i) sessão antiga criada pela factory do tablet continua com `source='tablet'`; (j) `tablet_id` aceita nulo; (k) rodar `up()` das duas migrations duas vezes não falha (retomável).
- [ ] **Step 2:** `cd backend && php artisan test --filter=PhoneAccess` → FAIL.
- [ ] **Step 3:** Implementar migrations, models, factories, config e o serviço conforme as Interfaces. `tablet_id` nullable via `->nullable()->change()` mantendo a FK.
- [ ] **Step 4:** Rodar as duas migrations num MySQL 8 descartável (como na 9.1; container `vinia-mysql` em 3307 ou um novo) e conferir `SHOW CREATE TABLE comensal_sessions`; anotar o resultado no relatório.
- [ ] **Step 5:** `php artisan test` completo → verde.
- [ ] **Step 6: Commit** (se autorizado): `feat(backend): dados do acesso por celular e PhoneAccessService [Story 9.2]`.

---

### Task 3: `ComensalActor` e refatoração sem mudança de comportamento

**Files:**
- Create: `backend/app/Support/Comensal/ComensalActor.php`
- Modify: `backend/app/Http/Middleware/TabletAuthentication.php`, `backend/app/Http/Controllers/Api/AiInteractionController.php`, `backend/app/Http/Controllers/Api/ComensalSessionController.php`, `backend/app/Http/Controllers/Api/WineController.php`, `backend/config/sofia.php` (`tablet.queries_per_session` = 25)
- Test: `backend/tests/Unit/Comensal/ComensalActorTest.php`

**Interfaces:**
- Produces `final class ComensalActor`: `forTablet(Tablet): self`; `forPhoneSession(ComensalSession): self`; `from(Request): self` (lê `$request->attributes->get('comensal_actor')`; `LogicException` se ausente); `restaurantId(): int`; `isPhone(): bool`; `ownsSession(ComensalSession): bool` (tablet: `tablet_id` igual ao seu; celular: `id` igual ao da sua sessão; sessão de celular tem `tablet_id` nulo, então nunca pertence a um tablet); `queriesPerSession(): int` (tablet `config('sofia.tablet.queries_per_session')`, celular `config('sofia.phone.queries_per_session')`); `dailyRestaurantLimit(): ?int` (tablet `null`, celular `config('sofia.phone.queries_per_restaurant_per_day')`).
- `TabletAuthentication` passa a também gravar `$request->attributes->set('comensal_actor', ComensalActor::forTablet($tablet))`, mantendo `merge(['tablet', 'restaurant'])`.
- Controllers: propriedade da sessão, limite por sessão (hoje a constante `RATE_LIMIT = 25`) e `restaurant_id` vêm do actor; `WineController` lê o restaurante de `$request->get('restaurant')`. Respostas, status e códigos do tablet ficam idênticos.

- [ ] **Step 1: Testes que falham** (`ComensalActorTest`): (a) tablet A é dono de sessão do tablet A e não da do tablet B; (b) actor de celular é dono só da própria sessão; (c) sessão de celular (`tablet_id` nulo) não pertence a actor de tablet; (d) limites: tablet 25 e `dailyRestaurantLimit() === null`; celular 15 e 500 (ler de `config` com `config([...])` alterado no teste); (e) `from()` sem atributo lança `LogicException`.
- [ ] **Step 2:** `php artisan test --filter=ComensalActor` → FAIL.
- [ ] **Step 3:** Implementar o actor e refatorar os três controllers e o middleware. Não mudar nenhuma mensagem nem status.
- [ ] **Step 4:** `php artisan test` completo (733 + novos) → verde, sem alterar teste existente.
- [ ] **Step 5: Commit** (se autorizado): `refactor(backend): ComensalActor para servir tablet e celular [Story 9.2]`.

---

### Task 4: Contexto público por slug e carta pública

**Files:**
- Create: `backend/app/Http/Middleware/ResolvePublicRestaurant.php`
- Modify: `backend/bootstrap/app.php` (alias `public.restaurant` e `prependToPriorityList(before: SubstituteBindings::class, prepend: ResolvePublicRestaurant::class)`), `backend/routes/api.php`, `backend/app/Providers/AppServiceProvider.php` (limiter `public-carta`)
- Test: `backend/tests/Feature/Api/PublicCartaTest.php`

**Interfaces:**
- Produces `ResolvePublicRestaurant::handle($request, $next, string $mode = 'carta')`: lê o parâmetro de rota `slug`, localiza `Restaurant` com `active = true` e `phone_access_enabled = true`; se não achar, `404` JSON `{"error":{"code":"NOT_FOUND","message":"Carta não encontrada."}}` (**mesmo corpo** para inexistente, desligado e inativo). Achando: `CurrentRestaurant::use($restaurant->id)`, `$request->merge(['restaurant' => $restaurant])`, `$request->route()->forgetParameter('slug')` (senão o slug é injetado nos argumentos dos controllers). `terminate()` chama `CurrentRestaurant::forget()`. O `$mode = 'session'` é implementado no Task 5.
- Rotas, em `routes/api.php`: `Route::prefix('public/r/{slug}')->where(['slug' => '[A-Za-z0-9_-]+'])` com, em `public.restaurant:carta` e `throttle:public-carta`: `GET /restaurant` (`RestaurantController@show`), `GET /wines` e `GET /wines/{wine}` (`WineController`, que já lê o restaurante do request depois do Task 3).
- Limiter `public-carta`: `Limit::perMinute(config('sofia.phone.carta_requests_per_minute'))->by('carta|'.$request->ip())`, resposta 429 JSON `RATE_LIMITED`.

- [ ] **Step 1: Testes que falham** (`PublicCartaTest`, dados de `SeedsTwoRestaurants` com A com celular ligado): (a) `GET /api/public/r/restaurante-alfa/restaurant` → 200 sem autenticação, só `id`, `name`, `logo_url`, `primary_color`, `secondary_color` (sem `cnpj`, `plan`, `qr_key`); (b) `/wines` traz o vinho de A e não contém "Rótulo Beta Exclusivo"; o filtro `?type=tinto` funciona como no tablet; (c) `/wines/{wineB}` pela rota de A → 404, e `/wines/{wineA}` → 200; (d) slug inexistente, restaurante com celular desligado e restaurante inativo → 404 com **corpo idêntico** entre os três; (e) depois da requisição, `app(CurrentRestaurant::class)->isRestricted()` é `false` (contexto não vaza); (f) com o limiter reduzido para 3 por `config()`, a 4ª requisição do mesmo IP → 429 `RATE_LIMITED`.
- [ ] **Step 2:** `php artisan test --filter=PublicCarta` → FAIL.
- [ ] **Step 3:** Implementar middleware, prioridade, rotas e limiter. Conferir que `php artisan route:list --path=api/public` mostra as 3 rotas com `public.restaurant:carta`.
- [ ] **Step 4:** `php artisan test` completo → verde.
- [ ] **Step 5: Commit** (se autorizado): `feat(backend): carta pública por slug com contexto de restaurante [Story 9.2]`.

---

### Task 5: Sessão do celular e Sofia com tetos

**Files:**
- Create: `backend/app/Http/Controllers/Api/PublicSessionController.php`
- Modify: `backend/app/Http/Middleware/ResolvePublicRestaurant.php` (modo `session`), `backend/routes/api.php`, `backend/app/Providers/AppServiceProvider.php` (limiter `public-session-start`), `backend/app/Http/Controllers/Api/AiInteractionController.php` (teto diário)
- Test: `backend/tests/Feature/Api/PublicSessionTest.php`, `backend/tests/Feature/Api/PublicSofiaTest.php`

**Interfaces:**
- `POST /api/public/r/{slug}/sessions` (`public.restaurant:carta`, `throttle:public-session-start`). Corpo `{"key": "<32 hex>"}`, cabeçalho `X-Device-Id` (UUID). Valida os dois (422). Chama `PhoneAccessService::assertKeyAllowsSession`; falha → 403 com o `errorCode` (`QR_INVALID`/`QR_EXPIRED`) e mensagem em português. Sucesso → 201 `{"data": {"session_id", "token", "expires_at" (ISO 8601), "queries_limit"}}`; o token é `bin2hex(random_bytes(20))`, gravado como `hash('sha256', $token)`; a sessão nasce com `source='phone'`, `tablet_id` nulo, `device_id`, `expires_at = now() + ttl`, `started_at = now()`.
- Limiter `public-session-start`: retorna `[Limit::perHour(sessions_per_ip_per_hour)->by('ip|'.ip), Limit::perDay(sessions_per_device_per_day)->by('device|'.deviceId)]`; sem UUID válido no cabeçalho, a chave do aparelho vira `'device|invalid|'.ip`; 429 JSON `RATE_LIMITED` com mensagem amigável.
- `ResolvePublicRestaurant` modo `session`: além do contexto, exige `Authorization: Bearer <token>`; busca `ComensalSession` por `token_hash` com `source='phone'` **depois** de `CurrentRestaurant::use` (o escopo da Fase 1 já limita ao restaurante do slug); ausente ou desconhecido → 401 `UNAUTHORIZED`; conhecida mas `isExpired()` → 401 `SESSION_EXPIRED`; ok → `request->attributes->set('comensal_actor', ComensalActor::forPhoneSession($session))`.
- Rotas em `public.restaurant:session`: `PATCH /sessions/{session}` (`ComensalSessionController@update`), `POST /ai/recommend` e `GET /ai/interactions/{interaction}` (`AiInteractionController`).
- `AiInteractionController::store`: depois do limite por sessão, se `actor->dailyRestaurantLimit()` não for nulo, contar `AiInteraction` de sessões `source='phone'` criadas desde o início do dia no fuso `config('app.business_timezone')` (mesmo cálculo do `DashboardStats`, convertido a UTC); `>=` limite → 429 `SOFIA_DAILY_LIMIT` ("A Sofia atingiu o limite de hoje neste restaurante. Chame o nosso sommelier."). No celular o `session_id` do corpo precisa ser o da sessão autenticada (senão 403 `FORBIDDEN`).

- [ ] **Step 1: Testes que falham.** `PublicSessionTest`: (a) chave certa → 201, token de 40 caracteres, `expires_at` ≈ +180 min, linha com `source='phone'`, `tablet_id` nulo, `token_hash === hash('sha256', $token)`, e o token em claro **não** está em nenhuma coluna; (b) chave errada ou ausente → 403 `QR_INVALID`; chave vencida → 403 `QR_EXPIRED`; (c) sem `X-Device-Id` ou com valor que não é UUID → 422; (d) a 4ª sessão do mesmo aparelho no dia → 429 `RATE_LIMITED`; com `sessions_per_ip_per_hour` = 2 por `config()`, a 3ª do mesmo IP → 429; (e) restaurante desligado → 404 mesmo com a chave certa. `PublicSofiaTest` (com `Queue::fake()`): (f) sem Authorization → 401 `UNAUTHORIZED`; token inexistente → 401 `UNAUTHORIZED`; (g) sessão vencida (`travel(181)->minutes()`) e sessão com `ended_at` → 401 `SESSION_EXPIRED`, sem criar `AiInteraction`; (h) token válido → 201 com `interaction_id`, a interação nasce com o `restaurant_id` de A; (i) a 16ª consulta da sessão → 429 `RATE_LIMITED`; (j) com `queries_per_restaurant_per_day` = 2, a 3ª consulta do dia no restaurante (mesmo vinda de outra sessão de celular) → 429 `SOFIA_DAILY_LIMIT`, e interações de **tablet** do mesmo restaurante não entram na contagem; (k) `GET /ai/interactions/{id}` de outra sessão de celular do mesmo restaurante → 404; (l) `PATCH /sessions/{id}` com `ended_at` e, depois, a Sofia responde 401 `SESSION_EXPIRED`; (m) token de sessão de celular em `/api/v1/ai/recommend` → 401 e token de tablet em `/api/public/r/{slug}/ai/recommend` → 401; (n) restaurante desligado depois da sessão criada → a Sofia responde 404.
- [ ] **Step 2:** `php artisan test --filter=PublicSession` e `--filter=PublicSofia` → FAIL.
- [ ] **Step 3:** Implementar conforme as Interfaces. Reaproveitar o `AiInteractionController` existente (não copiar a montagem de prompts).
- [ ] **Step 4:** `php artisan test` completo → verde (inclui a suíte da 9.1).
- [ ] **Step 5: Commit** (se autorizado): `feat(backend): sessão curta do celular e tetos da Sofia [Story 9.2]`.

---

### Task 6: Isolamento das rotas públicas

**Files:**
- Create: `backend/tests/Feature/Isolation/PublicApiIsolationTest.php`
- Modify (só se o Task 5 criou consulta crua): `backend/tests/Feature/Isolation/RawQueryAuditTest.php`

**Interfaces:** consome `SeedsTwoRestaurants` (A e B, ambos com celular ligado, cada um com sessão de celular criada pelo fluxo real `POST /sessions`).

- [ ] **Step 1: Escrever os testes** (cada negativo com controle positivo e re-leitura do registro de B): (a) token de sessão de B na rota de A → 401 `UNAUTHORIZED`, com corpo **idêntico** ao de um token inexistente; (b) `compare` com `wine_a_id` de B pela rota de A → 422 com a mesma mensagem de id inexistente; (c) chave do QR de A em `/sessions` de B → 403 `QR_INVALID` e nenhuma sessão criada em B; (d) interação de B lida com o token de A → 404; (e) `PATCH /sessions/{sessaoB}` com o token de A → 404 e a sessão de B segue sem `ended_at`; (f) **guarda de rotas:** toda rota cujo URI começa com `api/public/` tem middleware `public.restaurant:carta` ou `public.restaurant:session` (uma rota pública nova sem ele reprova); (g) com A desligado, B segue 200.
- [ ] **Step 2:** `php artisan test --filter=PublicApiIsolation` → deve passar (o código vem dos Tasks 4 e 5). Fazer **prova de mutação** numa cópia com `vendor` copiado (symlink não pega): (1) remover o `CurrentRestaurant::use` do middleware; (2) mover o lookup da sessão para antes do `use`. Cada uma deve derrubar pelo menos um teste; registrar quais.
- [ ] **Step 3:** `php artisan test` completo → verde, com `RawQueryAuditTest` incluído (se aparecer consulta crua nova, revisar e entrar na allowlist com comentário).
- [ ] **Step 4: Commit** (se autorizado): `test(backend): isolamento das rotas públicas do celular [Story 9.2]`.

---

### Task 7: Entrada web `/r/{slug}` e shell da PWA

**Files:**
- Modify: `backend/routes/tablet.php`
- Test: `backend/tests/Feature/PublicEntryRouteTest.php`

**Interfaces:**
- `GET /r/{slug}` (sem o grupo `web`): se existe restaurante ativo com `phone_access_enabled`, responde `302` para `/tablet/r/{slug}` preservando a query string (`?k=`); senão 404. `{slug}` casa `[A-Za-z0-9_-]+`.
- `GET /tablet/r/{slug}/...` (já atendido pela rota genérica do SPA): quando o `path` começa com `r/`, remover do HTML o `<link rel="manifest" ...>` e responder `Cache-Control: no-cache, private`. Os demais caminhos do tablet seguem como estão.

- [ ] **Step 1: Testes que falham** (mesma montagem de `TabletSpaTest`, index temporário): (a) `GET /r/restaurante-alfa?k=abc` → 302 com `Location` terminando em `/tablet/r/restaurante-alfa?k=abc`; (b) slug inexistente, celular desligado e restaurante inativo → 404; (c) `GET /tablet/r/restaurante-alfa/wines/3` → 200 com o index, **sem** `<link rel="manifest"`, com `X-Robots-Tag: noindex` e `Cache-Control` contendo `no-cache` e `private`; (d) regressão: `GET /tablet/wines` continua com o `<link rel="manifest"`.
- [ ] **Step 2:** `php artisan test --filter=PublicEntryRoute` → FAIL.
- [ ] **Step 3:** Implementar em `routes/tablet.php`; confirmar que `.htaccess` já manda `/r/...` e `/tablet/r/...` ao `index.php` (arquivo/diretório inexistente).
- [ ] **Step 4:** `php artisan test` completo → verde.
- [ ] **Step 5: Commit** (se autorizado): `feat(backend): entrada /r/{slug} e shell da PWA no celular [Story 9.2]`.

---

### Task 8: Backoffice "Acesso por celular"

**Files:**
- Create: `backend/app/Livewire/PhoneAccess.php`, `backend/resources/views/livewire/phone-access.blade.php`
- Modify: `backend/routes/web.php` (`GET /backoffice/acesso-celular`, nome `backoffice.phone-access`), `backend/resources/views/backoffice/layouts/app.blade.php` (item de menu, só para quem tem `restaurant_id`, como "Tablets"), `backend/resources/views/livewire/restaurant-settings.blade.php` (aviso do slug)
- Test: `backend/tests/Feature/Backoffice/PhoneAccessTest.php`

**Interfaces:**
- `PhoneAccess` (Livewire, layout `backoffice.layouts.app`, título "Acesso por celular"): `mount()` exige `restaurant_id` (senão 403) e `authorize('update', $restaurant)`; o restaurante vem sempre do usuário logado (nenhum id vem do cliente). Ações: `enable(string $mode)`, `disable()`, `setMode(string $mode)`, `regenerateKey()`, `downloadQr()` (`streamDownload` de `vinia-qr-{slug}.svg`, `image/svg+xml`). Todas via `PhoneAccessService`. A view mostra: estado, texto de risco (carta sem custo de IA; a Sofia no celular consome créditos; QR permanente pode ser usado fora do local; recomendação do tablet), seletor mensal/permanente, QR em SVG (`QrCode::format('svg')->size(220)->margin(1)->generate($service->entryUrl($restaurant))`), o link, a validade, e os avisos de `expiring` (com dias restantes) e `expired`. Pedir confirmação ("o QR impresso deixa de funcionar") antes de `regenerateKey()`.
- Em Configurações, quando `phone_access_enabled`, um aviso junto ao campo do slug: alterar o endereço invalida o QR impresso.

- [ ] **Step 1: Testes que falham** (`Livewire::test`): (a) gerente de A vê o estado desligado e o texto de risco; (b) `enable('monthly')` persiste, mostra SVG e o link com `?k=`; (c) `setMode('permanent')` zera a validade; (d) `regenerateKey()` troca a chave e a antiga dá `QR_INVALID` no serviço; (e) usuário de B não altera A (a tela só opera no restaurante do próprio usuário); (f) admin sem restaurante → 403; (g) aviso de "expira em N dias" quando `expiring` e de "expirado" quando `expired`; (h) `downloadQr()` responde `image/svg+xml` com o SVG; (i) o aviso do slug aparece em Configurações só com o celular ligado; (j) o item de menu só aparece para usuário com restaurante.
- [ ] **Step 2:** `php artisan test --filter=PhoneAccessTest` → FAIL.
- [ ] **Step 3:** Implementar seguindo o visual do backoffice existente (classes `bo-*` de `tablet-list.blade.php`), com tema claro/escuro funcionando.
- [ ] **Step 4:** `php artisan test` completo → verde (inclui `ThemeScreensRegressionTest`; se ele listar telas, incluir a nova).
- [ ] **Step 5: Commit** (se autorizado): `feat(backend): tela Acesso por celular com QR mensal ou permanente [Story 9.2]`.

---

### Task 9: Frontend — modo de acesso, sessão e cliente da API

**Files:**
- Create: `frontend/src/services/access.ts`, `frontend/src/services/phoneSession.ts`
- Modify: `frontend/src/services/api.ts`, `frontend/src/types/index.ts`
- Test: `frontend/src/services/access.test.ts`, `frontend/src/services/phoneSession.test.ts`, `frontend/src/services/api.phone.test.ts`

**Interfaces:**
- `access.ts`: `type AccessMode = { kind: 'tablet' } | { kind: 'phone'; slug: string; basename: string }`; `detectAccessMode(pathname: string): AccessMode` com a regex `^((?:/tablet)?/r/([A-Za-z0-9_-]+))(?:/|$)` (grupo 1 = `basename`, grupo 2 = `slug`; qualquer outro caminho = `tablet`); `export const accessMode = detectAccessMode(window.location.pathname)`.
- `phoneSession.ts`: `getDeviceId(): string` (`localStorage['vinia_device_id']`, cria com `crypto.randomUUID()`); `captureQrKey(slug: string): void` (lê `?k=` da URL, grava em `sessionStorage['vinia_qr_key:'+slug]` e remove só o `k` da URL com `history.replaceState`, mantendo o resto); `getQrKey(slug): string | null`; `savePhoneSession(slug, {sessionId, token, expiresAt})`, `getPhoneSession(slug): {...} | null` (devolve `null` se `expiresAt` já passou no relógio do aparelho), `clearPhoneSession(slug)` (tudo em `sessionStorage`); `type PhoneErrorCode = 'QR_MISSING' | 'QR_INVALID' | 'QR_EXPIRED' | 'RATE_LIMITED' | 'SOFIA_DAILY_LIMIT' | 'SESSION_EXPIRED'`; `phoneErrorCode(err: unknown): PhoneErrorCode | null` (lê `error.code` do corpo ou o erro local `QR_MISSING`).
- `api.ts`: `resolveToken()` e `pointManifestToTablet` só rodam no modo `tablet`. Modo `phone`: prefixo `/api/public/r/${slug}` no lugar de `/api/v1`; GETs da carta sem `Authorization`; `createSession()` lança erro local `QR_MISSING` (sem tocar a rede) se não houver chave, senão faz `POST /sessions` com `{key}` e `X-Device-Id`, grava a sessão e devolve `{ session_id }`; `updateSession`, `recommend` e `getInteraction` enviam `Authorization: Bearer <token da sessão>`; um interceptor de resposta limpa a sessão guardada em 401 com `SESSION_EXPIRED`. O modo `tablet` não muda de comportamento.

- [ ] **Step 1: Testes que falham.** `access.test.ts`: `/tablet/`, `/tablet/wines` e `/` → `tablet`; `/r/restaurante-alfa` → phone, slug `restaurante-alfa`, basename `/r/restaurante-alfa`; `/tablet/r/restaurante-alfa/wines/3` → phone com basename `/tablet/r/restaurante-alfa`; `/r/` → `tablet`. `phoneSession.test.ts`: `captureQrKey` grava na `sessionStorage` (não na `localStorage`) e remove só o `k` de `?k=abc&x=1`; `getDeviceId` é estável entre chamadas e tem formato UUID; `getPhoneSession` devolve `null` com `expiresAt` no passado; `phoneErrorCode` lê o código do corpo de um `AxiosError`. `api.phone.test.ts` (axios mockado, modo phone): `createSession` sem chave lança `QR_MISSING` e **não** chama a rede; com chave faz `POST` em `/api/public/r/restaurante-alfa/sessions` com o corpo `{key}` e `X-Device-Id`; `getWines` não envia `Authorization`; `recommend` envia o token da sessão; resposta 401 `SESSION_EXPIRED` limpa a sessão guardada; no modo tablet `createSession` segue em `/api/v1/sessions` com o token do tablet.
- [ ] **Step 2:** `cd frontend && npm test -- --run src/services` → FAIL.
- [ ] **Step 3:** Implementar. Os testes do modo phone mudam a URL com `window.history.pushState` antes de importar o módulo (`vi.resetModules()`), já que `accessMode` é calculado na carga.
- [ ] **Step 4:** `npm test -- --run && npm run typecheck && npm run lint` → verdes (os 570 testes existentes intactos).
- [ ] **Step 5: Commit** (se autorizado): `feat(frontend): modo de acesso celular, sessão curta e cliente da API pública [Story 9.2]`.

---

### Task 10: Frontend — telas no modo celular

**Files:**
- Create: `frontend/src/components/PhoneGate.tsx`
- Modify: `frontend/src/App.tsx`, `frontend/src/main.tsx`, `frontend/src/pages/EntryPage.tsx`, `frontend/src/components/InactivityGuard.tsx`, `frontend/src/pages/AssistantPage.tsx`, `frontend/src/components/ThemeProvider.tsx`, `frontend/src/hooks/useWines.ts`
- Test: um arquivo `*.phone.test.tsx` ao lado de cada tela alterada, mais `frontend/src/components/PhoneGate.test.tsx`

**Interfaces:**
- `main.tsx`/`App.tsx`: no modo phone chamar `captureQrKey(slug)` antes da primeira renderização e usar `accessMode.basename` como `basename` do `BrowserRouter` (tablet continua com `BASE_URL`).
- `PhoneGate({children})`: no modo phone, se `useRestaurant()` falhar com 404, mostra uma tela "Carta indisponível" (`role="alert"`, "Esta carta não está disponível no momento. Fale com o nosso atendimento.") sem botão de tentar de novo; nos demais casos renderiza `children`. No modo tablet é transparente. Envolve `AppRoutes`.
- `EntryPage` (phone): "Ver Carta" vai direto para `/wines`, **sem** `createSession` (a carta é pública; a sessão nasce só quando a pessoa usa a Sofia).
- `InactivityGuard` (phone): só `<Outlet />`, sem temporizadores nem aviso.
- `AssistantPage` (phone): a criação preguiçosa de sessão em `sendRequest` já existe e passa a usar o `createSession` do modo phone. Mensagens por `phoneErrorCode`: `QR_MISSING` "Para falar com a Sofia, escaneie o QR code do restaurante."; `QR_INVALID` "Este QR code não é válido. Escaneie novamente o QR code do restaurante."; `QR_EXPIRED` "O QR code deste restaurante expirou. Peça um novo ao nosso atendimento."; `RATE_LIMITED` ao iniciar sessão "Você já usou a Sofia várias vezes hoje. Chame o nosso sommelier."; `SOFIA_DAILY_LIMIT` "A Sofia atingiu o limite de hoje neste restaurante. Chame o nosso sommelier."; 429 `RATE_LIMITED` ao consultar mantém a mensagem atual de limite da sessão. `SESSION_EXPIRED` em `recommend`: limpar o `sessionId`, criar outra sessão e repetir a consulta **uma vez**, sem mensagem de erro.
- `ThemeProvider`: no modo phone o tema **não** volta ao escuro quando a sessão da Sofia começa nem é gravado em `localStorage` (o escopo do tema no celular é constante); o tablet mantém a regra da Story 6.8.
- `useWines`: `refetchInterval` de 5 min no modo phone (60 s no tablet), para não somar requisições no wifi compartilhado.

- [ ] **Step 1: Testes que falham** (API e `accessMode` mockados): (a) `PhoneGate` com 404 mostra "Carta indisponível" e não renderiza `children`; com sucesso renderiza; (b) `EntryPage` phone: clicar "Ver Carta" navega para `/wines` e `createSession` **não** é chamado; (c) `InactivityGuard` phone: com timers falsos, 10 min sem interação não chamam `updateSession` nem mostram aviso; (d) `AssistantPage` phone: sem chave, a consulta mostra a mensagem de `QR_MISSING` e não chama `recommend`; `QR_EXPIRED` e `SOFIA_DAILY_LIMIT` mostram as mensagens acima; `SESSION_EXPIRED` em `recommend` cria nova sessão e repete uma vez (e uma segunda falha vira erro); (e) `ThemeProvider` phone: alternar para o claro e depois iniciar a sessão da Sofia mantém o claro e nada é gravado em `localStorage['vinia.theme']`; (f) `useWines` phone usa 300000 ms de refetch; (g) regressão: testes do modo tablet existentes seguem passando.
- [ ] **Step 2:** `npm test -- --run` → FAIL nos novos.
- [ ] **Step 3:** Implementar. Reaproveitar os componentes e tokens atuais (sem estilo novo, exceto a tela "Carta indisponível" no padrão visual da capa).
- [ ] **Step 4:** `npm test -- --run && npm run typecheck && npm run lint && npm run build` → verdes. Atenção: o `npm run build` regrava `backend/public/tablet`.
- [ ] **Step 5: Commit** (se autorizado): `feat(frontend): carta e Sofia no modo celular [Story 9.2]`.

---

### Task 11: PWA — cache offline da carta pública

**Files:**
- Create: `frontend/src/pwa/cartaCache.ts`
- Modify: `frontend/vite.config.ts` (`workbox.runtimeCaching`)
- Test: `frontend/src/pwa/cartaCache.test.ts`

**Interfaces:**
- `cartaCache.ts` exporta `CARTA_CACHE = 'vinia-carta'` e `isCartaRequest({ url, request }: { url: URL; request: Request }): boolean`: verdadeiro só para `GET` com `url.pathname` casando `^/api/public/r/[A-Za-z0-9_-]+/(restaurant|wines(/\d+)?)$`. A função é serializada pelo Workbox para dentro do `sw.js`, então deve ser **autocontida** (sem imports nem variáveis de fora do corpo).
- `vite.config.ts`: `runtimeCaching: [{ urlPattern: isCartaRequest, handler: 'NetworkFirst', options: { cacheName: CARTA_CACHE, networkTimeoutSeconds: 4, expiration: { maxEntries: 60, maxAgeSeconds: 7 * 24 * 3600 }, cacheableResponse: { statuses: [200] } } }]`. O `navigateFallbackDenylist` atual (`?token=`) não muda: navegações com `?k=` caem no `index.html` em cache, o que é o desejado offline.

- [ ] **Step 1: Testes que falham** (`isCartaRequest`): (a) `GET /api/public/r/restaurante-alfa/restaurant`, `/wines` e `/wines/12` → verdadeiro; (b) `POST` em qualquer um → falso; (c) `GET /api/public/r/restaurante-alfa/ai/interactions/5` → falso; (d) `/api/public/r/restaurante-alfa/sessions` → falso; (e) `/api/v1/wines` (tablet) → falso; (f) `/api/public/r/a/b/wines` → falso; (g) `isCartaRequest.toString()` não referencia identificadores externos (`CARTA_CACHE`, `import`).
- [ ] **Step 2:** `npm test -- --run src/pwa` → FAIL.
- [ ] **Step 3:** Implementar e configurar o Workbox. Depois de `npm run build`, conferir que `backend/public/tablet/sw.js` contém `vinia-carta` e **não** contém o padrão de `/ai/` nem de `/sessions`.
- [ ] **Step 4:** `npm test -- --run && npm run typecheck && npm run lint && npm run build` → verdes.
- [ ] **Step 5: Commit** (se autorizado): `feat(frontend): cache offline da carta pública no service worker [Story 9.2]`.

---

### Task 12: Verificação ponta a ponta e fechamento (feito pelo controlador, não delegado)

**Files:**
- Modify: `vinia-docs/docs/stories/9.2.story.md` (File List, Dev Agent Record, Change Log, status InReview)

- [ ] **Step 1:** `php artisan test` (backend) e `npm test -- --run`, `typecheck`, `lint`, `build` (frontend): todos verdes; anotar as contagens.
- [ ] **Step 2: Navegador de verdade** (Playwright em Chromium, servidor local com `npm run build` feito, banco local com um restaurante com celular ligado): (a) abrir `/r/{slug}?k={chave}` → redireciona, a carta aparece e `?k=` some da URL; (b) abrir a Sofia → sessão criada e uma resposta (Groq mockado ou chave real de desenvolvimento); (c) esgotar as 15 consultas → mensagem de limite; (d) com o service worker ativo, `context.setOffline(true)` e recarregar → a carta aparece com os dados da última visita e a Sofia mostra a mensagem de indisponível (nada da Sofia vem do cache); (e) regenerar o QR no backoffice → a chave antiga mostra "QR inválido" e a carta segue; (f) desligar o celular → a página mostra "Carta indisponível"; (g) fechar a aba e reabrir `/tablet/r/{slug}` sem `?k=` → Sofia pede o QR. Guardar capturas e o resultado de cada item no relatório.
- [ ] **Step 3:** Conferir as migrations em MySQL 8 (já feito no Task 2) e rodar a suíte backend também em MySQL, como na 9.1.
- [ ] **Step 4:** Revisão final do branch inteiro (modelo mais capaz) com foco no Review Focus acima; corrigir o que ela achar em **uma** rodada e re-revisar.
- [ ] **Step 5:** Atualizar a Story 9.2 (File List, Dev Agent Record com os rulings, Change Log, status InReview), o cofre (Status do Vinia, padrão "sessão curta do comensal por QR", decisões das travas) e o grafo (`/graphify . --update`).
- [ ] **Step 6:** Mostrar ao Rafael o menu da skill `finishing-a-development-branch`.

---

## Self-review

- **Cobertura da spec (Fase 2 do §8):** rota `/r/{slug}` → Tasks 4 e 7; QR com validade de 1 mês ou permanente e explicação de risco → Tasks 2 e 8; sessão curta → Task 5; travas da Sofia (sessão, consultas, aparelho, IP) → Tasks 2, 3 e 5, com o teto diário provisório cobrindo o anti-objetivo de custo; PWA com cache offline → Tasks 10 e 11; cache de perguntas frequentes e cota do plano ficam explicitamente fora (Fase 4).
- **Consistência de nomes:** `ComensalActor` (Task 3) é usado nos Tasks 5 e 6; `PhoneAccessService` (Task 2) nos Tasks 5 e 8; `public.restaurant:carta|session` nos Tasks 4, 5 e 6; `PhoneErrorCode` (Task 9) nos Tasks 9 e 10; `CARTA_CACHE`/`isCartaRequest` só no Task 11.
- **Proporção:** o plano descreve interfaces, valores e asserções; os corpos de código ficam com o implementador.
