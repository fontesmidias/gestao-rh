"""Telemetria de uso — o que acontece no APARELHO da pessoa (v2.24).

Pedido do Bruno em 2026-07-29, logo depois do incidente da tela branca: ele
passou horas sem saber por que dois candidatos travaram, porque o erro
acontecia no navegador deles e morria lá. A telemetria HTTP que já existia
(`main.py`) só registra o lado do SERVIDOR, vai para o log do container e
some no restart — foi por isso que um `TypeError` no React não deixou rastro
nenhum.

Quatro famílias de evento, todas pedidas explicitamente:

- `erro`        — exceção de JS, com página, stack e versão do bundle. É o que
                  teria mostrado o bug de 2026-07-29 no PRIMEIRO candidato.
- `friccao`     — a pessoa travou: reenviou o mesmo documento, tentou de novo,
                  abandonou a etapa. Mostra ONDE se desiste.
- `jornada`     — que tela abriu e quando. Reconstrói o caminho de alguém que
                  ligou reclamando.
- `desempenho`  — quanto demorou de verdade no celular em 4G, não no servidor.

**Isto NÃO é a auditoria.** `EventoAuditoria` responde "quem fez o quê" e é
prova de ato (append-only, nunca expurgada por conveniência). A telemetria
responde "como foi usar o sistema" e é DESCARTÁVEL por desenho — tem retenção
configurável e expurgo por intervalo de datas. Misturar as duas transformaria
dado de produto em prova jurídica, e prova jurídica em lixo que se apaga.

LGPD — o que este modelo NÃO guarda, por decisão de projeto:
- **nada do que a pessoa digita**: nenhum valor de campo, nenhum conteúdo de
  formulário. Só o NOME da etapa e o que aconteceu com ela.
- **IP completo não**: só os dois primeiros octetos (`191.180.x.x`), que bastam
  para distinguir "problema de uma operadora" de "problema do sistema" sem
  localizar a pessoa.
- o `user_agent` é truncado, serve para saber se o defeito é de um navegador só.
"""

import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base

# As FKs abaixo apontam para `candidato` e `talento`. O SQLAlchemy resolve o
# alvo pelo NOME da tabela no metadata — se o módulo do modelo não tiver sido
# importado, ele levanta `NoReferencedTableError` no primeiro flush. Importar
# aqui garante que quem usa a telemetria não precise conhecer essa ordem.
# (Pego por teste: sem isto, TODA gravação falhava em silêncio, porque o
# `registrar_eventos` engole exceção por desenho.)
from app.models import candidato as _candidato  # noqa: F401
from app.models import talento as _talento  # noqa: F401


class TipoTelemetria(str, enum.Enum):
    """Família do evento — governa como a tela do RH agrupa e o que destaca."""

    erro = "erro"
    friccao = "friccao"
    jornada = "jornada"
    desempenho = "desempenho"


# Quem estava usando quando o evento aconteceu. Não é o mesmo que "quem é a
# pessoa": um candidato mexe na própria admissão, o RH mexe no painel.
class OrigemTelemetria(str, enum.Enum):
    candidato = "candidato"     # wizard/checklist da admissão
    talento = "talento"         # formulário público do Banco de Talentos
    colaborador = "colaborador"  # portal /meu e creche
    rh = "rh"                   # painel
    publico = "publico"         # home, verificação de documento


class EventoTelemetria(Base):
    __tablename__ = "evento_telemetria"
    __table_args__ = (
        # A consulta mais comum da tela: "erros das últimas 24h", "fricção
        # desta semana". Tipo + data cobre todos os filtros do painel.
        Index("ix_telemetria_tipo_data", "tipo", "criado_em"),
        # "o que aconteceu com ESTA pessoa" — o pedido de telemetria
        # individualizada na ficha.
        Index("ix_telemetria_candidato_data", "candidato_id", "criado_em"),
        Index("ix_telemetria_talento_data", "talento_id", "criado_em"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True,
                                          default=uuid.uuid4)
    tipo: Mapped[TipoTelemetria] = mapped_column(
        String(20), index=True)
    origem: Mapped[OrigemTelemetria] = mapped_column(String(20), index=True)

    # A quem o evento pertence. Os dois são opcionais e não excludentes: a
    # mesma pessoa pode ter registro como talento e como candidato (o par é
    # descoberto pelo mini-CRM, ver services/crm.py::escopo_pessoa).
    candidato_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("candidato.id", ondelete="CASCADE"), index=True)
    talento_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("talento.id", ondelete="CASCADE"), index=True)
    # Usuário do painel, quando a origem é `rh`. String (e-mail), não FK: é
    # snapshot — o registro sobrevive à remoção do usuário, igual ao CRM.
    usuario_rh: Mapped[str | None] = mapped_column(String(200))

    # Sessão anônima do navegador: liga os eventos de uma MESMA visita sem
    # identificar ninguém. É gerada no cliente e vive só na aba.
    sessao: Mapped[str | None] = mapped_column(String(40), index=True)

    # O que aconteceu. `evento` é o nome curto e estável usado nos filtros
    # ("erro_render", "documento_reenviado", "etapa_abandonada"); `pagina` é
    # onde ("/c/documentos", "/rh/talentos").
    evento: Mapped[str] = mapped_column(String(60), index=True)
    pagina: Mapped[str | None] = mapped_column(String(120), index=True)

    # Duração em milissegundos — só para `desempenho` e para etapas medidas.
    duracao_ms: Mapped[int | None] = mapped_column(Integer)

    # Contexto livre: stack do erro, nome do documento reenviado, quantas
    # tentativas. NUNCA conteúdo digitado pela pessoa.
    detalhe: Mapped[dict | None] = mapped_column(JSONB)

    # Versão do bundle que estava rodando. Foi exatamente o que faltou em
    # 2026-07-29 para saber se a aba tinha ficado com código velho.
    versao: Mapped[str | None] = mapped_column(String(40))
    user_agent: Mapped[str | None] = mapped_column(String(200))
    # Só os dois primeiros octetos (191.180.x.x) — ver LGPD no topo.
    ip_prefixo: Mapped[str | None] = mapped_column(String(20))

    criado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True)
