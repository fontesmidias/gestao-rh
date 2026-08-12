import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { rh as api } from '../api.js'
import SelectBusca from '../SelectBusca.jsx'
import VisualizadorArquivo from '../VisualizadorArquivo.jsx'
import GravacaoEntrevista from './GravacaoEntrevista.jsx'
import { fmtDataHora } from '../fmt.js'

// A ficha da entrevista — DUAS naturezas, um componente.
//
// Todo o texto do instrumento (competências, âncoras, escalas, perguntas de
// triagem) vem por prop `form`, carregada de `GET /rh/entrevistas/formulario`.
// **O front não duplica nada**: mudar uma âncora é mexer só em
// `services/entrevistas.py`, e esta tela acompanha sozinha.
//
// Não existe campo de "outras perguntas" DE PROPÓSITO (§ 6): campo de pergunta
// livre é risco jurídico (Lei 9.029/95 veda perguntar sobre situação familiar,
// filhos, gravidez…), roteiro pré-aprovado é defesa da empresa. O `observacao`
// é livre; o ROTEIRO não.
//
// COMPOSIÇÃO (v2.65): esta ficha é um formulário longo com escala de nota, e a
// referência canônica desse papel no projeto é o `FormularioAvaliacao.jsx` (o
// formulário da cartilha). Ela reusa as MESMAS primitivas: um `.rh-conferencia`
// só (não N cards empilhados), `.rh-conferencia-corpo` para as duas colunas,
// `.chips-escolha`/`.chip-escolha` para a escala — todas as opções à vista, um
// clique — e `.rh-conferencia-acoes` para os botões. A v2.64 passou no
// `test_design_system.py` e mesmo assim não parecia com o resto do sistema: o
// teste cobre VOCABULÁRIO (classe existe? token existe?), não COMPOSIÇÃO (qual
// primitiva serve a qual papel).

export default function FichaEntrevista({ entrevistaId, form, aoMudar }) {
  const [e, setE] = useState(null)
  const [campos, setCampos] = useState(null)
  const [salvando, setSalvando] = useState(false)
  const [erroCarga, setErroCarga] = useState(null)
  // ⚠️ O hook fica AQUI, acima do `if (!e) return` — chamar `useNavigate` depois
  // de um return condicional quebra as regras dos hooks (a ordem muda entre
  // renders). Mesma família do guard de estado nulo da v2.05.
  const navegar = useNavigate()

  // Atalho para o CRUD de roteiros (v2.75, pergunta do Bruno: *"cadê a parte
  // onde posso fazer CRUD de mais roteiros?"*). A tela sempre existiu, em
  // Configurações → 🗣️ Roteiros de entrevista, mas nada apontava para ela — e é
  // AQUI, conduzindo a entrevista, que se percebe que o roteiro precisa mudar.
  // A aba de Config vem do `localStorage`, não da URL: sem gravar a preferência
  // ANTES de navegar, o atalho abriria a última aba usada e pareceria não ter
  // funcionado.
  const irParaRoteiros = () => {
    localStorage.setItem('rh_config_aba', 'roteiros')
    navegar('/rh/config')
  }
  // Mensagem LOCAL: a ficha abre na linha, longe do topo — a confirmação tem
  // que nascer perto do botão que a gerou (regra da v1.96/v2.47).
  const [msg, setMsg] = useState(null)

  const carregar = () => {
    setErroCarga(null)
    return api.entrevista(entrevistaId).then((r) => {
      setE(r)
      setCampos({
        triagem: r.triagem || {},
        triagem_desfecho: r.triagem_desfecho || '',
        competencias: r.competencias || {},
        justificativas: r.justificativas || {},
        variante: r.variante || 'comportamental',
        recomendacao: r.recomendacao || '',
        recomendacao_motivo: r.recomendacao_motivo || '',
        observacao: r.observacao || '',
      })
    }).catch((err) => setErroCarga(err.detail || err.message || 'Falha ao carregar.'))
  }
  useEffect(() => { carregar() }, [entrevistaId])

  if (erroCarga) {
    return (
      <div className="rh-conferencia">
        <p className="alerta">Não foi possível carregar: {erroCarga}</p>
        <button className="btn-principal btn-mini" onClick={carregar}>Tentar de novo</button>
      </div>
    )
  }
  // Guard ANTES de qualquer uso dos estados nulos.
  if (!e || !campos) return <div className="rh-conferencia"><p>Carregando…</p></div>

  const eTriagem = e.tipo === 'triagem'
  const encerrada = e.status === 'arquivada'
  const marcar = (grupo, chave, valor) =>
    setCampos({ ...campos, [grupo]: { ...campos[grupo], [chave]: valor } })

  const montarPayload = (concluir) => ({
    ...(eTriagem
      ? { triagem: campos.triagem, triagem_desfecho: campos.triagem_desfecho || null }
      : { competencias: campos.competencias, justificativas: campos.justificativas,
          variante: campos.variante,
          recomendacao: campos.recomendacao || null,
          recomendacao_motivo: campos.recomendacao_motivo || null }),
    observacao: campos.observacao,
    concluir,
  })

  const salvar = async (concluir) => {
    setSalvando(true)
    setMsg(null)
    try {
      await api.salvarEntrevista(entrevistaId, montarPayload(concluir))
      await carregar()
      // `aoMudar` recarrega a LISTA. Dentro do try, mas depois do carregar:
      // se a recarga falhar, não se reporta falha de algo que salvou.
      if (aoMudar) await aoMudar()
      setMsg({ texto: concluir ? 'Entrevista concluída e registrada na memória da pessoa.' : 'Rascunho salvo.' })
    } catch (err) {
      // O backend devolve `detail.erros` NOMEANDO o que falta ("Justifique a
      // nota de 'Trato com público'"). Perder essa lista faria a tela dizer só
      // "não deu" — que é o defeito que o 422 detalhado veio consertar.
      const d = err.detail
      setMsg({ erro: true, texto: d?.erros ? d.erros.join(' · ') : (d?.erro || d || err.message) })
    } finally { setSalvando(false) }
  }

  const desfecho = async (status) => {
    setSalvando(true)
    setMsg(null)
    try {
      await api.desfechoEntrevista(entrevistaId, { status })
      await carregar()
      if (aoMudar) await aoMudar()
    } catch (err) {
      setMsg({ erro: true, texto: err.detail?.erro || err.detail || err.message })
    } finally { setSalvando(false) }
  }

  return (
    <div className="rh-conferencia">
      <div className="rh-conferencia-topo">
        <div>
          <h3>{e.pessoa}</h3>
          <span className="explica">
            {eTriagem ? 'Triagem — checagem de viabilidade' : 'Entrevista — avaliação ancorada'}
            {e.vaga_titulo && ` · vaga: ${e.vaga_titulo}`}
            {e.local && ` · ${e.local}`}
          </span>
          <div>
            <span className="chip">{e.status}</span>{' '}
            {e.marcada_para && <span className="chip">marcada {fmtDataHora(e.marcada_para)}</span>}{' '}
            {/* O ROTEIRO com que ESTA entrevista foi feita — vem do snapshot,
                não do roteiro vivo. Editar o roteiro depois não reescreve o que
                a nota significava, e a tela mostra qual versão sustentou a
                avaliação. */}
            {e.roteiro_nome && (
              <button className="chip chip-link"
                      title="Roteiro com que esta entrevista foi feita. Editar o roteiro depois NÃO altera este registro. Clique para ver e editar os roteiros."
                      onClick={irParaRoteiros}>
                roteiro: {e.roteiro_nome} v{e.roteiro_versao} ↗
              </button>
            )}{' '}
            {e.modalidade && <span className="chip">{e.modalidade}</span>}{' '}
            {e.defasagem_dias > 0 && (
              <span className="chip" style={{ '--chip-cor': 'var(--ambar)' }}
                    title="Memória decai: quanto maior a distância entre a conversa e o preenchimento, mais o relato é reconstrução.">
                preenchida {e.defasagem_dias}d depois
              </span>
            )}
          </div>
        </div>
        {/* SEM botão de fechar aqui (v2.78): quem abriu a ficha foi o "Mais
            detalhes" da linha, e ele mesmo fecha — virando "Menos detalhes".
            Dois controles para a mesma ação é o que o Bruno reprovou duas vezes
            seguidas. */}
      </div>

      {/* Gravação (v2.97): fica ANTES do formulário porque a conversa vem antes
          do preenchimento — quem grava, grava enquanto entrevista, e o valor do
          módulo é justamente não escrever durante a conversa. Depois do
          formulário, o botão só seria achado quando já não servisse. */}
      <GravacaoEntrevista entrevistaId={entrevistaId} encerrada={encerrada} />

      {/* Entrevista que passou da data e ninguém fechou: o sistema PERGUNTA.
          Nunca marca `nao_veio` sozinho — silêncio não é falta. */}
      {e.aguardando_desfecho && (
        <div className="aviso-inline">
          <strong>Esta entrevista está aguardando um desfecho.</strong>
          <div className="explica" style={{ margin: '.3rem 0 .5rem' }}>
            A data marcada já passou e ninguém registrou o que aconteceu. O
            sistema não conclui por você — diga o que houve:
          </div>
          <div className="chips-escolha">
            <button type="button" className="chip-escolha" disabled={salvando}
                    onClick={() => desfecho('nao_veio')}>Não compareceu</button>
            <button type="button" className="chip-escolha" disabled={salvando}
                    onClick={() => desfecho('remarcada')}>Remarcada</button>
            <button type="button" className="chip-escolha" disabled={salvando}
                    onClick={() => desfecho('cancelada')}>Cancelada</button>
          </div>
        </div>
      )}

      {/* Convite e lembrete (v2.66, § 14.4). Quando NÃO podem sair, a tela diz
          POR QUÊ — "desligado" sem motivo faria o RH tentar de novo achando
          que foi falha de rede, quando o que falta é o e-mail no cadastro
          (cenário 26). Nunca falha calada. */}
      {e.marcada_para && (
        <p className="explica">
          {e.motivo_sem_lembrete
            ? `Lembrete desligado: ${e.motivo_sem_lembrete}`
            : e.convite_enviado_em
              ? `Convite enviado em ${fmtDataHora(e.convite_enviado_em)}.`
                + (e.lembrete_enviado_em
                    ? ` Lembrete enviado em ${fmtDataHora(e.lembrete_enviado_em)}.`
                    : ' O lembrete sai na véspera.')
              : 'Nenhum convite enviado ainda.'}
        </p>
      )}

      {eTriagem ? (
        <Triagem form={form} campos={campos} marcar={marcar} setCampos={setCampos}
                 desabilitado={encerrada} />
      ) : (
        // O instrumento da AVALIAÇÃO é o do SNAPSHOT desta entrevista — não o
        // roteiro de hoje. Sem isso, uma entrevista feita com um roteiro
        // customizado mostraria as competências de outro, e as notas gravadas
        // não teriam onde aparecer.
        <Avaliacao form={{ ...form, competencias: e.roteiro_competencias || form.competencias }}
                   campos={campos} marcar={marcar} setCampos={setCampos}
                   desabilitado={encerrada} />
      )}

      <label className="campo">
        <span className="rotulo">Observação
          <span className="dica-inline"> — livre; o roteiro acima não é</span></span>
        <textarea rows={2} value={campos.observacao} disabled={encerrada}
                  onChange={(ev) => setCampos({ ...campos, observacao: ev.target.value })} />
      </label>

      {msg && <p className={msg.erro ? 'alerta' : 'sucesso'}>{msg.texto}</p>}

      {!encerrada && (
        <div className="rh-conferencia-acoes">
          <button className="btn-secundario btn-mini" onClick={() => salvar(false)}
                  disabled={salvando}>
            {salvando ? 'Salvando…' : 'Salvar rascunho'}
          </button>
          <button className="btn-principal btn-mini" onClick={() => salvar(true)}
                  disabled={salvando}>
            Concluir
          </button>
        </div>
      )}

      {/* O DOCUMENTO da ficha (v2.67, § 15.2-15.4). Fica no fim porque só
          existe depois de a entrevista estar concluída — mostrá-lo antes seria
          oferecer um botão que responde 422. */}
      <DocumentoDaFicha entrevistaId={entrevistaId} status={e.status} />
    </div>
  )
}

// --------------------------------------------------------------------------
// TRIAGEM — sem nota, sem competência, sem âncora. É outra coisa (§ 4.1).
// --------------------------------------------------------------------------

const RESPOSTAS_TRIAGEM = [
  { valor: 'sim', rotulo: 'Sim' },
  { valor: 'nao', rotulo: 'Não' },
  { valor: 'nao_sei', rotulo: 'Não sei' },
]

function Triagem({ form, campos, marcar, setCampos, desabilitado }) {
  return (
    <>
      <p className="explica">
        Checagem de viabilidade: descobrir em cinco minutos se vale marcar uma
        hora presencial. Sem nota — o que derruba a contratação raramente é
        incapacidade, é escala que não cabe, local inacessível ou salário abaixo
        do esperado.
      </p>

      <span className="rh-conferencia-bloco-titulo">Roteiro de triagem</span>
      {/* Cada pergunta é uma linha da escala: enunciado à esquerda, as três
          respostas à direita, todas à vista. Mesma primitiva do formulário da
          cartilha (`TabelaEscala`) — sim/não/não sei é escala curta, não
          motivo para uma lista suspensa por pergunta. */}
      <div className="rh-escala">
        {form.triagem.perguntas.map((p) => (
          <div className="rh-escala-linha" key={p.chave}>
            <span className="rh-escala-rotulo">
              {p.pergunta}
              {/* Seguro-desemprego é registrado porque EXPLICA falta e
                  desistência — nunca para excluir alguém. Dizer isso na tela é
                  o que impede o campo de virar critério na prática. */}
              {p.nunca_exclui && (
                <span className="dica-inline"> — registrado para entender
                  disponibilidade; <strong>nunca é critério de exclusão</strong></span>
              )}
            </span>
            <span className="chips-escolha">
              {RESPOSTAS_TRIAGEM.map((r) => (
                <button type="button" key={r.valor} disabled={desabilitado}
                        className={`chip-escolha ${campos.triagem[p.chave] === r.valor ? 'on' : ''}`}
                        onClick={() => marcar('triagem', p.chave,
                                              campos.triagem[p.chave] === r.valor ? undefined : r.valor)}>
                  {r.rotulo}</button>
              ))}
            </span>
          </div>
        ))}
      </div>

      <div className="campo" style={{ marginTop: '1rem' }}>
        <span className="rotulo">Desfecho</span>
        <div className="chips-escolha">
          {form.triagem.desfechos.map((d) => (
            <button type="button" key={d.chave} disabled={desabilitado}
                    className={`chip-escolha ${campos.triagem_desfecho === d.chave ? 'on' : ''}`}
                    onClick={() => setCampos({ ...campos,
                      triagem_desfecho: campos.triagem_desfecho === d.chave ? '' : d.chave })}>
              {d.rotulo}</button>
          ))}
        </div>
      </div>
    </>
  )
}

// --------------------------------------------------------------------------
// ENTREVISTA — 4 competências ancoradas, justificativa obrigatória.
// --------------------------------------------------------------------------

function Avaliacao({ form, campos, marcar, setCampos, desabilitado }) {
  const exigeMotivo = (form.recomendacoes || [])
    .find((r) => r.chave === campos.recomendacao)?.exige_motivo

  return (
    <>
      <div className="campo">
        <span className="rotulo">Variante das perguntas</span>
        <div className="chips-escolha">
          {form.variantes.map((v) => (
            <button type="button" key={v.chave} disabled={desabilitado}
                    className={`chip-escolha ${campos.variante === v.chave ? 'on' : ''}`}
                    onClick={() => setCampos({ ...campos, variante: v.chave })}>
              {v.rotulo}</button>
          ))}
        </div>
        <span className="explica">
          A comportamental exige que a pessoa tenha uma história para contar —
          com quem nunca trabalhou formalmente ela mede currículo, não
          competência. A competência, a escala e as âncoras são as mesmas nas
          duas.
        </span>
      </div>

      {/* UMA competência por bloco: nome escrito UMA VEZ, com a pergunta, as
          notas e a justificativa juntas (v2.75, reprovação do Bruno: *"por que
          escrever o título duas vezes? basta escrever cada título 1x e estarem
          alinhadas as notas e o campo de escrita"*).
          Antes eram DUAS listas paralelas — competências à esquerda,
          justificativas à direita — cada uma repetindo os 4 nomes. Além da
          repetição, nada garantia que as duas colunas ficassem na mesma altura:
          a pergunta da 1ª competência ocupa 2 linhas e a da 2ª ocupa 1, então a
          justificativa da 2ª aparecia na altura da 3ª. A pessoa preenchia o
          campo errado.
          É a armadilha da v2.66 numa variação: a primitiva de 2 colunas serve
          conteúdo EMPARELHADO, e o par aqui é *nota ↔ justificativa DAQUELA
          competência* — não "a lista de notas" ao lado de "a lista de textos".
          Emparelhando de verdade, o alinhamento deixa de ser sorte.
          A composição é a da referência canônica (`FormularioAvaliacao.jsx`):
          `.rh-escala-linha` com o rótulo e os `.chip-escolha`, e o `.campo` com
          o textarea logo abaixo. */}
      <div className="rh-conferencia-bloco-titulo">Competências</div>
      <p className="explica" style={{ margin: '0 0 .6rem' }}>
        Nota sem evidência é ruído — descreva o que foi observado, não o adjetivo.
        A justificativa é obrigatória em cada nota dada.
      </p>
      <div className="rh-escala">
        {form.competencias.map((c) => (
          <div className="rh-escala-linha rh-escala-linha-larga" key={c.chave}>
            <span className="rh-escala-rotulo">
              {c.nome}
              <span className="dica-inline"> — {c.perguntas[campos.variante]
                || c.perguntas.comportamental}</span>
            </span>
            <span className="chips-escolha">
              {form.escala.map((s) => (
                // A ÂNCORA vem junto do botão (v2.77, pedido do Bruno: *"as
                // âncoras têm que estar perto dos marcadores"*). Antes ela só
                // existia no `title` — que **não abre no celular**, onde não há
                // mouse — e num `<details>` no fim do bloco, longe de onde a
                // nota é dada. Quem avalia precisa ler a âncora NA HORA de
                // escolher: é ela que separa "4" de "3".
                // `data-dica` + `.chip-com-dica` reusa o mecanismo do
                // `Ajuda.jsx` (CSS puro, `:hover` no desktop e `:focus` no
                // toque) — o padrão da casa, em vez de um popup novo.
                <button type="button" key={s.valor} disabled={desabilitado}
                        title={c.ancoras[s.valor]}
                        data-dica={c.ancoras[s.valor]}
                        className={`chip-escolha chip-com-dica ${campos.competencias[c.chave] === s.valor ? 'on' : ''}`}
                        onClick={() => marcar('competencias', c.chave,
                                              campos.competencias[c.chave] === s.valor
                                                ? undefined : s.valor)}>
                  {s.rotulo}</button>
              ))}
            </span>
            <textarea rows={2} disabled={desabilitado}
                      value={campos.justificativas[c.chave] || ''}
                      onChange={(ev) => marcar('justificativas', c.chave, ev.target.value)}
                      placeholder="O que a pessoa disse que sustenta esta nota." />
          </div>
        ))}
      </div>
      {/* As âncoras num <details>: cursor, marcador e margem vêm do
          styles.css (regra da v2.47.1) — nada de style inline aqui.
          Continuam aqui embaixo, e não dentro de cada bloco: são as MESMAS
          quatro descrições para todas as competências, e repeti-las em cada uma
          seria a duplicação que esta leva veio remover. No dia a dia elas já
          estão no `title` de cada chip. */}
      <details>
        {/* Continua existindo mesmo com a âncora no chip (v2.77): aqui elas
            aparecem LADO A LADO, e comparar as quatro é outra tarefa —
            calibrar antes de começar, ou conferir um caso limítrofe. O chip
            responde "o que é o 3?"; esta lista responde "onde termina o 3 e
            começa o 4?". */}
        <summary>ver todas as âncoras lado a lado</summary>
        {form.competencias.map((c) => (
          <div className="campo" key={c.chave}>
            <span className="rotulo">{c.nome}</span>
            <ul>
              {form.escala.map((s) => (
                <li key={s.valor}><strong>{s.valor}</strong> — {c.ancoras[s.valor]}</li>
              ))}
            </ul>
          </div>
        ))}
      </details>

      <div className="campo">
        <span className="rotulo">Recomendação</span>
        <div className="chips-escolha">
          {form.recomendacoes.map((r) => (
            <button type="button" key={r.chave} disabled={desabilitado}
                    className={`chip-escolha ${campos.recomendacao === r.chave ? 'on' : ''}`}
                    onClick={() => setCampos({ ...campos,
                      recomendacao: campos.recomendacao === r.chave ? '' : r.chave })}>
              {r.rotulo}</button>
          ))}
        </div>
        {exigeMotivo && (
          <label className="campo" style={{ marginTop: '.5rem' }}>
            <span className="rotulo">Motivo
              <span className="dica-inline"> — obrigatório nesta recomendação: "com
                ressalva" sem dizer qual ressalva não é recomendação, é
                impressão</span></span>
            <textarea rows={2} disabled={desabilitado}
                      value={campos.recomendacao_motivo}
                      onChange={(ev) => setCampos({ ...campos, recomendacao_motivo: ev.target.value })} />
          </label>
        )}
      </div>
    </>
  )
}


// ---------------------------------------------------------------------------
// O DOCUMENTO da ficha (v2.67, § 15.2-15.4)
//
// **Onde a ficha VIVE**: no Arquivo e aqui, na ficha da pessoa. E **onde NÃO
// vive**: no dossiê de admissão. O Bruno chegou a incluir e corrigiu na mesma
// sessão — o dossiê CIRCULA (cliente, pasta física, quem pedir) e nota de
// seleção com justificativa escrita é dado sensível sobre a pessoa. A garantia
// é estrutural no backend (tabela própria, fora das três fontes que o
// `services/dossie.py` lê) e há teste por mutação; o texto abaixo existe para
// que quem OPERA a tela também saiba disso.
//
// O documento RENDERIZA na tela (regra da v2.33) — nada de `window.open` para a
// API, que no Chrome do Android baixa em vez de exibir.
// ---------------------------------------------------------------------------
function DocumentoDaFicha({ entrevistaId, status }) {
  const [dados, setDados] = useState(null)
  const [erroCarga, setErroCarga] = useState(null)
  const [doc, setDoc] = useState(null)
  const [senha, setSenha] = useState('')
  const [assinando, setAssinando] = useState(false)
  // Mensagem local: este bloco fica no PÉ de uma ficha longa; uma confirmação
  // no topo da tela seria invisível para quem clicou aqui (regra da v2.47).
  const [msg, setMsg] = useState(null)

  const carregar = () => {
    setErroCarga(null)
    return api.assinaturasEntrevista(entrevistaId)
      .then(setDados)
      .catch((err) => setErroCarga(err.detail?.erro || err.detail || err.message
                                   || 'Falha ao carregar.'))
  }
  useEffect(() => { carregar() }, [entrevistaId, status])

  // Falha de carga vira ERRO com botão de tentar de novo, nunca `null` silencioso
  // (regra da v2.46) — e o guard vem ANTES do primeiro uso do estado nulo.
  if (erroCarga) {
    return (
      <div className="rh-card">
        <p className="alerta">Não foi possível carregar as assinaturas: {erroCarga}</p>
        <button className="btn-secundario btn-mini" onClick={carregar}>Tentar de novo</button>
      </div>
    )
  }
  if (dados === null) return <p className="explica">Carregando o documento…</p>

  const impedimentos = dados.impedimentos || []
  const vias = dados.itens || []
  const viva = vias.filter((v) => !v.substituida_em)

  const abrir = async () => {
    setMsg(null)
    try {
      const blob = await api.documentoEntrevista(entrevistaId)
      setDoc({ blob, nome: 'ficha-de-entrevista.pdf' })
    } catch (err) {
      const d = err.detail
      setMsg({ erro: true,
               texto: d?.faltando ? d.faltando.join(' · ') : (d?.erro || d || err.message) })
    }
  }

  const assinar = async () => {
    setAssinando(true)
    setMsg(null)
    try {
      const r = await api.assinarFichaEntrevista(entrevistaId, senha)
      setSenha('')
      await carregar()
      setMsg({ texto: `Ficha assinada (via ${r.via}).` })
    } catch (err) {
      const d = err.detail
      setMsg({ erro: true,
               texto: d === 'senha_invalida'
                 ? 'Senha incorreta — é a senha do seu login no painel.'
                 : (d?.faltando ? d.faltando.join(' · ') : (d?.erro || d || err.message)) })
    } finally { setAssinando(false) }
  }

  return (
    <div className="rh-card">
      <span className="rh-conferencia-bloco-titulo">Documento da ficha</span>
      <p className="explica">
        Fica no Arquivo e aqui, na ficha da pessoa. <strong>Não entra no dossiê
        de admissão</strong> — o dossiê circula, e a nota da seleção é dado
        sensível sobre a pessoa.
      </p>

      {impedimentos.length > 0 ? (
        // Diz ANTES o que impede, em vez de deixar o botão ligado para dar 422
        // no clique.
        <p className="alerta">{impedimentos.join(' · ')}</p>
      ) : (
        <>
          <div className="rh-conferencia-acoes">
            <button className="btn-secundario btn-mini" onClick={abrir}>
              Ver o documento
            </button>
          </div>

          {viva.length > 0 ? (
            <p className="explica">
              Assinada por {viva[viva.length - 1].assinante} em{' '}
              {fmtDataHora(viva[viva.length - 1].assinado_em)}.
            </p>
          ) : (
            <label className="campo">
              <span className="rotulo">Assinar como quem conduziu
                <span className="dica-inline"> — confirme com a senha do seu
                  login. O entrevistado não assina.</span></span>
              <input type="password" value={senha} autoComplete="off"
                     onChange={(ev) => setSenha(ev.target.value)}
                     placeholder="Sua senha do painel" />
            </label>
          )}

          {viva.length === 0 && (
            <div className="rh-conferencia-acoes">
              <button className="btn-principal btn-mini" onClick={assinar}
                      disabled={assinando || !senha}>
                {assinando ? 'Assinando…' : 'Assinar a ficha'}
              </button>
            </div>
          )}
        </>
      )}

      {vias.length > 1 && (
        // As vias ANTERIORES continuam listadas: alterar a entrevista depois de
        // assinar gera uma via NOVA, e a anterior permanece com o hash dela —
        // ato assinado não se edita retroativamente.
        <details>
          <summary>vias anteriores ({vias.length - viva.length})</summary>
          <ul>
            {vias.filter((v) => v.substituida_em).map((v) => (
              <li key={v.id}>
                via {v.via} — {v.assinante}, {fmtDataHora(v.assinado_em)}
                {' '}(substituída em {fmtDataHora(v.substituida_em)})
              </li>
            ))}
          </ul>
        </details>
      )}

      {msg && <p className={msg.erro ? 'alerta' : 'sucesso'}>{msg.texto}</p>}

      {doc && (
        <VisualizadorArquivo blob={doc.blob} nome={doc.nome}
                             aoFechar={() => setDoc(null)} />
      )}
    </div>
  )
}
