"""Recebimento do comprovante mensal — a porta que faltava, para as DUAS portas.

O colaborador envia pelo link do creche; o RH envia pelo painel (antes, o único
caminho quando faltava documento era DEVOLVER o levantamento e esperar). As duas
chamam `receber()`: duplicar a lógica faria as portas divergirem na primeira
mudança — foi o que o `_guardar_curriculo` (v2.74) já ensinou.

Neste sistema quase todo dado tem duas portas (v2.89.1), e aqui a diferença
entre elas é só QUEM está agindo — a regra de negócio é a mesma, e mora aqui.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, timezone

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.beneficio import BeneficioCreche, CriancaCreche, StatusBeneficio
from app.models.candidato import Candidato, PostoServico
from app.models.creche_competencia import CompetenciaCreche, StatusCompetencia
from app.services import creche_comprovante, creche_competencia
from app.services.auditoria import registrar


def _posto_do_beneficio(db: Session, ben: BeneficioCreche) -> PostoServico | None:
    col = db.get(Candidato, ben.candidato_id)
    if col is None or col.posto_servico_id is None:
        return None
    return db.get(PostoServico, col.posto_servico_id)


def anterior_a_vigencia(db: Session, ben: BeneficioCreche,
                        ano: int, mes: int) -> bool:
    """A competência é anterior à data em que o contrato passou a dar direito?

    NÃO recusa (decisão do Bruno, 18/08/2026): fica marcado para o RH decidir,
    porque há caso legítimo — o aditivo pode ter efeito retroativo, e recusar
    aqui negaria direito que existe. Sem vigência informada, devolve `False`:
    tratar "não sei desde quando" como "é retroativo" encheria a fila de alarme
    falso, e alarme falso ensina a ignorar o alarme (a lição dos processos 9.1/
    9.2 na v2.91).
    """
    posto = _posto_do_beneficio(db, ben)
    if posto is None or posto.creche_vigente_desde is None:
        return False
    inicio = posto.creche_vigente_desde
    # a competência cobre o mês inteiro: só é anterior se o mês TERMINOU antes
    # de o direito começar
    ultimo_dia_do_mes = (date(ano + 1, 1, 1) if mes == 12
                         else date(ano, mes + 1, 1))
    return ultimo_dia_do_mes <= inicio


def receber(db: Session, ben: BeneficioCreche, crianca_id: uuid.UUID,
            ano: int, mes: int, partes: list[tuple[str, bytes]],
            valor_texto: str | None, ator: str,
            ator_detalhe: str | None = None,
            hoje: date | None = None) -> CompetenciaCreche:
    """Grava (ou substitui) o comprovante de UMA criança em UM mês.

    Levanta `HTTPException` com `detail` que a tela sabe traduzir. As guardas
    estão aqui, no SERVIÇO, e não na rota, pelo mesmo motivo da checagem de
    consentimento da v2.66: porta nova que não passasse por elas furaria a regra
    sem nada na tela denunciando.
    """
    hoje = hoje or datetime.now(timezone.utc).date()

    crianca = db.get(CriancaCreche, crianca_id)
    if crianca is None or crianca.beneficio_id != ben.id:
        raise HTTPException(status_code=404, detail="crianca_nao_encontrada")
    if not partes:
        raise HTTPException(status_code=422, detail="arquivo_vazio")

    # Criança indeferida não gera reembolso — aceitar o comprovante dela criaria
    # despesa comprovada para quem não tem direito, e alguém somaria isso.
    if crianca.decisao == "indeferida":
        raise HTTPException(status_code=409, detail={
            "erro": "crianca_indeferida", "crianca": crianca.nome,
            "motivo": crianca.motivo_decisao})

    # Só benefício ATIVO recebe comprovante mensal: em análise ainda não há
    # direito reconhecido, e suspenso/encerrado deixou de haver.
    if ben.status != StatusBeneficio.ativo:
        raise HTTPException(status_code=409, detail={
            "erro": "beneficio_nao_ativo", "status": ben.status.value})

    problema = creche_competencia.valida(ano, mes, hoje)
    if problema:
        raise HTTPException(status_code=422, detail={
            "erro": problema, "competencia": creche_competencia.rotulo(ano, mes)})

    registro = db.scalar(select(CompetenciaCreche).where(
        CompetenciaCreche.crianca_id == crianca_id,
        CompetenciaCreche.ano == ano, CompetenciaCreche.mes == mes))
    if registro is None:
        registro = CompetenciaCreche(
            beneficio_id=ben.id, crianca_id=crianca_id, ano=ano, mes=mes)
        db.add(registro)
        db.flush()
    elif registro.status == StatusCompetencia.aprovado.value:
        # Reenviar por cima de um comprovante JÁ APROVADO trocaria a peça que
        # sustenta um pagamento que talvez já tenha saído. Quem precisa corrigir
        # isso é o RH, reabrindo — não o colaborador, em silêncio.
        raise HTTPException(status_code=409, detail={
            "erro": "competencia_ja_aprovada",
            "competencia": creche_competencia.rotulo(ano, mes)})

    # O tipo é copiado da criança, mas guardado NA COMPETÊNCIA: a família pode
    # trocar de arranjo no meio do ano, e o registro do mês tem de descrever o
    # que foi entregue naquele mês.
    registro.tipo_comprovante = crianca.tipo_comprovante
    registro.valor_informado_texto = (valor_texto or "").strip() or None
    registro.valor_centavos = creche_competencia.centavos(valor_texto)
    registro.anterior_a_vigencia = anterior_a_vigencia(db, ben, ano, mes)
    # Reenvio volta para "enviado": um comprovante recusado que é reenviado
    # precisa ser analisado de novo, senão fica com a recusa antiga colada.
    registro.status = StatusCompetencia.enviado.value
    registro.motivo_recusa = None
    registro.analisado_por = None
    registro.analisado_em = None

    paginas = creche_comprovante.gravar(db, registro, partes,
                                        ator=ator, ator_detalhe=ator_detalhe)

    registrar(db, "creche_comprovante_enviado", ator=ator,
              ator_detalhe=ator_detalhe, candidato_id=ben.candidato_id,
              detalhe={"crianca": crianca.nome,
                       "competencia": creche_competencia.rotulo(ano, mes),
                       "paginas": paginas,
                       "valor": registro.valor_informado_texto,
                       "tipo": registro.tipo_comprovante,
                       "anterior_a_vigencia": registro.anterior_a_vigencia})
    db.commit()
    return registro


def dump(registro: CompetenciaCreche, teto_centavos: int | None = None) -> dict:
    """A competência como a tela a lê.

    Devolve o valor COMPROVADO e o REEMBOLSÁVEL separadamente: são números
    diferentes quando a despesa passa do teto, e mostrar só um deles esconderia
    de qual se está falando bem no lugar onde isso decide pagamento.
    """
    reembolsavel = creche_competencia.valor_reembolsavel(
        registro.valor_centavos, teto_centavos)
    return {
        "id": str(registro.id), "crianca_id": str(registro.crianca_id),
        "ano": registro.ano, "mes": registro.mes,
        "competencia": creche_competencia.rotulo(registro.ano, registro.mes),
        "status": registro.status,
        "tipo_comprovante": registro.tipo_comprovante,
        "valor_informado": registro.valor_informado_texto,
        "valor_comprovado": creche_competencia.reais(registro.valor_centavos),
        "valor_reembolsavel": creche_competencia.reais(reembolsavel),
        "paginas": registro.paginas,
        "tem_arquivo": bool(registro.arquivo_pdf_key),
        "enviado_em": registro.enviado_em,
        "enviado_por": registro.enviado_por,
        "analisado_por": registro.analisado_por,
        "analisado_em": registro.analisado_em,
        "motivo_recusa": registro.motivo_recusa,
        "anterior_a_vigencia": registro.anterior_a_vigencia,
    }
