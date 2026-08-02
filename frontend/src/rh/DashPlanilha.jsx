import { useEffect, useMemo, useRef, useState } from 'react'
import CheckMestre from '../CheckMestre.jsx'
import SelectBusca from '../SelectBusca.jsx'

// Dash-planilha reutilizável para os módulos do RH: ordenação por qualquer
// coluna, filtros por coluna, seleção + ações em massa, colunas configuráveis
// (mostrar/ocultar, salvo no navegador) e exportação CSV do que está à vista.
// PILOTO no Banco de Talentos; a mesma config serve os demais módulos depois.
//
// Config de coluna: { chave, rotulo, valor?(linha)->texto, ordenavel?, filtro?:
//   'texto'|'select'|'lista', opcoes?:[...], render?(linha)->JSX, sempreVisivel?, quebra? }
//
// `filtro: 'lista'` monta as opções a partir dos PRÓPRIOS dados e usa o
// SelectBusca — é o certo para posto, cargo, tags, cidade: valores que mudam e
// que ninguém deveria precisar digitar exatamente igual. Use `'texto'` só onde
// a busca é por trecho livre (nome, matrícula) e `'select'` onde a lista é
// fixa e conhecida (Sim/Não, status).
// Card de métrica (opcional): { rotulo, valor, cor?, filtro?: {chave, valor} } —
//   clicar num card COM `filtro` ativa aquele filtro (toggle); clicar de novo
//   limpa. Cards sem `filtro` são só indicadores. (feedback 2026-07-22, item 3)
export default function DashPlanilha({
  id,               // identificador do módulo (namespace do localStorage)
  colunas,
  dados,            // array de linhas (objetos)
  cards,            // [{rotulo, valor, cor?, filtro?}]  (opcional)
  // Filtros que o PAI controla (tipicamente server-side, que recarregam a
  // API): [{chave, rotulo, valor, opcoes, aoMudar, vazioRotulo?}]. Aparecem na
  // MESMA grade dos filtros de coluna, para a tela ter um bloco de filtros só.
  // Sem `opcoes` vira campo de TEXTO (busca server-side por nome/CPF, v2.51) —
  // com `debounce` em ms, para não disparar uma consulta por tecla.
  filtrosExtras,
  // Ações extras na barra de filtros (ex.: "Exportar planilha" do servidor,
  // que é diferente do "Exportar CSV" do que está na tela).
  acoesFiltro,
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

  // Opções derivadas dos PRÓPRIOS dados, para `filtro: 'lista'` (v2.52).
  // Posto, cargo, tags e cidade eram campo de texto livre — o RH tinha que
  // saber escrever o nome exato do posto para filtrar. Agora a lista se monta
  // sozinha com os valores que existem na tela, e o SelectBusca deixa digitar
  // para achar. Coluna cujo `valor` devolve ARRAY (tags, cargos) entra item a
  // item: quem tem 3 tags aparece nas 3, não numa opção "a, b, c".
  const opcoesDerivadas = useMemo(() => {
    const mapa = {}
    for (const col of colunas) {
      if (col.filtro !== 'lista') continue
      const vistos = new Set()
      for (const linha of dados) {
        const v = valorDe(linha, col)
        for (const item of (Array.isArray(v) ? v : [v])) {
          const t = item == null ? '' : String(item).trim()
          if (t) vistos.add(t)
        }
      }
      mapa[col.chave] = [...vistos].sort((a, b) => a.localeCompare(b, 'pt'))
    }
    return mapa
  }, [dados, colunas])

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
                    // `dica` explica a MÉTRICA (como o número é calculado);
                    // sem ela, o title continua sendo o do filtro.
                    title={card.dica || (card.filtro
                      ? (cardAtivo(card) ? 'Clique para limpar o filtro' : `Filtrar por ${card.rotulo}`)
                      : undefined)}>
              <strong>{card.valor}</strong><span>{card.rotulo}</span>
            </button>
          ))}
        </div>
      )}
      {/* Barra de filtros: GRADE compacta (não uma-linha-por-filtro), cada
          filtro com rótulo pequeno em cima. Os 'select' viram SelectBusca —
          começa a digitar e a lista filtra (feedback do Bruno: "filtro é algo
          funcional; todos eu possa começar a digitar e ir aparecendo"). Os de
          texto já filtram ao digitar em memória. Ver 08-sistema-de-design.md. */}
      <div className="rh-card dash-filtros">
        {/* Filtros do PAI (server-side) entram na MESMA grade dos de coluna —
            feedback do Bruno 2026-07-30 sobre o creche: "tem dois cards, acho
            que apenas um, tudo concentrado e coeso de filtros, seria mais
            interessante". Antes, o filtro pesado ficava num card à parte e o
            dash tinha o seu — dois controles de status na mesma tela, um
            acima do outro, que é convite a filtrar por um e estranhar o
            resultado do outro. */}
        {(filtrosExtras || []).map((f) => (
          <label key={f.chave} className="dash-filtro">
            <span className="dash-filtro-rot">{f.rotulo}</span>
            {f.opcoes ? (
              <SelectBusca
                opcoes={f.opcoes.map((o) => ({ valor: String(o.v ?? o), rotulo: String(o.r ?? o) }))}
                valor={f.valor || ''} aoEscolher={f.aoMudar}
                placeholder={`${f.rotulo}…`} vazioRotulo={f.vazioRotulo || `${f.rotulo}: todos`}
                style={{ minWidth: '100%' }} />
            ) : (
              <FiltroTexto f={f} />
            )}
          </label>
        ))}
        {colunas.filter((c) => c.filtro).map((c) => (
          <label key={c.chave} className="dash-filtro">
            <span className="dash-filtro-rot">{c.rotulo}</span>
            {c.filtro === 'select' || c.filtro === 'lista' ? (
              <SelectBusca
                opcoes={(c.filtro === 'lista'
                  ? (opcoesDerivadas[c.chave] || []).map((v) => ({ valor: v, rotulo: v }))
                  : (c.opcoes || []).map((o) => ({ valor: String(o.v ?? o), rotulo: String(o.r ?? o) })))}
                valor={filtros[c.chave] || ''}
                aoEscolher={(v) => setFiltros({ ...filtros, [c.chave]: v })}
                placeholder={`${c.rotulo}…`} vazioRotulo={`${c.rotulo}: todos`}
                style={{ minWidth: '100%' }} />
            ) : (
              <input placeholder={`${c.rotulo}…`} value={filtros[c.chave] || ''}
                     onChange={(e) => setFiltros({ ...filtros, [c.chave]: e.target.value })} />
            )}
          </label>
        ))}
        <div className="dash-filtros-acoes">
          {acoesFiltro}
          <button className="btn-secundario btn-mini" onClick={exportarCsv}>⬇ Exportar CSV</button>
          <button className="btn-secundario btn-mini" onClick={() => setConfigAberta((v) => !v)}>⚙ Colunas</button>
        </div>
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

// Filtro de TEXTO controlado pelo pai (server-side). O estado é local para a
// digitação não esperar o servidor, e só chama `aoMudar` depois da pausa
// (`debounce`, 400ms por padrão) — senão cada tecla vira uma consulta.
function FiltroTexto({ f }) {
  const [txt, setTxt] = useState(f.valor || '')
  const primeiro = useRef(true)
  // O pai é a fonte da verdade: se ele limpar o filtro por fora ("limpar
  // filtros"), o campo acompanha.
  useEffect(() => { setTxt(f.valor || '') }, [f.valor])
  useEffect(() => {
    if (primeiro.current) { primeiro.current = false; return }
    if (txt === (f.valor || '')) return
    const t = setTimeout(() => f.aoMudar(txt), f.debounce ?? 400)
    return () => clearTimeout(t)
  }, [txt])
  return <input placeholder={f.placeholder || `${f.rotulo}…`} value={txt}
                onChange={(e) => setTxt(e.target.value)} />
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
