"""Painel do RH para o Cadastro de Desenvolvimento (Onda B).

Duas telas por trás destas rotas:
  1. **Fila de validação** — o que os colaboradores enviaram, esperando conferência.
  2. **Tipos** — o catálogo configurável (o que pode ser cadastrado, validade,
     criticidade, cargos, prazos por posto/cargo).

A fila é o risco operacional do módulo: ~2.400 pedidos/ano = ~10 por dia útil.
A 3 minutos cada, são 30 minutos por dia, todo dia. Por isso a aprovação em
LOTE existe — mas **documento crítico nunca entra nela** (`pode_aprovar_em_lote`).
"""

import uuid
from datetime import date, datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.auth_rh import requer_rh
from app.core.db import get_db
from app.models.candidato import Candidato, PostoServico
from app.models.desenvolvimento import (ArquivoDesenvolvimento, PrazoValidade,
                                        RegistroDesenvolvimento,
                                        SolicitacaoMatricula, StatusRegistro,
                                        TipoDesenvolvimento, TurmaReciclagem)
from app.models.usuario_rh import UsuarioRH
from app.services import storage
from app.services.auditoria import registrar
from app.services.desenvolvimento import (calcular_validade, meses_validade_de,
                                          pode_aprovar_em_lote, situacao_validade)

router = APIRouter(tags=["desenvolvimento-rh"], dependencies=[Depends(requer_rh)])


def _dump(db: Session, r: RegistroDesenvolvimento) -> dict:
    col = db.get(Candidato, r.candidato_id)
    posto = (db.get(PostoServico, col.posto_servico_id)
             if col and col.posto_servico_id else None)
    return {
        "id": str(r.id),
        "candidato_id": str(r.candidato_id),
        "colaborador": col.nome_completo if col else "—",
        "matricula": col.matricula if col else None,
        "cargo": col.cargo_funcao if col else None,
        "posto": posto.nome if posto else None,
        "tipo": r.tipo.nome if r.tipo else None,
        "tipo_id": str(r.tipo_id),
        "critico": bool(r.tipo and r.tipo.critico),
        "titulo": r.titulo,
        "instituicao": r.instituicao,
        "carga_horaria": r.carga_horaria,
        "concluido_em": r.concluido_em.isoformat() if r.concluido_em else None,
        "validade_ate": r.validade_ate.isoformat() if r.validade_ate else None,
        "situacao_validade": situacao_validade(r),
        "status": r.status.value,
        "observacao": r.observacao,
        "motivo_recusa": r.motivo_recusa,
        # o que a IA propôs, para o RH comparar com o que a pessoa confirmou
        "extraido_ia": r.extraido_ia,
        "lido_por_ia": r.lido_por_ia_em is not None,
        "documentos": [{"id": str(a.id), "papel": a.papel,
                        "nome": a.nome_original, "tamanho": a.tamanho,
                        "sensibilidade": a.sensibilidade.value}
                       for a in r.arquivos],
        "pode_lote": pode_aprovar_em_lote(r),
        "criado_em": r.criado_em.isoformat() if r.criado_em else None,
        "validado_por": r.validado_por,
        "validado_em": r.validado_em.isoformat() if r.validado_em else None,
        "enviado_por": r.enviado_por,
    }


# ---------------------------------------------------------------------------
# Fila de validação
# ---------------------------------------------------------------------------


@router.get("/rh/desenvolvimento/registros")
def listar_registros(status: str | None = None, candidato_id: uuid.UUID | None = None,
                     db: Session = Depends(get_db)) -> dict:
    """Fila do RH. Sem filtro, traz o que espera decisão (pendente + devolvido).

    Filtro pesado fica SERVER-SIDE (aqui) e o DashPlanilha refina em memória por
    cima — padrão da casa. São ~7.200 arquivos em 3 anos: trazer tudo ao cliente
    seria regressão de performance."""
    consulta = select(RegistroDesenvolvimento)
    if candidato_id:
        consulta = consulta.where(
            RegistroDesenvolvimento.candidato_id == candidato_id)
    if status:
        alvos = [s.strip() for s in status.split(",") if s.strip()]
        consulta = consulta.where(RegistroDesenvolvimento.status.in_(alvos))
    elif not candidato_id:
        consulta = consulta.where(RegistroDesenvolvimento.status.in_(
            [StatusRegistro.pendente, StatusRegistro.devolvido]))
    registros = db.scalars(
        consulta.order_by(RegistroDesenvolvimento.criado_em.desc())).all()

    contagem = dict(db.execute(
        select(RegistroDesenvolvimento.status, func.count())
        .group_by(RegistroDesenvolvimento.status)).all())
    return {
        "registros": [_dump(db, r) for r in registros],
        "metricas": {s.value: contagem.get(s, 0) for s in StatusRegistro},
    }


class LoteIn(BaseModel):
    ids: list[uuid.UUID]


@router.post("/rh/desenvolvimento/registros/lote/validar")
def validar_lote(payload: LoteIn, db: Session = Depends(get_db),
                 rh: UsuarioRH = Depends(requer_rh)) -> dict:
    """Aprova em massa — só o que `pode_aprovar_em_lote` autoriza.

    **Documento crítico é recusado aqui, não filtrado silenciosamente**: se o RH
    marcou um brigadista no lote, ele precisa saber que aquele ficou de fora, e
    não descobrir depois que "aprovou" algo que não foi aprovado.
    """
    validados, barrados = [], []
    for rid in payload.ids:
        r = db.get(RegistroDesenvolvimento, rid)
        if r is None:
            continue
        if not pode_aprovar_em_lote(r):
            col = db.get(Candidato, r.candidato_id)
            barrados.append({
                "id": str(r.id),
                "colaborador": col.nome_completo if col else "—",
                "motivo": ("documento crítico: confira um a um"
                           if (r.tipo and r.tipo.critico)
                           else "faltam dados obrigatórios")})
            continue
        col = db.get(Candidato, r.candidato_id)
        r.validade_ate = calcular_validade(r.concluido_em,
                                           meses_validade_de(db, r.tipo, col))
        r.status = StatusRegistro.validado
        r.validado_por = rh.email
        r.validado_em = datetime.now(timezone.utc)
        validados.append(str(r.id))
    if validados:
        registrar(db, "desenvolvimento_validado_lote", ator="rh",
                  ator_detalhe=rh.email,
                  detalhe={"quantidade": len(validados), "barrados": len(barrados)})
    db.commit()
    return {"validados": validados, "barrados": barrados}


class ValidarIn(BaseModel):
    # o RH pode corrigir o que a pessoa digitou antes de validar
    titulo: str | None = None
    instituicao: str | None = None
    carga_horaria: str | None = None
    concluido_em: str | None = None   # aaaa-mm-dd


def _data_de(txt: str | None):
    from datetime import datetime as dt
    txt = (txt or "").strip()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y"):
        try:
            return dt.strptime(txt, fmt).date()
        except ValueError:
            continue
    return None


@router.post("/rh/desenvolvimento/registros/{registro_id}/validar")
def validar(registro_id: uuid.UUID, payload: ValidarIn,
            db: Session = Depends(get_db), rh: UsuarioRH = Depends(requer_rh)) -> dict:
    """Valida um registro: passa a valer no histórico e no dossiê.

    A validade é RECALCULADA aqui com o prazo vigente (tipo → cargo → posto) e
    persistida: o prazo pode mudar depois, mas a validade de um certificado já
    emitido não muda junto."""
    r = db.get(RegistroDesenvolvimento, registro_id)
    if r is None:
        raise HTTPException(status_code=404, detail="registro_nao_encontrado")
    if r.status == StatusRegistro.validado:
        raise HTTPException(status_code=409, detail="ja_validado")
    for campo in ("titulo", "instituicao", "carga_horaria"):
        valor = getattr(payload, campo)
        if valor is not None:
            setattr(r, campo, valor.strip() or None)
    if payload.concluido_em is not None:
        r.concluido_em = _data_de(payload.concluido_em)
    col = db.get(Candidato, r.candidato_id)
    r.validade_ate = calcular_validade(r.concluido_em,
                                       meses_validade_de(db, r.tipo, col))
    r.status = StatusRegistro.validado
    r.validado_por = rh.email
    r.validado_em = datetime.now(timezone.utc)
    r.motivo_recusa = None
    registrar(db, "desenvolvimento_validado", ator="rh", ator_detalhe=rh.email,
              candidato_id=r.candidato_id,
              detalhe={"tipo": r.tipo.nome if r.tipo else None,
                       "validade": r.validade_ate.isoformat() if r.validade_ate else None})
    db.commit()
    db.refresh(r)
    return _dump(db, r)


class MotivoIn(BaseModel):
    motivo: str


@router.post("/rh/desenvolvimento/registros/{registro_id}/devolver")
def devolver(registro_id: uuid.UUID, payload: MotivoIn,
             db: Session = Depends(get_db), rh: UsuarioRH = Depends(requer_rh)) -> dict:
    """Devolve para o colaborador corrigir. O motivo é VISÍVEL para ele — por
    isso o campo é obrigatório e a tela avisa que ele lê."""
    r = db.get(RegistroDesenvolvimento, registro_id)
    if r is None:
        raise HTTPException(status_code=404, detail="registro_nao_encontrado")
    if not (payload.motivo or "").strip():
        raise HTTPException(status_code=422, detail="motivo_obrigatorio")
    r.status = StatusRegistro.devolvido
    r.motivo_recusa = payload.motivo.strip()
    r.validado_por = rh.email
    r.validado_em = datetime.now(timezone.utc)
    registrar(db, "desenvolvimento_devolvido", ator="rh", ator_detalhe=rh.email,
              candidato_id=r.candidato_id, detalhe={"motivo": r.motivo_recusa})
    db.commit()
    _avisar_colaborador(db, r, "devolvido")
    db.refresh(r)
    return _dump(db, r)


@router.post("/rh/desenvolvimento/registros/{registro_id}/recusar")
def recusar(registro_id: uuid.UUID, payload: MotivoIn,
            db: Session = Depends(get_db), rh: UsuarioRH = Depends(requer_rh)) -> dict:
    """Recusa em definitivo (não se aplica ao cargo, documento falso, duplicado).
    Diferente de devolver: não pede correção, encerra."""
    r = db.get(RegistroDesenvolvimento, registro_id)
    if r is None:
        raise HTTPException(status_code=404, detail="registro_nao_encontrado")
    if not (payload.motivo or "").strip():
        raise HTTPException(status_code=422, detail="motivo_obrigatorio")
    r.status = StatusRegistro.recusado
    r.motivo_recusa = payload.motivo.strip()
    r.validado_por = rh.email
    r.validado_em = datetime.now(timezone.utc)
    registrar(db, "desenvolvimento_recusado", ator="rh", ator_detalhe=rh.email,
              candidato_id=r.candidato_id, detalhe={"motivo": r.motivo_recusa})
    db.commit()
    _avisar_colaborador(db, r, "recusado")
    db.refresh(r)
    return _dump(db, r)


@router.get("/rh/desenvolvimento/registros/{registro_id}/documento/{arquivo_id}")
def baixar_documento(registro_id: uuid.UUID, arquivo_id: uuid.UUID,
                     db: Session = Depends(get_db)) -> Response:
    """Serve o documento para o RH conferir. Content-Type pela extensão — pode
    ser foto, não só PDF."""
    a = db.get(ArquivoDesenvolvimento, arquivo_id)
    if a is None or a.registro_id != registro_id:
        raise HTTPException(status_code=404, detail="arquivo_nao_encontrado")
    try:
        dados = storage.ler(a.key)
    except Exception:
        raise HTTPException(status_code=404, detail="arquivo_indisponivel")
    tipos = {"pdf": "application/pdf", "jpg": "image/jpeg", "jpeg": "image/jpeg",
             "png": "image/png", "webp": "image/webp", "heic": "image/heic"}
    ext = a.key.rsplit(".", 1)[-1].lower()
    return Response(content=dados,
                    media_type=a.content_type or tipos.get(ext, "application/octet-stream"),
                    headers={"Content-Disposition":
                             f'inline; filename="{a.papel}.{ext}"'})


# ---------------------------------------------------------------------------
# Tipos (catálogo configurável) — rotas ESPECÍFICAS antes das paramétricas
# ---------------------------------------------------------------------------


def _dump_tipo(db: Session, t: TipoDesenvolvimento) -> dict:
    prazos = db.scalars(select(PrazoValidade)
                        .where(PrazoValidade.tipo_id == t.id)).all()
    em_uso = db.scalar(select(func.count()).select_from(RegistroDesenvolvimento)
                       .where(RegistroDesenvolvimento.tipo_id == t.id)) or 0
    return {
        "id": str(t.id), "nome": t.nome, "descricao": t.descricao,
        "exige_validade": t.exige_validade, "meses_validade": t.meses_validade,
        "critico": t.critico, "cargos_aplicaveis": t.cargos_aplicaveis or [],
        "documentos_exigidos": t.documentos_exigidos or [],
        "aviso_dias_antes": t.aviso_dias_antes, "ativo": t.ativo,
        "em_uso": em_uso,
        "prazos": [{"id": str(p.id), "cargo": p.cargo,
                    "posto_id": str(p.posto_id) if p.posto_id else None,
                    "meses_validade": p.meses_validade} for p in prazos],
    }


class TipoIn(BaseModel):
    nome: str
    descricao: str | None = None
    exige_validade: bool = False
    meses_validade: int | None = None
    critico: bool = False
    cargos_aplicaveis: list[str] | None = None
    documentos_exigidos: list[str] | None = None
    aviso_dias_antes: int = 90
    ativo: bool = True


@router.get("/rh/desenvolvimento/tipos")
def listar_tipos(db: Session = Depends(get_db)) -> dict:
    tipos = db.scalars(select(TipoDesenvolvimento)
                       .order_by(TipoDesenvolvimento.nome)).all()
    return {"tipos": [_dump_tipo(db, t) for t in tipos]}


@router.post("/rh/desenvolvimento/tipos", status_code=201)
def criar_tipo(payload: TipoIn, db: Session = Depends(get_db),
               rh: UsuarioRH = Depends(requer_rh)) -> dict:
    nome = (payload.nome or "").strip()
    if not nome:
        raise HTTPException(status_code=422, detail="nome_obrigatorio")
    if db.scalar(select(TipoDesenvolvimento)
                 .where(func.lower(TipoDesenvolvimento.nome) == nome.lower())):
        raise HTTPException(status_code=409, detail="nome_duplicado")
    t = TipoDesenvolvimento(
        nome=nome, descricao=(payload.descricao or "").strip() or None,
        exige_validade=payload.exige_validade,
        meses_validade=payload.meses_validade if payload.exige_validade else None,
        critico=payload.critico,
        cargos_aplicaveis=payload.cargos_aplicaveis or None,
        documentos_exigidos=payload.documentos_exigidos or None,
        aviso_dias_antes=payload.aviso_dias_antes, ativo=payload.ativo)
    db.add(t)
    registrar(db, "desenvolvimento_tipo_criado", ator="rh", ator_detalhe=rh.email,
              detalhe={"nome": nome, "critico": t.critico})
    db.commit()
    db.refresh(t)
    return _dump_tipo(db, t)


@router.put("/rh/desenvolvimento/tipos/{tipo_id}")
def editar_tipo(tipo_id: uuid.UUID, payload: TipoIn, db: Session = Depends(get_db),
                rh: UsuarioRH = Depends(requer_rh)) -> dict:
    t = db.get(TipoDesenvolvimento, tipo_id)
    if t is None:
        raise HTTPException(status_code=404, detail="tipo_nao_encontrado")
    t.nome = (payload.nome or t.nome).strip()
    t.descricao = (payload.descricao or "").strip() or None
    t.exige_validade = payload.exige_validade
    t.meses_validade = payload.meses_validade if payload.exige_validade else None
    t.critico = payload.critico
    t.cargos_aplicaveis = payload.cargos_aplicaveis or None
    t.documentos_exigidos = payload.documentos_exigidos or None
    t.aviso_dias_antes = payload.aviso_dias_antes
    t.ativo = payload.ativo
    registrar(db, "desenvolvimento_tipo_editado", ator="rh", ator_detalhe=rh.email,
              detalhe={"nome": t.nome})
    db.commit()
    db.refresh(t)
    return _dump_tipo(db, t)


@router.delete("/rh/desenvolvimento/tipos/{tipo_id}", status_code=204)
def excluir_tipo(tipo_id: uuid.UUID, db: Session = Depends(get_db),
                 rh: UsuarioRH = Depends(requer_rh)) -> None:
    """Recusa 409 se o tipo estiver em uso — como o DELETE de jornada. Apagar
    levaria junto o histórico de quem já enviou aquele certificado."""
    t = db.get(TipoDesenvolvimento, tipo_id)
    if t is None:
        raise HTTPException(status_code=404, detail="tipo_nao_encontrado")
    em_uso = db.scalar(select(func.count()).select_from(RegistroDesenvolvimento)
                       .where(RegistroDesenvolvimento.tipo_id == t.id)) or 0
    if em_uso:
        raise HTTPException(status_code=409, detail="tipo_em_uso")
    registrar(db, "desenvolvimento_tipo_excluido", ator="rh", ator_detalhe=rh.email,
              detalhe={"nome": t.nome})
    db.delete(t)
    db.commit()


class PrazoIn(BaseModel):
    cargo: str | None = None
    posto_id: uuid.UUID | None = None
    meses_validade: int


@router.post("/rh/desenvolvimento/tipos/{tipo_id}/prazos", status_code=201)
def criar_prazo(tipo_id: uuid.UUID, payload: PrazoIn, db: Session = Depends(get_db),
                rh: UsuarioRH = Depends(requer_rh)) -> dict:
    """Sobrescreve a validade para um cargo OU um posto (o mais específico
    vence na hora de calcular)."""
    t = db.get(TipoDesenvolvimento, tipo_id)
    if t is None:
        raise HTTPException(status_code=404, detail="tipo_nao_encontrado")
    cargo = (payload.cargo or "").strip() or None
    if bool(cargo) == bool(payload.posto_id):
        # nem os dois, nem nenhum: a regra precisa de um alvo único
        raise HTTPException(status_code=422, detail="informe_cargo_ou_posto")
    if payload.meses_validade < 1:
        raise HTTPException(status_code=422, detail="meses_invalido")
    db.add(PrazoValidade(tipo_id=t.id, cargo=cargo, posto_id=payload.posto_id,
                         meses_validade=payload.meses_validade))
    registrar(db, "desenvolvimento_prazo_criado", ator="rh", ator_detalhe=rh.email,
              detalhe={"tipo": t.nome, "cargo": cargo,
                       "posto": str(payload.posto_id) if payload.posto_id else None,
                       "meses": payload.meses_validade})
    db.commit()
    db.refresh(t)
    return _dump_tipo(db, t)


@router.delete("/rh/desenvolvimento/prazos/{prazo_id}", status_code=204)
def excluir_prazo(prazo_id: uuid.UUID, db: Session = Depends(get_db),
                  rh: UsuarioRH = Depends(requer_rh)) -> None:
    p = db.get(PrazoValidade, prazo_id)
    if p is None:
        raise HTTPException(status_code=404, detail="prazo_nao_encontrado")
    db.delete(p)
    db.commit()


# ---------------------------------------------------------------------------
# Brigadistas: vencimentos, turmas e solicitação de matrícula
# ---------------------------------------------------------------------------


@router.get("/rh/desenvolvimento/brigadistas")
def listar_brigadistas(db: Session = Depends(get_db)) -> dict:
    """Quem está com certificação CRÍTICA vencendo — a "consulta" que substitui
    o módulo de brigadistas.

    Não é tabela nova: são registros validados, de tipo crítico, ordenados pelo
    que vence primeiro. Traz as pendências de cada um para o RH saber quem já
    pode ser matriculado."""
    from app.services.matricula_reciclagem import pendencias_do_dossie
    registros = db.scalars(
        select(RegistroDesenvolvimento)
        .join(TipoDesenvolvimento)
        .where(TipoDesenvolvimento.critico == True,  # noqa: E712
               RegistroDesenvolvimento.validade_ate.isnot(None))
        .order_by(RegistroDesenvolvimento.validade_ate)).all()
    linhas = []
    for r in registros:
        base = _dump(db, r)
        base["pendencias"] = pendencias_do_dossie(db, r)
        base["pronto"] = not base["pendencias"]
        base["dias_para_vencer"] = ((r.validade_ate - date.today()).days
                                    if r.validade_ate else None)
        linhas.append(base)
    return {
        "brigadistas": linhas,
        "metricas": {
            "vencidos": sum(1 for l in linhas if l["situacao_validade"] == "vencido"),
            "a_vencer": sum(1 for l in linhas if l["situacao_validade"] == "a_vencer"),
            "prontos": sum(1 for l in linhas if l["pronto"]),
        },
    }


class TurmaIn(BaseModel):
    inicio_em: str            # aaaa-mm-dd
    periodo: str = "noturno"  # diurno | noturno
    entidade: str = "Multicursos"
    email_destino: str | None = None
    observacao: str | None = None
    tipo_id: uuid.UUID | None = None


def _dump_turma(t: TurmaReciclagem) -> dict:
    return {"id": str(t.id), "entidade": t.entidade,
            "inicio_em": t.inicio_em.isoformat() if t.inicio_em else None,
            "periodo": t.periodo, "email_destino": t.email_destino,
            "observacao": t.observacao, "encerrada": t.encerrada}


@router.get("/rh/desenvolvimento/turmas")
def listar_turmas(db: Session = Depends(get_db)) -> dict:
    turmas = db.scalars(select(TurmaReciclagem)
                        .where(TurmaReciclagem.encerrada == False)  # noqa: E712
                        .order_by(TurmaReciclagem.inicio_em)).all()
    from app.services.matricula_reciclagem import textos
    return {"turmas": [_dump_turma(t) for t in turmas], "textos": textos(db)}


@router.post("/rh/desenvolvimento/turmas", status_code=201)
def criar_turma(payload: TurmaIn, db: Session = Depends(get_db),
                rh: UsuarioRH = Depends(requer_rh)) -> dict:
    inicio = _data_de(payload.inicio_em)
    if inicio is None:
        raise HTTPException(status_code=422, detail="data_invalida")
    if payload.periodo not in ("diurno", "noturno"):
        raise HTTPException(status_code=422, detail="periodo_invalido")
    t = TurmaReciclagem(
        inicio_em=inicio, periodo=payload.periodo,
        entidade=(payload.entidade or "Multicursos").strip(),
        email_destino=(payload.email_destino or "").strip() or None,
        observacao=(payload.observacao or "").strip() or None,
        tipo_id=payload.tipo_id)
    db.add(t)
    registrar(db, "reciclagem_turma_criada", ator="rh", ator_detalhe=rh.email,
              detalhe={"inicio": inicio.isoformat(), "periodo": t.periodo})
    db.commit()
    db.refresh(t)
    return _dump_turma(t)


@router.delete("/rh/desenvolvimento/turmas/{turma_id}", status_code=204)
def encerrar_turma(turma_id: uuid.UUID, db: Session = Depends(get_db),
                   rh: UsuarioRH = Depends(requer_rh)) -> None:
    """Encerra (não apaga): a turma pode estar citada numa solicitação enviada."""
    t = db.get(TurmaReciclagem, turma_id)
    if t is None:
        raise HTTPException(status_code=404, detail="turma_nao_encontrada")
    t.encerrada = True
    db.commit()


class RascunhoIn(BaseModel):
    registro_ids: list[uuid.UUID]
    turma_id: uuid.UUID | None = None
    agrupar: bool = True
    data_turma: str | None = None   # quando não há turma cadastrada
    periodo: str | None = None


@router.post("/rh/desenvolvimento/matricula/rascunho")
def rascunho_matricula(payload: RascunhoIn, db: Session = Depends(get_db)) -> dict:
    """Monta o(s) e-mail(s) para o RH conferir ANTES de enviar.

    Não envia nada. Devolve também as pendências de cada pessoa — quem está
    incompleto **bloqueia** o envio (decisão do Bruno: não sai dossiê furado
    para a clínica)."""
    from app.services.matricula_reciclagem import montar
    registros = [db.get(RegistroDesenvolvimento, rid) for rid in payload.registro_ids]
    registros = [r for r in registros if r is not None]
    if not registros:
        raise HTTPException(status_code=422, detail="nenhum_registro")
    turma = db.get(TurmaReciclagem, payload.turma_id) if payload.turma_id else None
    rascunhos = montar(db, registros, turma, payload.agrupar,
                       data_turma=_data_de(payload.data_turma),
                       periodo=payload.periodo)
    incompletos = [{"nome": p["nome"], "pendencias": p["pendencias"]}
                   for r in rascunhos for p in r["colaboradores"] if p["pendencias"]]
    return {"rascunhos": rascunhos, "incompletos": incompletos,
            "pode_enviar": not incompletos}


class EnviarMatriculaIn(BaseModel):
    registro_ids: list[uuid.UUID]
    destinatarios: list[str]
    assunto: str
    corpo: str
    corpo_html: str | None = None
    turma_id: uuid.UUID | None = None
    data_turma: str | None = None
    periodo: str | None = None


@router.post("/rh/desenvolvimento/matricula/enviar")
def enviar_matricula(payload: EnviarMatriculaIn, db: Session = Depends(get_db),
                     rh: UsuarioRH = Depends(requer_rh)) -> dict:
    """Envia a solicitação com os dossiês em anexo — um PDF por pessoa.

    O texto vem do que o RH conferiu na tela (ele pode ter editado), e é isso
    que fica guardado: a `SolicitacaoMatricula` é a prova do que foi pedido."""
    from app.services import dossie_reciclagem
    from app.services.email import enviar_email
    from app.services.matricula_reciclagem import pendencias_do_dossie

    registros = [db.get(RegistroDesenvolvimento, rid) for rid in payload.registro_ids]
    registros = [r for r in registros if r is not None]
    if not registros:
        raise HTTPException(status_code=422, detail="nenhum_registro")
    destinos = [e.strip() for e in payload.destinatarios if e and e.strip()]
    if not destinos:
        raise HTTPException(status_code=422, detail="sem_destinatario")

    # trava: ninguém incompleto vai para a clínica
    faltando = []
    for r in registros:
        pend = pendencias_do_dossie(db, r)
        if pend:
            col = db.get(Candidato, r.candidato_id)
            faltando.append({"nome": col.nome_completo if col else "—",
                             "pendencias": pend})
    if faltando:
        raise HTTPException(status_code=422,
                            detail={"erro": "dossie_incompleto", "faltando": faltando})

    anexos, pessoas = [], []
    for r in registros:
        col = db.get(Candidato, r.candidato_id)
        try:
            pdf = dossie_reciclagem.gerar(db, r)
        except ValueError:
            raise HTTPException(
                status_code=422,
                detail={"erro": "dossie_incompleto",
                        "faltando": [{"nome": col.nome_completo if col else "—",
                                      "pendencias": ["documentos ilegíveis"]}]})
        anexos.append((dossie_reciclagem.nome_arquivo(col), pdf))
        pessoas.append({"candidato_id": str(r.candidato_id),
                        "registro_id": str(r.id),
                        "nome": col.nome_completo if col else "—"})

    turma = db.get(TurmaReciclagem, payload.turma_id) if payload.turma_id else None
    enviados = 0
    for destino in destinos:
        if enviar_email(destino, payload.assunto, payload.corpo,
                        payload.corpo_html, anexos=anexos):
            enviados += 1

    sol = SolicitacaoMatricula(
        turma_id=turma.id if turma else None,
        turma_inicio_em=(turma.inicio_em if turma else _data_de(payload.data_turma)),
        turma_periodo=(turma.periodo if turma else payload.periodo),
        destinatarios=destinos, assunto=payload.assunto, corpo=payload.corpo,
        colaboradores=pessoas,
        enviado_em=datetime.now(timezone.utc) if enviados else None,
        enviado_por=rh.email)
    db.add(sol)
    registrar(db, "reciclagem_matricula_solicitada", ator="rh", ator_detalhe=rh.email,
              detalhe={"pessoas": len(pessoas), "destinos": len(destinos),
                       "enviados": enviados})
    db.commit()
    if not enviados:
        raise HTTPException(status_code=502, detail="email_nao_enviado")
    return {"enviados": enviados, "pessoas": len(pessoas),
            "anexos": [n for n, _ in anexos]}


@router.get("/rh/desenvolvimento/registros/{registro_id}/dossie")
def baixar_dossie(registro_id: uuid.UUID, db: Session = Depends(get_db)) -> Response:
    """Prévia do PDF que iria para a clínica — o RH confere antes de mandar."""
    from app.services import dossie_reciclagem
    r = db.get(RegistroDesenvolvimento, registro_id)
    if r is None:
        raise HTTPException(status_code=404, detail="registro_nao_encontrado")
    col = db.get(Candidato, r.candidato_id)
    try:
        pdf = dossie_reciclagem.gerar(db, r)
    except ValueError:
        raise HTTPException(status_code=422, detail="dossie_vazio")
    return Response(content=pdf, media_type="application/pdf",
                    headers={"Content-Disposition":
                             f'inline; filename="{dossie_reciclagem.nome_arquivo(col)}"'})


def _avisar_colaborador(db: Session, r: RegistroDesenvolvimento, acao: str) -> None:
    """Avisa quem enviou que houve decisão. Sem isso a pessoa só descobriria se
    entrasse no portal por acaso — e o loop não fecharia."""
    from app.services.email import enviar_email, html_moderno
    col = db.get(Candidato, r.candidato_id)
    if col is None or not col.email:
        return
    primeiro = (col.nome_completo or "").split()[0].title()
    titulo = r.titulo or (r.tipo.nome if r.tipo else "seu envio")
    from app.core.config import get_settings
    url = f"{get_settings().base_url.rstrip('/')}/meu"
    if acao == "devolvido":
        assunto = "Green House — precisamos de um ajuste no seu envio"
        linhas = [f"Olá, <strong>{primeiro}</strong>!",
                  f"Sobre <strong>{titulo}</strong>, precisamos de um ajuste:",
                  f"<em>{r.motivo_recusa}</em>",
                  f"Acesse <a href='{url}'>{url}</a> para corrigir e reenviar."]
        texto = (f"Olá, {primeiro}!\n\nSobre {titulo}, precisamos de um ajuste:\n"
                 f"{r.motivo_recusa}\n\nAcesse {url} para corrigir e reenviar.\n")
    else:
        assunto = "Green House — sobre o seu envio"
        linhas = [f"Olá, <strong>{primeiro}</strong>!",
                  f"<strong>{titulo}</strong> não pôde ser aceito.",
                  f"<em>{r.motivo_recusa}</em>",
                  "Em caso de dúvida, fale com o RH."]
        texto = (f"Olá, {primeiro}!\n\n{titulo} não pôde ser aceito.\n"
                 f"{r.motivo_recusa}\n\nEm caso de dúvida, fale com o RH.\n")
    try:
        enviar_email(col.email, assunto, texto, html_moderno(assunto, linhas))
    except Exception:
        pass  # aviso que falha não pode derrubar a decisão do RH
