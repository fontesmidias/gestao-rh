"""Resolução da memória do RH (anotações e tags) por PESSOA.

A pessoa vive em dois registros — `talento` e `candidato` — ligados por
`talento.candidato_id`. Estas funções recebem UM lado (talento_id OU
candidato_id) e devolvem a memória dos DOIS lados quando há vínculo, para a
anotação criada no talento "seguir a pessoa" após a conversão, sem cópia.

`escopo_pessoa` é o núcleo: dado um lado, descobre o par (o outro id) e devolve
os predicados OR usados nas consultas de anotação/tag."""
import uuid

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models.candidato import Candidato
from app.models.crm import Anotacao, PessoaTag, Tag
from app.models.talento import Talento


def escopo_pessoa(db: Session, *, talento_id: uuid.UUID | None = None,
                  candidato_id: uuid.UUID | None = None) -> dict:
    """Descobre AMBOS os ids da mesma pessoa a partir de um lado.

    - talento_id dado → o candidato é `talento.candidato_id` (se convertido).
    - candidato_id dado → o talento é aquele cujo `candidato_id` == candidato_id
      (consulta reversa; pode não existir se a pessoa nunca foi talento).

    Devolve {"talento_id": ..., "candidato_id": ...} com o que existir."""
    tid, cid = talento_id, candidato_id
    if talento_id is not None and candidato_id is None:
        t = db.get(Talento, talento_id)
        if t is not None:
            cid = t.candidato_id
    elif candidato_id is not None and talento_id is None:
        tid = db.scalar(select(Talento.id).where(Talento.candidato_id == candidato_id))
    return {"talento_id": tid, "candidato_id": cid}


def _predicado(modelo, escopo: dict):
    """OR entre as duas FKs — casa registros de qualquer lado da pessoa.
    Se nenhum id existir, devolve um predicado sempre-falso (lista vazia)."""
    cond = []
    if escopo.get("talento_id") is not None:
        cond.append(modelo.talento_id == escopo["talento_id"])
    if escopo.get("candidato_id") is not None:
        cond.append(modelo.candidato_id == escopo["candidato_id"])
    if not cond:
        return modelo.id == None  # noqa: E711 — sempre falso, sem tocar o banco
    return or_(*cond)


def anotacoes_da_pessoa(db: Session, escopo: dict) -> list[Anotacao]:
    return list(db.scalars(
        select(Anotacao).where(_predicado(Anotacao, escopo))
        .order_by(Anotacao.criado_em.desc())))


def tags_da_pessoa(db: Session, escopo: dict) -> list[Tag]:
    ids = db.scalars(
        select(PessoaTag.tag_id).where(_predicado(PessoaTag, escopo))).all()
    if not ids:
        return []
    return list(db.scalars(select(Tag).where(Tag.id.in_(ids)).order_by(Tag.nome)))


def tags_por_talento(db: Session, talentos: list[Talento]) -> dict:
    """Mapa {talento_id: [dump_tag, ...]} em POUCAS consultas (sem N+1), já
    unindo as tags do talento e as do candidato vinculado. Para a coluna/filtro
    de tags no dash do Banco de Talentos."""
    if not talentos:
        return {}
    tids = [t.id for t in talentos]
    cids = [t.candidato_id for t in talentos if t.candidato_id]
    # talento_id -> candidato_id (para juntar os dois lados)
    cand_de = {t.id: t.candidato_id for t in talentos}

    vinculos = db.execute(
        select(PessoaTag.tag_id, PessoaTag.talento_id, PessoaTag.candidato_id).where(
            or_(PessoaTag.talento_id.in_(tids),
                PessoaTag.candidato_id.in_(cids) if cids else PessoaTag.id == None)  # noqa: E711
        )).all()
    # tags usadas → carrega os objetos Tag de uma vez
    tag_ids = {v.tag_id for v in vinculos}
    tags = {t.id: t for t in db.scalars(select(Tag).where(Tag.id.in_(tag_ids)))} if tag_ids else {}
    # índices por lado
    por_talento = {}
    por_candidato = {}
    for v in vinculos:
        if v.talento_id:
            por_talento.setdefault(v.talento_id, set()).add(v.tag_id)
        if v.candidato_id:
            por_candidato.setdefault(v.candidato_id, set()).add(v.tag_id)

    resultado = {}
    for tid in tids:
        ids = set(por_talento.get(tid, set()))
        cid = cand_de.get(tid)
        if cid:
            ids |= por_candidato.get(cid, set())
        resultado[tid] = [dump_tag(tags[i]) for i in ids if i in tags]
    return resultado


def dump_anotacao(a: Anotacao) -> dict:
    return {
        "id": a.id, "texto": a.texto, "autor": a.autor_nome,
        "quando": a.criado_em,
        "tem_anexo": bool(a.anexo_key), "anexo_nome": a.anexo_nome,
        # de qual lado foi criada (info; o front pode marcar "quando era talento")
        "origem": "talento" if a.talento_id else "candidato",
    }


def dump_tag(t: Tag) -> dict:
    return {"id": t.id, "nome": t.nome, "cor": t.cor, "ativo": t.ativo}
