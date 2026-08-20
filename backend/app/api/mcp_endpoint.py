"""O endpoint `/mcp`: onde o assistente efetivamente trabalha.

⚠️ **O 401 é obrigatório, e um 200 com corpo de erro não serve.** É o
`WWW-Authenticate` numa resposta 401 que dispara a descoberta do OAuth no
cliente — sem ele, o "conectar" nunca aparece, mesmo com o servidor no ar e
respondendo. Um servidor que devolve 200 dizendo "não autenticado" fica
invisível para o fluxo inteiro.

O protocolo falado aqui é JSON-RPC 2.0 sobre HTTP (Streamable HTTP). Só os três
métodos que importam estão implementados — `initialize`, `tools/list` e
`tools/call`; o resto responde `method not found`, que é o previsto.
"""

from __future__ import annotations

import inspect
import logging

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.mcp.ferramentas import FERRAMENTAS, SemPermissao
from app.services import mcp_oauth as oauth
from app.services.auditoria import registrar
from app.services.contexto_log import definir_ator
from app.services.limite import exigir

router = APIRouter(tags=["mcp"])
log = logging.getLogger(__name__)

VERSAO_DO_PROTOCOLO = "2025-06-18"


def _desafio() -> dict:
    """O cabeçalho que ensina o cliente a se autenticar.

    O `resource_metadata` aponta para o documento que diz onde fica o servidor
    de autorização — é o fio que o cliente puxa para descobrir tudo o mais.
    """
    return {"WWW-Authenticate": (
        'Bearer realm="portal-rh", '
        f'resource_metadata="{oauth.issuer()}/.well-known/'
        'oauth-protected-resource/mcp"')}


def _nao_autenticado() -> JSONResponse:
    # Todos os motivos devolvem a MESMA resposta (molde do token_automacao):
    # distinguir "expirou" de "revogado" de "não existe" diria a quem testa
    # credenciais qual delas já existiu.
    return JSONResponse(
        {"error": "invalid_token",
         "error_description": "credencial ausente, expirada ou revogada"},
        status_code=401, headers=_desafio())


def _esquema(fn) -> dict:
    """Monta o schema da ferramenta a partir da própria assinatura.

    Derivar da assinatura em vez de escrever à mão evita a divergência clássica:
    parâmetro renomeado no código e esquecido no schema faz o modelo mandar um
    campo que a função não aceita, e o erro aparece como "a ferramenta falhou".

    `db` e `usuario` são pulados: são a injeção do servidor, não entrada do
    modelo.
    """
    propriedades, obrigatorios = {}, []
    for nome, p in inspect.signature(fn).parameters.items():
        if nome in ("db", "usuario"):
            continue
        anotacao = p.annotation
        tipo = "string"
        if anotacao is bool or anotacao == "bool":
            tipo = "boolean"
        elif "list" in str(anotacao):
            tipo = "array"
        entrada: dict = {"type": tipo}
        if tipo == "array":
            entrada["items"] = {"type": "string"}
        propriedades[nome] = entrada
        if p.default is inspect.Parameter.empty:
            obrigatorios.append(nome)
    return {"type": "object", "properties": propriedades, "required": obrigatorios}


def _catalogo() -> list[dict]:
    return [{
        "name": f.__name__,
        # A docstring É a descrição que o modelo lê para escolher a ferramenta.
        "description": inspect.getdoc(f) or "",
        "inputSchema": _esquema(f),
    } for f in FERRAMENTAS]


def _resposta(id_, resultado=None, erro=None) -> JSONResponse:
    corpo: dict = {"jsonrpc": "2.0", "id": id_}
    if erro is not None:
        corpo["error"] = erro
    else:
        corpo["result"] = resultado
    return JSONResponse(corpo)


def _texto(conteudo) -> dict:
    """Resultado de ferramenta no formato que o protocolo espera."""
    import json

    return {"content": [{"type": "text",
                         "text": json.dumps(conteudo, ensure_ascii=False,
                                            default=str, indent=2)}]}


@router.post("/mcp")
async def mcp(request: Request, db: Session = Depends(get_db)):
    autorizacao = request.headers.get("authorization") or ""
    if not autorizacao.lower().startswith("bearer "):
        return _nao_autenticado()

    usuario = oauth.identidade_do_access_token(db, autorizacao[7:].strip())
    if usuario is None:
        return _nao_autenticado()
    db.commit()  # persiste o carimbo de uso da concessão

    # `automacao:` no log é o que responde "foi gente ou foi o assistente?".
    # (No banco o ator vai como "rh" + o e-mail: a coluna `ator` tem 20 chars e
    # não caberia o prefixo — e o `registrar` engoliria o erro em silêncio.)
    definir_ator(f"automacao:{usuario.email}")
    exigir(f"mcp:usuario:{usuario.id}", maximo=120, janela_s=60)

    try:
        pedido = await request.json()
    except Exception:
        return _resposta(None, erro={"code": -32700, "message": "JSON inválido"})

    metodo = pedido.get("method")
    id_ = pedido.get("id")

    if metodo == "initialize":
        return _resposta(id_, {
            "protocolVersion": VERSAO_DO_PROTOCOLO,
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "portal-rh", "version": "1.0.0"},
        })

    if metodo in ("notifications/initialized", "ping"):
        return _resposta(id_, {})

    if metodo == "tools/list":
        return _resposta(id_, {"tools": _catalogo()})

    if metodo == "tools/call":
        return _chamar(db, usuario, id_, pedido.get("params") or {})

    return _resposta(id_, erro={"code": -32601,
                                "message": f"método não suportado: {metodo}"})


def _chamar(db: Session, usuario, id_, params: dict) -> JSONResponse:
    nome = params.get("name")
    argumentos = params.get("arguments") or {}
    fn = next((f for f in FERRAMENTAS if f.__name__ == nome), None)
    if fn is None:
        return _resposta(id_, erro={"code": -32602,
                                    "message": f"ferramenta desconhecida: {nome}"})

    registrar(db, "mcp_ferramenta", ator="rh", ator_detalhe=usuario.email,
              detalhe={"ferramenta": nome})
    try:
        resultado = fn(db, usuario, **argumentos)
        db.commit()
        return _resposta(id_, _texto(resultado))
    except SemPermissao as exc:
        db.rollback()
        # `isError` e não erro de protocolo: o modelo precisa LER a explicação e
        # repeti-la para a pessoa, em vez de a chamada falhar sem contexto.
        return _resposta(id_, {**_texto({"erro": str(exc)}), "isError": True})
    except TypeError as exc:
        db.rollback()
        return _resposta(id_, erro={"code": -32602,
                                    "message": f"argumentos inválidos: {exc}"})
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        # Nunca ecoar `str(exc)` do banco: a mensagem de truncamento do Postgres
        # inclui o VALOR que estourou, e ele pode ser um CPF (regra do handler
        # global do `main.py`).
        log.exception("falha na ferramenta %s", nome)
        return _resposta(id_, {**_texto({
            "erro": "A consulta falhou no portal. Tente algo mais específico ou "
                    "avise quem administra o sistema."}), "isError": True})


@router.get("/mcp")
def mcp_get(request: Request, db: Session = Depends(get_db)):
    """O cliente abre um GET para receber eventos; sem credencial, 401.

    Mesmo sem stream implementado, este 401 importa: é por ele que alguns
    clientes descobrem que precisam autenticar.
    """
    autorizacao = request.headers.get("authorization") or ""
    if not autorizacao.lower().startswith("bearer "):
        return _nao_autenticado()
    if oauth.identidade_do_access_token(db, autorizacao[7:].strip()) is None:
        return _nao_autenticado()
    return JSONResponse({"status": "ok"})
