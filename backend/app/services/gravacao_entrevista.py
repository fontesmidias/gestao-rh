"""Regras da gravação e transcrição de entrevista (v2.97).

Desenho completo em `docs/planejamento/14-transcricao-de-entrevistas.md`.
Aqui ficam as transições de estado e as travas que as sustentam.
"""

import logging
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.entrevista import Entrevista
from app.models.gravacao_entrevista import GravacaoEntrevista, StatusGravacao
from app.services import storage

log = logging.getLogger(__name__)

# Áudio de 40 min em Opus (o que o `MediaRecorder` do navegador entrega) dá
# ~20 MB. O teto é generoso porque o custo de recusar é alto: a entrevista já
# aconteceu, e o áudio não se refaz.
AUDIO_MAX_BYTES = 200 * 1024 * 1024
EXTENSOES_AUDIO = frozenset({"webm", "ogg", "oga", "opus", "mp3", "m4a", "wav", "mp4"})

# Modelo padrão do faster-whisper. `small` dá conta de português com áudio de
# sala e roda em CPU; `medium` é melhor e ~3x mais lento. Configurável para não
# exigir deploy quando o Bruno quiser trocar.
MODELO_PADRAO = "small"


def obter_ou_criar(db: Session, entrevista: Entrevista) -> GravacaoEntrevista:
    """A gravação de uma entrevista, criando o registro `nao_perguntado` se ainda
    não existe. Nasce nesse estado de propósito: ele diz *"ninguém foi
    consultado"*, que é diferente de *"não quis"* — e a diferença é o que prova
    que a pessoa foi perguntada (v2.34)."""
    g = db.scalar(select(GravacaoEntrevista).where(
        GravacaoEntrevista.entrevista_id == entrevista.id))
    if g is None:
        g = GravacaoEntrevista(entrevista_id=entrevista.id)
        db.add(g)
        db.flush()
    return g


class GravacaoRecusada(Exception):
    """A transição pedida não é permitida no estado atual."""

    def __init__(self, erro: str, detalhe: str = ""):
        self.erro = erro
        self.detalhe = detalhe
        super().__init__(detalhe or erro)


def registrar_consentimento(db: Session, g: GravacaoEntrevista, consentiu: bool,
                            registrado_por: str) -> GravacaoEntrevista:
    """Registra o que a pessoa respondeu quando foi perguntada.

    **Só se muda a resposta enquanto não há áudio.** Depois de gravado, trocar
    para "recusado" apagaria a base do que já foi coletado — o caminho certo aí
    é EXCLUIR a gravação (`excluir`), que remove o áudio de verdade. Aceitar a
    troca sem apagar deixaria um áudio existindo sob um registro que diz que a
    pessoa não autorizou, que é a pior das duas mentiras possíveis.
    """
    if g.audio_key and not consentiu:
        raise GravacaoRecusada(
            "audio_ja_existe",
            "Já existe áudio gravado. Para retirar o consentimento, exclua a "
            "gravação — assim o áudio é apagado de verdade.")

    g.status = StatusGravacao.consentido if consentiu else StatusGravacao.recusado
    g.consentimento_em = datetime.now(timezone.utc)
    g.consentimento_por = registrado_por
    return g


def marcar_para_transcrever(db: Session, g: GravacaoEntrevista, *, key: str,
                            bytes_: int, tipo: str,
                            duracao_s: int | None) -> GravacaoEntrevista:
    """Áudio guardado: entra na fila.

    ⚠️ **Sem consentimento, recusa.** A checagem vive aqui e não só na rota
    porque esta é a última porta antes de o áudio virar dado do sistema — e
    "as rotas não deixam" não é garantia (v2.66): migration, acerto no banco e
    teste destrutivo não passam por rota.
    """
    if not g.pode_gravar:
        raise GravacaoRecusada(
            "sem_consentimento",
            "A pessoa não autorizou a gravação desta entrevista.")
    g.audio_key, g.audio_bytes, g.audio_tipo = key, bytes_, tipo
    g.duracao_s = duracao_s
    g.gravado_em = datetime.now(timezone.utc)
    g.status = StatusGravacao.aguardando
    g.erro = None
    return g


def excluir(db: Session, g: GravacaoEntrevista) -> None:
    """Apaga o áudio E a transcrição, e devolve ao estado de recusa.

    O registro PERMANECE (com `recusado`): apagar a linha apagaria a prova de
    que a pessoa foi consultada, que é justamente o que ela existe para provar.
    O áudio, esse sai do storage de verdade — é dado biométrico, e "some da tela"
    não é o mesmo que "foi apagado" (a lição do verso do RG que ficava no MinIO,
    v2.35).
    """
    if g.audio_key:
        try:
            storage.remover(g.audio_key)
        except Exception:                       # noqa: BLE001
            # Não trava a operação: o expurgo varre por prefixo depois. Mas
            # REGISTRA — falha de remoção de dado pessoal não pode ser silêncio.
            log.exception("Não foi possível remover o áudio %s", g.audio_key)
    g.audio_key = g.audio_bytes = g.audio_tipo = None
    g.duracao_s = g.gravado_em = None
    g.texto = g.idioma = g.modelo = g.transcrito_em = None
    g.processamento_s = None
    g.erro = None
    g.status = StatusGravacao.recusado
    g.consentimento_em = datetime.now(timezone.utc)


ROTULOS = {
    StatusGravacao.nao_perguntado: "Ainda não perguntado",
    StatusGravacao.consentido: "Autorizado — pode gravar",
    StatusGravacao.recusado: "A pessoa não autorizou",
    StatusGravacao.aguardando: "Na fila para transcrever",
    StatusGravacao.processando: "Transcrevendo…",
    StatusGravacao.pronta: "Transcrição pronta",
    StatusGravacao.falhou: "Não foi possível transcrever",
    StatusGravacao.audio_inaudivel: "Áudio sem fala reconhecível",
}


def resumo(g: GravacaoEntrevista | None) -> dict:
    """O que a tela mostra. Gravação inexistente é `nao_perguntado`, nunca
    `null`: null faria a tela sumir com o bloco e ninguém seria perguntado."""
    if g is None:
        return {"status": StatusGravacao.nao_perguntado.value,
                "rotulo": ROTULOS[StatusGravacao.nao_perguntado],
                "tem_audio": False, "tem_texto": False}
    return {
        "id": str(g.id), "status": g.status.value,
        "rotulo": ROTULOS.get(g.status, g.status.value),
        "tem_audio": bool(g.audio_key), "tem_texto": bool(g.texto),
        "duracao_s": g.duracao_s, "audio_bytes": g.audio_bytes,
        "consentimento_em": g.consentimento_em,
        "consentimento_por": g.consentimento_por,
        "gravado_em": g.gravado_em, "transcrito_em": g.transcrito_em,
        "erro": g.erro, "modelo": g.modelo,
    }
