import { useEffect, useRef, useState } from 'react'
import { buscar, authRH } from '../api.js'

// Player de áudio da entrevista (v2.98) — desktop e celular.
//
// **Por que não `<audio src={url}>` direto:** as rotas de áudio exigem
// `Authorization: Bearer`, e o `<audio>` não manda header — ele faria um GET
// anônimo e receberia 401. O padrão da casa para arquivo autenticado é buscar o
// blob e criar um `objectURL` (é o que o `VisualizadorArquivo` faz desde a
// v2.33), com o bônus de o download sair com o nome certo em vez do último
// segmento da URL.
//
// Usa o `<audio controls>` NATIVO de propósito: no celular ele vira o controle
// do sistema (com a tela bloqueada, no fone), coisa que um player desenhado à
// mão não consegue. É a mesma escolha do `<details>` e do `<input type=file>`:
// o nativo ganha quando o navegador faz melhor.

export default function PlayerAudio({ url, nome, rotulo }) {
  const [blobUrl, setBlobUrl] = useState(null)
  const [erro, setErro] = useState(null)
  const [carregando, setCarregando] = useState(false)
  const objetoRef = useRef(null)

  // Revoga o objectURL ao sair: sem isso o áudio inteiro fica na memória do
  // navegador depois de fechar a ficha — e são dezenas de MB por entrevista.
  useEffect(() => () => {
    if (objetoRef.current) URL.revokeObjectURL(objetoRef.current)
  }, [])

  const carregar = async () => {
    setCarregando(true); setErro(null)
    try {
      const r = await buscar(url, { headers: authRH() })
      if (!r.ok) throw new Error(r.status === 404 ? 'áudio não encontrado' : `erro ${r.status}`)
      const b = await r.blob()
      if (objetoRef.current) URL.revokeObjectURL(objetoRef.current)
      objetoRef.current = URL.createObjectURL(b)
      setBlobUrl(objetoRef.current)
    } catch (e) {
      setErro(e.message || 'não foi possível carregar o áudio')
    } finally { setCarregando(false) }
  }

  const baixar = () => {
    if (!blobUrl) return
    const a = document.createElement('a')
    a.href = blobUrl
    a.download = `${nome}.webm`
    a.click()
  }

  // Só busca o áudio quando a pessoa PEDE. Carregar sozinho baixaria dezenas de
  // MB ao abrir a ficha — no celular, com dados móveis, sem ninguém pedir.
  if (!blobUrl) {
    return (
      <div className="player-audio">
        {rotulo && <span className="player-rotulo">{rotulo}</span>}
        <button type="button" className="btn-secundario btn-mini"
                disabled={carregando} onClick={carregar}>
          {carregando ? 'Carregando…' : '▶ Ouvir'}
        </button>
        {erro && <span className="alerta" style={{ padding: '.2rem .5rem' }}>{erro}</span>}
      </div>
    )
  }

  return (
    <div className="player-audio">
      {rotulo && <span className="player-rotulo">{rotulo}</span>}
      {/* `preload="metadata"`: o blob já está na memória, mas isso faz o
          navegador saber a duração antes de tocar — sem, a barra fica sem fim
          conhecido e não dá para arrastar. */}
      <audio controls preload="metadata" src={blobUrl} style={{ width: '100%' }} />
      <button type="button" className="btn-link" onClick={baixar}>⬇ baixar</button>
    </div>
  )
}
