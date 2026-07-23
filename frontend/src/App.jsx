import { Routes, Route, Link } from 'react-router-dom'
import CandidatoApp from './candidato/CandidatoApp.jsx'
import TestagemApp from './candidato/TestagemApp.jsx'
import ProvaApp from './candidato/ProvaApp.jsx'
import AssinarExterno from './AssinarExterno.jsx'
import RHApp from './rh/RHApp.jsx'
import Verificar, { VerificarEntrada } from './Verificar.jsx'
import Entrar from './Entrar.jsx'
import BancoDeTalentos from './Talentos.jsx'
import CrecheLink from './CrecheLink.jsx'
import Portal from './Portal.jsx'
import logo from './assets/logo.png'
import BotaoTema from './Tema.jsx'

// Portal público: três portas claras para os três públicos do sistema.
const PORTAS = [
  { to: '/entrar', ico: '🧑', titulo: 'Sou Candidato',
    desc: 'Continuar minha admissão. Use o link que você recebeu — ou entre com o seu CPF.' },
  { to: '/rh', ico: '🏢', titulo: 'Sou RH',
    desc: 'Acessar o painel de administração das admissões da Green House.' },
  { to: '/verificar', ico: '🔎', titulo: 'Verificar documento',
    desc: 'Conferir a validade e a autenticidade de um documento assinado no Portal.' },
]

function Home() {
  return (
    <main className="portal">
      <header className="portal-topo">
        <img src={logo} alt="Green House" className="logo-img" />
        <h1>Portal de Admissão</h1>
        <p className="portal-sub">Admissão de colaboradores 100% digital, do convite à assinatura.</p>
      </header>
      <nav className="portal-portas">
        {PORTAS.map((p) => (
          <Link key={p.to} to={p.to} className="porta">
            <span className="porta-ico" aria-hidden="true">{p.ico}</span>
            <span className="porta-texto">
              <span className="porta-titulo">{p.titulo}</span>
              <span className="porta-desc">{p.desc}</span>
            </span>
            <span className="porta-seta" aria-hidden="true">→</span>
          </Link>
        ))}
      </nav>
      <p className="portal-talentos">
        Ainda não é da equipe? <Link to="/banco-de-talentos">Cadastre-se no Banco de Talentos →</Link>
      </p>
      <p className="portal-rodape">Assinatura eletrônica conforme a Lei nº 14.063/2020 ·
        dados tratados segundo a LGPD.</p>
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
      <Route path="/t/:token" element={<TestagemApp />} />
      <Route path="/p/:token" element={<ProvaApp />} />
      <Route path="/assinar/:token" element={<AssinarExterno />} />
      <Route path="/rh/*" element={<RHApp />} />
      <Route path="/verificar" element={<VerificarEntrada />} />
      <Route path="/verificar/:id" element={<Verificar />} />
      <Route path="/banco-de-talentos" element={<BancoDeTalentos />} />
      <Route path="/entrar" element={<Entrar />} />
      <Route path="/creche" element={<CrecheLink />} />
      {/* Portal do colaborador: uma porta só para cursos, certificados e
          pendências da pessoa (v1.83). */}
      <Route path="/meu" element={<Portal />} />
    </Routes>
    </>
  )
}
