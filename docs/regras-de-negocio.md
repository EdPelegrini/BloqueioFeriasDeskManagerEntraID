# Regras de negócio

> Dados fictícios — ver aviso no [README](../README.md). Códigos de autocategoria, status, causa,
> operador e grupo variam por ambiente Desk Manager; os valores abaixo são só ilustrativos.

## Origem da solicitação

A solicitação de bloqueio nasce como um chamado aberto pela área de RH/Gestão de Pessoas no Portal
do Solicitante, sempre com:

- **Autocategoria:** `9001` — "TI · Acesso · Bloqueio por Férias" (fictício)
- **Campos extras do chamado:**

| Código (exemplo) | Campo | Formato |
|---|---|---|
| `9101` | Nome completo do colaborador | texto livre |
| `9102` | Matrícula do colaborador | texto (compara com `employeeId` no Entra ID) |
| `9103` | Período inicial das férias | `DD-MM-AAAA` |
| `9104` | Período final das férias | `DD-MM-AAAA` |

## Status usados no ciclo de vida do chamado

| Status (exemplo) | Nome | SLA | Quando entra |
|---|---|---|---|
| `000001` | Aguardando Atendimento | corre | Estado inicial, ao abrir o chamado |
| `000010` | Agendamento | **pausado** | Chamado aberto com início das férias no futuro |
| `000020` | Aguardando Retorno de Férias | **pausado** | Colaborador bloqueado, aguardando a data de fim |
| `000002` | Resolvido | encerrado | Colaborador desbloqueado, chamado fechado |

## Condições de decisão (avaliadas a cada varredura)

Para cada chamado da autocategoria de férias, com matrícula e as duas datas preenchidas:

| Condição | Ação |
|---|---|
| `hoje` já é posterior ao fim **e** o chamado está em "Aguardando Retorno de Férias" | **Desbloquear**: remove do grupo do Entra ID, fecha como Resolvido |
| `início ≤ hoje ≤ fim` **e** o chamado não está em "Aguardando Retorno de Férias" | **Bloquear**: adiciona ao grupo do Entra ID, revoga sessões, muda para "Aguardando Retorno de Férias" |
| `hoje` é anterior ao início **e** o chamado não está em Agendamento | **Agendar**: muda para "Agendamento" com a data de início (pausa o SLA) |
| `hoje` já é posterior ao fim **e** o chamado nunca chegou a ser bloqueado | **Finalizar fora de janela**: fecha como Resolvido sem mexer no grupo |
| Nenhuma das anteriores | Não faz nada (já está no estado correto) |

Chamados sem matrícula ou sem uma das duas datas são ignorados. Chamados fora da autocategoria de
férias também são ignorados (a varredura é ampla — todos os chamados em aberto — mas só age nos que
pertencem a esse processo).

A **varredura completa roda sempre**, inclusive quando o webhook informa qual chamado acabou de ser
aberto: esse chamado só é usado para decidir a quem avisar (ver *Alertas*). Só a varredura completa
tem a lista de abertos necessária para as travas de duplicidade e para a detecção de órfãos.

## Guardas de segurança

- **Ambiguidade de matrícula → nenhuma ação.** A matrícula é normalizada (remoção/adição de zeros à
  esquerda) e comparada com o campo `employeeId` de usuários no Microsoft Entra ID. Se o resultado
  trouxer **0 ou mais de 1** usuário, a automação não bloqueia nem desbloqueia ninguém — registra
  uma pendência para tratamento manual.
- **Falha no Graph → não muda status no Desk.** Se adicionar/remover do grupo ou revogar sessões
  falhar, o chamado permanece no status anterior. Isso evita que o Desk "diga" que o colaborador
  está bloqueado quando na verdade a chamada ao Entra ID falhou.
- **Falha ao revogar sessões não desfaz o bloqueio.** Se a inclusão no grupo funcionou mas a
  revogação de sessões falhar, o bloqueio segue em frente (o novo login já está impedido) e o
  problema fica registrado na observação interna do chamado, para acompanhamento da equipe.
- **Reautenticação a cada execução.** Cada rodada do Maestro obtém um token novo da API do Desk
  Manager e um novo token do Microsoft Graph — nenhum token é reaproveitado entre execuções.
- **Retry em erros transitórios.** Toda chamada ao Graph tenta até 4 vezes em throttling (429),
  502/503/504 e falha de rede, respeitando `Retry-After` (limitado a poucos segundos). Repetir é seguro:
  adicionar quem já é membro devolve "already exists", tratado como sucesso.

### Travas antes de bloquear ou agendar

Um pedido de **liberação** aberto na mesma autocategoria, ou um chamado com data digitada errada, não
pode ser tratado como pedido de bloqueio. Antes de bloquear ou agendar, a automação confere:

| Trava | Condição | Resultado |
|---|---|---|
| **A. Data muito antiga** | início anterior a 60 dias atrás | Não age; "REVISAR" (provável erro de digitação, ex.: ano trocado) |
| **B. Duplicidade** | outro chamado **aberto**, mais antigo, da mesma matrícula, com período sobreposto | Não age; "REVISAR" (possível pedido de liberação/cancelamento) |
| **C. Texto de liberação** | descrição ou assunto indicam "cancelar", "liberar", "não bloquear", "desconsiderar", etc. | Não age; "REVISAR" |

Na dúvida a automação **não age** e avisa. A decisão fica com uma pessoa.

### Membros órfãos do grupo

A cada varredura completa, a automação lista os membros do grupo de bloqueio e aponta quem **não é
justificado** por um chamado de férias aberto em "Aguardando Retorno" (nem foi bloqueado nesta
rodada). É o caso típico de um chamado fechado à mão com a pessoa ainda bloqueada. Esses casos entram
no alerta, e a automação **não remove ninguém sozinha**: a remoção por conta própria poderia liberar
alguém que deveria seguir bloqueado. A listagem só é considerada quando a lista de chamados abertos
veio inteira, para não gerar falso alarme.

## Alertas por e-mail

Um e-mail por execução (texto simples, via Graph `sendMail`) quando há algo que exige atenção:

- **Falhas da automação:** login no Desk recusado, listagem de chamados vazia, erro ao listar membros,
  erro por chamado (ex.: Graph recusou a operação).
- **Matrícula não resolvida** (0 ou mais de 1 usuário no Entra ID).
- **Chamados para revisão** (travas A, B e C).
- **Membros órfãos** do grupo.
- **Client secret perto de expirar** (30 dias ou menos).

**Sem repetir o mesmo alerta a cada abertura de chamado.** A automação não guarda estado entre
execuções, então a regra é por janela:

| Quando | O que vai no e-mail |
|---|---|
| **Rodada diária do cron** (03h–05h, horário local) | Resumo completo: tudo o que continua em aberto, mais o aviso do secret. Reenviado todo dia até ser resolvido. |
| **Demais execuções** (webhook, disparo manual) | Só **falhas gerais** (Desk/lista/membros) e os itens do **próprio chamado** que disparou o webhook (item novo). |

O e-mail registra no log quantos itens foram adiados para o resumo diário.

## Monitoramento

- **Batimento semanal.** Toda segunda, na rodada do cron, só se a varredura funcionou: um e-mail de
  "automação ativa" com chamados em aberto por situação, membros do grupo, órfãos, bloqueios e liberações
  dos próximos 7 dias e a validade do secret. **Se o e-mail deixar de chegar, a automação parou**: é o único
  jeito de perceber uma falha total silenciosa, já que com o Graph fora nem o alerta consegue sair.
- **Validade do client secret.** A automação lê no próprio registro do aplicativo a data de expiração da
  credencial em uso (localizada pelos 3 primeiros caracteres do segredo). Se a leitura falhar, só registra
  no log e não gera alerta.

## Ação Rápida "Liberar acesso agora"

Para o operador antecipar o retorno de quem já está bloqueado (ou cancelar um bloqueio agendado) **sem
entrar no Entra ID**. Fica em *Interação Avançada* do chamado de férias, para os grupos autorizados.

1. **Etapa 1 — confirmação.** Modal somente leitura com chamado, colaborador, matrícula, período,
   status, o que vai acontecer e quem está solicitando. Nada é alterado.
2. **Etapa 2 — execução.** (a) grava uma **nota de auditoria** no chamado (quem pediu, quando, e o
   período final antes/depois); (b) ajusta o **período final para ontem**; (c) aciona a varredura do
   Maestro principal, que remove do grupo (ou cancela o agendamento) e fecha o chamado **com todas as
   travas**.

A Ação Rápida **nunca mexe no Entra ID diretamente**: toda mudança de acesso continua passando pelo
mesmo código e pelas mesmas guardas. Limites: não atua em chamado já finalizado (orienta remover do
grupo; o alerta de órfãos cobre) e só recebe o *código* do operador, de onde resolve o nome pela API.
Para desfazer, basta restaurar o período original, registrado na nota.
