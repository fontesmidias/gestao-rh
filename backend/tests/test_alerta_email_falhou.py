"""Quando o e-mail para de sair, ALGUÉM fica sabendo.

Incidente de 2026-09-22: a caixa que autenticava o Microsoft 365 foi EXTINTA.
O sistema só FALHAVA — e ninguém soube até um candidato reclamar que não
recebeu o código de acesso. A v3.22 fez a cadeia de provedores não parar numa
credencial morta; faltava a outra metade: **perceber e avisar**.

O desenho reusa o que já existe, em vez de construir vigia novo:

    enviar_email falha
      ↓ registra `email_falhou` na auditoria
      ↓
    alertas_telemetria (já roda a cada 15 min)
      ↓ conta os eventos na janela
      ↓ avisa pela matriz de avisos internos

Nenhum container novo, nenhum relógio novo. A regra nasce SEMEADA por
migration — tipo de alerta sem regra cadastrada nunca dispara, e o
esquecimento só apareceria no próximo incidente.

O que este teste protege:

1. **O limiar separa ruído de sinal** — 1 falha pode ser rede; 3 em 30 min é
   problema. Abaixo do limiar, silêncio.
2. **Destinatário VAZIO não é falha de envio** — é candidato cadastrado sem
   e-mail (convite pelo WhatsApp), caso legítimo e frequente. Contá-lo encheria
   o alerta de ruído, e ruído ensina a ignorar o alerta (v2.88).
3. **O aviso NOMEIA quem ficou sem receber** — é a pergunta que se faz no
   incidente; sem isso o alerta diz que algo quebrou e deixa quem opera sem
   por onde começar.
4. **O registro NUNCA derruba o envio** — é chamado do `finally` de todo
   e-mail; uma exceção ali derrubaria a ação que o disparou (regra do
   `avisar()`, v1.82).
5. **A assinatura é FIXA por regra** — por destinatário, cada pessoa viraria um
   alerta próprio e a enxurrada esconderia o fato único que interessa.

Rode: PYTHONPATH=. .venv/Scripts/python.exe tests/test_alerta_email_falhou.py
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

from sqlalchemy import delete, func, select  # noqa: E402

from app.core.db import SessionLocal  # noqa: E402
from app.models.alerta import RegraAlerta, TipoAlerta  # noqa: E402
from app.models.evento import EventoAuditoria  # noqa: E402
from app.services import alertas  # noqa: E402
from app.services.email import ACAO_FALHA, _registrar_falha  # noqa: E402

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


def _limpar():
    """Teste que mexe em dado compartilhado devolve o estado (v2.66)."""
    with SessionLocal() as db:
        db.execute(delete(EventoAuditoria).where(EventoAuditoria.acao == ACAO_FALHA))
        db.commit()


def _quantos() -> int:
    with SessionLocal() as db:
        return db.scalar(select(func.count()).select_from(EventoAuditoria)
                         .where(EventoAuditoria.acao == ACAO_FALHA)) or 0


def _disparos():
    # `enviar=False` é o modo PREVISÃO: não manda e-mail e não grava histórico,
    # então testar não consome o silêncio nem estraga o alerta real.
    with SessionLocal() as db:
        return [d for d in alertas.avaliar(db, enviar=False)
                if d["tipo"] == TipoAlerta.email_falhou.value]


print("\n=== 0. a regra nasce SEMEADA (senão o tipo novo nunca dispara) ===")
with SessionLocal() as db:
    regra = db.scalar(select(RegraAlerta).where(
        RegraAlerta.tipo == TipoAlerta.email_falhou.value))
checar(regra is not None,
       "existe regra `email_falhou` no banco — tipo de alerta sem regra "
       "cadastrada e codigo orfao, e o esquecimento so apareceria no proximo "
       "incidente")
if regra is not None:
    checar(regra.ativa, "a regra nasce ATIVA")
    checar(regra.limiar >= 2,
           f"o limiar e maior que 1 (veio {regra.limiar}) — uma falha isolada "
           f"pode ser rede, e avisar dela vira ruido")

_limpar()

print("\n=== 1. abaixo do limiar: SILENCIO ===")
_registrar_falha("sozinha@exemplo.com", "Codigo de acesso")
checar(len(_disparos()) == 0,
       "1 falha nao dispara — ruido ensina a ignorar o alerta (v2.88)")

print("\n=== 2. no limiar: AVISA, e diz QUEM ficou sem receber ===")
_registrar_falha("candidato2@exemplo.com", "Codigo de acesso")
_registrar_falha("candidato3@exemplo.com", "Convite de admissao")
d = _disparos()
checar(len(d) == 1, f"3 falhas em 30 min disparam (veio {len(d)})")
if d:
    texto = d[0]["itens"][0]["texto"]
    checar("candidato3@exemplo.com" in texto,
           "o aviso NOMEIA destinatario — e a pergunta do incidente: 'quem "
           "ficou sem receber?'")
    checar("Configurações" in texto or "Configuracoes" in texto,
           f"o aviso diz ONDE resolver (veio {texto[:70]!r}) — recusa sem "
           f"saida faz quem opera consertar a coisa errada (v2.93)")
    # A assinatura fixa é o que impede a enxurrada por destinatário.
    checar(len(d[0]["itens"]) == 1,
           f"UM item, nao um por pessoa (veio {len(d[0]['itens'])}) — "
           f"assinatura por destinatario faria cada pessoa virar um alerta")

    # ⚠️ Contar itens NÃO basta (pego por mutação): o avaliador devolve uma
    # lista de um em qualquer desenho, então a asserção acima passa verde com a
    # assinatura por DESTINATÁRIO. O que prova a estabilidade é a assinatura
    # não mudar quando o conjunto de destinatários muda — é ela que o
    # `silencio_min` usa, e assinatura volátil faz cada falha nova furar o
    # silêncio e virar enxurrada.
    assinatura_antes = d[0]["itens"][0]["assinatura"]
    _registrar_falha("candidato4@exemplo.com", "Outro assunto")
    d2 = _disparos()
    checar(d2 and d2[0]["itens"][0]["assinatura"] == assinatura_antes,
           f"a assinatura NAO muda quando entra outro destinatario "
           f"({assinatura_antes[:40]!r} -> "
           f"{(d2[0]['itens'][0]['assinatura'][:40] if d2 else 'sem disparo')!r}) "
           f"— assinatura volatil fura o silencio e vira enxurrada")

print("\n=== 3. destinatario VAZIO nao e falha de envio ===")
# Candidato cadastrado sem e-mail (convite copiado para o WhatsApp) é caso
# legítimo: `enviar_email` devolve False, mas nada falhou.
from app.services.email import enviar_email  # noqa: E402

antes = _quantos()
enviar_email("", "sem destinatario", "corpo")
checar(_quantos() == antes,
       f"envio sem destinatario NAO vira evento (antes={antes}, "
       f"depois={_quantos()}) — e candidato sem e-mail, nao provedor quebrado")

print("\n=== 4. registrar a falha NUNCA derruba o envio ===")
# É chamado do `finally` de todo e-mail: exceção aqui derrubaria a ação que o
# disparou — a regra do `avisar()` (v1.82).
import app.services.email as mod  # noqa: E402

_orig = mod.SessionLocal
try:
    def _explode(*a, **k):
        raise RuntimeError("banco fora do ar (simulado)")

    # O import é local dentro de `_registrar_falha`, então substitui-se na origem
    import app.core.db as dbmod
    _orig_db = dbmod.SessionLocal
    dbmod.SessionLocal = _explode
    try:
        _registrar_falha("alguem@exemplo.com", "x")
        sobreviveu = True
    except Exception:
        sobreviveu = False
    finally:
        dbmod.SessionLocal = _orig_db
    checar(sobreviveu,
           "banco fora do ar nao levanta — o envelope nao derruba a carta")
finally:
    mod.SessionLocal = _orig

_limpar()
checar(_quantos() == 0, "o teste devolveu o banco ao estado anterior")

print()
if FALHAS:
    _reportar(f"test_alerta_email_falhou: {len(FALHAS)} FALHA(S)")
    for f in FALHAS:
        _reportar(f"  - {f}")
    raise SystemExit(1)
_reportar("test_alerta_email_falhou: OK")
