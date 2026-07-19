"""Menu 🗄️ Arquivo: inventário com filtros, download individual e backup em
lote (ZIP + planilha XLSX) do que o sistema já guarda (dossiês, vias assinadas,
documentos aprovados, dados estruturados). Leitura pura — não gera nem altera
nada. Toda exportação é auditada com a lista de quem foi exportado (LGPD)."""

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Response
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.auth_rh import requer_rh
from app.core.db import get_db
from app.models.assinatura import Assinatura
from app.models.candidato import Candidato, PostoServico, StatusCandidato
from app.models.documento import SlotDocumento, StatusSlot
from app.models.ficha import DocumentosIdentificacao
from app.models.usuario_rh import UsuarioRH
from app.services import storage
from app.services.auditoria import registrar
from app.services.export_planilha import linha_completa, montar_workbook, slug
from app.services.zip_stream import gerar_zip

router = APIRouter(tags=["arquivo-rh"], dependencies=[Depends(requer_rh)])

TETO_PESSOAS_LOTE = 500  # protege memória/tempo; acima disso, refinar o filtro


# ---------------------------------------------------------------------------
# Filtro (próprio — NÃO é o _filtrar de colaboradores; ver críticas do design)
# ---------------------------------------------------------------------------


def _cpf_mascarado(cpf: str | None) -> str:
    n = "".join(c for c in (cpf or "") if c.isdigit())
    return f"***.{n[3:6]}.{n[6:9]}-**" if len(n) == 11 else "—"


def _filtrar_pessoas(db: Session, *, posto_id=None, cargo=None, situacao=None,
                     status=None, desde=None, ate=None, busca=None) -> list[Candidato]:
    """Filtra Candidato para o arquivo. Inclui admissão E colaboradores (o
    arquivo abrange todos). `situacao='em_admissao'` -> situacao IS NULL.
    `desde/ate` (YYYY-MM-DD) filtram por criado_em (datetime) no SQL —
    data_admissao é string dd/mm/aaaa e NÃO é comparável aqui."""
    q = select(Candidato).order_by(Candidato.criado_em.desc())
    if posto_id:
        q = q.where(Candidato.posto_servico_id == posto_id)
    if cargo:
        q = q.where(Candidato.cargo_funcao == cargo)
    if situacao == "em_admissao":
        q = q.where(Candidato.situacao.is_(None))
    elif situacao:
        q = q.where(Candidato.situacao == situacao)
    if status:
        try:
            q = q.where(Candidato.status == StatusCandidato(status))
        except ValueError:
            pass
    if desde:
        q = q.where(Candidato.criado_em >= _dia(desde))
    if ate:
        q = q.where(Candidato.criado_em <= _dia(ate, fim=True))
    pessoas = db.scalars(q).all()
    if busca:
        termo = busca.strip().lower()
        digitos = "".join(c for c in termo if c.isdigit())
        cpfs = {}
        if digitos:
            for d in db.scalars(select(DocumentosIdentificacao)).all():
                cpfs[d.candidato_id] = d.cpf or ""
        pessoas = [c for c in pessoas
                   if termo in (c.nome_completo or "").lower()
                   or termo in (c.email or "").lower()
                   or (digitos and (digitos in "".join(x for x in (c.cpf or "") if x.isdigit())
                                    or digitos in cpfs.get(c.id, "")))]
    return pessoas


def _dia(texto: str, fim: bool = False) -> datetime:
    d = datetime.strptime(texto, "%Y-%m-%d")
    if fim:
        d = d.replace(hour=23, minute=59, second=59)
    return d.replace(tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# Contagens agregadas (uma query cada — sem N+1)
# ---------------------------------------------------------------------------


def _contagens(db: Session, ids: list[uuid.UUID]) -> tuple[dict, dict, dict]:
    """(assinaturas válidas por candidato, slots aprovados por candidato,
    dossiê existe por candidato) — cada um numa query só."""
    if not ids:
        return {}, {}, {}
    assin = dict(db.execute(
        select(Assinatura.candidato_id, func.count(Assinatura.id))
        .where(Assinatura.candidato_id.in_(ids),
               Assinatura.assinado_em.isnot(None),
               Assinatura.invalidada_em.is_(None))
        .group_by(Assinatura.candidato_id)).all())
    slots = dict(db.execute(
        select(SlotDocumento.candidato_id, func.count(SlotDocumento.id))
        .where(SlotDocumento.candidato_id.in_(ids),
               SlotDocumento.status == StatusSlot.aprovado,
               SlotDocumento.arquivo_pdf_key.isnot(None))
        .group_by(SlotDocumento.candidato_id)).all())
    return assin, slots, {}


# ---------------------------------------------------------------------------
# Inventário
# ---------------------------------------------------------------------------


@router.get("/rh/arquivo/inventario")
def inventario(posto_id: uuid.UUID | None = None, cargo: str | None = None,
               situacao: str | None = None, status: str | None = None,
               desde: str | None = None, ate: str | None = None,
               busca: str | None = None, db: Session = Depends(get_db)) -> dict:
    """Uma linha por pessoa com o que existe guardado (contagens), sem tocar no
    MinIO. Contagens via query agregada (sem N+1)."""
    pessoas = _filtrar_pessoas(db, posto_id=posto_id, cargo=cargo, situacao=situacao,
                               status=status, desde=desde, ate=ate, busca=busca)
    ids = [c.id for c in pessoas]
    assin, slots, _ = _contagens(db, ids)
    postos = {p.id: p.nome for p in db.scalars(select(PostoServico)).all()}
    # CPF nativo, ou da ficha quando faltar (um lookup para os que faltam)
    faltam = [c.id for c in pessoas if not c.cpf]
    cpf_ficha = {}
    if faltam:
        for d in db.scalars(select(DocumentosIdentificacao)
                            .where(DocumentosIdentificacao.candidato_id.in_(faltam))).all():
            cpf_ficha[d.candidato_id] = d.cpf
    linhas = []
    for c in pessoas:
        linhas.append({
            "id": c.id, "nome_completo": c.nome_completo,
            "cpf_mascarado": _cpf_mascarado(c.cpf or cpf_ficha.get(c.id)),
            "posto_nome": postos.get(c.posto_servico_id),
            "cargo_funcao": c.cargo_funcao,
            "situacao": c.situacao or "em admissão",
            "dossie_gerado_em": c.dossie_gerado_em,
            "tem_dossie": bool(c.dossie_pdf_key),
            "assinados": assin.get(c.id, 0),
            "aprovados": slots.get(c.id, 0),
        })
    return {
        "metricas": {
            "pessoas": len(linhas),
            "com_dossie": sum(1 for l in linhas if l["tem_dossie"]),
            "vias_assinadas": sum(l["assinados"] for l in linhas),
            "docs_aprovados": sum(l["aprovados"] for l in linhas),
        },
        "pessoas": linhas,
        "cargos": sorted({c.cargo_funcao for c in db.scalars(
            select(Candidato).where(Candidato.cargo_funcao.isnot(None)))} - {None, ""}),
    }


# ---------------------------------------------------------------------------
# Download individual
# ---------------------------------------------------------------------------


def _baixar(db: Session, key: str | None, nome_arquivo: str) -> Response:
    if not key:
        raise HTTPException(status_code=404, detail="arquivo_sem_key")
    try:
        conteudo = storage.ler(key)
    except Exception:
        raise HTTPException(status_code=404, detail="arquivo_nao_encontrado")
    return Response(content=conteudo, media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="{nome_arquivo}"'})


@router.get("/rh/arquivo/pessoa/{cid}/dossie")
def baixar_dossie(cid: uuid.UUID, db: Session = Depends(get_db),
                  rh: UsuarioRH = Depends(requer_rh)) -> Response:
    c = db.get(Candidato, cid)
    if c is None:
        raise HTTPException(status_code=404, detail="candidato_nao_encontrado")
    registrar(db, "arquivo_exportado_individual", ator="rh", ator_detalhe=rh.email,
              candidato_id=cid, detalhe={"tipo": "dossie"})
    db.commit()
    return _baixar(db, c.dossie_pdf_key, f"dossie-{slug(c.nome_completo)}.pdf")


@router.get("/rh/arquivo/pessoa/{cid}/assinatura/{assinatura_id}")
def baixar_assinatura(cid: uuid.UUID, assinatura_id: uuid.UUID,
                      db: Session = Depends(get_db),
                      rh: UsuarioRH = Depends(requer_rh)) -> Response:
    a = db.get(Assinatura, assinatura_id)
    if a is None or a.candidato_id != cid:
        raise HTTPException(status_code=404, detail="assinatura_nao_encontrada")
    from app.api.assinaturas import titulo_doc
    registrar(db, "arquivo_exportado_individual", ator="rh", ator_detalhe=rh.email,
              candidato_id=cid, detalhe={"tipo": "assinatura", "id": str(assinatura_id)})
    db.commit()
    return _baixar(db, a.pdf_key, f"{slug(titulo_doc(a))}.pdf")


@router.get("/rh/arquivo/pessoa/{cid}/slot/{slot_id}")
def baixar_slot(cid: uuid.UUID, slot_id: uuid.UUID, db: Session = Depends(get_db),
                rh: UsuarioRH = Depends(requer_rh)) -> Response:
    s = db.get(SlotDocumento, slot_id)
    if s is None or s.candidato_id != cid:
        raise HTTPException(status_code=404, detail="documento_nao_encontrado")
    registrar(db, "arquivo_exportado_individual", ator="rh", ator_detalhe=rh.email,
              candidato_id=cid, detalhe={"tipo": "slot", "id": str(slot_id)})
    db.commit()
    return _baixar(db, s.arquivo_pdf_key, f"{slug(s.tipo.value)}.pdf")


# ---------------------------------------------------------------------------
# Lote (ZIP + XLSX) — TUDO resolvido antes do stream (db não é usado no gerador)
# ---------------------------------------------------------------------------


class PedidoLote(BaseModel):
    ids: list[uuid.UUID] | None = None
    filtro: dict | None = None
    tipos: list[str] = ["dossie", "assinados", "aprovados", "ficha"]
    incluir_planilha: bool = True


def _resolver_lote(db: Session, pedido: PedidoLote) -> list[Candidato]:
    if pedido.ids:
        pessoas = [db.get(Candidato, i) for i in pedido.ids]
        return [c for c in pessoas if c is not None]
    if pedido.filtro:
        f = pedido.filtro
        return _filtrar_pessoas(db, posto_id=f.get("posto_id"), cargo=f.get("cargo"),
                                situacao=f.get("situacao"), status=f.get("status"),
                                desde=f.get("desde"), ate=f.get("ate"), busca=f.get("busca"))
    raise HTTPException(status_code=400, detail="selecao_vazia")


@router.post("/rh/arquivo/lote/estimativa")
def estimativa(pedido: PedidoLote, db: Session = Depends(get_db)) -> dict:
    """Preflight: quantas pessoas, quantos arquivos e MB aproximados — para a UI
    avisar antes de um ZIP grande. Vai ao MinIO só para somar tamanhos."""
    pessoas = _resolver_lote(db, pedido)
    total_bytes = 0
    arquivos = 0
    for c in pessoas:
        for key, tam in storage.listar_detalhado(f"candidatos/{c.id}/"):
            total_bytes += tam
            arquivos += 1
    return {"pessoas": len(pessoas), "arquivos": arquivos,
            "tamanho_mb": round(total_bytes / (1024 * 1024), 1),
            "acima_do_teto": len(pessoas) > TETO_PESSOAS_LOTE}


@router.post("/rh/arquivo/lote")
def exportar_lote(pedido: PedidoLote, db: Session = Depends(get_db),
                  rh: UsuarioRH = Depends(requer_rh)) -> StreamingResponse:
    """Backup em lote: ZIP com dossiês/vias assinadas/documentos aprovados
    organizados por posto/pessoa + planilha XLSX. Tudo do banco é resolvido
    AGORA (o gerador do ZIP só toca o MinIO, nunca a sessão)."""
    pessoas = _resolver_lote(db, pedido)
    if not pessoas:
        raise HTTPException(status_code=400, detail="selecao_vazia")
    if len(pessoas) > TETO_PESSOAS_LOTE:
        raise HTTPException(status_code=413, detail="lote_acima_do_limite")

    tipos = set(pedido.tipos)
    postos = {p.id: p.nome for p in db.scalars(select(PostoServico)).all()}
    from app.api.assinaturas import titulo_doc

    # 1) Resolve TODAS as entradas (caminho no ZIP + key no MinIO) já aqui.
    #    Pré-verifica existência (stat) para montar o relatório ANTES do stream.
    plano: list[tuple[str, str]] = []       # (caminho_zip, key)
    faltando: list[str] = []
    usados: set[str] = set()

    def _pasta(c: Candidato) -> str:
        posto = slug(postos.get(c.posto_servico_id) or "SEM-POSTO", "SEM-POSTO").upper()
        n = "".join(x for x in (c.cpf or "") if x.isdigit())[-4:]
        base = f"{posto}/{slug(c.nome_completo)}" + (f"-{n}" if n else "")
        cand, i = base, 2
        while cand in usados:
            cand, i = f"{base}-{i}", i + 1
        usados.add(cand)
        return cand

    def _add(caminho: str, key: str | None, rotulo: str) -> None:
        if not key:
            return
        if storage.stat(key) is None:
            faltando.append(rotulo)
            return
        plano.append((caminho, key))

    for c in pessoas:
        base = _pasta(c)
        if "dossie" in tipos and c.dossie_pdf_key:
            _add(f"{base}/dossie.pdf", c.dossie_pdf_key, f"{c.nome_completo}: dossiê")
        if "assinados" in tipos:
            for a in db.scalars(select(Assinatura).where(
                    Assinatura.candidato_id == c.id, Assinatura.assinado_em.isnot(None),
                    Assinatura.invalidada_em.is_(None))).all():
                _add(f"{base}/assinados/{slug(titulo_doc(a), f'doc-{a.id.hex[:8]}')}.pdf",
                     a.pdf_key, f"{c.nome_completo}: {titulo_doc(a)}")
        if "aprovados" in tipos:
            for s in db.scalars(select(SlotDocumento).where(
                    SlotDocumento.candidato_id == c.id,
                    SlotDocumento.status == StatusSlot.aprovado,
                    SlotDocumento.arquivo_pdf_key.isnot(None))).all():
                _add(f"{base}/documentos/{slug(s.tipo.value)}.pdf",
                     s.arquivo_pdf_key, f"{c.nome_completo}: {s.tipo.value}")

    # 2) Artefatos em memória: planilha (dados achatados + colunas de vínculo)
    #    e o relatório do que faltou — ambos resolvidos ANTES do stream.
    memoria: list[tuple[str, bytes]] = []
    if pedido.incluir_planilha and "ficha" in tipos:
        assin, slots, _ = _contagens(db, [c.id for c in pessoas])
        linhas = []
        for c in pessoas:
            linhas.append({
                "Posto": postos.get(c.posto_servico_id) or "",
                "Cargo/função": c.cargo_funcao or "",
                "Situação": c.situacao or "em admissão",
                "Matrícula": c.matricula or "",
                "Data admissão": c.data_admissao or "",
                "Data desligamento": c.data_desligamento or "",
                **linha_completa(db, c),
                "Vias assinadas (qtd)": assin.get(c.id, 0),
                "Documentos aprovados (qtd)": slots.get(c.id, 0),
            })
        memoria.append(("dados/colaboradores.xlsx", montar_workbook(linhas)))
    if faltando:
        txt = ("Arquivos esperados que não foram encontrados no armazenamento "
               "(a exportação seguiu sem eles):\n\n" + "\n".join(f"- {f}" for f in faltando))
        memoria.append(("_RELATORIO.txt", txt.encode("utf-8")))

    # 3) Auditoria ANTES do stream, com a lista de candidato_id (LGPD).
    registrar(db, "arquivo_exportado_lote", ator="rh", ator_detalhe=rh.email,
              detalhe={"pessoas": len(pessoas), "arquivos": len(plano),
                       "tipos": sorted(tipos), "faltando": len(faltando),
                       "candidato_ids": [str(c.id) for c in pessoas][:1000]})
    db.commit()

    # 4) Entradas de stream: só (caminho, provedor MinIO). O gerador NÃO usa db.
    stream = [(caminho, (lambda k=key: storage.abrir_em_blocos(k)))
              for caminho, key in plano]
    agora = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return StreamingResponse(
        gerar_zip(stream, memoria), media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="arquivo-greenhouse-{agora}.zip"',
                 # dispensa o buffering do proxy (evita timeout/estouro no nginx)
                 "X-Accel-Buffering": "no"})
