import { useEffect, useRef, useState } from 'react'
import { fmtData } from '../fmt.js'
import { rh as api } from '../api.js'
import { comAmpulheta } from '../Carregando.jsx'
import DashPlanilha from './DashPlanilha.jsx'

const STATUS = {
  novo: ['Novo', '#5bc0de'],
  em_analise: ['Em análise', '#e9a63a'],
  convertido: ['Convertido ✓', '#4f9d3a'],
  arquivado: ['Arquivado', '#999'],
}
const TESTE = {
  enviado: ['Teste enviado', '#8a6d3b'],
  em_andamento: ['Fazendo teste', '#c8a415'],
  concluido: ['Teste concluído', '#0fb257'],
}
const TIPO_ROT = { efetivo: 'Efetivo', intermitente: 'Intermitente', tanto_faz: 'Efetivo ou intermitente' }
const simNao = (v) => v == null ? '—' : v ? 'Sim' : 'Não'

// Dashboard-planilha do Banco de Talentos: ordena/filtra por coluna, seleção +
// ações em massa, colunas configuráveis e export. Enviar teste avulso, ver
// currículo e converter em candidato — tudo integrado.
export default function TalentosRH({ aoAbrir }) {
  const [talentos, setTalentos] = useState(null)
  const [msg, setMsg] = useState(null)
  const inputPlanilha = useRef(null)

  const recarregar = () => api.listarTalentos({}).then(setTalentos).catch(() => setTalentos([]))
  useEffect(() => { recarregar() }, [])

  const importar = async (arquivo) => {
    if (!arquivo) return
    setMsg(null)
    try {
      const r = await comAmpulheta('Importando a planilha do Banco de Talentos…',
                                   () => api.importarTalentosPlanilha(arquivo))
      setMsg({ tipo: 'ok', texto: `Importação concluída: ${r.criados} novo(s), `
        + `${r.pulados} já existente(s) pulado(s) (de ${r.total_planilha} na planilha).` })
      await recarregar()
    } catch (e) {
      setMsg({ tipo: 'erro', texto: e.detail === 'sem_coluna_nome'
        ? 'A planilha precisa ter a coluna "Nome completo". Confira o export do Forms.'
        : `Falha ao importar (${e.detail || e.message}).` })
    } finally { if (inputPlanilha.current) inputPlanilha.current.value = '' }
  }

  const converter = async (t) => {
    if (!window.confirm(`Converter ${t.nome} em candidato e iniciar a admissão?`)) return
    setMsg(null)
    try {
      const r = await api.converterTalento(t.id)
      setMsg({ tipo: 'ok', texto: r.email_enviado
        ? `${t.nome} virou candidato e recebeu o convite por e-mail. Abrindo a ficha…`
        : `${t.nome} virou candidato. ${t.email ? 'O e-mail não saiu — ' : 'Sem e-mail — '}copie o link na tela do candidato e mande pelo WhatsApp. Abrindo a ficha…` })
      await recarregar()
      if (aoAbrir) setTimeout(() => aoAbrir(r.candidato_id), 600)
    } catch (e) {
      setMsg({ tipo: 'erro', texto: e.detail === 'talento_ja_convertido'
        ? 'Este talento já foi convertido.' : `Não foi possível converter (${e.detail || e.message}).` })
    }
  }

  const mudarStatus = async (t, status) => {
    if (status === 'arquivado' && !window.confirm(`Arquivar ${t.nome}? Ele sai da triagem ativa.`)) return
    try { await api.statusTalento(t.id, status); await recarregar() }
    catch (e) { setMsg({ tipo: 'erro', texto: `Não foi possível atualizar (${e.detail || e.message}).` }) }
  }

  const verCurriculo = async (t) => {
    setMsg(null)
    try {
      const blob = await api.baixarCurriculoTalento(t.id)
      const url = URL.createObjectURL(blob)
      window.open(url, '_blank'); setTimeout(() => URL.revokeObjectURL(url), 30000)
    } catch (e) { setMsg({ tipo: 'erro', texto: `Não foi possível abrir o currículo (${e.detail || e.message}).` }) }
  }

  const enviarTeste = async (t) => {
    if (!t.email) { setMsg({ tipo: 'erro', texto: `${t.nome} não tem e-mail cadastrado — não dá para enviar o teste.` }); return }
    if (!window.confirm(`Enviar teste (DISC + situacional) para ${t.nome} (${t.email})?`)) return
    setMsg(null)
    try {
      const r = await api.enviarTesteTalento(t.id)
      setMsg({ tipo: 'ok', texto: r.email_enviado
        ? `Teste enviado para ${t.email}.`
        : `Link do teste gerado, mas o e-mail não saiu. Copie e mande pelo WhatsApp: ${r.url}` })
      await recarregar()
    } catch (e) { setMsg({ tipo: 'erro', texto: `Não foi possível enviar (${e.detail || e.message}).` }) }
  }

  const enviarTesteMassa = async (linhas, limpar) => {
    const comEmail = linhas.filter((t) => t.email)
    if (!comEmail.length) { setMsg({ tipo: 'erro', texto: 'Nenhum dos selecionados tem e-mail.' }); return }
    if (!window.confirm(`Enviar teste para ${comEmail.length} talento(s) com e-mail?`)) return
    setMsg(null)
    let ok = 0
    for (const t of comEmail) { try { await api.enviarTesteTalento(t.id); ok++ } catch { /* segue */ } }
    setMsg({ tipo: 'ok', texto: `Teste enviado para ${ok} de ${comEmail.length}.` })
    limpar(); await recarregar()
  }

  const chip = (rot, cor) => <span className="chip" style={{ '--chip-cor': cor }}>{rot}</span>

  const colunas = [
    { chave: 'nome', rotulo: 'Nome', ordenavel: true, filtro: 'texto', sempreVisivel: true,
      render: (t) => (<><strong>{t.nome}</strong><br /><small>{t.email || t.telefone || '—'}</small>
        {t.tem_curriculo && <span title="Enviou currículo"> 📎</span>}</>) },
    { chave: 'cargos', rotulo: 'Cargos', ordenavel: true, filtro: 'texto',
      valor: (t) => (t.cargos_interesse?.length ? t.cargos_interesse : (t.cargo_interesse ? [t.cargo_interesse] : [])) },
    { chave: 'cidade', rotulo: 'Cidade', ordenavel: true, filtro: 'texto' },
    { chave: 'regioes', rotulo: 'Regiões', valor: (t) => t.regioes || [] },
    { chave: 'tipo_contratacao', rotulo: 'Contratação', filtro: 'select',
      opcoes: [{ v: 'efetivo', r: 'Efetivo' }, { v: 'intermitente', r: 'Intermitente' }, { v: 'tanto_faz', r: 'Tanto faz' }],
      valor: (t) => TIPO_ROT[t.tipo_contratacao] || '' },
    { chave: 'ja_trabalhou_funcao', rotulo: 'Já atuou', valor: (t) => simNao(t.ja_trabalhou_funcao) },
    { chave: 'recebe_seguro_desemprego', rotulo: 'Seg.-desemprego', valor: (t) => simNao(t.recebe_seguro_desemprego) },
    { chave: 'tem_curriculo', rotulo: 'Currículo', filtro: 'select',
      opcoes: [{ v: 'Sim', r: 'Tem' }, { v: 'Não', r: 'Não tem' }],
      valor: (t) => t.tem_curriculo ? 'Sim' : 'Não',
      render: (t) => t.tem_curriculo
        ? <button className="btn-link" onClick={() => verCurriculo(t)}>📎 ver</button> : '—' },
    { chave: 'teste_status', rotulo: 'Teste', filtro: 'select',
      opcoes: [{ v: 'enviado', r: 'Enviado' }, { v: 'em_andamento', r: 'Fazendo' }, { v: 'concluido', r: 'Concluído' }],
      valor: (t) => t.teste_status || '',
      render: (t) => t.teste_status ? chip(...(TESTE[t.teste_status] || [t.teste_status, '#888'])) : '—' },
    { chave: 'status', rotulo: 'Status', ordenavel: true, filtro: 'select',
      opcoes: [{ v: 'novo', r: 'Novo' }, { v: 'em_analise', r: 'Em análise' },
               { v: 'convertido', r: 'Convertido' }, { v: 'arquivado', r: 'Arquivado' }],
      valor: (t) => (STATUS[t.status] || [t.status])[0],
      render: (t) => chip(...(STATUS[t.status] || [t.status, '#888'])) },
    { chave: 'criado_em', rotulo: 'Cadastro', ordenavel: true, valor: (t) => t.criado_em,
      render: (t) => fmtData(t.criado_em) },
  ]

  const acoesLinha = (t) => (<>
    {t.email && t.status !== 'convertido' && (
      <button className="btn-secundario btn-mini" onClick={() => enviarTeste(t)}>📝 Teste</button>)}
    {t.status !== 'convertido' && (<>
      <button className="btn-secundario btn-mini" onClick={() => mudarStatus(t, 'arquivado')}>Arquivar</button>
      <button className="btn-principal btn-mini" onClick={() => converter(t)}>→ Converter</button>
    </>)}
  </>)

  const acoesMassa = (linhas, limpar) => (<>
    <button className="btn-secundario btn-mini" onClick={() => enviarTesteMassa(linhas, limpar)}>📝 Enviar teste</button>
    <button className="btn-secundario btn-mini"
            onClick={async () => { for (const t of linhas) await api.statusTalento(t.id, 'arquivado').catch(() => {}); limpar(); recarregar() }}>
      Arquivar</button>
  </>)

  return (
    <main className="rh-painel">
      <header className="rh-topo">
        <h1>🎯 Banco de Talentos</h1>
        <div>
          <input ref={inputPlanilha} type="file" accept=".xlsx" hidden
                 onChange={(e) => importar(e.target.files?.[0])} />
          <button className="btn-secundario btn-mini" onClick={() => inputPlanilha.current?.click()}>
            ⬆ Importar planilha (Forms)</button>
        </div>
      </header>
      <p className="explica">Interessados do formulário público (<code>/banco-de-talentos</code>) ou
        importados da planilha do Microsoft Forms. Ordene por qualquer coluna, filtre, selecione para
        agir em massa, envie testes e converta em candidato — os dados migram e o link de admissão é disparado.</p>

      {msg && <div className={msg.tipo === 'erro' ? 'alerta' : 'sucesso'}>{msg.texto}</div>}

      {!talentos ? <p>Carregando…</p> : (
        <DashPlanilha id="talentos" colunas={colunas} dados={talentos}
                      acoesLinha={acoesLinha} acoesMassa={acoesMassa}
                      vazio="Nenhum talento cadastrado ainda." />
      )}
    </main>
  )
}
