import { useCallback, useEffect, useRef, useState } from 'react'

// Editor leve de imagem (sem bibliotecas externas — o público de baixa
// conectividade não deve baixar um cropper de centenas de kB). Faz o que o
// feedback de campo pediu: girar a foto que saiu deitada e recortar a sobra,
// sempre com uma margem de segurança para nunca cortar a borda do documento.
//
// props:
//   file        — File/Blob da imagem a editar
//   cropInicial — retângulo {x, y, w, h} em px da imagem, opcional (a moldura
//                 da câmera já entra com ~18% de folga); ausente = imagem toda
//   aoConcluir(file) — devolve a imagem editada como File JPEG
//   aoVoltar()       — cancela e volta (sem alterar nada)

const MARGEM = 0.18 // 18% de folga além das bordas identificadas

function clamp(v, min, max) { return Math.min(max, Math.max(min, v)) }

export default function EditorImagem({ file, cropInicial, aoConcluir, aoVoltar }) {
  const palcoRef = useRef(null)
  const imgRef = useRef(null)          // Image original já decodificada
  const [pronta, setPronta] = useState(false)
  const [angulo, setAngulo] = useState(0)      // 0 | 90 | 180 | 270
  const [dims, setDims] = useState({ w: 0, h: 0 })   // dims da imagem no ângulo atual
  const [fit, setFit] = useState({ escala: 1, largura: 0, altura: 0 })
  const [crop, setCrop] = useState(null)       // {x, y, w, h} em px da imagem girada
  const arraste = useRef(null)

  // Carrega a imagem uma vez.
  useEffect(() => {
    const url = URL.createObjectURL(file)
    const img = new Image()
    img.onload = () => { imgRef.current = img; setPronta(true) }
    img.src = url
    return () => URL.revokeObjectURL(url)
  }, [file])

  // Dimensões da imagem no ângulo atual (90/270 trocam largura e altura).
  useEffect(() => {
    if (!pronta) return
    const img = imgRef.current
    const girado = angulo === 90 || angulo === 270
    const w = girado ? img.naturalHeight : img.naturalWidth
    const h = girado ? img.naturalWidth : img.naturalHeight
    setDims({ w, h })
    // Ao girar, o crop volta ao enquadramento inicial (ou à imagem toda).
    if (angulo === 0 && cropInicial) {
      const m = { x: cropInicial.x, y: cropInicial.y, w: cropInicial.w, h: cropInicial.h }
      setCrop({
        x: clamp(m.x, 0, w), y: clamp(m.y, 0, h),
        w: clamp(m.w, 10, w - clamp(m.x, 0, w)),
        h: clamp(m.h, 10, h - clamp(m.y, 0, h)),
      })
    } else {
      setCrop({ x: w * 0.02, y: h * 0.02, w: w * 0.96, h: h * 0.96 })
    }
  }, [pronta, angulo, cropInicial])

  // Desenha a imagem girada e ajustada ao palco (cabe na largura e numa altura
  // máxima de ~60% da tela, para as ações do editor ficarem sempre visíveis).
  const redesenhar = useCallback(() => {
    const palco = palcoRef.current
    if (!palco || !pronta || !dims.w) return
    const cvs = palco.querySelector('canvas.editor-base')
    const dispoW = palco.parentElement?.clientWidth || palco.clientWidth || 320
    const maxH = (typeof window !== 'undefined' ? window.innerHeight : 640) * 0.6
    const escala = Math.min(dispoW / dims.w, maxH / dims.h)
    const dispW = dims.w * escala
    const dispH = dims.h * escala
    setFit({ escala, largura: dispW, altura: dispH })
    cvs.width = dims.w
    cvs.height = dims.h
    cvs.style.width = `${dispW}px`
    cvs.style.height = `${dispH}px`
    const ctx = cvs.getContext('2d')
    ctx.save()
    ctx.clearRect(0, 0, dims.w, dims.h)
    // Rotaciona em torno do centro.
    ctx.translate(dims.w / 2, dims.h / 2)
    ctx.rotate((angulo * Math.PI) / 180)
    const img = imgRef.current
    ctx.drawImage(img, -img.naturalWidth / 2, -img.naturalHeight / 2)
    ctx.restore()
  }, [pronta, dims, angulo])

  useEffect(() => { redesenhar() }, [redesenhar])
  useEffect(() => {
    window.addEventListener('resize', redesenhar)
    return () => window.removeEventListener('resize', redesenhar)
  }, [redesenhar])

  // --- Arraste do recorte (corpo e cantos), mouse e toque via pointer ---
  const iniciar = (tipo) => (e) => {
    e.preventDefault(); e.stopPropagation()
    const p = e.touches ? e.touches[0] : e
    arraste.current = { tipo, x0: p.clientX, y0: p.clientY, crop: { ...crop } }
  }

  useEffect(() => {
    const mover = (e) => {
      if (!arraste.current || !crop) return
      const p = e.touches ? e.touches[0] : e
      const { tipo, x0, y0, crop: c0 } = arraste.current
      const dx = (p.clientX - x0) / fit.escala
      const dy = (p.clientY - y0) / fit.escala
      let { x, y, w, h } = c0
      if (tipo === 'corpo') {
        x = clamp(c0.x + dx, 0, dims.w - c0.w)
        y = clamp(c0.y + dy, 0, dims.h - c0.h)
      } else {
        // Cantos: nw, ne, sw, se
        if (tipo.includes('w')) { x = clamp(c0.x + dx, 0, c0.x + c0.w - 20); w = c0.w - (x - c0.x) }
        if (tipo.includes('n')) { y = clamp(c0.y + dy, 0, c0.y + c0.h - 20); h = c0.h - (y - c0.y) }
        if (tipo.includes('e')) { w = clamp(c0.w + dx, 20, dims.w - c0.x) }
        if (tipo.includes('s')) { h = clamp(c0.h + dy, 20, dims.h - c0.y) }
      }
      setCrop({ x, y, w, h })
    }
    const soltar = () => { arraste.current = null }
    window.addEventListener('mousemove', mover)
    window.addEventListener('touchmove', mover, { passive: false })
    window.addEventListener('mouseup', soltar)
    window.addEventListener('touchend', soltar)
    return () => {
      window.removeEventListener('mousemove', mover)
      window.removeEventListener('touchmove', mover)
      window.removeEventListener('mouseup', soltar)
      window.removeEventListener('touchend', soltar)
    }
  }, [crop, fit.escala, dims])

  const girar = (sentido) => setAngulo((a) => (a + sentido + 360) % 360)

  const aplicar = () => {
    const c = crop || { x: 0, y: 0, w: dims.w, h: dims.h }
    const out = document.createElement('canvas')
    out.width = Math.max(1, Math.round(c.w))
    out.height = Math.max(1, Math.round(c.h))
    const ctx = out.getContext('2d')
    // Redesenha a imagem girada num canvas em tamanho cheio e recorta dele.
    const cheio = document.createElement('canvas')
    cheio.width = dims.w; cheio.height = dims.h
    const cc = cheio.getContext('2d')
    cc.translate(dims.w / 2, dims.h / 2)
    cc.rotate((angulo * Math.PI) / 180)
    const img = imgRef.current
    cc.drawImage(img, -img.naturalWidth / 2, -img.naturalHeight / 2)
    ctx.drawImage(cheio, c.x, c.y, c.w, c.h, 0, 0, c.w, c.h)
    out.toBlob((blob) => {
      if (!blob) return aoVoltar()
      aoConcluir(new File([blob], file.name || 'documento.jpg', { type: 'image/jpeg' }))
    }, 'image/jpeg', 0.92)
  }

  const box = crop && {
    left: crop.x * fit.escala, top: crop.y * fit.escala,
    width: crop.w * fit.escala, height: crop.h * fit.escala,
  }

  return (
    <div className="editor-imagem">
      <p className="editor-ajuda">✂️ Ajuste o recorte arrastando os cantos e gire se a foto
        estiver deitada. Deixamos uma folga de segurança para não cortar o documento.</p>
      <div className="editor-palco" ref={palcoRef}
           style={{ height: fit.altura ? `${fit.altura}px` : undefined }}>
        <canvas className="editor-base" />
        {box && (
          <div className="editor-crop" style={box} onMouseDown={iniciar('corpo')}
               onTouchStart={iniciar('corpo')}>
            {['nw', 'ne', 'sw', 'se'].map((c) => (
              <span key={c} className={`editor-canto ${c}`}
                    onMouseDown={iniciar(c)} onTouchStart={iniciar(c)} />
            ))}
          </div>
        )}
      </div>
      <div className="editor-barra">
        <button type="button" className="btn-secundario" onClick={() => girar(-90)}>↺ Girar</button>
        <button type="button" className="btn-secundario" onClick={() => girar(90)}>↻ Girar</button>
      </div>
      <div className="captura-acoes">
        <button type="button" className="btn-principal captura-disparo" onClick={aplicar}
                disabled={!pronta}>✔ Usar esta imagem</button>
        <button type="button" className="btn-secundario" onClick={aoVoltar}>‹ Voltar</button>
      </div>
    </div>
  )
}

// Retângulo da moldura em coordenadas nativas do vídeo, com margem de segurança
// de 18% além das bordas — usado como recorte inicial da foto (a pessoa já
// alinhou o documento à moldura, então esse é o enquadramento pretendido).
export function cropDaMoldura(video, palcoEl, molduraEl) {
  if (!video?.videoWidth || !palcoEl || !molduraEl) return null
  const palco = palcoEl.getBoundingClientRect()
  const mold = molduraEl.getBoundingClientRect()
  const escala = Math.max(palco.width / video.videoWidth, palco.height / video.videoHeight)
  const offX = (video.videoWidth * escala - palco.width) / 2
  const offY = (video.videoHeight * escala - palco.height) / 2
  const paraVideo = (xt, yt) => [
    (xt - palco.left + offX) / escala,
    (yt - palco.top + offY) / escala,
  ]
  const [x0, y0] = paraVideo(mold.left, mold.top)
  const [x1, y1] = paraVideo(mold.right, mold.bottom)
  const mx = (x1 - x0) * MARGEM
  const my = (y1 - y0) * MARGEM
  const x = clamp(x0 - mx, 0, video.videoWidth)
  const y = clamp(y0 - my, 0, video.videoHeight)
  return {
    x, y,
    w: clamp(x1 + mx, 0, video.videoWidth) - x,
    h: clamp(y1 + my, 0, video.videoHeight) - y,
  }
}
