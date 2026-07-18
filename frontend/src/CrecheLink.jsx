import { useEffect, useState } from 'react'
import { creche as api } from './api.js'
import logo from './assets/logo.png'

// Link público único do levantamento do Reembolso-Creche (IN SEGES/MGI 147/2026).
// Etapas: CPF -> código 2FA (e-mail) -> conferir dados -> crianças + certidão -> enviar.
export default function CrecheLink() {
  const [etapa, setEtapa] = useState('cpf') // cpf | codigo | sessao | enviado
  const [cpf, setCpf] = useState('')
  const [email, setEmail] = useState('')
  const [precisaEmail, setPrecisaEmail] = useState(false)
  const [codigo, setCodigo] = useState('')
  const [token, setToken] = useState(null)
  const [erro, setErro] = useState(null)
  const [carregando, setCarregando] = useState(false)

  const iniciar = async (e) => {
    e.preventDefault(); setErro(null); setCarregando(true)
    try {
      const r = await api.iniciar(cpf, precisaEmail ? email : undefined)
      if (r.precisa_email) { setPrecisaEmail(true); setErro(null) }
      else setEtapa('codigo')
    } catch (err) {
      setErro(err.detail === 'cpf_invalido' ? 'CPF inválido. Confira os números.'
        : 'Não foi possível iniciar. Tente novamente em instantes.')
    } finally { setCarregando(false) }
  }

  const confirmar = async (e) => {
    e.preventDefault(); setErro(null); setCarregando(true)
    try {
      const r = await api.confirmar(cpf, codigo, precisaEmail ? email : undefined)
      setToken(r.token); setEtapa('sessao')
    } catch (err) {
      setErro(err.detail === 'codigo_invalido'
        ? 'Código incorreto ou expirado. Confira no seu e-mail (inclusive o spam).'
        : 'Não foi possível confirmar. Tente novamente.')
    } finally { setCarregando(false) }
  }

  return (
    <main className="creche-publico">
      <header className="creche-topo">
        <img src={logo} alt="Green House" className="logo-img" />
        <h1>Reembolso-Creche</h1>
        <p className="creche-sub">Levantamento para análise de elegibilidade ao benefício, nos termos
          da <strong>Instrução Normativa SEGES/MGI nº 147/2026</strong>.</p>
      </header>

      {etapa === 'cpf' && (
        <form className="rh-card creche-card" onSubmit={iniciar}>
          <h2>Vamos começar</h2>
          <p className="explica">Informe seu CPF para localizarmos seu cadastro. Enviaremos um código
            de confirmação ao seu e-mail.</p>
          <label className="campo"><span className="rotulo">CPF</span>
            <input inputMode="numeric" placeholder="000.000.000-00" value={cpf} autoFocus
                   onChange={(e) => setCpf(e.target.value)} /></label>
          {precisaEmail && (
            <>
              <div className="alerta compacto">Não encontramos um e-mail no seu cadastro. Informe um
                e-mail válido para receber o código.</div>
              <label className="campo"><span className="rotulo">Seu e-mail</span>
                <input type="email" placeholder="voce@exemplo.com" value={email}
                       onChange={(e) => setEmail(e.target.value)} /></label>
            </>
          )}
          {erro && <div className="alerta">{erro}</div>}
          <button className="btn-principal" disabled={carregando}>
            {carregando ? 'Enviando…' : 'Enviar código'}</button>
        </form>
      )}

      {etapa === 'codigo' && (
        <form className="rh-card creche-card" onSubmit={confirmar}>
          <h2>Digite o código</h2>
          <p className="explica">Enviamos um código de 6 dígitos ao seu e-mail. <strong>Verifique também
            a caixa de spam</strong> — às vezes a mensagem vai para lá.</p>
          <label className="campo"><span className="rotulo">Código de confirmação</span>
            <input inputMode="numeric" maxLength={6} placeholder="000000" value={codigo} autoFocus
                   style={{ letterSpacing: '.4em', textAlign: 'center', fontSize: '1.4rem' }}
                   onChange={(e) => setCodigo(e.target.value.replace(/\D/g, ''))} /></label>
          {erro && <div className="alerta">{erro}</div>}
          <button className="btn-principal" disabled={carregando || codigo.length < 6}>
            {carregando ? 'Confirmando…' : 'Confirmar'}</button>
          <button type="button" className="btn-link" onClick={() => { setEtapa('cpf'); setCodigo('') }}>
            ← voltar</button>
        </form>
      )}

      {etapa === 'sessao' && token && (
        <SessaoCreche token={token} aoEnviar={() => setEtapa('enviado')} />
      )}

      {etapa === 'enviado' && (
        <div className="rh-card creche-card centro">
          <div style={{ fontSize: '3rem' }}>✅</div>
          <h2>Levantamento enviado!</h2>
          <p className="explica">Recebemos suas informações. O RH vai analisar a elegibilidade ao
            benefício e, se aprovado, você receberá as orientações por e-mail. Obrigado!</p>
        </div>
      )}

      <p className="portal-rodape">Dados tratados segundo a LGPD, exclusivamente para análise,
        concessão e fiscalização do reembolso-creche (IN SEGES/MGI nº 147/2026).</p>
    </main>
  )
}

function SessaoCreche({ token, aoEnviar }) {
  const [dados, setDados] = useState(null)
  const [erro, setErro] = useState(null)
  const [enviando, setEnviando] = useState(false)
  // form de nova criança
  const [nova, setNova] = useState({ nome: '', data_nascimento: '', parentesco: 'filho', tipo_comprovante: 'declaracao' })

  const recarregar = () => api.sessao(token).then(setDados).catch(() => setErro('Sessão expirada. Recomece pelo CPF.'))
  useEffect(() => { recarregar() }, [])

  const addCrianca = async () => {
    if (!nova.nome.trim() || !nova.data_nascimento.trim()) {
      setErro('Informe nome e data de nascimento da criança.'); return }
    setErro(null)
    try { await api.addCrianca(token, nova); setNova({ nome: '', data_nascimento: '', parentesco: 'filho', tipo_comprovante: 'declaracao' }); recarregar() }
    catch { setErro('Não foi possível adicionar. Tente de novo.') }
  }
  const subir = async (criancaId, tipo, arquivo) => {
    if (!arquivo) return
    setErro(null)
    try { await api.subirDocumento(token, criancaId, tipo, arquivo); recarregar() }
    catch (e) { setErro(`Falha ao enviar o arquivo (${e.detail || e.message}).`) }
  }
  const enviar = async () => {
    setErro(null); setEnviando(true)
    try { await api.enviar(token); aoEnviar() }
    catch (e) {
      setErro(e.detail?.erro === 'certidao_faltando'
        ? `Falta a certidão de nascimento de: ${e.detail.criancas.join(', ')}.`
        : e.detail === 'sem_criancas' ? 'Cadastre ao menos uma criança.'
        : 'Não foi possível enviar. Confira os dados.')
    } finally { setEnviando(false) }
  }

  if (!dados) return <div className="rh-card creche-card"><p>Carregando…</p></div>
  if (dados.status !== 'levantamento') {
    return <div className="rh-card creche-card centro"><h2>Você já enviou 🎉</h2>
      <p className="explica">Seu levantamento está em análise. Aguarde o retorno do RH por e-mail.</p></div>
  }

  return (
    <div className="creche-sessao">
      <div className="rh-card creche-card">
        <h2>Confira seus dados</h2>
        <p className="explica">Puxamos do seu cadastro. Confira e, se algo mudou, atualize.</p>
        <div className="creche-dados">
          <div><span className="rotulo">Nome</span><strong>{dados.nome_completo}</strong></div>
          <div><span className="rotulo">CPF</span><strong>{dados.cpf}</strong></div>
          <label className="campo"><span className="rotulo">E-mail</span>
            <input type="email" defaultValue={dados.email || ''}
                   onBlur={(e) => api.conferirDados(token, { email: e.target.value })} /></label>
          <label className="campo"><span className="rotulo">Telefone / WhatsApp</span>
            <input defaultValue={dados.telefone || ''}
                   onBlur={(e) => api.conferirDados(token, { telefone: e.target.value })} /></label>
        </div>
      </div>

      <div className="rh-card creche-card">
        <h2>Crianças</h2>
        <p className="explica">Cadastre cada filho(a), enteado(a) ou criança sob sua guarda judicial, e
          anexe a <strong>certidão de nascimento</strong> (obrigatória) — e o documento de guarda, quando
          for o caso.</p>

        {(dados.criancas || []).map((c) => (
          <div key={c.id} className="creche-crianca">
            <div className="creche-crianca-topo">
              <strong>{c.nome}</strong>
              <span className="explica" style={{ margin: 0 }}>{c.parentesco} · nasc. {c.data_nascimento}</span>
              <button className="btn-link" onClick={() => api.delCrianca(token, c.id).then(recarregar)}>remover</button>
            </div>
            <div className="creche-docs">
              <label className={`creche-doc ${c.tem_certidao ? 'ok' : ''}`}>
                {c.tem_certidao ? '✅ Certidão enviada' : '📎 Enviar certidão de nascimento'}
                <input type="file" hidden accept="image/*,.pdf"
                       onChange={(e) => subir(c.id, 'certidao', e.target.files?.[0])} />
              </label>
              <label className={`creche-doc ${c.tem_guarda ? 'ok' : ''}`}>
                {c.tem_guarda ? '✅ Guarda enviada' : '📎 Guarda judicial (se aplicável)'}
                <input type="file" hidden accept="image/*,.pdf"
                       onChange={(e) => subir(c.id, 'guarda', e.target.files?.[0])} />
              </label>
            </div>
          </div>
        ))}

        <div className="creche-nova">
          <div className="linha3">
            <label className="campo"><span className="rotulo">Nome da criança</span>
              <input value={nova.nome} onChange={(e) => setNova({ ...nova, nome: e.target.value })} /></label>
            <label className="campo"><span className="rotulo">Data de nascimento</span>
              <input placeholder="dd/mm/aaaa" value={nova.data_nascimento}
                     onChange={(e) => setNova({ ...nova, data_nascimento: e.target.value })} /></label>
            <label className="campo"><span className="rotulo">Vínculo</span>
              <select value={nova.parentesco} onChange={(e) => setNova({ ...nova, parentesco: e.target.value })}>
                <option value="filho">Filho(a)</option>
                <option value="enteado">Enteado(a)</option>
                <option value="guarda">Guarda judicial</option>
              </select></label>
          </div>
          <button className="btn-secundario" onClick={addCrianca}>+ Adicionar criança</button>
        </div>
      </div>

      {erro && <div className="alerta">{erro}</div>}
      <button className="btn-principal creche-enviar" disabled={enviando || !(dados.criancas || []).length}
              onClick={enviar}>
        {enviando ? 'Enviando…' : 'Enviar levantamento'}</button>
    </div>
  )
}
