import { useMemo, useState } from 'react'
import CheckMestre from '../CheckMestre.jsx'

// Dash-planilha reutilizável para os módulos do RH: ordenação por qualquer
// coluna, filtros por coluna, seleção + ações em massa, colunas configuráveis
// (mostrar/ocultar, salvo no navegador) e exportação CSV do que está à vista.
// PILOTO no Banco de Talentos; a mesma config serve os demais módulos depois.
//
// Config de coluna: { chave, rotulo, valor?(linha)->texto, ordenavel?, filtro?:
//   'texto'|'select', opcoes?:[...], render?(linha)->JSX, sempreVisivel?, quebra? }
// Card de métrica (opcional): { rotulo, valor, cor?, filtro?: {chave, valor} } —
//   clicar num card COM `filtro` ativa aquele filtro (toggle); clicar de novo
//   limpa. Cards sem `filtro` são só indicadores. (feedback 2026-07-22, item 3)
export default function DashPlanilha({
  id,               // identificador do módulo (namespace do localStorage)
  colunas,
  dados,            // array de linhas (objetos)
  cards,            // [{rotulo, valor, cor?, filtro?}]  (opcional)
  chaveLinha = (l) => l.id,
  acoesLinha,       // (linha) => JSX  (opcional)
  linhaExpandida,   // (linha) => JSX | null — detalhe aberto LOGO ABAIXO da linha
  acoesMassa,       // (linhasSelecionadas, limparSelecao) => JSX  (opcional)
  vazio = 'Nenhum registro.',
}) {
  const [sort, setSort] = useState({ chave: null, dir: 'asc' })
  const [filtros, setFiltros] = useState({})
  const [selec, setSelec] = useState(() => new Set())
  // ocultas: usa a escolha salva do RH; se nunca mexeu, o default vem das
  // colunas marcadas `oculta` na config (deixa o dash caber na tela).
  const [ocultas, setOcultas] = useState(() => {
    const salvo = carregarOcultas(id)
    if (salvo) return salvo
    return new Set(colunas.filter((c) => c.oculta).map((c) => c.chave))
  })
  const [configAberta, setConfigAberta] = useState(false)

  const visiveis = colunas.filter((c) => !ocultas.has(c.chave))
  const valorDe = (linha, col) => (col.valor ? col.valor(linha) : linha[col.chave])
  const textoDe = (linha, col) => {
    const v = valorDe(linha, col)
    return Array.isArray(v) ? v.join(', ') : (v == null ? '' : String(v))
  }

  // aplica filtros + ordenação em memória
  const linhas = useMemo(() => {
    let r = [...dados]
    for (const col of colunas) {
      const f = (filtros[col.chave] || '').trim().toLowerCase()
      if (!f) continue
      r = r.filter((l) => textoDe(l, col).toLowerCase().includes(f))
    }
    if (sort.chave) {
      const col = colunas.find((c) => c.chave === sort.chave)
      r.sort((a, b) => {
        const va = textoDe(a, col).toLowerCase(), vb = textoDe(b, col).toLowerCase()
        // números e datas comparam melhor por valor bruto quando possível
        const na = Number(valorDe(a, col)), nb = Number(valorDe(b, col))
        const cmp = (!isNaN(na) && !isNaN(nb)) ? na - nb : va.localeCompare(vb, 'pt')
        return sort.dir === 'asc' ? cmp : -cmp
      })
    }
    return r
  }, [dados, colunas, filtros, sort])

  const ordenar = (chave) =>
    setSort((s) => s.chave === chave
      ? { chave, dir: s.dir === 'asc' ? 'desc' : 'asc' }
      : { chave, dir: 'asc' })

  const ids = linhas.map(chaveLinha)
  const todos = ids.length > 0 && ids.every((i) => selec.has(i))
  const alguns = ids.some((i) => selec.has(i))
  const alternarTodos = () => setSelec(todos ? new Set() : new Set(ids))
  const alternar = (i) => setSelec((s) => { const n = new Set(s); n.has(i) ? n.delete(i) : n.add(i); return n })
  const limparSelecao = () => setSelec(new Set())
  const selecionadas = linhas.filter((l) => selec.has(chaveLinha(l)))

  const toggleColuna = (chave) => setOcultas((o) => {
    const n = new Set(o); n.has(chave) ? n.delete(chave) : n.add(chave)
    salvarOcultas(id, n); return n
  })

  const exportarCsv = () => {
    const cols = visiveis
    const escape = (s) => `"${String(s ?? '').replace(/"/g, '""')}"`
    const linhasCsv = [
      cols.map((c) => escape(c.rotulo)).join(';'),
      ...linhas.map((l) => cols.map((c) => escape(textoDe(l, c))).join(';')),
    ]
    // BOM UTF-8 para o Excel brasileiro abrir com acentos corretos
    const blob = new Blob(['﻿' + linhasCsv.join('\r\n')], { type: 'text/csv;charset=utf-8' })
    const a = document.createElement('a')
    a.href = URL.createObjectURL(blob)
    a.download = `${id}-${new Date().toISOString().slice(0, 10)}.csv`
    a.click(); URL.revokeObjectURL(a.href)
  }

  // clicar num card com `filtro` ativa/desliga (toggle) o filtro daquela coluna
  const cardAtivo = (card) =>
    card.filtro && (filtros[card.filtro.chave] || '') === String(card.filtro.valor)
  const clicarCard = (card) => {
    if (!card.filtro) return
    const { chave, valor } = card.filtro
    setFiltros((f) => ({ ...f, [chave]: cardAtivo(card) ? '' : String(valor) }))
  }

  return (
    <>
      {cards && cards.length > 0 && (
        <div className="rh-metricas dash-cards">
          {cards.map((card, i) => (
            <button key={i} type="button"
                    className={`rh-metrica dash-card${card.filtro ? ' clicavel' : ''}${cardAtivo(card) ? ' ativo' : ''}`}
                    style={card.cor ? { '--card-cor': card.cor } : undefined}
                    onClick={() => clicarCard(card)} disabled={!card.filtro}
                    title={card.filtro ? (cardAtivo(card) ? 'Clique para limpar o filtro' : `Filtrar por ${card.rotulo}`) : undefined}>
              <strong>{card.valor}</strong><span>{card.rotulo}</span>
            </button>
          ))}
        </div>
      )}
      {/* barra de filtros + ações */}
      <div className="rh-card rh-lote dash-filtros">
        {colunas.filter((c) => c.filtro).map((c) => (
          c.filtro === 'select' ? (
            <select key={c.chave} value={filtros[c.chave] || ''}
                    onChange={(e) => setFiltros({ ...filtros, [c.chave]: e.target.value })}>
              <option value="">{c.rotulo}: todos</option>
              {(c.opcoes || []).map((o) => <option key={o.v ?? o} value={o.v ?? o}>{o.r ?? o}</option>)}
            </select>
          ) : (
            <input key={c.chave} placeholder={c.rotulo} value={filtros[c.chave] || ''}
                   onChange={(e) => setFiltros({ ...filtros, [c.chave]: e.target.value })}
                   style={{ maxWidth: 200 }} />
          )
        ))}
        <span className="dash-espaco" />
        <button className="btn-secundario btn-mini" onClick={exportarCsv}>⬇ Exportar CSV</button>
        <button className="btn-secundario btn-mini" onClick={() => setConfigAberta((v) => !v)}>⚙ Colunas</button>
      </div>

      {configAberta && (
        <div className="rh-card dash-colunas">
          <strong>Colunas visíveis</strong>
          <div className="dash-colunas-lista">
            {colunas.map((c) => (
              <label key={c.chave} className={c.sempreVisivel ? 'desabilitada' : ''}>
                <input type="checkbox" checked={!ocultas.has(c.chave)} disabled={c.sempreVisivel}
                       onChange={() => toggleColuna(c.chave)} /> {c.rotulo}
              </label>
            ))}
          </div>
        </div>
      )}

      {alguns && acoesMassa && (
        <div className="rh-card rh-lote" style={{ alignItems: 'center' }}>
          <strong>{selecionadas.length} selecionado(s):</strong>
          {acoesMassa(selecionadas, limparSelecao)}
          <button className="btn-link" onClick={limparSelecao}>limpar seleção</button>
        </div>
      )}

      {linhas.length === 0 ? (
        <p className="explica centro">{vazio}</p>
      ) : (
        <div className="dash-scroll">
        <table className="rh-tabela dash-tabela">
          <thead>
            <tr>
              {acoesMassa && (
                <th className="dash-check">
                  <CheckMestre marcado={todos} parcial={alguns && !todos} onChange={alternarTodos}
                               title="Selecionar todos" />
                </th>
              )}
              {visiveis.map((c) => (
                <th key={c.chave} className={c.ordenavel ? 'dash-ord' : ''}
                    onClick={c.ordenavel ? () => ordenar(c.chave) : undefined}>
                  {c.rotulo}
                  {c.ordenavel && sort.chave === c.chave && (sort.dir === 'asc' ? ' ▲' : ' ▼')}
                </th>
              ))}
              {acoesLinha && <th></th>}
            </tr>
          </thead>
          <tbody>
            {linhas.map((l) => {
              const k = chaveLinha(l)
              // Painel de detalhe abre NA PRÓPRIA LINHA (v1.83). Abrir no topo
              // da página tira a pessoa do contexto: ela clicou na linha 12 e a
              // resposta aparece longe, fora da vista. Edição inline é o padrão
              // da casa — vale também para o detalhe.
              const expandido = linhaExpandida && linhaExpandida(l)
              return [
                <tr key={k} className={expandido ? 'dash-linha-aberta' : undefined}>
                  {acoesMassa && (
                    <td className="dash-check">
                      <input type="checkbox" style={{ width: 'auto', minHeight: 0 }}
                             checked={selec.has(k)} onChange={() => alternar(k)} />
                    </td>
                  )}
                  {visiveis.map((c) => (
                    <td key={c.chave} className={c.quebra ? 'dash-quebra' : undefined}>
                      {c.render ? c.render(l) : (textoDe(l, c) || '—')}</td>
                  ))}
                  {acoesLinha && <td className="acoes-candidato">{acoesLinha(l)}</td>}
                </tr>,
                expandido && (
                  <tr key={`${k}-detalhe`} className="dash-detalhe">
                    <td colSpan={visiveis.length + (acoesMassa ? 1 : 0) + (acoesLinha ? 1 : 0)}>
                      {expandido}
                    </td>
                  </tr>
                ),
              ]
            })}
          </tbody>
        </table>
        </div>
      )}
    </>
  )
}

function carregarOcultas(id) {
  // null = o RH nunca configurou (usa o default da config); Set = escolha salva
  try {
    const bruto = localStorage.getItem(`dash-ocultas:${id}`)
    return bruto == null ? null : new Set(JSON.parse(bruto))
  } catch { return null }
}
function salvarOcultas(id, set) {
  try { localStorage.setItem(`dash-ocultas:${id}`, JSON.stringify([...set])) } catch { /* ignora */ }
}
