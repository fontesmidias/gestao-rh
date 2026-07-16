import { useEffect, useRef, useState } from 'react'
import { candidato as api } from '../api.js'
import { DICAS, CODIGOS_ERRO_UPLOAD, NOMES_SUGESTAO, SECAO_SUGESTAO } from '../tooltips.js'
import Espera from '../Espera.jsx'
import { Cartao } from './CandidatoApp.jsx'
import CapturaDocumento from './Camera.jsx'

// Formato da moldura da câmera guiada por tipo de documento.
const FORMATO_DOC = {
  rg: 'cartao', cpf_doc: 'cartao', habilitacao_prof: 'cartao',
  titulo_eleitor_doc: 'cartao', reservista: 'cartao', cartao_vt: 'cartao',
  foto_3x4: 'retrato',
  comp_endereco: 'a4', comp_escolaridade: 'a4', diplomas: 'a4',
  laudo_pcd: 'a4', cert_casamento: 'a4', cert_nascimento_dep: 'a4',
  cartao_vacina_dep: 'a4', declaracao_escolar_dep: 'a4',
}
// Documentos que nascem digitais (PDF baixado de app/site): fotografar não
// faz sentido — o botão vai direto ao seletor de arquivo.
const DOCS_DIGITAIS = ['ctps_digital', 'pis_comprovante',
                       'nada_consta_eleitoral', 'nada_consta_criminal']

const STATUS = {
  pendente: { icone: '⬜', texto: 'Falta enviar' },
  enviado: { icone: '🕐', texto: 'Em análise pelo RH' },
  aprovado: { icone: '✅', texto: 'Aprovado' },
  rejeitado: { icone: '❌', texto: 'Precisa reenviar' },
  dispensado: { icone: '➖', texto: 'Dispensado' },
}

const MOTIVOS = {
  ilegivel: 'A imagem ficou ilegível — tente com mais luz.',
  doc_errado: 'O documento enviado não é o solicitado.',
  vencido: 'O documento está vencido — emita um novo.',
  incompleto: 'Faltou parte do documento (frente ou verso).',
  outro: 'Houve um problema com o arquivo.',
}

// Documento lido por OCR trouxe dados da ficha? Perguntamos ANTES de usar —
// consentimento explícito, e só campos ainda vazios são completados.
function BannerSugestoes({ token, slotId, sugestoes, aoFechar }) {
  const [aplicando, setAplicando] = useState(false)
  const [feito, setFeito] = useState(null)
  const nomes = Object.keys(sugestoes).map((c) => NOMES_SUGESTAO[c] || c)

  const aplicar = async () => {
    setAplicando(true)
    try {
      const ficha = await api.ficha(token)
      const porSecao = {}
      const aplicados = []
      for (const [campo, valor] of Object.entries(sugestoes)) {
        const sec = SECAO_SUGESTAO[campo]
        if (sec && !(ficha[sec]?.[campo])) {   // nunca sobrescreve o que já existe
          porSecao[sec] = { ...(porSecao[sec] || {}), [campo]: valor }
          aplicados.push(NOMES_SUGESTAO[campo] || campo)
        }
      }
      for (const [sec, dados] of Object.entries(porSecao)) {
        await api.salvarSecao(token, sec, dados)
      }
      setFeito(aplicados.length
        ? `Completamos: ${aplicados.join(', ')}. Confira na sua ficha — a responsabilidade pelas informações é sua.`
        : 'Esses campos já estavam preenchidos na sua ficha — nada foi alterado.')
    } catch {
      setFeito('Não conseguimos aplicar agora. Sem problema: os campos podem ser preenchidos na ficha.')
    } finally { setAplicando(false) }
  }

  return (
    <div className="slot-dica" role="status">
      {feito ? (
        <>✓ {feito} <button className="btn-link" onClick={aoFechar}>fechar</button></>
      ) : (
        <>
          👀 Lemos este documento e encontramos: <strong>{nomes.join(', ')}</strong>.
          Quer que a gente complete os campos ainda vazios da sua ficha com esses dados?
          Você confere tudo depois — nada é alterado sem a sua confirmação.
          <div style={{ marginTop: '.5rem', display: 'flex', gap: '.5rem' }}>
            <button className="btn-principal btn-mini" disabled={aplicando} onClick={aplicar}>
              {aplicando ? 'Aplicando…' : 'Sim, completar minha ficha'}</button>
            <button className="btn-secundario btn-mini" onClick={aoFechar}>Não, obrigado</button>
          </div>
        </>
      )}
    </div>
  )
}

export default function Checklist({ token, aoConcluir }) {
  const [check, setCheck] = useState(null)
  const [dicaAberta, setDicaAberta] = useState(null)
  const [enviando, setEnviando] = useState(null)
  const [erros, setErros] = useState({})
  const [sugestoes, setSugestoes] = useState(null) // {slotId, dados}
  const [avisos, setAvisos] = useState({})
  const [camera, setCamera] = useState(null) // {slotId, formato, titulo}
  const inputRef = useRef(null)
  const slotAtual = useRef(null)

  const recarregar = () => api.documentos(token).then(setCheck)
  useEffect(() => { recarregar() }, [token])

  if (!check) return <Cartao><p>Carregando…</p></Cartao>

  const escolher = (slot) => {
    slotAtual.current = slot.id
    if (DOCS_DIGITAIS.includes(slot.tipo)) {
      inputRef.current.click()   // PDF de app/site: direto ao arquivo
      return
    }
    setCamera({
      slotId: slot.id,
      formato: FORMATO_DOC[slot.tipo] || 'a4',
      titulo: (DICAS[slot.tipo] || {}).nome || 'Fotografar documento',
    })
  }

  // Validação preventiva: recusa na hora, sem gastar a internet do candidato
  // com um upload que o servidor rejeitaria.
  const EXTENSOES_OK = ['jpg', 'jpeg', 'png', 'heic', 'webp', 'bmp', 'pdf', 'doc', 'docx', 'odt', 'rtf']
  const MAX_MB = 50

  const validarAntesDeEnviar = (arquivo) => {
    if (arquivo.size === 0) return CODIGOS_ERRO_UPLOAD.arquivo_vazio
    if (arquivo.size > MAX_MB * 1024 * 1024) return CODIGOS_ERRO_UPLOAD.arquivo_grande_demais
    const ext = (arquivo.name.split('.').pop() || '').toLowerCase()
    if (!EXTENSOES_OK.includes(ext)) return CODIGOS_ERRO_UPLOAD.formato_nao_suportado
    return null
  }

  const aoSelecionar = (e) => {
    const arquivo = e.target.files[0]
    e.target.value = ''
    if (!arquivo) return
    enviar(slotAtual.current, arquivo)
  }

  const enviar = async (slotId, arquivo) => {
    setCamera(null)
    setErros((x) => ({ ...x, [slotId]: null }))
    const erroLocal = validarAntesDeEnviar(arquivo)
    if (erroLocal) {
      setErros((x) => ({ ...x, [slotId]: erroLocal }))
      return
    }
    setEnviando(slotId)
    setSugestoes((s) => (s?.slotId === slotId ? null : s))
    setAvisos((a) => ({ ...a, [slotId]: null }))
    try {
      const r = await api.enviarArquivo(token, slotId, arquivo)
      if (r.sugestoes && Object.keys(r.sugestoes).length) {
        setSugestoes({ slotId, dados: r.sugestoes })
      }
      // Mandou a CNH no lugar do RG? Acontece muito — avisa com carinho, sem travar.
      const slotTipo = check.slots.find((s) => s.id === slotId)?.tipo
      if (slotTipo === 'rg' && r.documento_detectado === 'cnh') {
        setAvisos((a) => ({ ...a, [slotId]:
          'Essa foto parece ser de uma CNH. Para este item precisamos do RG mesmo '
          + '(frente e verso) — a CNH pode ir no item "Habilitação profissional".' }))
      }
      await recarregar()
    } catch (err) {
      setErros((x) => ({
        ...x,
        [slotId]: CODIGOS_ERRO_UPLOAD[err.detail]
          || (err.status >= 500
              ? 'Tivemos um problema no servidor ao processar o arquivo. Tente de novo em instantes — se continuar, avise o RH.'
              : 'Não foi possível enviar. Verifique sua conexão e tente de novo.'),
      }))
    } finally { setEnviando(null) }
  }

  const podeConcluir = check.slots
    .filter((s) => s.obrigatorio)
    .every((s) => ['enviado', 'aprovado', 'dispensado'].includes(s.status))

  const concluir = async () => {
    await api.concluirEnvio(token)
    aoConcluir()
  }

  return (
    <Cartao>
      <input ref={inputRef} type="file" hidden accept="image/*,.pdf,.doc,.docx" onChange={aoSelecionar} />
      {camera && (
        <CapturaDocumento formato={camera.formato} titulo={camera.titulo}
                          aoCapturar={(arq) => enviar(camera.slotId, arq)}
                          aoArquivo={(arq) => enviar(camera.slotId, arq)}
                          aoFechar={() => setCamera(null)} />
      )}
      <div className="progresso">
        <div className="progresso-barra"
             style={{ width: `${(check.progresso.ok / Math.max(check.progresso.total, 1)) * 100}%` }} />
      </div>
      <p className="etapa-num">{check.progresso.ok} de {check.progresso.total} documentos obrigatórios ok</p>
      <h2>📄 Envie seus documentos</h2>
      <p className="etapa-num">Parte 3 de 4 — Documentos</p>
      <p className="explica">Toque em <strong>Enviar</strong> e fotografe ou escolha o arquivo
        (foto, PDF ou Word — nós convertemos). Não sabe onde conseguir um documento? Toque no
        <strong> ?</strong> do item. Ao terminar tudo, toque em
        <strong> CONCLUÍ MEU ENVIO</strong> — o RH será avisado e fará a conferência
        (parte 4 de 4). Você receberá retorno por e-mail.</p>

      {check.slots.map((s) => {
        const info = DICAS[s.tipo] || { nome: s.tipo, dica: '' }
        const st = STATUS[s.status]
        return (
          <div className={`slot ${s.status}`} key={s.id}>
            <div className="slot-linha">
              <span className="slot-icone">{st.icone}</span>
              <div className="slot-nome">
                <strong>{info.nome}</strong>
                {!s.obrigatorio && <em> (opcional)</em>}
                <div className="slot-status">{st.texto}</div>
                {s.status === 'rejeitado' && (
                  <div className="slot-motivo">{MOTIVOS[s.motivo_rejeicao] || ''} {s.motivo_rejeicao_obs || ''}</div>
                )}
              </div>
              <button className="btn-ajuda" title="Como conseguir este documento"
                      onClick={() => setDicaAberta(dicaAberta === s.id ? null : s.id)}>?</button>
              {['pendente', 'rejeitado', 'enviado'].includes(s.status) && (
                <button className="btn-principal btn-mini" disabled={enviando === s.id}
                        onClick={() => escolher(s)}>
                  {enviando === s.id ? 'Enviando…' : s.status === 'pendente' ? 'Enviar' : 'Reenviar'}
                </button>
              )}
            </div>
            {['enviado', 'aprovado'].includes(s.status) && (
              <div className="slot-arquivo-acoes">
                <a className="btn-link" target="_blank" rel="noreferrer"
                   href={api.meuArquivoUrl(token, s.id)}>👁 Ver o que enviei</a>
                {s.status === 'enviado' && (
                  <button className="btn-link" onClick={async () => {
                    if (!window.confirm('Excluir este arquivo? Você poderá enviar outro no lugar.')) return
                    try {
                      await api.excluirArquivo(token, s.id)
                      await recarregar()
                    } catch {
                      setErros((x) => ({ ...x, [s.id]: 'Não foi possível excluir agora. Tente de novo.' }))
                    }
                  }}>🗑 Excluir e enviar outro</button>
                )}
              </div>
            )}
            {enviando === s.id && <Espera texto="Enviando e conferindo seu documento…" />}
            {dicaAberta === s.id && <div className="slot-dica">💡 {info.dica}</div>}
            {erros[s.id] && <div className="alerta">{erros[s.id]}</div>}
            {avisos[s.id] && <div className="alerta">{avisos[s.id]}</div>}
            {sugestoes?.slotId === s.id && (
              <BannerSugestoes token={token} slotId={s.id} sugestoes={sugestoes.dados}
                               aoFechar={() => setSugestoes(null)} />
            )}
          </div>
        )
      })}

      <button className="btn-principal btn-concluir" disabled={!podeConcluir} onClick={concluir}>
        CONCLUÍ MEU ENVIO ✓
      </button>
      {!podeConcluir && (
        <p className="explica centro">O botão libera quando todos os documentos obrigatórios
          estiverem enviados.</p>
      )}
    </Cartao>
  )
}
