import { useRef, useState } from 'react'
import { rh as api } from '../api.js'
import { comAmpulheta } from '../Carregando.jsx'

// Central de Importações (feedback 2026-07-27: "quero uma aba dentro de
// configurações, em cards, para que tenha as instruções... movimentando as
// que porventura estão em outras páginas para que fiquem centralizadas").
// [decidido] MOVIMENTAR de verdade: os uploads saíram das telas de origem
// (que ganharam um link de cortesia para cá) e vivem só aqui. Reusa as MESMAS
// funções de api.js que já existiam — nenhuma lógica de importação foi
// duplicada, só a UI foi centralizada.
//
// Exceção: Incidência de Benefícios é fluxo de 2 passos (preview → decisões
// linha a linha → confirmar) com tela própria — o card aqui é um ATALHO para
// ela, não uma reimplementação (embutir seria reescrevê-la à toa).

// Card genérico de upload: título, instruções, formato aceito, e um
// formatador do relato de resposta (cada importação devolve campos
// diferentes — normalizar um envelope comum é dívida técnica futura; por ora
// cada card sabe formatar o seu).
function CardUpload({ titulo, instrucoes, aceita, aoImportar, formatarRelato, textoAmpulheta }) {
  const inputRef = useRef(null)
  const [msg, setMsg] = useState(null)
  const [relato, setRelato] = useState(null)

  const importar = async (arquivo) => {
    if (!arquivo) return
    setMsg(null); setRelato(null)
    try {
      const r = await comAmpulheta(textoAmpulheta, () => aoImportar(arquivo))
      setRelato(formatarRelato(r))
    } catch (e) {
      setMsg({ tipo: 'erro', texto: `Não foi possível importar (${e.detail || e.message}).` })
    } finally { if (inputRef.current) inputRef.current.value = '' }
  }

  return (
    <div className="rh-card">
      <h3>{titulo}</h3>
      <p className="explica">{instrucoes}</p>
      <input ref={inputRef} type="file" accept={aceita} hidden
             onChange={(e) => importar(e.target.files?.[0])} />
      <button className="btn-secundario btn-mini" onClick={() => inputRef.current?.click()}>
        📥 Escolher arquivo…</button>
      {relato && <div className="sucesso" style={{ marginTop: '.6rem' }}>{relato}</div>}
      {msg && <div className="alerta" style={{ marginTop: '.6rem' }}>{msg.texto}</div>}
    </div>
  )
}

export default function Importacoes() {
  return (
    <div>
      <p className="explica">Uploads de planilha em massa, centralizados aqui — cada card diz
        para que serve, o formato esperado e o que acontece com duplicados. Nenhuma importação
        altera dados sem revisão: o que já existe é atualizado com cuidado, o que não casa vira
        pendência para o RH resolver (nunca é descartado em silêncio).</p>

      <div className="rh-grid-2">
        <CardUpload
          titulo="👥 Colaboradores (base do Tirvu)"
          instrucoes="Planilha de colaboradores exportada do Tirvu. Casa por CPF: quem já existe é
            atualizado, quem não existe é criado. Reimportar o mesmo arquivo não duplica."
          aceita=".xlsx"
          textoAmpulheta="Importando a base de colaboradores…"
          aoImportar={(f) => api.importarColaboradores(f)}
          formatarRelato={(r) => `${r.criados} novo(s), ${r.atualizados} atualizado(s)`
            + (r.sem_cpf ? `, ${r.sem_cpf} linha(s) sem CPF ignorada(s)` : '')
            + `. Base total: ${r.total_base}.`}
        />

        <CardUpload
          titulo="🏢 Postos de serviço (planilha do Tirvu)"
          instrucoes="Planilha de Postos exportada do Tirvu. Casa por ID Tirvu (ou por nome, se o
            posto ainda não tiver ID). Preenche o tirvu_id automaticamente."
          aceita=".xlsx"
          textoAmpulheta="Importando a planilha de postos do Tirvu…"
          aoImportar={(f) => api.importarPostosPlanilha(f)}
          formatarRelato={(r) => `${r.criados} novo(s), ${r.atualizados} atualizado(s). `
            + `Total: ${r.total} posto(s).`}
        />

        <CardUpload
          titulo="🕒 Jornadas (planilha de colaboradores)"
          instrucoes="A mesma planilha de colaboradores do Tirvu tem uma coluna 'Jornada de
            Trabalho' — este card lê só essa coluna e cria as jornadas que ainda não existem."
          aceita=".xlsx"
          textoAmpulheta="Importando jornadas da planilha…"
          aoImportar={(f) => api.importarJornadasPlanilha(f)}
          formatarRelato={(r) => `${r.criadas} nova(s), ${r.puladas} já existente(s) `
            + `(de ${r.total_planilha} linhas). Confira a estruturação proposta em `
            + `Jornadas → "A confirmar".`}
        />

        <CardUpload
          titulo="🕒 Jornadas (planilha de escalas — 96 abas)"
          instrucoes="Planilha 'Escala de Trabalho - Detalhado' do Tirvu: cada aba é um posto. Traz
            todas as descrições de jornada distintas, sem fundir nenhuma parecida."
          aceita=".xlsx"
          textoAmpulheta="Lendo a planilha de escalas…"
          aoImportar={(f) => api.importarJornadas(f)}
          formatarRelato={(r) => `${r.jornadas_criadas} jornada(s) nova(s) de `
            + `${r.abas_processadas} aba(s) — ${r.abas_casadas_com_posto} casaram com postos.`}
        />

        <CardUpload
          titulo="🎯 Banco de Talentos (planilha do Microsoft Forms)"
          instrucoes="Pré-cadastros exportados do Microsoft Forms. Casa por e-mail (ou nome+telefone
            sem e-mail) — não duplica, mesmo com repetição dentro da própria planilha."
          aceita=".xlsx"
          textoAmpulheta="Importando a planilha do Banco de Talentos…"
          aoImportar={(f) => api.importarTalentosPlanilha(f)}
          formatarRelato={(r) => `${r.criados} novo(s), ${r.pulados} já existente(s) pulado(s) `
            + `(de ${r.total_planilha} na planilha).`}
        />

        <CardUpload
          titulo="📌 Ponto eletrônico (frequência do Tirvu)"
          instrucoes="Ponto exportado do Tirvu. Casa por matrícula. Vira CONTEXTO ao lado da
            avaliação de desempenho — nunca nota automática. Quem não casar fica listado."
          aceita=".xlsx"
          textoAmpulheta="Importando o ponto…"
          aoImportar={(f) => api.importarPonto(f)}
          formatarRelato={(r) => `${r.importados} colaborador(es) importado(s) de ${r.total}.`
            + (r.nao_casados?.length ? ` ${r.nao_casados.length} não reconhecido(s) pela matrícula.` : '')}
        />
      </div>

      <div className="rh-card">
        <h3>📊 Incidência de Benefícios (contratos × reembolso-creche)</h3>
        <p className="explica">Planilha com 2 abas (Público/Privado) que define a elegibilidade de
          creche por contrato. Fluxo de <strong>2 passos</strong>: o sistema propõe a equivalência
          entre a planilha e os postos da base, e o RH confirma linha a linha antes de aplicar —
          por isso continua em tela própria, dentro de <strong>Postos</strong>.</p>
        <p className="explica">→ Acesse em <strong>Postos → 📊 Incidência de Benefícios</strong>.</p>
      </div>

      <CardDeParaLotacoes />
      <CardVinculos />

      <CardTirvuTxt
        titulo="🧾 Cargos (arquivo .txt copiado do Tirvu)"
        instrucoes={<>O Tirvu não exporta cargos: selecione a lista inteira na tela dele,
          cole no Bloco de Notas e salve o <strong>.txt</strong>. O sistema lê o ID, o cargo e
          o <strong>CBO</strong> de cada linha. Cargo com dois IDs ativos (o CBO diferencia)
          nunca é resolvido sozinho — fica separado para você decidir.</>}
        aoEnviar={api.previewCargosArquivo}
        aoAplicar={api.confirmarCargosTirvu}
        campoNome="cargo"
        montarItem={(p) => ({ tirvu_id: p.tirvu_id, cargo: p.cargo, cbo: p.cbo, aplicar: true })}
        rotuloAmbiguo="cargo com mais de um ID ativo"
        ondeDecidir="Configurações → Empresas e jornadas"
      />

      <CardTirvuTxt
        titulo="🕕 Jornadas (arquivo .txt copiado do Tirvu)"
        instrucoes={<>Mesma coisa da lista de <strong>Jornadas</strong>: o sistema lê o ID, a
          descrição, a escala e o tratamento (banco de horas). Descrição repetida com IDs
          diferentes fica separada — fundir jornada é errar turno de gente, e o erro só
          aparece no contracheque.</>}
        aoEnviar={api.previewJornadasArquivo}
        aoAplicar={api.confirmarJornadasTirvu}
        campoNome="descricao"
        montarItem={(p) => ({ tirvu_id: p.tirvu_id, descricao: p.descricao,
                              escala: p.escala || '', tratamento: p.tratamento || '',
                              aplicar: true })}
        rotuloAmbiguo="descrição repetida com IDs diferentes"
        ondeDecidir="Configurações → Empresas e jornadas"
      />
    </div>
  )
}

// De-para lotação → posto (v2.40). É a peça que faltava para o vínculo em
// massa alcançar todo mundo: a lotação vem abreviada na planilha ("INEP ADM",
// "ANAC") e o apelido do posto aqui é o padrão longo. Só 11% casam sozinhos, e
// "ANAC" pode ser SEDE ou AEROPORTO — ambiguidade do DADO, que nenhum
// algoritmo resolve honestamente.
//
// Por isso a tela ordena por QUANTAS PESSOAS dependem de cada lotação: resolver
// "INEP ADM" (174 pessoas) antes de uma com 1 é o que respeita o tempo do RH.
function CardDeParaLotacoes() {
  const inputRef = useRef(null)
  const [previa, setPrevia] = useState(null)
  const [escolhas, setEscolhas] = useState({})
  const [msg, setMsg] = useState(null)
  const [feito, setFeito] = useState(null)

  const enviar = async (arquivo) => {
    if (!arquivo) return
    setMsg(null); setPrevia(null); setFeito(null); setEscolhas({})
    try {
      const r = await comAmpulheta('Procurando as lotações sem posto…',
        () => api.previewDeParaLotacoes(arquivo))
      setPrevia(r)
      // Pré-seleciona a melhor sugestão SÓ quando ela é folgadamente a melhor:
      // com duas parecidas (o caso "ANAC"), o campo fica vazio de propósito —
      // pré-selecionar uma delas é decidir no lugar do RH disfarçando de
      // sugestão.
      const inicial = {}
      for (const p of r.pendentes) {
        const [a, b] = p.sugestoes
        if (a && (!b || a.score - b.score > 0.15)) inicial[p.lotacao] = a.posto_id
      }
      setEscolhas(inicial)
    } catch (e) {
      setMsg(`Não foi possível ler a planilha (${e.detail || e.message}).`)
    } finally { if (inputRef.current) inputRef.current.value = '' }
  }

  const confirmar = async () => {
    setMsg(null)
    const itens = Object.entries(escolhas)
      .filter(([, posto_id]) => posto_id)
      .map(([lotacao, posto_id]) => ({ lotacao, posto_id }))
    if (!itens.length) { setMsg('Escolha ao menos um posto.'); return }
    try {
      setFeito(await comAmpulheta('Gravando o de-para…',
        () => api.confirmarDeParaLotacoes(itens)))
      setPrevia(null)
    } catch (e) {
      setMsg(`Não foi possível gravar (${e.detail || e.message}).`)
    }
  }

  const escolhidos = Object.values(escolhas).filter(Boolean).length
  const pessoasCobertas = (previa?.pendentes || [])
    .filter((p) => escolhas[p.lotacao]).reduce((s, p) => s + p.pessoas, 0)

  return (
    <div className="rh-card">
      <h3>🗺️ De-para de lotações (Tirvu → posto daqui)</h3>
      <p className="explica">A lotação vem <strong>abreviada</strong> na planilha do Tirvu
        (&ldquo;INEP ADM&rdquo;, &ldquo;ANAC&rdquo;) e aqui o posto tem o nome completo — por isso
        a maioria não casa sozinha. Suba a <strong>planilha de Colaboradores</strong>: o sistema
        ordena os postos mais parecidos e <strong>você escolhe</strong>. Feito uma vez, as
        próximas importações já sabem.</p>
      <input ref={inputRef} type="file" accept=".xlsx" hidden
             onChange={(e) => enviar(e.target.files?.[0])} />
      <button className="btn-secundario btn-mini" onClick={() => inputRef.current?.click()}>
        📥 Escolher a planilha…</button>

      {previa && previa.pendentes.length === 0 && (
        <div className="sucesso" style={{ marginTop: '.6rem' }}>
          Todas as lotações desta planilha já têm posto. Nada a decidir.
        </div>
      )}

      {previa && previa.pendentes.length > 0 && (
        <>
          <div className="rh-metricas" style={{ marginTop: '.6rem' }}>
            <div className="rh-metrica"><strong>{previa.pendentes.length}</strong><span>lotações sem posto</span></div>
            <div className="rh-metrica"><strong>{previa.total_pessoas}</strong><span>pessoas esperando</span></div>
            <div className="rh-metrica"><strong>{previa.ja_mapeadas}</strong><span>já decididas antes</span></div>
          </div>
          <div className="dash-scroll">
            <table className="rh-tabela">
              <thead><tr><th>Lotação (Tirvu)</th><th>Pessoas</th><th>Posto daqui</th></tr></thead>
              <tbody>
                {previa.pendentes.map((p) => (
                  <tr key={p.lotacao}>
                    <td className="dash-quebra">{p.lotacao}</td>
                    <td><strong>{p.pessoas}</strong></td>
                    <td>
                      <select value={escolhas[p.lotacao] || ''}
                              onChange={(e) => setEscolhas(
                                (x) => ({ ...x, [p.lotacao]: e.target.value }))}>
                        <option value="">— deixar para depois —</option>
                        {p.sugestoes.map((s) => (
                          <option key={s.posto_id} value={s.posto_id}>
                            {s.posto_nome} ({Math.round(s.score * 100)}%)
                          </option>
                        ))}
                        {/* A lista inteira: a sugestão pode simplesmente não ter
                            o posto certo, e sem esta saída o RH ficaria preso. */}
                        <optgroup label="Todos os postos">
                          {previa.postos.map((s) => (
                            <option key={s.id} value={s.id}>{s.nome}</option>
                          ))}
                        </optgroup>
                      </select>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="explica">
            Onde duas sugestões ficaram parecidas, o campo vem <strong>vazio de
            propósito</strong> — &ldquo;ANAC&rdquo; pode ser a sede ou o aeroporto, e essa
            escolha é sua. O que ficar em branco continua na fila.
          </p>
          <button className="btn-principal btn-mini" onClick={confirmar} disabled={!escolhidos}>
            Gravar {escolhidos} de-para ({pessoasCobertas} pessoa(s))
          </button>
        </>
      )}

      {feito && (
        <div className="sucesso" style={{ marginTop: '.6rem' }}>
          {feito.criados} de-para criado(s), {feito.atualizados} atualizado(s). Agora rode
          o card abaixo (&ldquo;Vincular colaboradores&rdquo;) para essas pessoas ganharem o posto.
        </div>
      )}
      {msg && <div className="alerta" style={{ marginTop: '.6rem' }}>{msg}</div>}
    </div>
  )
}

// Vínculo em massa (v2.39): a MESMA planilha de Colaboradores do Tirvu traz,
// por pessoa, Lotação, Cargo, Jornada de Trabalho e PCD — e o portal só usava
// as duas primeiras. Este card cruza tudo e mostra o que vai gravar ANTES de
// gravar: são ~1.000 registros, e o que se sobrescreve não volta.
//
// Divergência (valor diferente aqui) fica FORA do lote: pode ser correção que
// o RH fez à mão, e passar por cima em massa é irreversível na prática.
function CardVinculos() {
  const inputRef = useRef(null)
  const [previa, setPrevia] = useState(null)
  const [msg, setMsg] = useState(null)
  const [feito, setFeito] = useState(null)
  const [incluirPcd, setIncluirPcd] = useState(true)

  const enviar = async (arquivo) => {
    if (!arquivo) return
    setMsg(null); setPrevia(null); setFeito(null)
    try {
      setPrevia(await comAmpulheta('Cruzando a planilha com a base…',
        () => api.previewVinculos(arquivo)))
    } catch (e) {
      setMsg(e.detail === 'sem_coluna_cpf'
        ? 'A planilha não tem coluna de CPF — é ela que identifica cada pessoa.'
        : `Não foi possível ler a planilha (${e.detail || e.message}).`)
    } finally { if (inputRef.current) inputRef.current.value = '' }
  }

  const aplicar = async () => {
    setMsg(null)
    try {
      const itens = previa.itens.map((i) => ({
        cpf: i.cpf,
        jornada_id: i.jornada.situacao === 'preencher' ? i.jornada.id : null,
        cargo_funcao: i.cargo.situacao === 'preencher' ? i.cargo.texto : null,
        posto_id: i.posto.situacao === 'preencher' ? i.posto.id : null,
        pcd: incluirPcd && i.pcd.situacao === 'preencher' ? i.pcd.valor : null,
        pcd_deficiencia: incluirPcd ? i.pcd.deficiencia : null,
      }))
      setFeito(await comAmpulheta('Gravando os vínculos…', () => api.aplicarVinculos(itens)))
      setPrevia(null)
    } catch (e) {
      setMsg(`Não foi possível gravar (${e.detail || e.message}).`)
    }
  }

  const comPcd = (previa?.itens || []).filter((i) => i.pcd.situacao === 'preencher' && i.pcd.valor)

  return (
    <div className="rh-card">
      <h3>🔗 Vincular colaboradores (posto, cargo e jornada do Tirvu)</h3>
      <p className="explica">Use a <strong>mesma planilha de Colaboradores</strong> exportada do
        Tirvu. O sistema cruza por CPF e preenche a jornada, o cargo e o posto de quem está sem
        eles aqui — <strong>sem tocar</strong> em quem já tem valor diferente (isso vira uma lista
        para você decidir). Nada é gravado antes de você conferir os números.</p>
      <input ref={inputRef} type="file" accept=".xlsx" hidden
             onChange={(e) => enviar(e.target.files?.[0])} />
      <button className="btn-secundario btn-mini" onClick={() => inputRef.current?.click()}>
        📥 Escolher a planilha…</button>

      {previa && (
        <>
          <div className="rh-metricas" style={{ marginTop: '.6rem' }}>
            <div className="rh-metrica"><strong>{previa.linhas}</strong><span>na planilha</span></div>
            <div className="rh-metrica"><strong>{previa.prontas}</strong><span>prontos para vincular</span></div>
            <div className="rh-metrica"><strong>{previa.divergentes}</strong><span>divergem (você decide)</span></div>
            <div className="rh-metrica"><strong>{previa.fora_da_base}</strong><span>não estão no portal</span></div>
          </div>

          {comPcd.length > 0 && (
            <label className="campo campo-sem-margem">
              <span>
                <input type="checkbox" checked={incluirPcd}
                       onChange={(e) => setIncluirPcd(e.target.checked)} />{' '}
                Registrar também <strong>{comPcd.length} pessoa(s) como PCD</strong>, conforme o
                Tirvu
              </span>
              <small className="explica">É informação de saúde e vem da base do Tirvu, não de
                declaração da pessoa. Fica registrado quem aplicou e quando.</small>
            </label>
          )}

          {previa.lotacoes_sem_par.length > 0 && (
            <div className="alerta">
              <strong>{previa.lotacoes_sem_par.length} lotações</strong> da planilha não têm posto
              correspondente aqui — a lotação vem abreviada no Tirvu e o mesmo nome pode ser dois
              postos (&ldquo;ANAC&rdquo; é sede ou aeroporto?). Ninguém é vinculado no chute; o
              de-para assistido resolve isso:
              <ul>
                {previa.lotacoes_sem_par.slice(0, 5).map((l, i) => (
                  <li key={i}>{l.texto} — <strong>{l.pessoas}</strong> pessoa(s)</li>
                ))}
                {previa.lotacoes_sem_par.length > 5
                  && <li>…e mais {previa.lotacoes_sem_par.length - 5}.</li>}
              </ul>
            </div>
          )}

          {previa.jornadas_sem_par.length > 0 && (
            <div className="alerta">
              <strong>{previa.jornadas_sem_par.length}</strong> descrição(ões) de jornada da
              planilha não existem aqui. Suba o <strong>.txt de Jornadas</strong> (card acima) e
              rode de novo:
              <ul>
                {previa.jornadas_sem_par.slice(0, 3).map((j, i) => (
                  <li key={i}>{j.texto} — {j.pessoas} pessoa(s)</li>
                ))}
              </ul>
            </div>
          )}

          <button className="btn-principal btn-mini" onClick={aplicar} disabled={!previa.prontas}>
            Vincular {previa.prontas} colaborador(es)
          </button>
        </>
      )}

      {feito && (
        <div className="sucesso" style={{ marginTop: '.6rem' }}>
          {feito.jornada} jornada(s), {feito.cargo} cargo(s), {feito.posto} posto(s)
          {feito.pcd > 0 && `, ${feito.pcd} PCD`} gravados.
          {feito.ignorados > 0 && ` ${feito.ignorados} ignorado(s) (CPF fora do portal).`}
        </div>
      )}
      {msg && <div className="alerta" style={{ marginTop: '.6rem' }}>{msg}</div>}
    </div>
  )
}

// Upload do .txt copiado da tela do Tirvu (v2.38, pedido do Bruno: "quero
// apenas subir os txts e o sistema entender").
//
// O que MUDOU foi a porta de entrada — subir o arquivo em vez de colar o texto.
// O que NÃO mudou é a regra da casa: o sistema PROPÕE e o RH confirma. Por isso
// o card mostra o que vai gravar ANTES de gravar, e separa o que é ambíguo:
// nos dados reais são 2 cargos homônimos que 87 pessoas usam, e adivinhar qual
// é qual muda o CBO de gente de verdade.
function CardTirvuTxt({ titulo, instrucoes, aoEnviar, aoAplicar, campoNome,
                        montarItem, rotuloAmbiguo, ondeDecidir }) {
  const inputRef = useRef(null)
  const [previa, setPrevia] = useState(null)
  const [msg, setMsg] = useState(null)
  const [feito, setFeito] = useState(null)

  const enviar = async (arquivo) => {
    if (!arquivo) return
    setMsg(null); setPrevia(null); setFeito(null)
    try {
      setPrevia(await comAmpulheta('Lendo o arquivo…', () => aoEnviar(arquivo)))
    } catch (e) {
      // A contagem do cabeçalho não bater é o erro ÚTIL aqui: significa cópia
      // parcial da tela, e importar metade calado seria pior que recusar.
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
      const r = await comAmpulheta('Gravando…',
        () => aoAplicar({ itens: seguros.map(montarItem) }))
      setFeito(r)
      setPrevia(null)
    } catch (e) {
      setMsg(`Não foi possível gravar (${e.detail || e.message}).`)
    }
  }

  return (
    <div className="rh-card">
      <h3>{titulo}</h3>
      <p className="explica">{instrucoes}</p>
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
              <strong>{ambiguos.length}</strong> {ambiguos.length === 1 ? 'item' : 'itens'} com{' '}
              {rotuloAmbiguo} — o sistema não escolhe por você. Depois de gravar os demais,
              resolva em <strong>{ondeDecidir}</strong>:
              <ul>
                {ambiguos.slice(0, 5).map((p, i) => (
                  <li key={i}>{p[campoNome]}{p.cbo ? ` (CBO ${p.cbo})` : ''}
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
          {feito.gravados != null && `${feito.gravados} cargo(s) gravado(s).`}
          {feito.criadas != null && `${feito.criadas} criada(s), ${feito.atualizadas} atualizada(s).`}
        </div>
      )}
      {msg && <div className="alerta" style={{ marginTop: '.6rem' }}>{msg}</div>}
    </div>
  )
}
