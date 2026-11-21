# Deploy do Vinia na Hostinger (plano Business, hospedagem compartilhada)

Guia de produção para o site e o backoffice (Laravel + Livewire), a PWA do tablet e do celular (React), a Sofia (sommelier IA),
o cadastro self-service e a cobrança pelo Asaas.

> **A produção ainda roda a versão anterior ao SaaS.** Antes do próximo push da `main`, siga a seção 5.1.

> Este guia vive em `vinia-docs`; os caminhos `scripts/`, `backend/` e `.github/` se referem ao repositório de código `vinia-src`.
>
> Convenções deste guia: `<usuario>` é o usuário SSH da Hostinger (algo como `u123456789`), `<dominio>` é o
> domínio do site e `APP_PATH` é a raiz do clone: `/home/<usuario>/domains/<dominio>/vinia-app`.

## 1. Como a produção funciona

| Peça | Como roda na Hostinger |
|---|---|
| Backoffice | Laravel 13 + Livewire 4, PHP 8.3+ servido pelo LiteSpeed |
| PWA do tablet | Build estático em `backend/public/tablet`, servida em `https://<dominio>/tablet/` (fallback de rotas SPA no Laravel) |
| Banco | MySQL/MariaDB do hPanel |
| Cache, sessão e fila | Tudo no banco (`database`). **Sem Redis, sem Supervisor** |
| Fila | O cron de 1 minuto roda **direto** `queue:work --stop-when-empty --max-time=50` (o `schedule:run` não funciona aqui, ver 1.1) |
| Sofia | Chamada HTTP ao Groq **dentro do próprio request**, logo após a resposta ser enviada (ver seção 6) |
| Uploads | Cloudflare R2 (se as chaves estiverem no `.env`), senão `storage/app/public` via `public/storage` (criado com `ln -s`, ver 4.2) |
| Front (build) | Feito no GitHub Actions (ou no seu Mac). **O servidor não tem Node** |

### 1.1 Funções do PHP bloqueadas na Hostinger

O PHP do servidor (CLI e site) tem `disable_functions` com **`proc_open`, `exec`, `shell_exec`, `system`, `popen`, `passthru`, `symlink` e `link`**
(confira com `php -r 'echo ini_get("disable_functions");'`). Consequências, já tratadas neste guia:

| O que usa a função | O que falha | Solução adotada |
|---|---|---|
| Scripts do Composer (`@php artisan package:discover` no `post-autoload-dump`) | `The Process class relies on proc_open` (o erro vem do **próprio Composer**) | `composer install ... --no-scripts` e depois `php artisan package:discover` direto (o `deploy.sh` já faz isso) |
| `php artisan storage:link` (usa `symlink()`) | falha ao criar o link | criar **uma vez** pelo shell com `ln -s` (seção 4.2); o `deploy.sh` só cria se não existir |
| `schedule:run` (dispara `queue:work` como subprocesso) | a fila não anda | cron chamando `queue:work` direto (seção 3.4) |

Não é recomendado liberar essas funções num plano compartilhado só para contornar isso.

## 2. Estrutura de pastas no servidor

```text
/home/<usuario>/domains/<dominio>/
├── public_html  ->  vinia-app/backend/public     (symlink; document root fixo da Hostinger)
└── vinia-app/                                    (clone do repositório = APP_PATH)
    ├── backend/                                  (aplicação Laravel)
    │   ├── .env                                  (segredos, só no servidor, chmod 600)
    │   ├── public/
    │   │   ├── build/                            (assets do Livewire/Vite, enviados pelo CI)
    │   │   ├── tablet/                           (PWA do tablet, enviada pelo CI)
    │   │   └── storage -> ../storage/app/public  (symlink relativo)
    │   └── storage/
    ├── frontend/  prototipo/  docs/              (código-fonte; não expostos na web)
    ├── scripts/deploy.sh
    └── .deploy-staging/                          (área temporária dos assets do CI)
```

Só `backend/public` fica exposto. `.env`, `storage/`, `vendor/` e o `.git` ficam fora do document root.

Comando do symlink (rodar em `~/domains/<dominio>`, **depois** de clonar o repositório):

```bash
cd ~/domains/<dominio>
mv public_html public_html.bak-$(date +%F)     # a Hostinger cria uma pasta public_html padrão
ln -s vinia-app/backend/public public_html
ls -l public_html                               # deve mostrar: public_html -> vinia-app/backend/public
```

> O repositório tem o Laravel em `backend/`, por isso o destino é `vinia-app/backend/public` (e não
> `vinia-app/public`). O mesmo vale para o caminho do `artisan` no cron.

## 3. Configuração no hPanel

### 3.1 PHP

hPanel → **Avançado → Configuração do PHP**

- Versão: **8.3 ou superior** (o `composer.json` exige `^8.3`).
- Extensões habilitadas: `mbstring`, `pdo_mysql`, `mysqli`, `gd`, `zip`, `xml`, `dom`, `simplexml`,
  `xmlreader`, `xmlwriter`, `fileinfo`, `curl`, `openssl`, `intl`, `ctype`, `tokenizer`.
  (`zip`, `gd` e `xml*` são exigidos pela importação de planilhas de vinhos.)
- Opções: `upload_max_filesize` e `post_max_size` ≥ `8M` (fotos e planilhas); `max_execution_time` ≥ `60`
  (a Sofia roda após a resposta e pode levar até ~30 s).

> A versão do PHP **no SSH** pode ser diferente da do site. Confira com `php -v`. Se não for 8.3+, descubra
> o binário correto (por exemplo `ls /opt/alt/ | grep php`) e use o caminho completo em `PHP_BIN`
> (deploy) e no cron. Este caminho precisa ser confirmado no seu servidor.

### 3.2 Banco MySQL

hPanel → **Bancos de dados → Gerenciamento** → criar banco, usuário e senha. Anote os três valores:
vão em `DB_DATABASE`, `DB_USERNAME` e `DB_PASSWORD`. `DB_HOST=127.0.0.1` e `DB_PORT=3306`
(se a conexão falhar, use `localhost`). **Não use o hostname externo do servidor MySQL** que o hPanel mostra
(algo como `srvNNN.hstgr.io`): a conexão chega de fora e é recusada com `Access denied for user ...`, mesmo com a senha certa.

### 3.3 DNS e SSL

Se o domínio está com os nameservers de "parking" (`*.dns-parking.com`) e sem registro **A**, o site não abre de fora mesmo com o
servidor respondendo. hPanel → **Domínios → DNS / Nameservers**: crie o registro **A** `@` apontando para o IP da hospedagem
(confira em "Acesso SSH"/painel; o IP do SSH normalmente é o mesmo) e, opcionalmente, **CNAME** `www` → domínio.
Aguarde a propagação (`dig +short <dominio> @8.8.8.8` deve devolver o IP) e então ative o SSL.

hPanel → **Segurança → SSL** → instalar/ativar o SSL gratuito do domínio e ligar **Forçar HTTPS**.
O app também força `https` em produção (`URL::forceScheme`) e confia nos cabeçalhos do proxy
(`TRUSTED_PROXIES=*`).

### 3.4 Cron

hPanel → **Avançado → Cron Jobs** → novo cron, **a cada minuto** (`* * * * *`). O `crontab` não existe no SSH: só pelo hPanel.

```cron
* * * * * /usr/bin/php /home/<usuario>/domains/<dominio>/vinia-app/backend/artisan queue:work --stop-when-empty --max-time=50 >> /dev/null 2>&1
```

Chama o worker **direto**, e não `schedule:run`: o agendador dispara o `queue:work` como subprocesso (`proc_open`), que está bloqueado
(seção 1.1). O worker encerra sozinho em até 50 s, deixando folga para o minuto seguinte. Se o PHP padrão do cron não for 8.3+,
troque `/usr/bin/php` pelo caminho completo da versão correta. Sem este cron a **importação de planilha nunca termina**.

**Segundo cron: expurgo dos pedidos de demonstração (Story 7.4).** Novo cron, **uma vez por dia** (`15 3 * * *`, 03:15, fora do
horário de uso):

```cron
15 3 * * * /usr/bin/php /home/<usuario>/domains/<dominio>/vinia-app/backend/artisan demo-requests:purge >> /home/<usuario>/domains/<dominio>/vinia-app/backend/storage/logs/demo-requests-purge.log 2>&1
```

Apaga em definitivo os pedidos de demonstração da landing com mais de 12 meses (prazo do aviso de privacidade, seção 6.2).
Também chama o artisan **direto**, pelo mesmo motivo do cron da fila: sem `schedule:run`, que não funciona aqui (`proc_open`
bloqueado, seção 1.1); por isso o expurgo **não** está no agendador do Laravel e só roda se este cron existir. Mesma regra do
PHP 8.3+ do cron acima. A saída vai para `backend/storage/logs/demo-requests-purge.log` (fora do document root, seção 2), e não
para `/dev/null`: o arquivo recebe **uma linha de contagem por dia** (ex.: `0 pedido(s) de demonstração com mais de 12 meses
apagado(s).`), nunca nome, e-mail ou telefone, e é a prova de que o expurgo roda. Conferir: `tail backend/storage/logs/demo-requests-purge.log`.
Para testar à mão por SSH (a partir de `vinia-app`): `php backend/artisan demo-requests:purge`.

**Mais três crons diários (Stories 9.3 e 9.4).** Seguem as mesmas regras dos dois acima: chamam o artisan **direto**, usam PHP 8.3+
e gravam num log próprio só contagens, nunca nome, e-mail ou documento. Os três aceitam `--dry-run`, que conta sem apagar nem
enviar nada, para testar à mão por SSH. Crie-os **depois** do deploy que traz os comandos (seção 5.1); antes disso, o artisan
responde que o comando não existe.

```cron
0 4 * * * /usr/bin/php /home/<usuario>/domains/<dominio>/vinia-app/backend/artisan comensal-sessions:purge >> /home/<usuario>/domains/<dominio>/vinia-app/backend/storage/logs/comensal-sessions-purge.log 2>&1
30 4 * * * /usr/bin/php /home/<usuario>/domains/<dominio>/vinia-app/backend/artisan signups:purge-unverified >> /home/<usuario>/domains/<dominio>/vinia-app/backend/storage/logs/signups-purge.log 2>&1
0 9 * * * /usr/bin/php /home/<usuario>/domains/<dominio>/vinia-app/backend/artisan trial:send-reminders >> /home/<usuario>/domains/<dominio>/vinia-app/backend/storage/logs/trial-reminders.log 2>&1
```

Os cinco crons da produção:

| Comando | Quando | O que faz | Sem ele |
|---|---|---|---|
| `queue:work --stop-when-empty --max-time=50` | a cada minuto | drena a fila: importação de planilha, e-mails do cadastro, lembretes, avisos de cota e de cobrança | a importação nunca termina e os e-mails enfileirados não saem |
| `demo-requests:purge` | 03:15 | apaga pedidos de demonstração com mais de 12 meses (Story 7.4) | a promessa do aviso de privacidade não é cumprida |
| `comensal-sessions:purge` | 04:00 | apaga sessões de celular com mais de 12 meses e as perguntas delas à Sofia, e também as linhas vencidas da tabela `cache` (Story 9.3) | o aparelho (`device_id`) e o IP ficam guardados além do prazo |
| `signups:purge-unverified` | 04:30 | apaga cadastros que nunca confirmaram o e-mail e o restaurante vazio de cada um (Story 9.4) | cadastros abandonados se acumulam no banco |
| `trial:send-reminders` | 09:00 | envia ao dono, pela fila, os lembretes do teste de 14 dias nos dias 7, 12 e 14 (Story 9.4) | o dono não é avisado de que o teste vai acabar |

Os horários seguem o relógio do servidor e podem mudar, desde que os crons diários fiquem fora do horário de uso. Confira no hPanel se o
plano aceita cinco crons.

## 4. Primeiro deploy

### 4.1 Acesso SSH e clone

hPanel → **Avançado → Acesso SSH** (ative e veja host/porta). Porta: **65002**.

```bash
ssh -p 65002 <usuario>@<ip-ou-host>
cd ~/domains/<dominio>

# Repositório privado: chave de deploy somente leitura
ssh-keygen -t ed25519 -f ~/.ssh/vinia_deploy -N "" -C "vinia-hostinger"
cat ~/.ssh/vinia_deploy.pub     # cadastre em GitHub → Settings → Deploy keys (sem escrita)
printf 'Host github.com\n  IdentityFile ~/.ssh/vinia_deploy\n  IdentitiesOnly yes\n' >> ~/.ssh/config

git clone git@github.com:rafaelmarques10/vinia-src.git vinia-app
```

### 4.2 `.env`, dependências e banco

```bash
cd ~/domains/<dominio>/vinia-app/backend
cp .env.example .env && chmod 600 .env
nano .env                                  # preencha APP_URL, DB_*, GROQ_API_KEY, R2... (seção 9)

composer install --no-dev --optimize-autoloader --no-interaction --no-scripts   # --no-scripts: proc_open bloqueado (seção 1.1)
php artisan package:discover
php artisan key:generate                   # grava APP_KEY no .env (faça uma vez; não troque depois)
php artisan migrate --force
ln -s ../storage/app/public public/storage # storage:link não funciona aqui (symlink() bloqueado); rode a partir de backend/
ls -l public/storage                       # deve mostrar: storage -> ../storage/app/public
```

> **Não rode `php artisan db:seed` em produção.** O `AdminSeeder` cria `admin@vinia.app` com a senha fixa
> `password` e o `DemoSeeder` cria dados de demonstração.

### 4.3 Primeiro acesso (admin e restaurante)

Os restaurantes clientes se cadastram sozinhos em `https://<dominio>/cadastro`, com teste de 14 dias (seção 6.3). A linha de
comando abaixo fica para a conta do operador e para algum caso especial; depois, ajuste o plano do restaurante em **Planos**, no
backoffice. A senha é gravada com hash automaticamente. Os perfis são `admin`, `owner`, `manager` e `sommelier`. **Vincule sempre o
usuário a um restaurante (`restaurant_id`), inclusive o `admin`**: Identidade, Carta de vinhos e Tablets recusam usuário sem restaurante.

**O perfil `admin` é reservado ao operador do Vinia (Rafael)** e **nunca** deve ser usado na conta de um restaurante
cliente: o `admin` vê dados de todos (por exemplo, os pedidos de demonstração da landing, com nome, e-mail e telefone).
A conta de um restaurante cliente é `owner` (dono) ou `manager`. Sem informar `role`, o usuário nasce `manager`.

Abra o console e cole **uma linha por vez** (blocos longos com aspas aninhadas costumam quebrar ao copiar):

```bash
php artisan tinker
```
```php
$r = App\Models\Restaurant::create(['name' => 'Nome do Restaurante', 'slug' => 'nome-do-restaurante']);
App\Models\User::create(['name' => 'Seu Nome', 'email' => 'voce@dominio.com', 'password' => 'UMA-SENHA-FORTE', 'role' => 'owner', 'restaurant_id' => $r->id]);
exit
```

O `slug` é único, em minúsculas e com hífens. A senha fica no histórico do tinker: troque-a depois do primeiro login, em **Minha conta** (ícone no cabeçalho do backoffice).
Depois cadastre pelo backoffice, nesta ordem: **Identidade** (nome real, logo, cores) → **Carta de vinhos** (um a um ou **Importar planilha**,
com o modelo em `/backoffice/wines/import/template`) → **Tablets** (ver seção 6.1).

### 4.4 Assets (build do front)

O servidor não builda. Na **primeira vez**, envie os assets do seu Mac (Node 22, ver `.nvmrc`):

```bash
cd vinia-app   # no seu computador
SSH_HOST=<ip-ou-host> SSH_USER=<usuario> APP_PATH=/home/<usuario>/domains/<dominio>/vinia-app \
  bash scripts/push-assets.sh
```

Isso builda (`npm run build:prod`) e envia para `.deploy-staging/`. Depois, no servidor:

```bash
cd ~/domains/<dominio>/vinia-app
bash scripts/deploy.sh      # com APP_PATH=$PWD, PHP_BIN=... se necessário
```

O `deploy.sh` troca os assets, roda migrations, refaz os caches e sobe o site. A partir daí, o CI faz isso a cada push.

### 4.5 Symlink do `public_html` e cron

Faça o symlink da seção 2 e crie o cron da seção 3.4. Acesse `https://<dominio>/backoffice/login`.

## 5. Deploys seguintes (automático)

Cada push na `main` dispara `.github/workflows/deploy.yml`:

1. Testes (SQLite e MySQL 8) com PHP 8.3.
2. `npm run build:prod` (Livewire/Vite + PWA em `backend/public/tablet`).
3. Envio por rsync (porta 65002; cai para `scp` se não houver rsync) para `$APP_PATH/.deploy-staging`.
4. Execução remota de `scripts/deploy.sh`: `artisan down` → `git pull --ff-only` → `composer install --no-dev --no-scripts`
   → `package:discover` → troca de assets → `migrate --force` → `optimize:clear`/`optimize`/`view:cache` → `queue:restart` → `artisan up`.
   Se algo falhar, o site **sai da manutenção sozinho** e a falha é registrada.

Secrets do repositório (GitHub → Settings → Secrets and variables → Actions):

| Secret | Valor |
|---|---|
| `SSH_HOST` | host/IP do SSH |
| `SSH_USER` | `<usuario>` |
| `SSH_KEY` | chave privada **dedicada ao deploy** (conteúdo completo). Cadastre a pública em `~/.ssh/authorized_keys` no servidor |
| `APP_PATH` | `/home/<usuario>/domains/<dominio>/vinia-app` (sem aspas nem espaços) |
| `PHP_BIN` (opcional) | caminho completo do PHP 8.3+ se o `php` do SSH for outro |
| `SSH_KNOWN_HOSTS` (opcional) | saída de `ssh-keyscan -p 65002 <host>`, para fixar a identidade do servidor |

**Sobre o `SSH_KEY`:** gere uma chave **dedicada e sem passphrase** e cadastre-a pelo terminal, nunca colando na interface:

```bash
ssh-keygen -t ed25519 -N "" -C "vinia-github-deploy" -f ~/.ssh/vinia_gha
ssh-copy-id -p 65002 -i ~/.ssh/vinia_gha.pub <usuario>@<host>      # pede a senha do SSH uma vez
ssh -p 65002 -i ~/.ssh/vinia_gha -o IdentitiesOnly=yes <usuario>@<host> 'echo ok'   # teste local antes do CI
gh secret set SSH_KEY < ~/.ssh/vinia_gha
gh secret set APP_PATH --body "/home/<usuario>/domains/<dominio>/vinia-app"
```

No log do Actions, usuário e host aparecem mascarados (`***`) e um secret ausente aparece como valor **vazio** (ex.: `APP_PATH:`).
Disparo manual: `gh workflow run "Deploy Hostinger"`.

**Mudança no próprio `deploy.sh`:** o script carrega a função inteira antes do `git pull`, então uma alteração nele só vale a partir do deploy
**seguinte**. Se o primeiro run falhar com o comportamento antigo, basta refazer só o job: `gh run rerun <id> --failed`.

**Sobre versionar `public/build`:** não versionamos. Os assets são gerados no CI e enviados por rsync; assim o git
fica limpo e não há conflito de merge em arquivos gerados. Contingência sem GitHub Actions: `scripts/push-assets.sh --deploy`.

### 5.1 Primeira publicação da versão SaaS (Stories 9.1 a 9.8 e layout de 2026-11)

A produção roda a versão anterior ao SaaS (`8dee49f`). O próximo push da `main` leva tudo de uma vez:
- o isolamento por restaurante;
- a carta pelo celular;
- o cadastro self-service;
- planos e cota;
- a cobrança pelo Asaas e os créditos extras;
- o layout novo do site, do backoffice e do app;
- **14 migrations**.

O `deploy.sh` roda o `migrate` sozinho, então **prepare o servidor antes do push**.

**Antes do push:**

1. **Dump do banco** (seção 8), guardado fora do servidor.
2. **Consultas de conferência** (por SSH com `mysql` ou pelo phpMyAdmin). As duas precisam voltar vazias ou zero:

   ```sql
   -- Story 9.1: interação sem sessão faz falhar o NOT NULL de ai_interactions.restaurant_id
   SELECT COUNT(*) FROM ai_interactions i LEFT JOIN comensal_sessions s ON s.id = i.session_id WHERE s.id IS NULL;
   -- Story 9.2: slug fora do padrão quebra a carta pública /r/{slug}
   SELECT id, slug FROM restaurants WHERE slug NOT REGEXP '^[A-Za-z0-9_-]+$';
   ```

   Se a primeira não der zero, corrija ou apague essas interações. Se a segunda trouxer linhas, troque o slug desses restaurantes.
3. **MariaDB ou MySQL 8?** Confira com `mysql --version`. A suíte roda em SQLite e MySQL 8, e uma migration altera uma coluna já
   existente (`->change()`). Se for MariaDB, teste antes numa cópia: restaure o dump num MariaDB da mesma versão no seu computador
   (Docker) e rode `php artisan migrate` a partir da `main`.
4. **`.env` de produção** (seções 6.3, 6.4 e 9): `TRIAL_HASH_KEY`, `ONBOARDING_CONTACT_EMAIL`, `MAIL_*` (agora obrigatórios),
   `BILLING_GATEWAY=asaas`, `ASAAS_ENV=production`, `ASAAS_API_KEY` e `ASAAS_WEBHOOK_TOKEN`.
5. **DNS do e-mail:** SPF, DKIM e DMARC (seção 6.3).
6. **Groq fora do nível gratuito** (seção 6).
7. **Admins:** `SELECT id, email, restaurant_id FROM users WHERE role = 'admin';` deve trazer só a conta do operador.

**Push:** `git push origin main` e acompanhe com `gh run watch`. **Se o `migrate` falhar**, o `deploy.sh` tira o site da
manutenção com o código novo e o banco pela metade: volte ao `.previous-release` (seção 8, emergência), rode `optimize` e
restaure o dump se alguma migration já tiver rodado.

**Depois do deploy:**

1. Crie os três crons diários novos (seção 3.4) e rode cada comando uma vez por SSH com `--dry-run`.
2. Cadastre o webhook no painel do Asaas de produção (seção 6.4).
3. Todo restaurante que já existia vira **legado** (sem cota nem limite). A tabela `trial_claims` nasce nesta publicação, então
   nenhum deles vira `trial`, e a consulta prévia da Story 9.5 não se aplica. Combine os valores e tire a marca de cada um em **Planos**;
   para um cliente específico, use o campo **Cota**.
4. Se mudar o `.env` depois do deploy, rode `php backend/artisan optimize:clear && php backend/artisan optimize`. O `deploy.sh` só faz isso
   durante o deploy.
5. Testes:
   - Sofia (seção 6).
   - Cadastro completo com um e-mail seu (seção 6.3).
   - Uma assinatura e um pacote de créditos pagos de verdade (seção 6.4).
   - IP real e QR impresso (seção 6.5).
   - Envio de foto do rótulo.
   - No iPad, se o ícone ou a abertura ainda mostrarem a aparência antiga, reinstale a PWA (seção 6.1).

## 6. Sofia (sommelier IA)

**Decisão:** a Sofia **não usa streaming** (SSE). No compartilhado o LiteSpeed pode bufferizar a resposta, e o
fluxo do app já era sem streaming. Por isso não existe a flag `SOFIA_STREAMING`.

Como funciona hoje:

1. O tablet faz `POST /api/v1/ai/recommend` e recebe `201` com `interaction_id` imediatamente.
2. **Depois que a resposta HTTP é enviada**, o mesmo processo PHP chama o Groq (timeout `SOFIA_TIMEOUT`, padrão 25 s;
   até 2 retentativas com backoff para 429/503/529) e grava o resultado.
3. A PWA consulta `GET /api/v1/ai/interactions/{id}` a cada 1,5 s mostrando **"Sofia está pensando..."**
   e exibe o texto quando `status = done`. Em falha, mostra a mensagem amigável; sem resposta em 90 s, sai do loading.

Variáveis: `GROQ_API_KEY` (só no `.env`, nunca vai ao front), `GROQ_MODEL`, `SOFIA_TIMEOUT`, `SOFIA_MAX_TOKENS`,
`SOFIA_RETRY_TIMES` e `SOFIA_QUEUE`.

`SOFIA_QUEUE=true` enfileira a Sofia em vez de processar após a resposta. Use **apenas** como plano B: a fila só
anda a cada minuto (cron), então a resposta pode demorar até ~1 min.

**Conta da Groq:** suba para o Dev Tier antes de ter clientes. O nível gratuito limita a conta a 8.000 tokens por minuto, o que
trava a Sofia com poucas consultas ao mesmo tempo, e nele a Groq não devolveu os tokens em cache. Depois de subir, repita duas
consultas iguais e confira se `tokens_cached` aparece em `ai_usage`. O custo por consulta usa `config/ai_pricing.php` (preço por milhão
de tokens e o câmbio `AI_USD_BRL`): confira os valores contra a tabela atual da Groq.

### Como testar a Sofia em produção

O token vem de **Backoffice → Tablets**.

```bash
D=https://<dominio>; T=<token-do-tablet>
H=(-H "Authorization: Bearer $T" -H "Accept: application/json" -H "Content-Type: application/json")

SID=$(curl -s -X POST "$D/api/v1/sessions" "${H[@]}" | sed -E 's/.*"session_id":"([^"]+)".*/\1/')

# O POST precisa voltar em menos de ~2 s; é esse tempo que prova que o "após a resposta" funciona no LiteSpeed
curl -s -o /dev/null -w 'POST: HTTP %{http_code} em %{time_total}s\n' -X POST "$D/api/v1/ai/recommend" "${H[@]}" \
  -d "{\"session_id\":\"$SID\",\"type\":\"recommend_dish\",\"input\":{\"dish\":\"risoto de cogumelos\"}}"

curl -s "$D/api/v1/ai/interactions/1" "${H[@]}"     # use o interaction_id retornado; repita até status "done"
```

Resultado esperado: `HTTP 201` em poucos décimos de segundo; `status` evolui `pending → processing → done` em alguns segundos.
**Se o POST demorar o mesmo tempo da IA (15-30 s)**, o servidor está segurando a resposta até o fim do processamento:
use `SOFIA_QUEUE=true` provisoriamente e avalie a seção 10.

### 6.1 Tablet (PWA) no iPad

O tablet abre `https://<dominio>/tablet/?token=<token>` (o token e o QR code vêm de **Backoffice → Tablets**; confira que
`TABLET_URL=https://<dominio>/tablet`, no mesmo domínio, sem subdomínio). O app instalado na tela de início do iPad tem armazenamento
separado do Safari e abre o `start_url` do manifest, então o token precisa viajar nele. Como funciona:

- o token fica em `localStorage`;
- `GET /tablet/app.webmanifest?token=...` devolve o manifest com o `start_url` já contendo o token (só aceita 64 hexadecimais);
- quando a página abre com `?token=`, o **servidor** entrega o HTML com o `<link rel="manifest">` daquele tablet, e o service worker não
  intercepta essa navegação;
- `public/.htaccess` manda `/tablet/` com `?token=` ao Laravel (sem isso o servidor web entrega o `index.html` estático direto).

**Para instalar no iPad:** (1) apague o ícone antigo da tela inicial; (2) Ajustes → Safari → Avançado → Dados dos Sites → remova
o domínio (derruba o service worker antigo); (3) no Safari, abra `https://<dominio>/tablet/?token=<token>` (com a barra antes do `?`)
e espere a carta carregar; (4) Compartilhar → **Adicionar à Tela de Início** e abra pelo ícone. Fechar e reabrir deve continuar logado.

Regenerar o token do tablet no backoffice **invalida o ícone** (o token antigo está no `start_url`): repita os passos acima.
Para validar o servidor sem o iPad: `curl -s "https://<dominio>/tablet/?token=<64 hex qualquer>" | grep manifest` deve mostrar
`app.webmanifest?token=...`; sem token, `manifest.webmanifest`.

### 6.2 Landing pública e e-mail de aviso (Story 7.1)

`https://<dominio>/` serve a landing pública (antes redirecionava ao login; o backoffice segue em `/backoffice/login`).
O formulário "Quero uma demonstração" (`POST /demonstracao`, limite de 5 envios por minuto por IP) grava o pedido na
tabela `demo_requests` (criada pela migration, que roda sozinha no deploy) e depois envia um e-mail de aviso, **de forma
síncrona** (não depende do cron da fila).

**O pedido fica gravado mesmo que o e-mail falhe.** Sem SMTP configurado, a landing funciona e os pedidos aparecem no
backoffice (Story 7.2); só o aviso não sai, e a falha fica no log como `warning`.

**Retenção de 12 meses (Story 7.4).** O aviso de privacidade da landing promete guardar os pedidos por 12 meses. O comando
`demo-requests:purge` apaga em definitivo (sem lixeira) os pedidos de **qualquer status** com mais de 12 meses, contados da
data do pedido; ele roda pelo cron diário da seção 3.4. **Sem esse cron a promessa do aviso não é cumprida.** Mudar o prazo
exige mudar o código e o texto do aviso juntos. Exclusão antecipada a pedido do titular continua manual, pelo contato do aviso.

**Configurar o e-mail (no `backend/.env` do servidor):**

1. hPanel → **E-mails**: crie a caixa que vai enviar os avisos (ex.: um endereço do próprio domínio) e anote a senha.
   Os dados de SMTP (servidor, porta e criptografia) aparecem no hPanel, na configuração da caixa.
2. Preencha no `.env`:

   ```dotenv
   MAIL_MAILER=smtp
   MAIL_HOST=<servidor SMTP indicado no hPanel>
   MAIL_PORT=465                  # 465 com MAIL_SCHEME=smtps; 587 com MAIL_SCHEME=smtp (STARTTLS)
   MAIL_USERNAME=<endereço completo da caixa>
   MAIL_PASSWORD=<senha da caixa>
   MAIL_SCHEME=smtps
   MAIL_TIMEOUT=10                # segundos de espera pelo SMTP; padrão 10
   MAIL_FROM_ADDRESS=<mesmo endereço da caixa>
   MAIL_FROM_NAME="${APP_NAME}"
   DEMO_NOTIFY_TO=rafael.marques10@gmail.com
   ```

   `MAIL_SCHEME` substitui o antigo `MAIL_ENCRYPTION`, que o Laravel 11+ não lê mais (o `config/mail.php` usa `MAIL_SCHEME`).
   `MAIL_TIMEOUT` limita a espera pelo SMTP (conexão e resposta). Como o envio é síncrono, sem esse limite um SMTP
   inalcançável (host errado, porta bloqueada) travaria o formulário até o erro fatal de tempo do PHP (30 s), sem
   resposta ao visitante. Com o limite, o envio desiste, o erro vai para o log e o visitante vê a mensagem de sucesso.
   Mantenha bem abaixo de 30. Confira também se a Hostinger libera a saída na porta escolhida (465 ou 587).
   `MAIL_FROM_ADDRESS` **precisa ser preenchido no servidor** com o endereço da caixa: o `.env.example` traz
   `no-reply@vinia.ia.br` só para que o envio não falhe por falta de remetente, mas o SMTP da caixa costuma recusar
   remetente de outro endereço.
   `DEMO_NOTIFY_TO` é o destino do aviso; para trocar o destinatário basta mudar a variável, sem alterar código.
3. Aplique: `php backend/artisan optimize:clear && php backend/artisan optimize`.

**Testar:** envie o formulário da landing com dados reais. Deve aparecer "Recebemos seu pedido. Entraremos em contato
em breve.", e o e-mail "Novo pedido de demonstração — <restaurante>" chega em `DEMO_NOTIFY_TO`. Se o e-mail não chegar,
procure no log: `grep -i "pedido de demonstração" backend/storage/logs/laravel-*.log`.

**Indexação:** `public/robots.txt` bloqueia `/backoffice` e `/tablet`; a tela de login tem `noindex` e a PWA responde com
o cabeçalho `X-Robots-Tag: noindex` (pelo Laravel e pelo `public/.htaccess`, para os arquivos estáticos de `public/tablet`).
Conferir: `curl -sI https://<dominio>/tablet/ | grep -i x-robots-tag`.

### 6.3 Cadastro self-service e e-mails transacionais (Story 9.4)

`https://<dominio>/cadastro` cria o restaurante e o dono, com CPF ou CNPJ. O **teste de 14 dias começa quando o dono confirma o
e-mail**, pelo link assinado que a fila envia. Por isso, nesta versão o SMTP (seção 6.2) deixa de ser opcional: sem e-mail, ninguém
termina o cadastro, recupera a senha nem aceita um convite de equipe.

- **`TRIAL_HASH_KEY`:** chave que impede repetir o teste com o mesmo CPF. Gere **uma vez**, com
  `php artisan tinker --execute="echo base64_encode(random_bytes(32));"`, e guarde junto com a `APP_KEY`. Sem ela, o cadastro
  por CPF falha de propósito. Trocar a chave faz o app esquecer os CPFs que já usaram o teste.
- **`ONBOARDING_CONTACT_EMAIL`:** contato mostrado no cadastro e nos avisos de cota. Se ficar vazio, vale o `DEMO_NOTIFY_TO`.
- **SPF, DKIM e DMARC** no DNS do domínio (hPanel → Domínios → DNS), com os valores que a área de E-mails do hPanel indica. Sem eles,
  o e-mail de confirmação cai no spam e o cadastro trava.
- **`APP_URL` exato**, em `https`: a fila gera o link de confirmação fora de um request, a partir do `APP_URL`.

**Testar:** faça um cadastro com um e-mail seu, confirme pelo link e percorra o assistente de 4 passos até a carta.

### 6.4 Cobrança pelo Asaas (Stories 9.7 e 9.8)

O dono assina em **Meu plano**, pelo link hospedado do Asaas, e compra ali os pacotes de créditos extras. O acesso segue o pagamento
confirmado: o Asaas avisa pelo webhook, e o app reconsulta a cobrança antes de liberar. Os avisos por e-mail usam a fila.

1. **`.env`:** `BILLING_GATEWAY=asaas`, `ASAAS_ENV=production`, `ASAAS_API_KEY` (a chave **de produção**, diferente da do sandbox) e
   `ASAAS_WEBHOOK_TOKEN` (32 a 255 caracteres, diferente da chave). `BILLING_TOLERANCE_DAYS` é opcional. Com `BILLING_GATEWAY=fake`,
   o padrão do exemplo, nada é cobrado e nenhum pagamento se confirma.
2. **Webhook**, cadastrado no painel do Asaas de produção:
   - URL `https://<dominio>/api/webhooks/asaas`, com o mesmo token do `.env`;
   - eventos de cobrança: confirmada, recebida, vencida, estornada e chargeback;
   - evento de assinatura removida.

   Sandbox e produção têm webhooks separados. Token ausente ou diferente recebe `401`.
3. **Nota fiscal:** só ligue `ASAAS_NFSE_ENABLED=true` depois de definir com a contabilidade:
   - o serviço municipal (`ASAAS_NFSE_SERVICE_ID` ou `ASAAS_NFSE_SERVICE_CODE` e `ASAAS_NFSE_SERVICE_NAME`);
   - a alíquota de ISS (`ASAAS_NFSE_ISS_PERCENT`);
   - o CST de PIS/COFINS (`ASAAS_NFSE_PIS_COFINS_CST`).
4. **Preços:** os planos ficam em `config/plans.php`, o pacote de créditos em `config/billing.php` (`credits`). Mudar exige deploy.
5. **Tipo de cobrança:** hoje o código usa `UNDEFINED`, em que o cliente escolhe Pix, boleto ou cartão a cada cobrança. Trocar para
   `CREDIT_CARD`, em que o cartão renova sozinho, é mudança de código.

**Testar:** pague uma assinatura e um pacote de créditos de verdade. Confira a coluna Cobrança em **Planos** e o saldo em
**Meu plano**. Se o acesso não liberar, veja as entregas do webhook no painel do Asaas e o log.

### 6.5 Carta pelo celular, com o QR da mesa (Stories 9.2 e 9.3)

`https://<dominio>/r/<slug>` abre a carta pública do restaurante. Com a chave do QR (`#k=...`), abre também uma sessão curta da Sofia
no celular do cliente. O acesso por celular vem **desligado**; o gestor liga em **Acesso por celular**, e só no plano assinado.

- **Limites:** são as variáveis `SOFIA_PHONE_*` do `.env`. Os valores do exemplo são os padrões; só mude para apertar ou afrouxar um limite.
- **IP real:** as cotas por IP dependem de o app enxergar o IP do visitante, e não o do proxy (`TRUSTED_PROXIES=*`, seção 3.3). Para
  conferir, troque a senha em **Minha conta** e veja em `backend/storage/logs/audit-AAAA-MM-DD.log`: o `ip` da linha
  `account.password_changed` deve ser o seu IP público, e não `127.0.0.1` nem um IP interno.
- **QR impresso:** teste em iPhone e em Android, com a câmera, o Google Lens, o WhatsApp e o Instagram. A chave fica depois do `#`,
  e alguns leitores e navegadores embutidos cortam essa parte.
- **Retenção:** o cron `comensal-sessions:purge` (seção 3.4).
- **Troca da `APP_KEY`:** se ela mudar, ponha a antiga em `APP_PREVIOUS_KEYS`, porque a chave do QR é gravada criptografada.

## 7. Checklist de go-live

- [ ] PHP 8.3+ no hPanel e no CLI; extensões da seção 3.1
- [ ] Banco MySQL criado; `DB_*` preenchido; backup/dump feito antes do primeiro dado real
- [ ] `.env` com `APP_ENV=production`, `APP_DEBUG=false`, `APP_URL` em `https`, `LOG_CHANNEL=daily`, `LOG_LEVEL=warning`, `chmod 600`
- [ ] `APP_KEY` gerado **uma vez** e guardado em local seguro (perder a chave invalida sessões)
- [ ] `php artisan migrate --force` sem erros; **`db:seed` não foi executado**
- [ ] Usuário do restaurante criado como `owner` (ou `manager`) com senha forte (seção 4.3); `admin` só para o operador do Vinia; `admin@vinia.app` não existe
- [ ] DNS com registro A apontando para a hospedagem (`dig +short <dominio>` devolve o IP)
- [ ] Symlink `public_html -> vinia-app/backend/public` correto; `https://<dominio>/.env` e `/.git/config` retornam 403 ou 404 (nunca o conteúdo)
- [ ] `backend/public/storage` existe (`ln -s ../storage/app/public public/storage`)
- [ ] SSL ativo e "Forçar HTTPS" ligado
- [ ] Cron de 1 minuto criado chamando `queue:work --stop-when-empty --max-time=50` direto (seção 3.4)
- [ ] Cron diário do expurgo `demo-requests:purge` criado (seção 3.4); execução manual por SSH sem erro e `backend/storage/logs/demo-requests-purge.log` recebendo a linha de contagem
- [ ] `public/build` e `public/tablet` presentes; `/tablet/` abre e `/tablet/manifest.webmanifest` responde 200
- [ ] PWA instalada no iPad pelo procedimento da seção 6.1, abrindo autenticada pelo ícone e continuando logada ao reabrir
- [ ] QR code do tablet aponta para `TABLET_URL` correto (`https://<dominio>/tablet`)
- [ ] Upload de foto de vinho e de logo funcionando (R2 ou `public/storage`)
- [ ] Importação de planilha de vinhos funcionando
- [ ] Teste da Sofia (seção 6) com POST rápido e resposta `done`
- [ ] Secrets do GitHub cadastrados e um deploy de teste concluído pelo Actions
- [ ] Rotação de logs: `storage/logs/laravel-AAAA-MM-DD.log` sendo criado, sem erros
- [ ] Landing em `https://<dominio>/` com o aviso de privacidade revisado (sem o marcador `[CONTATO PARA EXCLUSÃO]`)
- [ ] `MAIL_*` e `DEMO_NOTIFY_TO` preenchidos; um pedido de teste pela landing gravado e o e-mail de aviso recebido (seção 6.2)
- [ ] `https://<dominio>/robots.txt` com `Disallow: /backoffice` e `Disallow: /tablet`
- [ ] Conferências de antes do push da versão SaaS feitas e dump guardado fora do servidor (seção 5.1)
- [ ] Os três crons diários novos criados (seção 3.4), cada comando rodado uma vez com `--dry-run`, sem erro
- [ ] `TRIAL_HASH_KEY` gerada e guardada junto com a `APP_KEY`; `ONBOARDING_CONTACT_EMAIL` preenchido
- [ ] SPF, DKIM e DMARC no DNS; um cadastro de teste confirmado pelo e-mail (seção 6.3)
- [ ] `BILLING_GATEWAY=asaas` com chave e token de produção; webhook cadastrado; uma assinatura e um pacote pagos e liberados (seção 6.4)
- [ ] Groq fora do nível gratuito; `config/ai_pricing.php` conferido (seção 6)
- [ ] IP real conferido no `audit` e QR impresso testado em iPhone e Android (seção 6.5)
- [ ] Só a conta do operador com `role = 'admin'`
- [ ] Restaurantes antigos revisados em **Planos** (marca de legado retirada depois de combinar os valores)

## 8. Rollback

Antes de qualquer deploy com **migration**, faça um dump do banco (hPanel → Backups, ou
`mysqldump -u <usuario_db> -p <banco> > ~/backup-$(date +%F-%H%M).sql`).

**Caminho recomendado (≈ 5 min):** reverter o commit problemático (`git revert <sha>`) e publicar na `main`.
O CI testa, builda e faz o deploy completo, inclusive dos assets.

**Emergência (mais rápido), por SSH:** o `deploy.sh` guarda o commit anterior em `backend/storage/app/.previous-release`
e os assets anteriores em `backend/public/build.prev` e `backend/public/tablet.prev`.

```bash
cd ~/domains/<dominio>/vinia-app
php backend/artisan down --retry=15
git reset --hard "$(cat backend/storage/app/.previous-release)"
(cd backend && composer install --no-dev --optimize-autoloader --no-interaction)

cd backend/public
rm -rf build tablet && mv build.prev build && mv tablet.prev tablet
cd ../..

php backend/artisan optimize:clear && php backend/artisan optimize
php backend/artisan queue:restart
php backend/artisan up
```

Depois da emergência, o próximo deploy volta a funcionar normalmente (`git pull --ff-only` avança até a `main`),
mas **reverta o commit ruim na `main`** para não reaplicá-lo.

**Migrations:** o rollback de código não desfaz o banco. Se a migration for aditiva (coluna/tabela nova), o código
antigo costuma conviver com ela. Se não for, restaure o dump ou use `php artisan migrate:rollback --step=1`
apenas quando o método `down()` daquela migration for seguro.

## 9. Variáveis do `.env` a preencher

Obrigatórias: `APP_KEY` (gerado), `APP_URL`, `DB_DATABASE`, `DB_USERNAME`, `DB_PASSWORD`, `GROQ_API_KEY`,
`SANCTUM_STATEFUL_DOMAINS` (o domínio, sem `https://`) e `TABLET_URL`.
Opcionais: `CLOUDFLARE_R2_*` (sem elas as imagens ficam em `storage/app/public`), `TRUSTED_PROXIES`, `SOFIA_*`.
E-mail de aviso da landing (seção 6.2): `MAIL_MAILER`, `MAIL_HOST`, `MAIL_PORT`, `MAIL_USERNAME`, `MAIL_PASSWORD`,
`MAIL_SCHEME`, `MAIL_FROM_ADDRESS`, `MAIL_FROM_NAME` e `DEMO_NOTIFY_TO`. Sem eles, a landing funciona e grava os pedidos,
mas o cadastro self-service não (seção 6.3): com o cadastro aberto, os `MAIL_*` são **obrigatórios**. `MAIL_FROM_ADDRESS` vem
como `no-reply@vinia.ia.br` no exemplo; troque pelo endereço da caixa. `MAIL_TIMEOUT` (segundos, padrão 10) já vem preenchido;
mantenha abaixo de 30.
Cadastro (seção 6.3): `TRIAL_HASH_KEY` (obrigatória) e `ONBOARDING_CONTACT_EMAIL`.
Cobrança (seção 6.4): `BILLING_GATEWAY`, `ASAAS_ENV`, `ASAAS_API_KEY` e `ASAAS_WEBHOOK_TOKEN`, obrigatórias para cobrar. Opcionais:
`BILLING_TOLERANCE_DAYS`, `ASAAS_NFSE_*` e `AI_USD_BRL`.
Sofia e celular (seções 6 e 6.5): `SOFIA_TABLET_QUERIES_PER_SESSION` e `SOFIA_PHONE_*` já vêm com os padrões;
`SOFIA_PROMPT_FULL_CARTA_MAX` (60) e `SOFIA_PROMPT_SELECTION_SIZE` (40) são opcionais.
Os demais valores já vêm corretos no `backend/.env.example`.

## 10. Quando migrar para uma VPS

Considere sair do compartilhado quando ocorrer qualquer um destes sinais:

- **Sofia lenta ou instável:** o `POST /ai/recommend` demora quase o mesmo tempo da IA (o LiteSpeed segura a resposta), ou
  você quer streaming/SSE confiável (precisa controlar buffering do servidor web).
- **Carga de polling:** cada tablet esperando a Sofia consulta a API a cada 1,5 s. Dezenas de tablets simultâneos geram
  dezenas de requisições por segundo, e a Hostinger limita processos PHP concorrentes. Sinais: erros 508/503, lentidão
  no backoffice quando há muitos tablets em uso, ou aviso de limite de recursos no hPanel.
- **Fila acima do que o cron suporta:** jobs que se acumulam porque 1 worker por minuto não dá conta (importações grandes de
  planilha, volume alto de IA via fila), ou necessidade de latência de fila abaixo de ~1 min.
- **Necessidade de Redis:** rate limit mais agressivo, cache/sessão com alta concorrência, filas com Horizon, broadcasting.
- **Necessidade de PostgreSQL:** recursos específicos (busca textual avançada, extensões como `pgvector`, JSONB indexado).
  O código hoje é agnóstico de banco; o `docker-compose.yml` tem o Postgres como perfil opcional.
- **WebSockets/Reverb** ou qualquer processo de longa duração (workers 24/7 com Supervisor).
- **Requisitos de disponibilidade/isolamento** que o plano compartilhado não garante (deploy sem janela de manutenção, múltiplos ambientes).

Ao migrar, o caminho é: `SOFIA_QUEUE=true` com worker persistente (Supervisor), `QUEUE_CONNECTION=redis`, e reavaliar o
polling por SSE/WebSocket.

## 11. Problemas comuns

| Sintoma | Causa provável | O que fazer |
|---|---|---|
| 500 logo após o deploy | `.env` inválido, `APP_KEY` vazia ou permissão de `storage/` | `tail -n 50 backend/storage/logs/laravel-*.log`; `chmod -R u+rwX backend/storage backend/bootstrap/cache` |
| CSS/JS do backoffice não carrega | `public/build` ausente ou HTTP/HTTPS misto | Rodar o CI de novo; conferir `APP_URL` em `https` |
| `/tablet/` dá 404 | `public/tablet` não foi enviado | Conferir o passo de rsync no Actions |
| Login do backoffice volta para a tela de login | `SESSION_DOMAIN`, `SESSION_SECURE_COOKIE` ou HTTP/HTTPS misto | `SESSION_DOMAIN=null`, SSL ativo, `php artisan optimize:clear` |
| Imagens quebradas | `public/storage` ausente ou R2 sem URL pública | `ln -s ../storage/app/public public/storage` (a partir de `backend/`); conferir `CLOUDFLARE_R2_PUBLIC_URL` |
| Importação de planilha nunca termina | Cron não está rodando ou usa `schedule:run` | Conferir o cron do `queue:work` direto (seção 3.4) |
| Deploy parou em "Modo manutenção" | Processo interrompido | Sair manualmente: `php backend/artisan up` |
| `The Process class relies on proc_open` no `composer install` | `proc_open` bloqueado (seção 1.1) | `--no-scripts` + `php artisan package:discover` |
| `storage:link` falha | `symlink()` bloqueado | `ln -s ../storage/app/public public/storage` (a partir de `backend/`) |
| `Access denied for user` no `migrate` | `DB_HOST` com o hostname externo | `DB_HOST=127.0.0.1` |
| CI: `Load key ... error in libcrypto` / `Permission denied (publickey)` | `SSH_KEY` colada errada, com passphrase, ou pública fora do `authorized_keys` | Gerar chave sem passphrase e usar `gh secret set SSH_KEY < arquivo` (seção 5) |
| CI: `APP_PATH:` vazio no log do rsync/deploy | Secret `APP_PATH` não cadastrado | `gh secret set APP_PATH --body ...` |
| Site não abre de fora (`Could not resolve host`) | DNS em parking, sem registro A | Seção 3.3 |
| Pedido de demonstração gravado, mas o e-mail não chega | `MAIL_*` ou `DEMO_NOTIFY_TO` vazios/errados, ou porta e `MAIL_SCHEME` trocados | Ver o `warning` no log; conferir a seção 6.2 e rodar `php artisan optimize:clear && php artisan optimize` |
| Pedidos de demonstração antigos não são apagados | Cron do expurgo ausente, usando `schedule:run`, ou com PHP errado (abaixo de 8.3) | `tail backend/storage/logs/demo-requests-purge.log`: sem linha do dia, o cron não rodou; conferir o cron do `demo-requests:purge` (seção 3.4) e rodar à mão `php backend/artisan demo-requests:purge` |
| Ícone do iPad abre a carta "sem vinhos" | Ícone criado sem o token no `start_url` | Procedimento da seção 6.1 (apagar ícone, limpar dados do site, reinstalar) |
| Site no ar, mas com erro depois de um deploy com migration | O `migrate` falhou no meio e o site voltou com o código novo | Seção 5.1: voltar ao `.previous-release` (seção 8) e restaurar o dump |
| Cadastro por CPF dá erro | `TRIAL_HASH_KEY` vazia | Gerar a chave (seção 6.3) e rodar `php backend/artisan optimize:clear && php backend/artisan optimize` |
| E-mail de confirmação não chega ou cai no spam | Cron da fila parado, `MAIL_*` errados ou SPF/DKIM/DMARC ausentes | Conferir o cron do `queue:work` (seção 3.4) e o DNS do e-mail (seção 6.3) |
| Link de confirmação aponta para outro endereço | `APP_URL` errado | Corrigir o `APP_URL` e rodar `optimize:clear` e `optimize` |
| Pagamento feito, mas o acesso não libera | Webhook não cadastrado, token diferente (`401`) ou cadastrado só no sandbox | Seção 6.4; o painel do Asaas mostra as entregas do webhook |
| Celular: "muitas tentativas" para todas as mesas | O app vê o IP do proxy no lugar do visitante | Seção 6.5 (IP real) |
