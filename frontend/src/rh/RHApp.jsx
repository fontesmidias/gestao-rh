import { useEffect, useMemo, useRef, useState } from 'react'
import { NavLink, Route, Routes, useNavigate, useParams } from 'react-router-dom'
import { fmtData, fmtDuracao, fmtTelefone } from '../fmt.js'
import { rh as api } from '../api.js'
import { STATUS_OPCOES, statusInfo } from '../status.js'
import SelectBusca from '../SelectBusca.jsx'
import { comAmpulheta } from '../Carregando.jsx'
import Detalhe from './Detalhe.jsx'
import Config from './Config.jsx'
import Colaboradores from './Colaboradores.jsx'
import TalentosRH from './TalentosRH.jsx'
import PostosRH from './PostosRH.jsx'
import JornadasRH from './JornadasRH.jsx'
import UniformesRH from './UniformesRH.jsx'
import DesenvolvimentoRH from './DesenvolvimentoRH.jsx'
import DesempenhoRH from './DesempenhoRH.jsx'
import AvaliacoesRH from './AvaliacoesRH.jsx'
import DashPlanilha from './DashPlanilha.jsx'
import { anotar, definirContexto } from '../telemetria.js'
import { criarTour, jaViu, marcarVisto } from './tour.js'
import Creche from './Creche.jsx'
import TestagemRH from './TestagemRH.jsx'
import Arquivo from './Arquivo.jsx'
import Modelos from './Modelos.jsx'
import Assinaturas from './Assinaturas.jsx'
import MinutarioRH from './MinutarioRH.jsx'
import MatchVagasRH from './MatchVagasRH.jsx'
import logo from '../assets/logo.png'
import InputSenha from '../InputSenha.jsx'
import BarraAtividade from '../BarraAtividade.jsx'
import Carregando from '../Carregando.jsx'
import { observarTabelas } from '../responsivo.js'

export default function RHApp() {
  const [logado, setLogado] = useState(api.logado())
  const tokenReset = new URLSearchParams(window.location.search).get('redefinir')
  if (tokenReset) return <RedefinirSenha token={tokenReset} />
  if (!logado) return <Login aoEntrar={() => setLogado(true)} />
  return (
    <>
      <BarraAtividade />
      <Carregando />
      <Painel aoSair={() => { api.sair(); setLogado(false) }} />
    </>
  )
}

function Login({ aoEntrar }) {
  const [email, setEmail] = useState('')
  const [senha, setSenha] = useState('')
  const [erro, setErro] = useState(null)
  const [esqueci, setEsqueci] = useState(false)
  const [enviando, setEnviando] = useState(false)
  const [enviado, setEnviado] = useState(false)
  const entrar = async (e) => {
    e.preventDefault()
    try { await api.login(email, senha); aoEntrar() }
    catch (er) {
      setErro(er.status === 429
        ? 'Muitas tentativas de login. Aguarde alguns minutos e tente de novo.'
        : 'E-mail ou senha incorretos.')
    }
  }
  if (esqueci) return (
    <main className="cartao rh-login">
      <h1>🔐 Esqueci minha senha</h1>
      {enviado ? (
        <>
          <div className="sucesso">Se este e-mail tiver acesso ao painel, enviamos um link de
            redefinição — ele vale por <strong>30 minutos</strong>. Confira também a caixa de
            spam.</div>
          <button className="btn-link" onClick={() => { setEsqueci(false); setEnviado(false) }}>
            ← voltar ao login</button>
        </>
      ) : (
        <form onSubmit={async (e) => {
          e.preventDefault()
          setEnviando(true)
          try { await api.esqueciSenha(email.trim()) } catch { /* resposta é sempre a mesma */ }
          setEnviando(false); setEnviado(true)
        }}>
          <p className="explica">Informe o e-mail que você usa para entrar no painel. Enviaremos
            um link para criar uma nova senha.</p>
          <label className="campo"><span className="rotulo">E-mail</span>
            <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} /></label>
          <button className="btn-principal" type="submit" disabled={enviando || !email}>
            {enviando ? 'Enviando…' : 'Enviar link de redefinição'}</button>
          <button className="btn-link" type="button" onClick={() => setEsqueci(false)}>
            ← voltar ao login</button>
        </form>
      )}
    </main>
  )
  return (
    <main className="cartao rh-login">
      <img src={logo} alt="Green House" className="logo-img" />
      <h1>Painel do RH</h1>
      <form onSubmit={entrar}>
        <label className="campo"><span className="rotulo">E-mail</span>
          <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} /></label>
        <label className="campo"><span className="rotulo">Senha</span>
          <InputSenha value={senha} onChange={(e) => setSenha(e.target.value)} /></label>
        {erro && <div className="alerta">{erro}</div>}
        <button className="btn-principal" type="submit">Entrar</button>
        <button className="btn-link" type="button" onClick={() => setEsqueci(true)}>
          Esqueci minha senha</button>
      </form>
    </main>
  )
}

function RedefinirSenha({ token }) {
  const [senha, setSenha] = useState('')
  const [confirma, setConfirma] = useState('')
  const [msg, setMsg] = useState(null)
  const [salvando, setSalvando] = useState(false)
  const [ok, setOk] = useState(false)
  const voltar = () => { window.location.href = '/rh' }
  if (ok) return (
    <main className="cartao rh-login">
      <h1>✅ Senha redefinida</h1>
      <div className="sucesso">Sua nova senha já vale. Entre no painel com ela.</div>
      <button className="btn-principal" onClick={voltar}>Ir para o login</button>
    </main>
  )
  return (
    <main className="cartao rh-login">
      <h1>🔐 Criar nova senha</h1>
      <form onSubmit={async (e) => {
        e.preventDefault()
        setMsg(null)
        if (senha !== confirma) { setMsg('As duas senhas não são iguais.'); return }
        setSalvando(true)
        try {
          await api.redefinirSenha(token, senha)
          setOk(true)
        } catch (er) {
          setMsg(er.detail === 'link_invalido_ou_expirado'
            ? 'Este link expirou ou já foi usado. Volte ao login e peça um novo em "Esqueci minha senha".'
            : er.detail === 'senha_curta_minimo_8'
              ? 'A senha precisa ter no mínimo 8 caracteres.'
              : `Não foi possível redefinir (${er.detail || er.message}).`)
        } finally { setSalvando(false) }
      }}>
        <label className="campo"><span className="rotulo">Nova senha (mín. 8 caracteres)</span>
          <InputSenha value={senha} onChange={(e) => setSenha(e.target.value)} /></label>
        <label className="campo"><span className="rotulo">Repita a nova senha</span>
          <InputSenha value={confirma} onChange={(e) => setConfirma(e.target.value)} /></label>
        {msg && <div className="alerta">{msg}</div>}
        <button className="btn-principal" type="submit" disabled={salvando || senha.length < 8}>
          {salvando ? 'Salvando…' : 'Salvar nova senha'}</button>
        <button className="btn-link" type="button" onClick={voltar}>← voltar ao login</button>
      </form>
    </main>
  )
}

// --- Admissões no DashPlanilha (v1.78): sort/filtro por coluna + cards clicáveis ---
const COLUNAS_ADMISSAO = () => [
  // Sem `filtro:` em `nome` e `status` (v2.51): a busca e o status são
  // SERVER-SIDE e vivem em `filtrosExtras`. Dois controles para o mesmo campo
  // — um filtrando o servidor, outro a memória — dá resultado que parece
  // errado. As colunas seguem ordenáveis, e os cards clicáveis continuam
  // funcionando porque a filtragem em memória roda sobre TODAS as colunas.
  { chave: 'nome', rotulo: 'Candidato', ordenavel: true, sempreVisivel: true,
    valor: (c) => c.nome_completo,
    render: (c) => (<><strong>{c.nome_completo}</strong><br />
      <small>{c.email || c.celular_whatsapp || 'sem contato — use 📋 Copiar link'}</small></>) },
  { chave: 'status', rotulo: 'Status', ordenavel: true,
    valor: (c) => statusInfo(c.status).label,
    render: (c) => (<span className="chip" style={{ '--chip-cor': statusInfo(c.status).cor }}>
      {statusInfo(c.status).icone} {statusInfo(c.status).label}</span>) },
  { chave: 'docs', rotulo: 'Docs', ordenavel: true,
    valor: (c) => (c.progresso_docs?.total ? c.progresso_docs.ok / c.progresso_docs.total : -1),
    render: (c) => (c.progresso_docs?.total ? `${c.progresso_docs.ok}/${c.progresso_docs.total}` : '—') },
  // Testes já respondidos aproveitados para esta pessoa (v2.21) — só o RH vê.
  // Oculta por padrão: nem toda admissão tem, e o dash já tem coluna demais.
  { chave: 'testes_vinculados', rotulo: 'Testes', ordenavel: true, oculta: true,
    valor: (c) => c.testes_vinculados || 0,
    render: (c) => (c.testes_vinculados
      ? <span className="chip" title="Testes respondidos antes da admissão, aproveitados pelo RH"
              style={{ '--chip-cor': '#5b7' }}>🧪 {c.testes_vinculados}</span>
      : '—') },
  { chave: 'criado_em', rotulo: 'Criado', ordenavel: true, valor: (c) => c.criado_em,
    render: (c) => fmtData(c.criado_em) },
]

// Cards do painel de Admissões: um bloco só, clicáveis quando filtram por status
// (v1.78 — antes eram <div> estáticos separados que não filtravam nada). As
// métricas operacionais (docs a revisar, reenvios, tempo médio) vêm de
// /rh/metricas e entram como indicadores.
function cardsAdmissao(lista, m) {
  // as métricas vêm de /rh/metricas (não da lista), então os cards aparecem
  // MESMO com a lista vazia/filtrada — são o painel, não o rodapé da tabela.
  if (!lista && !m) return null
  const reg = lista || []
  const porStatus = (s) => reg.filter((c) => c.status === s).length
  const cardStatus = (s) => ({
    rotulo: statusInfo(s).label, cor: statusInfo(s).cor, valor: porStatus(s),
    filtro: { chave: 'status', valor: statusInfo(s).label },
  })
  const cards = [
    { rotulo: 'Em admissão', valor: reg.length },
    cardStatus('envio_concluido'),
    cardStatus('em_revisao'),
    cardStatus('docs_pendentes'),
    cardStatus('aprovado'),
  ]
  if (m) {
    cards.push({ rotulo: 'Docs p/ revisar', valor: m.documentos_aguardando_revisao, cor: '#d9534f' })
    cards.push({ rotulo: 'Reenvios pendentes', valor: m.documentos_rejeitados_em_aberto, cor: '#e9a63a' })
    // Tempo de PREENCHIMENTO, não de calendário (v2.51). O card mostrava
    // `dossie_gerado_em - criado_em` — 2.590min de convite a dossiê, que
    // inclui a pessoa dormindo e esperando documento chegar. O que o RH quer
    // saber é quanto tempo o formulário toma de quem o preenche.
    cards.push({
      rotulo: m.tempo_liquido_medio_s == null ? 'Tempo de preenchimento' : 'Preenchimento (média)',
      valor: m.tempo_liquido_medio_s == null ? '—' : fmtDuracao(m.tempo_liquido_medio_s),
      dica: m.tempo_liquido_medio_s == null
        ? 'Ainda sem telemetria suficiente. A média aparece quando houver candidatos com sessões registradas.'
        : `Tempo que a pessoa REALMENTE passou preenchendo, somando as sessões `
          + `(intervalos acima de 30 min não contam). Amostra: ${m.tempo_liquido_amostra} pessoa(s). `
          + (m.tempo_medio_minutos_convite_ao_dossie != null
            ? `Do convite ao dossiê, o processo leva ${fmtDuracao(m.tempo_medio_minutos_convite_ao_dossie * 60)}.`
            : ''),
    })
  }
  return cards
}

const acoesAdmissao = (c, abrir) => (<>
  <button className="btn-secundario btn-mini" onClick={() => abrir(c.id)}>Abrir</button>
  <button className="btn-secundario btn-mini"
          title="Copia um link novo para você enviar pelo WhatsApp — NÃO envia e-mail"
          onClick={async (e) => {
            const btn = e.currentTarget
            const r = await api.gerarLink(c.id)
            await navigator.clipboard.writeText(r.link_magico)
            const original = btn.textContent
            btn.textContent = '✓ Copiado!'
            setTimeout(() => { btn.textContent = original }, 2000)
          }}>📋 Copiar link</button>
  <button className="btn-secundario btn-mini"
          title="Gera um link novo e reenvia o convite por e-mail"
          onClick={async (e) => {
            if (!window.confirm(`Reenviar o convite por e-mail para ${c.nome_completo}?`)) return
            const btn = e.currentTarget
            const r = await api.reenviarLink(c.id)
            const original = btn.textContent
            btn.textContent = r.email_enviado ? '✓ Enviado!'
              : (c.email ? '⚠ E-mail falhou' : '⚠ Sem e-mail')
            setTimeout(() => { btn.textContent = original }, 2500)
          }}>✉️ Reenviar</button>
</>)

// Sidebar esquerda retrátil: navegação sempre à vista, sem reload — mesmos
// rótulos de antes, novo lugar (feedback de campo, 2026-07-15).
// Menu por SEÇÕES, sempre expandido e rolável (feedback 2026-07-19: a versão
// hover/recolher ficou bugada — logo cortada, sem rolagem, itens demais soltos).
// Cada grupo tem um título curto; a <nav> rola sozinha quando não cabe. No
// celular vira gaveta pelo hambúrguer, retraindo ao escolher uma opção.
const GRUPOS = [
  ['Admissão', [
    ['inicio', '📋', 'Admissões'],
    ['colaboradores', '👥', 'Colaboradores'],
    ['postos', '🏢', 'Postos'],
    ['jornadas', '🕒', 'Jornadas'],
    ['uniformes', '👕', 'Uniformes'],
  ]],
  ['Documentos', [
    ['modelos', '📝', 'Modelos'],
    ['assinaturas', '✍️', 'Assinaturas'],
    ['arquivo', '🗄️', 'Arquivo'],
  ]],
  ['Avaliação', [
    ['testagem', '🧪', 'Testes'],
    ['desenvolvimento', '🎓', 'Desenvolvimento'],
    ['desempenho', '📌', 'Fatos Observados'],
    ['avaliacoes', '⭐', 'Avaliações'],
  ]],
  ['Benefícios', [
    ['creche', '🍼', 'Reembolso-Creche'],
  ]],
  ['Recrutamento', [
    ['talentos', '🎯', 'Banco de Talentos'],
    ['minutario', '💬', 'Minutário de Mensagens'],
    ['match-vagas', '🧩', 'Match de Vagas'],
  ]],
  ['Sistema', [
    ['config', '⚙️', 'Configurações'],
  ]],
]

// Menu com URL própria por tela (feedback 2026-07-27: "gostaria de abrir as
// coisas em outra aba" — sem <Link>/<NavLink> o navegador não tem link
// nenhum para oferecer no botão direito). Ctrl+clique e "abrir em nova aba"
// passam a funcionar de graça: o React Router intercepta só o clique simples.
function Sidebar({ aoSair, aoRever }) {
  const [movelAberto, setMovelAberto] = useState(false)
  const nome = localStorage.getItem('rh_nome') || ''
  return (
    <>
      <button className="rh-hamburguer" aria-label="Abrir menu"
              onClick={() => setMovelAberto(true)}>☰</button>
      {movelAberto && <div className="rh-sidebar-fundo" onClick={() => setMovelAberto(false)} />}
      <aside className={`rh-sidebar ${movelAberto ? 'movel-aberta' : ''}`}>
        <div className="rh-sidebar-logo">
          {/* logo customizada da empresa, com fallback para a padrão */}
          <img src="/api/marca/logo" alt="Logo da empresa" className="logo-topo"
               onError={(e) => { e.currentTarget.src = logo }} />
          {movelAberto && (
            <button className="rh-sidebar-fechar" aria-label="Fechar menu"
                    onClick={() => setMovelAberto(false)}>✕</button>
          )}
        </div>
        <nav>
          {GRUPOS.map(([titulo, itens]) => (
            <div className="rh-sidebar-grupo" key={titulo}>
              <span className="rh-sidebar-grupo-titulo">{titulo}</span>
              {itens.map(([id, icone, rotulo]) => (
                <NavLink key={id} to={id === 'inicio' ? '/rh' : `/rh/${id}`} end
                         className={({ isActive }) => `rh-sidebar-item ${isActive ? 'ativo' : ''}`}
                         onClick={() => setMovelAberto(false)}>
                  <span className="rh-sidebar-icone">{icone}</span>
                  <span>{rotulo}</span>
                </NavLink>
              ))}
            </div>
          ))}
        </nav>
        <div className="rh-sidebar-rodape">
          <span className="rh-sidebar-user" title={`Conectado(a) como ${nome}`}>
            <span className="rh-sidebar-avatar">{(nome || '?').trim()[0]?.toUpperCase()}</span>
            <span className="rh-nome">{nome}</span>
          </span>
          {/* Ícone, não texto: o rodapé é `space-between` com `nowrap`, e um
              terceiro item com rótulo comprimia o nome de quem está logado
              até sobrar só o avatar. */}
          <button className="btn-link rh-sidebar-tour" title="Rever o tour do painel"
                  aria-label="Rever o tour do painel" onClick={aoRever}>❓</button>
          <button className="btn-link" title="Sair da conta" onClick={aoSair}>Sair</button>
        </div>
      </aside>
    </>
  )
}

// Splat /rh/* reservado em App.jsx: cada tela do menu ganha URL própria
// (/rh/colaboradores, /rh/config…) e a pessoa aberta também (/rh/candidato/:id)
// — antes tudo era um único useState('inicio'), então botão direito não tinha
// link pra oferecer, F5 sempre voltava para Admissões, e não dava pra abrir
// duas pessoas em duas abas (feedback 2026-07-27).
function Painel({ aoSair }) {
  return (
    <Routes>
      <Route path="candidato/:id" element={<PainelConteudo aoSair={aoSair} />} />
      <Route path=":pagina" element={<PainelConteudo aoSair={aoSair} />} />
      <Route path="" element={<PainelConteudo aoSair={aoSair} />} />
    </Routes>
  )
}

function PainelConteudo({ aoSair }) {
  const navigate = useNavigate()
  const { pagina: paginaUrl, id: candidatoUrl } = useParams()
  const pagina = paginaUrl || 'inicio'
  // A URL é a fonte de verdade de qual pessoa está aberta — nada de estado
  // local duplicado (navegação direta, Voltar do navegador, tudo bate certo).
  const selecionado = candidatoUrl || null
  const [candidatos, setCandidatos] = useState(null)
  const [metricas, setMetricas] = useState(null)
  const [novo, setNovo] = useState(null) // form de novo candidato
  const [postos, setPostos] = useState([])
  const [convite, setConvite] = useState(null)
  const [erroConvite, setErroConvite] = useState(null)
  const [enviandoConvite, setEnviandoConvite] = useState(false)
  const [filtros, setFiltros] = useState({ status: '', busca: '', posto_id: '' })

  // Tour do painel: dispara UMA vez, na primeira visita, e fica disponível pelo
  // "?" do rodapé do menu. O atraso deixa a sidebar montar — sem ele o driver
  // não acha os elementos e pula os passos EM SILÊNCIO.
  const tour = useMemo(() => criarTour(), [])
  useEffect(() => {
    if (jaViu()) return
    marcarVisto()
    const t = setTimeout(() => tour.drive(), 600)
    return () => clearTimeout(t)
  }, [tour])

  const recarregar = (f = filtros) => {
    const limpos = Object.fromEntries(Object.entries(f).filter(([, v]) => v))
    api.candidatos(limpos).then(setCandidatos).catch((e) => {
      if (e.status === 401) aoSair()
    })
    api.metricas().then(setMetricas).catch(() => {})
  }
  const recarregarPostos = () => api.postos().then((r) => setPostos(r.postos)).catch(() => {})
  useEffect(() => { recarregar(); recarregarPostos() }, [])

  // Telemetria do painel (v2.24): identifica a origem como `rh` — o servidor
  // só aceita esse rótulo com autenticação, então ninguém finge ser o RH.
  useEffect(() => { definirContexto({ origem: 'rh', token: null }) }, [])

  // Que telas o RH usa e por quanto tempo. Serve para decidir o que melhorar
  // com base em uso real, e não em impressão de quem pediu por último.
  useEffect(() => {
    const entrou = performance.now()
    anotar('painel_pagina', { pagina: `/rh/${pagina}` })
    return () => anotar('painel_pagina_saiu', {
      pagina: `/rh/${pagina}`, duracao_ms: performance.now() - entrou,
    })
  }, [pagina])
  // no celular, as tabelas viram cards com rótulos automáticos das colunas
  useEffect(() => observarTabelas(), [])

  // Cargo do convite: mesmo padrão de busca do PostoServico em Detalhe.jsx —
  // evita "Vigia"/"vigia"/"Vigía" virarem cargos diferentes (feedback 2026-07-27).
  const [cargos, setCargos] = useState([])
  const [digitandoCargoConvite, setDigitandoCargoConvite] = useState(false)
  useEffect(() => { api.cargos().then((r) => setCargos(r.cargos)).catch(() => {}) }, [])
  const opcoesCargoConvite = useMemo(() => {
    const cargoAtual = novo?.cargo_funcao || ''
    const nomes = cargos.map((c) => c.nome)
    if (cargoAtual && !nomes.includes(cargoAtual)) nomes.unshift(cargoAtual)
    return [
      ...nomes.map((n) => {
        const achado = cargos.find((c) => c.nome === n)
        return { valor: n, rotulo: n,
                 extra: achado ? `${achado.pessoas} pessoa(s)` : 'atual' }
      }),
      { valor: '__novo', rotulo: '＋ Cargo novo…' },
    ]
  }, [cargos, novo?.cargo_funcao])

  // Jornadas para o seletor do convite: as do posto escolhido vêm primeiro
  // (ordenação, não filtro). Jornada é obrigatória no convite (feedback 2026-07-21).
  const [jornadasConvite, setJornadasConvite] = useState([])
  useEffect(() => {
    if (!novo) { setJornadasConvite([]); setDigitandoCargoConvite(false); return }
    api.jornadas(novo.posto_id || null).then(setJornadasConvite).catch(() => setJornadasConvite([]))
  }, [novo?.posto_id, novo === null])

  // Empresas para o convite (v2.44). Com UMA só — que é o caso do grupo — ela
  // já vem escolhida e o seletor nem aparece: obrigar um clique numa lista de
  // um item é teatro, não conferência. Com duas ou mais, o RH decide.
  const [empresasConvite, setEmpresasConvite] = useState([])
  useEffect(() => {
    if (!novo) return
    api.empresas().then((lista) => {
      setEmpresasConvite(lista || [])
      if ((lista || []).length === 1) {
        setNovo((x) => (x && !x.empresa_id ? { ...x, empresa_id: lista[0].id } : x))
      }
    }).catch(() => setEmpresasConvite([]))
  }, [novo === null])

  // aoAbrir/aoAbrirPessoa das telas filhas navegam para a URL da pessoa —
  // Ctrl+clique não se aplica aqui (é callback, não <a>), mas o histórico e o
  // F5 passam a funcionar, e a URL fica compartilhável.
  const navegar = (destino) => navigate(destino === 'inicio' ? '/rh' : `/rh/${destino}`)
  const abrirPessoa = (id) => navigate(`/rh/candidato/${id}`)
  const voltarDaPessoa = () => { navigate('/rh'); recarregar() }

  return (
    <div className="rh-layout">
      <Sidebar aoSair={aoSair} aoRever={() => tour.drive()} />
      <div className="rh-conteudo">
        {pagina === 'config' && <Config aoVoltar={() => navegar('inicio')} />}
        {pagina === 'colaboradores' && (
          <Colaboradores aoVoltar={() => navegar('inicio')} aoAbrir={abrirPessoa} />
        )}
        {pagina === 'postos' && <PostosRH />}
        {pagina === 'jornadas' && <JornadasRH aoVoltar={() => navegar('inicio')} />}
        {pagina === 'uniformes' && <UniformesRH aoVoltar={() => navegar('inicio')}
                                                abrirPessoa={abrirPessoa} />}
        {pagina === 'creche' && <Creche aoVoltar={() => navegar('inicio')} />}
        {pagina === 'desenvolvimento' && <DesenvolvimentoRH aoVoltar={() => navegar('inicio')} />}
        {pagina === 'desempenho' && <DesempenhoRH aoVoltar={() => navegar('inicio')} />}
        {pagina === 'avaliacoes' && <AvaliacoesRH aoVoltar={() => navegar('inicio')} />}
        {pagina === 'testagem' && <TestagemRH aoAbrirPessoa={abrirPessoa} />}
        {pagina === 'arquivo' && <Arquivo />}
        {pagina === 'modelos' && <Modelos />}
        {pagina === 'assinaturas' && <Assinaturas aoAbrirPessoa={abrirPessoa} />}
        {pagina === 'talentos' && <TalentosRH aoAbrir={abrirPessoa} />}
        {pagina === 'minutario' && <MinutarioRH />}
        {pagina === 'match-vagas' && <MatchVagasRH />}
        {selecionado && (
          <Detalhe id={selecionado} aoVoltar={voltarDaPessoa} />
        )}
        {pagina === 'inicio' && !selecionado && (
    <main className="rh-painel">
      <header className="rh-topo">
        <h1>Admissões</h1>
        <button className="btn-principal" onClick={() => setNovo({})}>+ Novo candidato</button>
      </header>

      {/* os cards agora vivem no DashPlanilha (clicáveis, filtram por status) */}

      {novo && (
        <div className="rh-card">
          <h3>Convidar candidato</h3>
          <p className="explica">Nome, <strong>posto</strong>, <strong>jornada</strong> e
            <strong> cargo</strong> são
            obrigatórios — com base no posto e no regime, os documentos do kit já nascem certos, e a
            jornada evita a pendência que o Tirvu acusa depois. Sem e-mail? Sem problema: o link
            aparece aqui para copiar e mandar pelo WhatsApp.</p>
          <div className="linha3">
            <input placeholder="Nome completo"
                   onChange={(e) => setNovo({ ...novo, nome_completo: e.target.value })} />
            <input placeholder="E-mail (opcional)" type="email"
                   onChange={(e) => setNovo({ ...novo, email: e.target.value })} />
            <input placeholder="Celular/WhatsApp (opcional)" inputMode="tel"
                   value={fmtTelefone(novo.celular_whatsapp)}
                   onChange={(e) => setNovo({ ...novo, celular_whatsapp: fmtTelefone(e.target.value) })} />
          </div>
          <div className="linha3">
            <SelectBusca valor={novo.posto_id || ''} placeholder="Buscar posto…"
                         aoEscolher={(v) => {
                           if (v === '__novo') { setNovo({ ...novo, criandoPosto: '' }); return }
                           setNovo({ ...novo, posto_id: v, criandoPosto: undefined })
                         }}>
              <option value="">— posto de serviço (obrigatório) —</option>
              {postos.map((p) => <option key={p.id} value={p.id}>
                {p.sigla || p.nome}{p.contrato_ref ? ` — ${p.contrato_ref}` : ''}</option>)}
              <option value="__novo">➕ Outro (cadastrar novo posto)</option>
            </SelectBusca>
            <SelectBusca valor={novo.jornada_id || ''} placeholder="Buscar jornada…"
                         aoEscolher={(v) => setNovo({ ...novo, jornada_id: v })}>
              <option value="">— jornada (obrigatória) —</option>
              {jornadasConvite.map((j) => <option key={j.id} value={j.id}>{j.descricao}</option>)}
            </SelectBusca>
            <SelectBusca valor={novo.regime || 'efetivo'}
                         aoEscolher={(v) => setNovo({ ...novo, regime: v })}>
              <option value="efetivo">Regime: Efetivo</option>
              <option value="intermitente">Regime: Intermitente</option>
            </SelectBusca>
          </div>
          <div className="linha2">
            {digitandoCargoConvite ? (
              <span className="rh-cargo-novo">
                <input placeholder="Cargo/função novo (obrigatório)" value={novo.cargo_funcao || ''}
                       autoFocus
                       onChange={(e) => setNovo({ ...novo, cargo_funcao: e.target.value })} />
                <button type="button" className="btn-secundario btn-mini"
                        title="Voltar para a lista de cargos já cadastrados"
                        onClick={() => setDigitandoCargoConvite(false)}>↩ lista</button>
              </span>
            ) : (
              <SelectBusca
                valor={novo.cargo_funcao || ''}
                vazioRotulo="— cargo/função (obrigatório) —" placeholder="Buscar cargo…"
                opcoes={opcoesCargoConvite}
                aoEscolher={(v) => {
                  if (v === '__novo') { setNovo({ ...novo, cargo_funcao: '' }); setDigitandoCargoConvite(true); return }
                  setNovo({ ...novo, cargo_funcao: v })
                }} />
            )}
            {/* Registra ponto: obrigatório no convite (feedback 2026-08-01,
                "é uma das coisas fundamentais para o Tirvu"). Antes só virava
                pendência na hora do export — e o Tirvu aceita a célula vazia
                calado, então o colaborador nascia lá sem a marcação. */}
            <SelectBusca valor={novo.registra_ponto === undefined || novo.registra_ponto === null
              ? '' : String(novo.registra_ponto)}
                         aoEscolher={(v) => setNovo({ ...novo,
                           registra_ponto: v === '' ? null : v === 'true' })}>
              <option value="">— registra ponto? (obrigatório) —</option>
              <option value="true">Registra ponto: Sim</option>
              <option value="false">Registra ponto: Não</option>
            </SelectBusca>
            {/* Empresa: o grupo opera com UMA empregadora, então o campo vem
                escolhido e serve ao cadastro. Obrigar um clique numa lista de
                um item seria teatro; com duas ou mais, o RH decide. */}
            {empresasConvite.length > 1 && (
              <SelectBusca valor={novo.empresa_id || ''} placeholder="Buscar empresa…"
                           aoEscolher={(v) => setNovo({ ...novo, empresa_id: v || null })}>
                <option value="">— empresa (empregadora) —</option>
                {empresasConvite.map((e2) => (
                  <option key={e2.id} value={e2.id}>{e2.nome_fantasia || e2.razao_social}</option>))}
              </SelectBusca>
            )}
            {jornadasConvite.length === 0 && (
              <span className="explica" style={{ margin: 0, alignSelf: 'center' }}>
                Nenhuma jornada cadastrada ainda — cadastre em <strong>Config → Empresas e jornadas</strong>.</span>)}
          </div>
          <div className="rh-lote" style={{ margin: '.5rem 0 0' }}>
            <label style={{ display: 'flex', alignItems: 'center', gap: '.45rem' }}>
              <input type="checkbox" style={{ width: 'auto', minHeight: 0 }}
                     checked={!!novo.fazer_disc}
                     onChange={(e) => setNovo({ ...novo, fazer_disc: e.target.checked })} />
              <span>🧭 Fazer o <strong>Inventário DISC</strong></span>
            </label>
            <label style={{ display: 'flex', alignItems: 'center', gap: '.45rem' }}>
              <input type="checkbox" style={{ width: 'auto', minHeight: 0 }}
                     checked={!!novo.fazer_situacional}
                     onChange={(e) => setNovo({ ...novo, fazer_situacional: e.target.checked })} />
              <span>🧩 Fazer o <strong>Teste Situacional</strong></span>
            </label>
            <span className="explica" style={{ margin: 0 }}>O candidato responde antes do cadastro;
              o resultado é visível só para o RH.</span>
          </div>
          {novo.criandoPosto !== undefined && (
            <div className="rh-adicional">
              <input placeholder="Nome do novo posto" value={novo.criandoPosto}
                     onChange={(e) => setNovo({ ...novo, criandoPosto: e.target.value })} />
              <input placeholder="Sigla (ex.: INEP Adm)" value={novo.criandoSigla || ''}
                     onChange={(e) => setNovo({ ...novo, criandoSigla: e.target.value })} style={{ maxWidth: 160 }} />
              <button className="btn-principal btn-mini" onClick={async () => {
                if (!novo.criandoPosto.trim()) return
                try {
                  const p = await api.criarPosto({ nome: novo.criandoPosto.trim(), sigla: (novo.criandoSigla || '').trim() || null })
                  await recarregarPostos()
                  setNovo({ ...novo, posto_id: p.id, criandoPosto: undefined, criandoSigla: undefined })
                } catch (e) {
                  setErroConvite(e.detail === 'posto_ja_existe' ? 'Já existe um posto com esse nome.' : `Não foi possível criar o posto (${e.detail || e.message}).`)
                }
              }}>Criar posto</button>
              <button className="btn-link" onClick={() => setNovo({ ...novo, criandoPosto: undefined })}>cancelar</button>
            </div>
          )}
          <div className="navegacao">
            <button className="btn-secundario" onClick={() => { setNovo(null); setConvite(null) }}>
              Cancelar</button>
            <button className="btn-principal" disabled={enviandoConvite} onClick={async () => {
              setErroConvite(null); setConvite(null)
              if (!novo.nome_completo?.trim()) {
                setErroConvite('Informe pelo menos o nome do candidato.'); return
              }
              if (!novo.posto_id) {
                setErroConvite('Escolha o posto de serviço (ou cadastre um novo em "Outro").'); return
              }
              if (!novo.jornada_id) {
                setErroConvite('Escolha a jornada de trabalho (o Tirvu recusa admissão sem jornada). '
                  + 'Se não houver nenhuma, cadastre em Config → Empresas e jornadas.'); return
              }
              if (!(novo.cargo_funcao || '').trim()) {
                setErroConvite('Informe o cargo/função — é obrigatório para gerar o link.'); return
              }
              if (novo.registra_ponto === undefined || novo.registra_ponto === null) {
                setErroConvite('Informe se a pessoa registra ponto. O Tirvu aceita esse campo '
                  + 'em branco sem reclamar, e o colaborador nasce lá sem a marcação.'); return
              }
              setEnviandoConvite(true)
              try {
                const r = await api.novoCandidato({
                  nome_completo: novo.nome_completo.trim(),
                  email: (novo.email || '').trim() || null,
                  celular_whatsapp: (novo.celular_whatsapp || '').trim() || null,
                  posto_id: novo.posto_id,
                  jornada_id: novo.jornada_id,
                  regime: novo.regime || 'efetivo',
                  cargo_funcao: (novo.cargo_funcao || '').trim() || null,
                  registra_ponto: novo.registra_ponto,
                  empresa_id: novo.empresa_id || null,
                  fazer_disc: !!novo.fazer_disc,
                  fazer_situacional: !!novo.fazer_situacional,
                })
                setConvite(r)
                recarregar()
              } catch (e) {
                let texto = `Não foi possível criar o convite (${e.detail || e.message}).`
                if (e.status === 422 && Array.isArray(e.detail)) {
                  const campos = e.detail.map((d) => `${d.loc?.slice(-1)[0]}: ${d.msg}`).join('; ')
                  texto = `Confira os campos — ${campos}`
                }
                if (e.status === 401) texto = 'Sua sessão expirou. Saia e entre novamente.'
                setErroConvite(texto)
              } finally { setEnviandoConvite(false) }
            }}>{enviandoConvite ? 'Criando…' : 'Convidar e enviar link'}</button>
          </div>
          {erroConvite && <div className="alerta">{erroConvite}</div>}
          {convite && (
            <div className="sucesso">
              Link mágico criado{convite.email_enviado ? ' e enviado por e-mail ✓' : ''}.
              {!convite.email_enviado && (convite.candidato?.email
                ? <> O e-mail não saiu — envie o link manualmente (WhatsApp):</>
                : <> Candidato sem e-mail — copie o link e mande pelo WhatsApp:</>)}
              <code className="link-copiar">{convite.link_magico}</code>
              <button className="btn-secundario btn-mini" onClick={(e) => {
                navigator.clipboard.writeText(convite.link_magico)
                const btn = e.currentTarget
                btn.textContent = '✓ Copiado!'
                setTimeout(() => { btn.textContent = '📋 Copiar link' }, 2000)
              }}>📋 Copiar link</button>
            </div>
          )}
        </div>
      )}

      {!candidatos ? <p>Carregando…</p> : (
        /* UM bloco de filtros só (v2.51): busca, status e posto são
           server-side e entram na MESMA grade do dash, via `filtrosExtras`.
           Antes eram dois cards empilhados — e STATUS aparecia nos dois, um
           filtrando o servidor e o outro a memória. O Bruno já tinha apontado
           isso no creche (v2.30): "tem dois cards, acho que apenas um, tudo
           concentrado e coeso de filtros". As colunas `nome` e `status`
           perderam o `filtro:` — um assunto, um controle; elas seguem
           ordenáveis e os cards clicáveis continuam funcionando. */
        <DashPlanilha id="admissoes" colunas={COLUNAS_ADMISSAO()}
                      dados={candidatos} cards={cardsAdmissao(candidatos, metricas)}
                      acoesLinha={(c) => acoesAdmissao(c, abrirPessoa)}
                      filtrosExtras={[
                        { chave: 'busca', rotulo: 'Candidato', valor: filtros.busca,
                          placeholder: '🔎 Nome, e-mail ou CPF',
                          aoMudar: (v) => { const f = { ...filtros, busca: v }; setFiltros(f); recarregar(f) } },
                        { chave: 'status', rotulo: 'Status', valor: filtros.status,
                          vazioRotulo: 'Status: todos',
                          opcoes: STATUS_OPCOES.filter(([v]) => v).map(([v, r]) => ({ v, r })),
                          aoMudar: (v) => { const f = { ...filtros, status: v }; setFiltros(f); recarregar(f) } },
                        { chave: 'posto_id', rotulo: 'Posto', valor: filtros.posto_id,
                          vazioRotulo: 'Posto: todos',
                          opcoes: postos.map((p) => ({ v: p.id, r: p.sigla || p.nome })),
                          aoMudar: (v) => { const f = { ...filtros, posto_id: v }; setFiltros(f); recarregar(f) } },
                      ]}
                      acoesFiltro={<>
                        {(filtros.busca || filtros.status || filtros.posto_id) && (
                          <button className="btn-link" onClick={() => {
                            const f = { status: '', busca: '', posto_id: '' }; setFiltros(f); recarregar(f)
                          }}>limpar filtros</button>
                        )}
                        <button className="btn-secundario btn-mini"
                                title="Baixa uma planilha das admissões que casam o filtro"
                                onClick={() => comAmpulheta('Gerando a planilha…', async () => {
                                  const blob = await api.exportarAdmissoes(Object.fromEntries(
                                    Object.entries(filtros).filter(([, v]) => v)))
                                  const a = document.createElement('a')
                                  a.href = URL.createObjectURL(blob)
                                  a.download = `admissoes-${new Date().toISOString().slice(0, 10)}.xlsx`
                                  a.click()
                                })}>⬇ Exportar planilha</button>
                      </>}
                      vazio={(filtros.busca || filtros.status || filtros.posto_id)
                        ? 'Nenhuma admissão com esses filtros.'
                        : 'Nenhum candidato ainda. Toque em "+ Novo candidato" para enviar o primeiro convite.'} />
      )}
    </main>
        )}
      </div>
    </div>
  )
}
