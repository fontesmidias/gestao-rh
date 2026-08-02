import { useEffect, useState } from 'react'
import { rh as api } from '../api.js'
import { fmtDataHora } from '../fmt.js'
import DashPlanilha from './DashPlanilha.jsx'
import Modal from '../Modal.jsx'
import SelectBusca from '../SelectBusca.jsx'

// Match de Vagas × Banco de Talentos (v2.00 — reescrito após o incidente de
// 2026-07-28, em que 131 talentos viraram 18 analisados e depois 2).
//
// O ranqueamento agora é ASSÍNCRONO: o RH clica, continua usando o sistema, e
// o resultado aparece na aba Resultados quando o worker termina. A IA nunca
// decide sozinha — ordena e explica; quem convoca é o RH. E ninguém some em
// silêncio: quem não tem currículo, quem tem currículo ilegível e quem ficou
// sem análise por cota aparecem todos, com o motivo.

const RESULTADO_ROTULO = {
  analisado: ['✅ Analisado', '#2e9e5b'],
  sem_curriculo: ['⭕ Sem currículo', '#8a8a8a'],
  curriculo_ilegivel: ['⚠️ Currículo ilegível', '#c98a12'],
  ia_indisponivel: ['⏳ Aguardando IA', '#3b7dd8'],
  erro: ['🔁 Erro na análise', '#c0392b'],
}

const STATUS_PROC = {
  na_fila: ['Na fila', '#8a8a8a'],
  processando: ['Processando…', '#3b7dd8'],
  concluido: ['Concluído', '#2e9e5b'],
  concluido_sem_ia: ['Concluído sem IA', '#c98a12'],
  falhou: ['Falhou', '#c0392b'],
}

export default function MatchVagasRH() {
  const [aba, setAba] = useState('vagas')
  const [vagas, setVagas] = useState(null)
  const [editando, setEditando] = useState(null)
  const [vagaResultado, setVagaResultado] = useState(null)
  const [msg, setMsg] = useState(null)
  const [indexacao, setIndexacao] = useState(null)

  const carregar = () => api.vagas(true).then(setVagas).catch(() => setVagas([]))
  const carregarIndexacao = () =>
    api.statusIndexacaoCurriculos().then(setIndexacao).catch(() => {})
  useEffect(() => { carregar(); carregarIndexacao() }, [])

  const excluir = async (v) => {
    if (!window.confirm(`Excluir a vaga "${v.titulo}"?`)) return
    try { await api.excluirVaga(v.id); carregar() }
    catch (e) { setMsg({ tipo: 'erro', texto: `Não foi possível excluir (${e.detail || e.message}).` }) }
  }

  const ranquear = async (v, reanalisar = false) => {
    setMsg(null)
    try {
      const r = await api.ranquearVaga(v.id, reanalisar)
      setMsg({ tipo: 'ok', texto: r.ja_em_andamento
        ? 'Esta vaga já está sendo processada — acompanhe em Resultados.'
        : 'Análise iniciada em segundo plano. Você pode continuar usando o sistema; '
          + 'o resultado aparece na aba Resultados (e você recebe um aviso quando terminar).' })
      setAba('resultados'); setVagaResultado(v)
    } catch (e) {
      setMsg({ tipo: 'erro', texto: e.detail === 'fila_indisponivel'
        ? 'O processamento em segundo plano está fora do ar. Avise o suporte.'
        : `Não foi possível iniciar (${e.detail || e.message}).` })
    }
  }

  if (!vagas) return <main className="rh-painel"><p>Carregando…</p></main>

  return (
    <main className="rh-painel">
      <header className="rh-topo">
        <h1>🧩 Match de Vagas</h1>
        <button className="btn-principal btn-mini" onClick={() => setEditando({})}>
          + Nova vaga</button>
      </header>

      <nav className="rh-subnav">
        <button className={`rh-subnav-item ${aba === 'vagas' ? 'ativo' : ''}`}
                onClick={() => setAba('vagas')}>📋 Vagas</button>
        <button className={`rh-subnav-item ${aba === 'resultados' ? 'ativo' : ''}`}
                onClick={() => setAba('resultados')}>📊 Resultados</button>
      </nav>

      {msg && <div className={msg.tipo === 'erro' ? 'alerta' : 'sucesso'}>{msg.texto}</div>}

      {aba === 'vagas' && (
        <>
          <p className="explica">Descreva a vaga e o sistema ranqueia os talentos do Banco de
            Talentos por aderência, lendo também o currículo com IA. A análise roda em{' '}
            <strong>segundo plano</strong> — você não precisa esperar na tela.
            <strong> A IA nunca decide sozinha</strong>: ela ordena e explica; quem convoca é você.</p>

          <IndexacaoCurriculos dados={indexacao} aoIndexar={async () => {
            try {
              await api.indexarCurriculos()
              setMsg({ tipo: 'ok', texto: 'Leitura dos currículos iniciada em segundo plano.' })
            } catch (e) {
              setMsg({ tipo: 'erro', texto: `Não foi possível iniciar (${e.detail || e.message}).` })
            }
          }} aoAtualizar={carregarIndexacao} />

          {vagas.length === 0
            ? <p className="explica">Nenhuma vaga cadastrada ainda.</p>
            : (
              <div className="dash-scroll">
                <table className="rh-tabela">
                  <thead><tr><th>Título</th><th>Cargo</th><th>Status</th><th></th></tr></thead>
                  <tbody>{vagas.map((v) => (
                    <tr key={v.id}>
                      <td><strong>{v.titulo}</strong></td>
                      <td>{v.cargo || '—'}</td>
                      <td>{v.ativa ? 'Ativa' : <em>Inativa</em>}</td>
                      <td>
                        <button className="btn-secundario btn-mini" onClick={() => ranquear(v)}>
                          🎯 Ranquear</button>
                        {' '}
                        <button className="btn-link" onClick={() => { setAba('resultados'); setVagaResultado(v) }}>
                          resultados</button>
                        {' · '}
                        <button className="btn-link" onClick={() => setEditando(v)}>editar</button>
                        {' · '}
                        <button className="btn-link" onClick={() => excluir(v)}>excluir</button>
                      </td>
                    </tr>
                  ))}</tbody>
                </table>
              </div>
            )}
        </>
      )}

      {aba === 'resultados' && (
        <Resultados vagas={vagas} vagaSelecionada={vagaResultado}
                    aoSelecionar={setVagaResultado}
                    aoReanalisar={(v) => ranquear(v, true)} />
      )}

      {editando && (
        <Modal titulo={editando.id ? `Editar vaga — ${editando.titulo}` : 'Nova vaga'}
               aoFechar={() => setEditando(null)}>
          <FormVaga vaga={editando} aoSalvo={() => { setEditando(null); carregar() }}
                    aoCancelar={() => setEditando(null)} />
        </Modal>
      )}
    </main>
  )
}

// Painel de leitura dos currículos: se este número estiver baixo, o gargalo
// está AQUI, não na IA — o ranqueamento só analisa quem já foi lido.
function IndexacaoCurriculos({ dados, aoIndexar, aoAtualizar }) {
  if (!dados) return null
  const { total_talentos: total, com_curriculo: comCv, indexados, ilegiveis, pendentes } = dados
  return (
    <div className="rh-card">
      <strong>📄 Leitura dos currículos</strong>
      <p className="explica">O texto do currículo é lido <strong>uma vez</strong> e reaproveitado
        em todos os ranqueamentos — por isso o Match não precisa reler nada a cada clique.
        O ranqueamento só consegue analisar quem já foi lido.</p>
      <div className="rh-lote">
        <span className="rh-metrica"><strong>{total}</strong><span>talentos</span></span>
        <span className="rh-metrica"><strong>{comCv}</strong><span>com currículo</span></span>
        <span className="rh-metrica"><strong>{indexados}</strong><span>lidos</span></span>
        {ilegiveis > 0 && (
          <span className="rh-metrica"><strong>{ilegiveis}</strong><span>ilegíveis</span></span>)}
        {pendentes > 0 && (
          <span className="rh-metrica"><strong>{pendentes}</strong><span>a ler</span></span>)}
      </div>
      {comCv === 0 && total > 0 && (
        <div className="alerta">Nenhum talento tem currículo anexado. Sem currículo, a IA não
          tem o que analisar — o ranking usa só os dados do cadastro (cargo, região,
          experiência informada).</div>
      )}
      <div className="rh-lote" style={{ marginTop: '.4rem' }}>
        <button className="btn-secundario btn-mini" onClick={aoIndexar}>
          📖 Ler currículos pendentes</button>
        <button className="btn-link" onClick={aoAtualizar}>atualizar</button>
      </div>
    </div>
  )
}

function Resultados({ vagas, vagaSelecionada, aoSelecionar, aoReanalisar }) {
  const [dados, setDados] = useState(null)
  const [erro, setErro] = useState(null)

  const vagaId = vagaSelecionada?.id
  const status = dados?.processamento?.status
  const rodando = status === 'na_fila' || status === 'processando'

  const carregar = () => {
    if (!vagaId) return
    api.resultadoVaga(vagaId).then(setDados)
      .catch((e) => setErro(e.detail || e.message))
  }

  // Efeito 1: trocou de vaga → limpa e busca. NÃO depende de `dados`, senão
  // o setDados(null) daqui se realimenta e a tela fica presa em "Carregando…".
  useEffect(() => {
    setDados(null); setErro(null)
    if (!vagaId) return
    api.resultadoVaga(vagaId).then(setDados)
      .catch((e) => setErro(e.detail || e.message))
  }, [vagaId])

  // Efeito 2: enquanto está processando, atualiza sozinho — o RH não precisa
  // ficar apertando F5 para saber se terminou. Para quando conclui.
  useEffect(() => {
    if (!rodando) return undefined
    const id = setInterval(carregar, 5000)
    return () => clearInterval(id)
  }, [rodando, vagaId])

  const colunas = [
    { chave: 'nome', rotulo: 'Talento', ordenavel: true, valor: (i) => i.nome },
    { chave: 'resultado', rotulo: 'Situação', ordenavel: true, filtro: 'select',
      opcoes: Object.entries(RESULTADO_ROTULO).map(([v, [r]]) => ({ v, r })),
      valor: (i) => (RESULTADO_ROTULO[i.resultado] || [i.resultado])[0],
      render: (i) => {
        const [rotulo, cor] = RESULTADO_ROTULO[i.resultado] || [i.resultado, '#888']
        return <span className="chip" style={{ '--chip-cor': cor }}>{rotulo}</span>
      } },
    { chave: 'nota', rotulo: 'Nota IA', ordenavel: true, valor: (i) => i.nota ?? -1,
      render: (i) => i.nota == null ? '—' : <strong>{i.nota}</strong> },
    { chave: 'bate_filtro', rotulo: 'Cargo/região', ordenavel: true,
      valor: (i) => i.bate_filtro ? 'Compatível' : 'Não compatível',
      render: (i) => i.bate_filtro ? '✓' : '—' },
    { chave: 'cargo_interesse', rotulo: 'Cargo de interesse', ordenavel: true,
      valor: (i) => i.cargo_interesse || '—', quebra: true },
    { chave: 'telefone', rotulo: 'Contato', valor: (i) => i.telefone || i.email || '—' },
    { chave: 'curriculo_suspeito', rotulo: 'Alerta', ordenavel: true,
      valor: (i) => i.curriculo_suspeito ? 'Suspeito' : '',
      render: (i) => i.curriculo_suspeito
        ? <span title="Foram detectados trechos que pareciam instruções escondidas no currículo. A IA foi orientada a ignorá-los — confira o currículo original.">🚩 suspeito</span>
        : null },
  ]

  if (!vagas.length) return <p className="explica">Cadastre uma vaga primeiro.</p>

  return (
    <>
      <label className="campo"><span className="rotulo">Vaga</span>
        <SelectBusca valor={vagaId || ''} aoEscolher={(v) => aoSelecionar(vagas.find((v) => v.id === v) || null)}>
          <option value="">— escolha uma vaga —</option>
          {vagas.map((v) => <option key={v.id} value={v.id}>{v.titulo}</option>)}
        </SelectBusca></label>

      {erro && <div className="alerta">{erro}</div>}
      {!vagaId && <p className="explica">Escolha uma vaga para ver o resultado.</p>}
      {vagaId && !dados && <p>Carregando…</p>}

      {dados && (
        <>
          <ResumoProcessamento proc={dados.processamento}
                               aoReanalisar={() => aoReanalisar(vagaSelecionada)} />
          {dados.itens.length === 0
            ? <p className="explica">Nenhum resultado ainda para esta vaga.</p>
            : (
              <DashPlanilha id="match-resultado" colunas={colunas} dados={dados.itens}
                            linhaExpandida={(i) => (i.justificativa || i.detalhe_falha)
                              ? <div className="explica" style={{ padding: '.5rem' }}>
                                  {i.justificativa && <><strong>Justificativa da IA:</strong> {i.justificativa}</>}
                                  {i.detalhe_falha && <><br /><strong>Detalhe:</strong> {i.detalhe_falha}</>}
                                </div>
                              : null}
                            vazio="Nenhum resultado." />
            )}
        </>
      )}
    </>
  )
}

function ResumoProcessamento({ proc, aoReanalisar }) {
  if (!proc) {
    return <p className="explica">Esta vaga ainda não foi ranqueada.</p>
  }
  const [rotulo, cor] = STATUS_PROC[proc.status] || [proc.status, '#888']
  const rodando = proc.status === 'na_fila' || proc.status === 'processando'
  return (
    <div className="rh-card">
      <div className="rh-lote" style={{ alignItems: 'center' }}>
        <span className="chip" style={{ '--chip-cor': cor }}>{rotulo}</span>
        {rodando && proc.total_talentos > 0 && (
          <span className="explica" style={{ margin: 0 }}>
            {proc.processados} de {proc.total_talentos} processados…</span>
        )}
        {!rodando && (
          <button className="btn-secundario btn-mini" onClick={aoReanalisar}
                  title="Refaz a análise de todo mundo, mesmo de quem já foi analisado">
            🔄 Reanalisar tudo</button>
        )}
      </div>
      <div className="rh-lote" style={{ marginTop: '.5rem' }}>
        <span className="rh-metrica"><strong>{proc.analisados_ia}</strong><span>analisados agora</span></span>
        <span className="rh-metrica"><strong>{proc.reaproveitados}</strong><span>já analisados antes</span></span>
        <span className="rh-metrica"><strong>{proc.sem_curriculo}</strong><span>sem currículo</span></span>
        <span className="rh-metrica"><strong>{proc.ilegiveis}</strong><span>currículo ilegível</span></span>
        {proc.suspeitos > 0 && (
          <span className="rh-metrica"><strong>{proc.suspeitos}</strong><span>com alerta</span></span>)}
      </div>
      {proc.observacao && <div className="alerta" style={{ marginTop: '.5rem' }}>{proc.observacao}</div>}
      <p className="explica" style={{ marginTop: '.4rem' }}>
        Iniciado em {fmtDataHora(proc.criado_em)}
        {proc.concluido_em && <> · concluído em {fmtDataHora(proc.concluido_em)}</>}
        {proc.solicitado_por && <> · por {proc.solicitado_por}</>}
      </p>
    </div>
  )
}

function FormVaga({ vaga, aoSalvo, aoCancelar }) {
  const [titulo, setTitulo] = useState(vaga.titulo || '')
  const [descricao, setDescricao] = useState(vaga.descricao || '')
  const [cargo, setCargo] = useState(vaga.cargo || '')
  const [regiao, setRegiao] = useState(vaga.regiao || '')
  const [regime, setRegime] = useState(vaga.regime || '')
  const [salarioMin, setSalarioMin] = useState(vaga.salario_min || '')
  const [salarioMax, setSalarioMax] = useState(vaga.salario_max || '')
  const [reqObrigatorios, setReqObrigatorios] = useState(vaga.requisitos_obrigatorios || '')
  const [reqDesejaveis, setReqDesejaveis] = useState(vaga.requisitos_desejaveis || '')
  const [msg, setMsg] = useState(null)
  const [salvando, setSalvando] = useState(false)

  const salvar = async () => {
    if (!titulo.trim()) { setMsg({ tipo: 'erro', texto: 'Informe um título.' }); return }
    setSalvando(true); setMsg(null)
    try {
      const dados = {
        titulo: titulo.trim(), descricao, cargo: cargo || null, regiao: regiao || null,
        regime: regime || null, salario_min: salarioMin || null, salario_max: salarioMax || null,
        requisitos_obrigatorios: reqObrigatorios || null, requisitos_desejaveis: reqDesejaveis || null,
      }
      if (vaga.id) await api.editarVaga(vaga.id, dados)
      else await api.criarVaga(dados)
      aoSalvo()
    } catch (e) {
      setMsg({ tipo: 'erro', texto: `Não foi possível salvar (${e.detail || e.message}).` })
    } finally { setSalvando(false) }
  }

  return (
    <div>
      <label className="campo"><span className="rotulo">Título da vaga</span>
        <input value={titulo} onChange={(e) => setTitulo(e.target.value)} /></label>
      <label className="campo"><span className="rotulo">Descrição</span>
        <textarea rows={4} value={descricao} onChange={(e) => setDescricao(e.target.value)} /></label>
      <div className="linha2">
        <label className="campo"><span className="rotulo">Cargo</span>
          <input value={cargo} onChange={(e) => setCargo(e.target.value)} /></label>
        <label className="campo"><span className="rotulo">Região</span>
          <input value={regiao} onChange={(e) => setRegiao(e.target.value)} /></label>
      </div>
      <div className="linha3">
        <label className="campo"><span className="rotulo">Regime</span>
          <SelectBusca valor={regime} aoEscolher={(v) => setRegime(v)}>
            <option value="">— não informar —</option>
            <option value="efetivo">Efetivo</option>
            <option value="intermitente">Intermitente</option>
            <option value="tanto_faz">Tanto faz</option>
          </SelectBusca></label>
        <label className="campo"><span className="rotulo">Salário mín.</span>
          <input value={salarioMin} onChange={(e) => setSalarioMin(e.target.value)} /></label>
        <label className="campo"><span className="rotulo">Salário máx.</span>
          <input value={salarioMax} onChange={(e) => setSalarioMax(e.target.value)} /></label>
      </div>
      <label className="campo"><span className="rotulo">Requisitos obrigatórios</span>
        <textarea rows={2} value={reqObrigatorios} onChange={(e) => setReqObrigatorios(e.target.value)} /></label>
      <label className="campo"><span className="rotulo">Requisitos desejáveis</span>
        <textarea rows={2} value={reqDesejaveis} onChange={(e) => setReqDesejaveis(e.target.value)} /></label>
      {msg && <div className="alerta">{msg.texto}</div>}
      <div className="rh-lote" style={{ marginTop: '.6rem' }}>
        <button className="btn-secundario btn-mini" onClick={aoCancelar}>cancelar</button>
        <button className="btn-principal btn-mini" disabled={salvando} onClick={salvar}>
          {salvando ? 'Salvando…' : 'Salvar'}</button>
      </div>
    </div>
  )
}
