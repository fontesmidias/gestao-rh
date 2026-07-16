import { useCallback, useEffect, useRef, useState } from 'react'

// Câmera guiada: moldura no formato do documento + dicas em tempo real de
// enquadramento, luz e foco — tudo medido DENTRO da moldura, não na cena
// inteira (senão "tudo certo" continuaria aparecendo com o documento fora do
// quadro). O DISPARO É SEMPRE DA PESSOA (feedback de campo, 2026-07-15: o
// auto-disparo pegava o documento ainda sendo ajeitado) — o botão habilita
// quando o quadro está bom. Depois do clique, a foto aparece congelada para
// conferir: "usar esta foto" ou "tirar outra".
// Filosofia: a câmera é um ATALHO — o botão de enviar um arquivo que a pessoa
// já tem no aparelho está sempre visível, e qualquer falha da câmera
// (sem permissão, sem câmera, navegador antigo, http) cai de pé nele.

const FORMATOS = {
  // razao = largura/altura da moldura; dica = como posicionar.
  cartao:    { razao: 85.6 / 54, dica: 'Encaixe o documento deitado dentro da moldura' },
  a4:        { razao: 210 / 297, dica: 'Encaixe a folha em pé dentro da moldura' },
  cabecalho: { razao: 2.1,       dica: 'Enquadre o CABEÇALHO da conta — a parte de cima, onde aparecem o nome e o endereço' },
  retrato:   { razao: 3 / 4,     dica: 'Centralize o rosto na moldura, fundo claro' },
}

// Limiares calibrados para o canvas de análise de 160px. Nitidez usa a mesma
// ideia do backend (variância do Laplaciano), medida só dentro da moldura.
const LUZ_MIN = 60        // média abaixo: ambiente escuro
const LUZ_MAX = 232       // média acima: estourado / reflexo forte
const FOCO_MIN = 25       // variância do Laplaciano abaixo: borrado
const ESTRUTURA_MIN = 18  // desvio-padrão mínimo dentro da moldura (documento tem texto)
const CONTRASTE_MIN = 9   // diferença mínima dentro/fora (documento destacado do fundo)
const QUADROS_PRONTO = 2      // quadros bons consecutivos (~350ms cada) para liberar o disparo

function medirFrame(video, canvas, palcoEl, molduraEl) {
  const w = 160
  const h = Math.max(1, Math.round((w * video.videoHeight) / (video.videoWidth || 1)))
  canvas.width = w
  canvas.height = h
  const ctx = canvas.getContext('2d', { willReadFrequently: true })
  ctx.drawImage(video, 0, 0, w, h)
  const { data } = ctx.getImageData(0, 0, w, h)
  const cinza = new Float32Array(w * h)
  for (let i = 0; i < w * h; i++) {
    cinza[i] = 0.299 * data[i * 4] + 0.587 * data[i * 4 + 1] + 0.114 * data[i * 4 + 2]
  }

  // Mapeia a moldura (px de tela) para o frame: o vídeo usa object-fit: cover,
  // então há escala + corte centralizado a compensar.
  const palco = palcoEl.getBoundingClientRect()
  const mold = molduraEl.getBoundingClientRect()
  const escala = Math.max(palco.width / video.videoWidth, palco.height / video.videoHeight)
  const offX = (video.videoWidth * escala - palco.width) / 2
  const offY = (video.videoHeight * escala - palco.height) / 2
  const k = w / video.videoWidth
  const paraFrame = (xTela, yTela) => [
    Math.round(((xTela - palco.left + offX) / escala) * k),
    Math.round(((yTela - palco.top + offY) / escala) * k),
  ]
  let [x0, y0] = paraFrame(mold.left, mold.top)
  let [x1, y1] = paraFrame(mold.right, mold.bottom)
  x0 = Math.max(1, x0); y0 = Math.max(1, y0)
  x1 = Math.min(w - 2, x1); y1 = Math.min(h - 2, y1)
  if (x1 - x0 < 8 || y1 - y0 < 8) return null   // moldura ainda sem medida útil

  // Estatísticas dentro e fora da moldura + foco (Laplaciano) dentro.
  let sD = 0, s2D = 0, nD = 0, sF = 0, s2F = 0, nF = 0, lap = 0, lap2 = 0, nL = 0
  for (let y = 1; y < h - 1; y++) {
    for (let x = 1; x < w - 1; x++) {
      const i = y * w + x
      const g = cinza[i]
      if (x >= x0 && x <= x1 && y >= y0 && y <= y1) {
        sD += g; s2D += g * g; nD++
        const v = 4 * g - cinza[i - 1] - cinza[i + 1] - cinza[i - w] - cinza[i + w]
        lap += v; lap2 += v * v; nL++
      } else {
        sF += g; s2F += g * g; nF++
      }
    }
  }
  const mD = sD / nD
  const mF = nF ? sF / nF : mD
  const stdD = Math.sqrt(Math.max(0, s2D / nD - mD * mD))
  const stdF = nF ? Math.sqrt(Math.max(0, s2F / nF - mF * mF)) : 0
  const mLap = lap / nL
  return {
    luz: mD,
    foco: lap2 / nL - mLap * mLap,
    estrutura: stdD,
    contraste: Math.abs(mD - mF),
    stdFora: stdF,
  }
}

function dicaDoMomento(m) {
  if (m.luz < LUZ_MIN) return { ok: false, icone: '🌑', texto: 'Está escuro — procure um lugar mais iluminado.' }
  if (m.luz > LUZ_MAX) return { ok: false, icone: '✨', texto: 'Luz demais ou reflexo — incline um pouco o documento.' }
  // Documento presente na moldura: precisa ter estrutura (texto) e se
  // destacar do que está fora — na dúvida, pede o enquadramento.
  if (m.estrutura < ESTRUTURA_MIN || (m.contraste < CONTRASTE_MIN && m.estrutura < m.stdFora + 6)) {
    return { ok: false, icone: '📐', texto: 'Encaixe o documento dentro da moldura.' }
  }
  if (m.foco < FOCO_MIN) return { ok: false, icone: '🌫️', texto: 'Imagem tremida — apoie o celular e aguarde o foco.' }
  return { ok: true, icone: '✅', texto: 'Ótimo! Toque em Fotografar.' }
}

export default function CapturaDocumento({ formato = 'cartao', titulo, aoCapturar, aoArquivo, aoFechar }) {
  const videoRef = useRef(null)
  const analiseRef = useRef(null)
  const palcoRef = useRef(null)
  const molduraRef = useRef(null)
  const streamRef = useRef(null)
  const bonsRef = useRef(0)
  const inputRef = useRef(null)
  const [estado, setEstado] = useState('abrindo')  // abrindo | ativa | sem-camera
  const [motivoSemCamera, setMotivoSemCamera] = useState(null)
  const [dica, setDica] = useState(null)
  const [pronto, setPronto] = useState(false)
  const [teimoso, setTeimoso] = useState(false)    // libera "fotografar assim mesmo"
  const [revisao, setRevisao] = useState(null)     // {url, file}: conferir antes de enviar
  const f = FORMATOS[formato] || FORMATOS.cartao

  const fecharStream = useCallback(() => {
    streamRef.current?.getTracks().forEach((t) => t.stop())
    streamRef.current = null
  }, [])

  // Congela o quadro para a pessoa CONFERIR — nada é enviado ainda.
  const fotografar = useCallback(() => {
    const v = videoRef.current
    if (!v || !v.videoWidth) return
    const c = document.createElement('canvas')
    c.width = v.videoWidth
    c.height = v.videoHeight
    c.getContext('2d').drawImage(v, 0, 0)
    c.toBlob((blob) => {
      if (!blob) return
      const file = new File([blob], 'documento.jpg', { type: 'image/jpeg' })
      setRevisao({ url: URL.createObjectURL(blob), file })
    }, 'image/jpeg', 0.92)
  }, [])

  const usarFoto = () => {
    if (!revisao) return
    URL.revokeObjectURL(revisao.url)
    fecharStream()
    aoCapturar(revisao.file)
  }

  const tirarOutra = () => {
    if (revisao) URL.revokeObjectURL(revisao.url)
    setRevisao(null)
    bonsRef.current = 0
    setPronto(false)
  }

  useEffect(() => {
    let vivo = true
    const abrir = async () => {
      if (!navigator.mediaDevices?.getUserMedia) {
        setMotivoSemCamera('Seu navegador não abre a câmera por aqui — sem problema, envie um arquivo.')
        setEstado('sem-camera')
        return
      }
      try {
        // Traseira no celular; no desktop cai na câmera que houver.
        const stream = await navigator.mediaDevices.getUserMedia({
          video: { facingMode: 'environment', width: { ideal: 1920 }, height: { ideal: 1080 } },
          audio: false,
        })
        if (!vivo) { stream.getTracks().forEach((t) => t.stop()); return }
        streamRef.current = stream
        const v = videoRef.current
        v.srcObject = stream
        await v.play().catch(() => {})   // iOS às vezes exige o playsinline já no elemento
        setEstado('ativa')
      } catch (e) {
        if (!vivo) return
        setMotivoSemCamera(
          e?.name === 'NotAllowedError'
            ? 'A câmera está sem permissão. Você pode liberar nas configurações do navegador — ou simplesmente enviar um arquivo.'
            : 'Não encontramos uma câmera disponível. Envie um arquivo do aparelho.'
        )
        setEstado('sem-camera')
      }
    }
    abrir()
    return () => { vivo = false; fecharStream() }
  }, [fecharStream])

  // Análise ~3x por segundo enquanto a câmera está ativa (pausa na revisão).
  useEffect(() => {
    if (estado !== 'ativa' || revisao) return undefined
    const t = setInterval(() => {
      const v = videoRef.current
      if (!v || v.readyState < 2 || !v.videoWidth || !molduraRef.current) return
      try {
        const m = medirFrame(v, analiseRef.current, palcoRef.current, molduraRef.current)
        if (!m) return
        const d = dicaDoMomento(m)
        setDica(d)
        bonsRef.current = d.ok ? bonsRef.current + 1 : 0
        setPronto(bonsRef.current >= QUADROS_PRONTO)
      } catch {
        // Frame indisponível (troca de aba, câmera fechando): tenta no próximo.
      }
    }, 350)
    // Depois de 8s sem quadro perfeito, deixa fotografar mesmo assim: câmera
    // fraca não pode ser beco sem saída — o servidor ainda confere a nitidez.
    const escape = setTimeout(() => setTeimoso(true), 8000)
    return () => { clearInterval(t); clearTimeout(escape) }
  }, [estado, revisao])

  const escolherArquivo = (e) => {
    const arq = e.target.files[0]
    e.target.value = ''
    if (!arq) return
    fecharStream()
    aoArquivo(arq)
  }

  // Moldura: caixa central na proporção do documento; o resto escurece.
  const paisagem = f.razao >= 1
  const molduraStyle = paisagem
    ? { width: 'min(86vw, 480px)', aspectRatio: String(f.razao) }
    : { height: 'min(58vh, 480px)', aspectRatio: String(f.razao) }

  return (
    <div className="captura-overlay" role="dialog" aria-label={titulo || 'Fotografar documento'}>
      <input ref={inputRef} type="file" hidden accept="image/*,.pdf,.doc,.docx"
             onChange={escolherArquivo} />
      <div className="captura-topo">
        <strong>{titulo || 'Fotografar documento'}</strong>
        <button type="button" className="btn-link captura-fechar"
                onClick={() => { fecharStream(); aoFechar() }}>✕ Fechar</button>
      </div>

      {estado !== 'sem-camera' ? (
        <div className="captura-palco" ref={palcoRef}>
          <video ref={videoRef} playsInline muted autoPlay className="captura-video" />
          <canvas ref={analiseRef} hidden />
          {revisao && <img src={revisao.url} alt="Foto capturada para conferência"
                           className="captura-revisao" />}
          {!revisao && (
            <div className="captura-moldura" ref={molduraRef} style={molduraStyle}
                 data-ok={pronto || undefined}>
              <i /><i /><i /><i />
            </div>
          )}
          <div className={`captura-dica ${(revisao || dica?.ok) ? 'ok' : ''}`} aria-live="polite">
            {revisao ? '🔍 Confira: dá para ler tudo? Sem cortes e sem reflexo?'
              : estado === 'abrindo' ? '📷 Abrindo a câmera…'
              : dica ? `${dica.icone} ${dica.texto}`
              : `📐 ${f.dica}`}
          </div>
        </div>
      ) : (
        <div className="captura-palco captura-sem-camera">
          <p>📁 {motivoSemCamera}</p>
        </div>
      )}

      <div className="captura-acoes">
        {estado === 'ativa' && revisao && (
          <>
            <button type="button" className="btn-principal captura-disparo" onClick={usarFoto}>
              ✔ Usar esta foto
            </button>
            <button type="button" className="btn-secundario" onClick={tirarOutra}>
              ↺ Tirar outra
            </button>
          </>
        )}
        {estado === 'ativa' && !revisao && (
          <button type="button" className="btn-principal captura-disparo"
                  disabled={!pronto && !teimoso} onClick={fotografar}>
            {pronto ? '📸 Fotografar' : teimoso ? '📸 Fotografar assim mesmo' : '⏳ Ajustando…'}
          </button>
        )}
        {!revisao && (
          <button type="button" className="btn-secundario"
                  onClick={() => inputRef.current.click()}>
            📁 Já tenho o arquivo — enviar do aparelho
          </button>
        )}
      </div>
      {estado === 'ativa' && !revisao && (
        <p className="captura-legenda">{f.dica}. Você dispara quando quiser — nada é enviado
          sem você conferir a foto antes.</p>
      )}
    </div>
  )
}
