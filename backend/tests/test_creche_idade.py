"""Idade das crianças do reembolso-creche (v2.27) — o cálculo que decide dinheiro.

Incidente de campo 2026-07-30: TODA criança aparecia como "❌ passou de 5a11m",
inclusive um bebê de 2 anos. O RH ia indeferir gente com direito.

A causa era só o FORMATO da data: `_idade_anos_meses` lia apenas `dd/mm/aaaa`,
mas o `InputData.jsx` do wizard devolve ISO (`aaaa-mm-dd`) por padrão — e é
assim que a maioria dos registros foi gravada. O `split("/")` falhava, a idade
virava `None`, e `None` era tratado como "não elegível".

O que se testa aqui não é aritmética de calendário: é a garantia de que o
sistema NÃO nega o benefício por não conseguir ler a própria data que gravou.

Rode: PYTHONPATH=. .venv/Scripts/python.exe tests/test_creche_idade.py
"""

import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault(
    "DATABASE_URL", "postgresql+psycopg://admissao:admissao@localhost:55432/admissao")

from app.api.creche import (_elegivel_por_idade, _idade_anos_meses,  # noqa: E402
                            data_br, partes_da_data)

FALHAS = []
REF = datetime(2026, 7, 30, tzinfo=timezone.utc)   # data fixa: teste estável


def checar(condicao, descricao):
    if condicao:
        print(f"  ok   {descricao}")
    else:
        print(f"  FALHA {descricao}")
        FALHAS.append(descricao)


def test_os_dois_formatos():
    """ISO e BR têm que dar a MESMA idade — é a mesma criança."""
    print("\n[os dois formatos do banco]")
    for iso, br, esperado in [
        ("2024-02-01", "01/02/2024", (2, 5)),
        ("2021-07-07", "07/07/2021", (5, 0)),
        ("2019-12-25", "25/12/2019", (6, 7)),
    ]:
        a, b = _idade_anos_meses(iso, REF), _idade_anos_meses(br, REF)
        checar(a == b == esperado,
               f"{iso} e {br} dão {esperado} (vieram {a} e {b})")


def test_caso_real_do_incidente():
    """Os dois registros do print do Bruno, com a data como está no banco."""
    print("\n[caso real de 2026-07-30]")
    yuri = _idade_anos_meses("2021-07-07", REF)
    hannah = _idade_anos_meses("2024-02-01", REF)
    checar(yuri == (5, 0), f"Yuri tem 5a0m (veio {yuri})")
    checar(hannah == (2, 5), f"Hannah tem 2a5m (veio {hannah})")
    checar(_elegivel_por_idade("2021-07-07", REF) is True,
           "Yuri está na idade — tinha direito e o sistema negava")
    checar(_elegivel_por_idade("2024-02-01", REF) is True,
           "Hannah, de 2 anos, está na idade")


def test_limite_da_in_147():
    """5 anos e 11 meses é o teto (art. 2º, §1º). O mês importa."""
    print("\n[limite de 5a11m]")
    casos = [
        ("2020-08-30", True,  "5a11m — último mês elegível"),
        ("2020-07-30", False, "6a0m — passou"),
        ("2026-07-30", True,  "recém-nascido"),
        ("2015-01-01", False, "11 anos — muito acima"),
    ]
    for data, esperado, desc in casos:
        obtido = _elegivel_por_idade(data, REF)
        checar(obtido is esperado, f"{desc}: {data} -> {obtido}")


def test_data_ilegivel_nao_vira_idade_inventada():
    """Melhor não saber do que afirmar errado.

    Uma idade inventada a partir de data corrompida decidiria benefício com
    dado falso — pior que admitir que não deu para ler.
    """
    print("\n[data ilegível]")
    for lixo in ["", None, "xx/yy/zzzz", "2024-99-99", "32/13/2024", "abc", "2024"]:
        checar(_idade_anos_meses(lixo, REF) is None,
               f"{lixo!r} não vira idade")
        checar(_elegivel_por_idade(lixo, REF) is False,
               f"{lixo!r} não é dado como elegível por engano")


def test_exibicao_sempre_em_br():
    """A tela e o PDF do requerimento mostram dd/mm/aaaa, venha como vier."""
    print("\n[exibição]")
    checar(data_br("2024-02-01") == "01/02/2024", "ISO vira BR na tela")
    checar(data_br("01/02/2024") == "01/02/2024", "BR continua BR")
    checar(data_br("1/2/2024") == "01/02/2024", "BR sem zero à esquerda é normalizado")
    checar(data_br(None) == "—", "data ausente não quebra a tela")


def test_partes_da_data():
    """A função-base, usada por todo o resto."""
    print("\n[partes_da_data]")
    checar(partes_da_data("2024-02-01") == (1, 2, 2024), "ISO decomposto certo")
    checar(partes_da_data("01/02/2024") == (1, 2, 2024), "BR decomposto certo")
    checar(partes_da_data("2024-13-01") is None, "mês 13 é recusado")
    checar(partes_da_data("1899-01-01") is None, "ano absurdo é recusado")


if __name__ == "__main__":
    test_os_dois_formatos()
    test_caso_real_do_incidente()
    test_limite_da_in_147()
    test_data_ilegivel_nao_vira_idade_inventada()
    test_exibicao_sempre_em_br()
    test_partes_da_data()

    print()
    if FALHAS:
        print(f"test_creche_idade: {len(FALHAS)} FALHA(S)")
        for f in FALHAS:
            print(f"  - {f}")
        sys.exit(1)
    print("test_creche_idade: OK")
