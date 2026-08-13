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
