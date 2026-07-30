import { test, expect } from '@playwright/test'

// Regressão do incidente de produção de 2026-07-29: TELA EM BRANCO no
// candidato, sem nenhum erro nos logs do servidor.
//
// Dois candidatos ficaram travados no meio do envio de documentos. A causa:
// `try_files $uri /index.html` valia também para /assets/*.js. Cada build gera
// assets com hash novo (index-C1OewSkj.js) e APAGA os anteriores; a aba que o
// candidato deixou aberta no celular — ele sai do sistema para fotografar o
// documento e volta — continuava pedindo o arquivo ANTIGO. O nginx respondia
// 200 com o HTML do index no lugar do JavaScript, o navegador tentava executar
// "<!doctype html>" como script, e a aplicação morria calada.
//
// Do ponto de vista do servidor foi um 200 bem-sucedido. Por isso nada
// apareceu em log nenhum, e por isso este teste existe: o defeito é INVISÍVEL
// para quem olha só o servidor, e o único sintoma é o pior possível para o
// candidato — uma página em branco, que não diz se o problema é a internet, o
// link, o celular ou o sistema.

test.describe('deploy não pode deixar o candidato com a tela em branco', () => {
  test('asset que não existe mais devolve 404 — nunca HTML disfarçado de JS', async ({ request }) => {
    // Exatamente o que a aba antiga do candidato pede depois de um deploy.
    const r = await request.get('/assets/index-BUNDLEQUEJAFOIAPAGADO.js')

    expect(r.status(),
      'asset inexistente tem que ser 404; 200 significa que o nginx devolveu '
      + 'o index.html no lugar do script, e o navegador quebra ao executá-lo'
    ).toBe(404)

    // A garantia que importa de verdade: o corpo NÃO pode ser a página HTML.
    // Um 404 com HTML de erro do nginx é aceitável; o que não pode é o SPA.
    const corpo = await r.text()
    expect(corpo).not.toContain('<div id="root">')
  })

  test('o asset atual é servido como JavaScript', async ({ page, request }) => {
    // Descobre o bundle vigente pelo próprio index.html — sem hash chumbado,
    // que mudaria a cada build e faria este teste falhar à toa.
    await page.goto('/')
    const src = await page.locator('script[src*="/assets/"]').first().getAttribute('src')
    expect(src, 'o index.html precisa referenciar algum bundle').toBeTruthy()

    const r = await request.get(src)
    expect(r.status()).toBe(200)
    expect(r.headers()['content-type']).toContain('javascript')
  })

  test('a rota do candidato continua servindo o SPA', async ({ request }) => {
    // Garantia INVERSA: /c/{token} é rota tratada no cliente e PRECISA do
    // fallback para index.html. Consertar o asset não pode ter quebrado a
    // navegação — que é justamente por onde o candidato entra.
    const r = await request.get('/c/token-inexistente-so-para-checar-a-rota')
    expect(r.status()).toBe(200)
    expect(await r.text()).toContain('<div id="root">')
  })

  test('o index.html nunca fica em cache', async ({ request }) => {
    // Sem isso, o navegador do candidato guardaria a página apontando para um
    // bundle já apagado — que é como o incidente começa.
    const r = await request.get('/')
    expect(r.headers()['cache-control'] || '').toContain('no-store')
  })

  test('a página do candidato monta e não fica em branco', async ({ page }) => {
    // O sintoma como o candidato viveu: abrir o link e ver a tela vazia.
    // Com token inválido o certo é aparecer a mensagem de link expirado —
    // nunca um <body> vazio.
    const quebras = []
    page.on('pageerror', (e) => quebras.push(e.message))

    await page.goto('/c/token-invalido-de-teste')
    await page.waitForLoadState('networkidle')

    expect(quebras.filter((m) => /Unexpected token '<'|is not valid JSON/i.test(m)),
      'erro de sintaxe ao executar o bundle = o servidor devolveu HTML no lugar do JS'
    ).toHaveLength(0)

    // Alguma coisa tem que estar escrita na tela. Qualquer mensagem serve —
    // menos o nada.
    const texto = (await page.locator('#root').innerText()).trim()
    expect(texto.length, 'a tela do candidato ficou EM BRANCO').toBeGreaterThan(0)
  })
})
