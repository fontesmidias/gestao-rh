import uuid

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, EmailStr
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import base_url_publica, ip_do_cliente
from app.core.db import get_db
from app.core.security import (criar_token_reset, criar_token_sessao, hash_senha,
                               validar_token_reset, validar_token_sessao, verificar_senha)
from app.services.auditoria import registrar
from app.services.email_templates import enviar_modelo
from app.services.limite import exigir
from app.services.nomes import capitalizar_nome
from app.models.usuario_rh import UsuarioRH

router = APIRouter(tags=["auth-rh"])

_bearer = HTTPBearer(auto_error=False)


class LoginOut(BaseModel):
    token: str
    nome: str


SENHA_MINIMA = 8


def exigir_senha_forte(senha: str) -> None:
    """Regra única de senha do painel (v2.84).

    Existia repetida em QUATRO lugares (`redefinir-senha`, `criar_usuario`,
    `trocar_senha` e `me/senha`), cada um com o mesmo `len(...) < 8` escrito à
    mão. Repetição de regra é como ela envelhece torto: basta alguém endurecer
    num ponto para haver duas políticas de senha no mesmo sistema, e a mais
    fraca é a que vale — porque é por ela que se cria o usuário.
    """
    if len(senha or "") < SENHA_MINIMA:
        raise HTTPException(status_code=422, detail="senha_curta_minimo_8")


# --- Primeiro acesso -------------------------------------------------------
#
# O primeiro administrador nascia do `.env` (`RH_ADMIN_EMAIL`/`_PASSWORD`), o
# que obrigava a escrever uma senha em arquivo e — num repositório PÚBLICO —
# publicava o endereço de quem opera o sistema junto com o exemplo. Agora, com a
# tabela vazia, o painel abre um cadastro guiado.
#
# ⚠️ **O portão é o BANCO, não a tela**: as duas rotas abaixo são públicas por
# necessidade (não há quem autentique antes do primeiro usuário), então quem
# decide é `select(UsuarioRH).limit(1) is None`. Criado o primeiro, as duas
# fecham para sempre — a de criação responde 409 e a de consulta diz `false`.
# Sem esse gate, seria uma porta aberta para criar administrador em produção.


def _sem_usuarios(db: Session) -> bool:
    return db.scalar(select(UsuarioRH).limit(1)) is None


@router.get("/rh/auth/primeiro-acesso")
def primeiro_acesso_necessario(db: Session = Depends(get_db)) -> dict:
    """Diz se o sistema ainda não tem NENHUM usuário.

    Pública de propósito, e por isso devolve só um booleano: quem pergunta é a
    tela de login, antes de existir sessão. Não revela nome, e-mail nem
    contagem — só se o sistema está por configurar, que é o que uma instalação
    nova anuncia de qualquer forma ao abrir o cadastro.
    """
    return {"necessario": _sem_usuarios(db)}


class PrimeiroAcessoIn(BaseModel):
    nome: str
    email: EmailStr
    senha: str


@router.post("/rh/auth/primeiro-acesso", response_model=LoginOut)
def criar_primeiro_usuario(payload: PrimeiroAcessoIn, request: Request,
                           db: Session = Depends(get_db)) -> LoginOut:
    """Cria o primeiro administrador e já devolve a sessão dele.

    Entrar direto não é conveniência: mandar a pessoa "agora faça login" logo
    depois de ela escolher a senha é um passo a mais para errar, e o ato de
    criar já prova quem ela é — foi ela quem definiu a credencial, agora.
    """
    ip = ip_do_cliente(request) or "?"
    # Mesmo com o gate do banco: sem limite, uma instalação recém-subida e ainda
    # sem dono pode ser varrida por robô até alguém acertar o primeiro POST.
    exigir(f"primeiro-acesso:ip:{ip}", maximo=10, janela_s=900)

    if not _sem_usuarios(db):
        # 409, não 403: o pedido não é proibido, ele deixou de fazer sentido.
        raise HTTPException(status_code=409, detail="primeiro_acesso_ja_feito")

    nome = (payload.nome or "").strip()
    if not nome:
        raise HTTPException(status_code=422, detail="nome_obrigatorio")
    exigir_senha_forte(payload.senha)

    # O primeiro usuário nasce SUPERADMIN (v2.86): é ele quem vai definir os
    # papéis de todo mundo. Nascer como `rh` deixaria a instalação sem ninguém
    # capaz de gerir permissões, e sem tela para corrigir isso.
    usuario = UsuarioRH(nome=capitalizar_nome(nome), email=str(payload.email).lower(),
                        senha_hash=hash_senha(payload.senha), papel="superadmin")
    db.add(usuario)
    db.flush()
    registrar(db, "primeiro_acesso", ator="rh", ator_detalhe=usuario.email,
              detalhe=f"primeiro administrador criado pela tela (IP {ip})")
    db.commit()
    return LoginOut(token=criar_token_sessao(str(usuario.id)), nome=usuario.nome)


class LoginIn(BaseModel):
    email: EmailStr
    senha: str


@router.post("/rh/auth/login", response_model=LoginOut)
def login(payload: LoginIn, request: Request, db: Session = Depends(get_db)) -> LoginOut:
    # Anti-força-bruta: por IP e por conta (a chave por conta segura ataque
    # distribuído numa mesma vítima; a por IP segura varredura de senhas).
    ip = ip_do_cliente(request) or "?"
    exigir(f"login:ip:{ip}", maximo=15, janela_s=300)
    exigir(f"login:conta:{payload.email.lower()}", maximo=10, janela_s=900)
    usuario = db.scalar(select(UsuarioRH).where(UsuarioRH.email == payload.email.lower()))
    if usuario is None or not usuario.ativo or not verificar_senha(payload.senha, usuario.senha_hash):
        registrar(db, "login_falhou", ator="rh", ator_detalhe=payload.email)
        db.commit()
        # Mensagem única: não revelar se o e-mail existe.
        raise HTTPException(status_code=401, detail="credenciais_invalidas")
    registrar(db, "login_ok", ator="rh", ator_detalhe=usuario.email)
    db.commit()
    return LoginOut(token=criar_token_sessao(str(usuario.id)), nome=usuario.nome)


class EsqueciSenhaIn(BaseModel):
    email: EmailStr


@router.post("/rh/auth/esqueci-senha", status_code=204)
def esqueci_senha(payload: EsqueciSenhaIn, request: Request,
                  db: Session = Depends(get_db)) -> None:
    """Sempre responde 204 (não revela se o e-mail existe). Se existir e estiver
    ativo, envia link de redefinição válido por 30 minutos."""
    exigir(f"reset:ip:{ip_do_cliente(request) or '?'}", maximo=5, janela_s=900)
    usuario = db.scalar(select(UsuarioRH).where(UsuarioRH.email == payload.email.lower()))
    registrar(db, "reset_senha_solicitado", ator="rh", ator_detalhe=payload.email.lower())
    db.commit()
    if usuario is None or not usuario.ativo:
        return
    token = criar_token_reset(str(usuario.id), usuario.senha_hash)
    link = f"{base_url_publica(request)}/rh?redefinir={token}"
    try:
        enviar_modelo(db, "rh_redefinir_senha", usuario.email, {
        "primeiro_nome": (usuario.nome or "").split()[0].title(),
        "link": link, "ttl": 30,
    })
    except Exception:
        # Não propaga o erro para não revelar se o e-mail existe; fica na auditoria.
        registrar(db, "reset_senha_email_falhou", ator="sistema", ator_detalhe=usuario.email)
        db.commit()


class RedefinirSenhaIn(BaseModel):
    token: str
    senha_nova: str


@router.post("/rh/auth/redefinir-senha", status_code=204)
def redefinir_senha(payload: RedefinirSenhaIn, request: Request,
                    db: Session = Depends(get_db)) -> None:
    exigir(f"redefinir:ip:{ip_do_cliente(request) or '?'}", maximo=10, janela_s=900)
    dados = validar_token_reset(payload.token)
    if dados is None:
        raise HTTPException(status_code=422, detail="link_invalido_ou_expirado")
    usuario = db.get(UsuarioRH, uuid.UUID(dados["sub"]))
    # O fragmento do hash garante uso único: após a troca, o token antigo morre.
    if usuario is None or not usuario.ativo or usuario.senha_hash[-16:] != dados["h"]:
        raise HTTPException(status_code=422, detail="link_invalido_ou_expirado")
    exigir_senha_forte(payload.senha_nova)
    usuario.senha_hash = hash_senha(payload.senha_nova)
    registrar(db, "senha_redefinida_por_link", ator="rh", ator_detalhe=usuario.email)
    db.commit()


def requer_rh(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: Session = Depends(get_db),
) -> UsuarioRH:
    """Autentica quem está chamando — responde só *"está logado?"*.

    ⚠️ **Não use isto para proteger rota nova.** Ela autentica e nada mais;
    quem AUTORIZA é `exige("permissao")` (abaixo). Continua aqui, e continua
    pública, por dois motivos legítimos: as rotas de perfil próprio (`/rh/me`),
    que qualquer usuário do painel acessa por definição, e o `exige` em si, que
    a compõe. O `test_permissoes_declaradas.py` reprova no CI a rota `/rh/*`
    que se proteger só com ela.
    """
    if credentials is None:
        raise HTTPException(status_code=401, detail="nao_autenticado")
    usuario_id = validar_token_sessao(credentials.credentials)
    if usuario_id is None:
        raise HTTPException(status_code=401, detail="sessao_invalida_ou_expirada")
    usuario = db.get(UsuarioRH, uuid.UUID(usuario_id))
    if usuario is None or not usuario.ativo:
        raise HTTPException(status_code=401, detail="usuario_inativo")
    # A partir daqui, toda linha de log desta requisição sai com o e-mail de
    # quem está agindo (v2.41): "alguém reprovou o documento" precisa ter dono.
    from app.services.contexto_log import definir_ator
    definir_ator(usuario.email)
    return usuario


def permissoes_do_usuario(db: Session, usuario: UsuarioRH) -> frozenset[str]:
    """Permissões efetivas de um usuário, a partir do papel dele.

    A ordem é: papel gravado no banco → padrão de fábrica → **nada**. O último
    degrau é o que importa: papel que não se resolve (removido, renomeado à mão,
    escrito errado numa migration) devolve conjunto VAZIO, que NEGA. O contrário
    — cair num padrão permissivo — deixaria um papel quebrado passar por
    administrador, e o sintoma seria acesso a mais, que ninguém reporta.
    """
    from app.models.papel import Papel
    from app.services import permissoes as cat

    papel = (usuario.papel or "").strip()
    if papel == cat.PAPEL_SUPERADMIN:
        # Não consulta lista: é o que faz módulo novo nascer liberado para ele.
        return cat.CHAVES

    registro = db.scalar(select(Papel).where(Papel.chave == papel))
    if registro is not None:
        return frozenset(registro.permissoes or ())
    return cat.permissoes_padrao(papel)


def exige(permissao: str):
    """Dependência que exige UMA permissão nomeada. É a porta das rotas `/rh/*`.

        @router.post("/rh/colaboradores/{cid}/desligar")
        def desligar(..., rh: UsuarioRH = Depends(exige("colaboradores:desligar"))):

    A chave é conferida contra o catálogo **na importação do módulo**, não na
    primeira requisição: permissão escrita errada derruba o boot com o nome do
    erro, em vez de virar um 403 em produção que ninguém liga à causa. É a mesma
    escolha do `_conferir_catalogo` dos documentos (v2.67).
    """
    from app.services import permissoes as cat

    if permissao not in cat.CHAVES:
        raise KeyError(
            f"permissao_desconhecida: {permissao!r} — acrescente ao catálogo em "
            "app/services/permissoes.py antes de usá-la numa rota."
        )

    def _dependencia(usuario: UsuarioRH = Depends(requer_rh),
                     db: Session = Depends(get_db)) -> UsuarioRH:
        concedidas = permissoes_do_usuario(db, usuario)
        if not cat.pode(usuario.papel or "", concedidas, permissao):
            # 403 e não 404: a rota existe e a pessoa está autenticada. O
            # `detail` NOMEIA a permissão que falta, porque quem lê isso é o
            # superadmin tentando entender por que a colega não consegue — sem
            # o nome, ele procuraria no papel errado.
            raise HTTPException(status_code=403, detail={
                "erro": "sem_permissao", "permissao": permissao,
                "rotulo": cat.POR_CHAVE[permissao].rotulo,
            })
        return usuario

    return _dependencia
