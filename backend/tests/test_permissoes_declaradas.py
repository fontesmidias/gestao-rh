"""Toda rota /rh/* declara uma permissão — ou o CI reprova (v2.86).

Teste ESTRUTURAL: lê os arquivos de `app/api/` com o `ast` da stdlib, sem subir
a app (é o que o permite rodar no passo rápido do `ci.yml`, junto do
`test_design_system.py`).

Por que ele existe: o `requer_rh` autentica e nada mais, então uma rota que se
proteger só com ele fica aberta a QUALQUER pessoa com login — inclusive à
recepcionista e ao gestor, que passam a ter conta a partir do módulo de
Processos. O defeito não aparece na tela: a rota funciona, devolve 200, e a
única forma de descobrir é alguém achar a URL. É a família do worker que não
roda (v2.66) e da lixeira de mão única (v2.72.2) — silêncio que parece
funcionamento.

⚠️ Ao criar rota nova sob `/rh/`, ou ela declara `Depends(exige("chave"))`, ou
entra em `SEM_PERMISSAO` abaixo COM justificativa. Não há terceira opção, e é
esse o ponto: "esqueci de declarar" e "decidi que é livre" precisam ser
distinguíveis por quem lê o código seis meses depois.
"""

import ast
import pathlib
import sys

RAIZ = pathlib.Path(__file__).resolve().parents[1]
API = RAIZ / "app" / "api"

sys.path.insert(0, str(RAIZ))
from app.services.permissoes import CHAVES  # noqa: E402


# Rotas `/rh/*` que legitimamente NÃO exigem permissão nomeada. Cada entrada
# precisa do porquê — a lista é curta de propósito e cresce com desconfiança.
SEM_PERMISSAO: dict[str, str] = {
    # Perfil próprio: todo usuário do painel mexe no que é dele, por definição.
    # Exigir permissão aqui criaria o absurdo de alguém não poder trocar a
    # própria senha.
    "/rh/me": "perfil próprio",
    "/rh/me/senha": "perfil próprio",
    # Credenciais: são as portas de ENTRADA, anteriores a qualquer sessão.
    "/rh/auth/login": "público por necessidade",
    "/rh/auth/primeiro-acesso": "público — portão é a tabela vazia (v2.84)",
    "/rh/auth/esqueci-senha": "público por necessidade",
    "/rh/auth/redefinir-senha": "público — validado pelo token do link",
    # Callbacks de OAuth: quem chama é o provedor, não o navegador de alguém
    # logado. A prova é o `state`, não a sessão.
    "/rh/config/m365/callback": "callback OAuth — provedor não manda token",
    "/rh/config/gmail/callback": "callback OAuth — provedor não manda token",
    # O catálogo de permissões e os papéis disponíveis: a própria tela de login
    # precisa saber o que o usuário pode para montar o menu.
    "/rh/permissoes/minhas": "responde sobre o próprio usuário",
}

METODOS = {"get", "post", "put", "patch", "delete"}


def _decoradores_de_rota(no: ast.FunctionDef) -> list[tuple[str, str]]:
    """Devolve (método, caminho) de cada `@router.<verbo>("/caminho")`."""
    achados = []
    for dec in no.decorator_list:
        if not isinstance(dec, ast.Call) or not isinstance(dec.func, ast.Attribute):
            continue
        if dec.func.attr not in METODOS or not dec.args:
            continue
        alvo = dec.args[0]
        if isinstance(alvo, ast.Constant) and isinstance(alvo.value, str):
            achados.append((dec.func.attr, alvo.value))
    return achados


def _chaves_exigidas(no: ast.AST) -> list[str]:
    """Todas as chaves passadas a `exige("...")` dentro de um nó."""
    chaves = []
    for filho in ast.walk(no):
        if (isinstance(filho, ast.Call) and isinstance(filho.func, ast.Name)
                and filho.func.id == "exige" and filho.args):
            arg = filho.args[0]
            if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                chaves.append(arg.value)
    return chaves


def _protecao_global(arvore: ast.Module) -> list[str]:
    """Chaves declaradas no `APIRouter(dependencies=[...])` do módulo."""
    for no in ast.walk(arvore):
        if (isinstance(no, ast.Call) and isinstance(no.func, ast.Name)
                and no.func.id == "APIRouter"):
            for kw in no.keywords:
                if kw.arg == "dependencies":
                    return _chaves_exigidas(kw.value)
    return []


def main() -> int:
    orfas: list[str] = []
    invalidas: list[str] = []
    total = 0
    protegidas = 0

    for arquivo in sorted(API.glob("*.py")):
        if arquivo.name == "__init__.py":
            continue
        arvore = ast.parse(arquivo.read_text(encoding="utf-8"))
        globais = _protecao_global(arvore)

        for no in ast.walk(arvore):
            if not isinstance(no, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            rotas = _decoradores_de_rota(no)
            if not rotas:
                continue
            # Chaves da própria rota: no decorador (dependencies=[...]) e na
            # assinatura (rh: UsuarioRH = Depends(exige("..."))).
            chaves = list(globais)
            for dec in no.decorator_list:
                chaves += _chaves_exigidas(dec)
            chaves += _chaves_exigidas(no.args)

            for metodo, caminho in rotas:
                if not caminho.startswith("/rh"):
                    continue  # rota pública: coberta por outros testes
                total += 1
                for chave in chaves:
                    if chave not in CHAVES:
                        invalidas.append(
                            f"{arquivo.name}:{no.lineno} {metodo.upper()} {caminho} "
                            f"→ permissão fora do catálogo: {chave!r}")
                if chaves:
                    protegidas += 1
                elif caminho not in SEM_PERMISSAO:
                    orfas.append(
                        f"{arquivo.name}:{no.lineno} {metodo.upper()} {caminho} "
                        f"(função {no.name})")

    if invalidas:
        print("FALHOU — permissão que não existe no catálogo:")
        for linha in invalidas:
            print("  •", linha)
    if orfas:
        print(f"FALHOU — {len(orfas)} rota(s) /rh/* sem permissão declarada.")
        print("  Cada uma precisa de Depends(exige(\"chave\")) — ou entrar em")
        print("  SEM_PERMISSAO no topo deste arquivo, COM a justificativa.")
        for linha in orfas:
            print("  •", linha)

    if invalidas or orfas:
        return 1

    print(f"OK — {protegidas} de {total} rotas /rh/* com permissão declarada; "
          f"{len(SEM_PERMISSAO)} isenções justificadas.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
