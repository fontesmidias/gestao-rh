"""O INSTRUMENTO da entrevista — competências, âncoras, escalas e perguntas.

⚠️ **A FONTE MUDOU NA v2.66. Leia antes de editar `COMPETENCIAS` abaixo.**

Até a v2.65 esta constante ERA o instrumento em runtime. Com os roteiros
múltiplos (§ 14.1), ela virou a **SEMENTE do roteiro padrão**: a migration
`a1c3e5b7d9f2` a copiou para a tabela `roteiro_entrevista` (`padrao=True`,
`status=publicado`), e é de lá que `GET /rh/entrevistas/formulario` lê hoje.
Editar `COMPETENCIAS` aqui **não muda mais nada em produção** — muda só o que
um banco novo receberia no primeiro `upgrade`. Quem edita o instrumento agora é
o Bruno, pela tela de Configurações → Roteiros de entrevista, sem deploy.

O que **não** mudou é o CONTRATO: o front continua lendo de
`GET /rh/entrevistas/formulario` e continua NÃO duplicando texto nenhum
(`test_entrevistas.py` varre o JSX e reprova a duplicação). Mudou a fonte, não
o contrato.

Três decisões de desenho que sustentam o resto:

1. **Escala 1–4, sem ponto médio** — de propósito. Com 1–5 o avaliador foge
   para o 3 e a nota não diz nada.
2. **Âncora comportamental (BARS)**: cada ponto da escala descreve um
   COMPORTAMENTO OBSERVÁVEL, não um adjetivo. A consequência de produto é a
   `justificativa obrigatória por competência` — nota sem frase ao lado é
   ruído, e `validar_preenchimento` recusa.
3. **Duas variantes da MESMA pergunta** (comportamental × situacional): a
   comportamental ("conte uma vez em que…") exige que a pessoa tenha uma
   história para contar, e não funciona com quem nunca trabalhou formalmente —
   primeiro emprego é fatia real nestes cargos. Nesse caso ela não mediria
   competência, mediria currículo. **A competência, a escala e a âncora são
   idênticas nas duas** — duas portas, mesma sala.

A TRIAGEM não tem nada disso de propósito (§ 4.1 do documento): é checagem de
viabilidade, não avaliação. Ver `PERGUNTAS_TRIAGEM`.
"""

# --------------------------------------------------------------------------
# Escala da entrevista
# --------------------------------------------------------------------------

ESCALA = [
    {"valor": 4, "rotulo": "4 — Evidência forte"},
    {"valor": 3, "rotulo": "3 — Atende"},
    {"valor": 2, "rotulo": "2 — Genérico, sem exemplo"},
    {"valor": 1, "rotulo": "1 — Contraindica"},
]

VALORES_VALIDOS = {e["valor"] for e in ESCALA}


# --------------------------------------------------------------------------
# As 4 competências (§ 4.2). Critério: (a) observável numa conversa de 20 min;
# (b) enraizada nos indicadores da cartilha de desempenho que o RH já aprovou,
# não inventada; (c) preditiva do que de fato derruba a permanência num posto.
#
# Quatro e não oito: com 15 competências preenche-se no automático; com 4,
# pensa-se. O teto antes da "fadiga de avaliação" é 8; para cargos operacionais
# o alvo é 4.
# --------------------------------------------------------------------------

COMPETENCIAS = [
    {
        "chave": "confiabilidade",
        "nome": "Confiabilidade e presença",
        "raiz": "indicadores `assiduidade` e `pontualidade` da cartilha",
        "ancoras": {
            4: ("Cita situação concreta em que se antecipou a um imprevisto "
                "(saiu mais cedo por chuva, greve, problema no transporte) e "
                "descreve como avisou o responsável com antecedência."),
            3: ("Descreve rotina de transporte compatível com o horário do "
                "posto; quando faltou, avisou antes e justificou."),
            2: ("Fala de pontualidade em termos genéricos (\"sou pontual\"), sem "
                "exemplo; admite atrasos ocasionais sem descrever como comunicou."),
            1: ("Relata faltas ou atrasos sem aviso; atribui a terceiros sem ação "
                "própria; não consegue descrever como chegaria ao posto."),
        },
        "perguntas": {
            "comportamental": ("Conte uma vez em que você quase se atrasou para o "
                               "trabalho. O que você fez?"),
            "situacional": ("Você começa às 6h e às 5h descobre que a linha de "
                            "ônibus está parada. O que você faz?"),
        },
    },
    {
        "chave": "trato_publico",
        "nome": "Trato com público e postura sob pressão",
        "raiz": "indicador `relacionamento` da cartilha",
        "ancoras": {
            4: ("Descreve situação real de conflito com público e como conduziu "
                "sem escalar: o que falou, a quem acionou, como terminou. Separa "
                "o problema da pessoa."),
            3: ("Descreve postura adequada (ouvir, não responder no mesmo tom, "
                "chamar o supervisor), com exemplo ainda que simples."),
            2: ("Diz que \"leva na boa\" ou \"não discuto\", sem descrever o que "
                "faz concretamente."),
            1: ("Relata revide, ironia ou abandono do posto; culpa o público; ou "
                "não consegue imaginar a situação."),
        },
        "perguntas": {
            "comportamental": ("Conte uma vez em que alguém falou com você de forma "
                               "ríspida no trabalho. O que aconteceu?"),
            "situacional": ("Um visitante insiste em entrar sem crachá e começa a "
                            "levantar a voz. O que você faz?"),
        },
    },
    {
        "chave": "norma_procedimento",
        "nome": "Cumprimento de norma e procedimento",
        "raiz": "indicadores `normas_epi` e `uniforme` da cartilha",
        "ancoras": {
            4: ("Cita norma ou procedimento específico de trabalho anterior e por "
                "que existia; descreve ocasião em que cumpriu mesmo sendo "
                "inconveniente."),
            3: ("Reconhece a existência de regras (EPI, uniforme, registro de "
                "ponto, livro de ocorrência) e diz cumprir, com exemplo."),
            2: ("Responde de forma genérica (\"sigo as regras\") sem citar nenhuma; "
                "trata norma como formalidade."),
            1: ("Relata ter contornado procedimento por conveniência e não vê "
                "problema nisso; ou desconhece o que é EPI no contexto do cargo."),
        },
        "perguntas": {
            "comportamental": ("Me conta uma regra do seu trabalho anterior que você "
                               "achava chata mas cumpria. Por que ela existia?"),
            "situacional": ("É um dia muito quente e o EPI incomoda. Ninguém está "
                            "olhando. O que você faz?"),
        },
    },
    {
        "chave": "comunicacao_registro",
        "nome": "Comunicação e registro",
        "raiz": ("`qualidade` da cartilha + necessidade operacional real: vigia que "
                 "não sabe descrever ocorrência é problema concreto"),
        "ancoras": {
            4: ("Relata fato em ordem, com o essencial e sem invenção; quando não "
                "sabe algo, diz que não sabe. Descreve como registraria por escrito "
                "ou a quem comunicaria."),
            3: ("Consegue contar o que aconteceu de forma compreensível, mesmo sem "
                "organização perfeita."),
            2: ("Respostas muito curtas ou desorganizadas; precisa de várias "
                "perguntas para se fazer entender."),
            1: ("Não consegue relatar um fato simples de forma que se entenda; ou "
                "preenche lacunas com suposição apresentada como certeza."),
        },
        "perguntas": {
            "comportamental": ("Conte o que aconteceu no seu último dia de trabalho, "
                               "do começo ao fim."),
            "situacional": ("Você presencia uma discussão no hall e o supervisor pede "
                            "um relato. O que você diz a ele?"),
        },
    },
]

CHAVES_COMPETENCIA = [c["chave"] for c in COMPETENCIAS]

VARIANTES = [
    {"chave": "comportamental", "rotulo": "Comportamental (tem experiência no cargo)"},
    {"chave": "situacional", "rotulo": "Situacional (primeiro emprego / sem experiência)"},
]


# --------------------------------------------------------------------------
# Recomendação final
# --------------------------------------------------------------------------

RECOMENDACOES = [
    {"chave": "contratar", "rotulo": "Contratar", "exige_motivo": False},
    {"chave": "contratar_com_ressalva", "rotulo": "Contratar com ressalva",
     "exige_motivo": True},
    {"chave": "banco_para_outra_vaga", "rotulo": "Banco para outra vaga",
     "exige_motivo": True},
    {"chave": "nao_contratar", "rotulo": "Não contratar", "exige_motivo": False},
]

# As duas que EXIGEM motivo. "Com ressalva" sem dizer qual ressalva não é
# recomendação, é impressão — e é exatamente o que o módulo existe para acabar.
RECOMENDACOES_COM_MOTIVO = {r["chave"] for r in RECOMENDACOES if r["exige_motivo"]}
CHAVES_RECOMENDACAO = {r["chave"] for r in RECOMENDACOES}


# --------------------------------------------------------------------------
# TRIAGEM (§ 4.1) — checagem de viabilidade. Sem nota, sem competência, sem
# âncora. O que derruba a contratação em terceirização raramente é
# incapacidade: é escala que não cabe na vida, local inacessível, salário
# abaixo do esperado.
# --------------------------------------------------------------------------

PERGUNTAS_TRIAGEM = [
    {"chave": "aceita_escala",
     "pergunta": "A escala é 12×36 noturno. Isso cabe na sua rotina?"},
    {"chave": "aceita_salario",
     "pergunta": "A remuneração é R$ X. Está de acordo?"},
    {"chave": "consegue_chegar",
     "pergunta": "O posto fica em <local>. Você consegue chegar no horário?"},
    {"chave": "tem_interesse",
     "pergunta": "Você ainda tem interesse nessa vaga?"},
    {"chave": "recebe_seguro_desemprego",
     "pergunta": "Você está recebendo seguro-desemprego hoje?",
     # Registrado porque EXPLICA falta e desistência, e porque o dado do
     # cadastro público pode ter oito meses. NUNCA é critério de exclusão:
     # recusar alguém por receber seguro-desemprego não é decisão do sistema.
     "nunca_exclui": True},

    # --- Acréscimos da v2.66 (§ 14.2) -------------------------------------
    # O critério é do Bruno e é o certo: *"pode colocar mais, desde que sejam
    # coerentes e coesas"*. A triagem NÃO pode virar entrevista curta. Toda
    # pergunta nova passou nos três filtros:
    #   1. responde-se sim/não/não sei — se exige julgamento, é competência;
    #   2. responde-se por telefone em segundos;
    #   3. prediz DESISTÊNCIA, não desempenho.
    # Com nove perguntas o preenchimento segue abaixo de dois minutos.
    {"chave": "tem_disponibilidade_imediata",
     "pergunta": "Se aprovado, você consegue começar em até 15 dias?"},
    {"chave": "tem_documentacao",
     "pergunta": "Está com CTPS, RG, CPF e comprovante de residência em mãos?"},
    {"chave": "ja_trabalhou_no_cliente",
     "pergunta": "Já trabalhou neste posto ou para este cliente antes?"},
    {"chave": "aceita_uniforme_epi",
     "pergunta": "O posto exige uniforme e EPI. Tudo bem para você?"},
]

CHAVES_TRIAGEM = [p["chave"] for p in PERGUNTAS_TRIAGEM]
RESPOSTAS_TRIAGEM = {"sim", "nao", "nao_sei"}

DESFECHOS_TRIAGEM = [
    {"chave": "segue", "rotulo": "Segue para entrevista"},
    {"chave": "nao_segue", "rotulo": "Não segue"},
    {"chave": "sem_contato", "rotulo": "Não consegui contato"},
]
CHAVES_DESFECHO_TRIAGEM = {d["chave"] for d in DESFECHOS_TRIAGEM}


# --------------------------------------------------------------------------
# Modalidade (v2.66, § 14.4) — decide o campo extra E o conteúdo do e-mail/.ics
# --------------------------------------------------------------------------

MODALIDADES = [
    {"chave": "presencial", "rotulo": "Presencial",
     "campo": "local", "rotulo_campo": "Endereço do local"},
    {"chave": "online", "rotulo": "Online (Teams)",
     "campo": "link_reuniao", "rotulo_campo": "Link da reunião"},
]
CHAVES_MODALIDADE = {m["chave"] for m in MODALIDADES}


# Retenção: 180 dias (decisão do Bruno). ARQUIVA, não apaga.
RETENCAO_PADRAO_DIAS = 180

# Lembrete da véspera: quantas horas antes o worker manda (§ 14.4). Roda junto
# do `avisar_vencimentos`, que já é cron e já tem anti-spam por auditoria — cron
# novo é mais uma peça para esquecer de subir no Portainer.
#
# ⚠️ **36h, não 24h — e o motivo é a CADÊNCIA do worker.** Ele dorme 86400s (24h)
# entre as passadas. Com janela de 24h exatos, a entrevista marcada para daqui a
# 23h fica INVISÍVEL: quando o worker acorda de novo, ela já aconteceu, e o
# lembrete nunca sai — falha silenciosa, porque nada acusa um e-mail que não foi
# enviado. A janela precisa ser maior que o intervalo entre as passadas, com
# folga. O anti-spam continua sendo o `lembrete_enviado_em`, não a janela: ela
# pode ser generosa sem virar repetição.
LEMBRETE_HORAS_ANTES = 36


# --------------------------------------------------------------------------
# ROTEIROS (v2.66, § 14.1) — o instrumento vive no BANCO; aqui mora a
# resolução por herança e a normalização do que entra.
# --------------------------------------------------------------------------

def normalizar_competencias(bruto) -> list[dict]:
    """Põe o instrumento no formato canônico, venha de onde vier.

    As âncoras são o ponto delicado: em Python a constante usa chaves INTEIRAS
    (`{4: "..."}`), mas JSON só tem chave de texto — o mesmo dado volta do banco
    como `{"4": "..."}`. Sem normalizar, `ancoras[4]` funcionaria na semente e
    devolveria `KeyError` no roteiro salvo pela tela, e o defeito só apareceria
    depois de alguém editar. Aqui tudo vira **texto**, dos dois lados.
    """
    saida = []
    for c in (bruto or []):
        if not isinstance(c, dict):
            continue
        chave = str(c.get("chave") or "").strip()
        nome = str(c.get("nome") or "").strip()
        if not chave or not nome:
            continue
        ancoras = {str(k): str(v) for k, v in (c.get("ancoras") or {}).items()}
        perguntas = {str(k): str(v) for k, v in (c.get("perguntas") or {}).items()}
        item = {"chave": chave, "nome": nome, "ancoras": ancoras,
                "perguntas": perguntas}
        if c.get("raiz"):
            item["raiz"] = str(c["raiz"])
        saida.append(item)
    return saida


# A semente do roteiro padrão, já no formato canônico. É o que a migration
# grava e o que um banco novo recebe.
COMPETENCIAS_PADRAO = normalizar_competencias(COMPETENCIAS)

NOME_ROTEIRO_PADRAO = "Roteiro padrão — cargos operacionais"


def normalizar_perguntas(bruto) -> list[dict]:
    """As perguntas do roteiro de TRIAGEM, no formato canônico (v2.67).

    Aceita `{chave, pergunta, nunca_exclui?}`. A chave é gerada a partir do
    texto quando não vem — o RH escreve a pergunta, não um identificador.

    **Nota, âncora e competência são DESCARTADAS aqui, em silêncio deliberado**:
    o que recusa com mensagem é `validar_roteiro`, na gravação. Este normalizador
    é usado também na LEITURA (dado antigo, dado editado à mão no banco), e
    deixar passar um campo de nota na leitura faria a tela desenhar um seletor de
    nota numa triagem — que é a fronteira do § 4.1.
    """
    saida, vistas = [], set()
    for p in (bruto or []):
        if isinstance(p, str):
            p = {"pergunta": p}
        if not isinstance(p, dict):
            continue
        texto = str(p.get("pergunta") or "").strip()
        if not texto:
            continue
        chave = str(p.get("chave") or "").strip()
        if not chave:
            from app.services.export_tirvu import normalizar_cargo
            base = normalizar_cargo(texto)[:40].replace(" ", "_").strip("_")
            chave = base or f"pergunta_{len(saida) + 1}"
        # Chave repetida sobrescreveria a resposta da anterior no JSON da
        # triagem — duas perguntas, uma resposta, sem erro nenhum na tela.
        if chave in vistas:
            sufixo = 2
            while f"{chave}_{sufixo}" in vistas:
                sufixo += 1
            chave = f"{chave}_{sufixo}"
        vistas.add(chave)
        item = {"chave": chave, "pergunta": texto}
        if p.get("nunca_exclui"):
            item["nunca_exclui"] = True
        saida.append(item)
    return saida


# A semente do roteiro de triagem padrão: as 9 perguntas de hoje.
PERGUNTAS_PADRAO = normalizar_perguntas(PERGUNTAS_TRIAGEM)

NOME_TRIAGEM_PADRAO = "Triagem padrão — checagem de viabilidade"

# Campos que denunciam uma triagem virando avaliação. Ficam numa constante
# porque a mesma lista é cobrada na validação E no teste estrutural — escrita
# duas vezes, divergiriam na primeira alteração.
CAMPOS_PROIBIDOS_TRIAGEM = ("ancoras", "nota", "notas", "escala", "competencia",
                            "competencias", "peso")


def validar_roteiro_triagem(nome: str | None, perguntas) -> list[str]:
    """Erros do roteiro de TRIAGEM, em linguagem de tela (v2.67, § 15.5 item 3).

    Duas regras, e as duas são de natureza, não de forma:

    - **Triagem publicada precisa de ao menos uma pergunta** (cenário 35):
      checagem vazia não é checagem — seria um registro que afirma ter havido
      triagem sem nada perguntado.
    - **Nada de âncora, nota, escala, peso ou competência.** É o § 4.1 e a
      decisão 3 do Bruno. Tornar as perguntas editáveis não pode ser a porta
      pela qual a triagem vira entrevista curta; o erro NOMEIA o campo que
      apareceu, porque "roteiro inválido" faria o RH procurar no escuro.
    """
    erros = []
    if not (nome or "").strip():
        erros.append("Dê um nome ao roteiro de triagem.")
    for p in (perguntas or []):
        if not isinstance(p, dict):
            continue
        achados = sorted(c for c in CAMPOS_PROIBIDOS_TRIAGEM if p.get(c))
        if achados:
            erros.append(
                f"'{str(p.get('pergunta') or '')[:40]}': triagem não tem "
                f"{', '.join(achados)}. Ela é checagem de viabilidade — quem "
                "avalia com nota e âncora é a entrevista.")
    if not normalizar_perguntas(perguntas):
        erros.append("A triagem precisa de ao menos uma pergunta — checagem "
                     "sem pergunta não é checagem.")
    return erros


def resolver_triagem(db, roteiro_id=None):
    """O roteiro de triagem que vale. Só PUBLICADO; None cai nas perguntas-semente.

    Mais simples que `resolver_roteiro` de propósito: triagem não herda por
    cargo. As perguntas ("aceita a escala?", "consegue chegar?") valem para
    qualquer posto — o que muda entre cargos é a RESPOSTA, não a pergunta.
    Herança aqui seria complexidade sem caso de uso.
    """
    from sqlalchemy import select

    from app.models.roteiro_entrevista import (RoteiroEntrevista, StatusRoteiro,
                                               TipoRoteiro)

    pub = RoteiroEntrevista.status == StatusRoteiro.publicado.value
    tri = RoteiroEntrevista.tipo == TipoRoteiro.triagem.value

    if roteiro_id:
        r = db.get(RoteiroEntrevista, roteiro_id)
        if (r is not None and r.status == StatusRoteiro.publicado.value
                and r.tipo == TipoRoteiro.triagem.value):
            return r
    return db.scalar(select(RoteiroEntrevista).where(pub, tri)
                     .order_by(RoteiroEntrevista.padrao.desc(),
                               RoteiroEntrevista.versao.desc()))


def validar_roteiro(nome: str | None, competencias) -> list[str]:
    """Erros de cadastro do roteiro, em linguagem de tela.

    O piso é baixo de propósito (nome + ao menos uma competência com nome e
    âncoras): o roteiro nasce RASCUNHO e o que impede um instrumento pela
    metade de ser usado é a publicação, não o salvamento. Travar a digitação
    faria o RH perder o texto no meio.
    """
    erros = []
    if not (nome or "").strip():
        erros.append("Dê um nome ao roteiro.")
    itens = normalizar_competencias(competencias)
    if not itens:
        erros.append("O roteiro precisa de ao menos uma competência com nome.")
    chaves = [c["chave"] for c in itens]
    if len(chaves) != len(set(chaves)):
        erros.append("Há competências com a mesma chave — cada uma precisa da sua.")
    for c in itens:
        faltam = [n for n in ("1", "2", "3", "4") if not (c["ancoras"].get(n) or "").strip()]
        if faltam:
            erros.append(
                f"'{c['nome']}': faltam as âncoras das notas {', '.join(faltam)}. "
                "Nota sem âncora descrita vira adjetivo, que é o que o roteiro "
                "existe para substituir.")
        if not (c["perguntas"].get("comportamental") or "").strip():
            erros.append(f"'{c['nome']}': falta a pergunta comportamental.")
        if not (c["perguntas"].get("situacional") or "").strip():
            erros.append(
                f"'{c['nome']}': falta a pergunta situacional — sem ela, quem "
                "nunca trabalhou formalmente fica sem pergunta que sirva.")
    return erros


def resolver_roteiro(db, *, cargo: str | None = None,
                     senioridade: str | None = None,
                     roteiro_id=None):
    """O roteiro que vale para este cargo. **Nunca levanta, nunca devolve nada.**

    Ordem de precedência (o mais específico vence — a mesma herança de
    `meses_validade_de` no módulo de Desenvolvimento):

        1. `roteiro_id` explícito, se PUBLICADO       (o RH escolheu na hora)
        2. cargo + senioridade                        ("Vigia · pleno")
        3. cargo                                      ("Vigia")
        4. o roteiro `padrao`                          (o piso do sistema)

    **Só entra roteiro PUBLICADO** (cenário 22): rascunho não aparece para
    escolher, e é essa trava que sustenta o "aprovado ANTES de ser usado".
    Passar um `roteiro_id` de rascunho não é erro aqui — cai na herança, e quem
    precisa recusar explicitamente é a rota de gravação, com 422 que explica.

    **Cargo sem roteiro cai no padrão, NUNCA em erro** (cenário 23): 87 pessoas
    na base compartilham um cargo escrito de três formas, e nenhuma entrevista
    pode abrir sem instrumento por causa de um cadastro que ninguém fez.
    """
    from sqlalchemy import select

    from app.models.roteiro_entrevista import (RoteiroEntrevista, StatusRoteiro,
                                               TipoRoteiro)

    # **Só roteiro de ENTREVISTA** (v2.67): com a triagem no mesmo catálogo, um
    # roteiro de triagem publicado poderia virar o fundo da herança e a ficha de
    # entrevista abriria com perguntas de viabilidade e nenhuma competência —
    # sem erro nenhum na tela, que é o pior desfecho.
    pub = ((RoteiroEntrevista.status == StatusRoteiro.publicado.value)
           & (RoteiroEntrevista.tipo == TipoRoteiro.entrevista.value))

    if roteiro_id:
        r = db.get(RoteiroEntrevista, roteiro_id)
        if (r is not None and r.status == StatusRoteiro.publicado.value
                and (getattr(r, "tipo", None)
                     or TipoRoteiro.entrevista.value) == TipoRoteiro.entrevista.value):
            return r

    from app.services.export_tirvu import normalizar_cargo
    chave = normalizar_cargo(cargo) if cargo else ""
    sen = (senioridade or "").strip().lower() or None

    if chave:
        if sen:
            r = db.scalar(
                select(RoteiroEntrevista).where(
                    pub, RoteiroEntrevista.cargo_norm == chave,
                    RoteiroEntrevista.senioridade == sen)
                .order_by(RoteiroEntrevista.versao.desc()))
            if r is not None:
                return r
        # Sem senioridade declarada, ou sem roteiro para ela: o do cargo, que
        # vale para todas (`senioridade IS NULL`).
        r = db.scalar(
            select(RoteiroEntrevista).where(
                pub, RoteiroEntrevista.cargo_norm == chave,
                RoteiroEntrevista.senioridade.is_(None))
            .order_by(RoteiroEntrevista.versao.desc()))
        if r is not None:
            return r

    r = db.scalar(
        select(RoteiroEntrevista)
        .where(pub, RoteiroEntrevista.padrao.is_(True))
        .order_by(RoteiroEntrevista.versao.desc()))
    if r is not None:
        return r

    # ---- REDE DE SEGURANÇA: o fundo da herança sumiu ----
    #
    # Não deveria acontecer — as rotas recusam arquivar e excluir o padrão
    # (cenário 25). Mas "não deveria" não é garantia: o `padrao` é uma coluna
    # booleana que uma migration futura, um acerto no banco ou um roteiro
    # editado podem deixar sem nenhum registro publicado marcado. Foi
    # exatamente o que aconteceu ao rodar as mutações desta leva: a mutação que
    # removia o guard ARQUIVOU o padrão, e o estado do banco sobreviveu à
    # restauração do código — a partir dali TODA entrevista abriria sem
    # instrumento.
    #
    # Sem esta rede, o sintoma seria uma ficha vazia sem erro nenhum: o pior
    # desfecho possível, porque a tela parece funcionar e a entrevista é
    # conduzida sem roteiro — que é justamente o que o § 6 existe para impedir.
    # Então: qualquer roteiro PUBLICADO sem cargo serve de fundo; na falta de
    # todos, a constante-semente entra por `formulario()`, que já cai nela
    # quando recebe None.
    return db.scalar(
        select(RoteiroEntrevista)
        .where(pub, RoteiroEntrevista.cargo_norm.is_(None))
        .order_by(RoteiroEntrevista.versao.desc()))


def dump_roteiro(r) -> dict:
    from app.models.roteiro_entrevista import StatusRoteiro, TipoRoteiro

    tipo = getattr(r, "tipo", None) or TipoRoteiro.entrevista.value
    return {
        "id": r.id, "nome": r.nome,
        "cargo": r.cargo, "senioridade": r.senioridade,
        "status": r.status, "versao": r.versao,
        "tipo": tipo,
        "competencias": normalizar_competencias(r.competencias),
        "perguntas": normalizar_perguntas(r.perguntas),
        # Só o PUBLICADO vira documento (cenário 33). A tela usa isto para não
        # oferecer um botão que responderia 409 — dizer antes é melhor que
        # recusar depois.
        "tem_documento": r.status == StatusRoteiro.publicado.value,
        "padrao": r.padrao,
        "publicado_em": r.publicado_em, "publicado_por": r.publicado_por,
        "criado_em": r.criado_em, "criado_por": r.criado_por,
        "arquivado_em": r.arquivado_em,
    }


def snapshot_do_roteiro(r) -> dict | None:
    """O que fica gravado NA ENTREVISTA (§ 14.1, decisão (a)).

    Guarda o instrumento inteiro, não uma referência: o roteiro pode ser
    editado (nova versão) ou arquivado depois, e a entrevista tem que continuar
    dizendo com que perguntas e âncoras aquela nota foi dada. Ler do roteiro
    vivo mostraria o texto de HOJE numa avaliação de meses atrás — e a nota
    deixaria de significar o que significava (cenários 21 e 24).
    """
    if r is None:
        return None
    return {"id": str(r.id), "nome": r.nome, "versao": r.versao,
            "cargo": r.cargo, "senioridade": r.senioridade,
            "competencias": normalizar_competencias(r.competencias)}


def formulario(competencias=None, perguntas=None) -> dict:
    """Tudo que o front precisa para desenhar as duas fichas.

    `competencias` vem do ROTEIRO resolvido (v2.66) e `perguntas` do roteiro de
    TRIAGEM (v2.67). Sem eles — banco novo antes da semente, ou roteiro vazio —
    caem nas constantes-semente, para a tela nunca abrir vazia. O front NÃO
    duplica competência, âncora nem pergunta; é o que `test_entrevista_instrumento`
    cobra estruturalmente varrendo o JSX.
    """
    itens = normalizar_competencias(competencias) or COMPETENCIAS_PADRAO
    da_triagem = normalizar_perguntas(perguntas) or PERGUNTAS_PADRAO
    return {
        "escala": ESCALA,
        "competencias": itens,
        "variantes": VARIANTES,
        "recomendacoes": RECOMENDACOES,
        "triagem": {
            "perguntas": da_triagem,
            "respostas": sorted(RESPOSTAS_TRIAGEM),
            "desfechos": DESFECHOS_TRIAGEM,
        },
    }


def validar_triagem(triagem: dict | None, desfecho: str | None,
                    perguntas=None) -> list[str]:
    """Erros de preenchimento da triagem, em linguagem de tela. Vazio = pode
    salvar. A triagem é deliberadamente permissiva: "não sei" é resposta
    legítima, e a linha livre é opcional.

    `perguntas` é o roteiro de triagem daquela ficha (v2.67): valida-se contra o
    que a tela mostrou. Validar sempre contra a constante faria a resposta de uma
    pergunta CRIADA pelo RH ser recusada como "pergunta desconhecida" — o
    catálogo seria editável e não preenchível, que é o mesmo defeito que a
    validação por constante já tinha causado nas competências.
    """
    erros = []
    validas = {p["chave"] for p in normalizar_perguntas(perguntas)} or set(CHAVES_TRIAGEM)
    for chave, valor in (triagem or {}).items():
        if chave not in validas:
            erros.append(f"Pergunta de triagem desconhecida: '{chave}'.")
        elif valor not in RESPOSTAS_TRIAGEM:
            erros.append(
                f"Resposta inválida em '{chave}': use sim, nao ou nao_sei.")
    if desfecho is not None and desfecho not in CHAVES_DESFECHO_TRIAGEM:
        erros.append(f"Desfecho de triagem inválido: '{desfecho}'.")
    return erros


def _nomes_das_competencias(instrumento=None) -> dict:
    """{chave: nome} do instrumento com que a entrevista foi feita.

    `instrumento` é a lista de competências do ROTEIRO (v2.66). Sem ele, vale a
    semente. Validar sempre contra a constante faria a nota de um roteiro
    customizado ser recusada como "competência desconhecida" — o roteiro do RH
    seria cadastrável e não preenchível.
    """
    itens = normalizar_competencias(instrumento) or COMPETENCIAS_PADRAO
    return {c["chave"]: c["nome"] for c in itens}


def validar_entrevista(competencias: dict | None, justificativas: dict | None,
                       recomendacao: str | None,
                       recomendacao_motivo: str | None,
                       instrumento=None) -> list[str]:
    """Erros de preenchimento da avaliação, em linguagem de tela.

    Duas regras que NÃO devem ser afrouxadas:

    - **Nota sem justificativa não salva** (§ 2.3): âncora comportamental sem
      evidência escrita é o mesmo ruído que o módulo veio substituir. O erro
      NOMEIA a competência que falta — "faltou justificativa" genérico faria o
      RH procurar qual das quatro.
    - **`contratar_com_ressalva` e `banco_para_outra_vaga` exigem motivo**.

    `instrumento` é o roteiro daquela entrevista (v2.66): valida-se contra o
    que a ficha mostrou, não contra a constante.
    """
    erros = []
    nomes = _nomes_das_competencias(instrumento)

    for chave, valor in (competencias or {}).items():
        if chave not in nomes:
            erros.append(f"Competência desconhecida: '{chave}'.")
        elif valor not in VALORES_VALIDOS:
            erros.append(f"Nota inválida em '{nomes[chave]}': use 1 a 4.")

    # A justificativa é cobrada por NOTA DADA — competência ainda não avaliada
    # não cobra nada (o RH pode salvar um rascunho parcial).
    for chave, valor in (competencias or {}).items():
        if chave not in nomes or valor not in VALORES_VALIDOS:
            continue
        texto = ((justificativas or {}).get(chave) or "").strip()
        if not texto:
            erros.append(f"Justifique a nota de '{nomes[chave]}'.")

    if recomendacao is not None:
        if recomendacao not in CHAVES_RECOMENDACAO:
            erros.append(f"Recomendação inválida: '{recomendacao}'.")
        elif (recomendacao in RECOMENDACOES_COM_MOTIVO
                and not (recomendacao_motivo or "").strip()):
            rotulo = next(r["rotulo"] for r in RECOMENDACOES
                          if r["chave"] == recomendacao)
            erros.append(f"'{rotulo}' exige o motivo.")
    return erros


def completa_entrevista(competencias: dict | None,
                        recomendacao: str | None,
                        instrumento=None) -> list[str]:
    """O que falta para a entrevista poder ser CONCLUÍDA (status realizada).

    Salvar rascunho parcial continua permitido — o que não se permite é fechar
    a avaliação pela metade. A cobrança é sobre as competências DAQUELE roteiro
    (v2.66): um roteiro de 6 competências cobra as 6, um de 3 cobra as 3.
    """
    faltando = []
    respondidas = set((competencias or {}).keys())
    nomes = _nomes_das_competencias(instrumento)
    if not respondidas >= set(nomes):
        faltam = [nome for chave, nome in nomes.items() if chave not in respondidas]
        faltando.append("competências sem nota: " + ", ".join(faltam))
    if not (recomendacao or "").strip():
        faltando.append("recomendação final")
    return faltando


def media(competencias: dict | None) -> float | None:
    """Média 1–4 das competências pontuadas. Sem competência, sem média (None,
    nunca 0 — zero seria uma nota, e a ausência de nota não é nota baixa)."""
    if not competencias:
        return None
    notas = [v for v in competencias.values() if v in VALORES_VALIDOS]
    return round(sum(notas) / len(notas), 2) if notas else None


def defasagem_dias(realizada_em, preenchida_em) -> int | None:
    """Quantos dias separam a entrevista do preenchimento (§ 2.5).

    Existe porque quem preenche no dia seguinte RECONSTRÓI em vez de lembrar. A
    resposta não é proibir (o RH deixaria de registrar), é CARIMBAR na tela.
    """
    if realizada_em is None or preenchida_em is None:
        return None
    dias = (preenchida_em - realizada_em).days
    return dias if dias > 0 else 0
