# Epic 2: Backoffice — Restaurante & Vinhos

**Status:** Ready
**Sprint:** 1–2 (Semanas 2–4)
**Objetivo:** Implementar o backoffice completo para gestão do restaurante — configurações, catálogo de vinhos (CRUD + upload) e importação via planilha.

## Stories

| Story | Título | Pontos | Feature |
|---|---|---|---|
| 2.1 | F001 — Gestão do Restaurante | 5 | F001 |
| 2.2 | F002 — Catálogo de Vinhos (CRUD + Fotos) | 8 | F002 |
| 2.3 | F003 — Importação de Vinhos via Planilha | 8 | F003 |

## Critério de Conclusão do Epic

- Gerente pode configurar restaurante (nome, logo, cores) via Livewire
- Gerente pode criar, editar, desativar e excluir rótulos
- Upload de fotos funcional no Cloudflare R2
- Importação assíncrona (.xlsx/.csv) com relatório de erros
- Multi-tenancy: gerente só acessa dados do próprio restaurante
