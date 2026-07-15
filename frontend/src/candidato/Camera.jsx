import { useCallback, useEffect, useRef, useState } from 'react'

// Câmera guiada: moldura no formato do documento + dicas em tempo real de
// luz e foco. Filosofia: a câmera é um ATALHO — o botão de enviar um arquivo
// que a pessoa já tem no aparelho está sempre visível, e qualquer falha da
// câmera (sem permissão, sem câmera, navegador antigo, http) cai de pé nele.

const FORMATOS = {
  // razao = largura/altura da moldura; dica = como posicionar.
  cartao:  { razao: 85.6 / 54, dica: 'Encaixe o documento deitado dentro da moldura' },
  rg_aberto: { razao: 96 / 130, dica: 'RG aberto, em pé, dentro da moldura (frente e verso juntos)' },
  a4:      { razao: 210 / 297, dica: 'Encaixe a folha em pé dentro da moldura' },
  retrato: { razao: 3 / 4,     dica: 'Centralize o rosto na moldura, fundo claro' },
}

// Limiares calibrados para o canvas de análise de 120px (valores empíricos:
// nitidez usa a mesma ideia do backend — variância do Laplaciano).
const LUZ_MIN = 60      // abaixo: ambiente escuro
const LUZ_MAX = 232     // acima: estourado / reflexo forte
const FOCO_MIN = 25     // abaixo: imagem borrada / câmera procurando foco
const QUADROS_BONS_PARA_OK = 3   // ~1s estável antes de liberar o disparo

function analisarFrame(video, canvas) {
  const w = 120
  const h = Math.max(1, Math.round((w * video.videoHeight) / (video.videoWidth || 1))) || 90
  canvas.width = w
  canvas.height = h
  const ctx = canvas.getContext('2d', { willReadFrequently: true })
  ctx.drawImage(video, 0, 0, w, h)
  const { data } = ctx.getImageData(0, 0, w, h)
  const cinza = new Float32Array(w * h)
  let soma = 0
  for (let i = 0; i < w * h; i++) {
    const g = 0.299 * data[i * 4] + 0.587 * data[i * 4 + 1] + 0.114 * data[i * 4 + 2]
    cinza[i] = g
    soma += g
  }
  const luz = soma / (w * h)
  let s1 = 0
  let s2 = 0
  let n = 0
  for (let y = 1; y < h - 1; y++) {
    for (let x = 1; x < w - 1; x++) {
      const i = y * w + x
      const v = 4 * cinza[i] - cinza[i - 1] - cinza[i + 1] - cinza[i - w] - cinza[i + w]
      s1 += v
      s2 += v * v
      n++
    }
  }
  const media = s1 / n
  const foco = s2 / n - media * media
  return { luz, foco }
}

function dicaDoMomento({ luz, foco }) {
  if (luz < LUZ_MIN) return { ok: false, icone: '🌑', texto: 'Está escuro — procure um lugar mais iluminado.' }
  if (luz > LUZ_MAX) return { ok: false, icone: '✨', texto: 'Luz demais ou reflexo — incline um pouco o documento.' }
  if (foco < FOCO_MIN) return { ok: false, icone: '🌫️', texto: 'Imagem tremida — apoie o celular e aguarde o foco.' }
  return { ok: true, icone: '✅', texto: 'Ótimo! Pode fotografar.' }
}

export default function CapturaDocumento({ formato = 'cartao', titulo, aoCapturar, aoArquivo, aoFechar }) {
  const videoRef = useRef(null)
  const analiseRef = useRef(null)
  const streamRef = useRef(null)
  const bonsRef = useRef(0)
  const inputRef = useRef(null)
  const [estado, setEstado] = useState('abrindo')  // abrindo | ativa | sem-camera
  const [motivoSemCamera, setMotivoSemCamera] = useState(null)
  const [dica, setDica] = useState(null)
  const [pronto, setPronto] = useState(false)
  const [teimoso, setTeimoso] = useState(false)    // libera "fotografar assim mesmo"
  const f = FORMATOS[formato] || FORMATOS.cartao

  const fecharStream = useCallback(() => {
    streamRef.current?.getTracks().forEach((t) => t.stop())
    streamRef.current = null
  }, [])

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

  // Análise ~3x por segundo enquanto a câmera está ativa.
  useEffect(() => {
    if (estado !== 'ativa') return undefined
    const t = setInterval(() => {
      const v = videoRef.current
      if (!v || v.readyState < 2 || !v.videoWidth) return
      try {
        const medidas = analisarFrame(v, analiseRef.current)
        const d = dicaDoMomento(medidas)
        setDica(d)
        bonsRef.current = d.ok ? bonsRef.current + 1 : 0
        setPronto(bonsRef.current >= QUADROS_BONS_PARA_OK)
      } catch {
        // Frame indisponível (troca de aba, câmera fechando): tenta no próximo.
      }
    }, 350)
    // Depois de 6s sem quadro perfeito, deixa fotografar mesmo assim: câmera
    // fraca não pode ser beco sem saída — o servidor ainda confere a nitidez.
    const escape = setTimeout(() => setTeimoso(true), 6000)
    return () => { clearInterval(t); clearTimeout(escape) }
  }, [estado])

  const fotografar = () => {
    const v = videoRef.current
    if (!v || !v.videoWidth) return
    const c = document.createElement('canvas')
    c.width = v.videoWidth
    c.height = v.videoHeight
    c.getContext('2d').drawImage(v, 0, 0)
    c.toBlob((blob) => {
      if (!blob) return
      fecharStream()
      aoCapturar(new File([blob], 'documento.jpg', { type: 'image/jpeg' }))
    }, 'image/jpeg', 0.92)
  }

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
        <div className="captura-palco">
          <video ref={videoRef} playsInline muted autoPlay className="captura-video" />
          <canvas ref={analiseRef} hidden />
          <div className="captura-moldura" style={molduraStyle} data-ok={pronto || undefined}>
            <i /><i /><i /><i />
          </div>
          <div className={`captura-dica ${dica?.ok ? 'ok' : ''}`} aria-live="polite">
            {estado === 'abrindo' ? '📷 Abrindo a câmera…'
              : dica ? `${dica.icone} ${dica.texto}` : `📐 ${f.dica}`}
          </div>
        </div>
      ) : (
        <div className="captura-palco captura-sem-camera">
          <p>📁 {motivoSemCamera}</p>
        </div>
      )}

      <div className="captura-acoes">
        {estado === 'ativa' && (
          <button type="button" className="btn-principal captura-disparo"
                  disabled={!pronto && !teimoso} onClick={fotografar}>
            {pronto ? '📸 Fotografar' : teimoso ? '📸 Fotografar assim mesmo' : '⏳ Ajustando…'}
          </button>
        )}
        <button type="button" className="btn-secundario"
                onClick={() => inputRef.current.click()}>
          📁 Já tenho o arquivo — enviar do aparelho
        </button>
      </div>
      {estado === 'ativa' && <p className="captura-legenda">{f.dica}</p>}
    </div>
  )
}
