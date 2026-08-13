"""A transcrição sai em PARÁGRAFOS, não num bloco único (v2.99).

Antes era `" ".join(...)`: 40 minutos de conversa viravam ~6.000 palavras num
parágrafo só, e o Bruno relatou o óbvio — *"a leitura fica difícil"*. O modelo já
devolve cada segmento com `start`/`end`, e era essa informação que estava sendo
jogada fora.

O que este teste protege:

1. **Pausa longa quebra parágrafo.** Numa entrevista, o silêncio entre turnos é
   onde um para de falar e o outro começa. Sem diarização não se sabe QUEM
   falou — mas se sabe que a fala mudou de dono, e a quebra reproduz isso.
2. **Fala corrida NÃO vira parágrafo de vinte linhas**: acima do teto, corta —
   mas só em fim de frase.
3. ⚠️ **NUNCA corta no meio de uma frase.** Dividir "trabalhei três anos na
   portaria" em duas linhas muda o que se lê, e a transcrição é peça que
   circula (vai ao PDF timbrado).
4. **Segmento vazio não vira parágrafo em branco** — o Whisper devolve trechos
   vazios em silêncio, e cada um viraria uma linha morta no meio do texto.

Roda no bloco stdlib do CI: a função é pura (recebe segmentos, devolve string) e
não importa `faster_whisper` — que só existe na imagem de transcrição.
"""

import pathlib
import sys

RAIZ = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from app.workers.transcricao import (PAUSA_PARAGRAFO_S,  # noqa: E402
                                     _em_paragrafos)

falhas: list[str] = []


def checar(ok: bool, descricao: str) -> None:
    print(f"  {'ok  ' if ok else 'FALHOU'}  {descricao}")
    if not ok:
        falhas.append(descricao)


class Seg:
    """O mínimo do segmento do faster-whisper que a função usa."""

    def __init__(self, text, start, end):
        self.text, self.start, self.end = text, start, end


def main() -> int:
    print("=== 1. Pausa longa separa parágrafos (troca de turno) ===")
    # Pergunta → pausa de 3s → resposta → pausa de 3s → nova pergunta.
    conversa = [
        Seg("Boa tarde, obrigado por vir.", 0, 2.0),
        Seg("Vamos falar da sua experiência.", 2.0, 4.0),
        Seg("Claro.", 7.0, 7.6),
        Seg("Trabalhei três anos na portaria de um condomínio.", 7.6, 11.0),
        Seg("Entendi. E por que saiu?", 14.5, 16.0),
    ]
    t = _em_paragrafos(conversa)
    paragrafos = t.split("\n\n")
    checar(len(paragrafos) == 3,
           f"três turnos viram três parágrafos (veio {len(paragrafos)})")
    checar(paragrafos[0].startswith("Boa tarde"),
           "o primeiro parágrafo é a pergunta de abertura")
    checar("Trabalhei três anos" in paragrafos[1],
           "a resposta fica junta no mesmo parágrafo (não houve pausa dentro dela)")

    print("\n=== 2. Fala contínua NÃO é quebrada ===")
    # Sem pausa nenhuma: tudo num parágrafo só, como foi dito.
    corrido = [Seg(f"frase {i}.", i * 2.0, i * 2.0 + 1.9) for i in range(6)]
    t = _em_paragrafos(corrido)
    checar("\n\n" not in t,
           "fala sem pausa não ganha quebra artificial")

    print("\n=== 3. Nunca corta no MEIO de uma frase ===")
    # Bloco longo SEM pontuação final até o fim: o teto de caracteres é
    # atingido, mas não há onde cortar sem partir a frase.
    longo = [Seg("palavra " * 30, i * 1.0, i * 1.0 + 0.9) for i in range(12)]
    t = _em_paragrafos(longo)
    for p in t.split("\n\n"):
        # Se cortou, o pedaço anterior tem que terminar em pontuação.
        pass
    partes = t.split("\n\n")
    ok = all(p.rstrip().endswith((".", "!", "?", "…")) for p in partes[:-1])
    checar(ok, f"todo corte por tamanho cai em fim de frase ({len(partes)} parágrafo(s))")

    print("\n=== 4. Fala longa COM frases quebra em fim de frase ===")
    frases = [Seg("Esta é uma frase de tamanho razoável para o teste. ",
                  i * 1.0, i * 1.0 + 0.9) for i in range(30)]
    t = _em_paragrafos(frases)
    partes = t.split("\n\n")
    checar(len(partes) > 1,
           f"fala muito longa ganha mais de um parágrafo (veio {len(partes)})")
    checar(all(p.rstrip().endswith((".", "!", "?", "…")) for p in partes[:-1]),
           "e cada corte cai em fim de frase")

    print("\n=== 5. Segmento vazio não vira linha em branco ===")
    com_vazios = [
        Seg("Primeira parte.", 0, 1.0),
        Seg("   ", 1.0, 1.2),
        Seg("", 1.2, 1.4),
        Seg("Segunda parte.", 1.4, 2.4),
    ]
    t = _em_paragrafos(com_vazios)
    checar("\n\n\n" not in t and t.count("\n\n") == 0,
           f"segmentos vazios são ignorados (veio {t!r})")

    # Seta ASCII nos prints: o console do Windows é cp1252 e estoura em "⇒".
    print("\n=== 6. Sem segmentos -> string vazia (nao quebra o chamador) ===")
    # O worker usa `if texto:` para decidir entre `pronta` e `inaudivel` —
    # devolver None quebraria essa decisão.
    checar(_em_paragrafos([]) == "", "lista vazia devolve string vazia, não None")

    print("\n=== 7. A constante da pausa é plausível ===")
    # Abaixo de 1s seria respiração no meio da frase; acima de 5s a conversa
    # inteira viraria um bloco de novo.
    checar(1.0 <= PAUSA_PARAGRAFO_S <= 5.0,
           f"PAUSA_PARAGRAFO_S = {PAUSA_PARAGRAFO_S}s está entre 1s e 5s")

    print("\n=== 8. Diarizacao: rotulo NEUTRO, numerado pela ORDEM DA CONVERSA ===")
    from app.workers.transcricao import _com_falantes, _falante_de

    # O pyannote devolve rótulos ARBITRÁRIOS e fora de ordem (SPEAKER_02 pode
    # falar primeiro). Numerar por eles daria "Interlocutor 3" numa conversa de
    # duas pessoas — e o RH procuraria um terceiro que não existe.
    trechos = [(0, 4.2, "SPEAKER_02"), (6.9, 11.2, "SPEAKER_00"),
               (14.4, 16.2, "SPEAKER_02")]
    conversa = [
        Seg("Boa tarde, obrigado por vir.", 0, 2.0),
        Seg("Vamos falar da sua experiência.", 2.0, 4.0),
        Seg("Claro.", 7.0, 7.6),
        Seg("Trabalhei três anos na portaria.", 7.6, 11.0),
        Seg("Entendi. E por que saiu?", 14.5, 16.0),
    ]
    t = _com_falantes(conversa, trechos)
    checar(t.startswith("[Interlocutor 1]"),
           f"quem fala PRIMEIRO e o Interlocutor 1 (veio {t[:20]!r})")
    checar("[Interlocutor 2]" in t, "o segundo falante ganha o rotulo 2")
    checar("[Interlocutor 3]" not in t,
           "conversa de duas vozes NAO inventa um terceiro (o rotulo do "
           "pyannote e arbitrario: SPEAKER_00 e _02)")
    checar("SPEAKER" not in t, "o rotulo interno do modelo nunca vaza para a tela")
    # Turnos consecutivos do mesmo falante viram UM parágrafo: um rótulo por
    # frase deixaria a leitura pior que o bloco corrido que veio consertar.
    checar(t.count("[Interlocutor 1]") == 2 and t.count("[Interlocutor 2]") == 1,
           "falas seguidas do mesmo interlocutor ficam num paragrafo so")

    print("\n=== 9. Diarizacao que FALHA degrada para o texto corrido ===")
    # A transcrição não pode se perder porque a diarização falhou: o texto é o
    # que serve para escrever a justificativa; saber quem falou é melhoria.
    sem = _com_falantes(conversa, None)
    checar("Interlocutor" not in sem and "Boa tarde" in sem,
           "sem trechos de falante, o texto sai sem rotulo — nunca vazio")

    # ⚠️ Exercita o CAMINHO REAL (`_transcrever`), não só a função interna: a
    # mutação que troca `if trechos:` por `if diarizar:` passava verde só com a
    # asserção acima — e ela é o defeito grave, porque com a diarização LIGADA e
    # o modelo indisponível o texto sairia sem os parágrafos da v2.99. Achado ao
    # rodar a mutação, não ao escrever o teste (a lição da v2.68/v2.98.4).
    import app.workers.transcricao as _mod

    class _Info:
        language = "pt"

    original_diarizar = _mod._diarizar
    original_modelo = None
    try:
        # Substitui o LIMITE EXTERNO: o modelo do Whisper e o do pyannote.
        # A diarização devolve `(trechos, aviso)` desde a v3.00.1: o motivo
        # da falha VOLTA para a tela, em vez de morrer no log.
        _mod._diarizar = lambda audio, token: (None, "modelo indisponivel")
        classe = type("W", (), {
            "__init__": lambda self, *a, **k: None,
            "transcribe": lambda self, *a, **k: (iter(conversa), _Info()),
        })
        import sys as _sys
        import types as _types
        falso = _types.ModuleType("faster_whisper")
        falso.WhisperModel = classe
        original_modelo = _sys.modules.get("faster_whisper")
        _sys.modules["faster_whisper"] = falso

        texto, _idi, aviso = _mod._transcrever(b"audio", "small", "pt",
                                               diarizar=True, hf_token="tok")
        checar("Boa tarde" in texto,
               "com diarizacao LIGADA e o modelo fora, o texto continua saindo")
        checar("Interlocutor" not in texto,
               "e sem rotulo inventado")
        checar("\n\n" in texto,
               "degrada para os PARAGRAFOS da v2.99, nao para um bloco unico")
    finally:
        _mod._diarizar = original_diarizar
        if original_modelo is None:
            _sys.modules.pop("faster_whisper", None)
        else:
            _sys.modules["faster_whisper"] = original_modelo

    print("\n=== 9b. A propria _diarizar devolve o MOTIVO, nao so None ===")
    # ⚠️ O caso 9 substitui `_diarizar` inteira, então nunca exercita o `return`
    # dela — a mutação que faz o aviso morrer no log passava VERDE. Aqui a
    # função REAL é chamada, nos dois caminhos de falha que existem sem rede:
    # sem token e com o pyannote ausente.
    _trechos, aviso_sem_token = _mod._diarizar(b"audio", "")
    checar(_trechos is None, "sem token, nao ha trechos")
    checar(bool(aviso_sem_token) and "token" in aviso_sem_token.lower(),
           f"e o motivo DIZ que falta o token (veio {str(aviso_sem_token)[:45]!r})")
    checar("Configurações" in (aviso_sem_token or ""),
           "e diz ONDE resolver — recusa sem saida deixa o problema na mao de "
           "quem opera (v2.87/v2.93)")

    # Com token, mas sem o pyannote instalado (é o caso da máquina de quem
    # desenvolve e da imagem da API): tem que devolver motivo, não estourar.
    _trechos2, aviso_falha = _mod._diarizar(b"audio", "hf_token_qualquer")
    checar(_trechos2 is None, "pyannote ausente nao devolve trechos")
    checar(bool(aviso_falha),
           "e a falha REAL tambem devolve motivo — nunca None silencioso")

    print("\n=== 10. O falante vem da MAIOR sobreposicao, nao do instante inicial ===")
    # Whisper e pyannote cortam em pontos diferentes: um segmento costuma
    # começar décimos ANTES de o falante assumir. Casar pelo início daria o
    # falante ANTERIOR em toda troca de turno — onde o rótulo mais importa.
    limite = [(0.0, 5.0, "A"), (5.0, 10.0, "B")]
    checar(_falante_de(4.8, 9.5, limite) == "B",
           "segmento que comeca no fim do turno anterior fica com quem fala mais")

    print("\n" + "=" * 62)
    if falhas:
        print(f"REPROVADO — {len(falhas)} verificação(ões) falharam:")
        for f in falhas:
            print(f"  - {f}")
        return 1
    print("APROVADO — a transcrição sai legível, sem cortar frase pela metade.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
