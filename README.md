# Bloqueio de Férias — Automação Desk Manager + Microsoft Entra ID

> ⚠️ **Dados fictícios.** Nomes de empresa, colaboradores, matrículas, IDs de tenant/aplicativo,
> chaves de Maestro/Cron/Webhook, e-mails e códigos de status usados neste repositório são de exemplo.
> Nenhum valor aqui corresponde a um ambiente real. Substitua tudo pelos códigos do seu próprio
> ambiente antes de usar.

## O que essa automação faz

Quando um colaborador entra de férias, a área de TI precisa bloquear o acesso dele aos sistemas
durante o período e liberar automaticamente no retorno. Este repositório documenta um **Maestro**
(motor de automação/iPaaS da plataforma [Desk Manager](https://desk.ms)) que:

1. Lê os chamados de solicitação de bloqueio por férias (autocategoria dedicada).
2. No início do período: adiciona o colaborador a um **grupo do Microsoft Entra ID** que bloqueia
   o acesso, **revoga as sessões abertas** dele (Microsoft Graph) e muda o status do chamado.
3. No fim do período: remove o colaborador do grupo e fecha o chamado como Resolvido.
4. Roda **duas vezes**: por um **cron diário** (rede de segurança) e por um **webhook** disparado
   na hora em que o chamado é aberto (tratamento imediato, evita estourar SLA).
5. **Não age no escuro:** travas contra pedido duplicado, de liberação ou com data errada; detecção de
   pessoas no grupo sem chamado que as justifique; matrícula ambígua vira pendência, nunca ação.
6. **Avisa quando algo exige atenção** por e-mail (Microsoft Graph `sendMail`), manda um **batimento
   semanal** de prova de vida e **monitora a validade do client secret** do aplicativo no Entra ID.
7. Oferece uma **Ação Rápida "Liberar acesso agora"** para o operador antecipar o retorno de um
   colaborador direto pelo chamado, sem entrar no Entra ID, com auditoria no próprio chamado.

## Estrutura deste repositório

```
├── README.md                        # este arquivo
├── docs/
│   ├── arquitetura.md               # diagramas e como as peças se encaixam
│   └── regras-de-negocio.md         # status, campos, decisões, travas, alertas e Ação Rápida
└── src/
    ├── parse_registrar.py           # bloco Python do Maestro principal (sanitizado, sem segredos)
    └── parse_liberar_agora.py       # bloco Python da Ação Rápida "Liberar acesso agora" (sanitizado)
```

## Stack

- **Desk Manager** — plataforma de service desk/ITSM que hospeda os Maestros, o cron, o webhook e
  a Ação Rápida (Interação Avançada).
- **Microsoft Graph API** — adicionar/remover o usuário do grupo de bloqueio, revogar sessões
  (`revokeSignInSessions`), listar membros do grupo, enviar os e-mails de alerta (`sendMail`) e ler a
  validade do client secret do próprio aplicativo.
- **Python** (bloco nativo do Maestro, runtime gerenciado pela plataforma) — usa `requests` para
  chamar a API do Desk Manager e o Graph.

## Segurança

- Nenhuma credencial fica no código do Maestro: elas ficam em **Constants** do próprio Maestro
  (`CST_*`), fora do fluxo versionado. Neste repositório não há valor real de chave ou segredo.
- Permissões de aplicativo no Entra ID (com consentimento de administrador):
  `GroupMember.ReadWrite.All`, `User.Read.All` e `User.RevokeSessions.All` para o bloqueio, e
  `Mail.Send` para os alertas.
- **Restrinja o `Mail.Send`.** Por padrão essa permissão de aplicativo permite enviar e-mail como
  *qualquer* caixa do tenant. Limite-a à caixa de alertas com uma
  [Application Access Policy](https://learn.microsoft.com/graph/auth-limit-mailbox-access) no Exchange Online.
- A leitura da validade do secret (`applications`) é opcional: se a permissão não existir, a automação
  só registra o fato no log e segue.
- Ver `docs/regras-de-negocio.md` para o detalhe de cada trava (ex.: nunca agir se a matrícula casar com
  mais de um usuário no Entra, nem se o chamado parecer pedido de liberação).

## Licença

Uso interno / exemplo educacional. Adapte livremente para o seu ambiente.
