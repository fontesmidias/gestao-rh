"""As três telas do `/authorize`: login, consentimento e recusa.

São HTML servido pelo backend, e não o SPA do painel, por uma razão prática: o
SPA guarda o token em `localStorage` e não sabe voltar para cá com os parâmetros
do OAuth. Uma tela dedicada é menor que o desvio.

⚠️ **Tudo que vem de fora é escapado.** O `client_name` e o `redirect_uri` são
digitados por quem registrou o cliente — que é qualquer um, já que o `/register`
é público por especificação. Interpolar isso cru numa página seria XSS na
própria tela de autorização, que é a última que deveria confiar em texto de
terceiro.

O visual segue o portal (as mesmas cores e a mesma sobriedade), mas o CSS é
embutido: a tela precisa funcionar antes de qualquer sessão existir, e depender
do bundle do SPA aqui seria depender de um deploy do front para consertar um
problema de autenticação.
"""

from __future__ import annotations

from html import escape
from urllib.parse import urlsplit

_ESTILO = """
:root { color-scheme: light dark; }
* { box-sizing: border-box; }
body {
  margin: 0; min-height: 100vh; display: flex; align-items: center;
  justify-content: center; padding: 1.5rem;
  font-family: "Segoe UI", system-ui, -apple-system, sans-serif;
  background: #f4f6f5; color: #1d2b25;
}
@media (prefers-color-scheme: dark) {
  body { background: #121714; color: #e8efe9; }
  .cartao { background: #1b2320; border-color: #2b3a33; }
  .campo input { background: #121714; color: #e8efe9; border-color: #2b3a33; }
  .destaque { background: #12211a; border-color: #2f5c45; }
  .rodape { color: #9bb0a4; }
}
.cartao {
  width: 100%; max-width: 27rem; background: #fff; border: 1px solid #dfe6e2;
  border-radius: 14px; padding: 1.75rem; box-shadow: 0 6px 24px rgba(0,0,0,.06);
}
h1 { font-size: 1.25rem; margin: 0 0 .35rem; }
p  { margin: .5rem 0; line-height: 1.5; }
.sub { color: #5d716a; font-size: .92rem; margin-top: 0; }
@media (prefers-color-scheme: dark) { .sub { color: #9bb0a4; } }
.campo { display: block; margin: .85rem 0; }
.campo span { display: block; font-size: .86rem; margin-bottom: .3rem; font-weight: 600; }
.campo input {
  width: 100%; padding: .6rem .7rem; font-size: 1rem; border-radius: 8px;
  border: 1px solid #cfdad4; background: #fff; color: inherit;
}
.destaque {
  background: #eef7f1; border: 1px solid #cfe6d9; border-radius: 10px;
  padding: .8rem .9rem; margin: 1rem 0; font-size: .93rem;
}
.destaque strong { word-break: break-all; }
.aviso {
  background: #fff6e5; border: 1px solid #f0d9a8; color: #6b4e12;
  border-radius: 10px; padding: .75rem .9rem; margin: 1rem 0; font-size: .9rem;
}
.erro {
  background: #fdeceb; border: 1px solid #f2c3bf; color: #8a2b23;
  border-radius: 10px; padding: .7rem .85rem; margin: .9rem 0; font-size: .92rem;
}
.acoes { display: flex; gap: .6rem; flex-wrap: wrap; margin-top: 1.2rem; }
button, .botao {
  flex: 1 1 9rem; padding: .68rem 1rem; font-size: .97rem; font-weight: 600;
  border-radius: 9px; border: 1px solid transparent; cursor: pointer;
  font-family: inherit; text-align: center; text-decoration: none;
}
.principal { background: #1f7a4d; color: #fff; }
.secundario { background: transparent; color: inherit; border-color: #cfdad4; }
ul { margin: .5rem 0 0; padding-left: 1.15rem; }
li { margin: .3rem 0; line-height: 1.45; }
.rodape { margin-top: 1.3rem; font-size: .82rem; color: #5d716a; }
"""


def _pagina(titulo: str, corpo: str) -> str:
    return (
        "<!doctype html><html lang='pt-BR'><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width, initial-scale=1'>"
        f"<title>{escape(titulo)}</title><style>{_ESTILO}</style></head>"
        f"<body><main class='cartao'>{corpo}</main></body></html>"
    )


def _campos_ocultos(parametros: dict) -> str:
    return "".join(
        f"<input type='hidden' name='{escape(k)}' value='{escape(str(v))}'>"
        for k, v in parametros.items() if v is not None
    )


def tela_de_login(parametros: dict, aplicativo: str, erro: str | None = None) -> str:
    """Pede e-mail e senha do portal.

    Diz **qual aplicativo** está pedindo já aqui: quem chega nesta tela veio de
    um redirect e pode não lembrar o que iniciou. Sem isso, a tela é um pedido de
    senha sem contexto — que é exatamente o que se ensina a não atender.
    """
    bloco_erro = f"<p class='erro'>{escape(erro)}</p>" if erro else ""
    return _pagina("Entrar no portal", f"""
      <h1>Entrar no portal</h1>
      <p class='sub'>{escape(aplicativo)} está pedindo acesso à sua conta.</p>
      {bloco_erro}
      <form method='post' action='/authorize'>
        {_campos_ocultos(parametros)}
        <label class='campo'><span>E-mail</span>
          <input type='email' name='email' autocomplete='username' required autofocus></label>
        <label class='campo'><span>Senha</span>
          <input type='password' name='senha' autocomplete='current-password' required></label>
        <div class='acoes'><button class='principal' type='submit'>Entrar</button></div>
      </form>
      <p class='rodape'>Use a mesma conta com que você acessa o portal.</p>
    """)


def tela_de_consentimento(parametros: dict, aplicativo: str, redirect_uri: str,
                          nome_da_pessoa: str, so_loopback: bool) -> str:
    """A tela que a pessoa realmente lê antes de conceder.

    Três coisas são obrigatórias aqui, e cada uma tem um motivo:

    1. **O hostname do redirect em destaque.** É a defesa contra um cliente
       registrado com o nome "Claude" e um destino diferente — o nome é texto
       livre de quem registrou; o destino é para onde a credencial vai de fato.
    2. **Aviso quando o destino é só loopback.** Qualquer processo no computador
       da pessoa pode abrir uma porta e dizer que é o aplicativo; nenhum
       documento de metadados prova o contrário.
    3. **O que se concede, em português, e o que NÃO se concede.** "Autorizar o
       acesso" não diz nada; dizer que efetivar, desligar e decidir reembolso
       continuam só pela tela diz.
    """
    host = escape(urlsplit(redirect_uri).hostname or redirect_uri)
    aviso = ""
    if so_loopback:
        aviso = ("<p class='aviso'>⚠️ Este aplicativo roda no seu próprio "
                 "computador. Só continue se foi você que iniciou a conexão "
                 "agora — qualquer programa local pode fazer este pedido.</p>")
    return _pagina("Autorizar acesso", f"""
      <h1>Autorizar {escape(aplicativo)}?</h1>
      <p class='sub'>Você está entrando como <strong>{escape(nome_da_pessoa)}</strong>.</p>
      <div class='destaque'>As informações serão enviadas para
        <strong>{host}</strong></div>
      {aviso}
      <p>O assistente vai poder, <strong>em seu nome</strong>:</p>
      <ul>
        <li>consultar admissões, colaboradores, vagas e benefícios;</li>
        <li>cadastrar talento, corrigir ficha, aprovar documento e gerar dossiê;</li>
        <li>marcar e registrar entrevista.</li>
      </ul>
      <p>Continuam <strong>só pela tela do portal</strong>, com uma pessoa
        olhando: efetivar, desligar, decidir reembolso-creche, assinar documento
        e exportar a base.</p>
      <form method='post' action='/authorize'>
        {_campos_ocultos(parametros)}
        <input type='hidden' name='decisao' value='autorizar'>
        <div class='acoes'>
          <button class='principal' type='submit'>Autorizar</button>
          <button class='secundario' type='submit' name='decisao' value='cancelar'
                  formnovalidate>Cancelar</button>
        </div>
      </form>
      <p class='rodape'>Você pode revogar este acesso a qualquer momento nas
        configurações do portal.</p>
    """)


def tela_de_recusa_por_papel(nome_da_pessoa: str, rotulo_do_papel: str) -> str:
    """Quando o login deu certo mas o papel não pode conectar.

    A recusa **diz o motivo e o que resolve**, em vez de um erro mudo: quem lê
    isto precisa saber se errou a conta ou se falta uma liberação, e essas duas
    situações pedem ações diferentes (regra da casa desde a v2.87). Devolver
    `access_denied` pelo redirect faria o Claude mostrar um "falha ao conectar"
    genérico — e a pessoa nunca leria o porquê.
    """
    return _pagina("Acesso não liberado", f"""
      <h1>Seu acesso ao assistente não está liberado</h1>
      <p>Você entrou como <strong>{escape(nome_da_pessoa)}</strong>, com o perfil
        <strong>{escape(rotulo_do_papel)}</strong>.</p>
      <p>A conexão com o assistente é liberada para os perfis
        <strong>RH</strong>, <strong>Administrador</strong> e
        <strong>Superadministrador</strong>.</p>
      <p class='rodape'>Se você precisa desse acesso, fale com quem administra o
        portal — a liberação é uma mudança de perfil, feita em Configurações →
        Equipe. Seu acesso ao portal pela tela continua normal.</p>
    """)


def tela_de_erro(titulo: str, explicacao: str, detalhe: str | None = None) -> str:
    """Erro que NÃO pode voltar pelo redirect.

    Quando o `client_id` não resolve ou o `redirect_uri` não confere, mandar a
    pessoa de volta seria mandá-la para um destino que não foi verificado — o
    open redirect que a spec manda evitar. Então vira tela.
    """
    extra = f"<p class='rodape'>{escape(detalhe)}</p>" if detalhe else ""
    return _pagina(titulo, f"""
      <h1>{escape(titulo)}</h1>
      <p class='erro'>{escape(explicacao)}</p>
      {extra}
    """)
