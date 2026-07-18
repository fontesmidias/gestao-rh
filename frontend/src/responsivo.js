// Responsividade do painel: no celular, TODAS as tabelas (.rh-tabela) viram
// cards — cada linha é um card e cada célula mostra o título da sua coluna.
// Para isso, este módulo carimba data-rotulo em cada <td> a partir do <th>
// correspondente, automaticamente (vale para qualquer tabela, atual ou futura).
// O CSS usa td[data-rotulo]::before { content: attr(data-rotulo) }.

export function rotularTabelas(raiz = document) {
  raiz.querySelectorAll('table.rh-tabela').forEach((tb) => {
    const titulos = [...tb.querySelectorAll('thead th')].map((th) => th.textContent.trim())
    tb.querySelectorAll('tbody tr').forEach((tr) => {
      let col = 0
      ;[...tr.children].forEach((td) => {
        const span = td.colSpan || 1
        const titulo = span === 1 ? titulos[col] : ''
        if (titulo) td.setAttribute('data-rotulo', titulo)
        else td.removeAttribute('data-rotulo')
        col += span
      })
    })
  })
}

// Observa o painel e re-rotula quando o conteúdo muda (filtros, paginação,
// linhas expandidas). Debounce curto para não trabalhar a cada tecla.
export function observarTabelas() {
  let agendado = null
  const aplicar = () => {
    agendado = null
    rotularTabelas()
  }
  const obs = new MutationObserver(() => {
    if (!agendado) agendado = requestAnimationFrame(aplicar)
  })
  obs.observe(document.body, { childList: true, subtree: true })
  rotularTabelas()
  return () => { obs.disconnect(); if (agendado) cancelAnimationFrame(agendado) }
}
