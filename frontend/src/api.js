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
async function buscar(url, opcoes) {
  try {
    return await fetch(url, opcoes)
  } catch (e) {
    const erro = new Error('sem_conexao')
    erro.detail = 'sem_conexao'
    erro.offline = true
    throw erro
  }
}

// Resposta !ok → Error com status + detail SEMPRE string utilizável, mesmo
// quando o corpo não é JSON (413 do proxy vem em HTML) ou o detail é
// estruturado (422 de validação do FastAPI vem como lista).
async function lancarErro(r) {
  let detail
  try { detail = (await r.json()).detail } catch { detail = null }
  if (typeof detail !== 'string') {
    if (r.status === 413) detail = 'arquivo_grande_demais'
    else if (r.status === 422) detail = 'dados_invalidos'
    else detail = r.statusText || 'erro'
  }
  const erro = new Error(detail)
  erro.status = r.status
  erro.detail = detail
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
  excluirArquivo: (t, slotId) =>
    req(`/c/${t}/documentos/${slotId}/arquivo`, { method: 'DELETE' }),
  concluirEnvio: (t) => req(`/c/${t}/concluir-envio`, { method: 'POST' }),
}

// --- Banco de Talentos (cadastro público, sem token) ---
export const talentos = {
  opcoes: () => req('/talentos/opcoes'),
  cadastrar: (dados) =>
    req('/talentos', { method: 'POST', body: JSON.stringify(dados) }),
}

// --- RH (token de sessão no localStorage) ---
const tokenRH = () => localStorage.getItem('rh_token')
const authRH = () => ({ Authorization: `Bearer ${tokenRH()}` })

export const rh = {
  logado: () => Boolean(tokenRH()),
  login: async (email, senha) => {
    const r = await req('/rh/auth/login', { method: 'POST', body: JSON.stringify({ email, senha }) })
    localStorage.setItem('rh_token', r.token)
    localStorage.setItem('rh_nome', r.nome)
    return r
  },
  sair: () => { localStorage.removeItem('rh_token'); localStorage.removeItem('rh_nome') },
  esqueciSenha: (email) =>
    req('/rh/auth/esqueci-senha', { method: 'POST', body: JSON.stringify({ email }) }),
  redefinirSenha: (token, senha_nova) =>
    req('/rh/auth/redefinir-senha', { method: 'POST',
                                      body: JSON.stringify({ token, senha_nova }) }),
  candidatos: () => req('/rh/candidatos', { headers: authRH() }),
  metricas: () => req('/rh/metricas', { headers: authRH() }),
  colaboradores: (filtros = {}) => {
    const q = new URLSearchParams(Object.entries(filtros).filter(([, v]) => v)).toString()
    return req(`/rh/colaboradores${q ? `?${q}` : ''}`, { headers: authRH() })
  },
  exportarColaboradores: (filtros = {}) => {
    const q = new URLSearchParams(Object.entries(filtros).filter(([, v]) => v)).toString()
    return req(`/rh/colaboradores/exportar${q ? `?${q}` : ''}`, { headers: authRH() })
  },
  novoCandidato: (dados) =>
    req('/rh/candidatos', { method: 'POST', headers: authRH(), body: JSON.stringify(dados) }),
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
  notificar: (id) =>
    req(`/rh/candidatos/${id}/notificar`, { method: 'POST', headers: authRH() }),
  editarFicha: (id, secao, dados, motivo) =>
    req(`/rh/candidatos/${id}/ficha/${secao}`,
        { method: 'PUT', headers: authRH(), body: JSON.stringify({ dados, motivo }) }),
  inserirArquivo: async (slotId, arquivo, origem) => {
    const fd = new FormData()
    fd.append('arquivo', arquivo)
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
  postos: () => req('/rh/postos', { headers: authRH() }),
  criarPosto: (dados) =>
    req('/rh/postos', { method: 'POST', headers: authRH(), body: JSON.stringify(dados) }),
  editarPosto: (id, dados) =>
    req(`/rh/postos/${id}`, { method: 'PUT', headers: authRH(), body: JSON.stringify(dados) }),
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
  verSmtp: () => req('/rh/config/smtp', { headers: authRH() }),
  salvarSmtp: (dados) =>
    req('/rh/config/smtp', { method: 'PUT', headers: authRH(), body: JSON.stringify(dados) }),
  testarSmtp: () => req('/rh/config/smtp/testar', { method: 'POST', headers: authRH() }),
  // Modelos de documento (CRUD + geração)
  modelos: () => req('/rh/modelos-documento', { headers: authRH() }),
  criarModelo: (dados) =>
    req('/rh/modelos-documento', { method: 'POST', headers: authRH(), body: JSON.stringify(dados) }),
  editarModelo: (id, dados) =>
    req(`/rh/modelos-documento/${id}`, { method: 'PUT', headers: authRH(), body: JSON.stringify(dados) }),
  excluirModelo: (id) =>
    req(`/rh/modelos-documento/${id}`, { method: 'DELETE', headers: authRH() }),
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
  statusTalento: (id, status) =>
    req(`/rh/talentos/${id}/status`, { method: 'PUT', headers: authRH(), body: JSON.stringify({ status }) }),
  converterTalento: (id) =>
    req(`/rh/talentos/${id}/converter`, { method: 'POST', headers: authRH() }),
  auditoria: () => req('/rh/auditoria', { headers: authRH() }),
  verAssinantes: () => req('/rh/config/assinantes', { headers: authRH() }),
  salvarAssinantes: (dados) =>
    req('/rh/config/assinantes', { method: 'PUT', headers: authRH(), body: JSON.stringify(dados) }),
  usuarios: () => req('/rh/usuarios', { headers: authRH() }),
  criarUsuario: (dados) =>
    req('/rh/usuarios', { method: 'POST', headers: authRH(), body: JSON.stringify(dados) }),
  editarUsuario: (id, dados) =>
    req(`/rh/usuarios/${id}`, { method: 'PUT', headers: authRH(), body: JSON.stringify(dados) }),
  redefinirSenhaUsuario: (id, senha_nova) =>
    req(`/rh/usuarios/${id}/senha`, { method: 'PUT', headers: authRH(),
                                      body: JSON.stringify({ senha_nova }) }),
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
}
