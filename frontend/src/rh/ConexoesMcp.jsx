import { useEffect, useState } from 'react'
import { rh as api } from '../api.js'
import { fmtDataHora } from '../fmt.js'

// Conexões do assistente (MCP com OAuth, v3.15).
//
// Duas diferenças em relação à tela de credenciais de máquina logo acima, e as
// duas mudam o que a tela precisa fazer:
//
// 1. **NÃO há botão de criar.** A conexão nasce quando a pessoa faz login no
//    Claude e autoriza — não existe nada para emitir aqui. Um formulário de
//    criação seria um controle que não decide nada.
// 2. **Cortar é a razão de existir.** A pergunta do desenho é "se vazar hoje à
//    noite, como eu corto?". Revogar aqui derruba a conexão na chamada
//    seguinte, sem esperar o token expirar.
export default function ConexoesMcp() {
  const [conexoes, setConexoes] = useState(null)
  const [erro, setErro] = useState(null)
  const [msg, setMsg] = useState(null)

  const recarregar = () => api.conexoesMcp().then(setConexoes)
  useEffect(() => {
    // Estado de erro SEPARADO, e não `.catch(() => setConexoes(null))`: com
    // `null` a tela ficaria em "Carregando…" para sempre, indistinguível de
    // rede lenta e sem como tentar de novo (v2.46).
    recarregar().catch((e) => setErro(e.detail || e.message))
  }, [])

  const revogar = async (c) => {
    if (!window.confirm(
      `Cortar o acesso de ${c.pessoa} pelo ${c.aplicativo}?\n\n` +
      'O acesso dela ao portal pela tela continua normal. Para voltar a usar o ' +
      'assistente, ela precisará autorizar de novo.')) return
    setErro(null)
    try {
      await api.revogarConexaoMcp(c.id)
      await recarregar()
      setMsg(`Acesso de ${c.pessoa} cortado.`)
    } catch (e) {
      setErro(e.detail || e.message)
    }
  }

  if (erro && conexoes === null) {
    return (
      <div className="rh-card">
        <h3>🔗 Conexões do assistente</h3>
        <p className="alerta">Não foi possível carregar: {String(erro)}</p>
        <button className="btn-secundario" onClick={() => {
          setErro(null)
          recarregar().catch((e) => setErro(e.detail || e.message))
        }}>Tentar de novo</button>
      </div>
    )
  }

  return (
    <div className="rh-card">
      <h3>🔗 Conexões do assistente</h3>
      <p className="explica">
        Quem conectou o portal ao Claude. A conexão nasce quando a pessoa faz
        login e autoriza — não há nada para criar aqui. O assistente age com um
        perfil <strong>menor</strong> que o dela: efetivar, desligar, decidir
        reembolso, assinar e exportar a base continuam só pela tela.
      </p>
      {msg && <p className="sucesso">{msg}</p>}
      {erro && <p className="alerta">{String(erro)}</p>}

      {conexoes === null && <p className="explica">Carregando…</p>}

      {conexoes?.length === 0 && (
        <p className="explica">
          Ninguém conectou o assistente ainda. Para conectar, a pessoa adiciona
          o endereço do portal como conector no Claude e faz login.
        </p>
      )}

      {conexoes?.length > 0 && (
        <div className="dash-scroll">
          <table className="rh-tabela">
            <thead>
              <tr>
                <th>Pessoa</th>
                <th>Aplicativo</th>
                <th>Autorizou em</th>
                <th>Último uso</th>
                <th>Situação</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {conexoes.map((c) => (
                <tr key={c.id}>
                  <td>{c.pessoa}</td>
                  <td>{c.aplicativo}</td>
                  <td>{fmtDataHora(c.criado_em)}</td>
                  {/* "—" e não "nunca": o carimbo é de minuto, então uma conexão
                      recém-criada pode ainda não ter registro de uso. */}
                  <td>{c.usado_em ? fmtDataHora(c.usado_em) : '—'}</td>
                  <td>
                    {c.valida
                      ? <span className="chip" style={{ '--chip-cor': 'var(--verde)' }}>ativa</span>
                      : <span className="chip" title={motivoLegivel(c)}>
                          revogada
                        </span>}
                  </td>
                  <td>
                    {c.valida && (
                      <button className="btn-remover" onClick={() => revogar(c)}>
                        Cortar acesso
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}

// O motivo importa: "reuso detectado" significa que o sistema viu uma credencial
// antiga sendo reapresentada — sinal de cópia roubada — e cortou sozinho. Sem
// essa distinção, quem lê a tela acha que alguém revogou à mão.
function motivoLegivel(c) {
  const quando = c.revogado_em ? ` em ${fmtDataHora(c.revogado_em)}` : ''
  const por = c.revogado_por ? ` por ${c.revogado_por}` : ''
  const motivos = {
    usuario: 'cortada pelo painel',
    reuso_detectado: 'cortada pelo sistema: uma credencial antiga foi reapresentada (possível cópia roubada)',
    codigo_reusado: 'cortada pelo sistema: o código de autorização foi usado duas vezes',
    conta_sem_acesso: 'cortada porque a conta foi desativada ou mudou de perfil',
  }
  return (motivos[c.revogado_motivo] || 'revogada') + quando + por
}
