import { useEffect, useState } from 'react'
import { fmtData } from '../fmt.js'
import { rh as api } from '../api.js'

// Multi-signatário: o RH monta um roteiro de assinatura (quem assina, em que
// papel e ordem) para um documento de modelo, dispara, e acompanha a timeline.
// A etapa do candidato entra pelo link mágico dele; usuários do RH assinam na
// fila; externos por link + código. Autorizações da equipe entram sozinhas.
export default function RoteiroAssinatura({ id }) {
  const [roteiros, setRoteiros] = useState(null)
  const [modelos, setModelos] = useState([])
  const [papeis, setPapeis] = useState([])
  const [usuarios, setUsuarios] = useState([])
  const [montando, setMontando] = useState(null)
  const [msg, setMsg] = useState(null)

  const recarregar = () => api.roteirosDoCandidato(id).then((r) => setRoteiros(r.solicitacoes))
  useEffect(() => {
    recarregar().catch(() => setRoteiros([]))
    api.modelos().then((r) => setModelos(r.modelos)).catch(() => {})
    api.papeis().then((r) => setPapeis(r.papeis)).catch(() => {})
    api.usuarios().then(setUsuarios).catch(() => {})
  }, [id])
  if (!roteiros) return null

  return (
    <div className="rh-card">
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '.5rem' }}>
        <strong>✍️ Roteiros de assinatura (vários signatários)</strong>
        {!montando && (
          <button className="btn-secundario btn-mini" onClick={() =>
            setMontando({ modelo_id: '', etapas: [{ papel: 'Contratado(a)', ordem: 1, tipo: 'candidato' }] })}>
            + Novo roteiro</button>
        )}
      </div>
      <p className="explica">Colete a assinatura de várias pessoas em ordem — o colaborador, alguém
        do RH (assina logado) e/ou um terceiro por e-mail. As autorizações da equipe entram
        automaticamente. Só quando todos assinam o documento fica concluído.</p>
      {msg && <div className={msg.tipo === 'erro' ? 'alerta' : 'sucesso'}>{msg.texto}</div>}

      {montando && (
        <MontarRoteiro montando={montando} setMontando={setMontando} modelos={modelos}
                       papeis={papeis} usuarios={usuarios} id={id} setMsg={setMsg}
                       recarregar={recarregar} />
      )}

      {roteiros.length === 0 && !montando
        ? <p className="explica">Nenhum roteiro ainda.</p>
        : roteiros.map((s) => (
          <div key={s.id} className="disc-bloco">
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '.4rem' }}>
              <strong>{s.titulo}</strong>
              <span className="chip" style={{ '--chip-cor': CORES_STATUS[s.status] || '#889' }}>
                {ROTULO_STATUS[s.status] || s.status}</span>
            </div>
            <table className="rh-tabela" style={{ marginTop: '.4rem' }}>
              <thead><tr><th>Ordem</th><th>Papel</th><th>Quem</th><th>Situação</th></tr></thead>
              <tbody>
                {s.etapas.map((e) => (
                  <tr key={e.id}>
                    <td>{e.ordem}</td><td>{e.papel}</td>
                    <td>{e.quem}</td>
                    <td>{e.assinado_em ? `✅ ${fmtData(e.assinado_em)}`
                      : e.recusada_em ? `❌ recusou (${e.recusada_motivo || ''})`
                      : '⏳ aguardando'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            <div className="rh-lote" style={{ marginTop: '.4rem' }}>
              {s.status === 'rascunho' && (
                <button className="btn-principal btn-mini" onClick={async () => {
                  setMsg(null)
                  try { await api.dispararRoteiro(s.id); await recarregar()
                    setMsg({ tipo: 'ok', texto: 'Roteiro disparado — os signatários serão avisados.' }) }
                  catch (e) { setMsg({ tipo: 'erro', texto: `Não foi possível disparar (${e.detail || e.message}).` }) }
                }}>▶ Disparar</button>
              )}
              {['rascunho', 'aguardando', 'pendente_rh'].includes(s.status) && (
                <button className="btn-link" onClick={async () => {
                  if (!window.confirm('Cancelar este roteiro?')) return
                  await api.cancelarRoteiro(s.id, 'cancelado pelo RH'); await recarregar()
                }}>cancelar</button>
              )}
            </div>
          </div>
        ))}
    </div>
  )
}

const CORES_STATUS = { rascunho: '#f0ad4e', aguardando: '#3b7dd8', concluida: '#0fb257',
                       pendente_rh: '#d9534f', cancelada: '#889', expirada: '#889' }
const ROTULO_STATUS = { rascunho: 'Rascunho', aguardando: 'Assinando', concluida: 'Concluído ✓',
                        pendente_rh: 'Ação do RH', cancelada: 'Cancelado', expirada: 'Expirado' }

function MontarRoteiro({ montando, setMontando, modelos, papeis, usuarios, id, setMsg, recarregar }) {
  const [salvando, setSalvando] = useState(false)
  // Ao escolher um modelo com roteiro-padrão, pré-carrega as etapas dele (o RH
  // completa as pessoas de RH/externo). Só faz isso uma vez por modelo.
  const escolherModelo = async (modelo_id) => {
    setMontando({ ...montando, modelo_id })
    if (!modelo_id) return
    try {
      const r = await api.roteiroPadrao(modelo_id)
      if (r.etapas && r.etapas.length) {
        setMontando({ modelo_id, etapas: r.etapas.map((e) => ({
          papel: e.papel, ordem: e.ordem, tipo: e.tipo_sugerido })) })
      }
    } catch { /* modelo sem padrão: mantém o que está */ }
  }
  const setEtapa = (i, campo, v) => setMontando({
    ...montando, etapas: montando.etapas.map((e, j) => j === i ? { ...e, [campo]: v } : e) })
  const addEtapa = () => setMontando({ ...montando,
    etapas: [...montando.etapas, { papel: '', ordem: montando.etapas.length + 1, tipo: 'usuario_rh' }] })

  return (
    <div className="form-inline-conteudo" style={{ border: '1px solid var(--borda)', borderRadius: 10, padding: '.7rem', margin: '.5rem 0' }}>
      <label className="campo"><span className="rotulo">Documento (modelo)</span>
        <select value={montando.modelo_id}
                onChange={(e) => escolherModelo(e.target.value)}>
          <option value="">— escolha o modelo —</option>
          {modelos.map((m) => <option key={m.id} value={m.id}>{m.titulo}</option>)}
        </select></label>
      <p className="explica" style={{ margin: '.4rem 0 0' }}>Signatários (na ordem em que assinam):</p>
      {montando.etapas.map((e, i) => (
        <div key={i} className="rh-lote" style={{ padding: '.3rem 0', borderBottom: '1px solid var(--borda)' }}>
          <input style={{ maxWidth: 60 }} inputMode="numeric" value={e.ordem}
                 title="Ordem" onChange={(ev) => setEtapa(i, 'ordem', parseInt(ev.target.value, 10) || 1)} />
          <select value={e.papel} onChange={(ev) => setEtapa(i, 'papel', ev.target.value)}>
            <option value="">— papel —</option>
            {papeis.map((p) => <option key={p.id} value={p.nome}>{p.nome}</option>)}
          </select>
          <select value={e.tipo} onChange={(ev) => setEtapa(i, 'tipo', ev.target.value)}>
            <option value="candidato">O colaborador</option>
            <option value="usuario_rh">Alguém do RH</option>
            <option value="externo">Externo (por e-mail)</option>
          </select>
          {e.tipo === 'usuario_rh' && (
            <select value={e.usuario_rh_id || ''} onChange={(ev) => setEtapa(i, 'usuario_rh_id', ev.target.value)}>
              <option value="">— quem do RH —</option>
              {usuarios.filter((u) => u.ativo).map((u) => <option key={u.id} value={u.id}>{u.nome}</option>)}
            </select>
          )}
          {e.tipo === 'externo' && (<>
            <input placeholder="Nome" value={e.externo_nome || ''} style={{ maxWidth: 140 }}
                   onChange={(ev) => setEtapa(i, 'externo_nome', ev.target.value)} />
            <input placeholder="E-mail" value={e.externo_email || ''} style={{ maxWidth: 160 }}
                   onChange={(ev) => setEtapa(i, 'externo_email', ev.target.value)} />
          </>)}
          {montando.etapas.length > 1 && (
            <button className="btn-link" title="Remover"
                    onClick={() => setMontando({ ...montando, etapas: montando.etapas.filter((_, j) => j !== i) })}>✕</button>
          )}
        </div>
      ))}
      <button className="btn-secundario btn-mini" style={{ marginTop: '.4rem' }} onClick={addEtapa}>+ Signatário</button>
      <div className="navegacao">
        <button className="btn-secundario" onClick={() => setMontando(null)}>Cancelar</button>
        <button className="btn-principal" disabled={salvando || !montando.modelo_id} onClick={async () => {
          setSalvando(true); setMsg(null)
          try {
            await api.montarRoteiro(id, { modelo_id: montando.modelo_id, etapas: montando.etapas })
            setMontando(null); await recarregar()
            setMsg({ tipo: 'ok', texto: 'Roteiro criado. Revise e clique em ▶ Disparar.' })
          } catch (e) {
            setMsg({ tipo: 'erro', texto: `Não foi possível criar (${
              Array.isArray(e.detail) ? 'confira os campos' : e.detail || e.message}).` })
          } finally { setSalvando(false) }
        }}>Criar roteiro</button>
      </div>
    </div>
  )
}
