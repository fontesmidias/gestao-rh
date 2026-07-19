import { useEffect, useRef, useState } from 'react'
import { rh as api } from '../api.js'
import { STATUS_OPCOES, statusInfo } from '../status.js'
import { comAmpulheta } from '../Carregando.jsx'
import SelectBusca from '../SelectBusca.jsx'
import CheckMestre from '../CheckMestre.jsx'
import Espera from '../Espera.jsx'

const fmtCpf = (c) => {
  const d = (c || '').replace(/\D/g, '')
  return d.length === 11 ? `${d.slice(0, 3)}.${d.slice(3, 6)}.${d.slice(6, 9)}-${d.slice(9)}` : (c || '—')
}
const fmtDataBR = (s) => {
  if (!s) return '—'
  // aceita "aaaa-mm-dd" (fichas) e "dd/mm/aaaa" (importação)
  if (/^\d{4}-\d{2}-\d{2}/.test(s)) return new Date(`${s}T12:00:00`).toLocaleDateString('pt-BR')
  return s
}

// Dash de colaboradores: importação em massa, filtros (status, situação, posto),
// tabela e exportação Excel completa, além dos controles de vínculo (efetivar,
// desligar, transferir) direto na linha.
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
  const [selecionados, setSelecionados] = useState(() => new Set())
  const timer = useRef(null)
  const inputArquivo = useRef(null)

  // Recortes da lista para decidir quais ações em massa fazem sentido.
  const registros = lista || []
  const efetivaveis = registros.filter((c) => !c.situacao)          // candidatos em admissão
  const selList = registros.filter((c) => selecionados.has(c.id))
  const selEfetivaveis = selList.filter((c) => !c.situacao).length
  const selAtivos = selList.filter((c) => c.situacao === 'ativo').length
  const selDesligados = selList.filter((c) => c.situacao === 'desligado').length

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
        ? 'A planilha precisa ter uma coluna "CPF". Confira o arquivo do Tirvu.'
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
  // vai para lá — quem ainda está em admissão não tem vínculo a criar. Por
  // padrão exclui os importados do próprio Tirvu (já existem lá).
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
  const alternarSel = (cid) => setSelecionados((s) => {
    const n = new Set(s); n.has(cid) ? n.delete(cid) : n.add(cid); return n
  })
  const selecionarTodos = (marcar) =>
    setSelecionados(marcar ? new Set(registros.map((c) => c.id)) : new Set())
  const efetivarSelecionados = async () => {
    const ids = [...selecionados]
    if (!ids.length) return
    if (!window.confirm(`Efetivar ${ids.length} candidato(s) como colaboradores ativos?`
      + '\n\nCandidatos ainda não aprovados também serão efetivados se estiverem selecionados.')) return
    setErro(null); setAviso(null)
    try {
      const r = await comAmpulheta('Efetivando selecionados…', () => api.efetivarLote(ids))
      setAviso(`${r.efetivados} efetivado(s)` + (r.pulados ? `, ${r.pulados} já eram colaboradores.` : '.'))
      setSelecionados(new Set())
      carregar()
    } catch (e) {
      setErro(`Não foi possível efetivar em massa (${e.detail || e.message}).`)
    }
  }
  const acaoMassa = async (acao) => {
    const ids = [...selecionados]
    if (!ids.length) return
    let data = null
    const rotulos = {
      desligar: 'desligado(s)', reativar: 'reativado(s)',
      marcar_dominio: 'marcado(s) como lançado(s) na Domínio',
      desmarcar_dominio: 'desmarcado(s) da Domínio',
    }
    if (acao === 'desligar') {
      data = window.prompt(`Desligar ${ids.length} colaborador(es) selecionado(s).`
        + '\nInforme a data de desligamento (dd/mm/aaaa):', new Date().toLocaleDateString('pt-BR'))
      if (!data) return
    } else {
      if (!window.confirm(`Confirmar: ${ids.length} registro(s) ${rotulos[acao]}?`)) return
    }
    setErro(null); setAviso(null)
    try {
      const r = await comAmpulheta('Aplicando ação nos selecionados…',
        () => api.acaoMassaColaboradores(ids, acao, data?.trim()))
      setAviso(`${r.afetados} ${rotulos[acao]}`
        + (r.pulados ? `, ${r.pulados} ignorado(s) (não eram colaboradores).` : '.'))
      setSelecionados(new Set()); carregar()
    } catch (e) {
      setErro(`Não foi possível ${acao} em massa (${e.detail || e.message}).`)
    }
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
    try {
      await api.transferirColaborador(c.id, opts[idx].id, data.trim())
      carregar()
    } catch { setErro('Não foi possível transferir.') }
  }

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
                  title="Planilha no layout de importação de admissões do Tirvu (28 colunas), com quem veio da admissão"
                  onClick={exportarTirvu}>⬆ Exportar p/ Tirvu</button>
          <button className="btn-principal btn-mini" disabled={exportando || !lista?.length}
                  onClick={exportar}>
            {exportando ? 'Gerando…' : '⬇ Exportar Excel'}</button>
        </div>
      </header>
      <p className="explica">Importe a base ativa do <strong>Tirvu (.xlsx)</strong> — a
        importação é <strong>por CPF</strong>: rodar de novo atualiza, não duplica. A
        exportação traz <strong>uma linha por colaborador com todas as respostas</strong>,
        respeitando os filtros. Atenção: contém dados pessoais e de saúde — trate conforme a LGPD.</p>
      <p className="explica"><strong>⬆ Exportar p/ Tirvu</strong> gera a planilha de
        <strong> importação de admissões</strong> (28 colunas) para você subir lá — apenas
        com quem <strong>veio da admissão</strong> e já foi efetivado. Quem foi importado
        do Tirvu já existe lá e fica de fora. O Tirvu ignora cadastros repetidos.</p>

      <div className="rh-card rh-lote">
        <select value={status} style={{ maxWidth: 200 }}
                onChange={(e) => { setStatus(e.target.value); carregar({ status: e.target.value }) }}>
          {STATUS_OPCOES.map(([v, r]) => <option key={v} value={v}>{r}</option>)}
        </select>
        <select value={situacao} style={{ maxWidth: 170 }}
                onChange={(e) => { setSituacao(e.target.value); carregar({ situacao: e.target.value }) }}>
          <option value="">Todas as situações</option>
          <option value="ativo">Ativos</option>
          <option value="desligado">Desligados</option>
        </select>
        <SelectBusca style={{ minWidth: 200 }} vazioRotulo="Todos os postos" placeholder="Buscar posto…"
          valor={postoId} aoEscolher={(v) => { setPostoId(v); carregar({ posto_id: v }) }}
          opcoes={postos.map((p) => ({ valor: p.id, rotulo: p.nome }))} />
        <input placeholder="Buscar por nome, e-mail ou CPF…" value={busca}
               style={{ flex: 1, minWidth: 200 }} onChange={(e) => aoBuscar(e.target.value)} />
        <span className="explica" style={{ margin: 0 }}>
          {lista ? `${lista.length} registro(s)` : ''}</span>
      </div>
      <label className="explica" style={{ display: 'flex', alignItems: 'center', gap: '.5rem',
              margin: '0 0 .6rem' }}>
        <input type="checkbox" style={{ width: 'auto', minHeight: 0 }} checked={incluirAdmissao}
               onChange={(e) => { setIncluirAdmissao(e.target.checked); carregar({ incluirAdmissao: e.target.checked }) }} />
        Incluir candidatos ainda em processo de admissão (por padrão, esta tela mostra só
        quem já é colaborador — importado ou efetivado).
      </label>

      {selecionados.size > 0 && (
        <div className="rh-card rh-lote" style={{ alignItems: 'center' }}>
          <strong>{selecionados.size} selecionado(s):</strong>
          {selEfetivaveis > 0 && (
            <button className="btn-principal btn-mini" onClick={efetivarSelecionados}>
              ✅ Efetivar ({selEfetivaveis})</button>)}
          {selAtivos > 0 && (
            <button className="btn-secundario btn-mini" onClick={() => acaoMassa('desligar')}>
              🚪 Desligar ({selAtivos})</button>)}
          {selDesligados > 0 && (
            <button className="btn-secundario btn-mini" onClick={() => acaoMassa('reativar')}>
              ♻️ Reativar ({selDesligados})</button>)}
          <button className="btn-secundario btn-mini" onClick={() => acaoMassa('marcar_dominio')}
                  title="Marca que estas admissões já foram lançadas no sistema Domínio (contabilidade)">
            🧾 Na Domínio ({selecionados.size})</button>
          <button className="btn-secundario btn-mini" onClick={() => acaoMassa('desmarcar_dominio')}
                  title="Desfaz a marcação de lançado na Domínio">
            ↩ Tirar da Domínio</button>
          <button className="btn-link" onClick={() => setSelecionados(new Set())}>limpar seleção</button>
        </div>
      )}

      {exportando && <Espera texto="Montando sua planilha com tudo dentro…" />}
      {aviso && <div className="alerta" style={{ borderColor: 'var(--verde)',
                     background: 'var(--verde-suave)', color: 'var(--verde-escuro)' }}>{aviso}</div>}
      {erro && <div className="alerta">{erro}</div>}

      {!lista ? <p>Carregando…</p> : lista.length === 0 ? (
        <p className="explica centro">Nenhum colaborador com esses filtros.</p>
      ) : (
        <table className="rh-tabela">
          <thead>
            <tr>
              <th style={{ width: 34 }}>
                <CheckMestre
                  marcado={registros.length > 0 && registros.every((c) => selecionados.has(c.id))}
                  parcial={registros.some((c) => selecionados.has(c.id))
                           && !registros.every((c) => selecionados.has(c.id))}
                  onChange={() => selecionarTodos(
                    !registros.every((c) => selecionados.has(c.id)))}
                  title="Selecionar todos os registros visíveis" />
              </th>
              <th>Nome</th><th>CPF</th><th>Posto</th><th>Nascimento</th>
              <th>Contato</th><th>Situação/Status</th><th>Ações</th></tr>
          </thead>
          <tbody>
            {lista.map((c) => (
              <tr key={c.id}>
                <td><input type="checkbox" style={{ width: 'auto', minHeight: 0 }}
                           checked={selecionados.has(c.id)} onChange={() => alternarSel(c.id)}
                           title="Selecionar para ação em massa" /></td>
                <td><strong>{c.nome_completo}</strong><br /><small>{c.email}</small></td>
                <td>{fmtCpf(c.cpf)}</td>
                <td>{c.posto_nome || '—'}</td>
                <td>{fmtDataBR(c.nascimento)}</td>
                <td>{c.celular_whatsapp || '—'}</td>
                <td>
                  {c.situacao
                    ? <span className="chip" style={{ '--chip-cor': c.situacao === 'ativo' ? '#0fb257' : '#889' }}>
                        {c.situacao === 'ativo' ? '🟢 Ativo' : '⚪ Desligado'}
                        {c.data_desligamento ? ` (${c.data_desligamento})` : ''}
                      </span>
                    : <span className="chip" style={{ '--chip-cor': statusInfo(c.status).cor }}>
                        {statusInfo(c.status).icone} {statusInfo(c.status).label}</span>}
                  {c.na_dominio_em && (
                    <span className="chip" style={{ '--chip-cor': '#3b7dd8', marginLeft: '.3rem' }}
                          title={`Lançada no sistema Domínio em ${new Date(c.na_dominio_em).toLocaleDateString('pt-BR')}`}>
                      🧾 Domínio</span>)}
                </td>
                <td className="acoes-candidato">
                  <button className="btn-secundario btn-mini" onClick={() => aoAbrir(c.id)}>Abrir</button>
                  {c.situacao !== 'ativo' && (
                    <button className="btn-secundario btn-mini" onClick={() => efetivar(c)}
                            title="Tornar colaborador ativo">Efetivar</button>)}
                  {c.situacao === 'ativo' && (
                    <>
                      <button className="btn-secundario btn-mini" onClick={() => transferir(c)}
                              title="Transferir de posto">Transferir</button>
                      <button className="btn-secundario btn-mini" onClick={() => desligar(c)}
                              title="Registrar desligamento">Desligar</button>
                    </>)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </main>
  )
}
