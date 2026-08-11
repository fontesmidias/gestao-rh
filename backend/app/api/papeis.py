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
        "ativo": p.ativo,
        "tudo": p.chave == cat.PAPEL_SUPERADMIN,
        "usuarios": em_uso,
    }


def _usuarios_do_papel(db: Session, chave: str) -> list[UsuarioRH]:
    return list(db.scalars(select(UsuarioRH).where(UsuarioRH.papel == chave)).all())


def _destinos_de_migracao(db: Session, exceto: str) -> list[dict]:
    """Papéis para onde as pessoas podem ser movidas, com o que cada um concede.

    Vai junto do 409 de propósito: recusar dizendo apenas "há 4 pessoas usando"
    deixa quem lê com o problema na mão e sem a saída — teria de sair da tela,
    conferir os papéis um a um e voltar. A escolha continua sendo de quem
    opera; o que muda é que ela cabe no mesmo lugar onde o bloqueio apareceu.
    """
    destinos = []
    for p in db.scalars(select(Papel).order_by(Papel.criado_em)).all():
        if p.chave == exceto or not p.ativo:
            continue  # migrar para papel inativo recriaria o mesmo problema
        destinos.append({
            "chave": p.chave, "rotulo": p.rotulo,
            "descricao": p.descricao,
            "permissoes": (len(cat.CHAVES) if p.chave == cat.PAPEL_SUPERADMIN
                           else len(p.permissoes or [])),
            "tudo": p.chave == cat.PAPEL_SUPERADMIN,
        })
    return destinos


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


@router.post("/rh/papeis/{papel_id}/duplicar", status_code=201)
def duplicar(papel_id: uuid.UUID, db: Session = Depends(get_db),
             rh: UsuarioRH = Depends(exige("config:usuarios"))) -> dict:
    """Cópia INATIVA — o caminho normal para criar um papel novo (v2.87).

    Partir de um papel parecido e ajustar é mais seguro do que montar do zero:
    quem começa numa tela em branco com 40 caixas tende a marcar demais (para
    a pessoa "não ficar travada") ou de menos, e o erro só aparece depois, no
    uso. Duplicar dá um ponto de partida que já funciona.

    **A cópia nasce inativa**, ao contrário do `duplicar` de provas — que herda
    `ativa=p.ativa` e por isso já vale no instante em que é criada. Aqui isso
    seria perigoso: um papel é permissão de acesso, e a cópia existe justamente
    para ser revisada ANTES de valer. Segue a semântica do roteiro de
    entrevista, cuja cópia nasce em rascunho.
    """
    p = db.get(Papel, papel_id)
    if p is None:
        raise HTTPException(status_code=404, detail="papel_nao_encontrado")

    # Chave livre a partir da original: `rh` → `rh-copia`, `rh-copia-2`…
    base = f"{p.chave}-copia"[:46]
    chave, n = base, 1
    while db.scalar(select(Papel).where(Papel.chave == chave)) is not None:
        n += 1
        chave = f"{base}-{n}"[:50]

    # O superadmin guarda lista vazia (`pode()` não a consulta), então copiar o
    # campo cru produziria um papel que não concede NADA — com o rótulo dizendo
    # o contrário. A cópia dele nasce com o catálogo inteiro, explícito.
    permissoes = (sorted(cat.CHAVES) if p.chave == cat.PAPEL_SUPERADMIN
                  else sorted(p.permissoes or []))

    novo = Papel(chave=chave, rotulo=f"{p.rotulo} (cópia)"[:100],
                 descricao=p.descricao, permissoes=permissoes,
                 de_fabrica=False, ativo=False)
    db.add(novo)
    db.flush()
    registrar(db, "papel_duplicado", ator="rh", ator_detalhe=rh.email,
              detalhe={"papel": chave, "de": p.chave,
                       "permissoes": len(permissoes)})
    db.commit()
    db.refresh(novo)
    return _dump(novo)


class AtivacaoIn(BaseModel):
    ativo: bool
    # Para onde mover quem usa o papel, quando se desativa um papel em uso.
    # Opcional: sem ele a rota RECUSA e devolve os destinos possíveis, para a
    # escolha acontecer na mesma tela.
    migrar_para: str | None = None


@router.put("/rh/papeis/{papel_id}/ativo")
def alternar_ativo(papel_id: uuid.UUID, payload: AtivacaoIn,
                   db: Session = Depends(get_db),
                   rh: UsuarioRH = Depends(exige("config:usuarios"))) -> dict:
    """Ativa ou desativa um papel. Desativar com gente dentro exige migração.

    Papel inativo não concede nada (ver `permissoes_do_usuario`), então
    desativar um papel em uso tiraria o acesso de várias pessoas **de uma vez e
    em silêncio** — o sintoma seria "403 em tudo", longe da causa. A rota
    recusa e devolve os destinos possíveis; com `migrar_para`, move as pessoas
    e desativa no MESMO ato, para não existir a janela em que elas ficam num
    papel que já não vale.
    """
    p = db.get(Papel, papel_id)
    if p is None:
        raise HTTPException(status_code=404, detail="papel_nao_encontrado")

    if payload.ativo:
        p.ativo = True
        registrar(db, "papel_ativado", ator="rh", ator_detalhe=rh.email,
                  detalhe={"papel": p.chave})
        db.commit()
        db.refresh(p)
        return _dump(p, len(_usuarios_do_papel(db, p.chave)))

    # --- Desativando -------------------------------------------------------
    if p.chave == cat.PAPEL_SUPERADMIN:
        # Mesma razão de ele não ser editável: sem superadmin ativo, ninguém
        # gere papéis e não há tela para desfazer.
        raise HTTPException(status_code=409, detail="superadmin_nao_desativavel")

    usuarios = _usuarios_do_papel(db, p.chave)
    if usuarios and not payload.migrar_para:
        raise HTTPException(status_code=409, detail={
            "erro": "papel_em_uso",
            "usuarios": len(usuarios),
            "nomes": [u.nome for u in usuarios[:8]],
            # A saída vai JUNTO do bloqueio: quem lê decide na mesma tela.
            "destinos": _destinos_de_migracao(db, p.chave),
        })

    migrados = 0
    if usuarios:
        destino = db.scalar(select(Papel).where(Papel.chave == payload.migrar_para))
        if destino is None or not destino.ativo:
            raise HTTPException(status_code=422, detail={
                "erro": "destino_invalido", "papel": payload.migrar_para})
        for u in usuarios:
            u.papel = destino.chave
            migrados += 1

    p.ativo = False
    # Auditoria nomeia PARA ONDE cada um foi: "por que a Fátima está como RH?"
    # é a pergunta que se faz depois, e o estado final não a responde.
    registrar(db, "papel_desativado", ator="rh", ator_detalhe=rh.email,
              detalhe={"papel": p.chave, "migrados": migrados,
                       "para": payload.migrar_para,
                       "usuarios": [u.email for u in usuarios]})
    db.commit()
    db.refresh(p)
    return {**_dump(p), "migrados": migrados}


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
    em_uso = _usuarios_do_papel(db, p.chave)
    if em_uso:
        raise HTTPException(status_code=409, detail={
            "erro": "papel_em_uso", "usuarios": len(em_uso),
            "nomes": [u.nome for u in em_uso[:8]],
            # Mesma saída oferecida na desativação: excluir também trava aqui,
            # e o caminho para destravar é o mesmo (mover as pessoas antes).
            "destinos": _destinos_de_migracao(db, p.chave)})

    registrar(db, "papel_excluido", ator="rh", ator_detalhe=rh.email,
              detalhe={"papel": p.chave})
    db.delete(p)
    db.commit()
