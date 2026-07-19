// Telemetria de comportamento durante os testes (informada nas instruções):
// registra QUANDO a pessoa sai da tela, troca de aba/janela, tenta printar,
// copia/cola ou perde conexão. Os eventos vão em lotes para o backend e só o
// RH os lê — servem para entender o comportamento e melhorar o sistema.
import { candidato as api } from '../api.js'

export function iniciarTelemetria(token, tipo) {
  const inicio = Date.now()
  let fila = []
  const anota = (e, d) => {
    fila.push({ t: (Date.now() - inicio) / 1000, e, ...(d ? { d } : {}) })
  }

  const enviar = () => {
    if (!fila.length) return
    const lote = fila
    fila = []
    api.testeEventos(token, tipo, lote).catch(() => { fila = lote.concat(fila) })
  }
  const descarga = () => {
    // ao fechar/sair da página, o fetch normal pode ser cancelado — beacon não
    anota('saida_pagina')
    if (navigator.sendBeacon) {
      navigator.sendBeacon(api.testeEventosUrl(token, tipo),
        new Blob([JSON.stringify({ eventos: fila })], { type: 'application/json' }))
      fila = []
    } else enviar()
  }

  const aoVisibilidade = () => anota(document.hidden ? 'oculto' : 'visivel')
  const aoDesfocar = () => anota('desfocou')
  const aoFocar = () => anota('focou')
  const aoTecla = (ev) => { if (ev.key === 'PrintScreen') anota('print') }
  const aoCopiar = () => anota('copiou')
  const aoRecortar = () => anota('recortou')
  const aoColar = () => anota('colou')
  const aoMenu = () => anota('menu_contexto')
  const aoOffline = () => anota('offline')
  const aoOnline = () => anota('online')

  document.addEventListener('visibilitychange', aoVisibilidade)
  window.addEventListener('blur', aoDesfocar)
  window.addEventListener('focus', aoFocar)
  window.addEventListener('keyup', aoTecla)
  document.addEventListener('copy', aoCopiar)
  document.addEventListener('cut', aoRecortar)
  document.addEventListener('paste', aoColar)
  document.addEventListener('contextmenu', aoMenu)
  window.addEventListener('offline', aoOffline)
  window.addEventListener('online', aoOnline)
  window.addEventListener('pagehide', descarga)

  anota('teste_aberto', `${window.screen?.width || '?'}x${window.screen?.height || '?'}`)
  const intervalo = setInterval(enviar, 8000)

  return () => {
    clearInterval(intervalo)
    enviar()
    document.removeEventListener('visibilitychange', aoVisibilidade)
    window.removeEventListener('blur', aoDesfocar)
    window.removeEventListener('focus', aoFocar)
    window.removeEventListener('keyup', aoTecla)
    document.removeEventListener('copy', aoCopiar)
    document.removeEventListener('cut', aoRecortar)
    document.removeEventListener('paste', aoColar)
    document.removeEventListener('contextmenu', aoMenu)
    window.removeEventListener('offline', aoOffline)
    window.removeEventListener('online', aoOnline)
    window.removeEventListener('pagehide', descarga)
  }
}
