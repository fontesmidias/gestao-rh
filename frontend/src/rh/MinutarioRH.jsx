import { useEffect, useState } from 'react'
import { rh as api } from '../api.js'
import { comAmpulheta } from '../Carregando.jsx'
import Modal from '../Modal.jsx'
import SelectBusca from '../SelectBusca.jsx'

const MEIOS = [['whatsapp', '💬 WhatsApp'], ['email', '✉️ E-mail'], ['outro', '📋 Outro']]

// Minutário de mensagens (v1.98, feedback 2026-07-27): modelos CRUD + geração
// assistida por IA a partir de campos da VAGA (nunca dado do candidato — a
// substituição de {{marcadores}} acontece depois, no servidor). O texto
// gerado sempre volta EDITÁVEL: a IA propõe, o RH aprova antes de enviar.
// Envio por copiar + link wa.me (decisão do Bruno) — sem integração com a
// API oficial do WhatsApp.
export default function MinutarioRH() {
  const [modelos, setModelos] = useState(null)
  const [tags, setTags] = useState([])
  const [compondo, setCompondo] = useState(false)
  const [editando, setEditando] = useState(null) // modelo em edição no modal, ou {} para novo
  // Ver a mensagem sem entrar no modo de edição (v2.92, pedido do Bruno): ler
  // o texto era possível só abrindo "editar", o que põe quem só queria
  // conferir a um Enter de alterar um modelo em uso.
  const [vendo, setVendo] = useState(null)
  const [msg, setMsg] = useState(null)

  const copiarTexto = async (m) => {
    try {
      await navigator.clipboard.writeText(m.corpo_base || '')
      setMsg({ tipo: 'ok', texto: `"${m.titulo}" copiado. Cole no WhatsApp ou no e-mail.` })
    } catch {
      // `clipboard` exige contexto seguro (https ou localhost) e permissão do
      // navegador. Falhar calado deixaria a pessoa colando o nada — melhor
      // dizer o que resolve: o texto está à vista no visualizador.
      setVendo(m)
      setMsg({ tipo: 'erro',
               texto: 'O navegador não deixou copiar. O texto está aberto abaixo — '
                      + 'selecione e copie com Ctrl+C.' })
    }
  }

  const carregar = () => api.minutarioModelos(true).then(setModelos).catch(() => setModelos([]))
  useEffect(() => {
    carregar()
    api.crmTags().then(setTags).catch(() => {})
  }, [])

  const duplicar = async (m) => {
    try {
      const novo = await api.minutarioDuplicarModelo(m.id)
      carregar()
      // Nasce INATIVO: a cópia existe para ser ajustada, e um modelo de
      // mensagem ativo já aparece para quem vai disparar.
      setMsg({ tipo: 'ok', texto: `"${novo.titulo}" criado INATIVO. Ajuste e ative.` })
    } catch (e) { setMsg({ tipo: 'erro', texto: `Não foi possível duplicar (${e.detail || e.message}).` }) }
  }

  const excluir = async (m) => {
    if (!window.confirm(`Excluir o modelo "${m.titulo}"?`)) return
    try { await api.minutarioExcluirModelo(m.id); carregar() }
    catch (e) { setMsg({ tipo: 'erro', texto: `Não foi possível excluir (${e.detail || e.message}).` }) }
  }

  if (!modelos) return <main className="rh-painel"><p>Carregando…</p></main>

  return (
    <main className="rh-painel">
      <header className="rh-topo">
        <h1>💬 Minutário de Mensagens</h1>
        <button className="btn-principal btn-mini" onClick={() => setCompondo(true)}>
          ✨ Compor com IA</button>
      </header>
      <p className="explica">Mensagens prontas para WhatsApp e e-mail, com português revisado.
        Preencha os campos da vaga e a IA monta o texto — você sempre confere e edita antes de
        enviar. O envio é por <strong>copiar o texto</strong> ou por um <strong>link do
        WhatsApp</strong> já com a mensagem pronta.</p>

      {msg && <div className={msg.tipo === 'erro' ? 'alerta' : 'sucesso'}>{msg.texto}</div>}

      <div className="rh-topo" style={{ marginTop: '1rem' }}>
        <h2 style={{ fontSize: '1.05rem', margin: 0 }}>Modelos salvos</h2>
        <button className="btn-secundario btn-mini" onClick={() => setEditando({})}>
          + Novo modelo</button>
      </div>

      {modelos.length === 0
        ? <p className="explica">Nenhum modelo salvo ainda. Componha uma mensagem e salve como modelo.</p>
        : (
          <div className="dash-scroll">
            <table className="rh-tabela">
              <thead><tr><th>Título</th><th>Meio</th><th>Tags</th><th>Status</th><th></th></tr></thead>
              <tbody>{modelos.map((m) => (
                <tr key={m.id}>
                  <td><strong>{m.titulo}</strong></td>
                  <td>{(MEIOS.find(([v]) => v === m.meio) || [null, m.meio])[1]}</td>
                  <td>{m.tags.map((t) => (
                    <span key={t.id} className="chip" style={{ '--chip-cor': t.cor || undefined }}>{t.nome}</span>
                  ))}</td>
                  <td>{m.ativo ? 'Ativo' : <em>Inativo</em>}</td>
                  <td>
                    <button className="btn-link" onClick={() => setVendo(m)}>ver</button>
                    <button className="btn-link" onClick={() => copiarTexto(m)}>copiar</button>
                    <button className="btn-link" onClick={() => setEditando(m)}>editar</button>
                    {' · '}
                    <button className="btn-link" onClick={() => duplicar(m)}
                            title="Cria uma cópia inativa para você ajustar">duplicar</button>
                    <button className="btn-link" onClick={() => excluir(m)}>excluir</button>
                  </td>
                </tr>
              ))}</tbody>
            </table>
          </div>
        )}

      {/* Visualizar (v2.92): mostra a mensagem como ela é, com o botão de
          copiar ao lado do texto — é ali que a pessoa está olhando quando
          decide levá-la para o WhatsApp (a regra da distância, v2.47). O
          `<pre>` preserva as quebras de linha: em `<p>` o texto viraria um
          parágrafo só, e a mensagem que se cola tem a formatação que se lê. */}
      {vendo && (
        <Modal titulo={`${vendo.titulo}`} aoFechar={() => setVendo(null)}>
          <p className="explica">
            {(MEIOS.find(([v]) => v === vendo.meio) || [null, vendo.meio])[1]}
            {vendo.tags?.length > 0 && ` · ${vendo.tags.map((t) => t.nome).join(', ')}`}
            {!vendo.ativo && ' · inativo'}
          </p>
          <pre className="bloco-codigo" style={{ whiteSpace: 'pre-wrap' }}>
            {vendo.corpo_base}</pre>
          <div className="navegacao">
            <button className="btn-principal" onClick={() => copiarTexto(vendo)}>
              📋 Copiar mensagem</button>
            <button className="btn-secundario"
                    onClick={() => { setEditando(vendo); setVendo(null) }}>Editar</button>
            <button className="btn-link" onClick={() => setVendo(null)}>Fechar</button>
          </div>
        </Modal>
      )}

      {compondo && (
        <Modal titulo="✨ Compor mensagem com IA" aoFechar={() => setCompondo(false)}>
          <ComporMensagem tags={tags} modelos={modelos.filter((m) => m.ativo)}
                          aoSalvarModelo={() => { setCompondo(false); carregar() }} />
        </Modal>
      )}

      {editando && (
        <Modal titulo={editando.id ? `Editar — ${editando.titulo}` : 'Novo modelo'}
               aoFechar={() => setEditando(null)}>
          <FormModelo modelo={editando} tags={tags}
                      aoSalvo={() => { setEditando(null); carregar() }}
                      aoCancelar={() => setEditando(null)} />
        </Modal>
      )}
    </main>
  )
}

function FormModelo({ modelo, tags, aoSalvo, aoCancelar }) {
  const [titulo, setTitulo] = useState(modelo.titulo || '')
  const [meio, setMeio] = useState(modelo.meio || 'whatsapp')
  const [corpo, setCorpo] = useState(modelo.corpo_base || '')
  const [tagIds, setTagIds] = useState(new Set((modelo.tags || []).map((t) => t.id)))
  const [msg, setMsg] = useState(null)
  const [salvando, setSalvando] = useState(false)

  const alternarTag = (id) => setTagIds((s) => {
    const n = new Set(s); n.has(id) ? n.delete(id) : n.add(id); return n
  })

  const salvar = async () => {
    if (!titulo.trim()) { setMsg({ tipo: 'erro', texto: 'Informe um título.' }); return }
    setSalvando(true); setMsg(null)
    try {
      const dados = { titulo: titulo.trim(), meio, corpo_base: corpo, tag_ids: [...tagIds] }
      if (modelo.id) await api.minutarioEditarModelo(modelo.id, dados)
      else await api.minutarioCriarModelo(dados)
      aoSalvo()
    } catch (e) {
      setMsg({ tipo: 'erro', texto: `Não foi possível salvar (${e.detail || e.message}).` })
    } finally { setSalvando(false) }
  }

  return (
    <div>
      <label className="campo"><span className="rotulo">Título</span>
        <input value={titulo} onChange={(e) => setTitulo(e.target.value)} /></label>
      <label className="campo"><span className="rotulo">Meio</span>
        <SelectBusca valor={meio} aoEscolher={(v) => setMeio(v)}>
          {MEIOS.map(([v, r]) => <option key={v} value={v}>{r}</option>)}
        </SelectBusca></label>
      <label className="campo"><span className="rotulo">Texto do modelo</span>
        <textarea rows={6} value={corpo} onChange={(e) => setCorpo(e.target.value)} /></label>
      {tags.length > 0 && (
        <div className="campo">
          <span className="rotulo">Tags</span>
          <div className="crm-tags-catalogo">
            {tags.map((t) => (
              <button key={t.id} type="button"
                      className={`chip crm-tag-opcao${tagIds.has(t.id) ? ' marcada' : ''}`}
                      style={{ '--chip-cor': t.cor || undefined }}
                      onClick={() => alternarTag(t.id)}>
                {tagIds.has(t.id) ? '✓ ' : ''}{t.nome}</button>
            ))}
          </div>
        </div>
      )}
      {msg && <div className="alerta">{msg.texto}</div>}
      <div className="rh-lote" style={{ marginTop: '.6rem' }}>
        <button className="btn-secundario btn-mini" onClick={aoCancelar}>cancelar</button>
        <button className="btn-principal btn-mini" disabled={salvando} onClick={salvar}>
          {salvando ? 'Salvando…' : 'Salvar'}</button>
      </div>
    </div>
  )
}

// Formulário de composição: cada campo é um "botão" de informação da vaga —
// nenhum é dado de candidato. Gera → mostra editável → RH decide copiar,
// abrir no WhatsApp, ou salvar como modelo novo/atualizar um existente.
function ComporMensagem({ tags, modelos, aoSalvarModelo }) {
  const [campos, setCampos] = useState({
    tom: '', cargo: '', regime: '', salario: '', local: '', escala: '', jornada: '',
    horario: '', requisitos_obrigatorios: '', requisitos_desejaveis: '',
    instrucoes_extra: '', prazo: '',
  })
  const [modeloBaseId, setModeloBaseId] = useState('')
  const [gerando, setGerando] = useState(false)
  const [texto, setTexto] = useState('')
  const [numeroWa, setNumeroWa] = useState('')
  const [msg, setMsg] = useState(null)
  const [salvarComo, setSalvarComo] = useState(false)
  const [tituloNovo, setTituloNovo] = useState('')

  const setCampo = (k, v) => setCampos((c) => ({ ...c, [k]: v }))

  const gerar = async () => {
    setGerando(true); setMsg(null)
    try {
      const r = await api.minutarioCompor({
        ...campos, modelo_base_id: modeloBaseId || null,
      })
      setTexto(r.texto)
    } catch (e) {
      setMsg({ tipo: 'erro', texto: e.detail === 'chave_nao_configurada'
        ? 'A IA (Groq) ainda não está configurada — veja Configurações → E-mail e integrações.'
        : `Não foi possível gerar (${e.detail || e.message}).` })
    } finally { setGerando(false) }
  }

  const copiar = async () => {
    await navigator.clipboard.writeText(texto)
    setMsg({ tipo: 'ok', texto: 'Copiado! Cole no WhatsApp ou e-mail.' })
  }

  const linkWa = () => {
    const numero = numeroWa.replace(/\D/g, '')
    const url = `https://wa.me/${numero ? numero + '/' : ''}?text=${encodeURIComponent(texto)}`
    window.open(url, '_blank')
  }

  const salvarModelo = async () => {
    if (!tituloNovo.trim()) { setMsg({ tipo: 'erro', texto: 'Informe um título para o modelo.' }); return }
    try {
      if (modeloBaseId) await api.minutarioEditarModelo(modeloBaseId, { titulo: tituloNovo.trim(), meio: 'whatsapp', corpo_base: texto, tag_ids: [] })
      else await api.minutarioCriarModelo({ titulo: tituloNovo.trim(), meio: 'whatsapp', corpo_base: texto, tag_ids: [] })
      aoSalvarModelo()
    } catch (e) {
      setMsg({ tipo: 'erro', texto: `Não foi possível salvar o modelo (${e.detail || e.message}).` })
    }
  }

  const campo = (chave, rotulo, placeholder) => (
    <label className="campo" key={chave}>
      <span className="rotulo">{rotulo}</span>
      <input value={campos[chave]} placeholder={placeholder}
             onChange={(e) => setCampo(chave, e.target.value)} />
    </label>
  )

  return (
    <div>
      {modelos.length > 0 && (
        <label className="campo"><span className="rotulo">Usar modelo como referência (opcional)</span>
          <SelectBusca valor={modeloBaseId} aoEscolher={(v) => setModeloBaseId(v)}>
            <option value="">— nenhum, começar do zero —</option>
            {modelos.map((m) => <option key={m.id} value={m.id}>{m.titulo}</option>)}
          </SelectBusca></label>
      )}
      <label className="campo"><span className="rotulo">Tom da mensagem</span>
        <input value={campos.tom} placeholder="ex.: cordial e direto, descontraído, formal"
               onChange={(e) => setCampo('tom', e.target.value)} /></label>
      <div className="linha2">
        {campo('cargo', 'Cargo/função', 'ex.: Auxiliar de Serviços Gerais')}
        <label className="campo"><span className="rotulo">Regime</span>
          <SelectBusca valor={campos.regime} aoEscolher={(v) => setCampo('regime', v)}>
            <option value="">— não informar —</option>
            <option value="efetivo">Efetivo</option>
            <option value="intermitente">Intermitente</option>
          </SelectBusca></label>
      </div>
      <div className="linha2">
        {campo('salario', 'Salário', 'ex.: R$ 1.600,00')}
        {campo('local', 'Local de trabalho', 'ex.: Águas Claras/DF')}
      </div>
      <div className="linha3">
        {campo('escala', 'Escala', 'ex.: 12x36, 5x2')}
        {campo('jornada', 'Jornada', 'ex.: 44h semanais')}
        {campo('horario', 'Horário', 'ex.: 08h às 17h')}
      </div>
      {campo('requisitos_obrigatorios', 'Requisitos obrigatórios', 'ex.: CNH categoria B')}
      {campo('requisitos_desejaveis', 'Requisitos desejáveis', 'ex.: experiência anterior na função')}
      <div className="linha2">
        {campo('instrucoes_extra', 'Instruções adicionais', 'ex.: enviar currículo até sexta')}
        {campo('prazo', 'Prazo', 'ex.: até 05/08')}
      </div>

      <button className="btn-principal btn-mini" disabled={gerando} onClick={gerar}>
        {gerando ? 'Gerando…' : '✨ Gerar mensagem'}</button>

      {texto && (
        <div style={{ marginTop: '.8rem' }}>
          <label className="campo"><span className="rotulo">Mensagem (edite à vontade)</span>
            <textarea rows={8} value={texto} onChange={(e) => setTexto(e.target.value)} /></label>
          <div className="rh-lote">
            <button className="btn-secundario btn-mini" onClick={copiar}>📋 Copiar</button>
            <input placeholder="Número do WhatsApp (opcional, com DDD)" style={{ maxWidth: 220 }}
                   value={numeroWa} onChange={(e) => setNumeroWa(e.target.value)} />
            <button className="btn-secundario btn-mini" onClick={linkWa}>💬 Abrir no WhatsApp</button>
          </div>
          <div className="rh-lote" style={{ marginTop: '.4rem' }}>
            {!salvarComo
              ? <button className="btn-link" onClick={() => { setSalvarComo(true); setTituloNovo(modeloBaseId ? modelos.find((m) => m.id === modeloBaseId)?.titulo || '' : '') }}>
                  💾 salvar como modelo
                </button>
              : (
                <>
                  <input placeholder="Título do modelo" value={tituloNovo}
                         onChange={(e) => setTituloNovo(e.target.value)} />
                  <button className="btn-secundario btn-mini" onClick={() => setSalvarComo(false)}>cancelar</button>
                  <button className="btn-principal btn-mini" onClick={salvarModelo}>
                    {modeloBaseId ? 'Atualizar modelo' : 'Salvar novo modelo'}</button>
                </>
              )}
          </div>
        </div>
      )}
      {msg && <div className={msg.tipo === 'erro' ? 'alerta' : 'sucesso'} style={{ marginTop: '.5rem' }}>{msg.texto}</div>}
    </div>
  )
}
