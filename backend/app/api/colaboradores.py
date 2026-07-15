"""Dash de colaboradores do RH: visão com filtros e exportação Excel completa
(linha a linha, com todas as respostas do formulário)."""

import io
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.auth_rh import requer_rh
from app.core.db import get_db
from app.models.candidato import Candidato, StatusCandidato
from app.models.ficha import (ContatoEmergencia, DadosPessoais,
                              DadosProfissionaisBancarios, Dependente,
                              DocumentosIdentificacao, Endereco, FichaEmergencia,
                              ValeTransporte)
from app.services.auditoria import registrar
from app.models.usuario_rh import UsuarioRH

router = APIRouter(tags=["colaboradores-rh"], dependencies=[Depends(requer_rh)])


def _fmt(v) -> str:
    if v is None or v == "":
        return ""
    if isinstance(v, bool):
        return "Sim" if v else "Não"
    if hasattr(v, "strftime"):
        return v.strftime("%d/%m/%Y")
    if hasattr(v, "value"):
        return str(v.value).replace("_", " ")
    return str(v)


def _linha_completa(db: Session, c: Candidato) -> dict:
    """Todas as respostas do candidato, achatadas em um dicionário ordenado."""
    p = db.get(DadosPessoais, c.id)
    e = db.get(Endereco, c.id)
    d = db.get(DocumentosIdentificacao, c.id)
    b = db.get(DadosProfissionaisBancarios, c.id)
    vt = db.get(ValeTransporte, c.id)
    fe = db.get(FichaEmergencia, c.id)
    deps = db.scalars(select(Dependente).where(Dependente.candidato_id == c.id)).all()
    contatos = db.scalars(select(ContatoEmergencia)
                          .where(ContatoEmergencia.candidato_id == c.id)).all()

    linha = {
        "Nome completo": c.nome_completo, "E-mail": c.email,
        "Celular/WhatsApp": c.celular_whatsapp, "Status": _fmt(c.status),
        "Convidado em": _fmt(c.criado_em), "Dossiê gerado em": _fmt(c.dossie_gerado_em),
    }
    if p:
        linha.update({
            "Nome social": _fmt(p.nome_social),
            "Data de nascimento": _fmt(p.data_nascimento), "Sexo": _fmt(p.sexo),
            "Identidade de gênero": _fmt(p.identidade_genero), "Cor/raça": _fmt(p.cor_raca),
            "Nacionalidade": _fmt(p.nacionalidade),
            "Naturalidade (cidade)": _fmt(p.naturalidade_cidade),
            "Naturalidade (UF)": _fmt(p.naturalidade_uf),
            "Estado civil": _fmt(p.estado_civil), "Escolaridade": _fmt(p.escolaridade),
            "PCD": _fmt(p.pcd),
        })
    if e:
        linha.update({
            "CEP": _fmt(e.cep), "Endereço": _fmt(e.logradouro_numero_complemento),
            "Bairro": _fmt(e.bairro), "Cidade": _fmt(e.cidade), "UF": _fmt(e.uf),
        })
    if d:
        linha.update({
            "RG": _fmt(d.rg_numero), "RG órgão emissor": _fmt(d.rg_orgao_emissor),
            "RG expedição": _fmt(d.rg_data_expedicao), "CPF": _fmt(d.cpf),
            "PIS/NIS/PASEP": _fmt(d.pis_nis_pasep), "CNH": _fmt(d.cnh_numero),
            "CNH categoria": _fmt(d.cnh_categoria),
            "Título de eleitor": _fmt(d.titulo_eleitor_numero),
            "Título zona": _fmt(d.titulo_eleitor_zona),
            "Título seção": _fmt(d.titulo_eleitor_secao),
        })
    if b:
        linha.update({
            "Tam. calça": _fmt(b.tamanho_calca), "Tam. camisa": _fmt(b.tamanho_camisa),
            "Tam. calçado": _fmt(b.tamanho_calcado), "Banco": _fmt(b.banco),
            "PIX tipo": _fmt(b.pix_tipo), "PIX chave": _fmt(b.pix_chave),
        })
    if vt:
        linha.update({
            "VT optante": _fmt(vt.optante), "VT cartão": _fmt(vt.cartao_dftrans),
            "VT trajeto": _fmt(vt.trajeto_descricao),
        })
    if fe:
        linha.update({
            "Tipo sanguíneo": _fmt(fe.tipo_sanguineo),
            "Medicamento contínuo": _fmt(fe.usa_medicamento_continuo),
            "Medicamentos": _fmt(fe.medicamentos),
            "Condições médicas": _fmt(fe.condicoes_medicas),
            "Orientações de emergência": _fmt(fe.orientacao_emergencia),
        })
    linha["Dependentes"] = "; ".join(
        f"{dep.nome_completo} ({_fmt(dep.parentesco)}, nasc. {_fmt(dep.data_nascimento)}, "
        f"CPF {dep.cpf}{', deduz IRRF' if dep.deduz_irrf else ''})"
        for dep in deps
    )
    linha["Contatos de emergência"] = "; ".join(
        f"{ct.nome_completo} ({ct.parentesco}, {ct.telefone_celular})"
        for ct in contatos
    )
    return linha


def _filtrar(db: Session, status: str | None, busca: str | None) -> list[Candidato]:
    q = select(Candidato).order_by(Candidato.criado_em.desc())
    if status:
        q = q.where(Candidato.status == StatusCandidato(status))
    candidatos = db.scalars(q).all()
    if busca:
        termo = busca.strip().lower()
        so_digitos = "".join(ch for ch in termo if ch.isdigit())
        cpfs = {}
        if so_digitos:
            for doc in db.scalars(select(DocumentosIdentificacao)).all():
                cpfs[doc.candidato_id] = doc.cpf or ""
        candidatos = [
            c for c in candidatos
            if termo in c.nome_completo.lower() or termo in c.email.lower()
            or (so_digitos and so_digitos in cpfs.get(c.id, ""))
        ]
    return candidatos


@router.get("/rh/colaboradores")
def listar(status: str | None = None, busca: str | None = None,
           db: Session = Depends(get_db)) -> list[dict]:
    saida = []
    for c in _filtrar(db, status, busca):
        p = db.get(DadosPessoais, c.id)
        e = db.get(Endereco, c.id)
        d = db.get(DocumentosIdentificacao, c.id)
        saida.append({
            "id": c.id, "nome_completo": c.nome_completo, "email": c.email,
            "celular_whatsapp": c.celular_whatsapp, "status": c.status,
            "cpf": d.cpf if d else None,
            "nascimento": p.data_nascimento if p else None,
            "cidade": e.cidade if e else None,
            "criado_em": c.criado_em,
            "dossie_gerado_em": c.dossie_gerado_em,
        })
    return saida


@router.get("/rh/colaboradores/exportar")
def exportar(status: str | None = None, busca: str | None = None,
             db: Session = Depends(get_db),
             rh: UsuarioRH = Depends(requer_rh)) -> Response:
    """Excel com uma linha por colaborador e TODAS as respostas do formulário."""
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter

    candidatos = _filtrar(db, status, busca)
    linhas = [_linha_completa(db, c) for c in candidatos]

    # União de todas as colunas na ordem em que aparecem (fichas incompletas
    # não escondem colunas das completas).
    colunas: list[str] = []
    for linha in linhas:
        for chave in linha:
            if chave not in colunas:
                colunas.append(chave)

    wb = Workbook()
    ws = wb.active
    ws.title = "Colaboradores"
    verde = PatternFill("solid", fgColor="0FB257")
    for j, nome in enumerate(colunas, start=1):
        cel = ws.cell(row=1, column=j, value=nome)
        cel.font = Font(bold=True, color="FFFFFF")
        cel.fill = verde
        cel.alignment = Alignment(vertical="center")
        ws.column_dimensions[get_column_letter(j)].width = max(14, min(38, len(nome) + 6))
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = f"A1:{get_column_letter(max(len(colunas), 1))}1"
    for i, linha in enumerate(linhas, start=2):
        for j, nome in enumerate(colunas, start=1):
            ws.cell(row=i, column=j, value=linha.get(nome, ""))

    buf = io.BytesIO()
    wb.save(buf)
    registrar(db, "colaboradores_exportados", ator="rh", ator_detalhe=rh.email,
              detalhe={"linhas": len(linhas), "status": status or "todos"})
    db.commit()
    agora = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return Response(
        content=buf.getvalue(),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition":
                 f'attachment; filename="colaboradores-{agora}.xlsx"'},
    )
