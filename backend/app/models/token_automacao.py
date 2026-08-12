"""Credencial de MÁQUINA para o MCP do portal (v2.94).

Por que não reusar o token de sessão do painel: ele é `itsdangerous` stateless
(`core/security.py`), com TTL de 12h. As duas coisas o desqualificam aqui:

1. **Stateless não se REVOGA.** A assinatura é a única prova; enquanto não
   expira, ele vale — não há onde marcar "este não vale mais". Para credencial
   de gente isso é aceitável (a janela é curta e a pessoa troca a senha); para
   credencial guardada em arquivo num desktop, é o oposto do que se precisa.
   A pergunta que decide é *"se vazar hoje à noite, como eu corto o acesso?"* —
   e com token stateless a resposta seria "trocando o SECRET_KEY", que derruba
   a sessão de TODO mundo.
2. **12h significa reautenticar todo dia**, e a saída óbvia (guardar a senha do
   usuário no desktop para renovar sozinho) é justamente o que não se deve
   fazer: uma senha vale para sempre e serve para entrar no painel inteiro.

Desenho: o segredo é sorteado, **mostrado UMA vez** e guardado só como
`sha256`. Quem tem o banco não tem a credencial — mesma razão pela qual senha é
hash. Revogar é escrever `revogado_em`, e revogar é um ATO REGISTRADO, não um
delete: apagar a linha apagaria junto a prova de que a credencial existiu e de
quando deixou de valer.

⚠️ O token NÃO é uma segunda porta de autenticação: ele resolve para um
`UsuarioRH` de verdade e passa pelo MESMO `exige(...)` das rotas do painel. Uma
porta paralela que não passasse pela checagem de permissão seria a forma mais
silenciosa de furar o modelo de papéis inteiro (v2.86).
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class TokenAutomacao(Base):
    __tablename__ = "token_automacao"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True,
                                          default=uuid.uuid4)
    # A quem o token dá acesso. As permissões são as DELE — o token não carrega
    # permissão própria, senão haveria duas fontes de verdade sobre o que a
    # automação pode, e elas divergiriam na primeira mudança de papel.
    usuario_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("usuario_rh.id", ondelete="CASCADE"), index=True)

    # Para que serve este token ("MCP do desktop do Bruno"). Obrigatório: com
    # vários tokens, "revogar o que vazou" exige saber qual é qual.
    descricao: Mapped[str] = mapped_column(String(200))

    # sha256 do segredo. O segredo em si não é guardado em lugar nenhum.
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)

    # Primeiros caracteres do segredo, só para a tela conseguir dizer QUAL token
    # é qual sem revelar nenhum ("mcp_a1b2c3…"). Não serve para autenticar.
    prefixo: Mapped[str] = mapped_column(String(16))

    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True),
                                                server_default=func.now())
    criado_por: Mapped[str | None] = mapped_column(String(200))  # snapshot do e-mail

    # Quando foi usado pela última vez. É o que responde "este token ainda está
    # em uso?" antes de revogar, e denuncia token esquecido vivo há meses.
    usado_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Revogar é marcar, nunca apagar: a linha é a prova de que a credencial
    # existiu e de quando deixou de valer.
    revogado_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revogado_por: Mapped[str | None] = mapped_column(String(200))

    # Validade opcional. Nulo = não expira (o caso normal de uma automação que
    # roda continuamente); com data, o token deixa de valer sozinho.
    expira_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    @property
    def valido(self) -> bool:
        """Só isto decide se o token vale. Concentrado numa propriedade porque
        espalhar a regra por chamadores faz uma das cópias esquecer de conferir
        `expira_em` — e a que esquece não dá erro, só aceita a mais."""
        from datetime import timezone as _tz
        if self.revogado_em is not None:
            return False
        if self.expira_em is not None:
            agora = datetime.now(_tz.utc)
            expira = self.expira_em
            if expira.tzinfo is None:          # coluna lida sem fuso
                expira = expira.replace(tzinfo=_tz.utc)
            if expira <= agora:
                return False
        return True
