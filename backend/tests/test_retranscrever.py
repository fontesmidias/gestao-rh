"""Refazer a transcrição a partir do áudio guardado (v3.00.3).

Pedido do Bruno em 2026-08-12, depois que a separação de vozes entrou no ar:
*"os antigos, queria utilizar já esse novo padrão com o hugging face"*. As
entrevistas transcritas ANTES da v3.00 saíram como texto corrido, e o áudio
delas continua guardado — dá para refazer sem regravar nada.

O que este teste protege são **dois defeitos que não dão erro nenhum**:

1. **A rota exigia `g.audio_key`** — campo que só o envio de ARQUIVO ÚNICO
   preenche. Quem gravou pelo navegador (o caminho normal desde a v2.98) guarda
   o áudio em `BlocoGravacao`, então recebia `404 sem_audio` com a entrevista
   inteira guardada ao lado. É a família do "a informação já existia, no lugar
   errado" (v2.95): o áudio está lá, a rota é que olhava para o campo errado.

2. **A rota exigia falha.** Aceitar só `falhou`/`audio_inaudivel` deixava sem
   saída justamente o caso do pedido — transcrição **`pronta`** é o estado
   normal de quem quer o padrão novo.

E uma decisão que não deve ser afrouxada: **refazer reenfileira um bloco por
tarefa**, o mesmo caminho do envio normal. Uma tarefa só para a entrevista
inteira faria um bloco ruim derrubar os outros oitenta minutos — o oposto da
garantia que os blocos existem para dar (v2.98).

Estrutural de propósito (stdlib + `ast`, sem banco): roda no CI junto dos
demais, e o que ele afirma é sobre o CÓDIGO da rota, não sobre uma resposta.
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
    print("== Refazer a transcrição (v3.00.3) ==")

    api = (RAIZ / "app/api/entrevistas.py").read_text(encoding="utf-8")
    servico = (RAIZ / "app/services/gravacao_entrevista.py").read_text(encoding="utf-8")
    tela = (RAIZ.parent / "frontend/src/rh/GravacaoEntrevista.jsx").read_text(encoding="utf-8")

    rota = _funcao(api, "retranscrever")
    checar(rota is not None, "a rota `retranscrever` existe")
    if rota is None:
        return 1
    corpo = ast.unparse(rota)

    # 1. Aceita quem gravou em BLOCOS -------------------------------------
    # A mutação que reintroduz `not g.audio_key` no guard é pega aqui: com ela,
    # o `blocos_de` some da rota (ou deixa de decidir), e a gravação do
    # navegador volta a receber 404.
    checar("blocos_de" in corpo,
           "a rota consulta os BLOCOS (não só `g.audio_key`)")
    checar("transcrever_bloco" in corpo,
           "reenfileira `transcrever_bloco` — uma tarefa por trecho")
    # O 404 ainda existe, mas só quando NÃO há bloco NEM áudio: é o caso do
    # áudio expurgado pela retenção, e a mensagem tem de dizer isso (v2.93 —
    # recusa que não oferece a saída faz consertar a coisa errada).
    # ⚠️ Afirma sobre a ÁRVORE, não sobre o texto: o `ast.unparse` escreve
    # `not blocos and (not g.audio_key)` — com parênteses —, e procurar a frase
    # como ela está no arquivo reprovaria código correto.
    guard = corpo.replace("(", "").replace(")", "")
    checar("not blocos and not g.audio_key" in guard,
           "só recusa quando não há bloco NEM áudio único")
    checar("retenção" in corpo or "retencao" in corpo,
           "a recusa explica que o áudio pode ter expirado")

    # 2. Aceita gravação PRONTA -------------------------------------------
    # Sem asserção sobre AUSÊNCIA aqui o teste não protege nada: o defeito
    # original era justamente um guard a mais.
    for proibido in ("StatusGravacao.falhou", "StatusGravacao.audio_inaudivel",
                     "StatusGravacao.pronta"):
        checar(f"{proibido} ==" not in corpo and f"== {proibido}" not in corpo,
               f"não exige status específico ({proibido.split('.')[-1]})")

    # Os blocos voltam para `aguardando`: deixá-los `pronto` faria o worker
    # pular o trabalho e a gravação ficaria presa em `aguardando` para sempre.
    checar("StatusBloco.aguardando" in corpo,
           "devolve os blocos a `aguardando` antes de reenfileirar")

    # 3. A tela sabe QUANDO oferecer ---------------------------------------
    # Oferecer sempre custaria ~1,7× a duração do áudio por nada.
    checar('"tem_falantes"' in servico,
           "o resumo diz se o texto já está separado por interlocutor")
    checar("bool(g.audio_key) or bool(blocos)" in servico,
           "`tem_audio` conta os blocos — senão a tela diz 'sem áudio' com o "
           "áudio guardado")
    checar('"diarizar"' in servico,
           "o resumo diz se a separação está ligada")

    checar("g.tem_audio && !g.tem_falantes" in tela,
           "a tela só oferece refazer quando há áudio e o texto é corrido")
    checar("g.diarizar !== false" in tela,
           "a tela não oferece refazer com a separação DESLIGADA (devolveria "
           "o mesmo texto)")

    # 4. Uma fonte só para a diarização ------------------------------------
    # Duas leituras da mesma chave divergem na primeira mudança de regra.
    checar(api.count('transcricao_diarizar') <= 1,
           "a chave `transcricao_diarizar` é lida num lugar só na API")

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
