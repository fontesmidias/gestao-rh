"""Montagem do dossiê único: fichas assinadas (1-3) + documentos aprovados na ordem oficial."""

import io
from datetime import datetime, timezone

from pypdf import PdfReader, PdfWriter, Transformation
from pypdf._page import PageObject
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.assinatura import Assinatura, DocumentoAssinavel
from app.models.candidato import Candidato
from app.models.documento import SlotDocumento, StatusSlot, TipoDocumento
from app.services import storage

# Ordem oficial definida pelo RH (docs/planejamento/01-visao-e-decisoes.md).
ORDEM_FICHAS = (
    DocumentoAssinavel.ficha_cadastro,
    DocumentoAssinavel.ficha_emergencia,
    DocumentoAssinavel.termo_vt,
    DocumentoAssinavel.acordo_confidencialidade,
)
ORDEM_DOCUMENTOS = (
    TipoDocumento.foto_3x4,
    TipoDocumento.rg,
    TipoDocumento.cpf_doc,
    TipoDocumento.ctps_digital,
    TipoDocumento.pis_comprovante,
    TipoDocumento.titulo_eleitor_doc,
    TipoDocumento.reservista,
    TipoDocumento.habilitacao_prof,
    TipoDocumento.laudo_pcd,
    TipoDocumento.comp_endereco,
    TipoDocumento.comp_escolaridade,
    TipoDocumento.diplomas,
    TipoDocumento.nada_consta_eleitoral,
    TipoDocumento.nada_consta_criminal,
    TipoDocumento.cert_casamento,
    TipoDocumento.cert_nascimento_dep,
    TipoDocumento.cartao_vacina_dep,
    TipoDocumento.declaracao_escolar_dep,
    TipoDocumento.cartao_vt,
)


# A4 em pontos (72 dpi)
A4_LARGURA, A4_ALTURA = 595.276, 841.890


def _adicionar_em_a4(writer: PdfWriter, pdf_bytes: bytes) -> None:
    """Adiciona cada página redimensionada proporcionalmente e centrada em A4 retrato —
    dossiê inteiro padronizado, independentemente do tamanho/orientação do original."""
    reader = PdfReader(io.BytesIO(pdf_bytes))
    for pagina in reader.pages:
        largura = float(pagina.mediabox.width)
        altura = float(pagina.mediabox.height)
        if abs(largura - A4_LARGURA) < 2 and abs(altura - A4_ALTURA) < 2:
            writer.add_page(pagina)
            continue
        escala = min(A4_LARGURA / largura, A4_ALTURA / altura)
        dx = (A4_LARGURA - largura * escala) / 2
        dy = (A4_ALTURA - altura * escala) / 2
        base = PageObject.create_blank_page(width=A4_LARGURA, height=A4_ALTURA)
        base.merge_transformed_page(
            pagina, Transformation().scale(escala).translate(dx, dy)
        )
        writer.add_page(base)


class DossieIncompleto(Exception):
    def __init__(self, pendencias: list[str]):
        self.pendencias = pendencias
        super().__init__(", ".join(pendencias))


class DossiePecasIlegiveis(Exception):
    """Nenhuma peça pôde ser lida — não há dossiê nenhum a gravar. Distinto de
    `DossieIncompleto` (que é 'falta documento'): aqui os documentos EXISTEM e
    estão corrompidos, e o que resolve é reenviá-los, não cobrá-los."""

    def __init__(self, ilegiveis: list[str]):
        self.ilegiveis = ilegiveis
        super().__init__(", ".join(ilegiveis))


def _rotulo(doc) -> str:
    """Nome legível de um documento/ficha para a mensagem do RH. O `.value` do
    enum ('nada_consta_criminal') não se lê na tela."""
    return str(getattr(doc, "value", doc)).replace("_", " ")


def pendencias_do_dossie(db: Session, candidato: Candidato) -> list[str]:
    """O que ainda falta para o dossiê ficar completo — SEM gerar nada. Usado
    pelo módulo de diagnóstico ('por que o dossiê não gerou?') e pela própria
    geração. Fichas não assinadas viram 'ficha:<doc>'; slots obrigatórios não
    aprovados/dispensados viram 'documento:<tipo>'."""
    assinados = {
        a.documento for a in db.scalars(
            select(Assinatura).where(
                Assinatura.candidato_id == candidato.id, Assinatura.assinado_em.isnot(None),
                Assinatura.invalidada_em.is_(None),
            )
        )
    }
    slots = db.scalars(
        select(SlotDocumento).where(SlotDocumento.candidato_id == candidato.id)
    ).all()
    pendencias = [f"ficha:{d.value}" for d in ORDEM_FICHAS if d not in assinados]
    pendencias += [
        f"documento:{s.tipo.value}"
        for s in slots
        if s.obrigatorio and s.status not in (StatusSlot.aprovado, StatusSlot.dispensado)
    ]
    return pendencias


def gerar_dossie(db: Session, candidato: Candidato, ignorar_pendencias: bool = False,
                 ilegiveis: list[str] | None = None) -> str:
    """Monta e grava o PDF único; devolve a key no MinIO. Exige fichas assinadas e
    todos os slots obrigatórios aprovados (ou dispensados) — salvo se o RH optar
    por gerar parcial (ignorar_pendencias=True), incluindo só o que existe.

    `ilegiveis` (se passado) recebe o nome de cada peça que NÃO pôde ser lida —
    PDF corrompido, arquivo sumido do storage. Elas são PULADAS em vez de
    derrubar o dossiê inteiro, mas quem chama precisa dizer isso na tela:
    dossiê a que falta uma página não pode se apresentar como completo.

    Por que pular em vez de estourar (v2.93, caso de campo 11/08/2026): um
    certificado emitido por site de governo veio com PDF que o pypdf não abre,
    e o dossiê inteiro morria em `PdfReadError`. A operadora tomou o erro 8×,
    não tinha como saber QUAL documento era, e concluiu que a culpa era dos
    campos obrigatórios — desmarcou condição médica, medicamento contínuo e
    contato de emergência de um colaborador real, tentando destravar. O erro
    não tinha relação nenhuma com isso, e continuou depois."""
    assinaturas = {
        a.documento: a
        for a in db.scalars(
            select(Assinatura).where(
                Assinatura.candidato_id == candidato.id, Assinatura.assinado_em.isnot(None),
                Assinatura.invalidada_em.is_(None),
            )
        )
    }
    slots = db.scalars(
        select(SlotDocumento).where(SlotDocumento.candidato_id == candidato.id)
    ).all()

    pendencias = pendencias_do_dossie(db, candidato)
    if pendencias and not ignorar_pendencias:
        raise DossieIncompleto(pendencias)

    from app.services.ordem_assinatura import ordem_fichas
    import logging
    log = logging.getLogger(__name__)
    if ilegiveis is None:
        ilegiveis = []

    def _juntar(key: str, rotulo: str) -> None:
        """Anexa uma peça ao dossiê. Peça ilegível é PULADA e NOMEADA — nunca
        derruba o dossiê inteiro, e nunca some em silêncio (`except: pass` aqui
        faria o dossiê sair com uma página a menos sem ninguém perceber)."""
        try:
            _adicionar_em_a4(writer, storage.ler(key))
        except Exception as exc:
            log.warning("Dossiê de %s: peça ilegível %r (%s): %s",
                        candidato.id, rotulo, key, exc)
            ilegiveis.append(rotulo)

    writer = PdfWriter()
    for doc in ordem_fichas(db):
        if doc in assinaturas:
            _juntar(assinaturas[doc].pdf_key, _rotulo(doc))

    # Documentos de roteiro multi-signatário concluídos: inclui o PDF final
    # consolidado (com todas as assinaturas) logo após as fichas.
    from app.models.solicitacao_assinatura import (SolicitacaoAssinatura,
                                                   StatusSolicitacao)
    for sol in db.scalars(select(SolicitacaoAssinatura).where(
            SolicitacaoAssinatura.candidato_id == candidato.id,
            SolicitacaoAssinatura.status == StatusSolicitacao.concluida,
            SolicitacaoAssinatura.pdf_final_key.isnot(None))).all():
        _juntar(sol.pdf_final_key, sol.titulo_doc or "documento assinado por vários")

    ordem = {tipo: i for i, tipo in enumerate(ORDEM_DOCUMENTOS)}
    aprovados = sorted(
        (s for s in slots if s.status == StatusSlot.aprovado and s.arquivo_pdf_key),
        key=lambda s: (ordem.get(s.tipo, 99), s.criado_em),
    )
    for slot in aprovados:
        _juntar(slot.arquivo_pdf_key, _rotulo(slot.tipo))

    # Nenhuma página entrou: TODAS as peças eram ilegíveis. Gravar aqui
    # substituiria o dossiê anterior por um PDF de zero página — o RH baixaria
    # um arquivo que não abre e o `dossie_gerado_em` diria que está pronto.
    if len(writer.pages) == 0:
        raise DossiePecasIlegiveis(ilegiveis)

    key = f"candidatos/{candidato.id}/dossie.pdf"
    saida = io.BytesIO()
    writer.write(saida)
    storage.salvar(key, saida.getvalue(), "application/pdf")
    candidato.dossie_pdf_key = key
    candidato.dossie_gerado_em = datetime.now(timezone.utc)
    return key
