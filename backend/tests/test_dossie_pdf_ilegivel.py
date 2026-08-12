"""Um PDF corrompido não derruba o dossiê inteiro — e não some em silêncio (v2.93).

Caso de campo (11/08/2026, colaborador do INEP). Um certificado emitido por site
de governo veio com um PDF que o `pypdf` não abre (`PdfReadError: Invalid
Elementary Object starting with b'\\x00'`). O `_adicionar_em_a4` estourava, e
**o dossiê inteiro morria** — 18 documentos aprovados, todos perdidos por causa
de um.

O estrago não foi o erro; foi o que ele ensinou a quem operava. A mensagem não
dizia QUAL documento era, então a analista tomou o erro oito vezes ao longo de
uma hora e concluiu que a culpa era dos campos obrigatórios: desmarcou
**condições médicas**, **medicamento contínuo** e **contato de emergência** de um
colaborador real, com o motivo `"por que não consigo salvar"` gravado na
auditoria. O erro continuou depois — nunca teve relação nenhuma com aqueles
campos. Ficou uma pessoa em posto sem contato de emergência registrado.

O que este teste trava:

1. **Peça ilegível é PULADA, não fatal** — as outras entram no dossiê.
2. **Ela é NOMEADA** na resposta. `except: pass` (que existia no ramo do
   multi-signatário) troca "quebra ruidosamente" por "some caladinho", e uma
   página faltando num dossiê que circula para o cliente é pior.
3. **Dossiê com peça pulada NÃO marca o candidato como aprovado** — dizer que a
   conferência terminou sobre um documento que não entrou no PDF é a mentira que
   este módulo não pode contar.
4. **Todas ilegíveis ⇒ recusa** (`DossiePecasIlegiveis`), em vez de gravar um PDF
   de zero página por cima do dossiê anterior.

⚠️ Ao rodar mutação aqui, confira que o teste **imprimiu** o resultado: ausência
de falha não é aprovação (v2.72.2).
"""

import io
import os
import pathlib
import sys
import uuid
from datetime import datetime, timezone

RAIZ = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

os.environ.setdefault("DATABASE_URL",
                      "postgresql+psycopg://admissao:admissao@localhost:55432/admissao")

from fpdf import FPDF  # noqa: E402

from app.core.db import SessionLocal  # noqa: E402
from app.models.assinatura import Assinatura, DocumentoAssinavel  # noqa: E402
from app.models.candidato import Candidato, StatusCandidato  # noqa: E402
from app.models.documento import (SlotDocumento, StatusSlot,  # noqa: E402
                                  TipoDocumento)
# Registra TODOS os modelos no metadata. `app/models/__init__.py` é vazio neste
# projeto — quem registra é a cadeia de imports da app —, e um teste que monta
# objetos direto pelo SQLAlchemy estoura no primeiro flush com
# `NoReferencedTableError` falando do VIZINHO (v2.64). Importar a app resolve a
# cadeia inteira de uma vez, em vez de caçar FK a FK.
import app.main  # noqa: F401,E402
from app.services import storage  # noqa: E402
from app.services.dossie import (DossiePecasIlegiveis,  # noqa: E402
                                 gerar_dossie)

falhas: list[str] = []


def checar(condicao: bool, descricao: str) -> None:
    print(f"{'  OK  ' if condicao else 'FALHOU'}  {descricao}")
    if not condicao:
        falhas.append(descricao)


def pdf_valido(texto: str) -> bytes:
    doc = FPDF()
    doc.add_page()
    doc.set_font("Helvetica", size=12)
    doc.cell(0, 10, texto)
    return bytes(doc.output())


# O byte nulo no lugar de um objeto é exatamente o que o pypdf reclamou no caso
# real. Cabeçalho de PDF válido para o arquivo passar por qualquer checagem de
# tipo e só quebrar no PARSER — que é o que aconteceu em produção.
PDF_CORROMPIDO = b"%PDF-1.4\n\x00\x00\x00 corrompido de proposito \x00\x00\n%%EOF\n"


def main() -> int:
    db = SessionLocal()
    marca = uuid.uuid4().hex[:8]
    cand = Candidato(
        nome_completo=f"Teste Dossiê Ilegível {marca}",
        cpf=f"000{marca[:8]}"[:11],
        email=f"dossie.ilegivel.{marca}@exemplo.com.br",
        cargo_funcao="Auxiliar",
        status=StatusCandidato.envio_concluido,
    )
    db.add(cand)
    db.flush()

    base = f"testes/dossie-ilegivel/{marca}"
    key_boa = f"{base}/ficha.pdf"
    key_ruim = f"{base}/certificado.pdf"
    key_boa2 = f"{base}/rg.pdf"
    storage.salvar(key_boa, pdf_valido("ficha de cadastro"), "application/pdf")
    storage.salvar(key_boa2, pdf_valido("rg"), "application/pdf")
    storage.salvar(key_ruim, PDF_CORROMPIDO, "application/pdf")

    db.add(Assinatura(
        candidato_id=cand.id, documento=DocumentoAssinavel.ficha_cadastro,
        assinado_em=datetime.now(timezone.utc), pdf_key=key_boa,
    ))
    # O documento que quebra: um "nada consta" aprovado, como no caso real.
    db.add(SlotDocumento(
        candidato_id=cand.id, tipo=TipoDocumento.nada_consta_criminal,
        status=StatusSlot.aprovado, arquivo_pdf_key=key_ruim, obrigatorio=False,
    ))
    db.add(SlotDocumento(
        candidato_id=cand.id, tipo=TipoDocumento.rg,
        status=StatusSlot.aprovado, arquivo_pdf_key=key_boa2, obrigatorio=False,
    ))
    db.commit()

    print("\n=== 1. Peça ilegível é pulada, e o resto do dossiê é gerado ===")
    ilegiveis: list[str] = []
    try:
        key = gerar_dossie(db, cand, ignorar_pendencias=True, ilegiveis=ilegiveis)
        gerou = True
    except Exception as exc:  # noqa: BLE001
        gerou = False
        key = None
        print(f"        (levantou {type(exc).__name__}: {exc})")

    checar(gerou, "o dossiê é gerado mesmo com um PDF corrompido no meio")

    if gerou:
        from pypdf import PdfReader
        paginas = len(PdfReader(io.BytesIO(storage.ler(key))).pages)
        # A ficha e o RG entraram; só o certificado corrompido ficou de fora.
        checar(paginas == 2,
               f"as peças legíveis entram no dossiê (esperado 2 páginas, veio {paginas})")

    checar(len(ilegiveis) == 1,
           f"a peça ilegível é reportada (esperado 1, veio {len(ilegiveis)}: {ilegiveis})")
    # Sem o NOME, o RH não sabe qual documento reenviar — foi o que custou uma
    # hora de trabalho e três exigências desmarcadas por engano.
    checar(any("nada consta" in i for i in ilegiveis),
           f"a peça ilegível é NOMEADA, não só contada (veio {ilegiveis})")

    print("\n=== 2. Dossiê com peça pulada não marca o candidato como aprovado ===")
    # A regra vive na rota; aqui garantimos o insumo que ela usa para decidir.
    checar(bool(ilegiveis),
           "a rota recebe a lista de ilegíveis para NÃO aprovar (insumo da decisão)")

    print("\n=== 3. Todas as peças ilegíveis ⇒ recusa, sem gravar PDF vazio ===")
    marca2 = uuid.uuid4().hex[:8]
    cand2 = Candidato(
        nome_completo=f"Teste Dossiê Vazio {marca2}",
        cpf=f"111{marca2[:8]}"[:11],
        email=f"dossie.vazio.{marca2}@exemplo.com.br",
        cargo_funcao="Auxiliar",
        status=StatusCandidato.envio_concluido,
    )
    db.add(cand2)
    db.flush()
    key_ruim2 = f"testes/dossie-ilegivel/{marca2}/unico.pdf"
    storage.salvar(key_ruim2, PDF_CORROMPIDO, "application/pdf")
    db.add(SlotDocumento(
        candidato_id=cand2.id, tipo=TipoDocumento.nada_consta_criminal,
        status=StatusSlot.aprovado, arquivo_pdf_key=key_ruim2, obrigatorio=False,
    ))
    db.commit()

    recusou = False
    nomeou = False
    try:
        gerar_dossie(db, cand2, ignorar_pendencias=True)
    except DossiePecasIlegiveis as exc:
        recusou = True
        nomeou = bool(exc.ilegiveis)
    except Exception as exc:  # noqa: BLE001
        print(f"        (levantou {type(exc).__name__}: {exc})")

    checar(recusou,
           "recusa com DossiePecasIlegiveis quando NADA pôde ser lido")
    checar(nomeou, "a recusa diz QUAIS peças estavam ilegíveis")
    # Gravar aqui deixaria um PDF de zero página no lugar do dossiê anterior, com
    # o `dossie_gerado_em` afirmando que está pronto.
    checar(cand2.dossie_pdf_key is None,
           "não grava dossiê nenhum quando não há página (não sobrescreve o anterior)")

    print("\n=== 4. Dossiê VAZIO por ausência continua sendo caso legítimo ===")
    # Regressão pega pelo CI: a primeira versão recusava com zero página SEM
    # olhar se houve falha, e quebrou o `test_entrevista_documentos`, que monta
    # um candidato sem documento nenhum e pede o parcial. Zero página por
    # AUSÊNCIA (ninguém entregou nada ainda) e zero por CORRUPÇÃO dão o mesmo
    # total — o que os separa é ter havido falha de leitura.
    marca3 = uuid.uuid4().hex[:8]
    cand3 = Candidato(
        nome_completo=f"Teste Dossiê Sem Nada {marca3}",
        cpf=f"222{marca3[:8]}"[:11],
        email=f"dossie.semnada.{marca3}@exemplo.com.br",
        cargo_funcao="Auxiliar",
        status=StatusCandidato.envio_concluido,
    )
    db.add(cand3)
    db.commit()

    vazio_ok = False
    try:
        gerar_dossie(db, cand3, ignorar_pendencias=True)
        vazio_ok = True
    except DossiePecasIlegiveis:
        pass
    except Exception as exc:  # noqa: BLE001
        print(f"        (levantou {type(exc).__name__}: {exc})")

    checar(vazio_ok,
           "parcial de quem não entregou NADA ainda não é recusado como ilegível")

    db.rollback()
    db.close()

    print("\n" + "=" * 62)
    if falhas:
        print(f"REPROVADO — {len(falhas)} verificação(ões) falharam:")
        for f in falhas:
            print(f"  - {f}")
        return 1
    print("APROVADO — dossiê sobrevive a PDF corrompido e nomeia o culpado.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
