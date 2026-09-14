# Infra — Ambiente e Deploy

> Status: ready | Versão: 1.0

## Ambientes

| Ambiente | Propósito | URL |
|---|---|---|
| `local` | Desenvolvimento | http://localhost:8000 |
| `staging` | Testes e QA | https://staging.vinia.app |
| `production` | Produção | https://app.vinia.app |

---

## Variáveis de Ambiente

```env
# ── Aplicação ─────────────────────────────
APP_NAME=Vinia
APP_ENV=production          # local | staging | production
APP_KEY=                    # gerado via: php artisan key:generate
APP_DEBUG=false             # true apenas em local
APP_URL=https://app.vinia.app

# ── Banco de Dados ────────────────────────
DB_CONNECTION=pgsql
DB_HOST=
DB_PORT=5432
DB_DATABASE=vinia
DB_USERNAME=
DB_PASSWORD=

# ── Banco de Dados — Teste ────────────────
DB_TEST_CONNECTION=sqlite
DB_TEST_DATABASE=:memory:

# ── Fila ──────────────────────────────────
QUEUE_CONNECTION=database   # MVP: database | Futuro: redis

# ── Cache ─────────────────────────────────
CACHE_DRIVER=database       # MVP: database | Futuro: redis

# ── Storage — Cloudflare R2 ───────────────
FILESYSTEM_DISK=r2
CLOUDFLARE_R2_BUCKET=vinia-assets
CLOUDFLARE_R2_ENDPOINT=https://{account_id}.r2.cloudflarestorage.com
CLOUDFLARE_R2_ACCESS_KEY=
CLOUDFLARE_R2_SECRET_KEY=
CLOUDFLARE_R2_PUBLIC_URL=https://assets.vinia.app

# ── IA — Anthropic ────────────────────────
ANTHROPIC_API_KEY=
ANTHROPIC_MODEL=claude-sonnet-4-6
ANTHROPIC_MAX_TOKENS=1000
AI_RATE_LIMIT_PER_SESSION=10

# ── E-mail ────────────────────────────────
MAIL_MAILER=smtp
MAIL_HOST=
MAIL_PORT=587
MAIL_USERNAME=
MAIL_PASSWORD=
MAIL_FROM_ADDRESS=noreply@vinia.app
MAIL_FROM_NAME=Vinia

# ── Sanctum ───────────────────────────────
SANCTUM_STATEFUL_DOMAINS=app.vinia.app,localhost
SESSION_DOMAIN=.vinia.app
```

---

## Infraestrutura — MVP

### Hosting: Railway (recomendado) ou Render

```
Serviços Railway:
├── Web Service     → Laravel (PHP 8.3, porta 8000)
├── Worker Service  → Laravel Queue Worker (php artisan queue:work)
└── PostgreSQL      → Banco de dados gerenciado
```

**Comandos de start no Railway:**

```bash
# Web Service
php artisan migrate --force && php artisan serve --host=0.0.0.0 --port=8000

# Worker Service
php artisan queue:work --sleep=3 --tries=3 --max-time=3600
```

### Cloudflare R2 — Storage

```
Buckets:
└── vinia-assets/
    ├── restaurants/{restaurant_id}/
    │   └── logo.{ext}
    └── wines/{restaurant_id}/
        └── {wine_id}.{ext}
```

**Configuração do disco Laravel (config/filesystems.php):**
```php
'r2' => [
    'driver'                  => 's3',
    'key'                     => env('CLOUDFLARE_R2_ACCESS_KEY'),
    'secret'                  => env('CLOUDFLARE_R2_SECRET_KEY'),
    'region'                  => 'auto',
    'bucket'                  => env('CLOUDFLARE_R2_BUCKET'),
    'url'                     => env('CLOUDFLARE_R2_PUBLIC_URL'),
    'endpoint'                => env('CLOUDFLARE_R2_ENDPOINT'),
    'use_path_style_endpoint' => true,
    'visibility'              => 'public',
],
```

---

## Pipeline de Deploy

### Deploy backend (Laravel)

```bash
# 1. Instalar dependências
composer install --no-dev --optimize-autoloader

# 2. Compilar assets (se houver)
npm ci && npm run build

# 3. Migrations
php artisan migrate --force

# 4. Cache de configuração
php artisan config:cache
php artisan route:cache
php artisan view:cache

# 5. Reiniciar queue worker
php artisan queue:restart
```

### Deploy frontend (React/Vite)

```bash
# 1. Instalar dependências
npm ci

# 2. Build de produção
VITE_API_URL=https://api.vinia.app npm run build

# 3. Output: dist/ → deploy na Cloudflare Pages ou Vercel
```

---

## Checklist de Produção

- [ ] `APP_DEBUG=false`
- [ ] `APP_KEY` gerado e salvo com segurança
- [ ] `ANTHROPIC_API_KEY` configurada como secret (não em código)
- [ ] Banco com backup automático habilitado
- [ ] SSL ativo em todos os domínios
- [ ] Queue worker rodando como serviço persistente
- [ ] Logs configurados (Laravel Log → arquivo ou serviço externo)
- [ ] Rate limiting da API ativo (10 req/min por IP no throttle padrão)
- [ ] Cloudflare R2 bucket com CORS configurado para o domínio da carta digital
- [ ] Monitoramento básico de uptime (ex: Better Uptime, UptimeRobot)

---

## CORS — Configuração

```php
// config/cors.php
'allowed_origins' => [
    'https://app.vinia.app',    // backoffice
    'https://carta.vinia.app',  // carta digital (tablet)
    'http://localhost:5173',    // React dev server local
],
'allowed_methods' => ['GET', 'POST', 'PATCH', 'DELETE', 'OPTIONS'],
'allowed_headers' => ['Content-Type', 'Authorization', 'Accept'],
```

---

## Domínios

| Subdomínio | Propósito |
|---|---|
| `app.vinia.app` | Backoffice Laravel |
| `carta.vinia.app` | Carta digital React (PWA do tablet) |
| `assets.vinia.app` | CDN do Cloudflare R2 (logos, fotos) |
| `api.vinia.app` | API REST (pode ser o mesmo do backoffice em `/api`) |
