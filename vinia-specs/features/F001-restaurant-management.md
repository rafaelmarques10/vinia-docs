# F001 — Gestão do Restaurante

> Status: ready | Versão: 1.0 | Sprint: 1

## Objetivo

Permitir que o proprietário ou administrador configure os dados do restaurante no backoffice, incluindo identidade visual que será aplicada à carta digital.

## Atores

- **Admin Vinia**: Rafael (superadmin da plataforma)
- **Gerente**: usuário do restaurante com acesso ao backoffice

## Pré-condições

- Restaurante criado pelo Admin Vinia
- Usuário gerente vinculado ao restaurante

---

## Regras de Negócio

- RN01: Cada restaurante possui um `slug` único gerado automaticamente a partir do nome (lowercase, sem acentos, hífens no lugar de espaços)
- RN02: O `slug` pode ser editado manualmente, mas deve permanecer único na plataforma
- RN03: Logo deve ser imagem PNG ou JPG com tamanho máximo de 2MB
- RN04: Logo é armazenada no Cloudflare R2 no path `restaurants/{restaurant_id}/logo.{ext}`
- RN05: `primary_color` e `secondary_color` devem ser hexadecimais válidos no formato `#RRGGBB`
- RN06: Ao desativar um restaurante (`active: false`), todos os seus tablets deixam de servir a carta digital imediatamente
- RN07: Um gerente só pode editar o restaurante ao qual está vinculado

## Campos

| Campo | Tipo | Obrigatório | Validação |
|---|---|---|---|
| name | string | sim | 2–255 caracteres |
| slug | string | sim (auto) | único, lowercase, sem espaços |
| cnpj | string | não | formato XX.XXX.XXX/XXXX-XX, válido |
| logo | file | não | PNG/JPG, max 2MB |
| primary_color | string | não | hex válido (#RRGGBB), default #7B2D8B |
| secondary_color | string | não | hex válido (#RRGGBB), default #C0392B |
| active | boolean | sim | default true |
| plan | enum | sim | starter, standard, premium |

---

## Critérios de Aceite

### CA01 — Editar dados básicos
```
Dado que sou gerente autenticado
Quando acesso Configurações > Restaurante
Então vejo formulário preenchido com dados atuais
Quando altero o nome e salvo
Então os dados são atualizados e o slug é recalculado automaticamente
E uma mensagem de sucesso é exibida
```

### CA02 — Upload de logo
```
Dado que sou gerente autenticado
Quando faço upload de uma imagem PNG de 500KB
Então a logo é salva no R2 e a URL é atualizada no registro
E a logo aparece imediatamente no backoffice
E a logo aparece na tela de entrada da carta digital
```

### CA03 — Upload inválido
```
Dado que faço upload de um arquivo PDF
Então recebo erro: "Formato inválido. Envie PNG ou JPG."
E o upload é rejeitado sem alterar a logo atual
```

### CA04 — Cores da marca
```
Dado que altero primary_color para #1A2B3C
Quando salvo e acesso a carta digital no tablet
Então a interface exibe a nova cor primária
```

### CA05 — Acesso negado entre restaurantes
```
Dado que sou gerente do Restaurante A
Quando tento acessar /backoffice/restaurants/{id_restaurante_B}
Então recebo HTTP 403
```

---

## Componentes Laravel

### Model: `Restaurant`
```php
// app/Models/Restaurant.php
protected $fillable = [
    'name', 'slug', 'cnpj', 'logo_url',
    'primary_color', 'secondary_color', 'active', 'plan'
];

protected $casts = [
    'active' => 'boolean',
];

// Relacionamentos
public function users(): HasMany
public function wines(): HasMany
public function tablets(): HasMany
```

### Service: `RestaurantService`
```php
// app/Services/RestaurantService.php
public function update(Restaurant $restaurant, array $data): Restaurant
public function uploadLogo(Restaurant $restaurant, UploadedFile $file): string
public function generateSlug(string $name): string
```

### Livewire Component: `RestaurantSettings`
```
// app/Livewire/RestaurantSettings.php
- Formulário reativo com validação inline
- Upload de logo com preview imediato
- Seletor de cor com input hex + preview visual
```

### Policy: `RestaurantPolicy`
```php
// app/Policies/RestaurantPolicy.php
public function update(User $user, Restaurant $restaurant): bool
// retorna true apenas se $user->restaurant_id === $restaurant->id
```

---

## Testes

| ID | Tipo | Descrição |
|---|---|---|
| T001-01 | Feature | Gerente atualiza nome do restaurante com sucesso |
| T001-02 | Feature | Upload de logo PNG válida salva no R2 e atualiza URL |
| T001-03 | Feature | Upload de arquivo inválido retorna erro de validação |
| T001-04 | Feature | Cor hex inválida retorna erro de validação |
| T001-05 | Unit | `generateSlug` converte "Café São João" em "cafe-sao-joao" |
| T001-06 | Feature | Gerente não acessa restaurante de terceiro (403) |
