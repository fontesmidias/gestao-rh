import { useEffect, useState } from 'react'
import { fmtDataHora } from '../fmt.js'
import { rh as api } from '../api.js'
import { statusInfo } from '../status.js'

// Diagnóstico de UM colaborador: por que o dossiê (não) gera, situação de
// fichas e documentos, e a linha do tempo de tudo que aconteceu. Nasceu do
// incidente da Kátia — investigar sem precisar de banco/SSH.
export function DiagnosticoColaborador({ id }) {
  const [d, setD] = useState(null)
  const [aberto, setAberto] = useState(false)
  useEffect(() => { if (aberto) api.diagnostico(id).then(setD).catch(() => setD(null)) }, [aberto, id])

  if (!aberto) return (
    <div className="rh-card">
      <button className="btn-secundario btn-mini" onClick={() => setAberto(true)}
              title="Investiga por que o dossiê não gera, o que falta e o histórico completo deste colaborador">
        🔍 Diagnóstico deste colaborador</button>
    </div>
  )
  if (!d) return <div className="rh-card"><p>Investigando…</p></div>

  const si = statusInfo(d.candidato.status)
  return (
    <div className="rh-card">
      <h3>🔍 Diagnóstico — {d.candidato.nome}</h3>
      <div className={`diag-veredito ${d.dossie.pode_gerar ? 'ok' : 'bloq'}`}>
        {d.dossie.pode_gerar
          ? '✅ O dossiê PODE ser gerado — nada está bloqueando.'
          : '⛔ O dossiê NÃO gera ainda. Falta:'}
        {!d.dossie.pode_gerar && (
          <ul>{d.dossie.pendencias.map((p, i) => <li key={i}>{p}</li>)}</ul>
        )}
      </div>

      <p className="explica" style={{ marginTop: '.6rem' }}>
        Status: <span className="chip" style={{ '--chip-cor': si.cor }}>{si.icone} {si.label}</span>
        {' · '}Contato: {d.candidato.email || '—'} / {d.candidato.celular_whatsapp || '—'}
        {' · '}Cargo: {d.candidato.cargo_funcao || '—'}
      </p>

      {d.formulario_incompleto.length > 0 && (
        <div className="alerta compacto">📝 Formulário: {d.formulario_incompleto.length} campo(s)
          obrigatório(s) em aberto — {d.formulario_incompleto.join(', ')}</div>
      )}

      <details style={{ marginTop: '.6rem' }}>
        <summary style={{ cursor: 'pointer' }}>Documentos ({d.documentos.length})</summary>
        <table className="rh-tabela" style={{ marginTop: '.4rem' }}>
          <thead><tr><th>Documento</th><th>Situação</th><th>Obrigatório</th></tr></thead>
          <tbody>
            {d.documentos.map((s, i) => (
              <tr key={i}><td>{s.tipo.replace(/_/g, ' ')}</td>
                <td>{s.status}</td><td>{s.obrigatorio ? 'sim' : 'não'}</td></tr>
            ))}
          </tbody>
        </table>
      </details>

      <details style={{ marginTop: '.6rem' }} open>
        <summary style={{ cursor: 'pointer' }}>Linha do tempo ({d.linha_do_tempo.length} eventos)</summary>
        <table className="rh-tabela" style={{ marginTop: '.4rem' }}>
          <thead><tr><th>Quando</th><th>Ação</th><th>Ator</th><th>Detalhe</th></tr></thead>
          <tbody>
            {d.linha_do_tempo.map((e, i) => (
              <tr key={i} className={/falhou|falha/.test(e.acao) ? 'diag-erro-linha' : ''}>
                <td style={{ whiteSpace: 'nowrap' }}>{fmtDataHora(e.quando)}</td>
                <td>{e.acao}</td>
                <td>{e.ator}{e.ator_detalhe ? ` (${e.ator_detalhe})` : ''}</td>
                <td><small>{e.detalhe ? JSON.stringify(e.detalhe) : ''}</small></td>
              </tr>
            ))}
          </tbody>
        </table>
      </details>
    </div>
  )
}

// Erros recentes do sistema (aba de Diagnóstico global em Configurações).
export function ErrosRecentes() {
  const [erros, setErros] = useState(null)
  const [aberto, setAberto] = useState(false)
  return (
    <div className="rh-card">
      <h3>🩺 Diagnóstico do sistema — erros recentes</h3>
      <p className="explica">Falhas registradas pelo sistema (dossiê que não montou, e-mail que
        não saiu…), com o colaborador afetado. Serve para investigar sem precisar acessar
        servidor ou banco.</p>
      {!aberto ? (
        <button className="btn-secundario" onClick={async () => {
          setErros(await api.errosRecentes()); setAberto(true)
        }}>Ver erros recentes</button>
      ) : !erros ? <p>Carregando…</p> : erros.length === 0 ? (
        <p className="explica">Nenhum erro registrado. 🎉</p>
      ) : (
        <table className="rh-tabela">
          <thead><tr><th>Quando</th><th>Erro</th><th>Colaborador</th><th>Detalhe</th></tr></thead>
          <tbody>
            {erros.map((e, i) => (
              <tr key={i}>
                <td style={{ whiteSpace: 'nowrap' }}>{fmtDataHora(e.quando)}</td>
                <td>{e.acao}</td>
                <td>{e.candidato_nome || '—'}</td>
                <td><small>{e.detalhe ? JSON.stringify(e.detalhe) : ''}</small></td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  )
}
