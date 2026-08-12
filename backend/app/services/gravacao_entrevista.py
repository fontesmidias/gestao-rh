"""Regras da gravação e transcrição de entrevista (v2.97).

Desenho completo em `docs/planejamento/14-transcricao-de-entrevistas.md`.
Aqui ficam as transições de estado e as travas que as sustentam.
"""

import logging
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.entrevista import Entrevista
from app.models.bloco_gravacao import BlocoGravacao, StatusBloco
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

# --- Configuração no painel (v2.98) ---------------------------------------
#
# Padrões escolhidos pelo Bruno. Todos editáveis sem deploy: sala com internet
# ruim pede bloco menor, e a retenção do áudio é decisão de política, não de
# código.
BLOCO_MIN_PADRAO = 10          # minutos por bloco de áudio
RETENCAO_DIAS_PADRAO = 120     # o áudio some depois disso; o TEXTO permanece


def config(db: Session) -> dict:
    """Bloco (min) e retenção (dias). Valor inválido cai no padrão em vez de
    quebrar: config ruim não pode impedir uma entrevista de ser gravada."""
    from app.services.config_dinamica import ler_config
    c = ler_config(db, ("transcricao_bloco_min", "transcricao_retencao_dias"))

    def _int(chave: str, padrao: int, minimo: int, maximo: int) -> int:
        try:
            v = int(str(c.get(chave) or "").strip())
        except (TypeError, ValueError):
            return padrao
        return v if minimo <= v <= maximo else padrao

    return {
        # Teto de 60 min por bloco: acima disso o upload de um bloco só já
        # arrisca o timeout que a divisão veio evitar.
        "bloco_min": _int("transcricao_bloco_min", BLOCO_MIN_PADRAO, 1, 60),
        # 0 = nunca expurgar (mesma convenção do log, v2.29). ⚠️ Trocar
        # `<= 0` por `is not None` transformaria "guardar para sempre" em
        # "apagar tudo hoje", em silêncio.
        "retencao_dias": _int("transcricao_retencao_dias", RETENCAO_DIAS_PADRAO, 0, 3650),
    }


def nome_arquivo(pessoa: str, quando, parte: int | None = None) -> str:
    """`ENTREVISTA 12-08-2026 - KATIA POLIANE` (+ ` - PARTE 2`).

    O mesmo padrão do dossiê (`DOCS ADM - NOME`, v2.98): caixa alta, sem acento,
    com a DATA — pedido do Bruno. A data entra porque a mesma pessoa pode ser
    entrevistada mais de uma vez, e dois arquivos com nome idêntico na pasta de
    Downloads viram `(1)`, `(2)` — que não dizem qual é qual.

    ASCII por necessidade: o header `Content-Disposition` não carrega acento com
    segurança em todos os clientes.
    """
    import unicodedata
    limpo = unicodedata.normalize("NFKD", pessoa or "").encode("ascii", "ignore").decode()
    for proibido in r'\/:*?"<>|':
        limpo = limpo.replace(proibido, " ")
    limpo = " ".join(limpo.split()).upper() or "SEM NOME"
    data = quando.strftime("%d-%m-%Y") if quando else "SEM DATA"
    sufixo = f" - PARTE {parte}" if parte else ""
    return f"ENTREVISTA {data} - {limpo}{sufixo}"


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
    # Apaga o áudio principal E o de cada bloco. ⚠️ Esquecer os blocos deixaria
    # a entrevista inteira no MinIO com a tela dizendo que foi apagada — o pior
    # desfecho possível para dado biométrico (v2.35).
    for key in [g.audio_key, *[b.audio_key for b in blocos_de(db, g)]]:
        if not key:
            continue
        try:
            storage.remover(key)
        except Exception:                       # noqa: BLE001
            # Não trava a operação: o expurgo varre por prefixo depois. Mas
            # REGISTRA — falha de remoção de dado pessoal não pode ser silêncio.
            log.exception("Não foi possível remover o áudio %s", key)
    for b in blocos_de(db, g):
        db.delete(b)
    g.audio_key = g.audio_bytes = g.audio_tipo = None
    g.duracao_s = g.gravado_em = None
    g.texto = g.idioma = g.modelo = g.transcrito_em = None
    g.processamento_s = None
    g.erro = None
    g.status = StatusGravacao.recusado
    g.consentimento_em = datetime.now(timezone.utc)


# ==========================================================================
# BLOCOS (v2.98)
#
# A entrevista real dura 40–90 min e é gravada em blocos de ~10 min. Ver o
# docstring de `models/bloco_gravacao.py` para o porquê.
# ==========================================================================


def proximo_indice(db: Session, g: GravacaoEntrevista) -> int:
    """O índice do próximo bloco. Baseado no MAIOR índice existente, não na
    contagem: se o bloco 2 for reenviado e o 3 já existir, contar daria 3 de
    novo e o `UniqueConstraint` recusaria."""
    maior = db.scalar(select(func.max(BlocoGravacao.indice)).where(
        BlocoGravacao.gravacao_id == g.id))
    return (maior or 0) + 1


def blocos_de(db: Session, g: GravacaoEntrevista) -> list[BlocoGravacao]:
    """Os blocos NA ORDEM DA CONVERSA.

    ⚠️ Ordena por `indice`, nunca pela listagem do storage: ela é lexicográfica
    e põe `bloco-10` antes de `bloco-2`, o que colocaria o meio da entrevista no
    lugar errado — e ninguém perceberia lendo o texto (v2.35).
    """
    return list(db.scalars(select(BlocoGravacao)
                           .where(BlocoGravacao.gravacao_id == g.id)
                           .order_by(BlocoGravacao.indice)))


def registrar_bloco(db: Session, g: GravacaoEntrevista, *, indice: int, key: str,
                    bytes_: int, tipo: str, duracao_s: int | None,
                    inicio_s: int | None) -> BlocoGravacao:
    """Guarda um bloco recém-enviado.

    ⚠️ **Sem consentimento, recusa** — a checagem vive aqui e não só na rota
    porque esta é a última porta antes de o áudio virar dado do sistema (v2.66).

    Reenviar o MESMO índice substitui o anterior (o áudio velho sai do storage),
    em vez de duplicar: é o que permite reenviar um bloco que falhou no upload
    sem criar um bloco fantasma na ordem.
    """
    if not g.pode_gravar:
        raise GravacaoRecusada(
            "sem_consentimento",
            "A pessoa não autorizou a gravação desta entrevista.")

    b = db.scalar(select(BlocoGravacao).where(
        BlocoGravacao.gravacao_id == g.id, BlocoGravacao.indice == indice))
    if b is None:
        b = BlocoGravacao(gravacao_id=g.id, indice=indice)
        db.add(b)
    elif b.audio_key and b.audio_key != key:
        try:
            storage.remover(b.audio_key)
        except Exception:                       # noqa: BLE001
            log.exception("Bloco anterior não removido: %s", b.audio_key)

    b.audio_key, b.audio_bytes, b.audio_tipo = key, bytes_, tipo
    b.duracao_s, b.inicio_s = duracao_s, inicio_s
    b.status = StatusBloco.aguardando
    b.texto = b.erro = None
    db.flush()

    # A gravação inteira volta a "aguardando": chegou material novo para
    # transcrever, mesmo que ela já estivesse `pronta` de blocos anteriores.
    g.status = StatusGravacao.aguardando
    g.gravado_em = g.gravado_em or datetime.now(timezone.utc)
    g.erro = None
    return b


def consolidar(db: Session, g: GravacaoEntrevista) -> GravacaoEntrevista:
    """Junta o texto dos blocos e decide o estado da gravação inteira.

    As regras de desfecho, e por que cada uma:

    - **Um bloco ainda rodando ⇒ a gravação continua `processando`.** Marcar
      `pronta` com metade da conversa faria o RH ler um texto truncado achando
      que é tudo.
    - **Todos inaudíveis ⇒ `audio_inaudivel`.** Um bloco mudo no meio (a pessoa
      lendo um documento) é normal e NÃO contamina o resto.
    - **Algum falhou, mas há texto ⇒ `pronta`, com o aviso de qual bloco falta.**
      Recusar tudo por causa de 10 minutos perdidos jogaria fora os outros 80 —
      mas apresentar como completo esconderia o buraco (a lição do dossiê,
      v2.93).
    """
    blocos = blocos_de(db, g)
    if not blocos:
        return g

    if any(b.status in (StatusBloco.aguardando, StatusBloco.processando) for b in blocos):
        g.status = StatusGravacao.processando
        return g

    com_texto = [b for b in blocos if (b.texto or "").strip()]
    falhos = [b for b in blocos if b.status == StatusBloco.falhou]

    g.texto = "\n\n".join((b.texto or "").strip() for b in com_texto) or None
    g.duracao_s = sum(b.duracao_s or 0 for b in blocos) or g.duracao_s
    g.transcrito_em = datetime.now(timezone.utc)
    g.processamento_s = sum(b.processamento_s or 0 for b in blocos) or None

    if not com_texto:
        g.status = (StatusGravacao.falhou if falhos else StatusGravacao.audio_inaudivel)
        g.erro = (f"{len(falhos)} bloco(s) falharam." if falhos
                  else "O áudio não tem fala reconhecível. Confira se o microfone "
                       "estava captando.")
        return g

    g.status = StatusGravacao.pronta
    # Dizer QUAIS blocos faltam, não só que faltam: o RH consegue reouvir
    # justamente aquele trecho.
    g.erro = (f"Transcrição parcial: os blocos {', '.join(str(b.indice) for b in falhos)} "
              "não puderam ser transcritos." if falhos else None)
    return g


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


def _bloco_dump(b) -> dict:
    return {"id": str(b.id), "indice": b.indice, "status": b.status.value,
            "duracao_s": b.duracao_s, "inicio_s": b.inicio_s,
            "tem_texto": bool(b.texto), "erro": b.erro,
            "bytes": b.audio_bytes}


def resumo(g: GravacaoEntrevista | None, db: Session | None = None) -> dict:
    """O que a tela mostra. Gravação inexistente é `nao_perguntado`, nunca
    `null`: null faria a tela sumir com o bloco e ninguém seria perguntado."""
    if g is None:
        return {"status": StatusGravacao.nao_perguntado.value,
                "rotulo": ROTULOS[StatusGravacao.nao_perguntado],
                "tem_audio": False, "tem_texto": False}
    blocos = blocos_de(db, g) if db is not None else []
    return {
        "id": str(g.id), "status": g.status.value,
        # A tela lista os blocos para baixar um a um e para mostrar QUAL falhou.
        "blocos": [_bloco_dump(b) for b in blocos],
        "duracao_total_s": sum(b.duracao_s or 0 for b in blocos) or g.duracao_s,
        "rotulo": ROTULOS.get(g.status, g.status.value),
        "tem_audio": bool(g.audio_key), "tem_texto": bool(g.texto),
        "duracao_s": g.duracao_s, "audio_bytes": g.audio_bytes,
        "consentimento_em": g.consentimento_em,
        "consentimento_por": g.consentimento_por,
        "gravado_em": g.gravado_em, "transcrito_em": g.transcrito_em,
        "erro": g.erro, "modelo": g.modelo,
    }
