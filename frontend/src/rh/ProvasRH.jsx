import { useEffect, useState } from 'react'
import { rh as api } from '../api.js'
import { fmtData } from '../fmt.js'
import DashPlanilha from './DashPlanilha.jsx'
import BancoItens from './BancoItens.jsx'
import SelectBusca from '../SelectBusca.jsx'

// Módulo de PROVAS por cargo: o RH monta provas (objetivas com gabarito +
// discursivas), gera link de aplicação e corrige. Duas visões: Editor e
// Aplicações (dash-planilha com correção). O gabarito nunca vai ao candidato.
export default function ProvasRH() {
  const [visao, setVisao] = useState('editor')  // editor | aplicacoes | banco
  return (
    <>
      <div className="rh-card rh-lote" style={{ gap: '.4rem' }}>
        <button className={`btn-mini ${visao === 'editor' ? 'btn-principal' : 'btn-secundario'}`}
                onClick={() => setVisao('editor')}>📝 Provas</button>
        <button className={`btn-mini ${visao === 'banco' ? 'btn-principal' : 'btn-secundario'}`}
                onClick={() => setVisao('banco')}>🗃️ Banco de itens</button>
        <button className={`btn-mini ${visao === 'aplicacoes' ? 'btn-principal' : 'btn-secundario'}`}
                onClick={() => setVisao('aplicacoes')}>📊 Aplicações & correção</button>
      </div>
      {visao === 'editor' && <Editor />}
      {visao === 'banco' && <BancoItens />}
      {visao === 'aplicacoes' && <Aplicacoes />}
    </>
  )
}

function Editor() {
  const [provas, setProvas] = useState(null)
  const [aberta, setAberta] = useState(null)   // prova em edição (com questões)
  const [msg, setMsg] = useState(null)

  const recarregar = () => api.provas().then(setProvas).catch(() => setProvas([]))
  useEffect(() => { recarregar() }, [])

  const nova = async () => {
    const titulo = window.prompt('Título da nova prova:')
    if (!titulo?.trim()) return
    try { const p = await api.criarProva({ titulo }); await recarregar(); abrir(p.id) }
    catch (e) { setMsg({ tipo: 'erro', texto: `Não foi possível criar (${e.detail || e.message}).` }) }
  }
  const abrir = async (id) => {
    try { setAberta(await api.provaDetalhe(id)) }
    catch { setMsg({ tipo: 'erro', texto: 'Não foi possível abrir a prova.' }) }
  }
  const excluir = async (p) => {
    if (!window.confirm(`Excluir a prova "${p.titulo}"? Vai para a lixeira.`)) return
    try { await api.excluirProva(p.id); setAberta(null); await recarregar() }
    catch (e) { setMsg({ tipo: 'erro', texto: `Falha ao excluir (${e.detail || e.message}).` }) }
  }
  const duplicar = async (p) => {
    try { const nova = await api.duplicarProva(p.id); await recarregar(); abrir(nova.id) }
    catch (e) { setMsg({ tipo: 'erro', texto: `Falha ao duplicar (${e.detail || e.message}).` }) }
  }

  if (aberta) return <EditorProva prova={aberta} aoVoltar={() => { setAberta(null); recarregar() }}
                                  aoSalvarMeta={abrir} />

  return (
    <>
      <div className="rh-card rh-lote">
        <button className="btn-principal btn-mini" onClick={nova}>+ Nova prova</button>
        <span className="explica" style={{ margin: 0 }}>{provas ? `${provas.length} prova(s)` : ''}</span>
      </div>
      {msg && <div className={msg.tipo === 'erro' ? 'alerta' : 'sucesso'}>{msg.texto}</div>}

      {!provas ? <p>Carregando…</p> : provas.length === 0 ? (
        <p className="explica centro">Nenhuma prova ainda. Crie a primeira.</p>
      ) : (
        <table className="rh-tabela">
          <thead><tr><th>Título</th><th>Cargo</th><th>Questões</th><th>Tempo</th><th>Ativa</th><th></th></tr></thead>
          <tbody>
            {provas.map((p) => (
              <tr key={p.id}>
                <td><strong>{p.titulo}</strong></td>
                <td>{p.cargo || '— genérica'}</td>
                <td>{p.qtd_questoes} ({p.qtd_objetivas} obj · {p.qtd_discursivas} disc)</td>
                <td>{Math.round(p.tempo_segundos / 60)} min</td>
                <td>{p.ativa ? '✅' : '🚫'}</td>
                <td className="acoes-candidato">
                  <button className="btn-secundario btn-mini" onClick={() => abrir(p.id)}>Editar</button>
                  <button className="btn-secundario btn-mini" onClick={() => duplicar(p)}>Duplicar</button>
                  <button className="btn-link" style={{ color: '#d9534f' }} onClick={() => excluir(p)}>Excluir</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </>
  )
}

function EditorProva({ prova, aoVoltar, aoSalvarMeta }) {
  const [p, setP] = useState(prova)
  const [msg, setMsg] = useState(null)
  const [nova, setNova] = useState(null)  // questão sendo criada
  const [doBanco, setDoBanco] = useState(false)  // painel "adicionar do banco"

  const recarregar = async () => { const d = await api.provaDetalhe(p.id); setP(d) }

  const salvarMeta = async () => {
    try {
      await api.editarProva(p.id, { titulo: p.titulo, cargo: p.cargo, descricao: p.descricao,
        tempo_segundos: p.tempo_segundos, ativa: p.ativa,
        embaralhar: p.embaralhar, mostrar_explicacao: p.mostrar_explicacao })
      setMsg({ tipo: 'ok', texto: 'Prova salva.' })
    } catch (e) { setMsg({ tipo: 'erro', texto: `Falha ao salvar (${e.detail || e.message}).` }) }
  }
  const excluirQ = async (q) => {
    if (!window.confirm('Excluir esta questão?')) return
    try { await api.excluirQuestao(p.id, q.id); await recarregar() }
    catch (e) { setMsg({ tipo: 'erro', texto: `Falha (${e.detail || e.message}).` }) }
  }
  const duplicarQ = async (q) => {
    try { await api.duplicarQuestao(p.id, q.id); await recarregar() }
    catch (e) { setMsg({ tipo: 'erro', texto: `Falha ao duplicar (${e.detail || e.message}).` }) }
  }
  const promoverQ = async (q) => {
    // herda o cargo da prova; senioridade "qualquer" e sem tags — o RH refina no
    // Banco de Itens depois. Copia (a questão original permanece na prova).
    try {
      await api.promoverParaBanco(p.id, q.id, { cargo: p.cargo || null })
      setMsg({ tipo: 'ok', texto: 'Questão copiada para o Banco de Itens (ajuste cargo/senioridade/tags lá).' })
    } catch (e) { setMsg({ tipo: 'erro', texto: `Falha ao enviar ao banco (${e.detail || e.message}).` }) }
  }

  const gerarLink = async () => {
    if (!p.questoes?.length) { setMsg({ tipo: 'erro', texto: 'Adicione ao menos uma questão antes de aplicar.' }); return }
    try {
      const r = await api.criarLinkProva(p.id, p.titulo)
      navigator.clipboard?.writeText(r.url)
      setMsg({ tipo: 'ok', texto: `Link de aplicação criado e copiado: ${r.url}` })
    } catch (e) { setMsg({ tipo: 'erro', texto: `Falha ao gerar link (${e.detail || e.message}).` }) }
  }

  return (
    <>
      <div className="rh-card rh-lote">
        <button className="btn-link" onClick={aoVoltar}>← Voltar às provas</button>
        <span className="dash-espaco" style={{ flex: 1 }} />
        <button className="btn-principal btn-mini" onClick={gerarLink}>🔗 Gerar link de aplicação</button>
      </div>
      {msg && <div className={msg.tipo === 'erro' ? 'alerta' : 'sucesso'}>{msg.texto}</div>}

      <div className="rh-card">
        <div className="linha2">
          <label className="campo"><span className="rotulo">Título</span>
            <input value={p.titulo} onChange={(e) => setP({ ...p, titulo: e.target.value })} /></label>
          <label className="campo"><span className="rotulo">Cargo (opcional)</span>
            <input value={p.cargo || ''} placeholder="Genérica se em branco"
                   onChange={(e) => setP({ ...p, cargo: e.target.value })} /></label>
        </div>
        <div className="linha2">
          <label className="campo"><span className="rotulo">Tempo (minutos)</span>
            <input type="number" min={1} value={Math.round(p.tempo_segundos / 60)}
                   onChange={(e) => setP({ ...p, tempo_segundos: (parseInt(e.target.value, 10) || 30) * 60 })} /></label>
          <label className="campo"><span className="rotulo">Ativa</span>
            <select value={p.ativa ? '1' : '0'} onChange={(e) => setP({ ...p, ativa: e.target.value === '1' })}>
              <option value="1">Sim</option><option value="0">Não</option></select></label>
        </div>
        <label className="campo"><span className="rotulo">Descrição / instruções (opcional)</span>
          <textarea rows={2} value={p.descricao || ''} onChange={(e) => setP({ ...p, descricao: e.target.value })} /></label>
        <label style={{ display: 'flex', alignItems: 'center', gap: '.5rem', margin: '.2rem 0' }}>
          <input type="checkbox" checked={!!p.embaralhar}
                 onChange={(e) => setP({ ...p, embaralhar: e.target.checked })} />
          <span>Embaralhar a ordem das questões e das alternativas para cada
            participante <small className="explica" style={{ margin: 0 }}>(anti-cola;
            a nota não muda)</small></span></label>
        <label style={{ display: 'flex', alignItems: 'center', gap: '.5rem', margin: '.2rem 0' }}>
          <input type="checkbox" checked={!!p.mostrar_explicacao}
                 onChange={(e) => setP({ ...p, mostrar_explicacao: e.target.checked })} />
          <span>Ao terminar, mostrar ao participante o gabarito e a explicação de
            cada questão <small className="explica" style={{ margin: 0 }}>(didática;
            deixe DESLIGADO em prova de seleção)</small></span></label>
        <button className="btn-principal btn-mini" onClick={salvarMeta}>Salvar dados da prova</button>
      </div>

      <div className="rh-card">
        <h3>Questões ({p.questoes?.length || 0})</h3>
        {(p.questoes || []).map((q, i) => (
          <QuestaoItem key={q.id} n={i + 1} provaId={p.id} questao={q}
                       aoSalvar={recarregar} aoExcluir={() => excluirQ(q)}
                       aoDuplicar={() => duplicarQ(q)} aoPromover={() => promoverQ(q)} />
        ))}
        {nova
          ? <QuestaoNova provaId={p.id} tipoInicial={nova}
                         aoSalvar={() => { setNova(null); recarregar() }}
                         aoCancelar={() => setNova(null)} />
          : doBanco
            ? <MontarDoBanco provaId={p.id} aoFechar={() => { setDoBanco(false); recarregar() }}
                             aoErro={(t) => setMsg({ tipo: 'erro', texto: t })} />
            : (
              <div className="rh-lote" style={{ marginTop: '.6rem' }}>
                <button className="btn-secundario btn-mini" onClick={() => setNova('objetiva')}>+ Questão objetiva</button>
                <button className="btn-secundario btn-mini" onClick={() => setNova('discursiva')}>+ Questão discursiva</button>
                <button className="btn-secundario btn-mini" onClick={() => setDoBanco(true)}>🗃️ Adicionar do banco</button>
              </div>
            )}
      </div>
    </>
  )
}

function QuestaoItem({ n, provaId, questao, aoSalvar, aoExcluir, aoDuplicar, aoPromover }) {
  const [ed, setEd] = useState(false)
  if (ed) return <FormQuestao provaId={provaId} inicial={questao}
                              aoSalvar={() => { setEd(false); aoSalvar() }}
                              aoCancelar={() => setEd(false)} />
  return (
    <div className="prova-questao">
      <div className="prova-questao-topo">
        <strong>{n}. {questao.tipo === 'objetiva' ? '☑' : '✎'} {questao.enunciado}</strong>
        <span className="prova-questao-acoes">
          <button className="btn-link" onClick={() => setEd(true)}>editar</button>
          <button className="btn-link" onClick={aoDuplicar}>duplicar</button>
          <button className="btn-link" onClick={aoPromover} title="Copiar para o banco de itens (reaproveitar em outras provas)">→ banco</button>
          <button className="btn-link" style={{ color: '#d9534f' }} onClick={aoExcluir}>excluir</button>
        </span>
      </div>
      {questao.tipo === 'objetiva' && (
        <ul className="prova-opcoes">
          {(questao.opcoes || []).map((o) => (
            <li key={o.id} className={o.id === questao.gabarito ? 'certa' : ''}>
              {o.id === questao.gabarito ? '✔ ' : ''}{o.texto}</li>
          ))}
        </ul>
      )}
      {questao.explicacao && (
        <small className="explica" style={{ margin: '.2rem 0 0' }}>💡 {questao.explicacao}</small>
      )}
      <small className="explica" style={{ margin: 0 }}>Peso {questao.peso}
        {questao.tipo === 'discursiva' ? ' · correção manual' : ''}</small>
    </div>
  )
}

function QuestaoNova({ provaId, tipoInicial, aoSalvar, aoCancelar }) {
  // tipoInicial vem do botão ("objetiva" ou "discursiva"). ANTES o form nascia
  // sempre objetivo (inicial={null} → tipo 'objetiva'), então o botão de
  // discursiva caía no form de objetiva (bug relatado pelo Bruno).
  return <FormQuestao provaId={provaId} inicial={null} tipoInicial={tipoInicial}
                      aoSalvar={aoSalvar} aoCancelar={aoCancelar} />
}

const SEN_ROT = { qualquer: 'Qualquer', junior: 'Júnior', pleno: 'Pleno', senior: 'Sênior' }

// Adicionar questões do BANCO DE ITENS à prova. Dois modos: escolher item a item
// (checkbox, filtrando) ou sorteio automático (N itens por filtro). Ambos COPIAM
// os itens para a prova (snapshot) — não desmontam nada do que já existe.
function MontarDoBanco({ provaId, aoFechar, aoErro }) {
  const [modo, setModo] = useState('manual')  // manual | sorteio
  const [dados, setDados] = useState(null)
  const [filtro, setFiltro] = useState({ cargo: '', senioridade: '', tag: '' })
  const [marcados, setMarcados] = useState(() => new Set())
  const [qtd, setQtd] = useState(5)
  const [salvando, setSalvando] = useState(false)

  const carregar = () => api.bancoItens(filtro).then(setDados).catch(() => setDados({ itens: [] }))
  useEffect(() => { carregar() }, [filtro.cargo, filtro.senioridade, filtro.tag])

  const alterna = (id) => setMarcados((s) => {
    const n = new Set(s); n.has(id) ? n.delete(id) : n.add(id); return n
  })

  const aplicar = async () => {
    setSalvando(true)
    try {
      if (modo === 'manual') {
        if (marcados.size === 0) { aoErro('Marque ao menos um item.'); setSalvando(false); return }
        await api.adicionarDoBanco(provaId, { item_ids: [...marcados] })
      } else {
        await api.adicionarDoBanco(provaId, {
          quantidade: parseInt(qtd, 10) || 1, cargo: filtro.cargo || null,
          senioridade: filtro.senioridade || null, tag: filtro.tag || null })
      }
      aoFechar()
    } catch (e) {
      aoErro(e.detail === 'banco_sem_itens_no_filtro' ? 'O banco não tem itens com esse filtro.'
        : (e.amigavel || e.detail || e.message))
      setSalvando(false)
    }
  }

  if (!dados) return <p className="explica">Carregando o banco…</p>
  const cargosOpc = (dados.cargos || []).map((c) => ({ valor: c, rotulo: c }))
  const tagsOpc = (dados.tags || []).map((t) => ({ valor: t, rotulo: t }))

  return (
    <div className="rh-card" style={{ background: 'var(--input-bg)', marginTop: '.6rem' }}>
      <div className="rh-lote" style={{ marginBottom: '.5rem' }}>
        <strong>Adicionar do banco:</strong>
        <button className={`btn-mini ${modo === 'manual' ? 'btn-principal' : 'btn-secundario'}`}
                onClick={() => setModo('manual')}>Escolher itens</button>
        <button className={`btn-mini ${modo === 'sorteio' ? 'btn-principal' : 'btn-secundario'}`}
                onClick={() => setModo('sorteio')}>Sortear</button>
        <span className="dash-espaco" style={{ flex: 1 }} />
        <button className="btn-link" onClick={aoFechar}>cancelar</button>
      </div>

      <div className="dash-filtros">
        <label className="dash-filtro"><span className="dash-filtro-rot">Cargo</span>
          <SelectBusca opcoes={cargosOpc} valor={filtro.cargo}
                       aoEscolher={(v) => setFiltro({ ...filtro, cargo: v })}
                       vazioRotulo="Cargo: todos" style={{ minWidth: '100%' }} /></label>
        <label className="dash-filtro"><span className="dash-filtro-rot">Senioridade</span>
          <SelectBusca opcoes={(dados.senioridades || []).map((s) => ({ valor: s, rotulo: SEN_ROT[s] || s }))}
                       valor={filtro.senioridade}
                       aoEscolher={(v) => setFiltro({ ...filtro, senioridade: v })}
                       vazioRotulo="Senioridade: todas" style={{ minWidth: '100%' }} /></label>
        <label className="dash-filtro"><span className="dash-filtro-rot">Tag</span>
          <SelectBusca opcoes={tagsOpc} valor={filtro.tag}
                       aoEscolher={(v) => setFiltro({ ...filtro, tag: v })}
                       vazioRotulo="Tag: todas" style={{ minWidth: '100%' }} /></label>
      </div>

      {modo === 'sorteio' ? (
        <div className="rh-lote" style={{ margin: '.6rem 0' }}>
          <label className="campo" style={{ maxWidth: 160 }}><span className="rotulo">Quantos itens sortear</span>
            <input type="number" min={1} value={qtd} onChange={(e) => setQtd(e.target.value)} /></label>
          <span className="explica" style={{ margin: 0 }}>Sorteia do banco conforme os filtros acima
            ({dados.itens.length} disponível(is)).</span>
        </div>
      ) : (
        <div style={{ maxHeight: '18rem', overflowY: 'auto', margin: '.5rem 0' }}>
          {dados.itens.length === 0 && <p className="explica">Nenhum item com esses filtros.</p>}
          {dados.itens.map((it) => (
            <label key={it.id} style={{ display: 'flex', gap: '.5rem', alignItems: 'flex-start', padding: '.3rem 0' }}>
              <input type="checkbox" checked={marcados.has(it.id)} onChange={() => alterna(it.id)} />
              <span>{it.tipo === 'objetiva' ? '☑' : '✎'} {it.enunciado}
                <small className="explica" style={{ margin: 0 }}>
                  {' '}· {it.cargo || 'genérico'} · {SEN_ROT[it.senioridade] || it.senioridade}
                  {(it.tags || []).length ? ` · ${it.tags.join(', ')}` : ''}</small></span>
            </label>
          ))}
        </div>
      )}

      <button className="btn-principal btn-mini" disabled={salvando} onClick={aplicar}>
        {salvando ? 'Adicionando…'
          : modo === 'manual' ? `Adicionar ${marcados.size} item(ns)` : `Sortear e adicionar`}</button>
    </div>
  )
}

// Formulário de questão (nova ou edição). Objetiva: enunciado + opções (a
// marcada é o gabarito). Discursiva: só enunciado. Em criação, o tipo vem de
// `tipoInicial` (botão); em edição, do próprio registro.
function FormQuestao({ provaId, inicial, tipoInicial, aoSalvar, aoCancelar }) {
  const [tipo] = useState(inicial?.tipo || tipoInicial || 'objetiva')
  const objetiva = tipo === 'objetiva'
  const [enunciado, setEnunciado] = useState(inicial?.enunciado || '')
  const [peso, setPeso] = useState(inicial?.peso || 1)
  const [opcoes, setOpcoes] = useState(
    inicial?.opcoes?.length ? inicial.opcoes : [{ id: 'a', texto: '' }, { id: 'b', texto: '' }])
  const [gabarito, setGabarito] = useState(inicial?.gabarito || 'a')
  const [explicacao, setExplicacao] = useState(inicial?.explicacao || '')
  const [erro, setErro] = useState(null)

  const letra = (i) => String.fromCharCode(97 + i)
  const setOpcao = (i, texto) => setOpcoes((os) => os.map((o, j) => j === i ? { ...o, texto } : o))
  const addOpcao = () => setOpcoes((os) => [...os, { id: letra(os.length), texto: '' }])
  const removeOpcao = (i) => setOpcoes((os) => os.length > 2 ? os.filter((_, j) => j !== i) : os)

  const salvar = async () => {
    if (!enunciado.trim()) { setErro('Escreva o enunciado.'); return }
    const dados = { enunciado, tipo, peso: parseInt(peso, 10) || 1,
                    explicacao: explicacao.trim() || null }
    if (tipo === 'objetiva') {
      const limpas = opcoes.filter((o) => o.texto.trim()).map((o, i) => ({ id: letra(i), texto: o.texto.trim() }))
      if (limpas.length < 2) { setErro('Informe ao menos 2 opções.'); return }
      // reindexa o gabarito para a nova ordem/letras
      const idxGab = opcoes.findIndex((o) => o.id === gabarito)
      dados.opcoes = limpas
      dados.gabarito = letra(Math.max(0, Math.min(idxGab, limpas.length - 1)))
    }
    setErro(null)
    try {
      if (inicial) await api.editarQuestao(provaId, inicial.id, dados)
      else await api.criarQuestao(provaId, dados)
      aoSalvar()
    } catch (e) { setErro(`Falha ao salvar (${e.detail || e.message}).`) }
  }

  return (
    <div className="prova-questao editando">
      <label className="campo"><span className="rotulo">Enunciado ({objetiva ? 'objetiva' : 'discursiva'})</span>
        <textarea rows={2} value={enunciado} onChange={(e) => setEnunciado(e.target.value)} autoFocus /></label>
      {tipo === 'objetiva' && (
        <div className="prova-opcoes-ed">
          <span className="rotulo">Opções <small>(marque a correta)</small></span>
          {opcoes.map((o, i) => (
            <div className="prova-opcao-linha" key={i}>
              <input type="radio" name={`gab-${inicial?.id || 'novo'}`} checked={gabarito === o.id}
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
        <textarea rows={2} value={explicacao} placeholder="Por que a resposta correta é a correta — só aparece ao participante se a prova permitir mostrar."
                  onChange={(e) => setExplicacao(e.target.value)} /></label>
      <label className="campo" style={{ maxWidth: 120 }}><span className="rotulo">Peso</span>
        <input type="number" min={1} value={peso} onChange={(e) => setPeso(e.target.value)} /></label>
      {erro && <div className="alerta">{erro}</div>}
      <div className="rh-lote">
        <button className="btn-principal btn-mini" onClick={salvar}>Salvar questão</button>
        <button className="btn-link" onClick={aoCancelar}>cancelar</button>
      </div>
    </div>
  )
}

// Aplicações das provas: dash-planilha (ordena/filtra/exporta) + correção das
// discursivas. A nota final combina objetivas (auto) + discursivas (RH).
function Aplicacoes() {
  const [apps, setApps] = useState(null)
  const [aberta, setAberta] = useState(null)  // aplicação em correção (detalhe)
  const [msg, setMsg] = useState(null)

  const recarregar = () => api.provaAplicacoes({}).then(setApps).catch(() => setApps([]))
  useEffect(() => { recarregar() }, [])

  const abrir = async (a) => {
    try { setAberta(await api.provaAplicacao(a.id)) }
    catch { setMsg({ tipo: 'erro', texto: 'Não foi possível abrir a aplicação.' }) }
  }

  if (aberta) return <Correcao aplicacao={aberta}
                               aoVoltar={() => { setAberta(null); recarregar() }} />

  const nota = (v) => v == null ? '—' : `${v}`
  const STATUS = {
    pendente: ['Não começou', '#889'], em_andamento: ['Em andamento', '#f0ad4e'],
    concluido: ['Concluído', '#0fb257'], expirado: ['Tempo esgotado', '#d9534f'],
  }
  const chip = (s) => { const [r, c] = STATUS[s] || [s, '#888']; return <span className="chip" style={{ '--chip-cor': c }}>{r}</span> }

  const colunas = [
    { chave: 'nome', rotulo: 'Participante', ordenavel: true, filtro: 'texto', sempreVisivel: true,
      render: (a) => <strong>{a.nome}</strong> },
    { chave: 'prova_titulo', rotulo: 'Prova', ordenavel: true, filtro: 'texto' },
    { chave: 'cargo', rotulo: 'Cargo', filtro: 'texto' },
    { chave: 'status', rotulo: 'Status', filtro: 'select',
      opcoes: [{ v: 'concluido', r: 'Concluído' }, { v: 'em_andamento', r: 'Em andamento' },
               { v: 'expirado', r: 'Tempo esgotado' }, { v: 'pendente', r: 'Não começou' }],
      valor: (a) => (STATUS[a.status] || [a.status])[0], render: (a) => chip(a.status) },
    { chave: 'nota_objetivas', rotulo: 'Objetivas', ordenavel: true, valor: (a) => a.nota_objetivas ?? -1,
      render: (a) => nota(a.nota_objetivas) },
    { chave: 'nota_final', rotulo: 'Nota final', ordenavel: true, valor: (a) => a.nota_final ?? -1,
      render: (a) => a.nota_final == null ? '—' : <strong>{a.nota_final}</strong> },
    { chave: 'correcao', rotulo: 'Correção', valor: (a) => a.precisa_correcao ? 'Pendente' : 'OK',
      render: (a) => a.precisa_correcao
        ? <span className="chip" style={{ '--chip-cor': '#d9534f' }}>corrigir</span>
        : (a.discursivas_total ? '✅' : '—') },
    { chave: 'comportamento', rotulo: 'Comportamento', ordenavel: true,
      valor: (a) => a.alertas_comportamento ?? 0,
      render: (a) => {
        const n = a.alertas_comportamento || 0
        const c = a.comportamento || {}
        if (!a.comportamento) return <span className="explica">—</span>
        const partes = []
        if (c.saidas_da_tela) partes.push(`${c.saidas_da_tela}× saiu da tela`)
        if (c.segundos_fora_da_tela) partes.push(`${c.segundos_fora_da_tela}s fora`)
        if (c.tentativas_print) partes.push(`${c.tentativas_print}× print`)
        if (c.copiar_colar) partes.push(`${c.copiar_colar}× copiar/colar`)
        if (c.quedas_de_conexao) partes.push(`${c.quedas_de_conexao}× caiu a conexão`)
        return n > 0
          ? <span className="chip" style={{ '--chip-cor': '#d9534f' }} title={partes.join(' · ')}>⚠️ {n}</span>
          : <span className="chip" style={{ '--chip-cor': '#0fb257' }} title="Sem sinais de saída/cópia">✓ limpo</span>
      } },
    { chave: 'criado_em', rotulo: 'Quando', ordenavel: true, valor: (a) => a.criado_em,
      render: (a) => fmtData(a.criado_em) },
  ]
  const acoesLinha = (a) => (
    <button className="btn-secundario btn-mini" onClick={() => abrir(a)}>
      {a.precisa_correcao ? 'Corrigir' : 'Ver'}</button>
  )

  return (
    <>
      {msg && <div className={msg.tipo === 'erro' ? 'alerta' : 'sucesso'}>{msg.texto}</div>}
      {!apps ? <p>Carregando…</p> : (
        <DashPlanilha id="prova-aplicacoes" colunas={colunas} dados={apps}
                      acoesLinha={acoesLinha} vazio="Nenhuma prova aplicada ainda." />
      )}
    </>
  )
}

// Relatório de comportamento (telemetria coletada durante a prova). Os dados
// SEMPRE foram coletados; agora aparecem no RH (dash + este detalhe). Um número
// alto de saídas/print/cópia sugere prova comprometida — mas é só INDÍCIO, o RH
// decide. NÃO é nota.
function RelatorioComportamento({ c }) {
  if (!c) return (
    <div className="rh-card">
      <h3>🖥️ Comportamento na tela</h3>
      <p className="explica">Sem telemetria registrada nesta aplicação.</p>
    </div>
  )
  const linhas = [
    ['Saídas da tela (trocou de aba/app)', c.saidas_da_tela, c.saidas_da_tela > 0],
    ['Tempo fora da tela', c.segundos_fora_da_tela ? `${c.segundos_fora_da_tela}s` : '0s', c.segundos_fora_da_tela > 0],
    ['Tentativas de print', c.tentativas_print, c.tentativas_print > 0],
    ['Copiar / colar / recortar', c.copiar_colar, c.copiar_colar > 0],
    ['Quedas de conexão', c.quedas_de_conexao, c.quedas_de_conexao > 0],
  ]
  const limpo = !(c.saidas_da_tela || c.tentativas_print || c.copiar_colar)
  return (
    <div className="rh-card">
      <h3>🖥️ Comportamento na tela {limpo
        ? <span className="chip" style={{ '--chip-cor': '#0fb257' }}>✓ sem sinais</span>
        : <span className="chip" style={{ '--chip-cor': '#d9534f' }}>⚠️ requer atenção</span>}</h3>
      <p className="explica">Registrado durante a prova — <strong>indício</strong>, não prova de
        fraude. {c.total_eventos} evento(s) capturado(s).</p>
      <table className="rh-tabela">
        <tbody>
          {linhas.map(([rot, val, alerta]) => (
            <tr key={rot}>
              <td>{rot}</td>
              <td style={{ fontWeight: 700, color: alerta ? '#d9534f' : 'inherit' }}>{val ?? 0}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

// Detalhe + correção de uma aplicação: RH vê as objetivas (com acerto) e pontua
// as discursivas (0-100). A nota final é recalculada no servidor.
function Correcao({ aplicacao, aoVoltar }) {
  const [a] = useState(aplicacao)
  const [notas, setNotas] = useState(() => {
    const init = {}
    for (const q of a.questoes || []) if (q.tipo === 'discursiva') init[q.id] = q.correcao || {}
    return init
  })
  const [msg, setMsg] = useState(null)
  const [salvo, setSalvo] = useState(a.nota_final)

  const setNota = (qid, campo, v) => setNotas((n) => ({ ...n, [qid]: { ...n[qid], [campo]: v } }))

  const salvar = async () => {
    const correcao = {}
    for (const [qid, c] of Object.entries(notas)) {
      correcao[qid] = { nota: c.nota === '' || c.nota == null ? null : Number(c.nota),
                        comentario: c.comentario || '' }
    }
    try {
      const r = await api.corrigirProva(a.id, correcao)
      setSalvo(r.nota_final)
      setMsg({ tipo: 'ok', texto: `Correção salva. Nota final: ${r.nota_final ?? '—'}.` })
    } catch (e) { setMsg({ tipo: 'erro', texto: `Falha ao salvar (${e.detail || e.message}).` }) }
  }

  return (
    <>
      <div className="rh-card rh-lote">
        <button className="btn-link" onClick={aoVoltar}>← Voltar às aplicações</button>
        <span className="dash-espaco" style={{ flex: 1 }} />
        <span className="explica" style={{ margin: 0 }}>Objetivas: <strong>{a.nota_objetivas ?? '—'}</strong>
          {' · '}Final: <strong>{salvo ?? '—'}</strong></span>
      </div>
      {msg && <div className={msg.tipo === 'erro' ? 'alerta' : 'sucesso'}>{msg.texto}</div>}

      <RelatorioComportamento c={a.comportamento} />

      <div className="rh-card">
        <h3>{a.nome} — {a.prova_titulo}</h3>
        {(a.questoes || []).map((q, i) => (
          <div key={q.id} className="prova-questao">
            <strong>{i + 1}. {q.tipo === 'objetiva' ? '☑' : '✎'} {q.enunciado}</strong>
            {q.tipo === 'objetiva' ? (
              <ul className="prova-opcoes">
                {(q.opcoes || []).map((o) => {
                  const certa = o.id === q.gabarito
                  const escolhida = o.id === q.escolha
                  return (
                    <li key={o.id} className={certa ? 'certa' : ''}>
                      {certa ? '✔ ' : ''}{escolhida ? '➡ ' : ''}{o.texto}
                      {escolhida && !certa && <span style={{ color: '#d9534f' }}> (marcou)</span>}
                    </li>
                  )
                })}
              </ul>
            ) : (
              <div className="prova-correcao">
                <p className="prova-resposta-txt">{q.resposta || <em>(sem resposta)</em>}</p>
                <div className="linha2">
                  <label className="campo" style={{ maxWidth: 140 }}><span className="rotulo">Nota (0–100)</span>
                    <input type="number" min={0} max={100} value={notas[q.id]?.nota ?? ''}
                           onChange={(e) => setNota(q.id, 'nota', e.target.value)} /></label>
                  <label className="campo"><span className="rotulo">Comentário (opcional)</span>
                    <input value={notas[q.id]?.comentario ?? ''}
                           onChange={(e) => setNota(q.id, 'comentario', e.target.value)} /></label>
                </div>
              </div>
            )}
            <small className="explica" style={{ margin: 0 }}>Peso {q.peso}</small>
          </div>
        ))}
        {(a.questoes || []).some((q) => q.tipo === 'discursiva') && (
          <button className="btn-principal btn-mini" onClick={salvar}>Salvar correção</button>
        )}
      </div>
    </>
  )
}
