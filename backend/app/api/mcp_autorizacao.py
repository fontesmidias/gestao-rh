"""O `/authorize`: a única rota do MCP que uma PESSOA vê.

Ela chega aqui por um redirect do Claude, faz login e decide. Por isso responde
HTML e não JSON — o interlocutor é um navegador.

⚠️ **A ordem das validações decide se um erro volta pelo `redirect_uri` ou vira
tela.** Enquanto o `client_id` e o `redirect_uri` não estiverem conferidos,
redirecionar seria mandar a pessoa a um destino não verificado — o open redirect
que a spec manda evitar. Depois de conferidos, a RFC manda devolver o erro por
lá, para o cliente poder tratá-lo.

Separado de `mcp_oauth.py` de propósito: aquele é descoberta e registro (JSON,
falando com o servidor do Claude); este é a conversa com a pessoa.
"""

from urllib.parse import urlencode, urlsplit

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import ip_do_cliente
from app.core.db import get_db
from app.core.security import verificar_senha
from app.models.usuario_rh import UsuarioRH
from app.services import mcp_oauth as oauth
from app.services import mcp_telas as telas
from app.services.auditoria import registrar
from app.services.limite import exigir

router = APIRouter(tags=["mcp-oauth"])


def _erro_em_tela(titulo: str, explicacao: str, detalhe: str | None = None) -> HTMLResponse:
    # 400, não 200: o status também é lido, e um erro com 200 entraria como
    # sucesso em qualquer telemetria pelo caminho.
    return HTMLResponse(telas.tela_de_erro(titulo, explicacao, detalhe), status_code=400)


def _volta_com_erro(redirect_uri: str, erro: str, descricao: str,
                    state: str | None) -> RedirectResponse:
    """Erro devolvido pelo redirect, já com o `iss` (RFC 9207).

    O `iss` vai em TODA resposta de autorização — inclusive nas de erro. É o que
    permite ao cliente detectar mix-up (uma resposta forjada por outro
    autorizador); omiti-lo justamente no erro deixaria o caminho mais fácil de
    explorar sem a proteção.
    """
    campos = {"error": erro, "error_description": descricao, "iss": oauth.issuer()}
    if state:
        campos["state"] = state
    juncao = "&" if "?" in redirect_uri else "?"
    return RedirectResponse(f"{redirect_uri}{juncao}{urlencode(campos)}", status_code=303)


def _parametros(client_id: str, redirect_uri: str, code_challenge: str,
                state: str | None, scope: str | None, resource: str | None) -> dict:
    """O que atravessa as telas em campos ocultos.

    ⚠️ São **reconferidos a cada passo**, nunca confiados por terem vindo de um
    formulário nosso: o HTML está no navegador da pessoa, e campo oculto é
    editável antes do POST.
    """
    return {"client_id": client_id, "redirect_uri": redirect_uri,
            "code_challenge": code_challenge, "state": state,
            "scope": scope, "resource": resource}


def _validar(db: Session, client_id: str, redirect_uri: str, response_type: str,
             code_challenge: str, code_challenge_method: str,
             resource: str | None, state: str | None):
    """Devolve uma resposta de erro, ou `None` se está tudo certo."""
    # ── Bloco A — vira TELA: o destino ainda não é confiável ──
    cliente = oauth.resolver_cliente(db, client_id)
    if cliente is None:
        return _erro_em_tela(
            "Aplicativo não reconhecido",
            "O aplicativo que pediu este acesso não está registrado, ou o "
            "registro dele foi revogado.",
            "Se você está conectando o assistente, remova o conector e "
            "adicione-o de novo.")
    if not oauth.redirect_uri_aceita(redirect_uri, cliente.redirect_uris or []):
        return _erro_em_tela(
            "Endereço de retorno não confere",
            "O endereço para onde este aplicativo quer voltar não é um dos que "
            "ele registrou.",
            "Isso costuma indicar um pedido adulterado. Nada foi concedido.")

    # ── Bloco B — o destino é confiável; o erro volta por lá ──
    if response_type != "code":
        return _volta_com_erro(redirect_uri, "unsupported_response_type",
                               "apenas response_type=code e suportado", state)
    if not code_challenge or code_challenge_method != "S256":
        return _volta_com_erro(redirect_uri, "invalid_request",
                               "PKCE com code_challenge_method=S256 e obrigatorio",
                               state)
    if not resource:
        return _volta_com_erro(redirect_uri, "invalid_request",
                               "o parametro resource e obrigatorio (RFC 8707)", state)
    if not oauth.mesmo_recurso(resource):
        return _volta_com_erro(redirect_uri, "invalid_target",
                               "este servidor nao emite token para esse resource",
                               state)
    return None


@router.get("/authorize")
def autorizar_get(client_id: str = "", redirect_uri: str = "",
                  response_type: str = "", code_challenge: str = "",
                  code_challenge_method: str = "", state: str | None = None,
                  scope: str | None = None, resource: str | None = None,
                  db: Session = Depends(get_db)):
    """Abre o fluxo: valida os parâmetros e pede o login."""
    problema = _validar(db, client_id, redirect_uri, response_type,
                        code_challenge, code_challenge_method, resource, state)
    if problema is not None:
        return problema
    cliente = oauth.resolver_cliente(db, client_id)
    return HTMLResponse(telas.tela_de_login(
        _parametros(client_id, redirect_uri, code_challenge, state, scope, resource),
        cliente.client_name))


@router.post("/authorize")
def autorizar_post(request: Request, client_id: str = Form(""),
                   redirect_uri: str = Form(""), code_challenge: str = Form(""),
                   state: str | None = Form(None), scope: str | None = Form(None),
                   resource: str | None = Form(None),
                   email: str | None = Form(None), senha: str | None = Form(None),
                   decisao: str | None = Form(None),
                   db: Session = Depends(get_db)):
    """Recebe o login e, depois, a decisão."""
    problema = _validar(db, client_id, redirect_uri, "code", code_challenge,
                        "S256", resource, state)
    if problema is not None:
        return problema
    cliente = oauth.resolver_cliente(db, client_id)
    parametros = _parametros(client_id, redirect_uri, code_challenge, state,
                             scope, resource)

    if decisao == "cancelar":
        return _volta_com_erro(redirect_uri, "access_denied",
                               "a pessoa nao autorizou o acesso", state)

    ip = ip_do_cliente(request) or "?"
    # Chaves próprias, separadas das do painel: são dois processos, e o rate
    # limit é em memória por processo — somar seria fingir uma contagem única.
    exigir(f"mcp-authorize:ip:{ip}", maximo=15, janela_s=300)
    if email:
        exigir(f"mcp-authorize:conta:{email.lower()}", maximo=10, janela_s=900)

    usuario = _autenticar(db, email, senha)
    if usuario is None:
        registrar(db, "mcp_login_falhou", ator="rh", ator_detalhe=(email or "")[:200])
        db.commit()
        return HTMLResponse(
            telas.tela_de_login(parametros, cliente.client_name,
                                erro="E-mail ou senha nao conferem."),
            status_code=401)

    # ⚠️ A RECUSA POR PAPEL acontece AQUI, e o lugar é a decisão:
    #   · DEPOIS do login, porque antes não se sabe quem é a pessoa — recusar
    #     por e-mail digitado revelaria quais contas existem;
    #   · ANTES do consentimento, porque a pessoa precisa LER o motivo, e um
    #     `access_denied` pelo redirect vira "falha ao conectar" genérico;
    #   · como TELA, não erro mudo: "errei a conta" e "falta liberação" pedem
    #     ações diferentes (a regra de recusa que oferece a saída, v2.87).
    if (usuario.papel or "") not in oauth.PAPEIS_QUE_PODEM_CONECTAR:
        registrar(db, "mcp_conexao_recusada", ator="rh", ator_detalhe=usuario.email,
                  detalhe={"papel": usuario.papel, "cliente": cliente.client_name})
        db.commit()
        return HTMLResponse(
            telas.tela_de_recusa_por_papel(usuario.nome, _rotulo(usuario.papel)),
            status_code=403)

    if decisao != "autorizar":
        registradas = [u for u in (cliente.redirect_uris or []) if u]
        so_loopback = bool(registradas) and all(oauth.eh_loopback(u) for u in registradas)
        return HTMLResponse(telas.tela_de_consentimento(
            {**parametros, "email": email, "senha": senha},
            cliente.client_name, redirect_uri, usuario.nome, so_loopback))

    _, segredo = oauth.emitir_codigo(db, cliente, usuario, redirect_uri,
                                     code_challenge, resource)
    cliente.usado_em = oauth._agora()
    registrar(db, "mcp_conexao_autorizada", ator="rh", ator_detalhe=usuario.email,
              detalhe={"cliente": cliente.client_name,
                       "destino": urlsplit(redirect_uri).hostname,
                       "papel_do_usuario": usuario.papel,
                       "papel_concedido": oauth.PAPEL_DO_TOKEN})
    db.commit()

    campos = {"code": segredo, "iss": oauth.issuer()}
    if state:
        campos["state"] = state
    juncao = "&" if "?" in redirect_uri else "?"
    return RedirectResponse(f"{redirect_uri}{juncao}{urlencode(campos)}", status_code=303)


def _autenticar(db: Session, email: str | None, senha: str | None) -> UsuarioRH | None:
    """Mesmo corpo do `login()` do painel — inclusive a resposta única.

    Não distingue "e-mail não existe" de "senha errada" nem de "conta inativa":
    a diferença diria a quem testa credenciais quais contas existem.
    """
    if not email or not senha:
        return None
    usuario = db.scalar(select(UsuarioRH).where(
        UsuarioRH.email == email.lower().strip()))
    if usuario is None or not usuario.ativo:
        return None
    if not verificar_senha(senha, usuario.senha_hash):
        return None
    return usuario


def _rotulo(papel: str | None) -> str:
    from app.services.permissoes import PAPEIS_POR_CHAVE

    registro = PAPEIS_POR_CHAVE.get((papel or "").strip())
    return registro.rotulo if registro else (papel or "sem perfil")
