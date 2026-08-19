import { useState } from 'react'
import { authRH, buscar } from '../api.js'

// Baixar arquivo de rota AUTENTICADA (v2.98.4).
//
// ⚠️ **`<a href="/api/...">` NÃO funciona em rota protegida** — foi o defeito
// que o Bruno viu na tela: clicar em "Baixar transcrição" abria uma janela com
// `{"detail":"nao_autenticado"}`. O navegador segue o link com um GET LIMPO: ele
// não manda o header `Authorization`, que é onde vive o token do painel (o
// sistema não usa cookie de sessão). O link parece certo no JSX, o build passa,
// e só quebra no clique — a mesma família do `api.x()` inexistente (v2.73).
//
// O padrão da casa para arquivo autenticado é este: busca com o header, cria um
// `objectURL` e dispara o download com o nome certo. Já era o que o
// `VisualizadorArquivo` (v2.33), o `baixarDossie` e o `PlayerAudio` faziam —
// faltava um componente para os links soltos.

// O `filename="..."` do `Content-Disposition`, quando a rota o manda. Devolve
// `null` se não houver — aí vale o nome que a tela passou.
export function nomeDoCabecalho(resposta) {
  const cd = resposta.headers.get('content-disposition') || ''
  const m = /filename\*?=(?:UTF-8'')?"?([^";]+)"?/i.exec(cd)
  return m ? decodeURIComponent(m[1]).trim() : null
}

export default function BotaoBaixar({ url, nome, children, className = 'btn-secundario btn-mini' }) {
  const [ocupado, setOcupado] = useState(false)
  const [erro, setErro] = useState(null)

  const baixar = async () => {
    setOcupado(true); setErro(null)
    try {
      const r = await buscar(url, { headers: authRH() })
      if (!r.ok) throw new Error(r.status === 404 ? 'arquivo não encontrado' : `erro ${r.status}`)
      const blob = await r.blob()
      const objeto = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = objeto
      // O `Content-Disposition` não alcança o `objectURL` — sem `download` o
      // arquivo sairia com um UUID por nome. Mas o cabeçalho CHEGA na resposta,
      // e dá para lê-lo: assim o padrão `MATRÍCULA - NOME - DOCUMENTO` (v3.04)
      // vale sozinho, sem depender de cada tela repetir o nome certo no JSX —
      // que é como as quatro nomeações do projeto divergiram.
      a.download = nomeDoCabecalho(r) || nome
      a.click()
      // Revoga depois do clique: sem isso o arquivo inteiro fica na memória do
      // navegador até a aba fechar.
      setTimeout(() => URL.revokeObjectURL(objeto), 30_000)
    } catch (e) {
      setErro(e.message || 'não foi possível baixar')
    } finally { setOcupado(false) }
  }

  return (
    <>
      <button type="button" className={className} disabled={ocupado} onClick={baixar}>
        {ocupado ? 'Baixando…' : children}
      </button>
      {erro && <span className="alerta" style={{ padding: '.2rem .5rem' }}>{erro}</span>}
    </>
  )
}
