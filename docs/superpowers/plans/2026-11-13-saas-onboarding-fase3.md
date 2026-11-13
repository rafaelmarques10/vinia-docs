# Vinia SaaS — Fase 3: Onboarding self-service — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Um restaurante desconhecido se cadastra em `/cadastro`, valida o e-mail, percorre um assistente de 4 passos e convida a equipe, com o teste de 14 dias travado por e-mail e por CPF/CNPJ, sem ajuda do Rafael.

**Architecture:** Livewire dentro do backoffice atual, usando o `Auth` do Laravel (`MustVerifyEmail`, password broker). O teste fica numa tabela própria `trial_claims` (sem escopo de restaurante, guardada mesmo se a conta for apagada); `restaurants.active` passa a ser aplicado também ao tablet e ao backoffice. Acesso por celular fica desligado no plano `trial`.

**Tech Stack:** Laravel 13, Livewire 4, PHPUnit (SQLite em memória; CI roda também MySQL 8), notificações em fila (`database`, cron de 1 minuto), SMTP já configurado em `MAIL_*`.

**Spec:** `docs/superpowers/specs/2026-11-13-vinia-onboarding-fase3-design.md` (e o spec-mãe `2026-11-10-vinia-saas-design.md`, Fase 3). Em caso de conflito, vale o design da Fase 3.

## Global Constraints

- Caminhos relativos a `vinia-src`; código em `backend/`. Comandos de teste: `cd backend && php artisan test --filter=<Classe>`; suíte completa `php artisan test` (baseline 1010). Toda suíte passa em SQLite **e** MySQL 8: nenhum teste usa aspas de identificador nem SQL de um banco só.
- **Produção é Hostinger compartilhada: sem `schedule:run`, sem worker contínuo.** Comandos periódicos são rodados por cron direto no hPanel (linha no docblock do comando, como `PurgeComensalSessions`); o `DEPLOY-HOSTINGER.md` **não** é editado (alterações do Rafael não commitadas).
- **CPF nunca em claro** (banco, log, auditoria, e-mail): só HMAC-SHA256 com chave própria `TRIAL_HASH_KEY`. CNPJ pode ficar em claro (só dígitos).
- Cadastro e convite **nunca** criam `admin`; `role` e `restaurant_id` nunca vêm de campo de formulário; atribuição explícita (o `#[Fillable]` do `User` inclui `role` e `restaurant_id`).
- Respostas de cadastro (casos "teste em andamento"), recuperação de senha e convite **não revelam** se existe conta, **exceto** a mensagem explícita "teste de 14 dias expirou" (decisão do Rafael).
- Trial = 14 dias a partir da **verificação** do e-mail; restaurante de cadastro nasce `active = false` e `plan = 'trial'`; acesso por celular desligado e **não pode ser ligado** enquanto `plan = 'trial'`.
- Restaurantes criados à mão (sem `trial_claim`) não mudam: continuam sem lembrete, sem bloqueio e sem passar pelo assistente.
- Mensagens ao usuário em português com acentos; commits convencionais com `[Story 9.4]` e `Co-Authored-By`; commits só na branch de trabalho (`git branch --show-current`, nunca `checkout/switch/stash`); nunca `git push`.
- Isolamento multi-tenant: telas novas com dado de restaurante usam `restaurant_id` do usuário logado (nunca de entrada), têm teste A×B, e consultas cruas entram no `RawQueryAuditTest::ALLOWED` com justificativa.
- Testes existentes só mudam quando o comportamento antigo foi trocado de propósito (lista no Dev Agent Record).

## Review Focus

1. **Mesmo e-mail "disfarçado"** (`Joao.Silva+x@Gmail.com` x `joaosilva@gmail.com`) ou mesmo CPF com máscara/sem máscara: deve contar como o mesmo teste (Task 2, 3 e 4).
2. **CPF em claro em qualquer lugar** (coluna, `Log`, canal `audit`, corpo do e-mail): nunca (Task 3 e 4).
3. **Usuário não verificado ou com teste encerrado** operando mesmo assim: restaurante inativo não abre tablet, carta pública nem Sofia, e `role=admin` no corpo do formulário é ignorado (Task 4 e 5).
4. **CNPJ do passo 1 já usado:** a conta fica, entra, vê "teste expirou" e nada mais; nada apagado (Task 7).
5. **Convite:** token reutilizado, vencido ou de outro restaurante; e-mail que já tem conta (resposta neutra); gerente convidando gerente; dono rebaixando a si mesmo; A×B na tela Equipe (Task 10).

---

### Task 1: Dados, config e perfil `sommelier`

**Files:**
- Create: `backend/config/onboarding.php`, `backend/app/Models/TrialClaim.php`, migrations `backend/database/migrations/2026_11_13_000001_create_trial_claims_table.php`, `..._000002_add_onboarding_columns.php`
- Modify: `backend/app/Models/User.php`, `backend/app/Models/Restaurant.php`, `backend/app/Services/TabletService.php`, `backend/.env.example`, `backend/database/factories/RestaurantFactory.php`
- Test: `backend/tests/Feature/Migrations/OnboardingMigrationsTest.php`, `backend/tests/Unit/Models/TrialClaimTest.php`

**Interfaces:**
- Produces: `config('onboarding')` com `trial_days` (14), `reminder_days` ([7,12,14]), `unverified_ttl_days` (7), `invite_ttl_days` (7), `hash_key` (`env('TRIAL_HASH_KEY')`), `contact_email` (`env('ONBOARDING_CONTACT_EMAIL')`, padrão `config('landing.notify_to')`); `User::ROLES` ganha `'sommelier'` e `ROLE_LABELS['sommelier'] = 'Sommelier'`; `User` implementa `MustVerifyEmail`.
- Produces: tabela `trial_claims` (`id`, `email_key` string 190 indexada, `cpf_hash` string 64 nullable indexada, `cnpj` string 14 nullable indexada, `restaurant_id` nullable FK `nullOnDelete`, `started_at`, `ends_at`, `ended_at` nullable, `last_reminder_day` unsigned tinyint nullable, timestamps). Model `TrialClaim` **sem** `BelongsToRestaurant` (consulta global por desenho); métodos `isActive(): bool` (`ended_at` nulo e `ends_at` futuro) e `isExpired(): bool`.
- Produces: colunas `users.signup_cpf_hash` (string 64 nullable) e `users.signup_cnpj` (string 14 nullable), ambas **fora** do `#[Fillable]`; `restaurants.onboarding_completed_at` (timestamp nullable; **backfill `now()` para todos os restaurantes existentes** na migration); `wines.is_sample` boolean default false. `TabletService::PLAN_LIMITS` ganha `'trial' => 1`.

- [ ] **Step 1: Write the failing tests** — `OnboardingMigrationsTest`: as colunas/tabela existem; restaurante pré-existente (criado antes do `up()` da segunda migration, via o padrão do `PhoneAccessMigrationsTest`) fica com `onboarding_completed_at` preenchido; `down()` reverte sem erro. `TrialClaimTest`: `isActive()` verdadeiro com `ends_at` futuro e `ended_at` nulo, falso com `ended_at` preenchido ou `ends_at` passado; apagar o restaurante deixa o claim com `restaurant_id` nulo. `UserTest` (existente ou novo): `User::ROLES` contém `sommelier`; `new User` é `MustVerifyEmail`.
- [ ] **Step 2: Run** `php artisan test --filter="OnboardingMigrations|TrialClaim"` → FAIL.
- [ ] **Step 3: Implement** migrations (sem `->change()`; padrão de tolerância ao deploy: nada com `$attributes` no model), model, config, `.env.example` (`TRIAL_HASH_KEY=` com comentário "gere com `php artisan tinker --execute=\"echo base64_encode(random_bytes(32));\"`; trocar invalida a trava"), `User` (`MustVerifyEmail`, ROLES), `TabletService::PLAN_LIMITS`, factory `RestaurantFactory` com estado `trial()`.
- [ ] **Step 4: Run** a suíte completa → verde (conferir que `UserManagementTest` e `RestaurantPlanTest` seguem verdes; se uma lista de perfis for afirmada por igualdade, atualizar deliberadamente e registrar).
- [ ] **Step 5: Commit** `feat(backend): tabela do teste, colunas do onboarding e perfil sommelier [Story 9.4]`.

### Task 2: Documento (CPF/CNPJ) e identidade de e-mail

**Files:**
- Create: `backend/app/Support/Onboarding/Document.php`, `backend/app/Support/Onboarding/EmailIdentity.php`, `backend/app/Rules/CpfOrCnpj.php`
- Test: `backend/tests/Unit/Onboarding/DocumentTest.php`, `backend/tests/Unit/Onboarding/EmailIdentityTest.php`

**Interfaces:**
- Produces: `Document::parse(?string $input): ?Document` (remove máscara; 11 dígitos com dígitos verificadores válidos = `cpf`; 14 válidos = `cnpj`; sequências repetidas como `111.111.111-11` e qualquer outra coisa = `null`); propriedades públicas `string $type` (`'cpf'|'cnpj'`) e `string $digits`; `masked(): string` (CPF `***.***.***-12`, CNPJ completo formatado).
- Produces: `EmailIdentity::key(string $email): string` (trim, minúsculas, remove `+tag` do local em **qualquer** domínio, remove pontos do local só em `gmail.com`/`googlemail.com`, e trata `googlemail.com` como `gmail.com`).
- Produces: regra `CpfOrCnpj` (`ValidationRule`) com a mensagem "Informe um CPF ou CNPJ válido."

- [ ] **Step 1: Write the failing tests** — CPF `529.982.247-25` e `52998224725` válidos; `529.982.247-26` inválido; `111.111.111-11` inválido; CNPJ `11.222.333/0001-81` válido; `11.222.333/0001-82` inválido; 12 dígitos = `null`; `masked()` de CPF nunca contém os 11 dígitos. E-mail: `Joao.Silva+x@Gmail.com` → `joaosilva@gmail.com`; `a.b@empresa.com.br` mantém os pontos; `x+y@empresa.com` → `x@empresa.com`; `a@googlemail.com` → `a@gmail.com`.
- [ ] **Step 2: Run** `--filter="DocumentTest|EmailIdentityTest"` → FAIL.
- [ ] **Step 3: Implement** os três arquivos (algoritmo módulo 11 padrão).
- [ ] **Step 4: Run** → PASS; suíte completa verde.
- [ ] **Step 5: Commit** `feat(backend): validação de CPF/CNPJ e identidade de e-mail para a trava do teste [Story 9.4]`.

### Task 3: `TrialService` (a trava)

**Files:**
- Create: `backend/app/Services/TrialService.php`, `backend/app/Support/Onboarding/TrialLookup.php`
- Test: `backend/tests/Feature/Onboarding/TrialServiceTest.php`

**Interfaces:**
- Consumes: `Document`, `EmailIdentity::key`, `TrialClaim`, `config('onboarding')`.
- Produces: `TrialLookup` com `status` (`'available'|'active'|'expired'`). `TrialService::hashCpf(string $digits): string` (HMAC-SHA256 com `config('onboarding.hash_key')`; lança `LogicException` se a chave estiver vazia). `TrialService::lookup(string $email, ?Document $doc): TrialLookup` (procura claim por `email_key` **ou** pelo documento: `cpf_hash` para CPF, `cnpj` para CNPJ; se qualquer claim encontrado estiver ativo → `active`; se achou e todos expirados/encerrados → `expired`; senão `available`). `TrialService::start(User $owner, Restaurant $restaurant): TrialClaim` (cria o claim com `started_at = now()`, `ends_at = now() + trial_days`, `email_key`, `cpf_hash`/`cnpj` vindos de `signup_*` do usuário e então **zera** `signup_*`; define `restaurants.plan = 'trial'` já definido e `active = true`). `TrialService::endBecauseCnpjUsed(Restaurant $restaurant, string $cnpjDigits): bool` (se existir **outro** claim com esse CNPJ: marca o claim do restaurante como `ended_at = now()`, `restaurants.active = false`, e devolve `true`; senão grava o `cnpj` no claim do restaurante e devolve `false`). `TrialService::daysRemaining(Restaurant): ?int` (`null` sem claim ou encerrado).

- [ ] **Step 1: Write the failing tests** — com `config(['onboarding.hash_key' => 'k'])`: (a) `lookup` de e-mail inédito → `available`; (b) após `start`, o mesmo e-mail em variante (`Joao.Silva+1@Gmail.com`) → `active`; (c) outro e-mail com o **mesmo CPF** (com e sem máscara) → `active`; (d) claim com `ends_at` passado → `expired` para e-mail e para CPF; (e) CNPJ idem; (f) `cpf_hash` nunca contém os dígitos e é determinístico; `hashCpf` sem chave lança; (g) `start` zera `signup_cpf_hash` e `signup_cnpj` do usuário; (h) `endBecauseCnpjUsed` com CNPJ de claim alheio → `true`, claim próprio encerrado, restaurante `active=false`, **nenhum registro apagado**; com CNPJ inédito → `false` e grava o `cnpj`; (i) o CNPJ do **próprio** restaurante repetido não conta como alheio; (j) `daysRemaining` = 14 logo após `start` e `null` após encerrar.
- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement** `TrialService` e `TrialLookup`. O `lookup` consulta `TrialClaim` sem escopo (a tabela não é de tenant): justificar no `RawQueryAuditTest` só se usar SQL cru (preferir Eloquent).
- [ ] **Step 4: Run** → PASS; suíte completa verde.
- [ ] **Step 5: Commit** `feat(backend): TrialService com a trava do teste por e-mail, CPF e CNPJ [Story 9.4]`.

### Task 4: Cadastro público (`/cadastro`)

**Files:**
- Create: `backend/app/Services/SignupService.php`, `backend/app/Livewire/Signup.php`, `backend/resources/views/livewire/signup.blade.php`, `backend/resources/views/signup.blade.php` (layout público no estilo de `auth/login`)
- Modify: `backend/routes/web.php`, `backend/app/Providers/AppServiceProvider.php` (limiter `signup`: 5/h por IP e 3/h por e-mail-chave)
- Test: `backend/tests/Feature/Onboarding/SignupTest.php`

**Interfaces:**
- Consumes: `TrialService::lookup/hashCpf`, `Document::parse`, `EmailIdentity::key`, `RestaurantService::generateSlug`.
- Produces: rota `GET /cadastro` (`signup.show`, só visitante) e o componente `Signup`. `SignupService::register(array $data): SignupOutcome` com `status` (`'created'|'active_trial'|'expired_trial'`) e `user` (`?User`); `$data` = `restaurant_name`, `name`, `email`, `password`, `document`. Em `created`: cria **numa transação** `Restaurant` (`active=false`, `plan='trial'`, `slug` único via `generateSlug`, `onboarding_completed_at` nulo) e `User` (`role='owner'`, `restaurant_id`, senha `Password::min(8)`, `signup_cpf_hash` ou `signup_cnpj`), dispara `Registered` (envia a verificação, Task 5) e faz login. Em `active_trial`: nada é criado, redireciona ao login com a mensagem genérica "Se este e-mail já tem uma conta, entre por aqui ou recupere a senha." Em `expired_trial`: nada é criado; mostra "Seu teste de 14 dias expirou." + o contato `config('onboarding.contact_email')`.

- [ ] **Step 1: Write the failing tests** — (a) cadastro válido (CPF) cria restaurante `active=false`, `plan='trial'`, usuário `owner` **não verificado**, `signup_cpf_hash` preenchido e nunca o CPF em nenhuma coluna (varrer `DB::table('users')`/`restaurants` com `json_encode`); (b) CNPJ válido grava `signup_cnpj`; (c) documento inválido → erro de validação; (d) `role=admin` e `restaurant_id=1` no corpo são ignorados; (e) e-mail com teste ativo (variante Gmail) → nada criado, mensagem genérica; (f) CPF de teste ativo com **outro** e-mail → idem; (g) e-mail/CPF/CNPJ de teste **expirado** → mensagem de expirado, nada criado; (h) e-mail já usado por um usuário existente sem claim (restaurante manual) → resposta genérica, nada criado; (i) slug duplicado vira `nome-2`; (j) limiter `signup` retorna 429 na 6ª tentativa do mesmo IP; (k) o log (`Log::spy`/`audit`) nunca recebe o CPF; (l) usuário logado/visitante autenticado é redirecionado.
- [ ] **Step 2: Run** `--filter=SignupTest` → FAIL.
- [ ] **Step 3: Implement** serviço, componente Livewire (validação por `CpfOrCnpj`), views, rota e limiter. Auditoria (`Log::channel('audit')`) só com ids e `status`, nunca e-mail nem documento.
- [ ] **Step 4: Run** → PASS; suíte completa verde.
- [ ] **Step 5: Commit** `feat(backend): cadastro público com trava do teste [Story 9.4]`.

### Task 5: Verificação de e-mail e início do trial

**Files:**
- Create: `backend/app/Notifications/VerifyEmailPt.php`, `backend/app/Listeners/StartTrialOnVerification.php`, `backend/resources/views/auth/verify-email.blade.php`
- Modify: `backend/routes/web.php`, `backend/app/Models/User.php` (`sendEmailVerificationNotification` usa `VerifyEmailPt`), `backend/app/Providers/AppServiceProvider.php` (limiter `verification-resend`: 3/h por usuário), `backend/resources/views/backoffice/layouts/app.blade.php` (faixa fixa "Confirme seu e-mail" com botão de reenviar)
- Test: `backend/tests/Feature/Onboarding/EmailVerificationTest.php`

**Interfaces:**
- Consumes: `TrialService::start`, evento `Illuminate\Auth\Events\Verified`.
- Produces: rotas `verification.notice` (`GET /backoffice/email/verificar`), `verification.verify` (`GET /backoffice/email/verificar/{id}/{hash}`, `signed`, `throttle:6,1`), `verification.send` (`POST`, limiter `verification-resend`). `VerifyEmailPt` implementa `ShouldQueue`, link assinado com validade de 24 h, texto em português. O listener chama `TrialService::start($user, $user->restaurant)` **somente** se o usuário tem `signup_cpf_hash` ou `signup_cnpj` (auto-cadastro) e ainda não há claim; é idempotente.

- [ ] **Step 1: Write the failing tests** — (a) `Notification::fake()`: `Signup` envia `VerifyEmailPt` na fila; (b) acessar o link assinado verifica o e-mail, cria `TrialClaim` com `ends_at = +14 dias`, liga `restaurants.active`, e zera `signup_*`; (c) link adulterado/expirado → 403 e nada muda; (d) verificar duas vezes não cria dois claims; (e) usuário **criado por admin** (sem `signup_*`) que verifica o e-mail não gera claim nem muda `active`; (f) reenvio respeita o limiter e responde igual para qualquer usuário; (g) a faixa "Confirme seu e-mail" aparece no layout para não verificado e some depois.
- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement** rotas (grupo `auth`, **sem** `verified`: o assistente é acessível antes), notificação, listener registrado em `AppServiceProvider::boot` (`Event::listen`), view e faixa.
- [ ] **Step 4: Run** → PASS; suíte completa verde (conferir `AccountTest`: trocar o e-mail em "Minha conta" **não** deve exigir nova verificação nesta fase; se o teste existente afirmar `email_verified_at`, registrar).
- [ ] **Step 5: Commit** `feat(backend): verificação de e-mail inicia o teste de 14 dias [Story 9.4]`.

### Task 6: Recuperação de senha

**Files:**
- Create: `backend/app/Notifications/ResetPasswordPt.php`, `backend/app/Http/Controllers/Backoffice/PasswordResetController.php`, `backend/resources/views/auth/forgot-password.blade.php`, `backend/resources/views/auth/reset-password.blade.php`
- Modify: `backend/routes/web.php`, `backend/app/Models/User.php` (`sendPasswordResetNotification`), `backend/resources/views/auth/login.blade.php` (link "Esqueci a senha"), `backend/app/Providers/AppServiceProvider.php` (limiter `password-reset`: 5/h por IP, 3/h por e-mail-chave)
- Test: `backend/tests/Feature/Auth/PasswordResetTest.php`

**Interfaces:**
- Produces: rotas `password.request` (`GET /backoffice/senha/esqueci`), `password.email` (`POST`), `password.reset` (`GET /backoffice/senha/redefinir/{token}`), `password.update` (`POST`), todas só para visitante; usa o password broker `users` com a tabela `password_reset_tokens` existente. A resposta do `POST password.email` é **sempre** "Se este e-mail tiver conta, enviaremos o link." (existente ou não, ativa ou desativada).

- [ ] **Step 1: Write the failing tests** — (a) e-mail existente recebe `ResetPasswordPt` na fila; (b) e-mail inexistente recebe a **mesma** resposta e nenhuma notificação; (c) usuário desativado (`active=false`) idem sem enviar; (d) token válido redefine a senha, invalida o token e a senha antiga deixa de entrar; (e) token inválido/expirado (60 min) → erro e nada muda; (f) a senha nova segue `Password::min(8)`; (g) limiter dá 429; (h) o log nunca recebe o token nem a senha.
- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement.** Reutilizar `User::normalizeEmail`.
- [ ] **Step 4: Run** → PASS; suíte completa verde.
- [ ] **Step 5: Commit** `feat(backend): recuperação de senha por e-mail [Story 9.4]`.

### Task 7: Restaurante inativo de verdade e página "teste encerrado"

**Files:**
- Create: `backend/app/Http/Middleware/EnsureRestaurantUsable.php`, `backend/resources/views/backoffice/trial-ended.blade.php`
- Modify: `backend/app/Http/Middleware/TabletAuthentication.php`, `backend/bootstrap/app.php` (alias `restaurant.usable`), `backend/routes/web.php`, `backend/app/Livewire/Concerns/*` só se necessário
- Test: `backend/tests/Feature/Onboarding/InactiveRestaurantTest.php`

**Interfaces:**
- Consumes: `TrialService::endBecauseCnpjUsed` (Task 3).
- Produces: `TabletAuthentication` passa a recusar (mesma resposta de token inválido) tablet cujo **restaurante** esteja `active = false`. Middleware `EnsureRestaurantUsable` (alias `restaurant.usable`, no grupo `auth` do backoffice **exceto** `logout`, `conta*`, verificação de e-mail, `onboarding*` e `trial-ended`): usuário não-admin, **verificado**, cujo restaurante está `active=false` com claim encerrado/expirado é redirecionado a `backoffice.trial.ended` (`GET /backoffice/teste-encerrado`: "Seu teste de 14 dias expirou. Seus dados estão guardados; assine para voltar." + contato). Usuário **não verificado** não é redirecionado (vê o assistente e a faixa). Admin nunca é afetado. A rota pública `/r/{slug}` já recusa `active=false` (inalterado; coberto por teste).

- [ ] **Step 1: Write the failing tests** — (a) tablet com token válido de restaurante `active=false` → 401 como token inválido; de restaurante ativo segue 200 (regressão); (b) `/api/public/r/{slug}/restaurant` de restaurante inativo → 404 (já existente: afirmar); (c) dono verificado de restaurante com claim expirado e `active=false` que abre `backoffice.wines.index` é redirecionado à página de teste encerrado, que mostra a mensagem e **não** lista vinhos; (d) dono não verificado abre `backoffice.dashboard` sem redirect; (e) admin abre tudo; (f) usuário de restaurante manual (`active=true`, sem claim) não é afetado; (g) o caso do CNPJ do passo 1 já usado: depois de `endBecauseCnpjUsed` a conta **continua existindo**, loga, vê a página, e os vinhos dela seguem no banco.
- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement.** Conferir `TabletAuthentication` linha 23 (consulta sem escopo) ao acrescentar a condição do restaurante (`whereHas`/join sem global scope; justificar no `RawQueryAuditTest` se houver SQL cru).
- [ ] **Step 4: Run** → PASS; suíte completa verde (testes de tablet/`TabletTenancyContextTest` seguem verdes: fábricas criam restaurante `active=true`).
- [ ] **Step 5: Commit** `feat(backend): restaurante inativo bloqueia tablet e backoffice e página de teste encerrado [Story 9.4]`.

### Task 8: Carta de exemplo

**Files:**
- Create: `backend/app/Services/SampleCartaService.php`, `backend/database/data/sample-carta.php` (array com ~10 vinhos fictícios: nome, produtor, tipo, safra, preço, notas, uvas; nomes e produtores **fictícios**, sem marcas reais)
- Modify: `backend/app/Models/Wine.php` (`is_sample` no cast booleano; fora do `$fillable` se o model usar lista), `backend/resources/views/livewire/wine-list.blade.php` (selo "Exemplo")
- Test: `backend/tests/Feature/Backoffice/SampleCartaTest.php`

**Interfaces:**
- Produces: `SampleCartaService::install(Restaurant $restaurant): int` (cria os vinhos com `is_sample=true` no contexto do restaurante, via `CurrentRestaurant` ou `restaurant_id` explícito; idempotente: se já instalados, devolve 0) e `removeSamples(Restaurant $restaurant): int` (apaga só `is_sample=true` **daquele** restaurante e devolve a contagem).

- [ ] **Step 1: Write the failing tests** — (a) `install` cria 8 a 12 vinhos, todos `is_sample`, todos do restaurante certo; (b) segunda chamada não duplica; (c) `removeSamples` apaga só exemplos e **não** toca vinhos reais nem exemplos de outro restaurante (A×B); (d) vinho de exemplo editado pelo dono por `WineForm` deixa de ser exemplo (`is_sample=false` ao salvar); (e) exemplos aparecem com o selo na lista.
- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement** (migration de `wines.is_sample` já veio na Task 1).
- [ ] **Step 4: Run** → PASS; suíte completa verde.
- [ ] **Step 5: Commit** `feat(backend): carta de exemplo instalável e removível [Story 9.4]`.

### Task 9: Assistente de 4 passos

**Files:**
- Create: `backend/app/Livewire/Onboarding/Wizard.php`, `backend/resources/views/livewire/onboarding/wizard.blade.php`
- Modify: `backend/routes/web.php` (`backoffice.onboarding`, `GET /backoffice/comecar`), `backend/app/Http/Controllers/Backoffice/DashboardController.php` (dono/gerente com `onboarding_completed_at` nulo é redirecionado ao assistente), `backend/app/Livewire/WineImport.php` (reuso, só se exigir parâmetro de retorno), `backend/app/Livewire/RestaurantSettings.php` (extrair/reusar a validação de cores se já existir)
- Test: `backend/tests/Feature/Onboarding/WizardTest.php`

**Interfaces:**
- Consumes: `RestaurantService::update/uploadLogo/generateSlug`, `TabletColorContrast`, `TrialService::endBecauseCnpjUsed`, `SampleCartaService`, `WineImportService`, `PhoneAccessService` (só leitura do estado), `TeamService::invite` (Task 10).
- Produces: componente `Wizard` com `step` 1 a 4; o restaurante vem **sempre** de `auth()->user()->restaurant_id`. **Passo 1:** nome, `slug` público editável (único, `alpha_dash:ascii`), CNPJ opcional, logo e cores (mesmas regras de `RestaurantSettings`); ao salvar um CNPJ, chama `TrialService::endBecauseCnpjUsed` e, se `true`, redireciona a `backoffice.trial.ended`. **Passo 2:** três botões: importar CSV/Excel (reusa o componente/serviço de importação existente), "Começar com a carta de exemplo" (`SampleCartaService::install`) e "Fazer depois". **Passo 3:** instruções de pareamento do tablet (link para `backoffice.tablets`; respeita `TabletService::PLAN_LIMITS['trial']`) e, no lugar do QR, um cartão "Acesso por celular (QR): disponível no plano assinado", com a explicação de risco/custo do spec §6.2. **Passo 4:** convidar por e-mail (perfil `manager` ou `sommelier`) ou pular. "Concluir" grava `restaurants.onboarding_completed_at = now()` e leva ao dashboard; "pular o assistente" também conclui.

- [ ] **Step 1: Write the failing tests** — (a) dono não concluído é redirecionado do dashboard ao assistente; concluído, não; (b) passo 1 grava nome, slug único e cores; cores que violam o contraste mostram a mensagem do `TabletColorContrast` e não salvam; (c) CNPJ inédito é gravado; CNPJ já usado em outro claim → redireciona à página de teste encerrado e `restaurants.active=false`; (d) passo 2 instala a carta de exemplo e a importação de CSV funciona dentro do assistente; "Fazer depois" avança sem criar vinho; (e) passo 3 **não** oferece ligar o acesso por celular (nenhum botão/`wire:click` de ativar; texto do plano assinado presente); (f) passo 4 chama o convite e aceita pular; (g) concluir grava `onboarding_completed_at`; (h) o assistente de um usuário nunca altera outro restaurante (A×B: `restaurant_id` vem do usuário, mesmo com `slug`/`id` forjados no payload Livewire); (i) sommelier e usuário de restaurante manual não são redirecionados ao assistente.
- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement** mantendo as propriedades públicas do Livewire só com campos de formulário (nada de ids; padrão da nota "Livewire sem propriedade pública").
- [ ] **Step 4: Run** → PASS; suíte completa verde.
- [ ] **Step 5: Commit** `feat(backend): assistente de 4 passos do onboarding [Story 9.4]`.

### Task 10: Equipe (convite, aceite e tela `Equipe`)

**Files:**
- Create: `backend/database/migrations/2026_11_13_000003_create_team_invitations_table.php`, `backend/app/Models/TeamInvitation.php`, `backend/app/Services/TeamService.php`, `backend/app/Notifications/TeamInvitationNotification.php`, `backend/app/Livewire/TeamList.php`, `backend/resources/views/livewire/team-list.blade.php`, `backend/resources/views/auth/accept-invitation.blade.php`, `backend/app/Http/Controllers/Backoffice/InvitationController.php`
- Modify: `backend/app/Providers/AppServiceProvider.php` (Gate `manage-team`), `backend/routes/web.php`, `backend/resources/views/backoffice/layouts/app.blade.php` e `components/backoffice-layout.blade.php` (item "Equipe" para owner/manager), `backend/app/Policies/WinePolicy.php` (sommelier edita vinhos), `backend/tests/Feature/Isolation/RawQueryAuditTest.php` se preciso
- Test: `backend/tests/Feature/Backoffice/TeamTest.php`, `backend/tests/Feature/Isolation/TeamIsolationTest.php`

**Interfaces:**
- Produces: tabela `team_invitations` (`restaurant_id` FK, `email`, `role` string, `token_hash` string 64 única, `invited_by` FK users, `expires_at`, `accepted_at` nullable, timestamps); `TeamInvitation` usa `BelongsToRestaurant`. Gate `manage-team` (usuário `owner` ou `manager` com `restaurant_id` nulo-seguro). `TeamService::invite(User $actor, string $email, string $role): void` (reautoriza; `owner` convida `manager|sommelier`, `manager` só `sommelier`; **resposta idêntica** se o e-mail já tem conta em qualquer restaurante, ou convite pendente: nada é enviado e nada é revelado; token aleatório de 40 caracteres, só o **hash** é guardado; validade `config('onboarding.invite_ttl_days')`). `TeamService::accept(string $token, string $name, string $password): User` (token válido, não aceito, não vencido; cria `User` com o `role` do convite, `restaurant_id` do convite, `email_verified_at = now()` (o link veio do e-mail), invalida o convite; erro único para token inexistente/vencido/aceito). `TeamService::changeRole`, `deactivate`, `reactivate` (dono; **nunca no próprio usuário**; nunca em usuário de outro restaurante; `admin` intocável; nunca criar `admin`). Rotas: `backoffice.team` (`GET /backoffice/equipe`, `can:manage-team`), `invitation.accept.show|store` (`GET|POST /convite/{token}`, visitante, `throttle`). Sommelier: vê e edita vinhos; **não** vê Equipe, Configurações, Acesso por celular, Tablets nem Planos.

- [ ] **Step 1: Write the failing tests** — Unidade/serviço: (a) dono convida `manager` e `sommelier`; gerente convida `sommelier` e é recusado ao convidar `manager`; `sommelier` não convida; (b) `role=admin` no convite é recusado; (c) convite para e-mail que já é usuário (outro restaurante, ou admin, ou o mesmo) devolve **o mesmo** retorno e não cria convite nem notificação; (d) só o hash do token está no banco; (e) aceitar com token válido cria o usuário no restaurante certo, verificado, com o perfil certo, e o mesmo token **não** funciona de novo; (f) token vencido e inexistente dão a mesma resposta; (g) dono muda perfil e desativa colega do próprio restaurante, mas **não a si mesmo**, nem usuário de outro restaurante, nem `admin`. Tela: (h) owner/manager abrem `backoffice.team` e só veem usuários **do próprio restaurante**; sommelier recebe 403; admin pelo gate `manage-team` não vê Equipe de ninguém (admin usa a tela Usuários); (i) item "Equipe" só aparece para quem pode; (j) sommelier acessa `backoffice.wines.index` e edita, mas recebe 403 em `backoffice.settings`, `backoffice.tablets`, `backoffice.phone-access` (nomes reais das rotas, conferir). Isolamento A×B: payload Livewire forjado com id de usuário/convite do restaurante B não age (`TeamIsolationTest`).
- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement**; mensagens em português simples; auditoria no canal `audit` só com ids, `role` e ip (nunca e-mail nem token).
- [ ] **Step 4: Run** → PASS; suíte completa verde (conferir `UserManagementTest` e a lista de perfis).
- [ ] **Step 5: Commit** `feat(backend): equipe com convite por e-mail e perfil sommelier [Story 9.4]`.

### Task 11: Acesso por celular travado no plano `trial`

**Files:**
- Modify: `backend/app/Services/PhoneAccessService.php`, `backend/app/Livewire/PhoneAccess.php`, `backend/resources/views/livewire/phone-access.blade.php`
- Test: `backend/tests/Feature/Backoffice/PhoneAccessTrialTest.php`

**Interfaces:**
- Produces: `PhoneAccessService::enable` e `setMode` recusam restaurante com `plan = 'trial'` usando a **mesma** forma de erro que o serviço já usa para outras recusas (ler o arquivo); a tela `PhoneAccess`, para plano `trial`, mostra o cartão "Disponível no plano assinado" **sem** botões de ligar/QR/download e sem alterar estado. Qualquer outro plano segue como hoje; restaurante com acesso já ligado e plano `trial` (criado à mão antes) **não** é desligado automaticamente (restaurantes manuais mantêm o plano que têm).

- [ ] **Step 1: Write the failing tests** — (a) `enable` em restaurante `trial` falha e `phone_access_enabled` continua falso; (b) em plano `starter`/`pro` (valores existentes) segue funcionando (regressão); (c) a tela para `trial` não contém os controles e o POST forjado via Livewire é recusado; (d) o `admin` alterando o plano para um assinado libera ligar; (e) a sessão pública de celular de um restaurante `trial` com acesso já ligado por engano devolve a resposta de acesso desligado (checagem na origem: `ResolvePublicRestaurant` modo `session`), coberta por teste.
- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** → PASS; suíte completa verde (os testes existentes de `PhoneAccess*` usam plano padrão `starter`: se alguma fábrica usar `trial`, ajustar a fábrica, não o teste).
- [ ] **Step 5: Commit** `feat(backend): acesso por celular exige plano assinado [Story 9.4]`.

### Task 12: Lembretes do trial e faxina de cadastros não verificados

**Files:**
- Create: `backend/app/Console/Commands/SendTrialReminders.php`, `backend/app/Console/Commands/PurgeUnverifiedSignups.php`, `backend/app/Notifications/TrialReminderNotification.php`
- Test: `backend/tests/Feature/Console/SendTrialRemindersTest.php`, `backend/tests/Feature/Console/PurgeUnverifiedSignupsTest.php`

**Interfaces:**
- Produces: `php artisan trial:send-reminders {--dry-run}`: para cada `TrialClaim` com `ended_at` nulo, calcula o dia do trial (`dia = diasDesdeInício + 1`); se o dia está em `config('onboarding.reminder_days')` e é maior que `last_reminder_day`, envia `TrialReminderNotification` (fila) ao usuário `owner` do restaurante, e grava `last_reminder_day`; **idempotente** (rodar duas vezes no mesmo dia não reenvia); no dia 14 a mensagem diz que o teste termina hoje; saída só com contagens. `php artisan signups:purge-unverified {--dry-run}`: apaga usuários **não verificados** criados há mais de `unverified_ttl_days` que têm `signup_cpf_hash` ou `signup_cnpj` **e** cujo restaurante não tem claim nem vinhos importados do usuário (só `is_sample` ou nenhum), apagando também o restaurante vazio; nunca toca verificados nem restaurantes manuais; saída só com contagens. Os docblocks trazem as linhas de cron diário (PHP e `artisan` por caminho absoluto, como `PurgeComensalSessions`); nenhum entra no `Schedule`.

- [ ] **Step 1: Write the failing tests** — lembretes: (a) dia 7, 12 e 14 enviam e os outros dias não; (b) segunda execução no mesmo dia não duplica; (c) claim encerrado e restaurante manual (sem claim) não recebem; (d) o destinatário é o `owner` verificado do restaurante, nunca outro; (e) `--dry-run` só conta; (f) a saída não contém e-mail. Faxina: (g) apaga cadastro não verificado de 8 dias e o restaurante vazio; mantém o de 6 dias; (h) mantém o verificado de qualquer idade e o usuário criado por admin/convite; (i) mantém restaurante que já tem vinho real; (j) `--dry-run` não apaga.
- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** → PASS; suíte completa verde.
- [ ] **Step 5: Commit** `feat(backend): lembretes do teste e faxina de cadastros não verificados [Story 9.4]`.

### Task 13: Landing aponta para o cadastro

**Files:**
- Modify: `backend/resources/views/landing.blade.php` (a seção do formulário vira o CTA "Testar 14 dias grátis" para `route('signup.show')`; todos os links de "demonstração" apontam para o cadastro), `backend/routes/web.php` (remover `POST /demonstracao`), `backend/tests/Feature/Landing/*`
- Delete (se nada mais os usar; conferir com Grep): `backend/app/Http/Controllers/DemoRequestController.php`, `backend/app/Http/Requests/DemoRequestStoreRequest.php`, `backend/app/Services/DemoRequestService.php`, `backend/app/Mail/DemoRequestReceived.php`, `backend/resources/views/mail/*demo*`, o limiter `demo-requests` e `backend/tests/Feature/Landing/DemoRequestStoreTest.php`
- Keep: model `DemoRequest`, `DemoRequestList` (histórico, só admin), `demo-requests:purge` e seus testes.
- Test: `backend/tests/Feature/Landing/LandingSignupCtaTest.php`

- [ ] **Step 1: Write the failing tests** — a landing não contém mais `<form` para `/demonstracao` nem `route('demo-requests.store')`; contém um link para `/cadastro` com o texto "Testar 14 dias grátis"; `POST /demonstracao` responde 404/405; o admin ainda abre a lista de pedidos antigos; o comando `demo-requests:purge` continua funcionando.
- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement**; os testes antigos de envio do formulário são removidos de propósito (registrar no Dev Agent Record), preservando os de `DemoRequestList`, `PurgeDemoRequests` e de landing que não dependam do formulário.
- [ ] **Step 4: Run** → PASS; suíte completa verde.
- [ ] **Step 5: Commit** `feat: landing leva ao cadastro self-service e aposenta o formulário de demonstração [Story 9.4]`.

### Task 14: Fecho (controlador)

Não é tarefa de implementador. O controlador: suíte completa em SQLite **e** num MySQL 8 descartável; `npm test`, `typecheck`, `lint` do frontend (esperado: sem mudança); ponta a ponta no Chromium (cadastro → e-mail na fila → link assinado → assistente → carta de exemplo → tablet; segundo cadastro com variante do e-mail, outro e-mail com o mesmo CPF e CNPJ já usado; convite e aceite; dono com teste encerrado); revisão final da branch (opus) com **uma** onda de correção; atualizar a story, o cofre e o grafo; **perguntar ao Rafael** antes do merge na `main`; anotar na story as linhas de cron (`trial:send-reminders` e `signups:purge-unverified`, diários) e a chave `TRIAL_HASH_KEY` do `.env` de produção, para o Rafael criar na publicação.
