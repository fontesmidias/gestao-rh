import { useEffect, useState } from 'react'
import { candidato as api } from '../api.js'
import { Cartao } from './CandidatoApp.jsx'
import Espera from '../Espera.jsx'

const NOMES = {
  ficha_cadastro: 'Ficha Cadastral do Colaborador',
  ficha_emergencia: 'Ficha de Emergência do Colaborador',
  termo_vt: 'Termo de Opção pelo Vale-Transporte',
}

// fase: revisar → enviando → codigo → assinando → concluido
export default function Assinatura({ token, email, aoConcluir }) {
  const [fichas, setFichas] = useState(null)
  const [fase, setFase] = useState('revisar')
  const [emailAtual, setEmailAtual] = useState(email || '')
  const [editandoEmail, setEditandoEmail] = useState(false)
  const [novoEmail, setNovoEmail] = useState(email || '')
  const [codigo, setCodigo] = useState('')
  const [msg, setMsg] = useState(null)

  const recarregar = () => api.fichas(token).then((r) => {
    setFichas(r.fichas)
    return r.fichas
  })
  useEffect(() => { recarregar() }, [token])

  if (!fichas) return <Cartao><p>Carregando…</p></Cartao>

  const pedirCodigo = async () => {
    setMsg(null)
    setFase('enviando')
    try {
      await api.solicitarCodigoUnico(token)
      setCodigo('')
      setFase('codigo')
      setMsg({ tipo: 'ok', texto: `O código foi enviado para ${emailAtual}. Verifique a sua caixa de entrada e, se necessário, a caixa de spam/lixo eletrônico. O código é válido por 10 minutos.` })
    } catch {
      setFase('revisar')
      setMsg({ tipo: 'erro', texto: 'Não foi possível enviar o código. Verifique sua conexão e tente novamente.' })
    }
  }

  const confirmar = async () => {
    setFase('assinando')
    setMsg(null)
    try {
      await api.assinarTodos(token, codigo)
      await recarregar()
      setFase('concluido')
      setMsg({ tipo: 'ok', texto: 'Documentos assinados com sucesso. Enviamos as vias assinadas para o seu e-mail. Toque em cada documento abaixo para visualizá-lo.' })
    } catch (e) {
      setFase('codigo')
      const textos = {
        codigo_incorreto: 'Código incorreto. Confira o e-mail e digite novamente.',
        codigo_expirado: 'O código expirou (validade de 10 minutos). Solicite um novo código.',
        tentativas_excedidas: 'Número de tentativas excedido. Solicite um novo código.',
      }
      setMsg({ tipo: 'erro', texto: textos[e.detail] || 'Não foi possível concluir a assinatura. Tente novamente.' })
    }
  }

  const todasAssinadas = fichas.every((f) => f.assinado)

  return (
    <Cartao>
      <p className="etapa-num">Parte 2 de 4 — Assinatura</p>
      <h2>✍️ Assinatura dos documentos admissionais</h2>
      <p className="explica">Seus dados foram registrados com sucesso. Agora,
        <strong> esta etapa é obrigatória e deve ser concluída em seguida</strong>: a sua
        admissão somente prossegue após a assinatura dos três documentos abaixo. Depois dela,
        restarão duas partes: <strong>envio dos seus documentos</strong> (fotos) e a
        <strong> conferência pelo RH</strong>.</p>

      <div className="lista-fichas">
        {fichas.map(({ documento, assinado }) => (
          <div className={`ficha-item ${assinado ? 'ok' : ''}`} key={documento}>
            <div>
              <strong>{assinado ? '✅' : '📄'} {NOMES[documento]}</strong>
              <a className="link-ver" href={api.previewUrl(token, documento)}
                 target="_blank" rel="noreferrer">
                {assinado ? 'ver documento assinado' : 'conferir o documento antes de assinar'}
              </a>
            </div>
          </div>
        ))}
      </div>

      {!todasAssinadas && (fase === 'revisar' || fase === 'enviando') && (
        <>
          <div className="aviso-codigo">
            <strong>Como funciona:</strong> confira os documentos acima. Ao tocar em
            <strong> Assinar os documentos</strong>, enviaremos <strong>um único código de
            6 números</strong> para o e-mail:
            {!editandoEmail ? (
              <div className="email-confirma">
                <code>{emailAtual}</code>
                <button className="btn-link" onClick={() => setEditandoEmail(true)}>
                  e-mail incorreto? Corrigir</button>
              </div>
            ) : (
              <div className="email-confirma">
                <input type="email" value={novoEmail}
                       onChange={(e) => setNovoEmail(e.target.value)} />
                <button className="btn-secundario btn-mini" onClick={async () => {
                  const limpo = novoEmail.trim()
                  await api.salvarSecao(token, 'pessoais', { email: limpo })
                  setEmailAtual(limpo)
                  setEditandoEmail(false)
                  setMsg({ tipo: 'ok', texto: `E-mail atualizado para ${limpo}.` })
                }}>Salvar e-mail</button>
              </div>
            )}
            Com esse único código, os três documentos são assinados de uma só vez
            (assinatura eletrônica — Lei nº 14.063/2020).
          </div>
          <button className="btn-principal" disabled={fase === 'enviando'} onClick={pedirCodigo}>
            {fase === 'enviando' ? '📨 Enviando o código para o seu e-mail…' : 'Assinar os documentos'}
          </button>
          {fase === 'enviando' && <Espera texto="Preparando e enviando seu código…" />}
        </>
      )}

      {(fase === 'codigo' || fase === 'assinando') && (
        <div className="aviso-codigo">
          <strong>Digite o código de 6 números recebido por e-mail:</strong>
          <div className="otp" style={{ marginTop: '.6rem' }}>
            <input inputMode="numeric" maxLength={6} placeholder="000000" value={codigo}
                   autoFocus onChange={(e) => setCodigo(e.target.value.replace(/\D/g, ''))} />
            <button className="btn-principal btn-mini"
                    disabled={codigo.length !== 6 || fase === 'assinando'} onClick={confirmar}>
              {fase === 'assinando' ? 'Assinando…' : 'Confirmar assinatura'}
            </button>
            <button className="btn-link" disabled={fase === 'assinando'} onClick={pedirCodigo}>
              Não recebeu? Reenviar código</button>
          </div>
          {fase === 'assinando' && <Espera texto="Assinando os 3 documentos e gerando suas vias…" />}
        </div>
      )}

      {msg && <div className={msg.tipo === 'erro' ? 'alerta' : 'sucesso'}>{msg.texto}</div>}

      {todasAssinadas && (
        <>
          <div className="aviso-codigo" style={{ marginTop: '1rem' }}>
            <strong>Próxima etapa (parte 3 de 4):</strong> enviar fotos ou arquivos dos seus
            documentos pessoais (RG, CPF, comprovantes…). Uma lista mostrará exatamente o que
            é necessário, um por um, com dicas de onde conseguir cada documento.
          </div>
          <button className="btn-principal btn-concluir" onClick={aoConcluir}>
            Continuar para o envio dos documentos →
          </button>
        </>
      )}
    </Cartao>
  )
}
