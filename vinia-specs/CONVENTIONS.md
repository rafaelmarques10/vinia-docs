# Vinia — Convenções Globais

> Status: ready | Versão: 1.0

## Stack

| Camada | Tecnologia |
|---|---|
| Backend / Backoffice | PHP 8.3 + Laravel 11 + Livewire 3 |
| API REST | Laravel 11 (JSON API) |
| Frontend Tablet | React 18 + Vite + Tailwind CSS |
| Banco de Dados | PostgreSQL 16 |
| IA | Anthropic API — claude-sonnet-4-6 |
| Storage | Cloudflare R2 |
| Auth | Laravel Sanctum |
| Queue | Laravel Queues (driver: database no MVP) |
| Hosting | Railway ou Render |

---

## Convenções de Código

### PHP / Laravel

- PSR-12 para formatação
- Namespace raiz: `App\`
- Models em `app/Models/`
- Services em `app/Services/` (lógica de negócio)
- Jobs em `app/Jobs/` (tarefas assíncronas, incluindo IA)
- Requests em `app/Http/Requests/` (validação)
- Resources em `app/Http/Resources/` (transformação JSON)
- Policies em `app/Policies/` (autorização)
- Todos os métodos públicos com tipagem explícita
- Nunca lógica de negócio em Controllers — delegar a Services

### React

- Componentes em `src/components/`
- Páginas em `src/pages/`
- Hooks customizados em `src/hooks/`
- Serviços de API em `src/services/`
- Tipos TypeScript em `src/types/`
- Usar React Query para todas as chamadas à API

### Banco de Dados

- Tabelas no plural, snake_case: `restaurants`, `wines`, `ai_interactions`
- Colunas em snake_case
- FKs sempre com sufixo `_id`: `restaurant_id`, `tablet_id`
- Sempre incluir `created_at` e `updated_at` (timestamps do Laravel)
- Soft deletes (`deleted_at`) onde recuperação for necessária
- Indexes em todas as FKs e colunas usadas em filtros frequentes
- Migrations nomeadas: `YYYY_MM_DD_HHMMSS_create_{tabela}_table.php`

---

## Convenções de API

- Prefixo: `/api/v1/`
- Autenticação: `Authorization: Bearer {token}` (Sanctum)
- Formato: JSON exclusivamente
- Respostas de sucesso: HTTP 200 ou 201
- Respostas de erro: estrutura padrão abaixo

### Estrutura de resposta padrão

```json
// Sucesso — lista
{
  "data": [...],
  "meta": { "total": 42, "page": 1, "per_page": 20 }
}

// Sucesso — item único
{
  "data": { ... }
}

// Erro
{
  "error": {
    "code": "WINE_NOT_FOUND",
    "message": "Rótulo não encontrado",
    "details": {}
  }
}
```

### Códigos de erro customizados

| Código | HTTP | Situação |
|---|---|---|
| `UNAUTHORIZED` | 401 | Token inválido ou ausente |
| `FORBIDDEN` | 403 | Recurso de outro restaurante |
| `NOT_FOUND` | 404 | Recurso não encontrado |
| `VALIDATION_ERROR` | 422 | Dados de entrada inválidos |
| `AI_UNAVAILABLE` | 503 | Anthropic API indisponível |
| `RATE_LIMITED` | 429 | Limite de requisições IA atingido |

---

## Convenções de Testes

- PHPUnit para testes backend (Laravel)
- Vitest para testes React
- Toda feature spec deve ter pelo menos:
  - 1 teste de caminho feliz (happy path)
  - 1 teste de validação de input inválido
  - 1 teste de autorização (acesso negado)
- Factories do Laravel para seeds de teste
- Banco de dados de teste separado (SQLite em memória ou PostgreSQL de test)

---

## Variáveis de Ambiente Obrigatórias

```env
# App
APP_NAME=Vinia
APP_ENV=production
APP_KEY=
APP_URL=

# Banco
DB_CONNECTION=pgsql
DB_HOST=
DB_PORT=5432
DB_DATABASE=vinia
DB_USERNAME=
DB_PASSWORD=

# IA
ANTHROPIC_API_KEY=
ANTHROPIC_MODEL=claude-sonnet-4-6
ANTHROPIC_MAX_TOKENS=1000
AI_RATE_LIMIT_PER_SESSION=10

# Storage
CLOUDFLARE_R2_BUCKET=
CLOUDFLARE_R2_ENDPOINT=
CLOUDFLARE_R2_ACCESS_KEY=
CLOUDFLARE_R2_SECRET_KEY=
CLOUDFLARE_R2_PUBLIC_URL=

# Queue
QUEUE_CONNECTION=database
```

---

## Glossário de Termos do Domínio

| Termo | Definição |
|---|---|
| Restaurante | Cliente B2B da Vinia — proprietário da conta |
| Comensal | Usuário final que interage com a carta digital no tablet |
| Rótulo | Um vinho cadastrado na carta do restaurante |
| Sofia | Nome da assistente IA da Vinia |
| Sessão | Período de uso do tablet por um comensal em uma visita |
| Carta digital | Interface React exibida no tablet para o comensal |
| Backoffice | Interface web de gestão do restaurante |
| Harmonização | Combinação ideal entre vinho e prato |
| Perfil de paladar | Preferências vínicas do comensal coletadas na sessão |
