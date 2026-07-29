"""Textos dos e-mails do sistema, editáveis pelo RH (v2.06).

Antes desta tabela, os 42 pontos de envio tinham assunto e corpo escritos à mão
em f-string no call site. Trocar uma vírgula num aviso era deploy, e o RH não
tinha como saber sequer QUAIS e-mails o sistema manda — foi o que o Bruno pediu
em 2026-07-28 ("uma página com os e-mails todos que existem, puxando suas
respectivas variáveis, com preview e histórico").

Desenho, em três regras:

1. **O template guarda APRESENTAÇÃO, nunca decisão.** As listas dinâmicas (os
   documentos a reenviar, as pendências da admissão) continuam sendo montadas
   em Python e chegam ao template prontas, como uma variável. O RH edita o
   texto ao redor e escolhe onde a lista aparece; a REGRA de o que entra nela
   fica no código.
2. **Variável obrigatória é validada no salvamento.** Um template de código de
   acesso sem `{{codigo}}` sairia bonito e vazio — e ninguém mais entraria no
   sistema. Por isso `EmailTemplate` não é a fonte da verdade sobre quais
   variáveis existem: quem manda é o CATALOGO em `services/email_templates.py`,
   e salvar sem uma obrigatória é 422.
3. **O texto do código é sempre o fallback.** Template ausente, apagado ou
   ilegível cai no texto original — e-mail nenhum deixa de sair porque alguém
   editou errado.

A substituição usa `fichas.aplicar_variaveis` (regex `{{chave}}`), a mesma dos
modelos de documento e do Teams: sem engine, sem dot-access, sem execução —
logo, sem superfície de template injection.
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class EmailTemplate(Base):
    """A versão VIGENTE do texto de um e-mail. Uma linha por `chave`."""

    __tablename__ = "email_template"

    chave: Mapped[str] = mapped_column(String(80), primary_key=True)
    assunto: Mapped[str] = mapped_column(Text)
    # Corpo em texto puro, um parágrafo por linha em branco. O HTML é derivado
    # dele (html_moderno), para o RH não precisar escrever marcação.
    corpo: Mapped[str] = mapped_column(Text)
    # Rótulo do botão de ação; a URL vem do contexto, nunca do RH.
    botao_texto: Mapped[str | None] = mapped_column(String(80))
    atualizado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    atualizado_por: Mapped[str | None] = mapped_column(String(200))


class EmailTemplateVersao(Base):
    """Histórico append-only: cada salvamento guarda o texto ANTERIOR.

    Serve a duas perguntas do RH: "quem mudou isso e quando?" e "como era
    antes?" — com restauração em um clique. O autor é SNAPSHOT (string), não
    FK: remover o usuário do painel não pode apagar a autoria de uma mudança.
    """

    __tablename__ = "email_template_versao"
    __table_args__ = (UniqueConstraint("chave", "versao", name="uq_email_versao"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True,
                                          default=uuid.uuid4)
    chave: Mapped[str] = mapped_column(String(80), index=True)
    versao: Mapped[int] = mapped_column()
    assunto: Mapped[str] = mapped_column(Text)
    corpo: Mapped[str] = mapped_column(Text)
    botao_texto: Mapped[str | None] = mapped_column(String(80))
    autor: Mapped[str | None] = mapped_column(String(200))
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True),
                                                server_default=func.now())
