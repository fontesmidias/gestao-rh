"""A fonte do sistema é configurável, e SÓ do sistema (v2.85).

Pedido do Bruno (2026-08-08):

    "quero que todas as fontes, de maneira global, seja Yu Gothic regular por
     padrão, mas que possa ser customizado em Configurações, dentro da aba
     Identidade visual. não precisa alterar a fonte dos documentos, apenas do
     sistema. obviamente só negritando o que tem que ficar em negrito."

Três coisas que este teste trava:

1. **SÓ o catálogo entra.** A pilha escolhida vai para o `--fonte` de TODA tela,
   inclusive as públicas. Texto livre deixaria gravar CSS arbitrário — e uma
   fonte que não existe **não dá erro**: a tela só fica estranha, sem nada
   apontando a causa. Mesma trava do documento específico (v2.79).
2. **A rota pública existe e devolve a PILHA, não a chave.** O wizard do
   candidato não tem login e é a maior parte do uso do sistema; sem rota
   pública, a customização valeria no painel e não valeria para quem está
   enviando documento pelo celular.
3. **Os DOCUMENTOS não mudam.** O PDF é gerado pelo fpdf2 com fontes próprias, e
   o hash do ato de assinatura é calculado sobre ele — trocar a fonte do
   documento faria manifesto já emitido apontar para um arquivo que não se
   reproduz. É o limite explícito do pedido.

Rode: PYTHONPATH=. .venv/Scripts/python.exe tests/test_fonte_configuravel.py
"""

import os
import re
import pathlib
import sys

os.environ.setdefault("DATABASE_URL",
                      "postgresql+psycopg://admissao:admissao@localhost:55432/admissao")
os.environ.setdefault("SECRET_KEY", "segredo-de-teste")
os.environ.setdefault("MINIO_ENDPOINT", "localhost:59000")
os.environ.setdefault("MINIO_ACCESS_KEY", "minio")
os.environ.setdefault("MINIO_SECRET_KEY", "minio12345")
os.environ.setdefault("RH_ADMIN_EMAIL", "rh@exemplo.com.br")
os.environ.setdefault("RH_ADMIN_PASSWORD", "senha-teste-123")

from fastapi.testclient import TestClient          # noqa: E402

from app.main import app                           # noqa: E402
from app.services.marca import (FONTE_PADRAO, FONTES,  # noqa: E402
                                pilha_da_fonte)

c = TestClient(app, raise_server_exceptions=False)

RAIZ = pathlib.Path(__file__).resolve().parents[2]
FALHAS: list[str] = []


def checar(condicao: bool, descricao: str) -> None:
    print(("  ok    " if condicao else "  FALHA ") + descricao)
    if not condicao:
        FALHAS.append(descricao)


_EMAIL = os.environ["RH_ADMIN_EMAIL"]
_login = c.post("/api/rh/auth/login",
                json={"email": _EMAIL, "senha": os.environ["RH_ADMIN_PASSWORD"]})
assert _login.status_code == 200 and "token" in _login.json(), (
    f"login do RH falhou ({_login.status_code}) — confira RH_ADMIN_EMAIL/"
    f"RH_ADMIN_PASSWORD do ambiente: {_login.text[:160]}")
H = {"Authorization": f"Bearer {_login.json()['token']}"}


print("\n1. o catálogo tem Yu Gothic como padrão, com a livre atrás dela")
checar(FONTE_PADRAO == "yu-gothic",
       f"o padrão do sistema é Yu Gothic (é {FONTE_PADRAO!r})")
_pilha = FONTES[FONTE_PADRAO]["pilha"]
checar("Yu Gothic" in _pilha, "a pilha começa pela Yu Gothic")
# Yu Gothic é PROPRIETÁRIA e não pode ser empacotada: sem uma livre atrás dela,
# quem está no Android/iPhone/Linux — a maior parte do público do wizard — cairia
# direto na fonte genérica do aparelho.
checar("Noto Sans JP" in _pilha,
       "e traz a Noto Sans JP (livre, embutida) para quem não a tem instalada")
checar(_pilha.rstrip().endswith("sans-serif"),
       "terminando em `sans-serif` — nenhuma tela fica sem fonte")
checar(all(f["pilha"].strip() for f in FONTES.values()),
       "toda fonte do catálogo tem pilha preenchida")

print("\n2. chave inválida NÃO deixa a tela sem fonte")
checar(pilha_da_fonte("nao-existe") == _pilha,
       "chave desconhecida cai no padrão (banco editado à mão, versão antiga)")
checar(pilha_da_fonte(None) == _pilha, "e `None` também")

print("\n3. a rota PÚBLICA existe — o wizard do candidato não tem login")
r = c.get("/api/marca/aparencia")
checar(r.status_code == 200, f"responde 200 SEM autenticação (veio {r.status_code})")
_fonte_publica = r.json().get("fonte", "") if r.status_code == 200 else ""
checar("," in _fonte_publica,
       f"e devolve a PILHA resolvida, não a chave (veio {_fonte_publica[:40]!r})")

print("\n4. o painel recebe o catálogo para montar o seletor")
r = c.get("/api/rh/marca", headers=H)
checar(r.status_code == 200, f"a rota do painel responde (veio {r.status_code})")
_corpo = r.json() if r.status_code == 200 else {}
checar(len(_corpo.get("fontes") or []) == len(FONTES),
       f"com as {len(FONTES)} fontes do catálogo (veio {len(_corpo.get('fontes') or [])})")
# Sem a `pilha`, a tela não teria como mostrar a prévia — e fonte se confere
# olhando, não lendo o nome.
checar(all(f.get("pilha") and f.get("rotulo") for f in (_corpo.get("fontes") or [])),
       "cada uma com rótulo e pilha (a prévia depende da pilha)")

print("\n5. SÓ o catálogo entra — texto livre viraria CSS arbitrário em toda tela")
r = c.put("/api/rh/marca", headers=H, json={"empresa_fonte": "Comic Sans; }"})
checar(r.status_code == 422, f"fonte fora do catálogo é recusada (veio {r.status_code})")
checar(r.json().get("detail") == "fonte_desconhecida",
       f"dizendo POR QUÊ (veio {r.json().get('detail')!r})")

print("\n6. trocar a fonte funciona, e volta ao padrão")
r = c.put("/api/rh/marca", headers=H, json={"empresa_fonte": "georgia"})
checar(r.status_code == 200, f"grava uma do catálogo (veio {r.status_code})")
checar("Georgia" in (r.json().get("fonte_pilha") or ""),
       f"e devolve a pilha nova para a tela aplicar na hora "
       f"(veio {(r.json().get('fonte_pilha') or '')[:40]!r})")
# A rota PÚBLICA tem que acompanhar: é ela que serve o candidato.
checar("Georgia" in (c.get("/api/marca/aparencia").json().get("fonte") or ""),
       "a rota pública passa a servir a fonte nova")
c.put("/api/rh/marca", headers=H, json={"empresa_fonte": FONTE_PADRAO})
checar(pilha_da_fonte("yu-gothic") in
       (c.get("/api/marca/aparencia").json().get("fonte") or ""),
       "e volta ao padrão sem sobra")

print("\n7. os DOCUMENTOS não mudam — é o limite explícito do pedido")
# O PDF é gerado pelo fpdf2 com fontes próprias, e o hash do ato de assinatura é
# calculado sobre ele. Se o gerador passasse a ler a fonte da config, manifesto
# já emitido apontaria para um arquivo que não se reproduz.
for arq in ("app/services/fichas.py", "app/services/entrevista_pdf.py",
            "app/services/documentos_texto.py"):
    caminho = RAIZ / "backend" / arq
    if not caminho.exists():
        continue
    fonte = caminho.read_text(encoding="utf-8")
    checar("empresa_fonte" not in fonte and "pilha_da_fonte" not in fonte,
           f"{arq} não lê a fonte da configuração")

print("\n8. o CSS usa o TOKEN, nunca a lista literal")
# Estas afirmações leem o FRONTEND, que NÃO existe dentro do container da API (o
# contexto de build da imagem é só `./backend`). Ali elas se anunciam como
# PULADAS, em vez de estourar `FileNotFoundError` e derrubar as sete seções que
# já passaram — e o anúncio importa: pular calado viraria "coberto" sem cobrir.
_css = RAIZ / "frontend" / "src" / "styles.css"
if not _css.exists():
    print("  PULADO (sem a árvore do frontend — roda fora do container da API)")
else:
    css = _css.read_text(encoding="utf-8")
    # O `body` repetia a pilha literal: o token era sobrescrito e o texto corrido
    # ficava com a fonte antiga — a tela muda "quase toda", o pior de enxergar.
    corpo = css.split("body {", 1)[1].split("}", 1)[0] if "body {" in css else ""
    # Sem tirar os COMENTÁRIOS, a asserção casa com o `var(--fonte)` escrito no
    # comentário que EXPLICA a regra — e passa verde com a pilha literal de volta
    # no `font-family` (mutação que a primeira versão deste teste deixou
    # escapar). É a armadilha da v2.71: teste que aprova a própria documentação.
    _sem_comentario = re.sub(r"/\*.*?\*/", "", corpo, flags=re.S)
    _decl = [ln for ln in _sem_comentario.splitlines() if "font-family" in ln]
    checar(bool(_decl) and "var(--fonte)" in _decl[0],
           f"o `body` declara `font-family: var(--fonte)` — senão o texto corrido "
           f"ignora a escolha (veio {(_decl[0].strip() if _decl else 'nenhuma')!r})")
    checar(".fonte-previa" in css,
           "a classe da prévia existe no styles.css (classe fantasma não estiliza nada)")

    main = (RAIZ / "frontend" / "src" / "main.jsx").read_text(encoding="utf-8")
    checar("noto-sans-jp" in main,
           "a Noto Sans JP é importada — sem isso o fallback da Yu Gothic não existe")
    checar("/api/marca/aparencia" in main,
           "e o main.jsx busca a fonte configurada")

print()
if FALHAS:
    print(f"test_fonte_configuravel: {len(FALHAS)} FALHA(S)")
    for f in FALHAS:
        print(f"  - {f}")
    sys.exit(1)
print("test_fonte_configuravel: OK")
