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


def test_pessoa_na_listagem():
    """A tela geral tem que dizer de QUEM é o evento (v2.36).

    A telemetria é identificada desde a v2.24 e o vínculo era gravado — mas a
    listagem nunca devolvia o nome, então o RH via o erro e não sabia a quem
    telefonar. E o nome vem em LOTE: uma consulta por linha transformaria a
    aba num gargalo justamente quando há muito evento, que é quando ela importa.
    """
    print("\n[pessoa na listagem]")
    from sqlalchemy import event

    from app.core.db import engine
    from app.models.talento import Talento

    db = SessionLocal()
    try:
        marca = f"pessoa-{uuid.uuid4().hex[:8]}"
        cand = Candidato(nome_completo="Fulano da Telemetria",
                         email=f"{uuid.uuid4().hex[:8]}@exemplo.com",
                         status=StatusCandidato.convidado)
        talento = Talento(nome="Sicrana do Banco",
                          email=f"{uuid.uuid4().hex[:8]}@exemplo.com",
                          cargo_interesse="analista")
        db.add_all([cand, talento])
        db.flush()

        tel.registrar_eventos(db, [{"evento": marca}], origem="candidato",
                              candidato_id=cand.id)
        tel.registrar_eventos(db, [{"evento": marca}], origem="talento",
                              talento_id=talento.id)
        tel.registrar_eventos(db, [{"evento": marca}], origem="publico")
        tel.registrar_eventos(db, [{"evento": marca}], origem="rh",
                              usuario_rh="rh@exemplo.com")
        db.commit()

        eventos = tel.listar(db, evento=marca, limite=50)
        # `.get`: sem isto, remover o nome da listagem quebraria com KeyError em
        # vez de dizer qual garantia caiu.
        nomes = {e.get("pessoa") for e in eventos}
        checar("Fulano da Telemetria" in nomes, "o candidato aparece pelo nome")
        checar("Sicrana do Banco" in nomes, "o talento aparece pelo nome")
        checar("rh@exemplo.com" in nomes,
               "evento do painel mostra o usuário do RH em vez de ficar sem dono")
        checar(any(e.get("pessoa") is None for e in eventos),
               "visita pública continua ANÔNIMA — identificar quem não se "
               "identificou seria inventar vínculo")
        tipos = {e.get("pessoa"): e.get("pessoa_tipo") for e in eventos}
        checar(tipos.get("Fulano da Telemetria") == "candidato"
               and tipos.get("Sicrana do Banco") == "talento",
               "o tipo distingue candidato de talento (a ficha só abre para um)")

        # Sem N+1: a diferença de consultas não pode acompanhar a de linhas.
        # Medir com limite absoluto mediria o tamanho do banco, que cresce a
        # cada execução — por isso compara-se DUAS listagens (v2.15).
        contador = {"n": 0}

        def _contar(*_a, **_kw):
            contador["n"] += 1

        event.listen(engine, "before_cursor_execute", _contar)
        try:
            contador["n"] = 0
            tel.listar(db, evento=marca, limite=1)
            poucas = contador["n"]
            contador["n"] = 0
            tel.listar(db, evento=marca, limite=50)
            muitas = contador["n"]
        finally:
            event.remove(engine, "before_cursor_execute", _contar)
        checar(muitas <= poucas + 1 and muitas <= 3,
               "consultas não crescem com o número de linhas — são 3 no total "
               f"(eventos + candidatos + talentos): {poucas} para {muitas}")
    finally:
        db.rollback()
        db.close()


def test_talento_so_com_prova():
    """Vincular evento a um talento exige PROVA, não um id digitado (v2.36).

    A rota de coleta é pública. Aceitar `talento_id` cru deixaria qualquer um
    escrever na jornada de outra pessoa — e o RH leria aquilo como o
    comportamento dela, que é pior do que não ter registro nenhum.
    """
    print("\n[talento identificado só com prova]")
    from fastapi.testclient import TestClient

    from app.api.talentos import talento_do_upload_token
    from app.main import app

    c = TestClient(app)
    marca = f"talento-tel-{uuid.uuid4().hex[:8]}"
    r = c.post("/api/talentos", json={
        "nome": "Talento da Telemetria", "email": f"{uuid.uuid4().hex[:8]}@exemplo.com",
        "cargos_interesse": ["Auxiliar de Serviços Gerais"], "consentimento_lgpd": True})
    checar(r.status_code == 201, f"cadastro público criado ({r.status_code})")
    tid, upload_token = r.json().get("id"), r.json().get("upload_token")

    checar(str(talento_do_upload_token(upload_token)) == str(tid),
           "o token do cadastro prova de quem é")
    checar(talento_do_upload_token("nada-disso") is None,
           "token forjado não identifica ninguém")
    checar(talento_do_upload_token(None) is None, "sem token, sem identificação")

    c.post("/api/telemetria", json={"eventos": [{"evento": marca}],
                                    "talento_token": upload_token})
    # id CRU: é o que um curioso mandaria. O campo nem existe mais no contrato.
    c.post("/api/telemetria", json={"eventos": [{"evento": f"{marca}-cru"}],
                                    "talento_id": tid})
    c.post("/api/telemetria", json={"eventos": [{"evento": f"{marca}-falso"}],
                                    "talento_token": "assinatura-invalida"})

    db = SessionLocal()
    try:
        por_evento = {e.evento: e for e in
                      db.query(EventoTelemetria)
                      .filter(EventoTelemetria.evento.like(f"{marca}%")).all()}
        com_prova = por_evento.get(marca)
        checar(com_prova is not None and str(com_prova.talento_id) == str(tid),
               "com o token do cadastro, o evento fica ligado à pessoa")
        checar(com_prova is not None and com_prova.origem == "talento",
               "e a origem passa a ser o Banco de Talentos")
        cru = por_evento.get(f"{marca}-cru")
        checar(cru is not None and cru.talento_id is None,
               "id cru NÃO vincula — o evento é registrado, mas de ninguém")
        falso = por_evento.get(f"{marca}-falso")
        checar(falso is not None and falso.talento_id is None,
               "token forjado também não vincula")
    finally:
        db.close()


def test_export_jornada():
    """O CSV de jornada é CRONOLÓGICO e diz quando cortou (v2.36)."""
    print("\n[export de jornada]")
    db = SessionLocal()
    try:
        cand = Candidato(nome_completo="Zezinho da Jornada",
                         email=f"{uuid.uuid4().hex[:8]}@exemplo.com",
                         status=StatusCandidato.convidado)
        db.add(cand)
        db.flush()
        marca = f"jornada-{uuid.uuid4().hex[:8]}"
        for i in range(3):
            tel.registrar_eventos(db, [{"evento": f"{marca}-{i}"}],
                                  origem="candidato", candidato_id=cand.id)
            db.flush()
        db.commit()

        csv_txt, linhas, truncado = tel.jornada_csv(db, dias=1)
        cabecalho = csv_txt.lstrip("﻿").splitlines()[0]
        checar(cabecalho.startswith("user_id;event;timestamp"),
               "as três primeiras colunas são as que as ferramentas de análise "
               "de caminho esperam")
        checar(csv_txt.startswith("﻿"), "tem BOM — abre no Excel-BR sem acento quebrado")
        checar(f"candidato:{cand.id}" in csv_txt,
               "o user_id é a PESSOA quando ela é conhecida")
        checar("Zezinho da Jornada" in csv_txt, "o nome vai junto, para leitura humana")

        posicoes = [csv_txt.index(f"{marca}-{i}") for i in range(3)]
        checar(posicoes == sorted(posicoes),
               "a ordem é CRESCENTE no tempo — jornada ao contrário não é jornada")
        checar(not truncado and linhas > 0, f"{linhas} linhas, sem corte")

        # Corte: o teto é sinalizado, nunca silencioso.
        _, poucas, cortou = tel.jornada_csv(db, dias=1, limite=2)
        checar(poucas == 2 and cortou,
               "quando o período tem mais que o teto, o corte é ANUNCIADO — "
               "senão o RH analisaria um pedaço achando que é o todo")
    finally:
        db.rollback()
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
    test_pessoa_na_listagem()
    test_talento_so_com_prova()
    test_export_jornada()

    print()
    if FALHAS:
        print(f"test_telemetria: {len(FALHAS)} FALHA(S)")
        for f in FALHAS:
            print(f"  - {f}")
        sys.exit(1)
    print("test_telemetria: OK")
