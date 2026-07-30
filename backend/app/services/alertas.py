"""Avaliação das regras de alerta da telemetria (v2.25).

Roda a cada 15 minutos (worker `alertas_telemetria`). Para cada regra ATIVA,
olha a janela configurada e decide se há algo digno de tirar alguém do que está
fazendo.

Três princípios que governam o módulo — nenhum é detalhe de implementação:

1. **Silêncio é recurso escasso.** Um alerta que vira ruído deixa de ser lido, e
   alerta ignorado é PIOR que alerta nenhum: dá falsa sensação de cobertura.
   Por isso o dedup por assinatura e a janela de silêncio não são opcionais nem
   configuráveis para "zero".

2. **O aviso diz o que fazer.** Assinatura, contagem, quantas pessoas e onde
   olhar. "Algo deu errado" obrigaria o RH a investigar do zero — que é
   exatamente o trabalho que este módulo existe para poupar.

3. **Nunca levanta.** Mesma regra do `avisar()`: alerta que falha não pode
   derrubar o worker nem a ação de ninguém.
"""

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.alerta import AlertaEnviado, RegraAlerta, TipoAlerta
from app.models.telemetria import EventoTelemetria, TipoTelemetria

log = logging.getLogger(__name__)

# Evento da matriz de avisos internos (services/notificacoes.py) e chave do
# template no catálogo de e-mails. Os dois precisam existir, senão o alerta é
# calculado e não chega a ninguém.
EVENTO_MATRIZ = "telemetria_alerta"
TEMPLATE = "aviso_telemetria_alerta"

# Teto de itens listados num aviso: um e-mail com 400 linhas não é lido.
MAX_ITENS_NO_AVISO = 10


def _assinatura(tipo: str, *partes: str | None) -> str:
    """Identidade do que disparou — a chave do dedup.

    Precisa ser estável (o mesmo problema gera a mesma assinatura em toda
    verificação) e específica (problemas diferentes não se cancelam).
    """
    return f"{tipo}|" + "|".join((p or "-")[:100] for p in partes)


def _ja_avisado(db: Session, assinatura: str, silencio_min: int) -> bool:
    corte = datetime.now(timezone.utc) - timedelta(minutes=max(1, silencio_min))
    return db.scalar(
        select(func.count()).select_from(AlertaEnviado)
        .where(AlertaEnviado.assinatura == assinatura,
               AlertaEnviado.criado_em >= corte)) > 0


def _ja_visto_alguma_vez(db: Session, assinatura: str) -> bool:
    """Para `erro_novo`: 'novo' é o que nunca gerou alerta. Sem janela."""
    return db.scalar(
        select(func.count()).select_from(AlertaEnviado)
        .where(AlertaEnviado.assinatura == assinatura)) > 0


def _filtros_da_regra(q, regra: RegraAlerta):
    if regra.origem:
        q = q.where(EventoTelemetria.origem == regra.origem)
    if regra.pagina:
        q = q.where(EventoTelemetria.pagina.ilike(f"%{regra.pagina}%"))
    if regra.evento:
        q = q.where(EventoTelemetria.evento == regra.evento)
    return q


def _avaliar_erro_novo(db: Session, regra: RegraAlerta, corte: datetime) -> list[dict]:
    """Mensagem de erro que nunca havia aparecido. O caso de 2026-07-29."""
    msg = EventoTelemetria.detalhe["mensagem"].astext
    q = select(msg.label("mensagem"), EventoTelemetria.pagina,
               func.count().label("n"),
               func.count(func.distinct(EventoTelemetria.sessao)).label("pessoas"))
    q = _filtros_da_regra(q, regra).where(
        EventoTelemetria.tipo == TipoTelemetria.erro.value,
        EventoTelemetria.criado_em >= corte)
    linhas = db.execute(q.group_by(msg, EventoTelemetria.pagina)).all()

    achados = []
    for mensagem, pagina, n, pessoas in linhas:
        assin = _assinatura("erro_novo", mensagem, pagina)
        if _ja_visto_alguma_vez(db, assin):
            continue        # já avisamos deste erro alguma vez: não é novo
        achados.append({
            "assinatura": assin, "n": n, "pessoas": pessoas,
            "texto": f"{mensagem or 'erro sem mensagem'} — em {pagina or 'página não informada'} "
                     f"({n}x, {pessoas} pessoa(s))",
        })
    return achados


def _avaliar_erro_volume(db: Session, regra: RegraAlerta, corte: datetime) -> list[dict]:
    """Erro CONHECIDO que explodiu de volume — assinatura de deploy ruim."""
    msg = EventoTelemetria.detalhe["mensagem"].astext
    q = select(msg.label("mensagem"), EventoTelemetria.pagina,
               func.count().label("n"),
               func.count(func.distinct(EventoTelemetria.sessao)).label("pessoas"))
    q = _filtros_da_regra(q, regra).where(
        EventoTelemetria.tipo == TipoTelemetria.erro.value,
        EventoTelemetria.criado_em >= corte)
    linhas = db.execute(
        q.group_by(msg, EventoTelemetria.pagina)
        .having(func.count() >= max(1, regra.limiar))).all()

    return [{
        "assinatura": _assinatura("erro_volume", mensagem, pagina),
        "n": n, "pessoas": pessoas,
        "texto": f"{mensagem or 'erro sem mensagem'} — em {pagina or '—'} "
                 f"({n}x em {regra.janela_min} min, {pessoas} pessoa(s))",
    } for mensagem, pagina, n, pessoas in linhas]


def _avaliar_friccao_pico(db: Session, regra: RegraAlerta, corte: datetime) -> list[dict]:
    """Muita gente travando no mesmo ponto: algo quebrou, não é desatenção."""
    q = select(EventoTelemetria.evento, EventoTelemetria.pagina,
               func.count().label("n"),
               func.count(func.distinct(EventoTelemetria.sessao)).label("pessoas"))
    q = _filtros_da_regra(q, regra).where(
        EventoTelemetria.tipo == TipoTelemetria.friccao.value,
        EventoTelemetria.criado_em >= corte)
    linhas = db.execute(
        q.group_by(EventoTelemetria.evento, EventoTelemetria.pagina)
        .having(func.count() >= max(1, regra.limiar))).all()

    return [{
        "assinatura": _assinatura("friccao_pico", evento, pagina),
        "n": n, "pessoas": pessoas,
        "texto": f"{evento} em {pagina or '—'} — {n}x em {regra.janela_min} min "
                 f"({pessoas} pessoa(s) diferentes)",
    } for evento, pagina, n, pessoas in linhas]


def _avaliar_lentidao(db: Session, regra: RegraAlerta, corte: datetime) -> list[dict]:
    """Página acima do tempo aceitável. Compara pela MEDIANA, não pela média.

    Um único caso de 40s (alguém no elevador com 1 barra de sinal) não é
    problema do sistema; a mediana só passa do limiar quando a maioria está
    esperando demais — que é o que merece acordar alguém.
    """
    mediana = func.percentile_cont(0.5).within_group(EventoTelemetria.duracao_ms)
    q = select(EventoTelemetria.pagina, mediana.label("mediana"),
               func.count().label("n"))
    q = _filtros_da_regra(q, regra).where(
        EventoTelemetria.tipo == TipoTelemetria.desempenho.value,
        EventoTelemetria.criado_em >= corte,
        EventoTelemetria.duracao_ms.isnot(None))
    linhas = db.execute(
        q.group_by(EventoTelemetria.pagina)
        # 3 amostras no mínimo: mediana de uma ou duas medições é anedota.
        .having(func.count() >= 3)
        .having(mediana >= max(1, regra.limiar))).all()

    return [{
        "assinatura": _assinatura("lentidao", pagina),
        "n": n, "pessoas": 0,
        "texto": f"{pagina or '—'} está levando {round((med or 0) / 1000, 1)}s "
                 f"para a maioria das pessoas ({n} medições)",
    } for pagina, med, n in linhas]


AVALIADORES = {
    TipoAlerta.erro_novo.value: _avaliar_erro_novo,
    TipoAlerta.erro_volume.value: _avaliar_erro_volume,
    TipoAlerta.friccao_pico.value: _avaliar_friccao_pico,
    TipoAlerta.lentidao.value: _avaliar_lentidao,
}

ROTULO_TIPO = {
    "erro_novo": "Erro novo",
    "erro_volume": "Volume de erros",
    "friccao_pico": "Pico de travamentos",
    "lentidao": "Lentidão",
}


def avaliar(db: Session, *, enviar: bool = True) -> list[dict]:
    """Roda todas as regras ativas. Devolve o que disparou.

    `enviar=False` é o modo PRÉ-VISUALIZAÇÃO da tela ("o que dispararia
    agora?"): não manda e-mail e não grava histórico, então não consome o
    silêncio nem estraga o `erro_novo` — testar uma regra não pode fazer o
    problema real deixar de avisar depois.
    """
    disparos = []
    regras = db.scalars(select(RegraAlerta).where(RegraAlerta.ativa.is_(True))).all()

    for regra in regras:
        try:
            avaliador = AVALIADORES.get(
                regra.tipo.value if hasattr(regra.tipo, "value") else regra.tipo)
            if avaliador is None:
                log.warning("regra de alerta com tipo desconhecido: %s", regra.tipo)
                continue

            corte = datetime.now(timezone.utc) - timedelta(minutes=max(1, regra.janela_min))
            achados = avaliador(db, regra, corte)

            # Dedup pela janela de silêncio (o `erro_novo` já filtrou pelo
            # histórico inteiro, mas isto protege as verificações seguidas).
            novos = [a for a in achados
                     if not _ja_avisado(db, a["assinatura"], regra.silencio_min)]
            if not novos:
                continue

            disparos.append({
                "regra_id": regra.id, "regra": regra.nome, "tipo": regra.tipo,
                "itens": novos[:MAX_ITENS_NO_AVISO],
                "total": len(novos),
            })
        except Exception:
            # Uma regra malformada não pode calar as outras.
            log.exception("falha ao avaliar a regra de alerta %s", regra.nome)

    if enviar:
        for d in disparos:
            _notificar(db, d)
    return disparos


def _notificar(db: Session, disparo: dict) -> None:
    """Manda pela MATRIZ de avisos internos e grava o histórico do dedup.

    O histórico é gravado MESMO se o e-mail não sair (destinatário não
    configurado, SMTP fora): senão, um evento cairia em laço, recalculando e
    tentando avisar a cada 15 minutos para sempre.
    """
    from app.services.notificacoes import avisar_modelo

    tipo = disparo["tipo"].value if hasattr(disparo["tipo"], "value") else disparo["tipo"]
    linhas = "\n".join(f"• {i['texto']}" for i in disparo["itens"])
    if disparo["total"] > len(disparo["itens"]):
        linhas += f"\n• (+{disparo['total'] - len(disparo['itens'])} outro(s))"

    # O botão "Ver na telemetria" precisa de uma URL. O worker não tem `request`
    # (roda no cron, não numa rota), então aqui é o único lugar do sistema em que
    # o `BASE_URL` é mesmo obrigatório — sem ele o botão sairia vazio, e um aviso
    # que não leva a lugar nenhum obriga o RH a caçar a tela na mão. Fora isso, o
    # aviso continua útil: a lista de problemas está no corpo.
    from app.core.config import get_settings
    base = (get_settings().base_url or "").rstrip("/")

    enviados = 0
    try:
        enviados = avisar_modelo(db, EVENTO_MATRIZ, TEMPLATE, {
            "regra": disparo["regra"],
            "tipo": ROTULO_TIPO.get(tipo, tipo),
            "quantidade": str(disparo["total"]),
            "lista": linhas,
            "link": f"{base}/rh/config" if base else "",
        })
    except Exception:
        log.exception("alerta de telemetria: falha ao notificar")

    for item in disparo["itens"]:
        db.add(AlertaEnviado(
            regra_id=disparo["regra_id"], tipo=tipo,
            assinatura=item["assinatura"], resumo=item["texto"][:2000],
            ocorrencias=item["n"], destinatarios=enviados,
        ))


def historico(db: Session, limite: int = 100) -> list[dict]:
    """Alertas já disparados — a prova de que o vigia está acordado.

    Sem esta lista, uma caixa de entrada silenciosa seria ambígua: "não houve
    problema" e "o alerta parou de funcionar" pareceriam a mesma coisa.
    """
    itens = db.scalars(
        select(AlertaEnviado).order_by(AlertaEnviado.criado_em.desc())
        .limit(min(limite, 500))).all()
    return [{
        "id": a.id, "quando": a.criado_em, "tipo": a.tipo,
        "rotulo": ROTULO_TIPO.get(a.tipo, a.tipo), "resumo": a.resumo,
        "ocorrencias": a.ocorrencias, "destinatarios": a.destinatarios,
    } for a in itens]
