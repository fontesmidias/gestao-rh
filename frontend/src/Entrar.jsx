import { useState } from 'react'
import { entrada } from './api.js'
import { fmtCpf, cpfValido } from './fmt.js'
import Espera from './Espera.jsx'

// Portal único de retorno: CPF → 2 perguntas de verificação → sessão.
// A segurança de verdade é o e-mail (fallback); as perguntas só encurtam o caminho.
export default function Entrar() {
  const [cpf, setCpf] = useState('')
  const [desafio, setDesafio] = useState(null) // {desafio, perguntas}
  const [respostas, setRespostas] = useState({})
  const [fase, setFase] = useState('cpf') // cpf | perguntas | email-enviado
  const [carregando, setCarregando] = useState(false)
  const [erro, setErro] = useState(null)

  const numeros = cpf.replace(/\D/g, '')

  const iniciar = async (e) => {
    e.preventDefault()
    setErro(null); setCarregando(true)
    try {
      const r = await entrada.iniciar(numeros)
      setDesafio(r); setRespostas({}); setFase('perguntas')
    } catch (er) {
      setErro(er.status === 429
        ? 'Muitas tentativas. Aguarde 15 minutos e tente de novo — ou use o link do seu e-mail.'
        : er.detail === 'cpf_invalido'
          ? 'Este CPF não existe — confira os números digitados.'
          : 'Não foi possível continuar. Tente novamente.')
    } finally { setCarregando(false) }
  }

  const responder = async (e) => {
    e.preventDefault()
    setErro(null); setCarregando(true)
    try {
      const { link } = await entrada.responder(desafio.desafio, respostas)
      window.location.href = link
    } catch (er) {
      setErro(er.status === 429
        ? 'Muitas tentativas. Aguarde 15 minutos — ou peça o link pelo e-mail abaixo.'
        : er.detail === 'desafio_expirado'
          ? 'O tempo esgotou. Volte e digite o CPF novamente.'
          : 'Não conseguimos confirmar os seus dados. Tente de novo ou peça o link pelo e-mail.')
    } finally { setCarregando(false) }
  }

  const pedirEmail = async () => {
    setErro(null); setCarregando(true)
    try { await entrada.linkEmail(numeros) } catch { /* resposta é sempre a mesma */ }
    setCarregando(false); setFase('email-enviado')
  }

  if (fase === 'email-enviado') return (
    <main className="cartao verificar">
      <h1>📬 Confira seu e-mail</h1>
      <p className="explica centro">Se este CPF tiver uma admissão em andamento, enviamos um
        novo link de acesso para o e-mail cadastrado. Confira também a caixa de spam.</p>
      <button className="btn-link" onClick={() => { setFase('cpf'); setCpf('') }}>← voltar</button>
    </main>
  )

  return (
    <main className="cartao verificar">
      <h1>🌱 Continuar minha admissão</h1>
      {fase === 'cpf' && (
        <form onSubmit={iniciar}>
          <p className="explica">Já começou sua admissão e quer continuar? Digite o seu CPF.
            Vamos fazer duas perguntas rápidas sobre os dados que você mesmo preencheu.</p>
          <label className="campo"><span className="rotulo">CPF</span>
            <input inputMode="numeric" maxLength={14} placeholder="000.000.000-00"
                   value={fmtCpf(cpf)} onChange={(e) => setCpf(e.target.value)} autoFocus /></label>
          {erro && <div className="alerta">{erro}</div>}
          <button className="btn-principal" type="submit"
                  disabled={carregando || !cpfValido(numeros)}>
            {carregando ? 'Um instante…' : 'Continuar'}</button>
          {carregando && <Espera texto="Preparando suas perguntas…" />}
        </form>
      )}
      {fase === 'perguntas' && desafio && (
        <form onSubmit={responder}>
          <p className="explica">Responda para confirmarmos que é você (você tem 10 minutos):</p>
          {desafio.perguntas.map((p) => (
            <label className="campo" key={p.codigo}>
              <span className="rotulo">{p.pergunta}</span>
              <input value={respostas[p.codigo] || ''} autoComplete="off"
                     onChange={(e) => setRespostas({ ...respostas, [p.codigo]: e.target.value })} />
            </label>
          ))}
          {erro && <div className="alerta">{erro}</div>}
          <button className="btn-principal" type="submit"
                  disabled={carregando || desafio.perguntas.some((p) => !respostas[p.codigo])}>
            {carregando ? 'Conferindo…' : 'Confirmar e entrar'}</button>
          {carregando && <Espera texto="Conferindo suas respostas…" />}
          <button className="btn-link" type="button" onClick={pedirEmail} disabled={carregando}>
            Não sei responder — enviar o link para o meu e-mail</button>
          <button className="btn-link" type="button" onClick={() => setFase('cpf')}>← voltar</button>
        </form>
      )}
    </main>
  )
}
