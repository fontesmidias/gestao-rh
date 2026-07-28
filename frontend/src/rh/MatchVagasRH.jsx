import { useEffect, useState } from 'react'
import { rh as api } from '../api.js'
import { comAmpulheta } from '../Carregando.jsx'
import DashPlanilha from './DashPlanilha.jsx'
import Modal from '../Modal.jsx'

// Match de Vagas × Banco de Talentos (v1.99, feedback 2026-07-27): o RH
// descreve a vaga e o sistema ranqueia os talentos por aderência, lendo
// também o currículo com IA. A IA NUNCA decide sozinha — só ordena e
// justifica; quem convoca é o RH. O currículo é entrada hostil (ver
// services/anti_prompt_injection.py no backend) — tentativa de manipulação
// vira alerta visível na tela, nunca é filtrada em silêncio.
export default function MatchVagasRH() {
  const [vagas, setVagas] = useState(null)
  const [editando, setEditando] = useState(null)
  const [ranqueando, setRanqueando] = useState(null) // vaga com resultado aberto
  const [resultado, setResultado] = useState(null)
  const [gerando, setGerando] = useState(false)
  const [msg, setMsg] = useState(null)

  const carregar = () => api.vagas(true).then(setVagas).catch(() => setVagas([]))
  useEffect(() => { carregar() }, [])

  const excluir = async (v) => {
    if (!window.confirm(`Excluir a vaga "${v.titulo}"?`)) return
    try { await api.excluirVaga(v.id); carregar() }
    catch (e) { setMsg({ tipo: 'erro', texto: `Não foi possível excluir (${e.detail || e.message}).` }) }
  }

  const abrirRanking = async (v) => {
    setRanqueando(v); setResultado(null); setGerando(true); setMsg(null)
    try {
      const r = await comAmpulheta('Analisando talentos…', () => api.ranquearVaga(v.id))
      setResultado(r)
    } catch (e) {
      setMsg({ tipo: 'erro', texto: e.detail === 'chave_nao_configurada'
        ? 'A IA (Groq) ainda não está configurada — veja Configurações → E-mail e integrações.'
        : `Não foi possível ranquear (${e.detail || e.message}).` })
      setRanqueando(null)
    } finally { setGerando(false) }
  }

  if (!vagas) return <main className="rh-painel"><p>Carregando…</p></main>

  const colunasRanking = [
    { chave: 'nome', rotulo: 'Talento', ordenavel: true, valor: (i) => i.nome },
    { chave: 'cargo_interesse', rotulo: 'Cargo de interesse', ordenavel: true,
      valor: (i) => i.cargo_interesse || '—' },
    { chave: 'nota_ia', rotulo: 'Nota IA', ordenavel: true, valor: (i) => i.nota_ia ?? -1,
      render: (i) => i.nota_ia == null
        ? (i.tem_curriculo ? <em>sem análise</em> : <em>sem currículo</em>)
        : <strong>{i.nota_ia}</strong> },
    { chave: 'bate_filtro_estruturado', rotulo: 'Filtro (cargo/região)', ordenavel: true,
      valor: (i) => i.bate_filtro_estruturado ? 'Sim' : 'Não',
      render: (i) => i.bate_filtro_estruturado ? '✓ Sim' : '— Não' },
    { chave: 'curriculo_suspeito', rotulo: 'Currículo', ordenavel: true,
      valor: (i) => i.curriculo_suspeito ? 'Suspeito' : (i.curriculo_legivel === false ? 'Ilegível' : 'OK'),
      render: (i) => i.curriculo_suspeito
        ? <span title="Foram detectados trechos que pareciam instruções escondidas — a IA foi orientada a ignorá-los, mas confira o currículo original.">⚠️ suspeito</span>
        : i.curriculo_legivel === false ? <span>não foi possível ler</span> : null },
  ]

  return (
    <main className="rh-painel">
      <header className="rh-topo">
        <h1>🎯 Match de Vagas</h1>
        <button className="btn-principal btn-mini" onClick={() => setEditando({})}>
          + Nova vaga</button>
      </header>
      <p className="explica">Descreva a vaga e o sistema ranqueia os talentos do Banco de
        Talentos por aderência, lendo também o currículo com IA. <strong>A IA nunca decide
        sozinha</strong> — ela ordena e explica; quem convoca é você. Currículo com trecho
        suspeito (tentativa de manipular a nota) fica marcado — nunca é filtrado em silêncio.</p>

      {msg && <div className={msg.tipo === 'erro' ? 'alerta' : 'sucesso'}>{msg.texto}</div>}

      {vagas.length === 0
        ? <p className="explica">Nenhuma vaga cadastrada ainda.</p>
        : (
          <table className="rh-tabela">
            <thead><tr><th>Título</th><th>Cargo</th><th>Status</th><th></th></tr></thead>
            <tbody>{vagas.map((v) => (
              <tr key={v.id}>
                <td><strong>{v.titulo}</strong></td>
                <td>{v.cargo || '—'}</td>
                <td>{v.ativa ? 'Ativa' : <em>Inativa</em>}</td>
                <td>
                  <button className="btn-secundario btn-mini" onClick={() => abrirRanking(v)}>
                    🎯 Ranquear talentos</button>
                  {' '}
                  <button className="btn-link" onClick={() => setEditando(v)}>editar</button>
                  {' · '}
                  <button className="btn-link" onClick={() => excluir(v)}>excluir</button>
                </td>
              </tr>
            ))}</tbody>
          </table>
        )}

      {editando && (
        <Modal titulo={editando.id ? `Editar vaga — ${editando.titulo}` : 'Nova vaga'}
               aoFechar={() => setEditando(null)}>
          <FormVaga vaga={editando} aoSalvo={() => { setEditando(null); carregar() }}
                    aoCancelar={() => setEditando(null)} />
        </Modal>
      )}

      {ranqueando && (
        <Modal titulo={`🎯 Ranking — ${ranqueando.titulo}`} aoFechar={() => setRanqueando(null)}>
          {gerando ? <p>Analisando…</p> : resultado && (
            <div>
              <p className="explica">
                {resultado.total} talento(s) no total · {resultado.curriculos_analisados}{' '}
                currículo(s) lido(s) pela IA
                {resultado.curriculos_suspeitos > 0 && (
                  <> · <strong style={{ color: 'var(--ambar)' }}>
                    {resultado.curriculos_suspeitos} com trecho suspeito
                  </strong></>
                )}
                {resultado.ia_indisponivel && (
                  <> · <strong>IA ficou indisponível durante a análise</strong> — os itens
                    restantes aparecem sem nota.</>
                )}
              </p>
              <DashPlanilha id="match-vagas-ranking" colunas={colunasRanking} dados={resultado.itens}
                            linhaExpandida={(i) => i.justificativa
                              ? <div className="explica" style={{ padding: '.5rem' }}>
                                  <strong>Justificativa da IA:</strong> {i.justificativa}
                                </div>
                              : null}
                            vazio="Nenhum talento para ranquear." />
            </div>
          )}
        </Modal>
      )}
    </main>
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
          <select value={regime} onChange={(e) => setRegime(e.target.value)}>
            <option value="">— não informar —</option>
            <option value="efetivo">Efetivo</option>
            <option value="intermitente">Intermitente</option>
            <option value="tanto_faz">Tanto faz</option>
          </select></label>
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
