"""Logs dos serviços na tela do RH (v2.29).

Pedido do Bruno em 2026-07-30: *"quero muito a tela de logs no painel"* — para
não depender de SSH quando alguém liga dizendo que não consegue entrar. Foi
exatamente o que aconteceu no incidente do Defender (v2.28): o diagnóstico
saiu do log, e ele teve que abrir terminal na VPS para me mandar.

Mecânica e decisões de LGPD em `services/logs.py`.
"""

import logging
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.auth_rh import exige, requer_rh
from app.core.db import get_db
from app.models.usuario_rh import UsuarioRH
from app.services import logs as svc
from app.services.auditoria import registrar
from app.services.config_dinamica import gravar_config

log = logging.getLogger(__name__)

router = APIRouter(tags=["logs"], dependencies=[Depends(requer_rh)])


@router.get("/rh/logs/servicos")
def listar_servicos(db: Session = Depends(get_db),
    _rh: UsuarioRH = Depends(exige("dados:logs"))) -> dict:
    """Serviços com log, os dias guardados de cada um e a retenção atual."""
    nomes = svc.servicos()
    return {
        "servicos": [{"nome": n, "dias": svc.dias_disponiveis(n)} for n in nomes],
        "retencao_dias": svc.retencao_dias(db),
        "diretorio": str(svc.DIR_LOGS),
        # Sem arquivo nenhum quase sempre significa volume não montado — dizer
        # isso na tela evita concluir "não houve log" quando é configuração.
        "ativo": bool(nomes),
    }


@router.get("/rh/logs/{servico}")
def ler_servico(servico: str, dia: str | None = None, busca: str | None = None,
                nivel: str | None = None, limite: int = 500,
    _rh: UsuarioRH = Depends(exige("dados:logs"))) -> dict:
    try:
        return svc.ler(servico, dia=dia, busca=busca, nivel=nivel, limite=limite)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/rh/logs/{servico}/baixar")
def baixar(servico: str, dia: str | None = None,
           db: Session = Depends(get_db),
           rh: UsuarioRH = Depends(exige("dados:logs"))) -> Response:
    """Arquivo inteiro em .txt.

    Fica na AUDITORIA: o arquivo carrega CPF, e-mail e nome de gente real, e
    baixar é tirar isso do servidor — quem levou e quando tem que ficar
    registrado, como em qualquer export de dado pessoal do sistema.
    """
    try:
        bruto = svc.texto_para_download(servico, dia)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="log_nao_encontrado") from exc
    registrar(db, "logs_baixados", ator="rh", ator_detalhe=rh.email,
              detalhe={"servico": servico, "dia": dia or date.today().isoformat()})
    db.commit()
    nome = f"{servico}-{dia or date.today().isoformat()}.txt"
    return Response(content=bruto, media_type="text/plain; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="{nome}"'})


class RetencaoIn(BaseModel):
    # 0 = indeterminado (guardar para sempre), pedido do Bruno.
    dias: int = Field(ge=0, le=svc.RETENCAO_MAX_DIAS)


@router.put("/rh/logs/retencao")
def definir_retencao(payload: RetencaoIn, db: Session = Depends(get_db),
                     rh: UsuarioRH = Depends(exige("config:escrever"))) -> dict:
    gravar_config(db, {"logs_retencao_dias": str(payload.dias)})
    registrar(db, "logs_retencao_alterada", ator="rh", ator_detalhe=rh.email,
              detalhe={"dias": payload.dias})
    db.commit()
    return {"retencao_dias": payload.dias}


@router.post("/rh/logs/enviar-agora")
def enviar_agora(db: Session = Depends(get_db),
                 rh: UsuarioRH = Depends(exige("dados:logs"))) -> dict:
    """Dispara o e-mail dos logs na hora — para conferir se chega a quem deve,
    sem esperar a próxima janela de 6h."""
    from app.workers.logs_email import rodar
    enviou = rodar(forcar=True)
    registrar(db, "logs_enviados_manual", ator="rh", ator_detalhe=rh.email)
    db.commit()
    return {"enviado": bool(enviou)}
