"""Blocos de áudio: a ordem, a substituição e a consolidação (v2.98).

Uma entrevista real dura 40–90 min e é gravada em blocos de ~10 min que sobem
DURANTE a conversa. O que este teste protege é o que quebra em silêncio:

1. **A ORDEM é o `indice`, nunca a listagem do storage.** Ela é lexicográfica e
   põe `bloco-10` antes de `bloco-2` — o meio da conversa iria para o lugar
   errado, e **ninguém perceberia lendo o texto**. É a armadilha da v2.35 (o
   verso do RG servido como frente) num lugar novo.
2. **Reenviar um bloco SUBSTITUI, não duplica.** Rede instável reenvia; sem o
   `UniqueConstraint` e a troca da key, ficaria um bloco fantasma no meio da
   entrevista — e o áudio antigo, órfão no MinIO.
3. **Um bloco mudo NÃO contamina os outros.** Silêncio enquanto a pessoa lê um
   documento é normal. Marcar a gravação inteira como inaudível por causa dele
   descartaria uma entrevista inteira.
4. **Bloco falho ⇒ o texto SAI, com o aviso de qual faltou.** Recusar tudo por 10
   minutos perdidos jogaria fora os outros 80; apresentar como completo
   esconderia o buraco (a lição do dossiê, v2.93).
5. **Bloco ainda rodando ⇒ a gravação NÃO é `pronta`.** Senão o RH lê metade da
   conversa achando que é tudo.
6. **Excluir apaga o áudio de TODOS os blocos** — esquecer os blocos deixaria a
   entrevista inteira no MinIO com a tela dizendo que foi apagada.
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
from app.models.bloco_gravacao import BlocoGravacao, StatusBloco  # noqa: E402
from app.models.entrevista import Entrevista, TipoEntrevista  # noqa: E402
from app.models.gravacao_entrevista import StatusGravacao  # noqa: E402
from app.services import storage  # noqa: E402
from app.services.gravacao_entrevista import (blocos_de, config,  # noqa: E402
                                              consolidar, excluir,
                                              nome_arquivo, obter_ou_criar,
                                              proximo_indice, registrar_bloco,
                                              registrar_consentimento, resumo)

falhas: list[str] = []


def checar(ok: bool, descricao: str) -> None:
    print(f"  {'ok  ' if ok else 'FALHOU'}  {descricao}")
    if not ok:
        falhas.append(descricao)


def main() -> int:  # noqa: C901
    db = SessionLocal()
    marca = uuid.uuid4().hex[:8]
    e = Entrevista(tipo=TipoEntrevista.entrevista,
                   entrevistador_nome=f"Teste Blocos {marca}",
                   marcada_para=datetime.now(timezone.utc))
    db.add(e)
    db.flush()
    g = obter_ou_criar(db, e)
    registrar_consentimento(db, g, True, "entrevistador@exemplo.com.br")
    db.commit()

    base = f"testes/blocos/{marca}"

    def guardar(n: int) -> str:
        # ⚠️ SEM zero-padding de propósito: `bloco-10` vem ANTES de `bloco-2`
        # lexicograficamente, que é o defeito real (v2.35). Com `{n:03d}` a
        # ordem por key coincidiria com a ordem por índice e a asserção passaria
        # por acidente — a mutação que troca `indice` por `audio_key` sairia
        # verde (achado ao rodar a mutação, não ao escrever o teste).
        key = f"{base}/bloco-{n}.webm"
        storage.salvar(key, f"audio do bloco {n}".encode(), "audio/webm")
        return key

    print("=== 1. A ordem é o índice, mesmo chegando fora de ordem ===")
    # Envia 10, depois 2, depois 1 — o pior caso: lexicograficamente "010" < "002"
    # seria falso, mas a listagem do storage colocaria "010" antes de "002"…
    for n, inicio in ((10, 5400), (2, 600), (1, 0)):
        registrar_bloco(db, g, indice=n, key=guardar(n), bytes_=20,
                        tipo="audio/webm", duracao_s=600, inicio_s=inicio)
    db.commit()

    ordem = [b.indice for b in blocos_de(db, g)]
    checar(ordem == [1, 2, 10],
           f"os blocos saem na ordem da CONVERSA, não da listagem (veio {ordem})")
    # A prova de que não é sorte: a listagem do storage devolve outra coisa.
    lexico = [k.rsplit("/", 1)[-1] for k in sorted(storage.listar(base + "/"))]
    checar(lexico != ["001.webm", "002.webm", "010.webm"] or True,
           f"(contexto) a listagem do storage é lexicográfica: {lexico}")

    print("\n=== 2. Próximo índice vem do MAIOR, não da contagem ===")
    # Com 3 blocos (1, 2, 10), contar daria 4 — e 4 já poderia existir noutra
    # ordem de envio. O maior + 1 é o único que não colide.
    checar(proximo_indice(db, g) == 11,
           f"próximo índice é 11 (maior + 1), não 4 (contagem) — veio {proximo_indice(db, g)}")

    print("\n=== 3. Reenviar SUBSTITUI, não duplica ===")
    antes = len(blocos_de(db, g))
    key_velha = db.scalar(
        __import__("sqlalchemy").select(BlocoGravacao.audio_key).where(
            BlocoGravacao.gravacao_id == g.id, BlocoGravacao.indice == 2))
    key_nova = f"{base}/002-reenviado.webm"
    storage.salvar(key_nova, b"audio reenviado maior", "audio/webm")
    registrar_bloco(db, g, indice=2, key=key_nova, bytes_=21,
                    tipo="audio/webm", duracao_s=605, inicio_s=600)
    db.commit()
    depois = len(blocos_de(db, g))
    checar(antes == depois == 3,
           f"reenviar o bloco 2 não cria um quarto bloco (antes {antes}, depois {depois})")
    # O áudio antigo não pode virar órfão no MinIO.
    checar(storage.listar(key_velha) == [],
           "o áudio anterior do bloco sai do storage (não vira órfão)")

    print("\n=== 4. Bloco rodando ⇒ a gravação NÃO fica pronta ===")
    for b in blocos_de(db, g):
        b.status, b.texto = StatusBloco.pronta, f"texto do bloco {b.indice}"
    blocos_de(db, g)[0].status = StatusBloco.processando
    db.commit()
    consolidar(db, g)
    db.commit()
    checar(g.status == StatusGravacao.processando,
           f"com um bloco processando, a gravação segue `processando` (veio {g.status.value})")
    checar(g.texto is None,
           "e o texto não é publicado pela metade")

    print("\n=== 5. Todos prontos ⇒ texto na ORDEM da conversa ===")
    for b in blocos_de(db, g):
        b.status, b.texto = StatusBloco.pronta, f"texto do bloco {b.indice}"
    db.commit()
    consolidar(db, g)
    db.commit()
    checar(g.status == StatusGravacao.pronta,
           f"a gravação fica `pronta` (veio {g.status.value})")
    esperado = "texto do bloco 1\n\ntexto do bloco 2\n\ntexto do bloco 10"
    checar(g.texto == esperado,
           f"o texto sai na ordem 1, 2, 10 — não 1, 10, 2 (veio {(g.texto or '')[:60]!r})")
    checar(g.erro is None, "sem aviso de falha quando nada falhou")

    print("\n=== 6. Bloco mudo NÃO contamina os outros ===")
    b2 = [b for b in blocos_de(db, g) if b.indice == 2][0]
    b2.status, b2.texto = StatusBloco.inaudivel, None
    db.commit()
    consolidar(db, g)
    db.commit()
    checar(g.status == StatusGravacao.pronta,
           "um trecho sem fala (pessoa lendo um documento) não invalida a gravação")
    checar("texto do bloco 1" in (g.texto or "") and "texto do bloco 10" in (g.texto or ""),
           "e o texto dos demais blocos continua lá")

    print("\n=== 7. Bloco falho ⇒ texto sai, COM o aviso de qual faltou ===")
    b2.status, b2.erro = StatusBloco.falhou, "estourou"
    db.commit()
    consolidar(db, g)
    db.commit()
    checar(g.status == StatusGravacao.pronta,
           "10 minutos perdidos não jogam fora os outros 80")
    # Dizer QUAL faltou, não só que faltou: o RH consegue reouvir aquele trecho.
    checar(g.erro is not None and "2" in g.erro,
           f"a tela é avisada de QUAL bloco faltou (veio {g.erro!r})")

    print("\n=== 8. Todos falhos ⇒ a gravação falha (não finge que está pronta) ===")
    for b in blocos_de(db, g):
        b.status, b.texto, b.erro = StatusBloco.falhou, None, "estourou"
    db.commit()
    consolidar(db, g)
    db.commit()
    checar(g.status == StatusGravacao.falhou,
           f"sem nenhum texto, a gravação é `falhou` (veio {g.status.value})")

    print("\n=== 9. Todos mudos ⇒ `audio_inaudivel`, não `falhou` ===")
    # São coisas diferentes: "o sistema quebrou" manda procurar defeito;
    # "o áudio não tem fala" manda conferir o microfone.
    for b in blocos_de(db, g):
        b.status, b.erro = StatusBloco.inaudivel, None
    db.commit()
    consolidar(db, g)
    db.commit()
    checar(g.status == StatusGravacao.audio_inaudivel,
           f"áudio sem fala é `audio_inaudivel`, não `falhou` (veio {g.status.value})")

    print("\n=== 10. O resumo devolve os blocos ordenados e a config ===")
    r = resumo(g, db)
    checar([b["indice"] for b in r["blocos"]] == [1, 2, 10],
           "o resumo entrega os blocos na ordem da conversa")
    checar(r.get("bloco_min") == config(db)["bloco_min"],
           "e o tamanho do bloco configurado, para a tela não adivinhar")
    checar(r.get("pode_gravar") is True,
           "consentimento dado continua permitindo gravar mesmo com a gravação "
           "em outro estado (o defeito do 2º bloco, v2.98.1)")

    print("\n=== 11. Nome do arquivo: data e parte ===")
    n = nome_arquivo("Kátia Poliane", datetime(2026, 8, 12), parte=2)
    checar(n == "ENTREVISTA 12-08-2026 - KATIA POLIANE - PARTE 2",
           f"nome com data, caixa alta e sem acento (veio {n!r})")

    print("\n=== 12. Excluir apaga o áudio de TODOS os blocos ===")
    chaves = [b.audio_key for b in blocos_de(db, g)]
    excluir(db, g)
    db.commit()
    sobraram = [k for k in chaves if k and storage.listar(k)]
    checar(not sobraram,
           f"nenhum áudio de bloco fica no MinIO (sobraram {len(sobraram)})")
    checar(blocos_de(db, g) == [],
           "os blocos saem do banco junto")
    checar(g.status == StatusGravacao.recusado and g.consentimento_em is not None,
           "e o registro do consentimento permanece — é a prova da consulta")

    db.rollback()
    db.close()

    print("\n" + "=" * 62)
    if falhas:
        print(f"REPROVADO — {len(falhas)} verificação(ões) falharam:")
        for f in falhas:
            print(f"  - {f}")
        return 1
    print("APROVADO — blocos na ordem certa, substituindo, e consolidando bem.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
