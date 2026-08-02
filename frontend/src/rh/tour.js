import { driver } from 'driver.js'
import 'driver.js/dist/driver.css'

// Tour do painel do RH (v2.49). O wizard do candidato tinha tour desde a v1.x;
// o painel — 17 telas em 6 grupos — nunca teve. Quem entra pela primeira vez
// vê um menu grande e nenhuma indicação de por onde começar.
//
// Duas regras que valem para qualquer passo que se acrescente aqui:
//
// 1. **Ancorar em elemento que EXISTE sempre.** `element` que não é encontrado
//    faz o driver.js pular o passo em silêncio — o tour encolhe sem avisar.
//    Por isso os passos usam a sidebar e o cabeçalho, que estão em toda
//    página do painel, e não um card que só aparece com dados.
// 2. **Dizer o que a pessoa GANHA, não o que a tela é.** "Aqui ficam os
//    colaboradores" não ajuda ninguém; "é aqui que você reverte alguém para
//    candidato sem perder a matrícula" ajuda.

const PASSOS = [
  {
    popover: {
      title: '👋 Este é o seu painel',
      description: 'Um tour rápido pelos quatro caminhos que você mais vai usar. '
        + 'Leva menos de um minuto — e você pode revê-lo quando quiser pelo "?" '
        + 'no canto do menu.',
    },
  },
  {
    element: '.rh-sidebar-grupo:first-child',
    popover: {
      title: '📋 Admissão — o caminho principal',
      description: 'Convide o candidato em <strong>Admissões</strong>; ele preenche e '
        + 'assina pelo link. Quando termina, você confere os documentos e efetiva — '
        + 'aí ele passa a aparecer em <strong>Colaboradores</strong>.',
      side: 'right',
    },
  },
  {
    element: '.rh-sidebar-grupo:nth-child(2)',
    popover: {
      title: '📝 Documentos',
      description: '<strong>Modelos</strong> são documentos seus, no papel timbrado, '
        + 'que o sistema preenche com os dados da pessoa. <strong>Assinaturas</strong> '
        + 'mostra o que aguarda alguém assinar — inclusive você.',
      side: 'right',
    },
  },
  {
    element: '.rh-sidebar-item',
    popover: {
      title: '🔎 Cada pessoa tem uma ficha',
      description: 'Clique no nome de alguém em qualquer lista para abrir a ficha dela: '
        + 'documentos para conferir em cima, cadastro logo abaixo, e o histórico '
        + 'completo no fim — fechado, para não atrapalhar.',
      side: 'right',
    },
  },
  {
    popover: {
      title: '❓ O "?" explica o vocabulário',
      description: 'Termos como <em>homologar</em>, <em>fato observado</em> ou '
        + '<em>repactuação</em> têm um <strong>?</strong> ao lado. Passe o mouse '
        + '(ou toque, no celular) para ver o que significam — sem sair da tela.',
    },
  },
]

export function criarTour() {
  return driver({
    showProgress: true,
    // Sem isto o driver escreve "2 of 5" — inglês no meio de uma interface
    // inteiramente em pt-BR.
    progressText: '{{current}} de {{total}}',
    nextBtnText: 'Próximo',
    prevBtnText: 'Voltar',
    doneBtnText: 'Entendi!',
    // O tour não deve travar quem já conhece o painel: clicar fora fecha.
    allowClose: true,
    steps: PASSOS,
  })
}

// Dispara UMA vez, na primeira visita. A trava vive em `localStorage` com
// chave própria (`tour_rh_visto`) — o tour do candidato usa `tour_visto`, e
// compartilhar a chave faria um esconder o outro, já que o RH também abre o
// link do candidato para conferir.
export const CHAVE_VISTO = 'tour_rh_visto'

export function jaViu() {
  try {
    return localStorage.getItem(CHAVE_VISTO) === '1'
  } catch {
    return true // navegador sem localStorage: não insistir
  }
}

export function marcarVisto() {
  try {
    localStorage.setItem(CHAVE_VISTO, '1')
  } catch {
    /* modo privado/sem storage: o tour só não será lembrado */
  }
}
