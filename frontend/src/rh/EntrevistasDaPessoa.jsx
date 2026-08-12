import { useEffect, useState } from 'react'
import { rh as api } from '../api.js'
import { fmtData } from '../fmt.js'
import PlayerAudio from './PlayerAudio.jsx'
import BotaoBaixar from './BotaoBaixar.jsx'

// Histórico de entrevistas da PESSOA (fase 2, § 8.5).
//
// Atravessa talento↔candidato pelo `escopo_pessoa` do mini-CRM: a entrevista
// feita quando ela ainda era talento aparece aqui depois do `converter()` —
// que é justamente o momento em que ela mais importa (cenário 6). Com FK
// única, sumiria.
//
// Fica ao lado da `MemoriaPessoa` porque responde à mesma pergunta ("o que já
// sabemos desta pessoa?"), só que com estrutura comparável em vez de texto
// livre.

export default function EntrevistasDaPessoa({ talentoId, candidatoId }) {
  const [dados, setDados] = useState(null)
  const [erro, setErro] = useState(null)

  const carregar = () => {
    setErro(null)
    return api.entrevistasDaPessoa({ talentoId, candidatoId })
      .then(setDados)
      .catch((e) => setErro(e.detail || e.message || 'Falha ao carregar.'))
  }

  useEffect(() => {
    if (!talentoId && !candidatoId) return
    carregar()
  }, [talentoId, candidatoId])

  if (!talentoId && !candidatoId) return null
  if (erro) {
    return (
      <div className="rh-card">
        <p className="alerta">Não foi possível carregar as entrevistas: {erro}</p>
        <button className="btn-secundario btn-mini" onClick={carregar}>Tentar de novo</button>
      </div>
    )
  }
  // Carregando reserva o lugar; vazio some (o bloco não se aplica à pessoa).
  // O `.rh-card` acompanha o irmão `EntrevistasDaVaga` e o vizinho direto
  // `TestesVinculados`, que ocupa esta mesma posição no `<details>` do
  // Detalhe: bloco de consulta da pessoa é card, sem exceção (v2.65).
  if (dados === null) return <div className="rh-card"><p>Carregando entrevistas…</p></div>
  if (!dados.itens.length) return null

  return (
    <div className="rh-card">
      <h3>Entrevistas ({dados.total})</h3>
      <div className="dash-scroll">
        <table className="rh-tabela">
          <thead>
            <tr>
              <th>Quando</th>
              <th>Tipo</th>
              <th>Vaga</th>
              <th>Situação</th>
              <th>Nota</th>
              <th>Desfecho</th>
              <th>Entrevistador</th>
              <th>Gravação</th>
            </tr>
          </thead>
          <tbody>
            {dados.itens.map((e) => (
              <tr key={e.id}>
                <td>{fmtData(e.realizada_em || e.marcada_para || e.criada_em)}</td>
                <td>{e.tipo === 'triagem' ? 'Triagem' : 'Entrevista'}</td>
                <td>
                  {e.vaga_titulo || '—'}
                  {e.vaga_titulo && !e.vaga_existe && (
                    <> <span className="chip" title="A vaga foi excluída; o título ficou registrado.">
                      vaga excluída</span></>
                  )}
                </td>
                <td>
                  <span className="chip">{e.status}</span>
                  {e.aguardando_desfecho && (
                    <> <span className="chip" style={{ '--chip-cor': 'var(--ambar)' }}
                             title="A data passou e ninguém registrou o que houve.">
                      ⚠ aguardando desfecho</span></>
                  )}
                </td>
                <td>{e.media == null ? '—' : e.media.toFixed(2)}</td>
                <td title={e.recomendacao_motivo || ''}>
                  {e.tipo === 'triagem'
                    ? (e.triagem_desfecho || '—')
                    : (e.recomendacao ? e.recomendacao.replace(/_/g, ' ') : '—')}
                </td>
                <td>{e.entrevistador}</td>
                {/* Gravação (v2.98.2, pedido do Bruno): a lista da ADMISSÃO e a
                    do COLABORADOR precisam chegar ao áudio e à transcrição —
                    a entrevista atravessa talento↔candidato pelas duas FKs, e
                    o áudio vai junto. Sem isto, o dado existia e a tela não
                    dava caminho para ele. */}
                <td>{!e.gravacao || (!e.gravacao.tem_audio && !e.gravacao.tem_texto)
                  ? '—'
                  : (
                    <div className="gravacao-lista">
                      {e.gravacao.tem_audio && (
                        // `tem_audio` cobre os DOIS caminhos: arquivo único
                        // (`audio_key`) e blocos. Na lista mostra-se o primeiro
                        // trecho; o resto está na ficha da entrevista.
                        <PlayerAudio
                          url={e.gravacao.blocos
                            ? api.urlBlocoEntrevista(e.id, 1)
                            : api.urlAudioEntrevista(e.id)}
                          nome={`entrevista-${e.id}`} />
                      )}
                      {e.gravacao.tem_texto && (
                        <BotaoBaixar url={api.urlTextoEntrevista(e.id)}
                                     nome={`transcricao-${e.id}.txt`}
                                     className="btn-link">⬇ transcrição</BotaoBaixar>
                      )}
                      {['aguardando', 'processando'].includes(e.gravacao.status) && (
                        <span className="chip">transcrevendo…</span>
                      )}
                    </div>
                  )}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
