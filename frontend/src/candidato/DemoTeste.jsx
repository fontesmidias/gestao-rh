// Demonstração animada de COMO SE RESPONDE, mostrada antes de iniciar o teste
// (v2.53, ideia do Bruno: "para que a pessoa entre nos testes sem dúvidas").
//
// Por que existe: a instrução do DISC é a mais difícil de entender lendo —
// "marque na coluna da esquerda a que MAIS tem a ver e, na da direita, a que
// MENOS, uma em cada coluna, nunca a mesma palavra". Isso se entende VENDO. E
// quem está prestes a fazer um teste que pode decidir a contratação dele não
// deveria gastar a atenção descobrindo a mecânica.
//
// Por que CSS/SVG e não GIF (decisão do Bruno em 2026-08-02, com os custos à
// vista): um GIF pesaria centenas de KB no celular de quem já sofre com
// conexão ruim, congelaria a tela do dia em que foi gravado, e não seria
// legível por leitor de tela nem traduzível. Isto são bytes, acompanha o tema
// e usa as MESMAS classes da tela real — se o teste mudar, a demo muda junto.
//
// Acessibilidade: a animação inteira é decorativa (`aria-hidden`), e o texto
// ao lado descreve a mesma coisa em palavras. Respeita
// `prefers-reduced-motion`: sem movimento, mostra o estado final preenchido.

const PALAVRAS_DISC = ['Determinado(a)', 'Comunicativo(a)', 'Paciente', 'Detalhista']

// Uma questão DISC de mentira, com as marcações "andando" sozinhas. Reusa
// `.teste-linha`, `.teste-adjetivo` e `.teste-tag` da tela de verdade.
function DemoDisc() {
  return (
    <div className="demo-teste" aria-hidden="true">
      <div className="teste-instrucao demo-instrucao">
        <span className="teste-tag">Mais a ver</span>
        <span>uma em cada coluna</span>
        <span className="teste-tag">Menos a ver</span>
      </div>
      <div className="teste-opcoes">
        {PALAVRAS_DISC.map((p, i) => (
          <div key={p} className="teste-linha demo-linha">
            {/* `data-demo` liga a animação: a linha 0 recebe o "mais" e a 3 o
                "menos", em tempos diferentes, para a pessoa ver a ordem. */}
            <span className={`demo-radio${i === 0 ? ' demo-marca-mais' : ''}`} />
            <span className="teste-adjetivo">{p}</span>
            <span className={`demo-radio${i === 3 ? ' demo-marca-menos' : ''}`} />
          </div>
        ))}
      </div>
    </div>
  )
}

// Situacional e prova objetiva: uma alternativa só. A demo mostra o clique
// percorrendo as opções e parando na escolhida.
function DemoEscolhaUnica({ opcoes }) {
  return (
    <div className="demo-teste" aria-hidden="true">
      <div className="teste-opcoes">
        {opcoes.map((t, i) => (
          <div key={t} className="teste-linha demo-linha">
            <span className={`demo-radio${i === 1 ? ' demo-marca-unica' : ''}`} />
            <span className="teste-adjetivo">{t}</span>
          </div>
        ))}
      </div>
    </div>
  )
}

// `tipo`: 'disc' | 'situacional' | 'prova'
export default function DemoTeste({ tipo }) {
  if (tipo === 'disc') {
    return (
      <div className="demo-bloco">
        <DemoDisc />
        <p className="explica demo-legenda">
          <strong>Assim:</strong> em cada questão há 4 palavras. Marque à
          <strong> esquerda</strong> a que mais tem a ver com você e à
          <strong> direita</strong> a que menos tem — nunca a mesma palavra nas
          duas colunas. Não existe resposta certa ou errada.
        </p>
      </div>
    )
  }
  const opcoes = tipo === 'prova'
    ? ['Primeira alternativa', 'Segunda alternativa', 'Terceira alternativa']
    : ['Eu resolveria sozinho(a)', 'Eu chamaria o meu líder', 'Eu pediria ajuda ao colega']
  return (
    <div className="demo-bloco">
      <DemoEscolhaUnica opcoes={opcoes} />
      <p className="explica demo-legenda">
        <strong>Assim:</strong> {tipo === 'prova'
          ? 'cada questão tem uma alternativa correta. Marque a que você considera certa.'
          : 'escolha a única alternativa que representa como você realmente agiria. Não existe resposta certa ou errada — responda pensando no seu dia a dia.'}
      </p>
    </div>
  )
}
