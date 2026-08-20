"""O provedor OAuth do MCP: emitir, resolver e revogar.

Molde: `token_automacao.py` (v2.94). As regras que NÃO devem ser afrouxadas são
as mesmas — casa por HASH e nunca por prefixo; usuário inativo NEGA; devolve
`None` para todos os motivos (distinguir na resposta diria a quem testa
credenciais qual delas já existiu); revogar MARCA e não apaga.

O que este módulo acrescenta ao molde, e por quê:

- **Rotação com detecção de reuso.** Cliente público precisa rotacionar o
  refresh (OAuth 2.1). Aqui a rotação guarda o hash ANTERIOR: se ele reaparecer,
  é cópia roubada, e a resposta é revogar a concessão inteira — não só recusar
  aquele pedido.
- **Audiência (RFC 8707).** O access token diz para QUAL recurso vale, e o
  `/mcp` recusa o que foi emitido para outro. Sem isso, um token de qualquer
  serviço que compartilhe o `SECRET_KEY` seria aceito aqui.
- **O papel é trocado na resolução.** Ver `identidade_do_access_token`.
"""

from __future__ import annotations

import base64
import hashlib
import secrets
from datetime import datetime, timedelta, timezone

from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.mcp_oauth import ClienteOAuth, CodigoAutorizacao, Concessao
from app.models.usuario_rh import UsuarioRH

# ── As constantes que sustentam as decisões do desenho ────────────────────────

#: O papel que o token carrega — SEMPRE, para qualquer pessoa que autorize.
#: Doc 17 § 4.1: a superfície da IA é deliberadamente menor que a da pessoa,
#: porque a IA executa instrução vinda de texto e, neste sistema, o texto vem de
#: currículo e de campo livre.
PAPEL_DO_TOKEN = "assistente_rh"

#: Quem pode conectar o assistente (decisão do Bruno, 20/08/2026).
#: ⚠️ `automacao` e `assistente_rh` estão FORA de propósito: são papéis de
#: MÁQUINA, não de gente — ninguém tem senha neles. Acrescentá-los aqui criaria
#: o laço da conta de máquina conectando a si mesma.
PAPEIS_QUE_PODEM_CONECTAR = frozenset({"superadmin", "admin", "rh"})

#: O único escopo. `offline_access` NÃO entra aqui: o refresh não é exigência do
#: recurso, e a spec pede que o resource server não o anuncie.
ESCOPO = "portal:assistente"

PREFIXO_CLIENTE = "mcpc_"
PREFIXO_CODIGO = "mcpa_"
PREFIXO_REFRESH = "mcpr_"

#: 60s, não 10 min: o code viaja na URL, e URL fica no histórico do navegador e
#: no log de todo proxy do caminho. A troca acontece em milissegundos.
CODIGO_TTL_S = 60

#: 10 min. Curto porque o access é assinado (não consultável para revogar) — mas
#: a revogação continua imediata, porque o `/mcp` consulta a CONCESSÃO a cada
#: chamada.
ACCESS_TTL_S = 600

#: 90 dias. Nulo seria "não expira", e credencial que nunca vence é a que
#: ninguém lembra de revogar.
REFRESH_TTL_DIAS = 90


def _hash(segredo: str) -> str:
    return hashlib.sha256(segredo.encode()).hexdigest()


def _agora() -> datetime:
    return datetime.now(timezone.utc)


# ── Issuer e resource canônicos ───────────────────────────────────────────────


def issuer() -> str:
    """A URL canônica do provedor.

    ⚠️ **NÃO usar `base_url_publica(request)`.** Ela deriva do cabeçalho `Host`,
    o que é certo para link mágico e reset de senha e ERRADO aqui: quem
    conseguisse forjar o `Host` faria o metadata anunciar um issuer que não é o
    nosso, e o `iss` da RFC 9207 mentiria — confused deputy clássico.

    Vazio RECUSA, em vez de cair no `base_url` do `.env`: o padrão dele é
    `http://localhost:8090`, e um provedor anunciando isso em produção passaria
    na descoberta e falharia no callback, com o sintoma longe da causa.
    """
    valor = (get_settings().mcp_issuer or "").strip().rstrip("/")
    if not valor:
        raise RuntimeError(
            "MCP_ISSUER não configurado. É a URL pública canônica do portal "
            "(ex.: https://rh.suaempresa.com.br) e não pode ser derivada do "
            "cabeçalho Host — o OAuth exige um issuer estável."
        )
    return valor


def resource() -> str:
    """O identificador do recurso protegido — o que o Claude vai chamar.

    Precisa bater EXATAMENTE com a URL que a pessoa digita no Claude. A
    comparação normaliza a barra final dos dois lados; o anúncio é sempre sem.
    """
    return f"{issuer()}/mcp"


def mesmo_recurso(apresentado: str | None) -> bool:
    if not apresentado:
        return False
    return apresentado.strip().rstrip("/") == resource().rstrip("/")


# ── PKCE ──────────────────────────────────────────────────────────────────────


def confere_pkce(code_verifier: str, code_challenge: str) -> bool:
    """S256, e só S256.

    `plain` é o que o OAuth 2.1 fechou: com ele o desafio É o segredo, e quem
    intercepta o redirect intercepta os dois. Comparação em tempo constante.
    """
    if not code_verifier or not code_challenge:
        return False
    digest = hashlib.sha256(code_verifier.encode("ascii")).digest()
    calculado = base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")
    return secrets.compare_digest(calculado, code_challenge)


# ── redirect_uri ──────────────────────────────────────────────────────────────


def _partes(uri: str) -> tuple[str, str, int | None, str]:
    from urllib.parse import urlsplit

    p = urlsplit(uri)
    return p.scheme.lower(), (p.hostname or "").lower(), p.port, p.path or "/"


def redirect_uri_aceita(apresentada: str, registradas: list[str]) -> bool:
    """Casa exato — MENOS a porta, quando o destino é loopback.

    ⚠️ O Claude Code sorteia uma porta a cada execução (RFC 8252 § 7.3). Exigir
    a porta faria a conexão funcionar na primeira vez e falhar em toda
    reconexão — o sintoma seria "às vezes funciona", que é caro de diagnosticar.
    Para `https`, a comparação é exata (só a barra final é normalizada).
    """
    if not apresentada:
        return False
    esq = _partes(apresentada)
    for registrada in registradas or []:
        dir_ = _partes(registrada)
        eh_loopback = esq[0] == "http" and esq[1] in ("localhost", "127.0.0.1", "::1")
        if eh_loopback:
            if esq[0] == dir_[0] and esq[1] == dir_[1] and esq[3] == dir_[3]:
                return True
        elif apresentada.rstrip("/") == registrada.rstrip("/"):
            return True
    return False


def eh_loopback(uri: str) -> bool:
    esq = _partes(uri)
    return esq[0] == "http" and esq[1] in ("localhost", "127.0.0.1", "::1")


# ── Cliente ───────────────────────────────────────────────────────────────────


def registrar_cliente(db: Session, client_name: str, redirect_uris: list[str],
                      origem: str = "dcr", ip: str | None = None) -> ClienteOAuth:
    """Registro dinâmico (RFC 7591).

    ⚠️ **Registrar NÃO dá acesso.** O endpoint é público por definição do
    protocolo, e isso é aceitável porque sem alguém fazer login em `/authorize`
    e autorizar, o cliente registrado não obtém token nenhum. Quem ler isto e
    quiser "fechar o buraco" fechando o endpoint vai quebrar a conexão.
    """
    registro = ClienteOAuth(
        client_id=PREFIXO_CLIENTE + secrets.token_urlsafe(24),
        # O nome vai para a TELA de consentimento, que é HTML. Cortar e deixar o
        # escape para o template não basta — cortar aqui limita o estrago.
        client_name=(client_name or "Aplicativo").strip()[:200],
        redirect_uris=list(redirect_uris or []),
        origem=origem,
        criado_por_ip=(ip or None),
    )
    db.add(registro)
    db.flush()
    return registro


def resolver_cliente(db: Session, client_id: str | None) -> ClienteOAuth | None:
    if not client_id:
        return None
    registro = db.scalar(select(ClienteOAuth).where(ClienteOAuth.client_id == client_id))
    if registro is None or not registro.valido:
        return None
    return registro


# ── Authorization code ────────────────────────────────────────────────────────


def emitir_codigo(db: Session, cliente: ClienteOAuth, usuario: UsuarioRH,
                  redirect_uri: str, code_challenge: str,
                  recurso: str) -> tuple[CodigoAutorizacao, str]:
    segredo = PREFIXO_CODIGO + secrets.token_urlsafe(32)
    registro = CodigoAutorizacao(
        codigo_hash=_hash(segredo),
        cliente_id=cliente.id,
        usuario_id=usuario.id,
        redirect_uri=redirect_uri,
        resource=recurso,
        escopo=ESCOPO,
        code_challenge=code_challenge,
        expira_em=_agora() + timedelta(seconds=CODIGO_TTL_S),
    )
    db.add(registro)
    db.flush()
    return registro, segredo


def resolver_codigo(db: Session, apresentado: str | None) -> CodigoAutorizacao | None:
    """Devolve a linha do code, válida ou NÃO — quem chama decide.

    Diferente do molde: aqui interessa distinguir "não existe" de "já foi
    usado", porque **code reapresentado é sinal de roubo** e a resposta é
    revogar a concessão que ele gerou. A distinção fica no servidor; a resposta
    ao cliente continua sendo o mesmo `invalid_grant` para todos os casos.
    """
    if not apresentado or not apresentado.startswith(PREFIXO_CODIGO):
        return None
    return db.scalar(select(CodigoAutorizacao).where(
        CodigoAutorizacao.codigo_hash == _hash(apresentado)))


# ── Concessão e refresh ───────────────────────────────────────────────────────


def abrir_concessao(db: Session, codigo: CodigoAutorizacao,
                    usuario: UsuarioRH) -> tuple[Concessao, str]:
    segredo = PREFIXO_REFRESH + secrets.token_urlsafe(32)
    registro = Concessao(
        cliente_id=codigo.cliente_id,
        usuario_id=codigo.usuario_id,
        refresh_hash=_hash(segredo),
        refresh_prefixo=segredo[:16],
        resource=codigo.resource,
        escopo=codigo.escopo,
        papel_concedido=PAPEL_DO_TOKEN,
        # Snapshot para a auditoria responder "quem era ela quando conectou?".
        # NÃO é usado para autorizar — ver o comentário no modelo.
        papel_do_usuario=(usuario.papel or ""),
        expira_em=_agora() + timedelta(days=REFRESH_TTL_DIAS),
    )
    db.add(registro)
    db.flush()
    return registro, segredo


def rotacionar(db: Session, concessao: Concessao) -> str:
    """Gera o refresh novo e invalida o anterior — no MESMO ato.

    ⚠️ O novo refresh tem que sair na MESMA resposta que invalida o antigo. Se a
    resposta trouxer só o access, o cliente fica com um refresh morto e a
    reconexão para de funcionar dez minutos depois — o pior sintoma possível,
    porque parece intermitência de rede.
    """
    novo = PREFIXO_REFRESH + secrets.token_urlsafe(32)
    concessao.refresh_hash_anterior = concessao.refresh_hash
    concessao.refresh_hash = _hash(novo)
    concessao.refresh_prefixo = novo[:16]
    concessao.geracao = (concessao.geracao or 1) + 1
    concessao.usado_em = _agora()
    db.flush()
    return novo


def resolver_refresh(db: Session, apresentado: str | None) -> tuple[Concessao | None, bool]:
    """Devolve `(concessao, reuso_detectado)`.

    `reuso_detectado=True` significa que o refresh apresentado é uma geração
    ANTERIOR: alguém tem uma cópia. Quem chama deve revogar a concessão inteira
    — recusar só aquele pedido deixaria a credencial legítima viva nas mãos de
    quem a roubou.
    """
    if not apresentado or not apresentado.startswith(PREFIXO_REFRESH):
        return None, False
    alvo = _hash(apresentado)
    atual = db.scalar(select(Concessao).where(Concessao.refresh_hash == alvo))
    if atual is not None:
        return atual, False
    anterior = db.scalar(select(Concessao).where(Concessao.refresh_hash_anterior == alvo))
    if anterior is not None:
        return anterior, True
    return None, False


def revogar(db: Session, concessao: Concessao, por: str | None = None,
            motivo: str = "usuario") -> None:
    """MARCA, não apaga — a linha é prova de que existiu e de quando parou."""
    if concessao.revogado_em is None:
        concessao.revogado_em = _agora()
        concessao.revogado_por = por
        concessao.revogado_motivo = motivo
        db.flush()


# ── Access token (assinado) ───────────────────────────────────────────────────


def _serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(get_settings().secret_key, salt="mcp-access")


def emitir_access(concessao: Concessao) -> str:
    return _serializer().dumps({
        "sub": str(concessao.usuario_id),
        "aud": concessao.resource,
        "gid": str(concessao.id),
    })


def identidade_do_access_token(db: Session, apresentado: str | None) -> UsuarioRH | None:
    """Devolve o usuário do token **já com o papel do assistente**.

    ⚠️ **O objeto devolvido NÃO é o do banco.** É um `UsuarioRH` transiente,
    construído aqui, com `papel = PAPEL_DO_TOKEN`. Duas razões, nesta ordem:

    1. `permissoes_do_usuario` lê `usuario.papel` do OBJETO. Devolver o do banco
       faria a pessoa agir com o papel do dia a dia dela — 27 permissões em vez
       de 15, incluindo desligar colaborador. E **nada daria erro**: as
       ferramentas passariam a funcionar melhor. É o defeito de acesso a mais,
       que ninguém reporta.
    2. Mutar o objeto carregado e deixar a sessão commitar **gravaria
       `assistente_rh` na linha real da pessoa** — ela perderia o acesso ao
       painel, e a causa estaria noutro serviço, a três arquivos de distância.
       Objeto que nunca esteve na sessão não pode ser gravado por acidente; é
       mais seguro que lembrar de chamar `db.expunge()`.

    Como o molde: devolve `None` para todos os motivos.
    """
    if not apresentado:
        return None
    try:
        dados = _serializer().loads(apresentado, max_age=ACCESS_TTL_S)
    except (BadSignature, SignatureExpired):
        return None

    # RFC 8707: o token diz para qual recurso foi emitido. Sem esta checagem,
    # um token emitido por outro serviço que compartilhe o SECRET_KEY valeria
    # aqui — é o confused deputy que a spec manda fechar.
    if not mesmo_recurso(dados.get("aud")):
        return None

    concessao = db.get(Concessao, _uuid(dados.get("gid")))
    # É esta consulta que faz "revoguei e parou de funcionar" valer DENTRO dos
    # 10 minutos de vida do access. Sem ela, revogar não cortaria nada até o
    # token expirar sozinho.
    if concessao is None or not concessao.valido:
        return None

    real = db.get(UsuarioRH, _uuid(dados.get("sub")))
    if real is None or not real.ativo:
        return None
    # O papel do dia a dia dela pode ter mudado desde que autorizou.
    if (real.papel or "") not in PAPEIS_QUE_PODEM_CONECTAR:
        return None

    anterior = concessao.usado_em
    agora = _agora()
    if anterior is None or (agora - anterior).total_seconds() > 60:
        concessao.usado_em = agora

    return UsuarioRH(
        id=real.id, nome=real.nome, email=real.email,
        senha_hash=real.senha_hash, ativo=real.ativo,
        papel=PAPEL_DO_TOKEN,
    )


def _uuid(valor):
    import uuid as _u

    try:
        return _u.UUID(str(valor))
    except (ValueError, TypeError, AttributeError):
        return None
