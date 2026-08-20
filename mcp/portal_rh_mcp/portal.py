"""Cliente HTTP do Portal de RH — a única porta por onde o MCP fala com a API.

Fica separado das ferramentas de propósito: as ferramentas descrevem O QUE se
pergunta ao portal; aqui mora COMO se pergunta, e o tratamento de erro. Quando o
token expira ou a rede cai, a resposta precisa dizer o que RESOLVE — é a regra
que o projeto inteiro segue (v2.93), e num assistente ela vale ainda mais: o
modelo vai LER a mensagem de erro e repeti-la para a pessoa.
"""

from __future__ import annotations

import os

import httpx

TEMPO_LIMITE = 30.0


class ErroDoPortal(Exception):
    """Falha que a pessoa precisa ver, com o que resolve junto."""


class Portal:
    """Conversa com a API do portal usando a credencial de máquina (`mcp_…`).

    O token vem do ambiente, não de argumento: no Claude Desktop ele é escrito
    UMA vez no `claude_desktop_config.json` e não passa por prompt nenhum — o
    modelo nunca o vê, e portanto não tem como vazá-lo numa resposta.
    """

    def __init__(self, base_url: str | None = None, token: str | None = None):
        self.base_url = (base_url or os.getenv("PORTAL_RH_URL") or "").rstrip("/")
        self.token = token or os.getenv("PORTAL_RH_TOKEN") or ""
        if not self.base_url:
            raise ErroDoPortal(
                "Falta dizer qual é o endereço do portal. Defina PORTAL_RH_URL "
                "no claude_desktop_config.json (ex.: https://rh.suaempresa.com.br)."
            )
        if not self.token:
            raise ErroDoPortal(
                "Falta a credencial. Defina PORTAL_RH_TOKEN no "
                "claude_desktop_config.json — crie a sua em Configurações → "
                "E-mail e integrações → Credenciais de automação."
            )

    def _url(self, caminho: str) -> str:
        return f"{self.base_url}/api{caminho}"

    def _cabecalhos(self) -> dict:
        return {"Authorization": f"Bearer {self.token}"}

    def _erro(self, r: httpx.Response) -> ErroDoPortal:
        """Traduz a resposta em algo acionável.

        ⚠️ As três causas mais comuns pedem AÇÕES DIFERENTES, e confundi-las faz
        quem opera mexer no lugar errado (v2.93): token revogado se resolve
        emitindo outro; falta de permissão se resolve com quem administra; e
        "não encontrado" quase sempre é o nome escrito diferente.
        """
        if r.status_code == 401:
            return ErroDoPortal(
                "A credencial não é aceita (pode ter sido revogada ou expirado). "
                "Crie outra em Configurações → E-mail e integrações → Credenciais "
                "de automação e atualize o claude_desktop_config.json."
            )
        if r.status_code == 403:
            return ErroDoPortal(
                "Esta ação não é permitida para o assistente. O papel dele é "
                "menor que o seu de propósito: efetivar, desligar, decidir "
                "reembolso, exportar a base e assinar continuam só pela tela."
            )
        if r.status_code == 404:
            return ErroDoPortal("Não encontrei esse registro no portal.")
        if r.status_code == 429:
            return ErroDoPortal(
                "Muitas chamadas seguidas. Espere alguns instantes e tente de novo."
            )
        detalhe = ""
        try:
            corpo = r.json()
            detalhe = corpo.get("detail") if isinstance(corpo, dict) else corpo
        except Exception:
            detalhe = (r.text or "")[:200]
        return ErroDoPortal(f"O portal recusou (HTTP {r.status_code}): {detalhe}")

    def _chamar(self, metodo: str, caminho: str, **kw):
        try:
            with httpx.Client(timeout=TEMPO_LIMITE) as cli:
                r = cli.request(metodo, self._url(caminho),
                                headers=self._cabecalhos(), **kw)
        except httpx.TimeoutException:
            raise ErroDoPortal(
                f"O portal não respondeu em {TEMPO_LIMITE:.0f}s. Ele pode estar "
                "fora do ar ou a consulta é pesada demais — tente algo mais "
                "específico."
            ) from None
        except httpx.HTTPError as exc:
            # "Sem internet" quase nunca é sem internet (v2.31): pode ser o
            # endereço errado no config, ou o portal fora do ar. A mensagem diz
            # os dois, em vez de mandar conferir a conexão.
            raise ErroDoPortal(
                f"Não consegui falar com o portal em {self.base_url}. Confira se "
                f"o endereço está certo no claude_desktop_config.json e se o "
                f"portal está no ar. ({exc.__class__.__name__})"
            ) from None
        if r.status_code >= 400:
            raise self._erro(r)
        if not r.content:
            return None
        try:
            return r.json()
        except Exception:
            return r.text

    def get(self, caminho: str, **params):
        limpos = {k: v for k, v in params.items() if v not in (None, "")}
        return self._chamar("GET", caminho, params=limpos)

    def post(self, caminho: str, corpo: dict | None = None):
        return self._chamar("POST", caminho, json=corpo or {})

    def put(self, caminho: str, corpo: dict | None = None):
        return self._chamar("PUT", caminho, json=corpo or {})
