import { useEffect, useState } from 'react'
import { fmtData } from '../fmt.js'
import { rh as api } from '../api.js'
import { Papeis, Assinantes } from './Config.jsx'

// Central de assinaturas (menu próprio): aguardando minha assinatura, o que já
// assinei, e gerenciar todos os roteiros. Antes espalhado em "Minhas
// assinaturas" e dentro de Configurações.
export default function Assinaturas() {
  const [aba, setAba] = useState('pendentes')
  return (
    <main className="rh-painel">
      <header className="rh-topo"><h1>✍️ Assinaturas</h1><div /></header>
      <nav className="rh-subnav">
        <button className={`rh-subnav-item ${aba === 'pendentes' ? 'ativo' : ''}`}
                onClick={() => setAba('pendentes')}>⏳ Aguardando minha assinatura</button>
        <button className={`rh-subnav-item ${aba === 'feitas' ? 'ativo' : ''}`}
                onClick={() => setAba('feitas')}>✅ Já assinei</button>
        <button className={`rh-subnav-item ${aba === 'gerenciar' ? 'ativo' : ''}`}
                onClick={() => setAba('gerenciar')}>📋 Gerenciar roteiros</button>
        <button className={`rh-subnav-item ${aba === 'configurar' ? 'ativo' : ''}`}
                onClick={() => setAba('configurar')}>⚙️ Papéis e assinantes</button>
      </nav>
      {aba === 'pendentes' && <Pendentes />}
      {aba === 'feitas' && <Feitas />}
      {aba === 'gerenciar' && <Gerenciar />}
      {aba === 'configurar' && <><Assinantes /><Papeis /></>}
    </main>
  )
}

function Pendentes() {
  const [pendentes, setPendentes] = useState(null)
  const [assinando, setAssinando] = useState(null)
  const [senha, setSenha] = useState('')
  const [msg, setMsg] = useState(null)
  const recarregar = () => api.minhasAssinaturas().then((r) => setPendentes(r.pendentes))
  useEffect(() => { recarregar().catch(() => setPendentes([])) }, [])

  return (
    <>
      <p className="explica">Documentos que dependem da sua assinatura, na sua vez do roteiro.
        Você assina aqui, logado, confirmando com a sua senha.</p>
      {msg && <div className={msg.tipo === 'erro' ? 'alerta' : 'sucesso'}>{msg.texto}</div>}
      {!pendentes ? <p>Carregando…</p> : pendentes.length === 0 ? (
        <p className="explica centro">Nada aguardando a sua assinatura. 🎉</p>
      ) : (
        <table className="rh-tabela">
          <thead><tr><th>Documento</th><th>Colaborador</th><th>Meu papel</th><th>Desde</th><th></th></tr></thead>
          <tbody>
            {pendentes.map((p) => (
              <tr key={p.etapa_id}>
                <td><strong>{p.titulo}</strong></td><td>{p.colaborador}</td><td>{p.papel}</td>
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
    </>
  )
}

function Feitas() {
  const [feitas, setFeitas] = useState(null)
  useEffect(() => { api.minhasAssinaturasFeitas().then((r) => setFeitas(r.feitas)).catch(() => setFeitas([])) }, [])
  return (
    <>
      <p className="explica">Documentos que você já assinou.</p>
      {!feitas ? <p>Carregando…</p> : feitas.length === 0 ? (
        <p className="explica centro">Você ainda não assinou nenhum documento por aqui.</p>
      ) : (
        <table className="rh-tabela">
          <thead><tr><th>Documento</th><th>Colaborador</th><th>Meu papel</th><th>Assinado em</th><th>Documento</th></tr></thead>
          <tbody>
            {feitas.map((f) => (
              <tr key={f.etapa_id}>
                <td><strong>{f.titulo}</strong></td><td>{f.colaborador}</td><td>{f.papel}</td>
                <td>{fmtData(f.assinado_em)}</td>
                <td>{f.documento_concluido
                  ? <span className="chip" style={{ '--chip-cor': '#0fb257' }}>✅ concluído</span>
                  : <span className="chip" style={{ '--chip-cor': '#3b7dd8' }}>aguardando outros</span>}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </>
  )
}

const CORES = { rascunho: '#f0ad4e', aguardando: '#3b7dd8', concluida: '#0fb257',
                pendente_rh: '#d9534f', cancelada: '#889', expirada: '#889' }
const ROTULO = { rascunho: 'Rascunho', aguardando: 'Assinando', concluida: 'Concluído',
                 pendente_rh: 'Ação do RH', cancelada: 'Cancelado', expirada: 'Expirado' }

function Gerenciar() {
  const [sols, setSols] = useState(null)
  const [msg, setMsg] = useState(null)
  const recarregar = () => api.todasSolicitacoes().then((r) => setSols(r.solicitacoes))
  useEffect(() => { recarregar().catch(() => setSols([])) }, [])
  return (
    <>
      <p className="explica">Todos os roteiros de assinatura em andamento e concluídos. Para montar
        um roteiro novo, abra a página do colaborador.</p>
      {msg && <div className={msg.tipo === 'erro' ? 'alerta' : 'sucesso'}>{msg.texto}</div>}
      {!sols ? <p>Carregando…</p> : sols.length === 0 ? (
        <p className="explica centro">Nenhum roteiro ainda.</p>
      ) : (
        <table className="rh-tabela">
          <thead><tr><th>Documento</th><th>Colaborador</th><th>Situação</th><th>Progresso</th><th>Criado</th><th></th></tr></thead>
          <tbody>
            {sols.map((s) => (
              <tr key={s.id}>
                <td><strong>{s.titulo}</strong></td><td>{s.colaborador}</td>
                <td><span className="chip" style={{ '--chip-cor': CORES[s.status] || '#889' }}>
                  {ROTULO[s.status] || s.status}</span></td>
                <td>{s.progresso}</td><td>{fmtData(s.criado_em)}</td>
                <td className="acoes-candidato">
                  {['rascunho', 'aguardando', 'pendente_rh'].includes(s.status) && (
                    <button className="btn-link" onClick={async () => {
                      if (!window.confirm('Cancelar este roteiro?')) return
                      try { await api.cancelarRoteiro(s.id, 'cancelado pelo RH'); await recarregar() }
                      catch (e) { setMsg({ tipo: 'erro', texto: `Não foi possível (${e.detail || e.message}).` }) }
                    }}>cancelar</button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </>
  )
}
