"""Banco de Talentos: cadastro público de interessados + triagem e conversão
em candidato pelo RH. O formulário público substitui o Microsoft Forms de
pré-cadastro: multi-etapas, campos ricos e currículo opcional (PDF/foto/Word)."""

import logging
import uuid
from pathlib import Path
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Response, UploadFile
from itsdangerous import BadSignature, URLSafeTimedSerializer
from pydantic import BaseModel, EmailStr, field_validator
from sqlalchemy import String, cast, or_, select
from sqlalchemy.orm import Session

from app.api.auth_rh import requer_rh
from app.core.config import base_url_publica, get_settings
from app.core.db import get_db
from app.models.candidato import Candidato
from app.models.talento import StatusTalento, Talento
from app.models.usuario_rh import UsuarioRH
from app.services import crm, storage
from app.services.auditoria import registrar
from app.services.email_templates import enviar_modelo
from app.services.magic_link import emitir_link

router = APIRouter(tags=["talentos"])
log = logging.getLogger(__name__)

UPLOAD_SALT = "talento-curriculo"
UPLOAD_TTL_S = 1800  # 30 min para anexar o currículo ao cadastro recém-criado
CURRICULO_MAX_BYTES = 10 * 1024 * 1024  # 10 MB
CURRICULO_EXTS = {"pdf", "jpg", "jpeg", "png", "heic", "webp", "doc", "docx"}
# Word não renderiza em navegador nenhum: estes são convertidos para PDF na
# hora de SERVIR, para o RH ler na tela (v2.33). O arquivo GUARDADO continua
# sendo o original que a pessoa enviou — a conversão é só de exibição.
_EXTS_WORD = {".doc", ".docx", ".odt", ".rtf"}
_CT_WORD = {"application/msword",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "application/vnd.oasis.opendocument.text", "application/rtf"}


def _ehWord(nome: str | None, ct: str | None) -> bool:
    """Casa por extensão OU content-type: o upload público às vezes chega com
    `application/octet-stream` (depende do celular), e aí só o nome denuncia."""
    if (ct or "") in _CT_WORD:
        return True
    return Path((nome or "").lower()).suffix in _EXTS_WORD

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


def talento_do_upload_token(token: str | None) -> uuid.UUID | None:
    """Talento provado pelo `upload_token`, ou None.

    Existe para que a telemetria pública não aceite um `talento_id` cru vindo
    do navegador (v2.36): a rota de coleta é aberta, e um id sem prova deixaria
    qualquer um pendurar eventos na jornada de outra pessoa — dado de produto
    que o RH lê como se fosse o comportamento dela. O token já é emitido no
    cadastro, tem assinatura e TTL curto; reusá-lo é mais barato e mais seguro
    do que inventar outra credencial.
    """
    if not token:
        return None
    try:
        dados = _upload_serializer().loads(token, max_age=UPLOAD_TTL_S)
        return uuid.UUID(str(dados.get("tid")))
    except (BadSignature, ValueError, TypeError):
        return None


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
    nome_cad, cargos_cad, email_cad = talento.nome, cargos, talento.email
    db.commit()
    # aviso interno configurável (v1.82) — desligado por padrão seria pior:
    # cadastro de talento que ninguém vê é currículo perdido
    from app.services.notificacoes import avisar_modelo
    avisar_modelo(
        db, "talento_cadastrado", "aviso_talento_cadastrado",
        {"nome": nome_cad,
         "cargos": ", ".join(cargos_cad) or "(não informado)"})
    # Agradecimento para a PESSOA (feedback 2026-07-28): a tela de obrigado só
    # existe enquanto a aba está aberta; sem e-mail, quem se cadastrou fica sem
    # nenhum comprovante de que o cadastro entrou. Texto editável pelo RH.
    if email_cad:
        from app.services.email_templates import enviar_modelo
        enviar_modelo(db, "talento_agradecimento", email_cad, {
            "primeiro_nome": (nome_cad or "").split()[0].title() if nome_cad else "",
            "nome": nome_cad or "",
            "cargos": ", ".join(cargos_cad) if cargos_cad else "",
        })
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

    # Extrai o texto do currículo AGORA, em background (v2.00): o currículo
    # não muda depois do upload, então relê-lo a cada ranqueamento era
    # desperdício — e com OCR garantia de estourar o timeout do nginx.
    # Falha ao enfileirar não pode derrubar o upload do candidato: o backfill
    # pega depois.
    try:
        from app.services import fila
        from app.workers.match import indexar_curriculo
        fila.enfileirar(indexar_curriculo, str(t.id))
    except Exception:
        log.warning("Não foi possível enfileirar a indexação do currículo do "
                    "talento %s — o backfill cobre depois.", t.id)

    return {"ok": True}


# ---------- RH (protegido) ----------


def _dump(t: Talento, teste: dict | None = None, tags: list | None = None,
          notas: dict | None = None) -> dict:
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
        "teste_status": (teste or {}).get("status"),  # None | enviado | em_andamento | concluido
        "tags": tags or [],   # tags do CRM (do talento E do candidato vinculado)
        # resumo das anotações para a linha do dash: quantas e a última
        "anotacoes": (notas or {}).get("total", 0),
        "ultima_anotacao": (notas or {}).get("ultima_texto"),
        "ultima_anotacao_autor": (notas or {}).get("ultima_autor"),
        "ultima_anotacao_quando": (notas or {}).get("ultima_quando"),
        "status": t.status.value, "candidato_id": t.candidato_id, "criado_em": t.criado_em,
    }


@router.get("/rh/talentos", dependencies=[Depends(requer_rh)])
def listar(status: str | None = None, busca: str | None = None,
           cargo: str | None = None, db: Session = Depends(get_db)) -> list[dict]:
    consulta = select(Talento).order_by(Talento.criado_em.desc())
    if status:
        consulta = consulta.where(Talento.status == status)
    if cargo:
        # cargo bate no string legado OU na lista JSON (texto do JSON)
        consulta = consulta.where(or_(
            Talento.cargo_interesse.ilike(f"%{cargo}%"),
            cast(Talento.cargos_interesse, String).ilike(f"%{cargo}%")))
    if busca:
        termo = f"%{busca.lower()}%"
        consulta = consulta.where(or_(
            Talento.nome.ilike(termo), Talento.email.ilike(termo),
            Talento.cidade.ilike(termo), Talento.resumo.ilike(termo)))
    talentos = db.scalars(consulta).all()
    # resumo de teste por talento, EM LOTE (o comentário aqui dizia "1 consulta,
    # sem N+1" mas o código chamava uma por pessoa — v2.15)
    testes = _resumo_teste_por_talento(db, list(talentos))
    # tags do CRM em lote (talento + candidato vinculado), sem N+1
    tags = crm.tags_por_talento(db, list(talentos))
    # resumo das anotações na própria linha (v2.15): o RH via "🗒️ Anotações" em
    # todo mundo e só descobria que não havia nada depois de abrir o modal.
    notas = crm.resumo_anotacoes_por_talento(db, list(talentos))
    return [_dump(t, testes.get(t.id), tags.get(t.id), notas.get(t.id))
            for t in talentos]


def marcar_em_analise(db: Session, talento: Talento) -> bool:
    """`novo` → `em_analise` quando o RH pratica um ATO DE ATENÇÃO sobre a
    pessoa: abrir o currículo ou as anotações dela (v2.00).

    Antes NADA movia esse status — só o clique manual e a conversão — então
    os 131 talentos ficavam todos "Novo" para sempre e o campo não
    discriminava nada (feedback do Bruno, 2026-07-28).

    NÃO é chamado pelo ranqueamento em massa de propósito: marcar 131 pessoas
    de uma vez recriaria o mesmo problema com outro rótulo. O status é sobre
    o RH ter olhado, não sobre a máquina ter processado."""
    if talento.status != StatusTalento.novo:
        return False
    talento.status = StatusTalento.em_analise
    return True


@router.get("/rh/talentos/{talento_id}/curriculo", dependencies=[Depends(requer_rh)])
def baixar_curriculo(talento_id: uuid.UUID, db: Session = Depends(get_db),
                     rh: UsuarioRH = Depends(requer_rh)) -> Response:
    """Serve o currículo original do talento (PDF/imagem/Word) para o RH conferir.
    Resolve tudo do banco ANTES de tocar o storage (armadilha DetachedInstance)."""
    t = db.get(Talento, talento_id)
    if t is None or not t.curriculo_key:
        raise HTTPException(status_code=404, detail="curriculo_nao_encontrado")
    key, nome, ct = t.curriculo_key, t.curriculo_nome or "curriculo", t.curriculo_tipo
    marcar_em_analise(db, t)   # abrir o currículo é ato de atenção
    db.commit()
    try:
        conteudo = storage.ler(key)
    except Exception as exc:
        # O log dizia só o nome do talento, então "não abriu" e "não existe no
        # storage" eram indistinguíveis na auditoria (feedback 2026-07-28).
        registrar(db, "talento_curriculo_falhou", ator="rh", ator_detalhe=rh.email,
                  detalhe={"talento": t.nome, "arquivo": nome, "tipo": ct,
                           "erro": type(exc).__name__})
        db.commit()
        raise HTTPException(status_code=404, detail="arquivo_nao_encontrado")

    # Word CONVERTE para PDF em vez de mandar baixar (v2.33, decisão do Bruno
    # em 2026-07-30 — perguntado, ele escolheu "converter"). O LibreOffice já
    # roda neste container para a normalização de documentos; aqui ele serve
    # para o RH LER o currículo na tela, que é o pedido. Se a conversão falhar,
    # cai no comportamento antigo (baixar) — nunca deixa o RH sem o arquivo.
    if _ehWord(nome, ct):
        try:
            from app.services.normalizacao import _word_para_pdf
            conteudo = _word_para_pdf(Path(nome.lower()).suffix, conteudo)
            ct = "application/pdf"
            nome = f"{Path(nome).stem}.pdf"
        except Exception:
            log.warning("conversão do currículo %s falhou; servindo o original", nome,
                        exc_info=True)

    # Só é `inline` o que o navegador SABE exibir. Word/octet-stream com
    # `inline` abria uma aba em branco — o arquivo vinha certo, o navegador é
    # que não renderiza (feedback 2026-07-28: "anexou um arquivo em word, deu
    # bom para baixar, mas não abriu"). Para esses, `attachment` baixa.
    exibivel = (ct or "").startswith("image/") or ct == "application/pdf"
    registrar(db, "talento_curriculo_visto", ator="rh", ator_detalhe=rh.email,
              detalhe={"talento": t.nome, "arquivo": nome, "tipo": ct,
                       "bytes": len(conteudo),
                       "modo": "inline" if exibivel else "download"})
    db.commit()
    disp = "inline" if exibivel else "attachment"
    return Response(content=conteudo, media_type=ct or "application/octet-stream",
                    headers={"Content-Disposition": f'{disp}; filename="{nome}"',
                             # o front lê para avisar que baixou em vez de abrir
                             "X-Curriculo-Modo": "inline" if exibivel else "download"})


class StatusIn(BaseModel):
    status: StatusTalento
    # Por que arquivou/desarquivou. Vira ANOTAÇÃO no mini-CRM (feedback
    # 2026-07-28) — com autor e data, junto do resto da memória da pessoa.
    motivo: str | None = None


@router.put("/rh/talentos/{talento_id}/status", dependencies=[Depends(requer_rh)])
def mudar_status(talento_id: uuid.UUID, payload: StatusIn, db: Session = Depends(get_db),
                 rh: UsuarioRH = Depends(requer_rh)) -> dict:
    """Muda o status do talento; o motivo (quando vier) vira anotação no CRM.

    O RH pediu "colocar alguma observação por ocasião do arquivamento, bem como
    quem foi o responsável e quando, e poder desfazer". Tudo isso já existe no
    mini-CRM (`Anotacao`: texto, anexo, autor SNAPSHOT e data) — então o
    arquivamento passa a ESCREVER lá em vez de ganhar campos próprios. Assim o
    histórico da pessoa fica num lugar só, e anexar documento ao arquivamento
    já funciona pela tela de anotações.

    Desfazer é mudar o status de volta: o registro do que houve fica, porque a
    anotação é append-only.
    """
    from app.models.crm import Anotacao
    from app.models.talento import StatusTalento as _S

    t = db.get(Talento, talento_id)
    if t is None:
        raise HTTPException(status_code=404, detail="talento_nao_encontrado")
    if t.status == StatusTalento.convertido:
        raise HTTPException(status_code=409, detail="talento_ja_convertido")
    anterior = t.status
    t.status = payload.status

    motivo = (payload.motivo or "").strip()
    if motivo:
        acao = {_S.arquivado: "Arquivado",
                _S.novo: "Reaberto",
                _S.em_analise: "Voltou para análise"}.get(payload.status, "Status alterado")
        db.add(Anotacao(
            talento_id=t.id,
            texto=f"{acao} — {motivo}",
            autor_id=rh.id, autor_nome=rh.nome or rh.email))

    registrar(db, "talento_status_alterado", ator="rh", ator_detalhe=rh.email,
              detalhe={"talento": t.nome, "status": t.status.value,
                       "anterior": anterior.value if anterior else None,
                       "motivo": motivo or None})
    db.commit()
    return _dump(t)


def _aproveitar_testes_do_talento(db: Session, t: Talento,
                                  candidato_id: uuid.UUID,
                                  autor: str | None) -> int:
    """Vincula ao candidato os testes/provas que ESTE talento já respondeu.

    Marcados `automatico=True`: o link foi disparado para ele, então a
    identidade não é palpite (diferente do link avulso anônimo, onde o RH
    escolhe da lista pelo nome). Nunca levanta — a conversão não pode falhar
    por causa do aproveitamento.
    """
    from app.models.prova import AplicacaoProva, LinkProva
    from app.models.teste import StatusTeste
    from app.models.testagem import (LinkTestagem, ParticipanteTestagem,
                                     TesteTestagem)
    from app.services.testes_vinculaveis import vincular

    aproveitados = 0
    try:
        for lk in db.scalars(select(LinkTestagem)
                             .where(LinkTestagem.talento_id == t.id)):
            for p in db.scalars(select(ParticipanteTestagem)
                                .where(ParticipanteTestagem.link_id == lk.id)):
                concluiu = db.scalar(select(TesteTestagem).where(
                    TesteTestagem.participante_id == p.id,
                    TesteTestagem.status == StatusTeste.concluido))
                if concluiu is not None:
                    vincular(db, candidato_id, "testagem", p.id, autor,
                             automatico=True)
                    aproveitados += 1

        for lk in db.scalars(select(LinkProva)
                             .where(LinkProva.talento_id == t.id)):
            for a in db.scalars(select(AplicacaoProva).where(
                    AplicacaoProva.link_id == lk.id,
                    AplicacaoProva.concluido_em.isnot(None))):
                vincular(db, candidato_id, "prova", a.id, autor, automatico=True)
                aproveitados += 1
    except Exception:
        log.warning("falha ao aproveitar testes do talento %s", t.id, exc_info=True)
    return aproveitados


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
    # Aproveita AUTOMATICAMENTE os testes que este talento já respondeu (v2.21):
    # aqui a identidade é certa (o link foi disparado para ele), então não há
    # julgamento a fazer — e refazer o mesmo teste na admissão seria desperdício
    # para a pessoa e ruído para o RH.
    _aproveitados = _aproveitar_testes_do_talento(db, t, candidato.id, rh.email)
    registrar(db, "talento_convertido", ator="rh", ator_detalhe=rh.email,
              candidato_id=candidato.id,
              detalhe={"talento": t.nome, "testes_aproveitados": _aproveitados})
    db.commit()

    enviado = False
    if candidato.email:
        enviado = enviar_modelo(db, "convite_admissao", candidato.email, {
            "primeiro_nome": (candidato.nome_completo or "").split()[0].title(),
            "nome": candidato.nome_completo, "link": link,
        })
    return {"candidato_id": candidato.id, "link_magico": link, "email_enviado": enviado}


# ---------- Enviar teste avulso ao talento (link /t/) ----------


def _resumo_teste_por_talento(db: Session, talentos: list[Talento]) -> dict:
    """Mapa {talento_id: resumo} em 3 consultas — não uma por talento.

    Era um dict comprehension chamando `_resumo_teste_talento` por pessoa (até
    3 consultas cada), com o comentário "1 consulta, sem N+1" logo acima. O
    teste de N+1 do resumo de anotações (v2.15) foi quem expôs: 43 consultas
    para 39 talentos.
    """
    from app.models.teste import StatusTeste
    from app.models.testagem import (LinkTestagem, ParticipanteTestagem,
                                     TesteTestagem)
    if not talentos:
        return {}
    tids = [t.id for t in talentos]

    # do mais novo para o mais antigo: o primeiro que cair no dict é o vigente
    links = list(db.scalars(select(LinkTestagem)
                            .where(LinkTestagem.talento_id.in_(tids))
                            .order_by(LinkTestagem.criado_em.desc())))
    link_do_talento: dict = {}
    for lk in links:
        link_do_talento.setdefault(lk.talento_id, lk)
    if not link_do_talento:
        return {}

    parts = list(db.scalars(select(ParticipanteTestagem)
                            .where(ParticipanteTestagem.link_id.in_(
                                [lk.id for lk in link_do_talento.values()]))
                            .order_by(ParticipanteTestagem.criado_em.desc())))
    part_do_link: dict = {}
    for p in parts:
        part_do_link.setdefault(p.link_id, p)

    testes_do_part: dict = {}
    if parts:
        for x in db.scalars(select(TesteTestagem).where(
                TesteTestagem.participante_id.in_([p.id for p in parts]))):
            testes_do_part.setdefault(x.participante_id, []).append(x)

    saida = {}
    for tid, lk in link_do_talento.items():
        part = part_do_link.get(lk.id)
        if part is None:
            saida[tid] = {"status": "enviado", "token": lk.token}
            continue
        testes = testes_do_part.get(part.id, [])
        concluidos = sum(1 for x in testes if x.status == StatusTeste.concluido)
        total = len(testes)
        saida[tid] = {
            "status": "concluido" if total and concluidos == total else "em_andamento",
            "token": lk.token, "concluidos": concluidos, "total": total}
    return saida


def _resumo_teste_talento(db: Session, talento_id: uuid.UUID) -> dict | None:
    """Status/resultado do teste avulso disparado para o talento, para o dash.
    None se nunca enviou. Junta o link (talento_id) → participante → testes."""
    from app.models.testagem import (LinkTestagem, ParticipanteTestagem,
                                     TesteTestagem)
    from app.models.teste import StatusTeste
    link = db.scalar(select(LinkTestagem)
                     .where(LinkTestagem.talento_id == talento_id)
                     .order_by(LinkTestagem.criado_em.desc()))
    if link is None:
        return None
    part = db.scalar(select(ParticipanteTestagem)
                     .where(ParticipanteTestagem.link_id == link.id)
                     .order_by(ParticipanteTestagem.criado_em.desc()))
    if part is None:
        return {"status": "enviado", "token": link.token}
    testes = db.scalars(select(TesteTestagem)
                        .where(TesteTestagem.participante_id == part.id)).all()
    concluidos = sum(1 for x in testes if x.status == StatusTeste.concluido)
    total = len(testes)
    status = "concluido" if total and concluidos == total else "em_andamento"
    return {"status": status, "token": link.token,
            "concluidos": concluidos, "total": total}


class EnviarTesteIn(BaseModel):
    tem_disc: bool = True
    tem_situacional: bool = True


@router.post("/rh/talentos/{talento_id}/enviar-teste", dependencies=[Depends(requer_rh)])
def enviar_teste(talento_id: uuid.UUID, payload: EnviarTesteIn, request: Request,
                 db: Session = Depends(get_db), rh: UsuarioRH = Depends(requer_rh)) -> dict:
    """Cria um link de testagem DEDICADO ao talento (sem convertê-lo em candidato)
    e envia o link /t/ ao e-mail dele. O resultado volta ao dash pelo talento_id."""
    import secrets

    from app.models.testagem import LinkTestagem
    from app.services.email import enviar_email as _envia, html_moderno
    from app.services.limite import exigir
    t = db.get(Talento, talento_id)
    if t is None:
        raise HTTPException(status_code=404, detail="talento_nao_encontrado")
    if not payload.tem_disc and not payload.tem_situacional:
        raise HTTPException(status_code=422, detail="escolha_ao_menos_um_teste")
    exigir(f"talento-teste:{talento_id}", maximo=5, janela_s=3600)

    link = LinkTestagem(nome=t.nome[:120], token=secrets.token_urlsafe(16),
                        criado_por=rh.email, tem_disc=payload.tem_disc,
                        tem_situacional=payload.tem_situacional,
                        talento_id=t.id, email_destino=t.email)
    db.add(link)
    registrar(db, "talento_teste_enviado", ator="rh", ator_detalhe=rh.email,
              detalhe={"talento": t.nome, "disc": payload.tem_disc,
                       "situacional": payload.tem_situacional})
    db.commit()

    url = f"{base_url_publica(request)}/t/{link.token}"
    enviado = False
    if t.email:
        enviado = _envia(
            t.email,
            "Green House — convite para um teste rápido",
            f"Olá, {t.nome.split()[0].title()}!\n\n"
            "A Green House gostaria que você fizesse um teste rápido como parte do "
            f"nosso processo. Acesse o link e siga as instruções:\n{url}\n\n"
            "É rápido e você pode fazer pelo celular.\n",
            html_moderno(
                "Um teste rápido para você",
                [f"Olá, <strong>{t.nome.split()[0].title()}</strong>!",
                 "A Green House gostaria que você fizesse um teste rápido. "
                 "Toque no botão para começar — é rápido e dá para fazer pelo celular."],
                botao_texto="Fazer o teste", botao_url=url))
    return {"ok": True, "token": link.token, "url": url, "email_enviado": enviado}


@router.get("/rh/talentos/{talento_id}/teste", dependencies=[Depends(requer_rh)])
def teste_do_talento(talento_id: uuid.UUID, db: Session = Depends(get_db)) -> dict:
    """Status/resultado do teste do talento (para o dash abrir o detalhe)."""
    resumo = _resumo_teste_talento(db, talento_id)
    if resumo is None:
        raise HTTPException(status_code=404, detail="sem_teste")
    return resumo


# ---------- Importar a planilha do Microsoft Forms ----------


def _norm_cab_talento(txt: str) -> str:
    import re
    import unicodedata
    txt = unicodedata.normalize("NFKD", str(txt or "")).encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", txt).strip().lower()


def _achar(cab: list[str], *alvos: str) -> int | None:
    norm = [_norm_cab_talento(c) for c in cab]
    for a in alvos:
        na = _norm_cab_talento(a)
        for i, c in enumerate(norm):
            if c == na or (na and na in c):
                return i
    return None


def _lista(valor: str) -> list[str]:
    """Cargos/regiões do Forms vêm separados por ';' (com ';' no fim)."""
    return [p.strip() for p in (valor or "").split(";") if p.strip()]


def _sim_nao(valor: str) -> bool | None:
    v = _norm_cab_talento(valor)
    if v in ("sim", "s"):
        return True
    if v in ("nao", "n"):
        return False
    return None


def _tipo_contratacao(valor: str) -> str | None:
    v = _norm_cab_talento(valor)
    if "efetivo" in v and "intermitente" in v:
        return "tanto_faz"
    if "tanto faz" in v or "os dois" in v or "ambos" in v:
        return "tanto_faz"
    if "intermitente" in v:
        return "intermitente"
    if "efetivo" in v:
        return "efetivo"
    return None


@router.post("/rh/talentos/importar-planilha", dependencies=[Depends(requer_rh)])
async def importar_planilha(arquivo: UploadFile, db: Session = Depends(get_db),
                            rh: UsuarioRH = Depends(requer_rh)) -> dict:
    """Importa os pré-cadastros exportados do Microsoft Forms (.xlsx). Casa as
    colunas pelo cabeçalho, mapeia cargos/regiões (separados por ';') e os
    Sim/Não. Idempotente: PULA quem já existe (por e-mail; ou nome+telefone quando
    sem e-mail) — reimportar a mesma planilha não duplica."""
    from app.api.incidencia_beneficios import _ler_abas
    try:
        conteudo = await arquivo.read()
    finally:
        await arquivo.close()  # descarta o spool em disco (dados pessoais)
    abas = _ler_abas(conteudo)
    if not abas:
        raise HTTPException(status_code=422, detail="arquivo_invalido")
    linhas = next(iter(abas.values()))
    if len(linhas) < 2:
        raise HTTPException(status_code=422, detail="planilha_vazia")
    cab = linhas[0]
    ci = {
        "nome": _achar(cab, "nome completo", "nome"),
        "telefone": _achar(cab, "telefone / whatsapp", "telefone", "whatsapp"),
        "email": _achar(cab, "e-mail", "email"),
        "cidade": _achar(cab, "cidade / bairro", "cidade"),
        "cargos": _achar(cab, "cargos / funcoes de interesse", "cargos"),
        "regioes": _achar(cab, "regioes onde voce pode trabalhar", "regioes"),
        "tipo": _achar(cab, "tipo de contratacao"),
        "ja_trabalhou": _achar(cab, "voce ja trabalhou"),
        "seguro": _achar(cab, "seguro-desemprego", "seguro desemprego"),
        "lgpd": _achar(cab, "autorizacao de uso dos dados", "lgpd"),
    }
    # a coluna "Nome completo" (col 6) é a resposta; a col "Nome" (4) é do Forms
    # (autor anônimo) — o _achar por "nome completo" pega a certa.
    if ci["nome"] is None:
        raise HTTPException(status_code=422, detail="sem_coluna_nome")

    # índice de duplicados existentes (por e-mail; e por nome+telefone)
    existentes = db.scalars(select(Talento)).all()
    por_email = {(t.email or "").strip().lower(): t for t in existentes if t.email}
    por_nome_tel = {((t.nome or "").strip().lower(), _so_digitos_tel(t.telefone))
                    for t in existentes}

    criados = pulados = 0
    for bruta in linhas[1:]:
        v = list(bruta) + [""] * (len(cab) - len(bruta))
        def val(k):  # noqa: E306
            i = ci[k]
            return (str(v[i]).strip() if i is not None and i < len(v) and v[i] is not None else "")
        nome = val("nome")
        if not nome:
            continue
        email = val("email").lower() or None
        tel = val("telefone") or None
        # dedup
        if email and email in por_email:
            pulados += 1
            continue
        if (nome.lower(), _so_digitos_tel(tel)) in por_nome_tel:
            pulados += 1
            continue

        cargos = _lista(val("cargos"))
        regioes = _lista(val("regioes"))
        t = Talento(
            nome=nome[:200], email=(email or None), telefone=(tel[:20] if tel else None),
            cidade=val("cidade")[:120] or None,
            cargos_interesse=cargos or None, regioes=regioes or None,
            cargo_interesse=cargos[0] if cargos else None,
            tipo_contratacao=_tipo_contratacao(val("tipo")),
            ja_trabalhou_funcao=_sim_nao(val("ja_trabalhou")),
            recebe_seguro_desemprego=_sim_nao(val("seguro")),
            origem="Importação (Forms)",
        )
        # LGPD: a planilha registra "Li e concordo" — carimba o consentimento
        if _norm_cab_talento(val("lgpd")):
            t.consentimento_lgpd_em = datetime.now(timezone.utc)
        db.add(t)
        if email:
            por_email[email] = t
        por_nome_tel.add((nome.lower(), _so_digitos_tel(tel)))
        criados += 1

    registrar(db, "talentos_importados", ator="rh", ator_detalhe=rh.email,
              detalhe={"criados": criados, "pulados": pulados})
    db.commit()
    return {"criados": criados, "pulados": pulados, "total_planilha": len(linhas) - 1}


def _so_digitos_tel(tel) -> str:
    return "".join(c for c in str(tel or "") if c.isdigit())
