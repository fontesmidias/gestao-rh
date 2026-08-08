import { useEffect, useState } from 'react'
import CampoComVariaveis from '../CampoComVariaveis.jsx'
import { rh as api } from '../api.js'

// Textos dos e-mails do sistema (v2.06, pedido do Bruno em 2026-07-28: "uma
// página com os e-mails todos que existem, puxando suas respectivas variáveis,
// bem como um preview do que foi alterado e manter um histórico").
//
// A tela lista TODOS os e-mails do catálogo — inclusive os que ninguém editou —
// porque metade do valor é o RH finalmente SABER o que o sistema manda. Edição
// abre na própria linha (sistema de design: nunca formulário no topo).

const fmtData = (v) => (v ? new Date(v).toLocaleString('pt-BR') : '—')

export default function EmailsConfig() {
  const [itens, setItens] = useState(null)
  const [aberto, setAberto] = useState(null)
  const [erro, setErro] = useState(null)

  const carregar = async () => {
    try { setItens(await api.listarEmails()) } catch { setErro('Não foi possível carregar os e-mails.') }
  }
  useEffect(() => { carregar() }, [])

  if (erro) return <div className="rh-card"><div className="alerta">{erro}</div></div>
  if (!itens) return <div className="rh-card"><p className="explica">Carregando…</p></div>

  const grupos = itens.reduce((acc, i) => {
    (acc[i.grupo] = acc[i.grupo] || []).push(i)
    return acc
  }, {})

  return (
    <div className="rh-card">
      <h3>✉️ Textos dos e-mails</h3>
      <p className="explica">Estes são todos os e-mails que o sistema envia. Clique em um
        para ver as variáveis disponíveis, editar o texto, conferir no preview e ver o
        histórico de alterações. O que você não editar continua com o texto padrão.</p>

      {Object.entries(grupos).map(([grupo, lista]) => (
        <div key={grupo}>
          <h4 className="rh-grupo-titulo">{grupo}</h4>
          {lista.map((it) => (
            <div key={it.chave} className="email-item">
              <button className="email-cabeca"
                      onClick={() => setAberto(aberto === it.chave ? null : it.chave)}>
                <span>
                  <strong>{it.rotulo}</strong>
                  {it.personalizado && <span className="chip-mini">editado</span>}
                  {it.critico && <span className="chip-mini alerta-mini">acesso</span>}
                  <br />
                  <small className="explica">{it.quando}</small>
                </span>
                <span>{aberto === it.chave ? '▲' : '▼'}</span>
              </button>
              {aberto === it.chave && (
                <Editor item={it} aoSalvar={carregar} />
              )}
            </div>
          ))}
        </div>
      ))}
    </div>
  )
}

function Editor({ item, aoSalvar }) {
  const [assunto, setAssunto] = useState(item.assunto)
  const [corpo, setCorpo] = useState(item.corpo)
  const [botao, setBotao] = useState(item.botao_texto || '')
  const [previa, setPrevia] = useState(null)
  const [versoes, setVersoes] = useState(null)
  const [msg, setMsg] = useState(null)     // mensagem PERTO do botão que a gerou
  const [ocupado, setOcupado] = useState(false)

  const mudou = assunto !== item.assunto || corpo !== item.corpo
    || (botao || '') !== (item.botao_texto || '')

  const verPrevia = async () => {
    setMsg(null); setOcupado(true)
    try {
      setPrevia(await api.previewEmail(item.chave,
        { assunto, corpo, botao_texto: botao || null }))
    } catch {
      setMsg({ tipo: 'erro', texto: 'Não foi possível gerar o preview.' })
    } finally { setOcupado(false) }
  }

  // O preview mostra como fica na tela; só o envio real mostra como o Gmail e
  // o Outlook renderizam de fato — que é onde a formatação costuma quebrar.
  // Vai só para a caixa de quem está editando (o RH não escolhe destinatário).
  const enviarTeste = async () => {
    setMsg(null); setOcupado(true)
    try {
      const r = await api.enviarTesteEmail(item.chave,
        { assunto, corpo, botao_texto: botao || null })
      setMsg({ tipo: 'ok', texto: `Teste enviado para ${r.enviado_para}. `
        + 'Confira também a caixa de spam — o assunto começa com [TESTE].' })
    } catch (e) {
      const d = e.detail || e.message || ''
      setMsg({ tipo: 'erro', texto: d === 'smtp_nao_configurado'
        ? 'O envio de e-mail ainda não está configurado (Configurações → E-mail e integrações).'
        : d === 'sem_email_no_seu_usuario'
          ? 'Seu usuário do painel está sem e-mail cadastrado — o teste iria para lugar nenhum.'
          : `Não foi possível enviar o teste: ${d}` })
    } finally { setOcupado(false) }
  }

  const salvar = async () => {
    setMsg(null); setOcupado(true)
    try {
      await api.salvarEmail(item.chave, { assunto, corpo, botao_texto: botao || null })
      setMsg({ tipo: 'ok', texto: 'Texto salvo. Os próximos e-mails já usam esta versão.' })
      await aoSalvar()
      if (versoes) setVersoes(await api.versoesEmail(item.chave))
    } catch (e) {
      const faltando = e.detail?.faltando
      setMsg({ tipo: 'erro', texto: faltando
        ? `Faltou a variável obrigatória ${faltando.map((f) => `{{${f}}}`).join(', ')} — `
          + 'sem ela o e-mail sai incompleto e a pessoa não consegue continuar.'
        : 'Não foi possível salvar.' })
    } finally { setOcupado(false) }
  }

  const restaurar = async (versao) => {
    setMsg(null); setOcupado(true)
    try {
      const r = await api.restaurarEmail(item.chave, versao)
      if (r.assunto !== undefined) { setAssunto(r.assunto); setCorpo(r.corpo); setBotao(r.botao_texto || '') }
      setMsg({ tipo: 'ok', texto: versao ? `Versão ${versao} restaurada.` : 'Texto padrão restaurado.' })
      await aoSalvar()
      setVersoes(await api.versoesEmail(item.chave))
      if (!versao) setPrevia(null)
    } catch {
      setMsg({ tipo: 'erro', texto: 'Não foi possível restaurar.' })
    } finally { setOcupado(false) }
  }

  const verHistorico = async () => {
    if (versoes) { setVersoes(null); return }
    try { setVersoes(await api.versoesEmail(item.chave)) } catch { setVersoes([]) }
  }

  return (
    <div className="email-editor">
      <div className="email-vars">
        <strong>Variáveis disponíveis</strong> — copie com as chaves duplas:
        <div>
          {item.variaveis.map((v) => (
            <span key={v.nome} className={`chip-var ${v.obrigatoria ? 'obrigatoria' : ''}`}
                  title={v.descricao + (v.obrigatoria ? ' (obrigatória)' : '')}>
              {`{{${v.nome}}}`}
            </span>
          ))}
        </div>
        {item.variaveis.some((v) => v.obrigatoria) && (
          <small className="explica">As destacadas são obrigatórias: sem elas o e-mail
            sairia incompleto, então o sistema não deixa salvar.</small>
        )}
      </div>

      {/* Quem recebe — só nos AVISOS INTERNOS. Nos demais o destinatário é a
          pessoa do processo (candidato, colaborador, assinante). É a MESMA
          matriz de Configurações → Avisos internos, exposta aqui para o RH ter
          o e-mail inteiro num lugar só (pedido de 2026-07-29). */}
      {item.evento && <Destinatarios item={item} aoSalvar={aoSalvar} />}

      {/* Assunto e corpo com o SELETOR DE VARIÁVEIS (v2.82): a lista acima
          continua (é onde as OBRIGATÓRIAS se destacam), mas digitar
          `{{primeiro_nome}}` de memória era o caminho para o erro que não dá
          erro — variável com nome torto fica no texto como está, e o e-mail
          sai com `{{codigo}}` no lugar do código. */}
      <CampoComVariaveis
        como="input" rotulo="Assunto"
        valor={assunto} aoMudar={setAssunto}
        variaveis={Object.fromEntries(item.variaveis.map(
          (v) => [v.nome, v.descricao + (v.obrigatoria ? ' (obrigatória)' : '')]))} />
      <CampoComVariaveis
        rotulo="Texto do e-mail" linhas={8}
        valor={corpo} aoMudar={setCorpo}
        variaveis={Object.fromEntries(item.variaveis.map(
          (v) => [v.nome, v.descricao + (v.obrigatoria ? ' (obrigatória)' : '')]))} />
      <small className="explica">Deixe uma linha em branco entre os parágrafos. A
        aparência (cores, logo, rodapé) é aplicada automaticamente.</small>
      {item.botao_texto_padrao && (
        <label className="campo"><span className="rotulo">Texto do botão</span>
          <input value={botao} onChange={(e) => setBotao(e.target.value)}
                 placeholder={item.botao_texto_padrao} /></label>
      )}

      {msg && <div className={msg.tipo === 'ok' ? 'aviso-inline' : 'alerta'}>{msg.texto}</div>}

      <div className="email-acoes">
        <button className="btn-secundario" onClick={verPrevia} disabled={ocupado}>
          👁 Ver preview</button>
        <button className="btn-secundario" onClick={enviarTeste} disabled={ocupado}
                title="Manda este texto para o seu próprio e-mail, com dados de exemplo">
          📨 Enviar teste para mim</button>
        <button className="btn-principal" onClick={salvar} disabled={ocupado || !mudou}>
          {ocupado ? 'Salvando…' : 'Salvar texto'}</button>
        <button className="btn-link" onClick={verHistorico}>
          {versoes ? 'ocultar histórico' : '🕘 histórico'}</button>
        {item.personalizado && (
          <button className="btn-link" onClick={() => restaurar(null)} disabled={ocupado}>
            voltar ao texto padrão</button>
        )}
      </div>

      {previa && (
        <div className="email-previa">
          <strong>Assim a pessoa recebe</strong> (com dados de exemplo)
          <p className="explica">Assunto: <strong>{previa.assunto}</strong></p>
          <iframe title="preview do e-mail" srcDoc={previa.html} className="email-iframe" />
        </div>
      )}

      {versoes && (
        <div className="email-historico">
          {versoes.length === 0 && <p className="explica">Nenhuma alteração ainda.</p>}
          {versoes.map((v) => (
            <div key={v.versao} className="email-versao">
              <div>
                <strong>Versão {v.versao}</strong> — {v.autor || 'sistema'} em {fmtData(v.criado_em)}
                <br /><small className="explica">{v.assunto}</small>
              </div>
              <button className="btn-link" onClick={() => restaurar(v.versao)} disabled={ocupado}>
                restaurar esta</button>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

// Quem recebe um AVISO INTERNO (v2.21). Vários e-mails separados por vírgula —
// é como o RH pensa a lista. Grava na MESMA matriz de Configurações → Avisos
// internos: não é um segundo lugar de verdade, é a mesma fonte exposta onde ele
// está editando o texto.
function Destinatarios({ item, aoSalvar }) {
  const [texto, setTexto] = useState((item.destinatarios || []).join(', '))
  const [ativo, setAtivo] = useState(item.aviso_ativo !== false)
  const [msg, setMsg] = useState(null)
  const [ocupado, setOcupado] = useState(false)

  const mudou = texto !== (item.destinatarios || []).join(', ')
    || ativo !== (item.aviso_ativo !== false)

  const salvar = async () => {
    setMsg(null); setOcupado(true)
    try {
      const r = await api.salvarDestinatariosEmail(item.chave,
        { destinatarios: texto, ativo })
      setMsg({ tipo: 'ok', texto: r.destinatarios.length
        ? `Vai para: ${r.destinatarios.join(', ')}.`
        : 'Sem destinatário específico — usa o e-mail padrão de avisos.' })
      await aoSalvar()
    } catch (e) {
      const inv = e.detail?.invalidos
      setMsg({ tipo: 'erro', texto: inv
        ? `E-mail inválido: ${inv.join(', ')}.`
        : `Não foi possível salvar (${e.detail?.motivo || e.detail || e.message}).` })
    } finally { setOcupado(false) }
  }

  return (
    <div className="email-vars">
      <strong>Quem recebe este aviso</strong>
      <label className="campo" style={{ marginTop: '.4rem' }}>
        <input value={texto} placeholder="fulano@empresa.com, ciclano@empresa.com"
               onChange={(e) => setTexto(e.target.value)} /></label>
      <small className="explica">Separe vários e-mails por vírgula. Em branco, o
        aviso vai para o e-mail padrão configurado em Avisos internos
        {item.destinatarios_herdado ? ` (hoje: ${item.destinatarios_herdado})` : ''}.</small>
      <label className="explica" style={{ display: 'flex', alignItems: 'center',
                                          gap: '.4rem', marginTop: '.3rem' }}>
        <input type="checkbox" checked={ativo} onChange={(e) => setAtivo(e.target.checked)} />
        <span>Enviar este aviso {ativo ? '' : '(desligado — ninguém recebe)'}</span>
      </label>
      {msg && <div className={msg.tipo === 'erro' ? 'alerta' : 'aviso-inline'}>{msg.texto}</div>}
      <button className="btn-secundario btn-mini" onClick={salvar}
              disabled={ocupado || !mudou} style={{ marginTop: '.4rem' }}>
        {ocupado ? 'Salvando…' : 'Salvar destinatários'}</button>
    </div>
  )
}
