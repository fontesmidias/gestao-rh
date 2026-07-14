# Modelo de Dados — Portal de Admissão

> Derivado da leitura campo a campo da "Ficha de Admissão — Green House" (Microsoft Forms,
> 50 perguntas — captura em `docs/formulario-de-admissao/`, fora do versionamento por conter
> potencial dado pessoal). Data: 2026-07-13.

## Princípios

- **Fidelidade ao formulário atual** — mesmos dados coletados, mesma base legal (LGPD:
  art. 7º II/V/VI; cor/raça e saúde: art. 11 II 'a' e 'e').
- **Estruturar o que o Forms obrigou a ser texto livre**: dependentes (hoje 3 campos de
  texto livre → tabela própria, sem limite), RG (órgão emissor + data separados), título
  de eleitor (número/zona/seção separados), contatos de emergência (tabela própria).
- **Eliminar perguntas-gambiarra**: "já tem CTPS em PDF?" (Q23) e "consegue emitir Nada
  Consta?" (Q26) deixam de ser perguntas e viram **slots de upload** com tooltip de ajuda.
- Dados de saúde (Q40-43) e cor/raça (Q6): colunas em tabela segregada com acesso restrito
  (uso exclusivo: ficha de emergência / obrigação legal).

## Entidades

### candidato
| Campo | Tipo | Obrig. | Origem (Q#) |
|---|---|---|---|
| id | uuid pk | — | — |
| status | enum(convidado, preenchendo, docs_pendentes, aguardando_assinatura, envio_concluido, em_revisao, aprovado, reprovado_pendencias, expurgado) | ✔ | fluxo |
| aceite_lgpd_em | timestamptz | ✔ | Q1 (consentimento com carimbo de hora) |
| nome_completo | text | ✔ | Q2 |
| data_nascimento | date | ✔ | Q3 |
| sexo | enum(feminino, masculino) | ✔ | Q4 |
| identidade_genero | enum(cisgenero, transgenero, transexual, travesti, genero_fluido, agenero, nao_informar) | ✔ | Q5 |
| cor_raca | enum(branca, preta, parda, amarela, indigena) | ✔* | Q6 (*acesso restrito) |
| nacionalidade | enum(brasileira, estrangeira) | ✔ | Q7 |
| naturalidade_cidade / naturalidade_uf | text / char(2) | ✔ | Q8 (separado) |
| estado_civil | enum(solteiro, casado, uniao_estavel, divorciado, separado, viuvo) | ✔ | Q9 |
| escolaridade | enum(fund_incompleto, fund_completo, medio_incompleto, medio_completo, sup_incompleto, sup_completo, pos_graduacao) | ✔ | Q10 |
| pcd | boolean | ✔ | Q11 (se sim → slot laudo obrigatório) |
| email | citext | ✔ | Q12 |
| celular_whatsapp | text (E.164) | ✔ | Q13 |
| declaracao_veracidade_em | timestamptz | ✔ | Q50 |

### endereco (1:1 candidato)
| Campo | Tipo | Obrig. | Q# |
|---|---|---|---|
| logradouro_numero_complemento | text | ✔ | Q14 |
| bairro | text | ✔ | Q15 |
| cidade | text | ✔ | Q16 |
| uf | char(2) | ✔ | Q17 |
| cep | char(8) | ✔ | Q18 (validar formato; autocompletar via ViaCEP no front) |

### documentos_identificacao (1:1 candidato)
| Campo | Tipo | Obrig. | Q# |
|---|---|---|---|
| rg_numero | text | ✔ | Q19 |
| rg_orgao_emissor | text | ✔ | Q20 (separado) |
| rg_data_expedicao | date | ✔ | Q20 (separado) |
| cpf | char(11) | ✔ | Q21 (validar dígitos) |
| pis_nis_pasep | text | ✔ | Q22 |
| cnh_numero / cnh_categoria | text / text | opcional | Q24 |
| titulo_eleitor_numero / zona / secao | text | ✔ | Q25 (separado) |

*(Q23 "CTPS em PDF?" e Q26 "consegue emitir Nada Consta?" → viram slots de upload com tooltip.)*

### dados_profissionais_bancarios (1:1 candidato)
| Campo | Tipo | Obrig. | Q# |
|---|---|---|---|
| tamanho_calca / tamanho_camisa / tamanho_calcado | text | ✔ | Q27 (separado em 3) |
| banco | text | ✔ | Q28 |
| pix_tipo | enum(cpf, celular, email, aleatoria) | ✔ | Q29 |
| pix_chave | text | ✔ | Q30 (validar coerência com tipo) |

### dependente (N:1 candidato) — estruturado, sem limite de 3
| Campo | Tipo | Obrig. | Q# |
|---|---|---|---|
| nome_completo | text | ✔ | Q31-34 |
| data_nascimento | date | ✔ | Q32-34 (regra: 0-6 → slot cartão vacina; 7-14 → slot declaração escolar) |
| cpf | char(11) | ✔ | obrigatório p/ todos (regra do form) |
| parentesco | enum(conjuge, filho, menor_guarda) | ✔ | Q31 (texto de apoio, Lei 9.250/95 art. 35) |
| deduz_irrf | boolean | ✔ | Q35-36 (por dependente, não em texto livre) |

### vale_transporte (1:1 candidato)
| Campo | Tipo | Obrig. | Q# |
|---|---|---|---|
| optante | boolean | ✔ | Q37 (gera conteúdo do Termo de Opção) |
| cartao_dftrans | text | se optante e já tiver | Q38 |
| trajeto_descricao | text | se optante | Q39 (ida/volta, linhas e valores) |

### ficha_emergencia (1:1 candidato — acesso restrito, LGPD art. 11)
| Campo | Tipo | Obrig. | Q# |
|---|---|---|---|
| tipo_sanguineo | text | opcional | Q40 |
| usa_medicamento_continuo | boolean | ✔ | Q41 |
| medicamentos | text | se sim | Q42 |
| condicoes_medicas | text | ✔ ("Nenhuma") | Q43 |
| orientacao_emergencia | text | opcional | Q49 |

### contato_emergencia (N:1 candidato; mínimo 1)
| Campo | Tipo | Obrig. | Q# |
|---|---|---|---|
| nome_completo | text | ✔ | Q44/Q48 |
| parentesco | text | ✔ | Q45/Q48 |
| telefone_celular | text | ✔ | Q46/Q48 |
| telefone_fixo_endereco | text | opcional | Q47 |
| ordem | smallint | ✔ | contato 1, 2… |

### slot_documento (N:1 candidato) — o coração do "continue de onde parou"
| Campo | Tipo | Notas |
|---|---|---|
| tipo | enum(foto_3x4, rg, cpf_doc, ctps_digital, pis_comprovante, titulo_eleitor_doc, reservista, habilitacao_prof, laudo_pcd, comp_endereco, comp_escolaridade, diplomas, nada_consta_eleitoral, nada_consta_criminal, cert_casamento, cert_nascimento_dep, cartao_vacina_dep, declaracao_escolar_dep, cartao_vt) | catálogo por candidato, gerado pelas regras |
| dependente_id | uuid fk nullable | slots de dependente |
| obrigatorio | boolean | calculado pelas regras condicionais |
| status | enum(pendente, enviado, aprovado, rejeitado, dispensado) | fila de revisão do RH |
| motivo_rejeicao | enum(ilegivel, doc_errado, vencido, incompleto, outro) + texto | notificação automática |
| arquivo_original_key / arquivo_pdf_key | text | chaves no MinIO |
| paginas | smallint | após normalização |
| enviado_em / revisado_em / revisado_por | timestamptz / fk usuario_rh | auditoria |

**Regras de geração de slots (condicionais):**
- `reservista`: obrigatório se sexo = masculino (e idade entre 18 e 45)
- `laudo_pcd`: obrigatório se pcd = true
- `cert_casamento`: se estado_civil ∈ (casado, uniao_estavel)
- `cartao_vacina_dep`: por dependente com idade 0-6
- `declaracao_escolar_dep`: por dependente com idade 7-14
- `cert_nascimento_dep`: por dependente
- `cartao_vt`: se vt.optante = true e cartao_dftrans informado
- `habilitacao_prof`, `diplomas`: opcionais (dispensáveis pelo RH)
- `comp_endereco`: validar emissão ≤ 90 dias (v1.1: OCR da data)

### assinatura (N:1 candidato) — assinatura eletrônica simples
| Campo | Tipo | Notas |
|---|---|---|
| documento | enum(ficha_cadastro, ficha_emergencia, termo_vt) | os 3 gerados pelo sistema |
| pdf_key | text | versão assinada no MinIO |
| hash_sha256 | char(64) | do PDF no momento da assinatura |
| otp_canal | enum(email, sms) | evidência |
| assinado_em / ip / user_agent | timestamptz / inet / text | trilha de evidências (Lei 14.063/2020) |

### acesso_magico (N:1 candidato)
token hash, expira_em, usado_em, revogado — link sem senha; renovável pelo RH.

### evento_auditoria
candidato_id, ator (candidato|rh|sistema), acao, detalhe jsonb, criado_em — trilha completa
(inclusive para comprovar consentimentos e notificações).

### usuario_rh
id, nome, email, senha_hash (login do RH; candidato nunca tem senha).

## Dossiê (PDF único) — ordem de montagem
1. Ficha Cadastro (gerada + assinada) → 2. Ficha de Emergência (gerada + assinada) →
3. Termo de Opção de VT (gerado + assinado) → 4. documentos pessoais → 5. comprovantes/
certidões → 6. dependentes. Slots aprovados apenas; montagem dispara quando todos os
obrigatórios estiverem aprovados.

## Retenção (expurgo MinIO + LGPD)
- Admissão concluída: dossiê final enviado por SMTP ao RH; originais soltos expurgados após N dias (`RETENTION_DAYS`).
- Candidato desistente/reprovado: expurgo total de arquivos + anonimização após M dias.
