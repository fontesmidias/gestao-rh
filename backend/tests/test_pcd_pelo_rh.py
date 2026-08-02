"""O RH registra o PCD e o laudo tem como chegar (v2.43).

Feedback do Bruno em 2026-08-01: *"um colaborador é PCD e não veio as
informações na ficha cadastral e também a documentação"*. Perguntado, ele
esclareceu: **a pessoa passou pela admissão e NÃO marcou** — PCD é dado de
saúde (art. 11 da LGPD) e muita gente evita declarar; ela contou ao RH por
fora.

O RH sempre pôde marcar `pcd` na ficha. O problema estava um passo adiante: ao
marcar, o LAUDO vira documento obrigatório — e se a pessoa já concluiu o envio
ou foi aprovada, o checklist dela está congelado. O RH fazia a coisa certa e
ganhava uma pendência que ninguém no mundo conseguia resolver.

O que este teste protege:

1. **Marcar PCD depois da conclusão pede o laudo automaticamente**, liberado
   para aquela pessoa enviar.
2. **A liberação vale para AQUELE slot e mais nada** — o resto do checklist
   continua congelado. É a mesma disciplina da reabertura cirúrgica de
   2026-07-24: não desfaz dossiê nem efetivação.
3. **Quem já enviou o laudo não é incomodado** — o documento está lá; foi a
   ficha que demorou a refletir isso.
4. **Com o checklist ABERTO nada é liberado**: o slot aparece sozinho pela
   sincronização normal, e liberar à toa marcaria como "pedido pelo RH" algo
   que é fluxo comum.
5. **Fica na auditoria** com quem pediu — é dado de saúde registrado por
   terceiro sobre alguém.

Rode: PYTHONPATH=. .venv/Scripts/python.exe tests/test_pcd_pelo_rh.py
"""

import io
import os
import uuid

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
from PIL import Image, ImageDraw  # noqa: E402
from sqlalchemy import select  # noqa: E402

from app.core.db import SessionLocal  # noqa: E402
from app.main import app  # noqa: E402
from app.models.candidato import Candidato  # noqa: E402
from app.models.documento import SlotDocumento, StatusSlot, TipoDocumento  # noqa: E402
from app.models.evento import EventoAuditoria  # noqa: E402

FALHAS = []


def checar(condicao, descricao):
    print(("  ok   " if condicao else "  FALHA ") + descricao)
    if not condicao:
        FALHAS.append(descricao)


def _nitida() -> bytes:
    im = Image.new("RGB", (900, 1200), "white")
    dr = ImageDraw.Draw(im)
    for i in range(28):
        dr.text((40, 30 + i * 40), f"LAUDO MEDICO CID H54 LINHA {i}", fill="black")
    b = io.BytesIO()
    im.save(b, "JPEG")
    return b.getvalue()


c = TestClient(app)
H = {"Authorization": f"Bearer {c.post('/api/rh/auth/login', json={'email': 'rh@greenhousedf.com.br', 'senha': 'senha-teste-123'}).json()['token']}"}
suf = uuid.uuid4().hex[:8]
jid = c.post("/api/rh/jornadas", headers=H,
             json={"descricao": f"PCD TESTE {suf}"}).json()["id"]


def _candidato_que_concluiu() -> tuple[str, str]:
    """Cria alguém, envia todos os obrigatórios e conclui. (id, token)."""
    r = c.post("/api/rh/candidatos", headers=H, json={
        "nome_completo": f"Pessoa PCD {suf}", "email": f"pcd{suf}@example.com",
        "celular_whatsapp": "+5561999994444", "jornada_id": jid,
        "cargo_funcao": "Auxiliar de Serviços Gerais", "registra_ponto": True})
    cid, tok = r.json()["candidato"]["id"], r.json()["link_magico"].rsplit("/c/", 1)[1]
    c.post(f"/api/c/{tok}/aceite", json={"aceite_lgpd": True})
    for s in c.get(f"/api/c/{tok}/documentos").json()["slots"]:
        if s["obrigatorio"] and s["status"] == "pendente":
            c.post(f"/api/c/{tok}/documentos/{s['id']}/arquivo",
                   files={"arquivo": ("d.jpg", _nitida(), "image/jpeg")})
    assert c.post(f"/api/c/{tok}/concluir-envio").status_code == 200
    return cid, tok


# ============ 1. marcar PCD depois da conclusão pede o laudo sozinho
print("\n[o RH marca PCD de quem já concluiu]")
cid, tok = _candidato_que_concluiu()
antes = [s for s in c.get(f"/api/c/{tok}/documentos").json()["slots"]
         if s["tipo"] == "laudo_pcd"]
checar(not antes, "quem não declarou não tinha o slot do laudo")

r = c.put(f"/api/rh/candidatos/{cid}/ficha/pessoais", headers=H,
          json={"motivo": "informado presencialmente pelo colaborador",
                "dados": {"pcd": True}})
checar(r.status_code == 200, f"o RH consegue marcar ({r.status_code}) {r.text[:120]}")
checar(r.json().get("laudo_pcd_pedido") is True,
       "e a resposta AVISA que o laudo foi pedido — senão um documento novo "
       "aparece na lista da pessoa e ninguém sabe por quê")

slots = c.get(f"/api/c/{tok}/documentos").json()["slots"]
laudo = next((s for s in slots if s["tipo"] == "laudo_pcd"), None)
checar(laudo is not None, "o laudo aparece no checklist dela")
checar(laudo and laudo["pedido_pelo_rh"] is True,
       "marcado como PEDIDO PELO RH, para a tela explicar de onde ele saiu")

# ============================== 2. ela consegue enviar SÓ aquele documento
print("\n[ela envia o laudo, e só ele]")
r = c.post(f"/api/c/{tok}/documentos/{laudo['id']}/arquivo",
           files={"arquivo": ("laudo.jpg", _nitida(), "image/jpeg")})
checar(r.status_code == 200,
       f"o envio do laudo é aceito mesmo com a admissão concluída ({r.status_code})")

outro = next(s for s in slots if s["tipo"] != "laudo_pcd" and s["status"] == "enviado")
r = c.post(f"/api/c/{tok}/documentos/{outro['id']}/arquivo",
           files={"arquivo": ("x.jpg", _nitida(), "image/jpeg")})
checar(r.status_code == 409 and r.json()["detail"] == "envio_ja_concluido",
       f"e o RESTO continua congelado ({r.status_code}) — liberar um documento "
       "não pode reabrir a admissão inteira")

print("\n[fica registrado quem pediu]")
with SessionLocal() as db:
    ev = db.scalars(select(EventoAuditoria).where(
        EventoAuditoria.acao == "documento_pedido_ao_candidato",
        EventoAuditoria.candidato_id == uuid.UUID(cid))).all()
    checar(len(ev) == 1, f"um evento de auditoria ({len(ev)})")
    checar(ev and ev[0].ator_detalhe == "rh@greenhousedf.com.br",
           "com o e-mail de quem pediu — é dado de saúde registrado por "
           "terceiro sobre alguém")
    slot_db = db.scalar(select(SlotDocumento).where(
        SlotDocumento.candidato_id == uuid.UUID(cid),
        SlotDocumento.tipo == TipoDocumento.laudo_pcd))
    checar(slot_db is not None and slot_db.liberado_por == "rh@greenhousedf.com.br",
           "e o próprio slot guarda quem abriu a porta")

# ================= 3. quem já enviou o laudo não é incomodado de novo
print("\n[quem já enviou não é incomodado]")
r = c.put(f"/api/rh/candidatos/{cid}/ficha/pessoais", headers=H,
          json={"motivo": "confirmando o registro", "dados": {"pcd_tipo": "visual"}})
checar(r.status_code == 200 and not r.json().get("laudo_pcd_pedido"),
       "editar outro campo do PCD não pede o laudo de novo")

# ==================== 4. com o checklist ABERTO, nada é liberado à toa
print("\n[com o checklist aberto, o fluxo normal basta]")
r = c.post("/api/rh/candidatos", headers=H, json={
    "nome_completo": f"Ainda Preenchendo {suf}", "email": f"abre{suf}@example.com",
    "celular_whatsapp": "+5561999993333", "jornada_id": jid,
    "cargo_funcao": "Auxiliar de Serviços Gerais", "registra_ponto": True})
cid2, tok2 = r.json()["candidato"]["id"], r.json()["link_magico"].rsplit("/c/", 1)[1]
c.post(f"/api/c/{tok2}/aceite", json={"aceite_lgpd": True})
r = c.put(f"/api/rh/candidatos/{cid2}/ficha/pessoais", headers=H,
          json={"motivo": "informado na entrevista", "dados": {"pcd": True}})
checar(r.status_code == 200 and not r.json().get("laudo_pcd_pedido"),
       "nada é 'pedido' — o checklist está aberto e o slot aparece sozinho")
laudo2 = next((s for s in c.get(f"/api/c/{tok2}/documentos").json()["slots"]
               if s["tipo"] == "laudo_pcd"), None)
checar(laudo2 is not None and laudo2["pedido_pelo_rh"] is False,
       "o slot existe pelo fluxo normal, sem a etiqueta de pedido especial")

# ===================================== 5. a rota genérica de pedir documento
print("\n[pedir qualquer documento depois]")
r = c.post(f"/api/rh/candidatos/{cid}/pedir-documento", headers=H,
           json={"tipo": "comp_escolaridade", "motivo": "faltou o histórico"})
checar(r.status_code == 200, f"o RH pede um documento avulso ({r.status_code})")
novo = next(s for s in c.get(f"/api/c/{tok}/documentos").json()["slots"]
            if s["tipo"] == "comp_escolaridade")
checar(novo["pedido_pelo_rh"] is True, "que chega à pessoa marcado como pedido")
r = c.post(f"/api/c/{tok}/documentos/{novo['id']}/arquivo",
           files={"arquivo": ("h.jpg", _nitida(), "image/jpeg")})
checar(r.status_code == 200, f"e ela consegue enviar ({r.status_code})")

r = c.post(f"/api/rh/candidatos/{cid}/pedir-documento", headers=H,
           json={"tipo": "comp_escolaridade"})
checar(r.status_code == 409 and r.json()["detail"] == "documento_ja_enviado",
       "pedir de novo o que já foi enviado é recusado — apagaria o que o RH "
       "talvez ainda nem tenha olhado")
r = c.post(f"/api/rh/candidatos/{cid}/pedir-documento", headers=H,
           json={"tipo": "nao_existe"})
checar(r.status_code == 422, "tipo desconhecido é recusado")

print()
if FALHAS:
    print(f"test_pcd_pelo_rh: {len(FALHAS)} FALHA(S)")
    for f in FALHAS:
        print(f"  - {f}")
    raise SystemExit(1)
print("test_pcd_pelo_rh: OK")
