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

  const carregar = () => {
    setErro(null)
    return api.configGravacao()
      .then((d) => { setCfg(d); setBloco(String(d.bloco_min)); setDias(String(d.retencao_dias)) })
      .catch((e) => setErro(e.detail || e.message || 'Falha ao carregar.'))
  }
  useEffect(() => { carregar() }, [])

  const salvar = async () => {
    setSalvando(true); setMsg(null)
    try {
      const d = await api.salvarConfigGravacao({
        bloco_min: Number(bloco), retencao_dias: Number(dias),
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
