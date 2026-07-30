import React from 'react'
import { anotarErro } from './telemetria.js'

// Rede de segurança do render (incidente de produção 2026-07-29).
//
// Até aqui o projeto NÃO tinha nenhum ErrorBoundary: qualquer exceção durante o
// render apagava a aplicação inteira e deixava a página EM BRANCO — sem
// mensagem, sem botão, sem pista. Foi assim que dois candidatos ficaram
// travados no meio do envio de documentos, e o RH não teve o que responder.
//
// Tela branca é o pior desfecho possível para quem está do outro lado: não diz
// se o problema é a internet, o link, o celular ou o sistema. A pessoa
// simplesmente conclui que "não funciona" e desiste. Qualquer coisa escrita na
// tela é melhor do que nada.
//
// A recuperação automática está no `chunkErro` (main.jsx), que trata a causa
// mais provável — bundle antigo depois de um deploy. Este componente é a
// segunda linha: pega TODO o resto e transforma em algo acionável.

export default class ErroFatal extends React.Component {
  constructor(props) {
    super(props)
    this.state = { erro: null }
  }

  static getDerivedStateFromError(erro) {
    return { erro }
  }

  componentDidCatch(erro, info) {
    console.error('[erro fatal de render]', erro, info?.componentStack)
    // Manda para a telemetria (v2.24): sem isto, o erro morre no navegador da
    // pessoa e o RH fica sabendo só quando ela liga reclamando — foi o que
    // aconteceu em 2026-07-29 e custou horas de investigação às cegas.
    anotarErro(erro?.message || String(erro), {
      pilha: (info?.componentStack || '').slice(0, 2000),
      onde: 'ErrorBoundary',
    })
  }

  render() {
    if (!this.state.erro) return this.props.children

    return (
      <div className="cartao" style={{ maxWidth: '32rem', margin: '4vh auto' }}>
        <h2>😕 Algo deu errado ao abrir esta página</h2>
        <p>
          Não foi você: houve uma falha aqui do nosso lado. Seus dados e os
          documentos que você já enviou <strong>estão salvos</strong>.
        </p>
        <p>
          Toque no botão abaixo para recarregar. Se continuar assim, fale com o
          RH da Green House pelo WhatsApp — o mesmo link continua valendo.
        </p>
        <button
          className="btn-principal"
          onClick={() => {
            // Recarrega buscando o HTML novo, e não o que está na memória da
            // aba: se a falha veio de um deploy no meio do caminho, isso
            // resolve sozinho.
            window.location.reload()
          }}
        >
          Recarregar a página
        </button>
      </div>
    )
  }
}
