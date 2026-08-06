# Módulo de Entrevistas — da concepção ao funcionamento

**Data:** 2026-08-05
**Origem:** 22ª leva de feedbacks (2026-08-04). Sessão de party mode com a sala
installed + benchmark de campo + mapeamento do código existente.
**Status:** desenhado, aguardando aprovação das competências pelo Bruno.

---

## 1. Por que este módulo existe

O sistema hoje leva a pessoa do Banco de Talentos até o convite de admissão
com um buraco no meio:

```
talento entra → vaga cadastrada → match ranqueia → RH abre currículo
   → status vira em_analise → RH manda teste /t/ e prova /p/
   → ??? ← AQUI
   → converter() → candidato → wizard de admissão
```

Entre "o RH olhou o currículo" e "o RH mandou o convite" acontece uma
conversa que **não deixa rastro nenhum no sistema**. Hoje ela vira, na
melhor das hipóteses, uma anotação solta no mini-CRM: *"entrevistei, gostei,
mandar convite"*.

Isso falha de três maneiras concretas:

1. **Não compara.** Com três pessoas entrevistadas para a mesma vaga, as
   anotações dizem "gostei dele", "pareceu boa" e "achei meio devagar". Não
   há como escolher com base em nada além de impressão.
2. **Não presta contas.** Se alguém perguntar por que aquela pessoa foi
   escolhida, a resposta é memória.
3. **Não protege a empresa.** Sem roteiro, o que foi perguntado depende de
   quem perguntou — e há perguntas que são ilícitas (§ 6).

### A tese

> A entrevista não é um módulo novo. É **o degrau que falta** no funil que já
> existe. Ela não inventa entidade de pessoa, não inventa formulário e não
> inventa mecanismo de acesso — ela costura peças que o sistema já tem.

---

## 2. O que o benchmark mudou no desenho

Pesquisa de campo (fontes ao final). O que sobreviveu ao escrutínio:

### 2.1 O número clássico está desatualizado — e o intervalo importa mais

Schmidt & Hunter (1998) dava **.51** para entrevista estruturada contra
**.38** para não-estruturada. Sackett et al. (2022) mostraram supercorreção
sistemática por restrição de amplitude; as estimativas caíram .10–.20.

Na revisão, a entrevista estruturada **passa a ser o preditor nº 1** de
desempenho no trabalho, com validade **.42** — mas o intervalo de
credibilidade de 80% vai de **.18 a .66**.

**A leitura que interessa não é o .42, é a largura do intervalo.** A mesma
técnica entrega quase nada ou entrega muito, dependendo da implementação.
Cada componente que se corta neste desenho custa validade real.

### 2.2 Comportamental × situacional — e por que as duas variantes existem

| Tipo | Validade geral | Complexidade baixa | média | alta |
|---|---|---|---|---|
| Comportamental ("conte uma vez em que…") | .51 | .48 | .51 | .51 |
| Situacional ("o que você faria se…") | .43 | .44 | .51 | **.30** |

Os cargos da Green House (vigia, ASG, recepcionista, auxiliar
administrativo) são de complexidade baixa a média — faixa em que as duas
funcionam (.44–.51).

**O achado que decide o desenho:** a pergunta comportamental exige que a
pessoa tenha uma história para contar. *"Conte uma vez em que lidou com um
cliente irritado"* não funciona com quem nunca trabalhou formalmente — e
primeiro emprego é fatia real nesses cargos. Nesse caso a pergunta não mede
competência, mede currículo.

**Decisão:** o roteiro tem **duas variantes de pergunta para a mesma
competência** — comportamental para quem tem experiência no cargo,
situacional para quem não tem. **A competência, a escala e a âncora são
idênticas nas duas.**

> **Ressalva registrada (Grumbal):** isso arranha o princípio "mesma pergunta
> para todos". A defesa (Sally) é que a comparação estruturada é *por
> competência ancorada*, não por literal da pergunta — duas portas, mesma
> sala. Se as duas variantes produzirem distribuições de nota muito
> diferentes, a âncora não está segurando. Com o volume da Green House isso
> não será mensurável tão cedo; fica anotado como risco aceito.

### 2.3 Nota sem evidência é ruído

Âncora comportamental (BARS) = cada ponto da escala descreve um
**comportamento observável**, não um adjetivo. Consequência de produto:
**justificativa obrigatória por competência**. Campo de nota sem frase ao
lado não salva.

### 2.4 Quatro competências, não oito

Consenso das fontes: 4–6 competências por entrevista, teto de 8 antes da
"fadiga de avaliação". Para cargos operacionais, **4 é o alvo**. Com 15
competências, preenche-se no automático; com 4, pensa-se.

### 2.5 Preenchimento tardio é invenção retrospectiva

Memória decai rápido. Quem preenche no dia seguinte **reconstrói**, não
lembra. A recomendação não é proibir (o RH deixaria de registrar) — é
**carimbar a defasagem** entre a entrevista e o preenchimento, visível na
tela.

### 2.6 O que ficou de fora por decisão

**Trava anti-"peeking"** (não ver a nota do colega antes de enviar a sua). O
Greenhouse mediu sobre 10 milhões de entrevistas em painel: quem espia tem
3,6% mais chance de dar exatamente a mesma nota, e quando a nota muda por
isso a chance de o candidato passar cai de 14% para menos de 6%. Custo de
implementação ≈ zero.

**Não se aplica hoje:** só o RH entrevista (decisão do Bruno, 2026-08-04) —
com um avaliador não há nota de colega para espiar. **Fica datado, não
descartado:** se um dia o supervisor do posto entrar como segundo avaliador,
esta trava volta à mesa antes de qualquer outra coisa.

**Gravação de entrevista (áudio/vídeo).** Fora do escopo — exige consentimento
expresso por escrito com prazo, acesso e armazenamento declarados. É
sub-projeto próprio.

---

## 3. Decisões travadas pelo Bruno

| # | Decisão | Consequência de desenho |
|---|---|---|
| 1 | **Só o RH entrevista** | Sem link público, sem código por e-mail, sem sessão externa. Tudo no painel autenticado. Zero superfície de acesso nova. |
| 2 | **Os três cenários ocorrem** — filtrar, verificar e alocar | Uma tela por vaga serve os três; muda o que se faz depois, não a lista. |
| 3 | **Duas fichas de natureza diferente** | Triagem = *checagem de viabilidade* (sem nota). Entrevista = *avaliação* (4 competências ancoradas). |
| 4 | **Seguro-desemprego entra na triagem** | Ver § 4.1 — é o motivo de a triagem existir. |
| 5 | **Retenção 180 dias configurável — arquiva, não apaga** | Sai da vista e das métricas; o registro permanece. |
| 6 | **Entrevista sem desfecho vira pendência e cobra** | O sistema pergunta, nunca conclui. |

### 3.1 Sobre a retenção — o que foi decidido e o que isso implica

A sala ofereceu três opções que todas assumiam **apagar** algo. O Bruno
respondeu fora do menu: *"nada, apenas fica arquivado"* — que é melhor do que
as três, porque resolve a tensão que a sala não resolveu:

- Nota velha não deve assombrar quem se candidata de novo dois anos depois.
- Mas reentrevistar quem faltou três vezes sem saber é desperdício.

Arquivar resolve os dois: o julgamento vencido sai da vista por padrão, e a
memória continua acessível a quem procurar.

> **Ressalva registrada (Vex):** arquivar **não é** minimizar. Anotação de
> entrevista, com nota e justificativa, sobre pessoa que nunca foi
> contratada, fica guardada indefinidamente. É defensável — o termo do Banco
> de Talentos cobre "tratar meus dados para fins de recrutamento", e
> tratamento é o verbo do art. 5º X da LGPD. A prática de mercado seria
> eliminar ou anonimizar em 90–180 dias. É uma escolha informada do Bruno,
> registrada como tal.

---

## 4. Concepção — as duas coisas

### 4.1 Triagem: checagem de viabilidade

**Não é uma entrevista curta.** É outra coisa.

O problema que a triagem resolve não é avaliar competência — é descobrir, em
cinco minutos de ligação, se **vale gastar uma hora presencial**. Em
terceirização a desistência raramente é por incapacidade; é por escala que
não cabe na vida da pessoa, local inacessível, salário abaixo do esperado —
ou porque a pessoa está recebendo seguro-desemprego e não tem interesse real
em ser contratada agora.

Por isso a triagem **não tem nota, não tem competência e não tem âncora**.
Tem perguntas de sim/não que decidem se segue.

**Campos (todos sim/não/não sei + uma linha livre no fim):**

| Campo | Pergunta ao vivo |
|---|---|
| `aceita_escala` | A escala é 12×36 noturno. Isso cabe na sua rotina? |
| `aceita_salario` | A remuneração é R$ X. Está de acordo? |
| `consegue_chegar` | O posto fica em \<local\>. Você consegue chegar no horário? |
| `tem_interesse` | Você ainda tem interesse nessa vaga? |
| `recebe_seguro_desemprego` | Você está recebendo seguro-desemprego hoje? |
| `observacao` | uma linha, livre |
| `desfecho` | `segue` \| `nao_segue` \| `sem_contato` |

**Sobre o seguro-desemprego.** O campo já existe em
`Talento.recebe_seguro_desemprego` (declarado no cadastro público, que pode
ter sido há oito meses). A triagem pergunta **o que vale hoje** — são dados
diferentes e ambos ficam. Quando divergirem, a triagem prevalece por ser mais
recente, e a divergência em si é informação.

Não é critério de exclusão e **não pode virar um**: recusar alguém por
receber seguro-desemprego não é decisão do sistema. É um dado que explica
falta e desistência, e que o RH usa para decidir se investe uma hora
presencial agora ou volta a procurar a pessoa depois.

**Tempo alvo de preenchimento: menos de 2 minutos.**

### 4.2 Entrevista: avaliação ancorada

Quatro competências, escala 1–4, **justificativa obrigatória em cada uma**,
recomendação final.

Escala 1–4 e não 1–5 de propósito: sem ponto médio, o avaliador é obrigado a
pender para um lado.

#### As quatro competências (PENDENTE DE APROVAÇÃO DO BRUNO)

Critério de escolha: (a) observável numa conversa de 20 minutos — se depende
de ver a pessoa trabalhar, não serve; (b) enraizada nos indicadores da
cartilha de desempenho que o RH já aprovou, não inventada; (c) preditiva do
que de fato derruba a permanência num posto.

---

**1 — Confiabilidade e presença**
*(raiz: indicadores `assiduidade` e `pontualidade` da cartilha)*

| Nota | Âncora |
|---|---|
| **4** | Cita situação concreta em que se antecipou a um imprevisto (saiu mais cedo por chuva, greve, problema no transporte) e descreve como avisou o responsável com antecedência. |
| **3** | Descreve rotina de transporte compatível com o horário do posto; quando faltou, avisou antes e justificou. |
| **2** | Fala de pontualidade em termos genéricos ("sou pontual"), sem exemplo; admite atrasos ocasionais sem descrever como comunicou. |
| **1** | Relata faltas ou atrasos sem aviso; atribui a terceiros sem ação própria; não consegue descrever como chegaria ao posto. |

- **Comportamental:** "Conte uma vez em que você quase se atrasou para o trabalho. O que você fez?"
- **Situacional:** "Você começa às 6h e às 5h descobre que a linha de ônibus está parada. O que você faz?"

---

**2 — Trato com público e postura sob pressão**
*(raiz: indicador `relacionamento` da cartilha)*

| Nota | Âncora |
|---|---|
| **4** | Descreve situação real de conflito com público e como conduziu sem escalar: o que falou, a quem acionou, como terminou. Separa o problema da pessoa. |
| **3** | Descreve postura adequada (ouvir, não responder no mesmo tom, chamar o supervisor), com exemplo ainda que simples. |
| **2** | Diz que "leva na boa" ou "não discuto", sem descrever o que faz concretamente. |
| **1** | Relata revide, ironia ou abandono do posto; culpa o público; ou não consegue imaginar a situação. |

- **Comportamental:** "Conte uma vez em que alguém falou com você de forma ríspida no trabalho. O que aconteceu?"
- **Situacional:** "Um visitante insiste em entrar sem crachá e começa a levantar a voz. O que você faz?"

---

**3 — Cumprimento de norma e procedimento**
*(raiz: indicadores `normas_epi` e `uniforme` da cartilha)*

| Nota | Âncora |
|---|---|
| **4** | Cita norma ou procedimento específico de trabalho anterior e por que existia; descreve ocasião em que cumpriu mesmo sendo inconveniente. |
| **3** | Reconhece a existência de regras (EPI, uniforme, registro de ponto, livro de ocorrência) e diz cumprir, com exemplo. |
| **2** | Responde de forma genérica ("sigo as regras") sem citar nenhuma; trata norma como formalidade. |
| **1** | Relata ter contornado procedimento por conveniência e não vê problema nisso; ou desconhece o que é EPI no contexto do cargo. |

- **Comportamental:** "Me conta uma regra do seu trabalho anterior que você achava chata mas cumpria. Por que ela existia?"
- **Situacional:** "É um dia muito quente e o EPI incomoda. Ninguém está olhando. O que você faz?"

---

**4 — Comunicação e registro**
*(raiz: `qualidade` da cartilha + necessidade operacional real: vigia que não
sabe descrever ocorrência é problema concreto)*

| Nota | Âncora |
|---|---|
| **4** | Relata fato em ordem, com o essencial e sem invenção; quando não sabe algo, diz que não sabe. Descreve como registraria por escrito ou a quem comunicaria. |
| **3** | Consegue contar o que aconteceu de forma compreensível, mesmo sem organização perfeita. |
| **2** | Respostas muito curtas ou desorganizadas; precisa de várias perguntas para se fazer entender. |
| **1** | Não consegue relatar um fato simples de forma que se entenda; ou preenche lacunas com suposição apresentada como certeza. |

- **Comportamental:** "Conte o que aconteceu no seu último dia de trabalho, do começo ao fim."
- **Situacional:** "Você presencia uma discussão no hall e o supervisor pede um relato. O que você diz a ele?"

---

**Recomendação final** (uma, obrigatória):
`contratar` · `contratar_com_ressalva` · `banco_para_outra_vaga` ·
`nao_contratar`

`contratar_com_ressalva` e `banco_para_outra_vaga` **exigem** o campo de
motivo — sem ele, não salva.

**Tempo alvo de preenchimento: menos de 5 minutos.**

---

## 5. Arquitetura — o que se reusa e o que nasce

> Regra global do projeto (Bruno, 2026-08-04): *não reinventar a roda —
> reciclar padrões estabelecidos, preservando as particularidades.*

### 5.1 A descoberta que mudou o desenho

**Não existe candidatura no sistema.** A única FK entre `vaga` e `talento` em
todo o schema é `match_analise` (`models/match.py:104`), que é resultado de
processamento de IA — não estágio de processo seletivo. `StatusTalento` tem
exatamente 4 valores (`novo`, `em_analise`, `convertido`, `arquivado`) e é
**global da pessoa**, não por vaga.

A saída óbvia seria criar `Candidatura` e modelar
`Job → Stage → Application → Interview`, como os ATS fazem.

**Decisão: não criar.** A Green House não tem funil de cinco etapas — tem
"olhei o currículo" e "chamei para conversar". Em vez disso:

> **A entrevista carrega o vínculo.** Ela tem `vaga_id` e tem a pessoa. Se
> existe entrevista, existe vínculo; se não existe, não precisa existir —
> hoje já não existe e ninguém sentiu falta.

Duas entrevistas da mesma pessoa para a mesma vaga (triagem + presencial) são
duas linhas. Isso é o "stage" do ATS sem a tabela de stage.

### 5.2 Padrões reusados

| O quê | De onde | Por quê |
|---|---|---|
| **Identidade da pessoa** | mini-CRM (`models/crm.py:62`, `services/crm.py:20`) | Duas FKs opcionais `talento_id`/`candidato_id` + `escopo_pessoa`. A entrevista **segue a pessoa** de talento para candidato sem cópia. `FatoObservado` **não serve** — ele é `candidato_id` obrigatório, e entrevista é majoritariamente com talento. |
| **Instrumento** | Desempenho (`services/desempenho.py:108`, `api/desempenho.py:362`) | Constantes de módulo + rota de 3 linhas (`GET .../formulario`) + respostas em JSON `{chave: valor}`. **Zero tabela para o instrumento.** O front não duplica texto. |
| **Validação** | `desempenho.validar_respostas` / `completa` | Erros em linguagem de tela; `completa()` diz o que falta para enviar. |
| **Autor** | mini-CRM e Desempenho | `autor_id` (FK) **e** `autor_nome` (snapshot String) — o nome não some se o usuário for removido. |
| **Anexo** | `api/crm.py:160` | `ler_upload` (teto, allowlist, `close()` no `finally`), key `entrevistas/{id}/anexo.{ext}`. |
| **Listagem** | Desempenho (`api/desempenho.py:101`) | `{"itens": [...], "metricas": {...}}` alimenta os `cards` do DashPlanilha direto. |
| **Tela** | `DashPlanilha` | Colunas, `cards` clicáveis, `filtrosExtras`, `linhaExpandida` (painel abre **na linha**, nunca no fim da página). |
| **Select** | `SelectBusca` | Nunca `<select>` nativo — o `test_design_system.py` reprova no CI. |
| **Menu** | `RHApp.jsx:329` | Grupo **Recrutamento**, junto de Banco de Talentos e Match de Vagas. 3 edições: tripla em `GRUPOS`, import, linha no dispatch. |
| **Auditoria** | `services/auditoria.registrar` | Toda decisão com ator e detalhe, antes do commit. |
| **Retenção** | `workers/expurgo.py` | Já roda diariamente e já tem retenção configurável (telemetria, logs). Aqui **arquiva**, não apaga. |

### 5.3 O que NÃO se reusa, e por quê

- **Nenhum mecanismo de link público.** Os 9 que existem (`/c/`, `/t/`, `/p/`,
  `AcessoCreche`, `AcessoPortal`, `upload_token`, assinatura externa,
  `AutorizacaoEquipe`, KBA) ficam intocados. Só o RH logado entrevista.
- **Nenhum e-mail novo, na fase 1.** Sem lembrete ao candidato, sem convite de
  calendário. Se um dia entrar, nasce no `CATALOGO` de
  `services/email_templates.py` (regra da v2.21).
- **Nem `FatoObservado`, nem `Anotacao`.** A tentação é gravar entrevista como
  anotação do CRM. Não serve: anotação é texto livre sem estrutura, e o valor
  aqui está em nota ancorada comparável. A entrevista **escreve** uma anotação
  no CRM ao ser concluída (§ 5.5) — mas não *é* uma.

### 5.4 Território virgem: data futura

**Não existe agendamento em lugar nenhum do sistema.** Nada de compromisso,
`.ics`, slot, disponibilidade ou lembrete. Mais: `api/desempenho.py:124` e
`:694` **recusam data futura** ativamente (`data_futura` é erro de validação),
porque fato observado e feedback são sobre o passado.

A entrevista é a primeira entidade do sistema que precisa de data futura. O
único mecanismo com data futura que dispara algo hoje é
`workers/avisar_vencimentos.py`, varrendo `validade_ate` de certificado.

**Escopo da fase 1:** campo de data/hora marcada + lista de pendências. **Sem**
convite de calendário, **sem** lembrete automático, **sem** disponibilidade de
agenda. Isso é fase 3, se for pedido.

### 5.5 O modelo

```python
# models/entrevista.py

class TipoEntrevista(str, Enum):
    triagem = "triagem"       # checagem de viabilidade (telefone)
    entrevista = "entrevista" # avaliação ancarada (presencial/vídeo)

class StatusEntrevista(str, Enum):
    marcada    = "marcada"      # data futura, nada preenchido
    realizada  = "realizada"    # aconteceu e foi preenchida
    nao_veio   = "nao_veio"     # não compareceu
    remarcada  = "remarcada"    # terminal; gera uma nova linha
    cancelada  = "cancelada"
    arquivada  = "arquivada"    # 180 dias (§ 3.1) — sai da vista, não some

class Entrevista(Base):
    __tablename__ = "entrevista"

    id: UUID (PK)

    # A pessoa — padrão do mini-CRM: exatamente uma preenchida
    talento_id:   FK talento.id   | None
    candidato_id: FK candidato.id | None

    # O vínculo com a vaga (§ 5.1). NULLABLE de propósito:
    # entrevista exploratória sem vaga é cenário real.
    vaga_id: FK vaga.id | None  (ondelete=SET NULL)
    # Snapshot — a vaga pode ser excluída (§ 7, cenário 4)
    vaga_titulo: String(160) | None

    tipo:   Enum TipoEntrevista
    status: Enum StatusEntrevista  default marcada

    # Agenda
    marcada_para: DateTime tz | None   # None = nasceu já realizada
    realizada_em: DateTime tz | None
    local:        String(120) | None   # "presencial — sede", "telefone", "vídeo"

    # Quem conduziu — snapshot pelo padrão da casa
    entrevistador_id:   FK usuario_rh.id | None
    entrevistador_nome: String(200)  NOT NULL

    # TRIAGEM (tipo == triagem)
    triagem: JSON | None
    # {aceita_escala, aceita_salario, consegue_chegar,
    #  tem_interesse, recebe_seguro_desemprego}  -> "sim"|"nao"|"nao_sei"
    triagem_desfecho: String(20) | None   # segue | nao_segue | sem_contato

    # ENTREVISTA (tipo == entrevista)
    #   Mesmo padrão de Avaliacao.competencias — dict JSON, sem tabela por item
    competencias:  JSON | None   # {chave: 1..4}
    justificativas: JSON | None  # {chave: "texto"}  — obrigatória por nota
    variante:      String(20) | None  # comportamental | situacional (§ 2.2)
    recomendacao:  String(30) | None
    recomendacao_motivo: Text | None  # obrigatório em 2 das 4 recomendações

    observacao: Text | None
    anexo_key / anexo_nome / anexo_tipo   # padrão api/crm.py:160

    # Defasagem de preenchimento (§ 2.5) — derivada, exibida na tela
    preenchida_em: DateTime tz | None

    criada_em / criada_por
    arquivada_em: DateTime tz | None
```

**Uma tabela.** O instrumento (competências, âncoras, escalas, perguntas) vive
em `services/entrevistas.py` como constante de módulo — nunca no banco, pelo
mesmo motivo que a cartilha de desempenho não está: o front lê da API e não
duplica texto.

**Ao concluir uma entrevista, escreve-se uma `Anotacao` no mini-CRM** com o
resumo e o link — o histórico da pessoa continua num lugar só. É o mesmo
padrão de `api/talentos.py:428`, onde mudar status com motivo escreve
anotação em vez de criar campos próprios.

---

## 6. A camada que ninguém pediu: proteção jurídica

**Lei 9.029/95** veda prática discriminatória para acesso ao emprego por
sexo, origem, raça, cor, estado civil, **situação familiar**, deficiência,
reabilitação profissional e idade. Não se pode perguntar: é casada, tem
filhos, quem cuida das crianças, pretende engravidar, religião, posição
política, orientação sexual. Exigir atestado de gravidez ou esterilização é
**crime**; a multa administrativa é de 10× o maior salário pago, +50% na
reincidência.

A consequência de produto é uma linha só e ela reenquadra o módulo:

> **Campo de pergunta livre é risco jurídico. Roteiro pré-aprovado é defesa
> da empresa.**

Hoje o entrevistador pergunta o que quiser e não fica registro. Se alguém
perguntar *"você pretende engravidar?"* numa entrevista da Green House hoje,
não existe nem como saber que perguntou. Com roteiro fixo e aprovado, o que
foi perguntado está escrito e foi aprovado antes — o ônus se inverte.

**Isso muda como o módulo se justifica perante a diretoria:** não é "melhora
a contratação", é "reduz passivo trabalhista". É a mesma linguagem da
requisição de pessoal assinada.

**Implicação de desenho:** o campo `observacao` é livre, mas o **roteiro** não.
A tela mostra as perguntas do instrumento; não há campo "outras perguntas".

---

## 7. Cenários previstos

O Bruno pediu explicitamente: *"preveja diversos cenários"*.

| # | Cenário | Tratamento |
|---|---|---|
| 1 | **A pessoa não aparece** | `nao_veio`. Entra na lista de pendências até alguém fechar. Nunca inferido — ver #2. |
| 2 | **Passou da data e ninguém preencheu** | Vira **pendência que cobra** (decisão do Bruno). O sistema **pergunta, não conclui**: silêncio não é falta. Mesma lição do `00:00` no import de ponto, onde tratar registro incompleto como falta acusaria 28 pessoas injustamente. |
| 3 | **RH entrevistou sem ter marcado** | `marcada_para = None`, nasce direto em `realizada`. **Exigir agendamento prévio mataria o módulo** — pessoa que aparece na porta é rotina. |
| 4 | **A vaga é excluída depois** | `DELETE /rh/vagas/{id}` (`vagas.py:111`) é **delete físico e não usa lixeira**. Por isso: `ondelete=SET NULL` + `vaga_titulo` como snapshot. A entrevista sobrevive à vaga. **Recomendação adicional:** passar a exclusão de vaga pela lixeira (`services/lixeira.py`), como provas já fazem. |
| 5 | **Entrevista sem vaga** | `vaga_id` nullable. Conversa exploratória é caso real. |
| 6 | **A pessoa vira candidato no meio** | `converter()` seta `talento.candidato_id`; `escopo_pessoa` resolve o par. A entrevista continua apontando para o talento e **aparece na ficha do candidato**. Só funciona porque se usou o padrão do CRM — com FK única, quebraria. |
| 7 | **Duas entrevistas, mesma pessoa, mesma vaga** | Duas linhas. É o esperado (triagem → presencial). |
| 8 | **Dois avaliadores discordam** | Fora de escopo hoje (só o RH). Quando entrar: **mostrar as duas notas, nunca calcular média automática** — a média apaga o desacordo, que é o dado mais informativo. |
| 9 | **Pessoa reprovada volta meses depois** | Entrevista de mais de 180 dias fica **arquivada**: fora da vista e das métricas, acessível a quem procurar. |
| 10 | **Preenchido três dias depois** | Salva, e a tela **carimba a defasagem** ("preenchida 3 dias depois"). Não se proíbe — proibir faz o RH não registrar. |
| 11 | **Triagem por telefone de 6 minutos** | Ficha de checagem, sem nota. É a razão de existirem duas fichas. |
| 12 | **Pessoa recebendo seguro-desemprego** | Registrado na triagem, **nunca como critério de exclusão**. Explica falta e desistência. |
| 13 | **Divergência entre cadastro e triagem** (seguro-desemprego) | A triagem prevalece por ser mais recente; ambos ficam. A divergência é informação. |
| 14 | **Entrevista de quem já é colaborador** | Funciona (movimentação interna) — `candidato_id` preenchido, `talento_id` nulo. Não se arquiva por prazo: é parte do vínculo. |
| 15 | **Nota sem justificativa** | Não salva. 422 dizendo qual competência falta. |
| 16 | **Recomendação com ressalva sem motivo** | Não salva. |
| 17 | **Vaga com 30 posições (alocação)** | A tela por vaga lista todos os entrevistados; nada impede N recomendações `contratar`. |
| 18 | **RH quer comparar 3 candidatos** | Tela da vaga, uma linha por pessoa, 4 notas lado a lado + recomendação. É o cenário "filtrar". |
| 19 | **Entrevista remarcada** | `remarcada` é terminal e **gera nova linha**. O histórico de remarcações fica visível — remarcar 3× é informação. |
| 20 | **Anexo (currículo anotado, teste em papel)** | Padrão `api/crm.py:160` — `ler_upload`, allowlist, teto, `close()` no `finally`. |

---

## 8. Telas

Três, nenhuma nova em conceito — todas reusam `DashPlanilha`.

### 8.1 Menu: Recrutamento → 🗣️ Entrevistas

`RHApp.jsx:329`, junto de Banco de Talentos e Match de Vagas. Três edições:
tripla em `GRUPOS`, import do componente, linha no dispatch (~`:532`).
Telemetria e tour vêm de graça.

### 8.2 Lista de entrevistas (`/rh/entrevistas`)

`DashPlanilha` com:

- **Cards clicáveis:** `⚠ Aguardando desfecho` (o mais importante — cenário 2)
  · `Marcadas` · `Realizadas` · `Não compareceram` · `Total`
- **Colunas:** pessoa (com atalho para a memória do CRM) · vaga · tipo ·
  quando · entrevistador · desfecho/recomendação · nota média
- **Filtros:** vaga (`filtro: 'lista'`) · tipo · status · entrevistador ·
  período
- **`linhaExpandida`:** a ficha completa **abre na linha**, nunca no fim da
  página (regra desde a v1.83)
- **Ações em massa:** arquivar com motivo

### 8.3 Ficha da entrevista

Formulário servido por `GET /rh/entrevistas/formulario` — o front **não
duplica** competência, âncora nem pergunta. Padrão idêntico ao
`FormularioAvaliacao.jsx`.

Layout da avaliação, por competência:

```
CONFIABILIDADE E PRESENÇA
  Pergunta:  [comportamental ▾]
  "Conte uma vez em que você quase se atrasou. O que você fez?"

  ( )1  ( )2  (•)3  ( )4     [ver âncoras ▾]
  Justificativa: [_______________________]  ← obrigatória
```

As âncoras ficam num `<details>` — o `styles.css` já traz cursor, marcador e
margem (regra da v2.47.1); nada de `style` inline.

### 8.4 Na tela da vaga: comparação

Aba/seção em Match de Vagas mostrando os entrevistados daquela vaga, uma
linha por pessoa, 4 notas lado a lado + recomendação. É o que atende
"filtrar" e "alocar" (§ 3, decisão 2).

### 8.5 Na ficha da pessoa

Seção no `Detalhe.jsx` e no painel do dash de Talentos, ao lado da
`MemoriaPessoa` — histórico de entrevistas da pessoa, atravessando
talento↔candidato via `escopo_pessoa`.

---

## 9. Rotas

Router com `dependencies=[Depends(requer_rh)]`. **Literais antes de
paramétricas** (armadilha documentada em `api/crm.py:9`).

```
GET    /rh/entrevistas/formulario          # instrumento (3 linhas, não toca o banco)
GET    /rh/entrevistas                     # lista + métricas p/ os cards
GET    /rh/entrevistas/pendencias          # aguardando desfecho (cenário 2)
POST   /rh/entrevistas                     # marcar OU registrar já realizada
GET    /rh/entrevistas/{id}
PUT    /rh/entrevistas/{id}                # preencher (valida § 4)
POST   /rh/entrevistas/{id}/desfecho       # nao_veio | remarcada | cancelada
POST   /rh/entrevistas/{id}/anexo
GET    /rh/entrevistas/{id}/anexo
POST   /rh/entrevistas/{id}/arquivar
DELETE /rh/entrevistas/{id}                # via lixeira, com motivo
GET    /rh/vagas/{vaga_id}/entrevistas     # comparação (§ 8.4)
GET    /rh/pessoa/entrevistas              # ?talento_id= | ?candidato_id= (§ 8.5)
```

---

## 10. Fases

### Fase 1 — o esqueleto que funciona

Migration (`down_revision = "e7f8a9b0c1d2"`, o head atual) · modelo ·
`services/entrevistas.py` com o instrumento · rotas · tela de lista com
pendências · ficha de triagem · ficha de entrevista · anotação no CRM ao
concluir · auditoria.

**Entrega:** o RH marca, preenche, e nada mais se perde.

### Fase 2 — comparação e memória

Comparação na tela da vaga (§ 8.4) · histórico na ficha da pessoa (§ 8.5) ·
carimbo de defasagem · arquivamento automático aos 180 dias no
`workers/expurgo.py` · exclusão de vaga passando pela lixeira (cenário 4).

### Fase 3 — PEDIDA pelo Bruno em 2026-08-05 — **ENTREGUE na v2.66**

Ver § 14 — o desenho mudou de forma com quatro pedidos dele, e o maior deles
(roteiros múltiplos) **tirou as competências do código e as levou para o
banco**, o que resolveu a pendência nº 1 por outro caminho.

Os quatro entregues: roteiros múltiplos com rascunho→publicado e snapshot por
entrevista (§ 14.1) · quatro perguntas novas de triagem (§ 14.2) · tag de
reaproveitamento reusando o `PessoaTag` do mini-CRM (§ 14.3) · lembrete por
e-mail e convite `.ics` com UID estável, SEQUENCE e cancelamento (§ 14.4).
Cenários 21–30 cobertos por teste, com 9 mutações validadas. Execução em
`12b-entrevistas-relatorio-execucao.md`.

Continua **fora**: segundo avaliador com a trava anti-peeking (§ 2.6), porque
só o RH entrevista (decisão 1) e não há colega cuja nota espiar. E a exclusão
de vaga **continua sendo delete físico** — a entrevista sobrevive e a pessoa é
tagueada, mas se a vaga em si vai para a lixeira continua sendo decisão dele
(pendência nº 3).

---

## 11. Testes

Regra da casa: **todo teste novo é validado por mutação** — reintroduz-se o
defeito e confirma-se que o teste falha.

| Teste | Garantia |
|---|---|
| `test_entrevista_escopo_pessoa` | Entrevista feita com talento **aparece** na ficha do candidato após `converter()`. Mutação: trocar por FK única. |
| `test_entrevista_validacao` | Nota sem justificativa → 422 nomeando a competência. Recomendação com ressalva sem motivo → 422. |
| `test_entrevista_vaga_excluida` | Excluir a vaga **não** apaga a entrevista; `vaga_titulo` preserva o nome. |
| `test_entrevista_sem_agendamento` | Entrevista nasce em `realizada` sem `marcada_para`. |
| `test_entrevista_pendencias` | Passou da data e não preenchida → aparece em pendências. **Nunca** vira `nao_veio` sozinha. |
| `test_entrevista_arquivamento` | Aos 180 dias arquiva; o registro **continua existindo** e é consultável. Mutação: trocar arquivar por delete. |
| `test_entrevista_instrumento` | `GET /formulario` devolve as 4 competências com âncoras; o front não tem texto duplicado (estrutural, como `test_design_system.py`). |
| `test_entrevista_n_mais_1` | Listar N entrevistas não faz N consultas. Comparar duas listagens de tamanhos diferentes (nunca limite absoluto — mede o tamanho do banco). |
| Design system | `test_design_system.py` já reprova `<select>` nativo, classe fantasma e token inexistente. |

---

## 12. Pendências com o Bruno

1. ~~**Aprovar as 4 competências e as âncoras**~~ — **RESOLVIDA e ENTREGUE na
   v2.66**. Com roteiros múltiplos (§ 14.1) as competências saíram do código e
   viraram o **roteiro padrão no banco, editável pela tela** (Configurações →
   Roteiros de entrevista). Ele ajusta âncora, pergunta e competência sem deploy
   e sem esperar ninguém.
2. ~~**Confirmar as perguntas de triagem**~~ — **RESPONDIDA**: *"pode colocar
   mais, mas desde que sejam coerentes e coesas"* (§ 14.2). As 4 novas foram
   entregues na v2.66. **Nota:** elas continuam em CONSTANTE (só as
   competências viraram roteiro editável) — se ele quiser a triagem editável
   pela tela também, é pedido novo.
3. **Exclusão de vaga pela lixeira** — hoje é delete físico. Ele respondeu o
   que importava (§ 14.3: a entrevista sobrevive **e** a pessoa é tagueada para
   reaproveitamento), mas não disse se a vaga em si deve ir para a lixeira.
   **Continua aberta.**
4. **A entrevista de quem virou colaborador** (cenário 14) fica fora do prazo
   de arquivamento? A sala assumiu que sim. **Continua aberta.**

---

## 13. Fora de escopo, registrado

- **Requisição de Pessoal** — adiada por decisão do Bruno (2026-08-04:
  *"outra hora faremos isso"*). O desenho fica guardado: quando voltar, volta
  como **link para o demandante preencher** (com fallback de preenchimento
  assistido pelo RH, e o documento registrando que foi assistido — precedente
  da v2.56), não como formulário do RH. O problema declarado era *"a ideia era
  que o RH não preenchesse"*.
- **Currículo que chega por e-mail** — o Bruno pediu para não focar agora. O
  que a sala achou e vale registrar: **não existe rota para o RH cadastrar um
  talento à mão** (só o form público `talentos.py:155` e a importação de
  planilha `:710`). O pedido dele não é sobre e-mail — é sobre **a porta que
  não existe**. Uma rota e uma tela reusando o schema do form público
  destravam isso, e o e-mail vira só a fonte.
- **Gravação de entrevista** — exige consentimento próprio (§ 2.6).
- **Trava anti-peeking** — datada, não descartada (§ 2.6).

---

## 14. Fase 3 — o desenho (decisões do Bruno, 2026-08-05)

Quatro pedidos dele depois de ver a v2.64 rodando. Um deles reorganiza o
módulo; três são encaixes.

### 14.1 Roteiros múltiplos — o pedido que muda a forma

> *"poderiam haver vários modelos de roteiros já, para os mais variados níveis
> de senioridades e cargos que já temos, para que possamos escolher os roteiros
> mais adequadamente, bem como customizar roteiros para que sejam submetidos a
> aprovação e, após isso, poderem ser utilizados."*

Hoje o roteiro é **uma** constante de módulo em `services/entrevistas.py`. Vira
um **catálogo no banco**, com estas três decisões travadas:

**(a) Rascunho → publicado, o próprio RH publica.**

Roteiro nasce `rascunho` e **não pode ser usado em entrevista nenhuma**.
Publicar é ato separado e deliberado, com autor e data na auditoria.

Isso é o que sustenta o argumento jurídico do § 6: a defesa não é "existe um
roteiro", é **"o roteiro foi aprovado ANTES de ser usado"**. Sem a trava, o
argumento cai.

**Versão congelada:** publicar cria uma versão. Editar um roteiro publicado
gera a **versão seguinte** — a entrevista já feita continua mostrando o roteiro
com que foi feita, não o texto de hoje. É a mesma regra do snapshot de
`titulo_doc`/`corpo_doc` em `solicitacao_assinatura`: editar o modelo não muda
o que a pessoa assinou.

**(b) Escolha por cargo, com exceção por senioridade.**

Mesma herança que ele escolheu para salário (§ 13 do dump da 22ª leva) e que o
módulo de Desenvolvimento já usa em `meses_validade_de` — o mais específico
vence:

```
1. cargo + senioridade   ("Auxiliar Administrativo · pleno")
2. cargo                 ("Auxiliar Administrativo")
3. roteiro padrão        (as 4 competências de hoje)
```

**Sugerido, nunca imposto** — o RH troca na hora, e a entrevista guarda qual
roteiro foi usado.

**Cuidado herdado:** cargo é **texto livre** (`Candidato.cargo_funcao`), e a
base tem 87 pessoas em "AUXILIAR DE SERVIÇOS GERAIS" com dois CBOs distintos.
O casamento é por `normalizar_cargo` (minúsculo, sem acento) — a mesma função
do de-para do Tirvu. Cargo sem roteiro **cai no padrão**, nunca em erro.

**(c) As 4 competências viram o roteiro padrão, no banco.**

Saem de `services/entrevistas.py` e viram um registro `publicado`, usado quando
nenhum roteiro específico casa. **Isso resolve a pendência nº 1 por outro
caminho:** em vez de esperar aprovação das âncoras que a sala escreveu, o Bruno
passa a editá-las pela tela, sem deploy.

> **Consequência a não perder de vista:** o instrumento deixa de viver em
> constante e passa a viver em dado. A regra "o front lê da API e não duplica
> texto" continua valendo e continua coberta por teste estrutural — o que muda
> é a **fonte**, não o contrato. `GET /rh/entrevistas/formulario` passa a
> aceitar `?roteiro_id=` e a devolver o roteiro resolvido.

**Modelo:**

```python
class StatusRoteiro(str, Enum):
    rascunho  = "rascunho"
    publicado = "publicado"
    arquivado = "arquivado"   # aposentado; entrevistas antigas continuam legíveis

class RoteiroEntrevista(Base):
    __tablename__ = "roteiro_entrevista"
    id: UUID
    nome: String(120)                       # "Vigia — operacional"
    cargo: String(120) | None               # texto livre; None = padrão
    cargo_norm: String(120) | None indexado # normalizar_cargo(cargo)
    senioridade: String(20) | None          # None = vale para todas
    status: Enum StatusRoteiro
    versao: Integer                         # 1, 2, 3…
    competencias: JSON                      # [{chave, nome, ancoras{4..1}, perguntas{...}}]
    padrao: Boolean                         # o roteiro-raiz; não se apaga
    publicado_em / publicado_por            # o ATO de aprovação, auditado
    criado_em / criado_por
```

A `Entrevista` ganha `roteiro_id` (FK, `SET NULL`) **e** `roteiro_snapshot`
(JSON) — pelo mesmo motivo de `vaga_titulo`: o registro tem que continuar
legível se o roteiro for arquivado.

**Rotas:** `GET/POST /rh/roteiros-entrevista` · `PUT /{id}` (só rascunho) ·
`POST /{id}/publicar` · `POST /{id}/duplicar` · `POST /{id}/arquivar`.
Literais antes de paramétricas.

**Tela:** Configurações, junto dos outros catálogos (Tags, Modelos). Não é tela
de uso diário.

### 14.2 Mais perguntas de triagem

> *"pode colocar mais, mas desde que sejam coerentes e coesas"*

O critério é dele e é o certo: a triagem **não pode virar entrevista curta**
(§ 4.1). Toda pergunta nova tem que passar em três filtros:

1. Responde-se **sim/não/não sei** — se precisa de julgamento, é competência,
   não triagem.
2. Responde-se **por telefone em segundos**.
3. **Prediz desistência**, não desempenho.

Acréscimos propostos, todos dentro do critério:

| Campo | Pergunta | Por quê |
|---|---|---|
| `tem_disponibilidade_imediata` | Se aprovado, consegue começar em até 15 dias? | Distingue interesse de disponibilidade — a pessoa quer, mas só em março. |
| `tem_documentacao` | Está com CTPS, RG, CPF e comprovante de residência em mãos? | Documento pendente trava a admissão depois do sim. |
| `ja_trabalhou_no_cliente` | Já trabalhou neste posto ou para este cliente antes? | Há contratos com veto a recontratação; descobrir depois custa a vaga. |
| `aceita_uniforme_epi` | O posto exige uniforme e EPI. Tudo bem? | Recusa aparece no primeiro dia, não na entrevista. |

**Continua sem nota, sem competência, sem âncora.** Com nove perguntas de
sim/não o preenchimento segue abaixo de dois minutos.

### 14.3 Tag na pessoa quando a vaga é excluída

> *"quando excluir uma vaga, a entrevista sobrevive, pois posso poder taguear a
> pessoa, de modo que ela possa ser reaproveitada para outro cargo"*

Ele resolveu o cenário 4 melhor do que a sala tinha resolvido. A entrevista já
sobrevivia (com `vaga_titulo`), mas isso preservava **o registro**; o que ele
quer é preservar **a pessoa como oportunidade**.

E o sistema já tem a peça: `PessoaTag` do mini-CRM, com catálogo, CRUD e as
mesmas duas FKs opcionais que a entrevista usa. **Nada de campo novo.**

- **Ao excluir uma vaga**, o RH vê quantas pessoas foram entrevistadas para ela
  e pode aplicar uma tag em lote — sugerida a partir do cargo da vaga
  (ex.: `reaproveitar: vigia`), editável.
- A recomendação **`banco_para_outra_vaga`** (que já existe e já exige motivo)
  ganha o mesmo atalho: recomendou, oferece a tag.
- As tags já aparecem e filtram no dash de Talentos — o reaproveitamento
  funciona sem tela nova.

**Não é automático.** Tag aplicada sozinha vira ruído, e o RH deixa de
confiar na tag. O sistema propõe, o RH confirma — regra da casa.

### 14.4 Lembrete por e-mail e convite de calendário

> *"lembrete por email, sim. convite de calendário, sim. considere que pode ser
> entrevista online (pelo teams) ou presencial"*

**Modalidade** vira campo (`modalidade`: `presencial` | `online`), e ela decide
o conteúdo dos dois:

| | Presencial | Online (Teams) |
|---|---|---|
| Campo extra | `local` (endereço) | `link_reuniao` (URL) |
| E-mail diz | onde é, e o que levar | o link, e como entrar |
| `.ics` traz | `LOCATION` = endereço | `LOCATION` = link + no corpo |

**Lembrete por e-mail** — duas entradas novas no `CATALOGO` de
`services/email_templates.py` (regra da v2.21: e-mail novo nasce na sua
página, editável com preview e histórico):

- `entrevista_marcada` — no ato de marcar.
- `entrevista_lembrete` — na véspera, por worker.

**Variáveis obrigatórias:** `{{data_hora}}` e — conforme a modalidade —
`{{local}}` ou `{{link_reuniao}}`. Sem elas o e-mail sai bonito e inútil, e o
salvamento é recusado com 422 (mecânica que já existe).

**Só envia se houver e-mail.** Sem e-mail, o campo de lembrete fica desligado
e a tela diz por quê — nunca falha calada.

**Convite de calendário (`.ics`)** — arquivo gerado pelo servidor e anexado ao
e-mail. Três cuidados:

1. **`UID` estável por entrevista** + `SEQUENCE` incrementado a cada
   remarcação, e `METHOD:REQUEST` — é o que faz o Outlook **atualizar** o
   compromisso em vez de criar um segundo.
2. **Cancelamento manda `METHOD:CANCEL`** com o mesmo `UID`; senão o
   compromisso fica na agenda da pessoa depois de cancelado.
3. **`TZID=America/Sao_Paulo`**, nunca UTC solto — o container roda em UTC
   (armadilha da v2.41, que já mordeu no log) e o convite chegaria três horas
   adiantado.

Não há integração com a API do Teams: o link é **colado pelo RH**, como o
`wa.me` do Minutário. Integrar exigiria app registrado no tenant e OAuth
próprio, e o ganho não paga.

**Worker do lembrete:** roda junto do `avisar_vencimentos` (já existe, já é
cron, já tem anti-spam por auditoria). Não criar cron novo — é mais uma peça
para esquecer de subir no Portainer.

### 14.5 Cenários novos que a fase 3 abre

| # | Cenário | Tratamento |
|---|---|---|
| 21 | Roteiro editado depois de usado | Nova **versão**; a entrevista antiga mostra o roteiro com que foi feita (`roteiro_snapshot`). |
| 22 | Roteiro em rascunho | **Não aparece** para escolher. Publicar é ato explícito. |
| 23 | Cargo sem roteiro específico | Cai no **padrão**. Nunca erro, nunca tela vazia. |
| 24 | Roteiro arquivado com entrevistas antigas | As entrevistas seguem legíveis pelo snapshot. |
| 25 | Alguém tenta apagar o roteiro padrão | Recusa — `padrao=True` não se apaga; arquivar exige que exista outro padrão. |
| 26 | Pessoa sem e-mail | Lembrete desligado, **com o motivo na tela**. |
| 27 | Entrevista remarcada depois do convite | `.ics` novo com mesmo `UID` e `SEQUENCE+1`. |
| 28 | Entrevista cancelada depois do convite | `.ics` de cancelamento; sem isso fica na agenda. |
| 29 | Online sem link preenchido | Não deixa marcar como online sem link — o e-mail seria inútil. |
| 30 | Vaga excluída com 5 entrevistados | Oferece tag em lote; **o RH confirma**, nada automático. |

---

## Fontes

- [Sackett et al. (2022) — revisão dos validity coefficients](https://pubmed.ncbi.nlm.nih.gov/34968080/)
- [SIOP — sobre a revisão de Sackett](https://www.siop.org/tip-article/is-cognitive-ability-the-best-predictor-of-job-performance-new-research-says-its-time-to-think-again/)
- [Huffcutt et al. (2004) — situacional × comportamental por complexidade](https://onlinelibrary.wiley.com/doi/10.1111/j.0965-075X.2004.280_1.x)
- [Greenhouse — scorecard peeking (10M entrevistas)](https://www.greenhouse.com/guidance/how-scorecard-peeking-can-create-bias-in-hiring)
- [Greenhouse — structured hiring guide](https://support.greenhouse.io/hc/en-us/articles/360039539772-Structured-hiring-guide)
- [Gupy — entrevista estruturada (referência BR)](https://www.gupy.io/blog/entrevista-estruturada)
- [AIHR — Behaviorally Anchored Rating Scales](https://www.aihr.com/blog/behaviorally-anchored-rating-scale/)
- [Lei 9.029/95 — Planalto](https://www.planalto.gov.br/ccivil_03/leis/l9029.htm)
- [MPMG — cartilha sobre discriminação no trabalho](https://www.mpmg.mp.br/data/files/07/C7/6D/33/DA44A7109CEB34A7760849A8/Cartilha%20-%20Perguntas%20e%20respostas%20sobre%20discriminacao%20%20no%20trabalho.pdf)
- [ConJur — LGPD no recrutamento e seleção](https://www.conjur.com.br/2020-set-24/pratica-trabalhista-adequacao-lgpd-recrutamento-selecao-candidatos-emprego/)
