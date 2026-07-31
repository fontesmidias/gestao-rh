import { useEffect, useState } from 'react'
import PdfViewer from './PdfViewer.jsx'

// Visualizador de DOCUMENTO na tela — o padrão pedido pelo Bruno em
// 2026-07-30: "todo documento que a gente tentar abrir ali em PDF, enfim, seja
// currículo ou seja a certidão de nascimento para análise de auxílio creche,
// que esse documento ele renderize ali na tela, para a gente não precisar ficar
// baixando".
//
// Antes só a tela de admissão renderizava (`PdfViewer` em `Detalhe.jsx`); todo
// o resto do painel fazia `window.open` numa aba nova — que no caso do Word
// abria uma aba EM BRANCO, porque navegador nenhum renderiza .docx.
//
// Três casos, nesta ordem:
//   PDF     -> PdfViewer (iframe no desktop, pdf.js no celular)
//   imagem  -> <img>, sem passar por PDF (mais leve e mais fiel)
//   Word    -> o backend converte para PDF (LibreOffice, que já roda no
//              container) e cai no primeiro caso. Decisão do Bruno: converter,
//              não mandar baixar.
//
// O download continua disponível SEMPRE: renderizar é o padrão, não uma prisão.
export default function VisualizadorArquivo({ blob, nome, aoFechar }) {
  const [url, setUrl] = useState(null)

  useEffect(() => {
    if (!blob) { setUrl(null); return }
    const u = URL.createObjectURL(blob)
    setUrl(u)
    // Revoga ao trocar de arquivo ou desmontar: object URL não revogado é
    // vazamento de memória com o arquivo inteiro dentro (o `Detalhe.jsx` tinha
    // esse defeito e nunca revogava).
    return () => URL.revokeObjectURL(u)
  }, [blob])

  if (!blob || !url) return null

  const tipo = blob.type || ''
  const ehImagem = tipo.startsWith('image/')
  // HEIC é imagem, mas navegador nenhum decodifica: sem isto a tela mostraria
  // um ícone quebrado, que parece defeito do sistema.
  const heic = /heic|heif/i.test(tipo) || /\.heic$|\.heif$/i.test(nome || '')

  return (
    // `na-linha`: este visualizador vive DENTRO do painel da linha, então não
    // pode reservar os 75vh que a coluna da tela de admissão usa — empurraria
    // o resto da ficha para fora da tela.
    <div className="rh-visualizador na-linha">
      <div className="rh-topo">
        <strong>{nome || 'Documento'}</strong>
        <span>
          <a className="btn-secundario btn-mini" href={url} download={nome || 'documento'}>
            ⬇ Baixar</a>
          {aoFechar && (
            <button className="btn-secundario btn-mini" onClick={aoFechar}>✕ Fechar</button>)}
        </span>
      </div>

      {heic ? (
        <p className="explica centro">Este arquivo é HEIC (foto de iPhone) e o navegador não
          consegue exibi-lo. Use o botão acima para baixar.</p>
      ) : ehImagem ? (
        <img src={url} alt={nome || 'documento'} className="visualizador-imagem" />
      ) : (
        <PdfViewer blob={blob} url={url} />
      )}
    </div>
  )
}
