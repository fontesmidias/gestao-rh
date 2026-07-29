"""Retomada de acesso no creche e no portal (v2.03, feedback 2026-07-28).

O ciclo que o Bruno relatou: a pessoa recebe o link, abre no app de e-mail
(webview), sai para ler o código, volta — e a tela zerou, porque o token de
sessão só existia depois de acertar o código e vivia apenas na memória do
navegador. O backend considerava a sessão válida por 6h; o front jogava fora
em 6 segundos.

A correção: o AcessoCreche/AcessoPortal nasce com token REAL no envio do
código, e esse token vai no e-mail. Regra inegociável (Vex, aceita pelo Bruno):

    o link IDENTIFICA sempre, AUTENTICA nunca.

Quem valida continua sendo o código. O único acesso que entra direto é o
emitido pelo RH (devolução do creche, v1.82), que nasce `confirmado_em`
porque o e-mail já foi comprovado antes.

Precisa dos containers de teste (pg-teste/minio-teste).
Rode: PYTHONPATH=. .venv/Scripts/python.exe tests/test_retomada_acesso.py
"""

import os
import secrets
import uuid
from datetime import datetime, timedelta, timezone

os.environ.setdefault(
    "DATABASE_URL", "postgresql+psycopg://admissao:admissao@localhost:55432/admissao")
os.environ.setdefault("MINIO_ENDPOINT", "localhost:59000")
os.environ.setdefault("MINIO_ACCESS_KEY", "minio")
os.environ.setdefault("MINIO_SECRET_KEY", "minio12345")
os.environ.setdefault("MINIO_SECURE", "false")
os.environ.setdefault("SECRET_KEY", "segredo-de-teste")
os.environ.setdefault("BASE_URL", "http://localhost:8090")

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import select, update  # noqa: E402

from app.api.creche_publico import _hash  # noqa: E402
from app.core.db import SessionLocal  # noqa: E402
from app.main import app  # noqa: E402
from app.models.beneficio import AcessoCreche, BeneficioCreche  # noqa: E402
from app.models.candidato import Candidato, SituacaoColaborador  # noqa: E402
from app.models.desenvolvimento import AcessoPortal  # noqa: E402

c = TestClient(app)


def _cpf_novo() -> str:
    """CPF sintético válido (dígitos verificadores calculados)."""
    base = [int(x) for x in f"{secrets.randbelow(10**9):09d}"]
    for _ in range(2):
        peso = len(base) + 1
        s = sum(v * (peso - i) for i, v in enumerate(base))
        d = (s * 10) % 11
        base.append(0 if d == 10 else d)
    return "".join(map(str, base))


def _colaborador(cpf: str) -> uuid.UUID:
    with SessionLocal() as db:
        col = Candidato(nome_completo="Maria Retomada Teste", cpf=cpf,
                        email=f"maria{cpf[:5]}@example.com",
                        situacao=SituacaoColaborador.ativo)
        db.add(col)
        db.commit()
        return col.id


# ---------------------------------------------------------------- CRECHE
cpf = _cpf_novo()
col_id = _colaborador(cpf)

r = c.post("/api/creche/iniciar", json={"cpf": cpf})
assert r.status_code == 200, r.text

# o acesso nasce COM token real (antes era um placeholder inutilizável)
with SessionLocal() as db:
    ben = db.scalar(select(BeneficioCreche).where(
        BeneficioCreche.candidato_id == col_id))
    ben_id = ben.id
    ac = db.scalars(select(AcessoCreche).where(
        AcessoCreche.beneficio_id == ben_id)).first()
    assert ac is not None, "nenhum AcessoCreche criado no envio do código"
    assert ac.confirmado_em is None, "acesso de código NÃO pode nascer confirmado"

# Sem saber o token não dá para retomar; simulamos o que chega no e-mail
# gerando um acesso equivalente e conferindo o CONTRATO da rota.
token_codigo = secrets.token_urlsafe(32)
with SessionLocal() as db:
    db.add(AcessoCreche(
        beneficio_id=ben_id, token_hash=_hash(token_codigo),
        codigo_hash=_hash("123456"),
        codigo_expira_em=datetime.now(timezone.utc) + timedelta(minutes=15),
        expira_em=datetime.now(timezone.utc) + timedelta(hours=6)))
    db.commit()

r = c.get(f"/api/creche/retomar/{token_codigo}")
assert r.status_code == 200, r.text
d = r.json()
assert d["primeiro_nome"] == "Maria", d
assert d["cpf_final"] == cpf[-4:], d
# A REGRA: link de código identifica, mas não deixa entrar.
assert d["pode_entrar"] is False, "link do código NÃO pode virar sessão sozinho"
assert d["aguardando_codigo"] is True, d
# E não vaza dado pessoal além do necessário para reconhecer a tentativa.
assert set(d) == {"primeiro_nome", "cpf_final", "pode_entrar", "aguardando_codigo"}, d
assert cpf not in r.text, "CPF completo não pode sair na resposta"

# confirmar SEM cpf, só com o token da retomada: é o caminho de quem voltou
r = c.post("/api/creche/confirmar", json={"codigo": "123456", "retomada": token_codigo})
assert r.status_code == 200, f"retomada não confirmou: {r.text}"
sessao = r.json()["token"]
assert c.get(f"/api/creche/sessao/{sessao}").status_code == 200

# o token de RETOMADA não vira sessão nem depois de confirmado
r = c.get(f"/api/creche/sessao/{token_codigo}")
assert r.status_code == 401, "token do e-mail não pode valer como token de sessão"

# link inexistente/expirado cai em 404 tratado (front manda para a tela de CPF)
assert c.get(f"/api/creche/retomar/{secrets.token_urlsafe(32)}").status_code == 404
with SessionLocal() as db:
    db.execute(update(AcessoCreche)
               .where(AcessoCreche.token_hash == _hash(token_codigo))
               .values(expira_em=datetime.now(timezone.utc) - timedelta(seconds=1)))
    db.commit()
assert c.get(f"/api/creche/retomar/{token_codigo}").status_code == 404, \
    "link vencido tem que ser recusado"

# --------------------------------------------------- CRECHE: acesso do RH
# O da devolução (v1.82) nasce confirmado e ESSE entra direto.
from app.api.creche_publico import emitir_acesso_devolucao  # noqa: E402

with SessionLocal() as db:
    ben = db.get(BeneficioCreche, ben_id)
    token_dev = emitir_acesso_devolucao(db, ben)
    db.commit()
d = c.get(f"/api/creche/retomar/{token_dev}").json()
assert d["pode_entrar"] is True, "acesso emitido pelo RH deve entrar direto"
assert c.get(f"/api/creche/sessao/{token_dev}").status_code == 200

# ---------------------------------------------------------------- PORTAL
cpf2 = _cpf_novo()
col2_id = _colaborador(cpf2)
r = c.post("/api/portal/iniciar", json={"cpf": cpf2})
assert r.status_code == 200, r.text

with SessionLocal() as db:
    ac = db.scalars(select(AcessoPortal).where(
        AcessoPortal.candidato_id == col2_id)).first()
    assert ac is not None and ac.confirmado_em is None

token_portal = secrets.token_urlsafe(32)
with SessionLocal() as db:
    db.add(AcessoPortal(
        candidato_id=col2_id, token_hash=_hash(token_portal),
        codigo_hash=_hash("654321"),
        codigo_expira_em=datetime.now(timezone.utc) + timedelta(minutes=15),
        expira_em=datetime.now(timezone.utc) + timedelta(hours=6)))
    db.commit()

d = c.get(f"/api/portal/retomar/{token_portal}").json()
assert d["primeiro_nome"] == "Maria" and d["cpf_final"] == cpf2[-4:], d
assert d["pode_entrar"] is False, "link do código do portal não pode entrar sozinho"

r = c.post("/api/portal/confirmar", json={"codigo": "654321", "retomada": token_portal})
assert r.status_code == 200, f"retomada do portal não confirmou: {r.text}"
assert c.get(f"/api/portal/sessao/{r.json()['token']}").status_code == 200
assert c.get(f"/api/portal/sessao/{token_portal}").status_code == 401


# ===================================================================== v2.17
# O LINK DO E-MAIL ENTRA DIRETO (feedback de campo 2026-07-29).
#
# O RH ficou sem conseguir entrar no creche: "foi eu mesmo quem copiou e colou
# o código, impossível ter erro". Era verdade — o código estava certo. O que
# houve: o limite é 5 pedidos por CPF a cada 15 min; no 6º o e-mail NÃO saiu,
# mas a tela avançou para "digite o código" assim mesmo, e ele colou o código
# do e-mail ANTERIOR. Sucesso mentiroso, terceira vez nesta leva.
#
# Decisão do Bruno: o link do e-mail passa a ENTRAR DIRETO, com o código como
# reserva no mesmo e-mail. O raciocínio (Vex e Winston): código e link chegam
# na MESMA caixa, logo provam o MESMO fator — exigir os dois era atrito
# duplicado, não segurança em camadas.
from app.api import creche_publico as _cp  # noqa: E402

_cap = {}
_orig_env = _cp.enviar_modelo


def _capturar(db, chave, dest, ctx, **kw):
    _cap.update(codigo=ctx.get("codigo"), link=ctx.get("link"))
    return True


cpf_link = _cpf_novo()
col_link = _colaborador(cpf_link)
_cp.enviar_modelo = _capturar
try:
    assert c.post("/api/creche/iniciar", json={"cpf": cpf_link}).status_code == 200
    tok_link = (_cap["link"] or "").split("?t=")[-1]
    assert tok_link, f"o e-mail do código precisa levar o link: {_cap}"

    # 1) o link ABRE a sessão sozinho — sem digitar código
    r = c.get(f"/api/creche/retomar/{tok_link}")
    assert r.status_code == 200, r.text
    assert r.json()["pode_entrar"] is True, (
        "o link do e-mail tem que entrar direto (decisão de 2026-07-29)")
    assert c.get(f"/api/creche/sessao/{tok_link}").status_code == 200, (
        "o `pode_entrar` prometeu sessão que o token não abre")

    # 2) uso ÚNICO: um segundo clique não reabre nada por si
    with SessionLocal() as db:
        _ac = db.scalar(select(AcessoCreche).where(
            AcessoCreche.token_hash == _hash(tok_link)))
        assert _ac.link_expira_em <= datetime.now(timezone.utc), (
            "o link deveria ter sido consumido no primeiro uso")

    # 3) o CÓDIGO continua valendo depois de o link ter sido usado — quem
    #    clicou no link e mesmo assim digitou o código não pode levar erro
    r = c.post("/api/creche/confirmar",
               json={"cpf": cpf_link, "codigo": _cap["codigo"]})
    assert r.status_code == 200, (
        f"código certo recusado depois do link: {r.text} — foi exatamente a "
        f"reclamação do RH em campo")

    # 4) código ERRADO continua sendo recusado (o link não afrouxou isso)
    assert c.post("/api/creche/confirmar",
                  json={"cpf": cpf_link, "codigo": "000000"}).status_code == 422

    # 5) link VENCIDO não entra (o TTL do link é o mesmo do código: 15 min)
    _cap.clear()
    c.post("/api/creche/iniciar", json={"cpf": cpf_link})
    tok2 = (_cap["link"] or "").split("?t=")[-1]
    with SessionLocal() as db:
        db.execute(update(AcessoCreche)
                   .where(AcessoCreche.token_hash == _hash(tok2))
                   .values(link_expira_em=datetime.now(timezone.utc) - timedelta(minutes=1)))
        db.commit()
    r = c.get(f"/api/creche/retomar/{tok2}")
    assert r.status_code == 200 and r.json()["pode_entrar"] is False, (
        "link vencido não pode entrar direto")
finally:
    _cp.enviar_modelo = _orig_env

print("  (v2.17: link entra direto, código segue valendo)")

print("test_retomada_acesso: OK")
