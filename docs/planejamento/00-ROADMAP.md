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
| **Lote-piloto de 50 currículos** | O MCP já cadastra talento (v3.14). Falta a primeira rodada medida: 50, taxa de acerto, ajuste — antes de pensar nos 14 mil. ⚠️ O intervalo de datas é parâmetro do RH, nunca constante, e vai para a auditoria. **`13-mcp-do-portal.md` § 7** | 22ª leva |
| **🔨 MCP remoto com OAuth — EM CONSTRUÇÃO** | **Decisão do Bruno (20/08/2026)**, ao ver o guia de instalação: *"geralmente só clico dentro da plataforma, ele pede para autenticar com o Claude e já funciona. Por que isso não vai no nosso?"*. É o único caminho em que ninguém cria nem cola credencial — e o único que funciona pelo NAVEGADOR e no CELULAR, sem exigir o Desktop. As 5 ferramentas, a máscara de CPF e o papel `assistente_rh` são reaproveitados; troca-se a porta de entrada. **`17-mcp-oauth.md`** | v3.14 |
| **MCP: instalar com as 2 a 5 pessoas** | ⏸️ Esperando o OAuth — com ele, "instalar" vira clicar e autorizar | v3.14 |
| **MCP: as escritas que faltam** | Convidar candidato, aprovar documento, marcar entrevista — o papel `assistente_rh` já tem a permissão, falta a casca. Uma a uma. **`18-mcp-servidor.md`** | 19/08/2026 |
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

### 24ª leva (2026-08-19/20) — v3.11 → v3.14
**O MCP saiu do papel.** O papel `assistente_rh` (v3.13) e, na v3.14, as
seis ferramentas registradas e funcionando no Claude Desktop — cascas finas
sobre rotas que já existiam. O OAuth foi arquivado de manhã (todos têm o
Desktop, que aceita o token `mcp_…`) e **desarquivado à tarde**, quando o Bruno
perguntou por que a nossa instalação dá trabalho se nas outras plataformas basta
clicar e autenticar. O arquivamento respondia *"dá para funcionar?"*; a pergunta
certa era *"por que a nossa é a única que dá trabalho?"*.

Dois achados: o SDK renomeou `FastMCP` para `MCPServer` na 2.0, e só o teste
que SOBE o servidor pegou; e a defesa contra prompt injection precisou ser
copiada para o pacote do desktop — com um teste comparando as duas, porque
cópia sem quem a cubra envelhece torta e em silêncio.

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
