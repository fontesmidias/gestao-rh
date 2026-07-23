"""Solicitação de matrícula à entidade formadora (Multicursos).

O RH marca no dash quem vai, escolhe a turma, e o sistema monta o e-mail já
preenchido — com os dados de cada pessoa e o dossiê em anexo. O RH confere,
edita se quiser, e envia.

Texto e assunto vêm da config dinâmica (editáveis no painel): a Multicursos
pode mudar de exigência e o RH ajusta sem deploy.
"""

import logging
from datetime import date

from sqlalchemy.orm import Session

from app.models.candidato import Candidato
from app.models.desenvolvimento import (RegistroDesenvolvimento, StatusRegistro,
                                        TurmaReciclagem)

log = logging.getLogger(__name__)

CHAVE_ASSUNTO = "matricula_assunto"
CHAVE_CORPO_INDIVIDUAL = "matricula_corpo_individual"
CHAVE_CORPO_GRUPO = "matricula_corpo_grupo"
CHAVE_DESTINO = "matricula_email_destino"

# Textos do Bruno (2026-07-22), palavra por palavra. Variáveis entre chaves.
ASSUNTO_PADRAO = "Solicitação de Matrícula - Reciclagem de Brigadista"

CORPO_INDIVIDUAL_PADRAO = """Prezados,

Solicito, por gentileza, a matrícula do colaborador {nome} na turma com início em {data_turma}, no período {periodo}.

Segue em anexo a documentação necessária para a inclusão do colaborador no curso.

Fico no aguardo da confirmação da matrícula. Caso seja necessária alguma informação adicional, permaneço à disposição."""

CORPO_GRUPO_PADRAO = """Prezados,

Solicito, por gentileza, a matrícula dos colaboradores abaixo na turma com início em {data_turma}, no período {periodo}:

{lista_nomes}

Segue em anexo a documentação necessária para a inclusão dos colaboradores no curso.

Fico no aguardo da confirmação da matrícula. Caso seja necessária alguma informação adicional, permaneço à disposição."""

# Papéis que o dossiê da Multicursos exige (documentação informada pelo Bruno):
# documento oficial com foto, certificado de formação e atestado de saúde.
PAPEIS_DOSSIE = ("identidade", "certificado_formacao", "aso")
ROTULO_PAPEL = {
    "identidade": "documento oficial com foto (RG/CNH)",
    "certificado_formacao": "certificado de formação de brigadista",
    "aso": "atestado de saúde ocupacional",
}


def textos(db: Session) -> dict:
    """Assunto e corpos configurados, caindo no padrão quando não há edição."""
    from app.services.config_dinamica import ler_config
    cfg = ler_config(db, (CHAVE_ASSUNTO, CHAVE_CORPO_INDIVIDUAL,
                          CHAVE_CORPO_GRUPO, CHAVE_DESTINO))
    return {
        "assunto": cfg.get(CHAVE_ASSUNTO) or ASSUNTO_PADRAO,
        "corpo_individual": cfg.get(CHAVE_CORPO_INDIVIDUAL) or CORPO_INDIVIDUAL_PADRAO,
        "corpo_grupo": cfg.get(CHAVE_CORPO_GRUPO) or CORPO_GRUPO_PADRAO,
        "email_destino": cfg.get(CHAVE_DESTINO) or "",
    }


def _data_br(d: date | None) -> str:
    """dd/mm — como o Bruno escreve no e-mail ("início em 03/08")."""
    return d.strftime("%d/%m") if d else "(data a definir)"


def pendencias_do_dossie(db: Session, registro: RegistroDesenvolvimento) -> list[str]:
    """O que falta para a pessoa poder ser matriculada.

    Bloqueia o envio (decisão do Bruno): não sai dossiê furado para a clínica.
    Devolve os RÓTULOS legíveis, que vão direto para a tela do RH.
    """
    exigidos = (registro.tipo.documentos_exigidos if registro.tipo else None) \
        or list(PAPEIS_DOSSIE)
    presentes = {a.papel for a in registro.arquivos}
    faltando = [ROTULO_PAPEL.get(p, p) for p in exigidos if p not in presentes]
    if registro.status != StatusRegistro.validado:
        faltando.insert(0, "validação do RH")
    return faltando


def montar(db: Session, registros: list[RegistroDesenvolvimento],
           turma: TurmaReciclagem | None, agrupar: bool,
           data_turma: date | None = None,
           periodo: str | None = None) -> list[dict]:
    """Monta o(s) rascunho(s) de e-mail.

    `agrupar=True` → UM e-mail com todos; `False` → um por pessoa. O Bruno quis
    as duas formas, escolhidas na hora.

    Não envia nada: devolve rascunhos para o RH conferir na tela.
    """
    cfg = textos(db)
    data = data_turma or (turma.inicio_em if turma else None)
    per = periodo or (turma.periodo if turma else "noturno")
    data_fmt = _data_br(data)

    pessoas = []
    for reg in registros:
        col = db.get(Candidato, reg.candidato_id)
        if col is None:
            continue
        pessoas.append({"registro_id": str(reg.id), "candidato_id": str(col.id),
                        "nome": col.nome_completo,
                        "matricula": col.matricula,
                        "cargo": col.cargo_funcao,
                        "pendencias": pendencias_do_dossie(db, reg)})

    if not pessoas:
        return []

    if agrupar:
        lista = "\n".join(f"{i}. {p['nome']}" for i, p in enumerate(pessoas, 1))
        corpo = cfg["corpo_grupo"].format(data_turma=data_fmt, periodo=per,
                                          lista_nomes=lista)
        return [{"assunto": cfg["assunto"], "corpo": corpo,
                 "destinatarios": _destinos(cfg, turma),
                 "colaboradores": pessoas,
                 "anexos": [_nome_dossie(p["nome"]) for p in pessoas]}]

    return [
        {"assunto": cfg["assunto"],
         "corpo": cfg["corpo_individual"].format(nome=p["nome"], data_turma=data_fmt,
                                                 periodo=per),
         "destinatarios": _destinos(cfg, turma),
         "colaboradores": [p],
         "anexos": [_nome_dossie(p["nome"])]}
        for p in pessoas
    ]


def _destinos(cfg: dict, turma: TurmaReciclagem | None) -> list[str]:
    """E-mail da turma vence o padrão global (a clínica pode ter um por turma)."""
    alvo = (turma.email_destino if turma and turma.email_destino
            else cfg["email_destino"])
    return [e.strip() for e in (alvo or "").replace(";", ",").split(",") if e.strip()]


def _nome_dossie(nome: str) -> str:
    """`dossie-joao-paulo-lima.pdf` — passa pelo slug da casa (path traversal:
    o nome vem de texto livre)."""
    from app.services.export_planilha import slug
    return f"dossie-{slug(nome)}.pdf"
