# Epic 5: Carta Digital React (Tablet)

**Status:** Ready
**Sprint:** 3 (Semanas 8–9)
**Objetivo:** Construir a interface React que o comensal usa no tablet — PWA em modo quiosque, navegação completa da carta com filtros, detalhe de rótulo e assistente Sofia integrado.

## Stories

| Story | Título | Pontos | Feature |
|---|---|---|---|
| 5.1 | Setup React + Vite + PWA + ThemeProvider | 5 | F005 base |
| 5.2 | F005 — Listagem, Filtros e Detalhe de Rótulo | 8 | F005 |
| 5.3 | F005 — Assistente Sofia (UI + integração IA) | 8 | F005/F006/F007 |

## Critério de Conclusão do Epic

- PWA em modo fullscreen sem barra de navegador
- Cores do restaurante aplicadas via CSS custom properties
- Listagem com filtros (tipo, país, uva, preço) e polling 60s
- Detalhe do rótulo com foto, ficha técnica e botão "Perguntar à Sofia"
- Fluxo completo do assistente: prato → recomendação | perfil → recomendação | comparativo
- Timeout de 3 minutos com aviso e encerramento de sessão
- Banner offline e navegação em cache
