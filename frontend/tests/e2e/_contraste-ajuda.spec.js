// O "?" de ajuda do portal do candidato é legível nos DOIS temas (v3.20).
//
// Prefixo `_`: roda à mão, fora do CI. O CI trava a regra estrutural (nada de
// cor fixa em `.btn-ajuda`); aqui a pergunta é outra e só o navegador responde:
// **qual é o contraste REAL do que foi renderizado?**
//
// O defeito (item 6 da 24ª leva): `.btn-ajuda` era `background: var(--tinta)`
// com `color: #fff`. No tema escuro `--tinta` inverte para quase branco, então
// era "?" branco sobre círculo branco — 1,13:1, contra o mínimo de 4,5:1 do
// WCAG AA. O `.ajuda-q` do painel do RH já tinha sido corrigido; este ficou.
//
// ⚠️ Contraste se MEDE no navegador, não se estima: o valor depende do que o
// `getComputedStyle` resolve, e um token pode ter mudado de valor sem ninguém
// mexer nesta regra.
//
// Rode com a stack local no ar:
//   BASE_URL=http://localhost:8090 npx playwright test _contraste-ajuda --workers=1

import { test, expect } from '@playwright/test'

const BASE = process.env.BASE_URL || 'http://localhost:8090'
const MINIMO = 4.5   // WCAG AA para texto normal

// Fórmula oficial do WCAG, avaliada DENTRO da página sobre o estilo computado.
const MEDIR = `(() => {
  const el = document.querySelector('.btn-ajuda')
  if (!el) return null
  const cs = getComputedStyle(el)
  const rgb = (s) => s.match(/\\d+(\\.\\d+)?/g).slice(0, 3).map(Number)
  const lum = (c) => {
    const [r, g, b] = c.map((v) => {
      const x = v / 255
      return x <= 0.03928 ? x / 12.92 : Math.pow((x + 0.055) / 1.055, 2.4)
    })
    return 0.2126 * r + 0.7152 * g + 0.0722 * b
  }
  const l1 = lum(rgb(cs.color)), l2 = lum(rgb(cs.backgroundColor))
  const [a, b] = l1 > l2 ? [l1, l2] : [l2, l1]
  return { razao: (a + 0.05) / (b + 0.05), cor: cs.color, fundo: cs.backgroundColor }
})()`

async function medirNoTema(page, tema) {
  await page.evaluate((t) => {
    document.documentElement.setAttribute('data-tema', t)
  }, tema)
  // um quadro para o CSS reassentar antes de ler o estilo computado
  await page.waitForTimeout(120)
  return page.evaluate(MEDIR)
}

test('o "?" de ajuda tem contraste suficiente nos dois temas', async ({ page }) => {
  // As três telas onde o botão vive (CandidatoApp, Checklist, Wizard) exigem um
  // token de candidato válido, que não existe num teste avulso. Como o que se
  // mede aqui é a REGRA DE CSS — a mesma para as três —, o botão é inserido na
  // página real, que já carregou a folha de estilos do sistema. O estilo
  // computado é o de produção; só o contexto de navegação é que é sintético.
  await page.goto(`${BASE}/`)
  await page.waitForLoadState('networkidle')
  await page.evaluate(() => {
    const b = document.createElement('button')
    b.className = 'btn-ajuda'
    b.textContent = '?'
    document.body.appendChild(b)
  })

  for (const tema of ['claro', 'escuro']) {
    const m = await medirNoTema(page, tema)
    expect(m, `deveria achar .btn-ajuda no tema ${tema}`).not.toBeNull()
    console.log(`  tema ${tema}: ${m.razao.toFixed(2)}:1  (texto ${m.cor} sobre ${m.fundo})`)
    expect(m.razao, `contraste no tema ${tema} (texto ${m.cor} sobre ${m.fundo})`)
      .toBeGreaterThanOrEqual(MINIMO)
  }
})
