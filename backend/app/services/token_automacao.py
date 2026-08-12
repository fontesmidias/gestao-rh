"""Emissão e validação da credencial de máquina do MCP (v2.94).

Ver `models/token_automacao.py` para o porquê de não reusar o token de sessão.
Aqui ficam as três operações e as regras que as sustentam.
"""

import hashlib
import logging
import secrets
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.token_automacao import TokenAutomacao
from app.models.usuario_rh import UsuarioRH

log = logging.getLogger(__name__)

# Prefixo reconhecível: quem achar a string num arquivo sabe o que é e o que
# revogar. É a mesma razão de `sk-`/`ghp_` — credencial anônima vazada demora
# muito mais para ser identificada e cortada.
PREFIXO = "mcp_"
_BYTES = 32          # 256 bits


def _hash(segredo: str) -> str:
    return hashlib.sha256(segredo.encode()).hexdigest()


def emitir(db: Session, usuario: UsuarioRH, descricao: str,
           criado_por: str | None = None,
           expira_em: datetime | None = None) -> tuple[TokenAutomacao, str]:
    """Cria a credencial e devolve `(registro, segredo)`.

    **O segredo só existe neste retorno.** Quem chama tem uma única chance de
    mostrá-lo; o banco guarda apenas o sha256. Se a pessoa perder, emite outro e
    revoga o anterior — que é o comportamento certo, e não um incômodo a
    contornar guardando o segredo "só por garantia".
    """
    segredo = PREFIXO + secrets.token_urlsafe(_BYTES)
    registro = TokenAutomacao(
        usuario_id=usuario.id,
        descricao=descricao.strip()[:200],
        token_hash=_hash(segredo),
        prefixo=segredo[:12],
        criado_por=criado_por,
        expira_em=expira_em,
    )
    db.add(registro)
    db.flush()
    return registro, segredo


def resolver(db: Session, apresentado: str) -> UsuarioRH | None:
    """Devolve o usuário do token, ou `None` se ele não vale.

    Regras que NÃO devem ser afrouxadas:

    - **Casa por HASH, nunca por prefixo.** O prefixo existe só para a tela
      distinguir um token do outro; autenticar por ele daria acesso a quem
      lesse a listagem.
    - **Usuário inativo NEGA.** Desativar a conta tem que cortar a automação
      junto — senão desligar alguém deixaria a credencial dele viva, que é
      exatamente o buraco que ninguém lembra de fechar.
    - **Devolve `None` para todos os motivos** (não existe, revogado, expirado,
      usuário inativo). Distinguir na RESPOSTA diria a quem testa credenciais
      qual delas já existiu.
    """
    if not apresentado or not apresentado.startswith(PREFIXO):
        return None

    registro = db.scalar(select(TokenAutomacao).where(
        TokenAutomacao.token_hash == _hash(apresentado)))
    if registro is None or not registro.valido:
        return None

    usuario = db.get(UsuarioRH, registro.usuario_id)
    if usuario is None or not usuario.ativo:
        return None

    # Carimbo de uso: é o que responde "este token ainda está em uso?" antes de
    # revogar. Granularidade de minuto para não escrever a cada chamada — a
    # pergunta é "foi usado hoje?", não "às 14:03:07".
    agora = datetime.now(timezone.utc)
    anterior = registro.usado_em
    if anterior is None or (agora - anterior).total_seconds() > 60:
        registro.usado_em = agora

    return usuario


def revogar(db: Session, registro: TokenAutomacao, por: str | None = None) -> None:
    """Corta o acesso. **Marca, não apaga** — a linha é a prova de que a
    credencial existiu e de quando deixou de valer. Idempotente: revogar duas
    vezes não reescreve a data da primeira, senão a segunda chamada apagaria o
    momento real do corte."""
    if registro.revogado_em is None:
        registro.revogado_em = datetime.now(timezone.utc)
        registro.revogado_por = por
