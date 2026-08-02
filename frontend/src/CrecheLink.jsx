import { useEffect, useState } from 'react'
import { creche as api } from './api.js'
import { fmtTelefone } from './fmt.js'
import InputData from './InputData.jsx'
import logo from './assets/logo.png'
import SelectBusca from './SelectBusca.jsx'

// Link público único do levantamento do Reembolso-Creche (IN SEGES/MGI 147/2026).
// Etapas: CPF -> código 2FA (e-mail) -> conferir dados -> crianças + certidão -> enviar.
// Quem não tem e-mail cadastrado: CPF -> verificar identidade (KBA) -> cadastrar
// e-mail -> código 2FA. A resposta do /iniciar nunca revela se o CPF é da base.
export default function CrecheLink() {
  // ?t=<token> tem DOIS usos (v2.03):
  // 1. e-mail de devolução (v1.82): o RH devolveu para correção, o e-mail já é
  //    comprovado, então entra direto — o backend nasce com confirmado_em.
  // 2. e-mail do CÓDIGO: o link identifica quem é, mas NÃO autentica — a pessoa
  //    volta por ele depois de sair para ler o código (o app de e-mail abre o
  //    site numa janela que morre ao trocar de tela) e só precisa digitar o
  //    código, sem recomeçar do CPF.
  // Quem manda é o `pode_entrar` do backend, não o front.
  const tokenUrl = new URLSearchParams(window.location.search).get('t')
  const [etapa, setEtapa] = useState(tokenUrl ? 'retomando' : 'cpf') // cpf | codigo | kba | sessao | enviado | retomando
  const [cpf, setCpf] = useState('')
  const [codigo, setCodigo] = useState('')
  const [token, setToken] = useState(null)
  const [retomada, setRetomada] = useState(null) // {primeiro_nome, cpf_final}
  const [erro, setErro] = useState(null)
  const [carregando, setCarregando] = useState(false)

  // Resolve o ?t= no backend. O token NÃO fica na barra de endereço depois de
  // usado (histórico, print, ombro do colega), mas só limpamos DEPOIS de saber
  // o que ele é — antes, apagar a URL era o que impedia o botão "voltar" de
  // recuperar a tentativa.
  useEffect(() => {
    if (!tokenUrl) return
    let vivo = true
    ;(async () => {
      try {
        const r = await api.retomar(tokenUrl)
        if (!vivo) return
        setRetomada(r)
        if (r.pode_entrar) { setToken(tokenUrl); setEtapa('sessao') }
        // Link vivo NÃO entra sozinho: quem abre o link primeiro, numa empresa
        // com Microsoft 365, é o Defender/Safe Links — e a entrada automática
        // fazia o scanner gastar o acesso da pessoa (incidente 2026-07-30).
        // Agora ela vê "é você? entrar" e o POST do clique é que consome.
        else if (r.pode_entrar_pelo_link) setEtapa('entrar')
        else setEtapa('codigo')
      } catch {
        if (!vivo) return
        // link vencido/desconhecido cai na entrada normal, nunca em tela morta
        setEtapa('cpf')
        setErro('Esse link expirou. Informe seu CPF para receber um novo código.')
      } finally {
        if (vivo) window.history.replaceState({}, '', window.location.pathname)
      }
    })()
    return () => { vivo = false }
  }, [])

  // O clique que consome o link. Se ele já tiver sido gasto, cai no código —
  // nunca em tela morta.
  const entrarPeloLink = async () => {
    setErro(null); setCarregando(true)
    try {
      const r = await api.entrarPeloLink(tokenUrl)
      setToken(r.token); setEtapa('sessao')
    } catch {
      setErro('Este link já foi usado. Digite o código que enviamos por e-mail.')
      setEtapa('codigo')
    } finally { setCarregando(false) }
  }

  const iniciar = async (e) => {
    e.preventDefault(); setErro(null); setCarregando(true)
    try {
      await api.iniciar(cpf)
      setEtapa('codigo')
    } catch (err) {
      // NÃO avança para a tela do código quando o envio falhou (feedback
      // 2026-07-29): antes, o 429 do limite de tentativas caía no genérico e a
      // tela mudava de etapa assim mesmo — a pessoa colava o código do e-mail
      // ANTERIOR e recebia "código incorreto", sem nunca saber que o e-mail
      // novo não tinha saído. É a mesma armadilha do "sucesso mentiroso".
      setErro(err.status === 429
        ? 'Você pediu o código várias vezes seguidas. Por segurança, aguarde '
          + '15 minutos e tente de novo — ou use o último código que chegou, '
          + 'se ainda estiver dentro dos 15 minutos.'
        : err.detail === 'cpf_invalido' ? 'CPF inválido. Confira os números.'
          : 'Não conseguimos enviar o código agora. Tente novamente em instantes.')
    } finally { setCarregando(false) }
  }

  const confirmar = async (e) => {
    e.preventDefault(); setErro(null); setCarregando(true)
    try {
      // Quem chegou pelo link do e-mail não digitou o CPF nesta tela — o
      // backend reconhece o token e devolve o CPF por ele.
      const r = await api.confirmar(cpf, codigo, tokenUrl || undefined)
      setToken(r.token); setEtapa('sessao')
    } catch (err) {
      // Desde 2026-07-30 QUALQUER código dentro dos 15 minutos vale — pedir um
      // novo não invalida mais o que já chegou. Então a orientação deixou de
      // ser "use o mais recente" (que mandava a pessoa desprezar um código
      // válido) e passou a ser sobre o PRAZO, que é o que de fato expira.
      setErro(err.status === 429
        ? 'Muitas tentativas seguidas. Aguarde alguns minutos e tente de novo.'
        : err.detail === 'codigo_invalido'
          ? 'Esse código não confere. Ele vale por 15 minutos — confira se '
            + 'digitou os 6 dígitos como estão no e-mail, ou toque em "Reenviar '
            + 'o código" abaixo para receber outro.'
          : 'Não foi possível confirmar. Tente novamente.')
    } finally { setCarregando(false) }
  }

  // Reenviar sem voltar para a tela do CPF (a pessoa já digitou; fazer de novo
  // é atrito). O backend recusa com 429 se for pedido demais, e a mensagem
  // diz isso em vez de fingir que enviou.
  const reenviar = async () => {
    setErro(null); setCarregando(true)
    try {
      await api.iniciar(cpf)
      setCodigo('')
      setErro('Enviamos um código novo. Use o do e-mail mais recente '
            + '(confira também o spam).')
    } catch (err) {
      setErro(err.status === 429
        ? 'Você já pediu o código várias vezes. Aguarde 15 minutos — ou use o '
          + 'último código que chegou, se ainda estiver válido.'
        : 'Não conseguimos reenviar agora. Tente em instantes.')
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

      {etapa === 'retomando' && (
        <div className="rh-card creche-card centro">
          <p className="explica">Um instante — estamos reconhecendo o seu link…</p>
        </div>
      )}

      {/* Um clique separa o link de virar sessão. Parece um passo a mais e é o
          que faz o link CHEGAR: o antivírus de e-mail abre o endereço para
          escanear, mas não aperta botão. */}
      {etapa === 'entrar' && (
        <div className="rh-card creche-card">
          <h2>É você?</h2>
          <p className="explica">Reconhecemos o seu link.
            {retomada?.primeiro_nome ? <> Você é <strong>{retomada.primeiro_nome}</strong>,</> : ' É o CPF'}
            {' '}terminado em <strong>{retomada?.cpf_final}</strong>.</p>
          {erro && <div className="alerta">{erro}</div>}
          <button className="btn-principal" disabled={carregando} onClick={entrarPeloLink}>
            {carregando ? 'Entrando…' : 'Sim, entrar'}</button>
          <button type="button" className="btn-link" disabled={carregando}
                  onClick={() => { setErro(null); setEtapa('codigo') }}>
            Prefiro digitar o código do e-mail</button>
        </div>
      )}

      {etapa === 'codigo' && (
        <form className="rh-card creche-card" onSubmit={confirmar}>
          <h2>Digite o código</h2>
          {retomada ? (
            <p className="explica">Bem-vindo de volta, <strong>{retomada.primeiro_nome}</strong>!
              Enviamos um código de 6 dígitos para o e-mail do CPF terminado em
              {' '}<strong>{retomada.cpf_final}</strong>. <strong>Verifique também a caixa de
              spam</strong>. Se precisar sair para ler o código, volte por este mesmo link
              do e-mail — você não perde o que já fez.</p>
          ) : (
            <p className="explica">Enviamos um código de 6 dígitos ao seu e-mail. <strong>Verifique também
              a caixa de spam</strong> — às vezes a mensagem vai para lá.</p>
          )}
          <label className="campo"><span className="rotulo">Código de confirmação</span>
            <input inputMode="numeric" maxLength={6} placeholder="000000" value={codigo} autoFocus
                   style={{ letterSpacing: '.4em', textAlign: 'center', fontSize: '1.4rem' }}
                   onChange={(e) => setCodigo(e.target.value.replace(/\D/g, ''))} /></label>
          {erro && <div className="alerta">{erro}</div>}
          <button className="btn-principal" disabled={carregando || codigo.length < 6}>
            {carregando ? 'Confirmando…' : 'Confirmar'}</button>
          {cpf && (
            <button type="button" className="btn-link" disabled={carregando}
                    onClick={reenviar}>🔄 Reenviar o código</button>)}
          {/* A KBA precisa do CPF digitado; quem entrou pelo link não digitou
              (só temos os 4 últimos dígitos), então o caminho é informar o CPF. */}
          <button type="button" className="btn-link"
                  onClick={() => { setErro(null); setEtapa(cpf ? 'kba' : 'cpf') }}>
            Não recebi o código / não tenho e-mail cadastrado</button>
          <button type="button" className="btn-link"
                  onClick={() => { setEtapa('cpf'); setCodigo(''); setRetomada(null) }}>
            ← informar outro CPF</button>
        </form>
      )}

      {etapa === 'kba' && (
        <VerificarIdentidade cpf={cpf}
          aoConcluir={() => { setEtapa('codigo'); setErro(null) }}
          aoVoltar={() => { setEtapa('codigo'); setErro(null) }} />
      )}

      {etapa === 'sessao' && token && (
        // `aoEnviar` recebe o QUE aconteceu: quem declarou não ter criança não
        // pode ler "se aprovado, você receberá as orientações" (v2.34) — não
        // há pedido a aprovar, e a mensagem faria a pessoa esperar por um
        // e-mail que nunca vem.
        <SessaoCreche token={token}
                      aoEnviar={(tipo) => setEtapa(tipo === 'sem_direito' ? 'declarado' : 'enviado')}
                      aoExpirar={() => { setToken(null); setEtapa('cpf') }} />
      )}

      {etapa === 'enviado' && (
        <div className="rh-card creche-card centro">
          <div style={{ fontSize: '3rem' }}>✅</div>
          <h2>Levantamento enviado!</h2>
          <p className="explica">Recebemos suas informações. O RH vai analisar a elegibilidade ao
            benefício e, se aprovado, você receberá as orientações por e-mail. Obrigado!</p>
        </div>
      )}

      {etapa === 'declarado' && (
        <div className="rh-card creche-card centro">
          <div style={{ fontSize: '3rem' }}>📄</div>
          <h2>Resposta registrada</h2>
          <p className="explica">Você declarou que <strong>não tem</strong> criança de até 5 anos
            e 11 meses. Obrigado por responder — fica registrado que você foi consultado(a).</p>
          <p className="explica">Se isso mudar (nascimento, adoção ou guarda), procure o RH: o
            levantamento pode ser reaberto a qualquer momento.</p>
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
//
// EXPORTADO e parametrizável (v1.83): o portal do colaborador (/meu) usa o
// MESMO componente com as rotas dele — as três funções de API entram por prop
// em vez de virem fixas do módulo de creche. Sem props, cai no creche (as
// chamadas existentes não mudam).
export function VerificarIdentidade({ cpf, aoConcluir, aoVoltar,
                                      kbaIniciar, kbaResponder, kbaDefinirEmail,
                                      textoEmail }) {
  const iniciarKba = kbaIniciar || api.kbaIniciar
  const responderKba = kbaResponder || api.kbaResponder
  const definirEmailKba = kbaDefinirEmail || api.kbaDefinirEmail
  const [fase, setFase] = useState('carregando') // carregando | perguntas | email
  const [desafio, setDesafio] = useState(null)
  const [perguntas, setPerguntas] = useState([])
  const [respostas, setRespostas] = useState({})
  const [autorizacao, setAutorizacao] = useState(null)
  const [email, setEmail] = useState('')
  const [erro, setErro] = useState(null)
  const [carregando, setCarregando] = useState(false)

  useEffect(() => {
    iniciarKba(cpf)
      .then((r) => { setDesafio(r.desafio); setPerguntas(r.perguntas); setFase('perguntas') })
      .catch((err) => setErro(err.detail === 'cpf_invalido' ? 'CPF inválido. Confira os números.'
        : err.detail === 'muitas_tentativas' ? 'Muitas tentativas. Aguarde alguns minutos.'
        : 'Não foi possível iniciar a verificação. Tente novamente.'))
  }, [cpf])

  const responder = async (e) => {
    e.preventDefault(); setErro(null); setCarregando(true)
    try {
      const r = await responderKba(desafio, respostas)
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
      await definirEmailKba(autorizacao, email)
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
        de confirmação para ele e {textoEmail || 'usaremos esse e-mail no seu benefício'}.</p>
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

function SessaoCreche({ token, aoEnviar, aoExpirar }) {
  const [dados, setDados] = useState(null)
  const [erro, setErro] = useState(null)
  const [enviando, setEnviando] = useState(false)
  // form de nova criança
  const [nova, setNova] = useState({ nome: '', data_nascimento: '', parentesco: 'filho', tipo_comprovante: 'declaracao' })
  // 'tenho' | 'nao_tenho' | null — a manifestação do colaborador (v2.34).
  // Começa NULA de propósito: a pessoa tem que escolher, e não encontrar um
  // formulário já aberto que ela ignora se não lhe disser respeito.
  const [resposta, setResposta] = useState(null)

  // Link do e-mail vencido (7 dias) cai aqui: em vez de tela morta, volta ao
  // CPF — o caminho normal com 2FA continua valendo.
  const recarregar = () => api.sessao(token).then((d) => {
    setDados(d)
    // Quem JÁ tem criança cadastrada (ou voltou de uma devolução) não pode
    // cair na pergunta zerada: ele já respondeu na prática, e obrigá-lo a
    // responder de novo esconderia o trabalho que ele já fez.
    if ((d.criancas || []).length) setResposta('tenho')
  }).catch(() => {
    setErro('Este link expirou. Entre com seu CPF para continuar.')
    if (aoExpirar) aoExpirar()
  })
  useEffect(() => { recarregar() }, [])

  const addCrianca = async () => {
    if (!nova.nome.trim() || !nova.data_nascimento.trim()) {
      setErro('Informe nome e data de nascimento da criança.'); return }
    setErro(null)
    try { await api.addCrianca(token, nova); setNova({ nome: '', data_nascimento: '', parentesco: 'filho', tipo_comprovante: 'declaracao' }); recarregar() }
    catch (e) {
      // A mensagem tem que dizer o que RESOLVE. O `catch` cego mandava "tente
      // de novo" para uma data recusada — e tentar de novo com a mesma data
      // falha de novo. O caso que originou isto (2026-08-02) foi o nascimento
      // do próprio colaborador digitado no campo do filho, provavelmente
      // oferecido pelo preenchimento automático do navegador.
      const M = {
        data_de_adulto: 'Essa data de nascimento dá idade de adulto — confira se não é a sua própria data. Use a data que está na certidão da criança.',
        data_no_futuro: 'A data de nascimento não pode ser no futuro.',
        data_invalida: 'Não consegui entender essa data de nascimento. Confira o dia, o mês e o ano.',
      }
      setErro(M[e.detail] || 'Não foi possível adicionar. Tente de novo.')
    }
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
  // A confirmação já está NA TELA (o texto da declaração + o botão), então não
  // há `window.confirm` aqui: um alerta do navegador em cima de um texto que a
  // pessoa acabou de ler é ruído, não segurança.
  const semDireito = async () => {
    setErro(null); setEnviando(true)
    try { await api.crecheSemDireito(token); aoEnviar('sem_direito') }
    catch (e) {
      setErro(e.detail === 'ha_criancas_cadastradas'
        ? 'Você já cadastrou uma criança abaixo. Remova-a antes de declarar que não tem.'
        : 'Não foi possível registrar. Tente de novo.')
    } finally { setEnviando(false) }
  }

  const temCriancas = (dados?.criancas || []).length > 0

  if (!dados) return <div className="rh-card creche-card"><p>Carregando…</p></div>
  if (dados.status !== 'levantamento') {
    return <AposEnvio token={token} status={dados.status}
                      motivoIndeferimento={dados.motivo_indeferimento} />
  }

  return (
    <div className="creche-sessao">
      {dados.motivo_devolucao && (
        <div className="aviso-inline">
          <strong>Seu pedido foi devolvido para correção.</strong><br />
          Motivo do RH: <em>{dados.motivo_devolucao}</em><br />
          Corrija o que for necessário abaixo e reenvie.
        </div>
      )}
      {/* A PERGUNTA vem primeiro (v2.34, pedido do Bruno): "que a pessoa
          manifeste que de fato tem ou não tem crianças, e não simplesmente
          entre no link e, como não tem, não faça nada e saia". Antes, quem não
          tinha filho abria a tela, via um formulário que não lhe dizia
          respeito e ia embora — e "não respondeu" ficava igual a "não tem
          direito" na planilha do RH. */}
      <div className="rh-card creche-card">
        <h2>Você tem criança que dá direito ao benefício?</h2>
        <p className="explica">O reembolso-creche vale para filho(a), enteado(a) ou criança sob
          sua guarda judicial <strong>de até 5 anos e 11 meses</strong>. Responda abaixo — mesmo
          que a resposta seja "não", a sua manifestação fica registrada.</p>
        <div className="creche-escolha">
          <button type="button"
                  className={resposta === 'tenho' ? 'btn-principal' : 'btn-secundario'}
                  onClick={() => setResposta('tenho')}>
            ✅ Sim, tenho — quero solicitar</button>
          <button type="button"
                  className={resposta === 'nao_tenho' ? 'btn-principal' : 'btn-secundario'}
                  disabled={temCriancas}
                  title={temCriancas
                    ? 'Você já cadastrou uma criança abaixo — remova-a antes de declarar que não tem.'
                    : undefined}
                  onClick={() => setResposta('nao_tenho')}>
            🚫 Não tenho criança nessa idade</button>
        </div>
        {resposta === 'nao_tenho' && (
          <div className="creche-declaracao">
            <p className="explica">Você declara que <strong>não possui</strong> filho(a),
              enteado(a) ou criança sob guarda de até 5 anos e 11 meses. O levantamento é
              encerrado sem pedido, e fica registrado que você foi consultado(a) e respondeu.</p>
            <p className="explica"><strong>Isso não é definitivo.</strong> Se você passar a ter
              uma criança nessa idade, procure o RH — o pedido pode ser reaberto a qualquer
              momento.</p>
            {erro && <div className="alerta">{erro}</div>}
            <button className="btn-principal" disabled={enviando} onClick={semDireito}>
              {enviando ? 'Registrando…' : 'Confirmar que não tenho'}</button>
            <button type="button" className="btn-link" disabled={enviando}
                    onClick={() => setResposta(null)}>← voltar</button>
          </div>
        )}
      </div>

      {resposta !== 'tenho' ? null : (<>
      <div className="rh-card creche-card">
        <h2>Seus dados de contato</h2>
        <p className="explica">Confira o que já temos e <strong>complete o que estiver em branco</strong>.
          O <strong>e-mail</strong> é por onde você recebe as atualizações do seu pedido (aprovação,
          devolução, orientações) — informe um e-mail que você acessa.</p>
        <div className="creche-dados">
          <div><span className="rotulo">Nome</span><strong>{dados.nome_completo}</strong></div>
          <div><span className="rotulo">CPF</span><strong>{dados.cpf}</strong></div>
          <label className="campo">
            <span className="rotulo">E-mail {!dados.email && <em className="dica-inline">— a preencher</em>}</span>
            <input type="email" placeholder="voce@exemplo.com" defaultValue={dados.email || ''}
                   onBlur={(e) => api.conferirDados(token, { email: e.target.value })} /></label>
          <label className="campo">
            <span className="rotulo">Telefone / WhatsApp {!dados.telefone && <em className="dica-inline">— a preencher</em>}</span>
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
              <InputData valor={nova.data_nascimento}
                         onChange={(iso) => setNova({ ...nova, data_nascimento: iso || '' })} /></label>
            <label className="campo"><span className="rotulo">Vínculo</span>
              <SelectBusca valor={nova.parentesco} aoEscolher={(v) => setNova({ ...nova, parentesco: v })}>
                <option value="filho">Filho(a)</option>
                <option value="enteado">Enteado(a)</option>
                <option value="guarda">Guarda judicial</option>
              </SelectBusca></label>
          </div>
          <button className="btn-secundario" onClick={addCrianca}>+ Adicionar criança</button>
        </div>
      </div>

      {erro && <div className="alerta">{erro}</div>}
      <button className="btn-principal creche-enviar" disabled={enviando || !(dados.criancas || []).length}
              onClick={enviar}>
        {enviando ? 'Enviando…' : 'Enviar levantamento'}</button>
      {/* O "não tenho" saiu daqui (v2.34): era um link de texto pequeno DEPOIS
          do botão principal, num cartão chamado "Crianças" — quem não tinha
          filho nunca chegava até ele. Virou uma das duas respostas no topo. */}
      </>)}
    </div>
  )
}

// Tela pós-envio: mostra o andamento e, quando o RH aprova, libera a assinatura
// do requerimento pela plataforma (o colaborador já está autenticado por 2FA).
// Texto honesto por estado — antes tudo que não era 'indeferido' mentia
// "em análise, aguarde" (feedback 2026-07-22), inclusive aprovado-com-ressalva,
// suspenso e a própria auto-declaração de "não tenho direito".
const ESTADO_MSG = {
  em_analise: { icone: '🎉', titulo: 'Você já enviou',
    texto: 'Seu levantamento está em análise. Você será avisado por e-mail quando o RH decidir.' },
  aguardando_repactuacao: { icone: '✅', titulo: 'Aprovado — aguardando o contrato',
    texto: 'Seu pedido foi APROVADO. O pagamento começa após o ajuste (repactuação) do contrato do seu posto. Avisaremos por e-mail quando estiver ativo — não é preciso fazer nada agora.' },
  ativo: { icone: '✅', titulo: 'Benefício ativo',
    texto: 'Seu Reembolso-Creche está ativo. O RH está preparando seu requerimento para assinatura — você será avisado.' },
  suspenso: { icone: '⏸️', titulo: 'Benefício suspenso',
    texto: 'Seu benefício está suspenso. Em caso de dúvida, procure o RH.' },
  encerrado: { icone: '🔒', titulo: 'Benefício encerrado',
    texto: 'Seu benefício foi encerrado. Em caso de dúvida, procure o RH.' },
  sem_direito_declarado: { icone: '📄', titulo: 'Sem direito ao benefício',
    texto: 'Você declarou não ter dependentes que dão direito ao Reembolso-Creche. Se isso mudou (novo filho, guarda, adoção), procure o RH para refazer o levantamento.' },
}

function AposEnvio({ token, status, motivoIndeferimento }) {
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
  if (status === 'indeferido') {
    return (
      <div className="rh-card creche-card centro">
        <div style={{ fontSize: '3rem' }}>📋</div>
        <h2>Pedido não deferido</h2>
        <p className="explica">Após a análise, seu pedido de Reembolso-Creche foi indeferido.</p>
        {motivoIndeferimento && (
          <div className="aviso-inline">
            <strong>Motivo:</strong> {motivoIndeferimento}</div>)}
        <p className="explica">Em caso de dúvida, procure o RH.</p>
      </div>
    )
  }
  const m = ESTADO_MSG[status] || ESTADO_MSG.em_analise
  return (
    <div className="rh-card creche-card centro">
      <div style={{ fontSize: '3rem' }}>{m.icone}</div>
      <h2>{m.titulo}</h2>
      <p className="explica">{m.texto}</p>
    </div>
  )
}
