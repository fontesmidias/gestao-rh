"""Módulo de Entrevistas — rotas do painel do RH (v2.64).

**Só o RH entrevista** (decisão do Bruno, 2026-08-04): nenhum link público,
nenhum código por e-mail, nenhuma sessão externa. Zero superfície de acesso
nova — o router inteiro é `Depends(requer_rh)`.

⚠️ **Armadilha de rotas**: as LITERAIS (`/formulario`, `/pendencias`) vêm ANTES
da paramétrica `/{entrevista_id}` — senão o FastAPI casa o literal com a
paramétrica, tenta convertê-lo em UUID e devolve 422.

Duas regras de produto que o código sustenta e que não devem ser afrouxadas:

- **O sistema pergunta, nunca conclui** (cenário 2). Entrevista cuja data
  passou e ninguém preencheu vira PENDÊNCIA que cobra — jamais `nao_veio`
  automático. Silêncio não é falta. É a mesma lição do `00:00` no import de
  ponto, onde tratar registro incompleto como falta acusaria 28 pessoas
  injustamente.
- **Nota sem justificativa não salva** (cenário 15) e ressalva sem motivo não
  salva (cenário 16) — 422 NOMEANDO o que falta.
"""
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Response, UploadFile
from pydantic import BaseModel
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.api.auth_rh import requer_rh
from app.core.db import get_db
from app.models.candidato import Candidato
from app.models.crm import Anotacao
from app.models.entrevista import (STATUS_TERMINAIS, Entrevista,
                                   StatusEntrevista, TipoEntrevista)
from app.models.talento import Talento
from app.models.usuario_rh import UsuarioRH
from app.models.vaga import Vaga
from app.services import crm, entrevistas as inst, storage
from app.services.auditoria import registrar
from app.services.lixeira import mandar_para_lixeira

router = APIRouter(tags=["entrevistas"], dependencies=[Depends(requer_rh)])

# Anexo: mesmo teto/allowlist do mini-CRM (api/crm.py) — currículo anotado,
# teste em papel fotografado (cenário 20).
ANEXO_MAX_BYTES = 10 * 1024 * 1024
ANEXO_EXTS = {"pdf", "jpg", "jpeg", "png", "heic", "webp", "doc", "docx", "txt", "xlsx"}
ANEXO_CT = {
    "pdf": "application/pdf", "jpg": "image/jpeg", "jpeg": "image/jpeg",
    "png": "image/png", "heic": "image/heic", "webp": "image/webp",
    "txt": "text/plain", "doc": "application/msword",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
}


# --------------------------------------------------------------------------
# Schemas
# --------------------------------------------------------------------------

class EntrevistaIn(BaseModel):
    talento_id: uuid.UUID | None = None
    candidato_id: uuid.UUID | None = None
    vaga_id: uuid.UUID | None = None
    tipo: str = "entrevista"
    # None = "nasceu já realizada": o RH entrevistou quem apareceu na porta.
    # Exigir agendamento prévio mataria o módulo (cenário 3).
    marcada_para: datetime | None = None
    local: str | None = None
    entrevistador_nome: str | None = None


class PreencherIn(BaseModel):
    # Triagem
    triagem: dict | None = None
    triagem_desfecho: str | None = None
    # Entrevista
    competencias: dict | None = None
    justificativas: dict | None = None
    variante: str | None = None
    recomendacao: str | None = None
    recomendacao_motivo: str | None = None
    observacao: str | None = None
    realizada_em: datetime | None = None
    local: str | None = None
    # True = fechar a avaliação (exige tudo). False/omitido = salvar rascunho.
    concluir: bool = False


class DesfechoIn(BaseModel):
    status: str                 # nao_veio | remarcada | cancelada
    motivo: str | None = None


class ArquivarIn(BaseModel):
    motivo: str | None = None


class ExcluirIn(BaseModel):
    motivo: str | None = None


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------

def _pessoa_de(db: Session, e: Entrevista) -> dict:
    """Nome e ids da pessoa entrevistada, de qualquer um dos dois lados."""
    if e.talento_id:
        t = db.get(Talento, e.talento_id)
        if t is not None:
            return {"nome": t.nome, "talento_id": t.id, "candidato_id": t.candidato_id}
    if e.candidato_id:
        c = db.get(Candidato, e.candidato_id)
        if c is not None:
            return {"nome": c.nome_completo, "talento_id": None, "candidato_id": c.id}
    return {"nome": "(pessoa removida)", "talento_id": e.talento_id,
            "candidato_id": e.candidato_id}


def _aguardando_desfecho(e: Entrevista, agora: datetime | None = None) -> bool:
    """A entrevista está cobrando um desfecho? (cenário 2)

    Passou da data marcada e continua `marcada` — ninguém disse o que houve. O
    sistema PERGUNTA; nunca conclui `nao_veio` sozinho.
    """
    if e.status != StatusEntrevista.marcada or e.marcada_para is None:
        return False
    return e.marcada_para < (agora or datetime.now(timezone.utc))


def _dump(e: Entrevista, pessoa: dict, agora: datetime | None = None) -> dict:
    return {
        "id": e.id,
        "pessoa": pessoa["nome"],
        "talento_id": pessoa["talento_id"], "candidato_id": pessoa["candidato_id"],
        "vaga_id": e.vaga_id,
        # Snapshot: se a vaga foi excluída, o título continua aqui (cenário 4).
        "vaga_titulo": e.vaga_titulo,
        "vaga_existe": e.vaga_id is not None,
        "tipo": e.tipo.value if hasattr(e.tipo, "value") else e.tipo,
        "status": e.status.value if hasattr(e.status, "value") else e.status,
        "marcada_para": e.marcada_para, "realizada_em": e.realizada_em,
        "local": e.local,
        "entrevistador": e.entrevistador_nome,
        "triagem": e.triagem, "triagem_desfecho": e.triagem_desfecho,
        "competencias": e.competencias, "justificativas": e.justificativas,
        "variante": e.variante,
        "recomendacao": e.recomendacao, "recomendacao_motivo": e.recomendacao_motivo,
        "observacao": e.observacao,
        "media": inst.media(e.competencias),
        # Carimbo da defasagem (§ 2.5) — quem preenche dias depois reconstrói.
        "defasagem_dias": inst.defasagem_dias(e.realizada_em, e.preenchida_em),
        "aguardando_desfecho": _aguardando_desfecho(e, agora),
        "tem_anexo": bool(e.anexo_key), "anexo_nome": e.anexo_nome,
        "criada_em": e.criada_em, "arquivada_em": e.arquivada_em,
    }


def _pessoas_em_lote(db: Session, linhas: list[Entrevista]) -> dict:
    """Mapa {entrevista_id: pessoa} em DUAS consultas, não N.

    Sem isto a listagem faria uma consulta por linha só para resolver o nome —
    o N+1 que o `resumo_anotacoes_por_talento` já ensinou a evitar no dash de
    Talentos (43 consultas viraram 5).
    """
    tids = {e.talento_id for e in linhas if e.talento_id}
    cids = {e.candidato_id for e in linhas if e.candidato_id}
    talentos = ({t.id: t for t in db.scalars(select(Talento).where(Talento.id.in_(tids)))}
                if tids else {})
    candidatos = ({c.id: c for c in db.scalars(select(Candidato).where(Candidato.id.in_(cids)))}
                  if cids else {})
    saida = {}
    for e in linhas:
        if e.talento_id and e.talento_id in talentos:
            t = talentos[e.talento_id]
            saida[e.id] = {"nome": t.nome, "talento_id": t.id,
                           "candidato_id": t.candidato_id}
        elif e.candidato_id and e.candidato_id in candidatos:
            c = candidatos[e.candidato_id]
            saida[e.id] = {"nome": c.nome_completo, "talento_id": None,
                           "candidato_id": c.id}
        else:
            saida[e.id] = {"nome": "(pessoa removida)", "talento_id": e.talento_id,
                           "candidato_id": e.candidato_id}
    return saida


def _exigir_pessoa(db: Session, talento_id, candidato_id) -> tuple:
    """Exatamente UMA das duas FKs, e a pessoa tem que existir."""
    if bool(talento_id) == bool(candidato_id):
        raise HTTPException(status_code=422, detail="informe_talento_ou_candidato")
    if talento_id:
        if db.get(Talento, talento_id) is None:
            raise HTTPException(status_code=404, detail="talento_nao_encontrado")
    elif db.get(Candidato, candidato_id) is None:
        raise HTTPException(status_code=404, detail="candidato_nao_encontrado")
    return talento_id, candidato_id


# --------------------------------------------------------------------------
# LITERAIS — sempre antes da paramétrica /{entrevista_id}
# --------------------------------------------------------------------------

@router.get("/rh/entrevistas/formulario")
def ver_formulario() -> dict:
    """O instrumento: 4 competências com âncoras, escala, variantes,
    recomendações e as perguntas de triagem. O front desenha as duas fichas a
    partir daqui e NÃO duplica nenhum texto. Não toca o banco."""
    return inst.formulario()


@router.get("/rh/entrevistas")
def listar(db: Session = Depends(get_db),
           vaga_id: uuid.UUID | None = None, tipo: str | None = None,
           status: str | None = None, incluir_arquivadas: bool = False) -> dict:
    """Lista + métricas para os cards do DashPlanilha.

    Arquivadas ficam FORA por padrão — é o que "sai da vista" significa
    (§ 3.1). `incluir_arquivadas=true` é o escape para quem procura.
    """
    consulta = select(Entrevista)
    if not incluir_arquivadas:
        consulta = consulta.where(Entrevista.status != StatusEntrevista.arquivada.value)
    if vaga_id:
        consulta = consulta.where(Entrevista.vaga_id == vaga_id)
    if tipo:
        consulta = consulta.where(Entrevista.tipo == tipo)
    if status:
        consulta = consulta.where(Entrevista.status == status)
    linhas = list(db.scalars(consulta.order_by(Entrevista.criada_em.desc())))

    pessoas = _pessoas_em_lote(db, linhas)
    agora = datetime.now(timezone.utc)
    itens = [_dump(e, pessoas[e.id], agora) for e in linhas]

    contagem = dict(db.execute(
        select(Entrevista.status, func.count()).group_by(Entrevista.status)).all())
    return {
        "itens": itens,
        "metricas": {
            # O card mais importante: quem está cobrando desfecho (cenário 2).
            "aguardando_desfecho": sum(1 for i in itens if i["aguardando_desfecho"]),
            "marcadas": contagem.get(StatusEntrevista.marcada.value, 0),
            "realizadas": contagem.get(StatusEntrevista.realizada.value, 0),
            "nao_compareceram": contagem.get(StatusEntrevista.nao_veio.value, 0),
            "arquivadas": contagem.get(StatusEntrevista.arquivada.value, 0),
            "total": len(itens),
        },
        "limite_anexo_mb": ANEXO_MAX_BYTES // (1024 * 1024),
    }


@router.get("/rh/entrevistas/pendencias")
def pendencias(db: Session = Depends(get_db)) -> dict:
    """Entrevistas cuja data passou e ninguém disse o que houve (cenário 2).

    **Nunca** vira `nao_veio` sozinha: o sistema pergunta, quem conclui é
    gente. Esta lista é a cobrança.
    """
    agora = datetime.now(timezone.utc)
    linhas = list(db.scalars(
        select(Entrevista).where(
            Entrevista.status == StatusEntrevista.marcada.value,
            Entrevista.marcada_para.is_not(None),
            Entrevista.marcada_para < agora,
        ).order_by(Entrevista.marcada_para)))
    pessoas = _pessoas_em_lote(db, linhas)
    return {"itens": [_dump(e, pessoas[e.id], agora) for e in linhas],
            "total": len(linhas)}


@router.get("/rh/pessoa/entrevistas")
def entrevistas_da_pessoa(db: Session = Depends(get_db),
                          talento_id: uuid.UUID | None = None,
                          candidato_id: uuid.UUID | None = None) -> dict:
    """Histórico de entrevistas da PESSOA, atravessando talento↔candidato.

    Usa `crm.escopo_pessoa` — o mesmo que faz a anotação "seguir a pessoa". É
    isto que garante o cenário 6: a entrevista feita quando ela era talento
    aparece na ficha do candidato depois do `converter()`, sem cópia. Com FK
    única, sumiria.
    """
    if talento_id is None and candidato_id is None:
        raise HTTPException(status_code=422, detail="informe_talento_ou_candidato")
    escopo = crm.escopo_pessoa(db, talento_id=talento_id, candidato_id=candidato_id)
    cond = []
    if escopo.get("talento_id"):
        cond.append(Entrevista.talento_id == escopo["talento_id"])
    if escopo.get("candidato_id"):
        cond.append(Entrevista.candidato_id == escopo["candidato_id"])
    if not cond:
        return {"itens": [], "total": 0}
    linhas = list(db.scalars(
        select(Entrevista).where(or_(*cond))
        .order_by(Entrevista.criada_em.desc())))
    pessoas = _pessoas_em_lote(db, linhas)
    agora = datetime.now(timezone.utc)
    return {"itens": [_dump(e, pessoas[e.id], agora) for e in linhas],
            "total": len(linhas)}


@router.get("/rh/vagas/{vaga_id}/entrevistas")
def entrevistas_da_vaga(vaga_id: uuid.UUID, db: Session = Depends(get_db)) -> dict:
    """Comparação: os entrevistados daquela vaga, uma linha por pessoa, com as
    4 notas lado a lado (cenários 17 e 18). É o que atende "filtrar" e
    "alocar"."""
    linhas = list(db.scalars(
        select(Entrevista).where(
            Entrevista.vaga_id == vaga_id,
            Entrevista.status != StatusEntrevista.arquivada.value,
        ).order_by(Entrevista.criada_em.desc())))
    pessoas = _pessoas_em_lote(db, linhas)
    agora = datetime.now(timezone.utc)
    return {"itens": [_dump(e, pessoas[e.id], agora) for e in linhas],
            "competencias": inst.COMPETENCIAS,
            "total": len(linhas)}


@router.post("/rh/entrevistas", status_code=201)
def criar(payload: EntrevistaIn, db: Session = Depends(get_db),
          rh: UsuarioRH = Depends(requer_rh)) -> dict:
    """Marca uma entrevista OU registra uma que já aconteceu.

    `marcada_para = None` nasce direto em `realizada`: pessoa que aparece na
    porta é rotina, e exigir agendamento prévio mataria o módulo (cenário 3).
    """
    tid, cid = _exigir_pessoa(db, payload.talento_id, payload.candidato_id)
    if payload.tipo not in {t.value for t in TipoEntrevista}:
        raise HTTPException(status_code=422, detail="tipo_invalido")

    vaga_titulo = None
    if payload.vaga_id:
        v = db.get(Vaga, payload.vaga_id)
        if v is None:
            raise HTTPException(status_code=404, detail="vaga_nao_encontrada")
        vaga_titulo = v.titulo      # snapshot desde o nascimento (cenário 4)

    ja_realizada = payload.marcada_para is None
    e = Entrevista(
        talento_id=tid, candidato_id=cid,
        vaga_id=payload.vaga_id, vaga_titulo=vaga_titulo,
        tipo=TipoEntrevista(payload.tipo),
        status=StatusEntrevista.realizada if ja_realizada else StatusEntrevista.marcada,
        marcada_para=payload.marcada_para,
        realizada_em=datetime.now(timezone.utc) if ja_realizada else None,
        local=(payload.local or "").strip() or None,
        entrevistador_id=rh.id,
        entrevistador_nome=(payload.entrevistador_nome or "").strip()
                           or rh.nome or rh.email,
        criada_por=rh.email)
    db.add(e)
    # A ação principal é validada ANTES da auditoria: `registrar()` faz flush e
    # ENGOLE exceção — um DataError aqui deixaria a sessão com rollback
    # pendente e o erro real apareceria como PendingRollbackError na próxima
    # operação, apontando para o lugar errado.
    db.flush()
    registrar(db, "entrevista_criada", ator="rh", ator_detalhe=rh.email,
              candidato_id=cid,
              detalhe={"entrevista": str(e.id), "tipo": e.tipo.value,
                       "ja_realizada": ja_realizada,
                       "vaga": vaga_titulo})
    db.commit()
    return _dump(e, _pessoa_de(db, e))


# --------------------------------------------------------------------------
# PARAMÉTRICAS
# --------------------------------------------------------------------------

@router.get("/rh/entrevistas/{entrevista_id}")
def ver(entrevista_id: uuid.UUID, db: Session = Depends(get_db)) -> dict:
    e = db.get(Entrevista, entrevista_id)
    if e is None:
        raise HTTPException(status_code=404, detail="entrevista_nao_encontrada")
    return _dump(e, _pessoa_de(db, e))


@router.put("/rh/entrevistas/{entrevista_id}")
def preencher(entrevista_id: uuid.UUID, payload: PreencherIn,
              db: Session = Depends(get_db),
              rh: UsuarioRH = Depends(requer_rh)) -> dict:
    """Preenche a ficha. Valida conforme o TIPO — são instrumentos diferentes.

    422 sempre NOMEIA o que falta: "Justifique a nota de 'Trato com público e
    postura sob pressão'" resolve; "preenchimento inválido" faz o RH procurar.
    """
    e = db.get(Entrevista, entrevista_id)
    if e is None:
        raise HTTPException(status_code=404, detail="entrevista_nao_encontrada")
    if e.status == StatusEntrevista.arquivada:
        raise HTTPException(status_code=409, detail="entrevista_arquivada")

    tipo = e.tipo.value if hasattr(e.tipo, "value") else e.tipo
    if tipo == TipoEntrevista.triagem.value:
        # Triagem NÃO tem nota, competência nem âncora — é outra coisa (§ 4.1).
        erros = inst.validar_triagem(payload.triagem, payload.triagem_desfecho)
        if erros:
            raise HTTPException(status_code=422,
                                detail={"erro": "preenchimento_invalido", "erros": erros})
        if payload.triagem is not None:
            e.triagem = payload.triagem
        if payload.triagem_desfecho is not None:
            e.triagem_desfecho = payload.triagem_desfecho
    else:
        erros = inst.validar_entrevista(
            payload.competencias, payload.justificativas,
            payload.recomendacao, payload.recomendacao_motivo)
        if erros:
            raise HTTPException(status_code=422,
                                detail={"erro": "preenchimento_invalido", "erros": erros})
        if payload.competencias is not None:
            e.competencias = payload.competencias
        if payload.justificativas is not None:
            e.justificativas = payload.justificativas
        if payload.variante is not None:
            e.variante = payload.variante
        if payload.recomendacao is not None:
            e.recomendacao = payload.recomendacao
        if payload.recomendacao_motivo is not None:
            e.recomendacao_motivo = payload.recomendacao_motivo

    if payload.observacao is not None:
        e.observacao = payload.observacao.strip() or None
    if payload.local is not None:
        e.local = payload.local.strip() or None
    if payload.realizada_em is not None:
        e.realizada_em = payload.realizada_em

    concluiu = False
    if payload.concluir:
        if tipo == TipoEntrevista.entrevista.value:
            faltando = inst.completa_entrevista(e.competencias, e.recomendacao)
            if faltando:
                raise HTTPException(
                    status_code=422,
                    detail={"erro": "entrevista_incompleta", "erros": faltando})
        elif not e.triagem_desfecho:
            raise HTTPException(
                status_code=422,
                detail={"erro": "entrevista_incompleta",
                        "erros": ["desfecho da triagem"]})
        if e.realizada_em is None:
            e.realizada_em = datetime.now(timezone.utc)
        e.status = StatusEntrevista.realizada
        concluiu = True

    # Carimbo da defasagem: marca QUANDO foi preenchida, para a tela poder
    # dizer "preenchida 3 dias depois" (§ 2.5, cenário 10).
    e.preenchida_em = datetime.now(timezone.utc)
    db.flush()

    if concluiu:
        _anotar_no_crm(db, e, rh)

    registrar(db, "entrevista_preenchida", ator="rh", ator_detalhe=rh.email,
              candidato_id=e.candidato_id,
              detalhe={"entrevista": str(e.id), "concluida": concluiu,
                       "recomendacao": e.recomendacao,
                       "triagem_desfecho": e.triagem_desfecho})
    db.commit()
    return _dump(e, _pessoa_de(db, e))


def _anotar_no_crm(db: Session, e: Entrevista, rh: UsuarioRH) -> None:
    """Ao CONCLUIR, escreve uma anotação no mini-CRM (§ 5.5).

    A entrevista **não é** uma anotação (anotação é texto livre sem estrutura;
    o valor aqui está na nota ancorada comparável) — mas ESCREVE uma, para o
    histórico da pessoa continuar num lugar só. Mesmo padrão de
    `talentos.py::mudar_status`, onde arquivar com motivo vira anotação em vez
    de ganhar campos próprios.
    """
    tipo = e.tipo.value if hasattr(e.tipo, "value") else e.tipo
    if tipo == TipoEntrevista.triagem.value:
        desfechos = {d["chave"]: d["rotulo"] for d in inst.DESFECHOS_TRIAGEM}
        resumo = desfechos.get(e.triagem_desfecho, e.triagem_desfecho or "sem desfecho")
        texto = f"Triagem realizada — {resumo}"
    else:
        rotulos = {r["chave"]: r["rotulo"] for r in inst.RECOMENDACOES}
        resumo = rotulos.get(e.recomendacao, e.recomendacao or "sem recomendação")
        m = inst.media(e.competencias)
        texto = f"Entrevista realizada — {resumo}"
        if m is not None:
            texto += f" (média {m:.2f})"
    if e.vaga_titulo:
        texto += f" · vaga: {e.vaga_titulo}"
    if e.recomendacao_motivo:
        texto += f" — {e.recomendacao_motivo}"
    db.add(Anotacao(talento_id=e.talento_id, candidato_id=e.candidato_id,
                    texto=texto, autor_id=rh.id,
                    autor_nome=rh.nome or rh.email))


@router.post("/rh/entrevistas/{entrevista_id}/desfecho")
def desfecho(entrevista_id: uuid.UUID, payload: DesfechoIn,
             db: Session = Depends(get_db),
             rh: UsuarioRH = Depends(requer_rh)) -> dict:
    """Fecha a entrevista sem preenchimento: não veio, remarcada ou cancelada.

    **Sempre um ato humano.** Nada aqui é inferido de silêncio — é justamente a
    rota que a pendência (cenário 2) cobra que alguém use.

    `remarcada` é TERMINAL e gera uma NOVA linha (cenário 19): o histórico de
    remarcações fica visível, porque remarcar 3× é informação.
    """
    e = db.get(Entrevista, entrevista_id)
    if e is None:
        raise HTTPException(status_code=404, detail="entrevista_nao_encontrada")
    permitidos = {StatusEntrevista.nao_veio.value, StatusEntrevista.remarcada.value,
                  StatusEntrevista.cancelada.value}
    if payload.status not in permitidos:
        raise HTTPException(status_code=422, detail="status_invalido")
    if e.status in (StatusEntrevista.realizada, StatusEntrevista.arquivada):
        raise HTTPException(status_code=409, detail="entrevista_ja_encerrada")

    e.status = StatusEntrevista(payload.status)
    motivo = (payload.motivo or "").strip()
    if motivo:
        e.observacao = ((e.observacao or "") + f"\n{motivo}").strip()
    db.flush()
    registrar(db, "entrevista_desfecho", ator="rh", ator_detalhe=rh.email,
              candidato_id=e.candidato_id,
              detalhe={"entrevista": str(e.id), "status": payload.status,
                       "motivo": motivo or None})
    db.commit()
    return _dump(e, _pessoa_de(db, e))


@router.post("/rh/entrevistas/{entrevista_id}/arquivar")
def arquivar(entrevista_id: uuid.UUID, payload: ArquivarIn,
             db: Session = Depends(get_db),
             rh: UsuarioRH = Depends(requer_rh)) -> dict:
    """ARQUIVA — o registro CONTINUA existindo e consultável (§ 3.1).

    Nota velha não deve assombrar quem se candidata de novo dois anos depois;
    mas reentrevistar quem faltou três vezes sem saber é desperdício. Arquivar
    resolve os dois: sai da vista e das métricas, a memória permanece.

    Se algum dia isto virar `db.delete`, é regressão — há teste por mutação.
    """
    e = db.get(Entrevista, entrevista_id)
    if e is None:
        raise HTTPException(status_code=404, detail="entrevista_nao_encontrada")
    e.status = StatusEntrevista.arquivada
    e.arquivada_em = datetime.now(timezone.utc)
    motivo = (payload.motivo or "").strip()
    db.flush()
    registrar(db, "entrevista_arquivada", ator="rh", ator_detalhe=rh.email,
              candidato_id=e.candidato_id,
              detalhe={"entrevista": str(e.id), "motivo": motivo or None})
    db.commit()
    return _dump(e, _pessoa_de(db, e))


@router.post("/rh/entrevistas/{entrevista_id}/anexo")
async def anexar(entrevista_id: uuid.UUID, arquivo: UploadFile,
                 db: Session = Depends(get_db),
                 rh: UsuarioRH = Depends(requer_rh)) -> dict:
    """Anexo: currículo anotado, teste em papel (cenário 20). Padrão do
    mini-CRM — allowlist, teto e `close()` no `finally` (o Starlette faz spool
    em disco acima de ~1MB; sem o close sobra arquivo temporário no container).
    """
    e = db.get(Entrevista, entrevista_id)
    if e is None:
        raise HTTPException(status_code=404, detail="entrevista_nao_encontrada")
    nome = arquivo.filename or ""
    ext = nome.rsplit(".", 1)[-1].lower() if "." in nome else ""
    if ext not in ANEXO_EXTS:
        raise HTTPException(status_code=422, detail="formato_nao_suportado")
    try:
        dados = await arquivo.read()
        if len(dados) > ANEXO_MAX_BYTES:
            raise HTTPException(status_code=413, detail="arquivo_grande")
        if e.anexo_key:
            try:
                storage.remover(e.anexo_key)
            except Exception:
                pass
        key = f"entrevistas/{e.id}/anexo.{ext}"
        ct = ANEXO_CT.get(ext, arquivo.content_type or "application/octet-stream")
        storage.salvar(key, dados, ct)
        e.anexo_key, e.anexo_nome, e.anexo_tipo = key, nome[:200], ct
        db.commit()
    finally:
        await arquivo.close()
    return _dump(e, _pessoa_de(db, e))


@router.get("/rh/entrevistas/{entrevista_id}/anexo")
def baixar_anexo(entrevista_id: uuid.UUID, db: Session = Depends(get_db)) -> Response:
    e = db.get(Entrevista, entrevista_id)
    if e is None or not e.anexo_key:
        raise HTTPException(status_code=404, detail="anexo_nao_encontrado")
    dados = storage.ler(e.anexo_key)
    return Response(content=dados,
                    media_type=e.anexo_tipo or "application/octet-stream",
                    headers={"Content-Disposition":
                             f'inline; filename="{e.anexo_nome or "anexo"}"'})


@router.delete("/rh/entrevistas/{entrevista_id}", status_code=204)
def excluir(entrevista_id: uuid.UUID, db: Session = Depends(get_db),
            rh: UsuarioRH = Depends(requer_rh)) -> Response:
    """Exclusão real passa pela LIXEIRA (regra da casa: toda exclusão do RH
    passa por lá, com retenção configurável). Diferente de ARQUIVAR, que é o
    fim natural pelo prazo e não tira o registro da base."""
    e = db.get(Entrevista, entrevista_id)
    if e is None:
        raise HTTPException(status_code=404, detail="entrevista_nao_encontrada")
    pessoa = _pessoa_de(db, e)
    tipo = e.tipo.value if hasattr(e.tipo, "value") else e.tipo
    mandar_para_lixeira(db, e, "entrevista",
                        f"{tipo} — {pessoa['nome']}", rh.email)
    if e.anexo_key:
        try:
            storage.remover(e.anexo_key)
        except Exception:
            pass
    db.delete(e)
    registrar(db, "entrevista_excluida", ator="rh", ator_detalhe=rh.email,
              detalhe={"entrevista": str(entrevista_id), "pessoa": pessoa["nome"]})
    db.commit()
    return Response(status_code=204)
