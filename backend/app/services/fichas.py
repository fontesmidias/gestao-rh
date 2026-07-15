"""Geração das 3 fichas em PDF (fpdf2 — puro Python, roda igual em qualquer ambiente).

Cada gerador recebe o candidato + entidades da ficha e devolve bytes de PDF.
Quando `assinatura` é passada, o rodapé ganha o bloco de assinatura eletrônica
com a trilha de evidências (Lei 14.063/2020).
"""

from datetime import date, datetime, timedelta, timezone

_TZ_BRASILIA = timezone(timedelta(hours=-3))

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
        self.ln(1)
        self.set_font("helvetica", "B", 10.5)
        self.set_fill_color(*AZUL)
        self.set_text_color(255, 255, 255)
        self.cell(190, 7, f"  {nome}", fill=True, new_x="LMARGIN", new_y="NEXT")
        self.set_text_color(30, 30, 30)

    def campo(self, rotulo: str, valor) -> None:
        """Linha de tabela com bordas: rótulo em célula sombreada + valor, como nos DOCX."""
        if valor is None or valor == "":
            valor = "-"
        if isinstance(valor, bool):
            valor = "Sim" if valor else "Não"
        if isinstance(valor, (date, datetime)):
            valor = valor.strftime("%d/%m/%Y")
        if hasattr(valor, "value"):
            valor = str(valor.value).replace("_", " ").title()
        valor = str(valor)

        self.set_font("helvetica", "", 9)
        largura_valor = 190 - 62
        linhas = max(1, len(self.multi_cell(largura_valor, 5.5, valor, dry_run=True,
                                            output="LINES")))
        altura = linhas * 5.5
        if self.get_y() + altura > self.h - 20:
            self.add_page()
        x, y = self.get_x(), self.get_y()
        self.set_font("helvetica", "B", 8.5)
        self.set_fill_color(238, 242, 232)
        self.cell(62, altura, f" {rotulo}", border=1, fill=True)
        self.set_font("helvetica", "", 9)
        self.set_xy(x + 62, y)
        self.multi_cell(largura_valor, 5.5, valor, border=1, new_x="LMARGIN", new_y="NEXT")
        self.set_y(max(self.get_y(), y + altura))

    def bloco_assinatura(self, assinatura: Assinatura, nome: str):
        self.ln(8)
        if self.get_y() > self.h - 55:
            self.add_page()
        self.set_draw_color(*AZUL)
        self.set_line_width(0.3)
        y = self.get_y()
        self.rect(10, y, 190, 34)
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
            f"Integridade (SHA-256 do documento sem este bloco): {assinatura.hash_sha256}\n"
            f"O manifesto completo de assinatura, com todas as evidências, está na última "
            f"página deste documento.",
        )

    def pagina_manifesto(self, assinatura: Assinatura, candidato, cpf: str | None,
                         base_url: str | None = None):
        """Última página do PDF assinado: todas as evidências da assinatura
        eletrônica simples (art. 4º, II, da Lei nº 14.063/2020)."""
        utc = assinatura.assinado_em
        brasilia = utc.astimezone(_TZ_BRASILIA)
        self.add_page()
        self.ln(2)
        self.set_font("helvetica", "B", 13)
        self.set_text_color(*AZUL)
        self.cell(0, 8, "MANIFESTO DE ASSINATURA ELETRÔNICA", align="C",
                  new_x="LMARGIN", new_y="NEXT")
        self.set_text_color(30, 30, 30)
        self.ln(3)

        self.secao("Documento")
        self.campo("Documento assinado", self.titulo)
        self.campo("Integridade (SHA-256)", assinatura.hash_sha256)
        self.campo("ID do registro de assinatura", str(assinatura.id))

        self.secao("Assinante")
        self.campo("Nome", candidato.nome_completo)
        self.campo("CPF", cpf)
        self.campo("E-mail verificado", candidato.email)

        self.secao("Evidências do ato")
        self.campo("Data e hora (Brasília)", brasilia.strftime("%d/%m/%Y %H:%M:%S (UTC-3)"))
        self.campo("Data e hora (UTC)", utc.strftime("%d/%m/%Y %H:%M:%S"))
        self.campo("Endereço IP", assinatura.ip)
        self.campo("Dispositivo (user-agent)", assinatura.user_agent)
        self.campo("Método", "Código de verificação numérico de uso único, enviado ao "
                             "e-mail do titular e validado nesta plataforma antes da "
                             "aposição da assinatura.")
        self.campo("Modalidade", "Assinatura eletrônica simples — art. 4º, I, da "
                                 "Lei nº 14.063/2020.")

        if base_url:
            url = f"{base_url}/verificar/{assinatura.id}"
            self.secao("Verificação de autenticidade")
            self.ln(2)
            try:
                import qrcode
                qr = qrcode.make(url, box_size=6, border=2)
                y_qr = self.get_y()
                self.image(qr.get_image(), x=14, y=y_qr, w=34, h=34)
                self.set_xy(54, y_qr + 4)
                self.set_font("helvetica", "", 9)
                self.multi_cell(
                    140, 5,
                    "Aponte a câmera do celular para o código ao lado, ou acesse o "
                    "endereço abaixo, para confirmar a validade e a integridade desta "
                    f"assinatura:\n{url}",
                )
                self.set_y(y_qr + 38)
            except Exception:
                self.set_font("helvetica", "", 9)
                self.multi_cell(190, 5, f"Confirme a validade desta assinatura em: {url}")

        self.ln(4)
        self.set_font("helvetica", "I", 8)
        self.multi_cell(
            190, 4.5,
            "O código SHA-256 acima é a impressão digital do conteúdo deste documento no "
            "momento da assinatura (calculado sobre o documento sem o bloco e sem este "
            "manifesto): qualquer alteração posterior ao conteúdo produz um código "
            "diferente, o que permite verificar a integridade da via. O registro completo "
            "do ato (solicitação do código, validação e assinatura) consta da trilha de "
            "auditoria do Portal de Admissão Green House sob o ID indicado acima.",
        )


def _nota(pdf: _FichaPDF, texto: str):
    pdf.set_font("helvetica", "I", 8)
    pdf.set_text_color(90, 90, 90)
    pdf.multi_cell(0, 4.5, texto)
    pdf.set_text_color(30, 30, 30)
    pdf.ln(1)


def _declaracao(pdf: _FichaPDF, titulo: str, texto: str, candidato: Candidato):
    pdf.ln(3)
    pdf.secao(titulo)
    pdf.set_font("helvetica", "", 9)
    pdf.multi_cell(0, 5, texto)
    pdf.ln(1)
    quando = (candidato.declaracao_veracidade_em.strftime("%d/%m/%Y %H:%M UTC")
              if candidato.declaracao_veracidade_em else "-")
    pdf.campo("Data/hora do preenchimento", quando)
    pdf.campo("Identificador da resposta", str(candidato.id))
    _nota(pdf, "Documento eletrônico gerado automaticamente pela Green House a partir do "
               "Formulário de Admissão preenchido pelo(a) colaborador(a). A autenticidade "
               "pode ser verificada pelo identificador da resposta acima.")


def _dump_pessoais(pdf: _FichaPDF, candidato: Candidato, p: DadosPessoais | None):
    pdf.secao("1. DADOS PESSOAIS")
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
                         assinatura: Assinatura | None = None,
                         base_url: str | None = None) -> bytes:
    p = db.get(DadosPessoais, candidato.id)
    e = db.get(Endereco, candidato.id)
    d = db.get(DocumentosIdentificacao, candidato.id)
    b = db.get(DadosProfissionaisBancarios, candidato.id)
    deps = db.scalars(select(Dependente).where(Dependente.candidato_id == candidato.id)).all()

    pdf = _FichaPDF("FICHA CADASTRAL DO COLABORADOR")
    _nota(pdf, "Documento gerado eletronicamente a partir do Formulário de Admissão Green House.")
    _dump_pessoais(pdf, candidato, p)
    if p:
        pdf.campo("Cor/raça (autodeclaração, IBGE)", p.cor_raca)

    pdf.ln(2); pdf.secao("2. ENDEREÇO")
    if e:
        pdf.campo("Endereço", e.logradouro_numero_complemento)
        pdf.campo("Bairro", e.bairro)
        pdf.campo("Cidade/UF", f"{e.cidade or '-'}/{e.uf or '-'}")
        pdf.campo("CEP", e.cep)

    pdf.ln(2); pdf.secao("3. DOCUMENTOS")
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

        _nota(pdf, "Observação: a CTPS é utilizada exclusivamente em meio digital "
                   "(Lei nº 13.874/2019). No formato digital, o número corresponde aos 7 "
                   "primeiros dígitos do CPF e a série aos 4 últimos.")

    pdf.ln(2); pdf.secao("4. UNIFORME")
    if b:
        pdf.campo("Tamanho (calça / camisa / calçado)",
                  f"{b.tamanho_calca or '-'} / {b.tamanho_camisa or '-'} / {b.tamanho_calcado or '-'}")

    pdf.ln(2); pdf.secao("5. DADOS BANCÁRIOS / CHAVE PIX (para pagamento do salário)")
    if b:
        pdf.campo("Banco", b.banco)
        pdf.campo("Tipo de chave PIX", b.pix_tipo)
        pdf.campo("Chave PIX", b.pix_chave)

    if deps:
        pdf.ln(2); pdf.secao("6. DEPENDENTES")
        for i, dep in enumerate(deps, 1):
            pdf.campo(f"Dependente {i}",
                      f"{dep.nome_completo} — {dep.data_nascimento.strftime('%d/%m/%Y')} — "
                      f"CPF {dep.cpf} — {dep.parentesco.value} — "
                      f"IRRF: {'sim' if dep.deduz_irrf else 'não'}")

    pdf.ln(2); pdf.secao("7. AUTORIZAÇÕES E TRATAMENTO DE DADOS")
    pdf.set_font("helvetica", "", 8)
    pdf.multi_cell(0, 4.5,
        "a) Autodeclaração de cor/raça — informação autodeclarada conforme a classificação do "
        "IBGE, em atendimento ao eSocial.\n"
        "b) Dependentes para o IRRF — declaro que os dependentes indicados atendem às condições "
        "da Lei nº 9.250/1995 e da legislação vigente da Receita Federal.\n"
        "c) Proteção de dados (LGPD — Lei nº 13.709/2018). A Green House Serviços de Locação de "
        "Mão de Obra Ltda. (CNPJ 12.531.678/0001-80), controladora, trata os dados para admissão "
        "e cumprimento de obrigações trabalhistas, previdenciárias, fiscais e regulatórias "
        "(art. 7º, II, V e VI). Dados sensíveis (cor/raça e saúde) são tratados para cumprimento "
        "de obrigação legal e proteção da vida e da incolumidade física do titular (art. 11, II, "
        "'a' e 'e'). O titular pode exercer os direitos do art. 18 da LGPD.")

    cpf = d.cpf if d else "-"
    _declaracao(
        pdf, "8. DECLARAÇÃO ELETRÔNICA DE PREENCHIMENTO E RESPONSABILIDADE",
        f"Eu, {candidato.nome_completo}, inscrito(a) no CPF nº {cpf}, declaro que preenchi "
        "pessoalmente o Formulário de Admissão da Green House e que todas as informações "
        "constantes neste documento são verdadeiras, completas, atuais e de minha inteira "
        "responsabilidade. Declaro estar ciente das sanções aplicáveis em caso de declaração "
        "falsa ou omissão, em especial o art. 299 do Código Penal (falsidade ideológica) e o "
        "parágrafo único do art. 10 do Decreto nº 83.936/1979, comprometendo-me a comunicar à "
        "empresa qualquer alteração dos dados aqui informados.",
        candidato,
    )

    if assinatura:
        pdf.bloco_assinatura(assinatura, candidato.nome_completo)
        pdf.pagina_manifesto(assinatura, candidato, cpf, base_url)
    return bytes(pdf.output())


def gerar_ficha_emergencia(db: Session, candidato: Candidato,
                           assinatura: Assinatura | None = None,
                           base_url: str | None = None) -> bytes:
    p = db.get(DadosPessoais, candidato.id)
    fe = db.get(FichaEmergencia, candidato.id)
    contatos = db.scalars(
        select(ContatoEmergencia)
        .where(ContatoEmergencia.candidato_id == candidato.id)
        .order_by(ContatoEmergencia.ordem)
    ).all()

    d = db.get(DocumentosIdentificacao, candidato.id)
    e = db.get(Endereco, candidato.id)

    pdf = _FichaPDF("FICHA DE EMERGÊNCIA DO COLABORADOR")
    _nota(pdf, "Documento gerado eletronicamente a partir do Formulário de Admissão Green House.")
    pdf.secao("1. DADOS DO COLABORADOR")
    pdf.campo("Nome completo", candidato.nome_completo)
    if p:
        pdf.campo("Data de nascimento", p.data_nascimento)
        pdf.campo("Pessoa com Deficiência (PCD)", p.pcd)
    if d:
        pdf.campo("CPF", d.cpf)
        pdf.campo("RG", d.rg_numero)
    if e:
        pdf.campo("Endereço residencial", e.logradouro_numero_complemento)
        pdf.campo("Cidade/UF — CEP", f"{e.cidade or '-'}/{e.uf or '-'} — {e.cep or '-'}")
    pdf.campo("Celular / WhatsApp", candidato.celular_whatsapp)
    pdf.campo("E-mail", candidato.email)

    pdf.ln(2); pdf.secao("2. INFORMAÇÕES DE SAÚDE")
    if fe:
        pdf.campo("Tipo sanguíneo", fe.tipo_sanguineo)
        pdf.campo("Uso contínuo de medicamentos?", fe.usa_medicamento_continuo)
        pdf.campo("Quais medicamentos", fe.medicamentos)
        pdf.campo("Condições médicas importantes", fe.condicoes_medicas)

    for c in contatos:
        pdf.ln(2); pdf.secao(f"{2 + c.ordem}. CONTATO DE EMERGÊNCIA {c.ordem}")
        pdf.campo("Nome", c.nome_completo)
        pdf.campo("Grau de parentesco", c.parentesco)
        pdf.campo("Telefone celular", c.telefone_celular)
        pdf.campo("Telefone fixo / Endereço", c.telefone_fixo_endereco)

    pdf.ln(2); pdf.secao("5. ORIENTAÇÕES ADICIONAIS")
    pdf.campo("Orientação específica em caso de emergência",
              fe.orientacao_emergencia if fe else None)

    cpf = d.cpf if d else "-"
    _declaracao(
        pdf, "6. DECLARAÇÃO ELETRÔNICA E AUTORIZAÇÃO",
        f"Eu, {candidato.nome_completo}, inscrito(a) no CPF nº {cpf}, declaro que preenchi "
        "pessoalmente estas informações, que são verdadeiras e de minha responsabilidade, e "
        "autorizo a Green House a utilizá-las exclusivamente em situações de emergência. "
        "Os dados de saúde aqui informados constituem dados pessoais sensíveis e são tratados "
        "para a proteção da vida e da incolumidade física do titular e para o cumprimento de "
        "obrigação legal, nos termos do art. 11, II, alíneas 'a' e 'e' da Lei nº 13.709/2018 "
        "(LGPD).",
        candidato,
    )
    if assinatura:
        pdf.bloco_assinatura(assinatura, candidato.nome_completo)
        pdf.pagina_manifesto(assinatura, candidato, cpf, base_url)
    return bytes(pdf.output())


def gerar_termo_vt(db: Session, candidato: Candidato,
                   assinatura: Assinatura | None = None,
                   base_url: str | None = None) -> bytes:
    d = db.get(DocumentosIdentificacao, candidato.id)
    vt = db.get(ValeTransporte, candidato.id)

    e = db.get(Endereco, candidato.id)

    pdf = _FichaPDF("DECLARAÇÃO DE OPÇÃO PELO VALE-TRANSPORTE (VT)")
    pdf.set_font("helvetica", "", 10)
    optante = bool(vt and vt.optante)
    cpf = d.cpf if d else "-"
    pdf.multi_cell(
        0, 6,
        f"EU, {candidato.nome_completo}, inscrito(a) no CPF sob o nº {cpf}, DECLARO, para os "
        f"devidos fins, quanto ao Vale-Transporte (VT), que "
        + ("OPTO por receber o Vale-Transporte." if optante
           else "NÃO OPTO por receber o Vale-Transporte, estando ciente de que poderei "
                "solicitá-lo posteriormente mediante nova declaração."),
    )
    pdf.ln(3)
    if optante and vt:
        pdf.secao("Dados do optante")
        if e:
            pdf.campo("Endereço residencial",
                      f"{e.logradouro_numero_complemento or '-'}, {e.bairro or '-'}, "
                      f"{e.cidade or '-'}/{e.uf or '-'} — CEP {e.cep or '-'}")
        pdf.campo("Número do cartão DFTrans (de sua titularidade)", vt.cartao_dftrans)
        pdf.campo("Percurso (ida e volta) — linhas, empresas e valores", vt.trajeto_descricao)
        pdf.ln(2)

    pdf.secao("DECLARO AINDA QUE:")
    pdf.set_font("helvetica", "", 8)
    pdf.multi_cell(0, 4.5,
        "a) caso OPTE por receber o vale-transporte, AUTORIZO expressamente o desconto mensal, "
        "em folha de pagamento, do valor equivalente a 6% do meu salário básico, nos termos do "
        "art. 4º da Lei nº 7.418/1985 e do art. 9º do Decreto nº 95.247/1987;\n"
        "b) resido no endereço acima informado, assumindo inteira responsabilidade pela "
        "veracidade das informações declaradas;\n"
        "c) estou ciente de que a declaração falsa ou o uso indevido do vale-transporte "
        "constituem falta grave, sujeita às medidas disciplinares cabíveis (art. 7º, §3º, do "
        "Decreto nº 95.247/1987);\n"
        "d) esta declaração substitui as anteriormente formalizadas, quando se tratar de "
        "atualização.")
    pdf.ln(2)
    quando = (candidato.declaracao_veracidade_em.strftime("%d/%m/%Y")
              if candidato.declaracao_veracidade_em else "")
    pdf.set_font("helvetica", "", 10)
    pdf.multi_cell(0, 6, f"Brasília - DF, {quando}.")

    if assinatura:
        pdf.bloco_assinatura(assinatura, candidato.nome_completo)
        pdf.pagina_manifesto(assinatura, candidato, cpf, base_url)
    return bytes(pdf.output())


GERADORES = {
    "ficha_cadastro": gerar_ficha_cadastro,
    "ficha_emergencia": gerar_ficha_emergencia,
    "termo_vt": gerar_termo_vt,
}
