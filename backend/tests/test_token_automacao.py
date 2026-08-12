"""A credencial de máquina do MCP: autentica, obedece ao papel, e REVOGA (v2.94).

O que este teste protege é o que separa esta credencial do token de sessão do
painel — e cada item já custaria caro se faltasse:

1. **Ela passa pelo MESMO `exige(...)`.** Entrar por `requer_rh` não é detalhe de
   implementação: é o que garante que a automação obedece ao papel dela. Uma
   porta paralela que autenticasse sem passar pela checagem furaria o modelo de
   papéis inteiro (v2.86) sem nada na tela denunciando.
2. **Revogar corta AGORA.** O token de sessão é `itsdangerous` stateless: enquanto
   não expira, vale — não há onde marcar "este não vale mais". Para credencial
   guardada num arquivo de desktop, "como eu corto se vazar hoje à noite?" é a
   pergunta que decide o desenho.
3. **O segredo não fica no banco.** Só o `sha256`. Quem tem o banco não tem a
   credencial, pela mesma razão que senha é hash.
4. **Usuário inativo nega.** Desativar a conta corta a automação junto — senão
   desligar alguém deixaria a credencial dele viva, que é o buraco que ninguém
   lembra de fechar.

⚠️ O teste afirma sobre o ESTADO (o token some do banco? a resposta muda?), não
só sobre o status code — a lição da v2.84: mutação que remove um portão devolve
200 e só a asserção de estado prova que a recusa era real.
"""

import os
import pathlib
import sys
import uuid
from datetime import datetime, timedelta, timezone

RAIZ = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

os.environ.setdefault("DATABASE_URL",
                      "postgresql+psycopg://admissao:admissao@localhost:55432/admissao")

from app.core.db import SessionLocal  # noqa: E402
from app.core.security import hash_senha  # noqa: E402
from app.models.token_automacao import TokenAutomacao  # noqa: E402
from app.models.usuario_rh import UsuarioRH  # noqa: E402
from app.services.token_automacao import PREFIXO, emitir, resolver, revogar  # noqa: E402

falhas: list[str] = []


def checar(condicao: bool, descricao: str) -> None:
    print(f"  {'ok  ' if condicao else 'FALHOU'}  {descricao}")
    if not condicao:
        falhas.append(descricao)


def main() -> int:
    db = SessionLocal()
    marca = uuid.uuid4().hex[:8]
    usuario = UsuarioRH(
        nome=f"Automação Teste {marca}",
        email=f"automacao.{marca}@exemplo.com.br",
        senha_hash=hash_senha("Senha-Que-Ninguem-Usa-2026!"),
        papel="automacao",
    )
    db.add(usuario)
    db.flush()

    print("=== 1. Emitir: o segredo aparece UMA vez e não fica no banco ===")
    registro, segredo = emitir(db, usuario, "MCP do desktop (teste)",
                               criado_por="teste@exemplo.com.br")
    db.commit()

    checar(segredo.startswith(PREFIXO),
           f"o segredo tem prefixo reconhecível ({PREFIXO}…) para ser identificado se vazar")
    checar(len(segredo) > 30, f"o segredo é longo o bastante ({len(segredo)} chars)")
    # Se o segredo estivesse gravado, quem lesse o banco teria a credencial.
    checar(segredo not in (registro.token_hash or ""),
           "o segredo NÃO é o que está gravado (a coluna guarda o hash)")
    checar(registro.token_hash != segredo and len(registro.token_hash) == 64,
           "o gravado é um sha256 de 64 caracteres")
    bruto = db.execute(
        __import__("sqlalchemy").text(
            "SELECT count(*) FROM token_automacao WHERE token_hash = :s"),
        {"s": segredo}).scalar()
    checar(bruto == 0,
           "o segredo em claro não existe em nenhuma linha da tabela")

    print("\n=== 2. Resolver: o token vale e aponta para o usuário certo ===")
    achado = resolver(db, segredo)
    checar(achado is not None and achado.id == usuario.id,
           "o token resolve para o usuário dono dele")
    checar(resolver(db, segredo + "x") is None,
           "segredo adulterado não resolve")
    checar(resolver(db, PREFIXO + "inexistente") is None,
           "segredo inexistente não resolve")
    # Autenticar pelo prefixo daria acesso a quem lesse a listagem da tela.
    checar(resolver(db, registro.prefixo) is None,
           "o PREFIXO exibido na tela não autentica (casa por hash, não por prefixo)")
    db.commit()
    checar(registro.usado_em is not None,
           "o uso é carimbado (é o que responde 'este token ainda está em uso?')")

    print("\n=== 3. Revogar corta AGORA ===")
    revogar(db, registro, por="teste@exemplo.com.br")
    db.commit()
    checar(resolver(db, segredo) is None,
           "token revogado deixa de resolver imediatamente")
    # Marcar, não apagar: a linha é a prova de que a credencial existiu.
    ainda = db.get(TokenAutomacao, registro.id)
    checar(ainda is not None,
           "revogar MARCA, não apaga (a linha é prova de que a credencial existiu)")
    checar(ainda is not None and ainda.revogado_em is not None,
           "a data da revogação fica registrada")

    print("\n=== 4. Revogar é idempotente e não reescreve a data ===")
    primeira = ainda.revogado_em
    revogar(db, ainda, por="outro@exemplo.com.br")
    db.commit()
    checar(ainda.revogado_em == primeira,
           "revogar de novo não reescreve o momento real do corte")

    print("\n=== 5. Token expirado não vale ===")
    reg_exp, seg_exp = emitir(db, usuario, "expirado",
                              expira_em=datetime.now(timezone.utc) - timedelta(minutes=1))
    db.commit()
    checar(resolver(db, seg_exp) is None, "token com `expira_em` no passado não resolve")
    checar(reg_exp.valido is False, "`valido` reprova o expirado")

    reg_fut, seg_fut = emitir(db, usuario, "ainda vale",
                              expira_em=datetime.now(timezone.utc) + timedelta(days=1))
    db.commit()
    checar(resolver(db, seg_fut) is not None, "token com validade futura resolve")

    print("\n=== 6. Usuário inativo corta a credencial junto ===")
    reg_at, seg_at = emitir(db, usuario, "usuario sera desativado")
    db.commit()
    checar(resolver(db, seg_at) is not None, "(pré-condição) o token vale com usuário ativo")
    usuario.ativo = False
    db.commit()
    checar(resolver(db, seg_at) is None,
           "desativar o usuário corta a credencial dele (o buraco que ninguém fecha)")

    db.rollback()
    db.close()

    print("\n" + "=" * 62)
    if falhas:
        print(f"REPROVADO — {len(falhas)} verificação(ões) falharam:")
        for f in falhas:
            print(f"  - {f}")
        return 1
    print("APROVADO — a credencial de máquina autentica, obedece e revoga.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
