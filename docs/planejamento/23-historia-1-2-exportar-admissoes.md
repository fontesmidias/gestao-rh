> **Origem.** Gerado com `bmad-create-story` e IMPLEMENTADO com `bmad-dev-story`,
> em 02/09/2026. Levantado contra o código real e validado em contexto
> independente.
>
> **Herda o contrato da história 1.1** (doc 22): a seleção manda, viaja no corpo
> da requisição, e o controle fica no card de ações, sempre visível.
>
> **Esta é a cópia canônica versionada**, com o registro de execução ao final.

---

# Story 1.2: Exportar também em Admissões

Status: review

Épico 1 (Onda 1, 24ª leva) · Contrato: `docs/planejamento/19-feedbacks-24a-leva.md` ·
Épicos: `docs/planejamento/20-epicos-24a-leva-onda-1.md` ·
História anterior: `docs/planejamento/22-historia-1-1-exportar-por-selecao.md`

## Story

As a analista de RH,
I want marcar candidatos em Admissões e exportar exatamente eles,
so that eu obtenha a planilha de quem está em admissão sem passar pela tela de
Colaboradores.

## Contexto: o que a 1.1 já resolveu, e o que falta

O Bruno relatou o item 13 em três sintomas. A história 1.1 resolveu o primeiro
(*"marquei pessoas e exportou outras"*). Este é o segundo: **"não achei onde
selecionar/exportar"** — em Admissões *"isso nem tem opção no módulo candidatos"*.

Duas lacunas, não uma:

1. **Admissões não tem seleção nenhuma.** O `DashPlanilha` só renderiza a coluna
   de checkbox quando recebe `acoesMassa` (`DashPlanilha.jsx:340`, `366`), e a
   tela não passa essa prop. Não há caixas para marcar.
2. **A exportação existente ignora seleção por construção.** É `GET
   /rh/candidatos-exportar` (`revisao.py:179`), só com filtros na querystring.

⚠️ **`aoSelecionar` sozinho não resolve.** Sem `acoesMassa` não existe checkbox,
então o callback dispararia sempre com lista vazia. As duas props andam juntas.

## Acceptance Criteria

**AC1 — dá para marcar candidatos em Admissões.**
A tela passa a ter a coluna de seleção, com marcar-todos, como Colaboradores.

**AC2 — a seleção manda.**
Marcados N candidatos, a planilha traz exatamente esses N. Os filtros do topo não
acrescentam nem removem ninguém.

**AC3 — sem seleção, vale o filtro.**
Sem ninguém marcado, a planilha traz exatamente quem a tela mostra, respeitando
busca, status e posto. É o comportamento de hoje, preservado.

**AC4 — o recorte de Admissões é respeitado.**
Só entra quem está em admissão (`situacao IS NULL`). A exportação não passa a
incluir colaboradores efetivados, nem por seleção nem por filtro.

**AC5 — volume real não quebra.**
A seleção viaja no corpo da requisição, nunca na querystring. Ver "O limite de
8 KB" na história 1.1: a URL corta em ~180 identificadores.

**AC6 — o controle fica onde se procura por ele.**
Junto das demais ações da tela, no card `.dash-acoes`, com a contagem no rótulo
no formato ` (N)` — o mesmo `sufixoSelecao` que a 1.1 usa em Colaboradores, para
as duas telas não divergirem.

**AC7 — coberto por teste.**
Teste que marca candidatos, exporta e confere nome a nome quem saiu na planilha.
A mutação que faz a exportação ignorar a seleção reprova o teste.

## Tasks / Subtasks

- [x] **Task 1 — a rota aceita seleção** (AC2, AC4, AC5)
  - [x] `POST /rh/candidatos-exportar` recebendo `ids` no corpo. O payload é
        MENOR que o `SelecaoExportIn` de Colaboradores: só `ids`, `status`,
        `busca` e `posto_id` — Admissões não tem `situacao`, `incluir_importados`
        nem `incluir_admissao` (o recorte dela é fixo)
  - [x] `GET` continua existindo e funcionando (AC3)
  - [x] Seleção respeita `situacao IS NULL` — ver "A trava do recorte", abaixo
  - [x] Declarar `Depends(exige("dados:exportar_base"))`, como o GET já faz
- [x] **Task 2 — a tela ganha seleção** (AC1, AC6)
  - [x] Passar `acoesMassa` ao `DashPlanilha` (é o que cria os checkboxes)
  - [x] Passar `aoSelecionar` para o estado da seleção
  - [x] Botão de exportar com a contagem no rótulo, no `.dash-acoes`
  - [x] Distinguir no rótulo o xlsx do `⬇ Exportar CSV` do dash (ver efeito
        colateral abaixo — ele passa a respeitar a seleção sozinho)
- [x] **Task 3 — o front manda a seleção** (AC2, AC3)
  - [x] `api.js`: `exportarAdmissoes` aceita `ids` e usa POST quando houver seleção
  - [x] Corrigir o download: falta `URL.revokeObjectURL` hoje (ver "Detalhes")
- [x] **Task 4 — teste** (AC7)
  - [x] Acrescentar blocos ao `test_export_por_selecao.py` (mesmo assunto, mesmo arquivo)
  - [x] Mutação nomeada, validada de verdade
  - [x] O teste já está no `ci.yml` — não precisa registrar de novo

---

## Dev Notes

### Reuse o que a 1.1 construiu — não invente contrato novo

A história 1.1 (v3.17, commit `9287d35`) já resolveu os problemas difíceis. **Leia
`docs/planejamento/22-historia-1-1-exportar-por-selecao.md` antes de escrever
código.** O que se herda:

| Peça | Onde | Como usar aqui |
|---|---|---|
| Prop `aoSelecionar` | `DashPlanilha.jsx:45` | já existe; só passar |
| `SelecaoExportIn` | `colaboradores.py` | modelo do payload; aqui o análogo é menor |
| `_selecionados` | `colaboradores.py` | devolve `(achados, faltando)` — **o padrão de nomear quem não existe** |
| POST com corpo + blob | `api.js:634` (`exportarSelecao`) | copie a forma REAL (abaixo) |
| Rótulo com contagem | `Colaboradores.jsx:164` (`sufixoSelecao`) | mesmo desenho (abaixo) |

A forma real do POST, para não inventar variante:

```js
exportarSelecao: (pedido, destino = 'tirvu') =>
  req(`/rh/colaboradores/exportar-selecao?destino=${destino}`,
      { method: 'POST', headers: authRH(), body: JSON.stringify(pedido) }),
```

Usa `req()`, que já devolve blob quando o `content-type` não é JSON
(`api.js:107-108`) — **não** precisa do `buscar` + `r.blob()` explícito do
`arquivoLote`. E o rótulo é exatamente:

```js
const sufixoSelecao = marcados.length ? ` (${marcados.length})` : ''
```

Ou seja `⬇ Exportar planilha (12)`, não `(12 marcados)` — as duas telas têm de
ficar iguais.

**Decisão registrada na 1.1 que esta história DEVE seguir:** a seleção chega ao
pai pela prop `aoSelecionar` do `DashPlanilha`, e **não** mudando o contrato de
`acoesFiltro` (que é nó JSX e obrigaria a mexer nos cinco consumidores). Foi
escolhida por ser aditiva.

### ⚠️ ESCOPO: Admissões exporta a planilha do RH, e SÓ ela

Não acrescente destinos Tirvu ou Dexion aqui. **Não é esquecimento — é regra de
negócio**, registrada em `colaboradores.py:201`:

> *"Só se exporta COLABORADOR: a pessoa nasce aqui como candidata e só passa a
> existir no Tirvu quando é efetivada (decisão do Bruno, 2026-07-19)."*

Quem está em admissão não tem vínculo a criar no Tirvu. Oferecer o botão ali
produziria uma planilha que o Tirvu rejeita ou, pior, importa gente que ainda não
foi contratada. O contrato (CAP-3) fala em *"exportação com o mesmo contrato de
CAP-2"* — o contrato é **a seleção mandar**, não a lista de destinos.

O destino aqui é o `montar_workbook` de `export_planilha.py`, o mesmo que o
destino `excel` de Colaboradores usa.

### A trava do recorte — o ponto mais fácil de errar

`_candidatos_admissao` (`revisao.py:31`) aplica `where(Candidato.situacao.is_(None))`
por padrão, e é isso que separa Admissões de Colaboradores (v1.63 — antes um
registro vazava nas duas telas).

⚠️ **A seleção por `ids` PULA esse filtro se você copiar `_selecionados` como
está.** Em `colaboradores.py`, `ids` é retorno antecipado: busca por id e pronto.
Lá isso é correto — o RH marcou aquelas pessoas. **Aqui não**: um id de
colaborador efetivado, mandado à mão ou vindo de uma lista velha, entraria numa
planilha de admissões sem nada denunciando.

Resolva conferindo `situacao IS NULL` também no caminho por `ids`, e **nomeando**
quem foi recusado — não descarte calado, que é o defeito que esta leva combate.
Um id que não existe e um id que existe mas não é de admissão são coisas
diferentes; a tela pode dizer as duas com a mesma mensagem, mas o teste distingue.

### Onde a tela vive — e por que isso muda o trabalho

**Admissões não tem arquivo próprio.** Ela é renderizada inline dentro de
`PainelConteudo` (`RHApp.jsx:586`), que serve ~20 telas. Estado novo e função de
exportar entram nesse componente grande.

O que já existe lá:

- Estados: `candidatos` (593, também serve de flag de carregamento), `metricas`
  (594), `postos` (596), `filtros` (600, forma `{status, busca, posto_id}`).
- `recarregar` (613-619) limpa valores vazios antes de chamar a API.
- `DashPlanilha` abre na linha **924**: recebe `id="admissoes"`, `colunas`,
  `dados`, `cards`, `acoesLinha`, `filtrosExtras` (927-939), `acoesFiltro`
  (940-957) e `vazio`. **Não recebe `acoesMassa` nem `aoSelecionar`.**
- `acoesFiltro` **já está ocupado**: tem "limpar filtros" (941-945) e o botão de
  exportar (946-956). Acrescente ao que existe, não substitua.

`COLUNAS_ADMISSAO` (259), `cardsAdmissao` (328) e `acoesAdmissao` (367) são
funções de topo de arquivo, fora do componente.

### O que `acoesMassa` deve conter

`acoesMassa` é obrigatório para os checkboxes existirem, mas nesta tela **não há
ação em massa a oferecer** além de exportar — e exportar mora no `.dash-acoes`,
não ali (a 1.1 explicou por quê: aquele bloco só aparece quando há seleção, e
exportar precisa estar alcançável sem ela).

Duas saídas honestas; escolha uma e **registre o porquê na nota de conclusão**:

1. `acoesMassa` devolve um resumo do que está marcado, com o "limpar seleção" que
   o `DashPlanilha` já acrescenta ao lado (`DashPlanilha.jsx:305`). Simples, e a
   barra não fica vazia.
2. `acoesMassa` devolve o mesmo botão de exportar, aceitando a duplicação com o
   do `.dash-acoes` — **não recomendado**: é "dois controles para a mesma
   escolha" (v2.75), o defeito que a 1.1 acabou de eliminar no CSV.

Se nenhuma convencer, o `DashPlanilha` pode ganhar uma prop que ligue os
checkboxes sem exigir `acoesMassa` — mas isso muda um componente compartilhado
por cinco telas, então só faça com motivo escrito.

### ⚠️ Efeito colateral de ligar `acoesMassa`: o CSV muda sozinho

A 1.1 alterou o `exportarCsv` do próprio `DashPlanilha` (`DashPlanilha.jsx:167`):

```js
const fonte = selecionadas.length ? selecionadas : linhas
```

Então, **no instante em que esta história passar `acoesMassa` e a tela ganhar
checkboxes, o botão `⬇ Exportar CSV` passa a respeitar a seleção** — sem ninguém
tocar nele. Isso é o comportamento certo e não precisa de trabalho.

O que precisa de decisão é outra coisa: ele ficará **ao lado do `⬇ Exportar
planilha`** (o xlsx), no mesmo card, com rótulos quase idênticos e conteúdos
diferentes (o CSV traz as colunas VISÍVEIS da tela; o xlsx traz a ficha completa,
~57 campos). Dois controles vizinhos que parecem a mesma coisa e não são.

Resolva **no rótulo**, não no comportamento: deixe claro qual é qual (por
exemplo, "Exportar planilha completa" para o xlsx). É a mesma classe de problema
que a 1.1 resolveu no CSV de Colaboradores — a diferença é que lá os conteúdos
divergiam, e aqui divergem o formato e a profundidade.

### Detalhes que o levantamento achou

- **Falta `URL.revokeObjectURL`** no download atual (`RHApp.jsx:946-956`).
  `Colaboradores.jsx` faz. Vaza um objeto por exportação; corrija de passagem.
- O botão atual **não tem `disabled`** nem estado de erro. Colaboradores usa
  `setErro`/`setAviso` (o `<Aviso>` flutuante). Se acrescentar aviso aqui, use o
  mesmo padrão — `<Aviso>` para resposta a AÇÃO, `.alerta` inline para ESTADO.
- **Chave de linha:** o `DashPlanilha` usa `chaveLinha` (padrão `l.id`) e os
  dicts de admissão têm `id`. Confirmado; `marcados.map((c) => c.id)` funciona.
- A rota registra `admissoes_exportadas` na auditoria (`revisao.py:190`). Mantenha,
  e faça o detalhe dizer se veio de seleção — a 1.1 usa `por_selecao`.
- `montar_workbook` monta as colunas pela **união das chaves das linhas**, não por
  lista fixa. Não é layout de importação; não existe pré-checagem de pendência
  aqui, e não deve existir.

### Testes

**Acrescente ao `backend/tests/test_export_por_selecao.py`** em vez de criar
arquivo novo: é o mesmo assunto, e ele já está no `ci.yml`. Siga a estrutura que
está lá (blocos numerados, `checar()`, limpeza no fim, dados fictícios com sufixo
por execução — o repositório é **público**).

Cobrir:

1. Marcar 2 de 4 candidatos em admissão → a planilha traz aqueles 2, conferidos
   **por nome** dentro do arquivo.
2. Seleção + filtro que não casa com ninguém → a seleção vence.
3. Sem seleção → vale o filtro.
4. **Id de quem NÃO está em admissão** (um colaborador efetivado, `situacao`
   preenchida) → recusado e nomeado, não exportado em silêncio. É o critério da
   "trava do recorte".
5. UUID malformado → 422, nunca 500.

**Mutação obrigatória:** remover a checagem de `situacao IS NULL` do caminho por
`ids`. O teste tem que reprovar. Confirme que ele **imprimiu** o resultado —
ausência de falha não é aprovação (v2.72.2).

**Ambiente:** precisa dos containers (`pg-teste` em 55432, `minio-teste` em
59000) e das migrations aplicadas. A 1.1 registrou que o Docker pode estar
desligado.

**Tela:** ao acrescentar coluna de seleção, rode
`frontend/tests/e2e/tabelas-cabem-na-tela.spec.js` com `--workers=1` — a coluna
nova consome largura, e acrescentar controle a essa área já estourou a tela antes
(v2.59). Admissões está na lista `TELAS` daquele teste.

### Regressões a não causar

- A tela de Colaboradores **não muda** nesta história. Se precisar mexer no
  `DashPlanilha`, confira que Creche, Jornadas, Talentos e Colaboradores seguem
  funcionando — são cinco consumidores.
- O `GET /rh/candidatos-exportar` continua servindo (AC3).
- A separação Admissões × Colaboradores (v1.63) é o invariante mais importante
  aqui: um registro aparece numa tela só.

### Project Structure Notes

| Arquivo | Natureza |
|---|---|
| `backend/app/api/revisao.py` | UPDATE — rota POST com `ids`, trava de recorte |
| `frontend/src/rh/RHApp.jsx` | UPDATE — estado da seleção, `acoesMassa`, `aoSelecionar`, botão com contagem |
| `frontend/src/api.js` | UPDATE — `exportarAdmissoes` aceita `ids` e usa POST |
| `backend/tests/test_export_por_selecao.py` | UPDATE — blocos de Admissões |

Fora de escopo: destinos Tirvu/Dexion em Admissões (regra de negócio, ver acima);
`export_planilha.py`; a tela de Colaboradores.

### References

- [Source: docs/planejamento/19-feedbacks-24a-leva.md#CAP-3] — contrato
- [Source: docs/planejamento/22-historia-1-1-exportar-por-selecao.md] — o contrato
  de seleção, a medição dos 8 KB e a decisão do `aoSelecionar`
- [Source: backend/app/api/colaboradores.py] — comentário da linha 201, a regra de
  que só colaborador vai ao Tirvu
- [Source: CLAUDE.md] — Admissões filtra `situacao IS NULL` (v1.63); seleção no
  corpo, nunca na querystring (v3.17); nada que age mora em bloco que se recolhe

## Dev Agent Record

### Agent Model Used

claude-opus-5 (1M context)

### Debug Log References

- Containers efêmeros recriados (foram removidos ao fim da 1.1) e migrations
  aplicadas antes de rodar o teste.
- O teste quebrou na primeira execução por um detalhe de layout: a planilha do
  RH (`export_planilha`) usa a coluna **"Nome completo"**, com minúscula, e a do
  Tirvu usa **"Nome Completo"**. O helper ganhou parâmetro e uma nota explicando.

### Completion Notes List

**Duas lacunas, não uma.** Admissões não tinha exportação por seleção porque não
tinha **seleção nenhuma**: o `DashPlanilha` só renderiza a coluna de checkbox
quando recebe `acoesMassa`, e a tela não passava essa prop. `aoSelecionar`
sozinho não resolveria — dispararia sempre com lista vazia.

**Decisão registrada: o que `acoesMassa` devolve.** Esta tela não tem ação em
massa a oferecer além de exportar, e exportar mora no card de ações (sempre
visível), não no bloco de seleção (que só existe quando há alguém marcado).
Escolhida a opção 1 da história: `acoesMassa` devolve um **resumo** do que está
marcado, apontando para o botão. Assim os checkboxes existem, a barra não fica
vazia, e não se cria um segundo controle de exportar — que seria "dois controles
para a mesma escolha" (v2.75), o defeito que a 1.1 acabou de eliminar no CSV.

**A trava do recorte — o ponto que a história marcou como mais fácil de errar.**
Copiar `_selecionados` de `colaboradores.py` teria deixado um **colaborador
efetivado entrar numa planilha de ADMISSÕES**, calado. Lá `ids` é retorno
antecipado e ignora os demais filtros, o que é correto (o RH marcou aquelas
pessoas); aqui o recorte `situacao IS NULL` é a identidade da tela (v1.63). A
rota confere `situacao is None` também no caminho por `ids`, e **nomeia** quem
recusou: cabeçalho `X-Fora-Do-Recorte`, mesmo desenho do `X-Tirvu-Pendencias`.

**Escopo respeitado: nada de Tirvu ou Dexion aqui.** Não é esquecimento — quem
está em admissão não tem vínculo a criar no Tirvu (decisão do Bruno, 2026-07-19,
registrada em `colaboradores.py:201`). O destino é a planilha do RH.

**Rótulos distinguem os dois botões vizinhos.** Ao ligar `acoesMassa`, o
`⬇ Exportar CSV` do próprio dash passou a respeitar a seleção **sozinho** (efeito
da 1.1, `DashPlanilha.jsx:167`). Ele ficaria ao lado do xlsx com rótulos quase
idênticos e conteúdos diferentes: o CSV traz as colunas VISÍVEIS; o xlsx traz a
ficha completa (~57 campos). Daí **"Exportar planilha completa"**, e o `title` de
cada um dizendo o que leva.

**Corrigido de passagem:** faltava `URL.revokeObjectURL` no download de Admissões
(Colaboradores já fazia) — vazava um objeto por exportação.

**Mutações validadas** (as duas reprovaram, nomeando o defeito):

| Mutação | O que o teste disse |
|---|---|
| tirar a trava do recorte (cópia cega de Colaboradores) | "vazou: Pessoa Teste 0 …" e "veio '0'" no cabeçalho |
| ignorar `ids` e cair nos filtros | "vazaram: Candidato Teste 2, Candidato Teste 3" |

**Verificação:** 14 blocos no `test_export_por_selecao.py` (os 8 da 1.1 mais 6 de
Admissões), conferindo nomes DENTRO da planilha. Smoke 15/15;
`test_permissoes_declaradas`, `test_api_front_existe`, `test_design_system`,
`test_export_tirvu` e `test_documento_especifico` OK. No navegador: os checkboxes
aparecem, o rótulo mostra a contagem e a requisição sai por POST com os ids no
corpo. As 12 medições da régua de largura passam **com a coluna nova**.

### File List

| Arquivo | O quê |
|---|---|
| `backend/app/api/revisao.py` | `SelecaoAdmissoesIn`, rota POST com a trava de recorte |
| `frontend/src/api.js` | `exportarAdmissoesSelecao` (POST, corpo JSON) |
| `frontend/src/rh/RHApp.jsx` | estado `marcados`, `acoesMassa`, `aoSelecionar`, botão com contagem, `revokeObjectURL` |
| `backend/tests/test_export_por_selecao.py` | 6 blocos de Admissões, 2 mutações validadas |
| `frontend/tests/e2e/_exportar-respeita-selecao.spec.js` | caso de Admissões |

### Change Log

- 02/09/2026 — História 1.2 implementada. Admissões ganhou seleção e exporta
  exatamente quem está marcado, sem afrouxar o recorte da tela.
