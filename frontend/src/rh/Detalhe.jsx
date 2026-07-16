import { useEffect, useState } from 'react'
import { rh as api } from '../api.js'
import { DICAS } from '../tooltips.js'

const MOTIVOS = [
  ['ilegivel', 'Ilegível'],
  ['doc_errado', 'Documento errado'],
  ['vencido', 'Vencido'],
  ['incompleto', 'Incompleto'],
  ['outro', 'Outro'],
]

// E-mail e celular editáveis pelo RH (caso real: candidato sem e-mail não
// recebia as fichas nem o código de assinatura). Toda alteração vai para a
// auditoria com o antes e o depois.
function ContatoEditavel({ dados, setMsg, recarregar }) {
  const [editando, setEditando] = useState(false)
  const [email, setEmail] = useState(dados.email || '')
  const [celular, setCelular] = useState(dados.celular_whatsapp || '')
  const [salvando, setSalvando] = useState(false)
  if (!editando) {
    return (
      <>
        {dados.email || 'sem e-mail'} · {dados.celular_whatsapp || 'sem celular'}
        <button className="btn-link" title="Corrigir e-mail/celular (fica na auditoria)"
                onClick={() => setEditando(true)}>✏️ editar contato</button>
      </>
    )
  }
  return (
    <span className="contato-editavel">
      <input type="email" placeholder="E-mail" value={email}
             onChange={(e) => setEmail(e.target.value)} />
      <input placeholder="Celular/WhatsApp" value={celular}
             onChange={(e) => setCelular(e.target.value)} />
      <button className="btn-principal btn-mini" disabled={salvando} onClick={async () => {
        setSalvando(true); setMsg(null)
        try {
          await api.editarContato(dados.id, {
            email: email.trim() || null, celular_whatsapp: celular.trim() || null,
          })
          setMsg({ tipo: 'ok', texto: 'Contato atualizado (registrado na auditoria).' })
          setEditando(false)
          await recarregar()
        } catch (e) {
          setMsg({ tipo: 'erro', texto: `Não foi possível salvar (${Array.isArray(e.detail)
            ? 'e-mail inválido' : e.detail || e.message}).` })
        } finally { setSalvando(false) }
      }}>{salvando ? 'Salvando…' : 'Salvar'}</button>
      <button className="btn-link" onClick={() => setEditando(false)}>cancelar</button>
    </span>
  )
}

function PostoServico({ dados, setMsg, recarregar }) {
  const [postos, setPostos] = useState(null)
  const [postoId, setPostoId] = useState(dados.posto_servico_id || '')
  const [cargo, setCargo] = useState(dados.cargo_funcao || '')
  const [salvando, setSalvando] = useState(false)
  useEffect(() => { api.postos().then(setPostos) }, [])
  if (!postos) return null
  const extras = (dados.assinaturas || []).filter((a) =>
    !['ficha_cadastro', 'ficha_emergencia', 'termo_vt'].includes(a.documento))
  return (
    <div className="rh-card rh-lote">
      <strong>Posto de serviço:</strong>
      <select value={postoId} style={{ maxWidth: 220 }}
              onChange={(e) => setPostoId(e.target.value)}>
        <option value="">— sem posto —</option>
        {postos.map((p) => <option key={p.id} value={p.id}>
          {p.nome}{p.contrato_ref ? ` — ${p.contrato_ref}` : ''}</option>)}
      </select>
      {postoId && (postos.find((p) => p.id === postoId)?.contrato_ref) && (
        <span className="explica" style={{ margin: 0 }}>
          contrato: <strong>{postos.find((p) => p.id === postoId).contrato_ref}</strong> (do
          cadastro do posto — nada para digitar)</span>
      )}
      <input placeholder="Cargo/função (ex.: Office Boy)" value={cargo}
             style={{ maxWidth: 260 }} onChange={(e) => setCargo(e.target.value)} />
      <button className="btn-principal btn-mini" disabled={salvando} onClick={async () => {
        setMsg(null); setSalvando(true)
        try {
          const r = await api.definirPosto(dados.id, {
            posto_id: postoId || null, cargo_funcao: cargo.trim() || null,
          })
          setMsg({ tipo: 'ok', texto: r.docs_gerados.length
            ? `Posto salvo. ${r.docs_gerados.length} documento(s) gerados e enviados para assinatura${r.email_enviado ? ' — o colaborador foi avisado por e-mail' : ' (e-mail não configurado: envie o link manualmente)'}.`
            : 'Posto salvo.' })
          await recarregar()
        } catch (e) {
          setMsg({ tipo: 'erro', texto: `Não foi possível salvar o posto (${e.detail || e.message}).` })
        } finally { setSalvando(false) }
      }}>{salvando ? 'Salvando…' : 'Salvar posto'}</button>
      {extras.length > 0 && (
        <span className="explica" style={{ margin: 0, width: '100%' }}>
          Documentos do posto: {extras.map((a) =>
            `${a.titulo} ${a.assinado_em ? '✓ assinado' : '⏳ aguardando assinatura'}`).join(' · ')}
        </span>
      )}
    </div>
  )
}

// Seções e campos que o RH pode completar/corrigir. A validação é a mesma do
// candidato (backend); documentos já assinados que exibem o dado alterado são
// invalidados e voltam para o CANDIDATO assinar — o RH prepara, nunca assina.
const SECOES_FICHA = {
  pessoais: ['nome_completo', 'nome_social', 'nome_mae', 'nome_pai',
             'data_nascimento', 'naturalidade_cidade', 'naturalidade_uf'],
  endereco: ['cep', 'logradouro_numero_complemento', 'bairro', 'cidade', 'uf'],
  documentos: ['rg_numero', 'rg_orgao_emissor', 'rg_data_expedicao', 'cpf',
               'pis_nis_pasep', 'cnh_numero', 'cnh_categoria',
               'titulo_eleitor_numero', 'titulo_eleitor_zona', 'titulo_eleitor_secao'],
  'trabalho-banco': ['tamanho_calca', 'tamanho_camisa', 'tamanho_calcado',
                     'banco', 'pix_tipo', 'pix_chave'],
  'vt-emergencia': ['vt_optante', 'vt_cartao_dftrans', 'vt_trajeto_descricao'],
}
const CHAVE_ESTADO = { 'trabalho-banco': 'trabalho_banco' }

function FichaRH({ id, setMsg }) {
  const [aberta, setAberta] = useState(false)
  const [ficha, setFicha] = useState(null)
  const [edicao, setEdicao] = useState({}) // {`secao.campo`: valor}
  const [motivo, setMotivo] = useState('')
  const [salvando, setSalvando] = useState(null)

  const carregar = () => api.fichaCandidato(id).then(setFicha)
  useEffect(() => { if (aberta) carregar() }, [aberta, id])

  if (!aberta) return (
    <div className="rh-card">
      <button className="btn-secundario btn-mini" onClick={() => setAberta(true)}>
        ✏️ Corrigir dados da ficha</button>
      <span className="explica" style={{ margin: 0 }}> Completa campos faltantes ou corrige
        erros. Fichas já assinadas que exibem o dado alterado voltam para o candidato
        assinar de novo (só as afetadas).</span>
    </div>
  )
  if (!ficha) return <div className="rh-card"><p>Carregando ficha…</p></div>

  const valorAtual = (secao, campo) => {
    const s = ficha[CHAVE_ESTADO[secao] || secao] || {}
    if (secao === 'vt-emergencia') {
      const vt = ficha.vt || {}
      return { vt_optante: vt.optante, vt_cartao_dftrans: vt.cartao_dftrans,
               vt_trajeto_descricao: vt.trajeto_descricao }[campo]
    }
    return s[campo]
  }

  const salvarSecao = async (secao) => {
    const dados = {}
    for (const campo of SECOES_FICHA[secao]) {
      const chave = `${secao}.${campo}`
      if (chave in edicao) dados[campo] = edicao[chave] === '' ? null : edicao[chave]
    }
    if (!Object.keys(dados).length) {
      setMsg({ tipo: 'erro', texto: 'Nenhum campo desta seção foi alterado.' }); return
    }
    if (!motivo.trim()) {
      setMsg({ tipo: 'erro', texto: 'Informe o motivo da correção — ele vai para a auditoria.' }); return
    }
    if (dados.vt_optante !== undefined && dados.vt_optante !== null) {
      dados.vt_optante = String(dados.vt_optante).toLowerCase() === 'true'
    }
    setSalvando(secao); setMsg(null)
    try {
      const r = await api.editarFicha(id, secao, dados, motivo.trim())
      const invalidadas = r.assinaturas_invalidadas || []
      setMsg({ tipo: 'ok', texto: invalidadas.length
        ? `Ficha atualizada. ${invalidadas.length} documento(s) voltaram para assinatura do candidato`
          + (r.email_enviado ? ' — ele foi avisado por e-mail.' : ' — avise-o (e-mail não saiu).')
        : 'Ficha atualizada (nenhum documento assinado foi afetado).' })
      setEdicao((e) => {
        const novo = { ...e }
        Object.keys(novo).forEach((k) => { if (k.startsWith(`${secao}.`)) delete novo[k] })
        return novo
      })
      await carregar()
    } catch (e) {
      const texto = Array.isArray(e.detail)
        ? e.detail.map((d) => `${d.loc?.slice(-1)[0]}: ${d.msg}`).join('; ')
        : (e.detail || e.message)
      setMsg({ tipo: 'erro', texto: `Não foi possível salvar (${texto}).` })
    } finally { setSalvando(null) }
  }

  return (
    <div className="rh-card ficha-rh">
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <strong>✏️ Corrigir dados da ficha</strong>
        <button className="btn-link" onClick={() => setAberta(false)}>fechar</button>
      </div>
      <p className="explica">Datas no formato <code>aaaa-mm-dd</code>. Deixar um campo em
        branco apaga o valor. Toda alteração exige motivo e fica na auditoria com o antes e
        o depois. Se o dado aparece em documento já assinado, a assinatura é invalidada e o
        candidato assina a versão nova — <strong>quem assina é sempre ele</strong>.</p>
      <label className="campo"><span className="rotulo">Motivo da correção (obrigatório)</span>
        <input value={motivo} placeholder="ex.: candidato informou RG errado pelo WhatsApp"
               onChange={(e) => setMotivo(e.target.value)} /></label>
      {Object.entries(SECOES_FICHA).map(([secao, campos]) => (
        <details key={secao} className="ficha-rh-secao">
          <summary>{secao.replace('-', ' e ')}</summary>
          {campos.map((campo) => {
            const chave = `${secao}.${campo}`
            const atual = valorAtual(secao, campo)
            return (
              <label className="campo" key={campo}>
                <span className="rotulo">{campo.replaceAll('_', ' ')}
                  {atual == null || atual === '' ? <em> — vazio</em> : null}</span>
                <input value={chave in edicao ? edicao[chave] : (atual ?? '')}
                       onChange={(e) => setEdicao({ ...edicao, [chave]: e.target.value })} />
              </label>
            )
          })}
          <button className="btn-principal btn-mini" disabled={salvando === secao}
                  onClick={() => salvarSecao(secao)}>
            {salvando === secao ? 'Salvando…' : 'Salvar esta seção'}</button>
        </details>
      ))}
    </div>
  )
}

export default function Detalhe({ id, aoVoltar }) {
  const [dados, setDados] = useState(null)
  const [visualizando, setVisualizando] = useState(null) // slot id
  const [urlPdf, setUrlPdf] = useState(null)
  const [rejeitando, setRejeitando] = useState(null)
  const [motivo, setMotivo] = useState('ilegivel')
  const [obs, setObs] = useState('')
  const [msg, setMsg] = useState(null)
  const [selecionados, setSelecionados] = useState(new Set())
  const [loteRejeitar, setLoteRejeitar] = useState(false)
  const [pendDossie, setPendDossie] = useState(null)

  const recarregar = () => api.detalhe(id).then(setDados)
  useEffect(() => { recarregar() }, [id])

  const ver = async (slot) => {
    setVisualizando(slot.id)
    const blob = await api.arquivo(slot.id)
    setUrlPdf(URL.createObjectURL(blob))
  }

  if (!dados) return <main className="rh-painel"><p>Carregando…</p></main>

  const enviados = dados.slots.filter((s) => s.status === 'enviado')

  const aprovar = async (slotId) => { await api.aprovar(slotId); await recarregar() }
  const rejeitar = async (slotId) => {
    await api.rejeitar(slotId, motivo, obs || null)
    setRejeitando(null); setObs('')
    await recarregar()
  }

  const inputManual = { current: null }

  const inserirNoSlot = (slot) => {
    const origem = window.prompt(
      'Como este documento chegou? (ex.: WhatsApp, e-mail, presencial)', 'WhatsApp')
    if (origem == null) return
    const input = document.createElement('input')
    input.type = 'file'
    input.accept = 'image/*,.pdf,.doc,.docx'
    input.onchange = async () => {
      const arq = input.files[0]
      if (!arq) return
      setMsg(null)
      try {
        await api.inserirArquivo(slot.id, arq, origem.trim() || 'WhatsApp')
        setMsg({ tipo: 'ok', texto: 'Documento inserido e etiquetado — revise e aprove como de costume.' })
        await recarregar()
      } catch (e) {
        setMsg({ tipo: 'erro', texto: `Não foi possível inserir (${e.detail || e.message}).` })
      }
    }
    input.click()
  }

  const reabrir = async (slot) => {
    const motivo = window.prompt('Motivo da reabertura (obrigatório — vai para a auditoria):')
    if (!motivo?.trim()) return
    setMsg(null)
    try {
      await api.reabrirSlot(slot.id, motivo.trim())
      setMsg({ tipo: 'ok', texto: 'Status reaberto (registrado na auditoria).' })
      await recarregar()
    } catch (e) {
      setMsg({ tipo: 'erro', texto: `Não foi possível reabrir (${e.detail || e.message}).` })
    }
  }

  const gerarDossie = async (forcar = false) => {
    setMsg(null); setPendDossie(null)
    try {
      await api.gerarDossie(id, forcar)
      setMsg({ tipo: 'ok', texto: forcar
        ? 'Dossiê PARCIAL gerado (há pendências — o candidato não foi marcado como aprovado).'
        : 'Dossiê gerado! O candidato foi marcado como aprovado.' })
      await recarregar()
    } catch (e) {
      setPendDossie(e.detail?.pendencias || [])
    }
  }

  const baixarDossie = async () => {
    const blob = await api.baixarDossie(id)
    const a = document.createElement('a')
    a.href = URL.createObjectURL(blob)
    a.download = `dossie-${dados.nome_completo}.pdf`
    a.click()
  }

  return (
    <main className="rh-painel">
      <header className="rh-topo">
        <button className="btn-link" onClick={aoVoltar}>← Voltar</button>
        <h1>{dados.nome_completo}</h1>
        <div>
          <button className="btn-secundario" onClick={() => gerarDossie(false)}>Gerar dossiê</button>
          {dados.dossie_gerado_em && (
            <button className="btn-principal" onClick={baixarDossie}>⬇ Baixar dossiê</button>
          )}
        </div>
      </header>
      <p className="explica">
        <ContatoEditavel dados={dados} setMsg={setMsg} recarregar={recarregar} /> · status:
        <strong> {dados.status}</strong>
        {enviados.length > 0 && <> · <strong>{enviados.length} documento(s) aguardando revisão</strong></>}
      </p>
      {msg && <div className={msg.tipo === 'erro' ? 'alerta' : 'sucesso'}>{msg.texto}</div>}

      <PostoServico dados={dados} setMsg={setMsg} recarregar={recarregar} />
      <FichaRH id={id} setMsg={setMsg} />

      {pendDossie && (
        <div className="alerta">
          <strong>O dossiê ainda tem pendências:</strong> {pendDossie.join(', ')}.
          <div style={{ marginTop: '.6rem' }}>
            <button className="btn-secundario btn-mini" onClick={() => gerarDossie(true)}>
              Gerar assim mesmo (dossiê parcial)</button>
            <button className="btn-link" onClick={() => setPendDossie(null)}>cancelar</button>
          </div>
        </div>
      )}

      {enviados.length > 0 && (
        <div className="rh-card rh-lote">
          <strong>Ações em massa:</strong>
          <button className="btn-link" onClick={() =>
            setSelecionados(new Set(enviados.map((s) => s.id)))}>
            selecionar todos em análise ({enviados.length})</button>
          <button className="btn-link" onClick={() => setSelecionados(new Set())}>limpar</button>
          <span className="explica" style={{ margin: 0 }}>{selecionados.size} selecionado(s)</span>
          <button className="btn-principal btn-mini" disabled={!selecionados.size}
                  onClick={async () => {
                    try {
                      const r = await api.aprovarLote([...selecionados])
                      setSelecionados(new Set()); setMsg({ tipo: 'ok',
                        texto: `${r.aprovados} documento(s) aprovado(s).` })
                      await recarregar()
                    } catch (e) {
                      setMsg({ tipo: 'erro',
                        texto: `Não foi possível aprovar em massa (${e.detail || e.message}).` })
                    }
                  }}>Aprovar selecionados</button>
          <button className="btn-rejeitar btn-mini" disabled={!selecionados.size}
                  onClick={() => setLoteRejeitar(!loteRejeitar)}>Rejeitar selecionados</button>
          {loteRejeitar && (
            <div className="rejeicao" style={{ width: '100%' }}>
              <select value={motivo} onChange={(e) => setMotivo(e.target.value)}>
                {MOTIVOS.map(([v, r]) => <option key={v} value={v}>{r}</option>)}
              </select>
              <input placeholder="Observação (opcional)" value={obs}
                     onChange={(e) => setObs(e.target.value)} />
              <button className="btn-rejeitar btn-mini" onClick={async () => {
                try {
                  const r = await api.rejeitarLote([...selecionados], motivo, obs || null)
                  setSelecionados(new Set()); setLoteRejeitar(false); setObs('')
                  setMsg({ tipo: 'ok', texto: `${r.rejeitados} documento(s) rejeitado(s) — o candidato recebeu um único e-mail com a lista.` })
                  await recarregar()
                } catch (e) {
                  setMsg({ tipo: 'erro',
                    texto: `Não foi possível rejeitar em massa (${e.detail || e.message}).` })
                }
              }}>Confirmar rejeição em massa</button>
            </div>
          )}
        </div>
      )}

      <div className="rh-revisao">
        <div className="rh-lista-slots">
          {dados.slots.map((s) => {
            const info = DICAS[s.tipo] || { nome: s.tipo }
            return (
              <div className={`slot ${s.status} ${visualizando === s.id ? 'ativo' : ''}`} key={s.id}>
                <div className="slot-linha">
                  {s.status === 'enviado' && (
                    <input type="checkbox" className="check-slot"
                           checked={selecionados.has(s.id)}
                           onChange={(e) => {
                             const novo = new Set(selecionados)
                             e.target.checked ? novo.add(s.id) : novo.delete(s.id)
                             setSelecionados(novo)
                           }} />
                  )}
                  <div className="slot-nome">
                    <strong>{info.nome}</strong>{!s.obrigatorio && <em> (opcional)</em>}
                    <div className="slot-status">{s.status}
                      {s.paginas ? ` · ${s.paginas} pág.` : ''}
                      {s.origem_envio === 'rh' &&
                        <span className="etiqueta-rh"> 📎 inserido pelo RH
                          {s.origem_envio_obs ? ` (${s.origem_envio_obs})` : ''}</span>}
                    </div>
                  </div>
                  {s.status !== 'pendente' && s.paginas && (
                    <button className="btn-secundario btn-mini" onClick={() => ver(s)}>Ver</button>
                  )}
                  {s.status === 'enviado' && <>
                    <button className="btn-principal btn-mini" onClick={() => aprovar(s.id)}>
                      Aprovar</button>
                    <button className="btn-rejeitar btn-mini"
                            onClick={() => setRejeitando(rejeitando === s.id ? null : s.id)}>
                      Rejeitar</button>
                  </>}
                  {s.status === 'pendente' && !s.obrigatorio && (
                    <button className="btn-link" onClick={async () => {
                      await api.dispensar(s.id); await recarregar()
                    }}>dispensar</button>
                  )}
                  {['pendente', 'rejeitado', 'enviado'].includes(s.status) && (
                    <button className="btn-secundario btn-mini"
                            title="Documento recebido por WhatsApp/e-mail/presencial: insira aqui (fica etiquetado na auditoria)"
                            onClick={() => inserirNoSlot(s)}>📎 Inserir</button>
                  )}
                  {['aprovado', 'dispensado', 'rejeitado'].includes(s.status) && (
                    <button className="btn-link" title="Desfaz a decisão (pede motivo)"
                            onClick={() => reabrir(s)}>↩ reabrir</button>
                  )}
                </div>
                {rejeitando === s.id && (
                  <div className="rejeicao">
                    <select value={motivo} onChange={(e) => setMotivo(e.target.value)}>
                      {MOTIVOS.map(([v, r]) => <option key={v} value={v}>{r}</option>)}
                    </select>
                    <input placeholder="Observação (opcional)" value={obs}
                           onChange={(e) => setObs(e.target.value)} />
                    <button className="btn-rejeitar btn-mini" onClick={() => rejeitar(s.id)}>
                      Confirmar rejeição</button>
                  </div>
                )}
              </div>
            )
          })}
        </div>
        <div className="rh-visualizador">
          {urlPdf ? <iframe title="documento" src={urlPdf} />
                  : <p className="explica centro">Selecione "Ver" em um documento para visualizar aqui.</p>}
        </div>
      </div>
    </main>
  )
}
