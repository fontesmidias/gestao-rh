"""Registro e leitura da telemetria de uso (v2.24).

Porta ÚNICA de entrada: `registrar_eventos`. Ela nunca levanta — telemetria que
derruba a ação do candidato seria uma troca péssima (a mesma regra do
`avisar()` em notificacoes.py, e pelo mesmo motivo).

Duas defesas que não são opcionais:

1. **Teto de volume.** O endpoint é PÚBLICO (o candidato não tem login), então
   é superfície de abuso: um laço no navegador encheria a tabela. Limitamos
   eventos por lote e tamanho de cada campo.
2. **Minimização na ENTRADA, não na leitura.** O IP é truncado e o
   `user_agent` cortado antes de gravar. Guardar o dado completo "porque um dia
   pode ser útil" é como o vazamento começa.
"""

import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.models.telemetria import (EventoTelemetria, OrigemTelemetria,
                                   TipoTelemetria)

log = logging.getLogger(__name__)

# Teto por lote: o front envia em blocos; acima disso é laço ou ataque.
MAX_EVENTOS_LOTE = 50
MAX_DETALHE_CHARS = 4000   # stack de erro cabe; despejo de dados, não
MAX_TEXTO = 120

# Retenção padrão. Escolha do Bruno (2026-07-29): 1 ano, para permitir análise
# sazonal — contratação de fim de ano contra o resto. Configurável no painel,
# em `telemetria_retencao_dias`.
RETENCAO_PADRAO_DIAS = 365


def _cortar(valor: Any, limite: int = MAX_TEXTO) -> str | None:
    if valor is None:
        return None
    texto = str(valor).strip()
    return texto[:limite] or None


def mascarar_pagina(pagina: str | None) -> str | None:
    """Tira o TOKEN do link mágico do caminho da página.

    `/c/uB0jq1m9hdmDNFygDg...` é credencial de acesso: quem tem o token entra na
    admissão da pessoa. Gravá-lo na telemetria criaria uma tabela cheia de
    chaves de acesso — e telemetria é feita para ser lida, exportada e olhada
    por várias pessoas. O mesmo mascaramento que o log HTTP já faz (`main.py`).

    O prefixo curto fica: dá para correlacionar eventos da mesma sessão sem
    servir de credencial.
    """
    if not pagina:
        return None
    partes = pagina.split("/")
    for marca in ("c", "t", "p"):        # links de candidato, testagem e prova
        if marca in partes:
            i = partes.index(marca) + 1
            if i < len(partes) and _parece_token(partes[i]):
                partes[i] = partes[i][:6] + "***"
    return "/".join(partes)


def _parece_token(trecho: str) -> bool:
    """Distingue um token de link mágico de um nome de etapa.

    Sem isto, `/c/assinatura` (nome de etapa, 10 caracteres) virava
    `/c/assina***` — e o MESMO erro aparecia duas vezes no alerta, uma por
    grafia, como se fossem problemas diferentes (pego ao testar o cenário real).
    Agrupar errado é pior que não agrupar: infla a contagem e esconde o padrão.

    Token do `itsdangerous` é longo e mistura maiúsculas, minúsculas, dígitos e
    `-`/`_`; nome de etapa é palavra minúscula. Exigimos tamanho E mistura de
    caixa — um nome de etapa nunca tem as duas coisas.
    """
    if len(trecho) < 20:
        return False
    return any(c.islower() for c in trecho) and any(c.isupper() for c in trecho)


def ip_prefixo(ip: str | None) -> str | None:
    """Só os dois primeiros octetos: `191.180.x.x`.

    Basta para distinguir "a operadora inteira está com problema" de "o sistema
    está com problema", que é o uso legítimo — e não localiza a pessoa.
    IPv6 fica só com os dois primeiros grupos, pelo mesmo motivo.
    """
    if not ip:
        return None
    if ":" in ip:
        partes = ip.split(":")
        return ":".join(partes[:2]) + ":x:x"
    partes = ip.split(".")
    if len(partes) != 4:
        return None
    return f"{partes[0]}.{partes[1]}.x.x"


def registrar_eventos(
    db: Session,
    eventos: list[dict],
    *,
    origem: str,
    candidato_id: uuid.UUID | None = None,
    talento_id: uuid.UUID | None = None,
    usuario_rh: str | None = None,
    sessao: str | None = None,
    versao: str | None = None,
    user_agent: str | None = None,
    ip: str | None = None,
) -> int:
    """Grava um lote. Devolve quantos entraram. NUNCA levanta.

    O chamador não precisa (e não deve) tratar erro: se a telemetria falhar, a
    ação do usuário segue normalmente. Perder um registro de uso é irrelevante
    perto de travar uma admissão.
    """
    try:
        try:
            origem_val = OrigemTelemetria(origem).value
        except ValueError:
            log.warning("telemetria: origem desconhecida %r", origem)
            return 0

        gravados = 0
        for bruto in (eventos or [])[:MAX_EVENTOS_LOTE]:
            if not isinstance(bruto, dict):
                continue
            nome = _cortar(bruto.get("evento"), 60)
            if not nome:
                continue   # evento sem nome não serve para nada
            try:
                tipo = TipoTelemetria(bruto.get("tipo") or "jornada").value
            except ValueError:
                tipo = TipoTelemetria.jornada.value

            detalhe = bruto.get("detalhe")
            if detalhe is not None and not isinstance(detalhe, dict):
                detalhe = {"valor": str(detalhe)[:MAX_DETALHE_CHARS]}
            if isinstance(detalhe, dict):
                # Corta cada campo: um stack gigante ou um despejo acidental de
                # formulário não podem inchar a tabela nem virar depósito de
                # dado pessoal.
                detalhe = {str(k)[:40]: (str(v)[:MAX_DETALHE_CHARS] if v is not None else None)
                           for k, v in list(detalhe.items())[:20]}

            duracao = bruto.get("duracao_ms")
            try:
                duracao = int(duracao) if duracao is not None else None
                if duracao is not None and (duracao < 0 or duracao > 86_400_000):
                    duracao = None      # fora de um dia é relógio errado
            except (TypeError, ValueError):
                duracao = None

            db.add(EventoTelemetria(
                tipo=tipo, origem=origem_val,
                candidato_id=candidato_id, talento_id=talento_id,
                usuario_rh=_cortar(usuario_rh, 200), sessao=_cortar(sessao, 40),
                evento=nome, pagina=mascarar_pagina(_cortar(bruto.get("pagina"))),
                duracao_ms=duracao, detalhe=detalhe,
                versao=_cortar(bruto.get("versao") or versao, 40),
                user_agent=_cortar(user_agent, 200),
                ip_prefixo=ip_prefixo(ip),
            ))
            gravados += 1

        if gravados:
            db.flush()
        return gravados
    except Exception:
        # Mesma regra do avisar(): telemetria nunca derruba a ação que a gerou.
        #
        # MAS o silêncio tem preço, e este módulo já pagou: um erro de mapeamento
        # (FK sem o modelo importado) fez TODA gravação falhar sem que nada
        # aparecesse — o `except` escondeu por completo. É a mesma armadilha da
        # v2.02 ("catch vazio não pode engolir erro de infra"), agora do lado do
        # servidor. Por isso o log é `exception` (com stack) e não `warning`, e
        # por isso `test_telemetria.py` afirma que a gravação REALMENTE grava,
        # em vez de só verificar que não levantou.
        log.exception("telemetria: falha ao registrar lote — eventos PERDIDOS")
        try:
            db.rollback()
        except Exception:
            pass
        return 0


# ---------------------------------------------------------------------------
# Leitura — o que a tela do RH consome
# ---------------------------------------------------------------------------


def _serializar(e: EventoTelemetria) -> dict:
    return {
        "id": e.id, "quando": e.criado_em, "tipo": e.tipo, "origem": e.origem,
        "evento": e.evento, "pagina": e.pagina, "duracao_ms": e.duracao_ms,
        "detalhe": e.detalhe, "versao": e.versao, "sessao": e.sessao,
        "usuario_rh": e.usuario_rh, "candidato_id": e.candidato_id,
        "talento_id": e.talento_id, "user_agent": e.user_agent,
        "ip_prefixo": e.ip_prefixo,
    }


def da_pessoa(db: Session, *, candidato_id: uuid.UUID | None = None,
              talento_id: uuid.UUID | None = None, limite: int = 200) -> list[dict]:
    """Telemetria de UMA pessoa — o que alimenta o painel na ficha dela.

    Busca pelos DOIS vínculos quando ambos são conhecidos: a pessoa atravessa
    talento → candidato e a memória tem que seguir junto, como no mini-CRM.
    """
    if candidato_id is None and talento_id is None:
        return []
    condicoes = []
    if candidato_id is not None:
        condicoes.append(EventoTelemetria.candidato_id == candidato_id)
    if talento_id is not None:
        condicoes.append(EventoTelemetria.talento_id == talento_id)
    from sqlalchemy import or_
    eventos = db.scalars(
        select(EventoTelemetria).where(or_(*condicoes))
        .order_by(EventoTelemetria.criado_em.desc())
        .limit(min(limite, 500))).all()
    return [_serializar(e) for e in eventos]


def listar(db: Session, *, tipo: str | None = None, origem: str | None = None,
           evento: str | None = None, pagina: str | None = None,
           desde: datetime | None = None, ate: datetime | None = None,
           limite: int = 300) -> list[dict]:
    """Consulta geral, com os filtros da aba de Telemetria."""
    q = select(EventoTelemetria)
    if tipo:
        q = q.where(EventoTelemetria.tipo == tipo)
    if origem:
        q = q.where(EventoTelemetria.origem == origem)
    if evento:
        q = q.where(EventoTelemetria.evento == evento)
    if pagina:
        q = q.where(EventoTelemetria.pagina.ilike(f"%{pagina}%"))
    if desde:
        q = q.where(EventoTelemetria.criado_em >= desde)
    if ate:
        q = q.where(EventoTelemetria.criado_em <= ate)
    eventos = db.scalars(
        q.order_by(EventoTelemetria.criado_em.desc()).limit(min(limite, 1000))).all()
    return [_serializar(e) for e in eventos]


def resumo(db: Session, dias: int = 7) -> dict:
    """Os números do topo da aba — o que se olha antes de filtrar.

    Erros vêm AGRUPADOS por mensagem, não em lista crua: 300 ocorrências do
    mesmo `TypeError` são UM problema, e a lista crua esconderia isso atrás do
    volume. Foi exatamente o que aconteceu em 2026-07-29.
    """
    corte = datetime.now(timezone.utc) - timedelta(days=max(1, dias))

    por_tipo = dict(db.execute(
        select(EventoTelemetria.tipo, func.count())
        .where(EventoTelemetria.criado_em >= corte)
        .group_by(EventoTelemetria.tipo)).all())

    # A expressão do JSONB precisa ser a MESMA instância no SELECT e no GROUP
    # BY: montada duas vezes, o SQLAlchemy gera dois parâmetros distintos e o
    # Postgres recusa ("must appear in the GROUP BY clause") — pego em teste.
    msg = EventoTelemetria.detalhe["mensagem"].astext
    erros = db.execute(
        select(EventoTelemetria.evento, msg.label("mensagem"),
               EventoTelemetria.pagina, func.count().label("ocorrencias"),
               func.max(EventoTelemetria.criado_em).label("ultima"),
               func.count(func.distinct(EventoTelemetria.sessao)).label("pessoas"))
        .where(EventoTelemetria.tipo == TipoTelemetria.erro.value,
               EventoTelemetria.criado_em >= corte)
        .group_by(EventoTelemetria.evento, msg, EventoTelemetria.pagina)
        .order_by(func.count().desc()).limit(20)).all()

    # Páginas mais lentas: MEDIANA, não média. Uma chamada de 40s distorce a
    # média e faz parecer que tudo está lento; a mediana mostra o que a maioria
    # das pessoas realmente vive.
    lentas = db.execute(
        select(EventoTelemetria.pagina,
               func.percentile_cont(0.5).within_group(
                   EventoTelemetria.duracao_ms).label("mediana"),
               func.max(EventoTelemetria.duracao_ms).label("pior"),
               func.count().label("amostras"))
        .where(EventoTelemetria.tipo == TipoTelemetria.desempenho.value,
               EventoTelemetria.criado_em >= corte,
               EventoTelemetria.duracao_ms.isnot(None))
        .group_by(EventoTelemetria.pagina)
        .order_by(func.percentile_cont(0.5).within_group(
            EventoTelemetria.duracao_ms).desc()).limit(10)).all()

    friccao = db.execute(
        select(EventoTelemetria.evento, EventoTelemetria.pagina,
               func.count().label("ocorrencias"))
        .where(EventoTelemetria.tipo == TipoTelemetria.friccao.value,
               EventoTelemetria.criado_em >= corte)
        .group_by(EventoTelemetria.evento, EventoTelemetria.pagina)
        .order_by(func.count().desc()).limit(15)).all()

    return {
        "dias": dias,
        "total": sum(por_tipo.values()),
        "por_tipo": por_tipo,
        "erros": [{"evento": e, "mensagem": m, "pagina": p, "ocorrencias": o,
                   "ultima": u, "pessoas": q} for e, m, p, o, u, q in erros],
        "lentas": [{"pagina": p, "mediana_ms": round(med or 0), "pior_ms": pior,
                    "amostras": n} for p, med, pior, n in lentas],
        "friccao": [{"evento": e, "pagina": p, "ocorrencias": o}
                    for e, p, o in friccao],
    }


def expurgar(db: Session, *, antes_de: datetime | None = None,
             desde: datetime | None = None, ate: datetime | None = None) -> int:
    """Apaga telemetria. Devolve quantas linhas saíram.

    Dois modos, os dois pedidos pelo Bruno: `antes_de` (retenção — o worker usa)
    e o intervalo `desde`/`ate` (expurgo cirúrgico, ex.: os testes de ontem que
    poluíram os números).

    Não passa pela lixeira, e é de propósito: telemetria é dado descartável de
    produto. Mandar milhões de linhas de uso para a lixeira a encheria e
    esconderia o que ela existe para proteger — documento de gente.
    """
    if antes_de is None and desde is None and ate is None:
        return 0
    q = delete(EventoTelemetria)
    if antes_de is not None:
        q = q.where(EventoTelemetria.criado_em < antes_de)
    if desde is not None:
        q = q.where(EventoTelemetria.criado_em >= desde)
    if ate is not None:
        q = q.where(EventoTelemetria.criado_em <= ate)
    return db.execute(q).rowcount or 0


def retencao_dias(db: Session) -> int:
    """Dias de retenção configurados no painel (padrão: 1 ano)."""
    from app.services.config_dinamica import ler_config
    try:
        cfg = ler_config(db, ("telemetria_retencao_dias",))
        valor = int(cfg.get("telemetria_retencao_dias") or RETENCAO_PADRAO_DIAS)
        return max(1, min(valor, 3650))     # entre 1 dia e 10 anos
    except (TypeError, ValueError):
        return RETENCAO_PADRAO_DIAS
