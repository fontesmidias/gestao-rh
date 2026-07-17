import { useEffect, useState } from 'react'
import { fmtDataHora } from '../fmt.js'
import { rh as api } from '../api.js'
import InputSenha from '../InputSenha.jsx'

// OCR assistido por IA (Mistral): melhora muito a leitura de fotos de
// celular. Opcional — sem chave, o OCR local (Tesseract) continua valendo.
function OcrIA() {
  const [cfg, setCfg] = useState(null)
  const [chave, setChave] = useState('')
  const [msg, setMsg] = useState(null)
  const [ocupado, setOcupado] = useState(false)

  const carregar = () => api.verOcr().then(setCfg).catch(() => {})
  useEffect(() => { carregar() }, [])
  if (!cfg) return null

  return (
    <section className="rh-card">
      <h3>🤖 OCR com IA (Mistral)</h3>
      <p className="explica">A leitura dos documentos passa a usar a IA da Mistral —
        muito mais precisa em fotos de celular. Crie uma chave gratuita em
        console.mistral.ai → API Keys e cole abaixo. Sem chave (ou se a API falhar),
        o leitor local continua funcionando normalmente.
        <br /><strong>LGPD:</strong> com a IA ativada, as imagens dos documentos são
        enviadas ao serviço da Mistral exclusivamente para leitura — o aviso de
        privacidade do candidato já contempla esse tratamento.</p>
      <div className="linha2">
        <InputSenha placeholder={cfg.chave_definida ? 'Chave (já definida)' : 'Chave da API Mistral'}
                    value={chave} onChange={(e) => setChave(e.target.value)} />
        <span>
          <button className="btn-principal btn-mini" disabled={ocupado} onClick={async () => {
            setMsg(null); setOcupado(true)
            try {
              const r = await api.salvarOcr({ mistral_api_key: chave.trim() })
              setCfg(r); setChave('')
              setMsg({ tipo: 'ok', texto: r.chave_definida
                ? 'Chave salva — use "Testar leitura" para confirmar.'
                : 'OCR com IA desligado (leitor local em uso).' })
            } catch (e) {
              setMsg({ tipo: 'erro', texto: `Não foi possível salvar (${e.detail || e.message}).` })
            } finally { setOcupado(false) }
          }}>Salvar</button>{' '}
          <button className="btn-secundario btn-mini" disabled={ocupado || !cfg.chave_definida}
                  onClick={async () => {
                    setMsg(null); setOcupado(true)
                    try {
                      const r = await api.testarOcr()
                      setMsg({ tipo: 'ok', texto: `A IA leu: "${r.texto_lido}" — funcionando!` })
                    } catch (e) {
                      setMsg({ tipo: 'erro', texto: `Teste falhou: ${e.detail || e.message}` })
                    } finally { setOcupado(false) }
                  }}>Testar leitura</button>
        </span>
      </div>
      <p className="explica">Status: {cfg.chave_definida
        ? '✅ IA ativada (com leitor local de reserva)' : '⭕ usando apenas o leitor local'}</p>
      <Msg msg={msg} />
    </section>
  )
}

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
      <Equipe />
      <Postos />
      <Assinantes />
      <M365 />
      <Gmail />
      <WebhookEmail />
      <Smtp />
      <OcrIA />
      <ModelosDocumento />
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
          <InputSenha value={atual} onChange={(e) => setAtual(e.target.value)} /></label>
        <label className="campo"><span className="rotulo">Nova senha (mín. 8 caracteres)</span>
          <InputSenha value={nova} onChange={(e) => setNova(e.target.value)} /></label>
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

function Assinantes() {
  const [dados, setDados] = useState(null)
  const [msg, setMsg] = useState(null)
  useEffect(() => { api.verAssinantes().then(setDados) }, [])
  if (!dados) return null
  const campo = (chave, rotulo) => (
    <label className="campo"><span className="rotulo">{rotulo}</span>
      <input value={dados[chave] || ''}
             onChange={(e) => setDados({ ...dados, [chave]: e.target.value })} /></label>
  )
  return (
    <div className="rh-card">
      <h3>Assinantes dos documentos oficiais</h3>
      <p className="explica">Representantes da empresa que constam nos ofícios e documentos
        de posto de serviço (nome, cargo e CPF). A alteração vale para documentos gerados
        daqui em diante — vias já assinadas não mudam.</p>
      <div className="linha3">
        {campo('ass1_nome', 'Assinante 1 — nome')}
        {campo('ass1_cargo', 'Cargo')}
        {campo('ass1_cpf', 'CPF')}
      </div>
      <div className="linha3">
        {campo('ass2_nome', 'Assinante 2 — nome')}
        {campo('ass2_cargo', 'Cargo')}
        {campo('ass2_cpf', 'CPF')}
      </div>
      <button className="btn-secundario" onClick={async () => {
        setMsg(null)
        try {
          const r = await api.salvarAssinantes(dados)
          setDados(r); setMsg({ tipo: 'ok', texto: 'Assinantes atualizados.' })
        } catch (e) {
          setMsg({ tipo: 'erro', texto: `Não foi possível salvar (${e.detail || e.message}).` })
        }
      }}>Salvar assinantes</button>
      <Msg msg={msg} />
    </div>
  )
}

function Postos() {
  const [postos, setPostos] = useState(null)
  const [novo, setNovo] = useState(null) // {nome, contrato_ref}
  const [msg, setMsg] = useState(null)
  const recarregar = () => api.postos().then(setPostos)
  useEffect(() => { recarregar() }, [])
  if (!postos) return null
  return (
    <div className="rh-card">
      <h3>Postos de serviço</h3>
      <p className="explica">Postos com documentação específica (ex.: INFRAERO). Ao vincular
        um colaborador a um posto (na tela do candidato), os documentos adicionais são gerados
        e enviados para assinatura eletrônica automaticamente.</p>
      {postos.length > 0 && (
        <table className="rh-tabela">
          <thead><tr><th>Posto</th><th>Contrato (referência)</th></tr></thead>
          <tbody>
            {postos.map((p) => (
              <tr key={p.id}><td><strong>{p.nome}</strong></td><td>{p.contrato_ref || '—'}</td></tr>
            ))}
          </tbody>
        </table>
      )}
      {!novo ? (
        <button className="btn-secundario" style={{ marginTop: '.75rem' }}
                onClick={() => setNovo({ nome: '', contrato_ref: '' })}>+ Novo posto</button>
      ) : (
        <div style={{ marginTop: '.75rem' }}>
          <div className="linha2">
            <input placeholder="Nome do posto (ex.: INFRAERO)" value={novo.nome}
                   onChange={(e) => setNovo({ ...novo, nome: e.target.value })} />
            <input placeholder="Contrato (ex.: 0053-OS 2025_0001)" value={novo.contrato_ref}
                   onChange={(e) => setNovo({ ...novo, contrato_ref: e.target.value })} />
          </div>
          <div className="navegacao">
            <button className="btn-secundario" onClick={() => setNovo(null)}>Cancelar</button>
            <button className="btn-principal" onClick={async () => {
              setMsg(null)
              try {
                await api.criarPosto({ nome: novo.nome.trim(), contrato_ref: novo.contrato_ref.trim() || null })
                setNovo(null); setMsg({ tipo: 'ok', texto: 'Posto criado.' })
                await recarregar()
              } catch (e) {
                setMsg({ tipo: 'erro', texto: e.detail === 'posto_ja_existe'
                  ? 'Já existe um posto com esse nome.'
                  : `Não foi possível criar (${e.detail || e.message}).` })
              }
            }}>Criar posto</button>
          </div>
        </div>
      )}
      <Msg msg={msg} />
    </div>
  )
}

const ERROS_EQUIPE = {
  email_ja_utilizado: 'Este e-mail já é usado por outro usuário.',
  senha_curta_minimo_8: 'A senha precisa ter no mínimo 8 caracteres.',
  nome_obrigatorio: 'Informe o nome.',
  nao_pode_desativar_a_si_mesmo: 'Você não pode desativar o seu próprio acesso.',
  ultimo_usuario_ativo: 'Este é o último usuário ativo — desativá-lo trancaria todo mundo para fora.',
}

function erroEquipe(e) {
  if (ERROS_EQUIPE[e.detail]) return ERROS_EQUIPE[e.detail]
  if (Array.isArray(e.detail)) {
    return 'Confira: ' + e.detail.map((d) => `${d.loc?.slice(-1)[0]}: ${d.msg}`).join('; ')
  }
  return `Não foi possível concluir (${e.detail || e.message}).`
}

function Equipe() {
  const [usuarios, setUsuarios] = useState(null)
  const [novo, setNovo] = useState(null) // {nome, email, senha}
  const [senhaDe, setSenhaDe] = useState(null) // id do usuário em redefinição
  const [novaSenha, setNovaSenha] = useState('')
  const [editando, setEditando] = useState(null) // {id, nome, email}
  const [salvando, setSalvando] = useState(false)
  const [msg, setMsg] = useState(null)
  const recarregar = () => api.usuarios().then(setUsuarios)
  useEffect(() => { recarregar() }, [])
  if (!usuarios) return null

  return (
    <div className="rh-card">
      <h3>Equipe do RH</h3>
      <p className="explica">Quem pode entrar no painel. Em vez de excluir, desative o acesso —
        o histórico de auditoria do usuário é preservado.</p>
      <table className="rh-tabela">
        <thead><tr><th>Nome</th><th>E-mail (login)</th><th>Situação</th><th></th></tr></thead>
        <tbody>
          {usuarios.map((u) => (
            <tr key={u.id} style={u.ativo ? {} : { opacity: .55 }}>
              <td>
                {editando?.id === u.id ? (
                  <input value={editando.nome}
                         onChange={(e) => setEditando({ ...editando, nome: e.target.value })} />
                ) : <><strong>{u.nome}</strong>{u.sou_eu && <em> (você)</em>}</>}
              </td>
              <td>
                {editando?.id === u.id ? (
                  <input type="email" value={editando.email}
                         onChange={(e) => setEditando({ ...editando, email: e.target.value })} />
                ) : u.email}
              </td>
              <td>{u.ativo ? 'Ativo' : 'Desativado'}</td>
              <td>
                {editando?.id === u.id ? (
                  <>
                    <button className="btn-principal btn-mini" disabled={salvando} onClick={async () => {
                      setMsg(null); setSalvando(true)
                      try {
                        await api.editarUsuario(u.id, { nome: editando.nome.trim(),
                                                        email: editando.email.trim() })
                        setEditando(null)
                        setMsg({ tipo: 'ok', texto: 'Usuário atualizado.' })
                        await recarregar()
                      } catch (e) { setMsg({ tipo: 'erro', texto: erroEquipe(e) }) }
                      finally { setSalvando(false) }
                    }}>{salvando ? 'Salvando…' : 'Salvar'}</button>
                    <button className="btn-link" onClick={() => setEditando(null)}>cancelar</button>
                  </>
                ) : (
                  <>
                    <button className="btn-secundario btn-mini"
                            onClick={() => { setEditando({ id: u.id, nome: u.nome, email: u.email }); setSenhaDe(null) }}>
                      Editar</button>
                    <button className="btn-secundario btn-mini"
                            onClick={() => { setSenhaDe(senhaDe === u.id ? null : u.id); setNovaSenha(''); setEditando(null) }}>
                      Redefinir senha</button>
                    {!u.sou_eu && (
                      <button className={u.ativo ? 'btn-rejeitar btn-mini' : 'btn-principal btn-mini'}
                              onClick={async () => {
                                setMsg(null)
                                try {
                                  await api.editarUsuario(u.id, { ativo: !u.ativo })
                                  setMsg({ tipo: 'ok', texto: u.ativo
                                    ? `Acesso de ${u.nome} desativado.`
                                    : `Acesso de ${u.nome} reativado.` })
                                  await recarregar()
                                } catch (e) { setMsg({ tipo: 'erro', texto: erroEquipe(e) }) }
                              }}>{u.ativo ? 'Desativar' : 'Reativar'}</button>
                    )}
                  </>
                )}
                {senhaDe === u.id && (
                  <div className="rejeicao">
                    <InputSenha placeholder="Nova senha (mín. 8 caracteres)"
                           value={novaSenha} onChange={(e) => setNovaSenha(e.target.value)} />
                    <button className="btn-principal btn-mini" disabled={novaSenha.length < 8}
                            onClick={async () => {
                              setMsg(null)
                              try {
                                await api.redefinirSenhaUsuario(u.id, novaSenha)
                                setSenhaDe(null); setNovaSenha('')
                                setMsg({ tipo: 'ok', texto: `Senha de ${u.nome} redefinida — informe a nova senha pessoalmente.` })
                              } catch (e) { setMsg({ tipo: 'erro', texto: erroEquipe(e) }) }
                            }}>Confirmar</button>
                  </div>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      {!novo ? (
        <button className="btn-secundario" style={{ marginTop: '.75rem' }}
                onClick={() => setNovo({ nome: '', email: '', senha: '' })}>+ Novo usuário</button>
      ) : (
        <div style={{ marginTop: '.75rem' }}>
          <div className="linha3">
            <input placeholder="Nome completo" value={novo.nome}
                   onChange={(e) => setNovo({ ...novo, nome: e.target.value })} />
            <input placeholder="E-mail (será o login)" type="email" value={novo.email}
                   onChange={(e) => setNovo({ ...novo, email: e.target.value })} />
            <InputSenha placeholder="Senha inicial (mín. 8)" value={novo.senha}
                   onChange={(e) => setNovo({ ...novo, senha: e.target.value })} />
          </div>
          <div className="navegacao">
            <button className="btn-secundario" onClick={() => setNovo(null)}>Cancelar</button>
            <button className="btn-principal" disabled={salvando}
                    onClick={async () => {
                      setMsg(null)
                      if (!novo.nome.trim() || !novo.email.trim() || novo.senha.length < 8) {
                        setMsg({ tipo: 'erro', texto: 'Preencha nome, e-mail e uma senha com no mínimo 8 caracteres.' })
                        return
                      }
                      setSalvando(true)
                      try {
                        const r = await api.criarUsuario({ nome: novo.nome.trim(),
                                                           email: novo.email.trim(),
                                                           senha: novo.senha })
                        setNovo(null)
                        setMsg({ tipo: 'ok', texto: r.email_enviado
                          ? `Usuário criado. ${r.nome} recebeu um e-mail com as instruções de acesso — informe a senha inicial pessoalmente.`
                          : `Usuário criado. O e-mail de boas-vindas não pôde ser enviado — informe o endereço ${r.email} e a senha inicial pessoalmente.` })
                        await recarregar()
                      } catch (e) { setMsg({ tipo: 'erro', texto: erroEquipe(e) }) }
                      finally { setSalvando(false) }
                    }}>{salvando ? 'Criando…' : 'Criar usuário'}</button>
          </div>
        </div>
      )}
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
            plataforma <em>Web</em>, redirect URI <code>{cfg.redirect_uri}</code> (este
            endereço acompanha automaticamente como você está acessando o painel — se
            usar ora IP, ora domínio, registre os dois no aplicativo);
            em <em>API permissions</em> adicione <code>Mail.Send</code> e <code>User.Read</code>
            (delegadas); em <em>Certificates &amp; secrets</em> crie um segredo.
            Copie os valores para cá:</p>
          <div className="linha3">
            <input placeholder="Application (client) ID" value={cfg.client_id}
                   onChange={(e) => setCfg({ ...cfg, client_id: e.target.value })} />
            <input placeholder="Directory (tenant) ID" value={cfg.tenant_id}
                   onChange={(e) => setCfg({ ...cfg, tenant_id: e.target.value })} />
            <InputSenha placeholder={cfg.secret_definido ? 'Segredo (já definido)' : 'Client secret'}
                    value={secret} onChange={(e) => setSecret(e.target.value)} />
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

function Gmail() {
  const [cfg, setCfg] = useState(null)
  const [secret, setSecret] = useState('')
  const [msg, setMsg] = useState(null)
  const recarregar = () => api.verGmail().then(setCfg)
  useEffect(() => { recarregar() }, [])
  if (!cfg) return null
  return (
    <div className="rh-card">
      <h3>Google / Gmail (alternativa ao Microsoft 365)</h3>
      <p className="explica">Usado se o Microsoft 365 acima não estiver conectado. É o
        "Fazer login com o Google" que o próprio Google recomenda no lugar de senhas de app.</p>
      {cfg.conectado ? (
        <>
          <div className="sucesso">✅ Conectado como <strong>{cfg.conta}</strong> — os e-mails
            do sistema saem por esta conta (via Gmail).</div>
          <button className="btn-secundario" style={{ marginTop: '.75rem' }} onClick={async () => {
            await api.desconectarGmail(); recarregar()
          }}>Desconectar</button>
        </>
      ) : (
        <>
          <p className="explica">Configuração única em <strong>console.cloud.google.com</strong>:
            crie um projeto → <em>APIs &amp; Services → Enable APIs</em> e habilite a
            <em> Gmail API</em> → <em>OAuth consent screen</em> (tipo External; adicione seu
            e-mail como test user, ou publique o app) → <em>Credentials → Create credentials →
            OAuth client ID</em>, tipo <em>Web application</em>, com o redirect URI
            <code> {cfg.redirect_uri}</code> (este endereço acompanha como você está acessando o
            painel — o Google só aceita <strong>https://</strong> ou <strong>localhost</strong>;
            por IP não funciona, use com domínio). Copie os valores para cá:</p>
          <div className="linha2">
            <input placeholder="Client ID (…apps.googleusercontent.com)" value={cfg.client_id}
                   onChange={(e) => setCfg({ ...cfg, client_id: e.target.value })} />
            <InputSenha placeholder={cfg.secret_definido ? 'Client secret (já definido)' : 'Client secret'}
                    value={secret} onChange={(e) => setSecret(e.target.value)} />
          </div>
          <div className="navegacao">
            <button className="btn-secundario" onClick={async () => {
              setMsg(null)
              try {
                await api.salvarGmail({ client_id: cfg.client_id.trim(),
                                        client_secret: secret.trim() || null })
                setSecret('')
                setMsg({ tipo: 'ok', texto: 'Dados do aplicativo salvos.' })
                recarregar()
              } catch (e) {
                setMsg({ tipo: 'erro', texto: `Não foi possível salvar (${e.detail || e.message}).` })
              }
            }}>Salvar</button>
            <button className="btn-principal btn-mini" onClick={async () => {
              setMsg(null)
              try {
                const { url } = await api.urlLoginGmail()
                const popup = window.open(url, 'gmail', 'width=520,height=640')
                const timer = setInterval(() => {
                  if (popup && popup.closed) { clearInterval(timer); recarregar() }
                }, 800)
              } catch (e) {
                setMsg({ tipo: 'erro', texto: e.detail === 'configure_client_id_primeiro'
                  ? 'Salve primeiro o Client ID / Client secret do aplicativo.'
                  : 'Não foi possível iniciar a conexão.' })
              }
            }}>Conectar com a conta Google</button>
          </div>
        </>
      )}
      <Msg msg={msg} />
    </div>
  )
}

function WebhookEmail() {
  const [cfg, setCfg] = useState(null)
  const [url, setUrl] = useState('')
  const [msg, setMsg] = useState(null)
  const [ocupado, setOcupado] = useState(false)
  const recarregar = () => api.verWebhook().then(setCfg).catch(() => {})
  useEffect(() => { recarregar() }, [])
  if (!cfg) return null
  return (
    <div className="rh-card">
      <h3>Power Automate (webhook) — sem depender do admin do Microsoft 365</h3>
      <p className="explica">Caminho "plug and play" para quando o administrador do Office bloqueia
        tanto o SMTP autenticado quanto o registro de aplicativo: você cria um fluxo no
        <strong> Power Automate</strong> e o sistema só manda os dados do e-mail para ele.
        Usado quando o Microsoft 365 e o Google acima não estiverem conectados.</p>
      <details style={{ margin: '.2rem 0 .8rem' }}>
        <summary style={{ cursor: 'pointer', color: 'var(--verde-escuro)' }}>Como montar o fluxo (uma vez)</summary>
        <ol className="explica" style={{ marginTop: '.5rem' }}>
          <li>Em <strong>make.powerautomate.com</strong> → <em>Criar → Fluxo de nuvem instantâneo</em>,
            gatilho <em>"Quando uma solicitação HTTP é recebida"</em>.</li>
          <li>No corpo do JSON, use as propriedades: <code>para</code>, <code>assunto</code>,
            <code> texto</code>, <code>html</code> e <code>anexos</code> (lista com
            <code> nome</code>, <code>tipo</code> e <code>conteudo_base64</code>).</li>
          <li>Adicione a ação <em>Office 365 Outlook → Enviar um email (V2)</em>: Para = <code>para</code>,
            Assunto = <code>assunto</code>, Corpo = <code>html</code>. Para anexos, use
            <em> Base64ToBinary(item()?['conteudo_base64'])</em> num "Aplicar a cada".</li>
          <li>Salve, copie a <strong>URL HTTP POST</strong> gerada e cole abaixo.</li>
        </ol>
      </details>
      {cfg.configurado && (
        <div className="sucesso" style={{ marginBottom: '.6rem' }}>✅ Fluxo configurado
          (<code>{cfg.url_mascarada}</code>) — os e-mails saem por ele quando o M365/Google
          não estiverem conectados.</div>
      )}
      <label className="campo"><span className="rotulo">URL do fluxo (HTTP POST, https://…)</span>
        <InputSenha placeholder={cfg.configurado ? 'URL já definida — preencha para trocar' : 'Cole a URL do gatilho HTTP'}
                    value={url} onChange={(e) => setUrl(e.target.value)} /></label>
      <div className="navegacao">
        <button className="btn-secundario" disabled={ocupado} onClick={async () => {
          setMsg(null); setOcupado(true)
          try {
            const r = await api.salvarWebhook({ webhook_url: url.trim() })
            setCfg(r); setUrl('')
            setMsg({ tipo: 'ok', texto: r.configurado
              ? 'URL salva — use "Testar envio" para confirmar.'
              : 'Webhook desligado.' })
          } catch (e) {
            setMsg({ tipo: 'erro', texto: e.detail === 'url_precisa_ser_https'
              ? 'A URL precisa começar com https://.'
              : `Não foi possível salvar (${e.detail || e.message}).` })
          } finally { setOcupado(false) }
        }}>Salvar</button>
        <button className="btn-principal btn-mini" disabled={ocupado || !cfg.configurado}
                onClick={async () => {
                  setMsg(null); setOcupado(true)
                  try {
                    const r = await api.testarWebhook()
                    setMsg({ tipo: 'ok', texto: `E-mail de teste enviado ao fluxo para ${r.enviado_para} — confira a caixa de entrada.` })
                  } catch (e) {
                    setMsg({ tipo: 'erro', texto: e.detail === 'falha_no_envio_pelo_fluxo'
                      ? 'O fluxo não confirmou o envio. Confira a URL e se o fluxo está ligado.'
                      : `Teste falhou: ${e.detail || e.message}` })
                  } finally { setOcupado(false) }
                }}>Testar envio</button>
      </div>
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
      <h3>E-mail (SMTP) — último recurso</h3>
      <p className="explica">Usado apenas se nem o Microsoft 365 nem o Google acima estiverem
        conectados.</p>
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
          <InputSenha value={senha} onChange={(e) => setSenha(e.target.value)} /></label>
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

const ESCOPOS = [
  ['avulso', 'Qualquer colaborador'],
  ['cargo', 'Colaboradores de um cargo'],
  ['posto', 'Colaboradores de um posto'],
]
const VAZIO = { titulo: '', corpo: '', escopo: 'avulso', cargo_alvo: '', posto_alvo_id: '' }

// Abre um PDF (blob autenticado) em nova aba.
async function abrirBlob(promessaBlob, setMsg) {
  try {
    const blob = await promessaBlob
    window.open(URL.createObjectURL(blob), '_blank')
  } catch (e) {
    setMsg?.({ tipo: 'erro', texto: `Não foi possível gerar o PDF (${e.detail || e.message}).` })
  }
}

function ModelosDocumento() {
  const [dados, setDados] = useState(null) // {modelos, variaveis}
  const [postos, setPostos] = useState([])
  const [edit, setEdit] = useState(null) // {id?, titulo, corpo, escopo, cargo_alvo, posto_alvo_id}
  const [msg, setMsg] = useState(null)
  const [salvando, setSalvando] = useState(false)
  const recarregar = () => api.modelos().then(setDados).catch(() => {})
  useEffect(() => { recarregar(); api.postos().then(setPostos).catch(() => {}) }, [])
  if (!dados) return null

  const salvar = async () => {
    if (!edit.titulo.trim() || !edit.corpo.trim()) {
      setMsg({ tipo: 'erro', texto: 'Preencha o título e o corpo do documento.' }); return
    }
    setSalvando(true); setMsg(null)
    const corpo = {
      titulo: edit.titulo.trim(), corpo: edit.corpo, escopo: edit.escopo,
      cargo_alvo: edit.escopo === 'cargo' ? edit.cargo_alvo.trim() : null,
      posto_alvo_id: edit.escopo === 'posto' ? (edit.posto_alvo_id || null) : null,
    }
    try {
      if (edit.id) await api.editarModelo(edit.id, corpo)
      else await api.criarModelo(corpo)
      setEdit(null); setMsg({ tipo: 'ok', texto: 'Modelo salvo.' })
      await recarregar()
    } catch (e) {
      setMsg({ tipo: 'erro', texto: `Não foi possível salvar (${e.detail || e.message}).` })
    } finally { setSalvando(false) }
  }

  return (
    <div className="rh-card">
      <h3>📝 Modelos de documento</h3>
      <p className="explica">Crie documentos do zero já no papel timbrado da empresa. Use
        variáveis entre chaves duplas — na hora de gerar para um colaborador, elas são
        preenchidas automaticamente. Depois, na tela do colaborador, é só clicar em
        <strong> Gerar</strong>.</p>
      <p className="explica" style={{ marginTop: '-.4rem' }}>Variáveis disponíveis:{' '}
        {Object.entries(dados.variaveis).map(([k, desc]) => (
          <code key={k} title={desc} style={{ marginRight: '.4rem' }}>{`{{${k}}}`}</code>
        ))}</p>

      {dados.modelos.length > 0 && (
        <table className="rh-tabela">
          <thead><tr><th>Título</th><th>Aplica-se a</th><th></th></tr></thead>
          <tbody>
            {dados.modelos.map((m) => (
              <tr key={m.id}>
                <td><strong>{m.titulo}</strong></td>
                <td>{(ESCOPOS.find((e) => e[0] === m.escopo) || [])[1] || m.escopo}
                  {m.cargo_alvo ? `: ${m.cargo_alvo}` : ''}</td>
                <td>
                  <button className="btn-secundario btn-mini"
                          onClick={() => abrirBlob(api.previaModelo(m.id), setMsg)}>Prévia</button>
                  <button className="btn-secundario btn-mini" onClick={() => setEdit({
                    id: m.id, titulo: m.titulo, corpo: m.corpo, escopo: m.escopo,
                    cargo_alvo: m.cargo_alvo || '', posto_alvo_id: m.posto_alvo_id || '',
                  })}>Editar</button>
                  <button className="btn-link" onClick={async () => {
                    if (!window.confirm(`Excluir o modelo "${m.titulo}"?`)) return
                    await api.excluirModelo(m.id); await recarregar()
                  }}>excluir</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {!edit ? (
        <button className="btn-secundario" style={{ marginTop: '.75rem' }}
                onClick={() => setEdit({ ...VAZIO })}>+ Novo modelo</button>
      ) : (
        <div style={{ marginTop: '.75rem' }}>
          <label className="campo"><span className="rotulo">Título (aceita variáveis)</span>
            <input value={edit.titulo} placeholder="Ex.: Declaração de vínculo — {{nome}}"
                   onChange={(e) => setEdit({ ...edit, titulo: e.target.value })} /></label>
          <label className="campo"><span className="rotulo">Corpo do documento</span>
            <textarea rows={7} value={edit.corpo}
                      placeholder="Declaramos que {{nome}}, CPF {{cpf}}, exerce a função de {{cargo}}…"
                      onChange={(e) => setEdit({ ...edit, corpo: e.target.value })} /></label>
          <div className="linha2">
            <label className="campo"><span className="rotulo">Aplica-se a</span>
              <select value={edit.escopo}
                      onChange={(e) => setEdit({ ...edit, escopo: e.target.value })}>
                {ESCOPOS.map(([v, t]) => <option key={v} value={v}>{t}</option>)}
              </select></label>
            {edit.escopo === 'cargo' && (
              <label className="campo"><span className="rotulo">Cargo</span>
                <input value={edit.cargo_alvo} placeholder="Ex.: Recepcionista"
                       onChange={(e) => setEdit({ ...edit, cargo_alvo: e.target.value })} /></label>
            )}
            {edit.escopo === 'posto' && (
              <label className="campo"><span className="rotulo">Posto</span>
                <select value={edit.posto_alvo_id}
                        onChange={(e) => setEdit({ ...edit, posto_alvo_id: e.target.value })}>
                  <option value="">— escolha —</option>
                  {postos.map((p) => <option key={p.id} value={p.id}>{p.nome}</option>)}
                </select></label>
            )}
          </div>
          <div className="navegacao">
            <button className="btn-secundario" onClick={() => setEdit(null)}>Cancelar</button>
            <button className="btn-principal" disabled={salvando} onClick={salvar}>
              {salvando ? 'Salvando…' : 'Salvar modelo'}</button>
          </div>
        </div>
      )}
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
                <td>{fmtDataHora(e.quando)}</td>
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
