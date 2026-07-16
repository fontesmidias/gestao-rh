import { useEffect, useRef, useState } from 'react'
import { FRASES } from './Espera.jsx'

// Feedback global do painel do RH: barra fininha animada no topo enquanto
// houver requisição em andamento (padrão GitHub/YouTube) e, se a operação
// passar de ~2s, uma frase de espera elegante no canto — as mesmas do
// candidato, que o RH nunca via.
export default function BarraAtividade() {
  const [ocupada, setOcupada] = useState(false)
  const [frase, setFrase] = useState(null)
  const timerRef = useRef(null)

  useEffect(() => {
    const aoMudar = (e) => {
      const ativa = e.detail > 0
      setOcupada(ativa)
      clearTimeout(timerRef.current)
      if (ativa) {
        timerRef.current = setTimeout(() =>
          setFrase(FRASES[Math.floor(Math.random() * FRASES.length)]), 2000)
      } else {
        setFrase(null)
      }
    }
    window.addEventListener('rh-ocupado', aoMudar)
    return () => {
      window.removeEventListener('rh-ocupado', aoMudar)
      clearTimeout(timerRef.current)
    }
  }, [])

  return (
    <>
      {ocupada && <div className="barra-atividade" role="progressbar"
                       aria-label="Processando…"><i /></div>}
      {ocupada && frase && (
        <div className="toast-espera" role="status">⏳ {frase}</div>
      )}
    </>
  )
}
