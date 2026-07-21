"""Portal único de retorno do candidato: CPF + perguntas de verificação (KBA).

Desenho de segurança:
- A KBA é CONVENIÊNCIA, não fortaleza: o fallback (e a segurança real) continua
  sendo a posse do e-mail cadastrado, via link mágico.
- Anti-enumeração: CPF inexistente recebe perguntas do mesmo pool e a mesma
  resposta de erro — nada revela quem está em processo de admissão.
- Bloqueio progressivo por CPF+IP após falhas repetidas; tudo na auditoria.
- O desafio é stateless: token assinado com TTL de 10 minutos.
"""

from fastapi import APIRouter, Depends, HTTPException, Request
from itsdangerous import BadSignature
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import base_url_publica, ip_do_cliente
from app.core.db import get_db
from app.models.candidato import Candidato
from app.models.ficha import DocumentosIdentificacao
from app.services import kba
from app.services.auditoria import registrar
from app.services.email import enviar_email, html_moderno
from app.services.magic_link import emitir_link
from app.services.validacao import cpf_valido

router = APIRouter(tags=["entrada-candidato"])

SALT = "entrada-kba"


def _candidato_pelo_cpf(db: Session, cpf: str) -> Candidato | None:
    """O processo MAIS RECENTE daquele CPF (recontratações geram novo processo)."""
    docs = db.scalars(select(DocumentosIdentificacao)
                      .where(DocumentosIdentificacao.cpf == cpf)).all()
    candidatos = [db.get(Candidato, d.candidato_id) for d in docs]
    candidatos = [c for c in candidatos if c is not None]
    if not candidatos:
        return None
    return max(candidatos, key=lambda c: c.criado_em)


class IniciarIn(BaseModel):
    cpf: str


@router.post("/entrar/iniciar")
def iniciar(payload: IniciarIn, request: Request, db: Session = Depends(get_db)) -> dict:
    cpf = "".join(c for c in payload.cpf if c.isdigit())
    if not cpf_valido(cpf):
        raise HTTPException(status_code=422, detail="cpf_invalido")
    ip = ip_do_cliente(request) or "-"
    if kba.bloqueado(f"cpf:{cpf}") or kba.bloqueado(f"ip:{ip}"):
        raise HTTPException(status_code=429, detail="muitas_tentativas")

    candidato = _candidato_pelo_cpf(db, cpf)
    # CPF inexistente OU sem dados suficientes cai no pool genérico (gabarito
    # impossível) — resposta uniforme, nada revela; o fallback por e-mail segue.
    return kba.montar_desafio(db, candidato, SALT, extra_payload={"cpf": cpf})


class ResponderIn(BaseModel):
    desafio: str
    respostas: dict[str, str]


@router.post("/entrar/responder")
def responder(payload: ResponderIn, request: Request, db: Session = Depends(get_db)) -> dict:
    ip = ip_do_cliente(request) or "-"
    try:
        dados = kba.serializer(SALT).loads(payload.desafio, max_age=kba.DESAFIO_TTL_S)
    except BadSignature:
        raise HTTPException(status_code=422, detail="desafio_expirado")
    cpf = dados["cpf"]
    if kba.bloqueado(f"cpf:{cpf}") or kba.bloqueado(f"ip:{ip}"):
        raise HTTPException(status_code=429, detail="muitas_tentativas")

    if not kba.conferir_respostas(dados["gabarito"], payload.respostas):
        kba.registrar_falha(f"cpf:{cpf}", f"ip:{ip}")
        registrar(db, "entrada_kba_falhou", ator="candidato",
                  detalhe={"cpf_final": cpf[-4:], "ip": ip})
        db.commit()
        # Resposta uniforme: não revela se o CPF existe nem qual pergunta errou.
        raise HTTPException(status_code=422, detail="nao_confirmado")

    candidato = _candidato_pelo_cpf(db, cpf)
    link = emitir_link(db, candidato, base_url_publica(request))
    registrar(db, "entrada_kba_ok", ator="candidato", candidato_id=candidato.id,
              detalhe={"ip": ip})
    db.commit()
    return {"link": link}


class LinkEmailIn(BaseModel):
    cpf: str


@router.post("/entrar/link-email", status_code=204)
def link_por_email(payload: LinkEmailIn, request: Request,
                   db: Session = Depends(get_db)) -> None:
    """Fallback: envia um novo link mágico ao e-mail cadastrado. Sempre 204 —
    não revela se o CPF existe."""
    cpf = "".join(c for c in payload.cpf if c.isdigit())
    ip = ip_do_cliente(request) or "-"
    if _bloqueado(f"ip:{ip}"):
        raise HTTPException(status_code=429, detail="muitas_tentativas")
    candidato = _candidato_pelo_cpf(db, cpf)
    registrar(db, "entrada_link_email", ator="candidato",
              detalhe={"cpf_final": cpf[-4:] if cpf else "-", "ip": ip,
                       "encontrado": candidato is not None})
    db.commit()
    if candidato is None:
        return
    link = emitir_link(db, candidato, base_url_publica(request))
    db.commit()
    enviar_email(
        candidato.email,
        "🌱 Green House — seu link de acesso à admissão",
        f"Olá, {candidato.nome_completo.split()[0].title()}!\n\n"
        f"Você pediu um novo acesso à sua admissão. Use o link abaixo:\n{link}\n\n"
        "Se não foi você, ignore esta mensagem.\n",
        html_moderno(
            "Seu link de acesso",
            [
                f"Olá, <strong>{candidato.nome_completo.split()[0].title()}</strong>!",
                "Você pediu um novo acesso à sua admissão pelo portal. "
                "Toque no botão para continuar de onde parou.",
                "Se não foi você quem pediu, ignore esta mensagem.",
            ],
            botao_texto="Continuar minha admissão",
            botao_url=link,
        ),
    )
