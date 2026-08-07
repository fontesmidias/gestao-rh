"""Entrevista: cargo e posto quando não há vaga cadastrada (v2.74).

Por que estes campos existem, em vez de exigir uma vaga:

Nem toda entrevista nasce de vaga aberta. O RH conversa para um posto que
precisa repor gente, e obrigar a cadastrar uma vaga só para marcar a conversa
seria burocracia inventada — o mesmo motivo pelo qual `vaga_id` sempre foi
nullable (cenário 5 do documento: "entrevista sem vaga").

São **alternativa**, não substituto: havendo vaga, ela continua mandando, e o
cargo dela é que alimenta a herança do roteiro.

Duas escolhas de tipo, ambas seguindo o que o sistema já faz:

- **`cargo` é STRING, não FK.** É assim em `Candidato.cargo_funcao`,
  `ModeloDocumento.cargo_alvo` e nas provas por cargo — virar tabela quebraria
  os três. É também o que `resolver_roteiro` casa, por `normalizar_cargo`
  (minúsculo, sem acento), então o texto digitado aqui já resolve o roteiro.
- **`posto_id` é FK com SNAPSHOT do nome**, pela mesma razão do `vaga_titulo`:
  o posto pode ir para a lixeira, e a entrevista precisa continuar legível
  depois — dizer para qual posto a conversa foi é metade do registro.

Revision ID: a2c4e6f8b1d3
Revises: f1a3c5e7b9d2
"""
import sqlalchemy as sa
from alembic import op

revision = "a2c4e6f8b1d3"
down_revision = "f1a3c5e7b9d2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Todas NULLABLE: as entrevistas que já existem foram marcadas com vaga (ou
    # sem nada), e inventar um cargo para elas seria escrever no registro de uma
    # conversa que já aconteceu.
    op.add_column("entrevista", sa.Column("cargo", sa.String(120), nullable=True))
    op.add_column("entrevista", sa.Column("posto_id", sa.UUID(as_uuid=True), nullable=True))
    op.add_column("entrevista", sa.Column("posto_nome", sa.String(200), nullable=True))
    op.create_foreign_key("fk_entrevista_posto", "entrevista", "posto_servico",
                          ["posto_id"], ["id"], ondelete="SET NULL")
    op.create_index("ix_entrevista_posto_id", "entrevista", ["posto_id"])


def downgrade() -> None:
    op.drop_index("ix_entrevista_posto_id", table_name="entrevista")
    op.drop_constraint("fk_entrevista_posto", "entrevista", type_="foreignkey")
    op.drop_column("entrevista", "posto_nome")
    op.drop_column("entrevista", "posto_id")
    op.drop_column("entrevista", "cargo")
