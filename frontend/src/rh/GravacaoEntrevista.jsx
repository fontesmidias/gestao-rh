import { useEffect, useRef, useState } from 'react'
import { rh as api } from '../api.js'
import { fmtDataHora, fmtDuracao } from '../fmt.js'
import PlayerAudio from './PlayerAudio.jsx'
import BotaoBaixar from './BotaoBaixar.jsx'

// Gravação e transcrição da entrevista (v2.97, blocos na v2.98).
//
// Desenho em `docs/planejamento/14-transcricao-de-entrevistas.md`. As decisões
// que este componente carrega:
//
// **O consentimento é uma PERGUNTA, com as duas respostas do mesmo tamanho.**
// Uma entrevista de emprego é a conversa mais assimétrica que existe: de um lado
// quem decide, do outro quem precisa do emprego. Se "autorizar" fosse um botão
// verde grande e "não autorizar" um link cinza, a pessoa clicaria no primeiro —
// não porque concordou, mas porque não sente que pode recusar.
//
// **Os blocos são AUTOMÁTICOS e invisíveis** (decisão do Bruno, 2026-08-12): a
// cada N minutos o `MediaRecorder` fecha um pedaço e ele sobe SOZINHO, sem
// interromper a conversa. O entrevistador só clica em Gravar e em Encerrar.
// Motivo: se o navegador cair aos 32 min, o que já subiu está salvo — e a
// entrevista não se refaz. O disclaimer na tela diz isso, para ninguém fechar a
// aba achando que só o "Encerrar" salva.
//
// **Pausar ≠ Encerrar.** Pausar retoma no mesmo bloco; Encerrar pergunta antes,
// porque é irreversível (manda transcrever e não dá para continuar). Um clique
// errado no meio de uma entrevista de 40 minutos não pode custar a gravação.

const MIME_PREFERIDOS = ['audio/webm;codecs=opus', 'audio/webm', 'audio/mp4', 'audio/ogg']
const BLOCO_MIN_PADRAO = 10

function mimeSuportado() {
  if (typeof MediaRecorder === 'undefined') return null
  return MIME_PREFERIDOS.find((m) => MediaRecorder.isTypeSupported?.(m)) || ''
}

export default function GravacaoEntrevista({ entrevistaId, encerrada }) {
  const [g, setG] = useState(null)
  const [erro, setErro] = useState(null)
  const [ocupado, setOcupado] = useState(false)
  const [fase, setFase] = useState('parado')      // parado | gravando | pausado
  const [segundos, setSegundos] = useState(0)
  const [enviando, setEnviando] = useState(0)     // blocos subindo agora

  const rec = useRef(null)
  const fluxoRef = useRef(null)
  const pedacos = useRef([])
  const indiceRef = useRef(1)
  const inicioBlocoRef = useRef(0)     // segundo da entrevista em que o bloco começou
  const totalRef = useRef(0)           // segundos já gravados (sobrevive à pausa)
  const marcaRef = useRef(0)           // Date.now() do último "retomar"
  const cronometro = useRef(null)
  const fecharBloco = useRef(null)     // timer do corte automático
  const encerrandoRef = useRef(false)  // distingue corte automático de fim real

  const blocoMin = g?.bloco_min || BLOCO_MIN_PADRAO

  const carregar = () => api.gravacaoEntrevista(entrevistaId)
    .then((d) => { setG(d); setErro(null) })
    .catch((e) => setErro(e.amigavel || e.detail || e.message))

  useEffect(() => { carregar() }, [entrevistaId])

  // Enquanto transcreve, a tela se atualiza sozinha: sem isto o RH ficaria
  // olhando "Transcrevendo…" sem saber se acabou.
  useEffect(() => {
    if (!g || !['aguardando', 'processando'].includes(g.status)) return
    const t = setInterval(carregar, 8000)
    return () => clearInterval(t)
  }, [g?.status, entrevistaId])

  // Solta o microfone se a tela sair no meio — senão o navegador fica com o
  // indicador de gravação aceso depois de a ficha fechar.
  useEffect(() => () => {
    if (rec.current?.state && rec.current.state !== 'inactive') rec.current.stop()
    fluxoRef.current?.getTracks?.().forEach((t) => t.stop())
    clearInterval(cronometro.current)
    clearTimeout(fecharBloco.current)
  }, [])

  // Avisa antes de fechar a aba gravando. O navegador não deixa escolher o
  // texto, mas o aviso existe — e sem ele um F5 distraído custa a conversa.
  useEffect(() => {
    if (fase === 'parado') return
    const aviso = (ev) => { ev.preventDefault(); ev.returnValue = '' }
    window.addEventListener('beforeunload', aviso)
    return () => window.removeEventListener('beforeunload', aviso)
  }, [fase])

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

  const enviarBloco = async (blob, indice, duracaoS, inicioS) => {
    if (!blob || blob.size === 0) return
    setEnviando((n) => n + 1)
    try {
      const arq = new File([blob], `bloco-${indice}.webm`, { type: blob.type })
      const r = await api.subirBlocoEntrevista(entrevistaId, arq,
        { indice, duracaoS, inicioS })
      setG(r)
    } catch (e) {
      // O bloco não subiu, mas a gravação CONTINUA: interromper a entrevista
      // por causa de um trecho perdido seria pior. A tela diz qual falhou.
      setErro(`O trecho ${indice} não foi enviado (${e.detail || e.message}). `
              + 'A gravação continua; você pode reenviar depois de encerrar.')
    } finally { setEnviando((n) => Math.max(0, n - 1)) }
  }

  // Cria um MediaRecorder para UM bloco. Ao parar, envia e — se ainda estamos
  // gravando — abre o próximo. É assim que o corte fica invisível: o áudio do
  // bloco seguinte já está sendo capturado quando o anterior sobe.
  const abrirBloco = (fluxo, mime) => {
    const r = new MediaRecorder(fluxo, mime ? { mimeType: mime } : undefined)
    const meuIndice = indiceRef.current
    const meuInicio = inicioBlocoRef.current
    pedacos.current = []
    r.ondataavailable = (ev) => { if (ev.data?.size) pedacos.current.push(ev.data) }
    r.onstop = () => {
      const blob = new Blob(pedacos.current, { type: mime || 'audio/webm' })
      const dur = Math.max(0, Math.round(totalRef.current - meuInicio))
      enviarBloco(blob, meuIndice, dur, meuInicio)
      if (!encerrandoRef.current && fluxoRef.current) {
        indiceRef.current = meuIndice + 1
        inicioBlocoRef.current = totalRef.current
        abrirBloco(fluxoRef.current, mime)
      }
    }
    r.start(1000)   // fatia de 1s: se algo travar, o que já veio está no array
    rec.current = r
    clearTimeout(fecharBloco.current)
    fecharBloco.current = setTimeout(() => {
      if (r.state === 'recording') r.stop()     // o onstop abre o próximo
    }, blocoMin * 60 * 1000)
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
      fluxoRef.current = fluxo
      encerrandoRef.current = false
      indiceRef.current = (g?.blocos?.length || 0) + 1
      totalRef.current = 0
      inicioBlocoRef.current = 0
      marcaRef.current = Date.now()
      setSegundos(0)
      clearInterval(cronometro.current)
      cronometro.current = setInterval(() => {
        const s = totalRef.current + (Date.now() - marcaRef.current) / 1000
        setSegundos(Math.floor(s))
      }, 500)
      abrirBloco(fluxo, mime)
      setFase('gravando')
    } catch {
      // Não distingue "negou a permissão" de "não há microfone": a ação que
      // resolve é a mesma, e é isso que a mensagem precisa dizer.
      setErro('Não foi possível acessar o microfone. Autorize o uso no navegador '
              + '(cadeado ao lado do endereço) e tente de novo.')
    }
  }

  const pausar = () => {
    if (rec.current?.state !== 'recording') return
    rec.current.pause()                 // PAUSE, não stop: o bloco continua o mesmo
    clearTimeout(fecharBloco.current)   // o relógio do corte não corre na pausa
    clearInterval(cronometro.current)
    totalRef.current += (Date.now() - marcaRef.current) / 1000
    setSegundos(Math.floor(totalRef.current))
    setFase('pausado')
  }

  const retomar = () => {
    if (rec.current?.state !== 'paused') return
    rec.current.resume()
    marcaRef.current = Date.now()
    cronometro.current = setInterval(() => {
      setSegundos(Math.floor(totalRef.current + (Date.now() - marcaRef.current) / 1000))
    }, 500)
    // Repõe o corte com o tempo que FALTAVA do bloco, não com o cheio: senão
    // uma entrevista com muitas pausas geraria blocos de 25 min.
    const decorrido = totalRef.current - inicioBlocoRef.current
    const resta = Math.max(5, blocoMin * 60 - decorrido) * 1000
    fecharBloco.current = setTimeout(() => {
      if (rec.current?.state === 'recording') rec.current.stop()
    }, resta)
    setFase('gravando')
  }

  const encerrar = () => {
    const tempo = fmtDuracao(segundos)
    if (!window.confirm(
      `Encerrar a gravação de ${tempo}?\n\n`
      + 'O áudio vai para transcrição e não dá para continuar esta gravação '
      + 'depois. Se quer só interromper por um momento, use Pausar.')) return
    encerrandoRef.current = true
    clearTimeout(fecharBloco.current)
    clearInterval(cronometro.current)
    if (rec.current?.state === 'paused') {
      // `stop()` num recorder pausado não dispara `ondataavailable` em todos os
      // navegadores — retomar antes garante o último pedaço.
      rec.current.resume()
      totalRef.current += 0
    }
    if (rec.current?.state && rec.current.state !== 'inactive') rec.current.stop()
    fluxoRef.current?.getTracks?.().forEach((t) => t.stop())
    fluxoRef.current = null
    setFase('parado')
  }

  const enviarArquivo = async (arquivo) => {
    setOcupado(true); setErro(null)
    try {
      setG(await api.subirAudioEntrevista(entrevistaId, arquivo, null))
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
    try { setG(await api.excluirGravacaoEntrevista(entrevistaId)) }
    catch (e) { setErro(e.amigavel || e.detail || e.message) }
    finally { setOcupado(false) }
  }

  const tentarDeNovo = async () => {
    setOcupado(true); setErro(null)
    try { setG(await api.retranscreverEntrevista(entrevistaId)) }
    catch (e) { setErro(e.dados?.mensagem || e.amigavel || e.detail || e.message) }
    finally { setOcupado(false) }
  }

  if (!g && !erro) return <div className="rh-card"><p>Carregando…</p></div>

  const st = g?.status
  const gravandoAgora = fase !== 'parado'
  const blocos = g?.blocos || []

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

      {/* --- GRAVAÇÃO --- */}
      {g?.pode_gravar && !encerrada && (
        <>
          {!gravandoAgora && (
            <p className="explica">
              Autorizado{g.consentimento_em ? ` em ${fmtDataHora(g.consentimento_em)}` : ''}.
              {' '}Comece a gravar quando a conversa começar.
            </p>
          )}

          {gravandoAgora && (
            <>
              <p className={fase === 'pausado' ? 'aviso-inline' : 'explica'}>
                <strong>
                  {fase === 'gravando' ? '⏺ Gravando' : '⏸ Pausado'} — {fmtDuracao(segundos)}
                </strong>
                {enviando > 0 && ` · enviando ${enviando} trecho(s)…`}
              </p>
              {/* O DISCLAIMER que o Bruno pediu: a pessoa precisa saber que o
                  envio acontece durante a conversa, senão fecha a aba achando
                  que só o "Encerrar" salva. */}
              <p className="explica">
                A gravação é enviada em trechos de {blocoMin} min enquanto vocês
                conversam — se algo acontecer com o navegador, o que já subiu
                está guardado. <strong>Não feche esta aba.</strong>
              </p>
            </>
          )}

          <div className="navegacao">
            {fase === 'parado' && (
              <button className="btn-secundario btn-mini" disabled={ocupado}
                      onClick={comecar}>⏺ Gravar</button>
            )}
            {fase === 'gravando' && (
              <button className="btn-secundario btn-mini" onClick={pausar}>⏸ Pausar</button>
            )}
            {fase === 'pausado' && (
              <button className="btn-secundario btn-mini" onClick={retomar}>▶ Retomar</button>
            )}
            {gravandoAgora && (
              <button className="btn-remover btn-mini" onClick={encerrar}>
                ⏹ Encerrar</button>
            )}
            {!gravandoAgora && (
              <label className="btn-secundario btn-mini" style={{ cursor: 'pointer' }}>
                Enviar arquivo de áudio
                <input type="file" accept="audio/*" style={{ display: 'none' }}
                       disabled={ocupado}
                       onChange={(e) => { const f = e.target.files?.[0]; if (f) enviarArquivo(f) }} />
              </label>
            )}
          </div>
        </>
      )}

      {['aguardando', 'processando'].includes(st) && !gravandoAgora && (
        <p className="explica">
          <strong>{g.rotulo}</strong> — a transcrição roda em segundo plano e pode
          levar alguns minutos. Pode fechar esta tela; ela continua.
        </p>
      )}

      {st === 'audio_inaudivel' && (
        <>
          <p className="aviso-inline">{g.erro || 'O áudio não tem fala reconhecível.'}</p>
          <button className="btn-secundario btn-mini" disabled={ocupado}
                  onClick={tentarDeNovo}>Tentar transcrever de novo</button>
        </>
      )}

      {st === 'falhou' && (
        <>
          {/* Falha COM motivo e COM saída: recusar sem oferecer alternativa
              deixa o problema na mão de quem opera (v2.87/v2.93). */}
          <p className="alerta">{g.erro || 'Não foi possível transcrever.'}</p>
          <button className="btn-secundario btn-mini" disabled={ocupado}
                  onClick={tentarDeNovo}>Tentar de novo</button>
        </>
      )}

      {st === 'pronta' && (
        <>
          <p className="explica">
            Transcrição pronta{g.transcrito_em ? ` em ${fmtDataHora(g.transcrito_em)}` : ''}
            {g.duracao_total_s ? ` · ${fmtDuracao(g.duracao_total_s)} de áudio` : ''}.
          </p>
          {/* Transcrição parcial (algum bloco falhou): o texto SAI, mas a tela
              diz qual trecho falta — esconder seria pior (v2.93). */}
          {g.erro && <p className="aviso-inline">{g.erro}</p>}
          <div className="navegacao">
            {/* NÃO é <a href>: rota autenticada, e o navegador segue link sem
                o header Authorization — o defeito que apareceu como
                {"detail":"nao_autenticado"} na tela (v2.98.4). */}
            <BotaoBaixar url={api.urlTextoEntrevista(entrevistaId)}
                         nome="transcricao.txt">⬇ Baixar transcrição (.txt)</BotaoBaixar>
          </div>
        </>
      )}

      {/* --- OS TRECHOS: ouvir e baixar um a um --- */}
      {blocos.length > 0 && (
        <details>
          <summary>🎧 Trechos gravados ({blocos.length})</summary>
          {blocos.map((b) => (
            <div key={b.indice} className="bloco-linha">
              <PlayerAudio
                url={api.urlBlocoEntrevista(entrevistaId, b.indice)}
                nome={`trecho-${b.indice}`}
                rotulo={`Trecho ${b.indice}${b.duracao_s ? ` · ${fmtDuracao(b.duracao_s)}` : ''}`} />
              {b.status === 'falhou' && (
                <span className="chip" style={{ '--chip-cor': 'var(--erro)' }}
                      title={b.erro || ''}>não transcrito</span>
              )}
              {b.status === 'inaudivel' && (
                <span className="chip" style={{ '--chip-cor': 'var(--ambar)' }}
                      title="Sem fala reconhecível neste trecho — normal em pausas.">
                  sem fala</span>
              )}
            </div>
          ))}
        </details>
      )}

      {/* Áudio único (arquivo enviado de fora), sem blocos. */}
      {g?.tem_audio && blocos.length === 0 && (
        <div style={{ marginTop: 'var(--esp-3)' }}>
          <PlayerAudio url={api.urlAudioEntrevista(entrevistaId)}
                       nome="entrevista" rotulo="Áudio da entrevista" />
        </div>
      )}

      {(g?.tem_audio || blocos.length > 0) && !encerrada && !gravandoAgora && (
        <p style={{ marginTop: 'var(--esp-2)' }}>
          <button className="btn-link" disabled={ocupado} onClick={excluir}>
            apagar áudio e transcrição</button>
        </p>
      )}
    </div>
  )
}
