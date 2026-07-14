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
          const r = await api.salvarPerfil(dados)
          localStorage.setItem('rh_nome', r.nome)
          setMsg({ tipo: 'ok', texto: 'Perfil atualizado. Use o novo e-mail no próximo login.' })
        } catch (e) {
          setMsg({ tipo: 'erro', texto: e.detail === 'email_ja_utilizado'
            ? 'Este e-mail já é usado por outro usuário.' : 'Não foi possível salvar.' })
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

function Smtp() {
  const [cfg, setCfg] = useState(null)
  const [senha, setSenha] = useState('')
  const [msg, setMsg] = useState(null)
  const [testando, setTestando] = useState(false)
  useEffect(() => { api.verSmtp().then(setCfg) }, [])
  if (!cfg) return null
  return (
    <div className="rh-card">
      <h3>E-mail (SMTP)</h3>
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
