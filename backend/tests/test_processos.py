"""Carteira de Processos: quem responde quando o titular sai (v2.91).

O módulo existe para uma pergunta do Bruno: *"caso haja algum funcionário
substituído, indo embora do RH ou qualquer outra coisa, tenha uma organização
de processos"*. O que este teste protege é justamente o que a planilha NÃO
consegue fazer sozinha:

1. **A cadeia responde sozinha.** Esvaziar a função do titular faz o processo
   passar ao próximo — sem ninguém redistribuir carteira. Se isso quebrar, o
   módulo vira uma planilha web: mostra o titular que saiu como se ainda
   respondesse, e ninguém percebe até alguém procurá-lo.
2. **Reimportar ATUALIZA, não duplica.** A carteira é revisada por trimestre;
   importação que duplica a cada revisão inutiliza o módulo em três meses.
3. **O rodízio não é processo órfão.** Os processos 9.1 e 9.2 têm "Escala
   diária (rodízio)" como titular de propósito. Acusá-los como "sem dono"
   seria alarme falso — e alarme falso ensina a ignorar o alarme, deixando
   passar o processo realmente órfão.
4. **Nada é ignorado em silêncio.** Linha que o parser não usa vira item na
   lista de `ignoradas`, com o motivo: importação que "funciona" e descarta
   oito linhas é pior que uma que falha.

O teste roda contra a PLANILHA REAL do Bruno (`docs/Processos do RH/`), não
contra um arquivo montado à mão: cópia inventada passa a divergir do arquivo de
verdade na primeira revisão dele, e o teste segue verde (a lição da v2.54).
"""

import os
import sys
import pathlib

RAIZ = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

os.environ.setdefault("DATABASE_URL",
                      "postgresql+psycopg://admissao:admissao@localhost:55432/admissao")

from sqlalchemy import select  # noqa: E402

from app.api.incidencia_beneficios import _ler_abas  # noqa: E402
from app.core.db import SessionLocal  # noqa: E402
from app.models.processo import FuncaoRH, Processo  # noqa: E402
from app.services import importar_carteira as imp  # noqa: E402
from app.services import processos as sv  # noqa: E402

PLANILHA = RAIZ.parent / "docs" / "Processos do RH" / "Carteira_Processos_RH_MatrizRACI 3.xlsx"


def main() -> int:
    if not PLANILHA.exists():
        # Anuncia a pré-condição em vez de falhar numa asserção que não fala da
        # causa (regra da v2.84). O `docs/` não vai ao repositório público.
        print(f"PULADO — a planilha não está em {PLANILHA}. "
              "Este teste precisa do arquivo real da carteira.")
        return 0

    falhas: list[str] = []
    db = SessionLocal()
    try:
        abas = _ler_abas(PLANILHA.read_bytes())
        previa = imp.analisar(abas, db)

        # 4. Nada ignorado em silêncio.
        if previa.ignoradas:
            falhas.append(
                f"{len(previa.ignoradas)} linha(s) da planilha real não foram "
                f"lidas: {previa.ignoradas[:3]}")
        if set(previa.cenarios) != {"C1", "C2"}:
            falhas.append(f"esperava os dois cenários, veio {previa.cenarios}")

        imp.aplicar(db, previa)
        db.commit()
        total = len(db.scalars(select(Processo)).all())
        if total < 30:
            falhas.append(f"esperava ~32 processos da carteira real, veio {total}")

        # 2. Reimportar ATUALIZA, não duplica.
        imp.aplicar(db, imp.analisar(abas, db))
        db.commit()
        depois = len(db.scalars(select(Processo)).all())
        if depois != total:
            falhas.append(
                f"reimportar duplicou: {total} → {depois}. A carteira é revisada "
                "por trimestre; duplicar a cada revisão inutiliza o módulo.")

        # 1. A REGRA CENTRAL: o titular sai, a cadeia responde.
        p = db.scalar(select(Processo).where(Processo.codigo == "1.1"))
        if p is None:
            falhas.append("o processo 1.1 não foi importado")
        else:
            antes = sv.dump_processo(db, p, "C1")
            titular = antes["titular"]
            if not titular:
                falhas.append("o processo 1.1 ficou sem titular na importação")
            else:
                f = db.scalar(select(FuncaoRH).where(FuncaoRH.nome == titular))
                guardado = f.pessoa_nome
                f.pessoa_nome = None          # a titular saiu do RH
                db.commit()
                depois_ = sv.dump_processo(db, p, "C1")
                if depois_["sem_dono"]:
                    falhas.append(
                        "com o titular fora, o processo ficou SEM DONO — a "
                        "cadeia de substituição não está sendo percorrida.")
                elif not depois_["assumido"]:
                    falhas.append(
                        f"ninguém assumiu no lugar de {titular}: responsável "
                        f"continua {depois_['responsavel']!r}.")
                f.pessoa_nome = guardado      # devolve o estado (v2.66)
                db.commit()

        # 3. Rodízio não é órfão.
        r = db.scalar(select(Processo).where(Processo.codigo == "9.1"))
        if r is not None:
            d = sv.dump_processo(db, r, "C1")
            if not d["rodizio"]:
                falhas.append("o 9.1 deveria ser reconhecido como rodízio")
            if d["sem_dono"]:
                falhas.append(
                    "o 9.1 (rodízio) foi acusado de 'sem dono' — alarme falso "
                    "ensina a ignorar o alarme.")

        # A carga precisa distinguir titularidade de apoio: somar os dois
        # esconderia o que a Coordenação usa para redistribuir.
        carga = sv.carga_por_funcao(db, "C1")
        if not any(c["dono"] and c["apoio"] for c in carga):
            falhas.append("a carga não separou titularidade de apoio.")
    finally:
        db.close()

    if falhas:
        print("FALHOU:")
        for f in falhas:
            print("  •", f)
        return 1
    print("OK — a carteira real importa sem perdas, reimportar atualiza, e a\n"
          "     cadeia responde sozinha quando o titular sai.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
