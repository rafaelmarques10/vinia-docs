# F004 — Gestão de Tablets

> Status: ready | Versão: 1.0 | Sprint: 2

## Objetivo

Permitir que o restaurante registre e gerencie os tablets que exibem a carta digital, controlando acesso via token único por dispositivo.

## Atores

- **Gerente**: cadastra e gerencia tablets
- **Tablet**: se autentica via token para acessar a API

## Pré-condições

- Restaurante ativo com gerente autenticado
- Tablet físico com browser moderno disponível

---

## Regras de Negócio

- RN01: Cada tablet possui um `token` único de 64 caracteres gerado pelo sistema
- RN02: O token é exibido uma única vez no momento do cadastro — não é recuperável, apenas regenerável
- RN03: Revogar um tablet invalida o token imediatamente — a carta digital para de funcionar naquele dispositivo
- RN04: Ao regenerar token, o token anterior é invalidado
- RN05: O número máximo de tablets ativos é definido pelo `plan` do restaurante:
  - `starter`: 1 tablet
  - `standard`: 3 tablets
  - `premium`: 6 tablets
- RN06: Tablets extras podem ser contratados com custo adicional (fora do escopo do MVP — apenas exibir mensagem)
- RN07: `last_seen_at` é atualizado a cada chamada autenticada da API do tablet
- RN08: Tablet é considerado offline se `last_seen_at` > 5 minutos atrás

## Campos

| Campo | Tipo | Obrigatório | Validação |
|---|---|---|---|
| name | string | sim | 2–100 caracteres (ex: "Mesa 1", "Entrada") |
| token | string | auto | 64 chars hex, único |
| active | boolean | sim | default true |

---

## Critérios de Aceite

### CA01 — Cadastrar tablet
```
Dado que sou gerente e tenho slot disponível no meu plano
Quando cadastro novo tablet com nome "Mesa 1"
Então o sistema gera um token único de 64 caracteres
E exibe o token em modal com QR code para configuração rápida
E alerta: "Anote o token — ele não será exibido novamente"
```

### CA02 — Parear tablet
```
Dado que tenho o token do tablet
Quando acesso {APP_URL}/tablet?token={token} no browser do tablet
Então a carta digital carrega com identidade visual do restaurante
E o tablet aparece como "Online" no backoffice
```

### CA03 — Limite de plano atingido
```
Dado que sou cliente do plano Starter (1 tablet) e já tenho 1 ativo
Quando tento cadastrar um segundo tablet
Então recebo mensagem: "Seu plano permite até 1 tablet ativo. Faça upgrade ou adicione tablet avulso."
E o cadastro é bloqueado
```

### CA04 — Revogar tablet
```
Dado que revogo o tablet "Mesa 1"
Então o token é invalidado imediatamente
E a carta digital nesse tablet exibe tela de erro: "Dispositivo não autorizado"
E no backoffice o tablet aparece como "Revogado"
```

### CA05 — Regenerar token
```
Dado que regenero o token do tablet "Mesa 1"
Então um novo token é gerado e exibido em modal
E o token anterior para de funcionar imediatamente
```

### CA06 — Status online/offline
```
Dado que o tablet fez uma chamada à API há 3 minutos
Então o backoffice exibe o tablet como "Online"
Dado que a última chamada foi há 10 minutos
Então o backoffice exibe o tablet como "Offline"
```

---

## Componentes Laravel

### Model: `Tablet`
```php
// app/Models/Tablet.php
protected $fillable = ['restaurant_id', 'name', 'token', 'active', 'last_seen_at'];
protected $hidden   = ['token'];  // nunca exposto em listagens

protected $casts = [
    'active'       => 'boolean',
    'last_seen_at' => 'datetime',
];

public function isOnline(): bool
// retorna true se last_seen_at > now() - 5min

public function restaurant(): BelongsTo
public function sessions(): HasMany
```

### Service: `TabletService`
```php
// app/Services/TabletService.php
public function create(Restaurant $restaurant, string $name): array
// retorna ['tablet' => Tablet, 'token' => string (plain)]

public function regenerateToken(Tablet $tablet): string   // retorna novo token plain
public function revoke(Tablet $tablet): void
public function canAddTablet(Restaurant $restaurant): bool
```

### Middleware: `TabletAuthentication`
```php
// app/Http/Middleware/TabletAuthentication.php
// Valida Bearer token da API, injeta tablet e restaurant no request
// Atualiza last_seen_at
// Retorna 401 se token inválido ou tablet inativo
```

### Livewire: `TabletList`
```
- Listagem com status online/offline (polling a cada 30s)
- Ação de revogar e regenerar token
- Modal com QR code ao criar/regenerar
```

---

## Testes

| ID | Tipo | Descrição |
|---|---|---|
| T004-01 | Feature | Criar tablet — token de 64 chars gerado |
| T004-02 | Feature | Limite de plano bloqueado corretamente |
| T004-03 | Middleware | Token válido — request passa com tablet injetado |
| T004-04 | Middleware | Token inválido — retorna 401 |
| T004-05 | Middleware | Tablet inativo — retorna 401 |
| T004-06 | Feature | Revogar tablet — token para de funcionar |
| T004-07 | Feature | Regenerar token — token antigo invalidado, novo funciona |
| T004-08 | Unit | `isOnline()` retorna false se last_seen_at > 5min |
| T004-09 | Middleware | `last_seen_at` atualizado a cada request autenticado |
