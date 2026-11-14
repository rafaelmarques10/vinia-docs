# Vinia SaaS — Fase 5a: assinar e pagar pelo Asaas (design)

**Data:** 2026-11-14 · **Autor:** Rafael (decisões) + controlador (calls marcadas **[CALL]**)
**Status:** abordagem A (assinatura recorrente do Asaas) aprovada pelo Rafael em 2026-11-14; este documento aguarda a aprovação dele. Deriva do spec-mãe `2026-11-10-vinia-saas-design.md` (§6.1, §6.5, §7), do estudo `2026-11-12-vinia-saas-precificacao.md` e das Stories 9.4 a 9.6. O excedente (pacote de consultas, limite em R$, fatura pós-paga) fica para a **Fase 5b**.

## 1. Intenção e por quê

Hoje só o Rafael assina um restaurante, à mão, na tela de planos, e o ciclo de 30 dias renova sozinho. Para vender sem estar no meio de cada venda, o dono precisa escolher um plano e pagar sozinho; o pagamento (e só ele) deve renovar o acesso e a falta dele deve desligar a Sofia no prazo. O Rafael cria a conta no Asaas e põe as credenciais do sandbox no `.env`; o Asaas também pode emitir a nota fiscal.

## 2. Objetivos

1. **`PaymentGateway`** (interface) com a implementação `AsaasGateway` (API v3) e uma `FakeGateway` para testes e para desenvolver sem credenciais.
2. **Tela "Meu plano"** no backoffice (dono): estado atual (dias de teste, plano, pago até), escolha de plano, **Assinar** (leva ao link de pagamento do Asaas), **Trocar de plano**, **Cancelar** e **Faturas**.
3. **Webhook** do Asaas que renova o acesso quando o pagamento entra, marca o atraso e registra tudo de forma idempotente.
4. **Estado derivado pelo pagamento:** assinatura gerida pelo gateway fica ativa até a data paga; passada a data, 7 dias de carência (carta visível, Sofia desligada) e depois encerrada, sem apagar nada.
5. **Nota fiscal opcional:** emissão automática de NFS-e pelo Asaas por assinatura, atrás de uma chave no `.env` (desligada por padrão) e de dados fiscais em configuração.
6. **Avisos em português** ao dono: pagamento confirmado, pagamento em atraso (carência) e assinatura cancelada; as faixas e e-mails do teste e da cota passam a apontar para "Meu plano".

## 3. Não objetivos e anti-objetivos

**Não objetivos:** excedente e fatura pós-paga (5b); cupom e oferta de lançamento (−30%); proporcional (pro rata) em troca de plano; reembolso; formulário de cartão próprio; marketplace/split; conciliação contábil; emitir nota fiscal por outro serviço; subdomínio e domínio (Fase 7).

**Anti-objetivos (falha mesmo funcionando):** um webhook falso (o Asaas não assina os avisos) liberar acesso pago; o mesmo pagamento renovar duas vezes (reenvio ou ordem trocada de eventos); um cliente que pagou perder a Sofia porque um aviso se perdeu; CPF, CNPJ, cartão, chave da API ou token do webhook em log ou em tabela; um restaurante ver ou alterar a assinatura de outro; cliente antigo (legado) ou assinado à mão pelo admin ser bloqueado de surpresa; quebrar o fluxo de teste de 14 dias que já existe.

## 4. Decisões do Rafael

- Abordagem **A**: assinatura recorrente do Asaas com link de pagamento hospedado por eles (Pix, boleto ou cartão); o Vinia não toca em dado de cartão.
- Excedente fica para a 5b; na 5a o plano e a cota são os da Fase 4.
- Rafael cria a conta e configura o `.env` com as credenciais do sandbox; a nota fiscal pode ser emitida pelo próprio Asaas, e o Vinia só liga isso por configuração.

## 5. Abordagem

Alternativas descartadas: **B** cobranças avulsas geradas pelo Vinia a cada ciclo (exige cron, refaz recorrência e tratamento de atraso que o Asaas já tem) e **C** formulário de cartão dentro do Vinia (responsabilidade e código sem ganho). Em A o Asaas gera as cobranças, avisa o cliente e emite a nota; o Vinia assina, cancela, troca o valor e escuta os eventos de cobrança.

## 6. Comportamento

**Modelo.** `subscriptions` ganha `gateway` (nulo ou `asaas`), `gateway_customer_id`, `gateway_subscription_id` e `paid_through` (data até a qual está pago). Nova tabela `payment_events`: um registro por aviso do gateway (id do evento único para idempotência, restaurante, id da cobrança, tipo, valor, estado, link da fatura, data de vencimento, data do pagamento), usada também como histórico de faturas. **Sem CPF, sem CNPJ, sem cartão** nela nem em log **[CALL]**: o CPF/CNPJ digitado para assinar vai direto ao Asaas e não é gravado no Vinia (o CNPJ opcional que o cadastro já guarda continua como está).

**Assinar (trial ou legado ou cancelado).** O dono escolhe o plano e informa nome ou razão social e CPF ou CNPJ (o Asaas exige para cobrar e para a nota; com a nota ligada, também CEP e número). O Vinia cria o cliente e a assinatura no Asaas (vencimento hoje, valor do plano em `config/plans.php`) e leva o dono ao link de pagamento da primeira cobrança. Até o pagamento entrar, **nada muda**: o teste segue até o fim e, se já estiver em carência, continua em carência. Quem assina durante o teste não leva os dias que sobram **[CALL]**.

**Pagamento entra (`PAYMENT_CONFIRMED`/`PAYMENT_RECEIVED`).** A assinatura vira `active` no plano pago, `legacy = false`, `paid_through` avança um ciclo de 30 dias a partir do vencimento pago (nunca para trás), `cycle_started_at` acompanha. Cada cobrança renova **uma única vez** (idempotente pelo id da cobrança).

**Estado derivado (`SubscriptionService::state`).** Assinatura sem gateway: igual à Fase 4 (renova sozinha). Assinatura com gateway: `active` até `paid_through`; depois `grace` por 7 dias (carta visível, Sofia desligada) e `ended`. Cancelar mantém o acesso pago até `paid_through` (só a renovação para) e depois segue a carência **[CALL]**.

**Trocar de plano.** O plano e a cota novos valem na hora; o Asaas passa a cobrar o valor novo a partir da próxima cobrança, sem proporcional **[CALL]**. **Cancelar:** cancela a assinatura no Asaas, mantém o pago até `paid_through`. Quem cancelou pode assinar de novo.

**Webhook** `POST /webhooks/asaas`, fora do grupo web (sem CSRF, sem sessão), com limitador próprio. Confere o cabeçalho `asaas-access-token` contra `ASAAS_WEBHOOK_TOKEN` em tempo constante (recusa com 401). Como o aviso não é assinado, **antes de agir o Vinia consulta a cobrança na API do Asaas** e usa o estado e o vínculo com a assinatura que voltam de lá, não o corpo recebido. Responde 200 depressa também para eventos que não conhece (o Asaas pausa a fila de quem responde erro seguidas vezes). Eventos tratados: cobrança confirmada/recebida (renova), vencida (registra e a carência corre pela data), estornada/chargeback (registra e alerta o Rafael), assinatura removida (cancela). Tudo grava em `payment_events` e audita com ids.

**Autocorreção.** `BillingSyncService::sync(Restaurant)` consulta as cobranças da assinatura no Asaas e aplica o que faltar, pelo mesmo caminho do webhook. É chamado ao abrir "Meu plano" e por um botão do admin, para o cliente que pagou não depender de um aviso perdido.

**Nota fiscal.** Com `ASAAS_NFSE_ENABLED=true`, ao criar a assinatura o Vinia configura no Asaas a emissão automática das notas (`invoiceSettings`) com o serviço municipal, a alíquota de ISS e a situação de PIS/COFINS lidos de `config/billing.php`. Desligada por padrão; a emissão real depende do cadastro municipal do Rafael e não é garantida por esta fase.

**Avisos.** E-mails ao dono, por notificação em fila (a existente): pagamento confirmado, pagamento em atraso (Sofia desligada, carta segue por 7 dias) e assinatura cancelada. O Asaas já envia ao cliente os avisos da própria cobrança. As faixas e e-mails de teste, cota e carência ganham o botão "Assinar" / "Ver meu plano".

**Admin.** A tela de planos mostra a cobrança de cada restaurante (gestão: manual ou Asaas, pago até, último evento) e o botão de sincronizar. As ações manuais da Fase 4 seguem valendo para assinaturas sem gateway; nas geridas pelo gateway, assinar/cancelar à mão fica bloqueado com aviso.

## 7. Restrições

Hostinger compartilhada: sem cron novo e sem worker (avisos pela fila existente; o webhook processa no próprio pedido). Suíte verde em SQLite **e** MySQL 8. Isolamento A×B em "Meu plano", faturas e webhook. Segredos só no `.env` (`ASAAS_API_KEY`, `ASAAS_ENV=sandbox|production`, `ASAAS_WEBHOOK_TOKEN`, `BILLING_GATEWAY=fake|asaas`). Fluxo AIOX: story em `vinia-docs` (9.7), push/PR só do @devops. O sandbox e a produção têm webhooks separados; o ambiente local precisa de um túnel público para receber avisos reais.

## 8. Sucesso

Um dono em teste escolhe um plano, paga pelo link e passa a ter o plano e a cota; no mês seguinte a próxima cobrança paga renova sozinha; sem pagamento, a Sofia desliga ao fim de `paid_through` e a carta fica 7 dias; cancelar mantém o pago até o fim do período; reenviar o mesmo aviso não renova duas vezes; um aviso com token errado é recusado; clientes legados e assinados à mão não mudam; suíte verde; e, com as credenciais do sandbox no `.env`, o fluxo roda de ponta a ponta contra o Asaas.

## 9. Deixado ao construtor

Nomes de tabelas, colunas, classes e rotas; layout de "Meu plano"; textos dos avisos; o formato exato dos campos do `AsaasGateway` (a primeira tarefa valida no sandbox como assinar com cartão recorrente automático, tipo de cobrança `UNDEFINED` versus `CREDIT_CARD`, e como obter o link da primeira cobrança, e ajusta o desenho se a API se comportar diferente do esperado); a ordem das tarefas.
