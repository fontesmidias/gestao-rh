"""Logs dos serviços em ARQUIVO — legíveis no painel, sem SSH (v2.29).

Pedido do Bruno em 2026-07-30, no dia em que o log foi a única forma de achar
uma colaboradora travada há seis horas: *"não seria o caso todos os logs de
cada serviço ficarem armazenados em um arquivo separadamente, de modo que eu
possa lê-los a qualquer momento, sem a necessidade de dar comandos no terminal
SSH"*.

O motivo é concreto e já cobrou: **o log do container morre no restart**. Se o
incidente do Defender (v2.28) tivesse acontecido um dia antes, não haveria
rastro nenhum — e o diagnóstico dependeu de ler exatamente aquelas linhas.

## Por que arquivo, e não o socket do Docker

Ler `docker logs` de dentro da API exigiria montar `/var/run/docker.sock` no
container. Isso dá à API **controle total do Docker do host**: quem
comprometesse a API assumiria a VPS inteira, e a API é justamente o que está
exposto à internet. Num sistema com dado de RH, isso não se faz por
conveniência de leitura. Cada serviço escreve o PRÓPRIO arquivo num volume
compartilhado; o painel lê os arquivos.

Consequência aceita: só aparecem aqui os serviços NOSSOS (api, worker,
alertas, expurgo). Postgres e MinIO seguem no `docker logs` — eles quase nunca
são a pergunta, e o custo de segurança não compensa.

## LGPD

Estas linhas contêm CPF, e-mail e nome (foi o CPF completo no log que permitiu
achar a Keli). Antes eram voláteis; em arquivo, viram **dado pessoal
armazenado**. Por isso a retenção é configurável no painel — decisão do Bruno
de 2026-07-30 —, e `0` significa "guardar por tempo indeterminado", escolha
consciente dele. O expurgo roda no worker diário junto com os demais.
"""

from __future__ import annotations

import logging
import os
import re
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path

log = logging.getLogger(__name__)

# Onde os arquivos moram. Volume compartilhado entre api e workers; em
# desenvolvimento cai numa pasta local, sem exigir configuração.
DIR_LOGS = Path(os.getenv("LOG_DIR", "/var/log/gestao-rh"))

# Nome do serviço que está escrevendo. Cada container define o seu — é o que
# separa os arquivos e alimenta o seletor da tela.
SERVICO = os.getenv("LOG_SERVICO", "api")

RETENCAO_PADRAO_DIAS = 7
# 0 = indeterminado (o Bruno pediu essa opção explicitamente). Teto alto para
# não travar quem quiser guardar muito, mas ainda finito quando NÃO é 0.
RETENCAO_MAX_DIAS = 3650

# Teto de leitura: o painel nunca carrega um arquivo inteiro na memória.
MAX_LINHAS_LEITURA = 5000


def _arquivo_do(servico: str, dia: date | None = None) -> Path:
    """`api.log` para o de hoje; `api.log.2026-07-30` para os rotacionados —
    é o sufixo que o `TimedRotatingFileHandler` usa."""
    base = DIR_LOGS / f"{servico}.log"
    return base if dia is None else Path(f"{base}.{dia.isoformat()}")


# Fuso de Brasília, sempre — a mesma decisão que o front já seguia desde
# 2026-07-16 (`fmt.js`). O container roda em UTC, então o log saía três horas
# adiantado: quem lê a tela às 14h procurava "14:" no arquivo e encontrava as
# 11h. Numa investigação isso não é detalhe — é a diferença entre achar e não
# achar a linha, e pior, entre achá-la e concluir que foi outro momento.
TZ_BRASILIA = ZoneInfo("America/Sao_Paulo")


class _FormatadorBrasilia(logging.Formatter):
    """Carimba a hora local de Brasília, com o deslocamento explícito.

    O `-03` no fim não é enfeite: o arquivo é baixado e enviado por e-mail, e
    sem ele ninguém sabe se aquela hora já foi convertida ou não.
    """

    def formatTime(self, record, datefmt=None):  # noqa: N802 (assinatura da stdlib)
        quando = datetime.fromtimestamp(record.created, tz=TZ_BRASILIA)
        return quando.strftime(datefmt or "%Y-%m-%d %H:%M:%S %z")


def configurar(servico: str | None = None) -> None:
    """Liga a escrita em arquivo, ao lado do stdout (que continua existindo —
    `docker logs` segue funcionando e é a rede de segurança se o volume falhar).

    NUNCA levanta: log é diagnóstico, não pode derrubar o processo que o emite.
    Volume somente-leitura, disco cheio ou permissão errada degradam para
    "só stdout", com um aviso no próprio stdout.
    """
    nome = servico or SERVICO
    try:
        DIR_LOGS.mkdir(parents=True, exist_ok=True)
        handler = TimedRotatingFileHandler(
            _arquivo_do(nome), when="midnight", backupCount=0, encoding="utf-8")
        # backupCount=0: quem apaga é o expurgo, que respeita a retenção
        # configurada no painel (inclusive "indeterminado"). Deixar o handler
        # apagar sozinho ignoraria a escolha do RH.
        handler.suffix = "%Y-%m-%d"
        # `req` e `ator` em TODA linha (v2.41): é o que liga um erro solto à
        # requisição e à pessoa que o provocou. Sem eles, o log tinha volume e
        # não tinha rastro — dez pessoas usando ao mesmo tempo viravam um
        # emaranhado só. O filtro os injeta sozinho; nenhum call-site muda.
        from app.services.contexto_log import FiltroContexto
        handler.addFilter(FiltroContexto())
        handler.setFormatter(_FormatadorBrasilia(
            "%(asctime)s %(levelname)s %(name)s req=%(req)s ator=%(ator)s %(message)s"))
        raiz = logging.getLogger()
        # Idempotente: reconfigurar não duplica linha (o entrypoint pode chamar
        # mais de uma vez, e log duplicado atrapalha justamente na hora do aperto)
        for h in list(raiz.handlers):
            if isinstance(h, TimedRotatingFileHandler):
                raiz.removeHandler(h)
        raiz.addHandler(handler)
        # Sem isto, o arquivo só recebe WARNING para cima: o nível vinha do
        # `basicConfig` do `main.py`, que os WORKERS não importam — então tudo
        # que expurgo, alertas e vencimentos registram com `log.info` ("X
        # arquivos expurgados", "alerta disparado") nunca chegava ao arquivo.
        # Justamente o que o Bruno queria poder investigar. `NOTSET` significa
        # "herda", e o padrão herdado é WARNING.
        if raiz.level in (logging.NOTSET, logging.WARNING):
            raiz.setLevel(logging.INFO)
        log.info("Logs em arquivo: %s", _arquivo_do(nome))
    except Exception:
        log.exception("Não foi possível abrir o log em arquivo — seguindo só no stdout")


def servicos() -> list[str]:
    """Serviços que têm arquivo hoje ou em algum dia guardado."""
    try:
        nomes = {p.name.split(".log")[0] for p in DIR_LOGS.glob("*.log*")}
        return sorted(n for n in nomes if n)
    except Exception:
        return []


def dias_disponiveis(servico: str) -> list[str]:
    """Dias com arquivo, mais recente primeiro. 'hoje' é o arquivo corrente."""
    saida = []
    try:
        if _arquivo_do(servico).exists():
            saida.append(date.today().isoformat())
        for p in DIR_LOGS.glob(f"{servico}.log.*"):
            sufixo = p.name.rsplit(".", 1)[-1]
            if re.fullmatch(r"\d{4}-\d{2}-\d{2}", sufixo):
                saida.append(sufixo)
    except Exception:
        return []
    return sorted(set(saida), reverse=True)


def _caminho(servico: str, dia: str | None) -> Path:
    """Resolve serviço+dia num caminho DENTRO de DIR_LOGS.

    Os dois vêm da URL, então são entrada não confiável: `servico` só pode ter
    letras/dígitos/hífen e `dia` tem que ser uma data ISO. Sem isso,
    `../../etc/passwd` viraria leitura de arquivo do sistema — é a mesma regra
    do `export_planilha.slug()` para nome de arquivo em export.
    """
    if not re.fullmatch(r"[a-z0-9_-]{1,40}", servico or ""):
        raise ValueError("servico_invalido")
    if dia:
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", dia):
            raise ValueError("dia_invalido")
        if dia == date.today().isoformat():
            return _arquivo_do(servico)
        return _arquivo_do(servico, date.fromisoformat(dia))
    return _arquivo_do(servico)


def ler(servico: str, *, dia: str | None = None, busca: str | None = None,
        nivel: str | None = None, limite: int = 500) -> dict:
    """Últimas linhas do serviço, com filtro por texto e por nível.

    Lê do FIM para o começo: o que interessa num diagnóstico é o que acabou de
    acontecer, e um arquivo de um dia movimentado não cabe na memória.
    """
    caminho = _caminho(servico, dia)
    if not caminho.exists():
        return {"servico": servico, "dia": dia, "linhas": [], "total": 0,
                "truncado": False}
    limite = max(1, min(limite, MAX_LINHAS_LEITURA))
    # Vários termos separados por espaço: a linha precisa conter TODOS (v2.41).
    # É o que permite cruzar perguntas — "email.envio creche" acha os e-mails do
    # creche, "ERROR ator=candidato" acha os erros que atingiram candidatos.
    # Um termo só se comporta exatamente como antes.
    termos = [t for t in (busca or "").lower().split() if t]
    niveis = {"ERROR": ("ERROR", "CRITICAL"), "WARNING": ("WARNING", "ERROR", "CRITICAL")}
    prefixos = niveis.get((nivel or "").upper())

    linhas: list[str] = []
    lidas = 0
    try:
        with caminho.open("r", encoding="utf-8", errors="replace") as fh:
            for linha in fh:
                lidas += 1
                if prefixos and not any(f" {p} " in linha for p in prefixos):
                    continue
                if termos:
                    minuscula = linha.lower()
                    if not all(t in minuscula for t in termos):
                        continue
                linhas.append(linha.rstrip("\n"))
                # Janela deslizante: segura só o que vai devolver, em vez de
                # carregar o arquivo inteiro para depois cortar.
                if len(linhas) > limite:
                    del linhas[0]
    except Exception:
        log.exception("Falha ao ler o log de %s", servico)
        return {"servico": servico, "dia": dia, "linhas": [], "total": 0,
                "truncado": False, "erro": "leitura_falhou"}
    return {"servico": servico, "dia": dia, "linhas": linhas,
            "total": len(linhas), "lidas": lidas,
            "truncado": lidas > len(linhas)}


def texto_para_download(servico: str, dia: str | None = None) -> bytes:
    """Arquivo inteiro, para o botão de baixar em .txt."""
    caminho = _caminho(servico, dia)
    if not caminho.exists():
        raise FileNotFoundError(servico)
    return caminho.read_bytes()


def retencao_dias(db) -> int:
    """Dias de retenção configurados. **0 = indeterminado** (não expurga) —
    opção pedida pelo Bruno em 2026-07-30."""
    from app.services.config_dinamica import ler_config
    try:
        bruto = ler_config(db, ("logs_retencao_dias",)).get("logs_retencao_dias")
        if bruto in (None, ""):
            return RETENCAO_PADRAO_DIAS
        valor = int(bruto)
        if valor <= 0:
            return 0
        return min(valor, RETENCAO_MAX_DIAS)
    except Exception:
        return RETENCAO_PADRAO_DIAS


def expurgar(dias: int) -> int:
    """Apaga arquivos rotacionados mais velhos que `dias`. `0` não apaga nada.

    Só toca em arquivo com sufixo de DATA — o log corrente (`api.log`) nunca é
    removido, senão o serviço perderia o arquivo aberto no meio da escrita.
    """
    if dias <= 0:
        return 0
    corte = date.today() - timedelta(days=dias)
    apagados = 0
    try:
        for p in DIR_LOGS.glob("*.log.*"):
            sufixo = p.name.rsplit(".", 1)[-1]
            if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", sufixo):
                continue
            if date.fromisoformat(sufixo) < corte:
                p.unlink(missing_ok=True)
                apagados += 1
    except Exception:
        log.exception("Falha ao expurgar logs antigos")
    return apagados


# ---------------------------------------------------------------------------
# Envio por e-mail — 4x ao dia (decisão do Bruno: "não precisa guardar, envie
# os logs 4x por dia, distribuídos ao longo do dia").
# ---------------------------------------------------------------------------

# 4 janelas de 6h. O worker roda de hora em hora e só dispara quando entra numa
# janela nova, então reinício de container não duplica nem pula envio.
JANELAS_H = (0, 6, 12, 18)


def janela_atual(agora: datetime | None = None) -> str:
    a = agora or datetime.now(timezone.utc)
    inicio = max(h for h in JANELAS_H if h <= a.hour)
    return f"{a.date().isoformat()}T{inicio:02d}"


def _resumo(linhas: list[str]) -> dict:
    erros = sum(1 for x in linhas if " ERROR " in x or " CRITICAL " in x)
    avisos = sum(1 for x in linhas if " WARNING " in x)
    return {"total": len(linhas), "erros": erros, "avisos": avisos}
