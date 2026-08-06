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
    # Aviso interno: qual EVENTO da matriz de `notificacoes.py` governa quem
    # recebe. Preenchido só no grupo "Avisos internos" — os demais vão para uma
    # pessoa específica (candidato, colaborador, assinante), não para uma lista.
    evento: str | None = None
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
             "Seja bem-vindo(a) à Green House! Para concluir a sua admissão, "
             "toque no botão abaixo — pelo celular ou pelo computador. Não "
             "precisa de senha.\n\n"
             "COMECE AGORA: sua contratação só é efetivada depois que você "
             "preencher os dados, assinar os documentos e enviar toda a "
             "documentação. Se precisar interromper, tudo fica salvo — mas "
             "conclua o quanto antes.\n\n"
             "O link é pessoal: não compartilhe com ninguém. Qualquer dúvida, "
             "fale com o RH.",
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
             "Seu benefício de Reembolso-Creche foi ativado. 🎉\n\n"
             "Todo mês, até o dia {{dia}}, envie a comprovação da despesa do mês "
             "anterior, de uma destas formas:\n"
             "- DECLARAÇÃO assinada por quem cuida da criança (cuidador(a)/babá) "
             "— use o modelo que enviamos; ou\n"
             "- NOTA FISCAL da creche/pré-escola, quando for um estabelecimento.\n\n"
             "Sem a comprovação no prazo, o reembolso do mês pode não ser efetuado.",
       variaveis={"nome": "primeiro nome do colaborador",
                  "dia": "dia limite da entrega mensal"},
       exemplo={"nome": "Maria", "dia": "10"}),

    _m(chave="creche_indeferido", grupo="Reembolso-Creche",
       rotulo="Pedido indeferido",
       quando="O RH indefere o pedido de Reembolso-Creche.",
       assunto="Green House — Reembolso-Creche: resultado da análise",
       corpo="Olá, {{nome}}!\n\n"
             "Após a análise, seu pedido de Reembolso-Creche foi indeferido.\n\n"
             "Motivo: {{motivo}}\n\n"
             "Em caso de dúvida, procure o RH.",
       variaveis={"nome": "primeiro nome", "motivo": "motivo do indeferimento"},
       obrigatorias=("motivo",),
       exemplo={"nome": "Maria", "motivo": "A criança já completou 5 anos."}),

    _m(chave="creche_suspenso", grupo="Reembolso-Creche",
       rotulo="Benefício suspenso ou encerrado",
       quando="O RH suspende ou encerra o benefício.",
       assunto="Green House — Reembolso-Creche {{verbo}}",
       corpo="Olá, {{nome}}!\n\n"
             "Seu Reembolso-Creche foi {{verbo}}.\n\n"
             "Motivo: {{motivo}}\n\n"
             "Você não precisa mais enviar a comprovação mensal. Em caso de "
             "dúvida, procure o RH.",
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
             "Sua avaliação de desempenho foi registrada após a conversa de "
             "feedback.\n\n"
             "Você pode ler e escrever a sua manifestação até {{prazo}} — "
             "concordando ou não.\n\n"
             "Registrar sua opinião é um direito seu.",
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
             "{{titulo}} {{quando}} — validade até {{validade}}.\n\n"
             "Para renovar, envie no portal: documento com foto (RG ou CNH), "
             "certificado de formação e atestado de saúde ocupacional.\n\n"
             "Assim que estiver tudo certo, o RH providencia a matrícula na "
             "reciclagem.",
       variaveis={"primeiro_nome": "primeiro nome", "titulo": "nome do certificado",
                  "quando": "'vence em N dias' ou 'venceu há N dias'",
                  "validade": "data de validade",
                  "link": "endereço do portal"},
       botao_texto="Enviar meus documentos", botao_url_var="link",
       exemplo={"primeiro_nome": "Maria", "titulo": "Brigada de Incêndio",
                "quando": "vence em 30 dias", "validade": "30/08/2026",
                "link": "https://exemplo/meu"}),

    # ----------------------------------------------------------- entrevistas
    # v2.66, § 14.4. Pedido do Bruno: *"lembrete por email, sim. convite de
    # calendário, sim. considere que pode ser entrevista online (pelo teams) ou
    # presencial"*.
    #
    # **`{{onde}}` é uma variável PRONTA, montada em Python** conforme a
    # modalidade — endereço no presencial, link no online. É a regra da v2.06:
    # o template é APRESENTAÇÃO, nunca decisão. Se `local` e `link_reuniao`
    # fossem duas variáveis soltas no corpo, o RH teria que escrever um texto
    # que serve aos dois casos e um deles sairia vazio — "Endereço:" seguido de
    # nada, num e-mail que a pessoa usa para saber aonde ir.
    _m(chave="entrevista_marcada", grupo="Entrevistas",
       rotulo="Entrevista marcada",
       quando="O RH marca a entrevista (e a cada remarcação). Leva o convite "
              "de calendário (.ics) anexado.",
       assunto="Green House — sua entrevista em {{data_hora}}",
       corpo="Olá, {{primeiro_nome}}!\n\n"
             "Sua entrevista com a Green House está marcada para "
             "{{data_hora}}.\n\n"
             "{{onde}}\n\n"
             "Leve um documento com foto. Se não puder comparecer, responda "
             "este e-mail — remarcar é tranquilo, faltar sem avisar atrapalha "
             "quem está esperando.\n\n"
             "O convite em anexo entra direto na sua agenda.",
       variaveis={"primeiro_nome": "primeiro nome da pessoa",
                  "nome": "nome completo",
                  "data_hora": "data e hora da entrevista (dd/mm/aaaa às HH:MM)",
                  "onde": "onde é: o endereço (presencial) ou o link da reunião "
                          "(online) — montado pelo sistema conforme a modalidade",
                  "vaga": "título da vaga, quando houver"},
       # `data_hora` e `onde` são o e-mail INTEIRO: sem eles a pessoa recebe um
       # aviso que não diz quando nem aonde ir.
       obrigatorias=("data_hora", "onde"),
       exemplo={"primeiro_nome": "Maria", "nome": "Maria Souza",
                "data_hora": "12/08/2026 às 14:00",
                "onde": "É presencial, em: SIA Trecho 3, Lote 625 — Brasília/DF",
                "vaga": "Vigia noturno"}),

    _m(chave="entrevista_lembrete", grupo="Entrevistas",
       rotulo="Lembrete da entrevista (véspera)",
       quando="O worker diário avisa cerca de 24h antes da entrevista marcada. "
              "Uma vez só por entrevista.",
       assunto="Green House — lembrete: sua entrevista é {{data_hora}}",
       corpo="Olá, {{primeiro_nome}}!\n\n"
             "Passando para lembrar da sua entrevista: {{data_hora}}.\n\n"
             "{{onde}}\n\n"
             "Leve um documento com foto. Se algo mudou e você não puder vir, "
             "responda este e-mail.",
       variaveis={"primeiro_nome": "primeiro nome da pessoa",
                  "nome": "nome completo",
                  "data_hora": "data e hora da entrevista (dd/mm/aaaa às HH:MM)",
                  "onde": "onde é: o endereço (presencial) ou o link da reunião "
                          "(online) — montado pelo sistema conforme a modalidade",
                  "vaga": "título da vaga, quando houver"},
       obrigatorias=("data_hora", "onde"),
       exemplo={"primeiro_nome": "Maria", "nome": "Maria Souza",
                "data_hora": "12/08/2026 às 14:00",
                "onde": "É online. Link da reunião: https://teams.exemplo/abc",
                "vaga": "Vigia noturno"}),

    _m(chave="entrevista_cancelada", grupo="Entrevistas",
       rotulo="Entrevista cancelada",
       quando="O RH cancela uma entrevista que já tinha convite enviado. Leva o "
              "cancelamento de calendário (.ics) anexado.",
       assunto="Green House — sua entrevista de {{data_hora}} foi cancelada",
       corpo="Olá, {{primeiro_nome}}!\n\n"
             "A entrevista que estava marcada para {{data_hora}} foi "
             "cancelada.\n\n"
             "Isso não encerra o seu cadastro conosco: seu currículo continua "
             "na nossa base e podemos procurá-lo para outras oportunidades.\n\n"
             "O anexo remove o compromisso da sua agenda.",
       variaveis={"primeiro_nome": "primeiro nome da pessoa",
                  "nome": "nome completo",
                  "data_hora": "data e hora que estava marcada",
                  "vaga": "título da vaga, quando houver"},
       obrigatorias=("data_hora",),
       exemplo={"primeiro_nome": "Maria", "nome": "Maria Souza",
                "data_hora": "12/08/2026 às 14:00", "vaga": "Vigia noturno"}),

    _m(chave="desenvolvimento_devolvido", grupo="Colaborador",
       rotulo="Curso/certificado devolvido para ajuste",
       quando="O RH devolve um documento do colaborador para correção.",
       assunto="Green House — precisamos de um ajuste no seu envio",
       corpo="Olá, {{primeiro_nome}}!\n\n"
             "Sobre {{titulo}}, precisamos de um ajuste:\n\n"
             "{{motivo}}\n\n"
             "Acesse o portal para corrigir e reenviar.",
       variaveis={"primeiro_nome": "primeiro nome",
                  "titulo": "título do curso/certificado",
                  "motivo": "motivo informado pelo RH",
                  "link": "endereço do portal"},
       botao_texto="Corrigir e reenviar", botao_url_var="link",
       exemplo={"primeiro_nome": "Maria", "titulo": "NR-35",
                "motivo": "o certificado está sem a data de conclusão",
                "link": "https://exemplo/meu"}),

    _m(chave="desenvolvimento_recusado", grupo="Colaborador",
       rotulo="Curso/certificado recusado",
       quando="O RH recusa um documento enviado pelo colaborador (terminal).",
       assunto="Green House — sobre o seu envio",
       corpo="Olá, {{primeiro_nome}}!\n\n"
             "{{titulo}} não pôde ser aceito.\n\n"
             "{{motivo}}\n\n"
             "Em caso de dúvida, fale com o RH.",
       variaveis={"primeiro_nome": "primeiro nome",
                  "titulo": "título do curso/certificado",
                  "motivo": "motivo informado pelo RH"},
       exemplo={"primeiro_nome": "Maria", "titulo": "NR-35",
                "motivo": "o documento enviado não é um certificado."}),

    # ------------------------------------------------ códigos de acesso (OTP)
    # CRÍTICOS: sem {{codigo}} o e-mail sai vazio e ninguém entra. A validação
    # de obrigatórias é o que impede o RH de se trancar para fora sem perceber.
    _m(chave="assinatura_codigo_lote", grupo="Códigos de acesso", critico=True,
       rotulo="Código para assinar as fichas da admissão",
       quando="O candidato pede o código para assinar os documentos da admissão.",
       assunto="Green House — Código de assinatura dos documentos admissionais",
       corpo="Prezado(a) {{nome}},\n\n"
             "Sua assinatura eletrônica é: {{codigo}}\n\n"
             "Este código vale por {{ttl}} minutos e assina os documentos "
             "abaixo:\n\n"
             "{{documentos}}\n\n"
             "Se não foi você que pediu, ignore esta mensagem.",
       variaveis={"nome": "nome completo", "codigo": "código de 6 dígitos",
                  "ttl": "minutos de validade",
                  "documentos": "lista dos documentos (montada pelo sistema)"},
       obrigatorias=("codigo", "documentos"),
       exemplo={"nome": "Maria Souza", "codigo": "123456", "ttl": "10",
                "documentos": "- Ficha de cadastro\n- Termo de VT"}),

    _m(chave="assinatura_codigo_documento", grupo="Códigos de acesso", critico=True,
       rotulo="Código para assinar um documento",
       quando="O candidato pede o código para assinar um documento avulso.",
       assunto="🌱 Green House — seu código para assinar: {{documento}}",
       corpo="Seu código para assinar \"{{documento}}\" é: {{codigo}}\n\n"
             "Ele vale por {{ttl}} minutos.",
       variaveis={"documento": "título do documento", "codigo": "código de 6 dígitos",
                  "ttl": "minutos de validade"},
       obrigatorias=("codigo",),
       exemplo={"documento": "Termo de Confidencialidade", "codigo": "123456",
                "ttl": "10"}),

    _m(chave="assinatura_externa_codigo", grupo="Códigos de acesso", critico=True,
       rotulo="Código para assinante externo",
       quando="Um assinante de fora da empresa pede o código para assinar.",
       assunto="Green House — código para assinar o documento",
       corpo="Olá, {{nome}}!\n\n"
             "Use o código abaixo para confirmar e assinar o documento:\n\n"
             "{{codigo}}\n\n"
             "Ele vale por {{ttl}} minutos.",
       variaveis={"nome": "nome do assinante externo", "codigo": "código de 6 dígitos",
                  "ttl": "minutos de validade"},
       obrigatorias=("codigo",),
       exemplo={"nome": "João Prestador", "codigo": "123456", "ttl": "10"}),

    _m(chave="autorizacao_equipe_codigo", grupo="Códigos de acesso", critico=True,
       rotulo="Código de autorização da equipe",
       quando="Um representante confirma a autorização permanente de assinatura.",
       assunto="Green House — confirme sua autorização de assinatura",
       corpo="Olá, {{nome}}!\n\n"
             "Você foi indicado(a) como {{papel}} para assinar documentos em "
             "nome da equipe. Confirme com o código abaixo:\n\n"
             "{{codigo}}\n\n"
             "Ele vale por {{ttl}} minutos. Confirmar é um ato de vontade seu: "
             "a partir daí os documentos do seu papel saem sob a sua "
             "autorização permanente.",
       variaveis={"nome": "nome do representante", "papel": "papel na assinatura",
                  "codigo": "código de 6 dígitos", "ttl": "minutos de validade"},
       obrigatorias=("codigo",),
       exemplo={"nome": "Ana Diretora", "papel": "Contratante",
                "codigo": "123456", "ttl": "10"}),

    _m(chave="teste_codigo", grupo="Códigos de acesso", critico=True,
       rotulo="Código de confirmação do teste",
       quando="O participante confirma a identidade para começar um teste.",
       assunto="Green House — código de confirmação para o seu teste",
       corpo="Olá, {{primeiro_nome}}!\n\n"
             "Seu código de confirmação é: {{codigo}}\n\n"
             "Ele vale por {{ttl}} minutos.",
       variaveis={"primeiro_nome": "primeiro nome", "codigo": "código de 6 dígitos",
                  "ttl": "minutos de validade"},
       obrigatorias=("codigo",),
       exemplo={"primeiro_nome": "Maria", "codigo": "123456", "ttl": "15"}),

    _m(chave="creche_codigo", grupo="Códigos de acesso", critico=True,
       rotulo="Código do Reembolso-Creche",
       quando="O colaborador informa o CPF no link público do creche.",
       assunto="Green House — código para o levantamento do Reembolso-Creche",
       corpo="Olá, {{primeiro_nome}}!\n\n"
             "Use o código abaixo para confirmar sua identidade no levantamento "
             "do Reembolso-Creche (IN SEGES/MGI nº 147/2026):\n\n"
             "{{codigo}}\n\n"
             "Ou toque no botão abaixo: ele já abre o seu levantamento, sem "
             "precisar digitar nada. O código e o botão valem por {{ttl}} "
             "minutos.\n\n"
             "Verifique também a sua caixa de spam — a mensagem pode ter ido "
             "para lá.",
       variaveis={"primeiro_nome": "primeiro nome", "codigo": "código de 6 dígitos",
                  "ttl": "minutos de validade",
                  "link": "link que abre o levantamento direto"},
       obrigatorias=("codigo",),
       botao_texto="Entrar no meu levantamento", botao_url_var="link",
       exemplo={"primeiro_nome": "Maria", "codigo": "123456", "ttl": "15",
                "link": "https://exemplo/creche?t=abc"}),

    _m(chave="portal_codigo", grupo="Códigos de acesso", critico=True,
       rotulo="Código de acesso ao portal do colaborador",
       quando="O colaborador informa o CPF em /meu.",
       assunto="Green House — seu código de acesso",
       corpo="Olá, {{primeiro_nome}}!\n\n"
             "Use o código abaixo para entrar no seu portal:\n\n"
             "{{codigo}}\n\n"
             "Ou toque no botão abaixo: ele já abre o seu portal, sem precisar "
             "digitar nada. O código e o botão valem por {{ttl}} minutos.\n\n"
             "Se não foi você que pediu, ignore este e-mail.",
       variaveis={"primeiro_nome": "primeiro nome", "codigo": "código de 6 dígitos",
                  "ttl": "minutos de validade",
                  "link": "link que abre o portal direto"},
       obrigatorias=("codigo",),
       botao_texto="Entrar no meu portal", botao_url_var="link",
       exemplo={"primeiro_nome": "Maria", "codigo": "123456", "ttl": "15",
                "link": "https://exemplo/meu?t=abc"}),

    _m(chave="rh_redefinir_senha", grupo="Códigos de acesso", critico=True,
       rotulo="Redefinição de senha do painel",
       quando="Alguém do RH pede para redefinir a senha do painel.",
       assunto="🔐 Green House — redefinição de senha do painel",
       corpo="Olá, {{primeiro_nome}}!\n\n"
             "Recebemos um pedido para redefinir a sua senha do painel do RH. "
             "Toque no botão abaixo para escolher uma nova.\n\n"
             "O link vale por {{ttl}} minutos e só pode ser usado uma vez.\n\n"
             "Se não foi você que pediu, ignore este e-mail — sua senha atual "
             "continua valendo.",
       variaveis={"primeiro_nome": "primeiro nome", "link": "link de redefinição",
                  "ttl": "minutos de validade"},
       obrigatorias=("link",),
       botao_texto="Escolher nova senha", botao_url_var="link",
       exemplo={"primeiro_nome": "Bruno", "link": "https://exemplo/rh?redefinir=abc",
                "ttl": "30"}),

    _m(chave="rh_usuario_criado", grupo="Códigos de acesso", critico=True,
       rotulo="Acesso ao painel criado",
       quando="O RH cadastra uma pessoa nova no painel.",
       assunto="🌱 Green House — seu acesso ao Portal de Admissão",
       corpo="Olá, {{primeiro_nome}}!\n\n"
             "{{quem_criou}} criou o seu acesso ao painel do RH.\n\n"
             "Seu usuário é: {{email}}\n\n"
             "Use a opção \"Esqueci minha senha\" na tela de login para "
             "definir a sua senha.",
       variaveis={"primeiro_nome": "primeiro nome", "email": "e-mail de login",
                  "quem_criou": "quem cadastrou", "link": "endereço do painel"},
       obrigatorias=("email",),
       botao_texto="Acessar o painel", botao_url_var="link",
       exemplo={"primeiro_nome": "Ana", "email": "ana@greenhousedf.com.br",
                "quem_criou": "Bruno", "link": "https://exemplo/rh"}),

    # ---------------------------------------------------- assinatura (envios)
    _m(chave="assinatura_vias_assinadas", grupo="Assinatura",
       rotulo="Vias assinadas (com os PDFs em anexo)",
       quando="Logo após o candidato assinar — leva as vias dele em anexo.",
       assunto="Green House — Seus documentos assinados (vias do colaborador)",
       corpo="Prezado(a) {{nome}},\n\n"
             "Confirmamos a assinatura eletrônica dos seus documentos "
             "admissionais. As vias assinadas seguem ANEXAS a esta mensagem "
             "para a sua guarda:\n\n"
             "{{documentos}}\n\n"
             "Próximo passo obrigatório: envie a sua documentação pelo mesmo "
             "link da admissão. Sua contratação somente será efetivada após o "
             "envio completo.",
       variaveis={"nome": "nome completo",
                  "documentos": "lista dos documentos (montada pelo sistema)"},
       obrigatorias=("documentos",),
       exemplo={"nome": "Maria Souza",
                "documentos": "- Ficha de cadastro\n- Termo de VT"}),

    _m(chave="modelo_para_assinar", grupo="Assinatura",
       rotulo="Documento de modelo aguarda assinatura",
       quando="O RH envia um documento de modelo para a pessoa assinar.",
       assunto="Green House — documento aguarda sua assinatura: {{documento}}",
       corpo="Prezado(a) {{nome}},\n\n"
             "O documento \"{{documento}}\" aguarda a sua assinatura "
             "eletrônica.\n\n"
             "É rápido e pode ser feito pelo celular.",
       variaveis={"nome": "nome completo", "documento": "título do documento",
                  "link": "link para assinar"},
       botao_texto="Assinar o documento", botao_url_var="link",
       exemplo={"nome": "Maria Souza", "documento": "Acordo de Teletrabalho",
                "link": "https://exemplo/c/abc"}),

    _m(chave="modelo_anexo", grupo="Assinatura",
       rotulo="Documento de modelo em anexo (sem assinatura)",
       quando="O RH envia um documento de modelo apenas para conhecimento.",
       assunto="Green House — {{documento}}",
       corpo="Prezado(a) {{nome}},\n\n"
             "Segue em anexo o documento \"{{documento}}\".",
       variaveis={"nome": "nome completo", "documento": "título do documento"},
       exemplo={"nome": "Maria Souza", "documento": "Comunicado Interno"}),

    _m(chave="assinatura_externa_convite", grupo="Assinatura", critico=True,
       rotulo="Convite para assinante externo",
       quando="Um documento em roteiro chega à vez de um assinante de fora.",
       assunto="Green House — documento aguarda sua assinatura ({{papel}})",
       corpo="Olá, {{nome}}!\n\n"
             "Um documento da Green House aguarda a sua assinatura como "
             "{{papel}}.\n\n"
             "O link é pessoal e vale só para você.",
       variaveis={"nome": "nome do assinante externo", "papel": "papel na assinatura",
                  "link": "link de assinatura"},
       obrigatorias=("link",),
       botao_texto="Ver e assinar o documento", botao_url_var="link",
       exemplo={"nome": "João Prestador", "papel": "Testemunha",
                "link": "https://exemplo/assinar/abc"}),

    # ---------------------------------------------------------- creche (resto)
    _m(chave="creche_aguardando_contrato", grupo="Reembolso-Creche",
       rotulo="Aprovado, aguardando o contrato",
       quando="O RH aprova mas o pagamento depende de repactuação do contrato.",
       assunto="Green House — Reembolso-Creche: aprovado, aguardando o contrato",
       corpo="Olá, {{nome}}!\n\n"
             "Seu pedido de Reembolso-Creche foi APROVADO.\n\n"
             "O pagamento depende de um ajuste no contrato com o órgão, que já "
             "está em andamento. Assim que concluído, o benefício passa a ser "
             "pago — e avisamos você.\n\n"
             "Não é preciso fazer nada agora.",
       variaveis={"nome": "primeiro nome"},
       exemplo={"nome": "Maria"}),

    _m(chave="creche_incluir_crianca", grupo="Reembolso-Creche",
       rotulo="Reaberto para incluir criança",
       quando="O RH reabre o benefício para o colaborador incluir outra criança.",
       assunto="Green House — Reembolso-Creche: inclua a nova criança",
       corpo="Olá, {{nome}}!\n\n"
             "Seu Reembolso-Creche foi reaberto para você incluir a nova "
             "criança.\n\n"
             "Atenção: enquanto o pedido estiver em análise, o benefício sai "
             "da folha — reenvie o quanto antes para voltar a receber.",
       variaveis={"nome": "primeiro nome", "link": "endereço do link do creche"},
       botao_texto="Incluir a criança", botao_url_var="link",
       exemplo={"nome": "Maria", "link": "https://exemplo/creche"}),

    _m(chave="creche_sem_direito", grupo="Reembolso-Creche",
       rotulo="Registro de 'não faço jus'",
       quando="Fica registrado que o colaborador declarou não ter direito.",
       assunto="Green House — Reembolso-Creche: registro de 'sem direito'",
       corpo="Olá, {{nome}}!\n\n"
             "Registramos que você declarou não fazer jus ao Reembolso-Creche "
             "no momento.\n\n"
             "Se a situação mudar (nova criança, mudança de posto), procure o "
             "RH: dá para reabrir o pedido a qualquer tempo.",
       variaveis={"nome": "primeiro nome"},
       exemplo={"nome": "Maria"}),

    # ------------------------------------------------------- avisos internos
    # Vão para a EQUIPE (RH, operacional, líder de brigada) pela matriz de
    # `services/notificacoes.py` — quem recebe cada um se configura em
    # Configurações → Avisos internos. O texto fica editável porque quem
    # recebe nem sempre é quem conhece o sistema: o Gabriel e o Vitor recebem
    # o de uniforme, o líder de brigada recebe o de certificação.
    _m(chave="aviso_envio_concluido", grupo="Avisos internos",
       evento="envio_concluido",
       rotulo="Candidato concluiu o envio",
       quando="O candidato clica em 'CONCLUÍ MEU ENVIO'.",
       assunto="📥 Documentação completa: {{nome}}",
       corpo="O candidato {{nome}} concluiu o envio da documentação.\n\n"
             "Acesse o painel do RH para revisar.",
       variaveis={"nome": "nome do candidato", "link": "endereço do painel"},
       botao_texto="Revisar no painel", botao_url_var="link",
       exemplo={"nome": "Maria Souza", "link": "https://exemplo/rh"}),

    _m(chave="aviso_documento_reenviado", grupo="Avisos internos",
       evento="envio_concluido",
       rotulo="Documento reenviado por quem já foi aprovado",
       quando="Um candidato já aprovado reenvia um documento que fora rejeitado.",
       assunto="🔁 Documento reenviado (já aprovado): {{nome}}",
       corpo="O colaborador {{nome}}, já aprovado, reenviou um documento que "
             "havia sido rejeitado.\n\n"
             "Reavalie no painel do RH.",
       variaveis={"nome": "nome do colaborador", "link": "endereço do painel"},
       botao_texto="Reavaliar no painel", botao_url_var="link",
       exemplo={"nome": "Maria Souza", "link": "https://exemplo/rh"}),

    _m(chave="aviso_uniforme", grupo="Avisos internos",
       evento="uniforme_pendente",
       rotulo="Uniforme: tamanhos de um novo admitido",
       quando="O candidato conclui a admissão tendo informado os tamanhos.",
       assunto="👕 Uniforme: {{nome}} informou os tamanhos",
       corpo="{{nome}} concluiu a admissão e informou os tamanhos de uniforme.\n\n"
             "A lista completa, com posto e medidas, fica na tela Uniformes — "
             "não vai por e-mail.",
       variaveis={"nome": "nome do colaborador",
                  "link": "endereço da tela de Uniformes"},
       botao_texto="Ver a lista de uniformes", botao_url_var="link",
       exemplo={"nome": "Maria Souza", "link": "https://exemplo/rh/uniformes"}),

    _m(chave="aviso_telemetria_alerta", grupo="Avisos internos",
       evento="telemetria_alerta",
       rotulo="⚠️ Telemetria: algo quebrou ou travou",
       quando="Uma regra de alerta dispara (verificação a cada 15 minutos).",
       assunto="⚠️ {{tipo}}: {{regra}}",
       # A lista chega PRONTA do Python: o template é apresentação, nunca
       # decisão — a regra do que entra continua no código (v2.06).
       corpo="A vigilância do sistema encontrou algo que merece atenção.\n\n"
             "Regra: {{regra}}\n"
             "Ocorrências: {{quantidade}}\n\n"
             "{{lista}}\n\n"
             "Isto é um aviso automático a partir da telemetria — ninguém "
             "precisou reclamar para ele chegar. Confira os detalhes em "
             "Configurações → Telemetria.",
       variaveis={"regra": "nome da regra que disparou",
                  "tipo": "tipo do alerta (erro novo, lentidão…)",
                  "quantidade": "quantos itens dispararam",
                  "lista": "os itens, um por linha (montado pelo sistema)",
                  "link": "endereço da tela de Telemetria"},
       obrigatorias=("lista",),
       botao_texto="Ver na telemetria", botao_url_var="link",
       exemplo={"regra": "Erro novo na tela de alguém", "tipo": "Erro novo",
                "quantidade": "1", "link": "https://exemplo/rh/config",
                "lista": "• Cannot read properties of null (reading 'some') — "
                         "em /c/assinatura (3x, 2 pessoa(s))"}),

    _m(chave="aviso_dossie_pronto", grupo="Avisos internos",
       evento="dossie_pronto",
       rotulo="Dossiê de admissão pronto",
       quando="O dossiê completo de um candidato termina de ser gerado.",
       assunto="📄 Dossiê de admissão pronto: {{nome}}",
       corpo="O dossiê completo de {{nome}} foi gerado e está pronto para "
             "download no painel.",
       variaveis={"nome": "nome do candidato", "link": "endereço do painel"},
       botao_texto="Baixar no painel", botao_url_var="link",
       exemplo={"nome": "Maria Souza", "link": "https://exemplo/rh"}),

    _m(chave="aviso_creche_levantamento", grupo="Avisos internos",
       evento="creche_levantamento_enviado",
       rotulo="Reembolso-Creche: levantamento enviado",
       quando="Um colaborador envia (ou reenvia) o levantamento para análise.",
       assunto="👶 Reembolso-Creche: levantamento de {{nome}}",
       corpo="{{nome}} enviou o levantamento do Reembolso-Creche com "
             "{{criancas}} criança(s).\n\n"
             "Analise na tela de Reembolso-Creche.",
       variaveis={"nome": "nome do colaborador",
                  "criancas": "quantas crianças foram cadastradas"},
       exemplo={"nome": "Maria Souza", "criancas": "2"}),

    _m(chave="aviso_logs_periodico", grupo="Avisos internos",
       evento="logs_periodico",
       rotulo="Logs dos serviços (4x ao dia)",
       quando="A cada 6 horas, com o resumo do período e os arquivos em anexo.",
       assunto="🧾 Logs do sistema — {{janela}}",
       corpo="Resumo do período ({{janela}}):\n\n{{resumo}}\n\n"
             "Os arquivos completos vão em anexo (.txt).\n\n"
             "Para filtrar e pesquisar, use Configurações → Logs dos serviços.",
       variaveis={"janela": "período coberto por este envio",
                  "resumo": "linhas, erros e avisos por serviço"},
       exemplo={"janela": "30/07/2026 12h–18h",
                "resumo": "api: 1.240 linhas · 3 erros · 12 avisos"}),

    _m(chave="aviso_talento_cadastrado", grupo="Avisos internos",
       evento="talento_cadastrado",
       rotulo="Banco de Talentos: novo cadastro",
       quando="Alguém se cadastra pelo formulário público do Banco de Talentos.",
       assunto="⭐ Banco de Talentos: {{nome}}",
       corpo="{{nome}} se cadastrou no Banco de Talentos.\n\n"
             "Cargos de interesse: {{cargos}}\n\n"
             "Acesse o painel do RH para ver o cadastro.",
       variaveis={"nome": "nome de quem se cadastrou",
                  "cargos": "cargos de interesse informados"},
       exemplo={"nome": "Maria Souza",
                "cargos": "Recepcionista, Auxiliar de Serviços Gerais"}),

    _m(chave="aviso_desenvolvimento_enviado", grupo="Avisos internos",
       evento="desenvolvimento_enviado",
       rotulo="Colaborador enviou curso ou certificado",
       quando="Alguém envia algo novo pelo portal e a fila de validação cresce.",
       assunto="🎓 {{nome}} enviou um documento",
       corpo="{{nome}} {{acao}} um documento para o Cadastro de "
             "Desenvolvimento: {{titulo}}.\n\n"
             "A fila de validação está na tela de Desenvolvimento.",
       variaveis={"nome": "nome do colaborador",
                  "acao": "'enviou' ou 'reenviou'",
                  "titulo": "título do curso/certificado"},
       exemplo={"nome": "Maria Souza", "acao": "enviou", "titulo": "NR-35"}),

    _m(chave="aviso_match_concluido", grupo="Avisos internos",
       evento="match_vagas_concluido",
       rotulo="Match de Vagas: ranqueamento concluído",
       quando="Termina o ranqueamento de uma vaga contra o Banco de Talentos.",
       assunto="Match de Vagas concluído — {{vaga}}",
       corpo="O ranqueamento da vaga \"{{vaga}}\" terminou.\n\n"
             "{{resumo}}\n\n"
             "Veja o resultado completo em Match de Vagas → Resultados.",
       variaveis={"vaga": "título da vaga",
                  "resumo": "os números do ranqueamento (montados pelo sistema)"},
       obrigatorias=("resumo",),
       exemplo={"vaga": "Recepcionista — INEP",
                "resumo": "- Analisados agora pela IA: 18\n"
                          "- Reaproveitados de análise anterior: 4\n"
                          "- Sem currículo enviado: 9"}),

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
                  contexto: dict, anexos=None, remetente: str | None = None) -> bool:
    """Renderiza e envia. Sem destinatário, `enviar_email` já devolve False.

    `remetente` (v2.67) serve o endereço próprio de recrutamento; vazio mantém
    o remetente padrão do sistema, que é o comportamento de todos os demais
    e-mails.
    """
    assunto, texto, html = renderizar(db, chave, contexto)
    return enviar_email(destinatario or "", assunto, texto, html, anexos=anexos,
                        remetente=remetente)


def listar(db: Session) -> list[dict]:
    """Catálogo + estado atual, para a tela do RH."""
    personalizados = {t.chave: t for t in db.scalars(select(EmailTemplate)).all()}
    # Quem recebe cada AVISO INTERNO — a mesma matriz de Configurações → Avisos
    # internos, exibida aqui para o RH ter o e-mail inteiro num lugar só
    # (pedido de 2026-07-29). É a MESMA fonte: editar aqui ou lá dá no mesmo.
    try:
        from app.services.notificacoes import ler_matriz
        matriz = ler_matriz(db)
    except Exception:  # pragma: no cover — matriz ilegível não derruba a tela
        log.warning("matriz de notificações ilegível na listagem de e-mails")
        matriz = {}
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
            # Aviso interno: quem recebe (vários, separados por vírgula na tela).
            # Nos demais o destinatário é a pessoa do processo, não uma lista.
            "evento": m.evento,
            "destinatarios": (matriz.get(m.evento, {}).get("emails") or []
                              if m.evento else None),
            "destinatarios_herdado": (matriz.get(m.evento, {}).get("herdado")
                                      if m.evento else None),
            "aviso_ativo": (matriz.get(m.evento, {}).get("ativo", True)
                            if m.evento else None),
        })
    return saida
