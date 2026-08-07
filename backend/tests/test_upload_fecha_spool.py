"""O upload do candidato fecha o spool — e recusa o que não deve entrar.

Por que este teste existe (v2.71): o `upload_seguro.py` nasceu na v2.56 para
resolver exatamente isto no creche e no portal, e deixou de fora o fluxo de
MAIOR volume do sistema. `documentos.py` (envio de documento pelo candidato,
rota PÚBLICA) e `rh_ficha.py` (inserção pelo RH) liam com `up.file.read()` cru,
sem `close()` em lugar nenhum do arquivo.

O Starlette faz *spool* em disco de qualquer upload acima de ~1MB. Sem fechar,
o temporário fica no container — e o que passa por ali é RG, CPF, certidão de
nascimento. Pior, num LOOP: N arquivos enviados = N spools vazados por
requisição.

Duas coisas que este teste trava, além do `close()`:

1. **`ler_upload_sync` existe e é SÍNCRONA.** As rotas de documentos são `def`
   (rodam no threadpool do FastAPI) porque fazem OCR pela Mistral com timeout
   de até 120s. Convertê-las para `async` só para usar o `ler_upload`
   assíncrono jogaria essa chamada bloqueante no event loop e travaria a API
   inteira a cada envio — trocaria vazamento de arquivo por indisponibilidade.
   Se alguém "simplificar" removendo a variante síncrona, o teste reprova.

2. **`marca.py` não aceita SVG.** SVG é código: um `<script>` dentro dele
   executa quando o navegador abre, e a logo é servida com
   `media_type: image/svg+xml` em rota PÚBLICA, no mesmo domínio do painel —
   XSS armazenado. Vale na SAÍDA também: tirar só do upload deixaria a logo
   enviada antes ainda sendo servida como SVG executável.

Roda sem banco e sem rede: usa um stub de `Session` para o teto de tamanho.

Rode: PYTHONPATH=. .venv/Scripts/python.exe tests/test_upload_fecha_spool.py
"""

import io
import pathlib
import sys
import tempfile

from fastapi import HTTPException
from starlette.datastructures import UploadFile

from app.services.upload_seguro import (EXTENSOES_COM_WORD, ler_upload_sync,
                                        teto_bytes)

RAIZ = pathlib.Path(__file__).resolve().parents[1]
FALHAS: list[str] = []


def checar(condicao: bool, descricao: str) -> None:
    print(("  ok    " if condicao else "  FALHA ") + descricao)
    if not condicao:
        FALHAS.append(descricao)


def _tem_no_codigo(texto: str, trecho: str) -> bool:
    """O trecho aparece numa linha de CÓDIGO (não em comentário nem docstring).

    Sem isto, procurar `up.file.read()` no arquivo acusaria o comentário que
    explica a correção — o teste reprovaria justamente a documentação do que
    ele existe para garantir.
    """
    dentro_docstring = False
    for linha in texto.splitlines():
        sem_espaco = linha.strip()
        if sem_espaco.count('"""') % 2 == 1:
            dentro_docstring = not dentro_docstring
            continue
        if dentro_docstring or sem_espaco.startswith("#"):
            continue
        codigo = linha.split("#", 1)[0]      # comentário no fim da linha
        if trecho in codigo:
            return True
    return False


class _SessaoFake:
    """`ler_upload_sync` só usa a sessão para ler o teto da config."""

    def execute(self, *a, **k):
        class _R:
            def all(self):
                return []
        return _R()

    def scalars(self, *a, **k):
        class _R:
            def all(self):
                return []
        return _R()


def _upload_grande(nome: str, tamanho: int) -> UploadFile:
    """UploadFile acima do limite de spool — o Starlette rola para disco."""
    spool = tempfile.SpooledTemporaryFile(max_size=1024 * 1024)
    spool.write(b"x" * tamanho)
    spool.seek(0)
    return UploadFile(file=spool, filename=nome, size=tamanho)


def main() -> int:
    print("Upload do candidato: spool fechado e formatos recusados\n")
    db = _SessaoFake()

    # ---------------------------------------------------------------- 1
    # O spool é FECHADO — é o ponto central. Um arquivo de 2MB obriga o
    # Starlette a rolar para disco; depois da leitura ele tem que estar fechado.
    up = _upload_grande("rg.jpg", 2 * 1024 * 1024)
    checar(not up.file.closed, "antes da leitura, o spool está aberto")
    dados = ler_upload_sync(db, up, EXTENSOES_COM_WORD)
    checar(len(dados) == 2 * 1024 * 1024, "o conteúdo é lido por inteiro")
    checar(up.file.closed, "DEPOIS da leitura, o spool está FECHADO")

    # ---------------------------------------------------------------- 2
    # Recusa fecha o spool também: recusar e deixar o temporário no disco
    # seria o pior dos dois mundos — sem o dado gravado e com ele esquecido.
    up_exe = _upload_grande("virus.exe", 2 * 1024 * 1024)
    try:
        ler_upload_sync(db, up_exe, EXTENSOES_COM_WORD)
        recusou = False
    except HTTPException as e:
        recusou = e.status_code == 422
    checar(recusou, ".exe é recusado (422)")
    checar(up_exe.file.closed, "mesmo RECUSADO, o spool é fechado")

    # ---------------------------------------------------------------- 3
    # A tela oferece .doc/.docx (Camera.jsx, Checklist.jsx). A lista curta
    # recusaria o que a própria tela ofereceu — armadilha registrada na v2.61.
    up_doc = UploadFile(file=io.BytesIO(b"conteudo"), filename="curriculo.docx")
    try:
        ler_upload_sync(db, up_doc, EXTENSOES_COM_WORD)
        aceitou_word = True
    except HTTPException:
        aceitou_word = False
    checar(aceitou_word, ".docx é aceito (a tela do candidato o oferece)")

    # ---------------------------------------------------------------- 4
    # As rotas continuam SÍNCRONAS e usam a variante síncrona.
    for arq, rotas in (("app/api/documentos.py", ("enviar_arquivo",
                                                  "enviar_identidade")),
                       ("app/api/rh_ficha.py", ("inserir_arquivo_rh",))):
        texto = (RAIZ / arq).read_text(encoding="utf-8")
        checar("ler_upload_sync" in texto,
               f"{arq} usa ler_upload_sync")
        # Só linhas de CÓDIGO: o comentário que EXPLICA a correção cita
        # `up.file.read()` de propósito, e uma busca no texto cru acusaria o
        # próprio comentário — teste que reprova a documentação do conserto.
        checar(not _tem_no_codigo(texto, "up.file.read()"),
               f"{arq} não tem mais `up.file.read()` cru")
        for rota in rotas:
            checar(f"async def {rota}" not in texto,
                   f"{arq}: `{rota}` continua SÍNCRONA (OCR bloqueante no "
                   f"threadpool, nunca no event loop)")

    # ---------------------------------------------------------------- 5
    # SVG fora do upload E da saída da marca.
    marca = (RAIZ / "app/api/marca.py").read_text(encoding="utf-8")
    depois_tipos = marca.split("_TIPOS_IMG", 1)[1]
    bloco_allowlist = depois_tipos.split("}", 1)[0]
    checar("svg" not in bloco_allowlist,
           "marca.py: SVG fora da allowlist de upload")
    corpo_servir = marca.split("def _servir", 1)[1]
    checar('"svg"' not in corpo_servir.split("return Response", 1)[0],
           "marca.py: SVG fora do mapa do _servir (logo antiga não é servida "
           "como SVG executável)")
    checar("arquivo.file.close()" in marca, "marca.py: fecha o spool")

    # ---------------------------------------------------------------- 6
    # O webhook deriva o tipo do anexo da extensão (era application/pdf fixo).
    wh = (RAIZ / "app/services/webhook_email.py").read_text(encoding="utf-8")
    # De novo só o CÓDIGO: o docstring do módulo documenta o contrato do JSON
    # e mostra `"tipo": "application/pdf"` como EXEMPLO de saída correta para
    # um .pdf — o que é certo, e não pode reprovar o teste.
    checar(not _tem_no_codigo(wh, '"tipo": "application/pdf"'),
           "webhook_email.py: tipo do anexo não é mais chumbado")
    checar("_tipo_do_anexo" in wh,
           "webhook_email.py: deriva o tipo pela extensão")

    print()
    if FALHAS:
        print(f"{len(FALHAS)} FALHA(S):")
        for f in FALHAS:
            print("  - " + f)
        return 1
    print("Tudo certo.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
