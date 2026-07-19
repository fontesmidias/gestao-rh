"""Assinatura eletrônica simples das 3 fichas: preview → OTP → assinar."""

import hashlib
import secrets
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import base_url_publica, get_settings, ip_do_cliente
from app.core.db import get_db
from app.models.assinatura import FICHAS_BASE, Assinatura, DocumentoAssinavel
from app.models.candidato import Candidato, StatusCandidato
from app.services import storage
from app.services.auditoria import registrar
from app.services.email import enviar_email
from app.services.fichas import GERADORES
from app.services.magic_link import resolver_token

router = APIRouter(tags=["assinaturas"])

MAX_TENTATIVAS_OTP = 5


def _candidato_do_token(token: str, db: Session) -> Candidato:
    candidato = resolver_token(db, token)
    if candidato is None:
        raise HTTPException(status_code=404, detail="link_invalido_ou_expirado")
    return candidato


def _registro(db: Session, candidato: Candidato, documento: DocumentoAssinavel) -> Assinatura:
    # Só registros ATIVOS de FLUXO LIVRE: uma assinatura invalidada fica para
    # histórico; e as de ROTEIRO multi-signatário (solicitacao_etapa_id) são
    # ignoradas aqui — elas têm caminho próprio e não podem brigar com o wizard
    # (correção C1).
    assinatura = db.scalar(
        select(Assinatura).where(
            Assinatura.candidato_id == candidato.id, Assinatura.documento == documento,
            Assinatura.invalidada_em.is_(None),
            Assinatura.solicitacao_etapa_id.is_(None),
        )
    )
    if assinatura is None:
        assinatura = Assinatura(candidato_id=candidato.id, documento=documento)
        db.add(assinatura)
        db.flush()
    return assinatura


def _docs_exigidos(db: Session, candidato: Candidato) -> list[DocumentoAssinavel]:
    """As 3 fichas (sempre) + documentos extras que o RH gerou para o candidato
    (registros de Assinatura já criados — ex.: documentos do posto INFRAERO).
    Exclui as Assinaturas de roteiro multi-signatário (têm fluxo próprio)."""
    extras = db.scalars(
        select(Assinatura).where(
            Assinatura.candidato_id == candidato.id,
            Assinatura.documento.notin_(FICHAS_BASE),
            Assinatura.invalidada_em.is_(None),
            Assinatura.solicitacao_etapa_id.is_(None),
        )
    ).all()
    return list(FICHAS_BASE) + sorted({a.documento for a in extras}, key=lambda d: d.value)


# --- Documentos de MODELO do RH enviados para assinatura -------------------
# Convivem com os documentos fixos do enum: a chave pública deles nas rotas e
# no payload é "modelo-<id do registro de assinatura>".


def _assinaturas_modelo(db: Session, candidato: Candidato) -> list[Assinatura]:
    return db.scalars(
        select(Assinatura).where(
            Assinatura.candidato_id == candidato.id,
            Assinatura.modelo_id.isnot(None),
            Assinatura.invalidada_em.is_(None),
            Assinatura.solicitacao_etapa_id.is_(None),  # roteiro tem fluxo próprio
        ).order_by(Assinatura.criado_em)
    ).all()


def _assinaturas_roteiro_na_vez(db: Session, candidato: Candidato) -> list[Assinatura]:
    """Assinaturas de ROTEIRO multi-signatário cuja etapa do candidato está NA
    VEZ (ordem corrente e solicitação aguardando). Só essas entram no fluxo do
    candidato — as demais ficam bloqueadas até chegar a vez dele (gate de ordem,
    correção C1)."""
    from app.models.solicitacao_assinatura import (EtapaAssinatura,
                                                   SolicitacaoAssinatura,
                                                   StatusSolicitacao)
    etapas = db.scalars(
        select(EtapaAssinatura)
        .join(SolicitacaoAssinatura,
              EtapaAssinatura.solicitacao_id == SolicitacaoAssinatura.id)
        .where(SolicitacaoAssinatura.candidato_id == candidato.id,
               SolicitacaoAssinatura.status == StatusSolicitacao.aguardando,
               EtapaAssinatura.ordem == SolicitacaoAssinatura.etapa_atual_ordem,
               EtapaAssinatura.assinatura_id.isnot(None),
               EtapaAssinatura.assinado_em.is_(None))).all()
    saida = []
    for e in etapas:
        a = db.get(Assinatura, e.assinatura_id)
        if a is not None and a.assinado_em is None:
            saida.append(a)
    return saida


def chave_doc(a: Assinatura) -> str:
    return a.documento.value if a.documento else f"modelo-{a.id}"


def titulo_doc(a: Assinatura) -> str:
    if a.documento:
        return NOMES_DOC[a.documento]
    return a.titulo_doc or "Documento"


def _resolver_doc(db: Session, candidato: Candidato,
                  chave: str) -> tuple[DocumentoAssinavel | None, Assinatura]:
    """Resolve a chave da rota: valor do enum OU 'modelo-<uuid>'."""
    if chave.startswith("modelo-"):
        try:
            a = db.get(Assinatura, uuid.UUID(chave.removeprefix("modelo-")))
        except ValueError:
            a = None
        if (a is None or a.candidato_id != candidato.id or a.modelo_id is None
                or a.invalidada_em is not None):
            raise HTTPException(status_code=404, detail="documento_nao_encontrado")
        return None, a
    try:
        doc = DocumentoAssinavel(chave)
    except ValueError:
        raise HTTPException(status_code=404, detail="documento_nao_encontrado")
    return doc, _registro(db, candidato, doc)


def _gerar_pdf(db: Session, candidato: Candidato, a: Assinatura,
               com_assinatura: bool = False, base_url: str | None = None) -> bytes:
    """PDF do documento da assinatura `a` — fixo (enum) ou de modelo (snapshot)."""
    from app.services.fichas import gerar_documento_modelo
    if a.documento:
        if com_assinatura:
            return GERADORES[a.documento.value](db, candidato, a, base_url)
        return GERADORES[a.documento.value](db, candidato)
    return gerar_documento_modelo(db, a.titulo_doc or "Documento", a.corpo_doc or "",
                                  candidato, a if com_assinatura else None, base_url)


@router.get("/c/{token}/fichas")
def status_fichas(token: str, db: Session = Depends(get_db)) -> dict:
    candidato = _candidato_do_token(token, db)
    assinaturas = db.scalars(
        select(Assinatura).where(Assinatura.candidato_id == candidato.id,
                                 Assinatura.invalidada_em.is_(None))
    ).all()
    por_doc = {a.documento: a for a in assinaturas}
    db.commit()
    return {
        "fichas": [
            {
                "documento": doc,
                "titulo": NOMES_DOC[doc],
                "assinado": doc in por_doc and por_doc[doc].assinado_em is not None,
                "assinado_em": por_doc[doc].assinado_em if doc in por_doc else None,
            }
            for doc in _docs_exigidos(db, candidato)
        ] + [
            # documentos de modelo enviados pelo RH para assinatura
            {
                "documento": chave_doc(a),
                "titulo": titulo_doc(a),
                "assinado": a.assinado_em is not None,
                "assinado_em": a.assinado_em,
            }
            for a in _assinaturas_modelo(db, candidato)
        ]
    }


@router.get("/c/{token}/fichas/{documento}/preview")
def preview(token: str, documento: str, db: Session = Depends(get_db)) -> Response:
    """PDF do documento (fixo ou de modelo): a via assinada, se existir; senão,
    prévia com os dados atuais."""
    candidato = _candidato_do_token(token, db)
    _, assinatura = _resolver_doc(db, candidato, documento)
    if assinatura.assinado_em is not None and assinatura.pdf_key:
        pdf = storage.ler(assinatura.pdf_key)
    else:
        pdf = _gerar_pdf(db, candidato, assinatura)
    db.commit()
    return Response(content=pdf, media_type="application/pdf")


NOMES_DOC = {
    DocumentoAssinavel.ficha_cadastro: "Ficha Cadastral do Colaborador",
    DocumentoAssinavel.ficha_emergencia: "Ficha de Emergência do Colaborador",
    DocumentoAssinavel.termo_vt: "Termo de Opção pelo Vale-Transporte",
    DocumentoAssinavel.acordo_confidencialidade: "Acordo de Confidencialidade",
    DocumentoAssinavel.oficio_cartao_cidadao:
        "Ofício INFRAERO — Cartão Cidadão e extrato do INSS",
    DocumentoAssinavel.informacoes_trabalhador:
        "Informações ao Trabalhador (INFRAERO)",
    DocumentoAssinavel.termo_lgpd_infraero:
        "Termo de Consentimento LGPD — Credenciamento (INFRAERO)",
    DocumentoAssinavel.informativo_intermitente:
        "Informativo de Integração — Intermitente",
    DocumentoAssinavel.ficha_cadastral_terceirizado:
        "Ficha Cadastral de Terceirizado (Presidência)",
    DocumentoAssinavel.oficio_apresentacao_presidencia:
        "Ofício de Apresentação — Presidência da República",
}


def _nome_mascarado(nome: str) -> str:
    """LGPD (minimização): primeiro nome + iniciais dos demais. 'José T. S.'"""
    partes = [p for p in nome.split() if p]
    if not partes:
        return "-"
    return " ".join([partes[0].title()] + [f"{p[0].upper()}." for p in partes[1:]])


def _cpf_mascarado(cpf: str | None) -> str:
    n = "".join(c for c in (cpf or "") if c.isdigit())
    if len(n) != 11:
        return "-"
    return f"***.{n[3:6]}.{n[6:9]}-**"


@router.get("/verificar/{assinatura_id}")
def verificar_assinatura(assinatura_id: uuid.UUID, db: Session = Depends(get_db)) -> dict:
    """Verificação PÚBLICA de autenticidade (QR code do manifesto). Dados
    minimizados: nome e CPF mascarados; nada de e-mail, IP ou dispositivo."""
    assinatura = db.get(Assinatura, assinatura_id)
    if assinatura is None or assinatura.assinado_em is None:
        raise HTTPException(status_code=404, detail="assinatura_nao_encontrada")
    candidato = db.get(Candidato, assinatura.candidato_id)

    from app.models.ficha import DocumentosIdentificacao
    doc_id = db.get(DocumentosIdentificacao, candidato.id)

    registrar(db, "assinatura_verificada", ator="publico",
              candidato_id=candidato.id, detalhe={"assinatura": str(assinatura.id)})
    db.commit()
    if assinatura.invalidada_em is not None:
        # A assinatura EXISTIU e era íntegra, mas o documento foi atualizado
        # depois — dizer 'não encontrada' aqui soaria como fraude; a verdade
        # é 'substituída por uma versão mais recente'.
        return {
            "valida": False,
            "substituida": True,
            "documento": titulo_doc(assinatura),
            "assinante": _nome_mascarado(candidato.nome_completo),
            "cpf": _cpf_mascarado(doc_id.cpf if doc_id else None),
            "assinado_em": assinatura.assinado_em,
            "invalidada_em": assinatura.invalidada_em,
            "hash_sha256": assinatura.hash_sha256,
            "id": assinatura.id,
        }
    return {
        "valida": True,
        "documento": titulo_doc(assinatura),
        "papel": assinatura.papel,
        "assinante": _nome_mascarado(candidato.nome_completo),
        "cpf": _cpf_mascarado(doc_id.cpf if doc_id else None),
        "assinado_em": assinatura.assinado_em,
        "hash_sha256": assinatura.hash_sha256,
        "metodo": "Código de verificação de uso único enviado ao e-mail do titular "
                  "(assinatura eletrônica simples — art. 4º, I, Lei nº 14.063/2020).",
        "id": assinatura.id,
    }


@router.post("/c/{token}/fichas/solicitar-codigo", status_code=204)
def solicitar_codigo_unico(token: str, db: Session = Depends(get_db)) -> None:
    """Um único código para assinar todos os documentos pendentes de uma vez."""
    from app.services.limite import exigir
    exigir(f"assin-codigo:{token[:16]}", maximo=5, janela_s=900)
    candidato = _candidato_do_token(token, db)
    registros = [_registro(db, candidato, d) for d in _docs_exigidos(db, candidato)]
    registros += _assinaturas_modelo(db, candidato)
    pendentes = [a for a in registros if a.assinado_em is None]
    if not pendentes:
        raise HTTPException(status_code=409, detail="todos_ja_assinados")

    codigo = f"{secrets.randbelow(1_000_000):06d}"
    otp_hash = hashlib.sha256(codigo.encode()).hexdigest()
    expira = datetime.now(timezone.utc) + timedelta(minutes=get_settings().otp_ttl_minutes)
    for assinatura in pendentes:
        assinatura.otp_hash = otp_hash
        assinatura.otp_expira_em = expira
        assinatura.otp_tentativas = 0
    db.commit()

    from app.services.email import html_moderno

    docs = "\n".join(f"  - {titulo_doc(a)}" for a in pendentes)
    docs_html = "".join(f"<li>{titulo_doc(a)}</li>" for a in pendentes)
    ttl = get_settings().otp_ttl_minutes
    enviar_email(
        candidato.email,
        "Green House — Código de assinatura dos documentos admissionais",
        f"Prezado(a) {candidato.nome_completo},\n\n"
        f"Seu código de assinatura eletrônica é: {codigo}\n\n"
        f"Ele é válido por {ttl} minutos e assina, de uma só vez, os seguintes documentos:\n"
        f"{docs}\n\nDigite o código na tela de assinatura para concluir. Caso não localize "
        "esta mensagem, verifique a caixa de spam ou lixo eletrônico.\n\n"
        "Se você não solicitou este código, desconsidere esta mensagem.\n\n"
        "Atenciosamente,\nRH — Green House\n",
        html_moderno(
            "Seu código de assinatura",
            [
                f"Prezado(a) <strong>{candidato.nome_completo}</strong>,",
                f"Use o código abaixo na tela de assinatura. Ele é válido por "
                f"<strong>{ttl} minutos</strong> e assina, de uma só vez, os documentos:"
                f"<ul style='margin:8px 0 0 18px;color:#3a4152'>{docs_html}</ul>",
                "Se você não solicitou este código, desconsidere esta mensagem.",
            ],
            destaque=codigo,
        ),
    )


class AssinarTodosIn(BaseModel):
    codigo: str


@router.post("/c/{token}/fichas/assinar")
def assinar_todos(
    token: str,
    payload: AssinarTodosIn,
    request: Request,
    db: Session = Depends(get_db),
) -> dict:
    """Valida o código único e assina todos os documentos pendentes."""
    candidato = _candidato_do_token(token, db)
    registros = [_registro(db, candidato, d) for d in _docs_exigidos(db, candidato)]
    registros += _assinaturas_modelo(db, candidato)
    registros += _assinaturas_roteiro_na_vez(db, candidato)  # multi-signatário
    pendentes = [a for a in registros if a.assinado_em is None]
    if not pendentes:
        raise HTTPException(status_code=409, detail="todos_ja_assinados")

    ref = pendentes[0]
    if ref.otp_hash is None or ref.otp_expira_em is None:
        raise HTTPException(status_code=409, detail="codigo_nao_solicitado")
    if ref.otp_expira_em < datetime.now(timezone.utc):
        raise HTTPException(status_code=410, detail="codigo_expirado")
    if ref.otp_tentativas >= MAX_TENTATIVAS_OTP:
        raise HTTPException(status_code=429, detail="tentativas_excedidas")
    if hashlib.sha256(payload.codigo.encode()).hexdigest() != ref.otp_hash:
        for a in pendentes:
            a.otp_tentativas += 1
        db.commit()
        raise HTTPException(status_code=422, detail="codigo_incorreto")

    agora = datetime.now(timezone.utc)
    anexos: list[tuple[str, bytes]] = []
    assinados = []
    for assinatura in pendentes:
        chave = chave_doc(assinatura)
        pdf_sem_bloco = _gerar_pdf(db, candidato, assinatura)
        assinatura.hash_sha256 = hashlib.sha256(pdf_sem_bloco).hexdigest()
        assinatura.assinado_em = agora
        assinatura.ip = ip_do_cliente(request)
        assinatura.user_agent = request.headers.get("user-agent", "")[:400]
        assinatura.otp_hash = None
        assinatura.otp_expira_em = None
        pdf_assinado = _gerar_pdf(db, candidato, assinatura, com_assinatura=True,
                                  base_url=base_url_publica(request))
        # Rubrica digital em CADA página: registro + hash + instante na lateral.
        from app.services.fichas import carimbar_rubrica_lateral
        pdf_assinado = carimbar_rubrica_lateral(pdf_assinado, assinatura)
        # Key com o id da assinatura: uma re-assinatura (após invalidação)
        # nunca sobrescreve a via antiga — cada via assinada é preservada.
        key = f"candidatos/{candidato.id}/fichas/{chave}-{assinatura.id}.pdf"
        storage.salvar(key, pdf_assinado, "application/pdf")
        assinatura.pdf_key = key
        anexos.append((f"{chave}.pdf", pdf_assinado))
        assinados.append({"documento": chave, "assinado_em": agora,
                          "hash_sha256": assinatura.hash_sha256})
        registrar(db, "documento_assinado", ator="candidato", candidato_id=candidato.id,
                  detalhe={"documento": chave, "hash": assinatura.hash_sha256})

    if candidato.status == StatusCandidato.aguardando_assinatura:
        candidato.status = StatusCandidato.docs_pendentes
    db.commit()

    # Multi-signatário: promove as etapas de roteiro que o candidato acabou de
    # assinar (libera o próximo signatário). Fora da transação principal.
    from app.api.solicitacoes_assinatura import promover_etapa_do_candidato
    for a in pendentes:
        if a.solicitacao_etapa_id:
            promover_etapa_do_candidato(db, a, base_url_publica(request))

    from app.services.email import html_moderno

    docs_html = "".join(f"<li>{titulo_doc(a)}</li>" for a in pendentes)
    enviar_email(
        candidato.email,
        "Green House — Seus documentos assinados (vias do colaborador)",
        f"Prezado(a) {candidato.nome_completo},\n\n"
        "Confirmamos a assinatura eletrônica dos seus documentos admissionais, que seguem "
        "anexos a esta mensagem para sua guarda:\n"
        + "\n".join(f"  - {titulo_doc(a)}" for a in pendentes)
        + "\n\nPróximo passo obrigatório: envie a sua documentação pelo mesmo link da "
        "admissão. Sua contratação somente será efetivada após o envio completo.\n\n"
        "Atenciosamente,\nRH — Green House\n",
        html_moderno(
            "Documentos assinados ✓",
            [
                f"Prezado(a) <strong>{candidato.nome_completo}</strong>,",
                "Confirmamos a assinatura eletrônica dos seus documentos admissionais. "
                "As vias assinadas seguem <strong>anexas a esta mensagem</strong> para sua guarda:"
                f"<ul style='margin:8px 0 0 18px;color:#3a4152'>{docs_html}</ul>",
                "<strong>Próximo passo obrigatório:</strong> envie a sua documentação pelo "
                "mesmo link da admissão. Sua contratação somente será efetivada após o "
                "envio completo.",
            ],
        ),
        anexos=anexos,
    )
    return {"assinados": assinados}


@router.post("/c/{token}/fichas/{documento}/solicitar-codigo", status_code=204)
def solicitar_codigo(
    token: str, documento: str, db: Session = Depends(get_db)
) -> None:
    from app.services.limite import exigir
    exigir(f"assin-codigo:{token[:16]}", maximo=5, janela_s=900)
    candidato = _candidato_do_token(token, db)
    if candidato.status not in (StatusCandidato.aguardando_assinatura,
                                StatusCandidato.docs_pendentes,
                                StatusCandidato.preenchendo,
                                # re-assinatura após atualização de dados pelo RH
                                StatusCandidato.envio_concluido,
                                StatusCandidato.em_revisao):
        raise HTTPException(status_code=409, detail="fase_invalida_para_assinatura")
    _, assinatura = _resolver_doc(db, candidato, documento)
    if assinatura.assinado_em is not None:
        raise HTTPException(status_code=409, detail="documento_ja_assinado")

    codigo = f"{secrets.randbelow(1_000_000):06d}"
    assinatura.otp_hash = hashlib.sha256(codigo.encode()).hexdigest()
    assinatura.otp_expira_em = datetime.now(timezone.utc) + timedelta(
        minutes=get_settings().otp_ttl_minutes
    )
    assinatura.otp_tentativas = 0
    db.commit()

    nome_doc = titulo_doc(assinatura)
    enviar_email(
        candidato.email,
        f"🌱 Green House — seu código para assinar: {nome_doc}",
        f"Seu código de assinatura é: {codigo}\n\n"
        f"Ele vale por {get_settings().otp_ttl_minutes} minutos e serve apenas para o "
        f"documento '{nome_doc}'. Se você não pediu este código, ignore este e-mail.\n",
    )


class AssinarIn(BaseModel):
    codigo: str


@router.post("/c/{token}/fichas/{documento}/assinar")
def assinar(
    token: str,
    documento: DocumentoAssinavel,
    payload: AssinarIn,
    request: Request,
    db: Session = Depends(get_db),
) -> dict:
    candidato = _candidato_do_token(token, db)
    doc_enum, assinatura = _resolver_doc(db, candidato, documento)
    if assinatura.assinado_em is not None:
        raise HTTPException(status_code=409, detail="documento_ja_assinado")
    if assinatura.otp_hash is None or assinatura.otp_expira_em is None:
        raise HTTPException(status_code=409, detail="codigo_nao_solicitado")
    if assinatura.otp_expira_em < datetime.now(timezone.utc):
        raise HTTPException(status_code=410, detail="codigo_expirado")
    if assinatura.otp_tentativas >= MAX_TENTATIVAS_OTP:
        raise HTTPException(status_code=429, detail="tentativas_excedidas")

    if hashlib.sha256(payload.codigo.encode()).hexdigest() != assinatura.otp_hash:
        assinatura.otp_tentativas += 1
        db.commit()
        raise HTTPException(status_code=422, detail="codigo_incorreto")

    # Evidências: hash do documento SEM o bloco de assinatura, IP, user-agent, instante.
    pdf_sem_bloco = _gerar_pdf(db, candidato, assinatura)
    assinatura.hash_sha256 = hashlib.sha256(pdf_sem_bloco).hexdigest()
    assinatura.assinado_em = datetime.now(timezone.utc)
    assinatura.ip = ip_do_cliente(request)
    assinatura.user_agent = request.headers.get("user-agent", "")[:400]
    assinatura.otp_hash = None
    assinatura.otp_expira_em = None

    pdf_assinado = _gerar_pdf(db, candidato, assinatura, com_assinatura=True,
                              base_url=base_url_publica(request))
    from app.services.fichas import carimbar_rubrica_lateral
    pdf_assinado = carimbar_rubrica_lateral(pdf_assinado, assinatura)
    key = f"candidatos/{candidato.id}/fichas/{chave_doc(assinatura)}-{assinatura.id}.pdf"
    storage.salvar(key, pdf_assinado, "application/pdf")
    assinatura.pdf_key = key

    # Assinou as 3? Candidato segue para a etapa de documentos.
    assinadas = db.scalars(
        select(Assinatura).where(
            Assinatura.candidato_id == candidato.id, Assinatura.assinado_em.isnot(None),
            Assinatura.invalidada_em.is_(None),
        )
    ).all()
    todas = {a.documento for a in assinadas if a.documento} | ({doc_enum} if doc_enum else set())
    if todas >= set(_docs_exigidos(db, candidato)) \
            and candidato.status == StatusCandidato.aguardando_assinatura:
        candidato.status = StatusCandidato.docs_pendentes

    registrar(db, "documento_assinado", ator="candidato", candidato_id=candidato.id,
              detalhe={"documento": chave_doc(assinatura), "hash": assinatura.hash_sha256})
    db.commit()
    return {
        "documento": chave_doc(assinatura),
        "assinado_em": assinatura.assinado_em,
        "hash_sha256": assinatura.hash_sha256,
    }
