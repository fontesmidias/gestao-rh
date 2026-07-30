import { useEffect, useState } from 'react'
import { rh as api } from '../api.js'
import { fmtDataHora } from '../fmt.js'
import DashPlanilha from './DashPlanilha.jsx'
import Ajuda from '../Ajuda.jsx'
import AlertasTelemetria from './AlertasTelemetria.jsx'

// Telemetria de uso (v2.24, Configurações → 📈 Telemetria).
//
// Nasceu do incidente de 2026-07-29: dois candidatos travados com a tela em
// branco, e nenhuma forma de saber — o erro acontecia no navegador deles e
// morria lá. O servidor registrou 200 em tudo.
//
// A tela responde três perguntas, nesta ordem, porque é a ordem em que elas
// importam:
//   1. Está quebrando? (erros agrupados — 300 ocorrências do mesmo erro são
//      UM problema, não 300)
//   2. Onde as pessoas travam? (fricção)
//   3. O que está lento no aparelho delas? (desempenho, por mediana)
//
// Não é a Auditoria (Sistema → Auditoria): aquela é prova de ato, append-only.
// Esta é dado de produto, descartável, com retenção configurável.
//
// LAYOUT: usa as primitivas de `08-sistema-de-design.md` — `.rh-card` para cada
// bloco, `.rh-metricas` para os números, `.rh-grid-2` para pares de campo. A 1ª
// versão inventou onze classes (`rh-secao`, `rh-bloco`, `rh-acoes`…) que não
// existiam no styles.css: sem CSS por trás, a tela saiu crua, sem card nem
// respiro (feedback do Bruno, 2026-07-30). Ao mexer aqui, confira se a classe
// EXISTE em styles.css antes de usá-la.

const TIPOS = [
  ['', 'Todos os tipos'],
  ['erro', '🔴 Erros'],
  ['friccao', '🟠 Fricção'],
  ['jornada', '🔵 Jornada'],
  ['desempenho', '🟣 Desempenho'],
]
const ORIGENS = [
  ['', 'Todas as origens'],
  ['candidato', 'Candidato (admissão)'],
  ['talento', 'Banco de Talentos'],
  ['colaborador', 'Colaborador (portal/creche)'],
  ['rh', 'Painel do RH'],
  ['publico', 'Público'],
]
const ROTULO_TIPO = { erro: '🔴 Erro', friccao: '🟠 Fricção',
                      jornada: '🔵 Jornada', desempenho: '🟣 Desempenho' }

const COLUNAS = [
  { chave: 'quando', rotulo: 'Quando', ordenavel: true, sempreVisivel: true,
    valor: (e) => e.quando, render: (e) => fmtDataHora(e.quando) },
  { chave: 'tipo', rotulo: 'Tipo', ordenavel: true, filtro: 'select',
    opcoes: Object.values(ROTULO_TIPO).map((r) => ({ v: r, r })),
    valor: (e) => ROTULO_TIPO[e.tipo] || e.tipo },
  { chave: 'evento', rotulo: 'Evento', ordenavel: true, filtro: 'texto',
    valor: (e) => e.evento },
  { chave: 'pagina', rotulo: 'Página', ordenavel: true, filtro: 'texto',
    valor: (e) => e.pagina || '—', quebra: true },
  { chave: 'origem', rotulo: 'Origem', ordenavel: true, filtro: 'select',
    opcoes: ORIGENS.filter(([v]) => v).map(([v]) => ({ v, r: v })),
    valor: (e) => e.origem },
  { chave: 'duracao', rotulo: 'Duração', ordenavel: true,
    valor: (e) => e.duracao_ms || 0,
    render: (e) => (e.duracao_ms ? `${(e.duracao_ms / 1000).toFixed(1)}s` : '—') },
  { chave: 'versao', rotulo: 'Versão', ordenavel: true, valor: (e) => e.versao || '—' },
]

export default function TelemetriaRH() {
  const [dias, setDias] = useState(7)
  const [resumo, setResumo] = useState(null)
  const [eventos, setEventos] = useState(null)
  const [filtros, setFiltros] = useState({ tipo: '', origem: '' })

  const carregar = () => {
    api.telemetriaResumo(dias).then(setResumo).catch(() => setResumo(null))
    api.telemetria({ ...filtros, dias, limite: 300 })
      .then(setEventos).catch(() => setEventos([]))
  }
  useEffect(() => { carregar() }, [dias, filtros.tipo, filtros.origem])

  const vazio = resumo && resumo.total === 0

  return (
    <>
      <div className="rh-card">
        <div className="rh-topo">
          <h3>📈 Telemetria de uso</h3>
          <label className="campo campo-sem-margem">
            <select value={dias} onChange={(e) => setDias(Number(e.target.value))}>
              <option value={1}>Últimas 24 horas</option>
              <option value={7}>Últimos 7 dias</option>
              <option value={30}>Últimos 30 dias</option>
              <option value={90}>Últimos 90 dias</option>
            </select>
          </label>
        </div>

        <p className="explica">
          O que acontece no <strong>aparelho das pessoas</strong> — erros de tela,
          onde elas travam e o que está lento de verdade no celular delas. É
          diferente da Auditoria <Ajuda texto="A Auditoria (aba Sistema) registra QUEM FEZ O QUÊ e é prova de ato: nunca se apaga. A Telemetria registra COMO FOI USAR o sistema, é dado de produto e tem retenção configurável." />.
        </p>

        {resumo && (
          <div className="rh-metricas">
            <div className="rh-metrica">
              <strong>{resumo.por_tipo?.erro || 0}</strong><span>🔴 Erros</span>
            </div>
            <div className="rh-metrica">
              <strong>{resumo.por_tipo?.friccao || 0}</strong><span>🟠 Fricção</span>
            </div>
            <div className="rh-metrica">
              <strong>{resumo.por_tipo?.desempenho || 0}</strong><span>🟣 Lentidão</span>
            </div>
            <div className="rh-metrica">
              <strong>{resumo.total}</strong><span>Total de eventos</span>
            </div>
          </div>
        )}

        {vazio && (
          <p className="explica" style={{ marginBottom: 0 }}>
            Nenhum evento neste período. Se o sistema acabou de ser atualizado, é
            normal — os dados aparecem conforme as pessoas usam.
          </p>
        )}
      </div>

      {/* 1. Está quebrando? Agrupado por mensagem: 300 ocorrências do mesmo
          erro são UM problema — a lista crua esconderia isso no volume. */}
      {resumo?.erros?.length > 0 && (
        <div className="rh-card">
          <h3>🔴 Erros de tela — o que está quebrando ({resumo.erros.length})</h3>
          <table className="rh-tabela">
            <thead><tr>
              <th>Mensagem</th><th>Página</th><th>Vezes</th>
              <th>Sessões</th><th>Última</th>
            </tr></thead>
            <tbody>
              {resumo.erros.map((e, i) => (
                <tr key={i}>
                  <td className="dash-quebra"><code>{e.mensagem || e.evento}</code></td>
                  <td>{e.pagina || '—'}</td>
                  <td><strong>{e.ocorrencias}</strong></td>
                  <td>{e.pessoas}</td>
                  <td>{fmtDataHora(e.ultima)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="explica">
            <strong>Sessões</strong> é quanta gente diferente bateu no mesmo erro.
            Um número alto significa que não é caso isolado.
          </p>
        </div>
      )}

      {/* 2. Onde as pessoas travam. */}
      {resumo?.friccao?.length > 0 && (
        <div className="rh-card">
          <h3>🟠 Onde as pessoas travam ({resumo.friccao.length})</h3>
          <table className="rh-tabela">
            <thead><tr><th>O que aconteceu</th><th>Página</th><th>Vezes</th></tr></thead>
            <tbody>
              {resumo.friccao.map((f, i) => (
                <tr key={i}>
                  <td>{f.evento}</td><td>{f.pagina || '—'}</td>
                  <td><strong>{f.ocorrencias}</strong></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* 3. O que está lento — por MEDIANA, não média: uma chamada de 40s
          distorceria a média e faria parecer que tudo está lento. */}
      {resumo?.lentas?.length > 0 && (
        <div className="rh-card">
          <h3>🟣 O que está lento no aparelho das pessoas ({resumo.lentas.length})</h3>
          <table className="rh-tabela">
            <thead><tr>
              <th>Página</th><th>Tempo típico</th><th>Pior caso</th><th>Amostras</th>
            </tr></thead>
            <tbody>
              {resumo.lentas.map((l, i) => (
                <tr key={i}>
                  <td className="dash-quebra">{l.pagina || '—'}</td>
                  <td><strong>{(l.mediana_ms / 1000).toFixed(1)}s</strong></td>
                  <td>{(l.pior_ms / 1000).toFixed(1)}s</td>
                  <td>{l.amostras}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="explica">
            <strong>Tempo típico</strong> é a mediana — o que a maioria das pessoas
            realmente espera. A média seria distorcida por um único caso lento.
          </p>
        </div>
      )}

      {/* Alertas ANTES da lista crua e da retenção: é o que o RH mais usa. */}
      <AlertasTelemetria />

      <details className="rh-card">
        <summary><strong>🔎 Todos os eventos</strong> — filtrar e exportar</summary>
        <div className="rh-grid-2">
          <label className="campo">
            <span className="rotulo">Tipo</span>
            <select value={filtros.tipo}
                    onChange={(e) => setFiltros({ ...filtros, tipo: e.target.value })}>
              {TIPOS.map(([v, r]) => <option key={v} value={v}>{r}</option>)}
            </select>
          </label>
          <label className="campo">
            <span className="rotulo">Origem</span>
            <select value={filtros.origem}
                    onChange={(e) => setFiltros({ ...filtros, origem: e.target.value })}>
              {ORIGENS.map(([v, r]) => <option key={v} value={v}>{r}</option>)}
            </select>
          </label>
        </div>
        {eventos === null ? <p className="explica">Carregando…</p> : (
          <DashPlanilha id="telemetria" colunas={COLUNAS} dados={eventos}
                        chaveLinha={(e) => e.id}
                        linhaExpandida={(e) => <DetalheEvento evento={e} />}
                        vazio="Nenhum evento no período." />
        )}
      </details>

      <Retencao aoMudar={carregar} />
    </>
  )
}

function DetalheEvento({ evento }) {
  return (
    <div>
      <p><strong>Evento:</strong> {evento.evento} · <strong>Sessão:</strong>{' '}
        <code>{evento.sessao || '—'}</code></p>
      {evento.usuario_rh && <p><strong>Usuário:</strong> {evento.usuario_rh}</p>}
      <p><strong>Navegador:</strong> {evento.user_agent || '—'}</p>
      {/* Só o prefixo do IP é guardado — ver LGPD em models/telemetria.py */}
      <p><strong>Rede:</strong> {evento.ip_prefixo || '—'}{' '}
        <span className="explica">(só o prefixo, por LGPD)</span></p>
      {evento.detalhe && (
        <pre className="bloco-codigo">{JSON.stringify(evento.detalhe, null, 2)}</pre>
      )}
    </div>
  )
}

// Retenção e expurgo — os dois pedidos do Bruno: mudar o prazo padrão e poder
// apagar um intervalo específico (ex.: os testes de ontem que poluíram os
// números).
function Retencao({ aoMudar }) {
  const [dias, setDias] = useState('')
  const [intervalo, setIntervalo] = useState({ desde: '', ate: '' })
  const [ocupado, setOcupado] = useState(false)
  const [msg, setMsg] = useState(null)

  useEffect(() => {
    api.telemetriaRetencao().then((r) => setDias(String(r.dias))).catch(() => {})
  }, [])

  const salvar = async () => {
    setOcupado(true); setMsg(null)
    try {
      await api.salvarTelemetriaRetencao(Number(dias))
      setMsg({ tipo: 'ok', texto: `Retenção salva: ${dias} dias. O expurgo roda diariamente.` })
    } catch {
      setMsg({ tipo: 'erro', texto: 'Não foi possível salvar a retenção.' })
    } finally { setOcupado(false) }
  }

  const expurgar = async () => {
    if (!intervalo.desde && !intervalo.ate) {
      setMsg({ tipo: 'erro', texto: 'Informe pelo menos uma das datas do intervalo.' })
      return
    }
    if (!window.confirm(`Apagar a telemetria de ${intervalo.desde || 'o início'} até `
                        + `${intervalo.ate || 'agora'}? Isto não tem volta.`)) return
    setOcupado(true); setMsg(null)
    try {
      const r = await api.telemetriaExpurgar({
        desde: intervalo.desde || null, ate: intervalo.ate || null,
      })
      setMsg({ tipo: 'ok', texto: `${r.removidos} evento(s) apagado(s).` })
      aoMudar()
    } catch (e) {
      setMsg({ tipo: 'erro', texto: e.detail === 'informe_o_intervalo'
        ? 'Informe o intervalo de datas.' : 'Não foi possível apagar agora.' })
    } finally { setOcupado(false) }
  }

  return (
    <details className="rh-card">
      <summary><strong>🗑️ Retenção e limpeza</strong></summary>
      <p className="explica">
        A telemetria é apagada automaticamente depois do prazo abaixo — o expurgo
        roda uma vez por dia, junto com o de arquivos.
      </p>

      <div className="rh-grid-2">
        <label className="campo">
          <span className="rotulo">Guardar por (dias)</span>
          <input type="number" min="1" max="3650" value={dias}
                 onChange={(e) => setDias(e.target.value)} />
          <small className="explica">Padrão: 365 (um ano), o que permite comparar
            períodos do ano anterior.</small>
        </label>
        <label className="campo">
          <span className="rotulo">&nbsp;</span>
          <button className="btn-secundario" onClick={salvar} disabled={ocupado || !dias}>
            Salvar retenção
          </button>
        </label>
      </div>

      <h4>Apagar um intervalo específico</h4>
      <p className="explica">
        Útil depois de testes que poluíram os números. Fica registrado na
        auditoria: quem apagou, quando e quanto.
      </p>
      <div className="rh-grid-2">
        <label className="campo"><span className="rotulo">De</span>
          <input type="date" value={intervalo.desde}
                 onChange={(e) => setIntervalo({ ...intervalo, desde: e.target.value })} />
        </label>
        <label className="campo"><span className="rotulo">Até</span>
          <input type="date" value={intervalo.ate}
                 onChange={(e) => setIntervalo({ ...intervalo, ate: e.target.value })} />
        </label>
      </div>
      <button className="btn-secundario" onClick={expurgar} disabled={ocupado}>
        Apagar telemetria deste intervalo
      </button>
      {msg && <div className={msg.tipo === 'ok' ? 'sucesso' : 'alerta'}>{msg.texto}</div>}
    </details>
  )
}
