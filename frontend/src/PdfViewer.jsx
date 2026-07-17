import { useEffect, useRef, useState } from 'react'

// Visualizador de PDF que se adapta ao aparelho:
//  - Desktop: <iframe> nativo (rápido, com a barra de ferramentas do navegador
//    — zoom, busca, impressão — que o RH usa no dia a dia).
//  - Celular: o Chrome do Android NÃO tem visualizador embutido e o <iframe>
//    com blob mostra só um fundo escuro com um botão "Abrir" morto (bug de
//    campo, 2026-07). Nesses aparelhos renderizamos com pdf.js em <canvas>.
// Import dinâmico: o pdf.js (~500 kB) só baixa no celular, quando é preciso —
// o desktop e o portal do candidato não pagam esse peso.
function ehCelular() {
  if (typeof window === 'undefined') return false
  const semVisualizador = window.matchMedia?.('(pointer: coarse)').matches
  const telaEstreita = window.matchMedia?.('(max-width: 820px)').matches
  return Boolean(semVisualizador || telaEstreita)
}

async function carregarPdfjs() {
  const pdfjs = await import('pdfjs-dist')
  pdfjs.GlobalWorkerOptions.workerSrc =
    new URL('pdfjs-dist/build/pdf.worker.min.mjs', import.meta.url).toString()
  return pdfjs
}

export default function PdfViewer({ blob, url }) {
  const areaRef = useRef(null)
  const [estado, setEstado] = useState('carregando') // carregando | ok | erro
  const [celular] = useState(ehCelular)

  useEffect(() => {
    if (!blob || !celular) return
    let cancelado = false
    const area = areaRef.current
    setEstado('carregando')
    ;(async () => {
      try {
        const pdfjs = await carregarPdfjs()
        const doc = await pdfjs.getDocument({ data: await blob.arrayBuffer() }).promise
        if (cancelado) return
        area.replaceChildren()
        // Nitidez em telas de alta densidade: canvas maior + CSS em 100%.
        const dpr = Math.min(window.devicePixelRatio || 1, 2)
        const largura = Math.max(area.clientWidth - 2, 280)
        for (let n = 1; n <= doc.numPages; n++) {
          const pagina = await doc.getPage(n)
          if (cancelado) return
          const base = pagina.getViewport({ scale: 1 })
          const escala = largura / base.width
          const vp = pagina.getViewport({ scale: escala * dpr })
          const canvas = document.createElement('canvas')
          canvas.width = vp.width
          canvas.height = vp.height
          canvas.style.width = '100%'
          canvas.className = 'pdf-pagina'
          area.appendChild(canvas)
          await pagina.render({ canvasContext: canvas.getContext('2d'), viewport: vp }).promise
        }
        if (!cancelado) setEstado('ok')
      } catch {
        if (!cancelado) setEstado('erro')
      }
    })()
    return () => { cancelado = true }
  }, [blob, celular])

  // Desktop: iframe nativo, exatamente como era antes desta mudança.
  if (!celular) {
    return <iframe title="documento" className="pdf-iframe" src={url} />
  }

  return (
    <div className="pdf-viewer">
      {estado === 'carregando' && <p className="explica centro">Abrindo o documento…</p>}
      {estado === 'erro' && (
        <p className="explica centro">Não conseguimos exibir este PDF aqui.
          Use o link para baixá-lo e abrir no aparelho.</p>
      )}
      <div ref={areaRef} />
    </div>
  )
}
