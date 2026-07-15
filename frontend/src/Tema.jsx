import { useEffect, useState } from 'react'

// Tema claro/escuro: começa seguindo o aparelho (prefers-color-scheme) e o
// botão alterna na hora; a escolha manual fica lembrada no dispositivo.
const doSistema = () =>
  window.matchMedia('(prefers-color-scheme: dark)').matches ? 'escuro' : 'claro'

export function temaAtual() {
  return localStorage.getItem('tema') || doSistema()
}

export function aplicarTema(tema) {
  document.documentElement.dataset.tema = tema
}

export default function BotaoTema() {
  const [tema, setTema] = useState(temaAtual)
  useEffect(() => { aplicarTema(tema) }, [tema])
  useEffect(() => {
    // Sem escolha manual, acompanha mudanças do aparelho em tempo real.
    const mq = window.matchMedia('(prefers-color-scheme: dark)')
    const ouvir = () => { if (!localStorage.getItem('tema')) setTema(doSistema()) }
    mq.addEventListener('change', ouvir)
    return () => mq.removeEventListener('change', ouvir)
  }, [])
  const alternar = () => {
    const novo = tema === 'escuro' ? 'claro' : 'escuro'
    localStorage.setItem('tema', novo)
    setTema(novo)
  }
  return (
    <button className="btn-tema" onClick={alternar}
            title={tema === 'escuro' ? 'Mudar para o tema claro' : 'Mudar para o tema escuro'}
            aria-label="Alternar tema claro/escuro">
      {tema === 'escuro' ? '☀️' : '🌙'}
    </button>
  )
}
