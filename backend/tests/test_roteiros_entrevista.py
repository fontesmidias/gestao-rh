"""Fase 3 do Módulo de Entrevistas (v2.66) — cenários 21 a 30 do § 14.5.

Cobre os quatro pedidos do Bruno de 2026-08-05: roteiros múltiplos (§ 14.1),
mais perguntas de triagem (§ 14.2), tag de reaproveitamento (§ 14.3) e o
convite/lembrete de calendário (§ 14.4).

Regra da casa: **todo teste novo é validado por MUTAÇÃO** — reintroduz-se o
defeito e confirma-se que o teste falha. Teste que passa com o defeito presente
não é teste. As mutações verificadas estão anotadas em cada bloco.

⚠️ **Referência de teste é CONSTANTE conhecida do teste**, nunca valor lido do
próprio sistema sob teste. Foi o defeito que este mesmo módulo pagou na v2.64:
`titulo_original = resposta["vaga_titulo"]` comparado com `depois["vaga_titulo"]`
passava verde com o snapshot zerado, porque a mutação zerava os DOIS lados. Aqui
o texto da âncora, o nome do roteiro e o UID do `.ics` são literais escritos no
teste.

Precisa dos containers de teste:
  docker run -d --name pg-teste ... postgres:16-alpine
  docker run -d --name minio-teste ... quay.io/minio/minio server /data

Rode: PYTHONPATH=. .venv/Scripts/python.exe tests/test_roteiros_entrevista.py
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

from app.main import app  # noqa: E402

c = TestClient(app)

# Credencial do AMBIENTE, nunca literal na linha do login (v2.71): no CI o
# admin nasce com a senha do `.env` do job, e a literal devolvia 401 -> o teste
# morria em `KeyError: 'token'`, erro que não diz nada sobre a causa.
EMAIL = os.environ["RH_ADMIN_EMAIL"]
SENHA = os.environ["RH_ADMIN_PASSWORD"]

r = c.post("/api/rh/auth/login", json={"email": EMAIL, "senha": SENHA})
assert r.status_code == 200, (
    f"login falhou ({r.status_code}): confira RH_ADMIN_EMAIL/RH_ADMIN_PASSWORD "
    f"— `criar_admin_inicial` só cria o admin com a tabela VAZIA, então num "
    f"banco com usuários antigos o admin do .env não existe. Resposta: {r.text}")
RH = {"Authorization": f"Bearer {r.json()['token']}"}

# Sufixo por EXECUÇÃO: nome de roteiro, e-mail de talento e título de vaga se
# repetiriam entre rodadas no MESMO banco, e teste que só passa em banco limpo é
# armadilha (lição do test_jornadas_confirmar_lote).
SUF = uuid.uuid4().hex[:8]

falhas = []


def checar(cond, msg):
    if cond:
        print(f"  ok   {msg}")
    else:
        print(f"  FALHOU  {msg}")
        falhas.append(msg)


def criar_talento(nome="Fulano de Teste", email=True):
    corpo = {"nome": nome, "telefone": "61999990000",
             "cargos_interesse": ["Vigia"], "consentimento_lgpd": True}
    if email:
        corpo["email"] = f"talento-{SUF}-{uuid.uuid4().hex[:6]}@exemplo.com"
    r = c.post("/api/talentos", json=corpo)
    assert r.status_code in (200, 201), f"criar talento: {r.status_code} {r.text}"
    return r.json()["id"]


def criar_vaga(titulo, cargo="Vigia"):
    r = c.post("/api/rh/vagas", headers=RH, json={
        "titulo": titulo, "descricao": "Posto 12x36 noturno.", "cargo": cargo})
    assert r.status_code in (200, 201), f"criar vaga: {r.status_code} {r.text}"
    return r.json()["id"]


# CONSTANTES do teste — a referência NUNCA é lida do sistema sob teste.
ANCORA_CUSTOM = "ANCORA-CUSTOM-DO-TESTE-NAO-VEM-DA-CONSTANTE"
PERGUNTA_CUSTOM = "PERGUNTA-CUSTOM-COMPORTAMENTAL-DO-TESTE"
PERGUNTA_CUSTOM_SIT = "PERGUNTA-CUSTOM-SITUACIONAL-DO-TESTE"
ANCORA_EDITADA = "ANCORA-DEPOIS-DA-EDICAO-QUE-NAO-PODE-VAZAR"


def competencias_custom(chave="soldagem", nome="Solda e acabamento",
                        ancora4=ANCORA_CUSTOM):
    return [{
        "chave": chave, "nome": nome,
        "ancoras": {"4": ancora4, "3": "Ancora 3 do teste",
                    "2": "Ancora 2 do teste", "1": "Ancora 1 do teste"},
        "perguntas": {"comportamental": PERGUNTA_CUSTOM,
                      "situacional": PERGUNTA_CUSTOM_SIT},
    }]


# --------------------------------------------------------------------------
print("\n0. Pré-condição: existe um roteiro padrão PUBLICADO")
# --------------------------------------------------------------------------
# Por que este bloco existe: rodando as MUTAÇÕES desta leva, a que removia o
# guard de `arquivar` deixou o roteiro padrão ARQUIVADO no banco — e o estado
# sobreviveu à restauração do código. A partir dali, todo o resto do arquivo
# falhava por um motivo que não tinha nada a ver com o que estava sendo testado.
#
# Teste que depende de estado deixado por outra execução é a mesma armadilha do
# `test_jornadas_confirmar_lote` ("só passa em banco limpo"), de cabeça para
# baixo. Aqui a pré-condição é conferida e ANUNCIADA — se o padrão estiver
# quebrado, o teste diz isso em vez de acusar quinze falhas sem causa.
inicio = c.get("/api/rh/roteiros-entrevista?incluir_arquivados=true", headers=RH).json()
pub_padrao = [i for i in inicio["itens"] if i["padrao"] and i["status"] == "publicado"]
if not pub_padrao:
    quebrados = [i for i in inicio["itens"] if i["padrao"]]
    print(f"     ATENÇÃO: nenhum padrão publicado (marcados padrão: "
          f"{[(i['nome'], i['status']) for i in quebrados]}). Restaurando pelo "
          f"BANCO para que as falhas seguintes sejam as REAIS.")
    # Pelo banco, não pela rota: `publicar` recusa roteiro ARQUIVADO com 409 —
    # e é assim que tem que ser (arquivado é aposentado). Consertar
    # pré-condição de teste não é caso de afrouxar a regra do sistema.
    import sqlalchemy as _sa

    from app.core.db import SessionLocal as _S0
    from app.models.roteiro_entrevista import RoteiroEntrevista as _R0
    with _S0() as _db0:
        alvo = _db0.scalar(_sa.select(_R0).where(_R0.padrao.is_(True)))
        if alvo is None:
            alvo = _db0.scalar(_sa.select(_R0).where(_R0.cargo_norm.is_(None))
                               .order_by(_R0.criado_em))
        if alvo is not None:
            alvo.padrao, alvo.status, alvo.arquivado_em = True, "publicado", None
            _db0.commit()

# --------------------------------------------------------------------------
print("\n1. O roteiro PADRÃO foi semeado pela migration e é o fundo da herança")
# --------------------------------------------------------------------------
lista = c.get("/api/rh/roteiros-entrevista", headers=RH)
checar(lista.status_code == 200, f"GET /rh/roteiros-entrevista responde 200 ({lista.status_code})")
padroes = [i for i in lista.json()["itens"] if i["padrao"]]
checar(len(padroes) == 1,
       f"existe EXATAMENTE um roteiro padrão (achados: {len(padroes)}) — dois "
       "fundos de herança seriam escolhidos por ordem, em silêncio")
padrao = padroes[0] if padroes else {}
checar(padrao.get("status") == "publicado",
       "o padrão nasce PUBLICADO — semeado assim, senão o 1º /formulario após o "
       "deploy abriria sem instrumento")
checar(len(padrao.get("competencias") or []) == 4,
       f"o padrão tem as 4 competências da semente ({len(padrao.get('competencias') or [])})")

# As âncoras voltam com chave de TEXTO ("4"), não inteiro — JSON não tem chave
# numérica, e ler `ancoras[4]` quebraria só depois de alguém editar pela tela.
if padrao.get("competencias"):
    a = padrao["competencias"][0]["ancoras"]
    checar(set(a.keys()) == {"1", "2", "3", "4"},
           f"as âncoras vêm com chave de TEXTO '1'..'4' (veio: {sorted(a.keys())})")


# --------------------------------------------------------------------------
print("\n2. Cenário 22 — roteiro em RASCUNHO não pode ser usado")
# --------------------------------------------------------------------------
# Mutação verificada: tirar o filtro `status == publicado` de `resolver_roteiro`
# -> o rascunho passa a ser servido e este bloco falha.
NOME_RASCUNHO = f"Rascunho que nao pode ser usado {SUF}"
r = c.post("/api/rh/roteiros-entrevista", headers=RH, json={
    "nome": NOME_RASCUNHO, "cargo": f"CargoRascunho{SUF}",
    "competencias": competencias_custom()})
checar(r.status_code == 201, f"cria roteiro ({r.status_code} {r.text[:120]})")
rascunho = r.json()
checar(rascunho["status"] == "rascunho",
       "roteiro NASCE rascunho, sempre — publicar é ato separado e deliberado")

# Pedir o formulário APONTANDO para o rascunho: não pode servi-lo.
f = c.get(f"/api/rh/entrevistas/formulario?roteiro_id={rascunho['id']}", headers=RH)
checar(f.status_code == 200, "o formulário responde 200 mesmo com roteiro em rascunho")
servido = f.json()
texto_servido = str(servido["competencias"])
checar(ANCORA_CUSTOM not in texto_servido,
       "o instrumento do RASCUNHO **não** é servido (é a trava que sustenta "
       "'aprovado ANTES de ser usado')")
checar((servido.get("roteiro") or {}).get("padrao") is True,
       "e cai no PADRÃO em vez de erro ou tela vazia")
checar(bool(servido.get("aviso_roteiro")),
       "e ANUNCIA que o roteiro pedido não está publicado — nada é filtrado em silêncio")

# Também não pode ser usado ao CRIAR a entrevista.
t_rasc = criar_talento("Pessoa Do Rascunho")
ent = c.post("/api/rh/entrevistas", headers=RH, json={
    "talento_id": t_rasc, "tipo": "entrevista", "roteiro_id": rascunho["id"]}).json()
checar(ent.get("roteiro_id") != rascunho["id"],
       "entrevista criada com roteiro em rascunho NÃO o adota (cai no padrão)")
checar(ANCORA_CUSTOM not in str(ent.get("roteiro_competencias") or []),
       "e o snapshot dela não contém o instrumento não aprovado")


# --------------------------------------------------------------------------
print("\n3. Publicar é o ATO de aprovação — e aí sim o roteiro vale")
# --------------------------------------------------------------------------
r = c.post(f"/api/rh/roteiros-entrevista/{rascunho['id']}/publicar", headers=RH)
checar(r.status_code == 200, f"publica ({r.status_code} {r.text[:120]})")
pub = r.json()
checar(pub["status"] == "publicado", "status virou publicado")
checar(pub["publicado_em"] is not None and pub["publicado_por"],
       "o ATO fica carimbado com quem publicou e quando (é o que a defesa invoca)")

f = c.get(f"/api/rh/entrevistas/formulario?roteiro_id={pub['id']}", headers=RH).json()
checar(ANCORA_CUSTOM in str(f["competencias"]),
       "publicado, o instrumento passa a ser servido")


# --------------------------------------------------------------------------
print("\n4. Cenário 23 — cargo SEM roteiro cai no padrão, NUNCA em erro")
# --------------------------------------------------------------------------
# Mutação verificada: fazer `resolver_roteiro` levantar/devolver None quando não
# acha o cargo -> o formulário quebra ou volta vazio, e este bloco falha.
f = c.get(f"/api/rh/entrevistas/formulario?cargo=CargoQueNaoExiste{SUF}", headers=RH)
checar(f.status_code == 200,
       f"cargo desconhecido responde 200, não erro ({f.status_code})")
corpo = f.json()
checar(len(corpo["competencias"]) >= 1, "e devolve um instrumento (nunca tela vazia)")
checar((corpo.get("roteiro") or {}).get("padrao") is True,
       "o instrumento devolvido é o do roteiro PADRÃO")


# --------------------------------------------------------------------------
print("\n5. Herança: cargo+senioridade vence cargo, que vence o padrão")
# --------------------------------------------------------------------------
CARGO = f"Vigia Heranca {SUF}"
ANCORA_CARGO = "ANCORA-DO-ROTEIRO-DE-CARGO"
ANCORA_SENIOR = "ANCORA-DO-ROTEIRO-DE-CARGO-MAIS-SENIORIDADE"

r_cargo = c.post("/api/rh/roteiros-entrevista", headers=RH, json={
    "nome": f"So cargo {SUF}", "cargo": CARGO,
    "competencias": competencias_custom(ancora4=ANCORA_CARGO)}).json()
c.post(f"/api/rh/roteiros-entrevista/{r_cargo['id']}/publicar", headers=RH)

r_sen = c.post("/api/rh/roteiros-entrevista", headers=RH, json={
    "nome": f"Cargo mais senioridade {SUF}", "cargo": CARGO, "senioridade": "senior",
    "competencias": competencias_custom(ancora4=ANCORA_SENIOR)}).json()
c.post(f"/api/rh/roteiros-entrevista/{r_sen['id']}/publicar", headers=RH)

f = c.get(f"/api/rh/entrevistas/formulario?cargo={CARGO}", headers=RH).json()
checar(ANCORA_CARGO in str(f["competencias"]),
       "sem senioridade, vence o roteiro DO CARGO")
f = c.get(f"/api/rh/entrevistas/formulario?cargo={CARGO}&senioridade=senior",
          headers=RH).json()
checar(ANCORA_SENIOR in str(f["competencias"]),
       "com senioridade, vence o roteiro do CARGO + SENIORIDADE (o mais específico)")
f = c.get(f"/api/rh/entrevistas/formulario?cargo={CARGO}&senioridade=junior",
          headers=RH).json()
checar(ANCORA_CARGO in str(f["competencias"]),
       "senioridade SEM roteiro próprio cai no do cargo, não no padrão")

# O casamento é por `normalizar_cargo` — cargo é texto livre e a base tem o
# mesmo cargo escrito de três formas.
f = c.get(f"/api/rh/entrevistas/formulario?cargo={CARGO.upper()}  ", headers=RH).json()
checar(ANCORA_CARGO in str(f["competencias"]),
       "CAIXA ALTA e espaço sobrando casam o mesmo roteiro (normalizar_cargo)")

# Senioridade fora da lista fixa é recusada NA ENTRADA — texto livre viraria
# 'pleno'/'Pleno'/'plena' e a herança pararia de casar em silêncio.
r = c.post("/api/rh/roteiros-entrevista", headers=RH, json={
    "nome": f"Senioridade invalida {SUF}", "cargo": CARGO, "senioridade": "estagiario",
    "competencias": competencias_custom()})
checar(r.status_code == 422, f"senioridade fora da lista fixa é recusada ({r.status_code})")


# --------------------------------------------------------------------------
print("\n6. Cenário 21 — editar roteiro publicado NÃO altera entrevista já feita")
# --------------------------------------------------------------------------
# ESTE é o teste que justifica o `roteiro_snapshot`.
# Mutação verificada: fazer o `_dump` ler as competências do ROTEIRO VIVO
# (`db.get(RoteiroEntrevista, e.roteiro_id).competencias`) em vez do snapshot
# -> a entrevista antiga passa a mostrar `ANCORA_EDITADA` e este bloco falha.
CARGO_SNAP = f"Cargo Snapshot {SUF}"
ANCORA_ORIGINAL = "ANCORA-ORIGINAL-COM-QUE-A-NOTA-FOI-DADA"

r_snap = c.post("/api/rh/roteiros-entrevista", headers=RH, json={
    "nome": f"Roteiro do snapshot {SUF}", "cargo": CARGO_SNAP,
    "competencias": competencias_custom(ancora4=ANCORA_ORIGINAL)}).json()
c.post(f"/api/rh/roteiros-entrevista/{r_snap['id']}/publicar", headers=RH)

t_snap = criar_talento("Pessoa Do Snapshot")
ent_snap = c.post("/api/rh/entrevistas", headers=RH, json={
    "talento_id": t_snap, "tipo": "entrevista", "cargo": CARGO_SNAP}).json()
checar(ent_snap["roteiro_id"] == r_snap["id"],
       "a entrevista adota o roteiro resolvido pelo cargo")
checar(ANCORA_ORIGINAL in str(ent_snap["roteiro_competencias"]),
       "e guarda o SNAPSHOT do instrumento no nascimento")

# Agora EDITA o roteiro publicado.
r = c.put(f"/api/rh/roteiros-entrevista/{r_snap['id']}", headers=RH, json={
    "competencias": competencias_custom(ancora4=ANCORA_EDITADA)})
checar(r.status_code == 200, f"edita o roteiro publicado ({r.status_code})")
editado = r.json()
checar(editado["versao"] == 2,
       f"editar publicado gera a VERSÃO SEGUINTE (veio v{editado['versao']})")
checar(editado["status"] == "rascunho",
       "e ele volta a RASCUNHO — enquanto é reescrito, não pode ser escolhido")

# A entrevista de antes continua com o instrumento de antes.
depois = c.get(f"/api/rh/entrevistas/{ent_snap['id']}", headers=RH).json()
checar(ANCORA_ORIGINAL in str(depois["roteiro_competencias"]),
       "a entrevista JÁ FEITA continua mostrando a âncora ORIGINAL")
checar(ANCORA_EDITADA not in str(depois["roteiro_competencias"]),
       "e NÃO enxerga o texto novo — editar o roteiro não reescreve, "
       "retroativamente, o que a nota significava")


# --------------------------------------------------------------------------
print("\n7. Cenário 24 — roteiro ARQUIVADO, entrevistas antigas seguem legíveis")
# --------------------------------------------------------------------------
c.post(f"/api/rh/roteiros-entrevista/{r_snap['id']}/publicar", headers=RH)
r = c.post(f"/api/rh/roteiros-entrevista/{r_snap['id']}/arquivar", headers=RH,
           json={"motivo": "cargo descontinuado"})
checar(r.status_code == 200, f"arquiva o roteiro ({r.status_code} {r.text[:120]})")

depois = c.get(f"/api/rh/entrevistas/{ent_snap['id']}", headers=RH).json()
checar(ANCORA_ORIGINAL in str(depois["roteiro_competencias"]),
       "com o roteiro ARQUIVADO, a entrevista continua legível pelo snapshot")

# E o arquivado sai da resolução (não pode mais ser escolhido).
f = c.get(f"/api/rh/entrevistas/formulario?cargo={CARGO_SNAP}", headers=RH).json()
checar(ANCORA_ORIGINAL not in str(f["competencias"]),
       "roteiro arquivado deixa de ser resolvido para novas entrevistas")
checar((f.get("roteiro") or {}).get("padrao") is True,
       "e o cargo volta a cair no padrão")


# --------------------------------------------------------------------------
print("\n8. Cenário 25 — o roteiro PADRÃO não se apaga nem se arquiva")
# --------------------------------------------------------------------------
# Mutação verificada: tirar o `if r.padrao: 409` de `arquivar`/`excluir`
# -> o padrão é removido, a herança fica sem fundo e este bloco falha.
r = c.post(f"/api/rh/roteiros-entrevista/{padrao['id']}/arquivar", headers=RH, json={})
checar(r.status_code == 409,
       f"arquivar o padrão é recusado com 409 ({r.status_code})")
r = c.delete(f"/api/rh/roteiros-entrevista/{padrao['id']}", headers=RH)
checar(r.status_code == 409,
       f"excluir o padrão é recusado com 409 ({r.status_code})")

# E continua lá, servindo como fundo.
f = c.get("/api/rh/entrevistas/formulario", headers=RH).json()
checar((f.get("roteiro") or {}).get("padrao") is True,
       "o padrão continua sendo o fundo da herança depois das duas recusas")

# Roteiro que JÁ SUSTENTOU entrevista também não se apaga — o caminho é arquivar.
r = c.delete(f"/api/rh/roteiros-entrevista/{r_cargo['id']}", headers=RH)
if r.status_code == 204:
    checar(True, "roteiro sem uso pode ser excluído (passa pela lixeira)")
else:
    checar(r.status_code == 409, f"roteiro em uso é recusado com 409 ({r.status_code})")

# Trocar o padrão é possível (senão "não se apaga" viraria "não se troca"),
# mas só com roteiro PUBLICADO.
r = c.post("/api/rh/roteiros-entrevista", headers=RH, json={
    "nome": f"Candidato a padrao {SUF}", "competencias": competencias_custom()}).json()
resp = c.post(f"/api/rh/roteiros-entrevista/{r['id']}/tornar-padrao", headers=RH)
checar(resp.status_code == 409,
       f"tornar padrão um RASCUNHO é recusado ({resp.status_code}) — o padrão é "
       "usado sem escolha do RH, então tem que ter passado pela aprovação")


# --------------------------------------------------------------------------
print("\n9. § 14.2 — as perguntas novas de triagem, sem nota e sem competência")
# --------------------------------------------------------------------------
f = c.get("/api/rh/entrevistas/formulario", headers=RH).json()
chaves = {p["chave"] for p in f["triagem"]["perguntas"]}
esperadas = {"tem_disponibilidade_imediata", "tem_documentacao",
             "ja_trabalhou_no_cliente", "aceita_uniforme_epi"}
checar(esperadas <= chaves,
       f"as 4 perguntas novas do § 14.2 estão na triagem (faltam: {esperadas - chaves})")
checar(len(chaves) == 9, f"a triagem tem as 9 perguntas (veio {len(chaves)})")
checar("recebe_seguro_desemprego" in chaves,
       "e o seguro-desemprego continua lá (decisão 4 do Bruno)")
# Continua SEM nota, competência ou âncora — é outra natureza (§ 4.1).
checar(all("ancoras" not in p and "nota" not in p for p in f["triagem"]["perguntas"]),
       "nenhuma pergunta de triagem ganhou âncora ou nota — triagem NÃO é "
       "entrevista curta")

t_tri = criar_talento("Pessoa Triagem Nova")
e_tri = c.post("/api/rh/entrevistas", headers=RH,
               json={"talento_id": t_tri, "tipo": "triagem"}).json()["id"]
r = c.put(f"/api/rh/entrevistas/{e_tri}", headers=RH, json={
    "triagem": {"tem_documentacao": "nao", "aceita_uniforme_epi": "sim",
                "ja_trabalhou_no_cliente": "nao_sei",
                "tem_disponibilidade_imediata": "sim"},
    "triagem_desfecho": "segue"})
checar(r.status_code == 200,
       f"as perguntas novas são aceitas no preenchimento ({r.status_code} {r.text[:100]})")
r = c.put(f"/api/rh/entrevistas/{e_tri}", headers=RH,
          json={"triagem": {"tem_documentacao": "talvez"}})
checar(r.status_code == 422, "e continuam recusando resposta fora de sim/nao/nao_sei")


# --------------------------------------------------------------------------
print("\n10. § 14.3 / cenário 30 — tag de reaproveitamento, PROPOSTA e em lote")
# --------------------------------------------------------------------------
# Mutação verificada: aplicar a tag automaticamente ao excluir a vaga (sem o
# POST /reaproveitar) -> o teste que exige a tag AUSENTE antes da confirmação
# falha.
TITULO_REAPROVEITA = f"Vaga que sera excluida {SUF}"
CARGO_REAPROVEITA = f"Recepcionista {SUF}"
v_reap = criar_vaga(TITULO_REAPROVEITA, cargo=CARGO_REAPROVEITA)
pessoas_reap = [criar_talento(f"Entrevistado {i} {SUF}") for i in range(3)]
for tid in pessoas_reap:
    c.post("/api/rh/entrevistas", headers=RH,
           json={"talento_id": tid, "tipo": "entrevista", "vaga_id": v_reap})
# A MESMA pessoa entrevistada duas vezes (triagem + presencial) conta UMA vez.
c.post("/api/rh/entrevistas", headers=RH,
       json={"talento_id": pessoas_reap[0], "tipo": "triagem", "vaga_id": v_reap})

prev = c.get(f"/api/rh/vagas/{v_reap}/entrevistados", headers=RH)
checar(prev.status_code == 200, f"a prévia responde 200 ({prev.status_code})")
p = prev.json()
checar(p["total"] == 3,
       f"lista 3 PESSOAS, não 4 entrevistas — quem foi entrevistado duas vezes "
       f"é uma pessoa a taguear (veio {p['total']})")
checar(CARGO_REAPROVEITA in (p.get("tag_sugerida") or ""),
       f"SUGERE a tag a partir do cargo da vaga (veio {p.get('tag_sugerida')!r})")

# Antes de confirmar, NINGUÉM está tagueado — o sistema propõe, o RH confirma.
antes = c.get(f"/api/rh/crm/pessoa?talento_id={pessoas_reap[0]}", headers=RH).json()
TAG_REAP = f"reaproveitar: {CARGO_REAPROVEITA}"
checar(TAG_REAP not in [t["nome"] for t in antes.get("tags", [])],
       "a tag NÃO foi aplicada sozinha — tag automática vira ruído e o RH deixa "
       "de confiar na tag")

r = c.post("/api/rh/entrevistas/reaproveitar", headers=RH, json={
    "tag": TAG_REAP, "vaga_titulo": TITULO_REAPROVEITA,
    "pessoas": [{"talento_id": t} for t in pessoas_reap]})
checar(r.status_code == 200, f"aplica em lote ({r.status_code} {r.text[:120]})")
checar(r.json()["marcadas"] == 3, f"marca as 3 ({r.json().get('marcadas')})")

depois = c.get(f"/api/rh/crm/pessoa?talento_id={pessoas_reap[0]}", headers=RH).json()
checar(TAG_REAP in [t["nome"] for t in depois.get("tags", [])],
       "e a tag do mini-CRM aparece na pessoa (PessoaTag reusada, sem campo novo)")

# Idempotente: aplicar de novo não duplica.
r2 = c.post("/api/rh/entrevistas/reaproveitar", headers=RH, json={
    "tag": TAG_REAP, "pessoas": [{"talento_id": t} for t in pessoas_reap]})
checar(r2.json()["marcadas"] == 0, "aplicar de novo não duplica (idempotente)")

# A entrevista sobrevive à exclusão da vaga E a pessoa fica tagueada.
r = c.delete(f"/api/rh/vagas/{v_reap}", headers=RH)
checar(r.status_code in (200, 204), f"exclui a vaga ({r.status_code})")
ainda = c.get(f"/api/rh/crm/pessoa?talento_id={pessoas_reap[0]}", headers=RH).json()
checar(TAG_REAP in [t["nome"] for t in ainda.get("tags", [])],
       "depois de a vaga sumir, a PESSOA continua marcada como oportunidade")


# --------------------------------------------------------------------------
print("\n11. § 14.4 / cenário 29 — online SEM link não se marca")
# --------------------------------------------------------------------------
# Mutação verificada: tirar a checagem de `erros_de_modalidade` da criação
# -> a entrevista online nasce sem link e este bloco falha.
t_on = criar_talento("Pessoa Online")
amanha = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
r = c.post("/api/rh/entrevistas", headers=RH, json={
    "talento_id": t_on, "tipo": "entrevista", "marcada_para": amanha,
    "modalidade": "online"})
checar(r.status_code == 422,
       f"online sem link é recusada ({r.status_code}) — o convite sairia sem "
       "dizer por onde entrar")
r = c.post("/api/rh/entrevistas", headers=RH, json={
    "talento_id": t_on, "tipo": "entrevista", "marcada_para": amanha,
    "modalidade": "online", "link_reuniao": "https://teams.exemplo/reuniao-abc"})
checar(r.status_code == 201, f"com link, marca ({r.status_code} {r.text[:120]})")
ent_online = r.json()
checar(ent_online["modalidade"] == "online", "a modalidade fica gravada")

# Presencial sem endereço é TOLERADO de propósito: "telefone", "nossa sede" e o
# combinado por WhatsApp são rotina; travar aí faria o RH inventar texto.
r = c.post("/api/rh/entrevistas", headers=RH, json={
    "talento_id": criar_talento("Pessoa Presencial"), "tipo": "entrevista",
    "marcada_para": amanha, "modalidade": "presencial"})
checar(r.status_code == 201, "presencial sem endereço é permitida (não se trava)")


# --------------------------------------------------------------------------
print("\n12. Cenário 26 — pessoa SEM e-mail: lembrete desligado COM o motivo")
# --------------------------------------------------------------------------
# Mutação verificada: fazer `motivo_sem_envio` devolver None sempre -> a tela
# passa a mostrar o lembrete como ligado para quem não tem e-mail, e falha aqui.
t_sem = criar_talento("Pessoa Sem Email", email=False)
r = c.post("/api/rh/entrevistas", headers=RH, json={
    "talento_id": t_sem, "tipo": "entrevista", "marcada_para": amanha,
    "modalidade": "presencial", "local": "Sede", "enviar_convite": True})
checar(r.status_code == 201, f"a entrevista é criada mesmo assim ({r.status_code})")
sem_email = r.json()
checar(sem_email["motivo_sem_lembrete"],
       "a resposta DIZ o motivo de o lembrete estar desligado — nunca falha calada")
checar("e-mail" in (sem_email["motivo_sem_lembrete"] or "").lower(),
       f"e o motivo aponta a causa real ({sem_email['motivo_sem_lembrete']!r})")
checar(sem_email.get("convite", {}).get("enviado") is False,
       "o convite não sai, e a resposta ANUNCIA isso em vez de fingir sucesso")
checar(sem_email["convite_enviado_em"] is None,
       "e nada é carimbado como enviado")


# --------------------------------------------------------------------------
print("\n13. Cenários 27 e 28 — o .ics: UID estável, SEQUENCE que cresce, CANCEL")
# --------------------------------------------------------------------------
# ESTE é o bloco que impede a entrevista fantasma na agenda de alguém.
# Mutação verificada: trocar `uid_da_entrevista` por `uuid4()` a cada chamada
# -> o UID muda entre convite e remarcação e este bloco falha.
from app.services import calendario  # noqa: E402

EID = uuid.UUID("00000000-0000-4000-8000-000000000abc")
INICIO = datetime(2026, 9, 10, 17, 0, tzinfo=timezone.utc)   # 14h de Brasília

ics1 = calendario.gerar_ics(entrevista_id=EID, inicio=INICIO,
                            resumo="Entrevista", local="Sede",
                            sequencia=0).decode("utf-8")
ics2 = calendario.gerar_ics(entrevista_id=EID, inicio=INICIO + timedelta(days=1),
                            resumo="Entrevista", local="Sede",
                            sequencia=1).decode("utf-8")

# A referência é uma CONSTANTE do teste, não o UID lido do primeiro arquivo —
# comparar ics1 com ics2 seria tautologia (mutação que randomiza os dois lados
# mudaria ambos e a asserção... na verdade falharia; mas a constante prova o
# FORMATO também, que a comparação cruzada não prova).
UID_ESPERADO = f"UID:entrevista-{EID}@entrevistas.greenhouse"
checar(UID_ESPERADO in ics1, f"o UID é derivado do id da entrevista ({UID_ESPERADO})")
checar(UID_ESPERADO in ics2,
       "a REMARCAÇÃO usa o MESMO UID — é o que faz o Outlook ATUALIZAR o "
       "compromisso em vez de criar um segundo no horário velho")
checar("SEQUENCE:0" in ics1 and "SEQUENCE:1" in ics2,
       "e a SEQUENCE cresce — com sequência igual a atualização é ignorada em silêncio")
checar("METHOD:REQUEST" in ics1, "convite normal vai como METHOD:REQUEST")

ics_cancel = calendario.gerar_ics(entrevista_id=EID, inicio=INICIO,
                                  resumo="Entrevista", sequencia=2, cancelar=True
                                  ).decode("utf-8")
checar("METHOD:CANCEL" in ics_cancel and "STATUS:CANCELLED" in ics_cancel,
       "cancelar manda METHOD:CANCEL — sem isso o compromisso fica na agenda "
       "depois de cancelado e a pessoa vem")
checar(UID_ESPERADO in ics_cancel,
       "com o MESMO UID (senão cancelaria um compromisso que não existe)")

# TZID de Brasília, nunca UTC solto: o container roda em UTC (armadilha da
# v2.41) e o convite chegaria três horas adiantado.
checar("TZID=America/Sao_Paulo" in ics1,
       "o DTSTART leva TZID=America/Sao_Paulo")
checar("DTSTART;TZID=America/Sao_Paulo:20260910T140000" in ics1,
       f"e a hora sai em BRASÍLIA (17h UTC -> 14h). Achado: "
       f"{[l for l in ics1.splitlines() if l.startswith('DTSTART')]}")
checar("BEGIN:VTIMEZONE" in ics1 and "TZOFFSETTO:-0300" in ics1,
       "o VTIMEZONE vai declarado (cliente que não conhece o TZID cairia em UTC)")
checar(ics1.endswith("\r\n") and "\r\n" in ics1,
       "linhas terminam em CRLF (exigência do RFC; cliente rígido recusa só \\n)")


# --------------------------------------------------------------------------
print("\n14. O convite REAL: sequência incrementa na remarcação, e cancelar avisa")
# --------------------------------------------------------------------------
from app.core.db import SessionLocal  # noqa: E402
from app.models.entrevista import Entrevista  # noqa: E402

# Marca com convite (o envio de e-mail em si depende de SMTP, que não há no
# teste — o que se afirma aqui é a MECÂNICA da sequência, que é o que estraga a
# agenda quando erra).
t_seq = criar_talento("Pessoa Da Sequencia")
ent_seq = c.post("/api/rh/entrevistas", headers=RH, json={
    "talento_id": t_seq, "tipo": "entrevista", "marcada_para": amanha,
    "modalidade": "presencial", "local": "Sede", "enviar_convite": True}).json()

with SessionLocal() as db:
    e = db.get(Entrevista, uuid.UUID(ent_seq["id"]))
    # Simula "o convite saiu" para exercitar o caminho de ATUALIZAÇÃO — sem
    # SMTP no teste, o carimbo não vem do envio real.
    e.convite_enviado_em = datetime.now(timezone.utc)
    e.sequencia_convite = 0
    db.commit()

depois = (datetime.now(timezone.utc) + timedelta(days=3)).isoformat()
r = c.put(f"/api/rh/entrevistas/{ent_seq['id']}", headers=RH, json={
    "marcada_para": depois, "reenviar_convite": True})
checar(r.status_code == 200, f"remarca pela ficha ({r.status_code} {r.text[:120]})")
checar(r.json()["sequencia_convite"] == 1,
       f"a SEQUENCE incrementou no reenvio (veio {r.json()['sequencia_convite']}) — "
       "sem isso a remarcação é ignorada e a pessoa vem no horário velho")


# --------------------------------------------------------------------------
print("\n15. O lembrete da véspera: janela, uma vez só, e nunca do passado")
# --------------------------------------------------------------------------
# Mutação verificada: tirar o `if e.lembrete_enviado_em is not None: return False`
# de `deve_lembrar` -> o lembrete passa a sair todo dia e este bloco falha.
from app.services import entrevista_convite as conv  # noqa: E402
from app.services.entrevistas import LEMBRETE_HORAS_ANTES  # noqa: E402


class _Fake:
    """Objeto mínimo com a forma que `deve_lembrar` lê. Evita gravar 5 registros
    no banco para exercitar uma função pura de janela."""

    def __init__(self, **kw):
        self.status = "marcada"
        self.marcada_para = None
        self.lembrete_enviado_em = None
        self.__dict__.update(kw)


AGORA = datetime(2026, 9, 1, 12, 0, tzinfo=timezone.utc)
checar(conv.deve_lembrar(_Fake(marcada_para=AGORA + timedelta(hours=20)), AGORA),
       "entrevista daqui a 20h entra na janela do lembrete")
checar(not conv.deve_lembrar(_Fake(marcada_para=AGORA + timedelta(days=10)), AGORA),
       "entrevista daqui a 10 dias ainda NÃO (seria lembrete cedo demais)")
checar(not conv.deve_lembrar(_Fake(marcada_para=AGORA - timedelta(hours=2)), AGORA),
       "entrevista que JÁ PASSOU não recebe lembrete — quem cobra essa é a fila "
       "de pendências, que fala com o RH, não com a pessoa")
checar(not conv.deve_lembrar(
    _Fake(marcada_para=AGORA + timedelta(hours=20),
          lembrete_enviado_em=AGORA - timedelta(hours=1)), AGORA),
    "já lembrado NÃO lembra de novo — repetir ensina a pessoa a ignorar o e-mail")
checar(not conv.deve_lembrar(
    _Fake(status="cancelada", marcada_para=AGORA + timedelta(hours=20)), AGORA),
    "entrevista cancelada não recebe lembrete")

# A janela tem que ser MAIOR que a cadência do worker (24h): com 24h exatos, a
# entrevista marcada para daqui a 23h fica invisível entre duas passadas e o
# lembrete nunca sai — falha silenciosa, porque nada acusa e-mail não enviado.
checar(LEMBRETE_HORAS_ANTES > 24,
       f"a janela ({LEMBRETE_HORAS_ANTES}h) é maior que as 24h de sono do worker")


# --------------------------------------------------------------------------
print("\n16. Os e-mails novos nascem no CATÁLOGO (regra da v2.21)")
# --------------------------------------------------------------------------
from app.services.email_templates import CATALOGO_POR_CHAVE, renderizar  # noqa: E402

for chave in ("entrevista_marcada", "entrevista_lembrete", "entrevista_cancelada"):
    checar(chave in CATALOGO_POR_CHAVE,
           f"'{chave}' está no CATALOGO (editável com preview e histórico)")

m = CATALOGO_POR_CHAVE.get("entrevista_marcada")
checar(m and "data_hora" in m.obrigatorias and "onde" in m.obrigatorias,
       "`data_hora` e `onde` são OBRIGATÓRIAS — sem elas o e-mail sai bonito e "
       "não diz quando nem aonde ir")

# `{{onde}}` é montado em PYTHON conforme a modalidade (o template é
# apresentação, nunca decisão — regra da v2.06).
checar("teams.exemplo" in conv.onde_e("online", None, "https://teams.exemplo/x"),
       "online: `onde` leva o LINK")
checar("SIA Trecho" in conv.onde_e("presencial", "SIA Trecho 3", None),
       "presencial: `onde` leva o ENDEREÇO")
checar(conv.onde_e("presencial", None, None).strip() != "",
       "e sem nenhum dos dois a frase não fica VAZIA (buraco no e-mail)")

with SessionLocal() as db:
    assunto, texto, html = renderizar(db, "entrevista_marcada", {
        "primeiro_nome": "Maria", "nome": "Maria Souza",
        "data_hora": "12/08/2026 às 14:00",
        "onde": "É presencial, em: SIA Trecho 3", "vaga": "Vigia"})
checar("12/08/2026" in texto and "SIA Trecho 3" in texto,
       "o e-mail renderizado leva a data e o lugar")

# A hora sai em Brasília, como tudo que a pessoa lê.
checar(conv.data_hora_br(datetime(2026, 9, 10, 17, 0, tzinfo=timezone.utc))
       == "10/09/2026 às 14:00",
       f"a data do e-mail sai em BRASÍLIA (17h UTC -> 14h): "
       f"{conv.data_hora_br(datetime(2026, 9, 10, 17, 0, tzinfo=timezone.utc))!r}")


# --------------------------------------------------------------------------
print("\n17. O front NÃO duplica o texto do roteiro (estrutural)")
# --------------------------------------------------------------------------
# A fonte mudou (constante -> banco), o CONTRATO não: o front continua lendo de
# GET /formulario. Mutação: colar uma âncora do roteiro padrão no JSX -> falha.
f = c.get("/api/rh/entrevistas/formulario", headers=RH).json()
raiz = os.path.join(os.path.dirname(__file__), "..", "..", "frontend", "src")
trechos = [f["competencias"][0]["ancoras"]["4"][:40],
           f["competencias"][1]["perguntas"]["comportamental"][:40],
           f["triagem"]["perguntas"][0]["pergunta"][:40],
           # As perguntas NOVAS do § 14.2 também não podem ser coladas na tela.
           next(p["pergunta"] for p in f["triagem"]["perguntas"]
                if p["chave"] == "tem_documentacao")[:40]]
duplicado = []
for pasta, _, arquivos in os.walk(raiz):
    for nome in arquivos:
        if not nome.endswith(".jsx"):
            continue
        with open(os.path.join(pasta, nome), encoding="utf-8") as fh:
            conteudo = fh.read()
        for t in trechos:
            if t and t in conteudo:
                duplicado.append(f"{nome}: {t[:30]}...")
checar(not duplicado,
       f"o front não duplica texto do instrumento (achados: {duplicado})")


# --------------------------------------------------------------------------
print("\n18. N+1 — listar roteiros não faz uma consulta por roteiro")
# --------------------------------------------------------------------------
# NÃO se usa limite absoluto (mede o tamanho do banco, que cresce a cada
# execução): compara-se DUAS listagens de tamanhos diferentes.
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


q_antes = contar_consultas(
    lambda: c.get("/api/rh/roteiros-entrevista", headers=RH))
for i in range(8):
    c.post("/api/rh/roteiros-entrevista", headers=RH, json={
        "nome": f"Roteiro N mais 1 {i} {SUF}",
        "competencias": competencias_custom()})
q_depois = contar_consultas(
    lambda: c.get("/api/rh/roteiros-entrevista", headers=RH))
print(f"     antes -> {q_antes} consultas | +8 roteiros -> {q_depois} consultas")
checar(q_depois - q_antes <= 2,
       f"8 roteiros a mais não custam ~8 consultas a mais ({q_antes} -> {q_depois})")


# --------------------------------------------------------------------------
print("\n19. Rede de segurança — a ficha NUNCA abre sem instrumento")
# --------------------------------------------------------------------------
# Achado REAL desta leva, não hipótese: rodando as mutações, o padrão ficou
# ARQUIVADO no banco e `resolver_roteiro` passou a devolver None — toda ficha
# abriria vazia, SEM ERRO NENHUM. A tela pareceria funcionar e a entrevista
# seria conduzida sem roteiro, que é exatamente o que o § 6 existe para
# impedir. A rede de segurança é o último degrau da herança.
#
# Mutação verificada: tirar o fallback de `resolver_roteiro` (devolver None
# quando não há padrão publicado) -> este bloco falha.
from app.core.db import SessionLocal as _S  # noqa: E402
from app.models.roteiro_entrevista import RoteiroEntrevista as _R  # noqa: E402
from app.services.entrevistas import resolver_roteiro  # noqa: E402

with _S() as db:
    padroes_db = list(db.scalars(
        __import__("sqlalchemy").select(_R).where(_R.padrao.is_(True))))
    estados = [(p.id, p.status, p.padrao) for p in padroes_db]
    # Derruba o fundo: nenhum padrão publicado.
    for p in padroes_db:
        p.padrao = False
    db.commit()

    r = resolver_roteiro(db, cargo=f"CargoOrfao{SUF}")
    checar(r is not None,
           "sem NENHUM roteiro marcado como padrão, a resolução ainda encontra "
           "um instrumento — ficha vazia sem erro é o pior desfecho possível")

    # E o formulário continua servindo competências, nunca vazio.
    f_orfao = c.get(f"/api/rh/entrevistas/formulario?cargo=CargoOrfao{SUF}",
                    headers=RH).json()
    checar(len(f_orfao["competencias"]) >= 1,
           f"o formulário continua devolvendo instrumento "
           f"({len(f_orfao['competencias'])} competências)")

    # Devolve o banco ao estado anterior — o teste não deixa estrago para o
    # próximo (foi o defeito que este bloco existe para lembrar).
    for pid, status, padrao in estados:
        alvo = db.get(_R, pid)
        alvo.padrao, alvo.status = padrao, status
    db.commit()

restaurado = c.get("/api/rh/roteiros-entrevista", headers=RH).json()
checar(len([i for i in restaurado["itens"] if i["padrao"]]) == 1,
       "e o teste DEVOLVE o padrão ao final (não deixa estrago para a próxima "
       "execução)")


print()
if falhas:
    print(f"test_roteiros_entrevista: {len(falhas)} FALHA(S)")
    for f_ in falhas:
        print(f"  - {f_}")
    raise SystemExit(1)
print("test_roteiros_entrevista: OK")
