# Vinia SaaS — Fase 3: Onboarding self-service (design)

**Data:** 2026-11-13 · **Autor:** Rafael (decisões) + controlador (calls marcadas **[CALL]**)
**Status:** aguardando aprovação do Rafael (revisado pelo construtor em 2026-11-13; respostas do Rafael às duas perguntas incorporadas). Deriva do spec `2026-11-10-vinia-saas-design.md` (Fase 3, §6.1, §8) e das Stories 9.1 a 9.3 (multi-tenant, acesso por celular, retenção LGPD), já mergeadas na `main` local.

## 1. Intenção e por quê

Hoje o formulário da landing só envia um e-mail de aviso ao Rafael, que cria a conta do restaurante à mão. A Fase 3 transforma esse formulário na porta de entrada: um restaurante desconhecido se cadastra, valida o e-mail, monta a carta e convida a equipe, **sem ajuda do Rafael**. Meta do spec: carta publicada em **menos de 15 minutos**. Sem isso o Vinia não é vendável (spec §1).

## 2. Objetivos

1. Cadastro público (`/cadastro`) que cria o restaurante e o usuário dono, com verificação de e-mail.
2. Trial de 14 dias sem cartão, **travado por e-mail e por CPF/CNPJ**: quem já usou o teste vê que ele expirou.
3. Recuperação de senha por e-mail.
4. Assistente de 4 passos depois do login: (1) restaurante: nome, endereço público (`/r/<slug>`), logo e cores; (2) carta: importar CSV/Excel, partir da carta de exemplo ou deixar para depois; (3) acesso dos clientes: **no trial só o tablet** (instruções de pareamento); o acesso por celular (QR) aparece como recurso do plano assinado, com a explicação de risco/custo do spec §6.2; (4) equipe: convidar por e-mail (pode pular). Ao fim: carta pronta no tablet; o QR só existe no plano assinado.
5. Convite de equipe por e-mail, com o perfil novo `sommelier`.
6. E-mails transacionais (verificação, recuperação, convite, lembretes do trial nos dias 7, 12 e 14).
7. Carta de exemplo (poucos vinhos fictícios que o restaurante pode apagar de uma vez).

## 3. Não objetivos e anti-objetivos

**Não objetivos:** importação por **PDF/foto** (decisão do Rafael: fica para o plano assinado/premium, entra com a Fase 4, que dá cota e custo à IA); cobrança e gateway (Fases 4 e 5; o gateway será o Asaas); bloqueio por fim de trial e cota (Fase 4: a Fase 3 só registra datas e mostra os dias restantes); 2FA, multi-unidade, login do comensal; cadastro por Google/SSO.

**Anti-objetivos (seria falha mesmo funcionando):** um mesmo restaurante/pessoa conseguir vários testes de 14 dias; vazar ou guardar o CPF em claro; usuário sem e-mail verificado publicar a carta ou usar a Sofia; um usuário criado por convite ou cadastro virar `admin` da plataforma; um restaurante ver dados de outro.

## 4. Decisões do Rafael

- Plano de Implementação: Fase 3 depende só da 1; a produção fica na Hostinger compartilhada (sem Redis nem worker contínuo) e o deploy segue no **GitHub Actions** (`.github/workflows/deploy.yml`); domínio `vinia.ia.br`.
- O formulário de demonstração vira o cadastro: cadastra, valida o e-mail e acessa o self-service; **e-mail que já usou o teste recebe a mensagem de que o teste de 14 dias expirou**.
- **Acesso por celular (QR) fica desligado durante o trial** e só é liberado no plano assinado (premium); o dono não liga sozinho. No trial o restaurante usa o tablet; a Sofia fica limitada aos tetos já existentes do tablet.
- **Caso do CNPJ do passo 1 já usado em outro teste:** a conta é mantida, o teste nasce encerrado, o restaurante fica inativo e o dono entra, vê "seu teste de 14 dias expirou" e os dados preservados, para só assinar (Fase 5). Nada é apagado.
- **A trava vale por e-mail, por CPF ou CNPJ (a pessoa informa um dos dois) e também pelo CNPJ que o restaurante preencher no assistente**, porque quem inventa e-mails faria vários testes.
- PDF/foto fica para o premium (Fase 4 em diante).
- Abordagem **A**: Livewire dentro do backoffice atual, usando o `Auth` do Laravel (verificação de e-mail e recuperação de senha), sem SPA nova.

## 5. Abordagens consideradas

**A (escolhida):** `/cadastro` público e assistente em Livewire no backoffice, reaproveitando design system, importação CSV/Excel, tela de acesso por celular e tela de usuários. Menor custo, nenhum stack novo, um só login. **B:** SPA React separada: duplica autenticação e telas, e a Hostinger não tem Node. **C:** estender o formulário de demonstração: mistura lead com conta real e atrapalha a trava por documento.

## 6. Comportamento

**Cadastro.** Campos: nome do restaurante, nome do responsável, e-mail, senha, CPF **ou** CNPJ (dígitos validados). Resultados: (a) e-mail e documento inéditos: cria `restaurant` + usuário `owner`, registra o teste (ver §7), envia o link de verificação e leva ao assistente; (b) e-mail ou documento com teste em andamento: não cria nada, manda ao login (com "esqueci a senha"); (c) e-mail ou documento cujo teste já terminou: "Seu teste de 14 dias expirou" (a assinatura só existe na Fase 5; até lá a mensagem aponta para o contato do Rafael).

**Verificação.** Link assinado e com validade. O trial de 14 dias **começa na verificação** **[CALL]**, não no cadastro. Antes de verificar, a pessoa percorre o assistente, mas **o restaurante fica inativo (carta e Sofia fora do ar) até a verificação** **[CALL]**; um aviso fixo pede a verificação, com botão de reenviar (limitado).

**Carta de exemplo [CALL].** ~10 vinhos fictícios, marcados como exemplo, que o restaurante remove com uma ação ("Remover vinhos de exemplo"); nunca aparecem como vinho real depois disso.

**Convite de equipe [CALL].** O dono/gerente convida por e-mail com perfil `manager` ou `sommelier`; o link é assinado, vale 7 dias, define a senha e já entra no restaurante de quem convidou. O usuário continua em **um** restaurante só (spec §7). O perfil `sommelier` é novo; o que ele pode ou não fazer (sugestão: ver e editar vinhos, sem usuários, planos nem acesso por celular) é detalhado no plano.

**Landing [CALL].** O CTA "Testar 14 dias grátis" e o formulário apontam para `/cadastro`. O model e a lista de `DemoRequest` ficam como histórico no painel de admin; a rota antiga `POST /demonstracao` sai depois da troca.

## 6.1 Calls do controlador após a revisão do construtor

- **"Publicar"** não cria estado novo: o restaurante nasce com `active = false` e a verificação do e-mail liga o `active`. No trial a carta serve só o tablet; o acesso público por celular só existe no plano assinado.
- **Cadastro não verificado não trava e-mail nem documento:** o registro da trava nasce na verificação (quando o trial começa); cadastros não verificados são apagados após 7 dias.
- **Restaurantes criados à mão pelo Rafael:** sem registro de trial, sem lembretes, sem bloqueio; nada muda para eles.
- **Trial x `subscriptions`:** a Fase 3 guarda as datas no registro do trial; a Fase 4 cria `subscriptions` a partir dele.
- **Equipe:** o dono convida gerente ou sommelier, desativa usuários e troca perfis do próprio restaurante, exceto o seu; o gerente só convida sommelier. Reusar a tela de usuários com escopo por restaurante ou criar uma tela "Equipe" fica com o construtor, com testes A×B.
- **Convite para e-mail que já tem conta ou trial:** resposta igual à de qualquer convite ("se puder ser convidado, enviamos"), sem revelar existência de conta.
- **Detalhes:** hash do CPF com chave própria no `.env` (trocar a `APP_KEY` não quebra a trava); o CNPJ do cadastro preenche `restaurants.cnpj`; o expurgo LGPD da Story 9.3 não toca a tabela do trial.

## 7. Trava do teste [CALL no mecanismo]

- Tabela de registro do teste (nome à escolha do construtor), **guardada mesmo que a conta seja apagada**: e-mail normalizado (minúsculas; no Gmail, sem pontos e sem `+tag`), tipo e **hash** do documento, `restaurant_id`, início e fim do teste. Sem ela a regra não se sustenta. Retenção e base legal (prevenção de fraude) a registrar no aviso de privacidade da Fase 7.
- **CPF:** só o hash (HMAC com segredo do servidor, `APP_KEY` ou chave própria), nunca o número. **CNPJ:** pode ficar em claro (dado de empresa, já existe em `restaurants.cnpj`).
- Ao informar o CNPJ no passo 1 do assistente, o sistema confere esse CNPJ no registro também: se já teve teste, o teste dessa conta nasce encerrado e o restaurante fica inativo (ver §4), sem apagar nada.
- **Limite aceito:** CPF/CNPJ válidos mas inventados passam (não há prova de posse); a verificação forte fica para quando houver cobrança (Fase 5).
- A mensagem de "teste expirou" revela que o e-mail/documento já existe (enumeração). É uma troca assumida pelo Rafael; as demais respostas de cadastro e de recuperação de senha **não** revelam a existência de conta.

## 8. Restrições

Hostinger compartilhada: **sem `schedule:run` nem worker contínuo**. A fila roda por cron de 1 minuto (já existe); os e-mails de verificação/convite/recuperação vão pela fila (até ~1 min de atraso) e os **lembretes do trial (dias 7, 12 e 14) pedem um cron diário direto no hPanel**, como o do expurgo (Story 9.3). SMTP: o configurado hoje (`MAIL_*`); SPF, DKIM e DMARC do domínio são pré-requisito de entregabilidade (Fase 6/7). Seguir o fluxo AIOX (stories em `vinia-docs`, push e PR só do @devops), suíte verde em SQLite **e** MySQL 8, isolamento multi-tenant (testes A×B) e `RawQueryAuditTest`. Limites de taxa em cadastro, reenvio de verificação, recuperação de senha e convite. Cadastro e convite **nunca** criam `admin`; o `role` não pode vir do formulário (mass assignment).

## 9. Sucesso

Um restaurante novo, sozinho, sai do formulário com a carta publicada e o QR em menos de 15 minutos; o mesmo e-mail, CPF ou CNPJ não ganha segundo teste; nenhum CPF em claro no banco ou nos logs; suíte verde.

## 10. Deixado ao construtor

Nomes de tabelas/colunas, tela e copy do assistente, texto dos e-mails, lista exata da carta de exemplo, matriz fina de permissões do `sommelier`, forma do segredo do hash de CPF, estrutura das stories e a ordem das Tasks.
