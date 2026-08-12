/**
 * LEVANTAMENTO (não é teste de regressão): mede a densidade visual das telas do
 * painel para embasar o redesenho pedido pelo Bruno em 2026-08-11 — *"não tô
 * achando muito intuitivo, o RH não tá achando certas coisas, parece muita
 * poluição visual"*.
 *
 * Mede em vez de opinar, porque "poluído" é impressão e impressão não se
 * discute. O que se discute é: quantos controles competem por atenção antes do
 * primeiro dado? quanto se rola até ver o primeiro registro? quantas cores e
 * pesos diferentes há na mesma faixa da tela?
 *
 * Prefixado com `_` para não entrar na suíte de CI: roda à mão quando se quer o
 * retrato.
 *
 *   BASE_URL=http://localhost:8090 RH_EMAIL=... RH_SENHA=... \
 *     npx playwright test _levantamento-densidade --workers=1
 */
import { expect, test } from '@playwright/test'
import fs from 'fs'

const EMAIL = process.env.RH_EMAIL || 'teste@exemplo.com.br'
const SENHA = process.env.RH_SENHA || 'senha-teste-123'

const TELAS = [
  { id: 'admissoes', url: '/rh/inicio', nome: 'Admissões' },
  { id: 'colaboradores', url: '/rh/colaboradores', nome: 'Colaboradores' },
  { id: 'talentos', url: '/rh/talentos', nome: 'Banco de Talentos' },
  { id: 'entrevistas', url: '/rh/entrevistas', nome: 'Entrevistas' },
]

const VIEWPORTS = [
  { id: 'desktop', width: 1440, height: 900 },
  { id: 'celular', width: 390, height: 844 },
]

async function entrar(page) {
  await page.goto('/rh')
  await page.fill('input[type=email]', EMAIL)
  await page.fill('input[type=password]', SENHA)
  await page.click('button[type=submit]')
  await page.waitForTimeout(2500)
  return page.evaluate(() => localStorage.getItem('rh_token'))
}

test('retrato de densidade das telas do painel', async ({ page }) => {
  test.setTimeout(240_000)
  const token = await entrar(page)
  expect(token, 'login precisa funcionar — confira RH_EMAIL/RH_SENHA').toBeTruthy()

  const relatorio = []

  for (const vp of VIEWPORTS) {
    await page.setViewportSize({ width: vp.width, height: vp.height })
    for (const tela of TELAS) {
      await page.goto(tela.url)
      await page.evaluate((t) => localStorage.setItem('rh_token', t), token)
      await page.goto(tela.url)
      await page.waitForTimeout(3500)

      const m = await page.evaluate(() => {
        const vis = (el) => {
          const r = el.getBoundingClientRect()
          const s = getComputedStyle(el)
          return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none'
        }
        const todos = [...document.querySelectorAll('*')].filter(vis)

        // Quanto se rola até o primeiro DADO (primeira linha de tabela ou card).
        const primeiroDado = document.querySelector(
          '.rh-tabela tbody tr, .dash-card, .dash-scroll tbody tr')
        const alturaAteDado = primeiroDado
          ? Math.round(primeiroDado.getBoundingClientRect().top + window.scrollY)
          : null

        // Controles que competem por atenção: tudo que se clica ou preenche.
        const controles = todos.filter((e) =>
          ['BUTTON', 'INPUT', 'SELECT', 'TEXTAREA', 'A'].includes(e.tagName))
        const botoes = controles.filter((e) => e.tagName === 'BUTTON')

        // Quantos controles aparecem ACIMA do primeiro dado — o "pedágio"
        // que a pessoa atravessa antes de ver o que veio buscar.
        const pedagio = alturaAteDado == null ? null : controles.filter((e) => {
          const r = e.getBoundingClientRect()
          return r.top + window.scrollY < alturaAteDado && r.width > 0
        }).length

        // Vocabulário visual: quantas cores de texto, tamanhos de fonte e pesos
        // diferentes convivem. Variedade alta = ruído, não hierarquia.
        const cores = new Set(), tamanhos = new Set(), pesos = new Set()
        const fundos = new Set(), raios = new Set()
        for (const e of todos) {
          const s = getComputedStyle(e)
          if (e.textContent && e.children.length === 0) {
            cores.add(s.color); tamanhos.add(s.fontSize); pesos.add(s.fontWeight)
          }
          if (s.backgroundColor !== 'rgba(0, 0, 0, 0)') fundos.add(s.backgroundColor)
          if (s.borderRadius !== '0px') raios.add(s.borderRadius)
        }

        // Estouro lateral: elemento cuja borda direita passa da viewport.
        const vazando = todos.filter((e) => {
          const r = e.getBoundingClientRect()
          if (r.width === 0) return false
          if (e.closest('.dash-scroll')) return false   // rola de propósito
          return r.right > window.innerWidth + 1
        }).length

        return {
          alturaAteDado,
          pedagio,
          controles: controles.length,
          botoes: botoes.length,
          coresTexto: cores.size,
          tamanhosFonte: tamanhos.size,
          pesosFonte: pesos.size,
          fundos: fundos.size,
          raios: raios.size,
          vazando,
          alturaPagina: Math.round(document.body.scrollHeight),
        }
      })

      relatorio.push({ tela: tela.nome, viewport: vp.id, ...m })
      await page.screenshot({
        path: `tests/e2e/_retrato/${tela.id}-${vp.id}.png`,
        fullPage: false,
      })
      console.log(`${vp.id.padEnd(8)} ${tela.nome.padEnd(20)} ` +
        `até 1º dado: ${String(m.alturaAteDado).padStart(5)}px | ` +
        `pedágio: ${String(m.pedagio).padStart(3)} controles | ` +
        `cores: ${m.coresTexto} | fontes: ${m.tamanhosFonte} | ` +
        `pesos: ${m.pesosFonte} | raios: ${m.raios} | vaza: ${m.vazando}`)
    }
  }

  fs.writeFileSync('tests/e2e/_retrato/densidade.json',
                   JSON.stringify(relatorio, null, 2))
  console.log('\nRetrato salvo em tests/e2e/_retrato/')
})
