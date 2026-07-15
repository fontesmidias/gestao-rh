import { Routes, Route, Link } from 'react-router-dom'
import CandidatoApp from './candidato/CandidatoApp.jsx'
import RHApp from './rh/RHApp.jsx'
import Verificar from './Verificar.jsx'
import Entrar from './Entrar.jsx'
import logo from './assets/logo.png'
import BotaoTema from './Tema.jsx'

function Home() {
  return (
    <main className="welcome">
      <img src={logo} alt="Green House" className="logo-img" />
      <h1>Portal de Admissão</h1>
      <p>Candidato: use o link que você recebeu por e-mail ou WhatsApp.</p>
      <p><Link to="/entrar">Perdeu o link? Continue com o seu CPF →</Link></p>
      <p><Link to="/rh">Acesso do RH →</Link></p>
    </main>
  )
}

export default function App() {
  return (
    <>
    <BotaoTema />
    <Routes>
      <Route path="/" element={<Home />} />
      <Route path="/c/:token/*" element={<CandidatoApp />} />
      <Route path="/rh/*" element={<RHApp />} />
      <Route path="/verificar/:id" element={<Verificar />} />
      <Route path="/entrar" element={<Entrar />} />
    </Routes>
    </>
  )
}
