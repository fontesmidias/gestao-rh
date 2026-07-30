// Telemetria de uso — o que acontece NO APARELHO da pessoa (v2.24).
//
// Existe por causa do incidente de 2026-07-29: dois candidatos travaram com a
// tela em branco e o erro morreu no navegador deles. A telemetria HTTP do
// servidor registrou 200 em tudo, porque do lado dele deu tudo certo — o
// `TypeError` aconteceu no React, depois da resposta.
//
// Quatro famílias: erro, fricção (onde a pessoa trava), jornada (por onde
// passou) e desempenho (quanto demorou de verdade em 4G).
//
// NUNCA registra o que a pessoa digita — só o NOME da etapa e o que aconteceu
// com ela. A minimização de IP/user-agent é feita no servidor, na entrada.
//
// Não confundir com `candidato/telemetria.js`, que é a telemetria de
// COMPORTAMENTO durante os testes (troca de aba, print) e é informada nas
// instruções do teste. São propósitos diferentes e ficam separadas de propósito.

const FILA = []
let temporizador = null
let contexto = { origem: 'publico', token: null, talentoId: null }

// Sessão anônima: liga os eventos de uma MESMA visita sem identificar ninguém.
// Vive só na aba (sessionStorage) — fechou, acabou.
const SESSAO = (() => {
  try {
    let s = sessionStorage.getItem('tel-sessao')
    if (!s) {
      s = Math.random().toString(36).slice(2, 12) + Date.now().toString(36)
      sessionStorage.setItem('tel-sessao', s)
    }
    return s
  } catch { return null }   // modo privado com storage bloqueado
})()

// Versão do bundle: em 2026-07-29 foi exatamente o que faltou para saber se a
// aba estava com código velho. O Vite injeta o hash no nome do arquivo.
const VERSAO = (() => {
  try {
    const src = document.querySelector('script[src*="/assets/"]')?.src || ''
    return src.split('/').pop()?.slice(0, 40) || null
  } catch { return null }
})()

export function definirContexto(novo) {
  contexto = { ...contexto, ...novo }
}

function agendarEnvio() {
  if (temporizador) return
  // 3s: junta os eventos de uma interação num lote só. Enviar a cada evento
  // faria a telemetria competir com as chamadas que a pessoa está esperando.
  temporizador = setTimeout(enviar, 3000)
}

async function enviar() {
  clearTimeout(temporizador)
  temporizador = null
  if (!FILA.length) return
  const lote = FILA.splice(0, 50)
  const corpo = JSON.stringify({
    eventos: lote, sessao: SESSAO, origem: contexto.origem,
    token: contexto.token, talento_id: contexto.talentoId,
  })
  try {
    // A rota do painel identifica o usuário do RH; a pública, não.
    const rota = contexto.origem === 'rh' ? '/api/rh/telemetria' : '/api/telemetria'
    const cab = { 'Content-Type': 'application/json' }
    if (contexto.origem === 'rh') {
      const t = localStorage.getItem('rh_token')
      if (t) cab.Authorization = `Bearer ${t}`
    }
    await fetch(rota, { method: 'POST', headers: cab, body: corpo, keepalive: true })
  } catch {
    // Telemetria que falha JAMAIS pode atrapalhar quem está usando o sistema.
    // Descarta em silêncio — mesma regra do `avisar()` no backend.
  }
}

export function anotar(evento, { tipo = 'jornada', pagina, duracao_ms, detalhe } = {}) {
  try {
    FILA.push({
      evento: String(evento).slice(0, 60), tipo,
      pagina: (pagina || window.location.pathname).slice(0, 120),
      duracao_ms: duracao_ms == null ? undefined : Math.round(duracao_ms),
      detalhe, versao: VERSAO,
    })
    // Erro não espera o lote: se a página está quebrando, ela pode morrer
    // antes dos 3 segundos e o registro se perderia — justamente o que
    // aconteceu no incidente que originou este módulo.
    if (tipo === 'erro') enviar()
    else agendarEnvio()
  } catch { /* nunca propaga */ }
}

export const anotarErro = (mensagem, extra = {}) =>
  anotar('erro_render', { tipo: 'erro', detalhe: { mensagem: String(mensagem).slice(0, 500), ...extra } })

export const anotarFriccao = (evento, detalhe) =>
  anotar(evento, { tipo: 'friccao', detalhe })

// Mede quanto uma ação demorou DE VERDADE, no aparelho da pessoa.
export async function medir(nome, promessa) {
  const t0 = performance.now()
  try {
    return await promessa
  } finally {
    const ms = performance.now() - t0
    // Só registra o que passou de 1,5s: abaixo disso é ruído e encheria a
    // tabela sem ensinar nada.
    if (ms > 1500) anotar(nome, { tipo: 'desempenho', duracao_ms: ms })
  }
}

// Erros globais que nenhum ErrorBoundary pega (fora do React, em promessa solta).
export function instalarCapturaGlobal() {
  window.addEventListener('error', (e) => {
    if (e?.message) anotarErro(e.message, { origem: 'window.error', arquivo: e.filename?.slice(0, 120) })
  })
  window.addEventListener('unhandledrejection', (e) => {
    const m = e?.reason?.message || e?.reason
    if (m) anotarErro(m, { origem: 'promessa' })
  })
  // Descarga ao sair: o lote pendente não pode morrer com a aba.
  const descarregar = () => {
    if (!FILA.length) return
    try {
      navigator.sendBeacon?.('/api/telemetria', new Blob([JSON.stringify({
        eventos: FILA.splice(0, 50), sessao: SESSAO,
        origem: contexto.origem, token: contexto.token, talento_id: contexto.talentoId,
      })], { type: 'application/json' }))
    } catch { /* ignora */ }
  }
  window.addEventListener('pagehide', descarregar)
  // `visibilitychange` é o que REALMENTE dispara no celular: o candidato sai do
  // navegador para fotografar o documento e volta — o `pagehide` pode nunca
  // acontecer numa sessão inteira. Sem isto, a telemetria de quem usa o celular
  // (a maioria) só chegaria quando a aba fosse fechada de vez.
  document.addEventListener('visibilitychange', () => {
    if (document.hidden) descarregar()
  })
}
