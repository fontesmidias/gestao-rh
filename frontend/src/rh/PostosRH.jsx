import { useEffect, useState } from 'react'
import { rh as api } from '../api.js'

const VAZIO = { nome: '', sigla: '', cnpj: '', contrato_ref: '', exige_docs_infraero: false,
  documentos_kit: [], atributos: {}, da_direito_creche: false, valor_reembolso_creche: '' }

// Aba própria de Postos: CRUD, importador em massa da lista de lotações e
// colunas dinâmicas (o RH cria colunas novas sem mexer no banco).
export default function PostosRH() {
  const [postos, setPostos] = useState(null)
  const [colunas, setColunas] = useState([])
  const [docsDisp, setDocsDisp] = useState({}) // documentos específicos disponíveis
  const [edit, setEdit] = useState(null)      // posto em edição/criação
  const [importar, setImportar] = useState(null) // texto colado
  const [gerColunas, setGerColunas] = useState(null) // string das colunas em edição
  const [msg, setMsg] = useState(null)

  const recarregar = () => api.postos(true).then((r) => {
    setPostos(r.postos); setColunas(r.colunas || []); setDocsDisp(r.documentos_disponiveis || {}) })
  useEffect(() => { recarregar() }, [])
  if (!postos) return <main className="rh-painel"><p>Carregando…</p></main>

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
        CNPJ do tomador e contrato. Importe a lista de uma vez, edite pelo painel e crie colunas
        próprias para oportunidades futuras. Postos com documentação específica (Presidência,
        INFRAERO) terão o kit próprio na etapa de documentos por posto.</p>

      <div className="rh-card rh-lote">
        <button className="btn-principal btn-mini" onClick={() => setEdit({ ...VAZIO })}>+ Novo posto</button>
        <button className="btn-secundario btn-mini" onClick={() => setImportar('')}>⬆ Importar lista</button>
        <button className="btn-secundario btn-mini"
                onClick={() => setGerColunas(colunas.join(', '))}>⚙ Colunas ({colunas.length})</button>
        <span className="explica" style={{ margin: 0 }}>{postos.length} posto(s)</span>
      </div>

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

      {edit && (
        <div className="rh-card">
          <h3>{edit.id ? 'Editar posto' : 'Novo posto'}</h3>
          <div className="linha3">
            <input placeholder="Nome do posto" value={edit.nome}
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
            <button className="btn-secundario" onClick={() => setEdit(null)}>Cancelar</button>
            <button className="btn-principal" onClick={salvar}>Salvar posto</button>
          </div>
        </div>
      )}

      <table className="rh-tabela">
        <thead><tr><th>Sigla</th><th>Nome</th><th>CNPJ</th><th>Contrato</th>
          {colunas.map((c) => <th key={c}>{c}</th>)}<th></th></tr></thead>
        <tbody>
          {postos.map((p) => (
            <tr key={p.id} style={p.ativo ? {} : { opacity: .5 }}>
              <td><strong>{p.sigla || '—'}</strong></td>
              <td>{p.nome}{(p.exige_docs_infraero || (p.documentos_kit || []).length) ? ' 🗂️' : ''}
                {p.da_direito_creche ? <span title={`Reembolso-creche${p.valor_reembolso_creche ? ': ' + p.valor_reembolso_creche : ''}`}> 🍼</span> : ''}</td>
              <td>{p.cnpj || '—'}</td>
              <td>{p.contrato_ref || '—'}</td>
              {colunas.map((c) => <td key={c}>{(p.atributos || {})[c] || '—'}</td>)}
              <td className="acoes-candidato">
                <button className="btn-secundario btn-mini" onClick={() => setEdit({
                  ...p, sigla: p.sigla || '', cnpj: p.cnpj || '', contrato_ref: p.contrato_ref || '',
                  documentos_kit: p.documentos_kit || [], atributos: p.atributos || {},
                  da_direito_creche: !!p.da_direito_creche,
                  valor_reembolso_creche: p.valor_reembolso_creche || '',
                })}>Editar</button>
                {p.ativo && (
                  <button className="btn-link" onClick={async () => {
                    if (!window.confirm(`Desativar o posto "${p.nome}"? Ele some das listas de escolha (colaboradores já vinculados seguem intactos).`)) return
                    await api.excluirPosto(p.id); await recarregar()
                  }}>desativar</button>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </main>
  )
}
