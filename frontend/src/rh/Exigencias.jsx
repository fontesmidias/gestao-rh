import { useEffect, useState } from 'react'
import { rh as api } from '../api.js'

/**
 * O que é obrigatório na admissão (v2.80).
 *
 * Pedido do Bruno: *"por padrão vir marcado os campos obrigatórios para todos
 * (lógico, aqueles que têm que ser obrigatórios), mas customizável por
 * candidato, pelo pessoal do RH. Daí ter um padrão geral lá em configurações"*.
 *
 * O MESMO componente serve os dois lugares — muda só quem responde:
 *
 *   · em Configurações (`candidatoId` ausente) → define o padrão da CASA;
 *   · na ficha da pessoa (`candidatoId`)       → a EXCEÇÃO daquela pessoa.
 *
 * Um componente só porque a tela é a mesma: lista de itens com um interruptor.
 * Duplicar faria as duas divergirem na primeira mudança — e a diferença real
 * (quem manda no PUT, e se o motivo é exigido) cabe em duas condições.
 *
 * A ORIGEM de cada item é o que a tela mostra além do check: sem ela o RH não
 * distingue "o padrão é assim" de "alguém decidiu isto para esta pessoa".
 */

const ORIGEM_ROTULO = {
  fabrica: null,                        // o padrão: não precisa dizer nada
  casa: 'padrão da casa',
  pessoa: 'decidido para esta pessoa',
  sistema: 'exigido pelo sistema',
}

export default function Exigencias({ candidatoId, setMsg }) {
  const [dados, setDados] = useState(null)
  const [erro, setErro] = useState(null)
  const [salvando, setSalvando] = useState(null)   // chave em curso

  const carregar = () => {
    setErro(null)
    const p = candidatoId ? api.exigenciasDoCandidato(candidatoId) : api.exigenciasPadrao()
    return p.then(setDados)
      .catch((e) => setErro(e.detail || e.message || 'Falha ao carregar.'))
  }
  useEffect(() => { carregar() }, [candidatoId])

  const alternar = async (grupo, item) => {
    if (item.travado) return
    const novo = !item.obrigatorio
    // Na FICHA o motivo é obrigatório — é ele que explica, meses depois, por
    // que esta pessoa não entregou o que todo mundo entrega. No padrão da casa
    // não se pede: a mudança vale para todos e fica na auditoria com o autor.
    let motivo = ''
    if (candidatoId) {
      motivo = window.prompt(
        `${novo ? 'Passar a exigir' : 'Dispensar'} "${item.rotulo}" desta pessoa.\n\n`
        + 'Por quê? (fica registrado com o seu nome)', '')
      if (motivo === null) return               // cancelou
      if (!motivo.trim()) {
        setMsg?.({ tipo: 'erro', texto: 'O motivo é obrigatório.' })
        return
      }
    }
    setSalvando(item.chave)
    try {
      if (candidatoId) {
        await api.ajustarExigencia(candidatoId, grupo, item.chave, novo, motivo.trim())
      } else {
        await api.salvarExigenciaPadrao(grupo, item.chave, novo)
      }
      await carregar()
      setMsg?.({ tipo: 'ok', texto: `${item.rotulo}: ${novo ? 'passou a ser exigido' : 'dispensado'}.` })
    } catch (e) {
      setMsg?.({ tipo: 'erro', texto: `Não foi possível salvar (${e.detail || e.message}).` })
    } finally { setSalvando(null) }
  }

  // Desfazer só aparece onde há o que desfazer: item que veio de fábrica não
  // tem exceção a remover, e um botão que não faz nada é ruído (v2.54).
  const desfazer = async (grupo, item) => {
    setSalvando(item.chave)
    try {
      if (candidatoId) {
        await api.ajustarExigencia(candidatoId, grupo, item.chave, null, '')
      } else {
        await api.salvarExigenciaPadrao(grupo, item.chave, null)
      }
      await carregar()
      setMsg?.({ tipo: 'ok', texto: `${item.rotulo} voltou ao padrão.` })
    } catch (e) {
      setMsg?.({ tipo: 'erro', texto: `Não foi possível desfazer (${e.detail || e.message}).` })
    } finally { setSalvando(null) }
  }

  if (erro) {
    return (
      <div className="rh-card">
        <p className="alerta">Não foi possível carregar: {erro}</p>
        <button className="btn-principal btn-mini" onClick={carregar}>Tentar de novo</button>
      </div>
    )
  }
  if (!dados) return <div className="rh-card"><p>Carregando…</p></div>

  const bloco = (titulo, grupo, itens) => (
    <div className="rh-card">
      <strong>{titulo}</strong>
      <ul className="fichas-status" style={{ marginTop: '.4rem' }}>
        {itens.map((i) => {
          // A origem que MERECE ser mostrada: `fabrica` é o padrão e não
          // informa nada. Na tela do padrão da casa, "casa" também é o esperado
          // — o que se destaca é o que fugiu do normal.
          const origem = ORIGEM_ROTULO[i.origem]
          const destacar = i.origem === 'pessoa' || (!candidatoId && i.origem === 'casa')
          return (
            <li key={i.chave}>
              <label className="campo-check" style={{ margin: 0 }}>
                <input type="checkbox" checked={i.obrigatorio} disabled={i.travado || salvando === i.chave}
                       onChange={() => alternar(grupo, i)} />
                {i.rotulo}
              </label>
              {i.travado && (
                <span className="chip" title="Sem isto a admissão não se completa: base legal (LGPD), código de assinatura por e-mail e casamento do CPF no resto do sistema.">
                  exigido pelo sistema</span>
              )}
              {!i.travado && destacar && origem && (
                <>
                  {' '}<span className="chip" style={{ '--chip-cor': 'var(--ambar)' }}>{origem}</span>
                  {' '}<button className="btn-link btn-mini" disabled={salvando === i.chave}
                               onClick={() => desfazer(grupo, i)}>voltar ao padrão</button>
                </>
              )}
            </li>
          )
        })}
      </ul>
    </div>
  )

  return (
    <>
      <p className="explica">
        {candidatoId
          ? 'Vale só para esta pessoa. O que estiver marcado aqui é o que ela precisa entregar para concluir a admissão.'
          : 'Vale para TODOS os candidatos daqui em diante. Quem já concluiu a admissão não é afetado — e cada pessoa pode ter exceção própria, na ficha dela.'}
      </p>
      {bloco('📎 Documentos', 'documentos', dados.documentos)}
      {bloco('📝 Campos da ficha', 'campos', dados.campos)}
    </>
  )
}
