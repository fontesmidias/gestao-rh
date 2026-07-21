import { useRef, useState } from 'react'
import { rh as api } from '../api.js'
import { comAmpulheta } from '../Carregando.jsx'

// Importação ASSISTIDA da planilha de Incidência de Benefícios: normaliza os
// postos no padrão CLIENTE - Nº CONTRATO - OBJETO e define a elegibilidade ao
// Reembolso-Creche por contrato. O sistema PROPÕE a equivalência com o posto do
// Tirvu; o RH CONFIRMA cada linha (nunca merge cego — regra do projeto).
export default function IncidenciaBeneficios({ aoVoltar, aoAplicar }) {
  const [preview, setPreview] = useState(null) // { total, com_creche, compostos, linhas }
  const [decisoes, setDecisoes] = useState({}) // idx -> { posto_id, ... }
  const [erro, setErro] = useState(null)
  const [msg, setMsg] = useState(null)
  const input = useRef(null)

  const subir = async (arquivo) => {
    if (!arquivo) return
    setErro(null); setMsg(null)
    try {
      const r = await comAmpulheta('Lendo a planilha de incidência…', () => api.incidenciaPreview(arquivo))
      setPreview(r)
      // decisão inicial por linha: melhor sugestão (se score alto) senão "ignorar"
      const iniciais = {}
      r.linhas.forEach((l) => {
        const melhor = l.sugestoes?.[0]
        iniciais[l.idx] = {
          posto_id: melhor && melhor.score >= 0.6 ? melhor.posto_id : 'ignorar',
          nome_normalizado: l.nome_normalizado,
          da_direito_creche: l.da_direito_creche,
          valor_reembolso: l.composto ? '' : (l.creche_valor || ''),
          contrato_ref: l.contrato || '',
        }
      })
      setDecisoes(iniciais)
    } catch (e) {
      setErro(e.detail === 'arquivo_invalido' ? 'Arquivo inválido. Envie o .xlsx da planilha de incidência.'
        : e.detail === 'sem_linhas_reconhecidas' ? 'Não reconheci as abas PÚBLICO/PRIVADO. Confira a planilha.'
        : `Falha ao ler a planilha (${e.detail || e.message}).`)
    } finally { if (input.current) input.current.value = '' }
  }

  const setDec = (idx, campo, valor) =>
    setDecisoes((d) => ({ ...d, [idx]: { ...d[idx], [campo]: valor } }))

  const aplicar = async () => {
    setErro(null); setMsg(null)
    const lista = Object.values(decisoes)
    try {
      const r = await comAmpulheta('Aplicando as equivalências confirmadas…',
                                   () => api.incidenciaConfirmar(lista))
      setMsg(`Pronto: ${r.criados} novo(s), ${r.atualizados} atualizado(s), ${r.ignorados} ignorado(s).`)
      setPreview(null); setDecisoes({})
      aoAplicar?.()
    } catch (e) { setErro(`Falha ao aplicar (${e.detail || e.message}).`) }
  }

  return (
    <main className="rh-painel">
      <header className="rh-topo">
        <button className="btn-link" onClick={aoVoltar}>← Voltar aos postos</button>
        <h1>📋 Incidência de Benefícios</h1><div />
      </header>
      <p className="explica">Importe a <strong>Planilha de Incidência de Benefícios</strong> (.xlsx, abas
        PÚBLICO e PRIVADO). O sistema normaliza cada posto no padrão <strong>CLIENTE - Nº CONTRATO -
        OBJETO</strong> e define quem <strong>faz jus ao Reembolso-Creche</strong> pelo contrato. Para cada
        linha, confirme a equivalência com o posto do Tirvu — nada é gravado sem sua confirmação.</p>

      {!preview && (
        <div className="rh-card rh-lote">
          <input ref={input} type="file" accept=".xlsx" hidden
                 onChange={(e) => subir(e.target.files?.[0])} />
          <button className="btn-principal btn-mini" onClick={() => input.current?.click()}>
            ⬆ Enviar planilha de incidência</button>
        </div>
      )}
      {msg && <div className="sucesso">{msg}</div>}
      {erro && <div className="alerta">{erro}</div>}

      {preview && (
        <>
          <div className="rh-metricas">
            <div className="rh-metrica"><strong>{preview.total}</strong><span>linhas na planilha</span></div>
            <div className="rh-metrica"><strong>{preview.com_creche}</strong><span>dão direito a creche</span></div>
            <div className="rh-metrica"><strong>{preview.compostos}</strong><span>valores compostos (revisar)</span></div>
          </div>
          <div className="rh-card rh-lote">
            <button className="btn-principal btn-mini" onClick={aplicar}>✅ Aplicar equivalências confirmadas</button>
            <button className="btn-secundario btn-mini" onClick={() => { setPreview(null); setDecisoes({}) }}>
              Cancelar</button>
            <span className="explica" style={{ margin: 0 }}>Revise cada linha antes de aplicar.</span>
          </div>

          <table className="rh-tabela">
            <thead><tr><th>Posto normalizado</th><th>Equivalência no Tirvu</th>
              <th>Creche</th><th>Valor</th></tr></thead>
            <tbody>
              {preview.linhas.map((l) => {
                const d = decisoes[l.idx] || {}
                return (
                  <tr key={l.idx}>
                    <td><strong>{l.nome_normalizado}</strong>
                      {l.composto && <span title="Valor composto (dois sindicatos) — confira o valor"> ⚠️</span>}
                      <br /><small>{l.aba}</small></td>
                    <td>
                      <select value={d.posto_id || 'ignorar'}
                              onChange={(e) => setDec(l.idx, 'posto_id', e.target.value)}>
                        {(l.sugestoes || []).map((s) => (
                          <option key={s.posto_id} value={s.posto_id}>
                            {s.posto_nome} ({Math.round(s.score * 100)}%)</option>
                        ))}
                        <option value="novo">➕ Criar novo posto</option>
                        <option value="ignorar">— Ignorar esta linha</option>
                      </select>
                    </td>
                    <td>
                      <input type="checkbox" checked={!!d.da_direito_creche}
                             onChange={(e) => setDec(l.idx, 'da_direito_creche', e.target.checked)} />
                    </td>
                    <td>
                      {d.da_direito_creche
                        ? <input value={d.valor_reembolso || ''} placeholder="R$ 0,00" style={{ width: 120 }}
                                 onChange={(e) => setDec(l.idx, 'valor_reembolso', e.target.value)} />
                        : <span className="explica" style={{ margin: 0 }}>—</span>}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </>
      )}
    </main>
  )
}
