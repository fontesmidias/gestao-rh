import { useEffect, useState } from 'react'
import { fmtDataHora } from './fmt.js'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { verificarAssinatura } from './api.js'
import logo from './assets/logo.png'

// Cabeçalho comum das páginas públicas de verificação: logo + volta ao início.
function VerificarTopo() {
  return (
    <Link to="/" className="verificar-marca">
      <img src={logo} alt="Green House" className="logo-img" />
    </Link>
  )
}

// Entrada pública de verificação (rota /verificar, sem código): a pessoa lê o
// QR do documento (que já leva a /verificar/{id}) ou digita o código aqui.
export function VerificarEntrada() {
  const [id, setId] = useState('')
  const navigate = useNavigate()
  const ir = (e) => {
    e.preventDefault()
    const v = id.trim()
    if (v) navigate(`/verificar/${encodeURIComponent(v)}`)
  }
  return (
    <main className="cartao verificar">
      <VerificarTopo />
      <div className="verificar-selo neutro">🔎</div>
      <h1>Verificar documento</h1>
      <p className="explica centro">Todo documento assinado no Portal traz um <strong>QR code</strong> e
        um <strong>código de registro</strong> (no manifesto da última página e na lateral de cada
        página). Aponte a câmera do celular para o QR code — ou digite o código do registro abaixo.</p>
      <form onSubmit={ir} className="verificar-form">
        <input placeholder="Código do registro (ex.: 3fa85f64-5717-…)" value={id}
               onChange={(e) => setId(e.target.value)} aria-label="Código do registro" />
        <button className="btn-principal" type="submit" disabled={!id.trim()}>Verificar</button>
      </form>
      <p className="explica centro" style={{ marginTop: '1rem' }}>
        <Link to="/">← Voltar ao início</Link></p>
    </main>
  )
}

// Página PÚBLICA de verificação de assinatura (destino do QR code do manifesto).
export default function Verificar() {
  const { id } = useParams()
  const [dados, setDados] = useState(null)
  const [erro, setErro] = useState(false)

  useEffect(() => {
    verificarAssinatura(id).then(setDados).catch(() => setErro(true))
  }, [id])

  if (erro) return (
    <main className="cartao verificar">
      <VerificarTopo />
      <div className="verificar-selo invalido">✕</div>
      <h1>Assinatura não encontrada</h1>
      <p className="explica centro">Não existe registro de assinatura com este código.
        Se você chegou aqui por um QR code impresso em um documento, ele pode ter sido
        adulterado — trate a via com desconfiança e confirme com o RH da Green House.</p>
      <p className="explica centro"><Link to="/verificar">← Tentar outro código</Link></p>
    </main>
  )
  if (!dados) return <main className="cartao verificar"><VerificarTopo />
    <p className="centro">Verificando…</p></main>

  if (dados.substituida) return (
    <main className="cartao verificar">
      <VerificarTopo />
      <div className="verificar-selo invalido">↻</div>
      <h1>Assinatura substituída</h1>
      <p className="explica centro">Esta assinatura foi realizada de forma autêntica em{' '}
        {fmtDataHora(dados.assinado_em)}, mas o documento foi
        <strong> atualizado depois disso</strong> e uma nova versão foi (ou será) assinada.
        A via que você tem em mãos <strong>não é a mais recente</strong> — solicite a
        versão atual ao RH da Green House.</p>
      <dl className="verificar-dados">
        <dt>Documento</dt><dd>{dados.documento}</dd>
        <dt>Assinante</dt><dd>{dados.assinante}</dd>
        <dt>CPF</dt><dd>{dados.cpf}</dd>
        <dt>Substituída em</dt><dd>{fmtDataHora(dados.invalidada_em)}</dd>
        <dt>Integridade da via antiga (SHA-256)</dt><dd className="hash">{dados.hash_sha256}</dd>
      </dl>
    </main>
  )

  return (
    <main className="cartao verificar">
      <VerificarTopo />
      <div className="verificar-selo valido">✓</div>
      <h1>Assinatura válida</h1>
      <p className="explica centro">Este registro confirma a autenticidade da assinatura
        eletrônica abaixo, realizada no Portal de Admissão Green House.</p>
      <dl className="verificar-dados">
        <dt>Documento</dt><dd>{dados.documento}</dd>
        <dt>Assinante</dt><dd>{dados.assinante}</dd>
        <dt>CPF</dt><dd>{dados.cpf}</dd>
        <dt>Assinado em</dt><dd>{fmtDataHora(dados.assinado_em)} (horário de Brasília)</dd>
        <dt>Método</dt><dd>{dados.metodo}</dd>
        <dt>Integridade (SHA-256)</dt><dd className="hash">{dados.hash_sha256}</dd>
        <dt>ID do registro</dt><dd className="hash">{dados.id}</dd>
      </dl>
      <p className="explica" style={{ marginTop: '1rem' }}>
        <strong>Como conferir a integridade:</strong> o código SHA-256 acima é a impressão
        digital do documento no momento da assinatura. Se você tem a via em mãos, compare
        este código com o impresso no manifesto (última página): se forem idênticos, o
        conteúdo não foi alterado desde a assinatura.</p>
      <p className="explica">Em respeito à Lei Geral de Proteção de Dados, esta página
        exibe apenas dados mínimos, com nome e CPF parcialmente ocultados.</p>
    </main>
  )
}
