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

      <div className="rh-card">
        <h3>📋 Cargos e jornadas (colados da tela do Tirvu)</h3>
        <p className="explica">Não é upload de arquivo — o RH cola o texto copiado direto da tela do
          Tirvu. Continua na aba <strong>Empresas e jornadas</strong>, logo abaixo do de-para de
          cargos, por ser o mesmo assunto.</p>
      </div>
    </div>
  )
}
