"""Capitalização de nome de pessoa — e a proibição do `.title()`.

Feedback do Bruno (2026-08-02): *"Maria De Fátima, onde o 'De' nesse caso
deveria ser 'de'... está muito feio no visual do front e até nas fichas
geradas, bem como nos e-mails."*

O achado que este teste protege é que o sistema **produzia** o defeito, não só
o tolerava: `ocr_rg.py` sugeria o nome da mãe com `.title()` do Python, e
`"maria de fátima".title()` devolve exatamente `"Maria De Fátima"`. O candidato
aceitava a sugestão com um toque.

Duas garantias, e a segunda é a que dura:

  1. `capitalizar_nome` acerta os casos reais (preposições, caixa alta, `d'`,
     hífen, sufixo romano) e é IDEMPOTENTE — o wizard salva a cada 900ms de
     digitação, então a função roda sobre o próprio resultado o tempo todo.
  2. Nenhum ponto que grava NOME volta a usar `.title()` — teste ESTRUTURAL,
     que lê o código-fonte. Sem ele, o próximo `.title()` reintroduz o defeito
     num arquivo que ninguém está olhando.

Roda sem banco e sem FastAPI: stdlib + o módulo de nomes.
"""
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.nomes import capitalizar_nome, primeiro_nome  # noqa: E402

FALHAS = []
RAIZ = Path(__file__).resolve().parents[1] / "app"


def checar(condicao, descricao):
    if condicao:
        print(f"  ok   {descricao}")
    else:
        print(f"  FALHA {descricao}")
        FALHAS.append(descricao)


def test_o_caso_que_o_bruno_reclamou():
    print("\n[o caso do feedback]")
    # Os três jeitos que o candidato digita, e o certo é o mesmo para todos.
    for entrada in ["MARIA DE FÁTIMA", "maria de fátima", "Maria De Fátima"]:
        obtido = capitalizar_nome(entrada)
        checar(obtido == "Maria de Fátima", f"{entrada!r} -> {obtido!r}")

    # E o que o `.title()` do Python faria — a prova de que ele não serve.
    checar("maria de fátima".title() == "Maria De Fátima",
           "(referência) o .title() do Python produz o defeito reclamado")


def test_preposicoes_e_sufixos():
    print("\n[preposições, sufixos e grafias]")
    casos = [
        ("JOSÉ DOS SANTOS NETO", "José dos Santos Neto"),
        ("JOSÉ DA SILVA JÚNIOR", "José da Silva Júnior"),
        ("joão paulo ii", "João Paulo II"),
        ("ana-clara silva", "Ana-Clara Silva"),
        ("van der berg", "Van der Berg"),
        ("  espaços   demais  ", "Espaços Demais"),
        ("ANA", "Ana"),
    ]
    for entrada, esperado in casos:
        obtido = capitalizar_nome(entrada)
        checar(obtido == esperado, f"{entrada!r} -> {obtido!r}")

    # Preposição ABRINDO o nome fica maiúscula: quem se chama "De Souza" de
    # primeiro nome existe, e minúsculo no começo pareceria erro.
    checar(capitalizar_nome("de souza lima") == "De Souza Lima",
           "preposição no início continua maiúscula")


def test_idempotente():
    """Aplicar duas vezes dá o mesmo — o autosave do wizard depende disso."""
    print("\n[idempotência]")
    for entrada in ["MARIA DE FÁTIMA", "josé dos santos neto", "joão paulo ii",
                    "d'ávila souza", "ana-clara silva"]:
        uma = capitalizar_nome(entrada)
        duas = capitalizar_nome(uma)
        checar(uma == duas, f"{entrada!r}: estável em {uma!r}")


def test_nunca_perde_o_nome():
    """Entrada não vazia nunca sai vazia — nome é dado de identificação."""
    print("\n[não destrói dado]")
    for entrada in ["X", "A B", "ÉLI", "'", "123", "maria"]:
        obtido = capitalizar_nome(entrada)
        checar(obtido != "", f"{entrada!r} não some (virou {obtido!r})")
    checar(capitalizar_nome("") == "" and capitalizar_nome(None) == "",
           "vazio e None seguem vazios, sem levantar")


def test_nao_inventa_acento():
    """`FATIMA` continua `Fatima` — capitalizar não é corrigir ortografia.

    É por isso que a base existente NÃO deve ser migrada em lote: o que está
    gravado em caixa alta já perdeu o acento na origem, e uma migração cega
    gravaria "Fatima" como se fosse o nome correto de alguém.
    """
    print("\n[não inventa acento]")
    checar(capitalizar_nome("MARIA DE FATIMA") == "Maria de Fatima",
           "sem acento na entrada, sem acento na saída")


def test_primeiro_nome():
    print("\n[primeiro nome, para tratamento em e-mail]")
    checar(primeiro_nome("MARIA DE FÁTIMA") == "Maria", "MARIA DE FÁTIMA -> Maria")
    checar(primeiro_nome("josé dos santos") == "José", "josé dos santos -> José")
    checar(primeiro_nome("") == "", "vazio não quebra o e-mail")


def test_nenhum_ponto_de_escrita_usa_title():
    """ESTRUTURAL: `.title()` não pode voltar onde se grava NOME.

    Esta é a garantia que dura. As anteriores provam que a função de hoje está
    certa; esta impede que alguém, daqui a seis meses, escreva
    `nome.title()` num arquivo novo e reintroduza "Maria De Fátima" sem que
    nada acuse.

    A varredura é dos arquivos que comprovadamente ESCREVEM nome — não do
    projeto inteiro: `.title()` sobre rótulo de enum ou cidade é legítimo e não
    deve travar o CI.
    """
    print("\n[nenhum .title() em ponto de escrita de nome]")
    alvos = [
        "api/ficha.py", "api/candidatos.py", "api/talentos.py",
        "api/rh_ficha.py", "services/ocr_rg.py", "services/nomes.py",
    ]
    padrao = re.compile(r"\b(nome\w*|nomes\[\d\])\s*\.title\(\)")
    for rel in alvos:
        caminho = RAIZ / rel
        if not caminho.exists():
            checar(False, f"{rel}: arquivo não encontrado (o teste ficou cego)")
            continue
        achados = [
            f"{rel}:{i}"
            for i, linha in enumerate(caminho.read_text(encoding="utf-8").splitlines(), 1)
            # Comentário citando `.title()` para explicar por que NÃO usá-lo é
            # legítimo — e existe em `nomes.py` e `ocr_rg.py`.
            if padrao.search(linha) and not linha.lstrip().startswith("#")
        ]
        checar(not achados,
               f"{rel} não usa .title() em nome"
               + (f" (achado em {achados})" if achados else ""))


if __name__ == "__main__":
    test_o_caso_que_o_bruno_reclamou()
    test_preposicoes_e_sufixos()
    test_idempotente()
    test_nunca_perde_o_nome()
    test_nao_inventa_acento()
    test_primeiro_nome()
    test_nenhum_ponto_de_escrita_usa_title()

    print()
    if FALHAS:
        print(f"test_nomes: {len(FALHAS)} FALHA(S)")
        for f in FALHAS:
            print(f"  - {f}")
        sys.exit(1)
    print("test_nomes: OK")
