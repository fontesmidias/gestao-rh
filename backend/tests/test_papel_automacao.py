"""O papel `automacao` (MCP) é estreito POR DESENHO — e continua estreito (v2.94).

Este teste existe porque a proteção aqui é uma LISTA, e lista alarga sozinha:
amanhã alguém precisa que a automação leia mais uma coisa, acrescenta a chave, e
nada reprova. O papel deixaria de ser "assistente de diagnóstico" e viraria mais
um administrador — em silêncio, porque tudo continua funcionando.

O que se protege, e por quê (ver `docs/planejamento/13-mcp-do-portal.md`):

1. **Não exporta base.** O eixo da permissão é a natureza do ATO (v2.86): um GET
   que devolve 1.171 CPFs é `dados:exportar_base`, não `:ler`. Assistente de
   diagnóstico não puxa a base inteira.
2. **Não lê a própria trilha.** Quem é auditado não lê auditoria nem log.
3. **Uma única escrita.** `selecao:escrever` — a porta de cadastrar talento. Nada
   que efetive, desligue, decida benefício, gere dossiê ou crie usuário.
4. **Não é superadmin.** `tudo=False`: o papel que ignora a checagem é o do dono
   do sistema, e um papel de máquina com `tudo` seria a chave da casa num token
   guardado em desktop.

⚠️ Se uma asserção daqui falhar depois de você acrescentar uma permissão ao
papel, a pergunta não é "como faço o teste passar?" — é *"esta permissão é de
DIAGNÓSTICO?"*. Se for de ação, ela provavelmente não pertence a este papel.

Roda no bloco stdlib do CI: não importa a app, só o catálogo.
"""

import pathlib
import sys

RAIZ = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from app.services.permissoes import (CHAVES, PAPEIS_POR_CHAVE,  # noqa: E402
                                     permissoes_padrao)

CHAVE = "automacao"

falhas: list[str] = []


def checar(condicao: bool, descricao: str) -> None:
    print(f"  {'ok  ' if condicao else 'FALHOU'}  {descricao}")
    if not condicao:
        falhas.append(descricao)


# O que o papel JAMAIS pode ter. Cada entrada é uma decisão registrada, não uma
# preferência: a chave à esquerda, o motivo à direita.
PROIBIDAS = {
    "dados:exportar_base": "puxaria a base inteira com CPF",
    "dados:auditoria": "quem é auditado não lê a própria trilha",
    "dados:logs": "log tem CPF e e-mail de gente real",
    "dados:expurgar": "apagar arquivo não se desfaz",
    "config:usuarios": "criaria outro usuário — inclusive administrador",
    "config:escrever": "mudaria a configuração do sistema",
    "colaboradores:efetivar": "efetivar é ato de vínculo",
    "colaboradores:desligar": "desligar é ato de vínculo",
    "colaboradores:escrever": "editaria cadastro de colaborador",
    "admissao:escrever": "editaria ficha de admissão",
    "admissao:dossie": "geraria o documento que circula",
    "admissao:revisar_documento": "aprovar documento é juízo humano",
    "creche:decidir": "decide dinheiro no contracheque",
    "desempenho:homologar": "fecha a avaliação de uma pessoa",
    "documentos:assinar": "assinatura é ato de vontade",
    "sistema:lixeira": "restauraria/removeria registro excluído",
    "recepcao:configurar": "configuração de outro módulo",
}


def main() -> int:
    print("=== 1. O papel existe no catálogo ===")
    padrao = PAPEIS_POR_CHAVE.get(CHAVE)
    checar(padrao is not None, f"papel '{CHAVE}' está em PAPEIS_PADRAO")
    if padrao is None:
        print("\nREPROVADO — sem o papel, o resto não se verifica.")
        return 1

    concedidas = permissoes_padrao(CHAVE)
    print(f"        (concede: {sorted(concedidas)})")

    print("\n=== 2. NÃO é superadmin ===")
    # `tudo=True` ignora a checagem inteira. Num papel de máquina, cujo token
    # vive num desktop, isso seria entregar a chave da casa.
    checar(padrao.tudo is False,
           "o papel não tem `tudo=True` (não ignora a checagem de permissão)")

    print("\n=== 3. As permissões proibidas continuam de fora ===")
    for chave, motivo in sorted(PROIBIDAS.items()):
        checar(chave not in concedidas, f"não concede `{chave}` — {motivo}")

    print("\n=== 4. Só UMA escrita, e é a de cadastrar talento ===")
    escritas = {c for c in concedidas
                if not c.endswith(":ler") and c != "selecao:escrever"}
    checar(not escritas,
           f"nenhuma escrita além de `selecao:escrever` (sobrando: {sorted(escritas)})")
    checar("selecao:escrever" in concedidas,
           "concede `selecao:escrever` (a porta de cadastrar talento)")

    print("\n=== 5. O que concede existe mesmo no catálogo ===")
    # Chave inventada não dá erro: ela simplesmente nunca casa, e o papel
    # concede menos do que o rótulo promete.
    inexistentes = sorted(concedidas - CHAVES)
    checar(not inexistentes,
           f"toda chave concedida existe em PERMISSOES (fantasmas: {inexistentes})")

    print("\n=== 6. O papel é MENOR que o do RH ===")
    # Se a automação puder mais que a equipe de RH, o desenho se inverteu.
    do_rh = permissoes_padrao("rh")
    extras = sorted(concedidas - do_rh)
    checar(not extras,
           f"não concede nada que o papel 'rh' não tenha (extras: {extras})")
    checar(len(concedidas) < len(do_rh),
           f"é estritamente menor que o do RH ({len(concedidas)} < {len(do_rh)})")

    print("\n" + "=" * 62)
    if falhas:
        print(f"REPROVADO — {len(falhas)} verificação(ões) falharam:")
        for f in falhas:
            print(f"  - {f}")
        print("\nAntes de 'consertar o teste': a permissão nova é de DIAGNÓSTICO?")
        return 1
    print("APROVADO — o papel da automação continua estreito.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
