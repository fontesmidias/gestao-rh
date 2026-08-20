"""As três tabelas do provedor OAuth do MCP remoto.

Existem porque o padrão de mercado é *clicar no conector e autenticar* — e o
nosso pedia instalar Python, abrir o terminal e editar um JSON. O que o OAuth
elimina não é o terminal (o instalador `.mcpb` também eliminaria): é a
**credencial colada**. A pessoa entra com a conta que já tem, e revogar o acesso
dela passa a ser desligá-la no portal.

⚠️ **O molde é `token_automacao.py` (v2.94), e as regras dele valem aqui**:
segredo guardado só como `sha256` (quem tem o banco não tem a credencial),
prefixo reconhecível para ser identificado se vazar, **revogar MARCA e não
apaga** (a linha é prova de que existiu e de quando deixou de valer), e a
property `valido` concentrando a decisão num lugar só.

**O que deliberadamente NÃO tem tabela:**

- **O access token** é assinado (`itsdangerous`) e vive 10 minutos. Linha no
  banco custaria uma escrita e uma leitura a cada chamada de ferramenta. A
  revogação continua imediata porque o `/mcp` consulta a CONCESSÃO a cada
  chamada — é ela que morre quando alguém revoga, não o access.
- **`client_secret`**, porque o Claude é cliente PÚBLICO: a prova é o PKCE. Uma
  coluna de segredo que ninguém confere é pior que não ter — dá a impressão de
  uma defesa que não existe.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


def _venceu(quando: datetime | None) -> bool:
    """`expira_em` no passado? Normaliza o fuso antes de comparar.

    A coluna é `timezone=True`, mas uma linha gravada por SQL cru pode voltar
    sem fuso — e comparar ingênuo com aware levanta `TypeError`. É a mesma
    normalização que `token_automacao.valido` faz.
    """
    if quando is None:
        return False
    if quando.tzinfo is None:
        quando = quando.replace(tzinfo=timezone.utc)
    return quando <= datetime.now(timezone.utc)


class ClienteOAuth(Base):
    """Um cliente que se registrou para pedir autorização (o Claude).

    Registrar-se é público por definição do protocolo (RFC 7591) — e é
    aceitável porque **registrar NÃO dá acesso**: sem uma pessoa fazer login e
    autorizar, o cliente registrado não obtém token nenhum. Quem ler isto e
    quiser "fechar o buraco" fechando o endpoint vai quebrar a conexão.
    """

    __tablename__ = "mcp_cliente_oauth"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True,
                                          default=uuid.uuid4)
    client_id: Mapped[str] = mapped_column(String(500), unique=True, index=True)
    client_name: Mapped[str] = mapped_column(String(200))
    # Lista de strings, substituída inteira — nunca editada item a item. Tabela
    # filha aqui seria três joins para comparar uma string.
    redirect_uris: Mapped[list] = mapped_column(JSONB, default=list)
    # "dcr" (registro dinâmico) ou "cimd" (o client_id é a URL do metadata).
    # String e não enum: são dois valores que podem crescer, e enum novo custa
    # a dança das duas migrations do Postgres.
    origem: Mapped[str] = mapped_column(String(20), default="dcr")
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True),
                                                server_default=func.now())
    # O /register é público: saber de onde veio é o que permite investigar.
    criado_por_ip: Mapped[str | None] = mapped_column(String(45), nullable=True)
    usado_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revogado_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revogado_por: Mapped[str | None] = mapped_column(String(200), nullable=True)

    @property
    def valido(self) -> bool:
        return self.revogado_em is None


class CodigoAutorizacao(Base):
    """O `code` que volta no redirect e é trocado por token em segundos.

    **Uso ÚNICO** — e é por isso que ele é linha no banco e não algo assinado:
    "já foi usado?" é estado, e stateless não sabe responder. Um code
    reapresentado significa que ele foi interceptado; a resposta é recusar **e
    revogar a concessão que ele gerou**.

    Vida de 60 segundos, não 10 minutos: o code viaja na URL, e URL fica no
    histórico do navegador e no log de todo proxy pelo caminho. A troca acontece
    em milissegundos.
    """

    __tablename__ = "mcp_codigo_autorizacao"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True,
                                          default=uuid.uuid4)
    codigo_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    cliente_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("mcp_cliente_oauth.id", ondelete="CASCADE"),
        index=True)
    usuario_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("usuario_rh.id", ondelete="CASCADE"), index=True)
    # O redirect_uri EXATO usado no /authorize: o /token compara, e divergência
    # é sinal de code roubado sendo trocado por outro cliente.
    redirect_uri: Mapped[str] = mapped_column(String(500))
    # RFC 8707: para qual recurso este code vale. Sem isto, um token emitido
    # aqui poderia ser apresentado a outro serviço que compartilhe a chave.
    resource: Mapped[str] = mapped_column(String(500))
    escopo: Mapped[str] = mapped_column(String(500), default="")
    # ⚠️ `code_challenge_method` NÃO é coluna: só S256 é aceito. Coluna daria a
    # impressão de que há escolha — e `plain` é justamente o que o OAuth 2.1
    # fechou.
    code_challenge: Mapped[str] = mapped_column(String(128))
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True),
                                                server_default=func.now())
    expira_em: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    usado_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    concessao_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)

    @property
    def valido(self) -> bool:
        return self.usado_em is None and not _venceu(self.expira_em)


class Concessao(Base):
    """O vínculo pessoa ↔ cliente: é isto que se revoga.

    **Uma linha por concessão, não por refresh token.** A rotação atualiza o
    `refresh_hash` na mesma linha e incrementa a `geracao` — o que faz revogar
    pela tela cortar a corrente inteira, não só o último elo.

    ⚠️ `refresh_hash_anterior` é o que detecta ROUBO: um refresh já rotacionado
    sendo reapresentado significa que alguém tem uma cópia. A resposta certa não
    é recusar aquele pedido e seguir — é **revogar a concessão inteira**. Sem
    esta coluna, o reuso seria indistinguível de "não existe", e a concessão
    legítima continuaria viva nas mãos de quem a roubou.
    """

    __tablename__ = "mcp_concessao"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True,
                                          default=uuid.uuid4)
    cliente_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("mcp_cliente_oauth.id", ondelete="CASCADE"),
        index=True)
    usuario_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("usuario_rh.id", ondelete="CASCADE"), index=True)
    refresh_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    refresh_hash_anterior: Mapped[str | None] = mapped_column(String(64), nullable=True,
                                                              index=True)
    # Só para a tela distinguir uma concessão da outra. NÃO autentica: casar por
    # prefixo daria acesso a quem lesse a listagem (a regra do token_automacao).
    refresh_prefixo: Mapped[str] = mapped_column(String(16))
    resource: Mapped[str] = mapped_column(String(500))
    escopo: Mapped[str] = mapped_column(String(500), default="")
    # Snapshot do que foi concedido: sempre `assistente_rh`.
    papel_concedido: Mapped[str] = mapped_column(String(50))
    # ⚠️ SNAPSHOT do papel do dia a dia da pessoa NA HORA de autorizar, para a
    # auditoria responder "quem era ela quando conectou?". **NÃO é usado para
    # autorizar** — autorizar por ele daria à pessoa o papel dela, que é
    # exatamente o que o desenho evita. Não "conserte" isto achando que é bug.
    papel_do_usuario: Mapped[str] = mapped_column(String(50))
    geracao: Mapped[int] = mapped_column(Integer, default=1)
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True),
                                                server_default=func.now())
    usado_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expira_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revogado_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revogado_por: Mapped[str | None] = mapped_column(String(200), nullable=True)
    # "usuario" | "reuso_detectado" | "desligamento"
    revogado_motivo: Mapped[str | None] = mapped_column(String(100), nullable=True)

    @property
    def valido(self) -> bool:
        return self.revogado_em is None and not _venceu(self.expira_em)
