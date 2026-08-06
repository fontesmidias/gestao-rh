"""v2.68 (§ 16.1) — o remetente de recrutamento no Microsoft 365.

Cobre os cenários 39–41 do § 16.5 de
`docs/planejamento/12-modulo-de-entrevistas.md`:

| # | Cenário | Esperado |
|---|---|---|
| 39 | remetente preenchido, `Send As` NÃO liberado | reenvia da caixa conectada, **avisa**, e o e-mail SAI |
| 40 | remetente vazio | cai no `smtp_from`, em silêncio e por desenho |
| 41 | provedor sem suporte a remetente alternativo | usa a caixa conectada; o `ORGANIZER` do `.ics` respeita a chave |

**Duas regras de teste que esta leva não pode esquecer:**

1. **A referência é CONSTANTE conhecida do teste**, nunca valor lido do próprio
   sistema (armadilha da v2.64: comparar a resposta com ela mesma passa com o
   defeito presente).
2. **Exercita o caminho REAL**, não a função interna. O teste do `.ics` na
   v2.67 chamava `_anexo_ics` diretamente — provava que a função funciona, não
   que a ROTA a usa. Aqui o ponto de entrada é `enviar_convite`, o mesmo que a
   rota chama, e o que se substitui é o **limite HTTP** (`httpx.post`), que é
   de fato externo ao sistema.

Cada bloco anota a MUTAÇÃO que o reprova. Teste que passa com o defeito
presente não é teste.

Precisa dos containers de teste:
  docker run -d --name pg-teste ... postgres:16-alpine
  docker run -d --name minio-teste ... quay.io/minio/minio server /data

Rode: PYTHONPATH=. .venv/Scripts/python.exe tests/test_remetente_recrutamento.py
"""

import os
import uuid
from datetime import datetime, timedelta, timezone

os.environ.setdefault(
    "DATABASE_URL", "postgresql+psycopg://admissao:admissao@localhost:55432/admissao")
os.environ.setdefault("MINIO_ENDPOINT", "localhost:59000")
os.environ.setdefault("MINIO_ACCESS_KEY", "minio")
os.environ.setdefault("MINIO_SECRET_KEY", "minio12345")
os.environ.setdefault("MINIO_SECURE", "false")
os.environ.setdefault("RH_ADMIN_EMAIL", "rh@greenhousedf.com.br")
os.environ.setdefault("RH_ADMIN_PASSWORD", "senha-teste-123")
os.environ.setdefault("SECRET_KEY", "segredo-de-teste")
os.environ.setdefault("BASE_URL", "http://localhost:8090")

from fastapi.testclient import TestClient  # noqa: E402

from app.core.db import SessionLocal  # noqa: E402
from app.main import app  # noqa: E402
from app.models.configuracao import Configuracao  # noqa: E402
from app.models.entrevista import Entrevista  # noqa: E402
from app.services import email as svc_email  # noqa: E402
from app.services import entrevista_convite as conv  # noqa: E402
from app.services import m365  # noqa: E402
from app.services.config_dinamica import gravar_config  # noqa: E402

c = TestClient(app)

r = c.post("/api/rh/auth/login", json={"email": "rh@greenhousedf.com.br",
                                       "senha": "senha-teste-123"})
assert r.status_code == 200, f"login falhou: {r.status_code} {r.text}"
RH = {"Authorization": f"Bearer {r.json()['token']}"}

SUF = uuid.uuid4().hex[:8]

# CONSTANTES do teste — as referências. Nunca lidas do sistema.
REMETENTE = "recrutamento-teste@exemplo-greenhouse.com"
CONTA_CONECTADA = "login-conectado@exemplo-greenhouse.com"
# A resposta REAL do Graph quando falta `Send As` (é este texto que o código
# tem que reconhecer como permissão, e não como falha de envio).
CORPO_SEND_AS_NEGADO = (
    '{"error":{"code":"ErrorSendAsDenied","message":"The user account which was '
    'used to submit this request does not have the right to send mail on behalf '
    'of the specified sending account."}}')

falhas = []


def checar(cond, msg):
    if cond:
        print(f"  ok   {msg}")
    else:
        print(f"  FALHOU  {msg}")
        falhas.append(msg)


# ---------------------------------------------------------------------------
# O Graph de mentira: substitui o LIMITE HTTP, não as funções do sistema.
# Guarda cada tentativa para o teste poder afirmar quantas houve e com qual
# `from` — é isso que separa "reenviou" de "desistiu".
# ---------------------------------------------------------------------------
class GraphFalso:
    def __init__(self, *, nega_send_as=False, status_erro=None, corpo_erro=""):
        self.nega_send_as = nega_send_as
        self.status_erro = status_erro
        self.corpo_erro = corpo_erro
        self.tentativas = []   # o `from` de cada POST (None = caixa conectada)

    def post(self, url, **kw):
        if "sendMail" not in url:            # é a renovação do token
            return RespostaFalsa(200, '{"access_token":"tok-de-teste"}')
        msg = (kw.get("json") or {}).get("message", {})
        de = (msg.get("from") or {}).get("emailAddress", {}).get("address")
        self.tentativas.append(de)
        if self.status_erro is not None:
            return RespostaFalsa(self.status_erro, self.corpo_erro)
        if self.nega_send_as and de:
            return RespostaFalsa(403, CORPO_SEND_AS_NEGADO)
        return RespostaFalsa(202, "")


class RespostaFalsa:
    def __init__(self, status_code, text):
        self.status_code, self.text = status_code, text

    def json(self):
        import json
        return json.loads(self.text or "{}")

    def raise_for_status(self):
        pass


def com_graph(graph, fn):
    """Roda `fn` com o Graph de mentira no lugar do httpx do módulo m365."""
    original = m365.httpx.post
    m365.httpx.post = graph.post
    try:
        return fn()
    finally:
        m365.httpx.post = original


def ligar_m365():
    with SessionLocal() as db:
        gravar_config(db, {"m365_refresh_token": "refresh-de-teste",
                           "m365_conta": CONTA_CONECTADA,
                           "m365_client_id": "cid", "m365_tenant_id": "tid",
                           "m365_client_secret": "seg"})
        db.commit()


def desligar_m365():
    with SessionLocal() as db:
        for chave in ("m365_refresh_token", "m365_conta", "m365_client_id",
                      "m365_tenant_id", "m365_client_secret"):
            reg = db.get(Configuracao, chave)
            if reg is not None:
                db.delete(reg)
        db.commit()


def definir_remetente(valor):
    with SessionLocal() as db:
        if valor is None:
            reg = db.get(Configuracao, "email_recrutamento")
            if reg is not None:
                db.delete(reg)
        else:
            gravar_config(db, {"email_recrutamento": valor})
        db.commit()


def entrevista_marcada():
    """Uma entrevista MARCADA, com data futura — a que gera convite."""
    r = c.post("/api/talentos", json={
        "nome": "Pessoa Do Convite",
        "email": f"convite-{SUF}-{uuid.uuid4().hex[:6]}@exemplo.com",
        "telefone": "61999990000", "cargos_interesse": ["Vigia"],
        "consentimento_lgpd": True})
    assert r.status_code in (200, 201), f"criar talento: {r.status_code} {r.text}"
    tid = r.json()["id"]
    quando = (datetime.now(timezone.utc) + timedelta(days=3)).isoformat()
    r = c.post("/api/rh/entrevistas", headers=RH, json={
        "talento_id": tid, "tipo": "entrevista", "marcada_para": quando,
        "modalidade": "online", "link_reuniao": "https://exemplo.com/sala"})
    assert r.status_code in (200, 201), f"criar entrevista: {r.status_code} {r.text}"
    return r.json()["id"]


ESTADO_ANTERIOR = {}
with SessionLocal() as db:
    for chave in ("m365_refresh_token", "m365_conta", "m365_client_id",
                  "m365_tenant_id", "m365_client_secret", "email_recrutamento"):
        reg = db.get(Configuracao, chave)
        ESTADO_ANTERIOR[chave] = reg.valor if reg is not None else None


try:
    # ======================================================================
    print("\n1. Cenário 39 — `Send As` NÃO liberado: reenvia, avisa, e o e-mail SAI")
    # ======================================================================
    # MUTAÇÃO que reprova: em `m365.enviar_via_graph`, trocar o bloco do reenvio
    # por `return {"ok": False, "aviso": None}` (fazer a recusa ABORTAR o
    # envio) -> `enviado` vira False e as duas asserções abaixo falham.
    ligar_m365()
    definir_remetente(REMETENTE)
    eid = entrevista_marcada()

    graph = GraphFalso(nega_send_as=True)
    with SessionLocal() as db:
        e = db.get(Entrevista, uuid.UUID(eid))
        r39 = com_graph(graph, lambda: conv.enviar_convite(
            db, e, "Pessoa Do Convite", "pessoa@exemplo.com"))

    checar(r39["enviado"] is True,
           f"o e-mail SAIU mesmo com o Send As negado (enviado={r39['enviado']!r})")
    checar(len(graph.tentativas) == 2,
           f"houve REENVIO: 2 tentativas ao Graph (houve {len(graph.tentativas)})")
    checar(graph.tentativas[:1] == [REMETENTE],
           f"a 1ª tentativa usou o remetente de recrutamento ({graph.tentativas[:1]})")
    checar(graph.tentativas[1:] == [None],
           f"a 2ª saiu da CAIXA CONECTADA, sem `from` ({graph.tentativas[1:]})")
    aviso39 = r39.get("aviso") or ""
    checar(bool(aviso39), "o convite volta COM aviso — não sai calado")
    # O aviso tem que dizer o que RESOLVE (lição da v2.17/v2.18). A referência é
    # a constante do teste, não o texto lido do sistema.
    checar("Send As" in aviso39 or "Enviar como" in aviso39,
           f"o aviso NOMEIA a permissão que falta ({aviso39[:70]!r})")
    checar(REMETENTE in aviso39,
           "o aviso diz de QUAL endereço se trata")

    # ======================================================================
    print("\n2. Cenário 40 — remetente vazio: caixa conectada, em silêncio")
    # ======================================================================
    # MUTAÇÃO: fazer `enviar_via_graph` avisar mesmo sem `remetente` pedido
    # (tirar o `if pedido and ...`) -> o aviso apareceria e este bloco falha.
    definir_remetente(None)
    eid40 = entrevista_marcada()
    graph40 = GraphFalso(nega_send_as=True)   # negaria, se houvesse o que negar
    with SessionLocal() as db:
        e = db.get(Entrevista, uuid.UUID(eid40))
        r40 = com_graph(graph40, lambda: conv.enviar_convite(
            db, e, "Pessoa Do Convite", "pessoa@exemplo.com"))

    checar(r40["enviado"] is True, "com a chave vazia o convite sai normalmente")
    checar(r40.get("aviso") is None,
           f"e SEM aviso — não há nada a configurar (aviso={r40.get('aviso')!r})")
    checar(len(graph40.tentativas) == 1,
           f"uma tentativa só, sem reenvio ({len(graph40.tentativas)})")
    # A chave vazia CAI no smtp_from. Aqui a referência não pode ser o
    # `smtp_from` lido do sistema (seria comparar a resposta com ela mesma):
    # o que se afirma é que NÃO foi pedido `from` de terceiro ao Graph.
    checar(graph40.tentativas == [None],
           "nenhum `from` de terceiro foi pedido ao Graph")

    # A distinção que custou uma reprovação nesta leva: `email_recrutamento`
    # CAI no smtp_from (certo para o ORGANIZER do .ics) e
    # `email_recrutamento_escolhido` NÃO (certo para o `From` do Graph). Com a
    # chave vazia, usar a primeira para o `From` pediria ao Graph permissão
    # para enviar como a própria caixa — e avisaria sobre uma configuração que
    # ninguém fez. MUTAÇÃO: em `enviar_convite`, trocar `_escolhido` de volta
    # por `email_recrutamento` -> os três blocos acima falham.
    from app.services.config_dinamica import (  # noqa: E402
        email_recrutamento, email_recrutamento_escolhido)
    with SessionLocal() as db:
        checar(email_recrutamento_escolhido(db) == "",
               f"com a chave vazia, `_escolhido` é vazio "
               f"({email_recrutamento_escolhido(db)!r})")
        checar(bool(email_recrutamento(db)),
               "e o fallback do .ics continua devolvendo um endereço")

    # ======================================================================
    print("\n3. Erro de envio COMUM não é tratado como falta de `Send As`")
    # ======================================================================
    # É a regra da v2.00: erro de permissão (permanente) ≠ erro de envio
    # (transitório). MUTAÇÃO: fazer `recusou_por_permissao` devolver True para
    # qualquer status -> haveria reenvio e aviso, e as três asserções falham.
    definir_remetente(REMETENTE)
    eid41 = entrevista_marcada()
    graph500 = GraphFalso(status_erro=500, corpo_erro='{"error":{"code":"InternalServerError"}}')
    with SessionLocal() as db:
        e = db.get(Entrevista, uuid.UUID(eid41))
        r500 = com_graph(graph500, lambda: conv.enviar_convite(
            db, e, "Pessoa Do Convite", "pessoa@exemplo.com"))

    checar(r500["enviado"] is False, "falha de envio comum é FALHA, não sucesso")
    checar(r500.get("aviso") is None,
           f"e NÃO vira aviso de Send As ({r500.get('aviso')!r})")
    checar(len(graph500.tentativas) == 1,
           f"não houve reenvio às cegas ({len(graph500.tentativas)} tentativa(s))")
    checar(r500.get("motivo"),
           "a tela recebe o motivo da falha, não silêncio")

    # O classificador, nos limites que importam.
    checar(m365.recusou_por_permissao(403, CORPO_SEND_AS_NEGADO) is True,
           "403 + ErrorSendAsDenied é recusa de PERMISSÃO")
    checar(m365.recusou_por_permissao(500, CORPO_SEND_AS_NEGADO) is False,
           "500 NÃO é recusa de permissão, mesmo com o texto parecido")
    checar(m365.recusou_por_permissao(0, "timeout") is False,
           "erro de rede (status 0) NÃO é recusa de permissão")
    checar(m365.recusou_por_permissao(403, '{"error":{"code":"ErrorQuotaExceeded"}}') is False,
           "403 por outro motivo não vira aviso de Send As")

    # ======================================================================
    print("\n4. Cenário 41 — sem M365, o ORGANIZER do .ics respeita a chave")
    # ======================================================================
    # MUTAÇÃO: voltar `organizador_email` para o `smtp_from` do settings -> o
    # endereço abaixo não aparece no arquivo.
    desligar_m365()
    definir_remetente(REMETENTE)
    eid_ics = entrevista_marcada()
    with SessionLocal() as db:
        e = db.get(Entrevista, uuid.UUID(eid_ics))
        anexos = conv._anexo_ics(db, e, "pessoa@exemplo.com", False)
    ics = anexos[0][1].decode() if anexos else ""
    checar(REMETENTE in ics,
           "o ORGANIZER do .ics usa o remetente de recrutamento")
    checar(anexos and anexos[0][0].endswith(".ics"),
           f"o anexo é um .ics ({anexos[0][0] if anexos else '(nenhum)'})")

    # O anexo do convite não pode sair como `application/pdf` no Graph — era o
    # defeito da v2.41 sobrevivendo neste caminho: com o tipo errado, o Outlook
    # mostra um anexo em vez de oferecer "adicionar à agenda".
    #
    # ⚠️ Este bloco JÁ FOI REPROVADO uma vez nesta leva: a 1ª versão afirmava
    # `m365._tipo_grafo("convite.ics") == "text/calendar"`, e a mutação que
    # chumba `application/pdf` na MENSAGEM passava verde — a função estava
    # certa, e nada provava que a mensagem a usava. É a mesma lição do teste do
    # `.ics` na v2.67. Agora a asserção lê o `contentType` da mensagem REAL que
    # `enviar_via_graph` monta e entrega ao limite HTTP.
    # MUTAÇÃO: voltar `"contentType": "application/pdf"` chumbado -> falha.
    class GraphEspiao(GraphFalso):
        """Guarda a MENSAGEM inteira, para o teste ler o que foi montado."""
        def __init__(self):
            super().__init__()
            self.mensagens = []

        def post(self, url, **kw):
            if "sendMail" in url:
                self.mensagens.append((kw.get("json") or {}).get("message", {}))
            return super().post(url, **kw)

    ligar_m365()
    espiao = GraphEspiao()
    with SessionLocal() as db:
        e = db.get(Entrevista, uuid.UUID(eid_ics))
        com_graph(espiao, lambda: conv.enviar_convite(
            db, e, "Pessoa Do Convite", "pessoa@exemplo.com"))
    anexos_graph = espiao.mensagens[0].get("attachments", []) if espiao.mensagens else []
    tipos = {a.get("name", ""): a.get("contentType") for a in anexos_graph}
    ics_no_graph = [t for n, t in tipos.items() if n.endswith(".ics")]
    checar(ics_no_graph == ["text/calendar"],
           f"na MENSAGEM entregue ao Graph, o .ics sai como text/calendar "
           f"(saiu {ics_no_graph})")
    desligar_m365()

    # E o PDF continua saindo como PDF — o conserto não pode ter trocado o tipo
    # dos anexos que já estavam certos.
    checar(m365._tipo_grafo("ficha.pdf") == "application/pdf",
           f"o PDF continua application/pdf ({m365._tipo_grafo('ficha.pdf')!r})")

    # ======================================================================
    print("\n5. A rota de Configurações — o campo existe e se apaga")
    # ======================================================================
    # Antes da v2.68 a chave `email_recrutamento` NÃO tinha rota nem tela: só
    # dava para preenchê-la escrevendo direto no banco.
    r = c.get("/api/rh/config/recrutamento", headers=RH)
    checar(r.status_code == 200, f"GET da configuração responde ({r.status_code})")
    checar(r.json().get("email_recrutamento") == REMETENTE,
           f"e devolve o que está gravado ({r.json().get('email_recrutamento')!r})")

    r = c.put("/api/rh/config/recrutamento", headers=RH,
              json={"email_recrutamento": "  outro@exemplo-teste.com  "})
    checar(r.status_code == 200 and r.json()["email_recrutamento"] == "outro@exemplo-teste.com",
           f"PUT grava e APARA espaços ({r.status_code}, {r.json().get('email_recrutamento')!r})")

    r = c.put("/api/rh/config/recrutamento", headers=RH,
              json={"email_recrutamento": "isto-nao-e-email"})
    checar(r.status_code == 422, f"endereço sem @ é recusado com 422 ({r.status_code})")

    # Vazio é um valor VÁLIDO — é como se volta ao padrão. `EmailStr` recusaria
    # e deixaria o RH sem como desfazer.
    r = c.put("/api/rh/config/recrutamento", headers=RH, json={"email_recrutamento": ""})
    checar(r.status_code == 200 and r.json()["email_recrutamento"] == "",
           f"vazio é aceito e limpa a configuração ({r.status_code})")

    # A tela precisa saber se o aviso do `Send As` se aplica.
    ligar_m365()
    r = c.get("/api/rh/config/recrutamento", headers=RH)
    checar(r.json().get("depende_de_send_as") is True,
           "com M365 conectado, a tela sabe que o Send As é exigido")
    checar(r.json().get("conta_conectada") == CONTA_CONECTADA,
           f"e sabe qual conta nomear ({r.json().get('conta_conectada')!r})")
    desligar_m365()
    r = c.get("/api/rh/config/recrutamento", headers=RH)
    checar(r.json().get("depende_de_send_as") is False,
           "sem M365, não promete uma exigência que não existe")

    # ======================================================================
    print("\n6. `enviar_com_aviso` não mudou o contrato de `enviar_email`")
    # ======================================================================
    # Os ~40 call-sites do projeto continuam recebendo booleano. MUTAÇÃO:
    # fazer `enviar_email` devolver dict -> todo o resto do sistema quebra.
    saida = svc_email.enviar_email("", "assunto", "corpo")
    checar(saida is False,
           f"`enviar_email` continua devolvendo booleano ({saida!r})")
    saida2 = svc_email.enviar_com_aviso("", "assunto", "corpo")
    checar(isinstance(saida2, dict) and saida2 == {"ok": False, "aviso": None},
           f"`enviar_com_aviso` devolve {{ok, aviso}} ({saida2!r})")

    # ======================================================================
    print("\n7. A tela NÃO duplica o texto do aviso (vem do servidor)")
    # ======================================================================
    # Mesma regra do instrumento da entrevista: texto duplicado no JSX passa a
    # divergir do servidor na primeira revisão dele.
    raiz = os.path.join(os.path.dirname(__file__), "..", "..", "frontend", "src")
    achados = []
    for pasta, _, arquivos in os.walk(raiz):
        for nome in arquivos:
            if not nome.endswith(".jsx"):
                continue
            with open(os.path.join(pasta, nome), encoding="utf-8") as fh:
                conteudo = fh.read()
            if "O e-mail saiu, mas do endereço de sempre" in conteudo:
                achados.append(nome)
    checar(not achados,
           f"o texto do aviso mora só no servidor (achado em: {achados})")

finally:
    # Devolve a configuração ao estado anterior — teste não deixa estrago.
    with SessionLocal() as db:
        for chave, valor in ESTADO_ANTERIOR.items():
            reg = db.get(Configuracao, chave)
            if valor is None:
                if reg is not None:
                    db.delete(reg)
            else:
                gravar_config(db, {chave: valor})
        db.commit()


print(f"\ntest_remetente_recrutamento: {len(falhas)} FALHA(S)"
      if falhas else "\ntest_remetente_recrutamento: OK")
for f in falhas:
    print(f"  - {f}")
raise SystemExit(1 if falhas else 0)
