"""Arquivamento automatico de entrevistas aos 180 dias (v2.64, fase 2).

ARQUIVA, NAO APAGA (decisao do Bruno). O julgamento vencido sai da vista e das
metricas; o registro continua existindo e consultavel. Este teste existe para
que a troca de `arquivar` por `delete` seja REPROVADA - mutacao verificada.

Cobre tambem o cenario 14: entrevista de quem virou COLABORADOR nao e arquivada
por prazo, porque e parte do vinculo, nao material de recrutamento com validade.

Rode: PYTHONPATH=. .venv/Scripts/python.exe tests/test_entrevista_arquivamento.py
"""

import os
import uuid
from datetime import datetime, timedelta, timezone

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

from app.core.db import SessionLocal  # noqa: E402
from app.models.candidato import Candidato  # noqa: E402
from app.models.entrevista import Entrevista, StatusEntrevista  # noqa: E402
from app.models.talento import Talento  # noqa: E402
# `Entrevista` tem FK para `usuario_rh` e `vaga`; sem importar esses modelos, as
# tabelas nao entram no metadata e o SQLAlchemy nao resolve a FK
# (NoReferencedTableError no primeiro flush). Importar modelo que so aparece
# como ALVO de FK e requisito, nao enfeite.
from app.models.usuario_rh import UsuarioRH  # noqa: E402,F401
from app.models.vaga import Vaga  # noqa: E402,F401
from app.workers.expurgo import arquivar_entrevistas  # noqa: E402

SUF = uuid.uuid4().hex[:8]
falhas = []


def checar(cond, msg):
    if cond:
        print(f"  ok   {msg}")
    else:
        print(f"  FALHOU  {msg}")
        falhas.append(msg)


agora = datetime.now(timezone.utc)
antiga = agora - timedelta(days=200)     # passou dos 180
recente = agora - timedelta(days=10)     # dentro do prazo

with SessionLocal() as db:
    # Talento comum: entrevista ANTIGA -> deve ser arquivada.
    t_velho = Talento(nome=f"Velho {SUF}", email=f"velho-{SUF}@x.com",
                      consentimento_lgpd_em=agora)
    # Talento comum: entrevista RECENTE -> NAO deve ser tocada.
    t_novo = Talento(nome=f"Novo {SUF}", email=f"novo-{SUF}@x.com",
                     consentimento_lgpd_em=agora)
    db.add_all([t_velho, t_novo])

    # Colaborador ATIVO com entrevista antiga -> cenario 14, fica de fora.
    colab = Candidato(nome_completo=f"Colaborador {SUF}", situacao="ativo")
    db.add(colab)
    db.flush()

    e_antiga = Entrevista(talento_id=t_velho.id, tipo="entrevista",
                          status=StatusEntrevista.realizada,
                          realizada_em=antiga, entrevistador_nome="RH Teste")
    e_recente = Entrevista(talento_id=t_novo.id, tipo="entrevista",
                           status=StatusEntrevista.realizada,
                           realizada_em=recente, entrevistador_nome="RH Teste")
    e_colab = Entrevista(candidato_id=colab.id, tipo="entrevista",
                         status=StatusEntrevista.realizada,
                         realizada_em=antiga, entrevistador_nome="RH Teste")
    db.add_all([e_antiga, e_recente, e_colab])
    db.commit()
    id_antiga, id_recente, id_colab = e_antiga.id, e_recente.id, e_colab.id

print("\n1. O worker arquiva o que passou do prazo")
n = arquivar_entrevistas()
checar(n >= 1, f"o worker arquivou pelo menos 1 entrevista (n={n})")

with SessionLocal() as db:
    a = db.get(Entrevista, id_antiga)
    r = db.get(Entrevista, id_recente)
    col = db.get(Entrevista, id_colab)

    # O ponto central: ARQUIVA, NAO APAGA.
    # Mutacao verificada: trocar `e.status = arquivada` por `db.delete(e)` ->
    # `a is None` e este bloco falha.
    checar(a is not None,
           "a entrevista antiga CONTINUA EXISTINDO no banco (arquivar != apagar)")
    checar(a is not None and a.status == StatusEntrevista.arquivada,
           "e seu status virou `arquivada`")
    checar(a is not None and a.arquivada_em is not None,
           "com a data de arquivamento carimbada")

    checar(r is not None and r.status == StatusEntrevista.realizada,
           "a entrevista RECENTE nao foi tocada (dentro do prazo)")

    # Cenario 14: quem virou colaborador fica fora do prazo.
    checar(col is not None and col.status == StatusEntrevista.realizada,
           "a entrevista de COLABORADOR nao e arquivada por prazo "
           "(e parte do vinculo, nao material de recrutamento)")

print("\n2. Retencao 0 = indeterminado: nada e arquivado")
# Mutacao verificada: trocar `if dias <= 0` por `if dias is not None` ->
# "guardar para sempre" viraria "arquivar tudo hoje", em silencio.
from app.services.config_dinamica import gravar_config  # noqa: E402

with SessionLocal() as db:
    t_zero = Talento(nome=f"Zero {SUF}", email=f"zero-{SUF}@x.com",
                     consentimento_lgpd_em=agora)
    db.add(t_zero)
    db.flush()
    e_zero = Entrevista(talento_id=t_zero.id, tipo="entrevista",
                        status=StatusEntrevista.realizada,
                        realizada_em=antiga, entrevistador_nome="RH Teste")
    db.add(e_zero)
    db.commit()
    id_zero = e_zero.id

with SessionLocal() as db:
    gravar_config(db, {"entrevistas_retencao_dias": "0"})
    db.commit()
try:
    n0 = arquivar_entrevistas()
    checar(n0 == 0, f"com retencao 0, nada e arquivado (n={n0})")
    with SessionLocal() as db:
        z = db.get(Entrevista, id_zero)
        checar(z is not None and z.status == StatusEntrevista.realizada,
               "e a entrevista antiga continua intacta")
finally:
    # devolve o padrao para nao contaminar as proximas execucoes
    with SessionLocal() as db:
        gravar_config(db, {"entrevistas_retencao_dias": ""})
        db.commit()

print()
if falhas:
    print(f"test_entrevista_arquivamento: {len(falhas)} FALHA(S)")
    for f_ in falhas:
        print(f"  - {f_}")
    raise SystemExit(1)
print("test_entrevista_arquivamento: OK")
