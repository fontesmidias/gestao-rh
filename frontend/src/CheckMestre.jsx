import { useEffect, useRef } from 'react'

// Checkbox-mestre de cabeçalho: marca/desmarca todos e exibe o estado "parcial"
// (indeterminate) quando só alguns estão selecionados. O React não expõe
// `indeterminate` de forma declarativa, então aplicamos via ref.
export default function CheckMestre({ marcado, parcial, onChange, title }) {
  const ref = useRef(null)
  useEffect(() => { if (ref.current) ref.current.indeterminate = !!parcial }, [parcial])
  return (
    <input ref={ref} type="checkbox" style={{ width: 'auto', minHeight: 0 }}
           checked={marcado} onChange={onChange} title={title} />
  )
}
