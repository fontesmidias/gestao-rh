import { useEffect, useState } from 'react'
import { rh as api } from '../api.js'
import DashPlanilha from './DashPlanilha.jsx'

// Cadastro de Desenvolvimento — painel do RH (Onda B).
//
// Duas abas: a FILA (o que os colaboradores enviaram) e os TIPOS (catálogo
// configurável). A fila é o risco operacional do módulo: ~10 validações por dia
// útil quando os 1.200 estiverem cadastrando. Por isso a aprovação em LOTE —
// mas documento crítico (brigada, NR) nunca entra nela.
export default function DesenvolvimentoRH({ aoVoltar }) {
  const [aba, setAba] = useState('fila')
  return (
    <section>
      <div className="rh-topo">
        <h1>🎓 Desenvolvimento</h1>
        <button className="btn-secundario btn-mini" onClick={aoVoltar}>← voltar</button>
      </div>
      <div className="rh-abas">
        <button className={aba === 'fila' ? 'ativa' : ''} onClick={() => setAba('fila')}>
          Fila de validação</button>
        <button className={aba === 'brigada' ? 'ativa' : ''} onClick={() => setAba('brigada')}>
          Brigada &amp; reciclagem</button>
        <button className={aba === 'tipos' ? 'ativa' : ''} onClick={() => setAba('tipos')}>
          Tipos e prazos</button>
      </div>
      {aba === 'fila' && <Fila />}
      {aba === 'brigada' && <Brigada />}
      {aba === 'tipos' && <Tipos />}
    </section>
  )
}

// --------------------------------------------------------------------------
// Fila de validação
// --------------------------------------------------------------------------

const ROTULO_PAPEL = {
  identidade: 'Documento com foto', certificado_formacao: 'Certificado de formação',
  certificado_reciclagem: 'Certificado de reciclagem', aso: 'Atestado de saúde',
  outro: 'Documento',
}

function Fila() {
  const [dados, setDados] = useState(null)
  const [filtroStatus, setFiltroStatus] = useState('')   // '' = aguardando decisão
  const [msg, setMsg] = useState(null)
  const [abrindo, setAbrindo] = useState(null)           // registro em conferência

  const carregar = () => api.desenvolvimentoRegistros(filtroStatus)
    .then(setDados).catch((e) => setMsg({ tipo: 'erro', texto: e.detail || e.message }))
  useEffect(() => { carregar() }, [filtroStatus])

  if (!dados) return <p className="explica">Carregando…</p>

  const colunas = [
    { chave: 'colaborador', rotulo: 'Colaborador', ordenavel: true, filtro: 'texto',
      sempreVisivel: true },
    { chave: 'cargo', rotulo: 'Cargo', ordenavel: true, filtro: 'texto', quebra: true },
    { chave: 'posto', rotulo: 'Posto', ordenavel: true, filtro: 'texto', quebra: true,
      oculta: true },
    { chave: 'tipo', rotulo: 'Tipo', ordenavel: true, filtro: 'texto' },
    { chave: 'titulo', rotulo: 'Curso', ordenavel: true, filtro: 'texto', quebra: true },
    { chave: 'concluido_em', rotulo: 'Concluído', ordenavel: true,
      render: (l) => fmt(l.concluido_em) },
    { chave: 'validade_ate', rotulo: 'Validade', ordenavel: true,
      render: (l) => fmt(l.validade_ate) },
    { chave: 'critico', rotulo: 'Criticidade', filtro: 'select',
      opcoes: ['Crítico', 'Comum'],
      valor: (l) => (l.critico ? 'Crítico' : 'Comum'),
      render: (l) => (l.critico
        ? <span className="chip" style={{ '--chip-cor': '#e5484d' }}>Crítico</span>
        : <span className="chip">Comum</span>) },
    { chave: 'status', rotulo: 'Situação', filtro: 'select',
      opcoes: ['Em análise', 'Validado', 'Devolvido', 'Não aceito'],
      valor: (l) => ROTULO_STATUS[l.status] || l.status,
      render: (l) => <ChipStatus registro={l} /> },
    { chave: 'documentos', rotulo: 'Docs', valor: (l) => l.documentos.length },
  ]

  const cards = [
    { rotulo: 'Aguardando', valor: dados.metricas.pendente || 0, cor: '#f5a623' },
    { rotulo: 'Devolvidos', valor: dados.metricas.devolvido || 0, cor: '#e5484d' },
    { rotulo: 'Validados', valor: dados.metricas.validado || 0, cor: '#0a8f46' },
  ]

  const validarLote = async (linhas, limpar) => {
    setMsg(null)
    try {
      const r = await api.desenvolvimentoValidarLote(linhas.map((l) => l.id))
      const barrados = r.barrados || []
      setMsg({
        tipo: barrados.length ? 'aviso' : 'ok',
        texto: `${r.validados.length} validado(s).` + (barrados.length
          ? ` ${barrados.length} ficaram de fora e precisam ser conferidos um a um: `
            + barrados.map((b) => `${b.colaborador} (${b.motivo})`).join('; ')
          : '') })
      limpar(); carregar()
    } catch (e) { setMsg({ tipo: 'erro', texto: e.detail || e.message }) }
  }

  return (
    <>
      <div className="rh-lote" style={{ margin: '.4rem 0 1rem' }}>
        <strong>Mostrar:</strong>
        <select value={filtroStatus} style={{ maxWidth: 220 }}
                onChange={(e) => setFiltroStatus(e.target.value)}>
          <option value="">Aguardando decisão</option>
          <option value="validado">Validados</option>
          <option value="recusado">Não aceitos</option>
          <option value="pendente,validado,recusado,devolvido">Todos</option>
        </select>
      </div>
      <Msg msg={msg} />

      <DashPlanilha
        id="desenvolvimento-fila" colunas={colunas} dados={dados.registros} cards={cards}
        vazio="Nada aguardando validação. 🎉"
        // o detalhe abre LOGO ABAIXO da linha clicada, não no topo da página
        linhaExpandida={(l) => (abrindo === l.id ? (
          // `key`: o form guarda o estado inicial da prop — sem isso, reabrir
          // outro registro reaproveitaria os campos do anterior
          <Conferencia key={l.id} registro={l}
                       aoFechar={() => { setAbrindo(null); carregar() }}
                       aoErro={(t) => setMsg({ tipo: 'erro', texto: t })} />
        ) : null)}
        acoesLinha={(l) => (
          <button className={`btn-${abrindo === l.id ? 'principal' : 'secundario'} btn-mini`}
                  onClick={() => setAbrindo(abrindo === l.id ? null : l.id)}>
            {abrindo === l.id ? 'Fechar' : 'Conferir'}</button>
        )}
        acoesMassa={(linhas, limpar) => (
          <button className="btn-principal btn-mini"
                  onClick={() => validarLote(linhas, limpar)}>
            ✔ Validar {linhas.length} selecionado(s)</button>
        )} />
      <p className="explica" style={{ marginTop: '.8rem' }}>
        Documento <strong>crítico</strong> (brigada, NR) não é validado em lote —
        precisa ser conferido um a um. Se você marcar um, o sistema avisa e deixa
        os demais passarem.</p>
    </>
  )
}

// --------------------------------------------------------------------------
// Conferência de um registro (documento de um lado, campos do outro)
// --------------------------------------------------------------------------

function Conferencia({ registro, aoFechar, aoErro }) {
  const [campos, setCampos] = useState({
    titulo: registro.titulo || '', instituicao: registro.instituicao || '',
    carga_horaria: registro.carga_horaria || '',
    concluido_em: registro.concluido_em || '',
  })
  const [motivo, setMotivo] = useState('')
  const [acao, setAcao] = useState(null)      // devolver | recusar
  const [salvando, setSalvando] = useState(false)

  const executar = async (fn) => {
    setSalvando(true)
    try { await fn(); aoFechar() }
    catch (e) { aoErro(e.detail || e.message) }
    finally { setSalvando(false) }
  }

  const ia = registro.extraido_ia || {}
  const sugeriu = Object.values(ia).some((v) => v && Object.keys(v).length)

  return (
    <div className="rh-conferencia">
      <div className="rh-conferencia-topo">
        <div>
          <h3>{registro.colaborador}</h3>
          <span className="explica">
            {[registro.cargo, registro.posto, registro.tipo].filter(Boolean).join(' · ')}
          </span>
          {registro.critico && (
            <div style={{ marginTop: '.35rem' }}>
              <span className="chip" style={{ '--chip-cor': '#e5484d' }}>
                Crítico — confira com atenção</span>
            </div>
          )}
        </div>
        <button className="btn-secundario btn-mini" onClick={aoFechar}>✕ fechar</button>
      </div>

      <div className="rh-conferencia-corpo">
        <div className="rh-conferencia-docs">
          <span className="rh-conferencia-bloco-titulo">Documentos enviados</span>
          {registro.documentos.length === 0 && (
            <p className="explica">Nenhum documento anexado.</p>
          )}
          {registro.documentos.map((d) => (
            <div key={d.id} className="portal-doc ok">
              <div>
                <strong>{ROTULO_PAPEL[d.papel] || d.papel}</strong>
                <div className="explica" style={{ margin: 0 }}>
                  {d.nome || 'arquivo'}
                  {d.sensibilidade === 'saude' && ' · dado sensível'}
                </div>
              </div>
              {/* rota autenticada: baixa como blob e abre em aba nova (o href
                  direto não levaria o token do RH) */}
              <button className="btn-secundario btn-mini" onClick={async () => {
                try {
                  const blob = await api.desenvolvimentoDocumento(registro.id, d.id)
                  const url = URL.createObjectURL(blob)
                  window.open(url, '_blank')
                  setTimeout(() => URL.revokeObjectURL(url), 30000)
                } catch (e) { aoErro(`Não foi possível abrir (${e.detail || e.message}).`) }
              }}>Abrir</button>
            </div>
          ))}
        </div>

        <div className="rh-conferencia-campos">
          <span className="rh-conferencia-bloco-titulo">O que a pessoa informou</span>
          {sugeriu && (
            <p className="explica" style={{ margin: '0 0 .6rem' }}>
              ✨ A leitura automática propôs campos; a pessoa confirmou o que está abaixo.
            </p>
          )}
          <label className="campo"><span className="rotulo">Curso</span>
            <input value={campos.titulo}
                   onChange={(e) => setCampos({ ...campos, titulo: e.target.value })} /></label>
          <label className="campo"><span className="rotulo">Instituição</span>
            <input value={campos.instituicao}
                   onChange={(e) => setCampos({ ...campos, instituicao: e.target.value })} /></label>
          <div className="linha2">
            <label className="campo"><span className="rotulo">Carga horária</span>
              <input value={campos.carga_horaria}
                     onChange={(e) => setCampos({ ...campos, carga_horaria: e.target.value })} /></label>
            <label className="campo"><span className="rotulo">Conclusão</span>
              <input type="date" value={campos.concluido_em}
                     onChange={(e) => setCampos({ ...campos, concluido_em: e.target.value })} /></label>
          </div>
          {registro.observacao && (
            <p className="explica">Observação: {registro.observacao}</p>
          )}
        </div>
      </div>

      {acao && (
        <div className="campo" style={{ marginTop: '1rem', marginBottom: 0 }}>
          <span className="rotulo">
            {acao === 'devolver' ? 'O que a pessoa precisa corrigir?'
              : 'Por que não pode ser aceito?'}</span>
          <textarea rows={2} value={motivo} autoFocus
                    placeholder="Ex.: o certificado está ilegível, envie outra foto."
                    onChange={(e) => setMotivo(e.target.value)} />
          <span className="dica-inline">⚠️ Este texto é lido pelo colaborador —
            escreva o que ele precisa fazer.</span>
        </div>
      )}

      <div className="rh-conferencia-acoes">
        {!acao && (
          <>
            <button className="btn-principal btn-mini" disabled={salvando}
                    onClick={() => executar(() =>
                      api.desenvolvimentoValidar(registro.id, campos))}>
              ✔ Validar</button>
            <button className="btn-secundario btn-mini"
                    onClick={() => setAcao('devolver')}>↩ Devolver para correção</button>
            <button className="btn-secundario btn-mini"
                    onClick={() => setAcao('recusar')}>✕ Não aceitar</button>
          </>
        )}
        {acao && (
          <>
            <button className="btn-principal btn-mini"
                    disabled={salvando || !motivo.trim()}
                    onClick={() => executar(() => (acao === 'devolver'
                      ? api.desenvolvimentoDevolver(registro.id, motivo)
                      : api.desenvolvimentoRecusar(registro.id, motivo)))}>
              Confirmar</button>
            <button className="btn-link" onClick={() => { setAcao(null); setMotivo('') }}>
              cancelar</button>
          </>
        )}
      </div>
    </div>
  )
}

const ROTULO_STATUS = {
  pendente: 'Em análise', validado: 'Validado',
  devolvido: 'Devolvido', recusado: 'Não aceito',
}

function ChipStatus({ registro: r }) {
  const cores = { pendente: '#f5a623', validado: '#0a8f46',
                  devolvido: '#e5484d', recusado: '#e5484d' }
  // O PRAZO manda sobre o status: certificado validado que já venceu é um
  // problema, não uma conquista.
  if (r.status === 'validado' && r.situacao_validade === 'vencido') {
    return <span className="chip" style={{ '--chip-cor': '#e5484d' }}>Vencido</span>
  }
  if (r.status === 'validado' && r.situacao_validade === 'a_vencer') {
    return <span className="chip" style={{ '--chip-cor': '#f5a623' }}>A vencer</span>
  }
  if (r.status === 'validado' && r.situacao_validade === 'valido') {
    return <span className="chip" style={{ '--chip-cor': '#0a8f46' }}>Válido</span>
  }
  return <span className="chip" style={{ '--chip-cor': cores[r.status] }}>
    {ROTULO_STATUS[r.status] || r.status}</span>
}

function fmt(iso) {
  if (!iso) return '—'
  const [a, m, d] = iso.split('-')
  return `${d}/${m}/${a}`
}

// --------------------------------------------------------------------------
// Brigada & reciclagem — quem vence, quem já pode ser matriculado
// --------------------------------------------------------------------------

function Brigada() {
  const [dados, setDados] = useState(null)
  const [turmas, setTurmas] = useState([])
  const [msg, setMsg] = useState(null)
  const [rascunho, setRascunho] = useState(null)   // e-mails montados
  const [novaTurma, setNovaTurma] = useState(false)

  const carregar = () => Promise.all([
    api.desenvolvimentoBrigadistas(), api.desenvolvimentoTurmas(),
  ]).then(([b, t]) => { setDados(b); setTurmas(t.turmas) })
    .catch((e) => setMsg({ tipo: 'erro', texto: e.detail || e.message }))
  useEffect(() => { carregar() }, [])
  if (!dados) return <p className="explica">Carregando…</p>

  const colunas = [
    { chave: 'colaborador', rotulo: 'Colaborador', ordenavel: true, filtro: 'texto',
      sempreVisivel: true },
    { chave: 'posto', rotulo: 'Posto', ordenavel: true, filtro: 'texto', quebra: true },
    { chave: 'cargo', rotulo: 'Cargo', ordenavel: true, filtro: 'texto', quebra: true,
      oculta: true },
    { chave: 'validade_ate', rotulo: 'Vence em', ordenavel: true,
      valor: (l) => l.validade_ate || '',
      render: (l) => (
        <span>{fmt(l.validade_ate)}
          {l.dias_para_vencer != null && (
            <small style={{ display: 'block', color: 'var(--cinza-txt)' }}>
              {l.dias_para_vencer >= 0 ? `em ${l.dias_para_vencer} dias`
                : `há ${-l.dias_para_vencer} dias`}</small>)}
        </span>) },
    { chave: 'situacao_validade', rotulo: 'Situação', filtro: 'select',
      opcoes: ['Vencido', 'A vencer', 'Válido'],
      valor: (l) => ({ vencido: 'Vencido', a_vencer: 'A vencer',
                       valido: 'Válido' }[l.situacao_validade] || '—'),
      render: (l) => <ChipStatus registro={l} /> },
    { chave: 'pronto', rotulo: 'Dossiê', filtro: 'select',
      opcoes: ['Pronto', 'Incompleto'],
      valor: (l) => (l.pronto ? 'Pronto' : 'Incompleto'),
      quebra: true,
      render: (l) => (l.pronto
        ? <span className="chip" style={{ '--chip-cor': '#0a8f46' }}>Pronto</span>
        : <span className="aviso-pendente">⚠️ falta {l.pendencias.join(', ')}</span>) },
  ]

  const cards = [
    { rotulo: 'Vencidos', valor: dados.metricas.vencidos, cor: '#e5484d',
      filtro: { chave: 'situacao_validade', valor: 'Vencido' } },
    { rotulo: 'A vencer', valor: dados.metricas.a_vencer, cor: '#f5a623',
      filtro: { chave: 'situacao_validade', valor: 'A vencer' } },
    { rotulo: 'Prontos p/ matrícula', valor: dados.metricas.prontos, cor: '#0a8f46',
      filtro: { chave: 'pronto', valor: 'Pronto' } },
  ]

  const montar = async (linhas, agrupar) => {
    setMsg(null)
    try {
      const r = await api.desenvolvimentoRascunhoMatricula({
        registro_ids: linhas.map((l) => l.id),
        turma_id: turmas[0] ? turmas[0].id : null,
        agrupar,
      })
      setRascunho({ ...r, agrupar, registro_ids: linhas.map((l) => l.id) })
    } catch (e) { setMsg({ tipo: 'erro', texto: e.detail || e.message }) }
  }

  return (
    <>
      <p className="explica" style={{ marginTop: '.4rem' }}>
        Quem tem certificação <strong>crítica</strong> vencendo. Marque quem vai para a
        reciclagem e o sistema monta o e-mail para a entidade formadora, com o dossiê
        de cada um em anexo.</p>
      <Msg msg={msg} />

      <div className="rh-card" style={{ marginBottom: '.8rem' }}>
        <div className="rh-topo" style={{ marginBottom: '.3rem' }}>
          <strong>Próximas turmas</strong>
          <button className="btn-secundario btn-mini"
                  onClick={() => setNovaTurma(!novaTurma)}>
            {novaTurma ? 'cancelar' : '＋ Nova turma'}</button>
        </div>
        {turmas.length === 0 && !novaTurma && (
          <p className="explica" style={{ margin: 0 }}>Nenhuma turma cadastrada — você
            pode informar a data na hora de montar o e-mail.</p>
        )}
        {turmas.map((t) => (
          <p className="explica" key={t.id} style={{ margin: '.2rem 0' }}>
            📅 <strong>{fmt(t.inicio_em)}</strong> · {t.periodo} · {t.entidade}
            {t.email_destino && ` · ${t.email_destino}`}
          </p>
        ))}
        {novaTurma && (
          <FormTurma aoFechar={() => { setNovaTurma(false); carregar() }}
                     aoErro={(t) => setMsg({ tipo: 'erro', texto: t })} />
        )}
      </div>

      {rascunho && (
        <RevisarEmail rascunho={rascunho} turmas={turmas}
                      aoFechar={() => setRascunho(null)}
                      aoEnviado={(n) => {
                        setRascunho(null); carregar()
                        setMsg({ tipo: 'ok', texto: `Solicitação enviada (${n} destinatário(s)).` })
                      }}
                      aoErro={(t) => setMsg({ tipo: 'erro', texto: t })} />
      )}

      <DashPlanilha
        id="desenvolvimento-brigada" colunas={colunas} dados={dados.brigadistas}
        cards={cards} vazio="Ninguém com certificação crítica cadastrada ainda."
        acoesLinha={(l) => (
          <button className="btn-secundario btn-mini" onClick={async () => {
            try {
              const blob = await api.desenvolvimentoDossie(l.id)
              const url = URL.createObjectURL(blob)
              window.open(url, '_blank')
              setTimeout(() => URL.revokeObjectURL(url), 30000)
            } catch (e) {
              setMsg({ tipo: 'erro', texto: e.detail === 'dossie_vazio'
                ? 'Sem documentos legíveis para montar o dossiê.'
                : (e.detail || e.message) })
            }
          }}>Ver dossiê</button>
        )}
        acoesMassa={(linhas) => (
          <>
            <button className="btn-principal btn-mini"
                    onClick={() => montar(linhas, true)}>
              ✉ Um e-mail com os {linhas.length}</button>
            <button className="btn-secundario btn-mini"
                    onClick={() => montar(linhas, false)}>
              ✉ Um e-mail para cada</button>
          </>
        )} />
    </>
  )
}

// Revisão antes do envio: o RH LÊ e edita o texto, depois manda. É o passo que
// o Bruno pediu — "colocar para gerar o e-mail, conferir e posteriormente enviar".
function RevisarEmail({ rascunho, turmas, aoFechar, aoEnviado, aoErro }) {
  const [i, setI] = useState(0)               // qual e-mail (quando é 1 por pessoa)
  const [edicao, setEdicao] = useState(() =>
    rascunho.rascunhos.map((r) => ({ ...r, destinatarios: r.destinatarios.join(', ') })))
  const [enviando, setEnviando] = useState(false)
  const atual = edicao[i]
  if (!atual) return null

  const mexer = (campo, valor) =>
    setEdicao(edicao.map((e, j) => (j === i ? { ...e, [campo]: valor } : e)))

  const enviar = async () => {
    setEnviando(true)
    try {
      let total = 0
      for (const e of edicao) {
        const r = await api.desenvolvimentoEnviarMatricula({
          registro_ids: e.colaboradores.map((p) => p.registro_id),
          destinatarios: e.destinatarios.split(',').map((x) => x.trim()).filter(Boolean),
          assunto: e.assunto, corpo: e.corpo, corpo_html: e.corpo_html || null,
          turma_id: turmas[0] ? turmas[0].id : null,
        })
        total += r.enviados
      }
      aoEnviado(total)
    } catch (e) {
      aoErro(e.detail && e.detail.erro === 'dossie_incompleto'
        ? `Falta documento de: ${e.detail.faltando.map((f) => f.nome).join(', ')}`
        : e.detail === 'email_nao_enviado'
          ? 'O e-mail não pôde ser enviado — confira a configuração de e-mail.'
          : (e.detail || e.message))
    } finally { setEnviando(false) }
  }

  return (
    <div className="rh-card rh-conferencia" style={{ marginBottom: '.8rem' }}>
      <div className="rh-conferencia-topo">
        <div>
          <h3>Conferir antes de enviar</h3>
          <span className="explica">
            {edicao.length > 1
              ? `E-mail ${i + 1} de ${edicao.length} — um por colaborador`
              : `Um e-mail com ${atual.colaboradores.length} colaborador(es)`}
          </span>
        </div>
        <button className="btn-secundario btn-mini" onClick={aoFechar}>✕ fechar</button>
      </div>

      {!rascunho.pode_enviar && (
        <div className="alerta">
          <strong>Não dá para enviar ainda.</strong> Falta documento de:{' '}
          {rascunho.incompletos.map((c) => `${c.nome} (${c.pendencias.join(', ')})`).join('; ')}
        </div>
      )}

      <label className="campo"><span className="rotulo">Para</span>
        <input value={atual.destinatarios} placeholder="matriculas@multicursos.com.br"
               onChange={(e) => mexer('destinatarios', e.target.value)} /></label>
      <label className="campo"><span className="rotulo">Assunto</span>
        <input value={atual.assunto}
               onChange={(e) => mexer('assunto', e.target.value)} /></label>
      <label className="campo"><span className="rotulo">Mensagem</span>
        <textarea rows={12} value={atual.corpo}
                  onChange={(e) => mexer('corpo', e.target.value)} /></label>
      <p className="explica">📎 Anexos: {atual.anexos.join(', ')}</p>

      <div className="rh-conferencia-acoes">
        {edicao.length > 1 && (
          <>
            <button className="btn-secundario btn-mini" disabled={i === 0}
                    onClick={() => setI(i - 1)}>← anterior</button>
            <button className="btn-secundario btn-mini" disabled={i === edicao.length - 1}
                    onClick={() => setI(i + 1)}>próximo →</button>
          </>
        )}
        <button className="btn-principal btn-mini"
                disabled={enviando || !rascunho.pode_enviar
                          || !atual.destinatarios.trim()}
                onClick={enviar}>
          {enviando ? 'Enviando…'
            : edicao.length > 1 ? `Enviar os ${edicao.length} e-mails` : 'Enviar'}</button>
      </div>
    </div>
  )
}

function FormTurma({ aoFechar, aoErro }) {
  const [f, setF] = useState({ inicio_em: '', periodo: 'noturno',
                               entidade: 'Multicursos', email_destino: '' })
  const [salvando, setSalvando] = useState(false)
  return (
    <div className="linha2" style={{ marginTop: '.5rem' }}>
      <label className="campo"><span className="rotulo">Início</span>
        <input type="date" value={f.inicio_em}
               onChange={(e) => setF({ ...f, inicio_em: e.target.value })} /></label>
      <label className="campo"><span className="rotulo">Período</span>
        <select value={f.periodo} onChange={(e) => setF({ ...f, periodo: e.target.value })}>
          <option value="noturno">Noturno</option>
          <option value="diurno">Diurno</option>
        </select></label>
      <label className="campo"><span className="rotulo">Entidade</span>
        <input value={f.entidade}
               onChange={(e) => setF({ ...f, entidade: e.target.value })} /></label>
      <label className="campo"><span className="rotulo">E-mail da entidade</span>
        <input type="email" value={f.email_destino} placeholder="matriculas@…"
               onChange={(e) => setF({ ...f, email_destino: e.target.value })} /></label>
      <button className="btn-principal btn-mini" disabled={salvando || !f.inicio_em}
              onClick={async () => {
                setSalvando(true)
                try { await api.desenvolvimentoCriarTurma(f); aoFechar() }
                catch (e) { aoErro(e.detail || e.message) }
                finally { setSalvando(false) }
              }}>Salvar turma</button>
    </div>
  )
}

// --------------------------------------------------------------------------
// Tipos e prazos (catálogo configurável)
// --------------------------------------------------------------------------

const PAPEIS = ['identidade', 'certificado_formacao', 'certificado_reciclagem',
                'aso', 'outro']

function Tipos() {
  const [tipos, setTipos] = useState(null)
  const [editando, setEditando] = useState(null)
  const [msg, setMsg] = useState(null)

  const carregar = () => api.desenvolvimentoTipos().then((r) => setTipos(r.tipos))
    .catch((e) => setMsg({ tipo: 'erro', texto: e.detail || e.message }))
  useEffect(() => { carregar() }, [])
  if (!tipos) return <p className="explica">Carregando…</p>

  const excluir = async (t) => {
    if (!window.confirm(`Excluir o tipo "${t.nome}"?`)) return
    try { await api.desenvolvimentoExcluirTipo(t.id); carregar() }
    catch (e) {
      setMsg({ tipo: 'erro', texto: e.detail === 'tipo_em_uso'
        ? `"${t.nome}" já tem ${t.em_uso} registro(s) — não pode ser excluído.`
        : (e.detail || e.message) })
    }
  }

  return (
    <>
      <p className="explica">O que os colaboradores podem cadastrar. É aqui que se define
        se o certificado <strong>vence</strong>, se é <strong>crítico</strong> (não entra
        em validação por lote) e de quantos em quantos meses ele precisa ser renovado —
        com exceções por cargo ou posto.</p>
      <Msg msg={msg} />

      {editando && (
        <FormTipo tipo={editando} aoFechar={() => { setEditando(null); carregar() }}
                  aoErro={(t) => setMsg({ tipo: 'erro', texto: t })} />
      )}

      {!editando && (
        <button className="btn-principal btn-mini" style={{ marginBottom: '.7rem' }}
                onClick={() => setEditando({ novo: true })}>＋ Novo tipo</button>
      )}

      {tipos.map((t) => (
        <div className="rh-card" key={t.id} style={{ marginBottom: '.6rem' }}>
          <div className="rh-topo" style={{ marginBottom: '.3rem' }}>
            <h4 style={{ margin: 0 }}>
              {t.nome}{' '}
              {t.critico && <span className="chip" style={{ '--chip-cor': '#e5484d' }}>
                Crítico</span>}
              {!t.ativo && <span className="chip">Inativo</span>}
            </h4>
            <div>
              <button className="btn-secundario btn-mini"
                      onClick={() => setEditando(t)}>Editar</button>
              <button className="btn-secundario btn-mini"
                      onClick={() => excluir(t)}>Excluir</button>
            </div>
          </div>
          {t.descricao && <p className="explica" style={{ margin: 0 }}>{t.descricao}</p>}
          <p className="explica" style={{ margin: '.3rem 0 0' }}>
            {t.exige_validade
              ? `Vence a cada ${t.meses_validade} meses · avisa ${t.aviso_dias_antes} dias antes`
              : 'Sem validade'}
            {t.cargos_aplicaveis.length > 0 && ` · cargos: ${t.cargos_aplicaveis.join(', ')}`}
            {t.em_uso > 0 && ` · ${t.em_uso} registro(s)`}
          </p>
          {t.prazos.length > 0 && (
            <p className="explica" style={{ margin: '.2rem 0 0' }}>
              Exceções: {t.prazos.map((p) => (
                `${p.cargo || 'posto específico'} → ${p.meses_validade}m`)).join(' · ')}
            </p>
          )}
        </div>
      ))}
    </>
  )
}

function FormTipo({ tipo, aoFechar, aoErro }) {
  const novo = !!tipo.novo
  const [f, setF] = useState({
    nome: tipo.nome || '', descricao: tipo.descricao || '',
    exige_validade: !!tipo.exige_validade, meses_validade: tipo.meses_validade || 24,
    critico: !!tipo.critico, aviso_dias_antes: tipo.aviso_dias_antes || 90,
    cargos: (tipo.cargos_aplicaveis || []).join(', '),
    documentos: tipo.documentos_exigidos || [],
    ativo: tipo.ativo !== false,
  })
  const [salvando, setSalvando] = useState(false)

  const salvar = async () => {
    setSalvando(true)
    try {
      const corpo = {
        nome: f.nome.trim(), descricao: f.descricao.trim() || null,
        exige_validade: f.exige_validade,
        meses_validade: f.exige_validade ? Number(f.meses_validade) : null,
        critico: f.critico, aviso_dias_antes: Number(f.aviso_dias_antes) || 90,
        cargos_aplicaveis: f.cargos.split(',').map((c) => c.trim()).filter(Boolean),
        documentos_exigidos: f.documentos, ativo: f.ativo,
      }
      if (novo) await api.desenvolvimentoCriarTipo(corpo)
      else await api.desenvolvimentoEditarTipo(tipo.id, corpo)
      aoFechar()
    } catch (e) {
      aoErro(e.detail === 'nome_duplicado' ? 'Já existe um tipo com esse nome.'
        : (e.detail || e.message))
    } finally { setSalvando(false) }
  }

  const toggleDoc = (p) => setF({ ...f, documentos: f.documentos.includes(p)
    ? f.documentos.filter((x) => x !== p) : [...f.documentos, p] })

  return (
    <div className="rh-card" style={{ marginBottom: '.8rem' }}>
      <h4 style={{ marginTop: 0 }}>{novo ? 'Novo tipo' : `Editar: ${tipo.nome}`}</h4>
      <label className="campo"><span className="rotulo">Nome</span>
        <input value={f.nome} autoFocus placeholder="Ex.: Formação de brigada"
               onChange={(e) => setF({ ...f, nome: e.target.value })} /></label>
      <label className="campo"><span className="rotulo">Descrição (aparece para o colaborador)</span>
        <input value={f.descricao} onChange={(e) => setF({ ...f, descricao: e.target.value })} /></label>
      <label className="campo"><span className="rotulo">Cargos a que se aplica
        <span className="dica-inline"> — vazio = todos</span></span>
        <input value={f.cargos} placeholder="Bombeiro Civil, Brigadista"
               onChange={(e) => setF({ ...f, cargos: e.target.value })} /></label>

      <div className="campo">
        <span className="rotulo">Documentos exigidos no dossiê</span>
        <div className="chips-escolha">
          {PAPEIS.map((p) => (
            <button type="button" key={p}
                    className={`chip-escolha ${f.documentos.includes(p) ? 'on' : ''}`}
                    onClick={() => toggleDoc(p)}>{ROTULO_PAPEL[p] || p}</button>
          ))}
        </div>
      </div>

      <label className="campo" style={{ display: 'flex', alignItems: 'center', gap: '.5rem' }}>
        <input type="checkbox" checked={f.exige_validade}
               onChange={(e) => setF({ ...f, exige_validade: e.target.checked })} />
        <span>Este certificado vence</span></label>
      {f.exige_validade && (
        <div className="linha2">
          <label className="campo"><span className="rotulo">Vale por (meses)</span>
            <input inputMode="numeric" value={f.meses_validade}
                   onChange={(e) => setF({ ...f, meses_validade: e.target.value })} /></label>
          <label className="campo"><span className="rotulo">Avisar quantos dias antes</span>
            <input inputMode="numeric" value={f.aviso_dias_antes}
                   onChange={(e) => setF({ ...f, aviso_dias_antes: e.target.value })} /></label>
        </div>
      )}

      <label className="campo" style={{ display: 'flex', alignItems: 'center', gap: '.5rem' }}>
        <input type="checkbox" checked={f.critico}
               onChange={(e) => setF({ ...f, critico: e.target.checked })} />
        <span>Crítico <span className="dica-inline">— vencido deixa o posto irregular;
          nunca validado em lote</span></span></label>
      <label className="campo" style={{ display: 'flex', alignItems: 'center', gap: '.5rem' }}>
        <input type="checkbox" checked={f.ativo}
               onChange={(e) => setF({ ...f, ativo: e.target.checked })} />
        <span>Ativo <span className="dica-inline">— aparece para o colaborador</span></span></label>

      <div className="rh-lote">
        <button className="btn-principal btn-mini" disabled={salvando || !f.nome.trim()}
                onClick={salvar}>{salvando ? 'Salvando…' : 'Salvar'}</button>
        <button className="btn-link" onClick={aoFechar}>cancelar</button>
      </div>
    </div>
  )
}

function Msg({ msg }) {
  if (!msg) return null
  const classe = msg.tipo === 'ok' ? 'sucesso' : msg.tipo === 'aviso' ? 'aviso-inline' : 'alerta'
  return <div className={classe}>{msg.texto}</div>
}
