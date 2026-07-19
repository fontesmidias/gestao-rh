import { useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import { testagem as api } from '../api.js'
import { Instrucoes, Questionario, NOMES_TESTE } from './TesteApp.jsx'
import { ResultadoDisc, ResultadoSituacional } from '../ResultadoTeste.jsx'
import logo from '../assets/logo.png'

// Testagem avulsa (link público /t/{token}): a pessoa informa SÓ o nome, faz os
// dois testes e VÊ o próprio resultado ao final — ambiente de testagem, não de
// seleção. O RH cria/desativa os links e acompanha em Painel → Testes.
export default function TestagemApp() {
  const { token } = useParams()
  const chavePid = `testagem_pid_${token}`
  const [info, setInfo] = useState(null)
  const [pid, setPid] = useState(sessionStorage.getItem(chavePid))
  const [sessao, setSessao] = useState(null)
  const [fase, setFase] = useState('carregando')
  // fases: carregando | invalido | inativo | nome | menu | teste | resultados
  const [tipoAtual, setTipoAtual] = useState(null)
  const [resultados, setResultados] = useState(null)

  const recarregar = async (p = pid) => {
    const s = await api.sessao(token, p)
    setSessao(s)
    if (s.todos_concluidos) {
      setResultados(await api.resultados(token, p))
      setFase('resultados')
    } else setFase('menu')
    return s
  }

  useEffect(() => {
    api.info(token).then(async (i) => {
      setInfo(i)
      if (!i.ativo) { setFase('inativo'); return }
      if (pid) {
        try { await recarregar(pid); return }
        catch { sessionStorage.removeItem(chavePid); setPid(null) }
      }
      setFase('nome')
    }).catch((e) => setFase(e.detail === 'link_desativado' ? 'inativo' : 'invalido'))
  }, [token])

  const caixa = (filhos) => (
    <div className="candidato">
      <header className="topo"><img src={logo} alt="Green House" className="logo-topo" /></header>
      {filhos}
    </div>
  )

  if (fase === 'carregando') return caixa(<p style={{ padding: '1rem', textAlign: 'center' }}>Carregando…</p>)
  if (fase === 'invalido') return caixa(
    <div className="teste-caixa"><div className="teste-corpo">
      <div className="alerta">Este link de testagem não existe (confira o endereço com quem enviou).</div>
    </div></div>
  )
  if (fase === 'inativo') return caixa(
    <div className="teste-caixa"><div className="teste-corpo">
      <div className="alerta">Este link de testagem está <strong>desativado</strong> no momento.
        Fale com o RH da Green House.</div>
    </div></div>
  )
  if (fase === 'nome') return caixa(
    <FormNome nomeLink={info?.nome} aoEntrar={async (nome) => {
      const r = await api.participar(token, nome)
      sessionStorage.setItem(chavePid, r.participante_id)
      setPid(r.participante_id)
      await recarregar(r.participante_id)
    }} />
  )

  const cli = {
    questoes: (tipo) => api.questoes(token, pid, tipo),
    responder: (tipo, dados) => api.responder(token, pid, tipo, dados),
    concluir: (tipo) => api.concluir(token, pid, tipo),
  }

  if (fase === 'menu') {
    const proximos = sessao?.pendentes || []
    if (!proximos.length) return null
    const t = proximos[0]
    if (t.status === 'em_andamento') {
      if (tipoAtual !== t.tipo) setTipoAtual(t.tipo)
      return caixa(<Questionario cli={cli} tipo={t.tipo} aoConcluir={() => recarregar()} />)
    }
    return caixa(<Instrucoes tipo={t.tipo} comTelemetria={false} aoIniciar={async () => {
      await api.iniciar(token, pid, t.tipo)
      setTipoAtual(t.tipo)
      setFase('teste')
    }} />)
  }
  if (fase === 'teste' && tipoAtual) return caixa(
    <Questionario cli={cli} tipo={tipoAtual} aoConcluir={() => recarregar()} />
  )
  if (fase === 'resultados' && resultados) return caixa(
    <Resultados dados={resultados} />
  )
  return null
}

function FormNome({ nomeLink, aoEntrar }) {
  const [nome, setNome] = useState('')
  const [erro, setErro] = useState(null)
  const [enviando, setEnviando] = useState(false)
  return (
    <form className="teste-caixa" onSubmit={async (e) => {
      e.preventDefault(); setErro(null); setEnviando(true)
      try { await aoEntrar(nome.trim()) }
      catch (err) {
        setErro(err.detail === 'link_desativado' ? 'Este link foi desativado pelo RH.'
          : err.detail === 'muitas_tentativas' ? 'Muitas participações seguidas deste dispositivo. Aguarde um pouco e tente de novo.'
          : 'Não foi possível entrar. Tente novamente.')
      } finally { setEnviando(false) }
    }}>
      <div className="teste-cabecalho">Testes — {nomeLink || 'Green House'}</div>
      <div className="teste-corpo">
        <p className="explica">Você vai responder ao <strong>Inventário Comportamental (DISC)</strong> e
          ao <strong>Teste Situacional</strong>. Ao final, o seu resultado aparece na tela.
          Para começar, informe apenas o seu nome.</p>
        <label className="campo"><span className="rotulo">Seu nome completo</span>
          <input value={nome} required minLength={3} autoFocus
                 onChange={(e) => setNome(e.target.value)} /></label>
        {erro && <div className="alerta">{erro}</div>}
      </div>
      <div className="teste-rodape">
        <button className="btn-principal" disabled={enviando || nome.trim().length < 3}>
          {enviando ? 'Entrando…' : 'Começar »'}</button>
      </div>
    </form>
  )
}

const STATUS_FIM = { concluido: 'concluído', expirado: 'tempo esgotado (pontuado com o que foi respondido)' }

function Resultados({ dados }) {
  const disc = dados.testes.find((t) => t.tipo === 'disc')
  const sit = dados.testes.find((t) => t.tipo === 'situacional')
  return (
    <div className="teste-caixa">
      <div className="teste-cabecalho">Seu resultado, {dados.nome.split(' ')[0]}</div>
      <div className="teste-corpo">
        <p className="explica">Este é um inventário de <strong>apoio à gestão</strong> — não é
          avaliação psicológica nem define quem você é. Use como ponto de partida para
          autoconhecimento.</p>
        {disc && (
          <div className="disc-bloco">
            <strong>{NOMES_TESTE.disc}</strong>{' '}
            <span className="explica" style={{ margin: 0 }}>— {STATUS_FIM[disc.status] || disc.status}</span>
            <ResultadoDisc resultado={disc.resultado} perfis={dados.perfis} />
          </div>
        )}
        {sit && (
          <div className="disc-bloco">
            <strong>{NOMES_TESTE.situacional}</strong>{' '}
            <span className="explica" style={{ margin: 0 }}>— {STATUS_FIM[sit.status] || sit.status}</span>
            <ResultadoSituacional resultado={sit.resultado} />
          </div>
        )}
        <p className="explica">Suas respostas foram registradas. Obrigado por participar! 🌱</p>
      </div>
    </div>
  )
}
