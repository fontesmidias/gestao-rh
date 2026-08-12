"""Gravação de entrevista: sem consentimento não se grava (v2.97).

Gravação de voz é dado pessoal, e há entendimento de que voz é dado biométrico.
O que este teste protege não é uma funcionalidade — é a base legal dela.

⚠️ **Numa entrevista de emprego a conversa é assimétrica**: de um lado quem
decide, do outro quem precisa do emprego. Por isso três coisas precisam valer ao
mesmo tempo, e as três estão aqui:

1. **Sem consentimento, o áudio é RECUSADO** — e a checagem vive no SERVIÇO, não
   só na rota: "as rotas não deixam" não é garantia (v2.66), porque migration,
   acerto no banco e teste destrutivo não passam por rota.
2. **A recusa é um REGISTRO, não um vazio** (v2.34): sem manifestação gravada,
   "não foi perguntado" e "disse não" são a mesma linha em branco, e não se prova
   que a pessoa foi consultada.
3. **Retirar o consentimento APAGA o áudio de verdade** — "some da tela" não é o
   mesmo que "foi apagado" (a lição do verso do RG que ficava no MinIO, v2.35).
   E trocar para `recusado` deixando o áudio existir seria a pior das duas
   mentiras: um registro dizendo que a pessoa não autorizou, com o áudio dela
   guardado ao lado.

E uma trava estrutural: **a transcrição NÃO pode entrar no dossiê de admissão**
(§ 15.4). O `services/dossie.py` varre `SolicitacaoAssinatura` sem filtrar
origem, então todo fluxo novo entra nele POR PADRÃO — o dossiê CIRCULA: vai para
o cliente e para a pasta física.
"""

import os
import pathlib
import sys
import uuid
from datetime import datetime, timezone

RAIZ = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

os.environ.setdefault("DATABASE_URL",
                      "postgresql+psycopg://admissao:admissao@localhost:55432/admissao")

import app.main  # noqa: F401,E402  (registra os modelos no metadata — v2.64)

from app.core.db import SessionLocal  # noqa: E402
from app.models.entrevista import Entrevista, TipoEntrevista  # noqa: E402
from app.models.gravacao_entrevista import (GravacaoEntrevista,  # noqa: E402
                                            StatusGravacao)
from app.services import storage  # noqa: E402
from app.services.gravacao_entrevista import (GravacaoRecusada,  # noqa: E402
                                              excluir, marcar_para_transcrever,
                                              obter_ou_criar,
                                              registrar_consentimento, resumo)

falhas: list[str] = []


def checar(ok: bool, descricao: str) -> None:
    print(f"  {'ok  ' if ok else 'FALHOU'}  {descricao}")
    if not ok:
        falhas.append(descricao)


def main() -> int:
    db = SessionLocal()
    marca = uuid.uuid4().hex[:8]
    e = Entrevista(
        tipo=TipoEntrevista.entrevista,
        entrevistador_nome=f"Teste Gravação {marca}",
        marcada_para=datetime.now(timezone.utc),
    )
    db.add(e)
    db.flush()

    print("=== 1. Nasce 'não perguntado' — que NÃO é 'não quis' ===")
    g = obter_ou_criar(db, e)
    db.commit()
    checar(g.status == StatusGravacao.nao_perguntado,
           f"a gravação nasce em `nao_perguntado` (veio {g.status.value})")
    # A diferença entre os dois é o que prova que a pessoa foi consultada.
    checar(g.status != StatusGravacao.recusado,
           "`nao_perguntado` é distinto de `recusado` (senão não se prova a consulta)")
    checar(not g.pode_gravar, "sem consentimento, `pode_gravar` é falso")

    print("\n=== 2. Sem consentimento, o SERVIÇO recusa o áudio ===")
    recusou = False
    try:
        marcar_para_transcrever(db, g, key="x", bytes_=1, tipo="audio/webm", duracao_s=1)
    except GravacaoRecusada as exc:
        recusou = exc.erro == "sem_consentimento"
    checar(recusou,
           "o serviço recusa gravar sem consentimento (não só a rota — v2.66)")
    checar(g.audio_key is None, "e nada foi gravado no registro")

    print("\n=== 3. A recusa é um ATO registrado ===")
    registrar_consentimento(db, g, False, "entrevistador@exemplo.com.br")
    db.commit()
    checar(g.status == StatusGravacao.recusado, "o 'não' vira estado `recusado`")
    checar(g.consentimento_em is not None, "com a data em que foi registrado")
    checar(g.consentimento_por == "entrevistador@exemplo.com.br",
           "e com QUEM registrou (o sistema não viu a pessoa dizer não — viu o "
           "entrevistador afirmar que ela disse)")
    checar(not g.pode_gravar, "recusado continua sem poder gravar")

    print("\n=== 4. Com consentimento, grava e vai para a fila ===")
    registrar_consentimento(db, g, True, "entrevistador@exemplo.com.br")
    db.commit()
    checar(g.pode_gravar, "consentido pode gravar")

    key = f"testes/gravacao/{marca}/audio.webm"
    storage.salvar(key, b"audio de teste", "audio/webm")
    marcar_para_transcrever(db, g, key=key, bytes_=14, tipo="audio/webm", duracao_s=90)
    db.commit()
    checar(g.status == StatusGravacao.aguardando,
           f"o áudio guardado entra na fila (`aguardando`, veio {g.status.value})")
    checar(g.audio_key == key, "a key do áudio fica registrada")

    print("\n=== 5. Retirar o consentimento com áudio existente RECUSA, "
          "oferecendo a saída ===")
    # Aceitar aqui deixaria um áudio existindo sob um registro que diz que a
    # pessoa não autorizou.
    barrou = False
    mensagem = ""
    try:
        registrar_consentimento(db, g, False, "entrevistador@exemplo.com.br")
    except GravacaoRecusada as exc:
        barrou = exc.erro == "audio_ja_existe"
        mensagem = exc.detalhe
    checar(barrou, "recusa trocar para 'não autorizou' com áudio já gravado")
    # Recusar sem oferecer alternativa deixa o problema na mão de quem opera
    # (v2.87/v2.93): a mensagem tem que dizer o que RESOLVE.
    checar("exclua" in mensagem.lower(),
           f"e a mensagem diz o que resolve — excluir (veio: {mensagem[:60]!r})")
    checar(g.status == StatusGravacao.aguardando,
           "o estado não mudou pela metade")

    print("\n=== 6. Excluir apaga o áudio DE VERDADE e mantém o registro ===")
    g.texto = "transcrição de teste"
    db.commit()
    excluir(db, g)
    db.commit()
    checar(g.audio_key is None, "a key some do registro")
    checar(g.texto is None, "a transcrição some junto")
    checar(g.status == StatusGravacao.recusado,
           "e o estado vira `recusado` (a pessoa retirou a autorização)")
    # O objeto tem que sair do storage: "some da tela" não é "foi apagado".
    checar(storage.listar(f"testes/gravacao/{marca}/") == [],
           "o áudio saiu do MinIO (não é só a referência que sumiu)")
    ainda = db.get(GravacaoEntrevista, g.id)
    checar(ainda is not None,
           "o REGISTRO permanece — é a prova de que a pessoa foi consultada")

    print("\n=== 7. Estado sem gravação não é `null` na tela ===")
    # `null` faria a tela sumir com o bloco — e o bloco existe para a pergunta
    # ser feita.
    r = resumo(None)
    checar(r["status"] == "nao_perguntado",
           "gravação inexistente vira `nao_perguntado`, não `null`")
    checar(bool(r.get("rotulo")), "e vem com rótulo legível")

    print("\n=== 8. A transcrição NÃO tem caminho para o dossiê (§ 15.4) ===")
    dossie = (RAIZ / "app" / "services" / "dossie.py").read_text(encoding="utf-8")
    for termo in ("GravacaoEntrevista", "gravacao_entrevista", "transcricao"):
        checar(termo not in dossie,
               f"`services/dossie.py` não menciona '{termo}' — a transcrição não "
               "entra no dossiê que circula")

    db.rollback()
    db.close()

    print("\n" + "=" * 62)
    if falhas:
        print(f"REPROVADO — {len(falhas)} verificação(ões) falharam:")
        for f in falhas:
            print(f"  - {f}")
        return 1
    print("APROVADO — sem consentimento não se grava, e a recusa fica registrada.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
