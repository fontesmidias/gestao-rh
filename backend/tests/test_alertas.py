"""Alertas de telemetria (v2.25) — as garantias que sustentam o recurso.

O valor de um alerta está inteiro na CONFIANÇA que ele merece: se manda demais,
ninguém lê; se manda de menos, não serve. Estes testes cobrem exatamente as
promessas que decidem isso — dedup, silêncio, agrupamento e o modo teste que
não estraga o alerta real.

Rode: PYTHONPATH=. .venv/Scripts/python.exe tests/test_alertas.py
"""

import os
import sys
import uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault(
    "DATABASE_URL", "postgresql+psycopg://admissao:admissao@localhost:55432/admissao")

from app.core.db import SessionLocal  # noqa: E402
from app.models.alerta import AlertaEnviado, RegraAlerta  # noqa: E402
from app.models.telemetria import EventoTelemetria  # noqa: E402
from app.services import alertas  # noqa: E402
from app.services import telemetria as tel  # noqa: E402

FALHAS = []


def checar(condicao, descricao):
    if condicao:
        print(f"  ok   {descricao}")
    else:
        print(f"  FALHA {descricao}")
        FALHAS.append(descricao)


def limpar(db):
    """Ambiente limpo: alerta depende de histórico, e resíduo falsearia tudo."""
    db.query(EventoTelemetria).delete()
    db.query(AlertaEnviado).delete()
    db.query(RegraAlerta).delete()
    db.commit()


def erro(db, mensagem, pagina="/c/assinatura", sessao="s1", origem="candidato"):
    tel.registrar_eventos(db, [{
        "evento": "erro_render", "tipo": "erro", "pagina": pagina,
        "detalhe": {"mensagem": mensagem},
    }], origem=origem, sessao=sessao)


def test_erro_novo_dispara_uma_vez():
    """O cenário de 2026-07-29 — e a promessa de não virar enxurrada."""
    print("\n[erro novo]")
    db = SessionLocal()
    try:
        limpar(db)
        db.add(RegraAlerta(tipo="erro_novo", nome="Erro novo", limiar=1,
                           janela_min=60, silencio_min=60))
        db.commit()

        for i in range(3):
            erro(db, "Cannot read properties of null (reading 'some')", sessao=f"s{i}")
        db.commit()

        d = alertas.avaliar(db, enviar=False)
        checar(len(d) == 1, f"a regra disparou (veio {len(d)})")
        checar(d and d[0]["total"] == 1,
               "as 3 ocorrências viram UM item — é um problema, não três")
        checar(d and d[0]["itens"][0]["n"] == 3 and d[0]["itens"][0]["pessoas"] == 3,
               "o item traz a contagem (3x) e quantas pessoas (3)")

        # Envia de verdade e confere o dedup.
        alertas.avaliar(db, enviar=True)
        db.commit()
        checar(alertas.avaliar(db, enviar=False) == [],
               "na 2ª verificação NÃO dispara de novo — dedup por assinatura")

        # Erro DIFERENTE dispara mesmo dentro do silêncio do primeiro: o
        # silêncio é por problema, não global.
        erro(db, "outro erro completamente diferente")
        db.commit()
        checar(len(alertas.avaliar(db, enviar=False)) == 1,
               "um erro DIFERENTE dispara mesmo com o outro em silêncio")

        # "NOVO" é para sempre, não pela janela de silêncio — a garantia
        # específica deste tipo. Envelhecendo o histórico além do silêncio, o
        # `_ja_avisado` deixa de proteger e só o `_ja_visto_alguma_vez` segura;
        # sem ele, um erro já conhecido voltaria a ser anunciado como novidade
        # de hora em hora, para sempre. (Sem este caso, remover a checagem de
        # "já visto" passava no teste — lacuna achada por mutação.)
        alertas.avaliar(db, enviar=True)
        db.commit()
        from datetime import timedelta as _td
        for reg in db.query(AlertaEnviado).all():
            reg.criado_em = reg.criado_em - _td(days=30)
        db.commit()
        checar(alertas.avaliar(db, enviar=False) == [],
               "erro já avisado há 30 dias NÃO volta como 'novo'")
    finally:
        limpar(db)
        db.close()


def test_modo_teste_nao_estraga_o_alerta_real():
    """`enviar=False` não pode consumir o histórico.

    Se o botão "testar" marcasse o erro como já visto, o problema REAL nunca
    mais avisaria — o recurso se sabotaria no primeiro uso da tela.
    """
    print("\n[modo teste é inócuo]")
    db = SessionLocal()
    try:
        limpar(db)
        db.add(RegraAlerta(tipo="erro_novo", nome="Erro novo", limiar=1,
                           janela_min=60, silencio_min=60))
        db.commit()
        erro(db, "erro que sera testado antes de valer")
        db.commit()

        alertas.avaliar(db, enviar=False)
        alertas.avaliar(db, enviar=False)
        checar(db.query(AlertaEnviado).count() == 0,
               "testar não grava histórico nenhum")
        checar(len(alertas.avaliar(db, enviar=True)) == 1,
               "depois de testar, o alerta REAL continua disparando")
    finally:
        limpar(db)
        db.close()


def test_limiar_de_volume():
    """Abaixo do limiar não avisa; no limiar, avisa."""
    print("\n[limiar de volume]")
    db = SessionLocal()
    try:
        limpar(db)
        db.add(RegraAlerta(tipo="erro_volume", nome="Volume", limiar=5,
                           janela_min=60, silencio_min=60))
        db.commit()

        for i in range(4):
            erro(db, "erro repetido", sessao=f"v{i}")
        db.commit()
        checar(alertas.avaliar(db, enviar=False) == [],
               "4 ocorrências com limiar 5 NÃO disparam")

        erro(db, "erro repetido", sessao="v5")
        db.commit()
        d = alertas.avaliar(db, enviar=False)
        checar(len(d) == 1, "a 5ª ocorrência dispara (limiar atingido)")
    finally:
        limpar(db)
        db.close()


def test_lentidao_usa_mediana():
    """Um caso isolado de lentidão não pode acordar ninguém.

    Alguém no elevador com uma barra de sinal não é problema do sistema. A
    mediana só passa do limiar quando a MAIORIA está esperando demais.
    """
    print("\n[lentidão por mediana]")
    db = SessionLocal()
    try:
        limpar(db)
        db.add(RegraAlerta(tipo="lentidao", nome="Lentidão", limiar=8000,
                           janela_min=60, silencio_min=60))
        db.commit()

        # 1 medição horrível + 4 ótimas: a média passaria de 8s, a mediana não.
        for ms in (40000, 500, 600, 550, 700):
            tel.registrar_eventos(db, [{
                "evento": "carregou", "tipo": "desempenho",
                "pagina": "/c/documentos", "duracao_ms": ms}], origem="candidato")
        db.commit()
        checar(alertas.avaliar(db, enviar=False) == [],
               "um caso isolado de 40s NÃO dispara (a média dispararia)")

        limpar(db)
        db.add(RegraAlerta(tipo="lentidao", nome="Lentidão", limiar=8000,
                           janela_min=60, silencio_min=60))
        db.commit()
        for _ in range(5):
            tel.registrar_eventos(db, [{
                "evento": "carregou", "tipo": "desempenho",
                "pagina": "/c/documentos", "duracao_ms": 12000}], origem="candidato")
        db.commit()
        checar(len(alertas.avaliar(db, enviar=False)) == 1,
               "quando a MAIORIA espera 12s, dispara")
    finally:
        limpar(db)
        db.close()


def test_filtro_por_origem():
    """Regra restrita a uma origem não é disparada por outra."""
    print("\n[filtro por origem]")
    db = SessionLocal()
    try:
        limpar(db)
        db.add(RegraAlerta(tipo="erro_novo", nome="Só candidato", limiar=1,
                           janela_min=60, silencio_min=60, origem="candidato"))
        db.commit()

        erro(db, "erro que veio do painel", origem="rh")
        db.commit()
        checar(alertas.avaliar(db, enviar=False) == [],
               "erro do painel NÃO dispara regra restrita a candidato")

        erro(db, "erro que veio do candidato", origem="candidato")
        db.commit()
        checar(len(alertas.avaliar(db, enviar=False)) == 1,
               "erro do candidato dispara")
    finally:
        limpar(db)
        db.close()


def test_regra_quebrada_nao_cala_as_outras():
    """Uma regra malformada não pode derrubar a verificação inteira."""
    print("\n[isolamento entre regras]")
    db = SessionLocal()
    try:
        limpar(db)
        db.add(RegraAlerta(tipo="tipo_que_nao_existe", nome="Quebrada",
                           limiar=1, janela_min=60, silencio_min=60))
        db.add(RegraAlerta(tipo="erro_novo", nome="Boa", limiar=1,
                           janela_min=60, silencio_min=60))
        db.commit()
        erro(db, "erro apos a regra quebrada")
        db.commit()
        checar(len(alertas.avaliar(db, enviar=False)) == 1,
               "a regra boa dispara mesmo com uma regra inválida na lista")
    finally:
        limpar(db)
        db.close()


def test_historico_registra():
    """Sem histórico, silêncio é ambíguo: 'tudo bem' e 'quebrou' são iguais."""
    print("\n[histórico]")
    db = SessionLocal()
    try:
        limpar(db)
        db.add(RegraAlerta(tipo="erro_novo", nome="Erro novo", limiar=1,
                           janela_min=60, silencio_min=60))
        db.commit()
        erro(db, "erro que vai para o historico")
        db.commit()

        alertas.avaliar(db, enviar=True)
        db.commit()
        h = alertas.historico(db, limite=10)
        checar(len(h) == 1, f"o disparo foi registrado (veio {len(h)})")
        checar(h and h[0]["rotulo"] == "Erro novo",
               "o histórico traz o rótulo legível do tipo")
        checar(h and "erro que vai para o historico" in (h[0]["resumo"] or ""),
               "o resumo diz QUAL foi o problema")
    finally:
        limpar(db)
        db.close()


if __name__ == "__main__":
    test_erro_novo_dispara_uma_vez()
    test_modo_teste_nao_estraga_o_alerta_real()
    test_limiar_de_volume()
    test_lentidao_usa_mediana()
    test_filtro_por_origem()
    test_regra_quebrada_nao_cala_as_outras()
    test_historico_registra()

    print()
    if FALHAS:
        print(f"test_alertas: {len(FALHAS)} FALHA(S)")
        for f in FALHAS:
            print(f"  - {f}")
        sys.exit(1)
    print("test_alertas: OK")
