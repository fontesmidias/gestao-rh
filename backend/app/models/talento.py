import enum
import uuid
from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, Enum, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class StatusTalento(str, enum.Enum):
    novo = "novo"
    em_analise = "em_analise"
    convertido = "convertido"       # virou candidato (admissão iniciada)
    arquivado = "arquivado"


class Talento(Base):
    """Cadastro do Banco de Talentos: captação de interessados ANTES de haver
    vaga/convite. O RH filtra, tria e, ao decidir contratar, converte o
    talento em candidato (migrando os dados já preenchidos)."""

    __tablename__ = "talento"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    nome: Mapped[str] = mapped_column(String(200))
    email: Mapped[str | None] = mapped_column(String(200), index=True)
    telefone: Mapped[str | None] = mapped_column(String(20))
    # cargo_interesse (string única) mantido por compatibilidade — sincronizado
    # com o 1º item de cargos_interesse (o `converter` legado usa esta coluna).
    cargo_interesse: Mapped[str | None] = mapped_column(String(120), index=True)
    cargos_interesse: Mapped[list | None] = mapped_column(JSON)   # múltipla escolha (Forms)
    regioes: Mapped[list | None] = mapped_column(JSON)            # regiões onde pode trabalhar
    cidade: Mapped[str | None] = mapped_column(String(120))
    # 300, não 60 (v2.89.1, defeito de campo): o formulário público oferece uma
    # LISTA curta ("Ensino médio completo"), e 60 bastava para ela — mas quando
    # o RH cadastra à mão o campo é texto livre, e o real tem 104 caracteres:
    # "Técnico em Secretariado / Secretário Executivo; Inglês avançado
    # (cursando, Centro de Idiomas de Ceilândia)". Coluna dimensionada para o
    # caminho de entrada mais estreito quebra no dia em que aparece o outro.
    escolaridade: Mapped[str | None] = mapped_column(String(300))
    resumo: Mapped[str | None] = mapped_column(Text)   # experiência/apresentação
    # PROCEDÊNCIA do cadastro: "Importação (Forms)", "Currículo por e-mail",
    # "Indicação"… (o comentário antigo dizia "como soube da empresa", mas o uso
    # real do código sempre foi este — a importação grava a fonte aqui).
    origem: Mapped[str | None] = mapped_column(String(80))
    # efetivo | intermitente | tanto_faz (string, não enum — simples e suficiente)
    tipo_contratacao: Mapped[str | None] = mapped_column(String(20))
    ja_trabalhou_funcao: Mapped[bool | None] = mapped_column(Boolean)
    recebe_seguro_desemprego: Mapped[bool | None] = mapped_column(Boolean)
    # aceite LGPD (obrigatório no formulário) — carimbo é a prova do consentimento.
    # ⚠️ NULO no cadastro FEITO PELO RH (v2.73): a pessoa não estava na tela para
    # marcar nada, e gravar o carimbo ali registraria como aceite do titular algo
    # que ele não fez. Quem assumiu o cadastro fica nos dois campos abaixo, e a
    # tela mostra "sem consentimento registrado" — o registro descreve o ato
    # REAL, nunca a versão conveniente (precedente da `AutorizacaoEquipe`).
    consentimento_lgpd_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Quem cadastrou à mão (v2.73). `_nome` é SNAPSHOT: se o usuário do RH for
    # removido, o responsável pelo cadastro não some junto (padrão da `Anotacao`).
    cadastrado_por_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("usuario_rh.id", ondelete="SET NULL"))
    cadastrado_por_nome: Mapped[str | None] = mapped_column(String(200))
    # currículo (opcional): arquivo original guardado no MinIO, servido como veio
    curriculo_key: Mapped[str | None] = mapped_column(String(300))
    curriculo_nome: Mapped[str | None] = mapped_column(String(200))
    curriculo_tipo: Mapped[str | None] = mapped_column(String(100))  # content-type
    status: Mapped[StatusTalento] = mapped_column(
        Enum(StatusTalento, name="status_talento"), default=StatusTalento.novo, index=True)
    candidato_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("candidato.id"), nullable=True)
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
