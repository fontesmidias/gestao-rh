"""Testes já respondidos que o RH pode aproveitar para um candidato (v2.21).

O RH escolhe da lista; por isso a lista precisa dar CONTEXTO SUFICIENTE PARA
RECONHECER a pessoa — nome, quando respondeu, qual teste e por qual link. O
link avulso de testagem é anônimo (`ParticipanteTestagem` guarda só o nome), e
homônimo existe: mostrar só "José Silva" convidaria ao erro, e teste decide
contratação.

Quando o teste veio pelo Banco de Talentos (`talento_id` no link), a identidade
existe de verdade — esses aparecem marcados e são vinculados automaticamente na
conversão talento → candidato.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.prova import AplicacaoProva, LinkProva, ProvaCargo
from app.models.teste import StatusTeste
from app.models.teste_vinculado import OrigemTesteVinculado, TesteVinculado
from app.models.testagem import (LinkTestagem, ParticipanteTestagem,
                                 TesteTestagem)


def _ja_vinculados(db: Session) -> tuple[set, set]:
    """(participantes, aplicações) já usados por QUALQUER candidato."""
    linhas = db.execute(
        select(TesteVinculado.participante_id, TesteVinculado.aplicacao_id)).all()
    return ({p for p, _ in linhas if p}, {a for _, a in linhas if a})


def disponiveis(db: Session, busca: str | None = None,
                limite: int = 60) -> list[dict]:
    """Testes e provas CONCLUÍDOS que ainda não foram vinculados a ninguém.

    `busca` filtra pelo nome de quem respondeu — o RH normalmente sabe o nome e
    quer confirmar data e origem antes de escolher.
    """
    usados_part, usados_apl = _ja_vinculados(db)
    termo = (busca or "").strip().lower()
    saida: list[dict] = []

    # ---------------------------------------------------- DISC / situacional
    participantes = db.scalars(
        select(ParticipanteTestagem).order_by(
            ParticipanteTestagem.criado_em.desc())).all()
    links = {lk.id: lk for lk in db.scalars(select(LinkTestagem)).all()}
    testes_por_part: dict = {}
    for t in db.scalars(select(TesteTestagem)):
        testes_por_part.setdefault(t.participante_id, []).append(t)

    for p in participantes:
        if p.id in usados_part:
            continue
        if termo and termo not in (p.nome or "").lower():
            continue
        meus = testes_por_part.get(p.id, [])
        concluidos = [t for t in meus if t.status == StatusTeste.concluido]
        if not concluidos:
            continue  # só vale aproveitar o que a pessoa terminou
        lk = links.get(p.link_id)
        saida.append({
            "origem": OrigemTesteVinculado.testagem.value,
            "referencia_id": str(p.id),
            "nome_respondente": p.nome,
            "quando": max(t.concluido_em for t in concluidos if t.concluido_em)
            if any(t.concluido_em for t in concluidos) else p.criado_em,
            "o_que": ", ".join(sorted({t.tipo.value for t in concluidos})),
            "link_nome": lk.nome if lk else None,
            # identidade CONHECIDA: o link foi disparado para um talento
            "identificado": bool(lk and lk.talento_id),
            "talento_id": str(lk.talento_id) if lk and lk.talento_id else None,
        })

    # ------------------------------------------------------------- provas
    aplicacoes = db.scalars(
        select(AplicacaoProva).order_by(AplicacaoProva.criado_em.desc())).all()
    links_prova = {lk.id: lk for lk in db.scalars(select(LinkProva)).all()}
    provas = {pr.id: pr for pr in db.scalars(select(ProvaCargo)).all()}

    for a in aplicacoes:
        if a.id in usados_apl or a.concluido_em is None:
            continue
        if termo and termo not in (a.nome or "").lower():
            continue
        lk = links_prova.get(a.link_id)
        pr = provas.get(a.prova_id)
        saida.append({
            "origem": OrigemTesteVinculado.prova.value,
            "referencia_id": str(a.id),
            "nome_respondente": a.nome,
            "quando": a.concluido_em,
            "o_que": pr.titulo if pr else "Prova",
            "link_nome": lk.nome if lk else None,
            "identificado": bool(lk and lk.talento_id),
            "talento_id": str(lk.talento_id) if lk and lk.talento_id else None,
        })

    saida.sort(key=lambda x: x["quando"] or "", reverse=True)
    return saida[:limite]


def resultado_do_vinculo(db: Session, v: TesteVinculado) -> dict:
    """Lê o resultado LÁ NA ORIGEM — o vínculo aponta, nunca copia."""
    base = {
        "id": str(v.id), "origem": v.origem.value,
        "automatico": v.automatico,
        "vinculado_por": v.vinculado_por, "vinculado_em": v.vinculado_em,
    }
    if v.origem is OrigemTesteVinculado.testagem and v.participante_id:
        p = db.get(ParticipanteTestagem, v.participante_id)
        if p is None:
            return {**base, "indisponivel": True}
        testes = db.scalars(select(TesteTestagem).where(
            TesteTestagem.participante_id == p.id)).all()
        lk = db.get(LinkTestagem, p.link_id)
        return {**base,
                "nome_respondente": p.nome,
                "link_nome": lk.nome if lk else None,
                "testes": [{"tipo": t.tipo.value, "status": t.status.value,
                            "concluido_em": t.concluido_em,
                            "resultado": t.resultado} for t in testes]}

    if v.origem is OrigemTesteVinculado.prova and v.aplicacao_id:
        a = db.get(AplicacaoProva, v.aplicacao_id)
        if a is None:
            return {**base, "indisponivel": True}
        lk = db.get(LinkProva, a.link_id)
        pr = db.get(ProvaCargo, a.prova_id)
        return {**base,
                "nome_respondente": a.nome,
                "link_nome": lk.nome if lk else None,
                "prova": pr.titulo if pr else None,
                "concluido_em": a.concluido_em,
                "nota_final": a.nota_final,
                "nota_objetivas": a.nota_objetivas}

    return {**base, "indisponivel": True}


def vincular(db: Session, candidato_id: uuid.UUID, origem: str,
             referencia_id: uuid.UUID, autor: str | None,
             automatico: bool = False) -> TesteVinculado:
    """Cria o vínculo. Repetir o mesmo teste devolve o vínculo existente."""
    o = OrigemTesteVinculado(origem)
    campo = "participante_id" if o is OrigemTesteVinculado.testagem else "aplicacao_id"
    existente = db.scalar(
        select(TesteVinculado).where(
            TesteVinculado.candidato_id == candidato_id,
            getattr(TesteVinculado, campo) == referencia_id))
    if existente is not None:
        return existente
    v = TesteVinculado(candidato_id=candidato_id, origem=o,
                       automatico=automatico, vinculado_por=autor,
                       **{campo: referencia_id})
    db.add(v)
    db.flush()
    return v
