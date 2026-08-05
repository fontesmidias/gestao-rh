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
//
// COMPOSIÇÃO (v2.65): esta ficha é um formulário longo com escala de nota, e a
// referência canônica desse papel no projeto é o `FormularioAvaliacao.jsx` (o
// formulário da cartilha). Ela reusa as MESMAS primitivas: um `.rh-conferencia`
// só (não N cards empilhados), `.rh-conferencia-corpo` para as duas colunas,
// `.chips-escolha`/`.chip-escolha` para a escala — todas as opções à vista, um
// clique — e `.rh-conferencia-acoes` para os botões. A v2.64 passou no
// `test_design_system.py` e mesmo assim não parecia com o resto do sistema: o
// teste cobre VOCABULÁRIO (classe existe? token existe?), não COMPOSIÇÃO (qual
// primitiva serve a qual papel).

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
      <div className="rh-conferencia">
        <p className="alerta">Não foi possível carregar: {erroCarga}</p>
        <button className="btn-principal btn-mini" onClick={carregar}>Tentar de novo</button>
      </div>
    )
  }
  // Guard ANTES de qualquer uso dos estados nulos.
  if (!e || !campos) return <div className="rh-conferencia"><p>Carregando…</p></div>

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
    <div className="rh-conferencia">
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
        <div className="aviso-inline">
          <strong>Esta entrevista está aguardando um desfecho.</strong>
          <div className="explica" style={{ margin: '.3rem 0 .5rem' }}>
            A data marcada já passou e ninguém registrou o que aconteceu. O
            sistema não conclui por você — diga o que houve:
          </div>
          <div className="chips-escolha">
            <button type="button" className="chip-escolha" disabled={salvando}
                    onClick={() => desfecho('nao_veio')}>Não compareceu</button>
            <button type="button" className="chip-escolha" disabled={salvando}
                    onClick={() => desfecho('remarcada')}>Remarcada</button>
            <button type="button" className="chip-escolha" disabled={salvando}
                    onClick={() => desfecho('cancelada')}>Cancelada</button>
          </div>
        </div>
      )}

      {eTriagem ? (
        <Triagem form={form} campos={campos} marcar={marcar} setCampos={setCampos}
                 desabilitado={encerrada} />
      ) : (
        <Avaliacao form={form} campos={campos} marcar={marcar} setCampos={setCampos}
                   desabilitado={encerrada} />
      )}

      <label className="campo">
        <span className="rotulo">Observação
          <span className="dica-inline"> — livre; o roteiro acima não é</span></span>
        <textarea rows={2} value={campos.observacao} disabled={encerrada}
                  onChange={(ev) => setCampos({ ...campos, observacao: ev.target.value })} />
      </label>

      {msg && <p className={msg.erro ? 'alerta' : 'sucesso'}>{msg.texto}</p>}

      {!encerrada && (
        <div className="rh-conferencia-acoes">
          <button className="btn-secundario btn-mini" onClick={() => salvar(false)}
                  disabled={salvando}>
            {salvando ? 'Salvando…' : 'Salvar rascunho'}
          </button>
          <button className="btn-principal btn-mini" onClick={() => salvar(true)}
                  disabled={salvando}>
            Concluir
          </button>
        </div>
      )}
    </div>
  )
}

// --------------------------------------------------------------------------
// TRIAGEM — sem nota, sem competência, sem âncora. É outra coisa (§ 4.1).
// --------------------------------------------------------------------------

const RESPOSTAS_TRIAGEM = [
  { valor: 'sim', rotulo: 'Sim' },
  { valor: 'nao', rotulo: 'Não' },
  { valor: 'nao_sei', rotulo: 'Não sei' },
]

function Triagem({ form, campos, marcar, setCampos, desabilitado }) {
  return (
    <>
      <p className="explica">
        Checagem de viabilidade: descobrir em cinco minutos se vale marcar uma
        hora presencial. Sem nota — o que derruba a contratação raramente é
        incapacidade, é escala que não cabe, local inacessível ou salário abaixo
        do esperado.
      </p>

      <span className="rh-conferencia-bloco-titulo">Roteiro de triagem</span>
      {/* Cada pergunta é uma linha da escala: enunciado à esquerda, as três
          respostas à direita, todas à vista. Mesma primitiva do formulário da
          cartilha (`TabelaEscala`) — sim/não/não sei é escala curta, não
          motivo para uma lista suspensa por pergunta. */}
      <div className="rh-escala">
        {form.triagem.perguntas.map((p) => (
          <div className="rh-escala-linha" key={p.chave}>
            <span className="rh-escala-rotulo">
              {p.pergunta}
              {/* Seguro-desemprego é registrado porque EXPLICA falta e
                  desistência — nunca para excluir alguém. Dizer isso na tela é
                  o que impede o campo de virar critério na prática. */}
              {p.nunca_exclui && (
                <span className="dica-inline"> — registrado para entender
                  disponibilidade; <strong>nunca é critério de exclusão</strong></span>
              )}
            </span>
            <span className="chips-escolha">
              {RESPOSTAS_TRIAGEM.map((r) => (
                <button type="button" key={r.valor} disabled={desabilitado}
                        className={`chip-escolha ${campos.triagem[p.chave] === r.valor ? 'on' : ''}`}
                        onClick={() => marcar('triagem', p.chave,
                                              campos.triagem[p.chave] === r.valor ? undefined : r.valor)}>
                  {r.rotulo}</button>
              ))}
            </span>
          </div>
        ))}
      </div>

      <div className="campo" style={{ marginTop: '1rem' }}>
        <span className="rotulo">Desfecho</span>
        <div className="chips-escolha">
          {form.triagem.desfechos.map((d) => (
            <button type="button" key={d.chave} disabled={desabilitado}
                    className={`chip-escolha ${campos.triagem_desfecho === d.chave ? 'on' : ''}`}
                    onClick={() => setCampos({ ...campos,
                      triagem_desfecho: campos.triagem_desfecho === d.chave ? '' : d.chave })}>
              {d.rotulo}</button>
          ))}
        </div>
      </div>
    </>
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
      <div className="campo">
        <span className="rotulo">Variante das perguntas</span>
        <div className="chips-escolha">
          {form.variantes.map((v) => (
            <button type="button" key={v.chave} disabled={desabilitado}
                    className={`chip-escolha ${campos.variante === v.chave ? 'on' : ''}`}
                    onClick={() => setCampos({ ...campos, variante: v.chave })}>
              {v.rotulo}</button>
          ))}
        </div>
        <span className="explica">
          A comportamental exige que a pessoa tenha uma história para contar —
          com quem nunca trabalhou formalmente ela mede currículo, não
          competência. A competência, a escala e as âncoras são as mesmas nas
          duas.
        </span>
      </div>

      {/* Duas colunas, como o formulário da cartilha: as competências à
          esquerda, as justificativas à direita — o avaliador vê a nota que deu
          ao lado do que escreveu para sustentá-la, em vez de rolar entre elas. */}
      <div className="rh-conferencia-corpo">
        <div>
          <span className="rh-conferencia-bloco-titulo">Competências</span>
          <div className="rh-escala">
            {form.competencias.map((c) => (
              <div className="rh-escala-linha" key={c.chave}>
                <span className="rh-escala-rotulo">
                  {c.nome}
                  <span className="dica-inline"> — {c.perguntas[campos.variante]
                    || c.perguntas.comportamental}</span>
                </span>
                <span className="chips-escolha">
                  {form.escala.map((s) => (
                    <button type="button" key={s.valor} disabled={desabilitado}
                            title={c.ancoras[s.valor]}
                            className={`chip-escolha ${campos.competencias[c.chave] === s.valor ? 'on' : ''}`}
                            onClick={() => marcar('competencias', c.chave,
                                                  campos.competencias[c.chave] === s.valor
                                                    ? undefined : s.valor)}>
                      {s.rotulo}</button>
                  ))}
                </span>
              </div>
            ))}
          </div>
          {/* As âncoras num <details>: cursor, marcador e margem vêm do
              styles.css (regra da v2.47.1) — nada de style inline aqui. */}
          <details>
            <summary>ver âncoras das notas</summary>
            {form.competencias.map((c) => (
              <div className="campo" key={c.chave}>
                <span className="rotulo">{c.nome}</span>
                <ul>
                  {form.escala.map((s) => (
                    <li key={s.valor}><strong>{s.valor}</strong> — {c.ancoras[s.valor]}</li>
                  ))}
                </ul>
              </div>
            ))}
          </details>
        </div>

        <div>
          <span className="rh-conferencia-bloco-titulo">Justificativas (obrigatórias)</span>
          <p className="explica" style={{ margin: '0 0 .4rem' }}>
            Nota sem evidência é ruído — descreva o que foi observado, não o
            adjetivo.
          </p>
          {form.competencias.map((c) => (
            <label className="campo" key={c.chave}>
              <span className="rotulo">{c.nome}
                {campos.competencias[c.chave] != null && (
                  <span className="dica-inline"> — nota {campos.competencias[c.chave]}</span>
                )}</span>
              <textarea rows={2} disabled={desabilitado}
                        value={campos.justificativas[c.chave] || ''}
                        onChange={(ev) => marcar('justificativas', c.chave, ev.target.value)}
                        placeholder="O que a pessoa disse que sustenta esta nota." />
            </label>
          ))}
        </div>
      </div>

      <div className="campo">
        <span className="rotulo">Recomendação</span>
        <div className="chips-escolha">
          {form.recomendacoes.map((r) => (
            <button type="button" key={r.chave} disabled={desabilitado}
                    className={`chip-escolha ${campos.recomendacao === r.chave ? 'on' : ''}`}
                    onClick={() => setCampos({ ...campos,
                      recomendacao: campos.recomendacao === r.chave ? '' : r.chave })}>
              {r.rotulo}</button>
          ))}
        </div>
        {exigeMotivo && (
          <label className="campo" style={{ marginTop: '.5rem' }}>
            <span className="rotulo">Motivo
              <span className="dica-inline"> — obrigatório nesta recomendação: "com
                ressalva" sem dizer qual ressalva não é recomendação, é
                impressão</span></span>
            <textarea rows={2} disabled={desabilitado}
                      value={campos.recomendacao_motivo}
                      onChange={(ev) => setCampos({ ...campos, recomendacao_motivo: ev.target.value })} />
          </label>
        )}
      </div>
    </>
  )
}
