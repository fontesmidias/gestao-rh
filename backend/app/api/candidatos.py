import uuid

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, EmailStr
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.auth_rh import requer_rh
from app.core.config import base_url_publica
from app.core.db import get_db
from app.models.candidato import Candidato, StatusCandidato
from app.models.usuario_rh import UsuarioRH
from app.services.auditoria import registrar
from app.services.email_templates import enviar_modelo
from app.services.magic_link import emitir_link, resolver_token

router = APIRouter(tags=["candidatos"])


from pydantic import field_validator


class NovoCandidato(BaseModel):
    # Nome obrigatório; sem e-mail, o RH copia o link e manda pelo WhatsApp.
    # O posto é escolhido no convite (obrigatório no painel): com base nele e no
    # regime, os documentos específicos do kit já nascem certos.
    nome_completo: str
    email: EmailStr | None = None
    celular_whatsapp: str | None = None
    posto_id: uuid.UUID | None = None
    # Jornada obrigatória já no convite (feedback 2026-07-21): o Tirvu recusa
    # admissão sem jornada, e exigir aqui evita descobrir a pendência lá na
    # frente. O seletor do front oferece as jornadas do posto primeiro.
    jornada_id: uuid.UUID | None = None
    regime: str = "efetivo"
    cargo_funcao: str | None = None
    # Empresa e ponto no convite (feedback 2026-08-01): "é uma das coisas
    # fundamentais para o Tirvu". `registra_ponto` é obrigatório de verdade —
    # decisão do Bruno, ciente do risco de o RH marcar qualquer coisa para o
    # formulário deixar passar. A EMPRESA continua opcional aqui porque o grupo
    # opera com uma empregadora só (o export usa EMPRESA_TIRVU_ID fixo desde
    # 2026-07-24): o campo serve ao cadastro interno, e a tela já vem com ela
    # escolhida quando só existe uma — obrigar um clique numa lista de um item
    # é teatro, não conferência.
    empresa_id: uuid.UUID | None = None
    registra_ponto: bool | None = None
    # Testes marcados pelo RH ao gerar o link: o candidato responde ANTES de
    # seguir para o cadastro; o resultado é restrito ao RH.
    fazer_disc: bool = False
    fazer_situacional: bool = False

    @field_validator("nome_completo", "email", "celular_whatsapp", "cargo_funcao",
                     mode="before")
    @classmethod
    def _apara_espacos(cls, v):
        # E-mails colados do WhatsApp costumam vir com espaço no fim;
        # campo deixado em branco no formulário chega como "".
        if isinstance(v, str):
            v = v.strip()
        return v or None

    @field_validator("nome_completo")
    @classmethod
    def _padroniza_nome(cls, v):
        """Também no CONVITE, não só no que o candidato digita.

        O nome do convite é o que aparece no e-mail que a pessoa recebe — e o
        RH costuma colar de uma planilha, onde tudo vem em CAIXA ALTA.
        """
        from app.services.nomes import capitalizar_nome
        return capitalizar_nome(v) if v else v


class CandidatoOut(BaseModel):
    id: uuid.UUID
    nome_completo: str
    email: EmailStr | None = None
    celular_whatsapp: str | None = None
    status: StatusCandidato

    model_config = {"from_attributes": True}


class ConviteOut(BaseModel):
    candidato: CandidatoOut
    link_magico: str
    email_enviado: bool


# --- RH (protegido) ---


@router.post("/rh/candidatos", response_model=ConviteOut, status_code=201)
def criar_candidato(
    payload: NovoCandidato,
    request: Request,
    db: Session = Depends(get_db),
    _rh: UsuarioRH = Depends(requer_rh),
) -> ConviteOut:
    """Cadastra o candidato aprovado, emite o link mágico e envia o convite por e-mail.
    Com o posto e o regime escolhidos aqui, os documentos específicos do kit
    (INFRAERO / Informativo do Intermitente) já nascem exigidos."""
    from app.api.postos import gerar_docs_do_posto_e_regime
    from app.models.candidato import Jornada, PostoServico

    dados = payload.model_dump()
    posto_id = dados.pop("posto_id", None)
    jornada_id = dados.pop("jornada_id", None)
    regime = (dados.pop("regime", None) or "efetivo").strip().lower()
    cargo = dados.pop("cargo_funcao", None)
    empresa_id = dados.pop("empresa_id", None)
    registra_ponto = dados.pop("registra_ponto", None)
    fazer_disc = bool(dados.pop("fazer_disc", False))
    fazer_situacional = bool(dados.pop("fazer_situacional", False))
    if posto_id is not None and db.get(PostoServico, posto_id) is None:
        raise HTTPException(status_code=404, detail="posto_nao_encontrado")
    if empresa_id is not None:
        from app.models.candidato import Empresa
        if db.get(Empresa, empresa_id) is None:
            raise HTTPException(status_code=404, detail="empresa_nao_encontrada")
    # Jornada é obrigatória no convite (feedback 2026-07-21) e precisa existir.
    if jornada_id is None:
        raise HTTPException(status_code=422, detail="jornada_obrigatoria")
    # Cargo obrigatório no convite (feedback 2026-07-23): o cargo casa por TEXTO
    # com modelos/provas/arquivo, então precisa ser definido ao gerar o link.
    if not cargo:
        raise HTTPException(status_code=422, detail="cargo_obrigatorio")
    # Registra ponto obrigatório no convite (feedback 2026-08-01). Era pendência
    # só na hora do export, e o Tirvu ACEITA a célula vazia calado — o
    # colaborador nascia lá sem a marcação. Exigir aqui não briga com a regra da
    # v1.82 (não travar a edição dos importados, que nasceram sem o campo): no
    # convite não existe importado, a admissão começa agora.
    #
    # Vem DEPOIS de jornada e cargo de propósito: quem esquece o formulário
    # inteiro precisa ouvir primeiro sobre os campos que já eram exigidos, na
    # ordem em que aparecem na tela.
    if registra_ponto is None:
        raise HTTPException(status_code=422, detail="registra_ponto_obrigatorio")
    if db.get(Jornada, jornada_id) is None:
        raise HTTPException(status_code=404, detail="jornada_nao_encontrada")
    candidato = Candidato(**dados, posto_servico_id=posto_id, jornada_id=jornada_id,
                          regime=regime if regime in ("efetivo", "intermitente") else "efetivo",
                          cargo_funcao=cargo, empresa_id=empresa_id,
                          registra_ponto=registra_ponto)
    db.add(candidato)
    db.flush()
    docs_novos = gerar_docs_do_posto_e_regime(db, candidato)
    # testes marcados no convite (respondidos antes do cadastro)
    from app.models.teste import TesteCandidato, TipoTeste
    if fazer_disc:
        db.add(TesteCandidato(candidato_id=candidato.id, tipo=TipoTeste.disc))
    if fazer_situacional:
        db.add(TesteCandidato(candidato_id=candidato.id, tipo=TipoTeste.situacional))
    link = emitir_link(db, candidato, base_url_publica(request))
    registrar(db, "convite_criado", ator="rh", ator_detalhe=_rh.email, candidato_id=candidato.id,
              detalhe={"posto": str(posto_id), "regime": candidato.regime,
                       "docs_kit": [d.value for d in docs_novos]})
    db.commit()
    enviado = False
    if candidato.email:
        enviado = enviar_modelo(db, "convite_admissao", candidato.email, {
            "primeiro_nome": (candidato.nome_completo or "").split()[0].title(),
            "nome": candidato.nome_completo, "link": link,
        })
    return ConviteOut(
        candidato=CandidatoOut.model_validate(candidato), link_magico=link, email_enviado=enviado
    )


@router.post("/rh/candidatos/{candidato_id}/reenviar-link", response_model=ConviteOut)
def reenviar_link(
    candidato_id: uuid.UUID,
    request: Request,
    enviar_email_convite: bool = True,
    db: Session = Depends(get_db),
    _rh: UsuarioRH = Depends(requer_rh),
) -> ConviteOut:
    """Emite um novo link mágico (o anterior continua válido até expirar).
    Com enviar_email_convite=false, só gera e devolve o link — para o RH copiar
    e mandar por WhatsApp, sem duplicar e-mail para o candidato."""
    candidato = db.get(Candidato, candidato_id)
    if candidato is None:
        raise HTTPException(status_code=404, detail="candidato_nao_encontrado")
    link = emitir_link(db, candidato, base_url_publica(request))
    registrar(db, "link_reenviado" if enviar_email_convite else "link_copiado",
              ator="rh", ator_detalhe=_rh.email, candidato_id=candidato.id)
    db.commit()
    enviado = False
    if enviar_email_convite and candidato.email:
        enviado = enviar_modelo(db, "convite_admissao", candidato.email, {
            "primeiro_nome": (candidato.nome_completo or "").split()[0].title(),
            "nome": candidato.nome_completo, "link": link,
        })
    return ConviteOut(
        candidato=CandidatoOut.model_validate(candidato), link_magico=link, email_enviado=enviado
    )


# Sessão assistida vale poucas horas: é para usar AGORA, com a pessoa na sala.
# Um link de preenchimento-por-terceiro válido por três dias (como o convite
# comum) seria superfície de risco sem contrapartida nenhuma.
HORAS_SESSAO_ASSISTIDA = 8


@router.post("/rh/candidatos/{candidato_id}/sessao-assistida", response_model=ConviteOut)
def abrir_sessao_assistida(
    candidato_id: uuid.UUID,
    request: Request,
    db: Session = Depends(get_db),
    rh: UsuarioRH = Depends(requer_rh),
) -> ConviteOut:
    """Abre o wizard para o RH preencher COM A PESSOA PRESENTE.

    Feedback 2026-08-02: *"para os casos em que a pessoa tiver baixo grau de
    instrução, ou dificuldades [...] o RH fazer tudo, desde a inserção de dados,
    coleta de documentos e tudo mais e ver alguma forma que a pessoa possa
    assinar o documento. Pois hoje o RH gera o link mas fica inserindo tudo na
    mão como se fosse uma correção e não como se o candidato estivesse ali"*.

    O que muda em relação a simplesmente abrir o link de sempre — que é o que
    já dá para fazer hoje — é o REGISTRO. O link nasce marcado, tudo que é
    assinado por ele guarda quem operou, e o manifesto passa a descrever o ato
    como ele foi. Sem isso, uma admissão assistida e uma feita pela pessoa em
    casa são indistinguíveis no documento, e o manifesto afirma algo que não
    aconteceu exatamente assim.

    **O código de assinatura continua indo ao e-mail DELA** (decisão do Bruno):
    é o que mantém a prova de identidade intacta. Quem não tem e-mail precisa
    cadastrar um antes — por isso o 422 abaixo, que é orientação, não obstáculo.
    """
    candidato = db.get(Candidato, candidato_id)
    if candidato is None:
        raise HTTPException(status_code=404, detail="candidato_nao_encontrado")
    # Sem e-mail não há para onde mandar o código, e a assinatura ficaria sem
    # o fator que prova a identidade. Barrar AQUI, com a pessoa na frente do
    # RH, é o melhor momento possível para resolver: basta perguntar o e-mail.
    if not (candidato.email or "").strip():
        raise HTTPException(status_code=422, detail="sem_email")
    link = emitir_link(db, candidato, base_url_publica(request),
                       assistido_por=rh.email, horas=HORAS_SESSAO_ASSISTIDA)
    registrar(db, "sessao_assistida_aberta", ator="rh", ator_detalhe=rh.email,
              candidato_id=candidato.id,
              detalhe={"validade_horas": HORAS_SESSAO_ASSISTIDA})
    db.commit()
    # NÃO manda e-mail: o link é para o RH abrir na própria tela, agora. Mandar
    # um convite ao candidato aqui só confundiria quem está sentado ao lado.
    return ConviteOut(
        candidato=CandidatoOut.model_validate(candidato), link_magico=link,
        email_enviado=False,
    )


# ---------------------------------------------------------------------------
# Testes JÁ RESPONDIDOS aproveitados para o candidato (v2.21)
# ---------------------------------------------------------------------------


@router.get("/rh/testes-vinculaveis")
def testes_vinculaveis(busca: str | None = None, db: Session = Depends(get_db),
                       _rh: UsuarioRH = Depends(requer_rh)) -> list[dict]:
    """Testes/provas concluídos e ainda não aproveitados por ninguém.

    Cada item vem com nome, data, qual teste e por qual link — contexto para o
    RH RECONHECER a pessoa. O link avulso de testagem é anônimo, então escolher
    só pelo nome seria adivinhação, e teste decide contratação.
    """
    from app.services.testes_vinculaveis import disponiveis
    return disponiveis(db, busca)


class VincularTesteIn(BaseModel):
    origem: str                 # testagem | prova
    referencia_id: uuid.UUID    # participante_id ou aplicacao_id


@router.post("/rh/candidatos/{candidato_id}/testes-vinculados", status_code=201)
def vincular_teste(candidato_id: uuid.UUID, payload: VincularTesteIn,
                   db: Session = Depends(get_db),
                   rh: UsuarioRH = Depends(requer_rh)) -> dict:
    """Aproveita para este candidato um teste que a pessoa já respondeu."""
    from app.services.testes_vinculaveis import resultado_do_vinculo, vincular
    candidato = db.get(Candidato, candidato_id)
    if candidato is None:
        raise HTTPException(status_code=404, detail="candidato_nao_encontrado")
    if payload.origem not in ("testagem", "prova"):
        raise HTTPException(status_code=422, detail="origem_invalida")
    try:
        v = vincular(db, candidato.id, payload.origem, payload.referencia_id,
                     autor=rh.email, automatico=False)
    except Exception as exc:
        raise HTTPException(status_code=422,
                            detail=f"nao_foi_possivel_vincular: {exc}") from exc
    registrar(db, "teste_vinculado", ator="rh", ator_detalhe=rh.email,
              candidato_id=candidato.id,
              detalhe={"origem": payload.origem,
                       "referencia": str(payload.referencia_id)})
    db.commit()
    db.refresh(v)
    return resultado_do_vinculo(db, v)


@router.get("/rh/candidatos/{candidato_id}/testes-vinculados")
def listar_testes_vinculados(candidato_id: uuid.UUID,
                             db: Session = Depends(get_db),
                             _rh: UsuarioRH = Depends(requer_rh)) -> list[dict]:
    """Resultados aproveitados deste candidato — restrito ao RH.

    NÃO aparece para o candidato (não entra no wizard) nem no dossiê, que
    circula: resultado de teste é dado sensível de seleção.
    """
    from app.models.teste_vinculado import TesteVinculado
    from app.services.testes_vinculaveis import resultado_do_vinculo
    vinculos = db.scalars(
        select(TesteVinculado)
        .where(TesteVinculado.candidato_id == candidato_id)
        .order_by(TesteVinculado.vinculado_em.desc())).all()
    return [resultado_do_vinculo(db, v) for v in vinculos]


@router.delete("/rh/candidatos/{candidato_id}/testes-vinculados/{vinculo_id}",
               status_code=204)
def desvincular_teste(candidato_id: uuid.UUID, vinculo_id: uuid.UUID,
                      db: Session = Depends(get_db),
                      rh: UsuarioRH = Depends(requer_rh)) -> None:
    """Desfaz o vínculo — o RH pode ter reconhecido a pessoa errada."""
    from app.models.teste_vinculado import TesteVinculado
    v = db.get(TesteVinculado, vinculo_id)
    if v is None or v.candidato_id != candidato_id:
        raise HTTPException(status_code=404, detail="vinculo_nao_encontrado")
    registrar(db, "teste_desvinculado", ator="rh", ator_detalhe=rh.email,
              candidato_id=candidato_id, detalhe={"origem": v.origem.value})
    db.delete(v)
    db.commit()


class ContatoIn(BaseModel):
    email: EmailStr | None = None
    celular_whatsapp: str | None = None

    @field_validator("email", "celular_whatsapp", mode="before")
    @classmethod
    def _apara(cls, v):
        if isinstance(v, str):
            v = v.strip()
        return v or None


@router.put("/rh/candidatos/{candidato_id}/contato", response_model=CandidatoOut)
def editar_contato(
    candidato_id: uuid.UUID,
    payload: ContatoIn,
    db: Session = Depends(get_db),
    _rh: UsuarioRH = Depends(requer_rh),
) -> CandidatoOut:
    """O RH corrige e-mail/celular do candidato (caso real: cadastro sem
    e-mail → fichas e código de assinatura não chegavam). O antes e o depois
    ficam na auditoria — evidência para qualquer contestação de assinatura."""
    candidato = db.get(Candidato, candidato_id)
    if candidato is None:
        raise HTTPException(status_code=404, detail="candidato_nao_encontrado")
    antes = {"email": candidato.email, "celular_whatsapp": candidato.celular_whatsapp}
    dados = payload.model_dump(exclude_unset=True)
    for campo, valor in dados.items():
        setattr(candidato, campo, valor)
    registrar(db, "contato_alterado", ator="rh", ator_detalhe=_rh.email,
              candidato_id=candidato.id,
              detalhe={"antes": antes,
                       "depois": {"email": candidato.email,
                                  "celular_whatsapp": candidato.celular_whatsapp}})
    db.commit()
    return CandidatoOut.model_validate(candidato)


# --- Candidato (acesso via token do link mágico) ---


@router.get("/c/{token}", response_model=CandidatoOut)
def sessao_candidato(token: str, db: Session = Depends(get_db)) -> CandidatoOut:
    candidato = resolver_token(db, token)
    if candidato is None:
        raise HTTPException(status_code=404, detail="link_invalido_ou_expirado")
    db.commit()
    return CandidatoOut.model_validate(candidato)
