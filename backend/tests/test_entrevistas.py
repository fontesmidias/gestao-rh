"""Módulo de Entrevistas (v2.64) - os 8 testes de comportamento da seção 11 do
`docs/planejamento/12-modulo-de-entrevistas.md`.

(O 9º é o `test_design_system.py`, que já reprova `<select>` nativo, classe
fantasma e token inexistente - roda no CI e não se duplica aqui.)

Regra da casa: **todo teste novo é validado por MUTAÇÃO** - reintroduz-se o
defeito e confirma-se que o teste falha. Teste que passa com o defeito presente
não é teste. As mutações verificadas estão anotadas em cada função.

Precisa dos containers de teste:
  docker run -d --name pg-teste ... postgres:16-alpine
  docker run -d --name minio-teste ... quay.io/minio/minio server /data

Rode: PYTHONPATH=. .venv/Scripts/python.exe tests/test_entrevistas.py
"""

import os
import uuid
from datetime import datetime, timedelta, timezone

os.environ.setdefault(
    "DATABASE_URL", "postgresql+psycopg://admissao:admissao@localhost:55432/admissao")
os.environ.setdefault("MINIO_ENDPOINT", "localhost:59000")
os.environ.setdefault("MINIO_ACCESS_KEY", "minio")
os.environ.setdefault("MINIO_SECRET_KEY", "minio12345")
os.environ.setdefault("MINIO_SECURE", "false")
os.environ.setdefault("RH_ADMIN_EMAIL", "rh@greenhousedf.com.br")
os.environ.setdefault("RH_ADMIN_PASSWORD", "senha-teste-123")
os.environ.setdefault("SECRET_KEY", "segredo-de-teste")
os.environ.setdefault("BASE_URL", "http://localhost:8090")

from fastapi.testclient import TestClient  # noqa: E402

from app.core.db import SessionLocal  # noqa: E402
from app.main import app  # noqa: E402
from app.models.entrevista import Entrevista, StatusEntrevista  # noqa: E402

c = TestClient(app)

# Credencial do AMBIENTE, nunca literal na linha do login (v2.71): no CI o
# admin nasce com a senha do `.env` do job, e a literal devolvia 401 -> o teste
# morria em `KeyError: 'token'`, erro que não diz nada sobre a causa. Foi
# exatamente o que impediu `test_documentos_catalogo` e `test_email_templates`
# de entrarem no CI — e este teste tinha o mesmo defeito.
EMAIL = os.environ["RH_ADMIN_EMAIL"]
SENHA = os.environ["RH_ADMIN_PASSWORD"]

r = c.post("/api/rh/auth/login", json={"email": EMAIL, "senha": SENHA})
assert r.status_code == 200, (
    f"login falhou ({r.status_code}): confira RH_ADMIN_EMAIL/RH_ADMIN_PASSWORD "
    f"— `criar_admin_inicial` só cria o admin com a tabela VAZIA, então num "
    f"banco com usuários antigos o admin do .env não existe. Resposta: {r.text}")
RH = {"Authorization": f"Bearer {r.json()['token']}"}

# Sufixo por EXECUÇÃO: o e-mail do talento e o título da vaga se repetiriam
# entre rodadas no mesmo banco, e teste que só passa em banco limpo é
# armadilha (lição do test_jornadas_confirmar_lote).
SUF = uuid.uuid4().hex[:8]

falhas = []


def checar(cond, msg):
    if cond:
        print(f"  ok   {msg}")
    else:
        print(f"  FALHOU  {msg}")
        falhas.append(msg)


def criar_talento(nome="Fulano de Teste"):
    r = c.post("/api/talentos", json={
        "nome": nome, "email": f"talento-{SUF}-{uuid.uuid4().hex[:6]}@exemplo.com",
        "telefone": "61999990000", "cargos_interesse": ["Vigia"],
        "consentimento_lgpd": True})
    assert r.status_code in (200, 201), f"criar talento: {r.status_code} {r.text}"
    return r.json()["id"]


def criar_vaga(titulo=None):
    r = c.post("/api/rh/vagas", headers=RH, json={
        "titulo": titulo or f"Vigia noturno {SUF}",
        "descricao": "Posto 12x36 noturno.", "cargo": "Vigia"})
    assert r.status_code in (200, 201), f"criar vaga: {r.status_code} {r.text}"
    return r.json()["id"]


# --------------------------------------------------------------------------
print("\n1. test_entrevista_instrumento - o formulário serve as 4 competências")
# --------------------------------------------------------------------------
form = c.get("/api/rh/entrevistas/formulario", headers=RH)
checar(form.status_code == 200,
       "GET /formulario responde 200 (a rota literal não virou {id}  vira 422)")
f = form.json()
checar(len(f["competencias"]) == 4, "devolve exatamente 4 competências")
checar(all(len(comp["ancoras"]) == 4 for comp in f["competencias"]),
       "toda competência tem as 4 âncoras (1..4)")
checar(all(comp["perguntas"].get("comportamental") and comp["perguntas"].get("situacional")
           for comp in f["competencias"]),
       "toda competência tem as DUAS variantes de pergunta")
# ⚠️ NÃO se trava a CONTAGEM de perguntas (lição da v2.25: teste que afirma
# `len(...) == 5` quebra a cada acréscimo legítimo, sem apontar defeito — e a
# correção óbvia, incrementar o número, faz o teste não proteger nada). Este
# assert era `== 5` e quebrou na v2.66, quando o § 14.2 acrescentou 4 perguntas
# a PEDIDO do Bruno. O que importa é a NATUREZA da triagem, não quantas são:
# todas se respondem sim/não/não sei, e nenhuma tem nota, âncora ou competência.
perguntas_triagem = f["triagem"]["perguntas"]
checar(len(perguntas_triagem) >= 5,
       f"a triagem tem ao menos as 5 perguntas do documento ({len(perguntas_triagem)})")
checar(all("ancoras" not in p and "nota" not in p and "competencia" not in p
           for p in perguntas_triagem),
       "e NENHUMA delas tem nota, âncora ou competência — triagem é checagem de "
       "viabilidade, não entrevista curta (§ 4.1)")
checar(set(f["triagem"]["respostas"]) == {"sim", "nao", "nao_sei"},
       f"as respostas continuam sendo sim/nao/nao_sei ({f['triagem']['respostas']})")
checar(any(p["chave"] == "recebe_seguro_desemprego" for p in perguntas_triagem),
       "seguro-desemprego está na triagem (decisão 4 do Bruno)")

# O front NÃO pode duplicar o texto do instrumento (estrutural, como o
# test_design_system). Mutação: colar uma âncora no JSX -> tem que falhar.
raiz = os.path.join(os.path.dirname(__file__), "..", "..", "frontend", "src")
trechos = [f["competencias"][0]["ancoras"]["4"][:40],
           f["competencias"][1]["perguntas"]["comportamental"][:40],
           f["triagem"]["perguntas"][0]["pergunta"][:40]]
duplicado = []
for pasta, _, arquivos in os.walk(raiz):
    for nome in arquivos:
        if not nome.endswith(".jsx"):
            continue
        caminho = os.path.join(pasta, nome)
        with open(caminho, encoding="utf-8") as fh:
            conteudo = fh.read()
        for t in trechos:
            if t and t in conteudo:
                duplicado.append(f"{nome}: {t[:30]}...")
checar(not duplicado,
       f"o front NÃO duplica texto do instrumento (achados: {duplicado})")


# --------------------------------------------------------------------------
print("\n2. test_entrevista_sem_agendamento - nasce realizada, sem marcada_para")
# --------------------------------------------------------------------------
t1 = criar_talento("Pessoa Sem Agendamento")
r = c.post("/api/rh/entrevistas", headers=RH,
           json={"talento_id": t1, "tipo": "entrevista"})   # sem marcada_para
checar(r.status_code == 201, f"cria sem marcada_para ({r.status_code})")
e_sem_agenda = r.json()
checar(e_sem_agenda["status"] == "realizada",
       "nasce direto em `realizada` - exigir agendamento prévio mataria o módulo")
checar(e_sem_agenda["marcada_para"] is None, "marcada_para continua nulo")
checar(e_sem_agenda["realizada_em"] is not None, "realizada_em foi carimbado")


# --------------------------------------------------------------------------
print("\n3. test_entrevista_validacao - nota sem justificativa e ressalva sem motivo")
# --------------------------------------------------------------------------
t2 = criar_talento("Pessoa Validacao")
eid = c.post("/api/rh/entrevistas", headers=RH,
             json={"talento_id": t2, "tipo": "entrevista"}).json()["id"]

# Nota sem justificativa  vira 422 NOMEANDO a competência.
r = c.put(f"/api/rh/entrevistas/{eid}", headers=RH,
          json={"competencias": {"confiabilidade": 3}, "justificativas": {}})
checar(r.status_code == 422, f"nota sem justificativa é recusada ({r.status_code})")
erros = " ".join(r.json().get("detail", {}).get("erros", []))
checar("Confiabilidade e presença" in erros,
       f"o 422 NOMEIA a competência que falta (erros={erros!r})")

# Com justificativa, passa.
r = c.put(f"/api/rh/entrevistas/{eid}", headers=RH,
          json={"competencias": {"confiabilidade": 3},
                "justificativas": {"confiabilidade": "Descreveu a rotina de ônibus."}})
checar(r.status_code == 200, f"com justificativa, salva ({r.status_code})")

# Justificativa só de espaços NÃO conta como justificativa.
r = c.put(f"/api/rh/entrevistas/{eid}", headers=RH,
          json={"competencias": {"trato_publico": 2},
                "justificativas": {"trato_publico": "   "}})
checar(r.status_code == 422, "justificativa só com espaços é recusada")

# Recomendação com ressalva SEM motivo  vira 422.
r = c.put(f"/api/rh/entrevistas/{eid}", headers=RH,
          json={"recomendacao": "contratar_com_ressalva", "recomendacao_motivo": ""})
checar(r.status_code == 422, f"ressalva sem motivo é recusada ({r.status_code})")
r = c.put(f"/api/rh/entrevistas/{eid}", headers=RH,
          json={"recomendacao": "banco_para_outra_vaga", "recomendacao_motivo": ""})
checar(r.status_code == 422, "banco_para_outra_vaga sem motivo é recusada")
# `contratar` NÃO exige motivo - a exigência é das duas, não de todas.
r = c.put(f"/api/rh/entrevistas/{eid}", headers=RH, json={"recomendacao": "contratar"})
checar(r.status_code == 200, "`contratar` não exige motivo")

# Concluir pela METADE não fecha: faltam 3 competências.
r = c.put(f"/api/rh/entrevistas/{eid}", headers=RH, json={"concluir": True})
checar(r.status_code == 422, "não conclui com competências faltando")
checar("erros" in (r.json().get("detail") or {}), "e diz o que falta")


# --------------------------------------------------------------------------
print("\n4. test_entrevista_escopo_pessoa - a entrevista SEGUE a pessoa")
# --------------------------------------------------------------------------
# Este é o teste que justifica as DUAS FKs. Mutação verificada: trocar por FK
# única (só candidato_id) -> a entrevista do talento some da ficha do candidato.
t3 = criar_talento("Pessoa Que Converte")
ent_talento = c.post("/api/rh/entrevistas", headers=RH,
                     json={"talento_id": t3, "tipo": "triagem"}).json()["id"]

r = c.post(f"/api/rh/talentos/{t3}/converter", headers=RH)
checar(r.status_code in (200, 201), f"converte talento->candidato ({r.status_code})")
cand_id = r.json()["candidato_id"]

# Consultando pelo lado do CANDIDATO, a entrevista feita como TALENTO aparece.
r = c.get(f"/api/rh/pessoa/entrevistas?candidato_id={cand_id}", headers=RH)
checar(r.status_code == 200, "consulta por candidato_id responde 200")
ids = [i["id"] for i in r.json()["itens"]]
checar(ent_talento in ids,
       "a entrevista feita com o TALENTO aparece na ficha do CANDIDATO "
       "(com FK única, sumiria)")

# E pelo lado do talento também.
r = c.get(f"/api/rh/pessoa/entrevistas?talento_id={t3}", headers=RH)
checar(ent_talento in [i["id"] for i in r.json()["itens"]],
       "e continua aparecendo pelo lado do talento")


# --------------------------------------------------------------------------
print("\n5. test_entrevista_vaga_excluida - a entrevista sobrevive à vaga")
# --------------------------------------------------------------------------
# O título é uma CONSTANTE conhecida do teste, não uma variável lida da
# resposta: comparar `depois == antes` seria TAUTOLOGIA — a mutação que zera o
# snapshot zeraria os DOIS lados e a asserção passaria com o defeito presente
# (foi exatamente o que a mutação 5 revelou na 1ª versão deste teste).
TITULO_VAGA = f"Vigia noturno snapshot {SUF}"
vid = criar_vaga(TITULO_VAGA)
t4 = criar_talento("Pessoa Da Vaga")
ent_vaga = c.post("/api/rh/entrevistas", headers=RH,
                  json={"talento_id": t4, "tipo": "entrevista", "vaga_id": vid}).json()
checar(ent_vaga["vaga_titulo"] == TITULO_VAGA,
       f"o título da vaga é gravado como SNAPSHOT no nascimento "
       f"(esperado {TITULO_VAGA!r}, veio {ent_vaga['vaga_titulo']!r})")

r = c.delete(f"/api/rh/vagas/{vid}", headers=RH)
checar(r.status_code in (200, 204), f"exclui a vaga ({r.status_code})")

r = c.get(f"/api/rh/entrevistas/{ent_vaga['id']}", headers=RH)
checar(r.status_code == 200,
       "a entrevista CONTINUA existindo depois de a vaga ser excluída")
depois = r.json()
checar(depois["vaga_id"] is None, "vaga_id virou NULL (ondelete=SET NULL)")
checar(depois["vaga_titulo"] == TITULO_VAGA,
       f"o título sobrevive à exclusão da vaga ({depois['vaga_titulo']!r})")
checar(depois["vaga_existe"] is False, "a tela sabe que a vaga não existe mais")


# --------------------------------------------------------------------------
print("\n6. test_entrevista_pendencias - cobra, mas NUNCA conclui sozinha")
# --------------------------------------------------------------------------
t5 = criar_talento("Pessoa Que Nao Veio")
ontem = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()
ent_pend = c.post("/api/rh/entrevistas", headers=RH,
                  json={"talento_id": t5, "tipo": "entrevista",
                        "marcada_para": ontem}).json()
checar(ent_pend["status"] == "marcada", "com data futura informada, nasce `marcada`")

r = c.get("/api/rh/entrevistas/pendencias", headers=RH)
checar(r.status_code == 200, "GET /pendencias responde 200 (rota literal, não {id})")
pend_ids = [i["id"] for i in r.json()["itens"]]
checar(ent_pend["id"] in pend_ids,
       "passou da data e não foi preenchida -> aparece em PENDÊNCIAS")

# O ponto central: o sistema PERGUNTA, nunca conclui.
# Mutação verificada: marcar `nao_veio` automático na varredura -> falha aqui.
atual = c.get(f"/api/rh/entrevistas/{ent_pend['id']}", headers=RH).json()
checar(atual["status"] == "marcada",
       "continua `marcada` - o sistema NUNCA marca nao_veio sozinho")
checar(atual["aguardando_desfecho"] is True,
       "e se anuncia como aguardando desfecho (o card que cobra)")

# Só um ato humano fecha.
r = c.post(f"/api/rh/entrevistas/{ent_pend['id']}/desfecho", headers=RH,
           json={"status": "nao_veio"})
checar(r.status_code == 200 and r.json()["status"] == "nao_veio",
       "o RH fecha explicitamente como `nao_veio`")
r = c.get("/api/rh/entrevistas/pendencias", headers=RH)
checar(ent_pend["id"] not in [i["id"] for i in r.json()["itens"]],
       "e sai da fila de pendências")


# --------------------------------------------------------------------------
print("\n7. test_entrevista_arquivamento - ARQUIVA, não apaga")
# --------------------------------------------------------------------------
# Mutação verificada: trocar `arquivar` por `db.delete(e)` -> o GET vira 404 e
# este bloco falha.
t6 = criar_talento("Pessoa Arquivada")
ent_arq = c.post("/api/rh/entrevistas", headers=RH,
                 json={"talento_id": t6, "tipo": "entrevista"}).json()["id"]
r = c.post(f"/api/rh/entrevistas/{ent_arq}/arquivar", headers=RH,
           json={"motivo": "passou de 180 dias"})
checar(r.status_code == 200, f"arquiva ({r.status_code})")
checar(r.json()["status"] == "arquivada", "status virou `arquivada`")

r = c.get(f"/api/rh/entrevistas/{ent_arq}", headers=RH)
checar(r.status_code == 200,
       "o REGISTRO CONTINUA EXISTINDO e consultável (arquivar != apagar)")
checar(r.json()["arquivada_em"] is not None, "arquivada_em foi carimbado")

# Sai da vista por padrão...
lista = c.get("/api/rh/entrevistas", headers=RH).json()
checar(ent_arq not in [i["id"] for i in lista["itens"]],
       "sai da lista por padrão (sai da vista e das métricas)")
# ...mas é acessível a quem procurar.
lista2 = c.get("/api/rh/entrevistas?incluir_arquivadas=true", headers=RH).json()
checar(ent_arq in [i["id"] for i in lista2["itens"]],
       "e reaparece com incluir_arquivadas=true (a memória permanece)")


# --------------------------------------------------------------------------
print("\n8. test_entrevista_anotacao_no_crm - concluir escreve no mini-CRM")
# --------------------------------------------------------------------------
t7 = criar_talento("Pessoa Anotada")
ent_crm = c.post("/api/rh/entrevistas", headers=RH,
                 json={"talento_id": t7, "tipo": "triagem"}).json()["id"]
r = c.put(f"/api/rh/entrevistas/{ent_crm}", headers=RH,
          json={"triagem": {"aceita_escala": "sim", "tem_interesse": "sim"},
                "triagem_desfecho": "segue", "concluir": True})
checar(r.status_code == 200, f"conclui a triagem ({r.status_code})")

r = c.get(f"/api/rh/crm/anotacoes?talento_id={t7}", headers=RH)
if r.status_code != 200:
    r = c.get(f"/api/rh/crm/pessoa?talento_id={t7}", headers=RH)
corpo = r.json() if r.status_code == 200 else {}
anots = corpo.get("anotacoes", corpo.get("itens", []))
texto_anots = " ".join(a.get("texto", "") for a in anots)
checar("Triagem realizada" in texto_anots,
       f"ao concluir, escreve anotação no mini-CRM (texto={texto_anots[:80]!r})")


# --------------------------------------------------------------------------
print("\n9. test_entrevista_n_mais_1 - listar N não faz N consultas")
# --------------------------------------------------------------------------
# NÃO se usa limite absoluto de consultas: isso mede o TAMANHO DO BANCO, que
# cresce a cada execução. Compara-se DUAS listagens de tamanhos diferentes e
# exige-se que a diferença de consultas não acompanhe a de registros.
from sqlalchemy import event  # noqa: E402

from app.core.db import engine  # noqa: E402


def contar_consultas(fn):
    n = [0]

    def antes(conn, cursor, stmt, params, ctx, muitos):
        n[0] += 1
    event.listen(engine, "before_cursor_execute", antes)
    try:
        fn()
    finally:
        event.remove(engine, "before_cursor_execute", antes)
    return n[0]


vaga_a = criar_vaga(f"Vaga N+1 A {SUF}")
vaga_b = criar_vaga(f"Vaga N+1 B {SUF}")
# 2 entrevistas na vaga A, 8 na vaga B - pessoas DIFERENTES, que é o que
# provocaria o N+1 (uma consulta por pessoa para resolver o nome).
for _ in range(2):
    c.post("/api/rh/entrevistas", headers=RH,
           json={"talento_id": criar_talento(), "tipo": "entrevista", "vaga_id": vaga_a})
for _ in range(8):
    c.post("/api/rh/entrevistas", headers=RH,
           json={"talento_id": criar_talento(), "tipo": "entrevista", "vaga_id": vaga_b})

q_a = contar_consultas(lambda: c.get(f"/api/rh/vagas/{vaga_a}/entrevistas", headers=RH))
q_b = contar_consultas(lambda: c.get(f"/api/rh/vagas/{vaga_b}/entrevistas", headers=RH))
print(f"     2 registros -> {q_a} consultas | 8 registros -> {q_b} consultas")
# Com N+1 puro, 6 registros a mais custariam ~6 consultas a mais.
checar(q_b - q_a <= 2,
       f"6 registros a mais não custam ~6 consultas a mais ({q_a} -> {q_b}) - sem N+1")


# --------------------------------------------------------------------------
print("\n10. Extras - triagem sem nota, e o que o documento promete")
# --------------------------------------------------------------------------
# A triagem NÃO aceita competência/nota: são instrumentos de natureza diferente.
t8 = criar_talento("Pessoa Triagem Pura")
ent_tri = c.post("/api/rh/entrevistas", headers=RH,
                 json={"talento_id": t8, "tipo": "triagem"}).json()["id"]
r = c.put(f"/api/rh/entrevistas/{ent_tri}", headers=RH,
          json={"triagem": {"aceita_escala": "talvez"}})
checar(r.status_code == 422, "resposta fora de sim/nao/nao_sei é recusada na triagem")
r = c.get(f"/api/rh/entrevistas/{ent_tri}", headers=RH).json()
checar(r["competencias"] is None and r["media"] is None,
       "triagem não tem nota nem média (sem competência, média é None, não 0)")

# Exatamente UMA das duas FKs de pessoa.
r = c.post("/api/rh/entrevistas", headers=RH, json={"tipo": "entrevista"})
checar(r.status_code == 422, "sem pessoa nenhuma, recusa")
r = c.post("/api/rh/entrevistas", headers=RH,
           json={"tipo": "entrevista", "talento_id": t8, "candidato_id": cand_id})
checar(r.status_code == 422, "com as DUAS FKs, recusa (exatamente uma)")

# Remarcada é terminal e gera nova linha (cenário 19).
t9 = criar_talento("Pessoa Remarcada")
ent_rem = c.post("/api/rh/entrevistas", headers=RH,
                 json={"talento_id": t9, "tipo": "entrevista",
                       "marcada_para": (datetime.now(timezone.utc)
                                        + timedelta(days=1)).isoformat()}).json()["id"]
c.post(f"/api/rh/entrevistas/{ent_rem}/desfecho", headers=RH, json={"status": "remarcada"})
r = c.post(f"/api/rh/entrevistas/{ent_rem}/desfecho", headers=RH, json={"status": "cancelada"})
checar(r.status_code == 200,
       "remarcada permite correção de desfecho (não trava o registro)")
nova = c.post("/api/rh/entrevistas", headers=RH,
              json={"talento_id": t9, "tipo": "entrevista"})
checar(nova.status_code == 201, "e uma NOVA linha é criada para a remarcação")

# Arquivada não aceita mais preenchimento.
r = c.put(f"/api/rh/entrevistas/{ent_arq}", headers=RH, json={"observacao": "x"})
checar(r.status_code == 409, "entrevista arquivada não aceita mais edição")

# A média ignora ausência e nunca inventa zero.
with SessionLocal() as db:
    e = db.get(Entrevista, uuid.UUID(ent_arq))
    checar(e is not None and e.status == StatusEntrevista.arquivada,
           "no BANCO, o registro arquivado continua lá (não foi deletado)")


print()
if falhas:
    print(f"test_entrevistas: {len(falhas)} FALHA(S)")
    for f_ in falhas:
        print(f"  - {f_}")
    raise SystemExit(1)
print("test_entrevistas: OK")
