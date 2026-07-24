import { useEffect, useState } from 'react'
import { rh as api } from '../api.js'
import DashPlanilha from './DashPlanilha.jsx'
import SelectBusca from '../SelectBusca.jsx'
import Formulario from './FormularioAvaliacao.jsx'
import RadarCompetencias from './RadarCompetencias.jsx'

// Avaliação de Desempenho (Onda C) — o formulário da cartilha de 17/06/2026.
//
// A CONVERSA é o produto; o formulário é o registro dela. Por isso a máquina de
// estados não deixa pular o feedback presencial: rascunho → preenchida →
// feedback dado → (manifestação do colaborador) → homologada.
export default function AvaliacoesRH({ aoVoltar }) {
  const [aba, setAba] = useState('minhas')
  return (
    <section className="pagina">
      <div className="rh-topo">
        <h1>⭐ Avaliações</h1>
        <button className="btn-secundario btn-mini" onClick={aoVoltar}>← voltar</button>
      </div>
      <div className="rh-abas">
        <button className={aba === 'minhas' ? 'ativa' : ''} onClick={() => setAba('minhas')}>
          Minhas avaliações</button>
        <button className={aba === 'todas' ? 'ativa' : ''} onClick={() => setAba('todas')}>
          Homologação</button>
        <button className={aba === 'pessoa' ? 'ativa' : ''} onClick={() => setAba('pessoa')}>
          Por colaborador</button>
        <button className={aba === 'ciclos' ? 'ativa' : ''} onClick={() => setAba('ciclos')}>
          Ciclos</button>
      </div>
      {aba === 'ciclos' && <Ciclos />}
      {aba === 'pessoa' && <PorColaborador />}
      {(aba === 'minhas' || aba === 'todas') && <Lista somenteMinhas={aba === 'minhas'} />}
    </section>
  )
}

const ROTULO_STATUS = {
  rascunho: 'Rascunho', preenchida: 'Aguardando feedback',
  feedback_dado: 'Aguardando manifestação', manifestada: 'Pronta p/ homologar',
  homologada: 'Homologada', cancelada: 'Cancelada',
}
const COR_STATUS = {
  rascunho: '#889', preenchida: '#f5a623', feedback_dado: '#f5a623',
  manifestada: '#0a8f46', homologada: '#0a8f46', cancelada: '#e5484d',
}
const ROTULO_OCASIAO = {
  experiencia_30: 'Experiência 30d', experiencia_45: 'Experiência 45d',
  experiencia_60: 'Experiência 60d', experiencia_90: 'Experiência 90d',
  intermitente: 'Intermitente', periodica: 'Periódica',
  feedback_pontual: 'Feedback pontual', outro: 'Outro',
}
const ROTULO_RELACAO = {
  vertical: 'Vertical (liderança)', horizontal: 'Horizontal (par)',
  autoavaliacao: 'Autoavaliação',
}

function Lista({ somenteMinhas }) {
  const [dados, setDados] = useState(null)
  const [colaboradores, setColaboradores] = useState([])
  const [ciclos, setCiclos] = useState([])
  const [form, setForm] = useState(null)     // formulário da cartilha
  const [msg, setMsg] = useState(null)
  const [abrindo, setAbrindo] = useState(null)
  const [nova, setNova] = useState(false)

  const carregar = () => Promise.all([
    api.avaliacoes({ minhas: somenteMinhas ? 'true' : '' }),
    api.desempenhoColaboradores(), api.ciclos(), api.desempenhoFormulario(),
  ]).then(([a, col, ci, f]) => {
    setDados(a); setColaboradores(col.colaboradores); setCiclos(ci.ciclos); setForm(f)
  }).catch((e) => setMsg({ tipo: 'erro', texto: e.detail || e.message }))
  useEffect(() => { carregar() }, [somenteMinhas])

  if (!dados || !form) return <p className="explica">Carregando…</p>

  const colunas = [
    { chave: 'colaborador', rotulo: 'Colaborador', ordenavel: true, filtro: 'texto',
      sempreVisivel: true },
    { chave: 'cargo', rotulo: 'Cargo', filtro: 'texto', quebra: true, oculta: true },
    { chave: 'posto', rotulo: 'Posto', filtro: 'texto', quebra: true },
    { chave: 'ocasiao', rotulo: 'Ocasião', filtro: 'select',
      opcoes: Object.values(ROTULO_OCASIAO),
      valor: (l) => ROTULO_OCASIAO[l.ocasiao] || l.ocasiao },
    { chave: 'relacao', rotulo: 'Relação', filtro: 'select',
      opcoes: Object.values(ROTULO_RELACAO),
      valor: (l) => ROTULO_RELACAO[l.relacao] || l.relacao },
    { chave: 'avaliador', rotulo: 'Avaliador', filtro: 'texto', quebra: true },
    { chave: 'media', rotulo: 'Média', ordenavel: true,
      render: (l) => (l.media != null ? l.media.toFixed(2) : '—') },
    { chave: 'status', rotulo: 'Situação', filtro: 'select',
      opcoes: Object.values(ROTULO_STATUS),
      valor: (l) => ROTULO_STATUS[l.status] || l.status,
      render: (l) => <span className="chip" style={{ '--chip-cor': COR_STATUS[l.status] }}>
        {ROTULO_STATUS[l.status]}</span> },
  ]

  const m = dados.metricas
  const cards = [
    { rotulo: 'Rascunhos', valor: m.rascunho || 0, cor: '#889',
      filtro: { chave: 'status', valor: 'Rascunho' } },
    { rotulo: 'Aguardando feedback', valor: m.preenchida || 0, cor: '#f5a623',
      filtro: { chave: 'status', valor: 'Aguardando feedback' } },
    { rotulo: 'Prontas p/ homologar', valor: m.manifestada || 0, cor: '#0a8f46',
      filtro: { chave: 'status', valor: 'Pronta p/ homologar' } },
    { rotulo: 'Homologadas', valor: m.homologada || 0, cor: '#0a8f46',
      filtro: { chave: 'status', valor: 'Homologada' } },
  ]

  return (
    <>
      <p className="explica" style={{ marginTop: '.4rem' }}>
        {somenteMinhas
          ? 'As avaliações que você precisa preencher e dar o feedback.'
          : 'Todas as avaliações — é aqui que o RH homologa.'}
      </p>
      <Msg msg={msg} />

      {nova && (
        <NovaAvaliacao colaboradores={colaboradores} ciclos={ciclos}
                       aoFechar={() => { setNova(false); carregar() }}
                       aoErro={(t) => setMsg({ tipo: 'erro', texto: t })} />
      )}
      {!nova && somenteMinhas && (
        <button className="btn-principal btn-mini" style={{ marginBottom: '.8rem' }}
                onClick={() => setNova(true)}>＋ Nova avaliação</button>
      )}

      <DashPlanilha
        id={`avaliacoes-${somenteMinhas ? 'minhas' : 'todas'}`}
        colunas={colunas} dados={dados.avaliacoes} cards={cards}
        vazio="Nenhuma avaliação por aqui."
        linhaExpandida={(l) => (abrindo === l.id ? (
          <Formulario key={l.id} avaliacaoId={l.id} form={form}
                      homologando={!somenteMinhas}
                      aoFechar={() => { setAbrindo(null); carregar() }}
                      aoErro={(t) => setMsg({ tipo: 'erro', texto: t })} />
        ) : null)}
        acoesLinha={(l) => (
          <button className={`btn-${abrindo === l.id ? 'principal' : 'secundario'} btn-mini`}
                  onClick={() => setAbrindo(abrindo === l.id ? null : l.id)}>
            {abrindo === l.id ? 'Fechar' : 'Abrir'}</button>
        )} />
    </>
  )
}

function NovaAvaliacao({ colaboradores, ciclos, aoFechar, aoErro }) {
  const [f, setF] = useState({
    candidato_id: '', ciclo_id: ciclos[0] ? ciclos[0].id : '',
    relacao: 'vertical', ocasiao: 'periodica',
    periodo_inicio: '', periodo_fim: '',
  })
  const [salvando, setSalvando] = useState(false)
  return (
    <div className="rh-conferencia" style={{ marginBottom: '.8rem' }}>
      <div className="rh-conferencia-topo">
        <div>
          <h3>Nova avaliação</h3>
          <span className="explica">Os fatos registrados no período aparecem ao lado
            do formulário, para você não depender da memória.</span>
        </div>
        <button className="btn-secundario btn-mini" onClick={aoFechar}>✕ fechar</button>
      </div>
      <label className="campo"><span className="rotulo">Quem será avaliado</span>
        <SelectBusca valor={f.candidato_id} vazioRotulo="— escolha —"
                     placeholder="Buscar colaborador…"
                     opcoes={colaboradores.map((c) => ({
                       valor: c.id, rotulo: c.nome,
                       extra: [c.cargo, c.posto].filter(Boolean).join(' · ') }))}
                     aoEscolher={(v) => setF({ ...f, candidato_id: v })} /></label>
      <div className="linha2">
        <label className="campo"><span className="rotulo">Ocasião</span>
          <select value={f.ocasiao} onChange={(e) => setF({ ...f, ocasiao: e.target.value })}>
            {Object.entries(ROTULO_OCASIAO).map(([v, r]) =>
              <option key={v} value={v}>{r}</option>)}
          </select></label>
        <label className="campo"><span className="rotulo">Sua relação com a pessoa</span>
          <select value={f.relacao} onChange={(e) => setF({ ...f, relacao: e.target.value })}>
            {Object.entries(ROTULO_RELACAO).map(([v, r]) =>
              <option key={v} value={v}>{r}</option>)}
          </select></label>
      </div>
      <div className="linha2">
        <label className="campo"><span className="rotulo">Período avaliado — de</span>
          <input type="date" value={f.periodo_inicio}
                 onChange={(e) => setF({ ...f, periodo_inicio: e.target.value })} /></label>
        <label className="campo"><span className="rotulo">até</span>
          <input type="date" value={f.periodo_fim}
                 onChange={(e) => setF({ ...f, periodo_fim: e.target.value })} /></label>
      </div>
      {ciclos.length > 0 && (
        <label className="campo"><span className="rotulo">Ciclo</span>
          <select value={f.ciclo_id} onChange={(e) => setF({ ...f, ciclo_id: e.target.value })}>
            <option value="">— avulsa —</option>
            {ciclos.map((c) => <option key={c.id} value={c.id}>{c.nome}</option>)}
          </select></label>
      )}
      <div className="rh-conferencia-acoes">
        <button className="btn-principal btn-mini"
                disabled={salvando || !f.candidato_id}
                onClick={async () => {
                  setSalvando(true)
                  try { await api.criarAvaliacao(f); aoFechar() }
                  catch (e) { aoErro(e.detail || e.message) }
                  finally { setSalvando(false) }
                }}>{salvando ? 'Criando…' : 'Criar e preencher'}</button>
        <button className="btn-link" onClick={aoFechar}>cancelar</button>
      </div>
    </div>
  )
}

// --------------------------------------------------------------------------
// Por colaborador — radar (teia) + timeline
// --------------------------------------------------------------------------

function PorColaborador() {
  const [colaboradores, setColaboradores] = useState([])
  const [escolhido, setEscolhido] = useState('')
  const [radar, setRadar] = useState(null)
  const [historico, setHistorico] = useState([])
  const [msg, setMsg] = useState(null)

  useEffect(() => {
    api.desempenhoColaboradores().then((r) => setColaboradores(r.colaboradores))
      .catch((e) => setMsg({ tipo: 'erro', texto: e.detail || e.message }))
  }, [])

  useEffect(() => {
    if (!escolhido) { setRadar(null); setHistorico([]); return }
    Promise.all([api.radarColaborador(escolhido),
                 api.avaliacoes({ candidato_id: escolhido })])
      .then(([r, a]) => { setRadar(r); setHistorico(a.avaliacoes) })
      .catch((e) => setMsg({ tipo: 'erro', texto: e.detail || e.message }))
  }, [escolhido])

  const pessoa = colaboradores.find((c) => c.id === escolhido)
  const comNota = historico.filter((h) => h.media != null && h.status !== 'rascunho')

  return (
    <>
      <p className="explica" style={{ marginTop: '.4rem' }}>
        A trajetória de uma pessoa: onde ela está forte, onde precisa desenvolver, e
        como isso mudou ao longo do tempo. <strong>É o material da conversa de
        feedback</strong> — abra na frente dela.</p>
      <Msg msg={msg} />

      <label className="campo" style={{ maxWidth: 420 }}>
        <span className="rotulo">Colaborador</span>
        <SelectBusca valor={escolhido} vazioRotulo="— escolha —"
                     placeholder="Buscar colaborador…"
                     opcoes={colaboradores.map((c) => ({
                       valor: c.id, rotulo: c.nome,
                       extra: [c.cargo, c.posto].filter(Boolean).join(' · ') }))}
                     aoEscolher={setEscolhido} /></label>

      {escolhido && radar && (
        <div className="rh-card">
          <h3 style={{ marginTop: 0 }}>{pessoa ? pessoa.nome : ''}</h3>
          <div className="rh-conferencia-corpo">
            <div>
              <span className="rh-conferencia-bloco-titulo">Competências</span>
              {radar.respondentes && (radar.respondentes.vertical
                                      || radar.respondentes.horizontal) ? (
                <RadarCompetencias radar={radar} />
              ) : (
                <p className="explica">Ainda não há avaliação preenchida para
                  desenhar o gráfico.</p>
              )}
            </div>
            <div>
              <span className="rh-conferencia-bloco-titulo">Linha do tempo</span>
              {comNota.length === 0 && (
                <p className="explica">Nenhuma avaliação concluída ainda.</p>
              )}
              <Timeline itens={comNota} />
            </div>
          </div>
        </div>
      )}
    </>
  )
}

// Evolução das médias: uma barra por avaliação, da mais antiga para a mais nova.
// Mostra a curva da pessoa — que é o oposto de vigilância: ela vê o próprio
// progresso.
function Timeline({ itens }) {
  if (!itens.length) return null
  const ordenados = [...itens].reverse()   // a lista vem do mais novo
  return (
    <div className="timeline">
      {ordenados.map((it) => (
        <div className="timeline-item" key={it.id}>
          <div className="timeline-topo">
            <strong>{ROTULO_OCASIAO[it.ocasiao] || it.ocasiao}</strong>
            <span className="chip" style={{ '--chip-cor': COR_STATUS[it.status] }}>
              {ROTULO_STATUS[it.status]}</span>
          </div>
          <div className="timeline-barra">
            <div className="timeline-preenchida"
                 style={{ width: `${(it.media / 4) * 100}%` }} />
            <span className="timeline-valor">{it.media.toFixed(2)}</span>
          </div>
          <div className="explica" style={{ margin: 0 }}>
            {it.periodo_fim ? `até ${fmtIso(it.periodo_fim)}` : fmtIso((it.criado_em || '').slice(0, 10))}
            {' · '}{ROTULO_RELACAO[it.relacao]}
          </div>
        </div>
      ))}
    </div>
  )
}

// --------------------------------------------------------------------------
// Ciclos — 4 por ano, com datas configuráveis (geral, por posto ou individual)
// --------------------------------------------------------------------------

function Ciclos() {
  const [ciclos, setCiclos] = useState(null)
  const [novo, setNovo] = useState(false)
  const [f, setF] = useState({ nome: '', inicio_em: '', fim_em: '' })
  const [msg, setMsg] = useState(null)

  const carregar = () => api.ciclos().then((r) => setCiclos(r.ciclos))
    .catch((e) => setMsg({ tipo: 'erro', texto: e.detail || e.message }))
  useEffect(() => { carregar() }, [])
  if (!ciclos) return <p className="explica">Carregando…</p>

  return (
    <>
      <p className="explica" style={{ marginTop: '.4rem' }}>
        As janelas em que as avaliações acontecem — quatro por ano, com as datas que
        você escolher. Avaliar todo mundo na mesma janela é o que permite comparar
        os avaliadores entre si.</p>
      <Msg msg={msg} />

      {novo ? (
        <div className="rh-conferencia" style={{ marginBottom: '.8rem' }}>
          <div className="rh-conferencia-topo">
            <h3>Novo ciclo</h3>
            <button className="btn-secundario btn-mini"
                    onClick={() => setNovo(false)}>✕ fechar</button>
          </div>
          <label className="campo"><span className="rotulo">Nome</span>
            <input value={f.nome} placeholder="Ex.: 3º trimestre 2026" autoFocus
                   onChange={(e) => setF({ ...f, nome: e.target.value })} /></label>
          <div className="linha2">
            <label className="campo"><span className="rotulo">Início</span>
              <input type="date" value={f.inicio_em}
                     onChange={(e) => setF({ ...f, inicio_em: e.target.value })} /></label>
            <label className="campo"><span className="rotulo">Fim</span>
              <input type="date" value={f.fim_em}
                     onChange={(e) => setF({ ...f, fim_em: e.target.value })} /></label>
          </div>
          <div className="rh-conferencia-acoes">
            <button className="btn-principal btn-mini"
                    disabled={!f.nome.trim() || !f.inicio_em || !f.fim_em}
                    onClick={async () => {
                      try {
                        await api.criarCiclo(f)
                        setNovo(false); setF({ nome: '', inicio_em: '', fim_em: '' })
                        carregar()
                      } catch (e) {
                        setMsg({ tipo: 'erro', texto: e.detail === 'fim_antes_do_inicio'
                          ? 'O fim não pode ser antes do início.' : (e.detail || e.message) })
                      }
                    }}>Criar ciclo</button>
          </div>
        </div>
      ) : (
        <button className="btn-principal btn-mini" style={{ marginBottom: '.8rem' }}
                onClick={() => setNovo(true)}>＋ Novo ciclo</button>
      )}

      {ciclos.length === 0 && <p className="explica">Nenhum ciclo cadastrado.</p>}
      {ciclos.map((c) => (
        <div className="rh-card" key={c.id} style={{ marginBottom: '.6rem' }}>
          <div className="rh-topo" style={{ marginBottom: '.3rem' }}>
            <h4 style={{ margin: 0 }}>
              {c.nome} {c.encerrado && <span className="chip">Encerrado</span>}</h4>
            {!c.encerrado && (
              <button className="btn-secundario btn-mini" onClick={async () => {
                if (!window.confirm(`Encerrar o ciclo "${c.nome}"?`)) return
                try { await api.encerrarCiclo(c.id); carregar() }
                catch (e) { setMsg({ tipo: 'erro', texto: e.detail || e.message }) }
              }}>Encerrar</button>
            )}
          </div>
          <p className="explica" style={{ margin: 0 }}>
            {fmtIso(c.inicio_em)} a {fmtIso(c.fim_em)} · {c.avaliacoes} avaliação(ões)
            {c.homologadas > 0 && ` · ${c.homologadas} homologada(s)`}
          </p>
        </div>
      ))}
    </>
  )
}

function fmtIso(iso) {
  if (!iso) return '—'
  const [a, m, d] = iso.split('-')
  return `${d}/${m}/${a}`
}

function Msg({ msg }) {
  if (!msg) return null
  const classe = msg.tipo === 'ok' ? 'sucesso' : msg.tipo === 'aviso' ? 'aviso-inline' : 'alerta'
  return <div className={classe}>{msg.texto}</div>
}
