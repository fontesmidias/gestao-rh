// Datas e horas SEMPRE no fuso de Brasília (decisão do RH, 2026-07-16) —
// independentemente do fuso do aparelho de quem olha.
const TZ = 'America/Sao_Paulo'

export const fmtData = (v) =>
  v ? new Date(v).toLocaleDateString('pt-BR', { timeZone: TZ }) : '—'

export const fmtDataHora = (v) =>
  v ? new Date(v).toLocaleString('pt-BR', { timeZone: TZ }) : '—'

// ---------------------------------------------------------------------------
// CPF e telefone — máscara e validação CENTRALIZADAS (feedback 2026-07-21:
// "os dados têm que estar no padrão com DDD e as devidas máscaras"). Antes
// cada tela reimplementava fmtCpf/cpfValido; agora é daqui. Ver [[fmt-cpf-tel]].
// ---------------------------------------------------------------------------

export const soDigitos = (v) => (v || '').replace(/\D/g, '')

// Máscara de CPF conforme o usuário digita: 000.000.000-00 (trunca em 11).
export const fmtCpf = (v) => {
  const n = soDigitos(v).slice(0, 11)
  return n
    .replace(/(\d{3})(\d)/, '$1.$2')
    .replace(/(\d{3})\.(\d{3})(\d)/, '$1.$2.$3')
    .replace(/(\d{3})\.(\d{3})\.(\d{3})(\d)/, '$1.$2.$3-$4')
}

// Validação com dígitos verificadores (não só o tamanho).
export const cpfValido = (cpf) => {
  const n = soDigitos(cpf)
  if (n.length !== 11 || /^(\d)\1{10}$/.test(n)) return false
  for (const pos of [9, 10]) {
    let soma = 0
    for (let i = 0; i < pos; i++) soma += Number(n[i]) * ((pos + 1) - i)
    if ((soma * 10) % 11 % 10 !== Number(n[pos])) return false
  }
  return true
}

// Máscara de celular/fixo brasileiro com DDD, conforme digita:
// 11 dígitos -> (61) 99999-8888; 10 -> (61) 9999-8888. Trunca em 11.
export const fmtTelefone = (v) => {
  const n = soDigitos(v).slice(0, 11)
  if (n.length <= 2) return n.length ? `(${n}` : ''
  const ddd = n.slice(0, 2)
  const resto = n.slice(2)
  if (resto.length <= 4) return `(${ddd}) ${resto}`
  const corte = resto.length >= 9 ? 5 : 4  // celular (9 díg) x fixo (8 díg)
  return `(${ddd}) ${resto.slice(0, corte)}-${resto.slice(corte)}`
}

// Telefone válido = 10 (fixo) ou 11 (celular) dígitos, com DDD plausível
// (2 dígitos, 1º não-zero) e, no celular, o 3º dígito 9.
export const telefoneValido = (v) => {
  const n = soDigitos(v)
  if (n.length !== 10 && n.length !== 11) return false
  if (n[0] === '0') return false
  if (n.length === 11 && n[2] !== '9') return false
  return true
}
