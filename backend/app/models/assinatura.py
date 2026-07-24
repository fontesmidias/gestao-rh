import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class DocumentoAssinavel(str, enum.Enum):
    # Fichas da admissão (todo candidato)
    ficha_cadastro = "ficha_cadastro"
    ficha_emergencia = "ficha_emergencia"
    termo_vt = "termo_vt"
    acordo_confidencialidade = "acordo_confidencialidade"
    # Documentos por posto de serviço (gerados quando o RH marca o posto)
    oficio_cartao_cidadao = "oficio_cartao_cidadao"
    informacoes_trabalhador = "informacoes_trabalhador"
    termo_lgpd_infraero = "termo_lgpd_infraero"
    # Ficha de integração do intermitente (só quando o regime é intermitente)
    informativo_intermitente = "informativo_intermitente"
    # Kit específico da Presidência da República
    ficha_cadastral_terceirizado = "ficha_cadastral_terceirizado"
    oficio_apresentacao_presidencia = "oficio_apresentacao_presidencia"
    # Autodeclaração de residência: comprovante em nome de terceiro (só quando
    # o candidato informa titular+relação do comprovante).
    autodeclaracao_residencia = "autodeclaracao_residencia"


# Fichas exigidas de TODO candidato; os demais só existem se o RH os gerar.
# O acordo de confidencialidade entrou em 2026-07-16 e vale RETROATIVAMENTE:
# como a exigência é derivada desta tupla (não de registros pré-criados),
# quem ainda não assinou passa a dever a assinatura automaticamente.
FICHAS_BASE = (DocumentoAssinavel.ficha_cadastro, DocumentoAssinavel.ficha_emergencia,
               DocumentoAssinavel.termo_vt, DocumentoAssinavel.acordo_confidencialidade)


class Assinatura(Base):
    """Assinatura eletrônica simples (Lei 14.063/2020) com trilha de evidências."""

    __tablename__ = "assinatura"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    candidato_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("candidato.id"), index=True)
    # Documento fixo do sistema (enum) OU documento de modelo do RH (modelo_id).
    # Exatamente um dos dois é preenchido.
    documento: Mapped[DocumentoAssinavel | None] = mapped_column(
        Enum(DocumentoAssinavel, name="documento_assinavel"), nullable=True
    )
    modelo_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("modelo_documento.id"), nullable=True)
    # Snapshot do modelo no momento do envio para assinatura: edições/exclusões
    # posteriores do modelo NÃO mudam o que a pessoa assina.
    titulo_doc: Mapped[str | None] = mapped_column(String(200))
    corpo_doc: Mapped[str | None] = mapped_column(Text)
    # Papel do signatário no manifesto (Contratado(a), Testemunha…) — dos
    # papéis cadastrados em Configurações → Assinaturas.
    papel: Mapped[str | None] = mapped_column(String(60))
    # Quando esta Assinatura é a via do candidato DENTRO de um roteiro
    # multi-signatário, aponta para a etapa. As Assinatura de fluxo livre têm
    # isto NULL — e o `_registro`/`_docs_exigidos`/`_assinaturas_modelo` filtram
    # `solicitacao_etapa_id IS NULL` para não brigar com o roteiro (correção C1).
    solicitacao_etapa_id: Mapped[uuid.UUID | None] = mapped_column(String(36), nullable=True)
    pdf_key: Mapped[str | None] = mapped_column(String(300))
    hash_sha256: Mapped[str | None] = mapped_column(String(64))
    otp_hash: Mapped[str | None] = mapped_column(String(64))
    otp_expira_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    otp_tentativas: Mapped[int] = mapped_column(default=0)
    assinado_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ip: Mapped[str | None] = mapped_column(String(45))
    user_agent: Mapped[str | None] = mapped_column(String(400))
    # Invalidação (nunca deleção): dados que aparecem no documento mudaram após
    # a assinatura → esta via perde a validade, o registro fica para histórico
    # (o verificador público informa 'substituída') e um NOVO registro pendente
    # é criado para o candidato assinar a versão atualizada.
    invalidada_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    invalidada_motivo: Mapped[str | None] = mapped_column(String(300))
    # Informativo de integração só vai ao candidato assinar APÓS o RH disparar
    # (feedback 2026-07-23). Este doc NASCE com aguardando_liberacao=True e fica
    # oculto em _docs_exigidos até o RH liberar (`liberar-informativo`), quando
    # vira False. Todos os demais docs nascem False (liberados) — não muda nada.
    aguardando_liberacao: Mapped[bool] = mapped_column(default=False)
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
