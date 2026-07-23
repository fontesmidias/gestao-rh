"""Aviso automático de certificação prestes a vencer (Onda B).

O ciclo que o Bruno desenhou começa aqui: 90 dias antes de o certificado de
brigadista vencer, o colaborador **e** o líder de brigada recebem um e-mail. O
colaborador entra no portal `/meu`, manda os documentos, o RH valida, e o dash
de brigadistas monta a solicitação de matrícula à Multicursos.

Roda uma vez por dia junto com o expurgo (ver `docker-compose.base.yml`).

Anti-spam: cada registro é avisado UMA vez por janela — o carimbo fica na
auditoria, não numa coluna nova. Sem isso o worker mandaria o mesmo e-mail
todo dia durante 90 dias, e a pessoa aprenderia a ignorar.
"""

import logging
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import select

from app.core.db import SessionLocal
from app.models.candidato import Candidato, PostoServico
from app.models.desenvolvimento import (RegistroDesenvolvimento, StatusRegistro,
                                        TipoDesenvolvimento)
from app.models.evento import EventoAuditoria

log = logging.getLogger(__name__)

# Reavisa se o anterior saiu há mais de N dias (a pessoa pode ter perdido o
# e-mail; mas não vira spam diário).
INTERVALO_REAVISO_D = 30
ACAO = "desenvolvimento_aviso_vencimento"


def _ja_avisado(db, registro_id, dias_atras: int) -> bool:
    limite = datetime.now(timezone.utc) - timedelta(days=dias_atras)
    return db.scalar(
        select(EventoAuditoria).where(
            EventoAuditoria.acao == ACAO,
            EventoAuditoria.criado_em >= limite,
            EventoAuditoria.detalhe["registro"].astext == str(registro_id))
    ) is not None


def a_vencer(db, hoje: date | None = None) -> list[tuple]:
    """(registro, colaborador, dias) do que está dentro da janela de aviso.

    A janela é a do TIPO (`aviso_dias_antes`, 90 por padrão) — o mesmo número
    que o RH vê no painel, para não haver dois prazos divergentes.
    """
    hoje = hoje or date.today()
    saida = []
    registros = db.scalars(
        select(RegistroDesenvolvimento).where(
            RegistroDesenvolvimento.status == StatusRegistro.validado,
            RegistroDesenvolvimento.validade_ate.isnot(None))).all()
    for r in registros:
        tipo = db.get(TipoDesenvolvimento, r.tipo_id)
        if tipo is None or not tipo.exige_validade:
            continue
        dias = (r.validade_ate - hoje).days
        if dias > tipo.aviso_dias_antes:
            continue  # ainda longe
        col = db.get(Candidato, r.candidato_id)
        if col is None or col.situacao != "ativo":
            continue  # desligado não precisa reciclar
        # Já venceu há muito? Continua avisando — vencido é pior que a vencer.
        saida.append((r, col, dias))
    return saida


def avisar(hoje: date | None = None) -> int:
    """Manda os avisos pendentes. Devolve quantos e-mails saíram."""
    enviados = 0
    with SessionLocal() as db:
        for registro, col, dias in a_vencer(db, hoje):
            if _ja_avisado(db, registro.id, INTERVALO_REAVISO_D):
                continue
            destinos = _destinatarios(db, col)
            if not destinos:
                log.info("Sem e-mail para avisar sobre %s (%s)",
                         registro.titulo, col.nome_completo)
                continue
            _enviar(destinos, col, registro, dias)
            from app.services.auditoria import registrar
            registrar(db, ACAO, ator="sistema", candidato_id=col.id,
                      detalhe={"registro": str(registro.id), "dias": dias,
                               "destinos": len(destinos)})
            db.commit()
            enviados += len(destinos)
    return enviados


def _destinatarios(db, col: Candidato) -> list[str]:
    """O colaborador E o líder de brigada (pedido do Bruno). O líder sai da
    matriz de notificações — assim o RH escolhe quem é, sem código novo."""
    destinos = []
    if col.email:
        destinos.append(col.email)
    from app.services.notificacoes import destinatarios
    for e in destinatarios(db, "certificacao_vencendo"):
        if e and e not in destinos:
            destinos.append(e)
    return destinos


def _enviar(destinos: list[str], col: Candidato, registro, dias: int) -> None:
    from app.core.config import get_settings
    from app.services.email import enviar_email, html_moderno
    primeiro = (col.nome_completo or "").split()[0].title()
    titulo = registro.titulo or "sua certificação"
    quando = (f"vence em {dias} dias" if dias >= 0 else f"venceu há {-dias} dias")
    url = f"{get_settings().base_url.rstrip('/')}/meu"
    assunto = (f"Green House — {titulo} {quando}"
               if dias >= 0 else f"Green House — {titulo} VENCIDA")
    texto = (
        f"Olá, {primeiro}!\n\n"
        f"{titulo} {quando} (validade: {registro.validade_ate.strftime('%d/%m/%Y')}).\n\n"
        f"Para renovar, acesse {url}, entre com seu CPF e envie:\n"
        "- documento com foto (RG ou CNH)\n"
        "- certificado de formação\n"
        "- atestado de saúde ocupacional\n\n"
        "Assim que estiver tudo certo, o RH providencia a matrícula na "
        "reciclagem.\n\nAtenciosamente,\nRH — Green House\n")
    html = html_moderno(
        "Sua certificação precisa ser renovada",
        [f"Olá, <strong>{primeiro}</strong>!",
         f"<strong>{titulo}</strong> {quando} — validade até "
         f"<strong>{registro.validade_ate.strftime('%d/%m/%Y')}</strong>.",
         "Para renovar, envie no portal: documento com foto, certificado de "
         "formação e atestado de saúde ocupacional.",
         "Assim que estiver tudo certo, o RH providencia a matrícula na reciclagem."],
        botao_texto="Enviar meus documentos", botao_url=url)
    for destino in destinos:
        try:
            enviar_email(destino, assunto, texto, html)
        except Exception:
            log.warning("Falha ao avisar %s sobre vencimento", destino, exc_info=True)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    total = avisar()
    log.info("Avisos de vencimento enviados: %s", total)
