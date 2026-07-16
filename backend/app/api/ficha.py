"""Autosave do formulário admissional, seção a seção.

Cada PUT grava só a seção enviada (campos parciais são permitidos — é autosave,
a validação de completude acontece na declaração final). O GET devolve o estado
inteiro para o front retomar de onde parou.
"""

import uuid
from datetime import date, datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.models.candidato import Candidato, StatusCandidato
from app.models.ficha import (
    ContatoEmergencia,
    CorRaca,
    DadosPessoais,
    DadosProfissionaisBancarios,
    Dependente,
    DocumentosIdentificacao,
    Endereco,
    Escolaridade,
    EstadoCivil,
    FichaEmergencia,
    IdentidadeGenero,
    Nacionalidade,
    Parentesco,
    Sexo,
    TipoChavePix,
    ValeTransporte,
)
from app.services.magic_link import resolver_token

router = APIRouter(tags=["ficha"])


def _candidato_do_token(token: str, db: Session) -> Candidato:
    candidato = resolver_token(db, token)
    if candidato is None:
        raise HTTPException(status_code=404, detail="link_invalido_ou_expirado")
    if candidato.status in (StatusCandidato.expurgado, StatusCandidato.aprovado):
        raise HTTPException(status_code=409, detail="admissao_encerrada")
    return candidato


def _marca_preenchendo(candidato: Candidato) -> None:
    if candidato.status == StatusCandidato.convidado:
        candidato.status = StatusCandidato.preenchendo


def _upsert(db: Session, model, candidato_id: uuid.UUID, dados: BaseModel):
    obj = db.get(model, candidato_id)
    if obj is None:
        obj = model(candidato_id=candidato_id)
        db.add(obj)
    for campo, valor in dados.model_dump(exclude_unset=True).items():
        setattr(obj, campo, valor)
    return obj


# ---------- Schemas (todos parciais: autosave) ----------


class SecaoPessoais(BaseModel):
    nome_completo: str | None = None
    nome_social: str | None = None
    nome_mae: str | None = None
    nome_pai: str | None = None
    email: EmailStr | None = None
    celular_whatsapp: str | None = None
    data_nascimento: date | None = None
    sexo: Sexo | None = None
    identidade_genero: IdentidadeGenero | None = None
    cor_raca: CorRaca | None = None
    nacionalidade: Nacionalidade | None = None
    naturalidade_cidade: str | None = None
    naturalidade_uf: str | None = None
    estado_civil: EstadoCivil | None = None
    escolaridade: Escolaridade | None = None
    pcd: bool | None = None


class SecaoEndereco(BaseModel):
    cep: str | None = None
    logradouro_numero_complemento: str | None = None
    bairro: str | None = None
    cidade: str | None = None
    uf: str | None = None


def _validar_cpf(v):
    from app.services.validacao import cpf_valido

    if v is None or v == "":
        return v
    numeros = "".join(c for c in str(v) if c.isdigit())
    if not cpf_valido(numeros):
        raise ValueError("Este CPF não existe: os dígitos verificadores não conferem. "
                         "Confira os números digitados.")
    return numeros


class SecaoDocumentos(BaseModel):
    rg_numero: str | None = None
    rg_orgao_emissor: str | None = None
    rg_data_expedicao: date | None = None
    cpf: str | None = None

    _cpf_ok = field_validator("cpf")(_validar_cpf)
    pis_nis_pasep: str | None = None
    cnh_numero: str | None = None
    cnh_categoria: str | None = None
    titulo_eleitor_numero: str | None = None
    titulo_eleitor_zona: str | None = None
    titulo_eleitor_secao: str | None = None


class SecaoTrabalhoBanco(BaseModel):
    tamanho_calca: str | None = None
    tamanho_camisa: str | None = None
    tamanho_calcado: str | None = None
    banco: str | None = None
    pix_tipo: TipoChavePix | None = None
    pix_chave: str | None = None


class DependenteIn(BaseModel):
    nome_completo: str
    data_nascimento: date
    cpf: str
    parentesco: Parentesco
    deduz_irrf: bool = False

    _cpf_ok = field_validator("cpf")(_validar_cpf)


class ContatoEmergenciaIn(BaseModel):
    nome_completo: str
    parentesco: str
    telefone_celular: str
    telefone_fixo_endereco: str | None = None


class SecaoVtEmergencia(BaseModel):
    vt_optante: bool | None = None
    vt_cartao_dftrans: str | None = None
    vt_trajeto_descricao: str | None = None
    # true = colaborador declara ciência de que, com endereço em GO e optante
    # de VT, a empresa solicitará o(s) cartão(ões) de mobilidade no CNPJ dela.
    vt_ciencia_cartao_go: bool | None = None
    tipo_sanguineo: str | None = None
    usa_medicamento_continuo: bool | None = None
    medicamentos: str | None = None
    condicoes_medicas: str | None = None
    orientacao_emergencia: str | None = None


# ---------- Endpoints ----------


@router.post("/c/{token}/aceite-lgpd", status_code=204)
def aceite_lgpd(token: str, db: Session = Depends(get_db)) -> None:
    candidato = _candidato_do_token(token, db)
    if candidato.aceite_lgpd_em is None:
        candidato.aceite_lgpd_em = datetime.now(timezone.utc)
    _marca_preenchendo(candidato)
    db.commit()


@router.put("/c/{token}/ficha/pessoais", status_code=204)
def salvar_pessoais(token: str, payload: SecaoPessoais, db: Session = Depends(get_db)) -> None:
    candidato = _candidato_do_token(token, db)
    basicos = payload.model_dump(exclude_unset=True)
    for campo in ("nome_completo", "email", "celular_whatsapp"):
        if campo in basicos:
            novo = basicos.pop(campo)
            antigo = getattr(candidato, campo)
            if campo in ("email", "celular_whatsapp") and antigo and novo != antigo:
                # Trilha de contato: o OTP de assinatura vai para este e-mail —
                # qualquer mudança fica registrada (antes → depois).
                from app.services.auditoria import registrar
                registrar(db, "contato_alterado", ator="candidato",
                          candidato_id=candidato.id,
                          detalhe={"campo": campo, "antes": antigo, "depois": novo})
            setattr(candidato, campo, novo)
    _upsert(db, DadosPessoais, candidato.id, SecaoPessoais(**basicos))
    _marca_preenchendo(candidato)
    db.commit()


@router.put("/c/{token}/ficha/endereco", status_code=204)
def salvar_endereco(token: str, payload: SecaoEndereco, db: Session = Depends(get_db)) -> None:
    candidato = _candidato_do_token(token, db)
    _upsert(db, Endereco, candidato.id, payload)
    _marca_preenchendo(candidato)
    db.commit()


@router.put("/c/{token}/ficha/documentos", status_code=204)
def salvar_documentos(token: str, payload: SecaoDocumentos, db: Session = Depends(get_db)) -> None:
    candidato = _candidato_do_token(token, db)
    _upsert(db, DocumentosIdentificacao, candidato.id, payload)
    _marca_preenchendo(candidato)
    db.commit()


@router.put("/c/{token}/ficha/trabalho-banco", status_code=204)
def salvar_trabalho_banco(
    token: str, payload: SecaoTrabalhoBanco, db: Session = Depends(get_db)
) -> None:
    candidato = _candidato_do_token(token, db)
    _upsert(db, DadosProfissionaisBancarios, candidato.id, payload)
    _marca_preenchendo(candidato)
    db.commit()


@router.put("/c/{token}/ficha/dependentes", status_code=204)
def salvar_dependentes(
    token: str, payload: list[DependenteIn], db: Session = Depends(get_db)
) -> None:
    """Substitui a lista inteira (o front sempre envia o conjunto atual)."""
    candidato = _candidato_do_token(token, db)
    for dep in db.scalars(select(Dependente).where(Dependente.candidato_id == candidato.id)):
        db.delete(dep)
    for dep in payload:
        db.add(Dependente(candidato_id=candidato.id, **dep.model_dump()))
    _marca_preenchendo(candidato)
    db.commit()


@router.put("/c/{token}/ficha/vt-emergencia", status_code=204)
def salvar_vt_emergencia(
    token: str, payload: SecaoVtEmergencia, db: Session = Depends(get_db)
) -> None:
    candidato = _candidato_do_token(token, db)
    dados = payload.model_dump(exclude_unset=True)
    vt = {k.removeprefix("vt_"): v for k, v in dados.items() if k.startswith("vt_")}
    emergencia = {k: v for k, v in dados.items() if not k.startswith("vt_")}
    if vt:
        obj = db.get(ValeTransporte, candidato.id) or ValeTransporte(candidato_id=candidato.id)
        db.add(obj)
        # A ciência é um carimbo de data, não um booleano regravável: marca uma
        # vez e não se desfaz desmarcando (evidência de que o aviso foi dado).
        ciente = vt.pop("ciencia_cartao_go", None)
        if ciente and obj.ciencia_cartao_go_em is None:
            obj.ciencia_cartao_go_em = datetime.now(timezone.utc)
        for campo, valor in vt.items():
            setattr(obj, campo, valor)
    if emergencia:
        obj = db.get(FichaEmergencia, candidato.id) or FichaEmergencia(candidato_id=candidato.id)
        db.add(obj)
        for campo, valor in emergencia.items():
            setattr(obj, campo, valor)
    _marca_preenchendo(candidato)
    db.commit()


@router.put("/c/{token}/ficha/contatos-emergencia", status_code=204)
def salvar_contatos(
    token: str, payload: list[ContatoEmergenciaIn], db: Session = Depends(get_db)
) -> None:
    candidato = _candidato_do_token(token, db)
    for c in db.scalars(
        select(ContatoEmergencia).where(ContatoEmergencia.candidato_id == candidato.id)
    ):
        db.delete(c)
    for i, contato in enumerate(payload, start=1):
        db.add(ContatoEmergencia(candidato_id=candidato.id, ordem=i, **contato.model_dump()))
    _marca_preenchendo(candidato)
    db.commit()


@router.get("/c/{token}/ficha")
def estado_ficha(token: str, db: Session = Depends(get_db)) -> dict:
    """Estado completo para o front retomar de onde parou."""
    candidato = _candidato_do_token(token, db)

    def _dump(obj) -> dict | None:
        if obj is None:
            return None
        return {
            c.name: getattr(obj, c.name)
            for c in obj.__table__.columns
            if c.name != "candidato_id"
        }

    dependentes = db.scalars(
        select(Dependente).where(Dependente.candidato_id == candidato.id)
    ).all()
    contatos = db.scalars(
        select(ContatoEmergencia)
        .where(ContatoEmergencia.candidato_id == candidato.id)
        .order_by(ContatoEmergencia.ordem)
    ).all()
    db.commit()
    return {
        "status": candidato.status,
        "aceite_lgpd_em": candidato.aceite_lgpd_em,
        "pessoais": {
            "nome_completo": candidato.nome_completo,
            "email": candidato.email,
            "celular_whatsapp": candidato.celular_whatsapp,
            **(_dump(db.get(DadosPessoais, candidato.id)) or {}),
        },
        "endereco": _dump(db.get(Endereco, candidato.id)),
        "documentos": _dump(db.get(DocumentosIdentificacao, candidato.id)),
        "trabalho_banco": _dump(db.get(DadosProfissionaisBancarios, candidato.id)),
        "dependentes": [_dump(d) for d in dependentes],
        "vt": _dump(db.get(ValeTransporte, candidato.id)),
        "emergencia": _dump(db.get(FichaEmergencia, candidato.id)),
        "contatos_emergencia": [_dump(c) for c in contatos],
    }


# ---------- Declaração final (Q50) ----------

_OBRIGATORIOS_PESSOAIS = (
    "data_nascimento", "sexo", "identidade_genero", "cor_raca", "nacionalidade",
    "naturalidade_cidade", "naturalidade_uf", "estado_civil", "escolaridade", "pcd",
)
_OBRIGATORIOS_DOCS = (
    "rg_numero", "rg_orgao_emissor", "rg_data_expedicao", "cpf", "pis_nis_pasep",
    "titulo_eleitor_numero", "titulo_eleitor_zona", "titulo_eleitor_secao",
)


@router.post("/c/{token}/ficha/declaracao")
def declarar_veracidade(token: str, db: Session = Depends(get_db)) -> dict:
    """Valida completude, registra a declaração (Q50) e avança para a assinatura."""
    candidato = _candidato_do_token(token, db)
    pendencias: list[str] = []

    if candidato.aceite_lgpd_em is None:
        pendencias.append("aceite_lgpd")

    # E-mail é opcional no convite, mas indispensável daqui em diante: o código
    # de assinatura eletrônica é enviado por ele.
    if not candidato.email:
        pendencias.append("pessoais.email")

    pessoais = db.get(DadosPessoais, candidato.id)
    for campo in _OBRIGATORIOS_PESSOAIS:
        if pessoais is None or getattr(pessoais, campo) is None:
            pendencias.append(f"pessoais.{campo}")

    endereco = db.get(Endereco, candidato.id)
    for campo in ("cep", "logradouro_numero_complemento", "bairro", "cidade", "uf"):
        if endereco is None or getattr(endereco, campo) is None:
            pendencias.append(f"endereco.{campo}")

    docs = db.get(DocumentosIdentificacao, candidato.id)
    for campo in _OBRIGATORIOS_DOCS:
        if docs is None or getattr(docs, campo) is None:
            pendencias.append(f"documentos.{campo}")

    banco = db.get(DadosProfissionaisBancarios, candidato.id)
    for campo in ("tamanho_calca", "tamanho_camisa", "tamanho_calcado", "banco",
                  "pix_tipo", "pix_chave"):
        if banco is None or getattr(banco, campo) is None:
            pendencias.append(f"trabalho_banco.{campo}")

    vt = db.get(ValeTransporte, candidato.id)
    if vt is None or vt.optante is None:
        pendencias.append("vt.optante")

    emergencia = db.get(FichaEmergencia, candidato.id)
    if emergencia is None or emergencia.usa_medicamento_continuo is None:
        pendencias.append("emergencia.usa_medicamento_continuo")
    if emergencia is None or not emergencia.condicoes_medicas:
        pendencias.append("emergencia.condicoes_medicas")

    contatos = db.scalars(
        select(ContatoEmergencia).where(ContatoEmergencia.candidato_id == candidato.id)
    ).first()
    if contatos is None:
        pendencias.append("contatos_emergencia")

    if pendencias:
        raise HTTPException(status_code=422, detail={"pendencias": pendencias})

    candidato.declaracao_veracidade_em = datetime.now(timezone.utc)
    candidato.status = StatusCandidato.aguardando_assinatura
    db.commit()
    return {"status": candidato.status}
