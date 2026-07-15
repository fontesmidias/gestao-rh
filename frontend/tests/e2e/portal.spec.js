import { expect, test } from '@playwright/test'

// Credenciais do admin criado pelo bootstrap (definidas no .env da stack de teste).
const RH_EMAIL = process.env.RH_EMAIL || 'rh@greenhousedf.com.br'
const RH_SENHA = process.env.RH_SENHA || 'admin-inicial-trocar'

test('home carrega com logo e caminhos de entrada', async ({ page }) => {
  await page.goto('/')
  await expect(page.getByRole('heading', { name: 'Portal de Admissão' })).toBeVisible()
  await expect(page.getByAltText('Green House')).toBeVisible()
  await expect(page.getByRole('link', { name: /Perdeu o link/ })).toBeVisible()
  await expect(page.getByRole('link', { name: /Acesso do RH/ })).toBeVisible()
})

test('login do RH: senha errada avisa, senha certa abre o painel', async ({ page }) => {
  await page.goto('/rh')
  await page.getByLabel('E-mail').fill(RH_EMAIL)
  await page.getByLabel(/^Senha/).fill('senha-completamente-errada')
  await page.getByRole('button', { name: 'Entrar' }).click()
  await expect(page.getByText('E-mail ou senha incorretos.')).toBeVisible()

  await page.getByLabel(/^Senha/).fill(RH_SENHA)
  await page.getByRole('button', { name: 'Entrar' }).click()
  await expect(page.getByRole('heading', { name: /Admissões/ })).toBeVisible()
  // métricas do dashboard aparecem
  await expect(page.getByText('Docs p/ revisar')).toBeVisible()
})

test('tela de login tem o esqueci minha senha', async ({ page }) => {
  await page.goto('/rh')
  await page.getByRole('button', { name: 'Esqueci minha senha' }).click()
  await expect(page.getByRole('heading', { name: /Esqueci minha senha/ })).toBeVisible()
})

test('/entrar valida o CPF na hora', async ({ page }) => {
  await page.goto('/entrar')
  const cpf = page.getByLabel('CPF')
  await cpf.fill('11111111111')
  // CPF com dígito inválido mantém o botão desabilitado
  await expect(page.getByRole('button', { name: 'Continuar' })).toBeDisabled()
  await cpf.fill('529.982.247-25')
  await expect(page.getByRole('button', { name: 'Continuar' })).toBeEnabled()
})

test('verificador público: ID inexistente alerta possível adulteração', async ({ page }) => {
  await page.goto('/verificar/00000000-0000-0000-0000-000000000001')
  await expect(page.getByRole('heading', { name: 'Assinatura não encontrada' })).toBeVisible()
  await expect(page.getByText(/adulterado/)).toBeVisible()
})

async function criarConvite(request, dados) {
  const login = await request.post('/api/rh/auth/login',
    { data: { email: RH_EMAIL, senha: RH_SENHA } })
  expect(login.ok()).toBeTruthy()
  const { token } = await login.json()
  const convite = await request.post('/api/rh/candidatos', {
    headers: { Authorization: `Bearer ${token}` }, data: dados,
  })
  expect(convite.status()).toBe(201)
  return convite.json()
}

test('jornada do candidato: convite → LGPD → máscara de datas do wizard', async ({ page, request }) => {
  // RH cria o convite pela API (o link mágico volta na resposta)
  const { link_magico } = await criarConvite(request, {
    nome_completo: 'E2e Playwright da Silva',
    email: `e2e-${Date.now()}@example.com`, celular_whatsapp: '61911112222',
  })

  await page.goto(link_magico)
  await expect(page.getByText(/Sua admissão na Green House/)).toBeVisible()
  await page.getByRole('button', { name: 'Li e concordo em continuar' }).click()

  // wizard: máscara de data reconhece data inexistente e formata dd/mm/aaaa
  const data = page.getByPlaceholder('dd/mm/aaaa').first()
  await data.fill('')
  await data.pressSequentially('31022001')
  await expect(page.getByText(/Essa data não existe/)).toBeVisible()
  await data.fill('')
  await data.pressSequentially('15031990')
  await expect(data).toHaveValue('15/03/1990')
  await expect(page.getByText(/Essa data não existe/)).toHaveCount(0)
})

test('convite só com nome: link sai mesmo sem e-mail', async ({ request }) => {
  const convite = await criarConvite(request, { nome_completo: 'E2e Sem Email' })
  expect(convite.candidato.email).toBeNull()
  expect(convite.email_enviado).toBe(false)
  expect(convite.link_magico).toContain('/c/')
})

test('câmera guiada: moldura, dicas em tempo real e saída para arquivo', async ({ page, request }) => {
  const { link_magico } = await criarConvite(request, {
    nome_completo: 'E2e Camera da Silva',
    email: `e2e-cam-${Date.now()}@example.com`, celular_whatsapp: '61933334444',
  })
  // marca o tour de boas-vindas como já visto — senão o overlay do driver.js
  // cobre a tela e intercepta os cliques
  await page.addInitScript(() => localStorage.setItem('tour_visto', '1'))
  await page.goto(link_magico)
  await page.getByRole('button', { name: 'Li e concordo em continuar' }).click()

  // o leitor de RG/CNH agora está logo na etapa 1 (dados pessoais)
  const abrir = page.getByRole('button', { name: /Fotografar meu RG ou CNH/ })
  await expect(abrir).toBeVisible()
  await abrir.click()

  // overlay abre com a câmera falsa do Chromium: moldura + dica ao vivo
  const overlay = page.getByRole('dialog', { name: /Fotografar RG ou CNH/ })
  await expect(overlay).toBeVisible()
  await expect(overlay.locator('.captura-moldura')).toBeVisible()
  await expect(overlay.locator('.captura-dica')).toBeVisible({ timeout: 5000 })
  // o caminho do arquivo próprio está sempre à mão
  await expect(overlay.getByRole('button', { name: /Já tenho o arquivo/ })).toBeVisible()
  // o disparo existe (habilita quando o quadro está bom, ou vira
  // "fotografar assim mesmo" depois do tempo de escape)
  await expect(overlay.getByRole('button', { name: /Fotografar|Ajustando/ })).toBeVisible()

  // fechar devolve à etapa sem efeito colateral
  await overlay.getByRole('button', { name: /Fechar/ }).click()
  await expect(overlay).toHaveCount(0)
  await expect(abrir).toBeVisible()

  // na etapa de endereço, o leitor de comprovante também está à mão
  await page.getByRole('button', { name: 'Continuar →' }).click()
  await expect(page.getByRole('button', { name: /Fotografar minha conta/ })).toBeVisible()
})
