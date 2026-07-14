"""Geração das 3 fichas em PDF (fpdf2 — puro Python, roda igual em qualquer ambiente).

Cada gerador recebe o candidato + entidades da ficha e devolve bytes de PDF.
Quando `assinatura` é passada, o rodapé ganha o bloco de assinatura eletrônica
com a trilha de evidências (Lei 14.063/2020).
"""

from datetime import date, datetime

from fpdf import FPDF
from sqlalchemy.orm import Session

from app.models.assinatura import Assinatura
from app.models.candidato import Candidato
from app.models.ficha import (
    ContatoEmergencia,
    DadosPessoais,
    DadosProfissionaisBancarios,
    Dependente,
    DocumentosIdentificacao,
    Endereco,
    FichaEmergencia,
    ValeTransporte,
)
from sqlalchemy import select

VERDE = (140, 198, 63)
AZUL = (43, 46, 74)


def _latin1(texto: str) -> str:
    """Fontes core do PDF são latin-1; troca o que não existe nela (—, emojis…)."""
    return (
        texto.replace("—", "-").replace("–", "-").replace("’", "'")
        .encode("latin-1", "replace").decode("latin-1")
    )


class _FichaPDF(FPDF):
    def cell(self, *args, **kwargs):  # type: ignore[override]
        if args and isinstance(args[2] if len(args) > 2 else kwargs.get("text"), str):
            if len(args) > 2:
                args = (*args[:2], _latin1(args[2]), *args[3:])
            else:
                kwargs["text"] = _latin1(kwargs["text"])
        return super().cell(*args, **kwargs)

    def multi_cell(self, *args, **kwargs):  # type: ignore[override]
        if len(args) > 2 and isinstance(args[2], str):
            args = (*args[:2], _latin1(args[2]), *args[3:])
        elif isinstance(kwargs.get("text"), str):
            kwargs["text"] = _latin1(kwargs["text"])
        return super().multi_cell(*args, **kwargs)

    def __init__(self, titulo: str):
        super().__init__()
        self.titulo = titulo
        self.set_auto_page_break(auto=True, margin=20)
        self.add_page()

    def header(self):
        self.set_font("helvetica", "B", 14)
        self.set_text_color(*AZUL)
        self.cell(0, 8, "GREEN HOUSE", align="L")
        self.set_font("helvetica", "B", 12)
        self.cell(0, 8, self.titulo, align="R", new_x="LMARGIN", new_y="NEXT")
        self.set_draw_color(*VERDE)
        self.set_line_width(0.8)
        self.line(10, self.get_y() + 1, 200, self.get_y() + 1)
        self.ln(6)

    def secao(self, nome: str):
        self.set_font("helvetica", "B", 11)
        self.set_text_color(*VERDE)
        self.cell(0, 8, nome, new_x="LMARGIN", new_y="NEXT")
        self.set_text_color(30, 30, 30)

    def campo(self, rotulo: str, valor) -> None:
        if valor is None or valor == "":
            valor = "-"
        if isinstance(valor, bool):
            valor = "Sim" if valor else "Não"
        if isinstance(valor, (date, datetime)):
            valor = valor.strftime("%d/%m/%Y")
        if hasattr(valor, "value"):
            valor = str(valor.value).replace("_", " ").title()
        self.set_font("helvetica", "B", 9)
        self.cell(58, 6, f"{rotulo}:")
        self.set_font("helvetica", "", 9)
        self.multi_cell(0, 6, str(valor), new_x="LMARGIN", new_y="NEXT")

    def bloco_assinatura(self, assinatura: Assinatura, nome: str):
        self.ln(8)
        self.set_draw_color(*AZUL)
        self.set_line_width(0.3)
        y = self.get_y()
        self.rect(10, y, 190, 30)
        self.set_xy(14, y + 3)
        self.set_font("helvetica", "B", 9)
        self.cell(0, 5, "ASSINATURA ELETRÔNICA (Lei nº 14.063/2020)",
                  new_x="LMARGIN", new_y="NEXT")
        self.set_x(14)
        self.set_font("helvetica", "", 8)
        quando = assinatura.assinado_em.strftime("%d/%m/%Y %H:%M:%S UTC")
        self.multi_cell(
            182, 4.5,
            f"Assinado por {nome} em {quando}, mediante código de verificação enviado ao "
            f"titular. IP: {assinatura.ip or '-'}\n"
            f"Integridade (SHA-256 do documento sem este bloco): {assinatura.hash_sha256}",
        )


def _dump_pessoais(pdf: _FichaPDF, candidato: Candidato, p: DadosPessoais | None):
    pdf.secao("Dados Pessoais")
    pdf.campo("Nome completo", candidato.nome_completo)
    if p:
        pdf.campo("Data de nascimento", p.data_nascimento)
        pdf.campo("Sexo", p.sexo)
        pdf.campo("Identidade de gênero", p.identidade_genero)
        pdf.campo("Nacionalidade", p.nacionalidade)
        pdf.campo("Naturalidade", f"{p.naturalidade_cidade or '-'}/{p.naturalidade_uf or '-'}")
        pdf.campo("Estado civil", p.estado_civil)
        pdf.campo("Escolaridade", p.escolaridade)
        pdf.campo("PCD", p.pcd)
    pdf.campo("E-mail", candidato.email)
    pdf.campo("Celular/WhatsApp", candidato.celular_whatsapp)


def gerar_ficha_cadastro(db: Session, candidato: Candidato,
                         assinatura: Assinatura | None = None) -> bytes:
    p = db.get(DadosPessoais, candidato.id)
    e = db.get(Endereco, candidato.id)
    d = db.get(DocumentosIdentificacao, candidato.id)
    b = db.get(DadosProfissionaisBancarios, candidato.id)
    deps = db.scalars(select(Dependente).where(Dependente.candidato_id == candidato.id)).all()

    pdf = _FichaPDF("Ficha de Registro do Colaborador")
    _dump_pessoais(pdf, candidato, p)
    if p:
        pdf.campo("Cor/raça (autodeclaração)", p.cor_raca)

    pdf.ln(2); pdf.secao("Endereço")
    if e:
        pdf.campo("Endereço", e.logradouro_numero_complemento)
        pdf.campo("Bairro", e.bairro)
        pdf.campo("Cidade/UF", f"{e.cidade or '-'}/{e.uf or '-'}")
        pdf.campo("CEP", e.cep)

    pdf.ln(2); pdf.secao("Documentos")
    if d:
        pdf.campo("RG", f"{d.rg_numero or '-'} — {d.rg_orgao_emissor or '-'}")
        pdf.campo("RG — expedição", d.rg_data_expedicao)
        pdf.campo("CPF", d.cpf)
        pdf.campo("PIS/NIS/PASEP", d.pis_nis_pasep)
        if d.cnh_numero:
            pdf.campo("CNH", f"{d.cnh_numero} (cat. {d.cnh_categoria or '-'})")
        pdf.campo("Título de Eleitor",
                  f"{d.titulo_eleitor_numero or '-'} zona {d.titulo_eleitor_zona or '-'} "
                  f"seção {d.titulo_eleitor_secao or '-'}")

    pdf.ln(2); pdf.secao("Uniforme e Dados Bancários")
    if b:
        pdf.campo("Uniforme (calça/camisa/calçado)",
                  f"{b.tamanho_calca or '-'} / {b.tamanho_camisa or '-'} / {b.tamanho_calcado or '-'}")
        pdf.campo("Banco", b.banco)
        pdf.campo("Chave PIX", f"{(b.pix_tipo.value if b.pix_tipo else '-')}: {b.pix_chave or '-'}")

    if deps:
        pdf.ln(2); pdf.secao("Dependentes")
        for i, dep in enumerate(deps, 1):
            pdf.campo(f"Dependente {i}",
                      f"{dep.nome_completo} — {dep.data_nascimento.strftime('%d/%m/%Y')} — "
                      f"CPF {dep.cpf} — {dep.parentesco.value} — "
                      f"IRRF: {'sim' if dep.deduz_irrf else 'não'}")

    if assinatura:
        pdf.bloco_assinatura(assinatura, candidato.nome_completo)
    return bytes(pdf.output())


def gerar_ficha_emergencia(db: Session, candidato: Candidato,
                           assinatura: Assinatura | None = None) -> bytes:
    p = db.get(DadosPessoais, candidato.id)
    fe = db.get(FichaEmergencia, candidato.id)
    contatos = db.scalars(
        select(ContatoEmergencia)
        .where(ContatoEmergencia.candidato_id == candidato.id)
        .order_by(ContatoEmergencia.ordem)
    ).all()

    pdf = _FichaPDF("Ficha de Emergência")
    pdf.secao("Colaborador")
    pdf.campo("Nome completo", candidato.nome_completo)
    if p:
        pdf.campo("Data de nascimento", p.data_nascimento)
    pdf.campo("Celular", candidato.celular_whatsapp)

    pdf.ln(2); pdf.secao("Saúde")
    if fe:
        pdf.campo("Tipo sanguíneo", fe.tipo_sanguineo)
        pdf.campo("Uso contínuo de medicamentos", fe.usa_medicamento_continuo)
        pdf.campo("Medicamentos", fe.medicamentos)
        pdf.campo("Condições médicas", fe.condicoes_medicas)
        pdf.campo("Orientação em emergência", fe.orientacao_emergencia)

    pdf.ln(2); pdf.secao("Contatos de Emergência")
    for c in contatos:
        pdf.campo(f"Contato {c.ordem}",
                  f"{c.nome_completo} ({c.parentesco}) — {c.telefone_celular}"
                  + (f" — {c.telefone_fixo_endereco}" if c.telefone_fixo_endereco else ""))

    pdf.ln(4)
    pdf.set_font("helvetica", "I", 8)
    pdf.multi_cell(0, 4.5, "Dados de saúde tratados exclusivamente para proteção da vida e "
                           "integridade física do titular (LGPD, art. 11, II, 'a' e 'e').")
    if assinatura:
        pdf.bloco_assinatura(assinatura, candidato.nome_completo)
    return bytes(pdf.output())


def gerar_termo_vt(db: Session, candidato: Candidato,
                   assinatura: Assinatura | None = None) -> bytes:
    d = db.get(DocumentosIdentificacao, candidato.id)
    vt = db.get(ValeTransporte, candidato.id)

    pdf = _FichaPDF("Termo de Opção — Vale-Transporte")
    pdf.set_font("helvetica", "", 10)
    optante = bool(vt and vt.optante)
    cpf = d.cpf if d else "-"
    pdf.multi_cell(
        0, 6,
        f"Eu, {candidato.nome_completo}, CPF {cpf}, nos termos da Lei nº 7.418/1985 (art. 4º) "
        f"e do Decreto nº 95.247/1987, declaro que "
        + ("OPTO por receber o Vale-Transporte, autorizando o desconto legal de até 6% do meu "
           "salário básico." if optante
           else "NÃO OPTO por receber o Vale-Transporte, estando ciente de que poderei "
                "solicitá-lo posteriormente mediante novo termo."),
    )
    pdf.ln(4)
    if optante and vt:
        pdf.secao("Dados do benefício")
        pdf.campo("Cartão DFTrans", vt.cartao_dftrans)
        pdf.campo("Trajeto casa-trabalho", vt.trajeto_descricao)

    if assinatura:
        pdf.bloco_assinatura(assinatura, candidato.nome_completo)
    return bytes(pdf.output())


GERADORES = {
    "ficha_cadastro": gerar_ficha_cadastro,
    "ficha_emergencia": gerar_ficha_emergencia,
    "termo_vt": gerar_termo_vt,
}
