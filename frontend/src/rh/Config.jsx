import { useEffect, useState } from 'react'
import { rh as api } from '../api.js'

function Msg({ msg }) {
  if (!msg) return null
  return <div className={msg.tipo === 'erro' ? 'alerta' : 'sucesso'}>{msg.texto}</div>
}

export default function Config({ aoVoltar }) {
  return (
    <main className="rh-painel">
      <header className="rh-topo">
        <button className="btn-link" onClick={aoVoltar}>← Voltar</button>
        <h1>⚙️ Configurações</h1>
        <span />
      </header>
      <Perfil />
      <Senha />
      <M365 />
      <Smtp />
      <Auditoria />
    </main>
  )
}

function Perfil() {
  const [dados, setDados] = useState(null)
  const [msg, setMsg] = useState(null)
  useEffect(() => { api.meuPerfil().then(setDados) }, [])
  if (!dados) return null
  return (
    <div className="rh-card">
      <h3>Meu perfil</h3>
      <div className="linha2">
        <label className="campo"><span className="rotulo">Nome</span>
          <input value={dados.nome} onChange={(e) => setDados({ ...dados, nome: e.target.value })} /></label>
        <label className="campo"><span className="rotulo">E-mail (login)</span>
          <input type="email" value={dados.email}
                 onChange={(e) => setDados({ ...dados, email: e.target.value })} /></label>
      </div>
      <button className="btn-secundario" onClick={async () => {
        setMsg(null)
        try {
          const r = await api.salvarPerfil({ nome: dados.nome.trim(), email: dados.email.trim() })
          localStorage.setItem('rh_nome', r.nome)
          setMsg({ tipo: 'ok', texto: 'Perfil atualizado. Use o novo e-mail no próximo login.' })
        } catch (e) {
          let texto = 'Não foi possível salvar.'
          if (e.detail === 'email_ja_utilizado') texto = 'Este e-mail já é usado por outro usuário.'
          else if (Array.isArray(e.detail)) {
            texto = 'Confira: ' + e.detail.map((d) => `${d.loc?.slice(-1)[0]}: ${d.msg}`).join('; ')
          }
          setMsg({ tipo: 'erro', texto })
        }
      }}>Salvar perfil</button>
      <Msg msg={msg} />
    </div>
  )
}

function Senha() {
  const [atual, setAtual] = useState('')
  const [nova, setNova] = useState('')
  const [msg, setMsg] = useState(null)
  return (
    <div className="rh-card">
      <h3>Trocar senha</h3>
      <div className="linha2">
        <label className="campo"><span className="rotulo">Senha atual</span>
          <input type="password" value={atual} onChange={(e) => setAtual(e.target.value)} /></label>
        <label className="campo"><span className="rotulo">Nova senha (mín. 8 caracteres)</span>
          <input type="password" value={nova} onChange={(e) => setNova(e.target.value)} /></label>
      </div>
      <button className="btn-secundario" disabled={!atual || nova.length < 8} onClick={async () => {
        setMsg(null)
        try {
          await api.trocarSenha(atual, nova)
          setAtual(''); setNova('')
          setMsg({ tipo: 'ok', texto: 'Senha alterada com sucesso.' })
        } catch (e) {
          setMsg({ tipo: 'erro', texto: e.detail === 'senha_atual_incorreta'
            ? 'A senha atual está incorreta.' : 'Não foi possível trocar a senha.' })
        }
      }}>Trocar senha</button>
      <Msg msg={msg} />
    </div>
  )
}

function M365() {
  const [cfg, setCfg] = useState(null)
  const [secret, setSecret] = useState('')
  const [msg, setMsg] = useState(null)
  const recarregar = () => api.verM365().then(setCfg)
  useEffect(() => { recarregar() }, [])
  if (!cfg) return null
  return (
    <div className="rh-card">
      <h3>Microsoft 365 (recomendado)</h3>
      {cfg.conectado ? (
        <>
          <div className="sucesso">✅ Conectado como <strong>{cfg.conta}</strong> — os e-mails
            do sistema saem por esta conta (via Microsoft Graph).</div>
          <button className="btn-secundario" style={{ marginTop: '.75rem' }} onClick={async () => {
            await api.desconectarM365(); recarregar()
          }}>Desconectar</button>
        </>
      ) : (
        <>
          <p className="explica">Conecte a conta do Office com um clique. Antes, o administrador
            registra um aplicativo (uma única vez) em <strong>entra.microsoft.com</strong> →
            <em> Identity → App registrations → New registration</em>:
            plataforma <em>Web</em>, redirect URI <code>{cfg.redirect_uri}</code>;
            em <em>API permissions</em> adicione <code>Mail.Send</code> e <code>User.Read</code>
            (delegadas); em <em>Certificates &amp; secrets</em> crie um segredo.
            Copie os valores para cá:</p>
          <div className="linha3">
            <input placeholder="Application (client) ID" value={cfg.client_id}
                   onChange={(e) => setCfg({ ...cfg, client_id: e.target.value })} />
            <input placeholder="Directory (tenant) ID" value={cfg.tenant_id}
                   onChange={(e) => setCfg({ ...cfg, tenant_id: e.target.value })} />
            <input placeholder={cfg.secret_definido ? 'Segredo (já definido)' : 'Client secret'}
                   type="password" value={secret} onChange={(e) => setSecret(e.target.value)} />
          </div>
          <div className="navegacao">
            <button className="btn-secundario" onClick={async () => {
              setMsg(null)
              await api.salvarM365({ client_id: cfg.client_id.trim(),
                                     tenant_id: cfg.tenant_id.trim(),
                                     client_secret: secret.trim() || null })
              setSecret('')
              setMsg({ tipo: 'ok', texto: 'Dados do aplicativo salvos.' })
              recarregar()
            }}>Salvar</button>
            <button className="btn-principal btn-mini" onClick={async () => {
              setMsg(null)
              try {
                const { url } = await api.urlLoginM365()
                const popup = window.open(url, 'm365', 'width=520,height=640')
                const timer = setInterval(() => {
                  if (popup && popup.closed) { clearInterval(timer); recarregar() }
                }, 800)
              } catch (e) {
                setMsg({ tipo: 'erro', texto: e.detail === 'configure_client_id_primeiro'
                  ? 'Salve primeiro o Client ID / Tenant / Segredo do aplicativo.'
                  : 'Não foi possível iniciar a conexão.' })
              }
            }}>Conectar com a conta Microsoft</button>
          </div>
        </>
      )}
      <Msg msg={msg} />
    </div>
  )
}

function Smtp() {
  const [cfg, setCfg] = useState(null)
  const [senha, setSenha] = useState('')
  const [msg, setMsg] = useState(null)
  const [testando, setTestando] = useState(false)
  useEffect(() => { api.verSmtp().then(setCfg) }, [])
  if (!cfg) return null
  return (
    <div className="rh-card">
      <h3>E-mail (SMTP) — alternativa ao Microsoft 365</h3>
      <p className="explica">Usado apenas se o Microsoft 365 acima não estiver conectado.</p>
      <p className="explica">Para <strong>Microsoft 365</strong>: servidor
        <code> smtp.office365.com</code>, porta <code>587</code>, usuário = seu e-mail completo.
        Importante: o administrador precisa habilitar o <em>"Authenticated SMTP"</em> para a
        caixa (Centro de administração do Exchange → caixa de correio → Email apps). Se a conta
        tem MFA, crie uma <em>senha de aplicativo</em> e use aqui no lugar da senha normal.</p>
      <div className="linha2">
        <label className="campo"><span className="rotulo">Servidor SMTP</span>
          <input placeholder="smtp.office365.com" value={cfg.smtp_host || ''}
                 onChange={(e) => setCfg({ ...cfg, smtp_host: e.target.value })} /></label>
        <label className="campo"><span className="rotulo">Porta</span>
          <input type="number" value={cfg.smtp_port || 587}
                 onChange={(e) => setCfg({ ...cfg, smtp_port: Number(e.target.value) })} /></label>
      </div>
      <div className="linha2">
        <label className="campo"><span className="rotulo">Usuário (e-mail completo)</span>
          <input placeholder="rh@greenhousedf.com.br" value={cfg.smtp_user || ''}
                 onChange={(e) => setCfg({ ...cfg, smtp_user: e.target.value })} /></label>
        <label className="campo">
          <span className="rotulo">Senha {cfg.senha_definida && '(já definida — preencha só para trocar)'}</span>
          <input type="password" value={senha} onChange={(e) => setSenha(e.target.value)} /></label>
      </div>
      <label className="campo"><span className="rotulo">Remetente (De:)</span>
        <input value={cfg.smtp_from || ''}
               onChange={(e) => setCfg({ ...cfg, smtp_from: e.target.value })} /></label>
      <div className="navegacao">
        <button className="btn-secundario" onClick={async () => {
          setMsg(null)
          try {
            const r = await api.salvarSmtp({ ...cfg, smtp_password: senha || null })
            setCfg(r); setSenha('')
            setMsg({ tipo: 'ok', texto: 'Configuração salva.' })
          } catch { setMsg({ tipo: 'erro', texto: 'Não foi possível salvar. Confira os campos.' }) }
        }}>Salvar</button>
        <button className="btn-principal btn-mini" disabled={testando} onClick={async () => {
          setMsg(null); setTestando(true)
          try {
            const salvo = await api.salvarSmtp({ ...cfg, smtp_password: senha || null })
            setCfg(salvo); setSenha('')
            const r = await api.testarSmtp()
            setMsg({ tipo: 'ok', texto: `E-mail de teste enviado para ${r.enviado_para} — confira a caixa de entrada.` })
          } catch (e) {
            setMsg({ tipo: 'erro', texto: `Teste falhou: ${e.detail}` })
          } finally { setTestando(false) }
        }}>{testando ? 'Testando…' : 'Salvar acima e testar envio'}</button>
      </div>
      <Msg msg={msg} />
    </div>
  )
}

function Auditoria() {
  const [eventos, setEventos] = useState(null)
  const [aberto, setAberto] = useState(false)
  return (
    <div className="rh-card">
      <h3>Auditoria</h3>
      <p className="explica">Registro de tudo que acontece no sistema: logins, convites, envios,
        assinaturas, aprovações, alterações de configuração.</p>
      {!aberto ? (
        <button className="btn-secundario" onClick={async () => {
          setEventos(await api.auditoria()); setAberto(true)
        }}>Ver últimos eventos</button>
      ) : !eventos ? <p>Carregando…</p> : (
        <table className="rh-tabela">
          <thead><tr><th>Quando</th><th>Ação</th><th>Ator</th><th>Detalhe</th></tr></thead>
          <tbody>
            {eventos.map((e, i) => (
              <tr key={i}>
                <td>{new Date(e.quando).toLocaleString('pt-BR')}</td>
                <td>{e.acao}</td>
                <td>{e.ator}{e.ator_detalhe ? ` (${e.ator_detalhe})` : ''}</td>
                <td><small>{e.detalhe ? JSON.stringify(e.detalhe) : ''}</small></td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  )
}
