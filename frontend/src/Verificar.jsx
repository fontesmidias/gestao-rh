import { useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import { verificarAssinatura } from './api.js'

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
      <div className="verificar-selo invalido">✕</div>
      <h1>Assinatura não encontrada</h1>
      <p className="explica centro">Não existe registro de assinatura com este código.
        Se você chegou aqui por um QR code impresso em um documento, ele pode ter sido
        adulterado — trate a via com desconfiança e confirme com o RH da Green House.</p>
    </main>
  )
  if (!dados) return <main className="cartao verificar"><p className="centro">Verificando…</p></main>

  if (dados.substituida) return (
    <main className="cartao verificar">
      <div className="verificar-selo invalido">↻</div>
      <h1>Assinatura substituída</h1>
      <p className="explica centro">Esta assinatura foi realizada de forma autêntica em{' '}
        {new Date(dados.assinado_em).toLocaleString('pt-BR')}, mas o documento foi
        <strong> atualizado depois disso</strong> e uma nova versão foi (ou será) assinada.
        A via que você tem em mãos <strong>não é a mais recente</strong> — solicite a
        versão atual ao RH da Green House.</p>
      <dl className="verificar-dados">
        <dt>Documento</dt><dd>{dados.documento}</dd>
        <dt>Assinante</dt><dd>{dados.assinante}</dd>
        <dt>CPF</dt><dd>{dados.cpf}</dd>
        <dt>Substituída em</dt><dd>{new Date(dados.invalidada_em).toLocaleString('pt-BR')}</dd>
        <dt>Integridade da via antiga (SHA-256)</dt><dd className="hash">{dados.hash_sha256}</dd>
      </dl>
    </main>
  )

  return (
    <main className="cartao verificar">
      <div className="verificar-selo valido">✓</div>
      <h1>Assinatura válida</h1>
      <p className="explica centro">Este registro confirma a autenticidade da assinatura
        eletrônica abaixo, realizada no Portal de Admissão Green House.</p>
      <dl className="verificar-dados">
        <dt>Documento</dt><dd>{dados.documento}</dd>
        <dt>Assinante</dt><dd>{dados.assinante}</dd>
        <dt>CPF</dt><dd>{dados.cpf}</dd>
        <dt>Assinado em</dt><dd>{new Date(dados.assinado_em).toLocaleString('pt-BR')} (horário de Brasília)</dd>
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
