"""Teste unitário das regras de _slots_aplicaveis — sem banco.

Foco no bug 2026-07-24: o slot do cartão DFTrans (cartao_vt) deve aparecer para
TODO optante do VT, mesmo sem o número do cartão digitado (antes exigia o número
e por isso o slot não aparecia — nem para o candidato nem para o RH).

Rode: PYTHONPATH=. .venv/Scripts/python.exe tests/test_slots.py
"""

from app.services.slots import _slots_aplicaveis
from app.models.documento import TipoDocumento
from app.models.ficha import DadosPessoais, ValeTransporte, Dependente


class _Stub:
    def __init__(self, **kw):
        self.__dict__.update(kw)


class _Scalars:
    def __init__(self, itens):
        self._itens = itens

    def all(self):
        return self._itens


class _DBFake:
    def __init__(self, pessoais=None, vt=None, dependentes=None):
        self._pessoais = pessoais
        self._vt = vt
        self._deps = dependentes or []

    def get(self, modelo, _id):
        if modelo is DadosPessoais:
            return self._pessoais
        if modelo is ValeTransporte:
            return self._vt
        return None

    def scalars(self, _stmt):
        return _Scalars(self._deps)


cand = _Stub(id="c1")


def tem_cartao_vt(db):
    return any(s["tipo"] == TipoDocumento.cartao_vt for s in _slots_aplicaveis(db, cand))


# optante SEM número do cartão => o slot DEVE aparecer (o bug era não aparecer)
assert tem_cartao_vt(_DBFake(vt=_Stub(optante=True, cartao_dftrans=None)))
assert tem_cartao_vt(_DBFake(vt=_Stub(optante=True, cartao_dftrans="")))
# optante COM número => também aparece
assert tem_cartao_vt(_DBFake(vt=_Stub(optante=True, cartao_dftrans="123456")))
# NÃO optante => slot não aparece
assert not tem_cartao_vt(_DBFake(vt=_Stub(optante=False, cartao_dftrans=None)))
# sem registro de VT => slot não aparece
assert not tem_cartao_vt(_DBFake(vt=None))

print("test_slots: OK")
