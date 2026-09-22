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
| **24ª leva — 6 perguntas em aberto** | Banco da conta salário (um por posto?) · marco dos "5 dias úteis" do VT · termo de VT de quem ainda não está na base · quais movimentações o módulo cobre e quem aprova · base legal do RG/filiação no cadastro público · certificado de quê e quem assina. **Não bloqueiam a Onda 1.** Ver `19-feedbacks-24a-leva.md` | 24ª leva |

## 🤔 A decidir

| Tema | A pergunta |
|---|---|
| **Retenção do áudio de entrevista** | Hoje o áudio da entrevista gravada fica no servidor **para sempre**. A transcrição em texto pode sobreviver a ele. Por quantos meses guardar o áudio antes do expurgo? (pendência da v2.97 — o Bruno pediu para reformular a pergunta) |

## 📋 Na fila

| O quê | Por quê | Origem |
|---|---|---|
| **24ª leva — Ondas 2 a 5** | Módulo de assinaturas (o documento **não é disparado a ninguém** ao concluir — confirmado no código) · conta salário por posto · prazos de VT/VA customizáveis · Banco de Talentos configurável · MCP utilizável · 3 módulos novos (Termo de VT, movimentação funcional, certificados) | 24ª leva |
| **Stack do Portainer × arquivo do repo** | A stack de produção é uma CÓPIA colada e não se atualiza sozinha — em 22/09 ela estava sem `creche_lembretes` (nunca rodou na VPS) e sem a rede do e-mail. Já cobrou 5 vezes. A defesa real é o Portainer puxar do git (ele suporta), em vez da cópia manual | 22/09 |
| **Ambiente de homologação para o assistente** | O Bruno ofereceu acesso por `.env` para eu validar telas com dados reais (a v3.21 foi medida com 7 cargos; a base tem 111). Faltam 3 decisões: dados reais ou fictícios · leitura ou escrita · qual papel | 22/09 |
| **Declaração PF pré-preenchida** | **Decidido pelo Bruno (19/08/2026)**: *"tem que vir pré-preenchida com os dados já mapeados em relação ao filho do colaborador"*. Hoje o sistema gera o modelo EM BRANCO. O que já existe: nome do colaborador, CPF, e nome + data de nascimento da criança. ⚠️ O que **falta** e o modelo do Dr. Lucas pede: nome, CPF, RG e endereço do CUIDADOR, e o valor pago no mês — esses precisam ser coletados (decidir se por criança, uma vez, ou a cada competência) | 23ª leva |
| **Módulo de Recepção** | Aviso nasce no painel; webhook n8n como eco opcional; "sede" marcável | 22ª leva |
| **Lote-piloto de 50 currículos** | O MCP já cadastra talento (v3.14). Falta a primeira rodada medida: 50, taxa de acerto, ajuste — antes de pensar nos 14 mil. ⚠️ O intervalo de datas é parâmetro do RH, nunca constante, e vai para a auditoria. **`13-mcp-do-portal.md` § 7** | 22ª leva |
| **Testar o assistente na homologação** | O OAuth está pronto (v3.15). Falta ⏸️ **definir `MCP_ISSUER`** no `.env` e **atualizar a homologação** (roda a v3.09) — só então dá para adicionar o conector e fazer o teste real. Guia: **`mcp/CONECTAR.md`** | v3.15 |
| **MCP: as 2 a 5 pessoas conectarem** | Depois do teste na homologação. Só o uso real dirá se as descrições fazem o modelo escolher a ferramenta certa | v3.14 |
| **MCP: as escritas que faltam** | Convidar candidato, aprovar documento, marcar entrevista — o papel `assistente_rh` já tem a permissão, falta a casca. Uma a uma. **`18-mcp-servidor.md`** | 19/08/2026 |
| **Transcrição no módulo de Arquivo** | Hoje só aparece no card da entrevista | § 11 do doc 14 |
| **Dados da empresa vindos do banco** | Tirar contato/telefone/site do código; a tela de Marca já existe. ⚠️ O **contato do rodapé** dos e-mails já saiu do código (v3.22, editável em Config → E-mail) — este item é o que falta nos DOCUMENTOS | 2026-08-08 |

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

### 27ª leva (2026-09-22) — v3.21 → v3.25
**O dia em que três coisas quebraram por credencial ou referência inválida.**
Começou com o pedido de juntar a importação de cargos (que estava em três
telas) e terminou com o portal de produção sem e-mail nenhum.

- **v3.21 — Cargos num lugar só.** Orientação (o passo a passo do Tirvu, que só
  existia no WhatsApp) → importar em lote → conferir e cadastrar um a um. Com o
  CRUD unitário que faltava e o `cbo` que o cadastro à mão nunca gravava.
- **v3.21.1 — MinIO.** O Docker Hub passou a recusar o pull anônimo e o CI
  morria em 8s, antes de qualquer teste. A instrução certa (`quay.io`) já estava
  no CLAUDE.md e não alcançava os arquivos de deploy.
- **v3.22 — A cadeia de e-mail.** A caixa que autenticava o M365 foi extinta; o
  `refresh_token` morto no banco fazia `return False` e **bloqueava** Google,
  webhook e SMTP. Credencial inválida é pior que credencial nenhuma. Junto,
  o rodapé "não responda" nos 48 templates.
- **v3.23 — O cargo invisível e a porta do SMTP.** Defeito meu da v3.21: o
  seletor lia outra fonte, então cargo recém-cadastrado não aparecia em
  Admissões. E a cifra do SMTP passou a depender da porta (465 → `SMTP_SSL`),
  que é o que destravou o timeout de 30s.
- **v3.24 — O formulário que brigava com quem digitava.** Uma candidata levou
  **12 recusas 422 em 4 minutos**: o autosave mandava meia linha e o CPF era
  acusado a cada tecla.

- **v3.25 — O sistema avisa quando o e-mail para.** A outra metade: a cadeia
  não parava mais, mas ninguém ficava sabendo quando nenhum provedor entregava.
  Resolvido reusando o vigia que já roda a cada 15 min — ~40 linhas, nenhum
  container novo.

Fica a regra que liga as três: **credencial ou referência inválida bloqueia o
caminho que funcionaria sem ela** — e o erro nunca fala disso.

### 26ª leva (2026-09-02) — v3.17 → v3.20 — Onda 1 da 24ª leva
Os 6 itens decididos da Onda 1, todos entregues:
**exportar respeitando a seleção** (a planilha ia para a folha de pagamento com
gente que ninguém marcou, sem nada denunciando) · **as 34 colunas do Tirvu**
(modelo novo do fornecedor; as 6 novas são opcionais e já eram coletadas) ·
**o "?" invisível no tema escuro** (1,13:1 de contraste, medido) ·
**autodeclaração de residência pela ficha** · e os dois itens de tela do
Épico 2.

### 25ª leva (2026-08-27) — v3.16 → v3.16.1
**O requerimento de creche que não chegava a quem tinha de assinar.** Relato do
Bruno sobre os benefícios já aprovados e ativados. O roteiro **existia no
banco**: quem mentia era a consulta — `tem_roteiro` devolve o documento mais
recente de QUALQUER tipo, e o creche comparava a origem depois, em Python; quem
foi efetivado tem roteiro de admissão mais novo, e a sessão do colaborador
respondia `disponivel: false` com o requerimento pronto ao lado. Nada dava
erro, e o log registrava 200.

O conserto veio com a porta que faltava: o disparo vivia SÓ dentro do
`ativar_beneficio`, num `except` cujo evento nenhuma tela mostrava — quem
ficasse sem o roteiro não tinha rota nem botão. Agora o benefício ativo sem
requerimento é **acusado na ficha**, com disparo individual, varredura em lote
(que nomeia quem falhou) e envio da declaração-modelo anexa ao e-mail.

Fica a regra geral: **consulta que devolve "o mais recente de qualquer tipo" e
filtra depois responde sobre o documento errado** — filtre a espécie no SQL, e
use constante para o valor, porque string errada não dá erro: devolve "não
existe".

**v3.16.1, no mesmo dia:** o Bruno mandou um print mostrando que a correção
estava pela metade. A ficha dizia "Liberado — aguardando a assinatura",
**sem botão de enviar o requerimento**, e o lote respondia que já havia sido
enviado — sem ter enviado para ninguém. A v3.16 tratou *"o roteiro existe"*
como *"a pessoa foi avisada"*, e quem foi ativado antes dela tinha o documento
sem nunca ter recebido e-mail (o aviso não existia). Agora as rotas garantem as
duas coisas, o botão aparece enquanto couber cobrar, a ficha mostra a data do
último aviso e o lote separa "documento criado" de "cobrança reenviada".

Segunda regra da leva: **ter o registro não é saber que ele existe** — ao
escrever reprocessamento, separe *o artefato existir* de *a pessoa ter sido
avisada*, e carimbe o aviso só quando o envio dá certo.

Terceira, achada porque o TESTE travou: **ação em lote que manda e-mail é
trabalho de fila**. Medido, 951ms por e-mail contra 4ms de consulta — com 157
ativos são ~2,5 min contra os 60s do corte do nginx, e o sintoma em produção
seria "erro de rede" com metade dos e-mails já enviados. A varredura foi para o
`worker` que já existia (fila `default`, sem mudança de deploy), com o
relatório guardado para não sumir quando alguém fecha a aba.

### 24ª leva (2026-08-19/20) — v3.11 → v3.15
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

Na v3.15 o OAuth voltou e virou o caminho principal, depois de o Bruno
perguntar por que a nossa instalação dá trabalho se nas outras plataformas
basta clicar e autenticar. Conectar passou a ser adicionar o endereço e fazer
login — sem instalar nada, sem token para colar, e funcionando pelo navegador e
no celular.

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
