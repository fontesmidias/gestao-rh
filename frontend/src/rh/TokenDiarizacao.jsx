import { useEffect, useState } from 'react'
import { rh as api } from '../api.js'

// Token do Hugging Face — separação de vozes na transcrição (v3.00.2).
//
// **Por que fica em Integrações e não junto dos roteiros** (correção do Bruno,
// 2026-08-12): é CREDENCIAL de serviço externo, o mesmo tipo do M365, do Teams e
// das chaves de IA — todas moram aqui. Configuração de POLÍTICA (tamanho do
// trecho, retenção do áudio, ligar ou não a separação) continua com os roteiros
// de entrevista, porque é decisão do processo, não de integração.
//
// A distinção não é organizacional: quem procura "onde ponho a credencial X"
// abre Integrações, e é lá que ela precisa estar.

export default function TokenDiarizacao() {
  const [cfg, setCfg] = useState(null)
  // `null` = não mexer no que está guardado; string = gravar (vazia LIMPA).
  const [token, setToken] = useState(null)
  const [teste, setTeste] = useState(null)
  const [ocupado, setOcupado] = useState(false)
  const [msg, setMsg] = useState(null)

  const carregar = () => api.configGravacao()
    .then((r) => { setCfg(r); setToken(null) })
    .catch(() => {})
  useEffect(() => { carregar() }, [])
  if (!cfg) return null

  const testar = async () => {
    setOcupado(true); setTeste(null); setMsg(null)
    try {
      setTeste(await api.testarTokenDiarizacao(token))
    } catch (e) {
      setTeste({ ok: false, mensagem: e.detail || e.message })
    } finally { setOcupado(false) }
  }

  const salvar = async () => {
    setOcupado(true); setMsg(null)
    try {
      // Manda as opções atuais junto: a rota exige bloco e retenção, e
      // reenviá-las como estão evita que salvar o token mexa na política.
      await api.salvarConfigGravacao({
        bloco_min: cfg.bloco_min, retencao_dias: cfg.retencao_dias,
        hf_token: token ?? '',
      })
      await carregar()
      setMsg({ tipo: 'ok', texto: 'Token salvo.' })
    } catch (e) {
      setMsg({ tipo: 'erro', texto: e.detail || e.message })
    } finally { setOcupado(false) }
  }

  return (
    <section className="rh-card">
      <h3>🎙️ Separação de vozes na transcrição</h3>
      <p className="explica">
        Faz a transcrição da entrevista sair separada por{' '}
        <strong>Interlocutor 1, Interlocutor 2</strong>, em vez de texto corrido.
        O modelo exige um token <strong>gratuito</strong> do Hugging Face, usado
        <strong> uma única vez</strong> para baixá-lo — depois tudo roda aqui
        dentro, sem custo por uso e sem o áudio sair do sistema.
      </p>
      <p className="explica">
        <strong>Sem o token, a transcrição continua saindo</strong> — só não vem
        separada, e a ficha da entrevista diz o motivo. Ligar ou desligar a
        separação, o tamanho dos trechos e a retenção do áudio ficam em{' '}
        <strong>Roteiros de entrevista</strong>.
      </p>

      <label className="campo">
        <span className="rotulo">Token do Hugging Face
          {cfg.tem_hf_token && <span className="chip"> configurado</span>}</span>
        <input type="password" autoComplete="off"
               placeholder={cfg.tem_hf_token
                 ? '•••••••• (deixe em branco para manter o atual)'
                 : 'hf_…'}
               value={token ?? ''} onChange={(e) => setToken(e.target.value)} />
      </label>

      <p className="explica">
        Crie em <code>huggingface.co/settings/tokens</code> e{' '}
        <strong>aceite a licença</strong> em{' '}
        <code>huggingface.co/pyannote/speaker-diarization-3.1</code>, com a mesma
        conta. São duas coisas diferentes — o teste abaixo diz qual está faltando.
      </p>

      <div className="navegacao">
        {/* Testar ANTES de usar: sem isto, o erro só apareceria depois de uma
            entrevista de 40 minutos sair sem os rótulos. */}
        <button className="btn-secundario btn-mini" disabled={ocupado}
                onClick={testar}>
          {ocupado ? 'Testando…' : 'Testar token'}</button>
        <button className="btn-secundario btn-mini"
                disabled={ocupado || token === null} onClick={salvar}>
          Salvar</button>
      </div>

      {teste && <p className={teste.ok ? 'sucesso' : 'alerta'}>{teste.mensagem}</p>}
      {msg && <p className={msg.tipo === 'erro' ? 'alerta' : 'sucesso'}>{msg.texto}</p>}
    </section>
  )
}
