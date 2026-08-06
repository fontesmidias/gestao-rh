"""Os três documentos do Módulo de Entrevistas (v2.67, § 15.2).

- **Ficha de entrevista preenchida** (`hibrido`) — pessoa, vaga, roteiro USADO
  com a versão, as notas com justificativa, recomendação e quem conduziu. É a
  peça que sustenta o § 6 do documento: sem ela, *"o roteiro foi aprovado antes
  de ser usado"* é afirmação sem prova anexável.
- **Ficha de triagem preenchida** (`formulario`) — as respostas e o desfecho.
- **Roteiro publicado** (`hibrido`) — competências, âncoras e perguntas, com
  versão, quem publicou e quando. Até aqui o roteiro pré-aprovado só existia na
  tela; o documento é o que se anexa a uma defesa.

Reusa o `_OficioPDF` das fichas (timbrado, marca d'água, rodapé) pelo mesmo
motivo que o `creche_pdf` reusa: papel timbrado é identidade da empresa, e
redesenhá-lo aqui faria dois timbrados divergirem na primeira mudança de marca.


Cuidados que este módulo paga, e o defeito que cada um evita
-----------------------------------------------------------
**1. Nenhum gerador existente é substituído** (regra da v2.19). Estes são
documentos NOVOS, com geradores novos. O hash do ato de assinatura é calculado
sobre o PDF gerado — trocar um gerador antigo por template faria todo manifesto
já emitido apontar para um hash que não se reproduz.

**2. Data SEMPRE por `_data_hora`, nunca crua.** A v2.55 mordeu exatamente
aqui: o requerimento do creche imprimiu `2022-10-19` num documento oficial em
português, assinado, e a extração de texto do teste passou — só apareceu ao
transformar o PDF em imagem e olhar. Aqui as datas são `datetime` de verdade
(não a string de dois formatos do creche), mas a regra que fica é a mesma: uma
função só formata data no documento, e ela converte para a hora de **Brasília**
— o container roda em UTC (armadilha da v2.41) e uma entrevista das 8h sairia
impressa como 11h.

**3. Ficha INCOMPLETA não vira documento** (cenário 32). `erros_para_documento`
recusa antes de desenhar qualquer página: um PDF com competência sem nota, ou
sem recomendação, é prova CONTRA a empresa — parece registro formal e mostra
avaliação pela metade. Recusar com a lista do que falta é a única resposta útil.

**4. O texto vem do SNAPSHOT da entrevista, não do roteiro vivo.** Ler o roteiro
de hoje para imprimir uma entrevista de meses atrás mostraria âncoras que não
foram as usadas — e a nota deixaria de significar o que significava (cenários 21
e 24).
"""
from __future__ import annotations

import uuid as _uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.services import entrevistas as inst
from app.services.fichas import _OficioPDF

# Id fixo e reconhecível da amostra — o mesmo truque do `_candidato_de_amostra`
# (`...0000ff`). Fixo para que a prévia seja reproduzível; reconhecível para que
# um registro com este id no banco denuncie na hora que a amostra vazou.
_UUID_AMOSTRA = _uuid.UUID("00000000-0000-0000-0000-0000000000e7")

# Rótulos das respostas de triagem. O PDF é lido por quem não conhece o sistema
# (advogado, auditor, o próprio candidato num litígio): `nao_sei` cru numa peça
# formal é ruído, e "—" esconderia que a pergunta foi feita.
_RESPOSTA_TRIAGEM = {"sim": "Sim", "nao": "Não", "nao_sei": "Não sei / não respondeu"}

_DESFECHO_TRIAGEM = {d["chave"]: d["rotulo"] for d in inst.DESFECHOS_TRIAGEM}
_RECOMENDACAO = {r["chave"]: r["rotulo"] for r in inst.RECOMENDACOES}
_VARIANTE = {v["chave"]: v["rotulo"] for v in inst.VARIANTES}
_MODALIDADE = {m["chave"]: m["rotulo"] for m in inst.MODALIDADES}


def _brasilia(dt: datetime) -> datetime:
    """UTC-3 na mão — a mesma escolha (e o mesmo motivo) de `entrevista_convite`
    e `calendario`: a imagem é slim e a base de fusos do sistema não é
    garantida, então um `ZoneInfo` ausente levantaria dentro da geração do PDF.
    """
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc) - timedelta(hours=3)


def _data_hora(dt: datetime | None) -> str:
    """`12/08/2026 às 14:00`, hora de Brasília. Vazio vira travessão, NUNCA a
    data de hoje: imprimir o dia da geração no lugar de um campo em branco
    inventaria um fato dentro de um documento formal."""
    return f"{_brasilia(dt).strftime('%d/%m/%Y às %H:%M')}" if dt else "—"


def _data(dt: datetime | None) -> str:
    return f"{_brasilia(dt).strftime('%d/%m/%Y')}" if dt else "—"


def _secao_junta(pdf, nome: str, altura_minima: float = 34) -> None:
    """Faixa de seção que NÃO fica órfã no pé da página.

    Defeito real, encontrado olhando o PDF RENDERIZADO (não a extração de
    texto, que passava): a faixa "COMPETÊNCIA: CUMPRIMENTO DE NORMA E
    PROCEDIMENTO" caía na última linha da página 1 e a tabela dela abria na
    página 2 — um título de seção separado do próprio conteúdo, que num
    documento de duas páginas parece erro de montagem.

    O `set_auto_page_break` do fpdf quebra por ELEMENTO: ele garante que a faixa
    caiba, não que caiba a faixa MAIS a primeira linha do que vem depois. Por
    isso a checagem é explícita — reserva-se espaço para o bloco, não para o
    título. É a mesma técnica que o `campo()` das fichas já usa (`if self.get_y()
    + altura > self.h - 26`).
    """
    if pdf.get_y() + altura_minima > pdf.h - 26:
        pdf.add_page()
    pdf.secao(nome)


def _rotulo(mapa: dict, chave, vazio: str = "—") -> str:
    """Rótulo legível, caindo no PRÓPRIO valor quando o mapa não o conhece.

    Cair no valor (e não em "—") importa: um roteiro do RH pode ter competência
    que a constante não conhece, e imprimir travessão apagaria do documento uma
    resposta que existe. O documento mostra o que foi respondido, mesmo feio.
    """
    if not chave:
        return vazio
    return mapa.get(chave) or str(chave).replace("_", " ").capitalize()


# ---------------------------------------------------------------------------
# Amostra para a PRÉVIA do catálogo (§ 15.2)
# ---------------------------------------------------------------------------

# Nome fictício óbvio. Segue a escolha do `_candidato_de_amostra` de
# `api/modelos.py` ("Maria de Exemplo Souza"): a prévia mostra o documento com
# cara de documento em vez de uma folha de `{{variáveis}}`, e sem expor dado de
# gente real a quem só quer conferir o layout.
PESSOA_AMOSTRA = "João de Exemplo Ribeiro"


def entrevista_de_amostra(tipo: str = "entrevista"):
    """Entrevista FICTÍCIA, só em memória, para a prévia do catálogo.

    **Nunca vai ao banco** — `db.add` jamais é chamado, e o objeto nem sequer é
    anexado a uma sessão. É a mesma garantia do `_candidato_de_amostra`, e ela
    importa mais aqui: uma entrevista de amostra que vazasse para a tabela
    apareceria na fila de pendências do RH, com notas inventadas sobre uma
    pessoa que não existe.

    Os dados são plausíveis de propósito (notas variadas, uma justificativa
    real, uma ressalva com motivo): é assim que se vê se o layout aguenta texto
    de verdade — âncora longa, justificativa de três linhas.
    """
    from app.models.entrevista import Entrevista, StatusEntrevista, TipoEntrevista

    agora = datetime.now(timezone.utc)
    e = Entrevista()
    e.id = _UUID_AMOSTRA
    e.tipo = TipoEntrevista.triagem if tipo == "triagem" else TipoEntrevista.entrevista
    e.status = StatusEntrevista.realizada
    e.vaga_titulo = "Vigia — posto noturno 12x36 (exemplo)"
    e.entrevistador_nome = "Equipe de Recrutamento"
    e.marcada_para = agora
    e.realizada_em = agora
    e.preenchida_em = agora
    e.modalidade = "presencial"
    e.local = "Sede — Brasília/DF"
    e.duracao_min = 60
    e.observacao = ("Exemplo de observação livre registrada pelo RH após a "
                    "conversa.")

    if tipo == "triagem":
        e.triagem = {p["chave"]: ("sim" if i % 3 else "nao_sei")
                     for i, p in enumerate(inst.PERGUNTAS_PADRAO)}
        e.triagem_desfecho = "segue"
        return e

    competencias = inst.COMPETENCIAS_PADRAO
    notas = [4, 3, 3, 2]
    e.variante = "comportamental"
    e.competencias = {c["chave"]: notas[i % len(notas)]
                      for i, c in enumerate(competencias)}
    e.justificativas = {
        c["chave"]: ("Exemplo de justificativa escrita pelo entrevistador, "
                     "com o fato observado que sustenta a nota.")
        for c in competencias}
    e.recomendacao = "contratar_com_ressalva"
    e.recomendacao_motivo = ("Exemplo de ressalva: precisa de acompanhamento no "
                             "registro de ocorrências no primeiro mês.")
    e.roteiro_snapshot = {
        "id": str(_UUID_AMOSTRA), "nome": inst.NOME_ROTEIRO_PADRAO, "versao": 1,
        "cargo": None, "senioridade": None, "competencias": competencias}
    return e


def roteiro_de_amostra(tipo: str = "entrevista"):
    """Roteiro FICTÍCIO para a prévia. Também nunca vai ao banco."""
    from app.models.roteiro_entrevista import RoteiroEntrevista, StatusRoteiro, TipoRoteiro

    r = RoteiroEntrevista()
    r.id = _UUID_AMOSTRA
    r.tipo = TipoRoteiro.triagem.value if tipo == "triagem" else TipoRoteiro.entrevista.value
    r.nome = (inst.NOME_TRIAGEM_PADRAO if tipo == "triagem"
              else inst.NOME_ROTEIRO_PADRAO)
    r.status = StatusRoteiro.publicado.value
    r.versao = 1
    r.cargo = None
    r.senioridade = None
    r.padrao = True
    r.competencias = inst.COMPETENCIAS_PADRAO
    r.perguntas = inst.PERGUNTAS_PADRAO
    r.publicado_em = datetime.now(timezone.utc)
    r.publicado_por = "rh@exemplo.com"
    return r


# ---------------------------------------------------------------------------
# Recusas — o que NÃO vira documento
# ---------------------------------------------------------------------------


def erros_para_documento(e, instrumento=None) -> list[str]:
    """O que impede a entrevista de virar documento (cenário 32).

    Só entrevista **realizada e completa** vira ficha. Duas recusas:

    - status diferente de `realizada` — uma entrevista `marcada` viraria um
      documento que afirma ter havido conversa que ainda não houve; `nao_veio`
      e `cancelada` não têm avaliação nenhuma para imprimir;
    - preenchimento incompleto — reusa `completa_entrevista`, a MESMA função que
      guarda a conclusão da ficha na tela. Duas listas de "o que falta" (uma na
      rota, outra no PDF) divergiriam na primeira alteração do instrumento.
    """
    from app.models.entrevista import StatusEntrevista, TipoEntrevista

    tipo = e.tipo.value if hasattr(e.tipo, "value") else e.tipo
    status = e.status.value if hasattr(e.status, "value") else e.status
    erros = []
    # `arquivada` PASSA de propósito (cenário 38): arquivar tira da vista, nunca
    # apaga — e o documento de uma entrevista arquivada continua existindo e
    # sendo emitível. Recusar aqui faria o prazo de 180 dias virar destruição de
    # prova, que é o oposto da decisão 5 do Bruno.
    if status not in (StatusEntrevista.realizada.value, StatusEntrevista.arquivada.value):
        erros.append("Só entrevista realizada vira documento — esta está "
                     f"'{status}'.")
        return erros
    if tipo == TipoEntrevista.triagem.value:
        if not (e.triagem_desfecho or "").strip():
            erros.append("A triagem precisa de um desfecho antes de virar documento.")
        return erros
    faltam = inst.completa_entrevista(e.competencias, e.recomendacao, instrumento)
    if faltam:
        erros.append("A ficha está incompleta: " + "; ".join(faltam) + ".")
    return erros


# ---------------------------------------------------------------------------
# Blocos comuns
# ---------------------------------------------------------------------------


def _cabecalho_pessoa(pdf, e, pessoa_nome: str) -> None:
    pdf.secao("IDENTIFICAÇÃO")
    pdf.campo("Pessoa entrevistada", pessoa_nome or "—")
    # Snapshot da vaga: a vaga pode ter ido para a lixeira (v2.67) ou sumido
    # antes disso, e o documento continua dizendo para qual vaga a conversa foi
    # (cenário 4). Sem o snapshot sairia "—" numa peça de prova.
    pdf.campo("Vaga", e.vaga_titulo or "Sem vaga específica")
    pdf.campo("Conduzida por", e.entrevistador_nome or "—")
    pdf.campo("Realizada em", _data_hora(e.realizada_em))
    if e.marcada_para:
        pdf.campo("Marcada para", _data_hora(e.marcada_para))
    if e.modalidade:
        pdf.campo("Modalidade", _rotulo(_MODALIDADE, e.modalidade))
    # A DEFASAGEM é impressa quando existe (§ 2.5). Não é enfeite: quem preenche
    # dias depois reconstrói de memória, e quem lê a ficha meses depois tem o
    # direito de saber disso ao pesar a nota.
    dias = inst.defasagem_dias(e.realizada_em, e.preenchida_em)
    if dias:
        pdf.campo("Preenchida", f"{_data_hora(e.preenchida_em)} "
                                f"({dias} dia(s) após a entrevista)")


def _bloco_assinaturas(pdf, assinaturas) -> None:
    """Bloco das assinaturas eletrônicas da ficha (§ 15.3).

    Fica no MESMO documento porque a assinatura é sobre esta ficha e não sobre
    um anexo — e porque o hash gravado descreve o PDF SEM este bloco, que é a
    convenção do `Assinatura.hash_sha256` do resto do projeto: a integridade se
    confere regerando o documento base e comparando.
    """
    if not assinaturas:
        return
    pdf.ln(3)
    _secao_junta(pdf, "ASSINATURA ELETRÔNICA (Lei nº 14.063/2020)", 30)
    pdf.set_font("helvetica", "", 9)
    for a in assinaturas:
        pdf.multi_cell(
            0, 4.8,
            f"Assinado por {a.assinante_nome}"
            f"{f' ({a.assinante_email})' if a.assinante_email else ''} em "
            f"{_data_hora(a.assinado_em)} (horário de Brasília), autenticado pela "
            f"senha da própria sessão no painel do RH."
            f"\nIP: {a.ip or '—'}"
            f"\nIntegridade (SHA-256 do documento sem este bloco): "
            f"{a.hash_sha256 or '—'}",
            new_x="LMARGIN", new_y="NEXT")
        pdf.ln(2)


# ---------------------------------------------------------------------------
# 1. Ficha de ENTREVISTA preenchida
# ---------------------------------------------------------------------------


def gerar_ficha_entrevista(db: Session, e, pessoa_nome: str,
                           assinaturas=None) -> bytes:
    """A ficha preenchida, com o roteiro que foi usado.

    **O instrumento vem do `roteiro_snapshot`** — nunca do roteiro vivo. É o que
    faz o documento continuar dizendo, meses depois, com que âncoras aquela nota
    foi dada.
    """
    snap = e.roteiro_snapshot or {}
    competencias = (inst.normalizar_competencias(snap.get("competencias"))
                    or inst.COMPETENCIAS_PADRAO)

    pdf = _OficioPDF("FICHA DE ENTREVISTA")
    pdf.set_y(46)

    _cabecalho_pessoa(pdf, e, pessoa_nome)

    pdf.ln(2)
    _secao_junta(pdf, "INSTRUMENTO UTILIZADO", 30)
    # A VERSÃO é o núcleo do argumento jurídico do § 6: o documento não afirma
    # "existe um roteiro", afirma QUAL roteiro, em que versão, aprovado quando.
    pdf.campo("Roteiro", snap.get("nome") or inst.NOME_ROTEIRO_PADRAO)
    pdf.campo("Versão do roteiro", snap.get("versao") or "—")
    if snap.get("cargo"):
        pdf.campo("Cargo do roteiro", snap.get("cargo"))
    pdf.campo("Variante aplicada", _rotulo(_VARIANTE, e.variante))
    pdf.campo("Escala", "1 a 4, sem ponto médio (4 = evidência forte; "
                        "1 = contraindica)")

    pdf.ln(2)
    _secao_junta(pdf, "AVALIAÇÃO POR COMPETÊNCIA", 30)
    notas = e.competencias or {}
    justificativas = e.justificativas or {}
    for c in competencias:
        nota = notas.get(c["chave"])
        pdf.ln(1)
        pdf.set_font("helvetica", "B", 10)
        pdf.multi_cell(0, 5.4, f"{c['nome']} — nota {nota if nota else '—'} de 4",
                       new_x="LMARGIN", new_y="NEXT")
        # A ÂNCORA da nota dada, escrita por extenso. É ela que transforma "3"
        # num critério verificável em vez de uma impressão pessoal — e é o que
        # um terceiro precisa ler para entender o que a nota significa.
        ancora = (c.get("ancoras") or {}).get(str(nota)) if nota else None
        if ancora:
            pdf.set_font("helvetica", "I", 8.5)
            pdf.multi_cell(0, 4.4, f"Critério da nota {nota}: {ancora}",
                           new_x="LMARGIN", new_y="NEXT")
        pergunta = (c.get("perguntas") or {}).get(e.variante or "comportamental")
        if pergunta:
            pdf.set_font("helvetica", "", 8.5)
            pdf.multi_cell(0, 4.4, f"Pergunta: {pergunta}",
                           new_x="LMARGIN", new_y="NEXT")
        pdf.set_font("helvetica", "", 9.5)
        pdf.multi_cell(0, 4.8,
                       f"Justificativa: {(justificativas.get(c['chave']) or '—')}",
                       new_x="LMARGIN", new_y="NEXT")

    media = inst.media(e.competencias)
    pdf.ln(2)
    _secao_junta(pdf, "CONCLUSÃO", 30)
    pdf.campo("Média das competências", f"{media:.2f}".replace(".", ",")
              if media is not None else "—")
    pdf.campo("Recomendação", _rotulo(_RECOMENDACAO, e.recomendacao))
    if e.recomendacao_motivo:
        pdf.campo("Motivo da recomendação", e.recomendacao_motivo)
    if e.observacao:
        pdf.campo("Observações", e.observacao)

    pdf.ln(3)
    pdf.set_font("helvetica", "I", 8)
    pdf.multi_cell(
        0, 4,
        "Documento gerado pelo Portal de RH a partir do registro da entrevista. "
        "A avaliação seguiu roteiro pré-aprovado, com escala ancorada em "
        "comportamentos observáveis e justificativa escrita para cada nota.",
        new_x="LMARGIN", new_y="NEXT")

    _bloco_assinaturas(pdf, assinaturas)
    return bytes(pdf.output())


# ---------------------------------------------------------------------------
# 2. Ficha de TRIAGEM preenchida
# ---------------------------------------------------------------------------


def gerar_ficha_triagem(db: Session, e, pessoa_nome: str,
                        perguntas=None) -> bytes:
    """As respostas da triagem e o desfecho. **Sem nota, sem âncora, sem média.**

    A ausência é deliberada e é o § 4.1: triagem é checagem de viabilidade. Um
    número aqui — mesmo uma contagem de "sim" — convidaria a comparar pessoas
    por ele, e a triagem viraria a avaliação curta que ela não é.
    """
    itens = inst.normalizar_perguntas(perguntas) or inst.PERGUNTAS_PADRAO
    respostas = e.triagem or {}

    pdf = _OficioPDF("FICHA DE TRIAGEM")
    pdf.set_y(46)

    _cabecalho_pessoa(pdf, e, pessoa_nome)

    pdf.ln(2)
    _secao_junta(pdf, "CHECAGEM DE VIABILIDADE", 30)
    for p in itens:
        pdf.campo(p["pergunta"],
                  _rotulo(_RESPOSTA_TRIAGEM, respostas.get(p["chave"]),
                          vazio="Não perguntado"))

    # Perguntas respondidas que NÃO estão no roteiro atual: o roteiro pode ter
    # sido editado depois da triagem, e a resposta gravada não pode sumir do
    # documento por causa disso — some do formulário, não do que foi respondido.
    conhecidas = {p["chave"] for p in itens}
    extras = [(k, v) for k, v in respostas.items() if k not in conhecidas]
    if extras:
        pdf.ln(1)
        pdf.set_font("helvetica", "I", 8)
        pdf.multi_cell(0, 4, "Respostas registradas com um roteiro anterior:",
                       new_x="LMARGIN", new_y="NEXT")
        for chave, valor in extras:
            pdf.campo(str(chave).replace("_", " ").capitalize(),
                      _rotulo(_RESPOSTA_TRIAGEM, valor))

    pdf.ln(2)
    _secao_junta(pdf, "DESFECHO", 24)
    pdf.campo("Resultado da triagem", _rotulo(_DESFECHO_TRIAGEM, e.triagem_desfecho))
    if e.observacao:
        pdf.campo("Observações", e.observacao)

    pdf.ln(3)
    pdf.set_font("helvetica", "I", 8)
    # A frase do seguro-desemprego vai IMPRESSA no documento, não só na tela.
    # É a decisão 4 do Bruno, e é aqui que ela precisa aparecer: o documento
    # circula, e alguém que o leia sem conhecer o sistema poderia interpretar a
    # resposta como critério de corte.
    pdf.multi_cell(
        0, 4,
        "A triagem é uma checagem de viabilidade (escala, deslocamento, "
        "disponibilidade). Não atribui nota e não avalia competência. O "
        "recebimento de seguro-desemprego é registrado apenas como contexto e "
        "NUNCA constitui critério de exclusão.",
        new_x="LMARGIN", new_y="NEXT")
    return bytes(pdf.output())


# ---------------------------------------------------------------------------
# 3. Roteiro PUBLICADO
# ---------------------------------------------------------------------------


def gerar_roteiro(db: Session, r) -> bytes:
    """O roteiro pré-aprovado, como documento anexável.

    Só o PUBLICADO vira documento (cenário 33) — a recusa mora na rota, porque
    o motivo é de negócio ("rascunho não foi aprovado") e a mensagem precisa
    chegar ao RH, não virar exceção dentro do gerador.
    """
    from app.models.roteiro_entrevista import TipoRoteiro

    tipo = getattr(r, "tipo", None) or TipoRoteiro.entrevista.value
    e_triagem = tipo == TipoRoteiro.triagem.value

    pdf = _OficioPDF("ROTEIRO DE TRIAGEM" if e_triagem else "ROTEIRO DE ENTREVISTA")
    pdf.set_y(46)

    pdf.secao("IDENTIFICAÇÃO DO ROTEIRO")
    pdf.campo("Nome", r.nome)
    pdf.campo("Tipo", "Triagem (checagem de viabilidade)" if e_triagem
                      else "Entrevista (avaliação ancorada)")
    pdf.campo("Versão", r.versao)
    pdf.campo("Aplica-se ao cargo", r.cargo or "Todos os cargos (roteiro padrão)")
    if r.senioridade:
        pdf.campo("Senioridade", r.senioridade.capitalize())
    # QUEM aprovou e QUANDO — é exatamente esta linha que o § 6 invoca. Um
    # roteiro sem o ato de aprovação datado não sustenta "foi aprovado ANTES de
    # ser usado", que é a defesa perante a Lei 9.029/95.
    pdf.campo("Publicado em", _data(r.publicado_em))
    pdf.campo("Publicado por", r.publicado_por or "—")

    if e_triagem:
        pdf.ln(2)
        _secao_junta(pdf, "PERGUNTAS DE VIABILIDADE", 30)
        for p in inst.normalizar_perguntas(r.perguntas):
            pdf.campo(p["pergunta"], "Sim / Não / Não sei")
        pdf.ln(3)
        pdf.set_font("helvetica", "I", 8)
        pdf.multi_cell(
            0, 4,
            "Roteiro de checagem de viabilidade: sem nota, sem competência e "
            "sem âncora. O recebimento de seguro-desemprego, quando perguntado, "
            "é contexto e NUNCA critério de exclusão.",
            new_x="LMARGIN", new_y="NEXT")
        return bytes(pdf.output())

    pdf.ln(2)
    _secao_junta(pdf, "ESCALA", 30)
    for item in inst.ESCALA:
        pdf.campo(f"Nota {item['valor']}", item["rotulo"])

    for c in inst.normalizar_competencias(r.competencias):
        pdf.ln(2)
        # A faixa da competência precisa levar junto ao menos a primeira
        # pergunta; sozinha no pé da página ela viraria título órfão.
        _secao_junta(pdf, f"COMPETÊNCIA: {c['nome'].upper()}")
        perguntas = c.get("perguntas") or {}
        if perguntas.get("comportamental"):
            pdf.campo("Pergunta comportamental", perguntas["comportamental"])
        if perguntas.get("situacional"):
            pdf.campo("Pergunta situacional", perguntas["situacional"])
        for nota in ("4", "3", "2", "1"):
            texto = (c.get("ancoras") or {}).get(nota)
            if texto:
                pdf.campo(f"Âncora da nota {nota}", texto)

    pdf.ln(3)
    pdf.set_font("helvetica", "I", 8)
    pdf.multi_cell(
        0, 4,
        "Roteiro pré-aprovado de entrevista estruturada. As perguntas são fixas "
        "e iguais para todos os candidatos à mesma vaga; cada nota exige "
        "justificativa escrita, ancorada em comportamento observável.",
        new_x="LMARGIN", new_y="NEXT")
    return bytes(pdf.output())
