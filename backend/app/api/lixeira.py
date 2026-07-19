"""Lixeira do painel: listar, restaurar e configurar o prazo de retenção.

Tudo que o RH exclui (postos, modelos de documento…) vira snapshot aqui e pode
ser restaurado dentro do prazo (padrão 60 dias, configurável). Passado o prazo,
o expurgo é definitivo — feito de forma preguiçosa a cada acesso/exclusão."""

import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.auth_rh import requer_rh
from app.core.db import get_db
from app.models.lixeira import ItemLixeira
from app.models.usuario_rh import UsuarioRH
from app.services.auditoria import registrar
from app.services.config_dinamica import gravar_config
from app.services.lixeira import dias_retencao, expurgar_vencidos

router = APIRouter(tags=["lixeira"], dependencies=[Depends(requer_rh)])


def _reconstruir(item: ItemLixeira):
    """Reconstrói o registro original a partir do snapshot."""
    from app.models.candidato import PostoServico
    from app.models.modelo_documento import ModeloDocumento
    classes = {"posto": PostoServico, "modelo_documento": ModeloDocumento}
    cls = classes.get(item.entidade)
    if cls is None:
        raise HTTPException(status_code=422, detail="entidade_desconhecida")
    dados = dict(item.dados)
    obj = cls()
    for col in cls.__table__.columns:
        if col.name not in dados:
            continue
        valor = dados[col.name]
        if valor is not None:
            tipo = str(col.type).lower()
            if "uuid" in tipo:
                valor = uuid.UUID(valor)
            elif "date" in tipo or "timestamp" in tipo:
                from datetime import datetime
                valor = datetime.fromisoformat(valor)
                if "timestamp" not in tipo and "time" not in tipo:
                    valor = valor.date()
        setattr(obj, col.name, valor)
    return obj


@router.get("/rh/lixeira")
def listar(db: Session = Depends(get_db)) -> dict:
    expurgar_vencidos(db)
    db.commit()
    itens = db.scalars(select(ItemLixeira)
                       .where(ItemLixeira.restaurado_em.is_(None))
                       .order_by(ItemLixeira.apagado_em.desc())).all()
    return {"dias_retencao": dias_retencao(db),
            "itens": [{"id": i.id, "entidade": i.entidade, "rotulo": i.rotulo,
                       "ator": i.ator, "apagado_em": i.apagado_em} for i in itens]}


@router.post("/rh/lixeira/{item_id}/restaurar")
def restaurar(item_id: uuid.UUID, db: Session = Depends(get_db),
              rh: UsuarioRH = Depends(requer_rh)) -> dict:
    item = db.get(ItemLixeira, item_id)
    if item is None or item.restaurado_em is not None:
        raise HTTPException(status_code=404, detail="item_nao_encontrado")
    obj = _reconstruir(item)
    if db.get(type(obj), obj.id) is not None:
        raise HTTPException(status_code=409, detail="registro_ja_existe")
    db.add(obj)
    from datetime import datetime, timezone
    item.restaurado_em = datetime.now(timezone.utc)
    registrar(db, "lixeira_restaurado", ator="rh", ator_detalhe=rh.email,
              detalhe={"entidade": item.entidade, "rotulo": item.rotulo})
    db.commit()
    return {"restaurado": True, "entidade": item.entidade, "rotulo": item.rotulo}


class ConfigLixeiraIn(BaseModel):
    dias: int


@router.put("/rh/lixeira/config")
def configurar(payload: ConfigLixeiraIn, db: Session = Depends(get_db),
               rh: UsuarioRH = Depends(requer_rh)) -> dict:
    if not (1 <= payload.dias <= 3650):
        raise HTTPException(status_code=422, detail="dias_fora_da_faixa")
    gravar_config(db, {"lixeira_dias": str(payload.dias)})
    registrar(db, "lixeira_config", ator="rh", ator_detalhe=rh.email,
              detalhe={"dias": payload.dias})
    db.commit()
    return {"dias_retencao": payload.dias}
