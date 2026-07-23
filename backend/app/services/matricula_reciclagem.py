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

Solicito, por gentileza, a matrícula dos {quantidade} colaboradores abaixo na turma com início em {data_turma}, no período {periodo}:

{lista_nomes}

Segue em anexo a documentação necessária para a inclusão dos colaboradores no curso — um arquivo por colaborador, identificado pelo nome.

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


def _cpf_fmt(cpf: str | None) -> str:
    """CPF mascarado. Se não forem 11 dígitos, devolve VAZIO em vez do valor
    cru: um "CPF" malformado no e-mail da clínica é pior que nenhum — ela
    tentaria cadastrar com ele."""
    d = "".join(c for c in (cpf or "") if c.isdigit())
    return f"{d[:3]}.{d[3:6]}.{d[6:9]}-{d[9:]}" if len(d) == 11 else ""


_MINUSCULAS = {"de", "da", "do", "das", "dos", "e"}


def _titulo(texto: str | None) -> str:
    """Capitaliza sem transformar preposição em nome próprio: o `.title()` do
    Python devolve "Chefe De Brigada" — aqui sai "Chefe de Brigada"."""
    if not texto:
        return ""
    palavras = texto.lower().split()
    return " ".join(p if i and p in _MINUSCULAS else p.capitalize()
                    for i, p in enumerate(palavras))


def _linha_pessoa(i: int, p: dict) -> str:
    """Uma pessoa na lista do e-mail em GRUPO.

    Vai com os DADOS DE MATRÍCULA, não só o nome: a clínica precisa cadastrar
    cada um, e com nome sozinho ela teria de abrir os PDFs para achar CPF e
    nascimento (pedido do Bruno: "inserir automaticamente as informações
    necessárias para matricular as pessoas"). Campo ausente é omitido, para não
    poluir a linha com rótulo vazio.
    """
    partes = [f"{i}. {p['nome']}"]
    detalhes = []
    cpf = _cpf_fmt(p.get("cpf"))
    if cpf:
        detalhes.append(f"CPF {cpf}")
    if p.get("data_nascimento"):
        detalhes.append(f"nascimento {p['data_nascimento']}")
    if p.get("cargo"):
        detalhes.append(_titulo(p["cargo"]))
    if detalhes:
        partes.append("   " + " · ".join(detalhes))
    return "\n".join(partes)


def _html_grupo(assunto: str, corpo: str, pessoas: list[dict],
                data_fmt: str, periodo: str) -> str:
    """Versão HTML do e-mail em grupo: os dados viram TABELA.

    Com 2+ pessoas a lista em texto puro fica difícil de conferir; em tabela a
    clínica bate os campos de cadastro de uma olhada. O texto puro continua
    sendo enviado junto (multipart) para quem lê em cliente sem HTML.
    """
    from app.services.email import html_moderno
    linhas = "".join(
        f'<tr>'
        f'<td style="padding:8px 10px;border-bottom:1px solid #e6ece4">{i}</td>'
        f'<td style="padding:8px 10px;border-bottom:1px solid #e6ece4">'
        f'<strong>{p["nome"]}</strong></td>'
        f'<td style="padding:8px 10px;border-bottom:1px solid #e6ece4;'
        f'white-space:nowrap">{_cpf_fmt(p.get("cpf")) or "—"}</td>'
        f'<td style="padding:8px 10px;border-bottom:1px solid #e6ece4;'
        f'white-space:nowrap">{p.get("data_nascimento") or "—"}</td>'
        f'<td style="padding:8px 10px;border-bottom:1px solid #e6ece4">'
        f'{_titulo(p.get("cargo")) or "—"}</td>'
        f'</tr>'
        for i, p in enumerate(pessoas, 1))
    tabela = (
        '<table style="width:100%;border-collapse:collapse;font-size:14px;'
        'margin:18px 0">'
        '<thead><tr style="background:#f2f8ea;text-align:left">'
        '<th style="padding:8px 10px">#</th>'
        '<th style="padding:8px 10px">Colaborador</th>'
        '<th style="padding:8px 10px">CPF</th>'
        '<th style="padding:8px 10px">Nascimento</th>'
        '<th style="padding:8px 10px">Cargo</th>'
        '</tr></thead>'
        f'<tbody>{linhas}</tbody></table>')
    # O corpo editado pelo RH manda: o que vem antes da lista e o que vem
    # depois são preservados, e só a lista em texto vira tabela.
    antes, _, depois = corpo.partition("{lista_nomes}")
    if not depois:  # corpo já formatado (o RH editou): quebra na 1ª linha "1. "
        pedaco = corpo.split("\n1. ")
        antes = pedaco[0]
        depois = ("\n".join(pedaco[1].split("\n")[len(pessoas):])
                  if len(pedaco) > 1 else "")
    paragrafos = [p.strip().replace("\n", "<br>") for p in antes.split("\n\n") if p.strip()]
    paragrafos.append(tabela)
    paragrafos += [p.strip().replace("\n", "<br>")
                   for p in depois.split("\n\n") if p.strip()]
    return html_moderno(assunto, paragrafos, rodape="RH — Green House")


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
                        "cpf": col.cpf,
                        "data_nascimento": _nascimento(db, col),
                        "matricula": col.matricula,
                        "cargo": col.cargo_funcao,
                        "pendencias": pendencias_do_dossie(db, reg)})

    if not pessoas:
        return []

    if agrupar:
        lista = "\n".join(_linha_pessoa(i, p) for i, p in enumerate(pessoas, 1))
        corpo = cfg["corpo_grupo"].format(data_turma=data_fmt, periodo=per,
                                          lista_nomes=lista,
                                          quantidade=len(pessoas))
        return [{"assunto": cfg["assunto"], "corpo": corpo,
                 "corpo_html": _html_grupo(cfg["assunto"], corpo, pessoas,
                                           data_fmt, per),
                 "destinatarios": _destinos(cfg, turma),
                 "colaboradores": pessoas,
                 "agrupado": True,
                 "anexos": [_nome_dossie(p["nome"]) for p in pessoas]}]

    return [
        {"assunto": cfg["assunto"],
         "corpo": cfg["corpo_individual"].format(nome=p["nome"], data_turma=data_fmt,
                                                 periodo=per),
         "destinatarios": _destinos(cfg, turma),
         "colaboradores": [p],
         "agrupado": False,
         "anexos": [_nome_dossie(p["nome"])]}
        for p in pessoas
    ]


def _nascimento(db: Session, col: Candidato) -> str | None:
    """dd/mm/aaaa. A nativa do Candidato já é string (vale para o importado do
    Tirvu); a da ficha é date e só é consultada quando a nativa falta."""
    nativa = (col.data_nascimento or "").strip()
    if len(nativa) == 10:
        return nativa
    from app.models.ficha import DadosPessoais
    p = db.get(DadosPessoais, col.id)
    if p and p.data_nascimento:
        return p.data_nascimento.strftime("%d/%m/%Y")
    return None


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
