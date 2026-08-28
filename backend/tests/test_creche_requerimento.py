"""Disparo e gerenciamento do requerimento de creche (v3.16).

Defeito de campo de 26/08/2026, relatado pelo Bruno: *"nos que foram aprovados
e ativados, não chegou para esse pessoal automaticamente o processo de
assinar"*. O roteiro EXISTIA no banco; quem mentia era a consulta.

`tem_roteiro(db, candidato_id)` sem filtro devolve o roteiro mais RECENTE de
qualquer documento da pessoa, ordenado por `criado_em desc`. Quem foi efetivado
tem roteiros de admissão — e assim que um deles ficava mais novo que o do
creche, `_etapa_colaborador` comparava a origem, reprovava, e a sessão do
colaborador respondia `disponivel: false` **com o requerimento pronto ao lado**.
Nada dava erro: a tela do RH dizia "ativo", a do colaborador não mostrava botão
nenhum, e o log registrava um 200.

O que se garante aqui, e por quê:

1. **A consulta filtra a ORIGEM no SQL.** É o defeito acima. Sem isso o roteiro
   de admissão sequestra a resposta do creche.
2. **`criar_roteiro_creche` é idempotente por ORIGEM.** Antes ele comparava a
   origem do roteiro mais recente e, quando ela não batia, caía para criar um
   SEGUNDO roteiro de creche — o colaborador assinaria um e o RH o outro.
3. **A ficha do RH ACUSA o pendente.** Estado que ninguém vê equivale a não
   existir: era exatamente por não aparecer que o defeito durou.
4. **Só o benefício ATIVO dispara.** Disparar num `aguardando_repactuacao`
   mandaria assinar documento cujo valor ainda vai mudar — e a recusa oferece
   a saída, em vez de só bloquear (v2.93).
5. **O lote presta contas.** Lote que só diz "pronto" faz o RH acreditar que
   resolveu o que não resolveu (v2.14).

Precisa de banco e MinIO. Roda no CI dentro do container da API.
"""
import os
import sys
import uuid as _uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault(
    "DATABASE_URL", "postgresql+psycopg://admissao:admissao@localhost:55432/admissao")
os.environ.setdefault("SECRET_KEY", "teste")
os.environ.setdefault("MINIO_ENDPOINT", "localhost:59000")
os.environ.setdefault("MINIO_ACCESS_KEY", "minio")
os.environ.setdefault("MINIO_SECRET_KEY", "minio12345")

from fastapi.testclient import TestClient  # noqa: E402

from app.api.auth_rh import requer_rh  # noqa: E402
from app.core.db import SessionLocal  # noqa: E402
from app.main import app  # noqa: E402
from app.models.beneficio import BeneficioCreche, CriancaCreche  # noqa: E402
from app.models.beneficio import StatusBeneficio  # noqa: E402
from app.models.candidato import Candidato, PostoServico  # noqa: E402
from app.models.solicitacao_assinatura import (SolicitacaoAssinatura,  # noqa: E402
                                               StatusSolicitacao)
from app.models.usuario_rh import UsuarioRH  # noqa: E402
from app.services.roteiro_assinatura import (ORIGEM_CRECHE,  # noqa: E402
                                             criar_roteiro_creche, tem_roteiro)

FALHAS = []
db = SessionLocal()

# O usuário do RH precisa existir DE VERDADE no banco: a etapa 2 do roteiro tem
# FK para `usuario_rh`, e um objeto solto estouraria no flush.
_RH = db.scalar(
    __import__("sqlalchemy").select(UsuarioRH).limit(1))
if _RH is None:
    _RH = UsuarioRH(email=f"rh-{_uuid.uuid4().hex[:8]}@teste.com", nome="RH Teste",
                    senha_hash="x", papel="superadmin")
    db.add(_RH)
    db.commit()
app.dependency_overrides[requer_rh] = lambda: _RH
# `raise_server_exceptions=False`: sem isto um 500 sobe como exceção e mata o
# script no meio — a saída fica vazia e passa por sucesso (v2.72.2).
cli = TestClient(app, raise_server_exceptions=False)


def _reportar(texto: str) -> None:
    """Emoji em mensagem de falha quebra o console do Windows (cp1252) e o
    script morre ANTES de mostrar a causa — justamente quando ela importa
    (v3.15)."""
    try:
        print(texto)
    except UnicodeEncodeError:
        print(texto.encode("ascii", "replace").decode("ascii"))


def checar(condicao, descricao):
    _reportar(f"  {'ok  ' if condicao else 'FALHA'}  {descricao}")
    if not condicao:
        FALHAS.append(descricao)


def _cenario(nome: str, status=StatusBeneficio.ativo):
    posto = PostoServico(nome=f"Posto {nome} {_uuid.uuid4().hex[:6]}",
                         da_direito_creche=True, valor_reembolso_creche="R$ 500,00")
    db.add(posto)
    db.flush()
    col = Candidato(nome_completo=nome, cpf=str(_uuid.uuid4().int)[:11],
                    situacao="ativo", posto_servico_id=posto.id,
                    email=f"{_uuid.uuid4().hex[:8]}@exemplo.com.br")
    db.add(col)
    db.flush()
    ben = BeneficioCreche(candidato_id=col.id, status=status,
                          valor_reembolso="R$ 500,00")
    db.add(ben)
    db.flush()
    db.add(CriancaCreche(beneficio_id=ben.id, nome="Filho Um",
                         data_nascimento="2023-05-10", parentesco="filho",
                         tipo_comprovante="declaracao", decisao="deferida"))
    db.commit()
    return col, ben


print("\n== 1. roteiro de ADMISSAO nao pode esconder o do creche ==")
col1, ben1 = _cenario("Maria Do Creche")
criar_roteiro_creche(db, ben1, _RH)
db.commit()
# Agora o roteiro de admissão, criado DEPOIS — é o caso real de quem foi
# efetivado e assina contrato pela plataforma. Sem o filtro por origem, é ele
# que a consulta do creche devolve.
admissao = SolicitacaoAssinatura(
    candidato_id=col1.id, titulo_doc="Contrato de trabalho",
    origem=None, status=StatusSolicitacao.aguardando, etapa_atual_ordem=1)
db.add(admissao)
db.commit()

achado = tem_roteiro(db, col1.id, origem=ORIGEM_CRECHE)
checar(achado is not None and achado.origem == ORIGEM_CRECHE,
       "tem_roteiro(origem=creche) acha o do creche mesmo com um de admissao mais novo")
mais_recente = tem_roteiro(db, col1.id)
checar(mais_recente is not None and mais_recente.id == admissao.id,
       "sem o filtro, a consulta devolve MESMO o de admissao (o defeito reproduzido)")

# A prova que importa: a rota que o colaborador enxerga.
from app.api.creche_publico import _etapa_colaborador  # noqa: E402

sol_c, etapa_c = _etapa_colaborador(db, ben1)
checar(sol_c is not None and etapa_c is not None,
       "a sessao do colaborador ENXERGA o requerimento (era o `disponivel: false`)")

print("\n== 2. criar_roteiro_creche e idempotente por origem ==")
antes = db.query(SolicitacaoAssinatura).filter(
    SolicitacaoAssinatura.candidato_id == col1.id,
    SolicitacaoAssinatura.origem == ORIGEM_CRECHE).count()
criar_roteiro_creche(db, ben1, _RH)
db.commit()
depois = db.query(SolicitacaoAssinatura).filter(
    SolicitacaoAssinatura.candidato_id == col1.id,
    SolicitacaoAssinatura.origem == ORIGEM_CRECHE).count()
checar(antes == 1 and depois == 1,
       f"nao cria um SEGUNDO roteiro de creche (antes={antes}, depois={depois})")

print("\n== 3. a ficha do RH ACUSA quem esta pendente ==")
col2, ben2 = _cenario("Joao Sem Requerimento")  # ativo, sem roteiro nenhum
r = cli.get(f"/api/rh/creche/levantamentos/{ben2.id}")
checar(r.status_code == 200, f"detalhe responde 200 (veio {r.status_code})")
req = (r.json() or {}).get("requerimento") or {}
checar(req.get("pendente_disparo") is True,
       "benefício ativo SEM roteiro aparece como pendente_disparo")
r1 = cli.get(f"/api/rh/creche/levantamentos/{ben1.id}").json().get("requerimento") or {}
checar(r1.get("pendente_disparo") is False and r1.get("disparado") is True,
       "quem TEM roteiro nao e acusado (alarme falso ensina a ignorar o alarme)")

print("\n== 4. disparo individual ==")
r = cli.post(f"/api/rh/creche/levantamentos/{ben2.id}/disparar-requerimento")
checar(r.status_code == 200 and r.json().get("disparado") is True,
       f"dispara o pendente (status={r.status_code})")
# ESTADO, nao so o status code: a mutacao que faz a rota nao criar nada
# responderia 200 igual (v2.84).
db.expire_all()
checar(tem_roteiro(db, col2.id, origem=ORIGEM_CRECHE) is not None,
       "o roteiro REALMENTE existe no banco depois do disparo")
r = cli.post(f"/api/rh/creche/levantamentos/{ben2.id}/disparar-requerimento")
checar(r.status_code == 200 and r.json().get("motivo") == "ja_disparado",
       "segundo clique responde ja_disparado, sem criar outro")

print("\n== 5. beneficio NAO ativo recusa, com a saida ==")
col3, ben3 = _cenario("Ana Repactuacao", status=StatusBeneficio.aguardando_repactuacao)
r = cli.post(f"/api/rh/creche/levantamentos/{ben3.id}/disparar-requerimento")
d = r.json().get("detail") if r.status_code == 409 else None
checar(r.status_code == 409, f"recusa quem nao esta ativo (veio {r.status_code})")
# Afirmar sobre o DETAIL, nao so sobre o 409: outro motivo daria 409 igual
# (v2.80).
checar(isinstance(d, dict) and d.get("erro") == "beneficio_nao_ativo",
       "o detail NOMEIA o motivo da recusa")
checar(isinstance(d, dict) and bool(d.get("resolve")),
       "a recusa OFERECE a saida (v2.93), nao so o bloqueio")
db.expire_all()
checar(tem_roteiro(db, col3.id, origem=ORIGEM_CRECHE) is None,
       "e NAO criou roteiro nenhum para ele")

print("\n== 6. lote presta contas ==")
col4, ben4 = _cenario("Pedro Do Lote")
r = cli.post("/api/rh/creche/requerimentos/disparar-pendentes")
checar(r.status_code == 200, f"lote responde 200 (veio {r.status_code})")
corpo = r.json()
nomes = [d["nome"] for d in corpo.get("disparados", [])]
checar("Pedro Do Lote" in nomes,
       "o lote NOMEIA quem foi disparado (nao so a contagem)")
checar("falhas" in corpo,
       "o lote sempre reporta o campo de falhas, mesmo vazio")
db.expire_all()
checar(tem_roteiro(db, col4.id, origem=ORIGEM_CRECHE) is not None,
       "e o roteiro do lote REALMENTE existe no banco")
# Quem ja tinha nao entra de novo na lista de disparados.
checar("Maria Do Creche" not in nomes,
       "quem ja tinha roteiro nao aparece como disparado")

print("\n== 7. declaracao-modelo tem porta propria ==")
r = cli.post(f"/api/rh/creche/levantamentos/{ben4.id}/enviar-declaracao")
checar(r.status_code == 200 and "enviado_para" in r.json(),
       f"envia a declaracao-modelo (status={r.status_code})")
# Sem e-mail, recusa dizendo o que resolve — nao estoura em 500.
col5, ben5 = _cenario("Sem Email")
col5.email = None
db.commit()
r = cli.post(f"/api/rh/creche/levantamentos/{ben5.id}/enviar-declaracao")
d = r.json().get("detail") if r.status_code == 422 else None
checar(r.status_code == 422 and isinstance(d, dict) and bool(d.get("resolve")),
       "sem e-mail: 422 que diz o que resolve, nunca 500")

print("\n== 8. os templates existem no CATALOGO ==")
from app.services.email_templates import CATALOGO  # noqa: E402

chaves = {m.chave for m in CATALOGO}
for c in ("creche_requerimento_disponivel", "creche_declaracao_modelo"):
    checar(c in chaves, f"template {c} esta no catalogo")

print()
if FALHAS:
    _reportar(f"{len(FALHAS)} FALHA(S):")
    for f in FALHAS:
        _reportar(f"  - {f}")
    sys.exit(1)
_reportar("TODOS OS CENARIOS PASSARAM")
