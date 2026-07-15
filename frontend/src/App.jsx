import { Routes, Route, Link } from 'react-router-dom'
import CandidatoApp from './candidato/CandidatoApp.jsx'
import RHApp from './rh/RHApp.jsx'
import Verificar from './Verificar.jsx'

function Home() {
  return (
    <main className="welcome">
      <h1>🌱 Portal de Admissão — Green House</h1>
      <p>Candidato: use o link que você recebeu por e-mail ou WhatsApp.</p>
      <p><Link to="/rh">Acesso do RH →</Link></p>
    </main>
  )
}

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<Home />} />
      <Route path="/c/:token/*" element={<CandidatoApp />} />
      <Route path="/rh/*" element={<RHApp />} />
      <Route path="/verificar/:id" element={<Verificar />} />
    </Routes>
  )
}
