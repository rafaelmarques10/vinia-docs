# Epic 3: Tablets & API REST

**Status:** Ready
**Sprint:** 2 (Semanas 4–5)
**Objetivo:** Gestão de tablets no backoffice, endpoints da API REST para a carta digital e criação de sessões anônimas dos comensais.

## Stories

| Story | Título | Pontos | Feature |
|---|---|---|---|
| 3.1 | F004 — Gestão de Tablets | 5 | F004 |
| 3.2 | API REST — Carta Digital | 5 | F002/F005 |
| 3.3 | F008 — Sessão Anônima | 3 | F008 |

## Critério de Conclusão do Epic

- Gerente pode cadastrar tablets com limite por plano
- Token gerado e exibido em modal/QR code
- Middleware `TabletAuthentication` valida todas as rotas do tablet
- GET /api/v1/wines retorna rótulos filtrados e paginados
- POST/PATCH /api/v1/sessions cria e encerra sessão anônima
