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
  idempotente (CPF p/ colaboradores, `tirvu_id` p/ postos).

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
  CTPS/PIS (pré-checagem em `/rh/colaboradores/tirvu-pendencias`). O export EM
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
  `--chip-cor` inline; métricas são `.rh-metrica strong/span`).
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
- UI: edição inline na própria linha (nunca formulário no topo); ações pesadas
  com `comAmpulheta()`; toda tabela `.rh-tabela` vira card no mobile
  (rotulagem automática via `responsivo.js`).

## Contexto de longo prazo

O histórico de decisões por leva de feedback fica na memória do assistente
(`~/.claude/projects/.../memory/MEMORY.md`). Roadmap e pendências combinadas
com o Bruno estão lá — consultar antes de assumir que algo está pendente.
