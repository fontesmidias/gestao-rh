import { useEffect, useState } from 'react'
import { portal as api } from './api.js'
import { VerificarIdentidade } from './CrecheLink.jsx'
import logo from './assets/logo.png'

// Portal do colaborador (/meu) — UMA porta para tudo que é da pessoa.
//
// Quem usa isto é o bombeiro civil no plantão, no celular, com internet ruim,
// que recebeu um e-mail dizendo que o certificado vence. Ele nunca entrou no
// sistema antes. Por isso: um passo por tela, texto curto, e a HOME é o que
// está pendente — não um menu (menu é o que o sistema quer mostrar; a pessoa
// entra querendo resolver algo).
//
// Gate idêntico ao do creche: CPF → código por e-mail; sem e-mail, KBA.
export default function Portal() {
  const [etapa, setEtapa] = useState('cpf')   // cpf | codigo | kba | dentro
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
      setToken(r.token); setEtapa('dentro')
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
        <h1>Meu Portal</h1>
        {etapa !== 'dentro' && (
          <p className="creche-sub">Seus cursos, certificados e pendências em um lugar só.</p>
        )}
      </header>

      {etapa === 'cpf' && (
        <form className="rh-card creche-card" onSubmit={iniciar}>
          <h2>Vamos começar</h2>
          <p className="explica">Informe seu CPF. Enviaremos um código de confirmação
            para o seu e-mail.</p>
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
          <p className="explica">Enviamos um código de 6 dígitos ao seu e-mail.
            <strong> Verifique também a caixa de spam</strong> — às vezes a mensagem vai para lá.</p>
          <label className="campo"><span className="rotulo">Código de confirmação</span>
            <input inputMode="numeric" maxLength={6} placeholder="000000" value={codigo} autoFocus
                   style={{ letterSpacing: '.4em', textAlign: 'center', fontSize: '1.4rem' }}
                   onChange={(e) => setCodigo(e.target.value.replace(/\D/g, ''))} /></label>
          {erro && <div className="alerta">{erro}</div>}
          <button className="btn-principal" disabled={carregando || codigo.length < 6}>
            {carregando ? 'Confirmando…' : 'Entrar'}</button>
          <button type="button" className="btn-link"
                  onClick={() => { setEtapa('kba'); setErro(null) }}>
            Não recebi o código / não tenho e-mail cadastrado</button>
          <button type="button" className="btn-link"
                  onClick={() => { setEtapa('cpf'); setCodigo('') }}>← voltar</button>
        </form>
      )}

      {etapa === 'kba' && (
        <VerificarIdentidade cpf={cpf}
          kbaIniciar={api.kbaIniciar} kbaResponder={api.kbaResponder}
          kbaDefinirEmail={api.kbaDefinirEmail}
          textoEmail="usaremos esse e-mail para avisar você sobre prazos e documentos"
          aoConcluir={() => { setEtapa('codigo'); setErro(null) }}
          aoVoltar={() => { setEtapa('codigo'); setErro(null) }} />
      )}

      {etapa === 'dentro' && token && (
        <MinhaArea token={token} aoExpirar={() => { setToken(null); setEtapa('cpf') }} />
      )}

      <p className="portal-rodape">Dados tratados segundo a LGPD, exclusivamente para a
        gestão da sua relação de trabalho com a Green House.</p>
    </main>
  )
}

// --------------------------------------------------------------------------
// Dentro do portal
// --------------------------------------------------------------------------

function MinhaArea({ token, aoExpirar }) {
  const [dados, setDados] = useState(null)
  const [erro, setErro] = useState(null)
  const [novo, setNovo] = useState(null)      // registro sendo criado/editado

  const recarregar = () => api.sessao(token).then(setDados).catch(() => {
    setErro('Sua sessão expirou. Entre novamente com seu CPF.')
    if (aoExpirar) aoExpirar()
  })
  useEffect(() => { recarregar() }, [])

  if (erro) return <div className="rh-card creche-card"><div className="alerta">{erro}</div></div>
  if (!dados) return <div className="rh-card creche-card"><p>Carregando…</p></div>

  if (novo) return (
    <EnvioRegistro token={token} tipos={dados.tipos} registro={novo}
                   aoFechar={() => { setNovo(null); recarregar() }} />
  )

  return (
    <>
      <div className="rh-card creche-card">
        <h2 style={{ marginBottom: '.2rem' }}>Olá, {dados.primeiro_nome}!</h2>
        <p className="explica" style={{ marginBottom: 0 }}>
          {[dados.cargo, dados.posto].filter(Boolean).join(' · ') || 'Colaborador(a)'}
        </p>
      </div>

      {dados.pendencias.length > 0 && (
        <div className="rh-card creche-card">
          <h3 style={{ marginTop: 0 }}>O que precisa da sua atenção</h3>
          {dados.pendencias.map((p, i) => (
            <div className={`portal-pendencia ${p.urgente ? 'urgente' : ''}`} key={i}>
              <span className="portal-pendencia-icone">{p.urgente ? '🔴' : '⚠️'}</span>
              <div>
                <strong>{p.titulo}</strong>
                <div className="explica" style={{ margin: 0 }}>{p.detalhe}</div>
              </div>
            </div>
          ))}
        </div>
      )}

      {dados.fatos && dados.fatos.length > 0 && (
        <div className="rh-card creche-card">
          <h3 style={{ marginTop: 0 }}>Registros sobre o meu trabalho</h3>
          <p className="explica">O que suas lideranças registraram no período. Serve de
            base para a sua avaliação — se algo não confere, fale com o RH.</p>
          {dados.fatos.map((f) => (
            <div className="portal-registro" key={f.id}>
              <div className="portal-registro-topo">
                <strong>{fmtData(f.ocorrido_em)}</strong>
                <span className="chip" style={{ '--chip-cor':
                  f.tipo === 'positivo' ? '#0a8f46'
                    : f.tipo === 'negativo' ? '#e5484d' : '#889' }}>
                  {f.tipo === 'positivo' ? 'Positivo'
                    : f.tipo === 'negativo' ? 'A melhorar' : 'Registro'}</span>
              </div>
              <div style={{ marginTop: '.3rem' }}>{f.descricao}</div>
              {f.impacto && (
                <div className="explica" style={{ margin: '.2rem 0 0' }}>
                  Impacto: {f.impacto}</div>
              )}
            </div>
          ))}
        </div>
      )}

      <div className="rh-card creche-card">
        <h3 style={{ marginTop: 0 }}>Meu desenvolvimento</h3>
        <p className="explica">Seus cursos, treinamentos e certificações. Envie o que você
          fez — o RH confere e passa a valer no seu histórico.</p>

        {dados.registros.length === 0 && (
          <p className="explica">Você ainda não enviou nenhum curso ou certificado.</p>
        )}

        {dados.registros.map((r) => (
          <div className="portal-registro" key={r.id}>
            <div className="portal-registro-topo">
              <strong>{r.titulo || r.tipo}</strong>
              <SituacaoChip registro={r} />
            </div>
            <div className="explica" style={{ margin: '.2rem 0 0' }}>
              {[r.tipo, r.instituicao, r.carga_horaria].filter(Boolean).join(' · ')}
            </div>
            {r.validade_ate && (
              <div className="explica" style={{ margin: 0 }}>
                Válido até {fmtData(r.validade_ate)}
              </div>
            )}
            {r.status === 'devolvido' && r.motivo_recusa && (
              <div className="alerta" style={{ marginTop: '.5rem' }}>
                <strong>O RH pediu uma correção:</strong> {r.motivo_recusa}
                <button className="btn-secundario btn-mini" style={{ marginTop: '.5rem' }}
                        onClick={() => setNovo(r)}>Corrigir e reenviar</button>
              </div>
            )}
            {r.status === 'recusado' && r.motivo_recusa && (
              <div className="alerta" style={{ marginTop: '.5rem' }}>
                <strong>Não aceito:</strong> {r.motivo_recusa}
              </div>
            )}
          </div>
        ))}

        <button className="btn-principal" style={{ marginTop: '.8rem' }}
                onClick={() => setNovo({ novo: true })}>
          ＋ Enviar curso ou certificado</button>
      </div>
    </>
  )
}

// --------------------------------------------------------------------------
// Envio de um curso/certificado
// --------------------------------------------------------------------------

const ROTULO_PAPEL = {
  identidade: 'Documento com foto (RG ou CNH)',
  certificado_formacao: 'Certificado de formação',
  certificado_reciclagem: 'Certificado de reciclagem',
  aso: 'Atestado de saúde (ASO)',
  outro: 'Documento',
}

function EnvioRegistro({ token, tipos, registro, aoFechar }) {
  const editando = !registro.novo
  const [tipoId, setTipoId] = useState(registro.tipo_id || (tipos[0] && tipos[0].id) || '')
  const [id, setId] = useState(editando ? registro.id : null)
  const [campos, setCampos] = useState({
    titulo: registro.titulo || '', instituicao: registro.instituicao || '',
    carga_horaria: registro.carga_horaria || '',
    concluido_em: registro.concluido_em ? fmtData(registro.concluido_em) : '',
  })
  const [docs, setDocs] = useState(registro.documentos || [])
  const [lidos, setLidos] = useState({})     // papel -> aviso da leitura
  const [erro, setErro] = useState(null)
  const [salvando, setSalvando] = useState(false)

  const tipo = tipos.find((t) => t.id === tipoId)
  const exigidos = (tipo && tipo.documentos_exigidos && tipo.documentos_exigidos.length)
    ? tipo.documentos_exigidos : ['outro']

  // O registro precisa existir antes de receber arquivo (o upload é por id).
  const garantirRegistro = async () => {
    if (id) return id
    const r = await api.criarRegistro(token, { tipo_id: tipoId, ...comData(campos) })
    setId(r.id)
    return r.id
  }

  const subir = async (papel, arquivo) => {
    if (!arquivo) return
    setErro(null); setSalvando(true)
    try {
      const rid = await garantirRegistro()
      const r = await api.subirDocumento(token, rid, papel, arquivo)
      setDocs(r.registro.documentos)
      // A IA propõe; a pessoa confere. Só preenche o que ainda está VAZIO —
      // nunca sobrescreve o que ela digitou.
      const s = r.sugestoes || {}
      setCampos((atual) => ({
        titulo: atual.titulo,
        instituicao: atual.instituicao || s.instituicao || '',
        carga_horaria: atual.carga_horaria || s.carga_horaria || '',
        concluido_em: atual.concluido_em || (s.concluido_em ? fmtData(s.concluido_em) : ''),
      }))
      setLidos((a) => ({ ...a, [papel]: avisoLeitura(r.leitura, s) }))
    } catch (e) {
      setErro(e.detail === 'formato_nao_aceito'
        ? 'Formato não aceito. Envie PDF, foto (JPG/PNG) ou Word.'
        : e.detail === 'arquivo_grande' ? 'Arquivo muito grande (máximo 10 MB).'
        : e.detail === 'arquivo_vazio' ? 'O arquivo parece vazio. Tente de novo.'
        : `Não foi possível enviar (${e.detail || e.message}).`)
    } finally { setSalvando(false) }
  }

  const salvar = async () => {
    setErro(null); setSalvando(true)
    try {
      const rid = await garantirRegistro()
      await api.editarRegistro(token, rid, { tipo_id: tipoId, ...comData(campos) })
      aoFechar()
    } catch (e) {
      setErro(`Não foi possível salvar (${e.detail || e.message}).`)
    } finally { setSalvando(false) }
  }

  const enviadoDe = (papel) => docs.some((d) => d.papel === papel)
  const faltando = exigidos.filter((p) => !enviadoDe(p))

  return (
    <div className="rh-card creche-card">
      <h2 style={{ marginTop: 0 }}>
        {editando ? 'Corrigir envio' : 'Enviar curso ou certificado'}</h2>

      <label className="campo"><span className="rotulo">O que você fez?</span>
        <select value={tipoId} disabled={!!id}
                onChange={(e) => setTipoId(e.target.value)}>
          {tipos.map((t) => <option key={t.id} value={t.id}>{t.nome}</option>)}
        </select></label>
      {tipo && tipo.descricao && <p className="explica">{tipo.descricao}</p>}

      <div className="portal-docs">
        <span className="rotulo">Documentos</span>
        {exigidos.map((papel) => (
          <div className={`portal-doc ${enviadoDe(papel) ? 'ok' : ''}`} key={papel}>
            <div>
              <strong>{ROTULO_PAPEL[papel] || papel}</strong>
              {lidos[papel] && <div className="explica" style={{ margin: 0 }}>{lidos[papel]}</div>}
            </div>
            <label className="btn-secundario btn-mini" style={{ cursor: 'pointer' }}>
              {enviadoDe(papel) ? '✔ trocar' : 'Escolher'}
              <input type="file" hidden accept=".pdf,.jpg,.jpeg,.png,.heic,.webp,.doc,.docx"
                     onChange={(e) => subir(papel, e.target.files[0])} />
            </label>
          </div>
        ))}
      </div>

      <p className="explica">📷 Pode fotografar com o celular — só confira se está legível.</p>

      <label className="campo"><span className="rotulo">Nome do curso</span>
        <input value={campos.titulo} placeholder={tipo ? tipo.nome : ''}
               onChange={(e) => setCampos({ ...campos, titulo: e.target.value })} /></label>
      <label className="campo"><span className="rotulo">Onde você fez</span>
        <input value={campos.instituicao} placeholder="Ex.: Multicursos"
               onChange={(e) => setCampos({ ...campos, instituicao: e.target.value })} /></label>
      <div className="linha2">
        <label className="campo"><span className="rotulo">Carga horária</span>
          <input value={campos.carga_horaria} placeholder="Ex.: 20h"
                 onChange={(e) => setCampos({ ...campos, carga_horaria: e.target.value })} /></label>
        <label className="campo"><span className="rotulo">Data de conclusão</span>
          <input inputMode="numeric" placeholder="dd/mm/aaaa" value={campos.concluido_em}
                 onChange={(e) => setCampos({ ...campos, concluido_em: mascaraData(e.target.value) })} /></label>
      </div>

      {faltando.length > 0 && (
        <p className="aviso-pendente">⚠️ Ainda falta enviar: {
          faltando.map((p) => (ROTULO_PAPEL[p] || p)).join(', ')}</p>
      )}
      {erro && <div className="alerta">{erro}</div>}

      <button className="btn-principal" disabled={salvando || !tipoId}
              onClick={salvar}>{salvando ? 'Salvando…' : 'Enviar para o RH'}</button>
      <button className="btn-link" onClick={aoFechar}>← voltar</button>
    </div>
  )
}

function avisoLeitura(motivo, sugestoes) {
  if (motivo === 'saude_sem_zdr') return 'Documento recebido. Preencha os campos abaixo.'
  if (motivo === 'ok' && Object.keys(sugestoes || {}).length) {
    return '✨ Li o documento e preenchi o que consegui — confira abaixo.'
  }
  if (motivo === 'sem_texto') return 'Recebido, mas não consegui ler. Preencha na mão, por favor.'
  return 'Documento recebido.'
}

function comData(campos) {
  return { ...campos, concluido_em: campos.concluido_em || null }
}

function mascaraData(v) {
  const d = v.replace(/\D/g, '').slice(0, 8)
  if (d.length <= 2) return d
  if (d.length <= 4) return `${d.slice(0, 2)}/${d.slice(2)}`
  return `${d.slice(0, 2)}/${d.slice(2, 4)}/${d.slice(4)}`
}

function SituacaoChip({ registro: r }) {
  const mapa = {
    pendente: { texto: 'Em análise', cor: '#f5a623' },
    validado: { texto: 'Validado', cor: '#0a8f46' },
    recusado: { texto: 'Não aceito', cor: '#e5484d' },
    devolvido: { texto: 'Precisa corrigir', cor: '#e5484d' },
  }
  // validado mas vencendo: o prazo importa mais que o status
  if (r.status === 'validado' && r.situacao_validade === 'vencido') {
    return <span className="chip" style={{ '--chip-cor': '#e5484d' }}>Vencido</span>
  }
  if (r.status === 'validado' && r.situacao_validade === 'a_vencer') {
    return <span className="chip" style={{ '--chip-cor': '#f5a623' }}>A vencer</span>
  }
  const m = mapa[r.status] || mapa.pendente
  return <span className="chip" style={{ '--chip-cor': m.cor }}>{m.texto}</span>
}

function fmtData(iso) {
  if (!iso) return ''
  const [a, m, d] = iso.split('-')
  return `${d}/${m}/${a}`
}
