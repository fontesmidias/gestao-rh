# Changelog

Formato: [Keep a Changelog](https://keepachangelog.com/pt-BR/) · versionamento semântico.

Rollback: toda migration tem `downgrade()` escrito para não destruir dados —
`alembic downgrade -1` volta uma revisão; o código volta apontando a stack para a
tag anterior da imagem no GHCR. Faça `pg_dump` antes de qualquer downgrade.

> **Sobre "legado"**: valores de enum e campos que deixaram de ser usados **não
> são removidos** — o Postgres não apaga valor de enum sem recriar o tipo, e
> apagar coluna destruiria histórico. Eles ficam órfãos (não se escreve mais),
> com o motivo registrado abaixo e no `CLAUDE.md`. NÃO usar em código novo.

## [3.08.0] — 2026-08-19 — O botão que ninguém achava

Feedback do Bruno (18/08/2026): *"na etapa de assinar, apesar dela ver os dados
das fichas, ela não consegue editar, e o RH tem que editar manualmente"*. O
diagnóstico não era o que o relato sugeria — e ele não sabia em qual caminho a
pessoa estava (foi relato de terceiro), então os DOIS foram tratados.

### O que o código dizia

O backend **nunca** bloqueou: `_candidato_do_token` só barra `expurgado` e
`aprovado`. E o botão *"← Preciso corrigir meus dados antes de assinar"* existe
desde a v2.88. Mapeados os dois caminhos que levam a esta tela:

1. **Primeira assinatura** — o botão está lá, mas como `btn-link`: texto
   discreto, cinza, embaixo de um botão verde grande. Quem não o vê conclui que
   não dá para corrigir e chama o RH. **Botão que existe e não é achado não está
   entregue** (v2.75).
2. **Reassinatura** — o botão é escondido de propósito, e com razão: os dois
   caminhos que reabrem documento são ações do RH (editar a ficha, ou trocar
   posto/cargo/salário em `postos.py`), e a ficha de admissão está fechada. Mas
   ali não havia **nada** dizendo o que fazer: quem visse um dado errado assinava
   mesmo assim ou parava sem saber a quem recorrer.

### Corrigido

- O botão virou **`btn-secundario`** e ganhou ícone — continua abaixo do
  principal (um `btn-principal` por tela: o ato que FECHA o trabalho é assinar),
  mas agora se vê.
- Na reassinatura, a tela **diz a saída que existe**: não assine, fale com o RH,
  porque estes documentos foram atualizados por eles. É a regra da v2.87 —
  recusa (ou ausência de caminho) sempre oferece a alternativa no mesmo lugar.

## [3.07.0] — 2026-08-19 — O creche onde o RH já está olhando

*"Página de colaboradores, de admissão e demais páginas: conter as informações
também de benefício creche"* (Bruno, 18/08/2026). Antes, saber se alguém tinha o
benefício exigia abrir a tela do Creche e procurar — duas telas para uma
pergunta.

### Adicionado

- **Coluna "Creche" em Colaboradores**: ativo, em análise, ou **⚠️ falta N** —
  quantas crianças estão sem o comprovante do mês. Filtrável, e com um card
  clicável que aparece **só quando há pendência**: card fixo custaria altura de
  cabeçalho para dizer "0", e 8 cards em 2 colunas viram 4 fileiras no celular
  (a régua já reprovou esta tela uma vez, v2.85.1).
- **Coluna "Creche" em Admissões**, respondendo outra pergunta — ali o benefício
  ainda não existe. O que importa é *"o posto dá direito e a pessoa já informou
  criança no wizard?"*: quem vai para posto elegível sem ter informado nada é
  quem o RH precisa procurar **antes de efetivar**.

### Medido

- **3 consultas fixas** em Colaboradores e **3** em Admissões, não uma por
  pessoa — a lista tem 1.156 colaboradores, e o N+1 do dash de Talentos (v2.15)
  já custou 43 consultas para 39 registros. Conferido lendo o código: os laços
  finais só percorrem dicionários em memória.

## [3.06.0] — 2026-08-19 — O currículo virou obrigatório

Decisão do Bruno (18/08/2026), nos DOIS cadastros. Reverte conscientemente a
escolha de "máxima conversão" da v1.55, que tinha deixado só nome + aceite LGPD
como obrigatórios.

### Alterado

- **Formulário público**: o currículo passou a ser exigido para concluir, e o
  aviso aparece já no **PRIMEIRO passo** — quem descobre a exigência no fim já
  investiu o preenchimento inteiro e desiste ali. Aceita arquivo ou **foto das
  páginas**, que é o caso de quem preenche pelo celular.
- **Cadastro pelo RH**: obrigatório **com justificativa** — o RH cadastra por
  indicação ou telefone, antes de o arquivo existir, e travar isso pararia o
  trabalho por um documento que chega depois. O motivo vai para a auditoria
  **e para o mini-CRM**, que é onde o RH de fato olha: só na auditoria,
  *"por que esta pessoa não tem currículo?"* exigiria abrir a auditoria, e
  ninguém abre.

### Corrigido

- **"Cadastro recebido!" aparecia mesmo quando o currículo não subia.** O
  arquivo vai numa SEGUNDA chamada; se ela falhava, o `catch` só anotava na
  telemetria e a tela dizia sucesso — a pessoa ia embora achando que estava tudo
  certo. Agora há um terceiro estado: o cadastro fica (perder o contato de quem
  se interessou seria pior que um cadastro sem currículo), mas a tela **diz que
  faltou** e oferece tentar de novo. É o sucesso mentiroso da v2.02, no mesmo
  formulário.
  ⚠️ O botão "tentar de novo" só é seguro por causa da v3.05.0: sem a dedup da
  porta pública, reenviar criaria um segundo cadastro.

### Onde a exigência NÃO mora

Na rota de cadastro. O arquivo sobe depois de o registro existir — exigi-lo ali
seria exigir algo que ainda não chegou. Quem cobra é a tela; o backend garante
o registro da exceção.

## [3.05.0] — 2026-08-19 — Uma pessoa, um cadastro

*"Pensar em uma hipótese da pessoa se cadastrar apenas uma vez"* (Bruno,
18/08/2026). A causa apurada não era a que o pedido sugeria: o cadastro pelo RH
tinha dedup desde a v2.73 e a importação de planilha também — **a porta PÚBLICA
não tinha nenhuma**. A mesma pessoa preenchendo duas vezes criava dois
registros, e nada acusava.

### Adicionado

- **Dedup no cadastro público**, com a MESMA regra das outras duas portas
  (e-mail; ou nome + telefone quando não há e-mail), agora numa função só —
  três portas para o mesmo Banco de Talentos não podem discordar sobre o que é
  a mesma pessoa.
- ⚠️ **Aqui NÃO se responde "já existe", como a porta do RH faz.** Esta rota é
  pública: dizer *"já existe: Maria, maria@x.com"* a transformaria numa sonda
  para descobrir quem está no banco digitando e-mails alheios. O padrão da casa
  para porta pública é **resposta idêntica** (anti-enumeração, como o gate do
  creche e do portal), então o recadastro ATUALIZA em silêncio: é o que a pessoa
  quer, e não revela nada a quem sonda.
- **Campo vazio no reenvio não apaga o que havia**: quem se recadastra costuma
  preencher só o essencial, e perder o telefone que o RH já tinha por causa de
  um formulário mais curto seria perder dado sem ninguém pedir.
- **Arquivado volta para a fila** (decisão do Bruno): quem se candidata de novo
  pode ter mudado, e a decisão de descartar se toma outra vez com o dado atual.
  O motivo do descarte anterior sobrevive — ele vive como anotação append-only
  no mini-CRM (v2.14), então o RH reavalia sabendo por que tinha recusado.
  **`convertido` não é rebaixado**: rebaixar tiraria da fila de admissão alguém
  que está sendo admitido, e o sintoma seria a pessoa sumir da tela.

### Medido

- `test_talento_recadastro` no CI, com 6 blocos — inclusive a asserção de que a
  resposta do recadastro não contém nenhuma pista (`existe`, `duplicad`…) que
  permita distinguir "já havia" de "acabei de criar".

## [3.04.0] — 2026-08-19 — Um nome só para tudo que se baixa

Padrão de nome de arquivo `MATRÍCULA - NOME - DOCUMENTO`, caixa alta e sem
caractere especial, como o Bruno pediu — *"como regra para os módulos existentes
e os vindouros"*. É a continuação do pedido de 12/08, que resolveu UM documento
(o dossiê): havia **quatro funções de nomeação diferentes** e 31 pontos montando
nome à mão.

### Adicionado

- **`services/nome_arquivo.py`**, um lugar só. Caixa alta e ASCII não são
  estética: o header `Content-Disposition` só carrega ASCII com segurança, e a
  pasta física do RH é toda em caixa alta. Parte VAZIA é omitida junto com o
  separador — em admissão a matrícula quase sempre não existe, e
  ` - MARIA - FICHA.pdf` tem um hífen órfão que todo mundo lê como erro.
- **O `BotaoBaixar` agora LÊ o `Content-Disposition`** da resposta e o prefere
  ao nome passado no JSX. Assim o padrão vale sozinho, sem depender de cada tela
  repetir o nome certo — que é exatamente como as quatro nomeações divergiram.
- **Documento individual do Arquivo sai identificado**: antes era só
  `termo-vt.pdf`, e quem baixasse o mesmo documento de três pessoas ficava com
  três arquivos indistinguíveis na pasta.

### Corrigido

- **Dois testes novos estavam no bloco errado do CI.** `test_matricula` e
  `test_nome_arquivo` exercitam funções de TEXTO, mas elas moram em
  `export_tirvu.py`, que importa SQLAlchemy — e o bloco "stdlib pura" do CI não
  instala nada. Passavam na máquina de quem escreve (que tem o venv) e
  reprovavam no CI com `ModuleNotFoundError`. Movidos para o bloco que roda
  dentro do container, e o motivo ficou escrito no `ci.yml`. **Antes de pôr
  teste no bloco stdlib, confira o que o MÓDULO importa, não só o teste** —
  verificado rodando com o Python sem venv, que é a condição real de lá.

### Medido

- `test_nome_arquivo` validado por 2 mutações: separador solto quando falta a
  matrícula (reprova em 3 asserções) e remoção da limpeza de caracteres
  (reprova em 4, inclusive a das aspas, que quebrariam o header).

## [3.03.0] — 2026-08-19 — Seis dígitos, sem invadir o vizinho

Matrícula automática de **6 dígitos** (`99`+4), como o Bruno pediu para o padrão
de nome de arquivo. **Só para as próximas**: quem já tem a antiga (`999`+4, 7
dígitos) fica como está — aquele número já foi para o Tirvu e para a planilha de
ponto, e trocá-lo criaria duas matrículas para a mesma pessoa nos dois sistemas.

### Adicionado

- **Faixa nova `99NNNN`** e `matricula_formatada()` (zero-pad até 6 para EXIBIR
  e NOMEAR, sem tocar no gravado). Zero-pad é seguro: `matricula_norm` já ignora
  zeros à esquerda, então `003035` continua casando com `3035` na planilha de
  ponto — é isso que autoriza o padrão de nome sem quebrar a frequência.
- **Matrícula em Admissões** (era a única das três telas sem ela) e **no
  requerimento do creche**, que identificava a pessoa só por nome + CPF — e é a
  matrícula que o DP usa para casar com a folha. Sai só quando EXISTE: imprimir
  "Matrícula: -" num documento assinado sugere dado faltando, quando em geral
  ela ainda nem foi gerada.

### Corrigido

- **`999001` era lida como matrícula NOSSA.** Tem 6 dígitos e começa com `99`,
  então a leitura ingênua a tomaria por `99`+`9001` — e o gerador pularia para
  `999002`, **invadindo a numeração do Tirvu**, onde pode haver outra pessoa. A
  faixa nova agora exige que o dígito após o prefixo não seja `9`. Custo: a
  faixa vai até `998999` (~9.000 matrículas, folgado para ~1.200 pessoas); o
  ganho é não colidir com número de gente real.
- **O gerador considera as DUAS faixas** ao escolher o próximo número: `9990007`
  e `990007` compartilham o sequencial, e ignorar a legada faria a primeira
  matrícula nova repetir um número já usado (medido: geraria `990001` numa base
  que já tinha o sequencial 7).
- **`_indicio_tirvu` só reconhecia `999`**: o aviso de "esta pessoa já está no
  Tirvu" sumiria para todo mundo admitido a partir de agora — justamente os mais
  recentes.

### Medido

- `test_matricula` no CI, validado por mutação: remover o guard da ambiguidade
  reprova nomeando o caso `999001`.

## [3.02.0] — 2026-08-19 — A porta do mês

O ciclo MENSAL do reembolso-creche: a estrutura que faltava para receber o
comprovante que o e-mail de ativação já mandava enviar todo mês. Regras do
Jurídico (e-mail do Dr. Lucas, 18/08/2026): um comprovante por filho e por mês —
nota fiscal se a creche for PJ, declaração de quitação se o cuidador for PF —,
com corte no dia 25 e pagamento até o 5º dia útil do mês seguinte.

### Adicionado

- **`CompetenciaCreche`**: o comprovante de UMA criança em UM mês, com
  `UniqueConstraint(crianca, ano, mes)` — dois registros do mesmo mês fariam a
  soma da folha dobrar sem nada denunciar. Reenvio SUBSTITUI, com hash na
  auditoria do que saiu.
- **As duas portas de envio pela MESMA função** (`creche_envio.receber`):
  colaborador pelo link e **RH pelo painel** — antes o RH era somente-leitura
  sobre documento de creche, e faltando um o único caminho era devolver o
  levantamento inteiro e esperar.
- **Multi-folhas**: 1..N folhas viram um PDF, com os originais numerados com
  zero à esquerda (sem isso a listagem lexicográfica põe `10-` antes de `2-` e a
  folha sai fora de ordem — v2.35). Era a causa do *"não consigo ver se há mais
  de uma folha"*: não havia.
- **Lembrete configurável** (`workers/creche_lembretes.py`, padrão 5/2/1 dia
  antes), nos DOIS arquivos de deploy (v2.66). Chave de config AUSENTE cai no
  padrão; chave VAZIA desliga — tratar as duas igual impediria o RH de desligar.
- **Vigência por posto** (`creche_vigente_desde`): o aditivo de cada contrato
  tem data, e o direito era um booleano sem ela. Competência anterior à vigência
  é MARCADA para o RH decidir, **não recusada** — e vigência que já cobre o mês
  não marca, porque alarme falso ensina a ignorar o alarme (v2.91).
- **Tela das credenciais de automação**: as rotas existiam desde a v2.94 e nunca
  houve tela — criar um token exigia `docker exec`.
- **Criar jornada pela tela**: a rota e o `api.criarJornada` existiam desde
  sempre e nenhuma tela os chamava; o texto de lista vazia já dizia "crie
  manualmente" sem haver por onde.

- **As telas dos dois lados.** No link do colaborador, o comprovante do mês
  aparece só com o benefício ATIVO, com a câmera guiada da admissão (moldura,
  aviso de foto tremida, várias folhas) e o prazo como CONTAGEM — *"faltam 2
  dias"* move; *"dia 25"* obriga a fazer a conta. No painel do RH, a ficha do
  benefício ganhou a tabela dos comprovantes com **valor comprovado E valor a
  reembolsar** lado a lado (são números diferentes quando a despesa passa do
  teto, e mostrar só um esconderia de qual se fala no lugar que decide
  pagamento), a contagem de FOLHAS, a marca de retroativo e o botão de
  **anexar** — que o RH não tinha.

### Corrigido

- **`except` que "salva o original" gravava um PNG como se fosse PDF.** Quando a
  normalização recusa a foto por qualidade, o caminho de escape guardava os
  bytes crus e os mandava ao `combinar_pdfs` — `PdfStreamError`, e o envio
  inteiro caía com 500. O escape agora CONVERTE (reusando só o trecho pós-
  validação, porque `_imagem_para_pdf` reaplica as mesmas checagens que já
  recusaram) e confere que o resultado começa com `%PDF`: devolver bytes vazios
  passava pelo `is None` do chamador e estourava adiante. Folha que não vira PDF
  é PULADA e NOMEADA na auditoria; se NENHUMA virar, recusa com 422 — melhor que
  gravar zero página com o registro afirmando que está entregue (v2.93).
  **Pego pelo CI**, não em produção, porque o teste usa
  `raise_server_exceptions=False` (v2.72.2): sem isso o 500 mataria o script e a
  saída vazia passaria por sucesso.

### Medido

- 3 mutações no `test_creche_competencia`, todas reprovadas: teto virando valor
  fixo, valor ilegível virando zero e a virada de ano no vencimento.

## [3.01.0] — 2026-08-18 — A porta que a tela prometia

23ª leva de feedbacks (13 itens, a maioria do Reembolso-Creche). Esta versão
entrega o levantamento, as decisões e os dois itens que não dependiam de
ninguém; o ciclo mensal do creche vem na sequência.

### Descoberto

- **O e-mail de ativação do creche promete uma entrega mensal que o sistema não
  tem onde receber.** O texto manda enviar nota fiscal ou declaração todo mês —
  e o módulo tem **21 rotas POST, nenhuma** que aceite comprovante mensal (o
  único upload recusa o que não for certidão ou guarda). Não há tabela de
  competência, worker de lembrete nem data de corte. O `dia_entrega_mensal`
  existe, é editável em massa e é **dado morto**: só preenche uma variável de um
  e-mail enviado UMA vez, por uma função chamada `_email_orientacoes_mensais` —
  nome que engana quem lê. É a armadilha da v2.74 (*promessa na tela sem rota
  atrás*) na maior escala vista aqui, num benefício que entra em folha.
- **Pior**: aquele e-mail diz *"até o dia {{dia}}"* com o default **5**, e o
  Jurídico define corte no dia **25**. Quem foi ativado recebeu a data errada,
  junto de *"sem a comprovação no prazo, o reembolso pode não ser efetuado"*.
- Cinco feedbacks já estavam prontos ou quase: a coleta de creche na admissão
  **já existe** no wizard; o `tipo_comprovante` (PF/PJ) **já existe** no modelo e
  é coletado, sem nenhuma tela do RH mostrá-lo; a padronização de nomes é a
  **continuação** do pedido de 12/08.

### Adicionado

- **Criar jornada pela tela** (`JornadasRH.jsx`). A rota `POST /rh/jornadas` e o
  `api.criarJornada` existiam **desde sempre** e nenhuma tela os chamava — o
  texto de lista vazia já dizia *"crie manualmente"* sem haver por onde. Rota
  sem tela é o espelho da promessa sem rota. ⚠️ A rota é **idempotente por
  descrição**: se a jornada já existe ela devolve a existente com 201, então a
  tela distingue "criada" de "já existia" — sem isso o RH procuraria uma
  duplicata que não foi criada.
- **Vigência do reembolso-creche por posto** (`creche_vigente_desde`, migration
  `a3f7c1e9d5b2`): o aditivo de cada contrato tem data (ANEEL desde 01/05/2026;
  INEP 03/2026 e 37/2025 e MAPA 58/2024 desde 01/08; PREPÚBLICA desde 01/02), e
  o direito era um booleano **sem data** — o sistema não respondia *"esta pessoa
  tinha direito em maio?"*, que é o que auditoria e retroativo perguntam.
  Editável individualmente e **em massa** (um contrato tem vários postos e a
  data do aditivo é a mesma para todos). `NULL` = não informada: não se assume
  nem "desde sempre" nem "nunca" — adivinhar decide dinheiro no contracheque.

- **Tela das credenciais de automação** (Configurações → 🔌 Integrações). As
  rotas existiam **desde a v2.94** e nunca houve tela: criar um token exigia
  `docker exec` no container, o que na prática significa que o recurso não
  existia para quem opera — é o espelho do "tela que existe mas ninguém acha"
  (v2.75), com a tela ausente em vez de escondida. Três coisas que ela faz
  porque o desenho da credencial depende delas: **avisa ANTES de emitir** que o
  segredo aparece uma única vez (quem descobre depois o guarda "por garantia"
  noutro lugar, que é justamente o que gravar só o `sha256` evita); mostra
  **prefixo e último uso**, o que responde *"qual eu revogo?"* e *"este ainda
  está em uso?"* sem revelar segredo; e diz que **revogar marca e não apaga**.
  Só usuários **ativos** aparecem na lista — a rota recusa inativo com 422, e
  oferecê-los seria convidar ao erro.

### Documentado

- `docs/planejamento/15-feedbacks-23a-leva.md` — levantamento, as 13 decisões do
  Bruno, o plano por prioridade e a ideia **descartada** (um módulo genérico de
  "competência mensal") com o motivo, para não voltar por engano.
- `docs/planejamento/16-expertises-reusaveis.md` — **catálogo de peças
  reutilizáveis**, a pedido do Bruno (*"cada vez que criarmos uma expertise,
  vamos colocá-la de modo que podemos utilizá-la em módulos existentes e
  futuros"*). O reuso já era praticado sem registro, e isso custa: a v2.94 ia
  criar seis rotas de diagnóstico e **quatro já existiam**. Inclui a lista de
  peças **subutilizadas** — genéricas, com um consumidor só — e a lição
  estrutural: `BotaoBaixar` e `PlayerAudio` moram em `rh/` e têm 2 usos, enquanto
  `VisualizadorArquivo`, que resolve problema equivalente e está na raiz, tem 5.
  **Se o contrato não menciona o domínio, o arquivo não deveria morar nele.**

## [3.00.6] — 2026-08-13 — O guarda-corpo que não alcançava o fundo

Segundo `ModuleNotFoundError` no mesmo lugar, agora com `matplotlib`. A
mensagem da v3.00.5 fez o trabalho dela — nomeou o módulo e disse que não era o
token —, mas a defesa que deveria ter pego isso no CI **falhou por profundidade**.

### Corrigido

- **Faltava `matplotlib`.** Mesma causa do `torchvision`: o `pyannote.audio` o
  importa e não o declara como dependência.
- **O guarda-corpo do build era raso.** Ele importava a fachada
  `pyannote.audio.Pipeline`, e a exigência de `matplotlib` mora um nível abaixo,
  em `pyannote.audio.pipelines` — que só carrega quando o pipeline é montado de
  verdade. O build passou verde, a imagem subiu, e o erro apareceu na ficha de
  uma entrevista real. Agora o build importa **na mesma profundidade que o uso**
  (`SpeakerDiarization`, `AgglomerativeClustering` e
  `PretrainedSpeakerEmbedding`) — inclusive o caminho que só roda com token
  VÁLIDO, onde um módulo faltando apareceria depois de tudo parecer certo.

  A lição vale além daqui: **verificação de import só prova o que ela carrega**.
  Importar o pacote de cima passa a impressão de cobertura sem tê-la — é a
  família do "teste que não executa a linha mutada" (v2.67), aplicada a
  dependência.

### Medido

- Carregar o `medium` do disco: **138 s na primeira vez, 63 s com o cache do
  sistema quente**. Sem o cache em memória da v3.00.5, uma entrevista de 4
  blocos jogaria fora ~4 minutos só recarregando o mesmo modelo.
- A imagem ficou em **2,17 GB**, com o `medium` (1,5 GB) embutido — confirmado
  rodando `WhisperModel("medium")` dentro dela **sem baixar nada**.
- O aviso que o próprio `pyannote` imprime ao importar confirma o pino da
  v3.00.4: *"list_audio_backends has been deprecated… It will be removed from
  the 2.9 release"*.

### Interno

- `test_diarizacao_diagnostico.py` cresceu para 10 mutações.

## [3.00.5] — 2026-08-13 — A transcrição fica melhor, e a biblioteca que faltava entra

Duas coisas na mesma leva: a qualidade que o Bruno pediu (*"vamos de medium"*) e
a continuação do defeito da v3.00.4 — o erro tinha mudado de `AttributeError`
para `ModuleNotFoundError`, com o teste de token respondendo **200 nos dois
modelos**. A credencial estava certa desde o começo.

### Corrigido

- **Faltava `torchvision` no container.** O `pyannote.audio` o IMPORTA e não o
  declara como dependência, então o pip nunca o instalava e a diarização morria
  no import. Entra cravado (`0.23.0`, que casa com o torch 2.8).
- **Os pinos da v3.00.4 não estavam valendo.** O `pip install` do `pyannote`
  rodava DEPOIS, numa chamada separada, e reabria as faixas que a v3.00.4 tinha
  fechado — o log do build mostra `torch-2.13.0` e `huggingface-hub-1.27.0`
  entrando por cima. Agora tudo numa resolução só: conflito vira **erro de
  build**, e não imagem quebrada em produção.
- **O build agora IMPORTA o que a diarização usa.** Módulo faltando reprova no
  CI, em vez de virar erro na ficha de uma entrevista real.
- **`ModuleNotFoundError` virou caso próprio, e a mensagem NOMEIA o módulo.**
  Antes caía no texto genérico e mandava conferir token e licença — pela segunda
  vez, depois de o teste já ter aprovado os dois.

### Novo

- **A qualidade da transcrição virou escolha, e o padrão subiu para `medium`**
  (decisão do Bruno). Na entrevista real, o `small` escreveu *"Daxon"* por
  Dexion, *"ex-social"* por eSocial e *"gorrigo"* por currículo — o texto vira
  justificativa de avaliação, e nome errado ali é pior que espera maior. Três
  opções em Configurações → Gravação de entrevistas, cada uma dizendo o custo em
  tempo: `small` (~0,6× o áudio), `medium` (~1,5×) e `large-v3` (~3×).
  ⚠️ **Só o catálogo entra** (422 `modelo_desconhecido`): nome livre viraria
  download no Hugging Face dentro do worker, e a falha apareceria minutos
  depois, em segundo plano, sem nada na tela ligando uma coisa à outra.
- **A imagem pré-baixa o modelo padrão.** Sem isso, a primeira transcrição
  depois de cada deploy baixaria ~1,5 GB antes de começar — e quem espera é o
  RH, com a entrevista encerrada, sem nada dizendo que o atraso é download. O
  nome vem do `MODELO_PADRAO` do serviço, lido no build: duas listas
  divergiriam em silêncio, e o sintoma seria justamente esse download.
- A tela avisa que trocar o modelo **vale só para o que for transcrito daqui em
  diante**, e aponta o ↻ Refazer para aproveitar a qualidade nova no que já
  existe.

- **O modelo passou a ser guardado entre blocos.** Cada `WhisperModel(...)` relê
  o modelo do disco, e uma entrevista de 40 min vira ~4 blocos: com o `small`
  isso custava segundos, com o `medium` custaria dezenas deles por trecho. O
  worker RQ é processo de vida longa, então o cache vale para todas as tarefas
  que ele atender — guardado **por nome**, para que trocar o modelo no painel
  passe a valer sem reiniciar o container, e só o último, porque manter dois
  somaria os dois tamanhos na memória.
- A tela avisa que o `large-v3` usa ~3 GB enquanto transcreve: o container não
  tem limite de memória declarado, e numa VPS apertada ele disputaria memória
  com o banco — o sintoma seria o Postgres caindo durante uma transcrição,
  longe da causa. Aviso, nunca bloqueio: quem conhece a máquina decide.

### Interno

- A chave `transcricao_modelo` era lida pelo worker desde a v2.97 e **não tinha
  rota nem tela** — só era configurável escrevendo no banco (a armadilha da
  v2.68). Agora tem as três pontas.
- `test_diarizacao_diagnostico.py` cresceu para 9 mutações.

## [3.00.4] — 2026-08-13 — O erro que mandava conferir a coisa certa

Defeito de campo. A ficha da entrevista mostrou *"Não foi possível separar quem
falou (AttributeError). […] Confira o token do Hugging Face e se a licença do
modelo foi aceita"* — e **o token estava correto**. A mensagem mandava conferir
a coisa errada, que é o defeito mais caro do gênero neste projeto (v2.93: a
analista tomou o erro 8× em 70 minutos e desmarcou três exigências médicas por
diagnóstico errado).

### Corrigido

- **As versões do container de transcrição estavam com faixa ABERTA.** O
  `pyannote.audio` 3.x declara as dependências sem teto, e duas tiveram remoção
  destrutiva em out/2025: `torchaudio` 2.9 removeu `AudioMetaData` e o
  `huggingface_hub` 1.0 removeu `use_auth_token`. Com a faixa aberta, o pip pega
  a mais nova e a diarização quebra **no import do módulo**, antes de tocar no
  áudio — sem ninguém ter mexido em nada. Agora `torch`/`torchaudio` 2.8.0,
  `pyannote.audio` 3.3.2 e `huggingface_hub<1.0`, cravados.
- **`Pipeline.from_pretrained` devolve `None` — sem levantar — quando o acesso
  ao modelo é negado.** O erro só aparecia na linha SEGUINTE, como
  `AttributeError: 'NoneType'`, a um passo da causa e com cara de biblioteca
  quebrada. Agora a recusa é detectada onde nasce e diz o que resolve.
- **São DUAS licenças, e o teste de token conferia UMA.** O
  `speaker-diarization-3.1` usa o `segmentation-3.0` por baixo; faltando a
  segunda, o teste respondia "vai funcionar" e a falha aparecia depois, numa
  entrevista de 40 minutos. O teste agora percorre os dois e diz **qual** falta.
  Trata `404` como licença faltando: o Hub esconde modelo gated de quem não tem
  acesso, e ler isso como "não existe" mandaria procurar defeito onde não há.
- **A mensagem distingue as três causas**, porque as ações são diferentes:
  incompatibilidade de versão (que ninguém do RH resolve trocando token, e a
  tela agora diz isso), licença não aceita, token inválido.
- **O `print()` do pyannote virou log.** Ele explica a recusa por stdout, não
  por exceção — e a linha sumia justamente do lugar onde alguém vai procurar.

### Interno

- `test_diarizacao_diagnostico.py` (estrutural, no CI), validado por **4
  mutações**: reabrir a faixa de versões, remover a checagem de `None`, desligar
  a distinção de causa e conferir uma licença só. ⚠️ A terceira mutação **passou
  verde na primeira versão do teste** — ele procurava o TEXTO da mensagem, que
  continuava escrito no arquivo mesmo com o `if` desligado. A asserção passou a
  ler a árvore e exigir que a variável realmente DECIDA a mensagem. É a família
  do "teste que não executa a linha mutada" (v2.67).

## [3.00.3] — 2026-08-13 — As entrevistas antigas também ganham os interlocutores

Pedido do Bruno logo depois que a separação de vozes entrou no ar: *"os
antigos, queria utilizar já esse novo padrão com o hugging face"*. As
entrevistas transcritas antes da v3.00 saíram como texto corrido — e o áudio
delas continua guardado, então dá para refazer sem regravar nada.

Ao abrir a ficha para fazer isso, apareceram **dois defeitos que não davam erro
nenhum**:

### Corrigido

- **A rota de refazer exigia `g.audio_key` — campo que só o envio de ARQUIVO
  ÚNICO preenche.** Quem gravou pelo navegador (o caminho normal desde a v2.98)
  guarda o áudio em blocos, então recebia `404 sem_audio` **com a entrevista
  inteira guardada ao lado**. É a família do "a informação já existia, no lugar
  errado" (v2.95): o áudio estava lá; a rota olhava para o campo errado. Agora
  ela consulta os blocos e reenfileira **um por trecho** — o mesmo caminho do
  envio normal, para que um bloco ruim não derrube os outros oitenta minutos.
- **A rota exigia falha.** Aceitando só `falhou`/`audio_inaudivel`, ficava sem
  saída justamente o caso do pedido: transcrição **pronta** é o estado normal de
  quem quer o padrão novo.
- **`tem_audio` ignorava os blocos**, então a tela diria "sem áudio" para toda
  gravação feita pelo navegador.
- **A recusa passou a dizer o que houve.** Sem bloco e sem áudio único, a
  resposta explica que o áudio pode ter expirado pela retenção e que a
  transcrição atual permanece — recusa que não explica faz consertar a coisa
  errada (v2.93).

### Novo

- **Botão "↻ Refazer separando quem falou"** na ficha da entrevista, e ele
  **só aparece quando faz diferença**: há áudio guardado, a separação está
  ligada e o texto ainda é corrido. Oferecer sempre custaria ~1,7× a duração do
  áudio para devolver exatamente o mesmo texto. A tela diz quanto demora e que
  o texto atual só é substituído quando o novo fica pronto.

### Interno

- `diarizar` passou a sair do `config()` do serviço. Era lido também na rota de
  configuração — duas leituras da mesma chave divergem na primeira mudança de
  regra.
- `test_retranscrever.py` (estrutural, no CI), validado por **4 mutações**:
  exigir `audio_key`, enfileirar uma tarefa só, oferecer o botão sempre e
  `tem_audio` sem os blocos.

## [3.00.2] — 2026-08-12 — O token vai para Integrações, onde se procura por ele

Correção de endereço, apontada pelo Bruno: *"não seria melhor essa coisa de
token e teste estar em integrações?"*. Estava certo.

**Credencial de serviço externo mora em Integrações** — é onde vivem M365, Gmail,
Teams, SMTP e as chaves de IA. Eu havia posto o token do Hugging Face junto dos
roteiros de entrevista, misturando duas naturezas: quem procura *"onde ponho a
credencial X"* abre Integrações, e era lá que ela precisava estar.

A separação que ficou:

- **Integrações** → o TOKEN e o botão de testar (credencial).
- **Roteiros de entrevista** → ligar/desligar a separação de vozes, tamanho do
  trecho e retenção do áudio (política do processo).

⚠️ **Um assunto, um controle** (v2.75): o campo saiu da tela de roteiros em vez
de existir nos dois lugares — dois campos para a mesma credencial divergiriam, e
o RH não saberia qual vale. No lugar dele ficou um aviso que aparece **só quando
a separação está ligada e o token não foi configurado**, dizendo onde resolver.

Ao remover o controle, saíram junto o estado e a função que o alimentavam
(v2.78): `token`, `teste`, `testando` e `testar` teriam ficado declarados sem
uso, e o próximo a ler não saberia se é esquecimento ou intenção.

**Nota de operação:** a v3.00 não estava em produção quando o Bruno procurou o
campo — a VPS roda a v2.98.5. Nada estava quebrado; a tela ainda não existia lá.
O deploy da stack traz junto o container `transcricao` **bem maior** (~3 GB, com
PyTorch e pyannote), então o Portainer precisa RECRIAR o serviço, não só
reiniciá-lo.

## [3.00.1] — 2026-08-12 — A diarização que falha DIZ o que houve

Três perguntas do Bruno sobre a v3.00, e uma delas apontou um defeito real.

**"Esse token é pago? Tem limite?"** — não, e não. Conta e token gratuitos, e o
token serve **só para baixar o modelo uma vez**: depois disso ele roda local, em
PyTorch puro, no próprio container. Não há chamada de API por entrevista, não há
cota, não há custo por minuto — e o áudio continua sem sair de casa, que era a
decisão da v2.97. A tela agora diz isso, em vez de deixar a dúvida.

**"Se falhar? Não teria um fallback? Não seria erro silencioso?"** — aqui ele
estava certo, e o defeito era meu. A v3.00 tratava a falha **só no log**: a
transcrição saía sem rótulo e **nada aparecia na tela**. O RH abriria a ficha,
veria texto corrido, e não saberia se a diarização está desligada, sem token ou
quebrada. É o silêncio que a v2.66 (worker que não roda) e a v2.69 (documento que
não nasce) já cobraram caro.

Agora `_diarizar` devolve `(trechos, motivo)`: o motivo VOLTA para o registro e
daí para a tela, dizendo **o que resolve** — falta o token / a licença não foi
aceita / o modelo não respondeu. O fallback em si já existia e continua: sem
diarização o texto sai em parágrafos (v2.99). **Degrada, nunca perde** — mas
agora avisa.

⚠️ **A consolidação APAGAVA o aviso**: `g.erro = ... if falhos else None` zerava
o motivo que os blocos traziam. Os dois avisos agora convivem — qual bloco falhou
E por que não houve separação de vozes.

**"Não dá para customizar pelo front?"** — dá, e faltava o principal: um botão
**"Testar token"**, como o das chaves de IA (v2.00). Sem ele, o RH só descobriria
que o token está errado **depois de conduzir uma entrevista de 40 minutos**.
A rota consulta a API do Hub sem baixar os ~500 MB do modelo, e distingue os DOIS
motivos de recusa, que pedem ações diferentes: **401 = token inválido** (gere
outro) × **403 = licença não aceita** (abra a página do modelo e aceite). Rede
fora não vira "token recusado" — mandaria trocar uma credencial que está certa
(a lição da v2.00).

⚠️ **Duas mutações escaparam por eu substituir DEMAIS no teste.** A que faz o
aviso morrer no log passava verde porque o caso trocava a `_diarizar` inteira —
nunca exercitando o `return` dela. Só foi pega depois de o teste chamar a função
REAL, nos dois caminhos de falha que existem sem rede (sem token; pyannote
ausente). É a lição da v2.68 pela segunda vez nesta leva: **substitua o limite
externo, não as suas próprias funções.**

## [3.00.0] — 2026-08-12 — Interlocutor 1, Interlocutor 2

Pergunta do Bruno: *"será que conseguimos identificar os interlocutores, nem que
seja interlocutor 1, 2…?"*. **É essa formulação que torna o recurso aceitável** —
e ela reabre uma decisão que a v2.97 tinha fechado.

A v2.97 recusou diarização porque **atribuir fala a uma pessoa NOMEADA** numa
ficha que ela assina é risco jurídico: dizer *"o candidato afirmou X"* quando
quem disse foi o entrevistador é grave. Mas `Interlocutor 1` **não afirma quem é
ninguém** — só marca que a voz mudou. Se errar, o pior caso é um rótulo trocado
num parágrafo, e quem esteve na conversa percebe lendo. É a diferença entre
IDENTIFICAR e SEPARAR, e só a segunda está sendo feita.

⚠️ **NUNCA troque `Interlocutor N` pelo nome da pessoa.** No dia em que alguém
pedir isso, a pergunta é: *o que acontece se o rótulo estiver errado numa peça
que vai para uma reclamatória?*

**O custo é TEMPO, e o Bruno decidiu pagá-lo** (ligada por padrão): o pyannote
3.1 tem RTF ~1,74 em CPU — 10 min de áudio levam ~18 min. Uma entrevista de 40
minutos passa de poucos minutos para ~1h10 na fila. Roda em segundo plano, então
não trava ninguém; a transcrição fica pronta mais tarde. **Configurável no
painel** para desligar sem deploy se o tempo incomodar.

Três decisões que sustentam o desenho:

1. **A numeração segue a ORDEM DE ENTRADA na conversa**, não o rótulo interno do
   pyannote (`SPEAKER_00`, `SPEAKER_02`…), que é arbitrário e pularia números —
   "Interlocutor 3" numa conversa de duas pessoas faria o RH procurar um terceiro
   que não existe.
2. **O falante vem da MAIOR sobreposição**, não do instante inicial: Whisper e
   pyannote cortam em pontos diferentes, e casar pelo início daria o falante
   ANTERIOR em toda troca de turno — justamente onde o rótulo importa.
3. **Falha na diarização DEGRADA, nunca perde a transcrição.** Sem token, sem
   licença aceita, modelo indisponível: o texto sai em parágrafos, como na
   v2.99. O texto é o que serve para escrever a justificativa; saber quem falou
   é melhoria.

⚠️ **O modelo é GATED**: exige token gratuito do HuggingFace e aceite de licença.
A tela pede o token, diz onde consegui-lo, e avisa que **sem ele a transcrição
continua saindo** — só não vem separada. O token é credencial: nunca volta ao
painel (só `tem_hf_token: true/false`) e nunca entra na auditoria.

⚠️ **O gerador do faster-whisper é de uma passada só** — materializado em lista
antes de ser usado duas vezes (agrupar por falante E cair no texto corrido se a
diarização falhar). Sem isso, o segundo uso viria vazio e a transcrição sairia em
branco **sem erro nenhum**.

`torch` vem do índice de CPU (`--extra-index-url .../whl/cpu`): o padrão traz
CUDA e engordaria a imagem em ~2 GB de driver de GPU que o VPS não tem. Só o
container de transcrição carrega esse peso.

Testes: 18 asserções, **3 mutações, 3 pegas** (numerar pelo rótulo do pyannote;
casar o falante pelo instante inicial; deixar a falha derrubar a transcrição).
⚠️ A terceira **só passou a ser pega** depois de o teste exercitar o CAMINHO REAL
(`_transcrever`, com o modelo substituído) em vez da função interna — antes ela
saía verde. É a lição da v2.68.

## [2.99.0] — 2026-08-12 — A transcrição se lê, e o modelo de mensagem se ativa

Dois feedbacks do Bruno, ambos sobre coisa que existia e não servia.

**A transcrição vinha num bloco único** — *"a leitura fica difícil"*. Estava
certo: 40 minutos de conversa davam ~6.000 palavras num parágrafo só, porque o
worker fazia `" ".join(...)` sobre os segmentos. O `faster-whisper` já devolve
cada segmento com `start`/`end`, e era essa informação que estava sendo jogada
fora.

Agora `_em_paragrafos` quebra por **pausa** (`PAUSA_PARAGRAFO_S = 2.5s`): numa
entrevista, o silêncio entre turnos é onde um para de falar e o outro começa.
Sem diarização não se sabe QUEM falou — mas se sabe que a fala mudou de dono, e a
quebra reproduz isso na página. Fala corrida muito longa também quebra, mas
⚠️ **só em fim de frase**: cortar "trabalhei três anos na portaria" ao meio
mudaria o que se lê, e a transcrição é peça que circula (vai ao PDF timbrado).

`test_transcricao_paragrafos.py` no CI (11 asserções, stdlib pura — a função é
pura e não importa `faster_whisper`), **3 mutações, 3 pegas**: voltar ao bloco
único, cortar por tamanho sem exigir fim de frase, e ignorar a pausa.

**Modelo de mensagem duplicado ficava num beco.** A cópia nasce inativa de
propósito (v2.87 — cópia não vale antes de alguém revisar), e **não havia como
ativá-la**: o `PATCH` aceitava o campo, mas nenhum botão na tela o alcançava.

O `ativo` **tem** finalidade, ao contrário do que parecia: o `ComporMensagem`
filtra `modelos.filter(m => m.ativo)`, então modelo inativo some do seletor de
quem dispara — é o que impede um rascunho de aparecer para quem vai mandar a
mensagem. O que faltava era a saída.

Rota PRÓPRIA (`PUT .../ativo`) em vez de reusar o `PATCH`: aquele exige o corpo
inteiro, e reenviar título, corpo e tags só para alternar um booleano
sobrescreveria o texto na primeira divergência. Um ato, uma rota (KISS). O botão
diz o que ACONTECE ao clicar — "ativar"/"desativar" —, nunca o estado atual
(v2.78).

⚠️ O `test_api_front_existe` pegou um defeito meu antes do commit: a função nova
foi chamada no JSX e **não existia** no `api.js` (minha edição casou o nome
errado). É exatamente o defeito da v2.73 que ele existe para impedir.

## [2.98.5] — 2026-08-12 — A transcrição em papel timbrado

O PDF que o Bruno escolheu no protótipo, ao lado do `.txt` que já existia. Os
dois servem a coisas diferentes: **o texto puro é para copiar um trecho** e colar
na justificativa; **o PDF é para arquivar e circular** — e documento que circula
precisa dizer de quem é, de quando e para qual vaga. Um `.txt` solto numa pasta,
meses depois, é um arquivo sem dono.

Reusa o `_OficioPDF` das fichas (timbre, marca d'água, rodapé) e o MESMO
cabeçalho de identificação da ficha de entrevista — quem lê os dois lado a lado
não deveria ter de reaprender onde cada coisa está. Inventar um segundo papel
timbrado faria os dois divergirem na primeira mudança da marca (v2.65).

Três decisões do conteúdo:

- **O consentimento é impresso no documento**, não fica só no banco: é ele que
  sustenta a legalidade da gravação, e quem lê a transcrição meses depois precisa
  ver que ela foi autorizada, por quem e quando.
- **Transcrição parcial avisa no PAPEL**, não só na tela: um documento que
  circula não pode se apresentar como completo quando um trecho falhou (v2.93).
- **Aviso de método, e não é formalidade**: a transcrição é automática, sai com
  erros de reconhecimento e **não identifica quem falou** (sem diarização, por
  decisão de desenho). Quem lê precisa saber disso ANTES de citar um trecho como
  fala literal da pessoa.

⚠️ Gerado SOB DEMANDA, nunca gravado — não entra nas três fontes que o
`services/dossie.py` varre, e portanto não entra no dossiê de admissão (§ 15.4).

Verificado: A4, 3 imagens na página (timbre + marca d'água), as quatro seções
presentes.

⚠️ **Correção do CI, e o erro foi meu**: a edição que acrescentou
`test_blocos_gravacao` ao `ci.yml` gravou `
` LITERAL no lugar da quebra de
linha, e o shell leu isso como um teste chamado `n` —
`python: can't open file '/app/tests/n.py'`. Todos os 27 testes passavam; o
pipeline caía no nome inventado. Corrigido e **verificado simulando a expansão
do loop**: 27 nomes, nenhum inválido.

## [2.98.4] — 2026-08-12 — Baixar transcrição volta a funcionar

**Defeito visto pelo Bruno na tela**: clicar em "⬇ Baixar transcrição (.txt)"
abria uma janela com `{"detail":"nao_autenticado"}`.

A causa: era um `<a href="/api/...">` para uma rota **autenticada**. O sistema
autentica por `Authorization: Bearer` — não há cookie de sessão —, e link
seguido pelo navegador é um **GET limpo**, sem header nenhum. O JSX fica
plausível, o build passa, e só quebra no clique. Mesma família do `api.x()`
inexistente (v2.73) e da `prop` inventada (v2.64).

Reproduzido e corrigido com prova: a mesma URL devolve **401 sem header** e
**200 com header**; na tela, o download agora traz `transcricao.txt` com o
conteúdo certo.

`BotaoBaixar` (novo) busca com o header, cria o `objectURL` e dispara o download
— o padrão que o `VisualizadorArquivo` (v2.33), o `baixarDossie` e o
`PlayerAudio` já usavam; faltava um componente para os links soltos. ⚠️ O nome
do arquivo vai explícito: o `Content-Disposition` da rota **não alcança** o
`objectURL`, e sem ele o download sairia com um UUID por nome.

Eram DOIS links quebrados (a ficha da entrevista e a lista da pessoa). Varri o
resto do JSX: o único `href={api...}` restante é o preview do assinante externo,
que autoriza pelo TOKEN DA URL — ali o link direto está correto.

**Teste dos blocos** (`test_blocos_gravacao.py`, 22 asserções) entrou no CI,
fechando a dívida da v2.98: os blocos vinham sendo validados só à mão.
Validado por **3 mutações**, e ⚠️ **uma delas expôs um furo no próprio teste**:
as keys de áudio usavam zero-padding (`001`, `002`, `010`), então a ordem por
key coincidia com a ordem por índice e a mutação que troca `indice` por
`audio_key` passava VERDE. Com `bloco-2` e `bloco-10` — o caso real — a mutação
é pega por três asserções. **Sem rodar a mutação, o teste teria ido para o CI
parecendo proteger a ordem da conversa.**

## [2.98.3] — 2026-08-12 — O áudio expira em 120 dias; a transcrição fica

Retenção do áudio de entrevista, com o prazo que o Bruno definiu: **120 dias por
padrão, customizável no painel**, e exclusão antecipada pela ficha (que já
existia desde a v2.97).

**O áudio expira; o TEXTO permanece.** Voz é dado pessoal — há entendimento de
que é biométrico — e guardá-la para sempre é difícil de justificar. A
transcrição é o que serve para escrever a justificativa da avaliação: apagá-la
junto tiraria a razão de o módulo existir.

Três decisões que NÃO devem ser afrouxadas:

1. **Retenção `0` = INDETERMINADO**, não "apagar tudo hoje" (mesma convenção do
   log, v2.29). ⚠️ Trocar `<= 0` por `is not None` inverteria o significado e
   apagaria a base inteira em silêncio. A tela diz isso em palavras, e avisa
   quando o valor é 0 — campo numérico sem explicação seria lido ao contrário.
2. **Conta a partir da GRAVAÇÃO, não da criação da entrevista.** Uma entrevista
   marcada em janeiro e gravada em junho tem áudio de junho.
3. **O REGISTRO permanece.** Apagar a linha apagaria a prova de que a pessoa foi
   consultada e consentiu — que é exatamente o que ela existe para provar.

**Provado, não presumido**: envelheci uma gravação para 200 dias e rodei o
expurgo. O áudio sumiu do MinIO, a chave foi limpa nos blocos e no registro
principal, e o carimbo do consentimento continuou lá.

Roda na carona do expurgo diário (`python -m app.workers.expurgo`), que já está
nos DOIS arquivos de deploy — sem worker novo para esquecer de declarar (v2.66).

Configuração em **Configurações → 🗣️ Roteiros de entrevista**, junto do
instrumento: quem ajusta o roteiro é quem ajusta como a entrevista é gravada.
A mudança **vai para a auditoria** — meses depois, alguém vai perguntar por que
um áudio de 90 dias não existe mais, e a resposta precisa estar registrada.

⚠️ A rota `/rh/entrevistas/gravacao/config` foi declarada **ANTES** da
paramétrica `/rh/entrevistas/{entrevista_id}`: depois dela, "gravacao" viraria um
UUID inválido e a tela receberia 422 (a armadilha de rotas do FastAPI, já
registrada no `CLAUDE.md`).

## [2.98.2] — 2026-08-12 — A gravação acompanha a pessoa, e aparece onde ela é

Pedido do Bruno: *"o áudio da entrevista acompanha o colaborador quando ele
deixar de ser candidato"* — e a correção do endereço: **não é na ficha da
entrevista, é na tela de Admissão e na de Colaborador**.

O dado já atravessava: `Entrevista` tem as DUAS FKs (`talento_id` e
`candidato_id`, v2.64) e a gravação pendura na entrevista, então ela segue a
pessoa sozinha. **O que faltava era a tela dar caminho para ele** —
`EntrevistasDaPessoa` era uma tabela que listava a entrevista e não levava a
lugar nenhum.

Agora a listagem tem a coluna **Gravação**, com player e link da transcrição. A
mesma tela (`Detalhe.jsx`) serve Admissões e Colaboradores, então vale nos dois.

**Provado na prática, não presumido**: uma entrevista gravada com a pessoa ainda
TALENTO continuou acessível — com áudio e status — depois de convertê-la em
candidato.

⚠️ **Carga em LOTE** (`gravacoes_por_entrevista`): duas consultas para todas as
entrevistas da pessoa, não uma por linha. É o N+1 que a v2.15 já cobrou neste
mesmo arquivo (43 consultas para 39 talentos). O resumo traz só o que a LISTA
precisa — status, se há áudio/texto e quantos blocos; quem quer o detalhe abre a
ficha.

A contagem de blocos vai junto porque o front precisa saber qual URL de áudio
usar (arquivo único × primeiro trecho) — sem ela, adivinharia.

## [2.98.1] — 2026-08-12 — Gravar, pausar, retomar — e ouvir na própria tela

Segunda parte da gravação em blocos: agora ela funciona ponta a ponta.

**Blocos automáticos e invisíveis.** O `MediaRecorder` fecha um pedaço a cada
10 min e ele sobe SOZINHO, com o áudio do bloco seguinte já sendo capturado — o
corte não interrompe a conversa. O entrevistador clica em Gravar e em Encerrar,
e nada mais.

**Pausar ≠ Encerrar** (decisão do Bruno, sobre o clique acidental): pausar
retoma **no mesmo bloco**, e o relógio do corte automático repõe apenas o tempo
que FALTAVA — senão uma entrevista com muitas pausas geraria blocos de 25 min.
Encerrar pergunta antes, porque é irreversível. Medido no navegador: gravar 3s →
pausar (congela em 3s) → retomar (segue para 5s, não reinicia) → encerrar → o
bloco de 85 KB chega ao MinIO com duração e índice certos.

**Player nativo, desktop e celular** (`PlayerAudio.jsx`). Não é `<audio src>`
direto: as rotas exigem `Authorization`, e o `<audio>` não manda header — faria
um GET anônimo e receberia 401. Busca o blob e cria `objectURL`, o padrão do
`VisualizadorArquivo` desde a v2.33. **Só carrega quando a pessoa pede**: baixar
dezenas de MB ao abrir a ficha, no celular com dados móveis, sem ninguém pedir,
seria o oposto do desejado. O `<audio controls>` é o NATIVO de propósito — no
celular ele vira o controle do sistema, com a tela bloqueada e no fone.

**Um bloco que falha não derruba os outros.** Um job de fila por bloco: o texto
do começo aparece enquanto o fim ainda roda, e retentar custa 10 minutos, não 90.
Se o upload de um trecho falhar, **a gravação continua** — interromper a
entrevista por causa de um trecho perdido seria pior — e a tela diz qual falhou.

⚠️ **Defeito achado ao testar dois blocos seguidos**: `pode_gravar` era
`status == consentido`, e a partir do PRIMEIRO bloco a gravação passa a
`aguardando` — o SEGUNDO bloco era recusado com "sem consentimento", no meio da
conversa. Agora a checagem é o consentimento estar dado e não ter sido retirado;
os estados de processamento são consequência dele, não sua negação. `recusado` e
`nao_perguntado` continuam barrando, que é o ponto.

Mais: aviso do navegador ao fechar a aba gravando; disclaimer dizendo que o
envio acontece durante a conversa (senão alguém fecha a aba achando que só o
Encerrar salva); e o `objectURL` é revogado ao sair — sem isso o áudio inteiro
fica na memória depois de fechar a ficha.

## [2.98.0] — 2026-08-12 — O dossiê tem o nome certo, e a gravação vira blocos

**Nome do dossiê: `DOCS ADM - KATIA POLIANE.pdf`** (pedido do Bruno) — caixa
alta, sem acento, o padrão da pasta física do RH. Virou função ÚNICA
(`dossie.nome_arquivo_dossie`) porque o dossiê é baixado de **quatro** lugares
(a ficha no front, a rota individual, o Arquivo e o ZIP em lote) e cada um
montava o nome à mão. Quatro cópias divergem na primeira mudança, e o sintoma
seria o RH recebendo arquivos com dois padrões sem saber por quê. ASCII por
necessidade: o header `Content-Disposition` não carrega acento com segurança em
todos os clientes.

**Primeiro passo da gravação em BLOCOS** — base estrutural, com o resto vindo na
sequência desta leva.

Uma entrevista real dura 40–90 min, e o arquivo único tem três problemas
concretos: se o navegador cair aos 32 minutos **perde-se a conversa inteira** (e
ela não se refaz); o upload de 90 min arrisca o `proxy_read_timeout` do nginx
justamente no fim; e a transcrição só começa depois de tudo terminar. Com blocos
de **10 min (configurável em `transcricao_bloco_min`)**, o que já subiu está
salvo e o texto do começo aparece enquanto o fim ainda roda.

⚠️ **A divisão é automática e invisível** — decisão do Bruno, confirmada: o
entrevistador clica em Gravar, conversa, e clica em Encerrar. Nunca escolhe
blocos.

⚠️ **A ordem é o `indice`, jamais a listagem do storage**: ela é lexicográfica e
põe `bloco-10` antes de `bloco-2`, o que colocaria o meio da conversa no lugar
errado — e ninguém perceberia lendo o texto (é a armadilha da v2.35, onde o
verso do RG aparecia como frente). `UniqueConstraint(gravacao_id, indice)`:
reenviar um bloco SUBSTITUI, em vez de criar um fantasma no meio da conversa —
e reenviar é exatamente o que a rede instável provoca.

Três regras de consolidação, cada uma com o custo que evita:

- **Bloco ainda rodando ⇒ a gravação segue `processando`.** Marcar `pronta` com
  metade da conversa faria o RH ler um texto truncado achando que é tudo.
- **Um bloco mudo NÃO contamina os outros** — silêncio enquanto a pessoa lê um
  documento é normal. Só é `audio_inaudivel` se TODOS forem.
- **Bloco falho ⇒ o texto sai, com o aviso de QUAL faltou.** Recusar tudo por 10
  minutos perdidos jogaria fora os outros 80; apresentar como completo esconderia
  o buraco (a lição do dossiê, v2.93).

**Nomes de download com DATA**: `ENTREVISTA 12-08-2026 - KATIA POLIANE.webm` (e
`- PARTE 2` nos blocos). A data entra porque a mesma pessoa pode ser
entrevistada mais de uma vez, e dois arquivos de nome idêntico na pasta de
Downloads viram `(1)` e `(2)`, que não dizem qual é qual.

**Retenção configurável** (`transcricao_retencao_dias`, padrão **120** — decisão
do Bruno): o áudio expira, o TEXTO permanece. `0` = nunca expurgar, mesma
convenção do log (v2.29) — ⚠️ trocar `<= 0` por `is not None` transformaria
"guardar para sempre" em "apagar tudo hoje", em silêncio. O expurgo em si vem no
próximo passo.

⚠️ **`resumo()` passou a exigir a sessão** para listar os blocos. As 5 chamadas
foram corrigidas: sem o `db`, a lista voltaria VAZIA em silêncio — a tela diria
que não há blocos numa entrevista que os tem.

Migration reversível testada (upgrade → downgrade → upgrade). Sem regressão:
`test_gravacao_entrevista`, `test_entrevistas` e `test_design_system` verdes.

## [2.97.0] — 2026-08-12 — A entrevista se grava, com autorização

Módulo de gravação e transcrição de entrevistas, desenhado na 22ª leva
(`docs/planejamento/14-transcricao-de-entrevistas.md`) e priorizado pelo Bruno.
O *job* não é "ter o áudio": é **não perder o que foi dito** e **não escrever
enquanto entrevista** — hoje o entrevistador divide atenção entre conduzir e
anotar, e quem paga é a justificativa que ele assina depois.

**Decisões do Bruno, cumpridas:** fila, container separado, **self-hosted sem
API paga** (`faster-whisper`), resultado para baixar. Sem diarização — atribuir
fala errada numa ficha que a pessoa assina é risco jurídico, não ruído.

> **Áudio de entrevista não sai de casa.** Está escrito aqui e no documento
> porque, sem registro, alguém "otimiza" trocando por um serviço pago daqui a
> seis meses e desfaz a decisão sem saber que ela existiu.

**O consentimento é a parte que decide se isto pode existir.** Gravação de voz é
dado pessoal e há entendimento de que voz é dado biométrico. Numa entrevista de
emprego a conversa é a mais assimétrica que existe — de um lado quem decide, do
outro quem precisa do emprego. Por isso:

- A tela **pergunta**, com "Ela autorizou" e "Ela não autorizou" na **mesma
  classe de botão** (medido na tela, não presumido). Se um fosse verde grande e o
  outro um link cinza, a pessoa clicaria no primeiro por não sentir que pode
  recusar — e isso é teatro de consentimento.
- A tela **diz** que o áudio não vai a serviço externo e que **recusar não afeta
  em nada a avaliação**.
- **A recusa é um ATO registrado**, com quem registrou e quando. Sem
  manifestação gravada, "não foi perguntado" e "disse não" são a mesma linha em
  branco (v2.34) — e são estados distintos: são **oito**, não os seis do
  desenho, porque faltava `nao_perguntado`.
- **Sem consentimento, o serviço recusa** — a checagem vive em
  `marcar_para_transcrever`, não só na rota: "as rotas não deixam" não é
  garantia (v2.66).

**Três decisões que apareceram ao implementar, não no desenho:**

1. **Fila própria** (`transcricao`), não a `default`: áudio leva minutos e
   seguraria atrás de si o Match e a indexação de currículo, que levam segundos.
2. **Retirar o consentimento com áudio existente RECUSA, oferecendo a saída** —
   aceitar deixaria um áudio existindo sob um registro dizendo que a pessoa não
   autorizou, a pior das duas mentiras. O 409 diz o que resolve (excluir), em vez
   de só bloquear (v2.87/v2.93).
3. **A exclusão NÃO passa pela lixeira**, ao contrário de toda exclusão do RH:
   áudio é dado biométrico, e reter 60 dias seria o oposto do que se quer quando
   alguém retira o consentimento. O **registro** fica (é a prova da consulta); o
   **áudio** sai do storage — "some da tela" não é "foi apagado" (v2.35).

**Infra:** imagem própria `gestao-rh-transcricao` (o `faster-whisper` pesa
~500 MB e nem a API nem o worker o executam), com `ffmpeg` — o `MediaRecorder`
entrega WebM/Opus e sem ffmpeg a transcrição falharia num áudio perfeito — e
volume `whisper-cache`, senão cada restart rebaixa o modelo. Container nos
**dois** arquivos de deploy (v2.66) **e** na matriz do `ci.yml`: sem esta última,
o `portainer-stack.yml` apontaria para uma imagem inexistente.

⚠️ **A transcrição não tem caminho para o dossiê** (§ 15.4). O `dossie.py` varre
`SolicitacaoAssinatura` sem filtrar origem, então fluxo novo entra nele POR
PADRÃO — e o dossiê circula: vai ao cliente e à pasta física. Há asserção
cobrando isso.

Verificado: 9 cenários pela API rodando (recusa nos dois sentidos, formato
inválido nomeando os aceitos, exclusão apagando o objeto no MinIO), tela em
desktop e celular com zero vazamento, e `test_gravacao_entrevista.py` no CI com
**3 mutações, 3 pegas** (remover a trava de consentimento; esquecer de apagar o
áudio; permitir retirar o consentimento com áudio existente).

**Ainda não feito**, registrado no § 11 do documento: exibição no módulo de
Arquivo (hoje só no card da entrevista) e a **retenção do áudio**, que precisa de
decisão — a transcrição pode sobreviver ao áudio.

## [2.96.1] — 2026-08-12 — O padrão da tela de trabalho vira obrigatório

O Bruno usou a ficha redesenhada e confirmou: *"funcionou"*. Só agora o padrão
vira regra — era o combinado, e é a razão de ele não ter sido cravado junto com o
código: **padrão que não passou pelo uso real é palpite com autoridade**.

**§ 8c do `08-sistema-de-design.md`** (novo, obrigatório) — vale para toda tela
onde se *trabalha sobre um registro* (ficha da pessoa, benefício, vaga,
avaliação), não para listas. Quatro regras: o **impedimento no topo** com o
atalho que resolve; **um trabalho por vez** em abas por natureza; **um verde por
tela** (o ato que fecha o trabalho); e **exceção dita em palavras**, com o bloco
de muitos controles nascendo recolhido. Cada uma traz o custo já pago por não
segui-la, e o resultado medido (−25% de altura no desktop, −35% no celular).

**`test_tela_de_trabalho.py`** no CI — documento não reprova ninguém. Sem o
teste, a próxima tela nasce empilhada e o § 8c vira recomendação que se lê depois
de já ter feito errado.

O que ele deliberadamente NÃO cobra: "a aba certa abre por padrão" ou "o
impedimento é a frase certa" dependem de julgamento, e cobrar por regex o que
exige juízo produz falso alarme — que ensina a ignorar o alarme (v2.91).

⚠️ **Uma das três mutações expôs um furo real no próprio teste**: mover o resumo
das exceções para DENTRO do `<details>` (o defeito que ele existe para impedir)
passava verde, porque a asserção olhava o trecho errado do arquivo. A prova agora
é posicional — o resumo tem que vir antes da abertura do `<details>` que contém o
`<Exigencias>`. **Sem rodar a mutação, esse teste teria ido para o CI parecendo
proteger** — é a v2.64 numa variação nova.

## [2.96.0] — 2026-08-11 — Um trabalho por vez na ficha da pessoa

Passos 3 e 4 do redesenho aprovado no protótipo. Fecha a leva iniciada na v2.95.

**Quatro abas em vez de 14 blocos empilhados** — Documentos · Cadastro ·
Contratação · Histórico. A v2.47 já havia agrupado a tela por NATUREZA e isso
resolveu o "muito rolar" da época; o que sobrou é que as três faixas continuavam
na MESMA coluna, com o mesmo peso visual. Decisões do Bruno, perguntadas antes de
codar: **Documentos abre por padrão** (é o trabalho diário), e **Contratação sai
de dentro de "cadastro"** porque definir posto/salário é outro ato, feito uma vez.

Três decisões técnicas que sustentam isso:

- **`hidden`, não desmontar.** Trocar de aba não pode perder o que está sendo
  digitado na outra — e o estado dos componentes filhos (63 `useState` nesta
  tela) se perderia com montagem condicional.
- **A aba NÃO se guarda em `localStorage`.** Abrir a ficha de alguém é começar um
  trabalho novo; herdar a aba da pessoa ANTERIOR abriria a tela em Histórico sem
  ninguém pedir. (Em Config, guardar faz sentido — lá é preferência de uma tela
  só, não estado de outra pessoa.)
- **Reusa `.rh-abas`**, a primitiva que já existe (Creche etc.), em vez de
  inventar classe nova — a lição da v2.65: passar no teste estrutural não é
  seguir o padrão, e o padrão certo já estava escrito.

**Um verde por tela.** Eram seis botões `btn-principal` competindo pelo papel de
ação principal; "Efetivar" (irreversível) tinha o mesmo peso de "Salvar data".
Liberar informativo, acrescentar documento e salvar posto viraram secundários. O
verde cheio fica no ato que FECHA o trabalho — "Efetivar", e "Aprovar" dentro da
aba de documentos, que é o que fecha aquela unidade. **Medido: 2 → 1** botão
primário visível.

**Resultado medido** (mesmo critério antes e depois — `checkVisibility()`, que
resolve `<details>` fechado e `[hidden]`, coisa que `getBoundingClientRect` não
faz):

| | antes | depois |
|---|---|---|
| Altura da página (desktop) | 1815px | **1363px** (−25%) |
| Altura da página (celular) | 2360px | **1535px** (−35%) |
| Controles visíveis | 43 | **36** |
| Botões verdes cheios | 2 | **1** |
| Tamanhos de fonte | 13 | **12** |

⚠️ **Defeito de campo achado na medição, não no código**: "✅ Efetivar como
colaborador" saía **CORTADO** no celular — o rótulo não cabe em 165px e o
`text-overflow` escondia o corte em vez de denunciá-lo (v2.78). Corrigido com
`.so-desktop`, que encurta para "✅ Efetivar" no celular: encurtar rótulo é o
degrau ANTES de esconder, e ação nunca se esconde (v2.76.1).

Verificado nas quatro abas, claro e escuro, desktop e celular: zero vazamento
lateral, nenhum botão cortado. As 21 réguas de layout continuam verdes.

## [2.95.0] — 2026-08-11 — O que trava a admissão aparece primeiro

Primeiros dois passos do **redesenho da ficha da pessoa**, validado pelo Bruno em
protótipo antes de virar código. O pedido foi *"não tô achando muito intuitivo,
o RH não tá achando certas coisas, parece muita poluição visual"*.

**Medi antes de opinar** (Playwright, 1440×900 e 390×844): a ficha tem **109
controles clicáveis**, **54 caixas de marcação**, **14 blocos** de mesmo peso
visual e **15 tamanhos de fonte**. O diagnóstico não é "está feio" — é que a tela
não distingue o que se faz todo dia do que se faz uma vez por ano. "Aprovar a
CTPS" e "definir quais campos são obrigatórios para esta pessoa" têm a mesma
borda, o mesmo fundo e a mesma área.

**1 · O impedimento sobe para o topo** (`Detalhe.jsx::ImpedimentoDaFicha`). A
informação já existia — `GET /rh/candidatos/{id}/diagnostico` devolve
`dossie.pendencias` —, mas só aparecia dentro do bloco de Diagnóstico, no FIM da
página, atrás de um `<details>`, depois de ~65 linhas de telemetria. **A resposta
estava pronta e ninguém a via**: em 11/08 isso custou 54 minutos e três exigências
médicas desmarcadas por engano (v2.93). Três decisões: silêncio quando não há
impedimento (bloco verde em toda ficha seria mais um cartão competindo por
atenção); **falha de carga não vira alarme** (dizer "não foi possível verificar"
no topo de toda ficha ensinaria a ignorar a faixa vermelha — v2.88); e nomes de
verdade em vez de enum.

⚠️ **`_traduzir_pendencia` fazia `valor.replace("_", " ")`**, o que produzia
"ficha emergencia" e "termo vt" — sem acento nem maiúscula. Só apareceu ao ver a
tela renderizada (regra da v2.47). Agora deriva de `NOMES_DOC` e de
`exigencias.ROTULOS`, os dois mapas que já existiam: a terceira lista à mão
envelheceria torto e em silêncio (v2.69).

**2 · As 54 caixas dizem em PALAVRAS o que fugiu do padrão**
(`Exigencias.jsx::ResumoDasExcecoes`). Três caixas desmarcadas no meio de 54
idênticas são invisíveis — foi exatamente o caso de ontem. Agora a ficha mostra
*"Esta pessoa tem 3 exceções: Dispensados: Usa medicamento contínuo, Condições
médicas, Contato de emergência."* ⚠️ **O resumo mora FORA do `<details>`**: dentro
dele só apareceria para quem abrisse, e o problema que ele resolve é ninguém
abrir — `<details>` fechado nem renderiza o conteúdo (v2.76.2), então ele tem
consulta própria. Marcar o item alterado em âmbar (que já existia) não bastava:
exige varrer a grade item a item.

⚠️ **`--atencao-suave` não tinha par no tema escuro** — era `#fdf3e2` fixo, âmbar
CLARO nos dois temas. É a armadilha da v2.46, achada ao usar o token pela
primeira vez fora do `.chip`. Contraste medido depois da correção: **10,85:1** no
resumo e **7,64:1** no impedimento (mínimo AA é 4,5:1).

Verificado na tela, não só no código: claro e escuro, desktop e celular (zero
vazamento lateral em 390px; o impedimento cai a 295px do topo, dentro da primeira
tela). As 13 réguas de `tabelas-cabem-na-tela` e `lista-suspensa-nao-corta`
continuam verdes. O levantamento que produziu os números fica em
`frontend/tests/e2e/_levantamento-densidade.spec.js` (prefixo `_`: roda à mão,
não no CI) para medir de novo e comparar.

Faltam os passos 3 (abas) e 4 (um verde por tela) — serão outra leva, com nova
medição antes e depois.

## [2.94.0] — 2026-08-11 — A automação entra pela porta da frente

Primeiro degrau do **MCP do portal** (desenho em
`docs/planejamento/13-mcp-do-portal.md`): o que a automação É no sistema, e como
ela prova quem é. **Nenhuma ferramenta MCP ainda** — este passo existe para que,
quando elas chegarem, já entrem por uma porta com nome, papel e botão de
desligar.

**Dois achados encolheram muito o trabalho, e valem registro porque o padrão se
repete neste projeto: antes de construir, procurar o que já existe.**

1. **`api/diagnostico.py` já responde quatro das seis ferramentas planejadas** —
   nasceu do dossiê da Kátia que não gerava, é só leitura, e devolve dados-chave,
   por que o dossiê não gera, situação dos documentos e linha do tempo. Escrever
   seis rotas novas teria sido reimplementar o que está no ar.
2. **A porta de escrita também já existe**: `POST /rh/talentos` (v2.73) nasceu
   para *"currículo que chega por e-mail"* e já recusa duplicata **nomeando quem
   é**, com `forcar` para homônimo legítimo.

O que faltava de verdade não era ferramenta — era **credencial**. As rotas são de
sessão de navegador: login com senha e token de 12h. Sem isso, a automação
pararia todo dia, e a saída óbvia (guardar a senha do usuário no desktop) é
exatamente o que não se faz — senha vale para sempre e abre o painel inteiro.

**Papel `automacao`** (`services/permissoes.py`), papel de MÁQUINA e não de
gente: 4 permissões (`admissao:ler`, `selecao:ler`, `selecao:escrever`,
`organizacao:ler`) contra as 27 do papel `rh`. Cada ausência é uma decisão, não
um esquecimento: **sem `dados:exportar_base`** (o eixo é a natureza do ATO — um
GET que devolve 1.171 CPFs é exportação, não leitura), **sem `dados:auditoria` e
`:logs`** (quem é auditado não lê a própria trilha), **sem efetivar, desligar,
decidir creche, gerar dossiê ou criar usuário**. A única escrita é a de cadastrar
talento. Existe em migration PRÓPRIA porque a semeadura de papéis (`c7e9a1b3d5f8`)
já rodou em produção — migration aplicada não roda de novo (v2.70), e acrescentar
o papel àquela lista consertaria só bancos novos.

**Credencial de máquina** (`models/` + `services/token_automacao.py`), e a
pergunta que decidiu o desenho foi *"se vazar hoje à noite, como eu corto?"*:

- **Revogável.** O token de sessão é `itsdangerous` stateless: enquanto não
  expira, vale — não há onde marcar "este não vale mais", e cortá-lo exigiria
  trocar o `SECRET_KEY`, derrubando a sessão de todo mundo. **Medido: 200 → 401
  no instante da revogação.**
- **O segredo não fica no banco** — só o `sha256`, e um prefixo `mcp_…` para a
  tela distinguir um token do outro. Quem tem o banco não tem a credencial.
  Prefixo reconhecível pela mesma razão de `sk-`/`ghp_`: credencial anônima
  vazada demora muito mais para ser identificada.
- **Revogar MARCA, não apaga** — a linha é a prova de que a credencial existiu e
  de quando deixou de valer. Idempotente: revogar de novo não reescreve o momento
  real do corte.
- **Usuário inativo corta a credencial junto** — senão desligar alguém deixaria o
  token dele vivo, que é o buraco que ninguém lembra de fechar.
- **Entra pelo MESMO `requer_rh`**, e daí segue para o `exige(...)` de sempre.
  ⚠️ Isto não é detalhe de implementação: uma porta paralela que autenticasse sem
  passar pela checagem furaria o modelo de papéis inteiro (v2.86) sem nada na
  tela denunciando. **Medido na API rodando**: 200 em `/rh/candidatos` e
  `/rh/talentos`; **403** em `/rh/usuarios`, `/rh/logs/servicos` e
  `/rh/colaboradores`. No log, o ator sai como `automacao:<e-mail>` — no dia em
  que algo estranho aparecer, *"foi gente ou foi robô?"* tem resposta.

Gestão em `/rh/tokens-automacao` (GET/POST/DELETE, sob `config:usuarios`).
Descrição é obrigatória: sem ela, "revogar o que vazou" vira adivinhação entre
tokens idênticos na tela.

Testes: `test_papel_automacao.py` (stdlib, trava o escopo estreito — 3 mutações:
alargar com `exportar_base`, alargar com escrita que o RH também tem, promover a
superadmin) e `test_token_automacao.py` (19 asserções, 3 mutações: ignorar a
revogação, guardar o segredo em claro, aceitar usuário inativo). As três de cada
reprovam. Downgrade das duas migrations executado de verdade (1 → 0 → 1).

## [2.93.0] — 2026-08-11 — Um PDF corrompido não derruba o dossiê inteiro

**O defeito custou 54 minutos e três campos médicos de um colaborador real.**
Um certificado emitido por site de governo (o "nada consta") veio com um PDF que
o `pypdf` não abre — `PdfReadError: Invalid Elementary Object starting with
b'\x00' @76085`. O `_adicionar_em_a4` estourava e **o dossiê inteiro morria**:
18 documentos aprovados perdidos por causa de um.

O estrago não foi o erro; foi o que ele ensinou a quem operava. A mensagem não
dizia QUAL documento era, então a analista tomou o erro **oito vezes** entre
09:52 e 11:02 e concluiu que a culpa era dos campos obrigatórios. Desmarcou
**condições médicas**, **medicamento contínuo** e **contato de emergência**,
com o motivo `"por que não consigo salvar"` gravado na auditoria — que não é
justificativa, é um pedido de socorro digitado no campo errado. O erro continuou
depois de todos os ajustes: nunca teve relação nenhuma com aqueles campos.
Ficou uma pessoa em posto sem contato de emergência registrado.

**A saída já existia e a tela a escondia.** O dossiê parcial (`forcar=true`)
está no sistema desde sempre, com botão e tudo — mas o bloco que o oferece só
renderiza quando o erro é de PENDÊNCIA (`e.detail.pendencias`). O erro de
MONTAGEM cai em outro ramo do `catch`, `pendDossie` fica nulo, e **o botão nunca
apareceu**. É a regra da v2.87 (*"desativar em massa RECUSA oferecendo a saída,
nunca só o bloqueio"*) violada no lugar onde mais custava: recusar sem
alternativa manda quem opera procurar a saída sozinho, e ela procurou no
lugar errado.

O que mudou:

- **`dossie.py`**: cada peça entra por `_juntar`, que PULA a ilegível e a
  **NOMEIA**. O `except Exception: pass` que existia no ramo do
  multi-signatário foi eliminado junto — ele trocava "quebra ruidosamente" por
  "some caladinho", e página faltando num dossiê que circula para o cliente é
  pior que erro.
- **Nenhuma página ⇒ recusa** (`DossiePecasIlegiveis`), em vez de gravar um PDF
  de zero página POR CIMA do dossiê anterior com `dossie_gerado_em` dizendo que
  está pronto.
- **Peça pulada NÃO marca `aprovado`**: dizer que a conferência terminou sobre
  um documento que não entrou no PDF é a mentira que este módulo não pode
  contar. A mensagem de sucesso vira aviso e diz o que reenviar.
- **A tela oferece a saída nos TRÊS erros** (pendência, peças ilegíveis, falha
  não nomeada), não só no primeiro.
- **`test_dossie_pdf_ilegivel.py`** no CI, validado por **3 mutações** (voltar
  ao `except: pass`; remover o guard de PDF vazio; contar sem nomear) — as três
  reprovam.

⚠️ **Regressão pega pelo próprio CI, registrada porque a lição é geral**: a
primeira versão do guard recusava com zero página **sem olhar se houve falha**, e
quebrou o `test_entrevista_documentos` — que monta um candidato sem documento
nenhum e pede o parcial. **Dossiê vazio por AUSÊNCIA e vazio por CORRUPÇÃO dão o
mesmo total; o que os separa é ter havido falha de leitura.** Quem pede
`ignorar_pendencias` quer exatamente *"monte com o que houver"*, inclusive nada.
O guard virou `len(writer.pages) == 0 and ilegiveis`, e o teste ganhou o 4º caso
que faltava — a lacuna existia porque eu só havia coberto o caminho do defeito,
não o caminho legítimo que se parece com ele.

**Healthcheck da API** nos DOIS arquivos de deploy (a armadilha da v2.66: só num
deles não vale em produção). Usa **Python**, não `curl` — a imagem não tem curl
nem wget, e um healthcheck com curl marcaria o container como *unhealthy* para
sempre. Critério é só "a API responde": **`migracoes.em_dia` NÃO entra**, porque
reiniciar em loop por migration atrasada recriaria o incidente da v2.70, onde
schema velho no ar era melhor que tela morta.

## [2.92.0] — 2026-08-11 — A lista suspensa não é mais cortada, e o minutário mostra a mensagem

**A lista de papel saía pela borda** (defeito de campo, com print): o Bruno foi
trocar o papel da Fátima — a ÚLTIMA linha da tabela de usuários — e a lista
abriu para baixo, saindo pelo fim do card. A opção que decide o ACESSO da pessoa
ficava ilegível.

O `SelectBusca` abria com `top: calc(100% + 4px)` **fixo**, desde sempre. O § 5
do sistema de design já mandava o contrário — *"nada estoura a tela"* — e a
regra estava sendo violada em todo seletor perto do fim de um container; só não
tinha aparecido porque ninguém abrira uma lista na última linha de uma tabela.

Agora o painel MEDE o espaço abaixo do campo ao abrir e sobe quando não cabe.
Medir é necessário: media query não resolveria, porque o corte depende de ONDE
o campo está na página, não do tamanho da tela.

⚠️ **Por que as réguas existentes não pegaram**: `tabelas-cabem-na-tela` mede a
LARGURA da página, e overflow contido não alarga nada (v2.76.1). O que faltava
era medir a borda do painel ABERTO contra o container que o recorta — e isso só
existe com a lista aberta, o que nenhum teste fazia.
`lista-suspensa-nao-corta.spec.js` faz, na última linha (onde o espaço acaba;
testar na primeira passaria sempre). Validado por mutação: sem a correção, o
painel passa **114px** do fim da janela.

**Minutário: ver e copiar** (pedido do Bruno). Ler o texto de um modelo exigia
abrir "editar" — o que põe quem só queria conferir a um Enter de alterar um
modelo em uso. Agora cada linha tem **ver** e **copiar**, e o visualizador traz
o botão de copiar ao lado do texto: é ali que a pessoa está olhando quando
decide levá-la para o WhatsApp (a regra da distância, v2.47). O `<pre>` preserva
as quebras de linha — a mensagem que se cola tem a formatação que se lê. Se o
navegador recusar a área de transferência (contexto não seguro), o visualizador
ABRE com o texto à vista, em vez de falhar calado.

## [2.91.1] — 2026-08-11 — A função é o cargo, e a escala entra junto

Dois defeitos que o Bruno viu na primeira importação real.

**"A função está repetindo o nome."** A coluna Função mostrava *"Fátima
Sampaio"* onde deveria mostrar *"Assistente de RH Júnior"*. As colunas das abas
Matriz trazem PESSOAS, e o importador criava uma função com o nome de cada uma
— enquanto o par pessoa→cargo estava pronto na aba **Legenda e Regras**, que eu
não estava lendo.

Não era um defeito estético: o módulo inteiro se apoia em *"a titularidade
acompanha a função, não a pessoa"*, e com a função chamada "Fátima Sampaio"
trocar quem ocupa o cargo exigiria renomear a própria função — exatamente o
trabalho que o módulo existe para evitar.

**"Não apareceu a escala de rodízio diário."** A aba *Escala Diária* tem 5
postos (Demandas, E-mail, Teams, WhatsApp, Retaguarda) girando entre a equipe
num ciclo de 4 semanas, por cenário — **200 linhas** que eu simplesmente não
importava. É ela que responde pelos processos 9.1 e 9.2, então a tela dizia
"Escala do dia" sem saber dizer QUEM: justamente a informação que se procura ao
abrir a carteira numa terça-feira.

Agora a escala entra na mesma importação e aparece na tela, com as quatro
semanas (a primeira aberta, as demais recolhidas) e os postos lidos do
cabeçalho da planilha — não de uma lista fixa no código, que descartaria em
silêncio um canal novo.

Validado por mutação contra o arquivo real: voltar a usar o nome da pessoa como
função e deixar de ler a aba de escala. Ambas reprovam nomeando o defeito.

## [2.91.0] — 2026-08-11 — Carteira de Processos: quem responde quando alguém sai

O módulo que o Bruno pediu: *"caso haja algum funcionário substituído, indo
embora do RH ou qualquer outra coisa, tenha uma organização de processos"*.

A carteira dele (31 processos em 9 fases, dois cenários de efetivo) entra pela
**importação da planilha RACI**, com prévia e confirmação — nada de digitar de
novo, e a planilha continua servindo de referência. Reimportar ATUALIZA: a
carteira é revisada por trimestre, e importação que duplica a cada revisão
inutilizaria o módulo em três meses.

**A titularidade é do CARGO, não da pessoa** — decisão do Bruno, e o próprio
documento dele já dizia: *"a titularidade dos processos acompanha a função, não
a pessoa"*. É isso que faz o módulo responder à pergunta que a planilha não
responde: **ao esvaziar quem ocupa uma função, os processos dela passam na hora
para o próximo da cadeia**, sem ninguém redistribuir nada. A tela mostra titular
e "responde hoje" lado a lado, com a marca "assumiu" quando são diferentes.

O que a planilha não conseguia dizer, e agora aparece sozinho:

- **Processo sem dono** — ninguém da cadeia está ocupado. É o defeito que a
  carteira existe para impedir, e é silencioso: processo órfão não reclama.
- **Cadeia curta** — uma pessoa só. Pesa mais nos ritmos críticos: a CAT tem
  prazo legal contado em HORAS.
- **Carga por função**, com titularidade e apoio SEPARADOS: são naturezas
  diferentes (quem é dono responde por prazo; quem apoia entra quando chamado),
  e somar num número só esconderia o que a Coordenação usa para redistribuir.

**Dois casos da planilha real que o código trata explicitamente**: os processos
9.1 e 9.2 têm "Escala diária (rodízio)" como titular — não são órfãos, giram
entre a equipe, e acusá-los seria alarme falso (alarme falso ensina a ignorar o
alarme). E o 9.3 (Indicadores) existe SÓ no cenário 2, porque nasce com o
Analista Jr: a tela diz "previsto para o outro cenário", que é a resposta de
dimensionamento, não um erro.

⚠️ **Defeito pego contra a planilha real**: a coluna do titular se chama
"Titular (Dono)", e o parser a procurava por igualdade exata — ela caía fora, a
cadeia começava no 2º apoio e todo processo aparecia com o titular ERRADO, sem
erro nenhum. Só apareceu ao conferir que o 1.1 deveria ser da Fátima. Casamento
por PREFIXO resolveu.

Validado por mutação contra o arquivo real: a cadeia que para no titular e o
rodízio voltando a ser acusado de órfão — ambas reprovam nomeando a
consequência.

## [2.90.0] — 2026-08-10 — Os textos dos documentos passam a ser da empresa

Segunda parte do item do P1: *"tornar os demais documentos editáveis, conforme o
caso"* — com a ressalva que o próprio Bruno cravou: *"os que já foram assinados,
obviamente que não"*.

O que passou a ser editável em Configurações → Modelos → **Textos dos
documentos**: a lista de **direitos do trabalhador** (que sai no ofício da
INFRAERO e nas fichas de integração) e os quatro **ciclos de pagamento** — VT e
VA, por regime. São os textos que mudam por decisão da empresa ou por mudança de
norma, e que até aqui exigiam deploy.

**O layout continua fora do alcance**, como decidido: formulário oficial tem
campos posicionados, tabelas e loops (a ficha cadastral tem 49 chamadas de
campo), e virá-lo texto destruiria o papel. Para os 12 documentos que não são
texto corrido vale a escolha do Bruno: *"só a data e os dados; o layout fica"*.

Três garantias que sustentam isso:

1. **Documento assinado não muda.** O `hash_sha256` do ato foi calculado sobre
   aquele PDF, gravado no MinIO; quem assinou carrega a via que leu. Editar aqui
   muda o que SERÁ gerado daqui em diante — é o que mantém o `/verificar`
   batendo.
2. **Vazio volta ao padrão de fábrica.** Sem registro, com texto em branco ou
   com erro de leitura, vale a constante do código, e `texto()` nunca levanta:
   documento é papel que a pessoa assina, não pode deixar de sair porque a
   consulta de configuração falhou (a regra do `avisar()`).
3. **A fonte continua ÚNICA.** O corpo que o RH copia para criar um modelo
   (`documentos_texto.py`) lê o MESMO texto que o gerador do PDF — editar muda
   os dois juntos. Duplicar faria a amostra divergir do documento oficial, que
   é o defeito da v2.19 (a cópia à mão perdeu 6% do VT e 8% do FGTS).

Validado por duas mutações: o gerador voltando a ler a constante (a edição não
teria efeito no papel) e o corpo copiável voltando a ela (a amostra divergiria
do oficial). Ambas reprovam nomeando a consequência.

⚠️ Achado ao escrever o teste: a primeira asserção conferia que a frase antiga
sumira do PDF — e ela CONTINUAVA lá, corretamente, porque pertence ao
vale-ALIMENTAÇÃO, outro bloco. Ao afirmar sobre ausência num documento longo,
confira a que seção o trecho pertence.

## [2.89.1] — 2026-08-10 — O cadastro de talento que recusava sem dizer por quê

Defeito de campo, com o log em mãos: não dava para cadastrar talento à mão.
`StringDataRightTruncation` numa `varchar(60)` com **106 caracteres** —
"Técnico em Secretariado / Secretário Executivo; Inglês avançado (cursando,
Centro de Idiomas de Ceilândia)".

**Eram dois defeitos, e o segundo é o pior.**

A coluna `talento.escolaridade` nasceu dimensionada para o formulário PÚBLICO,
onde a escolaridade sai de uma lista curta ("Ensino médio completo"). No
cadastro pelo RH o campo é texto livre, e o real não cabia. Passou para 300.
**Coluna dimensionada para o caminho de entrada mais estreito quebra no dia em
que aparece o outro** — e neste sistema quase todo dado tem dois caminhos
(público × RH, wizard × importação).

Mas o que fez a pessoa perder a tarde foi o resto: o erro virava **HTTP 500 em
texto puro**. A tela dizia "não foi possível" e o RH refazia o cadastro inteiro
**sem saber qual campo encurtar** — de novo a família do "não salva e não diz o
motivo" (v1.96). Agora é 422 dizendo o campo, o limite e o tamanho recebido, com
os limites lidos do PRÓPRIO modelo (`Talento.__table__`): repetir os números à
mão faria a mensagem envelhecer torto na primeira migration que alargasse uma
coluna, e "máximo 60" onde já cabem 300 é pior que não dizer nada.

O `except DataError` vem **antes** de `registrar()`, que faz `flush()` e deixaria
a sessão em rollback pendente — o erro real ficaria escondido atrás de um
`PendingRollbackError` (a armadilha que o CLAUDE.md já registra).

O `downgrade` da migration **recusa** voltar a 60 se houver texto maior, em vez
de truncar em silêncio: dado de gente real não se perde num rollback.

Coberto por `test_talento_campos_longos.py`, com o texto REAL que falhou, e
validado por mutação (tirar o `except` faz o teste reprovar dizendo que voltou
o 500).

## [2.89.0] — 2026-08-10 — A data do papel é a do ato, não a da impressão

Primeira parte do item que faltava do P1: **a data dos documentos**.

Ao abrir o código, o diagnóstico mudou o escopo. Os geradores já resolviam a
data como `assinatura.assinado_em if assinado else date.today()` — ou seja,
**documento assinado já carregava a data do ato**, congelada. O `date.today()`
só valia para não assinados, e era recalculado a cada download: quem gerasse o
papel na quarta veria a data de quarta, ainda que a integração fosse de segunda.

Agora `Candidato.data_documentos` define a data que os documentos **não
assinados** daquela pessoa carimbam. Nula = o dia da geração, o comportamento
anterior. O campo fica na ficha, ao lado do informativo de integração — é ali
que se decide o que a pessoa vai assinar.

**A regra virou uma função só** (`fichas.data_do_documento`), com precedência
explícita: assinatura > escolha do RH > hoje. Eram **sete cópias** do mesmo
`assinado if ... else date.today()` espalhadas pelos geradores; bastaria uma
passar despercebida para o mesmo candidato ter dois documentos com datas
diferentes no mesmo dossiê, sem nada na tela denunciando.

**Documento assinado não muda, e não tem como mudar**: o `hash_sha256` do ato é
calculado sobre o PDF, e todo manifesto emitido aponta para ele. Se a data
configurada vazasse para um assinado, o PDF deixaria de se reproduzir e a
verificação passaria a acusar divergência — na peça que se usa em disputa
trabalhista, sem nada na tela denunciando. A resposta da rota **diz quantos já
estão assinados**, para o RH não achar que a correção alcançou o dossiê inteiro.

Data futura é recusada (422): quase sempre é o ano digitado errado, e documento
datado do futuro é papel que não se sustenta.

**Dois defeitos pegos por medir, não por ler o código**: (1) a mensagem da tela
mostrava **02/08 para uma data salva como 03/08** — `new Date("2026-08-03")` é
lido como UTC meia-noite e, convertido para São Paulo (UTC-3), volta um dia; o
banco estava certo o tempo todo. Data PURA se converte por texto (`isoParaBR`),
nunca por `Date`. (2) A primeira versão do teste procurava a data em `pages[0]`
e acusou "não encontrada" num PDF **correto** — ela fica na página 3.

Validado por duas mutações: tirar a precedência da assinatura e ignorar a data
escolhida. Ambas reprovam nomeando a consequência.

Fica para a próxima leva a segunda parte do item: editar os CAMPOS do corpo dos
documentos. Decisão do Bruno para os 12 que não são texto corrido (formulários e
híbridos): **só data e dados; o layout fica** — formulário oficial tem campos
posicionados, tabelas e loops, e virá-lo texto editável destruiria o papel.

## [2.88.0] — 2026-08-10 — Dá para voltar

Três feedbacks de campo do dia 10/08, mais a pendência que ficou da v2.86.

**"Estava escrevendo o endereço e não conseguiu mais voltar para editar."** O
mais grave dos três, e o diagnóstico surpreendeu: **o backend sempre permitiu** —
`_candidato_do_token` só barra `expurgado` e `aprovado`. Quem não oferecia o
caminho era a TELA: depois de confirmar os dados, o app ia para a assinatura e
não havia porta de volta; reabrir o link caía direto lá de novo. Agora existe
"← Preciso corrigir meus dados antes de assinar", ao lado do botão de assinar —
é ali que a pessoa relê o que preencheu e percebe o erro, e um link no rodapé
seria achado depois de ela já ter assinado. Só antes da assinatura: documento
assinado é peça de prova, e corrigir depois é o RH quem reabre. Não aparece em
reassinatura, onde os documentos vieram do RH e o formulário não é o que se
corrige.

**Nome social: pergunta antes do campo.** *"Tem pessoas preenchendo sem
necessidade."* O campo existia vazio ao lado dos outros — e campo vazio num
formulário de admissão parece coisa a preencher, então as pessoas repetiam ali o
nome civil. A explicação existia, mas só no tooltip, e `title` não abre no
celular (v2.77), que é onde o candidato preenche. Agora: *"Você usa nome
social?"*, padrão **Não**, e o campo aparece só ao responder Sim. O texto afirma
o direito (Decreto 8.727/2016) em vez de pedir justificativa — a pergunta é
sobre COMO a pessoa quer ser chamada, não sobre quem ela é. Responder "Não"
LIMPA o que estiver escrito: valor guardado que a tela não mostra sairia nos
documentos que a pessoa assina sem ela ver, e o wizard salva a cada 900ms.

**O quadro "o que é obrigatório para esta pessoa" em colunas.** São ~12
documentos e ~12 campos; em coluna única, uma rolagem longa para conferir o que
cabe numa tela. `auto-fit` + `minmax` faz a contagem sair da largura, não de
media query: **4 colunas em 1440px, 3 em 1150px, 1 em 390px** — e continua certo
dentro do painel estreito onde o bloco vive. ⚠️ **`min-width: 0` não bastou**: o
`.campo-check` é `white-space: nowrap`, então "Certidão de nascimento do
dependente" mediu **303px numa coluna de 246px** e foi impresso POR CIMA da
coluna vizinha. Enquanto o `nowrap` valer, não há onde quebrar. Só apareceu no
PRINT — o teste de largura passava, porque overflow contido não alarga a página
(v2.76.1).

**Pendência da v2.86 fechada**: o menu do painel agora esconde o que a pessoa
não pode. Cada item declara a permissão da tela que abre; grupo sem item visível
não deixa o título órfão. Medido: superadmin vê 18 itens, gestor vê 5, recepção
vê 0 — e **menu vazio DIZ que está vazio**, porque barra em branco parece
sistema quebrado e a pessoa liga achando que não carregou. Esconder é cortesia,
não segurança (quem protege é o `exige` de cada rota); o motivo de fazê-lo é que
botão que sempre responde 403 ensina a equipe a ignorar mensagem de erro.
Enquanto as permissões carregam — ou se a consulta falhar — o menu aparece
INTEIRO: erro de rede não pode parecer perda de acesso.

Fica para leva própria, por decisão do Bruno: tornar editáveis as datas e os
campos dos documentos gerados (21 pontos de `date.today()`, 15 documentos no
catálogo). Os **já assinados ficam intactos** — o hash é calculado sobre o PDF e
é o que prova que ninguém alterou depois da assinatura.

## [2.87.1] — 2026-08-10 — Duplicar em postos, vagas, modelos e minutário

Replica o padrão da v2.87 nos quatro cadastros que o Bruno marcou. Em todos, a
cópia nasce **sem valer** (inativa) — a exceção é o modelo de documento, que não
tem campo de ativação e por isso já é inofensivo até ser apontado a um alvo.

O que **não** se copia, e por quê:

- **`PostoServico.tirvu_id`** — é a chave com que a planilha de Postos do Tirvu
  casa o cadastro. Dois postos com o mesmo ID fazem a importação atualizar o
  posto ERRADO, em silêncio, porque ela casa por ID e não tem como saber qual
  dos dois é o certo. O `documentos_kit` e o creche, ao contrário, VÃO junto:
  são o trabalho de verdade, e posto sem kit significa gente admitida sem
  assinar o termo de VT.
- **O alvo do modelo de documento** (cargo, posto ou pessoa) — herdá-lo cria
  dois modelos disputando o mesmo destino, com `modelos-aplicaveis` devolvendo
  os dois e ninguém sabendo qual vale. Duplicar existe justamente para apontar
  a variação a outro alvo.
- **As análises de match da vaga** — são por (vaga, talento) e descrevem o
  julgamento feito para AQUELA vaga. Trazê-las daria um ranking pronto para uma
  vaga cujos requisitos ainda vão mudar: pareceria analisado sem ninguém ter
  analisado.

Já as **tags do minutário** vão junto: classificam a que assunto o modelo serve,
e a cópia serve ao mesmo — sem elas, a cópia sumiria dos filtros onde o original
aparece e alguém a daria por não criada.

**Defeito corrigido de passagem**: o "duplicar" de modelos de documento já
existia, mas era feito NO CLIENTE, remontando o payload — e copiava o alvo
(`cargo_alvo`, `posto_alvo_id`, `candidato_alvo_id`), produzindo exatamente os
dois modelos concorrentes descritos acima. Agora aponta para a rota dedicada.

`test_duplicar.py` entra no CI, validado por quatro mutações: posto herdando o
`tirvu_id`, posto perdendo o kit, vaga nascendo ativa e modelo herdando o alvo.

## [2.87.0] — 2026-08-10 — Duplicar, ajustar, então ativar

Pedido do Bruno olhando a tela de papéis, e cravado como **padrão** para o que
vier: *"a possibilidade de duplicar um existente e, a partir dessa duplicata,
editarmos o que tiver que editar para daí sim ativarmos"*.

Duplicar já existia em quatro lugares (provas, questões, roteiros de entrevista
e documentos do sistema) — só não era regra. Agora é: todo cadastro reusável
ganha `POST .../duplicar`. Quem começa numa tela em branco com 40 caixas de
permissão tende a marcar demais (para a pessoa "não ficar travada") ou de menos,
e o erro só aparece depois, no uso. Partir de um papel que já funciona é mais
seguro do que montar do zero.

**A cópia nasce INATIVA** — diferente do `duplicar` de provas, que herda
`ativa=p.ativa` e por isso já vale no instante em que é criada. Num papel isso
seria conceder acesso antes de alguém revisar o que ele concede. Segue a
semântica do roteiro de entrevista, cuja cópia nasce em rascunho.

**Ativar e desativar** (`papel.ativo`): papel inativo existe, aparece na tela e
**não concede nada**. Serve à cópia em ajuste e ao papel aposentado, que se
guarda em vez de excluir — excluir apagaria o registro de que ele existiu, e a
auditoria antiga passaria a citar um papel que ninguém mais encontra. A checagem
mora em `permissoes_do_usuario`, não na tela: esconder o botão deixaria a rota
respondendo 200 a quem souber a URL.

**Desativar papel EM USO recusa oferecendo a saída.** Foi o aprimoramento que o
Bruno pediu sobre a proposta original: recusar é seguro, mas deixa quem opera
com o problema na mão — teria de sair da tela, conferir os papéis um a um e
voltar. Agora o 409 vem com os **destinos possíveis e o que cada um concede**, e
a rota aceita `migrar_para`: as pessoas são movidas e o papel é desativado **no
mesmo ato**, sem a janela em que ficariam num papel que já não vale. A auditoria
registra para onde cada uma foi — "por que a Fátima está como RH?" é a pergunta
que se faz depois, e o estado final não a responde.

Três armadilhas pagas na implementação: a cópia do superadmin precisa
materializar o catálogo INTEIRO (ele guarda lista vazia porque `pode()` não a
consulta — copiar o campo cru daria um papel que não concede nada com o rótulo
dizendo o contrário); a chave se resolve por sufixo incremental (`rh-copia-2`)
porque é `unique`; e migrar para um papel inativo é recusado, senão o destino
recriaria o mesmo problema.

**Validado por três mutações**, cada uma reprovando com a mensagem do defeito
real: papel inativo voltando a conceder ("veio 200 — desativar não está cortando
o acesso de fato"), cópia nascendo ativa e migração que não move ninguém ("a
pessoa não foi migrada — desativar teria cortado o acesso dela em silêncio").

## [2.86.1] — 2026-08-10 — O admin do .env nascia sem poder gerir papéis

O CI pegou o que a máquina de quem desenvolve escondeu. O primeiro
administrador nasce por **duas portas** que dividem o mesmo portão ("a tabela
está vazia"): a tela de primeiro acesso e o `.env` (provisionamento
automatizado, `core/bootstrap.py`). A v2.86.0 acertou o papel só na primeira, e
a segunda caía no default `rh` — que não tem `config:escrever` nem
`config:usuarios`.

O resultado seria uma instalação provisionada **sem ninguém capaz de gerir
papéis**, e sem tela para corrigir, porque `config:usuarios` é justamente o que
falta. Localmente passou (o banco de desenvolvimento não tinha o admin do
`.env`); no CI, o `test_email_templates` levou 403.

Junto: o `preparar_ambiente_local.py` passou a corrigir o papel inclusive de
usuário ANTIGO — banco local anterior à v2.86 responderia 403 em metade das
telas, e o sintoma apareceria como defeito de layout (a confusão da v2.60).
Quatro testes que criam `UsuarioRH` ganharam `papel`: os que usam
`dependency_overrides[requer_rh]` seguem valendo (o `exige` depende dele), mas
o objeto sem papel faz `permissoes_do_usuario` devolver conjunto vazio e negar
tudo.

## [2.86.0] — 2026-08-10 — Nem todo mundo pode tudo

Até aqui o painel respondia UMA pergunta na porta: *"está logado?"*. O
`requer_rh` era a única proteção de **476 rotas**, então quem entrasse podia
efetivar, desligar em lote, exportar a base com 1.171 CPFs, baixar a trilha de
auditoria e **criar outro administrador**. Não havia degrau entre consultar a
lista de candidatos e apagar a pessoa.

Isso passou a doer agora porque os módulos de Processos e Recepção (próximas
levas) trazem para dentro do sistema gente que **não é do RH** — o gestor que
avalia a própria equipe, a recepcionista que anuncia visita. Dar a essas pessoas
a chave que o Coordenador tem hoje não era opção, e a mudança fica mais cara a
cada módulo novo.

**O que foi feito**

- **Catálogo de 40 permissões** (`services/permissoes.py`), com o eixo na
  NATUREZA DO ATO, não no arquivo. Um `GET` que devolve a base inteira com CPF
  é `dados:exportar_base` e não `colaboradores:ler` — é assim que a LGPD o
  enxerga, e é o que separa "abrir a ficha da Maria" de "levar 1.171 CPFs para
  fora". As 14 permissões que não se desfazem sozinhas ficam marcadas como
  sensíveis, e a tela conta quantas cada papel tem.
- **362 rotas `/rh/*` declaram a permissão que exigem.** Os 19 routers com
  `dependencies` global eram todos-ou-nada: `colaboradores.py` cobria com a
  MESMA dependência o `GET` que lista e o `POST .../desligar`.
- **5 papéis de fábrica** — superadmin, admin, RH, gestor e recepção —, todos
  editáveis pelo painel (Configurações → 🔑 Papéis e permissões), mais os que o
  superadmin criar. O `admin` é tudo **menos** `config:usuarios`: quem
  administra o sistema não escolhe quem entra nele, senão "admin" e "superadmin"
  seriam o mesmo papel com dois nomes — e o segundo poderia se promover ao
  primeiro.

**Três decisões que sustentam o desenho**

1. **Rota sem permissão declarada é REPROVADA no CI**, não liberada por padrão
   (`test_permissoes_declaradas.py`, stdlib pura). Com default aberto, "ainda
   não declarei" e "decidi que é livre" ficariam indistinguíveis no código, e a
   diferença só apareceria no dia em que alguém achasse a URL. As 9 isenções
   legítimas (perfil próprio, login, callbacks OAuth) estão listadas **com
   justificativa** — não há terceira opção.
2. **O superadmin IGNORA a checagem**, em vez de ser um papel com todas as
   caixas marcadas. Se fosse lista, cada módulo novo nasceria DESMARCADO para
   ele, e o dono do sistema descobriria isso levando um 403 na própria casa. É o
   que faz módulo novo nascer 100% liberado sem ninguém precisar lembrar.
3. **Papel que não resolve devolve conjunto VAZIO, que nega.** Cair num padrão
   permissivo faria um papel quebrado (removido, escrito errado numa migration)
   passar por administrador — e o sintoma seria acesso a MAIS, que ninguém
   reporta.

**A migration promove todo usuário existente a superadmin — de propósito.**
Rebaixar no deploy tiraria acesso de quem estava no meio de uma admissão, sem
aviso e sem ninguém para reconceder (o único que poderia também teria sido
rebaixado): a instalação ficaria travada por fora. Segurança que chega quebrando
o trabalho é revertida às pressas, e o que fica é nenhuma segurança. O degrau
real acontece na TELA, onde se vê o que cada papel concede — decisão de quem
conhece a equipe, não de uma migration adivinhando por e-mail.

**Travas que impedem fechar a porta por dentro**: o papel `superadmin` não se
edita, papel de fábrica não se apaga, papel em uso não se exclui (o 409 diz
quantas pessoas seriam afetadas) e rebaixar/desativar o ÚLTIMO superadmin é 422
— sem isso, ninguém mais conseguiria gerir papéis, e não há tela para desfazer.

**Validado por mutação**: remover o `exige` da rota de desligar faz
`test_permissoes_efeito.py` reprovar com a mensagem certa — *"404 significa que
a autorização passou"*. Sem essa asserção, a recepcionista poderia desligar
colaboradores. As 10 asserções afirmam sobre o MOTIVO do 403 e sobre o ESTADO do
banco, não só sobre o status code (lições da v2.80 e v2.84).

**Dois defeitos de colisão pegos pelos próprios guarda-corpos**: já existia um
componente `Papeis` (papel com que se ASSINA um documento) e as chaves
`papeis`/`criarPapel`/`editarPapel` no `api.js` — chave repetida em objeto
literal sobrescreve a anterior **em silêncio**, e três telas (Config, Modelos,
RoteiroAssinatura) passariam a chamar a rota errada com o build passando.
Renomeados para `PapeisAcesso`/`papeisAcesso*`. O `test_design_system` ainda
pegou uma classe fantasma (`rh-conferencia-bloco`) e um token inexistente
(`--aviso`) na tela nova.

## [2.85.1] — 2026-08-08 — A métrica vira fila no celular

O CI reprovou a v2.85 na régua de mobile: em **Admissões a primeira linha só
começava em 639px**, contra o teto de 600px.

**A causa não era a fonte.** Medida a diferença de altura entre Yu Gothic, Noto
Sans JP e Outfit no mesmo texto: **1px**. O que a fonte fez foi empurrar uma
tela que já estava a 8px do limite — aqui ela media 592px, e no CI, com dados
diferentes, um rótulo a mais quebrando em duas linhas bastou.

A causa real estava desde a v2.76: **oito cards de métrica em duas colunas são
quatro fileiras** — 275px de cabeçalho antes da lista, com altura que variava
conforme o rótulo mais longo. Um número diferente no banco mudava o layout.

No celular eles viram uma **fila que rola de lado**: uma fileira só, altura
previsível. Admissões caiu de **592px para 384px**, e as outras cinco telas
melhoraram junto.

Rolar métrica de lado é aceitável porque **métrica é consulta**. A regra "nunca
esconder AÇÃO" (v2.76.1) continua valendo: a `.dash-acoes` segue inteira na tela.

O terceiro card aparece cortado na borda de propósito — é o que sinaliza que há
mais para o lado, em vez de a fila parecer terminada.

A régua de vazamento lateral ganhou a mesma isenção que o `.dash-scroll` já
tinha: o conteúdo fica fora da VISTA, não fora da PÁGINA (`body.scrollWidth`
continua igual à viewport).

E2E **30/30**.

---

## [2.85.0] — 2026-08-08 — A fonte é sua

> *"quero que todas as fontes, de maneira global, seja Yu Gothic regular por
> padrão, mas que possa ser customizado em Configurações, dentro da aba
> Identidade visual. não precisa alterar a fonte dos documentos, apenas do
> sistema."*

### Yu Gothic é proprietária — e isso muda o desenho

Ela vem no Windows e no macOS, mas **não pode ser redistribuída**: não existe no
Google Fonts nem no Fontsource, e embutir o `.ttf` do Windows num repositório
público seria violação de licença. Declará-la sozinha faria o RH ver Yu Gothic e
o candidato no celular ver a fonte genérica do aparelho — sem nada avisando.

Então ela vem **acompanhada da Noto Sans JP**, que é livre, tem a mesma origem
tipográfica e pesa ~13KB no subconjunto latino. Windows e macOS usam Yu Gothic;
Android, iPhone e Linux caem na Noto — parecida o bastante para a troca não
saltar aos olhos.

### O seletor tem lista, não campo livre

Cinco fontes em **Configurações → Identidade visual**, cada uma com a cadeia de
alternativas pronta no servidor: Yu Gothic (padrão), Outfit (a original),
Noto Sans JP, fonte do aparelho e Georgia.

A pilha escolhida vira o `--fonte` de **toda tela**, inclusive as públicas —
texto livre deixaria gravar CSS arbitrário, e **fonte que não existe não dá
erro**: a tela só fica estranha, sem nada apontando a causa. Fora do catálogo é
422. Uma prévia mostra o resultado antes de salvar, com negrito, porque fonte se
confere olhando e não lendo o nome.

### A rota é pública, senão vale só metade

O wizard do candidato não tem login e é a maior parte do uso. Sem
`GET /marca/aparencia` público, a customização valeria no painel e não valeria
para quem está enviando documento pelo celular.

### Os documentos não mudam

Limite explícito do pedido, e há razão técnica: o PDF é gerado pelo fpdf2 com
fontes próprias, e o **hash do ato de assinatura** é calculado sobre ele —
trocar a fonte faria manifesto já emitido apontar para um arquivo que não se
reproduz. O teste varre os geradores e reprova se algum passar a ler a config.

### Dois defeitos achados no caminho

**O `body` repetia a pilha literal** em vez de usar `var(--fonte)`. Trocar só o
token deixaria a fonte valer em tudo **menos no texto corrido** — o defeito mais
difícil de enxergar, porque a tela muda "quase toda".

**`--bg-suave` não existia.** Usei o token na prévia e a conferência acusou:
token fantasma cai no fallback e a tela fica plausível, com a cor errada nos dois
temas (v2.46).

### Usuário padrão para testes locais

> *"para os testes locais, deixe um user e senha padrão, para não perdermos mais
> tempo."*

`criar_admin_inicial` só cria o admin do `.env` com a tabela **vazia** — em banco
de desenvolvimento com usuários antigos aquele e-mail não existe, e o 401 aparece
como `KeyError: 'token'` ou "senha errada". Custou três diagnósticos no mesmo
dia. `tests/preparar_ambiente_local.py` cria (ou redefine)
`teste@exemplo.com.br` / `senha-teste-123`, e recusa rodar com
`ENVIRONMENT=production`.

Fica documentado junto que a suíte de tela precisa de **`--workers=1`**: em
paralelo ela estoura o rate limit do login e as falhas parecem defeito de layout.

### Portões

26 verificações, 3 mutações. **A primeira versão do teste tinha um furo**: a
asserção do `body` casava com o `var(--fonte)` escrito no comentário que EXPLICA
a regra, e passava verde com a pilha literal de volta — a armadilha da v2.71,
teste que aprova a própria documentação. Corrigido removendo comentários antes
de afirmar. Conferido na tela: painel inteiro em Yu Gothic, seletor com prévia.
E2E **30/30**.

---

## [2.84.1] — 2026-08-08 — A asserção do autor lia o e-mail literal

O CI reprovou no `test_email_templates`. A v2.84 trocou o e-mail dos testes por
um genérico, e quatro asserções comparavam com a **string**, não com a variável
de ambiente — sendo que `_EMAIL = os.environ["RH_ADMIN_EMAIL"]` já existia dez
linhas acima, e é com esse admin que o teste faz login e edita o template.

No CI o administrador nasce com o e-mail do `.env` do job, então
`atualizado_por` vinha dele e a comparação falhava.

É a armadilha da v2.71 — *"senha literal em teste o amarra a UM banco"* — na
variante do e-mail: a v2.84 só mudou **qual** string estava chumbada, sem tirar
o problema. As quatro passam a usar `_EMAIL` e a informar o valor recebido na
mensagem de erro.

Os outros doze testes do CI que ainda citam o endereço foram conferidos um a um:
são todos `os.environ.setdefault`, que o job sobrescreve.

Validado como manda a regra e como faltou na v2.84: **banco novo dentro do
container**, com o admin do job. Os 16 testes do bloco mais o do primeiro
acesso, todos verdes antes do push.

---

## [2.84.0] — 2026-08-08 — O sistema não sabe mais quem é você

> *"o e-mail exposto na documentação é o rh@greenhousedf.com.br, ou seja, esse
> e-mail é real. Está deixando um ponto de vulnerabilidade exposta no
> repositório do GitHub. Quero que tire isso agora e mais: coloque um cadastro,
> tipo guiado, onde no primeiro acesso ali sejam coletados os dados e criados os
> dados cadastrais (…) mas lembre que é somente para o primeiro acesso."*

### O e-mail saiu — mas o conserto não é apagar texto

O endereço real aparecia em **46 arquivos versionados**, e trocá-los todos seria
tratar o sintoma: enquanto o primeiro administrador nascer do `.env`, sempre
haverá um e-mail e uma senha escritos em arquivo, e o `.env.example` sempre
sugerirá *algum* endereço. A causa é o admin vir de configuração.

Agora, **com o banco sem nenhum usuário, o painel abre um cadastro guiado**:
nome, e-mail, senha (com repetição), e entra direto — a pessoa acabou de
escolher a credencial, pedir que a digite de novo é só mais um passo para errar.

`RH_ADMIN_EMAIL`/`RH_ADMIN_PASSWORD` continuam existindo para instalação
automatizada, mas saíram do `.env.example` como caminho recomendado. As duas
portas dividem o mesmo portão — *a tabela está vazia* —, então não se atropelam.

### O portão é o banco, não a tela

As duas rotas novas são **públicas por necessidade**: não há quem autentique
antes do primeiro usuário existir. O que separa "instalação nova se
configurando" de "qualquer um cria administrador na produção" é uma única
checagem no servidor. Criado o primeiro, a consulta passa a dizer `false` e a
criação responde **409** — para sempre.

É por isso que o teste afirma sobre o **estado do banco**, não só sobre o status
code: a mutação que remove o portão devolveu 200 **e criou um segundo usuário**,
e as duas asserções reprovaram. Com o gate fora, a tela continuaria idêntica —
o defeito só apareceria no dia em que alguém encontrasse a rota.

### Limpeza do endereço

| Onde | O que era | O que ficou |
|---|---|---|
| `.env.example`, `config.py` | `rh@greenhousedf.com.br` | vazio / `seudominio.com.br` |
| `ci.yml` e 32 testes | credencial do banco efêmero | `admin@exemplo.com.br` |
| Placeholders de tela e exemplo | endereço real | exemplo genérico |
| **Documentos** (rodapé, termo LGPD, contato do DP) | — | **mantidos**, por decisão |

O último ponto é conteúdo público legítimo da empresa. Ficou combinado tirá-lo
do código numa próxima leva, lendo da configuração — inclusive nos documentos.

**Achado no caminho:** `EmailStr` **recusa o TLD `.local`** (não é domínio
público). A primeira troca usou `admin@exemplo.local` e teria quebrado o CI com
um 401 — que apareceria como "senha errada", apontando para o lugar errado.

### De quebra: uma regra de senha, não quatro

`len(senha) < 8` estava copiado em quatro rotas. Virou `exigir_senha_forte()`.
Regra repetida envelhece torto: basta alguém endurecer num ponto para haver duas
políticas no mesmo sistema — e a mais fraca é a que vale, porque é por ela que
se cria o usuário.

### Portões

19 verificações, 3 mutações (portão removido, consulta sempre `true`, senha sem
validação), todas reprovaram. Rodado **dentro do container** antes de entrar no
CI, onde ganhou banco próprio — o banco principal do job já tem admin, e lá o
fluxo não existiria. Fluxo conferido na TELA, com prints: cadastro, senha
divergente, entrada no painel e o login normal de volta depois. Smoke 15/15.

---

## [2.83.1] — 2026-08-08 — A empresa também vai por nome

> *"para empresa deve usar a informação da coluna razao_social, não o ID."*

A v2.83 trocou posto, cargo e jornada para texto e **deixou a Empresa como
`"1"`** — ela era fixa desde julho e não parecia parte da virada. Era.

Agora sai a **razão social**. O valor continua sendo um padrão (o grupo opera com
uma empregadora só, e por isso Empresa segue fora das pendências), mas quem tem
`empresa_id` na ficha usa a razão social **daquela** empregadora: se um dia
houver uma segunda — Nossa Cozinha já foi citada —, o export acerta sozinho em
vez de carimbar Green House em todo mundo. Esse é o tipo de erro que não dá erro.

`EMPRESA_TIRVU_ID = "1"` deu lugar a `EMPRESA_RAZAO_SOCIAL_PADRAO`.

2 mutações, ambas reprovaram: voltar ao `"1"` e ignorar o vínculo. O caso do
padrão passou a usar `empresa_id=None` — antes o candidato do teste tinha
vínculo, e a asserção teria passado pelo caminho errado.

---

## [2.83.0] — 2026-08-08 — O Tirvu voltou a falar por nome

> *"o que eu preciso que esteja na planilha de exportação para o tirvu é a
> informação da coluna nome (…) na coluna de descrição da jornada, vá a
> informação da coluna descrição (…) a de cargos também mudou, não é mais sobre
> o id do cargo, é sobre o nome do cargo mesmo."*

### Uma reversão consciente

Em **2026-07-24** o feedback foi o oposto: colar o texto fazia o Tirvu gravar
**zero**, e o export passou a escrever o `tirvu_id` nas três colunas. A decisão
ficou gravada no código, no `CLAUDE.md` e na memória do projeto.

O Tirvu mudou. O Bruno **testou uma importação com o texto direto na célula** e
ela foi aceita — nas três colunas, inclusive Cargo, que agora casa pelo nome e
não mais pelo id. Sem esse teste, a troca não teria sido feita: o modo como esse
erro se manifesta é traiçoeiro (a planilha entra e o vínculo nasce zerado, sem
reclamação), então a palavra de quem viu a importação passar é o que decide.

| Coluna | Antes | Agora |
|---|---|---|
| Posto de Serviço | `posto.tirvu_id` (`59`) | `posto.nome` (`ANAC - 14/2026 - SEDE`) |
| Cargo | de-para `CargoTirvu` (`50`) | `cargo_funcao` (`AUXILIAR DE SERVIÇOS GERAIS`) |
| Descrição da Jornada | `jornada.tirvu_id` (`531`) | `jornada.descricao` (o texto completo) |

`Empresa` continua fixa em `1` — ela nunca foi por texto.

### O que isso conserta de quebra

Com ID, quem estivesse num posto ou jornada **sem `tirvu_id` cadastrado** saía
com a célula vazia. Nos dados reais de produção são **19 postos e 23 jornadas**
nessa situação. O texto é dado do próprio cadastro e existe sempre: a
dependência do de-para desaparece do caminho do export.

### A pendência mudou de natureza

Antes, célula vazia significava *"o ID não foi cadastrado"* e o rótulo dizia
**"ID Tirvu do posto"**. Agora significa *"esta pessoa não tem posto na ficha"* —
outro problema, resolvido em outro lugar. Os rótulos viraram **Posto**, **Cargo**
e **Jornada**; manter o texto antigo mandaria o RH procurar no cadastro de IDs,
onde não há nada a corrigir.

O de-para `CargoTirvu` **continua vivo e sendo alimentado** — ele guarda o CBO,
que é o que distingue cargo homônimo. Só deixou de ser consultado no export;
`tirvu_id_do_cargo` foi removida por ter ficado órfã.

### Portões

4 mutações, todas reprovaram — inclusive as duas que restauram o ID nas células
(reprovam mostrando `49` e `246`, não por ausência: os stubs carregam ID **e**
texto de propósito). Planilha conferida com os **dados reais de produção**: 28
colunas, aba `Plan1`, três células com o texto certo e nenhuma pendência.

---

## [2.82.0] — 2026-08-08 — A variável entra onde o cursor está

> *"Nos modelos, seja de email, mensagens, doc, mostrar todas as variáveis
> disponíveis de cada colaborador (…) eu paro o cursor de digitação em
> determinado lugar do modelo e tenha como abrir um select com busca com as
> opções de variáveis, acho que melhora a ux e ui."*

### O erro que não dá erro

As variáveis eram uma **lista no topo da tela**. A pessoa lia `{{nome_social}}`,
voltava ao texto e digitava de memória — com as duas chaves de cada lado.

Errar não quebra nada: o `aplicar_variaveis` usa regex e só substitui o que casa
com uma chave conhecida. `{{nome_socal}}` (sem o "i") fica no texto **como
está** — e sai impresso no PDF que a pessoa assina. Num e-mail, `{{codigo}}` mal
digitado significa que ninguém recebe o código de acesso.

Agora a variável é escolhida numa lista com busca — que casa também pela
**descrição**, não só pelo nome — e entra pronta, na posição do cursor. Não há o
que digitar errado.

### Duas decisões que fazem funcionar

**A posição vem do DOM, não do React.** `selectionStart` lido do próprio campo e
guardado no `onBlur` — estado do React se perde quando o campo perde o foco, que
é exatamente o que acontece ao clicar no seletor. Guardar depois seria tarde.

**O foco volta para o texto**, com o cursor depois da variável. Sem isso a pessoa
insere, o cursor some, e precisa clicar no texto de novo — o seletor viraria um
atalho que custa dois cliques a mais.

Os chips continuam ao lado, agora **clicáveis**: quem já sabe o nome não abre
lista nenhuma, e clicar insere no mesmo lugar.

### Ligado nos dois editores

Modelos de documento **e** textos dos e-mails, nos dois campos de cada um
(título/assunto e corpo). O teste cobra os dois — deixar metade seria o tipo de
coisa que ninguém percebe até precisar.

A lista que ficava no topo de Modelos **saiu**: com o seletor sob cada campo, ela
apareceria três vezes na mesma tela, e no topo é legenda longe de onde se
escreve.

### Portões

2 mutações, ambas reprovaram. Backend verde, smoke **15/15**, E2E **30/30**.
Comportamento verificado na tela: inserção no meio do texto (posição 15 → cursor
em 23, foco de volta) pelos dois caminhos, chip e seletor.

---

## [2.81.0] — 2026-08-08 — A planilha que chega na caixa

> *"No corpo do email de envio de uniformes, tem que ir os dados da pessoa,
> como nome, CPF, cargo, posto e medidas. (…) quero algo que seja possível
> através da leitura do email, os responsáveis do uniforme identificarem as
> informações, sem a necessidade de entrar no sistema. Acho que seria o caso
> uma planilha do Excel ser enviada por e-mail."*

### Isto reverte a v2.07 — conscientemente

Na v2.07 ele pediu a mesma coisa e, ao ser perguntado, **escolheu o contrário**:
dados só na tela, e-mail como empurrão. O argumento era bom — *"ficha de pessoal
circulando em caixa que ninguém controla"*.

O uso mostrou o custo do outro lado: **quem compra e separa uniforme não é
usuário do painel**, e obrigá-lo a entrar para ver três medidas transformava um
recado em tarefa. Perguntado de novo, ele escolheu a planilha **anexa** — o
meio-termo que não existia antes:

- **anexo, não corpo** — não fica indexado no histórico da caixa de todo mundo,
  e dá para abrir no Excel e trabalhar em cima;
- **uma pessoa por e-mail**, no gatilho que já existia — não é dump da base.

A reversão está registrada no cabeçalho de `uniforme_planilha.py` e no
`CLAUDE.md`. Sem isso, a próxima leva leria a regra da v2.07 e "consertaria"
isto de volta.

### O que vai, e o que não vai

Sete colunas, em ordem fixa: **Nome · CPF · Cargo · Posto · Calça · Camisa ·
Calçado**. O CPF sai **mascarado** (`123.456.789-09`) e vem da **ficha**, não do
convite — o da ficha é o que a pessoa digitou e foi conferido contra o
documento.

Banco, PIX, endereço e salário estão a um `getattr` de distância e **não
entram**. Anexo circula; o que não é necessário para a tarefa não deve viajar
junto. O teste cobra isso explicitamente.

### Duas garantias que o histórico da casa exigiu

**Falha no anexo não segura o aviso.** Se a planilha não montar, o e-mail sai
sem ela, com o link da tela — como funcionava antes. Perder o aviso (ou travar a
conclusão da admissão) por causa de um `.xlsx` seria trocar um problema pequeno
por um maior.

**O texto do template foi corrigido.** Ele afirmava *"a lista não vai por
e-mail"* — verdade até a v2.80, mentira a partir daqui. Instrução que o sistema
não cumpre é a armadilha da v2.74, e o teste cobra que o corpo mencione o anexo.

### Verificado onde importa

O anexo foi conferido **no limite de envio** (`enviar_email`), não na função que
o monta: 5.261 bytes chegando, com o MIME do Excel — não `application/pdf`
chumbado, o defeito que a v2.41 corrigiu no SMTP e a v2.68 no Graph. É a lição
do teste do `.ics`: substituir o limite externo, não as próprias funções.

### E um defeito maior, que o CI achou

O primeiro push **reprovou**: no container, o anexo saía como `octet-stream`, não
Excel. A causa é do ambiente, não do código — `mimetypes.guess_type` lê a tabela
do **sistema** (no Linux, `/etc/mime.types`), e a imagem não conhece `.xlsx`.
Passava no Windows, falhava no CI.

Investigando, o problema era maior que o meu: **`.ics` e `.docx` também saíam
como `octet-stream`** naquele ambiente. No caso do `.ics`, isso significa
**convite de entrevista sem o "adicionar à agenda"** — o mesmo defeito que a
v2.68 corrigiu no caminho do Graph, vivo no SMTP desde sempre.

O `_tipo_do_anexo` ganhou mapa explícito para o que o sistema não garante. O
comentário do `.md` já previa exatamente isso e ninguém generalizou.

### Portões

3 mutações, todas reprovaram. Backend verde, smoke **15/15**, E2E **30/30** —
e os testes rodados **dentro do container**, contra banco limpo, que é a
condição real do CI.

---

## [2.80.0] — 2026-08-08 — Obrigatório é decisão, não constante

> *"Ter a opção de, no front, por padrão vir marcado os campos obrigatórios para
> todos (lógico, aqueles que têm que ser obrigatórios), mas customizável por
> candidato, pelo pessoal do RH. Daí ter um padrão geral lá em configurações."*

A obrigatoriedade era **chumbada em dois lugares** — `services/slots.py` para
documentos, `api/ficha.py` para campos. Mudar qualquer coisa exigia deploy, e o
caso excepcional (a pessoa que comprovadamente não tem aquele documento) não
tinha saída nenhuma.

### Três camadas, a mais específica vence

```
1. PADRÃO DE FÁBRICA        — o que o sistema traz
2. PADRÃO DA CASA (config)  — o RH muda para TODOS, sem deploy
3. EXCEÇÃO DA PESSOA        — o RH decide para UMA, com motivo
```

Ausência em qualquer nível **herda de cima**, nunca vira "não é obrigatório":
`None` é silêncio, `False` é uma decisão de dispensar, e o sistema precisa
distinguir os dois. Mesma herança do roteiro de entrevista (v2.66) e do prazo de
validade em Desenvolvimento.

Cobre **documentos e campos** — 19 e 33 itens —, com rótulo legível: o RH não
deve ver `trabalho_banco.pix_tipo`.

### Onde a decisão mora, e por que não no slot

`SlotDocumento.obrigatorio` seria o lugar óbvio — e errado. A
`sincronizar_slots` **reescreve** aquele campo a cada execução, e o wizard salva
a cada 900ms: a dispensa do RH sumiria sozinha em segundos, em silêncio. A
decisão vai para `Candidato.exigencias`; o slot continua sendo o estado do
ENVIO, não o da regra. **É o bloco 6 do teste** — três sincronizações seguidas,
e a dispensa continua de pé.

### O que não se desmarca

`aceite_lgpd`, `pessoais.email` e `documentos.cpf` não entram na tela. Não é
preciosismo: sem aceite não há base legal para guardar a ficha; sem e-mail o
código de assinatura não chega e a admissão para no meio; sem CPF a pessoa não
casa em creche, Tirvu nem ponto. Quebraria **longe daqui**, onde ninguém ligaria
uma coisa à outra.

### Duas lições de teste nesta leva

**Uma mutação passou verde e obrigou a reescrever a asserção.** Remover o guard
de `SEMPRE_OBRIGATORIOS` não fazia o teste falhar: aquelas chaves também não
estão no catálogo, então caíam em `chave_desconhecida` — 422 igual. Conferir só
o código faria o teste passar com a proteção removida. A asserção passou a
exigir o **motivo** da recusa (`exigencia_do_sistema`), e a ordem de validação
foi corrigida: o guard vem ANTES da checagem de catálogo, senão a proteção real
sumiria no dia em que alguém acrescentasse a chave à lista.

**O filtro de pendências ficou no fim, não espalhado.** As 12 verificações de
completude continuam num lugar só; a exigência é uma peneira sobre o resultado.
Menos superfície para errar — e o que não está no catálogo passa reto por
padrão, para que uma pendência nova acrescentada amanhã valha, em vez de sumir
por não estar catalogada.

### Portões

Migration `b3d5f7a9c2e4` executada up → down → up. 5 mutações, todas reprovaram.
Backend verde, smoke **15/15**, E2E **30/30**. Fluxo conferido na tela: marcar
em Configurações, ver o chip de origem, desfazer, e a ficha herdando.

---

## [2.79.0] — 2026-08-08 — O documento da cobertura

> *"Um intermitente precisou dar cobertura na presidência da República. Não
> estava fácil marcar para emitir os documentos específicos da presidência.
> Como podemos melhorar isso? Bem como para outros documentos específicos."*

### O diagnóstico mudou o desenho

A primeira leitura seria "faltam os documentos da Presidência". Conferindo o
código: **eles existem desde a v1.17–v1.21**, estão no catálogo, no enum e são
selecionáveis. O que faltava era outra coisa.

O kit é marcado **por POSTO** (`PostoServico.documentos_kit`) — e numa
**cobertura** a pessoa justamente não está lotada no posto que exige o
documento. As duas saídas disponíveis eram ruins:

- **lotá-la no posto da Presidência** — muda o VÍNCULO dela para emitir um papel;
- **marcar o kit no posto dela** — passaria a exigir aquilo de TODO MUNDO ali.

Daí a rota nova: acrescenta **um documento a uma pessoa**, sem tocar em posto
nenhum. O documento nasce como qualquer outro do kit e segue o fluxo normal —
aparece para assinar, entra no dossiê, conta como pendência.

Na ficha da pessoa, num bloco recolhido (é caso excepcional, não pode competir
com o trabalho diário): escolhe o documento, diz o motivo, pronto.

### As quatro garantias

1. **A lista vem do MESMO catálogo do kit de posto.** Uma lista paralela
   divergiria na primeira mudança — lição do enum reescrito à mão (v2.69).
2. **Só o catálogo entra.** Aceitar qualquer valor do enum deixaria acrescentar
   ficha de integração ou termo de VT à mão — documentos que o sistema decide
   por regime e por posto. No caso do VT seria um **segundo termo de desconto de
   6% em folha**.
3. **Motivo obrigatório**, e a auditoria guarda o motivo **e o posto da
   pessoa** — é o contraste que torna o registro verificável depois: *"lotada em
   X, assinou o kit de Y"*. Precedente do `reverter` (v1.65) e da troca de
   matrícula (v2.45).
4. **Não duplica assinatura viva.** Reemitir apagaria o que a pessoa já
   assinou; o 409 diz se está *pendente* ou *assinado*, porque a tela precisa
   distinguir — um pede paciência, o outro pede o caminho de invalidar.

### Uma mutação que quase passou por aprovação

A mutação que remove a checagem do catálogo fazia a rota estourar `KeyError`, e
o `TestClient` **repropaga a exceção do servidor**: o script morria sem imprimir
nenhum "FALHOU", e a saída sem falhas passaria por sucesso. É exatamente a
armadilha registrada na v2.72.2. Com `raise_server_exceptions=False` o 500 vira
resposta e as asserções o reprovam — nomeando cada documento proibido.

### Portões

`test_documento_especifico.py`: 4 mutações, todas reprovaram (a da duplicata
mostrou o estrago real: **2 assinaturas no banco**). Backend verde, smoke
**15/15**, E2E **30/30**. Fluxo conferido na tela renderizada.

---

## [2.78.0] — 2026-08-08 — Um botão, dois estados

> *"Não precisa ter um botão dizendo que está aberto e outro para fechar,
> totalmente desnecessário — e tem um 'risquinho' aparecendo também."*

Terceira tentativa no mesmo controle, e a certa. A v2.75 deixou **dois** botões
"fechar" (um na coluna, outro no painel). A v2.75.1 tirou um e **desabilitou** o
outro quando a ficha abria — trocou um defeito por outro: botão desabilitado que
anuncia estado não é controle, é ruído ocupando o lugar de uma ação.

Agora é **um só, que alterna**: *"Mais detalhes"* / *"Menos detalhes"*. O rótulo
diz o que ACONTECE ao clicar, não o estado atual — quem lê um botão espera o
efeito. O `✕ fechar` do painel saiu, e com ele a prop `aoFechar`, que ficaria
declarada sem uso.

### O risquinho

Era real e tinha causa: a `td` da linha de detalhe recebe `background` e borda do
tema, mas mede a largura **visível** do container (`100cqw` = 1060px) enquanto a
tabela pode ser mais larga (1370px). A borda de baixo era desenhada só até onde
a `td` chega, e a diferença aparecia como uma faixa clara à direita da linha
aberta. Sem borda e sem fundo próprios não há o que sobrar — quem pinta o painel
é o `.rh-conferencia` lá dentro.

### E um defeito que o rótulo novo criou

`.acoes-candidato:has(> :only-child)` fixava `width: 12ch` — largura pensada para
"abrir". Com "Menos detalhes" o texto saía cortado ("lenos detalhe" no print).
Foi para `16ch`.

Fica a regra: **ao trocar o texto de um botão de ação, confira a largura da
coluna** — ela é dimensionada em `ch`, proporcional ao rótulo, e o
`text-overflow: ellipsis` esconde o corte em vez de denunciá-lo.

### Portões

E2E **30/30**, backend verde, smoke **15/15**. Conferido nos dois ambientes:
desktop com o rótulo inteiro, celular com zero botões "fechar" e zero
vazamentos.

---

## [2.77.0] — 2026-08-07 — A âncora ao lado da nota

Dois problemas na ficha de entrevista, os dois com print.

### O vazio entre a pergunta e os botões de nota

No celular abria um buraco de ~130px entre a pergunta da competência e os chips
de nota. A causa: a regra base declara `.rh-escala-rotulo { flex: 1 1 12rem }` —
numa LINHA horizontal isso significa *"ocupe a largura que sobrar"*, e está
certo. Ao virar COLUNA no celular, o mesmo `1 1` passa a mandar no eixo
**vertical**, e o rótulo esticava para **192px** com 3 linhas de texto.

É a armadilha da v2.63 (`trocar display invalida as flags dos filhos`) no eixo
oposto: mudei `flex-direction` sem revisar o `flex` de quem está dentro.
Medido depois: rótulo 192px → 67px, bloco 428px → 303px.

### A âncora estava longe de onde a nota é dada

> *"tanto na versão web quanto na desktop, as âncoras têm que estar perto dos
> marcadores. Seria interessante se fosse um popup?"*

A descrição que separa "4 — Evidência forte" de "3 — Atende" só existia em dois
lugares ruins: no `title` do chip — que **não abre no celular**, onde não há
mouse — e num `<details>` no fim do bloco, longe da decisão.

Agora ela aparece **no próprio chip**, ao passar o mouse (desktop) e **ao tocar**
(celular). Não é componente novo: reusa o mecanismo do `Ajuda.jsx` — CSS puro
com `:hover`/`:focus`, sem estado no React —, que é o padrão de tooltip da casa.
O balão sobe em vez de descer, porque os chips ficam logo acima do campo de
justificativa e para baixo ele cobriria o que a pessoa vai escrever.

O `<details>` continua, com rótulo novo (*"ver todas as âncoras lado a lado"*):
o chip responde *"o que é o 3?"*; a lista responde *"onde termina o 3 e começa o
4?"* — calibrar antes de começar é outra tarefa.

### Portões

E2E **30/30**, backend verde, smoke **15/15**.

*Nota de método:* uma execução acusou falha no teste da câmera guiada e o
`git stash` sugeriu regressão minha. Reproduzindo com as mudanças restauradas,
**passou** — era ruído de ambiente. O `git stash` isola o código, não o estado
do container; confirmar duas vezes antes de acusar o próprio diff.

---

## [2.76.2] — 2026-08-07 — O `<details>` fechado não renderiza

> *"Não voltaram os filtros de select com busca. Quero que volte para todos que
> têm eles."*

Terceira correção da mesma leva, e a mais direta: **os filtros sumiram do
DESKTOP**. A v2.76.1 disse que "no desktop nada mudou" — estava errado, e o
print provou.

### A causa

Um **`<details>` fechado não renderiza o conteúdo**. Isso é do navegador, não do
estilo — e `display: contents` no CSS não muda. Eu neutralizei a caixa na folha
(`.dash-filtros-caixa { display: contents }`, `.dash-filtros-resumo { display:
none }`) achando que bastava para o desktop voltar ao que era. Os 9 filtros
continuavam no DOM, com altura zero.

O estado tem que nascer certo no JSX: `open={!ehCelular}`, com `matchMedia`
acompanhando o giro do aparelho — sem o listener, quem abrisse no celular e
girasse continuaria sem filtros num desktop.

### Por que nenhuma régua pegou

As três de layout mediam **celular**. O defeito era do desktop, e a suíte não
tinha nada apontado para lá além da largura de tabela. O teste novo mede as 8
telas em 1440px e cobra três coisas: a caixa **aberta**, filtros com altura
**maior que zero** (estar no DOM não basta — foi exatamente o sintoma) e o card
de ações visível.

Validado por mutação: removendo o `open`, ele reprova nomeando as 5 telas.

### Portões

E2E **30/30**, backend verde, smoke **15/15**.

---

## [2.76.1] — 2026-08-07 — O botão que sumiu junto com os filtros

Correção de **duas regressões que a v2.76 causou** — as duas apontadas pelo
Bruno usando o sistema em produção.

### O botão de cadastro não sumiu: eu o escondi

> *"Você tirou os botões de cadastro de novo banco de talentos. Como assim?"*
> *"Não quero que os botões fiquem no mesmo card que os filtros, pois os botões
> merecem ter seus próprios cards."*

Ele estava certo nas duas frases, e é o mesmo defeito. O "＋ Cadastrar talento"
morava **dentro do card de filtros** (`acoesFiltro` → `.dash-filtros-acoes`).
Quando a v2.76 recolheu esse card no celular, o botão foi junto — **sumiu da
tela sem nunca ter sido removido do código**.

Filtrar e AGIR são naturezas diferentes: uma refina o que se vê, a outra cria e
exporta. As ações ganharam card próprio (`.dash-acoes`), sempre visível.
**Regra que fica: nada que CRIA pode viver dentro de um bloco que se recolhe.**

*Sobre os filtros:* nenhum foi removido — todos continuam lá, recolhidos no
celular com um contador dos que estão ativos. No desktop nada mudou.

### A régua de largura não via o vazamento

> *"O ajuste que você fez na página de entrevistas está extrapolando as laterais
> da tela mobile."*

O teste de largura media `document.body.scrollWidth` e dizia **zero**. O
vazamento era de um elemento DENTRO do painel de detalhe — o "✕ fechar" medido
em `right=471` numa viewport de 390px — e overflow contido não alarga a página.

A causa: `.dash-detalhe` usa `width: 100cqw`, correto no modo TABELA (o container
rola de lado e o painel precisa ficar preso à parte visível) e **errado no modo
CARD**, onde mede um container mais largo que a tela.

Teste novo mede a **borda direita** de cada elemento, em 320px e 390px, com o
painel de detalhe ABERTO. Validado por mutação: devolver o `100cqw` faz ele
reprovar nomeando o elemento e onde ele termina.

**Uma mutação passou verde e mudou o texto do commit:** o `flex-wrap` que
acrescentei ao `.rh-conferencia-topo` na mesma leva **não era a causa** —
removê-lo mantém o teste verde. Ele fica porque é a regra global da v2.60, mas
o comentário no teste diz explicitamente para não lhe atribuir o conserto.

### Espaço vertical: a ordem para ganhar

O card de ações novo custou ~130px e devolveu a lista para fora da primeira tela
em 5 telas. Resolvido sem esconder nada: card sem moldura no celular, texto
explicativo cortado em 2 linhas (abre ao tocar) e `⬇ Exportar CSV` virando
`⬇ CSV` via `.so-desktop`, com a frase inteira no `title`.

A ordem ficou registrada na folha: **compactar espaçamento → recolher o que é
consulta → encurtar rótulo → só então esconder. Nunca esconder ação.**

### Portões

E2E **29/29** (dois testes novos), backend verde, smoke **15/15**.

---

## [2.76.0] — 2026-08-07 — A lista que começava fora da tela

> *"a navegação está feia demais para mobile, horrível. veja o print"* — com
> print estendido da tela inteira.

O diagnóstico não era estético. Medido em **390px de largura**, antes de
qualquer registro aparecer:

| Tela | Antes | Depois |
|---|---|---|
| Talentos | **1212px** | 549px |
| Colaboradores | 1092px | 552px |
| Entrevistas | 1039px | 471px |
| Desenvolvimento | 1013px | 516px |
| Admissões | 817px | 542px |

Em telas de 844px de altura, 1212px é **uma tela e meia de rolagem só para ver
o primeiro item** — a pessoa abre a lista e não vê lista nenhuma. A causa: tudo
foi desenhado para desktop e apenas EMPILHADO no celular.

Nenhuma régua existente pegava isso: as outras medem LARGURA (nada estoura de
lado) e ALTURA DE LINHA (o card não vira pergaminho). **Ninguém media quanto
cabeçalho existe antes do conteúdo.**

### As quatro regras — valem para TODA tela, não só as desta leva

Estão no `styles.css`, no bloco final `@media (max-width: 760px)`, e alcançam
qualquer tela que use `.rh-painel` + `DashPlanilha`. Tela nova nasce certa sem
ninguém lembrar delas.

1. **Filtro é passo seguinte, não a abertura da tela.** A barra nasce recolhida
   num `<details>`, com contador de quantos estão valendo. Chegava a **643px**
   sozinha. Quem abre a lista quer a LISTA. O contador não é enfeite: filtro
   ativo escondido faria a lista parecer recortada sem explicação.
2. **Métrica é informação, não cartaz.** Cards em 2 colunas compactas — 63px
   cada, contra ~120. Continuam clicáveis para filtrar.
3. **Ação do cabeçalho não ocupa a largura inteira.** `flex: 1 1 0` nos botões:
   com `auto` cada um parte da largura do próprio texto, e "＋ Registrar
   conversa" sozinho enchia os 390px, empurrando o vizinho para baixo (368px →
   179px). A área de toque continua acima dos 44px recomendados.
4. **O título não precisa de três linhas de respiro.** No celular cada pixel
   acima do conteúdo é rolagem que a pessoa paga.

No desktop **nada muda**: o `<details>` é `display: contents` e o `<summary>`
some, então o layout é byte a byte o de antes.

### O padrão ficou registrado, e travado por teste

- `08-sistema-de-design.md` ganhou a **§ 9.1**, com as regras, os números
  medidos e como conferir.
- O checklist ganhou a linha: *"no celular, a primeira linha da lista aparece
  antes de 600px — medida, não estimada"*.
- `tabelas-cabem-na-tela.spec.js` ganhou o teste que mede as 8 telas em 390px.
  **Validado por mutação**: abrindo os filtros por padrão, ele reprova nomeando
  cada tela e o motivo (`Talentos: a 1ª linha só começa em 1196px`).

### Portões

E2E **27/27** (o teste novo incluído), backend verde, smoke **15/15**.

---

## [2.75.0] — 2026-08-07 — O aviso que ninguém via

Cinco reprovações do Bruno usando o Módulo de Entrevistas, todas com print. São
defeitos de USO — o backend estava certo em todos.

### O aviso aparecia onde a pessoa não estava olhando

> *"esses avisos tem lugares que ele aparece no topo enquanto estamos lá embaixo
> na tela, ou seja nem aparecem"*

A confirmação era um `<p>` no topo do componente. Quem clicava num botão do meio
ou do fim da lista **nunca a via**. É a regra da v1.96/v2.47 — *"a mensagem vai
onde a PESSOA está olhando; o critério é DISTÂNCIA"* — que vinha sendo corrigida
tela a tela e voltava em cada tela nova. São 122 usos de `.sucesso`/`.alerta` em
47 arquivos: corrigir caso a caso não escala.

Nasceu o `<Aviso>`: ancorado na JANELA (`position: fixed`), então está sempre no
campo de visão, qualquer que seja o scroll. Cumpre os quatro pedidos —
**discreto** (canto inferior direito, fora do caminho da leitura), **tempo de
ler** (6s sucesso / 10s erro, com barra mostrando o tempo correr), **segura no
hover** e **fecha no ✕ ou Esc**.

⚠️ **Não substitui `.alerta` inline.** Muitos deles não respondem a ação nenhuma:
descrevem um ESTADO da tela (o banco atrasado em Config, os impedimentos da
ficha). Aquilo se consulta enquanto se trabalha — flutuar e sumir esconderia o
que a pessoa precisa ler. Um responde a clique; o outro explica o que está ali.

### Dois botões para a mesma coisa, duas vezes

> *"por que tem o botão triagem e entrevista, se ambos abrem a mesma coisa?"*

Abriam o MESMO formulário, mudando só o valor inicial de um campo "Tipo" que
continuava editável ali dentro — o botão escolhido não decidia nada. Virou **"+
Registrar conversa"**, e o campo Tipo (o primeiro do formulário) é o único lugar
onde a natureza é escolhida.

> *"por que dois botões fechar?"*

O "fechar" da coluna de ações e o "✕ fechar" do painel faziam a mesma coisa.
Ficou o do painel, que é o certo: está ao lado do conteúdo que se está lendo. Na
coluna, a ação agora só ABRE.

### Clique morto no nome da pessoa

> *"quando clico no nome da pessoa não aparece nada"*

O `onClick` só fazia algo com `candidato_id` — e quem é **talento** não tem: é a
maioria da lista, e todos os cadastrados na hora pela v2.74. O clique não fazia
nada: sem erro, sem espera, sem tela. É o defeito do currículo do Banco de
Talentos (v2.54), e a regra de lá vale aqui: **o que é clicável tem que fazer
alguma coisa, sempre**. Agora, sem candidato, abre a ficha da própria conversa.

### O título escrito duas vezes

> *"por que escrever o título duas vezes? basta escrever cada título 1x e
> estarem alinhadas as notas e o campo de escrita. o UX está horrível"*

Eram DUAS listas paralelas — as 4 competências à esquerda, os 4 textos à direita
—, cada uma repetindo os nomes. Pior que a repetição: **nada garantia
alinhamento**. A pergunta de uma competência ocupa 2 linhas e a da outra 1, então
o campo da 2ª aparecia na altura da 3ª — e a pessoa escrevia a justificativa no
lugar errado, num documento que ela assina.

É a armadilha da v2.66 numa variação: a primitiva de 2 colunas serve conteúdo
EMPARELHADO, e o par aqui é *nota ↔ justificativa daquela competência*, não "a
lista de notas" ao lado de "a lista de textos". Agora é **um bloco por
competência**: nome uma vez, pergunta, notas e justificativa juntas. Composição
copiada da referência canônica (`FormularioAvaliacao.jsx`), como manda a v2.65.

### O CRUD de roteiros que ninguém achava

> *"cadê a parte onde posso fazer CRUD de mais roteiros?"*

A tela sempre existiu (Configurações → 🗣️ Roteiros de entrevista), mas **nada
apontava para ela** — e é conduzindo a entrevista que se percebe que o roteiro
precisa mudar. Dois atalhos: o botão 🗣️ Roteiros no topo da lista e o chip do
roteiro na ficha, agora clicável. A aba vem do `localStorage`, não da URL, então
o atalho grava a preferência antes de navegar — sem isso abriria a última aba
usada e pareceria não funcionar.

### Portões

Backend: testes verdes, smoke **15/15**. E2E: **26/26**. Ficha conferida na tela
renderizada: 4 competências, **zero nomes duplicados**, chips e campo no mesmo
bloco, estouro horizontal 0.

*Nota sobre a suíte E2E:* uma execução acusou falhas no login — era o **rate
limit** acumulado por rodar a suíte várias vezes seguidas (o limite é em
memória, some ao reiniciar a API), não regressão. Armadilha já registrada na
v2.60.

---

## [2.74.0] — 2026-08-07 — A pessoa que não está na lista

Três pedidos do Bruno sobre o formulário de nova entrevista, com prints, mais um
que ele cobrou no meio da leva. O fio comum: **o formulário só funcionava se
tudo já estivesse cadastrado** — e o caso mais comum do recrutamento é
exatamente o contrário.

### A pessoa que ainda não existe

> *"pode ser que a pessoa não esteja no banco, logo, tem que permitir cadastrar
> a pessoa ali na hora, em regra o RH pode cadastrar com nome e whatsapp, para
> depois preencher mais informações sobre ela, como no módulo admissões"*

"A pessoa é" ganhou **"Ainda não cadastrada — cadastrar agora"**, e o cadastro
abre no próprio formulário: **nome e WhatsApp bastam**, como a admissão faz —
começa com o mínimo e completa no caminho. A pessoa entra no Banco de Talentos
pela mesma rota do cadastro à mão (v2.73), então herda tudo: nome padronizado,
**consentimento não fingido** e autor registrado. Da próxima vez ela já está na
lista.

`forcar: true` aqui é deliberado: o RH está com a pessoa na frente e não veio
conferir cadastro. Barrar a conversa por causa de um homônimo seria o sistema
atrapalhando.

### O currículo — que a v2.73 prometeu e não entregou

> *"na cadastro manual de talentos, você esqueceu da opção de poder anexar
> currículo"*

Pior que esquecer: a tela da v2.73 **dizia** "o currículo pode ser anexado
depois, pela ficha da pessoa" — e não havia como. A única rota de upload era a
PÚBLICA, autorizada por um `upload_token` com TTL de 30 min emitido no cadastro
público; o RH não tem token nenhum. Promessa na interface sem rota atrás é a
família do "documento que não nasce" (v2.69): ninguém vê o que falta.

Agora há `POST /rh/talentos/{id}/curriculo`, e o anexo aparece em **três**
lugares: no cadastro à mão, no cadastro pela entrevista e na ficha do talento
(onde também **troca** — o currículo que chega por e-mail costuma vir atualizado
depois). Mesma validação e mesma indexação do upload público: a porta é
`_guardar_curriculo`, uma só.

Troca com extensão diferente **remove o arquivo anterior**: só o registro aponta
para a key, então o antigo ficaria órfão no MinIO, fora do alcance da tela e do
expurgo — o defeito que o teste do anexo de entrevista pegou na v2.72.

Falha no upload **não desfaz o cadastro**: a pessoa já entrou, e a tela diz que
o arquivo não subiu. Perder o cadastro por causa de um anexo seria trocar um
problema pequeno por um maior.

### Cargo e posto quando não há vaga

> *"na vaga, podem ser dois campos, cargo e posto, puxando todos já cadastrados
> ou tendo a opção de criar ali mesmo"*

Nem toda entrevista nasce de vaga aberta: o RH conversa para um posto que
precisa repor gente. Os campos aparecem **só quando não há vaga escolhida** —
três campos dizendo a mesma coisa fariam preencher dois por engano (um assunto,
um controle, v2.30). Havendo vaga, ela manda, inclusive no cargo.

O cargo não é decorativo: é ele que resolve **qual roteiro** a entrevista usa
(herança cargo → padrão). Lista os cargos já usados na base, com "＋ Cargo
novo…" trocando para texto livre — o padrão do `Detalhe.jsx`, que evita
"Vigia"/"vigia"/"Vigía" virando três cargos.

`posto_id` é FK **com snapshot do nome**, pela mesma razão do `vaga_titulo`: o
posto pode ser excluído e a entrevista tem que continuar dizendo para onde a
conversa foi. Testado com exclusão definitiva de verdade — a FK vira NULL e o
nome permanece.

### Uma armadilha evitada no caminho

A primeira versão do seletor de cargo passava `permiteNovo` ao `SelectBusca` —
**prop que não existe**. O React a ignoraria em silêncio e o campo pareceria
funcionar sem nunca aceitar cargo novo: exatamente a armadilha da v2.64, pega
por abrir a assinatura do componente antes de confiar nela.

### Portões

Migration `a2c4e6f8b1d3` executada up → down → up. 15 testes de backend, smoke
**15/15**, E2E **26/26**, 4 mutações reprovando. Fluxo conferido na tela
renderizada e no banco: cargo, posto, telefone, currículo e consentimento nulo
com autor registrado.

---

## [2.73.0] — 2026-08-07 — A porta que não existia

O RH pode **cadastrar um talento à mão**, pelo painel. Era o último item do § 13
do Módulo de Entrevistas: o pedido original falava em "currículo que chega por
e-mail", mas o problema real era a porta ausente — o Banco de Talentos tinha
duas entradas (formulário público e importação de planilha do Forms) e **nenhuma
servia ao RH**. O currículo que chegava por e-mail ou indicação ficava de fora,
ou obrigava a pedir que a pessoa preenchesse o formulário de novo.

### Consentimento não se finge

No formulário público a pessoa marca "li e concordo" e o `consentimento_lgpd_em`
é carimbado; na importação, o carimbo vem da coluna da planilha. **Quando o RH
cadastra à mão, ninguém marcou nada.**

Decisão do Bruno: registrar a **origem**, sem fingir aceite. O campo fica NULO,
`cadastrado_por_id`/`_nome` guardam quem assumiu (nome em SNAPSHOT, como a
`Anotacao` do CRM), e a ficha diz *"sem aceite — cadastrado por Fulano"* em vez
de um travessão que parece dado faltando. É o precedente da `AutorizacaoEquipe`
(v1.42) e do manifesto de admissão assistida (v2.56): **o registro descreve o ato
REAL, nunca a versão conveniente**.

A tela avisa disso **antes** de cadastrar, não depois — e sugere mandar o link do
Banco de Talentos quando o aceite dela importa.

A mutação que carimba o consentimento é a mais importante do teste novo: ela
passaria em qualquer revisão de código (o cadastro funciona igual, a tela fica
até mais limpa) e o que se perde é a verdade de um registro de LGPD.

### Duplicata avisa, não funde

409 dizendo **quem** já existe, com botão para abrir a ficha da pessoa — "já
existe" sem nome faz o RH procurar na lista (regra da v2.55). Mesma regra de
duplicidade da importação de planilha (e-mail; ou nome+telefone, comparando só os
dígitos): duas portas para o mesmo banco não podem discordar sobre o que é a
mesma pessoa. `forcar` existe para o homônimo real e fica na auditoria.

É a regra da casa para equivalência assistida — jornadas, incidência de
benefícios e cargos do Tirvu todos propõem e deixam o humano confirmar.

### E um defeito de produção, relatado no meio da leva

> *"a msg abaixo aparece, no módulo de entrevistas quando clico em triagem ou
> entrevista — 😕 Algo deu errado ao abrir esta página"*

Era o ErrorBoundary. O formulário de nova entrevista chamava **`api.talentos()`,
uma função que nunca existiu** (a certa é `listarTalentos`). O `.catch(() => {})`
ao lado não protegia nada: `undefined()` é `TypeError` **síncrono**, estourado
antes de existir promessa para capturar — e exceção de render apaga a tela
inteira. Mesma família da `prop` inventada no `SelectBusca` (v2.64) e da classe
CSS fantasma (v2.25): o JSX fica plausível e o build passa.

**O defeito tinha uma segunda metade, mais silenciosa.** As três rotas daquele
`useEffect` devolvem lista pura (`-> list[dict]`), mas o código lia
`r.itens || r.vagas || []` — então, mesmo sem o `TypeError`, os seletores de
pessoa, vaga e candidato abririam **vazios, sem erro nenhum**. Corrigir só o nome
deixaria dois terços do defeito de pé. Medido depois do conserto: 18 pessoas e
3 vagas nos seletores.

`test_api_front_existe.py` varre todo o JSX e reprova chamada a `api.x()`
inexistente. A varredura completa não achou nenhuma outra.

### Portões

Backend: 15 testes verdes, smoke **15/15**. E2E: **26/26**. Migration
`f1a3c5e7b9d2` executada up → down → up. 4 mutações no cadastro e 1 no defeito do
front, todas reprovaram. Fluxo conferido na tela renderizada.

---

## [2.72.3] — 2026-08-07 — O chip que esticava a tabela

O CI da v2.72.2 **reprovou** — a régua de layout (`tabelas-cabem-na-tela`)
acusou Talentos estourando 67px e, na sequência, Entrevistas com linha de 251px.
Nenhum dos dois vinha das mudanças daquela leva (que mexeu só em testes, CI e no
mapa da lixeira). Os dois eram defeitos REAIS de tela que ninguém tinha visto —
e que agora atingiriam o RH em produção.

### O chip da tag de reaproveitamento estica a coluna inteira

`.chip` tem `white-space: nowrap` — correto para status e contagem, que ficariam
feios partidos. Mas a coluna Tags de Talentos recebe a **tag de
reaproveitamento**, que o próprio sistema gera a partir do cargo da vaga
(`entrevistas.py:493`, `reaproveitar: <cargo>`).

Não é problema de dado de teste. Medido contra a **base real**: o cargo com mais
gente — *"Auxiliar de Serviços Gerais"*, **18 pessoas** — produz uma tag de **41
caracteres**, mais longa que a do teste. O `max-width: 22rem` da `td` não contém
um filho que se recusa a quebrar:

```
sem a tag  -> tabela 1002px / área visível 1004px   (cabe)
com a tag  -> tabela 1049px / área visível 1004px   (45px fora da vista)
```

Corrigido com teto no chip dentro de coluna que quebra, texto inteiro no
`title`. **O teto precisa ser ABSOLUTO (`14ch`)**: com `max-width: 100%` a
largura da `td` é calculada a partir do conteúdo, então o `100%` acompanha o
chip que cresce e não limita nada — medido, o chip continuava em 256px. Com
`14ch` caiu para 116px e as cinco larguras passaram a caber.

### No modo CARD, o corte de 3 linhas nunca funcionou

Entrevistas a 1150px: um título real de posto (*"INEP - 37/2025 - APOIO
ADMINISTRATIVO, RECEPÇÃO E PORTARIA…"*) deixava a linha em **251px**, contra o
teto de 240 — o card ocupando meia tela, que é exatamente o defeito que o modo
card existe para resolver. **Pré-existente**: confirmado com `git stash`, falha
igual no código original.

A causa tem duas camadas, e a segunda só apareceu medindo:

1. a regra do corte é `td.dash-quebra > .dash-corta`, mas no card a `td` vira
   `display: flex` e a regra não alcança o filho da mesma forma;
2. **o navegador BLOCKIFICA o `.dash-corta`** (computed `flow-root`) e engole o
   `-webkit-box` — ele resiste até a `display: -webkit-box !important` aplicado
   inline. É o mesmo mecanismo que a v2.60 registrou para a `<td>`, num lugar
   novo.

Por isso o corte no card é por **`max-height`**, que não depende de `display`
nenhum. São **duas** linhas ali (não três): as células ficam lado a lado numa
grade e a mais alta estica as vizinhas — com três linhas dava 249px, ainda acima
do teto; com duas, 226px. Na tabela continuam três.

### Portões

Suíte E2E completa: **26/26** — incluindo os dois testes que estavam vermelhos.
Backend: 17 testes verdes, smoke 15/15.

---

## [2.72.2] — 2026-08-06 — A lixeira devolve o que engoliu

Fecha a última pendência do Módulo de Entrevistas, aberta desde a v2.67 e
repetida em quatro relatórios: *"conferir a restauração de uma vaga pela
lixeira"*. Ao exercitá-la, o defeito era **seis vezes maior que a pendência**.

### Seis das oito entidades entravam na lixeira e não voltavam

`api/lixeira.py::_reconstruir` tinha um mapa `entidade → modelo` com **duas**
entradas (`posto`, `modelo_documento`). Enquanto isso, oito coisas já eram
mandadas para lá: vaga (v2.67), prova, item de banco, papel de assinatura,
roteiro de entrevista, teste de candidato e entrevista.

Para as faltantes, a lixeira era **via de mão única**. Medido na rota, antes de
corrigir:

```
DELETE /rh/vagas/{id}          -> 204   (some da listagem)
GET    /rh/lixeira             -> lá está ela, com rótulo e data
POST   /{item}/restaurar       -> 422 {"detail":"entidade_desconhecida"}
```

**O que torna isso pior que um erro barulhento: a exclusão funciona.** O item
aparece listado, com rótulo e data, *exatamente igual* aos que voltam. Nada
avisa. O RH só descobriria no dia em que precisasse desfazer — que é o único dia
em que a lixeira importa. Mesma família do worker que não roda (v2.66) e do
documento que não nasce (v2.69): o silêncio se confunde com "está tudo certo".

Aconteceu **seis vezes seguidas** porque nada ligava uma ponta à outra: quem
escreve `mandar_para_lixeira(...)` num módulo novo não tem motivo para abrir o
`lixeira.py`.

### O guarda-corpo importa mais que a correção

`test_lixeira_restaura.py` varre as chamadas de `mandar_para_lixeira` em
`app/api/` e **reprova se alguma entidade não estiver no mapa**, nomeando-a. O
próximo módulo que mandar algo para a lixeira não repete o defeito.

Ele **não chuta uma contagem** (`assert len(mapa) == 9` quebraria na próxima
entidade legítima, e a "correção" óbvia — incrementar o número — faria o teste
não proteger nada, lição da v2.25): a garantia é derivada do código-fonte.

Quatro mutações verificadas. Duas coisas que elas ensinaram:

- **o varredor casou com a própria documentação**: o docstring que escrevi para
  explicar o defeito usa `mandar_para_lixeira(db, obj, "x", ...)` como exemplo,
  e o `"x"` entrou na lista como entidade órfã de verdade. O teste reprovava o
  texto que explica a correção — e o reflexo de quem o visse seria apagar a
  explicação. É a armadilha da v2.71; resolvida com o filtro que ignora
  comentário e docstring;
- **a mutação que aceita entidade desconhecida MATAVA o teste** em vez de
  reprová-lo: o `TestClient` repropaga a exceção do servidor, o script morre no
  meio e a saída fica sem nenhum "FALHOU" — **parecendo aprovação**. Com
  `raise_server_exceptions=False`, o 500 vira resposta e a asserção pode dizer
  que ele é errado.

### Portões

Verificado **dentro do container da API**, com Postgres e MinIO limpos e a senha
do job — não só na máquina de quem desenvolve: `test_lixeira_restaura` OK,
`test_entrevista_anexo` OK, smoke **15/15**. Localmente, os 17 testes verdes,
smoke 15/15, `npm run build` OK. Resíduo de mutação zero.

---

## [2.72.1] — 2026-08-06 — O smoke entra no CI

Resposta do Bruno à pergunta deixada em aberto na v2.72 (*"o `smoke_test` deve
entrar no CI?"*): **sim**.

O smoke é o portão mais completo do projeto — 15 etapas ponta a ponta: cadastro
pelo RH → link mágico → autosave da ficha → declaração de veracidade → upload de
documento (imagem vira PDF no MinIO) → conclusão → aprovação → dossiê. É o único
teste que percorre o caminho INTEIRO do candidato; os demais cobrem uma fatia
cada. E era justamente o que ninguém rodava.

### Os dois defeitos que o impediam de rodar lá — os mesmos de sempre

Não bastou acrescentar a linha no `ci.yml`. Rodando-o **dentro do container da
API**, como o pipeline faz, apareceram os dois de sempre:

1. **`os.environ.update` sobrescrevia a `DATABASE_URL`** — o smoke ia sempre ao
   banco local, e dentro do container isso o mandaria para um
   `localhost:55432` que não existe ali. Virou `setdefault`, como o
   `test_match_persistencia` na v2.72 e como todo o resto do projeto.
2. **A senha do admin era LITERAL na linha do login** — a armadilha da v2.71,
   pela quarta vez nesta contagem. No CI o admin nasce com a senha do `.env` do
   job.

O erro do segundo apareceu **exatamente como a mensagem nova prometia**, e é a
diferença que ela existe para fazer:

```
AssertionError: login falhou (401): confira RH_ADMIN_EMAIL/RH_ADMIN_PASSWORD
— `criar_admin_inicial` só cria o admin com a tabela VAZIA...
```

Não foi um `KeyError: 'token'` num dict.

### Verificado como o CI faz, não como é conveniente

Rodado **dentro do `deploy-api-1`**, contra um Postgres e um MinIO recém-criados
na rede da stack, com a senha do job (`senha-ci-12345678`): **15/15**. E de novo
no mesmo banco, para provar idempotência: **15/15**. Também segue verde na
máquina de quem desenvolve, com os padrões — os dois ambientes, não um.

### Passo próprio, não mais uma linha no laço

O smoke leva mais que todos os outros testes juntos. Num `for` compartilhado,
uma falha dele viraria uma linha perdida no meio do log; em passo próprio, o
GitHub mostra de cara qual portão caiu. Fica **depois** dos testes rápidos e
**antes** do Playwright: falha cedo, poupa os minutos de navegador.

---

## [2.72.0] — 2026-08-06 — O teste que ninguém rodava

Fecha a dívida do **Módulo de Entrevistas** — as quatro levas (v2.64 → v2.68)
entregaram 41 cenários e 9 mutações, e os relatórios de execução registraram
honestamente o que ficou faltando. Esta leva não acrescenta funcionalidade:
**faz o que já existe passar a ser verificado**.

### O módulo inteiro estava fora do CI

Quatro levas, cinco arquivos de teste, **zero rodando no pipeline**. É a
armadilha da v2.48 na segunda reincidência: lá foram os 38 testes Python que
"só rodavam se alguém lembrasse".

O que estava desprotegido não dá erro quando quebra — sai errado em silêncio:

- **o roteiro padrão é o PISO da herança**: sem ele, `resolver_roteiro` devolve
  `None` e **toda ficha de entrevista abre vazia, sem erro na tela** (defeito
  real, achado por mutação na v2.66);
- **a ficha assinada não pode entrar no dossiê**, que é o documento que CIRCULA
  (cliente, pasta física). O default do `dossie.py` é *"entra"*, e o vazamento é
  uma página a mais que ninguém confere;
- justificativa obrigatória por nota, o snapshot da vaga, e o sistema nunca
  concluindo `nao_veio` sozinho;
- arquivar que **não apaga**.

**Mas três deles não podiam entrar como estavam**: tinham a senha do admin
LITERAL na linha do login. No CI o admin nasce com a senha do `.env` do job, e a
literal devolve 401 → `KeyError: 'token'`, erro que não fala da causa. É
*exatamente* a armadilha da v2.71, que impediu `test_documentos_catalogo` e
`test_email_templates` de entrarem — e que se repetiu aqui sem ninguém notar.
Provado antes de corrigir: com a senha do CI, `test_entrevistas` dava
`login falhou: 401 credenciais_invalidas`.

No `test_entrevista_documentos` a literal pesava duas vezes — a mesma senha
assina a ficha (`prova_metodo = "senha_sessao_rh"`), então a assinatura seria
recusada por *"senha errada"*, apontando para o lugar errado do sistema.

### O anexo da entrevista ganhou teste (a dívida declarada da v2.64)

O relatório da v2.64 dizia, sem maquiagem: *"o cenário 20 está coberto por
código revisado, não por teste"*. Agora tem `test_entrevista_anexo.py`, com
**cinco mutações verificadas** — allowlist, teto, `close()` do spool, o órfão no
storage e o `Content-Type`.

A asserção do tipo é sobre a **resposta do GET**, não sobre a constante
`ANEXO_CT`: afirmar `ANEXO_CT["png"] == "image/png"` testaria o dicionário, não
a LIGAÇÃO — e foi assim que o `application/pdf` chumbado do caminho do Graph
sobreviveu até a v2.68 com um teste verde ao lado.

### `test_match_persistencia.py` — vermelho desde antes da v2.64

Três relatórios seguidos o registraram como pendência e perguntaram ao Bruno se
deveria ser consertado. A causa: `executar_processamento` varre
`select(Talento).where(status != "arquivado")` — **o banco inteiro** —, e as
asserções eram `r1["analisados"] == 1`. A 2ª execução no mesmo banco via os
talentos que a 1ª deixou (medido: 156 processados, 2 analisados) e falhava com
uma mensagem que não fala da causa.

A correção é de **RECORTE, não de garantia**: conta-se o resultado dos três
talentos do teste, que é o que cada asserção sempre quis afirmar. O contador
global virou contexto da mensagem de erro, nunca critério. Validado por duas
mutações (reaproveitamento desligado; `sem_curriculo` virando `analisado`) e por
três execuções seguidas no mesmo banco sujo.

**Não se resolve apagando os talentos no fim**: o teste morre no meio numa falha
legítima e deixa o banco sujo do mesmo jeito — o problema volta pela porta dos
fundos, e ainda some com a evidência do que falhou.

O `os.environ.update` do topo também foi para `setdefault`: ele SOBRESCREVIA a
`DATABASE_URL` do ambiente, então o teste ignorava para onde o operador o
apontava.

### O smoke test estava quebrado desde a v2.71 — e ninguém viu

Achado ao rodar os portões: **etapa 9, `formato_nao_suportado`**. Na v2.71 o
`detail` do `upload_seguro._conferir` virou DICIONÁRIO (diz a extensão recebida
e a lista de aceitos — a mensagem que a tela mostra a quem está com o celular na
mão), e o smoke ainda comparava com a string antiga.

**O comportamento estava certo; o teste é que ficou para trás.** Ficou invisível
porque **o smoke não roda no CI** — é portão manual. Voltou a **15/15**.

### Portões

| Portão | Resultado |
|---|---|
| 5 testes de entrevistas | **OK**, cada um rodado 2× seguidas no mesmo banco |
| `test_entrevista_anexo` (novo) | **OK** — 19 asserções, 5 mutações reprovaram |
| `test_match_persistencia` | **OK** — 3 execuções seguidas em banco sujo |
| Os 5 com a senha do CI, em banco novo | **OK** — a condição real do pipeline |
| `smoke_test.py` | **15/15** (estava vermelho) |
| Demais testes do CI | **OK** — 10 arquivos, sem regressão |
| `npm run build` | **OK** — 6,21s |

Nenhum arquivo de aplicação foi alterado: `git diff` de `app/` vazio ao final,
resíduo de mutação zero.

---

## [2.71.0] — 2026-08-06 — O documento do candidato não fica no disco

Primeira leva de pendências levantadas depois do incidente da v2.70. Quatro
itens fechados, todos verificados no código antes de mexer — vários que os
documentos listavam como abertos já tinham sido feitos e foram descartados.

### O spool que ficava no container — no fluxo de MAIOR volume

`documentos.py` (envio pelo candidato, rota **pública**) e `rh_ficha.py`
(inserção pelo RH) liam o upload com `up.file.read()` cru, **sem `close()` em
lugar nenhum do arquivo**. O Starlette faz spool em disco acima de ~1 MB, então
cada RG, CPF e certidão ficava de temporário no container — e num LOOP, um por
arquivo enviado.

É o mesmo defeito que criou o `upload_seguro.py` na v2.56. Ele corrigiu creche
e portal, e deixou de fora justamente o caminho por onde passa quase tudo.

**Por que não bastou chamar o `ler_upload` existente:** aquelas rotas são `def`,
não `async def`. No FastAPI, rota síncrona roda no **threadpool**; `async` roda
no **event loop**. E elas fazem OCR pela Mistral com timeout de até 120s —
convertê-las para `async` só para usar a função assíncrona jogaria uma chamada
bloqueante dentro do loop e **travaria a API inteira a cada envio**. Trocaria um
vazamento de arquivo por indisponibilidade.

Daí o `ler_upload_sync`: mesmas garantias, incluindo o `close()` no `finally`,
para rota declarada com `def`. A validação virou uma função só (`_conferir`),
usada pelas duas portas — variante nova não pode "esquecer" uma checagem.

Verificado ponta a ponta na stack real: JPG de **4,90 MB** (bem acima do limiar
de spool) → HTTP 200, slot `enviado`; `.exe` → 422 `formato_nao_suportado`.
`EXTENSOES_COM_WORD` porque a tela oferece `.doc/.docx` — a lista curta
recusaria o que ela mesma ofereceu (armadilha da v2.61).

### SVG na logo era XSS armazenado

`marca.py` aceitava `image/svg+xml` no upload de logo e favicon, e `_servir`
devolvia com esse `media_type` numa rota **pública**, no mesmo domínio do
painel. SVG é código: um `<script>` dentro dele executa quando o navegador
abre, com acesso à sessão de quem estiver logado.

O `upload_seguro.py` já excluía `.svg` pelo mesmo motivo (*"aceitava .exe, .svg
(que carrega script)"*); esta rota nasceu antes dele e ficou de fora.

**Tirado da allowlist E do `_servir`**: só do upload não bastaria — logo enviada
antes da correção continuaria no storage sendo servida como SVG executável.
Sem a entrada no mapa, ela cai no `image/png` do padrão e o script não roda. O
front usa `accept="image/*"`, então nada que a tela prometa é recusado.

### O terceiro caminho de e-mail ainda mentia sobre o anexo

`webhook_email.py:56` mandava todo anexo como `application/pdf` chumbado — o
mesmo defeito que a v2.41 corrigiu no SMTP e a v2.68 no Graph, vivo no caminho
do Power Automate porque **nenhum teste o tocava**. Por ali saem o `.txt` do log
(4×/dia) e o `.ics` do convite de entrevista: declarados como PDF, chegam
"corrompidos" e não abrem, com o arquivo perfeito do outro lado.

Agora deriva de `_tipo_do_anexo`, como os outros dois. Import local, seguindo o
`m365.py` — `email.py` importa este módulo, e import no topo fecharia ciclo.

### Testes que nunca rodaram no CI

De 54 arquivos de teste, **6 rodavam**. O comentário do CI justificava: os que
importam `app.main` "trocariam segundos por minutos de pipeline". Isso deixou de
valer no instante em que a stack Docker passou a subir no mesmo job para o
Playwright — o container `api` já tem tudo instalado.

- **`test_anti_prompt_injection`** entrou no bloco stdlib: o módulo que ele
  exercita importa só `re` e `secrets`, e o cabeçalho do teste já dizia "sem
  banco, sem rede". Cabia ali desde sempre. É a defesa contra currículo com
  instrução escondida, em upload público — regressão que não dá erro, só
  ranqueia errado.
- **Passo novo rodando dentro do container**: `documentos_catalogo` (divergência
  enum × catálogo levanta `RuntimeError` **no boot** — quebra o deploy inteiro),
  `email_templates`, `retomada_acesso` (*"o link IDENTIFICA, nunca AUTENTICA"*)
  e `export_tirvu` (o Tirvu aceita ERRADO desvio de forma — mesmo argumento que
  já colocou o Dexion no CI).

Dois deles **não podiam** rodar no CI como estavam: tinham a senha
`senha-teste-123` escrita na linha do login, enquanto o CI cria o admin com a
senha do `.env` do job. Falhavam com `KeyError: 'token'`, que não diz nada sobre
a causa. Agora leem do ambiente e afirmam o login com mensagem explícita.

A imagem **não** carrega `tests/` (o Dockerfile copia só `app` e `migrations`) —
código de teste em imagem de produção é superfície a mais. São copiados só
durante o CI, com `docker cp backend/tests/.` (o `/.` evita o aninhamento
silencioso que faz o Python rodar a cópia antiga — pego durante a validação).

### Guarda-corpo

`test_upload_fecha_spool.py`, validado por mutação nas duas frentes (remover o
`close()` → reprova; devolver o SVG à allowlist → reprova). Monta um
`UploadFile` real acima do limiar de spool e afirma que ele fecha — inclusive
**quando o arquivo é recusado**, porque recusar e deixar o temporário no disco
seria o pior dos dois mundos. Trava também que as rotas continuam síncronas.

Detalhe pago na escrita: a primeira versão reprovava buscando `up.file.read()`
no texto do arquivo — e achava o **comentário que explica a correção**. Teste
que reprova a documentação do próprio conserto. Agora ignora comentário e
docstring.

## [2.70.0] — 2026-08-06 — A migration que derrubou a API

Incidente de produção, entre 7h e 9h da manhã. O Bruno foi usar o sistema no
meio do expediente e **não conseguia logar**. Foi ao log do banco, viu que "o
backend não estava se comunicando com o banco", rodou uma atualização à mão,
conseguiu entrar — e ficou sem saber se houve dano.

Não houve dano de dado. Mas o que aconteceu merece registro, porque o sintoma
apontava para o lugar errado e a causa é uma classe de erro, não um caso.

### O banco estava bem. A API é que não existia.

A migration `d6f8b2c4e5a7` (v2.69, backfill da ficha de integração do efetivo)
inseria em `assinatura` por SQL cru listando quatro colunas:

```sql
INSERT INTO assinatura (id, candidato_id, documento, aguardando_liberacao)
```

`otp_tentativas` é `NOT NULL` e **não tem `server_default`** — nasceu assim em
`66a5f1cd51a0`. O `default=0` mora no modelo Python, e **SQL cru não passa pelo
ORM**: para aquela instrução, o default simplesmente não existe.

O que escondeu isso até produção: em banco VAZIO o `INSERT ... SELECT` insere
zero linhas e passa verde. É a armadilha do *"só passa em banco limpo"* (v2.14)
**de cabeça para baixo** — aqui o banco limpo é que esconde o defeito. Todo
teste local passou.

E o estrago não ficou contido na migration. O `docker-entrypoint.sh` tinha
`set -e` e roda `alembic upgrade head` **antes** do `exec uvicorn`: o alembic
saindo com código 1 abortava o script e o uvicorn **nunca subia**. Cada restart
repetia a falha. Por isso o sintoma foi "não loga" — não havia backend nenhum
respondendo, e do lado de fora isso é indistinguível de um problema de banco.

O banco ficou parado em `c5e7a9b1d3f4`, uma revisão antes do head, com o valor
`informativo_efetivo` **já commitado** no enum (aquela revisão usa
`autocommit_block`). Estado parcial permanente até a intervenção manual.

Reproduzido em Postgres limpo migrado ao estado pré-v2.64 com candidatos
semeados: `NotNullViolation`, exit 1, banco parado exatamente ali.

### O que a intervenção manual deixou para trás

O `alembic_version` foi para o head e as fichas passaram a existir — mas **as
linhas do backfill nunca foram inseridas**. As 31 que havia vieram da própria
aplicação, via `gerar_docs_do_posto_e_regime`, que usa o ORM e por isso
funciona. Confirmado pelo `\d assinatura` da produção: a coluna segue `not null`
sem default, então aquele INSERT não poderia ter rodado.

Como o alembic já dá `d6f8b2c4e5a7` por aplicada, corrigir o arquivo não a faz
rodar de novo naquele banco — corrige o futuro, não o presente. Daí a
`e9c1a3f5b7d2`, que repete o MESMO recorte com a coluna certa. É idempotente
(`NOT EXISTS`): quem já recebeu a ficha pela tela não ganha uma segunda.

Validado nos dois cenários: banco limpo (3 fichas para os efetivos abertos,
`aprovado` e `intermitente` de fora) e réplica do estado da produção (só os
faltantes recebem, sem duplicar).

### Falha de migration não derruba mais a API

Decisão do Bruno. Schema velho com o sistema no ar é melhor que tela morta: o
login continua, dá para diagnosticar com calma, e o `/api/health` **denuncia** o
atraso (`migracoes.em_dia: false`).

Vale notar o que isso conserta de tabela: aquele campo foi criado na v2.29 para
exatamente este cenário e **nunca poderia ter funcionado** — sem API no ar, não
há `/api/health` para consultar. O docstring da função afirmava, desde então,
que "a API sobe assim mesmo com o schema velho". Descrevia uma intenção que o
`set -e` contradizia. Agora o código faz o que o comentário sempre disse.

### O guarda-corpo

`tests/test_migration_insert_cru.py` — estrutural, stdlib pura, no CI. Percorre
a cadeia de revisões **na ordem de execução**, acumula o DDL (`create_table` +
`add_column`) e cobra que todo `INSERT INTO` liste as colunas `NOT NULL` sem
default que existiam naquele ponto. Validado por mutação: com o INSERT original
ele reprova nomeando `otp_tentativas`.

A ordem cronológica não é detalhe — a primeira versão reprovava
`roteiro_entrevista.tipo`, coluna acrescentada na v2.67 **depois** do INSERT da
v2.66. Teste que reprova código correto é pior que teste nenhum.

### Achado secundário: `env.py` com 8 modelos faltando

`alerta`, `assinatura_entrevista`, `entrevista`, `roteiro_entrevista`,
`solicitacao_assinatura`, `telemetria`, `testagem` e `vaga` não eram importados
em `migrations/env.py`. Sem efeito em runtime (quem registra os modelos é a
cadeia de imports da `app.main`), mas um `alembic revision --autogenerate`
concluiria que essas tabelas "sobram" no banco e geraria um `drop_table` para
cada uma. Dívida acumulada — 6 das 8 são anteriores a esta leva.

## [2.69.0] — 2026-08-05 — O efetivo também recebe a ficha de integração

Primeiro item dos feedbacks de 2026-08-05. O Bruno: *"Ficha de integração não
está sendo gerada para os efetivos, aos moldes das que são geradas para os
intermitentes"*. E, junto: *"o intervalo para o pagamento dos benefícios para
eles é de 1 a 30 e dos intermitentes é semanalmente"*.

### O defeito: um `if` que só olhava um lado

`gerar_docs_do_posto_e_regime` fazia `if candidato.regime == "intermitente"` e
mais nada. O efetivo — a MAIORIA dos admitidos — não recebia ficha de integração
nenhuma.

O que enganava: existe um `informacoes_trabalhador` que **parece** ser a ficha do
efetivo e não é. É um ofício de direitos do kit INFRAERO (CF, CLT, canal de
ouvidoria), só nasce em posto INFRAERO e serve a outro propósito. Quem lesse a
tupla `DOCS_INFORMATIVO` — comentada como *"efetivo/INFRAERO = ..."* — concluiria
que o efetivo estava coberto.

E o comentário do modelo (`candidato.py`: *"Decide qual ficha de integração o
colaborador assina"*) descrevia uma intenção que o código nunca cumpriu para o
lado efetivo. **Ausência de documento não gera erro**: ninguém abre uma tela e vê
"está faltando algo que deveria existir". Por isso durou.

### O que passa a existir

`informativo_efetivo`, ficha de integração espelho da do intermitente — mesmas
seções (boas-vindas, dados, VT, VA, conta salário, ponto Tirvu+, prazos de
assinatura, normativos), nascendo por REGIME e independente de posto, como a do
intermitente sempre nasceu.

**A única diferença de conteúdo é o ciclo de pagamento dos benefícios**, que é o
que o Bruno pediu:

| | Vale-transporte | Vale-alimentação |
|---|---|---|
| **Efetivo** | pago mensalmente, apuração **do dia 1 ao dia 30** | apuração **do dia 1 ao dia 30** |
| **Intermitente** | **semanalmente**, até a quarta-feira da semana seguinte | apuração **semanal**, paga até a quarta-feira seguinte |

Os textos moram em `_CICLO_VT`/`_CICLO_VA`, fora do gerador: quando o RH mudar um
ciclo, muda ali, e a outra ficha não é tocada por acidente. As duas fichas saem
de `_gerar_informativo_integracao` — o corpo é um só, então nenhuma delas
"esquece" uma seção que a outra recebeu.

**Local de trabalho**: o intermitente não é alocado a posto fixo e continua com o
rótulo `GHS - INTERMITENTE`; o efetivo imprime o posto REAL do cadastro.

### Dois defeitos vizinhos, achados no caminho

- **O informativo do intermitente nunca teve bloco de assinatura nem manifesto.**
  É documento assinável, e o PDF saía sem a prova do ato — o `if assinatura:`
  final que todos os outros geradores têm faltava só nele. Agora as duas fichas
  o têm.
- **`solicitacao_assinatura` reescrevia os valores do enum à mão** e já estava
  atrasado: faltava `autodeclaracao_residencia` (desde a v1.92) e faltaria
  `informativo_efetivo`. Passou a derivar de `DocumentoAssinavel`, que é a fonte.

### Backfill: só quem está com a admissão ABERTA

A migration cria a assinatura pendente para `status` anterior a `aprovado`. Quem
já foi aprovado teve o dossiê gerado e muitas vezes já foi efetivado — criar
pendência ali faria o sistema cobrar, de quem concluiu, um documento que não
existia quando aquilo aconteceu. Duas revisões separadas porque o Postgres
proíbe usar valor de enum recém-criado na mesma transação.

### Trocar o regime troca a ficha

Se o regime mudar, a ficha do regime anterior **ainda não assinada** é
invalidada. Sem isso a pessoa deveria as duas e poderia assinar a de um regime
que não é o dela — com os períodos de pagamento errados, que é justamente o que
distingue as duas. Já assinada nunca é tocada: é peça de prova.

### Testes

`tests/test_informativo_integracao.py`, validado por **3 mutações** (reverter ao
defeito original; dar o ciclo semanal ao efetivo; chumbar o posto) — as três
reprovaram. As asserções percorrem a ROTA de convite, não a função interna
(v2.68), e as âncoras dos ciclos são constantes do teste, nunca valores lidos do
sistema sob teste (v2.64). Cobre também o painel de liberação do RH: ficha que
não aparece ali nunca seria disparada ao candidato.

Duas contagens chumbadas em testes de catálogo (`== 11`) passaram a derivar do
enum — número mágico quebra a cada documento novo e legítimo sem apontar defeito,
e incrementá-lo faz o teste deixar de proteger (v2.25).

Smoke 15/15, suíte completa (52 testes) e `npm run build` verdes.

## [2.68.0] — 2026-08-06 — O e-mail sai, mesmo quando o tenant não colabora

§ 16.1 de `docs/planejamento/12-modulo-de-entrevistas.md`. Das 4 respostas que o
Bruno deu em 2026-08-06, **só uma vira código**: o remetente de recrutamento
passa a valer no Microsoft 365. As outras três eram "não", "como está" e
"corrigir o doc" — já registradas no commit `969bd2b`.

### O problema: uma configuração que não configurava nada

A v2.67 criou a chave `email_recrutamento`, e ela mudava o `ORGANIZER` do `.ics`
e o `From` no SMTP. Só que **em produção o envio não passa pelo SMTP** — sai
pela caixa do M365 conectada por OAuth, e o `remetente` era descartado antes de
chegar ao Graph. O RH podia preencher o endereço e nada mudava no e-mail que a
pessoa recebia.

Pior: **a chave não tinha rota nem tela**. Só dava para preenchê-la escrevendo
direto no banco. Um campo configurável que ninguém consegue configurar é uma
funcionalidade que existe só no código.

### São duas metades, e uma não é código

| Metade | Quem faz |
|---|---|
| Passar o remetente ao Graph e usá-lo quando houver permissão | o sistema (esta leva) |
| **Liberar `Send As` do endereço de recrutamento para a conta conectada, no admin do M365** | **o Bruno**, no tenant |

Sem a liberação o Graph responde `ErrorSendAsDenied` e **o e-mail não sai**. Por
isso o desenho tem duas tentativas e nunca desiste da carta: tenta com o
remetente; se a recusa for **de permissão**, reenvia da caixa conectada e
**avisa na tela** o que falta liberar. O convite sempre sai.

> É a regra da v2.00 na terceira variação: erro de **permissão** (permanente,
> resolve-se no admin) ≠ erro de **envio** (transitório, tenta de novo). Tratar
> os dois igual faria o RH achar que o sistema quebrou quando falta um clique no
> tenant — e mexer no lugar errado. Um 500 **não** vira segunda tentativa.

### A distinção que custou uma reprovação nesta leva

`email_recrutamento()` **cai no `smtp_from`** quando a chave está vazia — certo
para o `ORGANIZER` do `.ics`, que precisa de um endereço qualquer. Usar a mesma
função para o `From` do Graph pedia permissão para enviar como a caixa que já se
é: o Graph recusava igual, e o sistema avisava o RH que faltava liberar `Send
As` de um endereço **que ele nunca configurou** — ruído mandando mexer no tenant
sem motivo, e o oposto do cenário 40, que exige silêncio com a chave vazia.

Foi o **teste que reprovou o código**, não o contrário. Ficou a regra, agora em
`config_dinamica.email_recrutamento_escolhido`:

> **O fallback serve para PREENCHER um campo, nunca para pedir uma permissão.**

### Um defeito encontrado no caminho: o `.ics` chegava como PDF

O caminho do Graph tinha `"contentType": "application/pdf"` **chumbado** para
todo anexo — o mesmo defeito que a v2.41 consertou no SMTP, sobrevivendo aqui. O
`.ics` do convite passa por este caminho: com o tipo errado, o Outlook mostra um
anexo em vez de oferecer "adicionar à agenda". Agora o tipo vem da extensão.

### O que foi medido

- **4 mutações** aplicadas e conferidas. A da recusa-que-aborta reprovou 6
  asserções; a que classifica todo erro como permissão, 4; a do fallback no
  `From`, 3.
- **A 4ª mutação NÃO reprovou de primeira** — a asserção do `.ics` chamava
  `_tipo_grafo` isolada e passava verde com `application/pdf` chumbado na
  mensagem. Reescrita para ler o `contentType` da mensagem **real** que
  `enviar_via_graph` entrega ao limite HTTP. É a mesma lição do teste do `.ics`
  na v2.67: **teste que exercita a função interna não prova que a rota a usa**.

### Detalhes

- `services/m365.py`: `enviar_via_graph` aceita `remetente` e devolve
  `{ok, aviso}`; `recusou_por_permissao` classifica a recusa (só 400/403 com
  assinatura conhecida — rede e 500 são falha de envio); `aviso_send_as` monta o
  texto que nomeia a permissão e a conta; `_tipo_grafo` corrige o MIME do anexo.
- `services/email.py`: `enviar_com_aviso` é a porta que devolve `{ok, aviso}`.
  **`enviar_email` continua devolvendo booleano** — os ~40 call-sites do projeto
  não mudaram (há teste cobrando isso).
- `api/configuracoes.py`: `GET/PUT /rh/config/recrutamento`. Vazio é valor
  VÁLIDO (é como se volta ao padrão) — por isso `str` validado à mão, e não
  `EmailStr`, que recusaria a string vazia e deixaria o RH sem como desfazer.
- `rh/Config.jsx`: o card **Endereço de recrutamento**, com o aviso que só
  aparece quando o M365 está conectado — a tela não promete uma exigência que
  não existe.
- `rh/EntrevistasRH.jsx`: o aviso usa `.aviso-inline` (âmbar), **não** `.alerta`
  (vermelho): o convite saiu, e pintar de erro faria o RH reenviar — o que não
  muda nada, porque o que falta é uma liberação no admin.

### Fora desta leva, registrado

- **O `webhook_email.py` tem o MESMO `application/pdf` chumbado** (linha 56).
  Não mexi: é outro caminho de envio, não é o que o Bruno usa, e alargar escopo
  sem pedido é o que esta casa evita. Fica como recomendação.

## [2.67.0] — 2026-08-05 — Documento gerado que não entra no catálogo não existe

Fase 4 do Módulo de Entrevistas (§ 15 de
`docs/planejamento/12-modulo-de-entrevistas.md`). O Bruno respondeu as 5
perguntas em aberto da v2.66 e cravou uma **regra geral**, que é o item mais
importante desta leva:

> *"a cada documento novo gerado, ele deve compor o módulo de documentos também
> e todas as funcionalidades herdadas. bem como os templates de email"*

### Por que isso é uma cobrança, e não um pedido novo

É a regra da v2.21 (*"e-mail novo e documento novo NASCEM na sua página"*)
sendo cobrada — e ela estava sendo cumprida **pela metade**: a v2.66 pôs os 3
e-mails do módulo no `CATALOGO` de `email_templates.py` e
`grep -c "entrevista" services/documentos_catalogo.py` devolvia **zero**,
enquanto o módulo gerava documentos. Documento gerado sem entrada no catálogo é
documento que o RH não consegue ver, conferir nem versionar.

### Os três documentos (§ 15.2)

`entrevista_ficha` (híbrido), `entrevista_triagem` (formulário) e
`entrevista_roteiro` (híbrido), com amostra em PDF a partir de dados
**fictícios que nunca vão ao banco** (id `…0000e7`, o marcador que denuncia
vazamento — há teste).

**O catálogo ganhou DUAS famílias em vez de valores novos no enum.** A
alternativa óbvia — acrescentar `entrevista_ficha` ao `DocumentoAssinavel` —
seria destrutiva por dois caminhos que só aparecem lendo o código:
`api/rh_ficha.py:38` faz `_TODOS = list(DocumentoAssinavel)` e usa a lista em
`DOCS_POR_SECAO`, então **editar os dados pessoais de alguém passaria a
invalidar a ficha de entrevista dele**; e `_docs_exigidos` faria a ficha virar
pendência de assinatura do candidato no wizard. `_conferir_catalogo` agora
cobra a cobertura exata do enum para a família `admissao` e **reprova no import
se um documento de entrevista virar valor do enum**.

Nenhum gerador existente foi substituído (regra da v2.19): o hash do ato de
assinatura é calculado sobre o PDF gerado.

### A ficha é assinável pelo RH que conduziu (§ 15.3)

Logado, com a senha da própria sessão (`prova_metodo="senha_sessao_rh"`, o
método de `solicitacoes_assinatura.py:400`). O entrevistado **não** assina —
exigiria mandar link a quem talvez não seja contratado, e o link lhe daria
acesso às notas escritas a seu respeito. Assinar de novo cria a via SEGUINTE; a
anterior permanece com o hash dela (regra de 2026-07-15).

### E NÃO entra no dossiê de admissão (§ 15.4)

O Bruno incluiu e corrigiu na mesma sessão: *"não não. no dossiê de admissão
não."* Mesma regra que manteve resultado de teste fora do dossiê na v2.21 — **o
dossiê circula** (cliente, pasta física) e nota de seleção com justificativa é
dado sensível.

**A garantia é ESTRUTURAL, não uma lembrança.** `services/dossie.py` varre toda
`SolicitacaoAssinatura` concluída com `pdf_final_key` **sem filtrar `origem`**:
assinar a ficha por ali a colocaria no dossiê automaticamente, com uma página a
mais que ninguém veria. Por isso a assinatura mora em tabela PRÓPRIA
(`assinatura_entrevista`), fora das três fontes que o dossiê lê. Coberto por
mutação: incluir a ficha no `gerar_dossie` faz o teste falhar (o dossiê medido
foi de 0 para 2 páginas).

### As outras quatro respostas (§ 15.5)

1. **Vaga passa pela lixeira** — `DELETE /rh/vagas/{id}` era a única exclusão do
   painel que era delete FÍSICO. O `ondelete=SET NULL` + `vaga_titulo`
   **continuam**: a lixeira guarda a vaga, o snapshot mantém a entrevista
   legível — e se um dia a lixeira for expurgada (o prazo é configurável), a
   entrevista continua dizendo para qual vaga a conversa foi.
3. **Triagem editável** — entra no mesmo catálogo como `tipo=triagem`, mesma
   mecânica rascunho→publicado, e **continua sem nota, sem competência e sem
   âncora**: `validar_roteiro_triagem` recusa com 422 que NOMEIA o campo
   proibido. Triagem publicada sem pergunta nenhuma também é recusada (cenário
   35) — checagem vazia não é checagem.
4. **`duracao_min`** na entrevista, padrão 60, alimentando o `DTEND` do `.ics`.
   Zero ou negativo é recusado (cenário 37): `DTEND` anterior ao `DTSTART` faz o
   calendário de quem recebe descartar o evento.
5. **`email_recrutamento`** na config dinâmica, usada no `ORGANIZER` do `.ics` e
   nos e-mails de entrevista, **caindo no `smtp_from` quando vazia** (cenário
   36) — nunca falha por estar em branco. Limite registrado com honestidade: o
   override de remetente vale no caminho SMTP; nos caminhos M365/Google/webhook
   a mensagem sai da caixa conectada por construção, e forjar o `From` ali daria
   e-mail rejeitado — pior que sair do endereço de sempre.

### Um padrão por TIPO — defeito achado pela suíte antiga

A semente da triagem nasce `padrao=True`, e a listagem mostrava os dois tipos
juntos: apareciam **dois** padrões, e "qual é o padrão?" deixava de ter
resposta. Pior, o `tornar-padrao` desmarcava o padrão do OUTRO tipo, deixando a
triagem sem fundo de herança — a ficha abriria sem pergunta nenhuma, **sem erro
na tela**. Hoje a listagem, as métricas, o `tornar_padrao` e o
`resolver_roteiro` são todos recortados por tipo.

### O que foi conferido na TELA, não só no código

- **Título de seção órfão no PDF do roteiro**: a faixa "COMPETÊNCIA: CUMPRIMENTO
  DE NORMA E PROCEDIMENTO" caía na última linha da página 1 e a tabela dela
  abria na página 2. O `set_auto_page_break` do fpdf garante que a FAIXA caiba,
  não que caiba a faixa mais o que vem depois. A extração de texto passava.
- **Rótulo mentindo na tela de roteiros**: o `<details>` dizia "ver as
  competências e âncoras deste roteiro" **em roteiro de triagem**, que não tem
  nem uma nem outra — e a lista abria vazia.

## [2.66.0] — 2026-08-05 — O roteiro tem que ser aprovado antes de ser usado

Fase 3 do Módulo de Entrevistas — os quatro pedidos do Bruno depois de ver a
v2.64 rodando (§ 14 de `docs/planejamento/12-modulo-de-entrevistas.md`). Um
deles reorganiza o módulo; três são encaixes.

### Roteiros múltiplos — o instrumento saiu do código e virou dado (§ 14.1)

Até a v2.65 as 4 competências eram uma constante em `services/entrevistas.py`.
Agora são um **catálogo no banco** (`roteiro_entrevista`), e a migration
**semeia o roteiro padrão a partir da própria constante** — importada, nunca
copiada à mão: cópia passa a divergir da origem na primeira revisão dela e
ninguém percebe (a lição do `test_export_dexion`).

**Isso resolve a pendência nº 1 do documento por outro caminho.** Em vez de
esperar o Bruno aprovar as âncoras que a sala escreveu, ele passa a editá-las
pela tela, sem deploy.

Três decisões que sustentam o resto:

- **Rascunho → publicado, e só publicado se usa.** Não é burocracia: é o que
  sustenta o argumento jurídico do § 6. A defesa perante a Lei 9.029/95 não é
  "existe um roteiro", é **"o roteiro foi aprovado ANTES de ser usado"**. Sem a
  trava, o argumento cai. Publicar é ato separado, com autor e data na
  auditoria.
- **Versão congelada por SNAPSHOT.** A `Entrevista` guarda `roteiro_id` **e**
  `roteiro_snapshot` (JSON), pelo mesmo motivo do `vaga_titulo`. Editar um
  roteiro publicado gera a versão seguinte e o devolve a rascunho; a entrevista
  já feita continua mostrando o instrumento com que foi feita. Ler do roteiro
  vivo mostraria o texto de HOJE numa avaliação de meses atrás — e a nota
  deixaria de significar o que significava. **Coberto por mutação.**
- **Herança cargo → senioridade → padrão**, casando por `normalizar_cargo` (a
  mesma função do de-para do Tirvu, porque cargo é texto livre). Cargo sem
  roteiro **cai no padrão, nunca em erro**.

**O contrato com o front não mudou — a FONTE mudou.** `GET /rh/entrevistas/formulario`
continua sendo de onde a tela lê, e o teste estrutural que varre o JSX
procurando texto duplicado continua valendo (agora inclui as perguntas novas).

**Achado durante as mutações, e o defeito é real:** a mutação que removia o
guard de arquivar deixou o roteiro padrão `arquivado` — e a partir dali
`resolver_roteiro` devolvia `None`, ou seja, **toda ficha abriria vazia, sem
erro nenhum**. A tela pareceria funcionar e a entrevista seria conduzida sem
roteiro, que é exatamente o que o § 6 existe para impedir. Ganhou rede de
segurança: qualquer roteiro publicado sem cargo serve de fundo, e na falta de
todos vale a constante-semente. O guard das rotas continua (o padrão não se
arquiva nem se apaga), mas "não deveria acontecer" não é garantia.

### Mais perguntas de triagem (§ 14.2)

Quatro acréscimos — disponibilidade imediata, documentação em mãos, já
trabalhou no cliente, aceita uniforme/EPI. Todas passam nos três filtros do
critério do Bruno (*"desde que sejam coerentes e coesas"*): responde-se
sim/não/não sei, responde-se por telefone em segundos, e prediz **desistência**,
não desempenho. **Continua sem nota, sem competência e sem âncora** — triagem
não é entrevista curta.

O `test_entrevistas.py` cobrava `len(perguntas) == 5` e quebrou. O assert virou
derivação da NATUREZA (todas sim/não/não sei, nenhuma com âncora) em vez da
contagem — a lição da v2.25: teste que trava contagem de catálogo quebra a cada
acréscimo legítimo, e incrementar o número faz o teste não proteger nada.

### Tag de reaproveitamento (§ 14.3)

> *"quando excluir uma vaga, a entrevista sobrevive, pois posso poder taguear a
> pessoa, de modo que ela possa ser reaproveitada para outro cargo"*

Ele resolveu o cenário 4 melhor do que a sala: a entrevista já sobrevivia (com
`vaga_titulo`), mas isso preservava **o registro**; o que ele quer é preservar
**a pessoa como oportunidade**. E o sistema já tinha a peça — `PessoaTag` do
mini-CRM, com catálogo, CRUD e as mesmas duas FKs opcionais. **Nenhum campo
novo, nenhuma tela nova** (as tags já filtram no dash de Talentos).

**Proposta, nunca automática**: o sistema sugere o nome da tag a partir do cargo
da vaga e mostra quem foi entrevistado; o RH confirma. Tag aplicada sozinha vira
ruído e o RH deixa de confiar na tag. Pessoa entrevistada duas vezes conta uma
vez, e o lote presta contas de quem não deu.

### Lembrete por e-mail e convite de calendário (§ 14.4)

`modalidade` (`presencial` | `online`) decide o resto: endereço × link da
reunião. **Online sem link não se marca** — o convite sairia sem dizer por onde
entrar. Três entradas novas no `CATALOGO` de e-mails (marcada, lembrete,
cancelada), editáveis com preview e histórico pela regra da v2.21;
`{{data_hora}}` e `{{onde}}` são obrigatórias, e `{{onde}}` é montada em Python
conforme a modalidade — o template é apresentação, nunca decisão.

O `.ics` é gerado sem biblioteca, com os três cuidados que o documento cravou:

1. **UID estável por entrevista + SEQUENCE que cresce.** É o par que faz o
   Outlook ATUALIZAR o compromisso em vez de criar um segundo. UID novo a cada
   remarcação encheria a agenda da pessoa de entrevistas fantasma no horário
   antigo — o defeito mais caro possível num convite. Coberto por mutação.
2. **Cancelar manda `METHOD:CANCEL` com o mesmo UID**, senão o compromisso fica
   na agenda depois de cancelado e a pessoa vem.
3. **`TZID=America/Sao_Paulo`**, com `VTIMEZONE` declarado. O container roda em
   UTC (armadilha da v2.41) e o convite chegaria três horas adiantado.

**Sem e-mail, o lembrete fica desligado COM o motivo na tela** — nunca falha
calada. Falha de envio nunca derruba a ação: marcar a entrevista é o ato
principal, e SMTP fora do ar não pode impedir o RH de registrar o compromisso; o
resultado é anunciado, não engolido.

**O worker do lembrete mora dentro do `avisar_vencimentos`** (já é cron, já tem
anti-spam) — e aí veio o segundo achado: **`avisar_vencimentos` NÃO ESTAVA no
`deploy/portainer-stack.yml`**. O compose local o rodava; produção, não. Ou
seja, o aviso de certificação vencendo (Onda B, v1.83) **nunca saiu na VPS**, e
o lembrete de entrevista teria herdado o mesmo silêncio. Corrigido no mesmo
commit. Worker que não está nos DOIS arquivos simplesmente não roda, e nada
avisa.

A janela do lembrete é de **36h, não 24h**: o worker dorme 86400s, e com janela
de 24h exatos a entrevista marcada para daqui a 23h ficaria invisível entre duas
passadas — o lembrete nunca sairia, em silêncio. A janela precisa ser maior que
a cadência; o anti-spam é o carimbo, não a janela.

### Tela

`Configurações → 🗣️ Roteiros de entrevista`, junto dos outros catálogos — não é
tela de uso diário. Segue a composição corrigida na v2.65 (`.rh-conferencia`,
`.chips-escolha`, `.rh-conferencia-acoes`), e a conferência foi feita na tela
RENDERIZADA: a primeira versão punha o formulário inteiro em duas colunas e
deixava a coluna esquerda **vazia por ~1.100px** enquanto a direita esticava. A
primitiva de 2 colunas serve conteúdo EMPARELHADO (âncora ao lado da pergunta),
não bloco curto ao lado de bloco longo. Só aparece na tela; no código as duas
versões parecem igualmente razoáveis.

### Fora, e por quê

**Segundo avaliador com trava anti-peeking** continua fora: só o RH entrevista
(decisão 1), e não há colega cuja nota espiar. **A exclusão de vaga continua
sendo delete físico** — o Bruno respondeu o que importava (a pessoa é tagueada),
mas não disse se a vaga em si vai para a lixeira; mudar exclusão de outro módulo
é escopo que ele não pediu. Registrado como recomendação.

## [2.65.0] — 2026-08-05 — Passar no teste não é seguir o padrão

Correção **só visual** da tela de Entrevistas. Nenhuma mudança de backend,
schema, rota ou regra de negócio — o diff é de três arquivos JSX, e o
`styles.css` **não foi tocado** (zero classe nova).

O Bruno reprovou o visual da v2.64: *"você fugiu do padrão visual da página de
entrevistas. NÃO INVENTE NADA QUANTO A ISSO. Siga padrões já estabelecidos"*.
Ele está certo, e o mais importante é **por que a tela passou pelo guarda-corpo
assim mesmo**: o `test_design_system.py` deu verde nos 6 itens — zero classe
fantasma, zero token inexistente, zero `<select>` nativo, tabela em
`.dash-scroll`. A tela tinha o vocabulário certo e a composição errada.

**A lição, que vale para toda tela futura:** o teste estrutural cobre
VOCABULÁRIO (a classe existe? o token existe?), não COMPOSIÇÃO (qual primitiva
serve a qual papel). É a v2.25 numa variação nova — lá a tela saiu crua porque
as classes não existiam; aqui ela saiu estranha porque as classes existiam e
eram as erradas para o papel. Antes de escrever formulário novo, abra a tela
equivalente que já existe e copie a composição dela.

A referência canônica de formulário longo é o `FormularioAvaliacao.jsx` (o
formulário da cartilha). O que mudou, medido no navegador:

- **A escala de nota voltou a ser escala.** As notas 1–4 eram um `SelectBusca`
  — uma lista suspensa para escolher entre quatro opções, num instrumento cujo
  ponto inteiro é comparar âncoras. Agora são `.chips-escolha`/`.chip-escolha`,
  todas à vista, a escolhida marcada, um clique (o mesmo `TabelaEscala` da
  cartilha). A regra da casa é *"nunca `<select>` nativo"* e ela **não** implica
  *"sempre SelectBusca"*: `.chips-escolha` não é um select, é a primitiva
  específica de escala de nota. A infraestrutura já estava lá sem uso —
  `.chip-escolha` com 5 regras e `.rh-escala` com 7 no `styles.css`. Clicar no
  chip marcado desmarca (antes, a opção "— sem nota —" fazia esse papel).
- **Um `.rh-conferencia`, não N cards.** A ficha empilhava um `.rh-card` com
  borda e sombra POR COMPETÊNCIA (4 cards + 2). Medido depois: **0 `.rh-card`
  dentro da ficha**.
- **Duas colunas.** Passou a usar `.rh-conferencia-corpo` — competências à
  esquerda, justificativas à direita, com a nota repetida no rótulo da
  justificativa. Antes era pergaminho vertical de coluna única. Grid real
  medido: `454px 545px` em 1440 e `376px 451px` em 1150.
- **`<label className="rotulo">` era regressão funcional, não só estética.** As
  14 ocorrências eram as ÚNICAS do repositório (contra 202 `<span
  className="rotulo">` dentro de `<label className="campo">`), e como o `<label>`
  não tinha `htmlFor` nem envolvia o controle, **clicar no rótulo não focava o
  campo**. Zeradas.
- Botões soltos separados por `{' '}` viraram `.rh-conferencia-acoes` com
  `btn-mini`; `<h4>` cru virou `.rh-conferencia-bloco-titulo`; `.explica` ao
  lado de rótulo virou `.dica-inline`; e o bloco "aguardando desfecho" virou
  `.aviso-inline` (é aviso, não card).
- **Triagem também é instrumento**: as 5 perguntas viraram linhas de
  `.rh-escala` com Sim/Não/Não sei em chips — antes era um `SelectBusca` por
  pergunta, cinco listas suspensas para responder sim ou não. O desfecho idem.
  O aviso de que seguro-desemprego **nunca é critério de exclusão** continua na
  tela, agora como `.dica-inline` na própria pergunta.
- `EntrevistasDaPessoa` estava sem classe onde o irmão `EntrevistasDaVaga` usava
  `.rh-card` no mesmo papel; ambos agora são `.rh-card` — que é também o que o
  vizinho direto (`TestesVinculados`) faz na mesma posição do `<details>` do
  `Detalhe.jsx`.

Conferido RENDERIZADO com Playwright, lado a lado com a tela de Avaliações, nos
dois temas e nas duas larguras (1440 tabela / 1150 card): 22 chips com 3
marcados, 0 `label.rotulo`, 0 `.rh-card` na ficha, 0 `<h4>`, 0 `SelectBusca`, e
**0px de estouro horizontal** nas quatro combinações. `tabelas-cabem-na-tela`
verde nas 5 larguras (8/8); `test_design_system` verde nos 6 itens;
`test_entrevistas` e `test_entrevista_arquivamento` verdes — inclusive o guarda
estrutural de que o front NÃO duplica texto do instrumento.

Divergência registrada, sem mudar nada: o `08-sistema-de-design.md` (linhas
70–74) pede `.pagina` para tela nova, mas a prática são **17 telas com
`.rh-painel` contra 4 com `.pagina`**, incluindo as três telas de referência.
Entrevistas segue `.rh-painel` como as vizinhas. Qual das duas corrigir — o doc
ou as 17 telas — é decisão do Bruno.

## [2.64.0] — 2026-08-05 — A conversa que não deixava rastro

Módulo de Entrevistas (fases 1 e 2 do
`docs/planejamento/12-modulo-de-entrevistas.md`). Entre "o RH olhou o currículo"
e "o RH mandou o convite" acontecia uma conversa que **não deixava rastro
nenhum** — virava, na melhor das hipóteses, uma anotação solta: *"entrevistei,
gostei, mandar convite"*. Isso falhava em três frentes: não dava para
**comparar** (com três entrevistados, "gostei dele", "pareceu boa" e "achei meio
devagar" não decidem nada), não dava para **prestar contas** de por que aquela
pessoa foi escolhida, e não **protegia a empresa** — sem roteiro, o que foi
perguntado dependia de quem perguntou, e há perguntas que a Lei 9.029/95 veda.

Não é módulo novo: é o degrau que faltava no funil que já existe. Não inventa
entidade de pessoa, formulário nem mecanismo de acesso — costura peças prontas.

### Duas fichas, porque são coisas de natureza diferente

- **Triagem** — checagem de viabilidade por telefone, **sem nota, sem
  competência, sem âncora**. Em terceirização a desistência raramente é por
  incapacidade: é escala que não cabe na vida, local inacessível, salário abaixo
  do esperado. Cinco perguntas de sim/não decidem se vale gastar uma hora
  presencial. **Seguro-desemprego entra aqui e NUNCA é critério de exclusão** —
  é dado que explica falta e desistência, e a tela diz isso em voz alta.
- **Entrevista** — avaliação ancorada: 4 competências, escala **1–4 sem ponto
  médio** (com 1–5 o avaliador foge para o 3), **justificativa obrigatória em
  cada uma**. Nota sem evidência é ruído: o 422 **nomeia** a competência que
  falta, porque "preenchimento inválido" faz o RH procurar qual das quatro.

Quatro competências e não oito: com 15, preenche-se no automático; com 4,
pensa-se. Cada uma tem **duas variantes da mesma pergunta** — comportamental
para quem tem experiência, situacional para quem não tem. A comportamental
("conte uma vez em que…") exige que a pessoa tenha uma história para contar, e
com quem nunca trabalhou formalmente ela mediria currículo, não competência.
Competência, escala e âncoras são idênticas nas duas: duas portas, mesma sala.

### O sistema pergunta, nunca conclui

Entrevista cuja data passou e ninguém preencheu vira **pendência que cobra** —
card próprio no topo da lista. **Jamais** é marcada como "não compareceu"
sozinha: silêncio não é falta. É a mesma lição do `00:00` no import de ponto,
onde tratar registro incompleto como falta acusaria 28 pessoas injustamente.
Há teste por mutação: fazer o sistema concluir sozinho reprova a suíte.

### Arquiva, não apaga

Retenção de 180 dias configurável, no `workers/expurgo.py` que já roda diário.
O Bruno respondeu fora do menu de três opções que a sala ofereceu — todas
assumiam apagar algo. **Arquivar resolve a tensão que as outras não resolviam**:
nota velha não deve assombrar quem se candidata de novo dois anos depois, mas
reentrevistar quem faltou três vezes sem saber é desperdício. Sai da vista e das
métricas; a memória continua acessível a quem procurar. Entrevista de quem virou
**colaborador fica fora do prazo** — é parte do vínculo, não material de
recrutamento com validade.

### O que se reusou em vez de reinventar

- **Identidade da pessoa**: as DUAS FKs opcionais do mini-CRM
  (`talento_id`/`candidato_id`). Com FK única, a entrevista feita com o talento
  **sumiria** da ficha do candidato depois do `converter()` — que é justamente
  quando ela mais importa. Teste por mutação cobre isso.
- **Instrumento em constante de módulo**, nunca no banco (padrão da cartilha de
  desempenho): o front lê de `GET /rh/entrevistas/formulario` e **não duplica
  nenhum texto**. Há teste estrutural que varre o JSX e reprova a duplicação —
  mudar uma âncora é mexer num arquivo só.
- Anexo, listagem `{itens, metricas}`, `DashPlanilha` com detalhe **na linha**,
  `SelectBusca`, auditoria e lixeira: tudo padrão da casa.
- **Ao concluir, escreve uma `Anotacao` no mini-CRM** — a entrevista não *é* uma
  anotação (o valor está na nota ancorada comparável), mas o histórico da pessoa
  continua num lugar só.

### A vaga pode ser excluída; a entrevista sobrevive

`DELETE /rh/vagas/{id}` é delete **físico** e não passa pela lixeira. Por isso
`ondelete=SET NULL` **e** snapshot `vaga_titulo`: a entrevista sobrevive com o
nome da vaga preservado, e a tela avisa "vaga excluída". A recomendação de
passar a exclusão de vaga pela lixeira fica registrada — mudar exclusão de outro
módulo não estava no pedido desta leva.

### Medido na tela, não no código

O screenshot pegou dois defeitos que a leitura não pega: a tabela exigia **56px
além da área visível em 1440px** (a coluna "Desfecho / recomendação" com 20% e
"Situação" com 17% — o chip "⚠ aguardando desfecho" por extenso não quebra
linha), e o rótulo "+ Triagem" partia em duas linhas. Correções: o chip virou só
o sinal **⚠** com o texto no `title` (o card do topo já anuncia por extenso),
"Entrevistador" nasce oculta (com um só entrevistador repete o mesmo nome em
toda linha) e `white-space: nowrap` entrou na regra base do botão no
`styles.css` — não em `style` inline. Depois: **−2px** (cabe) e altura de linha
de 126px para 96px. A tela nova entrou em `TELAS` do
`tabelas-cabem-na-tela.spec.js` **no mesmo commit**.

### Testes

Os 8 testes de comportamento da seção 11 do documento + o design system, todos
**validados por mutação** (5 mutações aplicadas e revertidas; cada uma fez a
suíte falhar). Uma delas reprovou o **próprio teste**: a asserção do snapshot da
vaga comparava a resposta com uma variável lida da mesma resposta — tautologia
que passava com o defeito presente. Agora compara com uma constante conhecida.
O teste de N+1 compara **duas listagens de tamanhos diferentes** em vez de um
limite absoluto (que mediria o tamanho do banco): 2 registros → 3 consultas,
8 registros → 3 consultas.

### Fase 3 — não entregue, e por quê

Lembrete por e-mail, convite de calendário (.ics), segundo avaliador com trava
anti-peeking e roteiro por cargo **dependem de decisão do Bruno** e ficaram de
fora deliberadamente. Registrar a pergunta é entrega; respondê-la sozinho seria
inventar produto no lugar dele. Detalhes em
`docs/planejamento/12b-entrevistas-relatorio-execucao.md`.

## [2.63.0] — 2026-08-02 — O card não é um pergaminho

Print do Banco de Talentos ainda ruim, e uma pergunta do Bruno sobre os dados
de teste que criei. As duas coisas tratadas.

### O modo card tinha o mesmo defeito, virado de lado

As correções anteriores mediram o modo TABELA. No modo CARD (abaixo de 1250px),
uma linha do Banco de Talentos chegava a **491px de altura** — o card ocupava
quase a tela inteira, e o RH via uma pessoa por vez. Três causas somadas:

1. **Botões empilhados na vertical.** A regra do card usava `flex: 1 1 auto`,
   herança de quando `.acoes-candidato` era flex; desde a v2.59 ela é **grid**, e
   `flex` não faz efeito ali — cada botão virava uma fileira. Agora é
   `repeat(auto-fit, minmax(9rem, 1fr))`: os botões se distribuem pela largura,
   preservando a área de toque de 44px.
2. **Campo vazio virando linha.** "TAGS —" e "TESTE —" ocupavam altura para
   dizer que não há nada. Já existia regra para célula `:empty`, mas o
   `DashPlanilha` preenche com travessão — a célula nunca ficava vazia de fato.
   Agora ela é marcada com `dash-vazio` (inclusive quando o `render` devolve
   "—") e some **no card**; na tabela o travessão continua, porque ali a coluna
   precisa alinhar com o cabeçalho.
3. **Um campo por linha, de largura total.** Com 8-9 colunas, o card virava uma
   coluna de 9 linhas. Passou a ser **grade de duas colunas**
   (`auto-fit`/`minmax`), voltando a uma no celular sem media query extra. A
   coluna de ações e o checkbox atravessam a grade inteira.

Resultado medido: Talentos **491px → ~120px**; Desenvolvimento 330px,
Jornadas 268px e Colaboradores 245px, todos abaixo do teto.

### A régua, de novo

O teste de altura rodava **só em 1440px** — modo tabela. O defeito estava no
card. Agora roda nos dois modos (1440 e 1150), com teto próprio para cada um:
no card a linha é naturalmente mais alta (rótulo ao lado de cada valor, botão
com área de toque), mas 240px já significa card ocupando meia tela.

Validado por mutação: devolver o card ao empilhamento faz o teste de 1150px
falhar apontando as três telas.

### Sobre os dados de teste

O Bruno perguntou se eu estava gravando coisas nas informações globais. Estava
— no banco **local** de desenvolvimento, para reproduzir o volume real (a base
tem 1171 colaboradores; eu media com 19). Tudo removido e conferido: 40
colaboradores, 30 jornadas, 30 talentos, o usuário de medição e o posto de
teste. Os três colaboradores reais que eu havia apontado para esse posto
voltaram a ficar sem posto, como estavam. **Nada disso tocou produção** — o
ambiente é o `deploy-*` da máquina local.

## [2.62.0] — 2026-08-02 — A régua tinha buraco: 1200px e Jornadas

Prints do Bruno mostrando Colaboradores, Talentos e Jornadas **ainda cortando**
— depois de duas versões consertando exatamente isso, e com o teste de
regressão passando.

### Por que o teste não pegou

Três falhas minhas, e a primeira é a que ensina:

1. **A régua media três pontos, não a faixa.** O teste rodava em 1024, 1280 e
   1440 — e **pulava justamente 1150–1249**, onde o modo card já saíra (limiar
   de 1100px) mas a tela ainda era estreita. Medido depois: Colaboradores
   estourava 53px, Talentos 78px e Jornadas **223px** nessa janela.
2. **Jornadas nem estava na lista de telas testadas** — e era a que mais
   estourava, em quase toda largura.
3. **Medi com 19 registros; a base real tem 1171.** Com poucos dados, textos
   longos não aparecem e as colunas não incham. Reproduzi o volume e o
   conteúdo reais (posto de 86 caracteres, talento com quatro cargos) antes de
   consertar.

### O que mudou

- **Limiar do modo card: 1100px → 1250px.** Abaixo disso a tabela vira card,
  onde nada fica fora da vista. Foi o que zerou a faixa inteira; as telas com
  8–9 colunas não cabem em 1200px por mais CSS que se escreva.
- **Coluna de ações agora CEDE**: `clamp(17ch, 16vw, 24ch)` em vez de largura
  fixa. Em tela estreita ela era o maior peso da tabela (234px de ~1150).
- **Cinco colunas passaram a nascer ocultas**, todas com o filtro mantido na
  barra: CPF em Colaboradores (busca-se na barra, que aceita nome/e-mail/CPF),
  Currículo em Talentos (quem tem já mostra o atalho embaixo do nome), Ad.
  noturno e Intrajornada em Jornadas (são Sim/Não que se filtram).

### A régua consertada

O teste passou a medir **5 larguras × 7 telas** (era 3 × 6), com 1150 e 1200
incluídos e Jornadas na lista. Validado por mutação: devolver o limiar a 1100px
faz falhar exatamente 1150 e 1200 — as duas que antes escapavam.

Validação: 25 testes E2E, telas conferidas renderizadas em 1200px e 1440px com
dados de volume realista.

## [2.61.0] — 2026-08-02 — A câmera guiada e o timbrado em todo lugar

> *"ainda sobre o reembolso creche ou qualquer outra área que a pessoa tem que
> subir fotos, documentos ou arquivos, quero que utilize o que montamos e
> validamos de câmera, ficou legal, bem como, para o RH e/ou quando gerar o
> dossiê, já vir no padrão conforme documentos anteriores no timbrado da
> empresa."*

Último item da leva de feedbacks de 2026-08-02.

### O documento agora sai no papel timbrado

Creche e portal do colaborador gravavam o arquivo **cru**: a certidão
fotografada ficava como um `.jpg` no MinIO, enquanto a mesma foto enviada pelo
wizard da admissão virava uma A4 timbrada. Agora os dois passam pela **mesma**
`normalizar_para_pdf` — que, além do timbre, converte HEIC (foto de iPhone),
recusa imagem borrada ou pequena demais e valida que o PDF abre.

**Falha de conversão NÃO perde o documento.** Formato exótico, foto ilegível ou
PDF protegido caem no original. Recusar deixaria a pessoa sem conseguir enviar a
certidão do filho — e o benefício travaria pela qualidade de uma foto, não pelo
direito dela. O RH ainda vê o arquivo; só não sai timbrado.

No dossiê, cada folha passa a dizer **de quem é**: o rótulo leva o nome da
criança (`certidão de nascimento — Mikael`). Antes o cabeçalho saía genérico, e
num dossiê com dois filhos nada distinguia uma página da outra.

### A câmera guiada chegou ao creche e ao portal

A mesma do wizard — moldura, aviso de foto tremida ou escura em tempo real,
recorte antes de enviar, e o botão "já tenho o arquivo" por dentro, para quem
prefere escolher do aparelho. No portal isso resolve um caso concreto: quem usa
aquela tela é o bombeiro civil no plantão, no celular.

A legenda do portal já dizia *"pode fotografar com o celular — só confira se
está legível"*. Agora a câmera é quem confere.

**O currículo do Banco de Talentos continua com o seletor de arquivo** (decisão
do Bruno): é PDF ou Word que a pessoa já tem no celular, e a câmera
acrescentaria um passo para quem só quer anexar. Coerente com o backend, que
guarda o currículo **original** desde a v2.33 — é documento de terceiro, e o RH
precisa dele como veio.

### Dois detalhes que teriam mordido

- O `ler_upload` do creche (v2.56) **não aceitava Word**, mas a câmera oferece
  `.doc/.docx` no seletor: um envio que a própria tela ofereceu seria recusado
  com "formato não suportado". Passou a usar `EXTENSOES_COM_WORD`.
- No portal, o **OCR lê o original** e o **hash descreve o gravado**. Trocar a
  ordem faria a leitura assistida trabalhar sobre a foto reduzida dentro de uma
  A4 (pior) ou o hash apontar para um arquivo que não está no storage (inútil
  para conferir integridade).

Validação: smoke 15/15, 23 testes E2E, PDF conferido renderizado em imagem, e as
mutações do teste novo detectadas — inclusive a que volta a gravar cru.

## [2.60.0] — 2026-08-02 — Texto longo tem reticências, e nada mais vaza

Três prints depois da v2.59 mostraram que eu tinha resolvido o problema pela
metade — e criado outro.

### Tirar a rolagem lateral não pode criar rolagem vertical

O posto `SESI-DF - 22/2026 - BRIGADISTA, RECEPÇÃO, GARÇONARIA, PORTARIA E
LIMPEZA E CONSERVAÇÃO` (86 caracteres) quebrava em **seis linhas**, e a tabela
de Colaboradores passou a mostrar **duas pessoas por tela**. O RH deixou de
rolar para o lado e começou a rolar para baixo: não é melhor, é outro tipo de
ruim.

Agora texto longo é **cortado na 3ª linha com reticências**, e o texto inteiro
aparece ao parar o mouse — exatamente o que o Bruno propôs: *"para textos
longos ter reticências e, se parar o mouse, aparecer o texto completo"*. A
linha de Colaboradores caiu de **188px para 115px**.

Detalhe técnico que custou uma medição: o `line-clamp` **não funciona na
`<td>`**. O navegador força `display: flow-root` em célula de tabela e engole o
`-webkit-box` — o `clamp: 3` aparecia no computed style e a altura não mudava.
O corte precisa de um elemento interno (`.dash-corta`), que o `DashPlanilha`
agora injeta sozinho em toda coluna `quebra: true`.

### Os botões vazavam em outros lugares além da tabela

O primeiro print era do **checklist de documentos**, não do dash: `Ver /
Aprovar / Rejeitar / Inserir` saindo pela borda do card. A causa era a mesma da
v2.59 em outro lugar — `display: flex` **sem** `flex-wrap`, que faz o flex
preferir estourar o container a quebrar a linha. Ali a quebra só valia abaixo
de 480px.

Como o Bruno pediu que virasse padrão global *"e para serem adotados daqui em
diante também para as criações futuras"*, a correção não foi tela a tela: **uma
regra só** liga `flex-wrap` em todos os agrupamentos de ação do painel
(`.navegacao`, `.rh-lote`, `.rh-topo`, `.slot-linha`, `.ficha-item`,
`.rh-abas`…). Tela nova que use qualquer um deles **já nasce certa**, sem
precisar lembrar da regra.

Vem junto o `min-width: 0` nos textos ao lado de botões — a pegadinha clássica
do flexbox: um item usa o tamanho do CONTEÚDO como piso e empurra os vizinhos
para fora **mesmo com `flex-wrap` ligado**.

### Unidades relativas

Observação do Bruno: *"vejo que você está considerando as medidas em pixel.
Talvez não seja interessante em REM ou percentual?"*. As regras que escrevi já
usavam `ch` e `rem` (os píxeis estavam só nos comentários de medição), mas
converti o que era legado e importa ao layout: largura da sidebar
(`236px` → `14.75rem`) e o rótulo do modo card (`96px` → `6rem`). Passam a
acompanhar o zoom e a fonte do sistema.

### A régua ficou mais completa

O teste de regressão ganhou a verificação de **altura de linha** e da presença
do corte. Validado por mutação: remover o `.dash-corta` faz o teste apontar
"Colaboradores: linha de 188px" e as três telas com células sem corte.

Um ajuste no próprio teste: ele fazia login cinco vezes e batia no **rate limit
do painel** (proteção legítima). Agora entra uma vez e reaproveita o token.

Validação: 23 testes E2E passam, telas conferidas renderizadas.

## [2.59.0] — 2026-08-02 — Nenhuma tabela obriga a rolar para o lado

> *"tive que segurar a tecla ctrl e rolar o scroll do mouse, mas isso não é
> intuitivo. Quero que não seja necessário rolar nada, em tabela nenhuma de
> todas as páginas [...] pois o botão estava ali, como no exemplo, mas eu não
> vi."*

O botão em questão era o **"Atender presencial" que eu tinha acabado de criar**
na v2.56. Ele foi o quarto da coluna de ações e empurrou a tabela para fora da
tela — um defeito que eu introduzi e não percebi porque, no código, cada botão
parece inofensivo na linha em que é escrito. Ninguém soma as larguras.

### O que a medição mostrou

Medido no navegador, não estimado:

| | antes | depois |
|---|---|---|
| coluna de ações | **560px (53% da tabela)** | 234px |
| folga em 1366px | **2 pixels** | cabe |
| estouro em 1024px | **310px** | 0 |
| Talentos / Desenvolvimento | 381px / 474px | 0 / 0 |

Em 1366px sobravam **dois pixels**. Qualquer janela menor — notebook pequeno,
janela dividida ao meio — cortava a ação em silêncio, porque o `border-radius`
da tabela faz o corte parecer o fim dela e a barra de rolagem só aparece
durante o gesto.

### Cinco causas, todas corrigidas

1. **`white-space: nowrap` em TODA célula** — nada podia quebrar, então um
   e-mail longo ou um nome comprido esticava a tabela inteira. Invertido:
   quebrar virou o padrão (seguro: a linha fica mais alta e nada some) e
   `nowrap` virou exceção declarada (`nowrap: true` na coluna), para data,
   contagem, chip e botão. Usa `break-word`, não `anywhere` — este último
   partia "Recepcionista" em "Recepcionist/a", pior que a rolagem.
2. **Coluna de ações sem largura e em fila única** — virou **grade de 2
   colunas** com largura fixa em `ch`. Quatro botões passam a ocupar a largura
   de dois, e a coluna não cresce mais a cada botão novo.
3. **Zero indicador de rolagem** — agora há sombra nas bordas, que aparece
   sozinha quando há conteúdo além e some ao chegar ao fim. Feita só com
   `background-attachment: local/scroll`, sem listener nem estado: vale para as
   ~46 tabelas do painel de uma vez.
4. **Células que enumeravam listas inteiras** — o chip "falta X, Y, Z" de
   Colaboradores chegava a 241px (a coluna mais larga da tela) e chip não
   quebra. Virou contagem, com a lista no `title`. Mesma coisa com datas que
   mostravam hora e repetiam a mesma string no `title`.
5. **`min-width: 10rem` nas colunas `quebra`** — era um piso, e com 3-4 delas
   somava 480-640px que ninguém pediu. Reduzido para 6rem.

### E onde o CSS não bastava

Abaixo de **1100px**, as tabelas passam a virar **cards** — modo que já existia
e era usado só no celular. Em 1024px, Talentos e Desenvolvimento têm 8-9
colunas e não há CSS que faça isso caber sem esconder informação; o card
resolve por completo, com cada valor ao lado do seu rótulo.

Três colunas pouco usadas (Telefone e Cidade em Talentos, Cargo em
Desenvolvimento) passaram a nascer ocultas — continuam a um clique em
**⚙ Colunas**.

### A régua que faltava

`frontend/tests/e2e/tabelas-cabem-na-tela.spec.js`: mede 6 telas em 3 larguras
e reprova se alguma exigir rolagem lateral, ou se a coluna de ações passar de
35% da tabela. O defeito é invisível no código — este teste é o que impede o
próximo botão de repetir a história. Validado por mutação (restaurar o `nowrap`
faz dois testes falharem).

Validação: 22 testes E2E passam (os 18 anteriores + 4 novos), telas conferidas
renderizadas em 1024px e 1440px.

## [2.58.0] — 2026-08-02 — O atendimento presencial aparece na tela

Pergunta do Bruno depois da v2.56: *"onde e como eu marco que o atendimento foi
assistido? eu consigo marcar isso após um candidato iniciar seu cadastro?"* — e
ela expôs uma lacuna real: o botão existia, mas **nada na tela mostrava o
resultado**.

- **Indicador na lista de Admissões**: chip `🧑‍💼 em atendimento` na linha de
  quem tem sessão aberta agora, com quem abriu e quando (no `title`). O RH
  clicava e não tinha como saber, olhando a lista, que aquela pessoa já estava
  sendo atendida — nem por quem.
- **Registro na ficha da pessoa**, no topo: os atendimentos em curso e os
  encerrados. Antes isso existia só na auditoria geral, que ninguém abre no dia
  a dia. Cada assinatura também passa a expor quem a colheu.
- **A confirmação agora AVISA** que a marca vale do clique em diante. Respondendo
  à pergunta: sim, dá para marcar depois que a pessoa já começou — e o que ela
  já assinou continua registrado como feito por ela, **que é o correto**.
  Carimbar como presencial um documento assinado em casa seria a mentira que o
  manifesto existe para evitar. O que faltava era isso estar escrito.

Duas visões com propósitos diferentes, e o teste trava a distinção: a **lista**
mostra só o atendimento em curso (é operacional — "quem estou atendendo agora")
e some quando o link expira; a **ficha** guarda o histórico inteiro, porque
registro não some.

Validação: smoke 15/15, build limpo, design system OK, mutações detectadas.

## [2.57.0] — 2026-08-02 — O nome como se escreve, sem o espaço sobrando

> *"as vezes fica tudo minúsculo, as vezes digita tudo maiúsculo [...] e tem
> gente que quando termina de digitar o nome ainda dá um espaço depois da
> última palavra"*

A capitalização já vinha da v2.54, mas só valia para o NOME e só do momento da
gravação em diante. Duas lacunas fechadas.

### O espaço sobrando saía só do nome

Em endereço, cidade, bairro, cargo e documentos, o texto ia como digitado. Não
quebrava nada visivelmente — e é justamente por isso que passava:

- sujava o export do Tirvu/Dexion, lido por outro sistema;
- **duplicava a opção no filtro de coluna**: `"Taguatinga"` e `"Taguatinga "`
  viravam duas entradas na lista suspensa, e nenhuma achava as pessoas da
  outra;
- quebrava casamento por TEXTO (cargo, lotação, jornada), que é como boa parte
  do sistema liga as coisas;
- e, no e-mail, produzia um erro que **mentia**: o `EmailStr` recusava
  `"jose@x.com "` e a pessoa via *"e-mail inválido"* olhando para um endereço
  perfeitamente correto.

Agora todos os schemas da ficha herdam de `_AparaEspacos`, que apara todo campo
de texto com `mode="before"` — antes da validação de tipo, que é o que conserta
o caso do e-mail. Campo deixado só com espaços vira `None`, não `""`.

### A base existente foi padronizada

Decisão do Bruno: *"corrigir tudo automaticamente agora"*. Isso contraria a
regra do `CLAUDE.md` ("não migre nome em lote"), e a ressalva foi registrada
antes de executar — mas a decisão é dele, e a migração foi feita de um jeito
que a torna **reversível**: o nome original de cada registro alterado fica
guardado, e o `downgrade()` restaura o valor **exato** (verificado byte a byte,
espaços inclusive).

Alcança candidato, talento, nome de mãe/pai/social, dependentes, contatos de
emergência e crianças do creche. Quem já estava no padrão **não é tocado** e nem
entra no backup.

**O acento não é inventado**: `MARIA DE FATIMA` vira `Maria de Fatima`, nunca
`Maria de Fátima` (decisão do Bruno na mesma conversa). O acento se perdeu na
origem, e adivinhar escreveria errado o nome de alguém — pior que deixá-lo sem
acento.

Um defeito encontrado ao testar a migração, e que vale registrar: a primeira
versão assumia que toda tabela tem coluna `id`, mas `dados_pessoais` é 1:1 com o
candidato e usa `candidato_id`. A migração estourou no meio — e o rollback
transacional por revisão devolveu tudo ao estado anterior, sem alteração
parcial. É o que se espera do `transaction_per_migration`, confirmado na
prática.

Validação: **smoke 15/15**, build limpo, upgrade e downgrade testados contra
banco com dados sujos reais, e as mutações do teste novo detectadas.

## [2.56.0] — 2026-08-02 — Atendimento presencial, e o upload com guarda-corpo

### Admissão presencial assistida

> *"quero pensar em uma estratégia para os casos em que a pessoa tiver baixo
> grau de instrução, ou dificuldades [...] o RH fazer tudo, desde a inserção de
> dados, coleta de documentos e tudo mais e ver alguma forma que a pessoa possa
> assinar o documento. Pois hoje o RH gera o link mas fica inserindo tudo na mão
> como se fosse uma correção e não como se o candidato estivesse ali."*

**O recurso não é "deixar o RH preencher" — isso já dava para fazer** abrindo o
link mágico no computador do escritório. O que faltava era o **registro**: sem
ele, uma admissão preenchida pelo RH e uma feita pela pessoa em casa produzem
documentos idênticos, e o manifesto afirma *"código enviado ao titular e
validado nesta plataforma"* como se ela tivesse operado tudo sozinha.

Botão **"🧑‍💼 Atender presencial"** na lista de Admissões: abre o mesmo wizard
numa aba, marcado. O que muda:

- **O manifesto declara como a assinatura foi colhida** — campo novo *"Forma de
  coleta"*, entre Método e Modalidade: *"Assinatura colhida PRESENCIALMENTE, em
  atendimento assistido: o preenchimento foi operado por [RH], a pedido e na
  presença do titular, que validou o código recebido em seu próprio e-mail."* O
  bloco no corpo do documento também registra. É o princípio já cravado na
  `AutorizacaoEquipe`, que diz *"emitido sob autorização permanente de X"* em vez
  de *"X assinou"*: o documento descreve o ato real, nunca a versão mais
  conveniente dele.
- **A prova de identidade não é enfraquecida**: o código continua indo ao e-mail
  **da própria pessoa** (decisão do Bruno). Quem não tem e-mail é barrado na
  abertura da sessão, com o código `sem_email` — e esse é o melhor momento
  possível para resolver, com ela sentada na frente do RH.
- **O ator da assinatura continua sendo o CANDIDATO.** Quem quis assinar foi
  ele; o que se acrescenta é *como*, não *quem*. Trocar o ator para "rh"
  registraria que o RH assinou — exatamente a distorção que isto evita.
- **A marca vive no LINK** (`acesso_magico.assistido_por`), não numa tabela de
  sessão à parte: o wizard já resolve o token a cada requisição, então não há
  estado paralelo para sincronizar — nem sessão esquecida aberta. Validade de
  **8 horas**, não as 72 do convite: é para usar agora, com a pessoa na sala.
- Faixa permanente no wizard dizendo com quem se está atendendo e que o código
  chegará no e-mail dela. O formulário é idêntico ao que a pessoa vê em casa —
  sem o aviso, quem opera não sabe se está na aba certa.

O documento de assinatura remota **não muda em nada** — há teste de regressão
para isso, porque o manifesto é peça de prova e seu texto não deve variar por
acidente.

### Uploads do creche: as duas rotas sem nenhuma proteção

Achado durante a v2.54 e confirmado num levantamento de todas as rotas de
upload: **as duas do creche eram as únicas do backend inteiro sem
`await arquivo.close()`** — e são rotas **públicas**.

O Starlette faz *spool* em disco de qualquer upload acima de ~1 MB. Sem fechar,
o arquivo temporário fica no container, e o que sobrava ali era **certidão de
nascimento e guarda judicial de criança**. Também não havia teto de tamanho nem
validação de formato: `ext or "bin"` aceitava `.exe`, `.svg` e arquivo sem nome.

`services/upload_seguro.py` passa a ser a porta única — com o `close()` no
`finally` **dentro da função**, que é o que impede o próximo call-site de
esquecer, como este esqueceu.

**O teto é configurável no painel** (Configurações → Sistema), a pedido do
Bruno: limite chumbado no código exige deploy para ajustar, e quem descobre que
10 MB não bastam para a foto de um celular novo é o RH, com a pessoa do outro
lado da linha. Faixa de 1 a 200 MB, padrão 50.

Validação: **smoke 15/15**, build limpo, design system OK, manifesto conferido
renderizado em imagem, e as mutações dos testes novos detectadas.

## [2.55.0] — 2026-08-02 — Um filho de cada vez

> *"se a pessoa tem mais de um filho e um eu defiro e outro eu indefiro, não tem
> opção individual por filho, somente indeferir tudo ou aprovar tudo, não tá
> legal isso. Tem que ser individual isso de modo que eu marco os que defiro e os
> que indefiro, para gerar apenas um requerimento."*

Estava desenhado na v2.54 e o Bruno pediu para implementar ao ver o caso real na
tela (dois filhos, os dois elegíveis — mas a pergunta era o que fazer quando só
um fosse).

### O workaround anterior apagava a prova

Não havia decisão por criança em lugar nenhum: `CriancaCreche` não tinha campo
de decisão, e `ativar`/`indeferir` agiam sobre o benefício inteiro. Para negar
um filho, o único caminho era **devolver** o levantamento e pedir que o
colaborador **removesse** a criança — o que apagava o registro de que ela havia
sido analisada e negada. Justamente o registro que prova que o RH avaliou o
pedido todo.

Agora cada criança tem `decisao`, `motivo_decisao`, `decidido_por` (snapshot) e
`decidido_em`, com rota própria. Migração **aditiva**, sem backfill: benefício
aprovado antes desta versão fica com `decisao = NULL` e é tratado como
"deferido pelo modelo anterior" — marcar tudo como deferido gravaria uma
decisão que ninguém tomou, com data e autor inventados, num campo que é prova
de ato administrativo.

### O valor passou a ser POR CRIANÇA — e o cuidado que isso exigiu

Decisão do Bruno: o reembolso é por criança deferida. Indeferir uma reduz o
total sozinho, sem o RH recalcular à mão — que é onde o erro de folha
aconteceria. A tela mostra o unitário e o total (`2 crianças = R$ 1.053,28`).

**A armadilha estava no histórico**: para quem foi aprovado antes desta versão,
o `valor_reembolso` gravado JÁ era o total do benefício. Multiplicá-lo agora
dobraria o reembolso de quem tem dois filhos — em silêncio, no contracheque, sem
nada acusar. Por isso o total só multiplica quando há decisão registrada; sem
nenhuma, o valor gravado vale como está. É a garantia que mais mutações do teste
tentaram quebrar.

Valor ilegível (`a combinar`) volta cru, nunca `R$ 0,00`: zero entraria calado na
folha.

### Duas guardas que evitam decisão pela metade

- **Não se aprova com criança pendente** (409), e o erro **diz o nome** de quem
  falta — sem isso o RH procuraria na tabela qual esqueceu. Para isso, o
  `api.js` passou a preservar `detail` estruturado em `e.dados`: antes ele
  virava a string genérica do `statusText` e a lista de nomes se perdia na porta
  de entrada (mesma lição do `e.campos`).
- **Todas negadas ⇒ indeferido automaticamente**, com os motivos agregados por
  criança, em vez de um benefício "ativo" que paga zero — que seria mentira no
  relatório e no requerimento.

Motivo é **obrigatório para indeferir** (é o que o colaborador lê) e dispensado
para deferir.

### Um requerimento só, com as duas seções

O corpo que a pessoa **assina** lista apenas as deferidas — declarar como
beneficiada uma criança que o RH negou seria pedir que ela subscrevesse algo que
não vale. As negadas aparecem em seção própria, com o motivo: somem do
benefício, não do registro da análise.

O colaborador vê o resultado por criança no link do creche, **com o motivo**
(regra da casa desde o portal `/meu`) — antes de assinar, inclusive, que é
quando ainda dá para questionar. Quem decidiu não vai: nomear o analista
transformaria a decisão em disputa pessoal.

### Achado na conferência visual do PDF

O requerimento imprimia a data de nascimento **crua** — então quem preencheu
pelo wizard (que grava ISO) tinha `2022-10-19` num documento oficial em
português, assinado. Passou a usar `data_br`, que já existia e lê os dois
formatos. Só apareceu porque o PDF foi renderizado e olhado; a extração de texto
tinha passado.

Validação: **smoke 15/15**, build limpo, design system OK, e as cinco mutações
do teste novo detectadas — inclusive a que dobraria a folha.

## [2.54.0] — 2026-08-02 — A versão que mentia, o clique que não fazia nada, e o Dexion

Nove feedbacks de uso numa leva só, mais o exportador do Dexion. O Bruno cortou
o escopo em quatro: conserto, dash do creche, Dexion e padronização de nomes —
com decisão por filho, admissão assistida e câmera/timbrado **desenhados** para
depois (`docs/planejamento/11-desenhos-21a-leva.md`).

### A versão do sistema parou de mentir

O Bruno abriu `/api/health` depois de conferir um deploy e leu
`v2.27-idade-creche`. O código estava na 2.53.

Não era bug novo — era **reincidência**. O `VERSAO_DEPLOY` era uma string
chumbada à mão em `api/health.py`, e já tinha congelado antes, na `v1.50`, por
vinte versões. Na v2.28 alguém percebeu, consertou o campo **vizinho**
(`migracoes.no_codigo`, que passou a ser lido do diretório de migrations) e
escreveu no docstring da função ao lado que a constante chumbada era o mau
exemplo — deixando a constante. Ela congelou de novo, por mais 26 versões.

A lição das duas vezes é a mesma: **documentar que algo precisa ser atualizado à
mão não funciona**. Agora a versão vem de `app/versao.py` e o
`tests/test_versao.py` compara com o topo do `CHANGELOG.md`, reprovando no CI
quando divergem. Um segundo teste impede que a string literal volte para o
`health.py`. Sem isso, congelaria uma terceira vez.

E ela apareceu onde o Bruno pediu — *"algo que de fato seja funcional, mas não
necessariamente exposto a todo momento"*: **Configurações → Sistema**, com o
número, o nome da versão e se o banco acompanhou o código. Não no rodapé da
sidebar, que é `space-between` com `nowrap` e já avisa em comentário próprio que
um terceiro item comprime o nome de quem está logado.

### O currículo do Banco de Talentos: um clique literalmente morto

O relato foi *"eu cliquei, disse que renderizou, mas eu tive que clicar em 'ver
ficha' para abrir o card"*. Investigando, era pior: com a ficha fechada — o
estado padrão de toda linha — **nada acontecia**. Sem erro, sem espera, sem aba
nova.

`verCurriculo` só preenchia o estado `doc`, e o visualizador que renderiza esse
estado mora **dentro** da `FichaTalento`, que só é montada quando
`aberto === t.id`. O arquivo baixava e ficava invisível na memória. Pior: ao
clicar em "Ver ficha" depois, o currículo aparecia retroativamente, como se o
sistema guardasse rancor do clique anterior.

Corrigido: `verCurriculo` abre a ficha junto. **A regra que fica** — quem abre um
documento tem que abrir o lugar onde ele é exibido, na mesma ação; estado de
conteúdo e de visibilidade não podem ser independentes quando um só existe
dentro do outro.

Eram **três** pontos clicáveis do mesmo currículo (o Bruno viu dois). Ficou um:
o atalho embaixo do nome. A coluna "Currículo" virou **Sim/Não** — serve para
filtrar e responder de bate-pronto quem anexou, como ele pediu.

### Creche: a data que fazia o sistema recomendar a decisão errada

O caso relatado foi um filho aparecendo como `12/10/1998 · 27a 9m · ❌ passou de
5a11m`, quando a certidão dizia 19/04/2022.

**O cálculo estava certo.** `partes_da_data` lê os dois formatos desde a v2.27, e
o painel lê a data da criança, corretamente. O que estava no campo era o
nascimento do **próprio colaborador** — e o `InputData` não tinha
`autoComplete="off"`, então nem foi preciso erro humano: bastou o navegador
oferecer a data digitada momentos antes.

O estrago não parava no ❌ errado. Com 27 anos, `elegivel_idade` é `False` e
`idade_desconhecida` é `False` — as duas condições que ligam `revisar_idade`. O
sistema marcava o benefício como **risco de glosa** e empurrava o RH a suspender
quem tinha direito. A defesa da v2.27 cobriu "data ilegível" e não previu "data
legível e absurda".

Quatro camadas, nenhuma cobrindo a outra:

1. **Quarto estado** `idade_implausivel` (≥ 18 anos), fora do alarme de glosa
   pela mesma razão que `idade_desconhecida`: não se sabe a idade real, e acusar
   risco faria suspender benefício legítimo.
2. **Trava na entrada** (422 `data_de_adulto` / `data_no_futuro`), nos DOIS
   caminhos de cadastro — o link público e o wizard da admissão.
3. **Mensagem que diz o que resolve**: o `catch` cego dizia "tente de novo", e
   tentar de novo com a mesma data falha de novo. Agora explica que a data
   parece ser a do próprio colaborador.
4. **`autoComplete="off"`** no `InputData` — data de nascimento nunca se repete
   entre pessoas, sugerir a anterior só pode errar.

É **aviso, nunca bloqueio** no painel: filho com deficiência não tem limite de
idade em várias normas, e uma trava dura indeferiria calado um caso legítimo.

### Creche: o painel sem padding era um Fragment

O `DetalheBeneficio` devolvia `<>…</>`. O `.dash-detalhe > td` tem `padding: 0`
**de propósito** — o respiro é responsabilidade de quem preenche a célula. Sem
wrapper, tudo colava na borda.

E havia um segundo defeito invisível: a regra `.dash-detalhe > td > *` aplica
`position: sticky` e `width: 100cqw` a cada **filho direto**. Com Fragment eram
dez filhos virando dez elementos sticky independentes, que se desmontam quando a
tabela rola na horizontal. Um `<div className="ficha-talento">` conserta os dois.

### Creche: quem faz jus, e até quando (aba nova)

> *"o DP irá precisar saber mensalmente quem tem direito e não tem direito"*

O que a aba muda é o **tempo do verbo**: o painel de levantamentos constata
"está fora da idade" depois do fato; a aba responde "sai em 12/09/2026", que dá
ao DP tempo de se preparar. Tudo derivado da data de nascimento — zero coleta
nova.

Uma linha por **criança**, não por colaborador: é a criança que faz aniversário,
e o mesmo colaborador pode ter uma dentro e outra fora da idade — agrupar por
benefício esconderia justamente o caso que exige decisão.

O `_fim_do_direito` é travado por teste contra a regra de elegibilidade: **no dia
do fim ainda há direito; no dia seguinte, não**. Se as duas funções divergirem em
um dia, o DP tira da folha alguém que ainda tem direito e ninguém desconfia. O
29/02 cai em 28/02 no ano não bissexto — nunca 01/03, que daria um dia a mais.

### Creche: prazo e valor editáveis depois da aprovação

> *"para os reembolso creche que já obtiveram a aprovação e estão aguardando a
> repactuação, quero que seja possível editar ali no painel, tanto a data limite
> [...] quanto também o valor do reembolso"*

Faltava mesmo: o `valor_reembolso` só era gravado dentro de `ativar_beneficio`.
Repactuar um contrato deixava os benefícios ativos com o valor antigo congelado,
e o único jeito de mexer era **re-ativar** — o que regenera o dossiê, recria o
roteiro de assinatura e dispara e-mail. Muito estrago para trocar um número.

Agora é edição inline no painel (`PUT .../condicoes`), com mensagem local — o
bloco fica no meio da tela, e um `setMsg` do pai renderizaria a confirmação fora
do campo de visão. O valor **não** acompanha o posto sozinho: o campo existe
justamente para poder divergir.

### Exportador do Dexion (97 colunas)

> *"siga fielmente ao modelo da planilha, pois o dexion é mto enjoado"*

Módulo próprio (`services/export_dexion.py`), **sem reusar** o gerador do Tirvu —
os dois só se parecem de longe:

| | Tirvu | Dexion |
|---|---|---|
| colunas | 28 | **97** (A→CS) |
| aba | `Plan1` | `Sheet1` |
| cabeçalho | 1 linha | **4 linhas**; dados na 5ª |
| autoFilter | **recusa** | **tem**, em `A4:BV` |
| datas | texto `dd/mm/aaaa` | **serial do Excel**… exceto `INÍCIO (ESCALA)`, que é texto |

Copiar o gerador vizinho produziria um arquivo que **parece** certo — ou, pior,
que é aceito com as datas erradas em mil e duzentos dias, porque serial e texto
são as duas coisas que um parser lê sem reclamar.

A chave da linha é a **letra da coluna**, não o rótulo: o layout repete nomes
("CATEGORIA" três vezes, "UF" três, "TIPO DE JORNADA" duas), e com rótulo uma
sobrescreveria a outra em silêncio.

**A regra dos valores assumidos** (que vale para o próximo exportador):
**chumba-se o que é da EMPRESA; nunca o que é da PESSOA.** País, regime da
empregadora e tipo de declaração vão fixos, pelo mesmo raciocínio do
`EMPRESA_TIRVU_ID = "1"`. Categoria do trabalhador, CBO, sindicato e conta
bancária viram **pendência anunciada** — um código eSocial errado não dá erro na
importação: entra limpo e sai errado na declaração ao governo, meses depois. É a
assinatura de defeito do "Registra Ponto" da v1.82.

**O que o sistema ainda não coleta**: agência, conta e tipo de conta (há só
`banco` em texto livre e a chave PIX), município IBGE e CBO por pessoa. Decisão
do Bruno: exportar vazio por ora e tratar como pendência, em vez de inventar
dado que decide para onde vai o salário.

O teste compara o cabeçalho gerado com o **arquivo oficial, célula a célula**
(194 células) — não com uma cópia escrita à mão, que passaria a divergir do
modelo na primeira revisão dele sem que o teste percebesse. Duas mutações
escaparam da primeira versão do teste e foram fechadas: renomear a aba para
`Plan1` (comparava a constante consigo mesma — tautologia) e trocar a coluna BZ
para serial (o teste montava o valor sozinho em vez de usar a linha real).

### Nomes: o sistema PRODUZIA o "Maria De Fátima"

> *"o candidato hora digita tudo em caixa baixa, outros tudo em caixa alta [...]
> menos como no exemplo Maria De Fátima, onde o 'De' deveria ser 'de'"*

O achado que muda a leitura do feedback: **o defeito não era só tolerado, era
gerado**. O `ocr_rg.py` sugeria o nome da mãe com `.title()` do Python — e
`"maria de fátima".title()` devolve exatamente `"Maria De Fátima"`. O candidato
aceitava a sugestão com um toque. Ou seja, aquele nome pode ter sido escrito
pelo próprio portal.

`services/nomes.py` é o ponto único, aplicado na **entrada** (wizard, convite do
RH, Banco de Talentos, edição pelo painel e o OCR). Trata preposições, `d'Ávila`,
`Mc`, hífen e sufixo romano, e é idempotente — o wizard salva a cada 900ms.

**Não acentua**: `FATIMA` continua `Fatima`. É por isso que a base existente
**não** é migrada em lote — o que está em caixa alta já perdeu o acento na
origem, e uma migração cega gravaria "Fatima" como se fosse o nome correto de
alguém. Mesma regra da data do creche.

O `test_nomes.py` é estrutural: reprova qualquer `.title()` que volte a um ponto
de escrita de nome. É a garantia que dura — as outras provam que a função de hoje
está certa; esta impede que alguém reintroduza o defeito daqui a seis meses num
arquivo que ninguém está olhando.

### Testes no CI

Os testes estruturais novos entraram no `ci.yml`: `test_versao` e `test_nomes` no
passo de stdlib pura, e `test_export_dexion` num passo próprio (precisa de
`openpyxl` + `sqlalchemy`, mas não de FastAPI nem de banco — ~15s por uma
garantia que compara o arquivo com o modelo oficial).

Validação: **smoke 15/15**, `npm run build` limpo, design system OK, e todos os
testes novos verificados **por mutação**.

### Desenhados, não implementados

`docs/planejamento/11-desenhos-21a-leva.md` — decisão por filho no creche,
admissão presencial assistida e câmera/timbrado em todos os uploads. Cada um com
as decisões que só o Bruno toma.

**Achado fora do pedido, registrado lá**: os uploads de creche e portal não
fecham o arquivo (`await arquivo.close()`), não têm teto de tamanho e aceitam
qualquer extensão — em rota **pública**. O Starlette faz spool em disco acima de
~1MB, então sobra certidão de nascimento de criança em temp file no container.
Isso é conserto de segurança, não experiência, e não deveria esperar a câmera.

## [2.53.0] — 2026-08-02 — Ver como se responde, antes de começar

Ideia do Bruno, e melhor que os casos que eu tinha avaliado para animação:

> *"talvez o CSS/SVG seria interessante apenas para os testes DISC e
> situacionais e também os testes de processo seletivo, antes da pessoa
> iniciar, de modo que ela entre nos testes sem dúvidas."*

Quem está prestes a fazer um teste que pode decidir a contratação dele não
deveria gastar atenção descobrindo a mecânica. E a instrução do DISC é a mais
difícil de entender lendo — *"marque na coluna da esquerda a que MAIS tem a ver
e, na da direita, a que MENOS, uma em cada coluna, nunca a mesma palavra"*.
Isso se entende **vendo**.

### Adicionado

- **`DemoTeste.jsx`** — uma questão de mentira que se responde sozinha, na tela
  de instruções do **DISC**, do **situacional**, da **testagem avulsa** (`/t/`)
  e das **provas de seleção** (`/p/`). No DISC as marcações aparecem em
  sequência, uma em cada coluna, mostrando a regra em vez de descrevê-la.
- **A prova agora diz o tamanho da tarefa antes de aceitar**: quantas questões
  e quantos minutos. Antes a pessoa via só o campo do nome e descobria o resto
  com o cronômetro correndo. A rota pública `GET /p/{token}` passou a devolver
  `tempo_segundos` e `qtd_questoes` — o **gabarito continua fora** (verificado).

### Por que CSS/SVG e não GIF

Decisão do Bruno na abertura da reforma, e aqui ela se paga: um GIF pesaria
centenas de KB no celular de quem já sofre com conexão ruim, congelaria a tela
do dia em que foi gravado, e não seria legível por leitor de tela. A demo usa
as **mesmas classes da tela real** (`.teste-linha`, `.teste-adjetivo`,
`.teste-tag`) — se o teste mudar de aparência, ela muda junto.

Acessibilidade: a animação é decorativa (`aria-hidden`) e o texto ao lado diz a
mesma coisa em palavras. Com `prefers-reduced-motion`, some o movimento e fica
o estado final preenchido — que é o que a animação queria comunicar.

### Verificação

Build ok · `test_design_system` OK · `deploy-tela-branca` 8/8 · demo conferida
**renderizada** nos dois temas, no DISC, no situacional e na prova · rota
pública conferida: devolve tempo e quantidade, **não devolve gabarito**.

O guarda-corpo da v2.48 pegou uma classe fantasma minha (`demo-linha-unica`)
antes do commit — era exatamente para isso que ele existia.

## [2.52.0] — 2026-08-02 — Filtro de coluna também escolhe da lista

Continuação do pedido da v2.50, agora nos filtros das tabelas. O Bruno mandou
prints de cinco telas:

> *"no segundo print, quero aquele filtro maroto para posto, pois está a escrita
> livre. Na de uniformes, quero o filtro bom para cargo e posto. No de creche
> também. No de banco de talentos, os que sinalizei."*

A v2.50 resolveu os `<select>` de **preenchimento**; ficaram de fora os filtros
de **coluna** do `DashPlanilha`, que eram campo de texto: para filtrar por posto
o RH tinha que saber escrever o nome exato.

### Adicionado

- **`filtro: 'lista'`** na config de coluna: monta as opções a partir dos
  **próprios dados** da tela e usa o `SelectBusca`. Não exige escrever lista
  nenhuma — e acompanha os dados quando eles mudam.
- **Coluna que devolve ARRAY entra item a item.** Tags e cargos são listas por
  pessoa; sem isso a opção seria a string concatenada ("Auxiliar, Copeiro"),
  que não filtra nada. Quem tem 3 tags aparece nas 3.

### Mudado — 24 filtros

Os 7 que o Bruno apontou (posto em Jornadas e Creche; cargo e posto em
Uniformes; cargos, tags e cidade em Talentos) **mais 17 do mesmo tipo em telas
que ele não printou** — Avaliações, Desempenho, Desenvolvimento, Provas,
Telemetria. Ele pediu coerência; corrigir só o que estava no print deixaria o
resto incoerente na semana seguinte.

**O que continua sendo texto, de propósito:** nome de pessoa, descrição livre,
telefone, matrícula e ID do Tirvu. Nome se busca por **trecho** — digitar
"mari" acha Maria, Mariana e Marisa; numa lista de 1.171 nomes você teria que
saber qual escolher. O critério é a natureza do campo, não o tipo do filtro.

### Nota

O primeiro print (Colaboradores com dois blocos de filtro) era anterior à
v2.51, que já unificou aquela tela.

### Verificação

Build ok · `test_design_system` OK · `deploy-tela-branca` 8/8 · **8 telas
varridas com captura de erro de JS: zero erros**, nenhuma estoura · filtro de
array testado ao vivo (CARGOS derivou 4 opções item a item, não a string
concatenada).

## [2.51.0] — 2026-08-02 — Um bloco de filtros, e o tempo que a pessoa leva de verdade

Os dois pedidos que restavam do print de Admissões.

### Mudado — um bloco de filtros só

> *"parece que os dois que assinalei com as setas vermelhas são a mesma coisa,
> não faz sentido ter dois cards, isso pode gerar confusão. Não seria melhor ter
> um apenas com todas as funções necessárias?"*

**Admissões** e **Colaboradores** tinham **duas caixas de filtro empilhadas** —
e o mesmo campo aparecia nas duas (status em Admissões; nome e posto em
Colaboradores), uma consultando o servidor e a outra a memória. Filtrar por uma
enquanto a outra dizia coisa diferente dava resultado que parecia errado.

A regra e a solução já existiam desde a v2.30, quando o Bruno apontou o mesmo
no Reembolso-Creche (*"tudo concentrado e coeso de filtros"*) — só não tinham
sido aplicadas a estas duas telas. Agora os filtros server-side entram na mesma
grade do `DashPlanilha`, via `filtrosExtras`, e as colunas duplicadas perderam
o `filtro:` (**um assunto, um controle**). Elas seguem ordenáveis, e os cards
clicáveis continuam funcionando — a filtragem em memória roda sobre todas as
colunas, não só as que declaram filtro.

Para isso o `DashPlanilha` ganhou duas capacidades: **`filtrosExtras` sem
`opcoes` vira campo de texto** (com debounce, para não disparar uma consulta
por tecla) e **`acoesFiltro`** aceita botões próprios na barra — foi onde o
"Exportar planilha" e o "limpar filtros" foram parar.

### Mudado — tempo LÍQUIDO de preenchimento

> *"o card de tempo deveria refletir o real, de quanto tempo uma pessoa leva em
> média para preencher, mas o tempo LÍQUIDO que ela esteve preenchendo, não o
> tempo que ela iniciou e terminou. Quero o líquido."*

O card mostrava **2.590min** — o campo se chamava, literalmente,
`tempo_medio_minutos_convite_ao_dossie`: a diferença entre o convite e o
dossiê, incluindo a pessoa dormindo, trabalhando e esperando o documento chegar
pelo correio. Respondia "quanto o processo demora", não "quanto tempo leva para
preencher".

Agora o número vem da **telemetria**, que já registrava `sessao` (a visita) e
`criado_em` de cada evento desde a v2.24 — não foi preciso coletar nada novo.
`tempo_liquido_por_candidato` soma os intervalos entre eventos consecutivos da
mesma sessão e **descarta os buracos maiores que 30 minutos**, que são a pessoa
tendo ido embora. Medido com dados sintéticos: **20 min de preenchimento real
contra 8h30 de calendário**.

Três decisões travadas em `test_tempo_liquido.py` (9 verificações), porque
todas mudam o número que o RH vai olhar: buraco > 30 min não conta · sessões
diferentes somam (voltar no dia seguinte é a mesma pessoa) · a cauda de sessão
tem **teto**, senão quem entra e sai dez vezes ganha 5 min de crédito por nada
(~17% de inflação, medido). **Quem não tem telemetria fica fora da média**, em
vez de entrar como zero e puxá-la para baixo.

A métrica antiga continua no retorno da API — responde outra pergunta legítima
— e aparece no tooltip do card. O que saiu foi o número enganoso do rosto.

### Adicionado

- **`fmtDuracao`** em `fmt.js`: a unidade acompanha o número (`45s` · `25min` ·
  `1h30` · `1d19h`). "2.590min" não se lê como "quase dois dias". Use em
  qualquer card de duração.
- Cards do `DashPlanilha` aceitam **`dica`**, para explicar como a métrica é
  calculada — antes o `title` só servia ao filtro.
- Classe `.campo-check` (checkbox + rótulo na mesma linha), que várias telas
  faziam com `style` inline.

### Verificação

Build ok · `test_tempo_liquido` **9/9** · `test_design_system` OK ·
`deploy-tela-branca` 8/8 · as duas telas conferidas **renderizadas**: **1 bloco
de filtro** onde havia 2, zero cards soltos, nada estoura · busca testada ao
vivo (filtrou 4→3 linhas com **uma** consulta ao servidor, provando o debounce).

## [2.50.0] — 2026-08-02 — Toda lista suspensa filtra ao digitar

Pedido do Bruno, com um exemplo bom e dois ruins na mesma tela:

> *"para todos os campos onde tem lista suspensa em todas as páginas, seja para
> inserir informações, seja para filtrar... como exemplo positivo destaco o
> [cargo], que tanto pode rolar para baixo quanto digitar que já vai aparecendo,
> mas o mesmo não acontece com a jornada e o posto de serviço, pois o RH tem que
> ficar rolando até encontrar... principalmente os que têm muitas opções, para
> agilizar a vida do RH."*

Ele tem **111 cargos, 269 jornadas** e dezenas de postos. O componente certo
(`SelectBusca`) já existia desde a v1.41 — mas só tinha sido aplicado em ~20
lugares, e os outros **64 continuavam `<select>` nativo**.

### Mudado

- **Os 64 `<select>` nativos viraram `SelectBusca`.** Não sobrou nenhum.
- **O `SelectBusca` passou a aceitar `<option>` como filhos**, igual a um
  `<select>`. Foi o que tornou a conversão viável: em vez de reescrever 64
  blocos à mão (64 chances de errar), a maior parte virou troca de tag. A forma
  antiga (`opcoes={[...]}`) continua valendo — os ~20 usos anteriores não foram
  tocados.
- **O campo de busca só aparece a partir de 7 opções.** O pedido foi "todos,
  independente se grande ou não", e o padrão de USO é mesmo único — mas num
  select de 2 itens (*Efetivo/Intermitente*, *Sim/Não*) um campo de texto
  adicionaria um passo em vez de remover. O limiar é uma constante no
  componente (`MIN_BUSCA`), fácil de ajustar.
- **12 selects do wizard do candidato saíram numa edição só**: o `Wizard.jsx`
  já tinha um componente `Select` interno centralizando todos.
- `aria-haspopup`, `aria-expanded`, `role="listbox"` e `role="option"` — o
  componente vai de ~20 para 84 usos, então a acessibilidade dele passou a
  valer muito mais.

### Corrigido

- **`SelectBusca` dentro de `<label className="campo">` encolhia** para os
  180px do mínimo, em vez de ocupar a linha como o `<select>` que substituiu.
  Regra nova no `styles.css` para `.campo`, `.linha2` e `.linha3`.

### Guarda-corpo

`test_design_system.py` agora **reprova `<select>` nativo no JSX** — pedido
explícito do Bruno: *"daqui em diante, toda vez que tiver um select, já imponha
esse padrão"*. Comentário que menciona `<select>` não conta (falso positivo em
guarda-corpo ensina a ignorá-lo).

### Verificação

Build ok · `test_design_system` OK · `deploy-tela-branca` 8/8 · **17 telas
varridas com captura de erro de JS: 32 `SelectBusca` renderizados, zero erros**
· interação testada de ponta a ponta com **13 postos cadastrados**: campo de
busca aparece, digitar "PT1" filtra de 15 para 5 itens, escolher grava, página
não estoura.

## [2.49.0] — 2026-08-02 — O sistema explica a si mesmo

Quarta e última leva da reforma. As três anteriores corrigiram e protegeram;
esta **acrescenta** — é a parte do pedido original do Bruno sobre tornar o
sistema intuitivo.

Vale registrar a decisão de método, porque ela contraria o pedido literal: o
Bruno pediu **GIFs** de instrução. Apresentados os custos — peso no celular do
candidato (que já sofreu com tela branca e OCR lento), desatualização
silenciosa a cada mudança de tela, e o fato de não serem acessíveis nem
traduzíveis —, ele escolheu **onboarding embutido + animação CSS/SVG onde o
gesto for insubstituível**. GIF é remédio para interface que não se explica; a
aposta aqui é a interface se explicar.

### Adicionado

- **Tour do painel do RH** (`rh/tour.js`). O wizard do candidato tinha tour
  desde a v1.x; o painel — **17 telas em 6 grupos** — nunca teve, e quem entra
  pela primeira vez vê um menu grande sem indicação de por onde começar. Cinco
  passos que dizem o que a pessoa **ganha** em cada caminho, não o que a tela
  é. Dispara uma vez (chave `tour_rh_visto`, separada da do candidato — o RH
  também abre o link do candidato para conferir) e fica no rodapé do menu para
  rever.
- **12 termos novos no glossário** (`Ajuda.jsx`), cobrindo a lacuna que o
  próprio `08-sistema-de-design.md` registrava como pendente desde as Ondas
  B/C: `homologar`, `manifestacao`, `feedback_dado`, `avaliacao_vertical`,
  `avaliacao_horizontal`, `calibracao`, `fato_observado`, `pdi`, `reciclagem`,
  `documento_critico`. As definições explicam a **consequência**, não a
  palavra: manifestação diz que o prazo é de 7 dias; horizontal diz que com
  menos de 2 respondentes o resultado é suprimido.

### Corrigido

- **O tour saía BRANCO no tema escuro** — em ambos os tours, inclusive o do
  candidato, que está em produção há meses. O `driver.css` traz cores fixas e
  não expõe variável de cor nenhuma (só duração de animação e fonte), então as
  classes foram sobrescritas com os tokens da casa: fundo, texto, a seta que
  aponta o elemento (desenhada com `border-*-color`) e os botões, com o
  "Próximo" no verde da marca. Medido: **12,29:1 no escuro, 13,32:1 no claro**.
- **"2 of 5" em inglês** no meio de uma interface inteiramente em pt-BR —
  também nos dois tours. O `driver.js` aceita `progressText`, e ninguém tinha
  passado.
- **O botão de rever o tour espremia o nome de quem está logado.** A primeira
  versão usava rótulo "? Como usar"; medindo o rodapé (`space-between` com
  `nowrap`), o nome caía de 124px para o avatar sozinho. Virou ícone.
- Mais **13 hex crus** convertidos para token nos chips de estado — só os que
  eram **idênticos** a um token existente. Os outros 11 são cores próprias
  (vermelhos, âmbares, azuis, um roxo) que não existem na paleta: trocá-las
  pelo "token mais parecido" mudaria a cor na tela sem ninguém ter pedido.

### Verificação

`test_design_system` OK · `npm run build` ok · tour conferido **renderizado**
nos dois temas, com os 5 passos exibidos e **nenhum pulado por elemento
ausente** (o modo de falha silenciosa do `driver.js`) · contraste do popover
medido no Chromium.

## [2.48.0] — 2026-08-02 — Guarda-corpo: a dívida de design não volta sozinha

Terceira leva da reforma. As duas anteriores corrigiram defeitos; esta impede
que voltem — porque eles **já voltaram** antes: a armadilha da classe fantasma
está no `CLAUDE.md` desde a v2.25 e mesmo assim havia sete delas na base.

### Adicionado

- **`backend/tests/test_design_system.py`** — teste ESTRUTURAL (lê os arquivos,
  não precisa de banco nem navegador) que cobra as cinco regras que já custaram
  correção: classe usada no JSX que não existe no CSS · `var(--token)`
  inexistente e **fallback de cor** em `var()` · token de superfície sem par no
  tema escuro · `.rh-tabela` sem o wrapper `.dash-scroll` · `<details>` com
  `cursor`/margem remendados no JSX. Roda em segundos.
- **Os testes estruturais passaram a rodar no CI.** Descoberta desta leva:
  **nenhum dos 38 testes Python do projeto rodava no pipeline** — inclusive o
  `test_upload_multipart`, escrito na v2.39.1 justamente para pegar regressão
  futura, que só rodava se alguém lembrasse de executá-lo à mão. Um
  guarda-corpo que ninguém executa não é guarda-corpo. Entram os dois que são
  **stdlib pura**; os outros três importam `app.main` e exigiriam instalar
  FastAPI + SQLAlchemy, trocando segundos por minutos. Rodam **antes** da stack
  subir: falhar ali poupa ~4 min de build + Playwright.

### Corrigido

- **32 tabelas ganharam o wrapper `.dash-scroll`** — a dívida que a v2.46 mediu
  e adiou. Medição na tela real (17 telas × 4 larguras): **2 telas estouravam
  de fato** (`arquivo` +7px e `testagem` +198px a 1000px) e mais 2 a 820px
  (`postos`, `assinaturas`). As demais apareciam "largas" mas **não empurravam
  a página**, porque estão no `DashPlanilha`, que já rola dentro de si — o
  número "31 tabelas quebradas" da auditoria era inflado. Corrigidas todas
  assim mesmo, já que o padrão se repetiria. Resultado: **68 combinações
  verificadas, nenhuma estoura**.
- **Sete classes fantasma**, a armadilha da v2.25 de volta. A pior:
  `<p className="erro">` no relatório do Creche — uma mensagem de erro que
  **não estava estilizada como erro** (virou `.alerta`). As outras viraram
  regra de verdade no `styles.css` (`.lista-fichas`, `.prova-revisao`,
  `.dash-espaco`, `.rh-conferencia-docs/-campos`) ou saíram do JSX
  (`.ficha-rh`, que nunca existiu — só `.ficha-rh-secao`).
- **14 fallbacks de cor** em `var()` removidos do `styles.css`. Todos
  apontavam para tokens que existem, então não havia bug ativo — mas é o padrão
  exato que produziu o `--texto-suave` da v2.46, e agora o teste o proíbe.

### Nota sobre o que o teste NÃO cobra

Os ~560 `style` inline de espaçamento **não** reprovam o CI. São dívida
herdada; transformá-los em erro travaria o projeto sem consertar nada. Ficam
medidos aqui e são pagos tela a tela — foi assim que a v2.47 e esta leva
reduziram alguns deles de passagem.

## [2.47.1] — 2026-08-02 — O respiro e a setinha (padronizados no CSS)

Dois defeitos que o Bruno pegou em prints da v2.47 — ambos introduzidos por
ela. Não eram "para tratar depois": o padrão já existia e a leva não o seguiu.

- **Card do posto colado na lista de documentos.** Todo `.rh-card` tem
  `margin-bottom`, mas a `.rh-revisao` (a lista) é um grid, não um card, e não
  declarava o seu. Ninguém tinha visto porque, até a v2.47, ela era o **último**
  bloco da tela — o defeito nasceu ao pôr o cadastro logo abaixo.
- **A setinha ▸ do "Histórico e consulta" furava o padding do card.** Culpa do
  `list-style-position: outside` que eu mesmo escrevi ao criar
  `details.rh-card > summary`: com `outside`, o marcador é desenhado FORA da
  caixa de conteúdo e encosta na borda.

Como a pergunta era "isso vai se repetir em outras partes?", a correção foi
feita na **regra base**, não no ponto do defeito:

- `summary` agora tem `cursor: pointer`, `list-style-position: inside` e anel de
  foco no `styles.css`. Isso apagou **seis remendos inline** espalhados por
  `Detalhe`, `Diagnostico` e `Config` — três `style={{ cursor:'pointer' }}` e
  três `style={{ marginTop }}` — e evita o próximo.
- `details:not([class])` ganha o respiro do dobrável solto. O `:not([class])`
  não é detalhe: sem ele, a regra global sobrescrevia o espaçamento de
  `.ficha-rh-secao` e as seções da ficha iam de 8px para 12px — **regressão numa
  tela que estava certa**, pega ao medir os três casos lado a lado antes de
  fechar.

Verificação: `deploy-tela-branca` 8/8, medição no Chromium dos três tipos de
`<details>` (com classe própria, sem classe, e card dobrável) e conferência
visual no tema escuro.

## [2.47.0] — 2026-08-02 — A tela do candidato para de fazer você rolar

Segunda leva da reforma de frontend, e a que ataca a queixa original do Bruno:

> *"em especial quando entro em algum candidato para ser admitido, nada
> alinhado, sem padrões... hora são seguidos, hora não"*

**O diagnóstico do briefing estava incompleto, e a discussão em party mode o
corrigiu.** A leitura inicial era "a fila de trabalho está por último — suba
ela". Mas quando o Bruno respondeu que usa a tela para **duas** coisas de peso
igual (conferir documentos E corrigir cadastro), o problema real apareceu:
havia **seis blocos de consulta enfiados ENTRE as duas coisas que ele mais
usa**. Ele aprovava um documento lá embaixo, rolava para cima para acertar o
posto, e voltava. Só subir a fila não resolveria — inverteria quem fica longe
de quem. **O ganho não vem de reordenar: vem de tirar a consulta do meio.**

### Mudado

- **Três faixas, nesta ordem:** (1) documentos — a fila de revisão; (2)
  cadastro — posto, modelos e ficha, **colado** na primeira; (3) consulta —
  fichas, testes, roteiro, mini-CRM, telemetria e diagnóstico, agora dentro de
  um `<details>` fechado no fim ("🔎 Histórico e consulta desta pessoa").
  Nada foi removido da tela; o que não é trabalho diário deixou de ficar no
  caminho. Sem abas: decisão explícita do Bruno.
- **O cabeçalho parou de mentir sobre a importância das ações** (achado ao
  olhar a tela renderizada, não no código): "⬇ Baixar dossiê" levava o
  `btn-principal` e virava um botão verde gigante, enquanto **"Efetivar como
  colaborador" — que é irreversível — parecia secundário ao lado dele**. Os
  textos ainda quebravam em duas linhas dentro dos botões. Agora efetivar é a
  única ação primária e as demais são `btn-mini` uniformes: o cabeçalho caiu
  para **50px numa linha só**, e a página de 1426px para 1371px.

### Corrigido

- **Mensagem que aparecia fora do campo de visão.** `PostoServico` (o card do
  meio da tela, ~14 controles) mandava o resultado do "Salvar posto" para a
  mensagem global **do topo** — a pessoa salva olhando para o meio e a
  confirmação aparece onde ela não está vendo. É o mesmo defeito que a v1.96
  corrigiu na ficha, sobrevivendo em outros componentes. Ganharam mensagem
  local: `PostoServico`, `ModelosDoColaborador` e `FichasStatus` (este porque a
  reordenação o levou para dentro da faixa de consulta, no fim da página).
  **Não foram os 20 pontos de `setMsg`** — o critério que ficou é *distância*:
  componente colado no topo (contato, informativo) pode continuar usando a
  global.
- **Dois blocos sumiam ENQUANTO CARREGAVAM**, fazendo a tela pular na cara de
  quem já estava lendo. `PostoServico` (`if (!postos) return null`) e
  `ModelosDoColaborador`, que era pior: usava `if (!modelos || modelos.length
  === 0)` — a **mesma linha** para "ainda não chegou" e "não existe nenhum",
  dois estados indistinguíveis. Agora reservam o lugar enquanto carregam.
  Sumir quando **não se aplica** continua valendo (escolha do Bruno: mantém a
  densidade baixa) — o que não pode é sumir por estar carregando.
- Grade de 2 colunas deixava **meia linha vazia** quando o card de modelos não
  tinha nada a mostrar. Nova `.rh-grid-auto` (auto-fit) adapta a quantidade de
  colunas ao que existe de fato.
- Mais dois hex chumbados a menos (`#0fb257`, `#889` nos chips do cabeçalho) e
  dois `style` inline de layout trocados por primitiva existente.

### Verificação

`npm run build` ok · `deploy-tela-branca.spec.js` **8/8** · tela conferida
**renderizada** nos dois temas e em dois estados de candidato (docs pendentes e
aprovado), com medição de altura e de estouro horizontal. Foi essa conferência
visual — não a leitura do código — que revelou o problema do cabeçalho.

## [2.46.0] — 2026-08-02 — Contraste, foco e telas que travavam

Primeira leva da reforma de frontend. O pedido do Bruno foi de **design e
experiência de uso** — mas a auditoria mostrou que a base já tem um bom sistema
de design (`08-sistema-de-design.md`), com o vocabulário de botões 100%
consistente, wrapper de página em todas as telas, zero classes inventadas e só
2 classes mortas em 362. **O problema não era falta de padrão: eram defeitos
concretos que o padrão já proibia, e que ninguém tinha medido.**

Por isso esta leva não mexe em layout. Ela corrige o que impedia alguém de ler
ou de usar a tela — e deixa a reforma visual para as próximas, sobre uma base
sem bug.

### Corrigido

- **`--texto-suave` era um token FANTASMA.** Quatro regras do `styles.css` o
  usavam com fallback de cor fixa (`var(--texto-suave, #47554d)`) e ele **nunca
  foi definido** — então o cinza-escuro valia nos DOIS temas. Medido no
  navegador: **2,09:1 de contraste no tema escuro**, contra o mínimo de 4,5:1
  da WCAG AA. Afetava a leitura das opções de questão nas Provas e no Banco de
  Itens. Agora tem par claro/escuro: **12,29:1**. É exatamente a armadilha que
  o §3 do sistema de design descreve ("nunca dependa de fallback de cor fixa") —
  estava documentada e ativa.
- **`--tinta-suave` não tinha par escuro** (3,61:1). Usado em 12 lugares. Passou
  a inverter com o tema.
- **O motivo do indeferimento do creche era ilegível no tema escuro.** As caixas
  de *devolução* e de *indeferimento* do `CrecheLink` usavam `.alerta` com
  `background: '#fff8ec'` inline por cima — fundo claro chumbado, que no escuro
  vira uma caixa branca isolada. É o **portal público**, e é a caixa que carrega
  a informação de que a colaboradora precisa para corrigir o pedido. Agora usam
  `.aviso-inline`, que também foi tokenizada (ela tinha o mesmo defeito, e no
  tema claro dava 4,48:1 — abaixo do mínimo). Agora: **5,39:1** no claro e
  **9,06:1** no escuro.
- **Telas que travavam em "Carregando…" para sempre.** Se a API falhasse,
  `dados` ficava `null` e não havia erro nem retry — indistinguível de rede
  lenta. Corrigido em: `Detalhe.jsx` (a tela de um candidato — a mais usada do
  painel), `Diagnostico.jsx` (a ferramenta que existe *para* investigar quando
  algo falha) e `TelemetriaRH.jsx`. Todos seguem o padrão que já existia e
  funcionava em `Detalhe.jsx::FichaRH`: mensagem + "tentar de novo".
  Na Telemetria a falha é **anunciada** em vez de silenciosa: numa tela de
  monitoramento, silêncio se confunde com "nenhum problema".
- **Foco invisível no `SelectBusca`** — `outline: none` sem substituto no campo
  de busca. Como o `SelectBusca` é o componente de todos os filtros do painel
  (§6c), quem navega por teclado perdia o foco justamente ali. O anel global de
  4px ficaria pesado num campo que já é `autoFocus`, então o foco virou a
  própria borda inferior, reforçada.
- **Foco quebrado no tema escuro no `.ajuda-q`** (o ⓘ do glossário): o realce
  era `#dfe8e0` fixo. Passou a `--verde-suave`, que inverte, mais um
  `:focus-visible` explícito.
- **Cinco botões só-símbolo sem nome acessível** (`↑` `↓` `×` `×` `✕` em
  Assinaturas, Banco de Itens, Provas e Modelos) — um leitor de tela anunciava
  "seta pra cima, botão". Ganharam `aria-label` com o item a que se referem
  ("Subir *Termo de VT*", "Remover a opção B"), não só a ação.
- **Dois painéis abriam e não fechavam** (§6 do design: "tudo que abre, fecha"):
  o Diagnóstico do colaborador e o "Revisar endereços" das Configurações.

### Medido e adiado, de propósito

- **As ~35 tabelas sem `.dash-scroll`** (risco de estouro horizontal acima de
  800px) **não foram corrigidas nesta leva**. A tentativa óbvia — pôr
  `overflow-x: auto` na própria `.rh-tabela` — foi testada no navegador e
  **não funciona**: `display: table` ignora `overflow`, e a página estourava
  igual. A correção real exige envolver cada tabela num wrapper (35 edições de
  JSX) ou migrá-las para o `DashPlanilha`. Fica para a leva de dívida
  estrutural, com o guarda-corpo automatizado junto. Registrado no `CLAUDE.md`
  para não se tentar o atalho de novo.

### Verificação

`npm run build` ok · `deploy-tela-branca.spec.js` **8/8** · contraste medido no
Chromium real, nos dois temas, com a folha de estilo de verdade. As 4 falhas do
`portal.spec.js` são de credencial do banco local (senha já trocada, o teste usa
a inicial) — **preexistentes**, confirmadas com as alterações revertidas.

## [2.45.0] — 2026-08-02 — Trocar a matrícula sem partir o histórico

Fecha o item 5 — e a leva inteira de 2026-08-01:

> *"Ter a opção de trocar o número da matrícula de um admitido/colaborador."*

O cuidado aqui não é burocracia. A matrícula é a **chave** com que o import de
ponto do Tirvu encontra a pessoa. Trocar o número sem guardar o antigo partiria
o histórico de frequência dela em dois — e uma planilha de período anterior,
que ainda traz a matrícula velha, deixaria de casar. **Sem erro nenhum na
tela**: o registro simplesmente vira órfão.

Perguntado, o Bruno escolheu levar o histórico junto.

### Adicionado

- **Troca na própria linha** da tela de Colaboradores (a matrícula passou a ser
  uma coluna), com **motivo obrigatório** — ação manual do RH sai com motivo.
- **`matriculas_anteriores`**: a lista do que a pessoa já teve (migration
  `b4c5d6e7f8a9`). Lista, e não campo único — ninguém troca de matrícula uma
  vez só na vida (recontratação, correção, fusão de cadastro).
- **`_casar_matricula` passa a olhar as antigas**, então o ponto importado com
  o número velho continua caindo na pessoa certa. Quando o RH troca, a tela
  avisa quantos períodos de ponto estão pendurados.

### Notas

**Unicidade normalizada**: `003035` e `3035` são a mesma matrícula para o
Tirvu, e duas pessoas com o mesmo número é indistinguível de uma pessoa com
duas — o ponto passaria a cair na errada. 409 `matricula_em_uso`.

**A matrícula ATUAL tem precedência sobre a antiga de outra pessoa.** Números
são reciclados: se alguém recebe hoje um número que outra pessoa usou no
passado, o ponto vai para quem o usa agora.

Auditoria com o de → para, o motivo e quantos períodos de ponto existiam.

Coberto por `tests/test_trocar_matricula.py`, **validado por mutação** (trocar
sem guardar o histórico; unicidade sem normalizar zeros). O teste também foi
endurecido para **falhar dizendo qual garantia caiu** em vez de morrer com
`TypeError` — mensagem de falha é o que serve a quem lê daqui a meses.

## [2.44.0] — 2026-08-02 — Ponto e empresa já no convite

Fecha o item 4 da leva de 2026-08-01:

> *"Tornar obrigatório o RH marcar a empresa na hora de gerar o link para o
> candidato, bem como se bate ponto ou não, pois isso é uma das coisas
> fundamentais para o Tirvu."*

### Modificado

- **`registra_ponto` é obrigatório no convite** (422
  `registra_ponto_obrigatorio`). Era pendência só na hora do export — e o
  Tirvu **aceita a célula vazia calado**, então o colaborador nascia lá sem a
  marcação e ninguém descobria.
- **Empresa entra no cadastro**, já escolhida quando existe uma só — que é o
  caso do grupo. O seletor aparece apenas com duas ou mais.

### Notas

Exigir o ponto aqui **não briga** com a regra da v1.82 (que decidiu não torná-lo
obrigatório no formulário para não travar a edição de quem veio importado do
Tirvu sem o campo): no convite não existe importado — a admissão começa agora.

**A empresa continua fixa = 1 no export** (`EMPRESA_TIRVU_ID`, decisão de
2026-07-24, reconfirmada pelo Bruno ontem). O campo serve ao cadastro interno.
Obrigar um clique numa lista de um item é teatro, não conferência — por isso a
tela pré-seleciona em vez de exigir.

Ficou registrada a discordância levantada na revisão: campo obrigatório sem
saída pode fazer o RH marcar qualquer coisa só para o formulário passar. O
Bruno decidiu assim mesmo, ciente. Se aparecer gente marcada "Sim" que não bate
ponto, o próximo passo é o padrão vir do POSTO.

A validação vem **depois** de jornada e cargo de propósito: quem esquece o
formulário inteiro precisa ouvir primeiro sobre os campos na ordem da tela.
Coberto no `smoke_test` junto das demais obrigatoriedades (15/15), e os oito
testes que criam convite foram atualizados.

## [2.43.0] — 2026-08-02 — PCD registrado pelo RH, e o laudo com como chegar

Fecha o item 1 da leva de 2026-08-01. O Bruno relatou um colaborador PCD sem a
informação nem a documentação na ficha — e, perguntado, esclareceu o essencial:
**a pessoa passou pela admissão e não marcou**. PCD é dado de saúde (art. 11 da
LGPD) e muita gente evita declarar; ela contou ao RH por fora.

Então não havia bug: havia uma lacuna um passo adiante. O RH sempre pôde marcar
`pcd` na ficha — só que, ao marcar, o **laudo** vira documento obrigatório. Se a
pessoa já concluiu o envio ou foi aprovada, o checklist dela está congelado: o
RH fazia a coisa certa e ganhava uma pendência que ninguém conseguia resolver.

### Adicionado

- **Marcar PCD depois da conclusão pede o laudo sozinho**, já liberado para
  aquela pessoa enviar pelo link dela. A resposta avisa o RH que isso
  aconteceu — senão um documento novo aparece na lista de alguém e ninguém
  sabe de onde saiu.
- **`POST /rh/candidatos/{id}/pedir-documento`**: o mesmo mecanismo para
  qualquer documento que passe a ser exigido depois. Recusa pedir o que já foi
  enviado (apagaria o que o RH talvez nem tenha olhado).
- O checklist do candidato marca o item como **pedido pelo RH**, com uma frase
  explicando que o resto do envio continua registrado.

### Notas

**A liberação vale para AQUELE slot e mais nada.** O status do candidato fica
intacto, o dossiê não se desfaz, os demais documentos continuam congelados — a
mesma disciplina da reabertura cirúrgica de 2026-07-24.

**Com o checklist ainda aberto, nada é liberado**: o slot aparece sozinho pela
sincronização normal, e marcar como "pedido pelo RH" o que é fluxo comum só
confundiria.

Fica na auditoria com o e-mail de quem pediu, e o próprio slot guarda quem
abriu a porta (`liberado_por`) — é dado de saúde registrado por terceiro sobre
alguém.

Coberto por `tests/test_pcd_pelo_rh.py`, **validado por mutação** nas duas
garantias centrais (a liberação vazando para os outros slots; liberar com o
checklist aberto). `test_reabrir_envio` e o smoke 15/15 seguem verdes — as
guardas de envio mudaram e não podiam regredir.

## [2.42.0] — 2026-08-02 — O export da ficha avisa o que vai sair em branco

Fecha o item 2 da leva de 2026-08-01. O Bruno relatou que a planilha do Tirvu
saía sem posto, cargo e jornada — e o diagnóstico foi que **ele exportou pelo
botão da ficha**, que não fazia pré-checagem nenhuma. A verificação existia
desde a v1.82, só que no caminho em massa.

O que torna isso grave é o comportamento do Tirvu: ele **aceita a célula vazia
calado**. Ninguém descobre no upload — descobre semanas depois, com o
colaborador lá dentro e o vínculo torto.

### Corrigido

- O export individual passa a rodar as **mesmas** `pendencias_linha` do export
  em massa. O front pergunta antes de baixar, listando o que falta; a resposta
  leva `X-Tirvu-Pendencias` (quem chama a rota direto também é avisado); e a
  auditoria guarda a lista.
- **Sem pendência o cabeçalho diz "nenhuma"** — silêncio seria ambíguo entre
  "está tudo certo" e "ninguém conferiu".

### Notas

O download **não é bloqueado**: às vezes se quer a planilha incompleta mesmo, e
travar trocaria um problema por outro. O que muda é que ela nunca mais sai em
silêncio.

O cabeçalho é forçado a ASCII de propósito: "Descrição da Jornada de Trabalho"
com acento derrubaria a resposta HTTP inteira.

Coberto por `tests/test_tirvu_individual_pendencias.py`, que exige inclusive
que o individual acuse o **mesmo tanto** que o massa — duas contas diferentes
para a mesma planilha seriam piores que nenhuma. **Validado por mutação.**
Smoke 15/15.

## [2.41.0] — 2026-08-01 — Logs que permitem investigar de verdade

Feedback do Bruno:

> *"achei muito bom o layout, apenas pobre de tipos de informações que são
> registradas nos logs… poderiam ser muito mais informações, para possibilitar
> investigações verdadeiras mesmo"* — e, sobre o anexo, *"o txt que vai para o
> e-mail não abre de jeito nenhum, acho que é um arquivo corrompido"*.

O que faltava não era volume: era **poder ligar uma linha à outra**. O arquivo
registrava `POST /api/c/ab12*** status=200` e, três linhas abaixo, um erro de
storage — nada dizia que eram a mesma pessoa, na mesma ação. Com dez pessoas
usando ao mesmo tempo, investigar virava adivinhação com carimbo de hora.

### Adicionado

- **`req=` e `ator=` em TODA linha.** `req` é o mesmo identificador para tudo
  que acontece dentro de uma requisição — copie-o na busca e veja a sequência
  inteira, inclusive o que veio **antes** do erro. `ator` é o e-mail do usuário
  do RH ou `candidato:<primeiro nome>`. Injetados por filtro: nenhum ponto do
  código precisa lembrar de passá-los, e por isso não há buraco justamente onde
  o defeito aparece. A resposta HTTP também devolve `X-Request-Id`.
- **Uma linha por e-mail enviado** (canal `email.envio`), com destino, assunto,
  anexos, tempo e **desfecho** — "o e-mail saiu?" é a pergunta mais frequente
  de qualquer incidente daqui, e a resposta estava espalhada entre quatro
  provedores.
- **Storage cronometrado**: falha ao gravar vira erro no log (é o arquivo que a
  pessoa acabou de enviar) e operação acima de 2s vira aviso, com a chave e o
  tamanho. Quando alguém diz "o sistema está lento", a resposta passa a ser um
  número.
- **Atalhos de assunto na tela** (e-mails, ações, arquivos, só o que está
  lento, só candidatos) e **busca com vários termos** — a linha precisa conter
  todos, então `creche ERROR` cruza as duas perguntas.
- Botão **"Atualizar agora" ao lado das linhas** e a **hora da leitura**: a
  dúvida sobre estar vendo o agora era o que fazia a tela parecer parada.

### Corrigido

- **Hora de Brasília no log** (com o deslocamento escrito, `-0300`). O
  container roda em UTC: quem lia a tela às 14h procurava "14:" no arquivo e
  encontrava as 11h. `TZ: America/Sao_Paulo` foi para os quatro serviços no
  compose **e** no `portainer-stack.yml`, o que também alinha a virada diária
  do arquivo.
- **O anexo do e-mail declarava-se PDF, sempre.** Todo anexo saía como
  `application/pdf` — inclusive o `.txt` do log, que chegava "corrompido". O
  arquivo estava perfeito; o envelope é que mentia. Agora o tipo vem da
  extensão.
- **Os workers não escreviam nada de `INFO` no arquivo**, achado durante o
  teste: o nível vinha do `basicConfig` do `main.py`, que worker nenhum
  importa. Tudo que expurgo, alertas e vencimentos registram ("X arquivos
  expurgados", "alerta disparado") se perdia — justamente o que o Bruno queria
  poder investigar.

### Notas

O e-mail periódico ganhou um **`resumo.md`** como primeiro anexo: números por
serviço e os últimos erros de cada um, para responder "preciso olhar isso
agora?" sem abrir o log cru — que continua indo junto, agora abrindo.

Coberto por `tests/test_logs_investigacao.py`, **validado por mutação** em três
garantias (formatador voltando a UTC, nível em WARNING, `req` fixo). Smoke
15/15, `npm run build` limpo.

## [2.40.0] — 2026-08-01 — De-para de lotações: os 11% viram o resto

Fecha a lacuna medida na v2.39. Cargo casa em 100% e jornada em 99%, mas
**posto casava em 11%**: a lotação vem abreviada na planilha do Tirvu
("INEP ADM", "ANAC") e o apelido do posto aqui é o padrão longo
("ANAC - 14/2026 - AEROPORTO"). Não é falha de parser — `ANAC` **é** ambíguo:
pode ser a sede ou o aeroporto.

### Adicionado

- **Card "De-para de lotações"** na Central de Importações: sobe a planilha de
  Colaboradores, o sistema lista o que não casou **ordenado por quantas
  pessoas dependem** e ordena os postos candidatos; o RH escolhe. Feito uma
  vez, as importações seguintes já sabem (tabela `lotacao_tirvu`, migration
  `f2a3b4c5d6e7`).
- O de-para entra no mesmo mapa que o vínculo em massa usa — a decisão do RH
  passa a valer para todo mundo, senão seria decoração.
- Reconfirmar **corrige** o destino em vez de duplicar; o que já foi decidido
  some da fila.

### Corrigido — o defeito que os dados reais revelaram

A primeira versão ordenava só por semelhança de caracteres, e nos dados de
produção **`INEP ADM` (174 pessoas) sugeria `IPAM` com 0,67**, à frente do
posto certo (`INEP - 37/2025 - APOIO ADM`, 0,47) — as letras I-P-A-M estão
todas lá, na ordem. Um RH apressado mandaria 174 pessoas para o contrato de
outro cliente, e **nada** acusaria o erro depois.

Agora a **palavra inteira** pesa mais que a coincidência de letras. Efeito nas
maiores da fila: `INEP ADM`, `CNJ MOTORISTAS`, `ANATEL`, `MME`, `INFRAERO SCS`
e `INTERMITENTE` passaram a sugerir o posto certo em primeiro lugar.

### Notas

**Onde há empate real, o campo vem vazio de propósito.** Duas sugestões com
pontuação parecida (o caso "ANAC") não são pré-selecionadas: escolher uma
delas seria decidir no lugar do RH disfarçando de sugestão. E a lista completa
de postos fica sempre disponível — a sugestão pode simplesmente não ter o
posto certo.

Fila real medida: **90 lotações, 1.156 pessoas esperando** (`INEP ADM` sozinha
vale 174). Coberto por `tests/test_de_para_lotacao.py`, **validado por
mutação** — desligar a regra da palavra inteira reproduz a sugestão errada do
caso real. Smoke 15/15, `npm run build` limpo.

## [2.39.1] — 2026-08-01 — Correção: o upload dizia "não foi possível ler o arquivo"

Relatado pelo Bruno minutos depois da v2.39, com print e log: os cards novos
de importação respondiam *"Não foi possível ler o arquivo (dados_invalidos)"*.

O log mostrava a coisa mais enganosa possível — `422 Field required` para o
campo `arquivo`, **com o multipart inteiro impresso ao lado**: nome do arquivo,
tipo, conteúdo, tudo à vista. Parecia falta de dado onde o dado estava.

### Corrigido

As três chamadas novas mandavam o `FormData` pelo `req()` do `api.js`, que
**força `Content-Type: application/json`**. Com multipart, quem precisa
escrever esse cabeçalho é o navegador — só ele conhece o `boundary` que separa
as partes. Sobrescrito o cabeçalho, o boundary some e o FastAPI conclui que o
campo não veio. Agora usam `buscar()` direto, como os uploads antigos
(colaboradores, ponto, currículo) sempre fizeram — era por isso que eles
funcionavam.

### Notas

A regra nunca esteve escrita em lugar nenhum, então o próximo upload repetiria
o erro. Virou `tests/test_upload_multipart.py`, que é **estrutural**: lê o
`api.js`, encontra toda função que monta `FormData` e cobra que ela não use
`req()`. Validado por mutação — reintroduzir exatamente o defeito do print faz
o teste falhar.

Os testes de backend não pegavam isto e não pegariam: o `TestClient` monta o
multipart corretamente, então o defeito só existia no caminho do navegador.

## [2.39.0] — 2026-08-01 — Vincular mil colaboradores de uma vez

Pedido do Bruno:

> *"precisa vincular os colaboradores em massa também a seus respectivos
> postos, cargos e jornadas, conforme Tirvu, quero evitar trabalho manual"*

A planilha de Colaboradores do Tirvu — a mesma que já era importada — traz, por
pessoa, `Lotação`, `Cargo`, `Jornada de Trabalho` e `PCD?`. O portal usava as
duas primeiras e ignorava as outras duas.

### Adicionado

- **Card "Vincular colaboradores"** na Central de Importações: sobe a planilha,
  o sistema cruza por CPF e mostra os números **antes de gravar** — prontos,
  divergentes, fora da base, e o que não tem par aqui.
- **Vínculo de jornada por pessoa** (`jornada_id`), que a importação nunca
  gravou: a coluna existia na planilha e não era lida.
- **PCD do Tirvu**, opcional e marcado por você: nos dados reais são **23
  pessoas** cuja condição o Tirvu registra e o portal não sabia. Cria a ficha
  se ela não existir, e fica na auditoria com quem aplicou.

### Notas — o que este módulo se recusa a fazer

**Campo com valor DIFERENTE não é sobrescrito.** Vazio aqui → o Tirvu manda;
diferente → vira lista para você decidir. O valor do portal pode ser correção
feita à mão, e passar por cima de mil registros é irreversível na prática.

**Nada é vinculado no chute.** Medido contra os dados reais: cargo casa em
100% e jornada em 99%, mas **posto casa em 11%** — a lotação vem abreviada
("INEP ADM" sozinha vale 174 pessoas; "ANAC" pode ser sede ou aeroporto). As
lotações sem par saem em fila **com quantas pessoas dependem de cada uma**,
para o de-para assistido da próxima leva. Silêncio aqui faria o RH achar que
vinculou todo mundo.

**CPF com 11 dígitos não basta:** `000.000.000-00` passaria como pessoa e
inflaria o número de "não está no portal", escondendo a causa real (cadastro
sujo na origem).

O cargo não precisa de vínculo por pessoa — `cargo_funcao` é texto e o export
resolve o ID pelo de-para da v2.38; aqui ele só preenche quem está vazio.

Coberto por `tests/test_vinculo_tirvu.py` (classificação, gravação pela rota,
ausência de N+1 — 1 linha e 40 linhas custam as mesmas 5 consultas — e a
planilha real de 1.156 pessoas), **validado por mutação** nas duas garantias
centrais: sobrescrever quem diverge e esconder a fila de lotações. Smoke
15/15, `npm run build` limpo.

## [2.38.0] — 2026-08-01 — Subir o .txt do Tirvu, sem copiar e colar

Pedido do Bruno:

> *"quero fazer o mesmo pelo front, de apenas subir os txts e o sistema
> entender"*

O Tirvu não tem botão de exportar cargos nem jornadas: o RH seleciona a lista
na tela, cola no Bloco de Notas e salva. A padronização em massa (v1.96) já
lia esse texto — mas exigia colar num campo.

### Adicionado

- **Dois cards novos na Central de Importações** (Configurações → 📥
  Importações): cargos e jornadas por **upload do .txt**. Rotas
  `preview-cargos-arquivo` e `preview-jornadas-arquivo`.
- **Codificação tolerante** (`decodificar`): UTF-8, UTF-8 com BOM e ANSI
  (cp1252) dão o mesmo resultado. Errar isso não levanta erro — quebra o acento
  e faz o casamento por texto falhar **em silêncio**, justamente nos cargos
  acentuados. O Bloco de Notas grava nos três formatos conforme a versão do
  Windows.
- **O que se perdia agora é gravado**: `cargo_tirvu.cbo`,
  `jornada.tirvu_escala` e `jornada.tirvu_tratamento` (migration
  `e1f2a3b4c5d6`, aditiva). O parser já lia essas colunas e as jogava fora.
- O card mostra **o que vai gravar antes de gravar**: quantos estão prontos,
  quantos precisam de decisão, e quais são — com o CBO e quantas pessoas usam
  cada um.

### Notas

**A porta de entrada mudou; a regra não.** O sistema continua propondo e o RH
confirmando. Cargo homônimo e jornada duplicada seguem fora do lote
automático: nos dados reais são 2 cargos ("auxiliar de serviços gerais",
"supervisor administrativo") que **87 pessoas** usam, e o que os distingue é o
CBO — que agora fica gravado para sustentar a decisão.

**`tirvu_escala` não é `escala`**: a segunda é metadado interno do parser
(seg-sex, 12x36…), com outro vocabulário. Fundir faria ler um achando que é o
outro.

**Postos já estavam resolvidos** — a importação da planilha casa por ID e já
grava razão social, CNPJ e endereço, desambiguando apelidos truncados. Nada a
fazer ali.

Medido contra os arquivos reais de 01/08: **111 cargos** (87 ativos, 2
homônimos), **464 jornadas**, **108 postos**. Coberto por
`tests/test_tirvu_txt_upload.py`, que roda com os arquivos de produção quando
existem e com uma amostra equivalente no CI — **validado por mutação** (só
UTF-8 quebra o Bloco de Notas em ANSI; CBO vazio apagando o gravado). Smoke
15/15, `npm run build` limpo.

## [2.37.0] — 2026-08-01 — O endereço estava no banco e faltava no papel

Feedback do Bruno:

> *"No Termo de opção de VT, no campo Endereço Residencial, deve constar o
> endereço completo, pois está vindo apenas a cidade, estado e cep — cadê os
> outros dados que já foram coletados?"*

Estavam coletados, sim. O endereço mora no banco em **dois formatos**: a string
única legada (`logradouro_numero_complemento`) e os campos separados —
logradouro, número, complemento — que a integração com o Tirvu exigiu. Quem
preenche a ficha hoje grava o formato **atual** e deixa o legado nulo; nada
sincroniza os dois. Quatro geradores liam só o legado e imprimiam um traço no
lugar da rua.

É a mesma armadilha dos dois formatos de data do creche (v2.27), noutro campo:
**leia os dois, nunca migre em lote.**

### Corrigido

- **Termo de Opção pelo VT** — o endereço é o objeto da declaração ("resido no
  endereço acima informado, assumindo inteira responsabilidade pela
  veracidade") e do desconto de 6% em folha. Sai completo.
- **Ficha de emergência** — endereço residencial.
- **Ficha cadastral do terceirizado** (kit Presidência/INFRAERO).
- **Ofício de apresentação à Presidência** — o endereço caía na linha de
  pontinhos de preencher à mão, com o dado inteiro guardado no banco ao lado.
- **Planilha geral do RH** (`export_planilha`) — a coluna Endereço saía vazia.
- **CEP com hífen** nos documentos (`72215-342`, não `72215342`) — achado na
  conferência visual do PDF, não em teste: o banco guarda só os dígitos, o que
  está certo para armazenar e parece dado sujo no papel.

### Notas

A leitura dos dois formatos passou a viver num lugar só,
`services/endereco.py` — `rua()` para quem já imprime bairro/cidade/CEP em
campos próprios, `completo()` para texto corrido. Parte ausente é **omitida**,
não vira traço: "Rua X, 123, -, Brasília/DF" parece defeito.

**A ficha cadastral principal e a autodeclaração de residência já tratavam os
dois formatos** e não foram tocadas — o teste garante que continuam iguais.

Por decisão do Bruno, **documentos já assinados não são reemitidos**: o dado
completo sempre esteve no banco, na tela e no export do Tirvu, e obrigar quem
já assinou a assinar de novo por um erro de impressão nosso custaria mais do
que resolve. Daqui em diante todo PDF gerado sai certo — inclusive a reemissão
de quem assinou, quando ela acontecer por outro motivo.

Coberto por `tests/test_endereco_documentos.py`, **validado por mutação** nas
duas direções (esquecer o formato atual reproduz o defeito relatado, letra por
letra: *"Ceilândia Norte, Brasília/DF — CEP …"*; esquecer o legado quebra as
fichas antigas). Smoke 15/15 e **conferência visual do PDF** — que foi o que
revelou o CEP sem máscara.

## [2.36.0] — 2026-07-31 — Telemetria com nome: de estatística a atendimento

Termina a v2.24. A telemetria é **identificada** por decisão do Bruno — o caso
de uso é *"a pessoa ligou dizendo que não consegue"* —, o backend gravava o
vínculo desde o primeiro dia… e a tela geral não mostrava de **quem** era o
evento. O RH via o erro e não sabia a quem telefonar; só existia o caminho
inverso (abrir a ficha e olhar), que exige já saber quem procurar.

### Adicionado

- **Coluna "Pessoa"** na lista de eventos, com **link para a ficha**. Evento do
  painel mostra o usuário do RH; visita pública fica sem nome — identificar
  quem não se identificou seria inventar vínculo. O nome vem em **lote** (3
  consultas no total, não uma por linha).
- **Export de jornada** (`/rh/telemetria/jornada.csv`): os eventos do período
  em ordem **cronológica**, com as três primeiras colunas no formato que as
  ferramentas de análise de caminho esperam — `user_id,event,timestamp`. A
  tela responde *está quebrando?*, *onde travam?* e *o que está lento?*; não
  responde *por onde passaram antes de desistir*, e trazer essa análise para
  dentro do painel significaria pandas e biblioteca de gráficos na imagem por
  uma pergunta ocasional. O arquivo sai daqui e a análise roda onde quiserem.
  Vai para a **auditoria**: leva nome de gente real para fora do servidor,
  como o download de log (v2.29).
- **O talento passa a ser identificado de verdade**: `definirContexto` só era
  chamado com `origem`/`token`, nunca com o talento — ou seja, o campo
  `talento_id` **nunca era gravado** e o painel da ficha do talento consultava
  algo que não existia. Agora o formulário público liga o contexto assim que o
  cadastro nasce, e o envio do currículo (onde mais se trava) fica ligado à
  pessoa.

### Corrigido

- **Segurança: identidade de talento agora exige PROVA.** A rota de coleta é
  pública e aceitava um `talento_id` cru vindo do navegador — bastava
  conhecer um id para pendurar eventos na jornada de outra pessoa, e o RH
  leria aquilo como o comportamento dela (pior do que não ter registro). O
  contrato passou a receber o `upload_token` do cadastro — assinado, com
  prazo, já existente — e o id sem prova **não vincula**: o evento é
  registrado, mas de ninguém. Mesma regra que já valia para o token do
  candidato.
- `catch {}` mudo no envio do currículo do Banco de Talentos: falhar em
  silêncio escondia justamente o problema que a telemetria existe para achar
  (a lição da v2.02). Virou fricção registrada.

### Notas

Coberto por `tests/test_telemetria.py` (nome na listagem, anonimato de quem
não se identificou, ausência de N+1, prova do talento, ordem e corte do
export), **validado por mutação** nas três garantias centrais — listagem sem
nome, `talento_id` cru aceito e CSV em ordem invertida. Smoke 15/15,
`npm run build` limpo.

O corte do export é **anunciado** na tela (`X-Telemetria-Truncado`): silêncio
faria o RH analisar um pedaço achando que era o período inteiro.

## [2.35.0] — 2026-07-31 — "Ver o que enviei" mostra o que a pessoa enviou

Fecha o último item da leva de 2026-07-30. O botão **"👁 Ver o que enviei"**
existia desde sempre no checklist do candidato — e mostrava outro documento.

O que abria era o PDF que o sistema monta: a foto **reduzida e centralizada
numa página A4 no papel timbrado**. Para o dossiê do RH está certo. Para
alguém conferir se a *própria* foto saiu legível antes de concluir o envio, é
o documento errado — a miniatura faz uma foto boa parecer ruim e uma ruim
parecer aceitável, que é exatamente a decisão que a pessoa está tentando
tomar ali. Pior no celular: era um link para a API numa aba nova, e PDF em aba
nova no Chrome do Android **baixa** em vez de abrir (o mesmo defeito que a
v2.33 corrigiu no painel).

### Adicionado

- `GET /c/{token}/documentos/{id}/originais` e `…/original/{indice}` — a
  lista do que foi enviado e cada arquivo **como veio**. O `arquivo_original_key`
  existia no modelo desde o schema inicial e **nenhuma rota o servia**.
- O checklist renderiza o documento **dentro do próprio item**, com
  `VisualizadorArquivo` (o componente da v2.33), botão para alternar entre as
  partes do envio e um toque para ver o PDF como o RH recebe.
- **Todas as partes aparecem** (frente, verso, páginas da certidão): dizer "é
  isto que você enviou" mostrando só a frente é mentira. A lista vem do
  storage, não do banco — o registro guarda a key de **uma** parte só.
- HEIC (foto de iPhone) e Word são **convertidos ao servir**, como no currículo
  da v2.33; o arquivo guardado continua o original. Conversão que falha
  degrada para download — nunca deixa a pessoa sem o arquivo.

### Corrigido

- **LGPD — o expurgo deixava o verso para trás.** `workers/expurgo.py` apagava
  as duas keys do registro (`arquivo_original_key`, `arquivo_pdf_key`), mas um
  envio tem **N** partes gravadas como `original/{i}-{nome}`. O verso do RG,
  as páginas 2..N das certidões e tudo que veio depois do primeiro arquivo
  ficavam no MinIO **para sempre**, passada a retenção — sem nenhuma tela onde
  alguém notasse a sobra. Agora varre o prefixo do slot, como
  `documentos.py::expurgar_arquivos_do_slot` já fazia.
- **A ordem é a do envio, pelo número do prefixo.** A listagem do storage é
  lexicográfica: com 10 partes, `10-` vem antes de `2-` e o verso apareceria no
  lugar da frente.

### Notas

Coberto por `tests/test_documento_original.py` (original ≠ PDF timbrado, frente
≠ verso, ordem numérica, isolamento por token, expurgo completo, conversão e
degradação, envio antigo sem original), **validado por mutação** nas três
garantias centrais — servir sempre a key do registro, expurgar só pelo
registro e não ordenar. Smoke 15/15, `npm run build` limpo.

Envio antigo sem originais no storage: a lista vem vazia e a tela cai no PDF —
o que a pessoa via antes, nunca um erro.

## [2.34.0] — 2026-07-31 — Creche: a pessoa se manifesta, não some em silêncio

Pedido do Bruno em 2026-07-30:

> *"eu quero fazer um movimento que a pessoa manifeste que de fato tem ou não
> tem crianças, e não simplesmente entrar no link e, como não tem, não fazer
> nada e sair. E hoje a pessoa pode não ter filhos, mas amanhã pode ter — então
> é importante deixar tudo bem registrado."*

A diferença é jurídica, não cosmética: sem manifestação, **"não respondeu" e
"não tem direito" são a mesma linha em branco** na planilha, e daqui a dois
anos ninguém demonstra que o elegível foi consultado.

### Modificado

- **A pergunta vem primeiro**, com as duas respostas lado a lado e o mesmo peso
  visual: *"Sim, tenho — quero solicitar"* / *"Não tenho criança nessa idade"*.
  O formulário só aparece depois da escolha. Antes, quem não tinha filho abria
  a tela, via um cadastro que não lhe dizia respeito e ia embora — e a opção de
  declarar era um link de texto pequeno **depois** do botão de enviar, dentro
  de um cartão chamado "Crianças".
- **A declaração diz o que significa e que não é definitiva**: quem passar a ter
  criança procura o RH e o levantamento é reaberto. Registro guarda **quem,
  quando e o IP** (auditoria) — é o que sustenta a prova se for contestada.
- **Quadro da consulta no painel**: elegíveis · responderam · declararam não
  ter · faltam responder. Aparece **inclusive quando não falta ninguém**, que é
  justamente quando o RH precisa dele para provar que consultou todos.

### Corrigido

- Quem declarava "não tenho" via *"Levantamento enviado! … se aprovado, você
  receberá as orientações por e-mail"* — texto de quem pediu o benefício, que
  faria a pessoa esperar por um e-mail que nunca viria. Agora tem tela própria:
  *"Resposta registrada"*.
- **409 `ha_criancas_cadastradas`**: quem já cadastrou criança não declara que
  não tem nenhuma. O registro não pode contradizer o dado ao lado dele — e é o
  registro que vira prova.

### Notas

Coberto por `tests/test_creche_manifestacao.py` (rastro da declaração, guarda
de coerência, dupla declaração, quadro fechando, reversibilidade), **validado
por mutação** nas duas garantias centrais. Smoke 15/15. Conferido no navegador
nos dois caminhos, com o registro verificado no banco (`sem_direito_declarado`
/ `colaborador` / data).

"Declarou que não tem" **conta como resposta** — a manifestação é o que se
prova, não o pedido. Levantamento aberto e nunca enviado **não** conta: a
pessoa entrou e parou no meio, e continua na fila de cobrança.

---

## [2.33.0] — 2026-07-31 — Documento renderiza na tela (e o PDF no celular nunca funcionou)

Pedido do Bruno: *"que não baixasse necessariamente o currículo, mas que tivesse
opção para renderizar o currículo na tela"* — e, como regra geral, *"todo
documento que a gente tentar abrir ali, seja currículo ou seja a certidão de
nascimento para análise de auxílio creche, que renderize ali na tela, para a
gente não precisar ficar baixando"*.

### Adicionado

- **`VisualizadorArquivo`**: componente único que renderiza **PDF**, **imagem**
  e **Word** (convertido) dentro do painel da linha, com cabeçalho, ⬇ Baixar e
  ✕ Fechar. Antes só a tela de admissão renderizava; o resto do painel abria
  aba nova — e no Word abria aba **em branco**.
- **Currículo em Word é convertido para PDF ao servir** (`talentos.py`), com o
  LibreOffice que já roda no container. Decisão do Bruno: converter, não mandar
  baixar. O **original continua guardado** — a conversão é de exibição.
- Ligado no **Banco de Talentos** (currículo na ficha) e no **Reembolso-Creche**
  (certidão e guarda das crianças, logo abaixo da tabela).

### Corrigido — o defeito que o teste não pegava

**O visualizador de PDF no celular nunca funcionou.** O `mime.types` do nginx
não conhece `.mjs`, então o worker do pdf.js era servido como
`application/octet-stream` e o navegador **recusava o módulo** ("Strict MIME
type checking is enforced for module scripts"). No celular o pdf.js é o
**único** caminho — o Chrome do Android não tem visualizador embutido —, então
todo PDF caía em *"não conseguimos exibir este PDF aqui"*. Inclusive para o
candidato.

Achado **conferindo a tela**, não em teste: o iframe existia, tinha altura, o
blob estava correto (`application/pdf`, 1117 bytes) e mesmo assim a área ficava
branca.

### Notas

⚠️ **`types { }` no nginx SUBSTITUI o mapa inteiro de MIME.** A primeira versão
da correção fez o `index.html` sair como octet-stream e o site virou
**download**. É preciso `include mime.types` antes da exceção — e agora há
teste para as duas coisas.

Coberto por `tests/test_curriculo_word.py` (conversão, original preservado,
falha degradando para download, PDF/imagem intocados) e por dois testes novos
em `deploy-tela-branca.spec.js` (8/8). **Validado por mutação nos quatro
casos.** Smoke 15/15. Conferido no navegador: o currículo renderiza legível,
numa aba só.

---

## [2.32.0] — 2026-07-30 — Os macaquinhos no campo de senha

Pedido do Bruno: *"o emoji do macaquinho tampando o olho quando está oculta, e
o macaquinho olhando entre as mãos quando visível — acho que ficaria melhor, um
pouco de clima"*.

### Modificado

- `InputSenha` agora mostra **🙈 quando o texto está oculto** (ele tampa os
  olhos, como o campo) e **🙊 quando está visível**. Antes era 👁️/🙈, com o
  macaquinho no estado invertido. Um componente, **18 campos** — login do
  painel, troca de senha, chaves de API, secrets de OAuth e webhooks.
- A tela de **Assinaturas** era o último `<input type="password">` cru do
  projeto, sem olhinho nenhum: passou a usar o `InputSenha`. Errar a senha por
  não conseguir conferir o que digitou é atrito à toa num ato jurídico.
- `.rejeicao .campo-senha { flex: 1 }` no `styles.css`: o campo de senha é um
  `<span>` que ENVOLVE o input, então a regra antiga (`.rejeicao input`) não o
  alcançava e ele ficaria espremido na linha.

### Notas

Conferido no navegador nos dois estados: 🙈 com `type=password`, 🙊 com
`type=text`, `aria-label` acompanhando. O emoji é `aria-hidden` — quem usa
leitor de tela continua ouvindo "Mostrar/Ocultar o que digitei".

---

## [2.31.0] — 2026-07-30 — "Sem internet" no comprovante de residência: não era a internet

Relato de campo: *"no campo de comprovante de residência do Jonatas, na hora
que tenta puxar o arquivo do celular, informa que está sem internet"*.

A internet dele estava boa. O comprovante é o **único** slot com OCR
bloqueante, e o texto era lido **duas vezes com os mesmos bytes** na mesma
requisição — uma para a regra dos 90 dias, outra para as sugestões de ficha.
Cada leitura é uma ida à Mistral com `timeout=30s`, então um comprovante de
duas páginas podia passar de **120s** de trabalho síncrono contra os **60s** de
`proxy_read_timeout` do nginx. O nginx cortava, o `fetch` rejeitava, e o front
traduzia **qualquer** rejeição como "você está sem internet" — mensagem que
ainda convida a tentar de novo, gastando outros 60s.

Quatro correções, em camadas independentes:

### Corrigido

- **OCR roda uma vez por arquivo** (`normalizacao.py`): `_texto_do_envio`
  passou a memoizar por conteúdo (SHA-256 dos bytes + extensão). O tempo do
  upload do comprovante caiu pela metade. Cache com teto baixo (32) e limpeza
  ao encher — texto de documento é dado pessoal, não pode acumular na memória
  do processo.
- **O nginx deixou de cortar aos 60s** na rota de upload do candidato
  (`location ~ ^/api/c/[^/]+/documentos/`): `proxy_read_timeout`,
  `proxy_send_timeout` e `client_body_timeout` em 300s. Não é licença para
  demorar — é a rede de segurança para 4G com foto pesada, já que a causa de
  origem foi cortada acima.
- **"Sem internet" só quando é sem internet** (`api.js`): o `fetch` rejeita
  igual para falta de sinal e para conexão cortada no meio. Agora o erro
  distingue três casos — `sem_conexao` (confirmado por `navigator.onLine`),
  `demorou_demais` (rejeitou após 20s com a rede de pé) e
  `conexao_interrompida` —, cada um com a sua mensagem. A de `demorou_demais`
  diz explicitamente *"não foi a sua internet"* e orienta a reduzir a foto.
- **Os leitores do wizard pararam de culpar a foto**: `LeitorComprovante` e
  `LeitorRG` traduziam qualquer falha como *"não conseguimos ler a foto"*,
  mesmo quando o problema era o envio, e **não emitiam telemetria nenhuma** —
  o ponto mais cego do fluxo. Agora separam erro de servidor e registram
  `falha_no_envio`, como o checklist.

### Notas

Coberto por `tests/test_comprovante_ocr.py`, **validado por mutação** (remover
o cache e trocar a chave por uma fixa — as duas detectadas). A segunda mutação
protege o risco que o próprio cache introduz: chave errada faria o endereço de
uma pessoa aparecer na ficha de outra, bem pior que a lentidão original.
Smoke 15/15, E2E de tela branca 6/6 (regra do CLAUDE.md ao mexer no
`nginx.conf`), `nginx -t` na rede do compose.

A telemetria de `falha_no_envio` ganhou `rede` e `ms`: sem isso, timeout de
proxy e falta de sinal ficavam indistinguíveis nos números — foi o que atrasou
este diagnóstico.

---

## [2.30.0] — 2026-07-30 — Reembolso-Creche: um bloco de filtros, não dois

Feedback do Bruno, com print: *"na página de dash do reembolso creche tem dois
cards, acho que apenas um, tudo concentrado e coeso de filtros, seria mais
interessante"*.

Havia **dois filtros de status na mesma tela** — o de cima (server-side,
"Aguardando análise") num card próprio, e o `Status: todos` dentro da barra do
dash. Filtrar por um enquanto o outro dizia coisa diferente dava resultado que
parecia errado.

### Modificado

- `DashPlanilha` ganhou a prop **`filtrosExtras`**: filtros que o pai controla
  (tipicamente server-side) entram na **mesma grade** dos filtros de coluna, com
  o mesmo `SelectBusca`. O card separado deixou de existir.
- No creche, a coluna Status **perdeu o `filtro:`** — quem filtra status agora é
  só o seletor "Situação". A coluna segue ordenável e os cards clicáveis
  (Devolvidos/Ativos) continuam funcionando, porque a filtragem em memória roda
  sobre todas as colunas, não só as que declaram `filtro`.
- O contador "34 registro(s)" saiu: o card **"No filtro"** já mostrava o mesmo
  número, logo acima — era outra duplicação.

### Notas

O filtro **continua server-side**: verificado no navegador que trocar a situação
dispara `GET /rh/creche/levantamentos?status=ativo`. Trazer a base para o
cliente seria regressão de performance e de LGPD — por isso ele não virou filtro
de coluna. Regra registrada em `08-sistema-de-design.md` §6c: **um assunto, um
controle**. Conferido na tela real (login, navegação e troca de filtro por
Playwright), `npm run build` limpo.

---

## [2.29.0] — 2026-07-30 — Logs no painel: ler sem SSH, receber por e-mail

Pedido do Bruno no mesmo dia do incidente do Defender (v2.28), quando o
diagnóstico só saiu porque ele abriu terminal na VPS: *"não seria o caso todos
os logs de cada serviço ficarem armazenados em um arquivo, de modo que eu
possa lê-los a qualquer momento, sem a necessidade de dar comandos no terminal
SSH"* — e **"quero muito a tela de logs no painel"**.

O motivo é concreto: **o log do container morre no restart**. Se a Keli tivesse
travado um dia antes, não haveria rastro nenhum para ler.

### Adicionado

- **Tela `Configurações → 🧾 Logs dos serviços`**: escolhe o serviço e o dia,
  procura no texto (ex.: os 4 últimos dígitos de um CPF), filtra por nível, e
  **baixa em .txt**. Linhas de erro saem em vermelho e avisos em âmbar — é o
  que o olho procura primeiro.
- **Logs em arquivo** (`services/logs.py`): cada serviço escreve o próprio
  arquivo num volume compartilhado, com rotação diária. O stdout continua
  existindo (`docker logs` segue funcionando) — se o volume falhar, degrada
  para ele em vez de derrubar o serviço.
- **Envio por e-mail 4× ao dia** (`workers/logs_email.py`), a cada 6 horas, com
  resumo do período e os arquivos em anexo. Entrega pela **matriz de avisos
  internos** (evento `logs_periodico`), então os destinatários se editam na
  tela, vários por vírgula — regra da v2.21 para e-mail novo. Botão
  **"Enviar os logs agora"** para conferir sem esperar a janela.
- **Retenção configurável, com `0` = indeterminado** (escolha explícita do
  Bruno). O expurgo pega carona no worker diário e **nunca** apaga o log
  corrente, só os rotacionados por dia.

### Decisões

- **Não montamos o socket do Docker.** Ler `docker logs` de dentro da API
  exigiria `/var/run/docker.sock` no container — isso daria à API **controle
  total do Docker do host**, e a API é justamente o que está exposto à
  internet. Consequência aceita: aparecem aqui os serviços nossos (api,
  worker, alertas, expurgo); Postgres e MinIO seguem no `docker logs`.
- **LGPD**: estas linhas contêm CPF, e-mail e nome — foi o CPF completo no log
  que permitiu achar a colaboradora travada. Antes eram voláteis; em arquivo,
  viram dado pessoal armazenado. Por isso a retenção é configurável e **baixar
  vai para a auditoria** (`logs_baixados`), como qualquer export de dado
  pessoal.

### Notas

Coberto por `tests/test_logs.py`, **validado por mutação** (retenção 0 voltando
a apagar e a validação de path traversal removida — as duas detectadas).
Validado também contra a stack real: arquivo escrito, volume compartilhado
entre containers, busca, download (2.974 bytes), `../../etc/passwd` barrado e
e-mail entregue. Smoke 15/15.

---

## [2.28.0] — 2026-07-30 — O antivírus do e-mail estava gastando o link antes da pessoa

Uma colaboradora passou **seis horas** sem conseguir entrar no creche. Sete
códigos enviados **com sucesso** — o log do M365 confirma cada um. Nenhuma
entrada. E ela não aparecia em relatório nenhum, porque o painel só enxergava
quem *não recebeu* e-mail.

O log de produção mostrou o padrão sem ambiguidade: ela **pedia** o código do
IP do órgão (`200.130.24.100`) e o `creche_entrou_pelo_link` chegava segundos
depois de IPs da **Azure** (`74.179.68.x`, `135.232.x`, `72.153.x`). Não era
ela. Era o **Microsoft Defender / Safe Links**, que pré-abre todo link de
e-mail para escanear — comportamento padrão em qualquer empresa com Microsoft
365, e a Green House atende órgãos públicos.

Como o link era de **uso único** e o `GET /retomar` o **consumia**, o scanner
ficava com a sessão. Ela clicava e recebia "link expirado"; caía no código; o
código também falhava, porque cada novo pedido criava outro acesso e só o
**mais recente** era conferido — então o e-mail aberto na tela dela já não
valia. Pedia outro código, e o ciclo recomeçava.

### Corrigido

- **`GET` não tem mais efeito colateral** (`creche_publico.py`, `portal.py`):
  `retomar` só LÊ. Entrar virou `POST /creche/entrar/{token}` e
  `POST /portal/entrar/{token}` — **scanner de e-mail segue link, não aperta
  botão**. No front, a pessoa vê "É você? · Sim, entrar"; o clique é que
  consome. Um passo a mais na tela é o que faz o link **chegar**.
- **Qualquer código dentro dos 15 minutos vale** — antes só o acesso mais
  recente era conferido, e pedir um segundo código invalidava calado o e-mail
  que estava aberto na tela (o 422 com o código certo na mão). É a mesma
  garantia que a assinatura e o teste já davam; lá o código é sobrescrito no
  MESMO registro, aqui cada pedido cria um `AcessoCreche`, então a equivalência
  exigia conferir todos os vivos. Validade e cota de tentativas seguem iguais.
- **Tentativa recusada virou registro** (`creche_codigo_recusado`): 422
  repetido no mesmo CPF é o sinal mais forte de gente travada e não ia para
  lugar nenhum. O relatório **"Não conseguiram acessar"** ganhou o terceiro
  motivo — *Código recusado* —, que é o mais enganoso dos três: o envio
  funcionando dá a impressão de que está tudo bem.
- **Mensagem do código corrigida**: dizia "use o do e-mail MAIS RECENTE",
  orientação que mandava desprezar um código válido. Agora fala do prazo, que
  é o que de fato expira.

### Notas

Coberto por `tests/test_retomada_acesso.py`, **validado por mutação** (duas
mutações: devolver o consumo ao `GET` e voltar a conferir só o código mais
recente — as duas foram detectadas). Smoke 15/15.

A regra da v2.17 (*"código e link chegam na mesma caixa, provam o mesmo
fator"*) **continua valendo** — o que mudou não foi a confiança no link, foi
**quem** o abre primeiro.

---

## [2.27.0] — 2026-07-30 — Creche: a idade das crianças estava errada para todo mundo

Feedback do Bruno: *"por que quem nasceu em 2024 você diz que não tem menos de
4 anos e 11 meses? A leitura foi certinha, mas as contas estão erradas."*
Estava certo, e o problema era pior do que parecia.

### Corrigido
- **TODA criança aparecia como "❌ passou de 5a11m"**, inclusive um bebê de 2
  anos. A causa não era a aritmética: `_idade_anos_meses` lia apenas
  `dd/mm/aaaa`, mas o `InputData.jsx` do wizard devolve **ISO** (`aaaa-mm-dd`)
  por padrão — e é assim que a maioria dos registros foi gravada. O
  `split("/")` falhava, a idade virava `None`, e `None` era tratado como "não
  elegível". **O RH indeferiria quem tem direito.**
- `partes_da_data` aceita os dois formatos, com validação de sanidade (mês 13,
  ano absurdo → não vira idade inventada).
- **"Passou da idade" e "não consegui ler a data" viraram estados DIFERENTES**
  na tela (`idade_desconhecida` → "⚠️ conferir data"). Mostrar as duas coisas
  como ❌ é o que levaria ao indeferimento por engano.
- O `revisar_idade` (risco de glosa) deixou de acusar quem só tem data ilegível.
- A data agora sai sempre em `dd/mm/aaaa` na tela, venha como vier do banco.

### Por que não foi feita uma migração dos dados
O campo é `String(10)` livre e há registros das duas formas. Reescrever em lote
significaria adivinhar formato — `03/04` é 3 de abril ou 4 de março? — em dado
que decide dinheiro no contracheque de gente real.

### Alterado
- **O painel do benefício abre NA LINHA do colaborador**, não no fim da página
  (*"tenho que rolar a tela lá no final para conferir e depois voltar ao topo"*).
  O `DashPlanilha` já tinha `linhaExpandida`; o Creche não usava — renderizava o
  detalhe depois da tabela inteira. É a regra que já estava no CLAUDE.md desde a
  v1.83.

### Verificação
`tests/test_creche_idade.py` cobre os dois formatos, o caso real do incidente, o
limite de 5a11m, data ilegível e a exibição. Data de referência **fixa**, senão
o teste passaria hoje e falharia no mês que vem. Validado por **mutação**:
repondo a leitura só-BR, 12 asserções falham. Conferido na tela com os dados do
print: Yuri 5a0m ✅ e Hannah 2a5m ✅.

---

## [2.26.0] — 2026-07-30 — A tela de Telemetria estava fora do padrão visual

Feedback do Bruno: *"achei tão feia essa página, por que não seguiu o padrão de
layout? de cards, espaçamentos, alinhamentos?"*. Estava certo, e a causa não era
gosto.

### Corrigido
- **Onze classes de CSS inventadas** (`rh-secao`, `rh-bloco`, `rh-acoes`,
  `rh-form-inline`, `campo-check`…) que **não existiam** no `styles.css`. O JSX
  parecia correto e o build passava — CSS não reclama de seletor inexistente —,
  mas a tela saía crua: sem card, sem borda, sem espaçamento.
- As três telas (`TelemetriaRH`, `AlertasTelemetria`, `TelemetriaPessoa`)
  reescritas com as primitivas reais de `08-sistema-de-design.md`: `.rh-card`,
  `.rh-grid-2`, `.rh-topo`, `.rh-metricas`, `.rh-tabela`, `.campo`/`.rotulo`.
- **Cores em hex cru** (`'#c33'`, `'#c80'`) trocadas pelos tokens semânticos
  `var(--perigo)` / `var(--atencao)`, que invertem no tema escuro.
- Duas classes genuinamente novas entraram no `styles.css` com tokens, em vez de
  serem inventadas no JSX: `.bloco-codigo` (JSON de detalhe, rola na horizontal
  em vez de esticar o card) e `.campo-sem-margem`.

### Verificação
Auditoria automática dos três arquivos: nenhuma classe sem CSS, nenhum token
inexistente, nenhum hex cru. Conferido visualmente nos temas **claro e escuro**.

### Lição registrada no CLAUDE.md
Classe que não existe não estiliza nada, e o build não avisa. Antes de commitar
tela nova: `grep` de cada classe usada no `styles.css` — e ler o sistema de
design **antes** de escrever, não depois do feedback.

---

## [2.25.0] — 2026-07-30 — Alertas: o sistema avisa em vez de esperar a pergunta

A telemetria da v2.24 grava tudo certo, mas é **passiva** — alguém precisa abrir
a aba. No incidente de 29/07 isso não bastaria: o erro estaria gravado às 11h01
e a descoberta continuaria dependendo de o candidato ligar.

### Adicionado
- **Quatro tipos de alerta**, todos com regras **editáveis na tela** (nada de
  limiar chumbado no código — quem convive com os números é quem deve ajustá-los):
  - **Erro novo** — uma mensagem que nunca tinha aparecido. O caso de 29/07:
    teria avisado às 11h05.
  - **Volume de erros** — um erro conhecido que disparou; assinatura clássica de
    deploy ruim.
  - **Pico de travamentos** — muita gente travando no mesmo ponto. Indica que
    algo quebrou, não que as pessoas estão desatentas.
  - **Lentidão** — página acima do tempo aceitável **para a maioria** (mediana).
- **Entrega pela matriz de avisos internos** (evento `telemetria_alerta`), com
  texto editável no catálogo de e-mails — a mesma mecânica dos outros 40 avisos,
  nenhum caminho paralelo.
- **Worker `alertas` a cada 15 minutos**, serviço próprio no compose e no stack
  do Portainer. Não foi embutido no `expurgo` (24h): ali o alerta chegaria um
  dia depois e não serviria para nada.
- **"O que dispararia agora?"** — simulação que **não envia e não gasta o
  silêncio**. Testar não pode impedir o alerta real de chegar depois.
- **Histórico de alertas enviados**, com destaque em vermelho quando o alerta
  saiu para **ninguém** (destinatário não cadastrado): sem isso, caixa silenciosa
  seria ambígua — "não houve problema" e "quebrou" pareceriam iguais.
- Quatro regras já ativas na migration: o recurso nasce vigiando, em vez de
  esperar alguém configurar o que ainda não doeu.

### Corrigido
- **`/c/assinatura` era mascarado como se fosse token** (`/c/assina***`), e o
  mesmo erro aparecia **duas vezes** no alerta — uma por grafia, como se fossem
  problemas diferentes. Agrupar errado infla a contagem e esconde o padrão.
  `_parece_token` agora exige tamanho **e** caixa mista: nome de etapa nunca tem
  as duas coisas.
- **O teste do catálogo de e-mails travava o NÚMERO de avisos** (`== 8`). Cada
  aviso legítimo quebraria o teste sem apontar defeito, e a tentação seria só
  incrementar a constante — um teste que não protege nada. Agora o vínculo
  aviso↔evento é derivado do próprio catálogo.

### Corrigido depois, ao conferir a stack de produção
- **O botão "Ver na telemetria" do e-mail saía vazio**: o template declarava o
  botão, mas o `alertas.py` nunca passava a variável `link`. O worker roda no
  cron, sem `request`, então não há como derivar a URL da requisição — é o
  único ponto do sistema em que `BASE_URL` é mesmo obrigatório. Adicionado ao
  serviço `alertas` nos dois compose. Um aviso que não leva a lugar nenhum
  obriga o RH a caçar a tela na mão.

### Verificação
`tests/test_alertas.py` (7 blocos) cobre dedup, silêncio por problema,
agrupamento, limiar, mediana, filtro por origem, isolamento entre regras e
histórico. Validado por **mutação** — e a mutação expôs um teste fraco:
desativar a checagem de "já visto" passava. Faltava o caso de que **"novo" é
para sempre**, não pela janela de silêncio; sem ele, um erro conhecido voltaria a
ser anunciado como novidade de hora em hora. Caso adicionado, mutante agora
falha. Ciclo real conferido na stack: 4 erros simulados → alerta disparado →
e-mail entregue → 2ª verificação silenciosa.

---

## [2.24.0] — 2026-07-30 — Telemetria de uso: o que acontece no aparelho das pessoas

Resposta direta ao incidente das v2.22/v2.23. Dois candidatos travaram e o erro
morreu no navegador deles: o servidor registrou **200 em tudo**, porque do lado
dele deu certo — o `TypeError` aconteceu no React, depois da resposta. Não havia
o que procurar em log nenhum.

### Adicionado
- **`EventoTelemetria`** (migration `c9d0e1f2a3b4`) com quatro famílias:
  `erro` (exceção de JS com página, stack e versão do bundle), `friccao` (onde a
  pessoa trava), `jornada` (por onde passou, quanto tempo) e `desempenho`
  (quanto demorou no celular dela, não no servidor).
- **Telemetria individualizada na ficha da pessoa** — candidato, colaborador e
  Banco de Talentos. Responde "não consigo enviar meus documentos" com fato, e
  não com suposição. Segue a pessoa de talento → candidato, como o mini-CRM.
- **Aba Configurações → 📈 Telemetria**, organizada pelas três perguntas que
  importam, nessa ordem: *está quebrando?* (erros **agrupados** por mensagem —
  300 ocorrências do mesmo erro são UM problema, e a lista crua esconderia o
  padrão atrás do volume), *onde as pessoas travam?* e *o que está lento?*
- **Páginas lentas por MEDIANA, não média**: uma chamada de 40s distorceria a
  média e faria parecer que tudo está lento. A mediana mostra o que a maioria
  vive.
- **Retenção configurável** (padrão **1 ano**, para permitir comparação
  sazonal) com expurgo diário automático, e **expurgo por intervalo de datas**
  para limpar o que testes poluíram — registrado na auditoria.

### O que a telemetria NÃO guarda, por decisão de projeto
- **Nada do que a pessoa digita** — só o nome da etapa e o que aconteceu com ela.
- **IP truncado** (`191.180.x.x`): distingue "a operadora está com problema" de
  "o sistema está com problema" sem localizar ninguém.
- **Token do link mágico mascarado**: `/c/{token}` é credencial de acesso, e
  telemetria é feita para ser lida e exportada. Gravá-lo criaria uma planilha de
  chaves de acesso.

### Não é a Auditoria
`EventoAuditoria` responde "quem fez o quê" e é prova de ato — append-only,
nunca expurgada. A telemetria responde "como foi usar" e é descartável por
desenho. Misturar as duas transformaria dado de produto em prova jurídica, e
prova jurídica em lixo que se apaga.

### Verificação
`tests/test_telemetria.py` (8 blocos) cobre mascaramento, minimização de IP,
teto de volume (a rota é pública), agrupamento do resumo, os dois modos de
expurgo e a telemetria por pessoa.

**O teste encontrou um bug real antes do deploy**: as FKs de `candidato`/
`talento` não resolviam sem o import dos modelos, e **toda** gravação falhava —
em silêncio, porque `registrar_eventos` engole exceção por desenho. É a
armadilha da v2.02 ("catch vazio não pode engolir erro de infra") do lado do
servidor. Validado por **mutação**: removido o mascaramento do caminho de
gravação, o teste falha; restaurado, passa.

---

## [2.23.0] — 2026-07-29 — A segunda causa da tela branca: `fichas.some()` sobre `null`

A v2.22 corrigiu o nginx e a tela **continuou quebrando** — agora com a
mensagem do ErrorBoundary em vez do branco, o que revelou o erro que estava
escondido por baixo: `TypeError: Cannot read properties of null (reading 'some')`.

### Corrigido
- **`Assinatura.jsx` usava `fichas.some(...)` no corpo do componente**, mas
  `fichas` nasce `null` e só é preenchido pelo `useEffect`. O guard
  `if (!fichas) return` existia — na linha 54, enquanto o `some` estava na 26.
  O cálculo roda no **primeiro render**, antes de qualquer dado chegar:
  `null.some()` lançava e apagava a tela inteira do candidato.
- **Introduzido na v2.05** (28/07, 20:40), o que confirma a suspeita original de
  que "foi algo das atualizações de ontem para hoje". Atingia exatamente quem
  estava na etapa de **assinatura** — os dois candidatos travados.
- O sintoma engana: parece problema de rede ou de link, porque só acontece na
  janela em que a API ainda não respondeu.

### Verificação
Reproduzido com navegador real contra a stack (`pageerror` capturado, nenhuma
requisição falhando — bug de código puro). Teste novo segura a resposta da API
por 1,5s para renderizar no estado nulo; validado por **mutação** (bug reposto →
o ErrorBoundary aparece e o teste falha; restaurado → 6/6). Varredura no projeto
por `useState(null)` usado antes do guard: nenhum outro caso no caminho do
candidato.

### Lição registrada no CLAUDE.md
Estado que nasce `null` não pode ser usado no corpo do componente — o guard vem
antes do primeiro uso, não junto do `return`.

---

## [2.22.0] — 2026-07-29 — Tela em branco no candidato: o deploy apagava o script que a aba pedia

Incidente de produção. Dois candidatos travados no meio do envio da
documentação, com a **tela em branco** ao reabrir o link — e nenhuma linha de
erro em log nenhum.

### Corrigido
- **`try_files $uri /index.html` valia também para `/assets/*.js`.** Cada build
  gera assets com hash novo (`index-C1OewSkj.js`) e apaga os anteriores. O
  candidato deixa a página aberta no celular — ele sai para fotografar o
  documento e volta, que é o uso normal. Se um deploy acontece nesse meio, a aba
  pede o arquivo antigo e o nginx respondia **HTTP 200 com o HTML do index no
  lugar do JavaScript**; o navegador tentava executar `<!doctype html>` como
  script, e o React não montava. Agora `/assets/` usa `try_files $uri =404`.
- **Por que não havia o que procurar no log**: do ponto de vista do servidor foi
  um 200 bem-sucedido. O defeito era invisível para quem olhava só o servidor.
- **Explica os dois casos, inclusive o link criado no mesmo dia**: não depende de
  quando o link nasceu, e sim de a aba estar aberta durante um deploy.
- **`STATUS[s.status]` sem guarda no checklist** (`Checklist.jsx`): status
  desconhecido lançaria `TypeError` e mataria a tela igual. Não foi o gatilho
  deste incidente, mas era a mesma bomba armada.

### Adicionado
- **`ErroFatal.jsx` — o primeiro ErrorBoundary do projeto.** Não havia nenhum:
  qualquer exceção de render apagava a aplicação inteira, sem uma palavra na
  tela. Tela branca é o pior desfecho para quem está do outro lado, porque não
  diz se o problema é a internet, o link, o celular ou o sistema — a pessoa
  conclui que "não funciona" e desiste.
- **Recuperação automática de aba antiga** (`main.jsx`): falha ao carregar
  módulo = versão velha, então recarrega **uma** vez buscando o `index.html`
  novo. A trava em `sessionStorage` é obrigatória — sem ela, uma falha permanente
  viraria recarregamento infinito, que é pior que a tela branca.
- **`/api/health` mostra `migracoes.em_dia`**: se o `docker-entrypoint` falhar ao
  rodar `alembic upgrade head`, a API sobe com o schema velho e o defeito só
  aparece na cara do candidato. A revisão é **lida** do diretório de migrations —
  o `VERSAO_DEPLOY` estava congelado em `v1.50` havia vinte versões, mentindo
  com confiança.
- **Cache `immutable` nos assets**: o hash está no nome, então cachear para
  sempre é seguro e economiza banda no celular do candidato.

### Verificação
`tests/e2e/deploy-tela-branca.spec.js` roda contra o nginx real. Validado por
**mutação**: removido o bloco `/assets/`, o asset antigo voltou a responder 200
com `text/html` e o teste falhou onde devia; restaurado, 5/5 passam. Confirmado
que `/c/{token}` continua servindo o SPA — consertar o asset não podia quebrar a
navegação, que é por onde o candidato entra.

### Não era migration
Medido, não suposto: com o banco atrasado o painel do RH e o creche quebram
(`teste_vinculado` e `link_expira_em` não existem), mas as rotas do candidato
respondem 200. O `docker-entrypoint.sh` roda `alembic upgrade head`
corretamente.

---

## [2.21.0] — 2026-07-29 — Teste já respondido aproveitado no candidato

### Adicionado
- **`TesteVinculado`**: o RH aproveita para o candidato um DISC/situacional ou
  prova que a pessoa já respondeu antes de virar candidata. **Aponta, não copia**
  — o resultado é lido na origem; copiar criaria duas versões do mesmo dado e
  nenhuma confiável.
- **A identidade é registrada como o que é**: `automatico=True` quando veio do
  Banco de Talentos (o link tinha `talento_id`); `automatico=False` quando o RH
  escolheu da lista, com autor snapshot. Importa porque o link avulso de testagem
  é **anônimo** e teste decide contratação — vincular o resultado de um homônimo
  é decidir a vida de alguém com dado de outro. Por isso a lista de escolha mostra
  nome, data, qual teste e por qual link.
- **Só o RH vê**: não entra no wizard nem no dossiê, que circula.
- **Destinatários na tela dos textos de e-mail**: quem recebe cada aviso interno,
  editável junto do texto. Grava na **mesma** matriz de Avisos internos — uma
  fonte exposta em dois lugares, não duas verdades.

## [2.20.0] — 2026-07-29 — Avisos internos entram no catálogo

### Adicionado
- **`avisar_modelo(db, evento, chave_template, contexto)`**: os 8 avisos que vão
  à equipe passaram a ter assunto e corpo editáveis. O motivo não é cosmético —
  **quem recebe nem sempre conhece o sistema**: o Gabriel e o Vitor recebem o de
  uniforme, o líder de brigada recebe o de certificação vencendo.
- Catálogo vai a 40 templates. Template ausente degrada para 0 envios + log:
  aviso interno que falha nunca pode derrubar a ação do candidato que o disparou.

### Corrigido
- **O aviso "Dossiê pronto" lia `email_avisos_internos` direto, fora da matriz.**
  Desligar o evento no painel não o desligava, e cadastrar destinatário não
  funcionava — o RH configurava a matriz achando que ela governava tudo.

## [2.19.0] — 2026-07-29 — Catálogo dos documentos do sistema

### Adicionado
- Os 11 documentos da admissão numa tela só, com **amostra em PDF de verdade**
  (mesmo gerador, candidato fictício que nunca vai ao banco), download e "criar
  modelo a partir deste" nos de texto corrido.
- **Nenhum gerador foi substituído, e não devem ser**: o hash do ato de
  assinatura é calculado sobre o PDF gerado — trocar por template faria os
  manifestos já emitidos apontarem para um hash que não se reproduz.

### Corrigido
- A primeira versão trazia a lista de direitos do "Informações ao Trabalhador"
  escrita à mão, e **perdera 6% do VT, 8% do FGTS e o 5º dia útil** — texto
  plausível e errado num documento de contrato com órgão público. Virou
  `fichas.DIREITOS_TRABALHADOR` (fonte única) e o teste ganhou **âncoras**;
  "corpo não vazio + tem `{{`" deixava texto inventado passar.

## [2.18.0] — 2026-07-29 — A mensagem parou de culpar a coisa errada

### Corrigido
- `Assinatura.jsx` dizia **"verifique sua conexão"** para erro de cota — pior que
  inútil: a conexão está ótima e a frase convida a tentar de novo na hora,
  reabastecendo a cota.
- `AssinarExterno.jsx` tinha `catch {}` **mudo** ao pedir código: a falha não
  aparecia em lugar nenhum.
- "Código incorreto" passou a dizer o que resolve: **use o do e-mail mais
  recente** — só o último vale.

### Medido
Na assinatura e no teste o código é sobrescrito no mesmo registro, então **o
último enviado continua valendo depois do 429** (`test_codigo_cota.py`). Sem essa
garantia, a orientação na tela seria mentira.

## [2.17.0] — 2026-07-29 — O link do e-mail entra direto

Feedback de campo: *"foi eu mesmo quem copiou e colou o código. Impossível ter
erro."* Estava certo — o código era válido.

### Corrigido
- A cota é 5 pedidos por 15 min. Estourada, o e-mail **não saía**, mas o front
  **avançava de etapa assim mesmo** — sucesso mentiroso, o mesmo defeito da
  v2.02 pela terceira vez. A pessoa colava o código do e-mail anterior.
- 429 ganhou frase própria; botão "🔄 Reenviar o código" na própria tela.
- `confirmar` deixou de exigir `confirmado_em IS NULL`: quem entrava pelo link e
  ainda digitava o código levava "código inválido" com o código certo na mão.

### Adicionado
- **Link do e-mail entra direto** (creche e portal `/meu`): código e link chegam
  na mesma caixa, logo provam o mesmo fator — exigir os dois era atrito
  duplicado, não segurança em camadas. Uso único, 15 min. Migration
  `a8b9c0d1e2f3`; nulo = acesso antigo, que segue exigindo código.

## [2.16.0] — 2026-07-28 — "Enviar teste para mim" nos textos de e-mail

### Adicionado
- Manda o texto **em edição** para a caixa de quem está editando — ver como
  chega antes de valer para o candidato.

## [2.15.0] — 2026-07-28 — Currículo e anotações na linha do dash

### Adicionado
- O dash de Talentos mostrava "🗒️ Anotações" em todo mundo e o RH só descobria
  que não havia nada depois de abrir o modal. Agora vêm a contagem e a última
  anotação, carregadas **em lote**.

### Corrigido
- **O teste de N+1 escrito para isso expôs um N+1 antigo**: `_resumo_teste_talento`
  fazia até 3 consultas por talento, com o comentário "1 consulta, sem N+1" logo
  acima. A listagem caiu de **43 consultas para 39 talentos → 5**, constante.
- Armadilha registrada: medir N+1 com limite absoluto mede o tamanho do banco —
  compare duas listagens de tamanhos diferentes.

## [2.14.0] — 2026-07-28 — Arquivar talento registra motivo, autor e data

### Adicionado
- Arquivar **escreve no mini-CRM** em vez de ganhar campo próprio: a `Anotacao`
  já tinha texto, anexo, autor snapshot e data. Desfazer é mudar o status de
  volta; o registro permanece porque a anotação é append-only.
- O lote **presta contas de quem não foi** — antes tinha `.catch(() => {})` e
  dizia que arquivou tudo.

### Corrigido
- `test_jornadas_confirmar_lote` só passava em banco limpo (`descricao` é
  `unique=True`). Teste que grava em tabela com campo único precisa gerar o valor
  por execução.

## [2.13.0] — 2026-07-28 — Confirmar em lote as jornadas que o parser leu por completo

### Adicionado
- Só as **completas** entram no lote; as demais continuam uma a uma.

## [2.12.0] — 2026-07-28 — Fila de duplicidades: 199 pares viraram 3

### Corrigido
- O RH pediu ação em massa nas duplicidades de jornada. **Medindo contra os
  dados reais, a fila tinha 199 pares e só 3 eram duplicata** — 80 eram o mesmo
  texto com horário diferente, 40 o mesmo horário com cliente diferente.
  Resolver "em massa" seria o merge cego que o módulo existe para impedir, e o
  estrago é invisível: a pessoa descobre no contracheque.
- Duas regras estruturais: **números diferentes ⇒ jornadas diferentes**;
  **mesmos números + letras diferentes ⇒ clientes diferentes**.
- Lição geral: quando o RH pede velocidade, conferir antes se a fila não está
  cheia de ruído — velocidade em fila errada multiplica erro.

## [2.11.0] — 2026-07-28 — Currículo em Word abria aba em branco

### Corrigido
- O log de abertura não dizia nada sobre o que falhou.

## [2.10.0] — 2026-07-28 — Ficha completa do talento

### Adicionado
- Painel na própria linha com tudo do cadastro, incluindo o `resumo` e a
  `origem` — que iam para o banco e ninguém via.

### Corrigido
- `.talento-form` perdia para `.cartao` por ordem de fonte e grudava o
  formulário na esquerda. No mobile passava despercebido.
- Sublinhado do menu (os itens viraram `<NavLink>` na v1.97) e chips
  sobrepostos.

## [2.09.0] — 2026-07-28 — Todos os e-mails do sistema viram texto editável

### Adicionado
- Migração completa dos e-mails externos para o catálogo.

## [2.08.0] — 2026-07-28 — Tela de Uniformes

### Adicionado
- O pedido era "um e-mail com todas as informações de uniforme"; a escolha foi o
  **contrário do pedido literal**, e combinada: nome, posto e medidas por e-mail
  é ficha de pessoal circulando em caixa que ninguém controla, e a cada 20
  admissões seriam 20 e-mails que o time para de ler. A lista fica na tela; o
  aviso diz só "fulano informou os tamanhos, veja em /rh/uniformes".
- Dispara no `concluir_envio`, **nunca no autosave** — o wizard salva a cada 900ms.

## [2.07.0] — 2026-07-28 — E-mails externos migram para os textos editáveis

## [2.06.0] — 2026-07-28 — Textos de e-mail editáveis pelo RH

### Adicionado
- Catálogo em `email_templates.py` como fonte da verdade; a tabela guarda só o
  que o RH escreveu por cima. Histórico append-only, preview, restaurar versão.
- **O template é apresentação, nunca decisão**: os e-mails que enumeram
  documentos recebem a lista pronta como `{{lista}}` — a regra do que entra
  continua no código.
- **Variável obrigatória valida no salvamento**: sem `{{codigo}}` num e-mail de
  acesso, a mensagem sai bonita e vazia e ninguém mais entra no sistema.
- **Fallback sempre**: sem registro, texto vazio ou erro de leitura vale o padrão
  — e-mail nenhum deixa de sair por edição ruim.

### Corrigido
- **Teste de e-mail não pode depender da redação**: o smoke extraía o OTP com
  `split("eletrônica é: ")`. Com o texto editável, uma edição no painel derrubaria
  o CI num commit sem relação nenhuma. Agora acha o código por padrão.

## [2.05.0] — 2026-07-28 — A opção de VT se confirma antes de assinar

### Corrigido
- A troca da opção existia só dentro do card, no meio da lista de documentos;
  quem não reparasse assinava errado — e o termo vira desconto de até 6% em
  folha, então o erro custa salário. A confirmação foi para logo acima de
  "Assinar os documentos", dizendo o efeito em dinheiro.

## [2.04.0] — 2026-07-28 — O candidato reabre o próprio envio

### Adicionado
- Depois do "CONCLUÍ MEU ENVIO" o checklist congelava e só o RH reabria — quem
  percebia na hora que mandou o arquivo errado ficava dependendo de socorro.
- Guarda: **qualquer** slot já revisado recusa com 409 — trocar arquivo já
  analisado faria a análise valer para um documento que não existe mais.

## [2.03.0] — 2026-07-28 — O acesso público para de morrer no app de e-mail

### Corrigido
- **Link de e-mail identifica, nunca autentica** (regra que rege `/creche` e
  `/meu`). O gate 2FA morria no webview: a pessoa abria o link, saía para ler o
  código — única forma — e voltava com a tela zerada. O backend guardava a sessão
  por 6h, mas o token vivia só em `useState`, e o front ainda apagava o `?t=`.
- Limpar o `?t=` da URL só **depois** de resolvê-lo — apagar antes era o que
  impedia o "voltar" de recuperar a tentativa.

## [2.02.0] — 2026-07-28 — O caminho de volta do candidato estava quebrado nas três pontas

### Corrigido
- **Todo e-mail que manda a pessoa voltar ao sistema leva o link junto**: os
  e-mails de rejeição diziam "acesse o mesmo link da sua admissão" e **não
  mandavam link nenhum**.
- **`catch` vazio anti-enumeração engolindo erro de infra**: `Entrar.jsx` mostrava
  "📬 Confira seu e-mail" **mesmo com HTTP 500** — sucesso mentiroso; a pessoa
  esperava um e-mail que nunca saiu. A resposta idêntica para CPF que existe e
  que não existe continua certa; 5xx tem que virar erro visível.
- Regra: **erro de negócio ≠ erro de infraestrutura**. Ao escrever `catch`
  silencioso, pergunte qual falha ele está escondendo.

---

## [2.01.0] — 2026-07-28 — Modelos de IA configuráveis e à prova de "`:free` sumiu"

Salvar a chave do OpenRouter mostrava "não respondeu ou recusou a chave"
mesmo com a chave correta.

### Corrigido
- **Modelo `:free` do OpenRouter é volátil.** `meta-llama/llama-3.3-70b-instruct:free`
  foi removido do catálogo do OpenRouter; chamar um modelo inexistente devolve
  404, que o painel exibia como "recusou a chave" — escondendo a causa real (a
  chave estava certa, o modelo é que sumiu).
- **Mensagem de erro do painel agora distingue os motivos.** "Recusou a chave"
  só aparece em 401/403; um 404 diz "modelo indisponível — confira os modelos" +
  dica da política de dados do OpenRouter. Baseado em `IndisponivelError.codigo`.

### Adicionado
- **Lista de modelos por provedor com fallback interno.** Cada provedor tenta
  seus modelos em ordem; se um falha (404, cota…), cai no próximo modelo do
  MESMO provedor antes de trocar de provedor. Só 401/403 pula o provedor inteiro.
  Padrões free novos, ambos com suporte a JSON (exigido pelo Match):
  `google/gemma-4-31b-it:free` → `openai/gpt-oss-20b:free`.
- **Modelos editáveis no painel** (Config → IA de texto): quando um id sumir de
  novo, o RH corrige em segundos, sem deploy. Chaves `openrouter_modelos`/
  `groq_modelos` na config dinâmica; vazio volta aos padrões do código.

## [2.00.0] — 2026-07-28 — Match de Vagas assíncrono e multi-provedor

Correção do incidente do mesmo dia: o RH ranqueou 131 talentos e só 18 foram
analisados; 67 segundos depois, na segunda tentativa, só 2. Plano completo e
diagnóstico em `docs/planejamento/10-match-vagas-assincrono.md`.

### Corrigido
- **Cota da IA derrubava a análise inteira.** Um HTTP 429 (limite de uso —
  transitório, resolve em segundos) era convertido no MESMO erro de um 401
  (chave inválida — permanente), e um `kill switch` irreversível pulava
  todos os talentos restantes. Agora `CotaExcedidaError` é distinto de
  `IndisponivelError`, o `Retry-After` do provedor é respeitado, e o worker
  espera e retoma em vez de desistir do lote.
- **Nada era persistido**: cada clique refazia as 131 análises e pagava tudo
  de novo — foi por isso que a 2ª rodada foi *pior* que a 1ª. Agora o
  resultado é gravado e reaproveitado; clicar de novo é praticamente grátis
  (botão "Reanalisar tudo" força quando você quiser).
- **Mensagem desonesta**: a tela dizia "IA indisponível", que o RH lia como
  "caiu, vou tentar de novo" — e o segundo clique piorava tudo. Agora diz
  que o limite de uso foi atingido e em quanto tempo tentar.
- **Currículo `.heic` (foto de iPhone) era 100% ilegível**: o upload aceitava,
  mas faltava `pillow-heif` e o erro era engolido. Também corrigido:
  currículo com `curriculo_nome` NULL (importados de planilha) caía em
  "formato desconhecido" mesmo com o arquivo certo no MinIO.
- **Todos os talentos ficavam "Novo" para sempre** — nada movia o status.
  Agora `novo → em_analise` quando o RH pratica um **ato de atenção**: abrir
  o currículo ou as anotações da pessoa. Deliberadamente **não** no
  ranqueamento em massa: marcar 131 de uma vez recriaria o mesmo problema
  com outro rótulo.

### Adicionado
- **Ranqueamento assíncrono** na fila Redis/RQ que já existia no ecossistema
  e estava ociosa desde a v1.83. O RH clica e continua usando o sistema; o
  worker processa devagar, esperando cota quando precisa. Resolve também o
  timeout de 60s do nginx, que 131 análises jamais respeitariam.
- **Cadeia de provedores de IA**: **OpenRouter principal → Groq reserva**. Se
  um falha ou estoura cota, o outro assume automaticamente.
- **Aba de Resultados** — prestação de contas, não barra de progresso. Cada
  pessoa aparece com o MOTIVO de estar onde está: analisado (com nota e
  justificativa), sem currículo, currículo ilegível (com o formato),
  aguardando IA, ou com alerta de trecho suspeito. Ninguém some em silêncio
  — mesma regra do lote de documento crítico.
- **Painel de leitura de currículos**: quantos talentos existem, quantos têm
  currículo, quantos foram lidos e quantos são ilegíveis. Se este número
  estiver baixo, o gargalo está aí e não na IA.
- **Texto do currículo extraído uma vez, no upload** (Mistral OCR com
  fallback local), guardado **já minimizado** (sem CPF/RG/telefone/e-mail/
  CEP) e reaproveitado em todos os ranqueamentos. Botão de backfill para os
  currículos que já estavam na base.
- **Dados do cadastro entram na análise** junto com o currículo (cargo,
  região, escolaridade, experiência informada) — pedido do Bruno.
- **Aviso interno por e-mail ao terminar**, pela matriz de eventos (evento
  novo `match_vagas_concluido`), nunca direto para o `smtp_from`.

### Técnico
- `app/models/match.py` (CurriculoTexto, ProcessamentoMatch, AnaliseTalento),
  migration `e6f7a8b9c0d1`; `app/services/fila.py` (primeiro uso real da fila
  RQ), `app/services/curriculo_indexacao.py`, `app/workers/match.py`.
- Testes novos: `test_ia_texto_cadeia.py` (7 cenários — 429 vs 401, fallback
  entre provedores, espera do worker, teste de chave no provedor certo) e
  `test_match_persistencia.py` (reaproveitamento sem chamar IA, `reanalisar`
  sem duplicar, cota sem sumir com ninguém, retomada). `test_match_vagas.py`
  reescrito para a arquitetura nova.
- Dois bugs pegos pelos próprios testes antes de ir ao ar: `reanalisar=True`
  violava a constraint `UNIQUE(vaga_id, talento_id)` ao reinserir em vez de
  atualizar; e a aba de Resultados ficava presa em "Carregando…" por um
  `useEffect` que se realimentava.

### Pergunta aberta
Quantos dos 131 talentos têm currículo anexado? O painel de leitura agora
responde isso na tela. Se forem poucos, o gargalo não é IA — é que quase
ninguém anexa currículo, e isso se resolve no formulário público.

## [1.99.0] — 2026-07-28 — Onda C2: Match de Vagas × Banco de Talentos

### Adicionado
- **Match de Vagas** (Recrutamento → 🧩 Match de Vagas): o RH cadastra a vaga
  (título, descrição, cargo, região, regime, salário, requisitos
  obrigatórios/desejáveis) e o sistema ranqueia os talentos do Banco de
  Talentos por aderência — filtro estruturado local primeiro (cargo/região,
  sem custo de IA), depois leitura do currículo pela IA (nota + justificativa
  em campos fixos). **A IA nunca decide sozinha**: ordena e explica; quem
  convoca é o RH. Resultado no DashPlanilha (ordenável, filtrável, com a
  justificativa no detalhe da linha).
- **Base legal LGPD verificada**: o termo do Banco de Talentos já autoriza
  "tratar os dados para fins de recrutamento" — cobre a triagem por IA
  (uso primário da finalidade, não secundário). Formulário público ganhou
  uma frase de transparência avisando que dados e currículo podem ser
  analisados por IA, com decisão final sempre do RH.
- **Minimização antes do envio à IA**: CPF, RG, telefone, e-mail e CEP são
  removidos do texto do currículo antes de qualquer chamada — nenhum desses
  ajuda a avaliar aderência a uma vaga.

### Segurança — currículo é entrada hostil
- Achado do próprio Bruno durante a revisão do roadmap (não estava no plano
  original): o currículo é upload público de gente desconhecida, e o texto
  extraído dele vai direto para dentro de um prompt de IA — é **entrada
  hostil**, não dado. Ataque real e documentado no mercado ("white text
  resume injection"): texto em fonte branca/corpo 1 no fim do currículo
  instruindo o modelo a dar nota máxima. É falha silenciosa (ranking
  adulterado parece idêntico a um legítimo) e questão de **justiça do
  processo seletivo** — quem sabe o truque passa na frente de quem não sabe.
- **5 camadas de defesa** (`services/anti_prompt_injection.py`), nenhuma
  sozinha resolve: delimitador aleatório por chamada, saída estruturada
  (JSON, nunca texto livre), teto de tamanho, detecção de padrão suspeito
  com **alerta visível ao RH** (nunca filtro em silêncio — mesmo princípio
  do lote de documento crítico), e texto invisível reportado como sinal.
  Currículo suspeito aparece marcado "⚠️ suspeito" no ranking, com o texto
  neutralizado antes de chegar à IA — nunca escondido do RH.
- Regra geral registrada no CLAUDE.md para todo texto de origem externa que
  chegar a um modelo daqui para frente: é dado, nunca instrução.

### Técnico
- `app/models/vaga.py`, `app/api/vagas.py`, migration `d5e6f7a8b9c0`.
- `app/services/curriculo_texto.py`: extração de texto (PDF via
  pypdf/Mistral OCR, imagem via Tesseract/Mistral OCR, DOC/DOCX via
  LibreOffice+PDF) + minimização de PII. Nunca inventa nota para currículo
  ilegível.
- `app/services/match_vagas.py`: orquestra filtro estruturado + análise por
  IA, usando `ia_texto.py` (Groq) e `anti_prompt_injection.py`.
- Testes novos: `test_anti_prompt_injection.py` (5 padrões de ataque
  detectados, 3 currículos limpos sem falso positivo, teto de tamanho,
  resistência a fechamento de delimitador) e `test_match_vagas.py` (prova
  que o prompt que chega à IA não contém o comando de ataque íntegro, mesmo
  com IA mockada "honesta" — a defesa está na preparação do texto, não no
  bom comportamento do modelo).
- Groq mantido nos dois módulos de IA (C1 e C2) — decisão consciente do
  Bruno, contra a recomendação inicial de provedor com retenção zero;
  minimização é a proteção que resta.
- Validado com Playwright contra ambiente efêmero: CRUD de vaga, ranking
  real (talento com cargo compatível sobe para o topo da lista), e teste
  end-to-end confirmando que o filtro estruturado funciona corretamente.

## [1.98.0] — 2026-07-28 — Onda C1: Minutário de Mensagens

### Adicionado
- **Minutário de Mensagens** (Recrutamento → 💬 Minutário de Mensagens):
  modelos de mensagem (CRUD) para WhatsApp/e-mail + composição assistida por
  IA (Groq). O RH preenche campos da VAGA (tom, cargo, regime, salário,
  local, escala, jornada, horário, requisitos obrigatórios/desejáveis,
  instruções, prazo) — **nenhum dado de candidato** entra na chamada à IA. O
  texto gerado sempre volta editável antes de qualquer envio: a IA propõe, o
  RH aprova. Envio por **copiar o texto** ou por um **link do WhatsApp**
  (`wa.me`) já com a mensagem pronta — sem integração com a API oficial do
  WhatsApp (decisão consciente: `wa.me` entrega o essencial sem o custo e a
  dependência de uma conta Business verificada).
  - Modelos reusam o catálogo de **tags** do mini-CRM para categorizar.
  - Groq configurável em Configurações → E-mail e integrações (mesmo padrão
    do OCR com Mistral: chave na config dinâmica, nunca devolvida, botão de
    teste de conexão).

### Técnico
- `app/services/ia_texto.py`: camada de geração de texto, provedor
  configurável (Groq por padrão) — usada também pelo Match de Vagas (C2).
  Trocar de provedor no futuro é mudar este arquivo só.
- `app/models/minutario.py`, migration `c4d5e6f7a8b9`.
- Bug pego pelo teste novo (`test_minutario_prompt.py`) e corrigido antes de
  ir ao ar: preencher **só** o campo Tom gerava um prompt sem nenhuma
  instrução de conteúdo (o fallback genérico só disparava quando também
  faltava o tom). Corrigido: o fallback dispara por falta de CONTEÚDO
  (campos da vaga ou modelo de referência), o tom é só estilo.
- Testado com Playwright contra ambiente efêmero: composição, erro amigável
  sem chave configurada, CRUD de modelo, e a tela de config do Groq.

## [1.97.0] — 2026-07-28 — Onda B: 16ª leva de feedbacks (3 itens)

### Adicionado
- **URL própria para cada tela do painel do RH** (react-router estava
  instalado mas nunca usado dentro de `/rh/*`): menu lateral agora usa
  `<NavLink>` (`/rh/colaboradores`, `/rh/config`…) e cada pessoa aberta ganha
  `/rh/candidato/<id>`. Isso resolve de graça o que o botão direito não
  oferecia — Ctrl+clique e "abrir em nova aba" funcionam porque o React
  Router intercepta só o clique simples. F5 na ficha de alguém mantém a
  mesma tela (antes sempre voltava para Admissões).
- **Modal (primeiro do projeto) para as anotações do mini-CRM**: o inline
  dentro da linha da tabela estava espremido (rolava na horizontal) — o
  sistema de design (`08-sistema-de-design.md`) foi revisado no *princípio*,
  não ganhou uma exceção: "editar perto do item" agora admite inline **ou**
  modal ancorado (quando há anexo + histórico + texto longo). O modal
  reaproveita o padrão de fechar do `SelectBusca` (clique fora, Escape),
  mostra o nome da pessoa no cabeçalho, e tem foco preso.
  - **Editar anotação** (antes só criar/excluir): `PATCH
    /rh/crm/anotacoes/{id}`. O autor original nunca é sobrescrito — grava-se
    o editor e a data à parte (`editado_por`/`editado_quando`).
- **Central de Importações** (Configurações → 📥 Importações): os 6 uploads
  de planilha do RH (Colaboradores, Postos, Jornadas ×2, Talentos, Ponto)
  saíram das telas de origem e agora vivem só aqui, com instruções e o que
  acontece com duplicados — nenhuma lógica de importação foi duplicada, só a
  UI foi centralizada. As telas de origem ganharam um link de cortesia. A
  Incidência de Benefícios (fluxo de 2 passos com decisões linha a linha) e a
  padronização de cargos/jornadas por texto colado continuam em tela própria
  — a central aponta para elas, não as reimplementa.

### Técnico
- `frontend/src/Modal.jsx`, `frontend/src/rh/Importacoes.jsx`.
- Migration `b3c4d5e6f7a8`: `crm_anotacao.editado_em`/`editor_nome`.
- Testado manualmente com Playwright contra ambiente efêmero: navegação por
  URL, F5 na ficha, modal (criar/editar/fechar por Escape e clique fora), e
  upload real de planilha de Postos pela central nova (118 postos criados).

## [1.96.0] — 2026-07-27 — Onda A: 16ª leva de feedbacks (3 itens)

Roadmap completo e revisão adversária (party-mode) em
`docs/planejamento/09-roadmap-feedbacks-16a-leva.md`. Ordem de execução
`A3 → A1 → A2` (torneira antes do balde: estanca a entrada de cargo digitado
livre antes de limpar o de-para em massa).

### Corrigido
- **Ficha do RH não salvava e não dizia o motivo** (bug silencioso): uma
  `ValidationError` do Pydantic era levantada FORA do ciclo de validação do
  FastAPI (o corpo da rota é um dict livre) e escapava como **HTTP 500 em
  texto puro** — o front não tinha detalhe algum para mostrar. Corrigido em
  6 frentes:
  - Handler global `@app.exception_handler(Exception)` em `main.py`: qualquer
    erro não tratado agora devolve `{"erro": "interno", "id": "<correlação>"}`
    — **nunca** o texto real da exceção (que pode conter o valor que estourou
    no banco, ex.: CPF).
  - `rh_ficha.py::editar_secao` captura a `ValidationError` e devolve 422 com
    `[{loc, msg, type}]`, e captura `DataError` do commit (coluna truncada:
    UF por extenso, CEP com hífen, tipo sanguíneo longo) nomeando o campo.
  - Normalização de entrada: UF vira 2 letras maiúsculas, CEP vira só dígitos,
    antes da validação — mesmo padrão que o CPF já tinha.
  - `api.js` para de descartar a lista estruturada de erros do Pydantic
    (`e.campos`), em vez de trocá-la pela string genérica `dados_invalidos`.
  - Mensagem de erro/sucesso passa a ser **local à seção** (`<details>`), não
    mais um banner ~19 blocos JSX acima do formulário e fora do viewport.
  - Corrigido também: sucesso não é mais mascarado como falha quando o
    recarregamento pós-salvamento falha (o `await carregar()` estava dentro
    do `try`).
  - Formulário ganhou os campos que faltavam para o RH destravar uma ficha
    presa na declaração final: sexo, identidade de gênero, cor/raça,
    nacionalidade, estado civil, escolaridade, PCD, logradouro/número/
    complemento separados. Datas viram `<InputData>` com máscara, enums e UF
    viram `<select>` — nunca mais texto livre para esses campos.

### Adicionado
- **Cargo do convite é lista com busca**, igual ao seletor já usado na ficha
  do colaborador — evita "Vigia"/"vigia"/"Vigía" virando cargos distintos.
  Só frontend; `cargo_funcao` continua string livre.
- **Padronização em massa de cargos e jornadas do Tirvu**: o RH cola o texto
  copiado da tela do Tirvu (Cargos ou Jornadas) em Configurações → Empresas e
  jornadas, o sistema PROPÕE o de-para (`CargoTirvu`/`Jornada.tirvu_id`) e o
  RH confirma linha a linha — nunca grava sozinho. Detecta e sinaliza (nunca
  funde): cópia parcial (contagem do cabeçalho não bate), cargos homônimos
  com 2+ IDs ativos no Tirvu, jornadas duplicadas após limpar a sujeira de
  "vínculos" colada na cópia. Ataca a causa raiz das pendências manuais do
  export em massa para o Tirvu.

### Técnico
- `app/services/importar_tirvu_txt.py`: parser puro (sem DB) do formato
  colado — testável isoladamente.
- Rotas `POST /rh/tirvu-txt/{preview,confirmar}-{cargos,jornadas}`.
- Testes novos: `test_editar_secao_rh.py` (os casos que viravam 500 mudo),
  `test_importar_tirvu_txt.py` (parser, validado contra os dados reais do
  RH), `test_importacao_massa_nao_regride_export.py` — exigido pela revisão
  adversária: gera o export do Tirvu antes/depois da importação em massa e
  garante que **só** a coluna Cargo muda, célula a célula.

## [1.92.0] — 2026-07-24 — Onda Admissão/Ficha (6 ajustes)

### Adicionado / Corrigido
- **Cargo obrigatório no link**: o convite passa a exigir o cargo/função (422
  `cargo_obrigatorio`) — o cargo casa por texto com modelos/provas/arquivo.
- **Informativo de integração só após o RH disparar**: o informativo (efetivo
  INFRAERO e intermitente) NASCE bloqueado e só vai ao candidato assinar quando
  o RH clicar "📨 Liberar" no painel (`aguardando_liberacao`). Enquanto isso,
  não aparece no fluxo de assinatura. Vale para os dois regimes.
- **Autodeclaração de residência**: quando o comprovante não está no nome do
  candidato, ele marca no wizard, informa o titular e a relação (pai/cônjuge/
  locador…) e assina uma autodeclaração — que só é exigida nesse caso.
- **Instrução do salário do intermitente**: no campo de salário (ficha), uma
  nota aparece só quando o regime é intermitente: informe o valor/dia = salário
  do cargo ÷ 30.
- **Vários documentos no mesmo tipo (insert manual do RH)**: ao inserir um
  documento manualmente, o RH pode selecionar vários arquivos de uma vez (ex.:
  RG frente+verso, ou os documentos certos no lugar dos errados) — viram um PDF
  combinado, como no envio do candidato.
- **Matrícula do Tirvu protegida**: reimportar do Tirvu com a coluna "matrícula"
  vazia não zera mais a matrícula existente (999NNNN ou a real) — só sobrescreve
  quando vem preenchida. Espelha a proteção que já havia para o nome.

### Técnico
- `assinatura.aguardando_liberacao`, `endereco.comprovante_titular`/
  `comprovante_relacao`, enum `documento_assinavel += autodeclaracao_residencia`.
  Migration `e6a8c0d2f4b1` (reversível). Gerador `gerar_autodeclaracao_residencia`.

## [1.91.0] — 2026-07-24 — Telemetria das provas visível no RH

### Corrigido/Melhorado
- **O relatório de comportamento das provas agora aparece.** A telemetria (troca
  de aba/app, tempo fora da tela, tentativas de print, copiar/colar, quedas de
  conexão) já era coletada durante a prova, mas só existia no banco — não era
  exibida (feedback do Bruno: "por que não aparecem os dados de telemetria?").
  Agora:
  - **No dash de aplicações**: coluna "Comportamento" com um selo (✓ limpo / ⚠️ N)
    e o detalhe no tooltip; ordenável pela quantidade de alertas.
  - **No detalhe da aplicação**: card "🖥️ Comportamento na tela" com o relatório
    completo (cada métrica, destacando as que têm ocorrência).
- É **indício**, não prova de fraude — o RH decide; nunca vira nota.

## [1.90.0] — 2026-07-24 — Banco de Itens (Provas Fase 2)

### Adicionado
- **Banco de Itens**: questões REUTILIZÁVEIS, catalogadas por **cargo**,
  **senioridade** (Júnior/Pleno/Sênior/Qualquer) e **tags** de conteúdo. A ideia
  é tornar a confecção de provas ESCALÁVEL — catalogar uma vez, montar provas
  rápido. Nova aba em Provas (🗃️ Banco de itens) com CRUD e filtros.
- **Montar prova a partir do banco** (na tela de edição da prova, "🗃️ Adicionar
  do banco"): dois modos — **escolher item a item** (com filtros) ou **sortear**
  N itens por cargo/senioridade/tag. Em ambos, o item é **copiado** para a prova
  (snapshot): editar ou excluir o item no banco depois **não altera** provas já
  montadas nem aplicações em andamento.
- **Promover questão → banco** ("→ banco" em cada questão da prova): reaproveita
  uma questão já escrita, copiando-a para o banco (a original permanece na prova).

### Preserva o que existe (pedido do Bruno)
- Migração **ADITIVA** (`item_banco`, nova tabela) — NÃO toca `prova_cargo` nem
  `questao_prova`. As provas existentes continuam idênticas, nada é desmontado.
- Migration `d4f6b8a0c2e1` (reversível). Senioridade é lista fixa (não texto
  livre, para filtrar sem "pleno"/"Pleno"/"PL"). Tags do item são próprias
  (conteúdo), separadas do catálogo de tags de PESSOAS do CRM.

## [1.89.0] — 2026-07-24 — Provas-avançado Fase 1: aleatorização, duplicar, explicação

### Adicionado
- **Aleatorização das provas** (interruptor por prova): embaralha a ordem das
  questões E das alternativas para cada participante, com semente ESTÁVEL por
  aplicação — recarregar a página não reembaralha (o candidato não se perde). A
  correção casa por id da opção, então embaralhar a exibição **nunca altera a
  nota** (testado). Prova didática com sequência proposital fica com o
  embaralhamento desligado.
- **Explicação da resposta** (campo opcional por questão) + **flag por prova**
  "mostrar ao participante". Ao terminar, se a prova permite, o participante vê
  uma revisão com o gabarito e a explicação de cada questão (didática). Prova de
  seleção fica com a flag desligada e a revisão é bloqueada (403) — o gabarito
  nunca vaza. A nota continua restrita ao RH em qualquer caso.
- **Duplicar prova inteira** e **duplicar questão**: clona título/config e todas
  as questões (com gabarito e explicação); a cópia da prova nasce como "(cópia)"
  sem links/aplicações. Botões na lista de provas e em cada questão.

### Técnico
- `prova_cargo.embaralhar`/`mostrar_explicacao`, `questao_prova.explicacao`,
  `aplicacao_prova.seed`. Migration `c3e5a7f9b1d2` (reversível, sem enum).
- Embaralhamento determinístico por seed (`_publicas_ordenadas`): sub-seed por
  questão para as opções não permutarem todas igual. Rotas novas:
  `/rh/provas/{id}/duplicar`, `/rh/provas/{id}/questoes/{qid}/duplicar`,
  `/p/{token}/a/{aid}/revisao`.
- **Banco de itens por cargo/senioridade fica para a Fase 2** (rearquitetura: a
  questão deixaria de pertencer a uma única prova).

## [1.88.0] — 2026-07-24 — Máscara de data centralizada + filtros compactos

### Corrigido (dado / risco)
- **Máscara de data `dd/mm/aaaa` em todo campo de data digitável.** O campo de
  nascimento da criança na creche (link público e wizard) era input LIVRE sem
  máscara — dava para salvar "20122025" cru como data (bug relatado: nascimento
  de filho de brigadista gravado errado). Agora todo campo de data usa o
  componente central `<InputData/>`, que insere as barras conforme digita e
  **valida que a data existe** (rejeita 31/02, ano absurdo, data incompleta),
  guardando ISO por baixo. As duas máscaras que existiam duplicadas e privadas
  (Wizard, Portal) foram unificadas nesse componente + helpers em `fmt.js`
  (`fmtDataBR`/`isoParaBR`/`brParaISO`), espelhando o padrão de CPF/telefone.

### Melhorado (UX)
- **Barra de filtros do RH compacta.** Antes cada filtro ocupava uma linha
  inteira; agora é uma GRADE (vários por linha, rótulo pequeno em cima),
  aproveitando o espaço sem virar bagunça. Como todas as listas do RH usam o
  DashPlanilha, a mudança vale para todas de uma vez (Jornadas, Colaboradores,
  Talentos, Provas, Creche, Desenvolvimento…).
- **Todo filtro de seleção agora tem busca-ao-digitar.** Os `<select>` nativos
  da barra viraram `SelectBusca` — começa a digitar e a lista filtra ("filtro é
  algo funcional"). Os de texto já filtravam ao digitar.

## [1.87.0] — 2026-07-24 — Mini-CRM: anotações e tags no ciclo de vida

### Adicionado
- **Anotações e tags que acompanham a pessoa** por todo o ciclo de vida
  (talento → candidato → efetivo → desligado). A memória é feita uma vez e
  "segue a pessoa" sem cópia: como o talento é preservado e ligado ao candidato
  por `candidato_id`, as consultas juntam os dois lados (OR em `services/crm.py`).
- **Anotações**: texto livre + AUTOR (quem lançou, snapshot do nome) + data/hora
  + anexo opcional (MinIO). Registro de comunicação interna do RH, visível a
  toda a equipe. Excluível.
- **Tags**: catálogo com CRUD (Configurações → 🏷️ Tags): nome + cor + ativa.
  Marcar/desmarcar na pessoa; filtro e coluna no dash do Banco de Talentos.
  Catálogo único evita "entrevistado"/"Entrevistado" virarem tags diferentes.
- **Onde aparece**: painel na própria linha do dash de Talentos (botão
  🗒️ Anotações) e seção recolhível na ficha do candidato/colaborador
  (`Detalhe.jsx`). Componente único reutilizável `MemoriaPessoa.jsx`.

### Técnico
- Tabelas `crm_tag`, `crm_pessoa_tag` (N:N, 2 FKs opcionais talento/candidato),
  `crm_anotacao`. Migration `b7c4d9e1f2a3` (reversível). Sem enum novo.
- Rotas `/rh/crm/...` (todas restritas ao RH). Tags carregadas em lote no dump
  de talentos (sem N+1). Autor via `requer_rh` (`rh.id`/`rh.nome`).

## [1.86.0] — 2026-07-23 — Sistema de design + padronização + bugs de provas

### Sistema de design (a dor nº1: "toda hora tenho que padronizar")
- **Documento de padronização e identidade**
  (`docs/planejamento/08-sistema-de-design.md`): o guia canônico de padrões —
  tokens (os `--esp-*`/`--fs-*` já existiam, faltava USÁ-los), primitivas de
  layout, dark mode, editar-na-linha, overflow, toggle, tooltips, checklist de
  tela nova. Tela nova nasce padronizada porque consome o sistema.
- **Primitiva de página `.pagina`**: os módulos novos (Desenvolvimento,
  Desempenho, Avaliações) renderizavam `<section>` cru sem padding lateral e
  ficavam "sem respiro". Agora usam `.pagina` (= `.rh-painel`), com respiro.
- **Dark mode — menu suspenso legível**: faltava `color-scheme` no tema; o
  dropdown nativo do `<select>` vinha claro sobre o app escuro (ilegível).
  Corrigido em `:root` e `:root[data-tema='escuro']`.
- **Editar abre PERTO do item**: em Desenvolvimento → Tipos, editar abria no
  topo; agora o formulário substitui o card sendo editado.
- **Histórico que recolhe e não estoura**: o "ver histórico de decisões" (Creche)
  virou toggle; a auditoria (Configurações) ganhou rolagem contida e quebra de
  texto — a coluna JSON não estoura mais a margem da tela.

### Provas — 3 correções
- **Questão discursiva**: o botão "＋ Questão discursiva" caía no formulário de
  objetiva (nascia sempre objetiva). Agora abre o formulário certo (só
  enunciado).
- **Pontuação no dash**: prova só-objetiva concluída mostrava a nota das
  objetivas mas a **nota final ficava "—"** (só era calculada ao corrigir
  discursivas). Agora a nota final é gravada na conclusão quando não há
  discursivas.
- **Timer no celular**: ao trocar de app, o contador "parava" (era o relógio
  visual congelando). Agora deriva de um instante-alvo absoluto e
  re-sincroniza com o servidor ao voltar o foco.

### Análise entregue
- **Central de Ajuda** (`docs/planejamento/09-central-de-ajuda-analise.md`):
  comparativo GitBook vs. Notion/Docusaurus/MkDocs/Document360/Confluence etc.,
  com custos atuais e recomendação para equipe de uma pessoa só.

## [1.85.0] — 2026-07-23 — Import de ponto + interruptor do atestado

### Adicionado
- **Import de ponto do Tirvu como CONTEXTO da avaliação** (RH → Fatos
  Observados → Importar ponto): upload do `.xlsx` de ponto eletrônico, agregado
  por pessoa/período (`ResumoPonto`) e mostrado ao lado do formulário de
  avaliação — **nunca como nota automática**. Decisão de projeto para evitar
  "atraso vira número, número vira nota, nota vira desligamento".
- **Interruptor da leitura de atestado de saúde** (Configurações → OCR com IA):
  liga/desliga pelo painel a leitura por IA do atestado, que é dado sensível.
  Desligado por padrão; só deve ser ligado após a Mistral aprovar o Zero Data
  Retention no plano Scale (a trava vive no código, `ocr_roteador`).

### Decisões de dados (evitam injustiça)
- **Registro incompleto ≠ falta**: `00:00` de horas COM marcação de entrada é
  esquecimento de bater a saída, não ausência. Nos dados reais de 1 mês são 28
  incompletos contra 1 falta — tratar tudo como o Tirvu apurou acusaria 28
  pessoas injustamente.
- **`Horas Trabalhadas` é a fonte de verdade**, não as batidas (há dia sem
  batida e com horas apuradas). Casamento por **matrícula** (não há CPF na
  planilha), normalizando zeros à esquerda. Geolocalização e foto do ponto
  **não** são lidas (desproporcional para avaliação — LGPD).

## [1.84.0] — 2026-07-23 — Onda C: Avaliação de Desempenho

Digitaliza a Cartilha do Avaliador (17/06/2026) que rodava no Microsoft Forms.

### Adicionado
- **Fatos Observados**: a liderança registra na hora o que o colaborador fez
  (bom ou ruim), com fato e impacto — antídoto do efeito de recência. **O
  colaborador vê os fatos sobre ele** (portal `/meu`), mas **nunca o autor**.
  Rodam sozinhos e alimentam o formulário depois.
- **Formulário da cartilha** (11 seções, 7 indicadores, 8 competências, 5
  recomendações) com os fatos do período ao lado. Máquina de estados que **não
  deixa pular o feedback presencial**: rascunho → preenchida → feedback dado →
  manifestada → homologada.
- **Manifestação do colaborador** (seção 9, direito de resposta) no portal, com
  prazo de 7 dias — sem prazo, bastaria homologar antes de a pessoa ler.
- **Avaliação 360**: vertical (liderança, identificada) e horizontal (pares,
  **anônima e agregada** — o avaliado nunca vê o colega; o radar suprime a média
  dos pares com menos de 2 respostas).
- **Radar** ("teia") em SVG + **timeline** das médias na ficha da pessoa.
- **Calibração**: o desvio do avaliador INFORMA o homologador ("dá em média 4,0;
  os demais dão 3,6 — mais generoso") **sem alterar nota**. Distribuição forçada
  foi vetada; normalização com N pequeno é ruído.
- **Ciclos** (4 por ano, datas configuráveis) para agrupar as avaliações.

## [1.83.0] — 2026-07-23 — Onda B: Portal do Colaborador + Desenvolvimento

### Adicionado
- **Portal do colaborador `/meu`**: UMA porta para tudo que é da pessoa —
  cursos, certificados, pendências, avaliações. Gate do creche extraído (CPF →
  2FA por e-mail; sem e-mail, KBA), agora amarrado ao colaborador. A home é a
  lista de pendências dela, não um menu.
- **Cadastro de Desenvolvimento**: cursos, certificações e reciclagens ao longo
  do vínculo. Tipo configurável com validade, criticidade e cargos aplicáveis;
  herança do prazo em três níveis (posto > cargo > tipo). Leitura por IA
  pré-preenche; a pessoa confere.
- **Brigadistas NÃO é módulo — é uma consulta**: certificação crítica vencendo,
  com aviso automático 90 dias antes (worker), dash de quem está pronto, e
  montagem do e-mail de matrícula à Multicursos (individual ou em grupo, com o
  dossiê de cada um em PDF único).
- **Fila de validação do RH** com aprovação em lote para o caso fácil —
  documento crítico nunca entra no lote, e o lote diz quem barrou.
- **IA roteada por sensibilidade**: documento de saúde (atestado) só é lido com
  o Zero Data Retention ligado; identidade e certificado seguem normalmente.

## [1.82.0] — 2026-07-22 — Onda A: ajustes de campo

### Adicionado
- **Matriz de notificações** (evento × destinatários): cada aviso do sistema
  tem sua própria lista de e-mails, com herança de um padrão global. Corrige o
  aviso de "candidato concluiu o envio" que ia para a caixa de login do RH.
- **Creche — link direto na devolução, sem 2FA**: o e-mail de devolução leva um
  link de uso único (7 dias) que abre só a tela de correção; o e-mail já é
  comprovado, então refazer o código era atrito que fazia a correção não voltar.
- **Cargo/função clicável** na ficha: escolhe da lista de cargos já usados
  (evita "Vigia"/"vigia"/"Vigía") ou digita um novo. Continua texto livre.
- **Registra Ponto** vira pendência do export Tirvu (em branco, o Tirvu aceita
  calado e o colaborador nasce sem a marcação).

## [1.81.0] — 2026-07-22
### Adicionado
- **Colaboradores mostra o que falta no cadastro**: completude dos importados do
  Tirvu, para o RH ver de relance quem precisa de dado antes de exportar de volta.

## [1.76.0–1.80.0] — 2026-07-21/22 — DashPlanilha vira o padrão das listas
### Mudado
- **Colaboradores, Admissões e Creche migraram para o `DashPlanilha`**:
  ordenação por qualquer coluna, filtro por coluna, seleção + ações em massa,
  colunas configuráveis e export CSV — com cards de métrica clicáveis que
  ativam filtros. Os filtros pesados (posto, busca, status) ficam fora do dash,
  no topo, alimentando os dados; o dash refina em memória por cima. Passou a ser
  o padrão de TODA lista nova do RH.
- **Creche — "mais filhos" sem virar 1:N** (v1.79): reabrir o benefício ativo
  para acrescentar criança, em vez de largar o `candidato_id unique` e mexer em
  assinatura/dossiê.
### Corrigido
- Cards de Admissões aparecem mesmo com a lista vazia (v1.80, consertou o CI).

## [1.73.0–1.77.0] — 2026-07-21 — Reembolso-Creche: Ondas A/B/C

### Adicionado
- **Comunicação de estado + saídas** do creche: toda decisão avisa o colaborador
  por e-mail; **devolver** (reabre a edição), **indeferir** (terminal),
  **"não faço jus"** (some da fila mas fica no relatório), **suspender/encerrar**,
  e **desligar o colaborador encerra o benefício ativo**.
- **KBA nativa**: o gate serve os importados do Tirvu (sem ficha) usando dados
  imutáveis do cadastro (nascimento + sobrenome), não as fichas de admissão.
- **Não-respondentes e histórico** no dash, para provar que o elegível foi
  consultado e não pediu.

## [1.70.0] — 2026-07-20 — Jornadas estruturadas
### Adicionado
- Submenu **Jornadas** com parser que PROPÕE a estrutura (escala, horários,
  turno, adicional noturno, intrajornada, cargo) a partir da descrição — o RH
  confirma, nunca auto-grava. Sinalizador de duplicidade que só AVISA pares
  suspeitos (nunca funde: há ~40 erros de digitação nos dados reais). A
  `descricao` continua canônica — é ela que vai ao Tirvu.

## [1.69.0] — 2026-07-20 — `status` é só fluxo; `situacao` é só vínculo

### Mudado
- Separados os dois campos que compartilhavam `ativo`/`desligado` e confundiam
  as telas. Agora: **`status`** é só a fase do funil (convidado → … → aprovado/
  importado); **`situacao`** é só o vínculo (nulo = admissão, ativo, desligado).

### Legado
- Os valores **`ativo` e `desligado` do enum `StatusCandidato` ficaram ÓRFÃOS**
  (não se escreve mais). Não são removidos porque o Postgres não apaga valor de
  enum sem recriar o tipo; o front (`status.js`) já os ignora. **Não usar em
  código novo, não fundir os campos.**

## [1.63.0] — 2026-07-21 — Admissões e Colaboradores não vazam mais

### Corrigido
- **Cada registro aparece numa tela só**: Admissões filtra `situacao IS NULL`,
  Colaboradores filtra `situacao IS NOT NULL` (antes o mesmo registro vazava nas
  duas). Escapes simétricos para os casos de fronteira.

## [1.51.0] — 2026-07-20 — Reembolso-Creche (módulo completo)
### Adicionado
- Módulo do Reembolso-Creche (IN SEGES/MGI 147/2026): elegibilidade por posto,
  link público sem enumeração de CPF + KBA, assinatura colaborador→RH pelo
  multi-signatário, RH vê os documentos de cada criança, datas centralizadas e
  importador da planilha de incidência de benefícios (assistido).

## [1.55.0–1.61.0] — 2026-07-20 — Talentos, provas e imports

### Adicionado
- **Banco de Talentos** repaginado (wizard de 3 passos + currículo opcional),
  com dash próprio, envio de teste avulso e importação da planilha do Microsoft
  Forms (idempotente).
- **Provas por cargo**: banco de provas configurável pelo RH (objetivas com
  correção automática + discursivas), aplicação pública `/p/{token}`, correção
  no dash. Gabarito nunca vai ao público.

## [1.48.0–1.50.0] — 2026-07-19 — E-mail M365/Gmail em produção
### Corrigido
- **Callback OAuth** (Microsoft 365 e Gmail) passou a usar `https` quando o
  proxy não envia `X-Forwarded-Proto`, e a respeitar o `CF-Visitor`/host público
  atrás do Cloudflare — sem isso o login OAuth quebrava em produção.
- Rota de diagnóstico `/api/diag/callback` e versão no `/health` para confirmar
  qual imagem está no ar.

## [1.47.0] — 2026-07-19

### Mudado
- **"Exportar p/ Tirvu" saiu de Admissões e foi para Colaboradores**: só se
  manda para o Tirvu quem já virou colaborador (foi efetivado) — quem ainda
  está preenchendo a ficha não tem vínculo a criar lá. A planilha traz apenas
  quem **veio da admissão**; os importados do próprio Tirvu ficam de fora
  (já existem lá e seriam ignorados por ele).

## [1.46.0] — 2026-07-19

### Adicionado
- **Exportação de admissões para o Tirvu** — planilha no layout oficial de
  importação (28 colunas em ordem fixa), individual (botão na ficha) e em massa
  (respeitando os filtros da tela). Pré-checagem antes do download:
  o Tirvu recusa linha sem CTPS/PIS, e o RH fica sabendo aqui, não lá. Toda
  exportação é auditada (quem baixou, quantas linhas, quais postos).
- **CTPS Digital calculada** — número = o próprio CPF (11 dígitos), série =
  0000 (padrão eSocial). Preenchida sozinha quando o candidato informa o CPF;
  aparece na ficha cadastral só para os novos (quem já assinou não é afetado).
- **Empresas e Jornadas** como cadastros próprios (Configurações → Empresas e
  jornadas): o RH escolhe ou cria na hora, na ficha do colaborador. Jornadas
  importáveis da planilha de escalas do Tirvu (96 abas = 96 postos; as
  descrições do posto escolhido aparecem primeiro no seletor). "Registra ponto"
  por colaborador.
- **Endereço separado** (logradouro / número / complemento) na coleta nova,
  como o Tirvu pede. Endereços antigos migram por **backfill assistido**: o
  sistema propõe a separação e o RH confirma — nada muda sozinho.
- **Laudo PCD na ficha** — CID, tipo de deficiência, data do laudo e
  médico/CRM (Lei 8.213/91), coletados no formulário de quem se declara PCD.
- **Dependentes em bloco rotulado** na ficha cadastral (antes uma linha só).

### Corrigido
- Observação da CTPS na ficha dizia "7 primeiros dígitos + 4 últimos" —
  contradizia o padrão eSocial usado; corrigida.
- Planilhas enviadas ao RH (colaboradores, postos, jornadas) agora descartam o
  arquivo temporário do servidor imediatamente após o processamento.

## [1.44.0] — 2026-07-19

### Adicionado
- **Identidade visual configurável** (Configurações → Identidade visual): nome,
  razão social, CNPJ, endereço, contato, **logo e favicon** editáveis pelo
  painel. Aparecem nos PDFs, e-mails e no painel; os dados da Green House viram
  só o valor-padrão inicial. Desvincula o sistema de uma empresa específica.
- **Central de assinaturas** como menu próprio, com abas: documentos dos
  candidatos (dashboard de **todas** as assinaturas sem entrar em cada admissão),
  aguardando minha assinatura, já assinei, gerenciar roteiros, e papéis/
  assinantes/ordem.
- **Ordem das fichas de assinatura configurável** pelo RH (antes fixa no código).

### Mudado
- **Menu lateral reorganizado** por seções (Admissão, Documentos, Avaliação,
  Benefícios, Recrutamento, Sistema), sempre expandido e rolável — removida a
  versão hover/recolher que bugava. **Modelos** e **Assinaturas** saíram de
  Configurações e viraram menus próprios. Botão "Novo candidato" movido para a
  página de Admissões.

## [1.42.0 – 1.43.0] — 2026-07-19

### Adicionado
- **Multi-signatário**: um documento pode exigir a assinatura de vários em
  **ordem de papéis** — colaborador (link mágico), usuário do RH (assina logado,
  com senha) e/ou externo (link próprio + código, token de uso único e PDF só
  após 2FA). O PDF final consolida todas as assinaturas, com um manifesto
  multi-assinante e QR por etapa. Verificação pública por etapa.
- **Assinatura da equipe por autorização prévia registrada** (nunca carimbo
  falso): o representante confirma uma vez por código; sua assinatura passa a
  constar nos documentos daquele modelo, com validade e revogação.
- **Roteiro-padrão** de papéis por modelo; worker de **expiração** de roteiros
  vencidos + higienização LGPD de dados de externos não assinados.

## [1.38.0 – 1.41.0] — 2026-07-18/19

### Adicionado
- **Menu Arquivo**: inventário com filtros, download individual e **backup em
  lote** (ZIP por posto/pessoa + planilha XLSX), auditado com a lista de quem
  foi exportado.
- **Links de testagem avulsa** (`/t/{token}`): a pessoa entra só com o nome e vê
  o próprio resultado; **dashboard unificado de testes** (admissão + testagem)
  com reset e relatório de comportamento.
- **Modelos de documento completos**: opções por modelo (enviar por e-mail,
  exigir assinatura, papel do signatário), envio pontual para qualquer pessoa,
  predefinições (Ofício, Comunicado, Contrato, Declaração), papéis de assinatura.
- Testes do candidato editáveis após o convite; tooltip com o significado de
  cada palavra do DISC.

### Mudado
- Configurações reorganizada em submenus; UX desktop em cards (grade de 2
  colunas).

### Corrigido / Segurança
- **Rate limiting** em login (por IP e por conta), 2FA dos testes e da creche,
  recuperação de senha e solicitação de código de assinatura.
- **CPF sem máscara** nas telas internas do RH (máscara mantida no verificador
  público, nos logs e no envio à IA).
- **Trava anti-duplo-clique**: idempotência no servidor (dossiê, notificar,
  efetivar) — o 2º clique concorrente recebe 409; overlay de "processando" no
  cliente com atraso de 400 ms.

## [1.22.0 – 1.37.0] — 2026-07-17/18

### Adicionado
- **Reembolso-Creche** (IN SEGES/MGI 147/2026): adesão na admissão + link
  público de levantamento com 2FA e dossiê.
- **Base colaborador-cêntrica**: importação idempotente do Tirvu (.xlsx),
  colaboradores/postos, efetivar/desligar/transferir.
- **Testes DISC e situacional** na admissão, com telemetria de comportamento.
- **Lixeira universal** com restauração e retenção configurável.
- **Modelos de documento** no papel timbrado com variáveis; kit da Presidência;
  ficha do intermitente; campos de CNH/militar/dependentes.

### Corrigido
- Diversos feedbacks de campo: PDFs sem estouro de linha, DISC orientado, ficha
  completa, sincronização de nomes do Tirvu.

## [1.16.0] — 2026-07-17

### Adicionado
- **Notificações no Microsoft Teams**: em Configurações, o RH cola a URL de um
  Incoming Webhook (ou fluxo do Power Automate que posta no Teams) e escreve um
  **template** com variáveis (`{{nome}}`, `{{cargo}}`, `{{posto}}`,
  `{{status}}`…). Na tela do colaborador, o botão **Enviar ao Teams** posta a
  mensagem preenchida no canal. Sem OAuth — mesmo espírito do webhook de e-mail.

### Corrigido
- Cadastro público do Banco de Talentos falhava quando o e-mail era deixado em
  branco (o `EmailStr` recusava string vazia); agora vazio vira "sem e-mail".

## [1.15.0] — 2026-07-17

### Adicionado
- **Banco de Talentos**: formulário **público** (`/banco-de-talentos`, também
  linkado no portal) onde interessados deixam nome, contato, cargo pretendido,
  cidade, escolaridade e uma apresentação — protegido por honeypot anti-spam.
  No painel, uma aba **Banco de Talentos** lista os cadastros com filtros
  (status, cargo, busca livre), triagem de status e o botão **Converter em
  candidato**, que cria o cadastro migrando os dados já preenchidos, dispara o
  link de admissão e abre a ficha do novo candidato.

## [1.14.0] — 2026-07-17

### Adicionado
- **Módulo de criação de documentos (CRUD)**: o RH cria/edita documentos do
  zero em Configurações, já no papel timbrado padrão, com **variáveis
  dinâmicas** (`{{nome}}`, `{{cpf}}`, `{{cargo}}`, `{{posto}}`, `{{salario}}`,
  `{{data}}`…). Cada modelo pode ser vinculado a **qualquer colaborador**, a um
  **cargo** ou a um **posto**; na tela do colaborador aparecem os modelos
  aplicáveis com um botão **Gerar** (PDF preenchido no timbrado). Prévia
  disponível com os placeholders visíveis.
- **Todo PDF enviado vai para o papel timbrado A4** (decisão do RH): cada
  página do original é reduzida proporcionalmente e centralizada no corpo da
  página timbrada, sem distorcer. A leitura de texto (OCR e data do
  comprovante) passou a usar sempre o PDF original.

### Alterado
- Raiz do sistema virou um **portal com três portas** (Sou Candidato / Sou RH /
  Verificar documento) e há uma **entrada pública de verificação** (`/verificar`)
  onde se digita o código do registro.

## [1.12.0] — 2026-07-17

### Adicionado
- **Cargo, salário base e adicionais na ficha de cadastro**: o RH digita o
  salário à mão (texto livre) e adiciona quantos adicionais quiser (nome +
  valor em R$ ou %) na tela do posto; tudo passa a constar automaticamente na
  Ficha Cadastral do Colaborador. Alterar cargo/salário/adicionais de uma
  ficha já assinada a reabre para o colaborador assinar a versão atualizada
  (invalidação historizada, nunca deleção).
- **Colaborador troca a opção pelo Vale-Transporte** direto na tela de
  assinatura, enquanto o Termo de VT não foi assinado; depois de assinado, a
  troca é bloqueada (exigiria nova assinatura).

### Alterado
- **Marca d'água "GREENHOUSE"** (arte oficial que existia mas não era usada)
  agora aparece esmaecida na borda direita de todos os PDFs timbrados: fichas,
  ofícios, manifesto e páginas geradas a partir de fotos recebidas.

### Infraestrutura
- Os dois workflows de CI viraram um só (`ci.yml`, jobs `imagens` +
  `testes-de-interface`): cada commit aparece uma vez na lista de Actions.

## [1.10.0] — 2026-07-17

### Adicionado
- **Envio de e-mail via Power Automate (webhook)** como caminho "plug and play"
  para locatários do Microsoft 365 em que o admin bloqueia SMTP autenticado e
  registro de aplicativo: o RH cola a URL de um fluxo HTTP e o sistema manda o
  e-mail em JSON (com anexos em base64) para ele. Entra na cadeia de envio como
  Microsoft 365 → Google → **Power Automate** → SMTP, com card próprio no painel
  (passo a passo do fluxo e teste de envio). O envio OAuth direto via Microsoft
  Graph já existia e continua sendo a opção recomendada.

## [1.9.0] — 2026-07-17

### Adicionado
- **Frente e verso à prova de falhas**: nos documentos de duas partes (RG,
  reservista, CNH) o envio é passo a passo, um arquivo por vez — o seletor perde
  a seleção múltipla, acabando com o erro de quem tentava mandar os dois juntos.
- **Editor de imagem** (sem bibliotecas externas, para não pesar no aparelho de
  quem tem pouca internet): recorte com folga de segurança de 18% além da
  moldura já usada para alinhar, cantos arrastáveis (mouse e toque) e rotação de
  90° para a foto que saiu deitada. Vale para a foto tirada e para a imagem
  enviada do aparelho. Botão "Voltar" claro na câmera e no editor.

## [1.8.0] — 2026-07-17

### Corrigido
- **PDF não abria no Chrome do Android** (fundo escuro com um botão "Abrir" sem
  ação): o RH passa a ver os documentos por um visualizador em canvas (pdf.js)
  **apenas no celular** — no desktop segue o visualizador nativo do navegador.
- **Erros de upload** deixavam de virar um "sem conexão" genérico: queda real de
  rede, arquivo grande demais (413), formato inválido e erro de validação agora
  têm mensagens próprias e específicas.
- **Cabeçalho timbrado** dos documentos: arte alinhada à direita e título do
  documento centralizado.

## [1.7.0] — 2026-07-16

### Adicionado
- **Acordo de Confidencialidade** como quarta ficha de todo candidato,
  **retroativo**: quem ainda não assinou (mesmo já aprovado) passa a dever a
  assinatura automaticamente — o link de sempre abre direto na tela de
  assinar, e o dossiê passa a incluí-lo. Texto do modelo oficial com
  qualificação puxada dinamicamente da ficha (nome, CPF, nome social, função),
  endereço da sede unificado com o do rodapé, formatação uniforme no papel
  timbrado e gramática revisada (concordâncias, vírgulas, "resultará").

### Alterado
- OCR com IA (Mistral) passou a ser o **primeiro** degrau da leitura para
  qualquer arquivo (antes: só quando o PDF não tinha camada de texto);
  fallback: camada de texto do PDF → Tesseract local.

### Corrigido
- Busca no relatório de colaboradores quebrava (erro 500) quando havia
  candidato sem e-mail — efeito colateral do convite sem e-mail da 1.3.

## [1.6.0] — 2026-07-15

### Adicionado
- **Papel timbrado da empresa em todos os PDFs**: fichas, ofícios e manifesto
  usam as artes oficiais (cabeçalho de canto + rodapé institucional extraídos
  do modelo Word); fotos de documentos recebidos (RG, CPF…) viram página A4
  timbrada com o nome do documento e a data de recebimento. PDFs emitidos por
  órgãos (CTPS, certidões) seguem intactos — não se altera documento de
  terceiro. Vias já assinadas não mudam (hash preservado).
- **OCR com IA (Mistral)**: chave configurável pelo painel (com teste de
  leitura), cadeia de qualidade camada de texto do PDF → Mistral OCR →
  Tesseract local; falha de qualquer degrau cai para o seguinte em silêncio.
  Telemetria registra apenas tipo, hash e tamanho — nunca o conteúdo; a chave
  não aparece em logs; o aviso de privacidade do candidato passou a mencionar
  a leitura assistida por IA. PDFs escaneados (sem camada de texto) agora
  também são lidos quando a IA está ativa.

## [1.5.0] — 2026-07-15

### Adicionado
- **Fichas e assinaturas visíveis no painel**: o detalhe do candidato mostra
  cada documento exigido com o estado (assinado/aguardando), alerta quando o
  formulário está incompleto (fichas sairiam vazias) e ganhou o botão
  **"Notificar pendências por e-mail"** — cobrança com a lista exata do que
  falta e link novo. Nasceu de incidente real: e-mail cadastrado depois, e a
  pessoa nunca soube que havia fichas para preencher e assinar.
- **Termo de Consentimento LGPD (credenciamento)** no kit INFRAERO: gerado e
  assinado junto com os demais documentos do posto, com o mesmo código único.
- Painel do RH com **sidebar esquerda retrátil**, **barra de atividade** e
  botões travados durante requisições (fim do clique repetido); frases de
  espera agora também no painel.
- **Flash (torch)** na câmera guiada, quando o aparelho suporta.
- Foto OU arquivo para **todos** os documentos (fim do atalho que mandava
  CTPS/PIS direto ao seletor).
- Responsividade do painel para celular e tablet (tabelas com rolagem
  própria, revisão empilhada, métricas em grade).
- README rico (dores → soluções, rollback, resumo em inglês), CHANGELOG
  completo e LICENSE MIT.

### Alterado
- Salvar e-mail no contato avisa explicitamente que **não** envia nada
  sozinho — a notificação é um ato separado e auditado.

## [1.4.0] — 2026-07-15

Três fases nascidas de 11 anotações de uso real em produção, priorizadas em
mesa-redonda com foco em auditoria, LGPD e integridade das assinaturas.

### Adicionado
- **Fase 1 — controle do candidato:** ver o próprio envio (PDF), excluir envio
  ainda não aprovado e reenviar; preview de conferência da foto antes do envio;
  aviso de ciência do cartão de mobilidade (GO) com carimbo de data imutável;
  contrato do posto exibido a partir do cadastro (nada digitado à mão).
- **Fase 2 — poderes manuais do RH:** inserção de documento recebido fora do
  sistema (WhatsApp/e-mail/presencial) com etiqueta de origem; reabertura de
  status com motivo obrigatório; correção de dados da ficha por seção com
  auditoria campo a campo (antes → depois) e **re-assinatura granular** — só os
  documentos onde o dado aparece são invalidados e voltam para o candidato.
- **Fase 3 — frente e verso:** envio multi-arquivo vira um único PDF por
  documento; câmera guiada captura frente e verso em sequência (com passo
  opcional); OCR lê o texto combinado das partes.
- Assinaturas invalidadas são historizadas (nunca apagadas): o verificador
  público responde "assinatura substituída" com data e hash da via antiga; cada
  via assinada tem arquivo próprio no storage.
- E-mail/celular do candidato editáveis pelo RH e pelo próprio candidato, com
  trilha antes → depois na auditoria.
- Painel do RH com **sidebar esquerda retrátil**, barra de atividade global e
  botões travados durante requisições (fim do clique repetido).
- Captura por **foto OU arquivo para todos os documentos** (inclusive CTPS/PIS
  digitais — há quem tenha o cartão físico na mão).

### Alterado
- Comprovante de escolaridade passou a ser opcional.
- Câmera guiada sem disparo automático: o botão habilita quando o quadro está
  bom, mas quem fotografa é a pessoa; medidas de luz/foco restritas à moldura,
  com detecção de presença do documento.
- Exclusão/rejeição/substituição de arquivo varre todos os arquivos do slot
  (frente, verso, PDF) — cada um com hash SHA-256 na auditoria antes de sair.

### Corrigido
- Câmera dizia "tudo certo" com o documento fora do enquadramento (as medidas
  eram da cena inteira, não da moldura).

## [1.3.0] — 2026-07-15

### Adicionado
- Convite sem e-mail (só o nome é obrigatório): link em destaque para copiar e
  mandar pelo WhatsApp; e-mail vira pendência da ficha (o código de assinatura
  chega por ele).
- Leitor de identidade aceita **RG ou CNH**: detecta qual é, guarda no slot
  certo e avisa com gentileza quando a CNH veio no lugar do RG.
- OCR estendido: CNH (registro/categoria), título de eleitor (número/zona/
  seção), documento de CPF e CEP de comprovante de endereço; sugestões
  aplicadas **só com consentimento explícito** e nunca sobre campos preenchidos.
- Recusa imediata de documento de CPF com número divergente da ficha.
- **Câmera guiada** com moldura por tipo de documento, dicas em tempo real de
  luz/foco/enquadramento e conferência da foto; leitores junto aos campos que
  preenchem (RG/CNH na etapa de dados, comprovante na etapa de endereço, com
  moldura focada no cabeçalho da conta).
- Olhinho (mostrar/ocultar) em todos os campos de senha e segredos.
- Tema claro/escuro seguindo o dispositivo, com troca manual.
- Testes Playwright no CI contra a stack completa, incluindo a câmera (fake
  device do Chromium).

## [1.2.0] — 2026-07-14/15

### Adicionado
- Validações inteligentes no upload: foto tremida/borrada recusada na hora
  (variância do Laplaciano) e comprovante de endereço com mais de 90 dias
  bloqueado com mensagem clara.
- **Manifesto de assinatura** gravado como última página de cada PDF assinado:
  hash SHA-256, ID do registro, assinante, datas (Brasília + UTC), IP real,
  dispositivo, método e modalidade legal — com QR code para o **verificador
  público** (`/verificar/<id>`), que exibe dados minimizados (LGPD).
- Portal único de retorno **/entrar**: CPF + 2 perguntas de verificação
  derivadas da própria ficha (estilo TSE), com anti-enumeração, lockout e
  fallback de link por e-mail.
- Relatório de colaboradores com filtros e exportação **Excel** (~49 colunas).
- **Postos de serviço** com documentos específicos por contrato (ex.: ofícios
  INFRAERO) gerados em PDF fiel ao layout oficial e assinados na plataforma;
  assinantes dos documentos editáveis pelo painel.
- Nome social (Decreto 8.727/2016) e filiação (pai omitível) na ficha e nos
  documentos.
- Repaginada visual "fintech": fonte própria, cores vibrantes, micro-animações
  (com respeito a `prefers-reduced-motion`); máscara de datas `dd/mm/aaaa`
  digitável (o público trava no date picker).
- Botão "copiar link" por candidato no painel (para WhatsApp, sem reenviar
  e-mail).

## [1.1.0] — 2026-07-14

Primeira versão em produção (VPS via Portainer) + melhorias da v1.1.

### Adicionado
- Validação de CPF com dígito verificador (algoritmo da Receita) no backend e no
  formulário (aviso imediato + máscara), para titular e dependentes.
- Dashboard de métricas no painel do RH: candidatos, em andamento, documentos
  aguardando revisão, reenvios pendentes, dossiês gerados e tempo médio até o dossiê.
- "Esqueci minha senha" na tela de login: link por e-mail válido por 30 minutos e de
  uso único.
- Gestão da equipe do RH pelo painel: criar usuários (com e-mail de boas-vindas),
  editar, redefinir senha e ativar/desativar (com proteções contra auto-bloqueio).
- Envio de e-mail com "Fazer login com o Google" (OAuth + Gmail API), além do
  Microsoft 365; prioridade M365 → Google → SMTP.
- Teste de SMTP com diagnóstico dirigido (mostra a resposta exata do servidor e o
  passo de correção para os casos comuns do Microsoft 365).

### Corrigido
- Página em branco ao abrir um candidato no painel (hook condicional no React).
- Aprovar/rejeitar em massa não funcionavam (ordem de rotas no FastAPI); erros das
  ações em massa agora sempre aparecem na tela.
- Links gerados (link mágico, reset, e-mails, callback OAuth) agora derivam do endereço
  público da própria requisição — funcionam em localhost, IP:porta e domínio sem
  configurar BASE_URL; nginx preserva a porta.

## [1.0.0-rc.1] — 2026-07-14

Primeira versão candidata do Portal de Admissão.

### Adicionado
- Portal do candidato (mobile-first, sem senha): link mágico, aceite LGPD, wizard de 6
  etapas com autosave por campo, ViaCEP, dependentes ilimitados, tour guiado e tooltips
  com dicas por documento.
- Assinatura eletrônica simples (Lei 14.063/2020): código único por e-mail assina as 3
  fichas de uma vez; vias assinadas enviadas em anexo; trilha de evidências (hash, IP,
  user-agent, instante).
- Fichas Cadastral, de Emergência e Termo de VT geradas em PDF fiéis aos templates
  oficiais (textos legais, declarações, identificador de resposta).
- Checklist de documentos com regras condicionais (reservista, PCD, casamento,
  dependentes por idade, cartão VT), upload com normalização foto/Word→PDF e feedback
  imediato; botão "Concluí meu envio".
- Painel do RH: convites, revisão com visualizador de PDF, aprovação/rejeição individual
  e em massa (e-mail agrupado), dossiê único em A4 padronizado na ordem oficial (com opção
  de dossiê parcial), configurações (perfil, senha, SMTP com teste, Microsoft 365 via
  OAuth/Graph), auditoria.
- Infra: PostgreSQL + migrations Alembic automáticas no start (atualização sem perda de
  dados), MinIO com expurgo LGPD diário, Redis/RQ, e-mails HTML modernos, telemetria de
  requisições e trilha de auditoria.
- Deploy: compose base+variantes (ip / traefik / certbot), stack única para Portainer com
  imagens do GHCR publicadas por CI (GitHub Actions).

[1.7.0]: https://github.com/fontesmidias/admissao/releases/tag/v1.7.0
[1.6.0]: https://github.com/fontesmidias/admissao/releases/tag/v1.6.0
[1.5.0]: https://github.com/fontesmidias/admissao/releases/tag/v1.5.0
[1.4.0]: https://github.com/fontesmidias/admissao/releases/tag/v1.4.0
[1.3.0]: https://github.com/fontesmidias/admissao/releases/tag/v1.3.0
[1.2.0]: https://github.com/fontesmidias/admissao/releases/tag/v1.2.0
[1.1.0]: https://github.com/fontesmidias/admissao/releases/tag/v1.1.0
[1.0.0-rc.1]: https://github.com/fontesmidias/admissao/releases/tag/v1.0.0-rc.1
