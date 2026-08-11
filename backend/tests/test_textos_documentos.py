"""Textos dos documentos editáveis pelo painel — e o limite disso (v2.90).

Segunda parte do pedido do Bruno (*"tornar os demais documentos editáveis"*),
com a ressalva dele: *"os que já foram assinados, obviamente que não"*.

O que se afirma aqui:

1. **O texto editado CHEGA AO PDF.** Não basta a função devolver o valor certo:
   o gerador tem que estar consumindo dela. Teste que exercita só a função
   passa verde com o caminho real quebrado (v2.68).
2. **Vazio volta ao padrão de fábrica** — é o caminho de desfazer, e sem ele o
   RH fica preso ao que escreveu (v2.68). Documento nenhum sai sem texto.
3. **Cada bloco é independente.** Editar o ciclo do VT não pode mexer no do VA:
   são benefícios diferentes, e trocá-los prometeria à pessoa uma data de
   pagamento que não se cumpre.
4. **A fonte continua ÚNICA**: `documentos_texto.py` (o corpo que o RH copia
   para um modelo) lê o mesmo texto do gerador do PDF. Divergir aqui é o
   defeito da v2.19, que perdeu 6% do VT e 8% do FGTS numa cópia à mão.

⚠️ Lição do próprio desenvolvimento: a primeira asserção conferia que a frase
antiga ("dia 1 ao dia 30") sumira do PDF — e ela CONTINUAVA lá, corretamente,
porque pertence ao vale-ALIMENTAÇÃO, outro bloco. Ao afirmar sobre ausência num
documento longo, confira a QUE seção o trecho pertence.
"""

import io
import os
import sys
import uuid
import pathlib

RAIZ = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

os.environ.setdefault("DATABASE_URL",
                      "postgresql+psycopg://admissao:admissao@localhost:55432/admissao")

from pypdf import PdfReader  # noqa: E402

from app.core.db import SessionLocal  # noqa: E402
from app.models.candidato import (Candidato, PostoServico,  # noqa: E402
                                  StatusCandidato)
from app.models.ficha import DadosPessoais, DocumentosIdentificacao  # noqa: E402
from app.models.modelo_documento import ModeloDocumento  # noqa: E402,F401
from app.models.usuario_rh import UsuarioRH  # noqa: E402,F401
from app.services import fichas, textos_documentos  # noqa: E402

NOVO_VT = "O beneficio sera pago do dia 1 ao dia 25 de cada mes, por PIX."


def _texto_pdf(pdf: bytes) -> str:
    """Texto de TODAS as páginas (v2.89: a primeira versão só lia a página 1)."""
    r = PdfReader(io.BytesIO(pdf))
    return " ".join(" ".join(p.extract_text() or "" for p in r.pages).split())


def main() -> int:
    falhas: list[str] = []
    db = SessionLocal()
    marca = uuid.uuid4().hex[:8]
    try:
        posto = PostoServico(nome=f"Posto Texto {marca}")
        db.add(posto)
        db.commit()
        db.refresh(posto)
        cand = Candidato(nome_completo=f"Pessoa Texto {marca}", cargo_funcao="Vigia",
                         status=StatusCandidato.preenchendo,
                         posto_servico_id=posto.id, regime="efetivo")
        db.add(cand)
        db.commit()
        db.refresh(cand)
        db.add(DocumentosIdentificacao(candidato_id=cand.id, cpf="12345678901"))
        db.add(DadosPessoais(candidato_id=cand.id))
        db.commit()

        # O padrão de FÁBRICA, não o valor em vigor: execuções anteriores
        # podem ter deixado texto gravado, e comparar com o que está no banco
        # compararia o valor com ele mesmo — a tautologia da v2.64. Também é o
        # que faz o teste não depender de banco limpo (v2.14).
        padrao_vt = textos_documentos._padrao("texto_ciclo_vt_efetivo")
        padrao_va = textos_documentos._padrao("texto_ciclo_va_efetivo")
        # Garante o piso: se uma execução anterior morreu no meio, o banco pode
        # ter ficado sujo. Teste que exige banco limpo é armadilha (v2.66).
        for chave in ("texto_ciclo_vt_efetivo", "texto_ciclo_va_efetivo",
                      "texto_direitos_trabalhador"):
            textos_documentos.salvar(db, chave, "")
        db.commit()

        # 1. O texto editado chega ao PDF gerado.
        textos_documentos.salvar(db, "texto_ciclo_vt_efetivo", NOVO_VT)
        db.commit()
        texto = _texto_pdf(fichas._gerar_informativo_integracao(db, cand, "efetivo"))
        if "dia 1 ao dia 25" not in texto:
            falhas.append(
                "o PDF não usou o texto editado — o gerador não está lendo de "
                "`textos_documentos`, e a edição no painel não teria efeito "
                "nenhum sobre o papel que a pessoa assina.")

        # 3. O bloco vizinho (vale-alimentação) NÃO foi afetado. Editar o ciclo
        #    do VT mexendo no do VA prometeria data de pagamento que não se
        #    cumpre — e é o tipo de erro que ninguém confere no PDF.
        if padrao_va not in texto:
            falhas.append(
                "editar o ciclo do VT alterou (ou apagou) o texto do "
                "vale-ALIMENTAÇÃO — os blocos precisam ser independentes.")

        # 2. Vazio volta ao padrão: é o caminho de desfazer.
        textos_documentos.salvar(db, "texto_ciclo_vt_efetivo", "")
        db.commit()
        if textos_documentos.texto(db, "texto_ciclo_vt_efetivo") != padrao_vt:
            falhas.append("limpar o texto não voltou ao padrão de fábrica.")
        texto = _texto_pdf(fichas._gerar_informativo_integracao(db, cand, "efetivo"))
        if "dia 1 ao dia 25" in texto:
            falhas.append("o PDF ainda carrega o texto removido.")

        # 4. Fonte única: o corpo copiável lê o mesmo texto do gerador.
        textos_documentos.salvar(db, "texto_direitos_trabalhador",
                                 "a) Direito de teste desta leva;")
        db.commit()
        from app.services import documentos_texto
        corpo = documentos_texto.corpo_editavel("informacoes_trabalhador", db)
        if "Direito de teste desta leva" not in corpo:
            falhas.append(
                "o corpo copiável NÃO acompanhou o texto editado — a amostra "
                "que o RH duplica divergiria do documento oficial (v2.19).")
        textos_documentos.salvar(db, "texto_direitos_trabalhador", "")
        db.commit()
    finally:
        db.close()

    if falhas:
        print("FALHOU:")
        for f in falhas:
            print("  •", f)
        return 1
    print("OK — o texto editado chega ao PDF, vazio volta ao padrão, os blocos\n"
          "     são independentes e o corpo copiável acompanha.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
