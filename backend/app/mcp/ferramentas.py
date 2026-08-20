"""As 5 ferramentas do assistente, no servidor remoto.

**As descrições (docstrings) são o ativo aqui.** É o que o modelo lê para
decidir se usa a ferramenta — descrição fraca faz a ferramenta errada ser
chamada, e o sintoma aparece como "o assistente não entendeu", longe da causa.
Por isso elas são **idênticas** às do servidor stdio (`mcp/portal_rh_mcp/
servidor.py`), e um teste compara as duas: se divergirem, o remoto e o local
passam a responder diferente à mesma pergunta.

O que muda em relação ao stdio: lá as ferramentas falam HTTP com a API; aqui
rodam no mesmo processo e chamam a função de rota direto. O ganho não é
performance — é que **a identidade da pessoa não precisa dar um segundo salto**,
que exigiria uma segunda credencial.

⚠️ **`Depends` não roda em chamada direta.** Chamar `listar_candidatos(...)` de
dentro daqui NÃO executa o `exige(...)` declarado nela — o FastAPI só resolve
dependências quando ele mesmo despacha a requisição. Por isso o decorador
`@ferramenta` reproduz a checagem explicitamente, e o teste-portão cobra que a
permissão declarada aqui é a MESMA que a rota declara. Sem esse par, a
ferramenta seria uma porta paralela que não passa pelo modelo de papéis (v2.86).
"""

from __future__ import annotations

import functools
import uuid

from sqlalchemy.orm import Session

from app.models.usuario_rh import UsuarioRH
from app.services import permissoes as cat
from app.services.anti_prompt_injection import limpar_saida

#: Nome → permissão exigida. Fonte única, lida pelo decorador E pelo teste.
PERMISSAO_DA_FERRAMENTA: dict[str, str] = {}


class SemPermissao(Exception):
    """A pessoa não tem a permissão que a ferramenta exige."""


def ferramenta(permissao: str):
    """Declara a permissão da ferramenta e a confere antes de executar.

    ⚠️ A chave é validada **na importação do módulo**, como o `exige()` faz:
    permissão escrita errada derruba o boot nomeando o erro, em vez de virar um
    403 em produção que ninguém liga à causa.
    """
    if permissao not in cat.CHAVES:
        raise KeyError(
            f"permissao_desconhecida: {permissao!r} — acrescente ao PERMISSOES "
            "de app/services/permissoes.py antes de usá-la numa ferramenta."
        )

    def _decorador(fn):
        PERMISSAO_DA_FERRAMENTA[fn.__name__] = permissao

        @functools.wraps(fn)
        def _com_checagem(db: Session, usuario: UsuarioRH, *args, **kwargs):
            from app.api.auth_rh import permissoes_do_usuario

            concedidas = permissoes_do_usuario(db, usuario)
            if not cat.pode(usuario.papel or "", concedidas, permissao):
                raise SemPermissao(
                    "Esta ação não é permitida para o assistente. O papel dele é "
                    "menor que o seu de propósito: efetivar, desligar, decidir "
                    "reembolso, exportar a base e assinar continuam só pela tela."
                )
            return fn(db, usuario, *args, **kwargs)

        _com_checagem.permissao = permissao
        return _com_checagem

    return _decorador


# ---------------------------------------------------------------- leitura


@ferramenta("admissao:ler")
def buscar_candidato(db: Session, usuario: UsuarioRH, busca: str,
                     incluir_colaboradores: bool = False) -> dict:
    """Acha pessoas em ADMISSÃO pelo nome, e-mail ou matrícula.

    Use como PRIMEIRO passo quando a pessoa citar alguém pelo nome: as demais
    ferramentas pedem o `id`, e é aqui que ele sai. Devolve uma lista resumida
    (nome, status, progresso dos documentos), não a ficha inteira.

    `incluir_colaboradores=True` alcança também quem já foi efetivado — a
    listagem padrão mostra só quem está em admissão, que é o recorte da tela.
    """
    from app.api.revisao import listar_candidatos

    encontrados = listar_candidatos(
        status=None, busca=busca, posto_id=None,
        incluir_colaboradores=incluir_colaboradores, db=db, _rh=usuario)
    return limpar_saida({"encontrados": encontrados})


@ferramenta("admissao:ler")
def diagnostico_candidato(db: Session, usuario: UsuarioRH, candidato_id: str) -> dict:
    """Responde POR QUÊ: o retrato completo de uma pessoa em admissão.

    Numa chamada só: dados-chave, **por que o dossiê não gera**, o formulário
    que falta preencher, as fichas a assinar, a situação de cada documento e a
    linha do tempo. É a ferramenta certa para "por que o dossiê de fulano não
    sai?", "o que falta para essa admissão fechar?" e "o que aconteceu com essa
    pessoa?" — não chame três ferramentas para isso.

    O CPF sai mascarado. A linha do tempo vem dos 200 eventos mais recentes.
    """
    from app.api.diagnostico import diagnostico_candidato as rota

    return limpar_saida(rota(candidato_id=_uuid(candidato_id), db=db, _rh=usuario))


@ferramenta("admissao:ler")
def listar_admissoes(db: Session, usuario: UsuarioRH, status: str | None = None,
                     busca: str | None = None) -> dict:
    """A fila de trabalho da admissão: quem está em cada etapa.

    Use para "o que tem na minha fila hoje?" ou "quem está com documento
    pendente?". `status` aceita os valores do funil (por exemplo `convidado`,
    `docs_pendentes`, `envio_concluido`, `em_revisao`, `aprovado`); sem ele,
    vem a fila inteira.
    """
    from app.api.revisao import listar_candidatos

    admissoes = listar_candidatos(status=status, busca=busca, posto_id=None,
                                  incluir_colaboradores=False, db=db, _rh=usuario)
    return limpar_saida({"admissoes": admissoes})


@ferramenta("colaboradores:ler")
def pendencias_tirvu(db: Session, usuario: UsuarioRH, busca: str | None = None,
                     incluir_importados: bool = False) -> dict:
    """O que impede a planilha de importação do Tirvu de ser aceita.

    O Tirvu RECUSA linha sem CTPS, PIS ou jornada, e a recusa acontece LÁ,
    depois do trabalho de montar o arquivo. Esta é a pré-checagem: devolve quem
    está incompleto e o que falta em cada um.

    ⚠️ Não gera nem baixa a planilha — exportar a base é ato de tela, por
    desenho (são CPF e salário de todo mundo num arquivo só).
    """
    from app.api.colaboradores import pendencias_tirvu as rota

    return limpar_saida(rota(status=None, busca=busca, situacao=None, posto_id=None,
                             ids=None, incluir_importados=incluir_importados,
                             db=db, _rh=usuario))


# ---------------------------------------------------------------- escrita


@ferramenta("selecao:escrever")
def cadastrar_talento(db: Session, usuario: UsuarioRH, nome: str,
                      email: str | None = None, telefone: str | None = None,
                      cargos_interesse: list[str] | None = None,
                      resumo: str | None = None, origem: str | None = None,
                      forcar: bool = False,
                      motivo_sem_curriculo: str | None = None) -> dict:
    """Cadastra uma pessoa no Banco de Talentos (currículo que chegou por e-mail,
    indicação, contato por telefone).

    **Duplicata AVISA e não funde**: se já houver alguém com o mesmo e-mail (ou
    o mesmo nome+telefone), a resposta recusa DIZENDO QUEM É — id, nome, e-mail
    e situação. Nesse caso, **mostre a pessoa encontrada e pergunte** antes de
    repetir a chamada com `forcar=True`; homônimo real existe (a base tem mais
    de mil pessoas), mas quem decide é quem está operando, nunca você.

    **Não marque consentimento de LGPD**: quem cadastra é o RH, a pessoa não
    está na tela para concordar com nada, e o cadastro registra quem assumiu.
    Não há parâmetro para isso e não deve haver.

    O currículo em si sobe pela tela — esta ferramenta cria o registro. Quando
    ele ainda não existe, explique em `motivo_sem_curriculo` (fica na auditoria
    e como anotação no CRM), porque o currículo é obrigatório desde a v3.06.

    `origem` é a PROCEDÊNCIA em texto ("Currículo por e-mail", "Indicação do
    Gabriel"), não o nome de quem digitou.
    """
    from app.api.talentos import TalentoRHIn, cadastrar_pelo_rh

    payload = TalentoRHIn(
        nome=nome, email=email, telefone=telefone,
        cargos_interesse=cargos_interesse or [], resumo=resumo, origem=origem,
        forcar=forcar, motivo_sem_curriculo=motivo_sem_curriculo,
    )
    return limpar_saida(cadastrar_pelo_rh(payload=payload, db=db, rh=usuario))


def _uuid(valor: str):
    try:
        return uuid.UUID(str(valor))
    except (ValueError, TypeError, AttributeError) as exc:
        raise ValueError(
            f"{valor!r} não é um identificador válido. Use `buscar_candidato` "
            "para achar o id da pessoa."
        ) from exc


#: As ferramentas expostas, na ordem em que fazem sentido para quem pergunta.
#: ⚠️ `erros_recentes` NÃO está aqui, e a ausência é decisão: a rota que a
#: serviria exige `sistema:telemetria`, que o papel do assistente não tem — ela
#: responderia 403 sempre, e ferramenta que nunca funciona ensina quem opera a
#: ignorar mensagem de erro (v2.88).
FERRAMENTAS = (buscar_candidato, diagnostico_candidato, listar_admissoes,
               pendencias_tirvu, cadastrar_talento)
