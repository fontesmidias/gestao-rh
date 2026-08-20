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
| **Documento de indeferido** | O expurgo já apaga documento de criança de quem foi indeferido, passado o prazo. Confirmar se o prazo geral (90 dias) serve, ou se este caso pede outro |
| **Declaração PF preenchida** | Hoje o sistema gera o modelo EM BRANCO. Gerá-la preenchida exigiria cadastrar o cuidador (nome, CPF, RG, endereço) e o valor por mês — vale? |
| **Retenção do áudio de entrevista** | Pendência da v2.97: quanto tempo o áudio fica antes do expurgo. A transcrição pode sobreviver ao áudio |

## 📋 Na fila

| O quê | Por quê | Origem |
|---|---|---|
| **Exigir o documento certo por PF/PJ** | O `tipo_comprovante` hoje é só rótulo na tela; poderia validar (PJ ⇒ nota fiscal, PF ⇒ declaração) | 23ª leva, item 4 |
| **Módulo de Recepção** | Aviso nasce no painel; webhook n8n como eco opcional; "sede" marcável | 22ª leva |
| **Ferramentas MCP** | Papel `automacao` e credencial existem (v2.94); faltam as ferramentas — cascas finas sobre `api/diagnostico.py`, que já responde 4 das 6 | 22ª leva |
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
