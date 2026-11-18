# Vinia SaaS — Fase 5b: créditos extras de consultas (design)

**Data:** 2026-11-18 · **Autor:** Rafael (decisões) + controlador (calls marcadas **[CALL]**)
**Status:** abordagem A (saldo em consultas, pré-pago) escolhida pelo Rafael em 2026-11-18; este documento aguarda a aprovação dele. Deriva do spec-mãe `2026-11-10-vinia-saas-design.md` (§6.5), do estudo `2026-11-12-vinia-saas-precificacao.md` (linha 76) e da Fase 5a (`2026-11-14-vinia-cobranca-asaas-fase5a-design.md`, Story 9.7). **Muda o spec-mãe:** o excedente era pós-paga com limite em R$ definido pelo gestor; passa a ser **pré-pago**, e o saldo comprado é o limite.

## 1. Intenção e por quê

O dono paga um plano de valor fechado com uma cota de consultas da Sofia. Quando a cota acaba, ele compra um pacote de créditos na hora, sem mexer no plano mensal, e a Sofia volta assim que o pagamento entra. O Rafael quer evitar surpresa na fatura e inadimplência: ninguém consome antes de pagar.

## 2. Objetivos

1. **Comprar créditos** em "Meu plano" e no aviso de cota esgotada: pacote de **500 consultas** por **R$ 49** (ou **R$ 79**), cobrança avulsa no Asaas com link de pagamento (Pix, boleto ou cartão).
2. **Saldo de consultas** por restaurante, que sobe quando o pagamento entra (webhook, idempotente) e passa para o mês seguinte enquanto a assinatura estiver ativa.
3. **Consumo:** primeiro a cota do plano, depois o saldo. O `QuotaGate` segue sendo a única porta da Sofia (tablet e celular).
4. **Avisos:** saldo baixo (restam 20% do último pacote ou menos) e saldo zerado, ao dono, por e-mail e faixa em "Meu plano"; pagamento do pacote confirmado.
5. **Histórico** de compras e consumo de créditos em "Meu plano".

## 3. Não objetivos e anti-objetivos

**Não objetivos:** limite em R$ e fatura pós-paga (descartados); recompra automática (auto-recarga); cupom; reembolso ou estorno de saldo não usado; crédito para teste ou plano vencido; mais de um tamanho de pacote; nota fiscal específica do pacote além do que o Asaas já emite para cobranças avulsas por configuração.

**Anti-objetivos (falha mesmo funcionando):** a mesma compra creditar duas vezes (reenvio ou ordem trocada de eventos); a Sofia consumir crédito sem pagamento confirmado; consumir saldo enquanto ainda há cota do plano; a mesma consulta debitar o saldo duas vezes ou deixar de devolvê-lo quando a consulta falha e sai da cota; saldo de um restaurante visível ou usável por outro; quebrar a compra do plano, o webhook ou a renovação da 5a; CPF, CNPJ, cartão, chave da API ou token em log ou tabela.

## 4. Decisões do Rafael

- Excedente **pré-pago**: o dono compra créditos; plano mensal inalterado.
- Quando a cota e o saldo acabam, o dono compra mais **na hora** (o "upgrade no momento").
- O saldo **passa para o mês seguinte** enquanto a assinatura estiver ativa.
- Só plano ativo compra e consome crédito (trial não tem).
- Pacote de 500 consultas por R$ 49; R$ 79 sem o atalho da Sofia e com carta acima de 200 rótulos (estudo de precificação).

## 5. Abordagem

Alternativas: **A** saldo em consultas (escolhida); **B** saldo em R$ debitado pelo custo real (variação de centavos, difícil de explicar e testar); **C** pacote como item recorrente da assinatura (descartada: o plano não muda). Em A o pacote é uma cobrança avulsa no Asaas, que credita ao confirmar, e o consumo é um lançamento no uso de IA.

## 6. Comportamento

**Quem compra.** Só o dono (gate `manage-billing`), só com assinatura gerida pelo gateway e no estado `active`. Em carência, encerrada ou teste, a compra é recusada com aviso claro; quem está em carência precisa regularizar o plano primeiro **[CALL]**.

**Preço do pacote [CALL].** R$ 79 quando a carta do restaurante tem **mais de 200 rótulos**; senão R$ 49. O valor é decidido na hora da compra e **gravado na compra**; mudar o preço depois não altera compras feitas. Valores, tamanho do pacote (500) e o corte de 200 rótulos ficam em `config/plans.php` ou `config/billing.php`, não no código. O atalho da Sofia (Fase 4b) não é uma condição separada porque está sempre ativo; o corte pela carta é a regra viva **[CALL]**.

**Compra.** O dono clica em "Comprar créditos" e confirma o valor. O Vinia cria no Asaas uma cobrança avulsa para o cliente já existente da assinatura (vencimento hoje, `billingType` do mesmo padrão da 5a) e leva o dono ao link de pagamento. A compra fica `pending` até o pagamento entrar; nada muda no saldo antes disso. Uma compra `pending` aberta é reaproveitada se o dono clicar de novo (não cria cobrança duplicada); uma `pending` vencida ou cancelada é fechada.

**Crédito entra.** O webhook da 5a (mesmo endpoint, mesma conferência de token, mesma reconsulta do pagamento na API do Asaas) reconhece a cobrança como **pacote de créditos** pelo vínculo com a compra (id da cobrança), não pelo corpo do aviso. Ao `PAYMENT_CONFIRMED`/`PAYMENT_RECEIVED` o saldo sobe 500, uma única vez por cobrança (marca atômica, como `applied_at` na 5a). Cobrança de pacote nunca altera `paid_through`, plano nem estado da assinatura. Estorno ou chargeback de pacote já creditado alerta o Rafael e marca a compra; não retira saldo automaticamente **[CALL]**.

**Autocorreção.** `BillingSyncService::sync` (chamado ao abrir "Meu plano" e pelo botão do admin) também confere as compras `pending` no Asaas e aplica o que faltar, para um aviso perdido não deixar o dono pagante sem crédito.

**Consumo.** `ai_usage` ganha uma marca `from_credit` (consulta que passou da cota do plano e gastou 1 do saldo). `AiUsageRecorder::record` define a marca no momento de gravar o uso: se `used >= cota` do ciclo, a consulta é `from_credit`. **Saldo = consultas compradas creditadas − consultas `counted` e `from_credit`** (derivado, sem contador mutável). `markUncounted` (consulta que falhou depois de o provedor cobrar) devolve o saldo naturalmente porque a consulta sai de `counted`. O saldo nunca fica negativo por construção: o gate só libera com saldo.

**Gate.** `QuotaGate::check`: estado trial/active como hoje; sem cota (legado) passa; com cota, libera se `used + inFlight < cota + saldo`. Se `used + inFlight >= cota + saldo`, devolve **429 `QUOTA_EXHAUSTED`**, e a mensagem para o dono (não para o cliente do restaurante) leva ao "Comprar créditos"; a resposta ao cliente final continua "Chame o nosso sommelier". As consultas em andamento ocupam primeiro a cota e depois o saldo. Teste (trial) não tem saldo.

**Avisos.** Notificações em fila ao dono, como na 5a: saldo baixo (cruzou 20% do último pacote), saldo zerado (Sofia desligada até comprar) e compra confirmada. Cada aviso dispara uma vez por cruzamento (sem repetir a cada consulta). A faixa de cota esgotada de "Meu plano" ganha o botão de compra.

**Meu plano.** Mostra saldo de créditos, botão "Comprar créditos" (com o valor), compra pendente (link para pagar) e o histórico de compras (data, valor, estado) e o consumo do ciclo.

**Admin.** A tela de planos mostra o saldo de cada restaurante; o admin pode **conceder créditos** à mão (lançamento de cortesia, auditado, sem cobrança) e sincronizar compras.

**Decisões de detalhe (calls do controlador, após a leitura do construtor).**

1. **Marca `from_credit` e devolução [CALL].** Quando `markUncounted` tira da cota uma consulta que **não** era `from_credit`, a consulta `from_credit` mais antiga do mesmo ciclo perde a marca (o saldo volta e a cota é a que abriu espaço). Se a consulta uncounted era `from_credit`, só ela perde a marca. A corrida de duas gravações simultâneas lendo o mesmo `used` é aceita, como o gate já aceita (o desvio máximo é de poucas consultas, para o lado do cliente).
2. **Saldo fora de `active` [CALL].** O saldo **não expira nem é zerado**: fica congelado enquanto a assinatura estiver em teste, carência ou encerrada, e volta a valer quando ela voltar a `active` (inclusive reassinando). Não há reembolso. Troca de plano no meio do ciclo muda só a cota; o saldo não se altera.
3. **Avisos de saldo [CALL].** "Baixo" = saldo cai a 100 ou menos (20% de 500; valor em config), vindo de acima de 100; "zerado" = saldo chega a 0. Cada aviso grava uma marca de envio e **só rearma quando uma compra ou concessão leva o saldo acima do limite**. Vale também para quem só recebeu cortesia.
4. **Contagem de rótulos [CALL].** Conta os vinhos do restaurante **não removidos** (disponíveis ou não), no clique de comprar. Se uma compra `pending` aberta tem preço diferente do calculado agora, ela é fechada e uma nova é criada.
5. **Plano sem cota (legado) [CALL].** Não vê o botão de compra; a compra é recusada. Crédito só existe onde há cota.
6. **Webhook [CALL].** Cobrança cujo id está em `credit_purchases` segue o caminho do pacote; qualquer outra segue o caminho da 5a. Pagamento de pacote que chega com a assinatura fora de `active` **credita** o saldo (congelado, ver item 2); nunca mexe em `paid_through`.
7. **Cortesia do admin [CALL].** Mesma tabela das compras, com tipo `grant`: entra já como `paid`, sem cobrança, auditada, e aparece no histórico do dono como "cortesia". Não participa da reutilização de `pending`.
8. **Estorno de pacote [CALL].** Reusa o alerta ao Rafael que a 5a já faz para estorno e chargeback; sem canal novo.

## 7. Restrições

Hostinger compartilhada: sem cron novo (a compra nasce no clique; nada roda no fim do ciclo). Suíte verde em SQLite **e** MySQL 8. Isolamento A×B em saldo, compras e webhook. O webhook e o `QuotaGate` são os dois pontos críticos: nada da 5a (renovação, carência, token, idempotência) pode regredir. Segredos só no `.env`. Fluxo AIOX: story em `vinia-docs` (9.8), push/PR só do @devops. O sandbox do Asaas aceita `receiveInCash` para simular o pagamento do pacote.

## 8. Sucesso

Um dono com plano ativo esgota a cota, compra um pacote, paga pelo link e a Sofia volta com 500 consultas; sobra de um mês aparece no mês seguinte; o saldo só é gasto depois da cota; o mesmo aviso de pagamento não credita duas vezes; um aviso com token errado é recusado; trial, carência e encerrada não compram nem consomem crédito; uma consulta que falha devolve o saldo; cobrança de pacote não mexe em `paid_through`; os avisos disparam uma vez; suíte verde nos dois bancos; e, com as credenciais do sandbox, o fluxo comprar → pagar (`receiveInCash`) → crédito roda de ponta a ponta.

## 9. Deixado ao construtor

Nomes de tabelas, colunas, classes e rotas (por exemplo `credit_purchases` e a marca `from_credit`); como o `PaymentGateway` cria a cobrança avulsa (nova operação na interface, na `AsaasGateway` e na `FakeGateway`) e como o webhook distingue cobrança de pacote de cobrança de assinatura; a ordem das tarefas; o layout de "Meu plano"; textos dos avisos; a mensagem exata do gate para o dono; se o histórico de consumo é lista ou resumo.
