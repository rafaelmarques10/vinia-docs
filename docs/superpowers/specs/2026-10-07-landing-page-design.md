# Landing page pública do Vinia — Spec de design

> Status: **rascunho v0.1 para revisão** | Data: 2026-10-07 | Caminho: arquitetural (enxuto)
> Código: `vinia-src/backend` (Laravel). Esta spec **não altera** nenhuma spec existente (F001–F008); cria uma superfície nova.

---

## 1. Objetivo e sucesso

**Objetivo:** apresentar o Vinia a **donos e gerentes de restaurantes** e levá-los a **pedir uma demonstração** por um formulário.

**Sucesso (critérios verificáveis):**
1. `https://vinia.ia.br/` mostra a landing (hoje redireciona para o login).
2. Um visitante envia o formulário e o pedido **fica gravado no banco** mesmo que o envio de e-mail falhe.
3. Um e-mail de aviso chega a `DEMO_NOTIFY_TO` a cada pedido (quando o SMTP estiver configurado).
4. O Rafael (perfil `admin`) vê e gerencia os pedidos em `/backoffice/demonstracoes`; qualquer outro perfil **não** acessa.
5. Todo texto de produto na página tem **origem rastreável** nas specs (seção 4). Nenhum número, depoimento, cliente ou preço inventado.

**Fora de escopo:** analytics, CAPTCHA, preços e planos, depoimentos, outros idiomas, blog, A/B test, integração com CRM, painel de métricas.

## 2. Decisões (Rafael, 2026-10-07)

| Tema | Decisão |
|---|---|
| Ação principal (CTA) | Formulário "Quero uma demonstração" |
| Acompanhamento | Lista no backoffice **+** e-mail de aviso |
| E-mail de destino | `rafael.marques10@gmail.com` **inicialmente**, em variável `DEMO_NOTIFY_TO` para troca posterior sem alterar código |
| Abordagem | A: página Blade no próprio Laravel, rota `/` (sem site separado, sem formulário externo) |

## 3. Arquitetura

```
GET  /                        LandingController@show          → resources/views/landing.blade.php
POST /demonstracao            DemoRequestController@store     (throttle `demo-requests`: 5/min por IP)
GET  /backoffice/demonstracoes   Livewire DemoRequestList     (auth + Gate `manage-demo-requests`)
```

| Peça | Responsabilidade |
|---|---|
| `LandingController` | Só renderiza a view (sem lógica) |
| `DemoRequestStoreRequest` | Validação (seção 5) |
| `DemoRequestService::register(array): DemoRequest` | Grava, depois tenta notificar; **nunca** deixa a falha do e-mail apagar o pedido |
| `DemoRequest` (model) | Tabela `demo_requests` |
| `DemoRequestReceived` (Mailable) | E-mail de aviso, destino em `config('landing.notify_to')` |
| `DemoRequestList` (Livewire) | Lista paginada, filtro por status, ações de status |
| Gate `manage-demo-requests` | `fn (User $u) => $u->isAdmin()` (hoje `isAdmin()` existe e **não é usado**) |
| `config/landing.php` | `notify_to` = `env('DEMO_NOTIFY_TO')`; sem valor, o aviso é ignorado com um `Log::warning` |

**Convenções (CONVENTIONS.md):** lógica fora do controller (Service); validação em FormRequest; tabela no plural e `snake_case`; `created_at/updated_at`; índices nas colunas de filtro.

**Estilo:** um CSS próprio da landing (`resources/css/landing.css`, entrada nova no `vite.config.js`), independente do `app.css` do backoffice. A página funciona **sem JavaScript**. Os testes usam `withoutVite()` (padrão do projeto).

## 4. Conteúdo da página (rastreável às specs)

Idioma: português do Brasil. Rascunho de textos a refinar na implementação.

| Seção | Mensagem | Origem |
|---|---|---|
| **Hero** | Carta de vinhos digital no tablet, com sommelier virtual. Botão "Quero uma demonstração". Tablet desenhado em CSS exibindo a carta | F005, F006 |
| **O problema** | A carta impressa envelhece a cada rótulo que acaba; o sommelier nem sempre está livre quando o cliente decide | Premissa do produto (Arquitetura - Vinia); redigida como problema, **sem prometer resultado** |
| **Como funciona** (3 passos) | 1) Cadastre os rótulos, ou importe uma planilha. 2) Pareie os tablets com um código/QR. 3) O comensal explora a carta e pergunta à Sofia | F002, F003, F004, F005 |
| **Sofia** | Recomenda por **prato**, pelo **perfil de paladar** ou **comparando dois rótulos**, usando só os vinhos da carta do restaurante | F006, F007 |
| **Para o restaurante** | Backoffice próprio; importação `.xlsx`/`.csv` com relatório de erros por linha; "Esgotado" que atualiza sozinho; identidade visual do restaurante; vários tablets | F001, F002, F003, F004, F005 (RN02, RN06, RN07) |
| **Para o comensal** | Sem login nem cadastro; a sessão encerra após 3 min sem toque; aviso quando a conexão cai | F005 (RN03, RN05, RN08), F008 |
| **Perguntas frequentes** | Funciona em tablet? (navegador moderno, tela cheia; **testado em iPad**). Precisa de internet? A Sofia usa o quê? (só os vinhos da sua carta). Como cadastro os vinhos? Que dados do comensal vocês guardam? (sessão anônima, sem login) | F004, F005, F006, F008 |
| **Formulário** | Seção 5 | — |
| **Rodapé** | "Acesso do restaurante" → `/backoffice/login`; aviso de privacidade (seção 7) | — |

**Regras de copy:** não nomear o fornecedor de IA (a spec cita um, a produção usa outro); não dizer "aumente o ticket médio" nem qualquer ganho mensurável; não citar planos ou valores.

## 5. Formulário e dados

**Campos:** `name`* (2–120), `restaurant`* (2–150), `email`* (`email:rfc`, até 190), `phone`* (WhatsApp; só dígitos, 10–13 após limpar `+ ( ) -` e espaços), `city` (até 100), `message` (até 1000), `consent`* (checkbox LGPD), `website` (honeypot, deve vir vazio).

**Tabela `demo_requests`:** `id`, `name`, `restaurant`, `email`, `phone`, `city` (nulo), `message` (nulo), `status` (`novo` | `contatado` | `descartado`, padrão `novo`), `consent_at`, `created_at`, `updated_at`. Índices em `status` e `created_at`. **Não se grava IP nem user-agent.**

**Fluxo do envio:**
1. `website` preenchido → resposta de sucesso **sem gravar** (robô não descobre a armadilha).
2. Validação falha → volta ao formulário (`/#demo`) com os erros e os campos preenchidos.
3. Sucesso → grava com `consent_at = now()`, tenta o e-mail, redireciona a `/#demo` com mensagem "Recebemos seu pedido. Entraremos em contato em breve." (sem prometer prazo).
4. Mais de 5 envios por minuto por IP → HTTP 429 com mensagem amigável.

**Erros:** falha do e-mail é capturada, registrada (`Log::warning`) e **não** afeta a resposta nem o registro. Falha ao gravar mostra erro genérico e permite reenviar.

## 6. E-mail e backoffice

**E-mail** (`DemoRequestReceived`): assunto "Novo pedido de demonstração — {restaurante}", corpo com os campos do pedido e o link para `/backoffice/demonstracoes`. Enviado **de forma síncrona** (o cron do worker ainda não foi criado em produção), dentro de `try/catch`.

**Pré-requisito de ambiente (do Rafael):** hoje **não há SMTP configurado** (nem em `.env.example` nem no servidor; o mailer padrão é `log`). Para o aviso funcionar em produção: criar uma caixa de e-mail e preencher `MAIL_MAILER`, `MAIL_HOST`, `MAIL_PORT`, `MAIL_USERNAME`, `MAIL_PASSWORD`, `MAIL_ENCRYPTION`, `MAIL_FROM_ADDRESS`, `MAIL_FROM_NAME` e `DEMO_NOTIFY_TO=rafael.marques10@gmail.com` no `backend/.env` do servidor. Sem isso, a landing funciona e os pedidos aparecem no backoffice; só o aviso não sai.

**Backoffice:** item "Demonstrações" no menu **só para admin**; lista paginada (nome, restaurante, contato, data, status), filtro por status e botões "Marcar como contatado" / "Descartar" / "Reabrir". Contato exibido com links `mailto:` e `https://wa.me/`.

**Autorização:** rota sob `can:manage-demo-requests`; perfil `owner`/`manager` recebe 403; visitante é redirecionado ao login.

## 7. Privacidade (LGPD)

O formulário coleta dado pessoal, então a página traz um **aviso de privacidade** curto: quais dados (nome, restaurante, e-mail, telefone, cidade e mensagem), para quê (retornar o pedido de demonstração), por quanto tempo, e como pedir a exclusão (contato). O checkbox de consentimento é obrigatório e `consent_at` é gravado.

> **Atenção:** o texto será um **texto-base**. A **revisão jurídica é responsabilidade do Rafael** antes de publicar. Definir também o **prazo de retenção** (sugestão a validar: 12 meses).

## 8. Visual e acessibilidade

- Identidade do app: vinho `#6E1A22`, ouro `#D4AF37`, fundo `#1A1513`, **Cormorant Garamond** nos títulos e **Inter** no texto; mesma linguagem de filetes e tracking largo.
- Responsiva (celular, tablet, desktop); layout de leitura com largura máxima ~1120px.
- Texto corrido ≥ 16px; contraste AA (texto secundário nunca abaixo de 4,5:1); alvos ≥ 48px; foco visível; `lang="pt-BR"`; landmarks (`header`, `main`, `section`, `footer`); formulário com `label` real, erros associados por `aria-describedby`; respeita `prefers-reduced-motion`.
- Imagens: **nenhuma foto de stock**. O tablet do hero é HTML/CSS (reaproveita a linguagem dos wireframes do tablet).

## 9. SEO e indexação

`title`, `meta description`, Open Graph/Twitter, `canonical` `https://vinia.ia.br/`. Adicionar `robots.txt` com `Disallow: /backoffice` e `Disallow: /tablet`, e `noindex` no login e na PWA (que não devem aparecer em buscas).

## 10. Testes

- `GET /` retorna 200 e contém os títulos das seções; `GET /backoffice/login` continua funcionando.
- `POST /demonstracao` válido: grava, status `novo`, `consent_at` preenchido, e-mail enviado (`Mail::fake`).
- Inválido: erros por campo (nome curto, e-mail ruim, telefone fora do padrão, sem consentimento) e nada gravado.
- Honeypot preenchido: sucesso aparente e **nada gravado**.
- 6º envio no mesmo minuto: 429.
- E-mail lançando exceção: o pedido continua gravado e a resposta é de sucesso.
- Sem `DEMO_NOTIFY_TO`: grava e não tenta enviar.
- Backoffice: admin acessa e altera status; `owner`/`manager` recebem 403; visitante vai ao login.
- Acessibilidade: checagem manual dos pontos da seção 8 (e `*a11y-check` do @qa).

## 11. Entrega

1. Migration `demo_requests` (roda sozinha no deploy).
2. `.env.example` ganha `DEMO_NOTIFY_TO` e as variáveis `MAIL_*` documentadas.
3. Deploy pelo pipeline atual (push na `main`); o `/` passa a servir a landing.
4. No servidor: preencher as variáveis da seção 6.
5. Atualizar o guia `DEPLOY-HOSTINGER.md` (e-mail, `DEMO_NOTIFY_TO`) e o cofre.

## 12. Pontos em aberto

1. Texto do aviso de privacidade (revisão jurídica) e prazo de retenção.
2. Caixa de e-mail e dados de SMTP (sem isso, só o aviso por e-mail fica de fora).
3. Fontes do Google (Cormorant/Inter) são carregadas do Google: o IP do visitante é visto pelo Google. Manter (como no tablet) ou **hospedar as fontes**? Recomendação: hospedar, num passo posterior.
4. O FAQ vai citar valores? Hoje a spec não define preço: a resposta proposta é "combinamos na demonstração". Confirmar.
5. Nome e logotipo públicos: usar "Vinia" e a taça em traço do app.
