import { useEffect, useState } from 'react'
import { rh as api } from '../api.js'
import { comAmpulheta } from '../Carregando.jsx'
import { fmtCpf as fmtCpfBase, soDigitos, fmtDataHora } from '../fmt.js'
import Ajuda from '../Ajuda.jsx'
import DashPlanilha from './DashPlanilha.jsx'
import VisualizadorArquivo from '../VisualizadorArquivo.jsx'

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
        <button className={aba === 'pendentes' ? 'ativa' : ''}
                onClick={() => setAba('pendentes')}>Pendentes de resposta</button>
        <button className={aba === 'sem-acesso' ? 'ativa' : ''}
                onClick={() => setAba('sem-acesso')}>Não conseguiram acessar</button>
      </div>

      {aba === 'levantamentos' ? <Levantamentos />
        : aba === 'pendentes' ? <Pendentes />
        : aba === 'sem-acesso' ? <SemAcesso />
        : <PorPosto />}
    </main>
  )
}

// Relatório das tentativas de acesso ao creche que NÃO geraram código (feedback
// 2026-07-27: colaboradores reais relataram "CPF não está na base"). O gate
// público responde igual para todos (anti-enumeração), então é AQUI que o RH vê
// a verdade e decide se é bug/dado errado ou realmente fora da base.
function SemAcesso() {
  const [lista, setLista] = useState(null)
  const [erro, setErro] = useState(null)
  useEffect(() => {
    api.crecheTentativasSemAcesso()
      .then(setLista)
      .catch(() => setErro('Não foi possível carregar o relatório.'))
  }, [])
  if (erro) return <div className="rh-card"><p className="erro">{erro}</p></div>
  if (!lista) return <div className="rh-card"><p>Carregando…</p></div>

  return (
    <div className="rh-card">
      <p className="explica">Quem digitou o CPF no link do creche e <strong>não conseguiu
        entrar</strong>. Como o sistema responde igual para todos (para não revelar quem está na
        base), este é o único lugar onde você vê o que de fato aconteceu:</p>
      <ul className="explica" style={{ marginTop: 0 }}>
        <li><strong>CPF não encontrado</strong>: o CPF digitado não casou com nenhum cadastro. Pode
          estar realmente fora da base, ou cadastrado errado/incompleto (ex.: zero à esquerda
          perdido na planilha). Confira na base de colaboradores.</li>
        <li><strong>Sem e-mail cadastrado</strong>: o CPF casou, mas o cadastro não tem e-mail — a
          pessoa foi para a verificação por perguntas e pode ter travado. Cadastre o e-mail dela.</li>
        <li><strong>Código recusado</strong>: o e-mail <em>saiu normalmente</em> e mesmo assim a
          pessoa não entrou. É o caso mais enganoso — parece que está tudo bem porque o envio
          funcionou. Use <strong>Reenviar link</strong> para mandar um acesso direto, sem código.</li>
      </ul>
      {lista.length === 0
        ? <p>Nenhuma tentativa sem acesso registrada. 👍</p>
        : (
          <div className="dash-scroll">
            <table className="rh-tabela">
              <thead><tr>
                <th>CPF</th><th>Motivo</th><th>Nome / situação</th>
                <th>Tentativas</th><th>Última tentativa</th>
              </tr></thead>
              <tbody>{lista.map((t) => (
                <tr key={t.cpf}>
                  <td><strong>{t.cpf}</strong></td>
                  <td>{t.motivo === 'codigo_recusado'
                    ? <span className="chip" style={{ '--chip-cor': '#8e44ad' }}>Código recusado</span>
                    : t.motivo === 'sem_email'
                      ? <span className="chip" style={{ '--chip-cor': '#e9a63a' }}>Sem e-mail cadastrado</span>
                      : <span className="chip" style={{ '--chip-cor': '#c0392b' }}>CPF não encontrado</span>}</td>
                  <td>{t.nome ? <>{t.nome}{t.situacao ? <small> · {t.situacao}</small> : ''}</> : '—'}</td>
                  <td>{t.tentativas}</td>
                  <td>{t.ultima ? fmtDataHora(t.ultima) : '—'}</td>
                </tr>
              ))}</tbody>
            </table>
          </div>
        )}
    </div>
  )
}

// Elegíveis que ainda NÃO responderam — prova de consulta p/ os órgãos + cobrança.
function Pendentes() {
  const [lista, setLista] = useState(null)
  const [resumo, setResumo] = useState(null)
  useEffect(() => {
    api.crechePendentesResposta().then(setLista).catch(() => setLista([]))
    // O quadro fechado (v2.34): consultei X, responderam Y, faltam Z. Sem ele,
    // o RH via o total num lugar e os pendentes em outro, e a pergunta do órgão
    // — "vocês consultaram todos?" — não tinha resposta de uma linha.
    api.crecheResumo().then(setResumo).catch(() => {})
  }, [])
  const exportarCsv = () => {
    const esc = (s) => `"${String(s ?? '').replace(/"/g, '""')}"`
    const linhas = [['Nome', 'CPF', 'Matrícula', 'E-mail', 'Posto', 'Situação'].map(esc).join(';'),
      ...lista.map((p) => [p.nome, p.cpf, p.matricula, p.email, p.posto,
        p.iniciou ? 'Começou, não enviou' : 'Não acessou'].map(esc).join(';'))]
    const blob = new Blob(['﻿' + linhas.join('\r\n')], { type: 'text/csv;charset=utf-8' })
    const a = document.createElement('a'); a.href = URL.createObjectURL(blob)
    a.download = `creche-pendentes-${new Date().toISOString().slice(0, 10)}.csv`; a.click()
  }
  if (!lista) return <p>Carregando…</p>

  // O quadro aparece SEMPRE — inclusive quando não falta ninguém, que é
  // justamente quando o RH precisa dele para provar que consultou todos.
  const quadro = resumo && (
    <div className="rh-metricas">
      <div className="rh-metrica">
        <strong>{resumo.colaboradores_em_postos_elegiveis}</strong><span>Elegíveis</span></div>
      <div className="rh-metrica">
        <strong>{resumo.responderam}</strong><span>Responderam</span></div>
      <div className="rh-metrica">
        <strong>{resumo.declararam_sem_direito}</strong><span>Declararam não ter</span></div>
      <div className="rh-metrica">
        <strong>{resumo.faltam_responder}</strong><span>Faltam responder</span></div>
    </div>
  )

  if (!lista.length) {
    return (<>
      {quadro}
      <p className="explica centro">Todos os elegíveis responderam. 🎉</p>
    </>)
  }
  return (<>
    {quadro}
    <div className="rh-card rh-lote">
      <button className="btn-principal btn-mini" onClick={exportarCsv}>⬇ Exportar CSV</button>
      <span className="explica" style={{ margin: 0 }}><strong>{lista.length}</strong> colaborador(es)
        ativo(s) em posto elegível que ainda não responderam — cobre e prova a consulta aos órgãos.</span>
    </div>
    <div className="dash-scroll">
    <table className="rh-tabela dash-tabela">
      <thead><tr><th>Nome</th><th>CPF</th><th>Posto</th><th>Situação</th></tr></thead>
      <tbody>
        {lista.map((p) => (
          <tr key={p.candidato_id}>
            <td><strong>{p.nome}</strong><br /><small>{p.email || '—'}</small></td>
            <td>{fmtCpf(p.cpf)}</td><td className="dash-quebra">{p.posto || '—'}</td>
            <td>{p.iniciou
              ? <span className="chip" style={{ '--chip-cor': '#c8a415' }}>Começou, não enviou</span>
              : <span className="chip" style={{ '--chip-cor': '#889' }}>Não acessou</span>}</td>
          </tr>
        ))}
      </tbody>
    </table>
    </div>
  </>)
}

function Levantamentos() {
  const [lista, setLista] = useState(null)
  const [filtro, setFiltro] = useState('em_analise')
  const [erro, setErro] = useState(null)
  const [msg, setMsg] = useState(null)
  const [aberto, setAberto] = useState(null) // benefício em detalhe
  const [doc, setDoc] = useState(null)       // {blob, nome} exibido na tela
  const [historico, setHistorico] = useState(null) // timeline do benefício aberto

  const verHistorico = async (ben) => {
    // TOGGLE: clicar de novo recolhe. Botão que só abre e nunca fecha entulha a
    // tela (feedback do Bruno) — padrão da casa "tudo que abre, fecha".
    if (historico !== null) { setHistorico(null); return }
    setHistorico('carregando')
    try { setHistorico(await api.crecheHistorico(ben.id)) }
    catch { setHistorico([]) }
  }

  const carregar = (st = filtro) => {
    // "__devolvidos" é derivado (levantamento + devolvido_em): carrega os
    // levantamentos e filtra em memória por aguardando_correcao.
    const stServer = st === '__devolvidos' ? 'levantamento' : st
    return api.crecheLevantamentos(stServer || undefined)
      .then((r) => setLista(st === '__devolvidos' ? r.filter((b) => b.aguardando_correcao) : r))
      .catch(() => setErro('Não foi possível carregar os levantamentos.'))
  }
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
  const reabrir = async (ben) => {
    if (!window.confirm(`Reabrir o levantamento de ${ben.nome}?\n\n`
      + 'Volta a "preenchendo" para o colaborador refazer (indeferido por engano, '
      + 'ou passou a ter dependente).')) return
    setMsg(null); setErro(null)
    try {
      await api.crecheReabrir(ben.id)
      setMsg('Levantamento reaberto — o colaborador pode refazer.'); setAberto(null); carregar()
    } catch (e) { setErro(`Não foi possível reabrir (${e.detail || e.message}).`) }
  }
  // "mais filhos": o modelo é 1 benefício : N crianças, então reabrimos o ativo
  // para o colaborador acrescentar a criança (sem duplicar benefício).
  const incluirCrianca = async (ben) => {
    if (!window.confirm(`Reabrir o benefício de ${ben.nome} para INCLUIR outra criança?\n\n`
      + 'O colaborador recebe um e-mail para cadastrar a criança e reenviar. '
      + 'ATENÇÃO: o benefício sai do pagamento até você aprovar de novo.')) return
    setMsg(null); setErro(null)
    try {
      await api.crecheReabrir(ben.id)
      setMsg('Reaberto para inclusão — o colaborador foi avisado por e-mail.')
      setAberto(null); carregar()
    } catch (e) { setErro(`Não foi possível reabrir (${e.detail || e.message}).`) }
  }
  const suspender = async (ben, encerrar) => {
    const acao = encerrar ? 'Encerrar' : 'Suspender'
    const motivo = window.prompt(
      `${acao} o benefício de ${ben.nome}.\n\n`
      + (encerrar ? 'O benefício é encerrado (definitivo). ' : 'O benefício é suspenso (pode reativar depois). ')
      + 'Qual o motivo? (o colaborador é avisado e para de enviar comprovação)')
    if (!motivo || !motivo.trim()) return
    setMsg(null); setErro(null)
    try {
      await api.crecheSuspender(ben.id, motivo.trim(), encerrar)
      setMsg(`Benefício ${encerrar ? 'encerrado' : 'suspenso'}.`); setAberto(null); carregar()
    } catch (e) { setErro(`Não foi possível ${acao.toLowerCase()} (${e.detail || e.message}).`) }
  }
  const reenviarLink = async (ben) => {
    // destrava quem não conseguiu entrar: reenvia o código e, se preciso, corrige o e-mail
    const email = window.prompt(
      `Reenviar o link/código do Reembolso-Creche para ${ben.nome}.\n\n`
      + 'E-mail de destino (deixe como está para reenviar ao atual; corrija se estiver errado):',
      ben.email || '')
    if (email === null) return
    setMsg(null); setErro(null)
    try {
      const r = await api.crecheReenviarLink(ben.id, email.trim())
      setMsg(`Código reenviado para ${r.enviado_para}.`); carregar()
    } catch (e) {
      setErro(e.detail === 'sem_email'
        ? 'Sem e-mail para enviar — informe um e-mail válido para o colaborador.'
        : `Não foi possível reenviar (${e.detail || e.message}).`)
    }
  }
  // Documento abre NA TELA, não em aba nova (v2.33, pedido do Bruno: "que esse
  // documento ele renderize ali na tela, para a gente não precisar ficar
  // baixando"). A certidão da criança é o caso que ele citou: conferir a data
  // de nascimento era baixar arquivo por arquivo.
  const mostrar = (blob, nome) => setDoc({ blob, nome })
  const baixarDossie = async (ben) => {
    setErro(null)
    try {
      const blob = await comAmpulheta('Montando o dossiê do benefício…',
                                      () => api.crecheBaixarDossie(ben.id))
      mostrar(blob, `dossie-${(ben.nome || 'beneficio').split(' ')[0].toLowerCase()}.pdf`)
    } catch (e) { setErro(`Falha ao gerar o dossiê (${e.detail || e.message}).`) }
  }
  const verDocumento = async (ben, tipo) => {
    setErro(null)
    try { mostrar(await api.crecheBaixarDocumento(ben.id, tipo), `${tipo}.pdf`) }
    catch (e) { setErro(`Falha ao abrir o documento (${e.detail || e.message}).`) }
  }
  const verDocCrianca = async (ben, crianca, tipo) => {
    setErro(null)
    try {
      mostrar(await api.crecheBaixarDocCrianca(ben.id, crianca.id, tipo),
              `${tipo}-${(crianca.nome || 'crianca').split(' ')[0].toLowerCase()}`)
    } catch (e) { setErro(`Falha ao abrir o arquivo (${e.detail || e.message}).`) }
  }

  // --- config do DashPlanilha (v1.78): sort/filtro por coluna + cards clicáveis ---
  const rotStatus = (b) => b.aguardando_correcao
    ? 'Devolvido — aguarda reenvio'
    : (STATUS_BEN[b.status]?.rot || b.status)
  const colunas = [
    { chave: 'nome', rotulo: 'Colaborador', ordenavel: true, filtro: 'texto', sempreVisivel: true,
      valor: (b) => b.nome,
      render: (b) => (<><strong>{b.nome}</strong><br /><small>{fmtCpf(b.cpf)}</small></>) },
    { chave: 'posto', rotulo: 'Posto', ordenavel: true, filtro: 'texto', quebra: true,
      valor: (b) => b.posto || '',
      render: (b) => (<>{b.posto || '—'}{!b.posto_da_direito &&
        <span title="Posto não marcado como elegível"> ⚠️</span>}</>) },
    { chave: 'criancas', rotulo: 'Crianças', ordenavel: true,
      valor: (b) => (b.criancas || []).length,
      render: (b) => `${(b.criancas || []).length} (${(b.criancas || []).filter((c) => c.elegivel_idade).length} na idade)` },
    { chave: 'prazo', rotulo: 'Prazo', oculta: true, valor: (b) => b.dia_entrega_mensal,
      render: (b) => `dia ${b.dia_entrega_mensal}` },
    // SEM `filtro:` de propósito (2026-07-30). Quem filtra status é o seletor
    // "Situação", que recarrega a API — ter os dois deixava duas caixas de
    // status na mesma tela, e filtrar por uma enquanto a outra dizia algo
    // diferente dava resultado que parecia errado. A coluna continua
    // ordenável, e os cards (Devolvidos/Ativos) seguem filtrando por ela.
    { chave: 'status', rotulo: 'Status', ordenavel: true,
      valor: rotStatus,
      render: (b) => (<>
        {b.aguardando_correcao
          ? <span className="chip" style={{ '--chip-cor': '#d9822b' }}
                  title={b.motivo_devolucao || ''}>↩️ Devolvido — aguarda reenvio</span>
          : <span className="chip" style={{ '--chip-cor': (STATUS_BEN[b.status] || {}).cor || '#889' }}>
              {(STATUS_BEN[b.status] || {}).rot || b.status}</span>}
        {b.reenviado_apos_correcao && (
          <span className="chip" style={{ '--chip-cor': '#0fb257', marginLeft: '.3rem' }}
                title="O colaborador reenviou após a devolução">✓ reenviado</span>)}
        {b.revisar_idade && (
          <span className="chip" style={{ '--chip-cor': '#d9534f', marginLeft: '.3rem' }}
                title="Todas as crianças passaram da idade limite — revise (suspender)">⚠️ revisar idade</span>)}
      </>) },
  ]
  const acoesLinha = (b) => (<>
    <button className="btn-secundario btn-mini"
            onClick={() => { setAberto(aberto === b.id ? null : b.id); setHistorico(null) }}>
      {aberto === b.id ? 'Fechar' : 'Ver'}</button>
    {['em_analise', 'aguardando_repactuacao'].includes(b.status) && (
      <button className="btn-principal btn-mini" onClick={() => ativar(b, false)}>Ativar</button>)}
    {b.status === 'ativo' && (<>
      <button className="btn-secundario btn-mini" onClick={() => alterarPrazo(b)}>Prazo</button>
      <button className="btn-secundario btn-mini" onClick={() => incluirCrianca(b)}
              title="Nasceu outro filho? Reabre para o colaborador incluir a criança">
        ➕ Incluir criança</button>
      <button className="btn-secundario btn-mini" onClick={() => suspender(b, false)}
              title="Suspender (criança passou da idade, pendência)">Suspender</button>
      <button className="btn-secundario btn-mini" onClick={() => suspender(b, true)}
              title="Encerrar definitivamente">Encerrar</button>
    </>)}
    {b.status === 'levantamento' && !b.aguardando_correcao && (
      <button className="btn-secundario btn-mini" onClick={() => marcarSemDireito(b)}
              title="Registrar que declarou não ter dependentes que dão direito">Sem direito</button>)}
    {['indeferido', 'sem_direito_declarado'].includes(b.status) && (
      <button className="btn-secundario btn-mini" onClick={() => reabrir(b)}
              title="Voltar a preenchendo (indeferido por engano, ou passou a ter dependente)">
        ↩️ Reabrir</button>)}
  </>)
  const reg = lista || []
  const cards = reg.length ? [
    { rotulo: 'No filtro', valor: reg.length },
    { rotulo: 'Devolvidos', cor: '#d9822b',
      valor: reg.filter((b) => b.aguardando_correcao).length,
      filtro: { chave: 'status', valor: 'Devolvido — aguarda reenvio' } },
    { rotulo: 'Revisar idade', cor: '#d9534f', valor: reg.filter((b) => b.revisar_idade).length },
    { rotulo: 'Ativos', cor: '#0fb257', valor: reg.filter((b) => b.status === 'ativo').length,
      filtro: { chave: 'status', valor: STATUS_BEN.ativo.rot } },
  ] : null

  // O filtro server-side entra na grade do dash (feedback 2026-07-30: "tem
  // dois cards, acho que apenas um, tudo concentrado e coeso de filtros").
  // Ele NÃO vira filtro de coluna: recarrega a API, e a base é a folha inteira
  // — trazer tudo ao cliente seria regressão de performance e de LGPD.
  const filtrosExtras = [{
    chave: 'situacao', rotulo: 'Situação', valor: filtro,
    vazioRotulo: 'Situação: todas',
    aoMudar: (v) => { setFiltro(v); carregar(v) },
    opcoes: [
      { v: 'em_analise', r: 'Aguardando análise' },
      { v: '__devolvidos', r: 'Devolvidos — aguardando correção' },
      { v: 'aguardando_repactuacao', r: 'Aguardando repactuação' },
      { v: 'ativo', r: 'Ativos' },
      { v: 'indeferido', r: 'Indeferidos' },
      { v: 'levantamento', r: 'Ainda preenchendo' },
      { v: 'sem_direito_declarado', r: 'Sem direito (declarado)' },
    ],
  }]

  return (
    <>
      {msg && <div className="sucesso">{msg}</div>}
      {erro && <div className="alerta">{erro}</div>}

      {!lista ? <p>Carregando…</p> : (
        <DashPlanilha id="creche" colunas={colunas} dados={lista} cards={cards}
                      filtrosExtras={filtrosExtras}
                      acoesLinha={acoesLinha}
                      linhaExpandida={(b) => (aberto === b.id
                        ? <DetalheBeneficio
                            b={b} historico={historico} verHistorico={verHistorico}
                            verDocCrianca={verDocCrianca} verDocumento={verDocumento}
                            baixarDossie={baixarDossie} ativar={ativar}
                            indeferir={indeferir} devolver={devolver}
                            reenviarLink={reenviarLink}
                            doc={doc} fecharDoc={() => setDoc(null)} />
                        : null)}
                      vazio="Nenhum levantamento com esse filtro." />
      )}

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

// Painel de detalhe do benefício — abre NA PRÓPRIA LINHA do colaborador
// (feedback do Bruno, 2026-07-30: "quando clico em abrir, ele abre lá
// embaixo; deveria abrir a linha abaixo do colaborador, senão tenho que
// rolar a tela até o fim para conferir e depois voltar ao topo").
//
// É a mesma regra já registrada no CLAUDE.md para o DashPlanilha, que o
// Creche não seguia: o painel renderizava DEPOIS da tabela inteira.
function DetalheBeneficio({ b, historico, verHistorico, verDocCrianca, verDocumento,
                           baixarDossie, ativar, indeferir, devolver, reenviarLink,
                           doc, fecharDoc }) {
  return (
    <>
          <h3>{b.nome} — {fmtCpf(b.cpf)}</h3>
          <p className="explica">Posto: <strong>{b.posto || '—'}</strong> ·
            e-mail: {b.email || '—'} · telefone: {b.telefone || '—'} ·
            valor do posto: {b.valor_posto || '— (a repactuar)'}
            {' '}<button className="btn-link" onClick={() => reenviarLink(b)}
                   title="Reenviar o código de acesso ao colaborador (e corrigir o e-mail, se preciso)">
              ✉️ reenviar link</button></p>
          {b.motivo_devolucao && (
            <p className="explica" style={{ margin: '0 0 .6rem', color: '#7a5b1a' }}>
              ↩️ <strong>Última devolução:</strong> {b.motivo_devolucao}
              {b.reenviado_apos_correcao && ' — colaborador já reenviou'}</p>)}
          <div className="rh-lote" style={{ margin: '0 0 .6rem' }}>
            <button className="btn-link" onClick={() => verHistorico(b)}>
              🕘 {historico !== null ? 'Ocultar' : 'Ver'} histórico de decisões</button>
          </div>
          {historico && historico !== 'carregando' && (
            <div className="rh-card" style={{ background: 'var(--hover)', marginBottom: '.6rem' }}>
              <strong>Histórico</strong>
              {historico.length === 0 ? <p className="explica">Sem eventos.</p> : (
                <ul className="explica" style={{ margin: '.4rem 0 0', paddingLeft: '1.1rem' }}>
                  {historico.map((h, i) => (
                    <li key={i}>{fmtDataHora(h.quando)} — <strong>{h.rotulo}</strong>
                      {h.ator_detalhe ? ` (${h.ator_detalhe})` : ''}
                      {h.motivo ? `: ${h.motivo}` : ''}</li>))}
                </ul>)}
            </div>)}
          {historico === 'carregando' && <p className="explica">Carregando histórico…</p>}
          <table className="rh-tabela">
            <thead><tr><th>Criança</th><th>Nascimento</th><th>Idade</th><th>Vínculo</th>
              <th>Na idade?</th><th>Docs</th></tr></thead>
            <tbody>
              {(b.criancas || []).map((c) => (
                <tr key={c.id}>
                  <td>{c.nome}</td><td>{c.data_nascimento}</td>
                  <td>{c.idade_anos != null ? `${c.idade_anos}a ${c.idade_meses}m` : '—'}</td>
                  <td>{c.parentesco}</td>
                  {/* TRÊS estados, não dois (incidente 2026-07-30): data que
                      não dá para ler é dado a conferir, NÃO "passou da
                      idade". Mostrar as duas coisas como ❌ levaria o RH a
                      indeferir quem tem direito. */}
                  <td>{c.idade_desconhecida
                    ? <span title="A data de nascimento não pôde ser lida — confira o cadastro.">
                        ⚠️ conferir data</span>
                    : c.elegivel_idade ? '✅' : '❌ passou de 5a11m'}</td>
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
          {/* O documento aparece AQUI, logo abaixo das crianças — perto do
              botão que o abriu. Antes ia para uma aba nova, e conferir a data
              de nascimento na certidão obrigava a trocar de aba a cada
              criança. */}
          {doc && <VisualizadorArquivo blob={doc.blob} nome={doc.nome} aoFechar={fecharDoc} />}
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
    </>
  )
}