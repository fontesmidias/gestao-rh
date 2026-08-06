"""Assinatura da FICHA DE ENTREVISTA pelo RH que conduziu (v2.67, § 15.3).

Decisão do Bruno: a ficha preenchida é assinável, e quem assina é **o RH que
conduziu** — logado, com a senha da própria sessão (`prova_metodo =
"senha_sessao_rh"`, o mesmo método de `api/solicitacoes_assinatura.py:400`). O
**entrevistado não assina**: exigiria mandar link para quem talvez nem seja
contratado, e o link daria a ele acesso às notas e às justificativas escritas a
seu respeito.


Por que uma tabela PRÓPRIA, e não `SolicitacaoAssinatura` ou `Assinatura`
------------------------------------------------------------------------
Esta é a decisão de desenho que mais importa neste arquivo, e ela vem de uma
leitura do código, não de preferência.

**`SolicitacaoAssinatura` está descartada porque o DOSSIÊ a varre.**
`services/dossie.py` monta o dossiê e, logo depois das fichas, percorre **toda**
`SolicitacaoAssinatura` do candidato com `status == concluida` e
`pdf_final_key IS NOT NULL` — **sem filtrar `origem`**:

    for sol in db.scalars(select(SolicitacaoAssinatura).where(
            SolicitacaoAssinatura.candidato_id == candidato.id,
            SolicitacaoAssinatura.status == StatusSolicitacao.concluida,
            SolicitacaoAssinatura.pdf_final_key.isnot(None))).all():

Assinar a ficha por esse caminho a colocaria **automaticamente dentro do
dossiê**, que é exatamente o que o § 15.4 proíbe — e ninguém veria: o dossiê
sairia com uma página a mais, com as notas de seleção da pessoa, indo ao
cliente e à pasta física. O Bruno chegou a incluir a ficha no dossiê e corrigiu
na mesma sessão (*"não não. no dossiê de admissão não."*). Um filtro de origem
no `dossie.py` resolveria o sintoma, mas deixaria a porta encostada: qualquer
roteiro futuro de outro módulo voltaria a vazar pelo mesmo lugar.

**`Assinatura` está descartada porque é amarrada ao CANDIDATO** (`candidato_id`
não-nulo) e ao enum `DocumentoAssinavel`. A entrevista pode ser de um TALENTO
que nunca virou candidato — o padrão das duas FKs opcionais existe justamente
por isso. E acrescentar valor ao `DocumentoAssinavel` seria pior ainda:
`api/rh_ficha.py:38` faz `_TODOS = list(DocumentoAssinavel)` e usa a lista em
`DOCS_POR_SECAO`, então editar os dados pessoais de alguém passaria a
**invalidar a ficha de entrevista dele**; e `_docs_exigidos` faria a ficha de
entrevista virar pendência de assinatura do candidato no wizard.

O que se REUSA, porque o valor está aí: o método de prova (`senha_sessao_rh`), o
hash SHA-256 do PDF assinado, o carimbo de IP/user-agent e a auditoria. O que
não se reusa é o TRANSPORTE — e é o transporte que vazaria para o dossiê.
"""
import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID

from app.core.db import Base


class AssinaturaEntrevista(Base):
    __tablename__ = "assinatura_entrevista"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    entrevista_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("entrevista.id", ondelete="CASCADE"), index=True)

    # Quem assinou: FK + SNAPSHOT do nome e do e-mail. O snapshot é o que
    # sobrevive à remoção do usuário — mesma regra do `autor_nome` do mini-CRM
    # e do `entrevistador_nome` da própria entrevista. Sem ele, a prova de
    # autoria apontaria para uma linha que pode não existir mais.
    usuario_rh_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("usuario_rh.id"), nullable=True)
    assinante_nome: Mapped[str] = mapped_column(String(200))
    assinante_email: Mapped[str | None] = mapped_column(String(200))

    # O PDF **daquele momento**, com o bloco de assinatura. Fica no MinIO e
    # NUNCA é regerado: o hash abaixo descreve estes bytes.
    pdf_key: Mapped[str | None] = mapped_column(String(300))
    # SHA-256 do PDF SEM o bloco de assinatura — a mesma convenção do
    # `Assinatura.hash_sha256`, para que a integridade possa ser conferida
    # recalculando o documento base.
    hash_sha256: Mapped[str | None] = mapped_column(String(64))

    # Evidências do ato (Lei 14.063/2020, assinatura eletrônica simples).
    prova_metodo: Mapped[str] = mapped_column(String(40), default="senha_sessao_rh")
    ip: Mapped[str | None] = mapped_column(String(45))
    user_agent: Mapped[str | None] = mapped_column(String(400))

    # Via. Alterar a entrevista depois de assinada NÃO reescreve esta via
    # (cenário 31): gera-se uma NOVA, e a anterior permanece com o hash dela.
    # É a regra da casa desde 2026-07-15 — assinatura é prova de um ato, e ato
    # não se edita retroativamente.
    via: Mapped[int] = mapped_column(Integer, default=1)
    # Marca a via superada quando uma nova é emitida. A via antiga CONTINUA
    # existindo e consultável; some da vista, não do registro.
    substituida_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    assinado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now())
