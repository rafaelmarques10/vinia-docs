# Vinia SaaS — Ajustes pós-validação da Fase 2 e retenção LGPD (Story 9.3) — Plano de Implementação

> **Para quem executa:** SUB-SKILL OBRIGATÓRIA: usar superpowers:subagent-driven-development (recomendado) ou superpowers:executing-plans, tarefa a tarefa. Os passos usam checkbox (`- [ ]`).

**Goal:** Fechar o backlog que a revisão final da Story 9.2 deixou (decisão do Rafael em 2026-11-12: "realizar ajustes") e implementar a retenção LGPD do `device_id` das sessões de celular (recomendação do @po: cron direto e 12 meses), sem mudar o fluxo do tablet.

**Architecture:** Mudanças pequenas e independentes sobre a Fase 2 já mergeada na `main`: códigos de erro distintos para a cota por rede e para a rajada, um limitador por sessão dentro do `AiInteractionController`, estado "chave ilegível" no `PhoneAccessService`, comando de expurgo no modelo do `demo-requests:purge` (Story 7.4), chave do QR em fragmento de URL (`#k=`) para não chegar ao servidor, correções de tela do modo celular e um servidor de desenvolvimento que emula o `.htaccess`.

**Tech Stack:** Laravel + Livewire + PHPUnit (SQLite nos testes, MySQL 8 em produção e no CI); React 19 + Vite + Vitest.

**Spec:** `vinia-docs/docs/superpowers/specs/2026-11-10-vinia-saas-design.md` (§6.3 travas, §6.4 QR) e a Story 9.2 (`vinia-docs/docs/stories/9.2.story.md`, Dev Agent Record e "Achados do @po").

**Story / branch:** Story 9.3 (Epic 9), criada pelo @sm e validada pelo @po no Task 1. Branch local `feat/ajustes-fase2-9.3`, criada a partir da `main`. **Commits na branch estão autorizados pelo Rafael** ("pode commitar", 2026-11-12). **Merge na `main` e `git push`/PR NÃO** sem nova autorização dele (push/PR é do @devops).

## Decisões deste plano (revise)

1. **[CALL] Códigos novos:** `NETWORK_LIMITED` (429) para a cota de 60 sessões/h por IP (o wifi do restaurante e o CGNAT compartilham IP: a tela hoje diz "você usou várias vezes" quando quem esgotou foi a rede); `TOO_MANY_ATTEMPTS` (429) para o `throttle` de martelada (30/min por IP); `TOO_FAST` (429) para a rajada de consultas de uma sessão. A cota por aparelho (3/dia) continua `RATE_LIMITED`.
2. **[CALL] Rajada por sessão, dentro do controller.** O `ThrottleRequests` entra *antes* do `ResolvePublicRestaurant` na prioridade de middlewares, então um `throttle` chaveado por token criaria chaves de cache para tokens inventados. O limite (10 consultas por minuto, `SOFIA_PHONE_QUERIES_PER_MINUTE`) é checado em `AiInteractionController::store` só para sessões de celular, chaveado pelo **id da sessão** autenticada.
3. **[CALL] Chave do QR em fragmento (`#k=`).** O fragmento nunca vai ao servidor (some dos access logs da Hostinger). A URL do QR passa a ser `/r/{slug}#k={chave}`; o navegador herda o fragmento no 302 de `/r/{slug}` para `/tablet/r/{slug}`. O formato antigo `?k=` continua aceito (QR já impresso).
4. **[CALL] Chave ilegível** (APP_KEY mudou sem `APP_PREVIOUS_KEYS`): novo estado `unreadable` no `PhoneAccessService`, tratado como "vencida" na lógica (gera chave nova) e com aviso próprio na tela, em vez de 500.
5. **[CALL] Retenção LGPD: 12 meses**, expurgo em definitivo (DELETE) de `comensal_sessions` com `source='phone'` e `started_at` mais velho que 12 meses (as interações vão junto). Sessões de tablet não entram. Cron direto no hPanel (o `schedule:run` não funciona na Hostinger), como na 7.4. Prazo em constante do comando (mudar exige mudar o aviso de privacidade, que nasce na Fase 7).

**Fora desta story:** fallback offline para 429/5xx no cache do service worker; relógio do aparelho adiantado; app instalável; cota mensal e painel (Fase 4).

## Global Constraints

- Código em `vinia-src`, docs e stories em `vinia-docs`. Funcionar em SQLite (testes) **e MySQL 8** (CI e produção): nenhum teste que dependa de aspas de identificador ou SQL cru de um banco só (lição da 9.2: o `deploy.yml` roda os dois).
- `env()` só em `config/*.php`; todo limite do comensal passa por `SofiaLimits` (com padrão no código; `SofiaLimitsTest` falha se o `app/` ler `sofia.tablet|phone.*` por fora). Novas chaves entram em `SofiaLimits::PHONE`, `config/sofia.php` e `.env.example`.
- Não gravar IP em tabela; a saída do comando de expurgo traz só contagens (nunca id de sessão, aparelho ou restaurante).
- O fluxo do tablet não muda: a suíte (backend 944, frontend 681) continua verde ao fim de cada tarefa, sem alterar teste existente (exceto os que fixam o comportamento antigo explicitamente trocado aqui, registrados no relatório).
- Mensagens em português com acentuação; padrão de layout do backoffice: formulários em largura total (exceto 2 colunas).
- Commits convencionais com `[Story 9.3]`, na branch `feat/ajustes-fase2-9.3`. Nunca `git push`, nunca merge na `main` neste plano.

## Review Focus

1. O `#k=` sobrevive ao 302 de `/r/{slug}` num navegador de verdade e a chave **não** aparece na linha de requisição do servidor; `?k=` antigo continua funcionando.
2. A rajada por sessão não afeta o tablet nem outra sessão do mesmo IP (wifi compartilhado) e não cria chaves de cache para sessão inválida.
3. O expurgo apaga só `source='phone'` com mais de 12 meses (nem o tablet, nem a sessão de 11 meses), com a borda exata e o `--dry-run` sem apagar nada.
4. Com `qr_key` ilegível a tela abre (sem 500), o gestor consegue gerar um QR novo e a Sofia do celular responde `QR_INVALID`, sem vazar a causa.
5. Cada código novo chega à mensagem certa na tela do celular (rede x aparelho x rajada x muitas tentativas).

---

### Task 1: Story 9.3, validação do @po e branch

**Files:**
- Create: `vinia-docs/docs/stories/9.3.story.md`

- [ ] **Step 1:** Em `vinia-src`, a partir da `main`: `git checkout -b feat/ajustes-fase2-9.3`.
- [ ] **Step 2 (@sm / `aiox-sm`):** criar `9.3.story.md` no formato da `9.2.story.md`, status Draft, com os CAs: CA01 cota por rede com código e mensagem próprios; CA02 rajada de consultas por sessão limitada sem afetar o tablet; CA03 `qr_key` ilegível não derruba a tela e permite regenerar; CA04 expurgo LGPD de 12 meses das sessões de celular, com cron documentado; CA05 chave do QR em `#k=` com `?k=` antigo aceito; CA06 modo celular sem piscar carta vazia, perfil de paladar gravado na primeira consulta e sessão vencida durante o acompanhamento vira erro cedo; CA07 `scripts/dev-server.sh`; CA08 suíte verde em SQLite e MySQL 8.
- [ ] **Step 3 (@po / `aiox-po`):** validar (checklist de 10 pontos); só segue com GO (≥ 7).
- [ ] **Step 4: Commit** (em `vinia-docs`, só os arquivos da 9.3): `docs: story 9.3 ajustes pós-validação da Fase 2 e retenção LGPD`.

---

### Task 2: Códigos de erro de rede e rajada por sessão

**Files:**
- Modify: `backend/app/Http/Controllers/Api/PublicSessionController.php`, `backend/app/Providers/AppServiceProvider.php`, `backend/app/Http/Controllers/Api/AiInteractionController.php`, `backend/app/Support/Comensal/SofiaLimits.php`, `backend/config/sofia.php`, `backend/.env.example`
- Test: `backend/tests/Feature/Api/PublicSessionTest.php` (novos casos em arquivo novo `PublicSessionErrorCodesTest.php`), `backend/tests/Feature/Api/PublicSofiaBurstTest.php`, `backend/tests/Unit/Comensal/SofiaLimitsTest.php`

**Interfaces:**
- `SofiaLimits::PHONE['queries_per_minute'] = 10` (config `sofia.phone.queries_per_minute`, env `SOFIA_PHONE_QUERIES_PER_MINUTE`).
- `POST /api/public/r/{slug}/sessions`: a cota por IP (`sessions_per_ip_per_hour`) responde 429 `NETWORK_LIMITED` com a mensagem "Muitas pessoas estão usando a Sofia nesta rede agora. Tente de novo em alguns minutos ou chame o nosso sommelier."; a cota por aparelho segue 429 `RATE_LIMITED`; o limiter `public-session-attempts` passa a responder 429 `TOO_MANY_ATTEMPTS` ("Muitas tentativas seguidas. Aguarde um instante e tente de novo."). Quando as duas cotas estouram juntas, vale a do aparelho.
- `AiInteractionController::store`, só para `ComensalActor::isPhone()`: depois da checagem de propriedade da sessão e **antes** do limite por sessão, `RateLimiter::tooManyAttempts('sofia-burst|'.$sessionId, SofiaLimits::phone('queries_per_minute'))` → 429 `TOO_FAST` ("Você está enviando perguntas rápido demais. Aguarde alguns segundos e tente de novo."); senão `RateLimiter::hit($key, 60)`. O tablet não passa por aqui.

- [ ] **Step 1: Testes que falham.** Códigos: (a) 61ª sessão do mesmo IP (config reduzido) → `NETWORK_LIMITED`; (b) 4ª do mesmo aparelho → `RATE_LIMITED`; (c) aparelho **e** IP estourados juntos → `RATE_LIMITED`; (d) martelada (`session_attempts_per_minute` = 2) → `TOO_MANY_ATTEMPTS` mesmo recusada com 403. Rajada: (e) a 11ª consulta no mesmo minuto da mesma sessão → 429 `TOO_FAST` e **nenhuma** `AiInteraction` criada por ela; depois de `travel(61)->seconds()` a consulta passa; (f) outra sessão do mesmo IP não é afetada; (g) a sessão do tablet com 30 consultas em 1 minuto não leva `TOO_FAST`; (h) com `sofia.phone` removida do config, o padrão 10 vale; (i) token inexistente não cria chave de cache (`Cache` sem a chave `sofia-burst|...` do token inventado). `SofiaLimitsTest`: a nova chave existe em `SofiaLimits::PHONE`, em `config/sofia.php` e no `.env.example` com o mesmo valor.
- [ ] **Step 2:** `cd backend && php artisan test --filter="PublicSessionErrorCodes|PublicSofiaBurst|SofiaLimits"` → FAIL.
- [ ] **Step 3:** Implementar conforme as Interfaces. Ajustar, deliberadamente e registrando no relatório, os testes existentes que fixam `RATE_LIMITED` na cota por IP ou na martelada.
- [ ] **Step 4:** `php artisan test` completo → verde.
- [ ] **Step 5: Commit:** `feat(backend): códigos de erro para cota por rede e rajada de consultas por sessão [Story 9.3]`.

---

### Task 3: Chave ilegível e expurgo LGPD das sessões de celular

**Files:**
- Create: `backend/app/Console/Commands/PurgeComensalSessions.php`
- Modify: `backend/app/Services/PhoneAccessService.php`, `backend/app/Livewire/PhoneAccess.php`, `backend/resources/views/livewire/phone-access.blade.php`
- Test: `backend/tests/Feature/Console/PurgeComensalSessionsTest.php`, `backend/tests/Unit/Services/PhoneAccessServiceTest.php` (casos novos), `backend/tests/Feature/Backoffice/PhoneAccessTest.php` (casos novos)

**Interfaces:**
- `PhoneAccessService`: toda leitura de `qr_key` passa por um método privado que captura `Illuminate\Contracts\Encryption\DecryptException`, registra `Log::warning` (id do restaurante, **nunca** a chave) e devolve `null`. Nova constante `KEY_UNREADABLE = 'unreadable'` em `storedKey()` (chave guardada que não decifra); `keyState()` devolve `'unreadable'`; na lógica de `enable`, `setMode` e `regenerateKey` é tratada como `KEY_EXPIRED` (gera chave nova, sem reaproveitar); `assertKeyAllowsSession` → `QR_INVALID`; `entryUrl` → `null`. A tela mostra, nesse estado, um alerta "Não foi possível ler o QR guardado (a chave de criptografia do servidor mudou). Gere um novo QR e imprima-o." com o botão "Gerar novo QR" funcionando, sem QR, link nem download.
- `PurgeComensalSessions` (`php artisan comensal-sessions:purge {--dry-run}`): `public const RETENTION_MONTHS = 12`; apaga em definitivo `ComensalSession` com `source = 'phone'` e `started_at < now()->subMonthsNoOverflow(12)` (e as `ai_interactions` delas; conferir se a FK já faz cascade e, se não fizer, apagar as interações antes); nunca toca `source = 'tablet'`; saída só com as contagens (sessões e interações), prefixada por "(simulação)" no `--dry-run`, que não apaga nada. O docblock traz a linha de cron para o hPanel (modelo da 7.4: `0 4 * * * cd <APP_PATH> && php artisan comensal-sessions:purge >> storage/logs/comensal-sessions-purge.log 2>&1`, **fora** do `Schedule`, porque o `schedule:run` não funciona na Hostinger).

- [ ] **Step 1: Testes que falham.** Chave ilegível: (a) com `qr_key` gravado como lixo (via `DB::table`), `keyState` devolve `'unreadable'` sem lançar, `entryUrl` é nulo e `assertKeyAllowsSession` dá `QR_INVALID`; (b) `regenerateKey` e `enable` geram chave nova e voltam ao normal; (c) a tela (Livewire) abre sem 500 com o alerta, sem QR/link/download, e "Gerar novo QR" funciona; (d) nenhum log contém a chave. Expurgo: (e) apaga a sessão de celular de 13 meses e as interações dela; (f) mantém a de 11 meses; (g) mantém a sessão **de tablet** de 13 meses e as interações dela; (h) borda: `started_at` exatamente 12 meses atrás é mantida (`<` estrito); (i) `--dry-run` informa as contagens e não apaga nada; (j) a saída não contém UUID, `device_id` nem nome de restaurante; (k) funciona com sessões de vários restaurantes.
- [ ] **Step 2:** `php artisan test --filter="PurgeComensalSessions|PhoneAccess"` → FAIL.
- [ ] **Step 3:** Implementar conforme as Interfaces.
- [ ] **Step 4:** `php artisan test` completo → verde; rodar o comando no banco local em `--dry-run` e anotar a contagem no relatório.
- [ ] **Step 5: Commit:** `feat(backend): chave do QR ilegível não derruba a tela e expurgo LGPD das sessões de celular [Story 9.3]`.

---

### Task 4: Chave do QR em fragmento (`#k=`)

**Files:**
- Modify: `backend/app/Services/PhoneAccessService.php` (`entryUrl`), `backend/routes/tablet.php` (apenas comentários, se preciso), `frontend/src/services/phoneSession.ts`
- Test: `backend/tests/Unit/Services/PhoneAccessServiceTest.php`, `backend/tests/Feature/PublicEntryRouteTest.php`, `backend/tests/Feature/Backoffice/PhoneAccessTest.php`, `frontend/src/services/phoneSession.test.ts`

**Interfaces:**
- `PhoneAccessService::entryUrl(Restaurant): ?string` passa a devolver `url('/r/{slug}').'#k={chave}'` (sem `?k=`). O 302 de `/r/{slug}` continua preservando a query string (compatibilidade com `?k=`); o fragmento é herdado pelo navegador.
- `captureQrKey(slug)`: lê a chave primeiro de `location.hash` (`#k=<chave>`, via `URLSearchParams` do hash sem o `#`), e se não houver, de `?k=` (formato antigo); grava em `sessionStorage` como hoje; remove o `k` de **onde veio** com `history.replaceState` (hash: remove o fragmento inteiro quando só tinha o `k`; query: remove só o `k`, preservando os demais parâmetros), tudo em try/catch como já está.

- [ ] **Step 1: Testes que falham.** Backend: (a) `entryUrl` termina em `#k={chave}` e não contém `?k=`; (b) o 302 de `/r/{slug}?k=abc` ainda preserva a query (compatibilidade); (c) o link mostrado e o QR gerado pela tela usam o formato novo (comparar o SVG com o gerado da URL esperada, como nos testes da Task 8). Frontend: (d) com `#k=abc` a chave é guardada e a URL fica sem hash; (e) com `?k=abc` (antigo) continua funcionando e preserva os outros parâmetros; (f) com os dois, vale o hash e ambos saem da URL; (g) hash sem `k` (ex.: `#outra`) não é apagado; (h) storage bloqueado e `replaceState` que lança não derrubam.
- [ ] **Step 2:** `php artisan test --filter="PhoneAccessService|PublicEntryRoute|PhoneAccessTest"` e `cd ../frontend && npm test -- --run src/services/phoneSession` → FAIL.
- [ ] **Step 3:** Implementar.
- [ ] **Step 4:** `php artisan test` completo e `npm test -- --run && npm run typecheck && npm run lint` → verdes.
- [ ] **Step 5: Commit:** `feat: chave do QR no fragmento da URL (#k=), com ?k= antigo aceito [Story 9.3]`.

---

### Task 5: Frontend — mensagens por código e ajustes do modo celular

**Files:**
- Modify: `frontend/src/services/phoneSession.ts` (`PhoneErrorCode`), `frontend/src/pages/AssistantPage.tsx`, `frontend/src/components/PhoneGate.tsx`, `frontend/src/hooks/useAiInteraction.ts`, `frontend/src/hooks/useRestaurant.ts`
- Test: `*.phone.test.tsx` ao lado de cada alteração

**Interfaces:**
- `PhoneErrorCode` ganha `NETWORK_LIMITED`, `TOO_MANY_ATTEMPTS` e `TOO_FAST`. Mensagens: `NETWORK_LIMITED` "Muitas pessoas estão usando a Sofia nesta rede agora. Tente de novo em alguns minutos ou chame o nosso sommelier."; `TOO_MANY_ATTEMPTS` "Muitas tentativas seguidas. Aguarde um instante e tente de novo."; `TOO_FAST` "Você está enviando perguntas rápido demais. Aguarde alguns segundos e tente de novo." (ao consultar, sem encerrar a conversa). `RATE_LIMITED` ao abrir sessão continua "Você já usou a Sofia várias vezes hoje...".
- `PhoneGate`/`useRestaurant` (modo celular): não repetir a requisição quando o `GET /restaurant` responde 404 (`retry` condicional), para a tela "Carta indisponível" aparecer sem piscar a carta vazia; o contêiner da tela usa `h-full`/`min-h-full` em vez de `h-dvh` dentro da área do `AppFrame`.
- `AssistantPage` (modo celular): o perfil de paladar passa a ser gravado também na primeira consulta (hoje `if (sessionId)` usa o id capturado no clique e a sessão ainda não existe): usar o `sid` resolvido dentro de `runRequest`, com `.catch` como já existe.
- `useAiInteraction`: quando a consulta de acompanhamento falha com `phoneErrorCode(error) === 'SESSION_EXPIRED'`, parar o polling e a tela mostra a mensagem de indisponibilidade na hora (hoje fica "Sofia está pensando..." até 90 s).

- [ ] **Step 1: Testes que falham.** (a) cada código novo mostra a mensagem certa (abrir sessão: `NETWORK_LIMITED`, `TOO_MANY_ATTEMPTS`; consultar: `TOO_FAST`); (b) `PhoneGate` com 404 não repete a requisição (uma única chamada a `getRestaurant`) e não renderiza os `children` em nenhum quadro; (c) o `updateSession` com `palate_profile` é chamado com o `sid` novo na primeira consulta do celular; (d) 401 `SESSION_EXPIRED` no acompanhamento para o polling e mostra o erro sem esperar 90 s (timers falsos); (e) regressão: o modo tablet segue idêntico.
- [ ] **Step 2:** `cd frontend && npm test -- --run` → FAIL nos novos.
- [ ] **Step 3:** Implementar.
- [ ] **Step 4:** `npm test -- --run && npm run typecheck && npm run lint && npm run build` → verdes (681 + novos).
- [ ] **Step 5: Commit:** `feat(frontend): mensagens por código e ajustes do modo celular [Story 9.3]`.

---

### Task 6: Servidor de desenvolvimento que emula o `.htaccess`

**Files:**
- Create: `scripts/dev-server.sh`, `scripts/dev-router.php`

**Interfaces:**
- `scripts/dev-server.sh [porta]` (padrão 8000, host 127.0.0.1): sobe `PHP_CLI_SERVER_WORKERS=4 php -S 127.0.0.1:<porta> -t backend/public scripts/dev-router.php`, a partir da raiz do repositório (resolve o caminho do script), e imprime a URL. Comentário no topo explica por que não usar `php artisan serve`: com `public/tablet/index.html` existente o servidor embutido resolve `/tablet/r/{slug}` como `SCRIPT_NAME=/tablet/index.html` + `PATH_INFO` e o Laravel entra em loop de redirect em `/r/{slug}` (só em desenvolvimento; produção usa o `.htaccess`).
- `scripts/dev-router.php`: emula `backend/public/.htaccess`: arquivo estático ou diretório existente em `public/` → `return false`; `/tablet/` ou `/tablet` com `?token=<64 hex>` → Laravel; qualquer outro caminho → `require public/index.php` com `SCRIPT_NAME`, `SCRIPT_FILENAME` e `PHP_SELF` fixados em `/index.php` e `PATH_INFO` removido. Não altera nenhum arquivo do app.

- [ ] **Step 1:** Escrever os dois arquivos (o modelo é o router que o ponta a ponta da 9.2 usou: `.superpowers/sdd/.../scratchpad/e2e/router.php` não é versionado; a lógica está descrita acima).
- [ ] **Step 2: Verificação (no relatório, com as saídas):** subir o script em outra porta (ex.: 8123) com o banco local, e conferir por `curl`: `/up` 200, `/backoffice/login` 200, `/tablet/` 200, `/tablet/assets/<um arquivo gerado>` 200 (estático), `/r/<slug de um restaurante com celular ligado>` 302 para `/tablet/r/<slug>` **sem loop**, `/tablet/r/<slug>` 200; encerrar o servidor ao fim.
- [ ] **Step 3: Commit:** `chore: scripts/dev-server.sh e roteador que emula o .htaccess [Story 9.3]`.

---

### Task 7: Verificação e fechamento (feito pelo controlador, não delegado)

- [ ] **Step 1:** `php artisan test` (SQLite) **e** a suíte num MySQL 8 descartável; `npm test -- --run`, `typecheck`, `lint`, `build`.
- [ ] **Step 2: Navegador de verdade (Playwright):** (a) `/r/{slug}#k={chave}` termina em `/tablet/r/{slug}`, a chave fica na `sessionStorage`, a URL final não tem hash nem `k=`, e o log do servidor **não** contém a chave; (b) `/r/{slug}?k={chave}` (antigo) segue funcionando; (c) as mensagens novas aparecem (configurar limites baixos por variável de ambiente no servidor descartável); (d) `qr_key` corrompido: a tela do backoffice abre e permite gerar novo QR; (e) "Carta indisponível" sem piscar a carta; (f) o expurgo, em `--dry-run` e real, num banco descartável com sessões de idades diferentes.
- [ ] **Step 3:** Revisão final do branch (opus) e uma única onda de correção, se preciso.
- [ ] **Step 4:** Atualizar a Story 9.3, o cofre e as notas; **perguntar ao Rafael** antes de qualquer merge na `main`.
