"""Envia os logs dos serviços por e-mail, 4x ao dia (v2.29).

Decisão do Bruno em 2026-07-30: *"não precisa guardar, envie os logs 4x por
dia, distribuídos ao longo do dia para um e-mail que irei informar no front"*.

O worker roda **de hora em hora** e só envia quando entra numa janela nova
(00h, 06h, 12h, 18h UTC). Não é desperdício: é o que faz reinício de container
não duplicar nem pular envio — a janela já enviada fica registrada na config,
então subir o container cinco vezes na mesma hora manda um e-mail só, e um
container que ficou fora do ar às 12h ainda manda ao voltar.

Rode à mão: python -m app.workers.logs_email
"""

import logging

from app.core.db import SessionLocal
from app.services import logs as svc
from app.services.config_dinamica import gravar_config, ler_config
from app.services.notificacoes import avisar_modelo

log = logging.getLogger(__name__)

CHAVE_ULTIMA = "logs_ultima_janela_enviada"
# Teto por anexo. Acima disso o e-mail é recusado pelo provedor e ninguém
# recebe NADA — melhor cortar e avisar no corpo do que perder o envio inteiro.
MAX_ANEXO_BYTES = 4 * 1024 * 1024


def _fmt_janela(janela: str) -> str:
    """`2026-07-30T12` → `30/07/2026 12h–18h`, que é como se lê num assunto."""
    try:
        dia, hora = janela.split("T")
        a, m, d = dia.split("-")
        h = int(hora)
        return f"{d}/{m}/{a} {h:02d}h–{(h + 6) % 24:02d}h"
    except Exception:
        return janela


def rodar(forcar: bool = False) -> int:
    """Envia o pacote da janela corrente. Devolve 1 se enviou, 0 se não havia
    o que fazer. `forcar=True` ignora a janela (é o botão "enviar agora")."""
    janela = svc.janela_atual()
    with SessionLocal() as db:
        try:
            if not forcar:
                ultima = ler_config(db, (CHAVE_ULTIMA,)).get(CHAVE_ULTIMA)
                if ultima == janela:
                    return 0

            servicos = svc.servicos()
            if not servicos:
                # Sem arquivo nenhum: ou os logs em arquivo não subiram, ou é a
                # primeira volta. Não manda e-mail vazio, mas também não marca a
                # janela — assim a próxima volta tenta de novo.
                log.info("nenhum arquivo de log encontrado; nada a enviar")
                return 0

            resumo, anexos = [], []
            for nome in servicos:
                dados = svc.ler(nome, limite=svc.MAX_LINHAS_LEITURA)
                linhas = dados.get("linhas", [])
                r = svc._resumo(linhas)
                resumo.append(f"{nome}: {r['total']} linha(s) · "
                              f"{r['erros']} erro(s) · {r['avisos']} aviso(s)")
                try:
                    bruto = svc.texto_para_download(nome)
                except Exception:
                    continue
                if len(bruto) > MAX_ANEXO_BYTES:
                    # Corta pelo FIM: o que interessa é o mais recente.
                    bruto = (b"[... arquivo cortado: veja o completo em "
                             b"Configuracoes -> Logs dos servicos ...]\n"
                             + bruto[-MAX_ANEXO_BYTES:])
                anexos.append((f"{nome}.txt", bruto))

            enviados = avisar_modelo(
                db, "logs_periodico", "aviso_logs_periodico",
                {"janela": _fmt_janela(janela), "resumo": "\n".join(resumo)},
                anexos=anexos)
            # Marca a janela mesmo com 0 destinatários: se o evento está
            # desligado na matriz, insistir de hora em hora só encheria o log.
            gravar_config(db, {CHAVE_ULTIMA: janela})
            db.commit()
            log.info("logs da janela %s enviados para %s destinatário(s)",
                     janela, enviados)
            return 1
        except Exception:
            db.rollback()
            # Envio de log que falha não pode derrubar o worker — é diagnóstico,
            # não operação. Mesma regra do `avisar()`.
            log.exception("falha ao enviar os logs por e-mail")
            return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    rodar()
