import { useEffect, useState } from 'react'
import { rh as api } from '../api.js'
import SelectBusca from '../SelectBusca.jsx'
import { fmtDataHora } from '../fmt.js'

// A ficha da entrevista — DUAS naturezas, um componente.
//
// Todo o texto do instrumento (competências, âncoras, escalas, perguntas de
// triagem) vem por prop `form`, carregada de `GET /rh/entrevistas/formulario`.
// **O front não duplica nada**: mudar uma âncora é mexer só em
// `services/entrevistas.py`, e esta tela acompanha sozinha.
//
// Não existe campo de "outras perguntas" DE PROPÓSITO (§ 6): campo de pergunta
// livre é risco jurídico (Lei 9.029/95 veda perguntar sobre situação familiar,
// filhos, gravidez…), roteiro pré-aprovado é defesa da empresa. O `observacao`
// é livre; o ROTEIRO não.

export default function FichaEntrevista({ entrevistaId, form, aoFechar, aoMudar }) {
  const [e, setE] = useState(null)
  const [campos, setCampos] = useState(null)
  const [salvando, setSalvando] = useState(false)
  const [erroCarga, setErroCarga] = useState(null)
  // Mensagem LOCAL: a ficha abre na linha, longe do topo — a confirmação tem
  // que nascer perto do botão que a gerou (regra da v1.96/v2.47).
  const [msg, setMsg] = useState(null)

  const carregar = () => {
    setErroCarga(null)
    return api.entrevista(entrevistaId).then((r) => {
      setE(r)
      setCampos({
        triagem: r.triagem || {},
        triagem_desfecho: r.triagem_desfecho || '',
        competencias: r.competencias || {},
        justificativas: r.justificativas || {},
        variante: r.variante || 'comportamental',
        recomendacao: r.recomendacao || '',
        recomendacao_motivo: r.recomendacao_motivo || '',
        observacao: r.observacao || '',
      })
    }).catch((err) => setErroCarga(err.detail || err.message || 'Falha ao carregar.'))
  }
  useEffect(() => { carregar() }, [entrevistaId])

  if (erroCarga) {
    return (
      <div>
        <p className="alerta">Não foi possível carregar: {erroCarga}</p>
        <button className="btn-principal" onClick={carregar}>Tentar de novo</button>
      </div>
    )
  }
  // Guard ANTES de qualquer uso dos estados nulos.
  if (!e || !campos) return <p>Carregando…</p>

  const eTriagem = e.tipo === 'triagem'
  const encerrada = e.status === 'arquivada'
  const marcar = (grupo, chave, valor) =>
    setCampos({ ...campos, [grupo]: { ...campos[grupo], [chave]: valor } })

  const montarPayload = (concluir) => ({
    ...(eTriagem
      ? { triagem: campos.triagem, triagem_desfecho: campos.triagem_desfecho || null }
      : { competencias: campos.competencias, justificativas: campos.justificativas,
          variante: campos.variante,
          recomendacao: campos.recomendacao || null,
          recomendacao_motivo: campos.recomendacao_motivo || null }),
    observacao: campos.observacao,
    concluir,
  })

  const salvar = async (concluir) => {
    setSalvando(true)
    setMsg(null)
    try {
      await api.salvarEntrevista(entrevistaId, montarPayload(concluir))
      await carregar()
      // `aoMudar` recarrega a LISTA. Dentro do try, mas depois do carregar:
      // se a recarga falhar, não se reporta falha de algo que salvou.
      if (aoMudar) await aoMudar()
      setMsg({ texto: concluir ? 'Entrevista concluída e registrada na memória da pessoa.' : 'Rascunho salvo.' })
    } catch (err) {
      // O backend devolve `detail.erros` NOMEANDO o que falta ("Justifique a
      // nota de 'Trato com público'"). Perder essa lista faria a tela dizer só
      // "não deu" — que é o defeito que o 422 detalhado veio consertar.
      const d = err.detail
      setMsg({ erro: true, texto: d?.erros ? d.erros.join(' · ') : (d?.erro || d || err.message) })
    } finally { setSalvando(false) }
  }

  const desfecho = async (status) => {
    setSalvando(true)
    setMsg(null)
    try {
      await api.desfechoEntrevista(entrevistaId, { status })
      await carregar()
      if (aoMudar) await aoMudar()
    } catch (err) {
      setMsg({ erro: true, texto: err.detail?.erro || err.detail || err.message })
    } finally { setSalvando(false) }
  }

  return (
    <div>
      <div className="rh-conferencia-topo">
        <div>
          <h3>{e.pessoa}</h3>
          <span className="explica">
            {eTriagem ? 'Triagem — checagem de viabilidade' : 'Entrevista — avaliação ancorada'}
            {e.vaga_titulo && ` · vaga: ${e.vaga_titulo}`}
            {e.local && ` · ${e.local}`}
          </span>
          <div>
            <span className="chip">{e.status}</span>{' '}
            {e.marcada_para && <span className="chip">marcada {fmtDataHora(e.marcada_para)}</span>}{' '}
            {e.defasagem_dias > 0 && (
              <span className="chip" style={{ '--chip-cor': 'var(--ambar)' }}
                    title="Memória decai: quanto maior a distância entre a conversa e o preenchimento, mais o relato é reconstrução.">
                preenchida {e.defasagem_dias}d depois
              </span>
            )}
          </div>
        </div>
        <button className="btn-secundario btn-mini" onClick={aoFechar}>✕ fechar</button>
      </div>

      {/* Entrevista que passou da data e ninguém fechou: o sistema PERGUNTA.
          Nunca marca `nao_veio` sozinho — silêncio não é falta. */}
      {e.aguardando_desfecho && (
        <div className="rh-card">
          <p><strong>Esta entrevista está aguardando um desfecho.</strong></p>
          <p className="explica">
            A data marcada já passou e ninguém registrou o que aconteceu. O
            sistema não conclui por você — diga o que houve:
          </p>
          <button className="btn-secundario btn-mini" disabled={salvando}
                  onClick={() => desfecho('nao_veio')}>Não compareceu</button>{' '}
          <button className="btn-secundario btn-mini" disabled={salvando}
                  onClick={() => desfecho('remarcada')}>Remarcada</button>{' '}
          <button className="btn-secundario btn-mini" disabled={salvando}
                  onClick={() => desfecho('cancelada')}>Cancelada</button>
        </div>
      )}

      {eTriagem ? (
        <Triagem form={form} campos={campos} marcar={marcar} setCampos={setCampos}
                 desabilitado={encerrada} />
      ) : (
        <Avaliacao form={form} campos={campos} marcar={marcar} setCampos={setCampos}
                   desabilitado={encerrada} />
      )}

      <div className="campo">
        <label className="rotulo">Observação (livre)</label>
        <textarea rows={2} value={campos.observacao} disabled={encerrada}
                  onChange={(ev) => setCampos({ ...campos, observacao: ev.target.value })} />
      </div>

      {msg && <p className={msg.erro ? 'alerta' : 'sucesso'}>{msg.texto}</p>}

      {!encerrada && (
        <>
          <button className="btn-secundario" onClick={() => salvar(false)} disabled={salvando}>
            {salvando ? 'Salvando…' : 'Salvar rascunho'}
          </button>{' '}
          <button className="btn-principal" onClick={() => salvar(true)} disabled={salvando}>
            Concluir
          </button>
        </>
      )}
    </div>
  )
}

// --------------------------------------------------------------------------
// TRIAGEM — sem nota, sem competência, sem âncora. É outra coisa (§ 4.1).
// --------------------------------------------------------------------------

function Triagem({ form, campos, marcar, setCampos, desabilitado }) {
  const respostas = [
    { valor: 'sim', rotulo: 'Sim' },
    { valor: 'nao', rotulo: 'Não' },
    { valor: 'nao_sei', rotulo: 'Não sei' },
  ]
  return (
    <div className="rh-card">
      <p className="explica">
        Checagem de viabilidade: descobrir em cinco minutos se vale marcar uma
        hora presencial. Sem nota — o que derruba a contratação raramente é
        incapacidade, é escala que não cabe, local inacessível ou salário abaixo
        do esperado.
      </p>
      {form.triagem.perguntas.map((p) => (
        <div className="campo" key={p.chave}>
          <label className="rotulo">{p.pergunta}</label>
          <SelectBusca valor={campos.triagem[p.chave] || ''}
                       aoEscolher={(v) => marcar('triagem', p.chave, v)}
                       desabilitado={desabilitado}
                       opcoes={[{ valor: '', rotulo: '— sem resposta —' }, ...respostas]} />
          {/* Seguro-desemprego é registrado porque EXPLICA falta e desistência
              — nunca para excluir alguém. Dizer isso na tela é o que impede o
              campo de virar critério na prática. */}
          {p.nunca_exclui && (
            <span className="explica">
              Registrado para entender disponibilidade. <strong>Nunca é critério
              de exclusão.</strong>
            </span>
          )}
        </div>
      ))}
      <div className="campo">
        <label className="rotulo">Desfecho</label>
        <SelectBusca valor={campos.triagem_desfecho} desabilitado={desabilitado}
                     aoEscolher={(v) => setCampos({ ...campos, triagem_desfecho: v })}
                     opcoes={[{ valor: '', rotulo: '— escolher —' },
                              ...form.triagem.desfechos.map((d) => ({
                                valor: d.chave, rotulo: d.rotulo }))]} />
      </div>
    </div>
  )
}

// --------------------------------------------------------------------------
// ENTREVISTA — 4 competências ancoradas, justificativa obrigatória.
// --------------------------------------------------------------------------

function Avaliacao({ form, campos, marcar, setCampos, desabilitado }) {
  const exigeMotivo = (form.recomendacoes || [])
    .find((r) => r.chave === campos.recomendacao)?.exige_motivo

  return (
    <>
      <div className="rh-card">
        <div className="campo">
          <label className="rotulo">Variante das perguntas</label>
          <SelectBusca valor={campos.variante} desabilitado={desabilitado}
                       aoEscolher={(v) => setCampos({ ...campos, variante: v })}
                       opcoes={form.variantes.map((v) => ({ valor: v.chave, rotulo: v.rotulo }))} />
          <span className="explica">
            A comportamental exige que a pessoa tenha uma história para contar —
            com quem nunca trabalhou formalmente ela mede currículo, não
            competência. A competência, a escala e as âncoras são as mesmas nas
            duas.
          </span>
        </div>
      </div>

      {form.competencias.map((c) => (
        <div className="rh-card" key={c.chave}>
          <h4>{c.nome}</h4>
          <p className="explica">{c.perguntas[campos.variante] || c.perguntas.comportamental}</p>

          <div className="campo">
            <label className="rotulo">Nota</label>
            <SelectBusca valor={String(campos.competencias[c.chave] ?? '')}
                         desabilitado={desabilitado}
                         aoEscolher={(v) => marcar('competencias', c.chave,
                                                   v === '' ? undefined : Number(v))}
                         opcoes={[{ valor: '', rotulo: '— sem nota —' },
                                  ...form.escala.map((s) => ({
                                    valor: String(s.valor), rotulo: s.rotulo }))]} />
          </div>

          {/* As âncoras num <details>: cursor, marcador e margem vêm do
              styles.css (regra da v2.47.1) — nada de style inline aqui. */}
          <details>
            <summary>ver âncoras</summary>
            <ul>
              {form.escala.map((s) => (
                <li key={s.valor}><strong>{s.valor}</strong> — {c.ancoras[s.valor]}</li>
              ))}
            </ul>
          </details>

          <div className="campo">
            <label className="rotulo">Justificativa (obrigatória)</label>
            <textarea rows={2} disabled={desabilitado}
                      value={campos.justificativas[c.chave] || ''}
                      onChange={(ev) => marcar('justificativas', c.chave, ev.target.value)}
                      placeholder="O que a pessoa disse que sustenta esta nota." />
            <span className="explica">
              Nota sem evidência é ruído — descreva o que foi observado, não o
              adjetivo.
            </span>
          </div>
        </div>
      ))}

      <div className="rh-card">
        <div className="campo">
          <label className="rotulo">Recomendação</label>
          <SelectBusca valor={campos.recomendacao} desabilitado={desabilitado}
                       aoEscolher={(v) => setCampos({ ...campos, recomendacao: v })}
                       opcoes={[{ valor: '', rotulo: '— escolher —' },
                                ...form.recomendacoes.map((r) => ({
                                  valor: r.chave, rotulo: r.rotulo }))]} />
        </div>
        {exigeMotivo && (
          <div className="campo">
            <label className="rotulo">Motivo (obrigatório nesta recomendação)</label>
            <textarea rows={2} disabled={desabilitado}
                      value={campos.recomendacao_motivo}
                      onChange={(ev) => setCampos({ ...campos, recomendacao_motivo: ev.target.value })} />
            <span className="explica">
              "Com ressalva" sem dizer qual ressalva não é recomendação, é
              impressão.
            </span>
          </div>
        )}
      </div>
    </>
  )
}
