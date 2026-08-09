import React from 'react'
import ReactDOM from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import App from './App.jsx'
import ErroFatal from './ErroFatal.jsx'
import { instalarCapturaGlobal } from './telemetria.js'
// As DUAS famílias embutidas (v2.85). Yu Gothic, o padrão, é PROPRIETÁRIA da
// Microsoft e não pode ser empacotada — quem não a tem instalada (Android,
// iPhone, Linux: a maior parte do público do wizard) cai na Noto Sans JP, que é
// livre, tem a mesma origem tipográfica e pesa ~13KB no subconjunto latino.
// A Outfit continua porque segue escolhível no painel.
import '@fontsource/noto-sans-jp/400.css'
import '@fontsource/noto-sans-jp/600.css'
import '@fontsource/noto-sans-jp/700.css'
import '@fontsource/noto-sans-jp/800.css'
import '@fontsource/outfit/400.css'
import '@fontsource/outfit/600.css'
import '@fontsource/outfit/700.css'
import '@fontsource/outfit/800.css'
import './styles.css'

// Aplica o tema antes do primeiro render (sem "piscada"): escolha salva ou o
// modo do aparelho.
document.documentElement.dataset.tema =
  localStorage.getItem('tema')
  || (window.matchMedia('(prefers-color-scheme: dark)').matches ? 'escuro' : 'claro')

// ---------------------------------------------------------------------------
// Fonte configurável (v2.85)
// ---------------------------------------------------------------------------
// Aplicada ANTES de perguntar ao servidor, a partir do que ficou guardado da
// última visita: a resposta leva uns 100ms e, sem isso, toda tela abriria com a
// fonte padrão e trocaria na cara de quem está lendo. O `localStorage` é cache,
// não fonte da verdade — quem manda é o servidor, e a resposta dele sobrescreve.
const _fonteSalva = localStorage.getItem('marca_fonte')
if (_fonteSalva) document.documentElement.style.setProperty('--fonte', _fonteSalva)

fetch('/api/marca/aparencia')
  .then((r) => (r.ok ? r.json() : null))
  .then((d) => {
    if (!d?.fonte) return
    document.documentElement.style.setProperty('--fonte', d.fonte)
    localStorage.setItem('marca_fonte', d.fonte)
  })
  // Falha aqui NÃO pode quebrar nada: sem resposta vale o `--fonte` do CSS, que
  // já é uma pilha completa. Fonte é aparência — nunca motivo para tela morta.
  .catch(() => {})

// ---------------------------------------------------------------------------
// Aba aberta durante um deploy: recarrega uma vez, sozinha
// ---------------------------------------------------------------------------
// Incidente de produção 2026-07-29 — dois candidatos com a TELA EM BRANCO no
// meio do envio de documentos, sem erro nenhum nos logs.
//
// Cada build gera assets com hash novo (index-C1OewSkj.js) e APAGA os
// anteriores. O candidato deixa a página aberta no celular — comum aqui, porque
// ele sai do sistema para tirar foto do documento e volta. Se um deploy
// acontece nesse meio-tempo, a aba continua pedindo o arquivo que não existe
// mais. Antes disso, o nginx respondia 200 com o index.html no lugar do JS, o
// navegador tentava executar HTML como script e a aplicação morria calada.
//
// O nginx agora devolve 404 honesto (frontend/nginx.conf) e aqui fechamos o
// ciclo: falha de carregamento de módulo = versão velha, então recarrega
// buscando o index.html novo (que é `no-store`).
//
// A trava no sessionStorage é obrigatória: sem ela, uma falha PERMANENTE viraria
// recarregamento infinito — trocaríamos a tela branca por um pisca-pisca, que é
// pior. Uma tentativa; se não resolveu, o ErroFatal assume e explica.
const CHAVE_RECARGA = 'recarga-por-versao'

function recuperarDeVersaoAntiga() {
  if (sessionStorage.getItem(CHAVE_RECARGA)) return false
  sessionStorage.setItem(CHAVE_RECARGA, '1')
  window.location.reload()
  return true
}

// Import de módulo que falhou (chunk apagado por deploy). O texto varia por
// navegador — casamos os formatos conhecidos de Chrome, Firefox e Safari.
const ehFalhaDeChunk = (msg = '') =>
  /Failed to fetch dynamically imported module|Importing a module script failed|error loading dynamically imported module|Unexpected token '<'/i
    .test(String(msg))

window.addEventListener('error', (e) => {
  if (ehFalhaDeChunk(e?.message)) recuperarDeVersaoAntiga()
})
window.addEventListener('unhandledrejection', (e) => {
  if (ehFalhaDeChunk(e?.reason?.message)) recuperarDeVersaoAntiga()
})

// Chegou até aqui é porque o bundle atual carregou. A trava só é liberada
// depois de um tempo de navegação saudável — e NÃO na hora.
//
// O motivo: chunks carregados sob demanda (o visualizador de PDF, por exemplo)
// só são pedidos quando a pessoa clica. Se a trava fosse limpa aqui, uma falha
// permanente nesse chunk recarregaria a página a cada clique, para sempre.
// Trinta segundos separam "recarreguei e o problema continua" de "estou usando
// o sistema há um tempo e agora um deploy novo aconteceu".
setTimeout(() => sessionStorage.removeItem(CHAVE_RECARGA), 30_000)

// Captura erros que nenhum ErrorBoundary alcança (fora do React, promessa
// solta). Instalada ANTES do render: se a própria montagem quebrar, o registro
// ainda sai — que é exatamente o caso do incidente de 2026-07-29.
instalarCapturaGlobal()

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <ErroFatal>
      <BrowserRouter>
        <App />
      </BrowserRouter>
    </ErroFatal>
  </React.StrictMode>,
)
