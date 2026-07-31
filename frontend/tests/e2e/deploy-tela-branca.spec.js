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

  test('o index.html é servido como HTML, não como download', async ({ request }) => {
    // Regressão de 2026-07-31: um bloco `types { application/javascript mjs; }`
    // solto no server SUBSTITUIU o mapa inteiro de MIME do nginx, e o
    // index.html passou a sair como `application/octet-stream` — o site virava
    // DOWNLOAD em vez de abrir. O `include mime.types` tem que vir antes da
    // exceção. Este teste é barato e pega a classe toda de erro.
    const r = await request.get('/')
    expect(r.headers()['content-type'] || '').toContain('text/html')
  })

  test('o worker do pdf.js (.mjs) é servido como JavaScript', async ({ request }) => {
    // O `mime.types` do nginx não conhece `.mjs`: sem a exceção, o arquivo sai
    // como octet-stream e o navegador RECUSA o módulo ("Strict MIME type
    // checking is enforced for module scripts"). O efeito é invisível no
    // desktop e total no CELULAR, onde o pdf.js é o ÚNICO caminho para exibir
    // PDF (o Chrome do Android não tem visualizador embutido): todo documento
    // caía em "não conseguimos exibir este PDF aqui".
    const html = await (await request.get('/')).text()
    // o worker não é referenciado no index (o pdf.js o carrega sob demanda),
    // então descobrimos o nome pelo próprio bundle
    const bundle = html.match(/\/assets\/index-[\w-]+\.js/)?.[0]
    expect(bundle, 'o index.html precisa referenciar o bundle').toBeTruthy()
    const js = await (await request.get(bundle)).text()
    const worker = js.match(/assets\/pdf\.worker[\w.-]*\.mjs/)?.[0]
    test.skip(!worker, 'bundle sem worker de pdf.js — nada a checar')

    const r = await request.get(`/${worker}`)
    expect(r.status()).toBe(200)
    expect(r.headers()['content-type'] || '',
           'módulo ES servido com MIME errado é recusado pelo navegador')
      .toContain('javascript')
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

  test("a etapa de assinatura monta — nenhum estado null usado antes do guard", async ({ page }) => {
    // Segunda causa do MESMO incidente, encontrada quando a primeira já estava
    // corrigida e a tela continuou quebrando (agora com a mensagem do
    // ErrorBoundary, em vez do branco): `Assinatura.jsx` fazia
    // `fichas.some(...)` no corpo do componente, mas `fichas` nasce null e só é
    // preenchido pelo useEffect. O guard `if (!fichas)` existia — lá embaixo,
    // perto do return, tarde demais para o que é calculado em cima.
    // `null.some()` lançava TypeError e apagava a tela do candidato.
    // Introduzido na v2.05; pegou quem estava exatamente na etapa de assinatura.
    // Testar pela UI exigiria criar posto + jornada + candidato e conduzir o
    // wizard inteiro — frágil e dependente do estado do banco. O defeito é de
    // RENDER, então basta montar o componente com a resposta que o servidor
    // realmente devolve ANTES do useEffect resolver: `fichas` ainda null.
    //
    // Servimos uma página que importa o bundle publicado e renderiza só o
    // Assinatura, com a API interceptada para demorar — a janela exata em que
    // a tela quebrava.
    const quebras = []
    page.on('pageerror', (e) => quebras.push(e.message))

    // Segura a resposta de /fichas por 1,5s: durante esse tempo o componente
    // fica com `fichas === null` e é exatamente aí que `fichas.some()` lançava.
    await page.route('**/api/c/*/fichas', async (rota) => {
      await new Promise((r) => setTimeout(r, 1500))
      await rota.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ fichas: [
          { documento: 'ficha_cadastro', titulo: 'Ficha Cadastral', assinado: false },
          { documento: 'termo_vt', titulo: 'Termo de VT', assinado: false },
        ] }),
      })
    })
    // A ficha do candidato responde na hora: garante que o componente monta e
    // fica esperando só o /fichas.
    await page.route('**/api/c/*/ficha', (rota) => rota.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        status: 'aguardando_assinatura', aceite_lgpd_em: '2026-07-29T10:00:00Z',
        pessoais: { nome_completo: 'Regressao Tela Branca', email: 'r@example.com' },
        vt: { optante: true },
      }),
    }))
    await page.route('**/api/c/*/testes', (rota) => rota.fulfill({
      status: 200, contentType: 'application/json',
      body: JSON.stringify({ tem_testes: false, todos_concluidos: true }),
    }))

    await page.goto('/c/token-de-regressao-render')
    // Enquanto o /fichas não responde, o componente está com fichas === null.
    await page.waitForTimeout(700)

    expect(quebras.join(' | '),
      'exceção no render com estado ainda null apaga a tela inteira do candidato'
    ).not.toMatch(/Cannot read propert/)

    // O ErrorBoundary é a rede de segurança — se ELE apareceu, alguma coisa
    // quebrou no caminho e o candidato está travado do mesmo jeito.
    await expect(page.getByText('Algo deu errado ao abrir esta página')).toHaveCount(0)
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
