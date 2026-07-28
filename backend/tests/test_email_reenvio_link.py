"""Regressão dos DOIS defeitos que produziam o "ciclo eterno" de 2026-07-28.

O RH rejeitava um documento, a pessoa recebia um e-mail mandando "acessar o
mesmo link da sua admissão" — sem link nenhum — e, quando tentava pedir um novo
pelo portal, o botão de socorro respondia 500. Não era falta de instrução da
pessoa: o caminho de volta estava quebrado nas duas pontas.

1. ``entrada.py::link_por_email`` chamava ``_bloqueado()``, que não existe no
   módulo (é ``kba.bloqueado``) — NameError → 500 em TODA chamada.
2. ``revisao.py::rejeitar`` e ``::rejeitar_lote`` não emitiam link mágico algum,
   ao contrário de ``rh_ficha.py``, que já fazia certo.

Rode: PYTHONPATH=. .venv/Scripts/python.exe tests/test_email_reenvio_link.py
"""

import ast
import inspect
from pathlib import Path

from app.api import entrada, revisao
from app.services.email import html_moderno

RAIZ = Path(__file__).resolve().parent.parent / "app" / "api"


def _fonte(modulo, nome):
    return inspect.getsource(getattr(modulo, nome))


def _nomes_chamados(codigo: str) -> set[str]:
    """Nomes de função chamados no CORPO da rota (decorador fica de fora — o
    ``@router.post`` não é código que roda na requisição)."""
    arvore = ast.parse(inspect.cleandoc(codigo))
    chamados = set()
    for func in arvore.body:
        if not isinstance(func, ast.FunctionDef):
            continue
        for no in ast.walk(ast.Module(body=func.body, type_ignores=[])):
            if isinstance(no, ast.Call):
                if isinstance(no.func, ast.Name):
                    chamados.add(no.func.id)
                elif isinstance(no.func, ast.Attribute):
                    chamados.add(no.func.attr)
    return chamados


# ---------------------------------------------------------------- defeito 1
# O socorro "me manda o link por e-mail" não pode referenciar nome inexistente.
fonte_link_email = _fonte(entrada, "link_por_email")
assert "_bloqueado(" not in fonte_link_email, (
    "link_por_email voltou a chamar _bloqueado() — esse nome não existe no "
    "módulo e derruba a rota com NameError (500). Use kba.bloqueado()."
)
assert "bloqueado" in _nomes_chamados(fonte_link_email), (
    "link_por_email perdeu o bloqueio por IP — a rota é anti-enumeração e "
    "precisa de rate limit."
)

# Todo nome chamado na rota tem que existir de fato (o bug era exatamente este).
_globais = vars(entrada)
for _chamado in _nomes_chamados(fonte_link_email):
    if _chamado in _globais or hasattr(entrada.kba, _chamado):
        continue
    # métodos de objeto/str e builtins não são resolvíveis estaticamente
    if _chamado in dir(__builtins__) or _chamado in {
        "split", "title", "join", "isdigit", "get", "commit", "add", "flush",
    }:
        continue
    raise AssertionError(
        f"link_por_email chama '{_chamado}', que não existe no módulo entrada "
        f"nem em kba — mesmo modo de falha do NameError de 2026-07-28."
    )

# ---------------------------------------------------------------- defeito 2
# As duas rotas de rejeição precisam EMITIR link mágico, como rh_ficha.py faz.
assert hasattr(revisao, "emitir_link"), (
    "revisao.py não importa emitir_link — os e-mails de rejeição voltariam a "
    "mandar 'acesse o mesmo link' sem link."
)

for _rota in ("rejeitar", "rejeitar_lote"):
    _src = _fonte(revisao, _rota)
    assert "emitir_link" in _nomes_chamados(_src), (
        f"{_rota}() não emite link mágico. A pessoa recebe um e-mail mandando "
        f"reenviar um documento e não tem como voltar ao sistema."
    )
    assert "botao_url" in _src, (
        f"{_rota}() não passa botao_url ao html_moderno — sem botão, o link "
        f"não aparece de forma clicável no e-mail."
    )
    # A frase antiga é o sintoma: mandava acessar um link que não vinha junto.
    assert "mesmo link da sua admissão e" not in _src, (
        f"{_rota}() ainda manda 'acesse o mesmo link da sua admissão' como "
        f"instrução principal — o link agora vai no próprio e-mail."
    )
    # request é necessário para base_url_publica (o link precisa do host certo).
    assert "request" in inspect.signature(getattr(revisao, _rota)).parameters, (
        f"{_rota}() precisa receber `request` para montar a URL pública."
    )

# ------------------------------------------------- candidato sem e-mail (None)
# enviar_email() retorna cedo sem destinatário, mas o corpo é montado ANTES —
# não pode conter a string "None" no lugar do link.
_html_sem_link = html_moderno("t", ["p"], botao_texto="Reenviar", botao_url=None)
assert "None" not in _html_sem_link, (
    "html_moderno imprimiu 'None' no lugar do botão quando a URL é nula."
)
assert "<a href" not in _html_sem_link, (
    "html_moderno gerou um <a> sem destino válido."
)

# O texto puro das duas rotas tem ramo alternativo para link ausente.
for _rota in ("rejeitar", "rejeitar_lote"):
    _src = _fonte(revisao, _rota)
    assert "if link" in _src, (
        f"{_rota}() monta o corpo em texto puro sem tratar link=None — "
        f"candidato sem e-mail geraria 'Acesse ...: None'."
    )

print("test_email_reenvio_link: OK")
