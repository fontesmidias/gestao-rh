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
  // Mensagem amigável para códigos globais conhecidos (o call-site pode usar
  // e.amigavel quando quiser, ou continua com e.detail). A trava de duplo-clique
  // devolve 409 ja_em_processamento — o RH clicou de novo enquanto processava.
  const AMIGAVEIS = {
    ja_em_processamento: 'Esta ação já está sendo processada — aguarde um instante.',
    muitas_tentativas: 'Muitas tentativas seguidas. Aguarde alguns minutos.',
    sem_conexao: 'Sem conexão. Verifique a internet e tente de novo.',
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
  excluirArquivo: (t, slotId) =>
    req(`/c/${t}/documentos/${slotId}/arquivo`, { method: 'DELETE' }),
  concluirEnvio: (t) => req(`/c/${t}/concluir-envio`, { method: 'POST' }),
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
  confirmar: (cpf, codigo) =>
    req('/creche/confirmar', { method: 'POST', body: JSON.stringify({ cpf, codigo }) }),
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
  confirmar: (cpf, codigo) =>
    req('/portal/confirmar', { method: 'POST', body: JSON.stringify({ cpf, codigo }) }),
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
  candidatos: (filtros = {}) => {
    const q = new URLSearchParams(Object.entries(filtros).filter(([, v]) => v)).toString()
    return req(`/rh/candidatos${q ? `?${q}` : ''}`, { headers: authRH() })
  },
  exportarAdmissoes: (filtros = {}) => {
    const q = new URLSearchParams(Object.entries(filtros).filter(([, v]) => v)).toString()
    return req(`/rh/candidatos-exportar${q ? `?${q}` : ''}`, { headers: authRH() })
  },
  metricas: () => req('/rh/metricas', { headers: authRH() }),
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
  jornadas: (postoId) =>
    req(`/rh/jornadas${postoId ? `?posto_id=${postoId}` : ''}`, { headers: authRH() }),
  criarJornada: (dados) =>
    req('/rh/jornadas', { method: 'POST', headers: authRH(), body: JSON.stringify(dados) }),
  editarJornada: (id, dados, { confirmarEstrutura = false } = {}) =>
    req(`/rh/jornadas/${id}${confirmarEstrutura ? '?confirmar_estrutura=true' : ''}`,
        { method: 'PUT', headers: authRH(), body: JSON.stringify(dados) }),
  excluirJornada: (id) =>
    req(`/rh/jornadas/${id}`, { method: 'DELETE', headers: authRH() }),
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
  transferirColaborador: (id, posto_id, data_transferencia) =>
    req(`/rh/colaboradores/${id}/transferir`, { method: 'POST', headers: authRH(),
        body: JSON.stringify({ posto_id, data_transferencia }) }),
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
  // Devolve { postos, colunas }. Use api.postos().then(r => r.postos) para a lista.
  postos: (incluirInativos = false) =>
    req(`/rh/postos${incluirInativos ? '?incluir_inativos=true' : ''}`, { headers: authRH() }),
  // Cargos já usados na base ({ nome, pessoas }), mais frequentes primeiro.
  cargos: () => req('/rh/cargos', { headers: authRH() }),
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
  // Reembolso-Creche (IN 147/2026)
  crecheResumo: () => req('/rh/creche/resumo', { headers: authRH() }),
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
  criarQuestao: (provaId, dados) =>
    req(`/rh/provas/${provaId}/questoes`, { method: 'POST', headers: authRH(), body: JSON.stringify(dados) }),
  editarQuestao: (provaId, qid, dados) =>
    req(`/rh/provas/${provaId}/questoes/${qid}`, { method: 'PUT', headers: authRH(), body: JSON.stringify(dados) }),
  excluirQuestao: (provaId, qid) =>
    req(`/rh/provas/${provaId}/questoes/${qid}`, { method: 'DELETE', headers: authRH() }),
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
