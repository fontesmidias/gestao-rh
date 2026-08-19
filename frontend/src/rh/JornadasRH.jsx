import { useEffect, useState } from 'react'
import { rh as api } from '../api.js'
import DashPlanilha from './DashPlanilha.jsx'
import SelectBusca from '../SelectBusca.jsx'

// Página dedicada de Jornadas: a `descricao` é canônica (vai ao Tirvu como
// texto único, sem mudar o formato). Os campos estruturados (escala, horários,
// intrajornada, adicional noturno) são METADADOS internos — propostos pelo
// parser na importação e CONFIRMADOS pelo RH (nunca auto). Duplicidades são só
// sinalizadas (regra dos ~40 erros de digitação — nunca fundir sozinho).
const ESCALAS = [
  { v: 'seg-sex', r: 'Seg a Sex' }, { v: '12x36', r: '12x36' },
  { v: '5x2', r: '5x2' }, { v: 'seg-qui+sex', r: 'Seg-Qui + Sex difere' },
  { v: 'intermitente', r: 'Intermitente' },
]
const ESCALA_ROT = Object.fromEntries(ESCALAS.map((e) => [e.v, e.r]))
const simNao = (v) => (v ? 'Sim' : '—')

export default function JornadasRH({ aoVoltar }) {
  const [aba, setAba] = useState('lista')
  const [jornadas, setJornadas] = useState(null)
  const [postos, setPostos] = useState([])
  const [dups, setDups] = useState(null)
  const [msg, setMsg] = useState(null)
  const [criando, setCriando] = useState(false)

  const recarregar = () => api.jornadas().then(setJornadas).catch(() => setJornadas([]))
  useEffect(() => {
    recarregar()
    api.postos().then((r) => setPostos(r.postos || [])).catch(() => {})
  }, [])
  useEffect(() => {
    if (aba === 'duplicidades' && dups === null) {
      api.jornadasDuplicidades().then(setDups).catch(() => setDups([]))
    }
  }, [aba, dups])

  const postoNome = (id) => postos.find((p) => p.id === id)?.nome || '—'

  const salvarPosto = async (j, postoId) => {
    try { await api.editarJornada(j.id, { descricao: j.descricao, posto_servico_id: postoId || null, tirvu_id: j.tirvu_id || null }); recarregar() }
    catch (e) { setMsg({ tipo: 'erro', texto: `Não foi possível vincular o posto (${e.detail || e.message}).` }) }
  }
  const salvarTirvuId = async (j, tid) => {
    const novo = (tid || '').trim()
    if (novo === (j.tirvu_id || '')) return
    try {
      await api.editarJornada(j.id, { descricao: j.descricao, posto_servico_id: j.posto_servico_id || null, tirvu_id: novo || null })
      recarregar()
    } catch (e) { setMsg({ tipo: 'erro', texto: `Não foi possível salvar o ID Tirvu (${e.detail || e.message}).` }) }
  }
  // Criar jornada à mão. A rota é IDEMPOTENTE por descrição (case-insensitive):
  // se já existe, ela devolve a existente com 201 em vez de erro. Sem avisar,
  // o RH acha que criou uma segunda e fica procurando a duplicata na lista.
  const criar = async (dados) => {
    const antes = (jornadas || []).length
    const nova = await api.criarJornada(dados)
    const lista = await api.jornadas()
    setJornadas(lista)
    setCriando(false)
    setMsg(lista.length > antes
      ? { tipo: 'ok', texto: `Jornada "${nova.descricao}" criada.` }
      : { tipo: 'ok', texto: `Esta jornada já existia ("${nova.descricao}") — nada foi duplicado.` })
  }

  const excluir = async (j) => {
    if (!window.confirm(`Excluir a jornada "${j.descricao}"?`)) return
    try { await api.excluirJornada(j.id); recarregar() }
    catch (e) {
      setMsg({ tipo: 'erro', texto: e.detail === 'jornada_em_uso'
        ? 'Esta jornada está em uso por algum colaborador — desative ou reatribua antes.'
        : `Não foi possível excluir (${e.detail || e.message}).` })
    }
  }

  const colunas = [
    { chave: 'descricao', rotulo: 'Jornada (texto do Tirvu)', ordenavel: true, filtro: 'texto',
      sempreVisivel: true, quebra: true,
      render: (j) => (<><strong>{j.descricao}</strong>{!j.estruturado &&
        <span title="Estrutura ainda não confirmada pelo RH"> ⚠️</span>}</>) },
    { chave: 'posto', rotulo: 'Posto', filtro: 'lista', valor: (j) => postoNome(j.posto_servico_id),
      render: (j) => (
        <SelectBusca style={{ minWidth: 160 }} vazioRotulo="— sem posto —" placeholder="Buscar posto…"
          valor={j.posto_servico_id || ''} aoEscolher={(v) => salvarPosto(j, v)}
          opcoes={postos.map((p) => ({ valor: p.id, rotulo: p.nome }))} />) },
    { chave: 'tirvu_id', rotulo: 'ID Tirvu', filtro: 'texto', valor: (j) => j.tirvu_id || '',
      render: (j) => (
        <input style={{ maxWidth: '5.5rem' }} placeholder="ex.: 246" defaultValue={j.tirvu_id || ''}
               key={j.tirvu_id || ''} onBlur={(e) => salvarTirvuId(j, e.target.value)}
               className={j.tirvu_id ? '' : 'campo-pendente'}
               title="Código desta jornada na base do Tirvu — a importação de admissões casa por ele" />) },
    { chave: 'escala', rotulo: 'Escala', ordenavel: true, filtro: 'select',
      opcoes: ESCALAS, valor: (j) => ESCALA_ROT[j.escala] || '' },
    { chave: 'horarios', rotulo: 'Horários', valor: (j) =>
        [j.hora_entrada, j.saida_almoco, j.volta_almoco, j.hora_saida].filter(Boolean).join(' · ') },
    { chave: 'turno', rotulo: 'Turno', filtro: 'select', oculta: true,
      opcoes: [{ v: 'diurno', r: 'Diurno' }, { v: 'noturno', r: 'Noturno' }], valor: (j) => j.turno || '' },
    // Ocultas por padrão (v2.62): são Sim/Não que já se FILTRAM na barra do
    // dash, e a tabela tem 8 colunas — estourava a tela em 1200px. Continuam
    // a um clique em "⚙ Colunas".
    { chave: 'adicional_noturno', rotulo: 'Ad. noturno', filtro: 'select', oculta: true,
      opcoes: [{ v: 'Sim', r: 'Sim' }, { v: '—', r: 'Não' }], valor: (j) => simNao(j.adicional_noturno) },
    { chave: 'tem_intrajornada', rotulo: 'Intrajornada', filtro: 'select', oculta: true,
      opcoes: [{ v: 'Sim', r: 'Sim' }, { v: '—', r: 'Não' }],
      valor: (j) => simNao(j.tem_intrajornada),
      render: (j) => j.tem_intrajornada
        ? <span title={j.intrajornada_obs || ''}>Sim{j.intrajornada_obs ? ` (${j.intrajornada_obs})` : ''}</span> : '—' },
    { chave: 'cargo_relacionado', rotulo: 'Cargo', filtro: 'lista', oculta: true, valor: (j) => j.cargo_relacionado || '' },
    { chave: 'estruturado', rotulo: 'Estrutura', filtro: 'select',
      opcoes: [{ v: 'Confirmada', r: 'Confirmada' }, { v: 'A confirmar', r: 'A confirmar' }],
      valor: (j) => (j.estruturado ? 'Confirmada' : 'A confirmar'),
      render: (j) => j.estruturado
        ? <span className="chip" style={{ '--chip-cor': 'var(--verde-vivo)' }}>✓ Confirmada</span>
        : <span className="chip" style={{ '--chip-cor': '#e9a63a' }}>A confirmar</span> },
  ]

  const acoesLinha = (j) => (
    <button className="btn-secundario btn-mini" onClick={() => excluir(j)}>Excluir</button>)

  const aConfirmar = (jornadas || []).filter((j) => !j.estruturado).length
  // cards clicáveis: total, a-confirmar, 12x36, noturno (filtram a lista)
  const cards = (jornadas || []).length ? [
    { rotulo: 'Total', valor: jornadas.length },
    { rotulo: 'A confirmar', valor: aConfirmar, cor: '#e9a63a',
      filtro: { chave: 'estruturado', valor: 'A confirmar' } },
    { rotulo: '12x36', valor: jornadas.filter((j) => j.escala === '12x36').length, cor: '#5b7',
      filtro: { chave: 'escala', valor: ESCALA_ROT['12x36'] } },
    { rotulo: 'Noturnas', valor: jornadas.filter((j) => j.adicional_noturno).length, cor: '#8a6d3b',
      filtro: { chave: 'adicional_noturno', valor: 'Sim' } },
  ] : null

  return (
    <main className="rh-painel">
      <header className="rh-topo">
        {aoVoltar && <button className="btn-link" onClick={aoVoltar}>← Voltar</button>}
        <h1>🕒 Jornadas</h1>
        <div />
      </header>
      <p className="explica">A <strong>descrição</strong> é o texto que vai ao Tirvu (não muda o
        formato). Os demais campos são <strong>estrutura interna</strong> — o parser propõe na
        importação e você confirma. Vincule cada jornada ao seu posto. Para importar da planilha
        de colaboradores em massa, veja <strong>Configurações → 📥 Importações</strong>.</p>

      <div className="rh-lote" style={{ marginBottom: '.6rem' }}>
        <button className={aba === 'lista' ? 'btn-principal btn-mini' : 'btn-secundario btn-mini'}
                onClick={() => setAba('lista')}>Todas ({jornadas?.length || 0})</button>
        <button className={aba === 'confirmar' ? 'btn-principal btn-mini' : 'btn-secundario btn-mini'}
                onClick={() => setAba('confirmar')}>A confirmar ({aConfirmar})</button>
        <button className={aba === 'duplicidades' ? 'btn-principal btn-mini' : 'btn-secundario btn-mini'}
                onClick={() => setAba('duplicidades')}>Duplicidades suspeitas</button>
      </div>

      {msg && <div className={msg.tipo === 'erro' ? 'alerta' : 'sucesso'}>{msg.texto}</div>}

      {!jornadas ? <p>Carregando…</p> : aba === 'duplicidades' ? (
        <Duplicidades dups={dups} onMudou={() => { recarregar(); setDups(null) }} setMsg={setMsg} />
      ) : aba === 'confirmar' ? (
        <Confirmar jornadas={jornadas.filter((j) => !j.estruturado)} postos={postos}
                   onConfirmou={recarregar} setMsg={setMsg} />
      ) : (<>
        {/* Criar fica FORA do card de filtros (v2.76.1: nada que CRIA mora em
            bloco que se recolhe) e abre perto da lista, não no topo da tela. */}
        {criando && <NovaJornada postos={postos} aoCriar={criar}
                                 aoCancelar={() => setCriando(false)} setMsg={setMsg} />}
        <DashPlanilha id="jornadas" colunas={colunas} dados={jornadas} cards={cards}
                      acoesLinha={acoesLinha}
                      acoesFiltro={!criando && (
                        <button className="btn-secundario btn-mini"
                                onClick={() => setCriando(true)}>＋ Nova jornada</button>)}
                      vazio="Nenhuma jornada. Importe da planilha ou crie aqui em “＋ Nova jornada”." />
      </>)}
    </main>
  )
}

// --- Criar jornada à mão -----------------------------------------------------
// A rota `POST /rh/jornadas` existia desde sempre e a tela NUNCA a chamava — o
// texto de lista vazia já dizia "crie manualmente" sem haver por onde. Só a
// DESCRIÇÃO é pedida aqui: ela é o texto canônico que vai ao Tirvu, e a
// estrutura (escala, horários) é proposta pelo parser e confirmada depois, na
// aba "A confirmar" — pedir tudo agora inverteria esse fluxo.
function NovaJornada({ postos, aoCriar, aoCancelar, setMsg }) {
  const [descricao, setDescricao] = useState('')
  const [postoId, setPostoId] = useState('')
  const [tirvuId, setTirvuId] = useState('')
  const [salvando, setSalvando] = useState(false)

  const salvar = async () => {
    const desc = descricao.trim()
    if (!desc) { setMsg({ tipo: 'erro', texto: 'Informe a descrição da jornada.' }); return }
    setSalvando(true)
    try {
      await aoCriar({ descricao: desc, posto_servico_id: postoId || null,
                      tirvu_id: tirvuId.trim() || null })
    } catch (e) {
      setMsg({ tipo: 'erro', texto: `Não foi possível criar (${e.detail || e.message}).` })
    } finally { setSalvando(false) }
  }

  return (
    <div className="rh-card" style={{ marginBottom: '.6rem' }}>
      <h3>＋ Nova jornada</h3>
      <p className="explica">A <strong>descrição</strong> é o texto que vai ao Tirvu — escreva
        exatamente como ele deve aparecer lá. A estrutura (escala, horários) é proposta
        automaticamente e fica para você confirmar na aba <strong>A confirmar</strong>.</p>
      <div className="linha3">
        <label className="campo"><span className="rotulo">Descrição da jornada</span>
          <input value={descricao} autoFocus placeholder="ex.: 12X36 DIURNO 07:00 AS 19:00"
                 onChange={(e) => setDescricao(e.target.value)} /></label>
        <label className="campo"><span className="rotulo">Posto (opcional)</span>
          <SelectBusca valor={postoId} aoEscolher={setPostoId} vazioRotulo="— sem posto —"
                       placeholder="Buscar posto…"
                       opcoes={postos.map((p) => ({ valor: p.id, rotulo: p.nome }))} /></label>
        <label className="campo"><span className="rotulo">ID Tirvu (opcional)</span>
          <input value={tirvuId} placeholder="ex.: 246"
                 onChange={(e) => setTirvuId(e.target.value)} /></label>
      </div>
      <div className="rh-lote" style={{ marginTop: '.6rem' }}>
        <button className="btn-principal btn-mini" disabled={salvando} onClick={salvar}>
          {salvando ? 'Criando…' : 'Criar jornada'}</button>
        <button className="btn-secundario btn-mini" disabled={salvando} onClick={aoCancelar}>
          Cancelar</button>
      </div>
    </div>
  )
}

// --- Aba "A confirmar": mostra a proposta do parser p/ o RH confirmar/corrigir ---
function Confirmar({ jornadas, postos, onConfirmou, setMsg }) {
  const [edit, setEdit] = useState(null)   // {id, campos...}
  const [prop, setProp] = useState(null)
  // Confiança da proposta por jornada (v2.13). Medido nos dados reais: 86%
  // saem com confiança ALTA — confirmar uma a uma são 325 cliques para nada.
  const [resumo, setResumo] = useState(null)
  const [confirmando, setConfirmando] = useState(false)

  useEffect(() => {
    api.jornadasAConfirmar().then(setResumo).catch(() => setResumo(null))
  }, [jornadas.length])

  const confirmarAlta = async () => {
    const n = resumo?.por_confianca?.alta || 0
    if (!window.confirm(`Confirmar a estrutura de ${n} jornada(s) de alta confiança?\n\n`
      + 'Isso preenche só os campos internos (escala, horários). A descrição — a que '
      + 'vai ao Tirvu — não muda, e você pode reeditar qualquer uma depois.')) return
    setConfirmando(true); setMsg(null)
    try {
      const r = await api.confirmarJornadasLote({ confianca: 'alta' })
      setMsg({ tipo: 'ok', texto: `${r.confirmadas} confirmada(s). `
        + `${r.ignoradas} ficaram para revisão individual — são as que o parser não `
        + 'entendeu por completo.' })
      onConfirmou()
    } catch (e) {
      setMsg({ tipo: 'erro', texto: `Falha ao confirmar em lote (${e.detail || e.message}).` })
    } finally { setConfirmando(false) }
  }

  const abrir = async (j) => {
    const r = await api.propostaJornada(j.id)
    const p = r.proposta
    setEdit({ id: j.id, descricao: j.descricao, posto_servico_id: j.posto_servico_id })
    setProp(p)
  }
  const confirmar = async () => {
    try {
      await api.editarJornada(edit.id, {
        descricao: edit.descricao, posto_servico_id: edit.posto_servico_id,
        escala: prop.escala, hora_entrada: prop.hora_entrada, saida_almoco: prop.saida_almoco,
        volta_almoco: prop.volta_almoco, hora_saida: prop.hora_saida,
        bloco_secundario: prop.bloco_secundario, turno: prop.turno,
        adicional_noturno: prop.adicional_noturno, tem_intrajornada: prop.tem_intrajornada,
        intrajornada_obs: prop.intrajornada_obs, cargo_relacionado: prop.cargo_relacionado,
      }, { confirmarEstrutura: true })
      setEdit(null); setProp(null); onConfirmou()
    } catch (e) { setMsg({ tipo: 'erro', texto: `Falha ao confirmar (${e.detail || e.message}).` }) }
  }

  if (!jornadas.length) return <p className="explica centro">Tudo confirmado. 🎉</p>
  const alta = resumo?.por_confianca?.alta || 0
  return (
    <>
    {alta > 0 && (
      <div className="aviso-inline">
        <strong>{alta}</strong> de {resumo.total} têm a estrutura reconhecida por completo
        (escala e os quatro horários). As outras {resumo.total - alta} o parser leu só em
        parte e pedem o seu olho.
        <div style={{ marginTop: '.5rem' }}>
          <button className="btn-principal btn-mini" onClick={confirmarAlta} disabled={confirmando}>
            {confirmando ? 'Confirmando…' : `✓ Confirmar as ${alta} de alta confiança`}</button>
        </div>
      </div>
    )}
    <div className="dash-scroll">
      <table className="rh-tabela">
        <thead><tr><th>Jornada</th><th>Proposta do parser</th><th></th></tr></thead>
        <tbody>
          {jornadas.map((j) => (
            <tr key={j.id}>
              <td><strong>{j.descricao}</strong></td>
              <td>
                {edit?.id === j.id && prop ? (
                  <div className="rh-lote" style={{ flexWrap: 'wrap', gap: '.4rem' }}>
                    <SelectBusca valor={prop.escala || ''} aoEscolher={(v) => setProp({ ...prop, escala: v || null })}>
                      <option value="">— escala —</option>
                      {ESCALAS.map((es) => <option key={es.v} value={es.v}>{es.r}</option>)}
                    </SelectBusca>
                    {['hora_entrada', 'saida_almoco', 'volta_almoco', 'hora_saida'].map((k) => (
                      <input key={k} style={{ width: 70 }} placeholder={k.split('_')[0]} value={prop[k] || ''}
                             onChange={(e) => setProp({ ...prop, [k]: e.target.value || null })} />))}
                    <label className="explica" style={{ margin: 0, display: 'flex', gap: '.3rem', alignItems: 'center' }}>
                      <input type="checkbox" checked={!!prop.adicional_noturno}
                             onChange={(e) => setProp({ ...prop, adicional_noturno: e.target.checked, turno: e.target.checked ? 'noturno' : 'diurno' })} /> noturno</label>
                    <label className="explica" style={{ margin: 0, display: 'flex', gap: '.3rem', alignItems: 'center' }}>
                      <input type="checkbox" checked={!!prop.tem_intrajornada}
                             onChange={(e) => setProp({ ...prop, tem_intrajornada: e.target.checked })} /> intrajornada</label>
                    {prop.tem_intrajornada && (
                      <input style={{ width: 120 }} placeholder="obs (15 MINUTOS)" value={prop.intrajornada_obs || ''}
                             onChange={(e) => setProp({ ...prop, intrajornada_obs: e.target.value || null })} />)}
                  </div>
                ) : (
                  <span className="explica" style={{ margin: 0 }}>clique em "Revisar" para ver e confirmar</span>
                )}
              </td>
              <td className="acoes-candidato">
                {edit?.id === j.id
                  ? (<><button className="btn-principal btn-mini" onClick={confirmar}>✓ Confirmar</button>
                       <button className="btn-link" onClick={() => { setEdit(null); setProp(null) }}>cancelar</button></>)
                  : <button className="btn-secundario btn-mini" onClick={() => abrir(j)}>Revisar</button>}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
    </>
  )
}

// --- Aba "Duplicidades": pares suspeitos lado a lado; o RH decide (nunca funde) ---
function Duplicidades({ dups, onMudou, setMsg }) {
  const fundir = async (manter, remover) => {
    // "são a mesma": mantém uma e exclui a outra (só se a removida não estiver em uso)
    if (!window.confirm(`Confirmar que são a MESMA jornada?\n\nManter: "${manter}"\nExcluir: "${remover}"`)) return
    try {
      const lista = await api.jornadas()
      const alvo = lista.find((j) => j.descricao === remover)
      if (alvo) await api.excluirJornada(alvo.id)
      setMsg({ tipo: 'ok', texto: 'Duplicata resolvida.' }); onMudou()
    } catch (e) {
      setMsg({ tipo: 'erro', texto: e.detail === 'jornada_em_uso'
        ? 'A jornada a excluir está em uso — reatribua os colaboradores antes.'
        : `Não foi possível resolver (${e.detail || e.message}).` })
    }
  }
  if (dups === null) return <p>Carregando…</p>
  if (!dups.length) return <p className="explica centro">Nenhuma duplicidade suspeita. 👍</p>
  return (<>
    {/* A lista encolheu de 199 para 3 na v2.12: horário diferente e cliente
        diferente deixaram de entrar aqui (eram 99% do que aparecia). O texto
        explica o critério para o RH não achar que "sumiu" duplicidade. */}
    <p className="explica">Pares que parecem ser <strong>a mesma jornada escrita de dois
      jeitos</strong> — só muda pontuação, espaço ou acento. <strong>O sistema não funde
      sozinho</strong>: confira e decida.</p>
    <p className="explica">Jornadas com <strong>horário diferente</strong> (uma sai 16h, outra
      17h) ou de <strong>clientes diferentes</strong> no mesmo horário não aparecem aqui —
      são jornadas distintas de verdade, não duplicidade.</p>
    <div className="dash-scroll">
      <table className="rh-tabela">
        <thead><tr><th>Jornada A</th><th>Jornada B</th><th>Semelhança</th><th></th></tr></thead>
        <tbody>
          {dups.map((d, i) => (
            <tr key={i}>
              <td>{d.a}</td><td>{d.b}</td>
              <td>{Math.round(d.similaridade * 100)}%
                {d.identicas_apos_normalizar && <span title="Iguais após ignorar acento/espaço/typo"> ✓</span>}</td>
              <td className="acoes-candidato">
                <button className="btn-secundario btn-mini" onClick={() => fundir(d.a, d.b)}>Manter A</button>
                <button className="btn-secundario btn-mini" onClick={() => fundir(d.b, d.a)}>Manter B</button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  </>)
}
