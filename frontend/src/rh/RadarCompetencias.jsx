// Gráfico de radar ("teia de aranha") das 8 competências da cartilha.
//
// SVG puro, sem biblioteca: são 8 pontos numa escala de 1 a 4 — trazer uma
// dependência de gráficos para isso pesaria mais que o próprio recurso.
//
// Não é enfeite de dashboard: é o MATERIAL DA CONVERSA de feedback. O gestor
// abre na frente da pessoa e conversa em cima dele. Por isso os rótulos são as
// competências por extenso, e não códigos.
export default function RadarCompetencias({ radar, tamanho = 320 }) {
  if (!radar || !radar.eixos || radar.eixos.length === 0) return null
  const eixos = radar.eixos
  const n = eixos.length
  const centro = tamanho / 2
  const raio = tamanho / 2 - 58        // espaço para os rótulos
  const MAX = 4                         // escala da cartilha: 1 a 4

  // ângulo do eixo i, começando no topo e girando no sentido horário
  const ponto = (i, valor) => {
    const ang = (Math.PI * 2 * i) / n - Math.PI / 2
    const r = (Math.max(0, Math.min(valor, MAX)) / MAX) * raio
    return [centro + r * Math.cos(ang), centro + r * Math.sin(ang)]
  }

  const linhas = [
    { chave: 'vertical', rotulo: 'Liderança', cor: '#0a8f46' },
    { chave: 'horizontal', rotulo: 'Pares (média)', cor: '#3b82f6' },
    { chave: 'autoavaliacao', rotulo: 'Autoavaliação', cor: '#f5a623' },
  ].filter((l) => eixos.some((e) => e[l.chave] != null))

  const poligono = (chave) => eixos
    .map((e, i) => (e[chave] != null ? ponto(i, e[chave]).join(',') : null))
    .filter(Boolean).join(' ')

  return (
    <div className="radar-bloco">
      <svg viewBox={`0 0 ${tamanho} ${tamanho}`} className="radar-svg"
           role="img" aria-label="Gráfico de competências">
        {/* teia de fundo: um anel por nível da escala */}
        {[1, 2, 3, 4].map((nivel) => (
          <polygon key={nivel} fill="none" stroke="var(--borda)" strokeWidth="1"
                   points={eixos.map((_, i) => ponto(i, nivel).join(',')).join(' ')} />
        ))}
        {/* raios */}
        {eixos.map((_, i) => (
          <line key={i} x1={centro} y1={centro}
                x2={ponto(i, MAX)[0]} y2={ponto(i, MAX)[1]}
                stroke="var(--borda)" strokeWidth="1" />
        ))}
        {/* uma área por relação */}
        {linhas.map((l) => (
          <polygon key={l.chave} points={poligono(l.chave)}
                   fill={l.cor} fillOpacity="0.14" stroke={l.cor} strokeWidth="2" />
        ))}
        {/* rótulos das competências */}
        {eixos.map((e, i) => {
          const [x, y] = ponto(i, MAX + 0.55)
          const ancora = Math.abs(x - centro) < 6 ? 'middle' : (x > centro ? 'start' : 'end')
          return (
            <text key={e.chave} x={x} y={y} textAnchor={ancora}
                  dominantBaseline="middle" className="radar-rotulo">
              {curto(e.rotulo)}
            </text>
          )
        })}
      </svg>

      <div className="radar-legenda">
        {linhas.map((l) => (
          <span key={l.chave}>
            <i style={{ background: l.cor }} />{l.rotulo}
            {l.chave === 'horizontal' && radar.respondentes
              && ` (${radar.respondentes.horizontal})`}
          </span>
        ))}
      </div>

      {radar.horizontal_suprimido && (
        <p className="explica" style={{ margin: '.3rem 0 0' }}>
          A média dos pares só aparece com pelo menos {radar.minimo_horizontal}{' '}
          respostas — com uma só, daria para saber quem avaliou.
        </p>
      )}
    </div>
  )
}

// Rótulos longos quebram o desenho; o tooltip do <title> mostra o nome inteiro.
function curto(rotulo) {
  const mapa = {
    'Liderança integradora': 'Liderança',
    'Excelência em gestão': 'Gestão',
    'Planejamento e organização': 'Planejamento',
    'Trabalho em equipe': 'Equipe',
  }
  return mapa[rotulo] || rotulo
}
