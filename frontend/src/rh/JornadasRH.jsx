import { useEffect, useRef, useState } from 'react'
import { rh as api } from '../api.js'
import { comAmpulheta } from '../Carregando.jsx'
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
  const inputPlanilha = useRef(null)

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

  const importar = async (arquivo) => {
    if (!arquivo) return
    setMsg(null)
    try {
      const r = await comAmpulheta('Importando jornadas da planilha…',
                                   () => api.importarJornadasPlanilha(arquivo))
      setMsg({ tipo: 'ok', texto: `Importação concluída: ${r.criadas} nova(s), `
        + `${r.puladas} já existente(s) (de ${r.total_planilha} linhas). `
        + 'Confira a estruturação proposta na aba "A confirmar".' })
      recarregar(); setDups(null)
    } catch (e) {
      setMsg({ tipo: 'erro', texto: e.detail === 'sem_coluna_jornada'
        ? 'A planilha precisa da coluna "Jornada de Trabalho".'
        : `Falha ao importar (${e.detail || e.message}).` })
    } finally { if (inputPlanilha.current) inputPlanilha.current.value = '' }
  }

  const salvarPosto = async (j, postoId) => {
    try { await api.editarJornada(j.id, { descricao: j.descricao, posto_servico_id: postoId || null }); recarregar() }
    catch (e) { setMsg({ tipo: 'erro', texto: `Não foi possível vincular o posto (${e.detail || e.message}).` }) }
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
      sempreVisivel: true,
      render: (j) => (<><strong>{j.descricao}</strong>{!j.estruturado &&
        <span title="Estrutura ainda não confirmada pelo RH"> ⚠️</span>}</>) },
    { chave: 'posto', rotulo: 'Posto', filtro: 'texto', valor: (j) => postoNome(j.posto_servico_id),
      render: (j) => (
        <SelectBusca style={{ minWidth: 160 }} vazioRotulo="— sem posto —" placeholder="Buscar posto…"
          valor={j.posto_servico_id || ''} aoEscolher={(v) => salvarPosto(j, v)}
          opcoes={postos.map((p) => ({ valor: p.id, rotulo: p.nome }))} />) },
    { chave: 'escala', rotulo: 'Escala', ordenavel: true, filtro: 'select',
      opcoes: ESCALAS, valor: (j) => ESCALA_ROT[j.escala] || '' },
    { chave: 'horarios', rotulo: 'Horários', valor: (j) =>
        [j.hora_entrada, j.saida_almoco, j.volta_almoco, j.hora_saida].filter(Boolean).join(' · ') },
    { chave: 'turno', rotulo: 'Turno', filtro: 'select', oculta: true,
      opcoes: [{ v: 'diurno', r: 'Diurno' }, { v: 'noturno', r: 'Noturno' }], valor: (j) => j.turno || '' },
    { chave: 'adicional_noturno', rotulo: 'Ad. noturno', filtro: 'select',
      opcoes: [{ v: 'Sim', r: 'Sim' }, { v: '—', r: 'Não' }], valor: (j) => simNao(j.adicional_noturno) },
    { chave: 'tem_intrajornada', rotulo: 'Intrajornada', filtro: 'select',
      opcoes: [{ v: 'Sim', r: 'Sim' }, { v: '—', r: 'Não' }],
      valor: (j) => simNao(j.tem_intrajornada),
      render: (j) => j.tem_intrajornada
        ? <span title={j.intrajornada_obs || ''}>Sim{j.intrajornada_obs ? ` (${j.intrajornada_obs})` : ''}</span> : '—' },
    { chave: 'cargo_relacionado', rotulo: 'Cargo', filtro: 'texto', oculta: true, valor: (j) => j.cargo_relacionado || '' },
    { chave: 'estruturado', rotulo: 'Estrutura', filtro: 'select',
      opcoes: [{ v: 'Confirmada', r: 'Confirmada' }, { v: 'A confirmar', r: 'A confirmar' }],
      valor: (j) => (j.estruturado ? 'Confirmada' : 'A confirmar'),
      render: (j) => j.estruturado
        ? <span className="chip" style={{ '--chip-cor': '#0fb257' }}>✓ Confirmada</span>
        : <span className="chip" style={{ '--chip-cor': '#e9a63a' }}>A confirmar</span> },
  ]

  const acoesLinha = (j) => (
    <button className="btn-secundario btn-mini" onClick={() => excluir(j)}>Excluir</button>)

  const aConfirmar = (jornadas || []).filter((j) => !j.estruturado).length

  return (
    <main className="rh-painel">
      <header className="rh-topo">
        {aoVoltar && <button className="btn-link" onClick={aoVoltar}>← Voltar</button>}
        <h1>🕒 Jornadas</h1>
        <div>
          <input ref={inputPlanilha} type="file" accept=".xlsx" hidden
                 onChange={(e) => importar(e.target.files?.[0])} />
          <button className="btn-secundario btn-mini" onClick={() => inputPlanilha.current?.click()}>
            ⬆ Importar da planilha</button>
        </div>
      </header>
      <p className="explica">A <strong>descrição</strong> é o texto que vai ao Tirvu (não muda o
        formato). Os demais campos são <strong>estrutura interna</strong> — o parser propõe na
        importação e você confirma. Vincule cada jornada ao seu posto.</p>

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
      ) : (
        <DashPlanilha id="jornadas" colunas={colunas} dados={jornadas} acoesLinha={acoesLinha}
                      vazio="Nenhuma jornada. Importe da planilha ou crie manualmente." />
      )}
    </main>
  )
}

// --- Aba "A confirmar": mostra a proposta do parser p/ o RH confirmar/corrigir ---
function Confirmar({ jornadas, postos, onConfirmou, setMsg }) {
  const [edit, setEdit] = useState(null)   // {id, campos...}
  const [prop, setProp] = useState(null)

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
  return (
    <table className="rh-tabela">
      <thead><tr><th>Jornada</th><th>Proposta do parser</th><th></th></tr></thead>
      <tbody>
        {jornadas.map((j) => (
          <tr key={j.id}>
            <td><strong>{j.descricao}</strong></td>
            <td>
              {edit?.id === j.id && prop ? (
                <div className="rh-lote" style={{ flexWrap: 'wrap', gap: '.4rem' }}>
                  <select value={prop.escala || ''} onChange={(e) => setProp({ ...prop, escala: e.target.value || null })}>
                    <option value="">— escala —</option>
                    {ESCALAS.map((es) => <option key={es.v} value={es.v}>{es.r}</option>)}
                  </select>
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
    <p className="explica">Pares parecidos — <strong>o sistema não funde sozinho</strong>. Confira e
      decida: são a mesma jornada (grafia diferente) ou realmente diferentes?</p>
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
  </>)
}
