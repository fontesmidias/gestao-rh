"""O fluxo OAuth de ponta a ponta, contra banco de verdade.

Cobre o que só aparece quando as peças correm juntas: PKCE, replay de código,
rotação do refresh com detecção de reuso, recusa por papel e o corte do acesso
quando a conta é desativada.

⚠️ **`raise_server_exceptions=False`**: sem isso, uma exceção do servidor sobe
pelo TestClient e mata o script no meio — sem imprimir nenhum "FALHOU", e a
saída vazia passa por sucesso (a lição da v2.72.2). Com a flag, o 500 vira
resposta e a asserção pode reprová-lo.

⚠️ Teste destrutivo: cria usuários e clientes. Confere a pré-condição, ANUNCIA
quando ela está quebrada e limpa no fim — teste que suja o banco faz a próxima
execução falhar por um motivo que não tem nada a ver com o que se testa (v2.66).

Precisa de banco: roda no passo do CI com a stack de pé.
"""

import base64
import hashlib
import os
import sys
import uuid

os.environ.setdefault("MCP_ISSUER", "https://portal.exemplo.test")

from sqlalchemy import select  # noqa: E402

from app.core.db import SessionLocal  # noqa: E402
from app.core.security import hash_senha  # noqa: E402
from app.models.mcp_oauth import ClienteOAuth, CodigoAutorizacao, Concessao  # noqa: E402
from app.models.usuario_rh import UsuarioRH  # noqa: E402
from app.services import mcp_oauth as oauth  # noqa: E402

# ⚠️ Importados só para o SQLAlchemy resolver as FKs (v2.64). `registrar()`
# grava em `evento_auditoria`, que aponta para `candidato` — e um modelo só
# entra no `metadata` quando é importado. Sem estas linhas, o primeiro `flush`
# estoura com `NoReferencedTableError: could not find table 'candidato'`, e a
# mensagem fala do VIZINHO, não do modelo que se está testando. Este teste não
# sobe a app (que importaria tudo pela cadeia do `main`), então importa à mão.
import app.models.candidato  # noqa: E402,F401
import app.models.evento  # noqa: E402,F401

falhas = []
SUFIXO = uuid.uuid4().hex[:8]
SENHA = "teste-oauth-mcp-123"
REDIRECT = "https://claude.ai/api/mcp/auth_callback"


def _pkce():
    verifier = base64.urlsafe_b64encode(os.urandom(40)).decode().rstrip("=")
    desafio = base64.urlsafe_b64encode(
        hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")
    return verifier, desafio


def _criar_usuario(db, papel: str) -> UsuarioRH:
    u = UsuarioRH(nome=f"Teste {papel}", email=f"mcp-{papel}-{SUFIXO}@exemplo.test",
                  senha_hash=hash_senha(SENHA), ativo=True, papel=papel)
    db.add(u)
    db.flush()
    return u


def _cliente(db) -> ClienteOAuth:
    return oauth.registrar_cliente(db, "Claude (teste)", [REDIRECT], ip="127.0.0.1")


def _autorizar(cliente_http, cliente, usuario, verifier_desafio, decisao="autorizar"):
    """Faz o POST do consentimento e devolve a resposta (sem seguir o redirect)."""
    _, desafio = verifier_desafio
    return cliente_http.post("/authorize", data={
        "client_id": cliente.client_id, "redirect_uri": REDIRECT,
        "code_challenge": desafio, "resource": oauth.resource(),
        "email": usuario.email, "senha": SENHA, "decisao": decisao,
    }, follow_redirects=False)


def rodar():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from app.api import mcp_autorizacao, mcp_oauth as descoberta, mcp_token

    app = FastAPI()
    app.include_router(descoberta.router)
    app.include_router(mcp_autorizacao.router)
    app.include_router(mcp_token.router)
    http = TestClient(app, raise_server_exceptions=False)

    db = SessionLocal()
    criados = []
    try:
        rh = _criar_usuario(db, "rh")
        recepcao = _criar_usuario(db, "recepcao")
        cliente = _cliente(db)
        criados = [rh.id, recepcao.id, cliente.id]
        db.commit()

        # ── 1. Fluxo feliz ────────────────────────────────────────────────
        verifier, desafio = _pkce()
        r = _autorizar(http, cliente, rh, (verifier, desafio))
        if r.status_code != 303:
            falhas.append(f"autorizar deveria redirecionar (303), veio {r.status_code}")
            return
        destino = r.headers.get("location", "")
        if "code=" not in destino:
            falhas.append(f"o redirect não trouxe o code: {destino}")
            return
        if "iss=" not in destino:
            falhas.append("o redirect não trouxe o `iss` (RFC 9207) — o cliente "
                          "não consegue detectar mix-up.")
        code = destino.split("code=")[1].split("&")[0]

        r = http.post("/token", data={
            "grant_type": "authorization_code", "code": code,
            "redirect_uri": REDIRECT, "client_id": cliente.client_id,
            "code_verifier": verifier, "resource": oauth.resource()})
        if r.status_code != 200:
            falhas.append(f"/token recusou o fluxo feliz: {r.status_code} {r.text[:200]}")
            return
        dados = r.json()
        for campo in ("access_token", "refresh_token", "token_type", "expires_in"):
            if campo not in dados:
                falhas.append(f"resposta do /token sem `{campo}`")
        if r.headers.get("cache-control") != "no-store":
            falhas.append("resposta do /token sem `Cache-Control: no-store` — a "
                          "credencial pode ficar em cache intermediário.")
        access, refresh = dados.get("access_token"), dados.get("refresh_token")

        # ── 2. O access resolve, e com o papel do ASSISTENTE ───────────────
        identidade = oauth.identidade_do_access_token(db, access)
        if identidade is None:
            falhas.append("o access token emitido não resolve.")
        elif identidade.papel != oauth.PAPEL_DO_TOKEN:
            falhas.append(f"o access resolveu com papel {identidade.papel!r} — "
                          f"deveria ser {oauth.PAPEL_DO_TOKEN!r}.")
        # E o papel REAL no banco não pode ter sido tocado.
        db.expire_all()
        if db.get(UsuarioRH, rh.id).papel != "rh":
            falhas.append("⚠️ o papel REAL da pessoa foi reescrito no banco pela "
                          "resolução do token.")

        # ── 3. Replay do código: recusa E revoga a concessão ───────────────
        r = http.post("/token", data={
            "grant_type": "authorization_code", "code": code,
            "redirect_uri": REDIRECT, "client_id": cliente.client_id,
            "code_verifier": verifier, "resource": oauth.resource()})
        if r.status_code != 400 or r.json().get("error") != "invalid_grant":
            falhas.append(f"código reapresentado deveria dar invalid_grant, veio "
                          f"{r.status_code} {r.text[:120]}")
        db.expire_all()
        if oauth.identidade_do_access_token(db, access) is not None:
            falhas.append("⚠️ replay do código não revogou a concessão — o access "
                          "emitido continua valendo.")

        # ── 4. PKCE errado ────────────────────────────────────────────────
        verifier2, desafio2 = _pkce()
        r = _autorizar(http, cliente, rh, (verifier2, desafio2))
        code2 = r.headers["location"].split("code=")[1].split("&")[0]
        r = http.post("/token", data={
            "grant_type": "authorization_code", "code": code2,
            "redirect_uri": REDIRECT, "client_id": cliente.client_id,
            "code_verifier": "verifier-que-nao-confere", "resource": oauth.resource()})
        if r.status_code != 400 or r.json().get("error") != "invalid_grant":
            falhas.append("PKCE errado deveria dar invalid_grant — sem isso, quem "
                          "interceptar o código consegue trocá-lo.")

        # ── 5. resource de outro serviço ──────────────────────────────────
        verifier3, desafio3 = _pkce()
        r = _autorizar(http, cliente, rh, (verifier3, desafio3))
        code3 = r.headers["location"].split("code=")[1].split("&")[0]
        r = http.post("/token", data={
            "grant_type": "authorization_code", "code": code3,
            "redirect_uri": REDIRECT, "client_id": cliente.client_id,
            "code_verifier": verifier3, "resource": "https://outro-servico.test/mcp"})
        if r.json().get("error") != "invalid_target":
            falhas.append("resource de outro serviço deveria dar invalid_target "
                          "(RFC 8707).")

        # ── 6. Rotação do refresh e detecção de reuso ──────────────────────
        r = http.post("/token", data={
            "grant_type": "refresh_token", "refresh_token": refresh,
            "client_id": cliente.client_id, "resource": oauth.resource()})
        # A concessão do fluxo 1 foi revogada no passo 3, então este refresh já
        # não vale — o que também é uma asserção útil.
        if r.status_code == 200:
            falhas.append("refresh de concessão revogada foi aceito.")

        # Fluxo novo, só para a rotação.
        verifier4, desafio4 = _pkce()
        r = _autorizar(http, cliente, rh, (verifier4, desafio4))
        code4 = r.headers["location"].split("code=")[1].split("&")[0]
        dados4 = http.post("/token", data={
            "grant_type": "authorization_code", "code": code4,
            "redirect_uri": REDIRECT, "client_id": cliente.client_id,
            "code_verifier": verifier4, "resource": oauth.resource()}).json()
        refresh4 = dados4["refresh_token"]

        novo = http.post("/token", data={
            "grant_type": "refresh_token", "refresh_token": refresh4,
            "client_id": cliente.client_id, "resource": oauth.resource()})
        if novo.status_code != 200:
            falhas.append(f"renovação recusada: {novo.text[:150]}")
        else:
            refresh5 = novo.json().get("refresh_token")
            if refresh5 == refresh4:
                falhas.append("⚠️ o refresh NÃO rotacionou — o mesmo voltou.")
            # Reapresentar o antigo é sinal de roubo: revoga tudo.
            r = http.post("/token", data={
                "grant_type": "refresh_token", "refresh_token": refresh4,
                "client_id": cliente.client_id, "resource": oauth.resource()})
            if r.json().get("error") != "invalid_grant":
                falhas.append("refresh antigo reapresentado deveria dar invalid_grant.")
            r = http.post("/token", data={
                "grant_type": "refresh_token", "refresh_token": refresh5,
                "client_id": cliente.client_id, "resource": oauth.resource()})
            if r.status_code == 200:
                falhas.append("⚠️ reuso detectado NÃO revogou a concessão — o "
                              "refresh atual continua valendo nas mãos de quem "
                              "roubou o antigo.")

        # ── 7. Recusa por papel ───────────────────────────────────────────
        verifier6, desafio6 = _pkce()
        r = _autorizar(http, cliente, recepcao, (verifier6, desafio6))
        if r.status_code != 403:
            falhas.append(f"papel 'recepcao' deveria receber 403 com explicação, "
                          f"veio {r.status_code}")
        elif "não está liberado" not in r.text:
            falhas.append("a recusa por papel não explica o motivo na tela.")
        db.expire_all()
        emitidos = db.scalars(select(CodigoAutorizacao).where(
            CodigoAutorizacao.usuario_id == recepcao.id)).all()
        if emitidos:
            falhas.append("⚠️ foi emitido código para um papel que não pode conectar.")

        # ── 8. Desativar a conta corta o acesso ───────────────────────────
        verifier7, desafio7 = _pkce()
        r = _autorizar(http, cliente, rh, (verifier7, desafio7))
        code7 = r.headers["location"].split("code=")[1].split("&")[0]
        d7 = http.post("/token", data={
            "grant_type": "authorization_code", "code": code7,
            "redirect_uri": REDIRECT, "client_id": cliente.client_id,
            "code_verifier": verifier7, "resource": oauth.resource()}).json()
        pessoa = db.get(UsuarioRH, rh.id)
        pessoa.ativo = False
        db.commit()
        if oauth.identidade_do_access_token(db, d7["access_token"]) is not None:
            falhas.append("⚠️ conta desativada continua com o assistente ativo — "
                          "desligar alguém precisa cortar o acesso junto.")

    finally:
        # Limpa o que criou. As FKs são `ondelete=CASCADE`, então apagar o
        # usuário e o cliente leva junto códigos e concessões — por isso não se
        # apaga essas duas à mão (o ORM avisaria "esperava apagar 5, apagou 0",
        # que parece defeito e não é).
        db.rollback()
        if criados:
            for linha in db.scalars(select(ClienteOAuth).where(
                    ClienteOAuth.id.in_(criados))).all():
                db.delete(linha)
            for linha in db.scalars(select(UsuarioRH).where(
                    UsuarioRH.id.in_(criados))).all():
                db.delete(linha)
            db.commit()
        db.close()


rodar()

if falhas:
    print("FALHOU:")
    for f in falhas:
        print(f"  - {f}")
    sys.exit(1)
print("OK - fluxo completo: PKCE, replay, rotacao com deteccao de reuso, recusa "
      "por papel e corte ao desativar a conta.")
