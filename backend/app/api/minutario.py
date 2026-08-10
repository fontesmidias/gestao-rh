"""Minutário de mensagens (v1.98, feedback de campo 2026-07-27): CRUD de
modelos + geração de texto por IA a partir de campos estruturados da vaga.

A vaga é o que vai para a IA — NUNCA dado do candidato. A substituição de
marcadores como {{nome}} acontece DEPOIS, no servidor, sobre o texto já
gerado (services/fichas.py::aplicar_variaveis já existe e faz exatamente
isso para outros templates do sistema — reusado aqui).

Envio: copiar para a área de transferência + link wa.me (decisão do Bruno,
2026-07-27) — sem integração com a API oficial do WhatsApp. O link é
montado no FRONT (não precisa de rota própria: `https://wa.me/<numero>?
text=<encodeURIComponent(texto)>`)."""
import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.auth_rh import exige, requer_rh
from app.core.db import get_db
from app.models.crm import Tag
from app.models.minutario import MeioEnvio, ModeloMensagem, ModeloMensagemTag
from app.models.usuario_rh import UsuarioRH
from app.services.auditoria import registrar
from app.services.ia_texto import IndisponivelError, gerar_texto

router = APIRouter(tags=["minutario"], dependencies=[Depends(requer_rh)])


def _dump_modelo(m: ModeloMensagem, tags: list[Tag] | None = None) -> dict:
    return {
        "id": m.id, "titulo": m.titulo, "meio": m.meio.value, "corpo_base": m.corpo_base,
        "ativo": m.ativo, "atualizado_em": m.atualizado_em,
        "tags": [{"id": t.id, "nome": t.nome, "cor": t.cor} for t in (tags or [])],
    }


def _tags_do_modelo(db: Session, modelo_id) -> list[Tag]:
    return list(db.scalars(
        select(Tag).join(ModeloMensagemTag, ModeloMensagemTag.tag_id == Tag.id)
        .where(ModeloMensagemTag.modelo_id == modelo_id)))


class ModeloMensagemIn(BaseModel):
    titulo: str
    meio: MeioEnvio = MeioEnvio.whatsapp
    corpo_base: str = ""
    ativo: bool | None = None
    tag_ids: list[uuid.UUID] = []


@router.get("/rh/minutario/modelos")
def listar_modelos(incluir_inativos: bool = False, db: Session = Depends(get_db),
    _rh: UsuarioRH = Depends(exige("documentos:minutario"))) -> list[dict]:
    q = select(ModeloMensagem).order_by(ModeloMensagem.titulo)
    if not incluir_inativos:
        q = q.where(ModeloMensagem.ativo.is_(True))
    modelos = db.scalars(q).all()
    return [_dump_modelo(m, _tags_do_modelo(db, m.id)) for m in modelos]


@router.post("/rh/minutario/modelos", status_code=201)
def criar_modelo(payload: ModeloMensagemIn, db: Session = Depends(get_db),
                 rh: UsuarioRH = Depends(exige("documentos:minutario"))) -> dict:
    titulo = payload.titulo.strip()
    if not titulo:
        raise HTTPException(status_code=422, detail="titulo_obrigatorio")
    m = ModeloMensagem(titulo=titulo[:160], meio=payload.meio,
                       corpo_base=payload.corpo_base.strip(),
                       ativo=True if payload.ativo is None else payload.ativo)
    db.add(m)
    db.flush()
    for tid in payload.tag_ids:
        db.add(ModeloMensagemTag(modelo_id=m.id, tag_id=tid))
    registrar(db, "minutario_modelo_criado", ator="rh", ator_detalhe=rh.email,
              detalhe={"modelo": str(m.id), "titulo": titulo})
    db.commit()
    return _dump_modelo(m, _tags_do_modelo(db, m.id))


@router.patch("/rh/minutario/modelos/{modelo_id}")
def editar_modelo(modelo_id: uuid.UUID, payload: ModeloMensagemIn,
                  db: Session = Depends(get_db), rh: UsuarioRH = Depends(exige("documentos:minutario"))) -> dict:
    m = db.get(ModeloMensagem, modelo_id)
    if m is None:
        raise HTTPException(status_code=404, detail="modelo_nao_encontrado")
    titulo = payload.titulo.strip()
    if not titulo:
        raise HTTPException(status_code=422, detail="titulo_obrigatorio")
    m.titulo = titulo[:160]
    m.meio = payload.meio
    m.corpo_base = payload.corpo_base.strip()
    if payload.ativo is not None:
        m.ativo = payload.ativo
    for vinculo in db.scalars(select(ModeloMensagemTag).where(ModeloMensagemTag.modelo_id == m.id)):
        db.delete(vinculo)
    db.flush()
    for tid in payload.tag_ids:
        db.add(ModeloMensagemTag(modelo_id=m.id, tag_id=tid))
    registrar(db, "minutario_modelo_editado", ator="rh", ator_detalhe=rh.email,
              detalhe={"modelo": str(m.id)})
    db.commit()
    return _dump_modelo(m, _tags_do_modelo(db, m.id))


@router.delete("/rh/minutario/modelos/{modelo_id}", status_code=204)
def excluir_modelo(modelo_id: uuid.UUID, db: Session = Depends(get_db),
                   rh: UsuarioRH = Depends(exige("documentos:minutario"))) -> None:
    m = db.get(ModeloMensagem, modelo_id)
    if m is None:
        raise HTTPException(status_code=404, detail="modelo_nao_encontrado")
    db.delete(m)
    registrar(db, "minutario_modelo_excluido", ator="rh", ator_detalhe=rh.email,
              detalhe={"modelo": str(modelo_id)})
    db.commit()


# ---------- Geração assistida por IA ----------

# Cada campo abaixo é um "botão" do pedido do Bruno — o front monta um
# formulário com esses campos; nenhum é obrigatório (a IA lida com o que
# vier preenchido). NENHUM campo aqui é dado de candidato — é sobre a VAGA.
class ComporMensagemIn(BaseModel):
    tom: str | None = None                    # ex.: "cordial e direto", "descontraído"
    cargo: str | None = None
    regime: str | None = None                 # efetivo | intermitente
    salario: str | None = None
    local: str | None = None
    escala: str | None = None
    jornada: str | None = None
    horario: str | None = None
    requisitos_obrigatorios: str | None = None
    requisitos_desejaveis: str | None = None
    instrucoes_extra: str | None = None
    prazo: str | None = None
    modelo_base_id: uuid.UUID | None = None   # se veio de um modelo salvo, o corpo_base entra como referência


_PROMPT_SISTEMA = (
    "Você escreve mensagens de recrutamento para o RH da Green House (Brasília/DF) "
    "enviar por WhatsApp ou e-mail a candidatos e ao Banco de Talentos. "
    "Escreva em português do Brasil, SEM NENHUM ERRO DE ORTOGRAFIA OU GRAMÁTICA. "
    "Use o tom pedido; se não for informado, use um tom cordial e profissional. "
    "Inclua apenas as informações fornecidas — não invente cargo, salário, "
    "endereço, horário ou qualquer outro dado que não tenha sido passado. "
    "Se um campo não foi informado, simplesmente não o mencione (não escreva "
    "'a definir' nem placeholders). Não assine a mensagem. Não use emojis em "
    "excesso — no máximo 1 ou 2, se fizer sentido. Devolva SOMENTE o texto da "
    "mensagem final, pronto para copiar e colar, sem comentários antes ou depois."
)


def _prompt_usuario(dados: ComporMensagemIn, corpo_referencia: str | None) -> str:
    campos = {
        "Cargo/função": dados.cargo, "Regime": dados.regime, "Salário": dados.salario,
        "Local de trabalho": dados.local, "Escala": dados.escala, "Jornada": dados.jornada,
        "Horário de trabalho": dados.horario,
        "Requisitos obrigatórios": dados.requisitos_obrigatorios,
        "Requisitos desejáveis": dados.requisitos_desejaveis,
        "Instruções adicionais": dados.instrucoes_extra, "Prazo": dados.prazo,
    }
    linhas = [f"- {rotulo}: {valor}" for rotulo, valor in campos.items() if (valor or "").strip()]
    # O tom é só um modificador de ESTILO — nunca substitui o conteúdo. O
    # fallback genérico dispara quando falta CONTEÚDO (linhas ou modelo de
    # referência), não quando falta o tom (bug pego pelo teste: "só tom
    # preenchido" gerava prompt sem instrução nenhuma do que escrever).
    tem_conteudo = bool(linhas or corpo_referencia)
    partes = []
    if dados.tom:
        partes.append(f"Tom desejado: {dados.tom}.")
    if linhas:
        partes.append("Informações da vaga:\n" + "\n".join(linhas))
    if corpo_referencia:
        partes.append(
            "Use o texto abaixo como modelo de ESTRUTURA (não copie literalmente "
            "se as informações acima forem diferentes):\n" + corpo_referencia)
    if not tem_conteudo:
        partes.append("Escreva uma mensagem genérica de divulgação de vaga, convidando "
                       "a pessoa a se cadastrar no Banco de Talentos da Green House.")
    return "\n\n".join(partes)


@router.post("/rh/minutario/compor")
def compor_mensagem(payload: ComporMensagemIn, db: Session = Depends(get_db),
                    rh: UsuarioRH = Depends(exige("documentos:minutario"))) -> dict:
    """Gera o texto a partir dos campos da vaga (+ modelo de referência,
    se indicado). O texto SEMPRE volta editável no front antes de qualquer
    envio — a IA propõe, o RH aprova."""
    corpo_referencia = None
    if payload.modelo_base_id:
        m = db.get(ModeloMensagem, payload.modelo_base_id)
        if m is not None:
            corpo_referencia = m.corpo_base

    try:
        texto = gerar_texto(_PROMPT_SISTEMA, _prompt_usuario(payload, corpo_referencia))
    except IndisponivelError as exc:
        detail = "chave_nao_configurada" if str(exc) == "chave_nao_configurada" else "ia_indisponivel"
        raise HTTPException(status_code=422, detail=detail) from exc

    registrar(db, "minutario_mensagem_composta", ator="rh", ator_detalhe=rh.email,
              detalhe={"modelo_base": str(payload.modelo_base_id) if payload.modelo_base_id else None})
    db.commit()
    return {"texto": texto}
