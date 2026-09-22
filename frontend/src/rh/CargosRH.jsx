import { useEffect, useRef, useState } from 'react'
import { rh as api } from '../api.js'
import Aviso from '../Aviso.jsx'
import { comAmpulheta } from '../Carregando.jsx'

// Página de Cargos (feedback do Bruno, 2026-09-22): "não entendi por que ficou
// separado... tem um card 'Cargos x Id do TIRVU' em Empresas e jornadas, que
// seria o próximo passo após importar, que precisa estar próximo".
//
// O que estava espalhado em TRÊS lugares, sem nada dizendo qual usar:
//   1. Importações → 🧾 Cargos (.txt)            — subir arquivo  (v2.38)
//   2. Empresas e jornadas → 📋 Padronizar…      — colar texto    (v1.96)
//   3. Empresas e jornadas → 💼 Cargos × ID      — de-para manual
//
// (1) e (2) eram o MESMO passo por duas portas — e gravavam pela MESMA rota
// (`/rh/tirvu-txt/confirmar-cargos`); é o "dois controles para a mesma escolha"
// da v2.75. (3) é o passo SEGUINTE, e morava noutra aba: quem acabava de
// importar não tinha como saber que faltava conferir os IDs.
//
// Aqui os três viram UMA sequência na ordem em que o trabalho acontece:
// orientação → importar em lote → conferir/cadastrar um a um.
//
// ⚠️ Cargo continua STRING LIVRE no `Candidato` (CLAUDE.md): `cargo_alvo`, o
// filtro do Arquivo e as provas por cargo casam por TEXTO. Esta página NÃO é o
// CRUD de uma tabela de cargos — é o CRUD do DE-PARA lateral (`CargoTirvu`),
// que só o export do Tirvu consulta. Por isso a lista nasce dos cargos já
// USADOS na base, e não de um cadastro próprio: cargo que ninguém ocupa não
// precisa de ID.

// Passo a passo real do Tirvu, ditado pelo Bruno (o mesmo que ele mandou por
// WhatsApp para uma colaboradora do RH). Fica na tela porque a instrução vivia
// só no WhatsApp de quem já sabia — e o Tirvu não tem botão de exportar cargos,
// então ninguém adivinha o caminho.
function ComoExtrair() {
  return (
    <details className="rh-card">
      <summary><strong>📖 Como trazer os cargos do Tirvu (passo a passo)</strong></summary>
      <p className="explica">O Tirvu não tem botão de exportar cargos — o caminho é copiar a
        lista da tela dele e salvar num arquivo de texto. Leva um minuto:</p>
      <ol className="explica">
        <li><strong>No Tirvu</strong>, abra <strong>Colaboradores → Dados Cadastrais</strong>.</li>
        <li>No canto <strong>superior direito</strong>, vá em <strong>Cadastros → Cargos</strong>.</li>
        <li>Busque o cargo pelo nome (ou deixe a lista inteira, se for trazer todos).</li>
        <li><strong>Selecione</strong> o cargo — ou os cargos — e <strong>copie</strong> (Ctrl+C).</li>
        <li>Cole num <strong>Bloco de Notas</strong> e <strong>salve</strong> o arquivo.</li>
        <li>Volte aqui e suba o arquivo no cartão abaixo.</li>
      </ol>
      <p className="explica">O sistema lê o <strong>ID</strong>, o <strong>cargo</strong> e o{' '}
        <strong>CBO</strong> de cada linha, mostra o que vai gravar e só grava depois que você
        confere. Cargo com dois IDs ativos (é o CBO que os diferencia) nunca é resolvido
        sozinho — fica separado para você decidir.</p>
      <p className="explica"><strong>Precisa de um cargo só?</strong> Não precisa fazer nada
        disso: cadastre direto no cartão &ldquo;Cargos da base&rdquo;, mais abaixo.</p>
    </details>
  )
}

// Importação em lote do .txt. É o CardTirvuTxt de Importacoes.jsx, trazido para
// cá com as orientações ao lado — lá ele era um card solto no meio de outros
// seis, e o passo seguinte (conferir os IDs) ficava noutra aba.
function ImportarLote({ aoGravar }) {
  const inputRef = useRef(null)
  const [previa, setPrevia] = useState(null)
  const [msg, setMsg] = useState(null)
  const [feito, setFeito] = useState(null)

  const enviar = async (arquivo) => {
    if (!arquivo) return
    setMsg(null); setPrevia(null); setFeito(null)
    try {
      setPrevia(await comAmpulheta('Lendo o arquivo…', () => api.previewCargosArquivo(arquivo)))
    } catch (e) {
      // Contagem do cabeçalho não bater = cópia PARCIAL da tela. Importar
      // metade calado seria pior que recusar (v1.96).
      setMsg(e.detail?.includes?.('contagem')
        ? `O arquivo parece incompleto (${e.detail}). Copie a lista inteira da tela do Tirvu.`
        : `Não foi possível ler o arquivo (${e.detail || e.message}).`)
    } finally { if (inputRef.current) inputRef.current.value = '' }
  }

  const seguros = (previa?.propostas || []).filter((p) => p.aplicar_sugerido)
  const ambiguos = (previa?.propostas || []).filter((p) => !p.aplicar_sugerido)

  const aplicar = async () => {
    setMsg(null)
    try {
      const r = await comAmpulheta('Gravando…', () => api.confirmarCargosTirvu({
        itens: seguros.map((p) => ({ tirvu_id: p.tirvu_id, cargo: p.cargo,
                                     cbo: p.cbo, aplicar: true })),
      }))
      setFeito(r); setPrevia(null)
      aoGravar()  // a tabela abaixo é o passo seguinte: precisa refletir já
    } catch (e) {
      setMsg(`Não foi possível gravar (${e.detail || e.message}).`)
    }
  }

  return (
    <div className="rh-card">
      <h3>📥 Importar cargos do Tirvu (vários de uma vez)</h3>
      <p className="explica">Suba o <strong>.txt</strong> que você salvou do Bloco de Notas.
        Nada é gravado antes de você ver os números.</p>
      <input ref={inputRef} type="file" accept=".txt,text/plain" hidden
             onChange={(e) => enviar(e.target.files?.[0])} />
      <button className="btn-secundario btn-mini" onClick={() => inputRef.current?.click()}>
        📥 Escolher o .txt…</button>

      {previa && (
        <>
          <div className="rh-metricas" style={{ marginTop: '.6rem' }}>
            <div className="rh-metrica"><strong>{previa.total}</strong><span>no arquivo</span></div>
            <div className="rh-metrica"><strong>{seguros.length}</strong><span>prontos para gravar</span></div>
            <div className="rh-metrica"><strong>{ambiguos.length}</strong><span>precisam de você</span></div>
          </div>
          {ambiguos.length > 0 && (
            <div className="alerta">
              <strong>{ambiguos.length}</strong> {ambiguos.length === 1 ? 'cargo' : 'cargos'} com
              mais de um ID ativo — o sistema não escolhe por você. Depois de gravar os demais,
              ajuste o ID na tabela abaixo (o <strong>CBO</strong> é o que os diferencia):
              <ul>
                {ambiguos.slice(0, 5).map((p, i) => (
                  <li key={i}>{p.cargo}{p.cbo ? ` (CBO ${p.cbo})` : ''}
                    {p.pessoas_usando > 0 && ` — ${p.pessoas_usando} pessoa(s) usam`}</li>
                ))}
                {ambiguos.length > 5 && <li>…e mais {ambiguos.length - 5}.</li>}
              </ul>
            </div>
          )}
          <button className="btn-principal btn-mini" onClick={aplicar} disabled={!seguros.length}>
            Gravar {seguros.length} sem ambiguidade
          </button>
        </>
      )}

      {feito && (
        <div className="sucesso" style={{ marginTop: '.6rem' }}>
          {feito.gravados} cargo(s) gravado(s). Confira os IDs na tabela abaixo.
        </div>
      )}
      {msg && <div className="alerta" style={{ marginTop: '.6rem' }}>{msg}</div>}
    </div>
  )
}

// Cadastro de UM cargo (feedback do Bruno: "quando o rh quer subir apenas um
// cargo, daí seria interessante ter uma funcionalidade para isso, o CRUD").
// Antes, cadastrar um cargo exigia o ritual inteiro do .txt — abrir o Tirvu,
// copiar, colar no Bloco de Notas, salvar, subir — para gravar duas colunas.
function CadastrarUm({ aoSalvar, jaExiste }) {
  const [aberto, setAberto] = useState(false)
  const [cargo, setCargo] = useState('')
  const [tirvuId, setTirvuId] = useState('')
  const [cbo, setCbo] = useState('')
  const [erro, setErro] = useState(null)

  const limpar = () => { setCargo(''); setTirvuId(''); setCbo(''); setErro(null) }

  const salvar = async () => {
    setErro(null)
    const nome = cargo.trim()
    if (!nome) { setErro('Informe o cargo.'); return }
    if (!tirvuId.trim()) { setErro('Informe o ID do Tirvu — é ele que o export usa.'); return }
    try {
      await api.salvarCargoTirvu({ cargo_rotulo: nome, tirvu_id: tirvuId.trim(),
                                   cbo: cbo.trim() || null })
      limpar(); setAberto(false)
      aoSalvar(`Cargo "${nome}" cadastrado.`)
    } catch (e) { setErro(`Não foi possível salvar (${e.detail || e.message}).`) }
  }

  // Avisa ANTES de salvar que o cargo já tem ID: o upsert sobrescreveria calado,
  // e quem digitou de novo acha que está criando um segundo.
  const conflito = cargo.trim() ? jaExiste(cargo) : null

  if (!aberto) {
    return (
      <button className="btn-secundario btn-mini" onClick={() => setAberto(true)}>
        ＋ Cadastrar um cargo
      </button>
    )
  }

  return (
    <div className="rh-card" style={{ marginTop: '.6rem' }}>
      <h4>＋ Cadastrar um cargo</h4>
      <p className="explica">Para quando é <strong>um cargo só</strong> — não precisa do
        arquivo do Tirvu. O <strong>ID</strong> e o <strong>CBO</strong> estão na mesma tela
        de Cargos do Tirvu, ao lado do nome.</p>
      <div className="rh-grid-2">
        <label className="campo">
          <span className="rotulo">Cargo</span>
          <input value={cargo} onChange={(e) => setCargo(e.target.value)}
                 placeholder="ex.: Auxiliar de Serviços Gerais" autoComplete="off" />
        </label>
        <label className="campo">
          <span className="rotulo">ID no Tirvu</span>
          <input value={tirvuId} onChange={(e) => setTirvuId(e.target.value)}
                 placeholder="ex.: 50" autoComplete="off" />
        </label>
        <label className="campo">
          <span className="rotulo">CBO (opcional)</span>
          <input value={cbo} onChange={(e) => setCbo(e.target.value)}
                 placeholder="ex.: 514225" autoComplete="off" />
          <small className="explica">É o que diferencia dois cargos de mesmo nome.</small>
        </label>
      </div>
      {conflito && (
        <div className="aviso-inline">
          {/* Travessão no lugar do ID não distingue "não tem ID" de "não sei o
              ID" (a lição do creche, v2.27/v2.54) — e as duas situações pedem
              ações opostas: uma é preencher, a outra é substituir. */}
          &ldquo;{conflito.cargo_rotulo}&rdquo; já está na lista
          {conflito.tirvu_id
            ? <> com o ID <strong>{conflito.tirvu_id}</strong></>
            : <> e <strong>ainda sem ID</strong></>}
          {conflito.qtd > 0 && <>, usado por <strong>{conflito.qtd} pessoa(s)</strong></>}.{' '}
          {conflito.tirvu_id
            ? <>Salvar aqui <strong>substitui</strong> o ID dele.</>
            : <>Salvar aqui <strong>preenche</strong> o ID que falta — é o mesmo efeito de
              digitar direto na linha dele, abaixo.</>}
        </div>
      )}
      {erro && <div className="alerta" style={{ marginTop: '.6rem' }}>{erro}</div>}
      <div className="navegacao">
        <button className="btn-principal btn-mini" onClick={salvar}>Salvar cargo</button>
        <button className="btn-link" onClick={() => { limpar(); setAberto(false) }}>Cancelar</button>
      </div>
    </div>
  )
}

export default function CargosRH() {
  const [cargos, setCargos] = useState(null)
  const [erroCarga, setErroCarga] = useState(false)
  const [edicao, setEdicao] = useState({})   // {chave: {tirvu_id?, cbo?}}
  const [aviso, setAviso] = useState(null)

  const carregar = () => api.cargosTirvu()
    .then((r) => { setCargos(r); setErroCarga(false) })
    .catch(() => setErroCarga(true))
  // Falha de carga vira ERRO na tela com "tentar de novo", nunca lista vazia
  // (v2.46): `[]` diria "não há cargo nenhum", que é outra coisa.
  useEffect(() => { carregar() }, [])

  const salvarCampo = async (c, campo, valor) => {
    const atual = (c[campo] || '')
    const novo = (valor || '').trim()
    if (novo === atual) return
    // Apagar o ID REMOVE o de-para (o export volta a acusar pendência) — e sem
    // ID não há o que gravar, então o CBO sozinho não tem onde morar.
    try {
      await api.salvarCargoTirvu({
        cargo_rotulo: c.cargo_rotulo,
        tirvu_id: campo === 'tirvu_id' ? novo : (c.tirvu_id || ''),
        cbo: campo === 'cbo' ? novo : (c.cbo || null),
      })
      setEdicao((s) => { const n = { ...s }; delete n[c.cargo_normalizado]; return n })
      carregar()
      setAviso({ tipo: 'ok', texto: `"${c.cargo_rotulo}" atualizado.` })
    } catch (e) {
      setAviso({ tipo: 'erro', texto: `Não foi possível salvar (${e.detail || e.message}).` })
    }
  }

  const valorDe = (c, campo) => edicao[c.cargo_normalizado]?.[campo] ?? c[campo] ?? ''
  const editar = (c, campo, v) => setEdicao((s) => ({
    ...s, [c.cargo_normalizado]: { ...s[c.cargo_normalizado], [campo]: v },
  }))

  // Casa pelo mesmo critério do backend (minúsculo, sem acento, espaços
  // colapsados) — comparar cru diria "não existe" para "Vigia " com espaço.
  const normalizar = (s) => s.trim().toLowerCase()
    .normalize('NFD').replace(/[̀-ͯ]/g, '').replace(/\s+/g, ' ')
  const jaExiste = (nome) => (cargos || [])
    .find((c) => normalizar(c.cargo_rotulo) === normalizar(nome)) || null

  const semId = (cargos || []).filter((c) => !c.tirvu_id)
  const pessoasSemId = semId.reduce((s, c) => s + c.qtd, 0)

  return (
    <main className="rh-painel">
      <Aviso tipo={aviso?.tipo === 'erro' ? 'erro' : 'ok'} texto={aviso?.texto}
             aoFechar={() => setAviso(null)} />
      <header className="rh-topo">
        <h1>💼 Cargos</h1>
        <span />
      </header>

      <p className="explica">O cargo é <strong>texto livre</strong> na ficha de cada pessoa, mas a
        importação de admissões do Tirvu casa por <strong>ID numérico</strong> — sem o ID, a
        coluna Cargo sai vazia e o Tirvu recusa a linha. Esta página é onde cada cargo usado na
        base ganha o ID dele.</p>

      {/* O impedimento vai no TOPO, com o atalho que resolve (§ 8c do design):
          quem abre esta tela quase sempre veio de uma exportação que acusou
          pendência, e o número é o que diz se há trabalho a fazer. */}
      {cargos && semId.length > 0 && (
        <div className="alerta">
          <strong>{semId.length} cargo(s) ainda sem ID do Tirvu</strong>
          {pessoasSemId > 0 && <> — {pessoasSemId} pessoa(s) sairiam com a coluna Cargo vazia
            na próxima exportação.</>} Eles estão marcados em âmbar na tabela abaixo.
        </div>
      )}

      <ComoExtrair />
      <ImportarLote aoGravar={carregar} />

      <div className="rh-card">
        <h3>📋 Cargos da base</h3>
        <p className="explica">Todo cargo que alguém ocupa hoje aparece aqui, do mais usado ao
          menos. Edite o ID ou o CBO direto na linha — sai do campo, está salvo. Apagar o
          ID remove o de-para e o cargo volta a ficar pendente.</p>

        <CadastrarUm aoSalvar={(texto) => { carregar(); setAviso({ tipo: 'ok', texto }) }}
                     jaExiste={jaExiste} />

        {erroCarga && (
          <div className="alerta" style={{ marginTop: '.6rem' }}>
            Não foi possível carregar os cargos.{' '}
            <button className="btn-link" onClick={carregar}>Tentar de novo</button>
          </div>
        )}
        {!cargos && !erroCarga && <p className="explica">Carregando…</p>}
        {cargos && cargos.length === 0 && (
          <p className="explica">Nenhum cargo na base ainda — eles aparecem aqui conforme as
            pessoas são cadastradas, ou assim que você importar do Tirvu.</p>
        )}
        {cargos && cargos.length > 0 && (
          <div className="dash-scroll">
            <table className="rh-tabela">
              <thead><tr>
                <th>Cargo</th><th>Pessoas</th><th>ID Tirvu</th><th>CBO</th>
              </tr></thead>
              <tbody>{cargos.map((c) => (
                <tr key={c.cargo_normalizado}>
                  <td className="dash-quebra"><strong>{c.cargo_rotulo}</strong></td>
                  <td>{c.qtd}</td>
                  <td>
                    <input style={{ maxWidth: '6rem' }} placeholder="ex.: 50" autoComplete="off"
                           value={valorDe(c, 'tirvu_id')}
                           onChange={(e) => editar(c, 'tirvu_id', e.target.value)}
                           onBlur={(e) => salvarCampo(c, 'tirvu_id', e.target.value)}
                           className={c.tirvu_id ? '' : 'campo-pendente'} />
                  </td>
                  <td>
                    {/* O CBO só tem onde morar depois do ID: o de-para é uma
                        linha só, criada pelo ID. Habilitar antes ofereceria um
                        campo cujo valor se perderia sem nada dizendo. */}
                    <input style={{ maxWidth: '6rem' }} autoComplete="off"
                           placeholder={c.tirvu_id ? 'ex.: 514225' : '—'}
                           disabled={!c.tirvu_id}
                           title={c.tirvu_id ? 'É o que diferencia cargos de mesmo nome'
                                             : 'Informe o ID do Tirvu primeiro'}
                           value={valorDe(c, 'cbo')}
                           onChange={(e) => editar(c, 'cbo', e.target.value)}
                           onBlur={(e) => salvarCampo(c, 'cbo', e.target.value)} />
                  </td>
                </tr>
              ))}</tbody>
            </table>
          </div>
        )}
      </div>
    </main>
  )
}
