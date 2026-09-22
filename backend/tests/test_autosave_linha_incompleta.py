"""O autosave não recusa quem está digitando.

Caso de campo em 2026-09-22, lido no log de produção: uma candidata levou **12
recusas 422 em 4 minutos** para cadastrar UM dependente e UM contato de
emergência. A sequência está no log:

    data_nascimento:"" → "Input should be a valid date"
    cpf:""             → "Input should be a valid string"
    parentesco:null    → "Input should be 'conjuge', 'filho'..."
    cpf:"116"          → "Este CPF não existe"
    cpf:"1164"         → "Este CPF não existe"
    cpf:"116414"       → "Este CPF não existe"

Duas causas, ambas do mesmo desenho: **o wizard salva a cada 900ms e o backend
valida o estado FINAL**.

1. O filtro do autosave era `(d) => d.nome_completo` — bastava o NOME para a
   linha inteira ser enviada, ainda sem data nem CPF.
2. `_validar_cpf` acusava CPF incompleto como inválido, então cada tecla
   produzia um erro na tela — em INGLÊS, porque é a mensagem crua do Pydantic.

⚠️ E a correção do item 2 abriu um buraco que este teste também tranca: a
conclusão só checava `is None`, e "116" não é None — CPF pela metade passaria
como preenchido, na ficha que a pessoa ASSINA. A trava que existia por ACIDENTE
na validação por tecla precisou existir DE PROPÓSITO na conclusão.

O que este teste protege:

1. **CPF incompleto NÃO é recusado no autosave** — é CPF sendo digitado.
2. **CPF completo e inválido CONTINUA recusado** — a proteção real não caiu.
3. **CPF incompleto vira PENDÊNCIA na conclusão** — o buraco acima.
4. **O filtro do front casa com o schema do backend** — campo obrigatório que
   não entre no `linhaCompleta` volta a produzir o 422 silencioso.

Rode: PYTHONPATH=. .venv/Scripts/python.exe tests/test_autosave_linha_incompleta.py
"""

import os
import pathlib
import re

os.environ.setdefault(
    "DATABASE_URL", "postgresql+psycopg://admissao:admissao@localhost:55432/admissao")
os.environ.setdefault("MINIO_ENDPOINT", "localhost:59000")
os.environ.setdefault("MINIO_ACCESS_KEY", "minio")
os.environ.setdefault("MINIO_SECRET_KEY", "minio12345")
os.environ.setdefault("MINIO_SECURE", "false")
os.environ.setdefault("SECRET_KEY", "segredo-de-teste")
os.environ.setdefault("BASE_URL", "http://localhost:8090")

FALHAS = []

# A raiz do REPOSITÓRIO, quando ela existe. Dentro do container da API só há o
# `backend/` (não há `frontend/`), e é lá que o CI roda este teste — por isso o
# bloco que lê o JSX se ANUNCIA como pulado em vez de estourar
# `FileNotFoundError`, que não fala da causa. Pular em SILÊNCIO seria pior:
# daria teste verde sem ter verificado nada (v2.72).
_AQUI = pathlib.Path(__file__).resolve()
RAIZ = next((p for p in _AQUI.parents if (p / "frontend").is_dir()), None)
BACKEND = next((p for p in _AQUI.parents if (p / "app" / "api" / "ficha.py").is_file()),
               _AQUI.parents[1])


PADRAO_FILTRO = r"const linhaCompleta = \{(.*?)\n\}"


def _reportar(texto):
    """Emoji em mensagem de falha quebra o teste no console do Windows (v3.15)."""
    try:
        print(texto)
    except UnicodeEncodeError:
        print(texto.encode("ascii", "replace").decode("ascii"))


def checar(condicao, descricao):
    _reportar(("  ok   " if condicao else "  FALHA ") + descricao)
    if not condicao:
        FALHAS.append(descricao)


print("\n=== 1. CPF sendo DIGITADO nao e recusado ===")
from app.api.ficha import _validar_cpf  # noqa: E402

# A sequência EXATA do log de produção.
for parcial in ("116", "1164", "116414", "11641493"):
    try:
        _validar_cpf(parcial)
        ok = True
    except ValueError as exc:
        ok, motivo = False, str(exc)[:40]
    checar(ok, f"'{parcial}' passa (e CPF sendo digitado, nao CPF errado)"
               + ("" if ok else f" — veio {motivo!r}"))

print("\n=== 2. CPF COMPLETO e invalido CONTINUA recusado ===")
# A proteção real não pode ter caído junto: 11 dígitos com verificador errado.
try:
    _validar_cpf("11111111111")
    passou = True
except ValueError:
    passou = False
checar(not passou, "CPF de 11 digitos invalido e recusado — a protecao real "
                   "nao caiu junto com o ruido")

# E o válido continua passando (senão o teste acima estaria certo por acidente).
try:
    _validar_cpf("52998224725")  # CPF válido conhecido
    valido_ok = True
except ValueError:
    valido_ok = False
checar(valido_ok, "CPF valido de 11 digitos continua sendo aceito")

print("\n=== 3. CPF incompleto vira PENDENCIA na conclusao ===")
# O buraco que a correcao do item 1 abriu: a conclusao so checava `is None`,
# e "116" nao e None. Afirma sobre o CODIGO porque a funcao precisa de sessao
# e candidato montados; o que importa e que a checagem de TAMANHO exista.
fonte = (BACKEND / "app" / "api" / "ficha.py").read_text(encoding="utf-8")
sem_comentario = "\n".join(
    L for L in fonte.split("\n") if not L.lstrip().startswith("#"))
checar(re.search(r"len\(\s*[\"']{2}\.join\([^)]*docs\.cpf.*?\)\s*\)\s*<\s*11",
                 sem_comentario, re.S) is not None
       or ("docs.cpf" in sem_comentario and "< 11" in sem_comentario),
       "a conclusao cobra CPF com 11 digitos — sem isso, '116' passaria como "
       "preenchido na ficha que a pessoa ASSINA")

print("\n=== 4. o filtro do FRONT casa com o schema do BACKEND ===")
# Campo obrigatório que o `linhaCompleta` não confira volta a produzir o 422
# silencioso — é a mesma classe de defeito, só que de volta.
if RAIZ is None:
    # Container da API: so existe `backend/`, sem `frontend/`. ANUNCIA que
    # pulou — silencio aqui daria teste verde sem ter verificado nada (v2.72).
    _reportar("  (pulado) sem `frontend/` neste ambiente — bloco roda no repositorio")
    m = None
else:
    wizard = (RAIZ / "frontend" / "src" / "candidato" / "Wizard.jsx").read_text(encoding="utf-8")
    m = re.search(PADRAO_FILTRO, wizard, re.S)
    checar(m is not None, "o `linhaCompleta` existe no Wizard.jsx")
if m:
    bloco = m.group(1)
    # DependenteIn: nome_completo, data_nascimento, cpf, parentesco (deduz_irrf tem default)
    for campo in ("nome_completo", "data_nascimento", "cpf", "parentesco"):
        checar(campo in bloco,
               f"o filtro confere `{campo}` (obrigatorio em DependenteIn)")
    # ContatoEmergenciaIn: nome_completo, parentesco, telefone_celular
    checar("telefone_celular" in bloco,
           "o filtro confere `telefone_celular` (obrigatorio em ContatoEmergenciaIn)")
    # O opcional NAO deve estar la: exigi-lo esconderia a linha valida
    checar("telefone_fixo_endereco" not in bloco,
           "o filtro NAO exige `telefone_fixo_endereco` — e o unico opcional, e "
           "cobra-lo impediria de salvar linha legitima")
    # E o filtro tem que estar LIGADO nos dois pontos de salvamento
    checar(wizard.count("linhaCompleta.") >= 2,
           f"o filtro esta ligado nos DOIS salvamentos (veio "
           f"{wizard.count('linhaCompleta.')}) — metade ligada parece ligada")
    checar("d.nome_completo)" not in wizard and "c.nome_completo)" not in wizard,
           "o filtro ANTIGO (so o nome) nao sobrou em lugar nenhum")

print()
if FALHAS:
    _reportar(f"test_autosave_linha_incompleta: {len(FALHAS)} FALHA(S)")
    for f in FALHAS:
        _reportar(f"  - {f}")
    raise SystemExit(1)
_reportar("test_autosave_linha_incompleta: OK")
