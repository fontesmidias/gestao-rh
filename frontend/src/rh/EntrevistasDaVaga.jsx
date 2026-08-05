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
    </div>
  )
}

// Cabeçalho curto para a coluna não esticar a tabela; o nome inteiro fica no
// `title` (mesma regra da v2.59 para célula que enumera).
function abreviar(nome) {
  const s = String(nome || '')
  return s.length > 18 ? `${s.slice(0, 17)}…` : s
}
