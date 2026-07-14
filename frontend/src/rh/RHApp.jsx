import { useEffect, useState } from 'react'
import { rh as api } from '../api.js'
import Detalhe from './Detalhe.jsx'
import Config from './Config.jsx'

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
  if (!logado) return <Login aoEntrar={() => setLogado(true)} />
  return <Painel aoSair={() => { api.sair(); setLogado(false) }} />
}

function Login({ aoEntrar }) {
  const [email, setEmail] = useState('')
  const [senha, setSenha] = useState('')
  const [erro, setErro] = useState(null)
  const entrar = async (e) => {
    e.preventDefault()
    try { await api.login(email, senha); aoEntrar() }
    catch { setErro('E-mail ou senha incorretos.') }
  }
  return (
    <main className="cartao rh-login">
      <h1>🌱 Painel do RH</h1>
      <form onSubmit={entrar}>
        <label className="campo"><span className="rotulo">E-mail</span>
          <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} /></label>
        <label className="campo"><span className="rotulo">Senha</span>
          <input type="password" value={senha} onChange={(e) => setSenha(e.target.value)} /></label>
        {erro && <div className="alerta">{erro}</div>}
        <button className="btn-principal" type="submit">Entrar</button>
      </form>
    </main>
  )
}

function Painel({ aoSair }) {
  const [candidatos, setCandidatos] = useState(null)
  const [selecionado, setSelecionado] = useState(null)
  const [novo, setNovo] = useState(null) // form de novo candidato
  const [convite, setConvite] = useState(null)
  const [erroConvite, setErroConvite] = useState(null)
  const [enviandoConvite, setEnviandoConvite] = useState(false)
  const [config, setConfig] = useState(false)

  const recarregar = () => api.candidatos().then(setCandidatos).catch((e) => {
    if (e.status === 401) aoSair()
  })
  useEffect(() => { recarregar() }, [])

  if (config) return <Config aoVoltar={() => setConfig(false)} />
  if (selecionado) return (
    <Detalhe id={selecionado} aoVoltar={() => { setSelecionado(null); recarregar() }} />
  )

  return (
    <main className="rh-painel">
      <header className="rh-topo">
        <h1>🌱 Admissões</h1>
        <div>
          <span className="rh-nome">{localStorage.getItem('rh_nome')}</span>
          <button className="btn-secundario" onClick={() => setNovo({})}>+ Novo candidato</button>
          <button className="btn-secundario" onClick={() => setConfig(true)}>⚙️ Configurações</button>
          <button className="btn-link" onClick={aoSair}>Sair</button>
        </div>
      </header>

      {novo && (
        <div className="rh-card">
          <h3>Convidar candidato</h3>
          <div className="linha3">
            <input placeholder="Nome completo"
                   onChange={(e) => setNovo({ ...novo, nome_completo: e.target.value })} />
            <input placeholder="E-mail" type="email"
                   onChange={(e) => setNovo({ ...novo, email: e.target.value })} />
            <input placeholder="Celular/WhatsApp"
                   onChange={(e) => setNovo({ ...novo, celular_whatsapp: e.target.value })} />
          </div>
          <div className="navegacao">
            <button className="btn-secundario" onClick={() => { setNovo(null); setConvite(null) }}>
              Cancelar</button>
            <button className="btn-principal" disabled={enviandoConvite} onClick={async () => {
              setErroConvite(null); setConvite(null)
              if (!novo.nome_completo || !novo.email || !novo.celular_whatsapp) {
                setErroConvite('Preencha nome, e-mail e celular.'); return
              }
              setEnviandoConvite(true)
              try {
                const r = await api.novoCandidato(novo)
                setConvite(r)
                recarregar()
              } catch (e) {
                setErroConvite(e.status === 422
                  ? 'E-mail inválido — confira o endereço digitado.'
                  : `Não foi possível criar o convite (${e.detail || e.message}).`)
              } finally { setEnviandoConvite(false) }
            }}>{enviandoConvite ? 'Criando…' : 'Convidar e enviar link'}</button>
          </div>
          {erroConvite && <div className="alerta">{erroConvite}</div>}
          {convite && (
            <div className="sucesso">
              Link mágico criado{convite.email_enviado ? ' e enviado por e-mail ✓' : ''}.
              {!convite.email_enviado && <> E-mail não configurado — envie manualmente
                (WhatsApp):</>}
              <code className="link-copiar">{convite.link_magico}</code>
              <button className="btn-link" onClick={() =>
                navigator.clipboard.writeText(convite.link_magico)}>copiar</button>
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
                  <td><strong>{c.nome_completo}</strong><br /><small>{c.email}</small></td>
                  <td><span className="chip" style={{ background: cor }}>{rotulo}</span></td>
                  <td>{c.progresso_docs.total ? `${c.progresso_docs.ok}/${c.progresso_docs.total}` : '—'}</td>
                  <td>{new Date(c.criado_em).toLocaleDateString('pt-BR')}</td>
                  <td>
                    <button className="btn-secundario btn-mini"
                            onClick={() => setSelecionado(c.id)}>Abrir</button>
                    <button className="btn-link" title="Gera novo link e reenvia o convite"
                            onClick={async () => {
                              const r = await api.reenviarLink(c.id)
                              navigator.clipboard.writeText(r.link_magico)
                              alert(`Novo link gerado${r.email_enviado ? ' e enviado por e-mail' : ''} — copiado para a área de transferência.`)
                            }}>reenviar link</button>
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
