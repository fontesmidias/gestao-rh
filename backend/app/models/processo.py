"""Carteira de Processos do RH (v2.91).

Modela o que a `Carteira_Processos_RH_MatrizRACI.xlsx` do Bruno já descreve: 31
processos em 9 fases do ciclo de vida do colaborador, cada um com um TITULAR e
uma cadeia de apoio ordenada, atravessando dois cenários de efetivo.

A tese do documento, na palavra dele: *"Nenhum processo deve depender de uma
única pessoa."* O que o sistema acrescenta à planilha é responder na hora
*"quem responde por isto hoje?"* quando alguém sai — sem ninguém reescrever
nada.

**A titularidade é do CARGO, não da pessoa** (decisão do Bruno, e o próprio
documento já dizia: *"a titularidade dos processos acompanha a função, não a
pessoa"* — o caso Fátima). Trocar quem ocupa uma função não redistribui
carteira nenhuma: muda-se a pessoa alocada naquele cargo e os 31 processos
seguem com dono. Amarrar à pessoa faria cada saída virar um mutirão de
redistribuição, que é exatamente o problema a resolver.
"""

import uuid
from datetime import datetime

from sqlalchemy import (Boolean, DateTime, ForeignKey, Integer, String, Text,
                        UniqueConstraint, func)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import expression

from app.core.db import Base


class FuncaoRH(Base):
    """Uma função da área (Coordenação, Assistente Sênior, Auxiliar Júnior…).

    É a UNIDADE que possui processos. A pessoa que a ocupa é um atributo dela —
    e `pessoa_nome` é texto livre, não FK para `UsuarioRH`: a carteira precisa
    descrever gente que ainda **não tem conta no sistema** (o "Analista de RH Jr
    (a contratar)" do cenário 2) e gente que opera sem login. Amarrar a uma FK
    obrigaria a criar usuário para poder desenhar a estrutura.
    """

    __tablename__ = "funcao_rh"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True,
                                          default=uuid.uuid4)
    nome: Mapped[str] = mapped_column(String(120), unique=True)
    descricao: Mapped[str | None] = mapped_column(String(400), nullable=True)
    # Quem ocupa a função HOJE. Vazio = vaga aberta — e é isso que faz a tela
    # poder dizer "estes 6 processos estão sem gente", em vez de mostrá-los com
    # um dono que não existe.
    pessoa_nome: Mapped[str | None] = mapped_column(String(200), nullable=True)
    pessoa_email: Mapped[str | None] = mapped_column(String(200), nullable=True)
    # Ordem de exibição (Coordenação primeiro, depois sênior, júnior…).
    ordem: Mapped[int] = mapped_column(Integer, default=0)
    ativa: Mapped[bool] = mapped_column(Boolean, default=True,
                                        server_default=expression.true())
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True),
                                                server_default=func.now())


class Processo(Base):
    """Um processo da carteira: o que é, em que fase acontece, com que ritmo."""

    __tablename__ = "processo_rh"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True,
                                          default=uuid.uuid4)
    # "1.1", "2.4" — o código da planilha. Único: é por ele que a importação
    # ATUALIZA em vez de duplicar, e é como a equipe já se refere a cada um.
    codigo: Mapped[str] = mapped_column(String(20), unique=True, index=True)
    fase: Mapped[str] = mapped_column(String(120))
    nome: Mapped[str] = mapped_column(String(300))
    # Ritmo é a JANELA DE RESPOSTA esperada, não a dificuldade (a legenda da
    # planilha é explícita nisso): Imediato | Rápido | Curto | Médio |
    # Médio/Longo | Diário | Contínuo | Mensal. String, não enum: o Bruno
    # revisa a carteira a cada trimestre, e um ritmo novo não deve exigir
    # migration (a armadilha do `ALTER TYPE` em duas revisões).
    ritmo: Mapped[str | None] = mapped_column(String(40), nullable=True)
    observacao: Mapped[str | None] = mapped_column(Text, nullable=True)
    # RACI opcional (decisão do Bruno): a CADEIA é o modelo principal; estes
    # descrevem quem APROVA, quem é CONSULTADO e quem é INFORMADO quando o
    # processo tem essa distinção. Listas de nomes de função.
    aprovadores: Mapped[list] = mapped_column(JSONB, default=list)
    consultados: Mapped[list] = mapped_column(JSONB, default=list)
    informados: Mapped[list] = mapped_column(JSONB, default=list)
    ativo: Mapped[bool] = mapped_column(Boolean, default=True,
                                        server_default=expression.true())
    ordem: Mapped[int] = mapped_column(Integer, default=0)
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True),
                                                server_default=func.now())


class AtribuicaoProcesso(Base):
    """Quem responde por um processo, em que posição da cadeia e em que cenário.

    `posicao` 1 = titular (o dono); 2, 3, 4… = a ordem de quem assume na
    ausência. É uma LINHA por posição, e não uma lista no `Processo`, por três
    razões: a consulta "por quais processos a Fátima responde?" vira um índice
    em vez de varredura de JSON; trocar uma posição não reescreve o resto; e o
    banco garante que não existam dois titulares do mesmo processo no mesmo
    cenário (o `UniqueConstraint` abaixo).

    `cenario` guarda os dois momentos da área que a planilha já separa — C1
    (estrutura vigente) e C2 (com o Analista Jr). Modelar os dois permite
    responder "como fica quando a vaga for preenchida?" sem reescrever a
    carteira: é a pergunta de dimensionamento que o Bruno faz.
    """

    __tablename__ = "atribuicao_processo"
    __table_args__ = (
        # Sem isto, dois titulares do mesmo processo no mesmo cenário passariam
        # despercebidos — e "quem responde por isto?" passaria a ter duas
        # respostas, que é o mesmo que não ter nenhuma.
        UniqueConstraint("processo_id", "cenario", "posicao",
                         name="uq_atribuicao_posicao"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True,
                                          default=uuid.uuid4)
    processo_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("processo_rh.id", ondelete="CASCADE"), index=True)
    funcao_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("funcao_rh.id", ondelete="CASCADE"), index=True)
    cenario: Mapped[str] = mapped_column(String(4), default="C1", index=True)
    posicao: Mapped[int] = mapped_column(Integer)   # 1 = titular


class EscalaCanal(Base):
    """A escala rotativa de canais: quem atende o quê em cada dia útil.

    A carteira do Bruno tem uma aba própria para isto — 5 postos (Demandas,
    E-mail, Teams, WhatsApp, Retaguarda) girando entre a equipe num ciclo de 4
    semanas, por cenário. É ela que responde pelos processos 9.1 e 9.2, cujo
    "titular" é a própria escala.

    Sem importá-la, a tela dizia "Escala do dia" e não sabia dizer QUEM — que é
    justamente a informação que alguém procura ao olhar a carteira numa
    terça-feira. Uma linha por (cenário, semana, dia, posto): é a forma que
    permite responder "quem está no WhatsApp hoje?" com um índice, e é a mesma
    granularidade da planilha, o que mantém a reimportação simples.
    """

    __tablename__ = "escala_canal"
    __table_args__ = (
        UniqueConstraint("cenario", "semana", "dia", "posto",
                         name="uq_escala_posto"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True,
                                          default=uuid.uuid4)
    cenario: Mapped[str] = mapped_column(String(4), default="C1", index=True)
    semana: Mapped[int] = mapped_column(Integer)          # 1..4 (o ciclo)
    # Guardado como TEXTO ("Segunda"), não como número: é o que a planilha traz
    # e o que a tela mostra. Converter para índice exigiria mapear de volta em
    # dois lugares, e o ganho seria nenhum.
    dia: Mapped[str] = mapped_column(String(20))
    posto: Mapped[str] = mapped_column(String(40))        # Demandas, E-mail…
    pessoa: Mapped[str] = mapped_column(String(200))
