const BASE = '/api'

// Feedback de campo (2026-07-15): o RH clicava várias vezes achando que o
// comando não tinha ido. Toda chamada do painel conta aqui; enquanto houver
// requisição em andamento, o body ganha data-rh-ocupado (o CSS trava os
// botões do painel) e a BarraAtividade aparece no topo.
let ocupadasRH = 0
const notificarOcupado = () => {
  document.body.toggleAttribute('data-rh-ocupado', ocupadasRH > 0)
  window.dispatchEvent(new CustomEvent('rh-ocupado', { detail: ocupadasRH }))
}
const entrouRH = () => { ocupadasRH++; notificarOcupado() }
const saiuRH = () => { ocupadasRH = Math.max(0, ocupadasRH - 1); notificarOcupado() }

async function req(caminho, opcoes = {}) {
  const doPainel = caminho.startsWith('/rh')
  if (doPainel) entrouRH()
  try {
    return await _req(caminho, opcoes)
  } finally {
    if (doPainel) saiuRH()
  }
}

// Erro de rede de verdade (sem resposta do servidor): fetch rejeita com
// TypeError. Só ESSE caso vira "sem conexão" — resposta HTTP ruim é outra
// coisa e carrega o detail real do backend (bug de campo: upload de arquivo
// grande demais aparecia como "sem internet").
//
// MAS "o fetch rejeitou" não é sinônimo de "sem internet" (relato de campo
// 2026-07-30, comprovante de residência): a conexão cortada no MEIO do envio
// — timeout do proxy, RST, servidor demorando além do limite do nginx —
// rejeita com o mesmo TypeError de quem está sem sinal. Dizer "verifique a
// internet" para quem está com a internet boa manda a pessoa tentar de novo
// na hora, e a nova tentativa gasta o mesmo tempo até estourar de novo.
// `navigator.onLine` é falível para dizer que ESTÁ online (pode haver Wi-Fi
// sem saída), mas é confiável quando diz que NÃO está — então só afirmamos
// falta de conexão quando ele confirma.
export async function buscar(url, opcoes) {
  const inicio = Date.now()
  try {
    return await fetch(url, opcoes)
  } catch (e) {
    const offline = typeof navigator !== 'undefined' && navigator.onLine === false
    // Demorou muito e caiu com a rede de pé: quem cortou foi o servidor/proxy.
    const demorou = Date.now() - inicio > 20000
    const erro = new Error(offline ? 'sem_conexao'
      : demorou ? 'demorou_demais' : 'conexao_interrompida')
    erro.detail = erro.message
    erro.offline = offline
    erro.rede = true          // veio do fetch, não de uma resposta HTTP
    throw erro
  }
}

// Resposta !ok → Error com status + detail SEMPRE string utilizável, mesmo
// quando o corpo não é JSON (413 do proxy vem em HTML) ou o detail é
// estruturado (422 de validação do FastAPI vem como lista).
async function lancarErro(r) {
  let detailBruto
  try { detailBruto = (await r.json()).detail } catch { detailBruto = null }
  let detail = detailBruto
  if (typeof detail !== 'string') {
    if (r.status === 413) detail = 'arquivo_grande_demais'
    else if (r.status === 422) detail = 'dados_invalidos'
    else detail = r.statusText || 'erro'
  }
  const erro = new Error(detail)
  erro.status = r.status
  erro.detail = detail
  // Se o backend mandou uma LISTA estruturada [{loc, msg, type}] (422 de
  // validação, ou o 422 de campo do rh_ficha.py), preserva em e.campos — antes
  // isso era descartado e trocado pela string genérica 'dados_invalidos',
  // deixando o RH sem saber qual campo corrigir (feedback de campo 2026-07-27).
  erro.campos = Array.isArray(detailBruto) ? detailBruto : null
  // Detail ESTRUTURADO como objeto (ex.: o 409 `criancas_sem_decisao`, que
  // manda junto QUAIS crianças faltam) também é preservado — sem isto ele
  // virava a string genérica do statusText e a tela só conseguiria dizer "não
  // deu", perdendo justamente a informação que resolve. Mesma lição do
  // `e.campos`: erro estruturado que o backend se deu ao trabalho de montar
  // não pode ser descartado na porta de entrada.
  erro.dados = (detailBruto && typeof detailBruto === 'object'
                && !Array.isArray(detailBruto)) ? detailBruto : null
  // Mensagem amigável para códigos globais conhecidos (o call-site pode usar
  // e.amigavel quando quiser, ou continua com e.detail). A trava de duplo-clique
  // devolve 409 ja_em_processamento — o RH clicou de novo enquanto processava.
  const AMIGAVEIS = {
    ja_em_processamento: 'Esta ação já está sendo processada — aguarde um instante.',
    muitas_tentativas: 'Muitas tentativas seguidas. Aguarde alguns minutos.',
    sem_conexao: 'Sem conexão. Verifique a internet e tente de novo.',
    erro_interno: 'Ocorreu um erro inesperado. Tente novamente; se persistir, avise o suporte.',
  }
  erro.amigavel = AMIGAVEIS[detail] || null
  throw erro
}

async function _req(caminho, opcoes = {}) {
  // headers extraído antes do spread: senão opcoes.headers sobrescreveria o
  // Content-Type e a API receberia o JSON sem interpretação (bug histórico).
  const { headers, ...resto } = opcoes
  const r = await buscar(`${BASE}${caminho}`, {
    ...resto,
    headers: { 'Content-Type': 'application/json', ...(headers || {}) },
  })
  if (!r.ok) await lancarErro(r)
  if (r.status === 204) return null
  const tipo = r.headers.get('content-type') || ''
  return tipo.includes('json') ? r.json() : r.blob()
}

// --- Candidato (token do link mágico) ---
// Verificação pública de assinatura (QR code do manifesto) — sem autenticação.
export const verificarAssinatura = (id) => req(`/verificar/${id}`)

// Portal único de retorno do candidato (CPF + perguntas de verificação).
export const entrada = {
  iniciar: (cpf) =>
    req('/entrar/iniciar', { method: 'POST', body: JSON.stringify({ cpf }) }),
  responder: (desafio, respostas) =>
    req('/entrar/responder', { method: 'POST', body: JSON.stringify({ desafio, respostas }) }),
  linkEmail: (cpf) =>
    req('/entrar/link-email', { method: 'POST', body: JSON.stringify({ cpf }) }),
}

export const candidato = {
  sessao: (t) => req(`/c/${t}`),
  aceiteLgpd: (t) => req(`/c/${t}/aceite-lgpd`, { method: 'POST' }),
  ficha: (t) => req(`/c/${t}/ficha`),
  salvarSecao: (t, secao, dados) =>
    req(`/c/${t}/ficha/${secao}`, { method: 'PUT', body: JSON.stringify(dados) }),
  declarar: (t) => req(`/c/${t}/ficha/declaracao`, { method: 'POST' }),
  fichas: (t) => req(`/c/${t}/fichas`),
  previewUrl: (t, doc) => `${BASE}/c/${t}/fichas/${doc}/preview`,
  solicitarCodigoUnico: (t) => req(`/c/${t}/fichas/solicitar-codigo`, { method: 'POST' }),
  assinarTodos: (t, codigo) =>
    req(`/c/${t}/fichas/assinar`, { method: 'POST', body: JSON.stringify({ codigo }) }),
  trocarOpcaoVt: (t, optante) =>
    req(`/c/${t}/vale-transporte`, { method: 'PUT', body: JSON.stringify({ optante }) }),
  documentos: (t) => req(`/c/${t}/documentos`),
  // arquivo: File único OU array (frente/verso, páginas) — vira um PDF só no slot.
  enviarArquivo: async (t, slotId, arquivo) => {
    const fd = new FormData()
    const lista = Array.isArray(arquivo) ? arquivo : [arquivo]
    lista.forEach((a) => fd.append(lista.length > 1 ? 'arquivos' : 'arquivo', a))
    const r = await buscar(`${BASE}/c/${t}/documentos/${slotId}/arquivo`, { method: 'POST', body: fd })
    if (!r.ok) await lancarErro(r)
    return r.json()
  },
  // Foto do RG OU da CNH: o backend detecta qual é, guarda no slot certo e
  // devolve as sugestões de preenchimento.
  enviarIdentidade: async (t, arquivo) => {
    const fd = new FormData()
    const lista = Array.isArray(arquivo) ? arquivo : [arquivo]
    lista.forEach((a) => fd.append(lista.length > 1 ? 'arquivos' : 'arquivo', a))
    const r = await buscar(`${BASE}/c/${t}/documentos/identidade`, { method: 'POST', body: fd })
    if (!r.ok) await lancarErro(r)
    return r.json()
  },
  meuArquivoUrl: (t, slotId) => `${BASE}/c/${t}/documentos/${slotId}/arquivo`,
  // O PDF no timbrado (o que o RH recebe) — blob, para renderizar na tela em
  // vez de mandar o navegador baixar.
  meuArquivoPdf: (t, slotId) => req(`/c/${t}/documentos/${slotId}/arquivo`),
  // O que a pessoa ENVIOU: a lista (frente, verso, páginas) e cada arquivo.
  meusOriginais: (t, slotId) => req(`/c/${t}/documentos/${slotId}/originais`),
  meuOriginal: (t, slotId, indice) =>
    req(`/c/${t}/documentos/${slotId}/original/${indice}`),
  excluirArquivo: (t, slotId) =>
    req(`/c/${t}/documentos/${slotId}/arquivo`, { method: 'DELETE' }),
  concluirEnvio: (t) => req(`/c/${t}/concluir-envio`, { method: 'POST' }),
  // desfaz o "CONCLUÍ MEU ENVIO" enquanto o RH não revisou nada
  reabrirEnvio: (t) => req(`/c/${t}/reabrir-envio`, { method: 'POST' }),
  // Testes (DISC / situacional) — respondidos antes do cadastro
  testes: (t) => req(`/c/${t}/testes`),
  testesIdentificar: (t, dados) =>
    req(`/c/${t}/testes/identificar`, { method: 'POST', body: JSON.stringify(dados) }),
  testesConfirmar: (t, codigo) =>
    req(`/c/${t}/testes/confirmar`, { method: 'POST', body: JSON.stringify({ codigo }) }),
  testeIniciar: (t, tipo) => req(`/c/${t}/testes/${tipo}/iniciar`, { method: 'POST' }),
  testeQuestoes: (t, tipo) => req(`/c/${t}/testes/${tipo}/questoes`),
  testeResponder: (t, tipo, dados) =>
    req(`/c/${t}/testes/${tipo}/responder`, { method: 'POST', body: JSON.stringify(dados) }),
  testeConcluir: (t, tipo) => req(`/c/${t}/testes/${tipo}/concluir`, { method: 'POST' }),
  testeEventos: (t, tipo, eventos) =>
    req(`/c/${t}/testes/${tipo}/eventos`, { method: 'POST', body: JSON.stringify({ eventos }) }),
  // URL crua para navigator.sendBeacon (descarrega a telemetria ao fechar a página)
  testeEventosUrl: (t, tipo) => `${BASE}/c/${t}/testes/${tipo}/eventos`,
  // Reembolso-creche na admissão (só se o posto do candidato é elegível)
  crecheStatus: (t) => req(`/c/${t}/creche`),
  crecheAddCrianca: (t, dados) =>
    req(`/c/${t}/creche/criancas`, { method: 'POST', body: JSON.stringify(dados) }),
  crecheDelCrianca: (t, id) =>
    req(`/c/${t}/creche/criancas/${id}`, { method: 'DELETE' }),
  crecheSubirDoc: async (t, criancaId, tipo, arquivo) => {
    const fd = new FormData()
    fd.append('arquivo', arquivo)
    const r = await buscar(`${BASE}/c/${t}/creche/criancas/${criancaId}/documento?tipo=${tipo}`,
                           { method: 'POST', body: fd })
    if (!r.ok) await lancarErro(r)
    return r.json()
  },
}

// --- Reembolso-Creche: link público de levantamento (sem token de sessão RH) ---
export const creche = {
  iniciar: (cpf) =>
    req('/creche/iniciar', { method: 'POST', body: JSON.stringify({ cpf }) }),
  confirmar: (cpf, codigo, retomada) =>
    req('/creche/confirmar', { method: 'POST', body: JSON.stringify({ cpf, codigo, retomada }) }),
  // ?t= do e-mail: diz de quem é a tentativa, sem autenticar (o código continua
  // sendo exigido). É o que devolve a pessoa ao ponto onde parou quando ela sai
  // do app de e-mail para ler o código.
  retomar: (t) => req(`/creche/retomar/${t}`),
  // Entrar CONSOME o link — por isso é POST, e só sai daqui por clique da
  // pessoa: antivírus de e-mail (Defender/Safe Links) segue links, não faz POST.
  entrarPeloLink: (t) => req(`/creche/entrar/${t}`, { method: 'POST' }),
  // Verificação de identidade (KBA) para quem não tem e-mail cadastrado
  kbaIniciar: (cpf) =>
    req('/creche/kba/iniciar', { method: 'POST', body: JSON.stringify({ cpf }) }),
  kbaResponder: (desafio, respostas) =>
    req('/creche/kba/responder', { method: 'POST', body: JSON.stringify({ desafio, respostas }) }),
  kbaDefinirEmail: (autorizacao, email) =>
    req('/creche/kba/definir-email', { method: 'POST', body: JSON.stringify({ autorizacao, email }) }),
  sessao: (t) => req(`/creche/sessao/${t}`),
  conferirDados: (t, dados) =>
    req(`/creche/sessao/${t}/dados`, { method: 'PUT', body: JSON.stringify(dados) }),
  addCrianca: (t, dados) =>
    req(`/creche/sessao/${t}/criancas`, { method: 'POST', body: JSON.stringify(dados) }),
  delCrianca: (t, id) =>
    req(`/creche/sessao/${t}/criancas/${id}`, { method: 'DELETE' }),
  subirDocumento: async (t, criancaId, tipo, arquivo) => {
    const fd = new FormData()
    fd.append('arquivo', arquivo)
    const r = await buscar(`${BASE}/creche/sessao/${t}/criancas/${criancaId}/documento?tipo=${tipo}`,
                           { method: 'POST', body: fd })
    if (!r.ok) await lancarErro(r)
    return r.json()
  },
  enviar: (t) => req(`/creche/sessao/${t}/enviar`, { method: 'POST' }),
  crecheSemDireito: (t) => req(`/creche/sessao/${t}/sem-direito`, { method: 'POST' }),

  // Comprovante MENSAL de despesa (v3.02): nota fiscal se a creche é PJ,
  // declaração de quitação se o cuidador é PF. Um por filho e por mês.
  competencias: (t) => req(`/creche/sessao/${t}/competencias`),
  enviarComprovante: async (t, criancaId, ano, mes, arquivos, valor) => {
    // ⚠️ `FormData` NUNCA passa pelo `req()`: ele força `Content-Type: json` e
    // o navegador deixa de escrever o `boundary` — o FastAPI então não separa
    // as partes e devolve 422 "Field required" com o arquivo ali do lado
    // (v2.39.1). Vai por `buscar`, como os demais uploads.
    const fd = new FormData()
    for (const a of arquivos) fd.append('arquivos', a)
    const qs = new URLSearchParams({ crianca_id: criancaId, ano, mes })
    if (valor) qs.set('valor', valor)
    const r = await buscar(`${BASE}/creche/sessao/${t}/competencias?${qs}`,
                           { method: 'POST', body: fd })
    if (!r.ok) await lancarErro(r)
    return r.json()
  },
  requerimentoStatus: (t) => req(`/creche/sessao/${t}/requerimento`),
  assinarRequerimento: (t) =>
    req(`/creche/sessao/${t}/assinar-requerimento`, { method: 'POST' }),
}

// --- Portal do colaborador (/meu): uma porta só para tudo que é da pessoa ---
// Mesmo gate do creche (CPF → 2FA por e-mail; sem e-mail, KBA), mas a sessão é
// do COLABORADOR e não de um benefício.
export const portal = {
  iniciar: (cpf) =>
    req('/portal/iniciar', { method: 'POST', body: JSON.stringify({ cpf }) }),
  confirmar: (cpf, codigo, retomada) =>
    req('/portal/confirmar', { method: 'POST', body: JSON.stringify({ cpf, codigo, retomada }) }),
  retomar: (t) => req(`/portal/retomar/${t}`),
  entrarPeloLink: (t) => req(`/portal/entrar/${t}`, { method: 'POST' }),
  kbaIniciar: (cpf) =>
    req('/portal/kba/iniciar', { method: 'POST', body: JSON.stringify({ cpf }) }),
  kbaResponder: (desafio, respostas) =>
    req('/portal/kba/responder', { method: 'POST', body: JSON.stringify({ desafio, respostas }) }),
  kbaDefinirEmail: (autorizacao, email) =>
    req('/portal/kba/definir-email', { method: 'POST', body: JSON.stringify({ autorizacao, email }) }),
  sessao: (t) => req(`/portal/sessao/${t}`),
  criarRegistro: (t, dados) =>
    req(`/portal/sessao/${t}/registros`, { method: 'POST', body: JSON.stringify(dados) }),
  editarRegistro: (t, id, dados) =>
    req(`/portal/sessao/${t}/registros/${id}`, { method: 'PUT', body: JSON.stringify(dados) }),
  excluirRegistro: (t, id) =>
    req(`/portal/sessao/${t}/registros/${id}`, { method: 'DELETE' }),
  // devolve { registro, sugestoes, leitura } — as sugestões são o que a IA
  // propôs para a PESSOA conferir; nada é gravado a partir delas
  subirDocumento: async (t, registroId, papel, arquivo) => {
    const fd = new FormData()
    fd.append('arquivo', arquivo)
    const r = await buscar(
      `${BASE}/portal/sessao/${t}/registros/${registroId}/documento?papel=${papel}`,
      { method: 'POST', body: fd })
    if (!r.ok) await lancarErro(r)
    return r.json()
  },
  // Seção 9 da cartilha: o direito de resposta do colaborador. "A assinatura
  // indica ciência, não necessariamente concordância" — aqui a discordância cabe.
  manifestar: (t, avaliacaoId, texto) =>
    req(`/portal/sessao/${t}/avaliacoes/${avaliacaoId}/manifestacao`,
        { method: 'POST', body: JSON.stringify({ texto }) }),
}

// --- Testagem (link público /t/{token}: só o nome, resultado visível) ---
export const testagem = {
  info: (t) => req(`/t/${t}`),
  participar: (t, nome) =>
    req(`/t/${t}/participar`, { method: 'POST', body: JSON.stringify({ nome }) }),
  sessao: (t, pid) => req(`/t/${t}/p/${pid}`),
  iniciar: (t, pid, tipo) => req(`/t/${t}/p/${pid}/${tipo}/iniciar`, { method: 'POST' }),
  questoes: (t, pid, tipo) => req(`/t/${t}/p/${pid}/${tipo}/questoes`),
  responder: (t, pid, tipo, dados) =>
    req(`/t/${t}/p/${pid}/${tipo}/responder`, { method: 'POST', body: JSON.stringify(dados) }),
  concluir: (t, pid, tipo) => req(`/t/${t}/p/${pid}/${tipo}/concluir`, { method: 'POST' }),
  resultados: (t, pid) => req(`/t/${t}/p/${pid}/resultados`),
  eventos: (t, pid, tipo, eventos) =>
    req(`/t/${t}/p/${pid}/${tipo}/eventos`, { method: 'POST', body: JSON.stringify({ eventos }) }),
  eventosUrl: (t, pid, tipo) => `${BASE}/t/${t}/p/${pid}/${tipo}/eventos`,
}

// --- Prova por cargo (link público /p/{token}) ---
export const prova = {
  info: (t) => req(`/p/${t}`),
  participar: (t, nome) =>
    req(`/p/${t}/participar`, { method: 'POST', body: JSON.stringify({ nome }) }),
  iniciar: (t, aid) => req(`/p/${t}/a/${aid}/iniciar`, { method: 'POST' }),
  questoes: (t, aid) => req(`/p/${t}/a/${aid}/questoes`),
  responder: (t, aid, dados) =>
    req(`/p/${t}/a/${aid}/responder`, { method: 'POST', body: JSON.stringify(dados) }),
  concluir: (t, aid) => req(`/p/${t}/a/${aid}/concluir`, { method: 'POST' }),
  revisao: (t, aid) => req(`/p/${t}/a/${aid}/revisao`),
  eventos: (t, aid, eventos) =>
    req(`/p/${t}/a/${aid}/eventos`, { method: 'POST', body: JSON.stringify({ eventos }) }),
  eventosUrl: (t, aid) => `${BASE}/p/${t}/a/${aid}/eventos`,
}

// --- Assinatura de signatário externo (link público /assinar/{token}) ---
export const assinaturaExterna = {
  info: (t) => req(`/assinar/${t}`),
  solicitarCodigo: (t) => req(`/assinar/${t}/solicitar-codigo`, { method: 'POST' }),
  confirmar: (t, codigo) =>
    req(`/assinar/${t}/confirmar`, { method: 'POST', body: JSON.stringify({ codigo }) }),
  previewUrl: (t) => `${BASE}/assinar/${t}/preview`,
  assinar: (t) => req(`/assinar/${t}/assinar`, { method: 'POST' }),
}

// Verificação pública de uma etapa de assinatura (QR do manifesto multi)
export const verificarEtapa = (id) => req(`/verificar-etapa/${id}`)

// --- Banco de Talentos (cadastro público, sem token) ---
export const talentos = {
  opcoes: () => req('/talentos/opcoes'),
  cadastrar: (dados) =>
    req('/talentos', { method: 'POST', body: JSON.stringify(dados) }),
  enviarCurriculo: async (id, uploadToken, arquivo) => {
    const fd = new FormData()
    fd.append('arquivo', arquivo)
    const r = await buscar(`${BASE}/talentos/${id}/curriculo?upload_token=${encodeURIComponent(uploadToken)}`,
                           { method: 'POST', body: fd })
    if (!r.ok) await lancarErro(r)
    return r.json()
  },
}

// --- RH (token de sessão no localStorage) ---
const tokenRH = () => localStorage.getItem('rh_token')
export const authRH = () => ({ Authorization: `Bearer ${tokenRH()}` })

export const rh = {
  // --- Carteira de Processos (v2.91) ---
  processos: (cenario = 'C1') =>
    req(`/rh/processos?cenario=${cenario}`, { headers: authRH() }),
  processosOpcoes: () => req('/rh/processos/opcoes', { headers: authRH() }),
  escalaCanais: (cenario = 'C1') =>
    req(`/rh/processos/escala?cenario=${cenario}`, { headers: authRH() }),
  funcoesRH: () => req('/rh/processos/funcoes', { headers: authRH() }),
  criarFuncaoRH: (dados) =>
    req('/rh/processos/funcoes', { method: 'POST', headers: authRH(),
                                   body: JSON.stringify(dados) }),
  editarFuncaoRH: (id, dados) =>
    req(`/rh/processos/funcoes/${id}`, { method: 'PUT', headers: authRH(),
                                         body: JSON.stringify(dados) }),
  criarProcesso: (dados) =>
    req('/rh/processos', { method: 'POST', headers: authRH(),
                           body: JSON.stringify(dados) }),
  editarProcesso: (id, dados) =>
    req(`/rh/processos/${id}`, { method: 'PUT', headers: authRH(),
                                 body: JSON.stringify(dados) }),
  definirCadeia: (id, cenario, funcoes) =>
    req(`/rh/processos/${id}/cadeia`, { method: 'PUT', headers: authRH(),
                                        body: JSON.stringify({ cenario, funcoes }) }),
  excluirProcesso: (id) =>
    req(`/rh/processos/${id}`, { method: 'DELETE', headers: authRH() }),
  // Upload NUNCA passa pelo `req()`: ele força Content-Type JSON e o navegador
  // precisa escrever o `boundary` do multipart (v2.39.1).
  processosImportarPreview: async (arquivo) => {
    const fd = new FormData(); fd.append('arquivo', arquivo)
    const r = await buscar(`${BASE}/rh/processos/importar-preview`,
                           { method: 'POST', headers: authRH(), body: fd })
    if (!r.ok) await lancarErro(r); return r.json()
  },
  processosImportar: async (arquivo) => {
    const fd = new FormData(); fd.append('arquivo', arquivo)
    const r = await buscar(`${BASE}/rh/processos/importar`,
                           { method: 'POST', headers: authRH(), body: fd })
    if (!r.ok) await lancarErro(r); return r.json()
  },

  logado: () => Boolean(tokenRH()),
  login: async (email, senha) => {
    const r = await req('/rh/auth/login', { method: 'POST', body: JSON.stringify({ email, senha }) })
    localStorage.setItem('rh_token', r.token)
    localStorage.setItem('rh_nome', r.nome)
    return r
  },
  sair: () => { localStorage.removeItem('rh_token'); localStorage.removeItem('rh_nome') },
  // Primeiro acesso (v2.84): instalação sem NENHUM usuário cria o próprio
  // administrador. Quem decide é o servidor (a tabela está vazia?), nunca a
  // tela — ver o comentário do portão em `api/auth_rh.py`.
  primeiroAcessoNecessario: () => req('/rh/auth/primeiro-acesso'),
  primeiroAcesso: async (nome, email, senha) => {
    const r = await req('/rh/auth/primeiro-acesso',
                        { method: 'POST', body: JSON.stringify({ nome, email, senha }) })
    // Já entra: a pessoa acabou de escolher a credencial, pedir que a digite de
    // novo é só mais um passo para errar.
    localStorage.setItem('rh_token', r.token)
    localStorage.setItem('rh_nome', r.nome)
    return r
  },
  esqueciSenha: (email) =>
    req('/rh/auth/esqueci-senha', { method: 'POST', body: JSON.stringify({ email }) }),
  redefinirSenha: (token, senha_nova) =>
    req('/rh/auth/redefinir-senha', { method: 'POST',
                                      body: JSON.stringify({ token, senha_nova }) }),
  candidatos: (filtros = {}) => {
    const q = new URLSearchParams(Object.entries(filtros).filter(([, v]) => v)).toString()
    return req(`/rh/candidatos${q ? `?${q}` : ''}`, { headers: authRH() })
  },
  exportarAdmissoes: (filtros = {}) => {
    const q = new URLSearchParams(Object.entries(filtros).filter(([, v]) => v)).toString()
    return req(`/rh/candidatos-exportar${q ? `?${q}` : ''}`, { headers: authRH() })
  },
  metricas: () => req('/rh/metricas', { headers: authRH() }),
  // Testes já respondidos, aproveitados para um candidato (v2.21) — só o RH vê
  testesVinculaveis: (busca) =>
    req(`/rh/testes-vinculaveis${busca ? `?busca=${encodeURIComponent(busca)}` : ''}`,
        { headers: authRH() }),
  testesVinculados: (cid) =>
    req(`/rh/candidatos/${cid}/testes-vinculados`, { headers: authRH() }),
  vincularTeste: (cid, dados) =>
    req(`/rh/candidatos/${cid}/testes-vinculados`,
        { method: 'POST', headers: authRH(), body: JSON.stringify(dados) }),
  desvincularTeste: (cid, vid) =>
    req(`/rh/candidatos/${cid}/testes-vinculados/${vid}`,
        { method: 'DELETE', headers: authRH() }),
  uniformes: (pendentes) =>
    req(`/rh/uniformes${pendentes ? '?pendentes=true' : ''}`, { headers: authRH() }),
  colaboradores: (filtros = {}) => {
    const q = new URLSearchParams(Object.entries(filtros).filter(([, v]) => v)).toString()
    return req(`/rh/colaboradores${q ? `?${q}` : ''}`, { headers: authRH() })
  },
  exportarColaboradores: (filtros = {}) => {
    const q = new URLSearchParams(Object.entries(filtros).filter(([, v]) => v)).toString()
    return req(`/rh/colaboradores/exportar${q ? `?${q}` : ''}`, { headers: authRH() })
  },
  // Importação em massa da base do Tirvu (.xlsx). Idempotente por CPF.
  importarColaboradores: async (arquivo) => {
    const fd = new FormData()
    fd.append('arquivo', arquivo)
    entrouRH()
    try {
      const r = await buscar(`${BASE}/rh/colaboradores/importar`,
                             { method: 'POST', headers: authRH(), body: fd })
      if (!r.ok) await lancarErro(r)
      return r.json()
    } finally { saiuRH() }
  },
  // ---- Integração Tirvu: empresas, jornadas e export de admissões ----
  empresas: () => req('/rh/empresas', { headers: authRH() }),
  criarEmpresa: (dados) =>
    req('/rh/empresas', { method: 'POST', headers: authRH(), body: JSON.stringify(dados) }),
  editarEmpresa: (id, dados) =>
    req(`/rh/empresas/${id}`, { method: 'PUT', headers: authRH(), body: JSON.stringify(dados) }),
  // De-para cargo → ID do Tirvu (o cargo é texto livre; o Tirvu casa por ID).
  cargosTirvu: () => req('/rh/cargos-tirvu', { headers: authRH() }),
  salvarCargoTirvu: (dados) =>
    req('/rh/cargos-tirvu', { method: 'PUT', headers: authRH(), body: JSON.stringify(dados) }),
  jornadas: (postoId) =>
    req(`/rh/jornadas${postoId ? `?posto_id=${postoId}` : ''}`, { headers: authRH() }),
  criarJornada: (dados) =>
    req('/rh/jornadas', { method: 'POST', headers: authRH(), body: JSON.stringify(dados) }),
  editarJornada: (id, dados, { confirmarEstrutura = false } = {}) =>
    req(`/rh/jornadas/${id}${confirmarEstrutura ? '?confirmar_estrutura=true' : ''}`,
        { method: 'PUT', headers: authRH(), body: JSON.stringify(dados) }),
  excluirJornada: (id) =>
    req(`/rh/jornadas/${id}`, { method: 'DELETE', headers: authRH() }),
  // Confirmação em lote da estrutura proposta pelo parser (v2.13): 86% das
  // jornadas saem com confiança alta, e confirmar uma a uma são 325 cliques.
  jornadasAConfirmar: () => req('/rh/jornadas-a-confirmar', { headers: authRH() }),
  confirmarJornadasLote: (dados) =>
    req('/rh/jornadas/confirmar-lote', { method: 'POST', headers: authRH(),
        body: JSON.stringify(dados) }),
  propostaJornada: (id) =>
    req(`/rh/jornadas/${id}/proposta`, { headers: authRH() }),
  jornadasDuplicidades: () =>
    req('/rh/jornadas-duplicidades', { headers: authRH() }),
  importarJornadasPlanilha: async (arquivo) => {
    const fd = new FormData()
    fd.append('arquivo', arquivo)
    entrouRH()
    try {
      const r = await buscar(`${BASE}/rh/jornadas/importar-planilha`,
                             { method: 'POST', headers: authRH(), body: fd })
      if (!r.ok) await lancarErro(r)
      return r.json()
    } finally { saiuRH() }
  },
  importarJornadas: async (arquivo) => {
    const fd = new FormData()
    fd.append('arquivo', arquivo)
    entrouRH()
    try {
      const r = await buscar(`${BASE}/rh/jornadas/importar`,
                             { method: 'POST', headers: authRH(), body: fd })
      if (!r.ok) await lancarErro(r)
      return r.json()
    } finally { saiuRH() }
  },
  // Padronização em massa: cargos/jornadas colados da tela do Tirvu
  // (feedback 2026-07-27) — preview PROPÕE, o RH decide linha a linha,
  // confirmar GRAVA só o que foi marcado (nunca merge cego).
  previewCargosTirvuTxt: (texto) =>
    req('/rh/tirvu-txt/preview-cargos', { method: 'POST', headers: authRH(), body: JSON.stringify({ texto }) }),
  confirmarCargosTirvuTxt: (itens) =>
    req('/rh/tirvu-txt/confirmar-cargos', { method: 'POST', headers: authRH(), body: JSON.stringify({ itens }) }),
  previewJornadasTirvuTxt: (texto) =>
    req('/rh/tirvu-txt/preview-jornadas', { method: 'POST', headers: authRH(), body: JSON.stringify({ texto }) }),
  confirmarJornadasTirvuTxt: (itens) =>
    req('/rh/tirvu-txt/confirmar-jornadas', { method: 'POST', headers: authRH(), body: JSON.stringify({ itens }) }),
  // Mesma coisa a partir do .txt salvo pelo RH (v2.38) — só muda a porta de
  // entrada; a proposta e a confirmação continuam idênticas.
  // ATENÇÃO: upload NÃO passa por `req()` — ele força
  // `Content-Type: application/json`, e aí o navegador não escreve o
  // `boundary` do multipart. O FastAPI recebe um corpo que não sabe separar e
  // responde 422 "Field required" com o arquivo visivelmente presente no log,
  // que é o erro mais enganoso possível (bug de campo 2026-08-01). Use
  // `buscar()` direto e deixe o navegador definir o Content-Type.
  previewCargosArquivo: async (arquivo) => {
    const fd = new FormData(); fd.append('arquivo', arquivo)
    const r = await buscar(`${BASE}/rh/tirvu-txt/preview-cargos-arquivo`,
                           { method: 'POST', headers: authRH(), body: fd })
    if (!r.ok) await lancarErro(r)
    return r.json()
  },
  previewJornadasArquivo: async (arquivo) => {
    const fd = new FormData(); fd.append('arquivo', arquivo)
    const r = await buscar(`${BASE}/rh/tirvu-txt/preview-jornadas-arquivo`,
                           { method: 'POST', headers: authRH(), body: fd })
    if (!r.ok) await lancarErro(r)
    return r.json()
  },
  confirmarCargosTirvu: ({ itens }) =>
    req('/rh/tirvu-txt/confirmar-cargos', { method: 'POST', headers: authRH(), body: JSON.stringify({ itens }) }),
  confirmarJornadasTirvu: ({ itens }) =>
    req('/rh/tirvu-txt/confirmar-jornadas', { method: 'POST', headers: authRH(), body: JSON.stringify({ itens }) }),
  // Vínculo em massa (v2.39): a planilha de Colaboradores traz jornada, cargo,
  // lotação e PCD por pessoa. Preview PROPÕE, aplicar GRAVA o confirmado.
  previewVinculos: async (arquivo) => {
    const fd = new FormData(); fd.append('arquivo', arquivo)
    // idem: multipart não pode passar pelo req (ver comentário acima)
    const r = await buscar(`${BASE}/rh/colaboradores/vinculos/preview`,
                           { method: 'POST', headers: authRH(), body: fd })
    if (!r.ok) await lancarErro(r)
    return r.json()
  },
  aplicarVinculos: (itens) =>
    req('/rh/colaboradores/vinculos/aplicar',
        { method: 'POST', headers: authRH(), body: JSON.stringify({ itens }) }),
  // De-para lotação → posto (v2.40): a lotação do Tirvu vem abreviada e o
  // mesmo texto pode ser dois postos. O sistema sugere, o RH decide uma vez.
  deParaLotacoes: () => req('/rh/postos/de-para', { headers: authRH() }),
  previewDeParaLotacoes: async (arquivo) => {
    const fd = new FormData(); fd.append('arquivo', arquivo)
    // multipart: nunca pelo req() (ver comentário acima)
    const r = await buscar(`${BASE}/rh/postos/de-para/preview`,
                           { method: 'POST', headers: authRH(), body: fd })
    if (!r.ok) await lancarErro(r)
    return r.json()
  },
  confirmarDeParaLotacoes: (itens) =>
    req('/rh/postos/de-para/confirmar',
        { method: 'POST', headers: authRH(), body: JSON.stringify({ itens }) }),
  // Export em massa vive em Colaboradores: só vai para o Tirvu quem já foi
  // efetivado. Por padrão exclui os importados (já existem lá).
  pendenciasTirvu: (filtros = {}) => {
    const q = new URLSearchParams(Object.entries(filtros).filter(([, v]) => v)).toString()
    return req(`/rh/colaboradores/tirvu-pendencias${q ? `?${q}` : ''}`, { headers: authRH() })
  },
  exportarTirvu: (filtros = {}) => {
    const q = new URLSearchParams(Object.entries(filtros).filter(([, v]) => v)).toString()
    return req(`/rh/colaboradores/exportar-tirvu${q ? `?${q}` : ''}`, { headers: authRH() })
  },
  exportarTirvuIndividual: (id) =>
    req(`/rh/candidatos/${id}/exportar-tirvu`, { headers: authRH() }),
  // DEXION: mesmos filtros do Tirvu (a regra de quem entra é a mesma), layout
  // totalmente diferente — 97 colunas, cabeçalho de 4 linhas, datas em serial.
  pendenciasDexion: (filtros = {}) => {
    const q = new URLSearchParams(Object.entries(filtros).filter(([, v]) => v)).toString()
    return req(`/rh/colaboradores/dexion-pendencias${q ? `?${q}` : ''}`, { headers: authRH() })
  },
  exportarDexion: (filtros = {}) => {
    const q = new URLSearchParams(Object.entries(filtros).filter(([, v]) => v)).toString()
    return req(`/rh/colaboradores/exportar-dexion${q ? `?${q}` : ''}`, { headers: authRH() })
  },
  backfillEnderecos: () => req('/rh/enderecos-backfill', { headers: authRH() }),
  aplicarBackfillEnderecos: (itens) =>
    req('/rh/enderecos-backfill', { method: 'POST', headers: authRH(),
                                    body: JSON.stringify(itens) }),
  efetivarColaborador: (id) =>
    req(`/rh/colaboradores/${id}/efetivar`, { method: 'POST', headers: authRH() }),
  efetivarLote: (ids) =>
    req('/rh/colaboradores/lote/efetivar', { method: 'POST', headers: authRH(),
                                             body: JSON.stringify({ ids }) }),
  acaoMassaColaboradores: (ids, acao, data_desligamento) =>
    req('/rh/colaboradores/lote/acao', { method: 'POST', headers: authRH(),
        body: JSON.stringify({ ids, acao, data_desligamento }) }),
  desligarColaborador: (id, data_desligamento) =>
    req(`/rh/colaboradores/${id}/desligar`, { method: 'POST', headers: authRH(),
                                              body: JSON.stringify({ data_desligamento }) }),
  reverterColaborador: (id, destino, motivo) =>
    req(`/rh/colaboradores/${id}/reverter`, { method: 'POST', headers: authRH(),
        body: JSON.stringify({ destino, motivo }) }),
  reverterLote: (ids, destino, motivo) =>
    req('/rh/colaboradores/lote/reverter', { method: 'POST', headers: authRH(),
        body: JSON.stringify({ ids, destino, motivo }) }),
  // Trocar matrícula (v2.45): motivo obrigatório — mexe na chave que liga a
  // pessoa ao histórico de ponto dela.
  trocarMatricula: (id, matricula, motivo) =>
    req(`/rh/colaboradores/${id}/matricula`, { method: 'PUT', headers: authRH(),
        body: JSON.stringify({ matricula, motivo }) }),
  transferirColaborador: (id, posto_id, data_transferencia) =>
    req(`/rh/colaboradores/${id}/transferir`, { method: 'POST', headers: authRH(),
        body: JSON.stringify({ posto_id, data_transferencia }) }),
  novoCandidato: (dados) =>
    req('/rh/candidatos', { method: 'POST', headers: authRH(), body: JSON.stringify(dados) }),
  // Abre o wizard marcado como atendimento presencial: o RH preenche com a
  // pessoa ao lado, e a assinatura dela registra que foi assistida.
  sessaoAssistida: (id) =>
    req(`/rh/candidatos/${id}/sessao-assistida`, { method: 'POST', headers: authRH() }),
  reenviarLink: (id) =>
    req(`/rh/candidatos/${id}/reenviar-link`, { method: 'POST', headers: authRH() }),
  gerarLink: (id) =>
    req(`/rh/candidatos/${id}/reenviar-link?enviar_email_convite=false`,
        { method: 'POST', headers: authRH() }),
  detalhe: (id) => req(`/rh/candidatos/${id}`, { headers: authRH() }),
  editarContato: (id, dados) =>
    req(`/rh/candidatos/${id}/contato`,
        { method: 'PUT', headers: authRH(), body: JSON.stringify(dados) }),
  fichaCandidato: (id) => req(`/rh/candidatos/${id}/ficha`, { headers: authRH() }),
  baixarFicha: (id, documento) =>
    req(`/rh/candidatos/${id}/fichas/${documento}`, { headers: authRH() }),
  notificar: (id) =>
    req(`/rh/candidatos/${id}/notificar`, { method: 'POST', headers: authRH() }),
  enviarTeams: (id) =>
    req(`/rh/candidatos/${id}/teams`, { method: 'POST', headers: authRH() }),
  verAvisos: () => req('/rh/config/avisos', { headers: authRH() }),
  salvarAvisos: (dados) =>
    req('/rh/config/avisos', { method: 'PUT', headers: authRH(), body: JSON.stringify(dados) }),
  verTeams: () => req('/rh/config/teams', { headers: authRH() }),
  salvarTeams: (dados) =>
    req('/rh/config/teams', { method: 'PUT', headers: authRH(), body: JSON.stringify(dados) }),
  testarTeams: () => req('/rh/config/teams/testar', { method: 'POST', headers: authRH() }),
  // Textos dos e-mails do sistema (v2.06)
  listarEmails: () => req('/rh/config/emails', { headers: authRH() }),
  versoesEmail: (chave) => req(`/rh/config/emails/${chave}/versoes`, { headers: authRH() }),
  previewEmail: (chave, dados) =>
    req(`/rh/config/emails/${chave}/preview`,
        { method: 'POST', headers: authRH(), body: JSON.stringify(dados) }),
  // quem recebe um AVISO INTERNO, editável na própria tela do e-mail (v2.21);
  // grava na MESMA matriz de Configurações → Avisos internos
  salvarDestinatariosEmail: (chave, dados) =>
    req(`/rh/config/emails/${chave}/destinatarios`,
        { method: 'PUT', headers: authRH(), body: JSON.stringify(dados) }),
  // manda o texto EM EDIÇÃO para a caixa de quem está editando (v2.16)
  enviarTesteEmail: (chave, dados) =>
    req(`/rh/config/emails/${chave}/enviar-teste`,
        { method: 'POST', headers: authRH(), body: JSON.stringify(dados) }),
  salvarEmail: (chave, dados) =>
    req(`/rh/config/emails/${chave}`,
        { method: 'PUT', headers: authRH(), body: JSON.stringify(dados) }),
  restaurarEmail: (chave, versao) =>
    req(`/rh/config/emails/${chave}/restaurar${versao ? `?versao=${versao}` : ''}`,
        { method: 'POST', headers: authRH() }),
  editarFicha: (id, secao, dados, motivo) =>
    req(`/rh/candidatos/${id}/ficha/${secao}`,
        { method: 'PUT', headers: authRH(), body: JSON.stringify({ dados, motivo }) }),
  // Data que os documentos NÃO assinados desta pessoa carimbam (v2.89).
  // `data` nula volta ao padrão (o dia da geração) — vazio precisa ser valor
  // válido, senão não há como desfazer o que se configurou.
  definirDataDocumentos: (cid, data) =>
    req(`/rh/candidatos/${cid}/data-documentos`, { method: 'PUT', headers: authRH(),
                                                  body: JSON.stringify({ data: data || null }) }),
  informativos: (cid) => req(`/rh/candidatos/${cid}/informativos`, { headers: authRH() }),
  liberarInformativo: (cid) =>
    req(`/rh/candidatos/${cid}/liberar-informativo`, { method: 'POST', headers: authRH() }),
  inserirArquivo: async (slotId, arquivo, origem) => {
    const fd = new FormData()
    // aceita 1 arquivo ou vários (FileList/array) — viram um PDF combinado
    const lista = arquivo?.length != null && typeof arquivo !== 'string'
      ? Array.from(arquivo) : [arquivo]
    lista.filter(Boolean).forEach((f) => fd.append('arquivos', f))
    fd.append('origem', origem || 'whatsapp')
    entrouRH()
    try {
      const r = await buscar(`${BASE}/rh/slots/${slotId}/arquivo`,
                             { method: 'POST', headers: authRH(), body: fd })
      if (!r.ok) await lancarErro(r)
      return r.json()
    } finally { saiuRH() }
  },
  reabrirSlot: (slotId, motivo) =>
    req(`/rh/slots/${slotId}/reabrir`,
        { method: 'POST', headers: authRH(), body: JSON.stringify({ motivo }) }),
  arquivoUrl: (slotId) => `${BASE}/rh/slots/${slotId}/arquivo`,
  arquivo: (slotId) => req(`/rh/slots/${slotId}/arquivo`, { headers: authRH() }),
  aprovar: (slotId) => req(`/rh/slots/${slotId}/aprovar`, { method: 'POST', headers: authRH() }),
  rejeitar: (slotId, motivo, observacao) =>
    req(`/rh/slots/${slotId}/rejeitar`,
        { method: 'POST', headers: authRH(), body: JSON.stringify({ motivo, observacao }) }),
  dispensar: (slotId) => req(`/rh/slots/${slotId}/dispensar`, { method: 'POST', headers: authRH() }),
  aprovarLote: (slotIds) =>
    req('/rh/slots/lote/aprovar', { method: 'POST', headers: authRH(),
                                    body: JSON.stringify({ slot_ids: slotIds }) }),
  rejeitarLote: (slotIds, motivo, observacao) =>
    req('/rh/slots/lote/rejeitar', { method: 'POST', headers: authRH(),
      body: JSON.stringify({ slot_ids: slotIds, motivo, observacao }) }),
  // Devolve { postos, colunas }. Use api.postos().then(r => r.postos) para a lista.
  postos: (incluirInativos = false) =>
    req(`/rh/postos${incluirInativos ? '?incluir_inativos=true' : ''}`, { headers: authRH() }),
  // Cargos já usados na base ({ nome, pessoas }), mais frequentes primeiro.
  cargos: () => req('/rh/cargos', { headers: authRH() }),
  // Duplicar (v2.87): cópia INATIVA e SEM `tirvu_id` — dois postos com o
  // mesmo ID fariam a importação do Tirvu atualizar o posto errado.
  duplicarPosto: (id) =>
    req(`/rh/postos/${id}/duplicar`, { method: 'POST', headers: authRH() }),
  criarPosto: (dados) =>
    req('/rh/postos', { method: 'POST', headers: authRH(), body: JSON.stringify(dados) }),
  editarPosto: (id, dados) =>
    req(`/rh/postos/${id}`, { method: 'PUT', headers: authRH(), body: JSON.stringify(dados) }),
  excluirPosto: (id) =>
    req(`/rh/postos/${id}`, { method: 'DELETE', headers: authRH() }),
  importarPostos: (texto) =>
    req('/rh/postos/importar', { method: 'POST', headers: authRH(), body: JSON.stringify({ texto }) }),
  importarPostosPlanilha: async (arquivo) => {
    const fd = new FormData()
    fd.append('arquivo', arquivo)
    entrouRH()
    try {
      const r = await buscar(`${BASE}/rh/postos/importar-planilha`,
                             { method: 'POST', headers: authRH(), body: fd })
      if (!r.ok) await lancarErro(r)
      return r.json()
    } finally { saiuRH() }
  },
  editarPostosMassa: (dados) =>
    req('/rh/postos/massa', { method: 'PUT', headers: authRH(), body: JSON.stringify(dados) }),
  incidenciaPreview: async (arquivo) => {
    const fd = new FormData()
    fd.append('arquivo', arquivo)
    entrouRH()
    try {
      const r = await buscar(`${BASE}/rh/incidencia/preview`,
                             { method: 'POST', headers: authRH(), body: fd })
      if (!r.ok) await lancarErro(r)
      return r.json()
    } finally { saiuRH() }
  },
  incidenciaConfirmar: (decisoes) =>
    req('/rh/incidencia/confirmar', { method: 'POST', headers: authRH(),
                                      body: JSON.stringify({ decisoes }) }),
  // Versão do sistema + se o banco acompanhou o código. Rota PÚBLICA e sem
  // `authRH`: é a mesma que se abre no navegador para conferir um deploy, e
  // continuar respondendo sem login é o que a torna útil quando o painel está
  // fora do ar. Não começa com `/rh`, então não aciona o indicador de ocupado.
  saude: () => req('/health'),
  // Tamanho máximo de arquivo que o colaborador consegue enviar — editável no
  // painel para não exigir deploy quando o teto se mostra pequeno demais.
  tetoUpload: () => req('/rh/config/upload', { headers: authRH() }),
  salvarTetoUpload: (mb) =>
    req('/rh/config/upload', { method: 'PUT', headers: authRH(),
                               body: JSON.stringify({ mb }) }),
  lixeira: () => req('/rh/lixeira', { headers: authRH() }),
  lixeiraRestaurar: (id) =>
    req(`/rh/lixeira/${id}/restaurar`, { method: 'POST', headers: authRH() }),
  lixeiraConfig: (dias) =>
    req('/rh/lixeira/config', { method: 'PUT', headers: authRH(),
                                body: JSON.stringify({ dias }) }),
  acaoMassaPostos: (posto_ids, acao) =>
    req('/rh/postos/massa/acao', { method: 'POST', headers: authRH(),
                                   body: JSON.stringify({ posto_ids, acao }) }),
  definirColunasPosto: (colunas) =>
    req('/rh/postos/colunas', { method: 'PUT', headers: authRH(), body: JSON.stringify({ colunas }) }),
  definirPosto: (candidatoId, dados) =>
    req(`/rh/candidatos/${candidatoId}/posto`,
        { method: 'PUT', headers: authRH(), body: JSON.stringify(dados) }),
  gerarDossie: (id, forcar = false) =>
    req(`/rh/candidatos/${id}/dossie${forcar ? '?forcar=true' : ''}`,
        { method: 'POST', headers: authRH() }),
  baixarDossie: (id) => req(`/rh/candidatos/${id}/dossie`, { headers: authRH() }),
  // Configurações
  meuPerfil: () => req('/rh/me', { headers: authRH() }),
  salvarPerfil: (dados) =>
    req('/rh/me', { method: 'PUT', headers: authRH(), body: JSON.stringify(dados) }),
  trocarSenha: (senha_atual, senha_nova) =>
    req('/rh/me/senha', { method: 'PUT', headers: authRH(),
                          body: JSON.stringify({ senha_atual, senha_nova }) }),
  verOcr: () => req('/rh/config/ocr', { headers: authRH() }),
  salvarOcr: (dados) =>
    req('/rh/config/ocr', { method: 'PUT', headers: authRH(), body: JSON.stringify(dados) }),
  testarOcr: () => req('/rh/config/ocr/testar', { method: 'POST', headers: authRH() }),
  verGroq: () => req('/rh/config/groq', { headers: authRH() }),
  salvarGroq: (dados) =>
    req('/rh/config/groq', { method: 'PUT', headers: authRH(), body: JSON.stringify(dados) }),
  testarGroq: () => req('/rh/config/groq/testar', { method: 'POST', headers: authRH() }),
  // Minutário de mensagens (v1.98)
  minutarioModelos: (incluirInativos) =>
    req(`/rh/minutario/modelos${incluirInativos ? '?incluir_inativos=true' : ''}`, { headers: authRH() }),
  minutarioDuplicarModelo: (id) =>
    req(`/rh/minutario/modelos/${id}/duplicar`, { method: 'POST', headers: authRH() }),
  // Liga/desliga o modelo no seletor de composição (v2.99). Rota PRÓPRIA: o
  // PATCH exige o corpo inteiro, e reenviar o texto só para alternar um
  // booleano arriscaria sobrescrever o conteúdo.
  minutarioAlternarAtivo: (id) =>
    req(`/rh/minutario/modelos/${id}/ativo`, { method: 'PUT', headers: authRH() }),
  minutarioCriarModelo: (dados) =>
    req('/rh/minutario/modelos', { method: 'POST', headers: authRH(), body: JSON.stringify(dados) }),
  minutarioEditarModelo: (id, dados) =>
    req(`/rh/minutario/modelos/${id}`, { method: 'PATCH', headers: authRH(), body: JSON.stringify(dados) }),
  minutarioExcluirModelo: (id) =>
    req(`/rh/minutario/modelos/${id}`, { method: 'DELETE', headers: authRH() }),
  minutarioCompor: (dados) =>
    req('/rh/minutario/compor', { method: 'POST', headers: authRH(), body: JSON.stringify(dados) }),
  // Match de Vagas × Banco de Talentos (v1.99)
  vagas: (incluirInativas) =>
    req(`/rh/vagas${incluirInativas ? '?incluir_inativas=true' : ''}`, { headers: authRH() }),
  duplicarVaga: (id) =>
    req(`/rh/vagas/${id}/duplicar`, { method: 'POST', headers: authRH() }),
  criarVaga: (dados) =>
    req('/rh/vagas', { method: 'POST', headers: authRH(), body: JSON.stringify(dados) }),
  editarVaga: (id, dados) =>
    req(`/rh/vagas/${id}`, { method: 'PATCH', headers: authRH(), body: JSON.stringify(dados) }),
  excluirVaga: (id) =>
    req(`/rh/vagas/${id}`, { method: 'DELETE', headers: authRH() }),
  // Ranqueamento é ASSÍNCRONO (v2.00): devolve 202 + processamento_id e o
  // trabalho roda no worker. O RH continua usando o sistema e vê o resultado
  // na aba Resultados.
  ranquearVaga: (id, reanalisar = false) =>
    req(`/rh/vagas/${id}/ranquear`, { method: 'POST', headers: authRH(),
                                      body: JSON.stringify({ reanalisar }) }),
  resultadoVaga: (id) => req(`/rh/vagas/${id}/resultado`, { headers: authRH() }),
  processamentosVaga: (id) => req(`/rh/vagas/${id}/processamentos`, { headers: authRH() }),
  statusIndexacaoCurriculos: () => req('/rh/curriculos/indexacao', { headers: authRH() }),
  indexarCurriculos: () =>
    req('/rh/curriculos/indexar', { method: 'POST', headers: authRH() }),
  salvarOpenRouter: (dados) =>
    req('/rh/config/openrouter', { method: 'PUT', headers: authRH(), body: JSON.stringify(dados) }),
  testarOpenRouter: () =>
    req('/rh/config/openrouter/testar', { method: 'POST', headers: authRH() }),
  verSmtp: () => req('/rh/config/smtp', { headers: authRH() }),
  salvarSmtp: (dados) =>
    req('/rh/config/smtp', { method: 'PUT', headers: authRH(), body: JSON.stringify(dados) }),
  testarSmtp: () => req('/rh/config/smtp/testar', { method: 'POST', headers: authRH() }),
  // Remetente próprio do recrutamento (v2.68, § 16.1)
  verRecrutamento: () => req('/rh/config/recrutamento', { headers: authRH() }),
  salvarRecrutamento: (dados) =>
    req('/rh/config/recrutamento', { method: 'PUT', headers: authRH(), body: JSON.stringify(dados) }),
  // Modelos de documento (CRUD + geração)
  modelos: () => req('/rh/modelos-documento', { headers: authRH() }),
  duplicarModelo: (id) =>
    req(`/rh/modelos-documento/${id}/duplicar`, { method: 'POST', headers: authRH() }),
  criarModelo: (dados) =>
    req('/rh/modelos-documento', { method: 'POST', headers: authRH(), body: JSON.stringify(dados) }),
  editarModelo: (id, dados) =>
    req(`/rh/modelos-documento/${id}`, { method: 'PUT', headers: authRH(), body: JSON.stringify(dados) }),
  excluirModelo: (id) =>
    req(`/rh/modelos-documento/${id}`, { method: 'DELETE', headers: authRH() }),
  // Catálogo dos DOCUMENTOS do sistema (v2.16): ver todos, pré-visualizar em
  // PDF, baixar e — nos de texto corrido — criar um modelo editável a partir.
  // Trechos editáveis dos documentos (v2.90). Texto vazio VOLTA ao padrão de
  // fábrica — é o caminho de desfazer, não um documento sem texto.
  textosDocumentos: () => req('/rh/documentos-sistema/textos', { headers: authRH() }),
  salvarTextoDocumento: (chave, texto) =>
    req(`/rh/documentos-sistema/textos/${chave}`, { method: 'PUT', headers: authRH(),
                                                   body: JSON.stringify({ texto }) }),
  documentosSistema: () => req('/rh/documentos-sistema', { headers: authRH() }),
  previaDocumentoSistema: (chave) =>
    req(`/rh/documentos-sistema/${chave}/previa`, { headers: authRH() }),
  duplicarDocumentoSistema: (chave, titulo) =>
    req(`/rh/documentos-sistema/${chave}/duplicar`,
        { method: 'POST', headers: authRH(), body: JSON.stringify({ titulo }) }),
  previaModelo: (id) =>
    req(`/rh/modelos-documento/${id}/previa`, { headers: authRH() }),
  modelosAplicaveis: (candidatoId) =>
    req(`/rh/candidatos/${candidatoId}/modelos-aplicaveis`, { headers: authRH() }),
  gerarModelo: (candidatoId, modeloId) =>
    req(`/rh/candidatos/${candidatoId}/modelos/${modeloId}/gerar`, { headers: authRH() }),
  // Banco de talentos (RH)
  listarTalentos: (filtros = {}) => {
    const q = new URLSearchParams(Object.entries(filtros).filter(([, v]) => v)).toString()
    return req(`/rh/talentos${q ? `?${q}` : ''}`, { headers: authRH() })
  },
  // Cadastro à mão pelo RH (v2.73): a porta que não existia — só havia o
  // formulário público e a importação de planilha. `forcar` é para o homônimo
  // legítimo, depois do aviso de duplicata (409 com quem já existe).
  cadastrarTalento: (dados) =>
    req('/rh/talentos', { method: 'POST', headers: authRH(),
        body: JSON.stringify(dados) }),
  opcoesTalento: () => req('/talentos/opcoes'),
  // Exigências (v2.80): o que é obrigatório na admissão. Padrão da casa em
  // Configurações; exceção por pessoa na ficha dela. `obrigatorio: null`
  // desfaz a exceção e devolve ao padrão — sem isso o RH teria que saber de
  // cor qual era o valor original.
  exigenciasPadrao: () => req('/rh/config/exigencias', { headers: authRH() }),
  salvarExigenciaPadrao: (grupo, chave, obrigatorio) =>
    req('/rh/config/exigencias', { method: 'PUT', headers: authRH(),
        body: JSON.stringify({ grupo, chave, obrigatorio }) }),
  exigenciasDoCandidato: (id) =>
    req(`/rh/candidatos/${id}/exigencias`, { headers: authRH() }),
  ajustarExigencia: (id, grupo, chave, obrigatorio, motivo) =>
    req(`/rh/candidatos/${id}/exigencias`, { method: 'PUT', headers: authRH(),
        body: JSON.stringify({ grupo, chave, obrigatorio, motivo }) }),
  // Documento específico avulso, para COBERTURA (v2.79): a pessoa assina o kit
  // de um posto onde não está lotada, sem mudar o vínculo dela. O motivo é
  // obrigatório e vai para a auditoria junto com o posto dela — é o contraste
  // que torna o registro verificável depois.
  documentosEspecificos: (candidatoId) =>
    req(`/rh/candidatos/${candidatoId}/documentos-especificos`, { headers: authRH() }),
  acrescentarDocumentoEspecifico: (candidatoId, documento, motivo) =>
    req(`/rh/candidatos/${candidatoId}/documento-especifico`, {
      method: 'POST', headers: authRH(),
      body: JSON.stringify({ documento, motivo }) }),
  // Anexar/trocar o currículo pelo painel (v2.74). Faltava: o cadastro à mão
  // dizia "anexe depois pela ficha" e não havia rota para isso — a única era a
  // pública, autorizada por um token com TTL que o RH não tem.
  // ⚠️ `buscar()` direto, NUNCA `req()`: o `_req` força
  // `Content-Type: application/json`, e com FormData quem precisa escrever o
  // cabeçalho (com o `boundary`) é o NAVEGADOR. Sobrescrito, o FastAPI não
  // separa as partes e responde 422 `Field required` — o erro mais enganoso do
  // projeto (v2.39.1). O `test_upload_multipart.py` cobra esta regra.
  anexarCurriculoTalento: async (id, arquivo) => {
    const fd = new FormData()
    fd.append('arquivo', arquivo)
    entrouRH()
    try {
      const r = await buscar(`${BASE}/rh/talentos/${id}/curriculo`,
                             { method: 'POST', headers: authRH(), body: fd })
      if (!r.ok) await lancarErro(r)
      return r.json()
    } finally { saiuRH() }
  },
  // `motivo` vira anotação no mini-CRM (com autor e data) — v2.14
  statusTalento: (id, status, motivo) =>
    req(`/rh/talentos/${id}/status`, { method: 'PUT', headers: authRH(),
        body: JSON.stringify({ status, motivo }) }),
  converterTalento: (id) =>
    req(`/rh/talentos/${id}/converter`, { method: 'POST', headers: authRH() }),
  baixarCurriculoTalento: (id) =>
    req(`/rh/talentos/${id}/curriculo`, { headers: authRH() }),  // devolve blob
  enviarTesteTalento: (id, { tem_disc = true, tem_situacional = true } = {}) =>
    req(`/rh/talentos/${id}/enviar-teste`, { method: 'POST', headers: authRH(),
        body: JSON.stringify({ tem_disc, tem_situacional }) }),
  importarTalentosPlanilha: async (arquivo) => {
    const fd = new FormData()
    fd.append('arquivo', arquivo)
    entrouRH()
    try {
      const r = await buscar(`${BASE}/rh/talentos/importar-planilha`,
                             { method: 'POST', headers: authRH(), body: fd })
      if (!r.ok) await lancarErro(r)
      return r.json()
    } finally { saiuRH() }
  },
  // Mini-CRM: anotações e tags que acompanham a pessoa (talento+candidato).
  // Passa talento_id OU candidato_id — o backend junta os dois lados.
  crmMemoria: (pessoa) => {
    const q = new URLSearchParams(Object.entries(pessoa).filter(([, v]) => v)).toString()
    return req(`/rh/crm/pessoa?${q}`, { headers: authRH() })
  },
  crmTags: (incluirInativas = false) =>
    req(`/rh/crm/tags${incluirInativas ? '?incluir_inativas=true' : ''}`, { headers: authRH() }),
  crmCriarTag: (dados) =>
    req('/rh/crm/tags', { method: 'POST', headers: authRH(), body: JSON.stringify(dados) }),
  crmEditarTag: (id, dados) =>
    req(`/rh/crm/tags/${id}`, { method: 'PATCH', headers: authRH(), body: JSON.stringify(dados) }),
  crmExcluirTag: (id) =>
    req(`/rh/crm/tags/${id}`, { method: 'DELETE', headers: authRH() }),
  crmCriarAnotacao: (dados) =>
    req('/rh/crm/anotacoes', { method: 'POST', headers: authRH(), body: JSON.stringify(dados) }),
  crmEditarAnotacao: (id, texto) =>
    req(`/rh/crm/anotacoes/${id}`, { method: 'PATCH', headers: authRH(), body: JSON.stringify({ texto }) }),
  crmExcluirAnotacao: (id) =>
    req(`/rh/crm/anotacoes/${id}`, { method: 'DELETE', headers: authRH() }),
  crmAnexarAnotacao: async (id, arquivo) => {
    const fd = new FormData()
    fd.append('arquivo', arquivo)
    entrouRH()
    try {
      const r = await buscar(`${BASE}/rh/crm/anotacoes/${id}/anexo`,
                             { method: 'POST', headers: authRH(), body: fd })
      if (!r.ok) await lancarErro(r)
      return r.json()
    } finally { saiuRH() }
  },
  crmAnexo: (id) =>
    req(`/rh/crm/anotacoes/${id}/anexo`, { headers: authRH() }),  // devolve blob
  crmMarcarTag: (dados) =>
    req('/rh/crm/pessoa/tags', { method: 'POST', headers: authRH(), body: JSON.stringify(dados) }),
  crmDesmarcarTag: (pessoa, tagId) => {
    const q = new URLSearchParams({ tag_id: tagId,
      ...Object.fromEntries(Object.entries(pessoa).filter(([, v]) => v)) }).toString()
    return req(`/rh/crm/pessoa/tags?${q}`, { method: 'DELETE', headers: authRH() })
  },
  // Reembolso-Creche (IN 147/2026)
  crecheResumo: () => req('/rh/creche/resumo', { headers: authRH() }),
  crecheTentativasSemAcesso: () => req('/rh/creche/tentativas-sem-acesso', { headers: authRH() }),
  exportarCreche: () => req('/rh/creche/exportar', { headers: authRH() }),
  crecheLevantamentos: (status) =>
    req(`/rh/creche/levantamentos${status ? `?status=${status}` : ''}`, { headers: authRH() }),
  crecheLevantamento: (id) => req(`/rh/creche/levantamentos/${id}`, { headers: authRH() }),
  crecheAtivar: (id, dados) =>
    req(`/rh/creche/levantamentos/${id}/ativar`, { method: 'POST', headers: authRH(),
                                                   body: JSON.stringify(dados) }),
  crecheIndeferir: (id, motivo) =>
    req(`/rh/creche/levantamentos/${id}/indeferir`, { method: 'POST', headers: authRH(),
                                                      body: JSON.stringify({ motivo }) }),
  crecheDevolver: (id, motivo) =>
    req(`/rh/creche/levantamentos/${id}/devolver`, { method: 'POST', headers: authRH(),
                                                     body: JSON.stringify({ motivo }) }),
  crecheMarcarSemDireito: (colaboradorId) =>
    req(`/rh/creche/colaboradores/${colaboradorId}/sem-direito`, { method: 'POST', headers: authRH() }),
  crecheReenviarLink: (beneficioId, email) =>
    req(`/rh/creche/levantamentos/${beneficioId}/reenviar-link`,
        { method: 'POST', headers: authRH(), body: JSON.stringify({ email: email || null }) }),
  crecheReabrir: (beneficioId) =>
    req(`/rh/creche/levantamentos/${beneficioId}/reabrir`, { method: 'POST', headers: authRH() }),
  crecheSuspender: (beneficioId, motivo, encerrar) =>
    req(`/rh/creche/levantamentos/${beneficioId}/suspender`,
        { method: 'POST', headers: authRH(), body: JSON.stringify({ motivo, encerrar: !!encerrar }) }),
  crechePendentesResposta: () => req('/rh/creche/pendentes-resposta', { headers: authRH() }),
  crecheHistorico: (beneficioId) =>
    req(`/rh/creche/levantamentos/${beneficioId}/historico`, { headers: authRH() }),
  crechePrazos: (beneficio_ids, dia_entrega_mensal) =>
    req('/rh/creche/prazos', { method: 'PUT', headers: authRH(),
        body: JSON.stringify({ beneficio_ids, dia_entrega_mensal }) }),
  // Quem faz jus hoje, quem já não faz, e até quando cada criança faz —
  // tudo derivado da data de nascimento, para o fechamento mensal do DP.
  crecheVigencia: () => req('/rh/creche/vigencia', { headers: authRH() }),
  // Defere/indefere UMA criança. O requerimento continua sendo um só: as
  // deferidas vão no corpo, as negadas em seção própria com o motivo.
  crecheDecidirCrianca: (beneficioId, criancaId, decisao, motivo) =>
    req(`/rh/creche/levantamentos/${beneficioId}/criancas/${criancaId}/decidir`,
        { method: 'POST', headers: authRH(),
          body: JSON.stringify({ decisao, motivo }) }),
  // Prazo E valor de UM benefício já aprovado. Campo ausente não é alterado —
  // dá para corrigir só o valor sem ter que reenviar o prazo.
  crecheCondicoes: (id, dados) =>
    req(`/rh/creche/levantamentos/${id}/condicoes`, { method: 'PUT', headers: authRH(),
        body: JSON.stringify(dados) }),
  crecheGerarDossie: (id) =>
    req(`/rh/creche/levantamentos/${id}/dossie`, { method: 'POST', headers: authRH() }),
  crecheBaixarDossie: (id) =>
    req(`/rh/creche/levantamentos/${id}/dossie`, { headers: authRH() }),
  crecheDocumentoUrl: (id, tipo) => `${BASE}/rh/creche/levantamentos/${id}/documento/${tipo}`,

  // --- Cadastro de Desenvolvimento (Onda B) ---
  // `status` vazio = a fila de quem espera decisão (pendente + devolvido).
  desenvolvimentoRegistros: (status = '', candidatoId = '') => {
    const q = new URLSearchParams()
    if (status) q.set('status', status)
    if (candidatoId) q.set('candidato_id', candidatoId)
    const s = q.toString()
    return req(`/rh/desenvolvimento/registros${s ? `?${s}` : ''}`, { headers: authRH() })
  },
  desenvolvimentoValidar: (id, dados) =>
    req(`/rh/desenvolvimento/registros/${id}/validar`,
        { method: 'POST', headers: authRH(), body: JSON.stringify(dados || {}) }),
  desenvolvimentoDevolver: (id, motivo) =>
    req(`/rh/desenvolvimento/registros/${id}/devolver`,
        { method: 'POST', headers: authRH(), body: JSON.stringify({ motivo }) }),
  desenvolvimentoRecusar: (id, motivo) =>
    req(`/rh/desenvolvimento/registros/${id}/recusar`,
        { method: 'POST', headers: authRH(), body: JSON.stringify({ motivo }) }),
  // devolve { validados, barrados } — os barrados vêm COM o motivo, para a tela
  // dizer quem ficou de fora em vez de sumir com eles
  desenvolvimentoValidarLote: (ids) =>
    req('/rh/desenvolvimento/registros/lote/validar',
        { method: 'POST', headers: authRH(), body: JSON.stringify({ ids }) }),
  desenvolvimentoDocumento: (registroId, arquivoId) =>
    req(`/rh/desenvolvimento/registros/${registroId}/documento/${arquivoId}`,
        { headers: authRH() }),
  desenvolvimentoTipos: () => req('/rh/desenvolvimento/tipos', { headers: authRH() }),
  desenvolvimentoCriarTipo: (dados) =>
    req('/rh/desenvolvimento/tipos',
        { method: 'POST', headers: authRH(), body: JSON.stringify(dados) }),
  desenvolvimentoEditarTipo: (id, dados) =>
    req(`/rh/desenvolvimento/tipos/${id}`,
        { method: 'PUT', headers: authRH(), body: JSON.stringify(dados) }),
  desenvolvimentoExcluirTipo: (id) =>
    req(`/rh/desenvolvimento/tipos/${id}`, { method: 'DELETE', headers: authRH() }),
  // Brigada & reciclagem: quem vence, turmas e a solicitação à entidade
  desenvolvimentoBrigadistas: () =>
    req('/rh/desenvolvimento/brigadistas', { headers: authRH() }),
  desenvolvimentoTurmas: () => req('/rh/desenvolvimento/turmas', { headers: authRH() }),
  desenvolvimentoCriarTurma: (dados) =>
    req('/rh/desenvolvimento/turmas',
        { method: 'POST', headers: authRH(), body: JSON.stringify(dados) }),
  // monta o e-mail para o RH CONFERIR — não envia nada
  desenvolvimentoRascunhoMatricula: (dados) =>
    req('/rh/desenvolvimento/matricula/rascunho',
        { method: 'POST', headers: authRH(), body: JSON.stringify(dados) }),
  desenvolvimentoEnviarMatricula: (dados) =>
    req('/rh/desenvolvimento/matricula/enviar',
        { method: 'POST', headers: authRH(), body: JSON.stringify(dados) }),
  desenvolvimentoDossie: (registroId) =>
    req(`/rh/desenvolvimento/registros/${registroId}/dossie`, { headers: authRH() }),

  // --- Gestão de Desempenho: Fatos Observados (Onda C) ---
  fatos: (filtros = {}) => {
    const q = new URLSearchParams()
    for (const [k, v] of Object.entries(filtros)) if (v) q.set(k, v)
    const s = q.toString()
    return req(`/rh/desempenho/fatos${s ? `?${s}` : ''}`, { headers: authRH() })
  },
  criarFato: (dados) =>
    req('/rh/desempenho/fatos',
        { method: 'POST', headers: authRH(), body: JSON.stringify(dados) }),
  editarFato: (id, dados) =>
    req(`/rh/desempenho/fatos/${id}`,
        { method: 'PUT', headers: authRH(), body: JSON.stringify(dados) }),
  excluirFato: (id) =>
    req(`/rh/desempenho/fatos/${id}`, { method: 'DELETE', headers: authRH() }),
  subirAnexoFato: async (id, arquivo) => {
    const fd = new FormData()
    fd.append('arquivo', arquivo)
    const r = await buscar(`${BASE}/rh/desempenho/fatos/${id}/anexo`,
                           { method: 'POST', headers: authRH(), body: fd })
    if (!r.ok) await lancarErro(r)
    return r.json()
  },
  fatoAnexo: (id) => req(`/rh/desempenho/fatos/${id}/anexo`, { headers: authRH() }),
  // escalas, indicadores e competências da cartilha — o front não duplica os textos
  desempenhoFormulario: () => req('/rh/desempenho/formulario', { headers: authRH() }),
  desempenhoColaboradores: () =>
    req('/rh/desempenho/colaboradores', { headers: authRH() }),

  // --- Avaliações (formulário da cartilha) ---
  ciclos: () => req('/rh/desempenho/ciclos', { headers: authRH() }),
  criarCiclo: (dados) =>
    req('/rh/desempenho/ciclos',
        { method: 'POST', headers: authRH(), body: JSON.stringify(dados) }),
  encerrarCiclo: (id) =>
    req(`/rh/desempenho/ciclos/${id}/encerrar`, { method: 'POST', headers: authRH() }),
  avaliacoes: (filtros = {}) => {
    const q = new URLSearchParams()
    for (const [k, v] of Object.entries(filtros)) if (v) q.set(k, v)
    const s = q.toString()
    return req(`/rh/desempenho/avaliacoes${s ? `?${s}` : ''}`, { headers: authRH() })
  },
  avaliacao: (id) => req(`/rh/desempenho/avaliacoes/${id}`, { headers: authRH() }),
  criarAvaliacao: (dados) =>
    req('/rh/desempenho/avaliacoes',
        { method: 'POST', headers: authRH(), body: JSON.stringify(dados) }),
  salvarAvaliacao: (id, dados) =>
    req(`/rh/desempenho/avaliacoes/${id}`,
        { method: 'PUT', headers: authRH(), body: JSON.stringify(dados) }),
  enviarAvaliacao: (id) =>
    req(`/rh/desempenho/avaliacoes/${id}/enviar`, { method: 'POST', headers: authRH() }),
  registrarFeedback: (id, dados) =>
    req(`/rh/desempenho/avaliacoes/${id}/feedback`,
        { method: 'POST', headers: authRH(), body: JSON.stringify(dados) }),
  homologarAvaliacao: (id, dados) =>
    req(`/rh/desempenho/avaliacoes/${id}/homologar`,
        { method: 'POST', headers: authRH(), body: JSON.stringify(dados) }),
  // quanto este avaliador difere dos demais — INFORMA o homologador, não altera nota
  desvioAvaliador: (email, cicloId = '') =>
    req(`/rh/desempenho/avaliadores/${encodeURIComponent(email)}/desvio${
      cicloId ? `?ciclo_id=${cicloId}` : ''}`, { headers: authRH() }),
  radarColaborador: (candidatoId, cicloId = '') =>
    req(`/rh/desempenho/colaboradores/${candidatoId}/radar${
      cicloId ? `?ciclo_id=${cicloId}` : ''}`, { headers: authRH() }),
  // Frequência (ponto do Tirvu) — CONTEXTO, nunca nota
  pontoColaborador: (candidatoId) =>
    req(`/rh/desempenho/colaboradores/${candidatoId}/ponto`, { headers: authRH() }),
  importarPonto: async (arquivo) => {
    const fd = new FormData()
    fd.append('arquivo', arquivo)
    const r = await buscar(`${BASE}/rh/desempenho/ponto/importar`,
                           { method: 'POST', headers: authRH(), body: fd })
    if (!r.ok) await lancarErro(r)
    return r.json()
  },
  // baixam via fetch com Authorization e devolvem blob (para abrir em nova aba)
  crecheBaixarDocumento: (id, tipo) =>
    req(`/rh/creche/levantamentos/${id}/documento/${tipo}`, { headers: authRH() }),
  crecheBaixarDocCrianca: (id, criancaId, tipo) =>
    req(`/rh/creche/levantamentos/${id}/crianca/${criancaId}/documento/${tipo}`,
        { headers: authRH() }),
  // Testes do candidato (resultado restrito ao RH)
  testesCandidato: (id) => req(`/rh/candidatos/${id}/testes`, { headers: authRH() }),
  definirTestes: (id, fazer_disc, fazer_situacional) =>
    req(`/rh/candidatos/${id}/testes`, { method: 'PUT', headers: authRH(),
        body: JSON.stringify({ fazer_disc, fazer_situacional }) }),
  // Links de testagem (aplicação avulsa dos testes, participante vê o resultado)
  testagemLinks: () => req('/rh/testagem/links', { headers: authRH() }),
  testagemCriarLink: (nome, tem_disc = true, tem_situacional = true) =>
    req('/rh/testagem/links', { method: 'POST', headers: authRH(),
                                body: JSON.stringify({ nome, tem_disc, tem_situacional }) }),
  testagemEditarLink: (id, dados) =>
    req(`/rh/testagem/links/${id}`, { method: 'PUT', headers: authRH(),
                                      body: JSON.stringify(dados) }),
  testagemParticipantes: (id) =>
    req(`/rh/testagem/links/${id}/participantes`, { headers: authRH() }),
  // Provas por cargo (banco de provas configurável)
  provas: () => req('/rh/provas', { headers: authRH() }),
  provaDetalhe: (id) => req(`/rh/provas/${id}`, { headers: authRH() }),
  criarProva: (dados) =>
    req('/rh/provas', { method: 'POST', headers: authRH(), body: JSON.stringify(dados) }),
  editarProva: (id, dados) =>
    req(`/rh/provas/${id}`, { method: 'PUT', headers: authRH(), body: JSON.stringify(dados) }),
  excluirProva: (id) => req(`/rh/provas/${id}`, { method: 'DELETE', headers: authRH() }),
  duplicarProva: (id) =>
    req(`/rh/provas/${id}/duplicar`, { method: 'POST', headers: authRH() }),
  criarQuestao: (provaId, dados) =>
    req(`/rh/provas/${provaId}/questoes`, { method: 'POST', headers: authRH(), body: JSON.stringify(dados) }),
  editarQuestao: (provaId, qid, dados) =>
    req(`/rh/provas/${provaId}/questoes/${qid}`, { method: 'PUT', headers: authRH(), body: JSON.stringify(dados) }),
  excluirQuestao: (provaId, qid) =>
    req(`/rh/provas/${provaId}/questoes/${qid}`, { method: 'DELETE', headers: authRH() }),
  duplicarQuestao: (provaId, qid) =>
    req(`/rh/provas/${provaId}/questoes/${qid}/duplicar`, { method: 'POST', headers: authRH() }),
  // Banco de itens (Fase 2): questões reutilizáveis por cargo/senioridade/tags
  bancoItens: (filtros = {}) => {
    const q = new URLSearchParams(Object.entries(filtros).filter(([, v]) => v)).toString()
    return req(`/rh/banco-itens${q ? `?${q}` : ''}`, { headers: authRH() })
  },
  criarItemBanco: (dados) =>
    req('/rh/banco-itens', { method: 'POST', headers: authRH(), body: JSON.stringify(dados) }),
  editarItemBanco: (id, dados) =>
    req(`/rh/banco-itens/${id}`, { method: 'PUT', headers: authRH(), body: JSON.stringify(dados) }),
  excluirItemBanco: (id) =>
    req(`/rh/banco-itens/${id}`, { method: 'DELETE', headers: authRH() }),
  adicionarDoBanco: (provaId, dados) =>
    req(`/rh/provas/${provaId}/adicionar-do-banco`, { method: 'POST', headers: authRH(), body: JSON.stringify(dados) }),
  promoverParaBanco: (provaId, qid, dados) =>
    req(`/rh/provas/${provaId}/questoes/${qid}/promover`, { method: 'POST', headers: authRH(), body: JSON.stringify(dados) }),
  criarLinkProva: (provaId, nome) =>
    req(`/rh/provas/${provaId}/link`, { method: 'POST', headers: authRH(),
        body: JSON.stringify({ nome }) }),
  provaAplicacoes: (filtros = {}) => {
    const q = new URLSearchParams(Object.entries(filtros).filter(([, v]) => v)).toString()
    return req(`/rh/provas-aplicacoes${q ? `?${q}` : ''}`, { headers: authRH() })
  },
  provaAplicacao: (aid) => req(`/rh/provas-aplicacoes/${aid}`, { headers: authRH() }),
  corrigirProva: (aid, correcao_discursivas) =>
    req(`/rh/provas-aplicacoes/${aid}/correcao`, { method: 'PUT', headers: authRH(),
        body: JSON.stringify({ correcao_discursivas }) }),
  // Dash unificado de testes + reset (admissão e testagem)
  testesDash: () => req('/rh/testes/dash', { headers: authRH() }),
  resetarTeste: (candidatoId, tipo) =>
    req(`/rh/candidatos/${candidatoId}/testes/${tipo}/resetar`,
        { method: 'POST', headers: authRH() }),
  resetarTesteTestagem: (participanteId, tipo) =>
    req(`/rh/testagem/participantes/${participanteId}/testes/${tipo}/resetar`,
        { method: 'POST', headers: authRH() }),
  // Modelos: envio pontual para uma pessoa + papéis de assinatura
  enviarModelo: (candidatoId, modeloId, opcoes = {}) =>
    req(`/rh/candidatos/${candidatoId}/modelos/${modeloId}/enviar`,
        { method: 'POST', headers: authRH(), body: JSON.stringify(opcoes) }),
  // Multi-signatário: roteiro de assinatura
  montarRoteiro: (cid, dados) =>
    req(`/rh/candidatos/${cid}/solicitacoes-assinatura`, { method: 'POST', headers: authRH(),
        body: JSON.stringify(dados) }),
  dispararRoteiro: (id) =>
    req(`/rh/solicitacoes-assinatura/${id}/disparar`, { method: 'POST', headers: authRH() }),
  roteirosDoCandidato: (cid) =>
    req(`/rh/candidatos/${cid}/solicitacoes-assinatura`, { headers: authRH() }),
  cancelarRoteiro: (id, motivo) =>
    req(`/rh/solicitacoes-assinatura/${id}/cancelar`, { method: 'POST', headers: authRH(),
        body: JSON.stringify({ motivo }) }),
  minhasAssinaturas: () => req('/rh/minhas-assinaturas', { headers: authRH() }),
  minhasAssinaturasFeitas: () => req('/rh/minhas-assinaturas/feitas', { headers: authRH() }),
  todasSolicitacoes: () => req('/rh/solicitacoes-assinatura', { headers: authRH() }),
  assinaturasDash: (filtros = {}) => {
    const q = new URLSearchParams(Object.entries(filtros).filter(([, v]) => v)).toString()
    return req(`/rh/assinaturas/dash${q ? `?${q}` : ''}`, { headers: authRH() })
  },
  verOrdemAssinatura: () => req('/rh/ordem-assinatura', { headers: authRH() }),
  salvarOrdemAssinatura: (ordem) =>
    req('/rh/ordem-assinatura', { method: 'PUT', headers: authRH(),
        body: JSON.stringify({ ordem }) }),
  assinarEtapaRh: (etapaId, senha) =>
    req(`/rh/etapas/${etapaId}/assinar`, { method: 'POST', headers: authRH(),
        body: JSON.stringify({ senha }) }),
  recusarEtapaRh: (etapaId, motivo) =>
    req(`/rh/etapas/${etapaId}/recusar`, { method: 'POST', headers: authRH(),
        body: JSON.stringify({ motivo }) }),
  // Autorização da equipe (assinatura por autorização prévia)
  autorizacoesEquipe: (modeloId) =>
    req(`/rh/modelos/${modeloId}/autorizacoes-equipe`, { headers: authRH() }),
  criarAutorizacaoEquipe: (dados) =>
    req('/rh/autorizacoes-equipe', { method: 'POST', headers: authRH(),
        body: JSON.stringify(dados) }),
  confirmarAutorizacaoEquipe: (autorizacao_id, codigo) =>
    req('/rh/autorizacoes-equipe/confirmar', { method: 'POST', headers: authRH(),
        body: JSON.stringify({ autorizacao_id, codigo }) }),
  revogarAutorizacaoEquipe: (id) =>
    req(`/rh/autorizacoes-equipe/${id}/revogar`, { method: 'POST', headers: authRH() }),
  roteiroPadrao: (modeloId) =>
    req(`/rh/modelos/${modeloId}/roteiro-padrao`, { headers: authRH() }),
  salvarRoteiroPadrao: (modeloId, etapas) =>
    req(`/rh/modelos/${modeloId}/roteiro-padrao`, { method: 'PUT', headers: authRH(),
        body: JSON.stringify(etapas) }),
  // Identidade visual da empresa
  verMarca: () => req('/rh/marca', { headers: authRH() }),
  salvarMarca: (dados) =>
    req('/rh/marca', { method: 'PUT', headers: authRH(), body: JSON.stringify(dados) }),
  uploadMarcaLogo: async (arquivo) => {
    const fd = new FormData(); fd.append('arquivo', arquivo)
    const r = await buscar(`${BASE}/rh/marca/logo`, { method: 'POST', headers: authRH(), body: fd })
    if (!r.ok) await lancarErro(r); return r.json()
  },
  uploadMarcaFavicon: async (arquivo) => {
    const fd = new FormData(); fd.append('arquivo', arquivo)
    const r = await buscar(`${BASE}/rh/marca/favicon`, { method: 'POST', headers: authRH(), body: fd })
    if (!r.ok) await lancarErro(r); return r.json()
  },
  papeis: () => req('/rh/papeis-assinatura', { headers: authRH() }),
  criarPapel: (dados) =>
    req('/rh/papeis-assinatura', { method: 'POST', headers: authRH(),
                                   body: JSON.stringify(dados) }),
  editarPapel: (id, dados) =>
    req(`/rh/papeis-assinatura/${id}`, { method: 'PUT', headers: authRH(),
                                         body: JSON.stringify(dados) }),
  excluirPapel: (id) =>
    req(`/rh/papeis-assinatura/${id}`, { method: 'DELETE', headers: authRH() }),
  // Arquivo/backup: inventário, download individual e lote (ZIP+XLSX)
  arquivoInventario: (filtros = {}) => {
    const q = new URLSearchParams(Object.entries(filtros).filter(([, v]) => v)).toString()
    return req(`/rh/arquivo/inventario${q ? `?${q}` : ''}`, { headers: authRH() })
  },
  arquivoEstimativa: (pedido) =>
    req('/rh/arquivo/lote/estimativa', { method: 'POST', headers: authRH(),
                                         body: JSON.stringify(pedido) }),
  arquivoDossie: (cid) =>
    req(`/rh/arquivo/pessoa/${cid}/dossie`, { headers: authRH() }),
  arquivoAssinatura: (cid, id) =>
    req(`/rh/arquivo/pessoa/${cid}/assinatura/${id}`, { headers: authRH() }),
  arquivoSlot: (cid, id) =>
    req(`/rh/arquivo/pessoa/${cid}/slot/${id}`, { headers: authRH() }),
  // ZIP em lote: fetch + blob (o corpo é JSON; a resposta é binária/stream)
  arquivoLote: async (pedido) => {
    entrouRH()
    try {
      const r = await buscar(`${BASE}/rh/arquivo/lote`, {
        method: 'POST', headers: { 'Content-Type': 'application/json', ...authRH() },
        body: JSON.stringify(pedido),
      })
      if (!r.ok) await lancarErro(r)
      return r.blob()
    } finally { saiuRH() }
  },
  // Diagnóstico (investigação de incidentes)
  diagnostico: (id) => req(`/rh/candidatos/${id}/diagnostico`, { headers: authRH() }),
  errosRecentes: () => req('/rh/diagnostico/erros', { headers: authRH() }),
  auditoria: () => req('/rh/auditoria', { headers: authRH() }),
  // Telemetria de uso (v2.24) — o que acontece no aparelho das pessoas.
  // Não confundir com a auditoria acima: aquela é prova de ato ("quem fez o
  // quê"), esta é dado de produto ("como foi usar"), e é descartável.
  telemetriaResumo: (dias = 7) =>
    req(`/rh/telemetria/resumo?dias=${dias}`, { headers: authRH() }),
  telemetria: (filtros = {}) => {
    const q = new URLSearchParams(
      Object.entries(filtros).filter(([, v]) => v !== '' && v != null)).toString()
    return req(`/rh/telemetria${q ? `?${q}` : ''}`, { headers: authRH() })
  },
  telemetriaPessoa: (params) => {
    const q = new URLSearchParams(
      Object.entries(params).filter(([, v]) => v)).toString()
    return req(`/rh/telemetria/pessoa?${q}`, { headers: authRH() })
  },
  telemetriaExpurgar: (dados) =>
    req('/rh/telemetria/expurgar',
        { method: 'POST', headers: authRH(), body: JSON.stringify(dados) }),
  // Export de jornada (v2.36): CSV cronológico para análise de caminho fora do
  // painel. Precisa do fetch cru porque o front lê os cabeçalhos — quantas
  // linhas vieram e se o período foi cortado.
  telemetriaJornadaCsv: async ({ dias = 30, origem = '' } = {}) => {
    const q = new URLSearchParams({ dias, ...(origem ? { origem } : {}) })
    const r = await buscar(`${BASE}/rh/telemetria/jornada.csv?${q}`, { headers: authRH() })
    if (!r.ok) await lancarErro(r)
    return {
      blob: await r.blob(),
      linhas: Number(r.headers.get('X-Telemetria-Linhas') || 0),
      truncado: r.headers.get('X-Telemetria-Truncado') === '1',
    }
  },
  // Alertas: regras editáveis que fazem o sistema AVISAR (v2.25)
  alertaRegras: () => req('/rh/telemetria/alertas/regras', { headers: authRH() }),
  criarAlertaRegra: (dados) =>
    req('/rh/telemetria/alertas/regras',
        { method: 'POST', headers: authRH(), body: JSON.stringify(dados) }),
  editarAlertaRegra: (id, dados) =>
    req(`/rh/telemetria/alertas/regras/${id}`,
        { method: 'PUT', headers: authRH(), body: JSON.stringify(dados) }),
  excluirAlertaRegra: (id) =>
    req(`/rh/telemetria/alertas/regras/${id}`, { method: 'DELETE', headers: authRH() }),
  testarAlertas: () =>
    req('/rh/telemetria/alertas/testar', { method: 'POST', headers: authRH() }),
  alertaHistorico: () =>
    req('/rh/telemetria/alertas/historico', { headers: authRH() }),
  telemetriaRetencao: () => req('/rh/telemetria/retencao', { headers: authRH() }),
  salvarTelemetriaRetencao: (dias) =>
    req('/rh/telemetria/retencao',
        { method: 'PUT', headers: authRH(), body: JSON.stringify({ dias }) }),
  // Logs dos serviços (v2.29) — ler no painel, sem SSH.
  logServicos: () => req('/rh/logs/servicos', { headers: authRH() }),
  logLer: ({ servico, dia, busca, nivel, limite }) => {
    const q = new URLSearchParams()
    if (dia) q.set('dia', dia)
    if (busca) q.set('busca', busca)
    if (nivel) q.set('nivel', nivel)
    if (limite) q.set('limite', String(limite))
    const s = q.toString()
    return req(`/rh/logs/${servico}${s ? `?${s}` : ''}`, { headers: authRH() })
  },
  logBaixarUrl: (servico, dia) =>
    `${BASE}/rh/logs/${servico}/baixar${dia ? `?dia=${encodeURIComponent(dia)}` : ''}`,
  logBaixar: (servico, dia) =>
    req(`/rh/logs/${servico}/baixar${dia ? `?dia=${encodeURIComponent(dia)}` : ''}`,
        { headers: authRH() }),  // devolve blob
  salvarLogRetencao: (dias) =>
    req('/rh/logs/retencao',
        { method: 'PUT', headers: authRH(), body: JSON.stringify({ dias }) }),
  logEnviarAgora: () =>
    req('/rh/logs/enviar-agora', { method: 'POST', headers: authRH() }),
  verAssinantes: () => req('/rh/config/assinantes', { headers: authRH() }),
  salvarAssinantes: (dados) =>
    req('/rh/config/assinantes', { method: 'PUT', headers: authRH(), body: JSON.stringify(dados) }),
  // --- Papéis e permissões (v2.86) ---
  // `minhasPermissoes` é o que o painel usa para esconder o que a pessoa não
  // pode. Esconder é cortesia, não segurança — quem protege é o `exige` de
  // cada rota; mas botão que sempre responde 403 ensina a ignorar erro.
  minhasPermissoes: () => req('/rh/permissoes/minhas', { headers: authRH() }),
  catalogoPermissoes: () => req('/rh/permissoes/catalogo', { headers: authRH() }),
  // ⚠️ `papeisAcesso*`, NÃO `papeis*`: as chaves `papeis`/`criarPapel`/
  // `editarPapel` JÁ EXISTEM neste mesmo objeto (papéis de ASSINATURA, acima).
  // Chave repetida em objeto literal sobrescreve a anterior em SILÊNCIO — o
  // build passa e três telas (Config, Modelos, RoteiroAssinatura) passariam a
  // chamar a rota errada. Domínios diferentes, nomes diferentes.
  papeisAcesso: () => req('/rh/papeis', { headers: authRH() }),
  criarPapelAcesso: (dados) =>
    req('/rh/papeis', { method: 'POST', headers: authRH(), body: JSON.stringify(dados) }),
  editarPapelAcesso: (id, dados) =>
    req(`/rh/papeis/${id}`, { method: 'PUT', headers: authRH(), body: JSON.stringify(dados) }),
  excluirPapelAcesso: (id) =>
    req(`/rh/papeis/${id}`, { method: 'DELETE', headers: authRH() }),
  duplicarPapelAcesso: (id) =>
    req(`/rh/papeis/${id}/duplicar`, { method: 'POST', headers: authRH() }),
  // `migrar_para` só é necessário ao DESATIVAR um papel que tem gente dentro —
  // sem ele a rota recusa e devolve os destinos possíveis, para a escolha
  // acontecer na mesma tela em que o bloqueio apareceu.
  ativarPapelAcesso: (id, ativo, migrarPara) =>
    req(`/rh/papeis/${id}/ativo`, { method: 'PUT', headers: authRH(),
                                    body: JSON.stringify({ ativo, migrar_para: migrarPara || null }) }),

  usuarios: () => req('/rh/usuarios', { headers: authRH() }),
  criarUsuario: (dados) =>
    req('/rh/usuarios', { method: 'POST', headers: authRH(), body: JSON.stringify(dados) }),
  editarUsuario: (id, dados) =>
    req(`/rh/usuarios/${id}`, { method: 'PUT', headers: authRH(), body: JSON.stringify(dados) }),
  redefinirSenhaUsuario: (id, senha_nova) =>
    req(`/rh/usuarios/${id}/senha`, { method: 'PUT', headers: authRH(),
                                      body: JSON.stringify({ senha_nova }) }),
  // Credenciais de MÁQUINA (v2.94). O segredo volta SÓ na resposta de
  // `criarTokenAutomacao` — a listagem devolve apenas o prefixo.
  tokensAutomacao: () => req('/rh/tokens-automacao', { headers: authRH() }),
  criarTokenAutomacao: (dados) =>
    req('/rh/tokens-automacao', { method: 'POST', headers: authRH(),
                                  body: JSON.stringify(dados) }),
  revogarTokenAutomacao: (id) =>
    req(`/rh/tokens-automacao/${id}`, { method: 'DELETE', headers: authRH() }),

  verM365: () => req('/rh/config/m365', { headers: authRH() }),
  salvarM365: (dados) =>
    req('/rh/config/m365', { method: 'PUT', headers: authRH(), body: JSON.stringify(dados) }),
  urlLoginM365: () => req('/rh/config/m365/url-login', { headers: authRH() }),
  verWebhook: () => req('/rh/config/webhook', { headers: authRH() }),
  salvarWebhook: (dados) =>
    req('/rh/config/webhook', { method: 'PUT', headers: authRH(), body: JSON.stringify(dados) }),
  testarWebhook: () => req('/rh/config/webhook/testar', { method: 'POST', headers: authRH() }),
  verGmail: () => req('/rh/config/gmail', { headers: authRH() }),
  salvarGmail: (dados) =>
    req('/rh/config/gmail', { method: 'PUT', headers: authRH(), body: JSON.stringify(dados) }),
  urlLoginGmail: () => req('/rh/config/gmail/url-login', { headers: authRH() }),
  desconectarGmail: () =>
    req('/rh/config/gmail/desconectar', { method: 'POST', headers: authRH() }),
  desconectarM365: () =>
    req('/rh/config/m365/desconectar', { method: 'POST', headers: authRH() }),

  // ---- Entrevistas (v2.64) ----
  // O INSTRUMENTO (4 competências, âncoras, escalas, perguntas de triagem) vem
  // daqui e o front NÃO duplica nenhum texto — mudar uma âncora é mexer só em
  // `services/entrevistas.py`, e a tela acompanha sozinha.
  // ⚠️ A FONTE mudou na v2.66 (o instrumento saiu da constante e virou o
  // ROTEIRO no banco); o CONTRATO não: continua sendo daqui que o front lê, e
  // continua sem duplicar texto. Os parâmetros resolvem o roteiro por herança
  // — cargo+senioridade → cargo → padrão.
  formularioEntrevista: ({ roteiroId, cargo, senioridade } = {}) => {
    const q = new URLSearchParams()
    if (roteiroId) q.set('roteiro_id', roteiroId)
    if (cargo) q.set('cargo', cargo)
    if (senioridade) q.set('senioridade', senioridade)
    const s = q.toString()
    return req(`/rh/entrevistas/formulario${s ? `?${s}` : ''}`, { headers: authRH() })
  },
  modalidadesEntrevista: () =>
    req('/rh/entrevistas/modalidades', { headers: authRH() }),
  entrevistas: (filtros = {}) => {
    const q = new URLSearchParams()
    for (const [k, v] of Object.entries(filtros)) if (v) q.set(k, v)
    const s = q.toString()
    return req(`/rh/entrevistas${s ? `?${s}` : ''}`, { headers: authRH() })
  },
  entrevistasPendentes: () =>
    req('/rh/entrevistas/pendencias', { headers: authRH() }),
  entrevista: (id) => req(`/rh/entrevistas/${id}`, { headers: authRH() }),
  criarEntrevista: (dados) =>
    req('/rh/entrevistas',
        { method: 'POST', headers: authRH(), body: JSON.stringify(dados) }),
  salvarEntrevista: (id, dados) =>
    req(`/rh/entrevistas/${id}`,
        { method: 'PUT', headers: authRH(), body: JSON.stringify(dados) }),
  desfechoEntrevista: (id, dados) =>
    req(`/rh/entrevistas/${id}/desfecho`,
        { method: 'POST', headers: authRH(), body: JSON.stringify(dados) }),
  arquivarEntrevista: (id, motivo) =>
    req(`/rh/entrevistas/${id}/arquivar`,
        { method: 'POST', headers: authRH(), body: JSON.stringify({ motivo }) }),
  excluirEntrevista: (id) =>
    req(`/rh/entrevistas/${id}`, { method: 'DELETE', headers: authRH() }),
  // Entrevistas de uma VAGA (comparação) e de uma PESSOA (histórico que
  // atravessa talento↔candidato).
  entrevistasDaVaga: (vagaId) =>
    req(`/rh/vagas/${vagaId}/entrevistas`, { headers: authRH() }),
  entrevistasDaPessoa: ({ talentoId, candidatoId }) => {
    const q = new URLSearchParams()
    if (talentoId) q.set('talento_id', talentoId)
    if (candidatoId) q.set('candidato_id', candidatoId)
    return req(`/rh/pessoa/entrevistas?${q.toString()}`, { headers: authRH() })
  },
  // ⚠️ Upload NUNCA passa pelo `req()`: ele força Content-Type JSON e o
  // navegador precisa escrever o `boundary` do multipart (v2.39.1 — o 422
  // "Field required" mais enganoso do projeto).
  anexarEntrevista: async (id, arquivo) => {
    const fd = new FormData()
    fd.append('arquivo', arquivo)
    const r = await buscar(`${BASE}/rh/entrevistas/${id}/anexo`,
                           { method: 'POST', headers: authRH(), body: fd })
    if (!r.ok) await lancarErro(r)
    return r.json()
  },
  urlAnexoEntrevista: (id) => `${BASE}/rh/entrevistas/${id}/anexo`,

  // ---- Gravação e transcrição da entrevista (v2.97) ----
  // Áudio de entrevista NÃO sai de casa: o faster-whisper roda no container
  // `transcricao`. Nada disto entra no dossiê de admissão (§ 15.4).
  configGravacao: () =>
    req('/rh/entrevistas/gravacao/config', { headers: authRH() }),
  // Confere o token ANTES da entrevista real: sem isto, o RH só descobriria
  // que ele está errado depois de conduzir 40 minutos de conversa.
  testarTokenDiarizacao: (hfToken) =>
    req('/rh/entrevistas/gravacao/testar-token',
        { method: 'POST', headers: authRH(),
          body: JSON.stringify({ hf_token: hfToken || null }) }),
  salvarConfigGravacao: (dados) =>
    req('/rh/entrevistas/gravacao/config',
        { method: 'PUT', headers: authRH(), body: JSON.stringify(dados) }),
  gravacaoEntrevista: (id) =>
    req(`/rh/entrevistas/${id}/gravacao`, { headers: authRH() }),
  consentirGravacao: (id, consentiu) =>
    req(`/rh/entrevistas/${id}/gravacao/consentimento`,
        { method: 'PUT', headers: authRH(), body: JSON.stringify({ consentiu }) }),
  // Upload por `buscar`, nunca por `req` — ver o comentário do anexo acima.
  subirAudioEntrevista: async (id, arquivo, duracaoS) => {
    const fd = new FormData()
    fd.append('arquivo', arquivo)
    const q = duracaoS ? `?duracao_s=${Math.round(duracaoS)}` : ''
    const r = await buscar(`${BASE}/rh/entrevistas/${id}/gravacao${q}`,
                           { method: 'POST', headers: authRH(), body: fd })
    if (!r.ok) await lancarErro(r)
    return r.json()
  },
  retranscreverEntrevista: (id) =>
    req(`/rh/entrevistas/${id}/gravacao/transcrever`, { method: 'POST', headers: authRH() }),
  excluirGravacaoEntrevista: (id) =>
    req(`/rh/entrevistas/${id}/gravacao`, { method: 'DELETE', headers: authRH() }),
  // Bloco de áudio (v2.98): a gravação sobe em pedaços de ~10 min DURANTE a
  // conversa — se o navegador cair, o que já subiu está salvo.
  subirBlocoEntrevista: async (id, arquivo, { indice, duracaoS, inicioS }) => {
    const fd = new FormData()
    fd.append('arquivo', arquivo)
    const q = new URLSearchParams({ indice: String(indice) })
    if (duracaoS) q.set('duracao_s', String(Math.round(duracaoS)))
    if (inicioS != null) q.set('inicio_s', String(Math.round(inicioS)))
    const r = await buscar(`${BASE}/rh/entrevistas/${id}/gravacao/bloco?${q}`,
                           { method: 'POST', headers: authRH(), body: fd })
    if (!r.ok) await lancarErro(r)
    return r.json()
  },
  urlBlocoEntrevista: (id, indice) =>
    `${BASE}/rh/entrevistas/${id}/gravacao/bloco/${indice}/audio`,
  urlAudioEntrevista: (id) => `${BASE}/rh/entrevistas/${id}/gravacao/audio`,
  urlTextoEntrevista: (id) => `${BASE}/rh/entrevistas/${id}/gravacao/texto`,
  urlPdfEntrevista: (id) => `${BASE}/rh/entrevistas/${id}/gravacao/pdf`,

  // ---- Roteiros de entrevista (v2.66, § 14.1) ----
  // O catálogo do instrumento. Rascunho → publicado: só publicado se usa, e é
  // isso que sustenta "o roteiro foi aprovado ANTES de ser usado".
  // `tipo`: 'entrevista' (padrão) ou 'triagem' — são catálogos SEPARADOS, cada
  // um com o seu roteiro padrão (v2.67). Misturá-los mostraria dois padrões.
  roteirosEntrevista: (incluirArquivados = false, tipo = null) => {
    const q = new URLSearchParams()
    if (incluirArquivados) q.set('incluir_arquivados', 'true')
    if (tipo) q.set('tipo', tipo)
    const s = q.toString()
    return req(`/rh/roteiros-entrevista${s ? `?${s}` : ''}`, { headers: authRH() })
  },
  roteiroEntrevista: (id) =>
    req(`/rh/roteiros-entrevista/${id}`, { headers: authRH() }),
  criarRoteiroEntrevista: (dados) =>
    req('/rh/roteiros-entrevista',
        { method: 'POST', headers: authRH(), body: JSON.stringify(dados) }),
  editarRoteiroEntrevista: (id, dados) =>
    req(`/rh/roteiros-entrevista/${id}`,
        { method: 'PUT', headers: authRH(), body: JSON.stringify(dados) }),
  publicarRoteiroEntrevista: (id) =>
    req(`/rh/roteiros-entrevista/${id}/publicar`,
        { method: 'POST', headers: authRH() }),
  duplicarRoteiroEntrevista: (id) =>
    req(`/rh/roteiros-entrevista/${id}/duplicar`,
        { method: 'POST', headers: authRH() }),
  arquivarRoteiroEntrevista: (id, motivo) =>
    req(`/rh/roteiros-entrevista/${id}/arquivar`,
        { method: 'POST', headers: authRH(), body: JSON.stringify({ motivo }) }),
  tornarPadraoRoteiroEntrevista: (id) =>
    req(`/rh/roteiros-entrevista/${id}/tornar-padrao`,
        { method: 'POST', headers: authRH() }),
  excluirRoteiroEntrevista: (id) =>
    req(`/rh/roteiros-entrevista/${id}`, { method: 'DELETE', headers: authRH() }),

  // ---- Documentos do módulo (v2.67, § 15.2-15.4) ----
  // A ficha VIVE no Arquivo e na ficha da pessoa. NÃO vai ao dossiê de
  // admissão: o dossiê circula, e nota de seleção é dado sensível.
  urlDocumentoEntrevista: (id) => `${BASE}/rh/entrevistas/${id}/documento`,
  // Baixa o PDF como BLOB para renderizar na tela (regra da v2.33: documento
  // renderiza, não se baixa). `buscar` direto, sem o `req`, porque a resposta é
  // binária — e o 422 da ficha incompleta precisa chegar com o motivo.
  documentoEntrevista: async (id) => {
    const r = await buscar(`${BASE}/rh/entrevistas/${id}/documento`,
                           { headers: authRH() })
    if (!r.ok) await lancarErro(r)
    return r.blob()
  },
  documentoRoteiro: async (id) => {
    const r = await buscar(`${BASE}/rh/roteiros-entrevista/${id}/documento`,
                           { headers: authRH() })
    if (!r.ok) await lancarErro(r)
    return r.blob()
  },
  assinaturasEntrevista: (id) =>
    req(`/rh/entrevistas/${id}/assinaturas`, { headers: authRH() }),
  // Assinar = o RH que conduziu, com a senha da PRÓPRIA sessão
  // (`prova_metodo="senha_sessao_rh"`). O entrevistado não assina.
  assinarFichaEntrevista: (id, senha) =>
    req(`/rh/entrevistas/${id}/assinar`,
        { method: 'POST', headers: authRH(), body: JSON.stringify({ senha }) }),
  urlDocumentoRoteiro: (id) => `${BASE}/rh/roteiros-entrevista/${id}/documento`,

  // ---- Reaproveitamento (§ 14.3) ----
  // Quem foi entrevistado para a vaga + aplicar a tag do mini-CRM em lote.
  // PROPOSTA, nunca automática: tag aplicada sozinha vira ruído e o RH deixa
  // de confiar na tag.
  entrevistadosDaVaga: (vagaId) =>
    req(`/rh/vagas/${vagaId}/entrevistados`, { headers: authRH() }),
  reaproveitarEntrevistados: (dados) =>
    req('/rh/entrevistas/reaproveitar',
        { method: 'POST', headers: authRH(), body: JSON.stringify(dados) }),
}
