"""Acesso ao MinIO. Bucket criado na primeira utilização."""

import io
from functools import lru_cache

from minio import Minio

from app.core.config import get_settings


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
    _cliente().put_object(
        get_settings().minio_bucket, key, io.BytesIO(dados), len(dados), content_type=content_type
    )


def ler(key: str) -> bytes:
    resp = _cliente().get_object(get_settings().minio_bucket, key)
    try:
        return resp.read()
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
