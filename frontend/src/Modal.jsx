import { useEffect, useRef } from 'react'

// Primeiro modal do projeto (feedback 2026-07-27: anotações do CRM "aparecer
// um popup para lançar ou editar e para ver"). O sistema de design dizia
// "editar/criar abre PERTO do item, nunca no topo" e era só inline — o
// princípio continua valendo (ver docs/planejamento/08-sistema-de-design.md):
// modal ANCORADO (não formulário solto no topo da página) é a segunda forma
// permitida, usada quando o conteúdo tem anexo + histórico + texto longo, que
// não cabe espremido numa linha de tabela.
//
// Reaproveita o padrão de fechar já usado no SelectBusca.jsx: clique fora e
// Escape. Foco preso dentro do modal (acessibilidade) e título obrigatório
// (aria-label) — vira padrão da casa, nasce acessível.
//
// props:
//   titulo: string (obrigatório) — some no cabeçalho e no aria-label
//   aoFechar: () => void
//   children
export default function Modal({ titulo, aoFechar, children }) {
  const ref = useRef(null)

  useEffect(() => {
    const aoTeclar = (e) => { if (e.key === 'Escape') aoFechar() }
    document.addEventListener('keydown', aoTeclar)
    // foco preso: o primeiro elemento focável do modal recebe foco ao abrir
    const focavel = ref.current?.querySelector(
      'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])')
    focavel?.focus()
    return () => document.removeEventListener('keydown', aoTeclar)
  }, [aoFechar])

  return (
    <div className="modal-fundo" onMouseDown={(e) => { if (e.target === e.currentTarget) aoFechar() }}>
      <div className="modal-caixa" role="dialog" aria-modal="true" aria-label={titulo} ref={ref}>
        <div className="modal-cabecalho">
          <strong>{titulo}</strong>
          <button type="button" className="btn-link" onClick={aoFechar} aria-label="Fechar">✕</button>
        </div>
        <div className="modal-corpo">{children}</div>
      </div>
    </div>
  )
}
