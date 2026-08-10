"""Papéis e permissões — o painel que dá autonomia ao superadmin (v2.86).

Sem estas rotas o modelo de permissões seria configurável só escrevendo no
banco — que é o defeito da v2.68 (`email_recrutamento` nasceu lida pelo código,
documentada no CHANGELOG e sem tela nenhuma). Aqui a regra da casa vale
inteira: **chave de configuração sem rota e sem tela não é configurável**.

Toda rota deste arquivo exige `config:usuarios`, com uma exceção deliberada:
`GET /rh/permissoes/minhas`, que responde sobre o PRÓPRIO usuário e é o que
permite ao front esconder o que a pessoa não pode fazer. Exigir permissão ali
criaria o círculo de perguntar permissão para saber quais permissões se tem.
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.auth_rh import exige, permissoes_do_usuario, requer_rh
from app.core.db import get_db
from app.models.papel import Papel
from app.models.usuario_rh import UsuarioRH
from app.services import permissoes as cat
from app.services.auditoria import registrar

router = APIRouter(tags=["papeis"])


class PapelIn(BaseModel):
    chave: str | None = None      # só na criação; depois é imutável
    rotulo: str
    descricao: str | None = None
    permissoes: list[str] = []


def _dump(p: Papel, em_uso: int = 0) -> dict:
    return {
        "id": p.id, "chave": p.chave, "rotulo": p.rotulo,
        "descricao": p.descricao,
        # O superadmin guarda lista vazia no banco porque `pode()` não a
        # consulta. Devolver o catálogo INTEIRO aqui é o que faz a tela mostrar
        # tudo marcado, como o comportamento real dele — mostrar "0 permissões"
        # para quem pode tudo seria mentir na tela.
        "permissoes": (sorted(cat.CHAVES) if p.chave == cat.PAPEL_SUPERADMIN
                       else sorted(p.permissoes or [])),
        "de_fabrica": p.de_fabrica,
        "tudo": p.chave == cat.PAPEL_SUPERADMIN,
        "usuarios": em_uso,
    }


@router.get("/rh/permissoes/minhas")
def minhas_permissoes(db: Session = Depends(get_db),
                      rh: UsuarioRH = Depends(requer_rh)) -> dict:
    """O que EU posso — o front monta o menu a partir daqui.

    Esconder no front o que a pessoa não pode é cortesia, não segurança: quem
    protege é o `exige` de cada rota. Mas deixar visível um botão que sempre
    responde 403 ensina a equipe a ignorar mensagem de erro.
    """
    return {
        "papel": rh.papel,
        "permissoes": sorted(permissoes_do_usuario(db, rh)),
        "superadmin": rh.papel == cat.PAPEL_SUPERADMIN,
    }


@router.get("/rh/permissoes/catalogo")
def catalogo(_rh: UsuarioRH = Depends(exige("config:usuarios"))) -> dict:
    """Catálogo agrupado, para a tela desenhar as caixas de seleção."""
    return {"grupos": cat.catalogo_para_front()}


@router.get("/rh/papeis")
def listar(db: Session = Depends(get_db),
           _rh: UsuarioRH = Depends(exige("config:usuarios"))) -> list[dict]:
    papeis = db.scalars(select(Papel).order_by(Papel.criado_em)).all()
    # Quantas pessoas em cada papel: é o que impede apagar um papel achando que
    # está vazio e deixar gente sem acesso nenhum.
    usuarios = db.scalars(select(UsuarioRH)).all()
    em_uso: dict[str, int] = {}
    for u in usuarios:
        em_uso[u.papel] = em_uso.get(u.papel, 0) + 1
    return [_dump(p, em_uso.get(p.chave, 0)) for p in papeis]


@router.post("/rh/papeis", status_code=201)
def criar(payload: PapelIn, db: Session = Depends(get_db),
          rh: UsuarioRH = Depends(exige("config:usuarios"))) -> dict:
    chave = (payload.chave or "").strip().lower()
    if not chave or not chave.replace("_", "").replace("-", "").isalnum():
        raise HTTPException(status_code=422, detail="chave_invalida")
    if not (payload.rotulo or "").strip():
        raise HTTPException(status_code=422, detail="rotulo_obrigatorio")
    if db.scalar(select(Papel).where(Papel.chave == chave)) is not None:
        raise HTTPException(status_code=409, detail="chave_ja_existe")

    try:
        chaves = cat.validar_chaves(payload.permissoes)
    except ValueError as e:
        # Nomeia as chaves recusadas: um 422 genérico faria a tela mostrar a
        # caixa marcada com o acesso continuando negado, sem explicação.
        raise HTTPException(status_code=422, detail={
            "erro": "permissoes_desconhecidas", "mensagem": str(e)})

    p = Papel(chave=chave, rotulo=payload.rotulo.strip(),
              descricao=(payload.descricao or "").strip() or None,
              permissoes=chaves, de_fabrica=False)
    db.add(p)
    registrar(db, "papel_criado", ator="rh", ator_detalhe=rh.email,
              detalhe={"papel": chave, "permissoes": len(chaves)})
    db.commit()
    db.refresh(p)
    return _dump(p)


@router.put("/rh/papeis/{papel_id}")
def editar(papel_id: uuid.UUID, payload: PapelIn, db: Session = Depends(get_db),
           rh: UsuarioRH = Depends(exige("config:usuarios"))) -> dict:
    p = db.get(Papel, papel_id)
    if p is None:
        raise HTTPException(status_code=404, detail="papel_nao_encontrado")

    # O superadmin não se edita: é o papel que garante existir alguém capaz de
    # desfazer qualquer engano. Deixar tirar permissão dele permitiria fechar a
    # porta por dentro — a instalação ficaria sem ninguém que possa reabrir.
    if p.chave == cat.PAPEL_SUPERADMIN:
        raise HTTPException(status_code=409, detail="superadmin_nao_editavel")

    try:
        chaves = cat.validar_chaves(payload.permissoes)
    except ValueError as e:
        raise HTTPException(status_code=422, detail={
            "erro": "permissoes_desconhecidas", "mensagem": str(e)})

    antes = sorted(p.permissoes or [])
    if (payload.rotulo or "").strip():
        p.rotulo = payload.rotulo.strip()
    p.descricao = (payload.descricao or "").strip() or None
    p.permissoes = chaves
    # A auditoria guarda o DELTA, não só o estado final: "quem tirou o acesso
    # da Fátima e quando" é a pergunta que se faz depois, e o estado final não
    # a responde.
    registrar(db, "papel_editado", ator="rh", ator_detalhe=rh.email,
              detalhe={"papel": p.chave,
                       "concedidas": sorted(set(chaves) - set(antes)),
                       "revogadas": sorted(set(antes) - set(chaves))})
    db.commit()
    db.refresh(p)
    return _dump(p)


@router.delete("/rh/papeis/{papel_id}", status_code=204)
def excluir(papel_id: uuid.UUID, db: Session = Depends(get_db),
            rh: UsuarioRH = Depends(exige("config:usuarios"))) -> None:
    p = db.get(Papel, papel_id)
    if p is None:
        raise HTTPException(status_code=404, detail="papel_nao_encontrado")
    if p.de_fabrica:
        raise HTTPException(status_code=409, detail="papel_de_fabrica")

    # Papel em uso não se apaga: o usuário ficaria apontando para uma chave que
    # não resolve e — pela regra de `permissoes_do_usuario` — perderia TODO o
    # acesso, em silêncio, sem nada na tela dizendo por quê. O 409 diz quantas
    # pessoas seriam afetadas, para o superadmin movê-las antes.
    em_uso = db.scalars(select(UsuarioRH).where(UsuarioRH.papel == p.chave)).all()
    if em_uso:
        raise HTTPException(status_code=409, detail={
            "erro": "papel_em_uso", "usuarios": len(em_uso),
            "nomes": [u.nome for u in em_uso[:5]]})

    registrar(db, "papel_excluido", ator="rh", ator_detalhe=rh.email,
              detalhe={"papel": p.chave})
    db.delete(p)
    db.commit()
