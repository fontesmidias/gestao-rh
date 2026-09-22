# Os 48 e-mails: quais esperam resposta?

**Conclusão da análise (2026-09-22): NENHUM espera resposta.**

Todos são notificações automáticas, e cada um já tem um caminho próprio
de volta. O rodapé "não responda — fale com <contato>" está correto em
todos os 48. A capacidade de excluir existe (`responder=true` no
`html_moderno`) para o dia em que surgir um e-mail conversacional.

## Como cheguei a essa conclusão

Três casos me fizeram olhar duas vezes — e são justamente os que confirmam
a regra:

| Template | Por que olhei | Conclusão |
|---|---|---|
| `creche_declaracao_modelo` | manda um anexo para a pessoa preencher | a devolução é pelo **portal**, não por e-mail |
| `entrevista_marcada` | a pessoa pode querer remarcar | a resposta vai para o RH — e é o rodapé que diz para onde |
| `talento_agradecimento` | candidato pode ter dúvida | mais um motivo para o contato certo aparecer |

Os 10 **avisos internos** são o caso mais claro: vão para a própria equipe
e são informativos ("dossiê pronto", "logs 4x ao dia"). Os 9 **códigos de
acesso** têm a ação numa tela, não numa resposta.

⚠️ **Se um dia um e-mail passar a esperar resposta** (o minutário, se sair
por esta via), o caminho é `html_moderno(..., responder=True)` — não
apagar o rodapé dos outros.

## Admissão (2)

**Por que não espera resposta:** a pessoa volta pelo LINK do wizard, que vai no próprio e-mail

- `convite_admissao` — Convite para começar a admissão
- `link_acesso_reenvio` — Reenvio do link de acesso

## Documentos (3)

**Por que não espera resposta:** o reenvio é pelo checklist, no link da admissão

- `documento_rejeitado` — Um documento precisa ser reenviado
- `documentos_rejeitados_lote` — Vários documentos precisam ser reenviados
- `admissao_pendencias` — Cobrança de pendências da admissão

## Assinatura (6)

**Por que não espera resposta:** a assinatura acontece no link, com código por e-mail

- `ficha_alterada_reassinar` — Ficha alterada pelo RH: reassinar
- `posto_novos_documentos` — Novos documentos para assinar (mudança de posto)
- `assinatura_vias_assinadas` — Vias assinadas (com os PDFs em anexo)
- `modelo_para_assinar` — Documento de modelo aguarda assinatura
- `modelo_anexo` — Documento de modelo em anexo (sem assinatura)
- `assinatura_externa_convite` — Convite para assinante externo

## Reembolso-Creche (10)

**Por que não espera resposta:** o colaborador age no portal do creche (link no e-mail)

- `creche_devolvido` — Pedido devolvido para correção
- `creche_ativado` — Benefício ativado: orientações
- `creche_lembrete_mensal` — Lembrete: comprovante do mês
- `creche_requerimento_disponivel` — Requerimento disponível para assinar
- `creche_declaracao_modelo` — Declaração de quitação (modelo em anexo)
- `creche_indeferido` — Pedido indeferido
- `creche_suspenso` — Benefício suspenso ou encerrado
- `creche_aguardando_contrato` — Aprovado, aguardando o contrato
- `creche_incluir_crianca` — Reaberto para incluir criança
- `creche_sem_direito` — Registro de 'não faço jus'

## Colaborador (4)

**Por que não espera resposta:** a ação é no portal do colaborador (/meu)

- `desempenho_avaliacao` — Sua avaliação está disponível
- `certificacao_vencendo` — Certificação vencendo ou vencida
- `desenvolvimento_devolvido` — Curso/certificado devolvido para ajuste
- `desenvolvimento_recusado` — Curso/certificado recusado

## Entrevistas (3)

**Por que não espera resposta:** traz convite de calendário (.ics); remarcar é falar com o RH

- `entrevista_marcada` — Entrevista marcada
- `entrevista_lembrete` — Lembrete da entrevista (véspera)
- `entrevista_cancelada` — Entrevista cancelada

## Códigos de acesso (9)

**Por que não espera resposta:** o código se usa na tela de onde foi pedido

- `assinatura_codigo_lote` — Código para assinar as fichas da admissão
- `assinatura_codigo_documento` — Código para assinar um documento
- `assinatura_externa_codigo` — Código para assinante externo
- `autorizacao_equipe_codigo` — Código de autorização da equipe
- `teste_codigo` — Código de confirmação do teste
- `creche_codigo` — Código do Reembolso-Creche
- `portal_codigo` — Código de acesso ao portal do colaborador
- `rh_redefinir_senha` — Redefinição de senha do painel
- `rh_usuario_criado` — Acesso ao painel criado

## Avisos internos (10)

**Por que não espera resposta:** vão para a EQUIPE, são informativos — ninguém responde

- `aviso_envio_concluido` — Candidato concluiu o envio
- `aviso_documento_reenviado` — Documento reenviado por quem já foi aprovado
- `aviso_uniforme` — Uniforme: tamanhos de um novo admitido
- `aviso_telemetria_alerta` — ⚠️ Telemetria: algo quebrou ou travou
- `aviso_dossie_pronto` — Dossiê de admissão pronto
- `aviso_creche_levantamento` — Reembolso-Creche: levantamento enviado
- `aviso_logs_periodico` — Logs dos serviços (4x ao dia)
- `aviso_talento_cadastrado` — Banco de Talentos: novo cadastro
- `aviso_desenvolvimento_enviado` — Colaborador enviou curso ou certificado
- `aviso_match_concluido` — Match de Vagas: ranqueamento concluído

## Banco de Talentos (1)

**Por que não espera resposta:** confirmação de cadastro; dúvida vai para o RH

- `talento_agradecimento` — Agradecimento pelo cadastro

