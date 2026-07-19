import { useEffect, useState } from 'react'
import { fmtData } from '../fmt.js'
import { rh as api } from '../api.js'
import { ResultadoDisc, ResultadoSituacional } from '../ResultadoTeste.jsx'

// Página de TESTES: gestão dos links de testagem avulsa (criar, ativar/
// desativar, copiar URL) e acompanhamento dos participantes com os resultados.
// Diferente da admissão, aqui o participante entra só com o nome e VÊ o
// próprio resultado — serve para o RH validar o instrumento ou aplicar em quem
// já é da casa.
export default function TestagemRH() {
  const [links, setLinks] = useState(null)
  const [novoNome, setNovoNome] = useState('')
  const [criando, setCriando] = useState(false)
  const [aberto, setAberto] = useState(null) // link_id expandido
  const [participantes, setParticipantes] = useState(null)
  const [msg, setMsg] = useState(null)

  const recarregar = () => api.testagemLinks().then((r) => setLinks(r.links))
  useEffect(() => { recarregar() }, [])

  const abrir = async (id) => {
    if (aberto === id) { setAberto(null); return }
    setAberto(id); setParticipantes(null)
    setParticipantes(await api.testagemParticipantes(id))
  }

  const copiar = (e, url) => {
    navigator.clipboard.writeText(url)
    const btn = e.currentTarget
    const original = btn.textContent
    btn.textContent = '✓ Copiado!'
    setTimeout(() => { btn.textContent = original }, 2000)
  }

  return (
    <main className="rh-painel">
      <header className="rh-topo">
        <h1>🧪 Testes</h1>
        <div />
      </header>
      <p className="explica">Links de <strong>testagem avulsa</strong>: a pessoa entra só com o
        nome (sem CPF/e-mail), responde ao DISC e ao Situacional e <strong>vê o próprio
        resultado</strong> na tela. Use para testar o sistema ou aplicar fora da admissão.
        Os testes da admissão continuam no convite/página do candidato, com resultado
        restrito ao RH.</p>
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
                  <button className="btn-secundario btn-mini"
                          onClick={() => abrir(l.id)}>
                    {aberto === l.id ? 'Fechar' : '👁 Resultados'}</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {aberto && (
        !participantes ? <p>Carregando participantes…</p> : (
          <div className="rh-card">
            <h3>Participantes — {participantes.link.nome}</h3>
            {participantes.participantes.length === 0 ? (
              <p className="explica">Ninguém participou ainda por este link.</p>
            ) : participantes.participantes.map((p) => (
              <Participante key={p.id} p={p} perfis={participantes.perfis} />
            ))}
          </div>
        )
      )}
    </main>
  )
}

const STATUS_TESTE = {
  pendente: 'não começou', em_andamento: 'em andamento',
  concluido: 'concluído', expirado: 'tempo esgotado (pontuado parcial)',
}
const NOMES = { disc: 'Inventário DISC', situacional: 'Teste Situacional' }

function Participante({ p, perfis }) {
  const [aberto, setAberto] = useState(false)
  const disc = p.testes.find((t) => t.tipo === 'disc')
  const sit = p.testes.find((t) => t.tipo === 'situacional')
  const resumo = p.testes.map((t) => `${NOMES[t.tipo]}: ${STATUS_TESTE[t.status]}`).join(' · ')
  return (
    <div className="disc-bloco">
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                    flexWrap: 'wrap', gap: '.5rem' }}>
        <span><strong>{p.nome}</strong>{' '}
          <span className="explica" style={{ margin: 0 }}>
            — {fmtData(p.criado_em)} · {resumo}</span></span>
        <button className="btn-link" onClick={() => setAberto(!aberto)}>
          {aberto ? 'esconder' : 'ver resultado'}</button>
      </div>
      {aberto && (
        <>
          {disc?.resultado ? <ResultadoDisc resultado={disc.resultado} perfis={perfis} />
            : <p className="explica">DISC ainda sem resultado.</p>}
          {sit?.resultado ? <ResultadoSituacional resultado={sit.resultado} />
            : <p className="explica">Situacional ainda sem resultado.</p>}
        </>
      )}
    </div>
  )
}
