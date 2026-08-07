"""Poderes manuais do RH (fase 2 do feedback de campo, 2026-07-15).

Linhas vermelhas do projeto (mesa-redonda de segurança):
1. Nada some sem hash na auditoria.
2. Toda ação manual do RH sai assinada com o usuário e o motivo.
3. O clique de assinar é SEMPRE do candidato — o RH prepara, nunca assina.

Daqui saem: upload manual de documento recebido fora do sistema (WhatsApp,
presencial), reabertura de status de slot, e edição de dados da ficha com
invalidação granular das assinaturas afetadas (só as fichas onde o dado
aparece voltam para o candidato assinar — a operação não para).
"""

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Form, HTTPException, Request, UploadFile
from pydantic import BaseModel, ValidationError
from sqlalchemy import select
from sqlalchemy.exc import DataError
from sqlalchemy.orm import Session

from app.api.auth_rh import requer_rh
from app.core.config import base_url_publica
from app.core.db import get_db
from app.models.assinatura import Assinatura, DocumentoAssinavel
from app.models.candidato import Candidato, StatusCandidato
from app.models.documento import SlotDocumento, StatusSlot
from app.models.usuario_rh import UsuarioRH
from app.services.auditoria import registrar
from app.services.email_templates import enviar_modelo
from app.services.idempotencia import travar_por
from app.services.magic_link import emitir_link
from app.services.normalizacao import ArquivoInvalido, normalizar_para_pdf
from app.services.upload_seguro import EXTENSOES_COM_WORD, ler_upload_sync

router = APIRouter(tags=["rh-manual"], dependencies=[Depends(requer_rh)])

_TODOS = list(DocumentoAssinavel)

# Em qual documento assinável cada seção da ficha aparece. Mapa CONSERVADOR:
# na dúvida, invalida — melhor o candidato re-assinar do que um PDF assinado
# divergir dos dados reais.
DOCS_POR_SECAO: dict[str, list[DocumentoAssinavel]] = {
    "pessoais": _TODOS,
    "documentos": _TODOS,
    "endereco": [DocumentoAssinavel.ficha_cadastro, DocumentoAssinavel.termo_vt],
    "trabalho-banco": [DocumentoAssinavel.ficha_cadastro],
    "vt-emergencia": [DocumentoAssinavel.termo_vt, DocumentoAssinavel.ficha_emergencia],
}


def invalidar_assinaturas_afetadas(db: Session, candidato: Candidato, secao: str,
                                   ator_detalhe: str, campos: list[str]) -> list[str]:
    """Invalida (nunca deleta) as assinaturas concluídas dos documentos onde a
    seção editada aparece, e cria um novo registro pendente de cada um. Devolve
    os nomes dos documentos que voltaram para assinatura."""
    invalidados: list[str] = []
    for doc in DOCS_POR_SECAO.get(secao, []):
        assinatura = db.scalar(
            select(Assinatura).where(
                Assinatura.candidato_id == candidato.id, Assinatura.documento == doc,
                Assinatura.assinado_em.isnot(None), Assinatura.invalidada_em.is_(None),
            )
        )
        if assinatura is None:
            continue
        assinatura.invalidada_em = datetime.now(timezone.utc)
        assinatura.invalidada_motivo = (
            f"Dados da seção '{secao}' atualizados por {ator_detalhe} "
            f"(campos: {', '.join(campos)})"
        )[:300]
        registrar(db, "assinatura_invalidada", ator="rh", ator_detalhe=ator_detalhe,
                  candidato_id=candidato.id,
                  detalhe={"documento": doc.value, "hash": assinatura.hash_sha256,
                           "secao": secao, "campos": campos})
        db.add(Assinatura(candidato_id=candidato.id, documento=doc))
        invalidados.append(doc.value)
    return invalidados


class EdicaoSecaoIn(BaseModel):
    dados: dict
    motivo: str


# Campos de coluna curta (String(2)/(8)/(4)) onde o RH digitando com máscara ou
# por extenso ("Distrito Federal", "70000-000") estourava DataError no commit —
# 500 mudo (feedback de campo 2026-07-27). Normaliza ANTES da validação do
# Pydantic, espelhando o que a rota do candidato já faz com o CPF.
_CAMPOS_UF = ("uf", "naturalidade_uf", "cnh_uf")
_CAMPOS_CEP = ("cep",)


def _normalizar_entrada(dados: dict) -> dict:
    saida = dict(dados)
    for campo in _CAMPOS_UF:
        if campo in saida and isinstance(saida[campo], str):
            saida[campo] = saida[campo].strip().upper()[:2] or None
    for campo in _CAMPOS_CEP:
        if campo in saida and isinstance(saida[campo], str):
            numeros = "".join(c for c in saida[campo] if c.isdigit())
            saida[campo] = numeros or None
    return saida


@router.get("/rh/candidatos/{candidato_id}/ficha")
def ficha_do_candidato(candidato_id: uuid.UUID, db: Session = Depends(get_db)) -> dict:
    from app.api.ficha import montar_ficha
    candidato = db.get(Candidato, candidato_id)
    if candidato is None:
        raise HTTPException(status_code=404, detail="candidato_nao_encontrado")
    return montar_ficha(db, candidato)


@router.get("/rh/candidatos/{candidato_id}/fichas/{documento}")
def baixar_ficha_rh(candidato_id: uuid.UUID, documento: str,
                    db: Session = Depends(get_db)):
    """PDF de qualquer ficha (fixa ou de modelo) para o RH baixar e enviar
    manualmente se preciso: a via assinada (com o bloco), se existir; senão a
    prévia com os dados atuais. Vale assinada OU não — rede de segurança."""
    from fastapi import Response

    from app.api.assinaturas import _gerar_pdf, _resolver_doc
    from app.services import storage

    candidato = db.get(Candidato, candidato_id)
    if candidato is None:
        raise HTTPException(status_code=404, detail="candidato_nao_encontrado")
    _, assinatura = _resolver_doc(db, candidato, documento)
    if assinatura.assinado_em is not None and assinatura.pdf_key:
        pdf = storage.ler(assinatura.pdf_key)
        sufixo = "-assinada"
    else:
        pdf = _gerar_pdf(db, candidato, assinatura)
        sufixo = "-previa"
    nome = "".join(c for c in candidato.nome_completo if c.isalnum() or c in " -_").strip()[:40]
    return Response(
        content=pdf, media_type="application/pdf",
        headers={"Content-Disposition":
                 f'attachment; filename="{documento}{sufixo}-{nome}.pdf"'})


@router.put("/rh/candidatos/{candidato_id}/ficha/{secao}")
def editar_secao(
    candidato_id: uuid.UUID,
    secao: str,
    payload: EdicaoSecaoIn,
    request: Request,
    db: Session = Depends(get_db),
    rh: UsuarioRH = Depends(requer_rh),
) -> dict:
    """O RH completa/corrige dados da ficha. Validação idêntica à do candidato
    (mesmos schemas); auditoria com antes → depois; e se algum documento já
    assinado exibe esses dados, a assinatura é invalidada e o candidato é
    avisado para assinar a versão atualizada — quem assina é sempre ele."""
    from app.api import ficha as ficha_api

    candidato = db.get(Candidato, candidato_id)
    if candidato is None:
        raise HTTPException(status_code=404, detail="candidato_nao_encontrado")
    if candidato.status == StatusCandidato.expurgado:
        raise HTTPException(status_code=409, detail="candidato_expurgado")
    if not payload.motivo.strip():
        raise HTTPException(status_code=422, detail="motivo_obrigatorio")

    schemas = {
        "pessoais": (ficha_api.SecaoPessoais, ficha_api.DadosPessoais),
        "endereco": (ficha_api.SecaoEndereco, ficha_api.Endereco),
        "documentos": (ficha_api.SecaoDocumentos, ficha_api.DocumentosIdentificacao),
        "trabalho-banco": (ficha_api.SecaoTrabalhoBanco,
                           ficha_api.DadosProfissionaisBancarios),
        "vt-emergencia": (ficha_api.SecaoVtEmergencia, None),
    }
    if secao not in schemas:
        raise HTTPException(status_code=404, detail="secao_desconhecida")
    schema, modelo = schemas[secao]

    bruto = _normalizar_entrada(payload.dados)
    try:
        dados = schema(**bruto).model_dump(exclude_unset=True)
    except ValidationError as exc:
        # A validação deste endpoint roda manualmente (payload.dados é um dict
        # livre — o FastAPI não valida o conteúdo), então uma ValidationError
        # do Pydantic NÃO é RequestValidationError e escaparia como 500 mudo
        # sem este catch (feedback de campo 2026-07-27: "não salva e não diz
        # o motivo"). Devolve 422 com o mesmo formato de {loc, msg, type} que
        # o handler global de RequestValidationError já usa (main.py).
        erros = [{"loc": [str(p) for p in e.get("loc", [])], "msg": e.get("msg", ""),
                  "type": e.get("type", "")} for e in exc.errors()]
        raise HTTPException(status_code=422, detail=erros) from exc
    if not dados:
        raise HTTPException(status_code=422, detail="nada_para_alterar")

    # Antes → depois, campo a campo, para a auditoria.
    mudancas: dict[str, tuple] = {}

    def _aplicar(obj, campo: str, valor) -> None:
        mudancas[campo] = (getattr(obj, campo, None), valor)
        setattr(obj, campo, valor)

    if secao == "pessoais":
        for campo in ("nome_completo", "email", "celular_whatsapp"):
            if campo in dados:
                valor = dados.pop(campo)
                # Mesma padronização da entrada do candidato: o RH corrige a
                # ficha por aqui, e sem isto a correção reintroduziria o nome
                # em caixa alta que o wizard tinha acabado de normalizar.
                if campo == "nome_completo" and valor:
                    from app.services.nomes import capitalizar_nome
                    valor = capitalizar_nome(valor)
                _aplicar(candidato, campo, valor)
    if secao == "vt-emergencia":
        from app.models.ficha import FichaEmergencia, ValeTransporte
        vt = {k.removeprefix("vt_"): v for k, v in dados.items() if k.startswith("vt_")}
        emergencia = {k: v for k, v in dados.items() if not k.startswith("vt_")}
        vt.pop("ciencia_cartao_go", None)  # ciência é ato do candidato, não do RH
        for cls, valores in ((ValeTransporte, vt), (FichaEmergencia, emergencia)):
            if not valores:
                continue
            obj = db.get(cls, candidato.id) or cls(candidato_id=candidato.id)
            db.add(obj)
            for campo, valor in valores.items():
                _aplicar(obj, campo, valor)
    elif dados:
        obj = db.get(modelo, candidato.id) or modelo(candidato_id=candidato.id)
        db.add(obj)
        for campo, valor in dados.items():
            _aplicar(obj, campo, valor)

    if not mudancas:
        raise HTTPException(status_code=422, detail="nada_para_alterar")
    campos = sorted(mudancas.keys())

    # Valida os dados no BANCO antes de qualquer outra escrita. Precisa vir
    # ANTES de registrar()/invalidar_assinaturas_afetadas: registrar() faz seu
    # próprio db.flush() e engole exceção (auditoria nunca derruba a ação
    # principal) — se o DataError disparasse ali, a sessão ficava com rollback
    # pendente e a query seguinte (invalidar_assinaturas_afetadas) estourava
    # PendingRollbackError em vez do 422 que o RH precisa ver.
    try:
        db.flush()
    except DataError as exc:
        # Estourou no banco (ex.: tipo_sanguineo "A positivo" em coluna
        # String(4)) — sem este catch, o handler global de main.py devolve
        # 500 genérico e o RH não sabe qual campo corrigir. O texto real do
        # driver NUNCA vai ao cliente (pode conter o valor que estourou).
        db.rollback()
        raise HTTPException(
            status_code=422,
            detail=[{"loc": ["dados", c], "msg": "Valor não suportado para este campo "
                     "(muito longo ou em formato inesperado).", "type": "value_error"}
                    for c in campos],
        ) from exc

    registrar(db, "ficha_editada_rh", ator="rh", ator_detalhe=rh.email,
              candidato_id=candidato.id,
              detalhe={"secao": secao, "motivo": payload.motivo.strip(),
                       "antes": {k: _txt(v[0]) for k, v in mudancas.items()},
                       "depois": {k: _txt(v[1]) for k, v in mudancas.items()}})

    invalidados = invalidar_assinaturas_afetadas(db, candidato, secao, rh.email, campos)
    # PCD marcado pelo RH (v2.43, feedback 2026-08-01): a pessoa não declarou —
    # é dado de saúde, e muita gente evita — e o RH soube por fora. Marcar aqui
    # faz o LAUDO virar documento obrigatório; se ela já concluiu o envio, o
    # checklist está congelado e a pendência não teria como ser resolvida por
    # ninguém. Então o laudo já nasce LIBERADO para ela enviar, sem reabrir o
    # resto da admissão.
    laudo_pedido = False
    if "pcd" in mudancas and mudancas["pcd"][1] is True:
        laudo_pedido = _liberar_laudo_pcd(db, candidato, rh.email)
    db.commit()

    email_enviado = False
    if invalidados and candidato.email:
        link = emitir_link(db, candidato, base_url_publica(request))
        db.commit()
        nomes = _nomes_docs(invalidados)
        email_enviado = enviar_modelo(db, "ficha_alterada_reassinar", candidato.email, {
            "nome": candidato.nome_completo,
            "motivo": payload.motivo.strip(),
            "lista": '\n'.join(f"- {n}" for n in nomes),
            "link": link,
        })

    return {"secao": secao, "campos_alterados": campos,
            "assinaturas_invalidadas": invalidados, "email_enviado": email_enviado,
            # O front avisa o RH de que o laudo foi pedido — senão ele marca
            # PCD, some um documento novo na lista da pessoa e ninguém sabe por
            # quê.
            "laudo_pcd_pedido": laudo_pedido}


def _liberar_laudo_pcd(db: Session, candidato: Candidato, autor: str) -> bool:
    """Cria/libera o slot do laudo de PCD para a pessoa enviar. Devolve se
    houve algo a fazer.

    Não mexe em quem JÁ enviou o laudo (o documento está lá, foi a ficha que
    demorou a refletir isso) nem em quem ainda está preenchendo — nesse caso o
    checklist ainda está aberto e o slot aparece sozinho, pela sincronização
    normal.
    """
    from datetime import datetime, timezone

    from app.models.documento import SlotDocumento, StatusSlot, TipoDocumento

    slot = db.scalar(select(SlotDocumento).where(
        SlotDocumento.candidato_id == candidato.id,
        SlotDocumento.tipo == TipoDocumento.laudo_pcd,
        SlotDocumento.dependente_id.is_(None)))
    if slot is not None and slot.status in (StatusSlot.enviado, StatusSlot.aprovado):
        return False
    congelado = candidato.status in (StatusCandidato.envio_concluido,
                                     StatusCandidato.aprovado)
    if not congelado:
        return False        # o checklist está aberto: o slot aparece sozinho
    if slot is None:
        slot = SlotDocumento(candidato_id=candidato.id,
                             tipo=TipoDocumento.laudo_pcd, obrigatorio=True)
        db.add(slot)
    slot.liberado_em = datetime.now(timezone.utc)
    slot.liberado_por = autor
    registrar(db, "documento_pedido_ao_candidato", ator="rh", ator_detalhe=autor,
              candidato_id=candidato.id,
              detalhe={"tipo": TipoDocumento.laudo_pcd.value,
                       "motivo": "PCD registrado pelo RH",
                       "status_candidato": candidato.status.value})
    return True


def _txt(v) -> str | None:
    if v is None:
        return None
    return str(v.value) if hasattr(v, "value") else str(v)


def _nomes_docs(valores: list[str]) -> list[str]:
    from app.api.assinaturas import NOMES_DOC
    return [NOMES_DOC[DocumentoAssinavel(v)] for v in valores]


@router.post("/rh/slots/{slot_id}/arquivo")
def inserir_arquivo_rh(
    slot_id: uuid.UUID,
    arquivo: UploadFile | None = None,
    arquivos: list[UploadFile] | None = None,
    origem: str = Form("whatsapp"),
    db: Session = Depends(get_db),
    rh: UsuarioRH = Depends(requer_rh),
) -> dict:
    """Documento que chegou fora do sistema (WhatsApp, e-mail, presencial):
    o RH insere no slot com etiqueta de origem — visível no painel e na
    auditoria. Aceita VÁRIOS arquivos no mesmo tipo (ex.: RG frente+verso, ou
    substituir docs errados pelos certos) — viram um único PDF combinado, igual
    ao envio do candidato. Passa pelas mesmas validações."""
    from app.api.documentos import _gravar_partes_no_slot, _slot_out
    from app.services.normalizacao import combinar_pdfs

    slot = db.get(SlotDocumento, slot_id)
    if slot is None:
        raise HTTPException(status_code=404, detail="slot_nao_encontrado")
    candidato = db.get(Candidato, slot.candidato_id)

    lista = ([arquivo] if arquivo is not None else []) + (arquivos or [])
    if not lista:
        raise HTTPException(status_code=422, detail="arquivo_vazio")

    try:
        partes = []  # (nome, content_type, dados, pdf)
        for up in lista:
            # v2.71: o docstring acima sempre disse "passa pelas mesmas
            # validações" — e passava também pela mesma FALHA, o spool sem
            # `close()`. Agora passa pelas mesmas de verdade.
            dados = ler_upload_sync(db, up, EXTENSOES_COM_WORD)
            pdf, _ = normalizar_para_pdf(up.filename or "arquivo", dados,
                                         rotulo=slot.tipo.value)
            partes.append((up.filename or "arquivo", up.content_type, dados, pdf))
        pdf_final, paginas = combinar_pdfs([p[3] for p in partes])
    except ArquivoInvalido as exc:
        raise HTTPException(status_code=422, detail=exc.codigo) from exc

    _gravar_partes_no_slot(db, candidato, slot, partes, pdf_final, paginas)
    slot.origem_envio = "rh"
    slot.origem_envio_obs = origem.strip()[:120] or "whatsapp"
    registrar(db, "documento_inserido_rh", ator="rh", ator_detalhe=rh.email,
              candidato_id=candidato.id,
              detalhe={"tipo": slot.tipo.value, "origem": slot.origem_envio_obs,
                       "paginas": paginas, "arquivos": len(partes)})
    db.commit()
    return _slot_out(slot) | {"origem_envio": slot.origem_envio,
                              "origem_envio_obs": slot.origem_envio_obs}


@router.get("/rh/candidatos/{candidato_id}/informativos")
def listar_informativos(candidato_id: uuid.UUID, db: Session = Depends(get_db)) -> list[dict]:
    """Informativos de integração do candidato e se estão liberados para assinar.
    Alimenta o botão de disparo no painel do RH."""
    from app.api.assinaturas import NOMES_DOC
    from app.api.postos import DOCS_INFORMATIVO
    itens = db.scalars(
        select(Assinatura).where(
            Assinatura.candidato_id == candidato_id,
            Assinatura.documento.in_(DOCS_INFORMATIVO),
            Assinatura.invalidada_em.is_(None),
        )
    ).all()
    return [{
        "documento": a.documento.value,
        "nome": NOMES_DOC.get(a.documento, a.documento.value),
        "aguardando_liberacao": a.aguardando_liberacao,
        "assinado": a.assinado_em is not None,
    } for a in itens]


@router.post("/rh/candidatos/{candidato_id}/liberar-informativo")
def liberar_informativo(candidato_id: uuid.UUID, db: Session = Depends(get_db),
                        rh: UsuarioRH = Depends(requer_rh)) -> dict:
    """DISPARA o informativo de integração: libera para o candidato assinar. Só
    a partir daqui ele aparece no fluxo de assinatura (feedback do Bruno)."""
    from app.api.postos import DOCS_INFORMATIVO
    itens = db.scalars(
        select(Assinatura).where(
            Assinatura.candidato_id == candidato_id,
            Assinatura.documento.in_(DOCS_INFORMATIVO),
            Assinatura.aguardando_liberacao.is_(True),
            Assinatura.invalidada_em.is_(None),
        )
    ).all()
    for a in itens:
        a.aguardando_liberacao = False
    registrar(db, "informativo_liberado", ator="rh", ator_detalhe=rh.email,
              candidato_id=candidato_id, detalhe={"qtd": len(itens)})
    db.commit()
    return {"liberados": len(itens)}


@router.post("/rh/candidatos/{candidato_id}/notificar",
             dependencies=[Depends(travar_por("notificar"))])
def notificar_pendencias(candidato_id: uuid.UUID, request: Request,
                         db: Session = Depends(get_db),
                         rh: UsuarioRH = Depends(requer_rh)) -> dict:
    """Cobra o candidato por e-mail com o retrato exato do que falta: ficha
    incompleta, fichas aguardando assinatura e/ou documentos pendentes — com
    um link novo. Nasceu do incidente real: e-mail cadastrado depois, e a
    pessoa nunca soube que havia fichas para preencher e assinar."""
    from app.api.assinaturas import (NOMES_DOC, _assinaturas_modelo, _docs_exigidos,
                                     _registro, titulo_doc)
    from app.api.ficha import pendencias_da_ficha

    candidato = db.get(Candidato, candidato_id)
    if candidato is None:
        raise HTTPException(status_code=404, detail="candidato_nao_encontrado")
    if not candidato.email:
        raise HTTPException(status_code=422, detail="candidato_sem_email")

    pend_ficha = pendencias_da_ficha(db, candidato)
    fichas_pendentes = [NOMES_DOC[d] for d in _docs_exigidos(db, candidato)
                        if _registro(db, candidato, d).assinado_em is None]
    fichas_pendentes += [titulo_doc(a) for a in _assinaturas_modelo(db, candidato)
                         if a.assinado_em is None]
    slots = db.scalars(select(SlotDocumento).where(
        SlotDocumento.candidato_id == candidato.id)).all()
    docs_pendentes = [s.tipo.value.replace("_", " ")
                      for s in slots if s.obrigatorio and s.status in
                      (StatusSlot.pendente, StatusSlot.rejeitado)]

    itens: list[str] = []
    if pend_ficha:
        itens.append(f"Completar o formulário da admissão ({len(pend_ficha)} "
                     "campo(s) obrigatório(s) em aberto)")
    if fichas_pendentes:
        itens.append("Assinar eletronicamente: " + "; ".join(fichas_pendentes))
    if docs_pendentes:
        itens.append("Enviar os documentos: " + "; ".join(docs_pendentes))
    if not itens:
        raise HTTPException(status_code=409, detail="sem_pendencias")

    link = emitir_link(db, candidato, base_url_publica(request))
    registrar(db, "candidato_notificado", ator="rh", ator_detalhe=rh.email,
              candidato_id=candidato.id,
              detalhe={"pendencias_ficha": len(pend_ficha),
                       "fichas_para_assinar": len(fichas_pendentes),
                       "documentos_pendentes": len(docs_pendentes)})
    db.commit()

    lista_txt = "\n".join(f"  {i + 1}. {t}" for i, t in enumerate(itens))
    lista_html = "".join(f"<li>{t}</li>" for t in itens)
    enviado = enviar_modelo(db, "admissao_pendencias", candidato.email, {
        "nome": candidato.nome_completo,
        "lista": lista_txt, "link": link,
    })
    return {"email_enviado": enviado, "itens": itens, "link_magico": link}


@router.post("/rh/candidatos/{candidato_id}/teams")
def enviar_ao_teams(candidato_id: uuid.UUID, db: Session = Depends(get_db),
                    rh: UsuarioRH = Depends(requer_rh)) -> dict:
    """Posta no canal do Teams a mensagem do template do RH, com as variáveis
    do candidato preenchidas ({{nome}}, {{cargo}}, {{posto}}, {{status}}…)."""
    from app.services import teams
    from app.services.fichas import _contexto_modelo, aplicar_variaveis

    candidato = db.get(Candidato, candidato_id)
    if candidato is None:
        raise HTTPException(status_code=404, detail="candidato_nao_encontrado")
    if not teams.url_teams(db):
        raise HTTPException(status_code=422, detail="teams_nao_configurado")

    contexto = _contexto_modelo(db, candidato)
    contexto["status"] = candidato.status.value.replace("_", " ")
    mensagem = aplicar_variaveis(teams.template_teams(db), contexto)
    if not teams.enviar_mensagem(db, mensagem):
        raise HTTPException(status_code=422, detail="falha_no_envio_ao_teams")
    registrar(db, "teams_mensagem_enviada", ator="rh", ator_detalhe=rh.email,
              candidato_id=candidato.id)
    db.commit()
    return {"ok": True}


class ReabrirIn(BaseModel):
    motivo: str


@router.post("/rh/slots/{slot_id}/reabrir")
def reabrir_slot(slot_id: uuid.UUID, payload: ReabrirIn,
                 db: Session = Depends(get_db),
                 rh: UsuarioRH = Depends(requer_rh)) -> dict:
    """Desfaz uma aprovação/dispensa/rejeição feita por engano. Com arquivo,
    o slot volta para 'em análise'; sem arquivo, volta a 'pendente'."""
    slot = db.get(SlotDocumento, slot_id)
    if slot is None:
        raise HTTPException(status_code=404, detail="slot_nao_encontrado")
    if not payload.motivo.strip():
        raise HTTPException(status_code=422, detail="motivo_obrigatorio")
    if slot.status in (StatusSlot.pendente, StatusSlot.enviado):
        raise HTTPException(status_code=409, detail="slot_ja_esta_aberto")

    anterior = slot.status.value
    slot.status = StatusSlot.enviado if slot.arquivo_pdf_key else StatusSlot.pendente
    slot.motivo_rejeicao = None
    slot.motivo_rejeicao_obs = None
    slot.revisado_em = datetime.now(timezone.utc)
    slot.revisado_por = rh.id
    registrar(db, "slot_reaberto", ator="rh", ator_detalhe=rh.email,
              candidato_id=slot.candidato_id,
              detalhe={"tipo": slot.tipo.value, "de": anterior,
                       "para": slot.status.value, "motivo": payload.motivo.strip()})
    db.commit()
    return {"status": slot.status}
