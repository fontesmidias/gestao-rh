import { useEffect, useState } from 'react'
import { rh as api } from '../api.js'

// O formulário da cartilha (docs/Cartilha do Avaliador, 17-06-2026), 11 seções.
// As escalas, os 7 indicadores, as 8 competências e as 5 recomendações vêm do
// SERVIDOR — o front não duplica os textos do instrumento oficial.
//
// À esquerda, os FATOS do período: o líder revisa o que já registrou em vez de
// escrever do zero com a memória vazia.
export default function Formulario({ avaliacaoId, form, homologando,
                                     aoFechar, aoErro }) {
  const [a, setA] = useState(null)
  const [campos, setCampos] = useState(null)
  const [desvio, setDesvio] = useState(null)
  const [salvando, setSalvando] = useState(false)
  const [passo, setPasso] = useState(null)   // feedback | homologar

  const carregar = () => api.avaliacao(avaliacaoId).then((r) => {
    setA(r)
    setCampos({
      indicadores: r.indicadores || {}, competencias: r.competencias || {},
      pontos_fortes: r.pontos_fortes || '',
      pontos_desenvolver: r.pontos_desenvolver || '',
      pdi: r.pdi && r.pdi.length ? r.pdi : [{ o_que: '', acao: '', prazo: '', acompanhar_em: '' }],
      recomendacao: r.recomendacao || '', recomendacao_data: r.recomendacao_data || '',
      justificativa: r.justificativa || '',
    })
    if (homologando) {
      api.desvioAvaliador(r.avaliador).then((d) => setDesvio(d.desvio)).catch(() => {})
    }
  }).catch((e) => aoErro(e.detail || e.message))
  useEffect(() => { carregar() }, [avaliacaoId])

  if (!a || !campos) return <div className="rh-conferencia"><p>Carregando…</p></div>

  const editavel = a.status === 'rascunho'
  const mexer = (campo, valor) => setCampos({ ...campos, [campo]: valor })
  const marcar = (grupo, chave, valor) =>
    setCampos({ ...campos, [grupo]: { ...campos[grupo], [chave]: valor } })

  const salvar = async (depois) => {
    setSalvando(true)
    try {
      await api.salvarAvaliacao(avaliacaoId, campos)
      if (depois) await depois()
      else carregar()
    } catch (e) {
      aoErro(e.detail && e.detail.erros ? e.detail.erros.join(' ')
        : e.detail === 'somente_o_avaliador' ? 'Só quem criou esta avaliação pode preenchê-la.'
        : (e.detail || e.message))
    } finally { setSalvando(false) }
  }

  const enviar = () => salvar(async () => {
    try {
      await api.enviarAvaliacao(avaliacaoId)
      aoFechar()
    } catch (e) {
      aoErro(e.detail && e.detail.faltando
        ? `Ainda falta preencher: ${e.detail.faltando.join(', ')}.`
        : (e.detail || e.message))
      carregar()
    }
  })

  return (
    <div className="rh-conferencia">
      <div className="rh-conferencia-topo">
        <div>
          <h3>{a.colaborador}</h3>
          <span className="explica">
            {[a.cargo, a.posto].filter(Boolean).join(' · ')}
            {a.periodo_inicio && ` · período ${fmt(a.periodo_inicio)} a ${fmt(a.periodo_fim)}`}
          </span>
          <div style={{ marginTop: '.35rem' }}>
            <span className="chip">{ROTULO_OCASIAO[a.ocasiao] || a.ocasiao}</span>{' '}
            <span className="chip">{a.relacao === 'vertical' ? 'Vertical' : a.relacao === 'horizontal' ? 'Horizontal' : 'Autoavaliação'}</span>{' '}
            {a.media != null && <span className="chip" style={{ '--chip-cor': '#0a8f46' }}>
              média {a.media.toFixed(2)}</span>}
          </div>
        </div>
        <button className="btn-secundario btn-mini" onClick={aoFechar}>✕ fechar</button>
      </div>

      {homologando && desvio && desvio.tendencia !== 'alinhado' && (
        <div className="aviso-inline">
          <strong>Sobre este avaliador:</strong> ele dá em média{' '}
          <strong>{desvio.media_avaliador.toFixed(2)}</strong>, enquanto os demais dão{' '}
          <strong>{desvio.media_geral.toFixed(2)}</strong> — tende a ser{' '}
          <strong>{desvio.tendencia}</strong> ({desvio.avaliacoes} avaliação(ões)).
          <div className="explica" style={{ margin: '.3rem 0 0' }}>
            Isso é informação para a sua decisão. Nenhuma nota foi alterada.
          </div>
        </div>
      )}

      <div className="rh-conferencia-corpo">
        <div>
          <span className="rh-conferencia-bloco-titulo">Fatos do período</span>
          {(!a.fatos || a.fatos.length === 0) && (
            <p className="explica">Nenhum fato registrado neste período. Registre-os
              em <strong>Fatos Observados</strong> ao longo do trimestre — na próxima
              avaliação eles aparecem aqui.</p>
          )}
          {(a.fatos || []).map((f) => (
            <div className="portal-registro" key={f.id}>
              <div className="portal-registro-topo">
                <strong>{fmt(f.ocorrido_em)}</strong>
                <span className="chip" style={{ '--chip-cor':
                  f.tipo === 'positivo' ? '#0a8f46' : f.tipo === 'negativo' ? '#e5484d' : '#889' }}>
                  {f.tipo === 'positivo' ? 'Positivo' : f.tipo === 'negativo' ? 'Negativo' : 'Registro'}</span>
              </div>
              <div style={{ marginTop: '.25rem' }}>{f.descricao}</div>
              {f.impacto && <div className="explica" style={{ margin: 0 }}>
                Impacto: {f.impacto}</div>}
            </div>
          ))}
        </div>

        <div>
          <span className="rh-conferencia-bloco-titulo">2 — Indicadores objetivos</span>
          <TabelaEscala itens={form.indicadores} escala={form.escala_indicador}
                        valores={campos.indicadores} editavel={editavel}
                        aoMarcar={(k, v) => marcar('indicadores', k, v)} />

          <span className="rh-conferencia-bloco-titulo" style={{ marginTop: '1rem' }}>
            3 — Matriz de competências</span>
          <p className="explica" style={{ margin: '0 0 .4rem' }}>
            As de <strong>Gestão</strong> valem só para cargos de liderança; nos
            demais, marque N/A.</p>
          <TabelaEscala itens={form.competencias} escala={form.escala_competencia}
                        valores={campos.competencias} editavel={editavel}
                        aoMarcar={(k, v) => marcar('competencias', k, v)} />
        </div>
      </div>

      <label className="campo" style={{ marginTop: '1rem' }}>
        <span className="rotulo">4 — Pontos fortes observados</span>
        <textarea rows={2} value={campos.pontos_fortes} disabled={!editavel}
                  placeholder="O que a pessoa faz bem e deve ser reconhecido."
                  onChange={(e) => mexer('pontos_fortes', e.target.value)} /></label>
      <label className="campo">
        <span className="rotulo">5 — Pontos a desenvolver
          <span className="dica-inline"> — descreva fatos, não rótulos</span></span>
        <textarea rows={2} value={campos.pontos_desenvolver} disabled={!editavel}
                  placeholder="Comportamentos específicos, frequência e impacto."
                  onChange={(e) => mexer('pontos_desenvolver', e.target.value)} /></label>

      <div className="campo">
        <span className="rotulo">6 — Plano de desenvolvimento (PDI)</span>
        {campos.pdi.map((linha, i) => (
          <div className="rh-pdi-linha" key={i}>
            <input placeholder="O que desenvolver" value={linha.o_que || ''} disabled={!editavel}
                   onChange={(e) => mexer('pdi', campos.pdi.map((x, j) =>
                     j === i ? { ...x, o_que: e.target.value } : x))} />
            <input placeholder="Ação combinada" value={linha.acao || ''} disabled={!editavel}
                   onChange={(e) => mexer('pdi', campos.pdi.map((x, j) =>
                     j === i ? { ...x, acao: e.target.value } : x))} />
            <input type="date" title="Prazo" value={linha.prazo || ''} disabled={!editavel}
                   onChange={(e) => mexer('pdi', campos.pdi.map((x, j) =>
                     j === i ? { ...x, prazo: e.target.value } : x))} />
            <input type="date" title="Acompanhar em" value={linha.acompanhar_em || ''}
                   disabled={!editavel}
                   onChange={(e) => mexer('pdi', campos.pdi.map((x, j) =>
                     j === i ? { ...x, acompanhar_em: e.target.value } : x))} />
          </div>
        ))}
        {editavel && (
          <button className="btn-secundario btn-mini" onClick={() =>
            mexer('pdi', [...campos.pdi, { o_que: '', acao: '', prazo: '', acompanhar_em: '' }])}>
            + linha</button>
        )}
      </div>

      <div className="campo">
        <span className="rotulo">7 — Recomendação</span>
        <div className="chips-escolha">
          {form.recomendacoes.map((r) => (
            <button type="button" key={r.valor} disabled={!editavel}
                    className={`chip-escolha ${campos.recomendacao === r.valor ? 'on' : ''}`}
                    onClick={() => mexer('recomendacao', r.valor)}>{r.rotulo}</button>
          ))}
        </div>
        {form.recomendacoes.find((r) => r.valor === campos.recomendacao && r.pede_data) && (
          <label className="campo" style={{ marginTop: '.5rem' }}>
            <span className="rotulo">Até quando</span>
            <input type="date" value={campos.recomendacao_data} disabled={!editavel}
                   onChange={(e) => mexer('recomendacao_data', e.target.value)} /></label>
        )}
        <label className="campo" style={{ marginTop: '.5rem' }}>
          <span className="rotulo">Justificativa
            <span className="dica-inline"> — obrigatória; a cartilha não aceita
              recomendação sem justificativa</span></span>
          <textarea rows={2} value={campos.justificativa} disabled={!editavel}
                    onChange={(e) => mexer('justificativa', e.target.value)} /></label>
      </div>

      {a.status !== 'rascunho' && (
        <div className="campo">
          <span className="rotulo">8 — Feedback e postura</span>
          {a.feedback_em ? (
            <p className="explica" style={{ margin: 0 }}>
              Conversa em <strong>{fmt(a.feedback_em)}</strong> · postura:{' '}
              <strong>{a.postura}</strong>
              {a.postura_observacao && ` — ${a.postura_observacao}`}</p>
          ) : (
            <p className="explica" style={{ margin: 0 }}>
              Ainda não registrado. A conversa presencial é obrigatória antes de
              homologar.</p>
          )}
        </div>
      )}

      {a.manifestacao && (
        <div className="campo">
          <span className="rotulo">9 — Manifestação do colaborador</span>
          <div className="portal-registro" style={{ margin: 0 }}>{a.manifestacao}</div>
        </div>
      )}

      {passo === 'feedback' && (
        <RegistrarFeedback avaliacaoId={avaliacaoId} posturas={form.posturas}
                           aoFechar={() => { setPasso(null); carregar() }}
                           aoErro={aoErro} />
      )}
      {passo === 'homologar' && (
        <Homologar avaliacao={a} aoFechar={() => { setPasso(null); aoFechar() }}
                   aoErro={aoErro} />
      )}

      <div className="rh-conferencia-acoes">
        {editavel && (
          <>
            <button className="btn-secundario btn-mini" disabled={salvando}
                    onClick={() => salvar()}>Salvar rascunho</button>
            <button className="btn-principal btn-mini" disabled={salvando}
                    onClick={enviar}>Concluir preenchimento</button>
          </>
        )}
        {a.status === 'preenchida' && !passo && (
          <button className="btn-principal btn-mini" onClick={() => setPasso('feedback')}>
            💬 Registrar a conversa de feedback</button>
        )}
        {(a.status === 'feedback_dado' || a.status === 'manifestada') && !passo && homologando && (
          <button className="btn-principal btn-mini" onClick={() => setPasso('homologar')}>
            ✔ Homologar</button>
        )}
        {a.status === 'homologada' && (
          <span className="explica" style={{ margin: 0 }}>
            Homologada por {a.homologado_por} em {fmt((a.homologado_em || '').slice(0, 10))}.
          </span>
        )}
      </div>
    </div>
  )
}

function TabelaEscala({ itens, escala, valores, editavel, aoMarcar }) {
  return (
    <div className="rh-escala">
      {itens.map((item) => (
        <div className="rh-escala-linha" key={item.chave}>
          <span className="rh-escala-rotulo">
            {item.nivel === 'Gestão' && <small>Gestão · </small>}{item.rotulo}</span>
          <span className="chips-escolha">
            {escala.map((op) => (
              <button type="button" key={op.valor} disabled={!editavel}
                      title={op.descricao}
                      className={`chip-escolha ${valores[item.chave] === op.valor ? 'on' : ''}`}
                      onClick={() => aoMarcar(item.chave, op.valor)}>{op.rotulo}</button>
            ))}
          </span>
        </div>
      ))}
    </div>
  )
}

function RegistrarFeedback({ avaliacaoId, posturas, aoFechar, aoErro }) {
  const [f, setF] = useState({ feedback_em: hoje(), postura: 'receptivo',
                               postura_observacao: '' })
  const [salvando, setSalvando] = useState(false)
  return (
    <div className="campo" style={{ borderTop: '1px solid var(--borda-suave)',
                                    paddingTop: '.8rem', marginTop: '.8rem' }}>
      <span className="rotulo">Registrar a conversa de feedback</span>
      <p className="explica" style={{ margin: '0 0 .5rem' }}>
        A cartilha manda dar o feedback <strong>presencialmente, em local
        reservado</strong>. Registre aqui depois da conversa — não antes.</p>
      <div className="linha2">
        <label className="campo"><span className="rotulo">Data da conversa</span>
          <input type="date" value={f.feedback_em} max={hoje()}
                 onChange={(e) => setF({ ...f, feedback_em: e.target.value })} /></label>
        <label className="campo"><span className="rotulo">Como a pessoa reagiu</span>
          <select value={f.postura}
                  onChange={(e) => setF({ ...f, postura: e.target.value })}>
            {posturas.map((p) => <option key={p.valor} value={p.valor}>{p.rotulo}</option>)}
          </select></label>
      </div>
      <label className="campo"><span className="rotulo">Observações</span>
        <textarea rows={2} value={f.postura_observacao}
                  onChange={(e) => setF({ ...f, postura_observacao: e.target.value })} /></label>
      <button className="btn-principal btn-mini" disabled={salvando} onClick={async () => {
        setSalvando(true)
        try { await api.registrarFeedback(avaliacaoId, f); aoFechar() }
        catch (e) {
          aoErro(e.detail === 'data_futura' ? 'A conversa não pode ter data futura.'
            : (e.detail || e.message))
        } finally { setSalvando(false) }
      }}>Registrar conversa</button>
    </div>
  )
}

function Homologar({ avaliacao, aoFechar, aoErro }) {
  const [conclusao, setConclusao] = useState('')
  const [forcar, setForcar] = useState(false)
  const [aviso, setAviso] = useState(null)
  const [salvando, setSalvando] = useState(false)
  return (
    <div className="campo" style={{ borderTop: '1px solid var(--borda-suave)',
                                    paddingTop: '.8rem', marginTop: '.8rem' }}>
      <span className="rotulo">10 — Conclusão e observações do aplicador</span>
      <textarea rows={2} value={conclusao}
                onChange={(e) => setConclusao(e.target.value)} />
      {aviso && (
        <div className="aviso-inline">
          {aviso}
          <label style={{ display: 'flex', alignItems: 'center', gap: '.4rem',
                          marginTop: '.5rem' }}>
            <input type="checkbox" checked={forcar}
                   onChange={(e) => setForcar(e.target.checked)} />
            <span>Homologar mesmo assim (fica registrado na auditoria)</span></label>
        </div>
      )}
      <button className="btn-principal btn-mini" disabled={salvando} onClick={async () => {
        setSalvando(true)
        try {
          await api.homologarAvaliacao(avaliacao.id,
                                       { conclusao_aplicador: conclusao, forcar })
          aoFechar()
        } catch (e) {
          if (e.detail && e.detail.erro === 'aguardando_manifestacao') {
            setAviso(`O colaborador tem até ${fmt(e.detail.vence_em)} para registrar `
                     + 'a manifestação dele (seção 9). Esperar é o padrão.')
          } else { aoErro(e.detail || e.message) }
        } finally { setSalvando(false) }
      }}>Homologar</button>
    </div>
  )
}

const ROTULO_OCASIAO = {
  experiencia_30: 'Experiência 30d', experiencia_45: 'Experiência 45d',
  experiencia_60: 'Experiência 60d', experiencia_90: 'Experiência 90d',
  intermitente: 'Intermitente', periodica: 'Periódica',
  feedback_pontual: 'Feedback pontual', outro: 'Outro',
}

function hoje() {
  const d = new Date()
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}

function fmt(iso) {
  if (!iso) return '—'
  const [a, m, d] = iso.split('-')
  return `${d}/${m}/${a}`
}
