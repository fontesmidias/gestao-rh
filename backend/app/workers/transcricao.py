"""Transcrição de entrevista pela fila (v2.97).

Roda no container `transcricao`, não no `worker` comum: o `faster-whisper`
carrega um modelo na memória (~500 MB no `small`) e consome CPU por minutos.
Dentro da API competiria com requisição de gente real, e o nginx corta em 60s.

⚠️ **Este módulo NÃO importa `faster_whisper` no topo.** A imagem da API não tem
a dependência — só a do container de transcrição tem —, e um import de topo
quebraria o boot da API inteira por causa de uma função que ela nunca executa.
O import fica dentro de `_transcrever`.
"""

import io
import logging
import time
import uuid
from datetime import datetime, timezone

log = logging.getLogger(__name__)


def _config(db) -> dict:
    """Modelo e idioma, editáveis no painel — trocar `small` por `medium` não
    deve exigir deploy."""
    from app.services.config_dinamica import ler_config
    cfg = ler_config(db, ("transcricao_modelo", "transcricao_idioma"))
    from app.services.gravacao_entrevista import MODELO_PADRAO
    return {
        "modelo": (cfg.get("transcricao_modelo") or MODELO_PADRAO).strip(),
        # Fixar "pt" evita o auto-detect errar em áudio ruim e transcrever
        # português como espanhol — que sai plausível e errado.
        "idioma": (cfg.get("transcricao_idioma") or "pt").strip(),
    }


def _transcrever(audio: bytes, modelo: str, idioma: str) -> tuple[str, str]:
    """Devolve `(texto, idioma_detectado)`. Import local: ver o topo do módulo."""
    from faster_whisper import WhisperModel

    # `int8` roda em CPU com ~4x menos memória que `float32`, com perda de
    # qualidade irrelevante para fala. `cpu` explícito: sem GPU no VPS.
    w = WhisperModel(modelo, device="cpu", compute_type="int8")
    segmentos, info = w.transcribe(io.BytesIO(audio), language=idioma or None,
                                   vad_filter=True)
    # `vad_filter` corta silêncio — numa entrevista com pausas longas, isso é a
    # diferença entre minutos e dezenas de minutos de processamento.
    return _em_paragrafos(segmentos), getattr(info, "language", idioma)


# Uma pausa acima disto separa PARÁGRAFOS. 2,5s é a fronteira prática entre
# respirar no meio de uma frase e ceder a palavra — abaixo disso a conversa
# continua, acima dela alguém tomou o turno.
PAUSA_PARAGRAFO_S = 2.5


def _em_paragrafos(segmentos) -> str:
    """Junta os segmentos do Whisper em PARÁGRAFOS legíveis (v2.99).

    Antes era `" ".join(...)`: 40 minutos de conversa viravam um bloco único de
    ~6.000 palavras, e o Bruno relatou o óbvio — não se lê. O modelo já devolve
    cada segmento com `start`/`end`, e é essa informação que estava sendo jogada
    fora.

    Duas regras, e as duas vêm de como a fala funciona:

    1. **Pausa longa quebra parágrafo** (`PAUSA_PARAGRAFO_S`): numa entrevista, o
       silêncio entre turnos é justamente onde um para de falar e o outro começa.
       Sem diarização não se sabe QUEM falou — mas se sabe que a fala mudou de
       dono, e a quebra reproduz isso na página.
    2. **Parágrafo muito longo quebra na frase**: fala corrida sem pausa (alguém
       contando uma história) daria um parágrafo de vinte linhas. Acima do teto,
       corta no fim de frase mais próximo — nunca no meio.

    ⚠️ Nunca quebra no MEIO de uma frase por contagem de caracteres: dividir
    "trabalhei três anos na portaria" em duas linhas mudaria o sentido do que se
    lê, e a transcrição vira peça que circula.
    """
    paragrafos: list[str] = []
    atual: list[str] = []
    fim_anterior = None
    LIMITE_CHARS = 700          # ~10 linhas: acima disso o bloco cansa

    for s in segmentos:
        texto = (s.text or "").strip()
        if not texto:
            continue
        inicio = getattr(s, "start", None)
        pausa = (inicio - fim_anterior) if (inicio is not None and fim_anterior is not None) else 0
        atingiu_teto = sum(len(t) for t in atual) > LIMITE_CHARS
        # O teto só corta em FIM DE FRASE — no meio, mudaria o sentido.
        fecha_frase = bool(atual) and atual[-1].rstrip().endswith((".", "!", "?", "…"))
        if atual and (pausa >= PAUSA_PARAGRAFO_S or (atingiu_teto and fecha_frase)):
            paragrafos.append(" ".join(atual).strip())
            atual = []
        atual.append(texto)
        fim_anterior = getattr(s, "end", None)

    if atual:
        paragrafos.append(" ".join(atual).strip())
    return "\n\n".join(p for p in paragrafos if p).strip()


def transcrever_bloco(bloco_id: str) -> dict:
    """Transcreve UM bloco de ~10 min. É o caminho normal desde a v2.98.

    Um job por bloco, e não um job que percorre todos, por três razões:

    1. **O texto do começo aparece enquanto o fim ainda roda** — com um job
       único, o RH esperaria a entrevista inteira para ler a primeira frase.
    2. **Um bloco que falha não derruba os outros.** No job único, uma exceção
       no bloco 3 perderia o 4 e o 5 junto.
    3. **Retentar é barato**: reenfileira só o bloco que falhou, não 90 minutos.

    Ao terminar, chama `consolidar`, que decide o estado da gravação inteira
    (ver as três regras no docstring dela).
    """
    from app.core.db import SessionLocal
    from app.models.bloco_gravacao import BlocoGravacao, StatusBloco
    from app.services import storage
    from app.services.gravacao_entrevista import consolidar

    db = SessionLocal()
    inicio = time.monotonic()
    try:
        b = db.get(BlocoGravacao, uuid.UUID(bloco_id))
        if b is None:
            log.warning("Transcrição: bloco %s não existe mais.", bloco_id)
            return {"ok": False, "erro": "bloco_inexistente"}
        if not b.audio_key:
            b.status = StatusBloco.falhou
            b.erro = "O áudio deste trecho não foi guardado."
            db.commit()
            return {"ok": False, "erro": "sem_audio"}

        b.status = StatusBloco.processando
        db.commit()

        cfg = _config(db)
        texto, _idioma = _transcrever(storage.ler(b.audio_key),
                                      cfg["modelo"], cfg["idioma"])
        b.processamento_s = int(time.monotonic() - inicio)
        b.transcrito_em = datetime.now(timezone.utc)
        if texto:
            b.texto, b.status, b.erro = texto, StatusBloco.pronta, None
        else:
            # Bloco mudo é NORMAL (a pessoa lendo um documento, uma pausa longa)
            # e não contamina os outros — ver `consolidar`.
            b.status = StatusBloco.inaudivel
            b.erro = "Sem fala reconhecível neste trecho."
        db.commit()

        from app.models.gravacao_entrevista import GravacaoEntrevista
        g = db.get(GravacaoEntrevista, b.gravacao_id)
        if g is not None:
            consolidar(db, g)
            db.commit()
        return {"ok": bool(texto), "bloco": b.indice, "caracteres": len(texto or "")}

    except Exception as exc:                    # noqa: BLE001
        log.exception("Falha ao transcrever o bloco %s", bloco_id)
        try:
            b = db.get(BlocoGravacao, uuid.UUID(bloco_id))
            if b is not None:
                b.status = StatusBloco.falhou
                b.erro = f"Falha ao transcrever ({type(exc).__name__})."
                b.processamento_s = int(time.monotonic() - inicio)
                db.commit()
                from app.models.gravacao_entrevista import GravacaoEntrevista
                g = db.get(GravacaoEntrevista, b.gravacao_id)
                if g is not None:
                    # Consolida MESMO na falha: sem isto a gravação ficaria
                    # `processando` para sempre, e a tela mostraria um spinner
                    # eterno — indistinguível de "ainda está rodando".
                    consolidar(db, g)
                    db.commit()
        except Exception:                       # noqa: BLE001
            log.exception("Nem o estado de falha pôde ser gravado (%s)", bloco_id)
        return {"ok": False, "erro": type(exc).__name__}
    finally:
        db.close()


def transcrever(gravacao_id: str) -> dict:
    """Transcreve uma gravação de arquivo ÚNICO (sem blocos).

    Continua existindo para o áudio enviado de uma vez — o RH pode subir um
    arquivo gravado fora do sistema (celular, gravador). O caminho da gravação
    pelo navegador usa `transcrever_bloco`.

    Toda saída é um ESTADO GRAVADO, nunca silêncio (a regra do Match, v2.00):
    quem abrir a ficha depois precisa saber o que aconteceu com o áudio dele.
    """
    from app.core.db import SessionLocal
    from app.models.gravacao_entrevista import GravacaoEntrevista, StatusGravacao
    from app.services import storage

    db = SessionLocal()
    inicio = time.monotonic()
    try:
        g = db.get(GravacaoEntrevista, uuid.UUID(gravacao_id))
        if g is None:
            log.warning("Transcrição: gravação %s não existe mais.", gravacao_id)
            return {"ok": False, "erro": "gravacao_inexistente"}
        if not g.audio_key:
            g.status = StatusGravacao.falhou
            g.erro = "Não há áudio guardado para esta entrevista."
            db.commit()
            return {"ok": False, "erro": "sem_audio"}

        g.status = StatusGravacao.processando
        db.commit()

        cfg = _config(db)
        audio = storage.ler(g.audio_key)
        texto, idioma = _transcrever(audio, cfg["modelo"], cfg["idioma"])

        g.processamento_s = int(time.monotonic() - inicio)
        g.modelo, g.idioma = cfg["modelo"], idioma
        g.transcrito_em = datetime.now(timezone.utc)
        if not texto:
            # Gravou e não deu para transcrever: estado PRÓPRIO. Cair em
            # "falhou" faria o entrevistador procurar defeito no sistema quando
            # o problema é o áudio (microfone mudo, sala barulhenta).
            g.status = StatusGravacao.audio_inaudivel
            g.erro = ("O áudio não tem fala reconhecível. Confira se o microfone "
                      "estava captando.")
            db.commit()
            return {"ok": False, "erro": "audio_inaudivel"}

        g.texto = texto
        g.status = StatusGravacao.pronta
        g.erro = None
        db.commit()
        log.info("Transcrição %s pronta: %d caracteres em %ds.",
                 gravacao_id, len(texto), g.processamento_s)
        return {"ok": True, "caracteres": len(texto), "segundos": g.processamento_s}

    except Exception as exc:                    # noqa: BLE001
        log.exception("Falha ao transcrever %s", gravacao_id)
        try:
            g = db.get(GravacaoEntrevista, uuid.UUID(gravacao_id))
            if g is not None:
                g.status = StatusGravacao.falhou
                # A mensagem vai para a TELA: tipo do erro basta para orientar,
                # e o texto cru pode carregar caminho de arquivo.
                g.erro = f"Falha ao transcrever ({type(exc).__name__}). Tente de novo."
                g.processamento_s = int(time.monotonic() - inicio)
                db.commit()
        except Exception:                       # noqa: BLE001
            log.exception("Nem o estado de falha pôde ser gravado (%s)", gravacao_id)
        return {"ok": False, "erro": type(exc).__name__}
    finally:
        db.close()
