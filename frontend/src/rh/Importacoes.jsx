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
