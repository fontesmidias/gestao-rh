"""Cadastro de Desenvolvimento: cursos, certificações e qualificações do
colaborador ao longo do vínculo (Onda B do roadmap `06-jornada-do-colaborador`).

A tese: *a admissão é o começo do cadastro, não o fim*. Hoje o sistema conhece
a pessoa a fundo no dia em que ela entra e depois fica cego. Aqui o colaborador
manda o que fez desde então — curso, NR, formação de brigada — e o RH valida.

**Brigadista NÃO é um módulo separado.** É uma CONSULTA sobre esta tabela:
registros do tipo "formação de brigada", de quem ocupa os quatro cargos de
brigada, com validade vencendo. O que distingue o certificado de brigadista do
curso de Excel não é o tipo em si — é `exige_validade` + `critico`:

- **curso livre**: sem validade, sem criticidade. Compõe o desempenho e pronto.
- **certificação crítica** (brigada, NR): vence, e vencida deixa o posto
  irregular perante fiscalização. Nunca entra em aprovação de lote.

Tratar os dois igual seria ou burocratizar o curso de Excel, ou relaxar o
brigadista.
"""

import enum
import uuid
from datetime import date, datetime

from sqlalchemy import (JSON, Boolean, Date, DateTime, Enum, ForeignKey,
                        Integer, String, Text, func)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base


class StatusRegistro(str, enum.Enum):
    """Ciclo de vida de um registro enviado pelo colaborador."""
    # o colaborador enviou e aguarda o RH validar
    pendente = "pendente"
    # o RH conferiu o documento e validou: passa a valer para dossiê e relatório
    validado = "validado"
    # o RH recusou (documento ilegível, não confere, não se aplica ao cargo)
    recusado = "recusado"
    # o RH devolveu para o colaborador corrigir e reenviar (2ª chance, não veredito)
    devolvido = "devolvido"


class SensibilidadeDoc(str, enum.Enum):
    """Governa o ROTEAMENTO da leitura por IA (LGPD).

    `saude` é categoria especial (art. 11) e só pode ser lida quando o provedor
    estiver sob Zero Data Retention — a trava fica no código (`ocr_roteador`),
    não numa política que alguém esquece.
    """
    comum = "comum"      # certificado, diploma, declaração de curso
    identidade = "identidade"  # RG, CPF, CNH
    saude = "saude"      # ASO — atestado de saúde ocupacional


class TipoDesenvolvimento(Base):
    """O QUE pode ser cadastrado: "Formação de brigada", "NR-35", "Curso livre".

    Configurável pelo RH — a lista não é fixa no código, senão cada certificação
    nova exigiria deploy.
    """

    __tablename__ = "tipo_desenvolvimento"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True,
                                          default=uuid.uuid4)
    nome: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    descricao: Mapped[str | None] = mapped_column(Text)
    # Vence? Por quantos meses vale? (brigada = 24, definido pelo Bruno)
    exige_validade: Mapped[bool] = mapped_column(Boolean, default=False)
    meses_validade: Mapped[int | None] = mapped_column(Integer)
    # Crítico = a validade gera OBRIGAÇÃO (posto irregular na fiscalização).
    # Nunca entra em aprovação de lote; sempre conferido um a um.
    critico: Mapped[bool] = mapped_column(Boolean, default=False)
    # Cargos aos quais se aplica (JSON de strings, casando com
    # `Candidato.cargo_funcao`, que é texto livre). Vazio = vale para todos.
    cargos_aplicaveis: Mapped[list | None] = mapped_column(JSON)
    # Documentos que o dossiê deste tipo exige, na ordem em que a entidade
    # formadora pede. Ex. brigada: ["identidade", "certificado_formacao", "aso"]
    documentos_exigidos: Mapped[list | None] = mapped_column(JSON)
    # Antecedência do aviso de vencimento, em dias (customizável pelo front —
    # o Bruno sugeriu 60 como padrão).
    aviso_dias_antes: Mapped[int] = mapped_column(Integer, default=60)
    ativo: Mapped[bool] = mapped_column(Boolean, default=True)
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True),
                                                server_default=func.now())

    prazos: Mapped[list["PrazoValidade"]] = relationship(
        back_populates="tipo", cascade="all, delete-orphan")


class PrazoValidade(Base):
    """Sobrescreve `meses_validade` do tipo para um CARGO ou um POSTO.

    Pedido explícito do Bruno: "customizável por posto, ou cargo, ou qualquer
    outra coisa". Herança em três níveis — tipo → cargo → posto —, o mais
    específico vence (ver `services/desenvolvimento.py::meses_validade_de`).
    """

    __tablename__ = "prazo_validade"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True,
                                          default=uuid.uuid4)
    tipo_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tipo_desenvolvimento.id", ondelete="CASCADE"), index=True)
    # exatamente UM dos dois é preenchido
    cargo: Mapped[str | None] = mapped_column(String(120), index=True)
    posto_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("posto_servico.id", ondelete="CASCADE"), index=True)
    meses_validade: Mapped[int] = mapped_column(Integer)

    tipo: Mapped[TipoDesenvolvimento] = relationship(back_populates="prazos")


class RegistroDesenvolvimento(Base):
    """Um curso/certificação de UMA pessoa. O currículo dela dentro da empresa.

    O arquivo original fica no MinIO; aqui ficam os campos que a IA propôs e o
    humano confirmou (nunca o que a IA gravou sozinha).
    """

    __tablename__ = "registro_desenvolvimento"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True,
                                          default=uuid.uuid4)
    candidato_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("candidato.id"), index=True)
    tipo_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tipo_desenvolvimento.id"), index=True)
    status: Mapped[StatusRegistro] = mapped_column(
        Enum(StatusRegistro, name="status_registro_desenvolvimento"),
        default=StatusRegistro.pendente, index=True)

    # --- o que a pessoa declara (pré-preenchido pela IA, confirmado por ela) ---
    titulo: Mapped[str | None] = mapped_column(String(200))
    instituicao: Mapped[str | None] = mapped_column(String(200))
    carga_horaria: Mapped[str | None] = mapped_column(String(30))
    concluido_em: Mapped[date | None] = mapped_column(Date)
    # Calculado de `concluido_em` + meses de validade na validação do RH. Fica
    # PERSISTIDO (e não derivado a cada consulta) porque o prazo pode mudar
    # depois — e a validade de um certificado já emitido não muda junto.
    validade_ate: Mapped[date | None] = mapped_column(Date, index=True)
    observacao: Mapped[str | None] = mapped_column(Text)

    # --- rastro da leitura automatizada (auditoria LGPD) ---
    # o que a IA propôs, para se comparar com o que a pessoa confirmou
    extraido_ia: Mapped[dict | None] = mapped_column(JSON)
    lido_por_ia_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # --- decisão do RH ---
    validado_por: Mapped[str | None] = mapped_column(String(200))
    validado_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    motivo_recusa: Mapped[str | None] = mapped_column(Text)

    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True),
                                                server_default=func.now(), index=True)
    enviado_por: Mapped[str] = mapped_column(String(20), default="colaborador")  # colaborador | rh

    tipo: Mapped[TipoDesenvolvimento] = relationship()
    arquivos: Mapped[list["ArquivoDesenvolvimento"]] = relationship(
        back_populates="registro", cascade="all, delete-orphan")


class ArquivoDesenvolvimento(Base):
    """Documento anexado a um registro. Um registro pode exigir vários (o
    dossiê de brigada pede identidade + certificado + ASO)."""

    __tablename__ = "arquivo_desenvolvimento"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True,
                                          default=uuid.uuid4)
    registro_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("registro_desenvolvimento.id", ondelete="CASCADE"), index=True)
    # papel do arquivo dentro do registro: identidade | certificado_formacao |
    # certificado_reciclagem | aso | outro
    papel: Mapped[str] = mapped_column(String(40), default="outro")
    sensibilidade: Mapped[SensibilidadeDoc] = mapped_column(
        Enum(SensibilidadeDoc, name="sensibilidade_doc"),
        default=SensibilidadeDoc.comum)
    key: Mapped[str] = mapped_column(String(300))          # caminho no MinIO
    nome_original: Mapped[str | None] = mapped_column(String(200))
    content_type: Mapped[str | None] = mapped_column(String(100))
    tamanho: Mapped[int | None] = mapped_column(Integer)
    # SHA-256 do conteúdo: prova de qual arquivo foi lido, sem guardar o texto
    sha256: Mapped[str | None] = mapped_column(String(64))
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True),
                                                server_default=func.now())

    registro: Mapped[RegistroDesenvolvimento] = relationship(back_populates="arquivos")
