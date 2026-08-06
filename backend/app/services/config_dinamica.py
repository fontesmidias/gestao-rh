"""Configuração dinâmica: valores do banco (painel) sobrepõem o .env."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.configuracao import Configuracao

CHAVES_SMTP = ("smtp_host", "smtp_port", "smtp_user", "smtp_password", "smtp_from")


def ler_config(db: Session, chaves: tuple[str, ...]) -> dict[str, str]:
    registros = db.scalars(select(Configuracao).where(Configuracao.chave.in_(chaves))).all()
    return {r.chave: r.valor for r in registros}


def gravar_config(db: Session, valores: dict[str, str]) -> None:
    for chave, valor in valores.items():
        registro = db.get(Configuracao, chave)
        if registro is None:
            db.add(Configuracao(chave=chave, valor=valor))
        else:
            registro.valor = valor
    db.flush()


def smtp_config(db: Session) -> dict:
    """SMTP efetivo: banco > .env."""
    s = get_settings()
    banco = ler_config(db, CHAVES_SMTP)
    return {
        "host": banco.get("smtp_host", s.smtp_host),
        "port": int(banco.get("smtp_port", s.smtp_port) or 587),
        "user": banco.get("smtp_user", s.smtp_user),
        "password": banco.get("smtp_password", s.smtp_password),
        "from_": banco.get("smtp_from", s.smtp_from),
    }


# Remetente próprio do recrutamento (v2.67, § 15.5 item 5). Decisão do Bruno:
# convite e lembrete de entrevista saem de um endereço de recrutamento, e o
# `ORGANIZER` do `.ics` usa o mesmo.
CHAVE_EMAIL_RECRUTAMENTO = "email_recrutamento"


def email_recrutamento(db: Session) -> str | None:
    """O remetente do recrutamento — **cai no `smtp_from` quando vazio**.

    Cenário 36, e a regra é a mais importante desta função: **nunca falha por
    estar vazia**. A chave nasce inexistente em toda instalação, e um convite
    que não sai porque ninguém preencheu um campo de configuração seria uma
    entrevista perdida por um cadastro que nem foi pedido — o mesmo raciocínio
    do "cargo sem roteiro cai no padrão, nunca em erro".

    Devolve `None` quando nem a chave nem o `smtp_from` existem: aí quem chama
    omite o `From` e o provedor põe o dele, que é o comportamento que o sistema
    já tinha antes desta chave existir.
    """
    valor = (ler_config(db, (CHAVE_EMAIL_RECRUTAMENTO,))
             .get(CHAVE_EMAIL_RECRUTAMENTO) or "").strip()
    if valor:
        return valor
    return (smtp_config(db).get("from_") or "").strip() or None
