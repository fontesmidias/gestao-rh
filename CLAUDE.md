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

Stack e layout de diretórios saem do `requirements.txt`, do `package.json` e de
um `ls` — não se repetem aqui. O que segue é o que o código NÃO diz.

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

⚠️ **`up --build` constrói os SEIS serviços em paralelo e derruba o daemon em
máquina apertada** (2026-08-13, aconteceu duas vezes): a imagem de transcrição
compila torch + pyannote, e numa máquina de 7,8 GB (o WSL pega ~metade) o Docker
Desktop morre com `error during connect: … _ping: EOF` — erro que **não fala em
memória** e manda procurar defeito no Docker. Sintoma vizinho: `docker ps` vazio
e `docker info` acusando *"Docker Desktop is manually paused"*. Em máquina
apertada, construa um serviço por vez (`docker compose build api`) e deixe o
`transcricao` por último — ou nem o construa, se não for testar transcrição.

Stack local completo (containers `deploy-*`): roda a partir do código-fonte e
NÃO se atualiza sozinho — depois de commitar, reconstruir com

```bash
docker compose --env-file .env -f deploy/docker-compose.base.yml -f deploy/docker-compose.ip.yml up -d --build
```

(o `--env-file .env` é obrigatório: a interpolação de `${VAR}` do compose lê o
.env do diretório do primeiro `-f`, que é `deploy/` — sem a flag, porta e
REDIS_URL saem vazias.)

**Usuário PADRÃO dos testes locais** (v2.85, pedido do Bruno: *"para os testes
locais, deixe um user e senha padrão, para não perdermos mais tempo"*). O
`criar_admin_inicial` só cria o admin do `.env` com a tabela **VAZIA**, então em
banco de desenvolvimento com usuários antigos aquele e-mail não existe — e o
sintoma é um 401 que aparece como `KeyError: 'token'` ou "senha errada",
apontando para o lugar errado (mordeu no smoke, no `test_email_templates` e nos
testes de tela no mesmo dia). Rode uma vez após subir a stack:

```bash
docker cp backend/tests/. <api>:/app/tests
docker exec -e PYTHONPATH=. <api> python tests/preparar_ambiente_local.py
# teste@exemplo.com.br / senha-teste-123
BASE_URL=http://localhost:8090 RH_EMAIL=teste@exemplo.com.br \
  RH_SENHA=senha-teste-123 npx playwright test --workers=1
```

**`--workers=1` não é preciosismo**: em paralelo a suíte estoura o rate limit do
login (15/5min por IP) e as falhas PARECEM defeito de layout — timeout esperando
a tabela (v2.60). Reiniciar o container da API zera o limite (é em memória).

Ambiente de teste efêmero (SEMPRE recriar limpo entre execuções — resíduo causa
falsos erros):

```bash
docker run -d --name pg-teste -e POSTGRES_USER=admissao -e POSTGRES_PASSWORD=admissao \
  -e POSTGRES_DB=admissao -p 55432:5432 postgres:16-alpine
docker run -d --name minio-teste -p 59000:9000 -e MINIO_ROOT_USER=minio \
  -e MINIO_ROOT_PASSWORD=minio12345 quay.io/minio/minio server /data
```

## Armadilhas conhecidas (já morderam)

- **Mudar REGRA DE NEGÓCIO quebra o teste que cobria o comportamento antigo — e
  o E2E reprova por ÚLTIMO** (v3.06, mordeu em três commits seguidos): tornar o
  currículo obrigatório reprovou o `portal.spec.js`, que preenche o formulário
  público e espera "Cadastro recebido" **sem anexar nada** — porque até então não
  precisava. O teste estava certo; quem mudou a regra não foi procurar quem
  dependia dela. Como a correção só entrou depois, os DOIS commits seguintes
  subiram já reprovando pelo mesmo motivo. Ao mudar regra, **`grep` nos testes
  E2E pelo fluxo afetado**: eles exercitam a tela inteira e rodam no fim do
  pipeline, então a reprovação chega ~4 min depois dos testes rápidos.
  ⚠️ **Corolário que valeu mais que o conserto**: ao varrer quem MAIS dependia,
  achei dois testes que a dedup nova (v3.05) passaria a quebrar em SILÊNCIO —
  `test_talento_arquivar` usava e-mail derivado do nome, fixo entre execuções, e
  ele ARQUIVA talentos: o recadastro reabre arquivado como "novo", então a 2ª
  rodada verificaria um estado que ela mesma desfez (e o teste nem roda no CI).
  É o "só passa em banco limpo" (v2.14) por uma porta nova: **não foi o teste que
  sujou, foi a regra nova que passou a enxergar o resíduo**.
- **Verificação de import só prova o que ela CARREGA — importe na profundidade
  do uso** (v3.00.6, o mesmo defeito duas vezes): o build passou a terminar com
  um `python -c` importando `pyannote.audio.Pipeline`, e ele ficou VERDE com o
  `matplotlib` faltando — a exigência mora um nível abaixo, em
  `pyannote.audio.pipelines`, que só carrega quando o pipeline é montado de
  verdade. A imagem subiu e o `ModuleNotFoundError` apareceu na ficha de uma
  entrevista real. Importar o pacote de cima dá impressão de cobertura sem
  tê-la; é a v2.67 (*"teste que não executa a linha mutada"*) aplicada a
  dependência. Ao escrever guarda-corpo de import, importe o SÍMBOLO que o
  código de produção usa, não a fachada do pacote.
- **`pip install` encadeado REABRE a faixa que o anterior fechou** (v3.00.5, a
  continuação do defeito acima): a v3.00.4 cravou `torch==2.8.0` numa linha e
  instalou o `pyannote` na SEGUINTE — e o pip, resolvendo de novo, trocou o
  torch por baixo (o log do build mostra `torch-2.13.0` e
  `huggingface-hub-1.27.0` entrando por cima dos pinos). Pino só vale se tudo
  estiver na MESMA resolução; aí conflito vira erro de build em vez de imagem
  quebrada em produção. ⚠️ E **biblioteca que o pacote IMPORTA mas não DECLARA**
  não é instalada por ninguém: o `pyannote.audio` usa `torchvision` sem o
  declarar, e o sintoma foi `ModuleNotFoundError` na ficha da entrevista, com o
  token já testado e aprovado. Em container de ML, termine o `RUN` com um
  `python -c` que IMPORTE o que a função usa — módulo faltando reprova no CI,
  não na cara de quem opera.
- **Dependência com faixa ABERTA quebra sozinha, e o sintoma culpa a
  credencial** (v3.00.4, defeito de campo): o `Dockerfile.transcricao` pedia
  `torchaudio>=2.2,<3`, e o `pyannote.audio` 3.x declara as próprias
  dependências SEM TETO. `torchaudio` 2.9 removeu `AudioMetaData` e o
  `huggingface_hub` 1.0 removeu `use_auth_token` (out/2025) — o pip pega a mais
  nova, a diarização quebra **no import**, e a tela dizia *"confira o token do
  Hugging Face"* com o token CORRETO. Rebuild sem ninguém mexer em nada vira
  defeito em produção. Em container de ML, **crave as versões** e, ao subi-las,
  rode a função de ponta a ponta: o build passa igual. ⚠️ Três causas com ações
  DIFERENTES (versão incompatível · licença não aceita · token inválido) não
  podem sair com a mesma mensagem — é a v2.93 (*"recusa que aponta o lugar
  errado"*) numa variação nova. E **`Pipeline.from_pretrained` devolve `None`
  em silêncio** quando o acesso é negado: sem checar, o erro nasce na linha
  seguinte como `AttributeError: NoneType`, indistinguível de biblioteca
  quebrada. São **DUAS licenças** (`speaker-diarization-3.1` usa
  `segmentation-3.0`); conferir uma só dizia "vai funcionar" e a falha aparecia
  numa entrevista de 40 min. Coberto por `test_diarizacao_diagnostico.py`, 4
  mutações — uma delas **passou verde na 1ª versão do teste**, porque procurar o
  TEXTO da mensagem não prova que o `if` que a escolhe está ligado (v2.67).
- **Campo de "tem arquivo?" que só um dos caminhos preenche diz NÃO com o
  arquivo guardado ao lado** (v3.00.3): a rota de refazer a transcrição exigia
  `gravacao.audio_key`, preenchido só pelo envio de ARQUIVO ÚNICO — quem grava
  pelo navegador (o caminho normal desde a v2.98) guarda em `BlocoGravacao`, e
  recebia `404 sem_audio` **com a entrevista inteira no storage**. `tem_audio`
  no resumo tinha o mesmo furo, então a tela também dizia "sem áudio". Neste
  sistema quase todo dado tem DUAS portas (v2.89.1) e isto vale para a PRESENÇA
  do dado, não só para o tamanho dele: ao perguntar "existe arquivo?", conte
  TODOS os caminhos de gravação, nunca um campo só. E **ação de reprocessar não
  deve exigir estado de FALHA**: aceitar só `falhou` deixou sem saída o caso que
  motivou o recurso — refazer uma transcrição `pronta` para aplicar melhoria
  nova. ⚠️ O botão correspondente **só aparece quando faz diferença** (há áudio,
  a melhoria está ligada, e o texto ainda não a tem): oferecê-lo sempre gastaria
  ~1,7× a duração do áudio para devolver texto idêntico. Coberto por
  `test_retranscrever.py`, 4 mutações.
- **`<a href>` para rota AUTENTICADA devolve 401 — o navegador não manda o
  header** (v2.98.4, defeito visto pelo Bruno na tela): clicar em "Baixar
  transcrição" abria uma janela com `{"detail":"nao_autenticado"}`. O sistema
  autentica por `Authorization: Bearer` (não há cookie de sessão), e link
  seguido pelo navegador é um GET LIMPO. O JSX fica plausível, o build passa, e
  só quebra no clique — mesma família do `api.x()` inexistente (v2.73) e da
  `prop` inventada (v2.64). Use `BotaoBaixar` (busca com o header, cria
  `objectURL`, dispara o download com o nome certo) ou o `PlayerAudio` para
  áudio. ⚠️ O `download` do `<a>` precisa do NOME explícito: o
  `Content-Disposition` da rota não alcança o `objectURL`, e sem ele o arquivo
  sai com um UUID por nome. Exceção legítima: rota cuja autorização está no
  TOKEN DA URL (o preview do assinante externo) — ali o link direto é correto.
- **Consentimento em conversa ASSIMÉTRICA precisa ser recusável, e a recusa é um
  REGISTRO** (v2.97, gravação de entrevista): voz é dado pessoal e há
  entendimento de que é biométrico; numa entrevista de emprego, de um lado está
  quem decide e do outro quem precisa do emprego. Se "autorizar" for um botão
  verde grande e "recusar" um link cinza, a pessoa clica no primeiro por não
  sentir que pode recusar — isso é teatro de consentimento, não consentimento.
  Os dois botões usam a MESMA classe, e a tela DIZ que recusar não afeta a
  avaliação. São **oito** estados, não seis: faltava `nao_perguntado`, que é
  diferente de `recusado` — sem a distinção não se prova que a pessoa foi
  consultada (v2.34). Três travas que não devem ser afrouxadas: a checagem de
  consentimento vive no SERVIÇO (v2.66); **retirar o consentimento com áudio
  existente RECUSA** dizendo o que resolve (aceitar deixaria áudio guardado sob
  um registro dizendo que a pessoa não autorizou); e a exclusão **não passa pela
  lixeira** — reter 60 dias dado biométrico é o oposto do que se pede ao retirar
  consentimento; o registro fica, o áudio sai do storage (v2.35).
- **Container novo precisa entrar na matriz do `ci.yml`, não só nos dois
  composes** (v2.97): a armadilha da v2.66 (declarar worker nos DOIS arquivos de
  deploy) tem um terceiro arquivo quando a imagem é PRÓPRIA — sem a entrada em
  `jobs.imagens.strategy.matrix`, o `portainer-stack.yml` aponta para uma imagem
  que o CI nunca publicou e o container não sobe em produção. A matriz ganhou o
  campo `arquivo` para suportar Dockerfile alternativo.
- **Tela de TRABALHO sobre um registro segue o § 8c do design — é OBRIGATÓRIO**
  (v2.96.1, validado no uso real antes de virar regra): impedimento no topo com
  o atalho que resolve; um trabalho por vez em ABAS por natureza (`hidden`, não
  desmontar; a aba NÃO se guarda em `localStorage`; reusa `.rh-abas`); **um
  `btn-principal` por tela** (o ato que FECHA o trabalho — salvar/liberar/criar
  são secundários); e bloco com muitos controles nasce recolhido, resumindo as
  exceções **em palavras e FORA do `<details>`**. Vale para ficha da pessoa,
  benefício, vaga, avaliação — **não** para listas (essas seguem o
  `DashPlanilha`). Reprovado no CI por `test_tela_de_trabalho.py`; ao criar tela
  do tipo, acrescente-a à lista `TELAS_DE_TRABALHO` (é o mesmo contrato do
  `TELAS` da régua de largura, que já cobrou por não enumerar a tela nova na
  v2.62).
- **Para medir o que está VISÍVEL, use `checkVisibility()` — não
  `getBoundingClientRect`** (v2.96): a régua da v2.95 contou **52 checkboxes
  "visíveis"** que estavam dentro de um `<details>` FECHADO, porque o
  `getBoundingClientRect` devolve dimensão para conteúdo de details fechado e
  para filho de `[hidden]`. Com `el.checkVisibility({checkOpacity:true})` a mesma
  tela mediu **zero**. A diferença não é acadêmica: a primeira medição diria que
  as abas não resolveram nada. ⚠️ E **a comparação antes/depois tem que usar o
  MESMO critério** — re-medi o "antes" com `git stash` antes de afirmar a
  melhora, senão o número compara réguas diferentes e não mede coisa nenhuma.
- **Comentário JSX dentro de `&& (…)` quebra o build** (v2.96): `{cond && ( {/*
  … */} <button/> )}` é erro de sintaxe, porque ali só cabe UMA expressão. O
  comentário vai ANTES da linha do `&&`. Erro barato de achar (o build reprova),
  mas custa uma rodada.
- **Redesenho se valida em PROTÓTIPO, medindo antes e depois** (v2.95, método
  cravado pelo Bruno: *"se tudo de design for validar assim, vamos em frente"*).
  A queixa era *"não tô achando intuitivo, parece muita poluição visual"* — que é
  impressão, e impressão não se discute. O que se discute é contagem: a ficha
  tinha **109 controles, 54 caixas de marcação, 14 blocos de mesmo peso e 15
  tamanhos de fonte** (medido com Playwright em 1440×900 e 390×844;
  `frontend/tests/e2e/_levantamento-densidade.spec.js`, prefixo `_` = roda à mão,
  fora do CI). O ciclo é: **medir → protótipo (HTML, antes/depois, desktop E
  celular) → o Bruno valida → aplicar em UMA tela → medir de novo → só então
  cravar como padrão**. Não inverta: aplicar antes de validar é como as telas
  ficaram assim. E **as decisões que mudam o resultado se perguntam ANTES**
  (aba × rolagem, qual aba abre, o que nasce fechado) — com preview visual, não
  no abstrato.
- **A informação que resolve o problema já existia — estava no fim da página**
  (v2.95): `dossie.pendencias` (a única frase que responde *"por que esta pessoa
  não fechou?"*) vivia dentro do bloco de Diagnóstico, atrás de um `<details>`,
  depois de ~65 linhas de telemetria. Em 11/08 isso custou 54 minutos. Ao
  investigar "o RH não acha X", pergunte primeiro **se X já está na tela e onde**
  — quase sempre está, no lugar errado. Corolário: **resumo de bloco recolhido
  mora FORA do `<details>`** (fechado ele nem renderiza — v2.76.2), senão só o
  vê quem abre, e o problema é ninguém abrir.
- **Credencial de MÁQUINA não é token de sessão — e a pergunta que decide é "se
  vazar hoje à noite, como eu corto?"** (v2.94, `services/token_automacao.py`):
  o token do painel é `itsdangerous` STATELESS com TTL de 12h, e as duas coisas o
  desqualificam para automação. Stateless **não se revoga** (a assinatura é a
  única prova; cortá-lo exigiria trocar o `SECRET_KEY` e derrubar a sessão de
  todo mundo), e 12h obrigaria a guardar a SENHA do usuário no desktop para
  renovar — senha vale para sempre e abre o painel inteiro. O desenho: segredo
  sorteado, mostrado UMA vez, guardado só como `sha256` (quem tem o banco não tem
  a credencial), prefixo `mcp_…` reconhecível para ser identificado se vazar,
  **revogar MARCA e não apaga** (a linha é prova de que existiu e de quando
  deixou de valer) e **usuário inativo corta a credencial junto** — senão
  desligar alguém deixaria o token dele vivo. ⚠️ **Entra pelo MESMO `requer_rh`
  e segue para o `exige(...)`**: porta paralela que autenticasse sem passar pela
  checagem furaria o modelo de papéis inteiro (v2.86) sem nada na tela
  denunciando. O papel `automacao` é de MÁQUINA (4 permissões contra as 27 do
  `rh`), e cada ausência é decisão registrada — ao acrescentar ferramenta ao MCP,
  pergunte se a permissão nova é de DIAGNÓSTICO; se for de ação, provavelmente
  não pertence a este papel. Coberto por `test_papel_automacao.py` e
  `test_token_automacao.py`, 3 mutações cada.
- **Antes de construir módulo novo, procure o que já existe** (v2.94, duas vezes
  na mesma leva): o MCP ia ganhar seis rotas de diagnóstico — e
  `api/diagnostico.py` **já respondia quatro delas** (nasceu do dossiê da Kátia,
  só leitura, com dados-chave, pendências, documentos e linha do tempo); a porta
  de escrita ia ser criada, e `POST /rh/talentos` (v2.73) **já existia**, já
  nascida para *"currículo que chega por e-mail"* e já recusando duplicata
  nomeando quem é. O que faltava de verdade não era ferramenta, era CREDENCIAL —
  e isso só apareceu porque alguém abriu o código antes de escrever. `grep` pela
  rota antes de desenhar a rota.
- **Recusa que não oferece a SAÍDA faz quem opera consertar a coisa errada**
  (v2.93, caso de campo 11/08/2026 — o mais caro do gênero até aqui): um PDF de
  "nada consta" emitido por site de governo não abria no `pypdf`, e
  `dossie.py::_adicionar_em_a4` derrubava o dossiê INTEIRO — 18 documentos
  aprovados perdidos por causa de um. A mensagem não dizia QUAL documento era, e
  a analista tomou o erro **8×** em 70 minutos até concluir que a culpa era dos
  campos obrigatórios: desmarcou **condições médicas, medicamento contínuo e
  contato de emergência** de um colaborador real, com o motivo *"por que não
  consigo salvar"* na auditoria — que não é justificativa, é socorro digitado no
  campo errado. O erro continuou depois. ⚠️ **A saída existia e a tela a
  escondia**: o dossiê parcial (`forcar=true`) tem botão desde sempre, mas o
  bloco só renderiza no `catch` de PENDÊNCIA (`e.detail.pendencias`); erro de
  MONTAGEM cai noutro ramo, `pendDossie` fica nulo e o botão **nunca aparece**.
  É a v2.87 (*"recusa oferecendo a saída, nunca só o bloqueio"*) violada onde
  mais custava. Três regras: (1) toda recusa de ação pesada oferece a
  alternativa **no mesmo lugar onde recusou**, em TODOS os ramos do `catch`, não
  só no primeiro; (2) peça ilegível é **pulada e NOMEADA** — `except: pass`
  (que existia no ramo do multi-signatário) troca "quebra ruidosamente" por
  "some caladinho", e página faltando em dossiê que circula para o cliente é
  pior que erro; (3) **peça pulada não marca `aprovado`** e nenhuma página
  ⇒ recusa, senão um PDF de zero página sobrescreve o dossiê anterior com o
  `dossie_gerado_em` afirmando que está pronto. Coberto por
  `test_dossie_pdf_ilegivel.py`, 3 mutações.
- **Healthcheck com `curl` marca o container como *unhealthy* PARA SEMPRE**
  (v2.93): a imagem da API não tem `curl` nem `wget` — só Python. E o critério é
  apenas "a API responde": **`migracoes.em_dia` NÃO entra**, porque reiniciar em
  loop por migration atrasada recriaria o incidente da v2.70, onde schema velho
  no ar era melhor que tela morta. Vai nos DOIS arquivos de deploy (v2.66).

- **Lista suspensa abre para o lado que CABE — e o teste precisa ABRIR a lista**
  (v2.92, defeito visto pelo Bruno na tela): o `SelectBusca` abria com
  `top: calc(100% + 4px)` FIXO, então na última linha de uma tabela o painel
  saía pelo fim do card e a opção ficava ilegível — no caso, a que decide o
  ACESSO da pessoa. O § 5 do sistema de design já mandava ("nada estoura a
  tela") e a regra estava sendo violada em todo seletor perto do fim de um
  container. Hoje o lado é decidido MEDINDO o espaço no `onClick`: media query
  não serve, porque o corte depende de ONDE o campo está na página. ⚠️ **As
  réguas existentes não pegavam**: `tabelas-cabem-na-tela` mede a LARGURA, e
  overflow contido não alarga a página (v2.76.1) — faltava medir a borda do
  painel ABERTO contra o container que o recorta, e nenhum teste abria a lista.
  Ao mexer em popup/dropdown, meça-o ABERTO e na ÚLTIMA linha; testar na
  primeira passa sempre e não prova nada.
- **Carteira de Processos: a titularidade é do CARGO, e a cadeia responde
  SOZINHA** (v2.91, `models/processo.py` + `services/processos.py`): 31
  processos em 9 fases, dois cenários de efetivo, importados da planilha RACI do
  Bruno. `FuncaoRH` é a unidade que POSSUI processos; a pessoa é um atributo
  dela (texto livre, **não** FK para `UsuarioRH` — a carteira precisa descrever
  quem ainda não tem conta, como o "Analista Jr a contratar"). Esvaziar
  `pessoa_nome` faz `responsavel_atual` percorrer a cadeia e devolver o próximo
  — é a razão de existir do módulo, e há mutação cobrindo. **Dois casos da
  planilha real que NÃO são defeito**: 9.1/9.2 têm "Escala diária (rodízio)"
  como titular (giram entre a equipe — acusá-los de órfãos é alarme falso, e
  alarme falso ensina a ignorar o alarme); e o 9.3 só existe no C2, porque nasce
  com o Analista Jr. ⚠️ **A coluna do titular chama-se "Titular (Dono)"** — o
  parser casava por igualdade exata, ela caía fora, a cadeia começava no 2º
  apoio e TODO processo saía com o titular errado, sem erro nenhum. Casar por
  PREFIXO (`_coluna`) e conferir contra o arquivo real, não contra um montado à
  mão (v2.54).
- **Texto de documento editável mora em `services/textos_documentos.py` — e a
  constante continua sendo o PADRÃO** (v2.90): direitos do trabalhador e os
  quatro ciclos de VT/VA saíram do código para o painel, mas `DIREITOS_TRABALHADOR`
  e `_CICLO_VT`/`_CICLO_VA` continuam em `fichas.py` como fábrica — vazio ou erro
  de leitura cai neles, e `texto()` NUNCA levanta (documento é papel que a pessoa
  assina; não pode deixar de sair porque a consulta de config falhou). Ao tornar
  outro trecho editável: acrescente ao `BLOCOS`, ligue o gerador **e** o corpo
  copiável de `documentos_texto.py` — os dois leem a MESMA fonte, e deixar um
  para trás faz a amostra que o RH duplica divergir do documento oficial (o
  defeito da v2.19, que perdeu 6% do VT e 8% do FGTS numa cópia à mão). ⚠️ **O
  LAYOUT não entra**: formulário oficial tem campos posicionados, tabelas e loops
  (a ficha cadastral tem 49 chamadas de campo) — decisão do Bruno é *"só a data e
  os dados; o layout fica"*. E **documento assinado nunca muda**: o hash do ato
  foi calculado sobre aquele PDF.
- **Afirmar AUSÊNCIA em documento longo exige saber a que SEÇÃO o trecho
  pertence** (v2.90): o teste conferiu que "dia 1 ao dia 30" sumira do PDF depois
  de editar o ciclo do VT — e a frase continuava lá, CORRETAMENTE, porque
  pertence ao vale-ALIMENTAÇÃO, outro bloco. Asserção de ausência sobre texto
  extraído de PDF casa com qualquer seção; recorte antes de afirmar.
- **Coluna dimensionada para o caminho MAIS ESTREITO quebra no outro** (v2.89.1,
  defeito de campo): `talento.escolaridade` era `varchar(60)` porque o
  formulário PÚBLICO oferece uma LISTA curta ("Ensino médio completo") — mas no
  cadastro pelo RH o campo é texto livre, e o real tinha **106 caracteres**.
  Neste sistema quase todo dado tem DUAS portas (público × RH, wizard ×
  importação, formulário × planilha): ao criar coluna de texto, dimensione pela
  porta mais LARGA. E o defeito pior não era o tamanho: **o erro virava HTTP 500
  em texto puro**, então a tela dizia "não foi possível" e o RH refazia o
  cadastro inteiro sem saber qual campo encurtar. Rota que grava texto livre
  precisa de `except DataError` devolvendo 422 que NOMEIA campo, limite e
  tamanho — e os limites se leem do próprio modelo (`Model.__table__.columns`),
  nunca de uma lista à mão que envelhece na primeira migration. ⚠️ O `except`
  vem ANTES de `registrar()`: a auditoria faz `flush()` e deixaria a sessão em
  rollback pendente, escondendo a causa atrás de `PendingRollbackError`.
- **Data PURA (`aaaa-mm-dd`) não passa por `new Date()` — volta um dia** (v2.89):
  a tela dizia **02/08** para uma data salva como **03/08**, e o banco estava
  certo o tempo todo. `new Date("2026-08-03")` é lido como UTC meia-noite e,
  convertido para São Paulo (UTC-3), vira 02/08 às 21h — que é o que o `fmtData`
  faz. Para data sem hora use `isoParaBR` (converte por TEXTO). O `fmtData`
  continua certo para `datetime` com fuso; o erro é aplicá-lo a data pura.
  Sintoma que engana: parece defeito de gravação, e manda procurar no backend.
- **A data do documento é UMA função, e a assinatura tem precedência** (v2.89,
  `fichas.data_do_documento`): assinatura > escolha do RH (`data_documentos`) >
  hoje. Eram SETE cópias de `assinado if ... else date.today()` nos geradores —
  bastaria uma passar despercebida para o mesmo candidato ter dois documentos
  com datas diferentes no mesmo dossiê, sem nada na tela denunciando. ⚠️ **Nada
  passa por cima do assinado**: o `hash_sha256` do ato é calculado sobre o PDF
  (`api/assinaturas.py`) e todo manifesto emitido aponta para ele; data
  configurada vazando para um assinado faria o PDF deixar de se reproduzir e a
  verificação acusar divergência — na peça usada em disputa trabalhista. Ao
  acrescentar gerador novo, chame a função em vez de repetir o `else`.
- **PDF se confere em TODAS as páginas** (v2.89, corolário da v2.55): o teste
  procurou a data em `pages[0]` e acusou "não encontrada" num PDF **correto** —
  ela fica na página 3 do acordo. Extraia o texto de todas as páginas antes de
  afirmar que algo não está lá (é a v2.56 numa variação: lá a quebra de linha
  escondia a frase, aqui a paginação).
- **`min-width: 0` NÃO quebra texto enquanto houver `white-space: nowrap`**
  (v2.88, o rótulo que saiu por cima da coluna vizinha): ao pôr a lista de
  exigências em grade, "Certidão de nascimento do dependente" mediu **303px numa
  coluna de 246px** e foi impresso SOBRE a coluna ao lado. Soltar o piso do item
  (`min-width: 0` no `li` e no `.campo-check`) não resolve sozinho — sem lugar
  onde quebrar, o texto continua numa linha só. O `.campo-check` é `nowrap` de
  propósito (certo na barra de ações, onde rótulo curto não deve partir), então
  a correção é `white-space: normal` **só na lista em colunas**. Mordeu duas
  vezes na mesma leva porque **o teste de largura passava**: overflow CONTIDO
  não alarga a página (v2.76.1) e só apareceu no PRINT. Ao pôr em colunas algo
  que era lista vertical, meça a borda direita de cada item contra a do
  container — e olhe a tela.
- **Menu que esconde o que a pessoa não pode é CORTESIA — e menu vazio precisa
  DIZER que está vazio** (v2.88, `RHApp.jsx`): quem protege é o `exige` de cada
  rota, no servidor; esconder no front não acrescenta segurança nenhuma. O
  motivo de fazê-lo é outro: item que sempre responde 403 ensina a equipe a
  ignorar mensagem de erro, e é justamente a mensagem de erro que precisa ser
  levada a sério quando algo quebra. Três regras: (1) a permissão do item tem
  que ser a MESMA da rota que a tela chama ao abrir — uma "parecida" esconde o
  menu de quem poderia usar, ou mostra o de quem vai levar 403; (2) enquanto as
  permissões carregam, **e se a consulta falhar**, o menu aparece INTEIRO —
  erro de rede não pode parecer perda de acesso; (3) papel estreito pode zerar
  o menu (medido: recepção vê 0 itens), e barra em branco parece sistema
  quebrado — a explicação transforma "quebrou" em "ainda não é para mim".
- **DUPLICAR é o caminho normal de criar — e a cópia nasce SEM VALER** (v2.87,
  padrão cravado pelo Bruno: *"a possibilidade de duplicar um existente e, a
  partir dessa duplicata, editarmos o que tiver que editar para daí sim
  ativarmos"*). Já existia em provas, questões, roteiros e documentos do
  sistema; virou regra: **todo cadastro reusável ganha `POST .../duplicar`**.
  Quem começa numa tela em branco erra por excesso ou falta e só descobre no
  uso; partir de algo que funciona é mais seguro. ⚠️ **A cópia nasce inativa /
  em rascunho** — o `duplicar` de provas herda `ativa=p.ativa` e por isso já
  vale no instante em que é criada, o que num PAPEL seria conceder acesso antes
  de alguém revisar. Corolários pagos na v2.87: a cópia do superadmin precisa
  materializar o catálogo INTEIRO (ele guarda lista vazia porque `pode()` não a
  consulta — copiar o campo cru daria um papel que não concede NADA com o
  rótulo dizendo o contrário); a chave se resolve por sufixo incremental
  (`rh-copia`, `rh-copia-2`) porque `chave` é `unique`; e duplicar deve **abrir
  a cópia para edição na hora**, já que quem clica quer ajustar algo.
  **O que NÃO se copia** (v2.87.1, ao levar o padrão a posto/vaga/modelo/
  minutário): (a) o campo que IDENTIFICA no sistema externo —
  `PostoServico.tirvu_id` fora, senão dois postos com o mesmo ID fazem a
  importação do Tirvu atualizar o posto ERRADO, calada, porque ela casa por ID
  e não sabe qual dos dois é o certo; (b) o ALVO (`cargo_alvo`/`posto_alvo_id`/
  `candidato_alvo_id` do modelo de documento), senão ficam dois modelos
  disputando o mesmo destino e `modelos-aplicaveis` devolve os dois; (c) o
  JULGAMENTO feito sobre o original (as análises de match da vaga), que
  pareceria analisado sem ninguém ter analisado. **O que SE copia é o
  trabalho**: corpo do modelo, `documentos_kit` e creche do posto (posto sem
  kit = gente admitida sem assinar o termo de VT), tags do minutário (sem elas
  a cópia some dos filtros onde o original aparece). Coberto por
  `test_duplicar.py`, validado por 4 mutações.
- **Desativar em massa RECUSA oferecendo a saída — nunca só o bloqueio** (v2.87,
  `papeis.py::alternar_ativo`): papel inativo não concede nada, então desativar
  um papel EM USO cortaria o acesso de várias pessoas de uma vez e em silêncio
  (o sintoma seria "403 em tudo", longe da causa). O 409 vem com
  `destinos` — os papéis ativos e o que cada um concede — e a rota aceita
  `migrar_para`, movendo as pessoas e desativando **no mesmo ato**, para não
  existir a janela em que elas ficam num papel que já não vale. Recusar sem a
  saída deixa quem opera com o problema na mão: teria de sair da tela, conferir
  os papéis um a um e voltar. Vale para qualquer bloqueio de "X está em uso" —
  a alternativa cabe no mesmo lugar onde o bloqueio apareceu. ⚠️ **A checagem
  de `ativo` mora em `permissoes_do_usuario`, não na tela**: esconder o botão
  deixaria a rota respondendo 200 a quem souber a URL, que é a diferença entre
  controle e aparência de controle.
- **Rota nova sob `/rh/` DECLARA a permissão — `requer_rh` só autentica**
  (v2.86, `services/permissoes.py` + `auth_rh.py::exige`): até aqui a única
  proteção de 476 rotas respondia *"está logado?"*, então quem entrasse no
  painel podia efetivar, desligar em lote, exportar 1.171 CPFs, baixar a
  auditoria e **criar outro administrador**. Hoje cada rota declara
  `Depends(exige("chave"))` e o `test_permissoes_declaradas.py` reprova no CI a
  que não declarar — **rota sem permissão não é liberada por padrão**, senão
  "esqueci de declarar" e "decidi que é livre" ficam indistinguíveis, e a
  diferença só aparece quando alguém acha a URL. As 9 isenções (perfil próprio,
  login, callbacks OAuth) estão na lista `SEM_PERMISSAO` **com justificativa**.
  Três regras que NÃO devem ser afrouxadas: (1) o eixo é a **natureza do ATO**,
  não o arquivo — `colaboradores.py` tinha, sob o mesmo router, o `GET` que
  lista e o `POST .../desligar`, e um `GET` que devolve a base com CPF é
  `dados:exportar_base`, nunca `:ler`; (2) o **superadmin IGNORA a checagem**
  em vez de ter todas as caixas marcadas — com lista, módulo novo nasceria
  DESMARCADO para ele e o dono levaria 403 na própria casa; (3) papel que não
  resolve devolve conjunto **VAZIO, que nega** — padrão permissivo faria papel
  quebrado passar por administrador, e acesso a MAIS ninguém reporta. Ao criar
  permissão nova, acrescente ao `PERMISSOES` **antes** de usá-la: o `exige`
  confere a chave na IMPORTAÇÃO do módulo (derruba o boot nomeando o erro, em
  vez de virar 403 em produção que ninguém liga à causa).
- **As DUAS portas do primeiro usuário precisam do MESMO papel** (v2.86, pego
  pelo CI): o primeiro admin nasce de `auth_rh.py::criar_primeiro_usuario` (tela)
  OU de `core/bootstrap.py::criar_admin_inicial` (`.env`, provisionamento
  automatizado) — as duas dividem o portão "a tabela está vazia". Acertei o
  papel só na primeira, e o admin do `.env` caiu no default `rh`: instalação
  provisionada **sem ninguém capaz de gerir papéis**, e sem tela para corrigir,
  porque `config:usuarios` é justamente o que falta. Localmente passou (meu banco
  não tinha o admin do `.env`); no CI o `test_email_templates` levou 403 em
  `config:escrever`. Ao mexer no papel/atributo do primeiro usuário, confira os
  DOIS pontos — e note que **usuário criado em teste também precisa de `papel`**:
  `dependency_overrides[requer_rh]` continua alcançando o `exige` (que depende
  dele), mas o objeto devolvido sem papel faz `permissoes_do_usuario` devolver
  conjunto vazio e negar tudo. O `preparar_ambiente_local.py` corrige o papel
  inclusive de usuário ANTIGO, senão um banco local pré-v2.86 responde 403 em
  metade das telas e o sintoma parece defeito de layout (v2.60).
- **Papel de fábrica é PADRÃO, não estado — o que o superadmin editou fica**
  (v2.86): `PAPEIS_PADRAO` alimenta só a semeadura; a lista escolhida mora em
  `Papel.permissoes`. Módulo novo **não** concede acesso sozinho a papel que
  alguém já ajustou — permissão que aparece sem ninguém conceder é o oposto do
  controle que o modelo existe para dar. Quem sempre recebe o módulo novo é o
  superadmin, porque `pode()` nem consulta lista. **Migration promoveu todo
  usuário existente a superadmin de propósito**: rebaixar no deploy tiraria
  acesso de quem estava operando, sem ninguém para reconceder — a instalação
  ficaria travada por fora, e segurança que quebra o trabalho é revertida às
  pressas. O degrau real acontece na TELA.
- **Nome repetido em domínio diferente colide em SILÊNCIO no `api.js`** (v2.86,
  dois de uma vez): já existia o componente `Papeis` (papel com que se ASSINA um
  documento — Contratado, Testemunha) e as chaves `papeis`/`criarPapel`/
  `editarPapel`. Chave repetida em objeto literal **sobrescreve a anterior sem
  erro nenhum**: o build passa e três telas (Config, Modelos, RoteiroAssinatura)
  passariam a chamar a rota errada. Antes de acrescentar chave ao `rh` do
  `api.js`, `grep` pelo nome — e prefira o sufixo do domínio
  (`papeisAcesso`) a disputar o nome curto.

- **Descrições dos MÓDULOS mudaram de lugar** (2026-08-09): o que cada módulo
  é e como funciona (Entrevistas, Creche, Telemetria, Provas, Match, Desempenho,
  Desenvolvimento, Banco de Talentos, mini-CRM, IA de texto, Minutário, Alertas)
  vive agora em `backend/app/CLAUDE.md`, e o DashPlanilha em
  `frontend/src/rh/CLAUDE.md` — carregam sozinhos quando se trabalha ali. As
  armadilhas de FALHA SILENCIOSA ficaram aqui de propósito: elas precisam ser
  lidas antes de se saber em qual diretório se está.
- **Obrigatoriedade tem TRÊS camadas e mora fora do slot** (v2.80,
  `services/exigencias.py`): fábrica → padrão da casa (config dinâmica) →
  exceção da pessoa (`Candidato.exigencias`), a mais específica vencendo e a
  ausência HERDANDO (`None` é silêncio; `False` é decisão de dispensar).
  ⚠️ **NÃO guarde a decisão em `SlotDocumento.obrigatorio`**: a
  `sincronizar_slots` REESCREVE aquele campo a cada execução e o wizard salva a
  cada 900ms — a dispensa sumiria sozinha, em silêncio. O slot é o estado do
  ENVIO; a regra mora no candidato. `aceite_lgpd`, `pessoais.email` e
  `documentos.cpf` não se desmarcam: sem eles não há base legal, código de
  assinatura nem casamento de CPF, e o fluxo quebraria LONGE dali. O filtro de
  pendências fica no FIM de `pendencias_da_ficha` (peneira sobre o resultado),
  não espalhado nas 12 verificações.
- **Asserção de 422 precisa dizer POR QUÊ foi recusado** (v2.80, achado por
  mutação): tirar o guard de `SEMPRE_OBRIGATORIOS` não fez o teste falhar —
  aquelas chaves também não estão no catálogo, então caíam em
  `chave_desconhecida`, 422 igual. **Conferir só o status code faz o teste
  passar com a proteção removida.** Afirme sobre o `detail`. Corolário: valide
  na ORDEM certa (o guard do sistema ANTES da checagem de catálogo), senão a
  proteção real some no dia em que a chave entrar na lista.
- **Documento de kit é POR POSTO — cobertura precisa da porta avulsa** (v2.79,
  `revisao.py::acrescentar_documento_especifico`): *"um intermitente precisou
  dar cobertura na presidência da República; não estava fácil marcar para
  emitir os documentos específicos"*. Os documentos EXISTEM desde a v1.17 e são
  selecionáveis — mas em `PostoServico.documentos_kit`, e quem faz cobertura
  não está lotado no posto que os exige. As saídas eram lotá-la lá (muda o
  VÍNCULO para emitir um papel) ou marcar o kit no posto dela (exigiria aquilo
  de todo mundo ali). A rota acrescenta UM documento a UMA pessoa, sem tocar em
  posto. Quatro travas: a lista vem do MESMO
  `postos.DOCS_ESPECIFICOS_DISPONIVEIS` (lista paralela divergiria);
  **só o catálogo entra** — aceitar qualquer valor do enum deixaria criar um
  SEGUNDO `termo_vt`, que é desconto de 6% em folha; motivo obrigatório, com o
  POSTO DA PESSOA na auditoria (*"lotada em X, assinou o kit de Y"*); e 409 em
  assinatura viva, dizendo se está pendente ou assinada.
- **Botão DESABILITADO que anuncia estado é ruído, não controle** (v2.78,
  terceira tentativa no mesmo botão): a v2.75 deixou dois "fechar" (coluna +
  painel); a v2.75.1 tirou um e desabilitou o outro quando a ficha abria —
  *"não precisa ter um botão dizendo que está aberto e outro para fechar"*. O
  certo é **um botão que ALTERNA**, com rótulo dizendo o que ACONTECE ao clicar
  ("Mais detalhes" / "Menos detalhes"), nunca o estado atual. Ao remover o
  controle duplicado, **tire também a prop que o alimentava** (`aoFechar`),
  senão fica declarada sem uso.
- **Trocar o TEXTO de um botão de ação exige revisar a largura da coluna**
  (v2.78): `.acoes-candidato:has(> :only-child)` fixa `width` em `ch` —
  proporcional ao rótulo. "abrir" cabia em 12ch; "Menos detalhes" saiu cortado
  ("lenos detalhe" no print do Bruno), e o `text-overflow: ellipsis` da regra
  vizinha ESCONDE o corte em vez de denunciá-lo. Rótulo cortado é rótulo que
  não se lê.
- **A `td` do detalhe não pode ter borda nem fundo próprios** (v2.78, o
  "risquinho"): ela mede a largura VISÍVEL do container (`100cqw`, 1060px)
  enquanto a tabela pode ser mais larga (1370px), então a borda inferior era
  desenhada só até onde a `td` chega e a diferença virava uma faixa clara à
  direita da linha aberta. Quem pinta o painel é o `.rh-conferencia` dentro
  dela.
- **`flex: 1 1 X` muda de EIXO quando o contêiner vira coluna** (v2.77): a
  `.rh-escala-rotulo` é `flex: 1 1 12rem` — numa linha horizontal isso é "ocupe
  a largura que sobrar", certo; no celular, onde a `.rh-escala-linha` vira
  `flex-direction: column`, o mesmo `1 1` passa a mandar na ALTURA e o rótulo
  esticou para 192px com 3 linhas de texto, abrindo um vazio de ~130px entre a
  pergunta e os botões de nota. É a v2.63 (`trocar display invalida regras de
  filho`) no eixo oposto: ao mudar `flex-direction` numa media query, revise
  `flex` E `justify-content` dos filhos — `space-between` numa coluna distribui
  VERTICALMENTE.
- **`title` não abre no CELULAR — informação que decide vai no `:focus`**
  (v2.77): a âncora que separa "4 — Evidência forte" de "3 — Atende" só existia
  no `title` do chip e num `<details>` no fim do bloco. Sem mouse, o `title` não
  existe; e informação que sustenta a NOTA precisa estar onde a nota é dada.
  Use `data-dica` + o mecanismo do `Ajuda.jsx` (CSS puro, `:hover` no desktop e
  `:focus` no toque) em vez de inventar popup. Balão para CIMA quando houver
  campo de texto logo abaixo — para baixo ele cobre o que a pessoa vai escrever.
- **`<details>` FECHADO não renderiza o conteúdo — CSS não reabre** (v2.76.2,
  *"não voltaram os filtros de select com busca"*): ao recolher a barra de
  filtros no celular, neutralizei a caixa no CSS (`display: contents` +
  `summary` escondido) achando que no desktop tudo voltaria ao normal. Não
  volta: quem esconde o conteúdo de um `details` fechado é o NAVEGADOR, e os 9
  filtros ficaram no DOM com altura zero. O estado tem que nascer certo no JSX
  (`open={!ehCelular}`, com `matchMedia` + listener para o giro do aparelho).
  **Corolário para o teste**: afirmar que o elemento EXISTE não basta — meça
  `getBoundingClientRect().height > 0`. E régua de layout apontada só para
  celular não vê regressão de desktop; as três que existiam mediam 390px.
- **Nada que CRIA mora em bloco que se RECOLHE** (v2.76.1, reprovação do Bruno:
  *"você tirou os botões de cadastro do banco de talentos, como assim?"*): o
  "＋ Cadastrar talento" era passado em `acoesFiltro` e renderizado DENTRO do
  card de filtros; quando a v2.76 recolheu esse card no celular, ele sumiu da
  tela **sem nunca ter sido removido do código**. Filtrar refina o que se vê;
  agir cria e leva embora — naturezas diferentes, cards diferentes
  (`.dash-acoes`). Ao recolher qualquer bloco, liste o que está dentro dele.
- **`body.scrollWidth` NÃO detecta tudo que vaza pela lateral** (v2.76.1): a
  régua de largura dizia zero enquanto o Bruno via a ficha *"extrapolando as
  laterais da tela mobile"* — o vazamento era de um elemento DENTRO do painel de
  detalhe (`right=471` numa viewport de 390px), e overflow contido não alarga a
  página. Meça a **borda direita** dos elementos
  (`getBoundingClientRect().right > innerWidth`), com os painéis ABERTOS. Causa
  daquele caso: `.dash-detalhe` usa `width: 100cqw`, certo no modo TABELA (o
  container rola de lado) e errado no modo CARD, onde mede algo mais largo que a
  tela. **Ordem para ganhar espaço vertical**: compactar espaçamento → recolher
  o que é CONSULTA (filtros, texto explicativo) → encurtar rótulo
  (`.so-desktop`) → só então esconder. **Nunca esconder ação.**
- **No celular, mede-se a ALTURA DO CABEÇALHO — não só a largura** (v2.76,
  *"a navegação está feia demais para mobile, horrível"*): as réguas existentes
  mediam estouro lateral e altura de LINHA, e nenhuma via o defeito real —
  quanto se rola até o primeiro registro. Medido em 390px: **Talentos 1212px**,
  Colaboradores 1092px, Entrevistas 1039px, em telas de 844px de altura. Uma
  tela e meia de rolagem para ver o primeiro item. A causa é sempre a mesma:
  layout de desktop apenas EMPILHADO. As 4 regras estão no bloco final
  `@media (max-width: 760px)` do `styles.css` e valem para toda tela com
  `.rh-painel` + `DashPlanilha` — (1) filtros nascem RECOLHIDOS (chegavam a
  643px sozinhos) com contador dos ativos, senão a lista parece recortada sem
  explicação; (2) cards de métrica em 2 colunas; (3) botões do `.rh-topo` com
  **`flex: 1 1 0`** — com `auto` cada um parte da largura do próprio texto e o
  primeiro enche a tela; (4) título e respiro menores. No desktop nada muda
  (`display: contents` no `<details>`). Teto travado em teste: § 9.1 do
  `08-sistema-de-design.md` e `tabelas-cabem-na-tela.spec.js`.
- **Cabeçalho no limite quebra com QUALQUER mudança — e a culpada parece ser a
  última** (v2.85.1): o CI reprovou a régua de mobile logo após a troca de fonte
  (Admissões em **639px** contra o teto de 600), e a leitura óbvia era "a fonte
  nova é mais alta". **Medido: 1px de diferença** entre Yu Gothic, Noto Sans JP
  e Outfit. A causa real vinha da v2.76: **8 cards de métrica em 2 colunas são 4
  fileiras** — 275px de cabeçalho, com altura VARIÁVEL conforme o rótulo mais
  longo, então um dado diferente no banco muda o layout (aqui media 592px, no CI
  639). No celular eles viram **fila que rola de lado** (592 → **384px**).
  Rolar MÉTRICA de lado é aceitável — é consulta; a regra "nunca esconder AÇÃO"
  (v2.76.1) segue valendo para a `.dash-acoes`. A régua de borda direita ganhou
  a mesma isenção do `.dash-scroll`: o conteúdo fica fora da VISTA, não fora da
  PÁGINA. **Antes de culpar a mudança da vez, meça a contribuição dela** — e
  desconfie de teto que passa no seu banco e falha no CI: é altura dependente de
  DADO.
- **A fonte do sistema é CONFIGURÁVEL, e a pilha mora no SERVIDOR** (v2.85,
  `services/marca.py::FONTES`): padrão **Yu Gothic**, escolhível em
  Configurações → Identidade visual. ⚠️ **Yu Gothic é PROPRIETÁRIA da
  Microsoft** — não existe no Fontsource/Google Fonts e embutir o `.ttf` do
  Windows seria violação de licença num repo PÚBLICO; por isso ela vem
  acompanhada da **Noto Sans JP** (livre, embutida, ~13KB no subset latino), que
  atende Android/iPhone/Linux — a maior parte do público do wizard. **Só o
  catálogo entra** (422 `fonte_desconhecida`): a pilha vira o `--fonte` de TODA
  tela, e fonte inexistente **não dá erro**, só deixa a tela estranha. A rota
  `GET /marca/aparencia` é **pública** porque o wizard não tem login — sem ela a
  customização valeria só no painel. **Os DOCUMENTOS não mudam**: o hash do ato
  de assinatura é calculado sobre o PDF do fpdf2, e trocar a fonte faria
  manifesto emitido apontar para arquivo que não se reproduz (há teste varrendo
  os geradores). Ao mexer em tipografia: **use `var(--fonte)`, nunca a lista
  literal** — o `body` a repetia, e trocar só o token deixaria a fonte valer em
  tudo menos no texto corrido.
- **Teste estrutural de CSS tem que IGNORAR comentário** (v2.85, furo pego por
  mutação): a asserção `"var(--fonte)" in corpo_do_body` passava verde com a
  pilha literal de volta — porque casava com o `var(--fonte)` escrito no
  COMENTÁRIO que explica a regra. É a v2.71 (`_tem_no_codigo`) na variante CSS:
  remova `/* … */` antes de afirmar, e afirme sobre a LINHA da declaração.
- **Rota PÚBLICA que cria administrador: o portão é o BANCO, e o teste afirma
  sobre o ESTADO** (v2.84, `api/auth_rh.py`): o primeiro admin nascia do `.env`,
  o que obrigava a escrever senha em arquivo e — em repositório PÚBLICO —
  publicava o e-mail de quem opera. Hoje, com `select(UsuarioRH).limit(1) is
  None`, o painel abre um cadastro guiado. As duas rotas
  (`GET/POST /rh/auth/primeiro-acesso`) são públicas **por necessidade** (não há
  quem autentique antes do primeiro usuário), então a ÚNICA coisa que separa
  "instalação nova" de "qualquer um cria admin na produção" é aquela checagem.
  **Se ela cair, nada na tela denuncia** — a tela fica idêntica e o defeito só
  aparece quando alguém achar a rota. Por isso o teste confere o BANCO
  (`quantos == 1`) além do 409: a mutação que remove o portão devolve 200 **e
  cria o segundo usuário**, e só a asserção de estado prova que a recusa é real.
  O `.env` (`RH_ADMIN_EMAIL`/`_PASSWORD`) segue válido para provisionamento
  automatizado e divide o MESMO portão, então as duas portas não se atropelam.
  **Teste com pré-condição de banco vazio precisa de banco PRÓPRIO no CI** (o
  principal já tem o admin do job) e tem que ANUNCIAR a pré-condição quebrada,
  em vez de falhar numa asserção que não fala da causa.
- **`EmailStr` RECUSA o TLD `.local`** (v2.84): não é domínio público, e o
  `email-validator` reprova. Ao trocar e-mail de teste por um genérico, use
  `exemplo.com.br` — `admin@exemplo.local` faz o login devolver **401**, que
  aparece como "senha errada" e manda procurar no lugar errado (a armadilha da
  v2.71 com outra causa).
- **Marcador de variável DIGITADO à mão erra em silêncio — insira pelo cursor**
  (v2.82, `frontend/src/CampoComVariaveis.jsx`): as variáveis eram uma LISTA NO
  TOPO da tela; a pessoa lia `{{nome_social}}`, voltava ao texto e digitava de
  memória, com as duas chaves de cada lado. `fichas.aplicar_variaveis` é regex
  `{{(\w+)}}` e só substitui o que casa com chave conhecida — então
  `{{nome_socal}}` (sem o "i") **fica no texto como está** e sai impresso no PDF
  que a pessoa assina; num e-mail de acesso, `{{codigo}}` mal digitado significa
  que ninguém recebe o código. É a família do defeito silencioso: nada quebra, o
  resultado é que está errado. Duas decisões que fazem o seletor funcionar: (1)
  **a posição vem do DOM** (`selectionStart` lido do próprio campo, guardado no
  `onBlur`) — estado do React se perde quando o campo perde o foco, que é
  exatamente o que acontece ao clicar no seletor; (2) **o foco volta ao texto**
  com `setSelectionRange` dentro de `setTimeout(…, 0)` — o React ainda não
  repintou o valor novo quando o `onChange` retorna, e mexer na seleção antes
  disso não tem efeito. Ao criar editor novo que aceite variável, use este
  componente nos DOIS campos (título/assunto **e** corpo): metade ligada parece
  ligada, e o `test_campo_variaveis.py` cobra `count("<CampoComVariaveis") >= 2`.
- **Confirmação de AÇÃO é `<Aviso>` flutuante; `.alerta` inline é para ESTADO**
  (v2.75, `frontend/src/Aviso.jsx`): *"esses avisos tem lugares que ele aparece
  no topo enquanto estamos lá embaixo na tela, ou seja nem aparecem"*. A regra
  da v1.96/v2.47 ("a mensagem vai onde a PESSOA está olhando") vinha sendo
  corrigida tela a tela e voltava em cada tela nova — são 122 usos de
  `.sucesso`/`.alerta` em 47 arquivos. O `<Aviso>` é `position: fixed`: fora do
  fluxo, sempre no campo de visão. Segura no hover (e RECOMEÇA a contagem ao
  sair, não retoma os últimos ms), fecha no ✕ ou Esc, e tem barra de tempo para
  o sumiço não parecer aleatório. **Não converta os `.alerta` que DESCREVEM a
  tela** (banco atrasado em Config, impedimentos da ficha): aquilo se consulta
  enquanto se trabalha, e flutuar+sumir esconderia o que a pessoa precisa ler.
  O critério é: respondeu a um clique → `<Aviso>`; explica o que está ali →
  inline.
- **Dois controles para a mesma escolha = um deles não decide nada** (v2.75,
  duas vezes na mesma tela): (1) os botões "+ Triagem" e "+ Entrevista" abriam o
  MESMO formulário e só mudavam o valor inicial de um campo "Tipo" que
  continuava editável ali dentro — *"por que tem os dois, se ambos abrem a mesma
  coisa?"*; (2) o "fechar" da coluna de ações e o "✕ fechar" do painel faziam a
  mesma coisa. É a regra "um assunto, um controle" (v2.30) aplicada a AÇÃO, não
  a filtro. Quando sobrar um só, escolha **o mais perto do conteúdo**: o ✕ do
  painel fica ao lado do que se está lendo; o da coluna estava lá na direita,
  com o painel já empurrando a linha para longe.
- **A primitiva de 2 colunas quebra o ALINHAMENTO quando os lados têm alturas
  diferentes** (v2.75, reprovação do Bruno: *"por que escrever o título duas
  vezes? o UX está horrível"*): a ficha de entrevista tinha as 4 competências à
  esquerda e os 4 textos de justificativa à direita, cada lado repetindo os
  nomes. Além da duplicação, a pergunta de uma competência ocupa 2 linhas e a da
  outra 1 — então o campo da 2ª aparecia na altura da 3ª, e a pessoa escrevia no
  lugar errado, **num documento que ela assina**. É a v2.66 numa variação: aquela
  primitiva serve conteúdo EMPARELHADO, e o par era *nota ↔ justificativa DAQUELA
  competência*, não "a lista de notas" ao lado de "a lista de textos".
  Emparelhando de verdade (um bloco por competência), o alinhamento deixa de ser
  sorte. **Ao ver dois `.map()` sobre a MESMA lista em colunas irmãs, desconfie:
  quase sempre é um bloco só.**
- **Tela que existe mas ninguém acha não está entregue** (v2.75, *"cadê a parte
  onde posso fazer CRUD de mais roteiros?"*): o CRUD de roteiros vive em
  Configurações desde a v2.66 e **nada apontava para ele** de onde o trabalho
  acontece. Módulo com tela de configuração própria precisa de atalho a partir
  da tela de USO. Detalhe que morde: a aba de `Config.jsx` vem do
  `localStorage` (`rh_config_aba`), não da URL — navegar sem gravar a
  preferência abre a última aba usada, e o atalho parece não funcionar.
- **Promessa na TELA sem rota atrás não existe** (v2.74, cobrado pelo Bruno): a
  v2.73 escreveu no formulário *"o currículo pode ser anexado depois, pela ficha
  da pessoa"* — e **não havia rota para isso**. A única de upload era a PÚBLICA,
  autorizada por `upload_token` com TTL de 30 min emitido no cadastro público;
  o RH não tem token nenhum. Ninguém percebe, porque a tela não acusa: é a
  família do "documento que não nasce" (v2.69) e do worker que não roda (v2.66).
  **Ao escrever uma instrução na interface, `grep` pela rota que a cumpre.** Hoje
  existe `POST /rh/talentos/{id}/curriculo`, e as duas portas (pública e do RH)
  compartilham `_guardar_curriculo` — duplicar faria divergirem na 1ª mudança.
  Corolário: **troca de arquivo com extensão diferente muda a KEY**, e o antigo
  vira órfão no storage (fora do alcance da tela E do expurgo) se não for
  removido — mesmo defeito que o teste do anexo de entrevista pegou na v2.72.
- **`api.x()` que não existe DERRUBA A TELA — e o `.catch` não salva** (v2.73,
  defeito visto pelo Bruno em produção): `EntrevistasRH` chamava
  `api.talentos()`, função que **nunca existiu** (a certa é `listarTalentos`), e
  clicar em "+ Triagem" caía no ErrorBoundary. O `.catch(() => {})` ao lado não
  protegia nada — `undefined()` é `TypeError` **SÍNCRONO**, estourado antes de
  existir promessa, e exceção de render apaga a tela INTEIRA. Mesma família da
  `prop` inventada (v2.64) e da classe fantasma (v2.25): o JSX fica plausível e
  o build passa. Hoje o `test_api_front_existe.py` varre o JSX e reprova no CI.
  **Corolário que quase escapou**: as rotas `/rh/talentos`, `/rh/vagas` e
  `/rh/candidatos` devolvem **LISTA PURA** (`-> list[dict]`), e o código lia
  `r.itens || []` — mesmo sem o `TypeError`, os três seletores abririam VAZIOS,
  sem erro nenhum. Ao consertar chamada quebrada, confira também o FORMATO que a
  rota devolve; seletor vazio parece "não há dados cadastrados".
- **Cadastro FEITO PELO RH não carimba consentimento** (v2.73,
  `talentos.py::cadastrar_pelo_rh`): no formulário público a pessoa marca "li e
  concordo"; na importação o carimbo vem da planilha. Quando o RH cadastra à
  mão, **ninguém marcou nada** — então `consentimento_lgpd_em` fica NULO e
  `cadastrado_por_id`/`_nome` (SNAPSHOT) dizem quem assumiu. É o precedente da
  `AutorizacaoEquipe` e do manifesto assistido (v2.56): **o registro descreve o
  ato REAL, nunca a versão conveniente**. Carimbar ali passaria em qualquer
  revisão de código — o cadastro funciona igual — e o que se perde é a verdade
  de um registro de LGPD. Na ficha isso é TERCEIRO ESTADO ("sem aceite —
  cadastrado por X"), nunca travessão: travessão não distingue "não temos o
  dado" de "não houve aceite, e sabemos por quê" (lição do creche, v2.27/v2.54).
- **`.chip` não quebra linha — em coluna de tabela ele estica tudo** (v2.72.3):
  `white-space: nowrap` é certo para status e contagem (partidos ficariam
  feios), mas a coluna Tags recebe a **tag de reaproveitamento**, que o sistema
  gera do cargo da vaga (`reaproveitar: <cargo>`). Com o cargo mais numeroso da
  base real — *"Auxiliar de Serviços Gerais"*, 18 pessoas — são **41
  caracteres**, e a tabela de Talentos ia de 1002px para 1049px numa área de
  1004px. **O teto do chip tem que ser ABSOLUTO (`14ch`), não `max-width:
  100%`**: a largura da `td` é calculada A PARTIR do conteúdo, então `100%`
  acompanha o chip que cresce e não limita nada (medido: continuava em 256px).
  Texto inteiro no `title`, como manda a v2.59.
- **No modo CARD o `-webkit-line-clamp` NÃO funciona — corte por `max-height`**
  (v2.72.3): a regra do corte é `td.dash-quebra > .dash-corta`, mas no card a
  `td` vira `display: flex` **e o navegador BLOCKIFICA o `.dash-corta`**
  (computed `flow-root`), engolindo o `-webkit-box` — ele resiste até a
  `display: -webkit-box !important` inline. É o mesmo mecanismo da v2.60 (que
  registrou isso para a `<td>`) num lugar novo. Use `max-height`, que não
  depende de `display`. E são **2 linhas** no card contra 3 na tabela: ali as
  células ficam lado a lado numa grade e a mais alta ESTICA as vizinhas (3
  linhas = 249px, acima do teto de 240; 2 linhas = 226px).
- **Entrar na lixeira e VOLTAR dela são DUAS coisas** (v2.72.2,
  `api/lixeira.py::classes_restauraveis`): `mandar_para_lixeira(db, obj, "x",
  ...)` guarda o snapshot e faz o registro sumir da tela — mas restaurar usa um
  MAPA `entidade → modelo`, e o que não está lá responde `422
  entidade_desconhecida`. Estava assim para **SEIS das oito** entidades (vaga,
  prova, item de banco, papel de assinatura, roteiro de entrevista, teste de
  candidato): a lixeira era via de mão única. Ninguém percebeu porque **a
  exclusão funciona** e o item aparece listado com rótulo e data, igualzinho aos
  que voltam — o RH só descobriria no dia em que precisasse desfazer, o único
  dia em que a lixeira importa. Aconteceu seis vezes porque nada liga as pontas:
  quem escreve a exclusão num módulo novo não tem motivo para abrir o
  `lixeira.py`. Hoje o `test_lixeira_restaura.py` varre as chamadas em
  `app/api/` e reprova nomeando a órfã. **Ao mandar algo novo para a lixeira,
  acrescente ao mapa na MESMA leva** — é o par `documentos_catalogo`/gerador da
  v2.67 em outra roupa.
- **Mutação que MATA o teste parece aprovação** (v2.72.2): a mutação que fazia o
  `_reconstruir` aceitar qualquer entidade estourava no `INSERT`, e o
  `TestClient` **repropaga a exceção do servidor** — o script morria no meio,
  sem imprimir nenhum "FALHOU", e a saída vazia passava por sucesso. Em teste
  que exercita CAMINHO DE ERRO de rota, use
  `TestClient(app, raise_server_exceptions=False)`: aí o 500 vira resposta e a
  asserção pode reprová-lo. Vale a regra geral: depois de aplicar mutação,
  confira que o teste **imprimiu** o resultado — ausência de falha não é
  aprovação (a mesma lição do `grep -c` que devolve 0 na v2.64).
- **O `smoke_test` roda no CI (v2.72.1) — e o preço de ele NÃO rodar já foi
  pago**: são as 15 etapas ponta a ponta (cadastro → link mágico → autosave →
  declaração → upload com imagem virando PDF → conclusão → aprovação → dossiê),
  o único teste que percorre o caminho INTEIRO do candidato. Enquanto foi
  portão manual, ficou VERMELHO por três versões sem ninguém saber (v2.71 → a
  v2.72 o achou). Duas coisas ao mexer nele: (1) ele roda em **passo próprio**
  do `ci.yml`, depois dos testes rápidos e antes do Playwright — falha cedo e o
  log diz de cara que foi o smoke; (2) ele agora usa `os.environ.setdefault` e
  lê a credencial do ambiente, então **não chumbe `DATABASE_URL` nem senha**
  ali: dentro do container do CI o `localhost:55432` não existe, e o admin
  nasce com a senha do `.env` do job. **Antes de acrescentar teste ao
  `ci.yml`, rode-o DENTRO do container** (`docker exec -e PYTHONPATH=. <api>
  python tests/x.py`) contra um banco limpo — passar na sua máquina não prova
  nada sobre lá.
- **Teste ESCRITO e teste VERIFICADO são coisas diferentes — e o relatório que
  diz "coberto" mede o primeiro** (v2.72): o Módulo de Entrevistas entregou 4
  levas, 41 cenários e 9 mutações, com relatórios honestos… e **nenhum dos 5
  arquivos rodava no CI**. Ninguém mentiu: cada leva rodou os testes à mão, viu
  verde e seguiu. O que falta nesse ciclo é que a próxima pessoa a mexer no
  roteiro **não roda nada** — e o que quebra ali não dá erro, abre a ficha
  VAZIA. Ao fechar módulo, a pergunta não é *"escrevi teste?"* e sim *"o
  pipeline vai reprovar quem quebrar isto amanhã?"*. É a v2.48 na segunda
  reincidência. **Três defeitos concretos que só apareceram ao tentar
  incluí-los**: (1) três testes tinham a senha do admin LITERAL no login e
  dariam 401 no CI (a armadilha da v2.71, repetida sem ninguém notar) — no
  `test_entrevista_documentos` a mesma senha ASSINA a ficha, então a recusa
  apareceria como "senha errada", apontando para o lugar errado; (2)
  `test_match_persistencia` estava VERMELHO desde antes da v2.64, perguntado a
  cada relatório e nunca consertado; (3) o `smoke_test` estava quebrado desde a
  v2.71 e ninguém viu, **porque o smoke também não roda no CI**. Ao acrescentar
  teste ao `ci.yml`, rode-o antes com a senha do job (`RH_ADMIN_PASSWORD` do
  `.env` do CI) num banco NOVO — passar na sua máquina não prova nada sobre lá.
- **Asserção do CONTADOR GLOBAL amarra o teste ao tamanho do banco** (v2.72,
  `test_match_persistencia`): `executar_processamento` varre
  `select(Talento).where(status != "arquivado")` — a base inteira —, e o teste
  afirmava `r1["analisados"] == 1`. Vale na 1ª execução e nunca mais: a 2ª via
  os talentos que a 1ª deixou (156 processados, 2 analisados) e falhava com uma
  mensagem que não fala da causa. Recorte a asserção aos REGISTROS QUE O TESTE
  CRIOU e deixe o total como contexto da mensagem de erro, nunca como critério.
  **Não resolva apagando no fim**: teste que morre no meio numa falha legítima
  deixa o banco sujo do mesmo jeito, e ainda apaga a evidência do que falhou.
  Mesma família do "só passa em banco limpo" (v2.14).
- **Mudar `detail` de string para DICIONÁRIO quebra quem compara com a string**
  (v2.72): a v2.71 enriqueceu o erro do `upload_seguro._conferir` (passou a
  dizer a extensão recebida e a lista de aceitos — melhor para quem está com o
  celular na mão), e o `smoke_test` seguiu comparando
  `detail == "formato_nao_suportado"`. O comportamento estava CERTO e o teste
  vermelho, **por três versões**, porque o smoke é portão manual e não roda no
  CI. Ao enriquecer um `detail`, `grep` pela string antiga nos testes — e
  prefira afirmar sobre `detail["erro"]` tolerando campo extra.

- **Rota SÍNCRONA não pode virar `async` só para chamar função assíncrona**
  (v2.71): o `upload_seguro.ler_upload` é `async`, e as rotas de documento
  (`documentos.py`, `rh_ficha.py`) são `def`. A saída óbvia — pôr `async def` na
  rota — seria a errada: elas fazem **OCR pela Mistral com timeout de até
  120s**, e no FastAPI rota `def` roda no THREADPOOL enquanto `async def` roda
  no EVENT LOOP. Convertê-las jogaria a chamada bloqueante dentro do loop e
  **travaria a API inteira a cada envio** — trocaria um vazamento de arquivo
  temporário por indisponibilidade. Por isso existe `ler_upload_sync`, com as
  MESMAS garantias (o `close()` no `finally`) e a validação compartilhada em
  `_conferir`. Antes de acrescentar `async` a uma rota que já existe, veja o que
  ela faz de bloqueante — o teste `test_upload_fecha_spool.py` reprova se
  alguém "simplificar" removendo a variante síncrona.
- **Tirar formato perigoso da allowlist NÃO basta — a SAÍDA também serve o que
  já está gravado** (v2.71, `marca.py`): o upload de logo aceitava
  `image/svg+xml`, e o `_servir` devolvia com esse `media_type` em rota
  PÚBLICA, no mesmo domínio do painel. SVG é código: `<script>` dentro dele
  executa com acesso à sessão de quem está logado — XSS armazenado. Removê-lo
  só da entrada deixaria a logo enviada ANTES ainda sendo servida como SVG
  executável; foi preciso tirar também do mapa do `_servir`, para ela cair no
  `image/png` do padrão. Ao remover formato por segurança, pergunte sempre o
  que acontece com os arquivos que já entraram.
- **Teste estrutural que busca no TEXTO acha o próprio comentário** (v2.71): a
  primeira versão do `test_upload_fecha_spool` reprovava procurando
  `up.file.read()` no arquivo — e casava com o comentário que EXPLICA a
  correção. O mesmo com `"tipo": "application/pdf"`, que o docstring do
  `webhook_email.py` mostra como exemplo CERTO de saída para um `.pdf`. Teste
  assim reprova a documentação do próprio conserto, e o reflexo é apagar o
  comentário. Use um filtro que ignore comentário e docstring (`_tem_no_codigo`)
  quando a asserção for sobre AUSÊNCIA de um trecho.
- **Senha literal em teste o amarra a UM banco** (v2.71): `test_documentos_catalogo`
  e `test_email_templates` tinham `'senha': 'senha-teste-123'` escrita na linha
  do login, embora o `os.environ.setdefault` logo acima já respeitasse o
  ambiente. No CI o admin nasce com a senha do `.env` do job, então o login
  devolvia 401 e o teste morria em `KeyError: 'token'` — erro que não diz nada
  sobre a causa. **Foi o que impediu esses dois testes de entrarem no CI.**
  Leia a credencial do ambiente e AFIRME o login com mensagem explícita; um 401
  tem que dizer "confira RH_ADMIN_EMAIL/PASSWORD", não estourar num dict.
  (Lembrete: `criar_admin_inicial` só cria **se a tabela estiver vazia** — num
  banco de desenvolvimento com usuários antigos, o admin do `.env` não existe.)
- **`docker cp dir container:/destino` com destino EXISTENTE aninha em silêncio**
  (v2.71): vira `/destino/dir`, e o Python roda a cópia ANTIGA sem avisar —
  passei duas rodadas depurando um teste que eu já tinha corrigido. Copie o
  CONTEÚDO (`docker cp backend/tests/. container:/app/tests`), que é idempotente
  entre execuções.

- **Migration com INSERT cru NÃO herda default do modelo — e o `set -e` do
  entrypoint transforma isso em queda TOTAL** (v2.70, incidente de 2026-08-06
  entre 7h e 9h): a `d6f8b2c4e5a7` inseria em `assinatura` sem listar
  `otp_tentativas`, que é `NOT NULL` **sem `server_default`** (o `default=0`
  mora no modelo Python; SQL cru não passa pelo ORM). Em banco VAZIO o
  `INSERT ... SELECT` insere zero linhas e passa VERDE — é o *"só passa em banco
  limpo"* (v2.14) **de cabeça para baixo**: aqui o banco limpo ESCONDE o
  defeito, e todo teste local passou. Em produção, com gente real na base,
  `NotNullViolation`. O estrago não parou aí: o `docker-entrypoint.sh` roda
  `alembic upgrade head` ANTES do `exec uvicorn`, então o exit 1 abortava o
  script e **a API nunca subia** — cada restart repetia. O sintoma foi "não
  loga, o back não fala com o banco"; **o banco estava perfeito, não havia back
  nenhum**. Três defesas: (1) o entrypoint agora SEGUE EM FRENTE quando a
  migration falha (schema velho no ar > tela morta) e o `/api/health` denuncia
  com `migracoes.em_dia:false` — que é o que aquele campo, criado na v2.29 para
  este cenário, nunca pôde fazer, porque sem API não há /health para consultar;
  (2) `tests/test_migration_insert_cru.py` percorre a cadeia NA ORDEM de
  execução e cobra as colunas obrigatórias de todo `INSERT INTO` (validado por
  mutação; a ordem importa — sem ela reprovava `roteiro_entrevista.tipo`, que só
  passou a existir DEPOIS do INSERT que a "omitia"); (3) ao escrever backfill
  por SQL, confira as colunas `NOT NULL sem server_default` **no banco**, nunca
  no modelo. Em `assinatura` são `id`, `candidato_id` e `otp_tentativas`.
- **Migration já marcada como aplicada NÃO roda de novo — corrigir o arquivo
  conserta o futuro, não o presente** (v2.70): depois do conserto manual, o
  `alembic_version` da produção estava no head com a `d6f8b2c4e5a7` dada por
  aplicada, mas **sem as linhas do backfill**. Editar aquele arquivo só ajuda
  bancos novos. Para completar o que ficou faltando é preciso uma revisão NOVA
  (`e9c1a3f5b7d2`), com o mesmo recorte e **idempotente** (`NOT EXISTS`) — senão
  duplica em quem já recebeu. Ao consertar migration que já rodou em produção,
  pergunte sempre: *este banco vai reexecutá-la?* Quase sempre a resposta é não.

- **Documento com nome PARECIDO não é o documento — e a ausência não dá erro**
  (v2.69, feedback do Bruno: *"Ficha de integração não está sendo gerada para os
  efetivos"*): `gerar_docs_do_posto_e_regime` fazia `if candidato.regime ==
  "intermitente"` e mais nada, então o EFETIVO — a maioria dos admitidos — nunca
  recebeu ficha de integração. O que sustentou o engano por tantas versões foi o
  vizinho de nome: `informacoes_trabalhador` **parece** a ficha do efetivo e é
  outra coisa (ofício de direitos do kit INFRAERO, só em posto INFRAERO). A
  tupla `DOCS_INFORMATIVO` estava comentada como *"efetivo/INFRAERO = ..."*, e o
  comentário do modelo (`candidato.py`: *"Decide qual ficha de integração o
  colaborador assina"*) descrevia uma intenção que o código nunca cumpriu de um
  dos lados. **Documento que não nasce não gera erro em lugar nenhum**: ninguém
  abre uma tela e vê o que está faltando — é a família do worker que não roda
  (v2.66), onde o silêncio se confunde com "não havia nada a fazer". Hoje a
  fonte é `INFORMATIVO_POR_REGIME` (um mapa regime→documento, exaustivo por
  construção) e as duas fichas saem do MESMO `_gerar_informativo_integracao`, com
  a diferença isolada em `_CICLO_VT`/`_CICLO_VA`: variante nova não pode
  "esquecer" uma seção que a outra tem. Ao ver dois documentos com nomes
  próximos, confira o CONTEÚDO de cada um antes de assumir que cobrem um par.
- **Ficha de integração: o que muda por regime é o CICLO DE PAGAMENTO** (v2.69):
  efetivo apura **do dia 1 ao dia 30**; intermitente, **semanalmente** (pago até
  a quarta-feira da semana seguinte). É o único conteúdo que difere entre
  `informativo_efetivo` e `informativo_intermitente`, e sai num documento que a
  pessoa ASSINA — prometer o ciclo errado é errar sobre dinheiro. Os textos ficam
  em constantes fora do gerador de propósito: mudar um ciclo não deve tocar o
  outro por acidente. Trocar o regime invalida a ficha do regime anterior **se
  ainda não assinada** (assinada é peça de prova e permanece).
- **Enum reescrito à mão num segundo lugar ATRASA em silêncio** (v2.69):
  `solicitacao_assinatura.documento` listava os valores de `DocumentoAssinavel`
  literalmente, e já estava desatualizado — faltava `autodeclaracao_residencia`
  desde a v1.92. É o mesmo tipo do Postgres (`create_type=False`), então nada
  reclama: o valor só não existe para o SQLAlchemy daquele modelo. Derive de
  `[d.value for d in DocumentoAssinavel]`.

- **O FALLBACK serve para PREENCHER um campo, nunca para PEDIR uma permissão**
  (v2.68, pego pelo próprio teste): `config_dinamica.email_recrutamento()` cai
  no `smtp_from` quando a chave está vazia — certo para o `ORGANIZER` do `.ics`,
  que só precisa de um endereço qualquer. Usar a MESMA função para o `From` do
  Microsoft 365 pedia ao Graph permissão para enviar como a caixa **que já se
  é**: ele recusa igual (`ErrorSendAsDenied`), e o sistema avisava o RH que
  faltava liberar `Send As` de um endereço **que ninguém configurou** — ruído
  mandando mexer no tenant sem motivo. Por isso existem DUAS funções:
  `email_recrutamento()` (com fallback, para preencher) e
  `email_recrutamento_escolhido()` (sem, para pedir permissão). Ao reusar um
  getter "com padrão", pergunte se o consumidor vai PREENCHER ou vai PEDIR — no
  segundo caso o padrão mente.
- **Recusa por PERMISSÃO ≠ falha de ENVIO — e a carta tem que sair mesmo assim**
  (v2.68, `m365.enviar_via_graph`): é a regra da v2.00 na terceira variação. O
  Graph responde 403 `ErrorSendAsDenied` quando o `From` pedido não tem `Send
  As` liberado no tenant — erro PERMANENTE, que nenhuma retentativa resolve e
  que se conserta no admin do M365. Um 500 ou um timeout é transitório. Tratar
  os dois igual faria o RH achar que o sistema quebrou quando falta um clique no
  tenant, e mexer no lugar errado. O desenho: tenta com o remetente; **se e só
  se** a recusa for de permissão, reenvia da caixa conectada e devolve um
  `aviso` que a tela mostra. O convite SEMPRE sai — uma entrevista não se perde
  porque o tenant não foi configurado. Na tela o aviso é `.aviso-inline`
  (âmbar), **nunca** `.alerta` (vermelho): o e-mail saiu, e pintar de erro faria
  o RH reenviar, o que não muda nada. `enviar_email` continua devolvendo
  BOOLEANO (são ~40 call-sites); quem precisa do aviso usa `enviar_com_aviso`.
- **Chave de configuração sem ROTA e sem TELA não é configurável** (v2.68): a
  `email_recrutamento` nasceu na v2.67 lida pelo código, documentada no
  CHANGELOG… e **só preenchível escrevendo direto no banco** — não havia
  `GET/PUT` nem campo em lugar nenhum. Parece entregue em toda revisão de
  código, porque o consumo existe e funciona. Ao criar chave na config
  dinâmica, confira o par: `grep` pela chave em `app/api/` E em
  `frontend/src/`. **Vazio tem que ser valor VÁLIDO** na rota (é como se volta
  ao padrão) — `EmailStr` recusaria a string vazia e deixaria o RH sem como
  desfazer o que configurou.
- **Teste que exercita a função interna NÃO prova que o caminho real a usa**
  (v2.68, 2ª reincidência): a asserção do anexo do convite afirmava
  `_tipo_grafo("convite.ics") == "text/calendar"` e passava VERDE com a mutação
  que chumba `"application/pdf"` na mensagem entregue ao Graph — a função estava
  certa, e nada ligava uma coisa à outra. Mesma família do teste do `.ics` na
  v2.67 (chamava `_anexo_ics` em vez da rota) e do "comparar a resposta com ela
  mesma" da v2.64. **Substitua o LIMITE EXTERNO (o `httpx.post`), não as suas
  próprias funções**, e afirme sobre o objeto que o sistema realmente montou.
  Foi só isso que revelou que o caminho do Graph mandava TODO anexo como
  `application/pdf` — o defeito que a v2.41 consertou no SMTP, vivo aqui.
  (O `webhook_email.py:56` ainda tem o mesmo chumbo; fica registrado.)
- **Módulo que GERA documento entra no catálogo de documentos na MESMA leva**
  (v2.67, cobrado pelo Bruno: *"a cada documento novo gerado, ele deve compor o
  módulo de documentos também e todas as funcionalidades herdadas. bem como os
  templates de email"*). É a regra da v2.21 — e a v2.66 a cumpriu **pela
  metade**: pôs os 3 e-mails do Módulo de Entrevistas no `CATALOGO` de
  `email_templates.py` e deixou `grep -c "entrevista"
  services/documentos_catalogo.py` em **ZERO**, com o módulo gerando documento.
  Ninguém percebeu até ele cobrar, porque metade cumprida *parece* cumprida.
  Ao fechar módulo que produz PDF: entrada no `documentos_catalogo.py`, amostra
  com dados fictícios e download — não só o gerador.
  **Mas NÃO resolva isso acrescentando valor ao `DocumentoAssinavel`**: aquele
  enum é a lista do que o CANDIDATO assina. `api/rh_ficha.py:38` faz
  `_TODOS = list(DocumentoAssinavel)` e usa em `DOCS_POR_SECAO`, então editar os
  dados pessoais de alguém passaria a **invalidar a ficha de entrevista**; e
  `_docs_exigidos` faria a ficha virar pendência de assinatura no wizard. O
  catálogo tem `Origem` (famílias `admissao` × `entrevista`), e
  `_conferir_catalogo` reprova **no import** se um documento de entrevista virar
  valor do enum.
- **O DOSSIÊ varre `SolicitacaoAssinatura` SEM filtrar `origem`** (v2.67,
  `services/dossie.py`): qualquer roteiro multi-signatário `concluida` com
  `pdf_final_key` entra no dossiê do candidato, automaticamente. A ficha de
  entrevista assinada por ali teria ido junto — com as notas e as justificativas
  da seleção — para o documento que **circula** (cliente, pasta física). O
  § 15.4 proíbe explicitamente (*"não não. no dossiê de admissão não."*), pelo
  mesmo motivo que manteve resultado de teste fora do dossiê na v2.21. Por isso
  a assinatura da ficha mora em tabela PRÓPRIA (`assinatura_entrevista`), fora
  das três fontes que o dossiê lê (`Assinatura.pdf_key`,
  `SlotDocumento.arquivo_pdf_key`, `SolicitacaoAssinatura.pdf_final_key`).
  **Ao criar fluxo de assinatura novo, pergunte antes se ele deve aparecer no
  dossiê** — o default do código é "aparece", e o vazamento é silencioso: uma
  página a mais que ninguém confere. Coberto por mutação (0 → 2 páginas).
- **Teste que não EXECUTA a linha mutada não protege nada** (v2.67, duas vezes na
  mesma leva): (1) a asserção do `.ics` chamava `calendario.gerar_ics` DIRETO,
  com `duracao_min=e.duracao_min` escrito no teste — testava a biblioteca, não a
  LIGAÇÃO, e a mutação que chumbava `duracao_min=DURACAO_MIN` dentro do
  `_anexo_ics` passava verde; (2) o teste do "um padrão por tipo" só conferia
  listagens e nunca chamava `tornar-padrao`, então a mutação que fazia a rota
  desmarcar o padrão de qualquer tipo também passava. É a família da tautologia
  da v2.54/v2.64 numa variação nova: **a asserção tem que percorrer o caminho de
  produção**, não reproduzir a lógica dele ao lado.
- **Mutação suja o BANCO, e o estado sobrevive à restauração do código** (v2.67):
  a mutação do `tornar_padrao` desmarcou o `padrao` do roteiro de triagem
  semeado; depois de `cp backup` o teste continuou reprovando — reprovando
  **código correto**. Já tinha mordido na v2.66 (`resolver_roteiro`). Duas
  defesas: conferir o ESTADO do banco depois de rodar mutação, e escrever o teste
  para **consertar o piso antes de afirmar sobre ele**, em vez de depender de
  banco limpo.
- **Título de seção órfão no PDF: o `auto_page_break` do fpdf quebra por
  ELEMENTO** (v2.67, `entrevista_pdf._secao_junta`): ele garante que a FAIXA
  caiba na página, não que caiba a faixa **mais a primeira linha do que vem
  depois** — o título de uma competência ficava sozinho no pé da página 1 com a
  tabela dele abrindo na página 2. A extração de texto passava; só apareceu
  convertendo o PDF em IMAGEM e olhando (regra da v2.55). Reserve a altura do
  BLOCO antes de desenhar a faixa, como o `campo()` das fichas já faz.

- **Worker que não está nos DOIS arquivos de deploy simplesmente NÃO RODA em
  produção** (v2.66, achado ao pendurar o lembrete de entrevista): o
  `deploy/docker-compose.base.yml` rodava `avisar_vencimentos`, e o
  `deploy/portainer-stack.yml` — **o que sobe na VPS** — não. Ou seja, o aviso
  de certificação vencendo (Onda B, v1.83) nunca saiu em produção, e ninguém
  soube: worker que não roda não gera erro, gera SILÊNCIO, e silêncio se
  confunde com "não havia nada a avisar". É a terceira vez que este par de
  arquivos cobra (v2.25 alertas, v2.29 logs). **Ao criar ou mexer em worker,
  confira os DOIS** — e desconfie de qualquer worker cujo efeito você nunca viu
  acontecer na VPS.
- **Janela de varredura tem que ser MAIOR que a cadência do worker** (v2.66): o
  lembrete de entrevista nasceu com janela de 24h num worker que dorme 24h — a
  entrevista marcada para daqui a 23h ficaria invisível entre duas passadas e o
  lembrete nunca sairia, sem erro nenhum. Ficou em 36h. O anti-spam é o CARIMBO
  (`lembrete_enviado_em`), não a janela; então a janela pode ser generosa sem
  virar repetição. Vale para qualquer varredura com prazo.
- **Guard de rota não garante INVARIANTE de dado** (v2.66, achado rodando as
  próprias mutações): as rotas recusam arquivar e excluir o roteiro `padrao`,
  mas a mutação que removeu o guard deixou o padrão `arquivado` NO BANCO — e o
  estado sobreviveu à restauração do código. A partir dali `resolver_roteiro`
  devolvia `None` e **toda ficha de entrevista abriria vazia, sem erro**: a tela
  parece funcionar e a entrevista é conduzida sem roteiro, que é o oposto do que
  o módulo existe para garantir. Quando um dado é PISO de uma resolução em
  cascata, a última etapa precisa de rede de segurança própria — "as rotas não
  deixam" não é garantia, porque migration, acerto no banco e teste destrutivo
  não passam por rota.
- **Teste destrutivo deixa estrago para a próxima execução** (v2.66): o bloco de
  mutação arquivou o roteiro padrão e as falhas seguintes não tinham nada a ver
  com o que estava sendo testado — diagnóstico caro. Teste que MEXE em invariante
  do banco tem que (1) conferir a pré-condição e ANUNCIAR quando ela está
  quebrada, e (2) devolver o estado ao final. É a armadilha do "só passa em banco
  limpo" (v2.14) de cabeça para baixo: aqui o teste é que sujava.
- **A primitiva de 2 colunas serve conteúdo EMPARELHADO, não bloco curto ao lado
  de bloco longo** (v2.66, visto na tela, invisível no código): o formulário de
  roteiro pôs "quando o roteiro vale" (3 campos) ao lado das competências (7
  campos cada) num `.rh-conferencia-corpo`, e a coluna esquerda ficou **vazia por
  ~1.100px**. Na `FichaEntrevista` as 2 colunas funcionam porque os lados são
  PARES (a nota ao lado da justificativa que a sustenta). Ao reusar a
  composição, confira se os dois lados têm massa parecida — e confira
  RENDERIZADO: no código as duas versões parecem igualmente razoáveis.

- **Passar no teste estrutural NÃO é seguir o padrão — ele cobre VOCABULÁRIO,
  não COMPOSIÇÃO** (v2.65, reprovação do Bruno: *"você fugiu do padrão visual
  da página de entrevistas. NÃO INVENTE NADA QUANTO A ISSO. Siga padrões já
  estabelecidos"*). A ficha de Entrevistas da v2.64 passou nos 6 itens do
  `test_design_system.py` — zero classe fantasma, zero token inexistente, zero
  `<select>` nativo, tabela em `.dash-scroll` — e mesmo assim não parecia com o
  resto do sistema. O teste responde *"a classe existe?"*; ele não tem como
  responder *"esta é a primitiva certa para este papel?"*. Os defeitos reais
  eram todos de composição, com classes que existem: escala de nota 1–4 num
  `SelectBusca` (lista suspensa para comparar quatro âncoras) em vez de
  `.chips-escolha`; um `.rh-card` com borda e sombra POR COMPETÊNCIA em vez de
  um `.rh-conferencia` só; coluna única em vez de `.rh-conferencia-corpo`;
  `<h4>` cru em vez de `.rh-conferencia-bloco-titulo`. **É a v2.25 numa
  variação nova**: lá a tela saiu crua porque as classes NÃO existiam; aqui
  saiu estranha porque existiam e eram as erradas. Regra: **antes de escrever
  formulário/tela nova, abra a tela equivalente que já existe e copie a
  COMPOSIÇÃO dela** — para formulário longo com escala, a referência canônica é
  `FormularioAvaliacao.jsx`. Dois corolários pagos na mesma leva: (1) *"nunca
  `<select>` nativo"* **não** implica *"sempre `SelectBusca`"* — `.chips-escolha`
  não é um select, é a primitiva ESPECÍFICA de escala de nota, e a
  infraestrutura estava lá sem uso (`.chip-escolha` com 5 regras,
  `.rh-escala` com 7); (2) `<label className="rotulo">` (14 ocorrências, as
  ÚNICAS do repo contra 202 `<span className="rotulo">` dentro de `<label
  className="campo">`) era **regressão funcional**, não desvio estético — sem
  `htmlFor` e sem envolver o controle, clicar no rótulo não focava o campo.
- **Teste que compara a resposta com ela mesma passa com o defeito presente**
  (v2.64, pego por mutação): o `test_entrevista_vaga_excluida` guardava
  `titulo_original = resposta["vaga_titulo"]` e depois conferia
  `depois["vaga_titulo"] == titulo_original`. A mutação que ZERA o snapshot
  zerava os DOIS lados (`None == None`) e a asserção passava verde enquanto o
  defeito estava lá. **Referência de teste tem que ser CONSTANTE conhecida do
  teste**, nunca valor lido do próprio sistema sob teste — é a mesma lição da
  v2.54 ("comparar a aba com a própria constante é TAUTOLOGIA") numa variação
  nova. Foi a mutação que reprovou o teste, não o código: sem rodar as
  mutações, isto teria ido para produção parecendo coberto.
- **`prop` inventada em componente compartilhado não faz NADA e não avisa**
  (v2.64): a ficha de entrevista passava `desabilitado={encerrada}` ao
  `SelectBusca` para travar registro arquivado — e o `SelectBusca` **não tinha
  essa prop**. O React ignora prop desconhecida em silêncio, então a entrevista
  arquivada continuaria editável na tela, com o código *parecendo* certo. Mesma
  família da classe CSS fantasma (v2.25) e do token inexistente (v2.46): o
  JSX fica plausível e o build passa. **Antes de passar prop nova, abra a
  assinatura do componente** — foi corrigido acrescentando `desabilitado` de
  verdade ao `SelectBusca` (o `<select>` nativo que ele substituiu tinha
  `disabled`; a lacuna ia reaparecer em qualquer tela somente-leitura).
- **Modelo importado só como ALVO de FK precisa entrar no import do teste**
  (v2.64): teste que monta objetos direto pelo SQLAlchemy (sem subir a app)
  estourava `NoReferencedTableError: could not find table 'usuario_rh'` no
  primeiro flush — depois `'vaga'`. Os modelos entram no `metadata` quando são
  importados, e `app/models/__init__.py` é VAZIO neste projeto (quem registra
  tudo é a cadeia de imports da `app.main`). Em teste que não importa a app,
  importe explicitamente os modelos das tabelas apontadas pelas FKs, com
  `# noqa: F401` — o erro não fala do seu modelo, fala do vizinho.
- **`grep -c` que devolve 0 tem exit code 1 e corta o `&&` da cadeia** (v2.64):
  `cp backup x && grep -c MUTACAO x && rodar_teste` parava calado depois do
  grep quando o resultado era zero — exatamente o caso BOM (nenhuma mutação
  sobrando). O passo seguinte simplesmente não rodava, e a saída vazia parecia
  falha da restauração. Em verificação pós-mutação use `;` ou
  `$(grep -c ... || true)`.

- **O modo CARD tem os mesmos defeitos da tabela, virados de lado** (v2.63):
  as correções da v2.59–v2.62 mediram só o modo tabela; no card (abaixo de
  1250px) a linha do Banco de Talentos chegava a **491px** — uma pessoa por
  tela. Três causas: (1) a regra do card usava `flex: 1 1 auto` nos botões,
  herança de quando `.acoes-candidato` era flex — desde a v2.59 ela é **grid**,
  e `flex` ali não faz efeito nenhum (cada botão virava uma fileira); (2) campo
  vazio virava linha ("TAGS —" ocupando altura para dizer que não há nada) —
  `:empty` não bastava porque o `DashPlanilha` preenche com travessão, daí a
  classe `dash-vazio`; (3) um campo por linha de largura total, com 8-9
  colunas. Hoje o card é **grade de 2 colunas** e os botões se distribuem por
  `auto-fit`. **Ao mexer em layout de tabela, meça nos DOIS modos** — o teste
  de altura roda em 1440 (tabela) e 1150 (card), com teto próprio para cada.
- **Trocar `display` de um contêiner invalida as regras de filho em silêncio**
  (v2.63): `.acoes-candidato` virou grid na v2.59, e a media query do card
  continuou com `flex: 1 1 auto` nos botões — CSS não avisa que a propriedade
  deixou de valer. Ao mudar `flex` → `grid` (ou o contrário), procure TODAS as
  regras que estilizam os filhos daquele contêiner, inclusive dentro de media
  queries.

- **Teste de layout mede a FAIXA, não três pontos — e com dados REAIS** (v2.62):
  a régua da v2.59 rodava em 1024/1280/1440 e passava verde enquanto o Bruno
  mandava print de tela cortada. Ela pulava **1150–1249**, onde o modo card já
  saíra mas a tela ainda era estreita — ali Colaboradores estourava 53px,
  Talentos 78px e Jornadas 223px. Some a isso que eu media com **19 registros
  contra os 1171 reais**: com poucos dados o texto não estica a coluna. Ao
  medir layout, cubra os limiares das media queries (logo acima e logo abaixo)
  e crie dados com o VOLUME e o TEXTO de produção — posto de 86 caracteres,
  talento com quatro cargos.
- **Tela nova de lista entra na lista do teste** (v2.62): Jornadas era a que
  mais estourava e simplesmente **não estava** em `TELAS` no
  `tabelas-cabem-na-tela.spec.js`. Teste de cobertura que não enumera a tela
  nova dá falsa sensação de proteção — pior que não ter teste, porque ninguém
  vai conferir à mão o que "já está coberto".

- **Upload fora do wizard também normaliza — mas NUNCA recusa por isso** (v2.61,
  `creche_publico::_guardar_doc_crianca` e `portal::subir_documento`): creche e
  portal gravavam o arquivo CRU enquanto o wizard timbrava a mesma foto. Hoje
  passam pela mesma `normalizar_para_pdf`, com uma diferença deliberada em
  relação ao `documentos.py`: **falha de conversão cai no ORIGINAL**, não vira
  422. No wizard o candidato pode refazer a foto; no creche, recusar deixaria a
  pessoa sem enviar a certidão do filho, e o benefício travaria pela qualidade
  da foto, não pelo direito dela. O currículo do Banco de Talentos segue
  original DE PROPÓSITO (decisão da v2.33) — é documento de terceiro; há teste
  estrutural cobrando que ninguém "padronize" isso.
- **No portal, o OCR lê o ORIGINAL e o hash descreve o GRAVADO** (v2.61):
  `ler_documento(conteudo)` recebe o arquivo como veio (ler a foto reduzida
  dentro de uma A4 piora a extração — mesma regra do comentário em
  `normalizacao.py`), e `sha256`/`tamanho`/`content_type` descrevem o PDF que
  foi para o storage. Trocar um pelo outro dá leitura pior ou hash que não
  confere com o objeto guardado.
- **Ao reusar a câmera, confira a lista de extensões do backend** (v2.61): o
  `CapturaDocumento` oferece `.doc/.docx` no seletor de arquivo, mas o
  `ler_upload` usa `EXTENSOES_DOCUMENTO` por padrão, que NÃO inclui Word — um
  envio que a própria tela ofereceu voltaria como "formato não suportado". Use
  `EXTENSOES_COM_WORD` onde a câmera estiver ligada.
- **`aoCapturar`/`aoArquivo` da câmera recebem LISTA, sempre** (v2.61): mesmo
  uma foto vem como lista de um. Telas que guardam um documento por vez
  (creche, portal) precisam aceitar as duas formas —
  `Array.isArray(e) ? e[0] : e` — senão o upload manda um array para o
  `FormData` e o backend recebe `[object File]`.

- **Tirar a rolagem LATERAL sem limitar a ALTURA cria rolagem VERTICAL** (v2.60):
  um posto de 86 caracteres quebrava em seis linhas e a tabela mostrava DUAS
  pessoas por tela. Texto longo é **cortado na 3ª linha com reticências**, com o
  texto inteiro no `title` (pedido do Bruno). **`-webkit-line-clamp` NÃO
  funciona na `<td>`** — o navegador força `display: flow-root` em célula de
  tabela e engole o `-webkit-box`; o `clamp: 3` aparece no computed style e a
  altura não muda. O corte precisa de um DIV interno (`.dash-corta`), que o
  `DashPlanilha` injeta sozinho em toda coluna `quebra: true`.
- **`display: flex` sem `flex-wrap` VAZA — regra global, não conserto por tela**
  (v2.60): o flex prefere estourar o container a quebrar a linha, então o último
  botão fica fora da vista e nada avisa. Mordeu na coluna de ações (v2.59) e de
  novo no checklist de documentos (`.slot-linha`, onde a quebra só valia abaixo
  de 480px). Hoje há **uma regra só** ligando `flex-wrap` em todos os
  agrupamentos de ação (`.navegacao`, `.rh-lote`, `.rh-topo`, `.slot-linha`,
  `.ficha-item`, `.rh-abas`…) — tela nova que use qualquer um deles já nasce
  certa. Acompanha `min-width: 0` no texto ao lado dos botões: sem isso o item
  de flex usa o tamanho do CONTEÚDO como piso e empurra os vizinhos para fora
  **mesmo com `flex-wrap` ligado** (a pegadinha clássica do flexbox).
- **Teste E2E que faz login a cada caso bate no RATE LIMIT** (v2.60): a suíte de
  tabelas logava cinco vezes e caía em "Muitas tentativas" — falha que PARECE
  defeito de layout (timeout esperando a tabela) e não é. Faça login uma vez e
  injete o token (`localStorage['rh_token']`) nos demais. O rate limit é em
  memória: reiniciar o container da API o zera durante a depuração.

- **Botão novo na coluna de ações EMPURRA a tabela para fora da tela** (v2.59,
  feedback com print: *"tive que segurar ctrl e rolar o scroll do mouse [...] o
  botão estava ali, mas eu não vi"*). O "Atender presencial" da v2.56 foi o
  QUARTO botão e estourou o limite. Medido no navegador: a coluna de ações
  ocupava **560px de 1058px — 53% da tabela**, e em 1366px sobravam DOIS
  pixels; qualquer janela menor cortava a ação **em silêncio**, porque o
  `border-radius` da tabela faz o corte parecer o fim dela. O defeito é
  invisível no código — cada botão parece inofensivo na linha em que é escrito,
  e ninguém soma larguras. Por isso existe
  `frontend/tests/e2e/tabelas-cabem-na-tela.spec.js`: mede 6 telas em 3
  larguras e reprova se alguma exigir rolagem, ou se as ações passarem de 35%
  da tabela. **Rode ao acrescentar botão de ação ou coluna.**
- **Em tabela, o padrão é QUEBRAR; `nowrap` é a exceção declarada** (v2.59): era
  o contrário — `white-space: nowrap` em toda célula, e só as marcadas
  `quebra: true` fluíam. Um e-mail longo esticava a tabela inteira. Hoje:
  `nowrap: true` na config da coluna para o que não pode partir (data,
  contagem, matrícula); chips e botões já são automáticos. Use
  `overflow-wrap: break-word`, **nunca `anywhere`** — este parte no meio da
  palavra assim que aperta e transforma "Recepcionista" em "Recepcionist/a",
  pior de ler do que a rolagem que veio consertar.
- **Célula que ENUMERA lista vira a coluna mais larga da tela** (v2.59): o chip
  "⚠️ falta X, Y, Z" de Colaboradores chegava a 241px, e chip não quebra linha.
  Mostre a CONTAGEM e deixe a lista no `title`. Mesma regra para data: exibir
  data+hora na célula E repetir a mesma string no `title` custava 172px em
  Talentos por uma informação que quase nunca se usa ao minuto.
- **Abaixo de 1100px a tabela vira CARD — não tente resolver tudo no CSS**
  (v2.59): telas com 8-9 colunas (Talentos, Desenvolvimento) não cabem em
  1024px por mais que se quebre texto e comprima ações. O modo card já existia
  (era só para celular, em 760px) e resolve por completo: cada valor ao lado do
  seu rótulo, nada fora da vista. O limiar subiu para 1100px porque notebook
  pequeno e janela dividida ao meio são os dois casos em que o botão sumia.

- **Espaço sobrando não é inofensivo — apare TODO campo de texto, não só o
  nome** (v2.57, `ficha.py::_AparaEspacos`): *"tem gente que quando termina de
  digitar o nome ainda dá um espaço depois da última palavra"*. No nome o
  `capitalizar_nome` já resolvia; nos demais campos o texto ia como digitado, e
  `"Taguatinga "` **duplica a opção no filtro de coluna** (duas entradas na
  lista suspensa, nenhuma achando as pessoas da outra), suja o export lido por
  outro sistema e quebra casamento por TEXTO (cargo, lotação, jornada). Pior:
  no e-mail o `EmailStr` recusava `"jose@x.com "` e a tela dizia *"e-mail
  inválido"* para um endereço correto. O `model_validator` é `mode="before"`
  justamente por isso — aparar DEPOIS da validação de tipo não salvaria o
  e-mail. Campo só com espaços vira `None`, não `""`.
- **Migração que percorre tabelas não pode assumir que a PK é `id`** (v2.57,
  `e7f8a9b0c1d2`): `dados_pessoais` é 1:1 com o candidato e usa `candidato_id`.
  A primeira versão estourou no meio do lote — e o `transaction_per_migration`
  do `env.py` devolveu tudo, sem alteração parcial (confirmado na prática).
  Declare a PK por tabela. E, ao guardar backup em chave composta, use um
  separador que NÃO apareça no conteúdo: com `.` o split quebrava no UUID e o
  downgrade restauraria o registro errado, em silêncio.
- **Migração de dado de gente real: guarde o original** (v2.57): o Bruno pediu
  para padronizar os nomes já gravados, contrariando a regra "não migre nome em
  lote" — decisão dele, com a ressalva registrada antes. O que torna isso
  aceitável é a migração guardar o valor ANTERIOR de cada registro alterado
  (em `configuracao`) e o `downgrade()` restaurar o valor EXATO, espaços
  inclusive. Teste o downgrade de verdade, não só o upgrade: "reversível" que
  ninguém executou é promessa, não garantia. E **não invente acento** —
  `FATIMA` continua `Fatima`; adivinhar escreve errado o nome de alguém.

- **`await arquivo.close()` no `finally` mora DENTRO do serviço, não no
  call-site** (v2.56, `services/upload_seguro.py`): as duas rotas de upload do
  creche eram as ÚNICAS do backend inteiro sem o `close()` — e são PÚBLICAS. O
  Starlette faz spool em disco acima de ~1MB, então sobrava certidão de
  nascimento de criança em arquivo temporário no container. Também não havia
  teto de tamanho nem allowlist: `ext or "bin"` aceitava `.exe`, `.svg` e
  arquivo sem nome. Documentar "lembre de fechar" não funciona (o resto do
  projeto fechava; estas duas escaparam): use `ler_upload`, que valida e fecha
  numa função só. **O teto é configurável no painel** (Configurações →
  Sistema) — limite chumbado exige deploy, e quem descobre que 10MB não bastam
  para a foto de um celular novo é o RH com a pessoa na linha.
- **O manifesto descreve o ato REAL, nunca a versão conveniente** (v2.56,
  admissão assistida): quando o RH preenche a admissão com a pessoa presente, o
  manifesto NÃO pode continuar afirmando "código enviado ao titular e validado
  nesta plataforma" como se ela tivesse operado sozinha. Ganhou o campo *"Forma
  de coleta"* (`fichas.py::pagina_manifesto` + `bloco_assinatura`), preenchido
  a partir de `Assinatura.assistida_por`. Três regras que sustentam isso: (1) a
  marca precisa ser gravada **ANTES de `_gerar_pdf`**, senão o manifesto sai
  sem ela e o hash já foi calculado; (2) o **ator continua `candidato`** na
  auditoria — quem quis assinar foi ele, e trocar para `rh` registraria que o
  RH assinou; (3) exige e-mail da PRÓPRIA pessoa (422 `sem_email` na abertura),
  porque é o código no e-mail dela que sustenta a identidade. Precedente da
  casa: `AutorizacaoEquipe` diz "emitido sob autorização permanente de X", não
  "X assinou". O documento de assinatura remota não muda — há teste de
  regressão, porque manifesto é peça de prova e não deve variar por acidente.
- **Sessão de trabalho marcada vive no LINK, não em tabela à parte** (v2.56,
  `acesso_magico.assistido_por`): o wizard já resolve o token a cada
  requisição, então marcar o próprio acesso dispensa estado paralelo para
  sincronizar — e não existe "sessão esquecida aberta". Validade curta (8h, não
  as 72 do convite): link de preenchimento-por-terceiro é superfície de risco
  sem contrapartida se durar dias.
- **Texto em PDF quebra linha — normalize antes de procurar a frase** (v2.56):
  o `multi_cell` do fpdf quebra no meio da frase e o `extract_text` devolve o
  `\n`, então `"em atendimento assistido por" in texto` falha por causa da
  LARGURA DA CAIXA, não do conteúdo. Use `" ".join(texto.split())` no teste;
  senão você "conserta" um código que já estava certo.

- **Mudar a UNIDADE de um campo de dinheiro exige olhar o histórico** (v2.55,
  `creche.py::_valor_total`): o `valor_reembolso` do creche passou a ser POR
  CRIANÇA deferida. Só que, para quem foi aprovado ANTES, o valor gravado já
  era o total do benefício — multiplicá-lo pela contagem dobraria o reembolso
  de quem tem dois filhos, **em silêncio, no contracheque**. Por isso o total
  só multiplica quando há `decisao` registrada; sem nenhuma (o modelo antigo),
  o gravado vale como está. Regra geral: ao mudar o significado de um campo
  monetário, o registro antigo continua com o significado ANTIGO — a migração
  é de leitura, nunca de valor. Valor ilegível volta cru, jamais `R$ 0,00`
  (zero entraria calado na folha).
- **Decisão por item precisa impedir a decisão pela METADE** (v2.55, creche):
  aprovar um benefício com uma criança ainda sem decisão deixaria um dependente
  sem análise no requerimento e o valor errado. O `ativar_beneficio` recusa com
  409 **dizendo o NOME de quem falta** — erro que só diz "faltou decidir" faz o
  RH procurar na tabela. E "todas indeferidas" vira `indeferido` automático:
  benefício `ativo` que paga zero seria mentira no relatório. O documento que a
  pessoa ASSINA lista só as deferidas; as negadas vão em seção própria com o
  motivo — somem do benefício, não do registro da análise (antes, negar uma
  criança exigia REMOVÊ-LA, e a prova de que fora analisada ia junto).
- **`detail` estruturado do backend morre no `api.js` se ninguém o preservar**
  (v2.55): `lancarErro` converte `detail` que não é string na mensagem genérica
  do `statusText`. Um 409 que manda `{erro, criancas: [...]}` perdia a lista
  logo na porta de entrada, e a tela só conseguia dizer "não deu". Agora fica
  em `e.dados` (irmão do `e.campos`, criado pela mesma lição em 2026-07-27).
  Ao devolver erro estruturado do backend, confira que o front o preserva —
  senão o trabalho de montá-lo é jogado fora.
- **PDF se confere RENDERIZADO, não por extração de texto** (v2.55): o
  requerimento do creche imprimia a data de nascimento CRUA, então quem
  preencheu pelo wizard (que grava ISO) tinha `2022-10-19` num documento
  oficial em português, assinado. A extração de texto passou; só apareceu ao
  transformar o PDF em imagem e olhar. Use `data_br` (lê os dois formatos) em
  qualquer data impressa em documento — a regra da v2.27 vale para o PDF
  também, não só para a tela.

- **Marcador que se atualiza à mão CONGELA — o guarda-corpo é o teste** (v2.54,
  `app/versao.py` + `tests/test_versao.py`): o `VERSAO_DEPLOY` do
  `api/health.py` era string chumbada e congelou **duas vezes** — na `v1.50`
  por vinte versões e, depois de consertarem o campo VIZINHO e escreverem no
  docstring que a constante era o mau exemplo, de novo na `v2.27` por outras
  vinte e seis. O Bruno descobriu abrindo `/api/health` após um deploy
  conferido. **Documentar que algo precisa ser atualizado à mão não funciona**;
  o que funciona é falhar o build. Hoje a versão vem de `app/versao.py` e o
  teste a compara com o topo do `CHANGELOG.md` (+ um segundo teste que impede a
  literal de voltar ao `health.py`). Ao fechar uma versão, atualize os DOIS.
  Não dá para derivar do CHANGELOG em runtime: o contexto de build da imagem da
  API é `./backend` e o arquivo mora na RAIZ — leria certo só na máquina de
  quem desenvolve, o pior dos dois mundos.
- **Estado de CONTEÚDO e de VISIBILIDADE não podem ser independentes** (v2.54,
  `TalentosRH.jsx`): `verCurriculo` fazia só `setDoc(...)`, mas o
  `<VisualizadorArquivo>` mora DENTRO da `FichaTalento`, que só é montada com
  `aberto === t.id`. Com a ficha fechada — o padrão de toda linha — o clique era
  **literalmente morto**: baixava o arquivo e não acontecia nada na tela, sem
  erro nem espera. Pior, o currículo aparecia RETROATIVAMENTE ao abrir a ficha
  depois. Regra: quem abre um documento tem que abrir o lugar onde ele é
  exibido, **na mesma ação**. Ao criar um `useState` cujo conteúdo renderiza
  dentro de outro bloco condicional, verifique se a ação que o preenche também
  garante a montagem do bloco.
- **Painel do `DashPlanilha` precisa de UM wrapper — Fragment quebra duas
  coisas** (v2.54, `Creche.jsx`): o `.dash-detalhe > td` tem `padding: 0` DE
  PROPÓSITO (o respiro é de quem preenche a célula), e a regra
  `.dash-detalhe > td > *` aplica `position: sticky` + `width: 100cqw` a cada
  FILHO DIRETO. Com `<>…</>` eram dez filhos: sem padding nenhum E dez elementos
  sticky independentes que se desmontam quando a tabela rola na horizontal. Use
  `<div className="ficha-talento">` (o `TalentosRH` sempre fez certo). Se um
  painel "perdeu o espaçamento" depois de um refactor, procure o wrapper que
  sumiu antes de mexer no CSS.
- **Dado LEGÍVEL e absurdo é um QUARTO estado** (v2.54, caso de campo
  2026-08-02): a v2.27 ensinou que "não atende ao critério" ≠ "não consegui ler
  o dado". Faltava o terceiro: **"li um dado que não pode ser daquilo"**. Um
  filho apareceu com `12/10/1998 · 27a 9m` porque o campo tinha o nascimento do
  PRÓPRIO COLABORADOR — o `InputData` não tinha `autoComplete="off"`, então o
  navegador ofereceu a data digitada momentos antes. O cálculo estava certo. E o
  estrago não parava no ❌: com 27 anos, `elegivel_idade=False` e
  `idade_desconhecida=False` ligavam o `revisar_idade`, então o sistema marcava
  **risco de glosa** e empurrava o RH a suspender quem tinha direito.
  `_idade_implausivel` (≥18a) fica FORA do alarme pela mesma razão que
  `idade_desconhecida`. É **aviso, nunca bloqueio** no painel (filho com
  deficiência não tem limite de idade em várias normas), mas é **recusa 422 na
  ENTRADA** (`_conferir_data_da_crianca`, nos DOIS caminhos de cadastro). E a
  mensagem diz o que RESOLVE: `catch` cego mandando "tente de novo" faz a pessoa
  repetir a mesma data.
- **`autoComplete="off"` em data de nascimento** (v2.54, `InputData.jsx`): data
  de nascimento nunca se repete entre pessoas diferentes — sugerir a anterior só
  pode errar, e foi a causa provável do caso acima. Vale para qualquer campo
  cujo valor correto é necessariamente único por pessoa.
- **Exportador NOVO não reusa o gerador do vizinho** (v2.54,
  `services/export_dexion.py`): Tirvu e Dexion parecem o mesmo problema e são
  opostos em todos os pontos — 28 colunas × **97** (A→CS); aba `Plan1` ×
  `Sheet1`; cabeçalho de 1 linha × **4** (dados na 5ª); autoFilter **recusado** ×
  **exigido**; datas em TEXTO `dd/mm/aaaa` × **serial do Excel**… com exceção da
  coluna `BZ`, que é texto **na mesma planilha**. Copiar produz arquivo que
  PARECE certo — ou pior, aceito com as datas erradas em mil e duzentos dias,
  porque serial e texto são as duas coisas que um parser lê sem reclamar.
  A chave da linha é a **LETRA da coluna**, nunca o rótulo: o layout repete
  nomes ("CATEGORIA" 3×, "UF" 3×, "TIPO DE JORNADA" 2×) e com rótulo uma
  sobrescreveria a outra em silêncio. **Regra dos valores assumidos: chumba-se o
  que é da EMPRESA, nunca o que é da PESSOA** — país e regime da empregadora vão
  fixos (como o `EMPRESA_TIRVU_ID`); categoria, CBO, sindicato e conta bancária
  viram PENDÊNCIA anunciada, porque código de eSocial errado não dá erro na
  importação: entra limpo e sai errado na declaração meses depois (a assinatura
  do "Registra Ponto" da v1.82). O sistema NÃO coleta agência/conta/tipo de
  conta, município IBGE nem CBO por pessoa — decisão do Bruno (2026-08-02) foi
  exportar vazio e tratar como pendência.
- **Teste de layout compara com o ARQUIVO OFICIAL, não com cópia à mão** (v2.54,
  `test_export_dexion.py`): cópia escrita no teste passa a divergir do modelo na
  primeira revisão dele e o teste segue verde. Duas mutações escaparam da 1ª
  versão e ensinaram o resto: (1) comparar a aba com a própria constante é
  TAUTOLOGIA — renomear para `Plan1` mudava os dois lados juntos; (2) montar o
  dict da linha à mão no teste testa a MINHA escolha de função, não a do código,
  então trocar `_data_br_texto` por `_serial_excel` na coluna BZ passava batido.
  A linha do teste tem que vir de `linha_dexion`, e a referência tem que ser o
  `.xlsx` do fornecedor.
- **`.title()` do Python PRODUZ o "Maria De Fátima"** (v2.54,
  `services/nomes.py`): `"maria de fátima".title()` devolve exatamente o defeito
  que o Bruno reclamou — e o `ocr_rg.py` usava isso para SUGERIR o nome da mãe,
  que o candidato aceitava com um toque. O sistema não só tolerava a
  capitalização errada: ele a gerava. Use `capitalizar_nome` (preposições, `d'`,
  `Mc`, hífen, sufixo romano; idempotente, porque o wizard salva a cada 900ms),
  aplicado na ENTRADA — wizard, convite do RH, Banco de Talentos, edição pelo
  painel e o OCR. **NÃO acentua** (`FATIMA` continua `Fatima`) e por isso a base
  existente **não se migra em lote**: o que está em caixa alta já perdeu o acento
  na origem, e a migração cega gravaria "Fatima" como nome correto de alguém
  (mesma regra da data do creche). O `test_nomes.py` é estrutural e reprova
  `.title()` que volte a um ponto de escrita de nome.

- **Endereço também vem em DOIS formatos — use `services/endereco.py`** (v2.37,
  feedback de campo 2026-08-01): `Endereco` guarda a string única legada
  (`logradouro_numero_complemento`) E os campos separados
  (`logradouro`/`numero`/`complemento`) que o layout do Tirvu exigiu. A coleta
  ATUAL grava os separados e deixa o legado **nulo** — nada sincroniza os dois.
  Quem lia só o legado imprimia traço no lugar da rua: Termo de VT (o documento
  que declara "resido no endereço acima" e autoriza 6% de desconto), ficha de
  emergência, ficha cadastral do terceirizado, ofício à Presidência (caía na
  linha de pontinhos) e a planilha geral do RH. Use `endereco.rua()` onde já
  existem campos de bairro/cidade/CEP e `endereco.completo()` em texto corrido;
  `cep_formatado()` para imprimir (o banco guarda 8 dígitos sem máscara).
  Parte ausente é OMITIDA, nunca vira `-`. **NÃO migre em lote** — mesma regra
  da data do creche. A ficha cadastral principal e a autodeclaração de
  residência já tratavam os dois: não "consertar" o que está certo.
- **Data no banco vem em DOIS formatos — leia os dois** (v2.27, incidente de
  campo 2026-07-30): `CriancaCreche.data_nascimento` é `String(10)` com o
  comentário "dd/mm/aaaa", mas o `InputData.jsx` devolve **ISO** (`aaaa-mm-dd`)
  por padrão (só com `modoTexto` ele devolve BR) — e é assim que a maioria dos
  registros foi gravada. `_idade_anos_meses` lia só o BR: o `split("/")`
  falhava, a idade virava `None`, e `None` era tratado como "não elegível".
  Resultado: **toda** criança marcada "❌ passou de 5a11m", inclusive um bebê de
  2 anos, e o RH prestes a indeferir quem tem direito. Use
  `creche.partes_da_data` / `data_br`. **NÃO migre os dados em lote**: adivinhar
  formato (`03/04` é 3 de abril ou 4 de março?) reescreveria data de gente real
  em algo que decide dinheiro no contracheque.
- **"Não atende ao critério" e "não consegui ler o dado" são estados
  DIFERENTES** (mesma leva): tratar os dois como ❌ na tela leva a decisão
  errada — no creche, ao indeferimento de quem tem direito. Sempre que uma
  regra de elegibilidade depender de um dado que pode estar ilegível, exponha o
  terceiro estado ("conferir"), e não deixe que ele acione alarme de risco
  (`revisar_idade` ignora `idade_desconhecida`).
- **Painel de detalhe abre NA LINHA, nunca no fim da página** — regra que já
  valia desde a v1.83 e o Creche não seguia (feedback 2026-07-30: "tenho que
  rolar a tela lá no final para conferir e depois voltar ao topo"). Se a tela
  usa `DashPlanilha`, o detalhe vai em `linhaExpandida`; renderizar depois da
  tabela obriga a rolar a página inteira a cada item conferido.
- **Demonstração de como responder o teste é CSS, não GIF** (v2.53,
  `candidato/DemoTeste.jsx`): uma questão de mentira que se responde sozinha,
  antes do DISC, do situacional, da testagem avulsa e das provas. Existe porque
  a regra do DISC (uma marcação em cada coluna, nunca a mesma palavra) se
  entende VENDO, e quem vai fazer um teste que decide contratação não deveria
  gastar atenção com a mecânica. **Reusa as classes da tela REAL**
  (`.teste-linha`, `.teste-adjetivo`, `.teste-tag`) — se o teste mudar de
  aparência, a demo muda junto, em vez de congelar como um GIF congelaria. É
  `aria-hidden` (decorativa; o texto ao lado diz o mesmo em palavras) e respeita
  `prefers-reduced-motion` mostrando o estado FINAL preenchido. A rota pública
  `GET /p/{token}` devolve `tempo_segundos` e `qtd_questoes` para a pessoa saber
  o tamanho da tarefa antes de aceitar — **nunca o gabarito**.
- **Tour guiado: `driver.js`, um por público, tematizado à mão** (v2.49,
  `rh/tour.js` + `candidato/CandidatoApp.jsx`): o painel do RH e o wizard do
  candidato têm tours SEPARADOS, com chaves de `localStorage` distintas
  (`tour_rh_visto` × `tour_visto`) — compartilhar faria um esconder o outro, e
  o RH também abre o link do candidato para conferir. Três armadilhas pagas:
  (1) **passo com `element` que não existe é PULADO EM SILÊNCIO** — o tour
  encolhe sem avisar; ancore em elemento sempre presente (sidebar, cabeçalho),
  nunca em card que depende de dados, e confira contando os passos exibidos;
  (2) o `driver.css` tem **cores fixas e nenhuma variável de cor** — sem
  sobrescrever as classes `.driver-popover*` com os tokens, o balão sai BRANCO
  no tema escuro (ficou assim no tour do candidato por meses); (3) o progresso
  vem como **"2 of 5" em inglês** — passe `progressText: '{{current}} de
  {{total}}'`. Ao acrescentar passo, diga o que a pessoa GANHA, não o que a
  tela é.
- **O design system tem GUARDA-CORPO — rode antes de commitar tela**
  (v2.48, `backend/tests/test_design_system.py`): teste estrutural, stdlib
  pura, roda em segundos e **agora roda no CI**. Cobra classe fantasma, token
  inexistente, fallback de cor em `var()`, token de superfície sem par escuro,
  `.rh-tabela` sem `.dash-scroll` e `<details>` remendado no JSX. Descoberta da
  leva: **nenhum dos 38 testes Python rodava no CI** — o `test_upload_multipart`
  (v2.39.1) só rodava se alguém lembrasse. Ao criar teste estrutural novo,
  ACRESCENTE ao passo "Testes estruturais" do `ci.yml`; se ele importar
  `app.main`, NÃO entra (exigiria instalar FastAPI/SQLAlchemy e custaria
  minutos). O que o teste deliberadamente NÃO cobra: os ~560 `style` inline de
  espaçamento — dívida herdada que travaria o CI sem consertar nada.
- **`<details>`: cursor, marcador e margem vêm do `styles.css`** (v2.47.1):
  `summary` tem `cursor: pointer` + `list-style-position: inside` + anel de
  foco na folha; `details:not([class])` traz o respiro do dobrável solto. NÃO
  escreva `style={{ cursor:'pointer' }}` nem `marginTop` no JSX — seis
  remendos assim existiam antes da regra base. Duas armadilhas pagas: (1)
  `list-style-position: outside` (o padrão do navegador) desenha o ▸ FORA da
  caixa de conteúdo, encostando na borda do card e furando o alinhamento; (2)
  a regra global TEM que ser `:not([class])` — sem isso ela sobrescreve
  `.ficha-rh-secao`/`.rh-card`, que já definem o próprio espaçamento (as
  seções da ficha foram de 8px para 12px numa versão intermediária).
  **Bloco de topo que não é `.rh-card` precisa declarar `margin-bottom`**: a
  `.rh-revisao` não tinha, e só apareceu quando ela deixou de ser o último
  elemento da tela.
- **A ORDEM da tela é o custo real, não a posição de um bloco** (v2.47,
  `rh/Detalhe.jsx`): o Bruno usa a tela de uma pessoa para DUAS coisas de peso
  igual — conferir documento e corrigir cadastro. O defeito não era "a fila
  está por último": eram **seis blocos de consulta ENTRE as duas**, então ele
  aprovava embaixo, rolava pra cima pra acertar o posto e voltava. Subir a fila
  sozinho só inverteria quem fica longe de quem. Regra: **agrupe por NATUREZA
  (trabalho × consulta) e mantenha juntas as coisas que a pessoa alterna**; o
  que não é trabalho diário vai para um `<details>` no fim. Três faixas hoje:
  documentos · cadastro · consulta (fechada). Sem abas — decisão do Bruno.
- **`if (!x) return null` esconde DOIS estados diferentes** (v2.47): `null`
  (ainda carregando) e `[]` (não há nada) na mesma condição fazem o bloco sumir
  enquanto a API responde — e o conteúdo abaixo PULA na cara de quem já estava
  lendo. Mordeu em `PostoServico` e `ModelosDoColaborador`. Regra: bloco que
  some porque **não se aplica** àquela pessoa pode sumir (mantém a densidade
  baixa); bloco que some porque **está carregando** tem que RESERVAR o lugar.
  Teste os dois separadamente: `if (x === null) return <carregando/>` e só
  depois `if (x.length === 0) return null`.
- **Mensagem vai onde a PESSOA está olhando — o critério é DISTÂNCIA** (v2.47,
  a v1.96 de novo): componente longe do topo que chama o `setMsg` do pai põe a
  confirmação fora do campo de visão de quem clicou. Aconteceu no "Salvar
  posto" (card do meio da tela). Corrigido em `PostoServico`,
  `ModelosDoColaborador` e `FichasStatus`. **Não converta tudo em mensagem
  local**: componente colado no topo (contato, informativo) pode usar a global
  — o que decide é a distância entre o botão e a mensagem, não a contagem.
- **Confira a tela RENDERIZADA, não só o código** (v2.47): o cabeçalho do
  `Detalhe` tinha "⬇ Baixar dossiê" com `btn-principal`, virando um botão verde
  gigante, enquanto **"Efetivar como colaborador" — irreversível — parecia
  secundário**. No código as duas linhas parecem igualmente inocentes; na tela
  a hierarquia está invertida. Screenshot com Playwright + medir altura do
  cabeçalho e estouro horizontal pega o que a leitura não pega.
- **Token que não existe é PIOR que classe que não existe** (v2.46): a classe
  fantasma deixa a tela crua e alguém vê; o **token** fantasma cai no fallback e
  a tela fica plausível — só que com a cor CLARA valendo nos DOIS temas.
  `var(--texto-suave, #47554d)` esteve 4× no `styles.css` com o token nunca
  definido: **2,09:1 de contraste no escuro** (mínimo WCAG AA é 4,5:1), nas
  opções de questão das Provas. Duas regras que ficam: (1) **nunca escreva
  fallback de cor** em `var()` — se o token não existe, defina-o; (2) todo token
  de cor precisa de **par no `:root[data-tema='escuro']`** — `--tinta-suave`
  tinha 12 usos e nenhum par (3,61:1). Conferir com `grep -c 'nome-do-token'` nos
  DOIS blocos, e medir contraste no navegador de verdade (`getComputedStyle` +
  fórmula WCAG), não no olho: o tema escuro engana.
- **`overflow-x` numa `<table>` NÃO FUNCIONA — só o wrapper contém** (v2.46,
  medido com Playwright): `display: table` ignora `overflow`, então
  `.rh-tabela { overflow-x: auto }` não impede a tabela de empurrar a página.
  O que funciona é `<div className="dash-scroll">` em volta (é o que o
  `DashPlanilha` faz). Como ~35 tabelas do painel são escritas à mão, **não há
  conserto de uma linha no CSS** — ou envolve cada uma, ou migra para o
  `DashPlanilha`. Faixas: acima de 800px está DESPROTEGIDO; entre 480–800px a
  media query `.rh-tabela { display:block; overflow-x:auto }` resolve (aí o
  `display:block` faz o overflow valer); abaixo de 480px vira card.
- **Falha de carga tem que virar ERRO na tela, nunca `null` de volta** (v2.46):
  `api.x().then(setDados).catch(() => setDados(null))` deixa a tela em
  "Carregando…" para sempre — indistinguível de rede lenta, sem retry. Use
  estado de erro SEPARADO + botão "tentar de novo" (o padrão certo já existia em
  `Detalhe.jsx::FichaRH`). Duas sutilezas: (1) em tela de MONITORAMENTO
  (telemetria, logs) a falha tem que ser ANUNCIADA — silêncio se confunde com
  "nenhum problema", que é o oposto do que a tela existe para dizer; (2) se a
  mesma função de recarregar é chamada DEPOIS de ações (aprovar, salvar), o
  `catch` de carga vai só no `useEffect` inicial — senão um erro de ação troca a
  tela inteira por uma mensagem e apaga o trabalho em curso.
- **Classe de CSS que não existe não estiliza NADA — confira antes de usar**
  (v2.25, feedback do Bruno: "achei tão feia essa página, por que não seguiu o
  padrão?"). A 1ª tela de Telemetria inventou ONZE classes (`rh-secao`,
  `rh-bloco`, `rh-acoes`, `rh-form-inline`, `campo-check`…) que não estavam no
  `styles.css`. O JSX ficava plausível e o build passava — CSS não reclama de
  seletor inexistente —, mas a tela saía CRUA: sem card, sem borda, sem
  espaçamento, tudo empilhado. **O erro não foi de gosto, foi de não ter lido
  `docs/planejamento/08-sistema-de-design.md` antes de escrever.** O vocabulário
  real é curto: `.rh-card` (bloco), `.rh-grid-2` (duas colunas), `.rh-topo`
  (cabeçalho), `.rh-metricas`/`.rh-metrica` (números), `.rh-tabela`, `.campo` +
  `.rotulo`, `.explica`, `.chip`, `.aviso-codigo`, `.sucesso`/`.alerta`,
  `.btn-principal`/`.btn-secundario`/`.btn-link`/`.btn-remover`/`.btn-mini`.
  Antes de commitar tela nova: `grep -c '\.minha-classe' styles.css` em cada
  classe usada — zero significa que ela não faz nada. Idem para
  `var(--token)`: token inexistente cai no fallback e quebra o dark mode.
  Precisa de uma classe nova de verdade? Acrescente ao `styles.css` com tokens
  (foi o caso de `.bloco-codigo` e `.campo-sem-margem`), nunca invente no JSX.
- **Teste NÃO trava contagem de catálogo** (v2.25): `assert len(_INTERNOS) == 8`
  quebrava a cada aviso novo e legítimo, sem apontar defeito — e a correção
  óbvia (incrementar a constante) faz o teste não proteger nada. Derive a
  garantia do próprio catálogo (todo aviso interno tem `evento=` existente na
  matriz), nunca de uma lista escrita à mão no teste.
- **Estado que nasce `null` NÃO pode ser usado no corpo do componente** —
  o guard tem que vir ANTES de qualquer cálculo, não junto do `return`
  (2ª causa do incidente de 2026-07-29; a 1ª está no item seguinte). Em
  `Assinatura.jsx`, `const [fichas, setFichas] = useState(null)` na linha 14 e
  `fichas.some(...)` na linha 26 — mas o `if (!fichas) return` só aparecia na
  linha 54. O `some` roda no PRIMEIRO render, antes de o `useEffect` carregar:
  `null.some()` lança `TypeError` e apaga a tela INTEIRA do candidato.
  Introduzido na v2.05 e pegou justamente quem estava na etapa de assinatura —
  os dois candidatos travados. **Sintoma que engana**: parece problema de rede
  ou de link, porque só acontece na janela em que a API ainda não respondeu.
  Regra: ou use `(x || [])`, ou mova o guard para antes do primeiro uso. Ao
  criar estado `useState(null)`, procure TODO uso dele acima do guard.
  Coberto por `deploy-tela-branca.spec.js` (segura a resposta da API por 1,5s
  para render no estado nulo), validado por mutação.
- **SPA + deploy: asset que sumiu NÃO pode virar `index.html`** (incidente de
  produção 2026-07-29 — dois candidatos com a TELA EM BRANCO no meio do envio
  de documentos, e ZERO linha de erro em log nenhum). O `try_files $uri
  /index.html` do nginx é o certo para ROTA (`/c/{token}` é tratada no
  cliente), mas valia também para `/assets/*.js`. Cada build gera hash novo e
  APAGA o anterior; a aba que o candidato deixou aberta no celular — ele sai
  para fotografar o documento e volta, é o uso normal — continua pedindo o
  arquivo antigo. O nginx respondia **200 com o HTML do index no lugar do
  JavaScript**, o navegador tentava executar `<!doctype html>` como script e o
  React não montava. **Do ponto de vista do servidor foi um 200 bem-sucedido —
  por isso não havia o que procurar no log.** Não depende de quando o link
  nasceu, e sim de a aba estar aberta durante um deploy: por isso pegou também
  um candidato criado DEPOIS da atualização. Três defesas, nenhuma cobre a
  outra: (1) `location /assets/` com `try_files $uri =404` (+ `immutable`, que
  é seguro porque o hash está no nome); (2) `main.jsx` detecta falha de
  carregamento de módulo e recarrega UMA vez — a trava em `sessionStorage` é
  obrigatória, senão falha permanente vira recarregamento infinito, pior que a
  tela branca; (3) `ErroFatal.jsx`, o ErrorBoundary (não havia NENHUM no
  projeto: qualquer exceção de render apagava tudo, sem uma palavra na tela).
  Coberto por `frontend/tests/e2e/deploy-tela-branca.spec.js`, validado por
  mutação. **Tela branca é o pior desfecho possível** — não diz se o problema
  é a internet, o link, o celular ou o sistema; a pessoa conclui que "não
  funciona" e desiste. Ao mexer no `nginx.conf`, no roteamento ou em
  code-splitting, rode esse teste.
- **`/api/health` diz se o BANCO acompanhou o código** (`migracoes.em_dia`):
  se o `docker-entrypoint.sh` falhar no `alembic upgrade head`, a API sobe
  assim mesmo com o schema velho e o defeito só aparece na cara do usuário
  (com o banco atrasado, o painel do RH e o creche quebram; as rotas do
  candidato ainda respondem 200). A revisão esperada é **lida** do diretório de
  migrations — o `VERSAO_DEPLOY` chumbado à mão ficou congelado em `v1.50` por
  vinte versões, mentindo com a maior confiança. Conferir depois de todo deploy.
- **Rotas FastAPI**: declarar rotas específicas (`/lote/...`, `/massa/...`)
  ANTES das paramétricas (`/{id}`), senão o literal vira UUID inválido (422).
- **Rota com `dados: dict` livre burla a validação do FastAPI** (v1.96,
  `rh_ficha.py::editar_secao`): quando o corpo é tipado como `BaseModel` com um
  campo `dict`, o FastAPI NÃO valida o conteúdo — a validação manual
  (`schema(**payload.dados)`) roda DEPOIS, fora do ciclo normal. Uma
  `pydantic.ValidationError` levantada ali **não é** `RequestValidationError`
  e escapa como HTTP 500 em texto puro (era o bug "não salva e não diz o
  motivo"). Envolver em `try/except ValidationError` e devolver 422 manual
  sempre que uma rota validar um dict à mão. Há também um
  `@app.exception_handler(Exception)` global em `main.py` como rede de
  segurança — mas ele NUNCA ecoa `str(exc)` ao cliente (a mensagem de erro do
  Postgres para coluna truncada contém o VALOR que estourou, ex. CPF); devolve
  só `{"erro": "interno", "id": "<correlação>"}`, o motivo real fica no log.
- **`registrar()` (auditoria) faz `db.flush()` e ENGOLE exceção** — se o
  flush dela disparar um `DataError` (dado inválido de uma escrita anterior
  ainda não persistida), a sessão fica com rollback pendente e a PRÓXIMA
  operação de banco estoura `PendingRollbackError` em vez do erro real. Por
  isso: sempre validar (via `db.flush()` protegido) os dados da AÇÃO PRINCIPAL
  antes de chamar `registrar()` — nunca depois.
- **Mensagem de erro/sucesso do formulário do RH tem que ficar PERTO do botão
  que a gerou** — um `setMsg` que sobe pro componente pai e renderiza no topo
  da tela vale nada se o RH está com um `<details>` aberto e rolado até o
  fundo (é invisível na prática, mesmo aparecendo no DOM). Ficha do RH
  corrigido nisso (v1.96): mensagem local por seção, dentro do próprio
  `<details>`. Ver também: `await recarregar()` (ou similar) DENTRO do `try`
  de uma ação — se o recarregamento falhar depois de um salvamento bem
  sucedido, o `catch` reporta falha quando na verdade salvou.
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
- **Tempo de preenchimento é LÍQUIDO, vem da TELEMETRIA** (v2.51,
  `services/telemetria.py::tempo_liquido_por_candidato`): o card de Admissões
  mostrava `dossie_gerado_em - criado_em` (o campo se chamava
  `tempo_medio_minutos_convite_ao_dossie`) — 2.590 min que incluíam a pessoa
  dormindo e esperando documento chegar. Agora soma os intervalos entre eventos
  consecutivos da MESMA `sessao` e **descarta buracos > 30 min**
  (`GAP_INATIVIDADE_S`) — mesmo raciocínio do import de ponto, onde `00:00`
  com entrada é registro incompleto e não jornada de zero hora. Três regras que
  NÃO devem ser afrouxadas (travadas em `test_tempo_liquido.py`): sessões
  diferentes SOMAM (voltar no dia seguinte é a mesma pessoa); a cauda de sessão
  tem TETO (`CAUDA_MAX_S`), senão quem entra e sai 10 vezes infla a média em
  ~17%; e **quem não tem telemetria fica FORA da média**, nunca entra como
  zero. A métrica antiga continua na API (responde "quanto o processo demora")
  e vive no tooltip do card. Duração na tela sempre por `fmt.js::fmtDuracao` —
  a unidade acompanha o número (`45s`/`25min`/`1h30`/`1d19h`).
- **Filtro de coluna: `'lista'` para valor de conjunto, `'texto'` só para
  trecho** (v2.52). `filtro: 'lista'` no `DashPlanilha` monta as opções a
  partir dos PRÓPRIOS dados e usa o `SelectBusca` — é o certo para posto,
  cargo, tags, cidade, tipo, autor: valores que se repetem e que ninguém
  deveria ter que escrever exatamente igual (era texto livre em 24 filtros).
  Coluna cujo `valor` devolve ARRAY (tags, cargos) entra **item a item**, senão
  a opção seria a string concatenada e não filtraria nada. Continua `'texto'`
  o que se busca por TRECHO: nome de pessoa ("mari" acha Maria e Mariana),
  descrição livre, telefone, matrícula, ID. `'select'` só quando a lista é
  fixa e conhecida (Sim/Não, status). O critério é a natureza do campo.
- **Filtro server-side entra na barra do dash, NUNCA num card à parte** (regra
  da v2.30, aplicada a Admissões e Colaboradores só na v2.51): as duas telas
  tinham DUAS caixas de filtro empilhadas, com o mesmo campo nas duas (status
  em Admissões; nome e posto em Colaboradores) — uma consultando o servidor,
  outra a memória. Use `filtrosExtras` do `DashPlanilha` e **tire o `filtro:`
  da coluna que o filtro do pai cobre** (um assunto, um controle); a coluna
  segue ordenável e os cards clicáveis continuam funcionando, porque a
  filtragem em memória roda sobre TODAS as colunas. `filtrosExtras` sem
  `opcoes` vira campo de TEXTO com debounce; `acoesFiltro` põe botões próprios
  na barra (foi onde o "Exportar planilha" foi parar).
- **NUNCA escreva `<select>` nativo — o padrão é `SelectBusca`** (v2.50, pedido
  do Bruno: *"toda vez que tiver um select, já imponha esse padrão"*). Vale para
  filtro E preenchimento, em qualquer tela. Ele tem 111 cargos, 269 jornadas e
  dezenas de postos: rolar até achar era a queixa nº 1 do dia a dia. O
  componente aceita **duas formas** — `opcoes={[{valor, rotulo, extra}]}` (a
  original) ou **`<option>` como filhos**, igual a um `<select>` nativo (foi o
  que permitiu converter os 64 de uma vez, sem reescrever cada bloco). A opção
  de `value=""` vira automaticamente o "— nenhum —" do topo. **O campo de busca
  só aparece a partir de `MIN_BUSCA` (7) opções**: em lista de 2 itens
  (Sim/Não) o campo seria um passo a mais, e no celular a roda nativa é melhor
  de operar com o polegar — o padrão de USO é único, muda só a densidade.
  Dados carregados 1x pelo pai e filtrados em memória. O
  `test_design_system.py` reprova `<select>` no CI.
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
- **Integração Tirvu — CASA POR TEXTO desde 2026-08-08 (era por ID)** (v2.83,
  SEGUNDA reversão desta premissa): o export escreve **`posto.nome`,
  `cargo_funcao` e `jornada.descricao`** nas três colunas. O Tirvu MUDOU: em
  2026-07-24 colar o texto fazia ele gravar ZERO (por isso o export passou a
  mandar `tirvu_id`), e em 2026-08-08 o Bruno **testou uma importação com o
  texto na célula e ela foi aceita**, cargo inclusive. ⚠️ **Se voltar a exigir
  ID, o sintoma engana**: o Tirvu ACEITA a planilha e grava o vínculo ZERADO,
  calado — não confie em "a importação passou", confira um vínculo na tela dele.
  Ganho colateral: com ID, quem estava em posto/jornada sem `tirvu_id` saía com
  célula VAZIA (na base real, **19 postos e 23 jornadas**); o texto vem do
  próprio cadastro e existe sempre. **A pendência mudou de NATUREZA** — antes
  era "o ID não foi cadastrado" ("ID Tirvu do posto"), agora é "esta pessoa não
  tem posto na ficha", e os rótulos viraram `Posto`/`Cargo`/`Jornada`; o texto
  antigo mandaria o RH procurar no cadastro de IDs, onde não há o que corrigir.
  O de-para `CargoTirvu` **continua vivo e alimentado** (guarda o CBO, que
  distingue homônimo), só não é mais consultado no export —
  `tirvu_id_do_cargo` foi REMOVIDA por ficar órfã. Os `tirvu_id` de posto e
  jornada seguem sendo cadastrados e usados na IMPORTAÇÃO (é por eles que a
  planilha de Postos casa sem duplicar). **Empresa vai por RAZÃO SOCIAL**
  (v2.83.1 — era o ID `"1"`): `EMPRESA_RAZAO_SOCIAL_PADRAO` em
  `export_tirvu.py` é o PADRÃO, usado quando a ficha não tem `empresa_id` (o
  caso da esmagadora maioria: o grupo opera com uma empregadora só, decisão do
  Bruno 2026-07-24). Quem TEM o vínculo usa a razão social DELE — se surgir uma
  segunda empregadora (Nossa Cozinha), o export acerta sozinho em vez de
  carimbar Green House em todo mundo. Nunca é vazia, então NÃO vira pendência.
  A tela de Empresas em Config não pede ID. O modelo `docs/Layout de Importação de Admissões.xlsx` só tem cabeçalho
  (sem linha de exemplo) — por isso a validação de julho aprovou a FORMA e errou
  o CONTEÚDO. Agora: `PostoServico.tirvu_id` (já existia) e `Jornada.tirvu_id`
  (novo), e o de-para `CargoTirvu` (cargo texto→id, casado por `normalizar_cargo`:
  minúsculo/sem acento/espaços — cargo NÃO vira FK, só um mapa lateral usado no
  export). Há também `Empresa.tirvu_id` (coluna criada na migration) mas ele NÃO
  é usado — empresa é fixa=1 no export. A coluna "Descrição da Jornada de
  Trabalho" hoje recebe a DESCRIÇÃO mesmo (de 2026-07-24 a 2026-08-08 recebeu o
  ID, apesar do nome). Vínculo ausente vira PENDÊNCIA (`pendencias_linha`
  inclui Posto/Cargo/Jornada — NÃO Empresa). RH cadastra os IDs de Cargo em Config→Cargos, de
  Jornada na página de Jornadas e de Posto na página de Postos (input inline
  `.campo-pendente`/"— sem ID" âmbar quando vazio) — o de Posto vem pronto da
  importação da planilha de Postos do Tirvu (casa por ID; GHS=49). Rotas: `/rh/cargos-tirvu` (GET lista cargos usados×ID, PUT upsert;
  tirvu_id vazio REMOVE o de-para). `PostoIn.tirvu_id` só é gravado na edição se
  a chave veio no payload (`model_fields_set`) — editar outro campo não apaga o
  ID. `criar_empresa` no ramo "já existe" preenche o `tirvu_id` se estava vazio.
  Export re-deriva a CTPS SEMPRE do CPF; se o CPF for inválido/ausente, cai na
  CTPS gravada (não perde o dado).
- **CTPS Digital — série = 4 ÚLTIMOS do CPF, número = 7 PRIMEIROS** (feedback
  2026-07-24, corrige o "0000" anterior): `ctps_do_cpf` devolve `(cpf[:7],
  cpf[-4:])` — juntos reconstroem o CPF, é assim que o Tirvu importa. O export
  SEMPRE re-deriva do CPF (ignora o `ctps_numero/serie` gravado, que em fichas
  antigas é o formato velho CPF+"0000") — NÃO backfilla o banco, NÃO toca PDF
  assinado. `salvar_documentos` grava o formato novo só para quem preenche agora.
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
  importação). **Registra Ponto** também é pendência (v1.82): em branco, o Tirvu
  aceita a célula vazia CALADO e o colaborador nasce lá sem a marcação. Virou
  pendência em `pendencias_linha`, não campo obrigatório no formulário — exigir
  na tela travaria a edição dos importados, que nasceram sem o campo; o front só
  marca o select em âmbar (`.campo-pendente`). Rótulo amigável das pendências em
  `_ROTULO_PENDENCIA` (a coluna tem nome técnico). O arquivo é
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
  em `revisao.py` e serve candidato ou colaborador. CTPS Digital derivada do CPF
  (ver armadilha dedicada acima: número = 7 primeiros, série = 4 últimos; export
  re-deriva), nunca perguntada. Endereço: coleta nova é separada
  (logradouro/numero/complemento); o legado (string única) vai inteiro na coluna
  "Endereço" e migra só pelo backfill ASSISTIDO (parser propõe, RH confirma —
  heurística cega erra endereço de Brasília).
- **Trocar matrícula guarda a ANTERIOR — e o ponto depende disso** (v2.45,
  `colaboradores.py::trocar_matricula`): a matrícula é a chave com que
  `desempenho.py::_casar_matricula` liga a planilha de ponto do Tirvu à pessoa.
  Trocar sem guardar o número velho parte o histórico de frequência em dois, em
  SILÊNCIO — uma planilha de período anterior deixa de casar e o registro vira
  órfão, sem erro nenhum. Por isso `Candidato.matriculas_anteriores` é uma
  LISTA (recontratação, correção, fusão), e `_casar_matricula` a consulta
  depois de tentar a atual. **A matrícula atual tem precedência**: número
  reciclado vai para quem o usa hoje. Unicidade comparada NORMALIZADA
  (`matricula_norm`: só dígitos, sem zeros à esquerda — "003035" == "3035"),
  senão duas pessoas ficam com a mesma e o ponto cai na errada. Motivo
  obrigatório + auditoria com de → para.
- **Documento pedido DEPOIS da conclusão: `slot.liberado_em`** (v2.43): quando
  o RH marca `pcd` de quem já concluiu/foi aprovado, o LAUDO vira obrigatório
  num checklist congelado — pendência que ninguém consegue resolver. As guardas
  de `documentos.py::enviar_arquivo` abrem exceção para o slot com
  `liberado_em` **e** `status=pendente`: vale para AQUELE documento e mais
  nada (o resto continua fechado; o teste cobre o vazamento). Com o checklist
  ainda ABERTO nada é liberado — o slot aparece pela sincronização normal, e
  etiquetar fluxo comum como "pedido pelo RH" só confunde. Rota genérica:
  `/rh/candidatos/{id}/pedir-documento` (recusa 409 se já enviado). O front do
  candidato roteia para o checklist quando há slot `rejeitado` OU
  `pedido_pelo_rh`.
- **Log: `req=`/`ator=` em toda linha, hora de BRASÍLIA, nível INFO garantido**
  (v2.41, `services/contexto_log.py` + `logs.py::configurar`): o contexto é
  injetado por `FiltroContexto` (contextvars) — nenhum call-site passa nada, e
  é isso que evita buraco justamente onde o defeito aparece. `definir()` no
  middleware; `definir_ator()` no `requer_rh` e no `resolver_token` (candidato
  entra como PRIMEIRO NOME — nunca o token, que é credencial, nem o CPF).
  Três armadilhas já pagas: (1) o formatador tem que ser `_FormatadorBrasilia`
  — o container roda em UTC e o log saía 3h adiantado em relação à tela
  (`fmt.js` já usava America/Sao_Paulo desde 2026-07-16); `TZ` também está nos
  4 serviços do compose E do `portainer-stack.yml`, o que alinha a virada
  diária do arquivo. (2) `configurar()` força `INFO`: o nível vinha do
  `basicConfig` do `main.py`, que os WORKERS não importam — tudo que eles
  registram com `log.info` se perdia. (3) A busca aceita VÁRIOS termos (E, não
  OU): `creche ERROR` cruza as duas perguntas.
- **Anexo de e-mail: o tipo vem da EXTENSÃO** (v2.41, `email._tipo_do_anexo`):
  todo anexo saía chumbado como `application/pdf`, então o `.txt` do log
  chegava "corrompido" e não abria — o arquivo estava perfeito, o envelope é
  que mentia. `.md` precisa de caso próprio (não está no `mimetypes` de todo
  sistema). Ao acrescentar formato novo de anexo, conferir aqui.
- **Sugestão por similaridade: PALAVRA inteira vence semelhança de letras**
  (v2.40, `colaboradores.py::_sugerir_postos`): o `SequenceMatcher` sozinho
  colocou **`IPAM` na frente de `INEP - 37/2025 - APOIO ADM`** para a lotação
  `INEP ADM` — 174 pessoas —, porque as letras I-P-A-M aparecem na ordem. Erro
  desse tipo é aceito num clique e **nada o acusa depois**: a pessoa fica no
  contrato errado e o sistema não tem como saber. Some um bônus por palavra do
  texto que reaparece INTEIRA no candidato. Onde o empate é real (`ANAC` = sede
  ou aeroporto), a tela deixa o campo VAZIO — pré-selecionar seria decidir no
  lugar do RH disfarçando de sugestão. Vale para qualquer fila de equivalência
  assistida (a da Incidência de Benefícios usa o mesmo raciocínio).
- **Upload de arquivo NUNCA passa pelo `req()` do `api.js`** (v2.39.1, bug de
  campo 2026-08-01): `_req` força `Content-Type: application/json`, e com
  `FormData` quem precisa escrever o cabeçalho é o NAVEGADOR — só ele conhece o
  `boundary` que separa as partes. Sobrescrito, o FastAPI não separa nada e
  responde **422 `Field required`** para o campo do arquivo… com o multipart
  inteiro impresso no log ao lado, arquivo e conteúdo à vista. É o erro mais
  enganoso do projeto: parece falta de dado onde o dado está. Use `buscar()`
  direto (é o que os uploads antigos sempre fizeram, por isso funcionam).
  Coberto por `tests/test_upload_multipart.py`, que é ESTRUTURAL: lê o `api.js`
  e cobra a regra de toda função que monta `FormData` — vale para o próximo
  upload, não só para os de hoje.
- **Vínculo em massa pela planilha do Tirvu** (v2.39,
  `services/vinculo_tirvu.py`, rotas `/rh/colaboradores/vinculos/preview` e
  `/aplicar`): a planilha de Colaboradores traz `Lotação`, `Cargo`, `Jornada de
  Trabalho` e `PCD?` por pessoa — a importação lia só as duas primeiras. O
  módulo é PURO (recebe MAPAS prontos, não a sessão) justamente para obrigar o
  chamador a carregar em lote: com 1.156 linhas, uma consulta por linha é a
  diferença entre segundos e minutos. Regras que não devem ser afrouxadas:
  **campo vazio no portal é preenchido, campo DIFERENTE nunca é sobrescrito**
  (pode ser correção manual do RH; vira lista de decisão) e **o que não casa
  sai em fila com quantas pessoas dependem**. Números reais medidos: cargo casa
  100%, jornada 99%, **posto 11%** — a lotação vem abreviada ("INEP ADM" = 174
  pessoas) e o mesmo texto pode ser dois postos, então posto NÃO se resolve
  sozinho. CPF de 11 dígitos não basta: `000.000.000-00` viraria "pessoa fora
  do portal" e esconderia o cadastro sujo na origem.
- **Arquivo .txt do Tirvu: decodifique os TRÊS formatos** (v2.38,
  `importar_tirvu_txt.decodificar`): o RH cola a tela do Tirvu no Bloco de
  Notas e salva — que grava em UTF-8, UTF-8 com BOM ou ANSI (cp1252) conforme a
  versão do Windows. Ler com o codec errado NÃO levanta erro: quebra o acento e
  o casamento por texto falha CALADO, justamente nos cargos acentuados. As
  rotas `preview-cargos-arquivo`/`preview-jornadas-arquivo` só trocam a porta
  de entrada — delegam ao MESMO preview do texto colado, e a regra de propor +
  confirmar continua valendo. `cargo_tirvu.cbo` guarda o que DISTINGUE
  homônimo; `jornada.tirvu_escala`/`tirvu_tratamento` são do cadastro do Tirvu
  e NÃO se confundem com `jornada.escala` (metadado interno do parser, outro
  vocabulário). Campo vazio no arquivo NUNCA apaga o já gravado.
- **Padronização em massa de cargos/jornadas do Tirvu** (v1.96,
  `services/importar_tirvu_txt.py`, rotas `/rh/tirvu-txt/*`, tela em
  Config→Empresas e jornadas): resolve a causa raiz das pendências manuais do
  export — o RH cola o texto copiado direto da TELA do Tirvu (não é upload de
  arquivo) e o sistema PROPÕE o de-para; nunca grava sozinho (preview →
  confirmar, mesma mecânica da Incidência de Benefícios). O texto colado é
  `ID\tCampos...` por linha, com "lixo" de UI (avatar, responsável, data)
  intercalado — filtra por `^\d+\t`. **Contagem do cabeçalho** ("Lista de
  Cargos 111") é conferida contra o total parseado — cópia parcial da tela
  vira erro, não importação incompleta silenciosa. **Sujeira conhecida**: a
  descrição de jornada às vezes vem com "Sem vínculos"/"N vínculos" colado
  no FIM sem separador (é a coluna seguinte da tela que grudou na cópia) —
  `limpar_descricao_jornada` remove antes de casar. **Cargo homônimo com 2+
  IDs ATIVOS no Tirvu NUNCA é auto-resolvido** (ex. real: "AUXILIAR DE
  SERVIÇOS GERAIS" tem CBO 514225=limpeza e 763125=produção, 87 pessoas na
  base usam o mesmo texto) — o de-para é por TEXTO normalizado
  (`cargo_funcao` não é FK), então o sistema não tem como saber qual pessoa é
  qual; fica marcado "⚠️ ambíguo" na tela, o RH decide caso a caso ou nem
  marca (a importação segue sem aquele item). Mesma regra para jornada
  duplicada (descrição idêntica após limpar a sujeira, IDs diferentes).
  `Jornada.descricao` é `unique=True` — a rota de confirmar CASA por
  descrição normalizada antes de decidir criar vs. atualizar, nunca duplica.
- **Fila de tarefas** (`services/fila.py`, v2.00): Redis + RQ. O ecossistema
  já tinha Redis e um container `worker` rodando `rq worker ... default`
  desde a v1.83, mas **ninguém nunca enfileirou nada** — os workers antigos
  (expurgo, avisar_vencimentos, expirar_roteiros) são cron, não passam pela
  fila. Use `fila.enfileirar(funcao, *args)` para qualquer trabalho que
  possa passar de ~30s. **O nginx corta request acima de 60s** (`location
  /api/` usa o default; a exceção de 600s existe só para
  `/api/rh/arquivo/lote`) — trabalho longo NÃO pode ser síncrono. As funções
  enfileiráveis ficam em `app/workers/*.py` com assinatura simples (só ids,
  nunca objeto do SQLAlchemy — o RQ serializa a referência, não o código).
- **Texto de origem externa é DADO, nunca instrução** (regra geral,
  cravada em v1.99 pelo próprio Bruno durante a revisão do roadmap — vale
  para QUALQUER texto de terceiro que um dia chegue a um prompt, não só
  currículo): delimitado com marcador aleatório por chamada, saída da IA
  sempre estruturada (JSON de campos fixos, nunca texto livre), e
  **tentativa de manipulação detectada é REPORTADA ao usuário do painel,
  jamais filtrada em silêncio** — mesmo princípio já usado no lote de
  documento crítico (`desenvolvimento.py`: "o lote diz quem barrou, com
  nome e motivo"). Ver `services/anti_prompt_injection.py`.
- **Navegação do painel do RH tem URL própria** (v1.97, `RHApp.jsx`): o
  `react-router` estava instalado desde sempre e `App.jsx` já reservava
  `/rh/*` com um splat, mas dentro do painel tudo era `useState('inicio')` —
  por isso botão direito não oferecia "abrir em nova aba" (não havia
  `<a href>` nenhum), F5 sempre voltava para Admissões, e não dava para abrir
  duas pessoas em duas abas. Agora `Painel` declara `<Routes>` (`candidato/:id`,
  `:pagina`, raiz) e `PainelConteudo` lê `useParams()`/`useNavigate()`; o menu
  lateral usa `<NavLink to={...} end>` (o `end` evita que `/rh` fique "ativo"
  em toda subrota). `abrirPessoa(id)` substitui o antigo `setSelecionado` nas
  telas filhas — navega para `/rh/candidato/{id}` em vez de mexer em estado
  local. Ao criar uma tela nova no menu, sempre usar `<NavLink>`/`<Link>`,
  nunca `<button onClick={() => setPagina(...)}>`.
- **Modal** (`frontend/src/Modal.jsx`, v1.97 — primeiro do projeto): usado
  quando o conteúdo tem anexo + histórico + texto longo e não cabe inline
  (ver `08-sistema-de-design.md`, item 4, revisado). Reaproveita o padrão de
  fechar do `SelectBusca` (clique fora + Escape), tem `role="dialog"` e foco
  preso. Antes de criar outro modal, ver se este serve — é o único e deve
  continuar sendo, para não fragmentar o padrão.
- **Central de Importações** (`frontend/src/rh/Importacoes.jsx`,
  Config → 📥 Importações, v1.97): os uploads de planilha do RH (Colaboradores,
  Postos, Jornadas ×2, Talentos, Ponto) foram MOVIDOS para cá — as telas de
  origem não têm mais o `<input type="file">`, só um texto apontando para
  cá. **Ao adicionar upload de planilha novo, criar o card aqui, não na tela
  de origem.** Exceções que continuam em tela própria (e por quê): Incidência
  de Benefícios é fluxo de 2 passos com decisões linha a linha (embutir seria
  reescrevê-la à toa) e a padronização de cargos/jornadas é texto colado, não
  upload de arquivo — ambas ganharam só um card-atalho na central.
- **Filtro server-side vai em `filtrosExtras`, NÃO num card à parte** (v2.30,
  feedback do Bruno com print: *"tem dois cards, acho que apenas um, tudo
  concentrado e coeso de filtros"*): o creche tinha DUAS caixas de status na
  mesma tela — a server-side num `rh-card rh-lote` acima e a `Status: todos` da
  barra do dash. Filtrar por uma enquanto a outra dizia outra coisa dava
  resultado que parecia errado. `DashPlanilha` aceita
  `filtrosExtras={[{chave, rotulo, valor, opcoes, aoMudar, vazioRotulo?}]}` e
  os renderiza na MESMA grade. **Um assunto, um controle**: se o filtro do pai
  cobre uma coluna, tire o `filtro:` dela — a coluna segue ordenável e os cards
  clicáveis continuam, porque a filtragem em memória roda sobre TODAS as
  colunas, não só as que declaram `filtro`. O filtro continua server-side (não
  virou filtro de coluna: a base é a folha inteira, trazer ao cliente é
  regressão de performance E de LGPD).
- **Incidência de Benefícios** (`incidencia_beneficios.py`): a planilha do RH
  (abas PÚBLICO/PRIVADO) normaliza os postos no padrão `CLIENTE - Nº CONTRATO -
  OBJETO` e define a elegibilidade creche pela coluna "Reembolso creche/Mês". Lê
  as DUAS abas via zip+XML próprio (`_ler_abas` — o `_ler_linhas_xlsx` de
  `postos.py` lê só a 1ª). Equivalência com o Tirvu é ASSISTIDA: o sistema PROPÕE
  por similaridade (Cliente vs nome/sigla), o RH CONFIRMA cada linha (nunca merge
  cego — regra dos ~40 erros de digitação). Valores compostos (dois sindicatos
  numa célula) ficam como texto p/ decisão humana. `await arquivo.close()` no
  `finally`. Export normalizado p/ carga futura no Tirvu ficou p/ a próxima leva.
- **Portal do colaborador `/meu`** (`api/portal.py`, `Portal.jsx`): UMA porta
  para tudo que é da pessoa — o oposto de `/creche`, `/desenvolvimento`,
  `/brigada` separados. Gate IDÊNTICO ao do creche (CPF → 2FA por e-mail; sem
  e-mail, KBA), com `AcessoPortal` amarrado ao COLABORADOR (o `AcessoCreche` é
  amarrado ao benefício). A home é a lista de PENDÊNCIAS dele, não um menu. O
  `VerificarIdentidade` do `CrecheLink.jsx` foi EXPORTADO e parametrizado (as 3
  funções de KBA entram por prop) — reusar, não duplicar. O **motivo da recusa é
  visível ao colaborador** (decisão do Bruno); o campo no painel do RH avisa
  isso. Sensibilidade do arquivo é decidida pelo PAPEL, não pelo que o usuário
  diz.
- **DashPlanilha — detalhe na linha** (`linhaExpandida`, v1.83): painel abre
  numa `<tr>` LOGO ABAIXO da linha clicada, nunca no topo da página (feedback do
  Bruno: "quando clica, tem que abrir perto do nome da pessoa"). O painel NÃO
  herda a largura da tabela, que rola na horizontal — fica preso à largura
  visível via `container-type: inline-size` + `position: sticky`. Sem isso,
  metade dele fica fora da tela. As abas do projeto usam a classe **`ativa`**
  (não `on`).
- **Avisos internos = MATRIZ evento × destinatários** (`services/notificacoes.py`,
  v1.82): NUNCA mandar aviso interno direto para `smtp_from` — é a caixa de
  LOGIN, pessoal (foi o que fez o Bruno receber "candidato concluiu o envio" no
  e-mail dele). Use `avisar(db, "<evento>", assunto, corpo)`. Evento novo =
  entrada nova em `EVENTOS` (chave estável + rótulo + descrição) e nada mais: a
  tela do painel é dirigida por esse catálogo. Herança em cascata: lista do
  evento → `email_avisos_internos` (padrão global) → remetente. Evento com
  `ativo: false` não avisa NINGUÉM; evento fora do catálogo cai no padrão (aviso
  novo que alguém esqueceu de cadastrar ainda chega a alguém). Guardado como
  JSON na config dinâmica — sem migration. `avisar()` NUNCA levanta: aviso
  interno que falha não pode derrubar a ação do candidato que o disparou.
- **Cargo/função é STRING, não FK** (v1.82): `Candidato.cargo_funcao` continua
  texto livre — `ModeloDocumento.cargo_alvo`, o filtro do Arquivo e as provas
  por cargo casam por TEXTO, e virar tabela quebraria os três. `GET /rh/cargos`
  devolve os cargos já usados na base com a contagem de pessoas (mais frequentes
  primeiro) só para alimentar o `SelectBusca` do front — escolher da lista evita
  "Vigia"/"vigia"/"Vigía" virando três cargos; a opção "＋ Cargo novo…" troca
  para input livre. O cargo ATUAL é injetado na lista mesmo se não vier da API,
  senão o seletor apareceria vazio para cargo raro.
- **Campo novo em ficha assinada**: ACRESCENTAR campo não invalida assinatura
  (EDITAR invalida — regra de 2026-07-15). Tecnicamente: renderizar o campo novo
  SÓ se preenchido (`if`, como CNH/CTPS/laudo PCD em `fichas.py`) — o PDF é
  gerado sob demanda e a ficha antiga deve sair idêntica. O PDF assinado fica
  persistido no MinIO com hash do ato, então reformatar seções não quebra vias
  antigas.
- **Informativo de integração só após disparo do RH** (v1.92): o informativo
  (ficha de integração do regime — `informativo_efetivo` OU
  `informativo_intermitente`, mapeados em `INFORMATIVO_POR_REGIME`; mais o
  ofício `informacoes_trabalhador` do kit INFRAERO, que NÃO é ficha de
  integração — conjunto `DOCS_INFORMATIVO` em `postos.py`) NASCE
  com `Assinatura.aguardando_liberacao=True` no `gerar_docs_do_posto_e_regime` e
  fica OCULTO em `_docs_exigidos` (filtra `aguardando_liberacao IS False`) até o
  RH chamar `/rh/candidatos/{id}/liberar-informativo`. Todos os DEMAIS docs
  nascem `False` (liberados) — comportamento inalterado. Painel:
  `/informativos` lista + botão "Liberar" no `Detalhe` (`PainelInformativo`).
- **Autodeclaração de residência** (v1.92, `DocumentoAssinavel.autodeclaracao_residencia`):
  exigida SÓ quando o comprovante é de terceiro. O candidato preenche
  `endereco.comprovante_titular`/`comprovante_relacao` no wizard;
  `_sincronizar_autodeclaracao_residencia` (`ficha.py`, no salvar-endereço) CRIA
  a Assinatura quando o titular está preenchido e a REMOVE (se ainda não
  assinada) quando é limpo. Gerador `gerar_autodeclaracao_residencia` usa o
  helper `_declaracao`. **Cargo obrigatório no convite** (v1.92): 422
  `cargo_obrigatorio` em `candidatos.py` (o smoke cobre). **Insert manual do RH
  aceita N arquivos** → 1 PDF (`inserir_arquivo_rh` reusa `combinar_pdfs` +
  `_gravar_partes_no_slot`). **Import Tirvu não zera matrícula vazia**
  (`colaboradores.py`: guarda `if k in ("nome_completo","matricula") and not val`).
- **Resumo do CRM na LINHA do dash + o N+1 que ele revelou** (v2.15): o dash
  de Talentos mostrava "🗒️ Anotações" em todo mundo e o RH só descobria que
  não havia nada depois de abrir o modal; o 📎 do currículo era enfeite.
  Agora `_dump` traz `anotacoes` (quantas), `ultima_anotacao`/`_autor`/
  `_quando`, carregados em LOTE por `crm.resumo_anotacoes_por_talento`
  (mesma mecânica de `tags_por_talento`, unindo talento+candidato). Na linha,
  currículo e anotações viram atalhos clicáveis logo abaixo do nome, com a
  última anotação no `title`. **O teste de N+1 que escrevi para isso expôs um
  N+1 ANTIGO**: `testes = {t.id: _resumo_teste_talento(db, t.id) ...}` fazia
  até 3 consultas por talento — com o comentário "1 consulta, sem N+1" logo
  acima. Virou `_resumo_teste_por_talento` (3 consultas no total): a listagem
  caiu de **43 consultas para 39 talentos → 5 consultas**, constante.
  Armadilha do teste: medir N+1 com LIMITE ABSOLUTO não funciona (mede o
  tamanho do banco, que cresce a cada execução) — compare DUAS listagens de
  tamanhos diferentes e exija que a diferença de consultas não acompanhe a de
  registros.
- **Arquivar talento ESCREVE no mini-CRM, não ganha campo próprio** (v2.14,
  `talentos.py::mudar_status`): o RH pediu "observação e arquivo ao arquivar,
  com responsável e quando, e poder desfazer" — e a `Anotacao` do CRM já tinha
  texto, anexo, autor SNAPSHOT e data. Então `StatusIn.motivo` (opcional) vira
  uma anotação (`"Arquivado — <motivo>"`, `"Reaberto — …"`), o histórico da
  pessoa fica num lugar só e anexar documento já funciona pela tela de
  anotações. Desfazer é mudar o status de volta; o registro permanece porque a
  anotação é append-only. Motivo vazio/só espaços NÃO cria anotação. O lote de
  arquivamento pede UM motivo para todos e **presta contas de quem não foi**
  (antes tinha `.catch(() => {})` e dizia que arquivou tudo).
- **Teste que só passa em banco limpo é armadilha** (v2.14): o
  `test_jornadas_confirmar_lote` criava jornadas com descrição fixa e a
  `descricao` é `unique=True` — rodar duas vezes no mesmo banco falhava com
  "as 3 criadas deveriam estar na fila: 0", que não diz nada sobre a causa.
  Agora usa sufixo `uuid` por execução. Ao escrever teste que grava em tabela
  com campo único, sempre gerar o valor por execução.
- **REGRA: e-mail novo e documento novo NASCEM na sua página** (v2.21, cravada
  pelo Bruno em 2026-07-29). Nunca mais escrever e-mail em f-string no call
  site nem documento só no gerador:
  - **E-mail novo** → entrada no `CATALOGO` de `services/email_templates.py`
    (rótulo, `quando`, variáveis, obrigatórias, exemplo p/ o preview) +
    `enviar_modelo(...)`. Se for AVISO INTERNO, também: entrada em
    `notificacoes.EVENTOS`, o campo `evento=` no modelo (é o que liga o
    template à matriz) e `avisar_modelo(...)`. Os destinatários são vários,
    separados por vírgula, editáveis em Configurações → Textos dos e-mails E em
    Avisos internos — **é a MESMA matriz**, exposta nos dois lugares, não duas
    fontes de verdade.
  - **Documento novo** → entrada no `CATALOGO` de
    `services/documentos_catalogo.py` com o `Formato` correto; se for texto
    corrido, corpo em `documentos_texto.py` (importando de `fichas.py` quando
    o conteúdo já existe em constante — nunca copiar). O vínculo com
    posto/cargo/pessoa continua em `ModeloDocumento.escopo`.
  - Os dois catálogos se autovalidam: `test_email_templates` exige que todo
    aviso interno tenha evento correspondente, e `documentos_catalogo` compara
    com o enum `DocumentoAssinavel` no import.
- **Avisos internos também saem do catálogo** (v2.20): os 8 avisos que vão à
  EQUIPE (RH, operacional, líder de brigada) passaram a usar
  `notificacoes.avisar_modelo(db, evento, chave_template, contexto)` — mesma
  entrega de `avisar` (matriz de destinatários, nunca levanta), mas assunto e
  corpo vêm do catálogo, editáveis com preview e histórico. O motivo não é
  cosmético: **quem recebe nem sempre conhece o sistema** — o Gabriel e o Vitor
  recebem o de uniforme, o líder de brigada recebe o de certificação.
  `avisar()` continua para aviso com texto montado na hora. Template ausente
  degrada para 0 envios + log, nunca derruba a ação que o disparou.
  **Bug corrigido junto**: o aviso de dossiê pronto (`revisao.py`) lia
  `email_avisos_internos` DIRETO, fora da matriz — desligar o evento no painel
  não o desligava e cadastrar destinatário não funcionava. Virou o evento
  `dossie_pronto`. Ao criar aviso interno novo: entrada em `EVENTOS`, entrada
  no `CATALOGO` (grupo "Avisos internos") e `avisar_modelo` no ponto de envio —
  o teste cobra que todo aviso do catálogo tenha evento correspondente.
- **Teste já respondido aproveitado para o candidato** (v2.21,
  `models/teste_vinculado.py`, `services/testes_vinculaveis.py`,
  `TestesVinculados.jsx`): a pessoa respondeu DISC/situacional ou uma prova
  ANTES de virar candidata; o RH aproveita o resultado em vez de mandá-la
  refazer. **Aponta, não copia** — o vínculo referencia o
  `ParticipanteTestagem`/`AplicacaoProva` e o resultado é lido na origem.
  **A identidade é registrada como o que é**: `automatico=True` quando veio do
  Banco de Talentos (o link tinha `talento_id`, então o sistema sabe de quem
  é, e a conversão talento→candidato vincula sozinha); `automatico=False`
  quando o RH escolheu da lista, com autor snapshot. Isso existe porque o link
  avulso de testagem é ANÔNIMO (`ParticipanteTestagem` guarda só o nome) e
  homônimo decide contratação — por isso a lista de escolha mostra nome, data,
  qual teste e por qual link. **Só o RH vê**: não entra no wizard nem no
  dossiê, que circula.
- **Catálogo dos documentos do sistema** (v2.19,
  `services/documentos_catalogo.py`, `documentos_texto.py`, rotas em
  `modelos.py`, seção em `Modelos.jsx`): o RH vê os 11 documentos que a
  admissão gera, com amostra em PDF (candidato FICTÍCIO, nunca vai ao banco),
  download, e — nos de TEXTO CORRIDO — "criar modelo a partir deste", que
  copia o conteúdo para um `ModeloDocumento` editável.
  **NENHUM gerador foi substituído, e não devem ser**: o hash do ato de
  assinatura é calculado sobre o PDF gerado (`assinaturas.py`), então trocar
  um gerador por template faria os manifestos já emitidos apontarem para um
  hash que não se reproduz. Duplicar CRIA CÓPIA; o oficial segue intacto.
  Classificação em `Formato`: `texto` (3, duplicáveis) · `formulario` (3:
  campos em tabela e loops da ficha) · `hibrido` (5: branch, tabela desenhada,
  ou dados que **não existem** em `VARIAVEIS_MODELO` — RG, endereço, titular
  do comprovante). O catálogo se autovalida contra o enum no import.
  **Corpo editável NÃO PODE divergir do documento oficial**: a 1ª versão tinha
  a lista de direitos do informativo INFRAERO escrita à mão e perdeu 6% do VT,
  8% do FGTS e o 5º dia útil — texto plausível e errado num documento de
  contrato com órgão público. Virou `fichas.DIREITOS_TRABALHADOR` (fonte
  única, importada dos dois lados) e o teste ganhou ÂNCORAS (trechos que
  existem no oficial) — "corpo não vazio + tem `{{`" deixava passar.
- **Código por e-mail: a mensagem tem que dizer o que RESOLVE** (v2.17/v2.18,
  incidente de campo 2026-07-29 — "foi eu mesmo quem copiou e colou o código,
  impossível ter erro"). O código estava certo. A cota é **5 pedidos por
  CPF/token a cada 15 min**; estourada, o e-mail não sai — e o front dizia
  outra coisa. Três defeitos de mensagem, todos corrigidos:
  (1) `CrecheLink`/`Portal` AVANÇAVAM de etapa mesmo com o envio falhando (o
  429 caía no `catch` genérico), então a pessoa colava o código do e-mail
  anterior; (2) `Assinatura.jsx` tinha `catch` cego dizendo **"verifique sua
  conexão"** para erro de cota — pior que inútil, porque convida a tentar de
  novo na hora e reabastecer a cota; (3) `AssinarExterno` tinha `catch {}`
  MUDO no pedido de código. Regras que ficam: **nunca avançar de etapa quando
  o envio falha**; 429 tem frase própria ("aguarde 15 min OU use o último
  código que chegou"); e "código incorreto" deve dizer *use o do e-mail MAIS
  RECENTE* — reconferir um código certo é o que a pessoa faz quando a
  mensagem não explica. Diferença entre os fluxos, medida em
  `tests/test_codigo_cota.py`: na ASSINATURA e no TESTE o código é
  sobrescrito no mesmo registro, então **o último enviado continua valendo
  depois do 429** (é o que autoriza a orientação na tela); no creche/portal o
  registro era outro, e por isso o defeito lá era grave.
- **Creche: a pessoa MANIFESTA, não some em silêncio** (v2.34, pedido do Bruno
  2026-07-30): o link abre com a PERGUNTA ("você tem criança que dá direito?")
  e as duas respostas lado a lado, com o mesmo peso; o formulário só aparece
  depois da escolha. Antes, o "não tenho" era um `btn-link` de texto pequeno
  DEPOIS do botão de enviar, dentro do cartão "Crianças" — quem não tinha filho
  nunca chegava lá. **O motivo é jurídico**: sem manifestação, "não respondeu"
  e "não tem direito" são a MESMA linha em branco, e não se prova que o
  elegível foi consultado. Regras: `sem_direito` registra quem/quando/IP;
  **409 `ha_criancas_cadastradas`** (o registro não pode contradizer o dado ao
  lado); a declaração é REVERSÍVEL pelo `/reabrir` (quem não tem filho hoje
  pode ter amanhã); e quem declara vê tela PRÓPRIA ("Resposta registrada"), não
  a de "Levantamento enviado" — que faria esperar um e-mail que nunca vem. No
  painel, o quadro `elegíveis · responderam · declararam não ter · faltam`
  aparece SEMPRE, inclusive com zero pendentes. "Declarou que não tem" conta
  como resposta; levantamento aberto e nunca enviado NÃO conta.
- **Um envio tem N ARQUIVOS, o registro guarda a key de UM** (v2.35):
  `_gravar_partes_no_slot` grava `slots/{id}/original/{i}-{nome}` para cada
  parte (frente, verso, páginas da certidão), mas `SlotDocumento` só tem
  `arquivo_original_key` — a do PRIMEIRO. Quem tratar esse campo como "o
  original" erra por omissão, e a omissão é invisível: **o expurgo deixava o
  verso do RG no MinIO para sempre** (LGPD), e "ver o que enviei" mostraria a
  frente dizendo que era o envio inteiro. Liste pelo PREFIXO do slot
  (`storage.listar`, como `expurgar_arquivos_do_slot` e
  `documentos.py::_originais_do_slot` fazem), com o campo do registro só como
  fallback. **Ordene pelo número do prefixo**: a listagem do storage é
  lexicográfica e põe `10-` antes de `2-` — o verso no lugar da frente.
  Servir por ÍNDICE resolvido contra a listagem, nunca montar caminho com o
  nome do arquivo (é texto do usuário; mesma regra do `export_planilha.slug()`).
- **O PDF do slot é o documento do RH, não o da pessoa** (v2.35): o
  `arquivo` do candidato (`/c/{token}/documentos/{id}/arquivo`) serve o PDF
  TIMBRADO — a foto reduzida e centralizada numa A4. Está certo para o dossiê
  e ERRADO para alguém julgar se a própria foto ficou legível: a miniatura faz
  foto boa parecer ruim. Quem confere o próprio envio vê o ORIGINAL
  (`/original/{indice}`), com o timbrado a um toque. Vale a regra geral da
  v2.33 — renderiza na tela, nunca `<a target="_blank">` para a API (PDF em
  aba nova no Chrome do Android BAIXA, e no wizard isso atinge o candidato).
- **Documento RENDERIZA na tela — `VisualizadorArquivo`** (v2.33,
  `frontend/src/VisualizadorArquivo.jsx`): PDF, imagem e Word (convertido) num
  componente só, dentro do painel da linha, com Baixar/Fechar. Regra do Bruno:
  *"todo documento que a gente tentar abrir renderiza na tela, para não
  precisar ficar baixando"*. NÃO use `window.open(URL.createObjectURL(...))` em
  tela nova — era o padrão antigo e, no Word, abria aba EM BRANCO. Word é
  convertido para PDF ao SERVIR (`talentos.py`, via `_word_para_pdf`); o
  **original fica intacto** no MinIO (conversão é de exibição — currículo é
  documento de terceiro).
- **`.mjs` precisa de MIME explícito no nginx — o PDF no CELULAR nunca
  funcionou sem isso** (v2.33, achado em 2026-07-31 conferindo a TELA, não em
  teste): o `mime.types` não conhece `.mjs`, o worker do pdf.js saía como
  `application/octet-stream` e o navegador RECUSAVA o módulo ("Strict MIME type
  checking"). No celular o pdf.js é o ÚNICO caminho (Chrome do Android não tem
  visualizador), então todo PDF caía em "não conseguimos exibir este PDF aqui"
  — inclusive para o candidato. **⚠️ `types { }` SUBSTITUI o mapa inteiro de
  MIME**: sem `include /etc/nginx/mime.types` antes, o `index.html` vira
  octet-stream e o site inteiro vira DOWNLOAD (regressão real, pega pelo teste
  novo). Coberto por `deploy-tela-branca.spec.js`.
- **"Sem internet" quase nunca é sem internet — e o comprovante lia o OCR
  DUAS vezes** (v2.31, relato de campo 2026-07-30): o `comp_endereco` é o
  ÚNICO slot com OCR bloqueante, e `_texto_do_envio` era chamado com os MESMOS
  bytes em `validar_comprovante_recente` (regra dos 90 dias) E no `_texto` de
  `documentos.py` (sugestões). 30s de timeout cada, contra os **60s de
  `proxy_read_timeout`** do nginx: o nginx cortava, o `fetch` rejeitava e o
  front dizia "você está sem internet" para quem estava com a internet boa.
  Quatro camadas: (1) `_texto_do_envio` memoiza por SHA-256 do conteúdo +
  extensão — **a chave TEM que incluir o conteúdo**, senão o texto de um
  documento vaza para a ficha de outro (mutação que o teste pega); (2)
  `location ~ ^/api/c/[^/]+/documentos/` no `nginx.conf` com 300s; (3)
  `api.js` distingue `sem_conexao` (confirmado por `navigator.onLine === false`)
  de `demorou_demais` e `conexao_interrompida` — `fetch` rejeitado NÃO é
  sinônimo de offline; (4) `LeitorComprovante`/`LeitorRG` do wizard pararam de
  dizer "não conseguimos ler a foto" para falha de ENVIO e passaram a emitir
  `falha_no_envio` (não tinham telemetria nenhuma — o ponto mais cego do
  fluxo). Ao mexer no `nginx.conf`, rodar `deploy-tela-branca.spec.js`.
- **Logs dos serviços em ARQUIVO + tela no painel** (`services/logs.py`,
  `api/logs.py`, `workers/logs_email.py`, `rh/LogsRH.jsx`, v2.29): o
  `docker logs` MORRE no restart do container — o diagnóstico do incidente do
  Defender só existiu por sorte. Cada serviço escreve seu arquivo num volume
  compartilhado (`LOG_DIR`/`LOG_SERVICO` no compose E no `portainer-stack.yml`
  — sem os dois, não roda em produção); a tela fica em Configurações → Logs.
  - **NÃO montar `/var/run/docker.sock` na API** para ler o stdout dos outros
    containers: isso dá controle TOTAL do Docker do host a quem comprometer a
    API, que é o que está exposto à internet. Aceita-se ver só os serviços
    nossos; Postgres/MinIO ficam no `docker logs`.
  - **`servico` e `dia` vêm da URL e são validados por regex** antes de virar
    caminho (`_caminho`) — sem isso, `../../etc/passwd` seria leitura de
    arquivo do sistema por rota autenticada. Mesma regra do `export_planilha.slug()`.
  - **Retenção `0` = INDETERMINADO** (decisão do Bruno): não apaga nada.
    Cuidado ao refatorar — trocar `if dias <= 0` por `if dias is not None`
    transformaria "guardar para sempre" em "apagar tudo hoje", em silêncio.
    O log CORRENTE nunca é apagado, só os rotacionados por dia.
  - **Baixar vai para a AUDITORIA** (`logs_baixados`): o arquivo tem CPF,
    e-mail e nome de gente real; tirar isso do servidor é export de dado
    pessoal. Antes eram voláteis, agora são dado ARMAZENADO.
  - Envio 4x/dia pela MATRIZ (`avisar_modelo` com `anexos`, evento
    `logs_periodico`); a janela de 6h fica na config, então o worker rodando a
    cada 15 min não duplica nem pula envio ao reiniciar.
- **GET NÃO PODE TER EFEITO COLATERAL — o antivírus do e-mail abre o link
  antes da pessoa** (v2.28, incidente de campo 2026-07-30): uma colaboradora
  ficou SEIS HORAS sem entrar no creche, com **sete códigos enviados com
  sucesso** (o log do M365 confirma cada um). O `GET /creche/retomar/{token}`
  CONSUMIA o link (confirmava o acesso e zerava `link_expira_em`), e quem abre
  o link primeiro numa empresa com Microsoft 365 **não é a pessoa — é o
  Defender/Safe Links**, que pré-abre todo link para escanear. A assinatura no
  log é inconfundível: o CPF é digitado do IP do órgão e o
  `creche_entrou_pelo_link` chega segundos depois de IPs da **Azure**. Agora
  `retomar` só LÊ; entrar é `POST /creche/entrar/{token}` (e
  `/portal/entrar/{token}`) — **scanner segue link, não faz POST**. O front
  mostra "É você? · Sim, entrar"; o clique consome. Ao criar QUALQUER link de
  e-mail de uso único, a ação destrutiva vai no POST — link em e-mail
  corporativo é sempre pré-aberto por robô.
- **Código de acesso: TODOS os vivos valem, não só o último** (mesma leva): o
  `confirmar` do creche conferia apenas o acesso MAIS RECENTE, então pedir um
  segundo código invalidava calado o e-mail aberto na tela — 422 com o código
  certo na mão. Na assinatura e no teste isso não acontece porque o código é
  sobrescrito no MESMO registro; no creche/portal cada pedido cria um
  `AcessoCreche` novo, então a equivalência EXIGE conferir todos dentro da
  validade. O que limita continua sendo o TTL de 15 min e a cota de tentativas.
- **Tentativa de acesso recusada é REGISTRO, não silêncio** (mesma leva):
  `creche_codigo_recusado` na auditoria e terceiro motivo no relatório "Não
  conseguiram acessar" (*Código recusado*). Antes o relatório só via quem
  **não recebeu** e-mail — quem recebia e travava era invisível, e é o caso
  MAIS enganoso, porque o envio funcionando dá impressão de normalidade.
- **Link de e-mail ENTRA DIRETO no creche e no portal** (v2.17, decisão do
  Bruno que reverte a regra da v2.03): código e link chegam na MESMA caixa,
  logo provam o MESMO fator — exigir os dois era atrito duplicado, não
  segurança em camadas. `link_expira_em` (migration a8b9c0d1e2f3) vale o mesmo
  que o código (15 min) e é de USO ÚNICO; a sessão que ele abre mantém as 6h
  de `expira_em`. Nulo = acesso antigo, que segue exigindo código. O
  `confirmar` deixou de exigir `confirmado_em IS NULL` — quem entrava pelo
  link e ainda assim digitava o código levava "código inválido" com o código
  certo na mão.
- **Fila de decisão precisa ser MEDIDA antes de ganhar ação em massa** (v2.12,
  `jornada_duplicidade.py`): o RH pediu ação em massa nas 325 duplicidades de
  jornada ("um clique cada"). Medindo contra os dados reais (269 jornadas da
  planilha de escalas), a fila tinha **199 pares e só 3 eram duplicata** —
  80 eram o mesmo texto com HORÁRIO diferente (`13H -16H` x `13H -17H`) e 40
  eram o mesmo horário com CLIENTE diferente (INEP x MME, CARLTON CENTER x
  CARLTON TOWER). Resolver 199 "em massa" seria o merge cego que o módulo
  existe para impedir, e o estrago é invisível (jornada errada não dá erro; a
  pessoa descobre no contracheque). O `suspeitas()` deixou de depender só do
  limiar de similaridade e ganhou duas regras ESTRUTURAIS: **números
  diferentes ⇒ jornadas diferentes** (horário é o que distingue turno) e
  **mesmos números + letras diferentes ⇒ clientes diferentes**. Fila: 199 → 3.
  Lição que vale para qualquer fila do painel: quando o RH pede velocidade,
  conferir antes se a fila não está cheia de ruído — velocidade em fila errada
  multiplica erro. Coberto por `tests/test_jornada_duplicidade.py` (casos
  reais da planilha, validado por mutação).
- **`mimetypes.guess_type` depende do SISTEMA — não do código** (v2.81, achado
  pelo CI): a tabela vem do SO (no Linux, `/etc/mime.types`), e a imagem do
  container **não conhece `.xlsx`, `.ics` nem `.docx`**. O teste passava no
  Windows e reprovava no CI, com o anexo saindo como `octet-stream` — e no caso
  do `.ics` isso significa **convite sem o "adicionar à agenda"**, defeito que
  estava vivo no SMTP desde sempre (a v2.68 corrigiu só o caminho do Graph). O
  `email._tipo_do_anexo` agora tem MAPA EXPLÍCITO para essas extensões; o
  comentário do `.md` já previa o problema e ninguém generalizou. **Ao anexar
  formato novo, acrescente ao mapa** — e desconfie de qualquer teste de MIME que
  só rodou na sua máquina.
- **Uniformes: a lista fica na TELA, mas a planilha vai ANEXA no aviso**
  (v2.07 **revista na v2.81** — `revisao.py::uniformes`,
  `services/uniforme_planilha.py`): na v2.07 o Bruno pediu os dados por e-mail
  e, perguntado, escolheu o contrário (só tela), porque *"ficha de pessoal
  numa tabela por e-mail circula em caixa que ninguém controla"*. O uso mostrou
  o outro custo: **quem compra e separa uniforme não é usuário do painel**, e
  entrar no sistema para ver três medidas transforma recado em tarefa.
  Perguntado de novo (2026-08-08), escolheu a **planilha anexa** — anexo não
  fica indexado no histórico da caixa e dá para trabalhar em cima, e é UMA
  pessoa por e-mail, não o dump da base. **Não reverta isto de volta** achando
  que a regra da v2.07 continua valendo: ela foi revista com o caso de uso na
  mão. Só o que serve ao uniforme entra (nome, CPF, cargo, posto, 3 medidas) —
  banco, PIX e endereço estão a um `getattr` e ficam fora. Falha ao montar o
  anexo **não segura o aviso** (sai sem ele, com o link). O aviso continua
  disparando no `concluir_envio`, **nunca no autosave** — o wizard salva a cada
  900ms.
- **Textos de e-mail editáveis pelo RH** (v2.06, `services/email_templates.py`,
  `models/email_template.py`, Config → ✉️ Textos dos e-mails): o CATÁLOGO em
  `email_templates.py` é a fonte da verdade — quais e-mails existem, quais
  variáveis cada um oferece e quais são **obrigatórias**; a tabela guarda só o
  texto que o RH escreveu por cima. Quatro regras:
  (1) **O template é APRESENTAÇÃO, nunca decisão** — os e-mails que enumeram
  documentos/pendências recebem a lista PRONTA como `{{lista}}`, montada em
  Python; o RH edita o texto ao redor, a regra de o que entra continua no
  código. (2) **Variável obrigatória valida no salvamento** (422
  `variaveis_obrigatorias`): sem `{{codigo}}` num e-mail de acesso a mensagem
  sai bonita e vazia e ninguém mais entra no sistema — a variável do BOTÃO é
  exceção (chega pela URL do botão, não precisa estar no corpo). (3)
  **Fallback sempre**: sem registro, texto vazio ou erro de leitura vale o
  padrão do catálogo — e-mail nenhum deixa de sair por edição ruim. (4) **Nada
  de engine de template**: usa `fichas.aplicar_variaveis` (regex `{{chave}}`,
  `\w+`, sem dot-access) — o Jinja2 que a revisão pediu introduziria a
  superfície de injection que ele deveria proteger. Histórico append-only em
  `email_template_versao` (autor é SNAPSHOT string, não FK) com restaurar
  versão ou voltar ao padrão. Ao criar um e-mail novo: entrada no `CATALOGO` +
  `enviar_modelo(db, chave, destino, contexto)` no ponto de envio.
- **Teste de e-mail não pode depender da REDAÇÃO** (v2.06, armadilha achada no
  levantamento): o `smoke_test` extraía o OTP com
  `corpo.split("eletrônica é: ")` e o `test_email_reenvio_link` procurava
  `botao_url` no código-fonte. Com o texto editável pelo RH, uma edição no
  painel derrubaria o CI num commit sem relação nenhuma — e ninguém ligaria
  uma coisa à outra. Agora o smoke acha o código por PADRÃO
  (`re.search(r"(?<!\d)(\d{6})(?!\d)")`) e o teste renderiza o e-mail de
  verdade para conferir que o link chega. Regra: teste de e-mail afirma a
  GARANTIA (o link chegou, o código chegou), nunca a frase nem a implementação.
- **Escolha irreversível se confirma ANTES do botão, não dentro do card**
  (v2.05, feedback 2026-07-28 — "assinou com a opção errada"): a troca da opção
  de VT existia só dentro do card do `termo_vt`, no meio da lista de
  documentos; quem não reparasse assinava errado e aí é 409
  `termo_vt_ja_assinado`. Como o termo vira desconto de até 6% em folha, o erro
  custa salário. A confirmação agora fica logo acima de "Assinar os
  documentos" (mesmo lugar do bloco que confirma o e-mail), diz o efeito em
  dinheiro e avisa que depois não dá para trocar; o card só exibe o estado. A
  trava de PREENCHIMENTO já existia e não mudou (`ficha.py:480` +
  `declarar_veracidade` 422) — o problema nunca foi a obrigatoriedade, foi a
  pessoa não ver o que tinha respondido.
- **O candidato reabre o PRÓPRIO envio enquanto o RH não olhou** (v2.03,
  `documentos.py::reabrir_envio`): depois do "CONCLUÍ MEU ENVIO" o checklist
  congela (409 `envio_ja_concluido`) e antes só o RH reabria — quem percebia
  na hora que mandou o arquivo errado ficava travado dependendo de socorro.
  `POST /c/{token}/reabrir-envio` volta o status para `docs_pendentes`, com
  guarda: **qualquer** slot já revisado (aprovado/rejeitado/dispensado) recusa
  com 409 `rh_ja_revisou` — trocar arquivo já analisado faria a análise do RH
  valer para um documento que não existe mais. NÃO confundir com a reabertura
  cirúrgica pós-aprovação (essa é do RH e continua igual). Coberto por
  `tests/test_reabrir_envio.py` (validado por mutação).
- **Link de e-mail IDENTIFICA, nunca AUTENTICA** (v2.03, feedback 2026-07-28 —
  a regra que rege `/creche` e `/meu`): o gate 2FA morria no webview do app de
  e-mail. A pessoa abria o link, saía para LER o código (única forma) e voltava
  com a tela zerada — o backend guardava a sessão por 6h, mas o token vivia só
  em `useState`, e o front ainda apagava o `?t=` da URL. Agora o
  `AcessoCreche`/`AcessoPortal` nasce com token REAL no ENVIO do código (antes
  era um `token_hash` placeholder, inutilizável) e esse token vai no e-mail.
  Rotas `GET /creche/retomar/{token}` e `/portal/retomar/{token}` devolvem só
  primeiro nome + 4 últimos dígitos do CPF, e `pode_entrar` é true **apenas**
  para acesso emitido pelo RH (devolução, v1.82, nasce `confirmado_em` porque o
  e-mail já foi comprovado). Link de CÓDIGO nunca vira sessão sozinho — sessão
  expirada volta a pedir código; senão e-mail vazado = acesso. `confirmar`
  aceita `retomada=<token>` no lugar do CPF (quem voltou pelo link não
  redigitou). Limpar o `?t=` da URL só DEPOIS de resolvê-lo — apagar antes era
  o que impedia o "voltar" de recuperar a tentativa. Coberto por
  `tests/test_retomada_acesso.py` (validado por mutação).
- **Todo e-mail que MANDA a pessoa voltar ao sistema leva o link junto** (v2.02,
  feedback 2026-07-28): os e-mails de rejeição (`revisao.py::rejeitar` e
  `::rejeitar_lote`) diziam "acesse o mesmo link da sua admissão" e **não
  mandavam link nenhum** — a pessoa tinha que garimpar um e-mail de até 72h
  atrás e, se aquele já tinha expirado, ficava presa. Agora emitem
  `emitir_link()` novo (padrão que `rh_ficha.py:259/:435` já usava) e passam
  `botao_url` ao `html_moderno`. Duas armadilhas ao copiar esse padrão: a rota
  precisa receber `request` (o `base_url_publica` monta a URL pública), e
  candidato SEM e-mail deixa `link=None` — o corpo em texto puro precisa de ramo
  alternativo, senão sai "Acesse: None" (o HTML já se protege sozinho, o texto
  não). Coberto por `tests/test_email_reenvio_link.py`.
- **`catch` vazio anti-enumeração não pode engolir erro de INFRA** (v2.02, o
  defeito que escondeu os outros dois por semanas): `Entrar.jsx::pedirEmail`
  fazia `try { ... } catch {}` e mostrava "📬 Confira seu e-mail" **mesmo com
  HTTP 500** — sucesso mentiroso, a pessoa esperava um e-mail que nunca saiu e
  pedia de novo, em looping. A resposta idêntica para CPF que existe e que não
  existe continua CERTA (anti-enumeração), mas 5xx/rede tem que virar erro
  visível. É a MESMA lição da v2.00 (erro transitório ≠ permanente) numa
  terceira variação: **erro de negócio ≠ erro de infraestrutura**. Ao escrever
  `catch` silencioso, sempre pergunte qual falha ele está escondendo.
- **Reabertura CIRÚRGICA de documento pós-aprovação** (feedback 2026-07-24): um
  candidato `status=aprovado` pode reenviar SÓ um slot que o RH REJEITOU — nunca
  reabrir a ficha inteira nem mexer num slot já aprovado (isso desfaria dossiê/
  efetivação). O `status` fica INTACTO em `aprovado` (a rejeição em `revisao.py`
  já não mexe em aprovado — só `envio_concluido`→`docs_pendentes`). Três guards
  se sustentam: (1) `documentos.py::enviar_arquivo` E `enviar_identidade`
  recusam `409 apenas_documento_rejeitado` se `aprovado` e o slot não está
  `rejeitado` (o guard TEM que estar nas DUAS rotas — RG/CNH sobe pela
  identidade); (2) `concluir_envio` de um `aprovado` NÃO vira `envio_concluido`
  (retorna cedo, só avisa o RH que houve reenvio); (3) o gate de EDIÇÃO da ficha
  (`ficha.py::_candidato_do_token`) continua barrando `aprovado` com
  `admissao_encerrada` — o de `documentos.py` é aberto de propósito (o checklist
  serve o aprovado). Fluxo real do RH: reabrir o slot aprovado (`/rh/slots/{id}/
  reabrir` → volta a `enviado`) e então rejeitar. Front (`CandidatoApp.jsx`): no
  `admissao_encerrada`, se `api.documentos` tiver slot `rejeitado`, roteia para o
  checklist. Coberto pelo smoke (etapa 14b, os três riscos).
- **Emergência editável pelo RH** (feedback 2026-07-24): o candidato preenche a
  emergência no wizard, mas o RH também vê/corrige em `Detalhe.jsx`
  (`SECOES_FICHA['vt-emergencia']` lista os 5 campos + exibe os contatos; o
  backend `rh_ficha.py::editar_secao` já separava vt_/emergência). Campos
  booleanos (`vt_optante`, `usa_medicamento_continuo`) são `<select>`, NUNCA
  `<input>` texto — digitar "sim" num input gravaria `false` calado (dado médico).
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
  referenciar nas colunas com `create_type=False` (senão DuplicateObject). **Use
  `postgresql.ENUM(..., create_type=False)` do dialeto — não `sa.Enum(...,
  create_type=False)` genérico** (v1.98, mordeu de verdade): o `sa.Enum`
  genérico não respeita a flag ao criar a tabela na mesma migration —
  `op.create_table` dispara `CREATE TYPE` de novo via evento DDL mesmo com
  `create_type=False` no construtor, e o `.create(checkfirst=True)` explícito
  anterior já tinha criado, dando `DuplicateObject`. Sintoma enganoso: o erro
  diz "type already exists" mesmo quando `\dT+` no banco mostra que não existe
  — é a MESMA migration tentando criar duas vezes (uma explícita, uma via
  DDL da tabela), não um resíduo de execução anterior. Ver
  `migrations/versions/a9d3f6b18c42_talento.py` (funciona) vs. o que quebrou em
  `c4d5e6f7a8b9_minutario.py` antes da correção.
- **Revision id de migration**: NÃO escolher o "próximo da sequência" de olho —
  vários ids do projeto seguem o padrão `a1b2c3…`/`b2c3d4…` e reusar um que já
  existe fecha um CICLO no grafo (`Cycle is detected in revisions`), derrubando
  o `alembic upgrade` inteiro — inclusive o do entrypoint em PRODUÇÃO. Conferir
  com `grep -rn 'revision = ' migrations/versions/` antes de gravar.
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

- **Sistema de design (FONTE CANÔNICA):**
  `docs/planejamento/08-sistema-de-design.md` — regras de padronização e
  identidade (o Bruno cansou de padronizar tela a tela). Tela nova NASCE
  padronizada: renderiza dentro de `.pagina`/`.rh-painel` (o respiro vem da
  primitiva, não do módulo — `<section>` cru cola na borda); ZERO `style` inline
  de espaçamento/cor (use os tokens `--esp-*`, `--fs-*`, cores semânticas);
  editar/criar abre PERTO do item (nunca no topo); nada estoura a tela (tabela em
  `.dash-scroll`, texto longo em `.dash-quebra`); tudo que abre, fecha (toggle);
  testar no tema ESCURO (o `color-scheme` no `:root`/`[data-tema='escuro']`
  conserta o dropdown nativo do `<select>` — NÃO estilizar `<option>` à mão);
  termos de negócio com `<Ajuda>`. Ao mudar um padrão, atualizar o DOC e este
  CLAUDE.md. Checklist completo no doc.
- Idioma: TUDO em pt-BR (código, comentários, commits, UI).
- Commits direto no `main`: `feat(vX.Y): resumo` + corpo com bullets; uma
  versão por "onda" entregue. Push e acompanhar o CI (`gh run list/view`) —
  único workflow `ci.yml` (imagens api/frontend + testes de interface).
- **REGRA: toda leva atualiza CHANGELOG, README e os demais documentos —
  no MESMO commit** (cravada pelo Bruno em 2026-07-29). Não é burocracia: em
  2026-07-29 o CHANGELOG estava 20 versões atrás (parado na v2.01) e o README
  parado na v1.85, sem Match de Vagas, Minutário, Provas, textos de e-mail,
  catálogo de documentos, Uniformes nem mini-CRM — módulos inteiros que o
  sistema tinha e que documento nenhum registrava. Sistema completo sem
  histórico é sistema que ninguém além de quem o escreveu consegue operar ou
  auditar. Checklist ao fechar uma versão: (1) entrada no `CHANGELOG.md` com o
  PORQUÊ, não só o quê — as decisões e o que foi medido; (2) `README.md`
  refletindo o que existe hoje; (3) `CLAUDE.md` com a armadilha nova, se
  houver; (4) doc específico (`docs/planejamento/`) quando a leva mexe em
  padrão.
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
