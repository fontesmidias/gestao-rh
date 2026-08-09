"""Documento específico avulso — o caso da COBERTURA (v2.79).

Feedback do Bruno (2026-08-07):

    "Um intermitente precisou dar cobertura na presidência da República. Não
     estava fácil marcar para emitir os documentos específicos da presidência.
     Como podemos melhorar isso? Bem como para outros documentos específicos."

O kit da Presidência sempre existiu (v1.17–v1.21) e sempre foi selecionável —
mas **por POSTO** (`PostoServico.documentos_kit`). Numa cobertura a pessoa
justamente NÃO está lotada no posto que exige o documento, e as duas saídas
eram ruins:

  · lotá-la no posto da Presidência — muda o VÍNCULO dela para emitir um papel;
  · marcar o kit no posto dela — passaria a exigir aquilo de TODO MUNDO ali.

Daí a rota nova: acrescenta UM documento a UMA pessoa, sem tocar em posto
nenhum. O documento nasce como qualquer outro do kit (`Assinatura` liberada) e
segue o fluxo normal — aparece para assinar, entra no dossiê, conta como
pendência.

O que este teste trava:

1. **A lista vem do MESMO catálogo do kit de posto**
   (`postos.DOCS_ESPECIFICOS_DISPONIVEIS`). Uma lista paralela divergiria na
   primeira mudança — é a lição do enum reescrito à mão (v2.69) e da cópia do
   layout no teste do Dexion (v2.54).
2. **Só o catálogo entra.** Aceitar qualquer valor de `DocumentoAssinavel`
   deixaria o RH acrescentar ficha de integração ou termo de VT por engano —
   documentos que o sistema decide sozinho, por REGIME e por POSTO, e que
   apareceriam duplicados.
3. **Motivo é obrigatório.** É ele que explica, meses depois, por que alguém
   lotado no posto X assinou o kit do posto Y. Sem motivo o registro fica sem a
   metade que importa (precedente do `reverter` da v1.65 e da troca de
   matrícula da v2.45). A auditoria guarda o motivo **e o posto da pessoa** —
   é o contraste que torna o registro verificável.
4. **Não duplica assinatura viva.** Reemitir apagaria o que a pessoa já
   assinou; o 409 diz se está pendente ou assinado, porque a tela precisa
   distinguir os dois casos.

Mutações verificadas:
  1. aceitar documento fora do catálogo        -> bloco 3 falha
  2. motivo deixa de ser obrigatório           -> bloco 4 falha
  3. não checar assinatura existente           -> bloco 5 falha
  4. `aguardando_liberacao=True` no nascimento -> bloco 2 falha

Precisa dos containers de teste.

Rode: PYTHONPATH=. .venv/Scripts/python.exe tests/test_documento_especifico.py
"""

import os
import uuid

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
from sqlalchemy import select  # noqa: E402

from app.api.postos import DOCS_ESPECIFICOS_DISPONIVEIS  # noqa: E402
from app.core.db import SessionLocal  # noqa: E402
from app.main import app  # noqa: E402
from app.models.assinatura import Assinatura, DocumentoAssinavel  # noqa: E402
from app.models.candidato import Candidato  # noqa: E402

c = TestClient(app)

EMAIL = os.environ["RH_ADMIN_EMAIL"]
SENHA = os.environ["RH_ADMIN_PASSWORD"]
r = c.post("/api/rh/auth/login", json={"email": EMAIL, "senha": SENHA})
assert r.status_code == 200, (
    f"login falhou ({r.status_code}): confira RH_ADMIN_EMAIL/RH_ADMIN_PASSWORD "
    f"— `criar_admin_inicial` só cria o admin com a tabela VAZIA. {r.text}")
RH = {"Authorization": f"Bearer {r.json()['token']}"}

SUF = uuid.uuid4().hex[:8]
falhas: list[str] = []

DOC = "oficio_apresentacao_presidencia"


def checar(cond, msg):
    if cond:
        print(f"  ok   {msg}")
    else:
        print(f"  FALHOU  {msg}")
        falhas.append(msg)


def novo_candidato():
    """Cria direto pelo ORM: a rota de convite dispara e-mail e link mágico, que
    não têm nada a ver com o que se testa aqui."""
    with SessionLocal() as db:
        cand = Candidato(nome_completo=f"Cobertura {SUF}-{uuid.uuid4().hex[:4]}",
                         email=f"cob-{uuid.uuid4().hex[:8]}@exemplo.com",
                         cargo_funcao="Garçonete")
        db.add(cand)
        db.commit()
        return str(cand.id)


# --------------------------------------------------------------------------
print("\n1. a lista vem do MESMO catálogo do kit de posto")
# --------------------------------------------------------------------------
cid = novo_candidato()
r = c.get(f"/api/rh/candidatos/{cid}/documentos-especificos", headers=RH)
checar(r.status_code == 200, f"GET responde 200 ({r.status_code})")
chaves = {d["chave"] for d in r.json()["disponiveis"]}
checar(chaves == set(DOCS_ESPECIFICOS_DISPONIVEIS),
       f"as chaves são EXATAMENTE as do catálogo do posto — lista paralela "
       f"divergiria na 1ª mudança (veio {sorted(chaves)})")
checar(all(d["ja_tem"] is False for d in r.json()["disponiveis"]),
       "candidato novo não tem nenhum deles")
checar(any("Presidência" in d["rotulo"] for d in r.json()["disponiveis"]),
       "o kit da Presidência está entre os oferecidos (era o caso do Bruno)")

# --------------------------------------------------------------------------
print("\n2. acrescentar cria a assinatura LIBERADA, sem tocar no posto")
# --------------------------------------------------------------------------
# ⚠️ Mutação 4: nascer com `aguardando_liberacao=True` -> a 3ª asserção falha.
# Só o informativo de integração nasce bloqueado (v1.92); este é documento de
# kit, e segurar sua liberação faria o RH procurar um botão que não existe.
r = c.post(f"/api/rh/candidatos/{cid}/documento-especifico", headers=RH,
           json={"documento": DOC, "motivo": "Cobertura na Presidência em 08/08"})
checar(r.status_code == 200, f"POST responde 200 ({r.status_code} {r.text[:80]})")
checar("Presidência" in (r.json().get("rotulo") or ""),
       "a resposta devolve o rótulo legível (a tela mostra isso)")

with SessionLocal() as db:
    a = db.scalar(select(Assinatura).where(
        Assinatura.candidato_id == uuid.UUID(cid),
        Assinatura.documento == DocumentoAssinavel(DOC)))
    checar(a is not None, "a Assinatura foi criada no banco")
    checar(a is not None and a.aguardando_liberacao is False,
           "nasce LIBERADA — documento de kit não espera liberação do RH")
    cand = db.get(Candidato, uuid.UUID(cid))
    checar(cand.posto_servico_id is None,
           "o POSTO da pessoa continua intacto (é o ponto da leva: cobertura "
           "não muda vínculo)")

r = c.get(f"/api/rh/candidatos/{cid}/documentos-especificos", headers=RH)
checar([d for d in r.json()["disponiveis"] if d["chave"] == DOC][0]["ja_tem"] is True,
       "a listagem passa a marcar `ja_tem` — a tela não oferece o que já existe")

# --------------------------------------------------------------------------
print("\n3. SÓ o catálogo entra")
# --------------------------------------------------------------------------
# ⚠️ Mutação 1: aceitar qualquer valor do enum -> estas asserções falham.
#
# `termo_vt` e as fichas de integração são decididos pelo SISTEMA (por regime,
# por posto). Deixar o RH acrescentá-los à mão criaria duplicata do que o
# `gerar_docs_do_posto_e_regime` já cria — e, no caso do VT, um segundo termo
# de desconto de 6% em folha.
outro = novo_candidato()
# ⚠️ `raise_server_exceptions=False` (lição da v2.72.2): a mutação que remove a
# checagem faz a rota estourar `KeyError` no dicionário de rótulos, e o
# `TestClient` REPROPAGA a exceção do servidor — o script morreria aqui, sem
# imprimir nenhum "FALHOU", e a saída sem falhas passaria por aprovação. Com a
# flag, o 500 vira resposta e a asserção pode reprová-lo.
tolerante = TestClient(app, raise_server_exceptions=False)
for proibido in ("termo_vt", "ficha_cadastro", "informativo_efetivo"):
    r = tolerante.post(f"/api/rh/candidatos/{outro}/documento-especifico", headers=RH,
                       json={"documento": proibido, "motivo": "tentativa"})
    checar(r.status_code == 422,
           f"`{proibido}` é recusado com 422, não aceito nem 500 (veio {r.status_code})")

r = tolerante.post(f"/api/rh/candidatos/{outro}/documento-especifico", headers=RH,
                   json={"documento": "coisa_que_nao_existe", "motivo": "x"})
checar(r.status_code == 422, f"chave inexistente é recusada com 422 (veio {r.status_code})")

# --------------------------------------------------------------------------
print("\n4. MOTIVO é obrigatório — e vai para a auditoria com o posto")
# --------------------------------------------------------------------------
# ⚠️ Mutação 2: aceitar motivo vazio -> as 2 primeiras asserções falham.
for vazio in ("", "   "):
    r = c.post(f"/api/rh/candidatos/{outro}/documento-especifico", headers=RH,
               json={"documento": DOC, "motivo": vazio})
    checar(r.status_code == 422,
           f"motivo {vazio!r} é recusado — sem ele o registro não explica nada")

MOTIVO = f"Cobertura Presidência {SUF}"
r = c.post(f"/api/rh/candidatos/{outro}/documento-especifico", headers=RH,
           json={"documento": DOC, "motivo": MOTIVO})
checar(r.status_code == 200, "com motivo, entra")

from app.models.evento import EventoAuditoria  # noqa: E402

with SessionLocal() as db:
    ev = db.scalar(select(EventoAuditoria).where(
        EventoAuditoria.acao == "documento_especifico_acrescentado",
        EventoAuditoria.candidato_id == uuid.UUID(outro)))
    checar(ev is not None, "o ato fica na auditoria")
    det = (ev.detalhe or {}) if ev is not None else {}
    checar(det.get("motivo") == MOTIVO,
           f"o MOTIVO é gravado como escrito ({det.get('motivo')!r})")
    checar("posto_da_pessoa" in det,
           "e o POSTO DA PESSOA junto — é o contraste que torna o registro "
           "verificável ('lotada em X, assinou o kit de Y')")

# --------------------------------------------------------------------------
print("\n5. não duplica assinatura viva")
# --------------------------------------------------------------------------
# ⚠️ Mutação 3: remover a checagem -> estas asserções falham.
#
# Reemitir apagaria o que a pessoa já assinou. O 409 diz se está PENDENTE ou
# ASSINADO porque a tela precisa distinguir — "já está pendente" pede paciência;
# "já está assinado" pede o caminho de invalidar.
r = c.post(f"/api/rh/candidatos/{cid}/documento-especifico", headers=RH,
           json={"documento": DOC, "motivo": "de novo"})
checar(r.status_code == 409, f"o mesmo documento de novo dá 409 ({r.status_code})")
d = (r.json() or {}).get("detail") or {}
checar(isinstance(d, dict) and d.get("erro") == "documento_ja_existe",
       "o erro é estruturado (a tela monta a mensagem com ele)")
checar("assinado" in d, "e diz se já foi ASSINADO ou só está pendente")

with SessionLocal() as db:
    quantas = len(list(db.scalars(select(Assinatura).where(
        Assinatura.candidato_id == uuid.UUID(cid),
        Assinatura.documento == DocumentoAssinavel(DOC)))))
checar(quantas == 1, f"continua UMA assinatura no banco ({quantas})")

# --------------------------------------------------------------------------
print("\n6. a rota é do RH")
# --------------------------------------------------------------------------
checar(c.get(f"/api/rh/candidatos/{cid}/documentos-especificos").status_code
       in (401, 403), "GET sem token é recusado")
checar(c.post(f"/api/rh/candidatos/{cid}/documento-especifico",
              json={"documento": DOC, "motivo": "x"}).status_code in (401, 403),
       "POST sem token é recusado")
checar(c.get(f"/api/rh/candidatos/{uuid.uuid4()}/documentos-especificos",
             headers=RH).status_code == 404,
       "candidato inexistente dá 404")


print()
if falhas:
    print(f"test_documento_especifico: {len(falhas)} FALHA(S)")
    for f_ in falhas:
        print(f"  - {f_}")
    raise SystemExit(1)
print("test_documento_especifico: OK")
