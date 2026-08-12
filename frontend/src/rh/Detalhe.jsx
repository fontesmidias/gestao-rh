import { useEffect, useMemo, useState } from 'react'
import { fmtData, fmtDataHora, isoParaBR } from '../fmt.js'
import { rh as api } from '../api.js'
import { statusInfo } from '../status.js'
import { DICAS } from '../tooltips.js'
import { DiagnosticoColaborador } from './Diagnostico.jsx'
import RoteiroAssinatura from './RoteiroAssinatura.jsx'
import Ajuda from '../Ajuda.jsx'
import PdfViewer from '../PdfViewer.jsx'
import SelectBusca from '../SelectBusca.jsx'
import Exigencias, { ResumoDasExcecoes } from './Exigencias.jsx'
import InputData from '../InputData.jsx'
import MemoriaPessoa from './MemoriaPessoa.jsx'
import EntrevistasDaPessoa from './EntrevistasDaPessoa.jsx'
import TestesVinculados from './TestesVinculados.jsx'
import TelemetriaPessoa from './TelemetriaPessoa.jsx'
import Modal from '../Modal.jsx'
import { OPCOES } from '../candidato/Wizard.jsx'

const MOTIVOS = [
  ['ilegivel', 'Ilegível'],
  ['doc_errado', 'Documento errado'],
  ['vencido', 'Vencido'],
  ['incompleto', 'Incompleto'],
  ['outro', 'Outro'],
]

// E-mail e celular editáveis pelo RH (caso real: candidato sem e-mail não
// recebia as fichas nem o código de assinatura). Toda alteração vai para a
// auditoria com o antes e o depois.
// Atendimento presencial desta pessoa — o que está em curso e o que já houve.
//
// Feedback 2026-08-02: *"onde e como eu marco que o atendimento foi assistido?
// eu consigo marcar isso após um candidato iniciar seu cadastro?"*. Sim, e a
// marca vale do clique em diante — o que é correto (não se carimba como
// presencial um documento assinado em casa), mas precisava estar VISÍVEL.
// O que TRAVA esta admissão, no topo da ficha e em uma frase (v2.95).
//
// A informação já existia — `GET /rh/candidatos/{id}/diagnostico` devolve
// `dossie.pendencias` desde a v1.x —, mas só aparecia dentro do bloco de
// Diagnóstico, no FIM da página, atrás de um `<details>`, depois de ~65 linhas
// de telemetria. Ou seja: a resposta estava pronta e ninguém a via.
//
// Três decisões deste bloco:
//   1. **Silêncio quando não há impedimento.** Um bloco verde dizendo "pode
//      gerar" em toda ficha seria mais um cartão competindo por atenção — e a
//      tela já tinha 14. Só aparece quando há o que resolver.
//   2. **Falha de carga NÃO vira alarme.** Se o diagnóstico não responde, o
//      bloco some em silêncio: dizer "não foi possível verificar" no topo de
//      toda ficha ensinaria a equipe a ignorar a faixa vermelha, que é
//      justamente o que ela precisa levar a sério (v2.88).
//   3. **Nomeia o documento, não o código.** `documento:ctps_digital` vira
//      "CTPS digital" — o RH não deveria traduzir enum.
function ImpedimentoDaFicha({ id, recarga }) {
  const [pend, setPend] = useState(null)

  useEffect(() => {
    let vivo = true
    api.diagnostico(id)
      .then((d) => { if (vivo) setPend(d?.dossie?.pode_gerar ? [] : (d?.dossie?.pendencias || [])) })
      .catch(() => { if (vivo) setPend([]) })   // ver decisão 2
    return () => { vivo = false }
  }, [id, recarga])

  if (!pend || pend.length === 0) return null
  return (
    <div className="ficha-impedimento">
      <strong>{pend.length === 1
        ? 'Falta 1 item para o dossiê gerar:'
        : `Faltam ${pend.length} itens para o dossiê gerar:`}</strong>
      <ul>{pend.map((p, i) => <li key={i}>{p}</li>)}</ul>
    </div>
  )
}

// Busca própria só para o resumo das exceções (v2.95). Ele mora FORA do
// `<details>`, e `<details>` fechado não renderiza o conteúdo — então não dá
// para reaproveitar a consulta que o `Exigencias` faz lá dentro.
function ResumoExigenciasDaPessoa({ id }) {
  const [dados, setDados] = useState(null)
  useEffect(() => {
    let vivo = true
    api.exigenciasDoCandidato(id)
      .then((d) => { if (vivo) setDados(d) })
      .catch(() => { if (vivo) setDados(null) })
    return () => { vivo = false }
  }, [id])
  if (!dados) return null
  return <ResumoDasExcecoes dados={dados} />
}

function AtendimentoAssistido({ lista }) {
  if (!lista || lista.length === 0) return null
  const emCurso = lista.find((a) => a.em_curso)
  const anteriores = lista.filter((a) => !a.em_curso)

  return (
    <div className="aviso-assistido">
      {emCurso ? (<>
        <strong>🧑‍💼 Em atendimento presencial</strong> — aberto por{' '}
        <strong>{emCurso.por}</strong> em {fmtDataHora(emCurso.quando)}. O link se
        encerra sozinho em {fmtDataHora(emCurso.expira_em)}.
      </>) : (<>
        <strong>🧑‍💼 Houve atendimento presencial</strong> — o último por{' '}
        <strong>{anteriores[0].por}</strong> em {fmtDataHora(anteriores[0].quando)}.
      </>)}
      {/* O que a pessoa assinou ANTES do atendimento continua registrado como
          feito por ela. Dizer isso aqui evita a leitura errada de que a
          admissão inteira foi presencial. */}
      <p className="explica" style={{ margin: '.35rem 0 0' }}>
        Vale para o que foi assinado a partir daí — cada documento registra, no
        próprio manifesto, se foi colhido presencialmente ou pela pessoa
        sozinha.
        {anteriores.length > (emCurso ? 0 : 1) && (
          <> Ao todo: {lista.length} atendimento(s).</>)}
      </p>
    </div>
  )
}

function ContatoEditavel({ dados, setMsg, recarregar }) {
  const [editando, setEditando] = useState(false)
  const [email, setEmail] = useState(dados.email || '')
  const [celular, setCelular] = useState(dados.celular_whatsapp || '')
  const [salvando, setSalvando] = useState(false)
  if (!editando) {
    return (
      <>
        {dados.email || 'sem e-mail'} · {dados.celular_whatsapp || 'sem celular'}
        <button className="btn-link" title="Corrigir e-mail/celular (fica na auditoria)"
                onClick={() => setEditando(true)}>✏️ editar contato</button>
      </>
    )
  }
  return (
    <span className="contato-editavel">
      <input type="email" placeholder="E-mail" value={email}
             onChange={(e) => setEmail(e.target.value)} />
      <input placeholder="Celular/WhatsApp" value={celular}
             onChange={(e) => setCelular(e.target.value)} />
      <button className="btn-principal btn-mini" disabled={salvando} onClick={async () => {
        setSalvando(true); setMsg(null)
        try {
          await api.editarContato(dados.id, {
            email: email.trim() || null, celular_whatsapp: celular.trim() || null,
          })
          // Lição do incidente real: atualizar o e-mail NÃO envia nada sozinho.
          setMsg({ tipo: 'ok', texto: 'Contato atualizado (registrado na auditoria). '
            + (email.trim() && !dados.email
               ? 'Atenção: salvar o e-mail não envia nada — use "🔔 Notificar pendências" para o candidato receber o que falta.'
               : '') })
          setEditando(false)
          await recarregar()
        } catch (e) {
          setMsg({ tipo: 'erro', texto: `Não foi possível salvar (${Array.isArray(e.detail)
            ? 'e-mail inválido' : e.detail || e.message}).` })
        } finally { setSalvando(false) }
      }}>{salvando ? 'Salvando…' : 'Salvar'}</button>
      <button className="btn-link" onClick={() => setEditando(false)}>cancelar</button>
    </span>
  )
}

// O que faltava no incidente real: as fichas ficavam invisíveis para o RH.
// Cada documento exigido aparece com o estado, a ficha incompleta grita, e o
// botão de notificação manda o retrato exato das pendências por e-mail.
function FichasStatus({ dados }) {
  // Mensagem LOCAL (v2.47): com a reordenação da tela este card passou a viver
  // DENTRO da faixa de consulta, no fim da página — a mensagem global do topo
  // ficaria fora da vista de quem acabou de clicar em "Notificar".
  const [msg, setMsg] = useState(null)
  const [notificando, setNotificando] = useState(false)
  const pend = dados.pendencias_ficha || []
  const fichas = dados.fichas || []
  const temPendencia = pend.length > 0 || fichas.some((f) => !f.assinado)

  const notificar = async () => {
    if (!window.confirm(`Enviar um e-mail de cobrança para ${dados.nome_completo} com a lista de pendências?`)) return
    setNotificando(true); setMsg(null)
    try {
      const r = await api.notificar(dados.id)
      setMsg({ tipo: 'ok', texto: r.email_enviado
        ? `Cobrança enviada por e-mail (${r.itens.length} pendência(s) listadas).`
        : 'E-mail não saiu (verifique a configuração de envio) — copie o link e cobre pelo WhatsApp.' })
    } catch (e) {
      setMsg({ tipo: 'erro', texto: e.detail === 'candidato_sem_email'
        ? 'Este candidato não tem e-mail — cadastre em "editar contato" ou cobre pelo WhatsApp com 📋 Copiar link.'
        : e.detail === 'sem_pendencias' ? 'Nada a cobrar: está tudo em dia. 🎉'
        : e.amigavel || `Não foi possível notificar (${e.detail || e.message}).` })
    } finally { setNotificando(false) }
  }

  return (
    <div className="rh-card">
      <div className="rh-topo">
        <strong>📝 Fichas e assinaturas</strong>
        {temPendencia && (
          <button className="btn-secundario btn-mini" disabled={notificando}
                  title="Envia um e-mail ao candidato com a lista exata do que falta (formulário, assinaturas, documentos) e um link novo"
                  onClick={notificar}>
            {notificando ? 'Enviando…' : '🔔 Notificar'}</button>
        )}
      </div>
      {pend.length > 0 && (
        <div className="alerta compacto" style={{ marginTop: '.5rem' }}
             title={'Sem esses dados, as fichas seriam geradas vazias. O candidato completa pelo link dele — ou você preenche em ✏️ Corrigir dados da ficha.'}>
          ⚠️ Formulário incompleto — <strong>{pend.length} campo(s)</strong> em aberto <span className="dica-i">ⓘ</span>
        </div>
      )}
      <ul className="fichas-status">
        {fichas.map((f) => (
          <li key={f.documento}
              title={f.assinado ? `Assinada em ${fmtData(f.assinado_em)} (horário de Brasília)`
                                : 'Aguardando assinatura eletrônica do candidato'}>
            {f.assinado ? '✅' : '⏳'} {f.titulo}
            {f.assinado && <small> · {fmtData(f.assinado_em)}</small>}
            <button className="btn-link" style={{ marginLeft: '.4rem' }}
                    title={f.assinado ? 'Baixar a via assinada (PDF)' : 'Baixar a prévia atual (PDF) para envio manual'}
                    onClick={async () => {
                      setMsg(null)
                      try {
                        const blob = await api.baixarFicha(dados.id, f.documento)
                        const a = document.createElement('a')
                        a.href = URL.createObjectURL(blob)
                        a.download = `${f.documento}-${dados.nome_completo}.pdf`
                        a.click()
                      } catch (e) {
                        setMsg({ tipo: 'erro', texto: `Não foi possível baixar (${e.detail || e.message}).` })
                      }
                    }}>⬇ baixar</button>
          </li>
        ))}
      </ul>
      {msg && <div className={msg.tipo === 'erro' ? 'alerta' : 'sucesso'}>{msg.texto}</div>}
    </div>
  )
}

function PostoServico({ dados, recarregar }) {
  // Mensagem LOCAL (v2.47): este card fica no MEIO da tela e tem ~14 controles.
  // Mandar o resultado do "Salvar posto" para a mensagem global do topo é o
  // mesmo defeito que a v1.96 corrigiu na ficha — a pessoa salva olhando para
  // cá e a confirmação aparece fora do campo de visão dela.
  const [msg, setMsg] = useState(null)
  const [postos, setPostos] = useState(null)
  const [postoId, setPostoId] = useState(dados.posto_servico_id || '')
  const [cargo, setCargo] = useState(dados.cargo_funcao || '')
  const [cargos, setCargos] = useState([])          // cargos já usados na base
  const [digitandoCargo, setDigitandoCargo] = useState(false)
  const [salario, setSalario] = useState(dados.salario_base || '')
  const [adicionais, setAdicionais] = useState(dados.adicionais || [])
  const [salvando, setSalvando] = useState(false)
  const [novoPosto, setNovoPosto] = useState(null) // criar posto na hora
  // Integração Tirvu: empregadora, jornada e ponto — saem no export de admissões
  const [empresas, setEmpresas] = useState([])
  const [jornadas, setJornadas] = useState([])
  const [empresaId, setEmpresaId] = useState(dados.empresa_id || '')
  const [jornadaId, setJornadaId] = useState(dados.jornada_id || '')
  const [ponto, setPonto] = useState(dados.registra_ponto == null ? '' : String(dados.registra_ponto))
  const [novaEmpresa, setNovaEmpresa] = useState(null)
  const [novaJornada, setNovaJornada] = useState(null)
  const recarregarPostos = () => api.postos().then((r) => setPostos(r.postos))
  useEffect(() => { recarregarPostos() }, [])
  useEffect(() => { api.empresas().then(setEmpresas).catch(() => {}) }, [])
  // jornadas do posto escolhido vêm primeiro (ordenação, não filtro)
  useEffect(() => { api.jornadas(postoId || null).then(setJornadas).catch(() => {}) }, [postoId])
  useEffect(() => { api.cargos().then((r) => setCargos(r.cargos)).catch(() => {}) }, [])
  // O cargo atual entra na lista mesmo se não vier da API (cargo raro, ou
  // digitado agora): sem isso o SelectBusca mostraria o campo como vazio.
  const opcoesCargo = useMemo(() => {
    const nomes = cargos.map((c) => c.nome)
    if (cargo && !nomes.includes(cargo)) nomes.unshift(cargo)
    return [
      ...nomes.map((n) => {
        const achado = cargos.find((c) => c.nome === n)
        return { valor: n, rotulo: n,
                 extra: achado ? `${achado.pessoas} pessoa(s)` : 'atual' }
      }),
      { valor: '__novo', rotulo: '＋ Cargo novo…' },
    ]
  }, [cargos, cargo])
  // Enquanto os postos não chegam, o card RESERVA o lugar em vez de sumir: é
  // uma das duas áreas de trabalho da tela, e some-la fazia o conteúdo abaixo
  // pular na cara de quem já estava lendo.
  if (!postos) return (
    <div className="rh-card"><p className="explica">Carregando posto de serviço…</p></div>
  )
  const extras = (dados.assinaturas || []).filter((a) =>
    !['ficha_cadastro', 'ficha_emergencia', 'termo_vt',
      'acordo_confidencialidade'].includes(a.documento))
  const setAdic = (i, campo, v) =>
    setAdicionais(adicionais.map((a, j) => j === i ? { ...a, [campo]: v } : a))
  return (
    <div className="rh-card rh-lote">
      <strong>Posto de serviço:</strong>
      <SelectBusca style={{ maxWidth: 220 }} valor={postoId} aoEscolher={(v) => {
                if (v === '__novo') { setNovoPosto({ nome: '', sigla: '', contrato_ref: '' }); return }
                setPostoId(v)
              }}>
        <option value="">— sem posto —</option>
        {postos.map((p) => <option key={p.id} value={p.id}>
          {p.sigla || p.nome}{p.contrato_ref ? ` — ${p.contrato_ref}` : ''}</option>)}
        <option value="__novo">➕ Cadastrar novo posto…</option>
      </SelectBusca>
      {novoPosto && (
        <div className="rh-adicional" style={{ width: '100%' }}>
          <input placeholder="Nome do posto" value={novoPosto.nome}
                 onChange={(e) => setNovoPosto({ ...novoPosto, nome: e.target.value })} />
          <input placeholder="Sigla (ex.: INEP Adm)" style={{ maxWidth: 140 }} value={novoPosto.sigla}
                 onChange={(e) => setNovoPosto({ ...novoPosto, sigla: e.target.value })} />
          <input placeholder="Contrato (opcional)" style={{ maxWidth: 160 }} value={novoPosto.contrato_ref}
                 onChange={(e) => setNovoPosto({ ...novoPosto, contrato_ref: e.target.value })} />
          <button className="btn-principal btn-mini" onClick={async () => {
            if (!novoPosto.nome.trim()) return
            try {
              const p = await api.criarPosto({ nome: novoPosto.nome.trim(),
                sigla: novoPosto.sigla.trim() || null, contrato_ref: novoPosto.contrato_ref.trim() || null })
              await recarregarPostos(); setPostoId(p.id); setNovoPosto(null)
            } catch (e) {
              setMsg({ tipo: 'erro', texto: e.detail === 'posto_ja_existe'
                ? 'Já existe um posto com esse nome.' : `Não foi possível criar (${e.detail || e.message}).` })
            }
          }}>Criar</button>
          <button className="btn-link" onClick={() => setNovoPosto(null)}>cancelar</button>
        </div>
      )}
      {postoId && (postos.find((p) => p.id === postoId)?.contrato_ref) && (
        <span className="explica" style={{ margin: 0 }}
              title="Vem do cadastro do posto (Configurações → Postos) — nada para digitar">
          📄 <strong>{postos.find((p) => p.id === postoId).contrato_ref}</strong>
          <span className="dica-i"> ⓘ</span></span>
      )}
      {/* Cargo/função: escolhe da lista já mapeada ou digita um novo (v1.82).
          Continua string livre no banco — a lista só evita que "Vigia",
          "vigia" e "Vigía" virem três cargos diferentes nos filtros e nos
          modelos de documento, que casam por TEXTO. */}
      {digitandoCargo ? (
        <span className="rh-cargo-novo">
          <input placeholder="Cargo/função novo (ex.: Office Boy)" value={cargo}
                 autoFocus style={{ maxWidth: 240 }}
                 onChange={(e) => setCargo(e.target.value)} />
          <button type="button" className="btn-secundario btn-mini"
                  title="Voltar para a lista de cargos já cadastrados"
                  onClick={() => setDigitandoCargo(false)}>↩ lista</button>
        </span>
      ) : (
        <SelectBusca
          style={{ maxWidth: 260 }} valor={cargo}
          vazioRotulo="— cargo/função —" placeholder="Buscar cargo…"
          opcoes={opcoesCargo}
          aoEscolher={(v) => {
            if (v === '__novo') { setCargo(''); setDigitandoCargo(true); return }
            setCargo(v)
          }} />
      )}
      <label className="campo" style={{ maxWidth: 240 }}>
        <input placeholder="Salário base (ex.: R$ 1.500,00)" value={salario}
               onChange={(e) => setSalario(e.target.value)} />
        {dados.regime === 'intermitente' && (
          <small className="explica" style={{ margin: '.2rem 0 0', color: '#7a5b1a' }}>
            ⚠️ Intermitente: informe o <strong>valor por dia</strong> — salário do cargo
            ÷ 30 (ex.: cargo R$ 1.500 → R$ 50,00/dia).</small>)}
      </label>
      <SelectBusca style={{ maxWidth: 220 }}
              title="Empregadora que assina a carteira — sai na planilha do Tirvu" valor={empresaId} aoEscolher={(v) => {
                if (v === '__nova') { setNovaEmpresa({ razao_social: '', cnpj: '' }); return }
                setEmpresaId(v)
              }}>
        <option value="">— empresa —</option>
        {empresas.map((em) => <option key={em.id} value={em.id}>{em.razao_social}</option>)}
        <option value="__nova">➕ Cadastrar empresa…</option>
      </SelectBusca>
      {novaEmpresa && (
        <div className="rh-adicional" style={{ width: '100%' }}>
          <input placeholder="Razão social" value={novaEmpresa.razao_social}
                 onChange={(e) => setNovaEmpresa({ ...novaEmpresa, razao_social: e.target.value })} />
          <input placeholder="CNPJ (opcional)" style={{ maxWidth: 170 }} value={novaEmpresa.cnpj}
                 onChange={(e) => setNovaEmpresa({ ...novaEmpresa, cnpj: e.target.value })} />
          <button className="btn-principal btn-mini" onClick={async () => {
            if (!novaEmpresa.razao_social.trim()) return
            const em = await api.criarEmpresa({ razao_social: novaEmpresa.razao_social.trim(),
                                                cnpj: novaEmpresa.cnpj.trim() || null })
            setEmpresas(await api.empresas()); setEmpresaId(em.id); setNovaEmpresa(null)
          }}>Criar</button>
          <button className="btn-link" onClick={() => setNovaEmpresa(null)}>cancelar</button>
        </div>
      )}
      <SelectBusca style={{ minWidth: 260 }} vazioRotulo="— jornada de trabalho —"
        placeholder="Buscar jornada…" valor={jornadaId}
        aoEscolher={(v) => {
          if (v === '__nova') { setNovaJornada({ descricao: '' }); return }
          setJornadaId(v || '')
        }}
        opcoes={[...jornadas.map((j) => ({ valor: j.id, rotulo: j.descricao })),
                 { valor: '__nova', rotulo: '➕ Criar jornada…' }]} />
      {novaJornada && (
        <div className="rh-adicional" style={{ width: '100%' }}>
          <input placeholder="Descrição (ex.: INEP ADM - 2ª A 6ª - 08H - 12H - 13H - 17H)"
                 style={{ flex: 1, minWidth: 280 }} value={novaJornada.descricao}
                 onChange={(e) => setNovaJornada({ ...novaJornada, descricao: e.target.value })} />
          <button className="btn-principal btn-mini" onClick={async () => {
            if (!novaJornada.descricao.trim()) return
            const j = await api.criarJornada({ descricao: novaJornada.descricao.trim(),
                                               posto_servico_id: postoId || null })
            setJornadas(await api.jornadas(postoId || null)); setJornadaId(j.id); setNovaJornada(null)
          }}>Criar</button>
          <button className="btn-link" onClick={() => setNovaJornada(null)}>cancelar</button>
        </div>
      )}
      {/* Registra ponto é obrigatório para o Tirvu (v1.82): em branco, o
          colaborador nasce lá sem a marcação e ninguém percebe. Marca-se o
          campo em âmbar em vez de travar o salvamento — os importados do Tirvu
          nasceram sem o campo e não dá para prender a edição deles. */}
      <SelectBusca style={{ maxWidth: 190 }}
              className={ponto === '' ? 'campo-pendente' : undefined}
              title="Se o colaborador registra ponto — obrigatório na planilha do Tirvu" valor={ponto} aoEscolher={(v) => setPonto(v)}>
        <option value="">— registra ponto? —</option>
        <option value="true">Registra ponto: sim</option>
        <option value="false">Registra ponto: não</option>
      </SelectBusca>
      {ponto === '' && (
        <span className="aviso-pendente">
          ⚠️ Obrigatório para exportar ao Tirvu
        </span>
      )}
      <div className="rh-adicionais">
        <span className="explica" style={{ margin: 0, width: '100%' }}>Adicionais
          (entram na ficha junto com cargo e salário):</span>
        {adicionais.map((a, i) => (
          <div className="rh-adicional" key={i}>
            <input placeholder="Nome (ex.: Periculosidade)" value={a.nome || ''}
                   onChange={(e) => setAdic(i, 'nome', e.target.value)} />
            <input placeholder="Valor" value={a.valor || ''} style={{ maxWidth: 110 }}
                   onChange={(e) => setAdic(i, 'valor', e.target.value)} />
            <SelectBusca style={{ maxWidth: 130 }} valor={a.tipo || 'reais'} aoEscolher={(v) => setAdic(i, 'tipo', v)}>
              <option value="reais">R$ (reais)</option>
              <option value="percentual">% (percentual)</option>
            </SelectBusca>
            <button className="btn-link" title="Remover adicional"
                    onClick={() => setAdicionais(adicionais.filter((_, j) => j !== i))}>✕</button>
          </div>
        ))}
        <button className="btn-secundario btn-mini"
                onClick={() => setAdicionais([...adicionais, { nome: '', valor: '', tipo: 'reais' }])}>
          + Adicional</button>
      </div>
      <button className="btn-principal btn-mini" disabled={salvando} onClick={async () => {
        if (!window.confirm('Salvar posto e remuneração?\n\nSe a ficha de cadastro já estiver assinada e o cargo/salário mudar, ela será reaberta para nova assinatura do colaborador.')) return
        setMsg(null); setSalvando(true)
        try {
          const r = await api.definirPosto(dados.id, {
            posto_id: postoId || null, cargo_funcao: cargo.trim() || null,
            salario_base: salario.trim() || null,
            empresa_id: empresaId || null, jornada_id: jornadaId || null,
            registra_ponto: ponto === '' ? null : ponto === 'true',
            adicionais: adicionais
              .filter((a) => (a.nome || '').trim())
              .map((a) => ({ nome: a.nome.trim(), valor: (a.valor || '').trim(), tipo: a.tipo || 'reais' })),
          })
          const reaberta = r.ficha_reaberta
            ? ' A ficha de cadastro já assinada foi reaberta — use 🔔 Notificar para o colaborador assinar a versão atualizada.'
            : ''
          setMsg({ tipo: 'ok', texto: (r.docs_gerados.length
            ? `Posto salvo. ${r.docs_gerados.length} documento(s) gerados e enviados para assinatura${r.email_enviado ? ' — o colaborador foi avisado por e-mail' : ' (e-mail não configurado: envie o link manualmente)'}.`
            : 'Posto e remuneração salvos.') + reaberta })
          await recarregar()
        } catch (e) {
          setMsg({ tipo: 'erro', texto: `Não foi possível salvar o posto (${e.detail || e.message}).` })
        } finally { setSalvando(false) }
      }}>{salvando ? 'Salvando…' : 'Salvar posto'}</button>
      <button className="btn-secundario btn-mini"
              title="Baixa a planilha de importação de admissões do Tirvu com esta pessoa"
              onClick={async () => {
                try {
                  // Confere ANTES de baixar (feedback 2026-08-01): o export em
                  // massa sempre avisou o que falta, este aqui baixava a
                  // planilha furada calado — e o Tirvu aceita a célula vazia
                  // sem reclamar, então o erro só aparece semanas depois.
                  let faltas = []
                  try {
                    const p = await api.pendenciasTirvu({ ids: dados.id })
                    faltas = p.com_pendencia?.[0]?.faltam || []
                  } catch { /* a checagem falhar não pode impedir o download */ }
                  if (faltas.length && !window.confirm(
                    `Esta planilha vai sair com ${faltas.length} campo(s) em branco:\n\n`
                    + `• ${faltas.join('\n• ')}\n\n`
                    + 'O Tirvu ACEITA a célula vazia sem avisar, e o cadastro nasce '
                    + 'incompleto lá.\n\nBaixar assim mesmo?')) return

                  const blob = await api.exportarTirvuIndividual(dados.id)
                  const a = document.createElement('a')
                  a.href = URL.createObjectURL(blob)
                  a.download = `importacao-tirvu-${(dados.nome_completo || 'admissao').replace(/[^\wÀ-ú -]/g, '').trim().replace(/\s+/g, '-')}.xlsx`
                  a.click()
                  if (faltas.length) {
                    setMsg({ tipo: 'erro', texto: `Planilha baixada COM pendências: ${faltas.join(', ')}. `
                      + 'Cadastre os IDs do Tirvu (Config → Cargos, Jornadas, Postos) e exporte de novo.' })
                  }
                } catch (e) {
                  setMsg({ tipo: 'erro', texto: `Não foi possível exportar (${e.detail || e.message}).` })
                }
              }}>⬆ Planilha p/ Tirvu</button>
      {extras.length > 0 && (
        <span className="explica campo-sem-margem" style={{ width: '100%' }}>
          {extras.map((a) => (
            <span key={a.documento} className="chip-doc"
                  title={a.assinado_em ? `${a.titulo} — assinado` : `${a.titulo} — aguardando assinatura do candidato`}>
              {a.assinado_em ? '✅' : '⏳'} {a.titulo.replace(/ \(INFRAERO\)| INFRAERO —.*/, '')}
            </span>
          ))}
        </span>
      )}
      {msg && <div className={msg.tipo === 'erro' ? 'alerta' : 'sucesso'}>{msg.texto}</div>}
    </div>
  )
}

// Documentos-modelo (criados em Configurações) que se aplicam a este colaborador,
// com o botão de gerar o PDF já preenchido no papel timbrado.
function ModelosDoColaborador({ id }) {
  const [modelos, setModelos] = useState(null)
  const [gerando, setGerando] = useState(null)
  // Mensagem LOCAL: este card fica no meio da tela, e mandar o erro para a
  // mensagem global do topo é o mesmo defeito corrigido na ficha na v1.96 —
  // quem clica aqui não vê o resultado lá em cima.
  const [msgLocal, setMsgLocal] = useState(null)
  useEffect(() => { api.modelosAplicaveis(id).then(setModelos).catch(() => setModelos([])) }, [id])
  const gerar = async (m) => {
    setGerando(m.id); setMsgLocal(null)
    try {
      const blob = await api.gerarModelo(id, m.id)
      window.open(URL.createObjectURL(blob), '_blank')
    } catch (e) {
      setMsgLocal({ tipo: 'erro', texto: `Não foi possível gerar (${e.detail || e.message}).` })
    } finally { setGerando(null) }
  }
  // `null` (ainda carregando) e `[]` (não há modelo para este cargo/posto) são
  // estados DIFERENTES: o primeiro reserva o lugar, o segundo pode sumir.
  if (modelos === null) return (
    <div className="rh-card"><p className="explica">Carregando documentos…</p></div>
  )
  if (modelos.length === 0) return null
  return (
    <div className="rh-card rh-lote">
      <strong>📝 Documentos do colaborador:</strong>
      {modelos.map((m) => (
        <button key={m.id} className="btn-secundario btn-mini" disabled={gerando === m.id}
                onClick={() => gerar(m)}>
          {gerando === m.id ? 'Gerando…' : `⬇ ${m.titulo}`}</button>
      ))}
      <span className="explica campo-sem-margem" style={{ width: '100%' }}>Gerados no papel timbrado,
        com os dados deste colaborador preenchidos. Crie/edite modelos em Configurações.</span>
      {msgLocal && <div className={msgLocal.tipo === 'erro' ? 'alerta' : 'sucesso'}>{msgLocal.texto}</div>}
    </div>
  )
}

// Seções e campos que o RH pode completar/corrigir. A validação é a mesma do
// candidato (backend); documentos já assinados que exibem o dado alterado são
// invalidados e voltam para o CANDIDATO assinar — o RH prepara, nunca assina.
//
// pessoais/endereco ganharam os campos que faltavam (feedback 2026-07-27): sem
// eles o RH não conseguia destravar uma ficha parada na declaração final —
// sexo, identidade de gênero, cor/raça, nacionalidade, estado civil,
// escolaridade e PCD são obrigatórios lá (ficha.py), e o backend já aceitava,
// só o formulário do RH não expunha.
const SECOES_FICHA = {
  pessoais: ['nome_completo', 'nome_social', 'nome_mae', 'nome_pai',
             'data_nascimento', 'sexo', 'identidade_genero', 'cor_raca',
             'nacionalidade', 'naturalidade_cidade', 'naturalidade_uf',
             'estado_civil', 'escolaridade', 'pcd'],
  // logradouro_numero_complemento é o campo LEGADO (string única) — quem já
  // preencheu por ele passa a declaração sem precisar dos três campos novos
  // (ficha.py::pendencias_da_ficha). Mantido aqui só para corrigir fichas
  // antigas; a coleta nova usa logradouro/numero/complemento separados.
  endereco: ['cep', 'logradouro', 'numero', 'complemento',
             'logradouro_numero_complemento', 'bairro', 'cidade', 'uf'],
  documentos: ['rg_numero', 'rg_orgao_emissor', 'rg_data_expedicao', 'cpf',
               'pis_nis_pasep', 'cnh_numero', 'cnh_categoria', 'cnh_orgao_emissor',
               'cnh_uf', 'cnh_data_emissao', 'cnh_validade', 'cnh_primeira_habilitacao',
               'militar_tipo', 'militar_numero', 'militar_serie', 'militar_categoria',
               'militar_orgao', 'militar_data_emissao',
               'titulo_eleitor_numero', 'titulo_eleitor_zona', 'titulo_eleitor_secao'],
  'trabalho-banco': ['tamanho_calca', 'tamanho_camisa', 'tamanho_calcado',
                     'banco', 'pix_tipo', 'pix_chave'],
  // VT + emergência: o candidato preenche a emergência no wizard, mas o RH
  // também precisa ver/corrigir (feedback 2026-07-24: "não apareceu os dados de
  // emergência para o RH editar"). O backend (rh_ficha.py::editar_secao) já
  // separa vt_ de emergência e grava em ValeTransporte/FichaEmergencia.
  'vt-emergencia': ['vt_optante', 'vt_cartao_dftrans', 'vt_trajeto_descricao',
                    'tipo_sanguineo', 'usa_medicamento_continuo', 'medicamentos',
                    'condicoes_medicas', 'orientacao_emergencia'],
}
// Campos booleanos: o <input> devolve texto; convertê-los para bool no submit
// (como vt_optante já era). Chave = campo do payload.
const CAMPOS_BOOL = new Set(['vt_optante', 'usa_medicamento_continuo', 'pcd'])
// Campos de data: <InputData> com máscara BR, valor guardado em ISO — sem
// isso "15/03/1990" digitado num <input> texto virava ValidationError (500
// mudo) no backend (feedback 2026-07-27).
const CAMPOS_DATA = new Set(['data_nascimento', 'rg_data_expedicao', 'cnh_data_emissao',
                             'cnh_validade', 'cnh_primeira_habilitacao', 'militar_data_emissao'])
// Campos enum: <select> com as mesmas opções do wizard do candidato — digitar
// livre um enum ("CPF" em vez do valor exato) também virava 500 mudo.
const CAMPOS_ENUM = {
  sexo: OPCOES.sexo, identidade_genero: OPCOES.identidade_genero,
  cor_raca: OPCOES.cor_raca, nacionalidade: OPCOES.nacionalidade,
  estado_civil: OPCOES.estado_civil, escolaridade: OPCOES.escolaridade,
  pix_tipo: OPCOES.pix_tipo,
}
// Campos de UF: só 2 letras — <select> evita "Distrito Federal" (DataError
// de truncamento no commit, também 500 mudo antes da correção do backend).
const UFS = ['AC', 'AL', 'AP', 'AM', 'BA', 'CE', 'DF', 'ES', 'GO', 'MA', 'MT', 'MS',
             'MG', 'PA', 'PB', 'PR', 'PE', 'PI', 'RJ', 'RN', 'RS', 'RO', 'RR', 'SC',
             'SP', 'SE', 'TO']
const CAMPOS_UF = new Set(['naturalidade_uf', 'uf', 'cnh_uf'])
const CHAVE_ESTADO = { 'trabalho-banco': 'trabalho_banco' }

function FichaRH({ id }) {
  const [aberta, setAberta] = useState(false)
  const [ficha, setFicha] = useState(null)
  const [erroCarga, setErroCarga] = useState(null)
  const [edicao, setEdicao] = useState({}) // {`secao.campo`: valor}
  const [motivo, setMotivo] = useState('')
  const [salvando, setSalvando] = useState(null)
  // Mensagem LOCAL a esta seção — antes ia para o setMsg do pai, renderizado
  // ~19 blocos JSX acima do formulário (fora do viewport com o <details>
  // aberto e rolado até o botão Salvar). O RH nunca via o erro (feedback de
  // campo 2026-07-27: "não salva e não diz o motivo"). {secao: {tipo, texto}}
  const [msgSecao, setMsgSecao] = useState({})

  const carregar = () => api.fichaCandidato(id).then(setFicha)
    .then(() => setErroCarga(null))
    .catch(() => setErroCarga('Não foi possível carregar a ficha. Tente novamente.'))
  useEffect(() => { if (aberta) carregar() }, [aberta, id])

  if (!aberta) return (
    <div className="rh-card">
      <button className="btn-secundario btn-mini" onClick={() => setAberta(true)}
              title="Completa campos faltantes ou corrige erros. Fichas já assinadas que exibem o dado alterado voltam para o candidato assinar de novo — só as afetadas.">
        ✏️ Corrigir dados da ficha <span className="dica-i">ⓘ</span></button>
    </div>
  )
  if (erroCarga) return (
    <div className="rh-card">
      <div className="alerta">{erroCarga}</div>
      <button className="btn-secundario btn-mini" onClick={carregar}>tentar de novo</button>
    </div>
  )
  if (!ficha) return <div className="rh-card"><p>Carregando ficha…</p></div>

  const valorAtual = (secao, campo) => {
    const s = ficha[CHAVE_ESTADO[secao] || secao] || {}
    if (secao === 'vt-emergencia') {
      const vt = ficha.vt || {}
      const em = ficha.emergencia || {}
      return { vt_optante: vt.optante, vt_cartao_dftrans: vt.cartao_dftrans,
               vt_trajeto_descricao: vt.trajeto_descricao,
               tipo_sanguineo: em.tipo_sanguineo,
               usa_medicamento_continuo: em.usa_medicamento_continuo,
               medicamentos: em.medicamentos, condicoes_medicas: em.condicoes_medicas,
               orientacao_emergencia: em.orientacao_emergencia }[campo]
    }
    return s[campo]
  }

  const salvarSecao = async (secao) => {
    const dados = {}
    for (const campo of SECOES_FICHA[secao]) {
      const chave = `${secao}.${campo}`
      if (chave in edicao) dados[campo] = edicao[chave] === '' ? null : edicao[chave]
    }
    if (!Object.keys(dados).length) {
      setMsgSecao((m) => ({ ...m, [secao]: { tipo: 'erro', texto: 'Nenhum campo desta seção foi alterado.' } })); return
    }
    if (!motivo.trim()) {
      setMsgSecao((m) => ({ ...m, [secao]: { tipo: 'erro', texto: 'Informe o motivo da correção — ele vai para a auditoria.' } })); return
    }
    if (!window.confirm('Salvar a correção desta seção?\n\nSe algum documento já assinado exibir um dado alterado, ele será reaberto para o colaborador assinar novamente.')) return
    for (const campo of CAMPOS_BOOL) {
      if (dados[campo] !== undefined && dados[campo] !== null) {
        dados[campo] = String(dados[campo]).toLowerCase() === 'true'
      }
    }
    setSalvando(secao); setMsgSecao((m) => ({ ...m, [secao]: null }))
    try {
      const r = await api.editarFicha(id, secao, dados, motivo.trim())
      const invalidadas = r.assinaturas_invalidadas || []
      setMsgSecao((m) => ({ ...m, [secao]: { tipo: 'ok', texto: invalidadas.length
        ? `Ficha atualizada. ${invalidadas.length} documento(s) voltaram para assinatura do candidato`
          + (r.email_enviado ? ' — ele foi avisado por e-mail.' : ' — avise-o (e-mail não saiu).')
        : 'Ficha atualizada (nenhum documento assinado foi afetado).' } }))
      setEdicao((e) => {
        const novo = { ...e }
        Object.keys(novo).forEach((k) => { if (k.startsWith(`${secao}.`)) delete novo[k] })
        return novo
      })
      // Fora do try: se o recarregamento falhar depois de um salvamento bem
      // sucedido, o catch abaixo NÃO deve sobrescrever a mensagem de sucesso
      // por uma de erro (bug antigo: dizia "não foi possível salvar" quando na
      // verdade tinha salvo, levando o RH a reeditar à toa).
    } catch (e) {
      // e.campos vem do 422 estruturado [{loc, msg}] que o backend agora
      // devolve (rh_ficha.py); antes disso o api.js descartava a lista e só
      // sobrava a string genérica 'dados_invalidos' ou 'erro'.
      const texto = Array.isArray(e.campos)
        ? e.campos.map((c) => `${(c.loc || []).slice(-1)[0]}: ${c.msg}`).join('; ')
        : (e.amigavel || e.detail || e.message)
      setMsgSecao((m) => ({ ...m, [secao]: { tipo: 'erro', texto: `Não foi possível salvar (${texto}).` } }))
      setSalvando(null)
      return
    }
    setSalvando(null)
    carregar().catch(() => {})
  }

  return (
    <div className="rh-card">
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <strong>✏️ Corrigir dados da ficha</strong>
        <button className="btn-link" onClick={() => setAberta(false)}>fechar</button>
      </div>
      <p className="explica">Deixar um campo em branco apaga o valor. Toda alteração exige
        motivo e fica na auditoria com o antes e o depois. Se o dado aparece em documento já
        assinado, a assinatura é invalidada e o candidato assina a versão nova —
        <strong> quem assina é sempre ele</strong>.</p>
      <label className="campo"><span className="rotulo">Motivo da correção (obrigatório)</span>
        <input value={motivo} placeholder="ex.: candidato informou RG errado pelo WhatsApp"
               onChange={(e) => setMotivo(e.target.value)} /></label>
      {Object.entries(SECOES_FICHA).map(([secao, campos]) => (
        <details key={secao} className="ficha-rh-secao">
          <summary>{secao.replace('-', ' e ')}</summary>
          {campos.map((campo) => {
            const chave = `${secao}.${campo}`
            const atual = valorAtual(secao, campo)
            const valorEdit = chave in edicao ? edicao[chave] : (atual ?? '')
            // Campos booleanos viram <select> — nunca <input> texto: digitar
            // "sim" num input gravaria false silenciosamente (dado médico em
            // usa_medicamento_continuo). O submit converte "true"/"false".
            const ehBool = CAMPOS_BOOL.has(campo)
            const ehData = CAMPOS_DATA.has(campo)
            const ehUf = CAMPOS_UF.has(campo)
            const opcoesEnum = CAMPOS_ENUM[campo]
            return (
              <label className="campo" key={campo}>
                <span className="rotulo">{campo.replaceAll('_', ' ')}
                  {atual == null || atual === '' ? <em> — vazio</em> : null}</span>
                {ehBool ? (
                  <SelectBusca valor={valorEdit === '' ? '' : String(valorEdit)}
                               aoEscolher={(v) => setEdicao({ ...edicao, [chave]: v })}>
                    <option value="">— não informado —</option>
                    <option value="true">Sim</option>
                    <option value="false">Não</option>
                  </SelectBusca>
                ) : ehData ? (
                  <InputData valor={valorEdit || ''}
                             onChange={(iso) => setEdicao({ ...edicao, [chave]: iso ?? '' })} />
                ) : opcoesEnum ? (
                  <SelectBusca valor={valorEdit} aoEscolher={(v) => setEdicao({ ...edicao, [chave]: v })}>
                    <option value="">— não informado —</option>
                    {opcoesEnum.map(([v, rotulo]) => <option key={v} value={v}>{rotulo}</option>)}
                  </SelectBusca>
                ) : ehUf ? (
                  <SelectBusca valor={valorEdit} aoEscolher={(v) => setEdicao({ ...edicao, [chave]: v })}>
                    <option value="">— não informado —</option>
                    {UFS.map((u) => <option key={u} value={u}>{u}</option>)}
                  </SelectBusca>
                ) : (
                  <input value={valorEdit}
                         onChange={(e) => setEdicao({ ...edicao, [chave]: e.target.value })} />
                )}
              </label>
            )
          })}
          {secao === 'vt-emergencia' && (ficha.contatos_emergencia || []).length > 0 && (
            <div className="explica" style={{ width: '100%' }}>
              <strong>Contatos de emergência</strong> (preenchidos pelo candidato):
              <ul style={{ margin: '.3rem 0 0', paddingLeft: '1.1rem' }}>
                {ficha.contatos_emergencia.map((c) => (
                  <li key={c.id}>{c.nome_completo} — {c.parentesco} · {c.telefone_celular}
                    {c.telefone_fixo_endereco ? ` · ${c.telefone_fixo_endereco}` : ''}</li>
                ))}
              </ul>
            </div>
          )}
          {msgSecao[secao] && (
            <div className={msgSecao[secao].tipo === 'erro' ? 'alerta' : 'sucesso'}
                 style={{ width: '100%' }}>{msgSecao[secao].texto}</div>
          )}
          <button className="btn-principal btn-mini" disabled={salvando === secao}
                  onClick={() => salvarSecao(secao)}>
            {salvando === secao ? 'Salvando…' : 'Salvar esta seção'}</button>
        </details>
      ))}
    </div>
  )
}

// Anotações + tags do colaborador/candidato, num MODAL (v1.97 — antes era um
// recolhível inline; o conteúdo tem anexo+histórico e texto longo, que é
// justamente o caso em que o sistema de design admite modal ancorado em vez
// de inline. A memória é a MESMA da pessoa no Banco de Talentos — segue o
// ciclo de vida.
function MemoriaColaborador({ id, nome }) {
  const [aberto, setAberto] = useState(false)
  return (
    <div className="rh-card">
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                    flexWrap: 'wrap', gap: '.5rem' }}>
        <strong>🗒️ Anotações e tags</strong>
        <button className="btn-link" onClick={() => setAberto(true)}>ver / adicionar</button>
      </div>
      {aberto && (
        <Modal titulo={`🗒️ Anotações — ${nome}`} aoFechar={() => setAberto(false)}>
          <MemoriaPessoa pessoa={{ candidato_id: id }} />
        </Modal>
      )}
    </div>
  )
}

// Informativo de integração: o candidato só o vê para assinar DEPOIS que o RH
// dispara aqui (feedback do Bruno). Some se não houver informativo (efetivo
// não-INFRAERO). Recolhido quando não há nada pendente.
// Documento ESPECÍFICO acrescentado a UMA pessoa (v2.79).
//
// Nasceu da COBERTURA (feedback do Bruno): *"um intermitente precisou dar
// cobertura na presidência da República. Não estava fácil marcar para emitir os
// documentos específicos da presidência"*.
//
// O kit da Presidência sempre existiu e sempre foi selecionável — mas **por
// POSTO**, e numa cobertura a pessoa justamente NÃO está lotada no posto que
// exige o documento. As saídas eram lotá-la lá (muda o vínculo dela para emitir
// um papel) ou marcar o kit no posto dela (passaria a exigir aquilo de todo
// mundo daquele posto). Aqui é para UMA pessoa, e mais nada.
//
// Fica RECOLHIDO: é caso excepcional, e um bloco sempre aberto competiria com o
// que se faz todo dia nesta tela. O `<details>` traz cursor, marcador e respiro
// do styles.css — nada de style inline (v2.47.1).
function DocumentosEspecificos({ id, setMsg }) {
  const [itens, setItens] = useState(null)
  const [escolhido, setEscolhido] = useState('')
  const [motivo, setMotivo] = useState('')
  const [salvando, setSalvando] = useState(false)

  const carregar = () => api.documentosEspecificos(id)
    .then((r) => setItens(r.disponiveis || []))
    .catch(() => setItens([]))
  useEffect(() => { carregar() }, [id])

  const acrescentar = async () => {
    if (!escolhido) { setMsg?.({ tipo: 'erro', texto: 'Escolha o documento.' }); return }
    if (!motivo.trim()) {
      setMsg?.({ tipo: 'erro', texto: 'Diga o motivo — é o que explica depois por que esta pessoa assinou este documento.' })
      return
    }
    setSalvando(true)
    try {
      const r = await api.acrescentarDocumentoEspecifico(id, escolhido, motivo.trim())
      setMsg?.({ tipo: 'ok', texto: `${r.rotulo} acrescentado — já aparece para a pessoa assinar.` })
      setEscolhido(''); setMotivo('')
      carregar()
    } catch (e) {
      // O 409 traz se o documento já foi ASSINADO: reemitir apagaria o que ela
      // assinou, e a mensagem precisa distinguir os dois casos.
      const d = e.dados
      setMsg?.({ tipo: 'erro', texto: d?.erro === 'documento_ja_existe'
        ? `${d.rotulo} já está ${d.assinado ? 'assinado' : 'pendente'} para esta pessoa.`
        : `Não foi possível acrescentar (${e.detail || e.message}).` })
    } finally { setSalvando(false) }
  }

  if (!itens || itens.length === 0) return null
  const livres = itens.filter((i) => !i.ja_tem)

  return (
    <details>
      <summary>📎 Acrescentar documento específico (cobertura, caso excepcional)</summary>
      <div className="rh-card">
        <p className="explica">
          Para quem vai <strong>dar cobertura</strong> num posto que exige documento
          próprio — Presidência, INFRAERO — sem mudar a lotação dela. Vale só para
          esta pessoa; o posto e os demais colaboradores não mudam.
        </p>
        {livres.length === 0 ? (
          <p className="explica">Esta pessoa já tem todos os documentos específicos.</p>
        ) : (
          <div className="rh-grid-2">
            <div className="campo">
              <span className="rotulo">Documento</span>
              <SelectBusca valor={escolhido} aoEscolher={setEscolhido}
                           opcoes={[{ valor: '', rotulo: '— escolha —' },
                                    ...livres.map((i) => ({ valor: i.chave, rotulo: i.rotulo }))]} />
            </div>
            <label className="campo">
              <span className="rotulo">Motivo
                <span className="dica-inline"> — fica na auditoria</span></span>
              <input value={motivo} autoComplete="off"
                     placeholder="Ex.: cobertura na Presidência em 08/08"
                     onChange={(ev) => setMotivo(ev.target.value)} />
            </label>
          </div>
        )}
        {livres.length > 0 && (
          <div className="navegacao">
            <button className="btn-principal btn-mini" disabled={salvando}
                    onClick={acrescentar}>
              {salvando ? 'Acrescentando…' : 'Acrescentar documento'}
            </button>
          </div>
        )}
        {itens.some((i) => i.ja_tem) && (
          <p className="explica">
            Já tem: {itens.filter((i) => i.ja_tem).map((i) => i.rotulo).join(' · ')}
          </p>
        )}
      </div>
    </details>
  )
}

// Data que os documentos NÃO assinados desta pessoa carimbam (v2.89, feedback
// do Bruno: o papel costuma sair dias depois do ato — a integração aconteceu
// segunda e o documento é impresso na quarta, saindo com a data da impressão).
//
// Mora ao lado do informativo porque é ali que se decide o que a pessoa vai
// assinar; e a mensagem diz quantos documentos JÁ estão assinados, porque eles
// não mudam — silêncio faria parecer que a correção alcançou o dossiê inteiro.
function DataDosDocumentos({ id, valorInicial, setMsg }) {
  const [data, setData] = useState(valorInicial || '')
  const [salvando, setSalvando] = useState(false)

  const salvar = async (nova) => {
    setSalvando(true)
    try {
      const r = await api.definirDataDocumentos(id, nova)
      setData(r.data || '')
      setMsg?.({
        tipo: 'ok',
        texto: r.data
          // `isoParaBR`, NÃO `fmtData`: esta é uma data PURA (aaaa-mm-dd, sem
          // hora), e `new Date("2026-08-03")` é lido como UTC meia-noite —
          // convertido para São Paulo (UTC-3) vira 02/08 às 21h. O banco
          // guardava 03/08 e a tela dizia 02/08. Converter por TEXTO não passa
          // por fuso nenhum.
          ? `Documentos passam a sair com a data ${isoParaBR(r.data)}.`
            + (r.assinados_inalterados
               ? ` Os ${r.assinados_inalterados} já assinados mantêm a data em que foram assinados.`
               : '')
          : 'Voltou ao padrão: os documentos saem com a data do dia em que forem gerados.',
      })
    } catch (e) {
      setMsg?.({
        tipo: 'erro',
        texto: e.detail === 'data_futura'
          ? 'A data não pode estar no futuro — confira o ano digitado.'
          : `Não foi possível salvar (${e.detail || e.message}).`,
      })
    } finally { setSalvando(false) }
  }

  return (
    <div className="campo">
      <span className="rotulo">Data dos documentos</span>
      <div className="rh-lote" style={{ margin: 0 }}>
        <InputData valor={data} onChange={setData} />
        <button className="btn-secundario btn-mini" disabled={salvando}
                onClick={() => salvar(data)}>
          {salvando ? 'Salvando…' : 'Salvar data'}</button>
        {data && (
          <button className="btn-link" disabled={salvando}
                  onClick={() => { setData(''); salvar(null) }}>usar a data de hoje</button>
        )}
      </div>
      <small className="explica">
        Em branco, cada documento sai com a data do dia em que for gerado. Use
        quando o papel for emitido depois do ato — a integração de segunda
        impressa na quarta. <strong>Documento já assinado não muda</strong>:
        ele carrega a data em que foi assinado.
      </small>
    </div>
  )
}

function PainelInformativo({ id, setMsg }) {
  const [itens, setItens] = useState(null)
  const [liberando, setLiberando] = useState(false)
  const carregar = () => api.informativos(id).then(setItens).catch(() => setItens([]))
  useEffect(() => { carregar() }, [id])

  if (!itens || itens.length === 0) return null   // este candidato não tem informativo
  const pendentes = itens.filter((i) => i.aguardando_liberacao)

  const liberar = async () => {
    setLiberando(true); setMsg?.(null)
    try {
      const r = await api.liberarInformativo(id)
      setMsg?.({ tipo: 'ok', texto: `Informativo liberado — o candidato já pode assinar (${r.liberados}).` })
      carregar()
    } catch (e) {
      setMsg?.({ tipo: 'erro', texto: `Não foi possível liberar (${e.detail || e.message}).` })
    } finally { setLiberando(false) }
  }

  return (
    <div className="rh-card">
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                    flexWrap: 'wrap', gap: '.5rem' }}>
        <strong>📣 Informativo de integração</strong>
        {pendentes.length > 0 && (
          <button className="btn-principal btn-mini" disabled={liberando} onClick={liberar}>
            {liberando ? 'Liberando…' : '📨 Liberar para o candidato assinar'}</button>
        )}
      </div>
      <ul className="fichas-status" style={{ marginTop: '.4rem' }}>
        {itens.map((i) => (
          <li key={i.documento}>
            {i.assinado ? '✅' : i.aguardando_liberacao ? '🔒' : '⏳'} {i.nome}
            <small> · {i.assinado ? 'assinado'
              : i.aguardando_liberacao ? 'aguardando você liberar' : 'liberado, aguardando assinatura'}</small>
          </li>
        ))}
      </ul>
      {pendentes.length > 0 && (
        <p className="explica" style={{ margin: 0 }}>Enquanto não liberar, o informativo
          não aparece para o candidato assinar.</p>)}
    </div>
  )
}

export default function Detalhe({ id, aoVoltar }) {
  const [dados, setDados] = useState(null)
  const [visualizando, setVisualizando] = useState(null) // slot id
  const [pdf, setPdf] = useState(null) // {blob, url} do documento em exibição
  const [rejeitando, setRejeitando] = useState(null)
  const [motivo, setMotivo] = useState('ilegivel')
  const [obs, setObs] = useState('')
  const [msg, setMsg] = useState(null)
  const [selecionados, setSelecionados] = useState(new Set())
  const [loteRejeitar, setLoteRejeitar] = useState(false)
  const [pendDossie, setPendDossie] = useState(null)
  // Peças corrompidas e falha de montagem não-nomeada: estados PRÓPRIOS porque
  // os três oferecem a MESMA saída (gerar parcial) — e antes só o de pendência
  // a oferecia (v2.93).
  const [ilegiveis, setIlegiveis] = useState(null)
  const [falhaMontagem, setFalhaMontagem] = useState(null)

  const [erroCarga, setErroCarga] = useState(null)
  const recarregar = () => api.detalhe(id).then(setDados)
  // O catch fica SÓ na carga inicial: `recarregar()` também é chamado depois de
  // cada ação (aprovar, rejeitar, salvar) e ali o erro é reportado por `msg` —
  // trocar a tela inteira por uma mensagem apagaria o trabalho em curso.
  const carregar = () => recarregar().then(() => setErroCarga(null))
    .catch(() => setErroCarga('Não foi possível carregar esta pessoa.'))
  useEffect(() => { carregar() }, [id])

  const ver = async (slot) => {
    setVisualizando(slot.id)
    const blob = await api.arquivo(slot.id)
    setPdf({ blob, url: URL.createObjectURL(blob) })
  }

  if (erroCarga) return (
    <main className="rh-painel">
      <div className="rh-card">
        <div className="alerta">{erroCarga}</div>
        <button className="btn-secundario btn-mini" onClick={carregar}>tentar de novo</button>
        {aoVoltar && <button className="btn-link" onClick={aoVoltar}>← voltar</button>}
      </div>
    </main>
  )
  if (!dados) return <main className="rh-painel"><p>Carregando…</p></main>

  const enviados = dados.slots.filter((s) => s.status === 'enviado')

  const nomeDoc = (slot) => (DICAS[slot.tipo] || {}).nome || slot.tipo.replace(/_/g, ' ')
  const aprovar = async (slot) => {
    if (!window.confirm(`Aprovar "${nomeDoc(slot)}"? Ele entra no dossiê do colaborador.`)) return
    await api.aprovar(slot.id); await recarregar()
  }
  const rejeitar = async (slot) => {
    if (!window.confirm(`Rejeitar "${nomeDoc(slot)}"?\n\nO arquivo enviado será apagado e o `
      + 'colaborador precisará enviar outro. Esta ação fica registrada na auditoria.')) return
    await api.rejeitar(slot.id, motivo, obs || null)
    setRejeitando(null); setObs('')
    await recarregar()
  }

  const inputManual = { current: null }

  const inserirNoSlot = (slot) => {
    const origem = window.prompt(
      'Como este documento chegou? (ex.: WhatsApp, e-mail, presencial)', 'WhatsApp')
    if (origem == null) return
    const input = document.createElement('input')
    input.type = 'file'
    input.accept = 'image/*,.pdf,.doc,.docx'
    input.multiple = true   // vários arquivos no mesmo tipo → um PDF combinado
    input.onchange = async () => {
      const arqs = input.files
      if (!arqs || arqs.length === 0) return
      setMsg(null)
      try {
        await api.inserirArquivo(slot.id, arqs, origem.trim() || 'WhatsApp')
        setMsg({ tipo: 'ok', texto: `Documento inserido (${arqs.length} arquivo(s), combinados) e etiquetado — revise e aprove.` })
        await recarregar()
      } catch (e) {
        setMsg({ tipo: 'erro', texto: `Não foi possível inserir (${e.detail || e.message}).` })
      }
    }
    input.click()
  }

  const reabrir = async (slot) => {
    const motivo = window.prompt('Motivo da reabertura (obrigatório — vai para a auditoria):')
    if (!motivo?.trim()) return
    setMsg(null)
    try {
      await api.reabrirSlot(slot.id, motivo.trim())
      setMsg({ tipo: 'ok', texto: 'Status reaberto (registrado na auditoria).' })
      await recarregar()
    } catch (e) {
      setMsg({ tipo: 'erro', texto: `Não foi possível reabrir (${e.detail || e.message}).` })
    }
  }

  const gerarDossie = async (forcar = false) => {
    if (!window.confirm(forcar
      ? 'Gerar o dossiê PARCIAL (com pendências)? O colaborador NÃO será marcado como aprovado.'
      : `Gerar o dossiê de ${dados.nome_completo} e marcar como APROVADO?`)) return
    setMsg(null); setPendDossie(null); setIlegiveis(null); setFalhaMontagem(null)
    try {
      const r = await api.gerarDossie(id, forcar)
      // Peça pulada por estar ilegível: o dossiê SAIU, mas incompleto. Dizer
      // "gerado!" aqui esconderia a página que falta de quem vai mandar o PDF
      // ao cliente.
      const pulados = Array.isArray(r?.ilegiveis) ? r.ilegiveis : []
      setMsg(pulados.length
        ? { tipo: 'erro', texto: `Dossiê gerado SEM ${pulados.length === 1
            ? 'uma peça que não pôde ser lida' : `${pulados.length} peças que não puderam ser lidas`}: `
            + `${pulados.join(', ')}. O arquivo está corrompido ou ilegível — reenvie o documento `
            + 'e gere o dossiê de novo. O colaborador NÃO foi marcado como aprovado.' }
        : { tipo: 'ok', texto: forcar
            ? 'Dossiê PARCIAL gerado (há pendências — o candidato não foi marcado como aprovado).'
            : 'Dossiê gerado! O candidato foi marcado como aprovado.' })
      await recarregar()
    } catch (e) {
      // 422 com lista de pendências → mostra a lista. Qualquer outro erro (500,
      // arquivo faltando no storage, etc.) NÃO é "sem pendências": mostra o erro
      // real, senão o RH vê um banner vazio e acha que "estava tudo certo".
      if (Array.isArray(e.detail?.pendencias)) {
        setPendDossie(e.detail.pendencias)
      } else if (Array.isArray(e.dados?.ilegiveis)) {
        // Todas as peças estavam corrompidas. Diz QUAIS e o que resolve —
        // reenviar o documento, não mexer em campo obrigatório (v2.93).
        setIlegiveis(e.dados.ilegiveis)
      } else if (e.amigavel) {
        setMsg({ tipo: 'erro', texto: e.amigavel })
      } else {
        // Falha de montagem que não sabemos nomear. A saída (dossiê parcial)
        // existe desde sempre, mas só aparecia no erro de PENDÊNCIA — no erro
        // de MONTAGEM a tela recusava sem oferecer nada, e quem opera ia
        // procurar a saída no lugar errado (o caso de 11/08/2026: 54 min
        // desmarcando exigência médica por causa de um PDF corrompido).
        setFalhaMontagem(`${e.detail || e.message}`)
      }
    }
  }

  const baixarDossie = async () => {
    const blob = await api.baixarDossie(id)
    const a = document.createElement('a')
    a.href = URL.createObjectURL(blob)
    a.download = `dossie-${dados.nome_completo}.pdf`
    a.click()
  }

  const efetivar = async () => {
    const aprovado = dados.status === 'aprovado'
    const aviso = aprovado
      ? `Efetivar ${dados.nome_completo} como colaborador ativo? Ele passará a constar na página de Colaboradores.`
      : `ATENÇÃO: ${dados.nome_completo} ainda NÃO está aprovado (status atual: ${statusInfo(dados.status).label}).`
        + '\n\nEfetivar mesmo assim como colaborador ativo?'
    if (!window.confirm(aviso)) return
    setMsg(null)
    try {
      await api.efetivarColaborador(id)
      setMsg({ tipo: 'ok', texto: `${dados.nome_completo} agora é colaborador ativo.` })
      await recarregar()
    } catch (e) {
      setMsg({ tipo: 'erro', texto: e.amigavel || `Não foi possível efetivar (${e.detail || e.message}).` })
    }
  }

  return (
    <main className="rh-painel">
      <header className="rh-topo">
        <button className="btn-link" onClick={aoVoltar}>← Voltar</button>
        <h1>{dados.nome_completo}</h1>
        <div>
          <button className="btn-secundario btn-mini" title="Posta no canal do Teams (se configurado em Configurações)"
                  onClick={async () => {
                    if (!window.confirm(`Enviar uma mensagem ao canal do Teams sobre ${dados.nome_completo}?`)) return
                    setMsg(null)
                    try {
                      await api.enviarTeams(id)
                      setMsg({ tipo: 'ok', texto: 'Mensagem enviada ao Teams.' })
                    } catch (e) {
                      setMsg({ tipo: 'erro', texto: e.detail === 'teams_nao_configurado'
                        ? 'Configure o webhook do Teams em Configurações → Notificações no Teams.'
                        : `Não foi possível enviar ao Teams (${e.detail || e.message}).` })
                    }
                  }}>💬 Enviar ao Teams</button>
          <button className="btn-secundario btn-mini" onClick={() => gerarDossie(false)}>Gerar dossiê</button>
          <Ajuda termo="dossie" />
          {dados.dossie_gerado_em && (
            <button className="btn-secundario btn-mini" onClick={baixarDossie}>⬇ Baixar dossiê</button>
          )}
          {/* Efetivar é a ação PRIMÁRIA da tela (e irreversível) — as demais do
              cabeçalho são secundárias. Antes "⬇ Baixar dossiê" levava o
              btn-principal e dominava o topo, deixando o efetivar com menos
              peso visual que um download. Tokens no lugar dos hex de sempre. */}
          {dados.situacao === 'ativo'
            ? <span className="chip" style={{ '--chip-cor': 'var(--verde-vivo)' }}
                    title={dados.data_admissao ? `Admissão: ${dados.data_admissao}` : undefined}>
                ✅ Colaborador ativo</span>
            : dados.situacao === 'desligado'
            ? <span className="chip" style={{ '--chip-cor': 'var(--cinza-txt)' }}>⚪ Desligado</span>
            : <><button className="btn-principal btn-mini" onClick={efetivar}
                      title="Transforma este candidato em colaborador ativo (aparece em Colaboradores)">
                ✅ Efetivar como colaborador</button><Ajuda termo="efetivar" /></>}
        </div>
      </header>
      <p className="explica">
        <ContatoEditavel dados={dados} setMsg={setMsg} recarregar={recarregar} /> · status:
        <span className="chip" style={{ '--chip-cor': statusInfo(dados.status).cor }}>
          {statusInfo(dados.status).icone} {statusInfo(dados.status).label}</span>
        {enviados.length > 0 && <> · <strong>{enviados.length} documento(s) aguardando revisão</strong></>}
      </p>
      {msg && <div className={msg.tipo === 'erro' ? 'alerta' : 'sucesso'}>{msg.texto}</div>}

      {/* O IMPEDIMENTO vem antes de tudo (v2.95, redesenho validado pelo Bruno).
          Ele já existia — dentro do Diagnóstico, no FIM da página, atrás de um
          dobrável, depois de ~65 linhas de telemetria. É a única frase da tela
          que responde "por que esta pessoa ainda não fechou?", que é a razão de
          alguém abrir a ficha. Em 11/08/2026 isso custou 54 minutos: a analista
          tomou o erro do dossiê 8× sem nunca ver esta linha, e foi desmarcar
          exigências médicas achando que a culpa era delas. */}
      <ImpedimentoDaFicha id={id} recarga={dados.dossie_gerado_em} />

      {/* Atendimento presencial (v2.58): fica no TOPO, não num histórico lá
          embaixo — quem abre a ficha precisa saber, antes de qualquer coisa,
          que aquela admissão foi (ou está sendo) preenchida pelo RH com a
          pessoa presente. Antes isso existia só na auditoria geral, que
          ninguém abre no dia a dia. */}
      <AtendimentoAssistido lista={dados.atendimentos_assistidos} />

      {/* ===== ORDEM DA TELA (v2.47) =====
          O Bruno usa esta tela para DUAS coisas com o mesmo peso: conferir
          documentos e corrigir cadastro. Antes havia SEIS blocos de consulta
          (CRM, testes vinculados, telemetria, fichas, roteiro, diagnóstico)
          enfiados ENTRE as duas — ele aprovava lá embaixo, rolava pra cima para
          acertar o posto e voltava. A causa do "muito rolar" não era a fila
          estar por último: era a consulta estar no meio.
          Agora: [1] documentos  [2] cadastro  — coladas, no topo.
                 [3] consulta — no fim, colapsada. */}

      {/* Informativo de integração: ação (liberar), não consulta — fica junto
          do trabalho. Some quando o candidato não tem informativo. */}
      <PainelInformativo id={id} setMsg={setMsg} />
      <DataDosDocumentos id={id} valorInicial={dados.data_documentos} setMsg={setMsg} />

      {/* Documento específico avulso: ação, fica junto do trabalho (regra da
          v2.47 — trabalho e consulta em faixas separadas). */}
      <DocumentosEspecificos id={id} setMsg={setMsg} />

      {/* O que ESTA pessoa precisa entregar (v2.80). Recolhido: o padrão serve
          quase todo mundo, e um bloco sempre aberto com ~50 itens competiria
          com o trabalho diário desta tela.
          ⚠️ O RESUMO das exceções fica FORA do `<details>` (v2.95): dentro, ele
          só apareceria para quem abrisse — e o problema que ele resolve é
          justamente ninguém abrir. `<details>` fechado nem renderiza o conteúdo
          (v2.76.2), então o resumo precisa de consulta própria. */}
      <ResumoExigenciasDaPessoa id={id} />
      <details>
        <summary>☑️ O que é obrigatório para esta pessoa</summary>
        <Exigencias candidatoId={id} setMsg={setMsg} />
      </details>

      {pendDossie && (
        <div className="alerta">
          <strong>O dossiê ainda tem pendências:</strong> {pendDossie.join(', ')}.
          <div style={{ marginTop: '.6rem' }}>
            <button className="btn-secundario btn-mini" onClick={() => gerarDossie(true)}>
              Gerar assim mesmo (dossiê parcial)</button>
            <button className="btn-link" onClick={() => setPendDossie(null)}>cancelar</button>
          </div>
        </div>
      )}

      {/* Nenhuma peça pôde ser lida. O que resolve é REENVIAR o documento —
          dizer só "não foi possível" mandava quem opera procurar a causa em
          outro lugar (mexer em exigência não conserta PDF corrompido). */}
      {ilegiveis && (
        <div className="alerta">
          <strong>Nenhum documento pôde ser lido para montar o dossiê:</strong>{' '}
          {ilegiveis.join(', ')}.
          <p className="explica">Esses arquivos estão corrompidos ou num formato que o
            sistema não consegue abrir. Reabra o documento na ficha, peça o reenvio e
            gere o dossiê de novo. Mexer nos campos obrigatórios não resolve este erro.</p>
          <div style={{ marginTop: '.6rem' }}>
            <button className="btn-link" onClick={() => setIlegiveis(null)}>fechar</button>
          </div>
        </div>
      )}

      {/* Falha que não sabemos nomear: oferece a MESMA saída do erro de
          pendência. Recusar sem alternativa deixa o problema na mão de quem
          opera — a regra da v2.87, aplicada aqui na v2.93. */}
      {falhaMontagem && (
        <div className="alerta">
          <strong>O dossiê não pôde ser montado:</strong> {falhaMontagem}.
          <p className="explica">Se for urgente, dá para gerar o dossiê com o que já
            existe e completar depois — o colaborador NÃO é marcado como aprovado.
            O Diagnóstico deste colaborador mostra o motivo exato.</p>
          <div style={{ marginTop: '.6rem' }}>
            <button className="btn-secundario btn-mini" onClick={() => gerarDossie(true)}>
              Gerar assim mesmo (dossiê parcial)</button>
            <button className="btn-link" onClick={() => setFalhaMontagem(null)}>cancelar</button>
          </div>
        </div>
      )}

      {enviados.length > 0 && (
        <div className="rh-card rh-lote">
          <strong>Ações em massa:</strong>
          <button className="btn-link" onClick={() =>
            setSelecionados(new Set(enviados.map((s) => s.id)))}>
            selecionar todos em análise ({enviados.length})</button>
          <button className="btn-link" onClick={() => setSelecionados(new Set())}>limpar</button>
          <span className="explica" style={{ margin: 0 }}>{selecionados.size} selecionado(s)</span>
          <button className="btn-principal btn-mini" disabled={!selecionados.size}
                  onClick={async () => {
                    if (!window.confirm(`Aprovar ${selecionados.size} documento(s) selecionado(s)? Todos entram no dossiê.`)) return
                    try {
                      const r = await api.aprovarLote([...selecionados])
                      setSelecionados(new Set()); setMsg({ tipo: 'ok',
                        texto: `${r.aprovados} documento(s) aprovado(s).` })
                      await recarregar()
                    } catch (e) {
                      setMsg({ tipo: 'erro',
                        texto: `Não foi possível aprovar em massa (${e.detail || e.message}).` })
                    }
                  }}>Aprovar selecionados</button>
          <button className="btn-rejeitar btn-mini" disabled={!selecionados.size}
                  onClick={() => setLoteRejeitar(!loteRejeitar)}>Rejeitar selecionados</button>
          {loteRejeitar && (
            <div className="rejeicao" style={{ width: '100%' }}>
              <SelectBusca valor={motivo} aoEscolher={(v) => setMotivo(v)}>
                {MOTIVOS.map(([v, r]) => <option key={v} value={v}>{r}</option>)}
              </SelectBusca>
              <input placeholder="Observação (opcional)" value={obs}
                     onChange={(e) => setObs(e.target.value)} />
              <button className="btn-rejeitar btn-mini" onClick={async () => {
                if (!window.confirm(`Rejeitar ${selecionados.size} documento(s)? Os arquivos serão apagados e o colaborador precisará reenviá-los.`)) return
                try {
                  const r = await api.rejeitarLote([...selecionados], motivo, obs || null)
                  setSelecionados(new Set()); setLoteRejeitar(false); setObs('')
                  setMsg({ tipo: 'ok', texto: `${r.rejeitados} documento(s) rejeitado(s) — o candidato recebeu um único e-mail com a lista.` })
                  await recarregar()
                } catch (e) {
                  setMsg({ tipo: 'erro',
                    texto: `Não foi possível rejeitar em massa (${e.detail || e.message}).` })
                }
              }}>Confirmar rejeição em massa</button>
            </div>
          )}
        </div>
      )}

      <div className="rh-revisao">
        <div className="rh-lista-slots">
          {dados.slots.map((s) => {
            const info = DICAS[s.tipo] || { nome: s.tipo }
            return (
              <div className={`slot ${s.status} ${visualizando === s.id ? 'ativo' : ''}`} key={s.id}>
                <div className="slot-linha">
                  {s.status === 'enviado' && (
                    <input type="checkbox" className="check-slot"
                           checked={selecionados.has(s.id)}
                           onChange={(e) => {
                             const novo = new Set(selecionados)
                             e.target.checked ? novo.add(s.id) : novo.delete(s.id)
                             setSelecionados(novo)
                           }} />
                  )}
                  <div className="slot-nome">
                    <strong>{info.nome}</strong>{!s.obrigatorio && <em> (opcional)</em>}
                    <div className="slot-status">{s.status}
                      {s.paginas ? ` · ${s.paginas} pág.` : ''}
                      {s.origem_envio === 'rh' &&
                        <span className="etiqueta-rh"> 📎 inserido pelo RH
                          {s.origem_envio_obs ? ` (${s.origem_envio_obs})` : ''}</span>}
                    </div>
                  </div>
                  {s.status !== 'pendente' && s.paginas && (
                    <button className="btn-secundario btn-mini" onClick={() => ver(s)}>Ver</button>
                  )}
                  {s.status === 'enviado' && <>
                    <button className="btn-principal btn-mini" onClick={() => aprovar(s)}>
                      Aprovar</button>
                    <button className="btn-rejeitar btn-mini"
                            onClick={() => setRejeitando(rejeitando === s.id ? null : s.id)}>
                      Rejeitar</button>
                  </>}
                  {s.status === 'pendente' && !s.obrigatorio && (
                    <button className="btn-link" onClick={async () => {
                      if (!window.confirm(`Dispensar "${nomeDoc(s)}"? Este documento deixará de ser exigido deste colaborador.`)) return
                      await api.dispensar(s.id); await recarregar()
                    }}>dispensar</button>
                  )}
                  {['pendente', 'rejeitado', 'enviado'].includes(s.status) && (
                    <button className="btn-secundario btn-mini"
                            title="Documento recebido por WhatsApp/e-mail/presencial: insira aqui (fica etiquetado na auditoria)"
                            onClick={() => inserirNoSlot(s)}>📎 Inserir</button>
                  )}
                  {['aprovado', 'dispensado', 'rejeitado'].includes(s.status) && (
                    <button className="btn-link" title="Desfaz a decisão (pede motivo)"
                            onClick={() => reabrir(s)}>↩ reabrir</button>
                  )}
                </div>
                {rejeitando === s.id && (
                  <div className="rejeicao">
                    <SelectBusca valor={motivo} aoEscolher={(v) => setMotivo(v)}>
                      {MOTIVOS.map(([v, r]) => <option key={v} value={v}>{r}</option>)}
                    </SelectBusca>
                    <input placeholder="Observação (opcional)" value={obs}
                           onChange={(e) => setObs(e.target.value)} />
                    <button className="btn-rejeitar btn-mini" onClick={() => rejeitar(s)}>
                      Confirmar rejeição</button>
                  </div>
                )}
              </div>
            )
          })}
        </div>
        <div className="rh-visualizador">
          {pdf ? (
            <>
              <a className="btn-link so-celular" href={pdf.url} download="documento.pdf">⬇ Baixar este PDF</a>
              <PdfViewer blob={pdf.blob} url={pdf.url} />
            </>
          ) : <p className="explica centro">Selecione "Ver" em um documento para visualizar aqui.</p>}
        </div>
      </div>

      {/* ===== 2. CADASTRO — a outra metade do trabalho, colada na primeira ===== */}
      <PostoServico dados={dados} recarregar={recarregar} />
      {/* auto-ajuste: quando não há modelo aplicável, `ModelosDoColaborador`
          devolve null e a grade de 2 colunas deixaria metade da linha vazia. */}
      <div className="rh-grid-auto">
        <ModelosDoColaborador id={id} />
        <FichaRH id={id} />
      </div>

      {/* ===== 3. CONSULTA — não é trabalho do dia a dia: fica no fim e fechada.
           Antes estes seis blocos ficavam ENTRE as duas áreas acima. ===== */}
      <details className="rh-card">
        <summary>🔎 Histórico e consulta desta pessoa</summary>
        <div className="rh-grid-2">
          <FichasStatus dados={dados} />
          <TestesDoCandidato id={id} />
        </div>
        <RoteiroAssinatura id={id} />
        {/* Mini-CRM: anotações + tags que acompanham a pessoa desde o Banco de
            Talentos. */}
        <MemoriaColaborador id={id} nome={dados.nome_completo} />
        {/* Entrevistas da pessoa (v2.64): atravessa talento↔candidato pelo
            escopo do CRM — a entrevista feita quando ela era talento continua
            aqui depois da conversão. */}
        <EntrevistasDaPessoa candidatoId={id} />
        <TestesVinculados candidatoId={id} nome={dados.nome_completo} />
        {/* O que aconteceu na TELA desta pessoa (v2.24) */}
        <TelemetriaPessoa candidatoId={id} />
        <DiagnosticoColaborador id={id} />
      </details>
    </main>
  )
}

// Cores clássicas do DISC para o gráfico.
const CORES_DISC = { D: '#d9534f', I: '#f0ad4e', S: '#0fb257', C: '#3b7dd8' }
const STATUS_TESTE = {
  pendente: 'aguardando o candidato', em_andamento: 'em andamento',
  concluido: 'concluído', expirado: 'tempo esgotado (pontuado parcial)',
}

// Resultados dos testes — VISÍVEIS SÓ AQUI (painel do RH). O candidato nunca
// recebe o resultado. Uso como APOIO à decisão, nunca critério único
// (inventário comportamental não é avaliação psicológica — Res. CFP 31/2022).
function TestesDoCandidato({ id }) {
  const [dados, setDados] = useState(null)

  const recarregar = () =>
    api.testesCandidato(id).then(setDados).catch(() => setDados({ testes: [] }))
  useEffect(() => { recarregar() }, [id])

  if (!dados) return null
  const disc = dados.testes.find((t) => t.tipo === 'disc')
  const sit = dados.testes.find((t) => t.tipo === 'situacional')

  return (
    <div className="rh-card">
      <h3>🧭 Testes do candidato</h3>
      <EditarTestes id={id} disc={disc} sit={sit} recarregar={recarregar} />
      {dados.testes.length > 0 && (
      <p className="explica">Resultado restrito ao RH — use como <strong>apoio</strong> à decisão,
        nunca como critério único (inventário comportamental de gestão; não substitui avaliação
        psicológica).</p>
      )}

      {disc && (
        <div className="disc-bloco">
          <strong>Inventário DISC</strong>{' '}
          <span className="explica" style={{ margin: 0 }}>
            — {STATUS_TESTE[disc.status]}{disc.respondidas ? ` · ${disc.respondidas}/24 respondidas` : ''}</span>
          {disc.status !== 'pendente' && (
            <BotaoResetarTeste id={id} tipo="disc" nomeTeste="Inventário DISC"
                               recarregar={recarregar} />
          )}
          {disc.resultado && disc.resultado.percentuais && (
            <>
              <div className="disc-grafico">
                {['D', 'I', 'S', 'C'].map((d) => (
                  <div key={d} className="disc-coluna">
                    <div className="disc-barra-area">
                      <div className="disc-barra" style={{
                        height: `${Math.max(4, disc.resultado.percentuais[d])}%`,
                        background: CORES_DISC[d] }} />
                    </div>
                    <strong style={{ color: CORES_DISC[d] }}>{d}</strong>
                    <small>{disc.resultado.percentuais[d]}%</small>
                  </div>
                ))}
              </div>
              {disc.perfis && (
                <div className="disc-perfil">
                  <p><strong>Perfil predominante:{' '}
                    <span style={{ color: CORES_DISC[disc.resultado.principal] }}>
                      {disc.perfis[disc.resultado.principal].nome}</span>
                    {disc.resultado.secundaria && <> com traços de{' '}
                      <span style={{ color: CORES_DISC[disc.resultado.secundaria] }}>
                        {disc.perfis[disc.resultado.secundaria].nome}</span></>}
                  </strong></p>
                  <p>{disc.perfis[disc.resultado.principal].resumo}</p>
                  <p><strong>Pontos fortes:</strong> {disc.perfis[disc.resultado.principal].fortes}</p>
                  <p><strong>Pontos de atenção:</strong> {disc.perfis[disc.resultado.principal].atencao}</p>
                  <p><strong>Ambiente em que rende mais:</strong> {disc.perfis[disc.resultado.principal].ambiente}</p>
                  <details>
                    <summary className="btn-link">Ver os 4 perfis (D · I · S · C)</summary>
                    {['D', 'I', 'S', 'C'].map((d) => (
                      <p key={d} style={{ marginTop: '.5rem' }}>
                        <strong style={{ color: CORES_DISC[d] }}>{d} — {disc.perfis[d].nome}:</strong>{' '}
                        {disc.perfis[d].resumo}</p>
                    ))}
                  </details>
                </div>
              )}
            </>
          )}
        </div>
      )}

      {sit && (
        <div className="disc-bloco">
          <strong>Teste Situacional</strong>{' '}
          <span className="explica" style={{ margin: 0 }}>— {STATUS_TESTE[sit.status]}</span>
          {sit.status !== 'pendente' && (
            <BotaoResetarTeste id={id} tipo="situacional" nomeTeste="Teste Situacional"
                               recarregar={recarregar} />
          )}
          {sit.resultado && sit.resultado.percentual != null && (
            <p style={{ margin: '.4rem 0 0' }}>
              Conduta profissional: <strong>{sit.resultado.percentual}%</strong>{' '}
              (<strong>{sit.resultado.faixa}</strong>) — {sit.resultado.respondidas}/10 respondidas,
              {' '}{sit.resultado.pontos}/{sit.resultado.maximo} pontos.</p>
          )}
        </div>
      )}

      {dados.testes.filter((t) => t.comportamento).map((t) => (
        <ComportamentoTeste key={t.tipo} teste={t} />
      ))}
    </div>
  )
}

// Zera o teste para o candidato refazer pelo mesmo link (o resultado anterior
// fica preservado na auditoria).
function BotaoResetarTeste({ id, tipo, nomeTeste, recarregar }) {
  const [ocupado, setOcupado] = useState(false)
  return (
    <button className="btn-link" disabled={ocupado} style={{ marginLeft: '.5rem' }}
            title="Zera respostas e resultado para a pessoa refazer (o anterior fica na auditoria)"
            onClick={async () => {
              if (!window.confirm(`Resetar o ${nomeTeste}?\n\nAs respostas e o resultado atuais serão zerados (ficam na auditoria) e o candidato poderá refazer pelo link dele.`)) return
              setOcupado(true)
              try { await api.resetarTeste(id, tipo); await recarregar() }
              finally { setOcupado(false) }
            }}>{ocupado ? 'resetando…' : '🔁 resetar'}</button>
  )
}

// Liga/desliga os testes DEPOIS do convite (antes só dava na criação) e copia
// o link para o candidato responder. Desmarcar só remove teste ainda pendente
// — teste iniciado/concluído fica (o resultado não se apaga por engano).
function EditarTestes({ id, disc, sit, recarregar }) {
  const [querDisc, setQuerDisc] = useState(!!disc)
  const [querSit, setQuerSit] = useState(!!sit)
  const [salvando, setSalvando] = useState(false)
  const [msg, setMsg] = useState(null)
  useEffect(() => { setQuerDisc(!!disc); setQuerSit(!!sit) }, [!!disc, !!sit])
  const mudou = querDisc !== !!disc || querSit !== !!sit

  return (
    <div className="rh-lote" style={{ marginBottom: '.6rem' }}>
      <label style={{ display: 'flex', alignItems: 'center', gap: '.45rem' }}>
        <input type="checkbox" style={{ width: 'auto', minHeight: 0 }} checked={querDisc}
               onChange={(e) => setQuerDisc(e.target.checked)} />
        <span>🧭 Inventário DISC</span>
      </label>
      <label style={{ display: 'flex', alignItems: 'center', gap: '.45rem' }}>
        <input type="checkbox" style={{ width: 'auto', minHeight: 0 }} checked={querSit}
               onChange={(e) => setQuerSit(e.target.checked)} />
        <span>🧩 Teste Situacional</span>
      </label>
      {mudou && (
        <button className="btn-principal btn-mini" disabled={salvando} onClick={async () => {
          setSalvando(true); setMsg(null)
          try {
            const r = await api.definirTestes(id, querDisc, querSit)
            const partes = []
            if (r.criados.length) partes.push(`${r.criados.length} teste(s) adicionado(s)`)
            if (r.removidos.length) partes.push(`${r.removidos.length} removido(s) (foram para a lixeira)`)
            if (r.mantidos.length) partes.push('teste já iniciado/concluído não foi removido')
            setMsg({ tipo: 'ok', texto: `${partes.join(' · ') || 'Nada a mudar'}. `
              + (r.criados.length ? 'Use "📋 Copiar link dos testes" e envie ao candidato.' : '') })
            await recarregar()
          } catch (e) {
            setMsg({ tipo: 'erro', texto: `Não foi possível salvar (${e.detail || e.message}).` })
          } finally { setSalvando(false) }
        }}>{salvando ? 'Salvando…' : 'Salvar testes'}</button>
      )}
      {(disc || sit) && (
        <button className="btn-secundario btn-mini"
                title="Copia um link novo do candidato — ao abrir, ele responde primeiro aos testes pendentes"
                onClick={async (e) => {
                  const btn = e.currentTarget
                  const r = await api.gerarLink(id)
                  await navigator.clipboard.writeText(r.link_magico)
                  const original = btn.textContent
                  btn.textContent = '✓ Copiado!'
                  setTimeout(() => { btn.textContent = original }, 2000)
                }}>📋 Copiar link dos testes</button>
      )}
      {msg && <div className={msg.tipo === 'erro' ? 'alerta' : 'sucesso'}
                   style={{ width: '100%' }}>{msg.texto}</div>}
    </div>
  )
}

const NOMES_EVENTO = {
  teste_aberto: 'abriu o teste', oculto: 'saiu da tela (aba oculta/tela desligada)',
  visivel: 'voltou à tela', desfocou: 'trocou de janela/aplicativo', focou: 'voltou à janela',
  print: 'apertou PrintScreen', copiou: 'copiou texto', recortou: 'recortou texto',
  colou: 'colou texto', menu_contexto: 'abriu o menu do botão direito',
  offline: 'perdeu a conexão', online: 'conexão voltou', saida_pagina: 'fechou/saiu da página',
}
const mmssEvento = (s) => `${String(Math.floor(s / 60)).padStart(2, '0')}:${String(Math.round(s % 60)).padStart(2, '0')}`

// Telemetria de comportamento durante o teste — para o RH ler ou copiar e
// mandar a uma IA em busca de oportunidades de melhoria do sistema.
// (exportado: o dash de Testes reusa este relatório)
export function ComportamentoTeste({ teste }) {
  const [copiado, setCopiado] = useState(false)
  const c = teste.comportamento
  const nomeTeste = teste.tipo === 'disc' ? 'Inventário DISC' : 'Teste Situacional'

  const relatorio = () => {
    const linhas = (teste.eventos || []).map((e) =>
      `${mmssEvento(e.t)}  ${NOMES_EVENTO[e.e] || e.e}${e.d ? ` (${e.d})` : ''}`)
    return [
      `RELATÓRIO DE COMPORTAMENTO — ${nomeTeste}`,
      `Início: ${fmtData(teste.iniciado_em)} · Conclusão: ${fmtData(teste.concluido_em)}`,
      `Saídas da tela: ${c.saidas_da_tela} · Tempo fora da tela: ${c.segundos_fora_da_tela}s`,
      `PrintScreen: ${c.tentativas_print} · Copiar/colar: ${c.copiar_colar} · Quedas de conexão: ${c.quedas_de_conexao}`,
      '', 'LINHA DO TEMPO (mm:ss desde o início):', ...linhas,
    ].join('\n')
  }

  return (
    <div className="disc-bloco">
      <strong>🖥️ Comportamento — {nomeTeste}</strong>
      <p style={{ margin: '.4rem 0' }}>
        Saídas da tela: <strong>{c.saidas_da_tela}</strong> ·
        tempo fora: <strong>{Math.round(c.segundos_fora_da_tela)}s</strong> ·
        PrintScreen: <strong>{c.tentativas_print}</strong> ·
        copiar/colar: <strong>{c.copiar_colar}</strong> ·
        quedas de conexão: <strong>{c.quedas_de_conexao}</strong></p>
      <details>
        <summary className="btn-link">
          Linha do tempo ({c.total_eventos} eventos)</summary>
        <ul style={{ margin: '.4rem 0 0', paddingLeft: '1.2rem', fontSize: '.85rem' }}>
          {(teste.eventos || []).map((e, i) => (
            <li key={i}><code>{mmssEvento(e.t)}</code> {NOMES_EVENTO[e.e] || e.e}
              {e.d ? ` (${e.d})` : ''}</li>
          ))}
        </ul>
      </details>
      <button className="btn-secundario btn-mini" style={{ marginTop: '.4rem' }}
              onClick={() => { navigator.clipboard?.writeText(relatorio()); setCopiado(true)
                setTimeout(() => setCopiado(false), 2000) }}>
        {copiado ? '✓ Copiado' : '📋 Copiar relatório (para análise ou IA)'}</button>
    </div>
  )
}
