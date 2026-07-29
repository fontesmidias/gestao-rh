"""Textos de e-mail editáveis pelo RH (v2.06, feedback 2026-07-28).

O Bruno pediu "uma página com os e-mails todos que existem, puxando suas
respectivas variáveis, com preview e histórico" — e mandou migrar TODOS,
inclusive os que carregam código de acesso, contra a recomendação da sala.

O modo de falha que isso cria é o que este teste protege: o RH apaga o
`{{codigo}}` sem querer, o e-mail sai bonito e vazio, e ninguém mais entra no
sistema. A defesa é declarar variáveis OBRIGATÓRIAS por template e recusar o
salvamento (422) — não confiar.

As outras duas garantias testadas aqui:
- **fallback**: sem registro no banco (ou com texto vazio), vale o padrão do
  catálogo — e-mail nenhum deixa de sair por causa de uma edição ruim;
- **sem execução**: a substituição é `{{chave}}` por regex, então nem
  dot-access nem chamada de método passam. Não há template injection.

Precisa dos containers de teste para a parte de rotas.
Rode: PYTHONPATH=. .venv/Scripts/python.exe tests/test_email_templates.py
"""

import os

os.environ.setdefault(
    "DATABASE_URL", "postgresql+psycopg://admissao:admissao@localhost:55432/admissao")
os.environ.setdefault("MINIO_ENDPOINT", "localhost:59000")
os.environ.setdefault("MINIO_ACCESS_KEY", "minio")
os.environ.setdefault("MINIO_SECRET_KEY", "minio12345")
os.environ.setdefault("MINIO_SECURE", "false")
os.environ.setdefault("RH_ADMIN_EMAIL", "rh@greenhousedf.com.br")
os.environ.setdefault("RH_ADMIN_PASSWORD", "senha-teste-123")
os.environ.setdefault("SECRET_KEY", "segredo-de-teste")
os.environ.setdefault("BASE_URL", "http://localhost:8090")

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402
from app.services.email_templates import (CATALOGO, CATALOGO_POR_CHAVE,  # noqa: E402
                                          faltando_obrigatorias, renderizar)

c = TestClient(app)


class _DBVazio:
    """Banco sem nenhum template salvo — exercita o fallback."""

    def get(self, *_a, **_kw):
        return None


# ------------------------------------------------- catálogo bem formado
assert CATALOGO, "catálogo de e-mails vazio"
_chaves = [m.chave for m in CATALOGO]
assert len(_chaves) == len(set(_chaves)), "chave repetida no catálogo"

for m in CATALOGO:
    # toda obrigatória tem que estar declarada como variável...
    for v in m.obrigatorias:
        assert v in m.variaveis, f"{m.chave}: '{v}' é obrigatória mas não está em variaveis"
    # ...e o texto PADRÃO tem que respeitar as próprias obrigatórias, senão o
    # sistema já nasceria com um template inválido que o RH não pode salvar.
    assert not faltando_obrigatorias(m.chave, m.assunto, m.corpo), (
        f"{m.chave}: o texto de fábrica não usa as variáveis obrigatórias "
        f"{m.obrigatorias}")
    # a variável do botão precisa existir, senão o botão nunca apareceria
    if m.botao_url_var:
        assert m.botao_url_var in m.variaveis, (
            f"{m.chave}: botao_url_var '{m.botao_url_var}' não está em variaveis")
    # o preview precisa de exemplo para toda variável usada no texto
    for v in m.variaveis:
        if f"{{{{{v}}}}}" in f"{m.assunto}{m.corpo}":
            assert v in m.exemplo, (
                f"{m.chave}: variável '{v}' aparece no texto mas não tem exemplo "
                f"para o preview")

# ------------------------------- todo template renderiza com o seu exemplo
# Pega placeholder errado no catálogo (ex.: {{nome}} onde o contexto manda
# {{primeiro_nome}}), que sairia como "{{nome}}" cru no e-mail da pessoa.
for m in CATALOGO:
    _assunto, _texto, _html = renderizar(_DBVazio(), m.chave, dict(m.exemplo))
    assert "{{" not in _assunto and "{{" not in _texto, (
        f"{m.chave}: sobrou placeholder não substituído — "
        f"assunto={_assunto!r} corpo={_texto!r}")
    assert _texto.strip(), f"{m.chave}: corpo vazio"
    if m.botao_url_var and m.exemplo.get(m.botao_url_var):
        assert m.exemplo[m.botao_url_var] in _html, (
            f"{m.chave}: a URL do botão não chegou ao HTML")

# ------------------------------------------------------------ renderização
m = CATALOGO_POR_CHAVE["documento_rejeitado"]
assunto, texto, html = renderizar(_DBVazio(), "documento_rejeitado", {
    "nome": "Maria Souza", "primeiro_nome": "Maria",
    "motivo": "a imagem ficou ilegível", "link": "https://exemplo/c/tok"})
assert "Maria Souza" in texto and "ilegível" in texto, texto
assert "https://exemplo/c/tok" in html, "link sumiu do HTML"
assert "{{" not in texto, f"placeholder não substituído: {texto}"

# contexto com None não pode virar a string "None"
_a, _t, _h = renderizar(_DBVazio(), "documento_rejeitado", {
    "nome": "Maria", "primeiro_nome": "Maria", "motivo": "x", "link": None})
assert "None" not in _t and "None" not in _h

# ------------------------------------------- sem engine = sem execução
# A substituição é regex \w+: não existe dot-access nem chamada de método.
_a, _t, _h = renderizar(_DBVazio(), "creche_indeferido", {
    "nome": "{{__class__}}", "motivo": "{{7*7}}"})
assert "49" not in _t, "expressão foi avaliada — isso seria template injection"
# o valor injetado pelo contexto é texto, não é reinterpretado como template
assert "__class__" in _t

# ----------------------------------------------- guarda das obrigatórias
_com_lista = CATALOGO_POR_CHAVE["documentos_rejeitados_lote"]
assert "lista" in _com_lista.obrigatorias
assert faltando_obrigatorias("documentos_rejeitados_lote", "Assunto",
                             "Corpo sem a lista") == ["lista"]
# tolerante a espaços dentro das chaves, como o aplicar_variaveis é
assert faltando_obrigatorias("documentos_rejeitados_lote", "Assunto",
                             "Corpo com {{ lista }}") == []

# --------------------------------------------------------------- rotas
rh = {"Authorization": f"Bearer {c.post('/api/rh/auth/login', json={'email': 'rh@greenhousedf.com.br', 'senha': 'senha-teste-123'}).json()['token']}"}

r = c.get("/api/rh/config/emails", headers=rh)
assert r.status_code == 200, r.text
lista = r.json()
assert len(lista) == len(CATALOGO)
_um = next(x for x in lista if x["chave"] == "documento_rejeitado")
assert _um["variaveis"] and any(v["nome"] == "link" for v in _um["variaveis"])
assert _um["personalizado"] is False, "nada salvo ainda, não deveria estar personalizado"

# a tela exige login
assert c.get("/api/rh/config/emails").status_code == 401

# preview roda sobre o texto EM EDIÇÃO, sem salvar
r = c.post("/api/rh/config/emails/documento_rejeitado/preview", headers=rh,
           json={"assunto": "Oi {{primeiro_nome}}", "corpo": "Motivo: {{motivo}}",
                 "botao_texto": "Reenviar"})
assert r.status_code == 200, r.text
assert r.json()["assunto"] == "Oi Maria", r.json()
assert c.get("/api/rh/config/emails", headers=rh).json()[0]["personalizado"] is False, \
    "preview não pode ter salvado nada"

# salvar sem variável obrigatória é recusado
r = c.put("/api/rh/config/emails/documentos_rejeitados_lote", headers=rh,
          json={"assunto": "Documentos", "corpo": "Reenvie, por favor."})
assert r.status_code == 422, r.text
assert r.json()["detail"]["faltando"] == ["lista"], r.json()

# salvar de verdade
r = c.put("/api/rh/config/emails/documento_rejeitado", headers=rh,
          json={"assunto": "TESTE — reenvie {{primeiro_nome}}",
                "corpo": "Precisamos de novo: {{motivo}}", "botao_texto": "Reenviar"})
assert r.status_code == 200, r.text
_um = next(x for x in c.get("/api/rh/config/emails", headers=rh).json()
           if x["chave"] == "documento_rejeitado")
assert _um["personalizado"] is True and _um["assunto"].startswith("TESTE"), _um
assert _um["atualizado_por"] == "rh@greenhousedf.com.br"

# e o envio passa a usar o texto do RH
from app.core.db import SessionLocal  # noqa: E402

with SessionLocal() as db:
    assunto, texto, _ = renderizar(db, "documento_rejeitado", {
        "nome": "Maria", "primeiro_nome": "Maria", "motivo": "borrado", "link": None})
assert assunto == "TESTE — reenvie Maria", assunto
assert "Precisamos de novo: borrado" in texto, texto

# histórico guardou o texto ANTERIOR (o de fábrica)
r = c.get("/api/rh/config/emails/documento_rejeitado/versoes", headers=rh)
assert r.status_code == 200 and len(r.json()) >= 1, r.text
assert r.json()[0]["autor"] == "rh@greenhousedf.com.br"
assert "TESTE" not in r.json()[0]["assunto"], (
    "o histórico deve guardar o texto ANTERIOR, não o novo")

# restaurar de fábrica volta o padrão do catálogo
r = c.post("/api/rh/config/emails/documento_rejeitado/restaurar", headers=rh)
assert r.status_code == 200, r.text
with SessionLocal() as db:
    assunto, _t, _h = renderizar(db, "documento_rejeitado", {
        "nome": "Maria", "primeiro_nome": "Maria", "motivo": "x", "link": None})
assert assunto == CATALOGO_POR_CHAVE["documento_rejeitado"].assunto, assunto

# chave fora do catálogo é 404 (não cria template solto)
assert c.put("/api/rh/config/emails/nao_existe", headers=rh,
             json={"assunto": "a", "corpo": "b"}).status_code == 404

# ------------------------------------------------- enviar teste (v2.16)
# O preview mostra como fica na tela; só o envio real mostra como o Gmail e o
# Outlook renderizam. Vai para a caixa de QUEM ESTÁ EDITANDO e mais ninguém —
# o RH não escolhe destinatário, senão a tela de textos viraria disparador.
import app.services.email_templates as _mod_tpl  # noqa: E402
import app.api.configuracoes as _mod_cfg  # noqa: E402

_capturado = {}
_orig_env = _mod_cfg.enviar_email


def _fake(dest, assunto, corpo, html=None, levantar_erro=False, anexos=None, **kw):
    _capturado.update(dest=dest, assunto=assunto, corpo=corpo, html=html)
    return True


_mod_cfg.enviar_email = _fake
try:
    r = c.post("/api/rh/config/emails/documento_rejeitado/enviar-teste", headers=rh,
               json={"assunto": "Oi {{primeiro_nome}}", "corpo": "Motivo: {{motivo}}",
                     "botao_texto": "Reenviar"})
    assert r.status_code == 200, r.text
    # destinatário é SEMPRE o usuário logado
    assert r.json()["enviado_para"] == "rh@greenhousedf.com.br", r.json()
    assert _capturado["dest"] == "rh@greenhousedf.com.br", _capturado["dest"]
    # marca de teste no assunto: se vazar, fica evidente que é ensaio
    assert _capturado["assunto"].startswith("[TESTE] "), _capturado["assunto"]
    # usou o texto DIGITADO (não o salvo) e substituiu com o exemplo
    assert "Oi Maria" in _capturado["assunto"], _capturado["assunto"]
    assert "{{" not in _capturado["corpo"], _capturado["corpo"]
    # o payload NÃO tem campo de destinatário — é garantia estrutural
    assert "destinatario" not in _mod_cfg.EmailTemplateIn.model_fields
    assert "para" not in _mod_cfg.EmailTemplateIn.model_fields

    # chave fora do catálogo não envia nada
    _capturado.clear()
    assert c.post("/api/rh/config/emails/nao_existe/enviar-teste", headers=rh,
                  json={"assunto": "a", "corpo": "b"}).status_code == 404
    assert not _capturado, "enviou e-mail para chave desconhecida"

    # exige login
    assert c.post("/api/rh/config/emails/documento_rejeitado/enviar-teste",
                  json={"assunto": "a", "corpo": "b"}).status_code == 401
finally:
    _mod_cfg.enviar_email = _orig_env

# falha de SMTP vira 422 com o motivo, nunca 500 silencioso
def _falha(*a, **kw):
    raise RuntimeError("smtp fora do ar")


_mod_cfg.enviar_email = _falha
try:
    r = c.post("/api/rh/config/emails/documento_rejeitado/enviar-teste", headers=rh,
               json={"assunto": "a", "corpo": "b"})
    assert r.status_code == 422, f"esperava 422, veio {r.status_code}"
    assert "smtp fora do ar" in str(r.json()["detail"]), r.json()
finally:
    _mod_cfg.enviar_email = _orig_env

print("test_email_templates: OK")
