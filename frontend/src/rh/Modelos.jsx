import { Fragment, useEffect, useMemo, useRef, useState } from 'react'
import { rh as api } from '../api.js'

// 📝 Modelos de documento — página exclusiva (Configurações → Modelos).
// CRUD completo + prévia + duplicar + opções de envio (e-mail / assinatura
// eletrônica com papel do signatário) + envio pontual para qualquer pessoa
// (em admissão ou colaborador antigo), com busca.

const ESCOPOS = [
  ['avulso', 'Qualquer colaborador'],
  ['cargo', 'Colaboradores de um cargo'],
  ['posto', 'Colaboradores de um posto'],
  ['colaborador', 'Uma pessoa específica'],
]
const VAZIO = { titulo: '', corpo: '', escopo: 'avulso', cargo_alvo: '', posto_alvo_id: '',
                candidato_alvo_id: '', enviar_por_email: false, exige_assinatura: false,
                papel_assinatura: '' }

// Esqueletos de partida (feedback 2026-07-19): a pessoa escolhe um padrão e o
// editor já vem preenchido com a estrutura e as {{variaveis}} nos lugares —
// muito mais rápido que começar do zero. São TEXTO de partida, não modelos
// salvos (não criam registro). Baseados no estilo dos ofícios já existentes.
const PREDEFINICOES = [
  { id: 'oficio', nome: '📄 Ofício', titulo: 'Ofício — {{nome}}',
    corpo: 'Brasília/DF, {{data}}.\n\n'
      + 'Ao(À) Senhor(a)\n{{nome}}\n\n'
      + 'Assunto: [descreva o assunto]\n\n'
      + 'Prezado(a) Senhor(a),\n\n'
      + 'Vimos por meio deste ofício comunicar que [texto do ofício]. '
      + 'O(A) colaborador(a) {{nome}}, inscrito(a) no CPF {{cpf}}, ocupante do cargo de '
      + '{{cargo}} no posto {{posto}}, [complemente conforme a necessidade].\n\n'
      + 'Sendo o que se apresenta para o momento, colocamo-nos à disposição para '
      + 'eventuais esclarecimentos.\n\n'
      + 'Atenciosamente,\n\n{{empresa}}' },
  { id: 'comunicado', nome: '📢 Comunicado', titulo: 'Comunicado — {{nome}}',
    corpo: 'COMUNICADO\n\nBrasília/DF, {{data}}.\n\n'
      + 'Prezado(a) {{nome}},\n\n'
      + 'Comunicamos que [conteúdo do comunicado]. '
      + 'Solicitamos a devida ciência e, se aplicável, as providências cabíveis.\n\n'
      + 'Atenciosamente,\n{{empresa}}' },
  { id: 'contrato', nome: '📝 Contrato/Termo', titulo: 'Termo — {{nome}}',
    corpo: 'TERMO\n\n'
      + 'Pelo presente instrumento, {{empresa}}, e de outro lado {{nome}}, inscrito(a) '
      + 'no CPF {{cpf}}, ocupante do cargo de {{cargo}} no posto {{posto}}, '
      + 'ajustam entre si o seguinte:\n\n'
      + 'CLÁUSULA 1ª — [objeto do termo].\n\n'
      + 'CLÁUSULA 2ª — [obrigações].\n\n'
      + 'E, por estarem assim justos e acordados, firmam o presente em via eletrônica.\n\n'
      + 'Brasília/DF, {{data}}.' },
  { id: 'declaracao', nome: '🖋️ Declaração', titulo: 'Declaração — {{nome}}',
    corpo: 'DECLARAÇÃO\n\n'
      + 'Declaramos, para os devidos fins, que {{nome}}, inscrito(a) no CPF {{cpf}}, '
      + 'exerce o cargo de {{cargo}} no posto {{posto}}, [complemente: desde quando, '
      + 'com que finalidade].\n\n'
      + 'Por ser expressão da verdade, firmamos a presente declaração.\n\n'
      + 'Brasília/DF, {{data}}.\n\n{{empresa}}' },
]

function Msg({ msg }) {
  if (!msg) return null
  return <div className={msg.tipo === 'erro' ? 'alerta' : 'sucesso'}>{msg.texto}</div>
}

async function abrirBlob(promessaBlob, setMsg) {
  try {
    const blob = await promessaBlob
    window.open(URL.createObjectURL(blob), '_blank')
  } catch (e) {
    setMsg?.({ tipo: 'erro', texto: `Não foi possível gerar o PDF (${e.detail || e.message}).` })
  }
}

// Todas as pessoas do sistema (em admissão + colaboradores), para o envio
// pontual e para o escopo "uma pessoa específica".
function usePessoas() {
  const [pessoas, setPessoas] = useState([])
  useEffect(() => {
    Promise.allSettled([api.candidatos(), api.colaboradores()]).then(([c1, c2]) => {
      const mapa = new Map()
      for (const c of (c1.status === 'fulfilled' ? c1.value : []))
        mapa.set(c.id, { id: c.id, nome: c.nome_completo, extra: 'em admissão' })
      for (const c of (c2.status === 'fulfilled' ? (c2.value.colaboradores || c2.value) : []))
        mapa.set(c.id, { id: c.id, nome: c.nome_completo,
                         extra: c.situacao === 'desligado' ? 'desligado' : (c.cargo_funcao || 'colaborador') })
      setPessoas([...mapa.values()].sort((a, b) => a.nome.localeCompare(b.nome)))
    })
  }, [])
  return pessoas
}

export default function Modelos() {
  const [dados, setDados] = useState(null) // {modelos, variaveis}
  const [postos, setPostos] = useState([])
  const [papeis, setPapeis] = useState([])
  const [busca, setBusca] = useState('')
  const [edit, setEdit] = useState(null)
  const [enviando, setEnviando] = useState(null) // modelo_id com o painel de envio aberto
  const [assinaturas, setAssinaturas] = useState(null) // modelo_id com o painel de assinaturas
  const [msg, setMsg] = useState(null)
  const [salvando, setSalvando] = useState(false)
  const pessoas = usePessoas()

  const recarregar = () => api.modelos().then(setDados).catch(() => {})
  useEffect(() => {
    recarregar()
    api.postos().then((r) => setPostos(r.postos)).catch(() => {})
    api.papeis().then((r) => setPapeis(r.papeis)).catch(() => {})
  }, [])
  if (!dados) return <p>Carregando…</p>

  const filtrados = dados.modelos.filter((m) =>
    !busca.trim() || m.titulo.toLowerCase().includes(busca.trim().toLowerCase()))

  const salvar = async () => {
    if (!edit.titulo.trim() || !edit.corpo.trim()) {
      setMsg({ tipo: 'erro', texto: 'Preencha o título e o corpo do documento.' }); return
    }
    setSalvando(true); setMsg(null)
    const corpo = {
      titulo: edit.titulo.trim(), corpo: edit.corpo, escopo: edit.escopo,
      cargo_alvo: edit.escopo === 'cargo' ? edit.cargo_alvo.trim() : null,
      posto_alvo_id: edit.escopo === 'posto' ? (edit.posto_alvo_id || null) : null,
      candidato_alvo_id: edit.escopo === 'colaborador' ? (edit.candidato_alvo_id || null) : null,
      enviar_por_email: !!edit.enviar_por_email,
      exige_assinatura: !!edit.exige_assinatura,
      papel_assinatura: edit.exige_assinatura ? (edit.papel_assinatura || null) : null,
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

  const duplicar = async (m) => {
    setMsg(null)
    try {
      await api.criarModelo({
        titulo: `${m.titulo} (cópia)`, corpo: m.corpo, escopo: m.escopo,
        cargo_alvo: m.cargo_alvo, posto_alvo_id: m.posto_alvo_id,
        candidato_alvo_id: m.candidato_alvo_id, enviar_por_email: m.enviar_por_email,
        exige_assinatura: m.exige_assinatura, papel_assinatura: m.papel_assinatura,
      })
      setMsg({ tipo: 'ok', texto: `Cópia de "${m.titulo}" criada.` })
      await recarregar()
    } catch (e) {
      setMsg({ tipo: 'erro', texto: `Não foi possível duplicar (${e.detail || e.message}).` })
    }
  }

  return (
    <main className="rh-painel">
      <header className="rh-topo"><h1>📝 Modelos de documento</h1><div /></header>
      <div className="rh-card">
      <p className="explica">Crie documentos do zero já no papel timbrado da empresa, com
        variáveis entre chaves duplas preenchidas na hora de gerar. Um modelo pode ser só para
        <strong> baixar</strong>, para <strong>enviar por e-mail</strong> e/ou para
        <strong> assinatura eletrônica</strong> — nesse caso ele entra no mesmo fluxo das fichas
        (código por e-mail, bloco de assinatura, manifesto com papel do signatário e verificação
        pública por QR code).</p>
      <p className="explica" style={{ marginTop: '-.4rem' }}>Variáveis disponíveis:{' '}
        {Object.entries(dados.variaveis).map(([k, desc]) => (
          <code key={k} title={desc} style={{ marginRight: '.4rem' }}>{`{{${k}}}`}</code>
        ))}</p>

      <div className="rh-lote" style={{ margin: '.4rem 0 .6rem' }}>
        <input placeholder="🔎 Buscar modelo pelo título…" value={busca}
               style={{ maxWidth: 280 }} onChange={(e) => setBusca(e.target.value)} />
        <button className="btn-principal btn-mini" onClick={() => setEdit({ ...VAZIO })}>
          + Modelo em branco</button>
        <span className="explica" style={{ margin: 0 }}>ou começar de um padrão:</span>
        {PREDEFINICOES.map((p) => (
          <button key={p.id} className="btn-secundario btn-mini"
                  title={`Abre o editor já com a estrutura de ${p.nome}`}
                  onClick={() => setEdit({ ...VAZIO, titulo: p.titulo, corpo: p.corpo })}>
            {p.nome}</button>
        ))}
      </div>

      {edit && !edit.id && (
        <CamposModelo edit={edit} setEdit={setEdit} postos={postos} papeis={papeis}
                      pessoas={pessoas} salvar={salvar} salvando={salvando}
                      onCancelar={() => setEdit(null)} />
      )}

      {filtrados.length === 0
        ? <p className="explica">Nenhum modelo {busca ? 'encontrado com essa busca' : 'ainda — crie o primeiro acima'}.</p>
        : (
        <table className="rh-tabela">
          <thead><tr><th>Título</th><th>Aplica-se a</th><th>Opções de envio</th><th></th></tr></thead>
          <tbody>
            {filtrados.map((m) => {
              const editando = edit?.id === m.id
              return (
                <Fragment key={m.id}>
                  <tr className={editando ? 'linha-editando' : ''}>
                    <td><strong>{m.titulo}</strong></td>
                    <td>{(ESCOPOS.find((e) => e[0] === m.escopo) || [])[1] || m.escopo}
                      {m.cargo_alvo ? `: ${m.cargo_alvo}` : ''}
                      {m.escopo === 'colaborador' &&
                        `: ${pessoas.find((p) => p.id === m.candidato_alvo_id)?.nome || '…'}`}</td>
                    <td>
                      {m.exige_assinatura && (
                        <span className="chip" style={{ '--chip-cor': '#3b7dd8' }}
                              title={`Vai para assinatura eletrônica${m.papel_assinatura ? ` — assina como ${m.papel_assinatura}` : ''}`}>
                          ✍️ assinatura{m.papel_assinatura ? ` (${m.papel_assinatura})` : ''}</span>
                      )}{' '}
                      {m.enviar_por_email && (
                        <span className="chip" style={{ '--chip-cor': '#0fb257' }}
                              title="Ao enviar, a pessoa recebe por e-mail">✉️ e-mail</span>
                      )}
                      {!m.exige_assinatura && !m.enviar_por_email &&
                        <span className="explica" style={{ margin: 0 }}>só baixar</span>}
                    </td>
                    <td className="acoes-candidato">
                      <button className="btn-secundario btn-mini" title="PDF com as variáveis em aberto"
                              onClick={() => abrirBlob(api.previaModelo(m.id), setMsg)}>Prévia</button>
                      <button className="btn-secundario btn-mini"
                              title="Gerar/baixar/enviar para uma pessoa específica"
                              onClick={() => setEnviando(enviando === m.id ? null : m.id)}>
                        📤 Enviar</button>
                      <button className="btn-secundario btn-mini"
                              title="Autorizações da equipe e roteiro-padrão de assinatura"
                              onClick={() => setAssinaturas(assinaturas === m.id ? null : m.id)}>
                        🎭 Assinaturas</button>
                      <button className="btn-secundario btn-mini"
                              onClick={() => editando ? setEdit(null) : setEdit({
                        id: m.id, titulo: m.titulo, corpo: m.corpo, escopo: m.escopo,
                        cargo_alvo: m.cargo_alvo || '', posto_alvo_id: m.posto_alvo_id || '',
                        candidato_alvo_id: m.candidato_alvo_id || '',
                        enviar_por_email: m.enviar_por_email, exige_assinatura: m.exige_assinatura,
                        papel_assinatura: m.papel_assinatura || '',
                      })}>{editando ? 'Fechar' : 'Editar'}</button>
                      <button className="btn-link" title="Criar uma cópia deste modelo"
                              onClick={() => duplicar(m)}>duplicar</button>
                      <button className="btn-link" onClick={async () => {
                        if (!window.confirm(`Excluir o modelo "${m.titulo}"? Ele vai para a lixeira.`)) return
                        await api.excluirModelo(m.id); await recarregar()
                      }}>excluir</button>
                    </td>
                  </tr>
                  {editando && (
                    <tr className="linha-form-inline">
                      <td colSpan={4}>
                        <CamposModelo edit={edit} setEdit={setEdit} postos={postos}
                                      papeis={papeis} pessoas={pessoas} inline
                                      salvar={salvar} salvando={salvando}
                                      onCancelar={() => setEdit(null)} />
                      </td>
                    </tr>
                  )}
                  {enviando === m.id && (
                    <tr className="linha-form-inline">
                      <td colSpan={4}>
                        <EnviarParaPessoa modelo={m} pessoas={pessoas} setMsg={setMsg}
                                          aoFechar={() => setEnviando(null)} />
                      </td>
                    </tr>
                  )}
                  {assinaturas === m.id && (
                    <tr className="linha-form-inline">
                      <td colSpan={4}>
                        <AssinaturasDoModelo modelo={m} papeis={papeis} setMsg={setMsg}
                                             aoFechar={() => setAssinaturas(null)} />
                      </td>
                    </tr>
                  )}
                </Fragment>
              )
            })}
          </tbody>
        </table>
      )}
      <Msg msg={msg} />
      </div>
    </main>
  )
}

// Painel de assinaturas do modelo: autorizações da equipe (assinatura por
// autorização prévia registrada) + roteiro-padrão de papéis.
function AssinaturasDoModelo({ modelo, papeis, setMsg, aoFechar }) {
  const [autos, setAutos] = useState(null)
  const [rotinaPadrao, setRotinaPadrao] = useState(null)
  const [nova, setNova] = useState(null) // {nome, cargo, email, cpf, papel}
  const [confirmando, setConfirmando] = useState(null) // {id, codigo}

  const recarregar = () => api.autorizacoesEquipe(modelo.id).then((r) => setAutos(r.autorizacoes))
  const recarregarPadrao = () => api.roteiroPadrao(modelo.id)
    .then((r) => setRotinaPadrao(r.etapas)).catch(() => setRotinaPadrao([]))
  useEffect(() => { recarregar().catch(() => setAutos([])); recarregarPadrao() }, [modelo.id])

  return (
    <div className="form-inline-conteudo">
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <strong>🎭 Assinaturas de "{modelo.titulo}"</strong>
        <button className="btn-link" onClick={aoFechar}>fechar</button>
      </div>

      {/* --- Roteiro-padrão de papéis --- */}
      <p className="explica" style={{ marginTop: '.5rem' }}><strong>Roteiro-padrão:</strong> papéis
        que este documento pede por padrão (as pessoas você escolhe na hora de coletar). Deixe
        vazio se cada envio tem um roteiro diferente.</p>
      {rotinaPadrao && <RoteiroPadraoEditor modelo={modelo} papeis={papeis}
        etapas={rotinaPadrao} setMsg={setMsg} recarregar={recarregarPadrao} />}

      {/* --- Autorizações da equipe --- */}
      <p className="explica" style={{ marginTop: '.8rem' }}><strong>Assinatura da equipe:</strong> um
        representante autoriza <em>uma vez</em> (confirma por código no e-mail) que a assinatura dele
        conste nos documentos deste modelo. Não é assinatura no ato — o documento diz "emitido sob
        autorização de X". Revogável a qualquer momento.</p>
      {!autos ? <p>Carregando…</p> : (
        <table className="rh-tabela">
          <thead><tr><th>Representante</th><th>Papel</th><th>Situação</th><th></th></tr></thead>
          <tbody>
            {autos.map((a) => (
              <tr key={a.id}>
                <td><strong>{a.nome}</strong>{a.cargo ? ` — ${a.cargo}` : ''}<br /><small>{a.email}</small></td>
                <td>{a.papel}</td>
                <td>{a.revogada_em ? '⚪ revogada'
                  : a.ativa ? '🟢 ativa'
                  : a.autorizado_em ? '⏳ expirada' : '📧 aguardando confirmação'}</td>
                <td className="acoes-candidato">
                  {!a.autorizado_em && (
                    confirmando?.id === a.id ? (
                      <span className="rejeicao">
                        <input inputMode="numeric" maxLength={6} placeholder="Código"
                               value={confirmando.codigo} style={{ maxWidth: 90 }}
                               onChange={(e) => setConfirmando({ ...confirmando, codigo: e.target.value.replace(/\D/g, '') })} />
                        <button className="btn-principal btn-mini" onClick={async () => {
                          setMsg(null)
                          try {
                            await api.confirmarAutorizacaoEquipe(a.id, confirmando.codigo)
                            setConfirmando(null); await recarregar()
                            setMsg({ tipo: 'ok', texto: `Autorização de ${a.nome} confirmada e ativa.` })
                          } catch (e) {
                            setMsg({ tipo: 'erro', texto: e.detail === 'codigo_incorreto'
                              ? 'Código incorreto.' : `Não confirmou (${e.detail || e.message}).` })
                          }
                        }}>Confirmar</button>
                        <button className="btn-link" onClick={() => setConfirmando(null)}>cancelar</button>
                      </span>
                    ) : (
                      <button className="btn-secundario btn-mini"
                              title="Digite aqui o código que o representante recebeu por e-mail"
                              onClick={() => setConfirmando({ id: a.id, codigo: '' })}>Confirmar código</button>
                    )
                  )}
                  {a.ativa && (
                    <button className="btn-link" onClick={async () => {
                      if (!window.confirm(`Revogar a autorização de ${a.nome}?`)) return
                      await api.revogarAutorizacaoEquipe(a.id); await recarregar()
                    }}>revogar</button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {!nova ? (
        <button className="btn-secundario btn-mini" style={{ marginTop: '.5rem' }}
                onClick={() => setNova({ nome: '', cargo: '', email: '', cpf: '', papel: 'Contratante' })}>
          + Autorizar representante</button>
      ) : (
        <div className="rh-lote" style={{ marginTop: '.5rem' }}>
          <input placeholder="Nome" value={nova.nome} style={{ maxWidth: 160 }}
                 onChange={(e) => setNova({ ...nova, nome: e.target.value })} />
          <input placeholder="Cargo (opcional)" value={nova.cargo} style={{ maxWidth: 140 }}
                 onChange={(e) => setNova({ ...nova, cargo: e.target.value })} />
          <input placeholder="E-mail" value={nova.email} style={{ maxWidth: 180 }}
                 onChange={(e) => setNova({ ...nova, email: e.target.value })} />
          <select value={nova.papel} onChange={(e) => setNova({ ...nova, papel: e.target.value })}>
            {papeis.map((p) => <option key={p.id} value={p.nome}>{p.nome}</option>)}
          </select>
          <button className="btn-principal btn-mini" disabled={!nova.nome.trim() || !nova.email.trim()}
                  onClick={async () => {
                    setMsg(null)
                    try {
                      await api.criarAutorizacaoEquipe({ modelo_id: modelo.id, nome: nova.nome.trim(),
                        cargo: nova.cargo.trim() || null, email: nova.email.trim(),
                        cpf: nova.cpf.trim() || null, papel: nova.papel })
                      setNova(null); await recarregar()
                      setMsg({ tipo: 'ok', texto: 'Enviamos um código ao representante — quando ele passar, use "Confirmar código".' })
                    } catch (e) {
                      setMsg({ tipo: 'erro', texto: `Não foi possível (${e.detail || e.message}).` })
                    }
                  }}>Enviar código</button>
          <button className="btn-link" onClick={() => setNova(null)}>cancelar</button>
        </div>
      )}
    </div>
  )
}

// Editor do roteiro-padrão de papéis do modelo (só papel/ordem/tipo — as
// pessoas são escolhidas no disparo).
function RoteiroPadraoEditor({ modelo, papeis, etapas, setMsg, recarregar }) {
  const [linhas, setLinhas] = useState(etapas)
  useEffect(() => { setLinhas(etapas) }, [etapas])
  const set = (i, campo, v) => setLinhas(linhas.map((e, j) => j === i ? { ...e, [campo]: v } : e))
  return (
    <div>
      {linhas.map((e, i) => (
        <div key={i} className="rh-lote" style={{ padding: '.25rem 0' }}>
          <input style={{ maxWidth: 55 }} inputMode="numeric" value={e.ordem}
                 onChange={(ev) => set(i, 'ordem', parseInt(ev.target.value, 10) || 1)} />
          <select value={e.papel} onChange={(ev) => set(i, 'papel', ev.target.value)}>
            <option value="">— papel —</option>
            {papeis.map((p) => <option key={p.id} value={p.nome}>{p.nome}</option>)}
          </select>
          <select value={e.tipo_sugerido} onChange={(ev) => set(i, 'tipo_sugerido', ev.target.value)}>
            <option value="candidato">O colaborador</option>
            <option value="usuario_rh">Alguém do RH</option>
            <option value="externo">Externo</option>
          </select>
          <button className="btn-link" onClick={() => setLinhas(linhas.filter((_, j) => j !== i))}>✕</button>
        </div>
      ))}
      <div className="rh-lote">
        <button className="btn-secundario btn-mini" onClick={() =>
          setLinhas([...linhas, { papel: '', ordem: linhas.length + 1, tipo_sugerido: 'candidato' }])}>
          + Papel</button>
        <button className="btn-principal btn-mini" onClick={async () => {
          setMsg(null)
          try {
            await api.salvarRoteiroPadrao(modelo.id,
              linhas.filter((e) => e.papel).map((e) => ({ papel: e.papel, ordem: e.ordem, tipo_sugerido: e.tipo_sugerido })))
            await recarregar()
            setMsg({ tipo: 'ok', texto: 'Roteiro-padrão salvo.' })
          } catch (e) { setMsg({ tipo: 'erro', texto: `Não salvou (${e.detail || e.message}).` }) }
        }}>Salvar roteiro-padrão</button>
      </div>
    </div>
  )
}

// Busca a pessoa e escolhe a ação: baixar o PDF preenchido, enviar por e-mail
// e/ou mandar para assinatura (segue as opções do modelo, com override manual).
function EnviarParaPessoa({ modelo, pessoas, setMsg, aoFechar }) {
  const [busca, setBusca] = useState('')
  const [enviandoId, setEnviandoId] = useState(null)
  const [porEmail, setPorEmail] = useState(modelo.enviar_por_email)
  const [paraAssinatura, setParaAssinatura] = useState(modelo.exige_assinatura)
  const [resultado, setResultado] = useState(null)

  const achados = useMemo(() => {
    const q = busca.trim().toLowerCase()
    if (q.length < 2) return []
    return pessoas.filter((p) => p.nome.toLowerCase().includes(q)).slice(0, 8)
  }, [busca, pessoas])

  return (
    <div className="form-inline-conteudo">
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <strong>📤 Enviar "{modelo.titulo}" para uma pessoa</strong>
        <button className="btn-link" onClick={aoFechar}>fechar</button>
      </div>
      <div className="rh-lote" style={{ margin: '.5rem 0' }}>
        <label style={{ display: 'flex', alignItems: 'center', gap: '.4rem' }}>
          <input type="checkbox" style={{ width: 'auto', minHeight: 0 }} checked={paraAssinatura}
                 onChange={(e) => setParaAssinatura(e.target.checked)} />
          <span>✍️ Enviar para assinatura eletrônica</span>
        </label>
        <label style={{ display: 'flex', alignItems: 'center', gap: '.4rem' }}>
          <input type="checkbox" style={{ width: 'auto', minHeight: 0 }} checked={porEmail}
                 onChange={(e) => setPorEmail(e.target.checked)} />
          <span>✉️ Avisar/enviar por e-mail</span>
        </label>
      </div>
      <input placeholder="🔎 Digite o nome da pessoa (nova ou antiga)…" value={busca}
             autoFocus onChange={(e) => { setBusca(e.target.value); setResultado(null) }} />
      {achados.map((p) => (
        <div key={p.id} className="rh-lote" style={{ padding: '.35rem 0',
             borderBottom: '1px solid var(--borda)' }}>
          <span style={{ flex: 1 }}><strong>{p.nome}</strong>{' '}
            <span className="explica" style={{ margin: 0 }}>({p.extra})</span></span>
          <button className="btn-secundario btn-mini" title="Baixar o PDF preenchido"
                  onClick={() => abrirBlob(api.gerarModelo(p.id, modelo.id), setMsg)}>
            ⬇ Baixar</button>
          <button className="btn-principal btn-mini" disabled={enviandoId === p.id}
                  title={paraAssinatura ? 'Cria a pendência de assinatura e avisa a pessoa'
                                        : 'Envia o PDF por e-mail'}
                  onClick={async () => {
                    if (!paraAssinatura && !porEmail) {
                      setMsg({ tipo: 'erro', texto: 'Marque e-mail e/ou assinatura acima (ou use ⬇ Baixar).' })
                      return
                    }
                    setEnviandoId(p.id); setMsg(null)
                    try {
                      const r = await api.enviarModelo(p.id, modelo.id,
                        { enviar_email: porEmail, para_assinatura: paraAssinatura })
                      setResultado({ pessoa: p.nome, ...r })
                    } catch (e) {
                      setMsg({ tipo: 'erro', texto: `Não foi possível enviar (${e.detail || e.message}).` })
                    } finally { setEnviandoId(null) }
                  }}>{enviandoId === p.id ? 'Enviando…' : '📨 Enviar'}</button>
        </div>
      ))}
      {busca.trim().length >= 2 && achados.length === 0 && (
        <p className="explica">Ninguém encontrado com esse nome.</p>
      )}
      {resultado && (
        <div className="sucesso" style={{ marginTop: '.5rem' }}>
          {resultado.assinatura_criada
            ? <>Documento enviado para assinatura de <strong>{resultado.pessoa}</strong>
                {resultado.email_enviado ? ' — a pessoa foi avisada por e-mail ✓'
                  : ' — e-mail não saiu; copie o link e envie pelo WhatsApp:'}
                {!resultado.email_enviado && resultado.link_magico && (
                  <><code className="link-copiar">{resultado.link_magico}</code>
                  <button className="btn-secundario btn-mini" onClick={(e) => {
                    navigator.clipboard.writeText(resultado.link_magico)
                    e.currentTarget.textContent = '✓ Copiado!'
                  }}>📋 Copiar link</button></>
                )}</>
            : resultado.email_enviado
              ? <>PDF enviado por e-mail para <strong>{resultado.pessoa}</strong> ✓</>
              : <>O e-mail não saiu (a pessoa tem e-mail cadastrado? o envio está configurado?).</>}
        </div>
      )}
    </div>
  )
}

function CamposModelo({ edit, setEdit, postos, papeis, pessoas, salvar, salvando,
                        onCancelar, inline }) {
  const ref = useRef(null)
  useEffect(() => {
    if (inline && ref.current) ref.current.scrollIntoView({ behavior: 'smooth', block: 'center' })
  }, [])
  return (
    <div ref={ref} className={inline ? 'form-inline-conteudo' : ''}>
      <label className="campo"><span className="rotulo">Título (aceita variáveis)</span>
        <input value={edit.titulo} placeholder="Ex.: Declaração de vínculo — {{nome}}" autoFocus
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
        {edit.escopo === 'colaborador' && (
          <label className="campo"><span className="rotulo">Pessoa</span>
            <select value={edit.candidato_alvo_id}
                    onChange={(e) => setEdit({ ...edit, candidato_alvo_id: e.target.value })}>
              <option value="">— escolha —</option>
              {pessoas.map((p) => <option key={p.id} value={p.id}>{p.nome}</option>)}
            </select></label>
        )}
      </div>
      <div className="rh-lote" style={{ margin: '.4rem 0' }}>
        <label style={{ display: 'flex', alignItems: 'center', gap: '.4rem' }}
               title="Ao enviar para uma pessoa, ela recebe por e-mail (o PDF anexo, ou o link de assinatura)">
          <input type="checkbox" style={{ width: 'auto', minHeight: 0 }}
                 checked={!!edit.enviar_por_email}
                 onChange={(e) => setEdit({ ...edit, enviar_por_email: e.target.checked })} />
          <span>✉️ Enviar por e-mail</span>
        </label>
        <label style={{ display: 'flex', alignItems: 'center', gap: '.4rem' }}
               title="A pessoa assina eletronicamente pelo link dela — mesmo fluxo das fichas (código no e-mail, manifesto, QR de verificação)">
          <input type="checkbox" style={{ width: 'auto', minHeight: 0 }}
                 checked={!!edit.exige_assinatura}
                 onChange={(e) => setEdit({ ...edit, exige_assinatura: e.target.checked })} />
          <span>✍️ Exige assinatura eletrônica</span>
        </label>
        {edit.exige_assinatura && (
          <label className="campo" style={{ margin: 0 }}>
            <span className="rotulo">Assina na qualidade de</span>
            <select value={edit.papel_assinatura}
                    onChange={(e) => setEdit({ ...edit, papel_assinatura: e.target.value })}>
              <option value="">Contratado(a) (padrão)</option>
              {papeis.map((p) => <option key={p.id} value={p.nome}>{p.nome}</option>)}
            </select></label>
        )}
      </div>
      <div className="navegacao">
        <button className="btn-secundario" onClick={onCancelar}>Cancelar</button>
        <button className="btn-principal" disabled={salvando} onClick={salvar}>
          {salvando ? 'Salvando…' : 'Salvar modelo'}</button>
      </div>
    </div>
  )
}
