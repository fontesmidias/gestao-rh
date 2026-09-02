> **Origem.** Gerado com `bmad-create-story` a partir de
> `20-epicos-24a-leva-onda-1.md`, em 02/09/2026. Levantado contra o código real e
> validado em contexto independente.
>
> O arquivo que o agente de implementação consome vive em
> `_bmad-output/implementation-artifacts/` (não versionado). **Esta é a cópia
> canônica versionada.** Ao mexer, re-derivar lá e republicar aqui.

---

# Story 1.1: Exportar entrega quem está marcado

Status: ready-for-dev

Épico 1 (Onda 1, 24ª leva) · Contrato: `docs/planejamento/19-feedbacks-24a-leva.md` ·
Épicos: `docs/planejamento/20-epicos-24a-leva-onda-1.md`

## Story

As a analista de RH,
I want que a planilha do Tirvu, do Dexion ou do Excel traga exatamente as pessoas que marquei na tela,
so that o arquivo que vai para a folha de pagamento não contenha gente que eu não escolhi.

## Contexto: por que esta é a primeira da fila

Relato do Bruno (02/09/2026): **"marca as pessoas, exporta, e vêm outras."**

É a única **falha silenciosa** da 24ª leva. Os outros defeitos incomodam e serão
relatados; este não — a planilha sai, abre, parece certa, e vai para a folha de
pagamento com gente que ninguém escolheu. Por isso vem antes de tudo.

**A causa não é o backend.** O servidor já aceita `ids` desde sempre
(`_colaboradores_para_tirvu`, `colaboradores.py:207`) e essa capacidade **nunca
foi usada**. O defeito é estrutural no front: existem dois mundos em
`Colaboradores.jsx`.

| | Onde vive | Enxerga a seleção? |
|---|---|---|
| Efetivar / desligar / reverter / Domínio | `acoesMassa` (L381), passado ao `DashPlanilha` | **Sim** |
| Exportar Tirvu / Dexion / Excel | cabeçalho da tela (L434-443), fora do dash | **Não** |

Exportar monta o próprio conjunto a partir dos filtros do topo (L124, L154).
Nunca foi ação em massa.

## Acceptance Criteria

**AC1 — a seleção manda.**
Marcadas N pessoas em Colaboradores, exportar (Tirvu, Dexion ou Excel) produz
planilha com **exatamente essas N pessoas**. Os filtros do topo não acrescentam
nem removem ninguém.

**AC2 — sem seleção, vale a tela.**
Sem ninguém marcado, a planilha traz exatamente quem a tela está mostrando,
respeitando os filtros ativos. É o comportamento de hoje, preservado.

**AC3 — exportar é ação em massa.**
Os controles de exportar ficam junto de efetivar, desligar e reverter, e sem
seleção continuam alcançáveis (ver "Onde os botões ficam", abaixo — há uma
decisão de desenho a respeitar).

**AC4 — a pré-checagem enxerga o mesmo conjunto.**
A checagem de pendências que roda antes do download recebe o mesmo conjunto que
a exportação vai receber. Hoje as duas montam o conjunto separadamente (L156 e
L170).

**AC5 — volume real não quebra.**
Exportar a base inteira (1.171 pessoas hoje) funciona. Ver "O limite de 8 KB" —
**este critério exige mudança de contrato de rota**, não é opcional.

**AC6 — Excel também obedece.**
`GET /rh/colaboradores/exportar` (L174) **não aceita `ids` hoje**. Passa a aceitar,
com o mesmo contrato das outras duas.

**AC7 — coberto por teste.**
Teste que marca pessoas, exporta e confere **nome a nome** quem saiu na planilha.
A mutação que faz a exportação ignorar `ids` e cair nos filtros **reprova** o teste.

## Tasks / Subtasks

- [ ] **Task 0 — corrigir o `setAviso` inexistente** (bloqueia AC1/AC3; ver "Defeito achado")
  - [ ] Declarar o estado `aviso` em `Colaboradores.jsx` e renderizar com `<Aviso>`
  - [ ] Conferir que efetivar, desligar, reativar e reverter deixam de estourar
- [ ] **Task 1 — rotas aceitam seleção grande** (AC5, AC6)
  - [ ] Variantes `POST` das **cinco** rotas, com `ids` no CORPO — as três de
        exportação (`exportar`, `exportar-tirvu`, `exportar-dexion`) **e as duas de
        pendências** (`tirvu-pendencias`, `dexion-pendencias`), senão AC4 não fecha:
        a pré-checagem receberia conjunto diferente do da exportação
  - [ ] `GET` continua existindo e funcionando (AC2 e compatibilidade)
  - [ ] `exportar` (Excel) passa a resolver `ids` como as outras duas
  - [ ] Permissão: exportações declaram `dados:exportar_base`; **pendências mantêm
        `colaboradores:ler`** (é o que usam hoje, L225 e L288) — não eleve
- [ ] **Task 2 — front passa a seleção** (AC1, AC2, AC4)
  - [ ] `api.js`: funções de export aceitam `ids` e usam POST quando houver seleção
  - [ ] `exportarFolha` e `exportar` recebem as linhas selecionadas
  - [ ] Pendências e exportação compartilham **um único** conjunto resolvido
- [ ] **Task 3 — mover os controles** (AC3)
  - [ ] Botões de exportar vão para o card `.dash-acoes` (sempre visível), **não**
        para `acoesMassa` — ver "Onde os botões ficam", que explica por quê
  - [ ] O rótulo reflete a seleção (ex.: `⬆ Exportar p/ Tirvu (12 marcados)`)
  - [ ] Remover o bloco do cabeçalho (L434-443) — sem deixar controle duplicado
  - [ ] Resolver a convivência com o `⬇ Exportar CSV` do próprio dash (ver abaixo)
- [ ] **Task 4 — teste** (AC7)
  - [ ] `backend/tests/test_export_por_selecao.py`, com a mutação nomeada
  - [ ] Acrescentar ao `ci.yml` no bloco que sobe a app (ver "Testes")

---

## Dev Notes

### Defeito achado durante o levantamento — corrigir ANTES (Task 0)

`Colaboradores.jsx` chama **`setAviso` oito vezes** (L229, 232, 242, 245, 267,
271, 283, 287) e **nunca declara esse estado**. Não há `useState` para `aviso`
(as declarações vão de L92 a L101) nem import de `Aviso.jsx`.

- **Introduzido na v1.76** (commit `4577710`), quando a tela migrou para o
  `DashPlanilha`: o estado foi removido e as chamadas ficaram.
- **Nada acusa:** o projeto **não tem ESLint configurado** (`frontend/` não tem
  `.eslintrc*` nem `eslint.config.*`) e o `npm run build` passa.
- **Efeito:** `ReferenceError` na **primeira linha** de toda ação em massa —
  efetivar, desligar, reativar, reverter, Domínio. Exceção em handler de evento
  não derruba a tela, mas **a ação não acontece** e nada é dito.

Por que corrigir aqui: esta história mexe na barra de ações da mesma tela e faz
exportar passar a ler a seleção que essas ações já leem. Entregar sem isso seria
melhorar a exportação numa tela cujas outras ações em massa não funcionam.

Use o `<Aviso>` flutuante (`frontend/src/Aviso.jsx`), que é o padrão da casa para
confirmação de AÇÃO — `.alerta` inline é para descrever ESTADO.

Falso positivo descartado: `Config.jsx` usa `setAvisoConfig`, devidamente
declarado (L391).

### O limite de 8 KB — por que `ids` na querystring não serve

Medido nesta máquina, com UUID real e `Authorization` típico:

| Seleção | Querystring | Linha + headers | Cabe em 8 KB? |
|---|---|---|---|
| 50 | 1,9 KB | 2,3 KB | sim |
| 200 | 7,6 KB | 8,1 KB | **não** |
| 500 | 19,0 KB | 19,5 KB | **não** |
| 1.171 (base real) | 44,6 KB | 45,0 KB | **não** |

`frontend/nginx.conf` **não declara** `large_client_header_buffers`, então vale o
default do nginx: `4 8k`. Acima disso o nginx devolve **414** antes de a
requisição chegar ao FastAPI.

**O sintoma seria enganosíssimo:** exportar 30 pessoas funciona (é como se testa),
exportar a base inteira falha; e `api.js::lancarErro` **não trata 414** — o nginx
responde HTML, `r.json()` falha, `detail` fica nulo e a tela diz "erro". Ninguém
liga isso a tamanho de URL. É a família de defeito que esta leva existe para
eliminar, reintroduzida por uma porta nova.

**Não resolva subindo o buffer do nginx.** Isso conserta um ambiente e deixa o
outro quebrado (o arquivo do repo não sobe sozinho para o Portainer — v3.15.1), e
a URL continua carregando 1.171 identificadores de pessoas em log de acesso.

**Precedente da casa a seguir:** `POST /rh/arquivo/lote` (`arquivo.py:271`) faz
exatamente isso — recebe a seleção no corpo e devolve arquivo. O front tem o
espelho pronto em `api.js::arquivoLote` (L1421-1431): POST com corpo JSON,
`if (!r.ok) await lancarErro(r)`, `return r.blob()`. **Copie essa forma.**

Mantenha as rotas `GET` existentes funcionando (AC2 usa filtros, não `ids`, e cabe
folgado na URL).

### O que `ids` faz hoje no backend — leia antes de mexer

`_colaboradores_para_tirvu` (`colaboradores.py:207-216`):

```python
if ids:
    alvo = [i for i in (x.strip() for x in ids.split(",")) if i]
    return [c for i in alvo if (c := db.get(Candidato, uuid.UUID(i))) is not None]
candidatos = _filtrar(db, status, busca, situacao, posto_id, so_colaboradores=True)
if not incluir_importados:
    candidatos = [c for c in candidatos if c.origem != "importacao"]
```

Quatro comportamentos que **você precisa conhecer**:

1. **`ids` é retorno antecipado.** Todos os demais filtros são ignorados,
   inclusive `so_colaboradores` e `incluir_importados`. Isso está **correto** para
   esta história: o RH marcou aquelas pessoas, e é isso que ele leva (AC1).
2. **UUID malformado levanta `ValueError` não tratado → HTTP 500**, não 422. Ao
   escrever a rota nova, recuse com 422 nomeando o que veio errado.
3. **Id inexistente é descartado em silêncio** (`db.get` devolve `None`). Numa
   ação que gera folha de pagamento, sumiço calado é o defeito que a leva combate:
   se algum id pedido não existe, **diga**.
4. **A ordem do resultado passa a ser a dos ids**, não `criado_em desc`. Sem
   impacto no arquivo, mas não estranhe.

`_filtrar` (L35-70) **não tem** parâmetro `ids` — quem resolve é
`_colaboradores_para_tirvu`. E `busca` é filtrado em Python, não em SQL (L52-69).

### Efeito colateral que persiste no banco

`exportar_tirvu_massa` chama `linha_tirvu(db, c, gerar_matricula=True)` (L257) e
**commita** (L264): quem não tem matrícula **recebe uma** (padrão `999`+sequencial)
e ela fica gravada. Exportar não é operação de leitura pura.

Consequência prática: **exportar a seleção errada grava matrícula em quem não
devia**. É mais um motivo para AC1 estar certo antes de qualquer coisa.

### Como o front está hoje (levantado, com linhas)

**`Colaboradores.jsx`** (482 linhas):

- `exportar` (Excel) — L121-134. Monta filtros inline (L124-125), baixa via
  `createObjectURL` + `a.download` (L126-130), `catch` sem variável (L131), usa
  `<Espera>` (L450) e o estado `exportando` (L99).
- `exportarFolha` — L151-182. Recebe a string `'tirvu'`/`'dexion'`, resolve por
  `DESTINOS` (L144-149), monta filtros **sem** `incluir_admissao` (L154 — difere do
  Excel), consulta pendências (L156), confirma com `window.confirm` listando até 8
  nomes (L163-169), exporta (L170-171) e trata `nenhum_colaborador` (L177-181).
  Usa `comAmpulheta(texto, () => promessa)`.
- `acoesMassa` — L381-403. Assinatura `(linhas, limpar) => JSX`. **`linhas` são os
  objetos inteiros**, não ids; os handlers extraem com `.map(c => c.id)` (L238,
  250, 254, 286). Todos chamam `limpar()` e `carregar()` no sucesso.
- Bloco do cabeçalho a remover — L434-443, dentro de `<header className="rh-topo">`.

**`DashPlanilha.jsx`** (430 linhas):

- `acoesMassa(selecionadas, limparSelecao)` — chamado em **L304**, dentro de um
  bloco que **só aparece quando há ≥1 selecionado** (`{alguns && acoesMassa && ...}`,
  L301-307).
- `selecionadas` (L137) = `linhas.filter(l => selec.has(chaveLinha(l)))` — **objetos
  de linha**, e apenas os **visíveis** sob o filtro atual.
- `acoesFiltro` (L198) é renderizado no card `.dash-acoes` (L197), que é **sempre
  visível** e fica **fora** do `<details>` recolhível.
- **A seleção NÃO é limpa quando `dados` muda** — não há `useEffect` para isso.
  Marcadas 3 pessoas e aplicado um filtro que esconde 2, `selecionadas` traz 1; as
  outras 2 reaparecem ao limpar o filtro. Documente na UI se isso confundir.

### Onde os botões ficam — decisão de desenho a respeitar

Há uma tensão real entre duas regras da casa, e ela **precisa ser resolvida, não
ignorada**:

- O bloco `acoesMassa` do dash **só existe quando há seleção** (L301). Pôr
  exportar só ali **esconderia** a exportação de quem não marcou ninguém — e AC2
  exige que exportar sem seleção continue funcionando.
- `08-sistema-de-design.md` (§ v2.76.1, L788-790) separa as duas naturezas —
  *"Filtrar e AGIR são naturezas diferentes: uma refina o que se vê, a outra cria e
  exporta. As ações têm card próprio (`.dash-acoes`), sempre visível"* — e fecha com
  a regra: **"nada que CRIA pode viver dentro de um bloco que se recolhe"**.
  Exportar é AGIR, não filtrar. Foi o defeito de "sumiu o botão de cadastrar talento".

**Desenho que satisfaz as duas:** os controles de exportar ficam no card
`.dash-acoes` (sempre visível, fora do `<details>`) **e** o rótulo reflete a
seleção — `⬆ Exportar p/ Tirvu (12 marcados)` quando há seleção, sem sufixo quando
não há. Exportar fica alcançável sempre, e a tela **diz** o que vai levar antes do
clique.

**Três obstáculos concretos a resolver — nenhum é opcional:**

1. **`acoesFiltro` de Colaboradores já está ocupado** (L470-476: o checkbox
   "incluir em admissão"). Não substitua esse conteúdo — os botões precisam
   conviver com ele no mesmo card, ou entrar por outro caminho.

2. **`acoesFiltro` é um nó JSX, não uma função.** Fazê-lo receber a seleção como
   argumento muda o contrato do `DashPlanilha` e **todos** os consumidores
   (`Creche.jsx:620`, `JornadasRH.jsx:167`, `RHApp.jsx:940`, `TalentosRH.jsx:346`,
   além de Colaboradores). É mais caro do que parece. A alternativa barata é o
   `DashPlanilha` informar a seleção ao pai por callback (ex.: `aoSelecionar`),
   mantendo `selec` como fonte única e `acoesFiltro` como está.

3. **O `⬇ Exportar CSV` do próprio dash** (`DashPlanilha.jsx:144` e L203) já mora
   nesse card e exporta **o que está visível, ignorando a seleção**. Com os três
   botões novos ao lado, ficam quatro controles de exportar no mesmo lugar, dois
   contratos diferentes, sem nada explicando a diferença — exatamente o "dois
   controles para a mesma escolha" que a v2.75 proíbe. Resolva: ou o CSV passa a
   respeitar a seleção como os demais, ou o rótulo dele diz que é o da tela. Não
   deixe os dois comportamentos convivendo mudos.

Escolha um caminho para o item 2 e **registre na nota de conclusão qual foi e por
quê** — a história 1.2 (Admissões) vai reusar essa decisão.

### Testes

**Backend** — `backend/tests/test_export_por_selecao.py`, novo. Siga o padrão de
`test_documento_especifico.py`: `os.environ.setdefault` para as credenciais,
`TestClient(app)`, login em `/api/rh/auth/login` com asserção explícita, sufixo
`uuid.uuid4().hex[:8]` nos dados criados, acumulador `falhas` e `checar()`.

Cobrir:

1. Marcar 3 de 5 pessoas → planilha tem exatamente aquelas 3, **conferidas por
   nome** (abra o xlsx com `openpyxl`, como `test_export_tirvu.py` faz).
2. Filtros do topo **junto** com seleção → a seleção vence.
3. Sem seleção → vale o filtro.
4. Volume: uma seleção grande (≥200) **não** estoura — é o caso que a querystring
   não aguenta.
5. Id inexistente → resposta diz que faltou, em vez de sumir calado.
6. UUID malformado → 422 nomeando o problema, nunca 500.

**Mutação obrigatória** (AC7): fazer a rota ignorar `ids` e cair nos filtros. O
teste **tem** que reprovar. Confirme que ele **imprimiu** o resultado — ausência
de falha não é aprovação (v2.72.2), e use
`TestClient(app, raise_server_exceptions=False)` ao exercitar caminho de erro.

**Nenhuma das rotas de export tem teste HTTP hoje.** A única cobertura de `ids` é
`test_tirvu_individual_pendencias.py:108`, com **um** id.

**CI:** o teste sobe a app, então entra no bloco de `ci.yml` que roda dentro do
container (por volta da L314), **não** no bloco de testes stdlib. Rode antes com
`docker exec -e PYTHONPATH=. <api> python tests/test_export_por_selecao.py` — passar
na sua máquina não prova nada sobre lá.

**E2E:** se mexer no layout dos botões, rode
`frontend/tests/e2e/tabelas-cabem-na-tela.spec.js` — acrescentar botão à área de
ações já estourou a largura antes (v2.59). Use `--workers=1` (o rate limit do
login é 15/5min por IP e as falhas parecem defeito de layout).

**Sem dado real em teste** — o repositório é público. CPF e nome fictícios.

### Regressões a não causar

- `Detalhe.jsx:493` já usa `ids` com **um** id (export individual). Não quebre.
- A auditoria (`tirvu_exportado` L260, `dexion_exportado` L328,
  `colaboradores_exportados` L185) precisa continuar registrando, e agora deve
  refletir que a exportação veio de seleção.
- `montar_workbook_tirvu` e o layout **não mudam** nesta história — a 1.3 cuida
  das 34 colunas. Não antecipe.
- A permissão `dados:exportar_base` é marcada `perigosa=True`. Rota nova **declara**
  `Depends(exige(...))`, senão o `test_permissoes_declaradas` reprova no CI.

### Project Structure Notes

Arquivos que esta história toca:

| Arquivo | Natureza |
|---|---|
| `frontend/src/rh/Colaboradores.jsx` | UPDATE — estado `aviso`, exportar em `.dash-acoes`, remover bloco do cabeçalho |
| `frontend/src/rh/DashPlanilha.jsx` | UPDATE — expor a seleção ao pai; rever o `exportarCsv` (L144) |
| `frontend/src/api.js` | UPDATE — funções de export aceitam `ids` e usam POST |
| `backend/app/api/colaboradores.py` | UPDATE — rotas POST, `ids` no Excel, validação de UUID |
| `backend/tests/test_export_por_selecao.py` | NEW |
| `.github/workflows/ci.yml` | UPDATE — registrar o teste novo |

Fora de escopo: `export_tirvu.py` (história 1.3), a tela de Admissões (história 1.2).

### References

- [Source: docs/planejamento/19-feedbacks-24a-leva.md#CAP-2] — contrato
- [Source: docs/planejamento/19-feedbacks-24a-leva.md#Anexo — Achados no código] —
  item 13, com o registro de que o primeiro diagnóstico estava errado
- [Source: docs/planejamento/20-epicos-24a-leva-onda-1.md#Story 1.1]
- [Source: docs/planejamento/08-sistema-de-design.md] — § v2.76.1, ação não mora em
  bloco recolhível; § um assunto, um controle
- [Source: CLAUDE.md] — `<a href>` autenticado devolve 401; ação em lote com efeito
  externo é trabalho de fila; teste que não executa a linha mutada não protege nada

## Dev Agent Record

### Agent Model Used

### Debug Log References

### Completion Notes List

### File List
