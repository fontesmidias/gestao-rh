"""Acesso ao MinIO. Bucket criado na primeira utilização.

Toda operação é CRONOMETRADA e a que demora demais vira aviso no log (v2.41,
pedido do Bruno por "investigações verdadeiras"): quando alguém diz que "o
sistema está lento", a resposta precisa ser um número e um nome de arquivo, e
não uma impressão. O limiar é alto de propósito — registrar o que é normal
encheria o log e esconderia o que não é.
"""

import io
import logging
import time
from functools import lru_cache

from minio import Minio

from app.core.config import get_settings

log = logging.getLogger("storage")

# Acima disto, a operação vira linha no log. 2s é muito para um objeto que
# quase sempre responde em dezenas de milissegundos — e é o tempo a partir do
# qual a pessoa do outro lado já percebeu a demora.
LENTO_MS = 2000


def _cronometrar(operacao: str, key: str, inicio: float, tamanho: int | None = None) -> None:
    ms = round((time.perf_counter() - inicio) * 1000)
    if ms >= LENTO_MS:
        log.warning("storage LENTO op=%s key=%s ms=%s bytes=%s",
                    operacao, key, ms, tamanho if tamanho is not None else "-")


@lru_cache
def _cliente() -> Minio:
    s = get_settings()
    cliente = Minio(
        s.minio_endpoint,
        access_key=s.minio_access_key,
        secret_key=s.minio_secret_key,
        secure=s.minio_secure,
    )
    if not cliente.bucket_exists(s.minio_bucket):
        cliente.make_bucket(s.minio_bucket)
    return cliente


def salvar(key: str, dados: bytes, content_type: str = "application/octet-stream") -> None:
    inicio = time.perf_counter()
    try:
        _cliente().put_object(
            get_settings().minio_bucket, key, io.BytesIO(dados), len(dados),
            content_type=content_type)
    except Exception:
        # O que falha ao GRAVAR é o que a pessoa acabou de enviar: sem esta
        # linha, o arquivo some e o log não sabe de nada.
        log.exception("storage FALHOU op=salvar key=%s bytes=%s", key, len(dados))
        raise
    finally:
        _cronometrar("salvar", key, inicio, len(dados))


def ler(key: str) -> bytes:
    inicio = time.perf_counter()
    resp = _cliente().get_object(get_settings().minio_bucket, key)
    try:
        dados = resp.read()
        _cronometrar("ler", key, inicio, len(dados))
        return dados
    finally:
        resp.close()
        resp.release_conn()


def remover(key: str) -> None:
    _cliente().remove_object(get_settings().minio_bucket, key)


def listar(prefixo: str) -> list[str]:
    """Keys de todos os objetos sob o prefixo (ex.: os originais de um slot)."""
    return [obj.object_name for obj in
            _cliente().list_objects(get_settings().minio_bucket,
                                    prefix=prefixo, recursive=True)]


def listar_detalhado(prefixo: str) -> list[tuple[str, int]]:
    """(key, tamanho em bytes) de cada objeto sob o prefixo — para estimar o
    tamanho de um lote antes de montá-lo, sem baixar nada."""
    return [(obj.object_name, obj.size or 0) for obj in
            _cliente().list_objects(get_settings().minio_bucket,
                                    prefix=prefixo, recursive=True)]


def stat(key: str) -> int | None:
    """Tamanho do objeto em bytes, ou None se não existir — verificação barata
    de existência (usada para saber o que falta ANTES de montar um ZIP)."""
    from minio.error import S3Error
    try:
        return _cliente().stat_object(get_settings().minio_bucket, key).size
    except S3Error:
        return None


def abrir_em_blocos(key: str, tamanho_bloco: int = 65536):
    """Gera os bytes do objeto em blocos, sem materializá-lo inteiro em RAM
    (para montar ZIPs grandes em streaming). Fecha a conexão no finally mesmo
    que o consumidor aborte no meio."""
    resp = _cliente().get_object(get_settings().minio_bucket, key)
    try:
        yield from resp.stream(tamanho_bloco)
    finally:
        resp.close()
        resp.release_conn()
