import { useCallback, useEffect, useState } from 'react'
import { rh as api } from '../api.js'
import Ajuda from '../Ajuda.jsx'

// Logs dos serviços — pedido do Bruno em 2026-07-30: "quero muito a tela de
// logs no painel", para não depender de SSH quando alguém liga travado. Foi o
// que aconteceu no incidente do Defender (v2.28): o diagnóstico saiu do log e
// ele teve que abrir terminal na VPS.
//
// Só aparecem aqui os serviços NOSSOS (api, worker, alertas, expurgo), que
// escrevem no volume compartilhado. Postgres e MinIO seguem no `docker logs` —
// ler o stdout deles exigiria dar à API o socket do Docker, e quem
// comprometesse a API assumiria a VPS inteira.

const NIVEIS = [
  ['', 'Tudo'],
  ['WARNING', 'Avisos e erros'],
  ['ERROR', 'Só erros'],
]

// Colore a linha pelo nível, que é o que o olho procura primeiro.
function corDaLinha(linha) {
  if (linha.includes(' ERROR ') || linha.includes(' CRITICAL ')) return 'var(--perigo)'
  if (linha.includes(' WARNING ')) return 'var(--atencao)'
  return 'inherit'
}

export default function LogsRH() {
  const [info, setInfo] = useState(null)
  const [servico, setServico] = useState('')
  const [dia, setDia] = useState('')
  const [busca, setBusca] = useState('')
  const [nivel, setNivel] = useState('')
  const [dados, setDados] = useState(null)
  const [carregando, setCarregando] = useState(false)
  const [msg, setMsg] = useState(null)

  useEffect(() => {
    api.logServicos().then((r) => {
      setInfo(r)
      if (r.servicos?.length && !servico) setServico(r.servicos[0].nome)
    }).catch(() => setMsg({ tipo: 'erro', texto: 'Não foi possível listar os serviços.' }))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const carregar = useCallback(async () => {
    if (!servico) return
    setCarregando(true); setMsg(null)
    try {
      setDados(await api.logLer({ servico, dia, busca, nivel, limite: 500 }))
    } catch {
      setMsg({ tipo: 'erro', texto: 'Não foi possível ler este log.' })
    } finally { setCarregando(false) }
  }, [servico, dia, busca, nivel])

  useEffect(() => { carregar() }, [carregar])

  const baixar = async () => {
    setMsg(null)
    try {
      const blob = await api.logBaixar(servico, dia)
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `${servico}-${dia || 'hoje'}.txt`
      document.body.appendChild(a); a.click(); a.remove()
      setTimeout(() => URL.revokeObjectURL(url), 30000)
    } catch {
      setMsg({ tipo: 'erro', texto: 'Não foi possível baixar este arquivo.' })
    }
  }

  const atual = info?.servicos?.find((s) => s.nome === servico)

  return (
    <main className="pagina">
      <div className="rh-topo">
        <h1>🧾 Logs dos serviços</h1>
        <button className="btn-secundario btn-mini" onClick={carregar} disabled={carregando}>
          {carregando ? 'Lendo…' : '🔄 Atualizar'}</button>
      </div>

      <p className="explica">O que cada serviço registrou, direto do arquivo — sem precisar
        entrar por SSH. Guardamos em arquivo porque o log do container <strong>some quando ele
        reinicia</strong>, e é dele que sai o diagnóstico quando alguém não consegue entrar.</p>

      {info && !info.ativo && (
        <div className="alerta">Nenhum arquivo de log encontrado em <code>{info.diretorio}</code>.
          Isso normalmente significa que o volume de logs ainda não foi montado — depois de
          atualizar a stack, os serviços passam a escrever aqui.</div>
      )}

      {msg && <div className={msg.tipo === 'erro' ? 'alerta' : 'sucesso'}>{msg.texto}</div>}

      {info?.ativo && (
        <>
          <div className="rh-card">
            <div className="rh-grid-2">
              <label className="campo"><span className="rotulo">Serviço</span>
                <select value={servico} onChange={(e) => { setServico(e.target.value); setDia('') }}>
                  {info.servicos.map((s) => (
                    <option key={s.nome} value={s.nome}>{s.nome}</option>))}
                </select></label>
              <label className="campo"><span className="rotulo">Dia</span>
                <select value={dia} onChange={(e) => setDia(e.target.value)}>
                  <option value="">Hoje</option>
                  {(atual?.dias || []).map((d) => (
                    <option key={d} value={d}>{d}</option>))}
                </select></label>
            </div>
            <div className="rh-grid-2">
              <label className="campo"><span className="rotulo">Procurar no texto</span>
                <input value={busca} placeholder="ex.: creche, 9738, ERROR"
                       onChange={(e) => setBusca(e.target.value)} /></label>
              <label className="campo"><span className="rotulo">Nível</span>
                <select value={nivel} onChange={(e) => setNivel(e.target.value)}>
                  {NIVEIS.map(([v, r]) => <option key={v} value={v}>{r}</option>)}
                </select></label>
            </div>
            <button className="btn-secundario btn-mini" onClick={baixar}>
              ⬇ Baixar este log em .txt</button>
          </div>

          <div className="rh-card">
            {dados?.truncado && (
              <p className="explica">Mostrando as <strong>{dados.total}</strong> linhas mais
                recentes de {dados.lidas}. Use a busca para achar o resto, ou baixe o arquivo
                completo.</p>
            )}
            {!dados?.linhas?.length
              ? <p className="explica">Nada encontrado com esses filtros.</p>
              : (
                <div className="dash-scroll">
                  <pre className="bloco-codigo" style={{ maxHeight: '60vh', overflow: 'auto' }}>
                    {dados.linhas.map((l, i) => (
                      <div key={i} style={{ color: corDaLinha(l), whiteSpace: 'pre-wrap' }}>{l}</div>
                    ))}
                  </pre>
                </div>
              )}
          </div>
        </>
      )}

      <Retencao inicial={info?.retencao_dias} />
    </main>
  )
}

// Retenção + envio por e-mail. O Bruno pediu as duas coisas juntas: "não
// precisa guardar, envie 4x por dia" E "a retenção customizada, inclusive
// indeterminada".
function Retencao({ inicial }) {
  const [dias, setDias] = useState('')
  const [ocupado, setOcupado] = useState(false)
  const [msg, setMsg] = useState(null)

  useEffect(() => {
    if (inicial !== undefined && inicial !== null) setDias(String(inicial))
  }, [inicial])

  const salvar = async () => {
    setOcupado(true); setMsg(null)
    try {
      await api.salvarLogRetencao(Number(dias))
      setMsg({ tipo: 'ok', texto: Number(dias) === 0
        ? 'Retenção indeterminada: nenhum log será apagado automaticamente.'
        : `Retenção salva: ${dias} dia(s). A limpeza roda uma vez por dia.` })
    } catch {
      setMsg({ tipo: 'erro', texto: 'Não foi possível salvar a retenção.' })
    } finally { setOcupado(false) }
  }

  const enviar = async () => {
    setOcupado(true); setMsg(null)
    try {
      const r = await api.logEnviarAgora()
      setMsg(r.enviado
        ? { tipo: 'ok', texto: 'Enviado. Confira a caixa dos destinatários do aviso.' }
        : { tipo: 'erro', texto: 'Nada foi enviado — confira se há destinatários em '
            + 'Configurações → Avisos internos, no evento "Logs dos serviços".' })
    } catch {
      setMsg({ tipo: 'erro', texto: 'Não foi possível enviar agora.' })
    } finally { setOcupado(false) }
  }

  return (
    <details className="rh-card">
      <summary><strong>⚙️ Retenção e envio por e-mail</strong></summary>
      <p className="explica">Os logs vão por e-mail <strong>4 vezes ao dia</strong> (a cada 6
        horas), com os arquivos em anexo. Quem recebe é definido em Configurações → Avisos
        internos, no evento <em>“Logs dos serviços”</em> — dá para colocar vários endereços
        separados por vírgula.</p>
      <p className="explica">Estes arquivos contêm CPF, e-mail e nome de pessoas reais.
        {' '}<Ajuda texto="Retenção: por quanto tempo os arquivos de log ficam guardados no
        servidor antes de serem apagados sozinhos." /> Guarde só o tempo de que precisa.</p>
      <label className="campo"><span className="rotulo">Guardar por (dias) — 0 = indeterminado</span>
        <input type="number" min={0} max={3650} value={dias}
               onChange={(e) => setDias(e.target.value)} /></label>
      {Number(dias) === 0 && (
        <p className="explica">⚠️ Com <strong>0</strong>, nenhum log é apagado automaticamente —
          eles crescem até você apagar. Bom para investigar; ruim para deixar esquecido.</p>
      )}
      {msg && <div className={msg.tipo === 'erro' ? 'alerta' : 'sucesso'}>{msg.texto}</div>}
      <button className="btn-principal" onClick={salvar} disabled={ocupado || dias === ''}>
        Salvar retenção</button>
      <button className="btn-secundario" onClick={enviar} disabled={ocupado}>
        ✉️ Enviar os logs agora</button>
    </details>
  )
}
