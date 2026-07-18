import { useEffect, useState } from 'react'
import { rh as api } from '../api.js'
import { comAmpulheta } from '../Carregando.jsx'

const fmtCpf = (c) => {
  const d = (c || '').replace(/\D/g, '')
  return d.length === 11 ? `${d.slice(0, 3)}.${d.slice(3, 6)}.${d.slice(6, 9)}-${d.slice(9)}` : (c || '—')
}

// Reembolso-Creche (IN SEGES/MGI 147/2026). 1ª onda: levantamento de
// elegibilidade por posto — a relação que os órgãos cobram para instruir a
// repactuação. A camada de dados das crianças (idade, documentos) chega quando
// o autocadastro público entrar no ar.
export default function Creche({ aoVoltar }) {
  const [resumo, setResumo] = useState(null)
  const [erro, setErro] = useState(null)

  useEffect(() => {
    api.crecheResumo().then(setResumo)
      .catch(() => setErro('Não foi possível carregar o resumo.'))
  }, [])

  const exportar = async () => {
    setErro(null)
    try {
      const blob = await comAmpulheta('Montando a relação de elegíveis…',
                                      () => api.exportarCreche())
      const a = document.createElement('a')
      a.href = URL.createObjectURL(blob)
      a.download = `reembolso-creche-elegiveis-${new Date().toISOString().slice(0, 10)}.xlsx`
      a.click()
      URL.revokeObjectURL(a.href)
    } catch {
      setErro('A exportação falhou. Tente novamente — se persistir, veja a auditoria.')
    }
  }

  return (
    <main className="rh-painel">
      <header className="rh-topo">
        <button className="btn-link" onClick={aoVoltar}>← Voltar</button>
        <h1>🍼 Reembolso-Creche</h1>
        <button className="btn-principal btn-mini"
                disabled={!resumo?.colaboradores_em_postos_elegiveis}
                onClick={exportar}>⬇ Exportar relação (Excel)</button>
      </header>
      <p className="explica">Levantamento de elegibilidade da <strong>IN SEGES/MGI nº 147/2026</strong>.
        O direito ao benefício é <strong>por posto/contrato</strong> — marque quais postos dão direito na
        aba <strong>Postos</strong> (🍼). Esta relação é a que os órgãos cobram para instruir a
        repactuação (ex.: Ofício CNMP nº 5/2026, ANATEL nº 45/2026). Os dados das crianças e a idade
        (até 5 anos e 11 meses) serão coletados no autocadastro dos colaboradores, na próxima etapa.</p>

      {erro && <div className="alerta">{erro}</div>}
      {!resumo ? <p>Carregando…</p> : (
        <>
          <div className="rh-metricas">
            <div className="rh-metrica">
              <strong>{resumo.postos_elegiveis}</strong>
              <span>postos elegíveis</span>
            </div>
            <div className="rh-metrica">
              <strong>{resumo.colaboradores_em_postos_elegiveis}</strong>
              <span>colaboradores ativos nesses postos</span>
            </div>
          </div>

          {resumo.postos_elegiveis === 0 ? (
            <div className="rh-card">
              <p className="explica" style={{ margin: 0 }}>Nenhum posto marcado como elegível ainda.
                Vá em <strong>Postos</strong>, edite o tomador que oferece o benefício e marque
                <strong> "Este posto dá direito ao reembolso-creche"</strong>, informando o valor
                do contrato. Ele aparecerá aqui automaticamente.</p>
            </div>
          ) : (
            <table className="rh-tabela">
              <thead>
                <tr><th>Posto (contrato)</th><th>Sigla</th><th>Nº do contrato</th>
                    <th>Valor do reembolso</th><th>Colaboradores ativos</th></tr>
              </thead>
              <tbody>
                {resumo.por_posto.map((p) => (
                  <tr key={p.posto_id}>
                    <td><strong>{p.posto}</strong></td>
                    <td>{p.sigla || '—'}</td>
                    <td>{p.contrato_ref || '—'}</td>
                    <td>{p.valor_reembolso || <em style={{ opacity: .6 }}>a repactuar</em>}</td>
                    <td>{p.colaboradores_ativos}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </>
      )}
    </main>
  )
}
