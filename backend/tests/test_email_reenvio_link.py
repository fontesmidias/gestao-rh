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
    # request é necessário para base_url_publica (o link precisa do host certo).
    assert "request" in inspect.signature(getattr(revisao, _rota)).parameters, (
        f"{_rota}() precisa receber `request` para montar a URL pública."
    )

# --------------------------------------------- o e-mail RENDERIZADO tem o link
# Estes asserts eram sobre a IMPLEMENTAÇÃO (procuravam "botao_url" e "if link"
# no código-fonte) e quebraram na v2.06, quando os textos viraram template
# editável — uma mudança legítima. Agora testam a GARANTIA: renderiza o e-mail
# de verdade e confere que o link chega ao destinatário.
from app.services.email_templates import renderizar  # noqa: E402


class _DBVazio:
    """Sem template salvo: cai no padrão do catálogo (o fallback)."""

    def get(self, *_a, **_kw):
        return None


for _chave, _ctx in (
    ("documento_rejeitado",
     {"nome": "Maria Souza", "primeiro_nome": "Maria", "motivo": "ilegível",
      "link": "https://exemplo/c/tok123"}),
    ("documentos_rejeitados_lote",
     {"nome": "Maria Souza", "motivo": "vencido", "lista": "- rg",
      "link": "https://exemplo/c/tok123"}),
):
    _a, _txt, _html = renderizar(_DBVazio(), _chave, _ctx)
    assert "https://exemplo/c/tok123" in _html, (
        f"{_chave}: o link não chegou ao HTML — a pessoa recebe um e-mail "
        f"mandando reenviar e não tem como voltar ao sistema."
    )
    assert "<a href" in _html, f"{_chave}: o botão clicável sumiu do e-mail."

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

# link ausente (candidato sem e-mail) não pode virar a string "None" no corpo
for _chave, _ctx in (
    ("documento_rejeitado", {"nome": "Maria", "primeiro_nome": "Maria",
                             "motivo": "ilegível", "link": None}),
    ("documentos_rejeitados_lote", {"nome": "Maria", "motivo": "vencido",
                                    "lista": "- rg", "link": None}),
):
    _a, _txt, _html = renderizar(_DBVazio(), _chave, _ctx)
    assert "None" not in _txt and "None" not in _html, (
        f"{_chave}: link ausente virou a string 'None' no corpo do e-mail."
    )
    assert "<a href" not in _html, (
        f"{_chave}: gerou botão sem destino quando não há link."
    )

print("test_email_reenvio_link: OK")
