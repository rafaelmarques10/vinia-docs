# Vinia — Spec-Driven Development

> Versão: 1.0 | Status: MVP | Atualizado: Junho 2026

## O que é Spec-Driven Development

Spec-Driven Development (SDD) é a prática de escrever especificações precisas e executáveis **antes** do código. Cada feature, endpoint, tabela e comportamento de IA é descrito em um arquivo de spec que serve como:

- Contrato entre produto e engenharia
- Base para geração de código (via IA ou manual)
- Critério de aceite para testes
- Documentação viva do sistema

## Estrutura do Repositório de Specs

```
vinia-specs/
├── README.md                        ← este arquivo
├── CONVENTIONS.md                   ← convenções globais do projeto
│
├── features/                        ← specs funcionais por feature
│   ├── F001-restaurant-management.md
│   ├── F002-wine-catalog.md
│   ├── F003-wine-import.md
│   ├── F004-tablet-management.md
│   ├── F005-digital-menu.md
│   ├── F006-ai-recommendation.md
│   ├── F007-ai-compare.md
│   └── F008-anonymous-session.md
│
├── api/                             ← contratos de API REST
│   ├── openapi.yaml                 ← spec OpenAPI 3.1 completa
│   └── endpoints/
│       ├── restaurant.md
│       ├── wines.md
│       └── ai.md
│
├── database/                        ← especificações de banco de dados
│   ├── schema.md                    ← ERD e decisões de modelagem
│   └── migrations/
│       ├── M001-create-restaurants.md
│       ├── M002-create-users.md
│       ├── M003-create-wines.md
│       ├── M004-create-grapes.md
│       ├── M005-create-tablets.md
│       └── M006-create-sessions.md
│
├── ai/                              ← especificações de IA e prompts
│   ├── PROMPTS.md                   ← biblioteca de prompts da Sofia
│   └── behaviors.md                 ← comportamentos esperados da IA
│
└── infra/                           ← especificações de infraestrutura
    ├── environment.md               ← variáveis de ambiente
    └── deployment.md                ← pipeline de deploy
```

## Como usar estas specs

### Fluxo de desenvolvimento

```
1. Spec escrita e revisada
        ↓
2. Código gerado/escrito com base na spec
        ↓
3. Testes escritos validando os critérios de aceite da spec
        ↓
4. PR só é aceito se todos os critérios da spec passarem
```

### Ordem recomendada de implementação

1. `database/migrations/` → criar estrutura de dados
2. `features/F001` e `F002` → backoffice base
3. `api/openapi.yaml` → contrato da API
4. `features/F005` → carta digital
5. `ai/PROMPTS.md` → integração IA
6. `features/F006` e `F007` → fluxos de IA
7. `features/F008` → sessões

## Convenções de Status

| Status | Significado |
|---|---|
| `draft` | Em elaboração — não usar para desenvolvimento |
| `ready` | Aprovada — pode ser implementada |
| `in-progress` | Em implementação |
| `done` | Implementada e testada |
| `deprecated` | Substituída por outra spec |
