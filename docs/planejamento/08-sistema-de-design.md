# Sistema de Design e Identidade — Portal de RH Green House

> **Para que este documento existe:** o Bruno cansou de padronizar tela a tela.
> Toda leva nova vinha "sem respiro", com padding chutado no olho e cada módulo
> reinventando espaçamento. Este é o contrato: **daqui pra frente, tela nova
> nasce padronizada porque consome os tokens e as primitivas daqui — não porque
> alguém lembrou de ajustar depois.** Se você (ou o assistente) for criar ou
> mexer numa tela do RH, leia isto antes.

Fonte única de estilo: [`frontend/src/styles.css`](../../frontend/src/styles.css).
Não existe outro CSS, não existe CSS-in-JS, não existe Tailwind. Uma folha só.

---

## 1. Princípio: nunca chute um valor

O `styles.css` **já tem** uma escala completa de tokens. O erro histórico não foi
falta de sistema — foi **não usar o sistema**. Os módulos das Ondas B/C saíram
cheios de `style={{ margin: '.4rem 0 1rem' }}` e `padding: 1.1rem 1.2rem` no
olho. Isso é o que causa o "sem respiro" e a falta de uniformidade.

**Regra de ouro:** se você está escrevendo um número de espaçamento, tamanho de
fonte, cor, raio ou sombra **direto no JSX ou como valor solto no CSS**, pare —
existe um token. Use o token. `style` inline para espaçamento é dívida técnica.

### Tokens de espaçamento (escala de 4px)

| Token | Valor | Uso típico |
|-------|-------|-----------|
| `--esp-1` | .25rem (4px) | respiro mínimo entre ícone e texto |
| `--esp-2` | .5rem (8px) | gap dentro de um controle |
| `--esp-3` | .75rem (12px) | gap entre cards / itens de lista |
| `--esp-4` | 1rem (16px) | padding interno de card |
| `--esp-6` | 1.5rem (24px) | separação entre seções |
| `--esp-8` | 2rem (32px) | respiro de página |

### Tokens de tipografia

`--fs-titulo` (1.55rem) · `--fs-sub` (1.2rem) · `--fs-secao` (1.02rem) ·
`--fs-corpo` (1rem — **16px, evita zoom no iOS, nunca use menos em input**) ·
`--fs-apoio` (.875rem) · `--fs-mini` (.78rem). Fonte: `--fonte` (Outfit).
Alvo de toque mínimo: `--toque` (50px).

### Tokens de cor

Marca: `--verde` `--verde-vivo` `--verde-escuro` `--verde-suave` · Tinta (texto
forte): `--tinta` · Texto: `--texto` `--cinza-txt` · Superfícies: `--cartao`
`--fundo` `--borda` `--borda-suave` `--input-bg` `--hover` · Semânticas:
`--ok`/`--ok-suave` (verde), `--atencao`/`--atencao-suave` (âmbar),
`--perigo`/`--perigo-suave` (vermelho).

**Nunca escreva `#hex` no JSX.** Se precisa de cor de estado, use o par
semântico. Os `style={{ color: '#d9534f' }}` espalhados são legado a eliminar,
não padrão a copiar.

### Raio e sombra

`--raio` (18px, cards grandes) · `--raio-input` (13px) · `--raio-botao` (14px) ·
`--raio-chip` (999px) · `--sombra-cartao` · `--sombra-verde`.

---

## 2. Primitivas de layout (o "respiro" vem daqui)

O respiro da página **não é responsabilidade do módulo** — é da primitiva que o
envolve. Um módulo do RH que renderiza `<section>` cru dentro do `.rh-conteudo`
fica colado na borda porque o `.rh-conteudo` não tem padding lateral no desktop.
Foi exatamente o que aconteceu com Desenvolvimento/Desempenho/Avaliações.

### `.rh-painel` / `.pagina` — o wrapper de página do RH

Todo módulo do painel do RH deve renderizar dentro de um wrapper de página, que
carrega **max-width (não deixa a linha ficar quilométrica), centragem e o padding
de respiro**. As telas antigas (Admissões) já usam `<main className="rh-painel">`.
As novas devem usar `.pagina` (o mesmo respiro, nome semântico de página de
módulo).

```jsx
// CERTO — a página nasce com respiro
export default function MeuModulo() {
  return (
    <section className="pagina">
      <div className="rh-topo"><h1>🎓 Título</h1><button>← voltar</button></div>
      ...
    </section>
  )
}
```

```jsx
// ERRADO — <section> cru, sem respiro, cola na borda
<section>
  <div className="rh-topo">...</div>
</section>
```

### `.rh-card` — bloco de conteúdo

Card padrão: fundo `--cartao`, borda fina, `--raio`, padding via token. Já
existe. Use para agrupar formulário, detalhe, histórico. **Não** recrie o
padding do card com `style` inline.

### `.rh-grid-2` — duas colunas no desktop

Para aproveitar a largura em vez de empilhar tudo num pergaminho. Vira 1 coluna
no mobile automaticamente.

### `.rh-topo` — cabeçalho da página

Título à esquerda, ações à direita, quebra no mobile. Todo módulo abre com ele.

---

## 3. Dark mode: a regra que faltava

O tema é controlado por `:root[data-tema='escuro']` (atributo no `<html>`,
gravado pelo [`Tema.jsx`](../../frontend/src/Tema.jsx)). Os tokens todos têm par
escuro. **Mas há uma armadilha nativa:** o menu suspenso do `<select>` é pintado
pelo sistema operacional, fora do CSS. Sem uma declaração explícita, no Windows
ele vinha com fundo claro e texto claro do tema → **ilegível** (o feedback do
Bruno: "o contraste não dá pra ler").

**Solução (já aplicada):** `color-scheme` declarado no `:root` e no tema escuro.
Isso faz o navegador pintar os controles nativos (dropdown do select, scrollbar,
date picker) no esquema certo automaticamente. **Nunca remova essa linha** e
**nunca** estilize `<option>` com cores fixas — deixe o `color-scheme` cuidar.

**Armadilha do "token fantasma":** `var(--verde-claro, #eaf5ec)` referencia um
token que **não existe** — então o fallback fixo `#eaf5ec` (claro) vale nos DOIS
temas. No dark mode isso vira texto claro sobre fundo claro, ilegível (foi o bug
do dropdown `.select-busca`). **Nunca dependa de fallback de cor fixa.** Use
sempre um token que existe e inverte com o tema — para realce de item/hover, o
`--verde-suave` (claro no light, escuro no dark) é o certo, e fixe o texto num
token (`--tinta`), não deixe herdar. Componentes CUSTOMIZADOS (dropdown próprio,
`.select-busca`) **não** são cobertos pelo `color-scheme` — só os nativos são;
estes você estiliza à mão com tokens que invertem.

Ao criar tela nova: teste no claro **e** no escuro antes de dar por pronta.
Abrir um `<select>` nativo E um dropdown customizado (`.select-busca`) no escuro
é o teste mínimo.

**O token fantasma não é hipótese — aconteceu, e ficou meses na base** (v2.46).
`var(--texto-suave, #47554d)` estava em 4 regras e o token **nunca existiu**:
o fallback escuro valia nos dois temas e dava **2,09:1** de contraste no escuro
(mínimo AA: 4,5:1), nas opções de questão das Provas. Junto com ele,
`--tinta-suave` (12 usos) não tinha par escuro: 3,61:1. Três regras que ficam:

1. **Nunca escreva fallback de cor em `var()`.** Se o token não existe, defina-o.
   O fallback existe para dar sobrevida a valor ausente — em cor, ele apenas
   esconde o defeito e o congela no tema claro.
2. **Todo token de cor precisa de par em `:root[data-tema='escuro']`.** Definir
   só no `:root` é meio-caminho: o token existe, o `grep` acha, e mesmo assim
   quebra no escuro.
3. **Meça, não olhe.** Contraste se confere com `getComputedStyle` + fórmula
   WCAG num navegador de verdade (o Playwright já está no projeto). O tema
   escuro engana o olho: texto cinza sobre fundo escuro *parece* legível.

### Foco visível: `outline: none` exige substituto

Remover o outline sem repor indicação nenhuma deixa quem navega por teclado sem
saber onde está. Aconteceu em dois pontos centrais (v2.46): no
`.select-busca-input` (o campo de busca de **todos** os filtros do painel) e no
`.ajuda-q` (o ⓘ do glossário, cujo realce era um hex fixo, invisível no escuro).
O substituto não precisa ser o anel de 4px da regra global — uma borda inferior
reforçada ou um `:focus-visible` próprio bastam. O que não pode é não haver nada.

---

## 4. Editar/criar SEMPRE perto do item

Regra de negócio de UX, decidida com o Bruno e repetida em várias levas:
**quando a pessoa clica para editar/detalhar algo numa lista, o formulário abre
PERTO DO ITEM — nunca no topo da página.** Abrir no topo tira a pessoa do
contexto: ela clicou no fulano lá embaixo e a tela pula pro começo.

**"Perto do item" admite DUAS formas** (revisado em v1.97, feedback
2026-07-27 — anotações do CRM):

1. **Inline, na própria linha** — a forma padrão, para conteúdo **curto** que
   cabe numa linha de tabela ou card. Em listas com
   [`DashPlanilha`](../../frontend/src/rh/DashPlanilha.jsx): use a prop
   `linhaExpandida` — o painel abre numa `<tr>` logo abaixo da linha clicada
   (padrão desde v1.83). Catálogos que são cards empilhados (não tabela): o
   form inline abre junto do card sendo editado.
2. **Modal ANCORADO** ([`Modal.jsx`](../../frontend/src/Modal.jsx)) — quando o
   conteúdo tem **anexo + histórico + texto longo**, que não cabe espremido
   numa linha (ex.: anotações do mini-CRM, que rolavam na horizontal dentro da
   tabela). O modal mostra o nome da pessoa/item no cabeçalho — não perde o
   contexto, só ganha espaço. **Continua proibido** o formulário solto no topo
   da página, sem âncora nenhuma ao item.

Critério de escolha: se o conteúdo cabe numa linha sem rolagem, é inline. Se
tem anexo, histórico de itens, ou texto que precisa de `<textarea>` maior, é
modal. Na dúvida, comece inline — só migre para modal se o inline atual
estiver comprovadamente ruim (espremido, rolando, difícil de usar).

- **Criar registro novo** também deve abrir perto do gatilho, não no topo
  distante. Se o botão "＋ Novo" está acima da tabela, o form pode abrir ali
  colado ao botão — o que não pode é o form aparecer no topo enquanto a pessoa
  rolou a lista pra baixo.

Abas ativas usam a classe **`ativa`** (não `on`, não `active`).

---

## 5. Overflow: nada estoura a tela

Tela estourando a margem lateral é defeito, sempre. Regras:

- **Tabela larga** vai dentro de um container com `overflow-x: auto` que **rola
  dentro de si**, nunca empurra o body. O `DashPlanilha` já faz isso com
  `.dash-scroll` + `container-type: inline-size`. Tabela `.rh-tabela` solta (sem
  esse wrapper) é candidata a estourar — prefira o DashPlanilha ou envolva a
  tabela num `.dash-scroll`.
  **⚠️ Não tente resolver pondo `overflow-x` na própria `<table>`** (medido com
  Playwright em v2.46): `display: table` **ignora** `overflow`, e a página
  estoura exatamente igual. O wrapper não é preferência de estilo — é o único
  jeito que funciona. Situação atual da base: ~35 das 40 tabelas são escritas à
  mão e estão sem wrapper; acima de 800px elas estão desprotegidas (entre
  480–800px a media query as põe em `display:block`, e aí sim o overflow vale;
  abaixo de 480px viram card).
- **Coluna de texto longo** (cargos, descrição de jornada, motivos): marque
  `quebra: true` na config do DashPlanilha (`white-space: normal; max-width`),
  senão a célula estica a tabela toda.
- **No mobile**, `.rh-tabela` vira card automaticamente (`responsivo.js` carimba
  `data-rotulo`). Não escreva `<table>` à mão — use o DashPlanilha, que já herda
  esse comportamento.
- **Painéis expansíveis** (histórico, auditoria, logs): o conteúdo interno
  também tem que caber. Lista longa quebra linha; se tiver estrutura tabular,
  vai num `.dash-scroll`.

---

## 6. Conteúdo que abre TEM que fechar (toggle)

### `<details>`: a regra base é do `styles.css`, não do JSX

Antes da v2.47.1 não havia regra para `<summary>`, e cada tela remendava por
conta própria: **três telas repetiam `style={{ cursor: 'pointer' }}`** e outras
três, `style={{ marginTop: '.6rem' }}` — dívida que se multiplicava a cada
`<details>` novo. Agora o `styles.css` define:

- `summary { cursor: pointer; list-style-position: inside }` — **`inside` é
  obrigatório**: com o `outside` do navegador o marcador ▸ é desenhado FORA da
  caixa de conteúdo, encosta na borda do card e fura o alinhamento da página
  (defeito real, pego pelo Bruno num print da v2.47).
- `summary:focus-visible` com anel — navegação por teclado.
- `details:not([class])` ganha `margin-top` — o dobrável **solto**, sem classe.
  O `:not([class])` é essencial: `.ficha-rh-secao` e `.rh-card` já definem o
  próprio espaçamento, e uma regra global sobrescrevia o deles (as seções da
  ficha foram de 8px para 12px numa versão intermediária — regressão em tela
  que estava certa).
- `details.rh-card > summary` — variante "seção dobrável", o card inteiro é o
  `<details>`.

Ao criar um `<details>`: **não escreva `cursor`, `list-style` nem margem no
JSX.** Se precisar de comportamento diferente, dê uma classe a ele e estilize
a classe.

### Bloco de topo deve respiro ao seguinte

Todo `.rh-card` traz `margin-bottom: var(--esp-3)`. Blocos de topo que **não**
são cards precisam declarar o seu: a `.rh-revisao` (a lista de documentos do
`Detalhe`) não tinha, e o defeito só apareceu quando ela deixou de ser o último
elemento da tela — o card do posto ficou colado nela. Ao mover um bloco de
lugar, confira o respiro dos dois lados.

Todo "ver histórico / ver detalhe / ver mais" que **abre** ao clicar precisa
**fechar** ao clicar de novo. Botão que só abre e nunca recolhe deixa a tela
entulhada e foi reclamação explícita do Bruno no histórico de decisões. Padrão:
o mesmo botão alterna (o rótulo vira "ocultar/fechar" quando aberto), ou é um
`<details>` nativo.

---

## 6b. Campos de data: SEMPRE com máscara

Todo campo onde a pessoa **digita** uma data usa o componente central
[`InputData.jsx`](../../frontend/src/InputData.jsx) — nunca um `<input>` livre.
Ele insere as barras conforme digita (`dd/mm/aaaa`), **valida que a data existe**
(rejeita 31/02, ano absurdo, data incompleta) e guarda ISO (`aaaa-mm-dd`) por
baixo. Sem isso, dá para salvar `20122025` cru — foi um bug real (nascimento de
filho de brigadista gravado errado). As funções de máscara/validação
(`fmtDataBR`/`isoParaBR`/`brParaISO`) vivem em `fmt.js`, junto de CPF/telefone —
**não reimplemente máscara de data em lugar nenhum**. Para escolher uma data de
calendário (sem digitação), `<input type="date">` é aceitável.

## 6c. Barra de filtros: grade compacta, tudo com busca

Listas do RH filtram pela barra do `DashPlanilha` — declare `filtro` na config
da coluna (`'texto'` ou `'select'`) e a barra se monta sozinha. Ela é uma
**grade compacta** (vários filtros por linha, rótulo pequeno em cima), nunca uma
linha por filtro. Todo filtro `'select'` vira `SelectBusca` (começa a digitar e
a lista filtra) — filtro é funcional, a pessoa não deve rolar 300 opções. Não
escreva barra de filtro à mão: use a config de colunas do DashPlanilha.

**Filtro server-side entra na MESMA barra, via `filtrosExtras`** (2026-07-30).
Filtro que recarrega a API (status do creche, posto dos colaboradores) não pode
virar filtro de coluna — a base é a folha inteira, e trazer tudo ao cliente é
regressão de performance e de LGPD. Mas ele também não pode morar num card
próprio acima do dash: era assim no Reembolso-Creche e o Bruno resumiu o
problema —

> *"tem dois cards, acho que apenas um, tudo concentrado e coeso de filtros,
> seria mais interessante"*

Havia **duas caixas de status na mesma tela**, uma acima da outra, e filtrar por
uma enquanto a outra dizia coisa diferente dava resultado que parecia errado.
Passe esses filtros em `filtrosExtras={[{chave, rotulo, valor, opcoes, aoMudar}]}`
— eles aparecem na grade, com o mesmo `SelectBusca`, antes dos de coluna.

**Regra que vem junto: um assunto, um controle.** Se o filtro do pai já cobre
uma coluna, tire o `filtro:` daquela coluna (a coluna segue ordenável, e os
cards clicáveis continuam funcionando, porque a filtragem em memória roda sobre
todas as colunas, não só as que declaram `filtro`). Dois controles para o mesmo
campo é pior do que dois cards.

## 5b. Ordem da tela: agrupe por NATUREZA, não por ordem histórica

Tela que cresce por acréscimo vira pilha: cada leva põe um bloco no fim, e a
ordem final não é decisão de ninguém — é a cronologia do desenvolvimento. Foi o
que aconteceu no `Detalhe.jsx` (v2.47): **15 blocos, e seis deles de consulta
enfiados entre as duas coisas que o RH mais usa** (conferir documento e
corrigir cadastro). Ele aprovava embaixo, rolava para cima para acertar o posto
e voltava.

O diagnóstico ingênuo era "a fila está por último, suba ela". Errado: subir a
fila só inverteria quem fica longe de quem. **O custo estava na distância entre
as duas atividades, não na posição de uma delas.**

Regra: separe **trabalho** de **consulta**, mantenha juntas as coisas que a
pessoa alterna numa mesma visita, e mande o que não é diário para um
`<details>` fechado no fim (`details.rh-card`, que já tem estilo de resumo
clicável). No `Detalhe` ficaram três faixas: **documentos · cadastro ·
consulta (fechada)**.

Antes de reordenar uma tela, **pergunte ao usuário o que ele foi fazer ali** —
com peso, não com "depende". A resposta muda o desenho: uma atividade dominante
pede hierarquia; duas de peso igual pedem proximidade.

## 5c. Bloco condicional: "carregando" e "vazio" são estados DIFERENTES

`if (!dados) return null` esconde os dois casos na mesma linha — e o bloco some
enquanto a API responde, fazendo o conteúdo abaixo **pular na cara** de quem já
estava lendo. É uma das causas do "hora segue o padrão, hora não": a mesma
pessoa aberta duas vezes mostra quantidades diferentes de blocos.

- **Some porque não se aplica** àquela pessoa → pode sumir. Mantém a densidade
  baixa, e é o comportamento escolhido pelo Bruno.
- **Some porque está carregando** → tem que **reservar o lugar** (card com
  "Carregando…"), sobretudo se for uma das áreas principais da tela.

```jsx
if (itens === null) return <div className="rh-card"><p className="explica">Carregando…</p></div>
if (itens.length === 0) return null   // não se aplica: pode sumir
```

Grade de 2 colunas com um filho condicional deixa **meia linha vazia** quando
ele devolve `null`. Use `.rh-grid-auto` (auto-fit), que adapta a quantidade de
colunas ao que existe de fato.

## 6d. Falha de carga é ERRO na tela, nunca "Carregando…" eterno

`api.x().then(setDados).catch(() => setDados(null))` é armadilha: `null` é o
mesmo valor de "ainda carregando", então a tela fica em **"Carregando…" para
sempre** — indistinguível de rede lenta, sem retry, sem uma palavra. Estava em
`Detalhe.jsx` (a tela mais usada do painel), no `Diagnostico.jsx` (a ferramenta
que existe *para* investigar falhas) e na Telemetria (v2.46).

O padrão certo já existia em `Detalhe.jsx::FichaRH`: **estado de erro separado**
do estado de dados, mensagem em `.alerta` e botão **"tentar de novo"**. Duas
sutilezas que vieram do conserto:

- **Tela de monitoramento ANUNCIA a falha** (telemetria, logs, diagnóstico). Se
  o resumo não carregou e a tela fica muda, o RH lê "nenhum erro" onde na
  verdade é "não consegui saber" — o oposto do que a tela existe para dizer.
- **Se a mesma função de recarregar também roda depois de AÇÕES** (aprovar,
  salvar, rejeitar), o `catch` de carga vai só no `useEffect` inicial. Senão um
  erro de ação substitui a tela inteira por uma mensagem e apaga o trabalho em
  curso — o erro de ação já tem o seu próprio canal (`msg` perto do botão, §
  "mensagem perto do botão que a gerou").

### O critério é DISTÂNCIA, não "sempre local"

A v1.96 cravou "mensagem perto do botão que a gerou". A v2.47 mostrou que a
regra vazou para outros componentes da mesma tela: o **"Salvar posto"**, no
card do meio do `Detalhe`, mandava a confirmação para a mensagem global do
topo — a pessoa salva olhando para o meio e o resultado aparece onde ela não
está. Mesmo defeito, quatro anos-luz do lugar certo.

Mas **não converta tudo em mensagem local**. O critério é a distância entre o
botão e o lugar onde a mensagem sai:

- Componente **colado no topo** (linha de contato, informativo logo abaixo do
  cabeçalho) → a global serve, e evita espalhar estado.
- Componente **longe do topo**, dentro de `<details>`, ou numa tela que rola →
  mensagem **local**, renderizada dentro do próprio card.

Ao **mover** um bloco de lugar, reavalie: um card que estava no topo e foi para
o rodapé passa a precisar de mensagem local (aconteceu com `FichasStatus`).

## 7. Tooltips e ajuda: um padrão só

Dois níveis, ambos por CSS (nunca por estado/onClick), sempre no hover e some ao
tirar o mouse (no celular, `:focus-within` cobre o toque):

- **Referência curta** (glossário do RH, significado de termo): componente
  [`Ajuda.jsx`](../../frontend/src/Ajuda.jsx) — `<Ajuda termo="...">` ou
  `<span className="ajuda-q" data-dica="...">`. É o `ⓘ`/`?` ao lado do rótulo.
- **`title=` nativo** para dica de uma linha em botão/ícone.

**Módulo novo do RH deve ter ajuda nos termos de negócio.** As Ondas B/C saíram
sem `<Ajuda>` — é lacuna, não estilo. Ao adicionar um termo que o RH pode não
conhecer ("calibração", "desvio do avaliador", "fato observado", "reciclagem"),
ponha um `<Ajuda>`.

**Exceção:** as dicas LONGAS expansíveis de "como conseguir o documento" (wizard
do candidato) abrem no CLIQUE de propósito — texto longo que a pessoa lê enquanto
age no celular; hover as faria sumir no meio do passo a passo.

### O glossário explica a CONSEQUÊNCIA, não a palavra

Uma definição de dicionário não ajuda quem está decidindo. Compare:

- ❌ *"Manifestação: ato de manifestar-se sobre a avaliação."*
- ✅ *"Manifestação: o direito do colaborador de registrar a própria opinião
  sobre a avaliação recebida (seção 9 da cartilha). Tem prazo de 7 dias —
  passado ele, o RH pode homologar assim mesmo."*

A segunda diz o que muda na vida de quem lê. Quando o termo vem de norma ou de
instrumento oficial (cartilha, IN, CLT), **cite a origem** — é o que permite ao
RH defender a decisão depois.

### Tour guiado (`driver.js`)

Há dois, com chaves de `localStorage` separadas: painel do RH
([`rh/tour.js`](../../frontend/src/rh/tour.js), `tour_rh_visto`) e wizard do
candidato (`tour_visto`). Dispara uma vez na primeira visita e fica acessível
para rever — no rodapé do menu, no RH.

Três regras vindas de defeito real (v2.49):

1. **Ancore em elemento que existe sempre.** `element` não encontrado faz o
   `driver.js` **pular o passo em silêncio**: o tour encolhe e ninguém percebe.
   Use sidebar e cabeçalho, não card que depende de dados. Ao mexer, conte os
   passos exibidos.
2. **O `driver.css` não conhece o tema.** Ele traz cores fixas e não expõe
   variável de cor — as classes `.driver-popover*` estão sobrescritas no
   `styles.css` com os tokens da casa. Sem isso o balão sai branco no escuro
   (foi assim no tour do candidato por meses).
3. **`progressText: '{{current}} de {{total}}'`** — o padrão é "2 of 5".

Cada passo deve dizer **o que a pessoa ganha**, não o que a tela é.

---

## 8. Botões

- `.btn-principal` — ação primária da tela (verde cheio). Uma por contexto.
- `.btn-secundario` — ação secundária (contorno).
- `.btn-link` — ação terciária/textual (voltar, cancelar, "ver X").
- `.btn-mini` — variante compacta, para dentro de linhas/lotes.
- Ação pesada (dossiê, notificar, efetivar, gerar PDF): use `comAmpulheta()` /
  overlay `Carregando.jsx` (só aparece após 400ms, evita flicker) e trate o 409
  de idempotência (`e.amigavel`).

Alvo de toque mínimo `--toque` (50px) — não faça botão menor que isso no que o
candidato toca no celular.

---

## 8b. O checklist tem guarda-corpo automático

Desde a v2.48, `backend/tests/test_design_system.py` cobra por você as regras
deste documento que já custaram correção — e **roda no CI**, antes mesmo da
stack subir:

```bash
cd backend && PYTHONPATH=. .venv/Scripts/python.exe tests/test_design_system.py
```

O que ele reprova: classe usada no JSX que não existe no `styles.css` (§ v2.25)
· `var(--token)` inexistente e **fallback de cor** em `var()` (§3) · token de
superfície sem par no tema escuro (§3) · `.rh-tabela` fora do `.dash-scroll`
(§5) · `<details>` com `cursor`/margem no JSX (§6).

**O que ele deliberadamente NÃO reprova:** os ~560 `style` inline de
espaçamento. É dívida herdada — transformá-la em erro de CI travaria o projeto
sem consertar nada. Ela é paga tela a tela, e o CHANGELOG registra o saldo.

Isso não substitui o checklist abaixo: contraste, dark mode de verdade,
hierarquia visual e "abri a tela e olhei" continuam sendo trabalho humano.

## 9. Checklist de tela nova (cole no PR mental)

Antes de dar uma tela do RH por pronta:

- [ ] Renderiza dentro de `.pagina` (ou `.rh-painel`) — tem respiro lateral.
- [ ] Zero `style={{ margin/padding/... }}` inline de espaçamento — usei tokens.
- [ ] Zero `#hex` no JSX — usei tokens de cor semânticos.
- [ ] Lista é `DashPlanilha`, não `<table>` à mão.
- [ ] Editar/criar abre **perto do item** — inline ou modal ancorado — nunca solto no topo.
- [ ] Nada estoura a tela na horizontal (testei numa largura de celular).
- [ ] Tudo que abre, fecha (toggle).
- [ ] Testei no **tema escuro**, inclusive abrindo um `<select>`.
- [ ] Todo token de cor que usei tem par no `:root[data-tema='escuro']` — e
      **nenhum `var()` meu tem fallback de cor**.
- [ ] Falha de carga mostra **erro + "tentar de novo"**, não "Carregando…" eterno.
- [ ] Bloco condicional distingue **carregando** (reserva o lugar) de **vazio**
      (pode sumir) — não `if (!x) return null` para os dois.
- [ ] A mensagem de cada ação sai **onde a pessoa está olhando** (critério:
      distância do botão, não "sempre local").
- [ ] **Abri a tela renderizada** e conferi a hierarquia — qual botão domina, o
      que quebra em duas linhas, o que ficou vazio. O código não mostra isso.
- [ ] Botão só com ícone/símbolo tem `aria-label` dizendo **qual item** ele afeta.
- [ ] Se removi `outline`, repus indicação de foco.
- [ ] Termos de negócio têm `<Ajuda>`.
- [ ] Abas usam a classe `ativa`.
- [ ] Vira card no mobile de forma legível.

---

## 10. Identidade visual (marca)

- **Cor da marca:** verde Green House (`--verde #16c464` e a família). O verde é
  ação e afirmação; âmbar é atenção; vermelho é perigo/erro. Cor só onde há
  **significado** — o painel do RH é "plano e sutil" (bordas finas, sem sombras
  grandes), decisão validada com o Bruno. O portal do candidato é mais acolhedor.
- **Tipografia:** Outfit em toda a interface.
- **Tom de voz:** pt-BR, direto e respeitoso. Termos de negócio não viram
  sinônimo — explicam-se com tooltip. Mensagem de erro fala com a pessoa, não com
  o log.
- **Logo/identidade configurável:** a plataforma é de RH, não só da Green House;
  a identidade visual é configurável para desvincular a marca quando preciso.

> Este documento é vivo. Ao mudar um padrão com o Bruno, atualize aqui **e** no
> `CLAUDE.md` — senão a próxima leva volta a divergir e a dor recomeça.
