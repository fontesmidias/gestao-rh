"""Catálogo de roteiros de entrevista — rotas do painel do RH (v2.66, § 14.1).

Router inteiro sob `Depends(requer_rh)`: só o RH entrevista (decisão 1), e só o
RH cadastra o que se pergunta.

⚠️ **Armadilha de rotas**: as LITERAIS vêm ANTES da paramétrica `/{roteiro_id}`
— senão o FastAPI casa o literal com a paramétrica, tenta convertê-lo em UUID e
devolve 422. Já mordeu em `provas-aplicacoes` e em `/rh/crm/tags`.

Três regras de produto que este arquivo sustenta e que não devem ser
afrouxadas:

- **Rascunho não se usa** (cenário 22). É a trava que sustenta o argumento
  jurídico do § 6: a defesa perante a Lei 9.029/95 não é "existe um roteiro", é
  **"o roteiro foi aprovado ANTES de ser usado"**. Publicar é ato separado, com
  autor e data na auditoria.
- **Editar publicado cria a versão SEGUINTE** (cenário 21) e volta a rascunho:
  a entrevista já feita continua com o snapshot dela. Editar publicado no lugar
  reescreveria, retroativamente, o instrumento com que alguém foi avaliado.
- **O roteiro `padrao` não se apaga** (cenário 25) e não se arquiva sem outro no
  lugar: ele é o fundo da herança. Sem ele, cargo sem roteiro específico abriria
  a ficha sem instrumento nenhum.
"""
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.auth_rh import exige, requer_rh
from app.core.db import get_db
from app.models.entrevista import Entrevista
from app.models.roteiro_entrevista import (SENIORIDADES, RoteiroEntrevista,
                                           StatusRoteiro, TipoRoteiro)
from app.models.usuario_rh import UsuarioRH
from app.services import entrevistas as inst
from app.services.auditoria import registrar
from app.services.export_tirvu import normalizar_cargo

router = APIRouter(tags=["roteiros-entrevista"], dependencies=[Depends(requer_rh)])


class RoteiroIn(BaseModel):
    nome: str | None = None
    cargo: str | None = None
    senioridade: str | None = None
    competencias: list | None = None
    # v2.67 (§ 15.5 item 3): `entrevista` (padrão) ou `triagem`. A triagem usa
    # `perguntas` e continua SEM nota, competência ou âncora.
    tipo: str | None = None
    perguntas: list | None = None


class ArquivarRoteiroIn(BaseModel):
    motivo: str | None = None


def _tipo_ou_422(valor: str | None) -> str:
    """`entrevista` | `triagem`, com o padrão em `entrevista` (v2.67)."""
    v = (valor or "").strip().lower() or TipoRoteiro.entrevista.value
    if v not in {t.value for t in TipoRoteiro}:
        raise HTTPException(status_code=422, detail={
            "erro": "tipo_invalido",
            "erros": [f"Tipo '{valor}': use entrevista ou triagem."]})
    return v


def _validar_por_tipo(tipo: str, nome, competencias, perguntas) -> list[str]:
    """Cada natureza tem a sua validação — e é isso que impede a triagem
    editável de virar avaliação (§ 4.1)."""
    if tipo == TipoRoteiro.triagem.value:
        return inst.validar_roteiro_triagem(nome, perguntas)
    return inst.validar_roteiro(nome, competencias)


def _senioridade_ou_422(valor: str | None) -> str | None:
    """Senioridade é lista FIXA de propósito: texto livre viraria
    'pleno'/'Pleno'/'plena' e a herança pararia de casar em silêncio — o pior
    dos defeitos, porque o roteiro certo simplesmente não seria escolhido e
    ninguém veria erro nenhum."""
    v = (valor or "").strip().lower() or None
    if v is not None and v not in SENIORIDADES:
        raise HTTPException(
            status_code=422,
            detail={"erro": "senioridade_invalida",
                    "erros": [f"Senioridade '{valor}': use "
                              f"{', '.join(SENIORIDADES)} ou deixe em branco "
                              "(vale para todas)."]})
    return v


# --------------------------------------------------------------------------
# LITERAIS — sempre antes da paramétrica /{roteiro_id}
# --------------------------------------------------------------------------

@router.get("/rh/roteiros-entrevista")
def listar(db: Session = Depends(get_db),
           incluir_arquivados: bool = False,
           tipo: str | None = None,
    _rh: UsuarioRH = Depends(exige("selecao:entrevistar"))) -> dict:
    """Lista + métricas para os cards. Arquivados ficam fora por padrão.

    **Filtra por TIPO, com `entrevista` como padrão** (v2.67). Não é preferência
    de tela: cada natureza tem o SEU roteiro-raiz (`padrao=True`), porque cada
    uma tem a sua herança — a entrevista cai no roteiro padrão de competências,
    a triagem no de perguntas. Listar as duas juntas mostraria **dois** padrões
    na mesma tela, e "qual é o padrão?" deixaria de ter resposta única. A
    invariante que vale é *um padrão por tipo*.
    """
    tipo_filtro = _tipo_ou_422(tipo) if tipo else TipoRoteiro.entrevista.value
    consulta = select(RoteiroEntrevista).where(
        RoteiroEntrevista.tipo == tipo_filtro)
    if not incluir_arquivados:
        consulta = consulta.where(
            RoteiroEntrevista.status != StatusRoteiro.arquivado.value)
    linhas = list(db.scalars(consulta.order_by(
        RoteiroEntrevista.padrao.desc(), RoteiroEntrevista.nome)))

    # Quantas entrevistas cada roteiro já sustentou — em UMA consulta, não uma
    # por linha (o N+1 que o dash de Talentos já ensinou a evitar). O número
    # importa porque é o que diz ao RH que arquivar aquele roteiro tem história
    # atrás.
    usos = dict(db.execute(
        select(Entrevista.roteiro_id, func.count())
        .where(Entrevista.roteiro_id.is_not(None))
        .group_by(Entrevista.roteiro_id)).all())

    itens = []
    for r in linhas:
        d = inst.dump_roteiro(r)
        d["entrevistas"] = usos.get(r.id, 0)
        itens.append(d)

    # As métricas contam o MESMO recorte da lista — cards que somam os dois
    # tipos diriam "3 publicados" numa tela que mostra 2.
    contagem = dict(db.execute(
        select(RoteiroEntrevista.status, func.count())
        .where(RoteiroEntrevista.tipo == tipo_filtro)
        .group_by(RoteiroEntrevista.status)).all())
    return {
        "itens": itens,
        "tipo": tipo_filtro,
        "senioridades": SENIORIDADES,
        "metricas": {
            "publicados": contagem.get(StatusRoteiro.publicado.value, 0),
            "rascunhos": contagem.get(StatusRoteiro.rascunho.value, 0),
            "arquivados": contagem.get(StatusRoteiro.arquivado.value, 0),
            "total": len(itens),
        },
    }


@router.post("/rh/roteiros-entrevista", status_code=201)
def criar(payload: RoteiroIn, db: Session = Depends(get_db),
          rh: UsuarioRH = Depends(exige("selecao:entrevistar"))) -> dict:
    """Cria um roteiro. Nasce **rascunho**, sempre — e rascunho não se usa."""
    tipo = _tipo_ou_422(payload.tipo)
    erros = _validar_por_tipo(tipo, payload.nome, payload.competencias,
                              payload.perguntas)
    if erros:
        raise HTTPException(status_code=422,
                            detail={"erro": "roteiro_invalido", "erros": erros})
    sen = _senioridade_ou_422(payload.senioridade)
    cargo = (payload.cargo or "").strip() or None
    e_triagem = tipo == TipoRoteiro.triagem.value
    r = RoteiroEntrevista(
        nome=payload.nome.strip()[:120], cargo=cargo,
        cargo_norm=normalizar_cargo(cargo) if cargo else None,
        senioridade=sen, tipo=tipo,
        status=StatusRoteiro.rascunho.value, versao=1,
        # Cada natureza grava no SEU campo, e o outro fica nulo. Guardar
        # competência num roteiro de triagem deixaria a âncora latente ali,
        # esperando alguém "aproveitar".
        competencias=(None if e_triagem
                      else inst.normalizar_competencias(payload.competencias)),
        perguntas=(inst.normalizar_perguntas(payload.perguntas)
                   if e_triagem else None),
        padrao=False, criado_por=rh.email)
    db.add(r)
    # A ação principal é validada ANTES da auditoria: `registrar()` faz flush e
    # ENGOLE exceção — um erro aqui deixaria a sessão com rollback pendente e o
    # defeito real apareceria como PendingRollbackError na operação seguinte.
    db.flush()
    registrar(db, "roteiro_entrevista_criado", ator="rh", ator_detalhe=rh.email,
              detalhe={"roteiro": str(r.id), "nome": r.nome, "cargo": r.cargo})
    db.commit()
    return inst.dump_roteiro(r)


# --------------------------------------------------------------------------
# PARAMÉTRICAS
# --------------------------------------------------------------------------

@router.get("/rh/roteiros-entrevista/{roteiro_id}")
def ver(roteiro_id: uuid.UUID, db: Session = Depends(get_db),
    _rh: UsuarioRH = Depends(exige("selecao:entrevistar"))) -> dict:
    r = db.get(RoteiroEntrevista, roteiro_id)
    if r is None:
        raise HTTPException(status_code=404, detail="roteiro_nao_encontrado")
    return inst.dump_roteiro(r)


@router.get("/rh/roteiros-entrevista/{roteiro_id}/documento")
def documento_do_roteiro(roteiro_id: uuid.UUID, db: Session = Depends(get_db),
                         rh: UsuarioRH = Depends(exige("selecao:entrevistar"))) -> Response:
    """O roteiro publicado em PDF (§ 15.2) — a peça que se anexa a uma defesa.

    **Rascunho não gera documento** (cenário 33), e arquivado também não: um PDF
    timbrado dizendo "roteiro de entrevista" sem o ato de aprovação datado é
    exatamente o oposto do que o § 6 precisa provar — pareceria documento
    aprovado sem ter sido. O 409 diz o motivo, para o RH saber que falta
    publicar.
    """
    from app.services import entrevista_pdf as epdf
    from app.services.export_planilha import slug

    r = db.get(RoteiroEntrevista, roteiro_id)
    if r is None:
        raise HTTPException(status_code=404, detail="roteiro_nao_encontrado")
    if r.status != StatusRoteiro.publicado.value:
        raise HTTPException(status_code=409, detail={
            "erro": "roteiro_nao_publicado",
            "mensagem": "Só roteiro PUBLICADO vira documento. O documento serve "
                        "para provar que o roteiro foi aprovado antes de ser "
                        "usado — um rascunho não prova isso."})
    pdf = epdf.gerar_roteiro(db, r)
    registrar(db, "roteiro_entrevista_documento", ator="rh", ator_detalhe=rh.email,
              detalhe={"roteiro": str(r.id), "versao": r.versao})
    db.commit()
    nome = slug(f"roteiro-{r.nome}-v{r.versao}", fallback="roteiro")
    return Response(content=pdf, media_type="application/pdf",
                    headers={"Content-Disposition": f'inline; filename="{nome}.pdf"'})


@router.put("/rh/roteiros-entrevista/{roteiro_id}")
def editar(roteiro_id: uuid.UUID, payload: RoteiroIn,
           db: Session = Depends(get_db),
           rh: UsuarioRH = Depends(exige("selecao:entrevistar"))) -> dict:
    """Edita o roteiro.

    **Publicado volta a RASCUNHO e ganha a versão seguinte** (cenário 21). Não é
    burocracia: enquanto está sendo reescrito, ele não pode ser escolhido em
    entrevista nova — senão metade das entrevistas do dia usaria um instrumento
    a meio caminho, e nenhuma delas teria sido aprovada antes do uso.

    A entrevista já feita **não muda**: ela guarda `roteiro_snapshot`.
    """
    r = db.get(RoteiroEntrevista, roteiro_id)
    if r is None:
        raise HTTPException(status_code=404, detail="roteiro_nao_encontrado")
    if r.status == StatusRoteiro.arquivado.value:
        raise HTTPException(status_code=409, detail="roteiro_arquivado")

    nome = payload.nome if payload.nome is not None else r.nome
    comps = payload.competencias if payload.competencias is not None else r.competencias
    perg = payload.perguntas if payload.perguntas is not None else r.perguntas
    # O TIPO não se troca por edição: um roteiro de triagem que virasse de
    # entrevista carregaria as respostas já gravadas para dentro de uma ficha com
    # nota. Quem quer a outra natureza cria outro roteiro.
    tipo = getattr(r, "tipo", None) or TipoRoteiro.entrevista.value
    if payload.tipo is not None and _tipo_ou_422(payload.tipo) != tipo:
        raise HTTPException(status_code=422, detail={
            "erro": "tipo_imutavel",
            "erros": ["O tipo do roteiro não muda depois de criado — crie um "
                      "roteiro novo com a outra natureza."]})
    erros = _validar_por_tipo(tipo, nome, comps, perg)
    if erros:
        raise HTTPException(status_code=422,
                            detail={"erro": "roteiro_invalido", "erros": erros})

    era_publicado = r.status == StatusRoteiro.publicado.value
    if payload.nome is not None:
        r.nome = payload.nome.strip()[:120]
    if payload.competencias is not None and tipo != TipoRoteiro.triagem.value:
        r.competencias = inst.normalizar_competencias(payload.competencias)
    if payload.perguntas is not None and tipo == TipoRoteiro.triagem.value:
        r.perguntas = inst.normalizar_perguntas(payload.perguntas)
    if payload.cargo is not None:
        # O roteiro PADRÃO não tem cargo — ele é o fundo da herança. Deixar
        # alguém amarrá-lo a um cargo tiraria o piso do sistema sem aviso.
        if r.padrao and (payload.cargo or "").strip():
            raise HTTPException(
                status_code=422,
                detail={"erro": "padrao_sem_cargo",
                        "erros": ["O roteiro padrão vale para os cargos que não "
                                  "têm roteiro próprio — por isso ele não tem "
                                  "cargo. Duplique-o para criar um de cargo."]})
        cargo = (payload.cargo or "").strip() or None
        r.cargo = cargo
        r.cargo_norm = normalizar_cargo(cargo) if cargo else None
    if payload.senioridade is not None:
        r.senioridade = _senioridade_ou_422(payload.senioridade)

    if era_publicado:
        r.status = StatusRoteiro.rascunho.value
        r.versao = (r.versao or 1) + 1
        r.publicado_em, r.publicado_por = None, None
    db.flush()
    registrar(db, "roteiro_entrevista_editado", ator="rh", ator_detalhe=rh.email,
              detalhe={"roteiro": str(r.id), "versao": r.versao,
                       "voltou_a_rascunho": era_publicado})
    db.commit()
    return inst.dump_roteiro(r)


@router.post("/rh/roteiros-entrevista/{roteiro_id}/publicar")
def publicar(roteiro_id: uuid.UUID, db: Session = Depends(get_db),
             rh: UsuarioRH = Depends(exige("selecao:entrevistar"))) -> dict:
    """O ATO de aprovação — o que a defesa jurídica invoca.

    Fica na auditoria com quem publicou e quando. É por existir este ato
    separado que se pode dizer "o roteiro foi aprovado ANTES de ser usado";
    publicar junto com salvar apagaria a diferença entre rascunhar e aprovar.
    """
    r = db.get(RoteiroEntrevista, roteiro_id)
    if r is None:
        raise HTTPException(status_code=404, detail="roteiro_nao_encontrado")
    if r.status == StatusRoteiro.arquivado.value:
        raise HTTPException(status_code=409, detail="roteiro_arquivado")
    erros = _validar_por_tipo(getattr(r, "tipo", None) or TipoRoteiro.entrevista.value,
                              r.nome, r.competencias, r.perguntas)
    if erros:
        # Publicar é o que autoriza o uso: aqui a exigência é INTEIRA. Rascunho
        # pela metade se salva (para não perder o texto no meio da digitação);
        # publicado pela metade, não.
        raise HTTPException(status_code=422,
                            detail={"erro": "roteiro_invalido", "erros": erros})

    r.status = StatusRoteiro.publicado.value
    r.publicado_em = datetime.now(timezone.utc)
    r.publicado_por = rh.email
    db.flush()
    registrar(db, "roteiro_entrevista_publicado", ator="rh", ator_detalhe=rh.email,
              detalhe={"roteiro": str(r.id), "nome": r.nome, "versao": r.versao,
                       "cargo": r.cargo, "senioridade": r.senioridade})
    db.commit()
    return inst.dump_roteiro(r)


@router.post("/rh/roteiros-entrevista/{roteiro_id}/duplicar", status_code=201)
def duplicar(roteiro_id: uuid.UUID, db: Session = Depends(get_db),
             rh: UsuarioRH = Depends(exige("selecao:entrevistar"))) -> dict:
    """Cópia em rascunho — o caminho normal para criar um roteiro de cargo a
    partir do padrão, em vez de digitar quatro âncoras do zero."""
    r = db.get(RoteiroEntrevista, roteiro_id)
    if r is None:
        raise HTTPException(status_code=404, detail="roteiro_nao_encontrado")
    novo = RoteiroEntrevista(
        nome=f"{r.nome} (cópia)"[:120],
        cargo=r.cargo, cargo_norm=r.cargo_norm, senioridade=r.senioridade,
        tipo=getattr(r, "tipo", None) or TipoRoteiro.entrevista.value,
        status=StatusRoteiro.rascunho.value, versao=1,
        competencias=inst.normalizar_competencias(r.competencias),
        perguntas=inst.normalizar_perguntas(r.perguntas),
        # A cópia NUNCA nasce padrão: haveria dois fundos de herança e a
        # resolução escolheria um deles por ordem de versão, em silêncio.
        padrao=False, criado_por=rh.email)
    db.add(novo)
    db.flush()
    registrar(db, "roteiro_entrevista_duplicado", ator="rh", ator_detalhe=rh.email,
              detalhe={"roteiro": str(novo.id), "de": str(r.id)})
    db.commit()
    return inst.dump_roteiro(novo)


@router.post("/rh/roteiros-entrevista/{roteiro_id}/arquivar")
def arquivar(roteiro_id: uuid.UUID, payload: ArquivarRoteiroIn,
             db: Session = Depends(get_db),
             rh: UsuarioRH = Depends(exige("selecao:entrevistar"))) -> dict:
    """Aposenta o roteiro. As entrevistas antigas seguem legíveis pelo snapshot
    (cenário 24) — arquivar o roteiro não apaga o instrumento de ninguém.

    **O padrão não se arquiva** (cenário 25): ele é o fundo da herança. Sem ele,
    um cargo sem roteiro próprio abriria a ficha sem instrumento — e o módulo se
    recusaria a funcionar por causa de um cadastro que ninguém fez.
    """
    r = db.get(RoteiroEntrevista, roteiro_id)
    if r is None:
        raise HTTPException(status_code=404, detail="roteiro_nao_encontrado")
    if r.padrao:
        raise HTTPException(
            status_code=409,
            detail={"erro": "roteiro_padrao",
                    "erros": ["Este é o roteiro padrão: ele é usado sempre que "
                              "o cargo não tem roteiro próprio. Eleja outro "
                              "como padrão antes de arquivar este."]})
    r.status = StatusRoteiro.arquivado.value
    r.arquivado_em = datetime.now(timezone.utc)
    db.flush()
    registrar(db, "roteiro_entrevista_arquivado", ator="rh", ator_detalhe=rh.email,
              detalhe={"roteiro": str(r.id),
                       "motivo": (payload.motivo or "").strip() or None})
    db.commit()
    return inst.dump_roteiro(r)


@router.post("/rh/roteiros-entrevista/{roteiro_id}/tornar-padrao")
def tornar_padrao(roteiro_id: uuid.UUID, db: Session = Depends(get_db),
                  rh: UsuarioRH = Depends(exige("selecao:entrevistar"))) -> dict:
    """Elege este como o fundo da herança, e tira a marca do anterior.

    Existe para que "o padrão não se apaga" não vire "o padrão não se troca". O
    roteiro precisa estar PUBLICADO: um rascunho como piso da herança deixaria
    toda entrevista de cargo sem roteiro caindo num instrumento não aprovado —
    exatamente o que a trava de publicação existe para impedir.
    """
    r = db.get(RoteiroEntrevista, roteiro_id)
    if r is None:
        raise HTTPException(status_code=404, detail="roteiro_nao_encontrado")
    if r.status != StatusRoteiro.publicado.value:
        raise HTTPException(
            status_code=409,
            detail={"erro": "roteiro_nao_publicado",
                    "erros": ["Publique o roteiro antes de torná-lo padrão — o "
                              "padrão é usado sem escolha do RH, então ele "
                              "precisa ter passado pela aprovação."]})
    # **Só desmarca o padrão DO MESMO TIPO** (v2.67). Sem o recorte, eleger um
    # roteiro de entrevista tiraria a marca do padrão de TRIAGEM — e a triagem
    # ficaria sem fundo de herança, abrindo sem pergunta nenhuma. Cada natureza
    # tem o seu piso; são heranças independentes.
    tipo_dele = getattr(r, "tipo", None) or TipoRoteiro.entrevista.value
    anteriores = list(db.scalars(
        select(RoteiroEntrevista).where(RoteiroEntrevista.padrao.is_(True),
                                        RoteiroEntrevista.tipo == tipo_dele)))
    for a in anteriores:
        if a.id != r.id:
            a.padrao = False
    r.padrao, r.cargo, r.cargo_norm, r.senioridade = True, None, None, None
    db.flush()
    registrar(db, "roteiro_entrevista_padrao", ator="rh", ator_detalhe=rh.email,
              detalhe={"roteiro": str(r.id),
                       "anteriores": [str(a.id) for a in anteriores if a.id != r.id]})
    db.commit()
    return inst.dump_roteiro(r)


@router.delete("/rh/roteiros-entrevista/{roteiro_id}", status_code=204)
def excluir(roteiro_id: uuid.UUID, db: Session = Depends(get_db),
            rh: UsuarioRH = Depends(exige("selecao:entrevistar"))) -> Response:
    """Exclui um roteiro que nunca foi usado. Passa pela LIXEIRA (regra da casa).

    **O padrão nunca** (cenário 25). E roteiro que já sustentou entrevista
    também não: apagá-lo deixaria `roteiro_id` nulo em registros que dependem
    dele para se explicar. O caminho para aposentar é ARQUIVAR.
    """
    from app.services.lixeira import mandar_para_lixeira

    r = db.get(RoteiroEntrevista, roteiro_id)
    if r is None:
        raise HTTPException(status_code=404, detail="roteiro_nao_encontrado")
    if r.padrao:
        raise HTTPException(
            status_code=409,
            detail={"erro": "roteiro_padrao",
                    "erros": ["O roteiro padrão não se apaga — ele é o fundo da "
                              "herança de cargo."]})
    usos = db.scalar(select(func.count()).select_from(Entrevista)
                     .where(Entrevista.roteiro_id == r.id)) or 0
    if usos:
        raise HTTPException(
            status_code=409,
            detail={"erro": "roteiro_em_uso",
                    "erros": [f"Este roteiro já foi usado em {usos} entrevista(s). "
                              "Arquive-o em vez de excluir — as entrevistas "
                              "continuam legíveis, e o histórico não se apaga."]})
    mandar_para_lixeira(db, r, "roteiro_entrevista", r.nome, rh.email)
    db.delete(r)
    registrar(db, "roteiro_entrevista_excluido", ator="rh", ator_detalhe=rh.email,
              detalhe={"roteiro": str(roteiro_id), "nome": r.nome})
    db.commit()
    return Response(status_code=204)
