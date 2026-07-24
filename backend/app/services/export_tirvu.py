"""Planilha de importação de admissões do Tirvu ("Layout de Importação de
Admissões"): 28 colunas em ordem FIXA — o RH baixa daqui e sobe lá, sem
redigitar. O Tirvu deduplica por CPF do lado dele (quem já existe é ignorado)
e RECUSA linha sem CTPS e sem PIS.

Formatos conforme a exportação do próprio Tirvu: CPF com máscara, datas
dd/mm/aaaa. CTPS Digital derivada do CPF no formato que o Tirvu importa
(feedback 2026-07-24): número = os 7 primeiros dígitos do CPF, série = os 4
últimos (juntos reconstroem o CPF). NÃO é (CPF completo, "0000")."""

import io
import re
import unicodedata

from sqlalchemy.orm import Session

from app.models.candidato import (Candidato, CargoTirvu, Jornada,
                                  PostoServico)
from app.models.ficha import (DadosPessoais, DocumentosIdentificacao, Endereco)


def normalizar_cargo(texto) -> str:
    """Chave de casamento do de-para de cargo: minúsculo, sem acento, espaços
    colapsados. "Analista DF Jr"/"analista df jr "/"Analista  DF  Jr" → mesma
    chave, mesmo tirvu_id."""
    sem_acento = "".join(
        c for c in unicodedata.normalize("NFKD", str(texto or ""))
        if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", sem_acento).strip().lower()


def tirvu_id_do_cargo(db: Session, cargo_funcao) -> str:
    """ID do Tirvu para um cargo (texto livre) via de-para `CargoTirvu`. Vazio se
    o cargo não foi cadastrado — vira pendência na pré-checagem."""
    chave = normalizar_cargo(cargo_funcao)
    if not chave:
        return ""
    from sqlalchemy import select
    m = db.scalar(select(CargoTirvu).where(CargoTirvu.cargo_normalizado == chave))
    return (m.tirvu_id if m else "") or ""

# A empregadora é sempre a Green House, ID 1 na base do Tirvu (decisão do Bruno
# 2026-07-24). Fixo no export — não depende de cadastro de empresa.
EMPRESA_TIRVU_ID = "1"

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
    """CTPS Digital derivada do CPF, no formato que o Tirvu importa (feedback de
    campo 2026-07-24): NÚMERO = os 7 primeiros dígitos do CPF, SÉRIE = os 4
    últimos. Juntos reconstroem o CPF. NÃO é (CPF completo, "0000") — esse era o
    formato antigo, que o Tirvu recusou ("veio tudo junto, não separou os quatro
    últimos como série")."""
    d = _so_digitos(cpf)
    if len(d) != 11:
        return "", ""
    return d[:7], d[7:]


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
    jornada = db.get(Jornada, c.jornada_id) if c.jornada_id else None
    # Empresa é fixa (ID 1, Green House) — não precisa buscar do cadastro.

    cpf = (d.cpf if d and d.cpf else c.cpf) or ""
    # CTPS para o Tirvu: SEMPRE derivar do CPF (número = 7 primeiros, série = 4
    # últimos). O que está GRAVADO em ctps_numero/serie pode ser o formato antigo
    # (CPF completo + "0000") de fichas anteriores a 2026-07-24 — o export não
    # backfilla o banco nem toca o PDF assinado, apenas gera a planilha certa.
    # Só cai no gravado se, por algum motivo, não houver CPF.
    ctps_num, ctps_serie = ctps_do_cpf(cpf) if cpf else ("", "")
    # Se o CPF é inválido/ausente (derivação vazia) mas há CTPS gravada, usa a
    # gravada — não perder o dado por causa de um CPF sujo (B1 da revisão).
    if not ctps_num and d and d.ctps_numero:
        ctps_num, ctps_serie = d.ctps_numero, d.ctps_serie or ""

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

    # Empresa/Posto/Cargo/Jornada: o importador do Tirvu casa por ID NUMÉRICO da
    # base dele, não pelo texto (feedback 2026-07-24: colar o texto fez o Tirvu
    # gravar zero). Escrevemos o `tirvu_id` cadastrado; se faltar, sai vazio e
    # `pendencias_linha` acusa (melhor barrar aqui que subir e o Tirvu zerar).
    return {
        # Empresa é SEMPRE a Green House = ID 1 no Tirvu (decisão do Bruno
        # 2026-07-24: o grupo opera com uma empregadora só; não depende de
        # cadastro nem vira pendência). Se um dia houver outra, trocar aqui.
        "Empresa": EMPRESA_TIRVU_ID,
        "Posto de Serviço": (posto.tirvu_id if posto else "") or "",
        "Matrícula": matricula,
        "Nome Completo": c.nome_completo or "",
        "CPF": cpf_mascarado(cpf),
        "Cargo": tirvu_id_do_cargo(db, c.cargo_funcao),
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
        # Apesar do nome "Descrição", o Tirvu casa a jornada por ID (feedback
        # 2026-07-24: "veio com id zerado, o correto seria 246"). Escreve o
        # tirvu_id da jornada, não a descrição.
        "Descrição da Jornada de Trabalho": (jornada.tirvu_id if jornada else "") or "",
        # só dígitos: o front agora guarda mascarado (61) 99999-8888, mas o
        # Tirvu recebe o telefone limpo (como PIS/CPF-sem-máscara alhures)
        "Whatsapp": _so_digitos(c.celular_whatsapp),
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


# Rótulo amigável do campo na lista de pendências mostrada ao RH (a coluna do
# layout tem nome técnico; o RH lê o nome do campo como aparece na ficha).
_ROTULO_PENDENCIA = {
    # Estes agora saem como ID do Tirvu; se vazio, o cadastro do ID falta.
    "Posto de Serviço": "ID Tirvu do posto",
    "Cargo": "ID Tirvu do cargo",
    "Descrição da Jornada de Trabalho": "ID Tirvu da jornada",
    "Registra Ponto (S ou N)": "Registra Ponto",
}


def pendencias_linha(linha: dict) -> list[str]:
    """O que o Tirvu recusa/acusa como divergência no upload. Vai no aviso ao RH
    ANTES do upload — melhor saber aqui que descobrir na tela de divergências do
    Tirvu. A Matrícula NÃO entra: é auto-gerada (999+seq) no export. A Jornada
    entra: é dado real do cadastro que o Tirvu exige.

    "Registra Ponto" também entra (v1.82): é dado real do cadastro e sai em
    branco quando ninguém preencheu — o Tirvu aceita a célula vazia calado, e o
    colaborador nasce lá sem a marcação. Vira pendência aqui em vez de campo
    obrigatório no formulário: exigir na tela travaria a edição dos importados
    do Tirvu, que nasceram sem o campo."""
    faltas = []
    # "Empresa" não entra: é fixa (ID 1, Green House) — nunca falta.
    for campo in ("Nome Completo", "CPF", "PIS", "CTPS Número",
                  "Data de Admissão", "Posto de Serviço", "Cargo",
                  "Descrição da Jornada de Trabalho", "Registra Ponto (S ou N)"):
        if not linha.get(campo):
            faltas.append(_ROTULO_PENDENCIA.get(campo, campo))
    return faltas
