"""O padrão das telas de TRABALHO continua valendo (v2.96, § 8c do design).

O padrão nasceu do redesenho da ficha da pessoa, foi aprovado em protótipo pelo
Bruno e **confirmado no uso real** antes de virar obrigatório. Este teste existe
porque documento não reprova ninguém: sem ele, a próxima tela nasce empilhada de
novo e o § 8c vira recomendação que se lê depois de já ter feito errado.

O que se cobra aqui é o **verificável estruturalmente**. Coisas como "a aba certa
abre por padrão" ou "o impedimento é a frase certa" dependem de julgamento e
ficam para a revisão humana — cobrar por regex o que exige juízo produz falso
alarme, e falso alarme ensina a ignorar o alarme (a lição da v2.91).

Regras cobradas (§ 8c):

1. **Um verde por tela** — `btn-principal` é do ato que FECHA o trabalho. Seis
   verdes fazem nenhum ser o principal, e o pior caso é o irreversível
   ("Efetivar") pesar igual ao trivial ("Salvar data").
2. **Aba não se guarda em `localStorage`** — abrir o registro de outra pessoa é
   começar um trabalho novo; herdar a aba anterior abre a tela onde ninguém
   pediu.
3. **Abas reusam `.rh-abas`** — a primitiva existe desde o Creche; inventar
   classe nova é a v2.65 (passar no teste estrutural não é seguir o padrão).
4. **O resumo de exceções mora FORA do `<details>`** — dentro dele só apareceria
   para quem abrisse, e o problema que ele resolve é ninguém abrir.

Roda no bloco stdlib do CI: não importa a app, só lê arquivos.
"""

import pathlib
import re
import sys

RAIZ = pathlib.Path(__file__).resolve().parents[2]
SRC = RAIZ / "frontend" / "src"

falhas: list[str] = []


def checar(ok: bool, descricao: str) -> None:
    print(f"  {'ok  ' if ok else 'FALHOU'}  {descricao}")
    if not ok:
        falhas.append(descricao)


def sem_comentarios(codigo: str) -> str:
    """Comentário que EXPLICA a regra não pode ser confundido com violação dela —
    é a armadilha da v2.71 (o teste reprovava a documentação do próprio
    conserto)."""
    codigo = re.sub(r"\{/\*.*?\*/\}", "", codigo, flags=re.S)
    codigo = re.sub(r"/\*.*?\*/", "", codigo, flags=re.S)
    return re.sub(r"^\s*//.*$", "", codigo, flags=re.M)


# Telas de TRABALHO sobre um registro (§ 8c). Lista explícita, não heurística:
# "é tela de trabalho?" é julgamento, e adivinhar erraria nos dois sentidos.
# Ao criar uma tela nova deste tipo, ACRESCENTE aqui — é o mesmo contrato do
# `TELAS` da régua de largura (v2.62), que já cobrou por não enumerar a tela nova.
TELAS_DE_TRABALHO = ["rh/Detalhe.jsx"]


def main() -> int:
    print("=== 1. Um verde por tela (o ato que FECHA o trabalho) ===")
    for rel in TELAS_DE_TRABALHO:
        arq = SRC / rel
        if not arq.exists():
            checar(False, f"{rel} não encontrado — a lista TELAS_DE_TRABALHO envelheceu?")
            continue
        codigo = sem_comentarios(arq.read_text(encoding="utf-8"))
        verdes = codigo.count("btn-principal")
        # Teto generoso de propósito, e o número não é o que importa: vários
        # destes 9 são de SUBTELAS que nunca aparecem juntas (formulário de
        # criação, ação em massa, editar contato). O que a régua impede é a volta
        # da pilha de verdes no MESMO campo de visão — isso quem mede de verdade
        # é o levantamento de densidade (`checkVisibility`), que registrou
        # 2 → 1 visível. Aqui a contagem estática só segura a regressão grosseira.
        checar(verdes <= 10,
               f"{rel}: {verdes} usos de `btn-principal` no arquivo (teto 10; "
               "o que vale é 1 VISÍVEL por vez — medir com o levantamento)")

    print("\n=== 2. A aba NÃO se guarda em localStorage ===")
    for rel in TELAS_DE_TRABALHO:
        codigo = sem_comentarios((SRC / rel).read_text(encoding="utf-8"))
        # Procura o par "localStorage" + "aba" na MESMA linha: guardar a aba faria
        # a ficha da próxima pessoa abrir onde ninguém pediu.
        suspeitas = [ln.strip()[:90] for ln in codigo.splitlines()
                     if "localStorage" in ln and re.search(r"\baba\b", ln, re.I)]
        checar(not suspeitas,
               f"{rel}: a aba não é persistida em localStorage (achado: {suspeitas})")

    print("\n=== 3. Abas reusam a primitiva `.rh-abas` ===")
    css = (SRC / "styles.css").read_text(encoding="utf-8")
    checar(".rh-abas" in css, "a primitiva `.rh-abas` existe no styles.css")
    for rel in TELAS_DE_TRABALHO:
        codigo = sem_comentarios((SRC / rel).read_text(encoding="utf-8"))
        if "rh-abas" not in codigo:
            continue          # tela sem abas não é violação: nem toda precisa
        # Classe própria de abas = primitiva reinventada (v2.65).
        # `*-aba-*` (com sufixo) é DETALHE dentro da aba — `ficha-aba-conta` é o
        # contador —, não uma primitiva concorrente: o que se proíbe é
        # reimplementar o CONTÊINER (`.minhas-abas`) e o ITEM (`.minha-aba`).
        propria = re.findall(r'className="([a-z-]*-abas?)"', codigo)
        inventadas = [c for c in propria if c != "rh-abas"]
        checar(not inventadas,
               f"{rel}: não inventa classe de aba própria (achado: {inventadas})")

    print("\n=== 4. O resumo de exceções fica FORA do <details> ===")
    # `<details>` fechado nem renderiza o conteúdo (v2.76.2). Se o resumo cair
    # para dentro, ele volta a ser invisível — e o defeito de 11/08 (três
    # exigências médicas dispensadas sem ninguém ver) volta com ele.
    det = SRC / "rh" / "Detalhe.jsx"
    codigo = sem_comentarios(det.read_text(encoding="utf-8"))
    pos_resumo = codigo.find("<ResumoExigenciasDaPessoa")
    checar(pos_resumo != -1,
           "o resumo das exceções é renderizado na ficha")
    if pos_resumo != -1:
        # A prova é POSICIONAL: o resumo tem que aparecer ANTES da abertura do
        # `<details>` que contém o `<Exigencias>`. Se estiver depois, está
        # dentro dele — e um `<details>` fechado não renderiza o conteúdo.
        pos_exig = codigo.find("<Exigencias candidatoId")
        pos_details = codigo.rfind("<details>", 0, pos_exig) if pos_exig != -1 else -1
        checar(pos_details != -1,
               "(premissa) o bloco de exigências está dentro de um <details>")
        checar(pos_details == -1 or pos_resumo < pos_details,
               "o resumo vem ANTES do <details> das exigências — dentro, ele não "
               "renderizaria com o bloco fechado, que é o caso normal")
    checar("ResumoDasExcecoes" in (SRC / "rh" / "Exigencias.jsx").read_text(encoding="utf-8"),
           "o componente de resumo existe em Exigencias.jsx")

    print("\n=== 5. O impedimento é renderizado no topo, antes das abas ===")
    pos_imp = codigo.find("<ImpedimentoDaFicha")
    pos_abas = codigo.find('className="rh-abas"')
    checar(pos_imp != -1, "a ficha renderiza o bloco de impedimento")
    if pos_imp != -1 and pos_abas != -1:
        # O que trava o registro vem ANTES da navegação: ele é a razão de a
        # pessoa ter aberto a ficha, e vale para qualquer aba escolhida.
        checar(pos_imp < pos_abas,
               "o impedimento vem ANTES das abas (vale para todas, e é o motivo da visita)")

    print("\n" + "=" * 62)
    if falhas:
        print(f"REPROVADO — {len(falhas)} verificação(ões) falharam:")
        for f in falhas:
            print(f"  - {f}")
        print("\nVer § 8c de docs/planejamento/08-sistema-de-design.md.")
        return 1
    print("APROVADO — o padrão das telas de trabalho continua valendo.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
