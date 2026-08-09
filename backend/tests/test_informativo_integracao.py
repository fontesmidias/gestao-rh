"""Ficha de integração por REGIME — o efetivo também tem a dele (2026-08-05).

Feedback do Bruno: *"Ficha de integração não está sendo gerada para os efetivos,
aos moldes das que são geradas para os intermitentes"*.

Era verdade e a causa estava numa linha só: `gerar_docs_do_posto_e_regime` fazia
`if candidato.regime == "intermitente"` e mais nada. O efetivo — a MAIORIA dos
admitidos — não recebia ficha de integração nenhuma. O que ocupava esse lugar no
nome (`informacoes_trabalhador`) é outra coisa: um ofício de direitos do kit
INFRAERO, que só nasce em posto INFRAERO.

O defeito era invisível porque a ausência não gera erro: ninguém abre uma tela e
vê "está faltando um documento que deveria existir". O comentário do modelo
(`candidato.py`, *"Decide qual ficha de integração o colaborador assina"*) até
descrevia a intenção — que o código nunca cumpriu para o lado efetivo.

O que este teste trava, e por quê cada coisa:

1. **O efetivo recebe a ficha** — a asserção que faltava. Percorre a ROTA de
   convite, não a função interna: é o caminho que produção usa (lição da v2.68).
2. **O intermitente continua recebendo a dele** — a correção não podia trocar
   um defeito pelo outro.
3. **Cada um recebe UMA só** — receber as duas faria a pessoa assinar períodos
   de pagamento que não são os dela.
4. **Os PERÍODOS DE PAGAMENTO saem certos no PDF** (efetivo 1 a 30 ×
   intermitente semanal). É o conteúdo que distingue as duas fichas, e é o
   pedido literal do Bruno. As âncoras são CONSTANTES escritas aqui, nunca
   valores lidos do próprio sistema — comparar a resposta com ela mesma passa
   com o defeito presente (v2.64).
5. **Nasce aguardando liberação do RH** (v1.92): informativo de integração só
   vai ao candidato quando o RH dispara.

Precisa dos containers de teste.
Rode: PYTHONPATH=. .venv/Scripts/python.exe tests/test_informativo_integracao.py
"""

import os
import re

os.environ.setdefault(
    "DATABASE_URL", "postgresql+psycopg://admissao:admissao@localhost:55432/admissao")
os.environ.setdefault("MINIO_ENDPOINT", "localhost:59000")
os.environ.setdefault("MINIO_ACCESS_KEY", "minio")
os.environ.setdefault("MINIO_SECRET_KEY", "minio12345")
os.environ.setdefault("MINIO_SECURE", "false")
os.environ.setdefault("RH_ADMIN_EMAIL", "rh@exemplo.com.br")
os.environ.setdefault("RH_ADMIN_PASSWORD", "senha-teste-123")
os.environ.setdefault("SECRET_KEY", "segredo-de-teste")
os.environ.setdefault("BASE_URL", "http://localhost:8090")

import uuid  # noqa: E402

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import select  # noqa: E402

from app.core.db import SessionLocal  # noqa: E402
from app.main import app  # noqa: E402
from app.models.assinatura import Assinatura, DocumentoAssinavel  # noqa: E402
from app.models.candidato import Candidato  # noqa: E402
from app.services.fichas import GERADORES  # noqa: E402

c = TestClient(app)
rh = {"Authorization": "Bearer " + c.post(
    "/api/rh/auth/login",
    json={"email": "rh@exemplo.com.br", "senha": "senha-teste-123"}
).json()["token"]}

SUF = uuid.uuid4().hex[:8]  # tabelas com campo único não toleram valor fixo (v2.14)
jid = c.post("/api/rh/jornadas", headers=rh,
             json={"descricao": f"INTEGRACAO - TESTE {SUF}"}).json()["id"]

EFETIVO = DocumentoAssinavel.informativo_efetivo
INTERMITENTE = DocumentoAssinavel.informativo_intermitente


def _convidar(regime: str) -> uuid.UUID:
    """Cria o candidato pela ROTA de convite — o caminho de produção."""
    r = c.post("/api/rh/candidatos", headers=rh, json={
        "nome_completo": f"Teste Integração {regime.title()} {SUF}",
        "email": f"integracao.{regime}.{SUF}@example.com",
        "celular_whatsapp": "+5561999990000", "jornada_id": jid,
        "cargo_funcao": "Assistente de RH", "regime": regime,
        "registra_ponto": True})
    assert r.status_code in (200, 201), r.text
    return uuid.UUID(r.json()["candidato"]["id"])


def _assinaturas(cid: uuid.UUID) -> list[Assinatura]:
    with SessionLocal() as db:
        return list(db.scalars(select(Assinatura).where(
            Assinatura.candidato_id == cid,
            Assinatura.invalidada_em.is_(None))).all())


def _fichas_de_integracao(cid: uuid.UUID) -> set[DocumentoAssinavel]:
    return {a.documento for a in _assinaturas(cid)} & {EFETIVO, INTERMITENTE}


# ---------------------------------------------------------------- 1 e 2 e 3
efetivo_id = _convidar("efetivo")
assert _fichas_de_integracao(efetivo_id) == {EFETIVO}, (
    "o candidato EFETIVO tem que receber a ficha de integração dele — era "
    "exatamente o que faltava (o `if` só olhava o intermitente), e a ausência "
    f"não gera erro nenhum: {_fichas_de_integracao(efetivo_id)}")

intermitente_id = _convidar("intermitente")
assert _fichas_de_integracao(intermitente_id) == {INTERMITENTE}, (
    "o intermitente tem que continuar recebendo a ficha DELE, e só ela — "
    "receber as duas faria a pessoa assinar os períodos de pagamento do outro "
    f"regime: {_fichas_de_integracao(intermitente_id)}")

# ------------------------------------------------------------------------ 5
with SessionLocal() as db:
    a = db.scalar(select(Assinatura).where(Assinatura.candidato_id == efetivo_id,
                                           Assinatura.documento == EFETIVO))
    assert a.aguardando_liberacao is True, (
        "a ficha de integração nasce BLOQUEADA e só vai ao candidato depois que "
        "o RH libera (v1.92) — o intermitente sempre foi assim")

# ------------------------------------------------------------------------ 4
# Períodos de pagamento: é o que distingue as duas fichas. As âncoras são
# constantes DESTE teste, nunca valores lidos do sistema sob teste (v2.64).
def _texto_do_pdf(cid: uuid.UUID, chave: str) -> str:
    from pypdf import PdfReader
    import io
    with SessionLocal() as db:
        cand = db.get(Candidato, cid)
        pdf = GERADORES[chave](db, cand)
    bruto = "\n".join(p.extract_text() or "" for p in PdfReader(io.BytesIO(pdf)).pages)
    # o multi_cell do fpdf quebra a linha no meio da frase (v2.56)
    return re.sub(r"\s+", " ", bruto)


txt_efetivo = _texto_do_pdf(efetivo_id, "informativo_efetivo")
txt_intermitente = _texto_do_pdf(intermitente_id, "informativo_intermitente")

assert "do dia 1 ao dia 30" in txt_efetivo, (
    "o pedido do Bruno: para o EFETIVO o intervalo de pagamento dos benefícios "
    f"é de 1 a 30. Não achei no PDF: {txt_efetivo[:400]}")
assert "semanalmente" not in txt_efetivo and "apuração semanal" not in txt_efetivo, (
    "a ficha do efetivo não pode prometer pagamento semanal — é o ciclo do "
    f"INTERMITENTE, e sairia num documento que a pessoa assina: {txt_efetivo[:400]}")

assert "semanalmente" in txt_intermitente and "apuração semanal" in txt_intermitente, (
    "o intermitente continua com o ciclo SEMANAL (VT e VA) — a correção do "
    f"efetivo não podia mexer nele: {txt_intermitente[:400]}")
assert "do dia 1 ao dia 30" not in txt_intermitente, (
    "o ciclo mensal não pode vazar para a ficha do intermitente")

# As duas são a MESMA ficha em tudo o mais: o corpo comum tem que estar nas duas.
for ancora in ("INFORMATIVO DE INTEGRAÇÃO", "VALE TRANSPORTE", "VALE ALIMENTAÇÃO",
               "PONTO ELETRÔNICO", "NORMATIVOS E ORIENTAÇÕES"):
    assert ancora in txt_efetivo, (
        f"a ficha do efetivo saiu sem a seção '{ancora}' — o pedido foi que ela "
        "fosse 'aos moldes' da do intermitente, não uma versão reduzida")
    assert ancora in txt_intermitente, f"ficha do intermitente sem '{ancora}'"

# Local de trabalho: o intermitente não é alocado a posto fixo (sai o rótulo do
# regime); o efetivo sai com o posto REAL do cadastro.
assert "GHS - INTERMITENTE" in txt_intermitente, (
    "o intermitente imprime o rótulo do regime como local de trabalho")
assert "GHS - INTERMITENTE" not in txt_efetivo, (
    "o efetivo NÃO é alocado como intermitente — imprime o posto dele")

# Prova de que o posto do CADASTRO chega ao PDF, e não um rótulo fixo: aloca o
# efetivo num posto e confere o nome dele no documento. Sem isso, chumbar
# "GHS SEDE" no gerador passaria despercebido.
posto_nome = f"GOLGI BRASILIA TESTE {SUF}"
pid = c.post("/api/rh/postos", headers=rh,
             json={"nome": posto_nome, "sigla": "GOLGI"}).json()["id"]
assert c.put(f"/api/rh/candidatos/{efetivo_id}/posto", headers=rh,
             json={"posto_id": pid, "cargo_funcao": "Assistente de RH"}
             ).status_code == 200
assert posto_nome in _texto_do_pdf(efetivo_id, "informativo_efetivo"), (
    "o Local de Trabalho do efetivo tem que sair do posto ao qual ele está "
    "alocado no cadastro, não de um texto fixo")

# ------------------------------------------------------------------------ 6
# O catálogo de documentos (v2.67: módulo que gera documento entra no catálogo
# na MESMA leva) — e a amostra tem que gerar de verdade, não só constar da lista.
r = c.get("/api/rh/documentos-sistema", headers=rh)
assert r.status_code == 200, r.text
chaves = {d["chave"] for d in r.json()}
assert "informativo_efetivo" in chaves, (
    "documento novo entra no catálogo de documentos na mesma leva — sem isso o "
    "RH não tem amostra nem download, e a metade cumprida parece cumprida")

r = c.get("/api/rh/documentos-sistema/informativo_efetivo/previa", headers=rh)
assert r.status_code == 200 and r.content[:4] == b"%PDF", (
    f"a amostra do informativo do efetivo tem que gerar PDF: {r.status_code}")

# ------------------------------------------------------------------------ 7
# O painel de liberação do RH (v1.92) tem que ENXERGAR o documento novo: as duas
# rotas leem a tupla DOCS_INFORMATIVO, e uma ficha que não aparece ali nunca
# seria disparada ao candidato — ficaria pendente para sempre, sem erro nenhum.
r = c.get(f"/api/rh/candidatos/{efetivo_id}/informativos", headers=rh)
assert r.status_code == 200, r.text
docs = {i["documento"]: i for i in r.json()}
assert "informativo_efetivo" in docs, (
    f"a ficha do efetivo tem que aparecer no painel de liberação: {r.json()}")
assert docs["informativo_efetivo"]["aguardando_liberacao"] is True

assert c.post(f"/api/rh/candidatos/{efetivo_id}/liberar-informativo",
              headers=rh).json()["liberados"] >= 1, "o RH tem que conseguir liberá-la"
r = c.get(f"/api/rh/candidatos/{efetivo_id}/informativos", headers=rh)
assert {i["documento"]: i for i in r.json()}["informativo_efetivo"][
    "aguardando_liberacao"] is False, "depois de liberar, vai ao candidato"

print("test_informativo_integracao: OK")
