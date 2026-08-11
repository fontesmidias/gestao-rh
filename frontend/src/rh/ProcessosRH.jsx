import { useEffect, useState } from 'react'
import { rh as api } from '../api.js'
import Aviso from '../Aviso.jsx'
import DashPlanilha from './DashPlanilha.jsx'
import SelectBusca from '../SelectBusca.jsx'

// Carteira de Processos do RH (v2.91).
//
// A tela responde a UMA pergunta, e o resto é apoio: **quem responde por isto
// agora?** Por isso a coluna "Responde hoje" fica ao lado do titular e mostra a
// diferença quando alguém assumiu — é o caso "a titular saiu do RH", que é o
// motivo de o módulo existir.
//
// Usa o `DashPlanilha` como toda lista do painel (regra da casa): ordenar,
// filtrar por fase/ritmo/pessoa e ver o detalhe na própria linha vêm de graça.

const GRAVIDADE = { alta: '🔴', media: '🟡', baixa: '⚪' }

export default function ProcessosRH() {
  const [dados, setDados] = useState(null)
  const [funcoes, setFuncoes] = useState([])
  const [cenario, setCenario] = useState('C1')
  const [erro, setErro] = useState(null)
  const [msg, setMsg] = useState(null)
  const [importando, setImportando] = useState(false)
  const [previa, setPrevia] = useState(null)     // {resumo, arquivo}
  // A escala de canais (v2.91.1): é ela quem responde pelos processos 9.1/9.2,
  // e sem mostrá-la a tela dizia "Escala do dia" sem saber dizer quem.
  const [escala, setEscala] = useState(null)

  const carregar = (c = cenario) => api.processos(c).then(setDados)

  useEffect(() => {
    // Erro SEPARADO do carregando (v2.46): senão falha de rede vira
    // "Carregando…" para sempre, sem como tentar de novo.
    api.processos(cenario).then(setDados).catch(() => setErro(true))
    api.funcoesRH().then(setFuncoes).catch(() => setFuncoes([]))
    api.escalaCanais(cenario).then(setEscala).catch(() => setEscala(null))
  }, [cenario])

  if (erro) {
    return (
      <main className="rh-painel">
        <div className="rh-card">
          <p className="alerta">Não foi possível carregar a carteira.</p>
          <button className="btn-secundario" onClick={() => { setErro(null); carregar() }}>
            Tentar de novo</button>
        </div>
      </main>
    )
  }
  if (!dados) return <main className="rh-painel"><p>Carregando a carteira…</p></main>

  const escolherArquivo = async (arquivo) => {
    if (!arquivo) return
    setImportando(true); setMsg(null)
    try {
      // PRÉVIA antes de gravar — a carteira é digitada à mão, e merge cego
      // criaria atribuição errada que só aparece no dia da ausência.
      const r = await api.processosImportarPreview(arquivo)
      setPrevia({ resumo: r, arquivo })
    } catch (e) {
      setMsg({ tipo: 'erro', texto: e.detail?.erro === 'sem_abas_matriz'
        ? 'A planilha não tem as abas "Matriz C1"/"Matriz C2".'
        : `Não foi possível ler a planilha (${e.detail || e.message}).` })
    } finally { setImportando(false) }
  }

  const confirmarImportacao = async () => {
    setImportando(true)
    try {
      const r = await api.processosImportar(previa.arquivo)
      setPrevia(null)
      await carregar()
      setEscala(await api.escalaCanais(cenario).catch(() => null))
      setMsg({ tipo: 'ok', texto: `${r.criados} processo(s) criado(s), `
        + `${r.atualizados} atualizado(s), ${r.vinculos} vínculo(s) de cadeia`
        + (r.escala ? ` e ${r.escala} linha(s) de escala.` : '.') })
    } catch (e) {
      setMsg({ tipo: 'erro', texto: `Falha ao importar (${e.detail || e.message}).` })
    } finally { setImportando(false) }
  }

  const trocarPessoa = async (f, pessoa) => {
    try {
      await api.editarFuncaoRH(f.id, { ...f, pessoa_nome: pessoa })
      setFuncoes(await api.funcoesRH())
      await carregar()
      setMsg({ tipo: 'ok', texto: pessoa
        ? `${pessoa} passa a ocupar “${f.nome}”.`
        : `“${f.nome}” ficou vaga — os processos dela passaram para o próximo da cadeia.` })
    } catch (e) {
      setMsg({ tipo: 'erro', texto: `Não foi possível salvar (${e.detail || e.message}).` })
    }
  }

  const colunas = [
    { chave: 'codigo', rotulo: 'Código', valor: (p) => p.codigo, ordenavel: true, nowrap: true },
    { chave: 'fase', rotulo: 'Fase', valor: (p) => p.fase, filtro: 'lista', quebra: true },
    { chave: 'nome', rotulo: 'Processo', valor: (p) => p.nome, filtro: 'texto', quebra: true },
    { chave: 'ritmo', rotulo: 'Ritmo', valor: (p) => p.ritmo || '—', filtro: 'lista',
      nowrap: true,
      render: (p) => p.ritmo
        ? <span className="chip" title={p.ritmo_ajuda}
                style={p.critico ? { '--chip-cor': 'var(--ambar)' } : undefined}>
            {p.ritmo}</span>
        : '—' },
    { chave: 'titular', rotulo: 'Titular', valor: (p) => p.titular_pessoa || p.titular || '—',
      filtro: 'lista', quebra: true },
    { chave: 'responsavel', rotulo: 'Responde hoje',
      valor: (p) => p.responsavel || (p.rodizio ? 'Escala do dia' : '—'),
      filtro: 'lista', quebra: true,
      // A diferença entre titular e quem responde hoje é a informação que o
      // módulo existe para dar. Sem destacá-la, a tela é só a planilha na web.
      render: (p) => p.sem_dono
        ? <span className="chip" style={{ '--chip-cor': 'var(--erro)' }}
                title="Ninguém da cadeia está ocupado">sem dono</span>
        : p.rodizio ? <span title="Gira entre a equipe por dia útil">Escala do dia</span>
        : <>{p.responsavel || '—'}{p.assumido && (
            <> <span className="chip" style={{ '--chip-cor': 'var(--ambar)' }}
                     title={`Assumiu no lugar de ${p.titular_pessoa || p.titular}`}>
              assumiu</span></>)}</> },
    { chave: 'cadeia', rotulo: 'Cadeia', valor: (p) => p.cadeia.length, nowrap: true,
      render: (p) => <span title={p.cadeia.map((e) => `${e.posicao}. ${e.funcao}`).join(' → ')}>
        {p.cadeia.length}{p.cadeia_curta && ' ⚠️'}</span> },
  ]

  const semDono = dados.processos.filter((p) => p.sem_dono).length
  const curtas = dados.processos.filter((p) => p.cadeia_curta && !p.rodizio).length

  return (
    <main className="rh-painel">
      {msg && <Aviso tipo={msg.tipo} texto={msg.texto} aoFechar={() => setMsg(null)} />}
      <header className="rh-topo">
        <h1>🗂️ Carteira de Processos</h1>
        <div className="rh-lote" style={{ margin: 0 }}>
          <SelectBusca valor={cenario} aoEscolher={(v) => v && setCenario(v)}>
            <option value="C1">Cenário 1 — estrutura vigente</option>
            <option value="C2">Cenário 2 — com o Analista Jr</option>
          </SelectBusca>
          <label className="btn-secundario" style={{ cursor: 'pointer' }}>
            {importando ? 'Lendo…' : '📥 Importar planilha'}
            <input type="file" accept=".xlsx" style={{ display: 'none' }}
                   onChange={(e) => escolherArquivo(e.target.files?.[0])} />
          </label>
        </div>
      </header>

      {previa && (
        <div className="rh-card">
          <h3>Confira antes de importar</h3>
          <p className="explica">
            {previa.resumo.processos_novos.length} processo(s) novo(s) ·{' '}
            {previa.resumo.processos_alterados.length} atualizado(s) ·{' '}
            cenários: {previa.resumo.cenarios.join(', ')}
          </p>
          {previa.resumo.funcoes_novas.length > 0 && (
            <p className="explica">
              Vão ser criadas as funções: {previa.resumo.funcoes_novas.join(', ')}.
            </p>
          )}
          {previa.resumo.ignoradas.length > 0 && (
            // Linha não lida NUNCA some calada: importação que ignora oito
            // linhas e diz "pronto" é pior que uma que falha.
            <div className="alerta">
              <strong>{previa.resumo.ignoradas.length} linha(s) não serão importadas:</strong>
              <ul>{previa.resumo.ignoradas.slice(0, 8).map((i, n) => (
                <li key={n}>{i.aba} linha {i.linha}: {i.motivo}</li>))}</ul>
            </div>
          )}
          <div className="navegacao">
            <button className="btn-principal" disabled={importando}
                    onClick={confirmarImportacao}>
              {importando ? 'Importando…' : 'Importar'}</button>
            <button className="btn-secundario" onClick={() => setPrevia(null)}>Cancelar</button>
          </div>
        </div>
      )}

      {dados.alertas.length > 0 && (
        <div className="rh-card">
          <h3>O que precisa de atenção</h3>
          <ul className="fichas-status">
            {dados.alertas.map((a, n) => (
              <li key={n}>
                {GRAVIDADE[a.gravidade] || '⚪'}{' '}
                {a.codigo && <strong>{a.codigo}</strong>} {a.processo} — {a.texto}
              </li>
            ))}
          </ul>
        </div>
      )}

      <DashPlanilha
        id="processos" colunas={colunas} dados={dados.processos}
        cards={[
          { rotulo: 'Processos', valor: dados.processos.length },
          { rotulo: 'Sem dono', valor: semDono, cor: semDono ? 'var(--erro)' : undefined },
          { rotulo: 'Cadeia curta', valor: curtas },
          { rotulo: 'Pessoas', valor: dados.carga.filter((c) => !c.vaga_aberta).length },
        ]}
      />

      {escala?.semanas?.length > 0 && (
        <div className="rh-card">
          <h3>Escala rotativa de canais</h3>
          <p className="explica">
            Avança um posto por dia útil e recomeça. É esta escala que responde
            pelos processos <strong>9.1</strong> (Conferência do Módulo de
            Demandas) e <strong>9.2</strong> (Gestão de Canais) — por isso eles
            aparecem com “Escala do dia” no lugar de um titular fixo.
          </p>
          {escala.semanas.map((sem) => (
            <details key={sem.semana} open={sem.semana === 1}>
              <summary>Semana {sem.semana}</summary>
              <div className="dash-scroll">
                <table className="rh-tabela">
                  <thead><tr>
                    <th>Dia</th>
                    {escala.postos.map((p) => <th key={p}>{p}</th>)}
                  </tr></thead>
                  <tbody>
                    {sem.dias.map((d) => (
                      <tr key={d.dia}>
                        <td><strong>{d.dia}</strong></td>
                        {escala.postos.map((p) => (
                          <td key={p} className="dash-quebra">{d.postos[p] || '—'}</td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </details>
          ))}
        </div>
      )}

      <div className="rh-card">
        <h3>Quem é quem, e quanto cada um carrega</h3>
        <p className="explica">
          A titularidade acompanha a <strong>função</strong>, não a pessoa: ao
          trocar quem ocupa uma função, os processos dela seguem com dono.
          Deixar em branco registra a vaga aberta — e a cadeia passa a responder
          pelo próximo, na hora.
        </p>
        <div className="dash-scroll">
          <table className="rh-tabela">
            <thead><tr>
              <th>Função</th><th>Quem ocupa</th><th>Titular de</th><th>Apoia em</th>
            </tr></thead>
            <tbody>
              {dados.carga.map((c) => {
                const f = funcoes.find((x) => x.id === c.id) || { id: c.id, nome: c.funcao }
                return (
                  <tr key={c.id} style={c.vaga_aberta ? { opacity: .6 } : {}}>
                    <td className="dash-quebra">{c.funcao}</td>
                    <td>
                      <input defaultValue={c.pessoa || ''} placeholder="— vaga aberta —"
                             onBlur={(e) => {
                               const novo = e.target.value.trim()
                               if (novo !== (c.pessoa || '')) trocarPessoa(f, novo)
                             }} />
                    </td>
                    <td>{c.dono}</td>
                    <td>{c.apoio}</td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      </div>
    </main>
  )
}
