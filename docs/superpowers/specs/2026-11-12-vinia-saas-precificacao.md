# Vinia SaaS — Sugestão de preços por custo previsto e margem real por cliente

**Data:** 2026-11-12 · **Autor:** sugestão do assistente para decisão do Rafael · **Status:** proposta (nada aqui foi implementado)
**Pedido do Rafael (2026-11-12):** "em relação ao preço, sugerir valores com base no custo previsto e margem de lucro real por cliente".
**Ponto de partida:** as hipóteses do "Plano de Implementação – Vinia SaaS" (PDF de 2026-11-10): Início R$ 147 (500 consultas, até 100 rótulos), Pro R$ 297 (2.000 consultas, rótulos ilimitados), Rede R$ 597 (6.000 consultas, até 3 unidades), com a meta de **margem bruta acima de 80% em cada plano**.

## 1. Resumo

1. **A IA é barata; o que a encarece é o tamanho da carta.** Hoje cada consulta manda a carta inteira no prompt: custa **R$ 0,0036** com 11 vinhos (medido), R$ 0,015 com 100, R$ 0,041 com 300 e R$ 0,067 com 500.
2. **Os preços do PDF fecham a meta de 80% se a carta tiver até ~100 rótulos** e o cliente usar a cota inteira. Com carta de 300 rótulos e cota cheia, o Pro cai para 68% de margem bruta e a Rede para 56%.
3. **A correção é de engenharia, não de preço:** mandar no prompt só uma pré-seleção de **até 40 vinhos** (filtrada por tipo, faixa de preço e o que a pessoa pediu) deixa a consulta em **R$ 0,0073 para qualquer carta**. Com isso os três planos ficam em **89% a 90% de margem bruta no pior caso** (cota cheia, carta de 300).
4. **Recomendação: manter R$ 147 / R$ 297 / R$ 597 e as cotas 500 / 2.000 / 6.000**, condicionado ao atalho de 40 vinhos na Fase 4. Os pisos de 80% de margem com o atalho são R$ 75 / R$ 133 / R$ 287: sobra folga de cerca de 2×, então o preço é decisão de posicionamento, não de custo.
5. **Margem real por cliente (uso típico, depois de imposto e suporte):** Início ≈ R$ 104 (70%), Pro ≈ R$ 226 (76%), Rede ≈ R$ 455 (76%). A infraestrutura inteira (R$ 280/mês) é paga por **1,2 clientes Pro ou 2,5 clientes Início**.
6. **Sem o atalho**, o caminho seguro é limitar os planos: Início até 100 rótulos (já no PDF), Pro até 150 rótulos (81%) e Rede com cota de 4.000 consultas e 150 rótulos por unidade (83%), em vez de "rótulos ilimitados".

## 2. Custo real da Sofia (medido no banco de desenvolvimento)

**Base:** 22 consultas concluídas (`ai_interactions`), restaurante La Vigne, **11 vinhos disponíveis**. Médias: `tokens_used` ≈ 2.700 por consulta (2.449 a 3.064), prompt de 7.100 a 8.100 caracteres, resposta de 560 a 1.860 caracteres. Cada vinho ocupa ≈ **515 caracteres** no prompt (5.663 caracteres para os 11).

**Como estimei os tokens (premissa, não medição):** 3,3 caracteres por token em português ⇒ ≈ 156 tokens de entrada por vinho; parte fixa de entrada ≈ 614 tokens; saída conservadora de 500 tokens (o modelo raciocina, e o raciocínio é cobrado como saída). Hoje o sistema grava só o total (`tokens_used`); a Fase 4 precisa gravar entrada e saída separadas para o custo ser exato.

| Vinhos na carta | Custo por consulta | Com cache de entrada (50%) | Com atalho de 40 vinhos |
|---|---|---|---|
| 11 (medido) | R$ 0,0036 | R$ 0,0026 | R$ 0,0036 |
| 60 | R$ 0,0099 | R$ 0,0058 | R$ 0,0073 |
| 100 | R$ 0,0150 | R$ 0,0083 | R$ 0,0073 |
| 200 | R$ 0,0279 | R$ 0,0148 | R$ 0,0073 |
| 300 | R$ 0,0408 | R$ 0,0212 | R$ 0,0073 |
| 500 | R$ 0,0665 | R$ 0,0341 | R$ 0,0073 |

## 3. Premissas e fontes (confirme as que dependem de contrato)

| Item | Valor usado | Fonte / observação |
|---|---|---|
| Modelo | `openai/gpt-oss-120b` na Groq: **US$ 0,15 por milhão de tokens de entrada e US$ 0,60 de saída**; entrada em cache com 50% de desconto | [Morph, Groq Pricing (out/2026)](https://www.morphllm.com/groq-pricing), [computeprices](https://computeprices.com/providers/groq/models/gpt-oss-120b); o lançamento (ago/2025) listava US$ 0,75 de saída, valor antigo ([Groq](https://groq.com/blog/day-zero-support-for-openai-open-models)) |
| Câmbio | **R$ 5,50 por US$** (fechamento de 9/11/2026: R$ 5,51) | [Brasil 61](https://brasil61.com/n/dolar-hoje-fecha-em-leve-alta-a-r-5-51-apos-oscilar-entre-queda-e-valorizacao-bras2617447); sensibilidade com R$ 6,50 |
| Gateway (Asaas) | Pix ou boleto **R$ 1,99** por cobrança; cartão **2,99% + R$ 0,49**; mistura assumida de 64% Pix/boleto e 36% cartão | [Asaas, preços](https://www.asaas.com/precos-e-taxas), [comparativo Quasa (out/2026)](https://quasa.io/pt/media/asaas-ou-iugu-tarifa-publicada-vence-ate-o-volume-pedir-proposta); promoção de 3 meses para novos clientes não considerada; **confirmar na sua conta** |
| Gateway (Stripe) | 3,99% + R$ 0,39 no cartão; Pix 1,19% (por convite) | só fontes de terceiros, **não confirmado** ([calculadora](https://sellfy.com/pt/ferramentas/calculadora-de-taxas-do-stripe/)); a taxa maior favorece o Asaas |
| Imposto | **6% da receita** (Simples Nacional, Anexo III, faixa inicial); sensibilidade 11,2% | **confirmar com a contabilidade** (RM Consultoria): faixa, fator R e anexo mudam o número |
| Infraestrutura fixa | R$ 75 a R$ 485 por mês (ponto médio R$ 280); rateio de R$ 9 por cliente (≈ 30 clientes) | tabela do PDF (VPS, banco, backup, e-mail, monitoramento, domínio) |
| Suporte e implantação | R$ 20 (Início), R$ 30 (Pro), R$ 60 (Rede) por cliente por mês | **hipótese** de horas valorizadas; não há dado |
| Uso | típico = 50% da cota com carta de 60 rótulos | **hipótese**: não há dado de produção (só 22 consultas em desenvolvimento) |

## 4. Margem por plano (preços do PDF, hoje, sem atalho)

Margem bruta = receita − IA − gateway − infraestrutura rateada. Contribuição = margem bruta − imposto (6%) − suporte.

| Plano | Cenário | IA | Bruta | Contribuição |
|---|---|---|---|---|
| Início R$ 147 | uso típico, carta 60 | R$ 2,47 | 90,1% | R$ 103,68 (70,5%) |
| Início | cota cheia, carta 100 | R$ 7,51 | 86,7% | R$ 98,63 (67,1%) |
| Início | cota cheia, carta 300 | R$ 20,38 | **77,9%** | R$ 85,76 (58,3%) |
| Pro R$ 297 | uso típico, carta 60 | R$ 9,88 | 92,1% | R$ 225,65 (76,0%) |
| Pro | cota cheia, carta 100 | R$ 30,05 | 85,3% | R$ 205,48 (69,2%) |
| Pro | cota cheia, carta 300 | R$ 81,53 | **68,0%** | R$ 154,00 (51,9%) |
| Pro | cota cheia, carta 500 | R$ 133,01 | **50,6%** | R$ 102,52 (34,5%) |
| Rede R$ 597 | uso típico, carta 60 | R$ 29,64 | 92,2% | R$ 454,67 (76,2%) |
| Rede | cota cheia, carta 100 | R$ 90,16 | 82,1% | R$ 394,14 (66,0%) |
| Rede | cota cheia, carta 300 | R$ 244,60 | **56,2%** | R$ 239,70 (40,2%) |
| Rede | cota cheia, carta 500 | R$ 399,04 | **30,3%** | R$ 85,26 (14,3%) |

**Com o atalho de 40 vinhos** (cota cheia, carta de 300): Início 89,3% bruta (contribuição R$ 102,50), Pro 90,5% (R$ 220,92), Rede 89,8% (R$ 440,48). A IA vira 2,5% (Início), 4,9% (Pro) e 7,3% (Rede) do preço; sem o atalho seria 13,9%, 27,5% e 41,0% (o alerta interno de 30% do PDF dispararia na Rede).

## 5. Recomendação

| | Início | Pro | Rede |
|---|---|---|---|
| **Preço mensal** | **R$ 147** | **R$ 297** | **R$ 597** |
| Cota da Sofia | 500 consultas | 2.000 consultas | 6.000 consultas |
| Limite de carta (com atalho) | sem limite prático | sem limite | até 3 unidades |
| Limite de carta (**sem** atalho) | até 100 rótulos | **até 150 rótulos** | **até 150 por unidade e 4.000 consultas** |
| Piso para 80% de margem, cota cheia, com atalho | R$ 75 | R$ 133 | R$ 287 |
| Margem real típica (após imposto e suporte) | ≈ R$ 104 | ≈ R$ 226 | ≈ R$ 455 |

- **Oferta de lançamento (−30% por 3 meses):** R$ 103 / R$ 208 / R$ 418 mantêm 85% a 87% de margem bruta e 60% a 67% de contribuição, mesmo com cota cheia e carta de 300 (com atalho).
- **Excedente (só plano ativo, como já decidido):** pacote de **500 consultas por R$ 49** (≈ R$ 0,098 por consulta). Lucro líquido de 75% (carta de 100) a 80% (carta de 60). Sem o atalho e com carta acima de 200 rótulos, **R$ 79**. O gestor continua definindo o limite em R$.
- **Trial de 14 dias:** teto de **150 consultas** custa R$ 2,25 (carta de 100); com 25% de conversão (hipótese), são **≈ R$ 9 por cliente que fecha**.
- **Alerta interno:** manter o de 30% do preço (do PDF); com o atalho ele quase nunca dispara.

## 6. Sensibilidade e riscos

- **Câmbio R$ 6,50 e imposto 11,2%** (pior caso plausível): Pro, cota cheia, carta de 100, cai de 69,2% para **62,1%** de contribuição. Segue saudável.
- **Ponto de equilíbrio da infraestrutura:** R$ 75 → 0,3 a 0,7 cliente; R$ 280 → 1,2 (Pro) a 2,5 (Início); R$ 485 → 2,1 a 4,3 clientes. O risco do negócio não é o custo da IA, é **ter clientes**.
- **O que mais pesa na margem real** são imposto e tempo de suporte, não a IA.
- **Risco de dado:** todo o uso "típico" é hipótese. Os primeiros 3 a 5 clientes devem ser medidos e esta tabela refeita.
- **Preço do modelo:** a Groq já mudou o preço de saída uma vez (US$ 0,75 → 0,60). O atalho e o cache protegem contra uma alta.

## 7. O que isso pede do produto (entra no plano da Fase 4)

1. **Atalho de prompt:** enviar à Sofia só uma pré-seleção de ≤ 40 vinhos (tipo, faixa de preço, perfil e pergunta), em vez da carta inteira. É a alavanca que mais protege a margem.
2. **Cache de entrada da Groq:** manter a carta (ou a pré-seleção estável) como prefixo idêntico entre consultas para ganhar o desconto de 50% na entrada.
3. **Medição (`ai_usage`):** gravar tokens de entrada e de saída separados e o custo calculado por consulta (hoje só o total), para o painel e o alerta de 30%.
4. **Teto de trial** de 150 consultas e o limite de rótulos por plano, se o atalho não vier antes do lançamento.

## 8. O que falta para fechar

- Confirmar **gateway e taxas reais** (Asaas ou Stripe) e o **regime tributário** com a contabilidade.
- Decidir se os planos limitam **rótulos** (sem atalho) ou se o atalho entra antes do lançamento.
- Confirmar as **horas de suporte** por plano e a infraestrutura escolhida (VPS ou Hostinger).
- Medir o **uso real** dos primeiros clientes e refazer o modelo.

*Cálculo reproduzível: `python3 docs/superpowers/specs/2026-11-12-vinia-saas-precificacao.py` (as entradas e fórmulas são as das seções 2 e 3; troque câmbio, imposto, taxas e uso no topo do script para refazer a tabela).*
