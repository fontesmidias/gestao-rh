"""Telemetria de uso — coleta pública e consulta pelo RH (v2.24).

A coleta é PÚBLICA por necessidade: o candidato não tem login, e é justamente o
aparelho dele que precisamos observar. Por isso a rota de ingestão é a mais
defendida do módulo — rate limit, teto de lote, e nada do que a pessoa digita
entra (ver `services/telemetria.py`).

A consulta é restrita ao RH, como todo o resto do painel.
"""

import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.auth_rh import requer_rh
from app.core.config import ip_do_cliente
from app.core.db import get_db
from app.models.usuario_rh import UsuarioRH
from app.services import telemetria as tel
from app.services.limite import exigir

router = APIRouter(tags=["telemetria"])


class EventoIn(BaseModel):
    evento: str = Field(max_length=60)
    tipo: str = "jornada"
    pagina: str | None = Field(default=None, max_length=120)
    duracao_ms: int | None = None
    detalhe: dict | None = None
    versao: str | None = Field(default=None, max_length=40)


class LoteIn(BaseModel):
    eventos: list[EventoIn] = Field(default_factory=list, max_length=50)
    sessao: str | None = Field(default=None, max_length=40)
    # Quem está usando. O cliente DECLARA a origem, mas ela é conferida contra
    # o vínculo: um payload dizendo "sou RH" sem token não vira registro de RH.
    origem: str = "publico"
    # Token do link mágico, quando é candidato: identifica sem exigir login.
    token: str | None = Field(default=None, max_length=100)
    talento_id: uuid.UUID | None = None


@router.post("/telemetria", status_code=202)
def coletar(payload: LoteIn, request: Request,
            db: Session = Depends(get_db)) -> dict:
    """Recebe um lote do navegador. Responde 202 e NUNCA falha por telemetria.

    Devolve 202 (aceito) em vez de 200: o processamento é best-effort e o
    cliente não deve tomar decisão nenhuma com base nesta resposta.
    """
    ip = ip_do_cliente(request) or "?"
    # Rate limit por IP: a rota é pública. Generoso o bastante para uma sessão
    # real (que manda lotes esparsos) e apertado para um laço.
    try:
        exigir(f"telemetria:{ip}", maximo=60, janela_s=60)
    except HTTPException:
        # Nem 429 devolvemos: excesso é descartado em silêncio, porque
        # telemetria não pode virar canal de erro para quem está usando.
        return {"aceitos": 0}

    candidato_id = None
    origem = payload.origem
    if payload.token:
        from app.services.magic_link import resolver_token
        cand = resolver_token(db, payload.token)
        if cand is not None:
            candidato_id = cand.id
            origem = "candidato"
        else:
            origem = "publico"      # token inválido não vira evento de ninguém

    # `rh` só é aceito com autenticação — senão qualquer um poluiria a visão do
    # painel fingindo ser o RH.
    if origem == "rh":
        origem = "publico"

    n = tel.registrar_eventos(
        db, [e.model_dump() for e in payload.eventos],
        origem=origem, candidato_id=candidato_id, talento_id=payload.talento_id,
        sessao=payload.sessao, user_agent=request.headers.get("user-agent"), ip=ip,
    )
    if n:
        db.commit()
    return {"aceitos": n}


@router.post("/rh/telemetria", status_code=202)
def coletar_rh(payload: LoteIn, request: Request, db: Session = Depends(get_db),
               rh: UsuarioRH = Depends(requer_rh)) -> dict:
    """Coleta do PAINEL: mesma mecânica, mas com o usuário identificado."""
    n = tel.registrar_eventos(
        db, [e.model_dump() for e in payload.eventos],
        origem="rh", usuario_rh=rh.email, sessao=payload.sessao,
        user_agent=request.headers.get("user-agent"),
        ip=ip_do_cliente(request),
    )
    if n:
        db.commit()
    return {"aceitos": n}


# ---------------------------------------------------------------------------
# Consulta (RH)
# ---------------------------------------------------------------------------


@router.get("/rh/telemetria/resumo")
def resumo(dias: int = 7, db: Session = Depends(get_db),
           _rh: UsuarioRH = Depends(requer_rh)) -> dict:
    """Painel de cima da aba: totais, erros agrupados, páginas lentas, fricção."""
    return tel.resumo(db, dias=min(max(dias, 1), 365))


@router.get("/rh/telemetria")
def listar(tipo: str | None = None, origem: str | None = None,
           evento: str | None = None, pagina: str | None = None,
           dias: int | None = None, limite: int = 300,
           db: Session = Depends(get_db),
           _rh: UsuarioRH = Depends(requer_rh)) -> list[dict]:
    desde = (datetime.now(timezone.utc) - timedelta(days=dias)) if dias else None
    return tel.listar(db, tipo=tipo, origem=origem, evento=evento,
                      pagina=pagina, desde=desde, limite=limite)


@router.get("/rh/telemetria/pessoa")
def da_pessoa(candidato_id: uuid.UUID | None = None,
              talento_id: uuid.UUID | None = None, limite: int = 200,
              db: Session = Depends(get_db),
              _rh: UsuarioRH = Depends(requer_rh)) -> list[dict]:
    """Telemetria individualizada — o painel que aparece na ficha da pessoa.

    Quando só um dos ids vem, descobrimos o par pelo mini-CRM: a pessoa
    atravessa talento → candidato e a memória segue junto.
    """
    if candidato_id is None and talento_id is None:
        raise HTTPException(status_code=422, detail="informe_candidato_ou_talento")

    if candidato_id is not None and talento_id is None:
        from app.models.talento import Talento
        from sqlalchemy import select
        talento_id = db.scalar(
            select(Talento.id).where(Talento.candidato_id == candidato_id))
    elif talento_id is not None and candidato_id is None:
        from app.models.talento import Talento
        talento = db.get(Talento, talento_id)
        candidato_id = talento.candidato_id if talento else None

    return tel.da_pessoa(db, candidato_id=candidato_id, talento_id=talento_id,
                         limite=limite)


@router.get("/rh/telemetria/retencao")
def ver_retencao(db: Session = Depends(get_db),
                 _rh: UsuarioRH = Depends(requer_rh)) -> dict:
    return {"dias": tel.retencao_dias(db), "padrao": tel.RETENCAO_PADRAO_DIAS}


class RetencaoIn(BaseModel):
    dias: int = Field(ge=1, le=3650)


@router.put("/rh/telemetria/retencao")
def salvar_retencao(payload: RetencaoIn, db: Session = Depends(get_db),
                    rh: UsuarioRH = Depends(requer_rh)) -> dict:
    """Prazo de retenção, configurável pelo painel (pedido do Bruno)."""
    from app.services.auditoria import registrar
    from app.services.config_dinamica import gravar_config

    gravar_config(db, {"telemetria_retencao_dias": str(payload.dias)})
    registrar(db, "telemetria_retencao_alterada", ator="rh", ator_detalhe=rh.email,
              detalhe={"dias": payload.dias})
    db.commit()
    return {"dias": payload.dias}


# ---------------------------------------------------------------------------
# Regras de alerta (v2.25) — o sistema avisa em vez de esperar a pergunta
# ---------------------------------------------------------------------------


class RegraIn(BaseModel):
    tipo: str
    nome: str = Field(max_length=120)
    ativa: bool = True
    limiar: int = Field(default=1, ge=1, le=10_000_000)
    janela_min: int = Field(default=60, ge=5, le=10_080)     # 5 min a 7 dias
    # Silêncio mínimo de 5 min: zero transformaria o alerta em enxurrada a cada
    # verificação, e enxurrada não é lida. É o limite que protege o recurso.
    silencio_min: int = Field(default=60, ge=5, le=10_080)
    origem: str | None = Field(default=None, max_length=20)
    pagina: str | None = Field(default=None, max_length=120)
    evento: str | None = Field(default=None, max_length=60)


@router.get("/rh/telemetria/alertas/regras")
def listar_regras(db: Session = Depends(get_db),
                  _rh: UsuarioRH = Depends(requer_rh)) -> list[dict]:
    from app.models.alerta import RegraAlerta
    from sqlalchemy import select as _select
    regras = db.scalars(_select(RegraAlerta).order_by(RegraAlerta.criado_em)).all()
    return [{
        "id": r.id, "tipo": r.tipo, "nome": r.nome, "ativa": r.ativa,
        "limiar": r.limiar, "janela_min": r.janela_min,
        "silencio_min": r.silencio_min, "origem": r.origem,
        "pagina": r.pagina, "evento": r.evento,
    } for r in regras]


@router.post("/rh/telemetria/alertas/regras", status_code=201)
def criar_regra(payload: RegraIn, db: Session = Depends(get_db),
                rh: UsuarioRH = Depends(requer_rh)) -> dict:
    from app.models.alerta import RegraAlerta, TipoAlerta
    from app.services.auditoria import registrar

    if payload.tipo not in {t.value for t in TipoAlerta}:
        raise HTTPException(status_code=422, detail="tipo_invalido")
    regra = RegraAlerta(**payload.model_dump())
    db.add(regra)
    registrar(db, "alerta_regra_criada", ator="rh", ator_detalhe=rh.email,
              detalhe={"nome": payload.nome, "tipo": payload.tipo})
    db.commit()
    db.refresh(regra)
    return {"id": regra.id}


@router.put("/rh/telemetria/alertas/regras/{regra_id}")
def editar_regra(regra_id: uuid.UUID, payload: RegraIn,
                 db: Session = Depends(get_db),
                 rh: UsuarioRH = Depends(requer_rh)) -> dict:
    from app.models.alerta import RegraAlerta, TipoAlerta
    from app.services.auditoria import registrar

    regra = db.get(RegraAlerta, regra_id)
    if regra is None:
        raise HTTPException(status_code=404, detail="regra_nao_encontrada")
    if payload.tipo not in {t.value for t in TipoAlerta}:
        raise HTTPException(status_code=422, detail="tipo_invalido")
    for campo, valor in payload.model_dump().items():
        setattr(regra, campo, valor)
    registrar(db, "alerta_regra_editada", ator="rh", ator_detalhe=rh.email,
              detalhe={"nome": payload.nome})
    db.commit()
    return {"id": regra.id}


@router.delete("/rh/telemetria/alertas/regras/{regra_id}", status_code=204)
def excluir_regra(regra_id: uuid.UUID, db: Session = Depends(get_db),
                  rh: UsuarioRH = Depends(requer_rh)) -> None:
    from app.models.alerta import RegraAlerta
    from app.services.auditoria import registrar

    regra = db.get(RegraAlerta, regra_id)
    if regra is None:
        raise HTTPException(status_code=404, detail="regra_nao_encontrada")
    registrar(db, "alerta_regra_excluida", ator="rh", ator_detalhe=rh.email,
              detalhe={"nome": regra.nome})
    db.delete(regra)
    db.commit()


@router.post("/rh/telemetria/alertas/testar")
def testar_regras(db: Session = Depends(get_db),
                  _rh: UsuarioRH = Depends(requer_rh)) -> list[dict]:
    """"O que dispararia agora?" — sem enviar e sem gravar histórico.

    Não consumir o silêncio nem o histórico é essencial: testar uma regra não
    pode fazer o problema REAL deixar de avisar depois (um `erro_novo` marcado
    como já visto nunca mais dispararia).
    """
    from app.services.alertas import avaliar
    disparos = avaliar(db, enviar=False)
    db.rollback()   # garantia extra: nada do teste persiste
    return [{
        "regra": d["regra"],
        "tipo": d["tipo"].value if hasattr(d["tipo"], "value") else d["tipo"],
        "total": d["total"],
        "itens": [i["texto"] for i in d["itens"]],
    } for d in disparos]


@router.get("/rh/telemetria/alertas/historico")
def historico_alertas(limite: int = 100, db: Session = Depends(get_db),
                      _rh: UsuarioRH = Depends(requer_rh)) -> list[dict]:
    """Alertas já disparados — a prova de que o vigia está acordado.

    Sem esta lista, caixa de entrada silenciosa seria ambígua: "não houve
    problema" e "o alerta quebrou" pareceriam a mesma coisa.
    """
    from app.services.alertas import historico
    return historico(db, limite=limite)


class ExpurgoIn(BaseModel):
    """Expurgo cirúrgico por intervalo (pedido do Bruno, 2026-07-29)."""

    desde: datetime | None = None
    ate: datetime | None = None


@router.post("/rh/telemetria/expurgar")
def expurgar(payload: ExpurgoIn, db: Session = Depends(get_db),
             rh: UsuarioRH = Depends(requer_rh)) -> dict:
    """Apaga telemetria de um intervalo. Fica na AUDITORIA — quem apagou o quê.

    Exigir o intervalo é proposital: sem `desde` nem `ate`, um clique
    distraído levaria a base inteira.
    """
    if payload.desde is None and payload.ate is None:
        raise HTTPException(status_code=422, detail="informe_o_intervalo")

    n = tel.expurgar(db, desde=payload.desde, ate=payload.ate)
    from app.services.auditoria import registrar
    registrar(db, "telemetria_expurgada", ator="rh", ator_detalhe=rh.email,
              detalhe={"desde": str(payload.desde), "ate": str(payload.ate),
                       "linhas": n})
    db.commit()
    return {"removidos": n}
