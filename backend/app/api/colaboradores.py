"""Dash de colaboradores do RH: visão com filtros e exportação Excel completa
(linha a linha, com todas as respostas do formulário), importação em massa da
base do Tirvu e controles de vínculo (efetivar, desligar, transferir posto)."""

import io
import re
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Response, UploadFile
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.auth_rh import requer_rh
from app.core.db import get_db
from app.models.candidato import Candidato, PostoServico, StatusCandidato
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
            "Filiação (mãe)": _fmt(p.nome_mae), "Filiação (pai)": _fmt(p.nome_pai),
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


def _filtrar(db: Session, status: str | None, busca: str | None,
             situacao: str | None = None, posto_id: uuid.UUID | None = None) -> list[Candidato]:
    q = select(Candidato).order_by(Candidato.criado_em.desc())
    if status:
        q = q.where(Candidato.status == StatusCandidato(status))
    if situacao:
        q = q.where(Candidato.situacao == situacao)
    if posto_id:
        q = q.where(Candidato.posto_servico_id == posto_id)
    candidatos = db.scalars(q).all()
    if busca:
        termo = busca.strip().lower()
        so_digitos = "".join(ch for ch in termo if ch.isdigit())
        # CPF agora é campo nativo do Candidato (importação); mas para quem veio
        # da admissão o CPF vive na ficha de documentos. Consulto ambos.
        cpfs = {}
        if so_digitos:
            for doc in db.scalars(select(DocumentosIdentificacao)).all():
                cpfs[doc.candidato_id] = doc.cpf or ""
        candidatos = [
            c for c in candidatos
            # e-mail e celular podem ser None (convite sem e-mail, v1.3) —
            # era isto que derrubava a busca com 500.
            if termo in (c.nome_completo or "").lower()
            or termo in (c.email or "").lower()
            or (so_digitos and (so_digitos in _so_digitos(c.cpf)
                                or so_digitos in cpfs.get(c.id, "")))
        ]
    return candidatos


@router.get("/rh/colaboradores")
def listar(status: str | None = None, busca: str | None = None,
           situacao: str | None = None, posto_id: uuid.UUID | None = None,
           db: Session = Depends(get_db)) -> list[dict]:
    candidatos = _filtrar(db, status, busca, situacao, posto_id)
    # nomes dos postos em um só lookup (evita N+1 na lista de 1.156)
    postos = {p.id: p.nome for p in db.scalars(select(PostoServico)).all()}
    saida = []
    for c in candidatos:
        # Para importados, CPF/nascimento já são nativos; para admissão, caem na
        # ficha. Só busco a ficha quando o campo nativo está vazio.
        cpf = c.cpf
        nasc = c.data_nascimento
        if not cpf:
            d = db.get(DocumentosIdentificacao, c.id)
            cpf = d.cpf if d else None
        if not nasc:
            p = db.get(DadosPessoais, c.id)
            nasc = p.data_nascimento if p else None
        saida.append({
            "id": c.id, "nome_completo": c.nome_completo, "email": c.email,
            "celular_whatsapp": c.celular_whatsapp, "status": c.status,
            "situacao": c.situacao, "origem": c.origem,
            "cpf": cpf, "nascimento": nasc, "matricula": c.matricula,
            "posto_id": c.posto_servico_id,
            "posto_nome": postos.get(c.posto_servico_id),
            "data_admissao": c.data_admissao,
            "data_desligamento": c.data_desligamento,
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


# ======================================================================
# Importação em massa da base do Tirvu
# ======================================================================
#
# Mapeia cabeçalhos da planilha do Tirvu -> campos fixos do Candidato. Tudo que
# NÃO estiver aqui entra em `dados_tirvu` (colunas dinâmicas). O casamento de
# cabeçalho é tolerante (sem acento, minúsculo, sem espaços duplos).

_MAPA_TIRVU = {
    "cpf": "cpf",
    "colaborador": "nome_completo",
    "nome": "nome_completo",
    "matricula": "matricula",
    "nascimento": "data_nascimento",
    "data de nascimento": "data_nascimento",
    "cargo": "cargo_funcao",
    "lotacao": "_lotacao",           # vira posto (casado/criado à parte)
    "admissao": "data_admissao",
    "demissao": "data_desligamento",
    "status": "_situacao",           # ATIVO/DEMITIDO -> situacao
    "e-mail": "email",
    "email": "email",
    "telefone": "celular_whatsapp",
    "salario": "salario_base",
}


def _norm(txt: str) -> str:
    import unicodedata
    txt = unicodedata.normalize("NFKD", str(txt or "")).encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", txt).strip().lower()


def _so_digitos(v) -> str:
    return "".join(ch for ch in str(v or "") if ch.isdigit())


def _cpf_fmt(v) -> str | None:
    d = _so_digitos(v)
    if len(d) != 11:
        return None
    return f"{d[:3]}.{d[3:6]}.{d[6:9]}-{d[9:]}"


def _casar_posto(db: Session, cache: dict, lotacao: str) -> uuid.UUID | None:
    """Casa a 'Lotação' do Tirvu com um posto existente (por nome, case-insens.);
    se não existir, cria um posto novo (nunca falha a linha por isto)."""
    nome = (lotacao or "").strip()
    if not nome:
        return None
    chave = nome.lower()
    if chave in cache:
        return cache[chave]
    posto = db.scalar(select(PostoServico).where(PostoServico.nome.ilike(nome)))
    if posto is None:
        posto = PostoServico(nome=nome)
        db.add(posto)
        db.flush()
    cache[chave] = posto.id
    return posto.id


@router.post("/rh/colaboradores/importar")
async def importar_colaboradores(arquivo: UploadFile,
                                 db: Session = Depends(get_db),
                                 rh: UsuarioRH = Depends(requer_rh)) -> dict:
    """Importa a base de colaboradores ativos a partir da planilha (.xlsx) do
    Tirvu. Idempotente por CPF: linha cujo CPF já existe é ATUALIZADA, não
    duplicada. Colunas conhecidas viram campos; as demais entram em dados_tirvu.
    A 'Lotação' é casada com um posto (criado se não existir)."""
    from openpyxl import load_workbook

    conteudo = await arquivo.read()
    try:
        wb = load_workbook(io.BytesIO(conteudo), read_only=True, data_only=True)
    except Exception:
        raise HTTPException(status_code=422, detail="arquivo_invalido")
    ws = wb.active
    linhas = ws.iter_rows(values_only=True)
    try:
        cabecalho = [str(c or "").strip() for c in next(linhas)]
    except StopIteration:
        raise HTTPException(status_code=422, detail="planilha_vazia")

    # posição da coluna de CPF (obrigatória para dedup)
    norm_cab = [_norm(c) for c in cabecalho]
    if "cpf" not in norm_cab:
        raise HTTPException(status_code=422, detail="sem_coluna_cpf")

    # índice de CPFs já cadastrados -> registro
    ja = {c.cpf: c for c in db.scalars(
        select(Candidato).where(Candidato.cpf.is_not(None))).all()}
    cache_postos: dict = {}
    criados = atualizados = ignorados = 0
    sem_cpf = 0

    for bruta in linhas:
        if bruta is None or all(v in (None, "") for v in bruta):
            continue
        valores = list(bruta) + [None] * (len(cabecalho) - len(bruta))
        cpf = _cpf_fmt(valores[norm_cab.index("cpf")])
        if not cpf:
            sem_cpf += 1
            continue

        campos: dict = {}
        lotacao = None
        situacao_bruta = None
        dinamicos: dict = {}
        for titulo, nrm, valor in zip(cabecalho, norm_cab, valores):
            destino = _MAPA_TIRVU.get(nrm)
            v = "" if valor is None else str(valor).strip()
            if destino == "_lotacao":
                lotacao = v
            elif destino == "_situacao":
                situacao_bruta = v
            elif destino == "cpf":
                pass  # já tratado
            elif destino:
                campos[destino] = v or None
            elif v:
                dinamicos[titulo] = v

        situacao = "desligado" if _norm(situacao_bruta).startswith(("demit", "inativ", "deslig")) \
            else "ativo"

        alvo = ja.get(cpf)
        if alvo is None:
            alvo = Candidato(cpf=cpf, nome_completo=campos.get("nome_completo") or "(sem nome)",
                             origem="importacao")
            db.add(alvo)
            ja[cpf] = alvo
            criados += 1
        else:
            atualizados += 1
        # aplica campos fixos (não sobrescreve nome vazio)
        for k, val in campos.items():
            if k == "nome_completo" and not val:
                continue
            setattr(alvo, k, val)
        alvo.situacao = situacao
        alvo.status = StatusCandidato.desligado if situacao == "desligado" else StatusCandidato.ativo
        if lotacao:
            alvo.posto_servico_id = _casar_posto(db, cache_postos, lotacao)
        # mescla dinâmicos preservando o que já houver
        base = dict(alvo.dados_tirvu or {})
        base.update(dinamicos)
        alvo.dados_tirvu = base

    registrar(db, "colaboradores_importados", ator="rh", ator_detalhe=rh.email,
              detalhe={"criados": criados, "atualizados": atualizados,
                       "sem_cpf": sem_cpf, "postos_novos": len(cache_postos)})
    db.commit()
    return {"criados": criados, "atualizados": atualizados,
            "sem_cpf": sem_cpf, "postos_tocados": len(cache_postos),
            "total_base": len(ja)}


# ======================================================================
# Controles de vínculo: efetivar candidato, desligar, transferir posto
# ======================================================================


class DesligamentoIn(BaseModel):
    data_desligamento: str  # dd/mm/aaaa


class TransferenciaIn(BaseModel):
    posto_id: uuid.UUID
    data_transferencia: str | None = None  # registrada em dados_tirvu (histórico)


def _get_colab(db: Session, cid: uuid.UUID) -> Candidato:
    c = db.get(Candidato, cid)
    if c is None:
        raise HTTPException(status_code=404, detail="colaborador_nao_encontrado")
    return c


@router.post("/rh/colaboradores/{cid}/efetivar")
def efetivar(cid: uuid.UUID, db: Session = Depends(get_db),
             rh: UsuarioRH = Depends(requer_rh)) -> dict:
    """Transforma um candidato aprovado em colaborador ativo (mesmo registro)."""
    c = _get_colab(db, cid)
    c.situacao = "ativo"
    c.status = StatusCandidato.ativo
    if not c.data_admissao:
        c.data_admissao = datetime.now(timezone.utc).strftime("%d/%m/%Y")
    registrar(db, "colaborador_efetivado", ator="rh", ator_detalhe=rh.email,
              candidato_id=c.id, detalhe={"nome": c.nome_completo})
    db.commit()
    return {"id": c.id, "situacao": c.situacao, "status": c.status,
            "data_admissao": c.data_admissao}


@router.post("/rh/colaboradores/{cid}/desligar")
def desligar(cid: uuid.UUID, payload: DesligamentoIn, db: Session = Depends(get_db),
             rh: UsuarioRH = Depends(requer_rh)) -> dict:
    c = _get_colab(db, cid)
    c.situacao = "desligado"
    c.status = StatusCandidato.desligado
    c.data_desligamento = payload.data_desligamento.strip() or None
    registrar(db, "colaborador_desligado", ator="rh", ator_detalhe=rh.email,
              candidato_id=c.id,
              detalhe={"nome": c.nome_completo, "data": c.data_desligamento})
    db.commit()
    return {"id": c.id, "situacao": c.situacao, "data_desligamento": c.data_desligamento}


@router.post("/rh/colaboradores/{cid}/transferir")
def transferir(cid: uuid.UUID, payload: TransferenciaIn, db: Session = Depends(get_db),
               rh: UsuarioRH = Depends(requer_rh)) -> dict:
    c = _get_colab(db, cid)
    posto = db.get(PostoServico, payload.posto_id)
    if posto is None:
        raise HTTPException(status_code=404, detail="posto_nao_encontrado")
    origem = str(c.posto_servico_id) if c.posto_servico_id else None
    c.posto_servico_id = posto.id
    # histórico de transferências guardado nos dados dinâmicos (sem nova tabela)
    hist = dict(c.dados_tirvu or {})
    linha = f"{payload.data_transferencia or datetime.now(timezone.utc).strftime('%d/%m/%Y')} -> {posto.nome}"
    hist["Transferências"] = (hist.get("Transferências", "") + "; " + linha).strip("; ")
    c.dados_tirvu = hist
    registrar(db, "colaborador_transferido", ator="rh", ator_detalhe=rh.email,
              candidato_id=c.id,
              detalhe={"nome": c.nome_completo, "de": origem, "para": str(posto.id)})
    db.commit()
    return {"id": c.id, "posto_servico_id": c.posto_servico_id, "posto_nome": posto.nome}
