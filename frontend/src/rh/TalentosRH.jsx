import { useEffect, useState } from 'react'
import { fmtData, fmtDataHora } from '../fmt.js'
import { rh as api } from '../api.js'
import DashPlanilha from './DashPlanilha.jsx'
import MemoriaPessoa from './MemoriaPessoa.jsx'
import TelemetriaPessoa from './TelemetriaPessoa.jsx'
import Modal from '../Modal.jsx'
import VisualizadorArquivo from '../VisualizadorArquivo.jsx'

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
  // {blob, nome, talento} — currículo exibido na tela, amarrado ao talento
  // para não reaparecer no painel de outra pessoa.
  const [doc, setDoc] = useState(null)

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

  // Arquivar/desarquivar PEDE O MOTIVO, que vira anotação no mini-CRM com
  // autor e data (feedback 2026-07-28). Não há campo novo no talento: o
  // histórico da pessoa mora num lugar só, e anexar documento ao arquivamento
  // já funciona pela tela de anotações.
  const mudarStatus = async (t, status) => {
    const arquivando = status === 'arquivado'
    const motivo = window.prompt(arquivando
      ? `Arquivar ${t.nome} — por quê?\n\nFica registrado nas anotações com o seu nome e a data.`
      : `Reabrir ${t.nome} — por quê?\n\nFica registrado nas anotações com o seu nome e a data.`,
      '')
    if (motivo === null) return   // cancelou
    try {
      await api.statusTalento(t.id, status, motivo.trim() || null)
      setMsg({ tipo: 'ok', texto: arquivando
        ? `${t.nome} arquivado. Para desfazer, filtre por "Arquivado" e clique em Reabrir.`
        : `${t.nome} voltou para a triagem.` })
      await recarregar()
    } catch (e) { setMsg({ tipo: 'erro', texto: `Não foi possível atualizar (${e.detail || e.message}).` }) }
  }

  // O currículo abre NA TELA (v2.33, pedido do Bruno): "não baixasse
  // necessariamente o currículo, mas que tivesse opção para renderizar o
  // currículo na tela ali na versão desktop, como no módulo de admissão".
  // Word chega aqui já convertido em PDF pelo backend (LibreOffice), então o
  // caso "abriu uma aba em branco" da v2.11 deixou de existir. O botão de
  // baixar continua dentro do visualizador.
  //
  // ABRE A FICHA JUNTO — e isso não é conveniência, é o conserto de um clique
  // MORTO (feedback 2026-08-02: *"eu cliquei, disse que renderizou, mas eu tive
  // que clicar em 'ver ficha' para abrir o card"*). O visualizador mora DENTRO
  // da `FichaTalento`, que só é montada quando `aberto === t.id`; com a ficha
  // fechada — o estado padrão de toda linha — o `setDoc` preenchia um estado
  // que não tinha onde renderizar. Nada acontecia na tela: sem erro, sem
  // espera, sem aba nova. E, pior, o currículo aparecia RETROATIVAMENTE se a
  // pessoa clicasse em "Ver ficha" depois, como se o sistema tivesse guardado
  // rancor do clique anterior.
  //
  // A regra que fica: quem abre um documento tem que abrir o lugar onde ele é
  // exibido, na mesma ação. Estado de conteúdo e estado de visibilidade não
  // podem ser independentes quando um só existe dentro do outro.
  const verCurriculo = async (t) => {
    setMsg(null)
    setAberto(t.id)
    try {
      const blob = await api.baixarCurriculoTalento(t.id)
      setDoc({ blob, nome: t.curriculo_nome || 'curriculo', talento: t.id })
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
    // Currículo e anotações ficam LOGO ABAIXO DO NOME (feedback 2026-07-28):
    // o RH precisava abrir o modal para descobrir que não havia anotação, e o
    // 📎 era só um enfeite — agora abre o currículo direto daqui.
    { chave: 'nome', rotulo: 'Nome', ordenavel: true, filtro: 'texto', sempreVisivel: true,
      render: (t) => (<>
        {/* Sem e-mail, NADA embaixo do nome — nem o travessão. Ele não
            informa (o rótulo "e-mail" nem aparece ali) e no modo card ficava
            um traço solto ao lado do nome. */}
        <strong>{t.nome}</strong>{t.email && <><br /><small>{t.email}</small></>}
        <div className="linha-atalhos">
          {/* ÚNICO ponto clicável do currículo na linha (feedback 2026-08-02:
              *"fica o clicável em dois lugares, é necessário apenas um"*). A
              coluna "Currículo" virou só Sim/Não — serve para FILTRAR e para
              responder de bate-pronto quem anexou; abrir é aqui, junto do nome
              de quem se está lendo. Quem não anexou não mostra atalho nenhum:
              botão que não faz nada é ruído. */}
          {t.tem_curriculo && (
            <button className="btn-link" onClick={() => verCurriculo(t)}
                    title={t.curriculo_nome || 'abrir currículo'}>📎 currículo</button>)}
          {t.anotacoes > 0 && (
            <button className="btn-link" onClick={() => setAnotando(t)}
                    title={`${t.ultima_anotacao_autor || ''} — ${t.ultima_anotacao || ''}`
                      + (t.anotacoes > 1 ? `\n(+${t.anotacoes - 1} anterior(es))` : '')}>
              🗒️ {t.anotacoes} anotaç{t.anotacoes > 1 ? 'ões' : 'ão'}</button>)}
        </div>
      </>) },
    // Telefone em coluna própria — sem ele o RH não tem como contatar o talento
    // (antes só aparecia como fallback do e-mail no Nome, então sumia p/ quem
    // tinha e-mail). O dump já traz `telefone`.
    // Oculta por padrão (v2.59): o contato principal já aparece embaixo do
    // nome, e a tabela precisava caber na tela sem rolagem lateral. Continua
    // a um clique em "⚙ Colunas".
    { chave: 'telefone', rotulo: 'Telefone', filtro: 'texto', oculta: true,
      render: (t) => t.telefone || '—' },
    { chave: 'cargos', rotulo: 'Cargos', ordenavel: true, filtro: 'lista', quebra: true,
      valor: (t) => (t.cargos_interesse?.length ? t.cargos_interesse : (t.cargo_interesse ? [t.cargo_interesse] : [])) },
    { chave: 'tags', rotulo: 'Tags', filtro: 'lista', quebra: true,
      // valor = nomes das tags (o DashPlanilha filtra por esse texto)
      valor: (t) => (t.tags || []).map((g) => g.nome),
      render: (t) => (t.tags || []).length
        ? (t.tags || []).map((g) => (
            // `title` com o nome inteiro: a tag de reaproveitamento nasce do
            // cargo da vaga e chega a 41 caracteres com os cargos reais da base
            // ("reaproveitar: Auxiliar de Serviços Gerais"), então o CSS a corta
            // com reticências para ela não esticar a coluna (v2.72.3). Cortar
            // sem `title` esconderia qual tag é — a regra da v2.59: a contagem
            // fica na célula, o texto inteiro no `title`.
            <span key={g.id} className="chip" title={g.nome}
                  style={{ '--chip-cor': g.cor || undefined }}>{g.nome}</span>))
        : '—' },
    // Oculta por padrão (v2.59): o filtro de cidade continua na barra do dash,
    // e a coluna era o que faltava para a tabela caber sem rolagem lateral.
    { chave: 'cidade', rotulo: 'Cidade', ordenavel: true, filtro: 'lista', oculta: true },
    { chave: 'regioes', rotulo: 'Regiões', oculta: true, quebra: true, valor: (t) => t.regioes || [] },
    { chave: 'tipo_contratacao', rotulo: 'Contratação', filtro: 'select', oculta: true,
      opcoes: [{ v: 'efetivo', r: 'Efetivo' }, { v: 'intermitente', r: 'Intermitente' }, { v: 'tanto_faz', r: 'Tanto faz' }],
      valor: (t) => TIPO_ROT[t.tipo_contratacao] || '' },
    { chave: 'ja_trabalhou_funcao', rotulo: 'Já atuou', oculta: true, valor: (t) => simNao(t.ja_trabalhou_funcao) },
    { chave: 'recebe_seguro_desemprego', rotulo: 'Seg.-desemprego', oculta: true, valor: (t) => simNao(t.recebe_seguro_desemprego) },
    // Só RESPONDE "anexou?" — quem abre é o atalho embaixo do nome. Antes esta
    // célula tinha um segundo "📎 ver" idêntico, então o mesmo currículo era
    // clicável duas vezes na MESMA linha; e quem não anexou virava um "—" que
    // não diz se ninguém pediu ou se a pessoa não mandou. Sim/Não responde.
    // Oculta por padrão (v2.62): quem TEM currículo já mostra o atalho "📎
    // currículo" embaixo do nome, então a coluna só respondia pelos que não
    // têm — e custava 102px numa tabela que estourava em 1200px. O FILTRO
    // continua na barra, que é o uso real ("me mostre só quem anexou").
    { chave: 'tem_curriculo', rotulo: 'Currículo', filtro: 'select', oculta: true,
      opcoes: [{ v: 'Sim', r: 'Sim' }, { v: 'Não', r: 'Não' }],
      valor: (t) => t.tem_curriculo ? 'Sim' : 'Não',
      render: (t) => t.tem_curriculo ? 'Sim' : 'Não' },
    { chave: 'teste_status', rotulo: 'Teste', filtro: 'select',
      opcoes: [{ v: 'enviado', r: 'Enviado' }, { v: 'em_andamento', r: 'Fazendo' }, { v: 'concluido', r: 'Concluído' }],
      valor: (t) => t.teste_status || '',
      render: (t) => t.teste_status ? chip(...(TESTE[t.teste_status] || [t.teste_status, '#888'])) : '—' },
    { chave: 'status', rotulo: 'Status', ordenavel: true, filtro: 'select',
      opcoes: [{ v: 'novo', r: 'Novo' }, { v: 'em_analise', r: 'Em análise' },
               { v: 'convertido', r: 'Convertido' }, { v: 'arquivado', r: 'Arquivado' }],
      valor: (t) => (STATUS[t.status] || [t.status])[0],
      render: (t) => chip(...(STATUS[t.status] || [t.status, '#888'])) },
    // Só a DATA na célula; a hora fica no `title` (v2.59). Antes mostrava
    // data+hora e repetia a MESMA string no title — 172px, a coluna mais larga
    // da tabela depois das ações, para uma informação que quase nunca se usa
    // ao minuto.
    { chave: 'criado_em', rotulo: 'Cadastro', ordenavel: true, nowrap: true, valor: (t) => t.criado_em,
      render: (t) => <span title={fmtDataHora(t.criado_em)}>{fmtData(t.criado_em)}</span> },
  ]

  const acoesLinha = (t) => (<>
    <button className="btn-secundario btn-mini"
            onClick={() => setAberto(aberto === t.id ? null : t.id)}>
      {aberto === t.id ? '▲ Fechar' : '👁 Ver ficha'}</button>
    <button className="btn-secundario btn-mini" onClick={() => setAnotando(t)}>
      🗒️ Anotações</button>
    {t.email && t.status !== 'convertido' && (
      <button className="btn-secundario btn-mini" onClick={() => enviarTeste(t)}>📝 Teste</button>)}
    {t.status === 'arquivado' && (
      <button className="btn-secundario btn-mini" onClick={() => mudarStatus(t, 'novo')}>
        ↩ Reabrir</button>)}
    {t.status !== 'convertido' && t.status !== 'arquivado' && (
      <button className="btn-secundario btn-mini" onClick={() => mudarStatus(t, 'arquivado')}>Arquivar</button>)}
    {t.status !== 'convertido' && (
      <button className="btn-principal btn-mini" onClick={() => converter(t)}>→ Converter</button>)}
  </>)

  // Arquivar em lote: UM motivo para todos (vira uma anotação em cada pessoa,
  // com autor e data). Antes engolia os erros com `.catch(() => {})` e dizia
  // que arquivou tudo mesmo quando falhava — agora presta contas de quem não
  // foi e por quê (mesma regra do lote de documento crítico).
  const arquivarMassa = async (linhas, limpar) => {
    const alvos = linhas.filter((t) => t.status !== 'convertido' && t.status !== 'arquivado')
    if (!alvos.length) {
      setMsg({ tipo: 'erro', texto: 'Nenhum dos selecionados pode ser arquivado '
        + '(já arquivados ou convertidos).' })
      return
    }
    const motivo = window.prompt(`Arquivar ${alvos.length} talento(s) — por quê?\n\n`
      + 'O motivo fica nas anotações de cada um, com o seu nome e a data.', '')
    if (motivo === null) return
    let ok = 0
    const falhas = []
    for (const t of alvos) {
      try { await api.statusTalento(t.id, 'arquivado', motivo.trim() || null); ok++ }
      catch (e) { falhas.push(`${t.nome} (${e.detail || e.message})`) }
    }
    const ignorados = linhas.length - alvos.length
    setMsg({ tipo: falhas.length ? 'erro' : 'ok',
      texto: `${ok} arquivado(s).`
        + (ignorados ? ` ${ignorados} ignorado(s) por já estarem arquivados ou convertidos.` : '')
        + (falhas.length ? ` Não deu para arquivar: ${falhas.join('; ')}.` : '') })
    limpar(); recarregar()
  }

  const acoesMassa = (linhas, limpar) => (<>
    <button className="btn-secundario btn-mini" onClick={() => enviarTesteMassa(linhas, limpar)}>📝 Enviar teste</button>
    <button className="btn-secundario btn-mini" onClick={() => arquivarMassa(linhas, limpar)}>
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
                        ? <FichaTalento t={t} verCurriculo={verCurriculo}
                                        doc={doc?.talento === t.id ? doc : null}
                                        fecharDoc={() => setDoc(null)} /> : null)}
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

function FichaTalento({ t, verCurriculo, doc, fecharDoc }) {
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
        {/* Aqui o botão FECHA quando o currículo já está aberto — sem isso ele
            recarregaria o mesmo arquivo e nada mudaria na tela, que é a versão
            silenciosa do clique morto que este feedback veio consertar. */}
        <Campo rotulo="Currículo">
          {t.tem_curriculo
            ? (doc
                ? <button className="btn-link" onClick={fecharDoc}>▲ fechar currículo</button>
                : <button className="btn-link" onClick={() => verCurriculo(t)}>
                    📎 {t.curriculo_nome || 'abrir currículo'}</button>)
            : 'não enviou'}</Campo>
        <Campo rotulo="Consentimento LGPD">
          {t.consentimento_lgpd_em ? `aceito em ${fmtDataHora(t.consentimento_lgpd_em)}` : null}</Campo>
        <Campo rotulo="Cadastro">{fmtDataHora(t.criado_em)}</Campo>
      </div>
      {/* O currículo renderiza AQUI, na ficha, e não em aba nova (v2.33) — é o
          "analisa na hora" que o Bruno pediu: ler o currículo com os dados da
          pessoa do lado, sem trocar de aba nem baixar. */}
      {doc && <VisualizadorArquivo blob={doc.blob} nome={doc.nome} aoFechar={fecharDoc} />}
      {/* Diagnóstico: o que aconteceu na TELA desta pessoa (v2.24). Recolhido —
          só importa quando ela relata que não conseguiu se cadastrar. */}
      <TelemetriaPessoa talentoId={t.id} />
    </div>
  )
}
