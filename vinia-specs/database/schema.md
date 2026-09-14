# Database — Schema e Migrations

> Status: ready | Versão: 1.0

## Diagrama ERD

```
restaurants
    │ 1
    ├──── N ── users
    ├──── N ── wines
    │              │ N
    │              └──── N ── grapes  (via grape_wine)
    ├──── N ── tablets
    │              │ 1
    │              └──── N ── comensal_sessions
    │                              │ 1
    │                              └──── N ── ai_interactions
    └──── N ── comensal_sessions (restaurant_id direto)
```

---

## M001 — create_restaurants_table

```php
Schema::create('restaurants', function (Blueprint $table) {
    $table->id();
    $table->string('name');
    $table->string('slug')->unique();
    $table->string('cnpj', 18)->nullable();
    $table->text('logo_url')->nullable();
    $table->string('primary_color', 7)->default('#7B2D8B');
    $table->string('secondary_color', 7)->default('#C0392B');
    $table->boolean('active')->default(true);
    $table->string('plan', 50)->default('starter');
    // plan: starter | standard | premium
    $table->timestamps();

    $table->index('slug');
    $table->index('active');
});
```

---

## M002 — create_users_table

```php
Schema::create('users', function (Blueprint $table) {
    $table->id();
    $table->foreignId('restaurant_id')->constrained()->cascadeOnDelete();
    $table->string('name');
    $table->string('email')->unique();
    $table->string('password');
    $table->string('role', 50)->default('manager');
    // role: admin (Vinia) | manager (restaurante)
    $table->timestamp('email_verified_at')->nullable();
    $table->rememberToken();
    $table->timestamps();

    $table->index('restaurant_id');
    $table->index('email');
});
```

---

## M003 — create_wines_table

```php
Schema::create('wines', function (Blueprint $table) {
    $table->id();
    $table->foreignId('restaurant_id')->constrained()->cascadeOnDelete();
    $table->string('name');
    $table->string('producer');
    $table->smallInteger('vintage')->nullable();
    $table->string('country', 100);
    $table->string('region')->nullable();
    $table->string('type', 50);
    // type: tinto | branco | rosé | espumante | sobremesa | fortificado
    $table->decimal('alcohol', 4, 1)->nullable();
    $table->decimal('price', 10, 2);
    $table->text('description')->nullable();
    $table->text('tasting_notes')->nullable();
    $table->text('pairings')->nullable();
    $table->text('photo_url')->nullable();
    $table->boolean('available')->default(true);
    $table->timestamps();
    $table->softDeletes();  // para recuperação em caso de exclusão acidental

    $table->index('restaurant_id');
    $table->index(['restaurant_id', 'available']);
    $table->index(['restaurant_id', 'type']);
    $table->index(['restaurant_id', 'country']);
});
```

---

## M004 — create_grapes_table

```php
Schema::create('grapes', function (Blueprint $table) {
    $table->id();
    $table->string('name', 100)->unique();
    $table->timestamps();
});

Schema::create('grape_wine', function (Blueprint $table) {
    $table->foreignId('wine_id')->constrained()->cascadeOnDelete();
    $table->foreignId('grape_id')->constrained()->cascadeOnDelete();
    $table->smallInteger('percentage')->nullable();
    // percentual no blend — opcional

    $table->primary(['wine_id', 'grape_id']);
});
```

---

## M005 — create_tablets_table

```php
Schema::create('tablets', function (Blueprint $table) {
    $table->id();
    $table->foreignId('restaurant_id')->constrained()->cascadeOnDelete();
    $table->string('name', 100);
    $table->string('token', 64)->unique();
    $table->boolean('active')->default(true);
    $table->timestamp('last_seen_at')->nullable();
    $table->timestamps();

    $table->index('restaurant_id');
    $table->index('token');  // lookup frequente na autenticação
    $table->index(['restaurant_id', 'active']);
});
```

---

## M006 — create_sessions_table

```php
Schema::create('sessions', function (Blueprint $table) {
    $table->uuid('id')->primary();
    $table->foreignId('tablet_id')->constrained()->cascadeOnDelete();
    $table->foreignId('restaurant_id')->constrained()->cascadeOnDelete();
    $table->jsonb('palate_profile')->nullable();
    $table->foreignId('user_id')->nullable()->constrained()->nullOnDelete();
    // user_id: null no MVP, populado na V2 com identificação do comensal
    $table->timestamp('started_at')->useCurrent();
    $table->timestamp('ended_at')->nullable();
    $table->timestamps();

    $table->index('tablet_id');
    $table->index('restaurant_id');
    $table->index('started_at');
    $table->index('user_id');
    // GIN index para consultas JSONB (V2)
    // DB::statement('CREATE INDEX sessions_palate_profile_gin ON sessions USING GIN (palate_profile)');
});
```

> **Nota**: A tabela se chama `sessions` no banco, mas o Model Laravel se chama `ComensalSession` para evitar conflito com a classe nativa `Session` do Laravel.

---

## M007 — create_ai_interactions_table

```php
Schema::create('ai_interactions', function (Blueprint $table) {
    $table->id();
    $table->uuid('session_id');
    $table->foreign('session_id')->references('id')->on('sessions')->cascadeOnDelete();
    $table->string('type', 50);
    // type: recommend_dish | recommend_palate | compare
    $table->text('input');
    $table->text('prompt_sent');
    $table->text('response')->nullable();
    $table->integer('tokens_used')->nullable();
    $table->string('status', 20)->default('pending');
    // status: pending | processing | done | failed
    $table->timestamps();

    $table->index('session_id');
    $table->index('status');
    $table->index('created_at');
});
```

---

## Observações Gerais

- **Encoding**: UTF-8 em todas as tabelas (`utf8mb4` no MySQL; padrão no PostgreSQL)
- **Timezone**: armazenar timestamps em UTC — conversão para fuso do restaurante no frontend
- **Soft deletes**: apenas em `wines` no MVP — restaurantes e tablets usam `active` flag
- **UUID vs BIGINT**: `sessions` usa UUID para dificultar enumeração no polling do frontend; demais tabelas usam BIGINT auto-increment
- **JSONB**: `palate_profile` usa JSONB (não JSON) para suportar índice GIN futuro (V2)
