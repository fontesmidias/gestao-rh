# 23ª leva de feedbacks — 2026-08-18

Treze feedbacks do Bruno num dia, a maioria sobre **Reembolso-Creche** (IN
SEGES/MGI nº 147/2026). Este documento registra o **levantamento factual** do
código, o que foi **decidido**, o que está **pendente de decisão do Bruno** e o
que ficou **desenhado mas não executado** — para que nada dependa da memória de
quem estava na conversa.

> Método: levantamento no código ANTES de discutir (a regra da casa é *"procure
> o que já existe antes de construir"* — v2.94), depois avaliação adversária em
> party mode. O feedback descreve o SINTOMA; várias vezes nesta leva a causa
> apurada foi outra.

---

## Achado que reenquadra metade da leva

**O e-mail de ativação do creche PROMETE entrega mensal de nota fiscal ou
declaração — e o sistema não tem onde recebê-la.**

`email_templates.py:235` manda o colaborador enviar *"NOTA FISCAL da
creche/pré-escola"* todo mês. Levantado no código:

- O creche tem **21 rotas POST**. Nenhuma recebe comprovante mensal.
- O único upload é `criancas/{id}/documento`, que recusa qualquer coisa que não
  seja certidão ou guarda (`tipo not in ("certidao","guarda")` → 422).
- Não existe tabela de competência, mês de referência ou data de corte.
- Não existe worker de creche — `ls backend/app/workers/` não tem nenhum.
- `dia_entrega_mensal` existe, é editável individualmente e em massa… e **é dado
  morto**: só preenche uma variável do e-mail de ativação, enviado UMA vez.
  A função que o envia chama-se `_email_orientacoes_mensais`, nome que engana.

É a armadilha da v2.74 (*"promessa na tela sem rota atrás"*) na maior escala já
vista no projeto: o colaborador foi instruído por e-mail a fazer algo todo mês,
e não há porta. Isso vale para o benefício que entra em folha.

---

## O que JÁ EXISTE (não construir de novo)

| Item | Onde | Situação |
|---|---|---|
| `tipo_comprovante` (declaracao \| nota_fiscal) | `models/beneficio.py:107` | Campo existe, é coletado em `CrecheLink.jsx:359` e devolvido pela API — **nenhuma tela do RH mostra e nada muda por causa dele**. Semi-órfão. |
| `dia_entrega_mensal` | `models/beneficio.py:80` | Editável individual (`creche.py:1111`) e em massa (`creche.py:1090`). Sem consumidor real. |
| Elegibilidade por posto | `PostoServico.da_direito_creche` | Existe, com valor do reembolso. |
| Coleta de creche NA ADMISSÃO | `Wizard.jsx:843` `BlocoCreche` | **Já existe**: aparece quando o posto dá direito, coleta criança + certidão + guarda. O feedback 11 é menor do que parece. |
| Decisão por criança | v2.55 | Com motivo e auditoria. |
| CRUD de jornada (backend) | `organizacao.py:241/264/364` + `api.js:472` | **A rota de criar existe e a tela nunca a chama.** Falta só o botão. |
| Nome de arquivo padronizado | `services/dossie.py:87` | `nome_arquivo_dossie()` já produz `DOCS ADM - KATIA POLIANE` — caixa alta, ASCII — **criada em 2026-08-12 a pedido do Bruno**. O feedback 12 é a CONTINUAÇÃO desse pedido. |

---

## O que NÃO existe (as lacunas reais)

1. **Entrega mensal** — nenhuma estrutura (ver acima).
2. **Lembrete** — nenhum worker; nunca existiu.
3. **Upload pelo RH no creche** — `api/creche.py` não importa `UploadFile`. O RH
   é somente-leitura sobre documentos; a única correção é **devolver** o
   levantamento ao colaborador e esperar. Na admissão o RH insere; aqui não.
4. **Um arquivo por tipo** — a key é fixa (`creche/{ben}/{crianca}/{tipo}.pdf`)
   e reenviar **sobrescreve**. Não há multi-partes como o
   `_gravar_partes_no_slot` da admissão. Por isso o RH "não consegue ver se há
   mais de uma folha": **não há**.
5. **Termo de guarda não é exigido** — `enviar` (`creche_publico.py:736`) só
   cobra `certidao_key`. Quem declara `parentesco=guarda` fecha o levantamento
   sem o termo.
6. **Matrícula ausente** — não está no requerimento PDF (`creche_pdf.py`, zero
   ocorrências), nem nas colunas da tela de Creche, nem em Admissões.
7. **Dedup no cadastro público de talentos** — não existe. A mesma pessoa
   preenchendo duas vezes cria dois registros. A dedup só existe na rota do RH
   (`talentos.py:448`, avisa com 409 e não funde) e na importação.
   `Talento` não tem CPF.

---

## Diagnóstico divergente do relato — feedback nº 1 (assinatura)

O relato é *"na etapa de assinar ela vê os dados mas não consegue editar, e o RH
tem que editar manualmente"*. O código diz outra coisa:

- **O backend nunca bloqueou.** `ficha.py:41-47` só barra `expurgado` e
  `aprovado`; `aguardando_assinatura` passa.
- **O botão existe**: *"← Preciso corrigir meus dados antes de assinar"*
  (`Assinatura.jsx:214`) — entregue na v2.88, com o mesmo diagnóstico de então
  (*"o backend sempre permitiu; quem não oferecia o caminho era a TELA"*).
- **Mas ele some na REASSINATURA**: `CandidatoApp.jsx:228` passa `null` quando
  `reassinatura === true` (ligado em `:60` e `:76`). E aí, se o status já for
  `aprovado`, o backend também recusa.

São dois consertos opostos — afrouxar trava × mostrar a saída — e não dá para
escolher sem saber em qual caminho a pessoa estava. **Pergunta ao Bruno.**

---

## Perguntas que só o Bruno responde

1. **O e-mail do Dr. Lucas (18-08-26, "Reembolso-creche implementação")** — não
   está no repositório, e o único documento oficial guardado (ofício CNMP nº
   5/2026) apenas COBRA dados, não traz o texto da norma. **O art. 11 §2º da IN
   147 também não está aqui.** Sem isso, "a periodicidade é mensal" e o "PF×PJ"
   viram decisão nossa disfarçada de decisão da norma.
2. **A queixa nº 1 foi "o sistema me bloqueou" ou "eu não sabia o que fazer"?**
   Ver seção acima.
3. **O nome padronizado do arquivo leva o NOME da pessoa?** O
   `nome_arquivo_dossie()` de 12/08 já sai com nome completo. Se o arquivo
   circula fora do RH (cliente, e-mail), é dado pessoal saindo no nome do
   arquivo — decisão dele, não nossa.
4. **A matrícula de 6 dígitos é padrão do Tirvu ou preferência visual?** A
   matrícula automática do sistema é `999` + 4 = **7 dígitos** (`9990001`) e vai
   escrita na coluna "Matrícula" do export do Tirvu. `9990001` não vira `000000`
   sem deixar de ser o mesmo número. E há duas origens na base: importada do
   Tirvu (comprimento desconhecido) e a automática.
   *Nota apurada:* zero-pad para EXIBIÇÃO é seguro — `import_ponto.matricula_norm`
   já ignora zeros à esquerda, então o casamento do ponto não quebra.
5. **Na admissão (feedback 11), coletar ou só perguntar?** Ele mesmo levantou a
   tensão: *"não posso gerar uma possível expectativa"*. Coletar documento de
   criança de quem talvez não tenha direito também é coletar dado pessoal
   sensível sem base — a decisão muda o desenho.

---

## Ideia levantada e DESCARTADA na avaliação

**"Competência mensal genérica"** — um esqueleto de entrega periódica por
colaborador (mês, tipo, N arquivos, prazo, lembrete) do qual o creche seria o
primeiro consumidor, servindo depois a certificações e ponto.

**Descartada**, e o motivo fica registrado para não voltar por engano: é
abstração que ninguém pediu, atrasaria o item que é obrigação legal, e a regra
da casa é que o que morde neste projeto é **falha silenciosa**, não código
difícil de ler — refatoração ampla mexe em código que funciona sem pagar isso.
Se um dia a segunda entrega periódica aparecer, aí se generaliza com dois casos
reais na mão, não com um.

---

## Quadro de priorização proposto

Ordem sugerida por **risco × dependência**, não pela ordem em que os feedbacks
chegaram. O que está travado por decisão do Bruno aparece marcado.

### P0 — a promessa que já está no ar (creche mensal)
Itens **4, 5, 6, 8**. É a única lacuna que hoje produz dano concreto: o
colaborador foi instruído por e-mail a enviar algo todo mês e não há porta, num
benefício que entra em folha. Inclui:
- porta de entrada do comprovante mensal (competência), com PF×PJ decidindo
  qual documento se exige — **travado pela pergunta 1**;
- **múltiplas folhas por documento** (hoje sobrescreve — perde documento
  silenciosamente, o pior modo de falha deste projeto);
- **exigir o termo de guarda** de quem declara `parentesco=guarda`;
- **upload pelo RH**, como na admissão;
- lembretes com antecedência configurável (o `dia_entrega_mensal` já existe e
  vira, enfim, dado vivo).

⚠️ Ao criar o worker: ele precisa entrar nos **DOIS** arquivos de deploy
(`docker-compose.base.yml` E `portainer-stack.yml`) — a armadilha da v2.66, que
já custou o aviso de certificação nunca ter rodado em produção. E a janela de
varredura tem que ser MAIOR que a cadência do worker.

### P1 — o que não depende de decisão nenhuma
- **Botão de criar jornada** (feedback 13): a rota e o `api.js` já existem; é
  ligar a tela. Menor item da leva.
- **Currículo obrigatório no banco de talentos** (feedback 2). ⚠️ Decisão
  embutida: hoje o texto diz *"opcional — aumenta suas chances"* e o desenho era
  de **máxima conversão**. Tornar obrigatório é reverter uma decisão anterior —
  vale confirmar que é isso mesmo que ele quer, inclusive no cadastro feito
  pelo RH (onde o currículo às vezes não existe ainda).
- **Matrícula no requerimento do creche e nas telas** (feedbacks 9, 13) —
  o formato depende da pergunta 4, mas *mostrar* não depende.

### P2 — padronização de nomes de download (feedback 12)
31 pontos, hoje com **4 funções de nomeação diferentes e não unificadas**.
⚠️ Duas armadilhas apuradas:
- **`BotaoBaixar.jsx:33` IGNORA o `Content-Disposition`** — o nome vem do prop
  `nome` no JSX. Padronizar só no backend não resolve; tem que passar pelo front.
- 5 pontos servem **arquivo de terceiro** com o nome original (currículo, anexo
  de CRM, de entrevista) — decidir se entram na regra ou ficam de fora.
Travado em parte pela pergunta 3 (nome da pessoa no arquivo) e 4 (formato da
matrícula).

### P3 — dedup no cadastro público de talentos (feedback 3)
Causa real confirmada: **não existe dedup nenhuma na porta pública**. A regra da
casa (`talentos.py:425`) é *"duplicata AVISA, não funde"* — merge cego cria
associação errada que ninguém vê depois. Aplicar a mesma regra na porta pública,
com o cuidado de **não vazar quem já está na base** (anti-enumeração, como no
gate do creche).

### P4 — creche nas telas de Colaboradores/Admissões (feedback 10)
Levantado: `Colaboradores.jsx` não mostra nada de creche hoje. É agregação de
dado que já existe; sem decisão pendente, mas sem urgência.

### P5 — coleta de creche na admissão (feedback 11)
**Já existe** (`BlocoCreche` no wizard). O trabalho real é de TEXTO e de
expectativa — travado pela pergunta 5.

### Feedback 1 (assinatura) — fora da ordem
Pode ser P0 ou pode ser não-item, conforme a resposta da pergunta 2.

---

## Decisões do Bruno (2026-08-18, perguntado com o levantamento na mão)

1. **Assinatura (feedback 1): ele não sabe em qual caminho a pessoa estava** —
   foi relato de terceiro. Decisão: investigar os DOIS caminhos (primeira
   assinatura e reassinatura) e consertar o que estiver errado em cada um.
   Na primeira assinatura o botão existe e é discreto (dar destaque); na
   reassinatura ele é escondido de propósito e o backend recusa se
   `status=aprovado` (reabrir com trava e auditoria).

2. **Matrícula: mudar a automática para 6 dígitos, formato `99NNNN`**
   (`990001`, `990002`…), **valendo só para as PRÓXIMAS**. Quem já tem
   `999NNNN` fica como está — já foi para o Tirvu e para o ponto com aquele
   número, e renumerar criaria duas matrículas para a mesma pessoa nos dois
   sistemas.
   ⚠️ Consequências a tratar na implementação:
   - `proxima_matricula_auto` precisa considerar as DUAS faixas ao calcular a
     próxima, senão colide;
   - `colaboradores.py:526` usa `startswith("999")` como indício de "já existe
     no Tirvu" — passa a precisar reconhecer também `99NNNN`;
   - o nome do arquivo usa a matrícula REAL de cada pessoa (7 dígitos para os
     antigos, 6 para os novos), com zero-pad até 6 quando for mais curta.

3. **Nome do arquivo mantém o NOME COMPLETO da pessoa.** Os arquivos circulam
   fora do RH e é justamente o nome que faz a pasta funcionar. Mantido o padrão
   do `nome_arquivo_dossie()` (caixa alta, ASCII), agora com matrícula.

4. **Creche na admissão (feedback 11): COLETAR TUDO**, dados e documentos das
   crianças, **com texto claro de que o direito depende de análise do RH e do
   contrato**. Ganha o tempo que ele quer; o cuidado passa a ser de REDAÇÃO —
   a tela não pode prometer o benefício, e o documento coletado de quem for
   indeferido precisa de destino definido (expurgo/retenção).

### Ainda pendente do Bruno
- **O e-mail do Dr. Lucas (18-08-26) e o art. 11 §2º da IN 147.** Sem eles, o
  PF×PJ e a periodicidade mensal ficam sem fonte normativa — é o que separa
  "obrigação legal" de "preferência de processo". **Bloqueia o P0.**

---

## FONTE NORMATIVA — e-mail do Dr. Lucas (18/08/2026 17:01)

Recebido em `docs/email e anexos dr lucas/`. Lucas Coelho Teixeira (Jurídico),
para Jessica Messias, Scarleet Oliveira e Bruno Fontes; cópia para Leandro.
Dois anexos: a **Declaração de Quitação do cuidador PF** (art. 11, II, IN 147) e
o **Requerimento revisado**. Isto encerra a pergunta 1 e destrava o P0.

### Contratos com aditivo assinado (quem já tem direito HOJE)

| Contrato | Vigente desde |
|---|---|
| ANEEL — 12/2026 | 01/05/2026 |
| INEP — 03/2026 (Secretariado) | 01/08/2026 |
| INEP — 37/2025 (Apoio Adm.) | 01/08/2026 |
| MAPA — 58/2024 (Brigadista) | 01/08/2026 |
| PREPÚBLICA — 62/2025 | 01/02/2026 |

⚠️ **A vigência é POR CONTRATO e tem data de início.** Hoje o sistema só tem o
booleano `PostoServico.da_direito_creche`, sem data — não sabe responder "esta
pessoa tinha direito em maio?". Isso importa para retroativo e para auditoria.

### Os três documentos exigidos (e a periodicidade de cada um)

1. **Requerimento assinado pelo beneficiário** — *"Um por filho/enteado/menor
   sob guarda e uma única vez"*.
2. **Certidão de nascimento** — comprovando até 5 anos e 11 meses. Uma vez.
3. **Nota fiscal (se a creche for PJ) OU declaração de quitação (se o cuidador
   for PF)** — ***"Uma por filho e mensalmente"***.

**Data de corte: todo dia 25 do mês** (para os documentos do item 3).

**Apuração e pagamento acompanham o SALÁRIO**: a competência fechada é paga até
o **5º dia útil do mês subsequente**.

### O que isso confirma e o que MUDA no desenho

- ✅ Confirma o P0: a entrega do item 3 é **mensal, por filho**, com data de
  corte — e hoje não há porta para recebê-la. Deixa de ser preferência de
  processo: é o procedimento definido pelo Jurídico.
- ✅ Confirma o PF×PJ do feedback 4, com o documento de cada caso.
- ⚠️ **`dia_entrega_mensal` tem default 5 e é editável de 1 a 28.** A data de
  corte real é **25**, e o **dia 5** é outra coisa (o pagamento, 5º dia útil do
  mês seguinte). Há risco concreto de o campo existente estar sendo lido como
  "dia do pagamento" quando o Jurídico o define como "corte do envio" — os dois
  números convivem no mesmo processo e significam coisas opostas.
- ⚠️ **"Um requerimento POR FILHO"** contraria o desenho atual: o
  `creche_pdf.py:81` gera **UM requerimento por colaborador**, listando todas as
  crianças — decisão registrada na v2.55. **Precisa de decisão do Bruno.**
- ⚠️ A **Declaração de Quitação PF pede dados que o sistema não coleta**: nome,
  CPF, RG e endereço do CUIDADOR, e o **valor pago no mês** por extenso. Se o
  sistema for gerar essa declaração preenchida (como já gera o modelo em
  branco), precisa de um cadastro de cuidador por criança.
- ✅ As cláusulas a) a e) do requerimento revisado **batem palavra por palavra**
  com o que o `creche_pdf.py:123-145` já gera. O texto jurídico está correto;
  o que muda é a estrutura (um por filho) e a identificação (matrícula).

### Decisões do Bruno após a leitura do e-mail (2026-08-18)

6. **Data de corte = 25**, como padrão do `dia_entrega_mensal` (segue editável),
   **e comunicado a quem já foi ativado** corrigindo a data. Motivo: o e-mail
   `creche_ativado` diz *"Todo mês, até o dia {{dia}}, envie a comprovação"* com
   o default **5**, e ainda avisa *"sem a comprovação no prazo, o reembolso do
   mês pode não ser efetuado"* — quem leu "dia 5" está com a informação errada
   sobre algo que afeta o próprio reembolso.
   ⚠️ Os dois números convivem no processo e significam coisas opostas:
   **25 = corte do ENVIO**; **5º dia útil = PAGAMENTO da competência fechada**.
   Nomear os campos de forma que ninguém os confunda.

7. **Requerimento: UM POR CRIANÇA**, como o Jurídico escreveu — revertendo o
   desenho da v2.55 (um por colaborador listando todas). ⚠️ Requerimentos **já
   assinados ficam intactos**: o `hash_sha256` do ato é calculado sobre o PDF
   (`api/assinaturas.py`) e o manifesto emitido aponta para ele; regerar faria a
   verificação acusar divergência. A mudança vale para os novos.

8. **Declaração PF continua EM BRANCO** para preenchimento à mão. O sistema
   ganha a porta para RECEBER o arquivo assinado; **não** haverá cadastro de
   cuidador nesta leva. Registrado como possibilidade futura: a declaração pede
   nome, CPF, RG e endereço do cuidador e o valor pago — se um dia for gerada
   preenchida, esses dados precisam existir por criança.

---

## Plano de execução (revisado com a fonte normativa)

### P0 — Ciclo mensal do creche (destravado)
O núcleo: **competência mensal por criança**, com PF×PJ decidindo o documento.

- Modelo de competência (mês/ano + criança), com o comprovante do mês:
  **nota fiscal** se PJ, **declaração de quitação** se PF — a escolha já existe
  em `tipo_comprovante`, hoje semi-órfã.
- **Um comprovante por filho e por mês** (não por benefício).
- **Múltiplas folhas por documento** — hoje a key é fixa e reenviar sobrescreve.
- **Upload pelo RH**, como na admissão.
- **Exigir termo de guarda** de quem declara `parentesco=guarda`.
- Corte **dia 25**; lembretes com antecedência configurável (1d, 2d, N dias).
- Mostrar `tipo_comprovante` na tela do RH e o que falta no mês corrente.

⚠️ Armadilhas conhecidas a respeitar:
- worker novo entra nos **DOIS** arquivos de deploy (v2.66);
- janela de varredura **maior** que a cadência do worker (v2.66);
- e-mail novo nasce no `CATALOGO` de `email_templates.py` (v2.21);
- se algo novo for para a lixeira, entra no mapa de `classes_restauraveis`
  (v2.72.2);
- rota nova sob `/rh/` **declara a permissão** (v2.86).

### P1 — Sem dependência de decisão
- Botão de **criar jornada** (rota e `api.js` já existem).
- **Matrícula** no requerimento, na tela de Creche e em Admissões.
- **Gerador de matrícula `99NNNN`** para as próximas; as `999NNNN` existentes
  ficam. `proxima_matricula_auto` passa a considerar as duas faixas; o indício
  de "já existe no Tirvu" (`colaboradores.py:526`) passa a reconhecer ambas.
- **Currículo obrigatório** no Banco de Talentos — *pendente de confirmação:
  reverte a decisão de "máxima conversão" e afeta também o cadastro pelo RH.*

### P2 — Nomes de download
`MATRÍCULA - NOME - DOCUMENTO`, caixa alta, sem acento; matrícula com zero-pad
até 6 (as de 7 saem com 7). Estende `nome_arquivo_dossie()` em vez de criar a
quinta função. ⚠️ **`BotaoBaixar.jsx:33` ignora o `Content-Disposition`** — tem
que passar pelo front também. Decidir caso a caso os 5 pontos que servem
**arquivo de terceiro** com o nome original.

### P3 — Dedup no cadastro público de talentos
Mesma regra da porta do RH: **avisa, não funde**. ⚠️ Sem vazar quem já está na
base (anti-enumeração, como no gate do creche).

### P4 — Creche nas telas de Colaboradores/Admissões
Agregação de dado que já existe.

### P5 — Coleta na admissão
`BlocoCreche` já existe. Trabalho de **redação** (não prometer o benefício) e
destino do documento de quem for indeferido.

### Fora de ordem — feedback 1 (assinatura)
Investigar os dois caminhos e corrigir cada um, conforme a decisão 1.

### Consequência ainda em aberto
A **vigência por contrato** (ANEEL desde 01/05, INEP desde 01/08…) não existe no
modelo: `da_direito_creche` é booleano sem data. Sem isso o sistema não responde
*"esta pessoa tinha direito em maio?"* — relevante para retroativo e auditoria.
**Levar ao Bruno antes de implementar o P0.**

### Decisões complementares (2026-08-18)

9. **Currículo obrigatório no Banco de Talentos nos DOIS cadastros** (público e
   pelo RH). Reverte conscientemente a decisão de "máxima conversão" da v1.55.
   ⚠️ Na tela pública o texto atual é *"opcional — aumenta suas chances"*
   (`Talentos.jsx:203`) e precisa mudar junto; no cadastro pelo RH, o
   `NovoTalento.jsx:66-77` anexa o arquivo DEPOIS de criar (com falha
   não-fatal), então a obrigatoriedade tem que valer antes de criar, senão
   nasce talento sem currículo com a regra "ligada".

10. **Vigência do creche fica NO POSTO**, ao lado de `da_direito_creche` e
    `valor_reembolso_creche` — sem tabela de contratos nesta leva. O RH preenche
    as 5 datas do e-mail do Jurídico na tela de Postos. Um cadastro de contratos
    (agrupando postos do mesmo contrato) fica **desenhado, não executado**: hoje
    `contrato_ref` é texto livre e casá-lo com contratos reais seria uma leva
    própria, com risco de merge cego (a lição da Incidência de Benefícios).

11. **Competência anterior à vigência é ACEITA e MARCADA** para o RH decidir —
    não recusada. ⚠️ Como o risco é pagar retroativo indevido, a marca não pode
    ser só um campo no registro: aparece **na fila do RH**, visível, como as
    demais pendências. Marca invisível equivale a não ter marca.

### Decisões sobre o currículo obrigatório (2026-08-18)

12. **O cadastro público passa a funcionar como a admissão: AUTOSAVE.** O
    registro vai sendo salvo conforme a pessoa preenche (o RH consegue ver e
    consultar mesmo incompleto), e o **currículo é a ÚLTIMA etapa, obrigatória
    para CONCLUIR** — não para o registro existir. Isso resolve o dilema do
    upload em duas chamadas: ninguém perde o contato de quem teve problema
    técnico, e ninguém conclui sem currículo.
    - **Avisar desde a PRIMEIRA tela** que o currículo é necessário — quem
      descobre no fim desiste no fim.
    - Aceitar **foto ou arquivo**, reusando a **câmera guiada da admissão**
      (`candidato/Camera.jsx`: moldura, dicas de luz/foco, cortar, várias fotos
      → um PDF). Formato `a4`. ⚠️ Ao ligar a câmera, usar `EXTENSOES_COM_WORD`
      no backend — a armadilha da v2.61 (a tela oferece `.docx` e o backend
      recusaria).
    - ⚠️ O currículo do Banco de Talentos **segue sem timbre** (decisão da
      v2.33: é documento de terceiro). A câmera aqui é só a captura.

13. **Cadastro pelo RH: obrigatório COM JUSTIFICATIVA.** O RH pode cadastrar sem
    currículo escrevendo o motivo, que fica na auditoria — o padrão da casa em
    ações como reverter colaborador e trocar matrícula. Não trava a indicação
    por telefone e deixa rastro de quem entrou sem.

---

## REGRA DE PROJETO — expertise nasce reutilizável (2026-08-18)

Cravada pelo Bruno nesta leva:

> *"cada vez que criarmos uma expertise, vamos colocá-la de modo que podemos
> utilizá-la em módulos existentes e futuros, para que não tenhamos que criar
> algo do zero. não sei se seria o caso termos um registro das criações"*

Já é praticado sem estar escrito — e é por isso que funciona: a **câmera guiada**
(`candidato/Camera.jsx`) nasceu na admissão e hoje serve **4 telas** (wizard,
checklist, creche, portal); o `VerificarIdentidade` do creche foi exportado e
parametrizado para o portal; a KBA saiu de `api/entrada.py` para
`services/kba.py` justamente para ser reusada.

**O registro que faltava** vai em `docs/planejamento/16-expertises-reusaveis.md`:
o catálogo do que existe, o que cada peça faz e quem já usa. Sem ele, a peça
existe e ninguém sabe — foi o que aconteceu com o `POST /rh/talentos` (a v2.94
ia recriar uma porta que já existia) e com as rotas de diagnóstico.

### Decisões sobre o valor mensal (2026-08-18)

14. **O valor do posto é TETO, não valor fixo**: reembolsa-se **o menor** entre a
    despesa comprovada e o `valor_reembolso_creche` do posto. Comprovou R$ 400
    num posto de R$ 526,64 → reembolsa R$ 400.
15. **O colaborador informa o valor ao enviar** o comprovante; o RH confere
    contra o documento ao analisar. Permite somar a folha, conferir o teto e
    exportar.
    ⚠️ Consequência: o valor é **entrada de quem não é do RH** — tratar como
    dado a conferir, nunca como verdade. O RH pode corrigi-lo na análise, e a
    correção fica na auditoria (quem mudou, de → para).
    ⚠️ Dinheiro NÃO se guarda como texto nem como float: centavos em inteiro,
    como o resto do sistema faz onde o valor decide folha.

---

## Status da execução (2026-08-19)

### ✅ Entregue — v3.01.0
- Botão de **criar jornada** (rota existia, tela nunca chamava).
- **Vigência do creche por posto** (`creche_vigente_desde`), individual e em massa.
- **Tela das credenciais de automação** (rotas existiam desde a v2.94 sem tela).

### ✅ Entregue — v3.02.0 (P0, o ciclo mensal)
- `CompetenciaCreche` + migration, com unicidade por criança/mês.
- Regras puras (`services/creche_competencia.py`): competência válida, atraso,
  dias para o lembrete, e o **teto** — validadas por 3 mutações.
- **Multi-folhas** (`services/creche_comprovante.py`): 1..N folhas → um PDF.
- **As duas portas** pela mesma função (`services/creche_envio.py`).
- **Worker de lembrete**, nos dois arquivos de deploy, dias configuráveis.
- Template `creche_lembrete_mensal` no catálogo.
- **Telas**: colaborador (câmera guiada, prazo como contagem) e RH (tabela com
  comprovado × reembolsável, folhas, retroativo, aprovar/recusar/anexar).

⚠️ **Defeito encontrado pelo CI e corrigido na mesma leva**: o caminho de escape
da normalização gravava os bytes de um PNG como se fossem PDF, derrubando o
envio com 500. Detalhes no CHANGELOG da v3.02.0. Ficou coberto por teste.

### ⏳ Pendente do P0
- **Comunicado corrigindo a data** para quem já foi ativado com `dia 5` no
  e-mail (a decisão 6 previu; falta escolher QUANDO disparar).
- Validação na homologação — depende do Bruno olhar a tela.

### ✅ Entregue — v3.03.0 (matrícula)
Faixa `99NNNN` (6 díg.) só para as próximas; matrícula em Admissões e no
requerimento do creche. ⚠️ Achado: `999001` (matrícula REAL do Tirvu) seria lida
como da nossa faixa e o gerador invadiria a numeração deles.

### ✅ Entregue — v3.04.0 (nomes de download)
`services/nome_arquivo.py` com o padrão `MATRÍCULA - NOME - DOCUMENTO`; o
`BotaoBaixar` passou a LER o `Content-Disposition`, então o padrão vale sem cada
tela repetir o nome. Documento individual do Arquivo saía como `termo-vt.pdf`.

### ✅ Entregue — v3.05.0 (dedup público de talentos)
A porta pública não tinha dedup nenhuma. Recadastro ATUALIZA em silêncio
(anti-enumeração: responder "já existe" viraria sonda); arquivado volta à fila,
`convertido` não é rebaixado.

### ⏳ Pendente das demais prioridades
- **P1 (resta)**: currículo obrigatório nos dois cadastros — autosave + câmera
  (decisões 12 e 13).
- **P4**: creche nas telas de Colaboradores/Admissões.
- **P5**: coleta na admissão (redação + destino do documento de indeferido).
- **Feedback 1**: investigar os dois caminhos da assinatura.
