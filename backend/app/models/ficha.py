"""Entidades do formulário admissional (ver docs/planejamento/02-modelo-de-dados.md)."""

import enum
import uuid
from datetime import date, datetime

from sqlalchemy import (Boolean, Date, DateTime, Enum, ForeignKey, SmallInteger,
                        String, Text)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class Sexo(str, enum.Enum):
    feminino = "feminino"
    masculino = "masculino"


class IdentidadeGenero(str, enum.Enum):
    cisgenero = "cisgenero"
    transgenero = "transgenero"
    transexual = "transexual"
    travesti = "travesti"
    genero_fluido = "genero_fluido"
    agenero = "agenero"
    nao_informar = "nao_informar"


class CorRaca(str, enum.Enum):
    branca = "branca"
    preta = "preta"
    parda = "parda"
    amarela = "amarela"
    indigena = "indigena"


class Nacionalidade(str, enum.Enum):
    brasileira = "brasileira"
    estrangeira = "estrangeira"


class EstadoCivil(str, enum.Enum):
    solteiro = "solteiro"
    casado = "casado"
    uniao_estavel = "uniao_estavel"
    divorciado = "divorciado"
    separado = "separado"
    viuvo = "viuvo"


class Escolaridade(str, enum.Enum):
    fund_incompleto = "fund_incompleto"
    fund_completo = "fund_completo"
    medio_incompleto = "medio_incompleto"
    medio_completo = "medio_completo"
    sup_incompleto = "sup_incompleto"
    sup_completo = "sup_completo"
    pos_graduacao = "pos_graduacao"


class TipoChavePix(str, enum.Enum):
    cpf = "cpf"
    celular = "celular"
    email = "email"
    aleatoria = "aleatoria"


class Parentesco(str, enum.Enum):
    conjuge = "conjuge"
    filho = "filho"
    menor_guarda = "menor_guarda"


class DadosPessoais(Base):
    """Complemento 1:1 do Candidato — seção 'Você' do wizard (dados além de nome/e-mail/celular)."""

    __tablename__ = "dados_pessoais"

    candidato_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("candidato.id"), primary_key=True
    )
    # Nome social (Decreto 8.727/2016): usado nos documentos junto ao nome civil.
    nome_social: Mapped[str | None] = mapped_column(String(200))
    # Filiação: pai pode não constar do registro (não declarado) — nunca obrigar.
    nome_mae: Mapped[str | None] = mapped_column(String(200))
    nome_pai: Mapped[str | None] = mapped_column(String(200))
    data_nascimento: Mapped[date | None] = mapped_column(Date)
    sexo: Mapped[Sexo | None] = mapped_column(Enum(Sexo, name="sexo"))
    identidade_genero: Mapped[IdentidadeGenero | None] = mapped_column(
        Enum(IdentidadeGenero, name="identidade_genero")
    )
    # Acesso restrito (LGPD art. 11): exibido ao RH apenas com registro em auditoria.
    cor_raca: Mapped[CorRaca | None] = mapped_column(Enum(CorRaca, name="cor_raca"))
    nacionalidade: Mapped[Nacionalidade | None] = mapped_column(
        Enum(Nacionalidade, name="nacionalidade")
    )
    naturalidade_cidade: Mapped[str | None] = mapped_column(String(120))
    naturalidade_uf: Mapped[str | None] = mapped_column(String(2))
    estado_civil: Mapped[EstadoCivil | None] = mapped_column(Enum(EstadoCivil, name="estado_civil"))
    escolaridade: Mapped[Escolaridade | None] = mapped_column(
        Enum(Escolaridade, name="escolaridade")
    )
    pcd: Mapped[bool | None] = mapped_column(Boolean)


class Endereco(Base):
    __tablename__ = "endereco"

    candidato_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("candidato.id"), primary_key=True)
    cep: Mapped[str | None] = mapped_column(String(8))
    logradouro_numero_complemento: Mapped[str | None] = mapped_column(String(300))
    bairro: Mapped[str | None] = mapped_column(String(120))
    cidade: Mapped[str | None] = mapped_column(String(120))
    uf: Mapped[str | None] = mapped_column(String(2))


class DocumentosIdentificacao(Base):
    __tablename__ = "documentos_identificacao"

    candidato_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("candidato.id"), primary_key=True)
    rg_numero: Mapped[str | None] = mapped_column(String(20))
    rg_orgao_emissor: Mapped[str | None] = mapped_column(String(40))
    rg_data_expedicao: Mapped[date | None] = mapped_column(Date)
    cpf: Mapped[str | None] = mapped_column(String(11))
    pis_nis_pasep: Mapped[str | None] = mapped_column(String(14))
    cnh_numero: Mapped[str | None] = mapped_column(String(20))
    cnh_categoria: Mapped[str | None] = mapped_column(String(5))
    titulo_eleitor_numero: Mapped[str | None] = mapped_column(String(14))
    titulo_eleitor_zona: Mapped[str | None] = mapped_column(String(6))
    titulo_eleitor_secao: Mapped[str | None] = mapped_column(String(6))


class DadosProfissionaisBancarios(Base):
    __tablename__ = "dados_profissionais_bancarios"

    candidato_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("candidato.id"), primary_key=True)
    tamanho_calca: Mapped[str | None] = mapped_column(String(10))
    tamanho_camisa: Mapped[str | None] = mapped_column(String(10))
    tamanho_calcado: Mapped[str | None] = mapped_column(String(10))
    banco: Mapped[str | None] = mapped_column(String(120))
    pix_tipo: Mapped[TipoChavePix | None] = mapped_column(Enum(TipoChavePix, name="tipo_chave_pix"))
    pix_chave: Mapped[str | None] = mapped_column(String(200))


class Dependente(Base):
    __tablename__ = "dependente"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    candidato_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("candidato.id"), index=True)
    nome_completo: Mapped[str] = mapped_column(String(200))
    data_nascimento: Mapped[date] = mapped_column(Date)
    cpf: Mapped[str] = mapped_column(String(11))
    parentesco: Mapped[Parentesco] = mapped_column(Enum(Parentesco, name="parentesco"))
    deduz_irrf: Mapped[bool] = mapped_column(Boolean, default=False)


class ValeTransporte(Base):
    __tablename__ = "vale_transporte"

    candidato_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("candidato.id"), primary_key=True)
    optante: Mapped[bool | None] = mapped_column(Boolean)
    cartao_dftrans: Mapped[str | None] = mapped_column(String(40))
    trajeto_descricao: Mapped[str | None] = mapped_column(Text)
    # Endereço em Goiás + optante de VT: a empresa solicita o(s) cartão(ões) de
    # mobilidade (ex.: UTB) vinculados ao CNPJ — regra, não opção. Aqui fica o
    # registro de QUANDO o colaborador declarou ciência disso.
    ciencia_cartao_go_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class FichaEmergencia(Base):
    """Dados de saúde — acesso restrito (LGPD art. 11, II 'a' e 'e')."""

    __tablename__ = "ficha_emergencia"

    candidato_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("candidato.id"), primary_key=True)
    tipo_sanguineo: Mapped[str | None] = mapped_column(String(4))
    usa_medicamento_continuo: Mapped[bool | None] = mapped_column(Boolean)
    medicamentos: Mapped[str | None] = mapped_column(Text)
    condicoes_medicas: Mapped[str | None] = mapped_column(Text)
    orientacao_emergencia: Mapped[str | None] = mapped_column(Text)


class ContatoEmergencia(Base):
    __tablename__ = "contato_emergencia"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    candidato_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("candidato.id"), index=True)
    ordem: Mapped[int] = mapped_column(SmallInteger, default=1)
    nome_completo: Mapped[str] = mapped_column(String(200))
    parentesco: Mapped[str] = mapped_column(String(60))
    telefone_celular: Mapped[str] = mapped_column(String(20))
    telefone_fixo_endereco: Mapped[str | None] = mapped_column(String(300))
