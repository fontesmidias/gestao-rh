import { useEffect, useState } from 'react'
import { rh as api } from '../api.js'
import Detalhe from './Detalhe.jsx'
import Config from './Config.jsx'
import Colaboradores from './Colaboradores.jsx'
import logo from '../assets/logo.png'
import InputSenha from '../InputSenha.jsx'

const STATUS_CHIP = {
  convidado: ['Convidado', '#8896b3'],
  preenchendo: ['Preenchendo', '#e9a63a'],
  aguardando_assinatura: ['Assinando', '#e9a63a'],
  docs_pendentes: ['Enviando docs', '#e9a63a'],
  envio_concluido: ['Revisar! 📥', '#d9534f'],
  em_revisao: ['Em revisão', '#5bc0de'],
  aprovado: ['Aprovado ✓', '#4f9d3a'],
  reprovado_pendencias: ['Pendências', '#d9534f'],
  expurgado: ['Expurgado', '#999'],
}

export default function RHApp() {
  const [logado, setLogado] = useState(api.logado())
  const tokenReset = new URLSearchParams(window.location.search).get('redefinir')
  if (tokenReset) return <RedefinirSenha token={tokenReset} />
  if (!logado) return <Login aoEntrar={() => setLogado(true)} />
  return <Painel aoSair={() => { api.sair(); setLogado(false) }} />
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
    catch { setErro('E-mail ou senha incorretos.') }
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
    ['Tempo médio', dados.tempo_medio_dias_convite_ao_dossie == null
      ? '—' : `${dados.tempo_medio_dias_convite_ao_dossie} dias`, ''],
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

function Painel({ aoSair }) {
  const [candidatos, setCandidatos] = useState(null)
  const [metricas, setMetricas] = useState(null)
  const [selecionado, setSelecionado] = useState(null)
  const [novo, setNovo] = useState(null) // form de novo candidato
  const [convite, setConvite] = useState(null)
  const [erroConvite, setErroConvite] = useState(null)
  const [enviandoConvite, setEnviandoConvite] = useState(false)
  const [config, setConfig] = useState(false)
  const [colaboradores, setColaboradores] = useState(false)

  const recarregar = () => {
    api.candidatos().then(setCandidatos).catch((e) => {
      if (e.status === 401) aoSair()
    })
    api.metricas().then(setMetricas).catch(() => {})
  }
  useEffect(() => { recarregar() }, [])

  if (config) return <Config aoVoltar={() => setConfig(false)} />
  if (colaboradores) return (
    <Colaboradores aoVoltar={() => { setColaboradores(false); recarregar() }}
                   aoAbrir={(id) => { setColaboradores(false); setSelecionado(id) }} />
  )
  if (selecionado) return (
    <Detalhe id={selecionado} aoVoltar={() => { setSelecionado(null); recarregar() }} />
  )

  return (
    <main className="rh-painel">
      <header className="rh-topo">
        <h1><img src={logo} alt="" className="logo-topo" /> Admissões</h1>
        <div>
          <span className="rh-nome">{localStorage.getItem('rh_nome')}</span>
          <button className="btn-secundario" onClick={() => setNovo({})}>+ Novo candidato</button>
          <button className="btn-secundario" onClick={() => setColaboradores(true)}>👥 Colaboradores</button>
          <button className="btn-secundario" onClick={() => setConfig(true)}>⚙️ Configurações</button>
          <button className="btn-link" onClick={aoSair}>Sair</button>
        </div>
      </header>

      <Metricas dados={metricas} />

      {novo && (
        <div className="rh-card">
          <h3>Convidar candidato</h3>
          <p className="explica">Só o nome é obrigatório. Sem e-mail? Sem problema:
            o link aparece aqui para você copiar e mandar pelo WhatsApp — o candidato
            completa e-mail e celular na própria ficha.</p>
          <div className="linha3">
            <input placeholder="Nome completo"
                   onChange={(e) => setNovo({ ...novo, nome_completo: e.target.value })} />
            <input placeholder="E-mail (opcional)" type="email"
                   onChange={(e) => setNovo({ ...novo, email: e.target.value })} />
            <input placeholder="Celular/WhatsApp (opcional)"
                   onChange={(e) => setNovo({ ...novo, celular_whatsapp: e.target.value })} />
          </div>
          <div className="navegacao">
            <button className="btn-secundario" onClick={() => { setNovo(null); setConvite(null) }}>
              Cancelar</button>
            <button className="btn-principal" disabled={enviandoConvite} onClick={async () => {
              setErroConvite(null); setConvite(null)
              if (!novo.nome_completo?.trim()) {
                setErroConvite('Informe pelo menos o nome do candidato.'); return
              }
              setEnviandoConvite(true)
              try {
                const r = await api.novoCandidato({
                  nome_completo: novo.nome_completo.trim(),
                  email: (novo.email || '').trim() || null,
                  celular_whatsapp: (novo.celular_whatsapp || '').trim() || null,
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

      {!candidatos ? <p>Carregando…</p> : candidatos.length === 0 ? (
        <p className="explica centro">Nenhum candidato ainda. Toque em "+ Novo candidato" para
          enviar o primeiro convite.</p>
      ) : (
        <table className="rh-tabela">
          <thead>
            <tr><th>Candidato</th><th>Status</th><th>Docs</th><th>Criado</th><th></th></tr>
          </thead>
          <tbody>
            {candidatos.map((c) => {
              const [rotulo, cor] = STATUS_CHIP[c.status] || [c.status, '#888']
              return (
                <tr key={c.id}>
                  <td><strong>{c.nome_completo}</strong><br />
                    <small>{c.email || c.celular_whatsapp || 'sem contato — use 📋 Copiar link'}</small></td>
                  <td><span className="chip" style={{ background: cor }}>{rotulo}</span></td>
                  <td>{c.progresso_docs.total ? `${c.progresso_docs.ok}/${c.progresso_docs.total}` : '—'}</td>
                  <td>{new Date(c.criado_em).toLocaleDateString('pt-BR')}</td>
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
  )
}
