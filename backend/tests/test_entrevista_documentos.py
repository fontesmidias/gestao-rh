"""Fase 4 do Módulo de Entrevistas (v2.67) — os documentos e as 4 respostas.

Cobre os cenários 31–38 do § 15.6 de
`docs/planejamento/12-modulo-de-entrevistas.md`, mais a garantia que o Bruno
cravou como reprovação imediata:

    **a ficha de entrevista NÃO pode chegar ao dossiê de admissão.**

Regra da casa: **todo teste é validado por MUTAÇÃO** — reintroduz-se o defeito e
confirma-se que o teste falha. Teste que passa com o defeito presente não é
teste. As mutações verificadas estão anotadas em cada bloco.

⚠️ Regra que esta leva NÃO pode esquecer (armadilha da v2.64): **a referência do
teste é CONSTANTE conhecida do teste**, nunca valor lido do próprio sistema —
comparar a resposta com ela mesma passa com o defeito presente.

Precisa dos containers de teste:
  docker run -d --name pg-teste ... postgres:16-alpine
  docker run -d --name minio-teste ... quay.io/minio/minio server /data

Rode: PYTHONPATH=. .venv/Scripts/python.exe tests/test_entrevista_documentos.py
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

# Credencial do AMBIENTE, nunca literal (v2.71): no CI o admin nasce com a
# senha do `.env` do job, e a literal devolvia 401 -> `KeyError: 'token'`.
# Aqui pesa duas vezes: a `SENHA_RH` também assina a ficha de entrevista
# (`prova_metodo = "senha_sessao_rh"`), então a literal errada faria a
# assinatura ser recusada por "senha errada" — sintoma que aponta para o lugar
# errado do sistema.
EMAIL_RH = os.environ["RH_ADMIN_EMAIL"]
SENHA_RH = os.environ["RH_ADMIN_PASSWORD"]
r = c.post("/api/rh/auth/login", json={"email": EMAIL_RH, "senha": SENHA_RH})
assert r.status_code == 200, (
    f"login falhou ({r.status_code}): confira RH_ADMIN_EMAIL/RH_ADMIN_PASSWORD "
    f"— `criar_admin_inicial` só cria o admin com a tabela VAZIA, então num "
    f"banco com usuários antigos o admin do .env não existe. Resposta: {r.text}")
RH = {"Authorization": f"Bearer {r.json()['token']}"}

# Sufixo por EXECUÇÃO: e-mail de talento e título de vaga se repetiriam entre
# rodadas no mesmo banco, e teste que só passa em banco limpo é armadilha
# (lição do test_jornadas_confirmar_lote).
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


def entrevista_completa(talento_id, vaga_id=None):
    """Uma entrevista REALIZADA e completa — a que pode virar documento."""
    corpo = {"talento_id": talento_id, "tipo": "entrevista"}
    if vaga_id:
        corpo["vaga_id"] = vaga_id
    eid = c.post("/api/rh/entrevistas", headers=RH, json=corpo).json()["id"]
    form = c.get("/api/rh/entrevistas/formulario", headers=RH).json()
    chaves = [x["chave"] for x in form["competencias"]]
    r = c.put(f"/api/rh/entrevistas/{eid}", headers=RH, json={
        "competencias": {k: 3 for k in chaves},
        "justificativas": {k: f"Evidência observada para {k}." for k in chaves},
        "variante": "comportamental",
        "recomendacao": "contratar",
        "concluir": True})
    assert r.status_code == 200, f"concluir: {r.status_code} {r.text}"
    return eid


# ==========================================================================
print("\n1. O CATÁLOGO — os três documentos entraram (§ 15.2)")
# ==========================================================================
# É a regra que abre a leva: a v2.66 pôs os 3 E-MAILS no catálogo de e-mails e
# ZERO documento no de documentos. Mutação: remover as entradas de
# CATALOGO_ENTREVISTAS -> este bloco falha.
cat = c.get("/api/rh/documentos-sistema", headers=RH)
checar(cat.status_code == 200, f"GET /rh/documentos-sistema responde 200 ({cat.status_code})")
lista = cat.json()
por_chave = {d["chave"]: d for d in lista}

# Referência CONSTANTE do teste, não lida do sistema (armadilha da v2.64).
ESPERADOS = {
    "entrevista_ficha": "hibrido",
    "entrevista_triagem": "formulario",
    "entrevista_roteiro": "hibrido",
}
for chave, formato in ESPERADOS.items():
    checar(chave in por_chave, f"'{chave}' está no catálogo de documentos")
    if chave in por_chave:
        checar(por_chave[chave]["formato"] == formato,
               f"'{chave}' tem Formato '{formato}' (§ 15.2), veio "
               f"'{por_chave[chave]['formato']}'")
        checar(por_chave[chave]["origem"] == "entrevista",
               f"'{chave}' é da família entrevista")
        checar(not por_chave[chave]["duplicavel"],
               f"'{chave}' NÃO é duplicável (monta estrutura, não texto)")
        checar(bool(por_chave[chave]["porque_nao_duplica"]),
               f"'{chave}' explica por que não duplica")

# § 15.4 na TELA: quem lê o catálogo tem que saber que a ficha não vai ao dossiê.
onde = (por_chave.get("entrevista_ficha") or {}).get("onde_vive", "")
checar("dossiê" in onde.lower(),
       f"a tela DIZ onde a ficha vive e que não vai ao dossiê (onde_vive={onde[:50]!r})")

# A família de admissão continua inteira — a de entrevista não pode ter
# deslocado nada. A referência é o ENUM, não um número escrito aqui: contagem
# chumbada quebra a cada documento novo e legítimo sem apontar defeito (v2.25).
from app.models.assinatura import DocumentoAssinavel  # noqa: E402
da_admissao = {d["chave"] for d in lista if d["origem"] == "admissao"}
checar(da_admissao == {d.value for d in DocumentoAssinavel},
       "os documentos da admissão continuam todos no catálogo (faltando: "
       f"{ {d.value for d in DocumentoAssinavel} - da_admissao })")

# A prévia dos três gera PDF de verdade, com dados FICTÍCIOS.
for chave in ESPERADOS:
    r = c.get(f"/api/rh/documentos-sistema/{chave}/previa", headers=RH)
    checar(r.status_code == 200, f"prévia de '{chave}' responde 200 ({r.status_code})")
    checar(r.content[:4] == b"%PDF", f"prévia de '{chave}' é um PDF de verdade")
    checar(len(r.content) > 3000, f"prévia de '{chave}' não é uma folha vazia "
                                  f"({len(r.content)} bytes)")

# A amostra NUNCA vai ao banco. O id fixo `...0000e7` é o marcador: se ele
# aparecer na tabela, a prévia gravou. Mutação: dar `db.add(e)` no
# `entrevista_de_amostra` -> falha aqui.
with SessionLocal() as db:
    from app.services.entrevista_pdf import _UUID_AMOSTRA
    vazou = db.get(Entrevista, _UUID_AMOSTRA)
checar(vazou is None,
       "a entrevista de AMOSTRA nunca foi gravada no banco (dados fictícios)")


# ==========================================================================
print("\n2. A FICHA NÃO ENTRA NO DOSSIÊ (§ 15.4) — reprovação imediata")
# ==========================================================================
# *"não não. no dossiê de admissão não."* — o Bruno incluiu e corrigiu na mesma
# sessão. O dossiê CIRCULA e nota de seleção é dado sensível.
#
# MUTAÇÃO VERIFICADA: acrescentar ao `gerar_dossie` um trecho que varre
# `AssinaturaEntrevista` e inclui o `pdf_key` -> este bloco falha.
import inspect  # noqa: E402

from app.services import dossie as _dossie  # noqa: E402

fonte_dossie = inspect.getsource(_dossie)
for proibido in ("AssinaturaEntrevista", "assinatura_entrevista",
                 "entrevista_pdf", "Entrevista"):
    checar(proibido not in fonte_dossie,
           f"`services/dossie.py` não menciona '{proibido}' — a ficha de "
           f"entrevista não tem caminho para o dossiê")

# A garantia ESTRUTURAL: o dossiê lê três fontes, e nenhuma delas é usada pelo
# módulo de entrevistas. Se a assinatura da ficha passasse por
# `SolicitacaoAssinatura`, o dossiê a incluiria SEM NINGUÉM PERCEBER — ele varre
# toda solicitação concluída com pdf_final_key, sem filtrar `origem`.
checar("SolicitacaoAssinatura" in fonte_dossie,
       "(premissa do teste) o dossiê realmente varre SolicitacaoAssinatura")
from app.models.assinatura_entrevista import AssinaturaEntrevista  # noqa: E402
checar(AssinaturaEntrevista.__tablename__ == "assinatura_entrevista",
       "a assinatura da ficha mora em tabela PRÓPRIA, fora do caminho do dossiê")

# E o teste de comportamento: gera dossiê de quem TEM entrevista assinada e
# confere que o número de páginas não mudou por causa dela.
t_dos = criar_talento("Pessoa Com Dossie")
r = c.post(f"/api/rh/talentos/{t_dos}/converter", headers=RH)
checar(r.status_code in (200, 201), f"converte talento->candidato ({r.status_code})")
cand_dossie = r.json()["candidato_id"]

eid_dos = c.post("/api/rh/entrevistas", headers=RH, json={
    "candidato_id": cand_dossie, "tipo": "entrevista"}).json()["id"]
form = c.get("/api/rh/entrevistas/formulario", headers=RH).json()
chaves = [x["chave"] for x in form["competencias"]]
c.put(f"/api/rh/entrevistas/{eid_dos}", headers=RH, json={
    "competencias": {k: 4 for k in chaves},
    "justificativas": {k: "Evidência registrada." for k in chaves},
    "recomendacao": "contratar", "concluir": True})
r = c.post(f"/api/rh/entrevistas/{eid_dos}/assinar", headers=RH,
           json={"senha": SENHA_RH})
checar(r.status_code == 200, f"assina a ficha ({r.status_code} {r.text[:120]})")

from pypdf import PdfReader  # noqa: E402

import io  # noqa: E402

with SessionLocal() as db:
    from app.models.candidato import Candidato
    from app.services.dossie import gerar_dossie
    from app.services import storage
    cand = db.get(Candidato, uuid.UUID(cand_dossie))
    key = gerar_dossie(db, cand, ignorar_pendencias=True)
    db.commit()
    dados_dossie = storage.ler(key)
paginas = len(PdfReader(io.BytesIO(dados_dossie)).pages)
# Esta pessoa não assinou ficha nenhuma da admissão e não tem documento
# aprovado — o dossiê dela tem que sair VAZIO. Se a ficha de entrevista
# entrasse, teria página. A referência (0) é constante do teste.
checar(paginas == 0,
       f"o dossiê de quem tem ficha de entrevista ASSINADA continua sem "
       f"páginas dela ({paginas} páginas)")


# ==========================================================================
print("\n3. Cenário 32 — ficha INCOMPLETA não vira documento")
# ==========================================================================
# Mutação: tirar o `_exigir_documentavel` da rota -> um PDF com competência sem
# nota sairia timbrado, parecendo registro formal. Prova CONTRA a empresa.
t_inc = criar_talento("Pessoa Incompleta")
eid_inc = c.post("/api/rh/entrevistas", headers=RH,
                 json={"talento_id": t_inc, "tipo": "entrevista"}).json()["id"]
r = c.get(f"/api/rh/entrevistas/{eid_inc}/documento", headers=RH)
checar(r.status_code == 422,
       f"entrevista sem nota nenhuma não vira documento ({r.status_code})")
detalhe = r.json().get("detail") or {}
checar(bool(detalhe.get("faltando")), "e o 422 DIZ o que falta")

# Meio preenchida também não.
c.put(f"/api/rh/entrevistas/{eid_inc}", headers=RH, json={
    "competencias": {chaves[0]: 3},
    "justificativas": {chaves[0]: "Só uma competência avaliada."}})
r = c.get(f"/api/rh/entrevistas/{eid_inc}/documento", headers=RH)
checar(r.status_code == 422, "entrevista pela METADE também não vira documento")

# Assinar uma ficha incompleta também é recusado — e ANTES da senha.
r = c.post(f"/api/rh/entrevistas/{eid_inc}/assinar", headers=RH,
           json={"senha": SENHA_RH})
checar(r.status_code == 422,
       f"não se assina ficha incompleta ({r.status_code})")

# Completa -> vira documento.
eid_ok = entrevista_completa(criar_talento("Pessoa Completa"))
r = c.get(f"/api/rh/entrevistas/{eid_ok}/documento", headers=RH)
checar(r.status_code == 200, f"entrevista completa vira documento ({r.status_code})")
checar(r.content[:4] == b"%PDF", "e o documento é um PDF")


# ==========================================================================
print("\n4. § 15.3 — a ficha é assinada pelo RH, com a senha da sessão")
# ==========================================================================
eid_ass = entrevista_completa(criar_talento("Pessoa Assinatura"))

r = c.post(f"/api/rh/entrevistas/{eid_ass}/assinar", headers=RH,
           json={"senha": "senha-errada-de-proposito"})
checar(r.status_code == 401, f"senha errada não assina ({r.status_code})")

r = c.post(f"/api/rh/entrevistas/{eid_ass}/assinar", headers=RH,
           json={"senha": SENHA_RH})
checar(r.status_code == 200, f"com a senha certa, assina ({r.status_code})")
assinatura = r.json()
checar(assinatura.get("via") == 1, "nasce como via 1")
checar(len(assinatura.get("hash") or "") == 64, "e tem hash SHA-256 de 64 dígitos")

r = c.get(f"/api/rh/entrevistas/{eid_ass}/assinaturas", headers=RH)
itens = r.json()["itens"]
checar(len(itens) == 1, f"a ficha tem 1 via assinada ({len(itens)})")
checar(itens[0]["metodo"] == "senha_sessao_rh",
       f"o método registrado é `senha_sessao_rh` ({itens[0]['metodo']})")

# Cenário 31: alterar depois gera NOVA via; a anterior permanece com o hash dela.
# Mutação: fazer o `assinar` sobrescrever a via em vez de criar a seguinte ->
# a via 1 sumiria e o hash antigo deixaria de existir.
hash_via1 = itens[0]["hash"]
c.put(f"/api/rh/entrevistas/{eid_ass}", headers=RH,
      json={"observacao": "Observação acrescentada depois de assinar."})
r = c.post(f"/api/rh/entrevistas/{eid_ass}/assinar", headers=RH,
           json={"senha": SENHA_RH})
checar(r.status_code == 200 and r.json().get("via") == 2,
       f"assinar de novo cria a via 2 ({r.json().get('via')})")
itens = c.get(f"/api/rh/entrevistas/{eid_ass}/assinaturas", headers=RH).json()["itens"]
checar(len(itens) == 2, f"as DUAS vias continuam registradas ({len(itens)})")
antiga = [i for i in itens if i["via"] == 1][0]
checar(antiga["hash"] == hash_via1,
       "a via 1 mantém o hash dela — ato assinado não se edita retroativamente")
checar(antiga["substituida_em"] is not None,
       "a via 1 fica marcada como substituída (some da vista, não do registro)")

# O PDF assinado é servido do STORAGE (bytes gravados), não regerado.
r = c.get(f"/api/rh/entrevistas/{eid_ass}/documento", headers=RH)
checar(r.status_code == 200 and r.content[:4] == b"%PDF",
       "o documento assinado é servido")


# ==========================================================================
print("\n5. Cenário 33 — roteiro em RASCUNHO não gera documento")
# ==========================================================================
r = c.post("/api/rh/roteiros-entrevista", headers=RH, json={
    "nome": f"Roteiro rascunho {SUF}",
    "competencias": [{
        "chave": "teste", "nome": "Competência de teste",
        "ancoras": {"1": "a", "2": "b", "3": "c", "4": "d"},
        "perguntas": {"comportamental": "p1", "situacional": "p2"}}]})
checar(r.status_code == 201, f"cria roteiro em rascunho ({r.status_code})")
rot_id = r.json()["id"]
checar(r.json()["status"] == "rascunho", "nasce rascunho")
checar(r.json().get("tem_documento") is False,
       "e a tela já sabe que ele NÃO tem documento")

r = c.get(f"/api/rh/roteiros-entrevista/{rot_id}/documento", headers=RH)
checar(r.status_code == 409,
       f"rascunho NÃO gera documento ({r.status_code}) — o documento prova "
       f"aprovação, e rascunho não foi aprovado")

r = c.post(f"/api/rh/roteiros-entrevista/{rot_id}/publicar", headers=RH)
checar(r.status_code == 200, f"publica ({r.status_code})")
r = c.get(f"/api/rh/roteiros-entrevista/{rot_id}/documento", headers=RH)
checar(r.status_code == 200 and r.content[:4] == b"%PDF",
       f"publicado GERA o documento ({r.status_code})")


# ==========================================================================
print("\n6. § 15.5 item 3 — triagem editável, e CONTINUA sem nota")
# ==========================================================================
# O que a editabilidade não pode virar: a porta pela qual a triagem se
# transforma em entrevista curta (§ 4.1).
# Mutação: aceitar `ancoras` no roteiro de triagem -> o 422 abaixo some.
r = c.post("/api/rh/roteiros-entrevista", headers=RH, json={
    "tipo": "triagem", "nome": f"Triagem com ancora {SUF}",
    "perguntas": [{"pergunta": "Tem nota?", "ancoras": {"1": "x"}}]})
checar(r.status_code == 422,
       f"triagem com ÂNCORA é recusada ({r.status_code})")
erros = " ".join((r.json().get("detail") or {}).get("erros", []))
checar("ancoras" in erros or "âncora" in erros.lower(),
       f"e o erro NOMEIA o campo proibido ({erros[:80]!r})")

r = c.post("/api/rh/roteiros-entrevista", headers=RH, json={
    "tipo": "triagem", "nome": f"Triagem com nota {SUF}",
    "perguntas": [{"pergunta": "Vale nota?", "nota": 3}]})
checar(r.status_code == 422, "triagem com NOTA é recusada")

# Cenário 35: triagem sem NENHUMA pergunta não se publica.
r = c.post("/api/rh/roteiros-entrevista", headers=RH, json={
    "tipo": "triagem", "nome": f"Triagem vazia {SUF}", "perguntas": []})
checar(r.status_code == 422,
       f"triagem SEM pergunta é recusada ({r.status_code}) — checagem vazia "
       f"não é checagem")

# O caminho feliz: triagem válida, editável, publicável.
r = c.post("/api/rh/roteiros-entrevista", headers=RH, json={
    "tipo": "triagem", "nome": f"Triagem boa {SUF}",
    "perguntas": [{"pergunta": "Aceita a escala 12x36?"},
                  {"pergunta": "Consegue chegar ao posto?"}]})
checar(r.status_code == 201, f"triagem válida é criada ({r.status_code})")
tri_id = r.json()["id"]
checar(r.json()["tipo"] == "triagem", "e nasce com tipo=triagem")
checar(len(r.json()["perguntas"]) == 2, "com as 2 perguntas")
checar(not r.json().get("competencias"),
       "e SEM competência nenhuma — a natureza não se mistura")

# Tipo é imutável: virar entrevista carregaria respostas já dadas para uma
# ficha com nota.
r = c.put(f"/api/rh/roteiros-entrevista/{tri_id}", headers=RH,
          json={"tipo": "entrevista"})
checar(r.status_code == 422, f"o TIPO do roteiro não muda por edição ({r.status_code})")

# --- UM PADRÃO POR TIPO ---------------------------------------------------
# Defeito REAL desta leva, pego pela suíte antiga: a semente da triagem nasce
# `padrao=True` e a listagem mostrava os dois tipos juntos — apareciam DOIS
# padrões, e "qual é o padrão?" deixava de ter resposta. Pior: o
# `tornar-padrao` desmarcava o padrão do OUTRO tipo, deixando a triagem sem
# fundo de herança (ficha abrindo sem pergunta nenhuma, sem erro na tela).
#
# Mutação: tirar o filtro `tipo` da listagem OU do `tornar_padrao` -> falha.
#
# ⚠️ ANTES de medir, garante o piso da TRIAGEM. Rodar as mutações desta leva
# deixou o banco com a triagem sem `padrao` — e o estado SOBREVIVEU à
# restauração do código, fazendo o teste reprovar um código correto. É a mesma
# armadilha registrada na v2.66 (`resolver_roteiro`), e a resposta é a mesma:
# o teste conserta o piso antes de afirmar sobre ele, em vez de depender de o
# banco estar limpo.
with SessionLocal() as db:
    from sqlalchemy import select as _sel0
    from app.models.roteiro_entrevista import (RoteiroEntrevista as _R0,
                                               TipoRoteiro as _T0)
    from app.services.entrevistas import NOME_TRIAGEM_PADRAO as _NTP
    if not db.scalar(_sel0(_R0).where(_R0.tipo == _T0.triagem.value,
                                      _R0.padrao.is_(True))):
        alvo0 = db.scalar(_sel0(_R0).where(_R0.tipo == _T0.triagem.value,
                                           _R0.nome == _NTP)
                          .order_by(_R0.criado_em))
        if alvo0 is not None:
            alvo0.padrao, alvo0.status, alvo0.arquivado_em = True, "publicado", None
            db.commit()

# O `tornar-padrao` precisa ser EXERCITADO aqui — a 1ª versão deste bloco só
# conferia as listagens, e a mutação que fazia o `tornar_padrao` desmarcar
# padrão de qualquer tipo passava verde porque o teste nunca chamava a rota.
# É a mesma lição do `_anexo_ics` acima: asserção que não executa a linha
# mutada não protege nada.
r = c.post(f"/api/rh/roteiros-entrevista/{rot_id}/tornar-padrao", headers=RH)
checar(r.status_code == 200,
       f"elege um roteiro de ENTREVISTA como padrão ({r.status_code})")

for t_esperado in ("entrevista", "triagem"):
    r = c.get(f"/api/rh/roteiros-entrevista?tipo={t_esperado}", headers=RH)
    itens = r.json()["itens"]
    checar(all(i["tipo"] == t_esperado for i in itens),
           f"a lista de '{t_esperado}' só traz roteiros desse tipo")
    padroes = [i for i in itens if i["padrao"]]
    checar(len(padroes) == 1,
           f"existe EXATAMENTE um padrão de '{t_esperado}' ({len(padroes)}) — "
           f"cada natureza tem o seu fundo de herança")

# A herança da ENTREVISTA nunca cai num roteiro de triagem: o formulário tem
# que continuar vindo com competências.
form_apos = c.get("/api/rh/entrevistas/formulario", headers=RH).json()
checar(len(form_apos["competencias"]) >= 1,
       "o formulário de entrevista continua servindo COMPETÊNCIAS (não caiu "
       "num roteiro de triagem)")
checar(all(c_.get("ancoras") for c_ in form_apos["competencias"]),
       "e todas com âncoras — é instrumento de entrevista, não de triagem")

# DEVOLVE o padrão de entrevista ao roteiro semeado — este teste elegeu outro
# acima, e deixar o estado trocado faria a PRÓXIMA execução (e as outras
# suítes) rodarem sobre um instrumento diferente. Teste que suja o banco é
# armadilha: a falha aparece longe da causa.
with SessionLocal() as db:
    from sqlalchemy import select as _sel
    from app.models.roteiro_entrevista import (RoteiroEntrevista as _R,
                                               TipoRoteiro as _T)
    from app.services.entrevistas import NOME_ROTEIRO_PADRAO
    semeado = db.scalar(_sel(_R).where(_R.tipo == _T.entrevista.value,
                                       _R.nome == NOME_ROTEIRO_PADRAO)
                        .order_by(_R.criado_em))
    if semeado is not None:
        for outro in db.scalars(_sel(_R).where(_R.padrao.is_(True),
                                               _R.tipo == _T.entrevista.value)):
            outro.padrao = False
        semeado.padrao = True
        semeado.status, semeado.arquivado_em = "publicado", None
        db.commit()
        devolvido = semeado.padrao
    else:
        devolvido = False
checar(devolvido,
       "e o teste DEVOLVE o padrão de entrevista ao roteiro semeado")


# ==========================================================================
print("\n7. § 15.5 item 4 — duracao_min, e o cenário 37")
# ==========================================================================
t_dur = criar_talento("Pessoa Duracao")
quando = (datetime.now(timezone.utc) + timedelta(days=3)).isoformat()

for ruim in (0, -30):
    r = c.post("/api/rh/entrevistas", headers=RH, json={
        "talento_id": t_dur, "tipo": "entrevista", "marcada_para": quando,
        "duracao_min": ruim})
    checar(r.status_code == 422,
           f"duração {ruim} é recusada ({r.status_code}) — DTEND antes do "
           f"DTSTART quebra o calendário de quem recebe")

r = c.post("/api/rh/entrevistas", headers=RH, json={
    "talento_id": t_dur, "tipo": "entrevista", "marcada_para": quando,
    "duracao_min": 90})
checar(r.status_code == 201, f"duração 90 é aceita ({r.status_code})")
eid_dur = r.json()["id"]
checar(r.json()["duracao_min"] == 90, "e volta no dump")

# Sem informar, cai no padrão de 60 — referência CONSTANTE do teste.
r = c.post("/api/rh/entrevistas", headers=RH, json={
    "talento_id": t_dur, "tipo": "entrevista", "marcada_para": quando})
checar(r.json()["duracao_min"] == 60, "sem informar, o padrão é 60 minutos")

# E a duração REALMENTE chega ao .ics: DTSTART + 90 min = DTEND.
#
# ⚠️ O teste tem que passar pelo `_anexo_ics`, que é quem o convite usa — a 1ª
# versão chamava `calendario.gerar_ics` direto, com `duracao_min=e.duracao_min`
# escrito NO TESTE. Isso testava a biblioteca, não a LIGAÇÃO: a mutação que
# devolvia `duracao_min=DURACAO_MIN` fixo dentro do `_anexo_ics` passava verde,
# porque o teste nunca executava a linha mutada. Mesma família da tautologia da
# v2.54/v2.64 — a asserção precisa exercitar o caminho de produção.
#
# Mutação verificada: `duracao_min=DURACAO_MIN` fixo no `_anexo_ics` -> falha.
with SessionLocal() as db:
    from app.services import entrevista_convite as _conv
    e_dur = db.get(Entrevista, uuid.UUID(eid_dur))
    anexos_dur = _conv._anexo_ics(db, e_dur, "pessoa@exemplo.com", False)
checar(bool(anexos_dur), "o convite leva o .ics anexado")
ics = anexos_dur[0][1].decode() if anexos_dur else ""
linhas = {ln.split(":")[0].split(";")[0]: ln.split(":")[-1]
          for ln in ics.splitlines() if ":" in ln}
inicio_ics, fim_ics = linhas.get("DTSTART", ""), linhas.get("DTEND", "")
fmt = "%Y%m%dT%H%M%S"
delta = (datetime.strptime(fim_ics, fmt) - datetime.strptime(inicio_ics, fmt))
checar(delta == timedelta(minutes=90),
       f"o .ics reserva os 90 minutos pedidos (reservou {delta})")


# ==========================================================================
print("\n8. § 15.5 item 5 — remetente de recrutamento, cenário 36")
# ==========================================================================
# A regra: NUNCA falha por estar vazia.
from app.services.config_dinamica import email_recrutamento, gravar_config  # noqa: E402

with SessionLocal() as db:
    from app.models.configuracao import Configuracao
    from app.services.config_dinamica import smtp_config
    reg = db.get(Configuracao, "email_recrutamento")
    if reg is not None:
        db.delete(reg)
        db.commit()
    vazio = email_recrutamento(db)
    # O `smtp_from` EFETIVO é banco > .env — comparar só com a linha da tabela
    # ignoraria o `.env`, que é de onde ele vem em toda instalação nova. Foi o
    # que esta asserção fez na 1ª versão, e ela reprovou um código correto.
    efetivo = (smtp_config(db).get("from_") or "").strip() or None
checar(vazio == efetivo,
       f"chave VAZIA cai no smtp_from efetivo, sem erro "
       f"(devolveu {vazio!r}, esperado {efetivo!r})")

ESPERADO_REMETENTE = "recrutamento@exemplo-teste.com"
with SessionLocal() as db:
    gravar_config(db, {"email_recrutamento": ESPERADO_REMETENTE})
    db.commit()
    preenchido = email_recrutamento(db)
checar(preenchido == ESPERADO_REMETENTE,
       f"preenchida, é ela que vale ({preenchido!r})")

# E o ORGANIZER do .ics passa a usá-la. Mutação: voltar `organizador_email`
# para o `smtp_from` do settings -> o endereço abaixo não aparece.
with SessionLocal() as db:
    from app.services import entrevista_convite as conv
    e_dur = db.get(Entrevista, uuid.UUID(eid_dur))
    anexos = conv._anexo_ics(db, e_dur, "pessoa@exemplo.com", False)
conteudo_ics = anexos[0][1].decode() if anexos else ""
checar(ESPERADO_REMETENTE in conteudo_ics,
       "o ORGANIZER do .ics usa o remetente de recrutamento")

# Volta ao estado anterior — teste não deixa estrago para a próxima execução.
with SessionLocal() as db:
    from app.models.configuracao import Configuracao
    reg = db.get(Configuracao, "email_recrutamento")
    if reg is not None:
        db.delete(reg)
        db.commit()


# ==========================================================================
print("\n9. § 15.5 item 1 — a vaga passa pela LIXEIRA (cenário 34)")
# ==========================================================================
# Mutação: voltar o `db.delete(v)` sem `mandar_para_lixeira` -> a vaga some da
# lixeira e este bloco falha.
TITULO_VAGA = f"Vaga que vai para a lixeira {SUF}"
r = c.post("/api/rh/vagas", headers=RH, json={
    "titulo": TITULO_VAGA, "descricao": "Some pela lixeira.", "cargo": "Vigia"})
vaga_id = r.json()["id"]

eid_vaga = entrevista_completa(criar_talento("Pessoa Da Vaga"), vaga_id)

r = c.delete(f"/api/rh/vagas/{vaga_id}", headers=RH)
checar(r.status_code == 204, f"exclui a vaga ({r.status_code})")

with SessionLocal() as db:
    from sqlalchemy import select
    from app.models.lixeira import ItemLixeira
    na_lixeira = db.scalars(
        select(ItemLixeira).where(ItemLixeira.entidade == "vaga",
                                  ItemLixeira.entidade_id == uuid.UUID(vaga_id))).first()
checar(na_lixeira is not None,
       "a vaga excluída foi para a LIXEIRA (não é mais delete físico)")
if na_lixeira is not None:
    # Referência CONSTANTE: o título que ESTE teste escolheu, não um valor lido
    # de volta do sistema (armadilha da v2.64).
    checar(na_lixeira.dados.get("titulo") == TITULO_VAGA,
           "e o snapshot guarda o título de verdade, restaurável")

# Defesa em profundidade: o SET NULL + snapshot CONTINUAM valendo.
r = c.get(f"/api/rh/entrevistas/{eid_vaga}", headers=RH)
depois = r.json()
checar(depois["vaga_titulo"] == TITULO_VAGA,
       f"a entrevista continua dizendo para QUAL vaga foi ({depois['vaga_titulo']!r})")
checar(depois["vaga_id"] is None, "e a FK foi a NULL, sem levar a entrevista junto")

# O documento da entrevista continua saindo, com o nome da vaga excluída.
r = c.get(f"/api/rh/entrevistas/{eid_vaga}/documento", headers=RH)
checar(r.status_code == 200,
       f"o documento sai mesmo com a vaga excluída ({r.status_code})")


# ==========================================================================
print("\n10. Cenário 38 — ficha de entrevista ARQUIVADA continua emitível")
# ==========================================================================
# Arquivar tira da vista, NUNCA apaga (decisão 5). Recusar o documento aqui
# faria o prazo de 180 dias virar destruição de prova.
# Mutação: incluir `arquivada` na lista de status recusados de
# `erros_para_documento` -> este bloco falha.
eid_arq = entrevista_completa(criar_talento("Pessoa Arquivada"))
r = c.post(f"/api/rh/entrevistas/{eid_arq}/arquivar", headers=RH,
           json={"motivo": "Teste de arquivamento."})
checar(r.status_code == 200, f"arquiva ({r.status_code})")

r = c.get(f"/api/rh/entrevistas/{eid_arq}/documento", headers=RH)
checar(r.status_code == 200,
       f"o documento da entrevista ARQUIVADA continua saindo ({r.status_code}) "
       f"— arquivar tira da vista, não apaga")

with SessionLocal() as db:
    ainda = db.get(Entrevista, uuid.UUID(eid_arq))
checar(ainda is not None and ainda.status == StatusEntrevista.arquivada,
       "e o registro continua no banco, arquivado")


# ==========================================================================
print("\n11. O FRONT não duplica o texto dos documentos")
# ==========================================================================
# Mesma regra estrutural do instrumento: quem desenha o documento é o servidor.
raiz = os.path.join(os.path.dirname(__file__), "..", "..", "frontend", "src")
from app.services import entrevista_pdf as _epdf  # noqa: E402

# Trechos que SÓ existem no gerador — se aparecerem no JSX, alguém copiou.
trechos = ["A triagem é uma checagem de viabilidade",
           "Roteiro pré-aprovado de entrevista estruturada",
           "Documento gerado pelo Portal de RH a partir do registro"]
duplicado = []
for pasta, _, arquivos in os.walk(raiz):
    for nome in arquivos:
        if not nome.endswith(".jsx"):
            continue
        with open(os.path.join(pasta, nome), encoding="utf-8") as fh:
            conteudo = fh.read()
        for t in trechos:
            if t in conteudo:
                duplicado.append(f"{nome}: {t[:30]}...")
checar(not duplicado,
       f"o front NÃO duplica o texto dos documentos (achados: {duplicado})")


# ==========================================================================
print(f"\ntest_entrevista_documentos: {len(falhas)} FALHA(S)"
      if falhas else "\ntest_entrevista_documentos: OK")
for f in falhas:
    print(f"  - {f}")
raise SystemExit(1 if falhas else 0)
