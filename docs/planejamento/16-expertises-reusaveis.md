# Catálogo de peças reutilizáveis

> **Por que existe** — regra cravada pelo Bruno em 2026-08-18:
> *"cada vez que criarmos uma expertise, vamos colocá-la de modo que podemos
> utilizá-la em módulos existentes e futuros, para que não tenhamos que criar
> algo do zero. não sei se seria o caso termos um registro das criações"*
>
> O reuso **já é praticado** — a câmera guiada nasceu na admissão e serve 4
> telas; o `VerificarIdentidade` foi parametrizado para o portal; a KBA saiu de
> `api/entrada.py` para `services/kba.py`. O que faltava era o REGISTRO: sem
> ele, a peça existe e ninguém sabe. Já custou caro — a v2.94 ia criar seis
> rotas de diagnóstico e **quatro já existiam**, e ia criar uma porta de escrita
> de talentos que também já existia.

**Antes de construir qualquer coisa nova, procure aqui.** Se a peça existe, use;
se existe e não serve, estenda-a em vez de duplicar (duas cópias divergem na
primeira mudança — a lição do `_guardar_curriculo`, v2.74).

---

## Frontend — reuso amplo (5+ telas)

| Peça | Arquivo | Contrato | Usos |
|---|---|---|---|
| **SelectBusca** | `SelectBusca.jsx` | `{opcoes\|children, valor, aoEscolher, placeholder, vazioRotulo, desabilitado}` | **34** |
| **DashPlanilha** | `rh/DashPlanilha.jsx` | `{id, colunas, dados, cards, filtrosExtras, acoesFiltro, acoesLinha, linhaExpandida, acoesMassa, vazio}` | **14** |
| **Carregando** | `Carregando.jsx` | `comAmpulheta(texto, fn)` · `ampulheta(ativo, texto)` | 8 |
| **Ajuda** | `Ajuda.jsx` | `{termo, texto}` (alimentado por `tooltips.js`) | 7 |
| **Aviso** | `Aviso.jsx` | `{tipo, texto, aoFechar, duracaoMs}` — toast flutuante | 6 |
| **Espera** | `Espera.jsx` | `{texto}` + export `FRASES` | 6 |
| **VisualizadorArquivo** | `VisualizadorArquivo.jsx` | `{blob, nome, aoFechar}` | 5 |
| **fmt.js** | `fmt.js` | `fmtData`, `isoParaBR`, `fmtCpf`, `cpfValido`, `fmtDuracao`… | **29** |

## Frontend — reuso moderado

| Peça | Arquivo | Contrato | Usos |
|---|---|---|---|
| **Camera** (`CapturaDocumento`) | `candidato/Camera.jsx` | `{formato: cartao\|a4\|cabecalho\|retrato, titulo, passos, aoCapturar, aoArquivo, aoFechar}` | 4 |
| **InputData** | `InputData.jsx` | `{valor, onChange, modoTexto}` — devolve ISO por padrão | 4 |
| **Modal** | `Modal.jsx` | `{titulo, aoFechar, children}` | 4 |
| **InputSenha** · **PdfViewer** · **CheckMestre** | — | — | 2–3 |
| **CampoComVariaveis** | `CampoComVariaveis.jsx` | `{valor, aoMudar, variaveis, como}` — insere `{{var}}` no cursor | 2 |
| **BotaoBaixar** · **PlayerAudio** | `rh/` | `{url, nome}` — blob autenticado | 2 |

⚠️ **`aoCapturar`/`aoArquivo` da câmera recebem LISTA, sempre** — mesmo uma foto
vem como lista de um (v2.61). E ao ligá-la, o backend precisa aceitar
`EXTENSOES_COM_WORD`, senão recusa um envio que a própria tela ofereceu.

## Backend — serviços transversais

| Serviço | O que faz | APIs que usam |
|---|---|---|
| `auditoria.registrar` | Registro de auditoria; nunca derruba a operação | **39** |
| `email_templates` | Catálogo + envio de e-mail (fonte da verdade) | **17** |
| `storage` | MinIO: salvar/ler/listar/`abrir_em_blocos` | 13 |
| `magic_link` | Emite/resolve link do candidato | 13 |
| `limite` | Rate limit (`exigir` levanta 429) | 12 |
| `lixeira` | Soft-delete genérico + restauração | 9 |
| `config_dinamica` | Config do banco sobrepondo `.env` | 7 |
| `notificacoes` | Matriz evento × destinatários; nunca levanta | 6 |
| `export_planilha` | XLSX + **`slug()`** (nome de arquivo seguro) | 6 |
| `upload_seguro` | Teto, allowlist e `close()` do spool | 5 |
| `normalizacao` | Qualquer envio → PDF timbrado; `combinar_pdfs` | 5 |
| `nomes.capitalizar_nome` | "maria de fátima" → "Maria de Fátima" | 5 |
| `fichas.aplicar_variaveis` | Engine de template da casa (`{{chave}}`) | 5 |
| `validacao.cpf_valido` | — | 5 |
| `exigencias` | Fábrica → padrão da casa → exceção da pessoa | 4 |
| `kba` | Desafio de identidade com bloqueio | 3 |
| `idempotencia.trava` | Anti duplo-clique (409 na 2ª) | 3 |
| `permissoes.pode` | Catálogo de autorização | 3 |

---

## SUBUTILIZADAS — existem, são genéricas, quase ninguém usa

Esta é a parte mais útil do catálogo: peças prontas cujo contrato **não tem nada
de específico** do módulo onde nasceram.

### Backend

| Peça | Hoje | Serve para |
|---|---|---|
| **`zip_stream.gerar_zip`** | **só `api/arquivo.py`** | Qualquer download em lote. Pico de memória ≈ 1 arquivo; nada nela é do módulo Arquivo. Candidatos: dossiês de creche, anexos de entrevista, gravações. |
| **`anti_prompt_injection`** | só via `api/vagas.py` | **Todo** texto externo que entre em prompt de IA — não só currículo. Contrato puro `str → (str, bool)`. Candidatos: OCR, transcrição de entrevista. |
| **`idempotencia.trava`** | 3 arquivos | Toda rota que gera PDF, dispara e-mail ou efetiva estado. |
| **`endereco.completo`/`rua`** | **zero** APIs (só serviços) | Resolve a dualidade legado × campos separados num lugar só. Rotas que expõem endereço montam ad hoc — foi a causa do defeito da v2.37. |
| **`marca.dados_empresa`** | só `api/marca.py` | Todo gerador de PDF/e-mail com dado da empresa ainda escrito no código (pendência registrada em `marca-dados-empresa-do-banco`). |
| **`upload_seguro.ler_upload`** | 5 rotas | Guarda-corpo obrigatório de **qualquer** `UploadFile`. Nasceu de achado de segurança em rota pública (v2.56). |

### Frontend

| Peça | Problema | Ação sugerida |
|---|---|---|
| **`VerificarIdentidade`** | Já tem contrato injetável (`kbaIniciar`/`kbaResponder`/`kbaDefinirEmail` com fallback), mas **mora dentro de `CrecheLink.jsx`** — 716 linhas de um módulo específico. Quem quiser usar importa do Creche. | Extrair para `frontend/src/VerificarIdentidade.jsx`. Serve qualquer gate público. |
| **`BotaoBaixar`** e **`PlayerAudio`** | Estão em `rh/`, mas são **infraestrutura** (download/áudio de rota autenticada), não componentes de RH. Comparar com `VisualizadorArquivo.jsx`, que resolve problema equivalente, está na RAIZ e por isso tem 5 consumidores nos dois módulos. | Mover para a raiz. |
| **`EditorImagem`** | Contrato `{file, cropInicial, aoConcluir, aoVoltar}` não menciona documento nem candidato — mas só a `Camera` usa. | Serve foto de perfil, logo da empresa, qualquer anexo de imagem. |
| **`Ajuda`** e **`comAmpulheta`** | Usados só em `rh/`. As telas do CANDIDATO não têm ajuda contextual apesar da infraestrutura existir. | — |

> **Lição estrutural**: peça de infraestrutura guardada dentro de uma pasta de
> módulo tende a ficar invisível. Se o contrato não menciona o domínio, o
> arquivo não deveria morar no domínio.

---

## Como manter isto vivo

Ao criar peça reutilizável nova: acrescente a linha aqui **na mesma leva** — é o
mesmo contrato do `documentos_catalogo` e do `email_templates` (v2.21), que já
cobram entrada no catálogo. Catálogo desatualizado é pior que não ter: dá a
impressão de que a busca foi feita.
