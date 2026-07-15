import { useEffect, useRef, useState } from 'react'
import { rh as api } from '../api.js'
import Espera from '../Espera.jsx'

const STATUS_OPCOES = [
  ['', 'Todos os status'], ['convidado', 'Convidado'], ['preenchendo', 'Preenchendo'],
  ['aguardando_assinatura', 'Assinando'], ['docs_pendentes', 'Enviando docs'],
  ['envio_concluido', 'Aguardando revisão'], ['em_revisao', 'Em revisão'],
  ['aprovado', 'Aprovado'], ['reprovado_pendencias', 'Pendências'], ['expurgado', 'Expurgado'],
]

const fmtCpf = (c) => c && c.length === 11
  ? `${c.slice(0, 3)}.${c.slice(3, 6)}.${c.slice(6, 9)}-${c.slice(9)}` : (c || '—')

// Dash de colaboradores: filtros + tabela + exportação Excel completa.
export default function Colaboradores({ aoVoltar, aoAbrir }) {
  const [lista, setLista] = useState(null)
  const [status, setStatus] = useState('')
  const [busca, setBusca] = useState('')
  const [exportando, setExportando] = useState(false)
  const [erro, setErro] = useState(null)
  const timer = useRef(null)

  const carregar = (f = {}) => {
    api.colaboradores({ status: f.status ?? status, busca: f.busca ?? busca })
      .then(setLista).catch(() => setErro('Não foi possível carregar a lista.'))
  }
  useEffect(() => { carregar() }, [])

  const aoBuscar = (texto) => {
    setBusca(texto)
    clearTimeout(timer.current)
    timer.current = setTimeout(() => carregar({ busca: texto }), 400)
  }

  const exportar = async () => {
    setErro(null); setExportando(true)
    try {
      const blob = await api.exportarColaboradores({ status, busca })
      const a = document.createElement('a')
      a.href = URL.createObjectURL(blob)
      a.download = `colaboradores-${new Date().toISOString().slice(0, 10)}.xlsx`
      a.click()
      URL.revokeObjectURL(a.href)
    } catch {
      setErro('A exportação falhou. Tente novamente — se persistir, veja a auditoria.')
    } finally { setExportando(false) }
  }

  return (
    <main className="rh-painel">
      <header className="rh-topo">
        <button className="btn-link" onClick={aoVoltar}>← Voltar</button>
        <h1>👥 Colaboradores</h1>
        <button className="btn-principal btn-mini" disabled={exportando || !lista?.length}
                onClick={exportar}>
          {exportando ? 'Gerando…' : '⬇ Exportar Excel'}</button>
      </header>
      <p className="explica">A exportação traz <strong>uma linha por colaborador com todas as
        respostas do formulário</strong>, respeitando os filtros abaixo. Atenção: a planilha
        contém dados pessoais e de saúde — trate-a conforme a LGPD.</p>

      <div className="rh-card rh-lote">
        <select value={status} style={{ maxWidth: 230 }}
                onChange={(e) => { setStatus(e.target.value); carregar({ status: e.target.value }) }}>
          {STATUS_OPCOES.map(([v, r]) => <option key={v} value={v}>{r}</option>)}
        </select>
        <input placeholder="Buscar por nome, e-mail ou CPF…" value={busca}
               style={{ flex: 1, minWidth: 220 }} onChange={(e) => aoBuscar(e.target.value)} />
        <span className="explica" style={{ margin: 0 }}>
          {lista ? `${lista.length} colaborador(es)` : ''}</span>
      </div>

      {exportando && <Espera texto="Montando sua planilha com tudo dentro…" />}
      {erro && <div className="alerta">{erro}</div>}

      {!lista ? <p>Carregando…</p> : lista.length === 0 ? (
        <p className="explica centro">Nenhum colaborador com esses filtros.</p>
      ) : (
        <table className="rh-tabela">
          <thead>
            <tr><th>Nome</th><th>CPF</th><th>Nascimento</th><th>Cidade</th>
                <th>Contato</th><th>Status</th><th></th></tr>
          </thead>
          <tbody>
            {lista.map((c) => (
              <tr key={c.id}>
                <td><strong>{c.nome_completo}</strong><br /><small>{c.email}</small></td>
                <td>{fmtCpf(c.cpf)}</td>
                <td>{c.nascimento ? new Date(`${c.nascimento}T12:00:00`).toLocaleDateString('pt-BR') : '—'}</td>
                <td>{c.cidade || '—'}</td>
                <td>{c.celular_whatsapp}</td>
                <td>{(c.status || '').replace(/_/g, ' ')}</td>
                <td><button className="btn-secundario btn-mini"
                            onClick={() => aoAbrir(c.id)}>Abrir</button></td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </main>
  )
}
