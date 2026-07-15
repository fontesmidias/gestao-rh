import { useState } from 'react'

// Campo de senha com o "olhinho" (👁 mostrar / ocultar). Aceita as mesmas
// props de um <input> comum — troca só a apresentação.
export default function InputSenha(props) {
  const [visivel, setVisivel] = useState(false)
  return (
    <span className="campo-senha">
      <input {...props} type={visivel ? 'text' : 'password'} />
      {/* aria-label sem a palavra 'senha': o texto do botão entra no nome
          acessível do <label> que envolve o campo e confundiria a associação */}
      <button type="button" className="btn-olho" tabIndex={-1}
              title={visivel ? 'Ocultar o que digitei' : 'Mostrar o que digitei'}
              aria-label={visivel ? 'Ocultar o que digitei' : 'Mostrar o que digitei'}
              onClick={() => setVisivel(!visivel)}>
        <span aria-hidden="true">{visivel ? '🙈' : '👁️'}</span>
      </button>
    </span>
  )
}
