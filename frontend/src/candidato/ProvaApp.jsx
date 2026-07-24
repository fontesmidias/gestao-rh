import { useEffect, useRef, useState } from 'react'
import { useParams } from 'react-router-dom'
import { prova as api } from '../api.js'
import { iniciarTelemetria } from './telemetria.js'
import logo from '../assets/logo.png'

// Aplicação PÚBLICA de uma prova por cargo (link /p/{token}). A pessoa se
// identifica só pelo nome, responde questões objetivas e discursivas com timer,
// e envia. NÃO vê a própria nota — é seleção, restrita ao RH.
export default function ProvaApp() {
  const { token } = useParams()
  const chaveAid = `prova_aid_${token}`
  const [info, setInfo] = useState(null)
  const [fase, setFase] = useState('carregando') // carregando | invalido | identificar | prova | fim
  const [aid, setAid] = useState(() => localStorage.getItem(chaveAid) || null)
  const [nome, setNome] = useState('')
  const [erro, setErro] = useState(null)
  const [carregando, setCarregando] = useState(false)
  const [aidFim, setAidFim] = useState(null)       // aid guardado p/ a revisão pós-prova
  const [temRevisao, setTemRevisao] = useState(false)

  useEffect(() => {
    api.info(token)
      .then((i) => { setInfo(i); setFase(aid ? 'prova' : (i.ativo ? 'identificar' : 'invalido')) })
      .catch(() => setFase('invalido'))
  }, [token])

  const participar = async (e) => {
    e.preventDefault()
    if (nome.trim().length < 3) { setErro('Informe seu nome completo.'); return }
    setErro(null); setCarregando(true)
    try {
      const r = await api.participar(token, nome.trim())
      localStorage.setItem(chaveAid, r.aplicacao_id)
      setAid(r.aplicacao_id); setFase('prova')
    } catch (err) {
      setErro(err.detail === 'link_desativado' ? 'Este link está desativado.'
        : 'Não foi possível começar. Tente novamente.')
    } finally { setCarregando(false) }
  }

  if (fase === 'carregando') return <Casca><p>Carregando…</p></Casca>
  if (fase === 'invalido') return (
    <Casca><div className="alerta">Este link de prova não existe ou está desativado —
      confira o endereço com quem enviou.</div></Casca>)
  if (fase === 'fim') return (
    <Casca>
      <div className="verificar-selo valido">✓</div>
      <h2>Prova enviada!</h2>
      <p className="explica centro">Recebemos suas respostas. Obrigado por participar —
        o RH da Green House dará retorno.</p>
      {temRevisao && <RevisaoProva token={token} aid={aidFim} />}
    </Casca>)
  if (fase === 'identificar') return (
    <Casca>
      <h2>{info?.titulo || 'Prova'}</h2>
      {info?.descricao && <p className="explica centro">{info.descricao}</p>}
      <form onSubmit={participar}>
        <label className="campo"><span className="rotulo">Seu nome completo</span>
          <input value={nome} onChange={(e) => setNome(e.target.value)} autoFocus autoComplete="name" /></label>
        <p className="explica" style={{ fontSize: '.8rem' }}>Durante a prova registramos o
          comportamento na tela (troca de aba, saída, cópia/cola) — apenas para fins de avaliação.</p>
        {erro && <div className="alerta">{erro}</div>}
        <button className="btn-principal" disabled={carregando}>
          {carregando ? 'Começando…' : 'Começar a prova'}</button>
      </form>
    </Casca>)
  return <Questionario token={token} aid={aid} titulo={info?.titulo}
                       aoConcluir={(r) => {
                         localStorage.removeItem(chaveAid)
                         setAidFim(aid); setTemRevisao(!!r?.tem_revisao); setFase('fim')
                       }} />
}

function Casca({ children }) {
  return (
    <main className="cartao verificar">
      <span className="verificar-marca"><img src={logo} alt="Green House" className="logo-img" /></span>
      {children}
    </main>
  )
}

function Questionario({ token, aid, titulo, aoConcluir }) {
  const [dados, setDados] = useState(null)
  const [idx, setIdx] = useState(0)
  const [resp, setResp] = useState({})       // questao_id -> {escolha|texto}
  const [restante, setRestante] = useState(null)
  const [erro, setErro] = useState(null)
  const [enviando, setEnviando] = useState(false)
  const timerRef = useRef(null)
  const prazoRef = useRef(null)   // instante-alvo absoluto (ms) do fim da prova

  useEffect(() => iniciarTelemetria(token, null, {
    postar: (lote) => api.eventos(token, aid, lote),
    beaconUrl: () => api.eventosUrl(token, aid),
  }), [])

  // Sincroniza o relógio com o SERVIDOR (autoritativo): fixa o instante-alvo do
  // fim a partir de segundos_restantes. O contador visual passa a derivar desse
  // alvo, não de decrementos por segundo — assim, se o celular suspende o app
  // (o setInterval congela), ao voltar o número já aparece certo em vez de
  // "parecer que o tempo parou" (feedback do Bruno).
  const sincronizar = (segundos) => {
    if (segundos == null) return
    prazoRef.current = Date.now() + segundos * 1000
    setRestante(Math.max(0, Math.round(segundos)))
  }

  useEffect(() => {
    api.iniciar(token, aid)
      .then(() => api.questoes(token, aid))
      .then((d) => { setDados(d); setIdx(Math.min(d.respondidas || 0, d.questoes.length - 1)); sincronizar(d.segundos_restantes) })
      .catch((e) => setErro(e.detail === 'prova_ja_realizada'
        ? 'Esta prova já foi enviada.' : 'Não foi possível carregar. Recarregue a página.'))
  }, [])

  useEffect(() => {
    if (restante == null || prazoRef.current == null) return
    // deriva do instante-alvo absoluto: robusto a suspensão da aba/app
    timerRef.current = setInterval(() => {
      setRestante(Math.max(0, Math.round((prazoRef.current - Date.now()) / 1000)))
    }, 1000)
    return () => clearInterval(timerRef.current)
  }, [restante != null])

  // Ao voltar o foco (voltou de outro app/aba), re-busca o tempo do servidor:
  // corrige qualquer defasagem do relógio local e detecta expiração imediata.
  useEffect(() => {
    const aoVoltar = () => {
      if (document.visibilityState !== 'visible' || !dados) return
      api.questoes(token, aid)
        .then((d) => sincronizar(d.segundos_restantes))
        .catch(() => {})
    }
    document.addEventListener('visibilitychange', aoVoltar)
    return () => document.removeEventListener('visibilitychange', aoVoltar)
  }, [dados])

  useEffect(() => {
    if (restante === 0 && dados) api.concluir(token, aid).then(aoConcluir).catch(() => {})
  }, [restante])

  if (erro) return <Casca><div className="alerta">{erro}</div></Casca>
  if (!dados) return <Casca><p>Carregando a prova…</p></Casca>

  const q = dados.questoes[idx]
  const r = resp[q.id] || {}
  const objetiva = q.tipo === 'objetiva'
  const completa = objetiva ? !!r.escolha : (r.texto || '').trim().length > 0
  const ultima = idx === dados.questoes.length - 1
  const mmss = restante == null ? '' :
    `${String(Math.floor(restante / 60)).padStart(2, '0')}:${String(restante % 60).padStart(2, '0')}`

  const proximo = async () => {
    setErro(null); setEnviando(true)
    try {
      await api.responder(token, aid, { questao_id: q.id, escolha: r.escolha, texto: r.texto })
      if (ultima) { const fim = await api.concluir(token, aid); await aoConcluir(fim) }
      else setIdx(idx + 1)
    } catch (e) {
      setErro(`Não foi possível salvar (${e.detail || e.message}). Tente de novo.`)
    } finally { setEnviando(false) }
  }

  return (
    <div className="teste-caixa">
      <div className="teste-cabecalho">
        {titulo ? `${titulo} — ` : ''}Questão {idx + 1} de {dados.questoes.length}
      </div>
      <div className="teste-corpo">
        <p className="teste-situacao">{q.enunciado}</p>
        {objetiva ? (
          q.opcoes.map((op) => (
            <label key={op.id} className={`teste-opcao-sit ${r.escolha === op.id ? 'marcada' : ''}`}>
              <input type="radio" name={`q-${q.id}`} checked={r.escolha === op.id}
                     onChange={() => setResp({ ...resp, [q.id]: { escolha: op.id } })} />
              <span>{op.texto}</span>
            </label>
          ))
        ) : (
          <textarea className="prova-resposta" rows={6} value={r.texto || ''}
                    placeholder="Escreva sua resposta…"
                    onChange={(e) => setResp({ ...resp, [q.id]: { texto: e.target.value } })} />
        )}
      </div>
      {erro && <div className="alerta" style={{ margin: '0 1rem' }}>{erro}</div>}
      <div className="teste-rodape">
        <span className="teste-timer">🕐 {mmss}</span>
        <button className="btn-principal btn-mini" disabled={!completa || enviando} onClick={proximo}>
          {ultima ? 'Concluir e enviar' : 'Próximo »'}</button>
      </div>
    </div>
  )
}

// Revisão pós-prova (só quando a prova permite mostrar_explicacao). Mostra
// gabarito + explicação de cada questão para o participante APRENDER — nunca a
// nota (isso continua restrito ao RH). Carregada sob demanda (um clique).
function RevisaoProva({ token, aid }) {
  const [itens, setItens] = useState(null)
  const [aberto, setAberto] = useState(false)
  const [erro, setErro] = useState(null)

  const carregar = async () => {
    setAberto(true)
    try { const r = await api.revisao(token, aid); setItens(r.itens) }
    catch { setErro('Não foi possível carregar a revisão agora.') }
  }

  if (!aberto) return (
    <button className="btn-secundario" style={{ marginTop: '1rem' }} onClick={carregar}>
      📖 Ver o gabarito e as explicações</button>
  )
  if (erro) return <div className="alerta" style={{ marginTop: '1rem' }}>{erro}</div>
  if (!itens) return <p className="explica centro" style={{ marginTop: '1rem' }}>Carregando…</p>

  return (
    <div className="prova-revisao" style={{ marginTop: '1rem', textAlign: 'left' }}>
      {itens.map((it, i) => (
        <div className="prova-questao" key={i}>
          <strong>{i + 1}. {it.enunciado}</strong>
          {it.tipo === 'objetiva' ? (
            <ul className="prova-opcoes">
              {(it.opcoes || []).map((o) => {
                const correta = o.id === it.gabarito
                const escolhida = o.id === it.escolha
                return (
                  <li key={o.id} className={correta ? 'certa' : (escolhida ? 'errada' : '')}>
                    {correta ? '✔ ' : (escolhida ? '✗ ' : '')}{o.texto}
                    {escolhida && !correta && <small className="explica"> (sua resposta)</small>}
                  </li>
                )
              })}
            </ul>
          ) : (
            <p className="explica">Sua resposta: {it.resposta || '—'} · correção manual do RH.</p>
          )}
          {it.explicacao && (
            <small className="explica" style={{ margin: '.2rem 0 0', display: 'block' }}>💡 {it.explicacao}</small>
          )}
        </div>
      ))}
    </div>
  )
}
