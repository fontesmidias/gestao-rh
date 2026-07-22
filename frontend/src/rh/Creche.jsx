import { useEffect, useState } from 'react'
import { rh as api } from '../api.js'
import { comAmpulheta } from '../Carregando.jsx'
import { fmtCpf as fmtCpfBase, soDigitos } from '../fmt.js'
import Ajuda from '../Ajuda.jsx'

// exibição em tabela: CPF completo mascarado, senão travessão
const fmtCpf = (c) => (soDigitos(c).length === 11 ? fmtCpfBase(c) : (c || '—'))
const STATUS_BEN = {
  levantamento: { rot: 'Preenchendo', cor: '#c8a415' },
  em_analise: { rot: 'Em análise', cor: '#d9534f' },
  aguardando_repactuacao: { rot: 'Aguardando repactuação', cor: '#8a6d3b' },
  ativo: { rot: 'Ativo', cor: '#0fb257' },
  suspenso: { rot: 'Suspenso', cor: '#889' },
  encerrado: { rot: 'Encerrado', cor: '#889' },
  indeferido: { rot: 'Indeferido', cor: '#889' },
  sem_direito_declarado: { rot: 'Sem direito (declarado)', cor: '#6c8' },
}

// Reembolso-Creche (IN SEGES/MGI 147/2026): revisão dos levantamentos enviados
// pelos colaboradores + panorama de elegibilidade por posto.
export default function Creche({ aoVoltar }) {
  const [aba, setAba] = useState('levantamentos')
  const linkPublico = `${window.location.origin}/creche`

  return (
    <main className="rh-painel">
      <header className="rh-topo">
        <button className="btn-link" onClick={aoVoltar}>← Voltar</button>
        <h1>🍼 Reembolso-Creche</h1>
        <button className="btn-secundario btn-mini"
                onClick={() => { navigator.clipboard?.writeText(linkPublico) }}
                title={linkPublico}>🔗 Copiar link do levantamento</button>
      </header>
      <p className="explica">Envie o <strong>link único</strong> acima a todos os colaboradores. Eles se
        identificam por CPF, confirmam por código no e-mail e informam as crianças. A elegibilidade
        (IN SEGES/MGI nº 147/2026, até 5 anos e 11 meses) é analisada aqui — o colaborador não a vê.</p>

      <div className="rh-abas">
        <button className={aba === 'levantamentos' ? 'ativa' : ''}
                onClick={() => setAba('levantamentos')}>Levantamentos<Ajuda termo="levantamento" /></button>
        <button className={aba === 'postos' ? 'ativa' : ''}
                onClick={() => setAba('postos')}>Elegibilidade por posto<Ajuda termo="elegibilidade" /></button>
      </div>

      {aba === 'levantamentos' ? <Levantamentos /> : <PorPosto />}
    </main>
  )
}

function Levantamentos() {
  const [lista, setLista] = useState(null)
  const [filtro, setFiltro] = useState('em_analise')
  const [erro, setErro] = useState(null)
  const [msg, setMsg] = useState(null)
  const [aberto, setAberto] = useState(null) // benefício em detalhe

  const carregar = (st = filtro) =>
    api.crecheLevantamentos(st || undefined).then(setLista)
      .catch(() => setErro('Não foi possível carregar os levantamentos.'))
  useEffect(() => { carregar() }, [])

  const ativar = async (ben, aguardar) => {
    const dia = window.prompt('Prazo de entrega mensal da documentação (dia do mês, 1 a 28):',
                              String(ben.dia_entrega_mensal || 5))
    if (dia === null) return
    const valor = window.prompt('Valor do reembolso deste colaborador (ex.: R$ 526,64):',
                                ben.valor_posto || ben.valor_reembolso || '')
    setMsg(null); setErro(null)
    try {
      await comAmpulheta(aguardar ? 'Registrando aprovação…' : 'Ativando benefício…',
        () => api.crecheAtivar(ben.id, {
          dia_entrega_mensal: parseInt(dia, 10) || undefined,
          valor_reembolso: valor || undefined, aguardar_repactuacao: aguardar }))
      setMsg(aguardar ? 'Aprovado — aguardando repactuação do contrato.'
        : 'Benefício ativado. O colaborador recebeu as orientações da entrega mensal por e-mail.')
      setAberto(null); carregar()
    } catch (e) { setErro(`Falha ao aprovar (${e.detail || e.message}).`) }
  }
  const indeferir = async (ben) => {
    const motivo = window.prompt(`Indeferir o pedido de ${ben.nome}. Qual o motivo?`)
    if (!motivo) return
    setMsg(null); setErro(null)
    try { await api.crecheIndeferir(ben.id, motivo); setMsg('Pedido indeferido.'); setAberto(null); carregar() }
    catch (e) { setErro(`Falha ao indeferir (${e.detail || e.message}).`) }
  }
  const devolver = async (ben) => {
    const motivo = window.prompt(
      `Devolver o pedido de ${ben.nome} para correção.\n\n`
      + 'O motivo abaixo aparece para o colaborador, que poderá corrigir e reenviar:')
    if (!motivo || !motivo.trim()) return
    setMsg(null); setErro(null)
    try {
      await api.crecheDevolver(ben.id, motivo.trim())
      setMsg('Pedido devolvido ao colaborador para correção.'); setAberto(null); carregar()
    } catch (e) { setErro(`Falha ao devolver (${e.detail || e.message}).`) }
  }
  const marcarSemDireito = async (ben) => {
    if (!window.confirm(`Registrar que ${ben.nome} declarou NÃO ter filhos/dependentes `
      + 'que dão direito ao benefício?\n\nFica no relatório como consultado — não pediu.')) return
    setMsg(null); setErro(null)
    try {
      await api.crecheMarcarSemDireito(ben.candidato_id)
      setMsg('Registrado: colaborador sem direito ao benefício.'); carregar()
    } catch (e) {
      setErro(e.detail === 'beneficio_ativo'
        ? 'Este colaborador tem benefício ATIVO — encerre-o antes.'
        : `Não foi possível registrar (${e.detail || e.message}).`)
    }
  }
  const alterarPrazo = async (ben) => {
    const dia = window.prompt('Novo dia de entrega mensal (1 a 28):', String(ben.dia_entrega_mensal))
    if (dia === null) return
    try { await api.crechePrazos([ben.id], parseInt(dia, 10)); setMsg('Prazo atualizado.'); carregar() }
    catch (e) { setErro(`Falha ao alterar o prazo (${e.detail || e.message}).`) }
  }
  const abrirBlob = (blob) => {
    const url = URL.createObjectURL(blob)
    window.open(url, '_blank')
    setTimeout(() => URL.revokeObjectURL(url), 30000)
  }
  const baixarDossie = async (ben) => {
    setErro(null)
    try {
      const blob = await comAmpulheta('Montando o dossiê do benefício…',
                                      () => api.crecheBaixarDossie(ben.id))
      abrirBlob(blob)
    } catch (e) { setErro(`Falha ao gerar o dossiê (${e.detail || e.message}).`) }
  }
  const verDocumento = async (ben, tipo) => {
    setErro(null)
    try { abrirBlob(await api.crecheBaixarDocumento(ben.id, tipo)) }
    catch (e) { setErro(`Falha ao abrir o documento (${e.detail || e.message}).`) }
  }
  const verDocCrianca = async (ben, crianca, tipo) => {
    setErro(null)
    try { abrirBlob(await api.crecheBaixarDocCrianca(ben.id, crianca.id, tipo)) }
    catch (e) { setErro(`Falha ao abrir o arquivo (${e.detail || e.message}).`) }
  }

  return (
    <>
      <div className="rh-card rh-lote">
        <select value={filtro} style={{ maxWidth: 240 }}
                onChange={(e) => { setFiltro(e.target.value); carregar(e.target.value) }}>
          <option value="">Todos os status</option>
          <option value="em_analise">Aguardando análise</option>
          <option value="aguardando_repactuacao">Aguardando repactuação</option>
          <option value="ativo">Ativos</option>
          <option value="indeferido">Indeferidos</option>
          <option value="levantamento">Ainda preenchendo</option>
          <option value="sem_direito_declarado">Sem direito (declarado)</option>
        </select>
        <span className="explica" style={{ margin: 0 }}>{lista ? `${lista.length} registro(s)` : ''}</span>
      </div>
      {msg && <div className="sucesso">{msg}</div>}
      {erro && <div className="alerta">{erro}</div>}

      {!lista ? <p>Carregando…</p> : lista.length === 0 ? (
        <p className="explica centro">Nenhum levantamento com esse filtro.</p>
      ) : (
        <table className="rh-tabela">
          <thead><tr><th>Colaborador</th><th>Posto</th><th>Crianças</th>
            <th>Prazo</th><th>Status</th><th>Ações</th></tr></thead>
          <tbody>
            {lista.map((b) => {
              const s = STATUS_BEN[b.status] || { rot: b.status, cor: '#889' }
              const elegiveis = (b.criancas || []).filter((c) => c.elegivel_idade).length
              return (
                <tr key={b.id}>
                  <td><strong>{b.nome}</strong><br /><small>{fmtCpf(b.cpf)}</small></td>
                  <td>{b.posto || '—'}{!b.posto_da_direito &&
                    <span title="Posto não marcado como elegível"> ⚠️</span>}</td>
                  <td>{(b.criancas || []).length} ({elegiveis} na idade)</td>
                  <td>dia {b.dia_entrega_mensal}</td>
                  <td><span className="chip" style={{ '--chip-cor': s.cor }}>{s.rot}</span></td>
                  <td className="acoes-candidato">
                    <button className="btn-secundario btn-mini"
                            onClick={() => setAberto(aberto === b.id ? null : b.id)}>
                      {aberto === b.id ? 'Fechar' : 'Ver'}</button>
                    {['em_analise', 'aguardando_repactuacao'].includes(b.status) && (
                      <button className="btn-principal btn-mini" onClick={() => ativar(b, false)}>Ativar</button>)}
                    {b.status === 'ativo' && (
                      <button className="btn-secundario btn-mini" onClick={() => alterarPrazo(b)}>Prazo</button>)}
                    {b.status === 'levantamento' && (
                      <button className="btn-secundario btn-mini" onClick={() => marcarSemDireito(b)}
                              title="Registrar que declarou não ter dependentes que dão direito">
                        Sem direito</button>)}
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      )}

      {aberto && lista && (() => {
        const b = lista.find((x) => x.id === aberto)
        if (!b) return null
        return (
          <div className="rh-card">
            <h3>{b.nome} — {fmtCpf(b.cpf)}</h3>
            <p className="explica">Posto: <strong>{b.posto || '—'}</strong> ·
              e-mail: {b.email || '—'} · telefone: {b.telefone || '—'} ·
              valor do posto: {b.valor_posto || '— (a repactuar)'}</p>
            <table className="rh-tabela">
              <thead><tr><th>Criança</th><th>Nascimento</th><th>Idade</th><th>Vínculo</th>
                <th>Na idade?</th><th>Docs</th></tr></thead>
              <tbody>
                {(b.criancas || []).map((c) => (
                  <tr key={c.id}>
                    <td>{c.nome}</td><td>{c.data_nascimento}</td>
                    <td>{c.idade_anos != null ? `${c.idade_anos}a ${c.idade_meses}m` : '—'}</td>
                    <td>{c.parentesco}</td>
                    <td>{c.elegivel_idade ? '✅' : '❌ passou de 5a11m'}</td>
                    <td>
                      {c.tem_certidao
                        ? <button className="btn-link" onClick={() => verDocCrianca(b, c, 'certidao')}>📄 certidão</button>
                        : <span>⚠️ sem certidão</span>}
                      {c.tem_guarda &&
                        <> · <button className="btn-link" onClick={() => verDocCrianca(b, c, 'guarda')}>guarda</button></>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            <div className="rh-lote" style={{ marginTop: '.6rem' }}>
              <button className="btn-secundario btn-mini"
                      onClick={() => verDocumento(b, 'requerimento')}>📄 Prévia do requerimento</button>
              <button className="btn-secundario btn-mini"
                      onClick={() => verDocumento(b, 'declaracao')}>📄 Declaração-modelo</button>
              <button className="btn-secundario btn-mini" onClick={() => baixarDossie(b)}>⬇ Dossiê do benefício</button>
            </div>
            {['em_analise', 'aguardando_repactuacao'].includes(b.status) && (
              <div className="navegacao">
                <button className="btn-link" style={{ color: '#d9534f' }}
                        onClick={() => indeferir(b)}>Indeferir</button>
                <button className="btn-secundario btn-mini" onClick={() => devolver(b)}
                        title="Devolver ao colaborador para corrigir e reenviar (com motivo)">
                  ↩️ Devolver p/ correção</button>
                {b.status === 'em_analise' && (
                  <button className="btn-secundario" onClick={() => ativar(b, true)}>
                    Aprovar (aguardar repactuação)</button>)}
                <button className="btn-principal" onClick={() => ativar(b, false)}>Ativar benefício</button>
              </div>
            )}
          </div>
        )
      })()}
    </>
  )
}

function PorPosto() {
  const [resumo, setResumo] = useState(null)
  const [erro, setErro] = useState(null)

  useEffect(() => {
    api.crecheResumo().then(setResumo).catch(() => setErro('Não foi possível carregar o resumo.'))
  }, [])

  const exportar = async () => {
    setErro(null)
    try {
      const blob = await comAmpulheta('Montando a relação de elegíveis…', () => api.exportarCreche())
      const a = document.createElement('a')
      a.href = URL.createObjectURL(blob)
      a.download = `reembolso-creche-elegiveis-${new Date().toISOString().slice(0, 10)}.xlsx`
      a.click(); URL.revokeObjectURL(a.href)
    } catch { setErro('A exportação falhou. Tente novamente.') }
  }

  if (erro) return <div className="alerta">{erro}</div>
  if (!resumo) return <p>Carregando…</p>
  return (
    <>
      <div className="rh-card rh-lote">
        <button className="btn-principal btn-mini"
                disabled={!resumo.colaboradores_em_postos_elegiveis}
                onClick={exportar}>⬇ Exportar relação (Excel)</button>
        <span className="explica" style={{ margin: 0 }}>Relação nominal para instruir a repactuação
          (Ofícios CNMP nº 5/2026, ANATEL nº 45/2026).</span>
      </div>
      <div className="rh-metricas">
        <div className="rh-metrica"><strong>{resumo.postos_elegiveis}</strong><span>postos elegíveis</span></div>
        <div className="rh-metrica"><strong>{resumo.colaboradores_em_postos_elegiveis}</strong>
          <span>colaboradores ativos nesses postos</span></div>
      </div>
      {resumo.postos_elegiveis === 0 ? (
        <div className="rh-card"><p className="explica" style={{ margin: 0 }}>Nenhum posto marcado como
          elegível ainda. Vá em <strong>Postos</strong> e marque "Este posto dá direito ao
          reembolso-creche".</p></div>
      ) : (
        <table className="rh-tabela">
          <thead><tr><th>Posto (contrato)</th><th>Sigla</th><th>Nº do contrato</th>
            <th>Valor do reembolso</th><th>Colaboradores ativos</th></tr></thead>
          <tbody>
            {resumo.por_posto.map((p) => (
              <tr key={p.posto_id}>
                <td><strong>{p.posto}</strong></td><td>{p.sigla || '—'}</td>
                <td>{p.contrato_ref || '—'}</td>
                <td>{p.valor_reembolso || <em style={{ opacity: .6 }}>a repactuar</em>}</td>
                <td>{p.colaboradores_ativos}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </>
  )
}
