// Exportar leva quem está MARCADO — verificação na tela (v3.17).
//
// Prefixo `_`: roda à mão, fora do CI (como o `_levantamento-densidade`). O que
// o CI trava é o `test_export_por_selecao.py`, que confere o conteúdo da
// planilha. Aqui a pergunta é outra e só o navegador responde: **os botões
// existem, estão alcançáveis, e o que eles mandam é a seleção?**
//
// Foi escrito porque o defeito original era invisível no código e no build: o
// botão estava lá, bonito, no cabeçalho da tela — e simplesmente não enxergava
// a seleção que efetivar e desligar enxergavam.
//
// Rode com a stack local no ar:
//   BASE_URL=http://localhost:8090 RH_EMAIL=teste@exemplo.com.br \
//     RH_SENHA=senha-teste-123 npx playwright test _exportar-respeita-selecao --workers=1

import { test, expect } from '@playwright/test'

const BASE = process.env.BASE_URL || 'http://localhost:8090'
const EMAIL = process.env.RH_EMAIL || 'teste@exemplo.com.br'
const SENHA = process.env.RH_SENHA || 'senha-teste-123'

async function entrar(page) {
  await page.goto(`${BASE}/rh`)
  await page.getByLabel(/e-?mail/i).fill(EMAIL)
  await page.getByLabel(/senha/i).fill(SENHA)
  await page.getByRole('button', { name: /entrar/i }).click()
  await page.waitForSelector('.rh-painel, .dash-acoes', { timeout: 20000 })
}

test('exportar fica alcançável e manda a seleção no corpo', async ({ page }) => {
  await entrar(page)
  await page.goto(`${BASE}/rh/colaboradores`)
  await page.waitForSelector('.dash-acoes', { timeout: 20000 })
  await page.waitForSelector('.rh-tabela tbody tr', { timeout: 20000 })

  // 1. Sem seleção, os três botões existem e estão clicáveis. Escondê-los sem
  //    seleção repetiria o defeito da v2.76.1 (o botão que sumiu com o card).
  //
  //    Os seletores são presos ao `.dash-acoes`: "Tirvu" também aparece na
  //    coluna Origem de cada linha, e um seletor solto casaria com a tabela
  //    inteira — o teste falharia por ambiguidade, não por defeito.
  const acoes = page.locator('.dash-acoes')
  const tirvu = acoes.getByRole('button', { name: /Tirvu/i })
  const dexion = acoes.getByRole('button', { name: /Dexion/i })
  const excel = acoes.getByRole('button', { name: /Excel/i })
  for (const [nome, botao] of [['Tirvu', tirvu], ['Dexion', dexion], ['Excel', excel]]) {
    await expect(botao, `${nome} visível sem seleção`).toBeVisible()
    await expect(botao, `${nome} habilitado sem seleção`).toBeEnabled()
  }

  // 2. Os botões vivem no card de ações, não no cabeçalho da tela.
  await expect(tirvu).toBeVisible()
  await expect(page.locator('.rh-topo').getByRole('button', { name: /Tirvu/i }))
    .toHaveCount(0)

  // 3. Marcar duas linhas faz o rótulo dizer quantos vão. É o que permite à
  //    pessoa saber o que leva ANTES de clicar.
  const caixas = page.locator('.rh-tabela tbody input[type="checkbox"]')
  const total = await caixas.count()
  test.skip(total < 2, 'a base local precisa de ao menos 2 colaboradores')
  await caixas.nth(0).check()
  await caixas.nth(1).check()
  await expect(acoes.getByRole('button', { name: /Tirvu\s*\(2\)/ })).toBeVisible()

  // 4. O que sai na requisição é a seleção, no CORPO — não na URL.
  //    Este é o coração do teste: o defeito era exatamente o botão montar o
  //    próprio conjunto a partir dos filtros, ignorando o que foi marcado.
  const [req] = await Promise.all([
    page.waitForRequest((r) => r.url().includes('/exportar-selecao') && r.method() === 'POST',
                        { timeout: 20000 }),
    acoes.getByRole('button', { name: /Tirvu\s*\(2\)/ }).click(),
  ])
  const corpo = JSON.parse(req.postData() || '{}')
  expect(corpo.ids, 'a seleção viaja no corpo da requisição').toHaveLength(2)
  expect(req.url().length, 'a URL não carrega os ids (o nginx corta em 8 KB)')
    .toBeLessThan(300)
})

test('Admissões ganhou seleção e exporta quem está marcado', async ({ page }) => {
  await entrar(page)
  await page.goto(`${BASE}/rh`)
  await page.waitForSelector('.dash-acoes', { timeout: 20000 })
  await page.waitForSelector('.rh-tabela tbody tr', { timeout: 20000 })

  const acoes = page.locator('.dash-acoes')

  // 1. O botão existe e é alcançável SEM seleção — antes desta versão a tela
  //    não tinha exportação nenhuma ("isso nem tem opção no módulo candidatos").
  const exportar = acoes.getByRole('button', { name: /Exportar planilha completa/i })
  await expect(exportar, 'exportar visível sem seleção').toBeVisible()
  await expect(exportar, 'exportar habilitado sem seleção').toBeEnabled()

  // 2. A coluna de seleção passou a existir. Ela só aparece quando o
  //    DashPlanilha recebe `acoesMassa` — sem essa prop não há o que marcar.
  const caixas = page.locator('.rh-tabela tbody input[type="checkbox"]')
  const total = await caixas.count()
  test.skip(total < 2, 'a base local precisa de ao menos 2 candidatos em admissão')

  await caixas.nth(0).check()
  await caixas.nth(1).check()
  await expect(acoes.getByRole('button', { name: /Exportar planilha completa\s*\(2\)/ }))
    .toBeVisible()

  // 3. O que sai na requisição é a seleção, no CORPO.
  const [req] = await Promise.all([
    page.waitForRequest((r) => r.url().includes('/candidatos-exportar') && r.method() === 'POST',
                        { timeout: 20000 }),
    acoes.getByRole('button', { name: /Exportar planilha completa\s*\(2\)/ }).click(),
  ])
  const corpo = JSON.parse(req.postData() || '{}')
  expect(corpo.ids, 'a seleção viaja no corpo da requisição').toHaveLength(2)
  expect(req.url().length, 'a URL não carrega os ids (o nginx corta em 8 KB)')
    .toBeLessThan(300)
})
