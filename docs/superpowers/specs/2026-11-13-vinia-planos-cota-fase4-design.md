# Vinia SaaS — Fase 4: Planos, trial com prazo, cota e consumo (design)

**Data:** 2026-11-13 · **Autor:** Rafael (decisões) + controlador (calls marcadas **[CALL]**)
**Status:** decisões do Rafael incorporadas (renovação automática e marca "legado"); revisado pelo construtor em 2026-11-13. Deriva do spec-mãe `2026-11-10-vinia-saas-design.md` (§6.3, §6.5, §7, §8), do estudo `2026-11-12-vinia-saas-precificacao.md` e das Stories 9.1 a 9.4 (multi-tenant, celular, LGPD, onboarding), já mergeadas na `main` local.

## 1. Intenção e por quê

Hoje o teste de 14 dias não termina (só o CNPJ já usado inativa a conta), a Sofia não tem cota por plano e o sistema grava apenas o total de tokens por consulta. Para vender, o Vinia precisa: (a) encerrar o trial no prazo, (b) limitar e medir o uso da Sofia por plano, (c) mostrar ao gestor quanto já usou e avisar antes de acabar. O estudo de preços mostra que a IA é barata e que a margem depende de medir o custo e de limitar a cota; o risco do negócio é ter clientes, não o custo da IA.

## 2. Objetivos

1. `subscriptions`: plano, estado (`trial | active | canceled`), ciclo e datas, derivado ao ler (sem depender de cron).
2. **Trial com prazo:** no dia 14 a Sofia desliga; a carta fica visível por 7 dias; depois o restaurante fica inativo (página "teste encerrado", nada apagado). Teto de **150 consultas** no trial.
3. **Cota por plano**, contada em `ai_usage` no ciclo de 30 dias, aplicada no tablet **e** no celular: ao acabar, a carta segue e a Sofia mostra mensagem amigável.
4. **Medição:** `ai_usage` com uma linha por consulta concluída, tokens de **entrada e de saída separados** e custo calculado.
5. **Painel de consumo** (dia, semana, mês contra a cota, estilo medidor) e **alertas** em 80% e 100% por e-mail ao dono e faixa no painel.
6. **Admin assina o restaurante à mão** (até a Fase 5/Asaas): troca plano, inicia ciclo, vê consumo e custo; alerta interno quando a IA passa de 30% do preço.
7. Preservar o que já existe: restaurantes criados à mão continuam funcionando.

## 3. Não objetivos e anti-objetivos

**Não objetivos:** cobrança, gateway, fatura e **excedente** (Fase 5, com o Asaas); atalho de prompt de até 40 vinhos e cache de entrada da Groq (**Fase 4b**, depois desta, antes de cobrar clientes reais); PDF/foto (premium, depois); gestão de várias unidades; pagamento de impostos/notas.

**Anti-objetivos (falha mesmo funcionando):** custo de IA de um restaurante passar da mensalidade sem alerta nem teto; cota estourada por corrida de requisições simultâneas além de uma pequena margem; um restaurante ver o consumo de outro; `ai_usage` sumir no expurgo LGPD das sessões (a cobrança contestada precisa da base); trial que nunca termina; cliente antigo (feito à mão) ser bloqueado de surpresa.

## 4. Decisões do Rafael

- Seguir o estudo de preços: Início R$ 147 / 500 consultas, Pro R$ 297 / 2.000, Rede R$ 597 / 6.000 (valores finais e contratos de gateway: Rafael estuda; o design não depende deles).
- No dia 14 a Sofia desliga na hora; a carta fica visível por 7 dias; depois o restaurante fica inativo sem apagar nada (como no caso do CNPJ já usado). Até o gateway existir, o Rafael assina o restaurante à mão no painel de admin.
- O atalho de ≤ 40 vinhos e o cache de entrada vão para a **Fase 4b**, separada: a Fase 4 entrega medição, cota, trial com prazo e painel.
- Excedente fica para a Fase 5 (só tem sentido com cobrança).
- **Ciclo:** a assinatura ativa **renova sozinha a cada 30 dias** até o admin cancelar; o painel de admin mostra o fim do ciclo de cada restaurante. Na Fase 5 a cobrança passa a mandar na renovação.
- **Clientes criados à mão:** marca **"legado"** por restaurante: todo restaurante existente nasce com ela e, enquanto ligada, vale o plano atual **sem cota e sem limite de rótulos**; o Rafael tira a marca de cada um no painel. Restaurantes novos (trial e assinados no painel) nunca têm a marca. Para o trial valem sempre 14 dias, 150 consultas e 100 rótulos. O limite de rótulos nunca esconde nem apaga vinho existente: só impede cadastrar novos além do limite.

## 5. Abordagem

Uma tabela `subscriptions` por restaurante e uma tabela `ai_usage` com **uma linha por consulta concluída**; a cota usada é a soma das linhas do ciclo (índice por `restaurant_id` e data), sem contador separado. Estado da assinatura **derivado das datas ao ler** (`SubscriptionService::state()`), sem job periódico; um comando diário opcional só arruma `restaurants.active`. Descartadas: contador materializado por ciclo (dois lugares para errar e sem Redis para travar), cache de cota (precisa de invalidação), e modelar tudo em `restaurants` (mistura plano e ciclo com cadastro).

## 6. Comportamento

**Planos [CALL de mapeamento].** `starter = Início`, `standard = Pro`, `premium = Rede` (já existem no banco); `trial` ganha cota 150. Quotas e limites ficam em `config/plans.php` (nome, preço de referência, cota de consultas, limite de tablets, limite de rótulos).

**Estado derivado (lido por TODOS os pontos de bloqueio).** O middleware do backoffice, a autenticação do tablet e a rota pública leem o estado derivado, não `restaurants.active`; o cliente `canceled` vê a mesma página "teste encerrado" com texto próprio. A assinatura ativa renova o ciclo sozinha. `trial` (antes de `trial.ends_at`) → `trial_grace` (7 dias depois do fim: carta visível, Sofia desligada) → `trial_ended` (restaurante tratado como inativo, mesma página "teste encerrado" da Fase 3) ; `active` (plano pago, ciclo corrente); `canceled` (Sofia off, carta 7 dias, depois inativo). Admin muda o estado.

**Cota [CALL].** Conta consulta **concluída** (`ai_interactions` com resposta); erro do provedor não gasta cota; se a consulta falhar **depois** de o provedor já ter cobrado, grava-se a linha em `ai_usage` com o custo e a marca `counted = false` (não conta para a cota, mas entra no custo real e no alerta de 30%). Verificação **antes** de criar a consulta, no tablet e no celular, atrás de uma única porta (`QuotaGate`): se a cota do ciclo acabou, responde código `QUOTA_EXHAUSTED` e mensagem amigável ("A Sofia descansou por hoje…" a definir com o construtor), sem criar `AiInteraction`. Concorrência: a checagem e a gravação usam uma reserva pequena (margem aceita de poucas unidades acima da cota, como nas travas existentes); os tetos já existentes (por sessão, por aparelho, por IP, 500/dia por restaurante) continuam valendo.

**Medição.** Cada serviço de IA (Groq, Gemini, Anthropic) devolve tokens de entrada e de saída separados (hoje só a soma). O job grava `ai_usage` (restaurante, interação, provedor, modelo, `tokens_in`, `tokens_out`, `cost_brl`, data); o custo vem de `config/ai_pricing.php` (US$ por milhão de tokens de entrada e de saída por modelo, câmbio em R$), que o Rafael pode ajustar.

**Alertas.** Em 80% e 100% da cota do ciclo, e-mail ao dono (fila) uma vez por ciclo e por limiar, mais faixa no backoffice; trial usa o teto de 150. Alerta interno ao Rafael (log + e-mail) quando o custo de IA do ciclo passa de 30% do preço do plano.

**Painel.** Em "Minha conta" (ou item "Consumo"), para dono e gerente: consultas por dia, semana e mês contra a cota, tempo até o fim do ciclo; sommelier não vê. Admin vê o consumo e o custo de qualquer restaurante.

**Admin assina.** Na tela de planos: escolher plano, estado e início do ciclo de um restaurante (cria/atualiza `subscriptions`), ver cota usada, custo e fim do ciclo, e ligar/desligar a marca legado. **Restaurantes criados à mão:** a migration cria `subscriptions` `active` com o plano atual e `legacy = true` (sem cota e sem limite de rótulos até o Rafael tirar a marca). **Cadastros do trial já existentes na migração:** ganham assinatura `trial` com as datas do `trial_claims` (hoje não há nenhum em produção); a assinatura passa a guardar as datas do trial e o `trial_claims` fica só como trava contra reuso. Mudar de plano no meio do ciclo mantém o ciclo e aplica a cota nova.

**Limite de rótulos [CALL].** Sem o atalho (4b), o estudo manda limitar a carta: Início 100, Pro 150, Rede 150 por unidade, trial 100; ao importar/criar vinho além do limite, mensagem pedindo troca de plano. A 4b remove esse limite.

## 7. Restrições

Hostinger compartilhada (sem Redis, sem `schedule:run`; crons diretos só onde indispensável; esta fase não exige cron novo). Suíte verde em SQLite **e** MySQL 8; isolamento A×B nas telas de consumo; `ai_usage` **fora** do expurgo LGPD e **sem `device_id`** nem FK em cascata para `comensal_sessions`/`ai_interactions` (nota herdada da 9.3). Fluxo AIOX: story em `vinia-docs`, push/PR só do @devops. A Sofia do tablet e do celular continuam funcionando como hoje enquanto a cota não acabar.

## 8. Sucesso

Um restaurante no trial usa a Sofia até 150 consultas e/ou 14 dias e ela desliga; o dono vê quanto usou e é avisado em 80% e 100%; o Rafael troca o plano de um restaurante e a cota muda; cada consulta deixa uma linha com tokens de entrada, saída e custo; nenhum restaurante vê outro; clientes antigos seguem sem bloqueio; suíte verde.

## 9. Deixado ao construtor

Nomes de tabelas/colunas, textos das mensagens e e-mails, layout do painel e do medidor, estrutura das stories e a ordem das tarefas, forma exata da reserva de cota contra corrida.
