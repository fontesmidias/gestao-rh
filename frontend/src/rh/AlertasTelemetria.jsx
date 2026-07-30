import { useEffect, useState } from 'react'
import { rh as api } from '../api.js'
import { fmtDataHora } from '../fmt.js'

// Alertas de telemetria (v2.25): o sistema AVISA em vez de esperar a pergunta.
//
// A telemetria da v2.24 é passiva — alguém precisa abrir a aba. No incidente de
// 2026-07-29 isso não bastaria: o erro estaria gravado às 11h01, e a descoberta
// continuaria dependendo de o candidato ligar.
//
// As regras são editáveis aqui (pedido do Bruno: "customizar mais cenários").
// Chumbar os limiares no código obrigaria um deploy a cada ajuste, e quem
// convive com os números é quem deve ajustá-los.

const TIPOS = {
  erro_novo: {
    rotulo: '🆕 Erro novo',
    ajuda: 'Uma mensagem de erro que NUNCA tinha aparecido. Foi o caso de '
      + '29/07: teria avisado às 11h05, antes de qualquer ligação.',
    unidade: null,   // não usa limiar: dispara na primeira ocorrência
  },
  erro_volume: {
    rotulo: '📈 Volume de erros',
    ajuda: 'Um erro CONHECIDO que disparou de volume. É a assinatura clássica '
      + 'de um deploy que deu errado.',
    unidade: 'ocorrências',
  },
  friccao_pico: {
    rotulo: '🚧 Pico de travamentos',
    ajuda: 'Muita gente travando no mesmo ponto — reenviando o mesmo documento, '
      + 'por exemplo. Indica que algo quebrou, não que as pessoas estão desatentas.',
    unidade: 'ocorrências',
  },
  lentidao: {
    rotulo: '🐢 Lentidão',
    ajuda: 'Uma página passou do tempo aceitável para a MAIORIA das pessoas '
      + '(mediana). Um caso isolado de lentidão não dispara.',
    unidade: 'milissegundos',
  },
}

const ORIGENS = [
  ['', 'Qualquer origem'],
  ['candidato', 'Candidato (admissão)'],
  ['talento', 'Banco de Talentos'],
  ['colaborador', 'Colaborador (portal/creche)'],
  ['rh', 'Painel do RH'],
  ['publico', 'Público'],
]

const NOVA = {
  tipo: 'erro_novo', nome: '', ativa: true, limiar: 10,
  janela_min: 60, silencio_min: 60, origem: '', pagina: '', evento: '',
}

export default function AlertasTelemetria() {
  const [regras, setRegras] = useState(null)
  const [editando, setEditando] = useState(null)   // id ou 'nova'
  const [rascunho, setRascunho] = useState(NOVA)
  const [teste, setTeste] = useState(null)
  const [hist, setHist] = useState(null)
  const [msg, setMsg] = useState(null)
  const [ocupado, setOcupado] = useState(false)

  const recarregar = () => api.alertaRegras().then(setRegras).catch(() => setRegras([]))
  useEffect(() => { recarregar() }, [])

  const salvar = async () => {
    if (!rascunho.nome.trim()) {
      setMsg({ tipo: 'erro', texto: 'Dê um nome à regra — é ele que aparece no e-mail.' })
      return
    }
    setOcupado(true); setMsg(null)
    const dados = {
      ...rascunho,
      limiar: Number(rascunho.limiar) || 1,
      janela_min: Number(rascunho.janela_min) || 60,
      silencio_min: Number(rascunho.silencio_min) || 60,
      origem: rascunho.origem || null,
      pagina: rascunho.pagina || null,
      evento: rascunho.evento || null,
    }
    try {
      if (editando === 'nova') await api.criarAlertaRegra(dados)
      else await api.editarAlertaRegra(editando, dados)
      setEditando(null); setRascunho(NOVA)
      setMsg({ tipo: 'ok', texto: 'Regra salva. Ela vale a partir da próxima verificação.' })
      await recarregar()
    } catch (e) {
      setMsg({ tipo: 'erro', texto: `Não foi possível salvar (${e.detail || e.message}).` })
    } finally { setOcupado(false) }
  }

  const excluir = async (r) => {
    if (!window.confirm(`Excluir a regra "${r.nome}"? O sistema deixa de avisar sobre isso.`)) return
    try {
      await api.excluirAlertaRegra(r.id)
      setMsg({ tipo: 'ok', texto: 'Regra excluída.' })
      await recarregar()
    } catch { setMsg({ tipo: 'erro', texto: 'Não foi possível excluir.' }) }
  }

  const testar = async () => {
    setOcupado(true); setMsg(null); setTeste(null)
    try {
      setTeste(await api.testarAlertas())
    } catch { setMsg({ tipo: 'erro', texto: 'Não foi possível testar agora.' }) }
    finally { setOcupado(false) }
  }

  const verHistorico = async () => {
    try { setHist(await api.alertaHistorico()) } catch { setHist([]) }
  }

  return (
    <details className="rh-bloco">
      <summary><strong>🔔 Alertas — o sistema avisa você</strong></summary>

      <p className="explica">
        Em vez de esperar alguém abrir esta tela, o sistema verifica a cada
        <strong> 15 minutos</strong> e manda e-mail quando algo merece atenção.
        Quem recebe é definido em <strong>Configurações → Avisos internos</strong>,
        no evento <em>“⚠️ Telemetria: algo quebrou ou travou”</em> — a mesma
        matriz dos outros avisos.
      </p>

      {regras === null ? <p>Carregando…</p> : (
        <table className="rh-tabela">
          <thead><tr>
            <th>Regra</th><th>Tipo</th><th>Dispara quando</th>
            <th>Silêncio</th><th>Ativa</th><th></th>
          </tr></thead>
          <tbody>
            {regras.length === 0 && (
              <tr><td colSpan="6" className="explica">
                Nenhuma regra. Sem elas, a telemetria só fala quando você pergunta.
              </td></tr>
            )}
            {regras.map((r) => (
              <tr key={r.id}>
                <td><strong>{r.nome}</strong>
                  {(r.origem || r.pagina || r.evento) && (
                    <><br /><small>
                      {r.origem && `origem: ${r.origem} `}
                      {r.pagina && `página: ${r.pagina} `}
                      {r.evento && `evento: ${r.evento}`}
                    </small></>
                  )}
                </td>
                <td>{TIPOS[r.tipo]?.rotulo || r.tipo}</td>
                <td className="dash-quebra">{descrever(r)}</td>
                <td>{r.silencio_min} min</td>
                <td>{r.ativa ? '✅' : '⏸️'}</td>
                <td>
                  <button className="btn-link" onClick={() => {
                    setEditando(r.id)
                    setRascunho({ ...r, origem: r.origem || '', pagina: r.pagina || '',
                                  evento: r.evento || '' })
                  }}>editar</button>
                  <button className="btn-link" onClick={() => excluir(r)}>excluir</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {/* Edição PERTO do item, nunca no topo (sistema de design, item 3) */}
      {editando && (
        <Formulario rascunho={rascunho} setRascunho={setRascunho}
                    salvar={salvar} ocupado={ocupado}
                    cancelar={() => { setEditando(null); setRascunho(NOVA); setMsg(null) }} />
      )}

      {!editando && (
        <div className="rh-acoes">
          <button className="btn-secundario"
                  onClick={() => { setEditando('nova'); setRascunho(NOVA) }}>
            ＋ Nova regra
          </button>
          <button className="btn-link" onClick={testar} disabled={ocupado}>
            🔎 O que dispararia agora?
          </button>
          <button className="btn-link" onClick={verHistorico}>
            📜 Alertas já enviados
          </button>
        </div>
      )}

      {msg && <div className={msg.tipo === 'ok' ? 'sucesso' : 'alerta'}>{msg.texto}</div>}

      {teste && (
        <div className="aviso-codigo">
          <strong>Se a verificação rodasse agora:</strong>
          {teste.length === 0 ? (
            <p>Nada dispararia — nenhuma regra encontrou problema no período.</p>
          ) : (
            <ul>
              {teste.map((t, i) => (
                <li key={i}><strong>{t.regra}</strong> ({t.total}):
                  <ul>{t.itens.map((x, j) => <li key={j}>{x}</li>)}</ul>
                </li>
              ))}
            </ul>
          )}
          <p className="explica">
            Esta simulação <strong>não envia e-mail nem gasta o silêncio</strong> —
            testar aqui não impede o alerta de verdade de chegar depois.
          </p>
        </div>
      )}

      {hist && (
        <div className="rh-bloco-interno">
          <h4>📜 Alertas já enviados</h4>
          {hist.length === 0 ? (
            <p className="explica">
              Nenhum alerta enviado ainda. Isto é uma boa notícia — mas confira
              se há destinatário cadastrado em Avisos internos.
            </p>
          ) : (
            <table className="rh-tabela">
              <thead><tr>
                <th>Quando</th><th>Tipo</th><th>O quê</th><th>Enviado a</th>
              </tr></thead>
              <tbody>
                {hist.map((h) => (
                  <tr key={h.id}>
                    <td>{fmtDataHora(h.quando)}</td>
                    <td>{h.rotulo}</td>
                    <td className="dash-quebra">{h.resumo}</td>
                    {/* Zero destinatários = o alerta foi calculado mas não
                        chegou a ninguém. Precisa ser visível, senão o RH
                        acharia que está coberto quando não está. */}
                    <td>{h.destinatarios > 0 ? `${h.destinatarios} e-mail(s)`
                      : <span className="chip" style={{ '--chip-cor': '#c33' }}>
                          ninguém cadastrado</span>}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}
    </details>
  )
}

function descrever(r) {
  if (r.tipo === 'erro_novo') return 'Na primeira vez que o erro aparecer'
  if (r.tipo === 'lentidao') {
    return `A maioria esperar mais de ${(r.limiar / 1000).toFixed(1)}s (em ${r.janela_min} min)`
  }
  return `${r.limiar}+ vezes em ${r.janela_min} min`
}

function Formulario({ rascunho, setRascunho, salvar, cancelar, ocupado }) {
  const tipo = TIPOS[rascunho.tipo] || {}
  const set = (k) => (e) => setRascunho({ ...rascunho, [k]: e.target.value })

  return (
    <div className="rh-form-inline">
      <label className="campo"><span className="rotulo">Tipo de alerta</span>
        <select value={rascunho.tipo} onChange={set('tipo')}>
          {Object.entries(TIPOS).map(([v, t]) => (
            <option key={v} value={v}>{t.rotulo}</option>
          ))}
        </select>
        <small className="explica">{tipo.ajuda}</small>
      </label>

      <label className="campo"><span className="rotulo">Nome da regra</span>
        <input value={rascunho.nome} onChange={set('nome')}
               placeholder="ex.: Candidato travando no envio" />
        <small className="explica">Aparece no assunto do e-mail — escreva algo
          que você entenda às 7h da manhã.</small>
      </label>

      <div className="rh-grid-2">
        {/* `erro_novo` dispara na primeira ocorrência: limiar não faz sentido */}
        {tipo.unidade && (
          <label className="campo">
            <span className="rotulo">Dispara a partir de ({tipo.unidade})</span>
            <input type="number" min="1" value={rascunho.limiar} onChange={set('limiar')} />
            {rascunho.tipo === 'lentidao' && (
              <small className="explica">8000 = 8 segundos.</small>
            )}
          </label>
        )}
        <label className="campo"><span className="rotulo">Janela de observação (min)</span>
          <input type="number" min="5" value={rascunho.janela_min} onChange={set('janela_min')} />
          <small className="explica">Período que o sistema olha para trás.</small>
        </label>
        <label className="campo"><span className="rotulo">Silêncio depois de avisar (min)</span>
          <input type="number" min="5" value={rascunho.silencio_min}
                 onChange={set('silencio_min')} />
          <small className="explica">Impede o mesmo aviso de repetir. Alerta que
            vira enxurrada deixa de ser lido.</small>
        </label>
      </div>

      <details>
        <summary>Restringir a regra (opcional)</summary>
        <div className="rh-grid-2">
          <label className="campo"><span className="rotulo">Só desta origem</span>
            <select value={rascunho.origem} onChange={set('origem')}>
              {ORIGENS.map(([v, r]) => <option key={v} value={v}>{r}</option>)}
            </select>
          </label>
          <label className="campo"><span className="rotulo">Só nesta página (contém)</span>
            <input value={rascunho.pagina} onChange={set('pagina')} placeholder="ex.: /c/documentos" />
          </label>
          <label className="campo"><span className="rotulo">Só neste evento</span>
            <input value={rascunho.evento} onChange={set('evento')}
                   placeholder="ex.: documento_reenviado" />
          </label>
        </div>
      </details>

      <label className="campo-check">
        <input type="checkbox" checked={rascunho.ativa}
               onChange={(e) => setRascunho({ ...rascunho, ativa: e.target.checked })} />
        <span>Regra ativa</span>
      </label>

      <div className="rh-acoes">
        <button className="btn-principal" onClick={salvar} disabled={ocupado}>
          {ocupado ? 'Salvando…' : 'Salvar regra'}
        </button>
        <button className="btn-link" onClick={cancelar}>cancelar</button>
      </div>
    </div>
  )
}
