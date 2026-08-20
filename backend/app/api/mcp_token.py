"""O `/token`: troca o código por credencial, e rotaciona o refresh.

⚠️ **Aceita `application/x-www-form-urlencoded`, não JSON** (RFC 6749 § 4.1.3).
Por isso os parâmetros são `Form(...)` e não um `BaseModel` — um schema Pydantic
aqui responderia `422` a um pedido perfeitamente correto, e o sintoma seria
"conectar falhou", sem mais nada.

⚠️ **Os erros usam os códigos da RFC** (`invalid_grant`, `invalid_client`,
`invalid_request`, `invalid_target`), nunca códigos nossos: o cliente decide o
que fazer a partir deles — `invalid_grant` num refresh significa "reautorize";
um código desconhecido vira falha genérica e a pessoa não sabe o que resolver.
"""

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.core.config import ip_do_cliente
from app.core.db import get_db
from app.models.usuario_rh import UsuarioRH
from app.services import mcp_oauth as oauth
from app.services.auditoria import registrar
from app.services.limite import exigir

router = APIRouter(tags=["mcp-oauth"])


def _erro(codigo: str, descricao: str, status: int = 400) -> JSONResponse:
    # `no-store` porque a resposta desta rota carrega credencial: cache
    # intermediário guardando isso é vazamento silencioso.
    return JSONResponse({"error": codigo, "error_description": descricao},
                        status_code=status, headers={"Cache-Control": "no-store"})


def _sucesso(access: str, refresh: str, escopo: str) -> JSONResponse:
    return JSONResponse(
        {
            "access_token": access,
            "token_type": "Bearer",
            "expires_in": oauth.ACCESS_TTL_S,
            "refresh_token": refresh,
            "scope": escopo,
        },
        headers={"Cache-Control": "no-store", "Pragma": "no-cache"},
    )


def _pode_conectar(usuario: UsuarioRH | None) -> bool:
    return (usuario is not None and usuario.ativo
            and (usuario.papel or "") in oauth.PAPEIS_QUE_PODEM_CONECTAR)


@router.post("/token")
def token(request: Request, grant_type: str = Form(""),
          code: str | None = Form(None), redirect_uri: str | None = Form(None),
          client_id: str | None = Form(None), code_verifier: str | None = Form(None),
          refresh_token: str | None = Form(None), resource: str | None = Form(None),
          db: Session = Depends(get_db)):
    ip = ip_do_cliente(request) or "?"
    exigir(f"mcp-token:ip:{ip}", maximo=60, janela_s=300)

    if grant_type == "authorization_code":
        return _trocar_codigo(db, code, redirect_uri, client_id, code_verifier, resource)
    if grant_type == "refresh_token":
        return _renovar(db, refresh_token, client_id, resource)
    return _erro("unsupported_grant_type",
                 "use authorization_code ou refresh_token")


def _trocar_codigo(db: Session, code, redirect_uri, client_id, code_verifier, resource):
    """Primeira troca: o código vira access + refresh."""
    registro = oauth.resolver_codigo(db, code)
    if registro is None:
        return _erro("invalid_grant", "codigo desconhecido ou expirado")

    # ⚠️ MARCA COMO USADO ANTES DE QUALQUER OUTRA COISA.
    # Se o código já estava usado, isto é replay — alguém interceptou e está
    # tentando de novo. A resposta não é só recusar: é **revogar a concessão que
    # ele gerou**, porque a primeira troca pode ter sido a do atacante.
    if registro.usado_em is not None:
        if registro.concessao_id:
            from app.models.mcp_oauth import Concessao

            concessao = db.get(Concessao, registro.concessao_id)
            if concessao is not None:
                oauth.revogar(db, concessao, por="sistema", motivo="codigo_reusado")
                registrar(db, "mcp_codigo_reusado", ator="sistema",
                          detalhe={"concessao": str(concessao.id)})
        db.commit()
        return _erro("invalid_grant", "codigo ja utilizado")
    registro.usado_em = oauth._agora()
    db.flush()

    if not registro.valido and registro.usado_em is None:
        return _erro("invalid_grant", "codigo expirado")

    cliente = oauth.resolver_cliente(db, client_id or "")
    if cliente is None or cliente.id != registro.cliente_id:
        db.commit()
        return _erro("invalid_client", "cliente nao confere com o do codigo")

    # O redirect precisa ser o MESMO do /authorize: divergência é sinal de
    # código roubado sendo trocado por outro destino.
    if not redirect_uri or not oauth.redirect_uri_aceita(redirect_uri,
                                                         [registro.redirect_uri]):
        db.commit()
        return _erro("invalid_grant", "redirect_uri nao confere com o da autorizacao")

    if not oauth.confere_pkce(code_verifier or "", registro.code_challenge):
        # Sem o verifier, quem interceptou o código não consegue trocá-lo — é a
        # razão de o PKCE existir.
        db.commit()
        return _erro("invalid_grant", "code_verifier nao confere (PKCE)")

    if not oauth.mesmo_recurso(resource or registro.resource):
        db.commit()
        return _erro("invalid_target", "resource nao confere")

    usuario = db.get(UsuarioRH, registro.usuario_id)
    # Reconferido aqui: alguém pode ter sido desativado ou trocado de papel
    # entre o /authorize e o /token.
    if not _pode_conectar(usuario):
        db.commit()
        return _erro("invalid_grant", "a conta nao pode mais conectar o assistente")

    concessao, refresh = oauth.abrir_concessao(db, registro, usuario)
    registro.concessao_id = concessao.id
    access = oauth.emitir_access(concessao)
    registrar(db, "mcp_token_emitido", ator="rh", ator_detalhe=usuario.email,
              detalhe={"cliente": cliente.client_name, "concessao": str(concessao.id)})
    db.commit()
    return _sucesso(access, refresh, concessao.escopo)


def _renovar(db: Session, refresh_token, client_id, resource):
    """Renovação com ROTAÇÃO e detecção de reuso."""
    concessao, reuso = oauth.resolver_refresh(db, refresh_token)

    if reuso and concessao is not None:
        # ⚠️ Um refresh de geração anterior reaparecendo significa que alguém
        # tem uma cópia. Recusar só este pedido deixaria a credencial legítima
        # viva nas mãos de quem a roubou — então a concessão INTEIRA cai, e a
        # pessoa reautoriza.
        oauth.revogar(db, concessao, por="sistema", motivo="reuso_detectado")
        registrar(db, "mcp_refresh_reusado", ator="sistema",
                  detalhe={"concessao": str(concessao.id),
                           "usuario": str(concessao.usuario_id)})
        db.commit()
        return _erro("invalid_grant", "refresh token invalidado por reuso")

    if concessao is None or not concessao.valido:
        return _erro("invalid_grant", "refresh token invalido ou revogado")

    cliente = oauth.resolver_cliente(db, client_id or "")
    if cliente is None or cliente.id != concessao.cliente_id:
        return _erro("invalid_client", "cliente nao confere com a concessao")

    if resource and not oauth.mesmo_recurso(resource):
        return _erro("invalid_target", "resource nao confere")

    usuario = db.get(UsuarioRH, concessao.usuario_id)
    if not _pode_conectar(usuario):
        # Desligar alguém no portal corta o assistente dela junto — é o que faz
        # "revogar acesso = desligar o usuário" ser verdade.
        oauth.revogar(db, concessao, por="sistema", motivo="conta_sem_acesso")
        db.commit()
        return _erro("invalid_grant", "a conta nao pode mais conectar o assistente")

    novo_refresh = oauth.rotacionar(db, concessao)
    access = oauth.emitir_access(concessao)
    db.commit()
    # O refresh novo sai na MESMA resposta que invalida o antigo. Devolver só o
    # access deixaria o cliente com um refresh morto, e a reconexão pararia dez
    # minutos depois — parecendo intermitência de rede.
    return _sucesso(access, novo_refresh, concessao.escopo)
