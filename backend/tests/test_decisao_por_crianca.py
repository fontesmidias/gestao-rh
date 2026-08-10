"""Decisão do RH por CRIANÇA no reembolso-creche (v2.55).

Feedback de campo 2026-08-02, sobre um colaborador com dois filhos:

> *"se a pessoa tem mais de um filho e um eu defiro e outro eu indefiro, não
> tem opção individual por filho, somente indeferir tudo ou aprovar tudo, não
> tá legal isso. Tem que ser individual isso de modo que eu marco os que defiro
> e os que indefiro, para gerar apenas um requerimento."*

O que se garante aqui é o que decide DINHEIRO e o que serve de PROVA:

1. **O valor acompanha as decisões.** O reembolso é por criança deferida
   (decisão do Bruno): indeferir uma reduz o total sozinho, sem o RH
   recalcular à mão — que é onde o erro de folha aconteceria.
2. **Benefício anterior à v2.55 NÃO é multiplicado.** Lá o valor gravado já
   era o total; multiplicá-lo agora dobraria o reembolso de quem tem dois
   filhos, calado, no contracheque.
3. **Não se aprova com criança pendente**, e o erro diz QUEM falta.
4. **Todas negadas ⇒ indeferido**, nunca um "ativo" que paga zero.
5. **O requerimento assinado lista só as deferidas**; as negadas ficam em
   seção própria, com o motivo — some o benefício, não o registro da análise.

Precisa de banco (Postgres efêmero). Rode:
  PYTHONPATH=. .venv/Scripts/python.exe tests/test_decisao_por_crianca.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault(
    "DATABASE_URL", "postgresql+psycopg://admissao:admissao@localhost:55432/admissao")
os.environ.setdefault("SECRET_KEY", "teste")
os.environ.setdefault("MINIO_ENDPOINT", "localhost:59000")
os.environ.setdefault("MINIO_ACCESS_KEY", "minio")
os.environ.setdefault("MINIO_SECRET_KEY", "minio12345")

from fastapi.testclient import TestClient  # noqa: E402

from app.api.auth_rh import requer_rh  # noqa: E402
from app.api.creche import _dump_beneficio  # noqa: E402
from app.core.db import SessionLocal  # noqa: E402
from app.main import app  # noqa: E402
from app.models.beneficio import (BeneficioCreche, CriancaCreche,  # noqa: E402
                                  StatusBeneficio)
from app.models.candidato import Candidato  # noqa: E402
from app.models.usuario_rh import UsuarioRH  # noqa: E402

FALHAS = []
# `papel` obrigatório desde a v2.86 — ver test_admissao_assistida.
_RH = UsuarioRH(email="rh@teste.com", nome="RH Teste", senha_hash="x",
                papel="superadmin")
app.dependency_overrides[requer_rh] = lambda: _RH
cli = TestClient(app)
db = SessionLocal()


def checar(condicao, descricao):
    if condicao:
        print(f"  ok   {descricao}")
    else:
        print(f"  FALHA {descricao}")
        FALHAS.append(descricao)


def _cenario(nome: str, valor="R$ 526,64", nascimentos=("2022-10-19", "2024-06-09")):
    """Colaborador com N crianças, benefício em análise."""
    import uuid as _uuid
    col = Candidato(nome_completo=nome, cpf=str(_uuid.uuid4().int)[:11], situacao="ativo")
    db.add(col)
    db.flush()
    ben = BeneficioCreche(candidato_id=col.id, status=StatusBeneficio.em_analise,
                          valor_reembolso=valor)
    db.add(ben)
    db.flush()
    criancas = [
        CriancaCreche(beneficio_id=ben.id, nome=f"Filho {i + 1}",
                      data_nascimento=n, parentesco="filho")
        for i, n in enumerate(nascimentos)
    ]
    db.add_all(criancas)
    db.commit()
    return ben, criancas


def _decidir(ben, c, decisao, motivo=None):
    r = cli.post(
        f"/api/rh/creche/levantamentos/{ben.id}/criancas/{c.id}/decidir",
        json={"decisao": decisao, "motivo": motivo})
    # A rota escreve numa sessão PRÓPRIA (a do `get_db`). Sem expirar a nossa,
    # o SQLAlchemy serve os objetos do cache de identidade e o teste enxerga o
    # estado ANTERIOR — o que faria uma falha do teste parecer bug do código.
    # Aconteceu ao escrever este arquivo: o valor "não atualizava" na segunda
    # decisão, e a rota estava certa o tempo todo.
    db.expire_all()
    return r


def _dump(ben):
    """Estado atual do benefício, relido do banco."""
    db.expire_all()
    return _dump_beneficio(db, db.get(BeneficioCreche, ben.id))


def test_valor_acompanha_as_decisoes():
    """O total é unitário × deferidas — é o que o DP paga."""
    print("\n[o valor acompanha as decisões]")
    ben, (a, b) = _cenario("Valor Duas")

    _decidir(ben, a, "deferida")
    _decidir(ben, b, "deferida")
    d = _dump(ben)
    checar(d["deferidas"] == 2, "duas deferidas contadas")
    checar(d["valor_total"] == "R$ 1.053,28",
           f"duas crianças = R$ 1.053,28 (veio {d['valor_total']})")

    _decidir(ben, b, "indeferida", "Certidão ilegível")
    d = _dump(ben)
    checar(d["deferidas"] == 1 and d["indeferidas"] == 1,
           "uma deferida e uma indeferida")
    checar(d["valor_total"] == "R$ 526,64",
           f"indeferir uma REDUZ o total (veio {d['valor_total']})")
    checar(d["valor_unitario"] == "R$ 526,64",
           "o unitário não muda — é o valor do contrato")


def test_beneficio_antigo_nao_e_multiplicado():
    """Sem NENHUMA decisão, o valor gravado é o total — não se multiplica.

    Benefício aprovado antes da v2.55 tem todas as crianças com `decisao=None`,
    e ali o `valor_reembolso` JÁ era o valor do benefício. Multiplicar
    retroativamente dobraria o reembolso de quem tem dois filhos, em silêncio,
    no contracheque — o tipo de erro que ninguém percebe até alguém conferir a
    folha.
    """
    print("\n[benefício anterior à v2.55]")
    ben, _ = _cenario("Modelo Antigo")
    d = _dump(ben)
    checar(d["sem_decisao"] == 2, "duas crianças sem decisão")
    checar(d["valor_total"] == "R$ 526,64",
           f"o valor gravado vale como total, NÃO multiplicado (veio {d['valor_total']})")


def test_valor_ilegivel_nao_vira_zero():
    """Valor que não dá para interpretar volta cru, nunca R$ 0,00."""
    print("\n[valor ilegível]")
    ben, (a, b) = _cenario("Valor Torto", valor="a combinar")
    _decidir(ben, a, "deferida")
    _decidir(ben, b, "deferida")
    d = _dump(ben)
    checar(d["valor_total"] == "a combinar",
           f"texto livre volta como está (veio {d['valor_total']})")


def test_nao_aprova_com_crianca_pendente():
    """E o erro DIZ QUEM falta — senão o RH procura na tabela qual esqueceu."""
    print("\n[não aprova pela metade]")
    ben, (a, b) = _cenario("Meio Decidido")
    _decidir(ben, a, "deferida")
    r = cli.post(f"/api/rh/creche/levantamentos/{ben.id}/ativar", json={})
    checar(r.status_code == 409, f"ativar com pendente recusa (veio {r.status_code})")
    detalhe = r.json().get("detail") or {}
    checar(detalhe.get("erro") == "criancas_sem_decisao", "com o código próprio")
    checar(detalhe.get("criancas") == [b.nome],
           f"e o NOME de quem falta (veio {detalhe.get('criancas')})")


def test_todas_negadas_vira_indeferido():
    """Sem criança deferida não há o que reembolsar."""
    print("\n[todas negadas]")
    ben, (a, b) = _cenario("Todas Negadas")
    _decidir(ben, a, "indeferida", "Fora da idade")
    _decidir(ben, b, "indeferida", "Sem certidão")
    r = cli.post(f"/api/rh/creche/levantamentos/{ben.id}/ativar", json={})
    checar(r.status_code == 200, "a aprovação é aceita e convertida")
    d = r.json()
    checar(d["status"] == "indeferido",
           f"vira indeferido, não um 'ativo' que paga zero (veio {d['status']})")
    checar("Fora da idade" in (d["motivo_indeferimento"] or "")
           and "Sem certidão" in (d["motivo_indeferimento"] or ""),
           "com os DOIS motivos agregados, por criança")


def test_indeferir_exige_motivo():
    """O motivo é visível ao colaborador — negar sem dizer por quê não vale."""
    print("\n[motivo obrigatório para negar]")
    ben, (a, _b) = _cenario("Sem Motivo")
    r = _decidir(ben, a, "indeferida")
    checar(r.status_code == 422 and r.json().get("detail") == "motivo_obrigatorio",
           f"indeferir sem motivo é recusado (veio {r.status_code})")
    r = _decidir(ben, a, "deferida")
    checar(r.status_code == 200, "deferir NÃO exige motivo")


def test_crianca_de_outro_beneficio_e_recusada():
    """Sem esta guarda, o id de uma criança de outra família seria aceito."""
    print("\n[isolamento entre benefícios]")
    ben1, _ = _cenario("Família Um")
    _ben2, (outra, _) = _cenario("Família Dois")
    r = _decidir(ben1, outra, "deferida")
    checar(r.status_code == 404,
           f"criança de outro benefício é 404 (veio {r.status_code})")


def test_requerimento_lista_so_as_deferidas():
    """O documento que a pessoa ASSINA não declara criança que o RH negou.

    Mas a negada não SOME: fica em seção própria com o motivo — é esse registro
    que prova que o dependente foi analisado. Antes desta versão, negar uma
    criança exigia removê-la do cadastro, e a prova se perdia junto.
    """
    print("\n[requerimento: um só, com as duas seções]")
    from app.services.creche_pdf import gerar_requerimento_creche
    import pypdf
    import io as _io

    ben, (a, b) = _cenario("Requerimento", nascimentos=("2022-10-19", "09/06/2026"))
    _decidir(ben, a, "deferida")
    _decidir(ben, b, "indeferida", "Certidão não anexada")
    ben = db.get(BeneficioCreche, ben.id)
    texto = pypdf.PdfReader(_io.BytesIO(gerar_requerimento_creche(db, ben))
                            ).pages[0].extract_text()

    checar("Filho 1" in texto, "a deferida está no requerimento")
    checar("NÃO contemplado" in texto, "há a seção das não contempladas")
    checar("Certidão não anexada" in texto, "com o motivo da negativa")
    # A ordem importa: a negada tem que vir DEPOIS do cabeçalho da seção, senão
    # estaria no corpo que a pessoa assina como dependente contemplado.
    checar(texto.index("Filho 2") > texto.index("NÃO contemplado"),
           "a negada aparece DEPOIS do cabeçalho da seção, não no corpo")
    # Data sempre em dd/mm/aaaa: o banco guarda ISO e BR, e este é documento
    # oficial em português (achado na conferência visual do PDF).
    checar("19/10/2022" in texto and "09/06/2026" in texto,
           "as datas saem em dd/mm/aaaa, venham do banco como vierem")


if __name__ == "__main__":
    test_valor_acompanha_as_decisoes()
    test_beneficio_antigo_nao_e_multiplicado()
    test_valor_ilegivel_nao_vira_zero()
    test_nao_aprova_com_crianca_pendente()
    test_todas_negadas_vira_indeferido()
    test_indeferir_exige_motivo()
    test_crianca_de_outro_beneficio_e_recusada()
    test_requerimento_lista_so_as_deferidas()

    print()
    if FALHAS:
        print(f"test_decisao_por_crianca: {len(FALHAS)} FALHA(S)")
        for f in FALHAS:
            print(f"  - {f}")
        sys.exit(1)
    print("test_decisao_por_crianca: OK")
