"""Multi-signatário: um documento pode exigir a assinatura de VÁRIAS pessoas em
ordem de papéis (Contratado(a) → Testemunha → Contratante…).

Camada NOVA por cima da `Assinatura` (que continua sendo a via de UMA pessoa,
sem reescrita). Uma `SolicitacaoAssinatura` agrupa o documento + o roteiro; cada
`EtapaAssinatura` é um signatário (usuário do RH, externo, ou o candidato).

A etapa do candidato aponta para uma `Assinatura` DEDICADA (marcada com
`solicitacao_etapa_id` na própria Assinatura) — nunca reusa a assinatura de
fluxo livre do wizard (correção C1 da revisão: o dedup de `_registro` colidiria).
"""

import enum
import uuid
from datetime import datetime

from sqlalchemy import (JSON, Boolean, DateTime, Enum, ForeignKey, Integer,
                        String, Text, func)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class StatusSolicitacao(str, enum.Enum):
    rascunho = "rascunho"          # RH montando o roteiro
    aguardando = "aguardando"      # disparada; etapas assinando em ordem
    concluida = "concluida"        # todas assinaram; PDF final consolidado
    pendente_rh = "pendente_rh"    # uma etapa recusou; RH decide reatribuir
    cancelada = "cancelada"
    expirada = "expirada"


class TipoSignatario(str, enum.Enum):
    candidato = "candidato"        # o titular do link mágico (assina como hoje)
    usuario_rh = "usuario_rh"      # membro da equipe (assina logado, com senha)
    externo = "externo"            # terceiro (assina por link próprio + OTP)


class SolicitacaoAssinatura(Base):
    __tablename__ = "solicitacao_assinatura"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    candidato_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("candidato.id"), index=True)
    # documento fixo do enum OU documento de modelo (snapshot em titulo/corpo)
    documento: Mapped[str | None] = mapped_column(
        Enum("ficha_cadastro", "ficha_emergencia", "termo_vt",
             "acordo_confidencialidade", "oficio_cartao_cidadao",
             "informacoes_trabalhador", "termo_lgpd_infraero",
             "informativo_intermitente", "ficha_cadastral_terceirizado",
             "oficio_apresentacao_presidencia",
             name="documento_assinavel", create_type=False), nullable=True)
    modelo_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("modelo_documento.id"), nullable=True)
    titulo_doc: Mapped[str | None] = mapped_column(String(200))
    corpo_doc: Mapped[str | None] = mapped_column(Text)
    status: Mapped[StatusSolicitacao] = mapped_column(
        Enum(StatusSolicitacao, name="status_solicitacao"),
        default=StatusSolicitacao.rascunho)
    etapa_atual_ordem: Mapped[int] = mapped_column(Integer, default=0)
    pdf_final_key: Mapped[str | None] = mapped_column(String(300))
    hash_final_sha256: Mapped[str | None] = mapped_column(String(64))
    expira_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancelada_motivo: Mapped[str | None] = mapped_column(String(300))
    criada_por: Mapped[str | None] = mapped_column(String(120))
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    atualizado_em: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), onupdate=func.now())


class EtapaAssinatura(Base):
    __tablename__ = "etapa_assinatura"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    solicitacao_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("solicitacao_assinatura.id"), index=True)
    papel: Mapped[str] = mapped_column(String(60))   # snapshot do PapelAssinatura.nome
    ordem: Mapped[int] = mapped_column(Integer)
    tipo_signatario: Mapped[TipoSignatario] = mapped_column(
        Enum(TipoSignatario, name="tipo_signatario"))
    # exatamente um destes, conforme o tipo:
    assinatura_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("assinatura.id"), nullable=True)   # tipo=candidato
    usuario_rh_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("usuario_rh.id"), nullable=True)    # tipo=usuario_rh
    externo_nome: Mapped[str | None] = mapped_column(String(120))     # tipo=externo
    externo_email: Mapped[str | None] = mapped_column(String(180))
    externo_cpf: Mapped[str | None] = mapped_column(String(11))
    # link mágico próprio do externo (SHA-256 do token). Single-use: revogado ao
    # concluir/recusar (correção C2).
    token_hash: Mapped[str | None] = mapped_column(String(64), index=True)
    # 2FA do externo: sessão curta liberada só após validar o OTP (correção C2:
    # o PDF com dados pessoais só é servido após o 2º fator).
    otp_hash: Mapped[str | None] = mapped_column(String(64))
    otp_expira_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    otp_tentativas: Mapped[int] = mapped_column(Integer, default=0)
    otp_validado_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # evidências do ato de assinatura (preenchidas ao assinar)
    assinado_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # snapshot do assinante NO MOMENTO da assinatura (correção M5: o verificador
    # lê isto, não o registro vivo que pode ter mudado)
    assinante_nome: Mapped[str | None] = mapped_column(String(200))
    assinante_cpf: Mapped[str | None] = mapped_column(String(20))
    hash_sha256: Mapped[str | None] = mapped_column(String(64))
    pdf_key: Mapped[str | None] = mapped_column(String(300))
    ip: Mapped[str | None] = mapped_column(String(45))
    user_agent: Mapped[str | None] = mapped_column(String(400))
    prova_metodo: Mapped[str | None] = mapped_column(String(60))  # otp_email | senha_sessao_rh
    recusada_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    recusada_motivo: Mapped[str | None] = mapped_column(String(300))
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ModeloEtapaPadrao(Base):
    """Roteiro-padrão de PAPÉIS de um modelo (sem pessoas — as pessoas são
    escolhidas no disparo). Correção M9: nunca guardar usuario_rh_id fixo aqui,
    que apodrece quando a pessoa sai."""

    __tablename__ = "modelo_etapa_padrao"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    modelo_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("modelo_documento.id"), index=True)
    papel: Mapped[str] = mapped_column(String(60))
    ordem: Mapped[int] = mapped_column(Integer)
    tipo_sugerido: Mapped[TipoSignatario] = mapped_column(
        Enum(TipoSignatario, name="tipo_signatario"))
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AutorizacaoEquipe(Base):
    """Assinatura da equipe SEM correr atrás do diretor a cada documento
    (feedback do Bruno). NÃO é um PNG chumbado: é uma AUTORIZAÇÃO PRÉVIA
    REGISTRADA — um representante da empresa assina UMA vez (2FA), autorizando
    que sua assinatura conste nos documentos gerados a partir de um modelo, por
    um período. O documento diz 'emitido sob autorização permanente de X, ato N,
    data' — nunca 'X assinou este documento agora'."""

    __tablename__ = "autorizacao_equipe"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    modelo_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("modelo_documento.id"), index=True)
    nome: Mapped[str] = mapped_column(String(120))
    cargo: Mapped[str | None] = mapped_column(String(120))
    cpf: Mapped[str | None] = mapped_column(String(20))
    email: Mapped[str] = mapped_column(String(180))
    papel: Mapped[str] = mapped_column(String(60), default="Contratante")
    # evidências do ato de autorização (o representante confirmou por 2FA)
    autorizado_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    hash_sha256: Mapped[str | None] = mapped_column(String(64))
    ip: Mapped[str | None] = mapped_column(String(45))
    # janela de validade; None = sem prazo. Revogável a qualquer momento.
    validade_ate: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revogada_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # OTP para confirmar a autorização
    otp_hash: Mapped[str | None] = mapped_column(String(64))
    otp_expira_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    criado_por: Mapped[str | None] = mapped_column(String(120))
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
