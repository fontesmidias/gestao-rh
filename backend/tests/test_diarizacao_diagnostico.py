"""A separação de vozes falha DIZENDO a causa certa (v3.00.4).

Defeito de campo, 2026-08-13: a ficha da entrevista mostrou

    "Não foi possível separar quem falou (AttributeError). […] Confira o token
     do Hugging Face e se a licença do modelo foi aceita."

e **o token estava correto**. A mensagem mandava conferir a coisa errada, que é
o defeito mais caro do gênero neste projeto (v2.93: a analista tomou o erro 8×
em 70 minutos e desmarcou três exigências médicas por diagnóstico errado).

São TRÊS causas com ações diferentes, e este teste trava a distinção:

1. **Incompatibilidade de versão.** O `pyannote.audio` 3.x declara as
   dependências SEM TETO, e `torchaudio` 2.9 removeu `AudioMetaData` enquanto o
   `huggingface_hub` 1.0 removeu `use_auth_token` — as duas em out/2025. Com
   faixa aberta o pip pega a mais nova e o import quebra, **antes de tocar no
   áudio**. Ninguém do RH resolve isso trocando token.
2. **Licença não aceita.** `Pipeline.from_pretrained` devolve `None` — sem
   levantar — quando o acesso é negado; o `AttributeError` aparece só na linha
   SEGUINTE, a um passo da causa e com a cara de biblioteca quebrada.
3. **Token inválido.** Aí sim, gerar outro.

E a armadilha que fazia o teste de token mentir: **são DUAS licenças**
(`speaker-diarization-3.1` usa `segmentation-3.0` por baixo). Conferir uma só
respondia "vai funcionar" com a outra faltando, e a falha aparecia depois, numa
entrevista de 40 minutos.

Estrutural (stdlib + `ast`): roda no CI sem baixar 500 MB de modelo.
"""

import ast
import pathlib
import sys

RAIZ = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

falhas: list[str] = []


def checar(ok: bool, descricao: str) -> None:
    print(f"  {'ok  ' if ok else 'FALHOU'}  {descricao}")
    if not ok:
        falhas.append(descricao)


def _funcao(fonte: str, nome: str) -> ast.FunctionDef | None:
    for no in ast.walk(ast.parse(fonte)):
        if isinstance(no, ast.FunctionDef) and no.name == nome:
            return no
    return None


def main() -> int:
    print("== Diagnóstico da separação de vozes (v3.00.4) ==")

    worker = (RAIZ / "app/workers/transcricao.py").read_text(encoding="utf-8")
    api = (RAIZ / "app/api/entrevistas.py").read_text(encoding="utf-8")
    dockerfile = (RAIZ / "Dockerfile.transcricao").read_text(encoding="utf-8")
    tela = (RAIZ.parent / "frontend/src/rh/TokenDiarizacao.jsx").read_text(encoding="utf-8")

    # --- 1. Versões CRAVADAS -------------------------------------------------
    # Faixa aberta = a diarização quebra sozinha no próximo rebuild, sem
    # ninguém ter mexido em nada. É o defeito que motivou esta versão.
    checar("torchaudio==2.8.0" in dockerfile,
           "`torchaudio` cravado (2.9 removeu `AudioMetaData`)")
    checar("torch==2.8.0" in dockerfile,
           "`torch` cravado, para casar com o torchaudio")
    checar("pyannote.audio==3.3.2" in dockerfile,
           "`pyannote.audio` cravado")
    checar("huggingface_hub<1.0" in dockerfile,
           "`huggingface_hub` com TETO (1.0 removeu `use_auth_token`)")
    # `torchvision` é importado pelo pyannote e NÃO declarado por ele — o pip
    # não o instalava, e a diarização morria com `ModuleNotFoundError` (v3.00.5).
    checar("torchvision==0.23.0" in dockerfile,
           "`torchvision` instalado e cravado (o pyannote o usa sem declarar)")
    # ⚠️ Uma resolução SÓ: instalado num `pip install` posterior, o pyannote
    # reabre as faixas e o pip troca o torch por baixo — foi o que o log do
    # build mostrou acontecendo (torch 2.13, huggingface_hub 1.27).
    bloco = dockerfile[dockerfile.index("RUN pip install"):]
    bloco = bloco[:bloco.index("COPY")]
    checar(bloco.count("pip install") == 2,
           "torch e pyannote na MESMA resolução do pip (senão um sobrescreve o "
           "outro)")
    # Guarda-corpo: importar no build faz módulo faltando reprovar no CI, em
    # vez de virar erro na ficha da entrevista.
    checar("from pyannote.audio import Pipeline" in dockerfile,
           "o build IMPORTA o que a diarização usa, e falha se faltar")
    for aberto in ('"torchaudio>=2.2,<3"', '"torch>=2.2,<3"',
                   '"pyannote.audio>=3.1,<4"'):
        checar(aberto not in dockerfile,
               f"não voltou a faixa aberta em {aberto}")

    # --- 2. `from_pretrained` devolve None em silêncio ------------------------
    diarizar = _funcao(worker, "_diarizar")
    checar(diarizar is not None, "a função `_diarizar` existe")
    if diarizar is None:
        return 1
    corpo = ast.unparse(diarizar)

    checar("if pipe is None" in corpo,
           "checa `pipe is None` — o pyannote NEGA acesso devolvendo None")
    # A checagem tem de vir ANTES do uso, senão não protege nada: é o
    # `AttributeError` que apareceu na tela do Bruno.
    checar(corpo.index("if pipe is None") < corpo.index("pipe(caminho)"),
           "a checagem vem ANTES de usar o `pipe`")
    checar("segmentation-3.0" in corpo,
           "a recusa por licença nomeia os DOIS modelos")

    # --- 3. A mensagem distingue a causa -------------------------------------
    checar("ModuleNotFoundError" in corpo,
           "biblioteca AUSENTE é caso próprio e NOMEIA o módulo que falta")
    checar("AudioMetaData" in corpo and "use_auth_token" in corpo,
           "reconhece a falha de VERSÃO pelo texto do erro")
    checar("não é problema do seu token" in corpo,
           "falha de versão NÃO manda o RH mexer no token")
    # ⚠️ Afirmar que o TEXTO existe não basta — uma mutação que desligava o
    # `if de_versao` (trocando por `if False`) passou verde na primeira versão
    # deste teste: a mensagem continuava escrita no arquivo, morta. A garantia
    # tem de ser que a decisão é TOMADA, e isso se lê na árvore, não no texto.
    usa_no_if = any(
        isinstance(no, ast.If) and any(
            isinstance(x, ast.Name) and x.id == "de_versao"
            for x in ast.walk(no.test))
        for no in ast.walk(diarizar))
    checar(usa_no_if, "`de_versao` DECIDE a mensagem (está num `if`, não morto)")
    # O pyannote explica a recusa com print(), que some do log — e o log é onde
    # se procura depois.
    checar("redirect_stdout" in corpo,
           "captura o stdout do pyannote para o log")

    # --- 4. O teste de token confere as DUAS licenças ------------------------
    testar = _funcao(api, "testar_token_diarizacao")
    checar(testar is not None, "a rota `testar_token_diarizacao` existe")
    if testar is None:
        return 1
    corpo_t = ast.unparse(testar)
    checar("pyannote/segmentation-3.0" in corpo_t,
           "o teste de token confere TAMBÉM o modelo de segmentação")
    checar("for modelo in" in corpo_t,
           "percorre os modelos em vez de conferir um só")
    # O Hub esconde modelo gated de quem não tem acesso: 404 aqui é falta de
    # licença, não modelo inexistente.
    checar("(403, 404)" in corpo_t,
           "trata 404 como licença faltando (o Hub esconde modelo gated)")

    # --- 5. A tela manda aceitar as duas -------------------------------------
    checar("segmentation-3.0" in tela,
           "a tela do token lista as DUAS licenças")

    print()
    if falhas:
        print(f"FALHOU: {len(falhas)} verificação(ões)")
        for f in falhas:
            print(f"  - {f}")
        return 1
    print("Tudo certo.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
