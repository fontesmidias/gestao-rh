import { Fragment, useEffect, useState } from 'react'
import { fmtData } from '../fmt.js'
import { rh as api } from '../api.js'

const STATUS = {
  novo: ['Novo', '#5bc0de'],
  em_analise: ['Em análise', '#e9a63a'],
  convertido: ['Convertido ✓', '#4f9d3a'],
  arquivado: ['Arquivado', '#999'],
}
const PROXIMO_STATUS = [
  ['novo', 'Marcar como novo'],
  ['em_analise', 'Marcar em análise'],
  ['arquivado', 'Arquivar'],
]

// Dashboard do Banco de Talentos: lista, filtros e conversão em candidato.
export default function TalentosRH({ aoAbrir }) {
  const [talentos, setTalentos] = useState(null)
  const [filtros, setFiltros] = useState({ status: '', cargo: '', busca: '' })
  const [aberto, setAberto] = useState(null) // talento expandido
  const [msg, setMsg] = useState(null)

  const recarregar = () => api.listarTalentos(filtros).then(setTalentos).catch(() => setTalentos([]))
  useEffect(() => { recarregar() }, [filtros.status]) // filtros de texto: botão aplicar

  const converter = async (t) => {
    if (!window.confirm(`Converter ${t.nome} em candidato e iniciar a admissão?`)) return
    setMsg(null)
    try {
      const r = await api.converterTalento(t.id)
      setMsg({ tipo: 'ok', texto: r.email_enviado
        ? `${t.nome} virou candidato e recebeu o convite por e-mail. Abrindo a ficha…`
        : `${t.nome} virou candidato. ${t.email ? 'O e-mail não saiu — ' : 'Sem e-mail — '}copie o link na tela do candidato e mande pelo WhatsApp. Abrindo a ficha…` })
      await recarregar()
      if (aoAbrir) setTimeout(() => aoAbrir(r.candidato_id), 600)
    } catch (e) {
      setMsg({ tipo: 'erro', texto: e.detail === 'talento_ja_convertido'
        ? 'Este talento já foi convertido.'
        : `Não foi possível converter (${e.detail || e.message}).` })
    }
  }

  const mudarStatus = async (t, status) => {
    try { await api.statusTalento(t.id, status); await recarregar() }
    catch (e) { setMsg({ tipo: 'erro', texto: `Não foi possível atualizar (${e.detail || e.message}).` }) }
  }

  return (
    <main className="rh-painel">
      <header className="rh-topo"><h1>🎯 Banco de Talentos</h1><div /></header>
      <p className="explica">Interessados que se cadastraram no formulário público
        (<code>/banco-de-talentos</code>). Filtre, analise e, ao decidir contratar, converta em
        candidato — os dados já preenchidos migram e o link de admissão é disparado.</p>

      <div className="rh-card rh-lote">
        <select value={filtros.status} onChange={(e) => setFiltros({ ...filtros, status: e.target.value })}>
          <option value="">Todos os status</option>
          <option value="novo">Novos</option>
          <option value="em_analise">Em análise</option>
          <option value="convertido">Convertidos</option>
          <option value="arquivado">Arquivados</option>
        </select>
        <input placeholder="Cargo de interesse" value={filtros.cargo}
               onChange={(e) => setFiltros({ ...filtros, cargo: e.target.value })}
               style={{ maxWidth: 200 }} />
        <input placeholder="Buscar (nome, cidade, texto…)" value={filtros.busca}
               onChange={(e) => setFiltros({ ...filtros, busca: e.target.value })}
               onKeyDown={(e) => e.key === 'Enter' && recarregar()} style={{ maxWidth: 240 }} />
        <button className="btn-secundario btn-mini" onClick={recarregar}>Aplicar filtros</button>
      </div>

      {msg && <div className={msg.tipo === 'erro' ? 'alerta' : 'sucesso'}>{msg.texto}</div>}

      {!talentos ? <p>Carregando…</p> : talentos.length === 0 ? (
        <p className="explica centro">Nenhum talento com esses filtros.</p>
      ) : (
        <table className="rh-tabela">
          <thead><tr><th>Nome</th><th>Cargo</th><th>Cidade</th><th>Status</th><th>Cadastro</th><th></th></tr></thead>
          <tbody>
            {talentos.map((t) => {
              const [rotulo, cor] = STATUS[t.status] || [t.status, '#888']
              const exp = aberto === t.id
              return (
                <Fragment key={t.id}>
                  <tr>
                    <td><strong>{t.nome}</strong><br /><small>{t.email || t.telefone || '—'}</small></td>
                    <td>{t.cargo_interesse || '—'}</td>
                    <td>{t.cidade || '—'}</td>
                    <td><span className="chip" style={{ '--chip-cor': cor }}>{rotulo}</span></td>
                    <td>{fmtData(t.criado_em)}</td>
                    <td className="acoes-candidato">
                      <button className="btn-secundario btn-mini"
                              onClick={() => setAberto(exp ? null : t.id)}>{exp ? 'Fechar' : 'Ver'}</button>
                      {t.status !== 'convertido' && (
                        <button className="btn-principal btn-mini" onClick={() => converter(t)}>
                          → Converter em candidato</button>
                      )}
                    </td>
                  </tr>
                  {exp && (
                    <tr>
                      <td colSpan={6}>
                        <div className="talento-detalhe">
                          <p><strong>Contato:</strong> {t.email || '—'} · {t.telefone || '—'}</p>
                          <p><strong>Escolaridade:</strong> {t.escolaridade || '—'} ·{' '}
                            <strong>Como conheceu:</strong> {t.origem || '—'}</p>
                          {t.resumo && <p><strong>Experiência:</strong> {t.resumo}</p>}
                          {t.status !== 'convertido' && (
                            <div className="navegacao" style={{ justifyContent: 'flex-start', gap: '.4rem' }}>
                              {PROXIMO_STATUS.filter(([s]) => s !== t.status).map(([s, txt]) => (
                                <button key={s} className="btn-secundario btn-mini"
                                        onClick={() => mudarStatus(t, s)}>{txt}</button>
                              ))}
                            </div>
                          )}
                        </div>
                      </td>
                    </tr>
                  )}
                </Fragment>
              )
            })}
          </tbody>
        </table>
      )}
    </main>
  )
}
