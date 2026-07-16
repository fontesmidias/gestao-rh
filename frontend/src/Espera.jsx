import { useEffect, useState } from 'react'

// Mensagens de espera com personalidade: elegantes, leves, nunca agressivas.
// COMBINADO COM O BRUNO (2026-07-15): a cada atualização do sistema,
// acrescentar ~10 frases novas a este pool.
const FRASES = [
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
