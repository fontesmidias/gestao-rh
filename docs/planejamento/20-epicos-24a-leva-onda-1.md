# 20 — Épicos e histórias da 24ª leva (Onda 1)

> **Origem.** Derivado de `19-feedbacks-24a-leva.md` (SPEC + 4 anexos) com
> `bmad-create-epics-and-stories`, em 02/09/2026. O SPEC é o contrato; este
> documento é a decomposição da **Onda 1** em épicos e histórias implementáveis.
>
> **Este é o rastro que o item 14 pediu, um nível abaixo do SPEC.** Ele responde
> "o que exatamente construir agora, e como saber que ficou pronto".
>
> A área de trabalho do BMad fica em `_bmad-output/planning-artifacts/epics.md`
> (não versionada); **este arquivo é a cópia canônica versionada**. Ao atualizar,
> re-derivar lá e republicar aqui.
>
> **Levantado no código real** (02/09/2026): cada história aponta para arquivo e
> linha conferidos, não para suposição. Onde o anexo `achados-no-codigo.md` já
> rastreou a causa, a história a cita em vez de mandar redescobrir.

---

## Overview

Decomposição da Onda 1 da 24ª leva. O contrato é `docs/planejamento/19-feedbacks-24a-leva.md`
(SPEC + 4 anexos), validado por preservação. As Ondas 2 a 5 ficam registradas no SPEC e
não entram aqui — este documento cobre apenas as capacidades da Onda 1 já decididas.

Cada história aponta para arquivo e linha levantados no código real (02/09/2026), não
para suposição. Onde o anexo `achados-no-codigo.md` já rastreou a causa, a história a
cita em vez de mandar redescobrir.

## Requirements Inventory

### Functional Requirements

FR1 (CAP-2): Exportar entrega exatamente as pessoas marcadas na tela; sem marcação, entrega
exatamente quem os filtros da tela mostram. Exportar é ação em massa, ao lado de efetivar e
desligar — não um botão de cabeçalho que desconhece a seleção.

FR2 (CAP-2b): ADIADO pelo Bruno em 02/09/2026 — *"não quero mais, outro dia trataremos isso
melhor"*. A capacidade continua no SPEC e sai da Onda 1 sem desenho definido: nenhuma das
formas propostas (filtro na barra, coluna de destino, esconder importados por padrão) foi
aceita. Não implementar por conta própria; retomar com o Bruno.

FR3 (CAP-3): A tela de Admissões oferece exportação com o mesmo contrato de FR1, com o
controle junto das demais ações em massa.

FR4 (CAP-23): O export para o Tirvu usa o layout de 34 colunas, preenchendo as 6 novas a
partir do que o sistema já coleta.

FR5 (CAP-23): As 6 colunas novas são opcionais — campo vazio não vira pendência bloqueante,
e o layout de 28 colunas continua aceito.

FR6 (CAP-1): O "?" de ajuda do portal do candidato é legível no tema escuro.

FR7 (CAP-5): O RH gera a autodeclaração de residência a partir da página do candidato ou
colaborador, com um clique.

FR8 (CAP-4): O RH exclui candidato antigo ou duplicado com motivo obrigatório, pela lixeira.

FR9 (CAP-4): O candidato excluído volta da lixeira — restauração testada, não presumida.

FR10 (CAP-7): Quem sai do link e volta cai na etapa pendente do fluxo; o sistema decide
sozinho qual é.

### NonFunctional Requirements

NFR1: Contraste do glifo do "?" contra o próprio fundo maior ou igual a 4,5:1, medido no
navegador no tema escuro, nas três telas do portal do candidato.

NFR2: O Nº Cartão DF Trans sai como texto na planilha, nunca como número — como número o
Excel come o zero à esquerda e o cartão entra errado na integração.

NFR3: Toda rota nova sob `/rh/` declara permissão via `Depends(exige(...))`; rota sem
permissão reprova no CI.

NFR4: Exclusão passa pela lixeira e entra no mapa `classes_restauraveis`; sem a segunda
metade a lixeira vira via de mão única.

NFR5: Repositório é público — nenhum dado real (CPF, e-mail, nome de colaborador) em código
ou artefato versionado, inclusive em teste.

NFR6: Documento assinado nunca muda; alteração de texto ou layout vale só para documentos
futuros.

### Additional Requirements

- O backend já aceita `ids` e `posto_id` em `_colaboradores_para_tirvu`
  (`backend/app/api/colaboradores.py:207`) e os repassa em `exportar_tirvu_massa` (linha 241)
  e `exportar_dexion_massa` (linha 309). A capacidade de exportar por seleção existe no
  servidor e nunca foi usada — o trabalho de FR1 é de front, não de rota nova.
- `DashPlanilha` mantém a seleção em `selec` (`frontend/src/rh/DashPlanilha.jsx:43`) e a
  entrega a quem é `acoesMassa` (linha 301). Exportar vive fora disso, no cabeçalho da tela
  (`frontend/src/rh/Colaboradores.jsx:437-442`).
- `COLUNAS_TIRVU` (`backend/app/services/export_tirvu.py:47`) tem 28 entradas em ordem fixa;
  `montar_workbook_tirvu` (linha 329) escreve célula a célula e omite célula vazia de
  propósito, para não gerar `inlineStr` malformado que o parser do Tirvu recusa.
- O modelo novo `docs/Layout de Importação de Admissões (1).xlsx` foi lido: aba `Plan1`,
  34 colunas, as 28 primeiras idênticas às atuais na mesma ordem; as 6 novas são AC a AH —
  Nome do Pai, Nome da Mãe, Nº Cartão DF Trans, Nº do RG, Órgão Expedidor do RG, Data de
  Emissão do RG. O arquivo tem só cabeçalho, sem linha de exemplo.
- Os 6 campos já são coletados: `ficha.py` linhas 86, 87, 141, 142, 143 e 204. É ligar, não
  coletar — nenhuma migration de coleta.
- Não existe rota `DELETE` de candidato em `backend/app/api/candidatos.py`; a única é de
  teste-vinculado (linha 320). A capacidade de FR8 nunca foi construída.
- `Candidato` é alvo de 27 chaves estrangeiras em 16 modelos, das quais apenas 5 declaram
  `ondelete="CASCADE"`. Excluir sem tratar as dependentes estoura violação de integridade.
- `classes_restauraveis` (`backend/app/api/lixeira.py:25`) tem 10 entradas; `candidato` não
  está entre elas. `test_lixeira_restaura.py` varre as chamadas de `mandar_para_lixeira` e
  reprova entidade ausente do mapa.
- `_sincronizar_autodeclaracao_residencia` (`backend/app/api/ficha.py:293`) cria a Assinatura
  quando o comprovante é de terceiro e a remove quando o titular é limpo, se ainda não
  assinada. O gerador existe; falta a porta na tela do RH.
- `acrescentar_documento_especifico` (`backend/app/api/revisao.py:825`) é o precedente mais
  próximo de FR7: acrescenta um documento a uma pessoa, com motivo obrigatório, recusa 409
  em assinatura viva e restringe ao catálogo.
- `expurgar_vencidos` (`backend/app/services/lixeira.py:48`) apaga em definitivo o que passou
  da retenção. O snapshot da lixeira guarda só as colunas do próprio registro.

### UX Design Requirements

UX-DR1: `.btn-ajuda` (`frontend/src/styles.css:609`) usa `background: var(--tinta)` com
`color: #fff`; no tema escuro `--tinta` inverte para `#e9f4ec` e o resultado é "?" branco
sobre círculo branco. O `.ajuda-q` do painel do RH (linha 2037) já foi corrigido e traz o
comentário explicando — a correção segue o mesmo desenho, com tokens que invertem juntos.

UX-DR2: Exportar migra do cabeçalho da tela para a barra de ações em massa do
`DashPlanilha`, ficando ao lado de efetivar, desligar e reverter — mesmo lugar onde a
seleção já é entregue.

UX-DR3: ADIADO junto com FR2 (CAP-2b), por decisão do Bruno em 02/09/2026. Sem história
nesta onda.

UX-DR4: O botão de gerar a autodeclaração fica na ficha da pessoa, na faixa de documentos,
seguindo o § 8c do design (tela de trabalho sobre um registro).

UX-DR5: A exclusão de candidato pede motivo obrigatório e nomeia o que será removido junto,
antes de confirmar — recusa e confirmação oferecem a saída no mesmo lugar.

### FR Coverage Map

FR1 (CAP-2): Épico 1 — exportar passa a ser ação em massa e recebe a seleção do DashPlanilha.
FR2 (CAP-2b): ADIADO — fora da Onda 1 por decisão do Bruno (02/09/2026); sem história.
FR3 (CAP-3): Épico 1 — Admissões ganha o mesmo contrato de exportação.
FR4 (CAP-23): Épico 1 — layout de 34 colunas, com as 6 novas ligadas ao que já se coleta.
FR5 (CAP-23): Épico 1 — as 6 colunas novas são opcionais e não viram pendência.
FR6 (CAP-1): Épico 2 — o "?" do portal do candidato legível no tema escuro.
FR7 (CAP-5): Épico 2 — autodeclaração de residência gerada pela ficha.
FR10 (CAP-7): Épico 2 — o link devolve a pessoa à etapa pendente correta.
FR8 (CAP-4): Épico 3 — excluir candidato duplicado com motivo (histórias 3.1 e 3.2).
FR9 (CAP-4): Épico 3 — o candidato excluído volta da lixeira (história 3.3).

NFR1 → Épico 2 (história 2.1) · NFR2 → Épico 1 (história 1.3) · NFR3 → Épico 3 (história 3.1)
NFR4 → Épico 3 (história 3.3) · NFR5 → todas as histórias com teste · NFR6 → Épico 2 (história 2.2)

## Epic List

Três épicos. A ordem é a do anexo de priorização: falha silenciosa antes de falha visível.

### Epic 1: A planilha da folha traz exatamente quem o RH escolheu

Hoje o RH marca pessoas, exporta, e vêm outras — e o arquivo vai para a folha de pagamento
sem nada denunciando. Ao fim deste épico, exportar entrega quem está marcado; sem marcação,
quem os filtros mostram. Admissões ganha a mesma exportação, e o arquivo sai no layout novo
de 34 colunas que o fornecedor passou a exigir.

**FRs cobertos:** FR1, FR3, FR4, FR5  (FR2 adiado pelo Bruno — ver mapa de cobertura)
**NFRs:** NFR2, NFR5

**Por que um épico só:** as cinco capacidades tocam o mesmo par de arquivos —
`frontend/src/rh/Colaboradores.jsx` e `backend/app/services/export_tirvu.py`. Separá-las em
épicos faria três levas mexerem nas mesmas linhas, uma desfazendo o encaixe da outra. As
histórias ficam ordenadas dentro do épico e cada uma cabe numa sessão de implementação.

**Notas de implementação:** o backend já aceita `ids` e `posto_id`
(`colaboradores.py:207`) e nunca foi usado assim — o trabalho é de front. O modelo novo do
fornecedor foi lido: 34 colunas, as 28 primeiras idênticas e na mesma ordem.

### Epic 2: O candidato enxerga, encontra e retoma onde parou

Três defeitos que a pessoa do outro lado do link sente, cada um num ponto diferente do
caminho: a interrogação de ajuda invisível no tema escuro, a autodeclaração de residência que
só nasce pelo wizard e não tem botão na ficha, e o retorno pelo link que às vezes cai na etapa
errada. Ao fim, quem volta ao link chega onde tem o que fazer, e o RH emite a autodeclaração
sem depender de o candidato ter marcado comprovante de terceiro.

**FRs cobertos:** FR6, FR7, FR10
**NFRs:** NFR1, NFR5, NFR6

**Por que juntos:** são três pontos do portal do candidato e da ficha, todos de esforço baixo
e já decididos. Nenhum depende do outro; qualquer um pode ir a produção sozinho.

**Notas de implementação:** a causa de FR6 está rastreada até `styles.css:609`, com a correção
irmã já feita em `.ajuda-q` (linha 2037) servindo de modelo. O gerador da autodeclaração já
existe (`ficha.py:293`); falta a porta na tela. FR10 começa por mapear os estados reais até
nomear o caso que cai errado — não por escrever correção.

### Epic 3: O RH apaga o cadastro duplicado, e desfaz se errar

O Bruno está bloqueado hoje: não existe rota para excluir candidato. Ao fim deste épico ele
exclui o registro antigo ou duplicado com motivo obrigatório, o item aparece na lixeira, e
volta de lá — restauração testada, não presumida.

**FRs cobertos:** FR8, FR9
**NFRs:** NFR3, NFR4, NFR5

**Por que separado:** é o único do lote que cria capacidade inexistente, e o único que
escreve destrutivamente sobre um registro alvo de 27 chaves estrangeiras. Misturá-lo com
ajustes de tela esconderia o peso que ele tem.

**Notas de implementação:** `classes_restauraveis` (`lixeira.py:25`) não tem `candidato`, e
`test_lixeira_restaura.py` reprova quem entra na lixeira sem entrar no mapa. As 27 chaves
estrangeiras em 16 modelos, com apenas 5 em cascata, decidem o desenho da história 3.1.
A rota e a tela são histórias separadas porque juntas não cabem numa sessão de implementação.

---

## Epic 1: A planilha da folha traz exatamente quem o RH escolheu

Exportar deixa de ser um botão de cabeçalho que monta o próprio conjunto e passa a ser ação
em massa, recebendo a seleção que efetivar e desligar já recebem. Admissões ganha a mesma
capacidade. O arquivo do Tirvu sai no layout novo de 34 colunas.

### Story 1.1: Exportar entrega quem está marcado

As a analista de RH,
I want que a planilha do Tirvu ou do Dexion traga exatamente as pessoas que marquei na tela,
So that o arquivo que vai para a folha de pagamento não contenha gente que eu não escolhi.

**Acceptance Criteria:**

**Given** que estou na tela de Colaboradores e marquei três pessoas
**When** aciono exportar para o Tirvu
**Then** a planilha contém exatamente essas três pessoas
**And** os filtros do topo da tela não acrescentam nem removem ninguém do arquivo

**Given** que não marquei ninguém e apliquei filtros de posto e situação
**When** aciono exportar
**Then** a planilha contém exatamente as pessoas que a tela está mostrando

**Given** que marquei pessoas
**When** olho onde fica o controle de exportar
**Then** ele está na barra de ações em massa, ao lado de efetivar, desligar e reverter
**And** não existe mais um botão de exportar no cabeçalho da tela montando conjunto próprio

**Given** que a exportação usa a seleção
**When** o front chama a rota
**Then** ele envia os identificadores das linhas marcadas no parâmetro `ids`, que
`_colaboradores_para_tirvu` (`backend/app/api/colaboradores.py:207`) já aceita
**And** nenhuma rota nova é criada para isso

**Given** que a pré-checagem de pendências roda antes do download
**When** ela é consultada
**Then** recebe o mesmo conjunto que a exportação vai receber, e não outro

**Given** que a mudança está feita
**When** rodo o teste que a cobre
**Then** existe um caso que marca pessoas, exporta, e confere nome a nome quem saiu na planilha
**And** a mutação que faz a exportação ignorar `ids` e cair nos filtros reprova esse teste

### Story 1.2: Exportar também em Admissões

As a analista de RH,
I want exportar candidatos direto da tela de Admissões,
So that eu não precise passar por Colaboradores para obter a planilha de quem ainda está em
admissão.

**Acceptance Criteria:**

**Given** que estou na tela de Admissões e marquei candidatos
**When** aciono exportar
**Then** a planilha contém exatamente os candidatos marcados
**And** o comportamento é o mesmo estabelecido na história 1.1

**Given** que não marquei ninguém
**When** aciono exportar
**Then** a planilha contém exatamente os candidatos que a tela está mostrando, respeitando os
filtros de busca, status e posto já existentes

**Given** que procuro o controle
**When** olho a tela
**Then** ele está junto das demais ações em massa, no mesmo lugar que ocupa em Colaboradores
**And** o botão de exportar planilha que hoje vive em `acoesFiltro`
(`frontend/src/rh/RHApp.jsx:949`) não continua duplicando a mesma função em outro lugar

**Given** que Admissões lista quem tem `situacao` nula
**When** a exportação monta o conjunto
**Then** ela respeita esse recorte, sem passar a incluir colaboradores efetivados

### Story 1.3: A planilha do Tirvu sai com as 34 colunas do modelo novo

As a analista de RH,
I want que o arquivo gerado tenha as 34 colunas que o Tirvu passou a exigir,
So that a importação seja aceita sem eu ter de completar colunas à mão.

**Acceptance Criteria:**

**Given** o modelo oficial `docs/Layout de Importação de Admissões (1).xlsx`
**When** comparo com a planilha que o sistema gera
**Then** as 34 colunas saem na mesma ordem do modelo, na aba `Plan1`
**And** as 28 primeiras permanecem idênticas às atuais, sem reordenação

**Given** uma pessoa com nome do pai, nome da mãe, RG, órgão expedidor e data de emissão
preenchidos na ficha
**When** exporto
**Then** as colunas AC, AD, AF, AG e AH trazem esses valores, lidos do que o sistema já coleta
(`backend/app/api/ficha.py` linhas 86, 87, 141, 142 e 143)
**And** nenhum campo novo é perguntado ao candidato, e nenhuma migration de coleta é criada

**Given** uma pessoa com cartão do DF Trans cujo número começa com zero
**When** exporto e abro a planilha
**Then** o valor da coluna AE aparece como texto, com o zero à esquerda preservado
**And** existe teste que reprova se a célula for gravada como número

**Given** que o teste compara a planilha gerada
**When** ele afirma sobre o layout
**Then** a referência é o arquivo do fornecedor, não uma lista de cabeçalhos escrita no teste

**Given** uma pessoa sem nenhum dos seis campos novos preenchidos
**When** exporto
**Then** a planilha é gerada normalmente, com essas células vazias
**And** nenhum dos seis campos é acrescentado à lista que `pendencias_linha`
(`backend/app/services/export_tirvu.py:378`) verifica
**And** a opcionalidade vale desde esta história — ela não espera a 1.4 para não bloquear

### Story 1.4: A opcionalidade das colunas novas fica travada em teste

As a analista de RH,
I want que ninguém torne obrigatório, no futuro, um dos seis campos novos do Tirvu,
So that a falta de um RG ou de um cartão do DF Trans nunca me impeça de mandar a pessoa para
a folha.

**Acceptance Criteria:**

**Given** que a história 1.3 já entregou a opcionalidade funcionando
**When** esta história começa
**Then** o trabalho é travar esse comportamento em teste, não construí-lo
**And** a exportação de quem não tem os seis campos já funciona antes desta história começar

**Given** a mutação que acrescenta um dos seis campos às pendências obrigatórias
**When** rodo o teste
**Then** ele reprova, nomeando o campo que passou a bloquear indevidamente

**Given** o layout antigo de 28 colunas
**When** o teste afirma sobre compatibilidade
**Then** ele registra que esse layout continua aceito, conforme a regra do fornecedor

---

## Epic 2: O candidato enxerga, encontra e retoma onde parou

Três pontos do caminho de quem recebe o link, cada um independente do outro.

### Story 2.1: A interrogação de ajuda é legível no tema escuro

As a candidato usando o portal no tema escuro,
I want enxergar o botão de ajuda,
So that eu consiga pedir explicação quando travo numa etapa.

**Acceptance Criteria:**

**Given** o portal do candidato no tema escuro
**When** meço o contraste do glifo contra o fundo do próprio botão, no navegador
**Then** o valor é maior ou igual a 4,5:1
**And** a medição cobre as três telas onde a classe aparece: `CandidatoApp.jsx:142`,
`Checklist.jsx:365` e `Wizard.jsx:217`

**Given** o portal no tema claro
**When** meço o mesmo contraste
**Then** ele continua maior ou igual a 4,5:1, sem regressão

**Given** a correção em `frontend/src/styles.css:609`
**When** leio a regra
**Then** ela usa tokens que invertem juntos com o tema, no mesmo desenho que `.ajuda-q`
(linha 2037) já adotou
**And** nenhum valor de cor fixo é escrito para resolver o caso

### Story 2.2: O RH gera a autodeclaração de residência pela ficha

As a analista de RH,
I want emitir a autodeclaração de residência a partir da página da pessoa,
So that eu não dependa de o candidato ter declarado comprovante de terceiro no wizard.

**Acceptance Criteria:**

**Given** uma pessoa sem autodeclaração de residência
**When** aciono o controle na ficha dela
**Then** o documento passa a existir para ela assinar, seguindo o fluxo normal de assinatura
**And** o gerador usado é o que já existe, sem duplicação de texto

**Given** uma pessoa que já tem a autodeclaração pendente ou assinada
**When** aciono o controle
**Then** a resposta recusa nomeando o estado atual, e não cria um segundo documento
**And** a recusa diz o que resolve, no mesmo lugar onde recusou

**Given** que a rota é nova e vive sob `/rh/`
**When** ela é declarada
**Then** ela traz a permissão do ato via `Depends(exige(...))`, e o teste do CI que varre
permissões declaradas continua passando

**Given** que o precedente mais próximo é `acrescentar_documento_especifico`
(`backend/app/api/revisao.py:825`)
**When** a rota é escrita
**Then** ela segue o mesmo desenho: alvo único, recusa 409 em assinatura viva, auditoria do ato

**Given** um documento já assinado
**When** qualquer parte desta história roda
**Then** ele permanece intocado

### Story 2.3: O link devolve a pessoa à etapa pendente

As a candidato que saiu do link e voltou depois,
I want cair na etapa em que ainda tenho o que fazer,
So that eu não abra uma tela onde não há nada a resolver.

**Acceptance Criteria:**

**Given** o roteamento por status que já existe em
`frontend/src/candidato/CandidatoApp.jsx:53-88`
**When** a história começa
**Then** o primeiro trabalho é percorrer os estados reais e registrar, por escrito, qual
combinação devolve a tela errada
**And** nenhuma correção é escrita antes de o caso estar nomeado

**Given** o caso identificado
**When** a correção é aplicada
**Then** voltar pelo link naquele estado leva à etapa que tem trabalho pendente
**And** os estados que já roteavam certo continuam roteando certo

**Given** que falta documento a enviar
**When** volto pelo link
**Then** chego ao checklist

**Given** que falta assinar
**When** volto pelo link
**Then** chego à assinatura

**Given** a correção pronta
**When** rodo o teste que a cobre
**Then** ele exercita o roteamento a partir do estado, não a função isolada
**And** a mutação que devolve a tela errada naquele caso reprova o teste

---

## Epic 3: O RH apaga o cadastro duplicado, e desfaz se errar

Capacidade que nunca existiu: não há rota de exclusão de candidato no sistema.

### Story 3.1: A rota de exclusão existe e recusa quem não pode sair

As a analista de RH,
I want uma exclusão de candidato que só aceite cadastro sem nada pendurado, e que exija motivo,
So that eu apague o duplicado sem risco de arrastar junto ficha, documento ou assinatura de
alguém.

**Acceptance Criteria:**

**Given** um candidato duplicado, sem ficha, documento ou assinatura pendurados
**When** a rota de exclusão é chamada com um motivo
**Then** o registro é removido
**And** o motivo fica gravado na auditoria, com quem excluiu e quando

**Given** que nenhum motivo foi informado
**When** a rota é chamada
**Then** responde recusando, dizendo que o motivo é obrigatório

**Given** um candidato que já tem ficha preenchida, documento enviado ou assinatura
**When** a rota é chamada
**Then** responde recusando e nomeia o que impede
**And** a mensagem diz o que resolve, em vez de só bloquear

**Given** que o registro é alvo de 27 chaves estrangeiras em 16 modelos, das quais só 5 estão
em cascata
**When** a exclusão executa
**Then** não deixa referência órfã nem estoura violação de integridade
**And** é a recusa do critério anterior que garante isso, em vez de apagar dependentes em massa

**Given** que a rota é nova e vive sob `/rh/`
**When** ela é declarada
**Then** traz a permissão do ato via `Depends(exige(...))`, e o teste do CI continua passando

**Given** que a exclusão é destrutiva
**When** ela executa
**Then** passa por `mandar_para_lixeira` antes do delete, guardando o snapshot

**Given** a mutação que remove a recusa e deixa excluir candidato com dependentes
**When** rodo o teste
**Then** ele reprova, conferindo o ESTADO do banco e não apenas o código da resposta

### Story 3.2: O RH exclui pela tela da pessoa

As a analista de RH,
I want excluir o cadastro duplicado direto da tela, informando o motivo ali,
So that eu resolva a duplicidade sem depender de alguém chamar uma rota por mim.

**Acceptance Criteria:**

**Given** a rota entregue pela história 3.1
**When** esta história começa
**Then** o trabalho é a porta na tela, e a regra de quem pode sair já está pronta

**Given** um candidato duplicado aberto na tela
**When** aciono excluir
**Then** o sistema pede o motivo antes de executar, e não conclui sem ele

**Given** que confirmei a exclusão
**When** a operação termina
**Then** o registro deixa de aparecer nas telas de Admissões e de Colaboradores
**And** a confirmação aparece onde eu estava olhando, não no topo de uma tela rolada

**Given** um candidato que a regra não deixa excluir
**When** aciono excluir
**Then** a tela mostra o que impede, no mesmo lugar onde recusou

### Story 3.3: O candidato excluído volta da lixeira

As a analista de RH,
I want restaurar um candidato que excluí por engano,
So that o erro de um clique não custe um cadastro.

**Acceptance Criteria:**

**Given** um candidato que excluí
**When** abro a lixeira
**Then** ele aparece listado, com rótulo, motivo e data

**Given** o item na lixeira
**When** aciono restaurar
**Then** o candidato volta a aparecer nas telas, com os mesmos dados que tinha
**And** a restauração é verificada por teste que confere o registro depois de voltar, não
apenas a resposta da rota

**Given** o mapa `classes_restauraveis` (`backend/app/api/lixeira.py:25`)
**When** a leva termina
**Then** a entidade do candidato está nele
**And** `test_lixeira_restaura.py` passa, e reprovaria se a entrada faltasse

**Given** que a exclusão só aceita candidato sem nada pendurado (história 3.1)
**When** a restauração devolve o registro
**Then** ela devolve a pessoa inteira, porque não havia mais nada a devolver
**And** nenhuma restauração parcial e silenciosa é possível por construção
