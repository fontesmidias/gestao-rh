"""Postos de serviço: cadastro pelo RH e vínculo do candidato ao posto,
gerando os documentos adicionais para assinatura (ex.: INFRAERO)."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.auth_rh import requer_rh
from app.core.config import base_url_publica
from app.core.db import get_db
from app.models.assinatura import FICHAS_BASE, Assinatura, DocumentoAssinavel
from app.models.candidato import Candidato, PostoServico
from app.models.usuario_rh import UsuarioRH
from app.services.auditoria import registrar
from app.services.email import enviar_email, html_moderno
from app.services.magic_link import emitir_link

router = APIRouter(tags=["postos-rh"], dependencies=[Depends(requer_rh)])

DOCS_INFRAERO = (DocumentoAssinavel.oficio_cartao_cidadao,
                 DocumentoAssinavel.informacoes_trabalhador,
                 DocumentoAssinavel.termo_lgpd_infraero)

# Catálogo de documentos ESPECÍFICOS de posto que o RH pode marcar no CRUD.
# (Bruno: só Presidência e INFRAERO têm kit próprio; os demais usam o padrão.)
DOCS_ESPECIFICOS_DISPONIVEIS = {
    DocumentoAssinavel.oficio_cartao_cidadao.value: "Ofício Cartão Cidadão (INFRAERO)",
    DocumentoAssinavel.informacoes_trabalhador.value: "Informações ao Trabalhador (INFRAERO)",
    DocumentoAssinavel.termo_lgpd_infraero.value: "Termo LGPD Credenciamento (INFRAERO)",
    DocumentoAssinavel.ficha_cadastral_terceirizado.value:
        "Ficha Cadastral de Terceirizado (Presidência)",
    DocumentoAssinavel.oficio_apresentacao_presidencia.value:
        "Ofício de Apresentação (Presidência)",
}


def gerar_docs_do_posto_e_regime(db: Session, candidato: Candidato) -> list[DocumentoAssinavel]:
    """Cria os registros de Assinatura extras exigidos pelo POSTO (kit marcado no
    CRUD + o legado exige_docs_infraero) e pelo REGIME (Informativo do
    Intermitente) deste candidato, que ainda não existam. Fonte única usada pelo
    convite e pela (re)definição de posto."""
    existentes = {
        a.documento for a in db.scalars(
            select(Assinatura).where(Assinatura.candidato_id == candidato.id,
                                     Assinatura.invalidada_em.is_(None))).all()
    }
    exigidos: list[DocumentoAssinavel] = []
    posto = (db.get(PostoServico, candidato.posto_servico_id)
             if candidato.posto_servico_id else None)
    if posto:
        if posto.exige_docs_infraero:   # legado (posto INFRAERO existente)
            exigidos += list(DOCS_INFRAERO)
        for chave in (posto.documentos_kit or []):
            try:
                exigidos.append(DocumentoAssinavel(chave))
            except ValueError:
                pass  # chave desconhecida (ex.: enum removido): ignora
    if candidato.regime == "intermitente":
        exigidos.append(DocumentoAssinavel.informativo_intermitente)
    novos = []
    for doc in exigidos:
        if doc not in existentes and doc not in novos:
            db.add(Assinatura(candidato_id=candidato.id, documento=doc))
            novos.append(doc)
    return novos


# ---------- CRUD de postos ----------


CHAVE_COLUNAS = "posto_colunas"  # colunas dinâmicas (config global do painel)


class PostoIn(BaseModel):
    nome: str
    sigla: str | None = None
    cnpj: str | None = None
    contrato_ref: str | None = None
    exige_docs_infraero: bool | None = None
    documentos_kit: list[str] | None = None
    atributos: dict | None = None
    da_direito_creche: bool | None = None
    valor_reembolso_creche: str | None = None


def _dump_posto(p: PostoServico) -> dict:
    return {"id": p.id, "nome": p.nome, "sigla": p.sigla, "cnpj": p.cnpj,
            "contrato_ref": p.contrato_ref, "exige_docs_infraero": p.exige_docs_infraero,
            "documentos_kit": p.documentos_kit or [],
            "atributos": p.atributos or {}, "ativo": p.ativo,
            "da_direito_creche": p.da_direito_creche,
            "valor_reembolso_creche": p.valor_reembolso_creche}


def _colunas(db: Session) -> list[str]:
    from app.services.config_dinamica import ler_config
    import json
    bruto = ler_config(db, (CHAVE_COLUNAS,)).get(CHAVE_COLUNAS)
    try:
        return json.loads(bruto) if bruto else []
    except Exception:
        return []


@router.get("/rh/postos")
def listar_postos(incluir_inativos: bool = False,
                  db: Session = Depends(get_db)) -> dict:
    consulta = select(PostoServico).order_by(PostoServico.nome)
    if not incluir_inativos:
        consulta = consulta.where(PostoServico.ativo == True)  # noqa: E712
    postos = db.scalars(consulta).all()
    return {"postos": [_dump_posto(p) for p in postos], "colunas": _colunas(db),
            "documentos_disponiveis": DOCS_ESPECIFICOS_DISPONIVEIS}


@router.put("/rh/postos/colunas")
def definir_colunas(payload: dict, db: Session = Depends(get_db),
                    rh: UsuarioRH = Depends(requer_rh)) -> dict:
    """Colunas dinâmicas da tabela de postos (para oportunidades futuras) —
    sem DDL: são chaves guardadas em `atributos` de cada posto."""
    import json
    colunas = [str(c).strip() for c in (payload.get("colunas") or []) if str(c).strip()]
    from app.services.config_dinamica import gravar_config
    gravar_config(db, {CHAVE_COLUNAS: json.dumps(colunas, ensure_ascii=False)})
    registrar(db, "posto_colunas_alteradas", ator="rh", ator_detalhe=rh.email,
              detalhe={"colunas": colunas})
    db.commit()
    return {"colunas": colunas}


@router.post("/rh/postos", status_code=201)
def criar_posto(payload: PostoIn, db: Session = Depends(get_db),
                rh: UsuarioRH = Depends(requer_rh)) -> dict:
    nome = payload.nome.strip()
    if not nome:
        raise HTTPException(status_code=422, detail="nome_obrigatorio")
    if db.scalar(select(PostoServico).where(PostoServico.nome == nome)):
        raise HTTPException(status_code=409, detail="posto_ja_existe")
    posto = PostoServico(
        nome=nome, sigla=(payload.sigla or "").strip() or None,
        cnpj=(payload.cnpj or "").strip() or None,
        contrato_ref=(payload.contrato_ref or "").strip() or None,
        exige_docs_infraero=bool(payload.exige_docs_infraero),
        documentos_kit=[k for k in (payload.documentos_kit or [])
                        if k in DOCS_ESPECIFICOS_DISPONIVEIS],
        atributos=payload.atributos or {},
        da_direito_creche=bool(payload.da_direito_creche),
        valor_reembolso_creche=(payload.valor_reembolso_creche or "").strip() or None)
    db.add(posto)
    registrar(db, "posto_criado", ator="rh", ator_detalhe=rh.email, detalhe={"nome": nome})
    db.commit()
    return _dump_posto(posto)


@router.put("/rh/postos/{posto_id}")
def editar_posto(posto_id: uuid.UUID, payload: PostoIn, db: Session = Depends(get_db),
                 rh: UsuarioRH = Depends(requer_rh)) -> dict:
    posto = db.get(PostoServico, posto_id)
    if posto is None:
        raise HTTPException(status_code=404, detail="posto_nao_encontrado")
    if payload.nome.strip():
        posto.nome = payload.nome.strip()
    posto.sigla = (payload.sigla or "").strip() or None
    posto.cnpj = (payload.cnpj or "").strip() or None
    posto.contrato_ref = (payload.contrato_ref or "").strip() or None
    if payload.exige_docs_infraero is not None:
        posto.exige_docs_infraero = payload.exige_docs_infraero
    if payload.documentos_kit is not None:
        posto.documentos_kit = [k for k in payload.documentos_kit
                                if k in DOCS_ESPECIFICOS_DISPONIVEIS]
    if payload.atributos is not None:
        posto.atributos = payload.atributos
    if payload.da_direito_creche is not None:
        posto.da_direito_creche = payload.da_direito_creche
    if payload.valor_reembolso_creche is not None:
        posto.valor_reembolso_creche = payload.valor_reembolso_creche.strip() or None
    registrar(db, "posto_editado", ator="rh", ator_detalhe=rh.email,
              detalhe={"nome": posto.nome})
    db.commit()
    return _dump_posto(posto)


@router.delete("/rh/postos/{posto_id}", status_code=204)
def excluir_posto(posto_id: uuid.UUID, db: Session = Depends(get_db),
                  rh: UsuarioRH = Depends(requer_rh)) -> None:
    """Exclusão SOFT (ativo=False): candidatos já vinculados a este posto e a
    auditoria continuam íntegros — o posto só some das listas de escolha."""
    posto = db.get(PostoServico, posto_id)
    if posto is None:
        raise HTTPException(status_code=404, detail="posto_nao_encontrado")
    posto.ativo = False
    registrar(db, "posto_desativado", ator="rh", ator_detalhe=rh.email,
              detalhe={"nome": posto.nome})
    db.commit()


class ImportarPostosIn(BaseModel):
    # Uma linha por posto: "Nome; Sigla; CNPJ; Contrato" (só o nome é obrigatório).
    texto: str


@router.post("/rh/postos/importar")
def importar_postos(payload: ImportarPostosIn, db: Session = Depends(get_db),
                    rh: UsuarioRH = Depends(requer_rh)) -> dict:
    """Importa vários postos de uma vez a partir de texto colado (uma linha por
    posto, campos separados por ';' ou tab). Postos com nome já existente são
    ignorados (não duplica). Devolve o que criou e o que pulou."""
    existentes = {p.nome.strip().lower()
                  for p in db.scalars(select(PostoServico)).all()}
    criados, pulados = [], []
    for linha in payload.texto.splitlines():
        linha = linha.strip()
        if not linha:
            continue
        partes = [c.strip() for c in re_split(linha)]
        nome = partes[0] if partes else ""
        if not nome:
            continue
        if nome.lower() in existentes:
            pulados.append(nome)
            continue
        posto = PostoServico(
            nome=nome,
            sigla=(partes[1] if len(partes) > 1 else "") or None,
            cnpj=(partes[2] if len(partes) > 2 else "") or None,
            contrato_ref=(partes[3] if len(partes) > 3 else "") or None,
        )
        db.add(posto)
        existentes.add(nome.lower())
        criados.append(nome)
    registrar(db, "postos_importados", ator="rh", ator_detalhe=rh.email,
              detalhe={"criados": len(criados), "pulados": len(pulados)})
    db.commit()
    return {"criados": criados, "pulados": pulados}


def re_split(linha: str) -> list[str]:
    import re
    return re.split(r"\t|;", linha)


# ---------- Vínculo do candidato + geração dos documentos ----------


class AdicionalIn(BaseModel):
    nome: str
    valor: str
    tipo: str = "reais"  # "reais" | "percentual"


class PostoCandidatoIn(BaseModel):
    posto_id: uuid.UUID | None = None  # None = remover o posto
    cargo_funcao: str | None = None
    salario_base: str | None = None
    adicionais: list[AdicionalIn] | None = None  # None = não mexe; [] = limpa


@router.put("/rh/candidatos/{candidato_id}/posto")
def definir_posto(candidato_id: uuid.UUID, payload: PostoCandidatoIn, request: Request,
                  db: Session = Depends(get_db),
                  rh: UsuarioRH = Depends(requer_rh)) -> dict:
    """Vincula o candidato ao posto. Se o posto exige documentos adicionais
    (INFRAERO), eles entram na fila de assinatura e o candidato é avisado por
    e-mail com um link novo — o mesmo código único assina tudo."""
    candidato = db.get(Candidato, candidato_id)
    if candidato is None:
        raise HTTPException(status_code=404, detail="candidato_nao_encontrado")

    # Guarda o estado anterior dos campos que aparecem na ficha de cadastro,
    # para saber se a via já assinada precisa ser reemitida.
    antes = (candidato.cargo_funcao, candidato.salario_base,
             list(candidato.adicionais or []))

    def _aplica_remuneracao() -> None:
        candidato.cargo_funcao = (payload.cargo_funcao or "").strip() or None
        if payload.salario_base is not None:
            candidato.salario_base = payload.salario_base.strip() or None
        if payload.adicionais is not None:
            candidato.adicionais = [a.model_dump() for a in payload.adicionais]

    if payload.posto_id is None:
        candidato.posto_servico_id = None
        _aplica_remuneracao()
    else:
        posto = db.get(PostoServico, payload.posto_id)
        if posto is None:
            raise HTTPException(status_code=404, detail="posto_nao_encontrado")
        candidato.posto_servico_id = posto.id
        _aplica_remuneracao()
    db.flush()
    docs_novos = gerar_docs_do_posto_e_regime(db, candidato)

    # Cargo, salário e adicionais aparecem na ficha de cadastro. Se algo disso
    # mudou e a ficha já estava assinada, a via assinada divergiria dos dados
    # reais — então ela é invalidada (nunca deletada) e volta para assinatura.
    ficha_reaberta = False
    depois = (candidato.cargo_funcao, candidato.salario_base,
              list(candidato.adicionais or []))
    if depois != antes:
        from app.api.rh_ficha import invalidar_assinaturas_afetadas
        reabertos = invalidar_assinaturas_afetadas(
            db, candidato, "trabalho-banco", rh.email, ["cargo/salário/adicionais"])
        ficha_reaberta = bool(reabertos)

    registrar(db, "posto_definido", ator="rh", ator_detalhe=rh.email,
              candidato_id=candidato.id,
              detalhe={"posto": str(candidato.posto_servico_id),
                       "cargo": candidato.cargo_funcao,
                       "salario_base": candidato.salario_base,
                       "adicionais": len(candidato.adicionais or []),
                       "ficha_reaberta": ficha_reaberta,
                       "docs_gerados": [d.value for d in docs_novos]})
    db.commit()

    email_enviado = False
    if docs_novos:
        from app.api.assinaturas import NOMES_DOC
        link = emitir_link(db, candidato, base_url_publica(request))
        db.commit()
        docs_html = "".join(f"<li>{NOMES_DOC[d]}</li>" for d in docs_novos)
        email_enviado = enviar_email(
            candidato.email,
            "Green House — novos documentos aguardam a sua assinatura",
            f"Prezado(a) {candidato.nome_completo},\n\n"
            "O seu posto de serviço exige a assinatura dos documentos abaixo:\n"
            + "\n".join(f"  - {NOMES_DOC[d]}" for d in docs_novos)
            + f"\n\nAcesse: {link}\n\n"
            "Assine HOJE: sem essas assinaturas, sua alocação no posto não pode ser "
            "concluída.\n\nAtenciosamente,\nRH — Green House\n",
            html_moderno(
                "Novos documentos para assinar",
                [
                    f"Prezado(a) <strong>{candidato.nome_completo}</strong>,",
                    "O seu posto de serviço exige a assinatura dos documentos abaixo:"
                    f"<ul style='margin:8px 0 0 18px;color:#3a4152'>{docs_html}</ul>",
                    "<strong>Assine HOJE</strong> — sem essas assinaturas, sua alocação "
                    "no posto não pode ser concluída. O processo é o mesmo: um código "
                    "chega no seu e-mail e assina tudo de uma vez.",
                ],
                botao_texto="Assinar os documentos",
                botao_url=link,
            ),
        )
    return {
        "posto_servico_id": candidato.posto_servico_id,
        "cargo_funcao": candidato.cargo_funcao,
        "salario_base": candidato.salario_base,
        "adicionais": candidato.adicionais or [],
        "docs_gerados": [d.value for d in docs_novos],
        "email_enviado": email_enviado,
        "ficha_reaberta": ficha_reaberta,
    }
