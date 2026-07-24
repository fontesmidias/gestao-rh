import { useState } from 'react'
import { fmtDataBR, isoParaBR, brParaISO } from './fmt.js'

// Campo de data com máscara dd/mm/aaaa CENTRALIZADO. Guarda o valor como ISO
// (aaaa-mm-dd) por baixo — inequívoco e o que o backend prefere — mas a pessoa
// digita e vê no formato BR. Insere as barras conforme digita e VALIDA que a
// data existe (rejeita 31/02, ano absurdo, e o clássico "20122025" incompleto).
//
// Substitui as duas máscaras duplicadas e privadas que existiam (Wizard e
// Portal) e os inputs de data livre SEM máscara (nascimento de criança na
// creche), que deixavam salvar "20122025" cru. Ver fmt.js e
// docs/planejamento/08-sistema-de-design.md.
//
// Props:
//   valor     — ISO (aaaa-mm-dd) ou vazio
//   onChange  — recebe ISO quando a data é válida e completa; null enquanto
//               incompleta/ inválida (o pai sabe que ainda não há data boa)
//   modoTexto — se true, chama onChange com o TEXTO BR mascarado em vez de ISO
//               (para consumidores legados que gravam a string BR direto)
export default function InputData({ valor, onChange, modoTexto = false,
                                    placeholder = 'dd/mm/aaaa', ...resto }) {
  const [texto, setTexto] = useState(modoTexto ? (valor || '') : isoParaBR(valor))
  const [erro, setErro] = useState(null)

  const aoDigitar = (e) => {
    const mascarado = fmtDataBR(e.target.value)
    setTexto(mascarado)
    setErro(null)
    if (modoTexto) { onChange(mascarado); return }
    const iso = brParaISO(mascarado)
    if (mascarado.length === 10 && !iso) {
      setErro('Essa data não existe — confira o dia, o mês e o ano.')
      onChange(null)
      return
    }
    onChange(iso)   // ISO válido, ou null enquanto incompleta
  }

  return (
    <>
      <input inputMode="numeric" placeholder={placeholder} maxLength={10}
             value={texto} onChange={aoDigitar} {...resto} />
      {erro && <div className="alerta" style={{ marginTop: '.35rem', padding: '.5rem .75rem' }}>{erro}</div>}
    </>
  )
}
