"""Matriz de notificações internas: QUAL evento avisa QUEM (v1.82).

Antes, o único aviso interno do sistema ("candidato concluiu o envio") ia para
`smtp_from` — a caixa de LOGIN do e-mail, que é pessoal. O Bruno recebia no
e-mail dele e não tinha como mudar (feedback 2026-07-22).

O desenho é uma MATRIZ evento × destinatários, e não um campo de e-mail:
- cada evento interno tem uma linha, com destinatários próprios;
- quem não configurou nada herda o padrão global (`email_avisos_internos`, que
  já existia), e este por sua vez cai no remetente — ninguém deixa de ser
  avisado por esquecimento de configuração;
- um evento pode ser DESLIGADO (`ativo: false`) sem apagar a lista, para voltar
  depois sem redigitar.

Guardado como JSON na config dinâmica (chave-valor), então não precisa de
migration e as ondas seguintes (vencimento de certificado, avaliação pendente)
só acrescentam uma entrada em EVENTOS.
"""

import json
import logging
import re

from sqlalchemy.orm import Session

from app.services.config_dinamica import gravar_config, ler_config, smtp_config

log = logging.getLogger(__name__)

CHAVE = "notificacoes_matriz"
CHAVE_PADRAO = "email_avisos_internos"  # padrão global, anterior à matriz

# Catálogo dos eventos internos notificáveis. `chave` é estável (vai para o
# banco); o rótulo/descrição são para o painel. Acrescentar aqui é o que
# habilita um evento novo na tela — nada mais.
EVENTOS: list[dict] = [
    {
        "chave": "envio_concluido",
        "rotulo": "Candidato concluiu o envio",
        "descricao": "Quando o candidato clica em “Concluí meu envio” e a "
                     "documentação fica pronta para revisão.",
    },
    {
        "chave": "creche_levantamento_enviado",
        "rotulo": "Reembolso-Creche: levantamento enviado",
        "descricao": "Quando um colaborador envia (ou reenvia) o levantamento "
                     "do reembolso-creche para análise.",
    },
    {
        "chave": "talento_cadastrado",
        "rotulo": "Banco de Talentos: novo cadastro",
        "descricao": "Quando alguém se cadastra pelo formulário público do "
                     "Banco de Talentos.",
    },
    {
        "chave": "certificacao_vencendo",
        "rotulo": "Certificação prestes a vencer",
        "descricao": "Cópia do aviso que o colaborador recebe quando a "
                     "certificação está perto de vencer (brigada, NR). Use para "
                     "avisar o líder de brigada — o colaborador já é avisado "
                     "sempre.",
    },
    {
        "chave": "desenvolvimento_enviado",
        "rotulo": "Colaborador enviou curso ou certificado",
        "descricao": "Quando alguém envia algo novo para o Cadastro de "
                     "Desenvolvimento e a fila de validação cresce.",
    },
]

CHAVES_VALIDAS = {e["chave"] for e in EVENTOS}
_RE_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def email_valido(v: str) -> bool:
    return bool(_RE_EMAIL.match((v or "").strip()))


def _matriz_bruta(db: Session) -> dict:
    cru = ler_config(db, (CHAVE,)).get(CHAVE)
    if not cru:
        return {}
    try:
        dados = json.loads(cru)
        return dados if isinstance(dados, dict) else {}
    except (ValueError, TypeError):
        log.warning("matriz de notificações ilegível na config; usando o padrão")
        return {}


def destino_padrao(db: Session) -> str:
    """Para onde vai o que não tem destinatário próprio: o e-mail de avisos
    internos e, se ele estiver vazio, o próprio remetente (comportamento
    anterior — ninguém fica sem aviso)."""
    cfg = ler_config(db, (CHAVE_PADRAO,))
    return (cfg.get(CHAVE_PADRAO) or "").strip() or smtp_config(db)["from_"]


def ler_matriz(db: Session) -> dict:
    """Matriz completa para o painel: todo evento do catálogo aparece, com o que
    está configurado ou o padrão herdado."""
    salvo = _matriz_bruta(db)
    padrao = destino_padrao(db)
    saida = {}
    for ev in EVENTOS:
        cfg = salvo.get(ev["chave"]) or {}
        emails = [e for e in (cfg.get("emails") or []) if email_valido(e)]
        saida[ev["chave"]] = {
            "emails": emails,
            "ativo": cfg.get("ativo", True),
            # o que realmente será usado se ninguém preencher a lista
            "herdado": padrao if not emails else None,
        }
    return saida


def gravar_matriz(db: Session, matriz: dict) -> dict:
    """Grava só os eventos do catálogo; ignora chave desconhecida (o painel de
    uma versão futura não suja a config de uma antiga). O caller commita."""
    limpa = {}
    for chave, cfg in (matriz or {}).items():
        if chave not in CHAVES_VALIDAS:
            continue
        emails, vistos = [], set()
        for e in (cfg or {}).get("emails") or []:
            e = (e or "").strip()
            if e and email_valido(e) and e.lower() not in vistos:
                vistos.add(e.lower())
                emails.append(e)
        limpa[chave] = {"emails": emails, "ativo": bool((cfg or {}).get("ativo", True))}
    gravar_config(db, {CHAVE: json.dumps(limpa, ensure_ascii=False)})
    return limpa


def destinatarios(db: Session, evento: str) -> list[str]:
    """Para quem mandar o aviso do `evento`. Lista vazia = não mandar (o evento
    foi desligado de propósito).

    Evento fora do catálogo cai no padrão em vez de sumir: um aviso novo que
    alguém esqueceu de cadastrar aqui ainda chega a alguém."""
    if evento not in CHAVES_VALIDAS:
        return [destino_padrao(db)]
    cfg = (_matriz_bruta(db).get(evento)) or {}
    if not cfg.get("ativo", True):
        return []
    emails = [e for e in (cfg.get("emails") or []) if email_valido(e)]
    return emails or [destino_padrao(db)]


def avisar(db: Session, evento: str, assunto: str, corpo: str,
           html: str | None = None) -> int:
    """Manda o aviso interno do `evento` a quem estiver configurado. Devolve
    quantos e-mails saíram. Nunca levanta: aviso interno que falha não pode
    derrubar a ação do candidato/colaborador que o disparou."""
    from app.services.email import enviar_email
    enviados = 0
    for endereco in destinatarios(db, evento):
        try:
            enviar_email(endereco, assunto, corpo, html)
            enviados += 1
        except Exception:
            log.warning("falha ao avisar %s sobre %s", endereco, evento, exc_info=True)
    return enviados
