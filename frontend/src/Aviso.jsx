import { useEffect, useRef, useState } from 'react'

/**
 * Aviso flutuante — a resposta do sistema a uma AÇÃO do usuário (v2.75).
 *
 * Feedback do Bruno, com print da tela de Entrevistas:
 *
 *   "por padrão, qualquer aviso desse deve vir mais discretamente, mas visível,
 *    dar tempo de fazer a leitura, se parar o mouse ele manter ali e também ter
 *    a opção de fechar, caso não queira que ele fique na tela. Esses avisos tem
 *    lugares que ele aparece no topo enquanto estamos lá embaixo na tela, ou
 *    seja nem aparecem"
 *
 * O defeito central é o último: a mensagem era renderizada no TOPO do
 * componente, e quem clicou num botão do meio ou do fim da tela nunca a via. É
 * a mesma lição da v1.96 e da v2.47 ("mensagem vai onde a PESSOA está olhando —
 * o critério é DISTÂNCIA"), que foi corrigida tela a tela e voltava sempre que
 * alguém escrevia uma nova. Corrigir caso a caso não funciona: são 122 usos de
 * `.sucesso`/`.alerta` em 47 arquivos.
 *
 * A solução é tirar a mensagem do fluxo do documento: ela flutua ancorada na
 * JANELA, então está sempre no campo de visão, independente do scroll.
 *
 * As quatro regras que o Bruno pediu, e como cada uma é cumprida:
 *
 * 1. **Discreto mas visível** — canto inferior direito, fora do caminho da
 *    leitura; entra deslizando, com sombra para descolar do fundo.
 * 2. **Tempo de ler** — 6s para sucesso, 10s para erro (erro costuma trazer o
 *    que fazer a seguir, e é mais longo). Uma barra mostra o tempo correndo,
 *    para o sumiço não parecer aleatório.
 * 3. **Parar o mouse mantém** — `onMouseEnter` pausa o relógio; ao sair,
 *    RECOMEÇA a contagem cheia em vez de retomar os últimos milissegundos, que
 *    seria o mesmo que não pausar.
 * 4. **Dá para fechar** — botão ✕, e a tecla Esc.
 *
 * ⚠️ **Não serve para texto explicativo fixo.** Muitos `.alerta` do sistema não
 * são resposta a ação nenhuma: o banco atrasado em Config, os impedimentos da
 * ficha de entrevista, o que falta para exportar ao Tirvu. Esses descrevem um
 * ESTADO da tela e têm que ficar onde estão — flutuar e sumir esconderia a
 * informação que a pessoa precisa consultar enquanto trabalha. A distinção é:
 * respondeu a um clique → `<Aviso>`; explica o que está na tela → `.alerta`
 * inline, como sempre foi.
 *
 * Acessibilidade: `role="status"` + `aria-live="polite"` para sucesso (não
 * interrompe o leitor de tela) e `role="alert"` + `assertive` para erro.
 */

const MS_SUCESSO = 6000
const MS_ERRO = 10000

export default function Aviso({ tipo = 'ok', texto, aoFechar, duracaoMs }) {
  const [saindo, setSaindo] = useState(false)
  const [pausado, setPausado] = useState(false)
  // Muda a cada retomada de hover: reinicia o `useEffect` do relógio E a
  // animação da barra (via `key`), senão a barra ficaria congelada no lugar
  // onde parou enquanto a contagem recomeçou do zero.
  const [ciclo, setCiclo] = useState(0)
  const fechando = useRef(false)

  const erro = tipo === 'erro'
  const ms = duracaoMs || (erro ? MS_ERRO : MS_SUCESSO)

  // Fecha com a animação de saída, sem deixar o `aoFechar` ser chamado duas
  // vezes (clique no ✕ enquanto o relógio já disparou).
  const fechar = () => {
    if (fechando.current) return
    fechando.current = true
    setSaindo(true)
    setTimeout(() => aoFechar && aoFechar(), 180)
  }

  useEffect(() => {
    if (pausado || !texto) return
    const t = setTimeout(fechar, ms)
    return () => clearTimeout(t)
  }, [texto, ms, pausado, ciclo])

  useEffect(() => {
    const onKey = (e) => { if (e.key === 'Escape') fechar() }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])

  if (!texto) return null

  return (
    <div className={`aviso-flutuante${erro ? ' erro' : ''}${saindo ? ' saindo' : ''}`}
         role={erro ? 'alert' : 'status'}
         aria-live={erro ? 'assertive' : 'polite'}
         onMouseEnter={() => setPausado(true)}
         onMouseLeave={() => { setPausado(false); setCiclo((c) => c + 1) }}>
      <div className="aviso-flutuante-texto">{texto}</div>
      <button className="aviso-flutuante-fechar" onClick={fechar}
              aria-label="Fechar aviso" title="Fechar (Esc)">✕</button>
      {/* A barra existe para o sumiço não parecer aleatório: a pessoa VÊ o
          tempo correndo e sabe que pode parar o mouse para segurar. */}
      <span key={ciclo} className="aviso-flutuante-barra"
            style={{ animationDuration: `${ms}ms`,
                     animationPlayState: pausado ? 'paused' : 'running' }} />
    </div>
  )
}
