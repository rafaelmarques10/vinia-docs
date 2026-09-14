# F007 — IA: Comparativo entre Rótulos

> Status: ready | Versão: 1.0 | Sprint: 3

## Objetivo

Permitir que o comensal compare dois rótulos da carta via IA, recebendo análise comparativa em linguagem natural que auxilie a decisão.

## Pré-condições

- Sessão anônima ativa
- Pelo menos 2 rótulos disponíveis na carta

---

## Regras de Negócio

- RN01: O comensal seleciona exatamente 2 rótulos para comparar
- RN02: Ambos os rótulos devem estar `available = true` e pertencer ao restaurante da sessão
- RN03: O comparativo conta como 1 interação de IA para fins de rate limit (compartilha com F006)
- RN04: A IA recebe as fichas técnicas completas de ambos os rótulos
- RN05: A resposta deve estruturar claramente as diferenças sem indicar um "vencedor" absoluto — o objetivo é orientar, não substituir a escolha do comensal

## Critérios de Aceite

### CA01 — Comparativo básico
```
Dado que o comensal seleciona dois rótulos
Quando solicita a comparação
Então Sofia retorna análise cobrindo:
- Diferenças de estilo e corpo
- Perfil aromático de cada um
- Ocasiões/pratos que favorecem cada um
- Perfil de comensal ideal para cada um
Em linguagem elegante e equilibrada
```

### CA02 — Rótulo indisponível selecionado
```
Dado que um dos rótulos selecionados foi desativado entre o carregamento e a solicitação
Então a API retorna erro 422: "Um dos rótulos selecionados não está mais disponível"
E o frontend remove o rótulo da seleção e notifica o comensal
```

---

## User Prompt — Comparativo
```
O comensal quer comparar dois vinhos da carta:

Vinho A:
{wine_a_json}

Vinho B:
{wine_b_json}

Faça uma análise comparativa elegante entre os dois, destacando:
- Diferenças de estilo e corpo
- Perfil aromático
- Com quais pratos cada um harmoniza melhor
- Para qual perfil de comensal cada um é mais indicado

Não declare um vencedor — ajude o comensal a escolher com base no seu gosto e no que vai pedir.
```

## Componentes Laravel

```php
// Reutiliza AnthropicService e ProcessAiRecommendationJob
// Novo tipo na AiInteraction: type = 'compare'
// Novo método no AnthropicService:
public function buildComparePrompt(Wine $wineA, Wine $wineB): string
```

## Testes

| ID | Tipo | Descrição |
|---|---|---|
| T007-01 | Unit | `buildComparePrompt` injeta fichas de ambos os vinhos |
| T007-02 | Feature | Comparativo com 2 vinhos válidos retorna análise |
| T007-03 | Feature | Rótulo indisponível retorna 422 |
| T007-04 | Feature | Comparativo conta no rate limit da sessão |

---
---

# F008 — Sessão Anônima

> Status: ready | Versão: 1.0 | Sprint: 3

## Objetivo

Criar e gerenciar sessões anônimas dos comensais no tablet, capturando o perfil de paladar durante a navegação como base para a futura identificação portável (V2).

## Regras de Negócio

- RN01: Sessão criada automaticamente ao comensal tocar "Ver Carta"
- RN02: Identificada por UUID — nenhum dado pessoal coletado no MVP
- RN03: Sessão vinculada ao tablet e ao restaurante
- RN04: `palate_profile` (JSONB) armazena as respostas do fluxo de perfil de paladar
- RN05: Sessão encerrada (`ended_at`) ao timeout de inatividade ou ao retornar à tela de entrada
- RN06: Coluna `user_id` existe mas permanece `null` no MVP — preparada para V2
- RN07: Sessões são mantidas por 90 dias e depois arquivadas (fora do escopo do MVP)

## Estrutura do `palate_profile` (JSONB)

```json
{
  "color_preference": "tinto",
  "body_preference": "encorpado",
  "taste_preference": "seco",
  "price_range": "200-500",
  "collected_at": "2026-06-18T20:30:00Z"
}
```

## Critérios de Aceite

### CA01 — Criação automática de sessão
```
Dado que o comensal toca "Ver Carta"
Então POST /api/v1/sessions é chamado automaticamente pelo React
E uma sessão UUID é criada e armazenada no estado local do React
E o session_id é enviado em todas as chamadas de IA subsequentes
```

### CA02 — Encerramento por timeout
```
Dado que a sessão está ativa e o timeout de 3min é atingido
Quando o React retorna à tela de entrada
Então PATCH /api/v1/sessions/{id} é chamado com ended_at = now()
```

### CA03 — Perfil de paladar salvo
```
Dado que o comensal completa o fluxo de 4 perguntas
Então PATCH /api/v1/sessions/{id} atualiza palate_profile com as respostas
E o perfil é injetado nas próximas chamadas de IA da mesma sessão
```

## Componentes Laravel

### Model: `Session` (cuidado com conflito de nome — usar `ComensalSession`)
```php
// app/Models/ComensalSession.php
protected $table = 'sessions';
protected $keyType = 'string';  // UUID
public $incrementing = false;

protected $fillable = [
    'id', 'tablet_id', 'restaurant_id',
    'palate_profile', 'user_id', 'started_at', 'ended_at'
];

protected $casts = [
    'palate_profile' => 'array',
    'started_at'     => 'datetime',
    'ended_at'       => 'datetime',
];
```

### API Endpoints
```
POST  /api/v1/sessions
→ Cria sessão, retorna { session_id: uuid }

PATCH /api/v1/sessions/{id}
→ Atualiza palate_profile ou ended_at
→ Valida que session pertence ao tablet autenticado
```

## Testes

| ID | Tipo | Descrição |
|---|---|---|
| T008-01 | Feature | POST /sessions cria sessão com tablet_id correto |
| T008-02 | Feature | PATCH /sessions/{id} atualiza palate_profile |
| T008-03 | Feature | PATCH /sessions/{id} atualiza ended_at |
| T008-04 | Feature | Tablet B não acessa/atualiza sessão do Tablet A (403) |
| T008-05 | Unit | `palate_profile` persiste e retorna como array |
