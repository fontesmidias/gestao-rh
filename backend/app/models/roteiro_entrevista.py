"""Roteiro de entrevista (v2.66) — o instrumento saiu do código e virou dado.

Até a v2.65 as 4 competências viviam em `services/entrevistas.py` como constante
de módulo. O Bruno pediu o contrário, e o pedido reorganiza o módulo:

> *"poderiam haver vários modelos de roteiros já, para os mais variados níveis de
> senioridades e cargos que já temos, [...] bem como customizar roteiros para que
> sejam submetidos a aprovação e, após isso, poderem ser utilizados."*

Três decisões travadas que este modelo sustenta:

**1. Rascunho → publicado, e SÓ publicado se usa.**
Roteiro nasce `rascunho` e não pode ser escolhido em entrevista nenhuma.
Publicar é ato separado, com autor e data. Isso não é burocracia: é o que
sustenta o argumento jurídico do § 6 do documento. A defesa perante a Lei
9.029/95 não é "existe um roteiro" — é **"o roteiro foi aprovado ANTES de ser
usado"**. Sem a trava, o argumento cai, e o módulo perde a razão que o justifica
perante a diretoria.

**2. Versão congelada.** Editar um roteiro publicado gera a versão SEGUINTE. A
entrevista já feita continua mostrando o roteiro com que foi feita — é o mesmo
princípio do snapshot de `titulo_doc`/`corpo_doc` em `solicitacao_assinatura`:
editar o modelo não muda o que a pessoa assinou. Por isso a `Entrevista` ganha
`roteiro_snapshot` (JSON), não só `roteiro_id`: FK sozinha leria o texto DE HOJE
numa avaliação de meses atrás, e a nota deixaria de significar o que significava.

**3. Herança cargo → senioridade → padrão.** O mais específico vence, como
`meses_validade_de` do módulo de Desenvolvimento já faz. O casamento é por
`cargo_norm` (= `normalizar_cargo`, a MESMA função do de-para do Tirvu) porque
cargo é TEXTO LIVRE (`Candidato.cargo_funcao`) e a base tem 87 pessoas em
"AUXILIAR DE SERVIÇOS GERAIS" escrito de formas diferentes. Cargo sem roteiro
**cai no padrão, nunca em erro** — tela vazia por falta de cadastro seria o
módulo se recusando a funcionar por um dado que ninguém preencheu.

O `padrao=True` marca o roteiro-raiz: **não se apaga e não se arquiva sem que
exista outro no lugar**. É o piso do sistema; sem ele a resolução por herança
não teria fundo e uma entrevista de cargo novo abriria sem instrumento nenhum.
"""
import uuid
from datetime import datetime
from enum import Enum

from sqlalchemy import Boolean, DateTime, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class StatusRoteiro(str, Enum):
    rascunho = "rascunho"      # em edição — NÃO pode ser usado (cenário 22)
    publicado = "publicado"    # aprovado; é o único estado utilizável
    arquivado = "arquivado"    # aposentado; entrevistas antigas seguem legíveis


# Senioridades aceitas. Lista FIXA de propósito (mesma escolha do `SENIORIDADES`
# do banco de itens de provas): senioridade como texto livre viraria
# "pleno"/"Pleno"/"plena" e a herança pararia de casar em silêncio.
SENIORIDADES = ["junior", "pleno", "senior"]


class RoteiroEntrevista(Base):
    __tablename__ = "roteiro_entrevista"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    nome: Mapped[str] = mapped_column(String(120))

    # Cargo é TEXTO LIVRE em todo o sistema; `cargo_norm` é a chave de
    # casamento (minúsculo, sem acento, espaços colapsados). None = o roteiro
    # não é de cargo nenhum — serve como padrão.
    cargo: Mapped[str | None] = mapped_column(String(120))
    cargo_norm: Mapped[str | None] = mapped_column(String(120), index=True)
    # None = vale para TODAS as senioridades daquele cargo.
    senioridade: Mapped[str | None] = mapped_column(String(20))

    status: Mapped[str] = mapped_column(
        String(20), default=StatusRoteiro.rascunho.value, index=True)
    # Incrementa a cada publicação. A entrevista guarda o snapshot, então a
    # versão serve ao HISTÓRICO e à tela — não à leitura da entrevista antiga.
    versao: Mapped[int] = mapped_column(Integer, default=1)

    # O instrumento inteiro: [{chave, nome, ancoras{"1".."4"}, perguntas{...}}].
    # JSON e não tabela por item, pelo mesmo motivo de `Avaliacao.competencias`:
    # o conteúdo é lido e escrito inteiro, nunca consultado por item.
    competencias: Mapped[list | None] = mapped_column(JSONB)

    # O roteiro-raiz. Semeado pela migration a partir da constante que era a
    # fonte até a v2.65. Não se apaga (cenário 25).
    padrao: Mapped[bool] = mapped_column(Boolean, default=False, index=True)

    # O ATO de aprovação, auditado — é o que a defesa jurídica invoca.
    publicado_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    publicado_por: Mapped[str | None] = mapped_column(String(200))

    criado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now())
    criado_por: Mapped[str | None] = mapped_column(String(200))
    arquivado_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
