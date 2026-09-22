"""Regra padrão: avisar quando o e-mail para de sair.

Nasce do incidente de 2026-09-22: a caixa que autenticava o Microsoft 365 foi
EXTINTA, o sistema só FALHAVA, e ninguém soube até um candidato reclamar que
não recebeu o código de acesso. A v3.22 fez a cadeia de provedores não parar
numa credencial morta; esta regra faz alguém FICAR SABENDO quando nenhum
provedor consegue entregar.

⚠️ **Por que semear, e não deixar o RH criar:** um tipo de alerta sem regra
cadastrada NUNCA dispara — seria código órfão, e o esquecimento só apareceria
no próximo incidente, que é exatamente quando não se pode contar com ele. O
padrão protege; o RH ajusta ou desliga na tela (Configurações → Telemetria).

⚠️ **NÃO precisa das duas revisões da armadilha do enum**: `regra_alerta.tipo`
é `String(20)`, não um ENUM do Postgres — conferido no banco antes de escrever.

⚠️ **INSERT cru não herda default do modelo** (v2.70): as colunas `NOT NULL`
sem `server_default` são `id`, `tipo` e `nome` (conferido com `\\d` no banco,
não no modelo). As demais têm default no servidor e podem faltar.

Idempotente (`NOT EXISTS`): rodar de novo não cria uma segunda regra, e um
banco que já a tenha recebido de outra forma não ganha duplicata.

Revision ID: d4e8f1a2b9c7
"""

import sqlalchemy as sa
from alembic import op

revision = "d4e8f1a2b9c7"
down_revision = "c7f2a9e4b830"
branch_labels = None
depends_on = None

# 3 falhas em 30 min: uma isolada pode ser rede; três seguidas são problema.
# O silêncio de 2h evita a enxurrada que faria o alerta deixar de ser lido
# (v2.88) sem deixar o incidente passar despercebido por um turno inteiro.
LIMIAR = 3
JANELA_MIN = 30
SILENCIO_MIN = 120


def upgrade() -> None:
    op.execute(sa.text("""
        INSERT INTO regra_alerta (id, tipo, nome, ativa, limiar, janela_min, silencio_min)
        SELECT gen_random_uuid(), 'email_falhou',
               'E-mail não está saindo', true, :limiar, :janela, :silencio
        WHERE NOT EXISTS (SELECT 1 FROM regra_alerta WHERE tipo = 'email_falhou')
    """).bindparams(limiar=LIMIAR, janela=JANELA_MIN, silencio=SILENCIO_MIN))


def downgrade() -> None:
    # Remove só a regra SEMEADA (pelo nome exato): se o RH criou outra do mesmo
    # tipo, ela é decisão dele e não se apaga num downgrade.
    op.execute(sa.text("""
        DELETE FROM regra_alerta
        WHERE tipo = 'email_falhou' AND nome = 'E-mail não está saindo'
    """))
