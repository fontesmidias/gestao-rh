const BASE = '/api'

async function req(caminho, opcoes = {}) {
  const r = await fetch(`${BASE}${caminho}`, {
    headers: { 'Content-Type': 'application/json', ...(opcoes.headers || {}) },
    ...opcoes,
  })
  if (!r.ok) {
    let detail
    try { detail = (await r.json()).detail } catch { detail = r.statusText }
    const erro = new Error(typeof detail === 'string' ? detail : 'erro')
    erro.status = r.status
    erro.detail = detail
    throw erro
  }
  if (r.status === 204) return null
  const tipo = r.headers.get('content-type') || ''
  return tipo.includes('json') ? r.json() : r.blob()
}

// --- Candidato (token do link mágico) ---
export const candidato = {
  sessao: (t) => req(`/c/${t}`),
  aceiteLgpd: (t) => req(`/c/${t}/aceite-lgpd`, { method: 'POST' }),
  ficha: (t) => req(`/c/${t}/ficha`),
  salvarSecao: (t, secao, dados) =>
    req(`/c/${t}/ficha/${secao}`, { method: 'PUT', body: JSON.stringify(dados) }),
  declarar: (t) => req(`/c/${t}/ficha/declaracao`, { method: 'POST' }),
  fichas: (t) => req(`/c/${t}/fichas`),
  previewUrl: (t, doc) => `${BASE}/c/${t}/fichas/${doc}/preview`,
  solicitarCodigo: (t, doc) => req(`/c/${t}/fichas/${doc}/solicitar-codigo`, { method: 'POST' }),
  assinar: (t, doc, codigo) =>
    req(`/c/${t}/fichas/${doc}/assinar`, { method: 'POST', body: JSON.stringify({ codigo }) }),
  documentos: (t) => req(`/c/${t}/documentos`),
  enviarArquivo: async (t, slotId, arquivo) => {
    const fd = new FormData()
    fd.append('arquivo', arquivo)
    const r = await fetch(`${BASE}/c/${t}/documentos/${slotId}/arquivo`, { method: 'POST', body: fd })
    if (!r.ok) {
      const { detail } = await r.json()
      const erro = new Error(detail)
      erro.detail = detail
      throw erro
    }
    return r.json()
  },
  concluirEnvio: (t) => req(`/c/${t}/concluir-envio`, { method: 'POST' }),
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
  candidatos: () => req('/rh/candidatos', { headers: authRH() }),
  novoCandidato: (dados) =>
    req('/rh/candidatos', { method: 'POST', headers: authRH(), body: JSON.stringify(dados) }),
  reenviarLink: (id) =>
    req(`/rh/candidatos/${id}/reenviar-link`, { method: 'POST', headers: authRH() }),
  detalhe: (id) => req(`/rh/candidatos/${id}`, { headers: authRH() }),
  arquivoUrl: (slotId) => `${BASE}/rh/slots/${slotId}/arquivo`,
  arquivo: (slotId) => req(`/rh/slots/${slotId}/arquivo`, { headers: authRH() }),
  aprovar: (slotId) => req(`/rh/slots/${slotId}/aprovar`, { method: 'POST', headers: authRH() }),
  rejeitar: (slotId, motivo, observacao) =>
    req(`/rh/slots/${slotId}/rejeitar`,
        { method: 'POST', headers: authRH(), body: JSON.stringify({ motivo, observacao }) }),
  dispensar: (slotId) => req(`/rh/slots/${slotId}/dispensar`, { method: 'POST', headers: authRH() }),
  gerarDossie: (id) => req(`/rh/candidatos/${id}/dossie`, { method: 'POST', headers: authRH() }),
  baixarDossie: (id) => req(`/rh/candidatos/${id}/dossie`, { headers: authRH() }),
  // Configurações
  meuPerfil: () => req('/rh/me', { headers: authRH() }),
  salvarPerfil: (dados) =>
    req('/rh/me', { method: 'PUT', headers: authRH(), body: JSON.stringify(dados) }),
  trocarSenha: (senha_atual, senha_nova) =>
    req('/rh/me/senha', { method: 'PUT', headers: authRH(),
                          body: JSON.stringify({ senha_atual, senha_nova }) }),
  verSmtp: () => req('/rh/config/smtp', { headers: authRH() }),
  salvarSmtp: (dados) =>
    req('/rh/config/smtp', { method: 'PUT', headers: authRH(), body: JSON.stringify(dados) }),
  testarSmtp: () => req('/rh/config/smtp/testar', { method: 'POST', headers: authRH() }),
  auditoria: () => req('/rh/auditoria', { headers: authRH() }),
  verM365: () => req('/rh/config/m365', { headers: authRH() }),
  salvarM365: (dados) =>
    req('/rh/config/m365', { method: 'PUT', headers: authRH(), body: JSON.stringify(dados) }),
  urlLoginM365: () => req('/rh/config/m365/url-login', { headers: authRH() }),
  desconectarM365: () =>
    req('/rh/config/m365/desconectar', { method: 'POST', headers: authRH() }),
}
