import { useEffect, useRef, useState } from 'react'
import { rh as api } from '../api.js'
import { fmtDataHora, fmtDuracao } from '../fmt.js'

// Gravação e transcrição da entrevista (v2.97).
//
// Desenho em `docs/planejamento/14-transcricao-de-entrevistas.md`. O que este
// componente carrega de decisão, e por quê:
//
// **O consentimento é uma PERGUNTA, com as duas respostas do mesmo tamanho.**
// Uma entrevista de emprego é a conversa mais assimétrica que existe: de um lado
// quem decide, do outro quem precisa do emprego. Se "autorizar" fosse um botão
// verde grande e "não autorizar" um link cinza, a pessoa clicaria no primeiro —
// não porque concordou, mas porque não sente que pode recusar. Por isso os dois
// botões têm o mesmo peso, e a tela DIZ que recusar não afeta a avaliação.
//
// **Recusar é um registro, não um vazio** (v2.34): sem manifestação gravada,
// "não foi perguntado" e "disse não" são a mesma linha em branco, e não se prova
// que a pessoa foi consultada.
//
// **Nada some em silêncio** (v2.00): cada estado aparece com o motivo. Ausência
// de transcrição sem explicação faria o entrevistador achar que o sistema perdeu
// o trabalho dele — e o trabalho é a entrevista inteira.

const MIME_PREFERIDOS = ['audio/webm;codecs=opus', 'audio/webm', 'audio/mp4', 'audio/ogg']

function mimeSuportado() {
  if (typeof MediaRecorder === 'undefined') return null
  return MIME_PREFERIDOS.find((m) => MediaRecorder.isTypeSupported?.(m)) || ''
}

export default function GravacaoEntrevista({ entrevistaId, encerrada }) {
  const [g, setG] = useState(null)
  const [erro, setErro] = useState(null)
  const [ocupado, setOcupado] = useState(false)
  const [gravando, setGravando] = useState(false)
  const [segundos, setSegundos] = useState(0)
  const rec = useRef(null)
  const pedacos = useRef([])
  const inicio = useRef(0)
  const cronometro = useRef(null)

  const carregar = () => api.gravacaoEntrevista(entrevistaId)
    .then((d) => { setG(d); setErro(null) })
    .catch((e) => setErro(e.amigavel || e.detail || e.message))

  useEffect(() => { carregar() }, [entrevistaId])

  // Enquanto transcreve, a tela se atualiza sozinha: sem isto o RH ficaria
  // olhando "Transcrevendo…" sem saber se acabou, e recarregaria a página à mão.
  useEffect(() => {
    if (!g || !['aguardando', 'processando'].includes(g.status)) return
    const t = setInterval(carregar, 8000)
    return () => clearInterval(t)
  }, [g?.status, entrevistaId])

  useEffect(() => () => {
    // Solta o microfone se o componente sair enquanto grava — senão o navegador
    // fica com a luz da câmera/mic acesa depois de a tela fechar.
    if (rec.current?.state === 'recording') rec.current.stop()
    if (cronometro.current) clearInterval(cronometro.current)
  }, [])

  const consentir = async (sim) => {
    if (!sim && !window.confirm(
      'Registrar que a pessoa NÃO autorizou a gravação desta entrevista?')) return
    setOcupado(true); setErro(null)
    try {
      setG(await api.consentirGravacao(entrevistaId, sim))
    } catch (e) {
      setErro(e.dados?.mensagem || e.amigavel || e.detail || e.message)
    } finally { setOcupado(false) }
  }

  const comecar = async () => {
    setErro(null)
    const mime = mimeSuportado()
    if (mime === null) {
      setErro('Este navegador não grava áudio. Use o Chrome ou o Edge, ou envie '
              + 'um arquivo de áudio pelo botão abaixo.')
      return
    }
    try {
      const fluxo = await navigator.mediaDevices.getUserMedia({ audio: true })
      const r = new MediaRecorder(fluxo, mime ? { mimeType: mime } : undefined)
      pedacos.current = []
      r.ondataavailable = (ev) => { if (ev.data.size) pedacos.current.push(ev.data) }
      r.onstop = async () => {
        fluxo.getTracks().forEach((t) => t.stop())   // solta o microfone
        const dur = (Date.now() - inicio.current) / 1000
        const blob = new Blob(pedacos.current, { type: mime || 'audio/webm' })
        await enviar(new File([blob], 'entrevista.webm', { type: blob.type }), dur)
      }
      inicio.current = Date.now()
      setSegundos(0)
      cronometro.current = setInterval(
        () => setSegundos(Math.floor((Date.now() - inicio.current) / 1000)), 1000)
      r.start(1000)   // fatia de 1s: se a aba fechar, o que já veio está salvo
      rec.current = r
      setGravando(true)
    } catch {
      // Não distingue "negou a permissão" de "não há microfone" porque a ação
      // é a mesma; o que a mensagem precisa dizer é o que RESOLVE.
      setErro('Não foi possível acessar o microfone. Autorize o uso no navegador '
              + '(cadeado ao lado do endereço) e tente de novo.')
    }
  }

  const parar = () => {
    if (cronometro.current) clearInterval(cronometro.current)
    setGravando(false)
    if (rec.current?.state === 'recording') rec.current.stop()
  }

  const enviar = async (arquivo, duracaoS) => {
    setOcupado(true); setErro(null)
    try {
      setG(await api.subirAudioEntrevista(entrevistaId, arquivo, duracaoS))
    } catch (e) {
      setErro(e.dados?.mensagem
        || (e.dados?.erro === 'formato_nao_suportado'
            ? `Formato não aceito (${e.dados.recebido}). Aceitos: ${e.dados.aceitos?.join(', ')}.`
            : e.amigavel || e.detail || e.message))
    } finally { setOcupado(false) }
  }

  const excluir = async () => {
    if (!window.confirm('Apagar o áudio e a transcrição desta entrevista?\n\n'
      + 'O áudio é removido em definitivo. O registro de que a pessoa foi '
      + 'consultada permanece.')) return
    setOcupado(true); setErro(null)
    try {
      setG(await api.excluirGravacaoEntrevista(entrevistaId))
    } catch (e) {
      setErro(e.amigavel || e.detail || e.message)
    } finally { setOcupado(false) }
  }

  const tentarDeNovo = async () => {
    setOcupado(true); setErro(null)
    try {
      setG(await api.retranscreverEntrevista(entrevistaId))
    } catch (e) {
      setErro(e.dados?.mensagem || e.amigavel || e.detail || e.message)
    } finally { setOcupado(false) }
  }

  if (!g && !erro) return <div className="rh-card"><p>Carregando…</p></div>

  const st = g?.status
  return (
    <div className="rh-card">
      <strong>🎙️ Gravação e transcrição</strong>

      {erro && <p className="alerta">{erro}</p>}

      {/* --- A PERGUNTA. As duas respostas com o mesmo peso visual. --- */}
      {st === 'nao_perguntado' && (
        <>
          <p className="explica">
            Você pode gravar o áudio desta entrevista para gerar a transcrição
            depois — assim não precisa anotar enquanto conversa.
            <strong> Pergunte à pessoa se ela autoriza.</strong>
          </p>
          <p className="explica">
            O áudio fica guardado no próprio sistema, não é enviado a nenhum
            serviço externo, e só o RH tem acesso. <strong>Recusar não afeta em
            nada a avaliação</strong> — a entrevista acontece do mesmo jeito.
          </p>
          <div className="navegacao">
            <button className="btn-secundario btn-mini" disabled={ocupado || encerrada}
                    onClick={() => consentir(true)}>Ela autorizou</button>
            <button className="btn-secundario btn-mini" disabled={ocupado || encerrada}
                    onClick={() => consentir(false)}>Ela não autorizou</button>
          </div>
        </>
      )}

      {st === 'recusado' && (
        <>
          <p className="explica">
            <strong>A pessoa não autorizou a gravação.</strong> Registrado
            {g.consentimento_por ? ` por ${g.consentimento_por}` : ''}
            {g.consentimento_em ? ` em ${fmtDataHora(g.consentimento_em)}` : ''}.
            Não pergunte de novo nesta entrevista.
          </p>
          {!encerrada && (
            <button className="btn-link" disabled={ocupado}
                    onClick={() => consentir(true)}>a pessoa mudou de ideia e autorizou</button>
          )}
        </>
      )}

      {st === 'consentido' && (
        <>
          <p className="explica">
            Autorizado{g.consentimento_em ? ` em ${fmtDataHora(g.consentimento_em)}` : ''}.
            {gravando
              ? ' Gravando — pare quando a conversa terminar.'
              : ' Comece a gravar quando a conversa começar.'}
          </p>
          <div className="navegacao">
            {!gravando
              ? <button className="btn-secundario btn-mini" disabled={ocupado || encerrada}
                        onClick={comecar}>● Gravar</button>
              : <button className="btn-remover btn-mini" onClick={parar}>
                  ■ Parar ({fmtDuracao(segundos)})</button>}
            {!gravando && (
              <label className="btn-secundario btn-mini" style={{ cursor: 'pointer' }}>
                Enviar arquivo de áudio
                <input type="file" accept="audio/*" style={{ display: 'none' }}
                       disabled={ocupado || encerrada}
                       onChange={(e) => { const f = e.target.files?.[0]; if (f) enviar(f, null) }} />
              </label>
            )}
          </div>
        </>
      )}

      {['aguardando', 'processando'].includes(st) && (
        <p className="explica">
          <strong>{g.rotulo}</strong> — a transcrição roda em segundo plano e pode
          levar alguns minutos. Pode fechar esta tela; ela continua.
        </p>
      )}

      {st === 'audio_inaudivel' && (
        <>
          <p className="aviso-inline">{g.erro || 'O áudio não tem fala reconhecível.'}</p>
          <div className="navegacao">
            <button className="btn-secundario btn-mini" disabled={ocupado}
                    onClick={tentarDeNovo}>Tentar transcrever de novo</button>
            <a className="btn-secundario btn-mini" href={api.urlAudioEntrevista(entrevistaId)}
               target="_blank" rel="noreferrer">Ouvir o áudio</a>
          </div>
        </>
      )}

      {st === 'falhou' && (
        <>
          {/* Falha COM motivo e COM saída: recusar sem oferecer alternativa
              deixa o problema na mão de quem opera (v2.87/v2.93). */}
          <p className="alerta">{g.erro || 'Não foi possível transcrever.'}</p>
          <div className="navegacao">
            <button className="btn-secundario btn-mini" disabled={ocupado}
                    onClick={tentarDeNovo}>Tentar de novo</button>
            <a className="btn-secundario btn-mini" href={api.urlAudioEntrevista(entrevistaId)}
               target="_blank" rel="noreferrer">Ouvir o áudio</a>
          </div>
        </>
      )}

      {st === 'pronta' && (
        <>
          <p className="explica">
            Transcrição pronta{g.transcrito_em ? ` em ${fmtDataHora(g.transcrito_em)}` : ''}
            {g.duracao_s ? ` · ${fmtDuracao(g.duracao_s)} de áudio` : ''}.
          </p>
          <div className="navegacao">
            <a className="btn-secundario btn-mini" href={api.urlTextoEntrevista(entrevistaId)}>
              ⬇ Baixar transcrição</a>
            <a className="btn-secundario btn-mini" href={api.urlAudioEntrevista(entrevistaId)}
               target="_blank" rel="noreferrer">Ouvir o áudio</a>
          </div>
        </>
      )}

      {g?.tem_audio && !encerrada && (
        <p style={{ marginTop: 'var(--esp-2)' }}>
          <button className="btn-link" disabled={ocupado} onClick={excluir}>
            apagar áudio e transcrição</button>
        </p>
      )}
    </div>
  )
}
