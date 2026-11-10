# Vinia SaaS — Design

**Data:** 2026-11-10 · **Autor:** Rafael (decisões) · **Fonte:** "Plano de Implementação – Vinia SaaS" (PDF, 2026-11-10) + conversa de brainstorming
**Status:** aprovado pelo Rafael para seguir à implementação. Itens marcados **[CALL]** são decisões minhas (a revisar); **[ABERTO]** depende do Rafael.

## 1. Intenção

Transformar o Vinia (hoje em produção como instalação operada pelo Rafael) em SaaS vendável: um restaurante desconhecido se cadastra sozinho, testa 14 dias sem cartão, publica sua carta de vinhos, usa a Sofia (IA) e vira assinante, sem ajuda do Rafael. Meta do plano: 6 semanas, 3 restaurantes em contas reais.

**Por quê:** hoje cada restaurante é cadastrado manualmente pelo Rafael (projeto solo). Para divulgar e vender, o cadastro, a cobrança e o controle de custo da IA precisam ser autônomos.

## 2. Objetivos

1. Cadastro self-service com trial de 14 dias **sem cartão**.
2. Importação da carta (CSV/Excel; PDF/foto por IA como rascunho revisável). Restaurante novo publica a carta em < 15 min.
3. Carta pública por link/QR no celular do cliente; tablet continua existindo, opcional e recomendado.
4. Controle de custo da Sofia: cota por plano, medição de tokens, painel de consumo para o gestor, excedente opcional.
5. Cobrança recorrente por plano, bloqueio por inadimplência.
6. Isolamento garantido entre restaurantes (testes no CI).
7. Infra com fila, backup, monitoramento, staging; LGPD básica.
8. Landing com demo e CTA "Testar 14 dias grátis".

## 3. Não objetivos

- Banco por cliente (decisão do plano: banco único com `restaurant_id`).
- Login do comensal (cliente final nunca cria conta).
- Geolocalização para validar presença no restaurante (frágil e irritante).
- Multi-unidade/rede completa (plano Rede é só limite de unidades; gestão de várias unidades fica para depois) **[CALL]**.
- Emissão automática de nota fiscal na primeira versão (manual, como no plano).

## 4. Anti-objetivos (seria falha mesmo funcionando)

- Um restaurante ler, alterar ou apagar dados de outro.
- Custo de IA de um restaurante superar a mensalidade sem alerta nem teto.
- Preço errado publicado por erro de extração de IA (extração é sempre rascunho).
- Pedir cartão antes do trial (derruba conversão, decisão explícita do Rafael).

## 5. Estado atual do código (auditoria 2026-11-10)

O plano supõe "uma carta, um restaurante". O código **já está parcialmente multi-restaurante**:

| Item | Estado |
|---|---|
| `restaurants` (name, slug, cnpj, logo_url, cores, active, plan) | existe |
| `restaurant_id` em users, wines, tablets, comensal_sessions | existe (manual, sem escopo global) |
| `ai_interactions` | **sem** `restaurant_id` (liga por `session_id`); sem custo, só `tokens_used` |
| Escopo global (`BelongsToRestaurant`) | **não existe**; filtros são manuais por query |
| Policies (Restaurant, Wine) | existem; papéis `admin` (plataforma), `owner`, `manager` |
| Papel `sommelier`, tabela pivô `restaurant_user` | não existem (usuário pertence a um único restaurante via `users.restaurant_id`) |
| Acesso do comensal | só tablet com token Bearer (`TabletAuthentication`), API `/api/v1` |
| Cadastro self-service, verificação de e-mail, recuperação de senha | **não existem** |
| Importação CSV/Excel | existe (`WineImportService`, tela `WineImport`) |
| Importação PDF/foto por IA | não existe |
| Cobrança, planos com preço, trial | **não existem** (só `restaurants.plan` e limite de tablets, tela Planos do admin) |
| Cota/medição/limite por sessão da Sofia | parcial: 25 consultas por sessão (commit 8dee49f) |
| Fila | `jobs` table (driver database); sem Redis/Horizon |
| Landing + pedido de demonstração | existe (stories 7.1/7.2) |

**Consequência:** a Fase 1 do plano é bem menor do que escrita: o trabalho é **endurecer** (escopo global, `restaurant_id` em `ai_interactions`, testes de isolamento) e não criar do zero.

## 6. Decisões do Rafael

### 6.1 Trial e cobrança
- Trial de 14 dias **sem cartão**; lembretes nos dias 7, 12 e 14.
- Cobrança aparece só perto do fim do trial.
- Gateway, preços finais, domínio e hospedagem: **[ABERTO]** (Rafael vai estudar). O design não depende deles; a integração de gateway fica atrás de uma interface (`PaymentGateway`) **[CALL]**.

### 6.2 Acesso do comensal
- **Tablet:** opcional, mas apresentado como o modo **recomendado**, porque o consumo de créditos fica sob controle do restaurante.
- **Celular:** modo mais acessível; o cliente abre a carta pelo QR no próprio aparelho.
- O sistema explica ao gestor a diferença de risco ao escolher o modo celular.

### 6.3 Proteção do crédito de IA no modo celular
- **Carta** (vinhos, preços, filtros): pública, leve, cache offline, sem custo de IA.
- **Sofia:** só dentro de uma sessão curta e limitada. Travas combinadas **[CALL, valores a calibrar]**: sessão expira (~3 h), limite de consultas por sessão (hoje 25; revisar), limite por IP/aparelho, cache de perguntas frequentes por restaurante, cota mensal do plano.
- Se a cota acabar: carta segue visível, só a Sofia fica indisponível com mensagem amigável.

### 6.4 QR code
- O restaurante escolhe: **QR com validade de 1 mês** (renovado) ou **QR permanente único**, com aviso claro de que pode haver uso fora do local e custo maior.
- QR por mesa fica fora da v1 **[CALL]**.

### 6.5 Painel de consumo e excedente
- Painel de uso da Sofia por **dia, semana e mês** versus cota do plano (estilo medidor de uso do Claude).
- Alertas ao gestor **[CALL]**: 80% e 100% da cota.
- **Excedente (só no modo celular):** o sistema informa o risco e pede ao gestor um **limite de valor (R$)** para créditos extras. Dentro do limite a Sofia continua após a cota; ao se aproximar do limite gera alertas ao administrador do restaurante; o consumo extra vira **fatura pós-paga no ciclo seguinte**; ao bater o limite a Sofia desliga.
- **Só para quem tem plano ativo. No trial não há excedente.**
- **Inadimplente: Sofia desabilitada** (carta visível por 7 dias, como no plano).
- Preço do crédito extra e arredondamento da fatura: depende do custo real por consulta medido **[ABERTO]**; margem bruta > 80% por plano (do plano original).

## 7. Arquitetura alvo

- **Mantém:** Laravel + Livewire (backoffice), React/Vite PWA (cliente), Sofia via serviços de IA existentes (Anthropic/Gemini/Groq), banco único com `restaurant_id`.
- **Escopo global:** trait `BelongsToRestaurant` (global scope + preenchimento automático) nos models com `restaurant_id`. Consultas cruas (`DB::table`, `whereRaw`) revisadas.
- **Resolução de restaurante:** rota pública `/r/{slug}` (subdomínio fica para depois **[CALL]**); usuário logado no backoffice; tablet por token (como hoje).
- **Sessão de comensal para celular:** token de sessão assinado, com expiração e contadores; reaproveita `comensal_sessions`.
- **Uso de IA:** tabela `ai_usage` (restaurant_id, tokens in/out, custo, data) + contadores por ciclo; `ai_interactions` ganha `restaurant_id`.
- **Assinatura:** modelo `subscriptions` (plano, status: trial/active/past_due/canceled, trial_ends_at, ciclo) + webhooks do gateway atrás de interface.
- **Papéis:** manter `admin` (plataforma), `owner`, `manager`; `sommelier` e convite por e-mail na fase de onboarding. Usuário continua em um restaurante só na v1 **[CALL]** (pivô `restaurant_user` só se surgir necessidade real).

## 8. Fases

| # | Fase | Resultado | Depende de |
|---|---|---|---|
| 1 | Endurecer multi-tenant | escopo global, `restaurant_id` em `ai_interactions`, testes de isolamento no CI, revisão de queries cruas, cache/jobs com chave por restaurante | — |
| 2 | Acesso do comensal por celular | rota `/r/{slug}`, QR (validade 1 mês / permanente), sessão curta, travas da Sofia, PWA com cache offline | 1 |
| 3 | Onboarding self-service | cadastro, verificação de e-mail, recuperação de senha, assistente 4 passos, convite de equipe, e-mails transacionais, carta de exemplo, importação PDF/foto como rascunho | 1 |
| 4 | Planos, trial, cota e consumo | `subscriptions`, trial 14 dias, `ai_usage`, cota por plano, painel dia/semana/mês, alertas, bloqueio de inadimplente | 1, 2 |
| 5 | Cobrança e excedente | integração do gateway, webhooks, limite de excedente e fatura pós-paga, e-mails de cobrança | 4 e decisão de gateway/preços |
| 6 | Infra e segurança | VPS/container, Redis+Horizon, staging, backup com restauração testada, Sentry, uptime, 2FA opcional, auditoria, LGPD | decisão de hospedagem |
| 7 | Landing e lançamento | domínio, demo pública, termos/privacidade, analytics do funil, suporte | decisão de domínio |

Fases 1–4 não dependem das decisões em aberto e começam já. A 5 depende de gateway e preços; a 6, de hospedagem; a 7, de domínio.

## 9. Constraints do projeto

- Fluxo AIOX: trabalho por stories em `vinia-docs/docs/stories/`; `git push` e PR são exclusivos do @devops; documentação do Vinia sempre em `vinia-docs`.
- Não alterar L1/L2 do framework AIOX.
- Manter o stack já escolhido; testes automáticos obrigatórios (suíte atual com 470+ testes).
- Produção hoje na Hostinger compartilhada (sem Redis/Horizon): fases 1–4 devem funcionar nela.

## 10. Em aberto (Rafael)

1. Domínio e nome na web (vinia.app, vinia.com.br, vinia.ia.br já em uso).
2. Gateway: Asaas ou Stripe.
3. Hospedagem: VPS (Hetzner/DigitalOcean) ou Hostinger por mais tempo.
4. Preços finais dos planos e do crédito extra, depois de medir o custo real da Sofia.

## 11. Deixado ao construtor

Nomes de tabelas/colunas, estrutura das stories, valores exatos das travas da Sofia (dentro do que está em 6.3), layout das telas novas (seguindo o design system atual do backoffice).
