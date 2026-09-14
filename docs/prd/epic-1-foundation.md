# Epic 1: Foundation & Infraestrutura

**Status:** Ready
**Sprint:** 1 (Semanas 1–2)
**Objetivo:** Criar a base técnica do projeto — aplicação Laravel configurada, banco de dados estruturado e autenticação funcionando. Nenhuma feature de negócio, apenas a fundação sobre a qual tudo será construído.

## Stories

| Story | Título | Pontos |
|---|---|---|
| 1.1 | Setup Laravel 11 + PostgreSQL + Autenticação | 5 |
| 1.2 | Migrations — Estrutura Completa do Banco | 3 |
| 1.3 | Models Eloquent + Relações Base | 3 |

## Critério de Conclusão do Epic

- Laravel 11 rodando localmente e no Railway (staging)
- Todas as migrations executadas sem erro
- Login/logout funcionando no backoffice
- Usuário admin Vinia criado via seeder
- `php artisan test` passando com suite básica
