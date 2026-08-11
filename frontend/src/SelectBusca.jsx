import { Children, useEffect, useMemo, useRef, useState } from 'react'

// Select com busca: começa a digitar e a lista filtra.
//
// **É O PADRÃO DA CASA PARA TODA LISTA SUSPENSA** (v2.50, pedido do Bruno):
// filtro ou preenchimento, em qualquer tela. O RH tem 111 cargos, 269 jornadas
// e dezenas de postos — rolar até achar é o que ele mais reclamou. Não escreva
// `<select>` nativo em tela nova.
//
// Aceita DUAS formas, e as duas se comportam igual:
//
//   1. `opcoes={[{ valor, rotulo, extra? }]}`  — a original (`extra` é um texto
//      auxiliar exibido em cinza ao lado, ex.: "104 pessoa(s)").
//
//   2. `<option>` como filhos, igual a um `<select>` nativo — para converter
//      código existente quase sem reescrever:
//
//        <SelectBusca valor={x} aoEscolher={setX}>
//          <option value="">— posto (obrigatório) —</option>
//          {postos.map((p) => <option key={p.id} value={p.id}>{p.nome}</option>)}
//        </SelectBusca>
//
//      A opção de valor vazio vira automaticamente o "— nenhum —" do topo.
//
// **O campo de busca só aparece quando a lista justifica** (`MIN_BUSCA`). Num
// select de 2 opções (Sim/Não, Efetivo/Intermitente) um campo de texto seria um
// passo a mais, não a menos — e no celular a roda nativa do sistema é melhor de
// operar com o polegar. O padrão de USO é único; o que muda é só a densidade.
//
// Os dados são carregados uma vez pelo pai e filtrados EM MEMÓRIA (sem ida ao
// servidor a cada tecla).

const MIN_BUSCA = 7        // a partir de quantas opções o campo de busca aparece
const TETO_RENDER = 50     // a busca refina o resto

// Lê `<option>`/`<optgroup>` dos children e devolve o formato interno.
// Ignora o que não for option (comentário, `false` de um `&&`, etc.).
function lerOptions(children) {
  const out = []
  const visitar = (nos) => {
    Children.forEach(nos, (filho) => {
      if (!filho || typeof filho !== 'object') return
      if (filho.type === 'optgroup') { visitar(filho.props.children); return }
      if (filho.type !== 'option') return
      const p = filho.props || {}
      const rotulo = typeof p.children === 'string'
        ? p.children
        : Children.toArray(p.children).filter((c) => typeof c === 'string').join('')
      out.push({ valor: p.value ?? '', rotulo: (rotulo || '').trim(), extra: p['data-extra'] })
    })
  }
  visitar(children)
  return out
}

// `desabilitado` (v2.64): registro em modo somente-leitura (entrevista
// arquivada, ficha encerrada). O `<select>` nativo tem `disabled` e este
// componente o substituiu em toda a base — sem isso, cada tela precisaria
// esconder o campo à mão, e um `desabilitado` passado por engano seria
// SILENCIOSAMENTE ignorado, deixando editável o que deveria estar travado.
export default function SelectBusca({ opcoes, children, valor, aoEscolher,
                                      placeholder = 'Buscar…', vazioRotulo, style,
                                      titulo, id, desabilitado = false }) {
  const [aberto, setAberto] = useState(false)
  const [busca, setBusca] = useState('')
  const [foco, setFoco] = useState(0)
  // Para CIMA quando não cabe embaixo (v2.92, defeito de campo: na última
  // linha da tabela de usuários a lista abria para baixo e era CORTADA pelo
  // fim do card — a opção ficava ilegível, e é a que decide o acesso da
  // pessoa). O § 5 do sistema de design já mandava: nada estoura a tela.
  const [paraCima, setParaCima] = useState(false)
  const ref = useRef(null)

  // Children viram opções; a opção de valor vazio (`<option value="">`) assume
  // o papel do `vazioRotulo`, que é como o `<select>` nativo se comporta.
  const { lista, rotuloVazio } = useMemo(() => {
    if (opcoes) return { lista: opcoes, rotuloVazio: vazioRotulo }
    const lidas = lerOptions(children)
    const vazia = lidas.find((o) => o.valor === '')
    return {
      lista: lidas.filter((o) => o.valor !== ''),
      rotuloVazio: vazioRotulo ?? vazia?.rotulo,
    }
  }, [opcoes, children, vazioRotulo])

  const selecionado = lista.find((o) => String(o.valor) === String(valor))
  const comBusca = lista.length >= MIN_BUSCA

  // fecha ao clicar fora
  useEffect(() => {
    const fora = (e) => { if (ref.current && !ref.current.contains(e.target)) setAberto(false) }
    document.addEventListener('mousedown', fora)
    return () => document.removeEventListener('mousedown', fora)
  }, [])

  const filtradas = useMemo(() => {
    const q = busca.trim().toLowerCase()
    const base = q ? lista.filter((o) =>
      o.rotulo.toLowerCase().includes(q) || (o.extra || '').toLowerCase().includes(q)) : lista
    return base.slice(0, TETO_RENDER)
  }, [busca, lista])

  const escolher = (v) => { aoEscolher(v); setAberto(false); setBusca('') }

  const aoTeclar = (e) => {
    if (e.key === 'ArrowDown') { e.preventDefault(); setFoco((f) => Math.min(f + 1, filtradas.length - 1)) }
    else if (e.key === 'ArrowUp') { e.preventDefault(); setFoco((f) => Math.max(f - 1, 0)) }
    else if (e.key === 'Enter' && aberto) { e.preventDefault(); const o = filtradas[foco]; if (o) escolher(o.valor) }
    else if (e.key === 'Escape') { e.preventDefault(); setAberto(false) }
  }

  return (
    <div className="select-busca" ref={ref} style={style}>
      <button type="button" className="select-busca-campo" id={id} title={titulo}
              aria-haspopup="listbox" aria-expanded={aberto}
              disabled={desabilitado}
              onClick={(e) => {
                if (desabilitado) return
                // Decide o LADO na hora de abrir, medindo o espaço real abaixo
                // do campo. Fixo para baixo, o painel era cortado pelo fim do
                // card na última linha de uma tabela (v2.92).
                if (!aberto) {
                  const r = e.currentTarget.getBoundingClientRect()
                  const abaixo = window.innerHeight - r.bottom
                  // 260px é o `max-height` da lista no CSS; abrir para cima só
                  // quando embaixo não cabe E em cima cabe mais.
                  setParaCima(abaixo < 300 && r.top > abaixo)
                }
                setAberto(!aberto); setFoco(0)
              }}
              // Sem campo de busca, as setas ainda navegam: o teclado funciona
              // igual nos dois modos.
              onKeyDown={(e) => { if (!comBusca && aberto) aoTeclar(e) }}>
        <span className={selecionado ? '' : 'select-busca-placeholder'}>
          {selecionado ? selecionado.rotulo : (rotuloVazio || placeholder)}</span>
        <span className="select-busca-seta" aria-hidden="true">▾</span>
      </button>
      {aberto && !desabilitado && (
        <div className={`select-busca-painel ${paraCima ? 'para-cima' : ''}`}>
          {comBusca && (
            <input className="select-busca-input" autoFocus value={busca} placeholder={placeholder}
                   aria-label={placeholder}
                   onChange={(e) => { setBusca(e.target.value); setFoco(0) }} onKeyDown={aoTeclar} />
          )}
          <ul className="select-busca-lista" role="listbox">
            {rotuloVazio && (
              <li role="option" aria-selected={!valor}
                  className={`select-busca-item ${!valor ? 'ativo' : ''}`}
                  onMouseDown={() => escolher('')}>{rotuloVazio}</li>
            )}
            {filtradas.map((o, i) => (
              <li key={o.valor} role="option" aria-selected={String(o.valor) === String(valor)}
                  className={`select-busca-item ${i === foco ? 'foco' : ''} ${String(o.valor) === String(valor) ? 'ativo' : ''}`}
                  onMouseEnter={() => setFoco(i)} onMouseDown={() => escolher(o.valor)}>
                {o.rotulo}{o.extra && <small className="select-busca-extra"> · {o.extra}</small>}
              </li>
            ))}
            {filtradas.length === 0 && <li className="select-busca-vazio">Nada encontrado</li>}
          </ul>
        </div>
      )}
    </div>
  )
}
