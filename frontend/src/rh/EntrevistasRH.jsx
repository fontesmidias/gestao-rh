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
      valor: (l) => l.vaga_titulo || '—',
      render: (l) => (
        <>
          {l.vaga_titulo || '—'}
          {l.vaga_titulo && !l.vaga_existe &&
            <> <span className="chip" title="A vaga foi excluída; o título ficou registrado.">vaga excluída</span></>}
        </>
      ) },
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
  const [talentos, setTalentos] = useState([])
  const [candidatos, setCandidatos] = useState([])
  const [vagas, setVagas] = useState([])
  const [salvando, setSalvando] = useState(false)
  // Mensagem local: o card fica no meio da tela, e um setMsg do pai
  // renderizaria a confirmação fora do campo de visão de quem clicou.
  const [erro, setErro] = useState(null)

  useEffect(() => {
    api.talentos().then((r) => setTalentos(r.itens || r.talentos || [])).catch(() => {})
    api.vagas().then((r) => setVagas(r.vagas || r.itens || [])).catch(() => {})
    api.candidatos && api.candidatos({}).then((r) =>
      setCandidatos(r.itens || r.candidatos || [])).catch(() => {})
  }, [])

  const criar = async () => {
    if (!pessoaId) { setErro('Escolha a pessoa.'); return }
    setSalvando(true)
    setErro(null)
    try {
      const criada = await api.criarEntrevista({
        tipo,
        talento_id: quem === 'talento' ? pessoaId : null,
        candidato_id: quem === 'candidato' ? pessoaId : null,
        vaga_id: vagaId || null,
        // Vazio = "já aconteceu": nasce em `realizada`. Exigir agendamento
        // prévio mataria o módulo — pessoa que aparece na porta é rotina.
        marcada_para: quando ? new Date(quando).toISOString() : null,
        local: local || null,
      })
      aoCriar(criada)
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
          <SelectBusca valor={quem} aoEscolher={(v) => { setQuem(v); setPessoaId('') }}>
            <option value="talento">Do Banco de Talentos</option>
            <option value="candidato">Candidato / colaborador</option>
          </SelectBusca>
        </div>
        <div className="campo">
          <span className="rotulo">Pessoa</span>
          <SelectBusca valor={pessoaId} aoEscolher={setPessoaId}
                       opcoes={lista.map((p) => ({
                         valor: p.id, rotulo: p.nome || p.nome_completo,
                         extra: p.cargo_interesse || p.cargo_funcao || '',
                       }))} />
        </div>
        <div className="campo">
          <span className="rotulo">Vaga
            <span className="dica-inline"> — opcional; conversa exploratória é caso real</span></span>
          {/* Nullable de propósito: conversa exploratória é caso real. */}
          <SelectBusca valor={vagaId} aoEscolher={setVagaId}
                       opcoes={[{ valor: '', rotulo: '— sem vaga —' },
                                ...vagas.map((v) => ({ valor: v.id, rotulo: v.titulo }))]} />
        </div>
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
        <label className="campo">
          <span className="rotulo">Local</span>
          <input value={local} onChange={(e) => setLocal(e.target.value)}
                 placeholder="telefone, sede, vídeo…" />
        </label>
      </div>

      {erro && <p className="alerta">{erro}</p>}
      <div className="rh-conferencia-acoes">
        <button className="btn-principal btn-mini" onClick={criar} disabled={salvando}>
          {salvando ? 'Registrando…' : 'Registrar'}
        </button>
      </div>
    </div>
  )
}
