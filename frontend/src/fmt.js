// Datas e horas SEMPRE no fuso de Brasília (decisão do RH, 2026-07-16) —
// independentemente do fuso do aparelho de quem olha.
const TZ = 'America/Sao_Paulo'

export const fmtData = (v) =>
  v ? new Date(v).toLocaleDateString('pt-BR', { timeZone: TZ }) : '—'

export const fmtDataHora = (v) =>
  v ? new Date(v).toLocaleString('pt-BR', { timeZone: TZ }) : '—'
