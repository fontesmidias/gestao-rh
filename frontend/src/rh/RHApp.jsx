import { useEffect, useRef, useState } from 'react'
import { fmtData } from '../fmt.js'
import { rh as api } from '../api.js'
import { STATUS_OPCOES, statusInfo } from '../status.js'
import SelectBusca from '../SelectBusca.jsx'
import { comAmpulheta } from '../Carregando.jsx'
import Detalhe from './Detalhe.jsx'
import Config from './Config.jsx'
import Colaboradores from './Colaboradores.jsx'
import TalentosRH from './TalentosRH.jsx'
import PostosRH from './PostosRH.jsx'
import Creche from './Creche.jsx'
import TestagemRH from './TestagemRH.jsx'
import Arquivo from './Arquivo.jsx'
import Modelos from './Modelos.jsx'
import Assinaturas from './Assinaturas.jsx'
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

const EM_ANDAMENTO = ['convidado', 'preenchendo', 'aguardando_assinatura', 'docs_pendentes']

function Metricas({ dados }) {
  if (!dados) return null
  const andamento = EM_ANDAMENTO.reduce((n, s) => n + (dados.por_status[s] || 0), 0)
  const cards = [
    ['Candidatos', dados.total_candidatos, ''],
    ['Em andamento', andamento, ''],
    ['Docs p/ revisar', dados.documentos_aguardando_revisao,
     dados.documentos_aguardando_revisao > 0 ? 'destaque' : ''],
    ['Reenvios pendentes', dados.documentos_rejeitados_em_aberto,
     dados.documentos_rejeitados_em_aberto > 0 ? 'destaque' : ''],
    ['Dossiês gerados', dados.dossies_gerados, ''],
    ['Tempo médio', dados.tempo_medio_minutos_convite_ao_dossie == null
      ? '—' : `${dados.tempo_medio_minutos_convite_ao_dossie.toLocaleString('pt-BR')} min`, ''],
  ]
  return (
    <div className="rh-metricas">
      {cards.map(([rotulo, valor, extra]) => (
        <div className={`rh-metrica ${extra}`} key={rotulo}
             title={rotulo === 'Tempo médio' ? 'Do convite até o dossiê pronto' : undefined}>
          <strong>{valor}</strong>
          <span>{rotulo}</span>
        </div>
      ))}
    </div>
  )
}

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
  ]],
  ['Documentos', [
    ['modelos', '📝', 'Modelos'],
    ['assinaturas', '✍️', 'Assinaturas'],
    ['arquivo', '🗄️', 'Arquivo'],
  ]],
  ['Avaliação', [
    ['testagem', '🧪', 'Testes'],
  ]],
  ['Benefícios', [
    ['creche', '🍼', 'Reembolso-Creche'],
  ]],
  ['Recrutamento', [
    ['talentos', '🎯', 'Banco de Talentos'],
  ]],
  ['Sistema', [
    ['config', '⚙️', 'Configurações'],
  ]],
]

function Sidebar({ pagina, navegar, aoSair }) {
  const [movelAberto, setMovelAberto] = useState(false)
  const irPara = (fn) => { fn(); setMovelAberto(false) }
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
                <button key={id} className={`rh-sidebar-item ${pagina === id ? 'ativo' : ''}`}
                        onClick={() => irPara(() => navegar(id))}>
                  <span className="rh-sidebar-icone">{icone}</span>
                  <span>{rotulo}</span>
                </button>
              ))}
            </div>
          ))}
        </nav>
        <div className="rh-sidebar-rodape">
          <span className="rh-sidebar-user" title={`Conectado(a) como ${nome}`}>
            <span className="rh-sidebar-avatar">{(nome || '?').trim()[0]?.toUpperCase()}</span>
            <span className="rh-nome">{nome}</span>
          </span>
          <button className="btn-link" title="Sair da conta" onClick={aoSair}>Sair</button>
        </div>
      </aside>
    </>
  )
}

function Painel({ aoSair }) {
  const [candidatos, setCandidatos] = useState(null)
  const [metricas, setMetricas] = useState(null)
  const [selecionado, setSelecionado] = useState(null)
  const [novo, setNovo] = useState(null) // form de novo candidato
  const [postos, setPostos] = useState([])
  const [convite, setConvite] = useState(null)
  const [erroConvite, setErroConvite] = useState(null)
  const [enviandoConvite, setEnviandoConvite] = useState(false)
  const [pagina, setPagina] = useState('inicio') // inicio | colaboradores | config…
  const [filtros, setFiltros] = useState({ status: '', busca: '', posto_id: '' })

  const recarregar = (f = filtros) => {
    const limpos = Object.fromEntries(Object.entries(f).filter(([, v]) => v))
    api.candidatos(limpos).then(setCandidatos).catch((e) => {
      if (e.status === 401) aoSair()
    })
    api.metricas().then(setMetricas).catch(() => {})
  }
  const recarregarPostos = () => api.postos().then((r) => setPostos(r.postos)).catch(() => {})
  useEffect(() => { recarregar(); recarregarPostos() }, [])
  // no celular, as tabelas viram cards com rótulos automáticos das colunas
  useEffect(() => observarTabelas(), [])

  // Jornadas para o seletor do convite: as do posto escolhido vêm primeiro
  // (ordenação, não filtro). Jornada é obrigatória no convite (feedback 2026-07-21).
  const [jornadasConvite, setJornadasConvite] = useState([])
  useEffect(() => {
    if (!novo) { setJornadasConvite([]); return }
    api.jornadas(novo.posto_id || null).then(setJornadasConvite).catch(() => setJornadasConvite([]))
  }, [novo?.posto_id, novo === null])

  const navegar = (destino) => {
    setPagina(destino)
    setSelecionado(null)
    if (destino === 'inicio') recarregar()
  }

  return (
    <div className="rh-layout">
      <Sidebar pagina={pagina} navegar={navegar} aoSair={aoSair} />
      <div className="rh-conteudo">
        {pagina === 'config' && <Config aoVoltar={() => navegar('inicio')} />}
        {pagina === 'colaboradores' && (
          <Colaboradores aoVoltar={() => navegar('inicio')}
                         aoAbrir={(id) => { setPagina('inicio'); setSelecionado(id) }} />
        )}
        {pagina === 'postos' && <PostosRH />}
        {pagina === 'creche' && <Creche aoVoltar={() => navegar('inicio')} />}
        {pagina === 'testagem' && (
          <TestagemRH aoAbrirPessoa={(id) => { setPagina('inicio'); setSelecionado(id) }} />
        )}
        {pagina === 'arquivo' && <Arquivo />}
        {pagina === 'modelos' && <Modelos />}
        {pagina === 'assinaturas' && (
          <Assinaturas aoAbrirPessoa={(id) => { setPagina('inicio'); setSelecionado(id) }} />
        )}
        {pagina === 'talentos' && (
          <TalentosRH aoAbrir={(id) => { setPagina('inicio'); setSelecionado(id) }} />
        )}
        {pagina === 'inicio' && selecionado && (
          <Detalhe id={selecionado}
                   aoVoltar={() => { setSelecionado(null); recarregar() }} />
        )}
        {pagina === 'inicio' && !selecionado && (
    <main className="rh-painel">
      <header className="rh-topo">
        <h1>Admissões</h1>
        <button className="btn-principal" onClick={() => setNovo({})}>+ Novo candidato</button>
      </header>

      <Metricas dados={metricas} />

      {novo && (
        <div className="rh-card">
          <h3>Convidar candidato</h3>
          <p className="explica">Nome, <strong>posto</strong> e <strong>jornada</strong> são
            obrigatórios — com base no posto e no regime, os documentos do kit já nascem certos, e a
            jornada evita a pendência que o Tirvu acusa depois. Sem e-mail? Sem problema: o link
            aparece aqui para copiar e mandar pelo WhatsApp.</p>
          <div className="linha3">
            <input placeholder="Nome completo"
                   onChange={(e) => setNovo({ ...novo, nome_completo: e.target.value })} />
            <input placeholder="E-mail (opcional)" type="email"
                   onChange={(e) => setNovo({ ...novo, email: e.target.value })} />
            <input placeholder="Celular/WhatsApp (opcional)"
                   onChange={(e) => setNovo({ ...novo, celular_whatsapp: e.target.value })} />
          </div>
          <div className="linha3">
            <select value={novo.posto_id || ''} onChange={(e) => {
              if (e.target.value === '__novo') { setNovo({ ...novo, criandoPosto: '' }); return }
              setNovo({ ...novo, posto_id: e.target.value, criandoPosto: undefined })
            }}>
              <option value="">— posto de serviço (obrigatório) —</option>
              {postos.map((p) => <option key={p.id} value={p.id}>
                {p.sigla || p.nome}{p.contrato_ref ? ` — ${p.contrato_ref}` : ''}</option>)}
              <option value="__novo">➕ Outro (cadastrar novo posto)</option>
            </select>
            <select value={novo.jornada_id || ''}
                    onChange={(e) => setNovo({ ...novo, jornada_id: e.target.value })}>
              <option value="">— jornada (obrigatória) —</option>
              {jornadasConvite.map((j) => <option key={j.id} value={j.id}>{j.descricao}</option>)}
            </select>
            <select value={novo.regime || 'efetivo'}
                    onChange={(e) => setNovo({ ...novo, regime: e.target.value })}>
              <option value="efetivo">Regime: Efetivo</option>
              <option value="intermitente">Regime: Intermitente</option>
            </select>
          </div>
          <div className="linha2">
            <input placeholder="Cargo/função (opcional)"
                   onChange={(e) => setNovo({ ...novo, cargo_funcao: e.target.value })} />
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

      <div className="rh-card rh-lote">
        <input placeholder="🔎 Nome, e-mail ou CPF" value={filtros.busca} style={{ maxWidth: 220 }}
               onChange={(e) => { const f = { ...filtros, busca: e.target.value }; setFiltros(f); recarregar(f) }} />
        <SelectBusca style={{ minWidth: 190 }} vazioRotulo="Status: todos" placeholder="Buscar status…"
          valor={filtros.status} aoEscolher={(v) => { const f = { ...filtros, status: v }; setFiltros(f); recarregar(f) }}
          opcoes={STATUS_OPCOES.filter(([v]) => v).map(([v, r]) => ({ valor: v, rotulo: r }))} />
        <SelectBusca style={{ minWidth: 180 }} vazioRotulo="Posto: todos" placeholder="Buscar posto…"
          valor={filtros.posto_id} aoEscolher={(v) => { const f = { ...filtros, posto_id: v }; setFiltros(f); recarregar(f) }}
          opcoes={postos.map((p) => ({ valor: p.id, rotulo: p.sigla || p.nome }))} />
        {(filtros.busca || filtros.status || filtros.posto_id) && (
          <button className="btn-link" onClick={() => { const f = { status: '', busca: '', posto_id: '' }; setFiltros(f); recarregar(f) }}>limpar</button>
        )}
        <span style={{ flex: 1 }} />
        <button className="btn-secundario btn-mini" title="Baixa uma planilha das admissões que casam o filtro"
                onClick={() => comAmpulheta('Gerando a planilha…', async () => {
                  const blob = await api.exportarAdmissoes(Object.fromEntries(
                    Object.entries(filtros).filter(([, v]) => v)))
                  const a = document.createElement('a')
                  a.href = URL.createObjectURL(blob)
                  a.download = `admissoes-${new Date().toISOString().slice(0, 10)}.xlsx`
                  a.click()
                })}>⬇ Exportar planilha</button>
      </div>

      {!candidatos ? <p>Carregando…</p> : candidatos.length === 0 ? (
        <p className="explica centro">{(filtros.busca || filtros.status || filtros.posto_id)
          ? 'Nenhuma admissão com esses filtros.'
          : 'Nenhum candidato ainda. Toque em "+ Novo candidato" para enviar o primeiro convite.'}</p>
      ) : (
        <table className="rh-tabela">
          <thead>
            <tr><th>Candidato</th><th>Status</th><th>Docs</th><th>Criado</th><th></th></tr>
          </thead>
          <tbody>
            {candidatos.map((c) => {
              const si = statusInfo(c.status)
              return (
                <tr key={c.id}>
                  <td><strong>{c.nome_completo}</strong><br />
                    <small>{c.email || c.celular_whatsapp || 'sem contato — use 📋 Copiar link'}</small></td>
                  <td><span className="chip" style={{ '--chip-cor': si.cor }}>
                    {si.icone} {si.label}</span></td>
                  <td>{c.progresso_docs.total ? `${c.progresso_docs.ok}/${c.progresso_docs.total}` : '—'}</td>
                  <td>{fmtData(c.criado_em)}</td>
                  <td className="acoes-candidato">
                    <button className="btn-secundario btn-mini"
                            onClick={() => setSelecionado(c.id)}>Abrir</button>
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
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      )}
    </main>
        )}
      </div>
    </div>
  )
}
