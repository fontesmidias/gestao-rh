import { useEffect, useState } from 'react'
import { rh as api } from '../api.js'
import { fmtData } from '../fmt.js'
import DashPlanilha from './DashPlanilha.jsx'

// Módulo de PROVAS por cargo: o RH monta provas (objetivas com gabarito +
// discursivas), gera link de aplicação e corrige. Duas visões: Editor e
// Aplicações (dash-planilha com correção). O gabarito nunca vai ao candidato.
export default function ProvasRH() {
  const [visao, setVisao] = useState('editor')  // editor | aplicacoes
  return (
    <>
      <div className="rh-card rh-lote" style={{ gap: '.4rem' }}>
        <button className={`btn-mini ${visao === 'editor' ? 'btn-principal' : 'btn-secundario'}`}
                onClick={() => setVisao('editor')}>📝 Provas</button>
        <button className={`btn-mini ${visao === 'aplicacoes' ? 'btn-principal' : 'btn-secundario'}`}
                onClick={() => setVisao('aplicacoes')}>📊 Aplicações & correção</button>
      </div>
      {visao === 'editor' ? <Editor /> : <Aplicacoes />}
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

  const recarregar = async () => { const d = await api.provaDetalhe(p.id); setP(d) }

  const salvarMeta = async () => {
    try {
      await api.editarProva(p.id, { titulo: p.titulo, cargo: p.cargo, descricao: p.descricao,
        tempo_segundos: p.tempo_segundos, ativa: p.ativa })
      setMsg({ tipo: 'ok', texto: 'Prova salva.' })
    } catch (e) { setMsg({ tipo: 'erro', texto: `Falha ao salvar (${e.detail || e.message}).` }) }
  }
  const excluirQ = async (q) => {
    if (!window.confirm('Excluir esta questão?')) return
    try { await api.excluirQuestao(p.id, q.id); await recarregar() }
    catch (e) { setMsg({ tipo: 'erro', texto: `Falha (${e.detail || e.message}).` }) }
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
        <button className="btn-principal btn-mini" onClick={salvarMeta}>Salvar dados da prova</button>
      </div>

      <div className="rh-card">
        <h3>Questões ({p.questoes?.length || 0})</h3>
        {(p.questoes || []).map((q, i) => (
          <QuestaoItem key={q.id} n={i + 1} provaId={p.id} questao={q}
                       aoSalvar={recarregar} aoExcluir={() => excluirQ(q)} />
        ))}
        {nova
          ? <QuestaoNova provaId={p.id} tipoInicial={nova}
                         aoSalvar={() => { setNova(null); recarregar() }}
                         aoCancelar={() => setNova(null)} />
          : (
            <div className="rh-lote" style={{ marginTop: '.6rem' }}>
              <button className="btn-secundario btn-mini" onClick={() => setNova('objetiva')}>+ Questão objetiva</button>
              <button className="btn-secundario btn-mini" onClick={() => setNova('discursiva')}>+ Questão discursiva</button>
            </div>
          )}
      </div>
    </>
  )
}

function QuestaoItem({ n, provaId, questao, aoSalvar, aoExcluir }) {
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
  const [erro, setErro] = useState(null)

  const letra = (i) => String.fromCharCode(97 + i)
  const setOpcao = (i, texto) => setOpcoes((os) => os.map((o, j) => j === i ? { ...o, texto } : o))
  const addOpcao = () => setOpcoes((os) => [...os, { id: letra(os.length), texto: '' }])
  const removeOpcao = (i) => setOpcoes((os) => os.length > 2 ? os.filter((_, j) => j !== i) : os)

  const salvar = async () => {
    if (!enunciado.trim()) { setErro('Escreva o enunciado.'); return }
    const dados = { enunciado, tipo, peso: parseInt(peso, 10) || 1 }
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
