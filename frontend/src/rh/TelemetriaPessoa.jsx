import { useEffect, useState } from 'react'
import { rh as api } from '../api.js'
import { fmtDataHora } from '../fmt.js'

// Telemetria de UMA pessoa, dentro da ficha dela (v2.24).
//
// É o pedido literal do Bruno: "telemetria individualizada nas páginas dos
// candidatos, do banco de talentos, das admissões, colaboradores". O caso de
// uso é concreto e frequente — a pessoa liga dizendo "não consigo", e até aqui
// a única resposta possível era pedir que ela descrevesse a tela. Agora dá para
// abrir a ficha e ver o que aconteceu no aparelho dela.
//
// Recolhido por padrão: é diagnóstico, não rotina. A ficha já é longa e isto
// só importa quando algo deu errado.

const ICONE = { erro: '🔴', friccao: '🟠', jornada: '🔵', desempenho: '🟣' }

// Tradução para quem atende o telefone. O nome técnico do evento não ajuda
// ninguém no meio de uma ligação com a pessoa esperando.
const EM_PORTUGUES = {
  erro_render: 'A tela quebrou',
  link_invalido: 'Abriu um link vencido ou inválido',
  erro_ao_abrir: 'Erro ao abrir a página',
  documento_reenviado: 'Reenviou um documento',
  falha_no_envio: 'Falhou ao enviar um documento',
  arquivo_recusado_no_aparelho: 'O arquivo foi recusado antes de enviar',
  etapa_aberta: 'Abriu a etapa',
  etapa_concluida: 'Saiu da etapa',
  upload_documento: 'Envio de documento demorado',
  talento_passo: 'Abriu o passo do formulário',
  talento_passo_saiu: 'Saiu do passo do formulário',
  talento_bloqueado: 'Formulário não deixou avançar',
}

export default function TelemetriaPessoa({ candidatoId, talentoId }) {
  const [eventos, setEventos] = useState(null)
  const [aberto, setAberto] = useState(false)

  useEffect(() => {
    if (!aberto || eventos !== null) return
    api.telemetriaPessoa({ candidato_id: candidatoId, talento_id: talentoId })
      .then(setEventos).catch(() => setEventos([]))
  }, [aberto, candidatoId, talentoId])

  const erros = (eventos || []).filter((e) => e.tipo === 'erro')
  const friccoes = (eventos || []).filter((e) => e.tipo === 'friccao')

  return (
    <details className="rh-card" onToggle={(e) => setAberto(e.target.open)}>
      <summary>
        <strong>📈 O que aconteceu na tela desta pessoa</strong>
        {eventos && (erros.length > 0 || friccoes.length > 0) && (
          <span className="chip" style={{ '--chip-cor': erros.length ? 'var(--perigo)' : 'var(--atencao)' }}>
            {erros.length ? `${erros.length} erro(s)` : `${friccoes.length} travamento(s)`}
          </span>
        )}
      </summary>

      {eventos === null ? <p>Carregando…</p> : eventos.length === 0 ? (
        <p className="explica">
          Nenhum registro para esta pessoa. Ou ela ainda não acessou depois da
          atualização que ativou a telemetria, ou usou o sistema sem nenhum
          problema digno de registro.
        </p>
      ) : (
        <>
          <p className="explica">
            Do mais recente para o mais antigo. Serve para responder
            &ldquo;não consigo enviar meus documentos&rdquo; com fato, e não com
            suposição.
          </p>
          <table className="rh-tabela">
            <thead><tr>
              <th>Quando</th><th>O que aconteceu</th><th>Onde</th><th>Detalhe</th>
            </tr></thead>
            <tbody>
              {eventos.map((e) => (
                <tr key={e.id}>
                  <td>{fmtDataHora(e.quando)}</td>
                  <td>{ICONE[e.tipo] || ''} {EM_PORTUGUES[e.evento] || e.evento}</td>
                  <td className="dash-quebra">{e.pagina || '—'}</td>
                  <td className="dash-quebra">
                    {e.detalhe?.mensagem && <code>{e.detalhe.mensagem}</code>}
                    {e.detalhe?.tipo && <span>documento: {e.detalhe.tipo}</span>}
                    {e.duracao_ms > 0 && <span> {(e.duracao_ms / 1000).toFixed(1)}s</span>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}
    </details>
  )
}
