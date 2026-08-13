import { useEffect, useState } from 'react'
import { rh as api } from '../api.js'

// Configuração da gravação de entrevistas (v2.98.3).
//
// Duas coisas, e as duas são decisão de POLÍTICA, não ajuste de tela:
//
// **Tamanho do bloco** — a gravação sobe em pedaços durante a conversa. Sala com
// internet ruim pede blocos menores (menos a perder se a conexão cair no meio de
// um); sala boa aguenta blocos maiores, com menos requisições.
//
// **Retenção do áudio** — voz é dado pessoal, e há entendimento de que é
// biométrico. O áudio expira; a TRANSCRIÇÃO permanece, porque é ela que serve
// para escrever a justificativa da avaliação. `0` = guardar por tempo
// indeterminado, e a tela diz isso em palavras: um campo numérico com "0" e sem
// explicação seria lido como "apagar hoje".

export default function ConfigGravacao() {
  const [cfg, setCfg] = useState(null)
  const [erro, setErro] = useState(null)
  const [salvando, setSalvando] = useState(false)
  const [msg, setMsg] = useState(null)
  const [bloco, setBloco] = useState('')
  const [dias, setDias] = useState('')
  const [diarizar, setDiarizar] = useState(true)
  // `null` = não mexer no token guardado; string = gravar (vazia LIMPA).
  const [token, setToken] = useState(null)
  const [teste, setTeste] = useState(null)
  const [testando, setTestando] = useState(false)

  const carregar = () => {
    setErro(null)
    return api.configGravacao()
      .then((d) => {
        setCfg(d); setBloco(String(d.bloco_min)); setDias(String(d.retencao_dias))
        setDiarizar(d.diarizar !== false); setToken(null)
      })
      .catch((e) => setErro(e.detail || e.message || 'Falha ao carregar.'))
  }
  useEffect(() => { carregar() }, [])

  const testar = async () => {
    setTestando(true); setTeste(null)
    try {
      setTeste(await api.testarTokenDiarizacao(token))
    } catch (e) {
      setTeste({ ok: false, mensagem: e.detail || e.message })
    } finally { setTestando(false) }
  }

  const salvar = async () => {
    setSalvando(true); setMsg(null)
    try {
      const d = await api.salvarConfigGravacao({
        bloco_min: Number(bloco), retencao_dias: Number(dias),
        diarizar,
        // Só envia o token se a pessoa digitou algo: `null` preserva o que
        // está guardado, e é isso que permite salvar as outras opções sem
        // reenviar a credencial.
        ...(token === null ? {} : { hf_token: token }),
      })
      setCfg({ ...cfg, ...d })
      setMsg({ texto: 'Configuração salva.' })
    } catch (e) {
      setMsg({ erro: true, texto: e.detail?.[0]?.msg || e.detail || e.message })
    } finally { setSalvando(false) }
  }

  // Falha de carga vira ERRO com "tentar de novo", nunca "Carregando…" eterno
  // (v2.46).
  if (erro) {
    return (
      <div className="rh-card">
        <p className="alerta">Não foi possível carregar: {erro}</p>
        <button className="btn-secundario btn-mini" onClick={carregar}>Tentar de novo</button>
      </div>
    )
  }
  if (!cfg) return <div className="rh-card"><p>Carregando…</p></div>

  return (
    <div className="rh-card">
      <strong>🎙️ Gravação de entrevistas</strong>
      <p className="explica">
        Vale para toda entrevista gravada daqui em diante. O que já foi gravado
        não muda de tamanho de trecho; a retenção, sim — ela é aplicada a cada
        passada do expurgo.
      </p>

      <div className="rh-grid-2">
        <label className="campo">
          <span className="rotulo">Tamanho de cada trecho (minutos)</span>
          <input type="number" min="1" max="60" value={bloco}
                 onChange={(e) => setBloco(e.target.value)} />
          <small className="explica">
            A gravação é enviada em trechos, durante a conversa — se o navegador
            cair, o que já subiu está salvo. Padrão: {cfg.bloco_min_padrao} min.
            Internet instável na sala pede trechos menores.
          </small>
        </label>

        <label className="campo">
          <span className="rotulo">Guardar o áudio por (dias)</span>
          <input type="number" min="0" max="3650" value={dias}
                 onChange={(e) => setDias(e.target.value)} />
          <small className="explica">
            Depois desse prazo o áudio é apagado em definitivo e{' '}
            <strong>a transcrição permanece</strong>. Padrão:{' '}
            {cfg.retencao_dias_padrao} dias. <strong>0 = guardar por tempo
            indeterminado</strong> (nada é apagado).
          </small>
        </label>
      </div>

      {/* Diarização (v3.00): rótulo NEUTRO — "Interlocutor 1, 2". Nunca o nome
          da pessoa: o rótulo pode errar, e a transcrição vai ao PDF que
          circula. Dizer "quem falou" errado numa peça dessas é pior que não
          dizer. */}
      <label className="campo-check" style={{ marginTop: 'var(--esp-3)' }}>
        <input type="checkbox" checked={diarizar}
               onChange={(e) => setDiarizar(e.target.checked)} />
        Separar quem falou (Interlocutor 1, Interlocutor 2…)
      </label>
      <small className="explica">
        Deixa a transcrição muito mais legível, mas <strong>a transcrição demora
        bem mais</strong> — cerca de 1,7× a duração do áudio. Uma conversa de 40
        minutos leva perto de 1 hora para ficar pronta, em segundo plano.
        Os rótulos são neutros: o sistema separa as vozes, mas{' '}
        <strong>não sabe quem é quem</strong>.
      </small>

      {diarizar && (
        <label className="campo" style={{ marginTop: 'var(--esp-2)' }}>
          <span className="rotulo">Token do Hugging Face
            {cfg.tem_hf_token && <span className="chip"> configurado</span>}</span>
          <input type="password" autoComplete="off"
                 placeholder={cfg.tem_hf_token ? '•••••••• (deixe em branco para manter)' : 'hf_…'}
                 value={token ?? ''} onChange={(e) => setToken(e.target.value)} />
          <small className="explica">
            O modelo que separa as vozes exige um token <strong>gratuito</strong>{' '}
            do Hugging Face e o aceite da licença em{' '}
            <code>huggingface.co/pyannote/speaker-diarization-3.1</code>. Ele é
            usado <strong>uma única vez</strong>, para baixar o modelo — depois
            tudo roda aqui dentro, sem custo por uso e sem o áudio sair.
            <strong> Sem o token, a transcrição continua saindo</strong> — só
            não vem separada por interlocutor, e a ficha diz isso.
          </small>
          <div className="navegacao">
            <button type="button" className="btn-secundario btn-mini"
                    disabled={testando} onClick={testar}>
              {testando ? 'Testando…' : 'Testar token'}</button>
          </div>
          {teste && (
            <p className={teste.ok ? 'sucesso' : 'alerta'}>{teste.mensagem}</p>
          )}
        </label>
      )}

      {Number(dias) === 0 && (
        <p className="aviso-inline">
          Com <strong>0</strong>, o áudio das entrevistas fica guardado para
          sempre. Voz é dado pessoal — vale conferir se é isso mesmo que a
          política da empresa prevê.
        </p>
      )}

      {msg && <p className={msg.erro ? 'alerta' : 'sucesso'}>{msg.texto}</p>}
      <div className="navegacao">
        <button className="btn-secundario btn-mini" disabled={salvando} onClick={salvar}>
          {salvando ? 'Salvando…' : 'Salvar'}
        </button>
      </div>
    </div>
  )
}
