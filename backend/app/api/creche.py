"""Reembolso-Creche (IN SEGES/MGI 147/2026): página de acompanhamento do RH.

Nesta 1ª onda entrega o LEVANTAMENTO de elegibilidade por posto — a resposta
que os ofícios (CNMP nº 5/2026, ANATEL nº 45/2026) cobram em 5 dias úteis:
quantos colaboradores estão alocados em postos abrangidos pela IN. A camada de
dados das crianças (idade em anos/meses, documentos) entra na 2ª onda, quando o
autocadastro público estiver no ar; a estrutura já a comporta."""

import io
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.auth_rh import requer_rh
from app.core.db import get_db
from app.models.beneficio import BeneficioCreche, CriancaCreche, StatusBeneficio
from app.models.candidato import Candidato, PostoServico
from app.models.usuario_rh import UsuarioRH
from app.services import storage
from app.services.auditoria import registrar
from app.services.email import enviar_email, html_moderno

router = APIRouter(tags=["creche-rh"], dependencies=[Depends(requer_rh)])


def _gerar_e_guardar_dossie(db: Session, ben: BeneficioCreche) -> str:
    from app.services.creche_pdf import gerar_dossie_creche
    pdf = gerar_dossie_creche(db, ben)
    key = f"creche/{ben.id}/dossie-reembolso-creche.pdf"
    storage.salvar(key, pdf, "application/pdf")
    ben.dossie_pdf_key = key
    ben.dossie_gerado_em = datetime.now(timezone.utc)
    return key


def _idade_anos_meses(nasc: str, ref: datetime | None = None) -> tuple[int, int] | None:
    """Idade em (anos, meses) a partir de 'dd/mm/aaaa'. A IN 147 usa o limite de
    5 anos e 11 meses — por isso os meses importam."""
    ref = ref or datetime.now(timezone.utc)
    try:
        d, m, a = (int(x) for x in nasc.split("/"))
    except (ValueError, AttributeError):
        return None
    anos = ref.year - a
    meses = ref.month - m
    if ref.day < d:
        meses -= 1
    if meses < 0:
        anos -= 1
        meses += 12
    return (anos, meses) if anos >= 0 else None


def _elegivel_por_idade(nasc: str) -> bool:
    """<= 5 anos e 11 meses (art. 2º, §1º da IN 147/2026)."""
    am = _idade_anos_meses(nasc)
    if am is None:
        return False
    anos, meses = am
    return anos < 5 or (anos == 5 and meses <= 11)


def _postos_elegiveis(db: Session) -> list[PostoServico]:
    return db.scalars(
        select(PostoServico)
        .where(PostoServico.da_direito_creche == True)  # noqa: E712
        .order_by(PostoServico.nome)
    ).all()


@router.get("/rh/creche/resumo")
def resumo(db: Session = Depends(get_db)) -> dict:
    """Panorama do benefício: total de postos elegíveis e de colaboradores
    ativos alocados neles, quebrado por posto (com o valor de cada contrato)."""
    postos = _postos_elegiveis(db)
    ids = [p.id for p in postos]
    # contagem de colaboradores ATIVOS por posto elegível (uma consulta só)
    por_posto: dict = {pid: 0 for pid in ids}
    if ids:
        ativos = db.scalars(
            select(Candidato).where(
                Candidato.posto_servico_id.in_(ids),
                Candidato.situacao == "ativo",
            )
        ).all()
        for c in ativos:
            por_posto[c.posto_servico_id] = por_posto.get(c.posto_servico_id, 0) + 1

    linhas = [{
        "posto_id": p.id, "posto": p.nome, "sigla": p.sigla,
        "contrato_ref": p.contrato_ref,
        "valor_reembolso": p.valor_reembolso_creche,
        "colaboradores_ativos": por_posto.get(p.id, 0),
    } for p in postos]

    return {
        "postos_elegiveis": len(postos),
        "colaboradores_em_postos_elegiveis": sum(por_posto.values()),
        "por_posto": linhas,
    }


@router.get("/rh/creche/exportar")
def exportar(db: Session = Depends(get_db),
             rh: UsuarioRH = Depends(requer_rh)) -> Response:
    """Excel do levantamento: um colaborador ativo por linha, em postos que dão
    direito ao benefício, com o valor do reembolso do contrato. É a relação
    nominal que os órgãos pedem para instruir a repactuação."""
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter

    postos = {p.id: p for p in _postos_elegiveis(db)}
    colaboradores = []
    if postos:
        colaboradores = db.scalars(
            select(Candidato).where(
                Candidato.posto_servico_id.in_(list(postos.keys())),
                Candidato.situacao == "ativo",
            ).order_by(Candidato.nome_completo)
        ).all()

    cols = ["Nome completo", "CPF", "Matrícula", "Posto (contrato)", "Sigla",
            "Nº do contrato", "Valor do reembolso", "Data de admissão"]
    wb = Workbook()
    ws = wb.active
    ws.title = "Elegiveis Reembolso-Creche"
    verde = PatternFill("solid", fgColor="0FB257")
    for j, nome in enumerate(cols, start=1):
        cel = ws.cell(row=1, column=j, value=nome)
        cel.font = Font(bold=True, color="FFFFFF")
        cel.fill = verde
        cel.alignment = Alignment(vertical="center")
        ws.column_dimensions[get_column_letter(j)].width = max(14, min(40, len(nome) + 8))
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = f"A1:{get_column_letter(len(cols))}1"

    for i, c in enumerate(colaboradores, start=2):
        p = postos.get(c.posto_servico_id)
        valores = [c.nome_completo, c.cpf, c.matricula,
                   p.nome if p else "", p.sigla if p else "",
                   p.contrato_ref if p else "",
                   p.valor_reembolso_creche if p else "", c.data_admissao]
        for j, v in enumerate(valores, start=1):
            ws.cell(row=i, column=j, value=v or "")

    buf = io.BytesIO()
    wb.save(buf)
    registrar(db, "creche_levantamento_exportado", ator="rh", ator_detalhe=rh.email,
              detalhe={"colaboradores": len(colaboradores), "postos": len(postos)})
    db.commit()
    agora = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return Response(
        content=buf.getvalue(),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition":
                 f'attachment; filename="reembolso-creche-elegiveis-{agora}.xlsx"'},
    )


# ======================================================================
# Levantamentos: o RH revisa as adesões, aprova/ativa (com prazo mensal) ou
# indefere. Ao ativar, o colaborador recebe as orientações da entrega mensal.
# ======================================================================


def _dump_crianca_rh(c: CriancaCreche) -> dict:
    am = _idade_anos_meses(c.data_nascimento)
    return {
        "id": c.id, "nome": c.nome, "data_nascimento": c.data_nascimento,
        "parentesco": c.parentesco, "tipo_comprovante": c.tipo_comprovante,
        "idade_anos": am[0] if am else None, "idade_meses": am[1] if am else None,
        "elegivel_idade": _elegivel_por_idade(c.data_nascimento),
        "tem_certidao": bool(c.certidao_key), "tem_guarda": bool(c.guarda_key),
    }


def _dump_beneficio(db: Session, ben: BeneficioCreche) -> dict:
    col = db.get(Candidato, ben.candidato_id)
    posto = db.get(PostoServico, col.posto_servico_id) if col.posto_servico_id else None
    criancas = [_dump_crianca_rh(c) for c in ben.criancas]
    return {
        "id": ben.id, "candidato_id": col.id,
        "nome": col.nome_completo, "cpf": col.cpf, "matricula": col.matricula,
        "email": ben.email_confirmado or col.email, "telefone": ben.telefone,
        "posto": posto.nome if posto else None,
        "posto_da_direito": bool(posto and posto.da_direito_creche),
        "valor_posto": posto.valor_reembolso_creche if posto else None,
        "status": ben.status, "enviado_em": ben.enviado_em,
        "dia_entrega_mensal": ben.dia_entrega_mensal,
        "valor_reembolso": ben.valor_reembolso,
        "motivo_indeferimento": ben.motivo_indeferimento,
        "criancas": criancas,
        "algum_elegivel": any(c["elegivel_idade"] for c in criancas),
    }


@router.get("/rh/creche/levantamentos")
def listar_levantamentos(status: str | None = None,
                         db: Session = Depends(get_db)) -> list[dict]:
    """Adesões ao benefício. Por padrão as que precisam de ação (em análise);
    aceita filtro por status."""
    q = select(BeneficioCreche).order_by(BeneficioCreche.enviado_em.desc().nullslast())
    if status:
        q = q.where(BeneficioCreche.status == StatusBeneficio(status))
    return [_dump_beneficio(db, b) for b in db.scalars(q).all()]


@router.get("/rh/creche/levantamentos/{beneficio_id}")
def detalhe_levantamento(beneficio_id: uuid.UUID, db: Session = Depends(get_db)) -> dict:
    ben = db.get(BeneficioCreche, beneficio_id)
    if ben is None:
        raise HTTPException(status_code=404, detail="beneficio_nao_encontrado")
    return _dump_beneficio(db, ben)


class AtivarIn(BaseModel):
    dia_entrega_mensal: int | None = None
    valor_reembolso: str | None = None
    # se True, só aprova (aguardando_repactuacao); se False, ativa de fato
    aguardar_repactuacao: bool = False


@router.post("/rh/creche/levantamentos/{beneficio_id}/ativar")
def ativar_beneficio(beneficio_id: uuid.UUID, payload: AtivarIn, db: Session = Depends(get_db),
                     rh: UsuarioRH = Depends(requer_rh)) -> dict:
    """Aprova o benefício. Se aguardar_repactuacao=True, fica em
    'aguardando_repactuacao'; senão vai a 'ativo' e o colaborador recebe as
    orientações da entrega mensal (com o prazo)."""
    ben = db.get(BeneficioCreche, beneficio_id)
    if ben is None:
        raise HTTPException(status_code=404, detail="beneficio_nao_encontrado")
    col = db.get(Candidato, ben.candidato_id)
    posto = db.get(PostoServico, col.posto_servico_id) if col.posto_servico_id else None
    if payload.dia_entrega_mensal is not None:
        ben.dia_entrega_mensal = max(1, min(28, payload.dia_entrega_mensal))
    ben.valor_reembolso = (payload.valor_reembolso
                           or (posto.valor_reembolso_creche if posto else None))
    ben.revisado_por = rh.email
    ben.revisado_em = datetime.now(timezone.utc)
    # gera o dossiê do benefício (requerimento + anexos + declaração-modelo)
    try:
        _gerar_e_guardar_dossie(db, ben)
    except Exception:
        pass  # o dossiê é reproduzível pelo botão; não trava a ativação
    if payload.aguardar_repactuacao:
        ben.status = StatusBeneficio.aguardando_repactuacao
    else:
        ben.status = StatusBeneficio.ativo
        ben.ativado_em = datetime.now(timezone.utc)
        # roteiro de assinatura do requerimento: colaborador (na sessão de creche)
        # → RH que aprovou. Só após a aprovação é que o colaborador pode assinar.
        from app.services.roteiro_assinatura import criar_roteiro_creche
        try:
            criar_roteiro_creche(db, ben, rh)
        except Exception:
            pass  # a assinatura é reproduzível; não trava a ativação do benefício
        _email_orientacoes_mensais(ben, col)
    registrar(db, "creche_beneficio_ativado", ator="rh", ator_detalhe=rh.email,
              candidato_id=col.id,
              detalhe={"status": ben.status.value, "dia": ben.dia_entrega_mensal})
    db.commit()
    return _dump_beneficio(db, ben)


class IndeferirIn(BaseModel):
    motivo: str


@router.post("/rh/creche/levantamentos/{beneficio_id}/indeferir")
def indeferir_beneficio(beneficio_id: uuid.UUID, payload: IndeferirIn,
                        db: Session = Depends(get_db),
                        rh: UsuarioRH = Depends(requer_rh)) -> dict:
    ben = db.get(BeneficioCreche, beneficio_id)
    if ben is None:
        raise HTTPException(status_code=404, detail="beneficio_nao_encontrado")
    ben.status = StatusBeneficio.indeferido
    ben.motivo_indeferimento = payload.motivo.strip() or None
    ben.revisado_por = rh.email
    ben.revisado_em = datetime.now(timezone.utc)
    registrar(db, "creche_beneficio_indeferido", ator="rh", ator_detalhe=rh.email,
              candidato_id=ben.candidato_id, detalhe={"motivo": ben.motivo_indeferimento})
    db.commit()
    return _dump_beneficio(db, ben)


class PrazoMassaIn(BaseModel):
    beneficio_ids: list[uuid.UUID]
    dia_entrega_mensal: int


@router.put("/rh/creche/prazos")
def editar_prazos(payload: PrazoMassaIn, db: Session = Depends(get_db),
                  rh: UsuarioRH = Depends(requer_rh)) -> dict:
    """Ajusta o dia de entrega mensal de vários benefícios de uma vez (ou de um,
    passando um id só)."""
    dia = max(1, min(28, payload.dia_entrega_mensal))
    bens = db.scalars(select(BeneficioCreche)
                      .where(BeneficioCreche.id.in_(payload.beneficio_ids))).all()
    for b in bens:
        b.dia_entrega_mensal = dia
    registrar(db, "creche_prazos_alterados", ator="rh", ator_detalhe=rh.email,
              detalhe={"qtd": len(bens), "dia": dia})
    db.commit()
    return {"atualizados": len(bens), "dia_entrega_mensal": dia}


def _email_orientacoes_mensais(ben: BeneficioCreche, col: Candidato) -> None:
    """Enviado ao ATIVAR: orienta a entrega mensal da documentação de despesa."""
    email = ben.email_confirmado or col.email
    if not email:
        return
    dia = ben.dia_entrega_mensal
    enviar_email(
        email,
        "Green House — Reembolso-Creche ativado: orientações da entrega mensal",
        f"Olá, {col.nome_completo.split()[0].title()}!\n\n"
        "Seu benefício de Reembolso-Creche foi ATIVADO.\n\n"
        f"Todo mês, até o dia {dia}, você deve nos enviar a comprovação da "
        "despesa do mês anterior, de UMA destas formas:\n"
        "  - DECLARAÇÃO assinada pela pessoa que cuida da criança (modelo que "
        "enviamos), quando for cuidador(a)/babá; ou\n"
        "  - NOTA FISCAL da creche/pré-escola, quando for estabelecimento.\n\n"
        "Sem a comprovação no prazo, o reembolso do mês pode não ser efetuado.\n\n"
        "Atenciosamente,\nRH — Green House\n",
        html_moderno(
            "Reembolso-Creche ativado",
            [
                f"Olá, <strong>{col.nome_completo.split()[0].title()}</strong>!",
                "Seu benefício de <strong>Reembolso-Creche</strong> foi ativado. 🎉",
                f"Todo mês, <strong>até o dia {dia}</strong>, envie a comprovação "
                "da despesa do mês anterior, de uma destas formas:",
                "<ul style='margin:8px 0 0 18px;color:#3a4152'>"
                "<li><strong>Declaração</strong> assinada por quem cuida da criança "
                "(cuidador(a)/babá) — use o modelo que enviamos; ou</li>"
                "<li><strong>Nota fiscal</strong> da creche/pré-escola, quando for "
                "um estabelecimento.</li></ul>",
                "Sem a comprovação no prazo, o reembolso do mês pode não ser efetuado.",
            ],
        ),
    )


@router.post("/rh/creche/levantamentos/{beneficio_id}/dossie")
def gerar_dossie_endpoint(beneficio_id: uuid.UUID, db: Session = Depends(get_db),
                          rh: UsuarioRH = Depends(requer_rh)) -> dict:
    """(Re)gera o dossiê do benefício sob demanda."""
    ben = db.get(BeneficioCreche, beneficio_id)
    if ben is None:
        raise HTTPException(status_code=404, detail="beneficio_nao_encontrado")
    _gerar_e_guardar_dossie(db, ben)
    registrar(db, "creche_dossie_gerado", ator="rh", ator_detalhe=rh.email,
              candidato_id=ben.candidato_id)
    db.commit()
    return {"gerado_em": ben.dossie_gerado_em}


@router.get("/rh/creche/levantamentos/{beneficio_id}/dossie")
def baixar_dossie(beneficio_id: uuid.UUID, db: Session = Depends(get_db)) -> Response:
    ben = db.get(BeneficioCreche, beneficio_id)
    if ben is None:
        raise HTTPException(status_code=404, detail="beneficio_nao_encontrado")
    if not ben.dossie_pdf_key:
        _gerar_e_guardar_dossie(db, ben)
        db.commit()
    dados = storage.ler(ben.dossie_pdf_key)
    col = db.get(Candidato, ben.candidato_id)
    nome = (col.nome_completo or "colaborador").replace(" ", "-").lower()
    return Response(content=dados, media_type="application/pdf",
                    headers={"Content-Disposition":
                             f'inline; filename="dossie-creche-{nome}.pdf"'})


_CT_POR_EXT = {
    "pdf": "application/pdf", "jpg": "image/jpeg", "jpeg": "image/jpeg",
    "png": "image/png", "gif": "image/gif", "webp": "image/webp", "heic": "image/heic",
}


@router.get("/rh/creche/levantamentos/{beneficio_id}/crianca/{crianca_id}/documento/{tipo}")
def baixar_doc_crianca(beneficio_id: uuid.UUID, crianca_id: uuid.UUID, tipo: str,
                       db: Session = Depends(get_db),
                       rh: UsuarioRH = Depends(requer_rh)) -> Response:
    """Serve o documento (certidão/guarda) enviado para uma criança, para o RH
    conferir individualmente — aos moldes dos documentos cadastrais."""
    if tipo not in ("certidao", "guarda"):
        raise HTTPException(status_code=422, detail="tipo_invalido")
    c = db.get(CriancaCreche, crianca_id)
    if c is None or c.beneficio_id != beneficio_id:
        raise HTTPException(status_code=404, detail="crianca_nao_encontrada")
    key = c.certidao_key if tipo == "certidao" else c.guarda_key
    if not key:
        raise HTTPException(status_code=404, detail="documento_nao_encontrado")
    # resolve TUDO do banco antes de tocar o storage (evita DetachedInstanceError)
    ext = key.rsplit(".", 1)[-1].lower()
    content_type = _CT_POR_EXT.get(ext, "application/octet-stream")
    nome = f"{tipo}-{c.nome.replace(' ', '-').lower()}.{ext}"
    registrar(db, "creche_doc_crianca_visto", ator="rh", ator_detalhe=rh.email,
              candidato_id=None, detalhe={"beneficio": str(beneficio_id), "tipo": tipo})
    db.commit()
    try:
        dados = storage.ler(key)
    except Exception:
        raise HTTPException(status_code=404, detail="arquivo_nao_encontrado")
    return Response(content=dados, media_type=content_type,
                    headers={"Content-Disposition": f'inline; filename="{nome}"'})


@router.get("/rh/creche/levantamentos/{beneficio_id}/documento/{tipo}")
def previa_documento(beneficio_id: uuid.UUID, tipo: str, db: Session = Depends(get_db)) -> Response:
    """Prévia do requerimento preenchido (tipo=requerimento) ou da declaração
    modelo (tipo=declaracao) no timbrado."""
    from app.services.creche_pdf import (gerar_declaracao_modelo,
                                        gerar_requerimento_creche)
    ben = db.get(BeneficioCreche, beneficio_id)
    if ben is None:
        raise HTTPException(status_code=404, detail="beneficio_nao_encontrado")
    if tipo == "requerimento":
        pdf = gerar_requerimento_creche(db, ben)
    elif tipo == "declaracao":
        pdf = gerar_declaracao_modelo(db, ben)
    else:
        raise HTTPException(status_code=422, detail="tipo_invalido")
    return Response(content=pdf, media_type="application/pdf",
                    headers={"Content-Disposition": f'inline; filename="{tipo}.pdf"'})
