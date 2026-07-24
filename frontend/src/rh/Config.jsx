import { useEffect, useState } from 'react'
import { fmtDataHora } from '../fmt.js'
import { rh as api } from '../api.js'
import InputSenha from '../InputSenha.jsx'
import { ErrosRecentes } from './Diagnostico.jsx'

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

      <div className="rh-zdr">
        <div className="rh-zdr-topo">
          <strong>🔒 Leitura automática de atestado de saúde</strong>
          <label className="rh-switch">
            <input type="checkbox" checked={!!cfg.zdr_ativo} disabled={ocupado}
                   onChange={async (e) => {
                     const ligar = e.target.checked
                     if (ligar && !window.confirm(
                       'Ligue isto SÓ depois de a Mistral ter aprovado a "retenção zero" '
                       + '(Zero Data Retention) no seu plano Scale e você ter assinado o '
                       + 'contrato de tratamento de dados (DPA).\n\n'
                       + 'Sem isso, o atestado de saúde ficaria guardado 30 dias no '
                       + 'servidor da Mistral. Confirmar que já está tudo em ordem?')) return
                     setMsg(null); setOcupado(true)
                     try {
                       const r = await api.salvarOcr({ zdr_ativo: ligar })
                       setCfg(r)
                       setMsg({ tipo: ligar ? 'ok' : 'ok', texto: ligar
                         ? 'Leitura de atestado de saúde LIGADA.'
                         : 'Leitura de atestado de saúde desligada — o RH digita à mão.' })
                     } catch (e2) {
                       setMsg({ tipo: 'erro', texto: `Não foi possível alterar (${e2.detail || e2.message}).` })
                     } finally { setOcupado(false) }
                   }} />
            <span className="rh-switch-trilho" />
          </label>
        </div>
        <p className="explica" style={{ margin: '.4rem 0 0' }}>
          O atestado de saúde é dado sensível (LGPD). A leitura automática dele fica
          <strong> desligada por padrão</strong>: o documento é guardado só no nosso
          servidor e o RH digita a data e a validade à mão. Para ligar a leitura
          automática, a Mistral precisa ter aprovado a <strong>retenção zero</strong>
          {' '}(não guardar o documento) no plano Scale, com o contrato de dados (DPA)
          assinado. Identidade e certificado <strong>não</strong> dependem disso —
          já são lidos normalmente.
        </p>
        <p className="explica" style={{ margin: '.3rem 0 0' }}>
          Estado: {cfg.zdr_ativo
            ? '✅ ligada — o atestado de saúde é lido pela IA'
            : '⭕ desligada — o RH preenche o atestado à mão'}
        </p>
      </div>

      <Msg msg={msg} />
    </section>
  )
}

function Msg({ msg }) {
  if (!msg) return null
  return <div className={msg.tipo === 'erro' ? 'alerta' : 'sucesso'}>{msg.texto}</div>
}

// Identidade visual da empresa: desvincula o sistema de uma empresa específica.
// Os dados aparecem nos documentos (PDFs), e-mails e no painel. Padrão inicial:
// os dados que estavam chumbados no código.
function IdentidadeVisual() {
  const [dados, setDados] = useState(null)
  const [msg, setMsg] = useState(null)
  const [ver, setVer] = useState(0) // cache-buster das imagens
  const carregar = () => api.verMarca().then(setDados)
  useEffect(() => { carregar().catch(() => {}) }, [])
  if (!dados) return null

  const campo = (chave, rotulo, textarea) => (
    <label className="campo"><span className="rotulo">{rotulo}</span>
      {textarea
        ? <textarea rows={2} value={dados[chave] || ''} onChange={(e) => setDados({ ...dados, [chave]: e.target.value })} />
        : <input value={dados[chave] || ''} onChange={(e) => setDados({ ...dados, [chave]: e.target.value })} />}
    </label>
  )
  const subir = (fn, arquivo) => {
    setMsg(null)
    fn(arquivo).then(() => { setVer((v) => v + 1); carregar()
      setMsg({ tipo: 'ok', texto: 'Imagem atualizada.' }) })
      .catch((e) => setMsg({ tipo: 'erro', texto: e.detail === 'formato_invalido'
        ? 'Formato inválido (use PNG, JPG, WEBP, SVG ou ICO).'
        : e.detail === 'arquivo_grande_demais' ? 'Imagem grande demais (máx. 2 MB).'
        : `Não foi possível enviar (${e.detail || e.message}).` }))
  }
  const escolher = (fn) => {
    const inp = document.createElement('input')
    inp.type = 'file'; inp.accept = 'image/*'
    inp.onchange = () => { if (inp.files[0]) subir(fn, inp.files[0]) }
    inp.click()
  }

  return (
    <div className="rh-card">
      <h3>🎨 Identidade visual da empresa</h3>
      <p className="explica">Nome, dados e marca que aparecem nos documentos gerados, nos e-mails
        e no painel. O sistema começa com os dados da Green House — altere para a sua empresa.</p>
      <div className="linha2">
        {campo('empresa_nome', 'Nome curto (ex.: Green House)')}
        {campo('empresa_cnpj', 'CNPJ')}
      </div>
      {campo('empresa_razao', 'Razão social')}
      {campo('empresa_endereco', 'Endereço completo', true)}
      {campo('empresa_contato', 'Contato (telefone | site)')}
      <button className="btn-secundario" onClick={async () => {
        setMsg(null)
        try {
          await api.salvarMarca({
            empresa_nome: dados.empresa_nome, empresa_razao: dados.empresa_razao,
            empresa_cnpj: dados.empresa_cnpj, empresa_endereco: dados.empresa_endereco,
            empresa_contato: dados.empresa_contato,
          })
          setMsg({ tipo: 'ok', texto: 'Dados da empresa salvos. Valem para os próximos documentos.' })
        } catch (e) { setMsg({ tipo: 'erro', texto: `Não foi possível salvar (${e.detail || e.message}).` }) }
      }}>Salvar dados</button>

      <div className="linha2" style={{ marginTop: '1rem', alignItems: 'center' }}>
        <div>
          <span className="rotulo">Logo</span><br />
          {dados.tem_logo
            ? <img src={`/api/marca/logo?v=${ver}`} alt="logo" style={{ height: 44, marginTop: 4 }} />
            : <span className="explica">Usando a logo padrão.</span>}
          <br /><button className="btn-secundario btn-mini" style={{ marginTop: 6 }}
                        onClick={() => escolher(api.uploadMarcaLogo)}>⬆ Enviar logo</button>
        </div>
        <div>
          <span className="rotulo">Favicon (ícone da aba)</span><br />
          {dados.tem_favicon
            ? <img src={`/api/marca/favicon?v=${ver}`} alt="favicon" style={{ height: 28, marginTop: 4 }} />
            : <span className="explica">Usando o favicon padrão.</span>}
          <br /><button className="btn-secundario btn-mini" style={{ marginTop: 6 }}
                        onClick={() => escolher(api.uploadMarcaFavicon)}>⬆ Enviar favicon</button>
        </div>
      </div>
      <Msg msg={msg} />
    </div>
  )
}

// Submenus: cada assunto numa aba própria — acabou a rolagem infinita
// (feedback de campo, 2026-07-19). O último submenu aberto fica lembrado.
// Modelos e Assinaturas saíram para menus próprios (2026-07-19). Aqui ficam só
// as configurações do sistema.
const SUBMENUS = [
  ['geral', '👤 Geral'],
  ['equipe', '🧑‍🤝‍🧑 Equipe'],
  ['identidade', '🎨 Identidade visual'],
  ['organizacao', '🏢 Empresas e jornadas'],
  ['integracoes', '🔌 E-mail e integrações'],
  ['sistema', '🛠️ Sistema'],
]

export default function Config({ aoVoltar }) {
  const [aba, setAba] = useState(localStorage.getItem('rh_config_aba') || 'geral')
  const trocar = (id) => { setAba(id); localStorage.setItem('rh_config_aba', id) }
  return (
    <main className="rh-painel">
      <header className="rh-topo">
        <button className="btn-link" onClick={aoVoltar}>← Voltar</button>
        <h1>⚙️ Configurações</h1>
        <span />
      </header>
      <nav className="rh-subnav">
        {SUBMENUS.map(([id, rotulo]) => (
          <button key={id} className={`rh-subnav-item ${aba === id ? 'ativo' : ''}`}
                  onClick={() => trocar(id)}>{rotulo}</button>
        ))}
      </nav>
      {aba === 'geral' && <div className="rh-grid-2"><Perfil /><Senha /></div>}
      {aba === 'equipe' && <Equipe />}
      {aba === 'identidade' && <IdentidadeVisual />}
      {aba === 'organizacao' && <>
        <div className="rh-grid-2"><Empresas /><JornadasConfig /></div>
        <BackfillEnderecos />
      </>}
      {aba === 'integracoes' && <>
        <div className="rh-grid-2"><M365 /><Gmail /></div>
        <div className="rh-grid-2"><WebhookEmail /><Smtp /></div>
        <div className="rh-grid-2"><OcrIA /><AvisosInternos /></div>
        <Teams />
      </>}
      {aba === 'sistema' && <><Lixeira /><ErrosRecentes /><Auditoria /></>}
    </main>
  )
}

// Papéis com que alguém assina um documento (Contratado(a), Contratante,
// Testemunha, Validador(a)…) — aparecem no manifesto de assinatura dos
// modelos. A ordem prepara fluxos futuros com vários signatários.
export function Papeis() {
  const [papeis, setPapeis] = useState(null)
  const [novo, setNovo] = useState(null) // {nome, descricao, ordem}
  const [editando, setEditando] = useState(null)
  const [msg, setMsg] = useState(null)
  const recarregar = () => api.papeis().then((r) => setPapeis(r.papeis))
  useEffect(() => { recarregar().catch(() => setPapeis([])) }, [])
  if (!papeis) return null

  const salvarNovo = async () => {
    setMsg(null)
    try {
      await api.criarPapel({ nome: novo.nome.trim(), descricao: novo.descricao.trim() || null,
                             ordem: parseInt(novo.ordem, 10) || 0 })
      setNovo(null); await recarregar()
    } catch (e) {
      setMsg({ tipo: 'erro', texto: e.detail === 'papel_ja_existe'
        ? 'Já existe um papel com esse nome.' : `Não foi possível criar (${e.detail || e.message}).` })
    }
  }

  return (
    <div className="rh-card">
      <h3>🎭 Papéis de assinatura</h3>
      <p className="explica">A "qualidade" com que alguém assina — vai para o bloco de
        assinatura e o manifesto do documento (ex.: <em>assina na qualidade de Testemunha</em>).
        Escolha o papel de cada modelo em Modelos de documento. A <strong>ordem</strong> define
        a sequência quando houver mais de um signatário.</p>
      <table className="rh-tabela">
        <thead><tr><th>Ordem</th><th>Papel</th><th>Descrição</th><th></th></tr></thead>
        <tbody>
          {papeis.map((p) => (
            <tr key={p.id}>
              {editando?.id === p.id ? (
                <>
                  <td><input style={{ maxWidth: 70 }} inputMode="numeric" value={editando.ordem}
                             onChange={(e) => setEditando({ ...editando, ordem: e.target.value })} /></td>
                  <td><input value={editando.nome}
                             onChange={(e) => setEditando({ ...editando, nome: e.target.value })} /></td>
                  <td><input value={editando.descricao}
                             onChange={(e) => setEditando({ ...editando, descricao: e.target.value })} /></td>
                  <td>
                    <button className="btn-principal btn-mini" onClick={async () => {
                      setMsg(null)
                      try {
                        await api.editarPapel(p.id, { nome: editando.nome.trim(),
                          descricao: editando.descricao.trim() || null,
                          ordem: parseInt(editando.ordem, 10) || 0 })
                        setEditando(null); await recarregar()
                      } catch (e) {
                        setMsg({ tipo: 'erro', texto: `Não foi possível salvar (${e.detail || e.message}).` })
                      }
                    }}>Salvar</button>
                    <button className="btn-link" onClick={() => setEditando(null)}>cancelar</button>
                  </td>
                </>
              ) : (
                <>
                  <td>{p.ordem}</td>
                  <td><strong>{p.nome}</strong></td>
                  <td><small>{p.descricao || '—'}</small></td>
                  <td>
                    <button className="btn-secundario btn-mini"
                            onClick={() => setEditando({ id: p.id, nome: p.nome,
                              descricao: p.descricao || '', ordem: String(p.ordem) })}>Editar</button>
                    <button className="btn-link" onClick={async () => {
                      if (!window.confirm(`Excluir o papel "${p.nome}"? Ele vai para a lixeira.`)) return
                      await api.excluirPapel(p.id); await recarregar()
                    }}>excluir</button>
                  </td>
                </>
              )}
            </tr>
          ))}
        </tbody>
      </table>
      {!novo ? (
        <button className="btn-secundario" style={{ marginTop: '.75rem' }}
                onClick={() => setNovo({ nome: '', descricao: '', ordem: String(papeis.length + 1) })}>
          + Novo papel</button>
      ) : (
        <div className="rh-lote" style={{ marginTop: '.75rem' }}>
          <input placeholder="Nome (ex.: Fiador)" value={novo.nome} style={{ maxWidth: 200 }}
                 onChange={(e) => setNovo({ ...novo, nome: e.target.value })} />
          <input placeholder="Descrição (opcional)" value={novo.descricao}
                 onChange={(e) => setNovo({ ...novo, descricao: e.target.value })} />
          <input placeholder="Ordem" inputMode="numeric" value={novo.ordem} style={{ maxWidth: 80 }}
                 onChange={(e) => setNovo({ ...novo, ordem: e.target.value })} />
          <button className="btn-principal btn-mini" disabled={!novo.nome.trim()}
                  onClick={salvarNovo}>Criar</button>
          <button className="btn-link" onClick={() => setNovo(null)}>cancelar</button>
        </div>
      )}
      <Msg msg={msg} />
    </div>
  )
}

// Lixeira universal: tudo que o RH exclui (postos, modelos…) fica restaurável
// aqui pelo prazo de retenção (padrão 60 dias, configurável abaixo).
function Lixeira() {
  const [dados, setDados] = useState(null)
  const [dias, setDias] = useState('')
  const [msg, setMsg] = useState(null)
  const carregar = () => api.lixeira().then((d) => { setDados(d); setDias(String(d.dias_retencao)) })
  useEffect(() => { carregar().catch(() => setDados({ itens: [], dias_retencao: 60 })) }, [])
  if (!dados) return null

  const ENTIDADES = { posto: 'Posto de serviço', modelo_documento: 'Modelo de documento',
                      teste_candidato: 'Teste do candidato', papel_assinatura: 'Papel de assinatura',
                      candidato: 'Colaborador' }
  return (
    <div className="rh-card">
      <h3>🗑️ Lixeira</h3>
      <p className="explica">Registros excluídos ficam aqui, restauráveis, por
        <strong> {dados.dias_retencao} dias</strong> — depois o expurgo é definitivo (boa prática
        de retenção de dados inativos).</p>
      {dados.itens.length === 0
        ? <p className="explica">A lixeira está vazia.</p>
        : (
          <table className="rh-tabela">
            <thead><tr><th>Tipo</th><th>Registro</th><th>Excluído por</th><th>Quando</th><th>Ações</th></tr></thead>
            <tbody>
              {dados.itens.map((i) => (
                <tr key={i.id}>
                  <td>{ENTIDADES[i.entidade] || i.entidade}</td>
                  <td><strong>{i.rotulo}</strong></td>
                  <td>{i.ator || '—'}</td>
                  <td>{new Date(i.apagado_em).toLocaleString('pt-BR')}</td>
                  <td><button className="btn-secundario btn-mini" onClick={async () => {
                    setMsg(null)
                    try { await api.lixeiraRestaurar(i.id); setMsg({ tipo: 'ok', texto: `"${i.rotulo}" restaurado.` }); carregar() }
                    catch (e) {
                      setMsg({ tipo: 'erro', texto: e.detail === 'registro_ja_existe'
                        ? 'Já existe um registro com esse identificador (talvez recriado à mão).'
                        : 'Não foi possível restaurar.' })
                    }
                  }}>♻️ Restaurar</button></td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      <div className="linha2" style={{ alignItems: 'end', marginTop: '.6rem' }}>
        <label className="campo"><span className="rotulo">Prazo de retenção (dias)</span>
          <input inputMode="numeric" value={dias} onChange={(e) => setDias(e.target.value.replace(/\D/g, ''))} /></label>
        <button className="btn-secundario" onClick={async () => {
          setMsg(null)
          try { await api.lixeiraConfig(parseInt(dias, 10)); setMsg({ tipo: 'ok', texto: 'Prazo atualizado.' }); carregar() }
          catch { setMsg({ tipo: 'erro', texto: 'Informe um prazo entre 1 e 3650 dias.' }) }
        }}>Salvar prazo</button>
      </div>
      <Msg msg={msg} />
    </div>
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

export function Assinantes() {
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

function AvisosInternos() {
  const [cfg, setCfg] = useState(null)
  const [email, setEmail] = useState('')
  const [matriz, setMatriz] = useState({})
  const [novo, setNovo] = useState({})     // e-mail sendo digitado, por evento
  const [msg, setMsg] = useState(null)
  const carregar = (c) => {
    setCfg(c); setEmail(c.email_avisos_internos || ''); setMatriz(c.matriz || {})
  }
  useEffect(() => { api.verAvisos().then(carregar).catch(() => {}) }, [])
  if (!cfg) return null

  const doEvento = (chave) => matriz[chave] || { emails: [], ativo: true }
  const mexer = (chave, mudanca) =>
    setMatriz({ ...matriz, [chave]: { ...doEvento(chave), ...mudanca } })
  const addEmail = (chave) => {
    const e = (novo[chave] || '').trim()
    if (!e || !/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(e)) {
      setMsg({ tipo: 'erro', texto: 'Informe um e-mail válido.' }); return }
    const atuais = doEvento(chave).emails
    if (atuais.some((x) => x.toLowerCase() === e.toLowerCase())) {
      setNovo({ ...novo, [chave]: '' }); return }
    mexer(chave, { emails: [...atuais, e] })
    setNovo({ ...novo, [chave]: '' }); setMsg(null)
  }

  return (
    <div className="rh-card">
      <h3>📥 Avisos internos</h3>
      <p className="explica">Quem recebe cada aviso do sistema. O <strong>e-mail padrão</strong>
        vale para todo aviso sem destinatário próprio; deixando-o em branco, os avisos vão
        para o remetente (<code>{cfg.padrao || '—'}</code>).</p>
      <div className="linha2">
        <input type="email" placeholder="avisos@suaempresa.com.br" value={email}
               onChange={(e) => setEmail(e.target.value)} />
      </div>

      <h4 style={{ marginTop: '1.2rem' }}>Por tipo de aviso</h4>
      <p className="explica">Sem e-mail na lista, o aviso vai para o padrão acima.
        Desmarcando <em>Avisar</em>, ninguém é notificado daquele evento.</p>
      {(cfg.eventos || []).map((ev) => {
        const at = doEvento(ev.chave)
        return (
          <div className="aviso-evento" key={ev.chave}>
            <div className="aviso-evento-topo">
              <label className="aviso-evento-nome">
                <input type="checkbox" checked={at.ativo !== false}
                       onChange={(e) => mexer(ev.chave, { ativo: e.target.checked })} />
                <strong>{ev.rotulo}</strong>
              </label>
              <span className="explica" style={{ margin: 0 }}>{ev.descricao}</span>
            </div>
            {at.ativo !== false && (
              <div className="aviso-evento-destinos">
                {at.emails.map((e) => (
                  <span className="chip" key={e}>{e}
                    <button type="button" title="Remover" onClick={() =>
                      mexer(ev.chave, { emails: at.emails.filter((x) => x !== e) })}>✕</button>
                  </span>
                ))}
                {at.emails.length === 0 && (
                  <span className="explica" style={{ margin: 0 }}>
                    → usando o padrão ({cfg.email_avisos_internos || cfg.padrao || '—'})</span>
                )}
                <input type="email" placeholder="adicionar e-mail…" style={{ maxWidth: 240 }}
                       value={novo[ev.chave] || ''}
                       onChange={(e) => setNovo({ ...novo, [ev.chave]: e.target.value })}
                       onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); addEmail(ev.chave) } }} />
                <button type="button" className="btn-secundario btn-mini"
                        onClick={() => addEmail(ev.chave)}>+ Adicionar</button>
              </div>
            )}
          </div>
        )
      })}

      <button className="btn-principal" style={{ marginTop: '.8rem' }} onClick={async () => {
        setMsg(null)
        try {
          const r = await api.salvarAvisos({
            email_avisos_internos: email.trim(), matriz })
          carregar(r)
          setMsg({ tipo: 'ok', texto: 'Avisos internos salvos.' })
        } catch (e) {
          setMsg({ tipo: 'erro', texto: e.detail === 'email_invalido'
            ? 'E-mail inválido.' : `Não foi possível salvar (${e.detail || e.message}).` })
        }
      }}>Salvar</button>
      <Msg msg={msg} />
    </div>
  )
}

function Teams() {
  const [cfg, setCfg] = useState(null)
  const [url, setUrl] = useState('')
  const [template, setTemplate] = useState('')
  const [msg, setMsg] = useState(null)
  const [ocupado, setOcupado] = useState(false)
  const recarregar = () => api.verTeams().then((c) => { setCfg(c); setTemplate(c.template) }).catch(() => {})
  useEffect(() => { recarregar() }, [])
  if (!cfg) return null
  return (
    <div className="rh-card">
      <h3>💬 Notificações no Microsoft Teams</h3>
      <p className="explica">Avise a equipe no Teams a cada movimentação. Crie um
        <strong> Incoming Webhook</strong> no canal (ou um fluxo do Power Automate que poste no
        Teams) e cole a URL abaixo. A mensagem sai do <strong>template</strong> — use variáveis
        entre chaves duplas; na tela do colaborador há o botão <strong>Enviar ao Teams</strong>.</p>
      {cfg.configurado && (
        <div className="sucesso" style={{ marginBottom: '.6rem' }}>✅ Webhook configurado
          (<code>{cfg.url_mascarada}</code>).</div>
      )}
      <label className="campo"><span className="rotulo">URL do webhook (https://…)</span>
        <InputSenha placeholder={cfg.configurado ? 'URL definida — preencha para trocar' : 'Cole a URL do webhook do Teams'}
                    value={url} onChange={(e) => setUrl(e.target.value)} /></label>
      <label className="campo"><span className="rotulo">Template da mensagem (Markdown + variáveis)</span>
        <textarea rows={5} value={template} onChange={(e) => setTemplate(e.target.value)} /></label>
      <p className="explica" style={{ marginTop: '-.4rem' }}>Variáveis:{' '}
        {['nome', 'cargo', 'posto', 'contrato', 'salario', 'status', 'cpf', 'data'].map((v) => (
          <code key={v} style={{ marginRight: '.4rem' }}>{`{{${v}}}`}</code>
        ))}</p>
      <div className="navegacao">
        <button className="btn-secundario" disabled={ocupado} onClick={async () => {
          setMsg(null); setOcupado(true)
          try {
            const r = await api.salvarTeams({ webhook_url: url.trim() || null, template })
            setCfg(r); setUrl('')
            setMsg({ tipo: 'ok', texto: 'Configuração do Teams salva.' })
          } catch (e) {
            setMsg({ tipo: 'erro', texto: e.detail === 'url_precisa_ser_https'
              ? 'A URL precisa começar com https://.'
              : `Não foi possível salvar (${e.detail || e.message}).` })
          } finally { setOcupado(false) }
        }}>Salvar</button>
        <button className="btn-principal btn-mini" disabled={ocupado || !cfg.configurado}
                onClick={async () => {
                  setMsg(null); setOcupado(true)
                  try { await api.testarTeams(); setMsg({ tipo: 'ok', texto: 'Mensagem de teste enviada ao Teams.' }) }
                  catch (e) {
                    setMsg({ tipo: 'erro', texto: e.detail === 'falha_no_envio_ao_teams'
                      ? 'O Teams não confirmou o recebimento. Confira a URL do webhook.'
                      : `Teste falhou: ${e.detail || e.message}` })
                  } finally { setOcupado(false) }
                }}>Enviar teste</button>
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
      {/* TOGGLE (abre/fecha) — e a tabela vai dentro de .dash-scroll para ROLAR
         dentro de si, não estourar a margem da tela: a coluna "Detalhe" é um
         JSON longo (feedback do Bruno: "estoura as margens laterais"). */}
      {!aberto ? (
        <button className="btn-secundario" onClick={async () => {
          if (!eventos) setEventos(await api.auditoria())
          setAberto(true)
        }}>Ver últimos eventos</button>
      ) : !eventos ? <p>Carregando…</p> : (
        <>
          <button className="btn-link" style={{ marginBottom: '.5rem' }}
                  onClick={() => setAberto(false)}>Ocultar eventos</button>
          <div className="dash-scroll">
            <table className="rh-tabela">
              <thead><tr><th>Quando</th><th>Ação</th><th>Ator</th><th>Detalhe</th></tr></thead>
              <tbody>
                {eventos.map((e, i) => (
                  <tr key={i}>
                    <td>{fmtDataHora(e.quando)}</td>
                    <td>{e.acao}</td>
                    <td>{e.ator}{e.ator_detalhe ? ` (${e.ator_detalhe})` : ''}</td>
                    <td className="dash-quebra"><small>{e.detalhe ? JSON.stringify(e.detalhe) : ''}</small></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Empresas e jornadas (integração Tirvu) + backfill assistido de endereços
// ---------------------------------------------------------------------------

function Empresas() {
  const [empresas, setEmpresas] = useState(null)
  const [nova, setNova] = useState({ razao_social: '', cnpj: '' })
  const [msg, setMsg] = useState(null)
  const carregar = () => api.empresas().then(setEmpresas)
  useEffect(() => { carregar().catch(() => setEmpresas([])) }, [])
  if (!empresas) return null
  return (
    <div className="rh-card">
      <h3>🏢 Empresas</h3>
      <p className="explica">Empregadoras que assinam a carteira — saem na coluna
        "Empresa" da planilha de importação de admissões do Tirvu.</p>
      {empresas.length > 0 && (
        <table className="rh-tabela">
          <thead><tr><th>Razão social</th><th>CNPJ</th></tr></thead>
          <tbody>{empresas.map((e) => (
            <tr key={e.id}><td><strong>{e.razao_social}</strong></td><td>{e.cnpj || '—'}</td></tr>
          ))}</tbody>
        </table>
      )}
      <div className="linha2" style={{ alignItems: 'end', marginTop: '.6rem' }}>
        <label className="campo"><span className="rotulo">Razão social</span>
          <input value={nova.razao_social}
                 onChange={(e) => setNova({ ...nova, razao_social: e.target.value })} /></label>
        <label className="campo"><span className="rotulo">CNPJ (opcional)</span>
          <input value={nova.cnpj}
                 onChange={(e) => setNova({ ...nova, cnpj: e.target.value })} /></label>
      </div>
      <button className="btn-secundario" onClick={async () => {
        setMsg(null)
        if (!nova.razao_social.trim()) { setMsg({ tipo: 'erro', texto: 'Informe a razão social.' }); return }
        try {
          await api.criarEmpresa({ razao_social: nova.razao_social.trim(),
                                   cnpj: nova.cnpj.trim() || null })
          setNova({ razao_social: '', cnpj: '' }); setMsg({ tipo: 'ok', texto: 'Empresa cadastrada.' })
          carregar()
        } catch (e) { setMsg({ tipo: 'erro', texto: `Não foi possível criar (${e.detail || e.message}).` }) }
      }}>+ Cadastrar empresa</button>
      <Msg msg={msg} />
    </div>
  )
}

function JornadasConfig() {
  const [jornadas, setJornadas] = useState(null)
  const [busca, setBusca] = useState('')
  const [msg, setMsg] = useState(null)
  const [relato, setRelato] = useState(null)
  const carregar = () => api.jornadas().then(setJornadas)
  useEffect(() => { carregar().catch(() => setJornadas([])) }, [])
  if (!jornadas) return null
  const termo = busca.trim().toLowerCase()
  const visiveis = termo ? jornadas.filter((j) => j.descricao.toLowerCase().includes(termo)) : jornadas
  return (
    <div className="rh-card">
      <h3>🕐 Jornadas de trabalho</h3>
      <p className="explica">Importadas da planilha "Escala de Trabalho - Detalhado" do
        Tirvu (cada aba é um posto) ou criadas na ficha do colaborador. O arquivo enviado
        é processado e descartado — nada fica guardado.</p>
      <label className="btn-secundario" style={{ cursor: 'pointer' }}>
        📥 Importar planilha de escalas…
        <input type="file" accept=".xlsx" style={{ display: 'none' }}
               onChange={async (e) => {
                 const f = e.target.files[0]; e.target.value = ''
                 if (!f) return
                 setMsg(null); setRelato(null)
                 try {
                   const r = await api.importarJornadas(f)
                   setRelato(r); carregar()
                 } catch (err) {
                   setMsg({ tipo: 'erro', texto: err.detail === 'arquivo_invalido'
                     ? 'O arquivo não parece um .xlsx válido.'
                     : `Não foi possível importar (${err.detail || err.message}).` })
                 }
               }} />
      </label>
      {relato && (
        <div className="sucesso">
          {relato.jornadas_criadas} jornada(s) nova(s) de {relato.abas_processadas} abas —
          {' '}{relato.abas_casadas_com_posto} abas casaram com postos.
          {relato.abas_sem_posto.length > 0 && (
            <> Sem posto correspondente: {relato.abas_sem_posto.join(', ')}.
              As jornadas dessas abas entraram sem posto (valem para todos).</>
          )}
        </div>
      )}
      <p className="explica"><strong>{jornadas.length}</strong> jornada(s) cadastrada(s).</p>
      {jornadas.length > 0 && (
        <input placeholder="🔎 Filtrar jornadas…" value={busca}
               onChange={(e) => setBusca(e.target.value)} />
      )}
      {termo && (
        <ul>
          {visiveis.slice(0, 30).map((j) => <li key={j.id}>{j.descricao}</li>)}
          {visiveis.length > 30 && <li>…e mais {visiveis.length - 30}.</li>}
          {visiveis.length === 0 && <li>Nenhuma jornada com esse texto.</li>}
        </ul>
      )}
      <Msg msg={msg} />
    </div>
  )
}

// Backfill assistido: o parser propõe a separação do endereço antigo (string
// única) em logradouro/número/complemento; NADA é gravado sem o RH confirmar.
// Endereço de Brasília derruba heurística — o incerto fica para decidir à mão.
function BackfillEnderecos() {
  const [dados, setDados] = useState(null)
  const [edits, setEdits] = useState({})
  const [msg, setMsg] = useState(null)
  const [aberto, setAberto] = useState(false)
  const carregar = () => api.backfillEnderecos().then(setDados)
  useEffect(() => { carregar().catch(() => setDados({ total: 0, com_proposta: 0, itens: [] })) }, [])
  if (!dados || dados.total === 0) return null
  const valor = (i, campo) => {
    const e = edits[i.candidato_id]
    if (e && campo in e) return e[campo]
    return (i.proposta && i.proposta[campo]) || ''
  }
  const editar = (i, campo, v) =>
    setEdits({ ...edits, [i.candidato_id]: { ...edits[i.candidato_id], [campo]: v } })
  const aplicar = async (itens) => {
    setMsg(null)
    const payload = itens
      .map((i) => ({ candidato_id: i.candidato_id,
                     logradouro: valor(i, 'logradouro').trim(),
                     numero: valor(i, 'numero').trim(),
                     complemento: valor(i, 'complemento').trim() || null }))
      .filter((p) => p.logradouro && p.numero)
    if (!payload.length) { setMsg({ tipo: 'erro', texto: 'Nada para aplicar — confira logradouro e número.' }); return }
    try {
      const r = await api.aplicarBackfillEnderecos(payload)
      setMsg({ tipo: 'ok', texto: `${r.aplicados} endereço(s) separado(s).` })
      setEdits({}); carregar()
    } catch (e) { setMsg({ tipo: 'erro', texto: `Não foi possível aplicar (${e.detail || e.message}).` }) }
  }
  const seguros = dados.itens.filter((i) => i.proposta && !edits[i.candidato_id])
  return (
    <div className="rh-card">
      <h3>🏠 Endereços antigos — separar rua e número</h3>
      <p className="explica">A planilha do Tirvu pede logradouro, número e complemento
        separados; <strong>{dados.total}</strong> pessoa(s) ainda têm o endereço num campo só.
        O sistema propõe a separação e <strong>você confirma</strong> — nada muda sozinho.
        ({dados.com_proposta} com proposta automática; o resto precisa de ajuste manual.)</p>
      {!aberto ? (
        <button className="btn-secundario" onClick={() => setAberto(true)}>Revisar endereços…</button>
      ) : (<>
        {seguros.length > 0 && (
          <button className="btn-principal btn-mini" style={{ marginBottom: '.5rem' }}
                  onClick={() => aplicar(seguros)}>
            ✓ Aplicar as {seguros.length} propostas não editadas</button>
        )}
        <table className="rh-tabela">
          <thead><tr><th>Pessoa</th><th>Original</th><th>Logradouro</th><th>Nº</th><th>Compl.</th><th></th></tr></thead>
          <tbody>
            {dados.itens.map((i) => (
              <tr key={i.candidato_id}>
                <td><strong>{i.nome}</strong></td>
                <td style={{ maxWidth: 220 }}>{i.original}</td>
                <td><input value={valor(i, 'logradouro')} style={{ minWidth: 150 }}
                           onChange={(e) => editar(i, 'logradouro', e.target.value)} /></td>
                <td><input value={valor(i, 'numero')} style={{ width: 70 }}
                           onChange={(e) => editar(i, 'numero', e.target.value)} /></td>
                <td><input value={valor(i, 'complemento')} style={{ width: 100 }}
                           onChange={(e) => editar(i, 'complemento', e.target.value)} /></td>
                <td><button className="btn-secundario btn-mini"
                            onClick={() => aplicar([i])}>✓ Aplicar</button></td>
              </tr>
            ))}
          </tbody>
        </table>
      </>)}
      <Msg msg={msg} />
    </div>
  )
}
