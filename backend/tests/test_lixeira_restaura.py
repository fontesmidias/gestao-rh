"""A lixeira DEVOLVE o que engoliu — e toda entidade que entra sabe voltar.

Por que este teste existe (v2.72.2): a pendência registrada era estreita —
*"conferir a restauração de uma vaga pela lixeira"*, aberta desde a v2.67 e
repetida em quatro relatórios. Ao exercitá-la, o defeito era MUITO mais largo.

`api/lixeira.py::_reconstruir` tinha um mapa `entidade → modelo` com DUAS
entradas (`posto`, `modelo_documento`), enquanto OITO entidades já eram mandadas
para a lixeira: vaga (v2.67), prova, item de banco, papel de assinatura, roteiro
de entrevista, teste de candidato e entrevista. Para as seis faltantes a lixeira
era **via de mão única**: o registro entrava, aparecia listado com rótulo e data
igualzinho aos outros, e restaurar respondia `422 entidade_desconhecida`.

Medido na rota antes de corrigir:

    delete /rh/vagas/{id}      -> 204   (some da listagem)
    GET /rh/lixeira            -> lá está ela, com rótulo e data
    POST /{item}/restaurar     -> 422 {"detail":"entidade_desconhecida"}

O que torna isso pior que um 500: **a exclusão funciona**. Nada avisa. O RH só
descobre no dia em que precisa desfazer — que é o único dia em que a lixeira
importa. É a mesma família do worker que não roda (v2.66) e do documento que não
nasce (v2.69): o silêncio se confunde com "está tudo certo".

O bloco 1 é o guarda-corpo que impede a lacuna de voltar: varre as chamadas de
`mandar_para_lixeira` em `app/api/` e cobra que TODA entidade esteja no mapa.
Sem ele, o próximo módulo que mandar algo para a lixeira repete o defeito — e
repetir era o padrão, já que aconteceu seis vezes seguidas sem ninguém ver.

⚠️ Este bloco NÃO chuta uma contagem (`assert len(mapa) == 9` quebraria na
próxima entidade legítima e a "correção" óbvia — incrementar o número — faria o
teste não proteger nada, lição da v2.25). Ele deriva a garantia do próprio
código-fonte.

Mutações verificadas:
  1. tirar `"vaga"` do mapa                      -> blocos 1 e 3 falham
  2. tirar `"prova_cargo"` do mapa               -> bloco 1 falha, nomeando-a
  3. `_reconstruir` aceita entidade desconhecida -> bloco 5 falha
  4. restaurar não marca `restaurado_em`         -> bloco 4 falha

Precisa dos containers de teste:
  docker run -d --name pg-teste ... postgres:16-alpine
  docker run -d --name minio-teste ... quay.io/minio/minio server /data

Rode: PYTHONPATH=. .venv/Scripts/python.exe tests/test_lixeira_restaura.py
"""

import os
import pathlib
import re
import uuid

for _chave, _valor in dict(
    DATABASE_URL="postgresql+psycopg://admissao:admissao@localhost:55432/admissao",
    MINIO_ENDPOINT="localhost:59000",
    MINIO_ACCESS_KEY="minio",
    MINIO_SECRET_KEY="minio12345",
    MINIO_SECURE="false",
    RH_ADMIN_EMAIL="rh@greenhousedf.com.br",
    RH_ADMIN_PASSWORD="senha-teste-123",
    SECRET_KEY="segredo-de-teste",
    BASE_URL="http://localhost:8090",
).items():
    os.environ.setdefault(_chave, _valor)

from fastapi.testclient import TestClient  # noqa: E402

from app.api.lixeira import classes_restauraveis  # noqa: E402
from app.main import app  # noqa: E402

RAIZ = pathlib.Path(__file__).resolve().parents[1]

c = TestClient(app)

# Credencial do AMBIENTE, nunca literal (v2.71/v2.72): no CI o admin nasce com a
# senha do `.env` do job.
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
        print(f"  ok   {msg}")
    else:
        print(f"  FALHOU  {msg}")
        falhas.append(msg)


def _item_na_lixeira(entidade: str, marca: str):
    """Acha o item na lixeira pelo rótulo, que é o que o RH vê na tela."""
    lx = c.get("/api/rh/lixeira", headers=RH).json()
    return next((i for i in lx["itens"]
                 if i["entidade"] == entidade and marca in (i["rotulo"] or "")), None)


# --------------------------------------------------------------------------
print("\n1. TODA entidade que entra na lixeira sabe voltar (guarda-corpo)")
# --------------------------------------------------------------------------
# ⚠️ Mutações 1 e 2: remover uma entrada do mapa -> falha NOMEANDO a entidade.
#
# A verdade vem do código-fonte, não de uma lista escrita aqui: se amanhã um
# módulo novo mandar algo para a lixeira, este teste cobra o par sozinho.
_MAND = re.compile(r'mandar_para_lixeira\(\s*db\s*,\s*[^,]+,\s*["\']([a-z_]+)["\']')


def _so_codigo(texto: str) -> str:
    """Devolve o texto SEM comentários e SEM docstrings.

    ⚠️ Sem isto, o varredor casa com a PRÓPRIA DOCUMENTAÇÃO: o docstring de
    `classes_restauraveis()` explica o defeito escrevendo
    `mandar_para_lixeira(db, obj, "x", ...)` como exemplo, e o `"x"` entrava na
    lista como se fosse uma entidade órfã de verdade. O teste reprovava o texto
    que explica a correção — e o reflexo de quem o visse seria apagar a
    explicação. É a armadilha registrada na v2.71 (`_tem_no_codigo`).
    """
    linhas, dentro = [], False
    for linha in texto.splitlines():
        nua = linha.strip()
        aspas = nua.count('"""') + nua.count("'''")
        if aspas:
            if aspas % 2 == 1:
                dentro = not dentro
            continue
        if dentro or nua.startswith("#"):
            continue
        linhas.append(linha.split("#", 1)[0])
    return "\n".join(linhas)


entidades_no_codigo: dict[str, list[str]] = {}
for arquivo in sorted((RAIZ / "app" / "api").glob("*.py")):
    fonte = _so_codigo(arquivo.read_text(encoding="utf-8"))
    for ent in _MAND.findall(fonte):
        entidades_no_codigo.setdefault(ent, []).append(arquivo.name)

checar(len(entidades_no_codigo) >= 8,
       f"o varredor achou as chamadas de mandar_para_lixeira "
       f"({len(entidades_no_codigo)} entidades) — se cair a zero, a regex "
       f"parou de casar e o teste vira decoração")

mapa = classes_restauraveis()
orfas = {e: arqs for e, arqs in entidades_no_codigo.items() if e not in mapa}
checar(not orfas,
       "toda entidade mandada para a lixeira está no mapa de restauração"
       + (f" — ÓRFÃS: {orfas}" if orfas else ""))

# O contrário também é defeito, mas BENIGNO: entrada no mapa para algo que
# ninguém manda para a lixeira é código morto, não via de mão única. Fica como
# aviso, não como falha — remover entrada de entidade que voltou a ser excluída
# seria pior.
sobrando = [e for e in mapa if e not in entidades_no_codigo]
if sobrando:
    print(f"  aviso  no mapa mas ninguém manda para a lixeira: {sobrando}")

# --------------------------------------------------------------------------
print("\n2. a vaga excluída some da listagem e aparece na lixeira")
# --------------------------------------------------------------------------
TITULO = f"Vaga restauracao {SUF}"
vid = c.post("/api/rh/vagas", headers=RH,
             json={"titulo": TITULO, "descricao": "Descrição da vaga.",
                   "cargo": "Vigia", "regiao": "Asa Sul"}).json()["id"]

r = c.delete(f"/api/rh/vagas/{vid}", headers=RH)
checar(r.status_code in (200, 204), f"DELETE /rh/vagas responde {r.status_code}")


def _vagas():
    dados = c.get("/api/rh/vagas", headers=RH).json()
    return dados["vagas"] if isinstance(dados, dict) and "vagas" in dados else dados


checar(not any(v["id"] == vid for v in _vagas()),
       "depois de excluir, a vaga NÃO aparece mais na listagem")

item = _item_na_lixeira("vaga", SUF)
checar(item is not None, "a vaga aparece na lixeira, com o título como rótulo")

# --------------------------------------------------------------------------
print("\n3. restaurar DEVOLVE a vaga, com os dados intactos")
# --------------------------------------------------------------------------
# ⚠️ Mutação 1 (tirar "vaga" do mapa): estas asserções falham com 422.
#
# Era exatamente aqui que a pendência morava: antes desta leva, a resposta era
# `422 entidade_desconhecida` e a vaga NUNCA voltava.
r = c.post(f"/api/rh/lixeira/{item['id']}/restaurar", headers=RH)
checar(r.status_code == 200,
       f"POST /restaurar responde 200 (era 422 entidade_desconhecida): {r.text[:90]}")

voltou = [v for v in _vagas() if v["id"] == vid]
checar(bool(voltou), "a vaga VOLTA para a listagem depois de restaurada")
if voltou:
    v = voltou[0]
    checar(v.get("titulo") == TITULO, "o título volta idêntico ao que foi excluído")
    checar(v.get("cargo") == "Vigia" and v.get("regiao") == "Asa Sul",
           "os demais campos voltam preenchidos (não é um registro em branco)")

# --------------------------------------------------------------------------
print("\n4. o item restaurado SAI da lixeira — não fica para ser restaurado 2x")
# --------------------------------------------------------------------------
# ⚠️ Mutação 4: não marcar `restaurado_em` -> estas 2 asserções falham.
#
# Sem isso o mesmo item continuaria na lista e o 2º clique bateria em
# `registro_ja_existe` (409) — erro que parece defeito do sistema para quem só
# clicou no que a tela oferecia.
checar(_item_na_lixeira("vaga", SUF) is None,
       "o item some da lixeira depois de restaurado")

r = c.post(f"/api/rh/lixeira/{item['id']}/restaurar", headers=RH)
checar(r.status_code == 404,
       "restaurar o MESMO item de novo dá 404 (já foi restaurado)")

# --------------------------------------------------------------------------
print("\n5. entidade desconhecida continua sendo recusada")
# --------------------------------------------------------------------------
# ⚠️ Mutação 3: `_reconstruir` aceitando qualquer entidade -> falha.
#
# O 422 é a rede de segurança para o caso de alguém mandar algo para a lixeira
# sem acrescentar ao mapa. Alargar o mapa NÃO significa afrouxar isto — sem a
# recusa, o erro viraria um 500 no `cls()` com `NoneType`.
from app.core.db import SessionLocal  # noqa: E402
from app.models.lixeira import ItemLixeira  # noqa: E402

with SessionLocal() as db:
    fake = ItemLixeira(entidade=f"coisa_inexistente_{SUF}", entidade_id=uuid.uuid4(),
                       rotulo=f"Fantasma {SUF}", dados={}, ator="teste")
    db.add(fake)
    db.commit()
    fake_id = fake.id

# `raise_server_exceptions=False`: sem isso, a mutação que faz o `_reconstruir`
# aceitar qualquer entidade não REPROVA — ela mata o processo. O TestClient
# repropaga a exceção do servidor, o script morre no meio e nunca imprime o
# resultado; a saída fica sem "FALHOU" nenhum e PARECE aprovação (foi o que
# aconteceu na 1ª execução da mutação 3). Com a flag, o 500 vira resposta e a
# asserção pode dizer que ele é errado.
cliente_tolerante = TestClient(app, raise_server_exceptions=False)
r = cliente_tolerante.post(f"/api/rh/lixeira/{fake_id}/restaurar", headers=RH)
checar(r.status_code == 422 and "desconhecida" in r.text,
       f"entidade fora do mapa é recusada com 422, não estoura 500 "
       f"(veio {r.status_code})")

with SessionLocal() as db:
    lixo = db.get(ItemLixeira, fake_id)
    if lixo is not None:
        db.delete(lixo)
        db.commit()

# --------------------------------------------------------------------------
print("\n6. a lixeira é do RH — não é rota pública")
# --------------------------------------------------------------------------
checar(c.get("/api/rh/lixeira").status_code in (401, 403),
       "GET /rh/lixeira sem token é recusado")


print()
if falhas:
    print(f"test_lixeira_restaura: {len(falhas)} FALHA(S)")
    for f_ in falhas:
        print(f"  - {f_}")
    raise SystemExit(1)
print("test_lixeira_restaura: OK")
