"""Camada de geração de texto por IA — usada pelo Minutário de mensagens (C1)
e pelo Match de vagas (C2). Provedor CONFIGURÁVEL (mesmo padrão do OCR em
`ocr_ia.py`): a chave fica na config dinâmica, nunca em log, nunca devolvida
ao painel. Groq por padrão (decisão do Bruno, 2026-07-27 — roundtable
recomendou provedor com retenção zero para o C2, mas ele optou por Groq nos
dois módulos de forma consciente). Trocar de provedor no futuro é mudar este
arquivo, não o C1/C2 — os dois só chamam `gerar_texto`/`gerar_json`.

Regra geral de segurança do projeto para QUALQUER texto de origem externa
(currículo, anotação livre, etc.) passado a um modelo: é DADO, nunca
instrução. Ver `services/anti_prompt_injection.py` (usado pelo C2)."""

import logging

import httpx

from app.core.db import SessionLocal

log = logging.getLogger(__name__)
telemetria = logging.getLogger("telemetria")

_URL_GROQ = "https://api.groq.com/openai/v1/chat/completions"
_MODELO_PADRAO = "llama-3.3-70b-versatile"
_TIMEOUT = 40.0


def chave_groq(db=None) -> str | None:
    from app.services.config_dinamica import ler_config
    if db is not None:
        return ler_config(db, ("groq_api_key",)).get("groq_api_key") or None
    with SessionLocal() as sessao:
        return ler_config(sessao, ("groq_api_key",)).get("groq_api_key") or None


class IndisponivelError(Exception):
    """Chave ausente, provedor fora do ar, ou resposta inválida — o chamador
    decide o que fazer (nunca finge sucesso)."""


def _chamar(mensagens: list[dict], *, chave: str | None, resposta_json: bool,
            max_tokens: int) -> str:
    chave = chave or chave_groq()
    if not chave:
        raise IndisponivelError("chave_nao_configurada")
    corpo = {"model": _MODELO_PADRAO, "messages": mensagens, "max_tokens": max_tokens,
             "temperature": 0.4}
    if resposta_json:
        corpo["response_format"] = {"type": "json_object"}
    try:
        r = httpx.post(_URL_GROQ, headers={"Authorization": f"Bearer {chave}"},
                       json=corpo, timeout=_TIMEOUT)
        r.raise_for_status()
        dados = r.json()
        texto = dados["choices"][0]["message"]["content"]
        telemetria.info("ia_texto provedor=groq tokens=%s ok=1",
                        dados.get("usage", {}).get("total_tokens", "-"))
        return texto
    except Exception as exc:
        telemetria.info("ia_texto provedor=groq ok=0 motivo=%s", type(exc).__name__)
        log.warning("Groq indisponível (%s).", type(exc).__name__)
        raise IndisponivelError("provedor_indisponivel") from exc


def gerar_texto(prompt_sistema: str, prompt_usuario: str, *,
                chave: str | None = None, max_tokens: int = 900) -> str:
    """Texto livre (usado pelo Minutário — nunca recebe dado pessoal do
    candidato, só campos da vaga; a substituição de {{nome}} etc. acontece
    DEPOIS, no servidor, fora da chamada à IA)."""
    return _chamar(
        [{"role": "system", "content": prompt_sistema},
         {"role": "user", "content": prompt_usuario}],
        chave=chave, resposta_json=False, max_tokens=max_tokens,
    )


def gerar_json(prompt_sistema: str, prompt_usuario: str, *,
               chave: str | None = None, max_tokens: int = 700) -> str:
    """Saída em JSON (usado pelo Match de vagas — nota+justificativa em campos
    fixos, nunca texto livre: é a defesa mais forte contra o modelo 'obedecer'
    uma instrução escondida no currículo, ver anti_prompt_injection.py)."""
    return _chamar(
        [{"role": "system", "content": prompt_sistema},
         {"role": "user", "content": prompt_usuario}],
        chave=chave, resposta_json=True, max_tokens=max_tokens,
    )


def testar_groq(chave: str) -> str:
    """Valida a chave com uma pergunta trivial. Devolve o texto ou levanta
    RuntimeError com mensagem legível para o painel."""
    try:
        return gerar_texto(
            "Responda em português, em uma frase curta.",
            "Diga apenas: conexão funcionando.",
            chave=chave, max_tokens=30,
        )
    except IndisponivelError as exc:
        raise RuntimeError("A API da Groq não respondeu ou recusou a chave. "
                           "Confira a chave em console.groq.com → API Keys.") from exc
