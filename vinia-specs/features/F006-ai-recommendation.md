# F006 — IA de Recomendação (Assistente Sofia)

> Status: ready | Versão: 1.0 | Sprint: 3

## Objetivo

Oferecer ao comensal uma experiência de sommelier virtual via IA, com recomendações personalizadas por prato (harmonização) ou por perfil de paladar, usando os vinhos disponíveis na carta do restaurante.

## Atores

- **Comensal**: interage com Sofia via interface conversacional
- **Sofia**: assistente IA da Vinia (Anthropic claude-sonnet-4-6)

## Pré-condições

- Sessão anônima ativa (criada via F008)
- Pelo menos 2 rótulos disponíveis na carta
- Anthropic API acessível

---

## Regras de Negócio

- RN01: A IA recebe apenas os vinhos **disponíveis** (`available = true`) do restaurante
- RN02: A IA não deve recomendar rótulos que não estejam na carta — instrução explícita no system prompt
- RN03: Chamadas à IA são assíncronas via Laravel Job — o frontend faz polling
- RN04: Limite de 10 interações de IA por sessão (rate limiting por session_id)
- RN05: Toda interação é persistida em `ai_interactions` com input, prompt completo, resposta e tokens usados
- RN06: Se a Anthropic API estiver indisponível, retornar erro amigável ao comensal
- RN07: Timeout da chamada à IA: 30 segundos — se exceder, retornar erro
- RN08: O nome da IA é sempre **Sofia** — nunca "Claude" ou "Anthropic"
- RN09: Tom das respostas: elegante, sofisticado, acessível, em português brasileiro

## Tipos de Recomendação

### Tipo 1 — Por Prato (Harmonização)
- Input: texto livre com o prato que o comensal irá consumir
- Output: 2–3 sugestões ranqueadas com justificativa de harmonização

### Tipo 2 — Por Perfil de Paladar
- Input: respostas a 4 perguntas guiadas pela interface
- Output: recomendação personalizada com explicação do match

---

## Perguntas do Perfil de Paladar

```
P1: "Qual é a sua preferência de cor?"
    [Tinto] [Branco] [Rosé] [Espumante] [Surpreenda-me]

P2: "Como você gosta do vinho?"
    [Leve e delicado] [Médio e equilibrado] [Encorpado e intenso]

P3: "Qual perfil você prefere?"
    [Seco e mineral] [Frutado e aromático] [Doce ou suave]

P4: "Qual faixa de preço?"
    [Até R$ 200] [R$ 200–500] [R$ 500–1.000] [Acima de R$ 1.000]
```

---

## Critérios de Aceite

### CA01 — Recomendação por prato
```
Dado que o comensal informa "Vou pedir um filé ao molho de cogumelos"
Quando Sofia processa a solicitação
Então retorna 2–3 vinhos da carta com:
- Nome e safra do rótulo
- Justificativa de harmonização em linguagem elegante
- Indicação de preço
Tudo baseado apenas nos vinhos disponíveis na carta
```

### CA02 — Recomendação por paladar
```
Dado que o comensal responde: Tinto / Encorpado / Seco / R$ 200–500
Quando Sofia processa o perfil
Então retorna recomendação personalizada com explicação do match
```

### CA03 — Sem vinhos compatíveis
```
Dado que o comensal pede harmonização para "sashimi de atum"
E a carta possui apenas vinhos tintos encorpados
Então Sofia responde honestamente que a carta atual tem opções limitadas
E sugere a melhor alternativa disponível com justificativa
```

### CA04 — Rate limit atingido
```
Dado que o comensal realizou 10 interações na sessão atual
Quando tenta fazer a 11ª
Então recebe: "Você atingiu o limite de consultas desta sessão. Chame o nosso sommelier para mais orientações."
```

### CA05 — IA indisponível
```
Dado que a Anthropic API retorna erro 503
Então Sofia responde: "Desculpe, estou temporariamente indisponível. Por favor, chame nosso sommelier."
E o erro é registrado em log sem expor detalhes técnicos ao comensal
```

### CA06 — Identidade preservada
```
Dado que o comensal pergunta "Você é o ChatGPT?"
Então Sofia responde que é a sommelier virtual da Vinia
Sem mencionar Anthropic, Claude ou qualquer modelo de IA subjacente
```

---

## Prompts

### System Prompt — Base
```
Você é Sofia, a sommelier virtual do restaurante {restaurant_name}.

Regras absolutas:
- Recomende APENAS vinhos da carta fornecida abaixo. Nunca invente rótulos.
- Responda sempre em português brasileiro com tom elegante, sofisticado e acessível.
- Seja concisa mas completa — o comensal está em um ambiente de jantar.
- Nunca mencione Anthropic, Claude ou qualquer tecnologia de IA subjacente.
- Se perguntarem sobre sua identidade, diga que é a sommelier virtual da Vinia.

Carta de vinhos disponível:
{wines_json}
```

### User Prompt — Por Prato
```
O comensal informou que irá pedir: "{dish}"

Recomende 2 a 3 vinhos da carta que harmonizem bem com este prato.
Para cada vinho, explique brevemente por que é uma boa escolha.
Formate a resposta de forma clara e elegante.
```

### User Prompt — Por Paladar
```
Perfil de paladar do comensal:
- Cor preferida: {color_preference}
- Corpo: {body_preference}
- Perfil: {taste_preference}
- Faixa de preço: {price_range}

Com base neste perfil, recomende o(s) vinho(s) mais adequado(s) da carta.
Explique por que é uma boa escolha para este perfil.
```

### Estrutura do `wines_json` injetado no prompt
```json
[
  {
    "id": 42,
    "name": "Château Pichon Baron",
    "producer": "Château Pichon Baron",
    "vintage": 2018,
    "country": "França",
    "region": "Pauillac, Bordeaux",
    "type": "tinto",
    "grapes": ["Cabernet Sauvignon", "Merlot"],
    "alcohol": 13.5,
    "price": 1250.00,
    "tasting_notes": "Notas de cassis, cedro e especiarias...",
    "pairings": "Carnes vermelhas, cordeiro, caça"
  }
]
```

---

## Componentes Laravel

### Job: `ProcessAiRecommendationJob`
```php
// app/Jobs/ProcessAiRecommendationJob.php
public function __construct(
    private AiInteraction $interaction  // criada antes de disparar o job
)

public function handle(AnthropicService $service): void
// 1. Busca vinhos disponíveis do restaurante
// 2. Monta prompt (system + user)
// 3. Chama Anthropic API
// 4. Atualiza AiInteraction com resposta e tokens_used
// 5. Em caso de erro, marca interaction como failed
```

### Service: `AnthropicService`
```php
// app/Services/AnthropicService.php
public function complete(string $systemPrompt, string $userPrompt): AnthropicResponse
// Chama api.anthropic.com/v1/messages
// Timeout: 30s
// Model: config('services.anthropic.model')
// Max tokens: 1000

public function buildWinesJson(Collection $wines): string
public function buildSystemPrompt(Restaurant $restaurant): string
public function buildDishPrompt(string $dish): string
public function buildPalatePrompt(array $palateProfile): string
```

### Model: `AiInteraction`
```php
// app/Models/AiInteraction.php
protected $fillable = [
    'session_id', 'type', 'input', 'prompt_sent',
    'response', 'tokens_used', 'status'
];

// status: pending | processing | done | failed
```

### API Endpoint (polling)
```
POST /api/v1/ai/recommend
→ Cria AiInteraction (status: pending)
→ Dispara ProcessAiRecommendationJob
→ Retorna { interaction_id: uuid }

GET /api/v1/ai/interactions/{id}
→ Retorna { status, response } 
→ Frontend faz polling a cada 1,5s até status = done ou failed
```

---

## Testes

| ID | Tipo | Descrição |
|---|---|---|
| T006-01 | Unit | `buildWinesJson` serializa corretamente campos esperados |
| T006-02 | Unit | `buildSystemPrompt` injeta nome do restaurante e wines_json |
| T006-03 | Job | Job atualiza AiInteraction com resposta quando API responde |
| T006-04 | Job | Job marca status = failed quando API retorna 503 |
| T006-05 | Job | Job respeita timeout de 30s |
| T006-06 | Feature | Rate limit bloqueia 11ª interação na mesma sessão |
| T006-07 | Feature | POST /ai/recommend retorna interaction_id imediatamente |
| T006-08 | Feature | GET /ai/interactions/{id} retorna status e response |
| T006-09 | Feature | Resposta da IA só menciona vinhos da carta do restaurante |
