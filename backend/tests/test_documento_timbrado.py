"""Documento enviado fora do wizard também sai no papel timbrado (v2.61).

Pedido do Bruno (2026-08-02): *"ainda sobre o reembolso creche ou qualquer outra
área que a pessoa tem que subir fotos, documentos ou arquivos [...] para o RH
e/ou quando gerar o dossiê, já vir no padrão conforme documentos anteriores no
timbrado da empresa"*.

Até aqui só o wizard da admissão normalizava. O creche e o portal gravavam o
arquivo CRU: a certidão fotografada ficava como um `.jpg` no MinIO enquanto a
mesma foto, enviada pelo wizard, virava uma A4 timbrada.

As três garantias, em ordem de importância:

1. **O que se GRAVA é PDF timbrado** — com o rótulo do documento no cabeçalho,
   para uma folha se distinguir da outra dentro do dossiê.
2. **Falha de conversão NÃO perde o documento.** Formato exótico, foto ilegível
   ou PDF protegido caem no original. Recusar aqui deixaria a pessoa sem
   conseguir enviar a certidão do filho — e o benefício travaria pela qualidade
   de uma foto, não pelo direito dela.
3. **O currículo do Banco de Talentos continua ORIGINAL** — é documento de
   terceiro, o RH precisa dele como veio, e há decisão registrada nesse sentido
   desde a v2.33. Timbrar seria alterar prova alheia.

Precisa de banco + MinIO efêmeros. Rode:
  PYTHONPATH=. .venv/Scripts/python.exe tests/test_documento_timbrado.py
"""
import io
import os
import sys
import uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault(
    "DATABASE_URL", "postgresql+psycopg://admissao:admissao@localhost:55432/admissao")
os.environ.setdefault("SECRET_KEY", "teste")
os.environ.setdefault("MINIO_ENDPOINT", "localhost:59000")
os.environ.setdefault("MINIO_ACCESS_KEY", "minio")
os.environ.setdefault("MINIO_SECRET_KEY", "minio12345")
os.environ.setdefault("MINIO_BUCKET", "admissao")

import pypdf  # noqa: E402
from PIL import Image, ImageDraw  # noqa: E402

import app.main  # noqa: E402,F401 — resolve os modelos
from app.api.creche_publico import _guardar_doc_crianca  # noqa: E402
from app.core.db import SessionLocal  # noqa: E402
from app.models.beneficio import (BeneficioCreche, CriancaCreche,  # noqa: E402
                                  StatusBeneficio)
from app.models.candidato import Candidato  # noqa: E402
from app.services import storage  # noqa: E402

FALHAS = []
db = SessionLocal()


def checar(condicao, descricao):
    if condicao:
        print(f"  ok   {descricao}")
    else:
        print(f"  FALHA {descricao}")
        FALHAS.append(descricao)


class _Upload:
    """Dublê de `UploadFile` — só o que as funções de gravação leem."""

    def __init__(self, filename, content_type="image/jpeg"):
        self.filename = filename
        self.content_type = content_type


def _foto_legivel() -> bytes:
    """JPEG com textura suficiente para passar no teste de nitidez.

    Imagem lisa é recusada com `imagem_borrada` — a mesma razão pela qual o
    `test_documento_original.py` tem o helper `_nitida()`.
    """
    img = Image.new("RGB", (1000, 700), "white")
    d = ImageDraw.Draw(img)
    for i in range(0, 1000, 6):
        d.line([(i, 0), (i, 700)], fill=(20, 20, 20))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=92)
    return buf.getvalue()


def _crianca():
    col = Candidato(nome_completo="Pai Teste", cpf=str(uuid.uuid4().int)[:11],
                    situacao="ativo")
    db.add(col)
    db.flush()
    ben = BeneficioCreche(candidato_id=col.id, status=StatusBeneficio.levantamento)
    db.add(ben)
    db.flush()
    c = CriancaCreche(beneficio_id=ben.id, nome="Mikael Teste",
                      data_nascimento="2022-10-19", parentesco="filho")
    db.add(c)
    db.commit()
    return ben, c


def test_certidao_do_creche_vira_pdf_timbrado():
    print("\n[creche: a certidão sai timbrada]")
    ben, c = _crianca()
    key = _guardar_doc_crianca(ben.id, str(c.id), "certidao",
                               _Upload("certidao.jpg"), _foto_legivel())
    checar(key.endswith(".pdf"), f"a key é .pdf (veio {key.rsplit('/', 1)[-1]})")

    dados = storage.ler(key)
    checar(dados[:4] == b"%PDF", "o conteúdo gravado é PDF de verdade")

    texto = "".join(p.extract_text() for p in pypdf.PdfReader(io.BytesIO(dados)).pages)
    checar("CERTIDÃO DE NASCIMENTO" in texto.upper(),
           "com o NOME do documento no cabeçalho do timbrado")
    # O rodapé e a marca d'água são IMAGENS — não saem no `extract_text`. O que
    # prova o timbrado é a frase de recebimento (texto) e a presença de mais de
    # uma imagem na página: a foto enviada + as artes do papel.
    checar("Recebido pelo Portal" in texto,
           "e a linha de recebimento do timbrado")
    imgs = pypdf.PdfReader(io.BytesIO(dados)).pages[0].images
    checar(len(imgs) >= 2,
           f"a página tem a foto MAIS as artes do timbre ({len(imgs)} imagens)")


def test_guarda_tambem():
    """O outro documento da criança — mesma regra, rótulo próprio."""
    print("\n[creche: a guarda judicial também]")
    ben, c = _crianca()
    key = _guardar_doc_crianca(ben.id, str(c.id), "guarda",
                               _Upload("guarda.jpg"), _foto_legivel())
    texto = "".join(p.extract_text()
                    for p in pypdf.PdfReader(io.BytesIO(storage.ler(key))).pages)
    checar("GUARDA JUDICIAL" in texto.upper(),
           "o cabeçalho diz GUARDA JUDICIAL, não 'certidão'")


def test_falha_de_conversao_nao_perde_o_documento():
    """A garantia que protege a PESSOA, não o formato.

    Se a conversão falhar (formato exótico, arquivo corrompido), grava-se o
    original. Recusar deixaria alguém sem conseguir enviar a certidão do filho
    — e o benefício travaria pela qualidade de uma foto, não pelo direito dela.
    """
    print("\n[falha de conversão degrada, não recusa]")
    ben, c = _crianca()
    ruim = b"isto nao e uma imagem"
    key = _guardar_doc_crianca(ben.id, str(c.id), "certidao",
                               _Upload("certidao.jpg"), ruim)
    checar(not key.endswith(".pdf"),
           f"cai no original, com a extensão de origem (veio {key.rsplit('/', 1)[-1]})")
    checar(storage.ler(key) == ruim, "e o conteúdo enviado é preservado, byte a byte")


def test_dossie_identifica_de_quem_e_cada_folha():
    """Rótulo com o NOME da criança: num dossiê com dois filhos, "CERTIDÃO DE
    NASCIMENTO" repetido duas vezes não diz de quem é cada página."""
    print("\n[dossiê: cada folha diz de quem é]")
    import inspect

    from app.services import creche_pdf
    fonte = inspect.getsource(creche_pdf.gerar_dossie_creche)
    checar("c.nome" in fonte and "certidão de nascimento —" in fonte,
           "o dossiê passa o nome da criança como rótulo do anexo")


def test_curriculo_continua_original():
    """Decisão registrada desde a v2.33 — não regredir por 'consistência'.

    O currículo é documento de TERCEIRO: o RH precisa dele como veio, e a
    conversão de Word existe só na hora de SERVIR. Timbrá-lo seria alterar
    prova alheia.
    """
    print("\n[currículo: segue original, de propósito]")
    import inspect

    from app.api import talentos
    fonte = inspect.getsource(talentos.enviar_curriculo)
    checar("normalizar_para_pdf" not in fonte,
           "o upload do currículo NÃO normaliza")
    checar("ORIGINAL" in fonte,
           "e o docstring registra que é decisão, não esquecimento")


if __name__ == "__main__":
    test_certidao_do_creche_vira_pdf_timbrado()
    test_guarda_tambem()
    test_falha_de_conversao_nao_perde_o_documento()
    test_dossie_identifica_de_quem_e_cada_folha()
    test_curriculo_continua_original()

    print()
    if FALHAS:
        print(f"test_documento_timbrado: {len(FALHAS)} FALHA(S)")
        for f in FALHAS:
            print(f"  - {f}")
        sys.exit(1)
    print("test_documento_timbrado: OK")
