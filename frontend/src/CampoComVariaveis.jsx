import { useRef, useState } from 'react'
import SelectBusca from './SelectBusca.jsx'

/**
 * Campo de texto que INSERE a variável onde o cursor está (v2.82).
 *
 * Pedido do Bruno (2026-08-07):
 *
 *   "Nos modelos, seja de email, mensagens, doc, mostrar todas as variáveis
 *    disponíveis de cada colaborador, para que de fato possa ser customizado
 *    cada modelo. Ou por exemplo, eu paro o cursor de digitação em determinado
 *    lugar do modelo e tenha como abrir um select com busca com as opções de
 *    variáveis, acho que melhora a ux e ui."
 *
 * Antes, as variáveis eram uma LISTA NO TOPO da tela: a pessoa lia
 * `{{nome_social}}`, voltava ao texto e digitava de memória — com as duas
 * chaves de cada lado. Errar uma chave ou o nome não dá erro em lugar nenhum:
 * o `aplicar_variaveis` só substitui o que casa com o padrão, então
 * `{{nome_socal}}` fica no documento **como está**, e o defeito aparece no PDF
 * que a pessoa assina.
 *
 * Aqui a variável é escolhida de uma lista com busca e entra pronta, na posição
 * do cursor. Não há o que digitar errado.
 *
 * ## Duas decisões que sustentam isso
 *
 * 1. **A posição do cursor é lida do próprio `<textarea>`**
 *    (`selectionStart`), não de um estado do React. Estado se perde quando o
 *    campo perde o foco — que é exatamente o que acontece ao clicar no seletor.
 *    Guardamos a posição no `onBlur`, ANTES de o foco ir embora.
 * 2. **O foco volta para o texto depois de inserir**, com o cursor DEPOIS da
 *    variável. Sem isso a pessoa insere, o cursor some, e ela tem que clicar no
 *    texto de novo para continuar escrevendo — o seletor viraria um atalho que
 *    custa dois cliques a mais.
 *
 * A lista de variáveis continua visível ao lado, com a descrição no `title`:
 * quem já sabe o nome digita direto, quem não sabe escolhe. Um não substitui o
 * outro.
 */
export default function CampoComVariaveis({
  valor, aoMudar, variaveis, rotulo, dica, linhas = 7, placeholder,
  como = 'textarea',        // 'textarea' | 'input' (título aceita variável também)
  desabilitado = false,
}) {
  const ref = useRef(null)
  // Posição do cursor no momento em que o campo perdeu o foco. `null` = nunca
  // teve foco; aí a variável vai para o FIM, que é o palpite menos surpreendente.
  const posicao = useRef(null)
  const [escolhida, setEscolhida] = useState('')

  const guardarPosicao = () => {
    if (ref.current) posicao.current = ref.current.selectionStart
  }

  const inserir = (nome) => {
    if (!nome) return
    const marcador = `{{${nome}}}`
    const texto = valor || ''
    const at = posicao.current == null ? texto.length : posicao.current
    const novo = texto.slice(0, at) + marcador + texto.slice(at)
    aoMudar(novo)
    // Devolve o foco ao texto com o cursor DEPOIS da variável inserida. O
    // `setTimeout` é necessário: o React ainda não repintou o valor novo quando
    // este `onChange` retorna, e mexer na seleção antes disso não tem efeito.
    const fim = at + marcador.length
    posicao.current = fim
    setTimeout(() => {
      if (!ref.current) return
      ref.current.focus()
      ref.current.setSelectionRange(fim, fim)
    }, 0)
    setEscolhida('')      // o seletor volta ao neutro: inserir é ação, não estado
  }

  const lista = Object.entries(variaveis || {})
  const Campo = como === 'input' ? 'input' : 'textarea'

  return (
    <div className="campo">
      <span className="rotulo">{rotulo}
        {dica && <span className="dica-inline"> — {dica}</span>}</span>

      <Campo ref={ref} value={valor || ''} disabled={desabilitado}
             rows={como === 'textarea' ? linhas : undefined}
             placeholder={placeholder}
             onBlur={guardarPosicao}
             onSelect={guardarPosicao}
             onChange={(e) => aoMudar(e.target.value)} />

      {lista.length > 0 && !desabilitado && (
        <div className="campo-variaveis">
          <SelectBusca valor={escolhida} aoEscolher={inserir}
                       placeholder="Buscar variável…"
                       vazioRotulo="＋ Inserir variável"
                       opcoes={lista.map(([nome, desc]) => ({
                         valor: nome, rotulo: `{{${nome}}}`, extra: desc,
                       }))} />
          {/* Os chips continuam: quem já sabe o nome lê e digita, sem abrir
              lista nenhuma. Clicar também insere — é o mesmo caminho do
              seletor, para quem prefere o alvo visível ao campo de busca. */}
          <div className="campo-variaveis-chips">
            {lista.map(([nome, desc]) => (
              <button key={nome} type="button" className="chip chip-link"
                      title={`${desc} — clique para inserir onde está o cursor`}
                      onClick={() => inserir(nome)}>{`{{${nome}}}`}</button>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
