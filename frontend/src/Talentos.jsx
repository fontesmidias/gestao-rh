import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { talentos as api } from './api.js'
import logo from './assets/logo.png'

// Formulário PÚBLICO do Banco de Talentos (sem login). Quem se cadastra fica
// disponível para o RH triar e, quando houver vaga, converter em admissão.
export default function BancoDeTalentos() {
  const [cargos, setCargos] = useState([])
  const [form, setForm] = useState({
    nome: '', email: '', telefone: '', cargo_interesse: '', cidade: '',
    escolaridade: '', resumo: '', origem: '', website: '',  // website = honeypot
  })
  const [enviado, setEnviado] = useState(false)
  const [erro, setErro] = useState(null)
  const [enviando, setEnviando] = useState(false)

  useEffect(() => { api.opcoes().then((o) => setCargos(o.cargos || [])).catch(() => {}) }, [])
  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value })

  const enviar = async (e) => {
    e.preventDefault()
    if (!form.nome.trim()) { setErro('Informe o seu nome.'); return }
    setErro(null); setEnviando(true)
    try {
      await api.cadastrar(form)
      setEnviado(true)
    } catch (err) {
      setErro(`Não foi possível enviar (${err.detail || err.message}). Tente de novo.`)
    } finally { setEnviando(false) }
  }

  if (enviado) return (
    <main className="cartao verificar">
      <Link to="/" className="verificar-marca"><img src={logo} alt="Green House" className="logo-img" /></Link>
      <div className="verificar-selo valido">✓</div>
      <h1>Cadastro recebido!</h1>
      <p className="explica centro">Obrigado pelo interesse em fazer parte da Green House.
        Seus dados entraram no nosso Banco de Talentos. Quando surgir uma oportunidade que
        combine com o seu perfil, o RH entra em contato.</p>
      <p className="explica centro"><Link to="/">← Voltar ao início</Link></p>
    </main>
  )

  return (
    <main className="cartao talento-form">
      <Link to="/" className="verificar-marca"><img src={logo} alt="Green House" className="logo-img" /></Link>
      <h1>Banco de Talentos</h1>
      <p className="explica centro">Quer trabalhar na Green House? Deixe seus dados abaixo.
        Assim que surgir uma vaga com o seu perfil, o RH fala com você. Só o nome é obrigatório.</p>
      <form onSubmit={enviar}>
        <label className="campo"><span className="rotulo">Nome completo *</span>
          <input value={form.nome} onChange={set('nome')} autoComplete="name" /></label>
        <div className="linha2">
          <label className="campo"><span className="rotulo">E-mail</span>
            <input type="email" value={form.email} onChange={set('email')} autoComplete="email" /></label>
          <label className="campo"><span className="rotulo">Telefone / WhatsApp</span>
            <input value={form.telefone} onChange={set('telefone')} autoComplete="tel" /></label>
        </div>
        <div className="linha2">
          <label className="campo"><span className="rotulo">Cargo de interesse</span>
            <input list="cargos" value={form.cargo_interesse} onChange={set('cargo_interesse')} />
            <datalist id="cargos">{cargos.map((c) => <option key={c} value={c} />)}</datalist>
          </label>
          <label className="campo"><span className="rotulo">Cidade</span>
            <input value={form.cidade} onChange={set('cidade')} /></label>
        </div>
        <div className="linha2">
          <label className="campo"><span className="rotulo">Escolaridade</span>
            <input value={form.escolaridade} onChange={set('escolaridade')}
                   placeholder="Ex.: Ensino Médio completo" /></label>
          <label className="campo"><span className="rotulo">Como conheceu a Green House?</span>
            <input value={form.origem} onChange={set('origem')}
                   placeholder="Indicação, Instagram, site…" /></label>
        </div>
        <label className="campo"><span className="rotulo">Conte sobre sua experiência</span>
          <textarea rows={5} value={form.resumo} onChange={set('resumo')}
                    placeholder="Onde trabalhou, por quanto tempo, o que sabe fazer…" /></label>
        {/* honeypot: escondido de humanos, bots preenchem */}
        <input className="campo-isca" tabIndex={-1} autoComplete="off" value={form.website}
               onChange={set('website')} aria-hidden="true" />
        {erro && <div className="alerta">{erro}</div>}
        <button className="btn-principal" type="submit" disabled={enviando}>
          {enviando ? 'Enviando…' : 'Entrar para o Banco de Talentos'}</button>
      </form>
      <p className="explica centro" style={{ marginTop: '.8rem' }}>
        Seus dados são tratados conforme a LGPD, apenas para fins de recrutamento.
        <br /><Link to="/">← Voltar ao início</Link></p>
    </main>
  )
}
