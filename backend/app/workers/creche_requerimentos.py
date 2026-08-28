"""Varredura dos requerimentos de creche pendentes — ENFILEIRÁVEL (v3.16.1).

Por que não é síncrona: cada pessoa avisada custa **~1s de SMTP** (medido: 951ms
por e-mail contra 4ms de consulta), e o nginx corta qualquer request acima de
60s. Com os 149 benefícios ativos do banco de desenvolvimento a varredura leva
~2,5 min — em produção o RH veria "erro de rede" **com metade dos e-mails já
enviados**, sem saber quem recebeu e quem não. É exatamente o caso que a
`services/fila.py` existe para resolver (v2.00, o mesmo raciocínio do
ranqueamento do Match).

⚠️ O trabalho pesado é o ENVIO, não a consulta — por isso não adianta otimizar
SQL aqui: o custo é externo e não encolhe.

O resultado fica na config dinâmica (`creche_varredura_requerimentos`), que a
tela consulta para mostrar o relatório quando terminar. Guardar o desfecho é o
que impede o "rodei e não sei o que aconteceu": sem isso, quem fecha a aba
perde o relatório de quem foi avisado — e é ele que diz para quem NÃO ir
cobrar de novo.
"""

import json
import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy import select

from app.core.db import SessionLocal
from app.models.beneficio import BeneficioCreche, StatusBeneficio
from app.models.candidato import Candidato
from app.models.usuario_rh import UsuarioRH

log = logging.getLogger(__name__)

CHAVE_RESULTADO = "creche_varredura_requerimentos"


def varrer(rh_id: str, rh_email: str,
           beneficio_ids: list[str] | None = None) -> dict:
    """Executa a varredura. Recebe só IDs — o RQ serializa a REFERÊNCIA da
    função e os argumentos, nunca objetos do SQLAlchemy (regra da v2.00).

    `beneficio_ids` RECORTA a varredura. Existe por duas razões: o teste
    precisa afirmar sobre os registros que ELE criou (asserção sobre a base
    inteira mede o tamanho do banco, não o comportamento — v2.72), e em
    produção dá para cobrar um grupo sem disparar e-mail para todo mundo.
    `None` = todos os ativos, que é o uso normal do botão da tela.
    """
    # Imports tardios: o worker sobe em paralelo com a API, e importar a
    # camada de rotas no topo acoplaria o processo à ordem de boot.
    from app.api.creche import _avisar_requerimento, _disparar_requerimento
    from app.services.auditoria import registrar
    from app.services.config_dinamica import gravar_config

    db = SessionLocal()
    try:
        rh = db.get(UsuarioRH, uuid.UUID(str(rh_id)))
        if rh is None:  # usuário removido entre o clique e a execução
            rh = UsuarioRH(email=rh_email, nome=rh_email, senha_hash="",
                           papel="superadmin")
        q = select(BeneficioCreche).where(
            BeneficioCreche.status == StatusBeneficio.ativo)
        if beneficio_ids:
            q = q.where(BeneficioCreche.id.in_(
                [uuid.UUID(str(i)) for i in beneficio_ids]))
        ativos = db.scalars(q).all()
        criados, avisados, sem_email, ja_assinados, falhas = [], [], [], [], []
        for ben in ativos:
            col = db.get(Candidato, ben.candidato_id)
            nome = col.nome_completo if col else str(ben.candidato_id)
            item = {"id": str(ben.id), "nome": nome}
            try:
                avisar, motivo = _disparar_requerimento(db, ben, rh)
                if not avisar:
                    if motivo == "ja_assinado":
                        ja_assinados.append(item)
                    continue
                if motivo == "criado_e_avisado":
                    registrar(db, "creche_requerimento_disparado", ator="rh",
                              ator_detalhe=rh_email, candidato_id=ben.candidato_id,
                              detalhe={"beneficio": str(ben.id), "em_lote": True})
                db.commit()
                if _avisar_requerimento(db, ben, col, rh, em_lote=True):
                    (criados if motivo == "criado_e_avisado" else avisados).append(item)
                else:
                    # Sem e-mail o aviso não chega, e o roteiro sozinho não
                    # resolve: vira lista PRÓPRIA, senão o RH leria como
                    # cobrado quem continua sem saber de nada.
                    sem_email.append(item)
            except Exception as exc:
                # Uma pessoa que falha não pode derrubar as demais — e a falha
                # precisa CHEGAR à tela com o nome de quem foi.
                db.rollback()
                log.exception("varredura de requerimento falhou para %s", nome)
                falhas.append({**item, "erro": str(exc)[:200]})
        resultado = {
            "criados": criados, "avisados": avisados, "sem_email": sem_email,
            "ja_assinados": ja_assinados, "falhas": falhas,
            "total_ativos": len(ativos),
            "concluido_em": datetime.now(timezone.utc).isoformat(),
            "por": rh_email,
        }
        # `gravar_config` guarda TEXTO (é a API da config dinâmica; não existe
        # variante para JSON) — serializa aqui e a rota desserializa.
        gravar_config(db, {CHAVE_RESULTADO: json.dumps(resultado)})
        db.commit()
        log.info("varredura de requerimentos: %d criados, %d avisados, "
                 "%d sem e-mail, %d falhas (de %d ativos)",
                 len(criados), len(avisados), len(sem_email), len(falhas),
                 len(ativos))
        return resultado
    finally:
        db.close()
