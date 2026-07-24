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

Ao criar tela nova: teste no claro **e** no escuro antes de dar por pronta.
Abrir um `<select>` no escuro é o teste mínimo.

---

## 4. Editar/criar SEMPRE perto do item

Regra de negócio de UX, decidida com o Bruno e repetida em várias levas:
**quando a pessoa clica para editar/detalhar algo numa lista, o formulário abre
NA PRÓPRIA LINHA, logo abaixo do item — nunca no topo da página.** Abrir no topo
tira a pessoa do contexto: ela clicou no fulano lá embaixo e a tela pula pro
começo.

- Em listas com [`DashPlanilha`](../../frontend/src/rh/DashPlanilha.jsx): use a
  prop `linhaExpandida` — o painel abre numa `<tr>` logo abaixo da linha clicada
  (padrão desde v1.83).
- **Criar registro novo** também deve abrir perto do gatilho, não no topo
  distante. Se o botão "＋ Novo" está acima da tabela, o form pode abrir ali
  colado ao botão — o que não pode é o form aparecer no topo enquanto a pessoa
  rolou a lista pra baixo.
- Catálogos que são cards empilhados (não tabela): o form inline abre junto do
  card sendo editado.

Abas ativas usam a classe **`ativa`** (não `on`, não `active`).

---

## 5. Overflow: nada estoura a tela

Tela estourando a margem lateral é defeito, sempre. Regras:

- **Tabela larga** vai dentro de um container com `overflow-x: auto` que **rola
  dentro de si**, nunca empurra o body. O `DashPlanilha` já faz isso com
  `.dash-scroll` + `container-type: inline-size`. Tabela `.rh-tabela` solta (sem
  esse wrapper) é candidata a estourar — prefira o DashPlanilha ou envolva a
  tabela num `.dash-scroll`.
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

Todo "ver histórico / ver detalhe / ver mais" que **abre** ao clicar precisa
**fechar** ao clicar de novo. Botão que só abre e nunca recolhe deixa a tela
entulhada e foi reclamação explícita do Bruno no histórico de decisões. Padrão:
o mesmo botão alterna (o rótulo vira "ocultar/fechar" quando aberto), ou é um
`<details>` nativo.

---

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

## 9. Checklist de tela nova (cole no PR mental)

Antes de dar uma tela do RH por pronta:

- [ ] Renderiza dentro de `.pagina` (ou `.rh-painel`) — tem respiro lateral.
- [ ] Zero `style={{ margin/padding/... }}` inline de espaçamento — usei tokens.
- [ ] Zero `#hex` no JSX — usei tokens de cor semânticos.
- [ ] Lista é `DashPlanilha`, não `<table>` à mão.
- [ ] Editar/criar abre **perto do item**, não no topo.
- [ ] Nada estoura a tela na horizontal (testei numa largura de celular).
- [ ] Tudo que abre, fecha (toggle).
- [ ] Testei no **tema escuro**, inclusive abrindo um `<select>`.
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
