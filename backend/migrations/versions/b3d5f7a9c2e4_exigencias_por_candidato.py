"""Exigências ajustadas por candidato: documentos e campos (v2.80).

Pedido do Bruno (2026-08-07): *"ter a opção de, no front, por padrão vir marcado
os campos obrigatórios para todos (lógico, aqueles que têm que ser
obrigatórios), mas customizável por candidato, pelo pessoal do RH. Daí ter um
padrão geral lá em configurações"*.

Hoje a obrigatoriedade é CHUMBADA em dois lugares:

  · documentos — `services/slots.py`, lista `{"tipo": ..., "obrigatorio": True}`;
  · campos     — `api/ficha.py`, `_OBRIGATORIOS_PESSOAIS` / `_OBRIGATORIOS_DOCS`
                 e as listas soltas de endereço, banco, VT e emergência.

O PADRÃO GERAL vai para a config dinâmica (sem migration: é chave/valor).
Esta coluna guarda a EXCEÇÃO daquela pessoa.

Por que uma coluna JSONB no candidato, e não uma tabela:

1. **É um dado por pessoa, lido junto com ela.** Toda leitura da ficha já
   carrega o `Candidato`; uma tabela lateral seria mais uma consulta em todo
   lugar que monta pendência — e são muitos.
2. **`SlotDocumento.obrigatorio` NÃO serve para isso.** A `sincronizar_slots`
   REESCREVE aquele campo a cada execução (`slot.obrigatorio = spec[...]`), e o
   wizard salva a cada 900ms: a dispensa do RH seria apagada no autosave
   seguinte, em silêncio. Guardar a decisão fora do slot é o que a torna
   durável — o slot continua sendo o estado do ENVIO, não o da regra.
3. O formato é `{"documentos": {"chave": bool}, "campos": {"chave": bool}}`,
   com o MOTIVO e o autor na auditoria (o registro do ato mora lá, não aqui —
   mesma divisão da telemetria × auditoria, v2.24).

Revision ID: b3d5f7a9c2e4
Revises: a2c4e6f8b1d3
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "b3d5f7a9c2e4"
down_revision = "a2c4e6f8b1d3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # NULLABLE e sem server_default: ausência significa "segue o padrão geral",
    # que é o caso de 100% dos candidatos existentes. Preencher com `{}` para
    # todo mundo daria a impressão de que alguém decidiu algo — e o que este
    # campo registra é justamente uma DECISÃO.
    op.add_column("candidato",
                  sa.Column("exigencias", postgresql.JSONB(astext_type=sa.Text()),
                            nullable=True))


def downgrade() -> None:
    op.drop_column("candidato", "exigencias")
