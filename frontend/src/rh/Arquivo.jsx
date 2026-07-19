import { useEffect, useMemo, useRef, useState } from 'react'
import { fmtData } from '../fmt.js'
import { rh as api } from '../api.js'

// 🗄️ Arquivo: inventário do que o sistema guarda (dossiês, vias assinadas,
// documentos aprovados, dados) com filtros; download individual e backup em
// lote (ZIP organizado por posto/pessoa + planilha XLSX). Toda exportação é
// auditada. Leitura pura — não gera nem altera nada.

const TIPOS = [
  ['dossie', '📦 Dossiês'],
  ['assinados', '✍️ Vias assinadas'],
  ['aprovados', '📎 Documentos aprovados'],
  ['ficha', '📊 Dados da ficha (planilha)'],
]

function baixarBlob(blob, nome) {
  const a = document.createElement('a')
  a.href = URL.createObjectURL(blob)
  a.download = nome
  a.click()
  setTimeout(() => URL.revokeObjectURL(a.href), 4000)
}

export default function Arquivo() {
  const [filtros, setFiltros] = useState({ situacao: '', posto_id: '', cargo: '',
                                           desde: '', ate: '', busca: '' })
  const [dados, setDados] = useState(null)
  const [postos, setPostos] = useState([])
  const [sel, setSel] = useState(new Set())
  const [tipos, setTipos] = useState(new Set(['dossie', 'assinados', 'aprovados', 'ficha']))
  const [estimativa, setEstimativa] = useState(null)
  const [msg, setMsg] = useState(null)
  const [baixando, setBaixando] = useState(false)
  const debounce = useRef(null)

  useEffect(() => { api.postos().then((r) => setPostos(r.postos)).catch(() => {}) }, [])

  // recarrega o inventário com debounce (o filtro herda um scan quando há busca)
  useEffect(() => {
    clearTimeout(debounce.current)
    debounce.current = setTimeout(() => {
      const f = Object.fromEntries(Object.entries(filtros).filter(([, v]) => v))
      api.arquivoInventario(f).then((d) => { setDados(d); setSel(new Set()) }).catch(() => {})
    }, 400)
    return () => clearTimeout(debounce.current)
  }, [filtros])

  const toggleTipo = (t) => setTipos((s) => {
    const novo = new Set(s); novo.has(t) ? novo.delete(t) : novo.add(t); return novo
  })

  const pedido = useMemo(() => {
    const base = { tipos: [...tipos], incluir_planilha: tipos.has('ficha') }
    if (sel.size) return { ...base, ids: [...sel] }
    return { ...base, filtro: Object.fromEntries(Object.entries(filtros).filter(([, v]) => v)) }
  }, [sel, filtros, tipos])

  const estimar = async () => {
    setMsg(null)
    try { setEstimativa(await api.arquivoEstimativa(pedido)) }
    catch (e) { setMsg({ tipo: 'erro', texto: `Não foi possível estimar (${e.detail || e.message}).` }) }
  }

  const baixarLote = async () => {
    if (!tipos.size) { setMsg({ tipo: 'erro', texto: 'Escolha ao menos um tipo de conteúdo.' }); return }
    const n = sel.size || dados?.metricas.pessoas || 0
    if (!window.confirm(`Gerar o backup de ${n} pessoa(s)?\n\nO download pode demorar conforme o volume. A exportação fica registrada na auditoria (LGPD).`)) return
    setBaixando(true); setMsg(null)
    try {
      const blob = await api.arquivoLote(pedido)
      baixarBlob(blob, `arquivo-greenhouse-${new Date().toISOString().slice(0, 10)}.zip`)
      setMsg({ tipo: 'ok', texto: 'Backup gerado e baixado.' })
    } catch (e) {
      setMsg({ tipo: 'erro', texto: e.detail === 'lote_acima_do_limite'
        ? 'Seleção acima do limite (500 pessoas). Refine o filtro ou baixe em partes.'
        : e.detail === 'selecao_vazia' ? 'Nada selecionado para exportar.'
        : `Não foi possível gerar o backup (${e.detail || e.message}).` })
    } finally { setBaixando(false) }
  }

  const baixarUm = async (promessa, nome) => {
    setMsg(null)
    try { baixarBlob(await promessa, nome) }
    catch (e) {
      setMsg({ tipo: 'erro', texto: e.detail === 'arquivo_nao_encontrado' || e.detail === 'arquivo_sem_key'
        ? 'Arquivo não encontrado no armazenamento.' : `Não foi possível baixar (${e.detail || e.message}).` })
    }
  }

  const pessoas = dados?.pessoas || []
  const todosMarcados = pessoas.length > 0 && pessoas.every((p) => sel.has(p.id))
  const m = dados?.metricas

  return (
    <main className="rh-painel">
      <header className="rh-topo"><h1>🗄️ Arquivo</h1><div /></header>
      <p className="explica">Tudo que o sistema guarda por pessoa — dossiês, vias assinadas,
        documentos aprovados e dados da ficha. Baixe individualmente ou faça um <strong>backup
        em lote</strong> (ZIP organizado por posto/pessoa + planilha). Toda exportação é
        registrada na auditoria.</p>
      {msg && <div className={msg.tipo === 'erro' ? 'alerta' : 'sucesso'}>{msg.texto}</div>}

      {m && (
        <div className="rh-metricas">
          {[['Pessoas', m.pessoas], ['Com dossiê', m.com_dossie],
            ['Vias assinadas', m.vias_assinadas], ['Docs aprovados', m.docs_aprovados]].map(
            ([r, v]) => <div className="rh-metrica" key={r}><strong>{v}</strong><span>{r}</span></div>)}
        </div>
      )}

      <div className="rh-card rh-lote">
        <input placeholder="🔎 Nome, CPF ou e-mail" value={filtros.busca} style={{ maxWidth: 200 }}
               onChange={(e) => setFiltros({ ...filtros, busca: e.target.value })} />
        <select value={filtros.posto_id} onChange={(e) => setFiltros({ ...filtros, posto_id: e.target.value })}>
          <option value="">Posto: todos</option>
          {postos.map((p) => <option key={p.id} value={p.id}>{p.sigla || p.nome}</option>)}
        </select>
        <select value={filtros.cargo} onChange={(e) => setFiltros({ ...filtros, cargo: e.target.value })}>
          <option value="">Cargo: todos</option>
          {(dados?.cargos || []).map((c) => <option key={c} value={c}>{c}</option>)}
        </select>
        <select value={filtros.situacao} onChange={(e) => setFiltros({ ...filtros, situacao: e.target.value })}>
          <option value="">Situação: todas</option>
          <option value="em_admissao">Em admissão</option>
          <option value="ativo">Ativo</option>
          <option value="desligado">Desligado</option>
        </select>
        <label className="explica" style={{ margin: 0 }}>De
          <input type="date" value={filtros.desde} style={{ marginLeft: 4 }}
                 onChange={(e) => setFiltros({ ...filtros, desde: e.target.value })} /></label>
        <label className="explica" style={{ margin: 0 }}>até
          <input type="date" value={filtros.ate} style={{ marginLeft: 4 }}
                 onChange={(e) => setFiltros({ ...filtros, ate: e.target.value })} /></label>
      </div>

      <div className="rh-card rh-lote">
        <strong>Conteúdo:</strong>
        {TIPOS.map(([v, r]) => (
          <label key={v} style={{ display: 'flex', alignItems: 'center', gap: '.35rem' }}>
            <input type="checkbox" style={{ width: 'auto', minHeight: 0 }}
                   checked={tipos.has(v)} onChange={() => toggleTipo(v)} />
            <span>{r}</span>
          </label>
        ))}
      </div>

      <div className="rh-card rh-lote">
        <span className="explica" style={{ margin: 0 }}>
          {sel.size ? `${sel.size} selecionada(s)` : `Tudo que casa o filtro (${m?.pessoas || 0})`}</span>
        <button className="btn-secundario btn-mini" onClick={estimar}>Estimar tamanho</button>
        {estimativa && (
          <span className="explica" style={{ margin: 0 }}>
            ~{estimativa.tamanho_mb} MB · {estimativa.arquivos} arquivo(s)
            {estimativa.acima_do_teto && <strong style={{ color: '#d9534f' }}> · acima do limite (500)</strong>}
          </span>
        )}
        <button className="btn-principal btn-mini" disabled={baixando} onClick={baixarLote}>
          {baixando ? 'Gerando ZIP…' : '⬇ Baixar backup (ZIP)'}</button>
      </div>

      {!dados ? <p>Carregando…</p> : pessoas.length === 0 ? (
        <p className="explica centro">Ninguém encontrado com esses filtros.</p>
      ) : (
        <table className="rh-tabela">
          <thead>
            <tr>
              <th><input type="checkbox" className="check-slot" checked={todosMarcados}
                         onChange={(e) => setSel(e.target.checked ? new Set(pessoas.map((p) => p.id)) : new Set())} /></th>
              <th>Pessoa</th><th>Posto</th><th>Cargo</th><th>Situação</th>
              <th>Dossiê</th><th>Assinados</th><th>Aprovados</th><th></th>
            </tr>
          </thead>
          <tbody>
            {pessoas.map((p) => (
              <tr key={p.id}>
                <td><input type="checkbox" className="check-slot" checked={sel.has(p.id)}
                           onChange={(e) => setSel((s) => {
                             const n = new Set(s); e.target.checked ? n.add(p.id) : n.delete(p.id); return n
                           })} /></td>
                <td><strong>{p.nome_completo}</strong><br /><small>{p.cpf_mascarado}</small></td>
                <td>{p.posto_nome || '—'}</td>
                <td>{p.cargo_funcao || '—'}</td>
                <td>{p.situacao}</td>
                <td>{p.tem_dossie
                  ? <button className="btn-link" title={p.dossie_gerado_em ? `Gerado em ${fmtData(p.dossie_gerado_em)}` : ''}
                            onClick={() => baixarUm(api.arquivoDossie(p.id), `dossie-${p.nome_completo}.pdf`)}>⬇ baixar</button>
                  : '—'}</td>
                <td>{p.assinados}</td>
                <td>{p.aprovados}</td>
                <td></td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </main>
  )
}
