"""Logs que permitem investigar de verdade (v2.41).

Feedback do Bruno em 2026-08-01: *"achei muito bom o layout, apenas pobre de
tipos de informações que são registradas nos logs, acho que poderiam ser muito
mais informações, para que pudesse possibilitar investigações verdadeiras
mesmo"*. E, sobre o e-mail: *"o txt que vai para o email não abre de jeito
nenhum, acho que é um arquivo corrompido"*.

O que faltava não era volume — era **ligar uma linha à outra**. O log dizia
"POST /api/c/ab12*** status=200" e, três linhas abaixo, um erro de storage:
nada dizia que eram a mesma pessoa, na mesma ação. Com dez pessoas usando ao
mesmo tempo, investigar virava adivinhação com carimbo de hora.

O que este teste protege:

1. **`req=` e `ator=` em toda linha**, injetados por filtro — nenhum call-site
   precisa lembrar de passá-los, e é isso que garante que não haja buraco
   justamente onde o defeito aparece.
2. **O contexto NUNCA derruba o que estava logando** (mesma regra do
   `avisar()`).
3. **Uma linha por e-mail enviado**, com desfecho — "o e-mail saiu?" é a
   pergunta mais frequente de qualquer incidente daqui.
4. **O anexo declara o tipo certo**: o `.txt` do log ia como `application/pdf`
   e chegava "corrompido"; o arquivo estava perfeito, o envelope é que mentia.
5. **Busca com vários termos** exige TODOS na linha — é o que permite cruzar
   "creche" com "ERROR".

Rode: PYTHONPATH=. .venv/Scripts/python.exe tests/test_logs_investigacao.py
"""

import logging
import os
import tempfile
import uuid
from pathlib import Path

os.environ.setdefault(
    "DATABASE_URL", "postgresql+psycopg://admissao:admissao@localhost:55432/admissao")
os.environ.setdefault("SECRET_KEY", "segredo-de-teste")
# Log em diretório próprio: o teste escreve de verdade e lê de volta.
_TMP = Path(tempfile.mkdtemp(prefix="logs-teste-"))
os.environ["LOG_DIR"] = str(_TMP)

from app.services import contexto_log as ctx  # noqa: E402
from app.services import logs as svc  # noqa: E402
from app.services.email import _tipo_do_anexo  # noqa: E402

FALHAS = []


def checar(condicao, descricao):
    print(("  ok   " if condicao else "  FALHA ") + descricao)
    if not condicao:
        FALHAS.append(descricao)


# ================================== 1. contexto em toda linha, sem call-site
print("\n[req e ator em toda linha]")
svc.configurar("teste")
log = logging.getLogger("app.qualquer.servico")

marca = uuid.uuid4().hex[:8]
rid = ctx.definir(ator="rh@exemplo.com")
log.warning("aconteceu alguma coisa %s", marca)
ctx.definir_ator("candidato:Maria")
log.error("erro depois %s", marca)

for h in logging.getLogger().handlers:
    h.flush()

lido = svc.ler("teste", busca=marca, limite=50)
linhas = lido["linhas"]
checar(len(linhas) == 2, f"as duas linhas foram escritas no arquivo ({len(linhas)})")
checar(all(f"req={rid}" in l for l in linhas),
       "as duas carregam o MESMO req — é o que liga o erro ao que veio antes")
checar("ator=rh@exemplo.com" in linhas[0], "a primeira sai com o usuário do RH")
checar("ator=candidato:Maria" in linhas[1],
       "a segunda sai com o candidato — a identidade acompanha a requisição "
       "mesmo mudando no meio dela")
checar("app.qualquer.servico" in linhas[0],
       "um serviço qualquer no fundo da pilha ganha contexto sem mudar uma "
       "linha do próprio código")

# Fora de requisição (worker, cron) não pode quebrar nem poluir.
ctx._REQUISICAO.set("")
ctx._ATOR.set("")
log.info("worker rodando %s", marca)
for h in logging.getLogger().handlers:
    h.flush()
sem_ctx = [l for l in svc.ler("teste", busca=f"worker rodando {marca}")["linhas"]]
checar(sem_ctx and "req=-" in sem_ctx[0] and "ator=-" in sem_ctx[0],
       "sem requisição, sai traço — nunca vazio nem erro de formatação")

# =========================== 1b. hora de Brasília e nível que deixa passar
print("\n[hora de Brasília e nível]")
import re as _re  # noqa: E402
from datetime import datetime as _dt  # noqa: E402

from app.services.logs import TZ_BRASILIA  # noqa: E402

amostra = linhas[0]
m = _re.match(r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) ([-+]\d{4})", amostra)
checar(m is not None, f"a linha começa com data, hora e fuso explícitos: {amostra[:40]!r}")
if m:
    esperado = _dt.now(TZ_BRASILIA)
    hora_log = _dt.strptime(m.group(1), "%Y-%m-%d %H:%M:%S")
    checar(abs((esperado.replace(tzinfo=None) - hora_log).total_seconds()) < 120,
           f"a hora é a de BRASÍLIA, não a do container em UTC "
           f"(log: {m.group(1)}, agora: {esperado:%Y-%m-%d %H:%M:%S})")
    checar(m.group(2) in ("-0300", "-0200"),
           f"e o deslocamento vai escrito ({m.group(2)}) — o arquivo é baixado "
           "e enviado por e-mail, e sem ele ninguém sabe se já foi convertido")

# O nível: os WORKERS não importam o main.py, então sem isto tudo que eles
# registram com log.info ("X arquivos expurgados") nunca chegava ao arquivo.
checar(logging.getLogger().level <= logging.INFO,
       "configurar() garante INFO — o nível vinha do basicConfig do main.py, "
       "que worker nenhum importa")
info_tag = uuid.uuid4().hex[:8]
logging.getLogger("app.worker.qualquer").info("resumo da rodada %s", info_tag)
for h in logging.getLogger().handlers:
    h.flush()
checar(len(svc.ler("teste", busca=info_tag)["linhas"]) == 1,
       "linha de INFO de um worker chega ao arquivo")

# ============================================ 2. o log nunca derruba a ação
print("\n[o log não pode derrubar o que estava documentando]")


class Explosivo:
    def __str__(self):
        raise RuntimeError("objeto que estoura ao virar texto")


filtro = ctx.FiltroContexto()
registro = logging.LogRecord("x", logging.INFO, "f", 1, "m", None, None)
checar(filtro.filter(registro) is True, "o filtro deixa a linha passar")
checar(hasattr(registro, "req") and hasattr(registro, "ator"),
       "e sempre preenche os dois campos, senão o formatador quebraria")

try:
    ctx.definir(ator=None)
    ok_none = True
except Exception:
    ok_none = False
checar(ok_none, "definir sem ator não levanta")
checar(ctx.mascarar("x" * 500).__len__() == 60,
       "texto gigante é cortado — log não é depósito de campo livre")
checar(ctx.mascarar(None) == "", "nulo vira vazio, não 'None'")

# ============================================== 3. e-mail: saiu ou não saiu
print("\n[uma linha por e-mail enviado]")
ctx.definir(ator="rh@exemplo.com")
alvo = uuid.uuid4().hex[:8]
from app.services.email import enviar_email  # noqa: E402

# Sem destinatário: o caminho mais curto, e o que mais engana (o sistema
# "enviou" sem enviar).
enviar_email("", f"assunto {alvo}", "corpo")
for h in logging.getLogger().handlers:
    h.flush()
linhas_email = svc.ler("teste", busca=alvo, limite=20)["linhas"]
checar(any("email.envio" in l for l in linhas_email),
       "o envio aparece no canal email.envio, que é o filtro da tela")
checar(any("FALHOU" in l for l in linhas_email),
       "e-mail que NÃO saiu é registrado como falha — era isto que faltava "
       "quando os códigos do creche não chegavam")
checar(any(f"req=" in l for l in linhas_email),
       "com o req da requisição que tentou enviar")

# ================================= 4. anexo com o tipo certo (o bug relatado)
print("\n[o anexo declara o que ele é]")
checar(_tipo_do_anexo("api.txt") == ("text", "plain"),
       "log .txt vai como texto — como application/pdf, chegava 'corrompido'")
checar(_tipo_do_anexo("resumo.md") == ("text", "markdown"),
       "o resumo .md também (nem todo sistema conhece a extensão)")
checar(_tipo_do_anexo("dossie.pdf") == ("application", "pdf"),
       "PDF continua PDF — a correção não pode quebrar o que funcionava")
checar(_tipo_do_anexo("planilha.xlsx")[0] == "application",
       "planilha sai como application/...")
checar(_tipo_do_anexo("sem-extensao") == ("application", "octet-stream"),
       "sem extensão, o genérico — nunca um tipo inventado")

# ========================================== 5. busca com vários termos
print("\n[busca que cruza perguntas]")
tag = uuid.uuid4().hex[:8]
log.error("creche %s deu ruim", tag)
log.info("creche %s tudo certo", tag)
for h in logging.getLogger().handlers:
    h.flush()
checar(len(svc.ler("teste", busca=f"creche {tag}")["linhas"]) == 2,
       "dois termos: acha as duas linhas que têm ambos")
um_so = svc.ler("teste", busca=f"{tag} ruim")["linhas"]
checar(len(um_so) == 1 and "deu ruim" in um_so[0],
       "termos adicionais estreitam o resultado, em vez de virar frase literal")
checar(svc.ler("teste", busca=f"{tag} inexistente")["linhas"] == [],
       "termo que não aparece elimina a linha (é E, não OU)")

print()
if FALHAS:
    print(f"test_logs_investigacao: {len(FALHAS)} FALHA(S)")
    for f in FALHAS:
        print(f"  - {f}")
    raise SystemExit(1)
print("test_logs_investigacao: OK")
