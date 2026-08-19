"""Ciclo MENSAL do reembolso-creche — as rotas (v3.02).

O e-mail de ativação já mandava enviar, todo mês, a nota fiscal da creche (PJ)
ou a declaração de quitação do cuidador (PF) — e não havia rota que recebesse
isso: o creche tinha 21 rotas POST e nenhuma aceitava o comprovante. Este teste
cobre a porta nova, dos dois lados.

O que se garante aqui, e por quê:

1. **Múltiplas folhas viram UM PDF.** A causa do *"não consigo ver se há mais de
   uma folha"* era não haver: a key era fixa e o reenvio sobrescrevia.
2. **Reenvio SUBSTITUI, não duplica.** Dois registros do mesmo mês fariam a soma
   da folha dobrar sem nada denunciar (há `UniqueConstraint`).
3. **Comprovante já APROVADO não é sobrescrito pelo colaborador** — trocaria a
   peça que sustenta um pagamento que talvez já tenha saído.
4. **O teto é teto.** Despesa menor que o valor do posto paga a despesa.
5. **Criança indeferida não recebe comprovante** — criaria despesa comprovada
   para quem não tem direito.
6. **Recusa exige motivo**: sem ele o colaborador reenvia a mesma coisa.
7. **Competência anterior à vigência é MARCADA, não recusada** (decisão do
   Bruno) — e a marca precisa chegar à tela, senão equivale a não existir.

Precisa de banco e MinIO. Roda no CI dentro do container da API.
"""
import io
import os
import sys
import uuid as _uuid
from datetime import date

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
from app.models.beneficio import (BeneficioCreche, CriancaCreche,  # noqa: E402
                                  StatusBeneficio)
from app.models.candidato import Candidato, PostoServico  # noqa: E402
from app.models.creche_competencia import CompetenciaCreche  # noqa: E402
from app.models.usuario_rh import UsuarioRH  # noqa: E402
from app.services import creche_competencia as regras  # noqa: E402

FALHAS = []
_RH = UsuarioRH(email="rh@teste.com", nome="RH Teste", senha_hash="x",
                papel="superadmin")
app.dependency_overrides[requer_rh] = lambda: _RH
# `raise_server_exceptions=False`: sem isto, um 500 do servidor sobe como
# exceção e mata o script no meio — a saída fica VAZIA e passa por sucesso
# (a armadilha da v2.72.2).
cli = TestClient(app, raise_server_exceptions=False)
db = SessionLocal()

ANO, MES = regras.competencia_anterior(date.today())


def checar(condicao, descricao):
    print(f"  {'ok  ' if condicao else 'FALHA'}  {descricao}")
    if not condicao:
        FALHAS.append(descricao)


def _png(cor: int = 200) -> bytes:
    """Uma imagem real e pequena — o upload valida o conteúdo, não só a
    extensão, então bytes aleatórios seriam recusados por motivo errado."""
    from PIL import Image
    buf = io.BytesIO()
    Image.new("RGB", (700, 900), (cor, cor, cor)).save(buf, format="PNG")
    return buf.getvalue()


def _cenario(nome: str, valor="R$ 526,64", vigente_desde=None):
    posto = PostoServico(nome=f"Posto {nome} {_uuid.uuid4().hex[:6]}",
                         da_direito_creche=True, valor_reembolso_creche=valor,
                         creche_vigente_desde=vigente_desde)
    db.add(posto)
    db.flush()
    col = Candidato(nome_completo=nome, cpf=str(_uuid.uuid4().int)[:11],
                    situacao="ativo", posto_servico_id=posto.id)
    db.add(col)
    db.flush()
    ben = BeneficioCreche(candidato_id=col.id, status=StatusBeneficio.ativo,
                          valor_reembolso=valor)
    db.add(ben)
    db.flush()
    crianca = CriancaCreche(beneficio_id=ben.id, nome="Filho Um",
                            data_nascimento="2023-05-10", parentesco="filho",
                            tipo_comprovante="declaracao", decisao="deferida")
    db.add(crianca)
    db.commit()
    return ben, crianca


def _enviar(ben, crianca, arquivos, valor=None, ano=ANO, mes=MES):
    url = (f"/api/rh/creche/levantamentos/{ben.id}/competencias"
           f"?crianca_id={crianca.id}&ano={ano}&mes={mes}")
    if valor is not None:
        url += f"&valor={valor}"
    return cli.post(url, files=[("arquivos", a) for a in arquivos])


print("1. várias folhas viram UM PDF (a lacuna do 'não vejo mais de uma folha')")
ben, crianca = _cenario("Ciclo Multi Folhas")
r = _enviar(ben, crianca,
            [("folha1.png", _png(210), "image/png"),
             ("folha2.png", _png(180), "image/png")], valor="R$ 400,00")
checar(r.status_code == 200, f"envio com 2 folhas aceito (HTTP {r.status_code})")
corpo = r.json() if r.status_code == 200 else {}
checar(corpo.get("paginas") == 2, f"o PDF tem 2 páginas (veio {corpo.get('paginas')})")
checar(corpo.get("tem_arquivo") is True, "o arquivo ficou gravado")

print("2. o teto é TETO: despesa menor paga a despesa")
# posto de R$ 526,64, despesa de R$ 400,00
checar(corpo.get("valor_comprovado") == "R$ 400,00",
       f"valor comprovado (veio {corpo.get('valor_comprovado')})")
checar(corpo.get("valor_reembolsavel") == "R$ 400,00",
       f"reembolsa a DESPESA, não o teto (veio {corpo.get('valor_reembolsavel')})")

r2 = _enviar(ben, crianca, [("f.png", _png(150), "image/png")], valor="R$ 900,00")
checar(r2.status_code == 200, "reenvio com valor acima do teto aceito")
c2 = r2.json() if r2.status_code == 200 else {}
checar(c2.get("valor_reembolsavel") == "R$ 526,64",
       f"acima do teto, reembolsa o TETO (veio {c2.get('valor_reembolsavel')})")

print("3. reenvio SUBSTITUI — dois registros do mesmo mês dobrariam a folha")
db.expire_all()
quantos = db.query(CompetenciaCreche).filter(
    CompetenciaCreche.crianca_id == crianca.id,
    CompetenciaCreche.ano == ANO, CompetenciaCreche.mes == MES).count()
checar(quantos == 1, f"há UM registro para a competência (encontrados {quantos})")
checar(c2.get("paginas") == 1, "o reenvio trocou o conteúdo (1 folha agora)")

print("4. o RH analisa; recusar sem motivo é recusado")
comp_id = c2.get("id")
r3 = cli.post(f"/api/rh/creche/competencias/{comp_id}/analisar",
              json={"aprovar": False})
checar(r3.status_code == 422, f"recusa sem motivo dá 422 (veio {r3.status_code})")
checar(r3.json().get("detail") == "motivo_obrigatorio",
       "e o detalhe DIZ que falta o motivo")

r4 = cli.post(f"/api/rh/creche/competencias/{comp_id}/analisar",
              json={"aprovar": True, "valor": "R$ 450,00"})
checar(r4.status_code == 200, "aprovação aceita")
checar(r4.json().get("status") == "aprovado", "status virou aprovado")
checar(r4.json().get("valor_comprovado") == "R$ 450,00",
       "o RH pode corrigir o valor que o colaborador digitou")

print("5. comprovante JÁ APROVADO não é sobrescrito")
r5 = _enviar(ben, crianca, [("outra.png", _png(120), "image/png")])
checar(r5.status_code == 409, f"reenvio sobre aprovado dá 409 (veio {r5.status_code})")
det = r5.json().get("detail", {})
checar(isinstance(det, dict) and det.get("erro") == "competencia_ja_aprovada",
       "e o detalhe nomeia o motivo")

print("6. criança INDEFERIDA não recebe comprovante")
ben2, crianca2 = _cenario("Ciclo Indeferida")
crianca2.decisao = "indeferida"
crianca2.motivo_decisao = "fora da faixa etária"
db.commit()
r6 = _enviar(ben2, crianca2, [("f.png", _png(), "image/png")])
checar(r6.status_code == 409, f"comprovante de indeferida dá 409 (veio {r6.status_code})")
d6 = r6.json().get("detail", {})
checar(isinstance(d6, dict) and d6.get("erro") == "crianca_indeferida",
       "e o detalhe nomeia o motivo")

print("7. competência anterior à vigência é MARCADA, não recusada")
# vigência começa DEPOIS do mês que se está comprovando
depois = date(ANO + 1, 1, 1)
ben3, crianca3 = _cenario("Ciclo Retroativo", vigente_desde=depois)
r7 = _enviar(ben3, crianca3, [("f.png", _png(), "image/png")], valor="R$ 300,00")
checar(r7.status_code == 200,
       f"NÃO recusa — o RH decide (veio {r7.status_code})")
checar(r7.json().get("anterior_a_vigencia") is True,
       "mas vem MARCADA, e a marca chega à tela")

# e o caso oposto: vigência que já cobre o mês não pode marcar (alarme falso
# ensina a ignorar o alarme — a lição dos processos 9.1/9.2 da v2.91)
ben4, crianca4 = _cenario("Ciclo Coberto", vigente_desde=date(2026, 1, 1))
r8 = _enviar(ben4, crianca4, [("f.png", _png(), "image/png")])
checar(r8.status_code == 200 and r8.json().get("anterior_a_vigencia") is False,
       "competência coberta pela vigência NÃO é marcada")

print("8. a listagem mostra o que falta e o prazo")
r9 = cli.get(f"/api/rh/creche/levantamentos/{ben2.id}/competencias")
checar(r9.status_code == 200, "listagem responde")
corpo9 = r9.json() if r9.status_code == 200 else {}
checar(corpo9.get("dia_corte") == 5 or corpo9.get("dia_corte") == regras.DIA_CORTE_PADRAO,
       f"traz o dia de corte (veio {corpo9.get('dia_corte')})")
# a criança do ben2 está INDEFERIDA: não pode ser cobrada
checar(corpo9.get("pendentes") == [],
       "criança indeferida NÃO entra na lista de pendências")

print()
if FALHAS:
    print(f"test_creche_ciclo_mensal: {len(FALHAS)} FALHA(S)")
    for f in FALHAS:
        print(f"  - {f}")
    sys.exit(1)
print("test_creche_ciclo_mensal: OK")
