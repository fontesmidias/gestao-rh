"""Telemetria de uso (v2.24) — as garantias que não podem regredir.

Nasceu do incidente de 2026-07-29 (tela em branco no candidato, invisível nos
logs). O que se testa aqui não é "o código roda", e sim as promessas que
sustentam o módulo: que ele NÃO derruba a ação do usuário, que NÃO guarda dado
sensível e que o resumo AGRUPA em vez de despejar.

Rode: PYTHONPATH=. .venv/Scripts/python.exe tests/test_telemetria.py
"""

import os
import sys
import uuid
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault(
    "DATABASE_URL", "postgresql+psycopg://admissao:admissao@localhost:55432/admissao")

from app.core.db import SessionLocal  # noqa: E402
from app.models.candidato import Candidato, StatusCandidato  # noqa: E402
from app.models.telemetria import EventoTelemetria  # noqa: E402
from app.services import telemetria as tel  # noqa: E402

FALHAS = []


def checar(condicao, descricao):
    if condicao:
        print(f"  ok   {descricao}")
    else:
        print(f"  FALHA {descricao}")
        FALHAS.append(descricao)


def test_mascara_token_da_pagina():
    """O token do link mágico é CREDENCIAL — não pode virar linha de tabela.

    Quem tem o token entra na admissão da pessoa. A telemetria é feita para ser
    lida e exportada, então gravar o token criaria uma planilha de chaves de
    acesso.
    """
    print("\n[mascaramento do token]")
    m = tel.mascarar_pagina("/c/uB0jq1m9hdmDNFygDg1p17IADXmj39ZHUDmiqrYMcY0")
    checar("uB0jq1" in m and "39ZHUDmiqrYMcY0" not in m,
           "token do candidato é mascarado, mas o prefixo fica para correlação")
    # Token real do itsdangerous: longo e com caixa mista.
    checar(tel.mascarar_pagina("/t/kmS1Msdeh8fhW9-uLpTj8URpWNtnBNsnK3awMgpngdM").endswith("***"),
           "token de testagem também é mascarado")
    checar(tel.mascarar_pagina("/rh/talentos") == "/rh/talentos",
           "página do painel passa intacta (não tem token)")
    checar(tel.mascarar_pagina(None) is None, "página nula não quebra")

    # NOME DE ETAPA não é token. Sem esta distinção, `/c/assinatura` virava
    # `/c/assina***` e o MESMO erro aparecia duas vezes no alerta, uma por
    # grafia — agrupar errado infla a contagem e esconde o padrão.
    for etapa in ("/c/assinatura", "/c/documentos", "/c/formulario", "/c/acompanhamento"):
        checar(tel.mascarar_pagina(etapa) == etapa,
               f"'{etapa}' é nome de etapa e passa intacto")

    # A garantia que importa de verdade: o mascaramento é APLICADO na gravação.
    # Testar só a função deixaria passar alguém que a removesse do caminho —
    # pego numa validação por mutação.
    db = SessionLocal()
    try:
        marca = f"token-{uuid.uuid4().hex[:8]}"
        token_falso = "SEGREDOsegredoSEGREDOsegredo123"
        tel.registrar_eventos(db, [{"evento": marca, "pagina": f"/c/{token_falso}"}],
                              origem="candidato")
        db.commit()
        ev = db.query(EventoTelemetria).filter_by(evento=marca).first()
        checar(ev is not None and token_falso not in (ev.pagina or ""),
               "o token NÃO é gravado no banco — mascaramento aplicado na entrada")
    finally:
        db.rollback()
        db.close()


def test_ip_truncado():
    """Só o prefixo do IP: distingue operadora sem localizar a pessoa."""
    print("\n[minimização do IP]")
    checar(tel.ip_prefixo("191.180.44.12") == "191.180.x.x",
           "IPv4 guarda só os dois primeiros octetos")
    checar(tel.ip_prefixo("2804:14d:5c81::1").endswith(":x:x"),
           "IPv6 guarda só os dois primeiros grupos")
    checar(tel.ip_prefixo(None) is None, "IP ausente não quebra")
    checar(tel.ip_prefixo("lixo") is None, "IP inválido não vira lixo na tabela")


def test_nunca_levanta():
    """A promessa central: telemetria que falha NÃO derruba a ação do usuário.

    Mesma regra do `avisar()` em notificacoes.py. Se registrar um evento pudesse
    quebrar o envio de um documento, o remédio seria pior que a doença.
    """
    print("\n[nunca levanta]")
    db = SessionLocal()
    try:
        n = tel.registrar_eventos(db, [{"evento": "x"}], origem="origem_que_nao_existe")
        checar(n == 0, "origem desconhecida devolve 0 em vez de levantar")

        n = tel.registrar_eventos(db, [None, "texto solto", 42, {"sem": "nome"}],
                                  origem="publico")
        checar(n == 0, "lote com lixo não grava nada e não levanta")

        n = tel.registrar_eventos(db, [], origem="publico")
        checar(n == 0, "lote vazio é inofensivo")
    finally:
        db.rollback()
        db.close()


def test_teto_de_volume():
    """A rota é PÚBLICA: um laço no navegador não pode encher a tabela."""
    print("\n[teto de volume]")
    db = SessionLocal()
    try:
        n = tel.registrar_eventos(
            db, [{"evento": f"e{i}"} for i in range(500)], origem="publico")
        checar(n == tel.MAX_EVENTOS_LOTE,
               f"lote gigante é cortado em {tel.MAX_EVENTOS_LOTE} (veio {n})")

        n = tel.registrar_eventos(
            db, [{"evento": "grande", "detalhe": {"m": "x" * 99_999}}], origem="publico")
        ev = db.query(EventoTelemetria).filter_by(evento="grande").first()
        checar(ev is not None and len(ev.detalhe["m"]) <= tel.MAX_DETALHE_CHARS,
               "detalhe gigante é truncado, não estoura a coluna")

        tel.registrar_eventos(db, [{"evento": "relogio", "duracao_ms": 99_999_999_999}],
                              origem="publico")
        ev = db.query(EventoTelemetria).filter_by(evento="relogio").first()
        checar(ev is not None and ev.duracao_ms is None,
               "duração absurda (relógio errado do aparelho) vira nulo")
    finally:
        db.rollback()
        db.close()


def test_resumo_agrupa_erros():
    """300 ocorrências do mesmo erro são UM problema, não 300 linhas.

    É a lição direta do incidente: a lista crua esconderia o padrão atrás do
    volume, e foi justamente o padrão que faltou enxergar.
    """
    print("\n[resumo agrupa]")
    db = SessionLocal()
    try:
        marca = f"erro-teste-{uuid.uuid4().hex[:8]}"
        for _ in range(5):
            tel.registrar_eventos(db, [{
                "evento": marca, "tipo": "erro", "pagina": "/c/documentos",
                "detalhe": {"mensagem": "Cannot read properties of null"},
            }], origem="candidato")
        db.commit()

        r = tel.resumo(db, dias=1)
        linha = next((e for e in r["erros"] if e["evento"] == marca), None)
        checar(linha is not None, "o erro aparece no resumo")
        checar(linha and linha["ocorrencias"] == 5,
               f"as 5 ocorrências viram UMA linha com contagem 5 (veio {linha and linha['ocorrencias']})")
        checar(linha and linha["mensagem"] == "Cannot read properties of null",
               "a mensagem do erro é preservada — é o que identifica o defeito")
        checar(r["por_tipo"].get("erro", 0) >= 5, "o contador por tipo soma os erros")
    finally:
        db.rollback()
        db.close()


def test_expurgo_por_intervalo():
    """Os dois modos pedidos: retenção (antes_de) e cirúrgico (intervalo)."""
    print("\n[expurgo]")
    db = SessionLocal()
    try:
        marca = f"expurgo-{uuid.uuid4().hex[:8]}"
        tel.registrar_eventos(db, [{"evento": marca}], origem="publico")
        db.commit()
        antes = db.query(EventoTelemetria).filter_by(evento=marca).count()
        checar(antes == 1, "evento gravado para o teste")

        # Sem intervalo nenhum não apaga NADA: um clique distraído não pode
        # levar a base inteira.
        checar(tel.expurgar(db) == 0, "expurgo sem intervalo não apaga nada")

        agora = datetime.now(timezone.utc)
        n = tel.expurgar(db, desde=agora - timedelta(minutes=5), ate=agora + timedelta(minutes=5))
        db.commit()
        checar(n >= 1, f"expurgo por intervalo apagou {n} evento(s)")
        checar(db.query(EventoTelemetria).filter_by(evento=marca).count() == 0,
               "o evento do intervalo saiu de verdade")
    finally:
        db.rollback()
        db.close()


def test_telemetria_da_pessoa():
    """O pedido literal: abrir a ficha de alguém e ver o que aconteceu com ELA."""
    print("\n[telemetria individualizada]")
    db = SessionLocal()
    try:
        cand = Candidato(nome_completo="Telemetria Teste",
                         email=f"tel-{uuid.uuid4().hex[:8]}@example.com",
                         status=StatusCandidato.convidado, cargo_funcao="Vigia")
        db.add(cand)
        db.flush()

        tel.registrar_eventos(db, [
            {"evento": "etapa_aberta", "pagina": "/c/documentos"},
            {"evento": "documento_reenviado", "tipo": "friccao"},
        ], origem="candidato", candidato_id=cand.id)
        db.commit()

        eventos = tel.da_pessoa(db, candidato_id=cand.id)
        checar(len(eventos) == 2, f"os 2 eventos da pessoa voltam (vieram {len(eventos)})")
        checar(all(e["candidato_id"] == cand.id for e in eventos),
               "todos pertencem à pessoa certa")

        outro = tel.da_pessoa(db, candidato_id=uuid.uuid4())
        checar(outro == [], "pessoa sem eventos devolve lista vazia, não erro")
        checar(tel.da_pessoa(db) == [], "sem identificação nenhuma devolve vazio")
    finally:
        db.rollback()
        db.close()


def test_retencao_configuravel():
    """Padrão de 1 ano (escolha do Bruno) e limites sãos."""
    print("\n[retenção]")
    db = SessionLocal()
    try:
        checar(tel.RETENCAO_PADRAO_DIAS == 365, "o padrão é 1 ano")
        checar(1 <= tel.retencao_dias(db) <= 3650,
               "a retenção lida fica dentro dos limites")
    finally:
        db.close()


if __name__ == "__main__":
    test_mascara_token_da_pagina()
    test_ip_truncado()
    test_nunca_levanta()
    test_teto_de_volume()
    test_resumo_agrupa_erros()
    test_expurgo_por_intervalo()
    test_telemetria_da_pessoa()
    test_retencao_configuravel()

    print()
    if FALHAS:
        print(f"test_telemetria: {len(FALHAS)} FALHA(S)")
        for f in FALHAS:
            print(f"  - {f}")
        sys.exit(1)
    print("test_telemetria: OK")
