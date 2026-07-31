"""Logs dos serviços em arquivo (v2.29).

Pedido do Bruno em 2026-07-30 — ler os logs no painel, sem SSH, com envio 4x ao
dia por e-mail e retenção configurável (inclusive INDETERMINADA).

O que este teste protege, em ordem de gravidade:

1. **Path traversal**: `servico` e `dia` vêm da URL. Sem validação,
   `../../etc/passwd` viraria leitura de arquivo do sistema por uma rota
   autenticada — e o painel do RH tem sessão de 12h.
2. **Retenção 0 = indeterminado NÃO apaga nada.** Se um `if dias:` virasse
   `if dias is not None:` em alguma refatoração, a escolha explícita do Bruno
   (guardar para sempre) se transformaria em "apaga tudo hoje", em silêncio.
3. **O log corrente nunca é apagado** pelo expurgo — remover o arquivo aberto
   deixaria o serviço escrevendo num descritor órfão.
4. **A janela de 6h não duplica nem pula**: o worker roda a cada 15 min, então
   sem a trava o mesmo pacote sairia 24 vezes por janela.

Não precisa de containers (usa só o sistema de arquivos e um stub de config).
Rode: PYTHONPATH=. .venv/Scripts/python.exe tests/test_logs.py
"""

import os
import tempfile
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

os.environ.setdefault("SECRET_KEY", "segredo-de-teste")
os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://x:x@localhost:1/x")

_tmp = tempfile.mkdtemp(prefix="logs-teste-")
os.environ["LOG_DIR"] = _tmp

from app.services import logs as svc  # noqa: E402

svc.DIR_LOGS = Path(_tmp)


def _escrever(nome: str, linhas: list[str], dia: str | None = None) -> Path:
    caminho = svc.DIR_LOGS / (f"{nome}.log" if dia is None else f"{nome}.log.{dia}")
    caminho.write_text("\n".join(linhas) + "\n", encoding="utf-8")
    return caminho


# --------------------------------------------------------------- leitura
_escrever("api", [
    "2026-07-30 10:00:00 INFO telemetria method=GET path=/api/creche status=200",
    "2026-07-30 10:00:01 WARNING app.services.email SMTP nao configurado",
    "2026-07-30 10:00:02 ERROR app.api.creche estourou",
    "2026-07-30 10:00:03 INFO auditoria evento=creche_codigo_enviado cpf_final=9738",
])

d = svc.ler("api")
assert d["total"] == 4, d
assert svc.ler("api", nivel="ERROR")["total"] == 1
# WARNING inclui os erros: quem filtra por "avisos" quer ver o que é pior também
assert svc.ler("api", nivel="WARNING")["total"] == 2
assert svc.ler("api", busca="9738")["total"] == 1
assert svc.ler("api", busca="CRECHE")["total"] == 3, "busca tem que ignorar maiúsculas"
assert svc.ler("api", limite=2)["total"] == 2
# limite devolve as MAIS RECENTES (o fim do arquivo), não as primeiras
assert "9738" in svc.ler("api", limite=1)["linhas"][0]
assert svc.ler("inexistente")["linhas"] == []

# --------------------------------------------------- path traversal (1)
for veneno in ("../etc", "..", "a/b", "API", "x" * 41, ""):
    try:
        svc.ler(veneno)
        raise AssertionError(f"servico {veneno!r} deveria ter sido recusado")
    except ValueError:
        pass
for dia_ruim in ("../../etc/passwd", "2026-7-30", "hoje", "2026-07-30x"):
    try:
        svc.ler("api", dia=dia_ruim)
        raise AssertionError(f"dia {dia_ruim!r} deveria ter sido recusado")
    except ValueError:
        pass

# ------------------------------------------------------ dias e serviços
ontem = (date.today() - timedelta(days=1)).isoformat()
_escrever("api", ["linha de ontem"], dia=ontem)
_escrever("worker", ["worker vivo"])
assert set(svc.servicos()) == {"api", "worker"}, svc.servicos()
dias = svc.dias_disponiveis("api")
assert dias[0] == date.today().isoformat() and ontem in dias, dias
assert svc.ler("api", dia=ontem)["linhas"] == ["linha de ontem"]

# ---------------------------------------------------------- expurgo (2,3)
antigo = (date.today() - timedelta(days=40)).isoformat()
_escrever("api", ["linha velha"], dia=antigo)

assert svc.expurgar(0) == 0, "retenção 0 é INDETERMINADA — não pode apagar nada"
assert (svc.DIR_LOGS / f"api.log.{antigo}").exists(), (
    "com retenção indeterminada o arquivo antigo tem que continuar lá")
assert svc.expurgar(-5) == 0, "valor negativo não pode virar expurgo total"

assert svc.expurgar(7) == 1, "arquivo de 40 dias deveria ter sido apagado"
assert not (svc.DIR_LOGS / f"api.log.{antigo}").exists()
assert (svc.DIR_LOGS / f"api.log.{ontem}").exists(), "o de ontem está dentro do prazo"
assert (svc.DIR_LOGS / "api.log").exists(), (
    "o log CORRENTE nunca pode ser apagado — o serviço está escrevendo nele")

# --------------------------------------------------------- janelas (4)
def _em(h: int) -> str:
    return svc.janela_atual(datetime(2026, 7, 30, h, 30, tzinfo=timezone.utc))


assert _em(0) == _em(5) == "2026-07-30T00", _em(5)
assert _em(6) == _em(11) == "2026-07-30T06"
assert _em(12) == "2026-07-30T12"
assert _em(18) == _em(23) == "2026-07-30T18"
assert len({_em(h) for h in (0, 6, 12, 18)}) == 4, "as 4 janelas têm que ser distintas"

# ------------------------------------------------------------- download
bruto = svc.texto_para_download("api")
assert b"9738" in bruto
try:
    svc.texto_para_download("api", dia="1999-01-01")
    raise AssertionError("dia sem arquivo deveria levantar FileNotFoundError")
except FileNotFoundError:
    pass

# ------------------------------------------------------------- resumo
r = svc._resumo([" INFO x", " ERROR y", " WARNING z", " CRITICAL w"])
assert r == {"total": 4, "erros": 2, "avisos": 1}, r

print("test_logs: OK")
