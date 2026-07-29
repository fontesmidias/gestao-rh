import { useEffect, useState } from 'react'
import { fmtData, fmtDataHora } from '../fmt.js'
import { rh as api } from '../api.js'
import DashPlanilha from './DashPlanilha.jsx'
import MemoriaPessoa from './MemoriaPessoa.jsx'
import Modal from '../Modal.jsx'

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
  // talento com o modal de anotações aberto (v1.97: virou popup — antes era
  // um painel inline na própria linha, feedback 2026-07-27 "pense em algo
  // melhor" — a anotação tem anexo+histórico, não cabia espremida na tabela)
  const [anotando, setAnotando] = useState(null)
  // ficha completa aberta na própria linha (feedback 2026-07-28: "para nós é
  // interessante que apareça todos os campos que as pessoas preencheram").
  // Vai no painel e não em coluna nova: o dash já tem coluna demais, e resumo
  // e origem são texto livre que não cabe em célula.
  const [aberto, setAberto] = useState(null)

  const recarregar = () => api.listarTalentos({}).then(setTalentos).catch(() => setTalentos([]))
  useEffect(() => { recarregar() }, [])

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

  // PDF e imagem abrem em aba nova; Word (e qualquer outro tipo que o navegador
  // não renderiza) BAIXA. Antes tudo ia para window.open e o Word abria uma aba
  // em branco — o arquivo estava certo, o navegador é que não exibe (feedback
  // 2026-07-28: "deu bom para baixar, mas não abriu").
  const verCurriculo = async (t) => {
    setMsg(null)
    try {
      const blob = await api.baixarCurriculoTalento(t.id)
      const url = URL.createObjectURL(blob)
      const exibivel = blob.type === 'application/pdf' || blob.type.startsWith('image/')
      if (exibivel) {
        window.open(url, '_blank')
      } else {
        const a = document.createElement('a')
        a.href = url
        a.download = t.curriculo_nome || 'curriculo'
        document.body.appendChild(a); a.click(); a.remove()
        setMsg({ tipo: 'ok', texto: `O currículo de ${t.nome} está em `
          + `${t.curriculo_nome || 'arquivo'} — o navegador não exibe esse formato, `
          + 'então baixamos para você abrir no Word.' })
      }
      setTimeout(() => URL.revokeObjectURL(url), 30000)
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
      render: (t) => (<><strong>{t.nome}</strong><br /><small>{t.email || '—'}</small>
        {t.tem_curriculo && <span title="Enviou currículo"> 📎</span>}</>) },
    // Telefone em coluna própria — sem ele o RH não tem como contatar o talento
    // (antes só aparecia como fallback do e-mail no Nome, então sumia p/ quem
    // tinha e-mail). O dump já traz `telefone`.
    { chave: 'telefone', rotulo: 'Telefone', filtro: 'texto',
      render: (t) => t.telefone || '—' },
    { chave: 'cargos', rotulo: 'Cargos', ordenavel: true, filtro: 'texto', quebra: true,
      valor: (t) => (t.cargos_interesse?.length ? t.cargos_interesse : (t.cargo_interesse ? [t.cargo_interesse] : [])) },
    { chave: 'tags', rotulo: 'Tags', filtro: 'texto', quebra: true,
      // valor = nomes das tags (o DashPlanilha filtra por esse texto)
      valor: (t) => (t.tags || []).map((g) => g.nome),
      render: (t) => (t.tags || []).length
        ? (t.tags || []).map((g) => (
            <span key={g.id} className="chip" style={{ '--chip-cor': g.cor || undefined }}>{g.nome}</span>))
        : '—' },
    { chave: 'cidade', rotulo: 'Cidade', ordenavel: true, filtro: 'texto' },
    { chave: 'regioes', rotulo: 'Regiões', oculta: true, quebra: true, valor: (t) => t.regioes || [] },
    { chave: 'tipo_contratacao', rotulo: 'Contratação', filtro: 'select', oculta: true,
      opcoes: [{ v: 'efetivo', r: 'Efetivo' }, { v: 'intermitente', r: 'Intermitente' }, { v: 'tanto_faz', r: 'Tanto faz' }],
      valor: (t) => TIPO_ROT[t.tipo_contratacao] || '' },
    { chave: 'ja_trabalhou_funcao', rotulo: 'Já atuou', oculta: true, valor: (t) => simNao(t.ja_trabalhou_funcao) },
    { chave: 'recebe_seguro_desemprego', rotulo: 'Seg.-desemprego', oculta: true, valor: (t) => simNao(t.recebe_seguro_desemprego) },
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
      render: (t) => <span title={fmtDataHora(t.criado_em)}>{fmtDataHora(t.criado_em)}</span> },
  ]

  const acoesLinha = (t) => (<>
    <button className="btn-secundario btn-mini"
            onClick={() => setAberto(aberto === t.id ? null : t.id)}>
      {aberto === t.id ? '▲ Fechar' : '👁 Ver ficha'}</button>
    <button className="btn-secundario btn-mini" onClick={() => setAnotando(t)}>
      🗒️ Anotações</button>
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

  // cards de status clicáveis: o filtro aponta para o RÓTULO da coluna `status`
  // (é assim que o DashPlanilha compara). Clicar filtra; clicar de novo limpa.
  const cards = (talentos || []).length ? [
    { rotulo: 'Total', valor: talentos.length },
    ...['novo', 'em_analise', 'convertido', 'arquivado'].map((s) => ({
      rotulo: STATUS[s][0], cor: STATUS[s][1],
      valor: talentos.filter((t) => t.status === s).length,
      filtro: { chave: 'status', valor: STATUS[s][0] },
    })),
  ] : null

  return (
    <main className="rh-painel">
      <header className="rh-topo">
        <h1>🎯 Banco de Talentos</h1>
        <div />
      </header>
      <p className="explica">Interessados do formulário público (<code>/banco-de-talentos</code>) ou
        importados da planilha do Microsoft Forms (veja <strong>Configurações → 📥 Importações</strong>).
        Ordene por qualquer coluna, filtre, selecione para agir em massa, envie testes e converta em
        candidato — os dados migram e o link de admissão é disparado.</p>

      {msg && <div className={msg.tipo === 'erro' ? 'alerta' : 'sucesso'}>{msg.texto}</div>}

      {!talentos ? <p>Carregando…</p> : (
        <DashPlanilha id="talentos" colunas={colunas} dados={talentos} cards={cards}
                      acoesLinha={acoesLinha} acoesMassa={acoesMassa}
                      linhaExpandida={(t) => (aberto === t.id
                        ? <FichaTalento t={t} verCurriculo={verCurriculo} /> : null)}
                      vazio="Nenhum talento cadastrado ainda." />
      )}
      {anotando && (
        <Modal titulo={`🗒️ Anotações — ${anotando.nome}`} aoFechar={() => setAnotando(null)}>
          <MemoriaPessoa pessoa={{ talento_id: anotando.id }} />
        </Modal>
      )}
    </main>
  )
}

// Ficha completa do talento, aberta NA PRÓPRIA LINHA (feedback 2026-07-28:
// "para nós é interessante que apareça todos os campos que as pessoas
// preencheram, no painel, pois já ajuda na análise humana").
//
// Mostra inclusive o que não tinha lugar nenhum na tela até aqui: o `resumo`
// (o campo mais rico do formulário — "conte sobre sua experiência") e a
// `origem` ("como conheceu a Green House?"). Ambos iam para o banco e nunca
// eram vistos por ninguém.
function Campo({ rotulo, children, largo }) {
  return (
    <div className={largo ? 'ficha-campo largo' : 'ficha-campo'}>
      <span className="ficha-rotulo">{rotulo}</span>
      <div>{children || '—'}</div>
    </div>
  )
}

function FichaTalento({ t, verCurriculo }) {
  const lista = (v) => (Array.isArray(v) && v.length ? v.join(' · ') : null)
  return (
    <div className="ficha-talento">
      <div className="ficha-grade">
        <Campo rotulo="Nome">{t.nome}</Campo>
        <Campo rotulo="E-mail">{t.email}</Campo>
        <Campo rotulo="Telefone">{t.telefone}</Campo>
        <Campo rotulo="Cidade">{t.cidade}</Campo>
        <Campo rotulo="Escolaridade">{t.escolaridade}</Campo>
        <Campo rotulo="Contratação">{TIPO_ROT[t.tipo_contratacao]}</Campo>
        <Campo rotulo="Já atuou na função">{simNao(t.ja_trabalhou_funcao)}</Campo>
        <Campo rotulo="Recebe seguro-desemprego">{simNao(t.recebe_seguro_desemprego)}</Campo>
        <Campo rotulo="Cargos de interesse" largo>{lista(t.cargos_interesse)}</Campo>
        <Campo rotulo="Regiões" largo>{lista(t.regioes)}</Campo>
        <Campo rotulo="Experiência (o que a pessoa escreveu)" largo>
          {t.resumo ? <p className="ficha-texto">{t.resumo}</p> : null}</Campo>
        <Campo rotulo="Como conheceu a Green House" largo>{t.origem}</Campo>
        <Campo rotulo="Currículo">
          {t.tem_curriculo
            ? <button className="btn-link" onClick={() => verCurriculo(t)}>
                📎 {t.curriculo_nome || 'abrir currículo'}</button>
            : 'não enviou'}</Campo>
        <Campo rotulo="Consentimento LGPD">
          {t.consentimento_lgpd_em ? `aceito em ${fmtDataHora(t.consentimento_lgpd_em)}` : null}</Campo>
        <Campo rotulo="Cadastro">{fmtDataHora(t.criado_em)}</Campo>
      </div>
    </div>
  )
}
