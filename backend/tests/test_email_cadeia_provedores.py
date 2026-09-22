"""A cadeia de provedores não para numa CREDENCIAL MORTA.

Incidente de campo em 2026-09-22, o mais grave da família: a caixa que
autenticava o Microsoft 365 (`bruno.fontes@…`) foi **extinta**. O
`m365_refresh_token` continuou no banco, agora inútil, e o `_enviar_email`
fazia:

    if config_m365(db).get("m365_refresh_token"):
        ...
        return False          # ← parava AQUI

Ou seja: Google, webhook e SMTP **nunca eram tentados**, mesmo configurados.
O sistema inteiro ficou sem e-mail — e e-mail neste sistema é o que entrega
**código de acesso**: sem ele ninguém entra no creche nem no portal, e nenhum
candidato recebe o link da admissão.

**Credencial inválida é pior que credencial nenhuma.** Sem nada configurado o
sistema cairia no SMTP; com o token morto ele parava antes. É o mesmo mecanismo
do `docker login` expirado, que faz o registry negar uma imagem PÚBLICA que
qualquer um puxaria anonimamente — o defeito vizinho, no mesmo dia.

O que este teste protege:

1. **M365 morto cai para o próximo provedor** — a mutação que restaura o
   `return False` reprova.
2. **A queda AVISA na tela** — silêncio faria o sistema parecer saudável
   enquanto o provedor principal está morto, até ele ser a única opção em
   algum outro fluxo (é o "worker que não roda" da v2.66).
3. **O aviso de `Send As` tem precedência** — ele é mais específico, e
   sobrescrevê-lo mandaria o RH mexer no lugar errado (v2.68).
4. **A mensagem de erro NOMEIA o que falhou antes** — "smtp_nao_configurado"
   sozinho manda configurar SMTP quando o defeito real é a conta do M365
   extinta, que é onde está a correção (v2.93: recusa que aponta o lugar
   errado).

Sem rede: os provedores são substituídos no LIMITE EXTERNO (as funções que
falam com o mundo), nunca as nossas próprias — substituir a nossa lógica
testaria a substituição, não o código (v2.68).

Rode: PYTHONPATH=. .venv/Scripts/python.exe tests/test_email_cadeia_provedores.py
"""

import os

os.environ.setdefault(
    "DATABASE_URL", "postgresql+psycopg://admissao:admissao@localhost:55432/admissao")
os.environ.setdefault("MINIO_ENDPOINT", "localhost:59000")
os.environ.setdefault("MINIO_ACCESS_KEY", "minio")
os.environ.setdefault("MINIO_SECRET_KEY", "minio12345")
os.environ.setdefault("MINIO_SECURE", "false")
os.environ.setdefault("SECRET_KEY", "segredo-de-teste")
os.environ.setdefault("BASE_URL", "http://localhost:8090")

from app.services import email as mod  # noqa: E402

FALHAS = []


def _reportar(texto):
    """Emoji em mensagem de falha quebra o teste no console do Windows (v3.15)."""
    try:
        print(texto)
    except UnicodeEncodeError:
        print(texto.encode("ascii", "replace").decode("ascii"))


def checar(condicao, descricao):
    _reportar(("  ok   " if condicao else "  FALHA ") + descricao)
    if not condicao:
        FALHAS.append(descricao)


class _Cenario:
    """Substitui os LIMITES EXTERNOS do `_enviar_email`.

    `m365`/`gmail`/`webhook`/`smtp` dizem se cada provedor está CONFIGURADO;
    `entrega` diz quais deles conseguem ENTREGAR. A distinção é o coração do
    defeito: o M365 estava configurado e não entregava.
    """

    def __init__(self, *, m365=False, gmail=False, webhook=False, smtp=False,
                 entrega=(), aviso_graph=None):
        self.cfg = {"m365": m365, "gmail": gmail, "webhook": webhook, "smtp": smtp}
        self.entrega = set(entrega)
        self.aviso_graph = aviso_graph
        self.chamados = []

    def instalar(self):
        import app.services.gmail as g
        import app.services.m365 as m
        import app.services.webhook_email as w
        from app.services import config_dinamica as cd

        self._orig = (m.config_m365, m.enviar_via_graph, g.config_gmail,
                      g.enviar_via_gmail, w.url_webhook, w.enviar_via_webhook,
                      cd.smtp_config, mod.smtplib.SMTP)

        m.config_m365 = lambda db: ({"m365_refresh_token": "tok"} if self.cfg["m365"] else {})
        g.config_gmail = lambda db: ({"gmail_refresh_token": "tok"} if self.cfg["gmail"] else {})
        w.url_webhook = lambda db: ("http://exemplo" if self.cfg["webhook"] else "")
        cd.smtp_config = lambda db: (
            {"host": "smtp.exemplo.com", "port": 587, "user": "", "password": "",
             "from_": "sistema@exemplo.com"} if self.cfg["smtp"]
            else {"host": "", "port": 587, "user": "", "password": "", "from_": ""})

        def _graph(db, *a, **k):
            self.chamados.append("m365")
            return {"ok": "m365" in self.entrega, "aviso": self.aviso_graph}

        def _gmail(db, *a, **k):
            self.chamados.append("gmail")
            return "gmail" in self.entrega

        def _webhook(db, *a, **k):
            self.chamados.append("webhook")
            return "webhook" in self.entrega

        m.enviar_via_graph, g.enviar_via_gmail, w.enviar_via_webhook = _graph, _gmail, _webhook

        cenario = self

        class _SMTP:  # substitui o smtplib inteiro: nada sai para a rede
            def __init__(self, *a, **k):
                cenario.chamados.append("smtp")
                if "smtp" not in cenario.entrega:
                    raise OSError("conexão recusada (simulado)")

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def starttls(self): pass
            def login(self, *a): pass
            def send_message(self, *a): pass

        mod.smtplib.SMTP = _SMTP
        return self

    def restaurar(self):
        import app.services.gmail as g
        import app.services.m365 as m
        import app.services.webhook_email as w
        from app.services import config_dinamica as cd
        (m.config_m365, m.enviar_via_graph, g.config_gmail, g.enviar_via_gmail,
         w.url_webhook, w.enviar_via_webhook, cd.smtp_config, mod.smtplib.SMTP) = self._orig


def enviar(cenario, aviso=None):
    c = cenario.instalar()
    try:
        return mod._enviar_email("alguem@exemplo.com", "Assunto", "corpo", _aviso=aviso)
    finally:
        c.restaurar()


print("\n=== 1. o DEFEITO do incidente: M365 configurado mas MORTO ===")
c = _Cenario(m365=True, smtp=True, entrega=["smtp"])
ok = enviar(c)
checar(ok, "o e-mail SAI pelo SMTP mesmo com o token do M365 morto "
           "(antes: parava no M365 e ninguem recebia codigo de acesso)")
checar(c.chamados == ["m365", "smtp"],
       f"tentou M365 e depois SMTP, nessa ordem (veio {c.chamados})")

print("\n=== 2. a queda AVISA na tela ===")
c = _Cenario(m365=True, smtp=True, entrega=["smtp"])
aviso = [None]
enviar(c, aviso=aviso)
checar(aviso[0] is not None, "a tela recebe um aviso de que caiu para o reserva")
checar(aviso[0] and "Microsoft 365" in aviso[0],
       f"o aviso NOMEIA o provedor que falhou (veio {aviso[0]!r})")

print("\n=== 3. cadeia inteira: M365 e Google mortos, webhook entrega ===")
c = _Cenario(m365=True, gmail=True, webhook=True, entrega=["webhook"])
ok = enviar(c)
checar(ok and c.chamados == ["m365", "gmail", "webhook"],
       f"percorre a cadeia toda ate quem entrega (veio {c.chamados})")

print("\n=== 4. o aviso de Send As tem PRECEDENCIA (v2.68) ===")
# O Graph ENTREGOU, mas com aviso de permissão: esse aviso é mais específico
# e não pode ser sobrescrito pelo de queda de provedor.
c = _Cenario(m365=True, entrega=["m365"], aviso_graph="libere o Send As de x@y")
aviso = [None]
enviar(c, aviso=aviso)
checar(aviso[0] == "libere o Send As de x@y",
       f"o aviso de Send As sobrevive (veio {aviso[0]!r})")

print("\n=== 5. sem provedor nenhum que entregue: erro NOMEIA a causa ===")
c = _Cenario(m365=True, entrega=[])
c.instalar()
try:
    erro = ""
    try:
        mod._enviar_email("a@b.com", "x", "y", levantar_erro=True)
    except RuntimeError as exc:
        erro = str(exc)
    checar("Microsoft 365" in erro,
           f"a mensagem diz que o M365 falhou, em vez de mandar configurar SMTP "
           f"(veio {erro!r})")
finally:
    c.restaurar()

print("\n=== 6. a CIFRA depende da PORTA (incidente de 2026-09-22) ===")
# O log de produção mostrou a assinatura exata do erro: trocado o servidor, o
# `Connection refused` virou **timeout de 30s no `getreply`** — o socket abre,
# o Python espera a saudação em texto claro e o servidor espera o handshake
# TLS. Ninguém fala. `SMTP` + `starttls()` na 465 produz isso; `SMTP` sem
# `starttls()` na 587/2525 faz o servidor recusar a autenticação.
_usados: list[tuple[str, int]] = []


class _FakeSMTP:
    def __init__(self, host, port, timeout=None):
        _usados.append(("SMTP", port))

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def starttls(self):
        _usados.append(("starttls", 0))

    def login(self, *a):
        pass

    def send_message(self, *a):
        pass


class _FakeSSL(_FakeSMTP):
    def __init__(self, host, port, timeout=None):
        _usados.append(("SMTP_SSL", port))


def _cifra_na_porta(porta: int) -> list[tuple[str, int]]:
    import app.services.gmail as g
    import app.services.m365 as m
    import app.services.webhook_email as w
    from app.services import config_dinamica as cd

    orig = (mod.smtplib.SMTP, mod.smtplib.SMTP_SSL, m.config_m365,
            g.config_gmail, w.url_webhook, cd.smtp_config)
    mod.smtplib.SMTP, mod.smtplib.SMTP_SSL = _FakeSMTP, _FakeSSL
    m.config_m365 = lambda db: {}
    g.config_gmail = lambda db: {}
    w.url_webhook = lambda db: ""
    cd.smtp_config = lambda db: {"host": "mail.exemplo", "port": porta,
                                 "user": "u", "password": "s", "from_": "u"}
    _usados.clear()
    try:
        mod._enviar_email("a@b.com", "x", "y")
        return list(_usados)
    finally:
        (mod.smtplib.SMTP, mod.smtplib.SMTP_SSL, m.config_m365,
         g.config_gmail, w.url_webhook, cd.smtp_config) = orig


u465 = _cifra_na_porta(465)
checar(u465 == [("SMTP_SSL", 465)],
       f"porta 465 usa SMTP_SSL e NAO chama starttls (veio {u465}) — "
       f"`SMTP`+starttls ali da timeout de 30s no getreply, que parece rede")
for p in (587, 2525):
    u = _cifra_na_porta(p)
    checar(u == [("SMTP", p), ("starttls", 0)],
           f"porta {p} usa SMTP + STARTTLS (veio {u}) — sem ele o servidor "
           f"recusa a autenticacao")

print("\n=== 7. quem entrega de primeira NAO gera aviso (sem ruido) ===")
c = _Cenario(m365=True, entrega=["m365"])
aviso = [None]
ok = enviar(c, aviso=aviso)
checar(ok and aviso[0] is None,
       f"envio normal nao avisa nada (veio {aviso[0]!r}) — aviso sempre visivel "
       f"ensina a ignorar aviso")

print()
if FALHAS:
    _reportar(f"test_email_cadeia_provedores: {len(FALHAS)} FALHA(S)")
    for f in FALHAS:
        _reportar(f"  - {f}")
    raise SystemExit(1)
_reportar("test_email_cadeia_provedores: OK")
