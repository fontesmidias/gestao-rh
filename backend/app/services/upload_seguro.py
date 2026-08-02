"""Guarda-corpo dos uploads: tamanho, extensão e descarte do spool.

Nasceu de um achado durante a v2.54: as duas rotas de upload do creche
(`creche_publico.py`) gravavam o arquivo no MinIO **sem nenhuma proteção** —
sem teto de tamanho, aceitando qualquer extensão (`ext or "bin"`) e, o pior,
sem `await arquivo.close()`. E são rotas **públicas**.

Por que o `close()` importa mais do que parece: o Starlette faz *spool* em
disco de qualquer upload acima de ~1 MB. Sem fechar, o arquivo temporário fica
no container — e o que sobrava ali era **certidão de nascimento de criança**.
Os uploads que fazem certo (`talentos.py`, `portal.py`) já fechavam no
`finally`; o creche furou a regra da casa.

O teto é **configurável no painel** (Configurações → Sistema), decisão do Bruno
em 2026-08-02: limite chumbado no código exige deploy para ajustar, e quem
opera é quem descobre que 10 MB não bastam para a foto de um celular novo.

Uso:

    conteudo = await ler_upload(db, arquivo, EXTENSOES_DOCUMENTO)
    # levanta HTTPException com detail utilizável pelo front

O `finally` com o `close()` está DENTRO desta função: é o que garante que
nenhum call-site futuro esqueça — foi exatamente o esquecimento que originou
o problema.
"""

from fastapi import HTTPException, UploadFile
from sqlalchemy.orm import Session

# Formatos aceitos por tipo de envio. Listas explícitas, nunca "qualquer coisa":
# `ext or "bin"` aceitava .exe, .svg (que carrega script) e arquivo sem nome.
EXTENSOES_DOCUMENTO = frozenset({
    "pdf", "jpg", "jpeg", "png", "heic", "heif", "webp", "bmp",
})
EXTENSOES_COM_WORD = EXTENSOES_DOCUMENTO | {"doc", "docx", "odt", "rtf"}

# Padrão quando o RH ainda não mexeu na configuração. Igual ao `MAX_BYTES` da
# `normalizacao.py`, que é o limite do fluxo de documentos do candidato — para
# o creche não ser mais restritivo que a admissão sem ninguém ter decidido isso.
CHAVE_TETO_MB = "upload_max_mb"
TETO_MB_PADRAO = 50
# Limites do que o painel aceita: abaixo de 1 MB uma foto comum de celular já
# falharia (e o RH descobriria com o colaborador do outro lado da linha);
# acima de 200 MB o proxy e a memória do container é que barrariam, com um erro
# muito pior de diagnosticar do que este.
TETO_MB_MIN, TETO_MB_MAX = 1, 200


def teto_bytes(db: Session) -> int:
    """Tamanho máximo de upload em bytes, do painel ou do padrão."""
    from app.services.config_dinamica import ler_config

    bruto = ler_config(db, (CHAVE_TETO_MB,)).get(CHAVE_TETO_MB)
    try:
        mb = int(bruto) if bruto else TETO_MB_PADRAO
    except (TypeError, ValueError):
        mb = TETO_MB_PADRAO          # valor sujo no banco não trava o upload
    mb = max(TETO_MB_MIN, min(TETO_MB_MAX, mb))
    return mb * 1024 * 1024


def extensao_de(arquivo: UploadFile) -> str:
    """Extensão em minúsculas, sem ponto. `""` quando não há."""
    nome = arquivo.filename or ""
    if "." not in nome:
        return ""
    return nome.rsplit(".", 1)[-1].lower()[:5]


async def ler_upload(db: Session, arquivo: UploadFile,
                     extensoes: frozenset[str] = EXTENSOES_DOCUMENTO) -> bytes:
    """Lê o upload conferindo tamanho e extensão, e SEMPRE descarta o spool.

    Levanta `HTTPException` com `detail` que o front sabe traduzir:
    `arquivo_vazio`, `arquivo_grande_demais` (com o limite) ou
    `formato_nao_suportado` (com a lista aceita).

    O `close()` no `finally` é o ponto central: mesmo quando a validação
    recusa, o arquivo temporário some. Recusar e deixar o spool no disco seria
    o pior dos dois mundos — sem o dado gravado e com ele esquecido em /tmp.
    """
    limite = teto_bytes(db)
    try:
        conteudo = await arquivo.read()
    finally:
        await arquivo.close()

    if not conteudo:
        raise HTTPException(status_code=422, detail="arquivo_vazio")
    if len(conteudo) > limite:
        raise HTTPException(status_code=413, detail={
            "erro": "arquivo_grande_demais",
            "limite_mb": limite // (1024 * 1024),
            "tamanho_mb": round(len(conteudo) / (1024 * 1024), 1),
        })
    ext = extensao_de(arquivo)
    if ext not in extensoes:
        raise HTTPException(status_code=422, detail={
            "erro": "formato_nao_suportado",
            "extensao": ext or "(sem extensão)",
            "aceitos": sorted(extensoes),
        })
    return conteudo
