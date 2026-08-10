# Módulos do backend — descrição e regras próprias

Carrega quando se trabalha sob `backend/app/`. Saiu do `CLAUDE.md` raiz em
2026-08-09: são descrições de MÓDULO, úteis só quando se mexe neles, e no arquivo
raiz custavam contexto em toda sessão. **As armadilhas de falha silenciosa
continuam no raiz** — aquelas precisam ser lidas antes de se saber onde se está.

- **Telemetria de uso** (`models/telemetria.py`, `services/telemetria.py`,
  `api/telemetria.py`, `frontend/src/telemetria.js`, `rh/TelemetriaRH.jsx` +
  `rh/TelemetriaPessoa.jsx`, v2.24): o que acontece no APARELHO da pessoa —
  erro de JS, fricção, jornada e desempenho. Existe porque o incidente de
  2026-07-29 provou que a telemetria HTTP do servidor é cega: ela registrou
  **200 em tudo** enquanto dois candidatos viam tela branca, porque o
  `TypeError` acontecia no React, DEPOIS da resposta.
  - **NÃO é a auditoria.** `EventoAuditoria` = "quem fez o quê", prova de ato,
    append-only, nunca expurgada. `EventoTelemetria` = "como foi usar", dado de
    produto, descartável, retenção configurável (padrão 1 ano). Não fundir: daria
    dado de produto com peso de prova jurídica, e prova jurídica que se apaga.
  - **`registrar_eventos` é a porta única e NUNCA levanta** (mesma regra do
    `avisar()`). Mas o silêncio já cobrou: as FKs de candidato/talento não
    resolviam sem o import dos modelos em `models/telemetria.py`, e TODA
    gravação falhava sem sinal nenhum. Por isso o log é `exception` com stack, e
    o teste afirma que a gravação REALMENTE grava — não só que não levantou.
  - **A rota de coleta é PÚBLICA** (o candidato não tem login): rate limit por
    IP, teto de 50 eventos por lote e corte de cada campo. Excesso é descartado
    em silêncio — nem 429 —, porque telemetria não pode virar canal de erro para
    quem está usando. `origem="rh"` só é aceita na rota autenticada.
  - **IDENTIDADE NA ROTA PÚBLICA SÓ COM PROVA** (v2.36): o candidato vem pelo
    token do link mágico (resolvido no servidor) e o talento pelo
    `upload_token` do cadastro (`talento_do_upload_token`, assinado e com TTL)
    — **nunca** por um id cru no corpo. Um `talento_id` sem prova deixaria
    qualquer um pendurar eventos na jornada de outra pessoa, e o RH leria
    aquilo como o comportamento dela: dado de produto falso é pior que dado
    nenhum, porque parece verdadeiro. Sem prova, o evento é gravado SEM
    vínculo — some a identificação, não o registro.
  - **A tela geral mostra a PESSOA** (v2.36, `anexar_pessoa`): telemetria
    identificada que não diz de quem é o evento vira estatística — o caso de
    uso é "a pessoa ligou dizendo que não consegue". Nome em LOTE (3 consultas
    no total: eventos + candidatos + talentos), nunca uma por linha. Quem não
    se identificou continua ANÔNIMO.
  - **Análise de caminho é EXPORT, não biblioteca no servidor** (v2.36,
    `jornada_csv` + `/rh/telemetria/jornada.csv`): CSV cronológico com
    `user_id,event,timestamp` nas três primeiras colunas (formato do
    retentioneering e afins), `;` + BOM como todo CSV do projeto (`sep=';'` no
    pandas). Trazer pandas/plotly para a imagem por uma pergunta ocasional não
    se paga. O download vai para a AUDITORIA (leva nome de gente real, mesma
    regra do log da v2.29) e o corte no teto é ANUNCIADO na tela — corte
    silencioso faria analisar um pedaço achando que é o período inteiro.
  - **LGPD por desenho, na ENTRADA**: nada do que a pessoa digita; IP truncado
    (`ip_prefixo`); e **token do link mágico mascarado** (`mascarar_pagina`) —
    `/c/{token}` é CREDENCIAL, e telemetria é feita para ser lida e exportada.
    Testar só a função de mascarar não basta: o teste tem que provar que ela é
    aplicada na gravação (lacuna pega por mutação).
  - **Resumo AGRUPA**: erros por mensagem (300 ocorrências do mesmo erro são UM
    problema) e páginas lentas por **mediana**, não média — um caso de 40s
    distorceria a média e faria parecer que tudo está lento.
  - Expurgo mora em `workers/expurgo.py` (o compose já o agenda; um cron a mais
    seria mais uma peça para esquecer de subir) e NÃO passa pela lixeira —
    milhões de linhas de uso afogariam o que ela existe para proteger.
- **Alertas de telemetria** (`models/alerta.py`, `services/alertas.py`,
  `workers/alertas_telemetria.py`, `rh/AlertasTelemetria.jsx`, v2.25): a
  telemetria da v2.24 é PASSIVA (alguém tem que abrir a aba); os alertas a
  tornam ativa. Quatro tipos — `erro_novo`, `erro_volume`, `friccao_pico`,
  `lentidao` — com regras EDITÁVEIS na tela (o Bruno pediu "customizar mais
  cenários"; limiar chumbado exigiria deploy a cada ajuste).
  - **Entrega pela MATRIZ** (`avisar_modelo`, evento `telemetria_alerta`), nunca
    por caminho paralelo — é a regra da v2.21 para e-mail novo.
  - **Silêncio é recurso escasso**: dedup por assinatura + `silencio_min` (mínimo
    de 5, nunca zero). Alerta que vira enxurrada deixa de ser lido, e alerta
    ignorado é PIOR que alerta nenhum — dá falsa sensação de cobertura.
  - **`erro_novo` usa `_ja_visto_alguma_vez`, sem janela**: "novo" é para
    sempre. Se dependesse só do silêncio, um erro conhecido voltaria a ser
    anunciado como novidade de hora em hora. (O teste que não cobria isso
    passava com a checagem removida — lacuna achada por mutação.)
  - **`enviar=False` (botão "o que dispararia agora?") NÃO grava histórico**:
    testar não pode marcar o erro como já visto e impedir o alerta real.
  - **Lentidão por MEDIANA e mínimo de 3 amostras**: uma medição de 40s é
    alguém no elevador, não problema do sistema.
  - **Worker próprio a cada 15 min** (compose E `portainer-stack.yml` — sem os
    dois, não roda em produção). NÃO embutir no `expurgo`, que roda a cada 24h:
    o alerta chegaria um dia depois. O worker checa `has_table` antes de rodar —
    ele sobe em paralelo com a API, que é quem aplica as migrations, e registrar
    ERRO a cada deploy ensinaria a ignorar o log.
  - **Histórico mostra quando o alerta saiu para NINGUÉM** (0 destinatários):
    sem isso, caixa silenciosa seria ambígua — "sem problema" e "quebrou"
    pareceriam iguais.
- **Camada de IA de texto** (`services/ia_texto.py`, v2.00): CADEIA de
  provedores — **OpenRouter (principal) → Groq (reserva)**, chaves na config
  dinâmica (nunca em log, nunca devolvidas ao painel). `gerar_texto`/
  `gerar_json` são as únicas portas de entrada; trocar/acrescentar provedor é
  mexer SÓ neste arquivo (lista `PROVEDORES`).
  **ERRO TRANSITÓRIO ≠ PERMANENTE — armadilha que derrubou 112 de 131
  análises em 2026-07-28**: antes, `except Exception` convertia um HTTP 429
  (cota, resolve em segundos) no MESMO erro de um 401 (chave inválida,
  permanente), e o chamador desistia de tudo. Agora: `CotaExcedidaError`
  (transitório, com `espera_s` vindo do header `Retry-After`) vs.
  `IndisponivelError` (permanente). **Nunca** volte a tratar os dois igual.
  `esperar_cota=True` é só para o WORKER (ninguém esperando na tela): dorme o
  tempo pedido e retoma, em vez de trocar de provedor na hora.
  Testar chave usa `so_provedor=` — testar a chave da Groq NÃO pode mandá-la
  ao OpenRouter.
  **MODELO `:free` do OpenRouter É VOLÁTIL — some/renomeia sem aviso
  (mordeu em 2026-07-28)**: `meta-llama/llama-3.3-70b-instruct:free` deixou de
  existir e TODO teste de chave virava um falso "recusou a chave" — a chave
  estava certa, o modelo é que sumiu (404). Duas defesas: (1) cada provedor tem
  uma LISTA de modelos em ordem (`modelos_padrao`), tentados um a um —
  `IndisponivelError` de um modelo (404/400) cai no PRÓXIMO MODELO do mesmo
  provedor; só `chave_recusada` (401/403) pula o provedor inteiro (a chave é do
  provedor, nenhum modelo dele passaria). (2) A lista é editável no painel
  (Config → IA de texto, chaves `openrouter_modelos`/`groq_modelos` na config
  dinâmica; `_modelos_do_provedor` lê o override ou cai no padrão) — quando um id
  sumir de novo, o RH corrige em segundos, sem deploy. Padrões que suportam
  `response_format: json_object` (exigido pelo Match via `gerar_json`):
  `google/gemma-4-31b-it:free` → `openai/gpt-oss-20b:free`. **A mensagem de erro
  do painel DISTINGUE os motivos** (`IndisponivelError.codigo`): "recusou a
  chave" SÓ para 401/403; 404 diz "modelo indisponível, confira os modelos" +
  dica da política de dados do OpenRouter (modelos free às vezes exigem liberar
  em openrouter.ai/settings/privacy). NÃO volte ao genérico "não respondeu ou
  recusou a chave" — ele escondia a causa real.
- **Minutário de Mensagens** (`models/minutario.py`, `api/minutario.py`,
  `MinutarioRH.jsx`, v1.98): modelos de mensagem (CRUD, reusa o catálogo
  `Tag` do mini-CRM) + composição assistida por IA a partir de campos da
  VAGA. **`ComporMensagemIn` não tem NENHUM campo de candidato** (nome,
  telefone, e-mail, CPF) — é garantia estrutural, não checagem em runtime; a
  substituição de `{{marcadores}}` no texto acontece DEPOIS, no servidor.
  Texto sempre volta editável — nunca envia sozinho. Envio por copiar +
  link `wa.me`, sem integração com a API oficial do WhatsApp. **Armadilha
  pega por teste** (`test_minutario_prompt.py`): o fallback de "mensagem
  genérica" tem que disparar por falta de CONTEÚDO (campos da vaga ou modelo
  de referência) — o campo `tom` é só estilo e não pode, sozinho, evitar o
  fallback (senão o RH preenche só o tom e a IA recebe um prompt sem
  instrução nenhuma do que escrever).
- **Match de Vagas** (`models/vaga.py`, `api/vagas.py`,
  `services/match_vagas.py`, `services/curriculo_texto.py`,
  `MatchVagasRH.jsx`, v1.99): RH cadastra a vaga, o sistema ranqueia os
  talentos do Banco de Talentos por aderência — filtro estruturado local
  (cargo/região, grátis) primeiro, currículo lido por IA depois. **A IA
  nunca decide sozinha** — devolve nota + justificativa em JSON, o RH
  convoca. **Currículo é ENTRADA HOSTIL** (achado do Bruno, não estava no
  plano original): é upload público de gente desconhecida cujo texto vai
  direto para dentro de um prompt — ataque real de mercado ("white text
  resume injection": texto em fonte branca/corpo 1 instruindo a IA a dar
  nota máxima). É falha SILENCIOSA (ranking adulterado parece igual a um
  legítimo) e questão de justiça do processo seletivo, não só segurança.
  5 camadas em `anti_prompt_injection.py` (delimitador aleatório, saída
  estruturada, teto de tamanho, detecção+alerta visível, texto invisível
  vira sinal) — currículo suspeito aparece marcado "⚠️ suspeito" no
  ranking, NUNCA filtrado calado. **Minimização** (`curriculo_texto.py`):
  CPF/RG/telefone/e-mail/CEP removidos do texto ANTES do envio à IA — nome
  fica (necessário para o RH identificar o resultado; a Groq não tem
  cláusula de retenção zero, decisão consciente do Bruno, então a
  minimização é a proteção que resta). Extração de texto reaproveita o
  OCR/leitura já existentes (Mistral com fallback Tesseract/pypdf; DOC/DOCX
  via LibreOffice+PDF, mesmo padrão de `normalizacao.py::_word_para_pdf`) —
  currículo ilegível NUNCA gera nota inventada. Base legal: o termo do
  Banco de Talentos (`Talentos.jsx`) já cobre "tratar para fins de
  recrutamento" — a triagem por IA é uso primário, não secundário; o
  formulário público ganhou uma frase de transparência (não é condição de
  aceite, o consentimento já existente basta).
- **Match de Vagas — desenho ASSÍNCRONO e persistido** (v2.00,
  `models/match.py`, `services/curriculo_indexacao.py`, `workers/match.py`):
  reescrito depois de um incidente real — 131 talentos, 18 analisados; 67s
  depois, 2. Quatro regras que NÃO devem ser revertidas:
  1. **O ranqueamento NUNCA é síncrono.** `POST /ranquear` devolve 202 +
     `processamento_id` e enfileira; o worker processa. O RH continua usando
     o sistema, e o nginx não corta (60s).
  2. **Texto do currículo é extraído UMA VEZ, no upload**
     (`CurriculoTexto`), já minimizado. O currículo não muda depois de
     enviado — reler 131 a cada clique era desperdício e garantia de
     timeout. Backfill em `/rh/curriculos/indexar` cobre o histórico.
  3. **Análise é reaproveitada por (vaga, talento)** — clicar de novo é
     praticamente grátis. `reanalisar=True` força refazer. Cuidado: há
     `UNIQUE(vaga_id, talento_id)`, então reanalisar precisa ATUALIZAR o
     registro existente, nunca inserir outro (bug pego por teste).
  4. **Ninguém some em silêncio** (`ResultadoAnalise`): sem currículo,
     currículo ilegível, aguardando IA e erro são resultados GRAVADOS e
     exibidos com o motivo — não ausência. Cota estourada marca os
     pendentes como `ia_indisponivel` para retomar na próxima rodada, em vez
     de desistir do lote.
  O status do talento (`novo → em_analise`) muda em **ato de atenção do RH**
  (abrir currículo ou anotações, ver `talentos.py::marcar_em_analise`) e
  deliberadamente **NÃO** no ranqueamento em massa — marcar 131 de uma vez
  recriaria o problema de "todo mundo com o mesmo rótulo".
- **Provas por cargo** (`models/prova.py`, `api/provas.py`, `ProvasRH.jsx`,
  `ProvaApp.jsx`): banco de provas CONFIGURÁVEL pelo RH (diferente do DISC/
  situacional, gabarito fixo no código). Questões objetivas (opções {id,texto} +
  gabarito) e discursivas. Objetivas corrigidas AUTOMÁTICAS (pesos); discursivas
  o RH pontua 0-100; nota_final combina as duas por peso. Aplicação por link
  avulso `/p/{token}` (participante só informa o nome, timer server-side,
  telemetria — igual `/t/`); o participante NÃO vê a nota (seleção). GABARITO
  nunca vai ao público (`_questao_publica` remove; testado). **Armadilha de
  rotas**: as rotas de aplicação são `/rh/provas-aplicacoes` (hífen!) e NÃO
  `/rh/provas/aplicacoes` — senão o `aplicacoes` vira `{prova_id}` UUID e dá 422.
  A correção do RH usa o DashPlanilha. Link pode ir a um talento (`LinkProva.talento_id`).
  **Aleatorização (v1.89):** `ProvaCargo.embaralhar` embaralha ordem de questões
  E opções por participante, com `AplicacaoProva.seed` (gerada no `iniciar`,
  ESTÁVEL — recarregar não reembaralha). `_publicas_ordenadas` permuta com
  `random.Random(seed)` (sub-seed `seed+i` por questão p/ as opções não
  embaralharem todas igual). SEGURO porque a correção casa por ID da opção
  (`escolha == gabarito`), não por posição — embaralhar a exibição NUNCA muda a
  nota (testado). **Explicação (v1.89):** `QuestaoProva.explicacao` (opcional) +
  `ProvaCargo.mostrar_explicacao`. A rota `/p/{token}/a/{aid}/revisao` devolve
  gabarito+explicação ao PARTICIPANTE só se a flag estiver ligada E a aplicação
  concluída — senão 403 (o gabarito NÃO vaza em prova de seleção). NUNCA devolve
  nota (segue seleção). **Duplicar (v1.89):** `/rh/provas/{id}/duplicar` (prova
  inteira, nasce "(cópia)" sem links) e `/rh/provas/{id}/questoes/{qid}/duplicar`.
  **Banco de itens (Fase 2, v1.90):** `ItemBanco` (`models/prova.py`) é a questão
  REUTILIZÁVEL — existe SOZINHA (não é `QuestaoProva`), catalogada por `cargo`
  (string livre), `senioridade` (lista FIXA `SENIORIDADES`: qualquer/junior/
  pleno/senior — 'qualquer' serve a todos e o filtro casa nível OU 'qualquer') e
  `tags` (lista de strings do PRÓPRIO item — conteúdo tipo "NR-35"; NÃO o
  `crm_tag`, que é sobre PESSOAS — domínios separados de propósito). Migração
  ADITIVA (`item_banco`): NÃO toca `prova_cargo`/`questao_prova`, então as provas
  existentes NÃO são desmontadas. **Montar prova COPIA (snapshot):**
  `/rh/provas/{id}/adicionar-do-banco` (manual `item_ids` OU sorteio
  `quantidade`+filtros) cria `QuestaoProva` a partir do item — editar/excluir o
  item DEPOIS não muda prova montada nem aplicação em curso (testado). `/promover`
  copia questão de prova → banco (original permanece). Só ACRESCENTA ao final da
  prova, nunca remove. Front: aba "🗃️ Banco de itens" (`BancoItens.jsx`, CRUD) +
  `MontarDoBanco` no editor + botão "→ banco" por questão.
- **Entrevistas** (`models/entrevista.py`, `services/entrevistas.py`,
  `api/entrevistas.py`, `rh/EntrevistasRH.jsx` + `rh/FichaEntrevista.jsx` +
  `rh/EntrevistasDaVaga.jsx` + `rh/EntrevistasDaPessoa.jsx`, v2.64): o degrau
  entre "o RH olhou o currículo" e "o RH mandou o convite". Desenho completo em
  `docs/planejamento/12-modulo-de-entrevistas.md`; execução em `12b-…`.
  - **UMA tabela, DUAS naturezas** (`tipo`): triagem = checagem de viabilidade
    (SEM nota, competência ou âncora — é outra coisa, não entrevista curta);
    entrevista = avaliação ancorada (4 competências, escala 1–4 **sem ponto
    médio**, justificativa obrigatória por nota). O 422 **NOMEIA** a competência
    que falta.
  - **⚠️ O instrumento MUDOU DE FONTE na v2.66** (§ 14.1): até a v2.65 vivia em
    constante de módulo; agora é o **ROTEIRO no banco** (`roteiro_entrevista`),
    semeado pela migration `a1c3e5b7d9f2` a partir daquela constante. Editar
    `COMPETENCIAS` em `services/entrevistas.py` **não muda mais nada em
    produção** — muda só o que um banco novo recebe. Quem edita o instrumento é
    o RH, pela tela (Configurações → Roteiros de entrevista). **O CONTRATO não
    mudou**: o front lê `GET /rh/entrevistas/formulario` e NÃO duplica texto —
    `test_entrevistas.py` e `test_roteiros_entrevista.py` varrem o JSX e
    reprovam a duplicação.
  - **Roteiro nasce RASCUNHO e só publicado se usa** (v2.66): é o que sustenta o
    argumento do § 6 — a defesa não é "existe um roteiro", é *"o roteiro foi
    aprovado ANTES de ser usado"*. Editar publicado gera a versão SEGUINTE e o
    devolve a rascunho. A `Entrevista` guarda `roteiro_id` **e**
    `roteiro_snapshot` (mesma razão do `vaga_titulo`): ler do roteiro vivo
    mostraria o texto de HOJE numa avaliação de meses atrás. Herança
    `cargo+senioridade → cargo → padrão`, por `normalizar_cargo`; cargo sem
    roteiro cai no padrão, **nunca em erro**. O `padrao=True` não se apaga nem
    se arquiva — e `resolver_roteiro` ainda tem rede de segurança se ele sumir.
  - **Convite e lembrete** (v2.66, § 14.4, `services/calendario.py` +
    `services/entrevista_convite.py`): `modalidade` decide `local` ×
    `link_reuniao`; **online sem link não se marca**. O `.ics` tem UID ESTÁVEL
    por entrevista + `SEQUENCE` que cresce (é o que faz o Outlook ATUALIZAR em
    vez de criar um segundo), `METHOD:CANCEL` no cancelamento e
    `TZID=America/Sao_Paulo` (o container roda em UTC). Sem e-mail da pessoa, o
    lembrete fica desligado **com o motivo na tela**. O worker mora dentro do
    `avisar_vencimentos` — que precisou ser acrescentado ao
    `portainer-stack.yml`, onde faltava.
  - **DUAS FKs de pessoa** (`talento_id`/`candidato_id`), padrão do mini-CRM.
    Com FK única a entrevista feita com o talento SUMIRIA da ficha do candidato
    após o `converter()` — que é quando ela mais importa. Coberto por mutação.
  - **`vaga_id` é `ondelete=SET NULL` + snapshot `vaga_titulo`**: o
    `DELETE /rh/vagas/{id}` é delete FÍSICO e não passa pela lixeira. A
    entrevista sobrevive à vaga, com o nome dela. (Recomendação em aberto:
    passar a exclusão de vaga pela lixeira.)
  - **O sistema PERGUNTA, nunca conclui**: passou da data e ninguém preencheu →
    vira PENDÊNCIA que cobra, **jamais** `nao_veio` automático. Silêncio não é
    falta (a lição do `00:00` no import de ponto). Há teste por mutação.
  - **ARQUIVA, NÃO APAGA** (`workers/expurgo.py::arquivar_entrevistas`, 180
    dias configuráveis): sai da vista e das métricas, o registro permanece e é
    consultável com `?incluir_arquivadas=true`. Trocar por `db.delete` é
    reprovação imediata. **Retenção 0 = indeterminado** (não arquiva nada) —
    trocar `if dias <= 0` por `is not None` viraria "arquivar tudo hoje".
    **Quem virou colaborador fica FORA do prazo**: é parte do vínculo.
  - **Ao concluir, escreve `Anotacao` no mini-CRM** — a entrevista não *é* uma
    anotação (o valor está na nota ancorada comparável), mas o histórico da
    pessoa fica num lugar só (padrão de `talentos.py::mudar_status`).
  - **Documentos (v2.67)**: os três — ficha de entrevista, ficha de triagem e
    roteiro publicado — vivem em `services/entrevista_pdf.py` e entram no
    `documentos_catalogo.py` como família `Origem.entrevista`. A ficha é
    ASSINÁVEL pelo RH que conduziu (`senha_sessao_rh`), em tabela própria
    (`models/assinatura_entrevista.py`) **para não vazar no dossiê** — ver a
    armadilha do `dossie.py` acima. Ficha incompleta e roteiro em rascunho não
    geram documento; entrevista ARQUIVADA continua gerando (arquivar não apaga).
  - **Triagem editável (v2.67)**: entra no mesmo catálogo com `tipo=triagem` e
    **continua sem nota, competência ou âncora** — `validar_roteiro_triagem`
    recusa NOMEANDO o campo proibido. **Um padrão por TIPO**: listagem,
    métricas, `tornar_padrao` e `resolver_roteiro` são todos recortados por
    tipo, senão eleger padrão de entrevista apagaria o fundo de herança da
    triagem, em silêncio.
  - **O remetente de recrutamento vale no M365, com a metade do tenant**
    (v2.68, § 16.1): `email_recrutamento` é editável em Configurações → E-mail e
    integrações e vai ao `From` do Graph. O M365 só o aceita com **`Send As`**
    liberado no admin do tenant; sem isso o convite **sai da caixa conectada e a
    tela avisa** o que falta. O e-mail nunca deixa de sair.
  - **Roteiro FIXO, sem campo de "outras perguntas"** (Lei 9.029/95): campo de
    pergunta livre é risco jurídico; roteiro pré-aprovado é defesa da empresa. O
    `observacao` é livre; o ROTEIRO não. **Seguro-desemprego** entra na triagem
    e **nunca** é critério de exclusão — a tela diz isso.
- **Mini-CRM — anotações e tags no ciclo de vida** (`models/crm.py`,
  `services/crm.py`, `api/crm.py`, `frontend/src/rh/MemoriaPessoa.jsx`): memória
  do RH sobre a PESSOA que atravessa talento → candidato → efetivo → desligado.
  A pessoa vive em DOIS registros (`talento` e `candidato`, ligados por
  `talento.candidato_id`; o talento NÃO some ao converter). Por isso `Anotacao` e
  `PessoaTag` têm DUAS FKs opcionais (`talento_id`/`candidato_id`), uma
  preenchida por registro. A memória "segue a pessoa" SEM cópia: `escopo_pessoa`
  descobre o par (talento↔candidato) e as consultas usam OR nas duas chaves
  (`_predicado`) — nada é movido no `converter`, o elo já está na FK. **Autor**:
  grava `autor_id` (FK UsuarioRH) E `autor_nome` (SNAPSHOT — não some se o
  usuário for removido), via `requer_rh`. **Tags**: catálogo com CRUD
  (Configurações → Tags), `crm_pessoa_tag` N:N idempotente; no dash de Talentos a
  coluna/filtro de tags vem do dump, carregado EM LOTE (`tags_por_talento`, sem
  N+1, já unindo talento+candidato). Anexo por anotação no MinIO (prefixo
  `crm/anotacoes/{id}/`). Rotas `/rh/crm/...` restritas ao RH; a paramétrica
  `/tags/{tag_id}` fica por ÚLTIMO (senão captura `/pessoa`, `/anotacoes`). UI:
  `MemoriaPessoa.jsx` reusado no painel `linhaExpandida` do dash de Talentos e na
  seção recolhível do `Detalhe.jsx`.
- **Banco de Talentos**: form público (`Talentos.jsx`, rota `/banco-de-talentos`)
  = wizard de 3 passos que substituiu o Microsoft Forms. **Enviar teste avulso**:
  `POST /rh/talentos/{id}/enviar-teste` cria um `LinkTestagem` dedicado
  (`talento_id`+`email_destino`) e manda o link `/t/` ao e-mail — SEM converter o
  talento; o resultado volta ao dash (`teste_status` no `_dump`, via
  `_resumo_teste_talento`). Ao mexer no form público, ATUALIZE o teste E2E
  `portal.spec.js` (o de 3 passos) — mudou de campo único p/ chips.
  **Importar da planilha do Forms**: `POST /rh/talentos/importar-planilha` lê o
  .xlsx do Microsoft Forms (colunas casadas pelo cabeçalho; cargos/regiões
  separados por `;`; "Tanto faz…"→`tanto_faz`; Sim/Não→bool; "Li e concordo"→
  carimbo LGPD). IDEMPOTENTE: pula quem já existe (por e-mail; ou nome+telefone
  sem e-mail), inclusive duplicados DENTRO da planilha. Reusa `_ler_abas` de
  `incidencia_beneficios.py`. `models/talento.py` tem
  `cargos_interesse`/`regioes` (JSON, múltipla escolha) além do `cargo_interesse`
  string legado, que é SEMPRE sincronizado com o 1º cargo (o `converter`
  talento→candidato usa a string). Consentimento LGPD é obrigatório no cadastro
  (422 `consentimento_obrigatorio`). **Currículo é OPCIONAL** e guardado ORIGINAL
  no MinIO (`talentos/{id}/curriculo.{ext}`) — sem conversão (não há OCR aqui);
  RH baixa como veio. Upload sem login: o `POST /talentos` devolve um
  `upload_token` (itsdangerous, TTL 30min) que autoriza `POST
  /talentos/{id}/curriculo` — amarra o arquivo ao cadastro sem furar o honeypot.
  Formatos: pdf/jpg/png/heic/webp/doc/docx, ≤10MB. Cargos/regiões do formulário =
  lista fixa do Forms em `talentos.py` (`CARGOS_SUGERIDOS`/`REGIOES_SUGERIDAS`).
- **Reembolso-Creche (módulo)**: elegibilidade é POR POSTO
  (`PostoServico.da_direito_creche` + `valor_reembolso_creche`); intermitente não
  vê o benefício (o bloco só aparece se o posto dá direito) e passa a ver sozinho
  ao virar efetivo em posto elegível. O link público (`/creche`, `creche_publico.py`)
  NUNCA revela se o CPF é da base: `/creche/iniciar` responde IDÊNTICO para
  base-com-email, base-sem-email e fora-da-base. Quem não tem e-mail passa pela
  **KBA** (`app/services/kba.py`, a MESMA da entrada de admissão — extraída p/
  serviço compartilhado) antes de cadastrar/atualizar o e-mail e receber o 2FA.
  A **assinatura do requerimento** usa o multi-signatário: roteiro colaborador→RH
  criado e disparado no `ativar_beneficio` (`criar_roteiro_creche`), com
  `origem="creche_requerimento"` na `solicitacao_assinatura` — o colaborador
  assina na PRÓPRIA sessão de creche (já 2FA; etapa `candidato` SEM `assinatura_id`,
  por isso não aparece no wizard), o RH contra-assina pela fila. Na consolidação,
  `_consolidar_pdf_final` desvia p/ `gerar_requerimento_creche(vistos=...)` (mantém
  o layout oficial do DOCX e empilha os blocos+manifesto por cima — decisão do
  Bruno: manter o PDF gerado, não virar modelo de texto). Datas dos PDFs de creche
  são CENTRALIZADAS. RH abre cada doc de criança individualmente
  (`/rh/creche/.../crianca/{id}/documento/{tipo}`, serve do MinIO com Content-Type
  pela extensão — pode ser imagem, não só PDF). **Decisões do RH sobre o
  levantamento** (v1.66/v1.67): além de Aprovar (`ativar_beneficio`, que é o
  "deferir") e Indeferir (terminal, `motivo_indeferimento`), há **Devolver**
  (`/levantamentos/{id}/devolver`): status volta a `levantamento` — o que reabre
  a edição no link público (reusa o gate `editavel`, sem estado novo) e permite
  reenviar — com `motivo_devolucao` VISÍVEL ao colaborador (no CrecheLink) e
  distinto do `motivo_indeferimento`; devolver LIMPA `enviado_em`/
  `dados_conferidos_em` e anula um indeferimento anterior. **"Não faço jus"**
  (status `sem_direito_declarado` + `sem_direito_em/por`): o colaborador declara
  no link (`/creche/sessao/{token}/sem-direito`, rastro "colaborador") OU o RH
  marca pelo painel (`/rh/creche/colaboradores/{id}/sem-direito`, cria o
  benefício se não existir, recusa 409 se já estiver `ativo`) — some da fila de
  ação mas fica no relatório (filtro de status no dash) para provar que o
  elegível foi consultado e NÃO pediu. **"Mais filhos" NÃO virou 1:N** (v1.79):
  o modelo é 1 benefício : N crianças, então `/reabrir` aceita o benefício ATIVO
  e o colaborador ACRESCENTA a criança (botão "➕ Incluir criança"). Decisão do
  Bruno: evita largar o `candidato_id unique=True` e mexer em assinatura/dossiê.
  Reabrir um ativo o tira do pagamento até reaprovar — o e-mail avisa isso.
  **Comunicação de estado + saídas (v1.73-75, auditoria):** TODA transição de
  decisão avisa o colaborador por e-mail (`_email_*`: ativar/repactuação/devolver/
  indeferir/suspensão). O gate serve importados do Tirvu (sem ficha): a KBA usa
  dados IMUTÁVEIS NATIVOS do `Candidato` (nascimento+sobrenome), não as fichas.
  RH destrava quem não entra via `/reenviar-link` (corrige e-mail + reenvia
  código). `AposEnvio` (CrecheLink) tem texto honesto por StatusBeneficio.
  Saídas: `/reabrir` (indeferido/sem_direito → levantamento), `/suspender`
  (encerrar:bool, 409 se não-ativo). **Desligar colaborador encerra o benefício
  ativo** (`encerrar_creche_no_desligamento`). Guards de status em toda
  transição. Flags no dump: `aguardando_correcao`, `reenviado_apos_correcao`,
  `revisar_idade` (ativo sem criança na idade = risco de glosa). Métricas
  (`/rh/metricas`) contam só `situacao IS NULL`, não a base inteira.
  **Devolução manda LINK DIRETO, sem 2FA** (v1.82, pedido do Bruno): quem foi
  devolvido já validou o e-mail alguma vez, e refazer o código só para corrigir
  um dado faz a correção não voltar. `emitir_acesso_devolucao` (creche_publico)
  cria um `AcessoCreche` já `confirmado_em`, TTL de 7 dias, e **invalida os
  acessos vivos daquele benefício** — devolver de novo mata o link anterior. O
  front lê `?t=<token>` em `/creche`, entra direto na sessão e LIMPA a URL
  (`history.replaceState`); link vencido cai na tela de CPF, não em tela morta.
  Contenção: o token dá acesso a UM benefício, e `add_crianca`/`enviar` recusam
  409 fora de `levantamento` — link vazado após a aprovação não edita nada. A
  emissão fica na auditoria (`creche_acesso_direto_emitido`), NUNCA o token.
  **Relatório "Não conseguiram acessar"** (feedback 2026-07-27): o gate público
  responde IGUAL para todos (anti-enumeração), então o RH não sabia se um CPF
  estava mesmo fora da base ou se era bug. `/creche/iniciar` agora AUDITA o
  resultado sem vazar ao usuário: `creche_iniciar_sem_match` (CPF não casou —
  fora da base OU cadastrado errado/sem 11 dígitos) e `creche_iniciar_sem_email`
  (casou mas sem e-mail → foi p/ KBA e pode ter travado; grava nome+situação). O
  CPF completo vai no `detalhe` de propósito (auditoria é só do RH). Relatório em
  `/rh/creche/tentativas-sem-acesso` (agrega por CPF) + aba na tela de Creche. NÃO
  é o casamento por máscara que falha — a query casa `IN [com_máscara, só_dígitos]`
  (testado); a causa real é cadastro sem e-mail ou CPF errado/ausente.
- **Cadastro de Desenvolvimento** (Onda B, v1.83 — `models/desenvolvimento.py`,
  `api/desenvolvimento.py`, `api/portal.py`, `rh/DesenvolvimentoRH.jsx`): cursos,
  certificações e reciclagens do colaborador ao longo do vínculo. A tese é *a
  admissão é o começo do cadastro, não o fim*. **Brigadista NÃO é módulo — é uma
  CONSULTA** (`/rh/desenvolvimento/brigadistas`): registros de tipo `critico`
  com validade vencendo. O que separa o certificado de brigada do curso de Excel
  é `exige_validade` + `critico`, não o tipo em si. **Herança do prazo em 3
  níveis: posto > cargo > tipo** (`meses_validade_de`) — o mais específico vence.
  A validade é RECALCULADA e PERSISTIDA na validação do RH: mudar o prazo depois
  não altera certificado já emitido. **Documento crítico NUNCA entra em
  aprovação em lote** (`pode_aprovar_em_lote`) e o lote DIZ quem barrou, com
  nome e motivo — filtrar em silêncio faria o RH achar que aprovou o que não
  aprovou. Fila com filtro server-side + DashPlanilha por cima (são ~7.200
  arquivos em 3 anos). Ciclo completo: worker `avisar_vencimentos` (90 dias
  antes, anti-spam por auditoria, avisa colaborador + líder via matriz) →
  portal `/meu` → fila do RH → dash de brigada → `matricula_reciclagem.montar`
  (rascunho para conferir) → envio com `dossie_reciclagem.gerar` (1 PDF por
  pessoa, tudo em A4). Incompleto **bloqueia** o envio dizendo quem e o quê.
- **Gestão de Desempenho** (Onda C, v1.84 — `models/desempenho.py`,
  `services/desempenho.py`, `api/desempenho.py`, `rh/DesempenhoRH.jsx`,
  `rh/AvaliacoesRH.jsx`, `rh/FormularioAvaliacao.jsx`): o instrumento é a
  cartilha `docs/Cartilha do Avaliador e Formulário, de 17-06-2026.pdf`, que já
  rodava no Microsoft Forms — **as escalas, os 7 indicadores, as 8 competências
  e as 5 recomendações estão em `services/desempenho.py` palavra por palavra;
  mudá-los muda o instrumento oficial do RH**. O front NÃO duplica esses textos:
  pega em `/rh/desempenho/formulario`.
  **Fatos Observados vêm ANTES do formulário** e rodam sozinhos — são o
  antídoto do efeito de recência (a cartilha, pág. 3, exige fato observável em
  vez de rótulo). Ao abrir uma avaliação, os fatos do período aparecem ao lado;
  ao enviá-la, ficam vinculados (`avaliacao_id`) e viram imutáveis.
  **O colaborador vê os fatos registrados sobre ele** (portal `/meu`), mas
  **nunca o autor** — expor o nome viraria queda de braço entre colega e líder.
  `visivel_em` adia a exibição até a conversa, sem esconder para sempre.
  **Máquina de estados que NÃO deixa pular o feedback presencial**: rascunho →
  preenchida → feedback_dado → manifestada → homologada. Homologar direto de
  `preenchida` é 409: a cartilha (pág. 5) manda conversar, então o sistema
  exige. A **manifestação do colaborador** (seção 9) tem prazo de
  `PRAZO_MANIFESTACAO_D` (7d) — sem prazo o direito de resposta seria letra
  morta, bastando homologar antes de a pessoa ler; passado o prazo, `forcar`
  libera e fica na auditoria.
  **Anonimato**: horizontal é agregado e o avaliador NUNCA é revelado ao
  avaliado; vertical é identificado (é o líder da conversa). O `radar()`
  SUPRIME o horizontal com menos de `MINIMO_HORIZONTAL` (2) respondentes —
  agregado de um é o individual com outro nome.
  **Calibração**: `desvio_do_avaliador()` compara a média dele com a dos
  DEMAIS (excluir as próprias avaliações é essencial — com poucos avaliadores
  ele puxaria a média e mascararia o desvio) e devolve "mais generoso"/"mais
  rigoroso"/"alinhado" a partir de 0,3 numa escala de 1 a 4. **INFORMA o
  homologador, nunca altera nota**: normalizar com N pequeno é ruído, e
  distribuição forçada foi VETADA. `media_competencias` ignora N/A em vez de
  contá-lo como zero (o item não se aplica ao cargo; zerar puniria o avaliado).
  Radar em SVG puro (`RadarCompetencias.jsx`), sem biblioteca — 8 pontos numa
  escala de 1 a 4 não justificam dependência.
  **Import de ponto do Tirvu** (`services/import_ponto.py`, v1.85): upload do
  .xlsx (RH › Fatos Observados › Importar ponto), agregado por pessoa/período em
  `ResumoPonto`, e mostrado como CONTEXTO ao lado do formulário — **nunca nota**
  (decisão do Bruno: "atraso vira número, número vira nota, nota vira
  desligamento" é o que isto NÃO pode criar). Três armadilhas dos DADOS REAIS,
  todas tratadas: (1) NÃO há CPF na planilha → casa por MATRÍCULA normalizando
  zeros à esquerda dos dois lados ("003035"=="3035"); (2) `00:00` COM entrada é
  registro INCOMPLETO (esqueceu a saída), NUNCA falta — nos dados reais são 28
  incompletos vs 1 falta em 1 mês, então tratar tudo como o Tirvu apurou
  acusaria 28 pessoas injustamente; (3) `Horas Trabalhadas` é a fonte de
  verdade, não as batidas (há dia sem batida e com horas apuradas) — não deduzir
  presença dos horários. Geolocalização e foto NÃO são lidas (desproporcional,
  LGPD). Leitura pelo `_ler_linhas_xlsx` zip+XML. Reimportar o mesmo período
  substitui, não duplica; quem não casa por matrícula é listado, nunca criado.
