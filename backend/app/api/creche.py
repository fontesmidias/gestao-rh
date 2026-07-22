"""Reembolso-Creche (IN SEGES/MGI 147/2026): página de acompanhamento do RH.

Nesta 1ª onda entrega o LEVANTAMENTO de elegibilidade por posto — a resposta
que os ofícios (CNMP nº 5/2026, ANATEL nº 45/2026) cobram em 5 dias úteis:
quantos colaboradores estão alocados em postos abrangidos pela IN. A camada de
dados das crianças (idade em anos/meses, documentos) entra na 2ª onda, quando o
autocadastro público estiver no ar; a estrutura já a comporta."""

import io
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.auth_rh import requer_rh
from app.core.db import get_db
from app.models.beneficio import BeneficioCreche, CriancaCreche, StatusBeneficio
from app.models.candidato import Candidato, PostoServico
from app.models.usuario_rh import UsuarioRH
from app.services import storage
from app.services.auditoria import registrar
from app.services.email import enviar_email, html_moderno

router = APIRouter(tags=["creche-rh"], dependencies=[Depends(requer_rh)])


def _gerar_e_guardar_dossie(db: Session, ben: BeneficioCreche) -> str:
    from app.services.creche_pdf import gerar_dossie_creche
    pdf = gerar_dossie_creche(db, ben)
    key = f"creche/{ben.id}/dossie-reembolso-creche.pdf"
    storage.salvar(key, pdf, "application/pdf")
    ben.dossie_pdf_key = key
    ben.dossie_gerado_em = datetime.now(timezone.utc)
    return key


def _idade_anos_meses(nasc: str, ref: datetime | None = None) -> tuple[int, int] | None:
    """Idade em (anos, meses) a partir de 'dd/mm/aaaa'. A IN 147 usa o limite de
    5 anos e 11 meses — por isso os meses importam."""
    ref = ref or datetime.now(timezone.utc)
    try:
        d, m, a = (int(x) for x in nasc.split("/"))
    except (ValueError, AttributeError):
        return None
    anos = ref.year - a
    meses = ref.month - m
    if ref.day < d:
        meses -= 1
    if meses < 0:
        anos -= 1
        meses += 12
    return (anos, meses) if anos >= 0 else None


def _elegivel_por_idade(nasc: str) -> bool:
    """<= 5 anos e 11 meses (art. 2º, §1º da IN 147/2026)."""
    am = _idade_anos_meses(nasc)
    if am is None:
        return False
    anos, meses = am
    return anos < 5 or (anos == 5 and meses <= 11)


def _postos_elegiveis(db: Session) -> list[PostoServico]:
    return db.scalars(
        select(PostoServico)
        .where(PostoServico.da_direito_creche == True)  # noqa: E712
        .order_by(PostoServico.nome)
    ).all()


@router.get("/rh/creche/resumo")
def resumo(db: Session = Depends(get_db)) -> dict:
    """Panorama do benefício: total de postos elegíveis e de colaboradores
    ativos alocados neles, quebrado por posto (com o valor de cada contrato)."""
    postos = _postos_elegiveis(db)
    ids = [p.id for p in postos]
    # contagem de colaboradores ATIVOS por posto elegível (uma consulta só)
    por_posto: dict = {pid: 0 for pid in ids}
    if ids:
        ativos = db.scalars(
            select(Candidato).where(
                Candidato.posto_servico_id.in_(ids),
                Candidato.situacao == "ativo",
            )
        ).all()
        for c in ativos:
            por_posto[c.posto_servico_id] = por_posto.get(c.posto_servico_id, 0) + 1

    linhas = [{
        "posto_id": p.id, "posto": p.nome, "sigla": p.sigla,
        "contrato_ref": p.contrato_ref,
        "valor_reembolso": p.valor_reembolso_creche,
        "colaboradores_ativos": por_posto.get(p.id, 0),
    } for p in postos]

    return {
        "postos_elegiveis": len(postos),
        "colaboradores_em_postos_elegiveis": sum(por_posto.values()),
        "por_posto": linhas,
    }


@router.get("/rh/creche/pendentes-resposta")
def pendentes_resposta(db: Session = Depends(get_db),
                       _rh: UsuarioRH = Depends(requer_rh)) -> list[dict]:
    """Colaboradores ATIVOS em postos elegíveis que ainda NÃO responderam ao
    levantamento (não têm benefício, ou têm um em `levantamento` que nunca foi
    enviado). É a prova, para os órgãos (CNMP/ANATEL, prazo de 5 dias), de que
    todos os elegíveis foram consultados — e a lista de quem o RH precisa cobrar
    (auditoria 2026-07-22)."""
    postos = _postos_elegiveis(db)
    ids = [p.id for p in postos]
    if not ids:
        return []
    nomes_posto = {p.id: p.nome for p in postos}
    ativos = db.scalars(select(Candidato).where(
        Candidato.posto_servico_id.in_(ids),
        Candidato.situacao == "ativo")).all()
    # benefícios existentes por colaborador (o último estado conta como resposta,
    # exceto um levantamento que nunca foi enviado = não respondeu)
    bens = {b.candidato_id: b for b in db.scalars(select(BeneficioCreche)).all()}
    pendentes = []
    for c in ativos:
        b = bens.get(c.id)
        respondeu = b is not None and (
            b.status != StatusBeneficio.levantamento or b.enviado_em is not None)
        if not respondeu:
            pendentes.append({
                "candidato_id": c.id, "nome": c.nome_completo, "cpf": c.cpf,
                "matricula": c.matricula, "email": c.email,
                "posto": nomes_posto.get(c.posto_servico_id),
                "iniciou": b is not None,  # abriu o link mas não terminou
            })
    pendentes.sort(key=lambda x: (x["posto"] or "", x["nome"]))
    return pendentes


@router.get("/rh/creche/exportar")
def exportar(db: Session = Depends(get_db),
             rh: UsuarioRH = Depends(requer_rh)) -> Response:
    """Excel do levantamento: um colaborador ativo por linha, em postos que dão
    direito ao benefício, com o valor do reembolso do contrato. É a relação
    nominal que os órgãos pedem para instruir a repactuação."""
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter

    postos = {p.id: p for p in _postos_elegiveis(db)}
    colaboradores = []
    if postos:
        colaboradores = db.scalars(
            select(Candidato).where(
                Candidato.posto_servico_id.in_(list(postos.keys())),
                Candidato.situacao == "ativo",
            ).order_by(Candidato.nome_completo)
        ).all()

    cols = ["Nome completo", "CPF", "Matrícula", "Posto (contrato)", "Sigla",
            "Nº do contrato", "Valor do reembolso", "Data de admissão"]
    wb = Workbook()
    ws = wb.active
    ws.title = "Elegiveis Reembolso-Creche"
    verde = PatternFill("solid", fgColor="0FB257")
    for j, nome in enumerate(cols, start=1):
        cel = ws.cell(row=1, column=j, value=nome)
        cel.font = Font(bold=True, color="FFFFFF")
        cel.fill = verde
        cel.alignment = Alignment(vertical="center")
        ws.column_dimensions[get_column_letter(j)].width = max(14, min(40, len(nome) + 8))
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = f"A1:{get_column_letter(len(cols))}1"

    for i, c in enumerate(colaboradores, start=2):
        p = postos.get(c.posto_servico_id)
        valores = [c.nome_completo, c.cpf, c.matricula,
                   p.nome if p else "", p.sigla if p else "",
                   p.contrato_ref if p else "",
                   p.valor_reembolso_creche if p else "", c.data_admissao]
        for j, v in enumerate(valores, start=1):
            ws.cell(row=i, column=j, value=v or "")

    buf = io.BytesIO()
    wb.save(buf)
    registrar(db, "creche_levantamento_exportado", ator="rh", ator_detalhe=rh.email,
              detalhe={"colaboradores": len(colaboradores), "postos": len(postos)})
    db.commit()
    agora = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return Response(
        content=buf.getvalue(),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition":
                 f'attachment; filename="reembolso-creche-elegiveis-{agora}.xlsx"'},
    )


# ======================================================================
# Levantamentos: o RH revisa as adesões, aprova/ativa (com prazo mensal) ou
# indefere. Ao ativar, o colaborador recebe as orientações da entrega mensal.
# ======================================================================


def _dump_crianca_rh(c: CriancaCreche) -> dict:
    am = _idade_anos_meses(c.data_nascimento)
    return {
        "id": c.id, "nome": c.nome, "data_nascimento": c.data_nascimento,
        "parentesco": c.parentesco, "tipo_comprovante": c.tipo_comprovante,
        "idade_anos": am[0] if am else None, "idade_meses": am[1] if am else None,
        "elegivel_idade": _elegivel_por_idade(c.data_nascimento),
        "tem_certidao": bool(c.certidao_key), "tem_guarda": bool(c.guarda_key),
    }


def _dump_beneficio(db: Session, ben: BeneficioCreche) -> dict:
    col = db.get(Candidato, ben.candidato_id)
    posto = db.get(PostoServico, col.posto_servico_id) if col.posto_servico_id else None
    criancas = [_dump_crianca_rh(c) for c in ben.criancas]
    return {
        "id": ben.id, "candidato_id": col.id,
        "nome": col.nome_completo, "cpf": col.cpf, "matricula": col.matricula,
        "email": ben.email_confirmado or col.email, "telefone": ben.telefone,
        "posto": posto.nome if posto else None,
        "posto_da_direito": bool(posto and posto.da_direito_creche),
        "valor_posto": posto.valor_reembolso_creche if posto else None,
        "status": ben.status, "enviado_em": ben.enviado_em,
        "dia_entrega_mensal": ben.dia_entrega_mensal,
        "valor_reembolso": ben.valor_reembolso,
        "motivo_indeferimento": ben.motivo_indeferimento,
        "motivo_devolucao": ben.motivo_devolucao,
        "devolvido_em": ben.devolvido_em,
        # fila de acompanhamento (auditoria 2026-07-22): distingue "devolvi e
        # espero correção" de "colaborador só começou". aguardando_correcao =
        # voltou a levantamento por devolução e ainda não reenviou.
        "aguardando_correcao": (ben.status == StatusBeneficio.levantamento
                                and ben.devolvido_em is not None),
        "reenviado_apos_correcao": bool(ben.devolvido_em and ben.enviado_em
                                        and ben.enviado_em > ben.devolvido_em),
        "sem_direito_em": ben.sem_direito_em,
        "sem_direito_por": ben.sem_direito_por,
        "criancas": criancas,
        "algum_elegivel": any(c["elegivel_idade"] for c in criancas),
        # alerta de idade (auditoria 2026-07-22): benefício ATIVO em que NENHUMA
        # criança ainda está na idade → o RH deve suspender (risco de glosa).
        "revisar_idade": (ben.status == StatusBeneficio.ativo and bool(criancas)
                          and not any(c["elegivel_idade"] for c in criancas)),
    }


@router.get("/rh/creche/levantamentos")
def listar_levantamentos(status: str | None = None,
                         db: Session = Depends(get_db)) -> list[dict]:
    """Adesões ao benefício. Por padrão as que precisam de ação (em análise);
    aceita filtro por status."""
    q = select(BeneficioCreche).order_by(BeneficioCreche.enviado_em.desc().nullslast())
    if status:
        q = q.where(BeneficioCreche.status == StatusBeneficio(status))
    return [_dump_beneficio(db, b) for b in db.scalars(q).all()]


@router.get("/rh/creche/levantamentos/{beneficio_id}")
def detalhe_levantamento(beneficio_id: uuid.UUID, db: Session = Depends(get_db)) -> dict:
    ben = db.get(BeneficioCreche, beneficio_id)
    if ben is None:
        raise HTTPException(status_code=404, detail="beneficio_nao_encontrado")
    return _dump_beneficio(db, ben)


# rótulos amigáveis para o histórico (as ações de auditoria com prefixo creche_)
_HIST_ROTULO = {
    "creche_levantamento_enviado": "Colaborador enviou o levantamento",
    "creche_beneficio_devolvido": "RH devolveu para correção",
    "creche_beneficio_indeferido": "RH indeferiu",
    "creche_beneficio_ativado": "RH aprovou/ativou",
    "creche_beneficio_reaberto": "RH reabriu o levantamento",
    "creche_beneficio_suspenso": "RH suspendeu",
    "creche_beneficio_encerrado": "Benefício encerrado",
    "creche_sem_direito": "Registrado sem direito (não faz jus)",
    "creche_link_reenviado": "RH reenviou o link/código",
    "creche_codigo_enviado": "Código de acesso enviado",
    "creche_roteiro_falhou": "⚠️ Falha ao gerar o requerimento (reprocessar)",
}


@router.get("/rh/creche/levantamentos/{beneficio_id}/historico")
def historico_levantamento(beneficio_id: uuid.UUID, db: Session = Depends(get_db),
                           _rh: UsuarioRH = Depends(requer_rh)) -> list[dict]:
    """Linha do tempo das decisões do benefício (auditoria 2026-07-22): antes o
    RH só via o estado atual e o último revisor. Lê os eventos `creche_*` do
    colaborador, mais recente primeiro, com data/ator/motivo."""
    from app.models.evento import EventoAuditoria
    ben = db.get(BeneficioCreche, beneficio_id)
    if ben is None:
        raise HTTPException(status_code=404, detail="beneficio_nao_encontrado")
    eventos = db.scalars(
        select(EventoAuditoria)
        .where(EventoAuditoria.candidato_id == ben.candidato_id,
               EventoAuditoria.acao.like("creche\\_%", escape="\\"))
        .order_by(EventoAuditoria.criado_em.desc())).all()
    return [{
        "quando": e.criado_em, "ator": e.ator, "ator_detalhe": e.ator_detalhe,
        "acao": e.acao, "rotulo": _HIST_ROTULO.get(e.acao, e.acao),
        "motivo": (e.detalhe or {}).get("motivo") if e.detalhe else None,
    } for e in eventos]


class AtivarIn(BaseModel):
    dia_entrega_mensal: int | None = None
    valor_reembolso: str | None = None
    # se True, só aprova (aguardando_repactuacao); se False, ativa de fato
    aguardar_repactuacao: bool = False


@router.post("/rh/creche/levantamentos/{beneficio_id}/ativar")
def ativar_beneficio(beneficio_id: uuid.UUID, payload: AtivarIn, db: Session = Depends(get_db),
                     rh: UsuarioRH = Depends(requer_rh)) -> dict:
    """Aprova o benefício. Se aguardar_repactuacao=True, fica em
    'aguardando_repactuacao'; senão vai a 'ativo' e o colaborador recebe as
    orientações da entrega mensal (com o prazo)."""
    ben = db.get(BeneficioCreche, beneficio_id)
    if ben is None:
        raise HTTPException(status_code=404, detail="beneficio_nao_encontrado")
    col = db.get(Candidato, ben.candidato_id)
    posto = db.get(PostoServico, col.posto_servico_id) if col.posto_servico_id else None
    if payload.dia_entrega_mensal is not None:
        ben.dia_entrega_mensal = max(1, min(28, payload.dia_entrega_mensal))
    ben.valor_reembolso = (payload.valor_reembolso
                           or (posto.valor_reembolso_creche if posto else None))
    ben.revisado_por = rh.email
    ben.revisado_em = datetime.now(timezone.utc)
    # gera o dossiê do benefício (requerimento + anexos + declaração-modelo)
    try:
        _gerar_e_guardar_dossie(db, ben)
    except Exception:
        pass  # o dossiê é reproduzível pelo botão; não trava a ativação
    if payload.aguardar_repactuacao:
        ben.status = StatusBeneficio.aguardando_repactuacao
    else:
        ben.status = StatusBeneficio.ativo
        ben.ativado_em = datetime.now(timezone.utc)
        # roteiro de assinatura do requerimento: colaborador (na sessão de creche)
        # → RH que aprovou. Só após a aprovação é que o colaborador pode assinar.
        from app.services.roteiro_assinatura import criar_roteiro_creche
        try:
            criar_roteiro_creche(db, ben, rh)
        except Exception:
            # NÃO engolir sem rastro: sem o roteiro o colaborador nunca vê o botão
            # de assinar. Registra para o RH reprocessar (auditoria 2026-07-22).
            registrar(db, "creche_roteiro_falhou", ator="sistema",
                      candidato_id=col.id, detalhe={"beneficio": str(ben.id)})
    registrar(db, "creche_beneficio_ativado", ator="rh", ator_detalhe=rh.email,
              candidato_id=col.id,
              detalhe={"status": ben.status.value, "dia": ben.dia_entrega_mensal})
    db.commit()
    # e-mails após o commit (SMTP fora não desfaz a decisão)
    try:
        if ben.status == StatusBeneficio.ativo:
            _email_orientacoes_mensais(ben, col)
        else:
            _email_aguardando_repactuacao(ben, col)
    except Exception:
        pass
    return _dump_beneficio(db, ben)


class IndeferirIn(BaseModel):
    motivo: str


@router.post("/rh/creche/levantamentos/{beneficio_id}/indeferir")
def indeferir_beneficio(beneficio_id: uuid.UUID, payload: IndeferirIn,
                        db: Session = Depends(get_db),
                        rh: UsuarioRH = Depends(requer_rh)) -> dict:
    ben = db.get(BeneficioCreche, beneficio_id)
    if ben is None:
        raise HTTPException(status_code=404, detail="beneficio_nao_encontrado")
    ben.status = StatusBeneficio.indeferido
    ben.motivo_indeferimento = payload.motivo.strip() or None
    ben.revisado_por = rh.email
    ben.revisado_em = datetime.now(timezone.utc)
    col = db.get(Candidato, ben.candidato_id)
    registrar(db, "creche_beneficio_indeferido", ator="rh", ator_detalhe=rh.email,
              candidato_id=ben.candidato_id, detalhe={"motivo": ben.motivo_indeferimento})
    db.commit()
    try:
        _email_indeferimento(ben, col)  # avisa o colaborador (não trava)
    except Exception:
        pass
    return _dump_beneficio(db, ben)


class DevolverIn(BaseModel):
    motivo: str


@router.post("/rh/creche/levantamentos/{beneficio_id}/devolver")
def devolver_beneficio(beneficio_id: uuid.UUID, payload: DevolverIn,
                       db: Session = Depends(get_db),
                       rh: UsuarioRH = Depends(requer_rh)) -> dict:
    """Devolve o levantamento ao colaborador para correção (feedback
    2026-07-21). O status volta a `levantamento` — o que reabre a edição no link
    público e permite reenviar — com um motivo VISÍVEL ao colaborador. Limpa o
    envio anterior e um eventual indeferimento (a devolução é uma segunda
    chance, não um veredito)."""
    if not (payload.motivo or "").strip():
        raise HTTPException(status_code=422, detail="motivo_obrigatorio")
    ben = db.get(BeneficioCreche, beneficio_id)
    if ben is None:
        raise HTTPException(status_code=404, detail="beneficio_nao_encontrado")
    # guard: devolver só faz sentido para pedido em análise/aguardando. Sem isso
    # um clique fora de ordem devolveria um ATIVO, reabrindo edição de benefício
    # que já tem dossiê/assinatura (deixaria artefatos órfãos). Reabrir um
    # terminal (indeferido/sem-direito) é a rota /reabrir, não esta.
    if ben.status not in (StatusBeneficio.em_analise, StatusBeneficio.aguardando_repactuacao):
        raise HTTPException(status_code=409, detail="nao_devolvivel")
    ben.status = StatusBeneficio.levantamento
    ben.motivo_devolucao = payload.motivo.strip()
    ben.devolvido_em = datetime.now(timezone.utc)
    ben.motivo_indeferimento = None  # devolver anula um indeferimento anterior
    ben.enviado_em = None            # o colaborador vai reenviar
    ben.dados_conferidos_em = None   # e reconferir os dados
    ben.revisado_por = rh.email
    ben.revisado_em = datetime.now(timezone.utc)
    col = db.get(Candidato, ben.candidato_id)
    registrar(db, "creche_beneficio_devolvido", ator="rh", ator_detalhe=rh.email,
              candidato_id=ben.candidato_id, detalhe={"motivo": ben.motivo_devolucao})
    db.commit()
    try:
        _email_devolucao(ben, col)  # avisa o colaborador que precisa corrigir
    except Exception:
        pass
    return _dump_beneficio(db, ben)


class ReenviarLinkIn(BaseModel):
    email: str | None = None  # se vier, corrige o e-mail do colaborador antes


@router.post("/rh/creche/levantamentos/{beneficio_id}/reenviar-link")
def reenviar_link_creche(beneficio_id: uuid.UUID, payload: ReenviarLinkIn,
                         db: Session = Depends(get_db),
                         rh: UsuarioRH = Depends(requer_rh)) -> dict:
    """Destrava o colaborador que não consegue entrar (feedback 2026-07-22): e-mail
    não chegou, código expirou, ou o e-mail na base está errado. O RH pode
    corrigir o e-mail (com auditoria) e reenvia o código 2FA. Sem e-mail, não há
    como enviar — devolve 422 para o RH resolver o contato antes."""
    from app.api.creche_publico import _gerar_e_enviar_codigo
    ben = db.get(BeneficioCreche, beneficio_id)
    if ben is None:
        raise HTTPException(status_code=404, detail="beneficio_nao_encontrado")
    col = db.get(Candidato, ben.candidato_id)
    novo_email = (payload.email or "").strip()
    if novo_email:
        antes = col.email
        col.email = novo_email
        ben.email_confirmado = None  # o novo e-mail passará pelo 2FA de novo
        registrar(db, "creche_email_corrigido", ator="rh", ator_detalhe=rh.email,
                  candidato_id=col.id, detalhe={"antes": antes, "depois": novo_email})
        db.commit()
    destino = ben.email_confirmado or col.email
    if not destino:
        raise HTTPException(status_code=422, detail="sem_email")
    _gerar_e_enviar_codigo(db, col, ben, destino)
    registrar(db, "creche_link_reenviado", ator="rh", ator_detalhe=rh.email,
              candidato_id=col.id)
    db.commit()
    return {"enviado_para": destino}


def _marcar_sem_direito(db: Session, ben: BeneficioCreche, por: str) -> None:
    """Marca a declaração de que o colaborador não tem dependentes que dão
    direito. `por` = 'colaborador' (declarou no link) ou o e-mail do RH."""
    ben.status = StatusBeneficio.sem_direito_declarado
    ben.sem_direito_em = datetime.now(timezone.utc)
    ben.sem_direito_por = por


@router.post("/rh/creche/colaboradores/{colaborador_id}/sem-direito")
def rh_marcar_sem_direito(colaborador_id: uuid.UUID, db: Session = Depends(get_db),
                          rh: UsuarioRH = Depends(requer_rh)) -> dict:
    """O RH registra que o colaborador (elegível por posto) declarou não ter
    dependentes que dão direito — para quem respondeu por fora (WhatsApp,
    pessoalmente). Cria o benefício se ainda não existir. Fica no relatório
    como 'consultado e não pediu' (feedback 2026-07-21)."""
    col = db.get(Candidato, colaborador_id)
    if col is None:
        raise HTTPException(status_code=404, detail="colaborador_nao_encontrado")
    ben = db.scalar(select(BeneficioCreche)
                    .where(BeneficioCreche.candidato_id == colaborador_id))
    if ben is None:
        ben = BeneficioCreche(candidato_id=colaborador_id)
        db.add(ben)
    elif ben.status == StatusBeneficio.ativo:
        # não apaga um benefício em pagamento por engano de clique
        raise HTTPException(status_code=409, detail="beneficio_ativo")
    _marcar_sem_direito(db, ben, rh.email)
    registrar(db, "creche_sem_direito", ator="rh", ator_detalhe=rh.email,
              candidato_id=colaborador_id, detalhe={"por": "rh"})
    db.commit()
    try:
        _email_sem_direito(ben, col)  # confirmação escrita ao colaborador
    except Exception:
        pass
    return _dump_beneficio(db, ben)


@router.post("/rh/creche/levantamentos/{beneficio_id}/reabrir")
def reabrir_beneficio(beneficio_id: uuid.UUID, db: Session = Depends(get_db),
                      rh: UsuarioRH = Depends(requer_rh)) -> dict:
    """Tira o benefício de um estado TERMINAL (indeferido / sem_direito_declarado)
    e o devolve a `levantamento` para o colaborador refazer — a situação mudou
    (indeferido por engano; ou quem declarou 'sem direito' passou a ter filho/
    guarda). Feedback 2026-07-22: antes esses estados eram becos sem saída dos
    dois lados. Só age sobre terminais reabríveis; um ativo não se 'reabre' assim."""
    ben = db.get(BeneficioCreche, beneficio_id)
    if ben is None:
        raise HTTPException(status_code=404, detail="beneficio_nao_encontrado")
    if ben.status not in (StatusBeneficio.indeferido, StatusBeneficio.sem_direito_declarado):
        raise HTTPException(status_code=409, detail="nao_reabrivel")
    ben.status = StatusBeneficio.levantamento
    ben.motivo_indeferimento = None
    ben.sem_direito_em = None
    ben.sem_direito_por = None
    ben.enviado_em = None
    ben.dados_conferidos_em = None
    ben.revisado_por = rh.email
    ben.revisado_em = datetime.now(timezone.utc)
    registrar(db, "creche_beneficio_reaberto", ator="rh", ator_detalhe=rh.email,
              candidato_id=ben.candidato_id)
    db.commit()
    return _dump_beneficio(db, ben)


class EncerrarIn(BaseModel):
    motivo: str
    encerrar: bool = False  # False = suspender (reversível), True = encerrar


@router.post("/rh/creche/levantamentos/{beneficio_id}/suspender")
def suspender_beneficio(beneficio_id: uuid.UUID, payload: EncerrarIn,
                        db: Session = Depends(get_db),
                        rh: UsuarioRH = Depends(requer_rh)) -> dict:
    """Tira um benefício ATIVO de circulação: suspende (criança passou de 5a11m,
    pendência) ou encerra (desligamento). Para o ciclo mensal e avisa o
    colaborador — sem isso o RH seguia orientado a reembolsar quem já não tem
    direito (risco de glosa na prestação de contas, auditoria 2026-07-22)."""
    if not (payload.motivo or "").strip():
        raise HTTPException(status_code=422, detail="motivo_obrigatorio")
    ben = db.get(BeneficioCreche, beneficio_id)
    if ben is None:
        raise HTTPException(status_code=404, detail="beneficio_nao_encontrado")
    if ben.status not in (StatusBeneficio.ativo, StatusBeneficio.aguardando_repactuacao):
        raise HTTPException(status_code=409, detail="nao_suspensivel")
    ben.status = StatusBeneficio.encerrado if payload.encerrar else StatusBeneficio.suspenso
    ben.motivo_indeferimento = payload.motivo.strip()  # reusa o campo de motivo
    ben.revisado_por = rh.email
    ben.revisado_em = datetime.now(timezone.utc)
    col = db.get(Candidato, ben.candidato_id)
    registrar(db, "creche_beneficio_encerrado" if payload.encerrar else "creche_beneficio_suspenso",
              ator="rh", ator_detalhe=rh.email, candidato_id=col.id,
              detalhe={"motivo": payload.motivo.strip()})
    db.commit()
    try:
        _email_suspensao(ben, col, payload.motivo.strip(), payload.encerrar)
    except Exception:
        pass
    return _dump_beneficio(db, ben)


class PrazoMassaIn(BaseModel):
    beneficio_ids: list[uuid.UUID]
    dia_entrega_mensal: int


@router.put("/rh/creche/prazos")
def editar_prazos(payload: PrazoMassaIn, db: Session = Depends(get_db),
                  rh: UsuarioRH = Depends(requer_rh)) -> dict:
    """Ajusta o dia de entrega mensal de vários benefícios de uma vez (ou de um,
    passando um id só)."""
    dia = max(1, min(28, payload.dia_entrega_mensal))
    bens = db.scalars(select(BeneficioCreche)
                      .where(BeneficioCreche.id.in_(payload.beneficio_ids))).all()
    for b in bens:
        b.dia_entrega_mensal = dia
    registrar(db, "creche_prazos_alterados", ator="rh", ator_detalhe=rh.email,
              detalhe={"qtd": len(bens), "dia": dia})
    db.commit()
    return {"atualizados": len(bens), "dia_entrega_mensal": dia}


def _email_orientacoes_mensais(ben: BeneficioCreche, col: Candidato) -> None:
    """Enviado ao ATIVAR: orienta a entrega mensal da documentação de despesa."""
    email = ben.email_confirmado or col.email
    if not email:
        return
    dia = ben.dia_entrega_mensal
    enviar_email(
        email,
        "Green House — Reembolso-Creche ativado: orientações da entrega mensal",
        f"Olá, {col.nome_completo.split()[0].title()}!\n\n"
        "Seu benefício de Reembolso-Creche foi ATIVADO.\n\n"
        f"Todo mês, até o dia {dia}, você deve nos enviar a comprovação da "
        "despesa do mês anterior, de UMA destas formas:\n"
        "  - DECLARAÇÃO assinada pela pessoa que cuida da criança (modelo que "
        "enviamos), quando for cuidador(a)/babá; ou\n"
        "  - NOTA FISCAL da creche/pré-escola, quando for estabelecimento.\n\n"
        "Sem a comprovação no prazo, o reembolso do mês pode não ser efetuado.\n\n"
        "Atenciosamente,\nRH — Green House\n",
        html_moderno(
            "Reembolso-Creche ativado",
            [
                f"Olá, <strong>{col.nome_completo.split()[0].title()}</strong>!",
                "Seu benefício de <strong>Reembolso-Creche</strong> foi ativado. 🎉",
                f"Todo mês, <strong>até o dia {dia}</strong>, envie a comprovação "
                "da despesa do mês anterior, de uma destas formas:",
                "<ul style='margin:8px 0 0 18px;color:#3a4152'>"
                "<li><strong>Declaração</strong> assinada por quem cuida da criança "
                "(cuidador(a)/babá) — use o modelo que enviamos; ou</li>"
                "<li><strong>Nota fiscal</strong> da creche/pré-escola, quando for "
                "um estabelecimento.</li></ul>",
                "Sem a comprovação no prazo, o reembolso do mês pode não ser efetuado.",
            ],
        ),
    )


def _url_creche() -> str:
    from app.core.config import get_settings
    return f"{get_settings().base_url.rstrip('/')}/creche"


def _email_devolucao(ben: BeneficioCreche, col: Candidato) -> None:
    """Avisa o colaborador que o RH devolveu o levantamento para correção — sem
    isso ele só descobriria se reabrisse o link por acaso (feedback 2026-07-22).
    Instrui a acessar /creche com o CPF (não expomos link com token por e-mail:
    o acesso passa pelo 2FA de sempre)."""
    email = ben.email_confirmado or col.email
    if not email:
        return
    nome = col.nome_completo.split()[0].title()
    motivo = ben.motivo_devolucao or "verifique os dados e reenvie."
    url = _url_creche()
    enviar_email(
        email,
        "Green House — Reembolso-Creche: seu pedido foi devolvido para correção",
        f"Olá, {nome}!\n\n"
        "Seu levantamento do Reembolso-Creche foi DEVOLVIDO para correção.\n\n"
        f"Motivo: {motivo}\n\n"
        f"Acesse {url}, entre com seu CPF, corrija o que for necessário e reenvie.\n\n"
        "Atenciosamente,\nRH — Green House\n",
        html_moderno(
            "Pedido devolvido para correção",
            [
                f"Olá, <strong>{nome}</strong>!",
                "Seu levantamento do <strong>Reembolso-Creche</strong> foi "
                "<strong>devolvido para correção</strong>.",
                f"<strong>Motivo do RH:</strong> {motivo}",
                f"Acesse <a href='{url}'>{url}</a>, entre com seu CPF, corrija e reenvie.",
            ],
        ),
    )


def _email_aguardando_repactuacao(ben: BeneficioCreche, col: Candidato) -> None:
    """Avisa o colaborador de que foi APROVADO, mas o pagamento depende do ajuste
    (repactuação) do contrato do posto — senão ele acha que ainda está 'em
    análise' e cobra o RH sem necessidade (auditoria 2026-07-22)."""
    email = ben.email_confirmado or col.email
    if not email:
        return
    nome = col.nome_completo.split()[0].title()
    enviar_email(
        email,
        "Green House — Reembolso-Creche: aprovado, aguardando o contrato",
        f"Olá, {nome}!\n\n"
        "Seu Reembolso-Creche foi APROVADO pelo RH. O pagamento começa após o "
        "ajuste (repactuação) do contrato do seu posto. Avisaremos quando estiver "
        "ativo — não é preciso fazer nada agora.\n\nAtenciosamente,\nRH — Green House\n",
        html_moderno(
            "Aprovado — aguardando o contrato",
            [
                f"Olá, <strong>{nome}</strong>!",
                "Seu <strong>Reembolso-Creche</strong> foi <strong>aprovado</strong> pelo RH. 🎉",
                "O pagamento começa após o ajuste (repactuação) do contrato do seu "
                "posto. <strong>Avisaremos quando estiver ativo</strong> — não é "
                "preciso fazer nada agora.",
            ],
        ),
    )


def encerrar_creche_no_desligamento(db: Session, candidato_id) -> None:
    """Gancho chamado quando o colaborador é desligado: encerra o benefício
    creche ativo/aguardando (não faz sentido reembolsar quem saiu). Idempotente
    e silencioso — não trava o desligamento. NÃO faz commit (o chamador commita).
    Avisa o colaborador por e-mail."""
    ben = db.scalar(select(BeneficioCreche).where(
        BeneficioCreche.candidato_id == candidato_id,
        BeneficioCreche.status.in_((StatusBeneficio.ativo,
                                    StatusBeneficio.aguardando_repactuacao))))
    if ben is None:
        return
    ben.status = StatusBeneficio.encerrado
    ben.motivo_indeferimento = "Colaborador desligado"
    col = db.get(Candidato, candidato_id)
    registrar(db, "creche_beneficio_encerrado", ator="sistema",
              candidato_id=candidato_id, detalhe={"motivo": "desligamento"})
    try:
        _email_suspensao(ben, col, "Colaborador desligado", encerrado=True)
    except Exception:
        pass


def _email_sem_direito(ben: BeneficioCreche, col: Candidato) -> None:
    """Quando o RH registra 'sem direito' por um colaborador (respondeu por fora),
    manda uma confirmação escrita — ele pode contestar antes de virar relatório
    oficial, e a trilha de auditoria fica mais forte (auditoria 2026-07-22)."""
    email = ben.email_confirmado or col.email
    if not email:
        return
    nome = col.nome_completo.split()[0].title()
    enviar_email(
        email,
        "Green House — Reembolso-Creche: registro de 'sem direito'",
        f"Olá, {nome}!\n\n"
        "Registramos que você informou NÃO ter dependentes que dão direito ao "
        "Reembolso-Creche.\n\nSe isso estiver incorreto ou mudar (novo filho, "
        "guarda, adoção), procure o RH.\n\nAtenciosamente,\nRH — Green House\n",
        html_moderno(
            "Registro de 'sem direito'",
            [
                f"Olá, <strong>{nome}</strong>!",
                "Registramos que você informou <strong>não ter dependentes</strong> "
                "que dão direito ao Reembolso-Creche.",
                "Se isso estiver <strong>incorreto ou mudar</strong> (novo filho, "
                "guarda, adoção), procure o RH.",
            ],
        ),
    )


def _email_suspensao(ben: BeneficioCreche, col: Candidato, motivo: str, encerrado: bool) -> None:
    """Avisa o colaborador de que o benefício foi suspenso/encerrado e que ele
    NÃO precisa mais enviar a comprovação mensal (auditoria 2026-07-22)."""
    email = ben.email_confirmado or col.email
    if not email:
        return
    nome = col.nome_completo.split()[0].title()
    verbo = "encerrado" if encerrado else "suspenso"
    enviar_email(
        email,
        f"Green House — Reembolso-Creche {verbo}",
        f"Olá, {nome}!\n\n"
        f"Seu Reembolso-Creche foi {verbo}.\n\nMotivo: {motivo}\n\n"
        "Você não precisa mais enviar a comprovação mensal. Em caso de dúvida, "
        "procure o RH.\n\nAtenciosamente,\nRH — Green House\n",
        html_moderno(
            f"Reembolso-Creche {verbo}",
            [
                f"Olá, <strong>{nome}</strong>!",
                f"Seu <strong>Reembolso-Creche</strong> foi <strong>{verbo}</strong>.",
                f"<strong>Motivo:</strong> {motivo}",
                "Você <strong>não precisa mais</strong> enviar a comprovação mensal.",
            ],
        ),
    )


def _email_indeferimento(ben: BeneficioCreche, col: Candidato) -> None:
    """Avisa o colaborador do indeferimento com o motivo (antes: silencioso)."""
    email = ben.email_confirmado or col.email
    if not email:
        return
    nome = col.nome_completo.split()[0].title()
    motivo = ben.motivo_indeferimento or "não atende aos requisitos do benefício."
    enviar_email(
        email,
        "Green House — Reembolso-Creche: resultado da análise",
        f"Olá, {nome}!\n\n"
        "Após a análise, seu pedido de Reembolso-Creche foi INDEFERIDO.\n\n"
        f"Motivo: {motivo}\n\n"
        "Em caso de dúvida, procure o RH.\n\nAtenciosamente,\nRH — Green House\n",
        html_moderno(
            "Resultado da análise — indeferido",
            [
                f"Olá, <strong>{nome}</strong>!",
                "Após a análise, seu pedido de <strong>Reembolso-Creche</strong> "
                "foi <strong>indeferido</strong>.",
                f"<strong>Motivo:</strong> {motivo}",
                "Em caso de dúvida, procure o RH.",
            ],
        ),
    )


@router.post("/rh/creche/levantamentos/{beneficio_id}/dossie")
def gerar_dossie_endpoint(beneficio_id: uuid.UUID, db: Session = Depends(get_db),
                          rh: UsuarioRH = Depends(requer_rh)) -> dict:
    """(Re)gera o dossiê do benefício sob demanda."""
    ben = db.get(BeneficioCreche, beneficio_id)
    if ben is None:
        raise HTTPException(status_code=404, detail="beneficio_nao_encontrado")
    _gerar_e_guardar_dossie(db, ben)
    registrar(db, "creche_dossie_gerado", ator="rh", ator_detalhe=rh.email,
              candidato_id=ben.candidato_id)
    db.commit()
    return {"gerado_em": ben.dossie_gerado_em}


@router.get("/rh/creche/levantamentos/{beneficio_id}/dossie")
def baixar_dossie(beneficio_id: uuid.UUID, db: Session = Depends(get_db)) -> Response:
    ben = db.get(BeneficioCreche, beneficio_id)
    if ben is None:
        raise HTTPException(status_code=404, detail="beneficio_nao_encontrado")
    if not ben.dossie_pdf_key:
        _gerar_e_guardar_dossie(db, ben)
        db.commit()
    dados = storage.ler(ben.dossie_pdf_key)
    col = db.get(Candidato, ben.candidato_id)
    nome = (col.nome_completo or "colaborador").replace(" ", "-").lower()
    return Response(content=dados, media_type="application/pdf",
                    headers={"Content-Disposition":
                             f'inline; filename="dossie-creche-{nome}.pdf"'})


_CT_POR_EXT = {
    "pdf": "application/pdf", "jpg": "image/jpeg", "jpeg": "image/jpeg",
    "png": "image/png", "gif": "image/gif", "webp": "image/webp", "heic": "image/heic",
}


@router.get("/rh/creche/levantamentos/{beneficio_id}/crianca/{crianca_id}/documento/{tipo}")
def baixar_doc_crianca(beneficio_id: uuid.UUID, crianca_id: uuid.UUID, tipo: str,
                       db: Session = Depends(get_db),
                       rh: UsuarioRH = Depends(requer_rh)) -> Response:
    """Serve o documento (certidão/guarda) enviado para uma criança, para o RH
    conferir individualmente — aos moldes dos documentos cadastrais."""
    if tipo not in ("certidao", "guarda"):
        raise HTTPException(status_code=422, detail="tipo_invalido")
    c = db.get(CriancaCreche, crianca_id)
    if c is None or c.beneficio_id != beneficio_id:
        raise HTTPException(status_code=404, detail="crianca_nao_encontrada")
    key = c.certidao_key if tipo == "certidao" else c.guarda_key
    if not key:
        raise HTTPException(status_code=404, detail="documento_nao_encontrado")
    # resolve TUDO do banco antes de tocar o storage (evita DetachedInstanceError)
    ext = key.rsplit(".", 1)[-1].lower()
    content_type = _CT_POR_EXT.get(ext, "application/octet-stream")
    nome = f"{tipo}-{c.nome.replace(' ', '-').lower()}.{ext}"
    registrar(db, "creche_doc_crianca_visto", ator="rh", ator_detalhe=rh.email,
              candidato_id=None, detalhe={"beneficio": str(beneficio_id), "tipo": tipo})
    db.commit()
    try:
        dados = storage.ler(key)
    except Exception:
        raise HTTPException(status_code=404, detail="arquivo_nao_encontrado")
    return Response(content=dados, media_type=content_type,
                    headers={"Content-Disposition": f'inline; filename="{nome}"'})


@router.get("/rh/creche/levantamentos/{beneficio_id}/documento/{tipo}")
def previa_documento(beneficio_id: uuid.UUID, tipo: str, db: Session = Depends(get_db)) -> Response:
    """Prévia do requerimento preenchido (tipo=requerimento) ou da declaração
    modelo (tipo=declaracao) no timbrado."""
    from app.services.creche_pdf import (gerar_declaracao_modelo,
                                        gerar_requerimento_creche)
    ben = db.get(BeneficioCreche, beneficio_id)
    if ben is None:
        raise HTTPException(status_code=404, detail="beneficio_nao_encontrado")
    if tipo == "requerimento":
        pdf = gerar_requerimento_creche(db, ben)
    elif tipo == "declaracao":
        pdf = gerar_declaracao_modelo(db, ben)
    else:
        raise HTTPException(status_code=422, detail="tipo_invalido")
    return Response(content=pdf, media_type="application/pdf",
                    headers={"Content-Disposition": f'inline; filename="{tipo}.pdf"'})
