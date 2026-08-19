import { useEffect, useState } from 'react'
import { candidato as api } from '../api.js'
import { Cartao } from './CandidatoApp.jsx'
import Espera from '../Espera.jsx'

const NOMES = {
  ficha_cadastro: 'Ficha Cadastral do Colaborador',
  ficha_emergencia: 'Ficha de Emergência do Colaborador',
  termo_vt: 'Termo de Opção pelo Vale-Transporte',
}

// fase: revisar → enviando → codigo → assinando → concluido
export default function Assinatura({ token, email, aoConcluir, aoVoltarAoFormulario }) {
  const [fichas, setFichas] = useState(null)
  const [fase, setFase] = useState('revisar')
  const [emailAtual, setEmailAtual] = useState(email || '')
  const [editandoEmail, setEditandoEmail] = useState(false)
  const [novoEmail, setNovoEmail] = useState(email || '')
  const [codigo, setCodigo] = useState('')
  const [msg, setMsg] = useState(null)
  const [vtOptante, setVtOptante] = useState(null) // opção atual pelo Vale-Transporte
  const [trocandoVt, setTrocandoVt] = useState(false)

  // O termo de VT só entra na lista de quem tem VT a assinar; a confirmação
  // antes do botão depende disso (não faz sentido perguntar a quem não assina).
  //
  // `fichas` nasce null e só é preenchido pelo useEffect — mas esta linha roda
  // no PRIMEIRO render, antes disso. Sem o `|| []`, `null.some(...)` lançava
  // TypeError e apagava a tela inteira do candidato (incidente de produção
  // 2026-07-29, introduzido na v2.05). O guard `if (!fichas)` que protege o
  // resto do componente está lá embaixo, perto do return — tarde demais para
  // qualquer coisa calculada aqui em cima.
  const temTermoVt = (fichas || []).some((f) => f.documento === 'termo_vt' && !f.assinado)

  const recarregar = () => api.fichas(token).then((r) => {
    setFichas(r.fichas)
    return r.fichas
  })
  useEffect(() => { recarregar() }, [token])
  // Opção atual pelo VT — para o colaborador poder trocar antes de assinar.
  useEffect(() => {
    api.ficha(token).then((f) => setVtOptante(f?.vt?.optante ?? null)).catch(() => {})
  }, [token])

  const trocarVt = async (novo) => {
    setMsg(null); setTrocandoVt(true)
    try {
      await api.trocarOpcaoVt(token, novo)
      setVtOptante(novo)
      setMsg({ tipo: 'ok', texto: novo
        ? 'Você agora OPTA por receber o Vale-Transporte. Confira o termo antes de assinar.'
        : 'Você agora NÃO opta pelo Vale-Transporte. Confira o termo antes de assinar.' })
      await recarregar()
    } catch (e) {
      setMsg({ tipo: 'erro', texto: e.detail === 'termo_vt_ja_assinado'
        ? 'O Termo de VT já foi assinado e não pode mais ser alterado por aqui. Fale com o RH.'
        : 'Não foi possível trocar a opção agora. Tente de novo.' })
    } finally { setTrocandoVt(false) }
  }

  if (!fichas) return <Cartao><p>Carregando…</p></Cartao>

  const pedirCodigo = async () => {
    setMsg(null)
    setFase('enviando')
    try {
      await api.solicitarCodigoUnico(token)
      setCodigo('')
      setFase('codigo')
      setMsg({ tipo: 'ok', texto: `O código foi enviado para ${emailAtual}. Verifique a sua caixa de entrada e, se necessário, a caixa de spam/lixo eletrônico. O código é válido por 10 minutos.` })
    } catch (e) {
      setFase('revisar')
      // O `catch` era CEGO e culpava a conexão em qualquer erro (feedback
      // 2026-07-29). No 429 — cota de 5 pedidos por 15 min — isso é pior que
      // inútil: convida a tentar de novo na hora, que reabastece a cota e
      // prolonga o bloqueio. O último código enviado CONTINUA valendo, e é
      // isso que a pessoa precisa ouvir.
      setMsg({ tipo: 'erro', texto: e.status === 429
        ? 'Você pediu o código várias vezes seguidas. Aguarde 15 minutos — ou '
          + 'use o ÚLTIMO código que chegou no seu e-mail, se ainda estiver '
          + 'dentro dos 10 minutos de validade.'
        : e.offline
          ? 'Sem conexão. Confira a internet e tente novamente.'
          : 'Não foi possível enviar o código agora. Tente novamente em instantes.' })
    }
  }

  const confirmar = async () => {
    setFase('assinando')
    setMsg(null)
    try {
      await api.assinarTodos(token, codigo)
      await recarregar()
      setFase('concluido')
      setMsg({ tipo: 'ok', texto: 'Documentos assinados com sucesso. Enviamos as vias assinadas para o seu e-mail. Toque em cada documento abaixo para visualizá-lo.' })
    } catch (e) {
      setFase('codigo')
      const textos = {
        // "confira o e-mail" fazia a pessoa reconferir um código que estava
        // certo, quando o problema era ser de um e-mail antigo (2026-07-29).
        codigo_incorreto: 'Código incorreto. Use o do e-mail MAIS RECENTE — se você '
          + 'pediu o código mais de uma vez, só o último vale.',
        codigo_expirado: 'O código expirou (validade de 10 minutos). Toque em '
          + '"Assinar os documentos" para receber um novo.',
        tentativas_excedidas: 'Número de tentativas excedido. Toque em "Assinar os '
          + 'documentos" para receber um código novo.',
      }
      setMsg({ tipo: 'erro', texto: textos[e.detail]
        || (e.status === 429
          ? 'Muitas tentativas seguidas. Aguarde alguns minutos e tente de novo.'
          : 'Não foi possível concluir a assinatura. Tente novamente.') })
    }
  }

  const todasAssinadas = fichas.every((f) => f.assinado)

  return (
    <Cartao>
      <p className="etapa-num">Parte 2 de 4 — Assinatura</p>
      <h2>✍️ Assinatura dos documentos admissionais</h2>
      <p className="explica">Seus dados foram registrados com sucesso. Agora,
        <strong> esta etapa é obrigatória e deve ser concluída em seguida</strong>: a sua
        admissão somente prossegue após a assinatura dos documentos abaixo. Depois dela,
        restarão duas partes: <strong>envio dos seus documentos</strong> (fotos) e a
        <strong> conferência pelo RH</strong>.</p>

      <div className="lista-fichas">
        {fichas.map(({ documento, assinado, titulo }) => (
          <div className={`ficha-item ${assinado ? 'ok' : ''}`} key={documento}>
            <div>
              <strong>{assinado ? '✅' : '📄'} {titulo || NOMES[documento]}</strong>
              <a className="link-ver" href={api.previewUrl(token, documento)}
                 target="_blank" rel="noreferrer">
                {assinado ? 'ver documento assinado' : 'conferir o documento antes de assinar'}
              </a>
              {/* A troca vive no bloco de confirmação, logo acima do botão de
                  assinar — aqui fica só o estado, para o card não mentir. */}
              {documento === 'termo_vt' && !assinado && vtOptante !== null && (
                <div className="vt-opcao">
                  Sua opção: <strong>{vtOptante ? 'RECEBER o VT' : 'NÃO receber o VT'}</strong>
                </div>
              )}
            </div>
          </div>
        ))}
      </div>

      {/* Confirmação do VT ANTES do botão de assinar (feedback 2026-07-28: gente
          assinando o termo com a opção errada). Antes essa troca só existia
          dentro do card do termo, no meio da lista — quem não reparasse assinava
          e não dava mais para mudar (409). O termo vira desconto de até 6% em
          folha, então o erro custa dinheiro do salário da pessoa. */}
      {!todasAssinadas && (fase === 'revisar' || fase === 'enviando')
        && temTermoVt && vtOptante !== null && (
        <div className="aviso-codigo">
          <strong>Confirme sua opção pelo Vale-Transporte:</strong>
          <div className="email-confirma">
            <code>{vtOptante ? 'QUERO receber o VT' : 'NÃO quero o VT'}</code>
            <button className="btn-link" disabled={trocandoVt}
                    onClick={() => trocarVt(!vtOptante)}>
              {trocandoVt ? 'trocando…' : `trocar para ${vtOptante ? 'NÃO querer' : 'QUERER'}`}
            </button>
          </div>
          {vtOptante
            ? 'Optando pelo VT, a empresa desconta até 6% do seu salário básico (nunca '
              + 'mais do que o transporte custa).'
            : 'Sem o VT, nada é descontado do seu salário e o transporte fica por sua conta.'}
          {' '}<strong>Depois de assinar, essa opção não pode mais ser trocada por aqui.</strong>
        </div>
      )}

      {!todasAssinadas && (fase === 'revisar' || fase === 'enviando') && (
        <>
          <div className="aviso-codigo">
            <strong>Como funciona:</strong> confira os documentos acima. Ao tocar em
            <strong> Assinar os documentos</strong>, enviaremos <strong>um único código de
            6 números</strong> para o e-mail:
            {!editandoEmail ? (
              <div className="email-confirma">
                <code>{emailAtual}</code>
                <button className="btn-link" onClick={() => setEditandoEmail(true)}>
                  e-mail incorreto? Corrigir</button>
              </div>
            ) : (
              <div className="email-confirma">
                <input type="email" value={novoEmail}
                       onChange={(e) => setNovoEmail(e.target.value)} />
                <button className="btn-secundario btn-mini" onClick={async () => {
                  const limpo = novoEmail.trim()
                  await api.salvarSecao(token, 'pessoais', { email: limpo })
                  setEmailAtual(limpo)
                  setEditandoEmail(false)
                  setMsg({ tipo: 'ok', texto: `E-mail atualizado para ${limpo}.` })
                }}>Salvar e-mail</button>
              </div>
            )}
            Com esse único código, todos os documentos listados são assinados de uma só vez
            (assinatura eletrônica — Lei nº 14.063/2020).
          </div>
          <button className="btn-principal" disabled={fase === 'enviando'} onClick={pedirCodigo}>
            {fase === 'enviando' ? '📨 Enviando o código para o seu e-mail…' : 'Assinar os documentos'}
          </button>
          {/* Voltar a corrigir os dados (v2.88, feedback de campo: "estava
              escrevendo o endereço e não conseguiu mais voltar para editar").
              O backend SEMPRE permitiu — `_candidato_do_token` só barra
              `expurgado` e `aprovado` —, quem não oferecia o caminho era a
              tela: depois de confirmar, o app ia para cá e não havia porta de
              volta. Fica ao lado do botão de assinar porque é AQUI que a
              pessoa relê o que preencheu e percebe o erro; um link no rodapé
              seria achado depois de ela já ter assinado.
              Só aparece antes da assinatura: documento assinado é peça de
              prova, e corrigir dado depois disso é outra conversa (o RH
              reabre). */}
          {/* `btn-secundario`, não `btn-link` (v3.08): o relato que chegou foi
              *"ela vê os dados das fichas e não consegue editar, o RH tem que
              editar manualmente"* — e o backend sempre permitiu. O botão estava
              aqui desde a v2.88, mas como link de texto discreto embaixo do
              botão verde; quem não o vê conclui que não dá para corrigir e
              chama o RH. Botão que existe e não é achado não está entregue
              (v2.75). */}
          {aoVoltarAoFormulario && (
            <button className="btn-secundario" onClick={aoVoltarAoFormulario}
                    style={{ display: 'block', margin: '.8rem auto 0' }}>
              ✏️ Preciso corrigir meus dados antes de assinar
            </button>
          )}
          {/* REASSINATURA: aqui não há formulário para voltar — os documentos
              foram reabertos por uma ação do RH (edição da ficha ou troca de
              posto/cargo/salário), e a ficha de admissão está fechada. Mas a
              pessoa continua podendo ver um dado errado, e antes não havia NADA
              nesta tela dizendo o que fazer: ela assinava mesmo discordando, ou
              parava e ligava. Dizer para quem falar é a saída que existe. */}
          {!aoVoltarAoFormulario && (
            <p className="explica" style={{ textAlign: 'center', marginTop: '.8rem' }}>
              Encontrou algo errado? <strong>Não assine</strong> — fale com o RH
              antes, porque estes documentos foram atualizados por eles.
            </p>
          )}
          {fase === 'enviando' && <Espera texto="Preparando e enviando seu código…" />}
        </>
      )}

      {(fase === 'codigo' || fase === 'assinando') && (
        <div className="aviso-codigo">
          <strong>Digite o código de 6 números recebido por e-mail:</strong>
          <div className="otp" style={{ marginTop: '.6rem' }}>
            <input inputMode="numeric" maxLength={6} placeholder="000000" value={codigo}
                   autoFocus onChange={(e) => setCodigo(e.target.value.replace(/\D/g, ''))} />
            <button className="btn-principal btn-mini"
                    disabled={codigo.length !== 6 || fase === 'assinando'} onClick={confirmar}>
              {fase === 'assinando' ? 'Assinando…' : 'Confirmar assinatura'}
            </button>
            <button className="btn-link" disabled={fase === 'assinando'} onClick={pedirCodigo}>
              Não recebeu? Reenviar código</button>
          </div>
          {fase === 'assinando' && <Espera texto="Assinando os documentos e gerando suas vias…" />}
        </div>
      )}

      {msg && <div className={msg.tipo === 'erro' ? 'alerta' : 'sucesso'}>{msg.texto}</div>}

      {todasAssinadas && (
        <>
          <div className="aviso-codigo" style={{ marginTop: '1rem' }}>
            <strong>Próxima etapa (parte 3 de 4):</strong> enviar fotos ou arquivos dos seus
            documentos pessoais (RG, CPF, comprovantes…). Uma lista mostrará exatamente o que
            é necessário, um por um, com dicas de onde conseguir cada documento.
          </div>
          <button className="btn-principal btn-concluir" onClick={aoConcluir}>
            Continuar para o envio dos documentos →
          </button>
        </>
      )}
    </Cartao>
  )
}
