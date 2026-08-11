"""Carteira de Processos do RH — rotas do painel (v2.91).

Responde à pergunta que o Bruno colocou: *"caso haja algum funcionário
substituído, indo embora do RH ou qualquer outra coisa, tenha uma organização
de processos"*.

A importação segue a mecânica de toda planilha nesta casa: **preview →
confirmar**. Nunca grava direto — a carteira é digitada à mão e revisada por
trimestre, e um merge cego criaria atribuição errada que só apareceria no dia
em que alguém procurasse o responsável.
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.auth_rh import exige
from app.core.db import get_db
from app.models.processo import AtribuicaoProcesso, FuncaoRH, Processo
from app.models.usuario_rh import UsuarioRH
from app.services import processos as sv
from app.services.auditoria import registrar
from app.services.upload_seguro import ler_upload

router = APIRouter(tags=["processos"])

EXT_PLANILHA = frozenset({"xlsx"})


# --------------------------------------------------------------------------
# Consulta
# --------------------------------------------------------------------------

@router.get("/rh/processos/opcoes")
def opcoes(_rh: UsuarioRH = Depends(exige("processos:ler"))) -> dict:
    """Ritmos e cenários — a tela não duplica esses textos (regra da casa)."""
    return {"ritmos": [{"nome": k, "ajuda": v} for k, v in sv.RITMOS.items()],
            "cenarios": list(sv.CENARIOS),
            "criticos": list(sv.RITMOS_CRITICOS)}


@router.get("/rh/processos")
def listar(cenario: str = "C1", db: Session = Depends(get_db),
           _rh: UsuarioRH = Depends(exige("processos:ler"))) -> dict:
    if cenario not in sv.CENARIOS:
        raise HTTPException(status_code=422, detail="cenario_invalido")
    itens = db.scalars(select(Processo).order_by(Processo.codigo)).all()
    return {
        "processos": [sv.dump_processo(db, p, cenario) for p in itens],
        "carga": sv.carga_por_funcao(db, cenario),
        "alertas": sv.alertas(db, cenario),
        "cenario": cenario,
    }


@router.get("/rh/processos/funcoes")
def listar_funcoes(db: Session = Depends(get_db),
                   _rh: UsuarioRH = Depends(exige("processos:ler"))) -> list[dict]:
    funcoes = db.scalars(select(FuncaoRH).order_by(FuncaoRH.ordem, FuncaoRH.nome)).all()
    return [{"id": str(f.id), "nome": f.nome, "descricao": f.descricao,
             "pessoa_nome": f.pessoa_nome, "pessoa_email": f.pessoa_email,
             "ativa": f.ativa, "ordem": f.ordem} for f in funcoes]


# --------------------------------------------------------------------------
# Edição
# --------------------------------------------------------------------------

class FuncaoIn(BaseModel):
    nome: str
    descricao: str | None = None
    # Vazio = vaga aberta. É valor VÁLIDO: é assim que se registra que alguém
    # saiu, e é o que faz a cadeia passar a responder pelo próximo.
    pessoa_nome: str | None = None
    pessoa_email: str | None = None
    ordem: int = 0


@router.post("/rh/processos/funcoes", status_code=201)
def criar_funcao(payload: FuncaoIn, db: Session = Depends(get_db),
                 rh: UsuarioRH = Depends(exige("processos:escrever"))) -> dict:
    nome = (payload.nome or "").strip()
    if not nome:
        raise HTTPException(status_code=422, detail="nome_obrigatorio")
    if db.scalar(select(FuncaoRH).where(FuncaoRH.nome == nome)) is not None:
        raise HTTPException(status_code=409, detail="funcao_ja_existe")
    f = FuncaoRH(nome=nome[:120], descricao=(payload.descricao or "").strip() or None,
                 pessoa_nome=(payload.pessoa_nome or "").strip() or None,
                 pessoa_email=(payload.pessoa_email or "").strip() or None,
                 ordem=payload.ordem)
    db.add(f)
    registrar(db, "funcao_rh_criada", ator="rh", ator_detalhe=rh.email,
              detalhe={"funcao": nome})
    db.commit()
    db.refresh(f)
    return {"id": str(f.id), "nome": f.nome}


@router.put("/rh/processos/funcoes/{funcao_id}")
def editar_funcao(funcao_id: uuid.UUID, payload: FuncaoIn,
                  db: Session = Depends(get_db),
                  rh: UsuarioRH = Depends(exige("processos:escrever"))) -> dict:
    """Troca quem ocupa a função — o ato central do módulo.

    É aqui que "alguém saiu do RH" vira resposta do sistema: esvaziar
    `pessoa_nome` faz TODOS os processos daquela função passarem ao próximo da
    cadeia, na hora, sem redistribuir carteira. A auditoria guarda o de → para
    porque "quem respondia por isto em março?" é a pergunta que se faz depois.
    """
    f = db.get(FuncaoRH, funcao_id)
    if f is None:
        raise HTTPException(status_code=404, detail="funcao_nao_encontrada")
    antes = f.pessoa_nome
    if (payload.nome or "").strip():
        f.nome = payload.nome.strip()[:120]
    f.descricao = (payload.descricao or "").strip() or None
    f.pessoa_nome = (payload.pessoa_nome or "").strip() or None
    f.pessoa_email = (payload.pessoa_email or "").strip() or None
    f.ordem = payload.ordem
    if antes != f.pessoa_nome:
        registrar(db, "funcao_rh_pessoa_trocada", ator="rh", ator_detalhe=rh.email,
                  detalhe={"funcao": f.nome, "de": antes, "para": f.pessoa_nome})
    db.commit()
    return {"id": str(f.id), "nome": f.nome, "pessoa_nome": f.pessoa_nome}


class ProcessoIn(BaseModel):
    codigo: str
    fase: str
    nome: str
    ritmo: str | None = None
    observacao: str | None = None
    aprovadores: list[str] = []
    consultados: list[str] = []
    informados: list[str] = []


@router.post("/rh/processos", status_code=201)
def criar_processo(payload: ProcessoIn, db: Session = Depends(get_db),
                   rh: UsuarioRH = Depends(exige("processos:escrever"))) -> dict:
    codigo = (payload.codigo or "").strip()
    if not codigo or not (payload.nome or "").strip():
        raise HTTPException(status_code=422, detail="codigo_e_nome_obrigatorios")
    if db.scalar(select(Processo).where(Processo.codigo == codigo)) is not None:
        raise HTTPException(status_code=409, detail="codigo_ja_existe")
    p = Processo(codigo=codigo[:20], fase=(payload.fase or "—").strip()[:120],
                 nome=payload.nome.strip()[:300],
                 ritmo=(payload.ritmo or "").strip() or None,
                 observacao=(payload.observacao or "").strip() or None,
                 aprovadores=payload.aprovadores, consultados=payload.consultados,
                 informados=payload.informados)
    db.add(p)
    registrar(db, "processo_criado", ator="rh", ator_detalhe=rh.email,
              detalhe={"codigo": codigo, "nome": p.nome})
    db.commit()
    db.refresh(p)
    return sv.dump_processo(db, p)


@router.put("/rh/processos/{processo_id}")
def editar_processo(processo_id: uuid.UUID, payload: ProcessoIn,
                    db: Session = Depends(get_db),
                    rh: UsuarioRH = Depends(exige("processos:escrever"))) -> dict:
    p = db.get(Processo, processo_id)
    if p is None:
        raise HTTPException(status_code=404, detail="processo_nao_encontrado")
    p.fase = (payload.fase or p.fase).strip()[:120]
    p.nome = (payload.nome or p.nome).strip()[:300]
    p.ritmo = (payload.ritmo or "").strip() or None
    p.observacao = (payload.observacao or "").strip() or None
    p.aprovadores = payload.aprovadores
    p.consultados = payload.consultados
    p.informados = payload.informados
    registrar(db, "processo_editado", ator="rh", ator_detalhe=rh.email,
              detalhe={"codigo": p.codigo})
    db.commit()
    return sv.dump_processo(db, p)


class CadeiaIn(BaseModel):
    cenario: str = "C1"
    # Ordem IMPORTA: a posição na lista é a posição na cadeia. O primeiro é o
    # titular; os demais assumem nessa ordem.
    funcoes: list[uuid.UUID] = []


@router.put("/rh/processos/{processo_id}/cadeia")
def definir_cadeia(processo_id: uuid.UUID, payload: CadeiaIn,
                   db: Session = Depends(get_db),
                   rh: UsuarioRH = Depends(exige("processos:escrever"))) -> dict:
    """Redefine quem responde e em que ordem — a redistribuição da carteira."""
    p = db.get(Processo, processo_id)
    if p is None:
        raise HTTPException(status_code=404, detail="processo_nao_encontrado")
    if payload.cenario not in sv.CENARIOS:
        raise HTTPException(status_code=422, detail="cenario_invalido")
    # Função repetida faria a mesma pessoa cobrir a própria ausência — cadeia
    # que parece ter dois degraus e tem um.
    if len(set(payload.funcoes)) != len(payload.funcoes):
        raise HTTPException(status_code=422, detail="funcao_repetida_na_cadeia")

    for velha in db.scalars(select(AtribuicaoProcesso).where(
            AtribuicaoProcesso.processo_id == p.id,
            AtribuicaoProcesso.cenario == payload.cenario)).all():
        db.delete(velha)
    db.flush()
    for pos, fid in enumerate(payload.funcoes, start=1):
        if db.get(FuncaoRH, fid) is None:
            raise HTTPException(status_code=422, detail={
                "erro": "funcao_desconhecida", "id": str(fid)})
        db.add(AtribuicaoProcesso(processo_id=p.id, funcao_id=fid,
                                  cenario=payload.cenario, posicao=pos))
    registrar(db, "cadeia_processo_definida", ator="rh", ator_detalhe=rh.email,
              detalhe={"codigo": p.codigo, "cenario": payload.cenario,
                       "elos": len(payload.funcoes)})
    db.commit()
    return sv.dump_processo(db, p, payload.cenario)


@router.delete("/rh/processos/{processo_id}", status_code=204)
def excluir_processo(processo_id: uuid.UUID, db: Session = Depends(get_db),
                     rh: UsuarioRH = Depends(exige("processos:escrever"))) -> None:
    p = db.get(Processo, processo_id)
    if p is None:
        raise HTTPException(status_code=404, detail="processo_nao_encontrado")
    from app.services.lixeira import mandar_para_lixeira
    mandar_para_lixeira(db, p, "processo_rh", f"{p.codigo} — {p.nome}", rh.email)
    registrar(db, "processo_excluido", ator="rh", ator_detalhe=rh.email,
              detalhe={"codigo": p.codigo, "nome": p.nome})
    db.delete(p)
    db.commit()


# --------------------------------------------------------------------------
# Importação da planilha (preview → confirmar)
# --------------------------------------------------------------------------

@router.post("/rh/processos/importar-preview")
async def importar_preview(arquivo: UploadFile, db: Session = Depends(get_db),
                           _rh: UsuarioRH = Depends(exige("processos:escrever"))) -> dict:
    """Lê a planilha e PROPÕE — não grava nada."""
    from app.api.incidencia_beneficios import _ler_abas
    from app.services import importar_carteira

    conteudo = await ler_upload(db, arquivo, EXT_PLANILHA)
    abas = _ler_abas(conteudo)
    if not abas:
        raise HTTPException(status_code=422, detail="planilha_ilegivel")
    previa = importar_carteira.analisar(abas, db)
    if not previa.cenarios:
        raise HTTPException(status_code=422, detail={
            "erro": "sem_abas_matriz",
            "abas_encontradas": list(abas.keys())})
    return previa.resumo()


@router.post("/rh/processos/importar")
async def importar(arquivo: UploadFile, db: Session = Depends(get_db),
                   rh: UsuarioRH = Depends(exige("processos:escrever"))) -> dict:
    """Grava o que a prévia mostrou. Reimportar ATUALIZA, não duplica.

    A planilha é reenviada (em vez de o front devolver a prévia) por segurança:
    o que grava é o que o servidor LEU do arquivo, não uma lista que passou
    pelo navegador e pode ter sido alterada no caminho.
    """
    from app.api.incidencia_beneficios import _ler_abas
    from app.services import importar_carteira

    conteudo = await ler_upload(db, arquivo, EXT_PLANILHA)
    abas = _ler_abas(conteudo)
    if not abas:
        raise HTTPException(status_code=422, detail="planilha_ilegivel")
    previa = importar_carteira.analisar(abas, db)
    resultado = importar_carteira.aplicar(db, previa)
    registrar(db, "carteira_processos_importada", ator="rh", ator_detalhe=rh.email,
              detalhe=resultado)
    db.commit()
    return resultado
