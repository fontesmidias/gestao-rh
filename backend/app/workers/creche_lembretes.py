"""Lembrete da entrega mensal do reembolso-creche.

Pedido do Bruno (18/08/2026): *"ver um método de que quando vai se aproximando
a data de corte, ser enviado um lembrete da pessoa acessar o sistema e anexar a
documentação mensal correspondente"*, com *"datas customizáveis pelo front. Ex:
se a data de corte for todo dia 25, ter a opção de enviar 1d antes, 2d antes e
por aí vai, quantos forem necessários."*

Existe porque o e-mail de ativação PROMETIA a entrega mensal e nada a cobrava: o
`dia_entrega_mensal` era gravado, exibido e citado num e-mail enviado UMA vez —
e nenhum worker o consumia. Sem cobrança, quem esquece só descobre quando o
reembolso não sai.

⚠️ **Três armadilhas do projeto que este worker precisa respeitar:**

* **Worker que não está nos DOIS arquivos de deploy não roda em produção**
  (v2.66) — `docker-compose.base.yml` E `portainer-stack.yml`. Foi assim que o
  aviso de certificação vencendo nunca saiu, sem ninguém saber: worker que não
  roda não gera erro, gera silêncio.
* **A janela de varredura tem de ser maior que a cadência** — aqui o worker roda
  a cada 6h e cada dia de antecedência é conferido pela DATA, não por uma janela
  de horas, então um lembrete não cai no vão entre duas passadas.
* **Anti-spam pelo CARIMBO, não pela janela** (v2.66): o registro na auditoria é
  o que impede o mesmo lembrete de sair duas vezes no mesmo dia.
"""

import logging
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import select

from app.core.db import SessionLocal
from app.models.beneficio import BeneficioCreche, CriancaCreche, StatusBeneficio
from app.models.candidato import Candidato
from app.models.creche_competencia import CompetenciaCreche
from app.models.evento import EventoAuditoria
from app.services import creche_competencia as regras

log = logging.getLogger(__name__)

ACAO = "creche_lembrete_enviado"
# Quantos dias antes do corte avisar. Editável pelo RH em Configurações; o
# padrão cobre o caso que o Bruno descreveu (avisar com alguns dias e na véspera).
CHAVE_DIAS = "creche_lembrete_dias_antes"
DIAS_PADRAO = (5, 2, 1)


def dias_configurados(db) -> tuple[int, ...]:
    """Os dias de antecedência escolhidos pelo RH, ou o padrão.

    Lista vazia é decisão VÁLIDA (desligar os lembretes) e por isso é
    distinguida de "não configurado" — chave ausente cai no padrão, chave vazia
    desliga. Tratar as duas igual faria o RH não conseguir desligar.
    """
    from app.services.config_dinamica import ler_config

    bruto = ler_config(db, (CHAVE_DIAS,)).get(CHAVE_DIAS)
    if bruto is None:
        return DIAS_PADRAO
    dias = []
    for parte in str(bruto).replace(";", ",").split(","):
        parte = parte.strip()
        if parte.isdigit() and 0 <= int(parte) <= 28:
            dias.append(int(parte))
    return tuple(sorted(set(dias), reverse=True))


def _ja_avisado(db, beneficio_id, ano: int, mes: int, dias: int) -> bool:
    """Este lembrete exato (competência + antecedência) já saiu?

    A chave inclui a ANTECEDÊNCIA: avisar "faltam 5 dias" e depois "falta 1 dia"
    são dois lembretes legítimos da mesma competência. Sem isso, o segundo nunca
    sairia — e é justamente o da véspera que faz a pessoa agir.
    """
    limite = datetime.now(timezone.utc) - timedelta(days=40)
    return db.scalar(select(EventoAuditoria).where(
        EventoAuditoria.acao == ACAO,
        EventoAuditoria.criado_em >= limite,
        EventoAuditoria.detalhe["beneficio"].astext == str(beneficio_id),
        EventoAuditoria.detalhe["competencia"].astext == f"{mes:02d}/{ano}",
        EventoAuditoria.detalhe["dias_antes"].astext == str(dias),
    )) is not None


def pendencias(db, hoje: date | None = None) -> list[tuple]:
    """(benefício, colaborador, crianças sem comprovante, ano, mes, dias).

    Só benefício ATIVO e só criança DEFERIDA: cobrar comprovante de quem foi
    indeferido faria a pessoa juntar documento para um direito que não tem, e
    cobrar de benefício suspenso é pedir despesa que não será reembolsada.
    """
    hoje = hoje or date.today()
    dias_alvo = dias_configurados(db)
    if not dias_alvo:
        return []

    ano, mes = regras.competencia_anterior(hoje)
    saida = []
    ativos = db.scalars(select(BeneficioCreche).where(
        BeneficioCreche.status == StatusBeneficio.ativo)).all()
    for ben in ativos:
        dia_corte = ben.dia_entrega_mensal or regras.DIA_CORTE_PADRAO
        faltam = regras.dias_para_o_corte(dia_corte, hoje)
        if faltam not in dias_alvo:
            continue
        entregues = {
            r.crianca_id for r in db.scalars(select(CompetenciaCreche).where(
                CompetenciaCreche.beneficio_id == ben.id,
                CompetenciaCreche.ano == ano, CompetenciaCreche.mes == mes)).all()}
        pendentes = [c for c in db.scalars(select(CriancaCreche).where(
            CriancaCreche.beneficio_id == ben.id)).all()
            if c.decisao != "indeferida" and c.id not in entregues]
        if not pendentes:
            continue
        col = db.get(Candidato, ben.candidato_id)
        if col is None:
            continue
        saida.append((ben, col, pendentes, ano, mes, faltam))
    return saida


def avisar(db, hoje: date | None = None) -> int:
    """Manda os lembretes devidos e devolve quantos saíram."""
    from app.core.config import get_settings
    from app.services.auditoria import registrar
    from app.services.email_templates import enviar_modelo

    enviados = 0
    for ben, col, pendentes, ano, mes, faltam in pendencias(db, hoje):
        if _ja_avisado(db, ben.id, ano, mes, faltam):
            continue
        email = ben.email_confirmado or col.email
        if not email:
            continue
        enviar_modelo(db, "creche_lembrete_mensal", email, {
            "nome": (col.nome_completo or "").split()[0].title(),
            "competencia": regras.rotulo(ano, mes),
            "dia": ben.dia_entrega_mensal or regras.DIA_CORTE_PADRAO,
            "dias": faltam,
            "criancas": ", ".join(c.nome for c in pendentes),
            "link": f"{get_settings().base_url.rstrip('/')}/creche",
        })
        registrar(db, ACAO, ator="sistema", candidato_id=col.id,
                  detalhe={"beneficio": str(ben.id),
                           "competencia": f"{mes:02d}/{ano}",
                           "dias_antes": faltam,
                           "criancas": len(pendentes)})
        enviados += 1
    db.commit()
    return enviados


def rodar() -> None:
    """Uma passada. A cada 6h: os dias de antecedência são conferidos pela DATA,
    então rodar mais de uma vez no dia não duplica (o carimbo impede) e rodar
    poucas vezes não deixa passar."""
    db = SessionLocal()
    try:
        n = avisar(db)
        if n:
            log.info("creche: %d lembrete(s) de entrega mensal enviado(s)", n)
    except Exception:
        # Um erro aqui não pode derrubar o loop: amanhã tem outra passada, e o
        # worker morto seria silêncio — o modo de falha que mais custou aqui.
        log.exception("creche: falha ao enviar lembretes")
    finally:
        db.close()


if __name__ == "__main__":
    # Uma passada e sai: quem repete é o `while true; do … sleep N; done` do
    # compose, como fazem `expurgo`, `alertas_telemetria` e os demais. Loop
    # dentro do worker criaria DOIS relógios para a mesma coisa.
    logging.basicConfig(level=logging.INFO)
    rodar()
