import { useEffect, useState } from 'react'
import { creche as api } from './api.js'
import { fmtTelefone } from './fmt.js'
import logo from './assets/logo.png'

// Link público único do levantamento do Reembolso-Creche (IN SEGES/MGI 147/2026).
// Etapas: CPF -> código 2FA (e-mail) -> conferir dados -> crianças + certidão -> enviar.
// Quem não tem e-mail cadastrado: CPF -> verificar identidade (KBA) -> cadastrar
// e-mail -> código 2FA. A resposta do /iniciar nunca revela se o CPF é da base.
export default function CrecheLink() {
  const [etapa, setEtapa] = useState('cpf') // cpf | codigo | kba | sessao | enviado
  const [cpf, setCpf] = useState('')
  const [codigo, setCodigo] = useState('')
  const [token, setToken] = useState(null)
  const [erro, setErro] = useState(null)
  const [carregando, setCarregando] = useState(false)

  const iniciar = async (e) => {
    e.preventDefault(); setErro(null); setCarregando(true)
    try {
      await api.iniciar(cpf)
      setEtapa('codigo')
    } catch (err) {
      setErro(err.detail === 'cpf_invalido' ? 'CPF inválido. Confira os números.'
        : 'Não foi possível iniciar. Tente novamente em instantes.')
    } finally { setCarregando(false) }
  }

  const confirmar = async (e) => {
    e.preventDefault(); setErro(null); setCarregando(true)
    try {
      const r = await api.confirmar(cpf, codigo)
      setToken(r.token); setEtapa('sessao')
    } catch (err) {
      setErro(err.detail === 'codigo_invalido'
        ? 'Código incorreto ou expirado. Confira no seu e-mail (inclusive o spam).'
        : 'Não foi possível confirmar. Tente novamente.')
    } finally { setCarregando(false) }
  }

  return (
    <main className="creche-publico">
      <header className="creche-topo">
        <img src={logo} alt="Green House" className="logo-img" />
        <h1>Reembolso-Creche</h1>
        <p className="creche-sub">Levantamento para análise de elegibilidade ao benefício, nos termos
          da <strong>Instrução Normativa SEGES/MGI nº 147/2026</strong>.</p>
      </header>

      {etapa === 'cpf' && (
        <form className="rh-card creche-card" onSubmit={iniciar}>
          <h2>Vamos começar</h2>
          <p className="explica">Informe seu CPF para localizarmos seu cadastro. Enviaremos um código
            de confirmação ao seu e-mail.</p>
          <label className="campo"><span className="rotulo">CPF</span>
            <input inputMode="numeric" placeholder="000.000.000-00" value={cpf} autoFocus
                   onChange={(e) => setCpf(e.target.value)} /></label>
          {erro && <div className="alerta">{erro}</div>}
          <button className="btn-principal" disabled={carregando}>
            {carregando ? 'Enviando…' : 'Enviar código'}</button>
        </form>
      )}

      {etapa === 'codigo' && (
        <form className="rh-card creche-card" onSubmit={confirmar}>
          <h2>Digite o código</h2>
          <p className="explica">Enviamos um código de 6 dígitos ao seu e-mail. <strong>Verifique também
            a caixa de spam</strong> — às vezes a mensagem vai para lá.</p>
          <label className="campo"><span className="rotulo">Código de confirmação</span>
            <input inputMode="numeric" maxLength={6} placeholder="000000" value={codigo} autoFocus
                   style={{ letterSpacing: '.4em', textAlign: 'center', fontSize: '1.4rem' }}
                   onChange={(e) => setCodigo(e.target.value.replace(/\D/g, ''))} /></label>
          {erro && <div className="alerta">{erro}</div>}
          <button className="btn-principal" disabled={carregando || codigo.length < 6}>
            {carregando ? 'Confirmando…' : 'Confirmar'}</button>
          <button type="button" className="btn-link"
                  onClick={() => { setEtapa('kba'); setErro(null) }}>
            Não recebi o código / não tenho e-mail cadastrado</button>
          <button type="button" className="btn-link" onClick={() => { setEtapa('cpf'); setCodigo('') }}>
            ← voltar</button>
        </form>
      )}

      {etapa === 'kba' && (
        <VerificarIdentidade cpf={cpf}
          aoConcluir={() => { setEtapa('codigo'); setErro(null) }}
          aoVoltar={() => { setEtapa('codigo'); setErro(null) }} />
      )}

      {etapa === 'sessao' && token && (
        <SessaoCreche token={token} aoEnviar={() => setEtapa('enviado')} />
      )}

      {etapa === 'enviado' && (
        <div className="rh-card creche-card centro">
          <div style={{ fontSize: '3rem' }}>✅</div>
          <h2>Levantamento enviado!</h2>
          <p className="explica">Recebemos suas informações. O RH vai analisar a elegibilidade ao
            benefício e, se aprovado, você receberá as orientações por e-mail. Obrigado!</p>
        </div>
      )}

      <p className="portal-rodape">Dados tratados segundo a LGPD, exclusivamente para análise,
        concessão e fiscalização do reembolso-creche (IN SEGES/MGI nº 147/2026).</p>
    </main>
  )
}

// Verificação de identidade (KBA) para quem não tem e-mail cadastrado: responde
// perguntas que só a própria pessoa saberia, cadastra o e-mail e recebe o código.
// A resposta uniforme do backend (mesmo p/ CPF fora da base) evita enumeração.
function VerificarIdentidade({ cpf, aoConcluir, aoVoltar }) {
  const [fase, setFase] = useState('carregando') // carregando | perguntas | email
  const [desafio, setDesafio] = useState(null)
  const [perguntas, setPerguntas] = useState([])
  const [respostas, setRespostas] = useState({})
  const [autorizacao, setAutorizacao] = useState(null)
  const [email, setEmail] = useState('')
  const [erro, setErro] = useState(null)
  const [carregando, setCarregando] = useState(false)

  useEffect(() => {
    api.kbaIniciar(cpf)
      .then((r) => { setDesafio(r.desafio); setPerguntas(r.perguntas); setFase('perguntas') })
      .catch((err) => setErro(err.detail === 'cpf_invalido' ? 'CPF inválido. Confira os números.'
        : err.detail === 'muitas_tentativas' ? 'Muitas tentativas. Aguarde alguns minutos.'
        : 'Não foi possível iniciar a verificação. Tente novamente.'))
  }, [cpf])

  const responder = async (e) => {
    e.preventDefault(); setErro(null); setCarregando(true)
    try {
      const r = await api.kbaResponder(desafio, respostas)
      setAutorizacao(r.autorizacao); setFase('email')
    } catch (err) {
      setErro(err.detail === 'nao_confirmado'
        ? 'Não foi possível confirmar sua identidade com essas respostas. Confira e tente de novo.'
        : err.detail === 'desafio_expirado' ? 'A verificação expirou. Recomece.'
        : err.detail === 'muitas_tentativas' ? 'Muitas tentativas. Aguarde alguns minutos.'
        : 'Não foi possível verificar. Tente novamente.')
    } finally { setCarregando(false) }
  }

  const definirEmail = async (e) => {
    e.preventDefault(); setErro(null); setCarregando(true)
    try {
      await api.kbaDefinirEmail(autorizacao, email)
      aoConcluir()  // volta ao passo do código — já enviado ao novo e-mail
    } catch (err) {
      setErro(err.detail === 'email_invalido' ? 'E-mail inválido. Confira o endereço.'
        : err.detail === 'autorizacao_expirada' ? 'A verificação expirou. Recomece.'
        : 'Não foi possível cadastrar o e-mail. Tente novamente.')
    } finally { setCarregando(false) }
  }

  if (fase === 'carregando') return (
    <div className="rh-card creche-card"><p>Preparando a verificação…</p>
      {erro && <><div className="alerta">{erro}</div>
        <button className="btn-link" onClick={aoVoltar}>← voltar</button></>}</div>
  )

  if (fase === 'email') return (
    <form className="rh-card creche-card" onSubmit={definirEmail}>
      <h2>Cadastre seu e-mail</h2>
      <p className="explica">Identidade confirmada! Informe um e-mail válido — enviaremos o código
        de confirmação para ele e usaremos esse e-mail no seu benefício.</p>
      <label className="campo"><span className="rotulo">Seu e-mail</span>
        <input type="email" placeholder="voce@exemplo.com" value={email} autoFocus
               onChange={(ev) => setEmail(ev.target.value)} /></label>
      {erro && <div className="alerta">{erro}</div>}
      <button className="btn-principal" disabled={carregando || !email.trim()}>
        {carregando ? 'Enviando…' : 'Cadastrar e receber código'}</button>
    </form>
  )

  return (
    <form className="rh-card creche-card" onSubmit={responder}>
      <h2>Confirme sua identidade</h2>
      <p className="explica">Responda às perguntas abaixo para confirmarmos que é você. São dados que
        só você conhece.</p>
      {perguntas.map((p) => (
        <label className="campo" key={p.codigo}><span className="rotulo">{p.pergunta}</span>
          <input value={respostas[p.codigo] || ''}
                 onChange={(ev) => setRespostas({ ...respostas, [p.codigo]: ev.target.value })} /></label>
      ))}
      {erro && <div className="alerta">{erro}</div>}
      <button className="btn-principal"
              disabled={carregando || perguntas.some((p) => !(respostas[p.codigo] || '').trim())}>
        {carregando ? 'Verificando…' : 'Confirmar identidade'}</button>
      <button type="button" className="btn-link" onClick={aoVoltar}>← voltar</button>
    </form>
  )
}

function SessaoCreche({ token, aoEnviar }) {
  const [dados, setDados] = useState(null)
  const [erro, setErro] = useState(null)
  const [enviando, setEnviando] = useState(false)
  // form de nova criança
  const [nova, setNova] = useState({ nome: '', data_nascimento: '', parentesco: 'filho', tipo_comprovante: 'declaracao' })

  const recarregar = () => api.sessao(token).then(setDados).catch(() => setErro('Sessão expirada. Recomece pelo CPF.'))
  useEffect(() => { recarregar() }, [])

  const addCrianca = async () => {
    if (!nova.nome.trim() || !nova.data_nascimento.trim()) {
      setErro('Informe nome e data de nascimento da criança.'); return }
    setErro(null)
    try { await api.addCrianca(token, nova); setNova({ nome: '', data_nascimento: '', parentesco: 'filho', tipo_comprovante: 'declaracao' }); recarregar() }
    catch { setErro('Não foi possível adicionar. Tente de novo.') }
  }
  const subir = async (criancaId, tipo, arquivo) => {
    if (!arquivo) return
    setErro(null)
    try { await api.subirDocumento(token, criancaId, tipo, arquivo); recarregar() }
    catch (e) { setErro(`Falha ao enviar o arquivo (${e.detail || e.message}).`) }
  }
  const enviar = async () => {
    setErro(null); setEnviando(true)
    try { await api.enviar(token); aoEnviar() }
    catch (e) {
      setErro(e.detail?.erro === 'certidao_faltando'
        ? `Falta a certidão de nascimento de: ${e.detail.criancas.join(', ')}.`
        : e.detail === 'sem_criancas' ? 'Cadastre ao menos uma criança.'
        : 'Não foi possível enviar. Confira os dados.')
    } finally { setEnviando(false) }
  }
  const semDireito = async () => {
    if (!window.confirm('Confirmar que você NÃO tem filhos ou dependentes de até 5 anos '
      + 'que dão direito ao reembolso-creche?\n\nIsto encerra o levantamento sem pedido.')) return
    setErro(null); setEnviando(true)
    try { await api.crecheSemDireito(token); aoEnviar() }
    catch { setErro('Não foi possível registrar. Tente de novo.') }
    finally { setEnviando(false) }
  }

  if (!dados) return <div className="rh-card creche-card"><p>Carregando…</p></div>
  if (dados.status !== 'levantamento') {
    return <AposEnvio token={token} status={dados.status} />
  }

  return (
    <div className="creche-sessao">
      {dados.motivo_devolucao && (
        <div className="alerta" style={{ borderColor: '#e9a63a', background: '#fff8ec', color: '#7a5b1a' }}>
          <strong>Seu pedido foi devolvido para correção.</strong><br />
          Motivo do RH: <em>{dados.motivo_devolucao}</em><br />
          Corrija o que for necessário abaixo e reenvie.
        </div>
      )}
      <div className="rh-card creche-card">
        <h2>Confira seus dados</h2>
        <p className="explica">Puxamos do seu cadastro. Confira e, se algo mudou, atualize.</p>
        <div className="creche-dados">
          <div><span className="rotulo">Nome</span><strong>{dados.nome_completo}</strong></div>
          <div><span className="rotulo">CPF</span><strong>{dados.cpf}</strong></div>
          <label className="campo"><span className="rotulo">E-mail</span>
            <input type="email" defaultValue={dados.email || ''}
                   onBlur={(e) => api.conferirDados(token, { email: e.target.value })} /></label>
          <label className="campo"><span className="rotulo">Telefone / WhatsApp</span>
            <input inputMode="tel" placeholder="(61) 99999-8888"
                   defaultValue={fmtTelefone(dados.telefone)}
                   onInput={(e) => { e.target.value = fmtTelefone(e.target.value) }}
                   onBlur={(e) => api.conferirDados(token, { telefone: e.target.value })} /></label>
        </div>
      </div>

      <div className="rh-card creche-card">
        <h2>Crianças</h2>
        <p className="explica">Cadastre cada filho(a), enteado(a) ou criança sob sua guarda judicial, e
          anexe a <strong>certidão de nascimento</strong> (obrigatória) — e o documento de guarda, quando
          for o caso.</p>

        {(dados.criancas || []).map((c) => (
          <div key={c.id} className="creche-crianca">
            <div className="creche-crianca-topo">
              <strong>{c.nome}</strong>
              <span className="explica" style={{ margin: 0 }}>{c.parentesco} · nasc. {c.data_nascimento}</span>
              <button className="btn-link" onClick={() => api.delCrianca(token, c.id).then(recarregar)}>remover</button>
            </div>
            <div className="creche-docs">
              <label className={`creche-doc ${c.tem_certidao ? 'ok' : ''}`}>
                {c.tem_certidao ? '✅ Certidão enviada' : '📎 Enviar certidão de nascimento'}
                <input type="file" hidden accept="image/*,.pdf"
                       onChange={(e) => subir(c.id, 'certidao', e.target.files?.[0])} />
              </label>
              <label className={`creche-doc ${c.tem_guarda ? 'ok' : ''}`}>
                {c.tem_guarda ? '✅ Guarda enviada' : '📎 Guarda judicial (se aplicável)'}
                <input type="file" hidden accept="image/*,.pdf"
                       onChange={(e) => subir(c.id, 'guarda', e.target.files?.[0])} />
              </label>
            </div>
          </div>
        ))}

        <div className="creche-nova">
          <div className="linha3">
            <label className="campo"><span className="rotulo">Nome da criança</span>
              <input value={nova.nome} onChange={(e) => setNova({ ...nova, nome: e.target.value })} /></label>
            <label className="campo"><span className="rotulo">Data de nascimento</span>
              <input placeholder="dd/mm/aaaa" value={nova.data_nascimento}
                     onChange={(e) => setNova({ ...nova, data_nascimento: e.target.value })} /></label>
            <label className="campo"><span className="rotulo">Vínculo</span>
              <select value={nova.parentesco} onChange={(e) => setNova({ ...nova, parentesco: e.target.value })}>
                <option value="filho">Filho(a)</option>
                <option value="enteado">Enteado(a)</option>
                <option value="guarda">Guarda judicial</option>
              </select></label>
          </div>
          <button className="btn-secundario" onClick={addCrianca}>+ Adicionar criança</button>
        </div>
      </div>

      {erro && <div className="alerta">{erro}</div>}
      <button className="btn-principal creche-enviar" disabled={enviando || !(dados.criancas || []).length}
              onClick={enviar}>
        {enviando ? 'Enviando…' : 'Enviar levantamento'}</button>
      <p className="explica centro" style={{ marginTop: '.8rem' }}>
        Não tem filhos ou dependentes de até 5 anos?{' '}
        <button className="btn-link" onClick={semDireito} disabled={enviando}>
          Declarar que não tenho direito ao benefício</button>
      </p>
    </div>
  )
}

// Tela pós-envio: mostra o andamento e, quando o RH aprova, libera a assinatura
// do requerimento pela plataforma (o colaborador já está autenticado por 2FA).
function AposEnvio({ token, status }) {
  const [req, setReq] = useState(undefined) // undefined=carregando, null=indisponível
  const [erro, setErro] = useState(null)
  const [assinando, setAssinando] = useState(false)

  const recarregar = () => api.requerimentoStatus(token)
    .then((r) => setReq(r.disponivel ? r : null)).catch(() => setReq(null))
  useEffect(() => { recarregar() }, [])

  const assinar = async () => {
    setErro(null); setAssinando(true)
    try { await api.assinarRequerimento(token); await recarregar() }
    catch (e) {
      setErro(e.detail === 'ja_assinado' ? 'Você já assinou este requerimento.'
        : e.detail === 'fora_da_vez' ? 'Aguarde: o requerimento ainda não está liberado para sua assinatura.'
        : `Não foi possível assinar (${e.detail || e.message}).`)
    } finally { setAssinando(false) }
  }

  if (req && req.disponivel && !req.assinado && req.na_vez) {
    return (
      <div className="rh-card creche-card centro">
        <div style={{ fontSize: '2.5rem' }}>✍️</div>
        <h2>Assine seu requerimento</h2>
        <p className="explica">Seu benefício foi <strong>aprovado</strong>! Para concluir, assine
          eletronicamente o requerimento de Reembolso-Creche. Sua identidade já foi confirmada por
          código no e-mail (Lei nº 14.063/2020).</p>
        {erro && <div className="alerta">{erro}</div>}
        <button className="btn-principal" disabled={assinando} onClick={assinar}>
          {assinando ? 'Assinando…' : 'Assinar requerimento'}</button>
      </div>
    )
  }
  if (req && req.assinado) {
    return (
      <div className="rh-card creche-card centro">
        <div style={{ fontSize: '3rem' }}>✅</div>
        <h2>Requerimento assinado!</h2>
        <p className="explica">{req.concluido
          ? 'O documento foi assinado por todas as partes. Obrigado!'
          : 'Recebemos sua assinatura. O RH vai finalizar a assinatura institucional.'}</p>
      </div>
    )
  }
  const indeferido = status === 'indeferido'
  return (
    <div className="rh-card creche-card centro">
      <div style={{ fontSize: '3rem' }}>{indeferido ? '📋' : '🎉'}</div>
      <h2>{indeferido ? 'Pedido analisado' : 'Você já enviou'}</h2>
      <p className="explica">{indeferido
        ? 'Seu pedido foi analisado pelo RH. Em caso de dúvida, procure o RH.'
        : 'Seu levantamento está em análise. Aguarde o retorno do RH por e-mail.'}</p>
    </div>
  )
}
