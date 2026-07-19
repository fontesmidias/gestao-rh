"""Testes do candidato (DISC + situacional).

Fluxo do candidato (pelo link mágico da admissão):
1. GET /c/{token}/testes — quais testes estão pendentes.
2. POST identificar — confirma nome/CPF/e-mail; um CÓDIGO de 6 dígitos vai ao
   e-mail (2FA; a tela avisa para conferir o spam).
3. POST confirmar — valida o código e libera os testes.
4. POST {tipo}/iniciar — aceita o termo e dispara o timer (12 min no DISC).
5. GET {tipo}/questoes + POST {tipo}/responder + POST {tipo}/concluir.
O resultado é calculado no servidor e NUNCA devolvido ao candidato — apenas o
RH o consulta (GET /rh/candidatos/{id}/testes).

Amparo: inventário comportamental de apoio à gestão (não é teste psicológico —
avaliação psicológica é privativa de psicólogo, Res. CFP nº 31/2022); dados
tratados conforme a LGPD, com consentimento colhido na entrada.
"""

import hashlib
import secrets
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.auth_rh import requer_rh
from app.core.db import get_db
from app.models.candidato import Candidato
from app.models.teste import StatusTeste, TesteCandidato, TipoTeste
from app.models.usuario_rh import UsuarioRH
from app.services.auditoria import registrar
from app.services.disc import (PERFIS_DISC, TEMPO_DISC_SEGUNDOS,
                               TEMPO_SITUACIONAL_SEGUNDOS, pontuar_disc,
                               pontuar_situacional, questoes_disc_publicas,
                               questoes_situacional_publicas)
from app.services.email import enviar_email, html_moderno
from app.services.limite import exigir
from app.services.magic_link import resolver_token

router = APIRouter(tags=["testes"])

CODIGO_TTL_MIN = 15


def _hash(txt: str) -> str:
    return hashlib.sha256(txt.encode()).hexdigest()


def _cand(token: str, db: Session) -> Candidato:
    cand = resolver_token(db, token)
    if cand is None:
        raise HTTPException(status_code=404, detail="candidato_nao_encontrado")
    return cand


def _testes(db: Session, cand: Candidato) -> list[TesteCandidato]:
    return db.scalars(select(TesteCandidato)
                      .where(TesteCandidato.candidato_id == cand.id)
                      .order_by(TesteCandidato.criado_em)).all()


def _expira_se_estourou(db: Session, t: TesteCandidato) -> None:
    if (t.status == StatusTeste.em_andamento and t.prazo_ate
            and t.prazo_ate < datetime.now(timezone.utc)):
        # tempo estourado: pontua com o que foi respondido até aqui
        t.resultado = (pontuar_disc(t.respostas or []) if t.tipo == TipoTeste.disc
                       else pontuar_situacional(t.respostas or []))
        t.status = StatusTeste.expirado
        t.concluido_em = datetime.now(timezone.utc)
        db.commit()


def _dump_teste_candidato(t: TesteCandidato) -> dict:
    """Visão do CANDIDATO: nunca inclui resultado."""
    restante = None
    if t.status == StatusTeste.em_andamento and t.prazo_ate:
        restante = max(0, int((t.prazo_ate - datetime.now(timezone.utc)).total_seconds()))
    return {"tipo": t.tipo, "status": t.status,
            "identificado": t.identificado_em is not None,
            "segundos_restantes": restante,
            "respondidas": len(t.respostas or [])}


# ---------------------------------------------------------------------------
# Candidato
# ---------------------------------------------------------------------------


@router.get("/c/{token}/testes")
def listar_testes(token: str, db: Session = Depends(get_db)) -> dict:
    cand = _cand(token, db)
    testes = _testes(db, cand)
    for t in testes:
        _expira_se_estourou(db, t)
    pendentes = [t for t in testes
                 if t.status in (StatusTeste.pendente, StatusTeste.em_andamento)]
    return {
        "tem_testes": bool(testes),
        "pendentes": [_dump_teste_candidato(t) for t in pendentes],
        "todos_concluidos": bool(testes) and not pendentes,
        "identificado": bool(testes) and all(t.identificado_em for t in testes),
        "nome": cand.nome_completo, "email": cand.email,
    }


class IdentificarIn(BaseModel):
    nome_completo: str
    cpf: str
    email: str


@router.post("/c/{token}/testes/identificar")
def identificar(token: str, payload: IdentificarIn, db: Session = Depends(get_db)) -> dict:
    """Identificação mínima antes do teste. O código 2FA vai ao e-mail informado
    (que também atualiza o cadastro se o convite veio sem e-mail)."""
    from app.services.validacao import cpf_valido
    # evita disparo de e-mails em série pelo mesmo link
    exigir(f"teste-ident:{token[:16]}", maximo=5, janela_s=900)
    cand = _cand(token, db)
    cpf = "".join(c for c in payload.cpf if c.isdigit())
    if not cpf_valido(cpf):
        raise HTTPException(status_code=422, detail="cpf_invalido")
    email = payload.email.strip()
    if "@" not in email:
        raise HTTPException(status_code=422, detail="email_invalido")
    testes = _testes(db, cand)
    if not testes:
        raise HTTPException(status_code=404, detail="sem_testes")
    codigo = f"{secrets.randbelow(10**6):06d}"
    for t in testes:
        t.codigo_hash = _hash(codigo)
        t.codigo_expira_em = datetime.now(timezone.utc) + timedelta(minutes=CODIGO_TTL_MIN)
    # guarda o que o candidato informou (nome pode corrigir grafia; email idem)
    if not cand.email:
        cand.email = email
    if not cand.cpf:
        cand.cpf = f"{cpf[:3]}.{cpf[3:6]}.{cpf[6:9]}-{cpf[9:]}"
    registrar(db, "teste_identificacao", ator="candidato", candidato_id=cand.id)
    db.commit()
    enviar_email(
        email,
        "Green House — código de confirmação para o seu teste",
        f"Olá, {payload.nome_completo.split()[0].title()}!\n\n"
        f"Seu código de confirmação é: {codigo}\n\n"
        "Ele vale por 15 minutos.\n\n"
        "IMPORTANTE: verifique também a caixa de SPAM/lixo eletrônico.\n",
        html_moderno(
            "Código de confirmação",
            [
                f"Olá, <strong>{payload.nome_completo.split()[0].title()}</strong>!",
                "Use o código abaixo para confirmar sua identidade e iniciar o teste:",
                f"<div style='font-size:2rem;font-weight:800;letter-spacing:.3em;"
                f"text-align:center;margin:1rem 0;color:#0a8f46'>{codigo}</div>",
                "O código vale por 15 minutos. <strong>Verifique também a caixa de "
                "spam</strong> — a mensagem pode ter ido para lá.",
            ],
        ),
    )
    return {"enviado": True}


class ConfirmarIn(BaseModel):
    codigo: str


@router.post("/c/{token}/testes/confirmar")
def confirmar(token: str, payload: ConfirmarIn, db: Session = Depends(get_db)) -> dict:
    # código de 6 dígitos + 10 tentativas por janela: força bruta inviável no TTL
    exigir(f"teste-2fa:{token[:16]}", maximo=10, janela_s=900)
    cand = _cand(token, db)
    testes = _testes(db, cand)
    agora = datetime.now(timezone.utc)
    ok = any(t.codigo_hash == _hash(payload.codigo.strip())
             and t.codigo_expira_em and t.codigo_expira_em > agora for t in testes)
    if not ok:
        raise HTTPException(status_code=422, detail="codigo_invalido")
    for t in testes:
        t.identificado_em = agora
    registrar(db, "teste_2fa_confirmado", ator="candidato", candidato_id=cand.id)
    db.commit()
    return {"confirmado": True}


def _teste_do_tipo(db: Session, cand: Candidato, tipo: str) -> TesteCandidato:
    try:
        tipo_enum = TipoTeste(tipo)
    except ValueError:
        raise HTTPException(status_code=422, detail="tipo_invalido")
    t = db.scalar(select(TesteCandidato).where(
        TesteCandidato.candidato_id == cand.id, TesteCandidato.tipo == tipo_enum))
    if t is None:
        raise HTTPException(status_code=404, detail="teste_nao_encontrado")
    if t.identificado_em is None:
        raise HTTPException(status_code=403, detail="identificacao_pendente")
    _expira_se_estourou(db, t)
    return t


@router.post("/c/{token}/testes/{tipo}/iniciar")
def iniciar_teste(token: str, tipo: str, db: Session = Depends(get_db)) -> dict:
    """Aceita as orientações/termo e dispara o timer. Só pode UMA vez."""
    cand = _cand(token, db)
    t = _teste_do_tipo(db, cand, tipo)
    if t.status == StatusTeste.em_andamento:
        return _dump_teste_candidato(t)  # retomada (recarregou a página)
    if t.status != StatusTeste.pendente:
        raise HTTPException(status_code=409, detail="teste_ja_realizado")
    segundos = TEMPO_DISC_SEGUNDOS if t.tipo == TipoTeste.disc else TEMPO_SITUACIONAL_SEGUNDOS
    t.status = StatusTeste.em_andamento
    t.aceite_em = datetime.now(timezone.utc)
    t.iniciado_em = datetime.now(timezone.utc)
    t.prazo_ate = t.iniciado_em + timedelta(seconds=segundos)
    registrar(db, "teste_iniciado", ator="candidato", candidato_id=cand.id,
              detalhe={"tipo": tipo})
    db.commit()
    return _dump_teste_candidato(t)


@router.get("/c/{token}/testes/{tipo}/questoes")
def questoes(token: str, tipo: str, db: Session = Depends(get_db)) -> dict:
    cand = _cand(token, db)
    t = _teste_do_tipo(db, cand, tipo)
    if t.status != StatusTeste.em_andamento:
        raise HTTPException(status_code=409, detail="teste_nao_iniciado")
    qs = (questoes_disc_publicas() if t.tipo == TipoTeste.disc
          else questoes_situacional_publicas())
    return {"questoes": qs, **_dump_teste_candidato(t)}


class RespostaIn(BaseModel):
    questao: int
    # DISC: mais + menos; situacional: escolha
    mais: str | None = None
    menos: str | None = None
    escolha: str | None = None


@router.post("/c/{token}/testes/{tipo}/responder")
def responder(token: str, tipo: str, payload: RespostaIn, db: Session = Depends(get_db)) -> dict:
    cand = _cand(token, db)
    t = _teste_do_tipo(db, cand, tipo)
    if t.status != StatusTeste.em_andamento:
        raise HTTPException(status_code=409, detail="teste_nao_iniciado")
    if t.tipo == TipoTeste.disc:
        if not payload.mais or not payload.menos or payload.mais == payload.menos:
            raise HTTPException(status_code=422, detail="marque_mais_e_menos_diferentes")
        nova = {"questao": payload.questao, "mais": payload.mais, "menos": payload.menos}
    else:
        if not payload.escolha:
            raise HTTPException(status_code=422, detail="escolha_obrigatoria")
        nova = {"questao": payload.questao, "escolha": payload.escolha}
    # substitui resposta da mesma questão (o candidato pode voltar)
    respostas = [r for r in (t.respostas or []) if r.get("questao") != payload.questao]
    respostas.append(nova)
    t.respostas = respostas
    db.commit()
    return {"respondidas": len(respostas)}


class EventosIn(BaseModel):
    # cada evento: {"t": segundos desde o início, "e": tipo, "d": detalhe?}
    eventos: list[dict]


_MAX_EVENTOS = 800  # teto de segurança por teste


@router.post("/c/{token}/testes/{tipo}/eventos", status_code=204)
def registrar_eventos(token: str, tipo: str, payload: EventosIn,
                      db: Session = Depends(get_db)) -> None:
    """Telemetria de comportamento durante o teste (informada ao candidato nas
    instruções): saídas de tela, troca de aba/janela, tentativa de print,
    copiar/colar, queda de conexão. Servem para o RH entender o comportamento
    e melhorar o sistema — nunca para o candidato ver o resultado."""
    cand = _cand(token, db)
    t = _teste_do_tipo(db, cand, tipo)
    if t.status not in (StatusTeste.em_andamento, StatusTeste.concluido,
                        StatusTeste.expirado):
        return
    atuais = list(t.eventos or [])
    for ev in payload.eventos[: _MAX_EVENTOS - len(atuais)]:
        if isinstance(ev, dict) and ev.get("e"):
            atuais.append({"t": round(float(ev.get("t") or 0), 1),
                           "e": str(ev["e"])[:40],
                           **({"d": str(ev["d"])[:120]} if ev.get("d") else {})})
    t.eventos = atuais
    db.commit()


def _resumo_eventos(eventos: list) -> dict | None:
    """Síntese legível (e pronta para mandar a uma IA) da telemetria."""
    if not eventos:
        return None
    cont: dict[str, int] = {}
    fora = 0.0
    inicio_fora = None
    for ev in eventos:
        e = ev.get("e")
        cont[e] = cont.get(e, 0) + 1
        if e in ("oculto", "desfocou") and inicio_fora is None:
            inicio_fora = ev.get("t") or 0
        elif e in ("visivel", "focou") and inicio_fora is not None:
            fora += max(0.0, (ev.get("t") or 0) - inicio_fora)
            inicio_fora = None
    return {
        "total_eventos": len(eventos),
        "por_tipo": cont,
        "saidas_da_tela": cont.get("oculto", 0) + cont.get("desfocou", 0),
        "segundos_fora_da_tela": round(fora, 1),
        "tentativas_print": cont.get("print", 0),
        "copiar_colar": (cont.get("copiou", 0) + cont.get("colou", 0)
                         + cont.get("recortou", 0)),
        "quedas_de_conexao": cont.get("offline", 0),
    }


@router.post("/c/{token}/testes/{tipo}/concluir")
def concluir(token: str, tipo: str, db: Session = Depends(get_db)) -> dict:
    """Calcula e guarda o resultado (só o RH o verá) e conclui o teste."""
    cand = _cand(token, db)
    t = _teste_do_tipo(db, cand, tipo)
    if t.status == StatusTeste.expirado:
        return {"status": t.status}  # já pontuado com o que havia
    if t.status != StatusTeste.em_andamento:
        raise HTTPException(status_code=409, detail="teste_nao_iniciado")
    t.resultado = (pontuar_disc(t.respostas or []) if t.tipo == TipoTeste.disc
                   else pontuar_situacional(t.respostas or []))
    t.status = StatusTeste.concluido
    t.concluido_em = datetime.now(timezone.utc)
    registrar(db, "teste_concluido", ator="candidato", candidato_id=cand.id,
              detalhe={"tipo": tipo, "respondidas": len(t.respostas or [])})
    db.commit()
    # NUNCA devolve o resultado ao candidato
    return {"status": t.status}


# ---------------------------------------------------------------------------
# RH — resultado restrito
# ---------------------------------------------------------------------------


def _resumo_resultado(tipo: TipoTeste, resultado: dict | None) -> dict | None:
    """Resumo compacto do resultado para o dash (o completo fica no detalhe)."""
    r = resultado or None
    if not r:
        return None
    if tipo == TipoTeste.disc:
        return {"perfil": r.get("perfil"), "principal": r.get("principal"),
                "percentuais": r.get("percentuais")}
    return {"percentual": r.get("percentual"), "faixa": r.get("faixa")}


def _duracao_s(iniciado, concluido) -> int | None:
    if iniciado and concluido:
        return max(0, int((concluido - iniciado).total_seconds()))
    return None


@router.get("/rh/testes/dash", dependencies=[Depends(requer_rh)])
def dash_testes(db: Session = Depends(get_db)) -> dict:
    """Visão unificada de TODOS os testes — da admissão e da testagem avulsa —
    com status, duração, resultado resumido e comportamento (telemetria)."""
    from app.models.testagem import LinkTestagem, ParticipanteTestagem, TesteTestagem

    itens = []
    admissao = db.execute(
        select(TesteCandidato, Candidato)
        .join(Candidato, TesteCandidato.candidato_id == Candidato.id)
        .order_by(TesteCandidato.criado_em.desc())).all()
    for t, cand in admissao:
        _expira_se_estourou(db, t)
        itens.append({
            "origem": "admissao", "pessoa_id": t.candidato_id, "teste_id": t.id,
            "nome": cand.nome_completo, "contexto": cand.cargo_funcao or "admissão",
            "tipo": t.tipo, "status": t.status,
            "iniciado_em": t.iniciado_em, "concluido_em": t.concluido_em,
            "duracao_s": _duracao_s(t.iniciado_em, t.concluido_em),
            "respondidas": len(t.respostas or []),
            "resumo": _resumo_resultado(t.tipo, t.resultado),
            "resultado": t.resultado or None,
            "comportamento": _resumo_eventos(t.eventos or []),
            "eventos": t.eventos or [],
        })

    testagem = db.execute(
        select(TesteTestagem, ParticipanteTestagem, LinkTestagem)
        .join(ParticipanteTestagem, TesteTestagem.participante_id == ParticipanteTestagem.id)
        .join(LinkTestagem, ParticipanteTestagem.link_id == LinkTestagem.id)
        .order_by(TesteTestagem.criado_em.desc())).all()
    for t, p, link in testagem:
        itens.append({
            "origem": "testagem", "pessoa_id": p.id, "teste_id": t.id,
            "nome": p.nome, "contexto": link.nome,
            "tipo": t.tipo, "status": t.status,
            "iniciado_em": t.iniciado_em, "concluido_em": t.concluido_em,
            "duracao_s": _duracao_s(t.iniciado_em, t.concluido_em),
            "respondidas": len(t.respostas or []),
            "resumo": _resumo_resultado(t.tipo, t.resultado),
            "resultado": t.resultado or None,
            "comportamento": _resumo_eventos(t.eventos or []),
            "eventos": t.eventos or [],
        })

    concluidos = [i for i in itens if i["status"] in (StatusTeste.concluido,
                                                      StatusTeste.expirado)]
    duracoes = [i["duracao_s"] for i in concluidos if i["duracao_s"]]
    metricas = {
        "total": len(itens),
        "concluidos": len(concluidos),
        "em_andamento": sum(1 for i in itens if i["status"] == StatusTeste.em_andamento),
        "pendentes": sum(1 for i in itens if i["status"] == StatusTeste.pendente),
        "tempo_medio_s": round(sum(duracoes) / len(duracoes)) if duracoes else None,
        "com_alerta": sum(1 for i in itens if (i["comportamento"] or {}).get(
            "saidas_da_tela", 0) > 0),
    }
    return {"metricas": metricas, "itens": itens, "perfis": PERFIS_DISC}


@router.post("/rh/candidatos/{candidato_id}/testes/{tipo}/resetar")
def resetar_teste_rh(candidato_id: uuid.UUID, tipo: str,
                     db: Session = Depends(get_db),
                     _rh: UsuarioRH = Depends(requer_rh)) -> dict:
    """Zera o teste para a pessoa refazer: volta a pendente e limpa respostas,
    resultado e telemetria. O resultado anterior fica preservado na auditoria."""
    cand = db.get(Candidato, candidato_id)
    if cand is None:
        raise HTTPException(status_code=404, detail="candidato_nao_encontrado")
    try:
        tipo_enum = TipoTeste(tipo)
    except ValueError:
        raise HTTPException(status_code=422, detail="tipo_invalido")
    t = db.scalar(select(TesteCandidato).where(
        TesteCandidato.candidato_id == cand.id, TesteCandidato.tipo == tipo_enum))
    if t is None:
        raise HTTPException(status_code=404, detail="teste_nao_encontrado")
    registrar(db, "teste_resetado", ator="rh", ator_detalhe=_rh.email,
              candidato_id=cand.id,
              detalhe={"tipo": tipo, "status_anterior": t.status.value,
                       "resultado_anterior": t.resultado or None,
                       "respondidas": len(t.respostas or [])})
    t.status = StatusTeste.pendente
    t.respostas = []
    t.resultado = {}
    t.eventos = []
    t.iniciado_em = None
    t.prazo_ate = None
    t.concluido_em = None
    t.aceite_em = None
    db.commit()
    return {"tipo": t.tipo, "status": t.status}


class DefinirTestesIn(BaseModel):
    fazer_disc: bool
    fazer_situacional: bool


@router.put("/rh/candidatos/{candidato_id}/testes")
def definir_testes_rh(candidato_id: uuid.UUID, payload: DefinirTestesIn,
                      db: Session = Depends(get_db),
                      _rh: UsuarioRH = Depends(requer_rh)) -> dict:
    """O RH liga/desliga os testes DEPOIS do convite (antes, só dava na criação).
    Desmarcar só remove teste ainda PENDENTE (vai para a lixeira); teste já
    iniciado/concluído é mantido — resultado não se apaga por engano."""
    from app.services.lixeira import mandar_para_lixeira
    cand = db.get(Candidato, candidato_id)
    if cand is None:
        raise HTTPException(status_code=404, detail="candidato_nao_encontrado")
    desejo = {TipoTeste.disc: payload.fazer_disc,
              TipoTeste.situacional: payload.fazer_situacional}
    existentes = {t.tipo: t for t in _testes(db, cand)}
    criados, removidos, mantidos = [], [], []
    for tipo, quer in desejo.items():
        t = existentes.get(tipo)
        if quer and t is None:
            db.add(TesteCandidato(candidato_id=cand.id, tipo=tipo))
            criados.append(tipo.value)
        elif not quer and t is not None:
            if t.status == StatusTeste.pendente:
                mandar_para_lixeira(db, t, "teste_candidato",
                                    f"Teste {tipo.value} — {cand.nome_completo}",
                                    _rh.email)
                db.delete(t)
                removidos.append(tipo.value)
            else:
                mantidos.append(tipo.value)  # já iniciado/concluído: não remove
    registrar(db, "testes_editados", ator="rh", ator_detalhe=_rh.email,
              candidato_id=cand.id,
              detalhe={"criados": criados, "removidos": removidos, "mantidos": mantidos})
    db.commit()
    atuais = _testes(db, cand)
    return {"criados": criados, "removidos": removidos, "mantidos": mantidos,
            "testes": [{"tipo": t.tipo, "status": t.status} for t in atuais]}


@router.get("/rh/candidatos/{candidato_id}/testes",
            dependencies=[Depends(requer_rh)])
def resultados_rh(candidato_id: uuid.UUID, db: Session = Depends(get_db)) -> dict:
    testes = db.scalars(select(TesteCandidato)
                        .where(TesteCandidato.candidato_id == candidato_id)
                        .order_by(TesteCandidato.criado_em)).all()
    saida = []
    for t in testes:
        _expira_se_estourou(db, t)
        item = {
            "tipo": t.tipo, "status": t.status,
            "iniciado_em": t.iniciado_em, "concluido_em": t.concluido_em,
            "respondidas": len(t.respostas or []),
            "resultado": t.resultado or None,
            "comportamento": _resumo_eventos(t.eventos or []),
            "eventos": t.eventos or [],
        }
        if t.tipo == TipoTeste.disc and t.resultado:
            item["perfis"] = PERFIS_DISC  # textos de todos + o do candidato
        saida.append(item)
    return {"testes": saida}
