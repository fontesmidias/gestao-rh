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
      <p className="explica">{dados.email} · {dados.celular_whatsapp} · status:
        <strong> {dados.status}</strong>
        {enviados.length > 0 && <> · <strong>{enviados.length} documento(s) aguardando revisão</strong></>}
      </p>
      {msg && <div className={msg.tipo === 'erro' ? 'alerta' : 'sucesso'}>{msg.texto}</div>}

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
                      {s.paginas ? ` · ${s.paginas} pág.` : ''}</div>
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
