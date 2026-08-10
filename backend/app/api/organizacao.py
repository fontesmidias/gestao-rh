"""Empresas e jornadas de trabalho (integração com o Tirvu, leva 2026-07-19).

O RH escolhe OU cria na hora — por isso são tabelas com CRUD, não texto livre.
A importação lê a planilha "Escala de Trabalho - Detalhado" do Tirvu: cada ABA
é um posto (mesmos nomes da nossa base), a coluna E é a jornada. Traz todas as
descrições distintas SEM fusão automática — merge silencioso trocaria erros de
digitação visíveis ('ADICONAL') por associações erradas invisíveis. O import
relata quantas abas casaram com postos e quais não."""

import io
import re
import unicodedata
import uuid
import xml.etree.ElementTree as ET
import zipfile
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.auth_rh import exige, requer_rh
from app.core.db import get_db
from app.models.candidato import (Candidato, CargoTirvu, Empresa, Jornada,
                                  PostoServico)
from app.models.ficha import Endereco
from app.models.usuario_rh import UsuarioRH
from app.services.auditoria import registrar
from app.services.jornada_duplicidade import suspeitas as _dup_suspeitas
from app.services.jornada_parser import propor as _propor_jornada

router = APIRouter(tags=["organizacao-rh"], dependencies=[Depends(requer_rh)])

_NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
_NSR = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"


def _norm(txt: str) -> str:
    txt = unicodedata.normalize("NFKD", str(txt or "")).encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", txt).strip().lower()


# ======================================================================
# Empresas
# ======================================================================

class EmpresaIn(BaseModel):
    razao_social: str
    cnpj: str | None = None
    # ID desta empresa na base do Tirvu (o export de admissões casa por ID).
    tirvu_id: str | None = None


def _dump_empresa(e: Empresa) -> dict:
    return {"id": e.id, "razao_social": e.razao_social, "cnpj": e.cnpj,
            "tirvu_id": e.tirvu_id, "ativa": e.ativa}


@router.get("/rh/empresas")
def listar_empresas(db: Session = Depends(get_db),
    _rh: UsuarioRH = Depends(exige("organizacao:escrever"))) -> list[dict]:
    empresas = db.scalars(select(Empresa).order_by(Empresa.razao_social)).all()
    return [_dump_empresa(e) for e in empresas]


@router.post("/rh/empresas", status_code=201)
def criar_empresa(dados: EmpresaIn, db: Session = Depends(get_db),
                  rh: UsuarioRH = Depends(exige("organizacao:escrever"))) -> dict:
    nome = dados.razao_social.strip()
    if not nome:
        raise HTTPException(422, "Razão social obrigatória.")
    existente = db.scalar(select(Empresa).where(Empresa.razao_social.ilike(nome)))
    if existente:
        # "Criar" uma que já existe devolve a existente — o front usa este POST
        # no fluxo escolher-ou-criar sem se preocupar com corrida. Um tirvu_id
        # enviado junto NÃO se perde: preenche se ainda estiver vazio (B3).
        tid = (dados.tirvu_id or "").strip()
        if tid and not existente.tirvu_id:
            existente.tirvu_id = tid
            db.commit()
        return _dump_empresa(existente)
    emp = Empresa(razao_social=nome, cnpj=(dados.cnpj or "").strip() or None,
                  tirvu_id=(dados.tirvu_id or "").strip() or None)
    db.add(emp)
    registrar(db, "empresa_criada", ator="rh", ator_detalhe=rh.email,
              detalhe={"razao_social": nome})
    db.commit()
    return _dump_empresa(emp)


@router.put("/rh/empresas/{empresa_id}")
def editar_empresa(empresa_id: uuid.UUID, dados: EmpresaIn,
                   ativa: bool | None = None, db: Session = Depends(get_db),
                   rh: UsuarioRH = Depends(exige("organizacao:escrever"))) -> dict:
    emp = db.get(Empresa, empresa_id)
    if emp is None:
        raise HTTPException(404, "Empresa não encontrada")
    emp.razao_social = dados.razao_social.strip() or emp.razao_social
    emp.cnpj = (dados.cnpj or "").strip() or None
    emp.tirvu_id = (dados.tirvu_id or "").strip() or None
    if ativa is not None:
        emp.ativa = ativa
    registrar(db, "empresa_editada", ator="rh", ator_detalhe=rh.email,
              detalhe={"id": str(empresa_id)})
    db.commit()
    return _dump_empresa(emp)


# ======================================================================
# De-para de cargo → ID do Tirvu
# ======================================================================
# Cargo é texto livre no Candidato (não vira FK — quebraria cargo_alvo/Arquivo/
# provas). Este de-para lateral guarda o ID do Tirvu por cargo, usado SÓ no
# export. A tela lista os cargos JÁ USADOS na base (com contagem) para o RH
# atribuir o ID de cada um; casa por texto normalizado.

class CargoTirvuIn(BaseModel):
    cargo_rotulo: str
    tirvu_id: str


@router.get("/rh/cargos-tirvu")
def listar_cargos_tirvu(db: Session = Depends(get_db),
    _rh: UsuarioRH = Depends(exige("organizacao:ler"))) -> list[dict]:
    """Cargos usados na base × ID do Tirvu já cadastrado. Junta os cargos reais
    (Candidato.cargo_funcao, com contagem) ao de-para — o RH vê quem ainda não
    tem ID (o que faz o export sair zerado)."""
    from app.services.export_tirvu import normalizar_cargo
    mapa = {m.cargo_normalizado: m for m in db.scalars(select(CargoTirvu)).all()}
    # cargos reais em uso, com contagem
    usados: dict[str, dict] = {}
    for (cargo,) in db.execute(
            select(Candidato.cargo_funcao).where(Candidato.cargo_funcao.isnot(None))).all():
        chave = normalizar_cargo(cargo)
        if not chave:
            continue
        item = usados.setdefault(chave, {"cargo_rotulo": cargo.strip(), "qtd": 0})
        item["qtd"] += 1
    # inclui de-paras já cadastrados mesmo que ninguém use o cargo agora
    for chave, m in mapa.items():
        usados.setdefault(chave, {"cargo_rotulo": m.cargo_rotulo, "qtd": 0})
    saida = []
    for chave, info in sorted(usados.items(), key=lambda kv: (-kv[1]["qtd"], kv[0])):
        m = mapa.get(chave)
        saida.append({"cargo_normalizado": chave, "cargo_rotulo": info["cargo_rotulo"],
                      "qtd": info["qtd"], "id": m.id if m else None,
                      "tirvu_id": m.tirvu_id if m else None})
    return saida


@router.put("/rh/cargos-tirvu")
def salvar_cargo_tirvu(dados: CargoTirvuIn, db: Session = Depends(get_db),
                       rh: UsuarioRH = Depends(exige("organizacao:escrever"))) -> dict:
    """Upsert do de-para por texto de cargo. Enviar tirvu_id vazio REMOVE o
    mapeamento (o export volta a acusar pendência)."""
    from app.services.export_tirvu import normalizar_cargo
    chave = normalizar_cargo(dados.cargo_rotulo)
    if not chave:
        raise HTTPException(422, "Cargo obrigatório.")
    tid = (dados.tirvu_id or "").strip()
    m = db.scalar(select(CargoTirvu).where(CargoTirvu.cargo_normalizado == chave))
    if not tid:
        if m:
            db.delete(m)
            registrar(db, "cargo_tirvu_removido", ator="rh", ator_detalhe=rh.email,
                      detalhe={"cargo": dados.cargo_rotulo})
            db.commit()
        return {"cargo_normalizado": chave, "tirvu_id": None}
    if m:
        m.tirvu_id = tid
        m.cargo_rotulo = dados.cargo_rotulo.strip()
    else:
        m = CargoTirvu(cargo_normalizado=chave, cargo_rotulo=dados.cargo_rotulo.strip(),
                       tirvu_id=tid)
        db.add(m)
    registrar(db, "cargo_tirvu_salvo", ator="rh", ator_detalhe=rh.email,
              detalhe={"cargo": dados.cargo_rotulo, "tirvu_id": tid})
    db.commit()
    return {"id": m.id, "cargo_normalizado": chave, "cargo_rotulo": m.cargo_rotulo,
            "tirvu_id": m.tirvu_id}


# ======================================================================
# Jornadas
# ======================================================================

class JornadaIn(BaseModel):
    descricao: str
    posto_servico_id: uuid.UUID | None = None
    # ID desta jornada na base do Tirvu (o export de admissões casa por ID).
    tirvu_id: str | None = None
    # campos estruturados (opcionais; None = não mexer). O RH confirma a proposta
    # do parser ou edita à mão. A `descricao` continua canônica p/ o Tirvu.
    escala: str | None = None
    hora_entrada: str | None = None
    saida_almoco: str | None = None
    volta_almoco: str | None = None
    hora_saida: str | None = None
    bloco_secundario: str | None = None
    turno: str | None = None
    adicional_noturno: bool | None = None
    tem_intrajornada: bool | None = None
    intrajornada_obs: str | None = None
    cargo_relacionado: str | None = None


_CAMPOS_ESTRUT = ("escala", "hora_entrada", "saida_almoco", "volta_almoco",
                  "hora_saida", "bloco_secundario", "turno", "adicional_noturno",
                  "tem_intrajornada", "intrajornada_obs", "cargo_relacionado")


def _dump_jornada(j: Jornada) -> dict:
    return {
        "id": j.id, "descricao": j.descricao, "tirvu_id": j.tirvu_id,
        "posto_servico_id": j.posto_servico_id, "ativa": j.ativa,
        "escala": j.escala, "hora_entrada": j.hora_entrada,
        "saida_almoco": j.saida_almoco, "volta_almoco": j.volta_almoco,
        "hora_saida": j.hora_saida, "bloco_secundario": j.bloco_secundario,
        "turno": j.turno, "adicional_noturno": j.adicional_noturno,
        "tem_intrajornada": j.tem_intrajornada, "intrajornada_obs": j.intrajornada_obs,
        "cargo_relacionado": j.cargo_relacionado,
        "estruturado": j.estruturado_confirmado_em is not None,
    }


@router.get("/rh/jornadas")
def listar_jornadas(posto_id: uuid.UUID | None = None,
                    db: Session = Depends(get_db),
    _rh: UsuarioRH = Depends(exige("organizacao:escrever"))) -> list[dict]:
    """Todas as jornadas ativas. Com `posto_id`, as daquele posto vêm PRIMEIRO
    (ordenação, nunca filtro — jornada sem posto vale para todos e precisa
    continuar visível)."""
    jornadas = db.scalars(select(Jornada).where(Jornada.ativa)
                          .order_by(Jornada.descricao)).all()
    if posto_id:
        jornadas.sort(key=lambda j: (j.posto_servico_id != posto_id, j.descricao))
    return [_dump_jornada(j) for j in jornadas]


@router.post("/rh/jornadas", status_code=201)
def criar_jornada(dados: JornadaIn, db: Session = Depends(get_db),
                  rh: UsuarioRH = Depends(exige("organizacao:escrever"))) -> dict:
    desc = re.sub(r"\s+", " ", dados.descricao).strip()
    if not desc:
        raise HTTPException(422, "Descrição obrigatória.")
    existente = db.scalar(select(Jornada).where(Jornada.descricao.ilike(desc)))
    if existente:
        return _dump_jornada(existente)
    j = Jornada(descricao=desc, posto_servico_id=dados.posto_servico_id,
                tirvu_id=(dados.tirvu_id or "").strip() or None)
    # aplica campos estruturados enviados na criação (opcional)
    for campo in _CAMPOS_ESTRUT:
        valor = getattr(dados, campo)
        if valor is not None:
            setattr(j, campo, valor)
    db.add(j)
    registrar(db, "jornada_criada", ator="rh", ator_detalhe=rh.email,
              detalhe={"descricao": desc})
    db.commit()
    return _dump_jornada(j)


@router.put("/rh/jornadas/{jornada_id}")
def editar_jornada(jornada_id: uuid.UUID, dados: JornadaIn,
                   ativa: bool | None = None, confirmar_estrutura: bool = False,
                   db: Session = Depends(get_db),
                   rh: UsuarioRH = Depends(exige("organizacao:escrever"))) -> dict:
    """Edita a jornada. Os campos estruturados enviados (não-None) são gravados;
    com `confirmar_estrutura=true`, carimba a confirmação humana da estruturação
    (o RH validou a proposta do parser)."""
    j = db.get(Jornada, jornada_id)
    if j is None:
        raise HTTPException(404, "Jornada não encontrada")
    j.descricao = re.sub(r"\s+", " ", dados.descricao).strip() or j.descricao
    j.posto_servico_id = dados.posto_servico_id
    j.tirvu_id = (dados.tirvu_id or "").strip() or None
    # grava só os campos estruturados que vieram preenchidos (None = não mexe)
    for campo in _CAMPOS_ESTRUT:
        valor = getattr(dados, campo)
        if valor is not None:
            setattr(j, campo, valor)
    if confirmar_estrutura:
        j.estruturado_confirmado_em = datetime.now(timezone.utc)
    if ativa is not None:
        j.ativa = ativa
    registrar(db, "jornada_editada", ator="rh", ator_detalhe=rh.email,
              detalhe={"id": str(jornada_id), "confirmou_estrutura": confirmar_estrutura})
    db.commit()
    return _dump_jornada(j)


class ConfirmarLoteIn(BaseModel):
    # ids explícitos OU, se vazio, todas as de `confianca` (padrão: alta)
    jornada_ids: list[uuid.UUID] = []
    confianca: str = "alta"


@router.post("/rh/jornadas/confirmar-lote")
def confirmar_lote(payload: ConfirmarLoteIn, db: Session = Depends(get_db),
                   rh: UsuarioRH = Depends(exige("organizacao:escrever"))) -> dict:
    """Aplica a proposta do parser e carimba a confirmação em VÁRIAS jornadas.

    Medido nos dados reais (2026-07-28): das 269 jornadas da planilha de
    escalas, **86% saem com confiança ALTA** e o restante é 12X36 que o parser
    lê certo — não é ruído, é volume mesmo. Confirmar uma a uma são 325
    cliques para nada.

    Por que aqui o lote é seguro (e na tela de duplicidades não seria): isto
    grava METADADO INTERNO. A `descricao` canônica — a que vai ao Tirvu — não
    é tocada, e o RH pode reeditar qualquer campo depois. Fundir jornada, não:
    apaga um registro que alguém está usando.

    Ainda assim, o padrão é confirmar só as de ALTA confiança: as de média
    ficam para o olho humano, que é onde o parser erra.
    """
    consulta = select(Jornada).where(Jornada.estruturado_confirmado_em.is_(None))
    if payload.jornada_ids:
        consulta = consulta.where(Jornada.id.in_(payload.jornada_ids))
    pendentes = db.scalars(consulta).all()

    confirmadas, ignoradas = [], []
    for j in pendentes:
        proposta = _propor_jornada(j.descricao)
        # sem ids explícitos, respeita o filtro de confiança (não confirma no
        # escuro o que o parser não entendeu)
        if not payload.jornada_ids and proposta.get("confianca") != payload.confianca:
            ignoradas.append(str(j.id))
            continue
        for campo in _CAMPOS_ESTRUT:
            valor = proposta.get(campo)
            if valor is not None:
                setattr(j, campo, valor)
        j.estruturado_confirmado_em = datetime.now(timezone.utc)
        confirmadas.append(str(j.id))

    if confirmadas:
        registrar(db, "jornadas_confirmadas_lote", ator="rh", ator_detalhe=rh.email,
                  detalhe={"quantidade": len(confirmadas),
                           "confianca": payload.confianca if not payload.jornada_ids else "selecionadas"})
    db.commit()
    return {"confirmadas": len(confirmadas), "ignoradas": len(ignoradas)}


@router.get("/rh/jornadas-a-confirmar")
def jornadas_a_confirmar(db: Session = Depends(get_db),
                         _rh: UsuarioRH = Depends(exige("organizacao:ler"))) -> dict:
    """As pendentes de confirmação, já com a CONFIANÇA da proposta — é o que
    permite ao RH confirmar em lote só o que o parser entendeu bem."""
    pendentes = db.scalars(select(Jornada)
                           .where(Jornada.estruturado_confirmado_em.is_(None))
                           .order_by(Jornada.descricao)).all()
    saida, por_confianca = [], {"alta": 0, "media": 0, "baixa": 0}
    for j in pendentes:
        p = _propor_jornada(j.descricao)
        c = p.get("confianca", "baixa")
        por_confianca[c] = por_confianca.get(c, 0) + 1
        saida.append({"id": j.id, "descricao": j.descricao, "confianca": c,
                      "proposta": p})
    return {"jornadas": saida, "por_confianca": por_confianca,
            "total": len(pendentes)}


@router.delete("/rh/jornadas/{jornada_id}", status_code=204)
def excluir_jornada(jornada_id: uuid.UUID, db: Session = Depends(get_db),
                    rh: UsuarioRH = Depends(exige("organizacao:escrever"))):
    """Exclui a jornada. Se algum colaborador ainda a usa, recusa (o vínculo
    quebraria) — o RH desliga a jornada (`ativa=false`) ou reatribui antes."""
    j = db.get(Jornada, jornada_id)
    if j is None:
        raise HTTPException(404, "Jornada não encontrada")
    em_uso = db.scalar(select(Candidato).where(Candidato.jornada_id == jornada_id))
    if em_uso is not None:
        raise HTTPException(409, detail="jornada_em_uso")
    registrar(db, "jornada_excluida", ator="rh", ator_detalhe=rh.email,
              detalhe={"descricao": j.descricao})
    db.delete(j)
    db.commit()


@router.get("/rh/jornadas/{jornada_id}/proposta")
def proposta_jornada(jornada_id: uuid.UUID, db: Session = Depends(get_db),
                     _rh: UsuarioRH = Depends(exige("organizacao:escrever"))) -> dict:
    """Roda o parser sobre a descrição e devolve a PROPOSTA estruturada (não
    grava). O front mostra lado a lado com a descrição e o RH confirma/corrige."""
    j = db.get(Jornada, jornada_id)
    if j is None:
        raise HTTPException(404, "Jornada não encontrada")
    return {"jornada_id": j.id, "descricao": j.descricao,
            "proposta": _propor_jornada(j.descricao)}


@router.get("/rh/jornadas-duplicidades")
def jornadas_duplicidades(db: Session = Depends(get_db),
                          _rh: UsuarioRH = Depends(exige("organizacao:ler"))) -> list[dict]:
    """Pares de jornadas SUSPEITAS de duplicidade (grafias/typos diferentes) para
    o RH revisar. NUNCA funde — só sinaliza (regra dos ~40 erros de digitação).
    Rota com hífen (não `/jornadas/duplicidades`) para não colidir com
    `/jornadas/{id}` paramétrica."""
    jornadas = db.scalars(select(Jornada).where(Jornada.ativa)).all()
    por_desc = {j.descricao: j for j in jornadas}
    pares = _dup_suspeitas(list(por_desc.keys()))
    saida = []
    for p in pares:
        ja, jb = por_desc.get(p["a"]), por_desc.get(p["b"])
        if ja and jb:
            saida.append({**p, "id_a": ja.id, "id_b": jb.id})
    return saida


@router.post("/rh/jornadas/importar-planilha")
async def importar_jornadas(arquivo: UploadFile = File(...),
                            db: Session = Depends(get_db),
                            rh: UsuarioRH = Depends(exige("organizacao:escrever"))) -> dict:
    """Importa jornadas da planilha de colaboradores (.xlsx): coluna
    'Jornada de Trabalho' (a descrição CANÔNICA), casando o posto pela coluna
    'Lotação'. Idempotente por descrição normalizada (rodar 2x não duplica). Cada
    jornada nova nasce com a PROPOSTA do parser já aplicada, porém NÃO confirmada
    (`estruturado_confirmado_em` NULL) — o RH revisa e confirma depois."""
    from app.api.postos import _ler_linhas_xlsx
    try:
        conteudo = await arquivo.read()
    finally:
        await arquivo.close()
    linhas = _ler_linhas_xlsx(conteudo)
    if not linhas or len(linhas) < 2:
        raise HTTPException(422, detail="planilha_invalida")
    cab = [(c or "").strip().lower() for c in linhas[0]]

    def _idx(*nomes):
        for n in nomes:
            for i, c in enumerate(cab):
                if n in c:
                    return i
        return None

    ij = _idx("jornada de trabalho", "jornada")
    il = _idx("lotação", "lotacao")
    if ij is None:
        raise HTTPException(422, detail="sem_coluna_jornada")

    # cache de postos por nome normalizado, p/ casar a Lotação
    postos = db.scalars(select(PostoServico)).all()
    def _norm(s):
        s = "".join(c for c in unicodedata.normalize("NFKD", s or "")
                    if not unicodedata.combining(c)).upper()
        return re.sub(r"\s+", " ", s).strip()
    postos_por_nome = {_norm(p.nome): p for p in postos}
    # também casa por sigla, quando houver
    for p in postos:
        if p.sigla:
            postos_por_nome.setdefault(_norm(p.sigla), p)

    existentes = {_norm(j.descricao): j for j in db.scalars(select(Jornada)).all()}
    criadas = puladas = 0
    for linha in linhas[1:]:
        desc = re.sub(r"\s+", " ", (linha[ij] if ij < len(linha) else "") or "").strip()
        if not desc:
            continue
        if _norm(desc) in existentes:
            puladas += 1
            continue
        lot = _norm(linha[il]) if (il is not None and il < len(linha)) else ""
        posto = postos_por_nome.get(lot) if lot else None
        p = _propor_jornada(desc)
        j = Jornada(
            descricao=desc, posto_servico_id=(posto.id if posto else None),
            escala=p["escala"], hora_entrada=p["hora_entrada"],
            saida_almoco=p["saida_almoco"], volta_almoco=p["volta_almoco"],
            hora_saida=p["hora_saida"], bloco_secundario=p["bloco_secundario"],
            turno=p["turno"], adicional_noturno=p["adicional_noturno"],
            tem_intrajornada=p["tem_intrajornada"], intrajornada_obs=p["intrajornada_obs"],
            cargo_relacionado=p["cargo_relacionado"],
        )
        db.add(j)
        existentes[_norm(desc)] = j
        criadas += 1
    registrar(db, "jornadas_importadas", ator="rh", ator_detalhe=rh.email,
              detalhe={"criadas": criadas, "puladas": puladas})
    db.commit()
    return {"criadas": criadas, "puladas": puladas,
            "total_planilha": len(linhas) - 1}


# ======================================================================
# Backfill assistido de endereços (string única -> campos separados)
# ======================================================================
#
# O parser NUNCA grava sozinho: propõe, o RH confere original -> proposta e
# aprova (em lote os seguros, um a um os tortos). Endereço de Brasília
# ("QUADRA 3 CONJUNTO B CASA 12") derruba heurística — só propomos nos padrões
# em que dá para confiar; o resto fica "incerto" para o RH decidir.

_COMPL_FINAL = re.compile(
    r"^(?P<log>.+?)[\s,]+(?P<tipo>CASA|LOTE|LT|APTO|APARTAMENTO|AP|KM)\.?\s*"
    r"(?P<num>\d+\w?)\s*$", re.IGNORECASE)
_VIRGULA_NUM = re.compile(
    r"^(?P<log>.+?),\s*(?:n[º°o.]{0,2}\s*)?(?P<num>\d+\w?)\s*(?:[,–-]\s*(?P<compl>.+))?$",
    re.IGNORECASE)


def _propor_split(texto: str) -> dict | None:
    """Proposta de separação, ou None quando não há confiança."""
    t = re.sub(r"\s+", " ", texto or "").strip().rstrip(".")
    if not t:
        return None
    m = _VIRGULA_NUM.match(t)
    if m:
        return {"logradouro": m.group("log").strip(" ,"),
                "numero": m.group("num"),
                "complemento": (m.group("compl") or "").strip(" ,") or None}
    m = _COMPL_FINAL.match(t)
    if m:
        return {"logradouro": m.group("log").strip(" ,"),
                "numero": m.group("num"),
                "complemento": m.group("tipo").upper()}
    return None


@router.get("/rh/enderecos-backfill")
def listar_backfill(db: Session = Depends(get_db),
    _rh: UsuarioRH = Depends(exige("admissao:escrever"))) -> dict:
    """Endereços ainda na string única, com a proposta do parser (ou sem, se
    incerto). O RH aprova/edita na tela; nada muda sem confirmação."""
    pendentes = db.scalars(
        select(Endereco).where(Endereco.logradouro_numero_complemento.is_not(None),
                               Endereco.logradouro.is_(None))).all()
    itens = []
    for e in pendentes:
        cand = db.get(Candidato, e.candidato_id)
        itens.append({
            "candidato_id": e.candidato_id,
            "nome": cand.nome_completo if cand else "?",
            "original": e.logradouro_numero_complemento,
            "proposta": _propor_split(e.logradouro_numero_complemento),
        })
    com = sum(1 for i in itens if i["proposta"])
    return {"total": len(itens), "com_proposta": com, "itens": itens}


class BackfillItem(BaseModel):
    candidato_id: uuid.UUID
    logradouro: str
    numero: str
    complemento: str | None = None


@router.post("/rh/enderecos-backfill")
def aplicar_backfill(itens: list[BackfillItem], db: Session = Depends(get_db),
                     rh: UsuarioRH = Depends(exige("admissao:escrever"))) -> dict:
    """Grava as separações CONFIRMADAS pelo RH. A string original permanece
    intacta (evidência do que a pessoa declarou); a ficha só troca de layout
    para quem tiver os campos novos preenchidos."""
    aplicados = 0
    for item in itens:
        e = db.get(Endereco, item.candidato_id)
        if e is None or not item.logradouro.strip() or not item.numero.strip():
            continue
        e.logradouro = item.logradouro.strip()
        e.numero = item.numero.strip()
        e.complemento = (item.complemento or "").strip() or None
        aplicados += 1
    registrar(db, "enderecos_backfill", ator="rh", ator_detalhe=rh.email,
              detalhe={"aplicados": aplicados, "recebidos": len(itens)})
    db.commit()
    return {"aplicados": aplicados}


# ======================================================================
# Importação da planilha de escalas do Tirvu
# ======================================================================

def _abas_com_jornadas(conteudo: bytes) -> list[tuple[str, set[str]]] | None:
    """Lê TODAS as abas do xlsx (zip+XML puro, imune ao openpyxl quebrar com
    planilha do Tirvu) e devolve [(nome_da_aba, {descrições da coluna E})].
    A coluna certa é achada pelo cabeçalho 'Jornada', não por posição fixa."""
    try:
        z = zipfile.ZipFile(io.BytesIO(conteudo))
    except Exception:
        return None
    try:
        wb = ET.fromstring(z.read("xl/workbook.xml"))
        rels = ET.fromstring(z.read("xl/_rels/workbook.xml.rels"))
    except KeyError:
        return None
    alvo_por_rid = {
        r.get("Id"): "xl/" + r.get("Target", "").lstrip("/")
        for r in rels
        if "worksheet" in (r.get("Type") or "")
    }
    resultado: list[tuple[str, set[str]]] = []
    for sheet in wb.iter(f"{_NS}sheet"):
        nome = sheet.get("name") or ""
        caminho = alvo_por_rid.get(sheet.get(f"{_NSR}id"))
        if not caminho or caminho not in z.namelist():
            continue
        raiz = ET.fromstring(z.read(caminho))
        col_jornada: str | None = None
        jornadas: set[str] = set()
        for row in raiz.iter(f"{_NS}row"):
            for c in row.findall(f"{_NS}c"):
                ref = c.get("r", "")
                col = "".join(ch for ch in ref if ch.isalpha())
                v = c.find(f"{_NS}v")
                texto = (v.text or "").strip() if v is not None else ""
                if col_jornada is None:
                    if _norm(texto) == "jornada":
                        col_jornada = col
                elif col == col_jornada and texto:
                    jornadas.add(re.sub(r"\s+", " ", texto).strip())
        resultado.append((nome, jornadas))
    return resultado


@router.post("/rh/jornadas/importar")
async def importar_jornadas(arquivo: UploadFile, db: Session = Depends(get_db),
                            rh: UsuarioRH = Depends(exige("organizacao:escrever"))) -> dict:
    """Importa jornadas da planilha de escalas do Tirvu (uma aba por posto).
    Idempotente por descrição exata; NUNCA funde descrições parecidas. Casa a
    aba com um posto por nome normalizado e relata o que não casou. O arquivo
    é descartado após o processamento (nada persiste — regra transversal de
    uploads do RH)."""
    try:
        conteudo = await arquivo.read()
        abas = _abas_com_jornadas(conteudo)
    finally:
        await arquivo.close()  # fecha e descarta o spool em disco do Starlette
    if abas is None:
        raise HTTPException(422, "arquivo_invalido")
    if not abas:
        raise HTTPException(422, "planilha_vazia")

    postos = db.scalars(select(PostoServico)).all()
    posto_por_nome = {_norm(p.nome): p for p in postos}
    existentes = {_norm(j.descricao): j for j in db.scalars(select(Jornada)).all()}

    criadas = 0
    abas_casadas: list[str] = []
    abas_sem_posto: list[str] = []
    for nome_aba, descricoes in abas:
        posto = posto_por_nome.get(_norm(nome_aba))
        if not descricoes:
            continue  # aba sem coluna Jornada (capa, resumo) não conta no relato
        (abas_casadas if posto else abas_sem_posto).append(nome_aba)
        for desc in sorted(descricoes):
            chave = _norm(desc)
            ja = existentes.get(chave)
            if ja is not None:
                # já existe: só adota o posto se ela ainda não tinha nenhum
                if ja.posto_servico_id is None and posto is not None:
                    ja.posto_servico_id = posto.id
                continue
            nova = Jornada(descricao=desc,
                           posto_servico_id=posto.id if posto else None)
            db.add(nova)
            existentes[chave] = nova
            criadas += 1

    registrar(db, "jornadas_importadas", ator="rh", ator_detalhe=rh.email,
              detalhe={"criadas": criadas, "abas_casadas": len(abas_casadas),
                       "abas_sem_posto": abas_sem_posto})
    db.commit()
    return {
        "jornadas_criadas": criadas,
        "abas_processadas": len(abas_casadas) + len(abas_sem_posto),
        "abas_casadas_com_posto": len(abas_casadas),
        "abas_sem_posto": abas_sem_posto,
    }


# ======================================================================
# Padronização em massa: cargos e jornadas colados da tela do Tirvu
# (feedback de campo 2026-07-27) — preview PROPÕE, o RH confirma linha a
# linha, nunca grava sozinho (mesma regra da Incidência de Benefícios).
# Ver docs/planejamento/09-roadmap-feedbacks-16a-leva.md, item A2.
# ======================================================================

class TxtIn(BaseModel):
    texto: str


async def _texto_do_upload(arquivo: UploadFile) -> str:
    """Bytes do .txt enviado, decodificados e com o spool em disco fechado.

    O `close()` no finally é regra da casa: o Starlette faz spool em disco
    acima de ~1MB, e o arquivo de jornadas reais tem 110 KB hoje mas cresce —
    temp file esquecido no container é dado do RH parado onde ninguém olha.
    """
    from app.services.importar_tirvu_txt import decodificar
    try:
        return decodificar(await arquivo.read())
    finally:
        await arquivo.close()


@router.post("/rh/tirvu-txt/preview-cargos-arquivo")
async def preview_cargos_arquivo(arquivo: UploadFile, db: Session = Depends(get_db),
                                 _rh: UsuarioRH = Depends(exige("organizacao:escrever"))) -> dict:
    """Mesmo preview de cargos, a partir do .txt salvo pelo RH.

    O Tirvu não tem botão de exportar cargos: o RH seleciona a tela inteira,
    cola no Bloco de Notas e salva. Subir o arquivo evita o passo de colar num
    campo de texto — e o resultado é o MESMO preview, porque continua valendo
    a regra da casa: propor, nunca gravar sozinho.
    """
    return preview_cargos_tirvu(TxtIn(texto=await _texto_do_upload(arquivo)), db)


@router.post("/rh/tirvu-txt/preview-jornadas-arquivo")
async def preview_jornadas_arquivo(arquivo: UploadFile, db: Session = Depends(get_db),
                                   _rh: UsuarioRH = Depends(exige("organizacao:escrever"))) -> dict:
    """Mesmo preview de jornadas, a partir do .txt salvo pelo RH."""
    return preview_jornadas_tirvu(TxtIn(texto=await _texto_do_upload(arquivo)), db)


@router.post("/rh/tirvu-txt/preview-cargos")
def preview_cargos_tirvu(dados: TxtIn, db: Session = Depends(get_db),
    _rh: UsuarioRH = Depends(exige("organizacao:escrever"))) -> dict:
    """Lê o texto colado da tela 'Cargos' do Tirvu e PROPÕE o de-para —
    não grava nada. Sinaliza cópia parcial (contagem do cabeçalho) e cargos
    homônimos com 2+ IDs ativos (o RH decide qual usar; nunca funde
    sozinho)."""
    from app.services.export_tirvu import normalizar_cargo
    from app.services.importar_tirvu_txt import (ContagemInvalida,
                                                  detectar_homonimos_cargo,
                                                  normalizar_texto,
                                                  parsear_cargos)

    try:
        itens = parsear_cargos(dados.texto)
    except ContagemInvalida as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if not itens:
        raise HTTPException(status_code=422, detail="nenhum_registro_encontrado")

    homonimos = {g.chave_normalizada for g in detectar_homonimos_cargo(itens)}
    existentes = {m.cargo_normalizado: m for m in db.scalars(select(CargoTirvu)).all()}
    # Quantas pessoas usam cada cargo hoje — para o RH priorizar a revisão
    # (o caso grave é o homônimo com muita gente na base, não o sem uso).
    contagem_uso: dict[str, int] = {}
    for (cargo,) in db.execute(
            select(Candidato.cargo_funcao).where(Candidato.cargo_funcao.isnot(None))).all():
        chave = normalizar_cargo(cargo)
        if chave:
            contagem_uso[chave] = contagem_uso.get(chave, 0) + 1

    propostas = []
    for it in itens:
        if it.status != "ATIVO":
            continue  # inativo no Tirvu nunca é proposto — mesmo raciocínio do R3
        chave = normalizar_texto(it.cargo)
        atual = existentes.get(chave)
        propostas.append({
            "tirvu_id": it.tirvu_id, "cargo": it.cargo, "cbo": it.cbo,
            "chave_normalizada": chave,
            "tirvu_id_atual": atual.tirvu_id if atual else None,
            "diverge": bool(atual and atual.tirvu_id != it.tirvu_id),
            "homonimo": chave in homonimos,
            "pessoas_usando": contagem_uso.get(chave, 0),
            # sugerido para auto-aplicar SE não houver ambiguidade nem
            # divergência com o que já está gravado à mão
            "aplicar_sugerido": chave not in homonimos and not (atual and atual.tirvu_id != it.tirvu_id),
        })
    return {"total": len(itens), "ativos": len(propostas),
            "homonimos": len(homonimos), "propostas": propostas}


class ConfirmarCargoItem(BaseModel):
    tirvu_id: str
    cargo: str
    # CBO vem do próprio arquivo do Tirvu. Guardar é o que permite, depois,
    # distinguir os homônimos ("AUXILIAR DE SERVIÇOS GERAIS" 514225 x 763125)
    # na hora de decidir — sem ele a tela pede escolha sem mostrar a diferença.
    cbo: str = ""
    aplicar: bool = True


class ConfirmarCargosIn(BaseModel):
    itens: list[ConfirmarCargoItem]


@router.post("/rh/tirvu-txt/confirmar-cargos")
def confirmar_cargos_tirvu(dados: ConfirmarCargosIn, db: Session = Depends(get_db),
                           rh: UsuarioRH = Depends(exige("organizacao:escrever"))) -> dict:
    """Grava SÓ os itens com aplicar=True — a revisão humana já aconteceu no
    front (preview + decisão linha a linha)."""
    from app.services.export_tirvu import normalizar_cargo

    gravados = 0
    for item in dados.itens:
        if not item.aplicar:
            continue
        chave = normalizar_cargo(item.cargo)
        if not chave:
            continue
        cbo = (item.cbo or "").strip()[:10] or None
        m = db.scalar(select(CargoTirvu).where(CargoTirvu.cargo_normalizado == chave))
        if m:
            m.tirvu_id = item.tirvu_id
            m.cargo_rotulo = item.cargo.strip()
            # CBO vazio não apaga o que já estava gravado: o arquivo pode vir
            # sem a coluna, e perder dado por omissão é pior que não atualizar.
            if cbo:
                m.cbo = cbo
        else:
            db.add(CargoTirvu(cargo_normalizado=chave, cargo_rotulo=item.cargo.strip(),
                              tirvu_id=item.tirvu_id, cbo=cbo))
        gravados += 1
    registrar(db, "cargos_tirvu_importados_em_massa", ator="rh", ator_detalhe=rh.email,
              detalhe={"gravados": gravados, "total_enviado": len(dados.itens)})
    db.commit()
    return {"gravados": gravados}


@router.post("/rh/tirvu-txt/preview-jornadas")
def preview_jornadas_tirvu(dados: TxtIn, db: Session = Depends(get_db),
    _rh: UsuarioRH = Depends(exige("organizacao:escrever"))) -> dict:
    """Lê o texto colado da tela 'Jornadas' do Tirvu e PROPÕE o de-para de
    tirvu_id — não grava nada. Casa por descrição já limpa da sujeira de
    'vínculos'; sinaliza duplicatas (nunca funde sozinho)."""
    from app.services.importar_tirvu_txt import (ContagemInvalida,
                                                  detectar_duplicatas_jornada,
                                                  normalizar_texto,
                                                  parsear_jornadas)

    try:
        itens = parsear_jornadas(dados.texto)
    except ContagemInvalida as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if not itens:
        raise HTTPException(status_code=422, detail="nenhum_registro_encontrado")

    duplicatas = {g.chave_normalizada for g in detectar_duplicatas_jornada(itens)}
    existentes = {_norm(j.descricao): j for j in db.scalars(select(Jornada)).all()}

    propostas = []
    for it in itens:
        chave_norm = normalizar_texto(it.descricao)
        atual = existentes.get(_norm(it.descricao))
        propostas.append({
            "tirvu_id": it.tirvu_id, "descricao": it.descricao,
            "escala": it.escala, "tratamento": it.tratamento,
            "existe_na_base": atual is not None,
            "tirvu_id_atual": atual.tirvu_id if atual else None,
            "diverge": bool(atual and atual.tirvu_id and atual.tirvu_id != it.tirvu_id),
            "duplicata": chave_norm in duplicatas,
            "aplicar_sugerido": chave_norm not in duplicatas
                and not (atual and atual.tirvu_id and atual.tirvu_id != it.tirvu_id),
        })
    return {"total": len(itens), "duplicatas": len(duplicatas), "propostas": propostas}


class ConfirmarJornadaItem(BaseModel):
    tirvu_id: str
    descricao: str
    escala: str = ""
    tratamento: str = ""
    aplicar: bool = True


class ConfirmarJornadasIn(BaseModel):
    itens: list[ConfirmarJornadaItem]


@router.post("/rh/tirvu-txt/confirmar-jornadas")
def confirmar_jornadas_tirvu(dados: ConfirmarJornadasIn, db: Session = Depends(get_db),
                             rh: UsuarioRH = Depends(exige("organizacao:escrever"))) -> dict:
    """Grava SÓ os itens com aplicar=True: se a jornada já existe (por
    descrição normalizada), atualiza o tirvu_id; senão CRIA a jornada nova com
    a descrição já limpa e o tirvu_id. Nunca funde duas descrições
    diferentes."""
    existentes = {_norm(j.descricao): j for j in db.scalars(select(Jornada)).all()}
    criadas = 0
    atualizadas = 0
    for item in dados.itens:
        if not item.aplicar:
            continue
        descricao = item.descricao.strip()
        if not descricao:
            continue
        # Escala e tratamento vêm da lista do Tirvu junto do ID. Vazio não
        # apaga o que já existe, mesma regra do CBO.
        escala = (item.escala or "").strip()[:40] or None
        tratamento = (item.tratamento or "").strip()[:60] or None
        atual = existentes.get(_norm(descricao))
        if atual:
            mudou = False
            if atual.tirvu_id != item.tirvu_id:
                atual.tirvu_id = item.tirvu_id
                mudou = True
            if escala and atual.tirvu_escala != escala:
                atual.tirvu_escala = escala
                mudou = True
            if tratamento and atual.tirvu_tratamento != tratamento:
                atual.tirvu_tratamento = tratamento
                mudou = True
            if mudou:
                atualizadas += 1
        else:
            nova = Jornada(descricao=descricao, tirvu_id=item.tirvu_id,
                           tirvu_escala=escala, tirvu_tratamento=tratamento)
            db.add(nova)
            existentes[_norm(descricao)] = nova
            criadas += 1
    registrar(db, "jornadas_tirvu_importadas_em_massa", ator="rh", ator_detalhe=rh.email,
              detalhe={"criadas": criadas, "atualizadas": atualizadas,
                       "total_enviado": len(dados.itens)})
    db.commit()
    return {"criadas": criadas, "atualizadas": atualizadas}
