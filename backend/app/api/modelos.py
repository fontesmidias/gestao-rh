"""CRUD de modelos de documento criados pelo RH (layout timbrado + variáveis)
e geração do PDF preenchido para um colaborador."""

import io
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.api.auth_rh import requer_rh
from app.core.db import get_db
from app.models.candidato import Candidato
from app.models.modelo_documento import EscopoModelo, ModeloDocumento
from app.models.usuario_rh import UsuarioRH
from app.services.auditoria import registrar
from app.services.email import enviar_email
from app.services.fichas import (VARIAVEIS_MODELO, gerar_documento_modelo)

router = APIRouter(tags=["modelos-documento"], dependencies=[Depends(requer_rh)])


class ModeloIn(BaseModel):
    titulo: str
    corpo: str
    escopo: EscopoModelo = EscopoModelo.avulso
    cargo_alvo: str | None = None
    posto_alvo_id: uuid.UUID | None = None
    candidato_alvo_id: uuid.UUID | None = None
    # Comportamento ao enviar para uma pessoa
    enviar_por_email: bool = False
    exige_assinatura: bool = False
    papel_assinatura: str | None = None


def _dump(m: ModeloDocumento) -> dict:
    return {
        "id": m.id, "titulo": m.titulo, "corpo": m.corpo, "escopo": m.escopo.value,
        "cargo_alvo": m.cargo_alvo, "posto_alvo_id": m.posto_alvo_id,
        "candidato_alvo_id": m.candidato_alvo_id, "criado_em": m.criado_em,
        "atualizado_em": m.atualizado_em,
        "enviar_por_email": m.enviar_por_email,
        "exige_assinatura": m.exige_assinatura,
        "papel_assinatura": m.papel_assinatura,
    }


def _aplicar(m: ModeloDocumento, payload: ModeloIn) -> None:
    m.titulo = payload.titulo.strip()
    m.corpo = payload.corpo
    m.escopo = payload.escopo
    # Só o alvo do escopo escolhido é guardado; os demais zeram.
    m.cargo_alvo = payload.cargo_alvo.strip() if (
        payload.escopo == EscopoModelo.cargo and payload.cargo_alvo) else None
    m.posto_alvo_id = payload.posto_alvo_id if payload.escopo == EscopoModelo.posto else None
    m.candidato_alvo_id = (payload.candidato_alvo_id
                           if payload.escopo == EscopoModelo.colaborador else None)
    m.enviar_por_email = payload.enviar_por_email
    m.exige_assinatura = payload.exige_assinatura
    m.papel_assinatura = (payload.papel_assinatura or "").strip() or None


@router.get("/rh/modelos-documento")
def listar(db: Session = Depends(get_db)) -> dict:
    modelos = db.scalars(select(ModeloDocumento).order_by(ModeloDocumento.titulo)).all()
    return {"modelos": [_dump(m) for m in modelos],
            "variaveis": VARIAVEIS_MODELO}


@router.post("/rh/modelos-documento", status_code=201)
def criar(payload: ModeloIn, db: Session = Depends(get_db),
          rh: UsuarioRH = Depends(requer_rh)) -> dict:
    if not payload.titulo.strip() or not payload.corpo.strip():
        raise HTTPException(status_code=422, detail="titulo_e_corpo_obrigatorios")
    m = ModeloDocumento()
    _aplicar(m, payload)
    db.add(m)
    registrar(db, "modelo_documento_criado", ator="rh", ator_detalhe=rh.email,
              detalhe={"titulo": m.titulo, "escopo": m.escopo.value})
    db.commit()
    return _dump(m)


@router.put("/rh/modelos-documento/{modelo_id}")
def editar(modelo_id: uuid.UUID, payload: ModeloIn, db: Session = Depends(get_db),
           rh: UsuarioRH = Depends(requer_rh)) -> dict:
    m = db.get(ModeloDocumento, modelo_id)
    if m is None:
        raise HTTPException(status_code=404, detail="modelo_nao_encontrado")
    _aplicar(m, payload)
    registrar(db, "modelo_documento_editado", ator="rh", ator_detalhe=rh.email,
              detalhe={"titulo": m.titulo})
    db.commit()
    return _dump(m)


@router.delete("/rh/modelos-documento/{modelo_id}", status_code=204)
def excluir(modelo_id: uuid.UUID, db: Session = Depends(get_db),
            rh: UsuarioRH = Depends(requer_rh)) -> None:
    m = db.get(ModeloDocumento, modelo_id)
    if m is None:
        raise HTTPException(status_code=404, detail="modelo_nao_encontrado")
    registrar(db, "modelo_documento_excluido", ator="rh", ator_detalhe=rh.email,
              detalhe={"titulo": m.titulo})
    # snapshot restaurável antes do delete (lixeira, retenção configurável)
    from app.services.lixeira import mandar_para_lixeira
    mandar_para_lixeira(db, m, "modelo_documento", m.titulo, rh.email)
    db.delete(m)
    db.commit()


@router.get("/rh/modelos-documento/{modelo_id}/previa")
def previa(modelo_id: uuid.UUID, db: Session = Depends(get_db)) -> StreamingResponse:
    """Prévia sem colaborador: as variáveis aparecem como {{...}}."""
    m = db.get(ModeloDocumento, modelo_id)
    if m is None:
        raise HTTPException(status_code=404, detail="modelo_nao_encontrado")
    pdf = gerar_documento_modelo(db, m.titulo, m.corpo, None)
    return StreamingResponse(io.BytesIO(pdf), media_type="application/pdf")


@router.get("/rh/candidatos/{candidato_id}/modelos-aplicaveis")
def aplicaveis(candidato_id: uuid.UUID, db: Session = Depends(get_db)) -> list[dict]:
    """Modelos que valem para este colaborador: avulsos + do seu cargo + do seu
    posto + os anexados diretamente a ele."""
    candidato = db.get(Candidato, candidato_id)
    if candidato is None:
        raise HTTPException(status_code=404, detail="candidato_nao_encontrado")
    condicoes = [ModeloDocumento.escopo == EscopoModelo.avulso,
                 ModeloDocumento.candidato_alvo_id == candidato.id]
    if candidato.cargo_funcao:
        condicoes.append((ModeloDocumento.escopo == EscopoModelo.cargo)
                         & (ModeloDocumento.cargo_alvo == candidato.cargo_funcao))
    if candidato.posto_servico_id:
        condicoes.append((ModeloDocumento.escopo == EscopoModelo.posto)
                         & (ModeloDocumento.posto_alvo_id == candidato.posto_servico_id))
    modelos = db.scalars(
        select(ModeloDocumento).where(or_(*condicoes)).order_by(ModeloDocumento.titulo)
    ).all()
    return [{"id": m.id, "titulo": m.titulo, "escopo": m.escopo.value} for m in modelos]


@router.get("/rh/candidatos/{candidato_id}/modelos/{modelo_id}/gerar")
def gerar(candidato_id: uuid.UUID, modelo_id: uuid.UUID, db: Session = Depends(get_db),
          rh: UsuarioRH = Depends(requer_rh)) -> StreamingResponse:
    """Gera o PDF do modelo com as variáveis preenchidas para o colaborador."""
    candidato = db.get(Candidato, candidato_id)
    m = db.get(ModeloDocumento, modelo_id)
    if candidato is None or m is None:
        raise HTTPException(status_code=404, detail="nao_encontrado")
    pdf = gerar_documento_modelo(db, m.titulo, m.corpo, candidato)
    registrar(db, "modelo_documento_gerado", ator="rh", ator_detalhe=rh.email,
              candidato_id=candidato.id, detalhe={"titulo": m.titulo})
    db.commit()
    nome = "".join(c for c in m.titulo if c.isalnum() or c in " -_").strip()[:60] or "documento"
    return StreamingResponse(
        io.BytesIO(pdf), media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{nome}.pdf"'})


class EnviarModeloIn(BaseModel):
    # None = seguir o que está configurado no modelo
    enviar_email: bool | None = None
    para_assinatura: bool | None = None


@router.post("/rh/candidatos/{candidato_id}/modelos/{modelo_id}/enviar")
def enviar_para_pessoa(candidato_id: uuid.UUID, modelo_id: uuid.UUID,
                       payload: EnviarModeloIn, request: Request,
                       db: Session = Depends(get_db),
                       rh: UsuarioRH = Depends(requer_rh)) -> dict:
    """Envia o documento do modelo para UMA pessoa (antiga ou nova):

    - com assinatura: cria o registro pendente com SNAPSHOT do título/corpo
      (edições futuras do modelo não mudam o que a pessoa assina) e o papel do
      signatário; a pessoa assina pelo link mágico, no mesmo fluxo 2FA das
      fichas, com bloco de assinatura, manifesto e verificação pública.
    - por e-mail sem assinatura: manda o PDF pronto anexado.
    """
    from app.core.config import base_url_publica
    from app.models.assinatura import Assinatura
    from app.services.email import html_moderno
    from app.services.magic_link import emitir_link

    candidato = db.get(Candidato, candidato_id)
    m = db.get(ModeloDocumento, modelo_id)
    if candidato is None or m is None:
        raise HTTPException(status_code=404, detail="nao_encontrado")
    enviar_email_ = m.enviar_por_email if payload.enviar_email is None else payload.enviar_email
    para_assinatura = (m.exige_assinatura if payload.para_assinatura is None
                       else payload.para_assinatura)

    assinatura = None
    link = None
    if para_assinatura:
        # evita duplicar: reaproveita pendência ativa do mesmo modelo
        assinatura = db.scalar(select(Assinatura).where(
            Assinatura.candidato_id == candidato.id,
            Assinatura.modelo_id == m.id,
            Assinatura.assinado_em.is_(None),
            Assinatura.invalidada_em.is_(None)))
        if assinatura is None:
            assinatura = Assinatura(
                candidato_id=candidato.id, modelo_id=m.id,
                titulo_doc=m.titulo[:200], corpo_doc=m.corpo,
                papel=m.papel_assinatura or "Contratado(a)")
            db.add(assinatura)
            db.flush()
        link = emitir_link(db, candidato, base_url_publica(request))

    registrar(db, "modelo_documento_enviado", ator="rh", ator_detalhe=rh.email,
              candidato_id=candidato.id,
              detalhe={"titulo": m.titulo, "assinatura": para_assinatura,
                       "email": bool(enviar_email_)})
    db.commit()

    email_enviado = False
    if enviar_email_ and candidato.email:
        if para_assinatura:
            email_enviado = enviar_email(
                candidato.email,
                f"Green House — documento aguarda sua assinatura: {m.titulo}",
                f"Prezado(a) {candidato.nome_completo},\n\n"
                f"O documento \"{m.titulo}\" foi disponibilizado e aguarda a sua "
                f"assinatura eletrônica.\n\nAcesse: {link}\n\n"
                "A assinatura leva menos de um minuto.\n\nAtenciosamente,\nRH — Green House\n",
                html_moderno(
                    "Documento aguarda sua assinatura",
                    [
                        f"Prezado(a) <strong>{candidato.nome_completo}</strong>,",
                        f"O documento <strong>{m.titulo}</strong> foi disponibilizado "
                        "e aguarda a sua assinatura eletrônica.",
                        f"<a href='{link}'>Toque aqui para conferir e assinar</a> — "
                        "leva menos de um minuto.",
                    ],
                ),
            )
        else:
            pdf = gerar_documento_modelo(db, m.titulo, m.corpo, candidato)
            nome_arq = "".join(c for c in m.titulo if c.isalnum() or c in " -_").strip()[:60] \
                or "documento"
            email_enviado = enviar_email(
                candidato.email,
                f"Green House — {m.titulo}",
                f"Prezado(a) {candidato.nome_completo},\n\n"
                f"Segue anexo o documento \"{m.titulo}\".\n\n"
                "Atenciosamente,\nRH — Green House\n",
                html_moderno(
                    m.titulo,
                    [f"Prezado(a) <strong>{candidato.nome_completo}</strong>,",
                     f"Segue anexo o documento <strong>{m.titulo}</strong>."],
                ),
                anexos=[(f"{nome_arq}.pdf", pdf)],
            )

    return {"assinatura_criada": para_assinatura,
            "assinatura_id": str(assinatura.id) if assinatura else None,
            "email_enviado": email_enviado, "link_magico": link}


# --- Papéis de assinatura (Contratado(a), Contratante, Testemunha…) --------


class PapelIn(BaseModel):
    nome: str
    descricao: str | None = None
    ordem: int = 0


def _dump_papel(p) -> dict:
    return {"id": p.id, "nome": p.nome, "descricao": p.descricao, "ordem": p.ordem}


@router.get("/rh/papeis-assinatura")
def listar_papeis(db: Session = Depends(get_db)) -> dict:
    from app.models.modelo_documento import PapelAssinatura
    papeis = db.scalars(select(PapelAssinatura)
                        .order_by(PapelAssinatura.ordem, PapelAssinatura.nome)).all()
    return {"papeis": [_dump_papel(p) for p in papeis]}


@router.post("/rh/papeis-assinatura", status_code=201)
def criar_papel(payload: PapelIn, db: Session = Depends(get_db),
                rh: UsuarioRH = Depends(requer_rh)) -> dict:
    from app.models.modelo_documento import PapelAssinatura
    nome = payload.nome.strip()
    if not nome:
        raise HTTPException(status_code=422, detail="nome_obrigatorio")
    if db.scalar(select(PapelAssinatura).where(PapelAssinatura.nome == nome)):
        raise HTTPException(status_code=409, detail="papel_ja_existe")
    p = PapelAssinatura(nome=nome[:60], descricao=(payload.descricao or "").strip()[:300] or None,
                        ordem=payload.ordem)
    db.add(p)
    registrar(db, "papel_assinatura_criado", ator="rh", ator_detalhe=rh.email,
              detalhe={"nome": nome})
    db.commit()
    return _dump_papel(p)


@router.put("/rh/papeis-assinatura/{papel_id}")
def editar_papel(papel_id: uuid.UUID, payload: PapelIn, db: Session = Depends(get_db),
                 rh: UsuarioRH = Depends(requer_rh)) -> dict:
    from app.models.modelo_documento import PapelAssinatura
    p = db.get(PapelAssinatura, papel_id)
    if p is None:
        raise HTTPException(status_code=404, detail="papel_nao_encontrado")
    nome = payload.nome.strip()
    if not nome:
        raise HTTPException(status_code=422, detail="nome_obrigatorio")
    p.nome = nome[:60]
    p.descricao = (payload.descricao or "").strip()[:300] or None
    p.ordem = payload.ordem
    registrar(db, "papel_assinatura_editado", ator="rh", ator_detalhe=rh.email,
              detalhe={"nome": p.nome})
    db.commit()
    return _dump_papel(p)


# --- Roteiro-padrão de papéis de um modelo -------------------------------
# Só papel/ordem/tipo_sugerido — as PESSOAS são escolhidas no disparo
# (correção M9: nunca congelar um usuário RH aqui).


class EtapaPadraoIn(BaseModel):
    papel: str
    ordem: int
    tipo_sugerido: str  # candidato | usuario_rh | externo


@router.get("/rh/modelos/{modelo_id}/roteiro-padrao")
def ver_roteiro_padrao(modelo_id: uuid.UUID, db: Session = Depends(get_db)) -> dict:
    from app.models.solicitacao_assinatura import ModeloEtapaPadrao
    etapas = db.scalars(select(ModeloEtapaPadrao)
                        .where(ModeloEtapaPadrao.modelo_id == modelo_id)
                        .order_by(ModeloEtapaPadrao.ordem)).all()
    return {"etapas": [{"papel": e.papel, "ordem": e.ordem,
                        "tipo_sugerido": e.tipo_sugerido.value} for e in etapas]}


@router.put("/rh/modelos/{modelo_id}/roteiro-padrao")
def salvar_roteiro_padrao(modelo_id: uuid.UUID, payload: list[EtapaPadraoIn],
                          db: Session = Depends(get_db),
                          rh: UsuarioRH = Depends(requer_rh)) -> dict:
    from app.models.solicitacao_assinatura import (ModeloEtapaPadrao,
                                                   TipoSignatario)
    if db.get(ModeloDocumento, modelo_id) is None:
        raise HTTPException(status_code=404, detail="modelo_nao_encontrado")
    # substitui o roteiro-padrão inteiro
    for e in db.scalars(select(ModeloEtapaPadrao)
                        .where(ModeloEtapaPadrao.modelo_id == modelo_id)).all():
        db.delete(e)
    for it in payload:
        try:
            tipo = TipoSignatario(it.tipo_sugerido)
        except ValueError:
            raise HTTPException(status_code=422, detail="tipo_sugerido_invalido")
        db.add(ModeloEtapaPadrao(modelo_id=modelo_id, papel=it.papel.strip()[:60],
                                 ordem=it.ordem, tipo_sugerido=tipo))
    registrar(db, "roteiro_padrao_salvo", ator="rh", ator_detalhe=rh.email,
              detalhe={"modelo": str(modelo_id), "etapas": len(payload)})
    db.commit()
    return {"etapas": len(payload)}


@router.delete("/rh/papeis-assinatura/{papel_id}", status_code=204)
def excluir_papel(papel_id: uuid.UUID, db: Session = Depends(get_db),
                  rh: UsuarioRH = Depends(requer_rh)) -> None:
    from app.models.modelo_documento import PapelAssinatura
    from app.services.lixeira import mandar_para_lixeira
    p = db.get(PapelAssinatura, papel_id)
    if p is None:
        raise HTTPException(status_code=404, detail="papel_nao_encontrado")
    registrar(db, "papel_assinatura_excluido", ator="rh", ator_detalhe=rh.email,
              detalhe={"nome": p.nome})
    mandar_para_lixeira(db, p, "papel_assinatura", p.nome, rh.email)
    db.delete(p)
    db.commit()
