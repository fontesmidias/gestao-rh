"""Planilha de importação de admissões do Tirvu ("Layout de Importação de
Admissões"): 28 colunas em ordem FIXA — o RH baixa daqui e sobe lá, sem
redigitar. O Tirvu deduplica por CPF do lado dele (quem já existe é ignorado)
e RECUSA linha sem CTPS e sem PIS.

Formatos conforme a exportação do próprio Tirvu: CPF com máscara, datas
dd/mm/aaaa, empresa pela razão social. CTPS segue o padrão eSocial (CTPS
Digital): número = o próprio CPF (11 dígitos), série = "0000" — derivada aqui
quando a ficha ainda não a tem gravada."""

import io
import re

from sqlalchemy.orm import Session

from app.models.candidato import Candidato, Empresa, Jornada, PostoServico
from app.models.ficha import (DadosPessoais, DocumentosIdentificacao, Endereco)

COLUNAS_TIRVU = [
    "Empresa", "Posto de Serviço", "Matrícula", "Nome Completo", "CPF",
    "Cargo", "Data de Nascimento", "Data de Admissão", "Sexo (M ou F)",
    "Registra Ponto (S ou N)", "PIS", "CTPS Número", "CTPS Série", "Salário",
    "Salário - Complementar", "Salário - Extra", "Data Vigência - Salário",
    "Descrição da Jornada de Trabalho", "Whatsapp", "Últ. Período Aquisitivo",
    "Endereço", "Endereço - Número", "Endereço - Complemento",
    "Endereço - CEP", "Endereço - Bairro", "Endereço - Cidade",
    "Endereço - UF", "Login Sign-On",
]


def _so_digitos(v) -> str:
    return "".join(ch for ch in str(v or "") if ch.isdigit())


def cpf_mascarado(cpf) -> str:
    d = _so_digitos(cpf)
    if len(d) != 11:
        return str(cpf or "")
    return f"{d[:3]}.{d[3:6]}.{d[6:9]}-{d[9:]}"


def cep_mascarado(cep) -> str:
    """CEP no padrão do Tirvu: 00000-000 (ele exporta com hífen)."""
    d = _so_digitos(cep)
    if len(d) != 8:
        return str(cep or "")
    return f"{d[:5]}-{d[5:]}"


def ctps_do_cpf(cpf) -> tuple[str, str]:
    """CTPS Digital (eSocial): número = CPF completo, série = 0000."""
    d = _so_digitos(cpf)
    if len(d) != 11:
        return "", ""
    return d, "0000"


def _data(v) -> str:
    if v is None or v == "":
        return ""
    if hasattr(v, "strftime"):
        return v.strftime("%d/%m/%Y")
    return str(v)  # Candidato guarda datas já como "dd/mm/aaaa"


def _salario(texto) -> object:
    """'R$ 1.500,00' / '1500' -> número (o Tirvu espera valor); se o texto não
    parsear, vai cru — melhor o Tirvu apontar do que sumir o dado."""
    if not texto:
        return ""
    limpo = re.sub(r"[Rr]\$|\s", "", str(texto))
    if re.fullmatch(r"\d{1,3}(\.\d{3})*(,\d{1,2})?|\d+(,\d{1,2})?", limpo):
        try:
            return float(limpo.replace(".", "").replace(",", "."))
        except ValueError:
            pass
    if re.fullmatch(r"\d+(\.\d{1,2})?", limpo):
        return float(limpo)
    return str(texto)


PREFIXO_MATRICULA_AUTO = "999"


def proxima_matricula_auto(db: Session) -> str:
    """Próxima matrícula automática no padrão 999 + sequencial de 4 dígitos
    (9990001, 9990002, ...). Continua de onde parou: pega a MAIOR matrícula que
    casa com 999NNNN já gravada e soma 1. Estável e sem colisão."""
    from sqlalchemy import select
    matriculas = db.scalars(
        select(Candidato.matricula).where(
            Candidato.matricula.like(f"{PREFIXO_MATRICULA_AUTO}____"))).all()
    maior = 0
    for m in matriculas:
        d = _so_digitos(m)
        # 999 + 4 dígitos => 7 dígitos exatos começando por 999
        if len(d) == 7 and d.startswith(PREFIXO_MATRICULA_AUTO):
            maior = max(maior, int(d[3:]))
    return f"{PREFIXO_MATRICULA_AUTO}{maior + 1:04d}"


def garantir_matricula(db: Session, c: Candidato) -> str:
    """Garante que o colaborador tenha matrícula: se não tiver, gera a automática
    (999+seq) e GRAVA no cadastro (fica estável para sempre). O caller faz o
    commit. O Tirvu exige matrícula — assim ninguém sobe sem ela."""
    if c.matricula and c.matricula.strip():
        return c.matricula
    nova = proxima_matricula_auto(db)
    c.matricula = nova
    db.flush()  # materializa para a próxima chamada na mesma transação não colidir
    return nova


def linha_tirvu(db: Session, c: Candidato, gerar_matricula: bool = False) -> dict:
    """Uma linha do layout, na ordem exata das 28 colunas.

    `gerar_matricula=True` (só no EXPORT) gera e GRAVA a matrícula automática
    quando faltar. Na pré-checagem de pendências fica False — consulta não muta
    dados (e a matrícula deixa de ser pendência, já que o export a gera)."""
    p = db.get(DadosPessoais, c.id)
    e = db.get(Endereco, c.id)
    d = db.get(DocumentosIdentificacao, c.id)
    posto = db.get(PostoServico, c.posto_servico_id) if c.posto_servico_id else None
    empresa = db.get(Empresa, c.empresa_id) if c.empresa_id else None
    jornada = db.get(Jornada, c.jornada_id) if c.jornada_id else None

    cpf = (d.cpf if d and d.cpf else c.cpf) or ""
    ctps_num, ctps_serie = "", ""
    if d and d.ctps_numero:
        ctps_num, ctps_serie = d.ctps_numero, d.ctps_serie or "0000"
    elif cpf:
        ctps_num, ctps_serie = ctps_do_cpf(cpf)

    sexo = ""
    if p and p.sexo:
        sexo = "M" if p.sexo.value == "masculino" else "F"

    ponto = ""
    if c.registra_ponto is not None:
        ponto = "S" if c.registra_ponto else "N"

    nascimento = (p.data_nascimento if p and p.data_nascimento
                  else c.data_nascimento)

    # Endereço: coleta nova tem os campos separados; a antiga fica na string
    # única, que vai inteira na coluna "Endereço" (o Tirvu aceita as demais
    # vazias — validado pelo Bruno em 2026-07-19).
    logradouro, numero, complemento = "", "", ""
    if e:
        if e.logradouro:
            logradouro, numero, complemento = (
                e.logradouro, e.numero or "", e.complemento or "")
        else:
            logradouro = e.logradouro_numero_complemento or ""

    matricula = garantir_matricula(db, c) if gerar_matricula else (c.matricula or "")

    return {
        "Empresa": empresa.razao_social if empresa else "",
        "Posto de Serviço": posto.nome if posto else "",
        "Matrícula": matricula,
        "Nome Completo": c.nome_completo or "",
        "CPF": cpf_mascarado(cpf),
        "Cargo": c.cargo_funcao or "",
        "Data de Nascimento": _data(nascimento),
        "Data de Admissão": _data(c.data_admissao),
        "Sexo (M ou F)": sexo,
        "Registra Ponto (S ou N)": ponto,
        "PIS": (d.pis_nis_pasep if d else "") or "",
        "CTPS Número": ctps_num,
        "CTPS Série": ctps_serie,
        "Salário": _salario(c.salario_base),
        "Salário - Complementar": "",
        "Salário - Extra": "",
        "Data Vigência - Salário": "",
        "Descrição da Jornada de Trabalho": jornada.descricao if jornada else "",
        "Whatsapp": c.celular_whatsapp or "",
        "Últ. Período Aquisitivo": "",
        "Endereço": logradouro,
        "Endereço - Número": numero,
        "Endereço - Complemento": complemento,
        "Endereço - CEP": cep_mascarado(e.cep if e else ""),
        "Endereço - Bairro": (e.bairro if e else "") or "",
        "Endereço - Cidade": (e.cidade if e else "") or "",
        "Endereço - UF": (e.uf if e else "") or "",
        "Login Sign-On": "",
    }


ABA_TIRVU = "Plan1"


def montar_workbook_tirvu(linhas: list[dict]) -> bytes:
    """Gera a planilha EXATAMENTE no formato que o Tirvu aceita na importação:
    aba 'Plan1', as 28 colunas de COLUNAS_TIRVU em ordem FIXA (nunca a união das
    chaves), SEM auto-filtro, SEM painel congelado e SEM cabeçalho estilizado —
    o importador do Tirvu recusa planilhas com essa "decoração" (autoFilter no
    XML, aba com outro nome). Célula vazia é string vazia (não célula ausente/
    inlineStr solta), para o parser não tropeçar.

    Difere de propósito do `export_planilha.montar_workbook` (que é para o RH ler,
    com cor/filtro/congelamento) — este é para MÁQUINA, fiel ao modelo oficial
    `docs/Layout de Importação de Admissões.xlsx`."""
    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    ws.title = ABA_TIRVU
    # cabeçalho: texto puro, sem estilo (o modelo tem negrito, mas o que o Tirvu
    # lê é o TEXTO — mantemos simples e fiel à ordem)
    for j, nome in enumerate(COLUNAS_TIRVU, start=1):
        ws.cell(row=1, column=j, value=nome)
    for i, linha in enumerate(linhas, start=2):
        for j, nome in enumerate(COLUNAS_TIRVU, start=1):
            v = linha.get(nome, "")
            # Célula vazia: NÃO escreve (deixa ausente) — evita o
            # `<c t="inlineStr"></c>` malformado do openpyxl (tipo string sem o
            # elemento <is>), que faz parsers rígidos como o do Tirvu recusarem.
            # Só grava quando há conteúdo; números (salário) permanecem número.
            if v is None or v == "":
                continue
            ws.cell(row=i, column=j, value=v)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def pendencias_linha(linha: dict) -> list[str]:
    """O que o Tirvu recusa/acusa como divergência no upload. Vai no aviso ao RH
    ANTES do upload — melhor saber aqui que descobrir na tela de divergências do
    Tirvu. A Matrícula NÃO entra: é auto-gerada (999+seq) no export. A Jornada
    entra: é dado real do cadastro que o Tirvu exige."""
    faltas = []
    for campo in ("Nome Completo", "CPF", "PIS", "CTPS Número",
                  "Data de Admissão", "Empresa", "Cargo",
                  "Descrição da Jornada de Trabalho"):
        if not linha.get(campo):
            # rótulo amigável p/ a jornada
            faltas.append("Jornada de Trabalho"
                          if campo == "Descrição da Jornada de Trabalho" else campo)
    return faltas
