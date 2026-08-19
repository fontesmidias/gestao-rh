"""Comprovante MENSAL de despesa do Reembolso-Creche — uma competência por
criança, por mês.

Existe porque o sistema prometia isto e não tinha onde receber: o e-mail de
ativação (`creche_ativado`) manda o colaborador enviar, TODO MÊS, a nota fiscal
da creche (PJ) ou a declaração de quitação do cuidador (PF) — e o módulo tinha
21 rotas POST, nenhuma que aceitasse esse envio. O único upload recusava o que
não fosse certidão ou guarda. Promessa na tela sem rota atrás (v2.74), na maior
escala vista aqui, num benefício que entra em folha.

Regras vindas do Jurídico (e-mail do Dr. Lucas, 18/08/2026):

* O **requerimento** e a **certidão** são de uma vez só (e o requerimento é um
  por criança). O que se repete todo mês é **este** documento.
* **Um por filho e mensalmente** — daí a competência ser por CRIANÇA, não por
  benefício: quem tem dois filhos entrega dois comprovantes por mês.
* **Corte no dia 25**; a competência fechada é paga até o 5º dia útil do mês
  seguinte. São dois números que significam coisas opostas — ver
  `dia_entrega_mensal` (o corte) e não confundir com o prazo de pagamento.

Por que o valor é INTEIRO em centavos, divergindo do resto do sistema (que
guarda dinheiro como texto, ex. `valor_reembolso_creche = "R$ 526,64"`): aquele
campo é CONFIGURAÇÃO digitada pelo RH e lida uma vez; este é entrada de terceiro
que **vira soma** — o valor de cada mês entra no cálculo do reembolso. Guardar
texto obrigaria a parsear a cada conta, e `float` acumula erro de arredondamento
em dinheiro que vai para a folha. O texto do que a pessoa digitou fica em
`valor_informado_texto`, para o RH conferir contra o documento.
"""

import enum
import uuid
from datetime import datetime

from sqlalchemy import (DateTime, ForeignKey, Integer, String, UniqueConstraint,
                        func)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base


class StatusCompetencia(str, enum.Enum):
    # nasce quando alguém envia o comprovante (não existe linha "vazia": a
    # ausência de competência JÁ é a pendência, e criar linha vazia todo mês
    # para todo mundo encheria a tela de nada)
    enviado = "enviado"
    # o RH conferiu e aceitou — entra na folha
    aprovado = "aprovado"
    # o RH recusou (documento ilegível, valor divergente, mês errado)
    recusado = "recusado"


class CompetenciaCreche(Base):
    """O comprovante de despesa de UMA criança em UM mês."""

    __tablename__ = "competencia_creche"
    __table_args__ = (
        # Um comprovante por criança por mês. O reenvio SUBSTITUI (a rota
        # expurga o anterior); dois registros para o mesmo mês fariam a soma da
        # folha dobrar sem nada denunciar.
        UniqueConstraint("crianca_id", "ano", "mes", name="uq_competencia_crianca_mes"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True,
                                          default=uuid.uuid4)
    beneficio_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("beneficio_creche.id"), index=True)
    crianca_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("crianca_creche.id"), index=True)
    # competência de REFERÊNCIA da despesa (o mês em que o serviço foi prestado),
    # não o mês do envio — quem entrega em 25/09 comprova a despesa de agosto.
    ano: Mapped[int] = mapped_column(Integer)
    mes: Mapped[int] = mapped_column(Integer)          # 1-12

    # `String`, e não `Enum` do Postgres como o resto do projeto, DE PROPÓSITO:
    # acrescentar valor a enum nativo exige `ALTER TYPE ... ADD VALUE` em
    # revisão SEPARADA da que o usa (o Postgres proíbe usar valor recém-criado
    # na mesma transação — armadilha registrada no CLAUDE.md), e este ciclo
    # ainda vai ganhar estado conforme o uso real aparecer. Os valores válidos
    # são cobrados na rota, não pelo banco.
    status: Mapped[str] = mapped_column(String(12),
                                        default=StatusCompetencia.enviado.value)

    # `declaracao` (cuidador PF) ou `nota_fiscal` (creche PJ). Copiado da criança
    # no envio, mas guardado AQUI: a família pode trocar de arranjo no meio do
    # ano, e a competência tem de descrever o que foi entregue NAQUELE mês.
    tipo_comprovante: Mapped[str | None] = mapped_column(String(20))

    # Valor da despesa em CENTAVOS (ver docstring do módulo). O que se reembolsa
    # é o MENOR entre isto e o valor do posto — o valor do posto é TETO
    # (decisão do Bruno, 2026-08-18).
    valor_centavos: Mapped[int | None] = mapped_column(Integer)
    # O que a pessoa DIGITOU, como digitou — para o RH conferir contra o
    # documento sem depender da nossa interpretação.
    valor_informado_texto: Mapped[str | None] = mapped_column(String(30))

    # O comprovante: PDF combinado + prefixo dos originais (1..N folhas). Mesmo
    # desenho do slot da admissão — aqui a certidão/guarda do creche guardava UM
    # arquivo por tipo e reenviar SOBRESCREVIA, então "tem mais de uma folha?"
    # não tinha resposta possível.
    arquivo_pdf_key: Mapped[str | None] = mapped_column(String(300))
    paginas: Mapped[int | None] = mapped_column(Integer)

    enviado_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # quem enviou: "colaborador" ou o e-mail do RH (o RH também insere, como faz
    # na admissão — antes o único caminho era DEVOLVER o levantamento e esperar)
    enviado_por: Mapped[str | None] = mapped_column(String(200))

    # análise do RH
    analisado_por: Mapped[str | None] = mapped_column(String(200))
    analisado_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    motivo_recusa: Mapped[str | None] = mapped_column(String(400))

    # A competência é anterior à vigência do contrato deste posto? Não RECUSA
    # (decisão do Bruno): fica marcado para o RH decidir, e a marca aparece na
    # FILA, não só no registro — marca que ninguém vê equivale a não ter marca,
    # e o risco aqui é pagar retroativo indevido.
    anterior_a_vigencia: Mapped[bool] = mapped_column(default=False)

    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True),
                                                server_default=func.now())

    crianca: Mapped["CriancaCreche"] = relationship()  # noqa: F821
