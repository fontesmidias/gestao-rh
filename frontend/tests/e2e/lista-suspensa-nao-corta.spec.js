import { expect, test } from '@playwright/test'

// A lista suspensa não pode ser CORTADA (v2.92, defeito de campo).
//
// O Bruno foi trocar o papel da Fátima — a última linha da tabela de usuários —
// e a lista abriu para baixo, saindo pelo fim do card: a opção que decide o
// ACESSO da pessoa ficava ilegível. O § 5 do sistema de design já mandava
// ("nada estoura a tela"), e o `SelectBusca` violava a regra desde sempre,
// porque abria com `top: calc(100% + 4px)` fixo.
//
// ⚠️ Por que as réguas existentes não pegaram: `tabelas-cabem-na-tela` mede a
// LARGURA da página, e overflow contido não alarga nada (v2.76.1). Aqui o que
// se mede é a borda do PAINEL ABERTO contra a borda do container que o
// recorta — e isso só existe com a lista aberta, o que nenhum teste fazia.
//
// A medida é sobre o painel REAL, na ÚLTIMA linha: é lá que o espaço acaba.
// Testar na primeira linha passaria sempre e não provaria nada.

const BASE = process.env.BASE_URL || 'http://localhost:8090'
const EMAIL = process.env.RH_EMAIL || 'teste@exemplo.com.br'
const SENHA = process.env.RH_SENHA || 'senha-teste-123'

test('lista de papel na última linha abre inteira', async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 720 })
  await page.goto(`${BASE}/rh`)
  await page.fill('input[type=email]', EMAIL)
  await page.fill('input[type=password]', SENHA)
  await page.click('button[type=submit]')
  await page.waitForTimeout(2200)

  await page.goto(`${BASE}/rh/config`)
  await page.waitForTimeout(1500)
  await page.locator('.rh-subnav-item:has-text("Equipe")').click()
  await page.waitForTimeout(2500)

  const seletores = page.locator('.select-busca')
  const total = await seletores.count()
  expect(total, 'a tela de Equipe deveria ter seletores de papel').toBeGreaterThan(0)

  // A ÚLTIMA linha: é onde o espaço abaixo acaba e o painel era cortado.
  const ultimo = seletores.nth(total - 1)
  await ultimo.scrollIntoViewIfNeeded()
  await ultimo.click()
  await page.waitForTimeout(600)

  const medida = await page.locator('.select-busca-painel').last().evaluate((el) => {
    const p = el.getBoundingClientRect()
    const recorta = el.closest('.dash-scroll') || el.closest('.rh-card')
    const c = recorta?.getBoundingClientRect()
    return {
      alturaVisivel: Math.round(p.height),
      passaDaJanela: Math.round(p.bottom - window.innerHeight),
      passaDoContainer: c ? Math.round(p.bottom - c.bottom) : 0,
      itens: el.querySelectorAll('.select-busca-item').length,
    }
  })

  expect(medida.itens, 'o painel deveria listar as opções').toBeGreaterThan(0)
  expect(medida.alturaVisivel,
    'o painel abriu com altura quase zero — foi colapsado').toBeGreaterThan(60)
  expect(medida.passaDaJanela,
    `o painel passa ${medida.passaDaJanela}px do fim da JANELA — a opção fica `
    + 'fora da vista e a pessoa não consegue escolher').toBeLessThanOrEqual(0)
  expect(medida.passaDoContainer,
    `o painel passa ${medida.passaDoContainer}px do fim do CONTAINER que o `
    + 'recorta — é assim que ele aparecia cortado pela metade').toBeLessThanOrEqual(0)
})
