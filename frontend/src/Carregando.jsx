import { useEffect, useState } from 'react'

// Overlay de carregamento com AMPULHETA (pedido do Bruno, 2026-07-17): para
// ações que o RH dispara de propósito e precisa aguardar — importar a base,
// gerar dossiê, exportar Excel. Fundo levemente escurecido + ampulheta que
// vira como areia de verdade (gira 180°, faz uma pausa, vira de novo) —
// velocidade coerente, sem rodopio nervoso. NÃO é para autosave: aquele
// continua na barrinha fininha do topo (BarraAtividade), que não cobre a tela.
//
// Uso: controlado por um evento global 'rh-ampulheta' com {ativo, texto}.
// O helper comAmpulheta() abaixo embrulha uma promise e cuida de ligar/desligar.

export function ampulheta(ativo, texto = '') {
  window.dispatchEvent(new CustomEvent('rh-ampulheta', { detail: { ativo, texto } }))
}

// Embrulha uma ação assíncrona: mostra a ampulheta enquanto ela corre e a
// esconde ao final (mesmo em erro). Devolve o resultado da própria promise.
export async function comAmpulheta(texto, fn) {
  ampulheta(true, texto)
  try {
    return await fn()
  } finally {
    ampulheta(false)
  }
}

export default function Carregando() {
  const [estado, setEstado] = useState({ ativo: false, texto: '' })

  useEffect(() => {
    const aoMudar = (e) => setEstado(e.detail)
    window.addEventListener('rh-ampulheta', aoMudar)
    return () => window.removeEventListener('rh-ampulheta', aoMudar)
  }, [])

  if (!estado.ativo) return null
  return (
    <div className="ampulheta-overlay" role="status" aria-live="polite" aria-busy="true">
      <div className="ampulheta-caixa">
        <svg className="ampulheta-svg" viewBox="0 0 48 60" width="56" height="70"
             aria-hidden="true">
          {/* tampas e hastes */}
          <path d="M8 3 h32 M8 57 h32" stroke="currentColor" strokeWidth="3"
                strokeLinecap="round" />
          {/* corpo de vidro */}
          <path d="M12 5 h24 v6 c0 8 -12 10 -12 14 c0 4 12 6 12 14 v6 h-24 v-6
                   c0 -8 12 -10 12 -14 c0 -4 -12 -6 -12 -14 z"
                fill="none" stroke="currentColor" strokeWidth="2.4"
                strokeLinejoin="round" />
          {/* areia de cima (some) */}
          <path className="areia-cima"
                d="M15 7 h18 v3.5 c0 5 -9 8 -9 11.5 c0 -3.5 -9 -6.5 -9 -11.5 z"
                fill="currentColor" />
          {/* areia de baixo (cresce) */}
          <path className="areia-baixo"
                d="M15 53 h18 v-3.5 c0 -5 -9 -8 -9 -11.5 c0 3.5 -9 6.5 -9 11.5 z"
                fill="currentColor" />
          {/* filete caindo */}
          <line className="areia-filete" x1="24" y1="27" x2="24" y2="34"
                stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
        </svg>
        {estado.texto && <div className="ampulheta-texto">{estado.texto}</div>}
      </div>
    </div>
  )
}
