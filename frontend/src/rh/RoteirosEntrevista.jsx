import { useEffect, useState } from 'react'
import { rh as api } from '../api.js'
import SelectBusca from '../SelectBusca.jsx'
import VisualizadorArquivo from '../VisualizadorArquivo.jsx'
import { fmtDataHora } from '../fmt.js'

// Catálogo de roteiros de entrevista (v2.66, § 14.1) — Configurações.
//
// Mora em Configurações, junto de Tags e Modelos, porque **não é tela de uso
// diário**: o RH monta o roteiro uma vez e depois só o escolhe na ficha.
//
// COMPOSIÇÃO: segue a mesma da `FichaEntrevista` corrigida na v2.65 —
// `.rh-conferencia` como bloco, `.rh-conferencia-topo` para cabeçalho + ação,
// `.rh-conferencia-corpo` para as duas colunas, `.chips-escolha`/`.chip-escolha`
// para escolha curta à vista e `.rh-conferencia-acoes` para os botões. A lição
// da v2.65: passar no `test_design_system.py` é vocabulário (a classe existe?),
// não composição (qual primitiva serve a qual papel) — então a referência é a
// tela equivalente que já existe, não o teste.
//
// O texto do instrumento NÃO é duplicado aqui: o que esta tela edita é o
// CONTEÚDO do roteiro, que vem do banco. Nenhuma âncora ou pergunta está
// escrita no JSX (o `test_roteiros_entrevista.py` varre e reprova).

const ROTULO_STATUS = {
  rascunho: 'Rascunho', publicado: 'Publicado', arquivado: 'Arquivado',
}

// Uma competência em branco, para o RH começar a escrever. Só a ESTRUTURA —
// os textos são todos dele.
const COMPETENCIA_VAZIA = () => ({
  chave: '', nome: '',
  ancoras: { 4: '', 3: '', 2: '', 1: '' },
  perguntas: { comportamental: '', situacional: '' },
})

export default function RoteirosEntrevista() {
  const [dados, setDados] = useState(null)
  // Falha de CARGA vira erro na tela com "tentar de novo" — nunca `null`
  // silencioso, que deixaria "Carregando…" para sempre (regra da v2.46).
  const [erroCarga, setErroCarga] = useState(null)
  const [editando, setEditando] = useState(null)   // id em edição, ou 'novo'
  const [incluirArquivados, setIncluirArquivados] = useState(false)
  const [msg, setMsg] = useState(null)
  // v2.67 (§ 15.5 item 3): dois catálogos, um por natureza. Cada um tem o SEU
  // roteiro padrão — juntos, a tela mostraria dois padrões e "qual é o padrão?"
  // deixaria de ter resposta.
  const [tipo, setTipo] = useState('entrevista')
  const [doc, setDoc] = useState(null)

  const carregar = () => {
    setErroCarga(null)
    return api.roteirosEntrevista(incluirArquivados, tipo)
      .then(setDados)
      .catch((e) => setErroCarga(e.detail || e.message || 'Falha ao carregar.'))
  }
  useEffect(() => { carregar() }, [incluirArquivados, tipo])

  // O documento RENDERIZA na tela (regra da v2.33) — nada de abrir aba nova
  // para a API, que no Chrome do Android baixa em vez de exibir.
  const verDocumento = async (r) => {
    setMsg(null)
    try {
      const blob = await api.documentoRoteiro(r.id)
      setDoc({ blob, nome: `roteiro-${r.nome}.pdf` })
    } catch (e) {
      const d = e.detail
      setMsg({ erro: true, texto: d?.mensagem || d?.erro || d || e.message })
    }
  }

  const acao = async (fn, textoOk) => {
    setMsg(null)
    try {
      await fn()
      await carregar()
      setMsg({ texto: textoOk })
    } catch (e) {
      // O backend devolve `detail.erros` NOMEANDO o que falta. Perder essa
      // lista faria a tela dizer só "não deu".
      const d = e.detail
      setMsg({ erro: true, texto: d?.erros ? d.erros.join(' · ') : (d?.erro || d || e.message) })
    }
  }

  if (erroCarga) {
    return (
      <div className="rh-card">
        <p className="alerta">Não foi possível carregar: {erroCarga}</p>
        <button className="btn-principal btn-mini" onClick={carregar}>Tentar de novo</button>
      </div>
    )
  }
  // Guard ANTES de qualquer uso — "carregando" e "vazio" são estados
  // DIFERENTES e não podem cair na mesma condição (regra da v2.47).
  if (dados === null) return <div className="rh-card"><p>Carregando…</p></div>

  return (
    <div className="rh-card">
      <h3>🗣️ Roteiros de entrevista</h3>
      <p className="explica">
        O que se pergunta numa entrevista e como cada nota é ancorada. O roteiro
        nasce <strong>rascunho</strong> e só pode ser usado depois de
        <strong> publicado</strong> — é isso que permite dizer que o roteiro foi
        aprovado <em>antes</em> de ser usado, que é a defesa da empresa se
        alguém questionar o que foi perguntado.
      </p>
      {/* A herança por cargo é da ENTREVISTA. A triagem não herda: "aceita a
          escala?" vale para qualquer posto — o que muda entre cargos é a
          resposta, não a pergunta. Repetir o texto na aba errada ensinaria uma
          regra que não existe. */}
      {tipo === 'entrevista' ? (
        <p className="explica">
          A escolha é por <strong>cargo</strong>, com exceção por senioridade: o
          mais específico vence. Cargo sem roteiro próprio usa o padrão — nunca
          fica sem.
        </p>
      ) : (
        <p className="explica">
          A triagem é <strong>checagem de viabilidade</strong>: perguntas de
          sim/não que decidem se vale gastar uma hora presencial. Ela não tem
          nota, competência nem âncora — e continua assim, mesmo sendo editável.
          O seguro-desemprego é registrado como contexto e <strong>nunca</strong>
          {' '}é critério de exclusão.
        </p>
      )}

      {msg && <p className={msg.erro ? 'alerta' : 'sucesso'}>{msg.texto}</p>}

      {/* Duas naturezas, dois catálogos (v2.67). A triagem é checagem de
          viabilidade: perguntas de sim/não, SEM nota, competência ou âncora —
          e é assim que ela continua sendo, mesmo agora que é editável. */}
      <div className="rh-abas">
        <button className={tipo === 'entrevista' ? 'ativa' : ''}
                onClick={() => { setTipo('entrevista'); setEditando(null) }}>
          Entrevista — avaliação ancorada
        </button>
        <button className={tipo === 'triagem' ? 'ativa' : ''}
                onClick={() => { setTipo('triagem'); setEditando(null) }}>
          Triagem — checagem de viabilidade
        </button>
      </div>

      <div className="rh-metricas">
        <div className="rh-metrica"><strong>{dados.metricas.publicados}</strong><span>Publicados</span></div>
        <div className="rh-metrica"><strong>{dados.metricas.rascunhos}</strong><span>Rascunhos</span></div>
        <div className="rh-metrica"><strong>{dados.metricas.arquivados}</strong><span>Arquivados</span></div>
      </div>

      <div className="rh-topo">
        {editando === 'novo' ? <span /> : (
          <button className="btn-principal btn-mini" onClick={() => setEditando('novo')}>
            ＋ Novo roteiro
          </button>
        )}
        <label className="campo-sem-margem">
          <input type="checkbox" checked={incluirArquivados}
                 onChange={(ev) => setIncluirArquivados(ev.target.checked)} />
          {' '}mostrar arquivados
        </label>
      </div>

      {editando === 'novo' && (
        <FormRoteiro senioridades={dados.senioridades} tipo={tipo}
                     aoFechar={() => { setEditando(null); carregar() }}
                     aoErro={(t) => setMsg({ erro: true, texto: t })} />
      )}

      {dados.itens.length === 0 && (
        <p className="explica">Nenhum roteiro cadastrado.</p>
      )}

      {dados.itens.map((r) => (
        editando === r.id ? (
          <FormRoteiro key={r.id} roteiro={r} senioridades={dados.senioridades}
                       tipo={tipo}
                       aoFechar={() => { setEditando(null); carregar() }}
                       aoErro={(t) => setMsg({ erro: true, texto: t })} />
        ) : (
          <div className="rh-conferencia" key={r.id}>
            <div className="rh-conferencia-topo">
              <div>
                <h3>{r.nome}</h3>
                <span className="explica">
                  {r.cargo ? `cargo: ${r.cargo}` : 'vale para os cargos sem roteiro próprio'}
                  {r.senioridade && ` · ${r.senioridade}`}
                  {r.tipo === 'triagem'
                    ? ` · ${(r.perguntas || []).length} pergunta(s)`
                    : ` · ${(r.competencias || []).length} competência(s)`}
                  {r.entrevistas > 0 && ` · usado em ${r.entrevistas} entrevista(s)`}
                </span>
                <div>
                  <span className="chip">{ROTULO_STATUS[r.status] || r.status}</span>{' '}
                  <span className="chip">v{r.versao}</span>{' '}
                  {r.padrao && (
                    <span className="chip" title="É o roteiro usado quando o cargo não tem um próprio. Não se apaga nem se arquiva.">
                      padrão
                    </span>
                  )}{' '}
                  {r.publicado_em && (
                    <span className="explica">
                      publicado em {fmtDataHora(r.publicado_em)}
                      {r.publicado_por && ` por ${r.publicado_por}`}
                    </span>
                  )}
                </div>
              </div>
            </div>

            {/* O conteúdo depende da NATUREZA (v2.67). O rótulo antigo dizia
                "competências e âncoras" em todo roteiro — num de TRIAGEM isso
                é falso duas vezes: ela não tem nem uma nem outra, e a lista
                abriria VAZIA. Defeito visível só na tela renderizada; o código
                parecia certo, porque `r.competencias` simplesmente vem vazio.
                É a regra da v2.47: conferir a tela, não só o código. */}
            {r.tipo === 'triagem' ? (
              <details>
                <summary>ver as perguntas deste roteiro</summary>
                <ul>
                  {(r.perguntas || []).map((p) => (
                    <li key={p.chave}>{p.pergunta}</li>
                  ))}
                </ul>
                <span className="explica">
                  Todas se respondem com sim / não / não sei. A triagem não
                  atribui nota nem avalia competência.
                </span>
              </details>
            ) : (
              <details>
                <summary>ver as competências e âncoras deste roteiro</summary>
                {(r.competencias || []).map((cmp) => (
                  <div className="campo" key={cmp.chave}>
                    <span className="rotulo">{cmp.nome}</span>
                    <ul>
                      {['4', '3', '2', '1'].map((n) => (
                        <li key={n}><strong>{n}</strong> — {cmp.ancoras[n]}</li>
                      ))}
                    </ul>
                    <span className="explica">
                      Comportamental: {cmp.perguntas.comportamental}<br />
                      Situacional: {cmp.perguntas.situacional}
                    </span>
                  </div>
                ))}
              </details>
            )}

            <div className="rh-conferencia-acoes">
              {r.status !== 'arquivado' && (
                <button className="btn-secundario btn-mini"
                        onClick={() => setEditando(r.id)}>Editar</button>
              )}
              {r.status === 'rascunho' && (
                <button className="btn-principal btn-mini"
                        onClick={() => acao(() => api.publicarRoteiroEntrevista(r.id),
                                            'Roteiro publicado — a partir de agora ele pode ser usado.')}>
                  Publicar
                </button>
              )}
              <button className="btn-secundario btn-mini"
                      onClick={() => acao(() => api.duplicarRoteiroEntrevista(r.id),
                                          'Cópia criada como rascunho.')}>
                Duplicar
              </button>
              {/* O documento do roteiro (v2.67, § 15.2) — só do PUBLICADO. É a
                  peça que se anexa a uma defesa: prova que o roteiro foi
                  aprovado ANTES de ser usado, com data e autor. O botão nem
                  aparece no rascunho, em vez de aparecer e dar 409. */}
              {r.tem_documento && (
                <button className="btn-secundario btn-mini"
                        title="PDF do roteiro aprovado, com versão, quem publicou e quando."
                        onClick={() => verDocumento(r)}>
                  Ver documento
                </button>
              )}
              {r.status === 'publicado' && !r.padrao && (
                <button className="btn-secundario btn-mini"
                        title="Passa a ser o roteiro usado quando o cargo não tem um próprio."
                        onClick={() => acao(() => api.tornarPadraoRoteiroEntrevista(r.id),
                                            'Este passou a ser o roteiro padrão.')}>
                  Tornar padrão
                </button>
              )}
              {/* O padrão não se arquiva nem se apaga: ele é o fundo da
                  herança. Em vez de mostrar um botão que só devolve erro, a
                  tela explica por que ele não está ali. */}
              {r.padrao ? (
                <span className="explica">
                  O roteiro padrão não se arquiva nem se exclui — eleja outro
                  como padrão primeiro.
                </span>
              ) : (
                <>
                  {r.status !== 'arquivado' && (
                    <button className="btn-remover btn-mini"
                            onClick={() => acao(() => api.arquivarRoteiroEntrevista(r.id),
                                                'Roteiro arquivado — as entrevistas antigas continuam legíveis.')}>
                      Arquivar
                    </button>
                  )}
                  {r.entrevistas === 0 && (
                    <button className="btn-remover btn-mini"
                            onClick={() => {
                              if (!window.confirm(`Excluir o roteiro "${r.nome}"? Ele vai para a lixeira.`)) return
                              acao(() => api.excluirRoteiroEntrevista(r.id), 'Roteiro excluído.')
                            }}>
                      Excluir
                    </button>
                  )}
                </>
              )}
            </div>
          </div>
        )
      ))}

      {doc && (
        <VisualizadorArquivo blob={doc.blob} nome={doc.nome}
                             aoFechar={() => setDoc(null)} />
      )}
    </div>
  )
}

// --------------------------------------------------------------------------
// O formulário do roteiro — abre NA LINHA do item, nunca no topo da tela.
// --------------------------------------------------------------------------

function FormRoteiro({ roteiro, senioridades, aoFechar, aoErro, tipo = 'entrevista' }) {
  // O tipo do roteiro EXISTENTE manda; só o novo herda a aba aberta. Trocar o
  // tipo por edição é recusado no servidor (as respostas já gravadas iriam para
  // uma ficha com nota), e a tela não deve oferecer o que o servidor recusa.
  const eTriagem = (roteiro?.tipo || tipo) === 'triagem'
  const [nome, setNome] = useState(roteiro?.nome || '')
  const [cargo, setCargo] = useState(roteiro?.cargo || '')
  const [senioridade, setSenioridade] = useState(roteiro?.senioridade || '')
  const [comps, setComps] = useState(
    roteiro?.competencias?.length ? roteiro.competencias : [COMPETENCIA_VAZIA()])
  // As perguntas da TRIAGEM: só texto. Sem nota, sem âncora, sem competência —
  // é o § 4.1, e o servidor recusa com 422 se algum desses campos aparecer.
  const [perguntas, setPerguntas] = useState(
    roteiro?.perguntas?.length ? roteiro.perguntas : [{ pergunta: '' }])
  const [salvando, setSalvando] = useState(false)
  // Mensagem LOCAL: o formulário abre no meio da lista, longe do topo — a
  // confirmação nasce perto do botão que a gerou (regra da v1.96/v2.47).
  const [msg, setMsg] = useState(null)

  const mexer = (i, campo, valor) =>
    setComps(comps.map((c, j) => (j === i ? { ...c, [campo]: valor } : c)))
  const mexerAncora = (i, nota, valor) =>
    setComps(comps.map((c, j) => (
      j === i ? { ...c, ancoras: { ...c.ancoras, [nota]: valor } } : c)))
  const mexerPergunta = (i, variante, valor) =>
    setComps(comps.map((c, j) => (
      j === i ? { ...c, perguntas: { ...c.perguntas, [variante]: valor } } : c)))

  const salvar = async () => {
    setSalvando(true)
    setMsg(null)
    try {
      const corpo = eTriagem ? {
        nome,
        tipo: 'triagem',
        // Só o TEXTO da pergunta vai — a chave é derivada no servidor. Nada de
        // nota, âncora ou competência: a triagem editável não pode virar a
        // porta pela qual ela vira entrevista curta.
        perguntas: perguntas
          .map((p) => ({ pergunta: (p.pergunta || '').trim() }))
          .filter((p) => p.pergunta),
      } : {
        nome,
        tipo: 'entrevista',
        cargo: cargo || null,
        senioridade: senioridade || null,
        // A chave é derivada do nome quando o RH não a escreveu: é chave
        // técnica, e pedi-la seria pedir que ele pensasse como o banco.
        competencias: comps.map((c) => ({
          ...c,
          chave: (c.chave || c.nome || '').toLowerCase()
            .normalize('NFD').replace(/[̀-ͯ]/g, '')
            .replace(/[^a-z0-9]+/g, '_').replace(/^_|_$/g, '').slice(0, 40),
        })),
      }
      if (roteiro) await api.editarRoteiroEntrevista(roteiro.id, corpo)
      else await api.criarRoteiroEntrevista(corpo)
      aoFechar()
    } catch (e) {
      const d = e.detail
      const texto = d?.erros ? d.erros.join(' · ') : (d?.erro || d || e.message)
      setMsg({ erro: true, texto })
      if (aoErro) aoErro(texto)
    } finally { setSalvando(false) }
  }

  return (
    <div className="rh-conferencia">
      <div className="rh-conferencia-topo">
        <div>
          <h3>{roteiro ? 'Editar roteiro' : 'Novo roteiro'}</h3>
          {roteiro?.status === 'publicado' && (
            <span className="explica">
              Este roteiro está publicado. Ao salvar, ele vira a
              <strong> versão {(roteiro.versao || 1) + 1}</strong> e volta a
              rascunho — publique de novo para poder usá-lo. As entrevistas já
              feitas continuam com o roteiro com que foram feitas.
            </span>
          )}
        </div>
        <button className="btn-secundario btn-mini" onClick={aoFechar}>✕ fechar</button>
      </div>

      {/* ⚠️ NÃO em `.rh-conferencia-corpo` (2 colunas). Medido na tela: com 3
          campos à esquerda e 7 por competência à direita, a coluna esquerda
          ficava VAZIA por ~1.100px enquanto a direita esticava. A primitiva de
          2 colunas serve conteúdo EMPARELHADO (na ficha: a nota ao lado da
          justificativa que a sustenta), não um bloco curto ao lado de um longo.
          Aqui "quando vale" é cabeçalho — vai em `.rh-grid-2`, largura cheia —
          e as competências, que são o conteúdo, ficam com a tela toda. */}
      <div className="rh-grid-2">
        <div>
          <span className="rh-conferencia-bloco-titulo">Quando este roteiro vale</span>
          <label className="campo">
            <span className="rotulo">Nome do roteiro</span>
            <input value={nome} onChange={(e) => setNome(e.target.value)}
                   placeholder="Vigia — operacional" />
          </label>
          {/* Cargo e senioridade só existem na ENTREVISTA: a triagem não herda
              por cargo, porque "aceita a escala?" e "consegue chegar?" valem
              para qualquer posto — o que muda entre cargos é a RESPOSTA, não a
              pergunta. Campos que não fazem nada seriam pior que ausentes. */}
          {!eTriagem && (
          <label className="campo">
            <span className="rotulo">Cargo
              <span className="dica-inline"> — em branco, vale para todos os
                cargos sem roteiro próprio</span></span>
            <input value={cargo} disabled={roteiro?.padrao}
                   onChange={(e) => setCargo(e.target.value)}
                   placeholder="Vigia" />
          </label>
          )}
          {!eTriagem && (
          <div className="campo">
            <span className="rotulo">Senioridade
              <span className="dica-inline"> — em branco, vale para todas</span></span>
            {/* ⚠️ `valor`/`aoEscolher`/`desabilitado` — NÃO os nomes da lista
                suspensa nativa (`value`/`onChange`/`disabled`). O SelectBusca
                tem assinatura própria, e o React ignora prop desconhecida EM
                SILÊNCIO: com os nomes errados o campo renderiza vazio e nunca
                grava, com o código parecendo certo. É a armadilha que a v2.64
                pagou neste mesmo módulo — antes de passar prop nova, abrir a
                assinatura do componente. */}
            <SelectBusca valor={senioridade} desabilitado={!!roteiro?.padrao}
                         aoEscolher={(v) => setSenioridade(v)}>
              <option value="">— todas —</option>
              {(senioridades || []).map((s) => (
                <option key={s} value={s}>{s}</option>
              ))}
            </SelectBusca>
          </div>
          )}
        </div>
      </div>

      {eTriagem ? (
        <div>
          <span className="rh-conferencia-bloco-titulo">Perguntas de viabilidade</span>
          <p className="explica">
            Cada pergunta se responde com <strong>sim / não / não sei</strong>,
            por telefone, em segundos. A triagem <strong>não tem nota, nem
            competência, nem âncora</strong> — ela decide se vale gastar uma hora
            presencial, não se a pessoa é boa. Pergunta que exige julgamento é
            competência, e o lugar dela é a entrevista.
          </p>
          {perguntas.map((p, i) => (
            <div className="campo" key={i}>
              <span className="rotulo">Pergunta {i + 1}</span>
              <input value={p.pergunta || ''}
                     onChange={(e) => setPerguntas(perguntas.map((q, j) => (
                       j === i ? { ...q, pergunta: e.target.value } : q)))}
                     placeholder="A escala é 12x36 noturno. Isso cabe na sua rotina?" />
              {perguntas.length > 1 && (
                <button className="btn-remover btn-mini"
                        onClick={() => setPerguntas(perguntas.filter((_, j) => j !== i))}>
                  Remover
                </button>
              )}
            </div>
          ))}
          <button className="btn-secundario btn-mini"
                  onClick={() => setPerguntas([...perguntas, { pergunta: '' }])}>
            ＋ Outra pergunta
          </button>
        </div>
      ) : (
      <div>
        <div>
          <span className="rh-conferencia-bloco-titulo">Competências avaliadas</span>
          <p className="explica">
            Cada nota precisa de uma âncora que descreva um
            <strong> comportamento observável</strong>, não um adjetivo — é o que
            faz duas entrevistas serem comparáveis. As duas variantes da pergunta
            existem porque a comportamental ("conte uma vez em que…") não
            funciona com quem nunca trabalhou formalmente.
          </p>
          {comps.map((cmp, i) => (
            <details key={i} open={comps.length === 1}>
              <summary>{cmp.nome || `Competência ${i + 1}`}</summary>
              <label className="campo">
                <span className="rotulo">Nome da competência</span>
                <input value={cmp.nome}
                       onChange={(e) => mexer(i, 'nome', e.target.value)} />
              </label>
              {/* AQUI as 2 colunas fazem sentido: âncoras e perguntas são
                  conteúdo emparelhado — quem escreve a âncora da nota 4 está
                  pensando na pergunta que a provoca, e vê as duas juntas em vez
                  de rolar entre elas. */}
              <div className="rh-conferencia-corpo">
                <div>
                  <span className="rh-conferencia-bloco-titulo">Âncoras das notas</span>
                  {['4', '3', '2', '1'].map((n) => (
                    <label className="campo" key={n}>
                      <span className="rotulo">Nota {n}</span>
                      <textarea rows={2} value={cmp.ancoras?.[n] || ''}
                                onChange={(e) => mexerAncora(i, n, e.target.value)}
                                placeholder="O que a pessoa faz ou diz que caracteriza esta nota." />
                    </label>
                  ))}
                </div>
                <div>
                  <span className="rh-conferencia-bloco-titulo">As duas variantes da pergunta</span>
                  <label className="campo">
                    <span className="rotulo">Comportamental
                      <span className="dica-inline"> — para quem tem experiência
                        no cargo</span></span>
                    <textarea rows={3} value={cmp.perguntas?.comportamental || ''}
                              onChange={(e) => mexerPergunta(i, 'comportamental', e.target.value)} />
                  </label>
                  <label className="campo">
                    <span className="rotulo">Situacional
                      <span className="dica-inline"> — para primeiro emprego, que
                        não tem história para contar</span></span>
                    <textarea rows={3} value={cmp.perguntas?.situacional || ''}
                              onChange={(e) => mexerPergunta(i, 'situacional', e.target.value)} />
                  </label>
                </div>
              </div>
              {comps.length > 1 && (
                <button className="btn-remover btn-mini"
                        onClick={() => setComps(comps.filter((_, j) => j !== i))}>
                  Remover competência
                </button>
              )}
            </details>
          ))}
          <button className="btn-secundario btn-mini"
                  onClick={() => setComps([...comps, COMPETENCIA_VAZIA()])}>
            ＋ Acrescentar competência
          </button>
          <p className="explica">
            Quatro é o alvo para cargos operacionais: com muitas, preenche-se no
            automático; com poucas, pensa-se.
          </p>
        </div>
      </div>
      )}

      {msg && <p className={msg.erro ? 'alerta' : 'sucesso'}>{msg.texto}</p>}

      <div className="rh-conferencia-acoes">
        <button className="btn-secundario btn-mini" onClick={aoFechar}>Cancelar</button>
        <button className="btn-principal btn-mini" onClick={salvar} disabled={salvando}>
          {salvando ? 'Salvando…' : 'Salvar rascunho'}
        </button>
      </div>
    </div>
  )
}
