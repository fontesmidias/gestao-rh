"""A data do documento: escolhida pelo RH, mas NUNCA por cima da assinatura (v2.89).

O papel costuma sair dias depois do ato — a integração aconteceu segunda e o
documento é impresso na quarta —, então o RH define a data que os documentos
daquela pessoa carimbam. O que este teste protege é o limite disso:

**Documento assinado ignora a escolha.** O `hash_sha256` do ato é calculado
sobre o PDF (`api/assinaturas.py`), e todo manifesto emitido aponta para ele.
Se a data configurada vazasse para um documento assinado, o PDF deixaria de se
reproduzir e a verificação de autenticidade passaria a acusar divergência — na
peça que se usa em disputa trabalhista. Nada na tela denunciaria: o documento
continua abrindo, bonito, com a data errada.

⚠️ **Lição do próprio desenvolvimento deste teste**: a primeira versão procurava
a data em `pages[0]` e deu "não encontrado" para um PDF que estava CERTO — a
data fica na página 3 do acordo. Extraia o texto de TODAS as páginas antes de
afirmar que algo não está lá (é a v2.56 numa variação: lá a quebra de linha
escondia a frase, aqui a paginação).
"""

import io
import os
import sys
import uuid
import pathlib
from datetime import date, datetime, timezone

RAIZ = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

os.environ.setdefault("DATABASE_URL",
                      "postgresql+psycopg://admissao:admissao@localhost:55432/admissao")

from pypdf import PdfReader  # noqa: E402

from app.core.db import SessionLocal  # noqa: E402
from app.models.assinatura import Assinatura, DocumentoAssinavel  # noqa: E402
from app.models.candidato import (Candidato, PostoServico,  # noqa: E402
                                  StatusCandidato)
from app.models.ficha import DadosPessoais, DocumentosIdentificacao  # noqa: E402
# Alvos de FK da `assinatura` — precisam estar no `metadata` antes do primeiro
# flush, mesmo sem uso direto aqui. O erro não fala do SEU modelo, fala do
# vizinho: `NoReferencedTableError: ... could not find table 'modelo_documento'`
# (a armadilha da v2.64, que se paga em todo teste que não sobe a app).
from app.models.modelo_documento import ModeloDocumento  # noqa: E402,F401
from app.models.usuario_rh import UsuarioRH  # noqa: E402,F401
from app.services import fichas  # noqa: E402


def _texto(pdf: bytes) -> str:
    """Texto de TODAS as páginas, normalizado. Ver o aviso no topo do arquivo."""
    r = PdfReader(io.BytesIO(pdf))
    return " ".join(" ".join(p.extract_text() or "" for p in r.pages).split())


def main() -> int:
    falhas: list[str] = []
    db = SessionLocal()
    marca = uuid.uuid4().hex[:8]
    escolhida = date(2026, 8, 3)
    try:
        posto = PostoServico(nome=f"Posto Data {marca}")
        db.add(posto)
        db.commit()
        db.refresh(posto)

        cand = Candidato(nome_completo=f"Pessoa Data {marca}", cargo_funcao="Vigia",
                         status=StatusCandidato.preenchendo,
                         posto_servico_id=posto.id)
        db.add(cand)
        db.commit()
        db.refresh(cand)
        db.add(DocumentosIdentificacao(candidato_id=cand.id, cpf="12345678901"))
        db.add(DadosPessoais(candidato_id=cand.id))
        db.commit()

        # 1. Sem escolha: vale o dia da geração — o comportamento de sempre.
        if fichas.data_do_documento(cand) != date.today():
            falhas.append("sem data escolhida, o documento deveria usar hoje.")

        # 2. Com escolha: o PDF REAL carimba a data escolhida. Afirmar sobre o
        #    PDF, e não só sobre a função, é o que prova que a ligação existe —
        #    a função certa com o gerador não a chamando passaria verde (v2.68).
        cand.data_documentos = escolhida
        db.commit()
        texto = _texto(fichas.gerar_acordo_confidencialidade(db, cand))
        if escolhida.strftime("%d/%m/%Y") not in texto:
            falhas.append(
                f"o PDF não carimbou a data escolhida ({escolhida:%d/%m/%Y}) — "
                "o gerador não está usando `data_do_documento`.")
        if date.today().strftime("%d/%m/%Y") in texto:
            falhas.append("o PDF ainda carimba a data de hoje, ignorando a escolha.")

        # 3. A GARANTIA CENTRAL: assinado ignora a escolha e mantém o ato.
        assinado_em = datetime(2026, 7, 15, 10, 0, tzinfo=timezone.utc)
        a = Assinatura(candidato_id=cand.id,
                       documento=DocumentoAssinavel.ficha_cadastro,
                       assinado_em=assinado_em)
        db.add(a)
        db.commit()
        resolvida = fichas.data_do_documento(cand, a)
        if resolvida != assinado_em.date():
            falhas.append(
                f"documento ASSINADO usou {resolvida} em vez da data da "
                f"assinatura ({assinado_em.date()}) — o hash do ato foi "
                "calculado sobre o PDF com a data original, e mudá-la destrói "
                "a verificação de autenticidade.")

        # 4. Limpar volta ao padrão: sem isso não há como desfazer (v2.68).
        cand.data_documentos = None
        db.commit()
        if fichas.data_do_documento(cand) != date.today():
            falhas.append("limpar a data não voltou ao padrão (hoje).")
    finally:
        db.close()

    if falhas:
        print("FALHOU:")
        for f in falhas:
            print("  •", f)
        return 1
    print("OK — a data escolhida chega ao PDF, e o documento assinado mantém a\n"
          "     data do ato, que é sobre o que o hash foi calculado.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
