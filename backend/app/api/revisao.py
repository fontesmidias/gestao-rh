"""Painel do RH: lista de candidatos, revisão de documentos e dossiê."""

import unicodedata
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.auth_rh import requer_rh
from app.core.config import base_url_publica, get_settings
from app.core.db import get_db
from app.models.candidato import Candidato, StatusCandidato
from app.models.documento import MotivoRejeicao, SlotDocumento, StatusSlot
from app.models.usuario_rh import UsuarioRH
from app.services import storage
from app.services import telemetria as telemetria_svc
from app.services.auditoria import registrar
from app.services.dossie import DossieIncompleto, gerar_dossie
from app.services.email import enviar_email
from app.services.email_templates import enviar_modelo
from app.services.magic_link import emitir_link

router = APIRouter(tags=["revisao-rh"], dependencies=[Depends(requer_rh)])


def _candidatos_admissao(db: Session, status: str | None, busca: str | None,
                         posto_id: uuid.UUID | None,
                         incluir_colaboradores: bool = False) -> list[Candidato]:
    """Filtra a lista de Admissões. Com o uso, serão muitos admitidos — daí os
    filtros (feedback 2026-07-19).

    Admissões mostra SÓ quem está em admissão (``situacao IS NULL``); quem já é
    colaborador (importado do Tirvu ou efetivado) tem ``situacao`` preenchida e
    vive na tela de Colaboradores — antes aparecia nas duas telas, misturando
    tudo (feedback 2026-07-21). ``incluir_colaboradores`` é o escape simétrico
    ao ``incluir_admissao`` de Colaboradores, para consultas que precisem de
    todos (ex.: envio pontual de modelo)."""
    q = select(Candidato).order_by(Candidato.criado_em.desc())
    if not incluir_colaboradores:
        q = q.where(Candidato.situacao.is_(None))
    if status:
        try:
            q = q.where(Candidato.status == StatusCandidato(status))
        except ValueError:
            pass
    if posto_id:
        q = q.where(Candidato.posto_servico_id == posto_id)
    candidatos = db.scalars(q).all()
    if busca:
        from app.models.ficha import DocumentosIdentificacao
        termo = busca.strip().lower()
        digitos = "".join(c for c in termo if c.isdigit())
        cpfs = {}
        if digitos:
            for d in db.scalars(select(DocumentosIdentificacao)).all():
                cpfs[d.candidato_id] = d.cpf or ""
        candidatos = [c for c in candidatos
                      if termo in (c.nome_completo or "").lower()
                      or termo in (c.email or "").lower()
                      or (digitos and (digitos in "".join(x for x in (c.cpf or "") if x.isdigit())
                                       or digitos in cpfs.get(c.id, "")))]
    return candidatos


@router.get("/rh/candidatos")
def listar_candidatos(status: str | None = None, busca: str | None = None,
                      posto_id: uuid.UUID | None = None,
                      incluir_colaboradores: bool = False,
                      db: Session = Depends(get_db)) -> list[dict]:
    candidatos = _candidatos_admissao(db, status, busca, posto_id,
                                      incluir_colaboradores=incluir_colaboradores)
    slots = db.scalars(select(SlotDocumento)).all()
    por_candidato: dict[uuid.UUID, list[SlotDocumento]] = {}
    for s in slots:
        por_candidato.setdefault(s.candidato_id, []).append(s)
    # Quantos testes já respondidos foram aproveitados por candidato (v2.21) —
    # EM LOTE, para a lista não virar N+1 quando a base crescer.
    from app.models.teste_vinculado import TesteVinculado
    vinculados: dict[uuid.UUID, int] = {}
    for (cid,) in db.execute(select(TesteVinculado.candidato_id)).all():
        vinculados[cid] = vinculados.get(cid, 0) + 1
    # Atendimento presencial EM CURSO (v2.58): quem está com sessão assistida
    # aberta agora. Sem isto, o RH clicava em "Atender presencial" e não tinha
    # como saber, olhando a lista, que aquela pessoa já estava em atendimento —
    # nem quem estava atendendo.
    #
    # Uma consulta só, como o resto da listagem: a mesma lição do N+1 achado no
    # dash de Talentos (v2.15).
    from app.models.candidato import AcessoMagico
    agora = datetime.now(timezone.utc)
    assistidos: dict[uuid.UUID, dict] = {}
    for acesso in db.scalars(
        select(AcessoMagico).where(
            AcessoMagico.assistido_por.is_not(None),
            AcessoMagico.revogado == False,          # noqa: E712
            AcessoMagico.expira_em > agora,
        ).order_by(AcessoMagico.criado_em.desc())
    ).all():
        # `setdefault`: com a ordem desc, fica o acesso MAIS RECENTE de cada
        # pessoa — que é o atendimento que está acontecendo agora.
        assistidos.setdefault(acesso.candidato_id,
                              {"por": acesso.assistido_por,
                               "desde": acesso.criado_em,
                               "ate": acesso.expira_em})
    saida = []
    for cand in candidatos:
        meus = [s for s in por_candidato.get(cand.id, []) if s.obrigatorio]
        ok = [s for s in meus if s.status in (StatusSlot.aprovado, StatusSlot.dispensado)]
        saida.append({
            "id": cand.id,
            "nome_completo": cand.nome_completo,
            "email": cand.email,
            "status": cand.status,
            "progresso_docs": {"ok": len(ok), "total": len(meus)},
            "criado_em": cand.criado_em,
            "dossie_gerado_em": cand.dossie_gerado_em,
            "testes_vinculados": vinculados.get(cand.id, 0),
            "atendimento_assistido": assistidos.get(cand.id),
        })
    return saida


@router.get("/rh/candidatos-exportar")
def exportar_admissoes(status: str | None = None, busca: str | None = None,
                       posto_id: uuid.UUID | None = None,
                       db: Session = Depends(get_db),
                       _rh: UsuarioRH = Depends(requer_rh)) -> Response:
    """Planilha das admissões (mesmos filtros da tela), reusando o service de
    export compartilhado."""
    from datetime import datetime, timezone

    from app.services.export_planilha import linha_completa, montar_workbook
    candidatos = _candidatos_admissao(db, status, busca, posto_id)
    conteudo = montar_workbook([linha_completa(db, c) for c in candidatos])
    registrar(db, "admissoes_exportadas", ator="rh", ator_detalhe=_rh.email,
              detalhe={"linhas": len(candidatos), "status": status or "todos"})
    db.commit()
    agora = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return Response(
        content=conteudo,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="admissoes-{agora}.xlsx"'})


# O export EM MASSA para o Tirvu vive em `colaboradores.py`: só se manda para
# lá quem já virou colaborador (efetivado) — quem ainda está em admissão não
# tem vínculo para criar no Tirvu. Aqui fica apenas o export individual, usado
# pelo botão na ficha da pessoa.


@router.get("/rh/candidatos/{candidato_id}/exportar-tirvu")
def exportar_tirvu_individual(candidato_id: uuid.UUID,
                              db: Session = Depends(get_db),
                              _rh: UsuarioRH = Depends(requer_rh)) -> Response:
    """Planilha do Tirvu com UMA admissão (botão na ficha do aprovado)."""
    from app.services.export_planilha import slug
    from app.services.export_tirvu import (linha_tirvu, montar_workbook_tirvu,
                                           pendencias_linha)

    cand = db.get(Candidato, candidato_id)
    if cand is None:
        raise HTTPException(404, "Candidato não encontrado")
    # planilha CRUA no formato exato do Tirvu (aba Plan1, sem filtro/cor/freeze);
    # gerar_matricula=True grava a matrícula automática se faltar (commit abaixo).
    linha = linha_tirvu(db, cand, gerar_matricula=True)
    conteudo = montar_workbook_tirvu([linha])
    # As MESMAS pendências que o export em massa acusa (feedback de campo
    # 2026-08-01: o Bruno exportou por AQUI e recebeu a planilha com posto,
    # cargo e jornada em branco, sem um aviso sequer — o Tirvu aceita a célula
    # vazia calado e o vínculo nasce torto lá). O download continua acontecendo
    # (às vezes se quer a planilha incompleta mesmo), mas nunca mais em
    # silêncio: vai no cabeçalho e na auditoria.
    faltas = pendencias_linha(linha)
    registrar(db, "tirvu_exportado", ator="rh", ator_detalhe=_rh.email,
              detalhe={"linhas": 1, "candidato": str(cand.id),
                       "pendencias": faltas or None})
    db.commit()
    nome = slug(cand.nome_completo, fallback="admissao")
    return Response(
        content=conteudo,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition":
                 f'attachment; filename="importacao-tirvu-{nome}.xlsx"',
                 # Latin-1: cabeçalho HTTP não aceita acento, e "Jornada de
                 # Trabalho" com acento derrubaria a resposta inteira.
                 "X-Tirvu-Pendencias": ", ".join(faltas).encode(
                     "ascii", "ignore").decode() or "nenhuma"})


@router.get("/rh/uniformes")
def uniformes(pendentes: bool = False, db: Session = Depends(get_db)) -> dict:
    """Tamanhos de uniforme de quem está em admissão — a lista que o operacional
    usa para comprar (feedback 2026-07-28).

    O Bruno pediu "um e-mail para o Gabriel, o Vitor e o operacional com todas
    as informações de uniforme" e, ao ser perguntado, preferiu TELA + e-mail só
    de aviso: nome, posto e tamanhos numa tabela por e-mail é ficha de pessoal
    circulando em caixa que ninguém controla, e a cada 20 admissões seriam 20
    e-mails que o time para de ler. O aviso vira empurrão ("há N pendentes"),
    o dado fica aqui.

    `pendentes=true` traz só quem ainda não informou algum tamanho — é a fila
    de cobrança do RH.
    """
    from app.models.candidato import PostoServico
    from app.models.ficha import DadosProfissionaisBancarios

    candidatos = db.scalars(
        select(Candidato).where(Candidato.situacao.is_(None))
        .order_by(Candidato.nome_completo)).all()
    dados = {d.candidato_id: d for d in db.scalars(
        select(DadosProfissionaisBancarios)).all()}
    postos = {p.id: p for p in db.scalars(select(PostoServico)).all()}

    linhas, faltando = [], 0
    for c in candidatos:
        d = dados.get(c.id)
        tam = {"calca": (d.tamanho_calca if d else None) or None,
               "camisa": (d.tamanho_camisa if d else None) or None,
               "calcado": (d.tamanho_calcado if d else None) or None}
        completo = all(tam.values())
        if not completo:
            faltando += 1
        if pendentes and completo:
            continue
        posto = postos.get(c.posto_servico_id)
        linhas.append({
            "candidato_id": c.id, "nome": c.nome_completo,
            "cargo": c.cargo_funcao, "posto": posto.nome if posto else None,
            "status": c.status.value, "data_admissao": c.data_admissao,
            **tam, "completo": completo,
        })
    return {"linhas": linhas, "total": len(candidatos), "faltando": faltando}


@router.get("/rh/metricas")
def metricas(db: Session = Depends(get_db)) -> dict:
    """Números do painel de ADMISSÕES: só quem está em admissão (`situacao IS
    NULL`) — coerente com a tela. Antes contava TODA a base (incl. os 1156
    colaboradores importados do Tirvu), o que inflava "Candidatos" e não batia
    com a lista (feedback 2026-07-22)."""
    candidatos = db.scalars(select(Candidato).where(Candidato.situacao.is_(None))).all()
    ids_admissao = {c.id for c in candidatos}
    # slots só dos candidatos em admissão (não dos colaboradores importados)
    slots = [s for s in db.scalars(select(SlotDocumento)).all()
             if s.candidato_id in ids_admissao]

    por_status: dict[str, int] = {}
    for c in candidatos:
        por_status[c.status.value] = por_status.get(c.status.value, 0) + 1

    aguardando_revisao = sum(1 for s in slots if s.status == StatusSlot.enviado)
    rejeitados_abertos = sum(1 for s in slots if s.status == StatusSlot.rejeitado)

    concluidos = [c for c in candidatos if c.dossie_gerado_em is not None]
    tempo_medio_min = None
    if concluidos:
        total = sum((c.dossie_gerado_em - c.criado_em).total_seconds() for c in concluidos)
        tempo_medio_min = round(total / len(concluidos) / 60)

    # Tempo LÍQUIDO de preenchimento (v2.51, pedido do Bruno): quanto a pessoa
    # de fato passou na tela, somando as sessões e descartando os intervalos em
    # que ela estava fora. O de cima (convite → dossiê) responde outra
    # pergunta — "quanto o processo demora" — e continua no retorno, mas saiu
    # do card: 2.590 min de calendário não dizem nada sobre o formulário.
    liquidos = telemetria_svc.tempo_liquido_por_candidato(
        db, [c.id for c in candidatos])
    tempo_liquido_s = (round(sum(liquidos.values()) / len(liquidos))
                       if liquidos else None)

    return {
        "total_candidatos": len(candidatos),
        "por_status": por_status,
        "documentos_aguardando_revisao": aguardando_revisao,
        "documentos_rejeitados_em_aberto": rejeitados_abertos,
        "dossies_gerados": len(concluidos),
        "tempo_medio_minutos_convite_ao_dossie": tempo_medio_min,
        # segundos; None = ainda não há telemetria suficiente
        "tempo_liquido_medio_s": tempo_liquido_s,
        "tempo_liquido_amostra": len(liquidos),
    }


def _atendimentos_assistidos(db: Session, candidato_id: uuid.UUID) -> list[dict]:
    """Atendimentos presenciais desta pessoa — os em curso e os encerrados.

    Lido dos próprios links (`acesso_magico.assistido_por`), que é onde a marca
    vive: nada de tabela paralela para manter em dia.

    `em_curso` distingue o atendimento que está acontecendo AGORA do que já
    passou — é o que a tela usa para mostrar "em atendimento" em vez de um
    histórico morto.
    """
    from app.models.candidato import AcessoMagico

    agora = datetime.now(timezone.utc)
    acessos = db.scalars(
        select(AcessoMagico)
        .where(AcessoMagico.candidato_id == candidato_id,
               AcessoMagico.assistido_por.is_not(None))
        .order_by(AcessoMagico.criado_em.desc())
    ).all()
    return [{
        "por": a.assistido_por,
        "quando": a.criado_em,
        "expira_em": a.expira_em,
        "em_curso": (not a.revogado) and a.expira_em > agora,
    } for a in acessos]


@router.get("/rh/candidatos/{candidato_id}")
def detalhe_candidato(candidato_id: uuid.UUID, db: Session = Depends(get_db)) -> dict:
    cand = db.get(Candidato, candidato_id)
    if cand is None:
        raise HTTPException(status_code=404, detail="candidato_nao_encontrado")
    slots = db.scalars(
        select(SlotDocumento)
        .where(SlotDocumento.candidato_id == cand.id)
        .order_by(SlotDocumento.criado_em)
    ).all()
    from app.api.assinaturas import NOMES_DOC, _docs_exigidos, chave_doc, titulo_doc
    from app.api.ficha import pendencias_da_ficha
    from app.models.assinatura import Assinatura
    assinaturas = db.scalars(
        select(Assinatura).where(Assinatura.candidato_id == cand.id,
                                 Assinatura.invalidada_em.is_(None))).all()
    por_doc = {a.documento: a for a in assinaturas if a.documento}
    fichas = [
        {"documento": doc, "titulo": NOMES_DOC[doc],
         "assinado": doc in por_doc and por_doc[doc].assinado_em is not None,
         "assinado_em": por_doc[doc].assinado_em if doc in por_doc else None}
        for doc in _docs_exigidos(db, cand)
    ] + [
        # documentos de modelo enviados para assinatura deste colaborador
        {"documento": chave_doc(a), "titulo": titulo_doc(a),
         "assinado": a.assinado_em is not None, "assinado_em": a.assinado_em}
        for a in assinaturas if a.modelo_id is not None
    ]
    return {
        "id": cand.id,
        "nome_completo": cand.nome_completo,
        "email": cand.email,
        "celular_whatsapp": cand.celular_whatsapp,
        "status": cand.status,
        "situacao": cand.situacao,  # None se ainda em admissão; ativo/desligado se colaborador
        "data_admissao": cand.data_admissao,
        "data_desligamento": cand.data_desligamento,
        "dossie_gerado_em": cand.dossie_gerado_em,
        "posto_servico_id": cand.posto_servico_id,
        "cargo_funcao": cand.cargo_funcao,
        "salario_base": cand.salario_base,
        "adicionais": cand.adicionais or [],
        "empresa_id": cand.empresa_id,
        "jornada_id": cand.jornada_id,
        "registra_ponto": cand.registra_ponto,
        "assinaturas": [
            {"documento": chave_doc(a), "titulo": titulo_doc(a),
             "assinado_em": a.assinado_em,
             # Quem operou o preenchimento, quando foi atendimento presencial.
             # Aparece na ficha porque a auditoria geral ninguém abre no dia a
             # dia — e é aqui que se responde "como este documento foi colhido?"
             "assistida_por": a.assistida_por}
            for a in assinaturas
        ],
        # Atendimentos presenciais desta pessoa (v2.58): os EM CURSO e os já
        # encerrados. Sem isto, saber que alguém foi atendido presencialmente
        # exigia abrir a auditoria geral e garimpar.
        "atendimentos_assistidos": _atendimentos_assistidos(db, cand.id),
        # Visão que faltava no incidente real: fichas sem dados/sem assinatura
        # eram invisíveis para o RH — agora cada documento exigido aparece com
        # o seu estado, e a ficha incompleta grita.
        "fichas": fichas,
        "pendencias_ficha": pendencias_da_ficha(db, cand),
        "slots": [
            {
                "id": s.id,
                "tipo": s.tipo,
                "dependente_id": s.dependente_id,
                "obrigatorio": s.obrigatorio,
                "status": s.status,
                "motivo_rejeicao": s.motivo_rejeicao,
                "paginas": s.paginas,
                "origem_envio": s.origem_envio,
                "origem_envio_obs": s.origem_envio_obs,
                "enviado_em": s.enviado_em,
                "revisado_em": s.revisado_em,
            }
            for s in slots
        ],
    }


@router.get("/rh/slots/{slot_id}/arquivo")
def ver_arquivo(slot_id: uuid.UUID, db: Session = Depends(get_db)) -> Response:
    slot = db.get(SlotDocumento, slot_id)
    if slot is None or slot.arquivo_pdf_key is None:
        raise HTTPException(status_code=404, detail="arquivo_nao_encontrado")
    return Response(content=storage.ler(slot.arquivo_pdf_key), media_type="application/pdf")


def _ascii(texto: str) -> str:
    """Nome de arquivo seguro para header HTTP (só ASCII)."""
    sem_acento = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    return sem_acento.replace(" ", "-")


# As rotas de lote precisam vir ANTES das rotas /rh/slots/{slot_id}/...:
# o FastAPI casa na ordem de declaração e "lote" seria capturado pelo
# path param {slot_id}, falhando a validação de UUID com 422.


class LoteAprovarIn(BaseModel):
    slot_ids: list[uuid.UUID]


@router.post("/rh/slots/lote/aprovar")
def aprovar_lote(payload: LoteAprovarIn, db: Session = Depends(get_db),
                 rh: UsuarioRH = Depends(requer_rh)) -> dict:
    aprovados = 0
    for slot_id in payload.slot_ids:
        slot = db.get(SlotDocumento, slot_id)
        if slot is None or slot.status != StatusSlot.enviado:
            continue
        slot.status = StatusSlot.aprovado
        slot.revisado_em = datetime.now(timezone.utc)
        slot.revisado_por = rh.id
        registrar(db, "documento_aprovado", ator="rh", ator_detalhe=rh.email,
                  candidato_id=slot.candidato_id, detalhe={"tipo": slot.tipo.value, "lote": True})
        aprovados += 1
    db.commit()
    return {"aprovados": aprovados}


class LoteRejeitarIn(BaseModel):
    slot_ids: list[uuid.UUID]
    motivo: MotivoRejeicao
    observacao: str | None = None


@router.post("/rh/slots/lote/rejeitar")
def rejeitar_lote(payload: LoteRejeitarIn, request: Request,
                  db: Session = Depends(get_db),
                  rh: UsuarioRH = Depends(requer_rh)) -> dict:
    """Rejeita vários documentos; o candidato recebe UM e-mail listando tudo."""
    rejeitados_por_candidato: dict[uuid.UUID, list[SlotDocumento]] = {}
    for slot_id in payload.slot_ids:
        slot = db.get(SlotDocumento, slot_id)
        if slot is None or slot.status != StatusSlot.enviado:
            continue
        slot.status = StatusSlot.rejeitado
        slot.motivo_rejeicao = payload.motivo
        slot.motivo_rejeicao_obs = payload.observacao
        slot.revisado_em = datetime.now(timezone.utc)
        slot.revisado_por = rh.id
        from app.api.documentos import expurgar_arquivos_do_slot
        expurgar_arquivos_do_slot(db, slot, evento="documento_rejeitado_expurgado",
                                  ator="rh", ator_detalhe=rh.email)
        registrar(db, "documento_rejeitado", ator="rh", ator_detalhe=rh.email,
                  candidato_id=slot.candidato_id,
                  detalhe={"tipo": slot.tipo.value, "motivo": payload.motivo.value, "lote": True})
        rejeitados_por_candidato.setdefault(slot.candidato_id, []).append(slot)

    total = 0
    for candidato_id, slots in rejeitados_por_candidato.items():
        candidato = db.get(Candidato, candidato_id)
        if candidato.status == StatusCandidato.envio_concluido:
            candidato.status = StatusCandidato.docs_pendentes
        total += len(slots)
        # A LISTA é montada aqui e chega pronta ao template: o RH edita o texto
        # ao redor, mas a regra de o que entra na lista é do código (v2.06).
        lista = "\n".join(f"- {s.tipo.value.replace('_', ' ')}" for s in slots)
        # Um link NOVO por candidato (ver comentário em ``rejeitar``): o e-mail
        # mandava acessar "o mesmo link da sua admissão" sem link nenhum.
        link = emitir_link(db, candidato, base_url_publica(request)) if candidato.email else None
        motivo = _MOTIVO_LEGIVEL[payload.motivo] + (
            f" — {payload.observacao}" if payload.observacao else "")
        enviar_modelo(db, "documentos_rejeitados_lote", candidato.email, {
            "nome": candidato.nome_completo, "motivo": motivo,
            "lista": lista, "link": link,
        })
    db.commit()
    return {"rejeitados": total}


def _slot_para_revisar(slot_id: uuid.UUID, db: Session) -> SlotDocumento:
    slot = db.get(SlotDocumento, slot_id)
    if slot is None:
        raise HTTPException(status_code=404, detail="slot_nao_encontrado")
    if slot.status != StatusSlot.enviado:
        raise HTTPException(status_code=409, detail="slot_nao_esta_em_analise")
    return slot


@router.post("/rh/slots/{slot_id}/aprovar")
def aprovar(slot_id: uuid.UUID, db: Session = Depends(get_db),
            rh: UsuarioRH = Depends(requer_rh)) -> dict:
    slot = _slot_para_revisar(slot_id, db)
    slot.status = StatusSlot.aprovado
    slot.revisado_em = datetime.now(timezone.utc)
    slot.revisado_por = rh.id
    registrar(db, "documento_aprovado", ator="rh", ator_detalhe=rh.email,
              candidato_id=slot.candidato_id, detalhe={"tipo": slot.tipo.value})
    db.commit()
    return {"status": slot.status}


class RejeicaoIn(BaseModel):
    motivo: MotivoRejeicao
    observacao: str | None = None


_MOTIVO_LEGIVEL = {
    MotivoRejeicao.ilegivel: "a imagem ficou ilegível",
    MotivoRejeicao.doc_errado: "o documento enviado não é o solicitado",
    MotivoRejeicao.vencido: "o documento está vencido",
    MotivoRejeicao.incompleto: "o documento está incompleto (falta frente ou verso)",
    MotivoRejeicao.outro: "houve um problema com o arquivo",
}


@router.post("/rh/slots/{slot_id}/rejeitar")
def rejeitar(slot_id: uuid.UUID, payload: RejeicaoIn, request: Request,
             db: Session = Depends(get_db),
             rh: UsuarioRH = Depends(requer_rh)) -> dict:
    slot = _slot_para_revisar(slot_id, db)
    slot.status = StatusSlot.rejeitado
    slot.motivo_rejeicao = payload.motivo
    slot.motivo_rejeicao_obs = payload.observacao
    slot.revisado_em = datetime.now(timezone.utc)
    slot.revisado_por = rh.id
    # Arquivo reprovado sai do storage na hora (minimização de dados) — o hash
    # fica na auditoria e o slot abre para o candidato reenviar.
    from app.api.documentos import expurgar_arquivos_do_slot
    expurgar_arquivos_do_slot(db, slot, evento="documento_rejeitado_expurgado",
                              ator="rh", ator_detalhe=rh.email)

    candidato = db.get(Candidato, slot.candidato_id)
    # Reabre o checklist para o candidato corrigir.
    if candidato.status == StatusCandidato.envio_concluido:
        candidato.status = StatusCandidato.docs_pendentes
    registrar(db, "documento_rejeitado", ator="rh", ator_detalhe=rh.email,
              candidato_id=slot.candidato_id,
              detalhe={"tipo": slot.tipo.value, "motivo": payload.motivo.value})
    # Link NOVO no próprio e-mail: mandar "acesse o mesmo link da sua admissão"
    # sem link obrigava a pessoa a garimpar um e-mail de até 72h atrás — e se
    # aquele já tinha expirado, ela ficava presa (feedback de campo 2026-07-28).
    link = emitir_link(db, candidato, base_url_publica(request)) if candidato.email else None
    db.commit()

    motivo = _MOTIVO_LEGIVEL[payload.motivo] + (
        f" ({payload.observacao})" if payload.observacao else "")
    enviar_modelo(db, "documento_rejeitado", candidato.email, {
        "nome": candidato.nome_completo,
        "primeiro_nome": (candidato.nome_completo or "").split()[0].title(),
        "motivo": motivo,
        "link": link,
    })
    return {"status": slot.status}


@router.post("/rh/slots/{slot_id}/dispensar")
def dispensar(slot_id: uuid.UUID, db: Session = Depends(get_db),
              rh: UsuarioRH = Depends(requer_rh)) -> dict:
    slot = db.get(SlotDocumento, slot_id)
    if slot is None:
        raise HTTPException(status_code=404, detail="slot_nao_encontrado")
    if slot.status == StatusSlot.aprovado:
        raise HTTPException(status_code=409, detail="slot_ja_aprovado")
    slot.status = StatusSlot.dispensado
    slot.revisado_em = datetime.now(timezone.utc)
    slot.revisado_por = rh.id
    db.commit()
    return {"status": slot.status}


@router.post("/rh/candidatos/{candidato_id}/dossie")
def gerar_dossie_endpoint(candidato_id: uuid.UUID, request: Request, forcar: bool = False,
                          db: Session = Depends(get_db)) -> dict:
    """forcar=true gera o dossiê parcial mesmo com pendências (decisão do RH,
    registrada em auditoria); o status só vira 'aprovado' quando completo."""
    from app.services.idempotencia import trava
    cand = db.get(Candidato, candidato_id)
    if cand is None:
        raise HTTPException(status_code=404, detail="candidato_nao_encontrado")
    # trava de idempotência: dois cliques em "Gerar dossiê" não geram dois PDFs
    # nem dois e-mails; a 2ª chamada concorrente recebe 409 ja_em_processamento.
    with trava(f"dossie:{cand.id}"):
        try:
            gerar_dossie(db, cand, ignorar_pendencias=forcar)
        except DossieIncompleto as exc:
            raise HTTPException(status_code=422, detail={"pendencias": exc.pendencias}) from exc
        except Exception as exc:
            # Erro REAL (arquivo faltando no storage, PDF corrompido…): registra com
            # detalhe e devolve mensagem legível. Antes virava um 500 genérico que o
            # painel exibia como "sem pendências" — o RH achava que estava tudo certo.
            import logging
            logging.getLogger(__name__).exception("Falha ao montar o dossiê de %s", cand.id)
            registrar(db, "dossie_falhou", ator="rh", candidato_id=cand.id,
                      detalhe={"erro": f"{type(exc).__name__}: {exc}"[:300]})
            db.commit()
            raise HTTPException(status_code=422,
                                detail=f"erro_ao_montar_dossie: {type(exc).__name__}") from exc
        if not forcar:
            cand.status = StatusCandidato.aprovado
        registrar(db, "dossie_gerado", ator="rh", candidato_id=cand.id,
                  detalhe={"parcial": forcar})
        db.commit()

        # Aviso interno pela MATRIZ (v2.20). Antes lia `email_avisos_internos`
        # direto: desligar o evento no painel não desligava este aviso, e
        # cadastrar destinatário específico não funcionava — o RH configurava a
        # matriz achando que ela governava todos os avisos, e este escapava.
        from app.services.notificacoes import avisar_modelo
        avisar_modelo(
            db, "dossie_pronto", "aviso_dossie_pronto",
            {"nome": cand.nome_completo,
             "link": f"{base_url_publica(request)}/rh"})
        return {"status": cand.status, "dossie_gerado_em": cand.dossie_gerado_em}


@router.get("/rh/candidatos/{candidato_id}/dossie")
def baixar_dossie(candidato_id: uuid.UUID, db: Session = Depends(get_db)) -> Response:
    cand = db.get(Candidato, candidato_id)
    if cand is None or cand.dossie_pdf_key is None:
        raise HTTPException(status_code=404, detail="dossie_nao_gerado")
    return Response(
        content=storage.ler(cand.dossie_pdf_key),
        media_type="application/pdf",
        headers={"Content-Disposition":
                 f'attachment; filename="dossie-{_ascii(cand.nome_completo)}.pdf"'},
    )


# ======================================================================
# Pedir um documento DEPOIS que a pessoa já concluiu (v2.43)
# ======================================================================


class PedirDocumentoIn(BaseModel):
    tipo: str                # valor de TipoDocumento (ex.: "laudo_pcd")
    motivo: str = ""


@router.post("/rh/candidatos/{candidato_id}/pedir-documento")
def pedir_documento(candidato_id: uuid.UUID, payload: PedirDocumentoIn,
                    db: Session = Depends(get_db),
                    rh: UsuarioRH = Depends(requer_rh)) -> dict:
    """Cria (ou libera) UM documento para a pessoa enviar, mesmo com o envio já
    concluído ou aprovado.

    Nasceu do caso do PCD (feedback 2026-08-01): a pessoa não declarou a
    deficiência no formulário — é dado de saúde, e muita gente evita declarar —
    e o RH soube por fora. Ao marcar `pcd` na ficha, o laudo passa a ser
    exigido; se ela já tinha concluído, o checklist estava congelado e a
    pendência não tinha como ser resolvida por ninguém.

    Libera **este** documento e mais nada: o status do candidato fica intacto,
    o dossiê não se desfaz e os demais slots continuam fechados. É a mesma
    ideia da reabertura cirúrgica de 2026-07-24, para um documento que passou a
    existir depois.
    """
    from app.models.documento import TipoDocumento

    cand = db.get(Candidato, candidato_id)
    if cand is None:
        raise HTTPException(status_code=404, detail="candidato_nao_encontrado")
    if cand.status == StatusCandidato.expurgado:
        raise HTTPException(status_code=409, detail="candidato_expurgado")
    try:
        tipo = TipoDocumento(payload.tipo)
    except ValueError:
        raise HTTPException(status_code=422, detail="tipo_desconhecido") from None

    slot = db.scalar(select(SlotDocumento).where(
        SlotDocumento.candidato_id == cand.id, SlotDocumento.tipo == tipo,
        SlotDocumento.dependente_id.is_(None)))
    if slot is None:
        slot = SlotDocumento(candidato_id=cand.id, tipo=tipo, obrigatorio=True)
        db.add(slot)
    elif slot.status in (StatusSlot.enviado, StatusSlot.aprovado):
        # Já tem arquivo: pedir de novo aqui apagaria o que o RH talvez ainda
        # não tenha olhado. Para trocar um documento já enviado existe o
        # caminho de rejeitar, que diz à pessoa o QUE estava errado.
        raise HTTPException(status_code=409, detail="documento_ja_enviado")

    slot.liberado_em = datetime.now(timezone.utc)
    slot.liberado_por = rh.email
    registrar(db, "documento_pedido_ao_candidato", ator="rh", ator_detalhe=rh.email,
              candidato_id=cand.id,
              detalhe={"tipo": tipo.value, "motivo": payload.motivo.strip() or None,
                       "status_candidato": cand.status.value})
    db.commit()
    return {"slot_id": slot.id, "tipo": tipo.value, "liberado_em": slot.liberado_em}


class DocumentoEspecificoIn(BaseModel):
    """Documento ESPECÍFICO acrescentado a UMA pessoa (v2.79).

    `documento` é valor de `DocumentoAssinavel` — os mesmos do kit de posto
    (`postos.DOCS_ESPECIFICOS_DISPONIVEIS`), não uma lista paralela: duas fontes
    para "quais são os documentos especiais" divergiriam na primeira mudança.

    `motivo` é OBRIGATÓRIO. É ele que explica, meses depois, por que alguém
    lotado no posto X assinou o kit do posto Y — sem isso o registro fica sem a
    metade que importa (precedente do `reverter` colaborador→candidato, v1.65,
    e da troca de matrícula, v2.45).
    """
    documento: str
    motivo: str = ""


@router.get("/rh/candidatos/{candidato_id}/documentos-especificos")
def listar_documentos_especificos(candidato_id: uuid.UUID,
                                  db: Session = Depends(get_db)) -> dict:
    """O que dá para acrescentar a esta pessoa, e o que ela já tem.

    A tela precisa das duas listas: oferecer um documento que a pessoa já
    assinou faria o RH clicar e receber um 409 — erro que o sistema podia ter
    evitado.
    """
    from app.api.postos import DOCS_ESPECIFICOS_DISPONIVEIS
    from app.models.assinatura import Assinatura

    cand = db.get(Candidato, candidato_id)
    if cand is None:
        raise HTTPException(status_code=404, detail="candidato_nao_encontrado")

    ja_tem = {
        a.documento.value if hasattr(a.documento, "value") else a.documento
        for a in db.scalars(select(Assinatura).where(
            Assinatura.candidato_id == cand.id,
            Assinatura.invalidada_em.is_(None))).all()
    }
    return {
        "disponiveis": [
            {"chave": chave, "rotulo": rotulo, "ja_tem": chave in ja_tem}
            for chave, rotulo in DOCS_ESPECIFICOS_DISPONIVEIS.items()
        ],
    }


@router.post("/rh/candidatos/{candidato_id}/documento-especifico")
def acrescentar_documento_especifico(candidato_id: uuid.UUID,
                                     payload: DocumentoEspecificoIn,
                                     db: Session = Depends(get_db),
                                     rh: UsuarioRH = Depends(requer_rh)) -> dict:
    """Acrescenta UM documento específico à pessoa, sem mexer no posto dela.

    Nasceu da COBERTURA (feedback do Bruno, 2026-08-07): *"um intermitente
    precisou dar cobertura na presidência da República. Não estava fácil marcar
    para emitir os documentos específicos da presidência"*.

    O kit da Presidência sempre existiu e sempre foi selecionável — mas **por
    POSTO**, e numa cobertura a pessoa justamente NÃO está lotada no posto que
    exige o documento. A única saída era lotá-la lá, o que muda o vínculo dela
    para resolver uma emissão de papel; ou marcar o kit no posto dela, o que
    passaria a exigir aqueles documentos de todo mundo daquele posto.

    Aqui é para UMA pessoa e mais nada. O documento nasce como qualquer outro do
    kit (`Assinatura` liberada), então segue o fluxo normal: aparece para ela
    assinar, entra no dossiê, conta como pendência.

    **Não duplica assinatura viva**: se a pessoa já tem aquele documento
    pendente ou assinado, responde 409 — reemitir apagaria o que ela já assinou.
    Para trocar, existe o caminho de invalidar.
    """
    from app.api.postos import DOCS_ESPECIFICOS_DISPONIVEIS
    from app.models.assinatura import Assinatura, DocumentoAssinavel

    cand = db.get(Candidato, candidato_id)
    if cand is None:
        raise HTTPException(status_code=404, detail="candidato_nao_encontrado")
    if cand.status == StatusCandidato.expurgado:
        raise HTTPException(status_code=409, detail="candidato_expurgado")

    chave = (payload.documento or "").strip()
    if chave not in DOCS_ESPECIFICOS_DISPONIVEIS:
        # Só os do catálogo: aceitar qualquer valor do enum deixaria o RH
        # acrescentar ficha de integração ou termo de VT por engano — documentos
        # que o sistema decide sozinho, por regime e por posto.
        raise HTTPException(status_code=422, detail="documento_nao_disponivel")
    doc = DocumentoAssinavel(chave)

    motivo = (payload.motivo or "").strip()
    if not motivo:
        raise HTTPException(status_code=422, detail="motivo_obrigatorio")

    ja = db.scalar(select(Assinatura).where(
        Assinatura.candidato_id == cand.id,
        Assinatura.documento == doc,
        Assinatura.invalidada_em.is_(None)))
    if ja is not None:
        raise HTTPException(status_code=409, detail={
            "erro": "documento_ja_existe",
            "assinado": ja.assinado_em is not None,
            "rotulo": DOCS_ESPECIFICOS_DISPONIVEIS[chave],
        })

    db.add(Assinatura(candidato_id=cand.id, documento=doc,
                      aguardando_liberacao=False))
    # O posto DA PESSOA vai para a auditoria de propósito: é o contraste que
    # explica o registro — "lotada no posto X, assinou o kit do posto Y". Sem
    # ele, o motivo escrito pelo RH fica sem o contexto que o torna verificável.
    # (`Candidato` tem a FK, não um relationship — daí o `db.get`.)
    from app.models.candidato import PostoServico
    posto = (db.get(PostoServico, cand.posto_servico_id)
             if cand.posto_servico_id else None)
    registrar(db, "documento_especifico_acrescentado", ator="rh",
              ator_detalhe=rh.email, candidato_id=cand.id,
              detalhe={"documento": chave, "motivo": motivo,
                       "posto_da_pessoa": posto.nome if posto else None})
    db.commit()
    return {"ok": True, "documento": chave,
            "rotulo": DOCS_ESPECIFICOS_DISPONIVEIS[chave]}


# --------------------------------------------------------------------------
# EXIGÊNCIAS (v2.80) — o que é obrigatório, para todos e para cada pessoa
# --------------------------------------------------------------------------
# Pedido do Bruno: *"por padrão vir marcado os campos obrigatórios para todos
# (lógico, aqueles que têm que ser obrigatórios), mas customizável por
# candidato, pelo pessoal do RH. Daí ter um padrão geral lá em configurações"*.
#
# A resolução em três camadas mora em `services/exigencias.py`; aqui só ficam as
# portas. A do PADRÃO GERAL está em `configuracoes.py`, junto da config dinâmica.

class ExigenciaIn(BaseModel):
    """Ajuste de UMA exigência para UMA pessoa.

    `obrigatorio = None` REMOVE a exceção e devolve a pessoa ao padrão da casa —
    é o "desfazer". Sem ele, uma dispensa dada por engano ficaria para sempre, e
    o RH teria que adivinhar o padrão para reproduzi-lo à mão.
    """
    grupo: str                     # "documentos" | "campos"
    chave: str
    obrigatorio: bool | None = None
    motivo: str = ""


def _validar_exigencia(grupo: str, chave: str) -> None:
    """Recusa grupo/chave inválidos e o que é do SISTEMA.

    ⚠️ A ordem importa, e ela custou uma mutação para aparecer: o guard de
    `SEMPRE_OBRIGATORIOS` vem ANTES da checagem de catálogo. `pessoais.email` e
    `documentos.cpf` não estão em `CAMPOS_PADRAO` (não são configuráveis), então
    a checagem de catálogo já os recusaria — mas com a mensagem ERRADA
    ("chave_desconhecida"), e a proteção real sumiria no dia em que alguém
    acrescentasse essas chaves ao catálogo. Validar na ordem certa faz o motivo
    da recusa ser o verdadeiro.
    """
    from app.services.exigencias import (CAMPOS_PADRAO, DOCUMENTOS_PADRAO,
                                         SEMPRE_OBRIGATORIOS)
    if grupo not in ("documentos", "campos"):
        raise HTTPException(status_code=422, detail="grupo_invalido")
    if chave in SEMPRE_OBRIGATORIOS:
        # Não é preciosismo: sem aceite LGPD não há base legal para guardar a
        # ficha; sem e-mail o código de assinatura não chega e a admissão para
        # no meio; sem CPF a pessoa não casa em creche, Tirvu nem ponto.
        # Quebraria LONGE daqui, onde ninguém ligaria uma coisa à outra.
        raise HTTPException(status_code=422, detail="exigencia_do_sistema")
    catalogo = DOCUMENTOS_PADRAO if grupo == "documentos" else CAMPOS_PADRAO
    if chave not in catalogo:
        raise HTTPException(status_code=422, detail="chave_desconhecida")


@router.get("/rh/candidatos/{candidato_id}/exigencias")
def ler_exigencias(candidato_id: uuid.UUID, db: Session = Depends(get_db)) -> dict:
    """O que é exigido desta pessoa, com a ORIGEM de cada item.

    A origem (`fabrica` / `casa` / `pessoa` / `sistema`) é o que deixa a tela
    dizer *"dispensado para esta pessoa"* em vez de só mostrar um check
    desmarcado — sem ela o RH não distingue "o padrão é assim" de "alguém
    decidiu isto aqui".
    """
    from app.services.exigencias import dump_para_tela

    cand = db.get(Candidato, candidato_id)
    if cand is None:
        raise HTTPException(status_code=404, detail="candidato_nao_encontrado")
    return dump_para_tela(db, cand)


@router.put("/rh/candidatos/{candidato_id}/exigencias")
def ajustar_exigencia(candidato_id: uuid.UUID, payload: ExigenciaIn,
                      db: Session = Depends(get_db),
                      rh: UsuarioRH = Depends(requer_rh)) -> dict:
    """Dispensa ou passa a exigir UM item, só para esta pessoa.

    O MOTIVO é obrigatório ao mudar (não ao desfazer): é ele que explica, meses
    depois, por que aquela pessoa não entregou um documento que todo mundo
    entrega. Mesma regra do `reverter` (v1.65) e da troca de matrícula (v2.45).

    Ao mudar DOCUMENTO, os slots são ressincronizados na hora — senão a tela do
    candidato continuaria pedindo o que acabou de ser dispensado, e ele veria a
    mudança só no autosave seguinte.
    """
    from app.services.exigencias import ROTULOS

    cand = db.get(Candidato, candidato_id)
    if cand is None:
        raise HTTPException(status_code=404, detail="candidato_nao_encontrado")

    grupo = (payload.grupo or "").strip()
    chave = (payload.chave or "").strip()
    _validar_exigencia(grupo, chave)

    motivo = (payload.motivo or "").strip()
    if payload.obrigatorio is not None and not motivo:
        raise HTTPException(status_code=422, detail="motivo_obrigatorio")

    # Reescreve o dicionário inteiro em vez de mutar em profundidade: o
    # SQLAlchemy não detecta mudança DENTRO de um JSON já carregado, e a
    # gravação se perderia em silêncio.
    atual = dict(cand.exigencias or {})
    do_grupo = dict(atual.get(grupo) or {})
    if payload.obrigatorio is None:
        do_grupo.pop(chave, None)      # volta ao padrão da casa
    else:
        do_grupo[chave] = bool(payload.obrigatorio)
    atual[grupo] = do_grupo
    cand.exigencias = {g: v for g, v in atual.items() if v}  # não guarda grupo vazio

    if grupo == "documentos":
        from app.services.slots import sincronizar_slots
        sincronizar_slots(db, cand)

    registrar(db, "exigencia_ajustada", ator="rh", ator_detalhe=rh.email,
              candidato_id=cand.id,
              detalhe={"grupo": grupo, "chave": chave,
                       "rotulo": ROTULOS.get(chave, chave),
                       "obrigatorio": payload.obrigatorio,
                       "motivo": motivo or None})
    db.commit()
    return {"ok": True, "grupo": grupo, "chave": chave,
            "obrigatorio": payload.obrigatorio,
            "rotulo": ROTULOS.get(chave, chave)}
