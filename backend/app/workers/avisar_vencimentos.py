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
            _enviar(db, destinos, col, registro, dias)
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


def _enviar(db, destinos: list[str], col: Candidato, registro, dias: int) -> None:
    from app.core.config import get_settings
    from app.services.email import enviar_email
    from app.services.email_templates import renderizar
    # Renderiza UMA vez e reusa: o mesmo aviso vai ao colaborador e aos
    # destinatários internos da matriz.
    assunto, texto, html = renderizar(db, "certificacao_vencendo", {
        "primeiro_nome": (col.nome_completo or "").split()[0].title(),
        "titulo": registro.titulo or "sua certificação",
        "quando": f"vence em {dias} dias" if dias >= 0 else f"venceu há {-dias} dias",
        "validade": registro.validade_ate.strftime("%d/%m/%Y"),
        "link": f"{get_settings().base_url.rstrip('/')}/meu",
    })
    for destino in destinos:
        try:
            enviar_email(destino, assunto, texto, html)
        except Exception:
            log.warning("Falha ao avisar %s sobre vencimento", destino, exc_info=True)


def lembrar_entrevistas(agora=None) -> int:
    """Lembrete da véspera das entrevistas marcadas (v2.66, § 14.4).

    **Mora AQUI de propósito, e não em cron próprio.** Este worker já roda uma
    vez por dia, já tem anti-spam e já está declarado no compose E no
    `portainer-stack.yml` — um cron novo seria mais uma peça para esquecer de
    subir em produção, que é exatamente como um worker deixa de rodar sem
    ninguém notar.

    Regras que sustentam o comportamento:

    - **Uma vez por entrevista** (`lembrete_enviado_em`). Lembrete repetido
      ensina a pessoa a ignorar o e-mail, e aí o lembrete deixa de existir na
      prática. Remarcar ZERA o carimbo (em `enviar_convite`), porque a data nova
      merece o seu aviso.
    - **Só o que ainda vai acontecer.** Entrevista cuja hora já passou não
      recebe lembrete: quem cobra essa é a fila de PENDÊNCIAS, que fala com o
      RH, não com a pessoa.
    - **Sem e-mail, não sai** — e isso não é falha: é o estado que a tela já
      anuncia com o motivo (cenário 26).
    - Falha de envio **nunca derruba a varredura**: uma pessoa sem e-mail ou um
      SMTP intermitente não podem impedir o lembrete das outras.
    """
    from sqlalchemy import select

    from app.models.entrevista import Entrevista, StatusEntrevista
    from app.services import entrevista_convite as convite

    enviados = 0
    with SessionLocal() as db:
        candidatas = db.scalars(
            select(Entrevista).where(
                Entrevista.status == StatusEntrevista.marcada.value,
                Entrevista.marcada_para.is_not(None),
                Entrevista.lembrete_enviado_em.is_(None))).all()
        for e in candidatas:
            if not convite.deve_lembrar(e, agora):
                continue
            nome, email = _pessoa_da_entrevista(db, e)
            if not email:
                continue        # estado conhecido e anunciado na tela, não erro
            try:
                if convite.enviar_lembrete(db, e, nome, email):
                    enviados += 1
                    db.commit()
            except Exception:   # pragma: no cover - uma falha não para as outras
                log.warning("Falha ao lembrar da entrevista %s", e.id, exc_info=True)
                db.rollback()
    if enviados:
        log.info("Lembretes de entrevista enviados: %s", enviados)
    return enviados


def _pessoa_da_entrevista(db, e) -> tuple[str, str | None]:
    """(nome, e-mail) de qualquer um dos dois lados do par talento/candidato."""
    from app.models.talento import Talento

    if e.talento_id:
        t = db.get(Talento, e.talento_id)
        if t is not None:
            return t.nome or "", t.email
    if e.candidato_id:
        col = db.get(Candidato, e.candidato_id)
        if col is not None:
            return col.nome_completo or "", col.email
    return "", None


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    total = avisar()
    log.info("Avisos de vencimento enviados: %s", total)
    log.info("Lembretes de entrevista enviados: %s", lembrar_entrevistas())
