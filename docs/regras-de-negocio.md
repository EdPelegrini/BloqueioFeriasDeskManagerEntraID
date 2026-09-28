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
| Nenhuma das anteriores | Não faz nada (já está no estado correto) |

Chamados sem matrícula ou sem uma das duas datas são ignorados. Chamados fora da autocategoria de
férias também são ignorados (a varredura é ampla — todos os chamados em aberto — mas só age nos que
pertencem a esse processo).

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
