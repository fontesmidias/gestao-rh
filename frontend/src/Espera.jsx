import { useEffect, useState } from 'react'

// Mensagens de espera com humor ácido (mas nunca ofensivo): o sistema está
// trabalhando e faz questão de avisar — chega de bolinha girando muda.
const FRASES = [
  'Calma. Diferente de certas promessas, esta barra anda.',
  'Trabalhando. De verdade — não é reunião que podia ser e-mail.',
  'Convencendo os bits a colaborar. Alguns negociam pesado.',
  'Seus documentos estão passando na frente da fila do cartório. Inveja, cartório?',
  'Isso levaria 3 semanas em papel. Aguenta 3 segundos?',
  'Carregando… mais rápido que resposta de "vi sua mensagem, já te retorno".',
  'O servidor está correndo. De crocs, mas está correndo.',
  'Fazendo em segundos o que a burocracia faz em eras geológicas.',
  'Um momento. O hambúrguer da foto nunca chega igual, mas isto aqui chega.',
  'Processando… juro que ninguém foi tomar cafezinho no meio.',
  'Quase lá. "Quase" no sentido literal, não no de obra pública.',
  'Organizando seus dados com mais carinho que gaveta de documentos de casa.',
  'Se fosse fila de banco, você ainda estaria pegando a senha.',
  'Os elétrons estão dando o máximo. Pediram para avisar.',
  'Convertendo café em resultado. Receita clássica, funciona.',
  'Isto não travou. Travar é o que faz aquele aplicativo que você já conhece.',
  'Um instante — verificando tudo duas vezes, porque retrabalho é o verdadeiro vilão.',
  'Enviando… sem precisar de "segue em anexo" nem de "desconsiderar o anterior".',
  'A internet é uma série de tubos. Estamos desentupindo o seu.',
  'Mais rápido que "só 5 minutinhos" de quem está atrasado.',
  'Seus arquivos estão sendo tratados melhor que bagagem de aeroporto.',
  'Digitalizando a papelada para as árvores mandarem um obrigado.',
  'Paciência é uma virtude. Mas relaxa: aqui ela quase não é necessária.',
  'Fazendo mágica. Tá bom: fazendo engenharia, que é mágica com documentação.',
  'Não pisque. Ok, pode piscar, mas vai perder o final.',
  'Carregando com a urgência de quem também odeia esperar.',
  'Se esta espera fosse um protocolo físico, teria carimbo, grampo e três vias.',
  'O sistema está pensando. Diferente de formulário de papel, que nunca pensou.',
  'Sua conexão e nosso servidor estão tendo uma conversa produtiva. Raro, hoje em dia.',
  'Últimos ajustes — capricho não é lentidão, é respeito.',
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
