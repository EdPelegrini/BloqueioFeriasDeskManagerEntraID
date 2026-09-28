# Bloqueio de Férias — Automação Desk Manager + Microsoft Entra ID

> ⚠️ **Dados fictícios.** Nomes de empresa, colaboradores, matrículas, IDs de tenant/aplicativo,
> chaves de Maestro/Cron/Webhook e códigos de status usados neste repositório são de exemplo.
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

## Estrutura deste repositório

```
├── README.md                        # este arquivo
├── docs/
│   ├── arquitetura.md               # diagrama e como as peças se encaixam
│   └── regras-de-negocio.md         # tabela de status, campos, condições de bloqueio/desbloqueio
└── src/
    └── parse_registrar.py           # bloco Python do Maestro (sanitizado, sem segredos)
```

## Stack

- **Desk Manager** — plataforma de service desk/ITSM que hospeda o Maestro (fluxo de automação),
  o cron e o webhook.
- **Microsoft Graph API** — para adicionar/remover o usuário do grupo de bloqueio e para revogar
  sessões (`revokeSignInSessions`).
- **Python** (bloco nativo do Maestro, runtime gerenciado pela plataforma) — usa `requests` para
  chamar a API do Desk Manager e o Graph.

## Segurança

- Nenhuma credencial fica no código do Maestro: elas ficam em **Constants** do próprio Maestro
  (`CST_*`), fora do fluxo versionado.
- O app registrado no Entra ID precisa de permissão de aplicativo `GroupMember.ReadWrite.All` e
  `User.RevokeSessions.All` (Application permissions, com consentimento de administrador).
- Ver `docs/regras-de-negocio.md` para o detalhe de cada guarda de segurança (ex.: nunca agir se a
  matrícula casar com mais de um usuário no Entra).

## Licença

Uso interno / exemplo educacional. Adapte livremente para o seu ambiente.
