import { useEffect, useState } from 'react'
import { rh as api } from '../api.js'
import { fmtDataHora } from '../fmt.js'

// Testes JÁ RESPONDIDOS aproveitados para o candidato (v2.21, pedido do Bruno
// em 2026-07-29). A pessoa respondeu um DISC/situacional ou uma prova ANTES de
// virar candidata — refazer na admissão é desperdício para ela e ruído para o
// RH.
//
// **Só o RH vê**: não aparece no wizard do candidato nem no dossiê, que
// circula. Resultado de teste é dado sensível de seleção.
//
// A lista de escolha mostra CONTEXTO (nome, data, qual teste, por qual link)
// porque o link avulso de testagem é anônimo — guarda só o nome de quem
// respondeu. Escolher às cegas por nome, com homônimo, seria decidir
// contratação com o resultado de outra pessoa.

const TIPO_ROT = { disc: 'DISC', situacional: 'Situacional' }

export default function TestesVinculados({ candidatoId, nome }) {
  const [vinculados, setVinculados] = useState(null)
  const [escolhendo, setEscolhendo] = useState(false)
  const [disponiveis, setDisponiveis] = useState(null)
  const [busca, setBusca] = useState(nome || '')
  const [msg, setMsg] = useState(null)
  const [ocupado, setOcupado] = useState(false)

  const recarregar = () => api.testesVinculados(candidatoId)
    .then(setVinculados).catch(() => setVinculados([]))
  useEffect(() => { recarregar() }, [candidatoId])

  const procurar = async (termo) => {
    setDisponiveis(null)
    try { setDisponiveis(await api.testesVinculaveis(termo)) }
    catch { setDisponiveis([]) }
  }

  const abrir = () => { setEscolhendo(true); setMsg(null); procurar(busca) }

  const vincular = async (item) => {
    setMsg(null); setOcupado(true)
    try {
      await api.vincularTeste(candidatoId, {
        origem: item.origem, referencia_id: item.referencia_id,
      })
      setMsg({ tipo: 'ok', texto: `Teste de ${item.nome_respondente} aproveitado.` })
      setEscolhendo(false)
      await recarregar()
    } catch (e) {
      setMsg({ tipo: 'erro', texto: `Não foi possível vincular (${e.detail || e.message}).` })
    } finally { setOcupado(false) }
  }

  const desvincular = async (v) => {
    if (!window.confirm('Remover este teste do candidato? O resultado original '
      + 'continua existindo — só deixa de estar ligado a esta pessoa.')) return
    setMsg(null); setOcupado(true)
    try {
      await api.desvincularTeste(candidatoId, v.id)
      await recarregar()
    } catch (e) {
      setMsg({ tipo: 'erro', texto: `Não foi possível remover (${e.detail || e.message}).` })
    } finally { setOcupado(false) }
  }

  return (
    <div className="rh-card">
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                    flexWrap: 'wrap', gap: '.5rem' }}>
        <strong>🧪 Testes já respondidos</strong>
        <button className="btn-link" onClick={abrir}>+ aproveitar um teste</button>
      </div>
      <p className="explica">Resultados que a pessoa respondeu antes da admissão
        (link de teste ou prova). <strong>Só o RH vê</strong> — não aparece para o
        candidato nem no dossiê.</p>

      {msg && <div className={msg.tipo === 'erro' ? 'alerta' : 'aviso-inline'}>{msg.texto}</div>}

      {vinculados === null ? <p className="explica">Carregando…</p>
        : vinculados.length === 0 ? <p className="explica">Nenhum teste aproveitado.</p>
          : vinculados.map((v) => (
            <div key={v.id} className="email-item" style={{ padding: '.6rem' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between',
                            gap: '.5rem', flexWrap: 'wrap' }}>
                <span>
                  <strong>{v.prova || (v.testes || []).map((t) => TIPO_ROT[t.tipo] || t.tipo).join(' + ') || 'Teste'}</strong>
                  {v.automatico
                    ? <span className="chip-mini" title="Veio do Banco de Talentos: o sistema sabe de quem é">do talento</span>
                    : <span className="chip-mini alerta-mini" title={`Vinculado por ${v.vinculado_por || 'alguém do RH'}`}>escolhido pelo RH</span>}
                  <br />
                  <small className="explica">
                    respondido por <strong>{v.nome_respondente || '—'}</strong>
                    {v.link_nome ? ` · link "${v.link_nome}"` : ''}
                    {v.nota_final != null ? ` · nota ${v.nota_final}` : ''}
                  </small>
                  {(v.testes || []).map((t) => (
                    <div key={t.tipo}><small className="explica">
                      {TIPO_ROT[t.tipo] || t.tipo}: {t.resultado?.perfil
                        ? `perfil ${t.resultado.perfil}`
                        : t.status}
                      {t.concluido_em ? ` — ${fmtDataHora(t.concluido_em)}` : ''}
                    </small></div>
                  ))}
                  {v.indisponivel && (
                    <small className="explica">⚠️ o resultado original não está mais disponível</small>)}
                </span>
                <button className="btn-link" disabled={ocupado}
                        onClick={() => desvincular(v)}>remover</button>
              </div>
            </div>
          ))}

      {escolhendo && (
        <div className="email-editor" style={{ marginTop: '.6rem' }}>
          <p className="explica">Confira <strong>nome, data e origem</strong> antes de
            escolher — o link de teste avulso não identifica quem respondeu, então
            duas pessoas de mesmo nome apareceriam iguais.</p>
          <div className="rh-lote">
            <input placeholder="🔎 Buscar pelo nome de quem respondeu…" value={busca}
                   style={{ maxWidth: 280 }}
                   onChange={(e) => { setBusca(e.target.value); procurar(e.target.value) }} />
            <button className="btn-link" onClick={() => setEscolhendo(false)}>cancelar</button>
          </div>
          {disponiveis === null ? <p className="explica">Buscando…</p>
            : disponiveis.length === 0
              ? <p className="explica">Nenhum teste concluído disponível para aproveitar.</p>
              : disponiveis.map((d) => (
                <div key={`${d.origem}-${d.referencia_id}`} className="email-item"
                     style={{ padding: '.6rem' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between',
                                gap: '.5rem', flexWrap: 'wrap' }}>
                    <span>
                      <strong>{d.nome_respondente}</strong>
                      {d.identificado && (
                        <span className="chip-mini" title="Veio do Banco de Talentos">
                          identificado</span>)}
                      <br />
                      <small className="explica">
                        {d.o_que} · {fmtDataHora(d.quando)}
                        {d.link_nome ? ` · link "${d.link_nome}"` : ''}
                      </small>
                    </span>
                    <button className="btn-principal btn-mini" disabled={ocupado}
                            onClick={() => vincular(d)}>aproveitar</button>
                  </div>
                </div>
              ))}
        </div>
      )}
    </div>
  )
}
