"""Testes de CONTEÚDO do export do Tirvu — sem banco, sem containers.

A raiz dos feedbacks de 2026-07-24 foi um export que RODAVA mas cujas células
saíam com o valor errado (texto em vez de ID; CTPS série "0000"). O smoke valida
que o arquivo abre; estes testes validam o que vai DENTRO das células.

Rode: PYTHONPATH=. .venv/Scripts/python.exe tests/test_export_tirvu.py
"""

from openpyxl import load_workbook
import io
import pathlib
from datetime import date

from app.services import export_tirvu as t


# ---- CTPS: número = 7 primeiros dígitos do CPF, série = 4 últimos ----
assert t.ctps_do_cpf("123.456.789-09") == ("1234567", "8909"), t.ctps_do_cpf("12345678909")
assert t.ctps_do_cpf("00000000000") == ("0000000", "0000")
assert t.ctps_do_cpf("123") == ("", "")  # CPF inválido não deriva CTPS
assert t.ctps_do_cpf(None) == ("", "")


# ---- normalizador de cargo: colapsa espaço, desacentua, minúsculo ----
assert t.normalizar_cargo("  Analista  DF  Jr ") == "analista df jr"
assert t.normalizar_cargo("Vigía") == t.normalizar_cargo("vigia") == "vigia"
assert t.normalizar_cargo(None) == ""


# ---- linha_tirvu escreve os IDs do Tirvu, não os textos ----
# stubs mínimos: só o que linha_tirvu lê de cada objeto.
class _Stub:
    def __init__(self, **kw):
        self.__dict__.update(kw)


class _DBFake:
    """Devolve objetos por (modelo, id) de um dicionário pré-carregado e resolve
    o de-para de cargo por scalar()."""
    def __init__(self, objetos, cargo_id=None):
        self._objetos = objetos
        self._cargo_id = cargo_id

    def get(self, modelo, ident):
        return self._objetos.get((modelo.__name__, ident))

    def scalar(self, _stmt):
        # usado só por tirvu_id_do_cargo — devolvemos o de-para simulado
        if self._cargo_id is None:
            return None
        return _Stub(tirvu_id=self._cargo_id)


from app.models.candidato import Candidato, Empresa, Jornada, PostoServico
from app.models.ficha import DadosPessoais, DocumentosIdentificacao, Endereco

cid = "cand-1"
cand = _Stub(id=cid, nome_completo="Fulano de Tal", cpf="123.456.789-09",
             cargo_funcao="Analista DF Jr", posto_servico_id="p1", empresa_id="e1",
             jornada_id="j1", registra_ponto=True, celular_whatsapp="(61) 99999-8888",
             salario_base="R$ 2.000,00", matricula="0001234", data_admissao="01/02/2026",
             data_nascimento="10/10/1990")
objetos = {
    ("Candidato", cid): cand,
    ("DadosPessoais", cid): _Stub(sexo=_Stub(value="masculino"), data_nascimento="10/10/1990"),
    ("Endereco", cid): _Stub(logradouro="Rua X", numero="10", complemento="",
                             logradouro_numero_complemento=None, cep="70000-000",
                             bairro="Centro", cidade="Brasília", uf="DF"),
    ("DocumentosIdentificacao", cid): _Stub(cpf="123.456.789-09", ctps_numero="12345678909",
                                            ctps_serie="0000", pis_nis_pasep="12345678901"),
    ("PostoServico", "p1"): _Stub(tirvu_id="49", nome="GHS"),
    ("Empresa", "e1"): _Stub(tirvu_id="1", razao_social="GREEN HOUSE LTDA"),
    ("Jornada", "j1"): _Stub(tirvu_id="246", descricao="GHS SEDE - 2A A 5A ..."),
}
db = _DBFake(objetos, cargo_id="50")

linha = t.linha_tirvu(db, cand, gerar_matricula=False)

# Posto/Cargo/Jornada saem como TEXTO desde 2026-08-08 — o Tirvu MUDOU e passou
# a casar pelo nome (o Bruno testou a importação com o texto na célula e ela foi
# aceita). Até 2026-07-24 era o oposto: colar o texto fazia o Tirvu gravar zero,
# e este mesmo teste cravava os IDs "49"/"50"/"246".
#
# Os stubs têm tirvu_id E texto de propósito: se alguém reverter para o ID, a
# asserção reprova com o valor errado à vista, em vez de passar por ausência.
# Empresa também virou TEXTO (2026-08-08): sai a RAZÃO SOCIAL, não o id "1".
# Este candidato TEM empresa_id, então usa a razão social da empregadora
# vinculada — quem não tem cai no padrão (caso logo abaixo).
assert linha["Empresa"] == "GREEN HOUSE LTDA", linha["Empresa"]
assert linha["Posto de Serviço"] == "GHS", linha["Posto de Serviço"]
assert linha["Cargo"] == "Analista DF Jr", linha["Cargo"]
assert linha["Descrição da Jornada de Trabalho"] == "GHS SEDE - 2A A 5A ...", \
    linha["Descrição da Jornada de Trabalho"]
# CTPS derivada do CPF mesmo com "0000" gravado no banco (export re-deriva)
assert linha["CTPS Número"] == "1234567", linha["CTPS Número"]
assert linha["CTPS Série"] == "8909", linha["CTPS Série"]
# CEP com hífen, cidade preservada com acento, PIS sem máscara
assert linha["Endereço - CEP"] == "70000-000", linha["Endereço - CEP"]
assert linha["Endereço - Cidade"] == "Brasília", linha["Endereço - Cidade"]
assert linha["PIS"] == "12345678901"


# ---- CTPS: sem CPF, cai no gravado (fallback do elif) ----
cand_sem_cpf = _Stub(**{**cand.__dict__, "cpf": ""})
objs_sem_cpf = {
    **objetos,
    ("Candidato", cid): cand_sem_cpf,
    ("DocumentosIdentificacao", cid): _Stub(cpf="", ctps_numero="9998",
                                            ctps_serie="12", pis_nis_pasep="12345678901"),
}
linha_sc = t.linha_tirvu(_DBFake(objs_sem_cpf, cargo_id="50"), cand_sem_cpf,
                         gerar_matricula=False)
assert linha_sc["CTPS Número"] == "9998", linha_sc["CTPS Número"]
assert linha_sc["CTPS Série"] == "12", linha_sc["CTPS Série"]

# CPF INVÁLIDO (não-vazio, ≠11 dígitos) também cai no gravado (B1 da revisão)
cand_cpf_sujo = _Stub(**{**cand.__dict__, "cpf": "123"})
objs_sujo = {
    **objetos,
    ("Candidato", cid): cand_cpf_sujo,
    ("DocumentosIdentificacao", cid): _Stub(cpf="123", ctps_numero="7777",
                                            ctps_serie="55", pis_nis_pasep="1"),
}
linha_sj = t.linha_tirvu(_DBFake(objs_sujo, cargo_id="50"), cand_cpf_sujo,
                         gerar_matricula=False)
assert linha_sj["CTPS Número"] == "7777", linha_sj["CTPS Número"]


# ---- pendência quando falta o VÍNCULO (posto/cargo/jornada; empresa NÃO) ----
# Com o casamento por texto, a pendência mudou de NATUREZA: antes acusava "o ID
# do Tirvu não foi cadastrado"; agora acusa "esta pessoa não tem posto/cargo/
# jornada na ficha". O rótulo acompanhou — dizer "ID Tirvu do posto" mandaria o
# RH procurar no cadastro de IDs, que não é mais onde o problema está.
#
# Repare que o posto e a jornada aqui TÊM tirvu_id e não têm texto: é o inverso
# do stub principal, e reprova quem voltar a ler o ID (a linha sairia
# preenchida e a pendência não dispararia).
# `empresa_id=None` de propósito: é o caso REAL da base (o grupo tem uma
# empregadora só e quase ninguém tem o vínculo preenchido), e é ele que exercita
# a queda no padrão. Sem isso a asserção da razão social passaria pelo vínculo.
cand_sem_vinculo = _Stub(**{**cand.__dict__, "cargo_funcao": "", "empresa_id": None})
db_sem_texto = _DBFake({**objetos,
                        ("Candidato", cid): cand_sem_vinculo,
                        ("Jornada", "j1"): _Stub(tirvu_id="246", descricao=""),
                        ("PostoServico", "p1"): _Stub(tirvu_id="49", nome="")},
                       cargo_id="50")
linha2 = t.linha_tirvu(db_sem_texto, cand_sem_vinculo, gerar_matricula=False)
pend = t.pendencias_linha(linha2)
# Empresa NUNCA falta: sem vínculo (ou com razão social vazia) cai no padrão,
# por isso segue fora da lista de pendências.
assert linha2["Empresa"] == t.EMPRESA_RAZAO_SOCIAL_PADRAO, linha2["Empresa"]
assert "Empresa" not in pend, pend
assert "Posto" in pend, pend
assert "Cargo" in pend, pend
assert "Jornada" in pend, pend


# ---- workbook: aba Plan1, célula do cargo contém o NOME do cargo ----
wb_bytes = t.montar_workbook_tirvu([linha])
wb = load_workbook(io.BytesIO(wb_bytes))
ws = wb.active
assert ws.title == "Plan1", ws.title
cabecalho = [c.value for c in ws[1]]
i_cargo = cabecalho.index("Cargo")
assert ws.cell(row=2, column=i_cargo + 1).value == "Analista DF Jr", \
    ws.cell(row=2, column=i_cargo + 1).value
i_posto = cabecalho.index("Posto de Serviço")
assert ws.cell(row=2, column=i_posto + 1).value == "GHS", \
    ws.cell(row=2, column=i_posto + 1).value


# ===========================================================================
# LAYOUT NOVO — 34 colunas (v3.19, item 16 da 24ª leva)
#
# O fornecedor mandou um modelo novo em 02/09/2026. As 28 primeiras colunas são
# idênticas e na mesma ordem; as seis últimas (AC→AH) são novas e OPCIONAIS.
#
# Os seis campos JÁ eram coletados na ficha — o trabalho foi ligar o que existe
# às colunas novas, sem perguntar nada a ninguém e sem migration de coleta.
# ===========================================================================
print("\n[34 colunas: o layout bate com o arquivo do FORNECEDOR]")

# A referência é o .xlsx oficial, nunca uma lista escrita aqui: cópia à mão
# diverge do modelo na primeira revisão dele e o teste segue verde (v2.54).
#
# ⚠️ O caminho sai de `__file__`, não do diretório atual: este teste roda com o
# CWD em `backend/` e o modelo mora em `docs/`, na raiz do repositório.
MODELO = (pathlib.Path(__file__).resolve().parents[2]
          / "docs" / "Layout de Importação de Admissões (1).xlsx")

# ⚠️ O modelo pode NÃO EXISTIR aqui, e isso é legítimo: dentro do container da
# API este teste roda em `/app`, e a imagem copia só `app/`, `migrations/` e a
# configuração — `docs/` fica de fora DE PROPÓSITO (guarda planilhas com dados de
# gente real, e o repositório é público). Então a comparação com o arquivo do
# fornecedor roda no ambiente de desenvolvimento e é PULADA, com aviso, onde ele
# não está: reprovar ali seria acusar a ausência de um arquivo que nunca deveria
# estar na imagem, e um teste que acusa o certo ensina a ignorar o teste (v2.88).
#
# As asserções que NÃO dependem do arquivo estão logo abaixo e rodam sempre.
if MODELO.exists():
    ws_modelo = load_workbook(MODELO).active
    cabecalho_oficial = [c.value for c in ws_modelo[1] if c.value is not None]

    assert ws_modelo.title == "Plan1", ws_modelo.title
    assert cabecalho_oficial == t.COLUNAS_TIRVU, (
        "COLUNAS_TIRVU divergiu do modelo oficial.\n"
        f"  modelo ({len(cabecalho_oficial)}): {cabecalho_oficial}\n"
        f"  código ({len(t.COLUNAS_TIRVU)}): {t.COLUNAS_TIRVU}")

    # O layout ANTIGO continua sendo o prefixo do novo — é o que sustenta a regra
    # do fornecedor de que a planilha de 28 colunas segue aceita.
    MODELO_ANTIGO = MODELO.parent / "Layout de Importação de Admissões.xlsx"
    if MODELO_ANTIGO.exists():
        antigo = [c.value for c in load_workbook(MODELO_ANTIGO).active[1]
                  if c.value is not None]
        assert t.COLUNAS_TIRVU[:len(antigo)] == antigo, (
            "as 28 primeiras colunas mudaram de nome ou de ordem — o layout "
            "antigo precisa continuar sendo o PREFIXO exato do novo")
    print("  ok      layout conferido contra o arquivo do fornecedor")
else:
    print("  PULADO  o modelo do fornecedor não está neste ambiente"
          f" ({MODELO}); a comparação de layout roda em desenvolvimento")

# Estas NÃO dependem do arquivo e rodam em qualquer ambiente, inclusive no CI
# dentro do container: são 34 colunas, e as seis novas estão no fim, na ordem.
assert len(t.COLUNAS_TIRVU) == 34, len(t.COLUNAS_TIRVU)
assert t.COLUNAS_TIRVU[-6:] == [
    "Nome do Pai", "Nome da Mãe", "Nº Cartão DF Trans", "Nº do RG",
    "Órgão Expedidor do RG", "Data de Emissão do RG"], t.COLUNAS_TIRVU[-6:]

print("\n[as seis colunas novas saem preenchidas para quem tem o dado]")
cid34 = "cand-34"
cand34 = _Stub(id=cid34, nome_completo="Beltrano de Tal", cpf="123.456.789-09",
               cargo_funcao="Analista DF Jr", posto_servico_id="p1", empresa_id="e1",
               jornada_id="j1", registra_ponto=True, celular_whatsapp="(61) 99999-8888",
               salario_base="R$ 2.000,00", matricula="0001234",
               data_admissao="01/02/2026", data_nascimento="10/10/1990")
objs34 = {
    **objetos,
    ("Candidato", cid34): cand34,
    ("DadosPessoais", cid34): _Stub(sexo=_Stub(value="masculino"),
                                    data_nascimento="10/10/1990",
                                    nome_pai="Pai Fictício da Silva",
                                    nome_mae="Mãe Fictícia de Souza"),
    ("DocumentosIdentificacao", cid34): _Stub(
        cpf="123.456.789-09", ctps_numero="12345678909", ctps_serie="0000",
        pis_nis_pasep="12345678901", rg_numero="1234567",
        rg_orgao_emissor="SSP/DF", rg_data_expedicao=date(2015, 3, 20)),
    # ⚠️ O cartão do DF Trans mora no VALE-TRANSPORTE, não em DadosPessoais.
    # Com zero à ESQUERDA de propósito: é o caso que a regra do fornecedor
    # protege.
    ("ValeTransporte", cid34): _Stub(cartao_dftrans="0012345678"),
    ("Endereco", cid34): objetos[("Endereco", cid)],
}
linha34 = t.linha_tirvu(_DBFake(objs34, cargo_id="50"), cand34, gerar_matricula=False)

assert linha34["Nome do Pai"] == "Pai Fictício da Silva", linha34["Nome do Pai"]
assert linha34["Nome da Mãe"] == "Mãe Fictícia de Souza", linha34["Nome da Mãe"]
assert linha34["Nº do RG"] == "1234567", linha34["Nº do RG"]
assert linha34["Órgão Expedidor do RG"] == "SSP/DF", linha34["Órgão Expedidor do RG"]
# data no formato do layout, como as demais datas da planilha
assert linha34["Data de Emissão do RG"] == "20/03/2015", linha34["Data de Emissão do RG"]
assert linha34["Nº Cartão DF Trans"] == "0012345678", linha34["Nº Cartão DF Trans"]

print("\n[Nº Cartão DF Trans sai como TEXTO — o zero à esquerda sobrevive]")
# Regra do fornecedor. Como NÚMERO, o Excel come o zero e o cartão entra errado
# na integração — sem erro nenhum, que é o pior tipo de defeito.
#
# ⚠️ A asserção é sobre o `data_type` da célula, não só sobre o valor: numa
# comparação frouxa "0012345678" e 12345678 podem passar por iguais. E o cartão
# precisa estar PREENCHIDO, porque `montar_workbook_tirvu` omite célula vazia —
# com o campo em branco não haveria célula para ter tipo.
ws34 = load_workbook(io.BytesIO(t.montar_workbook_tirvu([linha34]))).active
cab34 = [c.value for c in ws34[1]]
assert len(cab34) == 34, len(cab34)
cel_dftrans = ws34.cell(row=2, column=cab34.index("Nº Cartão DF Trans") + 1)
assert cel_dftrans.value == "0012345678", cel_dftrans.value
assert cel_dftrans.data_type == "s", (
    f"o DF Trans saiu como {cel_dftrans.data_type!r} (n = número): o Excel comeria "
    "o zero à esquerda e o cartão entraria errado na integração")

# as colunas novas caíram nas posições AC→AH (27..32, base 0)
for pos, nome in enumerate(["Nome do Pai", "Nome da Mãe", "Nº Cartão DF Trans",
                            "Nº do RG", "Órgão Expedidor do RG",
                            "Data de Emissão do RG"], start=29):
    assert cab34[pos - 1] == nome, f"coluna {pos}: esperado {nome!r}, veio {cab34[pos - 1]!r}"

print("\n[as seis são OPCIONAIS: sem elas, exporta igual e não vira pendência]")
# `linha` (o cenário do topo) não tem NENHUM dos seis campos — os stubs dele não
# os declaram, exatamente como a ficha de quem nunca preencheu.
for nome in ("Nome do Pai", "Nome da Mãe", "Nº Cartão DF Trans", "Nº do RG",
             "Órgão Expedidor do RG", "Data de Emissão do RG"):
    assert linha[nome] == "", f"{nome} deveria sair vazio, veio {linha[nome]!r}"
    assert nome not in t.pendencias_linha(linha), (
        f"{nome} virou PENDÊNCIA — as seis colunas novas são opcionais e o layout "
        "de 28 continua aceito; exigi-las bloquearia o export de quem hoje sai "
        "sem problema")

# e a planilha de quem não tem os seis campos continua saindo
ws_vazio = load_workbook(io.BytesIO(t.montar_workbook_tirvu([linha]))).active
assert len([c.value for c in ws_vazio[1]]) == 34
# célula vazia é OMITIDA de propósito (evita o inlineStr malformado que o parser
# do Tirvu recusa) — então aqui se afirma a AUSÊNCIA, não o tipo.
assert ws_vazio.cell(row=2, column=cab34.index("Nº Cartão DF Trans") + 1).value is None

print("test_export_tirvu: OK")
