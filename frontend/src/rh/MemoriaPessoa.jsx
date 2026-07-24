import { useEffect, useState } from 'react'
import { rh as api } from '../api.js'
import { fmtDataHora } from '../fmt.js'

// Mini-CRM reutilizável: anotações + tags que acompanham a PESSOA por todo o
// ciclo de vida (talento → candidato → efetivo → desligado). Recebe `pessoa` =
// { talento_id } OU { candidato_id }; o backend junta os dois lados quando há
// vínculo, então a memória feita no talento aparece no candidato depois de
// convertido. Usado no painel da linha do dash de Talentos E na ficha do
// candidato/colaborador (Detalhe). Segue o sistema de design
// (docs/planejamento/08-sistema-de-design.md): tokens, sem style de espaçamento.
export default function MemoriaPessoa({ pessoa }) {
  const [dados, setDados] = useState(null)   // { anotacoes, tags }
  const [catalogo, setCatalogo] = useState([])  // todas as tags ativas
  const [texto, setTexto] = useState('')
  const [anexo, setAnexo] = useState(null)
  const [salvando, setSalvando] = useState(false)
  const [erro, setErro] = useState(null)
  const [abrirTags, setAbrirTags] = useState(false)

  const carregar = () => {
    api.crmMemoria(pessoa).then(setDados).catch((e) => setErro(e.amigavel || e.detail || e.message))
    api.crmTags().then(setCatalogo).catch(() => {})
  }
  useEffect(carregar, [pessoa.talento_id, pessoa.candidato_id])

  const adicionar = async () => {
    if (!texto.trim()) { setErro('Escreva a anotação.'); return }
    setSalvando(true); setErro(null)
    try {
      const nova = await api.crmCriarAnotacao({ ...pessoa, texto: texto.trim() })
      if (anexo) await api.crmAnexarAnotacao(nova.id, anexo)
      setTexto(''); setAnexo(null); carregar()
    } catch (e) { setErro(e.amigavel || e.detail || e.message) }
    finally { setSalvando(false) }
  }

  const excluir = async (id) => {
    if (!window.confirm('Excluir esta anotação?')) return
    try { await api.crmExcluirAnotacao(id); carregar() }
    catch (e) { setErro(e.amigavel || e.detail || e.message) }
  }

  const verAnexo = async (id) => {
    try {
      const blob = await api.crmAnexo(id)
      const url = URL.createObjectURL(blob)
      window.open(url, '_blank')
      setTimeout(() => URL.revokeObjectURL(url), 30000)
    } catch (e) { setErro(e.amigavel || e.detail || e.message) }
  }

  const alternarTag = async (tag, marcada) => {
    try {
      if (marcada) await api.crmDesmarcarTag(pessoa, tag.id)
      else await api.crmMarcarTag({ ...pessoa, tag_id: tag.id })
      carregar()
    } catch (e) { setErro(e.amigavel || e.detail || e.message) }
  }

  if (!dados) return <p className="explica">Carregando anotações…</p>
  const idsMarcadas = new Set((dados.tags || []).map((t) => t.id))

  return (
    <div className="crm-memoria">
      {erro && <div className="alerta">{erro}</div>}

      {/* Tags da pessoa + botão para marcar/desmarcar (toggle do seletor) */}
      <div className="crm-tags-linha">
        {(dados.tags || []).length === 0 && !abrirTags && (
          <span className="explica">Sem tags.</span>)}
        {(dados.tags || []).map((t) => (
          <span key={t.id} className="chip" style={{ '--chip-cor': t.cor || undefined }}>{t.nome}</span>
        ))}
        <button className="btn-link" onClick={() => setAbrirTags((v) => !v)}>
          {abrirTags ? 'fechar' : '🏷️ tags'}</button>
      </div>
      {abrirTags && (
        <div className="crm-tags-catalogo">
          {catalogo.length === 0
            ? <span className="explica">Nenhuma tag cadastrada. Crie em Configurações → Tags.</span>
            : catalogo.map((t) => {
              const marcada = idsMarcadas.has(t.id)
              return (
                <button key={t.id}
                        className={`chip crm-tag-opcao${marcada ? ' marcada' : ''}`}
                        style={{ '--chip-cor': t.cor || undefined }}
                        onClick={() => alternarTag(t, marcada)}>
                  {marcada ? '✓ ' : ''}{t.nome}</button>
              )
            })}
        </div>
      )}

      {/* Nova anotação */}
      <div className="crm-nova">
        <textarea rows={2} placeholder="Anotação sobre a pessoa (visível a todo o RH)…"
                  value={texto} onChange={(e) => setTexto(e.target.value)} />
        <div className="crm-nova-acoes">
          <label className="btn-link crm-anexo-label">
            📎 {anexo ? anexo.name : 'anexar arquivo'}
            <input type="file" style={{ display: 'none' }}
                   onChange={(e) => setAnexo(e.target.files?.[0] || null)} />
          </label>
          {anexo && <button className="btn-link" onClick={() => setAnexo(null)}>remover anexo</button>}
          <button className="btn-principal btn-mini" disabled={salvando}
                  onClick={adicionar}>{salvando ? 'Salvando…' : 'Adicionar'}</button>
        </div>
      </div>

      {/* Linha do tempo das anotações */}
      {(dados.anotacoes || []).length === 0
        ? <p className="explica">Nenhuma anotação ainda.</p>
        : (
          <ul className="crm-lista">
            {dados.anotacoes.map((a) => (
              <li key={a.id} className="crm-item">
                <div className="crm-item-topo">
                  <span className="crm-item-meta">
                    <strong>{a.autor}</strong> · {fmtDataHora(a.quando)}
                    {a.origem === 'talento' && <span className="crm-badge">quando era talento</span>}
                  </span>
                  <button className="btn-link" onClick={() => excluir(a.id)}>excluir</button>
                </div>
                <p className="crm-item-texto">{a.texto}</p>
                {a.tem_anexo && (
                  <button className="btn-link" onClick={() => verAnexo(a.id)}>
                    📎 {a.anexo_nome || 'anexo'}</button>
                )}
              </li>
            ))}
          </ul>
        )}
    </div>
  )
}
