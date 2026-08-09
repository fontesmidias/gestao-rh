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
os.environ.setdefault("RH_ADMIN_EMAIL", "rh@exemplo.com.br")
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
# Credencial do AMBIENTE, não literal (v2.71) — mesma correção do
# `test_documentos_catalogo`: a senha escrita à mão amarrava o teste a um banco
# criado com aquela senha, e no CI o login falhava com `KeyError: 'token'`.
_EMAIL = os.environ["RH_ADMIN_EMAIL"]
_SENHA = os.environ["RH_ADMIN_PASSWORD"]
_login = c.post("/api/rh/auth/login", json={"email": _EMAIL, "senha": _SENHA})
assert _login.status_code == 200 and "token" in _login.json(), (
    f"login do RH falhou ({_login.status_code}) — confira RH_ADMIN_EMAIL/"
    f"RH_ADMIN_PASSWORD do ambiente: {_login.text[:200]}")
rh = {"Authorization": f"Bearer {_login.json()['token']}"}

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
assert _um["atualizado_por"] == _EMAIL, _um["atualizado_por"]

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
assert r.json()[0]["autor"] == _EMAIL, r.json()[0]["autor"]
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
    assert r.json()["enviado_para"] == _EMAIL, r.json()
    assert _capturado["dest"] == _EMAIL, _capturado["dest"]
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

# --------------------------------------------- avisos internos (v2.20)
# Os avisos que vão para a EQUIPE (RH, operacional, líder de brigada) também
# passam a sair do catálogo: quem recebe nem sempre é quem conhece o sistema.
from app.services.notificacoes import EVENTOS, avisar_modelo  # noqa: E402

_INTERNOS = [m for m in CATALOGO if m.grupo == "Avisos internos"]
# Não se trava o NÚMERO de avisos: cada aviso novo (legítimo) quebraria o teste
# sem apontar defeito nenhum, e a tentação seria só incrementar a constante — um
# teste que não protege nada. O que importa é a GARANTIA, cobrada logo abaixo:
# todo aviso interno precisa de um evento correspondente na matriz, senão o RH
# não tem onde cadastrar quem recebe.
assert _INTERNOS, "o catálogo precisa ter avisos internos"

# todo aviso interno tem que casar com um EVENTO da matriz de notificações —
# senão o RH não teria onde cadastrar quem recebe
_eventos = {e["chave"] for e in EVENTOS}
# O vínculo é DERIVADO do próprio catálogo (campo `evento=`), não de uma lista
# escrita à mão aqui: a lista manual precisaria ser atualizada a cada aviso novo
# e, quando alguém esquecesse, o teste acusaria o teste — não o código.
for _m_int in _INTERNOS:
    assert _m_int.evento, (
        f"o aviso interno '{_m_int.chave}' não declara `evento=` — sem isso ele "
        f"não aparece na matriz e o RH não tem onde cadastrar quem recebe")
    assert _m_int.evento in _eventos, (
        f"'{_m_int.chave}' aponta para o evento '{_m_int.evento}', que não existe "
        f"em notificacoes.EVENTOS — o RH não teria onde cadastrar quem recebe")

# `avisar_modelo` renderiza pelo catálogo e respeita a matriz
_env = []
# `notificacoes.avisar_modelo` importa `enviar_email` de dentro da função, então
# o patch vai no MÓDULO DE ORIGEM — é o funil por onde ele passa.
import app.services.email as _mod_email  # noqa: E402

_orig_av = _mod_email.enviar_email


def _fake_av(dest, assunto, corpo, html=None, **kw):
    _env.append({"dest": dest, "assunto": assunto, "corpo": corpo})
    return True


_mod_email.enviar_email = _fake_av
try:
    from app.core.db import SessionLocal as _SL  # noqa: E402

    with _SL() as _db:
        n = avisar_modelo(_db, "envio_concluido", "aviso_envio_concluido",
                          {"nome": "Maria Souza", "link": "https://exemplo/rh"})
    assert n >= 1, "o aviso não saiu para ninguém (a matriz tem padrão global)"
    assert _env, "nenhum e-mail montado"
    assert "Maria Souza" in _env[0]["assunto"], _env[0]["assunto"]
    assert "{{" not in _env[0]["corpo"], _env[0]["corpo"]

    # template inexistente NÃO derruba o aviso — degrada para 0 e loga
    _env.clear()
    with _SL() as _db:
        assert avisar_modelo(_db, "envio_concluido", "nao_existe", {}) == 0
    assert not _env, "montou e-mail para template inexistente"
finally:
    _mod_email.enviar_email = _orig_av

# ------------------------------- destinatários na tela do e-mail (v2.21)
# Vários e-mails separados por vírgula, editados onde o RH edita o texto —
# gravando na MESMA matriz de Configurações → Avisos internos (uma fonte só).
_lista = c.get("/api/rh/config/emails", headers=rh).json()
_aviso = next(x for x in _lista if x["chave"] == "aviso_uniforme")
assert _aviso["evento"] == "uniforme_pendente", _aviso
# `destinatarios` é lista (pode vir preenchida de uma execução anterior — o
# teste não pode exigir banco virgem, senão falha no CI de alguém sem explicar)
assert isinstance(_aviso["destinatarios"], list), _aviso
# e-mail que NÃO é aviso interno não tem lista de destinatários
_externo = next(x for x in _lista if x["chave"] == "documento_rejeitado")
assert _externo["evento"] is None and _externo["destinatarios"] is None, _externo

r = c.put("/api/rh/config/emails/aviso_uniforme/destinatarios", headers=rh,
          json={"destinatarios": "gabriel@example.com, vitor@example.com", "ativo": True})
assert r.status_code == 200, r.text
assert r.json()["destinatarios"] == ["gabriel@example.com", "vitor@example.com"], r.json()

# a MESMA matriz enxerga (não é um segundo lugar de verdade)
from app.core.db import SessionLocal as _SL2  # noqa: E402

from app.services.notificacoes import destinatarios as _dests  # noqa: E402

with _SL2() as _db2:
    assert set(_dests(_db2, "uniforme_pendente")) == {
        "gabriel@example.com", "vitor@example.com"}

# e a listagem devolve o que foi salvo
_aviso = next(x for x in c.get("/api/rh/config/emails", headers=rh).json()
              if x["chave"] == "aviso_uniforme")
assert _aviso["destinatarios"] == ["gabriel@example.com", "vitor@example.com"], _aviso

# e-mail inválido é recusado com a lista do que está errado
r = c.put("/api/rh/config/emails/aviso_uniforme/destinatarios", headers=rh,
          json={"destinatarios": "gabriel@example.com, nao-e-email"})
assert r.status_code == 422 and r.json()["detail"]["invalidos"] == ["nao-e-email"], r.json()

# e-mail que vai para a pessoa do processo não aceita lista fixa
r = c.put("/api/rh/config/emails/documento_rejeitado/destinatarios", headers=rh,
          json={"destinatarios": "x@y.com"})
assert r.status_code == 422, r.text
assert r.json()["detail"]["erro"] == "email_sem_destinatario_configuravel", r.json()

# desligar o aviso: ninguém recebe
r = c.put("/api/rh/config/emails/aviso_uniforme/destinatarios", headers=rh,
          json={"destinatarios": "gabriel@example.com", "ativo": False})
assert r.status_code == 200, r.text
with _SL2() as _db2:
    assert _dests(_db2, "uniforme_pendente") == [], "aviso desligado não pode enviar"

assert c.put("/api/rh/config/emails/aviso_uniforme/destinatarios",
             json={"destinatarios": ""}).status_code == 401
assert c.put("/api/rh/config/emails/nao_existe/destinatarios", headers=rh,
             json={"destinatarios": ""}).status_code == 404

# limpa o que este teste configurou: deixar o aviso desligado atrapalharia
# quem rodasse depois (e o próprio sistema, se fosse o banco de verdade)
assert c.put("/api/rh/config/emails/aviso_uniforme/destinatarios", headers=rh,
             json={"destinatarios": "", "ativo": True}).status_code == 200

print("test_email_templates: OK")
