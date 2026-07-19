"""Geração das 3 fichas em PDF (fpdf2 — puro Python, roda igual em qualquer ambiente).

Cada gerador recebe o candidato + entidades da ficha e devolve bytes de PDF.
Quando `assinatura` é passada, o rodapé ganha o bloco de assinatura eletrônica
com a trilha de evidências (Lei 14.063/2020).
"""

import re
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

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
        # 26 de margem inferior: o rodapé timbrado ocupa os últimos ~23 mm.
        self.set_auto_page_break(auto=True, margin=26)
        self.add_page()

    def header(self):
        _desenhar_marca_dagua(self)
        try:
            # Papel timbrado oficial: arte alinhada à direita, título do
            # documento estritamente centralizado na página (pedido do RH).
            self.image(TIMBRADO_TOPO, x=self.w - 34, y=0, w=34)
            self.set_y(9)
            self.set_font("helvetica", "B", 12)
            self.set_text_color(*AZUL)
            self.set_x(0)
            self.cell(self.w, 8, self.titulo, align="C", new_x="LMARGIN", new_y="NEXT")
            self.set_y(28)
        except Exception:
            self.set_font("helvetica", "B", 14)
            self.set_text_color(*AZUL)
            self.cell(0, 8, "GREEN HOUSE", align="L")
            self.set_font("helvetica", "B", 12)
            self.cell(0, 8, self.titulo, align="R", new_x="LMARGIN", new_y="NEXT")
            self.set_draw_color(*VERDE)
            self.set_line_width(0.8)
            self.line(10, self.get_y() + 1, 200, self.get_y() + 1)
            self.ln(6)
        self.set_text_color(30, 30, 30)

    def footer(self):
        try:
            self.image(TIMBRADO_RODAPE, x=0, y=self.h - 23, w=210)
        except Exception:
            pass  # sem arte, sem rodapé — o conteúdo não depende dele

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

        largura_valor = 190 - 62
        self.set_font("helvetica", "", 9)
        linhas_v = max(1, len(self.multi_cell(largura_valor - 2, 5.5, valor, dry_run=True,
                                              output="LINES")))
        # O rótulo também precisa quebrar linha: nomes longos ("Número do cartão
        # DFTrans (de sua titularidade)") não podem invadir a célula do valor.
        self.set_font("helvetica", "B", 8.5)
        linhas_r = max(1, len(self.multi_cell(60, 4.4, rotulo, dry_run=True,
                                              output="LINES")))
        altura = max(linhas_v * 5.5, linhas_r * 4.4, 5.5)
        if self.get_y() + altura > self.h - 26:
            self.add_page()
        x, y = self.get_x(), self.get_y()
        self.set_fill_color(238, 242, 232)
        self.rect(x, y, 62, altura, style="DF")
        self.rect(x + 62, y, largura_valor, altura)
        self.set_font("helvetica", "B", 8.5)
        self.set_xy(x + 1, y + (altura - linhas_r * 4.4) / 2)
        self.multi_cell(60, 4.4, rotulo)
        self.set_font("helvetica", "", 9)
        self.set_xy(x + 62 + 1, y + (altura - linhas_v * 5.5) / 2)
        self.multi_cell(largura_valor - 2, 5.5, valor)
        self.set_xy(x, y + altura)

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
        papel = f", na qualidade de {assinatura.papel}" if assinatura.papel else ""
        self.multi_cell(
            182, 4.5,
            f"Assinado por {nome}{papel} em {quando}, mediante código de verificação enviado ao "
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
        if assinatura.papel:
            self.campo("Assina na qualidade de", assinatura.papel)
        self.campo("CPF", cpf)
        self.campo("E-mail verificado", candidato.email or "—")

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
    if p and p.nome_social:
        pdf.campo("Nome social", p.nome_social)
    if p:
        pdf.campo("Filiação (mãe)", p.nome_mae)
        pdf.campo("Filiação (pai)", p.nome_pai or "Não declarado")
        pdf.campo("Data de nascimento", p.data_nascimento)
        pdf.campo("Sexo", p.sexo)
        pdf.campo("Identidade de gênero", p.identidade_genero)
        pdf.campo("Nacionalidade", p.nacionalidade)
        pdf.campo("Naturalidade", f"{p.naturalidade_cidade or '-'}/{p.naturalidade_uf or '-'}")
        pdf.campo("Estado civil", p.estado_civil)
        pdf.campo("Escolaridade", p.escolaridade)
        pdf.campo("PCD", p.pcd)
    pdf.campo("E-mail", candidato.email or "-")
    pdf.campo("Celular/WhatsApp", candidato.celular_whatsapp or "-")


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

    contrato, cargo = _dados_posto(db, candidato)
    if (candidato.posto_servico_id or candidato.cargo_funcao
            or candidato.salario_base or candidato.adicionais):
        pdf.ln(2); pdf.secao("1.1 CARGO E REMUNERAÇÃO")
        pdf.campo("Posto de serviço / contrato", contrato)
        pdf.campo("Cargo / função", cargo)
        pdf.campo("Salário base", candidato.salario_base)
        for ad in (candidato.adicionais or []):
            sufixo = "%" if ad.get("tipo") == "percentual" else ""
            prefixo = "" if ad.get("tipo") == "percentual" else "R$ "
            pdf.campo(f"Adicional — {ad.get('nome', '-')}",
                      f"{prefixo}{ad.get('valor', '-')}{sufixo}")

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
            pdf.campo("CNH — nº de registro", f"{d.cnh_numero} (cat. {d.cnh_categoria or '-'})")
            pdf.campo("CNH — órgão emissor / UF",
                      f"{d.cnh_orgao_emissor or '-'} / {d.cnh_uf or '-'}")
            pdf.campo("CNH — emissão", d.cnh_data_emissao)
            pdf.campo("CNH — validade", d.cnh_validade)
            pdf.campo("CNH — 1ª habilitação", d.cnh_primeira_habilitacao)
        if d.militar_numero or d.militar_tipo:
            tipos = {"reservista": "Certificado de Reservista",
                     "alistamento": "Certificado de Alistamento Militar (CAM)",
                     "dispensa": "Certificado de Dispensa de Incorporação (CDI)"}
            pdf.campo("Situação militar — documento",
                      tipos.get(d.militar_tipo or "", d.militar_tipo or "-"))
            pdf.campo("Situação militar — nº / série (RA)",
                      f"{d.militar_numero or '-'} / {d.militar_serie or '-'}")
            pdf.campo("Situação militar — categoria", d.militar_categoria)
            pdf.campo("Situação militar — órgão expedidor", d.militar_orgao)
            pdf.campo("Situação militar — data de expedição", d.militar_data_emissao)
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

    pdf.ln(2); pdf.secao("6. DEPENDENTES")
    if deps:
        for i, dep in enumerate(deps, 1):
            pdf.campo(f"Dependente {i}",
                      f"{dep.nome_completo} — {dep.data_nascimento.strftime('%d/%m/%Y')} — "
                      f"CPF {dep.cpf} — {dep.parentesco.value} — "
                      f"IRRF: {'sim' if dep.deduz_irrf else 'não'}")
    else:
        pdf.set_font("helvetica", "", 9)
        pdf.multi_cell(0, 5.5,
                       "O(a) colaborador(a) DECLARA NÃO POSSUIR DEPENDENTES, comprometendo-se a "
                       "comunicar à empresa qualquer alteração nessa condição.")

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
    pdf.campo("Celular / WhatsApp", candidato.celular_whatsapp or "-")
    pdf.campo("E-mail", candidato.email or "-")

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


# ============================================================
# Documentos por posto de serviço (layout de ofício oficial)
# ============================================================

# Dados institucionais dos documentos oficiais. São o VALOR-PADRÃO; o painel
# (Configurações → Identidade visual) pode sobrepô-los pela config dinâmica.
# `aplicar_marca(db)` sincroniza estas globais com o que o RH salvou, e é
# chamada no início de cada geração de PDF.
EMPRESA_RAZAO = "GREEN HOUSE SERVIÇOS DE LOCAÇÃO DE MÃO DE OBRA LTDA"
EMPRESA_CNPJ = "12.531.678/0001-80"
EMPRESA_RODAPE = ("SCIA Quadra 15, Conjunto 13, Lote 8, Zona Industrial (Guará), "
                  "Brasília, DF, CEP: 71.250-015\n"
                  "+55 61 3346-8812 | www.greenhousedf.com.br")


def aplicar_marca(db) -> None:
    """Atualiza as globais EMPRESA_* com os dados salvos pelo RH (ou mantém os
    padrões). Chamada no começo de cada gerador de PDF."""
    global EMPRESA_RAZAO, EMPRESA_CNPJ, EMPRESA_RODAPE
    try:
        from app.services.marca import dados_empresa
        d = dados_empresa(db)
        EMPRESA_RAZAO = d["empresa_razao"]
        EMPRESA_CNPJ = d["empresa_cnpj"]
        EMPRESA_RODAPE = f"{d['empresa_endereco']}\n{d['empresa_contato']}"
    except Exception:
        pass  # config indisponível: mantém os padrões
# Assinantes-padrão; podem ser trocados pelo painel (Configurações → Assinantes).
EMPRESA_ASSINANTES = (("Leandro de Sá", "CEO", "026.030.441-76"),
                      ("Láysa Beatriz", "Assistente de RH", "113.900.916-86"))
NAVY = (23, 26, 60)
_ASSETS = Path(__file__).resolve().parent.parent / "assets"
LOGO = str(_ASSETS / "logo.png")
# Papel timbrado oficial (artes extraídas do modelo Word da empresa).
TIMBRADO_TOPO = str(_ASSETS / "timbrado-topo.png")       # canto sup. esquerdo
TIMBRADO_RODAPE = str(_ASSETS / "timbrado-rodape.jpg")   # rodapé institucional
TIMBRADO_MARCA = str(_ASSETS / "timbrado-marca.png")     # marca d'água vertical (borda direita)
_MARCA_RAZAO = 662 / 296                                 # altura/largura da arte


def _desenhar_marca_dagua(pdf) -> None:
    """Marca d'água "GREENHOUSE" (esmaecida) rente à borda direita, como no
    modelo Word. Desenhada no header (antes do conteúdo) para ficar ao fundo."""
    try:
        larg = 104  # mm — a arte tem a esquerda transparente, então a marca
        alt = larg * _MARCA_RAZAO      # visível fica junto à borda direita
        y = (pdf.h - alt) / 2          # centralizada na vertical
        pdf.image(TIMBRADO_MARCA, x=pdf.w - larg, y=y, w=larg)
    except Exception:
        pass  # sem a arte, o documento continua válido


def assinantes_config(db: Session) -> list[tuple[str, str, str]]:
    """Assinantes dos documentos oficiais: config do painel ou o padrão."""
    from app.services.config_dinamica import ler_config
    cfg = ler_config(db, ("doc_ass1_nome", "doc_ass1_cargo", "doc_ass1_cpf",
                          "doc_ass2_nome", "doc_ass2_cargo", "doc_ass2_cpf"))
    saida = []
    for i, padrao in enumerate(EMPRESA_ASSINANTES, start=1):
        nome = cfg.get(f"doc_ass{i}_nome", "")
        saida.append((nome or padrao[0],
                      cfg.get(f"doc_ass{i}_cargo", "") or padrao[1],
                      cfg.get(f"doc_ass{i}_cpf", "") or padrao[2]))
    return saida


class _OficioPDF(_FichaPDF):
    """Papel timbrado oficial da empresa: arte do canto superior esquerdo e
    rodapé institucional completos, extraídos do modelo Word do timbrado."""

    def header(self):
        _desenhar_marca_dagua(self)
        try:
            # Arte de canto sangrada na borda direita (984×724 px ≈ 1,36).
            self.image(TIMBRADO_TOPO, x=self.w - 52, y=0, w=52)
        except Exception:
            self.set_fill_color(*NAVY)
            self.rect(0, 0, 60, 24, style="F")
            self.set_xy(2, 8)
            self.set_font("helvetica", "B", 13)
            self.set_text_color(255, 255, 255)
            self.cell(56, 8, "GREENHOUSE", align="C")
            self.set_text_color(30, 30, 30)
        self.set_y(42)

    def footer(self):
        try:
            # Rodapé oficial em largura total (2234×244 px ≈ proporção 9,16).
            self.image(TIMBRADO_RODAPE, x=0, y=self.h - 23, w=210)
        except Exception:
            self.set_y(-24)
            self.set_draw_color(*VERDE)
            self.set_line_width(0.6)
            self.line(60, self.get_y(), 200, self.get_y())
            self.set_font("helvetica", "", 7.5)
            self.set_text_color(90, 100, 92)
            self.multi_cell(120, 3.6, EMPRESA_RODAPE)
            self.set_text_color(30, 30, 30)

    def paragrafo(self, texto: str, negrito_inicio: str | None = None):
        self.set_font("helvetica", "", 10.5)
        self.multi_cell(0, 5.6, texto)
        self.ln(2.5)

    def assinantes_empresa(self, assinantes=EMPRESA_ASSINANTES):
        self.ln(4)
        self.set_font("helvetica", "", 10.5)
        self.cell(0, 6, "Atenciosamente,", align="C", new_x="LMARGIN", new_y="NEXT")
        self.ln(2)
        self.set_font("helvetica", "B", 10.5)
        self.cell(0, 6, f"{EMPRESA_RAZAO}.", align="C", new_x="LMARGIN", new_y="NEXT")
        self.ln(1)
        y = self.get_y()
        self.set_font("helvetica", "", 10)
        for i, (nome, cargo, cpf) in enumerate(assinantes):
            x = 20 + i * 90
            self.set_xy(x, y)
            self.multi_cell(80, 5.4, f"{nome}\n{cargo}\nCPF: {cpf}", align="C")
        self.set_y(y + 20)


def _dados_posto(db: Session, candidato: Candidato) -> tuple[str, str]:
    """(contrato_ref, cargo_funcao) do candidato — '-' quando não definidos."""
    from app.models.candidato import PostoServico
    posto = db.get(PostoServico, candidato.posto_servico_id) \
        if candidato.posto_servico_id else None
    contrato = (posto.contrato_ref if posto and posto.contrato_ref else "-")
    return contrato, candidato.cargo_funcao or "-"


_MESES_PT = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho",
             "agosto", "setembro", "outubro", "novembro", "dezembro"]


def _data_extenso(d) -> str:
    return f"Brasília, DF, {d.day:02d} de {_MESES_PT[d.month - 1]} de {d.year}."


def gerar_oficio_cartao_cidadao(db: Session, candidato: Candidato,
                                assinatura: Assinatura | None = None,
                                base_url: str | None = None) -> bytes:
    contrato, cargo = _dados_posto(db, candidato)
    d = db.get(DocumentosIdentificacao, candidato.id)
    quando = (assinatura.assinado_em.date() if assinatura and assinatura.assinado_em
              else date.today())

    pdf = _OficioPDF("Ofício - Cartão Cidadão")
    pdf.set_font("helvetica", "", 10.5)
    pdf.cell(0, 6, _data_extenso(quando), align="R", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(4)
    pdf.multi_cell(0, 5.6,
                   "Á\nEMPRESA BRASILEIRA DE INFRAESTRUTURA AEROPORTUÁRIA - INFRAERO\n"
                   "Setor Bancário Norte Quadra 1 Bloco F Edifício Palácio da Agricultura "
                   "19º - Asa Norte, Brasília - DF\n"
                   "A/C da Coordenação de Fiscalização Documental de Contratos "
                   "Contínuos - ADCC-03")
    pdf.ln(3)
    pdf.set_font("helvetica", "B", 10.5)
    pdf.multi_cell(0, 5.6, "Assunto: Fornecimento de cartão cidadão e senha ao extrato "
                           f"do INSS\nReferência: Contrato Administrativo nº {contrato}")
    pdf.ln(3)
    pdf.paragrafo(f"1. {EMPRESA_RAZAO}, situada no endereço do rodapé, inscrita no "
                  f"CNPJ/MF sob o nº {EMPRESA_CNPJ}, por seu representante legal e "
                  "assistente de faturamento ao final subscritos e identificados, vem "
                  "expor o que se segue.")
    pdf.paragrafo("2. Em atenção às exigências contratuais sobre fornecimento de cartão "
                  "cidadão e acessos aos extratos das informações previdenciárias, segue "
                  "abaixo relação de todos os empregados alocados na prestação de "
                  "serviços na(s) dependência(s) da Infraero - Empresa Brasileira de "
                  "Infraestrutura Aeroportuária e as respectivas assinaturas individuais "
                  "declarando, neste ato, que possuem acesso aos extratos de informações "
                  "do FGTS e INSS.")

    # Tabela: nome / cargo / assinatura
    pdf.ln(1)
    pdf.set_font("helvetica", "B", 9.5)
    for larg, txt in ((70, "NOME DO EMPREGADO"), (50, "CARGO/FUNÇÃO"), (70, "ASSINATURA")):
        pdf.cell(larg, 8, f" {txt}", border=1)
    pdf.ln(8)
    pdf.set_font("helvetica", "", 9.5)
    situacao = ("Assinado eletronicamente\n(Lei nº 14.063/2020 - ver manifesto)"
                if assinatura and assinatura.assinado_em else "")
    p = db.get(DadosPessoais, candidato.id)
    nome_social = f"\n(NOME SOCIAL: {p.nome_social.upper()})" if p and p.nome_social else ""
    y = pdf.get_y()
    pdf.multi_cell(70, 6, f"{candidato.nome_completo}{nome_social}"
                          + (f"\nCPF: {d.cpf}" if d and d.cpf else ""), border=1)
    alto = max(pdf.get_y() - y, 12)
    pdf.set_xy(80, y)
    pdf.multi_cell(50, alto / 2 if situacao else alto, cargo, border=1)
    pdf.set_xy(130, y)
    pdf.multi_cell(70, alto / 2, situacao or " ", border=1)
    pdf.set_y(y + alto)
    pdf.ln(3)

    pdf.paragrafo(f"3. Por fim, a GREEN HOUSE reafirma o seu compromisso perante este "
                  "Contratante, bem como votos de estima e consideração.")
    pdf.assinantes_empresa(assinantes_config(db))

    if assinatura:
        pdf.bloco_assinatura(assinatura, candidato.nome_completo)
        pdf.pagina_manifesto(assinatura, candidato, d.cpf if d else None, base_url)
    return bytes(pdf.output())


def gerar_informacoes_trabalhador(db: Session, candidato: Candidato,
                                  assinatura: Assinatura | None = None,
                                  base_url: str | None = None) -> bytes:
    contrato, _cargo = _dados_posto(db, candidato)
    d = db.get(DocumentosIdentificacao, candidato.id)
    quando = (assinatura.assinado_em.date() if assinatura and assinatura.assinado_em
              else date.today())

    pdf = _OficioPDF("Informações ao Trabalhador")
    pdf.set_font("helvetica", "B", 12)
    pdf.cell(0, 7, "INFORMAÇÕES AO TRABALHADOR", align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(2)
    pdf.set_font("helvetica", "B", 10.5)
    pdf.cell(0, 6, f"Contrato Administrativo nº {contrato}", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(3)
    pdf.paragrafo(f"1. {EMPRESA_RAZAO}, situada no endereço do rodapé, inscrita no "
                  f"CNPJ/MF sob o nº {EMPRESA_CNPJ}, doravante denominada GREEN HOUSE, "
                  "por seus representantes legais, ao final subscritos e identificados, "
                  "vem expor o que se segue.")
    pdf.paragrafo("2. A GREEN HOUSE informa que os trabalhadores desta empresa possuem "
                  "direitos garantidos pela Constituição Federal, pela Consolidação das "
                  "Leis Trabalhistas (CLT) e pelas Convenções/Acordos Coletivos de "
                  "Trabalho. Assim, listamos abaixo alguns desses direitos:")
    direitos = [
        "a) Carteira de trabalho assinada desde o primeiro dia de serviço;",
        "b) Repouso semanal remunerado (1 folga por semana);",
        "c) Salário pago até o 5º (quinto) dia útil do mês subsequente à prestação "
        "do serviço;",
        "d) 13º salário;",
        "e) Férias de 30 (trinta) dias com acréscimo de 1/3 do salário;",
        "f) Vale Transporte com desconto máximo de 6% do salário;",
        "g) FGTS: depósito de 8% (oito por cento) do salário em conta bancária a favor "
        "do empregado. Dirija-se a uma Agência da Caixa Econômica Federal e solicite o "
        "extrato de contas vinculadas ao FGTS;",
        "h) Horas Extras compensadas em banco de horas;",
        "i) Indenizações pertinentes (verbas rescisórias), em caso de demissão;",
        "j) Recolhimento da Contribuição Previdenciária (INSS): dirija-se a uma Agência "
        "da Previdência Social e solicite o extrato de contribuições relativas ao seu "
        "NIT/PIS/PASEP.",
    ]
    pdf.set_font("helvetica", "", 10.5)
    for item in direitos:
        pdf.set_x(18)
        pdf.multi_cell(182, 5.6, item)
        pdf.ln(1)
    pdf.ln(1)
    pdf.paragrafo("3. Informa, ainda, que a Infraero disponibiliza aos trabalhadores de "
                  "empresas contratadas um canal para registro de reclamações (Ouvidoria "
                  "Interna) relativas às questões trabalhistas decorrentes da prestação "
                  "de seus serviços para a execução do contrato firmado entre o "
                  "RESPONSÁVEL e esta empresa ou denúncias de desvios comportamentais "
                  "como assédio moral e sexual. Sua mensagem pode ser enviada pelo "
                  "seguinte canal: terceirizados@infraero.gov.br")
    pdf.set_font("helvetica", "", 10.5)
    pdf.cell(0, 6, _data_extenso(quando), new_x="LMARGIN", new_y="NEXT")
    pdf.assinantes_empresa(assinantes_config(db))
    pdf.ln(2)
    pdf.set_font("helvetica", "", 10.5)
    pdf.cell(0, 6, f"Trabalhador ciente em: {quando.strftime('%d/%m/%Y')}",
             new_x="LMARGIN", new_y="NEXT")
    pdf.ln(4)
    if assinatura and assinatura.assinado_em:
        pdf.set_font("helvetica", "I", 10.5)
        pdf.cell(0, 6, f"{candidato.nome_completo} - assinado eletronicamente",
                 new_x="LMARGIN", new_y="NEXT")
    else:
        pdf.cell(0, 6, "_" * 60, new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("helvetica", "B", 9.5)
    pdf.cell(0, 6, "ASSINATURA DO TRABALHADOR", new_x="LMARGIN", new_y="NEXT")

    if assinatura:
        pdf.bloco_assinatura(assinatura, candidato.nome_completo)
        pdf.pagina_manifesto(assinatura, candidato, d.cpf if d else None, base_url)
    return bytes(pdf.output())


def gerar_termo_lgpd_infraero(db: Session, candidato: Candidato,
                              assinatura: Assinatura | None = None,
                              base_url: str | None = None) -> bytes:
    """Anexo 04 — Termo de consentimento LGPD do sistema de credenciamento
    (INFRAERO). Texto fiel ao modelo oficial, com nome/CPF preenchidos."""
    d = db.get(DocumentosIdentificacao, candidato.id)
    quando = (assinatura.assinado_em.date() if assinatura and assinatura.assinado_em
              else date.today())

    pdf = _OficioPDF("Termo de Consentimento - LGPD")
    pdf.ln(4)
    pdf.set_font("helvetica", "B", 12)
    pdf.cell(0, 7, "TERMO DE CONSENTIMENTO PARA TRATAMENTO DE DADOS PESSOAIS",
             align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 7, "SISTEMA DE CREDENCIAMENTO", align="C",
             new_x="LMARGIN", new_y="NEXT")
    pdf.ln(6)
    p = db.get(DadosPessoais, candidato.id)
    nome_social = f" (nome social: {p.nome_social})" if p and p.nome_social else ""
    cpf_txt = (f"{d.cpf[:3]}.{d.cpf[3:6]}.{d.cpf[6:9]}-{d.cpf[9:]}"
               if d and d.cpf and len(d.cpf) == 11 else "____________________")
    pdf.set_font("helvetica", "", 11)
    pdf.multi_cell(0, 6.4,
                   f"Eu, {candidato.nome_completo}{nome_social}, CPF {cpf_txt}, "
                   "AUTORIZO, de forma livre, informada e inequívoca, o tratamento dos "
                   "meus dados pessoais contidos no formulário de solicitação de "
                   "credenciais e em sua documentação anexa, em conformidade com a "
                   "Lei nº 13.709/2018 - Lei Geral de Proteção de Dados Pessoais (LGPD).")
    pdf.ln(6)
    pdf.cell(0, 6, f"Brasília, {quando.strftime('%d/%m/%Y')}.",
             new_x="LMARGIN", new_y="NEXT")
    pdf.ln(8)
    if assinatura and assinatura.assinado_em:
        pdf.set_font("helvetica", "I", 11)
        pdf.cell(0, 6, f"Assinatura: {candidato.nome_completo} - assinado eletronicamente",
                 new_x="LMARGIN", new_y="NEXT")
    else:
        pdf.cell(0, 6, "Assinatura: " + "_" * 56, new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("helvetica", "", 9.5)
    pdf.cell(0, 6, f"[{candidato.nome_completo}]", new_x="LMARGIN", new_y="NEXT")

    if assinatura:
        pdf.bloco_assinatura(assinatura, candidato.nome_completo)
        pdf.pagina_manifesto(assinatura, candidato, d.cpf if d else None, base_url)
    return bytes(pdf.output())


EMPRESA_ENDERECO = ("SCIA, Quadra 15, Conjunto 13, Lote 8, Zona Industrial (Guará), "
                    "Brasília/DF, CEP 71.250-015")

# Cláusulas do Acordo de Confidencialidade — texto do modelo oficial, com a
# gramática revisada (concordância de "os DADOS" no plural, "resultará",
# vírgulas) e a qualificação da empresa unificada com o endereço do rodapé.
_ACORDO_CLAUSULAS = (
    ("DEFINIÇÕES",
     ["Para os efeitos do presente ACORDO, serão adotadas as seguintes definições:",
      '"DADOS": toda e qualquer informação, veiculada sob qualquer forma, escrita ou '
      'verbal, tangível ou intangível (como, por exemplo, mas não se limitando a estes '
      'significados: descobertas, ideias, conceitos, know-how, técnicas, desenhos, '
      'projetos, especificações, diagramas, modelos, amostras, fluxogramas, programas '
      'de computador, mídias digitais, planos de marketing e vendas, nomes de clientes '
      'e outras informações técnicas, financeiras ou comerciais transmitidas por uma '
      'parte à outra), relacionada ao presente instrumento ou a qualquer outra '
      'negociação que venha a ser mantida entre as partes, e que: (1) se veiculada sob '
      'forma escrita ou sob qualquer outra forma tangível, esteja identificada com a '
      'designação "CONFIDENCIAL"; ou (2) se veiculada verbalmente, desde que, no '
      'momento de sua veiculação ou dentro de 5 (cinco) dias úteis após essa '
      'veiculação, a parte transmissora descreva o referido DADO, por escrito, '
      'identificando sua natureza confidencial, na forma do item (1) acima;',
      "PESSOAL AUTORIZADO: empregados, representantes, contratados e/ou empresas "
      "associadas de qualquer das partes e seus respectivos empregados, representantes "
      "e/ou contratados previamente autorizados pela Diretoria."]),
    ("VIGÊNCIA",
     ["O presente ACORDO vigorará pelo prazo de 2 (dois) anos a partir de sua "
      "assinatura, a menos que de outra forma seja acordado por escrito entre as partes."]),
    ("OBRIGAÇÕES DA RECEPTORA",
     ["A partir da data de assinatura do presente instrumento, a RECEPTORA deverá:",
      "a) utilizar os DADOS somente nos termos do presente ACORDO, sendo expressamente "
      "vedada sua utilização para qualquer outro fim que não os mencionados pela "
      "TRANSMISSORA no momento de sua divulgação;",
      "b) transmitir os DADOS somente aos membros do PESSOAL AUTORIZADO que tenham "
      "necessidade de tomar conhecimento de tal DADO, sendo vedada a divulgação a "
      "qualquer pessoa que não deva ter acesso ao referido DADO. A RECEPTORA deverá "
      "certificar-se de que os membros do PESSOAL AUTORIZADO estejam devidamente "
      "cientificados da natureza confidencial do DADO que lhes será divulgado, "
      "orientando-os a observar as obrigações assumidas por força do presente ACORDO;",
      "c) exigir que os membros do PESSOAL AUTORIZADO utilizem com os DADOS o mesmo "
      "grau de cuidado e sigilo utilizado com as informações confidenciais da própria "
      "RECEPTORA;",
      "d) informar à TRANSMISSORA qualquer divulgação ou utilização indevida dos DADOS "
      "de que venha a tomar conhecimento;",
      "e) não efetuar cópias ou qualquer outro tipo de reprodução dos DADOS recebidos "
      "por força do presente ACORDO sem a aprovação prévia da TRANSMISSORA."]),
    ("EXCEÇÕES",
     ["Nenhuma obrigação de confidencialidade será observada nas hipóteses em que os "
      "DADOS:",
      "a) já tenham sido divulgados à RECEPTORA sem obrigação de confidencialidade;",
      "b) venham a ser divulgados à RECEPTORA por terceiros sem obrigação de "
      "confidencialidade;",
      "c) estejam ou tenham sido tornados disponíveis publicamente, de forma lícita, "
      "por outra parte que não a RECEPTORA;",
      "d) tenham sido, total e independentemente, desenvolvidos pela RECEPTORA;",
      "e) devam ser divulgados por força de qualquer disposição legal ou regulamentar, "
      "ou de determinação judicial ou de outra autoridade pública competente, desde que "
      "a parte que tenha de efetuar a mencionada divulgação notifique imediatamente a "
      "TRANSMISSORA da existência de tal requerimento e não se oponha a que a "
      "TRANSMISSORA procure, às suas expensas, por meio de processo judicial ou "
      "administrativo, evitar tal divulgação."]),
    ("DISPOSIÇÕES GERAIS",
     ["O presente ACORDO, ou qualquer divulgação de informação realizada em "
      "conformidade com os seus termos e condições, com exceção das disposições nele "
      "expressas, não confere, a qualquer título, nenhum tipo de licença nem qualquer "
      "outro direito, de qualquer natureza, para a utilização dos DADOS, patentes, "
      "marcas, nomes comerciais, direitos autorais ou outro tipo de propriedade "
      "intelectual da TRANSMISSORA.",
      "Todos os DADOS divulgados na forma do presente ACORDO serão considerados de "
      "propriedade da TRANSMISSORA. Em até 15 (quinze) dias corridos do recebimento de "
      "uma solicitação da TRANSMISSORA, a RECEPTORA deverá devolver-lhe todos e "
      "quaisquer DADOS por ela recebidos sob forma tangível e todas as cópias de suas "
      "eventuais reproduções, e deverá, também, destruir todos os DADOS por ela "
      "produzidos com base, parcial ou total, em DADOS a ela divulgados pela "
      "TRANSMISSORA por força deste pacto.",
      "O presente ACORDO não estabelece nenhuma obrigatoriedade ou vedação a que "
      "qualquer das partes celebre outro contrato ou participe de qualquer outra "
      "negociação com outras partes.",
      "O presente ACORDO somente poderá ser alterado mediante aditivo escrito celebrado "
      "entre as partes. A tolerância de qualquer das partes com relação ao cumprimento "
      "das obrigações da outra parte não configurará novação.",
      "O presente ACORDO corresponde ao acordo integral entre as partes a respeito do "
      "seu objeto, substituindo qualquer entendimento anterior, verbal ou escrito.",
      "As partes reconhecem que o não cumprimento das obrigações assumidas sob este "
      "ACORDO resultará em prejuízos irreparáveis para a TRANSMISSORA e que, dentre "
      "outras medidas, a TRANSMISSORA poderá adotar qualquer medida que permita impedir "
      "ou restringir o descumprimento das obrigações ora assumidas, respondendo a parte "
      "infratora pelos danos diretos decorrentes da exposição de quaisquer DADOS de que "
      "trata este ACORDO. Em hipótese alguma as partes responderão por danos indiretos, "
      "lucros cessantes ou perda de receita.",
      "O presente ACORDO produz efeitos desde a data de admissão da RECEPTORA junto à "
      "TRANSMISSORA.",
      "O presente ACORDO submete-se à legislação vigente na República Federativa do "
      "Brasil.",
      "As partes elegem, de forma irretratável e irrevogável, o foro da circunscrição "
      "judiciária de Brasília/DF como o único competente para dirimir qualquer dúvida "
      "ou eventual controvérsia que possa surgir na execução do presente instrumento, "
      "com renúncia expressa a qualquer outro, por mais privilegiado que seja."]),
)


def gerar_acordo_confidencialidade(db: Session, candidato: Candidato,
                                   assinatura: Assinatura | None = None,
                                   base_url: str | None = None) -> bytes:
    """Acordo de Confidencialidade — antes gerado à mão no Word; agora com a
    qualificação puxada dinamicamente da ficha do colaborador, formatação
    uniforme no papel timbrado e gramática revisada."""
    d = db.get(DocumentosIdentificacao, candidato.id)
    p = db.get(DadosPessoais, candidato.id)
    quando = (assinatura.assinado_em.date() if assinatura and assinatura.assinado_em
              else date.today())

    cpf_txt = (f"{d.cpf[:3]}.{d.cpf[3:6]}.{d.cpf[6:9]}-{d.cpf[9:]}"
               if d and d.cpf and len(d.cpf) == 11 else "___.___.___-__")
    nome_social = f" (nome social: {p.nome_social})" if p and p.nome_social else ""
    cargo = f", na função de {candidato.cargo_funcao}" if candidato.cargo_funcao else ""

    pdf = _OficioPDF("Acordo de Confidencialidade")
    pdf.set_font("helvetica", "B", 12)
    pdf.cell(0, 7, "ACORDO DE CONFIDENCIALIDADE", align="C",
             new_x="LMARGIN", new_y="NEXT")
    pdf.ln(3)
    pdf.paragrafo(
        f"{EMPRESA_RAZAO}., inscrita no CNPJ/MF sob o nº {EMPRESA_CNPJ}, com sede na "
        f"{EMPRESA_ENDERECO}, neste ato representada na forma de seu ato constitutivo, "
        'doravante denominada simplesmente "TRANSMISSORA"; e '
        f"{candidato.nome_completo}{nome_social}, inscrito(a) no CPF sob o nº "
        f"{cpf_txt}{cargo}, doravante denominado(a) simplesmente \"RECEPTORA\".")
    pdf.paragrafo(
        "As partes, acima nomeadas e qualificadas, resolvem celebrar o presente Acordo "
        'de Confidencialidade, doravante simplesmente "ACORDO", de acordo com os '
        "seguintes termos e condições:")
    for titulo, paragrafos in _ACORDO_CLAUSULAS:
        pdf.ln(1)
        pdf.set_font("helvetica", "B", 10.5)
        pdf.cell(0, 6, titulo, new_x="LMARGIN", new_y="NEXT")
        pdf.ln(1)
        for texto in paragrafos:
            pdf.paragrafo(texto)
    pdf.paragrafo(
        "E, por estarem assim justas e contratadas, as partes assinam o presente "
        "ACORDO eletronicamente, na forma da Lei nº 14.063/2020, com a trilha de "
        "evidências registrada no manifesto anexo.")
    pdf.set_font("helvetica", "", 10.5)
    pdf.cell(0, 6, f"Brasília/DF, {quando.strftime('%d/%m/%Y')}.",
             new_x="LMARGIN", new_y="NEXT")
    pdf.assinantes_empresa(assinantes_config(db))
    pdf.ln(2)
    if assinatura and assinatura.assinado_em:
        pdf.set_font("helvetica", "I", 10.5)
        pdf.cell(0, 6, f"{candidato.nome_completo} - assinado eletronicamente",
                 new_x="LMARGIN", new_y="NEXT")
    else:
        pdf.cell(0, 6, "_" * 60, new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("helvetica", "B", 9.5)
    pdf.cell(0, 6, "RECEPTORA (COLABORADOR)", new_x="LMARGIN", new_y="NEXT")

    if assinatura:
        pdf.bloco_assinatura(assinatura, candidato.nome_completo)
        pdf.pagina_manifesto(assinatura, candidato, d.cpf if d else None, base_url)
    return bytes(pdf.output())


def carimbar_rubrica_texto(pdf_bytes: bytes, texto: str) -> bytes:
    """Aplica um texto de rubrica na lateral direita de CADA página. Núcleo
    reutilizável (o multi-signatário usa com um texto próprio). Qualquer falha
    devolve o PDF original — a rubrica é reforço, não requisito."""
    import io

    try:
        from pypdf import PdfReader, PdfWriter

        ov = FPDF(format="A4")
        ov.set_auto_page_break(False)
        ov.add_page()
        ov.set_font("helvetica", "", 5.4)
        ov.set_text_color(128, 138, 130)
        with ov.rotation(90, 206, 288):
            ov.text(206, 288, texto)
        pagina_rubrica = PdfReader(io.BytesIO(bytes(ov.output()))).pages[0]

        leitor = PdfReader(io.BytesIO(pdf_bytes))
        escritor = PdfWriter()
        for pagina in leitor.pages:
            pagina.merge_page(pagina_rubrica)
            escritor.add_page(pagina)
        saida = io.BytesIO()
        escritor.write(saida)
        return saida.getvalue()
    except Exception:
        return pdf_bytes


def carimbar_rubrica_lateral(pdf_bytes: bytes, assinatura: Assinatura) -> bytes:
    """Rubrica digital em CADA página do PDF assinado (via legada de 1 assinante)."""
    quando = assinatura.assinado_em.strftime("%d/%m/%Y %H:%M UTC") \
        if assinatura.assinado_em else "-"
    texto = (f"Assinatura eletronica (Lei 14.063/2020) | registro {assinatura.id} | "
             f"SHA-256 {assinatura.hash_sha256} | {quando} | confira em /verificar")
    return carimbar_rubrica_texto(pdf_bytes, texto)


# ---------- Documentos criados pelo RH (modelos com variáveis) ----------

# Variáveis disponíveis nos modelos de documento (o RH usa {{nome}}, {{cargo}}…).
VARIAVEIS_MODELO = {
    "nome": "Nome completo do colaborador",
    "nome_social": "Nome social (ou o nome completo, se não houver)",
    "cpf": "CPF do colaborador",
    "cargo": "Cargo/função",
    "posto": "Posto de serviço",
    "contrato": "Contrato de referência do posto",
    "salario": "Salário base",
    "data": "Data de hoje (dd/mm/aaaa)",
    "empresa": "Razão social da empresa",
}


def _cpf_formatado(cpf: str | None) -> str:
    n = "".join(filter(str.isdigit, cpf or ""))
    return f"{n[:3]}.{n[3:6]}.{n[6:9]}-{n[9:]}" if len(n) == 11 else (cpf or "-")


def _contexto_modelo(db: Session, candidato: Candidato | None) -> dict:
    from app.models.candidato import PostoServico
    aplicar_marca(db)  # a variável {{empresa}} e o timbrado usam a marca atual
    if candidato is None:
        return {k: f"{{{{{k}}}}}" for k in VARIAVEIS_MODELO} | {
            "data": date.today().strftime("%d/%m/%Y"), "empresa": EMPRESA_RAZAO}
    contrato, cargo = _dados_posto(db, candidato)
    posto = db.get(PostoServico, candidato.posto_servico_id) \
        if candidato.posto_servico_id else None
    d = db.get(DocumentosIdentificacao, candidato.id)
    p = db.get(DadosPessoais, candidato.id)
    return {
        "nome": candidato.nome_completo or "-",
        "nome_social": (getattr(p, "nome_social", None) or candidato.nome_completo or "-"),
        "cpf": _cpf_formatado(d.cpf if d else None),
        "cargo": cargo,
        "posto": posto.nome if posto else "-",
        "contrato": contrato,
        "salario": candidato.salario_base or "-",
        "data": date.today().strftime("%d/%m/%Y"),
        "empresa": EMPRESA_RAZAO,
    }


def aplicar_variaveis(texto: str, contexto: dict) -> str:
    """Substitui {{chave}} (tolerante a espaços/caixa) pelo valor do contexto.
    Chave desconhecida fica como está — o RH vê o placeholder e corrige."""
    def repl(m):
        return str(contexto.get(m.group(1).strip().lower(), m.group(0)))
    return re.sub(r"\{\{\s*(\w+)\s*\}\}", repl, texto or "")


def gerar_documento_modelo(db: Session, titulo: str, corpo: str,
                           candidato: Candidato | None = None,
                           assinatura: Assinatura | None = None,
                           base_url: str | None = None) -> bytes:
    """Renderiza um modelo do RH como PDF no papel timbrado padrão, com as
    variáveis preenchidas para o `candidato` (ou mantidas como {{...}} numa
    prévia sem colaborador). Com `assinatura` assinada, ganha o bloco de
    assinatura e o manifesto — mesmo padrão das fichas do sistema."""
    ctx = _contexto_modelo(db, candidato)
    pdf = _OficioPDF(aplicar_variaveis(titulo, ctx))
    pdf.set_font("helvetica", "B", 13)
    pdf.set_text_color(*AZUL)
    pdf.multi_cell(0, 7, aplicar_variaveis(titulo, ctx), align="C")
    pdf.set_text_color(30, 30, 30)
    pdf.ln(3)
    for paragrafo in aplicar_variaveis(corpo, ctx).split("\n"):
        if paragrafo.strip():
            pdf.paragrafo(paragrafo.strip())
        else:
            pdf.ln(2.5)
    if assinatura is not None and candidato is not None and assinatura.assinado_em:
        d = db.get(DocumentosIdentificacao, candidato.id)
        pdf.bloco_assinatura(assinatura, candidato.nome_completo)
        pdf.pagina_manifesto(assinatura, candidato, d.cpf if d else None, base_url)
    return bytes(pdf.output())


# ---------- Multi-signatário: um documento assinado por VÁRIAS pessoas --------

from dataclasses import dataclass


@dataclass
class VistoAssinatura:
    """Um assinante de um documento multi-signatário (o que vai no bloco e no
    manifesto). Snapshot: os dados são os do MOMENTO da assinatura."""
    nome: str
    papel: str
    cpf: str | None
    assinado_em: datetime | None
    ip: str | None
    hash_sha256: str | None
    id_verificacao: str          # id da etapa → /verificar-etapa/{id}
    metodo: str                  # otp_email | senha_sessao_rh | autorizacao_previa


def _texto_metodo(metodo: str) -> str:
    return {
        "otp_email": "Código de verificação de uso único, enviado ao e-mail do "
                     "signatário e validado nesta plataforma.",
        "senha_sessao_rh": "Autenticação da conta corporativa no painel + "
                           "reautenticação por senha no ato da assinatura.",
        "autorizacao_previa": "Autorização prévia registrada pelo representante "
                              "da empresa (ato de vontade único, com validação por "
                              "código), aposta automaticamente neste documento.",
    }.get(metodo, "Assinatura eletrônica simples — art. 4º, I, da Lei nº 14.063/2020.")


def _bloco_visto(pdf: "_FichaPDF", v: VistoAssinatura):
    """Um bloco de assinatura por signatário — empilháveis (correção: quebra de
    página entre eles)."""
    pdf.ln(6)
    if pdf.get_y() > pdf.h - 42:
        pdf.add_page()
    pdf.set_draw_color(*AZUL)
    pdf.set_line_width(0.3)
    y = pdf.get_y()
    pdf.rect(10, y, 190, 30)
    pdf.set_xy(14, y + 2.5)
    pdf.set_font("helvetica", "B", 8.5)
    quando = v.assinado_em.strftime("%d/%m/%Y %H:%M:%S UTC") if v.assinado_em else "-"
    pdf.cell(0, 5, f"ASSINATURA ELETRÔNICA — {v.papel} (Lei nº 14.063/2020)",
             new_x="LMARGIN", new_y="NEXT")
    pdf.set_x(14)
    pdf.set_font("helvetica", "", 7.5)
    pdf.multi_cell(
        182, 4.2,
        f"Assinado por {v.nome}, na qualidade de {v.papel}, em {quando}. IP: {v.ip or '-'}\n"
        f"Integridade da via (SHA-256): {v.hash_sha256}\n"
        f"Verificação individual desta assinatura: /verificar-etapa/{v.id_verificacao}")


def _pagina_manifesto_multi(pdf: "_FichaPDF", vistos: list[VistoAssinatura],
                            titulo: str, sol_id: str, base_url: str | None):
    """Manifesto que lista TODOS os signatários — um bloco 'Assinante N' por
    visto, cada um com seu QR próprio para /verificar-etapa."""
    pdf.add_page()
    pdf.ln(2)
    pdf.set_font("helvetica", "B", 13)
    pdf.set_text_color(*AZUL)
    pdf.cell(0, 8, "MANIFESTO DE ASSINATURA ELETRÔNICA", align="C",
             new_x="LMARGIN", new_y="NEXT")
    pdf.set_text_color(30, 30, 30)
    pdf.ln(2)
    pdf.secao("Documento")
    pdf.campo("Documento assinado", titulo)
    pdf.campo("ID da solicitação", sol_id)
    pdf.campo("Total de assinaturas", str(len(vistos)))

    for i, v in enumerate(vistos, start=1):
        if pdf.get_y() > pdf.h - 60:
            pdf.add_page()
        pdf.secao(f"Assinante {i} — {v.papel}")
        pdf.campo("Nome", v.nome)
        if v.cpf:
            pdf.campo("CPF", v.cpf)
        brasilia = v.assinado_em.astimezone(_TZ_BRASILIA) if v.assinado_em else None
        pdf.campo("Data e hora (Brasília)",
                  brasilia.strftime("%d/%m/%Y %H:%M:%S (UTC-3)") if brasilia else "-")
        pdf.campo("Endereço IP", v.ip)
        pdf.campo("Integridade (SHA-256)", v.hash_sha256)
        pdf.campo("Método", _texto_metodo(v.metodo))
        if base_url:
            url = f"{base_url}/verificar-etapa/{v.id_verificacao}"
            try:
                import qrcode
                qr = qrcode.make(url, box_size=4, border=2)
                y_qr = pdf.get_y() + 1
                pdf.image(qr.get_image(), x=14, y=y_qr, w=24, h=24)
                pdf.set_xy(42, y_qr + 2)
                pdf.set_font("helvetica", "", 8)
                pdf.multi_cell(150, 4.5,
                               f"Confira esta assinatura individualmente em:\n{url}")
                pdf.set_y(y_qr + 26)
            except Exception:
                pdf.set_font("helvetica", "", 8)
                pdf.multi_cell(190, 4.5, f"Confira em: {url}")


def gerar_documento_com_vistos(db: Session, sol, candidato: Candidato,
                               vistos: list[VistoAssinatura],
                               base_url: str | None = None) -> bytes:
    """Renderiza o documento (fixo ou de modelo) com N blocos de assinatura
    empilhados + manifesto multi-assinante. Usado na consolidação do PDF final
    de um roteiro concluído."""
    ctx = _contexto_modelo(db, candidato)
    if sol.modelo_id or sol.corpo_doc:
        titulo = aplicar_variaveis(sol.titulo_doc or "Documento", ctx)
        pdf = _OficioPDF(titulo)
        pdf.set_font("helvetica", "B", 13)
        pdf.set_text_color(*AZUL)
        pdf.multi_cell(0, 7, titulo, align="C")
        pdf.set_text_color(30, 30, 30)
        pdf.ln(3)
        for paragrafo in aplicar_variaveis(sol.corpo_doc or "", ctx).split("\n"):
            if paragrafo.strip():
                pdf.paragrafo(paragrafo.strip())
            else:
                pdf.ln(2.5)
    else:
        # documento fixo: gera o corpo pelo GERADOR e reabre para empilhar blocos
        # (raro no multi — a maioria dos multi é de modelo). Fallback simples:
        titulo = NOMES_DOC_FALLBACK.get(sol.documento, sol.documento or "Documento")
        pdf = _OficioPDF(titulo)
        pdf.set_font("helvetica", "B", 13)
        pdf.set_text_color(*AZUL)
        pdf.multi_cell(0, 7, titulo, align="C")
        pdf.set_text_color(30, 30, 30)
        pdf.ln(3)
        pdf.set_font("helvetica", "", 10)
        pdf.multi_cell(0, 5, "Documento do sistema submetido a assinatura múltipla. "
                             "As vias individuais de cada signatário e a íntegra do "
                             "conteúdo constam da trilha de auditoria.")
    for v in vistos:
        _bloco_visto(pdf, v)
    _pagina_manifesto_multi(pdf, vistos, titulo, str(sol.id), base_url)
    return bytes(pdf.output())


NOMES_DOC_FALLBACK = {
    "ficha_cadastro": "Ficha Cadastral do Colaborador",
    "ficha_emergencia": "Ficha de Emergência do Colaborador",
    "termo_vt": "Termo de Opção pelo Vale-Transporte",
    "acordo_confidencialidade": "Acordo de Confidencialidade",
}


def gerar_informativo_intermitente(db: Session, candidato: Candidato,
                                   assinatura: Assinatura | None = None,
                                   base_url: str | None = None) -> bytes:
    """Informativo de Integração do intermitente (GHS - INTERMITENTE): difere do
    efetivo nos períodos de pagamento de VT/VA (semanal), ponto pelo Tirvu+,
    prazos de assinatura e declaração de normativos. O colaborador lê e assina."""
    p = db.get(DadosPessoais, candidato.id)
    d = db.get(DocumentosIdentificacao, candidato.id)
    b = db.get(DadosProfissionaisBancarios, candidato.id)
    nome = (p.nome_completo if p and getattr(p, "nome_completo", None)
            else candidato.nome_completo)

    pdf = _FichaPDF("INFORMATIVO DE INTEGRAÇÃO")
    pdf.set_font("helvetica", "", 10)
    pdf.multi_cell(0, 5.4,
        "É com grande satisfação que damos as boas-vindas à nossa equipe! Estamos muito "
        "felizes com a sua chegada e confiantes de que sua experiência e dedicação "
        "contribuirão de forma significativa para o nosso crescimento e sucesso coletivo.")
    pdf.ln(1)
    pdf.set_font("helvetica", "B", 10)
    pdf.cell(0, 6, "Local e data: Brasília, DF, ____ / ____ / ______.",
             new_x="LMARGIN", new_y="NEXT")
    pdf.ln(1)

    pdf.campo("Nome Completo", nome)
    pdf.campo("CPF", d.cpf if d else None)
    pdf.campo("Telefone (WhatsApp)", candidato.celular_whatsapp)
    pdf.campo("E-mail", candidato.email)
    pdf.campo("Cargo", candidato.cargo_funcao)
    pdf.campo("Local de Trabalho (Posto)", "GHS - INTERMITENTE")

    pdf.secao("VALE TRANSPORTE")
    pdf.set_font("helvetica", "", 9.5)
    pdf.multi_cell(0, 5,
        "O primeiro ciclo de Vale-Transporte, caso optante, será disponibilizado em até 5 "
        "(cinco) dias úteis, a partir da data da assinatura do contrato de trabalho, por meio "
        "de pix. Neste primeiro momento, o valor será calculado de forma proporcional, da data "
        "de admissão até o dia 19 do respectivo mês.\n"
        "A partir de então, o benefício passará a ser pago semanalmente, até a quarta-feira da "
        "semana seguinte, por meio do cartão de vale-transporte, destinado à mobilidade no "
        "Distrito Federal ou, no caso de colaboradores residentes no Entorno, por meio dos "
        "cartões das respectivas empresas de transporte coletivo.")

    pdf.secao("VALE ALIMENTAÇÃO")
    pdf.set_font("helvetica", "", 9.5)
    pdf.multi_cell(0, 5,
        "O cartão de vale-alimentação estará disponível em até 10 (dez) dias úteis, contados da "
        "assinatura do contrato de trabalho. No ato do recebimento do cartão, será obrigatória a "
        "assinatura do respectivo recibo. Após o envio do recibo devidamente assinado ao "
        "Departamento Pessoal (e-mail: departamentopessoal@greenhousedf.com.br ou WhatsApp: "
        "61-99834-2311), será realizado o crédito do benefício no cartão.\n"
        "Os valores serão disponibilizados considerando o período de apuração semanal, sendo "
        "pago até a quarta-feira da semana seguinte.")

    pdf.secao("CONTA SALÁRIO")
    pdf.campo("Banco", b.banco if b else None)
    pdf.campo("Chave PIX", (b.pix_chave if b else None))
    pdf.set_font("helvetica", "", 9)
    pdf.multi_cell(0, 5, "O salário será depositado até o 5º (quinto) dia útil de cada mês.")

    pdf.secao("PONTO ELETRÔNICO (App Tirvu+)")
    pdf.set_font("helvetica", "", 9.5)
    pdf.multi_cell(0, 5,
        "Primeiro acesso: 1) baixe o aplicativo Tirvu+ na loja do seu celular; 2) conceda as "
        "permissões solicitadas (localização e câmera); 3) no campo Tirvu ID, insira GREENHOUSE, "
        "preencha os dados e confirme; 4) crie uma senha e use seu CPF + a senha para entrar.\n"
        "Registro de ponto: menu Colaborador > Ponto Eletrônico > Entrada. A captura da imagem é "
        "automática em até 3 segundos — não é preciso clicar em nenhum botão.")
    pdf.ln(1)
    pdf.set_font("helvetica", "B", 9.5)
    pdf.multi_cell(0, 5,
        "Os documentos são disponibilizados no app Tirvu e devem ser assinados dentro dos prazos:",
        new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("helvetica", "", 9.5)
    pdf.multi_cell(0, 5,
        "- Folha de Ponto: assinar no 1º dia útil de cada mês.\n"
        "- Contracheque: assinar no 5º dia útil de cada mês.\n"
        "- Recibo de vale alimentação/transporte: assinar no dia 20 de cada mês.\n"
        "- Demais documentos: assinar na data em que forem disponibilizados.\n"
        "Os documentos de pagamento (contracheque, vale-alimentação e vale-transporte) devem ser "
        "assinados imediatamente após a confirmação do crédito. O descumprimento dos prazos "
        "poderá acarretar medidas disciplinares conforme o art. 482 da CLT.")

    pdf.secao("NORMATIVOS E ORIENTAÇÕES")
    pdf.set_font("helvetica", "", 9.5)
    pdf.multi_cell(0, 5,
        "Declaro que recebi, via Tirvu, os seguintes normativos da GREEN HOUSE, cujo cumprimento "
        "é obrigatório: a) Código de Ética; b) Política Antiassédio; c) Política de Equidade de "
        "Gênero e Empoderamento Feminino; d) Política de Apresentação de Atestados.\n"
        "Orientações: mantenha apresentação e higiene pessoal condizentes com o ambiente "
        "corporativo; o uso do uniforme é obrigatório nas funções em que houver disponibilização; "
        "o uso do celular deve ser feito com bom senso, restrito ao necessário.\n"
        "Em caso de divergências, inconsistências ou dúvidas, contate imediatamente o setor "
        "responsável pelo telefone (61) 3346-8812.")

    return bytes(pdf.output())


def gerar_ficha_cadastral_terceirizado(db: Session, candidato: Candidato,
                                       assinatura: Assinatura | None = None,
                                       base_url: str | None = None) -> bytes:
    """Ficha Cadastral de Terceirizado (kit da Presidência da República) — réplica
    do modelo, preenchida com os dados do colaborador."""
    p = db.get(DadosPessoais, candidato.id)
    e = db.get(Endereco, candidato.id)
    d = db.get(DocumentosIdentificacao, candidato.id)

    def _campo(p, attr, default=None):
        return getattr(p, attr, default) if p else default

    pdf = _FichaPDF("FICHA CADASTRAL DE TERCEIRIZADO")
    _nota(pdf, "Preencher com letra de forma. Documento gerado a partir do Formulário de "
               "Admissão Green House para credenciamento na Presidência da República.")
    pdf.campo("Nome", _campo(p, "nome_completo") or candidato.nome_completo)
    pdf.campo("Nome social", _campo(p, "nome_social"))
    pdf.campo("CPF", d.cpf if d else None)
    pdf.campo("Sexo", _campo(p, "sexo"))
    pdf.campo("Nome da mãe", _campo(p, "nome_mae"))
    pdf.campo("Nome do pai", _campo(p, "nome_pai"))
    pdf.campo("Data de nascimento", _campo(p, "data_nascimento"))
    pdf.campo("Naturalidade / UF",
              f"{_campo(p, 'naturalidade_cidade') or '-'} / {_campo(p, 'naturalidade_uf') or '-'}")
    pdf.campo("Nacionalidade", _campo(p, "nacionalidade"))
    pdf.campo("PIS/PASEP", d.pis_nis_pasep if d else None)
    pdf.campo("RG — nº / órgão / UF / expedição",
              f"{(d.rg_numero if d else None) or '-'} / {(d.rg_orgao_emissor if d else None) or '-'}"
              f" / {(d.rg_data_expedicao if d else None) or '-'}")
    pdf.campo("Estado civil", _campo(p, "estado_civil"))
    pdf.campo("Escolaridade", _campo(p, "escolaridade"))
    pdf.campo("Endereço", e.logradouro_numero_complemento if e else None)
    pdf.campo("Bairro", e.bairro if e else None)
    pdf.campo("Cidade / UF / CEP",
              f"{(e.cidade if e else None) or '-'} / {(e.uf if e else None) or '-'}"
              f" / {(e.cep if e else None) or '-'}")
    pdf.campo("Celular / WhatsApp", candidato.celular_whatsapp)
    pdf.campo("E-mail", candidato.email)
    pdf.campo("Cargo / função", candidato.cargo_funcao)
    return bytes(pdf.output())


def gerar_oficio_apresentacao_presidencia(db: Session, candidato: Candidato,
                                          assinatura: Assinatura | None = None,
                                          base_url: str | None = None) -> bytes:
    """Ofício de Apresentação de Funcionário à Presidência da República
    (Coordenação de Serviços Gerais), para credenciamento na Divisão de
    Segurança — réplica do modelo, com as variáveis do colaborador."""
    contrato, cargo = _dados_posto(db, candidato)
    d = db.get(DocumentosIdentificacao, candidato.id)
    e = db.get(Endereco, candidato.id)
    cpf = _cpf_formatado(d.cpf if d else None)
    rg = (d.rg_numero if d else None) or "................."
    orgao = (d.rg_orgao_emissor if d else None) or "SSP/____"
    endereco = (e.logradouro_numero_complemento if e else None) or "................................"
    quando = (assinatura.assinado_em.date() if assinatura and assinatura.assinado_em
              else date.today())

    pdf = _OficioPDF("Ofício de Apresentação — Presidência da República")
    pdf.set_font("helvetica", "", 10.5)
    pdf.cell(0, 6, f"Brasília/DF, {quando.day:02d} de {_MESES_PT[quando.month - 1]} de {quando.year}.",
             align="R", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(4)
    _NX = {"new_x": "LMARGIN", "new_y": "NEXT"}
    pdf.set_font("helvetica", "B", 10.5)
    pdf.multi_cell(0, 5.6, "PRESIDÊNCIA DA REPÚBLICA\nCoordenação de Serviços Gerais - PR", **_NX)
    pdf.ln(2)
    pdf.set_font("helvetica", "", 10.5)
    pdf.multi_cell(0, 5.6, "Assunto: Apresentação de funcionário", **_NX)
    pdf.multi_cell(0, 5.6, f"Ref.: Contrato nº {contrato}", **_NX)
    pdf.ln(2)
    pdf.multi_cell(0, 5.6, "Senhor Gestor,", **_NX)
    pdf.ln(1)
    pdf.multi_cell(0, 5.6,
        "Encaminhamos, para fins de credenciamento junto à Divisão de Segurança da Presidência "
        f"da República, o(a) Sr(a). {candidato.nome_completo}, que iniciou suas atividades "
        f"laborais no referido contrato em ______________, na função de {cargo}, no local "
        "________________ das ________ hs, portador(a) do documento de identidade nº "
        f"{rg}, expedido pela {orgao}, CPF {cpf}, residente e domiciliado(a) à {endereco}.", **_NX)
    pdf.ln(1)
    pdf.multi_cell(0, 5.6,
        f"Por oportuno, solicita-se providenciar a confecção de crachá funcional para o(a) "
        f"funcionário(a) {candidato.nome_completo}, conforme documentação anexa.", **_NX)
    pdf.ln(3)
    pdf.assinantes_empresa()
    return bytes(pdf.output())


def _com_marca(gerador):
    """Envolve um gerador para sincronizar a marca da empresa (config dinâmica)
    antes de montar o PDF — o primeiro argumento é sempre `db`."""
    def _wrap(db, *args, **kwargs):
        aplicar_marca(db)
        return gerador(db, *args, **kwargs)
    return _wrap


GERADORES = {
    nome: _com_marca(g) for nome, g in {
        "ficha_cadastro": gerar_ficha_cadastro,
        "ficha_emergencia": gerar_ficha_emergencia,
        "termo_vt": gerar_termo_vt,
        "acordo_confidencialidade": gerar_acordo_confidencialidade,
        "oficio_cartao_cidadao": gerar_oficio_cartao_cidadao,
        "informacoes_trabalhador": gerar_informacoes_trabalhador,
        "termo_lgpd_infraero": gerar_termo_lgpd_infraero,
        "informativo_intermitente": gerar_informativo_intermitente,
        "ficha_cadastral_terceirizado": gerar_ficha_cadastral_terceirizado,
        "oficio_apresentacao_presidencia": gerar_oficio_apresentacao_presidencia,
    }.items()
}
