# F005 — Carta Digital (Tablet)

> Status: ready | Versão: 1.0 | Sprint: 3

## Objetivo

Interface React otimizada para tablet que exibe a carta de vinhos do restaurante, permite navegação com filtros e abre o assistente Sofia para recomendações por IA.

## Atores

- **Comensal**: usuário final que interage com o tablet na mesa

## Pré-condições

- Tablet pareado com restaurante via token
- Pelo menos 1 rótulo ativo cadastrado
- Conexão com internet disponível no salão

---

## Regras de Negócio

- RN01: A carta exibe apenas rótulos com `available = true`
- RN02: Identidade visual (logo, cores) vem da API e é aplicada ao tema da interface
- RN03: Timeout de inatividade: 3 minutos sem toque retorna à tela de entrada e encerra a sessão
- RN04: A interface opera em modo fullscreen (PWA) sem barra de navegador visível
- RN05: Nenhum login é solicitado ao comensal
- RN06: Rótulos indisponíveis marcados após carregamento inicial mostram overlay "Esgotado" sem recarregar a página
- RN07: A carta atualiza disponibilidade via polling a cada 60 segundos
- RN08: Offline: exibir mensagem "Sem conexão — a carta pode estar desatualizada" e usar cache local

## Telas e Fluxo

```
[Tela de Entrada]
      ↓ toque
[Sessão criada via API]
      ↓
[Carta — Lista de Vinhos]
   ↓ filtros      ↓ card
[Resultados]   [Detalhe do Rótulo]
                    ↓
              [Assistente Sofia]
                    ↓
              [Resposta da IA]
```

---

## Critérios de Aceite

### CA01 — Tela de entrada
```
Dado que o tablet está pareado
Quando o browser carrega a URL da carta
Então exibe tela com logo do restaurante e nome
Com botão "Ver Carta" em destaque
Com cores da marca aplicadas ao tema
```

### CA02 — Listagem com filtros
```
Dado que o comensal toca em "Ver Carta"
Então vê grid de cards com todos os rótulos disponíveis
Com filtros no topo: Tipo, País, Uva, Faixa de preço
Quando aplica filtro "Tipo: Espumante"
Então apenas espumantes são exibidos
E um contador mostra "X rótulos encontrados"
```

### CA03 — Detalhe do rótulo
```
Dado que o comensal toca em um card
Então vê tela de detalhe com:
- Foto em destaque (ou placeholder elegante se sem foto)
- Nome, produtor, safra, país, região
- Tipo, uvas, teor alcoólico
- Preço em destaque
- Descrição e notas de degustação
- Harmonizações sugeridas
- Botão "Perguntar à Sofia"
```

### CA04 — Timeout de inatividade
```
Dado que o comensal não toca na tela por 3 minutos
Então aparece aviso: "Retornando à tela inicial em 30 segundos..."
Com botão "Continuar navegando"
Se o comensal não responder
Então a tela retorna à entrada e a sessão é encerrada
```

### CA05 — Rótulo esgotado após carregamento
```
Dado que a carta está carregada e o gerente desativa um rótulo no backoffice
Quando o polling de 60s atualiza os dados
Então o card do rótulo exibe overlay "Esgotado" sem recarregar a página
E o rótulo não aparece em novas buscas/filtros
```

### CA06 — Modo offline
```
Dado que a conexão é perdida durante a navegação
Então um banner sutil aparece: "Sem conexão — carta pode estar desatualizada"
E o comensal ainda consegue navegar nos dados em cache
E o assistente Sofia exibe: "Assistente indisponível sem conexão"
```

---

## Componentes React

### Estrutura de páginas
```
src/
├── pages/
│   ├── EntryPage.tsx         ← tela de entrada com logo e botão
│   ├── WineListPage.tsx      ← lista com filtros
│   ├── WineDetailPage.tsx    ← detalhe do rótulo
│   └── AssistantPage.tsx     ← interface do chat com Sofia
│
├── components/
│   ├── WineCard.tsx          ← card do rótulo na listagem
│   ├── WineFilters.tsx       ← barra de filtros
│   ├── SoldOutOverlay.tsx    ← overlay de esgotado
│   ├── InactivityTimer.tsx   ← lógica de timeout
│   ├── OfflineBanner.tsx     ← banner de sem conexão
│   └── ThemeProvider.tsx     ← aplica cores do restaurante via CSS vars
│
├── hooks/
│   ├── useRestaurant.ts      ← dados do restaurante (React Query)
│   ├── useWines.ts           ← listagem + filtros (React Query)
│   ├── useInactivity.ts      ← timer de inatividade
│   └── useSession.ts         ← criação e gestão da sessão anônima
│
└── services/
    └── api.ts                ← cliente HTTP com token do tablet
```

### Gerenciamento de tema
```typescript
// ThemeProvider aplica as cores do restaurante como CSS custom properties
document.documentElement.style.setProperty('--color-primary', restaurant.primary_color);
document.documentElement.style.setProperty('--color-secondary', restaurant.secondary_color);
```

### Cache e polling
```typescript
// useWines.ts — React Query com polling
useQuery({
  queryKey: ['wines', restaurantId, filters],
  queryFn: () => api.getWines(filters),
  staleTime: 60_000,      // 60 segundos
  refetchInterval: 60_000 // polling automático
})
```

---

## Design / UX

- Layout landscape otimizado para tablets 10–12"
- Fonte mínima: 16px para legibilidade em ambiente de restaurante (luz baixa)
- Touch targets mínimos: 48x48px
- Cards com foto 16:9, informações em tipografia hierárquica clara
- Animações suaves (200ms) para transições entre telas
- Placeholder de foto: ícone de taça sobre fundo com cor secundária do restaurante
- Modo escuro suave por padrão (ambiente de restaurante fino)

---

## Testes

| ID | Tipo | Descrição |
|---|---|---|
| T005-01 | E2E | Token válido carrega tela de entrada com logo |
| T005-02 | E2E | Filtro por tipo retorna apenas rótulos do tipo |
| T005-03 | E2E | Toque no card abre detalhe com todos os campos |
| T005-04 | Component | InactivityTimer dispara após 3min sem toque |
| T005-05 | Component | SoldOutOverlay aparece quando available = false |
| T005-06 | Hook | useWines refetch a cada 60s atualiza dados |
| T005-07 | Component | OfflineBanner aparece quando navigator.onLine = false |
| T005-08 | E2E | ThemeProvider aplica cores do restaurante corretamente |
