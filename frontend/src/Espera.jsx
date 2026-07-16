import { useEffect, useState } from 'react'

// Mensagens de espera com personalidade: elegantes, leves, nunca agressivas.
// COMBINADO COM O BRUNO (2026-07-15): a cada atualização do sistema,
// acrescentar ~10 frases novas a este pool.
export const FRASES = [
  // Conjunto 1 — elegância e leveza
  'Um instante — capricho leva exatamente este tempinho.',
  'Preparando tudo com o cuidado de quem dobra a roupa recém-passada.',
  'Seus documentos estão sendo tratados como convidados de honra.',
  'Alguns segundos aqui poupam algumas semanas de papelada. Bom negócio.',
  'O sistema está caprichando. Perfeição apressada perde o ponto, como café.',
  'Organizando cada detalhe — do jeito que a sua futura empresa gosta.',
  'Quase pronto. O bom é que aqui "quase" dura segundos, não meses.',
  'Transformando burocracia em alguns toques de tela. Um prazer, aliás.',
  'Enquanto isso, respire fundo: o resto do processo é conosco.',
  'Verificando tudo duas vezes — porque confiança se constrói nos detalhes.',
  'A tecnologia trabalhando para você — e sem pedir cafezinho.',
  'Cada segundo aqui é um carimbo a menos na sua vida.',
  'Polindo os últimos detalhes. Brilho não aparece por acaso.',
  'Suas informações viajam em primeira classe, com cinto afivelado.',
  'O futuro do RH é isto: você espera segundos, não semanas.',
  'Um momento de calma — daqueles raros e bons.',
  'Registrando tudo com tinta digital, que não borra nem acaba.',
  'As árvores agradecem cada folha de papel que deixamos de usar.',
  'Fazendo a mágica acontecer — com engenharia e um toque de carinho.',
  'Um bom processo é como um bom anfitrião: cuida de tudo sem alarde.',
  'Seus dados estão em boas mãos. Digitais, mas boas.',
  'Detalhes levam tempo; felizmente, aqui o tempo se mede em segundos.',
  'Conferindo com a atenção de quem revisa um convite de casamento.',
  'A paciência é uma virtude — que aqui quase não chega a ser testada.',
  'Sem filas, sem senhas de papel, sem guichê. Só este instante.',
  'Trabalhando em silêncio, como as melhores equipes fazem.',
  'Ajustando cada peça no lugar — engrenagem boa nem se ouve.',
  'O seu tempo é valioso; estamos usando o mínimo possível dele.',
  'Tudo caminhando: suave como deve ser o primeiro dia de trabalho.',
  'Preparando o terreno para o seu próximo capítulo profissional.',
  // Conjunto 2 (atualização do OCR, 2026-07-15)
  'Lendo com atenção — como quem recebe uma carta escrita à mão.',
  'A elegância está nos detalhes; os detalhes estão quase prontos.',
  'Cada dado no seu lugar, como livros numa boa estante.',
  'Um processo bem feito é discreto: você só percebe o resultado.',
  'Semeando agora, colhendo em instantes. Jardinagem digital.',
  'Seus documentos passam por aqui como hóspedes de um bom hotel.',
  'O silêncio que você ouve é o som de tudo dando certo.',
  'Alinhando os últimos pontos — alfaiataria também é software.',
  'Boas notícias viajam rápido. As suas estão quase chegando.',
  'Enquanto o relógio dá uma volta curta, nós damos várias.',
  // Conjunto 3 (atualização RG/CNH + convite sem e-mail, 2026-07-15)
  'Toda grande jornada tem uma pequena pausa. Esta é a sua.',
  'Conferindo letra por letra — respeito também se demonstra assim.',
  'O melhor atalho ainda é fazer certo da primeira vez. Já já.',
  'Suas informações chegaram bem e estão sendo bem recebidas.',
  'Um bom café passa em quatro minutos; nós somos mais rápidos.',
  'Preparando cada detalhe como quem arruma a casa para visita querida.',
  'A pressa é inimiga da vírgula no lugar certo. Um instante.',
  'Aqui dentro, mil engrenagens giram para você não precisar girar nenhuma.',
  'Cuidando dos seus dados como se fossem nossos — porque é assim que se faz.',
  'O próximo passo já está sendo preparado. Você vai gostar dele.',
  // Conjunto 4 (atualização da câmera guiada, 2026-07-15)
  'Foco, luz e enquadramento: o trio que a gente confere por você.',
  'Uma boa foto vale por mil digitações. Estamos cuidando dela.',
  'Ajustando as lentes do processo — tudo em ótima definição.',
  'Cada clique seu economiza um formulário inteiro. Bela troca.',
  'Revelando a sua foto — sem quarto escuro, sem espera de uma semana.',
  'Enquadramento perfeito é meio caminho; o resto é conosco.',
  'Guardando tudo no lugar certo, como quem organiza um álbum de família.',
  'A luz estava boa, a foto ficou ótima — agora é só um instante.',
  'Processando com a calma de quem sabe exatamente o que faz.',
  'Sorria: a burocracia está ficando para trás, quadro a quadro.',
  // Conjunto 5 (auto-captura + leitores nas etapas, 2026-07-15)
  'Menos digitação, mais vida. É para isso que estamos aqui.',
  'O documento certo, no lugar certo, na hora certa. Quase lá.',
  'Encaixando as peças — este quebra-cabeça a gente monta junto.',
  'Trabalhando nos bastidores para o seu palco ficar impecável.',
  'Cada campo preenchido sozinho é um pequeno presente nosso.',
  'A tecnologia boa é a que ninguém percebe. Um instante e pronto.',
  'Afinando os instrumentos — a orquestra já vai tocar.',
  'Seu endereço, seus dados, seu ritmo. Nós só facilitamos.',
  'Um passo de cada vez — e olha que os passos aqui são rápidos.',
  'Terminando com esmero o que começou com um simples toque.',
  // Conjunto 6 (fase 1 do feedback de campo, 2026-07-15)
  'Ouvimos quem usa — e cada ajuste fino nasce de uma história real.',
  'Você no controle, nós no capricho. Boa divisão de tarefas.',
  'Conferir antes de enviar: elegância é dar tempo ao seu próprio olhar.',
  'Nada aqui se perde: o que sai de cena deixa recibo.',
  'Pequenos detalhes, grandes diferenças — é neles que estamos agora.',
  'O sistema aprende com você mais do que você imagina.',
  'Cada versão fica um pouco mais sua. Esta acabou de ficar.',
  'Quem revisa duas vezes assina tranquilo. Nós revisamos três.',
  'Do Goiás ao Plano Piloto, tudo no mesmo cuidado.',
  'Feito para quem tem mais o que fazer do que preencher formulários.',
  // Conjunto 7 (fase 2: poderes do RH com trilha completa, 2026-07-15)
  'Toda mudança aqui deixa assinatura — a nossa e a sua.',
  'Documentos com histórico são documentos com futuro.',
  'O RH prepara, você assina: cada um no seu papel, tudo no seu lugar.',
  'Nada se perde, tudo se registra. Lavoisier aprovaria o nosso RH.',
  'Chegou pelo WhatsApp? Entra pela porta da frente, com etiqueta e tudo.',
  'A confiança mora nos detalhes que ninguém vê — nós cuidamos deles.',
  'Erros acontecem; o que não acontece aqui é ficarem sem correção.',
  'Uma nova versão, uma nova assinatura — transparência de ponta a ponta.',
  'Seu processo anda mesmo quando algo precisa ser refeito.',
  'Auditoria completa: até as vírgulas sabem quem as trouxe.',
  // Conjunto 8 (fase 3: frente e verso, 2026-07-15)
  'Frente e verso: porque documento também tem dois lados da história.',
  'Juntando as páginas com o capricho de quem encaderna à mão.',
  'Duas fotos, um documento, zero complicação.',
  'O verso do RG guarda segredos — filiação, expedição… nós lemos por você.',
  'Costurando os arquivos num PDF só, com linha invisível.',
  'Cada página no seu lugar, como um álbum bem montado.',
  'Documento completo é documento aprovado de primeira.',
  'Virando a página — literalmente — para você não precisar reenviar depois.',
  'Um clique para a frente, outro para o verso, e o resto é conosco.',
  'Perfeição não é pressa: é a segunda foto tão boa quanto a primeira.',
  // Conjunto 9 (quick wins de UX do RH, 2026-07-15)
  'Um clique basta — nós seguramos os outros quatro para você.',
  'Trabalhando… e avisando que estamos trabalhando. Combinado é combinado.',
  'O menu ficou à esquerda, mas o caminho ficou mais curto.',
  'Sistemas bons respondem; sistemas ótimos respondem que estão respondendo.',
  'Cada segundo de espera aqui vem com legenda.',
  'Navegar sem recarregar: a página fica, só o assunto muda.',
  'A barrinha lá em cima é a gente costurando os dados.',
  'Paciência de um clique só — o resto é por nossa conta.',
  'Interface é como recepção: ninguém pode ficar sem resposta.',
  'De amador, só o carinho excessivo com os detalhes.',
  // Conjunto 10 (visibilidade das fichas + termo LGPD INFRAERO, 2026-07-15)
  'Nenhuma pendência fica no escuro — nem no modo escuro.',
  'O que falta agora tem nome, lista e lembrete. Falta pouco.',
  'Avisar é cuidar: ninguém deveria adivinhar o próximo passo.',
  'Seu kit de documentos se monta sozinho — só falta a sua assinatura.',
  'Consentimento informado: palavra difícil, gesto simples, valor enorme.',
  'A luz do flash é sua; a luz sobre o processo é nossa.',
  'Cobramos com elegância — firmeza e gentileza andam juntas por aqui.',
  'Cada documento sabe a que contrato pertence. Organização é isso.',
  'Do computador do RH ao seu celular, a mesma experiência inteira.',
  'Transparência não é recurso: é o padrão da casa.',
  // Conjunto 11 (timbrado + OCR com IA, 2026-07-15)
  'Papel timbrado digital: elegância que nem precisa de impressora.',
  'Cada documento agora chega vestido a caráter.',
  'Uma IA lê, um humano confere, o sistema registra. Trio de respeito.',
  'Seu RG em papel timbrado — organizado como arquivo de colecionador.',
  'A inteligência é artificial; o cuidado com seus dados é genuíno.',
  'Lendo sua foto com olhos treinados em milhões de documentos.',
  'Do rascunho ao timbrado: seus documentos subiram de categoria.',
  'Tecnologia de ponta com pé no chão — e fallback para tudo.',
  'O cabeçalho é da empresa; a história desses documentos é sua.',
  'Detalhes institucionais nos cantos, seus dados no centro. Como deve ser.',
]

const embaralhada = () => FRASES[Math.floor(Math.random() * FRASES.length)]

export default function Espera({ texto }) {
  const [frase, setFrase] = useState(embaralhada)
  useEffect(() => {
    const t = setInterval(() => setFrase(embaralhada()), 2600)
    return () => clearInterval(t)
  }, [])
  return (
    <div className="espera" role="status" aria-live="polite">
      <span className="espera-pontos"><i /><i /><i /></span>
      <div>
        {texto && <strong className="espera-titulo">{texto}</strong>}
        <span className="espera-frase" key={frase}>{frase}</span>
      </div>
    </div>
  )
}
