# Epic 4: Sofia IA — Recomendações

**Status:** Ready
**Sprint:** 3 (Semanas 6–7)
**Objetivo:** Integrar a Anthropic API como motor de IA assíncrono via Laravel Jobs, implementar os 3 tipos de recomendação da Sofia: por prato, por perfil de paladar e comparativo entre rótulos.

## Stories

| Story | Título | Pontos | Feature |
|---|---|---|---|
| 4.1 | AnthropicService + Job Base (Infraestrutura IA) | 5 | F006 base |
| 4.2 | F006 — IA Recomendação (Prato + Perfil) | 8 | F006 |
| 4.3 | F007 — IA Comparativo entre Rótulos | 5 | F007 |

## Critério de Conclusão do Epic

- `AnthropicService` chama API com timeout 30s e trata erros
- `ProcessAiRecommendationJob` persiste resultado em `ai_interactions`
- Rate limit de 10 interações por sessão funcionando
- Recomendação por prato retorna 2–3 vinhos da carta com justificativa
- Recomendação por perfil respeita as 4 perguntas do fluxo
- Comparativo gera análise sem declarar "vencedor"
- Sofia nunca menciona Anthropic, Claude ou tecnologia subjacente
