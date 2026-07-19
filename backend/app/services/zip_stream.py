"""Montagem de um ZIP em STREAMING de verdade, sobre a stdlib (sem dependência
nova). Emite os bytes conforme cada entrada é escrita, então o pico de memória
é ~1 arquivo por vez — nunca o ZIP inteiro nem todos os PDFs juntos.

Uso: passe uma lista de entradas já resolvidas (o caminho no ZIP + um provedor
de bytes preguiçoso), mais os bytes de arquivos "em memória" (a planilha, o
relatório). O provedor de bytes é chamado só quando aquela entrada é gravada.
"""

import zipfile
from typing import Callable, Iterable, Iterator


class _BufferEmissor:
    """Arquivo-like que acumula o que o ZipFile escreve e o entrega em blocos.
    O ZipFile escreve nele; nós drenamos o buffer entre as entradas."""

    def __init__(self) -> None:
        self._buf = bytearray()

    def write(self, dados: bytes) -> int:
        self._buf.extend(dados)
        return len(dados)

    def flush(self) -> None:  # ZipFile chama flush; nada a fazer
        pass

    def drenar(self) -> bytes:
        dados = bytes(self._buf)
        self._buf.clear()
        return dados


# Uma entrada de arquivo grande: (caminho_no_zip, provedor) onde provedor()
# devolve um iterável de blocos de bytes (ex.: storage.abrir_em_blocos(key)).
EntradaStream = tuple[str, Callable[[], Iterable[bytes]]]
# Uma entrada pequena já em memória: (caminho_no_zip, bytes)
EntradaMemoria = tuple[str, bytes]


def gerar_zip(entradas_stream: list[EntradaStream],
              entradas_memoria: list[EntradaMemoria]) -> Iterator[bytes]:
    """Gera os bytes do ZIP. ZIP_STORED (sem compressão): PDFs/imagens já vêm
    comprimidos, então comprimir de novo só gasta CPU e prende o streaming."""
    emissor = _BufferEmissor()
    with zipfile.ZipFile(emissor, "w", zipfile.ZIP_STORED) as zf:
        for caminho, provedor in entradas_stream:
            # abre a entrada e escreve bloco a bloco, drenando o buffer entre eles
            with zf.open(caminho, "w") as destino:
                for bloco in provedor():
                    destino.write(bloco)
                    saida = emissor.drenar()
                    if saida:
                        yield saida
            saida = emissor.drenar()
            if saida:
                yield saida
        for caminho, dados in entradas_memoria:
            with zf.open(caminho, "w") as destino:
                destino.write(dados)
            saida = emissor.drenar()
            if saida:
                yield saida
    # o close() do ZipFile escreve o índice central — drenar o resto
    saida = emissor.drenar()
    if saida:
        yield saida
