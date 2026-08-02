"""Espaço sobrando e caixa alta/baixa no que a pessoa digita (v2.57).

Feedback de campo 2026-08-02:

> *"as vezes fica tudo minúsculo, as vezes digita tudo maiúsculo [...] e tem
> gente que quando termina de digitar o nome ainda dá um espaço depois da
> última palavra"*

A capitalização já era tratada desde a v2.54 (`services/nomes.py`), mas só no
NOME. O espaço sobrando em qualquer OUTRO campo passava direto — e não é
inofensivo:

* suja o export do Tirvu/Dexion, que é lido por outro sistema;
* **duplica a opção no filtro de coluna**: `"Taguatinga"` e `"Taguatinga "`
  viram duas entradas na lista suspensa, e nenhuma acha as pessoas da outra;
* quebra casamento por TEXTO (cargo, lotação, jornada), que é como boa parte do
  sistema liga as coisas;
* e, no e-mail, causava um erro que mentia: `EmailStr` recusava
  `"jose@x.com "` e a pessoa via "e-mail inválido" olhando para um endereço
  perfeitamente correto.

Roda sem banco: só os schemas Pydantic e o serviço de nomes.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault(
    "DATABASE_URL", "postgresql+psycopg://admissao:admissao@localhost:55432/admissao")
os.environ.setdefault("SECRET_KEY", "teste")

from app.api.ficha import (ContatoEmergenciaIn, DependenteIn,  # noqa: E402
                           SecaoDocumentos, SecaoEndereco, SecaoPessoais)
from app.services.nomes import capitalizar_nome  # noqa: E402

FALHAS = []


def checar(condicao, descricao):
    if condicao:
        print(f"  ok   {descricao}")
    else:
        print(f"  FALHA {descricao}")
        FALHAS.append(descricao)


def test_o_espaco_no_fim_do_nome():
    """O caso literal do feedback."""
    print("\n[espaço depois da última palavra]")
    s = SecaoPessoais(**{"nome_completo": "MARIA DE FATIMA "})
    checar(s.nome_completo == "Maria de Fatima",
           f"'MARIA DE FATIMA ' -> {s.nome_completo!r}")
    s = SecaoPessoais(**{"nome_completo": "  joao da silva  "})
    checar(s.nome_completo == "Joao da Silva",
           f"espaço nas DUAS pontas -> {s.nome_completo!r}")
    s = SecaoPessoais(**{"nome_completo": "JOSÉ  DOS   SANTOS"})
    checar(s.nome_completo == "José dos Santos",
           f"espaços repetidos no meio -> {s.nome_completo!r}")


def test_as_tres_formas_de_digitar():
    """Caixa alta, caixa baixa e o 'De' — todas chegam ao mesmo lugar."""
    print("\n[caixa alta, baixa e o 'De']")
    esperado = "Maria de Fátima"
    for entrada in ["MARIA DE FÁTIMA", "maria de fátima", "Maria De Fátima",
                    "  Maria De Fátima  "]:
        obtido = SecaoPessoais(**{"nome_completo": entrada}).nome_completo
        checar(obtido == esperado, f"{entrada!r} -> {obtido!r}")


def test_espaco_sai_de_TODO_campo_de_texto():
    """Não só do nome: endereço, cidade, bairro, UF, documentos.

    Era a lacuna real — `capitalizar_nome` cobria o nome e mais nada.
    """
    print("\n[todo campo de texto, não só o nome]")
    e = SecaoEndereco(**{"cidade": "TAGUATINGA ", "bairro": "  Centro",
                         "logradouro": " Rua das Flores  ", "uf": "df "})
    checar(e.cidade == "TAGUATINGA", f"cidade -> {e.cidade!r}")
    checar(e.bairro == "Centro", f"bairro -> {e.bairro!r}")
    checar(e.logradouro == "Rua das Flores", f"logradouro -> {e.logradouro!r}")
    checar(e.uf == "df", f"uf -> {e.uf!r}")

    d = SecaoDocumentos(**{"rg_orgao_emissor": "SSP ", "cnh_categoria": " AB "})
    checar(d.rg_orgao_emissor == "SSP", f"órgão emissor -> {d.rg_orgao_emissor!r}")
    checar(d.cnh_categoria == "AB", f"categoria CNH -> {d.cnh_categoria!r}")


def test_email_com_espaco_nao_e_mais_recusado():
    """`EmailStr` recusava, e a mensagem culpava a pessoa pelo e-mail certo.

    O `mode="before"` é o que resolve: apara ANTES da validação de tipo.
    """
    print("\n[e-mail com espaço]")
    s = SecaoPessoais(**{"email": "  jose@example.com  "})
    checar(s.email == "jose@example.com", f"e-mail aparado -> {s.email!r}")


def test_so_espacos_vira_none():
    """Campo deixado com espaços é VAZIO, não um texto de um espaço."""
    print("\n[campo só com espaços]")
    e = SecaoEndereco(**{"complemento": "   "})
    checar(e.complemento is None, f"'   ' -> {e.complemento!r}")


def test_nao_quebra_o_resto():
    """Regressões: autosave parcial, datas, booleanos e CPF continuam iguais."""
    print("\n[nada mais muda]")
    s = SecaoPessoais(**{"nome_completo": "X"})
    checar(s.model_dump(exclude_unset=True) == {"nome_completo": "X"},
           "campo não enviado continua AUSENTE (o autosave é parcial)")
    s = SecaoPessoais(**{"data_nascimento": " 1990-01-01 "})
    checar(str(s.data_nascimento) == "1990-01-01", "data ainda é interpretada")
    s = SecaoPessoais(**{"pcd": True})
    checar(s.pcd is True, "booleano não é afetado")
    d = SecaoDocumentos(**{"cpf": " 390.533.447-05 "})
    checar(d.cpf == "39053344705", "CPF segue validado e limpo")


def test_dependentes_e_contatos_tambem():
    """Os outros schemas com nome de pessoa."""
    print("\n[dependentes e contatos de emergência]")
    d = DependenteIn(**{"nome_completo": "PEDRO DA SILVA ", "cpf": "39053344705",
                        "data_nascimento": "2015-05-05", "parentesco": "filho"})
    checar(d.nome_completo == "Pedro da Silva", f"dependente -> {d.nome_completo!r}")
    c = ContatoEmergenciaIn(**{"nome_completo": "  ANA MARIA  ",
                               "parentesco": "mãe ", "telefone_celular": "61999998888 "})
    checar(c.nome_completo == "Ana Maria", f"contato -> {c.nome_completo!r}")
    checar(c.parentesco == "mãe", f"parentesco aparado -> {c.parentesco!r}")


def test_nao_inventa_acento():
    """`FATIMA` continua `Fatima` — decisão do Bruno, 2026-08-02.

    O acento se perdeu na origem; adivinhar escreveria errado o nome de alguém,
    o que é pior que deixá-lo sem acento. Vale também para a migração da base
    existente (`e7f8a9b0c1d2`), que usa esta mesma função.
    """
    print("\n[não inventa acento]")
    checar(capitalizar_nome("MARIA DE FATIMA") == "Maria de Fatima",
           "sem acento na entrada, sem acento na saída")
    checar(capitalizar_nome("JOSE ANTONIO") == "Jose Antonio",
           "não vira 'José Antônio' por conta própria")


if __name__ == "__main__":
    test_o_espaco_no_fim_do_nome()
    test_as_tres_formas_de_digitar()
    test_espaco_sai_de_TODO_campo_de_texto()
    test_email_com_espaco_nao_e_mais_recusado()
    test_so_espacos_vira_none()
    test_nao_quebra_o_resto()
    test_dependentes_e_contatos_tambem()
    test_nao_inventa_acento()

    print()
    if FALHAS:
        print(f"test_espacos_e_caixa: {len(FALHAS)} FALHA(S)")
        for f in FALHAS:
            print(f"  - {f}")
        sys.exit(1)
    print("test_espacos_e_caixa: OK")
