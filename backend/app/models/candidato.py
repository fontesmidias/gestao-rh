import enum
import uuid
from datetime import datetime

from sqlalchemy import JSON, DateTime, Enum, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base


class StatusCandidato(str, enum.Enum):
    """Fase do FLUXO de admissão (ortogonal ao vínculo, que vive em `situacao`).
    Feedback 2026-07-21: `status` e `situacao` compartilhavam ativo/desligado e
    confundiam a tela. Agora `status` é só fluxo: efetivado aqui → `aprovado`
    (passou pelo funil); importado do Tirvu → `importado` (nunca passou). O
    vínculo (ativo/desligado) fica SÓ na `situacao`."""

    convidado = "convidado"
    preenchendo = "preenchendo"
    docs_pendentes = "docs_pendentes"
    aguardando_assinatura = "aguardando_assinatura"
    envio_concluido = "envio_concluido"
    em_revisao = "em_revisao"
    aprovado = "aprovado"
    reprovado_pendencias = "reprovado_pendencias"
    expurgado = "expurgado"
    # Veio da base do Tirvu (não passou pelo funil de admissão daqui).
    importado = "importado"
    # ÓRFÃOS (v1.69): não são mais escritos — o vínculo migrou para `situacao`.
    # Mantidos no enum porque o Postgres não remove valor sem recriar o tipo; o
    # front (status.js) já os ignora. NÃO USAR em código novo.
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
    # ID do posto na base do Tirvu — chave natural, à prova do truncamento do
    # "Nome/Apelido" (que colide entre postos diferentes). É por ele que a
    # importação de postos casa/atualiza sem duplicar.
    tirvu_id: Mapped[str | None] = mapped_column(String(30), index=True)
    sigla: Mapped[str | None] = mapped_column(String(60))
    razao_social: Mapped[str | None] = mapped_column(String(200))
    cnpj: Mapped[str | None] = mapped_column(String(20))
    contrato_ref: Mapped[str | None] = mapped_column(String(200))
    # Endereço do posto (usado em ofícios/documentos que precisam dele).
    endereco: Mapped[str | None] = mapped_column(String(300))
    cidade: Mapped[str | None] = mapped_column(String(120))
    uf: Mapped[str | None] = mapped_column(String(2))
    cep: Mapped[str | None] = mapped_column(String(10))
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


class Empresa(Base):
    """Empregadora que assina a carteira (coluna 'Empresa' do layout de
    importação do Tirvu). Green House é a primeira, mas o grupo tem outras
    (ex.: Nossa Cozinha) — o RH escolhe ou cria pelo painel."""

    __tablename__ = "empresa"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    razao_social: Mapped[str] = mapped_column(String(200), unique=True)
    cnpj: Mapped[str | None] = mapped_column(String(20))
    ativa: Mapped[bool] = mapped_column(default=True)
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Jornada(Base):
    """Jornada de trabalho como o Tirvu descreve (texto livre padronizado, ex.:
    'INEP ADM - 2ª A 6ª - 08H - 12H - 13H - 17H'). Importada da planilha de
    escalas ou criada pelo RH na hora. O posto é uma DICA de ordenação no
    seletor (jornadas sem posto valem para todos), nunca um filtro."""

    __tablename__ = "jornada"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    # `descricao` é CANÔNICA: é ela que vai para o Tirvu (texto único), como
    # hoje. Os campos estruturados abaixo são METADADOS internos do RH (filtros,
    # decisão de rubrica), preenchidos por parser-proponente + confirmação
    # humana — nunca alteram o que o Tirvu recebe (feedback 2026-07-22).
    descricao: Mapped[str] = mapped_column(String(300), unique=True)
    posto_servico_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("posto_servico.id"), nullable=True)
    # --- Estrutura (opcional; proposta pelo parser, confirmada pelo RH) ---
    # escala: seg-sex | 12x36 | 5x2 | seg-qui+sex | intermitente
    escala: Mapped[str | None] = mapped_column(String(20))
    # os 4 horários do bloco principal, "HH:MM" (entrada, saída p/ almoço,
    # volta do almoço, saída). Jornadas sem almoço (12x36 noturno) podem ter só 2.
    hora_entrada: Mapped[str | None] = mapped_column(String(5))
    saida_almoco: Mapped[str | None] = mapped_column(String(5))
    volta_almoco: Mapped[str | None] = mapped_column(String(5))
    hora_saida: Mapped[str | None] = mapped_column(String(5))
    # 2º bloco quando a jornada é composta (sexta/sábado diferente) — texto livre
    bloco_secundario: Mapped[str | None] = mapped_column(String(150))
    # diurno | noturno (adicional noturno = rubrica)
    turno: Mapped[str | None] = mapped_column(String(10))
    adicional_noturno: Mapped[bool] = mapped_column(default=False)
    # intrajornada: dá direito à rubrica de adicional; obs = detalhe do parser
    # ("15 MINUTOS", "REDUÇÃO"), texto livre confirmado pelo RH.
    tem_intrajornada: Mapped[bool] = mapped_column(default=False)
    intrajornada_obs: Mapped[str | None] = mapped_column(String(60))
    # cargo típico embutido na descrição (motorista/brigadista/ASG/AGP…)
    cargo_relacionado: Mapped[str | None] = mapped_column(String(40))
    # quando o RH confirmou a proposta do parser (NULL = ainda "a confirmar")
    estruturado_confirmado_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ativa: Mapped[bool] = mapped_column(default=True)
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Candidato(Base):
    __tablename__ = "candidato"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    posto_servico_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("posto_servico.id"), nullable=True)
    cargo_funcao: Mapped[str | None] = mapped_column(String(120))
    # Integração com o Tirvu (leva 2026-07-19): empregadora, jornada e ponto —
    # o RH escolhe/cria no convite ou depois; saem no export de admissões.
    empresa_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("empresa.id"), nullable=True)
    jornada_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("jornada.id"), nullable=True)
    registra_ponto: Mapped[bool | None] = mapped_column(nullable=True)
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
    # Conciliação com a contabilidade: quando esta admissão foi lançada no
    # sistema Domínio (marcado pelo RH, individual ou em massa).
    na_dominio_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
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
