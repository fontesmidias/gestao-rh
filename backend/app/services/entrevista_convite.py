"""Convite e lembrete de entrevista (v2.66, § 14.4) — a porta ÚNICA de envio.

Existe como serviço, e não solto na rota, porque três chamadores precisam do
MESMO comportamento: marcar (envia convite), remarcar/cancelar (envia
atualização ou cancelamento com o mesmo UID) e o worker da véspera. Espalhar
isso pelos call-sites faria um deles esquecer o `SEQUENCE`, e o defeito seria
uma entrevista fantasma na agenda de alguém.

Duas regras que sustentam o desenho:

**1. Sem e-mail, o lembrete fica DESLIGADO com o motivo na tela** (cenário 26) —
nunca falha calada. `motivo_sem_envio()` é a função que a tela usa para dizer
por quê, e a rota devolve o mesmo texto. Silêncio aqui faria o RH acreditar que
a pessoa foi avisada quando ninguém foi.

**2. Online sem link não se marca** (cenário 29). A checagem mora em
`erros_de_modalidade` e é chamada na GRAVAÇÃO, não no envio: recusar só na hora
do e-mail deixaria a entrevista marcada e o convite não; a tela diria "marcada"
e a pessoa não teria como entrar.

Falha de envio **nunca derruba a ação**: marcar a entrevista é o ato principal,
e um SMTP fora do ar não pode impedir o RH de registrar o compromisso. O
resultado do envio volta como dado (`enviado`/`motivo`) para a tela dizer o que
aconteceu — a mesma regra do `avisar()`, que nunca levanta, com a diferença de
que aqui o resultado é ANUNCIADO em vez de engolido.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from app.services import calendario
from app.services.entrevistas import LEMBRETE_HORAS_ANTES

log = logging.getLogger(__name__)

# Duração PADRÃO do convite. Até a v2.66 era a duração, ponto — não havia campo.
# Na v2.67 o Bruno pediu que virasse campo (`Entrevista.duracao_min`, § 15.5
# item 4), e esta constante passou a ser só o valor inicial: entrevista antiga,
# gravada antes da coluna existir, continua valendo uma hora.
DURACAO_MIN = 60


def duracao_de(e) -> int:
    """A duração daquela entrevista, com piso de 1 minuto.

    O piso é rede, não validação: quem recusa duração zero é a rota, com 422 que
    explica (cenário 37). Se ela chegasse aqui como 0 — registro antigo, acerto
    no banco —, o `DTEND` sairia igual ao `DTSTART` e o compromisso apareceria
    como um instante sem duração na agenda. Preferimos um minuto visível a um
    evento que o cliente de agenda descarta calado.
    """
    try:
        valor = int(getattr(e, "duracao_min", None) or DURACAO_MIN)
    except (TypeError, ValueError):
        return DURACAO_MIN
    return max(1, valor)


def _brasilia(dt: datetime) -> datetime:
    """UTC-3 na mão. O container roda em UTC (armadilha da v2.41) e `zoneinfo`
    depende da base de fusos do sistema, que a imagem slim não garante — um
    `ZoneInfo` ausente levantaria dentro do envio de e-mail."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc) - timedelta(hours=3)


def data_hora_br(dt: datetime | None) -> str:
    """`12/08/2026 às 14:00` — hora de Brasília, como tudo que a pessoa lê."""
    if dt is None:
        return ""
    return _brasilia(dt).strftime("%d/%m/%Y às %H:%M")


def erros_de_modalidade(modalidade: str | None, local: str | None,
                        link_reuniao: str | None) -> list[str]:
    """O que impede de MARCAR, em linguagem de tela (cenário 29).

    Online sem link é o caso que importa: o e-mail sairia dizendo "entrevista
    online" sem dizer por onde entrar, e a pessoa ficaria esperando um link que
    nunca vem. Presencial sem endereço é tolerado — "telefone", "nossa sede" e
    o combinado por WhatsApp são rotina, e travar aí só faria o RH inventar
    texto para o campo.
    """
    if modalidade is None:
        return []
    if modalidade == "online" and not (link_reuniao or "").strip():
        return ["Entrevista online precisa do link da reunião — sem ele o "
                "convite chega sem dizer por onde entrar."]
    return []


def onde_e(modalidade: str | None, local: str | None,
           link_reuniao: str | None) -> str:
    """A frase `{{onde}}` do e-mail, montada em PYTHON conforme a modalidade.

    É a regra da v2.06: o template é apresentação, a decisão é do código. Duas
    variáveis soltas obrigariam o RH a escrever um texto que serve aos dois
    casos, e um deles sairia vazio no e-mail que a pessoa usa para saber aonde ir.
    """
    if modalidade == "online":
        link = (link_reuniao or "").strip()
        return (f"É uma entrevista online. Link da reunião: {link}"
                if link else "É uma entrevista online.")
    endereco = (local or "").strip()
    if modalidade == "presencial":
        return (f"É presencial, em: {endereco}" if endereco
                else "É presencial. O RH confirma o endereço com você.")
    # Modalidade não informada (registro anterior à v2.66, ou o RH não marcou):
    # diz o que se sabe, sem inventar. Frase vazia deixaria um buraco no e-mail.
    return (f"Local: {endereco}" if endereco
            else "O RH confirma com você onde será.")


def motivo_sem_envio(pessoa_email: str | None,
                     marcada_para: datetime | None) -> str | None:
    """Por que este convite/lembrete NÃO pode sair. None = pode.

    A tela mostra este texto ao lado do interruptor do lembrete (cenário 26).
    "Não enviado" sem motivo faria o RH tentar de novo achando que foi falha de
    rede, quando o que falta é o e-mail da pessoa no cadastro.
    """
    if not (pessoa_email or "").strip():
        return ("Esta pessoa não tem e-mail no cadastro — o lembrete fica "
                "desligado. Cadastre o e-mail para poder avisá-la.")
    if marcada_para is None:
        return ("Esta entrevista não tem data marcada (foi registrada como já "
                "realizada), então não há o que lembrar.")
    return None


def _contexto(pessoa_nome: str, e) -> dict:
    primeiro = (pessoa_nome or "").split()[0] if (pessoa_nome or "").strip() else ""
    return {
        "primeiro_nome": primeiro, "nome": pessoa_nome or "",
        "data_hora": data_hora_br(e.marcada_para),
        "onde": onde_e(e.modalidade, e.local, e.link_reuniao),
        "vaga": e.vaga_titulo or "",
    }


def _anexo_ics(db, e, pessoa_email: str | None, cancelar: bool) -> list[tuple]:
    """O `.ics`, com o UID ESTÁVEL da entrevista e a sequência atual.

    Sem data marcada não há convite — e é o único caso em que o e-mail sai sem
    anexo (uma entrevista registrada como já realizada não tem o que agendar).

    O `ORGANIZER` passou a sair do **remetente de recrutamento** (v2.67, § 15.5
    item 5), que cai no `smtp_from` quando a chave está vazia. Ele importa mais
    do que parece: é o endereço para o qual o cliente de agenda manda o
    "aceito/recusado" da pessoa, e era o `smtp_from` chumbado do `.env` — que
    em produção é a caixa de LOGIN, não a de recrutamento.
    """
    if e.marcada_para is None:
        return []
    from app.services.config_dinamica import email_recrutamento
    resumo = f"Entrevista — Green House{f' · {e.vaga_titulo}' if e.vaga_titulo else ''}"
    dados = calendario.gerar_ics(
        entrevista_id=e.id, inicio=e.marcada_para, resumo=resumo,
        descricao=onde_e(e.modalidade, e.local, e.link_reuniao),
        local=((e.link_reuniao or "") if e.modalidade == "online"
               else (e.local or "")),
        organizador_email=email_recrutamento(db),
        convidado_email=pessoa_email or None,
        sequencia=e.sequencia_convite or 0, cancelar=cancelar,
        duracao_min=duracao_de(e))
    return [(calendario.nome_do_arquivo(e.id), dados)]


def enviar_convite(db, e, pessoa_nome: str, pessoa_email: str | None, *,
                   cancelar: bool = False) -> dict:
    """Manda o convite (ou o cancelamento) e carimba a entrevista.

    **A sequência do RFC 5545 incrementa ANTES de gerar o arquivo** quando é
    reenvio: o cliente de agenda só aceita a atualização se o número for maior
    que o que ele já tem. Com sequência igual e mesmo UID, a remarcação é
    ignorada **em silêncio** e a pessoa vem no horário velho (cenário 27).

    Devolve `{enviado, motivo}` — nunca levanta. Marcar a entrevista é o ato
    principal; SMTP fora do ar não pode impedir o RH de registrar o compromisso.
    O resultado é ANUNCIADO na tela, não engolido.
    """
    motivo = motivo_sem_envio(pessoa_email, e.marcada_para)
    if motivo:
        return {"enviado": False, "motivo": motivo}

    if e.convite_enviado_em is not None:
        # Já houve convite: esta é uma ATUALIZAÇÃO (remarcação ou cancelamento).
        e.sequencia_convite = (e.sequencia_convite or 0) + 1

    chave = "entrevista_cancelada" if cancelar else "entrevista_marcada"
    aviso = None
    try:
        from app.services.config_dinamica import email_recrutamento_escolhido
        from app.services.email_templates import enviar_modelo_com_aviso
        # `_escolhido` (e NÃO `email_recrutamento`) de propósito: o `From` só é
        # pedido quando o RH escolheu um endereço. Com a chave vazia o fallback
        # devolveria o próprio `smtp_from`, e pedir ao Graph para enviar como a
        # caixa que já se é levaria a um aviso de `Send As` sobre uma
        # configuração que ninguém fez (cenário 40 exige silêncio aqui).
        # O `.ics` continua usando o fallback — lá o endereço é para PREENCHER
        # um campo, não para pedir permissão.
        r = enviar_modelo_com_aviso(db, chave, pessoa_email,
                                    _contexto(pessoa_nome, e),
                                    anexos=_anexo_ics(db, e, pessoa_email, cancelar),
                                    remetente=email_recrutamento_escolhido(db))
        ok, aviso = r.get("ok"), r.get("aviso")
    except Exception:
        log.exception("Falha ao enviar convite da entrevista %s", e.id)
        return {"enviado": False,
                "motivo": "Não conseguimos enviar o e-mail agora. A entrevista "
                          "foi registrada; tente reenviar o convite."}

    if ok and not cancelar:
        e.convite_enviado_em = datetime.now(timezone.utc)
        # Convite novo zera o lembrete: remarcou, a pessoa precisa ser lembrada
        # da data NOVA. Sem isso o lembrete da véspera nunca sairia para uma
        # entrevista remarcada, porque o carimbo antigo continuaria lá.
        e.lembrete_enviado_em = None
    # `aviso` é o TERCEIRO desfecho (v2.68, § 16.1, cenário 39): o e-mail SAIU,
    # mas do endereço de sempre, porque o `Send As` do remetente de recrutamento
    # não está liberado no tenant. `enviado` continua True — a pessoa recebeu o
    # convite — e o aviso diz ao RH o que falta fazer no admin do M365. Dizer
    # só "enviado" esconderia que a configuração dele não está valendo.
    return {"enviado": bool(ok),
            "motivo": None if ok else
                      "O sistema não conseguiu enviar o e-mail (confira as "
                      "configurações de e-mail em Configurações).",
            "aviso": aviso}


def deve_lembrar(e, agora: datetime | None = None) -> bool:
    """Está na janela do lembrete da véspera?

    Só entrevista `marcada`, com data, ainda NO FUTURO e dentro das próximas
    `LEMBRETE_HORAS_ANTES`. Lembrar de entrevista que já passou é ruído — e o
    que cobra a que passou é a fila de PENDÊNCIAS, que fala com o RH, não com a
    pessoa.
    """
    from app.models.entrevista import StatusEntrevista

    agora = agora or datetime.now(timezone.utc)
    status = e.status.value if hasattr(e.status, "value") else e.status
    if status != StatusEntrevista.marcada.value or e.marcada_para is None:
        return False
    if e.lembrete_enviado_em is not None:
        return False        # uma vez por entrevista; duas viram spam
    quando = e.marcada_para
    if quando.tzinfo is None:
        quando = quando.replace(tzinfo=timezone.utc)
    if quando <= agora:
        return False        # já passou
    return quando - agora <= timedelta(hours=LEMBRETE_HORAS_ANTES)


def enviar_lembrete(db, e, pessoa_nome: str, pessoa_email: str | None) -> bool:
    """O lembrete da véspera. Carimba para não repetir."""
    if motivo_sem_envio(pessoa_email, e.marcada_para):
        return False
    try:
        from app.services.config_dinamica import email_recrutamento_escolhido
        from app.services.email_templates import enviar_modelo_com_aviso
        # O lembrete passa pelo MESMO caminho do convite — inclusive o reenvio
        # da caixa conectada quando o `Send As` não está liberado. Aqui o aviso
        # não vai para tela nenhuma (quem chama é o worker da véspera, sem
        # ninguém olhando); fica no log, que é onde se procura depois.
        r = enviar_modelo_com_aviso(db, "entrevista_lembrete", pessoa_email,
                                    _contexto(pessoa_nome, e),
                                    remetente=email_recrutamento_escolhido(db))
        ok = r.get("ok")
        if r.get("aviso"):
            log.warning("Lembrete da entrevista %s: %s", e.id, r["aviso"])
    except Exception:
        log.exception("Falha ao enviar lembrete da entrevista %s", e.id)
        return False
    if ok:
        e.lembrete_enviado_em = datetime.now(timezone.utc)
    return bool(ok)
