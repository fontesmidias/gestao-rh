"""Comprovante de residência: o OCR não pode rodar duas vezes (v2.31).

Relato de campo em 2026-07-30: *"no campo de comprovante de residência do
Jonatas, na hora que tenta puxar o arquivo do celular, informa que está sem
internet"*.

Não era internet. O comprovante é o ÚNICO slot com OCR bloqueante, e o texto
era lido DUAS vezes com os mesmos bytes na mesma requisição:

1. `validar_comprovante_recente` — a regra dos 90 dias (`documentos.py:100`)
2. `_texto` — as sugestões de ficha (`documentos.py:104`)

Cada leitura é uma ida à Mistral com `timeout=30s`. Um comprovante de duas
páginas podia passar de 120s de trabalho síncrono contra os **60s de
`proxy_read_timeout`** do nginx. O nginx cortava a conexão, o `fetch` rejeitava
e o front traduzia QUALQUER rejeição como "você está sem internet"
(`api.js:36`) — mensagem que ainda convida a pessoa a tentar de novo, gastando
outros 60s.

Este teste trava as duas garantias:

- **o OCR roda UMA vez por arquivo** numa requisição (o defeito de origem);
- **o cache é por CONTEÚDO**, não por tipo: dois comprovantes diferentes no
  mesmo processo não podem trocar de texto entre si. Um cache com chave errada
  aqui gravaria o endereço de uma pessoa na ficha de outra — bem pior que a
  lentidão que ele veio resolver.

Não precisa de containers.
Rode: PYTHONPATH=. .venv/Scripts/python.exe tests/test_comprovante_ocr.py
"""

import os

os.environ.setdefault("SECRET_KEY", "segredo-de-teste")
os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://x:x@localhost:1/x")

from app.services import normalizacao as n  # noqa: E402

# ------------------------------------------------------------------ arranjo
chamadas: list[bytes] = []


def _mistral_falso(dados: bytes, mime: str) -> str:
    """Conta cada ida ao OCR e devolve um texto derivado do CONTEÚDO — é o que
    permite provar que o cache não troca o texto de um arquivo pelo de outro."""
    chamadas.append(dados)
    return f"TEXTO-DE-{dados.decode('latin-1')[:15]}"


_original = n._texto_do_envio_sem_cache


def _sem_cache(ext, dados, pdf, _texto_via_mistral):
    return _original(ext, dados, pdf, _mistral_falso)


n._texto_do_envio_sem_cache = _sem_cache
n._CACHE_TEXTO.clear()

COMPROVANTE_A = b"CONTA-DE-LUZ-A" + b"\x00" * 40
COMPROVANTE_B = b"CONTA-DE-AGUA-B" + b"\x00" * 40

# ------------------------------- 1) OCR uma vez só na mesma requisição
t1 = n._texto_do_envio(".jpg", COMPROVANTE_A, b"")
t2 = n._texto_do_envio(".jpg", COMPROVANTE_A, b"")
assert t1 == t2, "a segunda leitura devolveu texto diferente"
assert len(chamadas) == 1, (
    f"o OCR foi chamado {len(chamadas)}x para o MESMO arquivo — é o defeito que "
    f"estourava o timeout do nginx e virava 'sem internet' na tela")

# ------------------------------- 2) cache por CONTEÚDO, não por tipo
chamadas.clear()
tb = n._texto_do_envio(".jpg", COMPROVANTE_B, b"")
assert len(chamadas) == 1, "arquivo novo tem que ser lido"
assert tb != t1, (
    "documento DIFERENTE recebeu o texto do anterior — isso gravaria o endereço "
    "de uma pessoa na ficha de outra")
assert "CONTA-DE-AGUA" in tb, tb

# a extensão faz parte da chave: o mesmo byte lido como pdf não reusa o de jpg
chamadas.clear()
n._texto_do_envio(".pdf", COMPROVANTE_A, COMPROVANTE_A)
assert len(chamadas) == 1, "extensão diferente tem que ser lida de novo"

# ------------------------------- 3) o caminho REAL do comprovante lê 1x
# É o que acontece em `documentos.py`: a validação dos 90 dias e as sugestões,
# uma seguida da outra, com os mesmos bytes.
chamadas.clear()
n._CACHE_TEXTO.clear()
n.validar_comprovante_recente("comprovante.jpg", COMPROVANTE_A, b"")
n._texto_do_envio(".jpg", COMPROVANTE_A, b"")
assert len(chamadas) == 1, (
    f"o fluxo do comprovante ainda faz {len(chamadas)} leituras de OCR — era "
    f"exatamente isto que dobrava o tempo do upload")

# ------------------------------- 4) o cache não cresce sem limite
chamadas.clear()
for i in range(n._CACHE_TEXTO_MAX + 5):
    n._texto_do_envio(".jpg", f"ARQUIVO-{i}".encode() + b"\x00" * 20, b"")
assert len(n._CACHE_TEXTO) <= n._CACHE_TEXTO_MAX, (
    f"cache com {len(n._CACHE_TEXTO)} entradas — texto de documento é dado "
    f"pessoal e não pode ficar acumulando na memória do processo")

n._texto_do_envio_sem_cache = _original
n._CACHE_TEXTO.clear()
print("test_comprovante_ocr: OK")
