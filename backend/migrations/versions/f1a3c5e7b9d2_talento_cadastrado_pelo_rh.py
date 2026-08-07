"""Talento cadastrado à mão pelo RH: quem cadastrou e de onde veio (v2.73).

Por que estes campos existem, em vez de reusar o que já havia:

`Talento.origem` já registra a PROCEDÊNCIA do cadastro — a importação grava
"Importação (Forms)" ali (o comentário do modelo diz "como soube da empresa",
mas o uso real do código é outro; seguimos o uso). Ele responde *de onde veio*,
não *quem digitou*.

O que faltava é o par de responsabilidade, e ele importa por causa do
CONSENTIMENTO. No cadastro público a pessoa marca "li e concordo" e o
`consentimento_lgpd_em` é carimbado; na importação do Forms o carimbo vem da
coluna "Li e concordo" da planilha. **Quando o RH cadastra à mão, ninguém
marcou nada** — e o sistema não pode gravar como aceite do titular algo que ele
não fez.

Por isso: `consentimento_lgpd_em` fica NULO (a ficha diz "sem consentimento
registrado") e estes dois campos dizem quem assumiu o cadastro. É o precedente
da `AutorizacaoEquipe` (v1.42), que escreve "emitido sob autorização permanente
de X" em vez de "X assinou": o registro descreve o ato REAL, nunca a versão
conveniente — a mesma regra do manifesto de admissão assistida (v2.56).

`cadastrado_por_nome` é SNAPSHOT (String, não FK): se o usuário do RH for
removido, o registro de quem cadastrou não pode sumir junto — mesma decisão da
`Anotacao` do mini-CRM.

Revision ID: f1a3c5e7b9d2
Revises: e9c1a3f5b7d2
"""
import sqlalchemy as sa
from alembic import op

revision = "f1a3c5e7b9d2"
down_revision = "e9c1a3f5b7d2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Ambas NULLABLE: os talentos que já existem vieram do formulário público ou
    # da planilha, e nenhum deles foi cadastrado por alguém do RH. Preencher com
    # um valor qualquer inventaria um responsável que não existe.
    op.add_column("talento", sa.Column("cadastrado_por_id", sa.UUID(as_uuid=True),
                                       nullable=True))
    op.add_column("talento", sa.Column("cadastrado_por_nome", sa.String(200),
                                       nullable=True))
    op.create_foreign_key("fk_talento_cadastrado_por", "talento", "usuario_rh",
                          ["cadastrado_por_id"], ["id"], ondelete="SET NULL")


def downgrade() -> None:
    op.drop_constraint("fk_talento_cadastrado_por", "talento", type_="foreignkey")
    op.drop_column("talento", "cadastrado_por_nome")
    op.drop_column("talento", "cadastrado_por_id")
