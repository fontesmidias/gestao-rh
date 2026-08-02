from fastapi import APIRouter, Request
from sqlalchemy import text

from app.core.config import base_url_publica
from app.core.db import engine
from app.versao import VERSAO, VERSAO_NOME, versao_completa

router = APIRouter(tags=["health"])

# Marcador de versão: vem de `app/versao.py`, que o `test_versao.py` mantém
# igual ao topo do CHANGELOG. Já foi uma string chumbada aqui e congelou DUAS
# vezes (v1.50 e v2.27) — a segunda mesmo depois de a função logo abaixo
# registrar o problema por escrito. Documentar não basta; o teste é que segura.
VERSAO_DEPLOY = versao_completa()


def _revisao_esperada() -> str | None:
    """Última revisão do Alembic presente NO CÓDIGO desta imagem.

    Lida do diretório de migrations em vez de chumbada à mão: uma constante
    esquecida (como o `VERSAO_DEPLOY`, que ficou parado na v1.50 por vinte
    versões) mente com a maior confiança do mundo.
    """
    try:
        from alembic.config import Config
        from alembic.script import ScriptDirectory
        from pathlib import Path
        raiz = Path(__file__).resolve().parents[2]
        script = ScriptDirectory.from_config(Config(str(raiz / "alembic.ini")))
        return script.get_current_head()
    except Exception:
        return None


def _revisao_aplicada() -> str | None:
    """Revisão que está GRAVADA no banco agora."""
    try:
        with engine.connect() as con:
            return con.execute(
                text("select version_num from alembic_version")).scalar()
    except Exception:
        return None


@router.get("/health")
def health() -> dict:
    """Saúde do serviço — e, principalmente, se o BANCO acompanhou o código.

    O `migracoes` existe por causa do incidente de 2026-07-29: o pedido foi
    "que o sistema não pare de uma atualização para a outra". Se o
    `docker-entrypoint.sh` falhar ao rodar `alembic upgrade head`, a API sobe
    assim mesmo com o schema velho — e o defeito só aparece na cara do
    candidato, numa tela que não explica nada.
    """
    esperada, aplicada = _revisao_esperada(), _revisao_aplicada()
    return {
        "status": "ok",
        "versao": VERSAO_DEPLOY,
        # Separados também em partes: a tela de Configurações mostra o número e
        # o nome em lugares diferentes, e não deve ter que fatiar string.
        "versao_numero": VERSAO,
        "versao_nome": VERSAO_NOME,
        "migracoes": {
            # `em_dia` é o que se olha primeiro. False = o banco ficou para
            # trás; rode `alembic upgrade head` no container da API.
            "em_dia": (esperada is not None and esperada == aplicada),
            "no_codigo": esperada,
            "no_banco": aplicada,
        },
    }


@router.get("/diag/callback")
def diag_callback(request: Request) -> dict:
    """Diagnóstico público (sem dados sensíveis): mostra a URL pública que o
    sistema monta e os headers de protocolo que o proxy/Cloudflare enviam.
    Serve para confirmar, no ar, se o callback OAuth sai http ou https."""
    base = base_url_publica(request)
    return {
        "versao": VERSAO_DEPLOY,
        "url_publica_montada": base,
        "callback_m365": f"{base}/api/rh/config/m365/callback",
        "headers_de_protocolo": {
            "host": request.headers.get("host"),
            "x-forwarded-host": request.headers.get("x-forwarded-host"),
            "x-forwarded-proto": request.headers.get("x-forwarded-proto"),
            "cf-visitor": request.headers.get("cf-visitor"),
            "x-forwarded-ssl": request.headers.get("x-forwarded-ssl"),
            "url_scheme_visto": request.url.scheme,
        },
    }
