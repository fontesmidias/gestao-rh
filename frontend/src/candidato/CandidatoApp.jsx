import { useEffect, useMemo, useState } from 'react'
import { useParams } from 'react-router-dom'
import { driver } from 'driver.js'
import 'driver.js/dist/driver.css'
import { candidato as api } from '../api.js'
import Wizard from './Wizard.jsx'
import Assinatura from './Assinatura.jsx'
import Checklist from './Checklist.jsx'
import logo from '../assets/logo.png'

export default function CandidatoApp() {
  const { token } = useParams()
  const [estado, setEstado] = useState(null)
  const [erro, setErro] = useState(null)
  const [tela, setTela] = useState(null) // boas-vindas | formulario | assinatura | documentos | acompanhamento

  const recarregar = async () => {
    const e = await api.ficha(token)
    setEstado(e)
    return e
  }

  const [reassinatura, setReassinatura] = useState(false)

  useEffect(() => {
    recarregar()
      .then(async (e) => {
        if (!e.aceite_lgpd_em) { setTela('boas-vindas'); return }
        if (['convidado', 'preenchendo'].includes(e.status)) { setTela('formulario'); return }
        if (e.status === 'aguardando_assinatura') { setTela('assinatura'); return }
        // Já passou da assinatura? Se o RH atualizou dados, algum documento
        // pode ter voltado a pendente — a assinatura fura a fila, sem travar o resto.
        try {
          const f = await api.fichas(token)
          if (f.fichas.some((x) => !x.assinado)) {
            setReassinatura(true)
            setTela('assinatura')
            return
          }
        } catch { /* segue o fluxo normal */ }
        setTela(e.status === 'docs_pendentes' ? 'documentos' : 'acompanhamento')
      })
      .catch((e) => setErro(e.status === 404 ? 'link' : 'geral'))
  }, [token])

  const tour = useMemo(() => driver({
    showProgress: true,
    nextBtnText: 'Próximo', prevBtnText: 'Voltar', doneBtnText: 'Entendi!',
    steps: [
      { popover: { title: '👋 Bem-vindo(a)!', description: 'Sua admissão é 100% digital e leva poucos minutos. Vamos te mostrar como funciona.' } },
      { popover: { title: '📝 1. Preencha seus dados', description: 'Responda o formulário com calma. Tudo é salvo automaticamente — pode parar e voltar depois pelo mesmo link.' } },
      { popover: { title: '✍️ 2. Assine 3 documentos', description: 'Você confere os documentos prontos e assina digitando um código que enviamos por e-mail. Sem imprimir nada.' } },
      { popover: { title: '📄 3. Envie fotos dos documentos', description: 'Uma lista mostra o que falta. Toque no botão "?" de cada item para ver dicas de onde conseguir.' } },
    ],
  }), [])

  if (erro === 'link') return (
    <Cartao>
      <h2>😕 Este link não está mais ativo</h2>
      <p>Ele pode ter vencido. Fale com o RH da Green House pelo WhatsApp para receber um novo link.</p>
    </Cartao>
  )
  if (erro) return <Cartao><h2>Algo deu errado</h2><p>Tente recarregar a página.</p></Cartao>
  if (!estado || !tela) return <Cartao><p>Carregando…</p></Cartao>

  const nome = (estado.pessoais?.nome_completo || '').split(' ')[0]

  const PASSOS = ['Seus dados', 'Assinatura', 'Documentos', 'Conferência']
  const passoAtual = { 'boas-vindas': 0, formulario: 0, assinatura: 1,
                       documentos: 2, acompanhamento: 3 }[tela]

  return (
    <div className="candidato">
      <header className="topo">
        <img src={logo} alt="Green House" className="logo-topo" />
        <button className="btn-ajuda" title="Rever explicação" onClick={() => tour.drive()}>?</button>
      </header>

      <nav className="stepper" aria-label="Etapas da admissão">
        {PASSOS.map((nome, i) => (
          <div key={nome}
               className={`passo ${i === passoAtual ? 'atual' : ''} ${i < passoAtual ? 'feito' : ''}`}>
            <span className="passo-num">{i < passoAtual ? '✓' : i + 1}</span>
            <span className="passo-nome">{nome}</span>
          </div>
        ))}
      </nav>

      {tela === 'boas-vindas' && (
        <Cartao>
          <h1>Olá{nome ? `, ${nome}` : ''}! 👋</h1>
          <p>Sua admissão na Green House depende do que você vai fazer agora — e
             <strong> quanto antes concluir, antes sua contratação é efetivada</strong>.
             O processo é digital e leva poucos minutos. Se precisar interromper, tudo fica
             salvo e você continua por este mesmo link — mas <strong>não deixe para depois:
             sem a documentação completa, o RH não pode efetivar seu registro</strong>.</p>
          <details className="lgpd">
            <summary>Aviso de Privacidade (LGPD) — toque para ler</summary>
            <p>A Green House coleta estes dados para admissão e cumprimento de obrigações
               trabalhistas, previdenciárias e fiscais (LGPD, art. 7º, II, V e VI). Cor/raça e
               dados de saúde são tratados para cumprimento de obrigação legal e proteção da sua
               vida e integridade física (art. 11, II, 'a' e 'e'), com uso restrito a essas
               finalidades.</p>
          </details>
          <button className="btn-principal" onClick={async () => {
            await api.aceiteLgpd(token)
            setTela('formulario')
            if (!localStorage.getItem('tour_visto')) {
              localStorage.setItem('tour_visto', '1')
              setTimeout(() => tour.drive(), 400)
            }
          }}>Li e concordo em continuar</button>
        </Cartao>
      )}

      {tela === 'formulario' && (
        <Wizard token={token} estado={estado} recarregar={recarregar}
                aoConcluir={() => setTela('assinatura')} />
      )}

      {tela === 'assinatura' && (
        <>
          {reassinatura && (
            <div className="alerta" style={{ maxWidth: 560, margin: '0 auto 1rem' }}>
              📝 <strong>Alguns documentos foram atualizados</strong> pelo RH e precisam da
              sua assinatura novamente. É rápido: confira e assine com o código do e-mail.
            </div>
          )}
          <Assinatura token={token} email={estado.pessoais?.email}
                      aoConcluir={() => setTela(
                        reassinatura && estado.status !== 'aguardando_assinatura'
                          ? (estado.status === 'docs_pendentes' ? 'documentos' : 'acompanhamento')
                          : 'documentos')} />
        </>
      )}

      {tela === 'documentos' && (
        <Checklist token={token} aoConcluir={() => setTela('acompanhamento')} />
      )}

      {tela === 'acompanhamento' && <Acompanhamento token={token} estado={estado} />}
    </div>
  )
}

function Acompanhamento({ token, estado }) {
  const [check, setCheck] = useState(null)
  useEffect(() => { api.documentos(token).then(setCheck).catch(() => {}) }, [token])
  const aprovado = estado.status === 'aprovado'
  return (
    <Cartao>
      <p className="etapa-num">Parte 4 de 4 — Conferência</p>
      {aprovado ? (
        <><h1>🎉 Documentação completa!</h1>
          <p>Bem-vindo(a) à Green House! Sua documentação foi aprovada. O RH entrará em
             contato com as orientações do seu primeiro dia.</p></>
      ) : (
        <><h1>📥 Recebemos seu envio!</h1>
          <p><strong>O que acontece agora:</strong> o RH confere cada documento e você será
             informado(a) <strong>por e-mail</strong> em qualquer caso. Se algum documento
             precisar ser reenviado, o e-mail explicará o motivo — basta acessar novamente
             o seu link de admissão (o mesmo desta página) e reenviar apenas o documento
             indicado. Quando tudo for aprovado, o e-mail confirmará a conclusão da sua
             documentação.</p>
          {check && <p className="progresso-txt">
            {check.progresso.ok} de {check.progresso.total} documentos conferidos/recebidos.</p>}</>
      )}
    </Cartao>
  )
}

export function Cartao({ children }) {
  return <main className="cartao">{children}</main>
}
