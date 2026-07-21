"""PDFs do Reembolso-Creche no papel timbrado da Green House:
- requerimento de concessão (preenchido, com as cláusulas legais da IN 147/2026);
- declaração-modelo de despesa (para o colaborador usar mensalmente, quando a
  comprovação for por pessoa física — cuidador/babá);
- dossiê do benefício (requerimento + certidões/guarda + declaração-modelo).

Fiéis aos modelos DOCX fornecidos pelo RH (Requerimento e Declaração da creche).
Reaproveitam o _OficioPDF (timbrado + parágrafos) das fichas."""

import io
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models.beneficio import BeneficioCreche
from app.models.candidato import Candidato, PostoServico
from app.services import storage
from app.services.dossie import _adicionar_em_a4
from app.services.fichas import _OficioPDF, _data_extenso

EMPRESA_RAZAO = "Green House Serviços de Locação de Mão de Obra Ltda."
EMPRESA_CNPJ = "12.531.678/0001-80"


def _parentesco_txt(p: str) -> str:
    return {"filho": "Filho(a)", "enteado": "Enteado(a)",
            "guarda": "Criança sob guarda judicial"}.get(p, p)


def gerar_requerimento_creche(db: Session, beneficio: BeneficioCreche,
                              vistos: list | None = None, sol=None,
                              base_url: str | None = None) -> bytes:
    """Requerimento de concessão do benefício, preenchido com os dados do
    colaborador e das crianças, com as cláusulas de declaração (a-e) da IN 147.

    Quando `vistos` é passado (assinatura pela plataforma), a linha de assinatura
    em papel dá lugar aos BLOCOS de assinatura eletrônica empilhados + o manifesto
    multi-assinante (mesmo pipeline dos demais documentos). Preserva o layout
    oficial do requerimento (decisão do Bruno: manter o PDF gerado + vistos)."""
    col = db.get(Candidato, beneficio.candidato_id)
    posto = db.get(PostoServico, col.posto_servico_id) if col.posto_servico_id else None
    tomador = (posto.razao_social or posto.nome) if posto else "-"
    contrato = (posto.contrato_ref if posto and posto.contrato_ref else "-")

    pdf = _OficioPDF("REQUERIMENTO - REEMBOLSO-CRECHE")
    pdf.set_y(46)

    pdf.set_font("helvetica", "B", 12)
    pdf.multi_cell(0, 6, "REQUERIMENTO DE CONCESSÃO DO BENEFÍCIO REEMBOLSO-CRECHE",
                   align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(3)

    # bloco de identificação (rótulo: valor)
    pdf.campo("Colaborador", col.nome_completo)
    pdf.campo("CPF", col.cpf or "-")
    pdf.campo("Empregadora", EMPRESA_RAZAO)
    pdf.campo("CNPJ Empregadora", EMPRESA_CNPJ)
    pdf.campo("Tomador dos serviços", tomador)
    pdf.campo("Nº do contrato", contrato)
    pdf.ln(3)

    pdf.paragrafo(
        "Venho, por meio deste, requerer a concessão do benefício de "
        "Reembolso-Creche, nos termos da Instrução Normativa SEGES/MGI nº 147, "
        "de 13 de abril de 2026.")
    pdf.paragrafo("Declaro possuir sob minha responsabilidade o(a)(s) seguinte(s) "
                  "dependente(s):")

    for c in beneficio.criancas:
        pdf.campo("Nome da Criança", c.nome)
        pdf.campo("Data de nascimento", c.data_nascimento)
        pdf.campo("Grau de parentesco", _parentesco_txt(c.parentesco))
        pdf.ln(1)

    pdf.ln(1)
    pdf.paragrafo(
        "Para fins de instrução do presente pedido, anexo a documentação "
        "comprobatória exigida.")
    pdf.paragrafo("Declaro, ainda, que:")

    clausulas = [
        "a) as informações prestadas são verdadeiras, comprometendo-me a "
        "comunicar imediatamente qualquer alteração que implique a perda ou "
        "modificação do direito ao benefício;",
        "b) não recebo benefício de valor igual, por força de convenção coletiva, "
        "acordo coletivo de trabalho ou sentença normativa;",
        "c) estou ciente de que meus dados pessoais e os do meu filho, enteado ou "
        "criança sob guarda judicial, conforme o caso, serão coletados e tratados "
        "para os fins de análise, concessão, manutenção e fiscalização do "
        "reembolso-creche;",
        "d) sou a mãe da criança, quando for o caso, tendo ciência de que a "
        "concessão do benefício para mim implica a inativação do mesmo benefício "
        "a eventual outro responsável que já o receba; e",
        "e) sou o pai ou responsável legal da criança, quando for o caso, e que: "
        "e.1) a mãe ou outro responsável não recebe o benefício previsto no art. "
        "3º, inciso III, do Decreto nº 12.174, de 2024, por força de contrato de "
        "prestação de serviços com regime de dedicação exclusiva de mão de obra "
        "firmado pela administração pública direta, autárquica e fundacional; e "
        "e.2) estou ciente de que a superveniente concessão do benefício previsto "
        "no art. 3º, inciso III, do Decreto nº 12.174, de 2024, para a mãe "
        "implicará na inativação deste mesmo benefício para mim.",
    ]
    for cl in clausulas:
        pdf.paragrafo(cl)

    pdf.ln(2)
    pdf.set_font("helvetica", "", 10.5)
    pdf.multi_cell(0, 6, _data_extenso(datetime.now(timezone.utc)), align="C",
                   new_x="LMARGIN", new_y="NEXT")
    pdf.ln(4)
    pdf.set_font("helvetica", "B", 9.5)
    pdf.cell(0, 6, "Documentos anexos:", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("helvetica", "", 9.5)
    for item in ("Cópia da certidão de nascimento do dependente;",
                 "Documento de guarda judicial (quando aplicável);",
                 "Demais documentos eventualmente solicitados pela empresa."):
        pdf.cell(0, 5.4, f"  -  {item}", new_x="LMARGIN", new_y="NEXT")

    if vistos:
        # assinatura eletrônica pela plataforma: blocos empilhados + manifesto
        from app.services.fichas import _bloco_visto, _pagina_manifesto_multi
        for v in vistos:
            _bloco_visto(pdf, v)
        titulo = "REQUERIMENTO - REEMBOLSO-CRECHE"
        _pagina_manifesto_multi(pdf, vistos, titulo,
                                str(sol.id) if sol is not None else "", base_url)
    else:
        # via em branco (prévia): linha de assinatura tradicional
        pdf.ln(8)
        pdf.set_font("helvetica", "", 10.5)
        pdf.cell(0, 6, "___________________________________________________",
                 align="C", new_x="LMARGIN", new_y="NEXT")
        pdf.cell(0, 6, "Assinatura do colaborador(a)", align="C",
                 new_x="LMARGIN", new_y="NEXT")

    return bytes(pdf.output())


def gerar_declaracao_modelo(db: Session, beneficio: BeneficioCreche) -> bytes:
    """Declaração-MODELO de despesa (Lei 14.457/2022, art. 2º, parágrafo único),
    a ser preenchida e assinada mensalmente pela pessoa que cuida da criança
    (quando a comprovação for por pessoa física). Campos em branco propositais."""
    pdf = _OficioPDF("DECLARAÇÃO - REEMBOLSO-CRECHE (MODELO)")
    pdf.set_y(48)

    pdf.set_font("helvetica", "B", 13)
    pdf.multi_cell(0, 8, "D E C L A R A Ç Ã O", align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(4)

    pdf.paragrafo(
        "Eu ______________________________, CPF nº ________________, Carteira de "
        "Identidade nº ________________, residente e domiciliada no(a) "
        "______________________________ CEP ______________, declaro para todos os "
        "fins necessários e, em conformidade com a Lei 14.457, de 21 de setembro "
        "de 2022, artigo 2º, parágrafo único, que mantenho sob meus cuidados em "
        "regime de creche, ______________________________, tendo essa criança como "
        "responsável legal o Sr.(a) ______________________________, CPF nº "
        "_______________, Carteira de Identidade nº _____________________.")
    pdf.paragrafo(
        "Declaro que pelos serviços por mim prestados, recebi o valor de "
        "R$ _______________ (______________________________________).")
    pdf.paragrafo(
        "Declaro, ainda, que sou responsável administrativa, civil e penalmente "
        "pela veracidade das informações aqui prestadas, ciente de que eventuais "
        "omissões ou declarações falsas poderão ensejar as sanções legais "
        "cabíveis.")
    pdf.paragrafo("Por ser verdade, firmo a presente declaração.")
    pdf.ln(4)
    pdf.cell(0, 6, "Brasília, DF, _______/_______/__________", align="C",
             new_x="LMARGIN", new_y="NEXT")
    pdf.ln(12)
    pdf.cell(0, 6, "_______________________________________________",
             align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 6, "Nome", align="C", new_x="LMARGIN", new_y="NEXT")

    return bytes(pdf.output())


def _anexo_como_pdf(key: str) -> bytes | None:
    """Baixa um anexo do storage e devolve-o como PDF (converte se for imagem)."""
    from pypdf import PdfReader  # validação
    from app.services.normalizacao import _imagem_para_pdf
    try:
        dados = storage.ler(key)
    except Exception:
        return None
    if not dados:
        return None
    ext = key.rsplit(".", 1)[-1].lower()
    if ext == "pdf":
        try:
            PdfReader(io.BytesIO(dados))  # confirma que é PDF legível
            return dados
        except Exception:
            return None
    # imagem -> PDF
    try:
        return _imagem_para_pdf(dados)
    except Exception:
        return None


def gerar_dossie_creche(db: Session, beneficio: BeneficioCreche) -> bytes:
    """Dossiê do benefício: requerimento preenchido + certidões e guardas das
    crianças + declaração-modelo. Todas as páginas padronizadas em A4."""
    from pypdf import PdfWriter

    writer = PdfWriter()
    _adicionar_em_a4(writer, gerar_requerimento_creche(db, beneficio))
    for c in beneficio.criancas:
        for key in (c.certidao_key, c.guarda_key):
            if key:
                pdf = _anexo_como_pdf(key)
                if pdf:
                    _adicionar_em_a4(writer, pdf)
    _adicionar_em_a4(writer, gerar_declaracao_modelo(db, beneficio))

    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()
