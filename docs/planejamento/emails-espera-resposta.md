# Os 48 e-mails do sistema — quais esperam resposta?

Marque a coluna "Espera resposta?" nos que NÃO devem levar o rodapé
"não responda". Minha leitura inicial está na última coluna.

## Admissão (2)

| Chave | O que é | Quando dispara | Espera resposta? |
|---|---|---|---|
| `convite_admissao` | Convite para começar a admissão | O RH cadastra o candidato (e no reenvio do convite). | |
| `link_acesso_reenvio` | Reenvio do link de acesso | O candidato pede um novo link pelo portal de entrada. | |

## Documentos (3)

| Chave | O que é | Quando dispara | Espera resposta? |
|---|---|---|---|
| `documento_rejeitado` | Um documento precisa ser reenviado | O RH rejeita um documento do checklist. | |
| `documentos_rejeitados_lote` | Vários documentos precisam ser reenviados | O RH rejeita vários documentos de uma vez. | |
| `admissao_pendencias` | Cobrança de pendências da admissão | O RH aciona 'Notificar pendências' na ficha do candidato. | |

## Assinatura (6)

| Chave | O que é | Quando dispara | Espera resposta? |
|---|---|---|---|
| `ficha_alterada_reassinar` | Ficha alterada pelo RH: reassinar | O RH edita a ficha e isso invalida documentos já assinados. | |
| `posto_novos_documentos` | Novos documentos para assinar (mudança de posto) | A mudança de posto/regime gera documentos novos. | |
| `assinatura_vias_assinadas` | Vias assinadas (com os PDFs em anexo) | Logo após o candidato assinar — leva as vias dele em anexo. | |
| `modelo_para_assinar` | Documento de modelo aguarda assinatura | O RH envia um documento de modelo para a pessoa assinar. | |
| `modelo_anexo` | Documento de modelo em anexo (sem assinatura) | O RH envia um documento de modelo apenas para conhecimento. | |
| `assinatura_externa_convite` | Convite para assinante externo | Um documento em roteiro chega à vez de um assinante de fora. | |

## Reembolso-Creche (10)

| Chave | O que é | Quando dispara | Espera resposta? |
|---|---|---|---|
| `creche_devolvido` | Pedido devolvido para correção | O RH devolve o levantamento do creche para correção. | |
| `creche_ativado` | Benefício ativado: orientações | O RH aprova e ativa o Reembolso-Creche. | |
| `creche_lembrete_mensal` | Lembrete: comprovante do mês | Faltando N dias para a data de corte, quando o comprovante daquele mês | |
| `creche_requerimento_disponivel` | Requerimento disponível para assinar | O requerimento de concessão é liberado para a assinatura do colaborado | |
| `creche_declaracao_modelo` | Declaração de quitação (modelo em anexo) | O RH envia ao colaborador o modelo de declaração de quitação, para o c | |
| `creche_indeferido` | Pedido indeferido | O RH indefere o pedido de Reembolso-Creche. | |
| `creche_suspenso` | Benefício suspenso ou encerrado | O RH suspende ou encerra o benefício. | |
| `creche_aguardando_contrato` | Aprovado, aguardando o contrato | O RH aprova mas o pagamento depende de repactuação do contrato. | |
| `creche_incluir_crianca` | Reaberto para incluir criança | O RH reabre o benefício para o colaborador incluir outra criança. | |
| `creche_sem_direito` | Registro de 'não faço jus' | Fica registrado que o colaborador declarou não ter direito. | |

## Colaborador (4)

| Chave | O que é | Quando dispara | Espera resposta? |
|---|---|---|---|
| `desempenho_avaliacao` | Sua avaliação está disponível | O RH libera o ciclo de avaliação de desempenho. | |
| `certificacao_vencendo` | Certificação vencendo ou vencida | O worker diário avisa 90 dias antes do vencimento. | |
| `desenvolvimento_devolvido` | Curso/certificado devolvido para ajuste | O RH devolve um documento do colaborador para correção. | |
| `desenvolvimento_recusado` | Curso/certificado recusado | O RH recusa um documento enviado pelo colaborador (terminal). | |

## Entrevistas (3)

| Chave | O que é | Quando dispara | Espera resposta? |
|---|---|---|---|
| `entrevista_marcada` | Entrevista marcada | O RH marca a entrevista (e a cada remarcação). Leva o convite de calen | |
| `entrevista_lembrete` | Lembrete da entrevista (véspera) | O worker diário avisa cerca de 24h antes da entrevista marcada. Uma ve | |
| `entrevista_cancelada` | Entrevista cancelada | O RH cancela uma entrevista que já tinha convite enviado. Leva o cance | |

## Códigos de acesso (9)

| Chave | O que é | Quando dispara | Espera resposta? |
|---|---|---|---|
| `assinatura_codigo_lote` | Código para assinar as fichas da admissão | O candidato pede o código para assinar os documentos da admissão. | |
| `assinatura_codigo_documento` | Código para assinar um documento | O candidato pede o código para assinar um documento avulso. | |
| `assinatura_externa_codigo` | Código para assinante externo | Um assinante de fora da empresa pede o código para assinar. | |
| `autorizacao_equipe_codigo` | Código de autorização da equipe | Um representante confirma a autorização permanente de assinatura. | |
| `teste_codigo` | Código de confirmação do teste | O participante confirma a identidade para começar um teste. | |
| `creche_codigo` | Código do Reembolso-Creche | O colaborador informa o CPF no link público do creche. | |
| `portal_codigo` | Código de acesso ao portal do colaborador | O colaborador informa o CPF em /meu. | |
| `rh_redefinir_senha` | Redefinição de senha do painel | Alguém do RH pede para redefinir a senha do painel. | |
| `rh_usuario_criado` | Acesso ao painel criado | O RH cadastra uma pessoa nova no painel. | |

## Avisos internos (10)

| Chave | O que é | Quando dispara | Espera resposta? |
|---|---|---|---|
| `aviso_envio_concluido` | Candidato concluiu o envio | O candidato clica em 'CONCLUÍ MEU ENVIO'. | |
| `aviso_documento_reenviado` | Documento reenviado por quem já foi aprovado | Um candidato já aprovado reenvia um documento que fora rejeitado. | |
| `aviso_uniforme` | Uniforme: tamanhos de um novo admitido | O candidato conclui a admissão tendo informado os tamanhos. | |
| `aviso_telemetria_alerta` | ⚠️ Telemetria: algo quebrou ou travou | Uma regra de alerta dispara (verificação a cada 15 minutos). | |
| `aviso_dossie_pronto` | Dossiê de admissão pronto | O dossiê completo de um candidato termina de ser gerado. | |
| `aviso_creche_levantamento` | Reembolso-Creche: levantamento enviado | Um colaborador envia (ou reenvia) o levantamento para análise. | |
| `aviso_logs_periodico` | Logs dos serviços (4x ao dia) | A cada 6 horas, com o resumo do período e os arquivos em anexo. | |
| `aviso_talento_cadastrado` | Banco de Talentos: novo cadastro | Alguém se cadastra pelo formulário público do Banco de Talentos. | |
| `aviso_desenvolvimento_enviado` | Colaborador enviou curso ou certificado | Alguém envia algo novo pelo portal e a fila de validação cresce. | |
| `aviso_match_concluido` | Match de Vagas: ranqueamento concluído | Termina o ranqueamento de uma vaga contra o Banco de Talentos. | |

## Banco de Talentos (1)

| Chave | O que é | Quando dispara | Espera resposta? |
|---|---|---|---|
| `talento_agradecimento` | Agradecimento pelo cadastro | Alguém se cadastra no Banco de Talentos. | |

