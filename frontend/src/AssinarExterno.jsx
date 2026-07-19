import { useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import { assinaturaExterna as api } from './api.js'
import logo from './assets/logo.png'

// Página pública do signatário EXTERNO (/assinar/{token}): confere o documento,
// recebe código no e-mail, e assina — espelha o passo de assinatura do
// candidato. O PDF só aparece após confirmar o código (dados protegidos).
export default function AssinarExterno() {
  const { token } = useParams()
  const [info, setInfo] = useState(null)
  const [fase, setFase] = useState('carregando') // carregando|invalido|codigo|conferir|assinado|fim
  const [codigo, setCodigo] = useState('')
  const [erro, setErro] = useState(null)
  const [ocupado, setOcupado] = useState(false)

  const recarregar = () =>
    api.info(token).then((i) => {
      setInfo(i)
      if (i.ja_assinou) setFase('assinado')
      else if (!i.documento_disponivel) setFase('indisponivel')
      else if (!i.na_vez) setFase('aguardando')
      else if (i.otp_validado) setFase('conferir')
      else setFase('codigo')
    }).catch(() => setFase('invalido'))
  useEffect(() => { recarregar() }, [token])

  const caixa = (filhos) => (
    <div className="candidato">
      <header className="topo"><img src={logo} alt="Green House" className="logo-topo" /></header>
      {filhos}
    </div>
  )

  if (fase === 'carregando') return caixa(<p style={{ padding: '1rem', textAlign: 'center' }}>Carregando…</p>)
  if (fase === 'invalido') return caixa(<div className="teste-caixa"><div className="teste-corpo">
    <div className="alerta">Este link de assinatura não existe ou expirou.</div></div></div>)
  if (fase === 'indisponivel') return caixa(<div className="teste-caixa"><div className="teste-corpo">
    <div className="alerta">O documento não está mais disponível para assinatura.</div></div></div>)
  if (fase === 'aguardando') return caixa(<div className="teste-caixa"><div className="teste-corpo">
    <p className="explica">Aguardando as assinaturas anteriores. Você será avisado por e-mail
      quando for a sua vez de assinar como <strong>{info?.papel}</strong>.</p></div></div>)
  if (fase === 'assinado' || fase === 'fim') return caixa(
    <div className="teste-caixa teste-fim">
      <div className="teste-fim-circulo">✓</div>
      <h2>Assinatura registrada com sucesso.</h2>
      <p className="explica">Obrigado! Sua assinatura, na qualidade de {info?.papel}, foi registrada.
        Você receberá a via por e-mail quando o documento estiver completo.</p>
    </div>)

  if (fase === 'codigo') return caixa(
    <form className="teste-caixa" onSubmit={async (e) => {
      e.preventDefault(); setErro(null); setOcupado(true)
      try { await api.confirmar(token, codigo); await recarregar() }
      catch (er) {
        setErro(er.detail === 'codigo_incorreto' ? 'Código incorreto.'
          : er.detail === 'codigo_expirado' ? 'Código expirado — peça um novo.'
          : 'Não foi possível confirmar.')
      } finally { setOcupado(false) }
    }}>
      <div className="teste-cabecalho">Assinatura de documento — {info?.papel}</div>
      <div className="teste-corpo">
        <p className="explica">Olá, <strong>{info?.nome}</strong>! Um documento aguarda a sua
          assinatura. Para conferir e assinar, confirme sua identidade com o código enviado
          ao seu e-mail.</p>
        <button type="button" className="btn-secundario btn-mini" disabled={ocupado}
                onClick={async () => { setErro(null); try { await api.solicitarCodigo(token) } catch {} }}>
          📧 Enviar código ao meu e-mail</button>
        <label className="campo" style={{ marginTop: '.6rem' }}><span className="rotulo">Código</span>
          <input inputMode="numeric" maxLength={6} placeholder="000000" value={codigo}
                 style={{ letterSpacing: '.4em', textAlign: 'center', fontSize: '1.4rem' }}
                 onChange={(e) => setCodigo(e.target.value.replace(/\D/g, ''))} /></label>
        {erro && <div className="alerta">{erro}</div>}
      </div>
      <div className="teste-rodape">
        <button className="btn-principal btn-mini" disabled={ocupado || codigo.length < 6}>Confirmar</button>
      </div>
    </form>)

  // conferir + assinar
  return caixa(
    <div className="teste-caixa">
      <div className="teste-cabecalho">Confira e assine — {info?.papel}</div>
      <div className="teste-corpo">
        <p className="explica">Confira o documento abaixo antes de assinar como
          <strong> {info?.papel}</strong>.</p>
        <a className="btn-secundario btn-mini" href={api.previewUrl(token)} target="_blank"
           rel="noreferrer">📄 Abrir o documento (PDF)</a>
        {erro && <div className="alerta" style={{ marginTop: '.6rem' }}>{erro}</div>}
      </div>
      <div className="teste-rodape">
        <button className="btn-principal" disabled={ocupado} onClick={async () => {
          if (!window.confirm('Assinar este documento eletronicamente?')) return
          setErro(null); setOcupado(true)
          try { await api.assinar(token); setFase('fim') }
          catch (er) { setErro(`Não foi possível assinar (${er.detail || er.message}).`) }
          finally { setOcupado(false) }
        }}>✍️ Assinar documento</button>
      </div>
    </div>)
}
