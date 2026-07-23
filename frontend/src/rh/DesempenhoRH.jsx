import { useEffect, useState } from 'react'
import { rh as api } from '../api.js'
import DashPlanilha from './DashPlanilha.jsx'
import SelectBusca from '../SelectBusca.jsx'

// Gestão de Desempenho — Fatos Observados (Onda C, 1ª fatia).
//
// Por que os fatos vêm ANTES do formulário: o líder, na hora de avaliar,
// esquece o que a pessoa fez — e escreve rótulo ("tem má vontade") onde a
// cartilha manda escrever fato ("faltou 3 vezes sem aviso em maio"). Com o
// banco de fatos, ele REVISA o que já registrou em vez de lembrar do zero.
//
// O colaborador VÊ o que foi registrado sobre ele (no portal /meu), mas não
// quem registrou.
export default function DesempenhoRH({ aoVoltar }) {
  const [dados, setDados] = useState(null)
  const [colaboradores, setColaboradores] = useState([])
  const [msg, setMsg] = useState(null)
  const [novo, setNovo] = useState(false)
  const [editando, setEditando] = useState(null)

  const carregar = () => Promise.all([api.fatos(), api.desempenhoColaboradores()])
    .then(([f, c]) => { setDados(f); setColaboradores(c.colaboradores) })
    .catch((e) => setMsg({ tipo: 'erro', texto: e.detail || e.message }))
  useEffect(() => { carregar() }, [])

  if (!dados) return <p className="explica">Carregando…</p>

  const colunas = [
    { chave: 'ocorrido_em', rotulo: 'Quando', ordenavel: true,
      valor: (l) => l.ocorrido_em || '', render: (l) => fmt(l.ocorrido_em),
      sempreVisivel: true },
    { chave: 'colaborador', rotulo: 'Colaborador', ordenavel: true, filtro: 'texto',
      sempreVisivel: true },
    { chave: 'tipo', rotulo: 'Tipo', filtro: 'select',
      opcoes: ['Positivo', 'Negativo', 'Neutro'],
      valor: (l) => ROTULO_TIPO[l.tipo],
      render: (l) => <ChipTipo tipo={l.tipo} /> },
    { chave: 'descricao', rotulo: 'O que aconteceu', filtro: 'texto', quebra: true },
    { chave: 'impacto', rotulo: 'Impacto', quebra: true, oculta: true },
    { chave: 'autor', rotulo: 'Registrado por', ordenavel: true, filtro: 'texto',
      quebra: true },
    { chave: 'tem_anexo', rotulo: 'Anexo',
      valor: (l) => (l.tem_anexo ? 'Sim' : 'Não'),
      render: (l) => (l.tem_anexo ? '📎' : '—') },
  ]

  const cards = [
    { rotulo: 'Positivos', valor: dados.metricas.positivo || 0, cor: '#0a8f46',
      filtro: { chave: 'tipo', valor: 'Positivo' } },
    { rotulo: 'Negativos', valor: dados.metricas.negativo || 0, cor: '#e5484d',
      filtro: { chave: 'tipo', valor: 'Negativo' } },
    { rotulo: 'Neutros', valor: dados.metricas.neutro || 0, cor: '#889',
      filtro: { chave: 'tipo', valor: 'Neutro' } },
  ]

  return (
    <section>
      <div className="rh-topo">
        <h1>📌 Fatos Observados</h1>
        <button className="btn-secundario btn-mini" onClick={aoVoltar}>← voltar</button>
      </div>
      <p className="explica">Registre <strong>na hora</strong> o que a pessoa fez — bom
        ou ruim — com o fato e o impacto. Na avaliação, isso aparece do lado do
        formulário, para você não depender da memória.
        {' '}<strong>O colaborador vê o que foi registrado sobre ele</strong> (sem o
        nome de quem registrou).</p>
      <Msg msg={msg} />

      {novo && (
        <FormFato colaboradores={colaboradores}
                  aoFechar={() => { setNovo(false); carregar() }}
                  aoErro={(t) => setMsg({ tipo: 'erro', texto: t })} />
      )}
      {!novo && (
        <button className="btn-principal btn-mini" style={{ marginBottom: '.8rem' }}
                onClick={() => setNovo(true)}>＋ Registrar fato</button>
      )}

      <DashPlanilha
        id="desempenho-fatos" colunas={colunas} dados={dados.fatos} cards={cards}
        vazio="Nenhum fato registrado ainda."
        linhaExpandida={(l) => (editando === l.id ? (
          <FormFato key={l.id} fato={l} colaboradores={colaboradores}
                    aoFechar={() => { setEditando(null); carregar() }}
                    aoErro={(t) => setMsg({ tipo: 'erro', texto: t })} />
        ) : null)}
        acoesLinha={(l) => (
          <>
            {l.tem_anexo && (
              <button className="btn-secundario btn-mini" onClick={async () => {
                try {
                  const blob = await api.fatoAnexo(l.id)
                  const url = URL.createObjectURL(blob)
                  window.open(url, '_blank')
                  setTimeout(() => URL.revokeObjectURL(url), 30000)
                } catch (e) { setMsg({ tipo: 'erro', texto: e.detail || e.message }) }
              }}>Ver anexo</button>
            )}
            <button className={`btn-${editando === l.id ? 'principal' : 'secundario'} btn-mini`}
                    onClick={() => setEditando(editando === l.id ? null : l.id)}>
              {editando === l.id ? 'Fechar' : 'Abrir'}</button>
          </>
        )} />
    </section>
  )
}

const ROTULO_TIPO = { positivo: 'Positivo', negativo: 'Negativo', neutro: 'Neutro' }

function ChipTipo({ tipo }) {
  const cores = { positivo: '#0a8f46', negativo: '#e5484d', neutro: '#889' }
  return <span className="chip" style={{ '--chip-cor': cores[tipo] }}>
    {ROTULO_TIPO[tipo] || tipo}</span>
}

function FormFato({ fato, colaboradores, aoFechar, aoErro }) {
  const editando = !!fato
  const [f, setF] = useState({
    candidato_id: fato ? fato.candidato_id : '',
    tipo: fato ? fato.tipo : 'positivo',
    descricao: fato ? fato.descricao : '',
    impacto: fato ? (fato.impacto || '') : '',
    ocorrido_em: fato ? fato.ocorrido_em : hoje(),
    visivel_em: fato ? (fato.visivel_em || '') : '',
  })
  const [arquivo, setArquivo] = useState(null)
  const [salvando, setSalvando] = useState(false)

  const salvar = async () => {
    if (!f.candidato_id) { aoErro('Escolha o colaborador.'); return }
    if (!f.descricao.trim()) { aoErro('Descreva o que aconteceu.'); return }
    setSalvando(true)
    try {
      const r = editando ? await api.editarFato(fato.id, f) : await api.criarFato(f)
      if (arquivo) await api.subirAnexoFato(r.id, arquivo)
      aoFechar()
    } catch (e) {
      aoErro(e.detail === 'data_futura' ? 'A data não pode ser no futuro.'
        : e.detail === 'somente_o_autor' ? 'Só quem registrou pode alterar este fato.'
        : e.detail === 'fato_ja_usado' ? 'Este fato já foi usado numa avaliação e não pode mudar.'
        : e.detail === 'arquivo_grande' ? 'Anexo muito grande (máximo 25 MB).'
        : e.detail === 'formato_nao_aceito' ? 'Formato não aceito (PDF, foto, vídeo ou Word).'
        : (e.detail || e.message))
    } finally { setSalvando(false) }
  }

  return (
    <div className="rh-conferencia">
      <div className="rh-conferencia-topo">
        <div>
          <h3>{editando ? 'Editar fato' : 'Registrar fato observado'}</h3>
          <span className="explica">Descreva o <strong>fato</strong>, não o rótulo:
            "faltou 3 vezes sem aviso em maio", não "tem má vontade".</span>
        </div>
        <button className="btn-secundario btn-mini" onClick={aoFechar}>✕ fechar</button>
      </div>

      {!editando && (
        <label className="campo"><span className="rotulo">Colaborador</span>
          <SelectBusca valor={f.candidato_id} vazioRotulo="— escolha —"
                       placeholder="Buscar colaborador…"
                       opcoes={colaboradores.map((c) => ({
                         valor: c.id, rotulo: c.nome,
                         extra: [c.cargo, c.posto].filter(Boolean).join(' · ') }))}
                       aoEscolher={(v) => setF({ ...f, candidato_id: v })} /></label>
      )}

      <div className="campo">
        <span className="rotulo">Tipo</span>
        <div className="chips-escolha">
          {['positivo', 'negativo', 'neutro'].map((t) => (
            <button type="button" key={t}
                    className={`chip-escolha ${f.tipo === t ? 'on' : ''}`}
                    onClick={() => setF({ ...f, tipo: t })}>{ROTULO_TIPO[t]}</button>
          ))}
        </div>
      </div>

      <label className="campo"><span className="rotulo">O que aconteceu</span>
        <textarea rows={3} value={f.descricao}
                  placeholder="Ex.: cobriu o posto no feriado sem ser escalado."
                  onChange={(e) => setF({ ...f, descricao: e.target.value })} /></label>
      <label className="campo"><span className="rotulo">Qual foi o impacto
        <span className="dica-inline"> — no cliente, na equipe, no serviço</span></span>
        <textarea rows={2} value={f.impacto}
                  placeholder="Ex.: o cliente não ficou descoberto."
                  onChange={(e) => setF({ ...f, impacto: e.target.value })} /></label>

      <div className="linha2">
        <label className="campo"><span className="rotulo">Quando aconteceu</span>
          <input type="date" value={f.ocorrido_em} max={hoje()}
                 onChange={(e) => setF({ ...f, ocorrido_em: e.target.value })} /></label>
        <label className="campo"><span className="rotulo">Mostrar ao colaborador a partir de
          <span className="dica-inline"> — vazio = já</span></span>
          <input type="date" value={f.visivel_em}
                 onChange={(e) => setF({ ...f, visivel_em: e.target.value })} /></label>
      </div>

      <label className="campo"><span className="rotulo">Anexo
        <span className="dica-inline"> — foto, vídeo curto ou documento (até 25 MB)</span></span>
        <input type="file" accept=".pdf,.jpg,.jpeg,.png,.heic,.webp,.mp4,.mov,.3gp,.doc,.docx"
               onChange={(e) => setArquivo(e.target.files[0])} /></label>

      <div className="rh-conferencia-acoes">
        <button className="btn-principal btn-mini" disabled={salvando}
                onClick={salvar}>{salvando ? 'Salvando…' : 'Salvar fato'}</button>
        <button className="btn-link" onClick={aoFechar}>cancelar</button>
      </div>
    </div>
  )
}

function hoje() {
  const d = new Date()
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}

function fmt(iso) {
  if (!iso) return '—'
  const [a, m, d] = iso.split('-')
  return `${d}/${m}/${a}`
}

function Msg({ msg }) {
  if (!msg) return null
  const classe = msg.tipo === 'ok' ? 'sucesso' : msg.tipo === 'aviso' ? 'aviso-inline' : 'alerta'
  return <div className={classe}>{msg.texto}</div>
}
