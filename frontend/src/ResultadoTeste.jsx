// Blocos de exibição de resultado dos testes (DISC + situacional), usados na
// testagem avulsa: página pública (participante vê o próprio resultado) e
// página do RH (acompanhamento). Os testes da ADMISSÃO continuam com a
// exibição própria no Detalhe do candidato, restrita ao RH.

export const CORES_DISC = { D: '#d9534f', I: '#f0ad4e', S: '#0fb257', C: '#3b7dd8' }

export function ResultadoDisc({ resultado, perfis }) {
  if (!resultado || !resultado.percentuais) return null
  const perfil = perfis?.[resultado.principal]
  return (
    <>
      <div className="disc-grafico">
        {['D', 'I', 'S', 'C'].map((d) => (
          <div key={d} className="disc-coluna">
            <div className="disc-barra-area">
              <div className="disc-barra" style={{
                height: `${Math.max(4, resultado.percentuais[d])}%`,
                background: CORES_DISC[d] }} />
            </div>
            <strong style={{ color: CORES_DISC[d] }}>{d}</strong>
            <small>{resultado.percentuais[d]}%</small>
          </div>
        ))}
      </div>
      {perfil && (
        <div className="disc-perfil">
          <p><strong>Perfil predominante:{' '}
            <span style={{ color: CORES_DISC[resultado.principal] }}>{perfil.nome}</span>
            {resultado.secundaria && <> com traços de{' '}
              <span style={{ color: CORES_DISC[resultado.secundaria] }}>
                {perfis[resultado.secundaria].nome}</span></>}
          </strong></p>
          <p>{perfil.resumo}</p>
          <p><strong>Pontos fortes:</strong> {perfil.fortes}</p>
          <p><strong>Pontos de atenção:</strong> {perfil.atencao}</p>
          <p><strong>Ambiente em que rende mais:</strong> {perfil.ambiente}</p>
        </div>
      )}
    </>
  )
}

export function ResultadoSituacional({ resultado }) {
  if (!resultado || resultado.percentual == null) return null
  return (
    <p style={{ margin: '.4rem 0 0' }}>
      Conduta profissional: <strong>{resultado.percentual}%</strong>{' '}
      (<strong>{resultado.faixa}</strong>) — {resultado.respondidas}/10 respondidas,
      {' '}{resultado.pontos}/{resultado.maximo} pontos.</p>
  )
}
