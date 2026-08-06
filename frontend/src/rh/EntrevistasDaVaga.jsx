import { useEffect, useState } from 'react'
import { rh as api } from '../api.js'
import { fmtData } from '../fmt.js'

// Comparação dos entrevistados de UMA vaga (fase 2, § 8.4) — cenários 17 e 18.
//
// É o que responde "por que essa pessoa e não a outra?". Com três entrevistados,
// as anotações soltas diziam "gostei dele", "pareceu boa" e "achei meio devagar";
// aqui as 4 notas ficam lado a lado, com a justificativa no hover e a
// recomendação ao lado.
//
// **Nada de média entre avaliadores** (cenário 8): hoje só o RH entrevista, e
// quando entrar um segundo, a regra do documento é mostrar as DUAS notas — a
// média apaga o desacordo, que é o dado mais informativo.

export default function EntrevistasDaVaga({ vagaId }) {
  const [dados, setDados] = useState(null)
  const [erro, setErro] = useState(null)

  useEffect(() => {
    if (!vagaId) return
    setDados(null)
    setErro(null)
    api.entrevistasDaVaga(vagaId).then(setDados)
      .catch((e) => setErro(e.detail || e.message || 'Falha ao carregar.'))
  }, [vagaId])

  if (!vagaId) return null
  if (erro) {
    return (
      <div className="rh-card">
        <p className="alerta">Não foi possível carregar as entrevistas: {erro}</p>
        <button className="btn-secundario btn-mini"
                onClick={() => api.entrevistasDaVaga(vagaId).then(setDados).catch(
                  (e) => setErro(e.detail || e.message))}>
          Tentar de novo
        </button>
      </div>
    )
  }
  // "Carregando" e "vazio" são estados DIFERENTES: o bloco que some enquanto a
  // API responde faz o conteúdo abaixo pular na cara de quem já estava lendo.
  if (dados === null) {
    return <div className="rh-card"><p>Carregando entrevistas…</p></div>
  }
  if (!dados.itens.length) {
    return (
      <div className="rh-card">
        <h3>Entrevistas desta vaga</h3>
        <p className="explica">Ninguém foi entrevistado para esta vaga ainda.</p>
      </div>
    )
  }

  const comps = dados.competencias || []
  return (
    <div className="rh-card">
      <h3>Entrevistas desta vaga</h3>
      <p className="explica">
        As quatro notas lado a lado — a justificativa de cada uma aparece ao
        passar o mouse. Serve para comparar candidatos e para alocar numa vaga
        com várias posições.
      </p>
      {/* Toda tabela vive dentro de um .dash-scroll: `overflow-x` numa
          <table> NÃO funciona (display:table ignora overflow) e ela empurraria
          a página inteira (regra medida na v2.46). */}
      <div className="dash-scroll">
        <table className="rh-tabela">
          <thead>
            <tr>
              <th>Pessoa</th>
              <th>Tipo</th>
              <th>Quando</th>
              {comps.map((c) => (
                <th key={c.chave} title={c.nome}>{abreviar(c.nome)}</th>
              ))}
              <th>Média</th>
              <th>Recomendação</th>
            </tr>
          </thead>
          <tbody>
            {dados.itens.map((e) => (
              <tr key={e.id}>
                <td>{e.pessoa}</td>
                <td>{e.tipo === 'triagem' ? 'Triagem' : 'Entrevista'}</td>
                <td>{fmtData(e.realizada_em || e.marcada_para || e.criada_em)}</td>
                {comps.map((c) => {
                  const nota = (e.competencias || {})[c.chave]
                  const just = (e.justificativas || {})[c.chave]
                  return (
                    <td key={c.chave} title={just || 'sem justificativa registrada'}>
                      {nota == null ? '—' : nota}
                    </td>
                  )
                })}
                <td>{e.media == null ? '—' : e.media.toFixed(2)}</td>
                <td>
                  {e.tipo === 'triagem'
                    ? (e.triagem_desfecho || '—')
                    : (e.recomendacao
                        ? <span className="chip">{e.recomendacao.replace(/_/g, ' ')}</span>
                        : '—')}
                  {e.recomendacao_motivo && (
                    <> <span className="chip" title={e.recomendacao_motivo}>motivo</span></>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <Reaproveitar vagaId={vagaId} />
    </div>
  )
}

// --------------------------------------------------------------------------
// Tag de reaproveitamento (v2.66, § 14.3) — cenário 30.
// --------------------------------------------------------------------------
// Pedido do Bruno: *"quando excluir uma vaga, a entrevista sobrevive, pois
// posso poder taguear a pessoa, de modo que ela possa ser reaproveitada para
// outro cargo"*. A entrevista já sobrevivia (com `vaga_titulo`), mas isso
// preservava o REGISTRO; o que ele quer é preservar a PESSOA como oportunidade.
//
// Reusa `PessoaTag` do mini-CRM — nenhum campo novo, e as tags já filtram no
// dash de Talentos, então o reaproveitamento funciona sem tela nova.
//
// **PROPOSTA, nunca automática.** O sistema sugere o nome da tag a partir do
// cargo; quem confirma é o RH. Tag aplicada sozinha vira ruído, e aí o RH deixa
// de confiar na tag — que é o oposto do que ela existe para fazer.

function Reaproveitar({ vagaId }) {
  const [prev, setPrev] = useState(null)
  const [tag, setTag] = useState('')
  const [aberto, setAberto] = useState(false)
  const [salvando, setSalvando] = useState(false)
  // Mensagem LOCAL: este bloco fica no fim de uma tabela que pode ser longa —
  // a confirmação nasce perto do botão que a gerou (regra da v1.96/v2.47).
  const [msg, setMsg] = useState(null)

  useEffect(() => {
    if (!aberto || !vagaId) return
    api.entrevistadosDaVaga(vagaId)
      .then((r) => { setPrev(r); setTag(r.tag_sugerida || '') })
      .catch((e) => setMsg({ erro: true, texto: e.detail || e.message }))
  }, [aberto, vagaId])

  const aplicar = async () => {
    setSalvando(true)
    setMsg(null)
    try {
      const r = await api.reaproveitarEntrevistados({
        tag, vaga_titulo: prev?.vaga_titulo,
        pessoas: (prev?.itens || []).map((p) => ({
          talento_id: p.talento_id, candidato_id: p.candidato_id,
        })),
      })
      // O lote presta contas de quem NÃO foi — dizer só "pronto" esconderia
      // quem ficou de fora (regra da casa desde o lote de arquivamento).
      const sobra = (r.ignoradas || []).length
      setMsg({
        texto: `${r.marcadas} pessoa(s) marcada(s) com "${r.tag.nome}".`
          + (sobra ? ` ${sobra} não deram — confira o cadastro delas.` : '')
          + (r.marcadas === 0 && !sobra ? ' (já estavam marcadas)' : ''),
      })
    } catch (e) {
      setMsg({ erro: true, texto: e.detail?.erros?.join(' · ') || e.detail || e.message })
    } finally { setSalvando(false) }
  }

  if (!aberto) {
    return (
      <div className="rh-conferencia-acoes">
        <button className="btn-secundario btn-mini" onClick={() => setAberto(true)}>
          🏷️ Marcar entrevistados para reaproveitamento
        </button>
      </div>
    )
  }
  return (
    <div className="rh-conferencia">
      <div className="rh-conferencia-topo">
        <div>
          <h3>Reaproveitar quem já foi entrevistado</h3>
          <span className="explica">
            Uma tag no mini-CRM guarda estas pessoas como oportunidade para
            outras vagas — e continua valendo depois que esta vaga sumir. As
            tags filtram no Banco de Talentos.
          </span>
        </div>
        <button className="btn-secundario btn-mini" onClick={() => setAberto(false)}>
          ✕ fechar
        </button>
      </div>

      {/* "Carregando" e "vazio" são estados diferentes e não podem cair na
          mesma condição. */}
      {prev === null && !msg && <p>Carregando quem foi entrevistado…</p>}
      {prev !== null && prev.total === 0 && (
        <p className="explica">Ninguém foi entrevistado para esta vaga.</p>
      )}
      {prev !== null && prev.total > 0 && (
        <>
          <p className="explica">
            {prev.total} pessoa(s): {prev.itens.map((p) => p.nome).join(', ')}
          </p>
          <label className="campo">
            <span className="rotulo">Tag
              <span className="dica-inline"> — sugerida a partir do cargo da vaga;
                edite à vontade</span></span>
            <input value={tag} onChange={(e) => setTag(e.target.value)} />
          </label>
        </>
      )}

      {msg && <p className={msg.erro ? 'alerta' : 'sucesso'}>{msg.texto}</p>}

      {prev !== null && prev.total > 0 && (
        <div className="rh-conferencia-acoes">
          <button className="btn-principal btn-mini" onClick={aplicar}
                  disabled={salvando || !tag.trim()}>
            {salvando ? 'Marcando…' : 'Marcar estas pessoas'}
          </button>
        </div>
      )}
    </div>
  )
}

// Cabeçalho curto para a coluna não esticar a tabela; o nome inteiro fica no
// `title` (mesma regra da v2.59 para célula que enumera).
function abreviar(nome) {
  const s = String(nome || '')
  return s.length > 18 ? `${s.slice(0, 17)}…` : s
}
