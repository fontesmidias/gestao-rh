import { useEffect, useState } from 'react'
import { rh as api } from '../api.js'
import DashPlanilha from './DashPlanilha.jsx'
import SelectBusca from '../SelectBusca.jsx'
import FichaEntrevista from './FichaEntrevista.jsx'
import { fmtData } from '../fmt.js'

// Módulo de Entrevistas (v2.64) — o degrau que faltava entre "o RH olhou o
// currículo" e "o RH mandou o convite".
//
// Duas naturezas na mesma lista, distinguidas por `tipo`:
//   • triagem    — checagem de viabilidade por telefone, SEM nota
//   • entrevista — avaliação ancorada, 4 competências
//
// O card mais importante é "⚠ Aguardando desfecho": entrevista cuja data passou
// e ninguém disse o que houve. O sistema PERGUNTA, nunca conclui `nao_veio`
// sozinho — silêncio não é falta.

const ROTULO_STATUS = {
  marcada: 'Marcada', realizada: 'Realizada', nao_veio: 'Não compareceu',
  remarcada: 'Remarcada', cancelada: 'Cancelada', arquivada: 'Arquivada',
}
const ROTULO_TIPO = { triagem: 'Triagem', entrevista: 'Entrevista' }

export default function EntrevistasRH({ aoVoltar, abrirPessoa }) {
  const [dados, setDados] = useState(null)
  // Falha de CARGA vira erro na tela com "tentar de novo" — nunca `null`
  // silencioso, que deixaria "Carregando…" para sempre (regra da v2.46).
  const [erroCarga, setErroCarga] = useState(null)
  const [form, setForm] = useState(null)
  const [msg, setMsg] = useState(null)
  const [aberta, setAberta] = useState(null)
  const [novo, setNovo] = useState(null)
  const [incluirArquivadas, setIncluirArquivadas] = useState(false)

  const carregar = () => {
    setErroCarga(null)
    return api.entrevistas(incluirArquivadas ? { incluir_arquivadas: 'true' } : {})
      .then(setDados)
      .catch((e) => setErroCarga(e.detail || e.message || 'Falha ao carregar.'))
  }

  useEffect(() => { carregar() }, [incluirArquivadas])
  // O instrumento é carregado UMA vez e passado adiante: as fichas o recebem
  // por prop em vez de cada uma pedir o seu.
  useEffect(() => {
    api.formularioEntrevista().then(setForm)
      .catch((e) => setErroCarga(e.detail || e.message || 'Falha ao carregar o formulário.'))
  }, [])

  if (erroCarga) {
    return (
      <main className="rh-painel">
        <header className="rh-topo"><h1>Entrevistas</h1></header>
        <div className="rh-card">
          <p className="alerta">Não foi possível carregar: {erroCarga}</p>
          <button className="btn-principal" onClick={carregar}>Tentar de novo</button>
        </div>
      </main>
    )
  }
  // `dados`/`form` nascem null: o guard vem ANTES de qualquer uso (a 2ª causa
  // do incidente de tela branca de 2026-07-29 foi exatamente um `.some()` em
  // estado nulo acima do guard).
  if (!dados || !form) {
    return (
      <main className="rh-painel">
        <header className="rh-topo"><h1>Entrevistas</h1></header>
        <div className="rh-card"><p>Carregando…</p></div>
      </main>
    )
  }

  const m = dados.metricas
  const cards = [
    // O primeiro card é o que cobra (cenário 2).
    { rotulo: '⚠ Aguardando desfecho', valor: m.aguardando_desfecho,
      cor: 'var(--ambar)', filtro: { chave: 'pendencia', valor: 'Sim' } },
    { rotulo: 'Marcadas', valor: m.marcadas, filtro: { chave: 'status', valor: 'Marcada' } },
    { rotulo: 'Realizadas', valor: m.realizadas, filtro: { chave: 'status', valor: 'Realizada' } },
    { rotulo: 'Não compareceram', valor: m.nao_compareceram,
      filtro: { chave: 'status', valor: 'Não compareceu' } },
    { rotulo: 'Total', valor: m.total },
  ]

  const colunas = [
    { chave: 'pessoa', rotulo: 'Pessoa', ordenavel: true, filtro: 'texto',
      sempreVisivel: true, quebra: true,
      render: (l) => (
        <button className="btn-link" title="Abrir a ficha da pessoa"
                onClick={(ev) => {
                  ev.stopPropagation()
                  if (l.candidato_id && abrirPessoa) abrirPessoa(l.candidato_id)
                }}>{l.pessoa}</button>
      ) },
    { chave: 'vaga', rotulo: 'Vaga', ordenavel: true, filtro: 'lista', quebra: true,
      // Snapshot: se a vaga foi excluída o título continua aqui (cenário 4).
      // Sem vaga, mostra cargo e posto (v2.74) — antes a coluna ficava com um
      // travessão e a conversa parecia não ter assunto. O `valor` alimenta o
      // filtro de lista, então ele precisa refletir o que a célula EXIBE.
      valor: (l) => l.vaga_titulo
        || [l.cargo, l.posto_nome].filter(Boolean).join(' · ') || '—',
      // `title` com o título inteiro: os postos reais são longos ("INEP -
      // 37/2025 - APOIO ADMINISTRATIVO, RECEPÇÃO E PORTARIA…") e o CSS corta
      // em 3 linhas para o card não ocupar meia tela — cortar sem `title`
      // esconderia de qual vaga é a entrevista (regra da v2.59/v2.60).
      render: (l) => {
        // Sem vaga cadastrada, cargo e posto ocupam o lugar dela (v2.74): é o
        // que responde "para que foi essa conversa". O posto vem em `<small>`
        // porque o cargo é o que decide o roteiro — a hierarquia da célula
        // acompanha a do dado.
        const semVaga = [l.cargo, l.posto_nome].filter(Boolean)
        return (
          <span title={l.vaga_titulo || semVaga.join(' · ') || undefined}>
            {l.vaga_titulo || (semVaga.length
              ? <>{l.cargo || ''}{l.posto_nome && <><br /><small>{l.posto_nome}</small></>}</>
              : '—')}
            {l.vaga_titulo && !l.vaga_existe &&
              <> <span className="chip" title="A vaga foi excluída; o título ficou registrado.">vaga excluída</span></>}
          </span>
        )
      } },
    { chave: 'tipo', rotulo: 'Tipo', ordenavel: true, filtro: 'select',
      opcoes: Object.values(ROTULO_TIPO),
      valor: (l) => ROTULO_TIPO[l.tipo] || l.tipo },
    { chave: 'quando', rotulo: 'Quando', ordenavel: true, nowrap: true,
      valor: (l) => l.realizada_em || l.marcada_para || l.criada_em,
      render: (l) => {
        const q = l.realizada_em || l.marcada_para
        return (
          <>
            {q ? fmtData(q) : '—'}
            {/* Carimbo da defasagem (§ 2.5): quem preenche dias depois
                RECONSTRÓI em vez de lembrar. Não se proíbe — se anuncia. */}
            {l.defasagem_dias > 0 &&
              <> <span className="chip" style={{ '--chip-cor': 'var(--ambar)' }}
                       title={`A entrevista foi preenchida ${l.defasagem_dias} dia(s) depois de realizada. Memória decai: quanto maior a distância, mais o relato é reconstrução.`}>
                preenchida {l.defasagem_dias}d depois</span></>}
          </>
        )
      } },
    // Oculta por padrão: com um só entrevistador (decisão 1 do Bruno) a coluna
    // repete o mesmo nome em toda linha e custava 137px dos 1060 visíveis.
    // Continua disponível em "Colunas" para quando houver mais de um.
    { chave: 'entrevistador', rotulo: 'Entrevistador', ordenavel: true,
      filtro: 'lista', oculta: true },
    { chave: 'status', rotulo: 'Situação', ordenavel: true, filtro: 'select',
      nowrap: true, opcoes: Object.values(ROTULO_STATUS),
      valor: (l) => ROTULO_STATUS[l.status] || l.status,
      render: (l) => (
        <>
          <span className="chip">{ROTULO_STATUS[l.status] || l.status}</span>
          {/* Só o SINAL, com o texto no title: medido em 1440px, o chip
              "⚠ aguardando desfecho" por extenso levava a coluna a 193px e a
              tabela a estourar 56px — chip não quebra linha (regra da v2.59).
              O card do topo já anuncia a fila por extenso. */}
          {l.aguardando_desfecho &&
            <> <span className="chip" style={{ '--chip-cor': 'var(--ambar)' }}
                     title="A data passou e ninguém registrou o que houve. O sistema não conclui por você — abra a linha e diga o que houve.">
              ⚠</span></>}
        </>
      ) },
    { chave: 'desfecho', rotulo: 'Desfecho', quebra: true,
      filtro: 'lista', valor: (l) => desfechoTexto(l, form) },
    { chave: 'nota', rotulo: 'Nota', ordenavel: true, nowrap: true,
      valor: (l) => (l.media == null ? '' : l.media),
      render: (l) => (l.media == null ? '—' : l.media.toFixed(2)) },
    // Coluna auxiliar só para o card "Aguardando desfecho" ter o que filtrar.
    { chave: 'pendencia', rotulo: 'Pendente?', oculta: true,
      valor: (l) => (l.aguardando_desfecho ? 'Sim' : 'Não') },
  ]

  return (
    <main className="rh-painel">
      <header className="rh-topo">
        <h1>Entrevistas</h1>
        <div>
          {/* O `white-space: nowrap` do rótulo vive no styles.css, na regra
              base do botão — não em style inline (v2.64). */}
          <button className="btn-secundario" onClick={() => setNovo({ tipo: 'triagem' })}>
            + Triagem
          </button>{' '}
          <button className="btn-principal" onClick={() => setNovo({ tipo: 'entrevista' })}>
            + Entrevista
          </button>
        </div>
      </header>

      {msg && <p className={msg.erro ? 'alerta' : 'sucesso'}>{msg.texto}</p>}

      {novo && (
        <NovaEntrevista inicial={novo} form={form}
                        aoFechar={() => setNovo(null)}
                        aoCriar={async (criada) => {
                          setNovo(null)
                          await carregar()
                          setAberta(criada.id)
                          setMsg({ texto: 'Entrevista registrada. Preencha a ficha abaixo.' })
                        }}
                        aoErro={(t) => setMsg({ erro: true, texto: t })} />
      )}

      <DashPlanilha
        id="entrevistas"
        colunas={colunas}
        dados={dados.itens}
        cards={cards}
        filtrosExtras={[{
          chave: 'arquivadas', rotulo: 'Arquivadas',
          valor: incluirArquivadas ? 'sim' : '',
          opcoes: [{ valor: '', rotulo: 'Ocultar arquivadas' },
                   { valor: 'sim', rotulo: 'Incluir arquivadas' }],
          aoMudar: (v) => setIncluirArquivadas(v === 'sim'),
        }]}
        chaveLinha={(l) => l.id}
        acoesLinha={(l) => (
          <button className="btn-secundario btn-mini"
                  onClick={() => setAberta(aberta === l.id ? null : l.id)}>
            {aberta === l.id ? 'fechar' : 'abrir'}
          </button>
        )}
        // O detalhe abre NA LINHA, nunca no fim da página (regra desde a v1.83).
        // UM wrapper `<div>`: com Fragment, o `.dash-detalhe > td > *` aplicaria
        // sticky a cada filho e o padding sumiria (armadilha da v2.54).
        linhaExpandida={(l) => (aberta === l.id ? (
          <div className="ficha-talento">
            <FichaEntrevista
              entrevistaId={l.id} form={form}
              aoFechar={() => setAberta(null)}
              aoMudar={carregar} />
          </div>
        ) : null)}
        vazio="Nenhuma entrevista registrada ainda."
      />
    </main>
  )
}

function desfechoTexto(l, form) {
  if (l.tipo === 'triagem') {
    const d = (form.triagem.desfechos || []).find((x) => x.chave === l.triagem_desfecho)
    return d ? d.rotulo : (l.triagem_desfecho || '—')
  }
  const r = (form.recomendacoes || []).find((x) => x.chave === l.recomendacao)
  return r ? r.rotulo : (l.recomendacao || '—')
}

// --------------------------------------------------------------------------
// Nova entrevista: abre PERTO do botão que a criou, não no topo da tela.
// --------------------------------------------------------------------------

function NovaEntrevista({ inicial, form, aoFechar, aoCriar, aoErro }) {
  const [tipo, setTipo] = useState(inicial.tipo || 'entrevista')
  const [quem, setQuem] = useState('talento')
  const [pessoaId, setPessoaId] = useState('')
  const [vagaId, setVagaId] = useState('')
  const [quando, setQuando] = useState('')
  const [local, setLocal] = useState('')
  // --- v2.66 (§ 14.4) ---
  const [modalidade, setModalidade] = useState('')
  const [linkReuniao, setLinkReuniao] = useState('')
  const [enviarConvite, setEnviarConvite] = useState(false)
  // --- v2.67 (§ 15.5 item 4): a duração vai para o `DTEND` do convite.
  // Nasce em 60, que era a constante até a v2.66 — o RH ajusta quando precisa.
  const [duracao, setDuracao] = useState(60)
  const [talentos, setTalentos] = useState([])
  const [candidatos, setCandidatos] = useState([])
  const [vagas, setVagas] = useState([])
  const [salvando, setSalvando] = useState(false)
  // --- v2.74 ---
  // Cargo e posto para a entrevista SEM vaga cadastrada: o RH conversa para um
  // posto que precisa repor gente, e cadastrar uma vaga só para marcar a
  // conversa é burocracia inventada.
  const [cargo, setCargo] = useState('')
  const [cargoLivre, setCargoLivre] = useState(false)   // "＋ Cargo novo…"
  const [postoId, setPostoId] = useState('')
  const [postos, setPostos] = useState([])
  const [cargosUsados, setCargosUsados] = useState([])
  // Cadastro RÁPIDO da pessoa que ainda não está no banco: nome + WhatsApp,
  // como a admissão faz — começa com o mínimo e completa no caminho. O
  // currículo entra aqui mesmo, que é como ele costuma chegar (por e-mail).
  const [novaPessoa, setNovaPessoa] = useState(null)   // {nome, telefone, arquivo}
  // Mensagem local: o card fica no meio da tela, e um setMsg do pai
  // renderizaria a confirmação fora do campo de visão de quem clicou.
  const [erro, setErro] = useState(null)
  // Separado do `erro` DE PROPÓSITO: o convite saiu. Pintar de vermelho faria o
  // RH achar que a pessoa não foi avisada e reenviar — que não muda nada,
  // porque o que falta é uma liberação no admin do Microsoft 365.
  const [aviso, setAviso] = useState(null)

  // ⚠️ `listarTalentos`, NÃO `api.talentos` (v2.73): a função `api.talentos`
  // NUNCA existiu, e chamá-la derrubava a tela inteira no ErrorBoundary — "Algo
  // deu errado ao abrir esta página" ao clicar em "+ Triagem" ou "+ Entrevista"
  // (relatado pelo Bruno). O `.catch(() => {})` não protegia nada: `undefined()`
  // é `TypeError` SÍNCRONO, estourado antes de existir promessa para capturar.
  // É a família da `prop` inventada (v2.64) e da classe fantasma (v2.25) — o
  // JSX fica plausível e o build passa, porque ninguém confere se o nome existe.
  //
  // E as TRÊS rotas devolvem LISTA PURA (`-> list[dict]`), não `{itens}` nem
  // `{vagas}`: os `r.itens || r.vagas || []` do código antigo devolviam `[]`
  // para sempre. Ou seja, mesmo sem o `TypeError` os três seletores do
  // formulário — pessoa, vaga e candidato — abririam VAZIOS, sem erro nenhum.
  // Corrigir só o nome da função deixaria dois terços do defeito de pé, e mais
  // silenciosos: seletor vazio parece "não há dados cadastrados".
  const _lista = (r) => (Array.isArray(r) ? r : (r?.itens || []))
  useEffect(() => {
    api.listarTalentos().then((r) => setTalentos(_lista(r))).catch(() => {})
    api.vagas().then((r) => setVagas(_lista(r))).catch(() => {})
    api.candidatos && api.candidatos({}).then((r) => setCandidatos(_lista(r))).catch(() => {})
    // v2.74 — cargo e posto para a entrevista sem vaga. Estas DUAS devolvem
    // objeto (`{postos}` / `{cargos}`), ao contrário das três acima: conferido
    // no backend, não suposto — foi exatamente essa suposição que deixou os
    // seletores vazios antes.
    api.postos().then((r) => setPostos(r?.postos || [])).catch(() => {})
    api.cargos().then((r) => setCargosUsados(r?.cargos || [])).catch(() => {})
  }, [])

  const criar = async () => {
    const cadastrando = quem === 'nova'
    if (cadastrando && !(novaPessoa?.nome || '').trim()) {
      setErro('Diga ao menos o nome da pessoa.'); return
    }
    if (!cadastrando && !pessoaId) { setErro('Escolha a pessoa.'); return }
    setSalvando(true)
    setErro(null)
    setAviso(null)
    try {
      // Cadastro rápido ANTES da entrevista (v2.74): a entrevista precisa
      // apontar para alguém. Vai pela MESMA rota do cadastro à mão (v2.73),
      // então herda tudo — nome padronizado, consentimento não fingido, autor
      // registrado. `forcar: true` porque aqui a duplicata não é erro do RH:
      // ele está com a pessoa na frente e não veio conferir cadastro; barrar a
      // conversa por causa de um homônimo seria o sistema atrapalhando.
      let alvoId = pessoaId
      let alvoTipo = quem
      if (cadastrando) {
        const t = await api.cadastrarTalento({
          nome: novaPessoa.nome, telefone: novaPessoa.telefone || null,
          origem: 'Cadastrado na entrevista', forcar: true,
        })
        alvoId = t.id
        alvoTipo = 'talento'
        // O currículo é anexado DEPOIS de existir o talento (a rota precisa do
        // id). Falha aqui NÃO derruba a entrevista — o arquivo se anexa pela
        // ficha, e perder a conversa por causa de um upload seria pior.
        if (novaPessoa.arquivo) {
          try {
            await api.anexarCurriculoTalento(alvoId, novaPessoa.arquivo)
          } catch (e) {
            setAviso(`A pessoa foi cadastrada, mas o currículo não subiu `
              + `(${e.detail || e.message}). Anexe pela ficha dela.`)
          }
        }
      }
      const criada = await api.criarEntrevista({
        tipo,
        talento_id: alvoTipo === 'talento' ? alvoId : null,
        candidato_id: alvoTipo === 'candidato' ? alvoId : null,
        vaga_id: vagaId || null,
        // Sem vaga, é o cargo que diz para que a conversa foi — e é ele que
        // resolve o roteiro. Com vaga, a vaga manda (o backend dá precedência).
        cargo: !vagaId ? (cargo || null) : null,
        posto_id: !vagaId ? (postoId || null) : null,
        // Vazio = "já aconteceu": nasce em `realizada`. Exigir agendamento
        // prévio mataria o módulo — pessoa que aparece na porta é rotina.
        marcada_para: quando ? new Date(quando).toISOString() : null,
        local: local || null,
        modalidade: modalidade || null,
        link_reuniao: linkReuniao || null,
        // Só acompanha quando há data: sem compromisso não há o que durar.
        duracao_min: quando ? Number(duracao) || 60 : null,
        enviar_convite: enviarConvite,
      })
      aoCriar(criada)
      // O convite é ANUNCIADO, nunca engolido: quando não sai (pessoa sem
      // e-mail, SMTP fora do ar), a resposta traz o motivo e a tela o mostra.
      // Silêncio faria o RH acreditar que a pessoa foi avisada.
      if (criada?.convite && !criada.convite.enviado && criada.convite.motivo) {
        setErro(`Entrevista registrada, mas o convite não saiu: ${criada.convite.motivo}`)
        return
      }
      // O convite SAIU, mas do endereço de sempre — o `Send As` do remetente de
      // recrutamento não está liberado no Microsoft 365 (v2.68, cenário 39).
      // Não é erro: é um aviso do que falta configurar. Some sozinho quando o
      // administrador libera, sem ninguém precisar mexer aqui.
      if (criada?.convite?.aviso) setAviso(criada.convite.aviso)
    } catch (e) {
      setErro(e.detail?.erro || e.detail || e.message || 'Não foi possível registrar.')
    } finally { setSalvando(false) }
  }

  const lista = quem === 'talento' ? talentos : candidatos
  return (
    <div className="rh-card">
      <div className="rh-topo">
        <h3>{tipo === 'triagem' ? 'Nova triagem' : 'Nova entrevista'}</h3>
        <button className="btn-secundario btn-mini" onClick={aoFechar}>✕ fechar</button>
      </div>

      <div className="rh-grid-2">
        <div className="campo">
          <span className="rotulo">Tipo</span>
          <SelectBusca valor={tipo} aoEscolher={setTipo}>
            <option value="triagem">Triagem (checagem por telefone, sem nota)</option>
            <option value="entrevista">Entrevista (avaliação ancorada)</option>
          </SelectBusca>
        </div>
        <div className="campo">
          <span className="rotulo">A pessoa é</span>
          {/* "Ainda não cadastrada" (v2.74): a pessoa que aparece na porta ou
              manda currículo por e-mail não está em lista nenhuma, e antes o
              formulário simplesmente não tinha o que oferecer. Ao escolher,
              abre o cadastro rápido logo abaixo — e o que ela cadastrar já
              entra no Banco de Talentos, então da próxima vez está na lista. */}
          <SelectBusca valor={quem}
                       aoEscolher={(v) => {
                         setQuem(v); setPessoaId('')
                         setNovaPessoa(v === 'nova' ? { nome: '', telefone: '', arquivo: null } : null)
                       }}>
            <option value="talento">Do Banco de Talentos</option>
            <option value="candidato">Candidato / colaborador</option>
            <option value="nova">Ainda não cadastrada — cadastrar agora</option>
          </SelectBusca>
        </div>
        {quem !== 'nova' && (
          <div className="campo">
            <span className="rotulo">Pessoa</span>
            <SelectBusca valor={pessoaId} aoEscolher={setPessoaId}
                         opcoes={lista.map((p) => ({
                           valor: p.id, rotulo: p.nome || p.nome_completo,
                           extra: p.cargo_interesse || p.cargo_funcao || '',
                         }))} />
          </div>
        )}
        {/* CADASTRO RÁPIDO (v2.74): o MÍNIMO para a conversa acontecer — nome e
            WhatsApp —, como a admissão faz (começa com o convite e completa no
            caminho). O currículo entra aqui porque é assim que ele chega: por
            e-mail, antes da conversa. O resto se preenche depois, pela ficha.
            A pessoa entra no Banco de Talentos, então da próxima vez já está na
            lista — e SEM consentimento fingido (v2.73). */}
        {quem === 'nova' && novaPessoa && (
          <div className="campo" style={{ gridColumn: '1 / -1' }}>
            <span className="rotulo">Cadastrar a pessoa
              <span className="dica-inline"> — nome e WhatsApp bastam; o resto entra depois</span></span>
            <div className="rh-grid-2">
              <label className="campo">
                <span className="rotulo">Nome</span>
                <input value={novaPessoa.nome} autoComplete="off"
                       placeholder="Como a pessoa se apresentou"
                       onChange={(e) => setNovaPessoa({ ...novaPessoa, nome: e.target.value })} />
              </label>
              <label className="campo">
                <span className="rotulo">WhatsApp</span>
                <input value={novaPessoa.telefone} autoComplete="off"
                       placeholder="(61) 9…"
                       onChange={(e) => setNovaPessoa({ ...novaPessoa, telefone: e.target.value })} />
              </label>
            </div>
            <label className="campo">
              <span className="rotulo">Currículo
                <span className="dica-inline"> — opcional; PDF, foto ou Word</span></span>
              <input type="file" accept=".pdf,.jpg,.jpeg,.png,.heic,.webp,.doc,.docx"
                     onChange={(e) => setNovaPessoa({
                       ...novaPessoa, arquivo: e.target.files?.[0] || null })} />
            </label>
            <p className="explica">
              Entra no Banco de Talentos <strong>sem consentimento LGPD
              registrado</strong> (a pessoa não está aqui para aceitar) — fica
              gravado que foi você quem cadastrou.
            </p>
          </div>
        )}
        <div className="campo">
          <span className="rotulo">Vaga
            <span className="dica-inline"> — opcional; conversa exploratória é caso real</span></span>
          {/* Nullable de propósito: conversa exploratória é caso real. */}
          <SelectBusca valor={vagaId} aoEscolher={setVagaId}
                       opcoes={[{ valor: '', rotulo: '— sem vaga —' },
                                ...vagas.map((v) => ({ valor: v.id, rotulo: v.titulo }))]} />
        </div>
        {/* CARGO e POSTO só aparecem SEM vaga escolhida (v2.74): com a vaga, é
            ela que diz para que a conversa foi, e mostrar três campos dizendo a
            mesma coisa faria o RH preencher dois por engano — um assunto, um
            controle (regra da v2.30). O cargo, além de registrar, é o que
            resolve qual ROTEIRO vale (herança cargo → padrão). */}
        {!vagaId && (
          <>
            <div className="campo">
              <span className="rotulo">Cargo
                <span className="dica-inline"> — decide o roteiro da entrevista</span></span>
              {/* Lista os cargos JÁ USADOS na base (mais frequentes primeiro),
                  com "＋ Cargo novo…" trocando para input livre — o mesmo padrão
                  do `Detalhe.jsx` e do convite. Escolher da lista evita
                  "Vigia"/"vigia"/"Vigía" virando três cargos (regra da v1.82).
                  ⚠️ NÃO existe prop `permiteNovo` no `SelectBusca`: prop
                  inventada é ignorada em silêncio pelo React (v2.64), e o campo
                  pareceria funcionar sem nunca aceitar cargo novo. */}
              {cargoLivre ? (
                <input value={cargo} autoComplete="off" autoFocus
                       placeholder="Digite o cargo"
                       onChange={(e) => setCargo(e.target.value)} />
              ) : (
                <SelectBusca valor={cargo}
                             aoEscolher={(v) => {
                               if (v === '__novo') { setCargoLivre(true); setCargo('') }
                               else setCargo(v)
                             }}
                             opcoes={[
                               { valor: '', rotulo: '— não informado —' },
                               ...cargosUsados.map((c) => ({
                                 valor: c.nome, rotulo: c.nome,
                                 extra: c.pessoas ? `${c.pessoas} pessoa(s)` : '',
                               })),
                               { valor: '__novo', rotulo: '＋ Cargo novo…' },
                             ]} />
              )}
            </div>
            <div className="campo">
              <span className="rotulo">Posto
                <span className="dica-inline"> — para qual contrato é a conversa</span></span>
              <SelectBusca valor={postoId} aoEscolher={setPostoId}
                           opcoes={[{ valor: '', rotulo: '— não informado —' },
                                    ...postos.map((p) => ({
                                      valor: p.id, rotulo: p.sigla || p.nome,
                                      extra: p.sigla ? p.nome : '',
                                    }))]} />
            </div>
          </>
        )}
        {/* `datetime-local` e não o `InputData` do projeto: aquele componente é
            de DATA (máscara dd/mm/aaaa, `maxLength={10}`, guarda ISO
            aaaa-mm-dd) e não tem hora — e entrevista sem hora não se marca.
            Registrado na v2.65 para não parecer descuido. */}
        <label className="campo">
          <span className="rotulo">Marcada para
            <span className="dica-inline"> — em branco = já aconteceu, nasce realizada</span></span>
          <input type="datetime-local" value={quando}
                 onChange={(e) => setQuando(e.target.value)} />
        </label>
        {/* Duração (v2.67, § 15.5 item 4) — só aparece com data marcada, porque
            é ela que vira o `DTEND` do convite. Zero é recusado no servidor
            (fim antes do começo faz o calendário descartar o evento). */}
        {quando && (
          <label className="campo">
            <span className="rotulo">Duração (minutos)
              <span className="dica-inline"> — é o que o convite reserva na
                agenda da pessoa</span></span>
            <input type="number" min="1" max="1440" value={duracao}
                   onChange={(e) => setDuracao(e.target.value)} />
          </label>
        )}
        <div className="campo">
          <span className="rotulo">Modalidade</span>
          <SelectBusca valor={modalidade} aoEscolher={setModalidade}>
            <option value="">— não informada —</option>
            <option value="presencial">Presencial</option>
            <option value="online">Online (Teams)</option>
          </SelectBusca>
        </div>
        {/* A modalidade decide qual campo aparece: endereço no presencial,
            link no online. Os dois ao mesmo tempo fariam o RH preencher o que
            não vale, e o e-mail sairia com a informação errada. */}
        {modalidade === 'online' ? (
          <label className="campo">
            <span className="rotulo">Link da reunião
              <span className="dica-inline"> — obrigatório no online: sem ele o
                convite chega sem dizer por onde entrar</span></span>
            <input value={linkReuniao} onChange={(e) => setLinkReuniao(e.target.value)}
                   placeholder="https://teams.microsoft.com/…" />
          </label>
        ) : (
          <label className="campo">
            <span className="rotulo">Local</span>
            <input value={local} onChange={(e) => setLocal(e.target.value)}
                   placeholder="telefone, sede, vídeo…" />
          </label>
        )}
      </div>

      {/* O convite só faz sentido com data marcada: entrevista registrada como
          já realizada não tem o que agendar. */}
      {quando && (
        <label className="campo-sem-margem">
          <input type="checkbox" checked={enviarConvite}
                 onChange={(e) => setEnviarConvite(e.target.checked)} />
          {' '}Avisar a pessoa por e-mail e mandar o convite de calendário
          <span className="dica-inline"> — se ela não tiver e-mail no cadastro,
            o sistema avisa aqui em vez de falhar calado</span>
        </label>
      )}

      {erro && <p className="alerta">{erro}</p>}
      {aviso && <p className="aviso-inline">⚠️ {aviso}</p>}
      <div className="rh-conferencia-acoes">
        <button className="btn-principal btn-mini" onClick={criar} disabled={salvando}>
          {salvando ? 'Registrando…' : 'Registrar'}
        </button>
      </div>
    </div>
  )
}
