"""O arquivo do Dexion tem que sair IGUAL ao modelo oficial.

O Bruno resumiu a exigência assim: *"siga fielmente ao modelo da planilha, pois
o dexion é mto enjoado"*. Este teste é o que transforma "fielmente" numa
garantia verificável, em vez de uma intenção.

Ele NÃO afirma o conteúdo dos dados (isso muda a cada export). Afirma a FORMA,
que é o que um importador rígido recusa:

  * as 97 colunas, na ordem exata A→CS;
  * as duas linhas de cabeçalho (grupos na 3, rótulos na 4) **comparadas célula
    a célula com o arquivo oficial**, não com uma cópia escrita à mão aqui —
    uma cópia à mão passaria a divergir do modelo na primeira revisão dele e o
    teste continuaria verde;
  * datas como SERIAL do Excel, e a exceção da coluna BZ, que é texto;
  * aba `Sheet1`, dados a partir da linha 5, `autoFilter` na linha 4.

A comparação com o arquivo real é o coração do teste. Se o Dexion mandar um
modelo novo, ele falha — que é exatamente o que se quer: o modelo mudou e o
gerador precisa acompanhar.
"""
import os
import re
import sys
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault(
    "DATABASE_URL", "postgresql+psycopg://admissao:admissao@localhost:55432/admissao")

from app.services.export_dexion import (  # noqa: E402
    ABA_DEXION, COLUNAS_DEXION, LINHA_CABECALHO, LINHA_GRUPOS,
    PRIMEIRA_LINHA_DADOS, _data_br_texto, _salario_texto, _serial_excel,
    montar_workbook_dexion, pendencias_linha)

FALHAS = []
NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
MODELO = (Path(__file__).resolve().parents[2] / "docs"
          / "orientações importacao dexion"
          / "PLANILHA MODELO CONVERSÃO TRABALHADORES - dexion.xlsx")


def checar(condicao, descricao):
    if condicao:
        print(f"  ok   {descricao}")
    else:
        print(f"  FALHA {descricao}")
        FALHAS.append(descricao)


def _celulas(caminho_ou_bytes, linhas: set[int]) -> dict:
    """{(linha, coluna): texto} das linhas pedidas — lê o XML cru.

    Vale para o modelo (que usa sharedStrings) e para o que o openpyxl gera
    (que usa inline/shared conforme o caso).
    """
    z = (zipfile.ZipFile(caminho_ou_bytes) if isinstance(caminho_ou_bytes, (str, Path))
         else zipfile.ZipFile(caminho_ou_bytes))
    try:
        ss = [
            "".join(t.text or "" for t in si.iter(NS + "t"))
            for si in ET.fromstring(z.read("xl/sharedStrings.xml")).iter(NS + "si")
        ]
    except KeyError:
        ss = []
    nome = [n for n in z.namelist()
            if "worksheets/sheet" in n and n.endswith(".xml")][0]
    sh = ET.fromstring(z.read(nome))
    out = {}
    for row in sh.iter(NS + "row"):
        r = int(row.get("r"))
        if r not in linhas:
            continue
        for c in row.iter(NS + "c"):
            ref = re.match(r"[A-Z]+", c.get("r")).group(0)
            tipo, v, inline = c.get("t"), c.find(NS + "v"), c.find(NS + "is")
            if tipo == "s" and v is not None:
                val = ss[int(v.text)]
            elif inline is not None:
                val = "".join(x.text or "" for x in inline.iter(NS + "t"))
            elif v is not None:
                val = v.text
            else:
                val = ""
            out[(r, ref)] = val
    return out


def _gerar(linhas: list[dict]) -> bytes:
    import io
    return io.BytesIO(montar_workbook_dexion(linhas))


def test_cabecalho_identico_ao_modelo_oficial():
    """As linhas 3 e 4 têm que bater com o arquivo do Dexion, célula a célula."""
    print("\n[cabeçalho vs. modelo oficial]")
    if not MODELO.exists():
        checar(False, f"modelo oficial não encontrado em {MODELO}")
        return

    esperado = _celulas(MODELO, {LINHA_GRUPOS, LINHA_CABECALHO})
    obtido = _celulas(_gerar([]), {LINHA_GRUPOS, LINHA_CABECALHO})

    divergentes = [
        (k, esperado.get(k), obtido.get(k))
        for k in sorted(set(esperado) | set(obtido))
        if esperado.get(k) != obtido.get(k)
    ]
    checar(not divergentes,
           f"as {len(esperado)} células de cabeçalho batem com o modelo"
           + (f" (divergem: {divergentes[:4]})" if divergentes else ""))


def test_as_97_colunas_em_ordem():
    print("\n[colunas]")
    letras = [l for l, _, _ in COLUNAS_DEXION]
    checar(len(COLUNAS_DEXION) == 97, f"são 97 colunas (vieram {len(COLUNAS_DEXION)})")
    checar(letras[0] == "A" and letras[-1] == "CS", "vão de A a CS")
    checar(len(letras) == len(set(letras)), "nenhuma letra de coluna repetida")

    # O layout REPETE rótulos ("CATEGORIA" 3x, "UF" 3x, "TIPO DE JORNADA" 2x).
    # É justamente por isso que a chave da linha é a LETRA: com rótulo, uma
    # coluna sobrescreveria a outra em silêncio.
    rotulos = [r for _, _, r in COLUNAS_DEXION]
    checar(len(rotulos) != len(set(rotulos)),
           "há rótulos repetidos no layout — a chave por letra é obrigatória")


def test_datas_sao_serial_menos_a_coluna_bz():
    """Serial em todas as datas; BZ é a exceção TEXTO, como no modelo."""
    print("\n[datas]")
    # Confere a época contra os valores do próprio modelo.
    from datetime import date, timedelta
    checar(_serial_excel("1990-01-01") == 32874,
           "01/01/1990 vira 32874, como o exemplo do modelo")
    checar(_serial_excel("2026-03-01") == 46082,
           "01/03/2026 vira 46082, como o exemplo do modelo")
    checar(_serial_excel("12/10/1998") == _serial_excel("1998-10-12"),
           "BR e ISO dão o mesmo serial — os dois formatos existem no banco")
    checar(_serial_excel("") is None and _serial_excel(None) is None,
           "data ausente não vira serial 0 (que seria 30/12/1899 no Excel)")
    checar(_serial_excel("lixo") is None, "data ilegível não vira número")

    checar(_data_br_texto("2026-02-01") == "01/02/2026",
           "BZ sai como TEXTO dd/mm/aaaa (é assim no modelo, ao contrário das outras)")
    checar(_data_br_texto(None) == "", "BZ sem data fica vazia, não '01/01/1900'")

    # A ida e volta tem que fechar: serial → data → serial.
    for iso in ["2022-04-19", "1998-10-12", "2026-08-02"]:
        s = _serial_excel(iso)
        volta = date(1899, 12, 30) + timedelta(days=s)
        checar(volta.isoformat() == iso, f"{iso}: serial {s} volta na mesma data")


def test_salario_nunca_vira_zero():
    """Salário ilegível sai VAZIO — zero entraria calado no contracheque."""
    print("\n[salário]")
    checar(_salario_texto("R$ 1.500,00") == "1500,00", "R$ 1.500,00 vira 1500,00")
    checar(_salario_texto("2000") == "2000,00", "número seco ganha os centavos")
    checar(_salario_texto("a combinar") == "", "texto livre vira vazio, NUNCA 0,00")
    checar(_salario_texto(None) == "" and _salario_texto("") == "",
           "ausência vira vazio")


def test_forma_do_arquivo():
    """Aba, primeira linha de dados e autoFilter — o que o importador confere."""
    print("\n[forma do arquivo]")
    linha = {l: "" for l, _, _ in COLUNAS_DEXION}
    linha.update({"A": "000001", "B": "FULANO DE TAL", "C": "95315637050"})
    buf = _gerar([linha])
    z = zipfile.ZipFile(buf)

    # Comparar com a constante seria TAUTOLOGIA: renomear a aba para "Plan1"
    # (o nome do Tirvu — o erro exato de quem copia o gerador vizinho) mudaria
    # os dois lados juntos e o teste continuaria verde. Foi o que uma mutação
    # provou. A referência é o ARQUIVO OFICIAL.
    wb_modelo = zipfile.ZipFile(MODELO).read("xl/workbook.xml").decode("utf-8")
    aba_modelo = re.search(r"name=[\"']([^\"']+)[\"']", wb_modelo).group(1)
    wb = z.read("xl/workbook.xml").decode("utf-8")
    m = re.search(r"name=[\"']([^\"']+)[\"']", wb)
    checar(m is not None and m.group(1) == aba_modelo,
           f"a aba se chama {aba_modelo!r}, como no modelo (veio {m.group(1) if m else None!r})")
    checar(ABA_DEXION == aba_modelo,
           "a constante ABA_DEXION acompanha o nome de aba do modelo")

    nome = [n for n in z.namelist()
            if "worksheets/sheet" in n and n.endswith(".xml")][0]
    sx = z.read(nome).decode("utf-8")
    af = re.search(r"<autoFilter ref=[\"']([^\"']+)", sx)
    checar(af is not None and af.group(1).startswith(f"A{LINHA_CABECALHO}:BV"),
           "autoFilter começa em A4 e vai até a coluna BV, como o modelo")

    dados = _celulas(_gerar([linha]), {PRIMEIRA_LINHA_DADOS})
    checar(dados.get((PRIMEIRA_LINHA_DADOS, "B")) == "FULANO DE TAL",
           "os dados começam na linha 5 (as 4 primeiras são cabeçalho)")

    # Célula vazia é PULADA, nunca escrita como string vazia: o openpyxl
    # geraria `<c t="inlineStr"></c>` malformado, que parser rígido recusa
    # (lição do Tirvu, v1.79).
    checar('t="inlineStr"></c>' not in sx and "<is/>" not in sx,
           "nenhuma célula inlineStr vazia e malformada")


def test_tipo_das_celulas_de_data_no_arquivo_gerado():
    """No ARQUIVO: datas são número; BZ é texto. Não basta testar a função.

    Mutação que passou batido até este teste existir: trocar `_data_br_texto`
    por `_serial_excel` na montagem da coluna BZ. As funções continuavam
    corretas isoladamente — o que mudava era QUAL delas a linha usa. Um teste
    de unidade sobre as funções não vê isso; só olhando a célula do arquivo.

    Por que importa: BZ é `01/02/2026` como TEXTO no modelo. Serial ali faria
    o Dexion ler o número cru (46054) como se fosse a data — ou recusar.
    """
    print("\n[tipo das células no arquivo]")
    # A linha vem de `linha_dexion`, NÃO montada à mão: montar o dict aqui
    # testaria a minha própria escolha de função em vez da do código. Uma
    # mutação provou isso — trocar `_data_br_texto` por `_serial_excel` na
    # coluna BZ passava batido enquanto o teste montava o valor sozinho.
    #
    # `linha_dexion` é a única função do módulo que toca os MODELOS (o resto é
    # puro). Onde não houver SQLAlchemy + pydantic instalados — o passo enxuto
    # do CI —, esta parte é PULADA COM AVISO, nunca em silêncio: um teste que
    # some sem dizer nada é pior que um teste que falha.
    try:
        from app.services.export_dexion import linha_dexion
        from app.models.candidato import Candidato  # noqa: F401 — só p/ checar
    except ImportError as e:
        print(f"  PULADO  (sem os modelos neste ambiente: {e})")
        print("          roda completo no venv do backend e no smoke")
        return

    class _Falso:
        """Candidato mínimo: só o que a coluna BZ e as datas usam.

        Sem banco de propósito — `linha_dexion` resolve as fichas por
        `db.get`, e um dublê que devolve None cobre o caminho "pessoa sem
        ficha preenchida", que é o mais comum em importado do Tirvu.
        """
        id = "00000000-0000-0000-0000-000000000000"
        nome_completo = "FULANO DE TAL"
        cpf = "95315637050"
        matricula = "000001"
        data_nascimento = "01/01/1990"
        data_admissao = "01/02/2026"
        posto_servico_id = None
        jornada_id = None
        cargo_funcao = None
        salario_base = "R$ 2.000,00"
        celular_whatsapp = None
        email = None

    class _DbFalso:
        def get(self, *_a, **_k):
            return None

    linha = linha_dexion(_DbFalso(), _Falso())
    checar(linha["K"] == _serial_excel("1990-01-01"),
           "a linha real põe o nascimento como serial")
    checar(linha["AY"] == _serial_excel("2026-02-01"),
           "a linha real põe a admissão como serial")

    z = zipfile.ZipFile(_gerar([linha]))
    nome = [n for n in z.namelist()
            if "worksheets/sheet" in n and n.endswith(".xml")][0]
    sx = z.read(nome).decode("utf-8")
    linha5 = re.search(r'<row r="5".*?</row>', sx, re.S).group(0)

    def tipo_de(col):
        m = re.search(rf'<c r="{col}5"([^>]*)>', linha5)
        return m.group(1) if m else None

    for col in ("K", "AY"):
        attrs = tipo_de(col)
        checar(attrs is not None and 't="s"' not in attrs and 't="inlineStr"' not in attrs,
               f"{col} é NÚMERO (serial), não texto")

    attrs_bz = tipo_de("BZ")
    checar(attrs_bz is not None and ('t="s"' in attrs_bz or 't="inlineStr"' in attrs_bz),
           "BZ é TEXTO — a exceção do modelo, e o erro mais fácil de cometer")

    # E o conteúdo tem que ser a data legível, não o número.
    celulas = _celulas(_gerar([linha]), {5})
    checar(celulas.get((5, "BZ")) == "01/02/2026",
           "BZ contém '01/02/2026', não o serial")


def test_pendencias_falam_a_lingua_do_rh():
    """Falta de dado vira rótulo que o RH entende — nunca a letra da coluna."""
    print("\n[pendências]")
    vazia = {l: "" for l, _, _ in COLUNAS_DEXION}
    faltam = pendencias_linha(vazia)
    checar("CPF" in faltam and "Nome completo" in faltam,
           "linha vazia acusa CPF e nome")
    checar(not any(len(f) <= 2 for f in faltam),
           "nenhuma pendência aparece como letra de coluna ('AK', 'BO')")

    completa = dict(vazia)
    for letra, _rot in [("B", ""), ("C", ""), ("K", ""), ("U", ""), ("AY", ""),
                        ("BN", ""), ("BO", ""), ("BP", ""), ("AN", ""),
                        ("AT", ""), ("BV", ""), ("H", ""), ("O", "")]:
        completa[letra] = "x"
    checar(pendencias_linha(completa) == [],
           "linha com todos os obrigatórios não acusa nada")

    # Serial 0 é uma data real (30/12/1899) e não pode ser lido como ausência,
    # mas `None` (data que não deu para ler) TEM que virar pendência.
    com_data = dict(completa)
    com_data["K"] = None
    checar("Data de nascimento" in pendencias_linha(com_data),
           "data ilegível (None) vira pendência, não passa batido")


if __name__ == "__main__":
    test_cabecalho_identico_ao_modelo_oficial()
    test_as_97_colunas_em_ordem()
    test_datas_sao_serial_menos_a_coluna_bz()
    test_salario_nunca_vira_zero()
    test_forma_do_arquivo()
    test_tipo_das_celulas_de_data_no_arquivo_gerado()
    test_pendencias_falam_a_lingua_do_rh()

    print()
    if FALHAS:
        print(f"test_export_dexion: {len(FALHAS)} FALHA(S)")
        for f in FALHAS:
            print(f"  - {f}")
        sys.exit(1)
    print("test_export_dexion: OK")
