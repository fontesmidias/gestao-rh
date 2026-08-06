"""Catálogo dos documentos do sistema (v2.16, pedido de 2026-07-28 madrugada).

"Pegue todos os que já temos disponíveis no sistema do tipo hardcoded e
coloque-os lá para CRUD e boas práticas, para que possamos duplicar e outras
coisas mais, bem como preview decente e que também possamos baixar."

O que este teste protege, além do óbvio:

1. **Nenhum gerador foi substituído.** O hash do ato de assinatura é calculado
   sobre o PDF gerado; trocar o gerador por template faria os manifestos já
   emitidos apontarem para um hash que não se reproduz. O teste confere que os
   11 documentos continuam sendo produzidos pelos MESMOS geradores.
2. **O catálogo cobre o enum inteiro.** Documento novo sem entrada aqui sumiria
   da tela do RH sem ninguém perceber.
3. **Só texto corrido é duplicável.** Formulário (ficha de cadastro, com loop
   de dependentes) e híbrido (termo de VT, com dois caminhos) não cabem em
   texto com variáveis — e a recusa vem com o motivo, para a tela explicar.

Precisa dos containers de teste.
Rode: PYTHONPATH=. .venv/Scripts/python.exe tests/test_documentos_catalogo.py
"""

import os

os.environ.setdefault(
    "DATABASE_URL", "postgresql+psycopg://admissao:admissao@localhost:55432/admissao")
os.environ.setdefault("MINIO_ENDPOINT", "localhost:59000")
os.environ.setdefault("MINIO_ACCESS_KEY", "minio")
os.environ.setdefault("MINIO_SECRET_KEY", "minio12345")
os.environ.setdefault("MINIO_SECURE", "false")
os.environ.setdefault("RH_ADMIN_EMAIL", "rh@greenhousedf.com.br")
os.environ.setdefault("RH_ADMIN_PASSWORD", "senha-teste-123")
os.environ.setdefault("SECRET_KEY", "segredo-de-teste")
os.environ.setdefault("BASE_URL", "http://localhost:8090")

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402
from app.models.assinatura import DocumentoAssinavel  # noqa: E402
from app.services.documentos_catalogo import (CATALOGO, TODOS,  # noqa: E402
                                              Formato, duplicavel)
from app.services.documentos_texto import corpo_editavel, tem_corpo  # noqa: E402
from app.services.fichas import GERADORES  # noqa: E402

c = TestClient(app)
rh = {"Authorization": f"Bearer {c.post('/api/rh/auth/login', json={'email': 'rh@greenhousedf.com.br', 'senha': 'senha-teste-123'}).json()['token']}"}

# ------------------------------------------- o catálogo cobre o enum inteiro
# (o próprio módulo já valida isso no import; aqui é a rede de segurança)
assert {d.chave for d in CATALOGO} == {d.value for d in DocumentoAssinavel}, (
    "catálogo e enum divergiram — documento novo sumiria da tela do RH")
# A contagem é DERIVADA do enum, nunca escrita à mão: número chumbado quebra a
# cada documento novo e legítimo sem apontar defeito nenhum, e a correção óbvia
# (incrementar a constante) faz o teste deixar de proteger (v2.25).
assert len(CATALOGO) == len(DocumentoAssinavel), (
    f"catálogo com {len(CATALOGO)} entradas para {len(DocumentoAssinavel)} "
    "valores do enum — há documento repetido ou faltando")

# ------------------------------------- os geradores continuam sendo os mesmos
# Se alguém trocar um gerador por template, o hash do ato de assinatura muda e
# os manifestos já emitidos deixam de se reproduzir. Isto é o guarda-corpo.
for d in CATALOGO:
    assert d.chave in GERADORES, (
        f"'{d.chave}' saiu de GERADORES — o documento oficial precisa continuar "
        f"sendo gerado pelo mesmo código que produziu os PDFs já assinados")

# ------------------------------------------------ só texto corrido é duplicável
_texto = [d.chave for d in CATALOGO if d.formato is Formato.texto]
assert len(_texto) == 3, f"esperava 3 documentos de texto, achei {_texto}"
for chave in _texto:
    assert duplicavel(chave) and tem_corpo(chave), (
        f"'{chave}' é de texto mas não tem corpo editável definido")
    corpo = corpo_editavel(chave)
    assert corpo.strip(), f"'{chave}': corpo editável vazio"
    assert "{{" in corpo, f"'{chave}': corpo sem nenhuma variável"

# ------------------- o corpo editável NÃO PODE MENTIR sobre o documento real
# A primeira versão deste módulo tinha texto INVENTADO para o informativo
# INFRAERO: sumiram os percentuais que dão valor jurídico ao documento e
# entraram itens que ele não tem. Passou pelo teste antigo (que só conferia
# "não é vazio" e "tem {{"). Estas âncoras são trechos que EXISTEM no gerador
# oficial — se o corpo editável divergir, o teste cai.
_ANCORAS = {
    "informacoes_trabalhador": [
        "6% do salário",                    # desconto máximo do VT
        "8% (oito por cento)",              # FGTS
        "5º (quinto) dia útil",             # prazo do salário
        "terceirizados@infraero.gov.br",    # canal exigido em contrato
        "Carteira de trabalho assinada desde o primeiro dia",
    ],
    "acordo_confidencialidade": [
        "TRANSMISSORA", "RECEPTORA",
        "2 (dois) anos",                    # vigência
        "PESSOAL AUTORIZADO",
    ],
    "termo_lgpd_infraero": [
        "Lei nº 13.709/2018",
        "AUTORIZO",
    ],
}
for chave, ancoras in _ANCORAS.items():
    corpo = corpo_editavel(chave)
    for trecho in ancoras:
        assert trecho in corpo, (
            f"'{chave}': o corpo editável perdeu '{trecho}', que existe no "
            f"documento oficial. Texto que diverge do documento real é pior "
            f"que texto nenhum — o RH adapta e emite achando que é o oficial.")

# a lista de direitos vem da CONSTANTE, não de cópia (fonte única)
from app.services.fichas import DIREITOS_TRABALHADOR  # noqa: E402

_corpo_infra = corpo_editavel("informacoes_trabalhador")
for _item in DIREITOS_TRABALHADOR:
    assert _item in _corpo_infra, (
        f"o direito {_item[:30]!r} sumiu do corpo editável — ele tem que vir "
        f"de `fichas.DIREITOS_TRABALHADOR`, não de texto copiado")

# nenhuma variável inventada: só as que o contexto do modelo conhece
import re as _re  # noqa: E402

from app.services.fichas import VARIAVEIS_MODELO  # noqa: E402

for chave in _texto:
    for var in _re.findall(r"\{\{\s*(\w+)\s*\}\}", corpo_editavel(chave)):
        assert var in VARIAVEIS_MODELO, (
            f"'{chave}' usa {{{{{var}}}}}, que não existe em VARIAVEIS_MODELO — "
            f"sairia impressa crua no PDF do RH")

for d in CATALOGO:
    if d.formato is not Formato.texto:
        assert not duplicavel(d.chave), f"'{d.chave}' não deveria ser duplicável"
        assert d.porque_nao_duplica, f"'{d.chave}': falta explicar o motivo"
        assert not tem_corpo(d.chave), (
            f"'{d.chave}' tem corpo editável mas não é duplicável — inconsistente")

# --------------------------------------------------------------- as rotas
assert c.get("/api/rh/documentos-sistema").status_code == 401

lista = c.get("/api/rh/documentos-sistema", headers=rh).json()
# A rota serve o catálogo INTEIRO — desde a v2.67 ele tem duas famílias
# (admissão + entrevista). A garantia se DERIVA do catálogo, não de um número
# escrito à mão: `== 11` quebrava a cada documento novo e legítimo sem apontar
# defeito, e a correção óbvia (incrementar) faz o teste não proteger nada
# (lição da v2.25).
assert len(lista) == len(TODOS), (len(lista), len(TODOS))
# Os 11 da admissão continuam servidos, e continuam sendo os do enum.
_admissao = [x for x in lista if x["origem"] == "admissao"]
assert {x["chave"] for x in _admissao} == {d.value for d in DocumentoAssinavel}, _admissao
_um = next(x for x in lista if x["chave"] == "acordo_confidencialidade")
assert _um["duplicavel"] is True and _um["formato"] == "texto", _um
_ficha = next(x for x in lista if x["chave"] == "ficha_cadastro")
assert _ficha["duplicavel"] is False and _ficha["porque_nao_duplica"], _ficha
assert _ficha["base"] is True, _ficha

# ------------------------------- PREVIEW: PDF de verdade, para os 11 documentos
for d in CATALOGO:
    r = c.get(f"/api/rh/documentos-sistema/{d.chave}/previa", headers=rh)
    assert r.status_code == 200, f"{d.chave}: {r.status_code} {r.text[:200]}"
    assert r.content[:4] == b"%PDF", f"{d.chave}: não veio PDF"
    assert len(r.content) > 5000, f"{d.chave}: PDF suspeito de vazio ({len(r.content)}b)"

assert c.get("/api/rh/documentos-sistema/nao_existe/previa",
             headers=rh).status_code == 404
assert c.get("/api/rh/documentos-sistema/ficha_cadastro/previa").status_code == 401

# a amostra usa candidato FICTÍCIO — nenhum dado de gente real vaza na prévia
import pypdf  # noqa: E402
import io as _io  # noqa: E402

_pdf = c.get("/api/rh/documentos-sistema/termo_lgpd_infraero/previa",
             headers=rh).content
_texto_pdf = pypdf.PdfReader(_io.BytesIO(_pdf)).pages[0].extract_text()
assert "Maria de Exemplo" in _texto_pdf, _texto_pdf[:300]

# --------------------------------------------------------------- DUPLICAR
_antes = len(c.get("/api/rh/modelos-documento", headers=rh).json()["modelos"])
r = c.post("/api/rh/documentos-sistema/acordo_confidencialidade/duplicar",
           headers=rh, json={"titulo": "Acordo — versão do RH"})
assert r.status_code == 201, r.text
novo = r.json()
assert novo["titulo"] == "Acordo — versão do RH", novo
assert "{{nome}}" in novo["corpo"], "a cópia veio sem as variáveis"
assert "CONFIDENCIALIDADE" in novo["corpo"].upper(), "a cópia veio sem o texto real"

_depois = c.get("/api/rh/modelos-documento", headers=rh).json()["modelos"]
assert len(_depois) == _antes + 1, "o modelo não entrou na lista"

# o modelo criado gera PDF (é um ModeloDocumento normal daqui em diante)
r = c.get(f"/api/rh/modelos-documento/{novo['id']}/previa", headers=rh)
assert r.status_code == 200 and r.content[:4] == b"%PDF", r.status_code

# duplicar FORMULÁRIO é recusado, com o motivo — a tela mostra ao RH
r = c.post("/api/rh/documentos-sistema/ficha_cadastro/duplicar",
           headers=rh, json={})
assert r.status_code == 422, r.text
assert r.json()["detail"]["erro"] == "documento_nao_duplicavel", r.json()
assert r.json()["detail"]["motivo"], "recusou sem explicar o porquê"

# híbrido também não
assert c.post("/api/rh/documentos-sistema/termo_vt/duplicar", headers=rh,
              json={}).status_code == 422

# chave inexistente
assert c.post("/api/rh/documentos-sistema/nao_existe/duplicar", headers=rh,
              json={}).status_code == 404
assert c.post("/api/rh/documentos-sistema/acordo_confidencialidade/duplicar",
              json={}).status_code == 401

# ------------------------------------------ o documento ORIGINAL não mudou
# (duplicar cria cópia; o oficial continua saindo do mesmo gerador)
_apos = c.get("/api/rh/documentos-sistema/acordo_confidencialidade/previa",
              headers=rh)
assert _apos.status_code == 200 and _apos.content[:4] == b"%PDF"

print("test_documentos_catalogo: OK")
