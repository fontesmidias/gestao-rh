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
const LARGURAS = [1024, 1280, 1440]

const TELAS = [
  ['Admissões', '/rh'],
  ['Colaboradores', '/rh/colaboradores'],
  ['Talentos', '/rh/talentos'],
  ['Postos', '/rh/postos'],
  ['Desenvolvimento', '/rh/desenvolvimento'],
  ['Creche', '/rh/creche'],
]

// Folga de 2px: arredondamento de subpixel do próprio navegador, não conteúdo
// cortado. Sem ela o teste ficaria intermitente por causa de meio pixel.
const TOLERANCIA = 2

async function entrar(page) {
  await page.goto('/rh')
  await page.locator('input[type=email]').first().fill(process.env.RH_EMAIL)
  await page.locator('input[type=password]').first().fill(process.env.RH_SENHA)
  await page.locator('button[type=submit]').first().click()
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
