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
import hashlib
import uuid
from datetime import datetime, timezone

from fastapi import (APIRouter, Depends, HTTPException, Request, Response,
                     UploadFile)
from pydantic import BaseModel
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.api.auth_rh import exige, requer_rh
from app.core.config import ip_do_cliente
from app.core.db import get_db
from app.models.assinatura_entrevista import AssinaturaEntrevista
from app.models.candidato import Candidato, PostoServico
from app.models.crm import Anotacao, PessoaTag, Tag
from app.models.entrevista import (STATUS_TERMINAIS, Entrevista,
                                   StatusEntrevista, TipoEntrevista)
from app.models.talento import Talento
from app.models.usuario_rh import UsuarioRH
from app.models.vaga import Vaga
from app.services import (crm, entrevista_convite as convite,
                          entrevistas as inst, storage)
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
    # --- v2.66 ---
    modalidade: str | None = None          # presencial | online
    link_reuniao: str | None = None
    # --- v2.67 ---
    # Duração do compromisso, em minutos (§ 15.5 item 4). Alimenta o `DTEND` do
    # `.ics`. Zero/negativo é recusado com 422 (cenário 37).
    duracao_min: int | None = None
    # Roteiro escolhido na hora. None = o sistema resolve por herança
    # (cargo+senioridade → cargo → padrão). Sugerido, nunca imposto.
    roteiro_id: uuid.UUID | None = None
    # Cargo: dica para a herança do roteiro E, desde a v2.74, dado GRAVADO —
    # quando não há vaga cadastrada, é ele que diz para que a conversa foi.
    cargo: str | None = None
    senioridade: str | None = None
    # Posto sem vaga (v2.74): o RH conversa para um posto que precisa repor
    # gente, e cadastrar uma vaga só para marcar a conversa é burocracia
    # inventada. Alternativa ao `vaga_id`, nunca substituto.
    posto_id: uuid.UUID | None = None
    # O RH decide se o convite sai. Sem e-mail da pessoa, não sai — e a
    # resposta diz POR QUÊ (cenário 26), nunca falha calada.
    enviar_convite: bool = False


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
    # --- v2.66: remarcar pela própria ficha ---
    marcada_para: datetime | None = None
    modalidade: str | None = None
    link_reuniao: str | None = None
    duracao_min: int | None = None
    reenviar_convite: bool = False
    # True = fechar a avaliação (exige tudo). False/omitido = salvar rascunho.
    concluir: bool = False


class DesfechoIn(BaseModel):
    status: str                 # nao_veio | remarcada | cancelada
    motivo: str | None = None
    # Cancelar/remarcar com convite já enviado avisa a pessoa e manda o
    # cancelamento de calendário — senão o compromisso fica na agenda dela
    # depois de cancelado, e ela vem (cenário 28).
    avisar_pessoa: bool = True


class ArquivarIn(BaseModel):
    motivo: str | None = None


class ExcluirIn(BaseModel):
    motivo: str | None = None


class PessoaRef(BaseModel):
    talento_id: uuid.UUID | None = None
    candidato_id: uuid.UUID | None = None


class ReaproveitarIn(BaseModel):
    """Tag de reaproveitamento em lote (§ 14.3). A tag vem do RH — o sistema
    SUGERE a partir do cargo da vaga, mas quem confirma é ele."""
    tag: str
    pessoas: list[PessoaRef] = []
    vaga_titulo: str | None = None


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------

def _pessoa_de(db: Session, e: Entrevista) -> dict:
    """Nome, e-mail e ids da pessoa entrevistada, de qualquer um dos dois lados.

    O e-mail entra aqui (v2.66) porque é ele que decide se o convite e o
    lembrete podem sair — e a tela precisa dizer o MOTIVO quando não podem
    (cenário 26), em vez de mostrar um interruptor que não faz nada.
    """
    if e.talento_id:
        t = db.get(Talento, e.talento_id)
        if t is not None:
            return {"nome": t.nome, "email": t.email,
                    "talento_id": t.id, "candidato_id": t.candidato_id}
    if e.candidato_id:
        c = db.get(Candidato, e.candidato_id)
        if c is not None:
            return {"nome": c.nome_completo, "email": c.email,
                    "talento_id": None, "candidato_id": c.id}
    return {"nome": "(pessoa removida)", "email": None,
            "talento_id": e.talento_id, "candidato_id": e.candidato_id}


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
        # v2.74: para a entrevista SEM vaga cadastrada. `posto_nome` é snapshot,
        # então continua legível mesmo depois de o posto ir para a lixeira.
        "cargo": e.cargo, "posto_id": e.posto_id, "posto_nome": e.posto_nome,
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
        # --- v2.66 ---
        "modalidade": e.modalidade, "link_reuniao": e.link_reuniao,
        "duracao_min": e.duracao_min or convite.DURACAO_MIN,
        "convite_enviado_em": e.convite_enviado_em,
        "lembrete_enviado_em": e.lembrete_enviado_em,
        "sequencia_convite": e.sequencia_convite or 0,
        # POR QUE o convite/lembrete não pode sair — a tela mostra este texto ao
        # lado do interruptor. "Desligado" sem motivo faria o RH tentar de novo
        # achando que foi falha de rede (cenário 26).
        "motivo_sem_lembrete": convite.motivo_sem_envio(
            pessoa.get("email"), e.marcada_para),
        "roteiro_id": e.roteiro_id,
        # O instrumento COM QUE A ENTREVISTA FOI FEITA. Vem do snapshot, nunca
        # do roteiro vivo: editar o roteiro depois não pode reescrever o que a
        # nota significava (cenários 21 e 24).
        "roteiro_nome": (e.roteiro_snapshot or {}).get("nome"),
        "roteiro_versao": (e.roteiro_snapshot or {}).get("versao"),
        "roteiro_competencias": inst.normalizar_competencias(
            (e.roteiro_snapshot or {}).get("competencias")) or None,
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
            saida[e.id] = {"nome": t.nome, "email": t.email, "talento_id": t.id,
                           "candidato_id": t.candidato_id}
        elif e.candidato_id and e.candidato_id in candidatos:
            c = candidatos[e.candidato_id]
            saida[e.id] = {"nome": c.nome_completo, "email": c.email,
                           "talento_id": None, "candidato_id": c.id}
        else:
            saida[e.id] = {"nome": "(pessoa removida)", "email": None,
                           "talento_id": e.talento_id,
                           "candidato_id": e.candidato_id}
    return saida


def _exigir_duracao(valor: int | None) -> int | None:
    """Duração válida, ou 422 que explica (cenário 37).

    Zero ou negativo produziria `DTEND` anterior (ou igual) ao `DTSTART`: o
    cliente de agenda descarta o evento ou desenha uma faixa vazia, e a pessoa
    simplesmente não vê a entrevista. O `gerar_ics` tem `max(1, ...)` como rede,
    mas rede não é validação — ela ESCONDERIA o erro de digitação em vez de
    dizer ao RH que ele digitou 0.

    O teto de 24h existe pelo mesmo motivo, na outra ponta: `duracao_min=100000`
    ocuparia dez semanas da agenda de alguém.
    """
    if valor is None:
        return None
    if valor <= 0:
        raise HTTPException(status_code=422, detail={
            "erro": "duracao_invalida",
            "mensagem": "A duração precisa ser de pelo menos 1 minuto — com "
                        "zero, o convite chega com fim antes do começo e o "
                        "calendário da pessoa o descarta."})
    if valor > 24 * 60:
        raise HTTPException(status_code=422, detail={
            "erro": "duracao_invalida",
            "mensagem": "A duração não pode passar de 24 horas."})
    return valor


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
def ver_formulario(db: Session = Depends(get_db),
                   roteiro_id: uuid.UUID | None = None,
                   cargo: str | None = None,
                   senioridade: str | None = None,
    _rh: UsuarioRH = Depends(exige("selecao:entrevistar"))) -> dict:
    """O instrumento: competências com âncoras, escala, variantes, recomendações
    e as perguntas de triagem. O front desenha as duas fichas a partir daqui e
    **NÃO duplica nenhum texto** (`test_entrevistas.py` varre o JSX e reprova).

    **O CONTRATO não mudou na v2.66 — a FONTE mudou.** Até a v2.65 isto devolvia
    uma constante de módulo; agora resolve o ROTEIRO no banco por herança
    (`roteiro_id` explícito → cargo+senioridade → cargo → padrão) e devolve as
    competências dele. O front continua lendo daqui e continua não sabendo nada
    do texto.

    Cargo sem roteiro **cai no padrão, nunca em erro** (cenário 23), e roteiro
    em rascunho **não é servido** (cenário 22) — `resolver_roteiro` só considera
    publicado.
    """
    r = inst.resolver_roteiro(db, cargo=cargo, senioridade=senioridade,
                              roteiro_id=roteiro_id)
    saida = inst.formulario(r.competencias if r is not None else None)
    saida["roteiro"] = ({"id": r.id, "nome": r.nome, "versao": r.versao,
                         "cargo": r.cargo, "senioridade": r.senioridade,
                         "padrao": r.padrao} if r is not None else None)
    # Se o `roteiro_id` pedido não foi o servido, quem pediu escolheu um
    # rascunho ou um arquivado. Dizer isso evita a tela mostrar um instrumento
    # e o RH acreditar que é outro — nada é filtrado em silêncio.
    if roteiro_id and (r is None or r.id != roteiro_id):
        saida["aviso_roteiro"] = (
            "O roteiro escolhido não está publicado (ou não existe mais). "
            "A ficha está usando o roteiro resolvido pelo cargo.")
    return saida


@router.get("/rh/entrevistas/modalidades")
def ver_modalidades(
    _rh: UsuarioRH = Depends(exige("selecao:entrevistar"))) -> dict:
    """Modalidades e qual campo cada uma exige — o front não duplica o rótulo."""
    return {"itens": inst.MODALIDADES}


@router.get("/rh/entrevistas")
def listar(db: Session = Depends(get_db),
           vaga_id: uuid.UUID | None = None, tipo: str | None = None,
           status: str | None = None, incluir_arquivadas: bool = False,
    _rh: UsuarioRH = Depends(exige("selecao:entrevistar"))) -> dict:
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
def pendencias(db: Session = Depends(get_db),
    _rh: UsuarioRH = Depends(exige("selecao:entrevistar"))) -> dict:
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
                          candidato_id: uuid.UUID | None = None,
    _rh: UsuarioRH = Depends(exige("selecao:entrevistar"))) -> dict:
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
def entrevistas_da_vaga(vaga_id: uuid.UUID, db: Session = Depends(get_db),
    _rh: UsuarioRH = Depends(exige("selecao:escrever"))) -> dict:
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


@router.get("/rh/vagas/{vaga_id}/entrevistados")
def entrevistados_para_reaproveitar(vaga_id: uuid.UUID,
                                    db: Session = Depends(get_db),
    _rh: UsuarioRH = Depends(exige("selecao:escrever"))) -> dict:
    """Quem foi entrevistado para esta vaga — a PRÉVIA do reaproveitamento
    (§ 14.3, cenário 30).

    O Bruno resolveu o cenário 4 melhor do que a sala tinha resolvido: a
    entrevista já sobrevivia à exclusão da vaga (com `vaga_titulo`), mas isso
    preservava **o registro**; o que ele quer é preservar **a pessoa como
    oportunidade**:

    > *"quando excluir uma vaga, a entrevista sobrevive, pois posso poder
    > taguear a pessoa, de modo que ela possa ser reaproveitada para outro
    > cargo"*

    E o sistema já tinha a peça: `PessoaTag` do mini-CRM, com catálogo, CRUD e
    as MESMAS duas FKs opcionais. **Nenhum campo novo.**

    Esta rota só MOSTRA e SUGERE. Aplicar é outro ato (`/reaproveitar`), porque
    tag aplicada sozinha vira ruído e o RH deixa de confiar na tag — o sistema
    propõe, o RH confirma.
    """
    v = db.get(Vaga, vaga_id)
    linhas = list(db.scalars(
        select(Entrevista).where(Entrevista.vaga_id == vaga_id)))
    pessoas = _pessoas_em_lote(db, linhas)
    # Uma pessoa entrevistada duas vezes (triagem + presencial) é UMA pessoa a
    # taguear, não duas — a chave é o par de FKs, não a entrevista.
    vistos, itens = set(), []
    for e in linhas:
        p = pessoas[e.id]
        chave = (p["talento_id"], p["candidato_id"])
        if chave in vistos:
            continue
        vistos.add(chave)
        itens.append({"nome": p["nome"], "talento_id": p["talento_id"],
                      "candidato_id": p["candidato_id"],
                      "recomendacao": e.recomendacao})
    cargo = (v.cargo if v is not None else None) or (v.titulo if v is not None else None)
    return {
        "itens": itens, "total": len(itens),
        "vaga_titulo": v.titulo if v is not None else None,
        # SUGESTÃO de nome de tag, editável — nunca aplicada sozinha.
        "tag_sugerida": f"reaproveitar: {cargo}" if cargo else "reaproveitar",
    }


@router.post("/rh/entrevistas/reaproveitar")
def reaproveitar(payload: ReaproveitarIn, db: Session = Depends(get_db),
                 rh: UsuarioRH = Depends(exige("selecao:entrevistar"))) -> dict:
    """Aplica a tag de reaproveitamento em lote (§ 14.3).

    **Reusa `PessoaTag` do mini-CRM — nenhum campo novo.** As tags já aparecem e
    filtram no dash de Talentos, então o reaproveitamento funciona sem tela
    nova: o RH filtra por "reaproveitar: vigia" e acha quem já conversou com a
    empresa.

    O catálogo (`Tag`) é reusado: cria-se a tag se ela não existir, para o RH
    não ter que ir a Configurações antes. Idempotente — marcar de novo não
    duplica, mesma mecânica de `crm.marcar_tag`.

    **Nada é automático** e nada é silencioso: a resposta diz quantas pessoas
    foram marcadas e quais não deram (`ignoradas`), pela regra da casa de que
    lote presta contas de quem ficou de fora.
    """
    nome = (payload.tag or "").strip()
    if not nome:
        raise HTTPException(status_code=422, detail="tag_obrigatoria")
    if not payload.pessoas:
        raise HTTPException(status_code=422, detail="nenhuma_pessoa")

    tag = db.scalar(select(Tag).where(Tag.nome == nome[:60]))
    if tag is None:
        tag = Tag(nome=nome[:60], ativo=True)
        db.add(tag)
        db.flush()

    marcadas, ignoradas = 0, []
    for p in payload.pessoas:
        tid, cid = p.talento_id, p.candidato_id
        if bool(tid) == bool(cid):
            ignoradas.append({"talento_id": tid, "candidato_id": cid,
                              "motivo": "informe exatamente talento ou candidato"})
            continue
        existe = db.scalar(select(PessoaTag).where(
            PessoaTag.tag_id == tag.id, PessoaTag.talento_id == tid,
            PessoaTag.candidato_id == cid))
        if existe is None:
            db.add(PessoaTag(tag_id=tag.id, talento_id=tid, candidato_id=cid,
                             aplicado_por=rh.email))
            marcadas += 1
    db.flush()
    registrar(db, "entrevista_reaproveitamento", ator="rh", ator_detalhe=rh.email,
              detalhe={"tag": tag.nome, "marcadas": marcadas,
                       "ignoradas": len(ignoradas),
                       "vaga": payload.vaga_titulo})
    db.commit()
    return {"tag": crm.dump_tag(tag), "marcadas": marcadas,
            "ignoradas": ignoradas}


@router.post("/rh/entrevistas", status_code=201)
def criar(payload: EntrevistaIn, db: Session = Depends(get_db),
          rh: UsuarioRH = Depends(exige("selecao:entrevistar"))) -> dict:
    """Marca uma entrevista OU registra uma que já aconteceu.

    `marcada_para = None` nasce direto em `realizada`: pessoa que aparece na
    porta é rotina, e exigir agendamento prévio mataria o módulo (cenário 3).
    """
    tid, cid = _exigir_pessoa(db, payload.talento_id, payload.candidato_id)
    if payload.tipo not in {t.value for t in TipoEntrevista}:
        raise HTTPException(status_code=422, detail="tipo_invalido")

    vaga_titulo, cargo_da_vaga = None, None
    if payload.vaga_id:
        v = db.get(Vaga, payload.vaga_id)
        if v is None:
            raise HTTPException(status_code=404, detail="vaga_nao_encontrada")
        vaga_titulo = v.titulo      # snapshot desde o nascimento (cenário 4)
        cargo_da_vaga = v.cargo

    # Posto (v2.74): snapshot do nome pela mesma razão do `vaga_titulo` — o
    # posto pode ir para a lixeira, e a entrevista tem que continuar dizendo
    # para ONDE a conversa foi.
    posto_nome = None
    if payload.posto_id:
        p = db.get(PostoServico, payload.posto_id)
        if p is None:
            raise HTTPException(status_code=404, detail="posto_nao_encontrado")
        posto_nome = p.nome

    modalidade = (payload.modalidade or "").strip() or None
    if modalidade is not None and modalidade not in inst.CHAVES_MODALIDADE:
        raise HTTPException(status_code=422, detail="modalidade_invalida")
    link = (payload.link_reuniao or "").strip() or None
    local = (payload.local or "").strip() or None
    # Online sem link não se marca (cenário 29): o convite sairia dizendo
    # "online" sem dizer por onde entrar. Recusa-se na GRAVAÇÃO, não no envio —
    # recusar só no e-mail deixaria a entrevista marcada e a pessoa sem acesso.
    erros = convite.erros_de_modalidade(modalidade, local, link)
    if erros:
        raise HTTPException(status_code=422,
                            detail={"erro": "modalidade_incompleta", "erros": erros})
    duracao = _exigir_duracao(payload.duracao_min)

    # O ROTEIRO (§ 14.1). Resolvido por herança quando o RH não escolhe:
    # cargo+senioridade → cargo → padrão. Cargo sem roteiro cai no padrão,
    # NUNCA em erro (cenário 23). A triagem não usa roteiro — ela não tem
    # competência nem âncora, é outra natureza (§ 4.1).
    roteiro = None
    if payload.tipo == TipoEntrevista.entrevista.value:
        roteiro = inst.resolver_roteiro(
            db, cargo=(payload.cargo or cargo_da_vaga),
            senioridade=payload.senioridade, roteiro_id=payload.roteiro_id)

    ja_realizada = payload.marcada_para is None
    e = Entrevista(
        talento_id=tid, candidato_id=cid,
        vaga_id=payload.vaga_id, vaga_titulo=vaga_titulo,
        # v2.74: quando não há vaga, cargo e posto dizem para que a conversa foi.
        # O cargo da VAGA tem precedência — se ela existe, é ela que manda.
        cargo=(cargo_da_vaga or (payload.cargo or "").strip() or None),
        posto_id=payload.posto_id, posto_nome=posto_nome,
        tipo=TipoEntrevista(payload.tipo),
        status=StatusEntrevista.realizada if ja_realizada else StatusEntrevista.marcada,
        marcada_para=payload.marcada_para,
        realizada_em=datetime.now(timezone.utc) if ja_realizada else None,
        local=local, modalidade=modalidade, link_reuniao=link,
        duracao_min=duracao if duracao is not None else convite.DURACAO_MIN,
        roteiro_id=roteiro.id if roteiro is not None else None,
        # SNAPSHOT do instrumento, não só a FK: o roteiro pode ganhar versão ou
        # ser arquivado, e a entrevista tem que continuar legível com as
        # perguntas e âncoras de quando a nota foi dada (cenários 21 e 24).
        roteiro_snapshot=inst.snapshot_do_roteiro(roteiro),
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

    # O convite sai DEPOIS de a entrevista existir — e nunca derruba a criação:
    # SMTP fora do ar não pode impedir o RH de registrar o compromisso. O
    # resultado é ANUNCIADO na resposta, não engolido.
    pessoa = _pessoa_de(db, e)
    envio = None
    if payload.enviar_convite:
        envio = convite.enviar_convite(db, e, pessoa["nome"], pessoa.get("email"))

    registrar(db, "entrevista_criada", ator="rh", ator_detalhe=rh.email,
              candidato_id=cid,
              detalhe={"entrevista": str(e.id), "tipo": e.tipo.value,
                       "ja_realizada": ja_realizada, "vaga": vaga_titulo,
                       "modalidade": modalidade,
                       "roteiro": str(roteiro.id) if roteiro is not None else None,
                       "convite_enviado": bool(envio and envio.get("enviado"))})
    db.commit()
    saida = _dump(e, pessoa)
    if envio is not None:
        saida["convite"] = envio
    return saida


# --------------------------------------------------------------------------
# PARAMÉTRICAS
# --------------------------------------------------------------------------

@router.get("/rh/entrevistas/{entrevista_id}")
def ver(entrevista_id: uuid.UUID, db: Session = Depends(get_db),
    _rh: UsuarioRH = Depends(exige("selecao:entrevistar"))) -> dict:
    e = db.get(Entrevista, entrevista_id)
    if e is None:
        raise HTTPException(status_code=404, detail="entrevista_nao_encontrada")
    return _dump(e, _pessoa_de(db, e))


@router.put("/rh/entrevistas/{entrevista_id}")
def preencher(entrevista_id: uuid.UUID, payload: PreencherIn,
              db: Session = Depends(get_db),
              rh: UsuarioRH = Depends(exige("selecao:entrevistar"))) -> dict:
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
        # As perguntas VÁLIDAS vêm do roteiro de triagem publicado (v2.67): com
        # as perguntas editáveis, validar contra a constante recusaria a resposta
        # de uma pergunta criada pelo RH como "desconhecida", e o catálogo seria
        # cadastrável e não preenchível.
        r_tri = inst.resolver_triagem(db)
        erros = inst.validar_triagem(
            payload.triagem, payload.triagem_desfecho,
            perguntas=(r_tri.perguntas if r_tri is not None else None))
        if erros:
            raise HTTPException(status_code=422,
                                detail={"erro": "preenchimento_invalido", "erros": erros})
        if payload.triagem is not None:
            e.triagem = payload.triagem
        if payload.triagem_desfecho is not None:
            e.triagem_desfecho = payload.triagem_desfecho
    else:
        # Valida contra o instrumento COM QUE A FICHA FOI ABERTA (o snapshot),
        # não contra a constante: um roteiro customizado de 6 competências teria
        # as 2 extras recusadas como "competência desconhecida", e o roteiro do
        # RH seria cadastrável e não preenchível.
        instrumento = (e.roteiro_snapshot or {}).get("competencias")
        erros = inst.validar_entrevista(
            payload.competencias, payload.justificativas,
            payload.recomendacao, payload.recomendacao_motivo,
            instrumento=instrumento)
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

    # --- Remarcação / modalidade pela própria ficha (v2.66) ---
    if payload.modalidade is not None:
        m = payload.modalidade.strip() or None
        if m is not None and m not in inst.CHAVES_MODALIDADE:
            raise HTTPException(status_code=422, detail="modalidade_invalida")
        e.modalidade = m
    if payload.link_reuniao is not None:
        e.link_reuniao = payload.link_reuniao.strip() or None
    if payload.marcada_para is not None:
        e.marcada_para = payload.marcada_para
    if payload.duracao_min is not None:
        e.duracao_min = _exigir_duracao(payload.duracao_min)
    erros_mod = convite.erros_de_modalidade(e.modalidade, e.local, e.link_reuniao)
    if erros_mod:
        raise HTTPException(status_code=422,
                            detail={"erro": "modalidade_incompleta",
                                    "erros": erros_mod})

    concluiu = False
    if payload.concluir:
        if tipo == TipoEntrevista.entrevista.value:
            faltando = inst.completa_entrevista(
                e.competencias, e.recomendacao,
                instrumento=(e.roteiro_snapshot or {}).get("competencias"))
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

    pessoa = _pessoa_de(db, e)
    envio = None
    if payload.reenviar_convite:
        # Reenvio = remarcação: `enviar_convite` INCREMENTA a sequência quando
        # já houve convite, e é isso que faz o Outlook atualizar o compromisso
        # em vez de ignorar a mudança em silêncio (cenário 27).
        envio = convite.enviar_convite(db, e, pessoa["nome"], pessoa.get("email"))

    registrar(db, "entrevista_preenchida", ator="rh", ator_detalhe=rh.email,
              candidato_id=e.candidato_id,
              detalhe={"entrevista": str(e.id), "concluida": concluiu,
                       "recomendacao": e.recomendacao,
                       "triagem_desfecho": e.triagem_desfecho,
                       "convite_reenviado": bool(envio and envio.get("enviado"))})
    db.commit()
    saida = _dump(e, pessoa)
    if envio is not None:
        saida["convite"] = envio
    return saida


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
             rh: UsuarioRH = Depends(exige("selecao:entrevistar"))) -> dict:
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

    # Cancelou/remarcou com convite já enviado? Manda o CANCELAMENTO com o
    # mesmo UID (cenário 28) — sem isso o compromisso fica na agenda da pessoa
    # depois de cancelado, e ela vem. Só faz sentido para quem recebeu convite:
    # avisar do cancelamento de algo que nunca foi comunicado é ruído.
    pessoa = _pessoa_de(db, e)
    envio = None
    encerra = payload.status in (StatusEntrevista.cancelada.value,
                                 StatusEntrevista.remarcada.value)
    if payload.avisar_pessoa and encerra and e.convite_enviado_em is not None:
        envio = convite.enviar_convite(db, e, pessoa["nome"], pessoa.get("email"),
                                       cancelar=True)

    registrar(db, "entrevista_desfecho", ator="rh", ator_detalhe=rh.email,
              candidato_id=e.candidato_id,
              detalhe={"entrevista": str(e.id), "status": payload.status,
                       "motivo": motivo or None,
                       "cancelamento_enviado": bool(envio and envio.get("enviado"))})
    db.commit()
    saida = _dump(e, pessoa)
    if envio is not None:
        saida["convite"] = envio
    return saida


@router.post("/rh/entrevistas/{entrevista_id}/arquivar")
def arquivar(entrevista_id: uuid.UUID, payload: ArquivarIn,
             db: Session = Depends(get_db),
             rh: UsuarioRH = Depends(exige("selecao:entrevistar"))) -> dict:
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
                 rh: UsuarioRH = Depends(exige("selecao:entrevistar"))) -> dict:
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
def baixar_anexo(entrevista_id: uuid.UUID, db: Session = Depends(get_db),
    _rh: UsuarioRH = Depends(exige("selecao:entrevistar"))) -> Response:
    e = db.get(Entrevista, entrevista_id)
    if e is None or not e.anexo_key:
        raise HTTPException(status_code=404, detail="anexo_nao_encontrado")
    dados = storage.ler(e.anexo_key)
    return Response(content=dados,
                    media_type=e.anexo_tipo or "application/octet-stream",
                    headers={"Content-Disposition":
                             f'inline; filename="{e.anexo_nome or "anexo"}"'})


# ==========================================================================
# DOCUMENTO da entrevista (v2.67, § 15.2-15.4)
#
# ⚠️ **NADA DAQUI ENTRA NO DOSSIÊ DE ADMISSÃO.** Decisão do Bruno, que chegou a
# incluir e corrigiu na mesma sessão: *"não não. no dossiê de admissão não."*
# O dossiê CIRCULA (cliente, pasta física, quem pedir) e nota de seleção com
# justificativa escrita é dado sensível sobre a pessoa — mesma regra que manteve
# resultado de teste fora do dossiê na v2.21.
#
# A garantia é ESTRUTURAL, não uma lembrança: o PDF é gravado com prefixo
# `entrevistas/`, e o `services/dossie.py` só lê `Assinatura.pdf_key`,
# `SlotDocumento.arquivo_pdf_key` e `SolicitacaoAssinatura.pdf_final_key` — três
# tabelas que este módulo deliberadamente NÃO usa (ver o docstring de
# `models/assinatura_entrevista.py`, que explica por que a
# `SolicitacaoAssinatura` foi descartada: o dossiê a varre sem filtrar origem).
# Há teste por mutação cobrindo isto.
# ==========================================================================


def _instrumento_da(e: Entrevista):
    """As competências COM QUE a entrevista foi feita — do snapshot, nunca do
    roteiro vivo (cenários 21 e 24)."""
    return (e.roteiro_snapshot or {}).get("competencias")


def _exigir_documentavel(db: Session, e: Entrevista) -> None:
    """422 com o que falta, quando a ficha ainda não pode virar documento."""
    from app.services import entrevista_pdf as epdf

    erros = epdf.erros_para_documento(e, _instrumento_da(e))
    if erros:
        raise HTTPException(status_code=422, detail={
            "erro": "entrevista_incompleta", "faltando": erros})


def _gerar_pdf_da(db: Session, e: Entrevista, assinaturas=None) -> bytes:
    from app.models.entrevista import TipoEntrevista
    from app.services import entrevista_pdf as epdf

    pessoa = _pessoa_de(db, e)
    tipo = e.tipo.value if hasattr(e.tipo, "value") else e.tipo
    if tipo == TipoEntrevista.triagem.value:
        r = inst.resolver_triagem(db)
        return epdf.gerar_ficha_triagem(
            db, e, pessoa["nome"], r.perguntas if r is not None else None)
    return epdf.gerar_ficha_entrevista(db, e, pessoa["nome"], assinaturas)


def _assinaturas_vivas(db: Session, entrevista_id) -> list:
    """As vias NÃO substituídas, da mais antiga para a mais nova."""
    return list(db.scalars(
        select(AssinaturaEntrevista)
        .where(AssinaturaEntrevista.entrevista_id == entrevista_id,
               AssinaturaEntrevista.substituida_em.is_(None))
        .order_by(AssinaturaEntrevista.via)))


@router.get("/rh/entrevistas/{entrevista_id}/documento")
def baixar_documento(entrevista_id: uuid.UUID, db: Session = Depends(get_db),
                     rh: UsuarioRH = Depends(exige("selecao:entrevistar"))) -> Response:
    """A ficha em PDF. Assinada, serve o PDF GRAVADO; senão, gera na hora.

    Servir o arquivo gravado (e não regerar) é o que faz o hash continuar
    válido: o SHA-256 do manifesto descreve BYTES, e um PDF regerado teria
    outro carimbo de data interno.
    """
    from app.services.export_planilha import slug

    e = db.get(Entrevista, entrevista_id)
    if e is None:
        raise HTTPException(status_code=404, detail="entrevista_nao_encontrada")
    _exigir_documentavel(db, e)

    pessoa = _pessoa_de(db, e)
    assinadas = _assinaturas_vivas(db, e.id)
    com_pdf = [a for a in assinadas if a.pdf_key]
    if com_pdf:
        try:
            dados = storage.ler(com_pdf[-1].pdf_key)
        except Exception:
            # Arquivo sumiu do storage: regera SEM os blocos de assinatura. Um
            # PDF regerado não reproduz o hash, então afirmar que ele é a via
            # assinada seria mentira — melhor entregar o documento não assinado
            # do que uma via cuja integridade não se confere.
            dados = _gerar_pdf_da(db, e)
    else:
        dados = _gerar_pdf_da(db, e)

    registrar(db, "entrevista_documento_baixado", ator="rh", ator_detalhe=rh.email,
              candidato_id=e.candidato_id,
              detalhe={"entrevista": str(e.id), "pessoa": pessoa["nome"]})
    db.commit()
    nome = slug(f"entrevista-{pessoa['nome']}", fallback="entrevista")
    return Response(content=dados, media_type="application/pdf",
                    headers={"Content-Disposition": f'inline; filename="{nome}.pdf"'})


class AssinarFichaIn(BaseModel):
    # A senha da PRÓPRIA sessão do RH logado — o mesmo método de
    # `solicitacoes_assinatura.py:400` (`prova_metodo="senha_sessao_rh"`).
    senha: str


@router.post("/rh/entrevistas/{entrevista_id}/assinar")
def assinar_ficha(entrevista_id: uuid.UUID, payload: AssinarFichaIn,
                  request: Request, db: Session = Depends(get_db),
                  rh: UsuarioRH = Depends(exige("documentos:assinar"))) -> dict:
    """Assina a ficha de entrevista — **o RH que conduziu** (§ 15.3).

    O entrevistado NÃO assina: exigiria mandar link a quem talvez não seja
    contratado, e o link lhe daria acesso às notas e às justificativas escritas
    a seu respeito.

    Alterar a entrevista depois NÃO reescreve esta via (cenário 31): assinar de
    novo cria a via SEGUINTE e marca a anterior como substituída — que continua
    existindo, com o hash dela. É a regra da casa desde 2026-07-15: assinatura é
    prova de um ato, e ato não se edita retroativamente.
    """
    from app.api.auth_rh import verificar_senha

    e = db.get(Entrevista, entrevista_id)
    if e is None:
        raise HTTPException(status_code=404, detail="entrevista_nao_encontrada")
    # A recusa da ficha incompleta vem ANTES da conferência de senha: negar por
    # senha uma ficha que nem poderia virar documento mandaria o RH procurar o
    # problema no lugar errado.
    _exigir_documentavel(db, e)
    if not verificar_senha(payload.senha, rh.senha_hash):
        raise HTTPException(status_code=401, detail="senha_invalida")

    agora = datetime.now(timezone.utc)
    anteriores = _assinaturas_vivas(db, e.id)
    for a in anteriores:
        a.substituida_em = agora

    # O hash descreve o documento SEM o bloco de assinatura — mesma convenção do
    # `Assinatura.hash_sha256`: confere-se a integridade regerando o base.
    base = _gerar_pdf_da(db, e)
    registro = AssinaturaEntrevista(
        entrevista_id=e.id, usuario_rh_id=rh.id,
        assinante_nome=rh.nome, assinante_email=rh.email,
        hash_sha256=hashlib.sha256(base).hexdigest(),
        prova_metodo="senha_sessao_rh",
        ip=ip_do_cliente(request),
        user_agent=(request.headers.get("user-agent") or "")[:400],
        via=(max((a.via for a in anteriores), default=0) + 1),
        assinado_em=agora)
    db.add(registro)
    db.flush()

    assinado = _gerar_pdf_da(db, e, [registro])
    # Prefixo `entrevistas/` — o dossiê não olha para cá (ver o aviso no topo
    # deste bloco).
    key = f"entrevistas/{e.id}/ficha-assinada-v{registro.via}.pdf"
    storage.salvar(key, assinado, "application/pdf")
    registro.pdf_key = key

    registrar(db, "entrevista_ficha_assinada", ator="rh", ator_detalhe=rh.email,
              candidato_id=e.candidato_id,
              detalhe={"entrevista": str(e.id), "via": registro.via,
                       "metodo": "senha_sessao_rh"})
    db.commit()
    return {"assinado": True, "via": registro.via,
            "hash": registro.hash_sha256, "assinado_em": registro.assinado_em,
            "assinante": registro.assinante_nome}


@router.get("/rh/entrevistas/{entrevista_id}/assinaturas")
def listar_assinaturas(entrevista_id: uuid.UUID,
                       db: Session = Depends(get_db),
    _rh: UsuarioRH = Depends(exige("selecao:entrevistar"))) -> dict:
    """As vias da ficha, inclusive as SUBSTITUÍDAS — a via antiga some da vista,
    nunca do registro."""
    e = db.get(Entrevista, entrevista_id)
    if e is None:
        raise HTTPException(status_code=404, detail="entrevista_nao_encontrada")
    linhas = db.scalars(
        select(AssinaturaEntrevista)
        .where(AssinaturaEntrevista.entrevista_id == entrevista_id)
        .order_by(AssinaturaEntrevista.via)).all()
    from app.services import entrevista_pdf as epdf
    return {
        "itens": [{
            "id": a.id, "via": a.via, "assinante": a.assinante_nome,
            "assinante_email": a.assinante_email, "assinado_em": a.assinado_em,
            "hash": a.hash_sha256, "metodo": a.prova_metodo,
            "substituida_em": a.substituida_em,
        } for a in linhas],
        # O que impede de assinar AGORA — a tela mostra em vez de deixar o botão
        # ligado para dar 422 no clique.
        "impedimentos": epdf.erros_para_documento(e, _instrumento_da(e)),
    }


@router.delete("/rh/entrevistas/{entrevista_id}", status_code=204)
def excluir(entrevista_id: uuid.UUID, db: Session = Depends(get_db),
            rh: UsuarioRH = Depends(exige("selecao:entrevistar"))) -> Response:
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
