import { useEffect, useMemo, useState } from 'react'
import { fmtData } from '../fmt.js'
import { rh as api } from '../api.js'
import { ResultadoDisc, ResultadoSituacional } from '../ResultadoTeste.jsx'
import { ComportamentoTeste } from './Detalhe.jsx'

// Página de TESTES: dash unificado (admissão + testagem avulsa) com status,
// duração, resultado e comportamento (telemetria), reset para refazer, e a
// gestão dos links de testagem avulsa.
export default function TestagemRH({ aoAbrirPessoa }) {
  const [aba, setAba] = useState('dash') // dash | links
  return (
    <main className="rh-painel">
      <header className="rh-topo">
        <h1>🧪 Testes</h1>
        <div />
      </header>
      <nav className="rh-subnav">
        <button className={`rh-subnav-item ${aba === 'dash' ? 'ativo' : ''}`}
                onClick={() => setAba('dash')}>📊 Acompanhamento</button>
        <button className={`rh-subnav-item ${aba === 'links' ? 'ativo' : ''}`}
                onClick={() => setAba('links')}>🔗 Links de testagem</button>
      </nav>
      {aba === 'dash' ? <Dash aoAbrirPessoa={aoAbrirPessoa} /> : <Links />}
    </main>
  )
}

const NOMES = { disc: 'DISC', situacional: 'Situacional' }
const STATUS = {
  pendente: ['⏳ não começou', '#889'],
  em_andamento: ['▶️ em andamento', '#f0ad4e'],
  concluido: ['✅ concluído', '#0fb257'],
  expirado: ['⌛ tempo esgotado', '#d9534f'],
}
const mmss = (s) => s == null ? '—'
  : `${String(Math.floor(s / 60)).padStart(2, '0')}:${String(s % 60).padStart(2, '0')}`

function Dash({ aoAbrirPessoa }) {
  const [dados, setDados] = useState(null)
  const [origem, setOrigem] = useState('')
  const [tipo, setTipo] = useState('')
  const [status, setStatus] = useState('')
  const [busca, setBusca] = useState('')
  const [aberto, setAberto] = useState(null) // teste_id expandido
  const [msg, setMsg] = useState(null)

  const recarregar = () => api.testesDash().then(setDados)
  useEffect(() => { recarregar() }, [])
  if (!dados) return <p>Carregando…</p>

  const itens = dados.itens.filter((i) =>
    (!origem || i.origem === origem)
    && (!tipo || i.tipo === tipo)
    && (!status || i.status === status)
    && (!busca.trim() || i.nome.toLowerCase().includes(busca.trim().toLowerCase())))

  const m = dados.metricas
  const cards = [
    ['Testes', m.total, ''],
    ['Concluídos', m.concluidos, ''],
    ['Em andamento', m.em_andamento, m.em_andamento > 0 ? 'destaque' : ''],
    ['Aguardando', m.pendentes, ''],
    ['Tempo médio', m.tempo_medio_s == null ? '—' : mmss(m.tempo_medio_s), ''],
    ['Com saídas de tela', m.com_alerta, m.com_alerta > 0 ? 'destaque' : ''],
  ]

  const resetar = async (i) => {
    if (!window.confirm(`Resetar o teste ${NOMES[i.tipo]} de ${i.nome}?\n\nAs respostas e o resultado atuais são zerados (ficam preservados na auditoria) e a pessoa pode fazer de novo pelo mesmo link.`)) return
    setMsg(null)
    try {
      if (i.origem === 'admissao') await api.resetarTeste(i.pessoa_id, i.tipo)
      else await api.resetarTesteTestagem(i.pessoa_id, i.tipo)
      setMsg({ tipo: 'ok', texto: `Teste ${NOMES[i.tipo]} de ${i.nome} resetado — a pessoa já pode refazer.` })
      await recarregar()
    } catch (e) {
      setMsg({ tipo: 'erro', texto: `Não foi possível resetar (${e.detail || e.message}).` })
    }
  }

  return (
    <>
      <div className="rh-metricas">
        {cards.map(([rotulo, valor, extra]) => (
          <div className={`rh-metrica ${extra}`} key={rotulo}>
            <strong>{valor}</strong><span>{rotulo}</span>
          </div>
        ))}
      </div>
      {msg && <div className={msg.tipo === 'erro' ? 'alerta' : 'sucesso'}>{msg.texto}</div>}
      <div className="rh-card rh-lote">
        <input placeholder="🔎 Buscar por nome…" value={busca} style={{ maxWidth: 220 }}
               onChange={(e) => setBusca(e.target.value)} />
        <select value={origem} onChange={(e) => setOrigem(e.target.value)}>
          <option value="">Origem: todas</option>
          <option value="admissao">Admissão</option>
          <option value="testagem">Testagem avulsa</option>
        </select>
        <select value={tipo} onChange={(e) => setTipo(e.target.value)}>
          <option value="">Teste: todos</option>
          <option value="disc">DISC</option>
          <option value="situacional">Situacional</option>
        </select>
        <select value={status} onChange={(e) => setStatus(e.target.value)}>
          <option value="">Status: todos</option>
          {Object.entries(STATUS).map(([v, [r]]) => <option key={v} value={v}>{r}</option>)}
        </select>
        <span className="explica" style={{ margin: 0 }}>{itens.length} teste(s)</span>
      </div>

      {itens.length === 0 ? <p className="explica centro">Nenhum teste com esses filtros.</p> : (
        <table className="rh-tabela">
          <thead><tr><th>Pessoa</th><th>Teste</th><th>Status</th><th>Duração</th>
            <th>Resultado</th><th>Comportamento</th><th></th></tr></thead>
          <tbody>
            {itens.map((i) => {
              const [rotulo, cor] = STATUS[i.status] || [i.status, '#889']
              const c = i.comportamento
              return (
                <FragmentoLinha key={i.teste_id} aberto={aberto === i.teste_id}>
                  <tr>
                    <td>
                      <strong>{i.nome}</strong><br />
                      <small>{i.origem === 'admissao' ? `admissão · ${i.contexto}` : `testagem · ${i.contexto}`}</small>
                    </td>
                    <td>{NOMES[i.tipo]}</td>
                    <td><span className="chip" style={{ '--chip-cor': cor }}>{rotulo}</span><br />
                      <small>{i.concluido_em ? fmtData(i.concluido_em) : i.iniciado_em ? `início ${fmtData(i.iniciado_em)}` : ''}</small></td>
                    <td>{mmss(i.duracao_s)}</td>
                    <td>{!i.resumo ? '—' : i.tipo === 'disc'
                      ? <strong>{i.resumo.perfil}</strong>
                      : <><strong>{i.resumo.percentual}%</strong> ({i.resumo.faixa})</>}</td>
                    <td>{!c ? '—' : c.saidas_da_tela > 0 || c.tentativas_print > 0
                      ? <span title={`${c.saidas_da_tela} saída(s) de tela · ${c.tentativas_print} print(s) · ${c.copiar_colar} copiar/colar`}>
                          ⚠️ {c.saidas_da_tela} saída(s)</span>
                      : '✔ sem alertas'}</td>
                    <td className="acoes-candidato">
                      <button className="btn-secundario btn-mini"
                              onClick={() => setAberto(aberto === i.teste_id ? null : i.teste_id)}>
                        {aberto === i.teste_id ? 'Fechar' : '👁 Detalhes'}</button>
                      {i.origem === 'admissao' && aoAbrirPessoa && (
                        <button className="btn-secundario btn-mini" title="Abrir a página do candidato"
                                onClick={() => aoAbrirPessoa(i.pessoa_id)}>Abrir pessoa</button>
                      )}
                      {i.status !== 'pendente' && (
                        <button className="btn-rejeitar btn-mini"
                                title="Zera respostas e resultado para a pessoa refazer (o anterior fica na auditoria)"
                                onClick={() => resetar(i)}>🔁 Resetar</button>
                      )}
                    </td>
                  </tr>
                  {aberto === i.teste_id && (
                    <tr className="linha-form-inline">
                      <td colSpan={7}>
                        <DetalheTeste item={i} perfis={dados.perfis} />
                      </td>
                    </tr>
                  )}
                </FragmentoLinha>
              )
            })}
          </tbody>
        </table>
      )}
    </>
  )
}

// tr + linha expandida precisam de um Fragment com key — invólucro simples
function FragmentoLinha({ children }) { return <>{children}</> }

function DetalheTeste({ item, perfis }) {
  return (
    <div className="form-inline-conteudo">
      {item.tipo === 'disc'
        ? (item.resultado?.percentuais
            ? <ResultadoDisc resultado={item.resultado} perfis={perfis} />
            : <p className="explica">Sem resultado ainda ({item.respondidas || 0} respondidas).</p>)
        : (item.resultado?.percentual != null
            ? <ResultadoSituacional resultado={item.resultado} />
            : <p className="explica">Sem resultado ainda ({item.respondidas || 0} respondidas).</p>)}
      {item.comportamento
        ? <ComportamentoTeste teste={item} />
        : <p className="explica">Sem telemetria de comportamento registrada.</p>}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Gestão dos links de testagem avulsa (participante entra só com o nome e vê
// o próprio resultado)
// ---------------------------------------------------------------------------

function Links() {
  const [links, setLinks] = useState(null)
  const [novoNome, setNovoNome] = useState('')
  const [criando, setCriando] = useState(false)
  const [msg, setMsg] = useState(null)

  const recarregar = () => api.testagemLinks().then((r) => setLinks(r.links))
  useEffect(() => { recarregar() }, [])

  const copiar = (e, url) => {
    navigator.clipboard.writeText(url)
    const btn = e.currentTarget
    const original = btn.textContent
    btn.textContent = '✓ Copiado!'
    setTimeout(() => { btn.textContent = original }, 2000)
  }

  return (
    <>
      <p className="explica">Links de <strong>testagem avulsa</strong>: a pessoa entra só com o
        nome (sem CPF/e-mail), responde ao DISC e ao Situacional e <strong>vê o próprio
        resultado</strong>. Os resultados aparecem na aba 📊 Acompanhamento. Os testes da
        admissão continuam no convite/página do candidato, com resultado restrito ao RH.</p>
      {msg && <div className={msg.tipo === 'erro' ? 'alerta' : 'sucesso'}>{msg.texto}</div>}

      <div className="rh-card rh-lote">
        <strong>Novo link:</strong>
        <input placeholder="Nome do link (ex.: Testagem interna julho)" value={novoNome}
               style={{ maxWidth: 320 }} onChange={(e) => setNovoNome(e.target.value)} />
        <button className="btn-principal btn-mini" disabled={criando || !novoNome.trim()}
                onClick={async () => {
                  setCriando(true); setMsg(null)
                  try {
                    await api.testagemCriarLink(novoNome.trim())
                    setNovoNome('')
                    await recarregar()
                    setMsg({ tipo: 'ok', texto: 'Link criado — copie a URL e envie para quem for testar.' })
                  } catch (e) {
                    setMsg({ tipo: 'erro', texto: `Não foi possível criar (${e.detail || e.message}).` })
                  } finally { setCriando(false) }
                }}>{criando ? 'Criando…' : '+ Criar link'}</button>
      </div>

      {!links ? <p>Carregando…</p> : links.length === 0 ? (
        <p className="explica centro">Nenhum link de testagem ainda. Crie o primeiro acima.</p>
      ) : (
        <table className="rh-tabela">
          <thead>
            <tr><th>Link</th><th>Situação</th><th>Participantes</th><th>Criado</th><th></th></tr>
          </thead>
          <tbody>
            {links.map((l) => (
              <tr key={l.id}>
                <td><strong>{l.nome}</strong><br />
                  <small style={{ wordBreak: 'break-all' }}>{l.url}</small></td>
                <td><span className="chip" style={{ '--chip-cor': l.ativo ? '#0fb257' : '#889' }}>
                  {l.ativo ? '🟢 Ativo' : '⚪ Desativado'}</span></td>
                <td>{l.participantes} ({l.concluidos} concluíram)</td>
                <td>{fmtData(l.criado_em)}</td>
                <td className="acoes-candidato">
                  <button className="btn-secundario btn-mini"
                          title="Copia a URL pública para enviar (WhatsApp/e-mail)"
                          onClick={(e) => copiar(e, l.url)}>📋 Copiar link</button>
                  <button className="btn-secundario btn-mini"
                          title={l.ativo ? 'Ninguém mais consegue entrar por este link até reativar'
                                         : 'Volta a aceitar participantes'}
                          onClick={async () => {
                            await api.testagemEditarLink(l.id, { ativo: !l.ativo })
                            await recarregar()
                          }}>{l.ativo ? '⏸ Desativar' : '▶ Ativar'}</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </>
  )
}
