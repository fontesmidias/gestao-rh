// Fonte ÚNICA de verdade dos status do candidato: mesma etiqueta, cor e ícone
// em Admissões, Colaboradores e no detalhe. Antes cada tela inventava o seu
// (Admissões dizia "Revisar!", Colaboradores mostrava o status cru "envio
// concluido") e o mesmo candidato parecia estar em situações diferentes.
export const STATUS = {
  convidado:             { label: 'Convidado',            cor: '#8896b3', icone: '✉️' },
  preenchendo:           { label: 'Preenchendo',          cor: '#e9a63a', icone: '✍️' },
  aguardando_assinatura: { label: 'Assinando',            cor: '#e9a63a', icone: '🖋️' },
  docs_pendentes:        { label: 'Enviando documentos',  cor: '#e9a63a', icone: '📎' },
  // Cor de atenção (vermelho) mantém a urgência que "Revisar!" tinha, mas o
  // rótulo é o mesmo em toda tela.
  envio_concluido:       { label: 'Aguardando revisão',   cor: '#d9534f', icone: '📥' },
  em_revisao:            { label: 'Em revisão',           cor: '#5bc0de', icone: '🔎' },
  aprovado:              { label: 'Aprovado',             cor: '#4f9d3a', icone: '✓' },
  reprovado_pendencias:  { label: 'Pendências',           cor: '#d9534f', icone: '⚠️' },
  expurgado:             { label: 'Expurgado',            cor: '#999999', icone: '🗑️' },
}

export function statusInfo(s) {
  return STATUS[s] || { label: (s || '').replace(/_/g, ' '), cor: '#888888', icone: '' }
}

// Opções para os selects de filtro (com "Todos" na frente).
export const STATUS_OPCOES = [
  ['', 'Todos os status'],
  ...Object.entries(STATUS).map(([valor, info]) => [valor, info.label]),
]
