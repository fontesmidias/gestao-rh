"""Exportar entrega EXATAMENTE quem o RH marcou (v3.17).

Feedback do Bruno (02/09/2026), item 13 da 24ª leva:

    "marca as pessoas, exporta, e vêm outras"

É a única **falha silenciosa** daquela leva, e a mais cara: os outros defeitos
incomodam e são relatados; este não. A planilha sai, abre, parece certa — e vai
para a **folha de pagamento** com gente que ninguém escolheu.

A capacidade de exportar por seleção SEMPRE existiu no servidor (`ids` em
`_colaboradores_para_tirvu`) e **nunca foi usada**: o botão vivia no cabeçalho da
tela, fora do `DashPlanilha`, e montava o próprio conjunto a partir dos filtros
do topo. Efetivar e desligar recebiam a seleção; exportar, não.

O que este teste trava:

1. **A seleção manda.** Marcar N pessoas e exportar traz aquelas N, conferidas
   **nome a nome dentro da planilha** — não pela contagem, que passaria com o
   conjunto errado do mesmo tamanho.
2. **A seleção vence o filtro.** Mandar `ids` E filtros juntos entrega os `ids`.
   É o caso exato do relato: a tela tinha filtro aplicado quando ele marcou.
3. **Sem seleção, vale o filtro.** O comportamento antigo continua — quem não
   marca ninguém leva o que a tela mostra.
4. **Volume real não quebra.** Uma seleção grande passa. Pela querystring não
   passaria: 1.171 UUIDs dão 44,6 KB contra o buffer de 8 KB do nginx, e o 414
   chegaria ao front como "erro" genérico (o `api.js` não trata 414). É por isso
   que a rota é POST com a seleção no CORPO.
5. **Quem não existe é NOMEADO, não sumido.** O caminho por querystring descarta
   id inexistente em silêncio. Numa ação que gera folha, sumiço calado é o
   defeito que esta leva existe para eliminar.
6. **UUID malformado é 422, nunca 500.** No caminho antigo, `uuid.UUID(i)`
   estoura `ValueError` não tratado.
7. **A pré-checagem enxerga o MESMO conjunto** que a exportação. Antes cada uma
   montava o seu, então o aviso podia descrever um conjunto e o arquivo trazer
   outro.

Mutações que este teste precisa reprovar (a razão de ele existir):

  1. `_selecionados` ignorar `pedido.ids` e cair sempre nos filtros -> blocos 1/2
  2. `_selecionados` devolver `[]` em `faltando` -> bloco 5
  3. a pré-checagem montar o conjunto por conta própria -> bloco 7

Precisa dos containers de teste (Postgres em 55432, MinIO em 59000).

Rode: PYTHONPATH=. .venv/Scripts/python.exe tests/test_export_por_selecao.py
"""

import io
import os
import uuid
from datetime import date

for _chave, _valor in dict(
    DATABASE_URL="postgresql+psycopg://admissao:admissao@localhost:55432/admissao",
    MINIO_ENDPOINT="localhost:59000",
    MINIO_ACCESS_KEY="minio",
    MINIO_SECRET_KEY="minio12345",
    MINIO_SECURE="false",
    RH_ADMIN_EMAIL="rh@exemplo.com.br",
    RH_ADMIN_PASSWORD="senha-teste-123",
    SECRET_KEY="segredo-de-teste",
    BASE_URL="http://localhost:8090",
).items():
    os.environ.setdefault(_chave, _valor)

from fastapi.testclient import TestClient  # noqa: E402
from openpyxl import load_workbook  # noqa: E402

from app.core.db import SessionLocal  # noqa: E402
from app.main import app  # noqa: E402
from app.models.candidato import Candidato, StatusCandidato  # noqa: E402

# `raise_server_exceptions=False`: sem isso, uma exceção do servidor é
# repropagada e MATA o script no meio — a saída fica vazia e a ausência de
# "FALHOU" passa por sucesso (v2.72.2). Aqui o bloco 6 exercita justamente um
# caminho de erro, e precisa ver o status code, não um traceback.
c = TestClient(app, raise_server_exceptions=False)

EMAIL = os.environ["RH_ADMIN_EMAIL"]
SENHA = os.environ["RH_ADMIN_PASSWORD"]
r = c.post("/api/rh/auth/login", json={"email": EMAIL, "senha": SENHA})
assert r.status_code == 200, (
    f"login falhou ({r.status_code}): confira RH_ADMIN_EMAIL/RH_ADMIN_PASSWORD "
    f"— `criar_admin_inicial` só cria o admin com a tabela VAZIA. {r.text}")
RH = {"Authorization": f"Bearer {r.json()['token']}"}

SUF = uuid.uuid4().hex[:8]
falhas: list[str] = []


def checar(cond, msg):
    if cond:
        print(f"  ok      {msg}")
    else:
        print(f"  FALHOU  {msg}")
        falhas.append(msg)


def nomes_da_planilha(conteudo: bytes, coluna: str = "Nome Completo") -> set[str]:
    """Os nomes que REALMENTE saíram no arquivo.

    Conferir a contagem não bastaria: exportar o conjunto errado do mesmo
    tamanho passaria verde, e é exatamente o defeito que estamos travando.
    """
    ws = load_workbook(io.BytesIO(conteudo)).active
    cabecalho = [cel.value for cel in ws[1]]
    idx = cabecalho.index(coluna) + 1
    return {ws.cell(row=i, column=idx).value
            for i in range(2, ws.max_row + 1)
            if ws.cell(row=i, column=idx).value}


# ---------------------------------------------------------------------------
# Cenário: cinco colaboradores nossos, com nome reconhecível e sufixo por
# execução (o banco de teste é reaproveitado; nome fixo colidiria entre rodadas).
# Dados fictícios — o repositório é PÚBLICO.
# ---------------------------------------------------------------------------
db = SessionLocal()
criados = []
try:
    for i in range(5):
        cand = Candidato(
            nome_completo=f"Pessoa Teste {i} {SUF}",
            email=f"pessoa{i}.{SUF}@exemplo.com.br",
            cargo_funcao="Auxiliar de Teste",
            status=StatusCandidato.aprovado,
            situacao="ativo",
            data_admissao=date(2026, 1, 15),
            origem="admissao",
        )
        db.add(cand)
        criados.append(cand)
    db.commit()
    for cand in criados:
        db.refresh(cand)
    IDS = [str(x.id) for x in criados]
    NOMES = [x.nome_completo for x in criados]
finally:
    db.close()

MARCADOS = IDS[:3]
NOMES_MARCADOS = set(NOMES[:3])
NOMES_FORA = set(NOMES[3:])

print("\n1. a seleção manda: sai exatamente quem foi marcado")
r = c.post("/api/rh/colaboradores/exportar-selecao?destino=tirvu",
           headers=RH, json={"ids": MARCADOS})
checar(r.status_code == 200, f"exportar por seleção responde 200 (veio {r.status_code})")
if r.status_code == 200:
    saiu = nomes_da_planilha(r.content)
    checar(NOMES_MARCADOS <= saiu,
           "os 3 marcados estão na planilha")
    checar(not (NOMES_FORA & saiu),
           "nenhum dos 2 NÃO marcados entrou na planilha"
           + (f" — vazaram: {sorted(NOMES_FORA & saiu)}" if NOMES_FORA & saiu else ""))

print("\n2. a seleção vence o filtro (o caso do relato)")
# Filtro que, sozinho, traria OUTRO conjunto: `situacao=desligado` não casa com
# ninguém que criamos. Se os filtros ainda mandassem, a planilha viria vazia ou
# com gente de fora — e é assim que "vêm outras" acontecia.
r = c.post("/api/rh/colaboradores/exportar-selecao?destino=tirvu",
           headers=RH, json={"ids": MARCADOS, "situacao": "desligado",
                             "busca": "nome-que-nao-existe"})
checar(r.status_code == 200, f"seleção + filtro responde 200 (veio {r.status_code})")
if r.status_code == 200:
    saiu = nomes_da_planilha(r.content)
    checar(NOMES_MARCADOS <= saiu,
           "com filtro que não casa com ninguém, a SELEÇÃO ainda manda")

print("\n3. sem seleção, vale o filtro da tela")
r = c.post("/api/rh/colaboradores/exportar-selecao?destino=tirvu",
           headers=RH, json={"busca": SUF})
checar(r.status_code == 200, f"exportar por filtro responde 200 (veio {r.status_code})")
if r.status_code == 200:
    saiu = nomes_da_planilha(r.content)
    checar(set(NOMES) <= saiu,
           "sem `ids`, a busca traz os 5 — o comportamento antigo continua")

print("\n4. volume: seleção grande passa (pela querystring não passaria)")
# 200 ids já estouram o buffer de 8 KB do nginx numa URL. No corpo, não.
muitos = MARCADOS + [str(uuid.uuid4()) for _ in range(200)]
r = c.post("/api/rh/colaboradores/exportar-selecao?destino=tirvu",
           headers=RH, json={"ids": muitos})
checar(r.status_code == 200,
       f"203 ids no corpo respondem 200 (veio {r.status_code}) — "
       "na querystring isto seria 414 no nginx")

print("\n5. quem foi pedido e não existe é NOMEADO, não sumido")
fantasma = str(uuid.uuid4())
r = c.post("/api/rh/colaboradores/exportar-selecao/pendencias?destino=tirvu",
           headers=RH, json={"ids": MARCADOS + [fantasma]})
checar(r.status_code == 200, f"pendências responde 200 (veio {r.status_code})")
if r.status_code == 200:
    corpo = r.json()
    checar(corpo.get("nao_encontrados") == [fantasma],
           "o id inexistente é devolvido em `nao_encontrados` — "
           f"veio {corpo.get('nao_encontrados')}")
    checar(corpo.get("total") == 3,
           f"o total conta só quem existe (veio {corpo.get('total')})")

print("\n6. UUID malformado é 422, nunca 500")
r = c.post("/api/rh/colaboradores/exportar-selecao?destino=tirvu",
           headers=RH, json={"ids": ["isto-nao-e-um-uuid"]})
checar(r.status_code == 422,
       f"id inválido responde 422 (veio {r.status_code}) — 500 esconderia a causa")

print("\n7. a pré-checagem enxerga o MESMO conjunto da exportação")
r_pend = c.post("/api/rh/colaboradores/exportar-selecao/pendencias?destino=tirvu",
                headers=RH, json={"ids": MARCADOS})
r_exp = c.post("/api/rh/colaboradores/exportar-selecao?destino=tirvu",
               headers=RH, json={"ids": MARCADOS})
if r_pend.status_code == 200 and r_exp.status_code == 200:
    checar(r_pend.json()["total"] == len(nomes_da_planilha(r_exp.content)),
           "pré-checagem e exportação contam o mesmo conjunto")
else:
    checar(False, "pré-checagem e exportação responderam 200")

print("\n8. destino desconhecido é recusado")
r = c.post("/api/rh/colaboradores/exportar-selecao?destino=inventado",
           headers=RH, json={"ids": MARCADOS})
checar(r.status_code == 422,
       f"destino fora do catálogo responde 422 (veio {r.status_code})")

# ---------------------------------------------------------------------------
# Limpeza: o teste cria registros num banco reaproveitado. Sem isto, cada
# execução deixa cinco pessoas para trás e a base de teste incha até alguém
# perceber. Roda mesmo se um bloco falhou.
# ---------------------------------------------------------------------------
db = SessionLocal()
try:
    for cid in IDS:
        obj = db.get(Candidato, uuid.UUID(cid))
        if obj is not None:
            db.delete(obj)
    db.commit()
finally:
    db.close()

print()
if falhas:
    print(f"test_export_por_selecao: {len(falhas)} FALHA(S)")
    for f in falhas:
        print(f"  - {f}")
    raise SystemExit(1)
print("test_export_por_selecao: OK")
