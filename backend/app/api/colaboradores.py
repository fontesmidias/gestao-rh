"""Dash de colaboradores do RH: visão com filtros e exportação Excel completa
(linha a linha, com todas as respostas do formulário), importação em massa da
base do Tirvu e controles de vínculo (efetivar, desligar, transferir posto)."""

import io
import re
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Response, UploadFile
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.auth_rh import requer_rh
from app.core.db import get_db
from app.models.candidato import Candidato, PostoServico, StatusCandidato
from app.models.ficha import (ContatoEmergencia, DadosPessoais,
                              DadosProfissionaisBancarios, Dependente,
                              DocumentosIdentificacao, Endereco, FichaEmergencia,
                              ValeTransporte)
from app.services.auditoria import registrar
from app.services.export_planilha import linha_completa as _linha_completa
from app.services.export_planilha import montar_workbook
from app.services.idempotencia import travar_por
from app.models.usuario_rh import UsuarioRH

router = APIRouter(tags=["colaboradores-rh"], dependencies=[Depends(requer_rh)])


def _filtrar(db: Session, status: str | None, busca: str | None,
             situacao: str | None = None, posto_id: uuid.UUID | None = None,
             so_colaboradores: bool = True) -> list[Candidato]:
    q = select(Candidato).order_by(Candidato.criado_em.desc())
    # A página Colaboradores mostra APENAS quem já é colaborador de fato: quem
    # foi importado do Tirvu ou efetivado (situacao preenchida). Quem ainda está
    # no fluxo de admissão (situacao NULL) aparece só em Admissões — antes
    # vazava para cá porque candidato e colaborador eram a mesma listagem.
    if so_colaboradores:
        q = q.where(Candidato.situacao.is_not(None))
    if status:
        q = q.where(Candidato.status == StatusCandidato(status))
    if situacao:
        q = q.where(Candidato.situacao == situacao)
    if posto_id:
        q = q.where(Candidato.posto_servico_id == posto_id)
    candidatos = db.scalars(q).all()
    if busca:
        termo = busca.strip().lower()
        so_digitos = "".join(ch for ch in termo if ch.isdigit())
        # CPF agora é campo nativo do Candidato (importação); mas para quem veio
        # da admissão o CPF vive na ficha de documentos. Consulto ambos.
        cpfs = {}
        if so_digitos:
            for doc in db.scalars(select(DocumentosIdentificacao)).all():
                cpfs[doc.candidato_id] = doc.cpf or ""
        candidatos = [
            c for c in candidatos
            # e-mail e celular podem ser None (convite sem e-mail, v1.3) —
            # era isto que derrubava a busca com 500.
            if termo in (c.nome_completo or "").lower()
            or termo in (c.email or "").lower()
            or (so_digitos and (so_digitos in _so_digitos(c.cpf)
                                or so_digitos in cpfs.get(c.id, "")))
        ]
    return candidatos


@router.get("/rh/colaboradores")
def listar(status: str | None = None, busca: str | None = None,
           situacao: str | None = None, posto_id: uuid.UUID | None = None,
           incluir_admissao: bool = False,
           db: Session = Depends(get_db)) -> list[dict]:
    # incluir_admissao=True traz também quem ainda está no fluxo de admissão
    # (para o RH localizar e efetivar um aprovado, por ex.).
    candidatos = _filtrar(db, status, busca, situacao, posto_id,
                          so_colaboradores=not incluir_admissao)
    # nomes dos postos em um só lookup (evita N+1 na lista de 1.156)
    postos = {p.id: p.nome for p in db.scalars(select(PostoServico)).all()}
    saida = []
    for c in candidatos:
        # Para importados, CPF/nascimento já são nativos; para admissão, caem na
        # ficha. Só busco a ficha quando o campo nativo está vazio.
        cpf = c.cpf
        nasc = c.data_nascimento
        if not cpf:
            d = db.get(DocumentosIdentificacao, c.id)
            cpf = d.cpf if d else None
        if not nasc:
            p = db.get(DadosPessoais, c.id)
            nasc = p.data_nascimento if p else None
        saida.append({
            "id": c.id, "nome_completo": c.nome_completo, "email": c.email,
            "celular_whatsapp": c.celular_whatsapp, "status": c.status,
            "situacao": c.situacao, "origem": c.origem,
            "cpf": cpf, "nascimento": nasc, "matricula": c.matricula,
            "posto_id": c.posto_servico_id,
            "posto_nome": postos.get(c.posto_servico_id),
            "data_admissao": c.data_admissao,
            "data_desligamento": c.data_desligamento,
            "na_dominio_em": c.na_dominio_em,
            "criado_em": c.criado_em,
            "dossie_gerado_em": c.dossie_gerado_em,
        })
    return saida


@router.get("/rh/colaboradores/exportar")
def exportar(status: str | None = None, busca: str | None = None,
             situacao: str | None = None, posto_id: uuid.UUID | None = None,
             incluir_admissao: bool = False,
             db: Session = Depends(get_db),
             rh: UsuarioRH = Depends(requer_rh)) -> Response:
    """Excel com uma linha por colaborador e TODAS as respostas do formulário.
    Respeita os mesmos filtros da tela (só-colaboradores por padrão)."""
    candidatos = _filtrar(db, status, busca, situacao, posto_id,
                          so_colaboradores=not incluir_admissao)
    conteudo = montar_workbook([_linha_completa(db, c) for c in candidatos])
    registrar(db, "colaboradores_exportados", ator="rh", ator_detalhe=rh.email,
              detalhe={"linhas": len(candidatos), "status": status or "todos"})
    db.commit()
    agora = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return Response(
        content=conteudo,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition":
                 f'attachment; filename="colaboradores-{agora}.xlsx"'},
    )


# ======================================================================
# Exportação para o Tirvu (layout de importação de admissões)
# ======================================================================
#
# Só se exporta COLABORADOR: a pessoa nasce aqui como candidata e só passa a
# existir no Tirvu quando é efetivada (decisão do Bruno, 2026-07-19). Por
# padrão saem apenas os que vieram da admissão — os importados do Tirvu já
# existem lá e seriam ignorados por ele de qualquer forma.


def _colaboradores_para_tirvu(db: Session, status: str | None, busca: str | None,
                              situacao: str | None, posto_id: uuid.UUID | None,
                              ids: str | None, incluir_importados: bool) -> list[Candidato]:
    if ids:
        alvo = [i for i in (x.strip() for x in ids.split(",")) if i]
        return [c for i in alvo if (c := db.get(Candidato, uuid.UUID(i))) is not None]
    candidatos = _filtrar(db, status, busca, situacao, posto_id, so_colaboradores=True)
    if not incluir_importados:
        candidatos = [c for c in candidatos if c.origem != "importacao"]
    return candidatos


# ATENÇÃO: rotas literais ANTES da paramétrica /{cid} (senão vira UUID inválido).
@router.get("/rh/colaboradores/tirvu-pendencias")
def pendencias_tirvu(status: str | None = None, busca: str | None = None,
                     situacao: str | None = None, posto_id: uuid.UUID | None = None,
                     ids: str | None = None, incluir_importados: bool = False,
                     db: Session = Depends(get_db)) -> dict:
    """Pré-checagem do export: o Tirvu RECUSA linha sem CTPS/PIS. O front avisa
    ANTES do download — melhor saber aqui do que descobrir lá."""
    from app.services.export_tirvu import linha_tirvu, pendencias_linha

    candidatos = _colaboradores_para_tirvu(db, status, busca, situacao, posto_id,
                                           ids, incluir_importados)
    problemas = []
    for c in candidatos:
        faltas = pendencias_linha(linha_tirvu(db, c))
        if faltas:
            problemas.append({"id": c.id, "nome": c.nome_completo, "faltam": faltas})
    return {"total": len(candidatos), "com_pendencia": problemas}


@router.get("/rh/colaboradores/exportar-tirvu")
def exportar_tirvu_massa(status: str | None = None, busca: str | None = None,
                         situacao: str | None = None, posto_id: uuid.UUID | None = None,
                         ids: str | None = None, incluir_importados: bool = False,
                         db: Session = Depends(get_db),
                         rh: UsuarioRH = Depends(requer_rh)) -> Response:
    """Planilha no layout de importação de admissões do Tirvu (28 colunas em
    ordem fixa). É o artefato mais sensível do sistema (CPF+PIS+salário em
    massa): auditoria sempre, com quem baixou, quantas linhas e quais postos."""
    from app.services.export_tirvu import linha_tirvu

    candidatos = _colaboradores_para_tirvu(db, status, busca, situacao, posto_id,
                                           ids, incluir_importados)
    if not candidatos:
        raise HTTPException(status_code=404, detail="nenhum_colaborador")
    linhas = [linha_tirvu(db, c) for c in candidatos]
    conteudo = montar_workbook(linhas, titulo="Admissões")
    registrar(db, "tirvu_exportado", ator="rh", ator_detalhe=rh.email,
              detalhe={"linhas": len(linhas), "incluiu_importados": incluir_importados,
                       "postos": sorted({l["Posto de Serviço"] for l in linhas
                                         if l["Posto de Serviço"]})})
    db.commit()
    agora = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return Response(
        content=conteudo,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition":
                 f'attachment; filename="importacao-tirvu-{agora}.xlsx"'})


# ======================================================================
# Importação em massa da base do Tirvu
# ======================================================================
#
# Mapeia cabeçalhos da planilha do Tirvu -> campos fixos do Candidato. Tudo que
# NÃO estiver aqui entra em `dados_tirvu` (colunas dinâmicas). O casamento de
# cabeçalho é tolerante (sem acento, minúsculo, sem espaços duplos).

_MAPA_TIRVU = {
    "cpf": "cpf",
    "colaborador": "nome_completo",
    "nome": "nome_completo",
    "matricula": "matricula",
    "nascimento": "data_nascimento",
    "data de nascimento": "data_nascimento",
    "cargo": "cargo_funcao",
    "lotacao": "_lotacao",           # vira posto (casado/criado à parte)
    "admissao": "data_admissao",
    "demissao": "data_desligamento",
    "status": "_situacao",           # ATIVO/DEMITIDO -> situacao
    "e-mail": "email",
    "email": "email",
    "telefone": "celular_whatsapp",
    "salario": "salario_base",
}


def _norm(txt: str) -> str:
    import unicodedata
    txt = unicodedata.normalize("NFKD", str(txt or "")).encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", txt).strip().lower()


def _so_digitos(v) -> str:
    return "".join(ch for ch in str(v or "") if ch.isdigit())


def _cpf_fmt(v) -> str | None:
    d = _so_digitos(v)
    if len(d) != 11:
        return None
    return f"{d[:3]}.{d[3:6]}.{d[6:9]}-{d[9:]}"


def _casar_posto(db: Session, cache: dict, lotacao: str) -> uuid.UUID | None:
    """Casa a 'Lotação' do Tirvu com um posto existente (por nome, case-insens.);
    se não existir, cria um posto novo (nunca falha a linha por isto)."""
    nome = (lotacao or "").strip()
    if not nome:
        return None
    chave = nome.lower()
    if chave in cache:
        return cache[chave]
    posto = db.scalar(select(PostoServico).where(PostoServico.nome.ilike(nome)))
    if posto is None:
        posto = PostoServico(nome=nome)
        db.add(posto)
        db.flush()
    cache[chave] = posto.id
    return posto.id


@router.post("/rh/colaboradores/importar")
async def importar_colaboradores(arquivo: UploadFile,
                                 db: Session = Depends(get_db),
                                 rh: UsuarioRH = Depends(requer_rh)) -> dict:
    """Importa a base de colaboradores ativos a partir da planilha (.xlsx) do
    Tirvu. Idempotente por CPF: linha cujo CPF já existe é ATUALIZADA, não
    duplicada. Colunas conhecidas viram campos; as demais entram em dados_tirvu.
    A 'Lotação' é casada com um posto (criado se não existir)."""
    from openpyxl import load_workbook

    try:
        conteudo = await arquivo.read()
    finally:
        # descarta o spool em disco do Starlette — planilha com CPFs não
        # persiste no container depois de processada (regra transversal)
        await arquivo.close()
    try:
        wb = load_workbook(io.BytesIO(conteudo), read_only=True, data_only=True)
    except Exception:
        raise HTTPException(status_code=422, detail="arquivo_invalido")
    ws = wb.active
    linhas = ws.iter_rows(values_only=True)
    try:
        cabecalho = [str(c or "").strip() for c in next(linhas)]
    except StopIteration:
        raise HTTPException(status_code=422, detail="planilha_vazia")

    # posição da coluna de CPF (obrigatória para dedup)
    norm_cab = [_norm(c) for c in cabecalho]
    if "cpf" not in norm_cab:
        raise HTTPException(status_code=422, detail="sem_coluna_cpf")

    # índice de CPFs já cadastrados -> registro
    ja = {c.cpf: c for c in db.scalars(
        select(Candidato).where(Candidato.cpf.is_not(None))).all()}
    cache_postos: dict = {}
    criados = atualizados = ignorados = 0
    sem_cpf = 0

    for bruta in linhas:
        if bruta is None or all(v in (None, "") for v in bruta):
            continue
        valores = list(bruta) + [None] * (len(cabecalho) - len(bruta))
        cpf = _cpf_fmt(valores[norm_cab.index("cpf")])
        if not cpf:
            sem_cpf += 1
            continue

        campos: dict = {}
        lotacao = None
        situacao_bruta = None
        dinamicos: dict = {}
        for titulo, nrm, valor in zip(cabecalho, norm_cab, valores):
            destino = _MAPA_TIRVU.get(nrm)
            v = "" if valor is None else str(valor).strip()
            if destino == "_lotacao":
                lotacao = v
            elif destino == "_situacao":
                situacao_bruta = v
            elif destino == "cpf":
                pass  # já tratado
            elif destino:
                campos[destino] = v or None
            elif v:
                dinamicos[titulo] = v

        situacao = "desligado" if _norm(situacao_bruta).startswith(("demit", "inativ", "deslig")) \
            else "ativo"

        alvo = ja.get(cpf)
        if alvo is None:
            alvo = Candidato(cpf=cpf, nome_completo=campos.get("nome_completo") or "(sem nome)",
                             origem="importacao")
            db.add(alvo)
            ja[cpf] = alvo
            criados += 1
        else:
            atualizados += 1
        # aplica campos fixos (não sobrescreve nome vazio)
        for k, val in campos.items():
            if k == "nome_completo" and not val:
                continue
            setattr(alvo, k, val)
        alvo.situacao = situacao
        alvo.status = StatusCandidato.desligado if situacao == "desligado" else StatusCandidato.ativo
        if lotacao:
            alvo.posto_servico_id = _casar_posto(db, cache_postos, lotacao)
        # mescla dinâmicos preservando o que já houver
        base = dict(alvo.dados_tirvu or {})
        base.update(dinamicos)
        alvo.dados_tirvu = base

    registrar(db, "colaboradores_importados", ator="rh", ator_detalhe=rh.email,
              detalhe={"criados": criados, "atualizados": atualizados,
                       "sem_cpf": sem_cpf, "postos_novos": len(cache_postos)})
    db.commit()
    return {"criados": criados, "atualizados": atualizados,
            "sem_cpf": sem_cpf, "postos_tocados": len(cache_postos),
            "total_base": len(ja)}


# ======================================================================
# Controles de vínculo: efetivar candidato, desligar, transferir posto
# ======================================================================


class DesligamentoIn(BaseModel):
    data_desligamento: str  # dd/mm/aaaa


class TransferenciaIn(BaseModel):
    posto_id: uuid.UUID
    data_transferencia: str | None = None  # registrada em dados_tirvu (histórico)


def _get_colab(db: Session, cid: uuid.UUID) -> Candidato:
    c = db.get(Candidato, cid)
    if c is None:
        raise HTTPException(status_code=404, detail="colaborador_nao_encontrado")
    return c


def _efetivar_um(db: Session, c: Candidato) -> None:
    c.situacao = "ativo"
    c.status = StatusCandidato.ativo
    if not c.data_admissao:
        c.data_admissao = datetime.now(timezone.utc).strftime("%d/%m/%Y")


class LoteEfetivarIn(BaseModel):
    ids: list[uuid.UUID]


# ATENÇÃO: a rota específica /lote/efetivar precisa vir ANTES da paramétrica
# /{cid}/efetivar, senão "lote" é interpretado como um UUID inválido (422).
@router.post("/rh/colaboradores/lote/efetivar")
def efetivar_lote(payload: LoteEfetivarIn, db: Session = Depends(get_db),
                  rh: UsuarioRH = Depends(requer_rh)) -> dict:
    """Efetiva vários candidatos de uma vez. Já-colaboradores são pulados."""
    efetivados, pulados = 0, 0
    for cid in payload.ids:
        c = db.get(Candidato, cid)
        if c is None:
            continue
        if c.situacao:  # já é colaborador (ativo/desligado): não mexe
            pulados += 1
            continue
        _efetivar_um(db, c)
        efetivados += 1
    registrar(db, "colaboradores_efetivados_lote", ator="rh", ator_detalhe=rh.email,
              detalhe={"efetivados": efetivados, "pulados": pulados})
    db.commit()
    return {"efetivados": efetivados, "pulados": pulados}


class AcaoMassaColabIn(BaseModel):
    ids: list[uuid.UUID]
    acao: str  # "desligar" | "reativar" | "marcar_dominio" | "desmarcar_dominio"
    data_desligamento: str | None = None  # obrigatória para "desligar"


@router.post("/rh/colaboradores/lote/acao")
def acao_massa_colaboradores(payload: AcaoMassaColabIn, db: Session = Depends(get_db),
                             rh: UsuarioRH = Depends(requer_rh)) -> dict:
    """Ação em massa nos colaboradores selecionados: desligar (com data) ou
    reativar. Não há exclusão — registro trabalhista não se apaga; desligar é o
    correto. Só age sobre quem já é colaborador (tem situação)."""
    if payload.acao not in ("desligar", "reativar", "marcar_dominio", "desmarcar_dominio"):
        raise HTTPException(status_code=422, detail="acao_invalida")
    if payload.acao == "desligar" and not (payload.data_desligamento or "").strip():
        raise HTTPException(status_code=422, detail="data_desligamento_obrigatoria")
    afetados, pulados = 0, 0
    for cid in payload.ids:
        c = db.get(Candidato, cid)
        if c is None:
            pulados += 1
            continue
        # conciliação com a Domínio vale para qualquer admissão (mesmo em curso)
        if payload.acao in ("marcar_dominio", "desmarcar_dominio"):
            c.na_dominio_em = (datetime.now(timezone.utc)
                               if payload.acao == "marcar_dominio" else None)
            afetados += 1
            continue
        if not c.situacao:  # desligar/reativar: ignora candidatos em admissão
            pulados += 1
            continue
        if payload.acao == "desligar":
            c.situacao = "desligado"
            c.status = StatusCandidato.desligado
            c.data_desligamento = payload.data_desligamento.strip()
        else:  # reativar
            c.situacao = "ativo"
            c.status = StatusCandidato.ativo
            c.data_desligamento = None
        afetados += 1
    registrar(db, "colaboradores_acao_massa", ator="rh", ator_detalhe=rh.email,
              detalhe={"acao": payload.acao, "afetados": afetados, "pulados": pulados})
    db.commit()
    return {"afetados": afetados, "pulados": pulados}


@router.post("/rh/colaboradores/{cid}/efetivar",
             dependencies=[Depends(travar_por("efetivar"))])
def efetivar(cid: uuid.UUID, db: Session = Depends(get_db),
             rh: UsuarioRH = Depends(requer_rh)) -> dict:
    """Transforma um candidato aprovado em colaborador ativo (mesmo registro)."""
    c = _get_colab(db, cid)
    _efetivar_um(db, c)
    registrar(db, "colaborador_efetivado", ator="rh", ator_detalhe=rh.email,
              candidato_id=c.id, detalhe={"nome": c.nome_completo})
    db.commit()
    return {"id": c.id, "situacao": c.situacao, "status": c.status,
            "data_admissao": c.data_admissao}


@router.post("/rh/colaboradores/{cid}/desligar")
def desligar(cid: uuid.UUID, payload: DesligamentoIn, db: Session = Depends(get_db),
             rh: UsuarioRH = Depends(requer_rh)) -> dict:
    c = _get_colab(db, cid)
    c.situacao = "desligado"
    c.status = StatusCandidato.desligado
    c.data_desligamento = payload.data_desligamento.strip() or None
    registrar(db, "colaborador_desligado", ator="rh", ator_detalhe=rh.email,
              candidato_id=c.id,
              detalhe={"nome": c.nome_completo, "data": c.data_desligamento})
    db.commit()
    return {"id": c.id, "situacao": c.situacao, "data_desligamento": c.data_desligamento}


@router.post("/rh/colaboradores/{cid}/transferir")
def transferir(cid: uuid.UUID, payload: TransferenciaIn, db: Session = Depends(get_db),
               rh: UsuarioRH = Depends(requer_rh)) -> dict:
    c = _get_colab(db, cid)
    posto = db.get(PostoServico, payload.posto_id)
    if posto is None:
        raise HTTPException(status_code=404, detail="posto_nao_encontrado")
    origem = str(c.posto_servico_id) if c.posto_servico_id else None
    c.posto_servico_id = posto.id
    # histórico de transferências guardado nos dados dinâmicos (sem nova tabela)
    hist = dict(c.dados_tirvu or {})
    linha = f"{payload.data_transferencia or datetime.now(timezone.utc).strftime('%d/%m/%Y')} -> {posto.nome}"
    hist["Transferências"] = (hist.get("Transferências", "") + "; " + linha).strip("; ")
    c.dados_tirvu = hist
    registrar(db, "colaborador_transferido", ator="rh", ator_detalhe=rh.email,
              candidato_id=c.id,
              detalhe={"nome": c.nome_completo, "de": origem, "para": str(posto.id)})
    db.commit()
    return {"id": c.id, "posto_servico_id": c.posto_servico_id, "posto_nome": posto.nome}
