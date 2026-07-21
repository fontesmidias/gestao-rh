import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { talentos as api } from './api.js'
import logo from './assets/logo.png'

// Formulário PÚBLICO do Banco de Talentos (sem login), em 3 passos curtos com
// barra de progresso — substitui o Microsoft Forms. Aceita currículo opcional
// (PDF/foto/Word). Só nome + aceite LGPD são obrigatórios (máxima conversão).
const PASSOS = ['Sobre você', 'O que você procura', 'Currículo & experiência']
const TIPOS = [
  { v: 'efetivo', r: 'Efetivo' },
  { v: 'intermitente', r: 'Intermitente' },
  { v: 'tanto_faz', r: 'Tanto faz — aceito os dois' },
]
const CV_ACCEPT = '.pdf,.doc,.docx,image/*'

export default function BancoDeTalentos() {
  const [passo, setPasso] = useState(0)
  const [cargos, setCargos] = useState([])
  const [regioes, setRegioes] = useState([])
  const [form, setForm] = useState({
    nome: '', email: '', telefone: '', cidade: '',
    cargos_interesse: [], regioes: [], tipo_contratacao: '',
    ja_trabalhou_funcao: null, recebe_seguro_desemprego: null,
    resumo: '', origem: '', consentimento_lgpd: false, website: '',
  })
  const [curriculo, setCurriculo] = useState(null)   // File
  const [enviado, setEnviado] = useState(false)
  const [erro, setErro] = useState(null)
  const [enviando, setEnviando] = useState(false)
  const inputCv = useRef(null)

  useEffect(() => {
    api.opcoes().then((o) => { setCargos(o.cargos || []); setRegioes(o.regioes || []) }).catch(() => {})
  }, [])

  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value })
  const toggleLista = (k, valor) => setForm((f) => {
    const tem = f[k].includes(valor)
    return { ...f, [k]: tem ? f[k].filter((x) => x !== valor) : [...f[k], valor] }
  })

  const validarPasso = () => {
    if (passo === 0 && !form.nome.trim()) return 'Informe o seu nome para continuarmos.'
    if (passo === 2 && !form.consentimento_lgpd) return 'É preciso aceitar o uso dos dados (LGPD) para enviar.'
    return null
  }
  const avancar = () => {
    const e = validarPasso()
    if (e) { setErro(e); return }
    setErro(null); setPasso((p) => Math.min(p + 1, PASSOS.length - 1))
  }
  const voltar = () => { setErro(null); setPasso((p) => Math.max(p - 1, 0)) }

  const enviar = async (e) => {
    e.preventDefault()
    const err = validarPasso()
    if (err) { setErro(err); return }
    setErro(null); setEnviando(true)
    try {
      const { website, ...dados } = form
      const r = await api.cadastrar({ ...dados, website })
      // currículo é opcional: se anexou e o cadastro devolveu token, envia
      if (curriculo && r?.id && r?.upload_token) {
        try { await api.enviarCurriculo(r.id, r.upload_token, curriculo) }
        catch { /* currículo é opcional — não bloqueia o cadastro já gravado */ }
      }
      setEnviado(true)
    } catch (err2) {
      setErro(err2.detail === 'consentimento_obrigatorio'
        ? 'É preciso aceitar o uso dos dados (LGPD) para enviar.'
        : `Não foi possível enviar (${err2.detail || err2.message}). Tente de novo.`)
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
      <p className="explica centro">Quer trabalhar na Green House? Leva 1 minuto.
        Assim que surgir uma vaga com o seu perfil, o RH fala com você.</p>

      {/* barra de progresso */}
      <div className="talento-passos" aria-hidden="true">
        {PASSOS.map((t, i) => (
          <div key={t} className={`talento-passo ${i === passo ? 'ativo' : ''} ${i < passo ? 'feito' : ''}`}>
            <span className="talento-passo-num">{i < passo ? '✓' : i + 1}</span>
            <span className="talento-passo-rot">{t}</span>
          </div>
        ))}
      </div>

      <form onSubmit={enviar}>
        {passo === 0 && (
          <fieldset className="talento-fs">
            <legend>Sobre você</legend>
            <label className="campo"><span className="rotulo">Nome completo *</span>
              <input value={form.nome} onChange={set('nome')} autoComplete="name" autoFocus /></label>
            <div className="linha2">
              <label className="campo"><span className="rotulo">Telefone / WhatsApp</span>
                <input value={form.telefone} onChange={set('telefone')} autoComplete="tel"
                       inputMode="tel" placeholder="(61) 90000-0000" /></label>
              <label className="campo"><span className="rotulo">E-mail</span>
                <input type="email" value={form.email} onChange={set('email')} autoComplete="email" /></label>
            </div>
            <label className="campo"><span className="rotulo">Cidade / bairro onde mora</span>
              <input value={form.cidade} onChange={set('cidade')}
                     placeholder="Ex.: Samambaia" /></label>
          </fieldset>
        )}

        {passo === 1 && (
          <fieldset className="talento-fs">
            <legend>O que você procura</legend>
            <span className="rotulo">Cargos / funções de interesse <small>(toque em quantos quiser)</small></span>
            <div className="chips-escolha">
              {cargos.map((c) => (
                <button type="button" key={c}
                        className={`chip-escolha ${form.cargos_interesse.includes(c) ? 'on' : ''}`}
                        onClick={() => toggleLista('cargos_interesse', c)}>{c}</button>
              ))}
            </div>

            <span className="rotulo" style={{ marginTop: '1rem' }}>Regiões onde pode trabalhar</span>
            <div className="chips-escolha">
              {regioes.map((r) => (
                <button type="button" key={r}
                        className={`chip-escolha ${form.regioes.includes(r) ? 'on' : ''}`}
                        onClick={() => toggleLista('regioes', r)}>{r}</button>
              ))}
            </div>

            <span className="rotulo" style={{ marginTop: '1rem' }}>Tipo de contratação que aceita</span>
            <div className="chips-escolha">
              {TIPOS.map((t) => (
                <button type="button" key={t.v}
                        className={`chip-escolha ${form.tipo_contratacao === t.v ? 'on' : ''}`}
                        onClick={() => setForm({ ...form, tipo_contratacao: t.v })}>{t.r}</button>
              ))}
            </div>

            <div className="linha2" style={{ marginTop: '1rem' }}>
              <SimNao rotulo="Já trabalhou na(s) função(ões) que marcou?"
                      valor={form.ja_trabalhou_funcao}
                      onChange={(v) => setForm({ ...form, ja_trabalhou_funcao: v })} />
              <SimNao rotulo="Está recebendo seguro-desemprego?"
                      valor={form.recebe_seguro_desemprego}
                      onChange={(v) => setForm({ ...form, recebe_seguro_desemprego: v })} />
            </div>
          </fieldset>
        )}

        {passo === 2 && (
          <fieldset className="talento-fs">
            <legend>Currículo & experiência</legend>
            <span className="rotulo">Currículo <small>(opcional — aumenta suas chances)</small></span>
            <input ref={inputCv} type="file" accept={CV_ACCEPT} hidden
                   onChange={(e) => setCurriculo(e.target.files?.[0] || null)} />
            <button type="button" className="talento-cv" onClick={() => inputCv.current?.click()}>
              {curriculo
                ? <>📎 <strong>{curriculo.name}</strong> · trocar</>
                : <>📎 Anexar currículo <small>PDF, foto ou Word</small></>}
            </button>

            <label className="campo" style={{ marginTop: '.9rem' }}>
              <span className="rotulo">Conte sobre sua experiência</span>
              <textarea rows={4} value={form.resumo} onChange={set('resumo')}
                        placeholder="Onde trabalhou, por quanto tempo, o que sabe fazer…" /></label>
            <label className="campo"><span className="rotulo">Como conheceu a Green House?</span>
              <input value={form.origem} onChange={set('origem')}
                     placeholder="Indicação, Instagram, site…" /></label>

            <label className="talento-lgpd">
              <input type="checkbox" checked={form.consentimento_lgpd}
                     onChange={(e) => setForm({ ...form, consentimento_lgpd: e.target.checked })} />
              <span>Autorizo a Green House a tratar meus dados para fins de recrutamento,
                conforme a <strong>LGPD</strong> (Lei nº 13.709/2018). Posso pedir a exclusão
                a qualquer momento pelo e-mail rh@greenhousedf.com.br. *</span>
            </label>
          </fieldset>
        )}

        {/* honeypot: escondido de humanos, bots preenchem */}
        <input className="campo-isca" tabIndex={-1} autoComplete="off" value={form.website}
               onChange={set('website')} aria-hidden="true" />

        {erro && <div className="alerta">{erro}</div>}

        <div className="talento-nav">
          {passo > 0
            ? <button type="button" className="btn-secundario" onClick={voltar}>← Voltar</button>
            : <span />}
          {passo < PASSOS.length - 1
            ? <button type="button" className="btn-principal" onClick={avancar}>Avançar →</button>
            : <button type="submit" className="btn-principal" disabled={enviando}>
                {enviando ? 'Enviando…' : 'Entrar para o Banco de Talentos'}</button>}
        </div>
      </form>

      <p className="explica centro" style={{ marginTop: '.8rem' }}>
        <Link to="/">← Voltar ao início</Link></p>
    </main>
  )
}

// Botãozinho Sim/Não (tri-estado: null = não respondido)
function SimNao({ rotulo, valor, onChange }) {
  return (
    <div className="campo">
      <span className="rotulo">{rotulo}</span>
      <div className="chips-escolha">
        <button type="button" className={`chip-escolha ${valor === true ? 'on' : ''}`}
                onClick={() => onChange(valor === true ? null : true)}>Sim</button>
        <button type="button" className={`chip-escolha ${valor === false ? 'on' : ''}`}
                onClick={() => onChange(valor === false ? null : false)}>Não</button>
      </div>
    </div>
  )
}
