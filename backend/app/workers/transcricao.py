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
import sys
import time
import uuid
from datetime import datetime, timezone

log = logging.getLogger(__name__)


def _config(db) -> dict:
    """Modelo e idioma, editáveis no painel — trocar `small` por `medium` não
    deve exigir deploy."""
    from app.services.config_dinamica import ler_config
    cfg = ler_config(db, ("transcricao_modelo", "transcricao_idioma",
                          "transcricao_diarizar", "transcricao_hf_token"))
    from app.services.gravacao_entrevista import MODELO_PADRAO
    return {
        # Ligada por padrão (decisão do Bruno, 2026-08-12), mas desligável sem
        # deploy: o custo é TEMPO (RTF ~1,74 em CPU), e quem sente isso é quem
        # espera a transcrição.
        "diarizar": (cfg.get("transcricao_diarizar") or "1").strip() != "0",
        # ⚠️ Token do HuggingFace: o modelo do pyannote é GATED (exige aceite de
        # licença). NUNCA vai para log nem volta ao painel — é credencial.
        "hf_token": (cfg.get("transcricao_hf_token") or "").strip(),
        "modelo": (cfg.get("transcricao_modelo") or MODELO_PADRAO).strip(),
        # Fixar "pt" evita o auto-detect errar em áudio ruim e transcrever
        # português como espanhol — que sai plausível e errado.
        "idioma": (cfg.get("transcricao_idioma") or "pt").strip(),
    }


def _transcrever(audio: bytes, modelo: str, idioma: str,
                 diarizar: bool = False, hf_token: str = "") -> tuple[str, str]:
    """Devolve `(texto, idioma_detectado)`. Import local: ver o topo do módulo."""
    from faster_whisper import WhisperModel

    # `int8` roda em CPU com ~4x menos memória que `float32`, com perda de
    # qualidade irrelevante para fala. `cpu` explícito: sem GPU no VPS.
    w = WhisperModel(modelo, device="cpu", compute_type="int8")
    segmentos, info = w.transcribe(io.BytesIO(audio), language=idioma or None,
                                   vad_filter=True)
    # `vad_filter` corta silêncio — numa entrevista com pausas longas, isso é a
    # diferença entre minutos e dezenas de minutos de processamento.
    #
    # ⚠️ O gerador do faster-whisper é de uma passada só: materializar ANTES de
    # usar duas vezes (agrupar por falante E cair no texto corrido se a
    # diarização falhar). Sem a lista, o segundo uso viria vazio — e a
    # transcrição sairia em branco sem erro nenhum.
    segmentos = list(segmentos)
    idioma_detectado = getattr(info, "language", idioma)

    trechos, aviso = _diarizar(audio, hf_token) if diarizar else (None, None)
    if trechos:
        return _com_falantes(segmentos, trechos), idioma_detectado, None
    # Sem diarização (desligada, sem token, ou falhou): texto corrido em
    # parágrafos — o comportamento da v2.99. Degrada, nunca perde — mas DIZ o
    # motivo quando a diarização foi pedida e não veio.
    return _em_paragrafos(segmentos), idioma_detectado, aviso


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
        texto, _idioma, aviso = _transcrever(storage.ler(b.audio_key),
                                             cfg["modelo"], cfg["idioma"],
                                             diarizar=cfg["diarizar"],
                                             hf_token=cfg["hf_token"])
        b.processamento_s = int(time.monotonic() - inicio)
        b.transcrito_em = datetime.now(timezone.utc)
        if texto:
            # `erro` carrega o AVISO da diarização quando ela foi pedida e não
            # veio: o bloco está pronto (tem texto), mas a tela precisa dizer
            # por que não há rótulo de falante — senão o RH não sabe se está
            # desligada, sem token ou quebrada.
            b.texto, b.status, b.erro = texto, StatusBloco.pronta, aviso
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
        texto, idioma, aviso = _transcrever(audio, cfg["modelo"], cfg["idioma"],
                                            diarizar=cfg["diarizar"],
                                            hf_token=cfg["hf_token"])

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
        # Ver o comentário do bloco: aviso da diarização vai para a TELA.
        g.erro = aviso
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


# ==========================================================================
# DIARIZAÇÃO — "quem falou" (v3.00)
#
# Pedido do Bruno: *"nem que seja, interlocutor 1, 2…"*. E é essa formulação
# que torna o recurso aceitável: a v2.97 recusou diarização porque atribuir fala
# a uma pessoa NOMEADA numa ficha que ela assina é risco jurídico — dizer "o
# candidato afirmou X" quando quem disse foi o entrevistador é grave.
#
# **`Interlocutor 1` não afirma quem é ninguém.** Só marca que a voz mudou. Se
# errar, o pior caso é um rótulo trocado num parágrafo, e quem esteve na conversa
# percebe lendo. É a diferença entre IDENTIFICAR e SEPARAR — e só a segunda está
# sendo feita aqui.
#
# ⚠️ **NUNCA troque `Interlocutor N` pelo nome da pessoa.** No dia em que alguém
# quiser isso, a pergunta é: o que acontece se o rótulo estiver errado numa peça
# que vai para uma reclamatória? Foi essa pergunta que manteve o recurso fora até
# agora.
#
# Custo medido (pyannote 3.1 em CPU): RTF ~1,74 — 10 min de áudio levam ~18 min
# para diarizar. Uma entrevista de 40 min passa de poucos minutos para ~1h10 na
# fila. Roda em segundo plano, e por isso não trava ninguém — mas a transcrição
# fica pronta MAIS TARDE. O Bruno decidiu ligá-la por padrão sabendo disso
# (2026-08-12); é configurável para desligar sem deploy se o tempo incomodar.
# ==========================================================================

ROTULO = "Interlocutor {n}"


def _diarizar(audio: bytes, token: str):
    """Devolve os trechos de fala com o falante, ou `None` se não der.

    `None` (e não exceção) porque **a transcrição não pode se perder por causa
    da diarização**: o texto é o que serve para escrever a justificativa da
    avaliação; saber quem falou é melhoria. Falha aqui degrada para o texto
    corrido, que é o comportamento da v2.99 — nunca para transcrição nenhuma.

    ⚠️ O modelo é GATED no HuggingFace: exige token e aceite de licença. Sem
    token, devolve `None` — e quem chama registra o motivo, para a tela poder
    dizer o que resolve em vez de mostrar um resultado pior sem explicação.
    """
    if not token:
        log.info("Diarização pulada: sem token do HuggingFace configurado.")
        return None, ("Sem o token do Hugging Face, a transcrição sai sem separar "
                      "quem falou. Configure em Configurações → Roteiros de "
                      "entrevista.")
    try:
        import tempfile

        import torch                                   # noqa: F401  (pyannote exige)
        from pyannote.audio import Pipeline

        pipe = Pipeline.from_pretrained(
            "pyannote/speaker-diarization-3.1", use_auth_token=token)
        # O pyannote lê de ARQUIVO, não de bytes. `delete=False` + remoção
        # explícita: no Linux o handle aberto de um NamedTemporaryFile não é
        # relido por outra biblioteca de forma confiável.
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            tmp.write(audio)
            caminho = tmp.name
        try:
            anotacao = pipe(caminho)
        finally:
            import os as _os
            try:
                _os.unlink(caminho)
            except OSError:
                log.warning("Temporário da diarização não removido: %s", caminho)

        trechos = [(t.start, t.end, rotulo)
                   for t, _, rotulo in anotacao.itertracks(yield_label=True)]
        log.info("Diarização: %d trecho(s), %d voz(es).",
                 len(trechos), len({r for _, _, r in trechos}))
        return trechos, None
    except Exception:                                   # noqa: BLE001
        # Sem token válido, sem licença aceita, modelo indisponível, memória…
        # Todos degradam igual: texto sem rótulo, que é melhor que nada.
        log.exception("Diarização falhou — a transcrição segue sem rótulo.")
        # ⚠️ O motivo VOLTA para quem chamou, e daí para a TELA. Só registrar no
        # log deixaria o RH vendo texto sem rótulo sem saber se a diarização
        # está desligada, sem token ou quebrada — e silêncio se confunde com
        # "estava tudo certo" (v2.66/v2.69). O tipo do erro basta para orientar;
        # o texto cru pode carregar caminho de arquivo.
        return None, (f"Não foi possível separar quem falou "
                      f"({type(sys.exc_info()[1]).__name__}). A transcrição está "
                      "completa, só sem os rótulos. Confira o token do Hugging "
                      "Face e se a licença do modelo foi aceita.")


def _falante_de(inicio: float | None, fim: float | None, trechos) -> str | None:
    """Quem estava falando neste segmento — o falante com MAIOR sobreposição.

    Pelo maior tempo em comum, e não pelo instante inicial: o Whisper e o
    pyannote cortam em pontos diferentes, então um segmento de fala costuma
    começar poucos décimos antes de o falante "oficialmente" assumir. Casar pelo
    início daria o falante ANTERIOR em toda troca de turno — justamente onde o
    rótulo importa.
    """
    if inicio is None or fim is None or not trechos:
        return None
    melhor, maior = None, 0.0
    for t_ini, t_fim, rotulo in trechos:
        comum = min(fim, t_fim) - max(inicio, t_ini)
        if comum > maior:
            melhor, maior = rotulo, comum
    return melhor


def _com_falantes(segmentos, trechos) -> str:
    """Texto agrupado por FALANTE, com rótulo neutro.

    Agrupa segmentos consecutivos do mesmo falante num parágrafo só: um rótulo
    por frase deixaria a leitura pior do que o bloco corrido que veio consertar.

    A numeração segue a ORDEM DE ENTRADA na conversa (quem fala primeiro é o 1),
    e não o rótulo interno do pyannote (`SPEAKER_00`, `SPEAKER_02`…), que é
    arbitrário e pularia números — "Interlocutor 3" numa conversa de duas pessoas
    faria o RH procurar um terceiro que não existe.
    """
    ordem: dict[str, int] = {}
    blocos: list[tuple[str, list[str]]] = []

    for s in segmentos:
        texto = (s.text or "").strip()
        if not texto:
            continue
        bruto = _falante_de(getattr(s, "start", None), getattr(s, "end", None), trechos)
        if bruto is not None and bruto not in ordem:
            ordem[bruto] = len(ordem) + 1
        rotulo = ROTULO.format(n=ordem[bruto]) if bruto is not None else ""
        if blocos and blocos[-1][0] == rotulo:
            blocos[-1][1].append(texto)
        else:
            blocos.append((rotulo, [texto]))

    partes = []
    for rotulo, falas in blocos:
        corpo = " ".join(falas).strip()
        if not corpo:
            continue
        partes.append(f"[{rotulo}]\n{corpo}" if rotulo else corpo)
    return "\n\n".join(partes).strip()
