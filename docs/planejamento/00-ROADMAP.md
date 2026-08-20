# 🗺️ Roadmap — o que está em fila, o que falta, o que ficou decidido

> **Este documento é atualizado A CADA VERSÃO.** Não é opcional: é o mesmo
> contrato do CHANGELOG e do README (regra de 2026-07-29). Fechar uma versão
> sem mexer aqui deixa a fila descrevendo um passado — e a fila só serve para
> responder *"o que vem agora?"*.
>
> **Numerado `00-` de propósito**: aparece primeiro na pasta, porque é por onde
> se começa.

## Como ler os status

| Status | O que significa |
|---|---|
| ✅ **Entregue** | Está no `main`, com CI verde e a versão anotada |
| 🔨 **Em desenvolvimento** | Alguém está mexendo agora |
| 📋 **Na fila** | Decidido e especificado — pode começar |
| ⏸️ **Bloqueado** | Depende de uma decisão ou de um insumo externo (diz qual) |
| 🤔 **A decidir** | Falta uma escolha do Bruno antes de virar fila |
| 🧊 **Descartado** | Avaliado e recusado — fica registrado com o motivo, para não voltar por engano |

---

## ⏸️ Bloqueado — precisa de você

| O quê | O que destrava | Desde |
|---|---|---|
| **Comunicado da data de corte** | Decidir QUANDO disparar. O padrão foi corrigido para dia 25, mas quem foi ativado antes recebeu "envie até o dia 5" por e-mail | v3.02 |
| **Validar a 23ª leva na homologação** | Olhar as telas novas e dizer se está bom | v3.09 |

## 🤔 A decidir

| Tema | A pergunta |
|---|---|
| **Retenção do áudio de entrevista** | Hoje o áudio da entrevista gravada fica no servidor **para sempre**. A transcrição em texto pode sobreviver a ele. Por quantos meses guardar o áudio antes do expurgo? (pendência da v2.97 — o Bruno pediu para reformular a pergunta) |

## 📋 Na fila

| O quê | Por quê | Origem |
|---|---|---|
| **Declaração PF pré-preenchida** | **Decidido pelo Bruno (19/08/2026)**: *"tem que vir pré-preenchida com os dados já mapeados em relação ao filho do colaborador"*. Hoje o sistema gera o modelo EM BRANCO. O que já existe: nome do colaborador, CPF, e nome + data de nascimento da criança. ⚠️ O que **falta** e o modelo do Dr. Lucas pede: nome, CPF, RG e endereço do CUIDADOR, e o valor pago no mês — esses precisam ser coletados (decidir se por criança, uma vez, ou a cada competência) | 23ª leva |
| **Módulo de Recepção** | Aviso nasce no painel; webhook n8n como eco opcional; "sede" marcável | 22ª leva |
| **🔨 MCP remoto com OAuth — EM DESENVOLVIMENTO** | Papel `assistente_rh` pronto (v3.13). ⚠️ **Obstáculo achado em 20/08**: o Claude na WEB só conecta connector remoto por **OAuth** — não aceita o token `mcp_…` num header (pedido fechado como "not planned" pela Anthropic). Como o uso é pelo Coworking no navegador, o portal precisa virar authorization server: `.well-known`, `/register` (RFC 7591), `/authorize`, `/token` com PKCE. Desenho em `17-mcp-oauth.md`. **Alternativa mais barata que continua válida**: Claude Desktop com o token que já existe | Papel `assistente_rh` criado na v3.13 (14 permissões, sem nada irreversível/dinheiro/config). **Falta**: o servidor MCP em si e as ferramentas. | Papel `automacao` e credencial existem (v2.94); faltam as ferramentas. ⚠️ **O uso mudou** (Bruno, 19/08/2026): não é só a Claude dele — são os **colaboradores do RH no Claude Coworking**, executando tarefas no portal por prompt. Isso muda o desenho: deixa de ser uma credencial de máquina para uma pessoa e passa a ser **várias pessoas agindo pelo MCP**, o que traz de volta as perguntas de AUTORIA (quem fez o quê) e de PERMISSÃO (o papel `automacao` tem 4 permissões de diagnóstico — insuficiente se eles forem *executar tarefas*). Ler `docs/planejamento/13-mcp-do-portal.md` e as ressalvas do CLAUDE.md sobre o papel `automacao` antes de desenhar | 22ª leva |
| **Transcrição no módulo de Arquivo** | Hoje só aparece no card da entrevista | § 11 do doc 14 |
| **Dados da empresa vindos do banco** | Tirar contato/telefone/site do código; a tela de Marca já existe | 2026-08-08 |

## 🧊 Descartado (com o motivo — não ressuscitar por engano)

| O quê | Por que não |
|---|---|
| **Módulo genérico de "competência mensal"** | Abstração que ninguém pediu; atrasaria a obrigação legal do creche. O que morde aqui é falha SILENCIOSA, não código difícil de ler. Se surgir uma segunda entrega periódica, generaliza-se com dois casos reais na mão |
| **Migrar para Docker Swarm** | Medido: réplicas quebrariam o rate limit em memória e a idempotência, e o `alembic upgrade` correria em paralelo. Se crescer, o caminho é k3s |
| **Mutirão de refatoração (SOLID)** | A modularização está boa; refatorar amplamente mexeria em código que funciona sem pagar o que de fato morde |

---

## ✅ Entregue — histórico por leva

O detalhe de cada versão está no `CHANGELOG.md`. Aqui fica só o mapa.

**Vigência dos 5 contratos** — o Bruno lançou as datas na tela em 19/08/2026
(ANEEL, INEP ×2, MAPA, PREPÚBLICA). O ciclo mensal passa a marcar corretamente
competência anterior à vigência.

### 23ª leva (2026-08-18/19) — v3.01 → v3.10
**Os 13 feedbacks do Bruno.** Ciclo mensal do creche completo (modelo, regras,
as duas portas, multi-folhas, worker de lembrete configurável, telas), vigência
por contrato, matrícula de 6 dígitos, nomes de download padronizados, dedup no
Banco de Talentos, currículo obrigatório, creche nas telas de Colaboradores e
Admissões, CRUD de jornada, tela de credenciais de automação, e o expurgo do
creche — que nunca havia existido.

Cinco defeitos encontrados sem terem sido pedidos: o e-mail prometia entrega
mensal sem porta para recebê-la; dizia "dia 5" com o Jurídico definindo dia 25;
`999001` seria lida como matrícula nossa e invadiria a numeração do Tirvu; a
tela dizia "Cadastro recebido!" com o currículo não enviado; e certidão de
criança indeferida ficava no storage para sempre.

### Levas anteriores
Ver `CHANGELOG.md` e os documentos `docs/planejamento/`.

---

## Ao fechar uma versão, atualize aqui

1. Mova o que entregou de 📋/🔨 para ✅, com o número da versão.
2. Se algo virou bloqueio, registre **o que destrava** — "pendente" sem dizer de
   quem depende é uma linha que ninguém resolve.
3. Se descartou uma ideia, escreva **por quê**. Ideia descartada sem motivo
   volta na leva seguinte e gasta a discussão de novo.
