"""O que é obrigatório na admissão — padrão geral + exceção por pessoa (v2.80).

Pedido do Bruno (2026-08-07): *"ter a opção de, no front, por padrão vir marcado
os campos obrigatórios para todos (lógico, aqueles que têm que ser
obrigatórios), mas customizável por candidato, pelo pessoal do RH. Daí ter um
padrão geral lá em configurações"*.

Antes disto a obrigatoriedade era **chumbada em dois lugares**:

  · documentos → `services/slots.py`, `{"tipo": ..., "obrigatorio": True}`;
  · campos     → `api/ficha.py`, `_OBRIGATORIOS_PESSOAIS`/`_OBRIGATORIOS_DOCS`
                 e as listas soltas de endereço, banco, VT e emergência.

Mudar qualquer coisa exigia deploy, e o caso excepcional — a pessoa que
comprovadamente não tem aquele documento — não tinha saída nenhuma.

## As três camadas

    1. PADRÃO DE FÁBRICA (aqui, `PADRAO`)      — o que o sistema traz
    2. PADRÃO DA CASA (config dinâmica)        — o RH muda para TODOS, sem deploy
    3. EXCEÇÃO DA PESSOA (`Candidato.exigencias`) — o RH decide para UMA

A mais específica vence, como a herança de `meses_validade_de` (Desenvolvimento)
e a de roteiro de entrevista (v2.66). Ausência em qualquer nível significa
"herda de cima", nunca "não é obrigatório" — a diferença importa: `False`
explícito é uma DECISÃO de dispensar, e `None` é silêncio.

## O que NÃO é configurável, e por quê

`SEMPRE_OBRIGATORIOS` não entra na tela. Não é preciosismo:

  · `aceite_lgpd` é a BASE LEGAL do tratamento de dados — sem ele o sistema não
    pode nem guardar a ficha;
  · `pessoais.email` é por onde sai o código de assinatura eletrônica: sem
    e-mail a pessoa não assina nada, e a admissão para no meio;
  · `documentos.cpf` é a chave que casa a pessoa em todo o resto do sistema
    (creche, Tirvu, ponto, importação).

Desmarcar qualquer um dos três não afrouxaria uma exigência — quebraria o
fluxo depois, longe daqui, e o RH não teria como ligar uma coisa à outra.

## O que este módulo NÃO decide

**Se o documento se APLICA àquela pessoa.** Reservista só existe para homem de
18 a 45; laudo PCD só para quem declarou deficiência; certidão de casamento só
para quem é casado. Isso continua em `slots.py`, que conhece a ficha — aqui só
se responde "*sendo aplicável, é obrigatório?*". Misturar as duas perguntas
faria o RH "dispensar" um documento que nem seria pedido.
"""

from sqlalchemy.orm import Session

from app.services.config_dinamica import ler_config

# Chave única na config dinâmica. Guarda o JSON do padrão da casa; ausente ou
# ilegível cai no padrão de fábrica abaixo — configuração ruim não pode travar
# admissão (mesma regra dos templates de e-mail, v2.06).
CHAVE_CONFIG = "exigencias_padrao"

# --------------------------------------------------------------------------
# Padrão de fábrica — o que o sistema traz. Espelha o que estava chumbado antes,
# para que ligar esta leva NÃO mude o comportamento de ninguém.
# --------------------------------------------------------------------------
DOCUMENTOS_PADRAO: dict[str, bool] = {
    "foto_3x4": True,
    "rg": True,
    "cpf_doc": True,
    "ctps_digital": True,
    "pis_comprovante": True,
    "titulo_eleitor_doc": True,
    "comp_endereco": True,
    "nada_consta_eleitoral": True,
    "nada_consta_criminal": True,
    # Opcionais por decisão do RH (2026-07-15): nem todo cargo exige.
    "comp_escolaridade": False,
    "habilitacao_prof": False,
    "diplomas": False,
    # Condicionais: só aparecem para quem se aplica (slots.py decide isso), e
    # quando aparecem são obrigatórios.
    "reservista": True,
    "laudo_pcd": True,
    "cert_casamento": True,
    "cartao_vt": True,
    "cert_nascimento_dep": True,
    "cartao_vacina_dep": True,
    "declaracao_escolar_dep": True,
}

CAMPOS_PADRAO: dict[str, bool] = {
    # pessoais
    "pessoais.data_nascimento": True, "pessoais.sexo": True,
    "pessoais.identidade_genero": True, "pessoais.cor_raca": True,
    "pessoais.nacionalidade": True, "pessoais.naturalidade_cidade": True,
    "pessoais.naturalidade_uf": True, "pessoais.estado_civil": True,
    "pessoais.escolaridade": True, "pessoais.pcd": True,
    # documentos
    "documentos.rg_numero": True, "documentos.rg_orgao_emissor": True,
    "documentos.rg_data_expedicao": True, "documentos.pis_nis_pasep": True,
    "documentos.titulo_eleitor_numero": True, "documentos.titulo_eleitor_zona": True,
    "documentos.titulo_eleitor_secao": True,
    # endereço
    "endereco.cep": True, "endereco.bairro": True, "endereco.cidade": True,
    "endereco.uf": True, "endereco.logradouro": True, "endereco.numero": True,
    # trabalho e banco
    "trabalho_banco.tamanho_calca": True, "trabalho_banco.tamanho_camisa": True,
    "trabalho_banco.tamanho_calcado": True, "trabalho_banco.banco": True,
    "trabalho_banco.pix_tipo": True, "trabalho_banco.pix_chave": True,
    # vale-transporte e emergência
    "vt.optante": True,
    "emergencia.usa_medicamento_continuo": True,
    "emergencia.condicoes_medicas": True,
    "emergencia.contatos": True,
}

# Rótulos legíveis para a tela — o RH não deve ver `trabalho_banco.pix_tipo`.
ROTULOS: dict[str, str] = {
    "foto_3x4": "Foto 3x4", "rg": "RG", "cpf_doc": "CPF (documento)",
    "ctps_digital": "CTPS Digital", "pis_comprovante": "Comprovante de PIS/NIS",
    "titulo_eleitor_doc": "Título de eleitor", "comp_endereco": "Comprovante de endereço",
    "nada_consta_eleitoral": "Nada consta eleitoral",
    "nada_consta_criminal": "Nada consta criminal",
    "comp_escolaridade": "Comprovante de escolaridade",
    "habilitacao_prof": "Habilitação profissional", "diplomas": "Diplomas",
    "reservista": "Certificado de reservista", "laudo_pcd": "Laudo (PCD)",
    "cert_casamento": "Certidão de casamento", "cartao_vt": "Cartão do VT (DFTrans)",
    "cert_nascimento_dep": "Certidão de nascimento do dependente",
    "cartao_vacina_dep": "Cartão de vacina do dependente",
    "declaracao_escolar_dep": "Declaração escolar do dependente",
    "pessoais.data_nascimento": "Data de nascimento", "pessoais.sexo": "Sexo",
    "pessoais.identidade_genero": "Identidade de gênero",
    "pessoais.cor_raca": "Cor/raça", "pessoais.nacionalidade": "Nacionalidade",
    "pessoais.naturalidade_cidade": "Naturalidade (cidade)",
    "pessoais.naturalidade_uf": "Naturalidade (UF)",
    "pessoais.estado_civil": "Estado civil", "pessoais.escolaridade": "Escolaridade",
    "pessoais.pcd": "Declara deficiência (PCD)",
    "documentos.rg_numero": "RG — número",
    "documentos.rg_orgao_emissor": "RG — órgão emissor",
    "documentos.rg_data_expedicao": "RG — data de expedição",
    "documentos.pis_nis_pasep": "PIS/NIS/PASEP",
    "documentos.titulo_eleitor_numero": "Título — número",
    "documentos.titulo_eleitor_zona": "Título — zona",
    "documentos.titulo_eleitor_secao": "Título — seção",
    "endereco.cep": "CEP", "endereco.bairro": "Bairro", "endereco.cidade": "Cidade",
    "endereco.uf": "UF", "endereco.logradouro": "Logradouro", "endereco.numero": "Número",
    "trabalho_banco.tamanho_calca": "Tamanho da calça",
    "trabalho_banco.tamanho_camisa": "Tamanho da camisa",
    "trabalho_banco.tamanho_calcado": "Tamanho do calçado",
    "trabalho_banco.banco": "Banco", "trabalho_banco.pix_tipo": "Tipo da chave PIX",
    "trabalho_banco.pix_chave": "Chave PIX",
    "vt.optante": "Optante do vale-transporte",
    "emergencia.usa_medicamento_continuo": "Usa medicamento contínuo",
    "emergencia.condicoes_medicas": "Condições médicas",
    "emergencia.contatos": "Contato de emergência",
}

# Não entram na tela — ver o cabeçalho do módulo.
SEMPRE_OBRIGATORIOS = frozenset({
    "aceite_lgpd", "pessoais.email", "documentos.cpf",
})


def _padrao_da_casa(db: Session) -> dict:
    """O que o RH configurou para TODOS. Ilegível ou ausente = padrão de fábrica.

    Nunca levanta: configuração quebrada não pode travar uma admissão (mesma
    regra do fallback dos templates de e-mail, v2.06).
    """
    import json
    bruto = ler_config(db, (CHAVE_CONFIG,)).get(CHAVE_CONFIG)
    if not bruto:
        return {}
    try:
        dados = json.loads(bruto)
        return dados if isinstance(dados, dict) else {}
    except (ValueError, TypeError):
        return {}


def _resolver(chave: str, padrao_fabrica: dict, casa: dict, pessoa: dict,
              grupo: str) -> bool:
    """A camada mais específica vence; ausência HERDA de cima.

    `None` e ausência são a mesma coisa aqui — "não decidi, use o de cima".
    Só `True`/`False` explícitos decidem. Sem isso, um `{}` gravado por acidente
    dispensaria tudo.
    """
    if chave in SEMPRE_OBRIGATORIOS:
        return True
    for fonte in ((pessoa or {}).get(grupo) or {}, (casa or {}).get(grupo) or {}):
        v = fonte.get(chave)
        if isinstance(v, bool):
            return v
    return bool(padrao_fabrica.get(chave, False))


def documento_obrigatorio(db: Session, candidato, chave: str) -> bool:
    """Este documento é obrigatório PARA ESTA PESSOA?

    Só responde sobre obrigatoriedade — se o documento se APLICA a ela (homem
    de 18-45 para reservista, casado para certidão) continua sendo do
    `slots.py`, que conhece a ficha.
    """
    return _resolver(chave, DOCUMENTOS_PADRAO, _padrao_da_casa(db),
                     getattr(candidato, "exigencias", None) or {}, "documentos")


def campo_obrigatorio(db: Session, candidato, chave: str) -> bool:
    """Este campo da ficha é obrigatório PARA ESTA PESSOA?"""
    return _resolver(chave, CAMPOS_PADRAO, _padrao_da_casa(db),
                     getattr(candidato, "exigencias", None) or {}, "campos")


def mapa_documentos(db: Session, candidato=None) -> dict[str, bool]:
    """Resolve TODOS os documentos de uma vez.

    Existe para o `slots.py`, que percorre a lista inteira a cada autosave (a
    cada 900ms no wizard): chamar `documento_obrigatorio` item a item releria a
    config a cada chamada. Uma leitura, um dicionário.
    """
    casa = _padrao_da_casa(db)
    pessoa = (getattr(candidato, "exigencias", None) or {}) if candidato else {}
    return {c: _resolver(c, DOCUMENTOS_PADRAO, casa, pessoa, "documentos")
            for c in DOCUMENTOS_PADRAO}


def mapa_campos(db: Session, candidato=None) -> dict[str, bool]:
    """Resolve TODOS os campos de uma vez (mesmo motivo do `mapa_documentos`)."""
    casa = _padrao_da_casa(db)
    pessoa = (getattr(candidato, "exigencias", None) or {}) if candidato else {}
    return {c: _resolver(c, CAMPOS_PADRAO, casa, pessoa, "campos")
            for c in CAMPOS_PADRAO}


def dump_para_tela(db: Session, candidato=None) -> dict:
    """O que a tela precisa para montar a configuração.

    Devolve, para cada item: a chave, o rótulo legível, o valor EFETIVO e de
    qual camada ele veio. A origem é o que permite à tela dizer *"este está
    dispensado para esta pessoa"* em vez de só mostrar um check desmarcado —
    sem ela o RH não distingue "o padrão é assim" de "alguém decidiu isto aqui".
    """
    casa = _padrao_da_casa(db)
    pessoa = (getattr(candidato, "exigencias", None) or {}) if candidato else {}

    def _origem(chave: str, grupo: str) -> str:
        if chave in SEMPRE_OBRIGATORIOS:
            return "sistema"
        if isinstance(((pessoa.get(grupo)) or {}).get(chave), bool):
            return "pessoa"
        if isinstance(((casa.get(grupo)) or {}).get(chave), bool):
            return "casa"
        return "fabrica"

    def _lista(padrao: dict, grupo: str) -> list[dict]:
        return [{
            "chave": c,
            "rotulo": ROTULOS.get(c, c),
            "obrigatorio": _resolver(c, padrao, casa, pessoa, grupo),
            "origem": _origem(c, grupo),
            "travado": c in SEMPRE_OBRIGATORIOS,
        } for c in padrao]

    return {
        "documentos": _lista(DOCUMENTOS_PADRAO, "documentos"),
        "campos": _lista(CAMPOS_PADRAO, "campos"),
    }
