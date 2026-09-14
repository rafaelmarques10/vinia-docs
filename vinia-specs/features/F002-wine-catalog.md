# F002 — Catálogo de Vinhos

> Status: ready | Versão: 1.0 | Sprint: 1

## Objetivo

Permitir que o restaurante gerencie os rótulos da sua carta de vinhos — cadastro, edição, upload de foto e controle de disponibilidade em tempo real.

## Atores

- **Gerente**: cadastra e gerencia os rótulos
- **Comensal**: visualiza os rótulos disponíveis na carta digital

## Pré-condições

- Restaurante ativo com gerente autenticado

---

## Regras de Negócio

- RN01: Cada rótulo pertence a exatamente um restaurante
- RN02: Um rótulo pode ter uma ou mais uvas (relação N:N via tabela `grape_wine`)
- RN03: Foto armazenada no R2 no path `restaurants/{restaurant_id}/wines/{wine_id}.{ext}`
- RN04: Foto deve ser PNG ou JPG com tamanho máximo de 5MB
- RN05: `available: false` oculta o rótulo na carta digital imediatamente (sem cache)
- RN06: Preço deve ser maior que zero
- RN07: Safra (`vintage`) deve ser entre 1900 e o ano atual
- RN08: Ao excluir um rótulo, remover a foto do R2
- RN09: Rótulos são listados na carta digital ordenados por tipo → país → nome, salvo filtros aplicados pelo comensal
- RN10: Gerente só acessa rótulos do próprio restaurante

## Campos

| Campo | Tipo | Obrigatório | Validação |
|---|---|---|---|
| name | string | sim | 2–255 caracteres |
| producer | string | sim | 2–255 caracteres |
| vintage | integer | não | 1900–ano atual |
| country | string | sim | 2–100 caracteres |
| region | string | não | max 255 caracteres |
| type | enum | sim | tinto, branco, rosé, espumante, sobremesa, fortificado |
| alcohol | decimal | não | 0.1–99.9 |
| price | decimal | sim | > 0, max 99999.99 |
| description | text | não | max 2000 caracteres |
| tasting_notes | text | não | max 2000 caracteres |
| pairings | text | não | max 1000 caracteres |
| photo | file | não | PNG/JPG, max 5MB |
| available | boolean | sim | default true |
| grapes | array | não | lista de nomes de uvas |

---

## Critérios de Aceite

### CA01 — Cadastro de rótulo
```
Dado que sou gerente autenticado
Quando preencho o formulário com dados válidos e salvo
Então o rótulo é criado com restaurant_id do meu restaurante
E aparece na listagem do backoffice
E aparece na carta digital se available = true
```

### CA02 — Upload de foto
```
Dado que faço upload de JPG de 2MB ao criar/editar rótulo
Então a foto é salva no R2
E a URL é armazenada em wines.photo_url
E a foto aparece no card da carta digital
```

### CA03 — Desativar rótulo
```
Dado que o rótulo "Château Pichon Baron 2018" está available = true
Quando altero para available = false
Então o rótulo deixa de aparecer na carta digital imediatamente
E no backoffice aparece marcado como "Indisponível"
```

### CA04 — Validação de campos obrigatórios
```
Dado que submeto o formulário sem preencher "name"
Então recebo erro: "O nome do rótulo é obrigatório"
E o rótulo não é criado
```

### CA05 — Múltiplas uvas
```
Dado que cadastro um vinho com uvas ["Cabernet Sauvignon", "Merlot"]
Então são criados/reutilizados registros na tabela grapes
E as relações são criadas em grape_wine
E ao detalhar o rótulo na carta digital, as duas uvas aparecem
```

### CA06 — Exclusão com limpeza de storage
```
Dado que o rótulo possui foto no R2
Quando o gerente exclui o rótulo
Então o registro é removido do banco
E a foto é deletada do R2
E o rótulo some da carta digital
```

---

## Componentes Laravel

### Model: `Wine`
```php
// app/Models/Wine.php
protected $fillable = [
    'restaurant_id', 'name', 'producer', 'vintage', 'country',
    'region', 'type', 'alcohol', 'price', 'description',
    'tasting_notes', 'pairings', 'photo_url', 'available'
];

protected $casts = [
    'available' => 'boolean',
    'price'     => 'decimal:2',
    'alcohol'   => 'decimal:1',
];

public function grapes(): BelongsToMany  // via grape_wine
public function restaurant(): BelongsTo
```

### Model: `Grape`
```php
// app/Models/Grape.php
protected $fillable = ['name'];
public function wines(): BelongsToMany
```

### Service: `WineService`
```php
// app/Services/WineService.php
public function create(Restaurant $restaurant, array $data): Wine
public function update(Wine $wine, array $data): Wine
public function delete(Wine $wine): void          // deleta foto do R2
public function uploadPhoto(Wine $wine, UploadedFile $file): string
public function syncGrapes(Wine $wine, array $grapeNames): void
public function toggleAvailability(Wine $wine): Wine
```

### Livewire: `WineForm`
```
- Formulário com validação inline
- Upload de foto com preview
- Campo de uvas com autocomplete (busca nas uvas já cadastradas)
- Toggle de disponibilidade com feedback imediato
```

### Livewire: `WineList`
```
- Tabela paginada (20 por página)
- Filtro por tipo e disponibilidade
- Busca por nome ou produtor
- Ação rápida de toggle disponibilidade sem abrir formulário
```

---

## Testes

| ID | Tipo | Descrição |
|---|---|---|
| T002-01 | Feature | Criar rótulo com dados válidos — persiste no banco |
| T002-02 | Feature | Upload de foto válida — salva no R2, URL atualizada |
| T002-03 | Feature | Upload de arquivo inválido — retorna erro |
| T002-04 | Feature | Preço negativo — retorna erro de validação |
| T002-05 | Feature | Toggle available false — rótulo some da API de carta |
| T002-06 | Feature | Múltiplas uvas — relações criadas corretamente em grape_wine |
| T002-07 | Feature | Exclusão — foto removida do R2 |
| T002-08 | Feature | Gerente não acessa rótulos de outro restaurante |
| T002-09 | Unit | `syncGrapes` reutiliza uva existente em vez de duplicar |
