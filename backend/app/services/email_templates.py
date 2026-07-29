"""Catálogo dos e-mails do sistema + renderização com o texto do RH (v2.06).

Este arquivo é a FONTE DA VERDADE sobre quais e-mails existem, quais variáveis
cada um oferece e quais são obrigatórias. A tabela `email_template` guarda
apenas o texto que o RH escreveu por cima do padrão.

Como usar num ponto de envio:

    from app.services.email_templates import enviar_modelo
    enviar_modelo(db, "creche_indeferido", col.email,
                  {"nome": primeiro, "motivo": ben.motivo_indeferimento})

Regras que sustentam o desenho (ver também `models/email_template.py`):

- **Variável obrigatória** (`obrigatorias`) é validada ao SALVAR: um template de
  código de acesso sem `{{codigo}}` sairia bonito e vazio, e ninguém mais
  entraria no sistema. Por isso o salvamento recusa com 422 em vez de confiar.
- **Fallback sempre**: sem registro no banco, ou com texto ilegível, vale o
  padrão daqui. E-mail nenhum deixa de sair porque alguém editou errado.
- **Lista dinâmica é uma variável pronta**: os e-mails que enumeram documentos
  ou pendências recebem `{{lista}}` já montada em Python. O RH escolhe onde ela
  entra e o que dizer ao redor; a regra de o que entra na lista é do código.
- A substituição é `fichas.aplicar_variaveis` (regex `{{chave}}`) — sem engine,
  sem dot-access, sem execução. Chave desconhecida fica visível como
  `{{assim}}`, para o RH ver que errou o nome em vez de mandar texto furado.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.email_template import EmailTemplate
from app.services.email import enviar_email, html_moderno

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class ModeloEmail:
    """Um e-mail do sistema: o que ele é, o que oferece e o que exige."""

    chave: str
    rotulo: str            # nome legível na tela do RH
    quando: str            # em que momento o sistema dispara isto
    assunto: str           # padrão de fábrica
    corpo: str             # padrão de fábrica (texto puro, parágrafos por \n\n)
    variaveis: dict[str, str]              # nome -> o que significa
    obrigatorias: tuple[str, ...] = ()     # sem estas, o salvamento é recusado
    botao_texto: str | None = None
    # Variável que carrega a URL do botão (a URL vem do sistema, não do RH).
    botao_url_var: str | None = None
    grupo: str = "Geral"
    critico: bool = False   # carrega código/link de acesso
    editavel: bool = True   # False = texto fixo, aparece na tela só p/ consulta
    observacao: str = ""    # nota exibida ao RH (ex.: por que não é editável)
    exemplo: dict[str, str] = field(default_factory=dict)  # para o preview


def _m(**kw) -> ModeloEmail:
    return ModeloEmail(**kw)


# ---------------------------------------------------------------------------
# CATÁLOGO
# ---------------------------------------------------------------------------
# Ordem = ordem de exibição na tela. `grupo` agrupa os cards.

CATALOGO: tuple[ModeloEmail, ...] = (
    # ---------------------------------------------------------------- acesso
    _m(chave="convite_admissao", grupo="Admissão", critico=True,
       rotulo="Convite para começar a admissão",
       quando="O RH cadastra o candidato (e no reenvio do convite).",
       assunto="🌱 Green House — comece sua admissão",
       corpo="Olá, {{primeiro_nome}}!\n\n"
             "Você foi selecionado(a) para a nossa equipe. Para começar sua "
             "admissão, é só tocar no botão abaixo — leva poucos minutos e "
             "pode ser feito pelo celular.\n\n"
             "O link é pessoal: não compartilhe com ninguém.",
       variaveis={"primeiro_nome": "primeiro nome do candidato",
                  "nome": "nome completo do candidato",
                  "link": "link mágico de acesso à admissão"},
       obrigatorias=("link",),
       botao_texto="Começar minha admissão", botao_url_var="link",
       exemplo={"primeiro_nome": "Maria", "nome": "Maria Souza",
                "link": "https://exemplo/c/abc123"}),

    _m(chave="link_acesso_reenvio", grupo="Admissão", critico=True,
       rotulo="Reenvio do link de acesso",
       quando="O candidato pede um novo link pelo portal de entrada.",
       assunto="🌱 Green House — seu link de acesso à admissão",
       corpo="Olá, {{primeiro_nome}}!\n\n"
             "Você pediu um novo acesso à sua admissão. Toque no botão para "
             "continuar de onde parou.\n\n"
             "Se não foi você quem pediu, ignore esta mensagem.",
       variaveis={"primeiro_nome": "primeiro nome do candidato",
                  "link": "link mágico de acesso"},
       obrigatorias=("link",),
       botao_texto="Continuar minha admissão", botao_url_var="link",
       exemplo={"primeiro_nome": "Maria", "link": "https://exemplo/c/abc123"}),

    # ------------------------------------------------------------ documentos
    _m(chave="documento_rejeitado", grupo="Documentos",
       rotulo="Um documento precisa ser reenviado",
       quando="O RH rejeita um documento do checklist.",
       assunto="🌱 Green House — um documento precisa ser reenviado",
       corpo="Prezado(a) {{nome}},\n\n"
             "Um dos seus documentos precisa ser enviado novamente: "
             "{{motivo}}.\n\n"
             "Sua contratação fica parada até esse reenvio — não deixe para "
             "depois.",
       variaveis={"nome": "nome completo do candidato",
                  "primeiro_nome": "primeiro nome",
                  "motivo": "motivo da rejeição, já em texto legível",
                  "link": "link para reenviar o documento"},
       botao_texto="Reenviar esse documento", botao_url_var="link",
       exemplo={"nome": "Maria Souza", "primeiro_nome": "Maria",
                "motivo": "a imagem ficou ilegível (foto tremida)",
                "link": "https://exemplo/c/abc123"}),

    _m(chave="documentos_rejeitados_lote", grupo="Documentos",
       rotulo="Vários documentos precisam ser reenviados",
       quando="O RH rejeita vários documentos de uma vez.",
       assunto="Green House — documentos precisam ser reenviados",
       corpo="Prezado(a) {{nome}},\n\n"
             "Os documentos abaixo precisam ser enviados novamente "
             "({{motivo}}):\n\n"
             "{{lista}}\n\n"
             "Sua contratação fica parada até esse reenvio.",
       variaveis={"nome": "nome completo do candidato",
                  "motivo": "motivo da rejeição, em texto legível",
                  "lista": "lista dos documentos (montada pelo sistema)",
                  "link": "link para reenviar"},
       obrigatorias=("lista",),
       botao_texto="Reenviar os documentos", botao_url_var="link",
       exemplo={"nome": "Maria Souza", "motivo": "o documento está vencido",
                "lista": "- rg\n- comp endereco",
                "link": "https://exemplo/c/abc123"}),

    _m(chave="admissao_pendencias", grupo="Documentos",
       rotulo="Cobrança de pendências da admissão",
       quando="O RH aciona 'Notificar pendências' na ficha do candidato.",
       assunto="Green House — sua admissão tem pendências que dependem de você",
       corpo="Prezado(a) {{nome}},\n\n"
             "Para seguirmos com a sua admissão, faltam estes itens:\n\n"
             "{{lista}}\n\n"
             "Leva poucos minutos. Faça hoje para não atrasar a sua "
             "contratação.",
       variaveis={"nome": "nome completo do candidato",
                  "lista": "itens pendentes (montada pelo sistema)",
                  "link": "link para continuar a admissão"},
       obrigatorias=("lista",),
       botao_texto="Continuar de onde parei", botao_url_var="link",
       exemplo={"nome": "Maria Souza",
                "lista": "1. Completar o formulário (3 campos em aberto)\n"
                         "2. Enviar os documentos: rg; comprovante de endereço",
                "link": "https://exemplo/c/abc123"}),

    # ------------------------------------------------------------ assinatura
    _m(chave="ficha_alterada_reassinar", grupo="Assinatura",
       rotulo="Ficha alterada pelo RH: reassinar",
       quando="O RH edita a ficha e isso invalida documentos já assinados.",
       assunto="Green House — documentos atualizados aguardam sua assinatura",
       corpo="Prezado(a) {{nome}},\n\n"
             "O RH atualizou informações da sua ficha ({{motivo}}). Os "
             "documentos abaixo foram regerados e precisam ser assinados "
             "novamente:\n\n"
             "{{lista}}\n\n"
             "A assinatura leva menos de um minuto.",
       variaveis={"nome": "nome completo", "motivo": "motivo informado pelo RH",
                  "lista": "documentos a reassinar (montada pelo sistema)",
                  "link": "link para assinar"},
       obrigatorias=("lista",),
       botao_texto="Assinar os documentos", botao_url_var="link",
       exemplo={"nome": "Maria Souza", "motivo": "correção do CPF",
                "lista": "- Ficha de cadastro\n- Termo de VT",
                "link": "https://exemplo/c/abc123"}),

    _m(chave="posto_novos_documentos", grupo="Assinatura",
       rotulo="Novos documentos para assinar (mudança de posto)",
       quando="A mudança de posto/regime gera documentos novos.",
       assunto="Green House — novos documentos aguardam a sua assinatura",
       corpo="Prezado(a) {{nome}},\n\n"
             "Novos documentos foram gerados para a sua admissão e aguardam "
             "assinatura:\n\n"
             "{{lista}}\n\n"
             "É rápido e pode ser feito pelo celular.",
       variaveis={"nome": "nome completo",
                  "lista": "documentos novos (montada pelo sistema)",
                  "link": "link para assinar"},
       obrigatorias=("lista",),
       botao_texto="Assinar os documentos", botao_url_var="link",
       exemplo={"nome": "Maria Souza", "lista": "- Termo de confidencialidade",
                "link": "https://exemplo/c/abc123"}),

    # ---------------------------------------------------------------- creche
    _m(chave="creche_devolvido", grupo="Reembolso-Creche",
       rotulo="Pedido devolvido para correção",
       quando="O RH devolve o levantamento do creche para correção.",
       assunto="Green House — Reembolso-Creche: seu pedido foi devolvido para correção",
       corpo="Olá, {{nome}}!\n\n"
             "Precisamos de um ajuste no seu pedido de Reembolso-Creche:\n\n"
             "{{motivo}}\n\n"
             "Corrija e reenvie — assim conseguimos concluir a análise.",
       variaveis={"nome": "primeiro nome do colaborador",
                  "motivo": "motivo da devolução, escrito pelo RH",
                  "link": "link que entra direto, sem código (7 dias)"},
       obrigatorias=("motivo",),
       botao_texto="Corrigir meu pedido", botao_url_var="link",
       exemplo={"nome": "Maria", "motivo": "A certidão da criança está ilegível.",
                "link": "https://exemplo/creche?t=abc"}),

    _m(chave="creche_ativado", grupo="Reembolso-Creche",
       rotulo="Benefício ativado: orientações",
       quando="O RH aprova e ativa o Reembolso-Creche.",
       assunto="Green House — Reembolso-Creche ativado: orientações da entrega mensal",
       corpo="Olá, {{nome}}!\n\n"
             "Seu Reembolso-Creche foi ativado. Todo mês, entregue o recibo da "
             "creche até o dia {{dia}} para que o reembolso entre na folha.\n\n"
             "O recibo precisa estar no nome da criança e conter o valor pago, "
             "a data e o CNPJ da instituição.",
       variaveis={"nome": "primeiro nome do colaborador",
                  "dia": "dia limite da entrega mensal"},
       exemplo={"nome": "Maria", "dia": "10"}),

    _m(chave="creche_indeferido", grupo="Reembolso-Creche",
       rotulo="Pedido indeferido",
       quando="O RH indefere o pedido de Reembolso-Creche.",
       assunto="Green House — Reembolso-Creche: resultado da análise",
       corpo="Olá, {{nome}},\n\n"
             "Analisamos o seu pedido de Reembolso-Creche e ele não pôde ser "
             "deferido pelo seguinte motivo:\n\n"
             "{{motivo}}\n\n"
             "Se tiver dúvidas ou novas informações, fale com o RH.",
       variaveis={"nome": "primeiro nome", "motivo": "motivo do indeferimento"},
       obrigatorias=("motivo",),
       exemplo={"nome": "Maria", "motivo": "A criança já completou 5 anos."}),

    _m(chave="creche_suspenso", grupo="Reembolso-Creche",
       rotulo="Benefício suspenso ou encerrado",
       quando="O RH suspende ou encerra o benefício.",
       assunto="Green House — Reembolso-Creche {{verbo}}",
       corpo="Olá, {{nome}},\n\n"
             "Seu Reembolso-Creche foi {{verbo}}.\n\n"
             "Motivo: {{motivo}}\n\n"
             "Em caso de dúvida, procure o RH.",
       variaveis={"nome": "primeiro nome", "verbo": "'suspenso' ou 'encerrado'",
                  "motivo": "motivo informado pelo RH"},
       exemplo={"nome": "Maria", "verbo": "suspenso",
                "motivo": "Desligamento da empresa."}),

    # ------------------------------------------------------------ colaborador
    _m(chave="desempenho_avaliacao", grupo="Colaborador",
       rotulo="Sua avaliação está disponível",
       quando="O RH libera o ciclo de avaliação de desempenho.",
       assunto="Green House — sua avaliação está disponível",
       corpo="Olá, {{primeiro_nome}}!\n\n"
             "Sua avaliação de desempenho está disponível no portal. "
             "Responda até {{prazo}}.\n\n"
             "É a sua oportunidade de registrar como foi o período e o que "
             "você espera para o próximo.",
       variaveis={"primeiro_nome": "primeiro nome", "prazo": "data limite",
                  "link": "endereço do portal do colaborador"},
       botao_texto="Ver minha avaliação", botao_url_var="link",
       exemplo={"primeiro_nome": "Maria", "prazo": "10/08/2026",
                "link": "https://exemplo/meu"}),

    _m(chave="certificacao_vencendo", grupo="Colaborador",
       rotulo="Certificação vencendo ou vencida",
       quando="O worker diário avisa 90 dias antes do vencimento.",
       assunto="Green House — {{titulo}} {{quando}}",
       corpo="Olá, {{primeiro_nome}}!\n\n"
             "Sua certificação {{titulo}} {{quando}} (validade: "
             "{{validade}}).\n\n"
             "Envie o comprovante da renovação pelo portal para manter seu "
             "cadastro em dia.",
       variaveis={"primeiro_nome": "primeiro nome", "titulo": "nome do certificado",
                  "quando": "'vence em N dias' ou 'venceu há N dias'",
                  "validade": "data de validade",
                  "link": "endereço do portal"},
       botao_texto="Enviar meus documentos", botao_url_var="link",
       exemplo={"primeiro_nome": "Maria", "titulo": "Brigada de Incêndio",
                "quando": "vence em 30 dias", "validade": "30/08/2026",
                "link": "https://exemplo/meu"}),

    _m(chave="desenvolvimento_devolvido", grupo="Colaborador",
       rotulo="Curso/certificado devolvido ou recusado",
       quando="O RH devolve ou recusa um documento enviado pelo colaborador.",
       assunto="Green House — precisamos de um ajuste no seu envio",
       corpo="Olá, {{primeiro_nome}}!\n\n"
             "Sobre o seu envio de {{titulo}}: {{motivo}}\n\n"
             "Você pode reenviar pelo portal.",
       variaveis={"primeiro_nome": "primeiro nome",
                  "titulo": "título do curso/certificado",
                  "motivo": "motivo informado pelo RH",
                  "link": "endereço do portal"},
       botao_texto="Reenviar pelo portal", botao_url_var="link",
       exemplo={"primeiro_nome": "Maria", "titulo": "NR-35",
                "motivo": "o certificado está sem a data de conclusão",
                "link": "https://exemplo/meu"}),

    # ---------------------------------------------------------------- talento
    _m(chave="talento_agradecimento", grupo="Banco de Talentos",
       rotulo="Agradecimento pelo cadastro",
       quando="Alguém se cadastra no Banco de Talentos.",
       assunto="🌱 Green House — recebemos o seu cadastro",
       corpo="Olá, {{primeiro_nome}}!\n\n"
             "Recebemos o seu cadastro no nosso Banco de Talentos — obrigado "
             "pelo interesse em fazer parte da Green House.\n\n"
             "Seu perfil fica à disposição do nosso time de recrutamento. "
             "Quando surgir uma vaga com o seu perfil, entramos em contato "
             "pelo telefone ou e-mail que você informou.\n\n"
             "Não é preciso fazer nada agora. Boa sorte!",
       variaveis={"primeiro_nome": "primeiro nome", "nome": "nome completo",
                  "cargos": "cargos de interesse informados"},
       exemplo={"primeiro_nome": "Maria", "nome": "Maria Souza",
                "cargos": "Auxiliar de Serviços Gerais, Recepcionista"}),
)

CATALOGO_POR_CHAVE = {m.chave: m for m in CATALOGO}


# ---------------------------------------------------------------------------
# Leitura / renderização
# ---------------------------------------------------------------------------


def modelo(chave: str) -> ModeloEmail:
    m = CATALOGO_POR_CHAVE.get(chave)
    if m is None:
        raise KeyError(f"e-mail '{chave}' não está no catálogo")
    return m


def texto_vigente(db: Session, chave: str) -> tuple[str, str, str | None]:
    """(assunto, corpo, botao_texto) — o do RH se houver, senão o padrão.

    Nunca levanta: registro ausente, texto vazio ou erro de banco caem no
    padrão do catálogo, porque e-mail não pode deixar de sair por causa de
    uma edição ruim.
    """
    m = modelo(chave)
    try:
        t = db.get(EmailTemplate, chave)
    except Exception:  # pragma: no cover - banco indisponível
        log.warning("template de e-mail '%s' ilegível; usando o padrão", chave)
        t = None
    if t is None or not (t.assunto or "").strip() or not (t.corpo or "").strip():
        return m.assunto, m.corpo, m.botao_texto
    return t.assunto, t.corpo, (t.botao_texto if t.botao_texto is not None
                                else m.botao_texto)


def faltando_obrigatorias(chave: str, assunto: str, corpo: str) -> list[str]:
    """Variáveis obrigatórias que sumiram do texto — o guard do salvamento.

    Um template de código de acesso sem `{{codigo}}` sai bonito e vazio, e aí
    ninguém mais entra no sistema. Melhor recusar o salvamento.

    A variável do BOTÃO não precisa aparecer no texto: ela já chega ao e-mail
    pelo botão de ação (a URL vem do sistema). Exigi-la no corpo obrigaria o RH
    a colar a URL crua num e-mail que já tem o botão.
    """
    m = modelo(chave)
    juntos = f"{assunto}\n{corpo}".replace("{{ ", "{{").replace(" }}", "}}")
    return [v for v in m.obrigatorias
            if v != m.botao_url_var and f"{{{{{v}}}}}" not in juntos]


def renderizar(db: Session, chave: str, contexto: dict) -> tuple[str, str, str]:
    """(assunto, corpo_texto, corpo_html) prontos para `enviar_email`."""
    from app.services.fichas import aplicar_variaveis

    m = modelo(chave)
    assunto_tpl, corpo_tpl, botao_texto = texto_vigente(db, chave)
    ctx = {k: ("" if v is None else str(v)) for k, v in contexto.items()}

    assunto = aplicar_variaveis(assunto_tpl, ctx)
    corpo = aplicar_variaveis(corpo_tpl, ctx)
    # Parágrafo em branco separa blocos; o HTML preserva as quebras internas
    # (as listas montadas em Python vêm com \n entre os itens).
    paragrafos = [p.strip().replace("\n", "<br>")
                  for p in corpo.split("\n\n") if p.strip()]
    url = ctx.get(m.botao_url_var) if m.botao_url_var else None
    html = html_moderno(
        aplicar_variaveis(m.rotulo, ctx),
        paragrafos,
        botao_texto=botao_texto if url else None,
        botao_url=url or None,
    )
    return assunto, corpo, html


def enviar_modelo(db: Session, chave: str, destinatario: str | None,
                  contexto: dict, anexos=None) -> bool:
    """Renderiza e envia. Sem destinatário, `enviar_email` já devolve False."""
    assunto, texto, html = renderizar(db, chave, contexto)
    return enviar_email(destinatario or "", assunto, texto, html, anexos=anexos)


def listar(db: Session) -> list[dict]:
    """Catálogo + estado atual, para a tela do RH."""
    personalizados = {t.chave: t for t in db.scalars(select(EmailTemplate)).all()}
    saida = []
    for m in CATALOGO:
        t = personalizados.get(m.chave)
        assunto, corpo, botao = texto_vigente(db, m.chave)
        saida.append({
            "chave": m.chave, "rotulo": m.rotulo, "grupo": m.grupo,
            "quando": m.quando, "critico": m.critico, "editavel": m.editavel,
            "observacao": m.observacao,
            "assunto": assunto, "corpo": corpo, "botao_texto": botao,
            "assunto_padrao": m.assunto, "corpo_padrao": m.corpo,
            "botao_texto_padrao": m.botao_texto,
            "personalizado": t is not None,
            "atualizado_em": t.atualizado_em if t else None,
            "atualizado_por": t.atualizado_por if t else None,
            "variaveis": [{"nome": k, "descricao": v,
                           "obrigatoria": k in m.obrigatorias}
                          for k, v in m.variaveis.items()],
        })
    return saida
