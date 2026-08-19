"""Gravação do comprovante MENSAL do creche — 1..N folhas viram um PDF.

Separado do `creche_competencia.py` (que é regra pura, sem I/O) porque este
mexe em storage e auditoria.

**Por que multi-folhas.** Até aqui o creche gravava UM arquivo por tipo, com key
fixa (`creche/{ben}/{crianca}/{tipo}.pdf`): reenviar SOBRESCREVIA, e não havia
como guardar a segunda folha de uma declaração ou de um termo. Era a causa do
*"não consigo ver se há mais de uma folha"* — não havia. A admissão já resolvia
isso desde sempre (`documentos.py::_gravar_partes_no_slot`), mas aquela função é
acoplada a `SlotDocumento`/`Candidato` e não dá para reusar direto; o que se
reusa aqui é o DESENHO — originais numerados + PDF combinado — e as funções
`normalizar_para_pdf`/`combinar_pdfs`, que são compartilhadas de verdade.

**Nada some sem hash na auditoria** (linha vermelha do projeto): o reenvio
expurga o anterior gravando antes o SHA-256, o tamanho e o caminho de cada
arquivo removido.

⚠️ Ao contrário do wizard, falha de normalização **não recusa** o envio: cai no
arquivo original. É a mesma decisão da v2.61 para creche e portal — recusar aqui
deixaria a pessoa sem conseguir comprovar a despesa por causa da qualidade de
uma foto, e o benefício travaria pela foto, não pelo direito.
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.services import storage
from app.services.auditoria import registrar


def prefixo(competencia_id) -> str:
    return f"creche/competencias/{competencia_id}"


def expurgar(db: Session, competencia, evento: str, ator: str,
             ator_detalhe: str | None = None) -> None:
    """Remove os arquivos da competência, com hash na auditoria ANTES.

    Chamado no reenvio: o comprovante do mês é ÚNICO (há `UniqueConstraint` por
    criança/mês), então mandar de novo substitui — e o que sai tem de deixar
    rastro, porque é peça de comprovação de despesa.
    """
    base = prefixo(competencia.id) + "/"
    try:
        keys = storage.listar(base)
    except Exception:
        keys = [k for k in (competencia.arquivo_pdf_key,) if k]

    evidencias = []
    for key in keys:
        try:
            dados = storage.ler(key)
            evidencias.append({"arquivo": key,
                               "sha256": hashlib.sha256(dados).hexdigest(),
                               "bytes": len(dados)})
        except Exception:
            evidencias.append({"arquivo": key, "sha256": None, "bytes": None})
    if evidencias:
        registrar(db, evento, ator=ator, ator_detalhe=ator_detalhe,
                  detalhe={"competencia": str(competencia.id),
                           "arquivos": evidencias})
    for key in keys:
        try:
            storage.remover(key)
        except Exception:
            # Um arquivo que já não está lá não pode impedir o reenvio: a
            # auditoria acima já registrou o que existia.
            pass


def gravar(db: Session, competencia, partes: list[tuple[str, bytes]],
           ator: str, ator_detalhe: str | None = None) -> int:
    """Grava as folhas do comprovante e devolve o total de PÁGINAS do PDF.

    Páginas, não arquivos: um PDF de três folhas enviado como arquivo único
    conta 3, e é esse o número que responde "quantas folhas tem?".

    `partes` é uma lista de `(nome_do_arquivo, bytes)` — uma foto por folha, ou
    um PDF só. Guarda cada ORIGINAL numerado (`original/01-…`, `original/02-…`) e
    o PDF combinado, que é o que o RH lê e o que entra no dossiê.

    ⚠️ Os originais são numerados com ZERO À ESQUERDA (`01-`, `02-`): a listagem
    do storage é lexicográfica e, sem isso, `10-` vem antes de `2-` — a folha na
    ordem errada num documento de comprovação (a armadilha da v2.35).
    """
    from app.services.normalizacao import combinar_pdfs, normalizar_para_pdf

    if competencia.arquivo_pdf_key:
        expurgar(db, competencia, evento="creche_comprovante_substituido",
                 ator=ator, ator_detalhe=ator_detalhe)

    base = prefixo(competencia.id)
    pdfs: list[bytes] = []
    for i, (nome, dados) in enumerate(partes, start=1):
        storage.salvar(f"{base}/original/{i:02d}-{nome}", dados,
                       "application/octet-stream")
        try:
            pdf, _paginas = normalizar_para_pdf(nome, dados,
                                                rotulo="Comprovante de despesa")
        except Exception:
            # Formato exótico ou PDF protegido: guarda o que veio. O RH ainda vê
            # o arquivo; só não sai timbrado. Recusar travaria a comprovação.
            pdf = dados
        pdfs.append(pdf)

    # `combinar_pdfs` devolve (bytes, TOTAL DE PÁGINAS) e já trata a lista de um
    # só — não chamá-la no caso de 1 arquivo gravaria a tupla como se fosse
    # bytes, e contaria ARQUIVOS no lugar de páginas (uma foto de 3 folhas em
    # PDF único apareceria como "1 página").
    final, paginas = combinar_pdfs(pdfs)
    key = f"{base}/comprovante.pdf"
    storage.salvar(key, final, "application/pdf")

    competencia.arquivo_pdf_key = key
    competencia.paginas = paginas
    competencia.enviado_em = datetime.now(timezone.utc)
    competencia.enviado_por = ator_detalhe or ator
    return paginas


def originais(competencia) -> list[str]:
    """As keys das folhas ORIGINAIS, na ordem em que foram enviadas.

    Existe porque o registro guarda só o PDF combinado: perguntar "quantas
    folhas tem?" ao campo daria a resposta errada. Listar pelo PREFIXO é o que
    enxerga todas — a lição da v2.35, onde o expurgo deixava o verso do RG no
    storage para sempre por olhar um campo só.
    """
    try:
        return sorted(storage.listar(prefixo(competencia.id) + "/original/"))
    except Exception:
        return []
