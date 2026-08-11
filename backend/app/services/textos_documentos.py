"""Trechos dos documentos que o RH edita pelo painel (v2.90).

Segunda parte do pedido do Bruno: *"tornar os demais documentos editáveis,
conforme o caso"* — com a ressalva que ele mesmo cravou: *"os que já foram
assinados, obviamente que não"*.

O que este arquivo torna editável, e o que deliberadamente NÃO torna
-------------------------------------------------------------------
**Editável**: os blocos de TEXTO DE NEGÓCIO — a lista de direitos do
trabalhador, as cláusulas do acordo de confidencialidade e os ciclos de
pagamento do VT/VA por regime. São textos que mudam por decisão da empresa ou
por mudança de norma, e hoje exigiriam deploy.

**Não editável**: o LAYOUT. Formulário oficial tem campos posicionados, tabelas
e loops (`ficha_cadastro` tem 49 chamadas de campo); virá-lo texto destruiria o
papel. Decisão do Bruno para os 12 documentos que não são texto corrido: *"só a
data e os dados; o layout fica"*.

Três garantias que sustentam isso
---------------------------------
1. **Documento ASSINADO não muda.** O `hash_sha256` do ato é calculado sobre o
   PDF (`api/assinaturas.py`) e o arquivo fica gravado no MinIO; quem já
   assinou carrega a via dele, com o texto que leu. Editar aqui muda o que
   SERÁ gerado daqui em diante — nunca o que já foi assinado. Isso não é
   opcional: é o que faz o `/verificar` continuar batendo.
2. **Vazio = padrão de fábrica.** Sem registro, com texto em branco ou com erro
   de leitura, vale a constante do código. Documento nenhum deixa de sair
   porque alguém apagou o conteúdo — a mesma regra dos templates de e-mail
   (v2.06).
3. **A fonte continua ÚNICA.** `documentos_texto.py` (o corpo que o RH copia
   para um modelo) importa das MESMAS constantes que o gerador do PDF usa.
   Passar a ler daqui mantém isso: editar o texto muda os dois lados juntos,
   como já acontece hoje. Duplicar faria a amostra divergir do documento
   oficial — o defeito que a v2.19 pagou com 6% do VT e 8% do FGTS errados.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.services.config_dinamica import gravar_config, ler_config

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class BlocoTexto:
    chave: str
    rotulo: str
    onde: str          # em que documento(s) este texto aparece
    ajuda: str
    # Uma linha por item. É a forma que os geradores consomem, e é a forma que
    # o RH entende: cada linha vira uma alínea/parágrafo do documento.
    por_linha: bool = True


BLOCOS: tuple[BlocoTexto, ...] = (
    BlocoTexto(
        "texto_direitos_trabalhador", "Direitos do trabalhador",
        "Informações ao Trabalhador (INFRAERO) e fichas de integração",
        "Uma alínea por linha. É a lista que a pessoa lê e assina — confira os "
        "percentuais (VT 6%, FGTS 8%) e o prazo de pagamento antes de salvar.",
    ),
    BlocoTexto(
        "texto_ciclo_vt_efetivo", "Ciclo de pagamento do VT — efetivo",
        "Informativo de Integração — Efetivo",
        "Como e quando o vale-transporte é pago a quem é efetivo. Hoje: "
        "apuração do dia 1 ao dia 30.",
        por_linha=False,
    ),
    BlocoTexto(
        "texto_ciclo_vt_intermitente", "Ciclo de pagamento do VT — intermitente",
        "Informativo de Integração — Intermitente",
        "Como e quando o vale-transporte é pago a quem é intermitente. Hoje: "
        "semanalmente, até a quarta-feira da semana seguinte.",
        por_linha=False,
    ),
    BlocoTexto(
        "texto_ciclo_va_efetivo", "Ciclo do vale-alimentação — efetivo",
        "Informativo de Integração — Efetivo",
        "Como e quando o vale-alimentação é pago a quem é efetivo.",
        por_linha=False,
    ),
    BlocoTexto(
        "texto_ciclo_va_intermitente", "Ciclo do vale-alimentação — intermitente",
        "Informativo de Integração — Intermitente",
        "Como e quando o vale-alimentação é pago a quem é intermitente.",
        por_linha=False,
    ),
)

POR_CHAVE: dict[str, BlocoTexto] = {b.chave: b for b in BLOCOS}


def _padrao(chave: str) -> str:
    """Texto de fábrica, lido das constantes que os geradores já usam.

    Import tardio de propósito: `fichas` importa muito (fpdf, modelos), e este
    módulo é consumido pela própria `fichas` — importar no topo daria ciclo.
    """
    from app.services import fichas

    if chave == "texto_direitos_trabalhador":
        return "\n".join(fichas.DIREITOS_TRABALHADOR)
    if chave == "texto_ciclo_vt_efetivo":
        return fichas._CICLO_VT["efetivo"]
    if chave == "texto_ciclo_vt_intermitente":
        return fichas._CICLO_VT["intermitente"]
    if chave == "texto_ciclo_va_efetivo":
        return fichas._CICLO_VA["efetivo"]
    if chave == "texto_ciclo_va_intermitente":
        return fichas._CICLO_VA["intermitente"]
    raise KeyError(f"bloco_desconhecido: {chave}")


def texto(db: Session | None, chave: str) -> str:
    """O texto em vigor: o do RH, se houver; senão o de fábrica.

    NUNCA levanta por causa do banco. Documento é papel que a pessoa assina —
    ele não pode deixar de sair porque a consulta de configuração falhou. A
    mesma regra do `avisar()` e do `registrar_eventos()`.
    """
    if db is None:
        return _padrao(chave)
    try:
        salvo = (ler_config(db, (chave,)).get(chave) or "").strip()
    except Exception:
        log.exception("Falha ao ler o texto %s; usando o padrão de fábrica", chave)
        return _padrao(chave)
    return salvo or _padrao(chave)


def linhas(db: Session | None, chave: str) -> tuple[str, ...]:
    """O mesmo texto, quebrado por linha — a forma que os geradores consomem."""
    return tuple(l.strip() for l in texto(db, chave).split("\n") if l.strip())


def listar(db: Session) -> list[dict]:
    """Catálogo para a tela: o texto em vigor e se ele foi personalizado."""
    salvos = ler_config(db, tuple(b.chave for b in BLOCOS))
    itens = []
    for b in BLOCOS:
        proprio = (salvos.get(b.chave) or "").strip()
        itens.append({
            "chave": b.chave, "rotulo": b.rotulo, "onde": b.onde,
            "ajuda": b.ajuda, "por_linha": b.por_linha,
            "texto": proprio or _padrao(b.chave),
            "padrao": _padrao(b.chave),
            "personalizado": bool(proprio),
        })
    return itens


def salvar(db: Session, chave: str, novo: str | None) -> dict:
    """Grava o texto do RH. Vazio VOLTA ao padrão — não apaga o documento.

    Vazio precisa ser valor válido, senão não há como desfazer o que se
    configurou (a lição da v2.68). Por isso "limpar" é o caminho de volta, e
    não um estado de documento sem texto.
    """
    if chave not in POR_CHAVE:
        raise KeyError(chave)
    gravar_config(db, {chave: (novo or "").strip()})
    return {"chave": chave, "texto": texto(db, chave),
            "personalizado": bool((novo or "").strip())}
