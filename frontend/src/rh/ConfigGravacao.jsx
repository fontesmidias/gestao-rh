import { useEffect, useState } from 'react'
import { rh as api } from '../api.js'
import SelectBusca from '../SelectBusca.jsx'

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
  const [modelo, setModelo] = useState('')

  const carregar = () => {
    setErro(null)
    return api.configGravacao()
      .then((d) => {
        setCfg(d); setBloco(String(d.bloco_min)); setDias(String(d.retencao_dias))
        setDiarizar(d.diarizar !== false)
        setModelo(d.modelo || d.modelo_padrao || '')
      })
      .catch((e) => setErro(e.detail || e.message || 'Falha ao carregar.'))
  }
  useEffect(() => { carregar() }, [])

  const salvar = async () => {
    setSalvando(true); setMsg(null)
    try {
      const d = await api.salvarConfigGravacao({
        bloco_min: Number(bloco), retencao_dias: Number(dias),
        diarizar, modelo,
        // O TOKEN não é enviado daqui: ele vive em Integrações (v3.00.2), e
        // omiti-lo preserva o que está guardado — salvar a política nunca
        // mexe na credencial.
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

      {/* Qualidade da transcrição (v3.00.5, decisão do Bruno): o `small`
          errava nome próprio e sigla numa entrevista real — "Dexion" saiu
          "Daxon", "eSocial" saiu "ex-social". O texto vira justificativa de
          avaliação, e nome errado ali é pior que espera maior.

          A lista vem do SERVIDOR: repeti-la aqui daria, na primeira mudança,
          uma opção que o worker recusa. */}
      <label className="campo" style={{ marginTop: 'var(--esp-3)' }}>
        <span className="rotulo">Qualidade da transcrição</span>
        <SelectBusca valor={modelo} aoMudar={setModelo}
                     opcoes={(cfg.modelos || []).map((m) => ({
                       valor: m.valor, rotulo: m.rotulo, extra: m.detalhe }))} />
        <small className="explica">
          {(cfg.modelos || []).find((m) => m.valor === modelo)?.detalhe}
          {' '}O tempo é somado ao da separação de vozes, quando ela está ligada.
        </small>
      </label>

      {modelo && cfg.modelo && modelo !== cfg.modelo && (
        <p className="aviso-inline">
          <strong>Vale só para o que for transcrito daqui em diante.</strong> O
          que já está pronto não muda sozinho — para reaproveitar a qualidade
          nova numa entrevista antiga, use <strong>↻ Refazer</strong> na ficha
          dela. E a primeira transcrição com um modelo novo demora mais: ele
          precisa ser baixado uma vez.
        </p>
      )}

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

      {diarizar && !cfg.tem_hf_token && (
        <p className="aviso-inline">
          A separação está ligada, mas o <strong>token do Hugging Face</strong>{' '}
          ainda não foi configurado — enquanto isso a transcrição sai sem os
          rótulos. Configure em <strong>Configurações → 🔌 E-mail e
          integrações</strong>.
        </p>
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
