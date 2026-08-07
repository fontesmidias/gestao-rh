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

# `setdefault`, não `update` (v2.72): o `update` SOBRESCREVIA a `DATABASE_URL`
# do ambiente, então o teste ignorava para onde o operador o estava apontando e
# ia sempre ao banco local — no CI (onde o Postgres é outro) isso o mandaria
# para um host que não existe. Todos os outros testes do projeto usam
# `setdefault` pelo mesmo motivo: o padrão serve a máquina de quem desenvolve,
# nunca decide pelo ambiente.
_PADROES = dict(
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
for _chave, _valor in _PADROES.items():
    os.environ.setdefault(_chave, _valor)

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


# --------------------------------------------------------------------------
# Por que os contadores da resposta NÃO servem de asserção (v2.72)
#
# `executar_processamento` varre `select(Talento).where(status != "arquivado")`
# — o BANCO INTEIRO, não os três talentos deste teste. As asserções originais
# eram `r1["analisados"] == 1`, que só valem em banco recém-criado: a 2ª
# execução no mesmo banco via os talentos que a 1ª deixou (medido: 156
# processados, 2 analisados) e falhava com uma mensagem que não fala da causa.
#
# Era a armadilha "só passa em banco limpo" (v2.14) num teste que a antecede, e
# deixou este arquivo VERMELHO desde antes da v2.64 — três relatórios seguidos o
# registraram como pendência.
#
# A correção é de RECORTE, não de garantia: conta-se o resultado dos três
# talentos do teste (`_meus`), que é exatamente o que cada asserção queria
# afirmar. O contador global vira contexto na mensagem de erro, nunca critério.
#
# ⚠️ NÃO troque isto por "apagar os talentos no fim": o teste morre no meio numa
# falha legítima e deixa o banco sujo do mesmo jeito — o problema volta pela
# porta dos fundos, e ainda por cima some com a evidência do que falhou.
# --------------------------------------------------------------------------

MEUS = {COM_CV, SEM_CV, ILEGIVEL}


def _meus(resposta):
    """Quantos dos MEUS três talentos caíram em cada resultado.

    Devolve um dict com as mesmas chaves da resposta do processamento, para as
    asserções permanecerem legíveis lado a lado com o que elas substituíram.
    """
    res = {t: r for t, r in _analises().items() if t in MEUS}
    conta = {
        "analisados": sum(1 for r in res.values() if r == ResultadoAnalise.analisado),
        "sem_curriculo": sum(1 for r in res.values()
                             if r == ResultadoAnalise.sem_curriculo),
        "ilegiveis": sum(1 for r in res.values()
                         if r == ResultadoAnalise.curriculo_ilegivel),
        "ia_indisponivel": sum(1 for r in res.values()
                               if r == ResultadoAnalise.ia_indisponivel),
    }
    # O total do banco entra só como CONTEXTO da mensagem de falha: ajuda a
    # entender o cenário sem virar critério de aprovação.
    conta["_global"] = resposta
    return conta


# ---------- 1ª rodada: analisa quem dá, e registra o MOTIVO dos demais ----------

chamadas = {"n": 0}


def _contando(s, u, **kw):
    chamadas["n"] += 1
    return _RESPOSTA_IA


r1 = _rodar(gerar=_contando)
m1 = _meus(r1)
assert m1["analisados"] == 1, m1
assert m1["sem_curriculo"] == 1, m1
assert m1["ilegiveis"] == 1, m1
# A IA foi chamada UMA vez POR TALENTO MEU analisável. Outros talentos do banco
# podem ter currículo indexado, então o total é `>= 1` — o que este teste
# garante é que o meu foi analisado, e as rodadas seguintes travam a repetição
# comparando com ESTE número, não com uma constante.
chamadas_apos_r1 = chamadas["n"]
assert chamadas_apos_r1 >= 1, chamadas

res = _analises()
assert res[COM_CV] == ResultadoAnalise.analisado
# ninguém some: sem currículo e ilegível ficam GRAVADOS com o motivo
assert res[SEM_CV] == ResultadoAnalise.sem_curriculo
assert res[ILEGIVEL] == ResultadoAnalise.curriculo_ilegivel

# ---------- 2ª rodada: REAPROVEITA — não chama a IA de novo ----------

r2 = _rodar(gerar=_contando)
m2 = _meus(r2)
# O reaproveitamento é o coração deste teste (foi a repetição do custo que
# estourou a cota em 2026-07-28): o meu talento continua `analisado` e a IA
# NÃO é chamada de novo por ninguém — nem por ele, nem pelos demais.
assert m2["analisados"] == 1, m2
assert r2["reaproveitados"] >= 1, r2
assert chamadas["n"] == chamadas_apos_r1, (
    f"a IA foi chamada de novo numa rodada que deveria só reaproveitar: "
    f"{chamadas_apos_r1} -> {chamadas['n']}")

# ---------- reanalisar=True: refaz, ATUALIZANDO (não viola a unique) ----------

r3 = _rodar(reanalisar=True, gerar=_contando)
m3 = _meus(r3)
assert m3["analisados"] == 1, m3
assert chamadas["n"] > chamadas_apos_r1, (
    f"reanalisar=True não refez a análise: {chamadas}")

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
m5 = _meus(r5)
assert m5["analisados"] == 1, f"não retomou quem ficou pendente: {m5}"
assert m5["ia_indisponivel"] == 0, (
    f"quem ficou como ia_indisponivel continuou parado: {m5}")

print("test_match_persistencia: OK")
