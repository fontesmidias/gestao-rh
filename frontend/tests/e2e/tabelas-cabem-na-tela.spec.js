/**
 * Nenhuma tabela do painel pode estourar a largura da tela.
 *
 * Feedback de campo 2026-08-02, com dois prints:
 *
 *   "tive que segurar a tecla ctrl e rolar o scroll do mouse, mas isso não é
 *    intuitivo. Quero que não seja necessário rolar nada, em tabela nenhuma de
 *    todas as páginas [...] pois o botão estava ali, como no exemplo, mas eu
 *    não vi."
 *
 * O botão em questão ("Atender presencial", v2.56) foi o quarto da coluna de
 * ações e empurrou a tabela para fora da tela. Medido antes do conserto:
 * a coluna de ações ocupava **560px de 1058px — 53% da tabela**, e em 1366px
 * sobravam DOIS pixels de folga. Qualquer janela menor cortava a ação, em
 * silêncio, porque o `border-radius` da tabela faz o corte parecer o fim dela.
 *
 * Este teste existe porque o defeito é INVISÍVEL no código: cada botão novo
 * parece inofensivo na linha em que é escrito, e ninguém soma as larguras. É a
 * régua que faltava — o mesmo papel do `test_design_system.py` no backend.
 *
 * Roda contra a stack completa (o CI já a sobe para os testes de interface).
 */
import { test, expect } from '@playwright/test'

// Larguras que importam: 1024 é notebook pequeno e janela dividida ao meio num
// monitor grande — os dois casos em que o botão sumia. 1280 e 1440 são os
// monitores do escritório.
// **1200 é o pior caso, e a primeira versão deste teste NÃO o media** — só
// 1024/1280/1440. Nessa faixa o modo card já saiu (limiar de 1100px) mas a
// tela ainda é estreita, e Colaboradores/Talentos/Jornadas estouravam
// 53/78/223px sem que nada acusasse (feedback 2026-08-02, com prints).
//
// Lição que fica: uma régua com poucos pontos mede os pontos, não a faixa.
const LARGURAS = [1024, 1150, 1200, 1280, 1440]

const TELAS = [
  ['Admissões', '/rh'],
  ['Colaboradores', '/rh/colaboradores'],
  ['Talentos', '/rh/talentos'],
  ['Postos', '/rh/postos'],
  ['Jornadas', '/rh/jornadas'],          // faltava — e era a que mais estourava
  ['Desenvolvimento', '/rh/desenvolvimento'],
  ['Creche', '/rh/creche'],
  ['Entrevistas', '/rh/entrevistas'],    // v2.64 — lista nova entra AQUI no mesmo commit
]

// Folga de 2px: arredondamento de subpixel do próprio navegador, não conteúdo
// cortado. Sem ela o teste ficaria intermitente por causa de meio pixel.
const TOLERANCIA = 2

// Token reaproveitado entre os testes deste arquivo: o painel tem rate limit
// de login (proteção legítima), e cinco logins seguidos derrubavam a suíte com
// "Muitas tentativas". Faz login UMA vez e injeta o token nos demais.
let tokenCache = null

async function entrar(page) {
  if (!tokenCache) {
    const r = await page.request.post('/api/rh/auth/login', {
      data: { email: process.env.RH_EMAIL, senha: process.env.RH_SENHA },
    })
    tokenCache = (await r.json()).token
  }
  await page.goto('/rh')
  await page.evaluate((t) => localStorage.setItem('rh_token', t), tokenCache)
  await page.goto('/rh')
  await page.waitForSelector('.dash-tabela, .rh-tabela', { timeout: 30000 })
  // Mede o PADRÃO, não a preferência de colunas que ficou salva de outra
  // execução — senão o teste passaria escondendo colunas por acidente.
  await page.evaluate(() => {
    for (const k of Object.keys(localStorage)) {
      if (k.startsWith('dash-ocultas:')) localStorage.removeItem(k)
    }
  })
}

for (const largura of LARGURAS) {
  test(`nenhuma tabela estoura a tela — ${largura}px`, async ({ page }) => {
    await page.setViewportSize({ width: largura, height: 900 })
    await entrar(page)

    const problemas = []
    for (const [nome, rota] of TELAS) {
      await page.goto(rota)
      await page.waitForTimeout(1200)
      const medidas = await page.evaluate(() => {
        const tabelas = []
        for (const wrap of document.querySelectorAll('.dash-scroll')) {
          const t = wrap.querySelector('table')
          if (t) tabelas.push({ visivel: wrap.clientWidth, necessaria: t.scrollWidth })
        }
        return {
          tabelas,
          // Tabela FORA de um `.dash-scroll` empurra a PÁGINA inteira — é o
          // caso registrado no CLAUDE.md ("overflow-x numa <table> não
          // funciona; só o wrapper contém").
          soltas: [...document.querySelectorAll('table.rh-tabela')]
            .filter((t) => !t.closest('.dash-scroll')).length,
          estouroDaPagina: document.body.scrollWidth - document.body.clientWidth,
        }
      })
      for (const t of medidas.tabelas) {
        const excesso = t.necessaria - t.visivel
        if (excesso > TOLERANCIA) {
          problemas.push(`${nome}: tabela ${excesso}px além da área visível`)
        }
      }
      if (medidas.estouroDaPagina > TOLERANCIA) {
        problemas.push(`${nome}: a PÁGINA rola ${medidas.estouroDaPagina}px na horizontal`)
      }
      if (medidas.soltas > 0) {
        problemas.push(`${nome}: ${medidas.soltas} tabela(s) sem wrapper .dash-scroll`)
      }
    }

    expect(problemas,
      'Alguma tabela voltou a exigir rolagem lateral. Costuma ser (a) um botão '
      + 'novo na coluna de ações, (b) uma coluna nova visível por padrão, ou '
      + '(c) uma célula com texto longo que não quebra (chip, data com hora). '
      + 'Conserto: `oculta: true` na coluna menos usada, ou encurtar o rótulo '
      + 'do botão deixando a explicação no `title`.\n' + problemas.join('\n'))
      .toEqual([])
  })
}

// Roda nos DOIS modos: 1440px é tabela, 1150px é card. A primeira versão
// media só 1440 — e o defeito estava no CARD, onde o Banco de Talentos chegou
// a **491px por linha** (botões empilhados verticalmente + campos vazios
// virando linha). Um teste de altura que só olha um modo mede metade da tela.
for (const largura of [1440, 1150]) {
test(`linha de tabela não vira um parágrafo — ${largura}px`, async ({ page }) => {
  /* Tirar a rolagem lateral sem limitar a ALTURA só troca um problema por
   * outro (feedback 2026-08-02, segundo print): um posto como "SESI-DF -
   * 22/2026 - BRIGADISTA, RECEPÇÃO, GARÇONARIA, PORTARIA E LIMPEZA E
   * CONSERVAÇÃO" quebrava em seis linhas, e a tabela mostrava DUAS pessoas por
   * tela. O RH deixou de rolar para o lado e passou a rolar para baixo.
   *
   * O conserto é o corte em 3 linhas com reticências (`.dash-corta`), com o
   * texto inteiro no `title` — pedido do Bruno: *"para textos longos ter
   * reticências e, se parar o mouse, aparecer o texto completo"*.
   */
  await page.setViewportSize({ width: largura, height: 900 })
  await entrar(page)
  const problemas = []
  for (const [nome, rota] of TELAS) {
    await page.goto(rota)
    await page.waitForTimeout(1200)
    const m = await page.evaluate(() => {
      const linhas = [...document.querySelectorAll('.dash-tabela tbody tr')]
        .filter((tr) => !tr.classList.contains('dash-detalhe'))
      if (!linhas.length) return null
      const alturas = linhas.map((tr) => tr.getBoundingClientRect().height)
      // Célula `quebra` sem o wrapper de corte é a que deixa a linha crescer
      // sem limite — o defeito volta por aí.
      const semCorte = [...document.querySelectorAll('.dash-tabela td.dash-quebra')]
        .filter((td) => !td.querySelector('.dash-corta')).length
      return { maior: Math.round(Math.max(...alturas)), semCorte }
    })
    if (!m) continue
    // 170px: acima disso a tabela deixa de ser varrível. O piso é dado pelo
    // Talentos, que tem SEIS botões de ação e chega a 162px legitimamente — a
    // grade 2×2 vira três fileiras. O texto longo, esse, é cortado em 3 linhas
    // e não passa de 115px; a garantia contra ele é a checagem de `semCorte`
    // logo abaixo, que é específica e não depende deste limiar.
    // No CARD a linha é naturalmente mais alta (rótulo ao lado de cada valor
    // e botões com área de toque), mas 240px já significa card ocupando meia
    // tela — foi o sintoma do Banco de Talentos.
    const teto = largura <= 1250 ? 240 : 170
    if (m.maior > teto) problemas.push(`${nome}: linha de ${m.maior}px de altura`)
    if (m.semCorte > 0) {
      problemas.push(`${nome}: ${m.semCorte} célula(s) de texto longo sem o corte em 3 linhas`)
    }
  }
  expect(problemas,
    'Alguma linha ficou alta demais. Texto longo deve ser CORTADO em 3 linhas '
    + '(coluna com `quebra: true` ganha `.dash-corta` automaticamente) e o texto '
    + 'inteiro fica no `title`.\n' + problemas.join('\n'))
    .toEqual([])
})
}

test('a coluna de ações não domina a tabela', async ({ page }) => {
  // Regra que sustenta o resto: se as ações voltarem a ocupar metade da
  // largura, qualquer coluna nova estoura de novo. Antes do conserto eram 53%.
  await page.setViewportSize({ width: 1440, height: 900 })
  await entrar(page)
  const proporcao = await page.evaluate(() => {
    const tab = document.querySelector('.dash-tabela')
    const acoes = document.querySelector('.acoes-candidato')
    if (!tab || !acoes) return 0
    return acoes.getBoundingClientRect().width / tab.getBoundingClientRect().width
  })
  expect(proporcao,
    `A coluna de ações ocupa ${Math.round(proporcao * 100)}% da tabela. `
    + 'Acima de 35% ela sufoca os dados e o próximo botão joga tudo para fora '
    + 'da tela — foi assim que o "Atender presencial" sumiu da vista.')
    .toBeLessThan(0.35)
})

// --------------------------------------------------------------------------
// CELULAR: a lista aparece sem uma tela e meia de rolagem (v2.76)
// --------------------------------------------------------------------------
// Feedback do Bruno, com print estendido: *"a navegação está feia demais para
// mobile, horrível"*.
//
// O defeito não era estético e não aparecia em nenhuma régua existente: as
// outras medem LARGURA (nada estoura de lado) e ALTURA DE LINHA (o card não
// vira pergaminho). Ninguém media quanto CABEÇALHO existe antes do primeiro
// registro — e era isso que estava errado.
//
// Medido em 390px antes do conserto:
//     Talentos 1212px · Colaboradores 1092px · Entrevistas 1039px
// Em telas de 844px de altura, 1212px é uma tela e meia de rolagem só para ver
// o primeiro item. A pessoa abre a lista e não vê lista nenhuma.
//
// O teto de 600px não é arbitrário: é o que sobra de uma tela de celular comum
// (844px) depois de descontar o que o navegador ocupa — ou seja, garante que
// ALGUMA linha da lista apareça sem rolar.
test('celular: a lista começa antes de 600px (cabeçalho não engole a tela)', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 })
  await entrar(page)

  const TETO = 600
  const problemas = []
  for (const [nome, rota] of TELAS) {
    await page.goto(rota)
    await page.waitForTimeout(1200)
    const m = await page.evaluate(() => {
      const tr = document.querySelector('.dash-tabela tbody tr')
      if (!tr) return null           // tela sem lista (ou sem dados) não conta
      const caixa = document.querySelector('.dash-filtros-caixa')
      return {
        y: Math.round(tr.getBoundingClientRect().top + window.scrollY),
        // A barra de filtros tem que nascer FECHADA no celular: é ela que
        // sozinha chegava a 643px. Se alguém a abrir por padrão, o teto acima
        // volta a estourar — mas esta asserção diz POR QUÊ, em vez de deixar o
        // número falhar sem explicação.
        filtrosAbertos: caixa ? caixa.open : null,
      }
    })
    if (!m) continue
    if (m.y > TETO) problemas.push(`${nome}: a 1ª linha só começa em ${m.y}px`)
    if (m.filtrosAbertos === true) {
      problemas.push(`${nome}: a barra de filtros nasce ABERTA no celular`)
    }
  }

  expect(problemas,
    'No celular o cabeçalho está empurrando a lista para fora da primeira tela. '
    + 'Costuma ser (a) a barra de filtros aberta por padrão, (b) cards de '
    + 'métrica em uma coluna, ou (c) botões de ação em largura cheia. '
    + 'As regras estão no bloco final `@media (max-width: 760px)` do '
    + 'styles.css, e o padrão está em 08-sistema-de-design.md § 9.1.\n'
    + problemas.join('\n'))
    .toEqual([])
})

// --------------------------------------------------------------------------
// CELULAR: nada vaza pela borda — nem DENTRO do painel aberto (v2.76.1)
// --------------------------------------------------------------------------
// O teste de largura media `document.body.scrollWidth`, e por isso NÃO pegou o
// defeito que o Bruno viu: *"o ajuste que você fez na página de entrevistas está
// extrapolando as laterais da tela mobile"*. O `body` não rolava — quem vazava
// era um elemento DENTRO do painel de detalhe (o "✕ fechar", medido em
// `right=471` numa viewport de 390px), e o overflow ficava contido sem alargar
// a página.
//
// A causa, confirmada por MUTAÇÃO (devolvê-la faz este teste reprovar):
// `.dash-detalhe` usa `width: 100cqw` — certo no modo TABELA, onde o container
// rola de lado e o painel precisa ficar preso à parte visível; errado no modo
// CARD, onde mede um container mais largo que a tela.
//
// ⚠️ O `flex-wrap` acrescentado ao `.rh-conferencia-topo` na mesma leva NÃO era
// a causa: removê-lo mantém este teste verde. Fica porque é a regra global da
// v2.60 (flex sem wrap vaza) e protege contra um botão a mais no futuro — mas
// não se atribua a ele o conserto deste defeito.
//
// Mede a borda DIREITA de cada elemento, que é o que denuncia conteúdo fora da
// vista mesmo quando a página inteira não rola. 320px entra de propósito: é o
// celular pequeno onde chip e botão longos aparecem primeiro.
for (const largura of [320, 390]) {
  test(`celular ${largura}px: nada vaza pela borda, nem na ficha aberta`, async ({ page }) => {
    await page.setViewportSize({ width: largura, height: 844 })
    await entrar(page)

    const problemas = []
    for (const [nome, rota] of TELAS) {
      await page.goto(rota)
      await page.waitForTimeout(1000)
      // Abre o primeiro detalhe, se a tela tiver — é lá que o defeito morava.
      const abrir = page.locator('.dash-tabela tbody button', { hasText: /^abrir$/ }).first()
      if (await abrir.count()) {
        await abrir.click({ timeout: 5000 }).catch(() => {})
        await page.waitForTimeout(1200)
      }
      const vazando = await page.evaluate(() => (
        [...document.querySelectorAll('.rh-painel *')]
          .filter((e) => {
            const r = e.getBoundingClientRect()
            // Ignora o que tem tamanho zero (escondido) e o que rola por
            // desenho (`.dash-scroll` contém a própria rolagem).
            if (r.width === 0 || r.height === 0) return false
            if (e.closest('.dash-scroll') && e.tagName === 'TABLE') return false
            return r.right > window.innerWidth + 1
          })
          .slice(0, 3)
          .map((e) => `${e.tagName}.${(e.className || '').toString().slice(0, 24)} `
            + `(termina em ${Math.round(e.getBoundingClientRect().right)}px)`)
      ))
      for (const v of vazando) problemas.push(`${nome}: ${v}`)
    }

    expect(problemas,
      'Algo passa da borda direita no celular. O `body` pode não rolar e o '
      + 'defeito existir mesmo assim — é conteúdo dentro de um contêiner. '
      + 'Costuma ser (a) `display: flex` sem `flex-wrap`, (b) `width: 100cqw` '
      + 'herdado do modo tabela, ou (c) chip/botão com `nowrap` sem teto.\n'
      + problemas.join('\n'))
      .toEqual([])
  })
}

// --------------------------------------------------------------------------
// DESKTOP: a barra de filtros está ABERTA e as ações estão à vista (v2.76.2)
// --------------------------------------------------------------------------
// Duas regressões que a v2.76/v2.76.1 causaram, ambas vistas pelo Bruno em
// produção — e nenhuma das réguas existentes pegava, porque todas mediam
// CELULAR:
//
//   *"não voltaram os filtros de select com busca, quero que volte para todos"*
//   *"você tirou os botões de cadastro do banco de talentos"*
//
// A causa do primeiro é sutil e vale registrar: um `<details>` FECHADO não
// renderiza o conteúdo, e `display: contents` no CSS não muda isso — quem
// esconde é o NAVEGADOR, não o estilo. Neutralizar a caixa na folha não bastou;
// o `open` tem que nascer certo no JSX (`open={!ehCelular}`).
//
// O segundo é o botão de CRIAR: ele morava dentro do card de filtros e sumiu
// junto quando o card passou a recolher. Card próprio, sempre visível.
test('desktop: filtros abertos e ações visíveis em todas as listas', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 })
  await entrar(page)

  const problemas = []
  for (const [nome, rota] of TELAS) {
    await page.goto(rota)
    await page.waitForTimeout(1100)
    const m = await page.evaluate(() => {
      const cx = document.querySelector('.dash-filtros-caixa')
      const filtros = [...document.querySelectorAll('.dash-filtro')]
      const acoes = document.querySelector('.dash-acoes')
      const visivel = (el) => !!el && el.getBoundingClientRect().height > 0
      return {
        temDash: !!document.querySelector('.dash-tabela'),
        caixaFechada: cx ? cx.open === false : false,
        qtdFiltros: filtros.length,
        // Filtro que existe no DOM mas tem altura zero está escondido — foi
        // exatamente o sintoma (os 9 filtros continuavam lá, invisíveis).
        filtrosVisiveis: filtros.filter(visivel).length,
        acoesVisiveis: visivel(acoes),
      }
    })
    if (!m.temDash) continue
    if (m.caixaFechada) problemas.push(`${nome}: a barra de filtros está FECHADA no desktop`)
    if (m.qtdFiltros > 0 && m.filtrosVisiveis === 0) {
      problemas.push(`${nome}: ${m.qtdFiltros} filtros no DOM, nenhum visível`)
    }
    if (!m.acoesVisiveis) problemas.push(`${nome}: o card de ações não está visível`)
  }

  expect(problemas,
    'No desktop os filtros têm que estar ABERTOS e as ações à vista. '
    + 'Lembre: `<details>` fechado NÃO renderiza o conteúdo — CSS não reabre '
    + 'isso, o `open` precisa nascer certo no JSX.\n' + problemas.join('\n'))
    .toEqual([])
})
