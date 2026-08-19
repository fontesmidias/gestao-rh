// Tooltip de nomenclatura: um "?" discreto ao lado de termos técnicos do
// painel, com o significado em linguagem simples (feedback de campo do RH:
// não trocar o termo — que tem sentido jurídico/operacional preciso — e sim
// explicá-lo). Funciona por hover no desktop e por toque (focus) no celular.
const GLOSSARIO = {
  dossie: 'Dossiê: arquivo PDF único que reúne toda a documentação do processo, pronto para arquivar ou enviar.',
  efetivar: 'Efetivar: transformar o candidato em colaborador ativo da empresa (encerra a fase de admissão).',
  triagem: 'Triagem: primeira análise dos interessados do Banco de Talentos, antes de convidar para a admissão.',
  elegibilidade: 'Elegibilidade: verificação de quem atende aos requisitos para receber o benefício.',
  levantamento: 'Levantamento: coleta interna de dados dos colaboradores para análise de elegibilidade (IN SEGES/MGI nº 147/2026).',
  repactuacao: 'Repactuação: renegociação do contrato com o tomador para incluir o custo do benefício antes de ativá-lo.',
  // O que se entrega TODO MÊS no reembolso-creche, e por que são dois papéis
  // diferentes: quem cuida da criança pode ser um estabelecimento (PJ, emite
  // nota fiscal) ou uma pessoa física (PF, assina a declaração de quitação) —
  // art. 11, II da IN SEGES/MGI nº 147/2026.
  creche: 'Comprovante mensal: a cada mês é preciso comprovar a despesa de cada criança — NOTA FISCAL quando quem cuida é uma creche/pré-escola (pessoa jurídica), ou DECLARAÇÃO DE QUITAÇÃO assinada quando é um cuidador pessoa física. O requerimento e a certidão são entregues uma vez só; este se repete.',
  intermitente: 'Intermitente: contrato de trabalho sem jornada fixa — o colaborador é convocado conforme a demanda (art. 452-A da CLT).',
  kit: 'Kit documental: conjunto de documentos que compõem o dossiê daquele posto (comuns + específicos do tomador).',
  slot: 'Slot: espaço reservado para um documento específico que o candidato precisa enviar.',
  timbrado: 'Papel timbrado: papel oficial da empresa, com logotipo no topo e rodapé institucional.',
  tomador: 'Tomador: o cliente/órgão onde o colaborador presta serviço (quem "toma" o serviço terceirizado).',
  posto: 'Posto de serviço: o local/contrato onde o colaborador trabalha (ex.: um órgão ou prédio atendido).',
  disc: 'DISC: inventário comportamental que indica tendências de comportamento (Dominância, Influência, Estabilidade e Conformidade). Apoio à gestão — nunca critério único.',
  situacional: 'Teste situacional: apresenta situações reais de trabalho e avalia a qualidade das reações escolhidas.',
  dois_fatores: 'Confirmação em duas etapas: além do link, a pessoa confirma um código recebido no e-mail, provando que é ela mesma.',
  lgpd: 'LGPD: Lei Geral de Proteção de Dados (Lei nº 13.709/2018) — regras para uso e guarda de dados pessoais.',
  // Gestão de Desempenho (Onda C). Os termos vêm da Cartilha do Avaliador — o
  // instrumento oficial do RH —, e saíram sem explicação nenhuma na tela.
  homologar: 'Homologar: o RH confere e encerra a avaliação, tornando-a oficial. Só depois da conversa de feedback e do prazo de manifestação do colaborador.',
  manifestacao: 'Manifestação: o direito do colaborador de registrar a própria opinião sobre a avaliação recebida (seção 9 da cartilha). Tem prazo de 7 dias — passado ele, o RH pode homologar assim mesmo.',
  feedback_dado: 'Feedback dado: marca que a conversa presencial entre líder e colaborador aconteceu. A cartilha exige a conversa — por isso não dá para homologar sem passar por aqui.',
  avaliacao_vertical: 'Vertical: avaliação feita pelo líder direto. É identificada — é ele quem conduz a conversa de feedback.',
  avaliacao_horizontal: 'Horizontal: avaliação feita por colegas do mesmo nível. É sempre anônima e agregada; com menos de 2 respondentes o resultado é suprimido, porque média de um só é o individual com outro nome.',
  calibracao: 'Calibração: compara a média das notas que um avaliador dá com a dos demais avaliadores. Serve para INFORMAR quem homologa ("este líder é mais rigoroso"), nunca para alterar nota.',
  fato_observado: 'Fato observado: registro de algo concreto que aconteceu no trabalho, anotado quando acontece. Existe para a avaliação se apoiar em fatos, não na lembrança do último mês (efeito de recência).',
  pdi: 'PDI: Plano de Desenvolvimento Individual — o que a pessoa vai fazer para evoluir, combinado na conversa de feedback.',
  // Desenvolvimento (Onda B)
  reciclagem: 'Reciclagem: refazer um curso ou certificação que venceu (ou está para vencer), para manter a habilitação válida.',
  documento_critico: 'Documento crítico: certificação cuja validade não pode falhar (brigada, NR, habilitação). Nunca entra em aprovação em lote — precisa de conferência individual.',
}

export default function Ajuda({ termo, texto }) {
  const dica = texto || GLOSSARIO[termo]
  if (!dica) return null
  return (
    <span className="ajuda-q" tabIndex={0} role="note" aria-label={dica} data-dica={dica}>?</span>
  )
}
