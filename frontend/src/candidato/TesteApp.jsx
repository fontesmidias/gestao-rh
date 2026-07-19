import { useEffect, useRef, useState } from 'react'
import { candidato as api } from '../api.js'
import { iniciarTelemetria } from './telemetria.js'

// Testes do candidato (inventário DISC + situacional), no formato do material
// de referência do RH: identificação mínima -> código por e-mail (2FA) ->
// orientações -> questões com "Mais a ver"/"Menos a ver" e timer -> conclusão.
// O candidato NUNCA vê o resultado — ele é restrito ao RH.
export default function TesteApp({ token, aoConcluirTudo }) {
  const [info, setInfo] = useState(null)
  const [fase, setFase] = useState('carregando')
  // fases: identificar | codigo | menu | instrucoes | teste | fim

  const [tipoAtual, setTipoAtual] = useState(null)

  const recarregar = async () => {
    const s = await api.testes(token)
    setInfo(s)
    if (s.todos_concluidos) { setFase('fim'); return s }
    if (!s.identificado) { setFase('identificar'); return s }
    setFase('menu')
    return s
  }
  useEffect(() => { recarregar() }, [])

  if (!info || fase === 'carregando') return <div className="teste-caixa"><p style={{ padding: '1rem' }}>Carregando…</p></div>

  if (fase === 'identificar') return (
    <Identificacao token={token} nome={info.nome} email={info.email}
                   aoEnviar={() => setFase('codigo')} />
  )
  if (fase === 'codigo') return (
    <Codigo token={token} aoConfirmar={recarregar} aoVoltar={() => setFase('identificar')} />
  )
  if (fase === 'menu') {
    const proximos = info.pendentes || []
    if (!proximos.length) { setFase('fim'); return null }
    const t = proximos[0]
    // retomada: se já estava em andamento, vai direto pro teste
    if (t.status === 'em_andamento') {
      if (tipoAtual !== t.tipo) setTipoAtual(t.tipo)
      return <Questionario token={token} tipo={t.tipo} aoConcluir={recarregar} />
    }
    return <Instrucoes tipo={t.tipo} aoIniciar={async () => {
      await api.testeIniciar(token, t.tipo)
      setTipoAtual(t.tipo)
      setFase('teste')
    }} />
  }
  if (fase === 'teste' && tipoAtual) return (
    <Questionario token={token} tipo={tipoAtual} aoConcluir={async () => {
      const s = await recarregar()
      if (!s.todos_concluidos) setFase('menu')
    }} />
  )
  if (fase === 'fim') return (
    <div className="teste-caixa teste-fim">
      <div className="teste-fim-circulo">✓</div>
      <h2>Preenchimento concluído com sucesso.</h2>
      <p className="explica">Obrigado! Suas respostas foram registradas. Agora vamos seguir para o
        seu cadastro de admissão.</p>
      <button className="btn-principal" onClick={aoConcluirTudo}>Continuar</button>
    </div>
  )
  return null
}

function Identificacao({ token, nome, email, aoEnviar }) {
  const [dados, setDados] = useState({ nome_completo: nome || '', cpf: '', email: email || '' })
  const [erro, setErro] = useState(null)
  const [enviando, setEnviando] = useState(false)

  const enviar = async (e) => {
    e.preventDefault(); setErro(null); setEnviando(true)
    try {
      await api.testesIdentificar(token, dados)
      aoEnviar()
    } catch (err) {
      setErro(err.detail === 'cpf_invalido' ? 'CPF inválido. Confira os números.'
        : err.detail === 'email_invalido' ? 'Informe um e-mail válido.'
        : 'Não foi possível enviar. Tente novamente.')
    } finally { setEnviando(false) }
  }

  return (
    <form className="teste-caixa" onSubmit={enviar}>
      <div className="teste-cabecalho">Confirmação de Cadastro</div>
      <div className="teste-corpo">
        <p className="explica">Antes do teste, confirme seus dados. Enviaremos um <strong>código de
          confirmação</strong> ao seu e-mail.</p>
        <label className="campo"><span className="rotulo">Nome completo</span>
          <input value={dados.nome_completo} required
                 onChange={(e) => setDados({ ...dados, nome_completo: e.target.value })} /></label>
        <label className="campo"><span className="rotulo">CPF</span>
          <input inputMode="numeric" placeholder="000.000.000-00" value={dados.cpf} required
                 onChange={(e) => setDados({ ...dados, cpf: e.target.value })} /></label>
        <label className="campo"><span className="rotulo">E-mail</span>
          <input type="email" placeholder="voce@exemplo.com" value={dados.email} required
                 onChange={(e) => setDados({ ...dados, email: e.target.value })} /></label>
        {erro && <div className="alerta">{erro}</div>}
      </div>
      <div className="teste-rodape">
        <button className="btn-principal btn-mini" disabled={enviando}>
          {enviando ? 'Enviando…' : 'Salvar'}</button>
      </div>
    </form>
  )
}

function Codigo({ token, aoConfirmar, aoVoltar }) {
  const [codigo, setCodigo] = useState('')
  const [erro, setErro] = useState(null)

  const confirmar = async (e) => {
    e.preventDefault(); setErro(null)
    try { await api.testesConfirmar(token, codigo); await aoConfirmar() }
    catch { setErro('Código incorreto ou expirado. Confira no seu e-mail (inclusive no spam).') }
  }

  return (
    <form className="teste-caixa" onSubmit={confirmar}>
      <div className="teste-cabecalho">Confirmação em duas etapas</div>
      <div className="teste-corpo">
        <p className="explica">Enviamos um código de 6 dígitos ao seu e-mail. <strong>O e-mail pode
          ir para o SPAM — é melhor verificar lá também.</strong></p>
        <label className="campo"><span className="rotulo">Código</span>
          <input inputMode="numeric" maxLength={6} placeholder="000000" value={codigo} autoFocus
                 style={{ letterSpacing: '.4em', textAlign: 'center', fontSize: '1.4rem' }}
                 onChange={(e) => setCodigo(e.target.value.replace(/\D/g, ''))} /></label>
        {erro && <div className="alerta">{erro}</div>}
      </div>
      <div className="teste-rodape">
        <button type="button" className="btn-link" onClick={aoVoltar}>← voltar</button>
        <button className="btn-principal btn-mini" disabled={codigo.length < 6}>Confirmar</button>
      </div>
    </form>
  )
}

const NOMES_TESTE = { disc: 'Inventário Comportamental', situacional: 'Teste Situacional' }

function Instrucoes({ tipo, aoIniciar }) {
  const [iniciando, setIniciando] = useState(false)
  const minutos = tipo === 'disc' ? 12 : 15
  return (
    <div className="teste-caixa">
      <div className="teste-cabecalho">{NOMES_TESTE[tipo]}</div>
      <div className="teste-corpo">
        <ul className="teste-orientacoes">
          <li>⏱️ Você terá <strong>{minutos} minutos</strong> para o preenchimento. Evite responder
            se estiver apressado(a). <strong>Você só pode preencher uma vez.</strong></li>
          {tipo === 'disc' ? (
            <li>📋 Em cada questão você verá <strong>4 palavras</strong>: marque na coluna da
              esquerda a que <strong>MAIS</strong> tem a ver com você e, na coluna da direita, a
              que <strong>MENOS</strong> tem a ver — sempre <strong>uma em cada coluna</strong>, e
              nunca a mesma palavra nas duas.</li>
          ) : (
            <li>📋 Em cada situação apresentada, escolha a <strong>única alternativa</strong> que
              melhor representa como você realmente agiria no dia a dia de trabalho.</li>
          )}
          <li>➡️ O botão <strong>Próximo</strong> só habilita quando a questão estiver completa; a
            resposta é salva a cada questão e, ao final, basta tocar em
            <strong> Concluir</strong>.</li>
          <li>🙋 Não peça ajuda para preencher, pois ninguém sabe mais sobre você do que você
            mesmo(a).</li>
          <li>🔕 Não divida sua atenção com outras atividades. Feche redes sociais e e-mail, e não
            converse ao telefone.</li>
          <li>🖥️ Durante o preenchimento, registramos eventos de navegação (saídas da tela, trocas
            de aba/janela e tentativas de captura), para garantir a integridade do processo
            seletivo — conforme a LGPD.</li>
        </ul>
        <p className="explica" style={{ marginTop: '.8rem' }}>Ao responder, você declara que as
          questões serão respondidas de acordo com as orientações recebidas, assumindo total
          responsabilidade sobre a veracidade das respostas. Este é um instrumento de apoio à
          gestão de pessoas; seus dados são tratados conforme a LGPD.</p>
      </div>
      <div className="teste-rodape">
        <button className="btn-principal" disabled={iniciando}
                onClick={async () => { setIniciando(true); try { await aoIniciar() } finally { setIniciando(false) } }}>
          Iniciar o questionário »</button>
      </div>
    </div>
  )
}

function Questionario({ token, tipo, aoConcluir }) {
  const [dados, setDados] = useState(null) // {questoes, segundos_restantes}
  const [idx, setIdx] = useState(0)
  const [resp, setResp] = useState({})     // questao -> {mais, menos} | {escolha}
  const [restante, setRestante] = useState(null)
  const [erro, setErro] = useState(null)
  const [enviando, setEnviando] = useState(false)
  const timerRef = useRef(null)

  useEffect(() => iniciarTelemetria(token, tipo), [tipo])

  useEffect(() => {
    api.testeQuestoes(token, tipo).then((d) => {
      setDados(d)
      setIdx(Math.min(d.respondidas || 0, d.questoes.length - 1))
      setRestante(d.segundos_restantes)
    }).catch(() => setErro('Não foi possível carregar as questões. Recarregue a página.'))
  }, [tipo])

  useEffect(() => {
    if (restante == null) return
    timerRef.current = setInterval(() => setRestante((s) => Math.max(0, s - 1)), 1000)
    return () => clearInterval(timerRef.current)
  }, [restante != null])

  useEffect(() => {
    // tempo esgotado: conclui com o que foi respondido
    if (restante === 0 && dados) { api.testeConcluir(token, tipo).then(aoConcluir) }
  }, [restante])

  if (erro) return <div className="teste-caixa"><div className="teste-corpo"><div className="alerta">{erro}</div></div></div>
  if (!dados) return <div className="teste-caixa"><p style={{ padding: '1rem' }}>Carregando…</p></div>

  const q = dados.questoes[idx]
  const r = resp[q.numero] || {}
  const ehDisc = tipo === 'disc'
  const completa = ehDisc ? (r.mais && r.menos && r.mais !== r.menos) : !!r.escolha
  const ultima = idx === dados.questoes.length - 1
  const mmss = restante == null ? '' :
    `${String(Math.floor(restante / 60)).padStart(2, '0')}:${String(restante % 60).padStart(2, '0')}`

  const proximo = async () => {
    setErro(null); setEnviando(true)
    try {
      await api.testeResponder(token, tipo, { questao: q.numero, ...r })
      if (ultima) { await api.testeConcluir(token, tipo); await aoConcluir() }
      else setIdx(idx + 1)
    } catch (e) {
      setErro(e.detail === 'marque_mais_e_menos_diferentes'
        ? 'Marque uma opção em cada coluna (não pode ser a mesma).'
        : 'Não foi possível salvar. Tente novamente.')
    } finally { setEnviando(false) }
  }

  return (
    <div className="teste-caixa">
      <div className="teste-cabecalho">Questão {q.numero} de {dados.questoes.length}</div>
      {ehDisc ? (
        <>
          <div className="teste-instrucao">
            <span className="teste-tag">Mais a ver</span>
            <span>Marque <strong>uma palavra em cada coluna</strong></span>
            <span className="teste-tag">Menos a ver</span>
          </div>
          <div className="teste-opcoes">
            {q.opcoes.map((adj) => (
              <div key={adj} className="teste-linha">
                <input type="radio" name={`mais-${q.numero}`} checked={r.mais === adj}
                       onChange={() => setResp({ ...resp, [q.numero]: { ...r, mais: adj,
                         menos: r.menos === adj ? undefined : r.menos } })} />
                <span className="teste-adjetivo">{adj}</span>
                <input type="radio" name={`menos-${q.numero}`} checked={r.menos === adj}
                       onChange={() => setResp({ ...resp, [q.numero]: { ...r, menos: adj,
                         mais: r.mais === adj ? undefined : r.mais } })} />
              </div>
            ))}
          </div>
          {!completa && (r.mais || r.menos) && (
            <div className="teste-aviso-suave">
              Falta marcar {r.mais ? 'a palavra que MENOS tem a ver (coluna da direita)'
                : 'a palavra que MAIS tem a ver (coluna da esquerda)'} para continuar.
            </div>
          )}
        </>
      ) : (
        <div className="teste-corpo">
          <p className="teste-situacao">{q.situacao}</p>
          {q.opcoes.map((op) => (
            <label key={op} className={`teste-opcao-sit ${r.escolha === op ? 'marcada' : ''}`}>
              <input type="radio" name={`sit-${q.numero}`} checked={r.escolha === op}
                     onChange={() => setResp({ ...resp, [q.numero]: { escolha: op } })} />
              <span>{op}</span>
            </label>
          ))}
        </div>
      )}
      {erro && <div className="alerta" style={{ margin: '0 1rem' }}>{erro}</div>}
      <div className="teste-rodape">
        <span className="teste-timer">🕐 {mmss}</span>
        <button className="btn-principal btn-mini" disabled={!completa || enviando} onClick={proximo}>
          {ultima ? 'Concluir' : 'Próximo »'}</button>
      </div>
    </div>
  )
}
