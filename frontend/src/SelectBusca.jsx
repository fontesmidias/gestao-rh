import { useEffect, useMemo, useRef, useState } from 'react'

// Select com busca: começa a digitar e a lista filtra (padrão de mercado).
// Substitui os <select> grandes onde rolar 300+ opções é sofrível. Dados
// carregados uma vez pelo pai e filtrados EM MEMÓRIA (sem GET a cada tecla).
//
// props:
//   opcoes: [{ valor, rotulo, extra? }]  — extra é um texto auxiliar (cargo, etc.)
//   valor: valor selecionado (ou '')
//   aoEscolher(valor)
//   placeholder, vazioRotulo (rótulo da opção "— nenhum —"; se omitido, sem opção vazia)
export default function SelectBusca({ opcoes, valor, aoEscolher, placeholder = 'Buscar…',
                                      vazioRotulo, style }) {
  const [aberto, setAberto] = useState(false)
  const [busca, setBusca] = useState('')
  const [foco, setFoco] = useState(0)
  const ref = useRef(null)

  const selecionado = opcoes.find((o) => o.valor === valor)

  // fecha ao clicar fora
  useEffect(() => {
    const fora = (e) => { if (ref.current && !ref.current.contains(e.target)) setAberto(false) }
    document.addEventListener('mousedown', fora)
    return () => document.removeEventListener('mousedown', fora)
  }, [])

  const filtradas = useMemo(() => {
    const q = busca.trim().toLowerCase()
    const base = q ? opcoes.filter((o) =>
      o.rotulo.toLowerCase().includes(q) || (o.extra || '').toLowerCase().includes(q)) : opcoes
    return base.slice(0, 50)  // teto de render; a busca refina o resto
  }, [busca, opcoes])

  const escolher = (v) => { aoEscolher(v); setAberto(false); setBusca('') }

  const aoTeclar = (e) => {
    if (e.key === 'ArrowDown') { e.preventDefault(); setFoco((f) => Math.min(f + 1, filtradas.length - 1)) }
    else if (e.key === 'ArrowUp') { e.preventDefault(); setFoco((f) => Math.max(f - 1, 0)) }
    else if (e.key === 'Enter' && aberto) { e.preventDefault(); const o = filtradas[foco]; if (o) escolher(o.valor) }
    else if (e.key === 'Escape') setAberto(false)
  }

  return (
    <div className="select-busca" ref={ref} style={style}>
      <button type="button" className="select-busca-campo" onClick={() => { setAberto(!aberto); setFoco(0) }}>
        <span className={selecionado ? '' : 'select-busca-placeholder'}>
          {selecionado ? selecionado.rotulo : (vazioRotulo || placeholder)}</span>
        <span className="select-busca-seta">▾</span>
      </button>
      {aberto && (
        <div className="select-busca-painel">
          <input className="select-busca-input" autoFocus value={busca} placeholder={placeholder}
                 onChange={(e) => { setBusca(e.target.value); setFoco(0) }} onKeyDown={aoTeclar} />
          <ul className="select-busca-lista">
            {vazioRotulo && (
              <li className={`select-busca-item ${!valor ? 'ativo' : ''}`}
                  onMouseDown={() => escolher('')}>{vazioRotulo}</li>
            )}
            {filtradas.map((o, i) => (
              <li key={o.valor} className={`select-busca-item ${i === foco ? 'foco' : ''} ${o.valor === valor ? 'ativo' : ''}`}
                  onMouseEnter={() => setFoco(i)} onMouseDown={() => escolher(o.valor)}>
                {o.rotulo}{o.extra && <small className="select-busca-extra"> · {o.extra}</small>}
              </li>
            ))}
            {filtradas.length === 0 && <li className="select-busca-vazio">Nada encontrado</li>}
          </ul>
        </div>
      )}
    </div>
  )
}
