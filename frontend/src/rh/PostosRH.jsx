import { Fragment, useEffect, useRef, useState } from 'react'
import { rh as api } from '../api.js'
import { comAmpulheta } from '../Carregando.jsx'
import CheckMestre from '../CheckMestre.jsx'

const VAZIO = { nome: '', sigla: '', cnpj: '', contrato_ref: '', exige_docs_infraero: false,
  documentos_kit: [], atributos: {}, da_direito_creche: false, valor_reembolso_creche: '' }

// Aba própria de Postos: CRUD, importador da planilha do Tirvu, vínculo de
// documentos em massa e colunas dinâmicas.
export default function PostosRH() {
  const [postos, setPostos] = useState(null)
  const [colunas, setColunas] = useState([])
  const [docsDisp, setDocsDisp] = useState({}) // documentos específicos disponíveis
  const [edit, setEdit] = useState(null)      // posto em edição/criação
  const [importar, setImportar] = useState(null) // texto colado
  const [gerColunas, setGerColunas] = useState(null) // string das colunas em edição
  const [msg, setMsg] = useState(null)
  const [selecionados, setSelecionados] = useState(() => new Set())
  const [massaKit, setMassaKit] = useState(null) // painel de vínculo em massa
  const inputPlanilha = useRef(null)

  const recarregar = () => api.postos(true).then((r) => {
    setPostos(r.postos); setColunas(r.colunas || []); setDocsDisp(r.documentos_disponiveis || {}) })
  useEffect(() => { recarregar() }, [])
  if (!postos) return <main className="rh-painel"><p>Carregando…</p></main>

  const importarPlanilha = async (arquivo) => {
    if (!arquivo) return
    setMsg(null)
    try {
      const r = await comAmpulheta('Importando a planilha de postos do Tirvu…',
                                   () => api.importarPostosPlanilha(arquivo))
      setMsg({ tipo: 'ok', texto: `Planilha importada: ${r.criados} novo(s), `
        + `${r.atualizados} atualizado(s). Total: ${r.total} posto(s).` })
      await recarregar()
    } catch (e) {
      setMsg({ tipo: 'erro', texto: e.detail === 'sem_coluna_nome'
        ? 'A planilha precisa ter a coluna "Nome / Apelido". Confira o export do Tirvu.'
        : `Falha ao importar a planilha (${e.detail || e.message}).` })
    } finally { if (inputPlanilha.current) inputPlanilha.current.value = '' }
  }

  const alternarSel = (id) => setSelecionados((s) => {
    const n = new Set(s); n.has(id) ? n.delete(id) : n.add(id); return n
  })
  const idsVisiveis = postos.map((p) => p.id)
  const todosSelecionados = idsVisiveis.length > 0 && idsVisiveis.every((id) => selecionados.has(id))
  const algunsSelecionados = idsVisiveis.some((id) => selecionados.has(id))
  const marcarTodos = (marcar) =>
    setSelecionados(marcar ? new Set(idsVisiveis) : new Set())
  const aplicarMassa = async (payload) => {
    setMsg(null)
    try {
      const r = await comAmpulheta('Aplicando aos postos selecionados…',
        () => api.editarPostosMassa({ posto_ids: [...selecionados], ...payload }))
      setMsg({ tipo: 'ok', texto: `${r.atualizados} posto(s) atualizado(s).` })
      setSelecionados(new Set()); setMassaKit(null); await recarregar()
    } catch (e) {
      setMsg({ tipo: 'erro', texto: `Falha na edição em massa (${e.detail || e.message}).` })
    }
  }
  const acaoMassa = async (acao) => {
    const n = selecionados.size
    const verbo = { ativar: 'Ativar', desativar: 'Desativar', excluir: 'EXCLUIR DEFINITIVAMENTE' }[acao]
    const aviso = acao === 'excluir'
      ? `EXCLUIR ${n} posto(s) DE FORMA DEFINITIVA?\n\nSó os postos SEM colaborador vinculado serão`
        + ' apagados; os demais são mantidos (desative-os se quiser escondê-los). Esta ação NÃO tem volta.'
      : `${verbo} ${n} posto(s) selecionado(s)?`
    if (!window.confirm(aviso)) return
    if (acao === 'excluir' && !window.confirm('Tem certeza? A exclusão é permanente.')) return
    setMsg(null)
    try {
      const r = await comAmpulheta(`${verbo} postos…`,
        () => api.acaoMassaPostos([...selecionados], acao))
      let txt = `${r.afetados} posto(s) ${acao === 'ativar' ? 'ativado(s)'
        : acao === 'desativar' ? 'desativado(s)' : 'excluído(s)'}.`
      if (r.bloqueados?.length) txt += ` ${r.bloqueados.length} não foram excluídos por terem`
        + ` colaboradores vinculados (${r.bloqueados.slice(0, 3).join(', ')}${r.bloqueados.length > 3 ? '…' : ''}) — desative-os se quiser.`
      setMsg({ tipo: r.bloqueados?.length ? 'erro' : 'ok', texto: txt })
      setSelecionados(new Set()); await recarregar()
    } catch (e) {
      setMsg({ tipo: 'erro', texto: `Falha na ação em massa (${e.detail || e.message}).` })
    }
  }

  const salvar = async () => {
    if (!edit.nome.trim()) { setMsg({ tipo: 'erro', texto: 'Informe o nome do posto.' }); return }
    const corpo = {
      nome: edit.nome.trim(), sigla: edit.sigla.trim() || null, cnpj: edit.cnpj.trim() || null,
      contrato_ref: edit.contrato_ref.trim() || null,
      exige_docs_infraero: !!edit.exige_docs_infraero,
      documentos_kit: edit.documentos_kit || [], atributos: edit.atributos || {},
      da_direito_creche: !!edit.da_direito_creche,
      valor_reembolso_creche: (edit.valor_reembolso_creche || '').trim() || null,
    }
    try {
      if (edit.id) await api.editarPosto(edit.id, corpo)
      else await api.criarPosto(corpo)
      setEdit(null); setMsg({ tipo: 'ok', texto: 'Posto salvo.' }); await recarregar()
    } catch (e) {
      setMsg({ tipo: 'erro', texto: e.detail === 'posto_ja_existe'
        ? 'Já existe um posto com esse nome.' : `Não foi possível salvar (${e.detail || e.message}).` })
    }
  }

  return (
    <main className="rh-painel">
      <header className="rh-topo"><h1>🏢 Postos de serviço</h1><div /></header>
      <p className="explica">Lotações onde os colaboradores são alocados. Cada posto tem sigla,
        CNPJ do tomador e contrato. <strong>Importe direto a planilha de Postos do Tirvu (.xlsx)</strong> —
        o sistema casa por ID do Tirvu (não duplica), enriquece com razão social, CNPJ e endereço, e
        desambigua apelidos repetidos. Marque documentos específicos por posto, em massa se quiser.</p>

      <div className="rh-card rh-lote">
        <button className="btn-principal btn-mini" onClick={() => setEdit({ ...VAZIO })}>+ Novo posto</button>
        <input ref={inputPlanilha} type="file" accept=".xlsx" hidden
               onChange={(e) => importarPlanilha(e.target.files?.[0])} />
        <button className="btn-secundario btn-mini"
                onClick={() => inputPlanilha.current?.click()}>⬆ Importar planilha do Tirvu</button>
        <button className="btn-secundario btn-mini" onClick={() => setImportar('')}>Colar lista</button>
        <button className="btn-secundario btn-mini"
                onClick={() => setGerColunas(colunas.join(', '))}>⚙ Colunas ({colunas.length})</button>
        <span className="explica" style={{ margin: 0 }}>{postos.length} posto(s)</span>
      </div>

      {selecionados.size > 0 && (
        <div className="rh-card rh-lote" style={{ alignItems: 'center' }}>
          <strong>{selecionados.size} posto(s) selecionado(s):</strong>
          <button className="btn-secundario btn-mini" onClick={() => setMassaKit({})}>
            🗂️ Vincular documentos / creche</button>
          <button className="btn-secundario btn-mini" onClick={() => acaoMassa('ativar')}>✅ Ativar</button>
          <button className="btn-secundario btn-mini" onClick={() => acaoMassa('desativar')}>🚫 Desativar</button>
          <button className="btn-secundario btn-mini" onClick={() => acaoMassa('excluir')}
                  style={{ color: '#d9534f' }}>🗑️ Excluir</button>
          {!todosSelecionados && (
            <button className="btn-link" onClick={() => marcarTodos(true)}>
              selecionar todos ({postos.length})</button>)}
          <button className="btn-link" onClick={() => setSelecionados(new Set())}>limpar seleção</button>
        </div>
      )}

      {massaKit && (
        <div className="rh-card">
          <h3>Aplicar a {selecionados.size} posto(s)</h3>
          <p className="explica">Marque o que aplicar aos postos selecionados. Só os campos que você
            mexer são alterados; os demais ficam como estão em cada posto.</p>
          <span className="rotulo">Documentos do kit</span>
          <p className="explica" style={{ margin: '.2rem 0 .4rem' }}>Os documentos marcados são
            <strong> adicionados</strong> ao kit de cada posto selecionado (não remove os que já têm).</p>
          {Object.entries(docsDisp).map(([chave, rotulo]) => (
            <label key={chave} style={{ display: 'flex', alignItems: 'center', gap: '.5rem', marginBottom: '.25rem' }}>
              <input type="checkbox" style={{ width: 'auto', minHeight: 0 }}
                     checked={(massaKit.documentos_kit || []).includes(chave)}
                     onChange={(e) => setMassaKit({ ...massaKit, documentos_kit: e.target.checked
                       ? [...(massaKit.documentos_kit || []), chave]
                       : (massaKit.documentos_kit || []).filter((k) => k !== chave) })} />
              <span>{rotulo}</span>
            </label>
          ))}
          <label style={{ display: 'flex', alignItems: 'center', gap: '.5rem', margin: '.6rem 0 .3rem' }}>
            <input type="checkbox" style={{ width: 'auto', minHeight: 0 }}
                   checked={massaKit.marcar_creche || false}
                   onChange={(e) => setMassaKit({ ...massaKit, marcar_creche: e.target.checked })} />
            <span>Marcar como <strong>dá direito ao reembolso-creche</strong></span>
          </label>
          {massaKit.marcar_creche && (
            <input placeholder="Valor do reembolso (ex.: R$ 526,64) — opcional"
                   value={massaKit.valor_reembolso_creche || ''} style={{ maxWidth: 300 }}
                   onChange={(e) => setMassaKit({ ...massaKit, valor_reembolso_creche: e.target.value })} />
          )}
          <div className="navegacao">
            <button className="btn-secundario" onClick={() => setMassaKit(null)}>Cancelar</button>
            <button className="btn-principal" onClick={() => aplicarMassa({
              documentos_kit: massaKit.documentos_kit || [], modo_kit: 'adicionar',
              ...(massaKit.marcar_creche ? { da_direito_creche: true,
                    valor_reembolso_creche: massaKit.valor_reembolso_creche || null } : {}),
            })}>Aplicar aos selecionados</button>
          </div>
        </div>
      )}

      {msg && <div className={msg.tipo === 'erro' ? 'alerta' : 'sucesso'}>{msg.texto}</div>}

      {gerColunas !== null && (
        <div className="rh-card">
          <h3>Colunas dinâmicas</h3>
          <p className="explica">Nomes das colunas extras, separados por vírgula (ex.: "Gestor,
            Turno, Endereço do posto"). Elas aparecem na tabela e no cadastro de cada posto.</p>
          <input value={gerColunas} onChange={(e) => setGerColunas(e.target.value)}
                 placeholder="Gestor, Turno, Observação" />
          <div className="navegacao">
            <button className="btn-secundario" onClick={() => setGerColunas(null)}>Cancelar</button>
            <button className="btn-principal" onClick={async () => {
              const cols = gerColunas.split(',').map((c) => c.trim()).filter(Boolean)
              await api.definirColunasPosto(cols); setGerColunas(null); await recarregar()
              setMsg({ tipo: 'ok', texto: 'Colunas atualizadas.' })
            }}>Salvar colunas</button>
          </div>
        </div>
      )}

      {importar !== null && (
        <div className="rh-card">
          <h3>Importar postos</h3>
          <p className="explica">Cole <strong>uma linha por posto</strong>, com os campos separados
            por <strong>;</strong> (ponto e vírgula) ou tabulação, nesta ordem:
            <code> Nome; Sigla; CNPJ; Contrato</code>. Só o nome é obrigatório. Postos já existentes
            são ignorados (não duplica).</p>
          <textarea rows={8} value={importar} onChange={(e) => setImportar(e.target.value)}
                    placeholder={'INSTITUTO NACIONAL DE ESTUDOS E PESQUISAS; INEP Adm; 01.678.363/0001-43\nPRESIDENCIA DA REPUBLICA; PRESIDENCIA; 00.394.411/0001-09'} />
          <div className="navegacao">
            <button className="btn-secundario" onClick={() => setImportar(null)}>Cancelar</button>
            <button className="btn-principal" onClick={async () => {
              try {
                const r = await api.importarPostos(importar)
                setImportar(null); await recarregar()
                setMsg({ tipo: 'ok', texto: `${r.criados.length} posto(s) criado(s)`
                  + (r.pulados.length ? `, ${r.pulados.length} já existiam (ignorados).` : '.') })
              } catch (e) {
                setMsg({ tipo: 'erro', texto: `Falha ao importar (${e.detail || e.message}).` })
              }
            }}>Importar</button>
          </div>
        </div>
      )}

      {/* Card no topo APENAS para criação de posto novo (aí faz sentido estar
          no topo). A EDIÇÃO acontece inline, na própria linha da tabela. */}
      {edit && !edit.id && (
        <div className="rh-card">
          <h3>Novo posto</h3>
          <CamposPosto edit={edit} setEdit={setEdit} docsDisp={docsDisp} colunas={colunas}
                       salvar={salvar} onCancelar={() => setEdit(null)} />
        </div>
      )}

      <table className="rh-tabela">
        <thead><tr>
          <th style={{ width: 34 }}>
            <CheckMestre marcado={todosSelecionados} parcial={algunsSelecionados && !todosSelecionados}
                         onChange={() => marcarTodos(!todosSelecionados)}
                         title="Selecionar todos os postos visíveis" />
          </th>
          <th>Sigla</th><th>Nome</th><th>CNPJ</th><th>Contrato</th>
          {colunas.map((c) => <th key={c}>{c}</th>)}<th></th></tr></thead>
        <tbody>
          {postos.map((p) => {
            const editando = edit?.id === p.id
            return (
              <Fragment key={p.id}>
                <tr style={p.ativo ? {} : { opacity: .5 }}
                    className={editando ? 'linha-editando' : ''}>
                  <td><input type="checkbox" style={{ width: 'auto', minHeight: 0 }}
                             checked={selecionados.has(p.id)} onChange={() => alternarSel(p.id)}
                             title="Selecionar para ação em massa" /></td>
                  <td><strong>{p.sigla || '—'}</strong></td>
                  <td>{p.nome}{(p.exige_docs_infraero || (p.documentos_kit || []).length) ? ' 🗂️' : ''}
                    {p.da_direito_creche ? <span title={`Reembolso-creche${p.valor_reembolso_creche ? ': ' + p.valor_reembolso_creche : ''}`}> 🍼</span> : ''}</td>
                  <td>{p.cnpj || '—'}</td>
                  <td>{p.contrato_ref || '—'}</td>
                  {colunas.map((c) => <td key={c}>{(p.atributos || {})[c] || '—'}</td>)}
                  <td className="acoes-candidato">
                    <button className="btn-secundario btn-mini" onClick={() => editando ? setEdit(null) : setEdit({
                      ...p, sigla: p.sigla || '', cnpj: p.cnpj || '', contrato_ref: p.contrato_ref || '',
                      documentos_kit: p.documentos_kit || [], atributos: p.atributos || {},
                      da_direito_creche: !!p.da_direito_creche,
                      valor_reembolso_creche: p.valor_reembolso_creche || '',
                    })}>{editando ? 'Fechar' : 'Editar'}</button>
                    {p.ativo && (
                      <button className="btn-link" onClick={async () => {
                        if (!window.confirm(`Desativar o posto "${p.nome}"? Ele some das listas de escolha (colaboradores já vinculados seguem intactos).`)) return
                        await api.excluirPosto(p.id); await recarregar()
                      }}>desativar</button>
                    )}
                  </td>
                </tr>
                {editando && (
                  <tr className="linha-form-inline">
                    <td colSpan={6 + colunas.length}>
                      <CamposPosto edit={edit} setEdit={setEdit} docsDisp={docsDisp}
                                   colunas={colunas} salvar={salvar}
                                   onCancelar={() => setEdit(null)} />
                    </td>
                  </tr>
                )}
              </Fragment>
            )
          })}
        </tbody>
      </table>
    </main>
  )
}

// Campos do posto — usado tanto no card de criação (topo) quanto inline na
// linha da tabela (edição). Ao montar inline, rola a si mesmo para o centro,
// para o RH não se perder quando edita um posto lá no fim da lista.
function CamposPosto({ edit, setEdit, docsDisp, colunas, salvar, onCancelar }) {
  const ref = useRef(null)
  useEffect(() => {
    // só rola quando é edição inline (posto já existente)
    if (edit?.id && ref.current) {
      ref.current.scrollIntoView({ behavior: 'smooth', block: 'center' })
    }
  }, [])
  return (
    <div ref={ref} className="form-posto">
      <div className="linha3">
        <input placeholder="Nome do posto" value={edit.nome} autoFocus
               onChange={(e) => setEdit({ ...edit, nome: e.target.value })} />
        <input placeholder="Sigla (ex.: INEP Adm)" value={edit.sigla}
               onChange={(e) => setEdit({ ...edit, sigla: e.target.value })} />
        <input placeholder="CNPJ" value={edit.cnpj}
               onChange={(e) => setEdit({ ...edit, cnpj: e.target.value })} />
      </div>
      <input placeholder="Contrato de referência" value={edit.contrato_ref}
             onChange={(e) => setEdit({ ...edit, contrato_ref: e.target.value })} />
      {Object.keys(docsDisp).length > 0 && (
        <div style={{ marginTop: '.6rem' }}>
          <span className="rotulo">Documentos específicos deste posto (kit)</span>
          <p className="explica" style={{ margin: '.2rem 0 .4rem' }}>Marque só se este posto
            exige documentos além dos obrigatórios padrão. Eles entram no kit de assinatura e
            no dossiê. A maioria dos postos não marca nada.</p>
          {Object.entries(docsDisp).map(([chave, rotulo]) => {
            const marcado = (edit.documentos_kit || []).includes(chave)
            return (
              <label key={chave} style={{ display: 'flex', alignItems: 'center', gap: '.5rem', marginBottom: '.25rem' }}>
                <input type="checkbox" style={{ width: 'auto', minHeight: 0 }} checked={marcado}
                       onChange={(e) => setEdit({ ...edit, documentos_kit: e.target.checked
                         ? [...(edit.documentos_kit || []), chave]
                         : (edit.documentos_kit || []).filter((k) => k !== chave) })} />
                <span>{rotulo}</span>
              </label>
            )
          })}
        </div>
      )}
      <div style={{ marginTop: '.6rem' }}>
        <span className="rotulo">Reembolso-Creche (IN SEGES/MGI 147/2026)</span>
        <p className="explica" style={{ margin: '.2rem 0 .4rem' }}>Marque se este tomador/contrato
          dá direito ao benefício. O valor varia por posto (repactuação do contrato) — informe o
          valor vigente; deixe em branco enquanto o contrato não for repactuado.</p>
        <label style={{ display: 'flex', alignItems: 'center', gap: '.5rem', marginBottom: '.4rem' }}>
          <input type="checkbox" style={{ width: 'auto', minHeight: 0 }}
                 checked={!!edit.da_direito_creche}
                 onChange={(e) => setEdit({ ...edit, da_direito_creche: e.target.checked })} />
          <span>Este posto dá direito ao reembolso-creche</span>
        </label>
        {edit.da_direito_creche && (
          <input placeholder="Valor do reembolso (ex.: R$ 526,64)"
                 value={edit.valor_reembolso_creche || ''} style={{ maxWidth: 280 }}
                 onChange={(e) => setEdit({ ...edit, valor_reembolso_creche: e.target.value })} />
        )}
      </div>
      {colunas.length > 0 && (
        <div className="linha3">
          {colunas.map((c) => (
            <input key={c} placeholder={c} value={(edit.atributos || {})[c] || ''}
                   onChange={(e) => setEdit({ ...edit, atributos: { ...edit.atributos, [c]: e.target.value } })} />
          ))}
        </div>
      )}
      <div className="navegacao">
        <button className="btn-secundario" onClick={onCancelar}>Cancelar</button>
        <button className="btn-principal" onClick={salvar}>Salvar posto</button>
      </div>
    </div>
  )
}
