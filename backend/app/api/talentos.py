"""Banco de Talentos: cadastro público de interessados + triagem e conversão
em candidato pelo RH. O formulário público substitui o Microsoft Forms de
pré-cadastro: multi-etapas, campos ricos e currículo opcional (PDF/foto/Word)."""

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Response, UploadFile
from itsdangerous import BadSignature, URLSafeTimedSerializer
from pydantic import BaseModel, EmailStr, field_validator
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.api.auth_rh import requer_rh
from app.core.config import base_url_publica, get_settings
from app.core.db import get_db
from app.models.candidato import Candidato
from app.models.talento import StatusTalento, Talento
from app.models.usuario_rh import UsuarioRH
from app.services import storage
from app.services.auditoria import registrar
from app.services.email import email_convite, enviar_email
from app.services.magic_link import emitir_link

router = APIRouter(tags=["talentos"])

UPLOAD_SALT = "talento-curriculo"
UPLOAD_TTL_S = 1800  # 30 min para anexar o currículo ao cadastro recém-criado
CURRICULO_MAX_BYTES = 10 * 1024 * 1024  # 10 MB
CURRICULO_EXTS = {"pdf", "jpg", "jpeg", "png", "heic", "webp", "doc", "docx"}
CURRICULO_CT = {
    "pdf": "application/pdf", "jpg": "image/jpeg", "jpeg": "image/jpeg",
    "png": "image/png", "heic": "image/heic", "webp": "image/webp",
    "doc": "application/msword",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}

# Cargos sugeridos no formulário público (do Microsoft Forms; "Outra" = texto livre).
CARGOS_SUGERIDOS = [
    "Auxiliar de Serviços Gerais / Faxineiro", "Servente de Limpeza",
    "Limpador de Vidros / Fachadas", "Zelador", "Agente de Portaria / Porteiro",
    "Recepcionista", "Telefonista / Operador de PABX", "Atendente", "Copeiro(a)",
    "Camareira", "Garçom / Garçonete", "Jardineiro / Auxiliar de Jardinagem",
    "Ajudante Geral de Manutenção e Reparos", "Bombeiro Civil / Brigadista",
    "Motorista", "Garagista", "Almoxarife", "Carregador / Montador",
    "Office Boy / Office Girl", "Auxiliar / Técnico de Saúde Bucal",
    "Operador / Técnico de Mídias Audiovisuais", "Educador Físico",
    "Encarregado(a) / Líder", "Supervisor(a)",
    "Auxiliar / Assistente Administrativo", "Recursos Humanos / Departamento Pessoal",
    "Financeiro / Faturamento", "Comercial", "Coordenação / Gerência",
    "Secretariado", "Comunicação / Design", "Jovem Aprendiz / Estágio", "Outra",
]

# Regiões do DF (do Microsoft Forms).
REGIOES_SUGERIDAS = [
    "Plano Piloto (Asa Sul, Asa Norte, Noroeste, Sudoeste, Eixo Monumental)",
    "Guará / SIA / SCIA", "Lago Sul / Park Way", "Taguatinga / Águas Claras",
    "Samambaia", "Gama / Riacho Fundo", "Outra região do DF", "Qualquer região",
]

TIPOS_CONTRATACAO = {"efetivo", "intermitente", "tanto_faz"}


def _upload_serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(get_settings().secret_key, salt=UPLOAD_SALT)


# ---------- Público (sem autenticação) ----------


class TalentoIn(BaseModel):
    nome: str
    email: EmailStr | None = None
    telefone: str | None = None
    cargos_interesse: list[str] = []
    regioes: list[str] = []
    cidade: str | None = None
    escolaridade: str | None = None
    resumo: str | None = None
    origem: str | None = None
    tipo_contratacao: str | None = None       # efetivo | intermitente | tanto_faz
    ja_trabalhou_funcao: bool | None = None
    recebe_seguro_desemprego: bool | None = None
    consentimento_lgpd: bool = False          # aceite obrigatório para enviar
    # Honeypot anti-spam: campo escondido no formulário; humano deixa vazio.
    # (Não pode começar com "_": o pydantic trata como atributo privado.)
    website: str | None = None

    # Inclui "email": o formulário público envia "" quando em branco, e o
    # EmailStr recusaria string vazia — aqui "" vira None antes da validação.
    @field_validator("nome", "email", "telefone", "cidade",
                     "escolaridade", "resumo", "origem", "tipo_contratacao", mode="before")
    @classmethod
    def _apara(cls, v):
        if isinstance(v, str):
            v = v.strip()
        return v or None


@router.get("/talentos/opcoes")
def opcoes_publicas() -> dict:
    return {"cargos": CARGOS_SUGERIDOS, "regioes": REGIOES_SUGERIDAS}


@router.post("/talentos", status_code=201)
def cadastrar(payload: TalentoIn, request: Request, db: Session = Depends(get_db)) -> dict:
    """Cadastro público no Banco de Talentos. Sem autenticação — protegido por
    honeypot e limite de tamanho; o RH tria depois. Devolve um `upload_token`
    (TTL curto) que autoriza anexar o currículo àquele cadastro."""
    dados = payload.model_dump()
    if dados.pop("website", None):
        # Bot preencheu o campo escondido: responde 201 sem gravar (não dá pistas).
        return {"ok": True}
    if not (dados.get("nome") or "").strip():
        raise HTTPException(status_code=422, detail="nome_obrigatorio")
    if not dados.pop("consentimento_lgpd", False):
        raise HTTPException(status_code=422, detail="consentimento_obrigatorio")
    if dados.get("resumo") and len(dados["resumo"]) > 4000:
        dados["resumo"] = dados["resumo"][:4000]

    cargos = [c.strip() for c in (dados.pop("cargos_interesse", None) or []) if c and c.strip()]
    regioes = [r.strip() for r in (dados.pop("regioes", None) or []) if r and r.strip()]
    tipo = dados.get("tipo_contratacao")
    if tipo and tipo not in TIPOS_CONTRATACAO:
        dados["tipo_contratacao"] = None

    talento = Talento(**dados)
    talento.cargos_interesse = cargos or None
    talento.regioes = regioes or None
    # cargo_interesse (string) = 1º cargo — mantém o `converter` legado funcionando
    talento.cargo_interesse = cargos[0] if cargos else None
    talento.consentimento_lgpd_em = datetime.now(timezone.utc)
    db.add(talento)
    db.flush()
    tid = str(talento.id)
    registrar(db, "talento_cadastrado", ator="publico",
              detalhe={"cargos": cargos, "cidade": talento.cidade})
    db.commit()
    upload_token = _upload_serializer().dumps({"tid": tid})
    return {"ok": True, "id": tid, "upload_token": upload_token}


@router.post("/talentos/{talento_id}/curriculo", status_code=201)
async def enviar_curriculo(talento_id: uuid.UUID, upload_token: str, arquivo: UploadFile,
                           db: Session = Depends(get_db)) -> dict:
    """Anexa o currículo (opcional) ao cadastro recém-criado. Autorizado pelo
    `upload_token` devolvido no cadastro (amarra o arquivo àquele talento sem
    exigir login e sem furar o anti-spam). Guarda o arquivo ORIGINAL no MinIO."""
    try:
        dados = _upload_serializer().loads(upload_token, max_age=UPLOAD_TTL_S)
    except BadSignature:
        raise HTTPException(status_code=422, detail="upload_token_invalido")
    if dados.get("tid") != str(talento_id):
        raise HTTPException(status_code=403, detail="token_nao_confere")
    t = db.get(Talento, talento_id)
    if t is None:
        raise HTTPException(status_code=404, detail="talento_nao_encontrado")
    try:
        conteudo = await arquivo.read()
    finally:
        await arquivo.close()  # descarta o spool em disco (arquivo com dados pessoais)
    if not conteudo:
        raise HTTPException(status_code=422, detail="arquivo_vazio")
    if len(conteudo) > CURRICULO_MAX_BYTES:
        raise HTTPException(status_code=422, detail="arquivo_grande_demais")
    ext = (arquivo.filename or "").rsplit(".", 1)[-1].lower()[:5]
    if ext not in CURRICULO_EXTS:
        raise HTTPException(status_code=422, detail="formato_nao_suportado")
    key = f"talentos/{t.id}/curriculo.{ext}"
    content_type = CURRICULO_CT.get(ext, arquivo.content_type or "application/octet-stream")
    storage.salvar(key, conteudo, content_type)
    t.curriculo_key = key
    t.curriculo_nome = (arquivo.filename or f"curriculo.{ext}")[:200]
    t.curriculo_tipo = content_type
    registrar(db, "talento_curriculo_enviado", ator="publico",
              detalhe={"talento": t.nome, "ext": ext})
    db.commit()
    return {"ok": True}


# ---------- RH (protegido) ----------


def _dump(t: Talento) -> dict:
    return {
        "id": t.id, "nome": t.nome, "email": t.email, "telefone": t.telefone,
        "cargo_interesse": t.cargo_interesse,
        "cargos_interesse": t.cargos_interesse or [],
        "regioes": t.regioes or [],
        "cidade": t.cidade, "escolaridade": t.escolaridade, "resumo": t.resumo,
        "origem": t.origem, "tipo_contratacao": t.tipo_contratacao,
        "ja_trabalhou_funcao": t.ja_trabalhou_funcao,
        "recebe_seguro_desemprego": t.recebe_seguro_desemprego,
        "consentimento_lgpd_em": t.consentimento_lgpd_em,
        "tem_curriculo": bool(t.curriculo_key), "curriculo_nome": t.curriculo_nome,
        "status": t.status.value, "candidato_id": t.candidato_id, "criado_em": t.criado_em,
    }


@router.get("/rh/talentos", dependencies=[Depends(requer_rh)])
def listar(status: str | None = None, busca: str | None = None,
           cargo: str | None = None, db: Session = Depends(get_db)) -> list[dict]:
    consulta = select(Talento).order_by(Talento.criado_em.desc())
    if status:
        consulta = consulta.where(Talento.status == status)
    if cargo:
        consulta = consulta.where(Talento.cargo_interesse.ilike(f"%{cargo}%"))
    if busca:
        termo = f"%{busca.lower()}%"
        consulta = consulta.where(or_(
            Talento.nome.ilike(termo), Talento.email.ilike(termo),
            Talento.cidade.ilike(termo), Talento.resumo.ilike(termo)))
    return [_dump(t) for t in db.scalars(consulta).all()]


@router.get("/rh/talentos/{talento_id}/curriculo", dependencies=[Depends(requer_rh)])
def baixar_curriculo(talento_id: uuid.UUID, db: Session = Depends(get_db),
                     rh: UsuarioRH = Depends(requer_rh)) -> Response:
    """Serve o currículo original do talento (PDF/imagem/Word) para o RH conferir.
    Resolve tudo do banco ANTES de tocar o storage (armadilha DetachedInstance)."""
    t = db.get(Talento, talento_id)
    if t is None or not t.curriculo_key:
        raise HTTPException(status_code=404, detail="curriculo_nao_encontrado")
    key, nome, ct = t.curriculo_key, t.curriculo_nome or "curriculo", t.curriculo_tipo
    registrar(db, "talento_curriculo_visto", ator="rh", ator_detalhe=rh.email,
              detalhe={"talento": t.nome})
    db.commit()
    try:
        conteudo = storage.ler(key)
    except Exception:
        raise HTTPException(status_code=404, detail="arquivo_nao_encontrado")
    return Response(content=conteudo, media_type=ct or "application/octet-stream",
                    headers={"Content-Disposition": f'inline; filename="{nome}"'})


class StatusIn(BaseModel):
    status: StatusTalento


@router.put("/rh/talentos/{talento_id}/status", dependencies=[Depends(requer_rh)])
def mudar_status(talento_id: uuid.UUID, payload: StatusIn, db: Session = Depends(get_db),
                 rh: UsuarioRH = Depends(requer_rh)) -> dict:
    t = db.get(Talento, talento_id)
    if t is None:
        raise HTTPException(status_code=404, detail="talento_nao_encontrado")
    if t.status == StatusTalento.convertido:
        raise HTTPException(status_code=409, detail="talento_ja_convertido")
    t.status = payload.status
    registrar(db, "talento_status_alterado", ator="rh", ator_detalhe=rh.email,
              detalhe={"talento": t.nome, "status": t.status.value})
    db.commit()
    return _dump(t)


@router.post("/rh/talentos/{talento_id}/converter", dependencies=[Depends(requer_rh)])
def converter(talento_id: uuid.UUID, request: Request, db: Session = Depends(get_db),
              rh: UsuarioRH = Depends(requer_rh)) -> dict:
    """Converte o talento em candidato: cria o cadastro migrando nome/contato,
    emite o link mágico da admissão e (se houver e-mail) envia o convite."""
    t = db.get(Talento, talento_id)
    if t is None:
        raise HTTPException(status_code=404, detail="talento_nao_encontrado")
    if t.status == StatusTalento.convertido and t.candidato_id:
        raise HTTPException(status_code=409, detail="talento_ja_convertido")

    candidato = Candidato(nome_completo=t.nome, email=t.email,
                          celular_whatsapp=t.telefone,
                          cargo_funcao=t.cargo_interesse)
    db.add(candidato)
    db.flush()
    link = emitir_link(db, candidato, base_url_publica(request))
    t.status = StatusTalento.convertido
    t.candidato_id = candidato.id
    registrar(db, "talento_convertido", ator="rh", ator_detalhe=rh.email,
              candidato_id=candidato.id, detalhe={"talento": t.nome})
    db.commit()

    enviado = False
    if candidato.email:
        assunto, texto, html = email_convite(candidato.nome_completo, link)
        enviado = enviar_email(candidato.email, assunto, texto, html)
    return {"candidato_id": candidato.id, "link_magico": link, "email_enviado": enviado}
