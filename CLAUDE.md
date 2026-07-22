# Portal de Admissão Green House

Portal de RH da Green House (Brasília/DF): admissão digital de candidatos,
base de colaboradores, testes DISC/situacional, reembolso-creche e geração de
documentos no papel timbrado. Produção numa VPS via Portainer (re-pull da
imagem; as migrations rodam sozinhas no entrypoint).

## ATENÇÃO: repositório PÚBLICO

- **NUNCA** commitar conteúdo de `docs/` (planilhas de colaboradores, ofícios,
  contratos, CNPJs). O `.gitignore` ignora `docs/*` exceto `docs/planejamento/`.
- O **gabarito do DISC nunca vai ao frontend** — pontuação só no servidor
  (`backend/app/services/disc.py`); o candidato da ADMISSÃO jamais vê o próprio
  resultado. Exceção intencional: na **testagem avulsa** (`/t/{token}`,
  `app/api/testagem.py`) o participante vê o resultado calculado — é ambiente
  de testagem/validação, decisão do Bruno (2026-07-19); o gabarito continua
  só no servidor.
- LGPD: dados pessoais só aparecem após 2FA por código no e-mail; respostas de
  CPF são anti-enumeração ("Se este CPF constar...").

## Arquitetura

- `backend/` — FastAPI (Python 3.12) + SQLAlchemy 2 + Alembic. Postgres 16,
  MinIO (arquivos), Redis/RQ (workers em `app/workers/`).
- `frontend/` — React + Vite (sem TypeScript). `src/candidato/` (wizard público),
  `src/rh/` (painel), `src/api.js` (todas as chamadas), `src/styles.css` (único CSS).
- Candidato e colaborador são o MESMO registro (`Candidato`): `situacao NULL` =
  em admissão; `ativo`/`desligado` = colaborador. Importação do Tirvu é
  idempotente (CPF p/ colaboradores, `tirvu_id` p/ postos). A tela de
  **Admissões** (`revisao.py::_candidatos_admissao`) filtra `situacao IS NULL`;
  **Colaboradores** filtra `situacao IS NOT NULL` — cada registro aparece numa
  tela só (v1.63; antes vazava nas duas). Escapes simétricos:
  `incluir_colaboradores` (Admissões) e `incluir_admissao` (Colaboradores).
  **`status` é SÓ fluxo; `situacao` é SÓ vínculo** (v1.69, item 1b — antes
  compartilhavam ativo/desligado e confundiam a tela). Regras: efetivar aqui →
  `status=aprovado`; importar do Tirvu → `status=importado` (valor novo, nunca
  passou pelo funil); desligar/reativar mexem SÓ na `situacao`, nunca no
  `status`. Os valores `ativo`/`desligado` do `StatusCandidato` são ÓRFÃOS (não
  se escreve mais; ficam no enum porque o Postgres não remove valor sem recriar
  o tipo; o front `status.js` já os ignora). NÃO usar em código novo, NÃO fundir
  os campos. **Bomba do expurgo:** `workers/expurgo.py` apaga arquivos de quem
  tem `status=aprovado` — como efetivado agora fica `aprovado`, o filtro exige
  `situacao IS NULL` (só admissão), senão apagaria documentos de colaborador
  ativo.
- **Migrations que adicionam E usam um valor de enum:** o `env.py` roda com
  `transaction_per_migration=True` (cada revisão commita sozinha). Separe em
  DUAS revisões: uma faz `ALTER TYPE ... ADD VALUE` (com `op.execute("COMMIT")`),
  a SEGUINTE usa o valor no `UPDATE` — o Postgres proíbe usar valor de enum
  recém-criado na mesma transação (`UnsafeNewEnumValueUsage`).
- **Reverter colaborador→candidato** (`/rh/colaboradores/{cid}/reverter` e
  `/lote/reverter`, v1.65): zera `situacao`/data para uma FASE de fluxo escolhida
  (convidado | em_revisao), **preserva a matrícula** e os dados. Motivo
  OBRIGATÓRIO (auditoria). `_indicio_tirvu` (origem=importacao ou matrícula
  999NNNN) só AVISA no front — nunca bloqueia (decisão do Bruno). Feito na tela
  atual de Colaboradores reusando o `Set` de selecionados (NÃO migra p/
  DashPlanilha — a avaliação adversária mostrou que o dash não aguenta o filtro
  server-side de Colaboradores sem regressão de LGPD/performance).

## Comandos (Windows; use o venv, o `python` do PATH é alias da MS Store)

```bash
cd backend
PYTHONPATH=. .venv/Scripts/python.exe -m alembic upgrade head
PYTHONPATH=. .venv/Scripts/python.exe tests/smoke_test.py   # 15 etapas, precisa dos containers abaixo
cd frontend && npm run build                                # valida JSX/CSS
```

Stack local completo (containers `deploy-*`): roda a partir do código-fonte e
NÃO se atualiza sozinho — depois de commitar, reconstruir com

```bash
docker compose --env-file .env -f deploy/docker-compose.base.yml -f deploy/docker-compose.ip.yml up -d --build
```

(o `--env-file .env` é obrigatório: a interpolação de `${VAR}` do compose lê o
.env do diretório do primeiro `-f`, que é `deploy/` — sem a flag, porta e
REDIS_URL saem vazias.)

Ambiente de teste efêmero (SEMPRE recriar limpo entre execuções — resíduo causa
falsos erros):

```bash
docker run -d --name pg-teste -e POSTGRES_USER=admissao -e POSTGRES_PASSWORD=admissao \
  -e POSTGRES_DB=admissao -p 55432:5432 postgres:16-alpine
docker run -d --name minio-teste -p 59000:9000 -e MINIO_ROOT_USER=minio \
  -e MINIO_ROOT_PASSWORD=minio12345 quay.io/minio/minio server /data
```

## Armadilhas conhecidas (já morderam)

- **Rotas FastAPI**: declarar rotas específicas (`/lote/...`, `/massa/...`)
  ANTES das paramétricas (`/{id}`), senão o literal vira UUID inválido (422).
- **Assinaturas**: documentos fixos usam o enum `DocumentoAssinavel`; documentos
  de MODELO do RH usam a chave `modelo-<assinatura_id>` nas rotas, com SNAPSHOT
  de título/corpo no registro `Assinatura` (editar o modelo não muda o que a
  pessoa assina). Resolver chaves com `_resolver_doc`/`_gerar_pdf` de
  `app/api/assinaturas.py` — nunca `GERADORES[...]` direto em código novo.
- **StreamingResponse + `Depends(get_db)`**: a sessão fecha quando a rota
  retorna, ANTES de o gerador streamar → `DetachedInstanceError`. Resolver todos
  os dados do banco ANTES de montar a resposta; o gerador só toca o MinIO
  (ver `app/api/arquivo.py`, export em lote). ZIP em streaming real via
  `app/services/zip_stream.py` (stdlib, `ZIP_STORED`) + `storage.abrir_em_blocos`.
- **Nomes de arquivo/pasta em export**: SEMPRE via `export_planilha.slug()`
  (remove `/ \ . ..`, acentos; fallback se vazio/reservado do Windows) — nunca
  concatenar `titulo_doc` cru (é texto livre do RH → path traversal).
- **Ações pesadas do RH** (dossiê, notificar, efetivar): protegidas por trava de
  idempotência (`app/services/idempotencia.py`) — 2º clique concorrente recebe
  409 `ja_em_processamento`. No front, o overlay (`Carregando.jsx`) só aparece
  após 400ms (evita flicker) e o erro 409 vira `e.amigavel` no `api.js`.
- **DISC — formato público das opções**: `questoes_disc_publicas()` devolve
  `opcoes: [{palavra, significado}]` (o significado é sinônimo NEUTRO para o
  tooltip; nunca descreve o traço, senão vaza o eixo DISC). O gabarito
  (dimensão) continua só no servidor. O front lê `.palavra`; a pontuação
  compara a palavra enviada. Definições em `SIGNIFICADOS_DISC` (disc.py),
  escritas à mão.
- **Select com busca**: `frontend/src/SelectBusca.jsx` para filtros suspensos
  grandes (postos, cargos) — dados carregados 1x e filtrados em memória.
- **Multi-signatário** (`solicitacao_assinatura`/`etapa_assinatura`): documento
  assinado por vários em ordem de papéis. A via do candidato dentro de um roteiro
  é uma `Assinatura` DEDICADA marcada com `solicitacao_etapa_id` — o
  `_registro`/`_docs_exigidos`/`_assinaturas_modelo` filtram `IS NULL` para não
  brigar com o wizard. `avancar_solicitacao` é serializado (`SELECT FOR UPDATE`).
  Externo: token single-use, PDF só após OTP validado. `/verificar-etapa` mostra
  só o assinante daquela etapa + "X de N" (sem coassinantes nominais). PDF final
  consolidado via `gerar_documento_com_vistos` (blocos empilhados + manifesto
  multi com QR por etapa). Rubrica/manifesto legado de 1 assinante intactos.
- **Assinatura da equipe**: NUNCA PNG/carimbo fingindo assinatura pessoal. É
  `AutorizacaoEquipe` — representante confirma 1x por código (ato de vontade);
  vira etapa já satisfeita por "autorização prévia" no roteiro do modelo; o
  manifesto diz "emitido sob autorização permanente de X", não "X assinou".
- **Integração Tirvu (export de admissões)**: `export_tirvu.py` gera o layout
  de 28 colunas em ORDEM FIXA (`COLUNAS_TIRVU`); o Tirvu recusa linha sem
  CTPS/PIS/JORNADA (pré-checagem em `/rh/colaboradores/tirvu-pendencias`). A
  **matrícula** NÃO é pendência: quando falta, o export a gera automaticamente no
  padrão **999+sequencial de 4 dígitos** (`9990001`, `9990002`, …) e GRAVA no
  cadastro (`garantir_matricula`/`proxima_matricula_auto`) — estável entre
  exports, sem colisão (continua da maior `999NNNN` existente). `linha_tirvu` só
  gera+grava com `gerar_matricula=True` (o EXPORT passa True e faz commit; a
  pré-checagem passa False — consulta não muta dados). **Jornada** é dado real do
  cadastro e continua bloqueante (o Tirvu acusa "Faltando Jornada de Trabalho" na
  importação). O arquivo é
  gerado por `montar_workbook_tirvu` (NÃO o `montar_workbook` genérico): planilha
  CRUA idêntica ao modelo `docs/Layout de Importação de Admissões.xlsx` — aba
  **`Plan1`**, SEM auto-filtro/painel congelado/cor no cabeçalho (o importador do
  Tirvu recusa a "decoração": `<autoFilter>`/`<pane>` no XML, aba com outro nome).
  Célula vazia é OMITIDA (não escrever `""` — o openpyxl geraria
  `<c t="inlineStr"></c>` malformado, que o parser do Tirvu rejeita); só grava
  células com conteúdo. Ordem SEMPRE por `COLUNAS_TIRVU`, nunca pela união das
  chaves do dict. CEP no padrão do Tirvu: COM hífen (`cep_mascarado`, 00000-000);
  CPF com máscara; datas dd/mm/aaaa; Sexo M/F; Registra Ponto S/N; PIS sem
  máscara. O export individual (ficha, `revisao.py`) e o em massa
  (`colaboradores.py`) usam o MESMO `montar_workbook_tirvu`. O export EM
  MASSA vive em **Colaboradores**, não em Admissões: só se manda para o Tirvu
  quem já foi EFETIVADO (quem está em admissão não tem vínculo a criar lá). Por
  padrão exclui `origem == "importacao"` — quem veio do Tirvu já existe lá
  (`incluir_importados=true` força). O export individual (botão na ficha) fica
  em `revisao.py` e serve candidato ou colaborador. CTPS Digital =
  padrão eSocial: número = o PRÓPRIO CPF (11 dígitos), série = "0000" — derivada
  em `salvar_documentos`, nunca perguntada. Endereço: coleta nova é separada
  (logradouro/numero/complemento); o legado (string única) vai inteiro na coluna
  "Endereço" e migra só pelo backfill ASSISTIDO (parser propõe, RH confirma —
  heurística cega erra endereço de Brasília).
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
- **Dash-planilha** (`frontend/src/rh/DashPlanilha.jsx`): componente RH reutilizável
  — ordena por qualquer coluna, filtra por coluna (texto/select), seleção + ações
  em massa (reusa `CheckMestre`), colunas configuráveis (mostrar/ocultar, salvo em
  `localStorage` por `id` do módulo) e export CSV (BOM UTF-8, abre no Excel-BR) do
  que está filtrado/ordenado. Dirigido por config de colunas
  (`{chave,rotulo,valor,ordenavel,filtro,opcoes,render,sempreVisivel}`). PILOTO no
  Banco de Talentos (`TalentosRH.jsx`). Sort/filtro são EM MEMÓRIA (volumes
  baixos). **ATENÇÃO** (avaliação adversária 2026-07-21): propagar aos outros
  módulos NÃO é plug-and-play. Colaboradores/Admissões filtram SERVER-SIDE
  (recarregam a API a cada filtro) e a base é a folha inteira (LGPD) — trocar
  pelo filtro-em-memória do dash traria tudo ao cliente (regressão de
  performance E de exposição). O componente ainda NÃO tem: cards/métricas no
  topo, nem forma de o pai injetar/controlar filtro (estado interno), nem modo
  server-side, nem paginação. Cards clicáveis→filtro (item 3) exige EVOLUIR o
  dash primeiro (slot de cards + filtro controlável + modo server-side) — piloto
  planejado só no Creche (que já tem `.rh-metrica` e volume baixo). **Coluna de
  texto longo** (cargos, descrição de jornada): marque `quebra: true` na config —
  a célula quebra linha (`white-space: normal`, `max-width: 22rem`) em vez de
  esticar a tabela e forçar rolagem lateral (v1.71). Sem isso, o default é
  `nowrap` (certo para datas/status/botões, ruim para texto livre). **Cards
  clicáveis→filtro** (item 3, v1.72): prop `cards` = `[{rotulo, valor, cor?,
  filtro?:{chave,valor}}]`. Card com `filtro` ativa aquele filtro ao clicar
  (TOGGLE — clicar de novo limpa); o `valor` do filtro é comparado com o
  `textoDe` da coluna, então use o RÓTULO exibido, não o código
  (ex.: 'Novo', não 'novo'). Cards sem `filtro` são indicadores (Total). Já em
  uso em Talentos (status) e Jornadas (escala/confirmação).
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
  elegível foi consultado e NÃO pediu. **"Novo requerimento p/ mais filhos" é
  pendência** (o modelo é 1:1, `candidato_id unique=True`; virar 1:N toca
  assinatura/dossiê/ativação/link — projetar p/ N, entregar 1).
- **Incidência de Benefícios** (`incidencia_beneficios.py`): a planilha do RH
  (abas PÚBLICO/PRIVADO) normaliza os postos no padrão `CLIENTE - Nº CONTRATO -
  OBJETO` e define a elegibilidade creche pela coluna "Reembolso creche/Mês". Lê
  as DUAS abas via zip+XML próprio (`_ler_abas` — o `_ler_linhas_xlsx` de
  `postos.py` lê só a 1ª). Equivalência com o Tirvu é ASSISTIDA: o sistema PROPÕE
  por similaridade (Cliente vs nome/sigla), o RH CONFIRMA cada linha (nunca merge
  cego — regra dos ~40 erros de digitação). Valores compostos (dois sindicatos
  numa célula) ficam como texto p/ decisão humana. `await arquivo.close()` no
  `finally`. Export normalizado p/ carga futura no Tirvu ficou p/ a próxima leva.
- **Campo novo em ficha assinada**: ACRESCENTAR campo não invalida assinatura
  (EDITAR invalida — regra de 2026-07-15). Tecnicamente: renderizar o campo novo
  SÓ se preenchido (`if`, como CNH/CTPS/laudo PCD em `fichas.py`) — o PDF é
  gerado sob demanda e a ficha antiga deve sair idêntica. O PDF assinado fica
  persistido no MinIO com hash do ato, então reformatar seções não quebra vias
  antigas.
- **Jornadas**: tabela própria; import da planilha de escalas do Tirvu (96 abas,
  1 aba = 1 posto, coluna "Jornada" achada pelo cabeçalho) em
  `organizacao.py::_abas_com_jornadas` — zip+XML puro, multi-abas. NUNCA fundir
  descrições parecidas (há ~40 erros de digitação nos dados reais; merge
  silencioso cria associação errada invisível). No seletor, jornadas do posto
  vêm PRIMEIRO (ordenação, nunca filtro).
- **Jornadas estruturadas** (v1.70, `JornadasRH.jsx`, submenu "Jornadas"): a
  `descricao` é CANÔNICA — é ela que vai ao Tirvu (texto único, formato
  inalterado); os campos estruturados (escala/4 horários/turno/adicional
  noturno/intrajornada+obs/cargo) são METADADOS INTERNOS. `jornada_parser.py`
  PROPÕE a estrutura (heurístico, ~86% confiança alta nos 270 casos reais); o RH
  CONFIRMA na aba "A confirmar" (`estruturado_confirmado_em`) — NUNCA
  auto-grava. `jornada_duplicidade.py` só SINALIZA pares suspeitos
  (SequenceMatcher sobre descrição normalizada + typos tipo ADICONAL→ADICIONAL);
  separa "idênticas após normalizar" das "parecidas mas diferentes" — o RH
  decide, o sistema NUNCA funde. Import por `POST /rh/jornadas/importar-planilha`
  (coluna "Jornada de Trabalho" + casa posto pela "Lotação"; idempotente por
  descrição normalizada; nasce com proposta aplicada mas não confirmada). Rotas:
  CRUD + `/jornadas/{id}/proposta` + `/jornadas-duplicidades` (HÍFEN, senão
  colide com a paramétrica). DELETE recusa 409 se a jornada estiver em uso. A
  página usa o `DashPlanilha` (2º consumidor real dele, além de Talentos).
- **Uploads de planilha do RH**: sempre `await arquivo.close()` em `finally` —
  o Starlette faz spool em disco acima de ~1MB e o temp file ficaria no
  container com CPFs de mil pessoas.
- **Migrations com ENUM**: criar o tipo com `.create(checkfirst=True)` e
  referenciar nas colunas com `create_type=False` (senão DuplicateObject).
- **Planilhas do Tirvu**: openpyxl quebra (stylesheet inválido, células sujas).
  Usar o leitor zip+XML `_ler_linhas_xlsx` em `app/api/postos.py`.
- **fpdf2**: `multi_cell(0, ...)` consecutivos precisam `new_x="LMARGIN",
  new_y="NEXT"`; rótulos de tabela usam o `campo()` de `_FichaPDF` (quebra
  linha na célula). PDFs de prova: gerar e CONFERIR visualmente (tool Read).
- **CSS**: conferir classes existentes em `styles.css` antes de usar (chip usa
  `--chip-cor` inline; métricas são `.rh-metrica strong/span`). **Checkbox/radio**
  já têm reset global (`input[type=checkbox],input[type=radio]` → 1.15rem, accent
  verde) desde v1.64 — NÃO precisa mais do remendo inline `style={{ width:'auto',
  minHeight:0 }}` que o código legado espalha (a regra `input,select,textarea`
  os inflava; por isso o remendo existia).
- **MutationObserver** de `responsivo.js`: só `childList+subtree` — observar
  `attributes` causa loop infinito.

## Convenções

- Idioma: TUDO em pt-BR (código, comentários, commits, UI).
- Commits direto no `main`: `feat(vX.Y): resumo` + corpo com bullets; uma
  versão por "onda" entregue. Push e acompanhar o CI (`gh run list/view`) —
  único workflow `ci.yml` (imagens api/frontend + testes de interface).
- Testar com dados reais antes de commitar: banco efêmero + smoke 15/15 +
  `npm run build`; para PDFs, prova visual.
- Exclusões do RH passam pela lixeira (`app/services/lixeira.py` —
  `mandar_para_lixeira` antes do delete; retenção configurável, padrão 60 dias).
- Termos de negócio não se trocam por sinônimos; explicá-los com o tooltip
  `Ajuda.jsx` (glossário).
- **Tooltips**: padrão ÚNICO = aparece no HOVER e some ao tirar o mouse (no
  celular, `:focus-within` cobre o toque) — 100% por CSS, nunca por estado/onClick.
  Vale para os tooltips CURTOS de referência: glossário do RH (`Ajuda.jsx`,
  `.ajuda-q` + `data-dica`), significado da palavra no DISC (`AjudaPalavra` em
  `TesteApp.jsx`, `.teste-ajuda-balao` visível no `:hover`/`:focus-within` do
  `.teste-ajuda-wrap`) e os `title=` nativos. NÃO se aplica às dicas LONGAS
  expansíveis de "como conseguir o documento" (checklist/wizard do candidato):
  essas continuam abrindo no CLIQUE — texto longo que a pessoa lê enquanto age no
  celular; hover as faria sumir no meio do passo a passo.
- UI: edição inline na própria linha (nunca formulário no topo); ações pesadas
  com `comAmpulheta()`; toda tabela `.rh-tabela` vira card no mobile
  (rotulagem automática via `responsivo.js`).

## Contexto de longo prazo

O histórico de decisões por leva de feedback fica na memória do assistente
(`~/.claude/projects/.../memory/MEMORY.md`). Roadmap e pendências combinadas
com o Bruno estão lá — consultar antes de assumir que algo está pendente.
