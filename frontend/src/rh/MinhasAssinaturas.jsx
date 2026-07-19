import { useEffect, useState } from 'react'
import { fmtData } from '../fmt.js'
import { rh as api } from '../api.js'

// Fila do usuário do RH: documentos de roteiro multi-signatário aguardando a
// assinatura DELE. Assina logado, provando presença com a senha.
export default function MinhasAssinaturas() {
  const [pendentes, setPendentes] = useState(null)
  const [assinando, setAssinando] = useState(null) // etapa_id em assinatura
  const [senha, setSenha] = useState('')
  const [msg, setMsg] = useState(null)

  const recarregar = () => api.minhasAssinaturas().then((r) => setPendentes(r.pendentes))
  useEffect(() => { recarregar().catch(() => setPendentes([])) }, [])

  return (
    <main className="rh-painel">
      <header className="rh-topo"><h1>✍️ Aguardando minha assinatura</h1><div /></header>
      <p className="explica">Documentos que dependem da sua assinatura, na sua vez do roteiro.
        Você assina aqui mesmo, logado, confirmando com a sua senha.</p>
      {msg && <div className={msg.tipo === 'erro' ? 'alerta' : 'sucesso'}>{msg.texto}</div>}

      {!pendentes ? <p>Carregando…</p> : pendentes.length === 0 ? (
        <p className="explica centro">Nada aguardando a sua assinatura. 🎉</p>
      ) : (
        <table className="rh-tabela">
          <thead><tr><th>Documento</th><th>Colaborador</th><th>Meu papel</th><th>Desde</th><th></th></tr></thead>
          <tbody>
            {pendentes.map((p) => (
              <tr key={p.etapa_id}>
                <td><strong>{p.titulo}</strong></td>
                <td>{p.colaborador}</td>
                <td>{p.papel}</td>
                <td>{fmtData(p.criado_em)}</td>
                <td className="acoes-candidato">
                  {assinando === p.etapa_id ? (
                    <span className="rejeicao">
                      <input type="password" placeholder="Sua senha" value={senha} autoFocus
                             onChange={(e) => setSenha(e.target.value)} />
                      <button className="btn-principal btn-mini" onClick={async () => {
                        setMsg(null)
                        try {
                          await api.assinarEtapaRh(p.etapa_id, senha)
                          setAssinando(null); setSenha('')
                          setMsg({ tipo: 'ok', texto: `Você assinou "${p.titulo}" como ${p.papel}.` })
                          await recarregar()
                        } catch (e) {
                          setMsg({ tipo: 'erro', texto: e.detail === 'senha_invalida'
                            ? 'Senha incorreta.' : `Não foi possível assinar (${e.detail || e.message}).` })
                        }
                      }}>Confirmar</button>
                      <button className="btn-link" onClick={() => { setAssinando(null); setSenha('') }}>cancelar</button>
                    </span>
                  ) : (
                    <button className="btn-principal btn-mini"
                            onClick={() => { setAssinando(p.etapa_id); setSenha('') }}>✍️ Assinar</button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </main>
  )
}
