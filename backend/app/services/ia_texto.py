"""Camada de geração de texto por IA — usada pelo Minutário de mensagens
(v1.98) e pelo Match de vagas (v1.99+). Provedores CONFIGURÁVEIS (mesmo padrão
do OCR em `ocr_ia.py`): as chaves ficam na config dinâmica, nunca em log,
nunca devolvidas ao painel.

CADEIA DE PROVEDORES (v2.00, decisão do Bruno 2026-07-28):
    OpenRouter (principal) → Groq (reserva)
Se o principal falhar ou estourar cota, o reserva assume automaticamente. Se
os dois falharem, levanta o erro CERTO para o chamador decidir — nunca finge
sucesso, nunca desiste em silêncio.

ERRO TRANSITÓRIO ≠ ERRO PERMANENTE (incidente de 2026-07-28): antes, um HTTP
429 (limite de cota — resolve em segundos) era convertido no MESMO erro de um
401 (chave inválida — permanente), e o Match de Vagas desligava a IA para
todos os talentos restantes. 131 talentos viraram 18 analisados, e 2 na
tentativa seguinte. Agora:
  - `CotaExcedidaError` → transitório, com `espera_s` vindo do header
    `Retry-After` quando o provedor manda. O chamador pode esperar e retomar.
  - `IndisponivelError` → permanente/desconhecido (chave errada, provedor
    fora do ar).

Regra geral de segurança do projeto para QUALQUER texto de origem externa
(currículo, anotação livre, etc.) passado a um modelo: é DADO, nunca
instrução. Ver `services/anti_prompt_injection.py`."""

import logging
import time

import httpx

from app.core.db import SessionLocal

log = logging.getLogger(__name__)
telemetria = logging.getLogger("telemetria")

_TIMEOUT = 40.0
_TENTATIVAS = 3          # por provedor, antes de passar para o próximo
_ESPERA_BASE_S = 2.0     # backoff exponencial: 2s, 4s, 8s
_ESPERA_MAX_S = 30.0     # teto por tentativa (o worker é que espera longo)

# Cadeia de provedores em ordem de preferência. `chave_cfg` é a chave na
# config dinâmica; `modelo` é o id do modelo em cada serviço.
PROVEDORES = (
    {
        "nome": "openrouter",
        "url": "https://openrouter.ai/api/v1/chat/completions",
        "chave_cfg": "openrouter_api_key",
        "modelo": "meta-llama/llama-3.3-70b-instruct:free",
    },
    {
        "nome": "groq",
        "url": "https://api.groq.com/openai/v1/chat/completions",
        "chave_cfg": "groq_api_key",
        "modelo": "llama-3.3-70b-versatile",
    },
)


class IndisponivelError(Exception):
    """Falha PERMANENTE ou desconhecida: chave ausente/inválida, provedor fora
    do ar, resposta inválida. Tentar de novo já não resolve sozinho."""


class CotaExcedidaError(Exception):
    """Falha TRANSITÓRIA: limite de requisições do provedor (HTTP 429).
    Resolve sozinha com o tempo — o chamador pode esperar `espera_s` e
    retomar de onde parou, em vez de desistir de tudo."""

    def __init__(self, mensagem: str = "cota_excedida", espera_s: float = 60.0):
        super().__init__(mensagem)
        self.espera_s = espera_s


def _ler_chave(chave_cfg: str, db=None) -> str | None:
    from app.services.config_dinamica import ler_config
    if db is not None:
        return ler_config(db, (chave_cfg,)).get(chave_cfg) or None
    with SessionLocal() as sessao:
        return ler_config(sessao, (chave_cfg,)).get(chave_cfg) or None


def chave_groq(db=None) -> str | None:
    return _ler_chave("groq_api_key", db)


def chave_openrouter(db=None) -> str | None:
    return _ler_chave("openrouter_api_key", db)


def provedores_configurados(db=None) -> list[str]:
    """Nomes dos provedores que têm chave — alimenta o painel e permite ao
    chamador saber se vale a pena tentar."""
    return [p["nome"] for p in PROVEDORES if _ler_chave(p["chave_cfg"], db)]


def _espera_do_header(resposta: httpx.Response, padrao: float) -> float:
    """`Retry-After` (segundos) quando o provedor manda — é a informação mais
    confiável sobre quando vale a pena tentar de novo. Antes era descartada."""
    bruto = resposta.headers.get("retry-after") or resposta.headers.get("Retry-After")
    try:
        return min(float(bruto), 300.0) if bruto else padrao
    except (TypeError, ValueError):
        return padrao


def _chamar_provedor(provedor: dict, mensagens: list[dict], *, chave: str,
                     resposta_json: bool, max_tokens: int) -> str:
    """Uma tentativa contra UM provedor. Levanta CotaExcedidaError (429) ou
    IndisponivelError (resto)."""
    corpo = {"model": provedor["modelo"], "messages": mensagens,
             "max_tokens": max_tokens, "temperature": 0.4}
    if resposta_json:
        corpo["response_format"] = {"type": "json_object"}
    cabecalhos = {"Authorization": f"Bearer {chave}"}
    if provedor["nome"] == "openrouter":
        # O OpenRouter pede identificação da aplicação (boas práticas deles).
        cabecalhos["HTTP-Referer"] = "https://greenhousedf.com.br"
        cabecalhos["X-Title"] = "Portal de RH Green House"

    try:
        r = httpx.post(provedor["url"], headers=cabecalhos, json=corpo, timeout=_TIMEOUT)
    except Exception as exc:   # rede, DNS, timeout
        telemetria.info("ia_texto provedor=%s ok=0 motivo=%s", provedor["nome"],
                        type(exc).__name__)
        raise IndisponivelError("provedor_indisponivel") from exc

    if r.status_code == 429:
        espera = _espera_do_header(r, 60.0)
        telemetria.info("ia_texto provedor=%s ok=0 motivo=cota espera=%.0fs",
                        provedor["nome"], espera)
        raise CotaExcedidaError("cota_excedida", espera_s=espera)
    if r.status_code in (401, 403):
        telemetria.info("ia_texto provedor=%s ok=0 motivo=chave_recusada", provedor["nome"])
        raise IndisponivelError("chave_recusada")
    if r.status_code >= 500:
        # Erro do lado deles — transitório, mas sem Retry-After confiável.
        telemetria.info("ia_texto provedor=%s ok=0 motivo=http_%s", provedor["nome"],
                        r.status_code)
        raise CotaExcedidaError("provedor_instavel", espera_s=10.0)
    if r.status_code >= 400:
        telemetria.info("ia_texto provedor=%s ok=0 motivo=http_%s", provedor["nome"],
                        r.status_code)
        raise IndisponivelError(f"http_{r.status_code}")

    try:
        dados = r.json()
        texto = dados["choices"][0]["message"]["content"]
    except Exception as exc:
        telemetria.info("ia_texto provedor=%s ok=0 motivo=resposta_invalida", provedor["nome"])
        raise IndisponivelError("resposta_invalida") from exc

    telemetria.info("ia_texto provedor=%s tokens=%s ok=1", provedor["nome"],
                    dados.get("usage", {}).get("total_tokens", "-"))
    return texto


def _chamar(mensagens: list[dict], *, chave: str | None, resposta_json: bool,
            max_tokens: int, esperar_cota: bool = False,
            so_provedor: str | None = None) -> str:
    """Percorre a cadeia de provedores. Em cada um, tenta até `_TENTATIVAS`
    vezes com backoff exponencial; se a cota estourar e `esperar_cota` for
    False, passa direto ao próximo provedor (não segura o request do RH).

    `esperar_cota=True` é para o WORKER: como ninguém está esperando na tela,
    vale a pena dormir o tempo que o provedor pediu e tentar de novo antes de
    trocar de provedor.

    `chave` + `so_provedor` restringem a UM provedor — usado só pelo botão de
    teste de conexão do painel (testar a chave da Groq não pode mandá-la ao
    OpenRouter)."""
    ultima_cota: CotaExcedidaError | None = None
    algum_configurado = False

    for provedor in PROVEDORES:
        if so_provedor and provedor["nome"] != so_provedor:
            continue
        chave_provedor = chave if chave else _ler_chave(provedor["chave_cfg"])
        if not chave_provedor:
            continue
        algum_configurado = True

        for tentativa in range(_TENTATIVAS):
            try:
                return _chamar_provedor(provedor, mensagens, chave=chave_provedor,
                                        resposta_json=resposta_json, max_tokens=max_tokens)
            except CotaExcedidaError as exc:
                ultima_cota = exc
                if not esperar_cota:
                    break          # troca de provedor: o RH não pode esperar
                if tentativa == _TENTATIVAS - 1:
                    break          # esgotou aqui; tenta o próximo provedor
                espera = min(exc.espera_s or (_ESPERA_BASE_S * (2 ** tentativa)), _ESPERA_MAX_S)
                log.info("Cota de %s excedida — aguardando %.0fs.", provedor["nome"], espera)
                time.sleep(espera)
            except IndisponivelError:
                break              # chave ruim / erro permanente: próximo provedor

    if not algum_configurado:
        raise IndisponivelError("chave_nao_configurada")
    if ultima_cota is not None:
        raise ultima_cota          # todos estouraram cota: é transitório
    raise IndisponivelError("provedor_indisponivel")


def gerar_texto(prompt_sistema: str, prompt_usuario: str, *,
                chave: str | None = None, max_tokens: int = 900,
                esperar_cota: bool = False, so_provedor: str | None = None) -> str:
    """Texto livre (usado pelo Minutário — nunca recebe dado pessoal do
    candidato, só campos da vaga; a substituição de {{nome}} etc. acontece
    DEPOIS, no servidor, fora da chamada à IA)."""
    return _chamar(
        [{"role": "system", "content": prompt_sistema},
         {"role": "user", "content": prompt_usuario}],
        chave=chave, resposta_json=False, max_tokens=max_tokens,
        esperar_cota=esperar_cota, so_provedor=so_provedor,
    )


def gerar_json(prompt_sistema: str, prompt_usuario: str, *,
               chave: str | None = None, max_tokens: int = 700,
               esperar_cota: bool = False) -> str:
    """Saída em JSON (usado pelo Match de vagas — nota+justificativa em campos
    fixos, nunca texto livre: é a defesa mais forte contra o modelo 'obedecer'
    uma instrução escondida no currículo, ver anti_prompt_injection.py)."""
    return _chamar(
        [{"role": "system", "content": prompt_sistema},
         {"role": "user", "content": prompt_usuario}],
        chave=chave, resposta_json=True, max_tokens=max_tokens,
        esperar_cota=esperar_cota,
    )


def _testar(chave: str, provedor: str, rotulo: str, onde: str) -> str:
    """Testa a chave CONTRA O PROVEDOR CERTO — testar a chave da Groq não pode
    mandá-la ao OpenRouter (e vice-versa)."""
    try:
        return gerar_texto("Responda em português, em uma frase curta.",
                           "Diga apenas: conexão funcionando.",
                           chave=chave, max_tokens=30, so_provedor=provedor)
    except CotaExcedidaError as exc:
        raise RuntimeError(f"A chave do {rotulo} funciona, mas o limite de uso está "
                           f"esgotado agora (tente em ~{int(exc.espera_s)}s).") from exc
    except IndisponivelError as exc:
        raise RuntimeError(f"A API do {rotulo} não respondeu ou recusou a chave. "
                           f"Confira a chave em {onde}.") from exc


def testar_groq(chave: str) -> str:
    return _testar(chave, "groq", "Groq", "console.groq.com → API Keys")


def testar_openrouter(chave: str) -> str:
    return _testar(chave, "openrouter", "OpenRouter", "openrouter.ai/keys")
