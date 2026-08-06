"""Convite de calendário (`.ics`) — v2.66, § 14.4.

Primeiro compromisso do sistema: **nada no projeto tinha data futura que
dispara algo** até a entrevista (o único vizinho é o `validade_ate` do
certificado, e ele só varre). Por isso este arquivo é curto e cheio de nota —
cada linha aqui existe por um defeito conhecido de agenda.

Três cuidados que o documento cravou, e o que cada um evita:

1. **`UID` estável por entrevista + `SEQUENCE` que incrementa.** É o par que
   faz o Outlook **atualizar** o compromisso em vez de criar um segundo. Gerar
   UID novo a cada remarcação enche a agenda da pessoa de entrevistas fantasma
   no horário antigo, e ela aparece na hora errada — o defeito mais caro
   possível num convite. Há teste por mutação.

2. **Cancelar manda `METHOD:CANCEL` com o MESMO `UID`.** Sem isso o
   compromisso fica na agenda depois de cancelado, e a pessoa vem.

3. **`TZID=America/Sao_Paulo`, nunca UTC solto.** O container roda em UTC
   (armadilha da v2.41, que já mordeu no log e fez a hora sair 3h adiantada). Um
   convite três horas fora não é um convite: é uma falta.

Sem biblioteca: o RFC 5545 de um VEVENT simples cabe em trinta linhas, e o
`icalendar` traria dependência para gerar texto que não muda.
"""
from __future__ import annotations

import uuid as _uuid
from datetime import datetime, timedelta, timezone

# Fuso do compromisso. Tudo que a pessoa lê é hora de Brasília — a mesma
# decisão do `_FormatadorBrasilia` do log e do `fmt.js` da tela.
TZID = "America/Sao_Paulo"

# Domínio do UID. Só precisa ser estável e único; não é resolvido por ninguém.
DOMINIO_UID = "entrevistas.greenhouse"

# Bloco VTIMEZONE de Brasília. Desde 2019 o Brasil não tem horário de verão,
# então UTC-3 o ano inteiro. Vai declarado no arquivo porque cliente de e-mail
# que não conhece o TZID cai em UTC silenciosamente — e aí a hora erra por três.
_VTIMEZONE = [
    "BEGIN:VTIMEZONE",
    f"TZID:{TZID}",
    "BEGIN:STANDARD",
    "DTSTART:19700101T000000",
    "TZOFFSETFROM:-0300",
    "TZOFFSETTO:-0300",
    "TZNAME:-03",
    "END:STANDARD",
    "END:VTIMEZONE",
]

DURACAO_PADRAO_MIN = 60


def uid_da_entrevista(entrevista_id) -> str:
    """O UID **estável**: mesma entrevista, mesmo UID, para sempre.

    Deriva do id da entrevista de propósito — nada de `uuid4()` no momento do
    envio. É esta função que garante o cenário 27 (remarcar ATUALIZA o
    compromisso) e o 28 (cancelar REMOVE o compromisso certo).
    """
    return f"entrevista-{entrevista_id}@{DOMINIO_UID}"


def _escapar(texto) -> str:
    """Escape do RFC 5545: vírgula, ponto e vírgula e barra invertida são
    separadores de campo — um endereço com vírgula parte a linha em duas e o
    convite chega truncado."""
    return (str(texto or "")
            .replace("\\", "\\\\").replace(";", "\\;")
            .replace(",", "\\,").replace("\n", "\\n"))


def _local_utc(dt: datetime) -> str:
    """`YYYYMMDDTHHMMSSZ` — usado só no DTSTAMP, que é carimbo de emissão."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _local_brasilia(dt: datetime) -> str:
    """`YYYYMMDDTHHMMSS` na hora LOCAL de Brasília, para acompanhar o TZID.

    Converte na mão (UTC-3 fixo) em vez de usar `zoneinfo`: a imagem é slim e a
    base de fusos do sistema não é garantida no container — e um `ZoneInfo`
    ausente levantaria na hora de mandar o convite, derrubando o e-mail junto.
    """
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return (dt.astimezone(timezone.utc) - timedelta(hours=3)).strftime("%Y%m%dT%H%M%S")


def _dobrar(linha: str) -> list[str]:
    """Linha de mais de 75 octetos vai dobrada com espaço à frente (RFC 5545).
    Descrição longa sem dobra faz cliente rígido descartar o evento inteiro."""
    if len(linha.encode("utf-8")) <= 74:
        return [linha]
    partes, atual = [], ""
    for ch in linha:
        if len((atual + ch).encode("utf-8")) > 72:
            partes.append(atual)
            atual = " " + ch
        else:
            atual += ch
    if atual:
        partes.append(atual)
    return partes


def gerar_ics(*, entrevista_id, inicio: datetime, resumo: str,
              descricao: str = "", local: str = "",
              organizador_email: str | None = None,
              convidado_email: str | None = None,
              sequencia: int = 0, cancelar: bool = False,
              duracao_min: int = DURACAO_PADRAO_MIN) -> bytes:
    """O arquivo `.ics` pronto para anexar.

    `sequencia` é o contador de remarcações da entrevista: **tem que crescer**,
    senão o cliente de agenda ignora a atualização por considerá-la mais velha
    que a que já tem. `cancelar=True` troca o METHOD para CANCEL e o STATUS
    para CANCELLED, mantendo o mesmo UID — é o que tira o compromisso da agenda
    em vez de deixá-lo lá dizendo que a pessoa tem entrevista.
    """
    metodo = "CANCEL" if cancelar else "REQUEST"
    fim = inicio + timedelta(minutes=max(1, duracao_min))

    linhas = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//Green House//Portal de Admissao//PT-BR",
        "CALSCALE:GREGORIAN",
        f"METHOD:{metodo}",
        *_VTIMEZONE,
        "BEGIN:VEVENT",
        f"UID:{uid_da_entrevista(entrevista_id)}",
        f"SEQUENCE:{int(sequencia)}",
        f"DTSTAMP:{_local_utc(datetime.now(timezone.utc))}",
        f"DTSTART;TZID={TZID}:{_local_brasilia(inicio)}",
        f"DTEND;TZID={TZID}:{_local_brasilia(fim)}",
        f"SUMMARY:{_escapar(resumo)}",
        f"STATUS:{'CANCELLED' if cancelar else 'CONFIRMED'}",
    ]
    if descricao:
        linhas.append(f"DESCRIPTION:{_escapar(descricao)}")
    if local:
        # LOCATION serve os dois casos: endereço no presencial, link no online
        # (§ 14.4). O link vai TAMBÉM na descrição, porque nem todo cliente
        # transforma o LOCATION em algo clicável.
        linhas.append(f"LOCATION:{_escapar(local)}")
    if organizador_email:
        linhas.append(f"ORGANIZER;CN=Green House:mailto:{organizador_email}")
    if convidado_email:
        linhas.append(
            "ATTENDEE;ROLE=REQ-PARTICIPANT;PARTSTAT=NEEDS-ACTION;RSVP=TRUE:"
            f"mailto:{convidado_email}")
    linhas += ["END:VEVENT", "END:VCALENDAR"]

    dobradas = []
    for linha in linhas:
        dobradas.extend(_dobrar(linha))
    # CRLF é exigência do RFC; cliente rígido recusa arquivo só com \n.
    return ("\r\n".join(dobradas) + "\r\n").encode("utf-8")


def nome_do_arquivo(entrevista_id) -> str:
    """Nome curto e estável do anexo. Não usa texto do usuário — mesma regra do
    `export_planilha.slug()`, que existe porque título livre vira travessia de
    caminho."""
    try:
        curto = str(_uuid.UUID(str(entrevista_id)))[:8]
    except (ValueError, AttributeError, TypeError):
        curto = "convite"
    return f"entrevista-{curto}.ics"
