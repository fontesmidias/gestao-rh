"""Teste do ranqueamento persistido e assíncrono (v2.00) — precisa dos
containers efêmeros.

Cobre as correções do incidente de 2026-07-28 (131 talentos → 18 analisados,
depois 2):

1. **Reaproveitamento**: clicar em "Ranquear" de novo NÃO chama a IA de novo.
   Era a repetição do custo que estourava a cota.
2. **`reanalisar=True`** refaz a análise ATUALIZANDO o registro existente —
   há UNIQUE(vaga_id, talento_id), então reinserir violaria a constraint
   (bug encontrado por este teste antes de ir ao ar).
3. **Cota estourada não faz ninguém sumir**: quem não deu para analisar fica
   gravado como `ia_indisponivel`, para ser retomado depois.
4. **Ninguém some em silêncio**: sem currículo e currículo ilegível viram
   resultado explícito, não ausência.

Rode: PYTHONPATH=. .venv/Scripts/python.exe tests/test_match_persistencia.py
"""

import os

os.environ.update(
    DATABASE_URL="postgresql+psycopg://admissao:admissao@localhost:55432/admissao",
    MINIO_ENDPOINT="localhost:59000",
    MINIO_ACCESS_KEY="minio",
    MINIO_SECRET_KEY="minio12345",
    MINIO_SECURE="false",
    RH_ADMIN_EMAIL="rh@greenhousedf.com.br",
    RH_ADMIN_PASSWORD="senha-teste-123",
    SECRET_KEY="segredo-de-teste",
    BASE_URL="http://localhost:8090",
)

import uuid
from unittest.mock import patch

from sqlalchemy import select

from app.main import app  # noqa: F401 — registra todos os modelos (resolve FKs)
from app.core.db import SessionLocal
from app.models.match import (AnaliseTalento, CurriculoTexto, ProcessamentoMatch,
                              ResultadoAnalise, StatusProcessamento)
from app.models.talento import Talento
from app.models.vaga import Vaga
from app.services import match_vagas
from app.services.ia_texto import CotaExcedidaError

_SUFIXO = uuid.uuid4().hex[:8]
_RESPOSTA_IA = ('{"nota": 82, "atende_obrigatorios": true, '
                '"justificativa": "5 anos na função."}')


def _preparar():
    """Cria vaga + 3 talentos: um com currículo legível, um sem currículo, e
    um com currículo ilegível."""
    with SessionLocal() as db:
        vaga = Vaga(titulo=f"Vaga persistencia {_SUFIXO}", descricao="d", cargo="Porteiro")
        db.add(vaga)

        com_cv = Talento(nome=f"Com CV {_SUFIXO}", cargos_interesse=["Porteiro"],
                         cargo_interesse="Porteiro",
                         curriculo_key=f"talentos/{_SUFIXO}/curriculo.pdf",
                         curriculo_nome="curriculo.pdf")
        sem_cv = Talento(nome=f"Sem CV {_SUFIXO}", cargos_interesse=["Porteiro"],
                         cargo_interesse="Porteiro")
        ilegivel = Talento(nome=f"Ilegivel {_SUFIXO}", cargos_interesse=["Porteiro"],
                           cargo_interesse="Porteiro",
                           curriculo_key=f"talentos/{_SUFIXO}/foto.heic",
                           curriculo_nome="foto.heic")
        db.add_all([com_cv, sem_cv, ilegivel])
        db.flush()

        db.add(CurriculoTexto(talento_id=com_cv.id, curriculo_key=com_cv.curriculo_key,
                              texto="Experiencia de 5 anos como porteiro.",
                              legivel=True, caracteres=36))
        db.add(CurriculoTexto(talento_id=ilegivel.id, curriculo_key=ilegivel.curriculo_key,
                              texto=None, legivel=False,
                              motivo_falha="nao_foi_possivel_ler_heic", caracteres=0))
        db.commit()
        return vaga.id, com_cv.id, sem_cv.id, ilegivel.id


VAGA_ID, COM_CV, SEM_CV, ILEGIVEL = _preparar()


def _rodar(reanalisar=False, gerar=None):
    with SessionLocal() as db:
        p = ProcessamentoMatch(vaga_id=VAGA_ID)
        db.add(p)
        db.commit()
        pid = p.id
    alvo = gerar or (lambda s, u, **kw: _RESPOSTA_IA)
    with patch.object(match_vagas, "gerar_json", alvo):
        return match_vagas.executar_processamento(pid, reanalisar=reanalisar)


def _analises():
    with SessionLocal() as db:
        return {a.talento_id: a.resultado for a in db.scalars(
            select(AnaliseTalento).where(AnaliseTalento.vaga_id == VAGA_ID))}


# ---------- 1ª rodada: analisa quem dá, e registra o MOTIVO dos demais ----------

chamadas = {"n": 0}


def _contando(s, u, **kw):
    chamadas["n"] += 1
    return _RESPOSTA_IA


r1 = _rodar(gerar=_contando)
assert r1["analisados"] == 1, r1
assert r1["sem_curriculo"] == 1, r1
assert r1["ilegiveis"] == 1, r1
assert chamadas["n"] == 1, chamadas

res = _analises()
assert res[COM_CV] == ResultadoAnalise.analisado
# ninguém some: sem currículo e ilegível ficam GRAVADOS com o motivo
assert res[SEM_CV] == ResultadoAnalise.sem_curriculo
assert res[ILEGIVEL] == ResultadoAnalise.curriculo_ilegivel

# ---------- 2ª rodada: REAPROVEITA — não chama a IA de novo ----------

r2 = _rodar(gerar=_contando)
assert r2["reaproveitados"] == 1, r2
assert r2["analisados"] == 0, r2
assert chamadas["n"] == 1, f"a IA foi chamada de novo: {chamadas}"

# ---------- reanalisar=True: refaz, ATUALIZANDO (não viola a unique) ----------

r3 = _rodar(reanalisar=True, gerar=_contando)
assert r3["analisados"] == 1, r3
assert r3["reaproveitados"] == 0, r3
assert chamadas["n"] == 2, chamadas

with SessionLocal() as db:
    quantas = len(list(db.scalars(select(AnaliseTalento).where(
        AnaliseTalento.vaga_id == VAGA_ID, AnaliseTalento.talento_id == COM_CV))))
assert quantas == 1, f"reanalisar duplicou a análise ({quantas} registros)"

# ---------- Cota estourada: ninguém some, fica marcado para retomar ----------

def _estoura_cota(s, u, **kw):
    raise CotaExcedidaError("cota_excedida", espera_s=30)


r4 = _rodar(reanalisar=True, gerar=_estoura_cota)
res4 = _analises()
assert res4[COM_CV] == ResultadoAnalise.ia_indisponivel, res4
with SessionLocal() as db:
    proc = db.scalar(select(ProcessamentoMatch)
                     .where(ProcessamentoMatch.vaga_id == VAGA_ID)
                     .order_by(ProcessamentoMatch.criado_em.desc()).limit(1))
    # mensagem HONESTA sobre cota (a antiga dizia só "IA indisponível", e o
    # RH clicava de novo achando que tinha caído — piorando o resultado)
    assert proc.observacao and "limite de uso" in proc.observacao.lower(), proc.observacao
    assert proc.status in (StatusProcessamento.concluido,
                           StatusProcessamento.concluido_sem_ia), proc.status

# ---------- Depois da cota voltar, a próxima rodada retoma quem ficou ----------

r5 = _rodar(gerar=_contando)
assert r5["analisados"] == 1, f"não retomou quem ficou pendente: {r5}"

print("test_match_persistencia: OK")
