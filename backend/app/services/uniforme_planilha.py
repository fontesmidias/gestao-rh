"""Planilha de uniforme — a que vai ANEXA no aviso ao operacional (v2.81).

Pedido do Bruno (2026-08-07):

    "No corpo do email de envio de uniformes, tem que ir os dados da pessoa,
     como nome, CPF, cargo, posto e medidas. (…) quero algo que seja possível
     através da leitura do email, os responsáveis do uniforme identificarem as
     informações, sem a necessidade de entrar no sistema. Acho que seria o caso
     uma planilha do Excel ser enviada por e-mail."

## Isto REVERTE, conscientemente, a decisão da v2.07

Lá ele pediu a mesma coisa e, ao ser perguntado, escolheu o contrário: os dados
ficariam só na tela, e o e-mail seria um empurrão ("fulano informou os
tamanhos"). O argumento era bom — *"ficha de pessoal circulando em caixa que
ninguém controla"*.

O uso mostrou o custo do outro lado: quem compra e separa uniforme **não é
usuário do sistema**, e obrigá-lo a entrar para ver três medidas transformava um
recado em tarefa. Perguntado de novo (2026-08-08), ele escolheu a planilha
ANEXA — que é o meio-termo que não existia antes:

  · **anexo, não corpo** — não fica indexado no histórico da caixa de todo mundo
    e dá para abrir no Excel e trabalhar em cima;
  · **uma pessoa por e-mail**, no gatilho que já existia — não é o dump da base.

Fica registrado que é uma reversão, e por quê: sem isso, a próxima leva leria a
regra da v2.07 no `CLAUDE.md` e "consertaria" isto de volta.

## O que NÃO vai na planilha

Só o que serve para comprar e entregar uniforme: nome, CPF, cargo, posto e as
três medidas. Endereço, salário, dados bancários, PIS — nada disso entra, mesmo
estando a um `getattr` de distância. Anexo circula; o que não é necessário para
a tarefa não deve viajar junto (minimização, a mesma regra do
`curriculo_texto.py`).
"""

from sqlalchemy.orm import Session

from app.models.candidato import Candidato

# Ordem das colunas na planilha. Explícita, e não a união das chaves do dict:
# quem abre precisa achar sempre a mesma coluna no mesmo lugar (a lição do
# layout do Tirvu, v1.82).
COLUNAS = ("Nome", "CPF", "Cargo", "Posto", "Calça", "Camisa", "Calçado")


def linha_uniforme(db: Session, candidato: Candidato) -> dict:
    """Os dados de uniforme de UMA pessoa, prontos para a planilha.

    Célula vazia vira `""` e não `None`: o `montar_workbook` escreve o que
    recebe, e `None` viraria a string "None" na cara de quem abre.
    """
    from app.models.candidato import PostoServico
    from app.models.ficha import DadosProfissionaisBancarios
    from app.services.export_tirvu import cpf_mascarado

    d = db.get(DadosProfissionaisBancarios, candidato.id)
    posto = (db.get(PostoServico, candidato.posto_servico_id)
             if candidato.posto_servico_id else None)

    # O CPF vive em DOIS lugares: no `Candidato` (o do convite) e na ficha de
    # identificação (o que a pessoa digitou). O da ficha é o conferido contra o
    # documento — por isso vem primeiro.
    from app.models.ficha import DocumentosIdentificacao
    docs = db.get(DocumentosIdentificacao, candidato.id)
    cpf = (docs.cpf if docs and docs.cpf else None) or candidato.cpf

    return {
        "Nome": candidato.nome_completo or "",
        "CPF": cpf_mascarado(cpf) if cpf else "",
        "Cargo": candidato.cargo_funcao or "",
        "Posto": posto.nome if posto else "",
        "Calça": (d.tamanho_calca if d else None) or "",
        "Camisa": (d.tamanho_camisa if d else None) or "",
        "Calçado": (d.tamanho_calcado if d else None) or "",
    }


def montar_planilha(db: Session, candidatos: list[Candidato]) -> bytes:
    """Os bytes do .xlsx com as linhas de uniforme.

    Reusa o `montar_workbook` genérico — o mesmo que gera os demais exports do
    painel. Um montador próprio só se justificaria se o formato tivesse exigência
    externa (é o caso do Tirvu e do Dexion, que recusam desvio de forma); aqui
    quem abre é uma pessoa.
    """
    from app.services.export_planilha import montar_workbook

    linhas = [linha_uniforme(db, c) for c in candidatos]
    # Garante a ORDEM das colunas mesmo que alguma pessoa tenha campo vazio: o
    # `montar_workbook` monta as colunas pela união das chaves na ordem em que
    # aparecem, então a primeira linha define o layout.
    linhas = [{col: linha.get(col, "") for col in COLUNAS} for linha in linhas]
    return montar_workbook(linhas, titulo="Uniforme")


def nome_do_arquivo(candidato: Candidato) -> str:
    """`uniforme-maria-souza.xlsx` — nome que se entende na caixa de entrada.

    Passa pelo `slug()`: o nome é texto do usuário e vira NOME DE ARQUIVO. Sem
    isso, um nome com `/` ou `..` viraria caminho (regra do `export_planilha`).
    """
    from app.services.export_planilha import slug

    return f"uniforme-{slug(candidato.nome_completo or 'colaborador')}.xlsx"
