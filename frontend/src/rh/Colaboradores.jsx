import { useEffect, useRef, useState } from 'react'
import { rh as api } from '../api.js'
import { statusInfo } from '../status.js'
import { comAmpulheta } from '../Carregando.jsx'
import { fmtCpf as fmtCpfBase, soDigitos } from '../fmt.js'
import { fmtData } from '../fmt.js'
import SelectBusca from '../SelectBusca.jsx'
import Espera from '../Espera.jsx'
import DashPlanilha from './DashPlanilha.jsx'

// exibição em tabela: CPF completo mascarado, senão travessão
const fmtCpf = (c) => (soDigitos(c).length === 11 ? fmtCpfBase(c) : (c || '—'))
const fmtDataBR = (s) => {
  if (!s) return '—'
  // aceita "aaaa-mm-dd" (fichas) e "dd/mm/aaaa" (importação)
  if (/^\d{4}-\d{2}-\d{2}/.test(s)) return new Date(`${s}T12:00:00`).toLocaleDateString('pt-BR')
  return s
}

// Dash de colaboradores sobre o DashPlanilha (v1.76): sort/filtro por coluna,
// cards clicáveis (situação/origem/Domínio), responsivo. Os filtros de TOPO
// (status/situação/posto/busca/incluir_admissao) continuam SERVER-SIDE
// (recarregam a API); o DashPlanilha refina em memória por cima e cuida da
// seleção + ações em massa contextuais.
export default function Colaboradores({ aoVoltar, aoAbrir }) {
  const [lista, setLista] = useState(null)
  const [postos, setPostos] = useState([])
  const [status, setStatus] = useState('')
  const [situacao, setSituacao] = useState('')
  const [postoId, setPostoId] = useState('')
  const [incluirAdmissao, setIncluirAdmissao] = useState(false)
  const [busca, setBusca] = useState('')
  const [exportando, setExportando] = useState(false)
  const [erro, setErro] = useState(null)
  const [aviso, setAviso] = useState(null)
  const timer = useRef(null)
  const inputArquivo = useRef(null)

  const carregar = (f = {}) => {
    api.colaboradores({
      status: f.status ?? status, busca: f.busca ?? busca,
      situacao: f.situacao ?? situacao, posto_id: f.posto_id ?? postoId,
      incluir_admissao: (f.incluirAdmissao ?? incluirAdmissao) || undefined,
    }).then(setLista).catch(() => setErro('Não foi possível carregar a lista.'))
  }
  useEffect(() => {
    carregar()
    api.postos().then((r) => setPostos(r.postos || [])).catch(() => {})
  }, [])

  const aoBuscar = (texto) => {
    setBusca(texto)
    clearTimeout(timer.current)
    timer.current = setTimeout(() => carregar({ busca: texto }), 400)
  }

  const importar = async (arquivo) => {
    if (!arquivo) return
    setErro(null); setAviso(null)
    try {
      const r = await comAmpulheta('Importando a base de colaboradores…',
                                   () => api.importarColaboradores(arquivo))
      setAviso(`Importação concluída: ${r.criados} novo(s), ${r.atualizados} atualizado(s)`
        + (r.sem_cpf ? `, ${r.sem_cpf} linha(s) sem CPF ignorada(s)` : '')
        + `. Base total: ${r.total_base}.`)
      carregar()
      api.postos().then((rp) => setPostos(rp.postos || [])).catch(() => {})
    } catch (e) {
      setErro(e.detail === 'sem_coluna_cpf'
        ? 'A planilha precisa de uma coluna "CPF". Confira o arquivo do Tirvu.'
        : e.detail === 'arquivo_invalido' || e.detail === 'planilha_vazia'
        ? 'Arquivo inválido ou vazio. Exporte novamente do Tirvu em .xlsx.'
        : 'A importação falhou. Tente novamente — se persistir, veja a auditoria.')
    } finally {
      if (inputArquivo.current) inputArquivo.current.value = ''
    }
  }

  const exportar = async () => {
    setErro(null); setExportando(true)
    try {
      const blob = await api.exportarColaboradores({ status, busca, situacao,
        posto_id: postoId, incluir_admissao: incluirAdmissao || undefined })
      const a = document.createElement('a')
      a.href = URL.createObjectURL(blob)
      a.download = `colaboradores-${new Date().toISOString().slice(0, 10)}.xlsx`
      a.click()
      URL.revokeObjectURL(a.href)
    } catch {
      setErro('A exportação falhou. Tente novamente — se persistir, veja a auditoria.')
    } finally { setExportando(false) }
  }

  // Planilha de importação de admissões do TIRVU (28 colunas). Só colaborador
  // vai para lá — quem ainda está em admissão não tem vínculo a criar.
  const exportarTirvu = async () => {
    setErro(null)
    const filtros = { status, busca, situacao, posto_id: postoId }
    try {
      const p = await comAmpulheta('Conferindo as admissões…',
                                   () => api.pendenciasTirvu(filtros))
      if (p.total === 0) {
        setErro('Nenhum colaborador vindo da admissão nos filtros atuais. '
                + 'Quem foi importado do Tirvu já existe lá e não precisa ser reenviado.')
        return
      }
      if (p.com_pendencia.length) {
        const nomes = p.com_pendencia.slice(0, 8)
          .map((x) => `• ${x.nome} (falta: ${x.faltam.join(', ')})`).join('\n')
        const extra = p.com_pendencia.length > 8
          ? `\n…e mais ${p.com_pendencia.length - 8}.` : ''
        if (!window.confirm(`${p.com_pendencia.length} de ${p.total} colaborador(es) têm campos que o Tirvu recusa:\n\n${nomes}${extra}\n\nExportar mesmo assim?`)) return
      }
      const blob = await comAmpulheta('Gerando a planilha do Tirvu…',
                                      () => api.exportarTirvu(filtros))
      const a = document.createElement('a')
      a.href = URL.createObjectURL(blob)
      a.download = `importacao-tirvu-${new Date().toISOString().slice(0, 10)}.xlsx`
      a.click()
      URL.revokeObjectURL(a.href)
    } catch (e) {
      setErro(e.detail === 'nenhum_colaborador'
        ? 'Nenhum colaborador nos filtros escolhidos.'
        : 'Não foi possível gerar a planilha do Tirvu. Tente novamente.')
    }
  }

  // --- controles de vínculo (com confirmação, padrão da casa) ---
  const efetivar = async (c) => {
    if (!window.confirm(`Efetivar ${c.nome_completo} como colaborador ativo?`)) return
    try { await api.efetivarColaborador(c.id); carregar() }
    catch { setErro('Não foi possível efetivar.') }
  }
  const desligar = async (c) => {
    const data = window.prompt(
      `Desligar ${c.nome_completo}.\nInforme a data de desligamento (dd/mm/aaaa):`,
      new Date().toLocaleDateString('pt-BR'))
    if (!data) return
    try { await api.desligarColaborador(c.id, data.trim()); carregar() }
    catch { setErro('Não foi possível registrar o desligamento.') }
  }
  const transferir = async (c) => {
    const opts = postos.filter((p) => p.ativo)
    if (!opts.length) { setErro('Cadastre postos antes de transferir.'); return }
    const nomes = opts.map((p, i) => `${i + 1}) ${p.nome}`).join('\n')
    const escolha = window.prompt(
      `Transferir ${c.nome_completo} para qual posto?\n\n${nomes}\n\nDigite o número:`)
    const idx = parseInt(escolha, 10) - 1
    if (isNaN(idx) || idx < 0 || idx >= opts.length) return
    const data = window.prompt('Data da transferência (dd/mm/aaaa):',
                               new Date().toLocaleDateString('pt-BR'))
    if (!data) return
    try { await api.transferirColaborador(c.id, opts[idx].id, data.trim()); carregar() }
    catch { setErro('Não foi possível transferir.') }
  }
  // reverter colaborador -> candidato (pergunta destino + motivo; avisa se Tirvu)
  const pedirReversao = (rotuloAlvo, indicio) => {
    if (indicio && !window.confirm(
      `Atenção: ${rotuloAlvo} tem indício de já existir no Tirvu (${indicio}).\n\n`
      + 'Reverter aqui NÃO desfaz o vínculo no Tirvu — resolva lá se necessário. Continuar?')) return null
    const escolha = window.prompt(
      `Reverter ${rotuloAlvo} de colaborador para candidato.\n\n`
      + 'Para onde volta? Digite 1 ou 2:\n1) Início (novo convite)\n2) Revisão (reavaliar dados)', '2')
    if (escolha === null) return null
    const destino = escolha.trim() === '1' ? 'convidado' : 'em_revisao'
    const motivo = window.prompt('Motivo da reversão (obrigatório, fica na auditoria):', '')
    if (!motivo || !motivo.trim()) { setErro('A reversão precisa de um motivo.'); return null }
    return { destino, motivo: motivo.trim() }
  }
  const reverter = async (c) => {
    const r = pedirReversao(c.nome_completo, c.indicio_tirvu)
    if (!r) return
    setErro(null); setAviso(null)
    try {
      await api.reverterColaborador(c.id, r.destino, r.motivo)
      setAviso(`${c.nome_completo} voltou a ser candidato.`); carregar()
    } catch (e) { setErro(`Não foi possível reverter (${e.detail || e.message}).`) }
  }

  // --- ações em massa (recebem as linhas selecionadas do DashPlanilha) ---
  const efetivarSelecionados = async (linhas, limpar) => {
    const ids = linhas.filter((c) => !c.situacao).map((c) => c.id)
    if (!ids.length) { setErro('Nenhum candidato efetivável selecionado.'); return }
    if (!window.confirm(`Efetivar ${ids.length} candidato(s) como colaboradores ativos?`
      + '\n\nCandidatos ainda não aprovados também serão efetivados se estiverem selecionados.')) return
    setErro(null); setAviso(null)
    try {
      const r = await comAmpulheta('Efetivando selecionados…', () => api.efetivarLote(ids))
      setAviso(`${r.efetivados} efetivado(s)` + (r.pulados ? `, ${r.pulados} já eram colaboradores.` : '.'))
      limpar(); carregar()
    } catch (e) { setErro(`Não foi possível efetivar em massa (${e.detail || e.message}).`) }
  }
  const acaoMassa = async (linhas, limpar, acao) => {
    const ids = linhas.filter((c) => c.situacao).map((c) => c.id)  // só colaboradores
    if (!ids.length && acao !== 'marcar_dominio' && acao !== 'desmarcar_dominio') {
      setErro('Selecione ao menos um colaborador.'); return
    }
    const idsDominio = linhas.map((c) => c.id)
    const alvo = (acao === 'marcar_dominio' || acao === 'desmarcar_dominio') ? idsDominio : ids
    let data = null
    const rotulos = {
      desligar: 'desligado(s)', reativar: 'reativado(s)',
      marcar_dominio: 'marcado(s) como lançado(s) na Domínio',
      desmarcar_dominio: 'desmarcado(s) da Domínio',
    }
    if (acao === 'desligar') {
      data = window.prompt(`Desligar ${alvo.length} colaborador(es) selecionado(s).`
        + '\nInforme a data de desligamento (dd/mm/aaaa):', new Date().toLocaleDateString('pt-BR'))
      if (!data) return
    } else if (!window.confirm(`Confirmar: ${alvo.length} registro(s) ${rotulos[acao]}?`)) return
    setErro(null); setAviso(null)
    try {
      const r = await comAmpulheta('Aplicando ação nos selecionados…',
        () => api.acaoMassaColaboradores(alvo, acao, data?.trim()))
      setAviso(`${r.afetados} ${rotulos[acao]}`
        + (r.pulados ? `, ${r.pulados} ignorado(s) (não eram colaboradores).` : '.'))
      limpar(); carregar()
    } catch (e) { setErro(`Não foi possível ${acao} em massa (${e.detail || e.message}).`) }
  }
  const reverterSelecionados = async (linhas, limpar) => {
    const alvos = linhas.filter((c) => c.situacao)  // só colaboradores
    if (!alvos.length) { setErro('Selecione ao menos um colaborador para reverter.'); return }
    const comTirvu = alvos.filter((c) => c.indicio_tirvu).length
    const rotulo = `${alvos.length} colaborador(es)` + (comTirvu ? ` (${comTirvu} com indício de Tirvu)` : '')
    const r = pedirReversao(rotulo, comTirvu ? 'alguns já podem existir no Tirvu' : null)
    if (!r) return
    setErro(null); setAviso(null)
    try {
      const res = await comAmpulheta('Revertendo selecionados…',
        () => api.reverterLote(alvos.map((c) => c.id), r.destino, r.motivo))
      setAviso(`${res.revertidos} revertido(s) a candidato`
        + (res.pulados ? `, ${res.pulados} ignorado(s) (não eram colaboradores).` : '.'))
      limpar(); carregar()
    } catch (e) { setErro(`Não foi possível reverter em massa (${e.detail || e.message}).`) }
  }

  // --- config do DashPlanilha ---
  const chipSituacao = (c) => c.situacao
    ? <span className="chip" style={{ '--chip-cor': c.situacao === 'ativo' ? '#0fb257' : '#889' }}>
        {c.situacao === 'ativo' ? '🟢 Ativo' : '⚪ Desligado'}
        {c.data_desligamento ? ` (${c.data_desligamento})` : ''}</span>
    : <span className="chip" style={{ '--chip-cor': statusInfo(c.status).cor }}>
        {statusInfo(c.status).icone} {statusInfo(c.status).label}</span>

  const colunas = [
    { chave: 'nome', rotulo: 'Nome', ordenavel: true, filtro: 'texto', sempreVisivel: true,
      valor: (c) => c.nome_completo,
      render: (c) => (<><strong>{c.nome_completo}</strong><br /><small>{c.email || '—'}</small></>) },
    { chave: 'cpf', rotulo: 'CPF', filtro: 'texto', valor: (c) => c.cpf, render: (c) => fmtCpf(c.cpf) },
    { chave: 'posto', rotulo: 'Posto', ordenavel: true, filtro: 'texto', quebra: true,
      valor: (c) => c.posto_nome || '' },
    { chave: 'nascimento', rotulo: 'Nascimento', ordenavel: true, oculta: true,
      valor: (c) => c.nascimento, render: (c) => fmtDataBR(c.nascimento) },
    { chave: 'contato', rotulo: 'Contato', oculta: true, valor: (c) => c.celular_whatsapp || '' },
    { chave: 'situacao', rotulo: 'Situação', ordenavel: true, filtro: 'select',
      opcoes: [{ v: 'Ativo', r: 'Ativo' }, { v: 'Desligado', r: 'Desligado' }, { v: 'Em admissão', r: 'Em admissão' }],
      valor: (c) => c.situacao === 'ativo' ? 'Ativo' : c.situacao === 'desligado' ? 'Desligado' : 'Em admissão',
      render: (c) => (<>{chipSituacao(c)}{c.na_dominio_em && (
        <span className="chip" style={{ '--chip-cor': '#3b7dd8', marginLeft: '.3rem' }}
              title={`Lançada na Domínio em ${new Date(c.na_dominio_em).toLocaleDateString('pt-BR')}`}>🧾 Domínio</span>)}</>) },
    { chave: 'origem', rotulo: 'Origem', filtro: 'select', oculta: true,
      opcoes: [{ v: 'Tirvu', r: 'Importado (Tirvu)' }, { v: 'Admissão', r: 'Da admissão' }],
      valor: (c) => c.origem === 'importacao' ? 'Tirvu' : 'Admissão' },
    // o que falta preencher no cadastro (importados do Tirvu vêm com buracos)
    { chave: 'cadastro', rotulo: 'Cadastro', filtro: 'select', quebra: true,
      opcoes: [{ v: 'Completo', r: 'Completo' }, { v: 'Falta', r: 'Falta preencher' }],
      valor: (c) => (c.dados_faltando?.length ? 'Falta' : 'Completo'),
      render: (c) => (c.dados_faltando?.length
        ? <span className="chip" style={{ '--chip-cor': '#e9a63a' }}
                title={`Faltam: ${c.dados_faltando.join(', ')}`}>
            ⚠️ falta {c.dados_faltando.join(', ')}</span>
        : <span className="chip" style={{ '--chip-cor': '#0fb257' }}>✓ completo</span>) },
    { chave: 'criado_em', rotulo: 'Cadastro', ordenavel: true, oculta: true,
      valor: (c) => c.criado_em, render: (c) => fmtData(c.criado_em) },
  ]

  const acoesLinha = (c) => (<>
    <button className="btn-secundario btn-mini" onClick={() => aoAbrir(c.id)}>Abrir</button>
    {c.situacao !== 'ativo' && (
      <button className="btn-secundario btn-mini" onClick={() => efetivar(c)} title="Tornar colaborador ativo">Efetivar</button>)}
    {c.situacao === 'ativo' && (<>
      <button className="btn-secundario btn-mini" onClick={() => transferir(c)} title="Transferir de posto">Transferir</button>
      <button className="btn-secundario btn-mini" onClick={() => desligar(c)} title="Registrar desligamento">Desligar</button>
    </>)}
    {c.situacao && (
      <button className="btn-secundario btn-mini" onClick={() => reverter(c)} title="Voltar a candidato">↩️ Reverter</button>)}
  </>)

  // ações em massa CONTEXTUAIS: só aparece o botão que faz sentido p/ a seleção
  const acoesMassa = (linhas, limpar) => {
    const efetivaveis = linhas.filter((c) => !c.situacao).length
    const ativos = linhas.filter((c) => c.situacao === 'ativo').length
    const desligados = linhas.filter((c) => c.situacao === 'desligado').length
    return (<>
      {efetivaveis > 0 && (
        <button className="btn-principal btn-mini" onClick={() => efetivarSelecionados(linhas, limpar)}>
          ✅ Efetivar ({efetivaveis})</button>)}
      {ativos > 0 && (
        <button className="btn-secundario btn-mini" onClick={() => acaoMassa(linhas, limpar, 'desligar')}>
          🚪 Desligar ({ativos})</button>)}
      {desligados > 0 && (
        <button className="btn-secundario btn-mini" onClick={() => acaoMassa(linhas, limpar, 'reativar')}>
          ♻️ Reativar ({desligados})</button>)}
      {(ativos + desligados) > 0 && (
        <button className="btn-secundario btn-mini" onClick={() => reverterSelecionados(linhas, limpar)}
                title="Voltar colaborador a candidato">↩️ Reverter ({ativos + desligados})</button>)}
      <button className="btn-secundario btn-mini" onClick={() => acaoMassa(linhas, limpar, 'marcar_dominio')}
              title="Marca que estas admissões já foram lançadas na Domínio">🧾 Na Domínio ({linhas.length})</button>
      <button className="btn-secundario btn-mini" onClick={() => acaoMassa(linhas, limpar, 'desmarcar_dominio')}>
        ↩ Tirar da Domínio</button>
    </>)
  }

  // cards clicáveis (filtram a coluna 'situacao'/'origem' em memória)
  const reg = lista || []
  const cards = reg.length ? [
    { rotulo: 'Total', valor: reg.length },
    { rotulo: 'Ativos', valor: reg.filter((c) => c.situacao === 'ativo').length, cor: '#0fb257',
      filtro: { chave: 'situacao', valor: 'Ativo' } },
    { rotulo: 'Desligados', valor: reg.filter((c) => c.situacao === 'desligado').length, cor: '#889',
      filtro: { chave: 'situacao', valor: 'Desligado' } },
    { rotulo: 'Importados (Tirvu)', valor: reg.filter((c) => c.origem === 'importacao').length, cor: '#5b7',
      filtro: { chave: 'origem', valor: 'Tirvu' } },
    { rotulo: 'Cadastro incompleto', cor: '#e9a63a',
      valor: reg.filter((c) => c.dados_faltando?.length).length,
      filtro: { chave: 'cadastro', valor: 'Falta' } },
    { rotulo: 'Na Domínio', valor: reg.filter((c) => c.na_dominio_em).length, cor: '#3b7dd8' },
  ] : null

  return (
    <main className="rh-painel">
      <header className="rh-topo">
        <button className="btn-link" onClick={aoVoltar}>← Voltar</button>
        <h1>👥 Colaboradores</h1>
        <div style={{ display: 'flex', gap: '.5rem' }}>
          <input ref={inputArquivo} type="file" accept=".xlsx" hidden
                 onChange={(e) => importar(e.target.files?.[0])} />
          <button className="btn-secundario btn-mini"
                  onClick={() => inputArquivo.current?.click()}>⬆ Importar base</button>
          <button className="btn-secundario btn-mini" disabled={!lista?.length}
                  title="Planilha no layout de importação de admissões do Tirvu (28 colunas)"
                  onClick={exportarTirvu}>⬆ Exportar p/ Tirvu</button>
          <button className="btn-principal btn-mini" disabled={exportando || !lista?.length}
                  onClick={exportar}>{exportando ? 'Gerando…' : '⬇ Exportar Excel'}</button>
        </div>
      </header>
      <p className="explica">Importe a base ativa do <strong>Tirvu (.xlsx)</strong> — a importação é
        <strong> por CPF</strong> (rodar de novo atualiza, não duplica). Clique nos cards para filtrar;
        ordene e filtre por qualquer coluna. Contém dados pessoais e de saúde — trate conforme a LGPD.</p>

      {/* filtros de topo SERVER-SIDE (recarregam a base) */}
      <div className="rh-card rh-lote">
        <SelectBusca style={{ minWidth: 200 }} vazioRotulo="Todos os postos" placeholder="Buscar posto…"
          valor={postoId} aoEscolher={(v) => { setPostoId(v); carregar({ posto_id: v }) }}
          opcoes={postos.map((p) => ({ valor: p.id, rotulo: p.nome }))} />
        <input placeholder="Buscar por nome, e-mail ou CPF…" value={busca}
               style={{ flex: 1, minWidth: 200 }} onChange={(e) => aoBuscar(e.target.value)} />
        <label className="explica" style={{ display: 'flex', alignItems: 'center', gap: '.4rem', margin: 0 }}>
          <input type="checkbox" checked={incluirAdmissao}
                 onChange={(e) => { setIncluirAdmissao(e.target.checked); carregar({ incluirAdmissao: e.target.checked }) }} />
          incluir em admissão
        </label>
      </div>

      {exportando && <Espera texto="Montando sua planilha com tudo dentro…" />}
      {aviso && <div className="alerta" style={{ borderColor: 'var(--verde)',
                     background: 'var(--verde-suave)', color: 'var(--verde-escuro)' }}>{aviso}</div>}
      {erro && <div className="alerta">{erro}</div>}

      {!lista ? <p>Carregando…</p> : (
        <DashPlanilha id="colaboradores" colunas={colunas} dados={lista} cards={cards}
                      acoesLinha={acoesLinha} acoesMassa={acoesMassa}
                      vazio="Nenhum colaborador com esses filtros." />
      )}
    </main>
  )
}
