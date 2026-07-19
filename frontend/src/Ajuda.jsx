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
}

export default function Ajuda({ termo, texto }) {
  const dica = texto || GLOSSARIO[termo]
  if (!dica) return null
  return (
    <span className="ajuda-q" tabIndex={0} role="note" aria-label={dica} data-dica={dica}>?</span>
  )
}
