"""Teste da cadeia de provedores de IA (services/ia_texto.py) — sem rede.

Cobre o incidente de 2026-07-28: um HTTP 429 (cota, transitório) era tratado
igual a um 401 (chave inválida, permanente), e o Match de Vagas desligava a
IA para todos os talentos restantes — 131 viraram 18 analisados, e 2 na
tentativa seguinte.

Rode: PYTHONPATH=. .venv/Scripts/python.exe tests/test_ia_texto_cadeia.py
"""

import os

os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://x:x@localhost/x")
os.environ.setdefault("SECRET_KEY", "x")
os.environ.setdefault("BASE_URL", "http://x")

from unittest.mock import patch

import httpx

from app.services import ia_texto
from app.services.ia_texto import CotaExcedidaError, IndisponivelError


def _resposta(status, corpo=None, headers=None):
    return httpx.Response(status_code=status, json=corpo or {}, headers=headers or {},
                          request=httpx.Request("POST", "http://x"))


_OK = {"choices": [{"message": {"content": "resposta boa"}}], "usage": {"total_tokens": 10}}


# ---------- 429 é TRANSITÓRIO e traz o tempo de espera do header ----------

def test_429_vira_cota_excedida_com_retry_after():
    chamadas = []

    def fake_post(url, **kw):
        chamadas.append(url)
        return _resposta(429, headers={"Retry-After": "45"})

    with patch.object(ia_texto, "_ler_chave", lambda cfg, db=None: "chave-x"), \
         patch.object(ia_texto.httpx, "post", fake_post):
        try:
            ia_texto.gerar_texto("s", "u")
            raise AssertionError("deveria ter levantado CotaExcedidaError")
        except CotaExcedidaError as exc:
            assert exc.espera_s == 45.0, exc.espera_s
    # tentou os DOIS provedores antes de desistir (não parou no primeiro)
    assert any("openrouter" in u for u in chamadas), chamadas
    assert any("groq" in u for u in chamadas), chamadas


# ---------- 401 é PERMANENTE — não é confundido com cota ----------

def test_401_vira_indisponivel_nao_cota():
    with patch.object(ia_texto, "_ler_chave", lambda cfg, db=None: "chave-x"), \
         patch.object(ia_texto.httpx, "post", lambda url, **kw: _resposta(401)):
        try:
            ia_texto.gerar_texto("s", "u")
            raise AssertionError("deveria ter levantado IndisponivelError")
        except CotaExcedidaError:
            raise AssertionError("401 NÃO pode virar CotaExcedidaError")
        except IndisponivelError:
            pass


# ---------- Fallback: OpenRouter falha, Groq assume ----------

def test_fallback_para_groq_quando_openrouter_falha():
    def fake_post(url, **kw):
        if "openrouter" in url:
            return _resposta(429, headers={"Retry-After": "60"})
        return _resposta(200, _OK)

    with patch.object(ia_texto, "_ler_chave", lambda cfg, db=None: "chave-x"), \
         patch.object(ia_texto.httpx, "post", fake_post):
        assert ia_texto.gerar_texto("s", "u") == "resposta boa"


# ---------- Sem nenhuma chave configurada ----------

def test_sem_chave_alguma():
    with patch.object(ia_texto, "_ler_chave", lambda cfg, db=None: None):
        try:
            ia_texto.gerar_texto("s", "u")
            raise AssertionError("deveria ter levantado IndisponivelError")
        except IndisponivelError as exc:
            assert "chave_nao_configurada" in str(exc)


# ---------- Só uma chave configurada: usa a que existe ----------

def test_so_groq_configurado():
    def fake_chave(cfg, db=None):
        return "chave-groq" if cfg == "groq_api_key" else None

    urls = []

    def fake_post(url, **kw):
        urls.append(url)
        return _resposta(200, _OK)

    with patch.object(ia_texto, "_ler_chave", fake_chave), \
         patch.object(ia_texto.httpx, "post", fake_post):
        assert ia_texto.gerar_texto("s", "u") == "resposta boa"
    assert all("groq" in u for u in urls), urls


# ---------- esperar_cota=True (worker): espera e retoma no MESMO provedor ----------

def test_worker_espera_e_retoma():
    tentativas = {"n": 0}

    def fake_post(url, **kw):
        tentativas["n"] += 1
        if tentativas["n"] == 1:
            return _resposta(429, headers={"Retry-After": "1"})
        return _resposta(200, _OK)

    dormiu = []
    with patch.object(ia_texto, "_ler_chave", lambda cfg, db=None: "chave-x"), \
         patch.object(ia_texto.httpx, "post", fake_post), \
         patch.object(ia_texto.time, "sleep", lambda s: dormiu.append(s)):
        assert ia_texto.gerar_texto("s", "u", esperar_cota=True) == "resposta boa"
    assert dormiu == [1.0], dormiu   # respeitou o Retry-After, não o backoff padrão


# ---------- Teste de chave manda para o provedor CERTO ----------

# `_chave_api_so` responde à chave dos provedores mas devolve None para
# `*_modelos` — assim `_modelos_do_provedor` cai nos PADRÕES sem tocar o banco.
def _chave_api_so(cfg, db=None):
    return "chave-x" if cfg.endswith("_api_key") else None


def test_testar_chave_vai_ao_provedor_certo():
    urls = []

    def fake_post(url, **kw):
        urls.append(url)
        return _resposta(200, _OK)

    with patch.object(ia_texto, "_ler_chave", _chave_api_so), \
         patch.object(ia_texto.httpx, "post", fake_post):
        ia_texto.testar_groq("chave-groq-do-rh")
    assert len(urls) == 1 and "groq" in urls[0], urls

    urls.clear()
    with patch.object(ia_texto, "_ler_chave", _chave_api_so), \
         patch.object(ia_texto.httpx, "post", fake_post):
        ia_texto.testar_openrouter("chave-openrouter-do-rh")
    assert len(urls) == 1 and "openrouter" in urls[0], urls


# ---------- Fallback ENTRE MODELOS do mesmo provedor (o `:free` que some) ----------

def test_fallback_entre_modelos_do_mesmo_provedor():
    vistos = []

    def fake_post(url, **kw):
        modelo = kw["json"]["model"]
        vistos.append(modelo)
        # 1º modelo padrão do OpenRouter não existe mais → 404; o 2º responde.
        if modelo == "google/gemma-4-31b-it:free":
            return _resposta(404, {"error": "no endpoints found"})
        return _resposta(200, _OK)

    with patch.object(ia_texto, "_ler_chave", _chave_api_so), \
         patch.object(ia_texto.httpx, "post", fake_post):
        assert ia_texto.gerar_texto("s", "u", so_provedor="openrouter") == "resposta boa"
    assert vistos == ["google/gemma-4-31b-it:free", "openai/gpt-oss-20b:free"], vistos


# ---------- 401 NÃO tenta os outros modelos do provedor (chave é do provedor) ----------

def test_401_pula_provedor_sem_varrer_modelos():
    or_modelos = []

    def fake_post(url, **kw):
        if "openrouter" in url:
            or_modelos.append(kw["json"]["model"])
            return _resposta(401)
        return _resposta(200, _OK)

    with patch.object(ia_texto, "_ler_chave", _chave_api_so), \
         patch.object(ia_texto.httpx, "post", fake_post):
        assert ia_texto.gerar_texto("s", "u") == "resposta boa"  # a Groq assumiu
    # tentou UM só modelo do OpenRouter antes de pular para a Groq (não os dois)
    assert len(or_modelos) == 1, or_modelos


# ---------- Override de modelos pelo painel tem precedência sobre o padrão ----------

def test_override_de_modelos_pelo_painel():
    vistos = []

    def fake_chave(cfg, db=None):
        if cfg == "openrouter_api_key":
            return "chave-x"
        if cfg == "openrouter_modelos":
            return "meu/modelo-a, meu/modelo-b"
        return None

    def fake_post(url, **kw):
        vistos.append(kw["json"]["model"])
        return _resposta(200, _OK)

    with patch.object(ia_texto, "_ler_chave", fake_chave), \
         patch.object(ia_texto.httpx, "post", fake_post):
        ia_texto.gerar_texto("s", "u", so_provedor="openrouter")
    assert vistos[0] == "meu/modelo-a", vistos


# ---------- Mensagem de erro distingue MODELO indisponível de CHAVE recusada ----------

def test_erro_404_nao_acusa_a_chave():
    with patch.object(ia_texto, "_ler_chave", _chave_api_so), \
         patch.object(ia_texto.httpx, "post", lambda url, **kw: _resposta(404)):
        try:
            ia_texto.testar_openrouter("chave-x")
            raise AssertionError("deveria ter levantado RuntimeError")
        except RuntimeError as exc:
            msg = str(exc)
            assert "404" in msg, msg
            assert "recusou a chave" not in msg, msg


def test_erro_401_acusa_a_chave():
    with patch.object(ia_texto, "_ler_chave", _chave_api_so), \
         patch.object(ia_texto.httpx, "post", lambda url, **kw: _resposta(401)):
        try:
            ia_texto.testar_openrouter("chave-x")
            raise AssertionError("deveria ter levantado RuntimeError")
        except RuntimeError as exc:
            assert "recusou a chave" in str(exc), str(exc)


# ---------- content nulo/vazio (HTTP 200) NUNCA devolve None (era o 500) ----------

def test_content_vazio_nao_devolve_none():
    # 200 com content=None (reasoning gastou o orçamento de tokens) cai como
    # resposta inválida e tenta o próximo modelo/provedor — nunca retorna None.
    def fake_post(url, **kw):
        return _resposta(200, {"choices": [{"message": {"content": None}}], "usage": {}})

    with patch.object(ia_texto, "_ler_chave", _chave_api_so), \
         patch.object(ia_texto.httpx, "post", fake_post):
        try:
            ia_texto.gerar_texto("s", "u")
            raise AssertionError("deveria ter levantado, não devolver None")
        except IndisponivelError as exc:
            assert exc.codigo == "resposta_vazia", exc.codigo


def test_content_vazio_no_teste_de_chave_vira_runtime_nao_500():
    # A rota faz texto[:120] — se gerar_texto devolvesse None, dava 500. Agora o
    # _testar levanta RuntimeError (→ 422 com mensagem clara), sem estourar.
    def fake_post(url, **kw):
        return _resposta(200, {"choices": [{"message": {"content": "   "}}], "usage": {}})

    with patch.object(ia_texto, "_ler_chave", _chave_api_so), \
         patch.object(ia_texto.httpx, "post", fake_post):
        try:
            ia_texto.testar_openrouter("chave-x")
            raise AssertionError("deveria ter levantado RuntimeError")
        except RuntimeError as exc:
            assert "vazio" in str(exc), str(exc)


def test_content_valido_ainda_retorna():
    # Não pode ter virado paranoico: content de verdade continua passando.
    def fake_post(url, **kw):
        return _resposta(200, _OK)

    with patch.object(ia_texto, "_ler_chave", _chave_api_so), \
         patch.object(ia_texto.httpx, "post", fake_post):
        assert ia_texto.gerar_texto("s", "u") == "resposta boa"


test_429_vira_cota_excedida_com_retry_after()
test_401_vira_indisponivel_nao_cota()
test_fallback_para_groq_quando_openrouter_falha()
test_sem_chave_alguma()
test_so_groq_configurado()
test_worker_espera_e_retoma()
test_testar_chave_vai_ao_provedor_certo()
test_fallback_entre_modelos_do_mesmo_provedor()
test_401_pula_provedor_sem_varrer_modelos()
test_override_de_modelos_pelo_painel()
test_erro_404_nao_acusa_a_chave()
test_erro_401_acusa_a_chave()
test_content_vazio_nao_devolve_none()
test_content_vazio_no_teste_de_chave_vira_runtime_nao_500()
test_content_valido_ainda_retorna()

print("test_ia_texto_cadeia: OK")
