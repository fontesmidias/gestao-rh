<!-- Roadmap das 4 ondas seguintes a v1.81. Consolidado em 2026-07-22 a partir
da sessao de party-mode com o Bruno (4 rodadas). As decisoes marcadas
"TRAVADA" foram confirmadas por ele na sessao e NAO devem ser reabertas sem
conversa. As restricoes de arquitetura e os testes obrigatorios sao condicao
de implementacao, nao sugestao. -->

# Roadmap — A JORNADA DO COLABORADOR

## 0. A tese

> **A admissão é o começo do cadastro, não o fim dele.**

Hoje o sistema conhece a pessoa profundamente **em um único dia** — CPF, CTPS,
endereço, dependentes, DISC, formação — e depois disso, silêncio. A pessoa vira
uma linha em `Colaboradores` com `situacao='ativo'` e fica congelada no retrato
do dia em que entrou. Podem passar seis anos.

O que o Bruno pediu, por três portas diferentes, é sempre a mesma coisa:

| Pedido | O que é, na verdade |
|---|---|
| Brigadista mandando reciclagem | a pessoa mudou desde que entrou |
| Colaborador cadastrando curso | a pessoa mudou desde que entrou |
| Fato observado registrado pelo líder | a pessoa mudou desde que entrou |
| Avaliação trimestral | a pessoa mudou desde que entrou |

O sistema registra o **retrato**. O que falta é o **filme**.

Consequência prática: o que parecia três módulos (brigadistas, desenvolvimento,
desempenho) é **dois módulos e uma consulta**. O roadmap abaixo é menor do que o
pedido original — não por corte de escopo, mas porque as peças se fundiram.

---

## 1. Estrutura em ondas

| Onda | Entrega | Por quê nessa ordem |
|---|---|---|
| **0** | Fundações compartilhadas (IA, portal do colaborador, escopo de acesso) | B e C consomem as três. Construir depois = construir duas vezes. |
| **A** | 4 ajustes pontuais | Independentes de tudo. Dor diária, custo baixo. |
| **B** | Cadastro de Desenvolvimento (piloto: brigadistas) | Valida as fundações com o caso mais difícil e volume baixo. |
| **C** | Avaliação de Desempenho (começa por Fatos Observados) | Chega em fundação já testada. Fatos Observados alimenta o formulário. |

**Ordem TRAVADA** (confirmada pelo Bruno).

---

## 2. As três populações (dimensionamento real)

Isso levou quatro rodadas para ficar claro e é a restrição que dimensiona tudo:

| População | Volume | O que faz | Impacto na arquitetura |
|---|---|---|---|
| **Avaliados** | ~20 | Recebem avaliação 360, 4×/ano | ~100 formulários/ciclo, ~400/ano. Cabe em memória. |
| **Avaliadores** | ~10 verticais + pares horizontais | Preenchem os formulários | ~6 formulários por avaliador por ciclo. **Gargalo é o tempo deles.** |
| **Cadastradores de desenvolvimento** | **~1.200** (empresa toda) | Pedem inclusão de curso/certificado | ~2.400 pedidos/ano, ~7.200 arquivos em 3 anos. **Exige filtro server-side.** |

> ⚠️ O volume da 3ª população derruba a premissa do `CLAUDE.md` de que
> *"sort/filtro são EM MEMÓRIA (volumes baixos)"*. Vale para avaliação; **não
> vale** para a fila de desenvolvimento. Padrão a seguir é o já existente em
> Colaboradores: filtro pesado server-side por cima, `DashPlanilha` refina em
> memória por baixo.

---

## 3. ONDA 0 — Fundações compartilhadas

Nenhuma das três existe hoje. As três são consumidas por B **e** C.

### 3.1. Camada de IA (roteada por sensibilidade)

> 🔧 **Correção pós-sessão (2026-07-22, verificada no código):** a sala assumiu
> que não havia IA nenhuma. **Errado — a base já existe.**
> `backend/app/services/ocr_ia.py` chama a **API de OCR da Mistral**
> (`mistral-ocr-latest`), com chave na config dinâmica, timeout de 30s,
> telemetria só de tipo + SHA-256 + tamanho, e **fallback local**: qualquer
> falha devolve `None` e o Tesseract assume. `ocr_rg.py` extrai sugestões de
> RG/CNH e `documentos.py` já consome isso no wizard do candidato.
> As condições 1-4 abaixo **já estão implementadas** para esse caminho, e a
> regra propõe-confirma também (`"o OCR sugere; o candidato confere"`).
>
> **O que falta de verdade na Onda 0**, portanto, não é a camada — é:
> (a) **roteamento por sensibilidade** (hoje não há distinção entre RG e
> atestado de saúde); (b) **extração de campos além de RG/CNH** (certificado,
> atestado); (c) verificar a cláusula contratual de retenção zero com a Mistral;
> (d) o log de auditoria dedicado a documento sensível. Isso reduz a Onda 0
> substancialmente.

**Decisão TRAVADA:** a IA lê **todos** os documentos, **inclusive o atestado de
saúde ocupacional**. O Bruno reafirmou ciente de que é dado pessoal sensível
(LGPD art. 11, categoria especial) e acrescentou o requisito: *"não quero
problemas"* — tratado aqui como requisito técnico, não como ressalva.

**Provedor escolhido pelo Bruno (2026-07-22): Mistral** — o mesmo já integrado
em `ocr_ia.py`. Verificado na documentação oficial em 2026-07-22:

| Ponto | Situação |
|---|---|
| Treinamento com dado de API | **Não** — "data sent through the API isn't used for model training" (vale para API paga; o tier gratuito *Experiment* treina por padrão) |
| Retenção padrão | **30 dias** para monitoramento de abuso |
| Zero Data Retention (ZDR) | **Só no plano Scale**, mediante **pedido aprovado** caso a caso — não é chave que se liga |
| `/v1/ocr` coberto pelo ZDR | **Sim** (é endpoint stateless) |
| Sede / regime | Empresa da UE, dados na UE, DPA disponível para clientes empresariais |

> ⚠️ **Consequência para o atestado de saúde:** sem ZDR aprovado, o documento
> fica **30 dias** nos servidores da Mistral. Para dado de saúde (LGPD art. 11)
> isso é retenção de dado sensível por terceiro sem necessidade — e o tier
> gratuito, que treina com o que recebe, é **proibido** para qualquer documento
> deste módulo. **Ordem prática:** (1) contratar o plano Scale; (2) pedir o ZDR
> justificando "documentos de RH com dados pessoais sensíveis"; (3) assinar o
> DPA; (4) só então habilitar a leitura de atestado. Enquanto o ZDR não estiver
> aprovado, o roteamento por sensibilidade deve **barrar o tipo `saude`** e
> deixar os demais funcionando — é uma linha de configuração, não um bloqueio de
> projeto.

**Condições de implementação (obrigatórias, não negociáveis):**

1. **Provedor com retenção zero e não-treinamento — em contrato**, não em página
   de marketing. → Mistral plano **Scale** + **ZDR aprovado** + **DPA assinado**;
   nunca o tier gratuito. A chave do tier gratuito no painel não pode ser usada
   para documento sensível.
2. **Documento sensível nunca é persistido fora da VPS.** Entra, extrai campo,
   sai. O arquivo original fica no MinIO, como o creche já faz.
3. **Log de auditoria de toda leitura de documento sensível:** quem, quando,
   qual tipo, hash do arquivo. **Nunca o conteúdo.** É o que prova, numa
   fiscalização, o que foi lido e que nada ficou guardado.
4. **Aviso ao colaborador** na tela em que ele sobe o documento, informando que
   passa por leitura automatizada (LGPD art. 9º, transparência). Uma frase.
5. **A IA nunca grava direto — propõe, humano confirma.** Já é a regra da casa
   (`jornada_parser`, `incidencia_beneficios`, backfill de endereço). Não abrir
   exceção: se a IA errar a validade de um atestado e isso gravar sozinho, o
   sistema passa a afirmar que um brigadista está regular quando não está.

**Custo:** ~2.400 chamadas/ano só na fila de desenvolvimento. Deixa de ser
detalhe de arquitetura e vira linha de despesa — dimensionar antes de contratar.

### 3.2. Portal do colaborador — `/meu` (desenho aprovado pelo Bruno)

Quatro pedidos batem na mesma porta: o brigadista mandando certificado, o
colaborador cadastrando curso, o avaliado escrevendo a manifestação da seção 9,
e o creche que **já entra hoje**.

O gate está pronto, testado e em produção — só está preso dentro do módulo de
creche: 2FA por e-mail, KBA (`app/services/kba.py`) para quem não tem e-mail,
resposta idêntica para CPF na base / fora da base (anti-enumeração). E a KBA já
usa dados **nativos** do `Candidato` (nascimento + sobrenome), então funciona
para o importado do Tirvu que nunca preencheu ficha — que é a maioria dos 1.200.

**Endereço: `/meu`** (aprovado). Uma porta só — o oposto de `/creche`,
`/desenvolvimento`, `/brigada` como portas separadas, que em seis meses deixaria
o colaborador sem saber qual é a dele.

```
/meu → CPF → [2FA por e-mail] ou [KBA, quem não tem e-mail] → Painel
                                                                │
   ┌──────────────┬───────────────────┬──────────────┬──────────┘
   ▼              ▼                   ▼              ▼
Meus dados   Meu desenvolvimento   Creche      Pendências
```

**A home é a lista de pendências DELE, não um menu.** Menu é o que o sistema
quer mostrar; a pessoa entra querendo resolver algo:

> ⚠️ Seu certificado de brigadista vence em 47 dias → Enviar reciclagem
> 📄 O RH devolveu seu pedido de creche: "Falta a certidão…" → Corrigir

Sem pendência, ela vê o próprio histórico.

**"Meu desenvolvimento" é o currículo dela dentro da empresa**, não um
formulário de upload: mostra o que mandou, o que o RH validou e o que está em
análise. É o que sustenta o *"valorizar quem busca se autoaperfeiçoar"* — se a
pessoa não vê o próprio inventário crescer, a frase não se cumpre e ela não
volta no sexto mês.

**O brigadista não vê "Portal de Reciclagem"** — vê o mesmo lugar onde mandou a
NR-35 ano passado, com um aviso em cima. Uma porta, um hábito.

**Escopo do que o colaborador vê** (confirmado pelo Bruno):

| Vê | Não vê |
|---|---|
| Os próprios dados cadastrais | Qualquer dado de colega |
| Os próprios cursos e certificados | — |
| O **motivo** de uma recusa do RH | — |
| O status do próprio creche | Notas de avaliação (Onda C tem regra própria) |
| Prazos e vencimentos dele | |

> O motivo da recusa é **visível ao colaborador** (decisão do Bruno): recusa sem
> motivo gera ligação para o RH. Consequência para a interface: o campo tem de
> ser escrito **sabendo que ele lê** — o rótulo no painel do RH avisa isso.

**Migração do creche para dentro do portal: SIM** (aprovado), mas **por último**
— o creche funciona e está estável; mexer nele antes de o portal provar-se seria
arriscar o que está bom por consistência visual.

### 3.3. Autorização por escopo (a terceira cara do sistema)

Hoje o sistema é binário: **RH** vê a folha inteira, **candidato** vê a si
mesmo. O Bruno pediu uma terceira cara: **liderança**, que vê dados dos seus
subordinados e de mais ninguém.

Um supervisor que consegue abrir a avaliação de alguém de outro posto é
vazamento, não bug de UX. **Isso é fundação, não feature** — construir antes de
C, não durante.

Testes obrigatórios:

- `test_supervisor_nao_acessa_avaliacao_de_outro_posto`
- `test_avaliador_horizontal_nao_ve_avaliacao_vertical_do_mesmo_alvo`

---

## 4. ONDA A — Os quatro ajustes

Independentes entre si e do resto. Podem sair a qualquer momento.

### A1. `Registra Ponto` obrigatório

Campo passa a ser obrigatório no cadastro. Já é coluna do layout Tirvu (S/N).
Atenção aos registros **existentes** sem o campo preenchido — decidir entre
backfill assistido e obrigatoriedade só na edição.

### A2. Cargo/função clicável

Seleção a partir dos cargos já mapeados, com opção de inserir novo. Usar
`SelectBusca.jsx` (padrão da casa para listas grandes: dados carregados 1× e
filtrados em memória).

### A3. Creche — link direto na devolução, sem 2FA

Quando o RH devolve um levantamento, o e-mail leva link de acesso direto — o
e-mail já foi validado, o 2FA vira atrito redundante.

**Desenho proposto** (afrouxamento consciente do gate; confirmar com o Bruno):
token single-use, validade curta (7 dias), amarrado àquele benefício
específico, abrindo **apenas** a tela de correção — não o histórico, não outros
dados. Se o e-mail vazar, o estrago fica contido.

### A4. Matriz de notificações

Problema relatado: *"estou recebendo no meu e-mail de login"* — notificação de
candidato indo para o e-mail pessoal do Bruno, sem configuração.

**Não** resolver com "campo de e-mail nas configurações". Resolver com uma
**matriz evento × destinatários**: cada evento do sistema (candidato concluiu
envio, creche enviado, certificado vencendo, avaliação pendente, …) tem lista de
destinatários configurável, com opção de caixa geral do RH + pessoas
específicas. Resolve o caso de hoje e todos os que as ondas B e C vão criar.

---

## 5. ONDA B — Cadastro de Desenvolvimento

### 5.1. A descoberta central

**Brigadista não é um módulo. É uma consulta.**

O Bruno confirmou que a Multicursos **não** manda a relação de formados — quem
alimenta é o próprio colaborador, enviando o certificado de formação e a última
reciclagem, com a IA preenchendo os campos. Isso é, palavra por palavra, o
fluxo do cadastro de desenvolvimento.

O "módulo de brigadistas" é:

> certificados do tipo *formação de brigada*, cujos titulares ocupam os cargos
> chefe de brigada, brigadista, bombeiro civil ou bombeiro líder, com validade
> vencendo nos próximos N dias.

Uma tabela, um filtro. **Decisão TRAVADA.**

Do lado da pessoa isso também é melhor: o bombeiro civil não entra num "Portal
de Reciclagem" que nunca viu — entra no mesmo lugar onde mandou a NR-35 ano
passado, e lá tem o aviso de vencimento. Uma porta só.

### 5.2. Onde a unificação quebra (e como resolver)

O certificado de brigadista tem consequência **contratual** — se vence, o posto
fica irregular perante fiscalização. O curso de Excel do fim de semana não tem
consequência nenhuma além de compor o desempenho.

Mesma tabela, criticidade oposta. Tratar igual = ou burocratizar o Excel, ou
relaxar o brigadista. **A distinção não é o tipo do documento — é se ele tem
validade que gera obrigação.**

`TipoDesenvolvimento`:

| campo | nota |
|---|---|
| `exige_validade` | bool |
| `meses_validade` | int, configurável |
| `critico` | bool — governa dossiê, alerta e proibição de lote |
| `cargos_aplicaveis` | JSON |

"Formação de brigadista" nasce `exige_validade=True`, `meses_validade=24`
(definido pelo Bruno em 2026-07-22), `critico=True`, cargos = os quatro.
"Curso livre" nasce com tudo falso.

**Herança do prazo em 3 níveis: tipo → cargo → posto.** O mais específico vence.
Pedido explícito do Bruno: *"customizável por posto, ou cargo, ou qualquer
outra coisa"*.

### 5.3. A fila de validação (o risco operacional real)

~2.400 pedidos/ano = **~10 por dia útil**. A 3 minutos cada, são **30 minutos
por dia, todo dia, para sempre**. Se a fila entope, o módulo morre em dois meses
e a culpa vai cair na interface.

**Aqui a IA ganha o custo dela — e não é onde ela foi pedida.** O gargalo não é
o colaborador digitando dois campos (ele faz isso 2×/ano); é o validador do RH
abrindo dez documentos por dia. Tela com documento de um lado, campos extraídos
do outro, botão de aprovar.

**Aprovação em lote para o caso fácil:** IA leu com alta confiança + tipo não
crítico + campos batendo → lista "prontos para aprovar" com checkbox, valida 20
de uma vez.

**Documento crítico nunca entra no lote.** Abre um a um, sempre.

- `test_documento_critico_nunca_entra_em_aprovacao_em_lote` — **obrigatório.**
  Sem ele, um dia alguém aprova 40 de uma vez sem olhar e o sistema passa a
  afirmar que há certificado válido onde não há. Pior que não ter sistema,
  porque agora tem gente confiando nele.

### 5.4. Piloto: postos com brigada

**Decisão TRAVADA** (Bruno seguiu a recomendação).

Não é o caso mais fácil — é **o mais difícil disfarçado de piloto**: documento
crítico, validade dura, quatro cargos, IA lendo dado de saúde, prazo por posto,
notificação com antecedência customizável, dossiê final para a Multicursos. Se
aguenta o brigadista, aguenta o curso de Excel de olhos fechados.

**Dimensionamento confirmado pelo Bruno (2026-07-22): ~10 postos com brigada.**
A ~4-6 brigadistas por posto, o piloto cobre **40 a 60 pessoas** — dentro do
estimado. Cada uma envia 3 documentos (identidade + certificado + ASO): ~150
documentos na primeira carga, depois só reciclagem (a cada 24 meses) e entrada
de gente nova. Fila diária de 2 a 3 documentos. O validador aprende o fluxo
antes da torneira dos 1.200 abrir.

**Critério de saída do piloto** (definido antes de começar, senão vira piloto
eterno): **um ciclo real completo ponta a ponta** — aviso de vencimento
disparado → colaborador entrou pelo portal → mandou os três documentos → IA leu
→ RH validou → dossiê saiu para a Multicursos.

### 5.5. Documentos do dossiê da Multicursos

Conforme especificado pelo Bruno:

- RG + CPF **ou** CNH
- Certificado de **formação** de brigadista
- Atestado de saúde ocupacional (para fins de curso/reciclagem)

Documento **já no sistema e validado pelo RH pode ser dispensado** — não pedir
de novo o que já se tem.

### 5.6. Plantão par/ímpar, diurno/noturno

Necessário para pedir a matrícula no período certo à Multicursos. Mas isso é
**escala**, não desenvolvimento — e o sistema já tem escala (tabela de Jornadas,
importada das 96 abas do Tirvu).

Perguntar ao bombeiro, no celular, algo que o sistema talvez já saiba faz a
pessoa desconfiar do sistema inteiro. **Propor e ele confirmar:** *"Pelo seu
posto e jornada, você está no plantão ímpar, diurno. Confere?"* — mesma regra
propõe-confirma de todo o resto.

Ressalva técnica: par/ímpar não é campo estruturado hoje; a `descricao` da
jornada é canônica e pode conter isso em texto livre.

### 5.7. Notificação de vencimento

Antecedência **customizável pelo front**, padrão **90 dias** (definido pelo
Bruno em 2026-07-22 — 90, não os 60 cogitados antes: é o tempo real de juntar
documento, marcar exame e a clínica abrir turma). Destinatários: o colaborador
**e** o líder de brigada. Consome a matriz de notificações da Onda A4.

Roda em worker Redis/RQ — infra já existe (`app/workers/`, ver `expurgo.py`).

### 5.9. Solicitação de matrícula à Multicursos (fluxo completo)

O ciclo que o Bruno desenhou, ponta a ponta:

```
[90 dias antes]  worker → e-mail ao colaborador + ao líder de brigada
       ↓
[colaborador]    entra no portal /meu, manda identidade + certificado + ASO
       ↓         (IA pré-preenche; ele confere e confirma)
       ↓
[RH valida]      fila de validação — crítico é conferido um a um
       ↓
[dash brigada]   RH vê quem está PRONTO, marca quem vai, escolhe a turma
       ↓
[rascunho]       sistema monta o e-mail com os dados de cada um + anexos
       ↓
[RH confere]     edita o que quiser na tela
       ↓
[envia]          e-mail sai para a Multicursos
```

**Turma é entidade** (`TurmaReciclagem`): data de início, período
(diurno/noturno), entidade formadora, observação. É o que permite o "clique
único" — escolhida a turma, o texto se monta para todos os marcados. O RH pode
cadastrar a próxima turma quando a clínica avisar, ou digitar a data na hora.

**Decisões do Bruno (2026-07-22):**

| Ponto | Decisão |
|---|---|
| Agrupamento | **Os dois**: o dash oferece "1 e-mail com os marcados" **e** "1 e-mail para cada". O RH escolhe na hora. |
| Anexos | **Um PDF por pessoa** (`dossie-<nome>.pdf`), com identidade + certificado + ASO empilhados — a clínica abre um arquivo por candidato. |
| Documento faltando | **Bloqueia e diz quem falta** ("Maria: falta o ASO"). Não sai dossiê furado. |

**Assunto:** `Solicitação de Matrícula - Reciclagem de Brigadista`

**Corpo (individual)** — texto do Bruno, com as variáveis marcadas:

> Prezados,
>
> Solicito, por gentileza, a matrícula do colaborador **{nome}** na turma com
> início em **{data_turma}**, no período **{periodo}**.
>
> Segue em anexo a documentação necessária para a inclusão do colaborador no
> curso.
>
> Fico no aguardo da confirmação da matrícula. Caso seja necessária alguma
> informação adicional, permaneço à disposição.

**Corpo (em grupo)** — mesma estrutura, no plural, com a lista numerada dos
colaboradores. O texto é **modelo editável** (mesma ideia dos modelos de
documento do RH), não string no código: a Multicursos pode mudar de exigência
e o RH ajusta sem deploy.

### 5.8. Por que 1.200 pessoas mandariam certificado espontaneamente

Premissa enorme, e o Bruno respondeu antes de ser perguntado:

> *"Para que a empresa pudesse conhecer melhor o seu colaborador… valorizar quem
> busca se autoaperfeiçoar."*

Não é conformidade — é reconhecimento. Diferença entre um sistema que morre no
sexto mês e um que as pessoas usam sem ninguém mandar.

**Mas o loop precisa fechar e ser visível.** Se a pessoa manda, o RH valida e
nunca mais nada acontece, ela não manda de novo. A tela do colaborador não é um
formulário de upload — é **o currículo dele dentro da empresa**, junto com a
timeline: cursos, avaliações, evolução.

> ⚠️ **Risco registrado:** "isso conta para promoção" é uma promessa que a
> empresa terá de cumprir. Alguém com seis certificados preterido por alguém sem
> nenhum vai imprimir a tela e levar para a reunião. O inverso, porém, é pior —
> hoje isso já acontece, só que sem registro e sem ninguém conseguir apontar.

---

## 6. ONDA C — Avaliação de Desempenho

### 6.1. O instrumento já existe

`docs/Cartilha do Avaliador e Formulário, de 17-06-2026.pdf` — 10 páginas, 11
seções, hoje rodando em Microsoft Forms. **Não inventar instrumento novo: o
formulário é a especificação.**

**Escalas (página 3, usar exatamente estas):**

- *Indicadores objetivos:* Atende · Atende parcial · Não atende · Não se aplica
- *Competências:* Não atende · Parcial · Adequado · Elevado · N/A

**Seções:** 1 identificação · 2 indicadores objetivos (7 itens) · 3 matriz de
competências (2 de Gestão + 6 Transversais) · 4 pontos fortes · 5 pontos a
desenvolver · 6 PDI · 7 recomendação · 8 postura ao receber feedback ·
9 manifestação do colaborador · 10 conclusão do aplicador · 11 assinaturas.

**Ocasião é um campo, não um módulo** (seção 1): experiência 30/45/60/90 ·
intermitente · periódica · feedback pontual/ocorrência · outro. Construir "só o
período de experiência" economizaria um `if`.

### 6.2. A cartilha já resolveu a assimetria de visibilidade

Duas frases do instrumento que valem mais que qualquer política nova:

- Seção 9 — **Manifestação do colaborador**: *"espaço para registrar
  concordância, discordância ou comentários"*.
- Página 5 — *"a assinatura do colaborador indica ciência da avaliação, não
  obrigatoriamente concordância"*.

O gestor registra como a pessoa reagiu (seção 8) **e** a pessoa registra o que
achou (seção 9), no mesmo documento assinado. **Preservar isso é obrigatório** —
é o que separa gestão de desempenho de vigilância com interface bonita.

Regra derivada: **o colaborador vê o que foi registrado sobre ele.**

### 6.3. Fatos Observados vem PRIMEIRO

Inversão contraintuitiva, e é a decisão mais importante da Onda C.

O Bruno diagnosticou o **efeito de recência** sem usar o termo: *"muitas das
vezes, o líder na hora de avaliar esquece de algo que o colaborador fez"*. E a
cartilha (pág. 3) exige **fato observável** em vez de rótulo — *"faltou 3 vezes
sem aviso em maio"*, não *"tem má vontade"*.

Sem banco de fatos, o líder abre o formulário com a memória vazia e escreve
rótulo, porque rótulo é o que sobra quando o fato foi esquecido. Com 6
formulários por avaliador por ciclo, isso é preenchido às pressas na véspera do
prazo — e essas notas decidem efetivação e desligamento.

**Portanto:** Fatos Observados roda **sozinho por um trimestre**, alimentando o
banco. Quando o formulário nascer, abre já com os fatos do período ao lado. O
líder não escreve do zero — **revisa o que já registrou**.

`FatoObservado`: `colaborador_id`, `autor_id`, `tipo` (positivo/negativo),
`descricao`, `impacto`, `anexo_id` (opcional), `ocorrido_em`.

- `test_colaborador_ve_proprios_fatos_observados`
- ⚠️ Anexo de **vídeo**: limitar tamanho e duração. Líderes gravando plantão no
  celular enchem o disco da VPS em três meses.

### 6.4. Anonimato e nivelação (a estratégia anti-injustiça)

**Decisão TRAVADA:**

| | Visibilidade | Por quê |
|---|---|---|
| **Vertical** | **Identificado** | É o líder. A pessoa sabe quem é e vai sentar na frente dele — a cartilha *exige* a conversa. |
| **Horizontal** | **Anônimo, agregado** | É o colega de mesmo nível. Se assina com nome, mente. |

Com apenas ~2 pares, o anonimato é matematicamente frágil: se as notas divergem,
o avaliado infere quem deu qual.

- `test_avaliado_nao_ve_horizontal_individual_apenas_agregado`
- `test_agregado_horizontal_exige_minimo_dois_respondentes` — **supressão de
  célula**, como estatística oficial. Agregado de um respondente é o individual
  com outro nome.

**Nivelação de rigor — não normalizar, informar.** As três famílias da
literatura:

1. *Distribuição forçada* — **VETADA.** A GE abandonou, a Microsoft matou em
   2013. Com ~20 avaliados, obriga a rebaixar alguém bom porque a matemática
   mandou. Aritmética fingindo ser justiça.
2. *Normalização estatística (z-score)* — **não aplicar à nota.** Com 3 avaliados
   por líder, o z-score é ruído puro. E quando a pessoa descobre que a nota que
   viu não é a que o líder deu, a confiança no sistema acaba.
3. *Comitê de calibração* — viável com 10 avaliadores. **Não discutido a fundo
   nesta sessão** — pendência para conversa dedicada.

**Solução adotada: mostrar o desvio ao homologador.** *"Este avaliador dá em
média 4,6; a média geral é 3,8."* Não altera dado, informa decisão. Um endpoint,
um cálculo, zero política nova — e é honesto com o avaliador, que também é
gente: ninguém acorda querendo ser injusto, e quem dá 5 em todo mundo
geralmente não sabe que faz isso.

> Distinção que importa: **normalização corrige rigor** (durão × bonzinho);
> **comitê corrige critério** (o que é "bom" para mim × para você). São
> problemas diferentes e o Bruno tem os dois.

### 6.5. A conversa é o produto

A cartilha manda dar o feedback **presencialmente, em local reservado** (pág. 5)
e registrar como a pessoa reagiu (pág. 4, passo 7).

Um sistema onde o gestor preenche, clica em enviar e a pessoa recebe a nota por
e-mail **não digitalizou a cartilha — matou o que ela pede.**

**Máquina de estados obrigatória:**

```
rascunho → preenchida → feedback dado (com data) → manifestação do colaborador → homologada
```

A manifestação (seção 9) **trava a homologação por um prazo**, senão vira letra
morta.

### 6.6. Ciclos e homologação

- **4 ciclos por ano** — TRAVADO.
- **Datas configuráveis pelo front**: geral, por posto ou individual — TRAVADO.
  (Recomendação da sala, não vinculante: datas fixas facilitam comitê de
  calibração, que só funciona com todo mundo avaliado na mesma janela.)
- **360 para todos os avaliados** (vertical + horizontal) — TRAVADO.
- **Homologador: o RH** — TRAVADO. A cartilha já traz "Gente & Cultura"
  assinando na seção 11.

### 6.7. Visualizações

- **Radar ("teia de aranha")** — 8 eixos, que são exatamente as 8 competências
  da seção 3 da cartilha. Não é enfeite de dashboard: é **o material da conversa
  de feedback** — o gestor abre na frente da pessoa e conversa em cima dele.
- **Timeline evolutiva** — histórico das ocasiões (30/45/60/90, depois
  periódicas). A pessoa vê a própria curva. É o oposto de vigilância.

### 6.8. Import de ponto do Tirvu — atenção

Pedido do Bruno: trazer entrada, saída, atrasos, atestados e lançamentos do
Tirvu para dar "dados objetivos" ao avaliador.

> ⚠️ **Risco a mitigar no desenho:** atraso vira número, número vira nota, nota
> vira desligamento — sem discussão de contexto. Quem chegou atrasado seis vezes
> cuidando da mãe doente aparece como número vermelho no painel do avaliador.
>
> Mitigação mínima: o dado bruto entra como **insumo com contexto editável**,
> nunca como nota calculada; e o colaborador vê o que está registrado sobre ele
> (regra 6.2).

**Layout recebido em 2026-07-22** (`docs/Exportação de Ponto Eletrônico.xlsx`,
431 linhas reais, 33 pessoas, julho/2026). Estrutura verificada:

- **Aba única, cabeçalho em DUAS linhas.** Linha 0 tem os grupos (`Entrada 1`,
  `Saída 1`, `Entrada 2`, `Saída 2`) com `undefined` nas colunas seguintes;
  linha 1 tem os subcampos de cada grupo. Os dados começam na **linha 2**.
- **49 colunas** = 13 de identificação/apuração + 4 blocos de 9 colunas
  (`Hora`, `Posto de Serviço`, `Latitude`, `Longitude`, `Distância`,
  `Expressão`, `Modo de Registro`, `Foto`, `Sincronização`).
- Identificação: `ID`, `Competência` (data dd/mm/aaaa), `Dia` (nome da semana),
  `Nome`, `Matrícula`, `Cargo`, `Empresa`, `Posto de Serviço`, `Jornada de
  Trabalho`, `Situação`, `Carga Prevista`, `Horas Trabalhadas`, `% Trabalhado`.
- `Situação` ∈ {Acima do Previsto, Dentro do Previsto, Abaixo do Previsto}.
- Lido pelo `_ler_linhas_xlsx` de `postos.py` (zip+XML) — o arquivo **não tem
  sharedStrings**, tudo inline. openpyxl não é necessário nem confiável aqui.

> ⚠️ **Armadilhas encontradas nos dados reais** (não são hipóteses — estão nas
> 431 linhas):
> 1. **NÃO existe coluna de CPF.** O casamento com o `Candidato` só pode ser
>    por **matrícula** — que é exatamente o campo que o sistema gera sozinho
>    (999+seq) quando falta. Casar por nome seria erro garantido (homônimos,
>    acentuação). Import tem de recusar linha cuja matrícula não exista na base
>    e listar as recusadas para o RH, nunca criar pessoa.
>    **Cuidado com zeros à esquerda:** as matrículas reais vêm como `001941`,
>    `001767`, `003035` — texto, não número. Normalizar dos dois lados antes de
>    comparar (`lstrip("0")` ou comparação por dígitos), senão `1941 != 001941`
>    e o import recusa a base inteira. A amostra também mostra a MESMA pessoa
>    com `3035` e outras com `003035` — a inconsistência está nos dados de
>    origem.
> 2. **Uma célula de horário pode conter DOIS horários** (`"10:17 07:00"`,
>    `"12:00 17:17"`) — 14 linhas na amostra. Um parser ingênuo de `HH:MM`
>    lê o primeiro e descarta o segundo em silêncio.
> 3. **29 linhas com `00:00` em Horas Trabalhadas** e `Situação = Abaixo do
>    Previsto`, mas COM marcação de entrada. É registro incompleto (esqueceu de
>    bater a saída), **não é falta** — tratar como falta seria acusar de ausência
>    quem trabalhou. Falta de verdade precisa de outro sinal, a confirmar (§ 9).
> 4. **A ausência de marcação não significa ausência de trabalho.** Há linha sem
>    nada em `Entrada 1` e com **04:10** em Horas Trabalhadas — e outra, também
>    sem marcação, com **10:33 (117%)**. Ou seja: **`Horas Trabalhadas` e
>    `Situação` são a apuração do Tirvu e devem ser a fonte de verdade**; as
>    quatro colunas de marcação são detalhe operacional e podem estar vazias
>    mesmo em dia trabalhado. Um parser que dedusse presença das marcações
>    inventaria falta onde não há.
>
> Consequências de LGPD/proporcionalidade: o export traz **latitude, longitude,
> distância e URL de FOTO** de cada marcação. Isso é rastreamento de localização
> e imagem — importar para um módulo de **avaliação de desempenho** é
> desproporcional ao fim. **Decisão de projeto: importar apenas as colunas de
> apuração** (competência, situação, carga prevista, horas trabalhadas, %) e
> **descartar geolocalização e foto na leitura**, sem persistir. Se um dia forem
> necessárias, é outro módulo com outra base legal.

### 6.9. IA no desempenho

Dois usos pedidos: **resumo do desempenho** e **sugestão de PDI** (seção 6 da
cartilha). Ambos consomem a camada da Onda 0 e seguem a regra propõe-confirma:
a IA sugere, o gestor edita e assume. Resumo visível **apenas ao gestor do
desempenho / homologador**, conforme pedido.

---

## 7. Restrições de arquitetura (consolidado)

1. **Filtro server-side na fila de desenvolvimento.** ~7.200 arquivos em 3 anos.
   A premissa "volumes baixos" do `CLAUDE.md` não vale aqui. Padrão: filtro
   pesado server-side no topo, `DashPlanilha` refinando em memória por baixo
   (igual Colaboradores).
2. **Autorização por escopo antes de C**, não durante.
3. **IA propõe, humano confirma** — sem exceção, inclusive quando a confiança
   for alta.
4. **Documento crítico nunca em lote.**
5. **Supressão de célula** no agregado horizontal (mínimo 2 respondentes).
6. **Rotas específicas antes das paramétricas** (armadilha conhecida: `/lote/`,
   `/massa/`, `/provas-aplicacoes`). Vale para todas as rotas novas.
7. **Limite de tamanho/duração** em anexo de vídeo do Fato Observado.
8. **`await arquivo.close()` no `finally`** em todo upload — regra da casa.

## 8. Testes obrigatórios (consolidado)

```
test_supervisor_nao_acessa_avaliacao_de_outro_posto
test_avaliador_horizontal_nao_ve_avaliacao_vertical_do_mesmo_alvo
test_avaliado_nao_ve_horizontal_individual_apenas_agregado
test_agregado_horizontal_exige_minimo_dois_respondentes
test_documento_critico_nunca_entra_em_aprovacao_em_lote
test_colaborador_ve_proprios_fatos_observados
test_leitura_documento_sensivel_registra_auditoria_sem_conteudo
```

## 9. Pendências com o Bruno

### Resolvidas em 2026-07-22 (mesma data)

| # | Pendência | Resposta |
|---|---|---|
| 1 | Layout do export de ponto do Tirvu | **Recebido** (`docs/Exportação de Ponto Eletrônico.xlsx`) — layout, armadilhas e decisão de descartar geolocalização/foto em § 6.8 |
| 2 | Provedor de IA | **Mistral** (o já integrado). Condições e ordem prática em § 3.1 |
| 3 | Base legal LGPD para dado de saúde | **Minuta redigida**: `07-lgpd-leitura-automatizada-documentos.md` — art. 11, II, "a" e "f"; falta revisão jurídica |
| 4 | Token sem 2FA na devolução do creche | **Confirmado e ENTREGUE** na Onda A (v1.82) |
| 6 | Quantos postos têm brigada | **~10 postos** → piloto de 40 a 60 pessoas (§ 5.4) |
| 7 | `Registra Ponto` nos registros existentes | **Resolvido na Onda A**: virou pendência do export, não campo travado (§ A1) |

### Em aberto

| # | Pendência | Trava o quê |
|---|---|---|
| 3b | **Revisão jurídica** da minuta LGPD + assinatura do DPA da Mistral + **aprovação do ZDR no plano Scale** | Leitura de ASO (só ela; o resto anda) |
| 5 | **Comitê de calibração** — conversa dedicada, não coberta nesta sessão | C (não bloqueia início) |
| 8 | Como o Tirvu marca **falta** de verdade (o `00:00` com marcação é registro incompleto, não ausência — § 6.8) | Precisão do item 6.8 |
| 9 | Confirmar se **par/ímpar e diurno/noturno** dá para derivar da jornada (hoje é texto livre) ou se pergunta ao brigadista | § 5.6 |

---

<!-- Consolidado por Paige a partir da sessao de party-mode de 2026-07-22.
Participantes: John (PM), Winston (arquitetura), Sally (UX), Mary (analise),
Amelia (eng), Murat (testes/risco), Dr. Quinn (causa-raiz), Victor (estrategia),
Grumbal (adversario). Decisoes "TRAVADA" confirmadas pelo Bruno na sessao. -->
