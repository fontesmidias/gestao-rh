import enum
import uuid
from datetime import datetime

from sqlalchemy import JSON, DateTime, Enum, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base


class StatusCandidato(str, enum.Enum):
    convidado = "convidado"
    preenchendo = "preenchendo"
    docs_pendentes = "docs_pendentes"
    aguardando_assinatura = "aguardando_assinatura"
    envio_concluido = "envio_concluido"
    em_revisao = "em_revisao"
    aprovado = "aprovado"
    reprovado_pendencias = "reprovado_pendencias"
    expurgado = "expurgado"
    # Já é colaborador da casa (aprovado e efetivado, ou importado da base do
    # Tirvu). É o "estado colaborador" do mesmo registro — Candidato é a fase
    # inicial do ciclo de vida, o colaborador é a fase de vínculo ativo.
    ativo = "ativo"
    desligado = "desligado"


class SituacaoColaborador(str, enum.Enum):
    """Situação do vínculo, independente do fluxo de admissão. Só faz sentido
    para quem já é colaborador (importado do Tirvu ou efetivado)."""

    ativo = "ativo"
    desligado = "desligado"


class PostoServico(Base):
    """Posto/contrato (lotação) onde o colaborador será lotado. Cada posto tem
    sigla, CNPJ do tomador, contrato de referência e pode carregar atributos
    extras (colunas dinâmicas criadas pelo RH pelo painel)."""

    __tablename__ = "posto_servico"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    nome: Mapped[str] = mapped_column(String(200), unique=True)
    sigla: Mapped[str | None] = mapped_column(String(60))
    cnpj: Mapped[str | None] = mapped_column(String(20))
    contrato_ref: Mapped[str | None] = mapped_column(String(200))
    # Default agora é False: só INFRAERO exige o kit dela. Na Leva de kits por
    # posto, esse booleano dá lugar a uma lista de documentos específicos.
    exige_docs_infraero: Mapped[bool] = mapped_column(default=False)
    # Documentos assináveis específicos deste posto (o RH marca no CRUD): lista
    # de valores de DocumentoAssinavel. Ex.: kit da Presidência.
    documentos_kit: Mapped[list] = mapped_column(JSON, default=list)
    # Colunas dinâmicas do painel: {"chave": "valor", ...}.
    atributos: Mapped[dict] = mapped_column(JSON, default=dict)
    # Reembolso-creche (IN SEGES/MGI 147/2026): o direito ao benefício é POR
    # posto/contrato — nem todo tomador o oferece. O valor varia por
    # repactuação de contrato (ex.: Presidência difere do teto da IN).
    da_direito_creche: Mapped[bool] = mapped_column(default=False)
    valor_reembolso_creche: Mapped[str | None] = mapped_column(String(30))  # "R$ 526,64"
    ativo: Mapped[bool] = mapped_column(default=True)
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Candidato(Base):
    __tablename__ = "candidato"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    posto_servico_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("posto_servico.id"), nullable=True)
    cargo_funcao: Mapped[str | None] = mapped_column(String(120))
    # Regime de contratação: "efetivo" (padrão) ou "intermitente". Decide qual
    # ficha de integração o colaborador assina.
    regime: Mapped[str] = mapped_column(String(20), default="efetivo")
    # Remuneração digitada pelo RH (texto livre: "R$ 1.500,00" ou "1500").
    # adicionais: lista de {"nome": str, "valor": str, "tipo": "reais"|"percentual"}.
    salario_base: Mapped[str | None] = mapped_column(String(60))
    adicionais: Mapped[list] = mapped_column(JSON, default=list)
    status: Mapped[StatusCandidato] = mapped_column(
        Enum(StatusCandidato, name="status_candidato"), default=StatusCandidato.convidado
    )
    # --- Vínculo de colaborador (preenchido para quem já está na casa) ---
    # CPF é a chave natural do colaborador na base do Tirvu; usado para
    # deduplicar a importação em massa e autenticar no autocadastro público.
    cpf: Mapped[str | None] = mapped_column(String(14), index=True, nullable=True)
    matricula: Mapped[str | None] = mapped_column(String(30), index=True, nullable=True)
    data_nascimento: Mapped[str | None] = mapped_column(String(10))  # dd/mm/aaaa
    # Situação do vínculo: None enquanto é candidato em admissão; "ativo" ou
    # "desligado" quando vira colaborador. Não confundir com `status` (fluxo).
    situacao: Mapped[str | None] = mapped_column(String(20), nullable=True)
    data_admissao: Mapped[str | None] = mapped_column(String(10))
    data_desligamento: Mapped[str | None] = mapped_column(String(10))
    # Como o registro entrou na base: "admissao" (fluxo normal) ou "importacao"
    # (planilha do Tirvu). Ajuda o diagnóstico e evita reprocessar convites.
    origem: Mapped[str] = mapped_column(String(20), default="admissao")
    # Todas as demais colunas do Tirvu (52 no total) que não viram campo fixo
    # entram aqui como {rótulo legível: valor}. É o CRUD de colunas dinâmicas.
    dados_tirvu: Mapped[dict] = mapped_column(JSON, default=dict)
    nome_completo: Mapped[str] = mapped_column(String(200))
    # E-mail e celular são opcionais no convite (o RH pode só copiar o link e
    # mandar por WhatsApp); o candidato completa na ficha — e o e-mail passa a
    # ser exigido lá, porque o código de assinatura chega por ele.
    email: Mapped[str | None] = mapped_column(String(200), index=True, nullable=True)
    celular_whatsapp: Mapped[str | None] = mapped_column(String(20), nullable=True)
    aceite_lgpd_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    declaracao_veracidade_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    dossie_pdf_key: Mapped[str | None] = mapped_column(String(300))
    dossie_gerado_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    arquivos_expurgados_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    acessos: Mapped[list["AcessoMagico"]] = relationship(back_populates="candidato")


class AcessoMagico(Base):
    __tablename__ = "acesso_magico"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    candidato_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("candidato.id"), index=True)
    # Apenas o hash do token é persistido; o token em claro vai só no link enviado.
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    expira_em: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    usado_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revogado: Mapped[bool] = mapped_column(default=False)
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    candidato: Mapped[Candidato] = relationship(back_populates="acessos")
