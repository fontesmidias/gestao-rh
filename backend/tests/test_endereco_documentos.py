"""O endereço sai INTEIRO nos documentos (v2.37).

Feedback de campo do Bruno em 2026-08-01: *"No Termo de opção de VT, no campo
Endereço Residencial, deve constar o endereço completo, pois está vindo apenas
a cidade, estado e cep — cadê os outros dados que já foram coletados?"*

Os dados estavam coletados. O endereço mora no banco em dois formatos — a
string única legada (`logradouro_numero_complemento`) e os campos separados que
a leva do Tirvu introduziu — e quatro geradores liam **só o legado**, que é
nulo para quem preencheu a ficha depois daquela mudança. O dado estava no
banco, na tela e no export do Tirvu; faltava só no papel.

O que este teste protege:

1. **Os dois formatos são lidos** — quem preencheu na coleta atual e quem tem a
   string legada saem com endereço nos dois casos.
2. **O Termo de VT sai com o endereço completo**: é o documento que declara
   "resido no endereço acima informado, assumindo inteira responsabilidade pela
   veracidade" e que autoriza um desconto de 6% em folha. Meio endereço
   descaracteriza a declaração que a pessoa assina.
3. **Onde já havia bairro/cidade/CEP em campos próprios, não se repete** — o
   documento é uma ficha, não um exercício de redundância.
4. **Parte ausente é OMITIDA, não vira traço**: "Rua X, 123, -, Brasília/DF"
   parece defeito do sistema.
5. **A ficha cadastral, que já tratava os dois formatos, continua igual** —
   correção que quebra o que estava certo é regressão.

Precisa dos containers de teste (pg-teste/minio-teste).
Rode: PYTHONPATH=. .venv/Scripts/python.exe tests/test_endereco_documentos.py
"""

import os
import uuid

os.environ.setdefault(
    "DATABASE_URL", "postgresql+psycopg://admissao:admissao@localhost:55432/admissao")
os.environ.setdefault("MINIO_ENDPOINT", "localhost:59000")
os.environ.setdefault("MINIO_ACCESS_KEY", "minio")
os.environ.setdefault("MINIO_SECRET_KEY", "minio12345")
os.environ.setdefault("MINIO_SECURE", "false")
os.environ.setdefault("SECRET_KEY", "segredo-de-teste")
os.environ.setdefault("BASE_URL", "http://localhost:8090")

from pypdf import PdfReader  # noqa: E402

from app.core.db import SessionLocal  # noqa: E402
from app.models.candidato import Candidato, StatusCandidato  # noqa: E402
from app.models.ficha import Endereco, ValeTransporte  # noqa: E402
from app.services import endereco as end  # noqa: E402
from app.services.fichas import (gerar_ficha_cadastro, gerar_ficha_emergencia,  # noqa: E402
                                 gerar_oficio_apresentacao_presidencia, gerar_termo_vt)

FALHAS = []


def checar(condicao, descricao):
    print(("  ok   " if condicao else "  FALHA ") + descricao)
    if not condicao:
        FALHAS.append(descricao)


def texto_do_pdf(dados: bytes) -> str:
    """Texto de todas as páginas, sem as quebras de linha do layout — o que
    interessa é se o dado CHEGOU ao papel, não onde a linha partiu."""
    bruto = "\n".join(p.extract_text() or "" for p in PdfReader(__import__("io").BytesIO(dados)).pages)
    return " ".join(bruto.split())


# ------------------------------------------------ 1. as duas leituras
print("\n[os dois formatos do banco]")
atual = Endereco(logradouro="QNM 34 Conjunto B", numero="12", complemento="Casa 2",
                 bairro="Ceilândia Norte", cidade="Brasília", uf="DF", cep="72215342")
legado = Endereco(logradouro_numero_complemento="SHIS QI 5 Conjunto 3 Casa 7",
                  bairro="Lago Sul", cidade="Brasília", uf="DF", cep="71615030")

checar(end.rua(atual) == "QNM 34 Conjunto B, 12, Casa 2",
       "coleta ATUAL: logradouro, número e complemento numa linha")
checar(end.rua(legado) == "SHIS QI 5 Conjunto 3 Casa 7",
       "ficha LEGADA: a string única continua valendo")
checar(end.rua(None) is None and end.completo(None) is None,
       "sem endereço, devolve None — o chamador decide o que mostrar")
checar(end.rua(Endereco()) is None, "endereço vazio não vira string de lixo")

completo_atual = end.completo(atual)
checar("QNM 34 Conjunto B" in completo_atual and "Ceilândia Norte" in completo_atual
       and "Brasília/DF" in completo_atual and "72215-342" in completo_atual,
       f"completo junta rua, bairro, cidade/UF e CEP: {completo_atual!r}")
checar("-" not in end.completo(Endereco(logradouro="Rua A", numero="1", cidade="Brasília")),
       "parte ausente é OMITIDA, não vira traço (traço parece defeito)")

# --------------------------------------------------- 2. nos documentos
print("\n[nos documentos gerados]")
db = SessionLocal()
try:
    cand = Candidato(nome_completo="Joana do Endereço Completo",
                     email=f"{uuid.uuid4().hex[:8]}@exemplo.com",
                     cpf="12345678901", status=StatusCandidato.convidado)
    db.add(cand)
    db.flush()
    db.add(Endereco(candidato_id=cand.id, logradouro="QNM 34 Conjunto B",
                    numero="12", complemento="Casa 2", bairro="Ceilândia Norte",
                    cidade="Brasília", uf="DF", cep="72215342"))
    db.add(ValeTransporte(candidato_id=cand.id, optante=True,
                          cartao_dftrans="0000123456",
                          trajeto_descricao="Ceilândia → Guará, 2 ônibus"))
    db.commit()

    vt = texto_do_pdf(gerar_termo_vt(db, cand))
    checar("QNM 34 Conjunto B" in vt, "TERMO DE VT: a rua chegou ao papel")
    checar("12" in vt and "Casa 2" in vt, "TERMO DE VT: número e complemento também")
    checar("Ceilândia Norte" in vt, "TERMO DE VT: o bairro está lá")
    checar("Brasília/DF" in vt and "72215-342" in vt,
           "TERMO DE VT: cidade/UF e CEP continuam (era só isto que saía antes), e o CEP sai COM hífen — o banco guarda só os dígitos")

    emerg = texto_do_pdf(gerar_ficha_emergencia(db, cand))
    checar("QNM 34 Conjunto B" in emerg, "FICHA DE EMERGÊNCIA: a rua chegou")
    checar(emerg.count("72215-342") == 1,
           "FICHA DE EMERGÊNCIA: o CEP aparece UMA vez — o campo ao lado já o "
           "imprime, e repetir é ruído numa ficha que se lê com pressa")

    oficio = texto_do_pdf(gerar_oficio_apresentacao_presidencia(db, cand))
    checar("QNM 34 Conjunto B" in oficio and "Ceilândia Norte" in oficio,
           "OFÍCIO À PRESIDÊNCIA: endereço completo em 'residente e domiciliado à'")
    # Vizinhança, não o documento inteiro: o ofício TEM outras lacunas de
    # preenchimento à mão (data de início, local, horário) e o RG ausente também
    # vira pontinhos. O que não pode é a lacuna estar onde mora o endereço.
    depois = oficio.split("domiciliado(a) à", 1)[-1][:60]
    checar("QNM 34 Conjunto B" in depois,
           f"OFÍCIO À PRESIDÊNCIA: o endereço vem logo após 'domiciliado(a) à': {depois!r}")
    checar("..." not in depois,
           "OFÍCIO À PRESIDÊNCIA: a linha de pontinhos não aparece no lugar do "
           "endereço quando o endereço existe")

    # A ficha cadastral JÁ tratava os dois formatos: aqui só se garante que a
    # correção não mexeu no que estava certo.
    cadastro = texto_do_pdf(gerar_ficha_cadastro(db, cand))
    checar("QNM 34 Conjunto B" in cadastro and "Casa 2" in cadastro,
           "FICHA CADASTRAL: continua completa (não era ela a quebrada)")

    # E quem é de antes da mudança continua saindo igual.
    velho = Candidato(nome_completo="Antonio da Ficha Antiga",
                      email=f"{uuid.uuid4().hex[:8]}@exemplo.com",
                      cpf="98765432100", status=StatusCandidato.convidado)
    db.add(velho)
    db.flush()
    db.add(Endereco(candidato_id=velho.id,
                    logradouro_numero_complemento="SHIS QI 5 Conjunto 3 Casa 7",
                    bairro="Lago Sul", cidade="Brasília", uf="DF", cep="71615030"))
    db.add(ValeTransporte(candidato_id=velho.id, optante=True))
    db.commit()

    vt_velho = texto_do_pdf(gerar_termo_vt(db, velho))
    checar("SHIS QI 5 Conjunto 3 Casa 7" in vt_velho,
           "FICHA ANTIGA: a string legada continua saindo — ninguém foi migrado")
finally:
    db.rollback()
    db.close()

print()
if FALHAS:
    print(f"test_endereco_documentos: {len(FALHAS)} FALHA(S)")
    for f in FALHAS:
        print(f"  - {f}")
    raise SystemExit(1)
print("test_endereco_documentos: OK")
