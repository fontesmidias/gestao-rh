"""Admissão presencial assistida (v2.56) — o manifesto tem que dizer a verdade.

Feedback de campo 2026-08-02:

> *"quero pensar em uma estratégia para os casos em que a pessoa tiver baixo
> grau de instrução, ou dificuldades [...] o RH fazer tudo, desde a inserção de
> dados, coleta de documentos e tudo mais e ver alguma forma que a pessoa possa
> assinar o documento. Pois hoje o RH gera o link mas fica inserindo tudo na mão
> como se fosse uma correção e não como se o candidato estivesse ali."*

O recurso NÃO é "deixar o RH preencher" — isso já dava para fazer abrindo o
link. O que ele acrescenta é o **registro**: sem ele, uma admissão preenchida
pelo RH e uma feita pela pessoa em casa produzem documentos idênticos, e o
manifesto afirma *"código enviado ao titular e validado nesta plataforma"* como
se ela tivesse operado tudo sozinha.

As garantias, em ordem de importância:

1. **O documento assistido DECLARA que foi assistido**, com o nome de quem
   operou — e o documento comum continua exatamente como sempre foi.
2. **A prova de identidade não é enfraquecida**: exige e-mail da própria
   pessoa, senão não há para onde mandar o código (422 na abertura da sessão).
3. **O ator da assinatura continua sendo o CANDIDATO** — quem quis assinar foi
   ele. O que se acrescenta é *como*, não *quem*.
4. Link comum nunca é confundido com assistido.

Precisa de banco + MinIO efêmeros. Rode:
  PYTHONPATH=. .venv/Scripts/python.exe tests/test_admissao_assistida.py
"""
import io
import os
import sys
import uuid
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault(
    "DATABASE_URL", "postgresql+psycopg://admissao:admissao@localhost:55432/admissao")
os.environ.setdefault("SECRET_KEY", "teste")
os.environ.setdefault("MINIO_ENDPOINT", "localhost:59000")
os.environ.setdefault("MINIO_ACCESS_KEY", "minio")
os.environ.setdefault("MINIO_SECRET_KEY", "minio12345")
os.environ.setdefault("BASE_URL", "http://localhost:8000")

import pypdf  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.api.auth_rh import requer_rh  # noqa: E402
from app.core.db import SessionLocal  # noqa: E402
from app.main import app  # noqa: E402
from app.models.assinatura import Assinatura, DocumentoAssinavel  # noqa: E402
from app.models.candidato import Candidato, Jornada, PostoServico  # noqa: E402
from app.models.usuario_rh import UsuarioRH  # noqa: E402
from app.services.fichas import gerar_ficha_cadastro  # noqa: E402

FALHAS = []
OPERADOR = "rh.maria@exemplo.com.br"
_RH = UsuarioRH(email=OPERADOR, nome="Maria RH", senha_hash="x")
app.dependency_overrides[requer_rh] = lambda: _RH
cli = TestClient(app)
db = SessionLocal()


def checar(condicao, descricao):
    if condicao:
        print(f"  ok   {descricao}")
    else:
        print(f"  FALHA {descricao}")
        FALHAS.append(descricao)


def _candidato(nome: str, email: str | None):
    posto = PostoServico(nome=f"POSTO {uuid.uuid4().hex[:6]}")
    db.add(posto)
    jornada = Jornada(descricao=f"JORNADA {uuid.uuid4().hex[:6]}")
    db.add(jornada)
    db.flush()
    c = Candidato(nome_completo=nome, cpf=str(uuid.uuid4().int)[:11], email=email,
                  posto_servico_id=posto.id, jornada_id=jornada.id,
                  cargo_funcao="Vigilante", registra_ponto=True)
    db.add(c)
    db.commit()
    return c


def _token(link: str) -> str:
    return link.rsplit("/", 1)[-1]


def test_sessao_exige_email_da_propria_pessoa():
    """Sem e-mail não há para onde mandar o código — e a prova de identidade
    cairia junto. Barrar na ABERTURA é o melhor momento: a pessoa está na
    frente do RH e basta perguntar o endereço."""
    print("\n[e-mail é pré-requisito]")
    sem = _candidato("Sem Email", None)
    r = cli.post(f"/api/rh/candidatos/{sem.id}/sessao-assistida")
    checar(r.status_code == 422 and r.json().get("detail") == "sem_email",
           f"sem e-mail a sessão é recusada (veio {r.status_code})")

    com = _candidato("Com Email", "com@example.com")
    r = cli.post(f"/api/rh/candidatos/{com.id}/sessao-assistida")
    checar(r.status_code == 200, "com e-mail a sessão abre")
    checar(r.json()["email_enviado"] is False,
           "NÃO manda convite: o link é para o RH abrir agora, não para a pessoa receber")


def test_a_ficha_sabe_que_a_sessao_e_assistida():
    """O wizard precisa mostrar a faixa — é idêntico ao que a pessoa vê em casa."""
    print("\n[o wizard reconhece a sessão]")
    c = _candidato("Jose Assistido", "jose.assistido@example.com")

    r = cli.post(f"/api/rh/candidatos/{c.id}/sessao-assistida")
    ficha = cli.get(f"/api/c/{_token(r.json()['link_magico'])}/ficha").json()
    checar(ficha.get("sessao_assistida") == OPERADOR,
           f"a ficha traz quem opera (veio {ficha.get('sessao_assistida')!r})")

    # Link comum NUNCA pode ser confundido com assistido — senão todo candidato
    # que preenche em casa teria o documento marcado como presencial.
    r2 = cli.post(f"/api/rh/candidatos/{c.id}/reenviar-link?enviar_email_convite=false")
    ficha2 = cli.get(f"/api/c/{_token(r2.json()['link_magico'])}/ficha").json()
    checar(ficha2.get("sessao_assistida") is None,
           f"link comum NÃO é assistido (veio {ficha2.get('sessao_assistida')!r})")


def _pdf_texto(assistida_por: str | None) -> str:
    c = _candidato("Jose Sem Pratica", "jose.pdf@example.com")
    a = Assinatura(candidato_id=c.id, documento=DocumentoAssinavel.ficha_cadastro,
                   assinado_em=datetime.now(timezone.utc), ip="10.0.0.9",
                   user_agent="Chrome", hash_sha256="a" * 64,
                   assistida_por=assistida_por)
    db.add(a)
    db.flush()
    pdf = gerar_ficha_cadastro(db, c, assinatura=a, base_url="http://x")
    return "".join(p.extract_text() for p in pypdf.PdfReader(io.BytesIO(pdf)).pages)


def test_manifesto_declara_o_atendimento_assistido():
    """A garantia central: o documento descreve o ato COMO ELE FOI.

    É o mesmo princípio da `AutorizacaoEquipe`, que diz "emitido sob autorização
    permanente de X" em vez de "X assinou" — o documento nunca simula um ato que
    não aconteceu daquela forma.
    """
    print("\n[o manifesto diz a verdade]")
    texto = _pdf_texto(OPERADOR)
    checar("PRESENCIALMENTE" in texto,
           "o manifesto declara que a coleta foi presencial")
    checar(OPERADOR in texto,
           "e NOMEIA quem operou o preenchimento")
    checar("Forma de coleta" in texto,
           "num campo próprio, ao lado de Método e Modalidade")
    # A prova de identidade continua descrita: o código foi para o e-mail DELA.
    checar("enviado ao" in texto and "titular" in texto,
           "e mantém que o código foi ao titular — a identidade não foi enfraquecida")


def test_bloco_no_corpo_do_documento_tambem_registra():
    """Não só o manifesto do fim: o BLOCO no corpo também precisa dizer.

    É o que alguém lê ao abrir o PDF, sem rolar até a última página. Nem todo
    documento tem esse bloco — a ficha cadastral, por exemplo, usa só o
    manifesto —, então o teste usa um que tem (o termo de VT).
    """
    print("\n[bloco de assinatura no corpo]")
    from app.services.fichas import gerar_termo_vt

    c = _candidato("Jose Bloco", "jose.bloco@example.com")
    a = Assinatura(candidato_id=c.id, documento=DocumentoAssinavel.termo_vt,
                   assinado_em=datetime.now(timezone.utc), ip="10.0.0.9",
                   user_agent="Chrome", hash_sha256="b" * 64,
                   assistida_por=OPERADOR)
    db.add(a)
    db.flush()
    pdf = gerar_termo_vt(db, c, assinatura=a, base_url="http://x")
    bruto = "".join(p.extract_text() for p in pypdf.PdfReader(io.BytesIO(pdf)).pages)
    # Espaços NORMALIZADOS: o `multi_cell` do fpdf quebra a linha no meio da
    # frase, e o `extract_text` devolve o `\n` — procurar a frase literal
    # falharia por causa da largura da caixa, não do conteúdo.
    texto = " ".join(bruto.split())
    checar("em atendimento assistido por" in texto,
           "o bloco no corpo registra o atendimento assistido")
    checar(OPERADOR in texto, "com o nome de quem operou")


def test_documento_comum_nao_muda():
    """Regressão: quem assina de casa não pode ganhar texto novo no documento.

    Sem esta garantia, a mudança valeria para TODA assinatura já emitida — e o
    manifesto é peça de prova cujo texto não deve variar por acidente.
    """
    print("\n[documento comum intacto]")
    texto = _pdf_texto(None)
    checar("PRESENCIALMENTE" not in texto,
           "assinatura remota NÃO menciona atendimento presencial")
    checar("Forma de coleta" not in texto,
           "e não ganha o campo novo")
    checar("Modalidade" in texto and "14.063/2020" in texto,
           "mas mantém tudo o que já tinha")


def test_o_rh_enxerga_o_atendimento_na_lista_e_na_ficha():
    """Feedback 2026-08-02: *"onde e como eu marco que o atendimento foi
    assistido?"*.

    O botão existia, mas nada na tela mostrava o resultado — o RH clicava e não
    tinha como saber, olhando a lista, que aquela pessoa estava em atendimento
    (nem por quem). E o registro vivia só na auditoria geral, que ninguém abre
    no dia a dia.

    Duas visões, com propósitos diferentes:

    * **lista**: só o atendimento EM CURSO (é operacional — "quem estou
      atendendo agora"), e some quando o link expira;
    * **ficha**: o HISTÓRICO inteiro, inclusive o encerrado — é registro, e
      registro não some.
    """
    print("\n[o RH enxerga o atendimento]")
    from datetime import timedelta

    from app.models.candidato import AcessoMagico

    c = _candidato("Jose Visivel", "jose.visivel@example.com")

    # antes de abrir: nada em lugar nenhum
    def _da_lista():
        lst = cli.get("/api/rh/candidatos").json()
        alvo = [x for x in lst if x["id"] == str(c.id)]
        return alvo[0]["atendimento_assistido"] if alvo else None

    def _da_ficha():
        return cli.get(f"/api/rh/candidatos/{c.id}").json()["atendimentos_assistidos"]

    checar(_da_lista() is None, "sem atendimento, a lista não marca nada")
    checar(_da_ficha() == [], "e a ficha não inventa histórico")

    cli.post(f"/api/rh/candidatos/{c.id}/sessao-assistida")
    na_lista = _da_lista()
    checar(na_lista is not None and na_lista["por"] == OPERADOR,
           "aberto o atendimento, a lista mostra QUEM está atendendo")
    ficha = _da_ficha()
    checar(len(ficha) == 1 and ficha[0]["em_curso"] is True,
           "e a ficha registra como em curso")

    # depois de expirar (as 8h do link): sai da lista, FICA na ficha.
    db.expire_all()
    acesso = db.query(AcessoMagico).filter(
        AcessoMagico.candidato_id == c.id,
        AcessoMagico.assistido_por.is_not(None)).first()
    acesso.expira_em = datetime.now(timezone.utc) - timedelta(hours=1)
    db.commit()

    checar(_da_lista() is None,
           "link expirado sai da lista — não é mais 'atendendo agora'")
    ficha = _da_ficha()
    checar(len(ficha) == 1 and ficha[0]["em_curso"] is False,
           "mas PERMANECE na ficha como histórico, marcado encerrado")


def test_o_ator_continua_sendo_o_candidato():
    """Quem quis assinar foi ELE. O que se acrescenta é COMO, não QUEM.

    Trocar o ator para "rh" registraria que o RH assinou — exatamente a
    distorção que este recurso existe para evitar.
    """
    print("\n[a autoria não muda]")
    import inspect

    from app.api import assinaturas as mod
    fonte = inspect.getsource(mod)
    checar('registrar(db, "documento_assinado", ator="candidato"' in fonte,
           "a auditoria da assinatura continua com ator=candidato")
    checar('"assistida_por": assistida_por' in fonte,
           "e acrescenta quem operou, quando houve atendimento assistido")


if __name__ == "__main__":
    test_sessao_exige_email_da_propria_pessoa()
    test_a_ficha_sabe_que_a_sessao_e_assistida()
    test_manifesto_declara_o_atendimento_assistido()
    test_bloco_no_corpo_do_documento_tambem_registra()
    test_documento_comum_nao_muda()
    test_o_rh_enxerga_o_atendimento_na_lista_e_na_ficha()
    test_o_ator_continua_sendo_o_candidato()

    print()
    if FALHAS:
        print(f"test_admissao_assistida: {len(FALHAS)} FALHA(S)")
        for f in FALHAS:
            print(f"  - {f}")
        sys.exit(1)
    print("test_admissao_assistida: OK")
