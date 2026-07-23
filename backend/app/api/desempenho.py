"""Gestão de Desempenho — painel do RH e da liderança (Onda C).

Primeira fatia: **Fatos Observados**. Rodam sozinhos, sem depender do
formulário — e é assim de propósito: quando a avaliação nascer, ela já abre com
os fatos do período ao lado, e o líder REVISA o que registrou em vez de
escrever do zero com a memória vazia.
"""

import uuid
from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Response, UploadFile
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.auth_rh import requer_rh
from app.core.db import get_db
from app.models.candidato import Candidato, PostoServico
from app.models.desempenho import (Avaliacao, CicloAvaliacao, FatoObservado,
                                   OcasiaoAvaliacao, RelacaoAvaliador,
                                   StatusAvaliacao, TipoFato)
from app.models.usuario_rh import UsuarioRH
from app.services import storage
from app.services.auditoria import registrar
from app.services.desempenho import (POSTURAS, PRAZO_MANIFESTACAO_D, completa,
                                     desvio_do_avaliador, fatos_do_periodo,
                                     formulario, media_competencias,
                                     prazo_manifestacao_vencido, radar,
                                     validar_respostas)

router = APIRouter(tags=["desempenho-rh"], dependencies=[Depends(requer_rh)])

EXT_ACEITAS = {"pdf", "jpg", "jpeg", "png", "heic", "webp", "mp4", "mov", "3gp",
               "doc", "docx"}
# Vídeo é o formato que o Bruno pediu, e é o que enche disco: um plantão inteiro
# gravado tem centenas de MB. 25 MB cobre um clipe curto de celular.
TAMANHO_MAX = 25 * 1024 * 1024
DURACAO_AVISO = "Prefira clipes curtos: o limite é 25 MB por anexo."


def _dump_fato(db: Session, f: FatoObservado, para_colaborador: bool = False) -> dict:
    col = db.get(Candidato, f.candidato_id)
    dados = {
        "id": str(f.id),
        "candidato_id": str(f.candidato_id),
        "colaborador": col.nome_completo if col else "—",
        "tipo": f.tipo.value,
        "descricao": f.descricao,
        "impacto": f.impacto,
        "ocorrido_em": f.ocorrido_em.isoformat() if f.ocorrido_em else None,
        "tem_anexo": bool(f.anexo_key),
        "anexo_nome": f.anexo_nome,
        "visivel_em": f.visivel_em.isoformat() if f.visivel_em else None,
        "criado_em": f.criado_em.isoformat() if f.criado_em else None,
        "usado_em_avaliacao": f.avaliacao_id is not None,
    }
    if not para_colaborador:
        # o autor aparece para o RH/liderança; para o avaliado, ver `_dump_para_colaborador`
        dados["autor"] = f.autor
    return dados


class FatoIn(BaseModel):
    candidato_id: uuid.UUID
    tipo: str = "positivo"
    descricao: str
    impacto: str | None = None
    ocorrido_em: str | None = None      # aaaa-mm-dd; vazio = hoje
    visivel_em: str | None = None       # atraso opcional até a conversa


def _data_de(txt: str | None) -> date | None:
    for fmt in ("%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime((txt or "").strip(), fmt).date()
        except ValueError:
            continue
    return None


@router.get("/rh/desempenho/fatos")
def listar_fatos(candidato_id: uuid.UUID | None = None, tipo: str | None = None,
                 desde: str | None = None, ate: str | None = None,
                 db: Session = Depends(get_db)) -> dict:
    """Fatos registrados. Filtro pesado SERVER-SIDE; o DashPlanilha refina em
    memória por cima (padrão da casa — isto cresce sem parar)."""
    consulta = select(FatoObservado)
    if candidato_id:
        consulta = consulta.where(FatoObservado.candidato_id == candidato_id)
    if tipo:
        consulta = consulta.where(FatoObservado.tipo.in_(
            [t.strip() for t in tipo.split(",") if t.strip()]))
    d1, d2 = _data_de(desde), _data_de(ate)
    if d1:
        consulta = consulta.where(FatoObservado.ocorrido_em >= d1)
    if d2:
        consulta = consulta.where(FatoObservado.ocorrido_em <= d2)
    fatos = db.scalars(consulta.order_by(FatoObservado.ocorrido_em.desc())).all()

    contagem = dict(db.execute(
        select(FatoObservado.tipo, func.count())
        .group_by(FatoObservado.tipo)).all())
    return {
        "fatos": [_dump_fato(db, f) for f in fatos],
        "metricas": {t.value: contagem.get(t, 0) for t in TipoFato},
        "limite_anexo_mb": TAMANHO_MAX // (1024 * 1024),
    }


@router.post("/rh/desempenho/fatos", status_code=201)
def criar_fato(payload: FatoIn, db: Session = Depends(get_db),
               rh: UsuarioRH = Depends(requer_rh)) -> dict:
    """Registra um fato. A descrição é obrigatória — sem ela não há fato, só
    rótulo, que é exatamente o que a cartilha (pág. 3) manda evitar."""
    col = db.get(Candidato, payload.candidato_id)
    if col is None:
        raise HTTPException(status_code=404, detail="colaborador_nao_encontrado")
    if not (payload.descricao or "").strip():
        raise HTTPException(status_code=422, detail="descricao_obrigatoria")
    if payload.tipo not in {t.value for t in TipoFato}:
        raise HTTPException(status_code=422, detail="tipo_invalido")
    ocorrido = _data_de(payload.ocorrido_em) or date.today()
    if ocorrido > date.today():
        raise HTTPException(status_code=422, detail="data_futura")

    f = FatoObservado(
        candidato_id=col.id, autor=rh.email, tipo=TipoFato(payload.tipo),
        descricao=payload.descricao.strip(),
        impacto=(payload.impacto or "").strip() or None,
        ocorrido_em=ocorrido, visivel_em=_data_de(payload.visivel_em))
    db.add(f)
    registrar(db, "fato_observado_registrado", ator="rh", ator_detalhe=rh.email,
              candidato_id=col.id, detalhe={"tipo": f.tipo.value})
    db.commit()
    db.refresh(f)
    return _dump_fato(db, f)


@router.put("/rh/desempenho/fatos/{fato_id}")
def editar_fato(fato_id: uuid.UUID, payload: FatoIn, db: Session = Depends(get_db),
                rh: UsuarioRH = Depends(requer_rh)) -> dict:
    """Só o AUTOR corrige o próprio registro, e só enquanto não foi usado numa
    avaliação — depois disso é peça de um documento fechado."""
    f = db.get(FatoObservado, fato_id)
    if f is None:
        raise HTTPException(status_code=404, detail="fato_nao_encontrado")
    if f.autor != rh.email:
        raise HTTPException(status_code=403, detail="somente_o_autor")
    if f.avaliacao_id is not None:
        raise HTTPException(status_code=409, detail="fato_ja_usado")
    if not (payload.descricao or "").strip():
        raise HTTPException(status_code=422, detail="descricao_obrigatoria")
    f.descricao = payload.descricao.strip()
    f.impacto = (payload.impacto or "").strip() or None
    if payload.tipo in {t.value for t in TipoFato}:
        f.tipo = TipoFato(payload.tipo)
    nova_data = _data_de(payload.ocorrido_em)
    if nova_data:
        if nova_data > date.today():
            raise HTTPException(status_code=422, detail="data_futura")
        f.ocorrido_em = nova_data
    registrar(db, "fato_observado_editado", ator="rh", ator_detalhe=rh.email,
              candidato_id=f.candidato_id)
    db.commit()
    db.refresh(f)
    return _dump_fato(db, f)


@router.delete("/rh/desempenho/fatos/{fato_id}", status_code=204)
def excluir_fato(fato_id: uuid.UUID, db: Session = Depends(get_db),
                 rh: UsuarioRH = Depends(requer_rh)) -> None:
    f = db.get(FatoObservado, fato_id)
    if f is None:
        raise HTTPException(status_code=404, detail="fato_nao_encontrado")
    if f.autor != rh.email:
        raise HTTPException(status_code=403, detail="somente_o_autor")
    if f.avaliacao_id is not None:
        raise HTTPException(status_code=409, detail="fato_ja_usado")
    if f.anexo_key:
        try:
            storage.remover(f.anexo_key)
        except Exception:
            pass
    registrar(db, "fato_observado_excluido", ator="rh", ator_detalhe=rh.email,
              candidato_id=f.candidato_id, detalhe={"descricao": f.descricao[:120]})
    db.delete(f)
    db.commit()


@router.post("/rh/desempenho/fatos/{fato_id}/anexo")
async def subir_anexo(fato_id: uuid.UUID, arquivo: UploadFile,
                      db: Session = Depends(get_db),
                      rh: UsuarioRH = Depends(requer_rh)) -> dict:
    """Anexo do fato (foto, vídeo curto, documento)."""
    f = db.get(FatoObservado, fato_id)
    if f is None:
        raise HTTPException(status_code=404, detail="fato_nao_encontrado")
    if f.autor != rh.email:
        raise HTTPException(status_code=403, detail="somente_o_autor")
    try:
        conteudo = await arquivo.read()
        if not conteudo:
            raise HTTPException(status_code=422, detail="arquivo_vazio")
        if len(conteudo) > TAMANHO_MAX:
            raise HTTPException(status_code=422, detail="arquivo_grande")
        ext = (arquivo.filename or "").rsplit(".", 1)[-1].lower()[:5]
        if ext not in EXT_ACEITAS:
            raise HTTPException(status_code=422, detail="formato_nao_aceito")
    finally:
        # Starlette faz spool em disco acima de ~1MB — sem o close, o temp file
        # ficaria no container (regra da casa).
        await arquivo.close()

    if f.anexo_key:
        try:
            storage.remover(f.anexo_key)
        except Exception:
            pass
    key = f"desempenho/fatos/{f.id}/anexo.{ext}"
    storage.salvar(key, conteudo, arquivo.content_type or "application/octet-stream")
    f.anexo_key = key
    f.anexo_nome = (arquivo.filename or "")[:200]
    f.anexo_tipo = arquivo.content_type
    f.anexo_tamanho = len(conteudo)
    db.commit()
    db.refresh(f)
    return _dump_fato(db, f)


@router.get("/rh/desempenho/fatos/{fato_id}/anexo")
def baixar_anexo(fato_id: uuid.UUID, db: Session = Depends(get_db)) -> Response:
    f = db.get(FatoObservado, fato_id)
    if f is None or not f.anexo_key:
        raise HTTPException(status_code=404, detail="anexo_nao_encontrado")
    try:
        dados = storage.ler(f.anexo_key)
    except Exception:
        raise HTTPException(status_code=404, detail="anexo_indisponivel")
    return Response(content=dados,
                    media_type=f.anexo_tipo or "application/octet-stream",
                    headers={"Content-Disposition":
                             f'inline; filename="{f.anexo_nome or "anexo"}"'})


@router.get("/rh/desempenho/formulario")
def ver_formulario() -> dict:
    """Escalas, indicadores, competências e recomendações da cartilha — o front
    desenha o formulário a partir daqui, sem duplicar os textos."""
    return formulario()


@router.get("/rh/desempenho/colaboradores")
def listar_colaboradores(db: Session = Depends(get_db)) -> dict:
    """Quem pode receber fato/avaliação: colaboradores ativos."""
    linhas = []
    for c in db.scalars(select(Candidato).where(Candidato.situacao == "ativo")
                        .order_by(Candidato.nome_completo)):
        posto = db.get(PostoServico, c.posto_servico_id) if c.posto_servico_id else None
        linhas.append({"id": str(c.id), "nome": c.nome_completo,
                       "cargo": c.cargo_funcao, "posto": posto.nome if posto else None})
    return {"colaboradores": linhas}


# ---------------------------------------------------------------------------
# Ciclos de avaliação — rotas ESPECÍFICAS antes das paramétricas
# ---------------------------------------------------------------------------


def _dump_ciclo(db: Session, ciclo: CicloAvaliacao) -> dict:
    total = db.scalar(select(func.count()).select_from(Avaliacao)
                      .where(Avaliacao.ciclo_id == ciclo.id)) or 0
    fechadas = db.scalar(select(func.count()).select_from(Avaliacao).where(
        Avaliacao.ciclo_id == ciclo.id,
        Avaliacao.status == StatusAvaliacao.homologada)) or 0
    return {"id": str(ciclo.id), "nome": ciclo.nome,
            "inicio_em": ciclo.inicio_em.isoformat(),
            "fim_em": ciclo.fim_em.isoformat(),
            "postos": ciclo.postos or [], "candidatos": ciclo.candidatos or [],
            "encerrado": ciclo.encerrado,
            "avaliacoes": total, "homologadas": fechadas}


class CicloIn(BaseModel):
    nome: str
    inicio_em: str
    fim_em: str
    postos: list[str] | None = None
    candidatos: list[str] | None = None


@router.get("/rh/desempenho/ciclos")
def listar_ciclos(db: Session = Depends(get_db)) -> dict:
    ciclos = db.scalars(select(CicloAvaliacao)
                        .order_by(CicloAvaliacao.inicio_em.desc())).all()
    return {"ciclos": [_dump_ciclo(db, x) for x in ciclos]}


@router.post("/rh/desempenho/ciclos", status_code=201)
def criar_ciclo(payload: CicloIn, db: Session = Depends(get_db),
                rh: UsuarioRH = Depends(requer_rh)) -> dict:
    """4 ciclos por ano (decisão do Bruno), com datas configuráveis — geral, por
    posto ou individual. O escopo vazio significa "todo mundo"."""
    inicio, fim = _data_de(payload.inicio_em), _data_de(payload.fim_em)
    if inicio is None or fim is None:
        raise HTTPException(status_code=422, detail="data_invalida")
    if fim < inicio:
        raise HTTPException(status_code=422, detail="fim_antes_do_inicio")
    if not (payload.nome or "").strip():
        raise HTTPException(status_code=422, detail="nome_obrigatorio")
    ciclo = CicloAvaliacao(nome=payload.nome.strip(), inicio_em=inicio, fim_em=fim,
                           postos=payload.postos or None,
                           candidatos=payload.candidatos or None)
    db.add(ciclo)
    registrar(db, "ciclo_avaliacao_criado", ator="rh", ator_detalhe=rh.email,
              detalhe={"nome": ciclo.nome})
    db.commit()
    db.refresh(ciclo)
    return _dump_ciclo(db, ciclo)


@router.post("/rh/desempenho/ciclos/{ciclo_id}/encerrar")
def encerrar_ciclo(ciclo_id: uuid.UUID, db: Session = Depends(get_db),
                   rh: UsuarioRH = Depends(requer_rh)) -> dict:
    ciclo = db.get(CicloAvaliacao, ciclo_id)
    if ciclo is None:
        raise HTTPException(status_code=404, detail="ciclo_nao_encontrado")
    ciclo.encerrado = True
    registrar(db, "ciclo_avaliacao_encerrado", ator="rh", ator_detalhe=rh.email,
              detalhe={"nome": ciclo.nome})
    db.commit()
    db.refresh(ciclo)
    return _dump_ciclo(db, ciclo)


# ---------------------------------------------------------------------------
# Avaliações
# ---------------------------------------------------------------------------


def _dump_avaliacao(db: Session, a: Avaliacao, com_fatos: bool = False) -> dict:
    col = db.get(Candidato, a.candidato_id)
    posto = (db.get(PostoServico, col.posto_servico_id)
             if col and col.posto_servico_id else None)
    dados = {
        "id": str(a.id),
        "candidato_id": str(a.candidato_id),
        "colaborador": col.nome_completo if col else "—",
        "matricula": col.matricula if col else None,
        "cargo": col.cargo_funcao if col else None,
        "posto": posto.nome if posto else None,
        "data_admissao": (col.data_admissao.isoformat()
                          if col and col.data_admissao else None),
        "avaliador": a.avaliador,
        "relacao": a.relacao.value,
        "ocasiao": a.ocasiao.value,
        "ocasiao_outro": a.ocasiao_outro,
        "status": a.status.value,
        "ciclo_id": str(a.ciclo_id) if a.ciclo_id else None,
        "periodo_inicio": a.periodo_inicio.isoformat() if a.periodo_inicio else None,
        "periodo_fim": a.periodo_fim.isoformat() if a.periodo_fim else None,
        "convocacao_em": a.convocacao_em.isoformat() if a.convocacao_em else None,
        "indicadores": a.indicadores or {},
        "competencias": a.competencias or {},
        "pontos_fortes": a.pontos_fortes,
        "pontos_desenvolver": a.pontos_desenvolver,
        "pdi": a.pdi or [],
        "recomendacao": a.recomendacao,
        "recomendacao_data": (a.recomendacao_data.isoformat()
                              if a.recomendacao_data else None),
        "justificativa": a.justificativa,
        "postura": a.postura,
        "postura_observacao": a.postura_observacao,
        "feedback_em": a.feedback_em.isoformat() if a.feedback_em else None,
        "manifestacao": a.manifestacao,
        "manifestacao_em": (a.manifestacao_em.isoformat()
                            if a.manifestacao_em else None),
        "conclusao_aplicador": a.conclusao_aplicador,
        "homologado_por": a.homologado_por,
        "homologado_em": a.homologado_em.isoformat() if a.homologado_em else None,
        "media": media_competencias(a.competencias),
        "faltando": completa(a),
        "criado_em": a.criado_em.isoformat() if a.criado_em else None,
    }
    if com_fatos:
        # Os fatos do período aparecem AO LADO do formulário: o líder revisa o
        # que já registrou em vez de escrever do zero com a memória vazia.
        dados["fatos"] = [
            {"id": str(f.id), "tipo": f.tipo.value, "descricao": f.descricao,
             "impacto": f.impacto, "autor": f.autor,
             "ocorrido_em": f.ocorrido_em.isoformat() if f.ocorrido_em else None}
            for f in fatos_do_periodo(db, a.candidato_id,
                                      a.periodo_inicio, a.periodo_fim)]
    return dados


class AvaliacaoIn(BaseModel):
    candidato_id: uuid.UUID
    ciclo_id: uuid.UUID | None = None
    relacao: str = "vertical"
    ocasiao: str = "periodica"
    ocasiao_outro: str | None = None
    periodo_inicio: str | None = None
    periodo_fim: str | None = None
    convocacao_em: str | None = None


@router.get("/rh/desempenho/avaliacoes")
def listar_avaliacoes(status: str | None = None, ciclo_id: uuid.UUID | None = None,
                      candidato_id: uuid.UUID | None = None,
                      minhas: bool = False, db: Session = Depends(get_db),
                      rh: UsuarioRH = Depends(requer_rh)) -> dict:
    consulta = select(Avaliacao)
    if status:
        consulta = consulta.where(Avaliacao.status.in_(
            [s.strip() for s in status.split(",") if s.strip()]))
    if ciclo_id:
        consulta = consulta.where(Avaliacao.ciclo_id == ciclo_id)
    if candidato_id:
        consulta = consulta.where(Avaliacao.candidato_id == candidato_id)
    if minhas:
        consulta = consulta.where(Avaliacao.avaliador == rh.email)
    avaliacoes = db.scalars(consulta.order_by(Avaliacao.criado_em.desc())).all()
    contagem = dict(db.execute(select(Avaliacao.status, func.count())
                               .group_by(Avaliacao.status)).all())
    return {"avaliacoes": [_dump_avaliacao(db, a) for a in avaliacoes],
            "metricas": {s.value: contagem.get(s, 0) for s in StatusAvaliacao}}


@router.post("/rh/desempenho/avaliacoes", status_code=201)
def criar_avaliacao(payload: AvaliacaoIn, db: Session = Depends(get_db),
                    rh: UsuarioRH = Depends(requer_rh)) -> dict:
    col = db.get(Candidato, payload.candidato_id)
    if col is None:
        raise HTTPException(status_code=404, detail="colaborador_nao_encontrado")
    if payload.relacao not in {r.value for r in RelacaoAvaliador}:
        raise HTTPException(status_code=422, detail="relacao_invalida")
    if payload.ocasiao not in {o.value for o in OcasiaoAvaliacao}:
        raise HTTPException(status_code=422, detail="ocasiao_invalida")
    if col.id == payload.candidato_id and payload.relacao == "autoavaliacao":
        pass  # autoavaliação é do próprio, sem restrição extra
    a = Avaliacao(
        candidato_id=col.id, ciclo_id=payload.ciclo_id, avaliador=rh.email,
        relacao=RelacaoAvaliador(payload.relacao),
        ocasiao=OcasiaoAvaliacao(payload.ocasiao),
        ocasiao_outro=(payload.ocasiao_outro or "").strip() or None,
        periodo_inicio=_data_de(payload.periodo_inicio),
        periodo_fim=_data_de(payload.periodo_fim),
        convocacao_em=_data_de(payload.convocacao_em),
        status=StatusAvaliacao.rascunho)
    db.add(a)
    registrar(db, "avaliacao_criada", ator="rh", ator_detalhe=rh.email,
              candidato_id=col.id, detalhe={"ocasiao": a.ocasiao.value,
                                            "relacao": a.relacao.value})
    db.commit()
    db.refresh(a)
    return _dump_avaliacao(db, a, com_fatos=True)


@router.get("/rh/desempenho/avaliacoes/{avaliacao_id}")
def ver_avaliacao(avaliacao_id: uuid.UUID, db: Session = Depends(get_db)) -> dict:
    a = db.get(Avaliacao, avaliacao_id)
    if a is None:
        raise HTTPException(status_code=404, detail="avaliacao_nao_encontrada")
    return _dump_avaliacao(db, a, com_fatos=True)


class RespostasIn(BaseModel):
    indicadores: dict | None = None
    competencias: dict | None = None
    pontos_fortes: str | None = None
    pontos_desenvolver: str | None = None
    pdi: list | None = None
    recomendacao: str | None = None
    recomendacao_data: str | None = None
    justificativa: str | None = None
    periodo_inicio: str | None = None
    periodo_fim: str | None = None


@router.put("/rh/desempenho/avaliacoes/{avaliacao_id}")
def salvar_avaliacao(avaliacao_id: uuid.UUID, payload: RespostasIn,
                     db: Session = Depends(get_db),
                     rh: UsuarioRH = Depends(requer_rh)) -> dict:
    """Salva o preenchimento. Só o AVALIADOR mexe, e só até enviar."""
    a = db.get(Avaliacao, avaliacao_id)
    if a is None:
        raise HTTPException(status_code=404, detail="avaliacao_nao_encontrada")
    if a.avaliador != rh.email:
        raise HTTPException(status_code=403, detail="somente_o_avaliador")
    if a.status != StatusAvaliacao.rascunho:
        raise HTTPException(status_code=409, detail="avaliacao_enviada")
    erros = validar_respostas(payload.indicadores, payload.competencias)
    if erros:
        raise HTTPException(status_code=422, detail={"erros": erros})

    if payload.indicadores is not None:
        a.indicadores = payload.indicadores
    if payload.competencias is not None:
        a.competencias = payload.competencias
    for campo in ("pontos_fortes", "pontos_desenvolver", "justificativa"):
        valor = getattr(payload, campo)
        if valor is not None:
            setattr(a, campo, valor.strip() or None)
    if payload.pdi is not None:
        a.pdi = payload.pdi
    if payload.recomendacao is not None:
        a.recomendacao = payload.recomendacao.strip() or None
    if payload.recomendacao_data is not None:
        a.recomendacao_data = _data_de(payload.recomendacao_data)
    if payload.periodo_inicio is not None:
        a.periodo_inicio = _data_de(payload.periodo_inicio)
    if payload.periodo_fim is not None:
        a.periodo_fim = _data_de(payload.periodo_fim)
    a.atualizado_em = datetime.now(timezone.utc)
    db.commit()
    db.refresh(a)
    return _dump_avaliacao(db, a, com_fatos=True)


@router.post("/rh/desempenho/avaliacoes/{avaliacao_id}/enviar")
def enviar_avaliacao(avaliacao_id: uuid.UUID, db: Session = Depends(get_db),
                     rh: UsuarioRH = Depends(requer_rh)) -> dict:
    """Fecha o preenchimento. Vincula os fatos do período usados — depois disso
    eles viram imutáveis, porque passam a ser peça de um documento."""
    a = db.get(Avaliacao, avaliacao_id)
    if a is None:
        raise HTTPException(status_code=404, detail="avaliacao_nao_encontrada")
    if a.avaliador != rh.email:
        raise HTTPException(status_code=403, detail="somente_o_avaliador")
    if a.status != StatusAvaliacao.rascunho:
        raise HTTPException(status_code=409, detail="avaliacao_enviada")
    faltando = completa(a)
    if faltando:
        raise HTTPException(status_code=422,
                            detail={"erro": "incompleta", "faltando": faltando})
    a.status = StatusAvaliacao.preenchida
    a.atualizado_em = datetime.now(timezone.utc)
    for f in fatos_do_periodo(db, a.candidato_id, a.periodo_inicio, a.periodo_fim):
        if f.avaliacao_id is None:
            f.avaliacao_id = a.id
    registrar(db, "avaliacao_preenchida", ator="rh", ator_detalhe=rh.email,
              candidato_id=a.candidato_id,
              detalhe={"recomendacao": a.recomendacao,
                       "media": media_competencias(a.competencias)})
    db.commit()
    db.refresh(a)
    return _dump_avaliacao(db, a)


class FeedbackIn(BaseModel):
    feedback_em: str
    postura: str
    postura_observacao: str | None = None


@router.post("/rh/desempenho/avaliacoes/{avaliacao_id}/feedback")
def registrar_feedback(avaliacao_id: uuid.UUID, payload: FeedbackIn,
                       db: Session = Depends(get_db),
                       rh: UsuarioRH = Depends(requer_rh)) -> dict:
    """Seção 8 — a CONVERSA aconteceu.

    Este passo não pode ser pulado: a cartilha (pág. 5) manda dar o feedback
    presencialmente, em local reservado. Um sistema onde o gestor preenche,
    clica em enviar e a pessoa recebe a nota por e-mail não digitalizou a
    cartilha — matou o que ela pede.
    """
    a = db.get(Avaliacao, avaliacao_id)
    if a is None:
        raise HTTPException(status_code=404, detail="avaliacao_nao_encontrada")
    if a.status != StatusAvaliacao.preenchida:
        raise HTTPException(status_code=409, detail="fora_de_ordem")
    if payload.postura not in {p["valor"] for p in POSTURAS}:
        raise HTTPException(status_code=422, detail="postura_invalida")
    data = _data_de(payload.feedback_em)
    if data is None:
        raise HTTPException(status_code=422, detail="data_invalida")
    if data > date.today():
        raise HTTPException(status_code=422, detail="data_futura")
    a.feedback_em = data
    a.postura = payload.postura
    a.postura_observacao = (payload.postura_observacao or "").strip() or None
    a.status = StatusAvaliacao.feedback_dado
    a.atualizado_em = datetime.now(timezone.utc)
    registrar(db, "avaliacao_feedback_dado", ator="rh", ator_detalhe=rh.email,
              candidato_id=a.candidato_id, detalhe={"postura": a.postura})
    db.commit()
    _avisar_manifestacao(db, a)
    db.refresh(a)
    return _dump_avaliacao(db, a)


class HomologarIn(BaseModel):
    conclusao_aplicador: str | None = None
    forcar: bool = False   # homologar sem esperar a manifestação


@router.post("/rh/desempenho/avaliacoes/{avaliacao_id}/homologar")
def homologar(avaliacao_id: uuid.UUID, payload: HomologarIn,
              db: Session = Depends(get_db),
              rh: UsuarioRH = Depends(requer_rh)) -> dict:
    """Seção 10 + fecho. O RH homologa (decisão do Bruno).

    A manifestação do colaborador (seção 9) tem um PRAZO: sem ele, o direito de
    resposta viraria letra morta — bastaria homologar antes de a pessoa ler. Se
    o prazo passou, `forcar` libera e o motivo fica na auditoria.
    """
    a = db.get(Avaliacao, avaliacao_id)
    if a is None:
        raise HTTPException(status_code=404, detail="avaliacao_nao_encontrada")
    if a.status not in (StatusAvaliacao.feedback_dado, StatusAvaliacao.manifestada):
        raise HTTPException(status_code=409, detail="fora_de_ordem")
    if (a.status == StatusAvaliacao.feedback_dado and not payload.forcar
            and not prazo_manifestacao_vencido(a)):
        raise HTTPException(status_code=409, detail={
            "erro": "aguardando_manifestacao",
            "prazo_dias": PRAZO_MANIFESTACAO_D,
            "vence_em": (a.feedback_em + timedelta(days=PRAZO_MANIFESTACAO_D)
                         ).isoformat() if a.feedback_em else None})
    a.conclusao_aplicador = (payload.conclusao_aplicador or "").strip() or None
    a.status = StatusAvaliacao.homologada
    a.homologado_por = rh.email
    a.homologado_em = datetime.now(timezone.utc)
    registrar(db, "avaliacao_homologada", ator="rh", ator_detalhe=rh.email,
              candidato_id=a.candidato_id,
              detalhe={"sem_manifestacao": a.manifestacao is None,
                       "forcado": payload.forcar})
    db.commit()
    db.refresh(a)
    return _dump_avaliacao(db, a)


@router.get("/rh/desempenho/avaliadores/{email}/desvio")
def ver_desvio(email: str, ciclo_id: uuid.UUID | None = None,
               db: Session = Depends(get_db)) -> dict:
    """Quanto este avaliador difere da média — para o HOMOLOGADOR decidir.
    Não altera nota nenhuma (ver `desvio_do_avaliador`)."""
    return {"desvio": desvio_do_avaliador(db, email, ciclo_id)}


@router.get("/rh/desempenho/colaboradores/{candidato_id}/radar")
def ver_radar(candidato_id: uuid.UUID, ciclo_id: uuid.UUID | None = None,
              db: Session = Depends(get_db)) -> dict:
    """8 eixos da cartilha. O horizontal é suprimido com menos de 2
    respondentes — agregado de um é o individual com outro nome."""
    return radar(db, candidato_id, ciclo_id)


def _avisar_manifestacao(db: Session, a: Avaliacao) -> None:
    """Avisa o colaborador de que a avaliação está disponível e ele pode
    registrar a manifestação (seção 9)."""
    from app.core.config import get_settings
    from app.services.email import enviar_email, html_moderno
    col = db.get(Candidato, a.candidato_id)
    if col is None or not col.email:
        return
    primeiro = (col.nome_completo or "").split()[0].title()
    url = f"{get_settings().base_url.rstrip('/')}/meu"
    prazo = (a.feedback_em + timedelta(days=PRAZO_MANIFESTACAO_D)
             ).strftime("%d/%m/%Y") if a.feedback_em else ""
    try:
        enviar_email(
            col.email, "Green House — sua avaliação está disponível",
            f"Olá, {primeiro}!\n\nSua avaliação de desempenho foi registrada após a "
            f"conversa de feedback. Você pode ler e, se quiser, escrever a sua "
            f"manifestação até {prazo}.\n\nAcesse {url}.\n\n"
            "Registrar sua opinião é um direito seu — concordando ou não.\n",
            html_moderno(
                "Sua avaliação está disponível",
                [f"Olá, <strong>{primeiro}</strong>!",
                 "Sua avaliação de desempenho foi registrada após a conversa de "
                 "feedback.",
                 f"Você pode ler e escrever a sua <strong>manifestação</strong> "
                 f"até <strong>{prazo}</strong> — concordando ou não.",
                 "Registrar sua opinião é um direito seu."],
                botao_texto="Ver minha avaliação", botao_url=url))
    except Exception:
        pass


