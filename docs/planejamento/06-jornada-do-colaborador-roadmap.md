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

**Condições de implementação (obrigatórias, não negociáveis):**

1. **Provedor com retenção zero e não-treinamento — em contrato**, não em página
   de marketing. A escolha do provedor é do Bruno; a cláusula não é opcional.
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

### 3.2. Portal do colaborador (extrair o gate do creche)

Quatro pedidos batem na mesma porta: o brigadista mandando certificado, o
colaborador cadastrando curso, o avaliado escrevendo a manifestação da seção 9,
e o creche que **já entra hoje**.

O gate está pronto, testado e em produção — só está preso dentro do módulo de
creche: 2FA por e-mail, KBA (`app/services/kba.py`) para quem não tem e-mail,
resposta idêntica para CPF na base / fora da base (anti-enumeração).

**Ação:** extrair para um portal do colaborador genérico. Passa a servir ~1.200
pessoas em vez de ~40 — o gate não muda, o volume sim.

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

Volume: ~40 a 60 pessoas → 2 a 3 documentos/dia na fila. O validador aprende o
fluxo antes da torneira dos 1.200 abrir.

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

Antecedência **customizável pelo front** (Bruno sugeriu 60 dias como padrão).
Destinatários: o colaborador **e** o líder de brigada. Consome a matriz de
notificações da Onda A4.

Roda em worker Redis/RQ — infra já existe (`app/workers/`, ver `expurgo.py`).

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

**Bloqueio atual:** o layout do export de ponto do Tirvu ainda não foi visto.
Sem ele, não há como especificar o parser. **Pendência com o Bruno.**

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

| # | Pendência | Trava o quê |
|---|---|---|
| 1 | **Layout do export de ponto/atestados do Tirvu** | Item 6.8 inteiro |
| 2 | **Escolha do provedor de IA** (com cláusula de retenção zero em contrato) | Onda 0 |
| 3 | **Base legal LGPD** para tratamento de dado de saúde + registro no inventário | Onda 0 / B |
| 4 | Confirmar desenho do token sem 2FA na devolução do creche (7 dias, single-use, escopo restrito) | A3 |
| 5 | **Comitê de calibração** — conversa dedicada, não coberta nesta sessão | C (não bloqueia início) |
| 6 | Quantos postos têm brigada (dimensionar o piloto) | B |
| 7 | `Registra Ponto` — o que fazer com os registros existentes sem o campo | A1 |

---

<!-- Consolidado por Paige a partir da sessao de party-mode de 2026-07-22.
Participantes: John (PM), Winston (arquitetura), Sally (UX), Mary (analise),
Amelia (eng), Murat (testes/risco), Dr. Quinn (causa-raiz), Victor (estrategia),
Grumbal (adversario). Decisoes "TRAVADA" confirmadas pelo Bruno na sessao. -->
