import { useEffect, useState } from 'react'
import { rh as api } from '../api.js'
import SelectBusca from '../SelectBusca.jsx'

// Banco de Itens (Provas Fase 2): questões REUTILIZÁVEIS catalogadas por cargo,
// senioridade e tags. Montar uma prova a partir do banco COPIA os itens (o
// EditorProva faz isso); aqui é o CRUD + filtros. Não desmonta provas existentes.
// Segue o sistema de design (edição na própria linha, filtros na barra).

const SEN_ROTULO = { qualquer: 'Qualquer', junior: 'Júnior', pleno: 'Pleno', senior: 'Sênior' }

export default function BancoItens() {
  const [dados, setDados] = useState(null)   // { itens, cargos, tags, senioridades }
  const [filtro, setFiltro] = useState({ cargo: '', senioridade: '', tag: '', tipo: '' })
  const [novo, setNovo] = useState(false)
  const [editando, setEditando] = useState(null)
  const [msg, setMsg] = useState(null)

  const carregar = () => api.bancoItens(filtro).then(setDados).catch(() => setDados({ itens: [] }))
  useEffect(() => { carregar() }, [filtro.cargo, filtro.senioridade, filtro.tag, filtro.tipo])

  const excluir = async (it) => {
    if (!window.confirm('Excluir este item do banco? Provas já montadas com ele NÃO mudam.')) return
    try { await api.excluirItemBanco(it.id); carregar() }
    catch (e) { setMsg({ tipo: 'erro', texto: e.amigavel || e.detail || e.message }) }
  }

  if (!dados) return <p className="explica">Carregando…</p>
  const cargosOpc = (dados.cargos || []).map((c) => ({ valor: c, rotulo: c }))
  const tagsOpc = (dados.tags || []).map((t) => ({ valor: t, rotulo: t }))

  return (
    <>
      <p className="explica">Questões reutilizáveis: catalogue por <strong>cargo</strong>,
        <strong> senioridade</strong> e <strong>tags</strong> uma vez, e monte provas rápido —
        escolhendo item a item ou por sorteio (na aba Provas, ao editar a prova). Editar ou
        excluir um item aqui <strong>não altera</strong> provas já montadas.</p>
      {msg && <div className={msg.tipo === 'erro' ? 'alerta' : 'sucesso'}>{msg.texto}</div>}

      {/* Filtros em grade compacta (padrão do sistema de design) */}
      <div className="rh-card dash-filtros">
        <label className="dash-filtro"><span className="dash-filtro-rot">Cargo</span>
          <SelectBusca opcoes={cargosOpc} valor={filtro.cargo}
                       aoEscolher={(v) => setFiltro({ ...filtro, cargo: v })}
                       placeholder="Cargo…" vazioRotulo="Cargo: todos" style={{ minWidth: '100%' }} /></label>
        <label className="dash-filtro"><span className="dash-filtro-rot">Senioridade</span>
          <SelectBusca opcoes={(dados.senioridades || []).map((s) => ({ valor: s, rotulo: SEN_ROTULO[s] || s }))}
                       valor={filtro.senioridade}
                       aoEscolher={(v) => setFiltro({ ...filtro, senioridade: v })}
                       placeholder="Senioridade…" vazioRotulo="Senioridade: todas" style={{ minWidth: '100%' }} /></label>
        <label className="dash-filtro"><span className="dash-filtro-rot">Tag</span>
          <SelectBusca opcoes={tagsOpc} valor={filtro.tag}
                       aoEscolher={(v) => setFiltro({ ...filtro, tag: v })}
                       placeholder="Tag…" vazioRotulo="Tag: todas" style={{ minWidth: '100%' }} /></label>
        <label className="dash-filtro"><span className="dash-filtro-rot">Tipo</span>
          <SelectBusca opcoes={[{ valor: 'objetiva', rotulo: 'Objetiva' }, { valor: 'discursiva', rotulo: 'Discursiva' }]}
                       valor={filtro.tipo}
                       aoEscolher={(v) => setFiltro({ ...filtro, tipo: v })}
                       placeholder="Tipo…" vazioRotulo="Tipo: todos" style={{ minWidth: '100%' }} /></label>
      </div>

      {novo
        ? <FormItem senioridades={dados.senioridades}
                    aoFechar={() => { setNovo(false); carregar() }}
                    aoErro={(t) => setMsg({ tipo: 'erro', texto: t })} />
        : <button className="btn-principal btn-mini" style={{ marginBottom: '.7rem' }}
                  onClick={() => setNovo(true)}>＋ Novo item</button>}

      <div className="rh-card">
        <h3>{dados.itens.length} item(ns)</h3>
        {dados.itens.length === 0 && <p className="explica">Nenhum item com esses filtros.</p>}
        {dados.itens.map((it) => (
          editando === it.id
            ? <FormItem key={it.id} item={it} senioridades={dados.senioridades}
                        aoFechar={() => { setEditando(null); carregar() }}
                        aoErro={(m) => setMsg({ tipo: 'erro', texto: m })} />
            : (
              <div className="prova-questao" key={it.id}>
                <div className="prova-questao-topo">
                  <strong>{it.tipo === 'objetiva' ? '☑' : '✎'} {it.enunciado}</strong>
                  <span className="prova-questao-acoes">
                    <button className="btn-link" onClick={() => setEditando(it.id)}>editar</button>
                    <button className="btn-link" style={{ color: '#d9534f' }} onClick={() => excluir(it)}>excluir</button>
                  </span>
                </div>
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: '.3rem', margin: '.2rem 0' }}>
                  {it.cargo && <span className="chip">{it.cargo}</span>}
                  <span className="chip">{SEN_ROTULO[it.senioridade] || it.senioridade}</span>
                  {(it.tags || []).map((t) => <span key={t} className="chip" style={{ '--chip-cor': '#5b8def' }}>{t}</span>)}
                </div>
                {it.explicacao && <small className="explica" style={{ margin: 0 }}>💡 {it.explicacao}</small>}
              </div>
            )
        ))}
      </div>
    </>
  )
}

// Form de item do banco: enunciado + (opções/gabarito se objetiva) + explicação
// + cargo + senioridade + tags.
function FormItem({ item, senioridades, aoFechar, aoErro }) {
  const novo = !item
  const [tipo, setTipo] = useState(item?.tipo || 'objetiva')
  const [enunciado, setEnunciado] = useState(item?.enunciado || '')
  const [opcoes, setOpcoes] = useState(
    item?.opcoes?.length ? item.opcoes : [{ id: 'a', texto: '' }, { id: 'b', texto: '' }])
  const [gabarito, setGabarito] = useState(item?.gabarito || 'a')
  const [explicacao, setExplicacao] = useState(item?.explicacao || '')
  const [peso, setPeso] = useState(item?.peso || 1)
  const [cargo, setCargo] = useState(item?.cargo || '')
  const [senioridade, setSenioridade] = useState(item?.senioridade || 'qualquer')
  const [tags, setTags] = useState((item?.tags || []).join(', '))
  const [salvando, setSalvando] = useState(false)

  const letra = (i) => String.fromCharCode(97 + i)
  const setOpcao = (i, texto) => setOpcoes((os) => os.map((o, j) => j === i ? { ...o, texto } : o))
  const addOpcao = () => setOpcoes((os) => [...os, { id: letra(os.length), texto: '' }])
  const removeOpcao = (i) => setOpcoes((os) => os.length > 2 ? os.filter((_, j) => j !== i) : os)

  const salvar = async () => {
    if (!enunciado.trim()) { aoErro('Escreva o enunciado.'); return }
    const dados = {
      enunciado, tipo, explicacao: explicacao.trim() || null, peso: parseInt(peso, 10) || 1,
      cargo: cargo.trim() || null, senioridade,
      tags: tags.split(',').map((t) => t.trim()).filter(Boolean),
    }
    if (tipo === 'objetiva') {
      const limpas = opcoes.filter((o) => o.texto.trim()).map((o, i) => ({ id: letra(i), texto: o.texto.trim() }))
      if (limpas.length < 2) { aoErro('Informe ao menos 2 opções.'); return }
      const idxGab = opcoes.findIndex((o) => o.id === gabarito)
      dados.opcoes = limpas
      dados.gabarito = letra(Math.max(0, Math.min(idxGab, limpas.length - 1)))
    }
    setSalvando(true)
    try {
      if (novo) await api.criarItemBanco(dados)
      else await api.editarItemBanco(item.id, dados)
      aoFechar()
    } catch (e) { aoErro(e.amigavel || e.detail || e.message) }
    finally { setSalvando(false) }
  }

  return (
    <div className="prova-questao editando">
      <label className="campo"><span className="rotulo">Tipo</span>
        <select value={tipo} onChange={(e) => setTipo(e.target.value)}>
          <option value="objetiva">Objetiva</option>
          <option value="discursiva">Discursiva</option></select></label>
      <label className="campo"><span className="rotulo">Enunciado</span>
        <textarea rows={2} value={enunciado} onChange={(e) => setEnunciado(e.target.value)} autoFocus /></label>
      {tipo === 'objetiva' && (
        <div className="prova-opcoes-ed">
          <span className="rotulo">Opções <small>(marque a correta)</small></span>
          {opcoes.map((o, i) => (
            <div className="prova-opcao-linha" key={i}>
              <input type="radio" name={`gab-${item?.id || 'novo'}`} checked={gabarito === o.id}
                     onChange={() => setGabarito(o.id)} title="Resposta correta" />
              <input value={o.texto} placeholder={`Opção ${letra(i).toUpperCase()}`}
                     onChange={(e) => setOpcao(i, e.target.value)} />
              {opcoes.length > 2 && <button className="btn-link" onClick={() => removeOpcao(i)}>×</button>}
            </div>
          ))}
          <button className="btn-link" onClick={addOpcao}>+ opção</button>
        </div>
      )}
      <label className="campo"><span className="rotulo">Explicação da resposta (opcional)</span>
        <textarea rows={2} value={explicacao} onChange={(e) => setExplicacao(e.target.value)} /></label>
      <div className="linha3">
        <label className="campo"><span className="rotulo">Cargo (opcional)</span>
          <input value={cargo} placeholder="Genérico se em branco"
                 onChange={(e) => setCargo(e.target.value)} /></label>
        <label className="campo"><span className="rotulo">Senioridade</span>
          <select value={senioridade} onChange={(e) => setSenioridade(e.target.value)}>
            {(senioridades || ['qualquer']).map((s) => (
              <option key={s} value={s}>{SEN_ROTULO[s] || s}</option>))}</select></label>
        <label className="campo" style={{ maxWidth: 100 }}><span className="rotulo">Peso</span>
          <input type="number" min={1} value={peso} onChange={(e) => setPeso(e.target.value)} /></label>
      </div>
      <label className="campo"><span className="rotulo">Tags <small>(vírgula: ex. NR-35, ronda)</small></span>
        <input value={tags} onChange={(e) => setTags(e.target.value)} /></label>
      <div className="rh-lote">
        <button className="btn-principal btn-mini" disabled={salvando} onClick={salvar}>
          {salvando ? 'Salvando…' : 'Salvar item'}</button>
        <button className="btn-link" onClick={aoFechar}>cancelar</button>
      </div>
    </div>
  )
}
