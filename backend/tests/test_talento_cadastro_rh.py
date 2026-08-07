"""O RH cadastra talento à mão — a porta que não existia (v2.73).

Por que esta rota existe: o Banco de Talentos tinha DUAS entradas — o formulário
público (`POST /talentos`) e a importação da planilha do Forms. **Nenhuma
servia ao RH.** O currículo que chega por e-mail ou por indicação ficava de fora,
ou obrigava a pedir que a pessoa preenchesse o formulário de novo. O pedido do
Bruno falava em "currículo por e-mail"; o problema real era a porta que faltava.

As duas decisões que este teste trava:

1. **CONSENTIMENTO NÃO SE FINGE.** No formulário público a pessoa marca "li e
   concordo" e o `consentimento_lgpd_em` é carimbado; na importação o carimbo vem
   da coluna da planilha. Quando o RH cadastra à mão, **ninguém marcou nada** — e
   gravar o carimbo registraria como aceite do titular algo que ele não fez. O
   campo fica NULO e `cadastrado_por_*` diz quem assumiu. É o precedente da
   `AutorizacaoEquipe` (v1.42) e do manifesto de admissão assistida (v2.56): o
   registro descreve o ato REAL, nunca a versão conveniente.

   A mutação que carimba o consentimento é a mais importante daqui: ela passaria
   despercebida em qualquer revisão de código — o cadastro funciona igual, a tela
   fica até mais "limpa", e o que se perde é a verdade de um registro de LGPD.

2. **DUPLICATA AVISA, NÃO FUNDE.** 409 dizendo QUEM já existe. É a regra da casa
   para equivalência assistida (jornadas, incidência de benefícios, cargos do
   Tirvu): o sistema propõe, o humano confirma — merge cego cria associação
   errada que ninguém vê depois. `forcar=true` existe para o homônimo real e fica
   na auditoria.

Mutações verificadas:
  1. carimbar `consentimento_lgpd_em` no cadastro do RH  -> bloco 2 falha
  2. não gravar `cadastrado_por_*`                        -> bloco 2 falha
  3. remover a checagem de duplicata                      -> bloco 3 falha
  4. `forcar` deixa de funcionar                          -> bloco 4 falha
  5. duplicata por nome+telefone deixa de ser checada     -> bloco 3 falha

Precisa dos containers de teste (banco + MinIO).

Rode: PYTHONPATH=. .venv/Scripts/python.exe tests/test_talento_cadastro_rh.py
"""

import os
import uuid

for _chave, _valor in dict(
    DATABASE_URL="postgresql+psycopg://admissao:admissao@localhost:55432/admissao",
    MINIO_ENDPOINT="localhost:59000",
    MINIO_ACCESS_KEY="minio",
    MINIO_SECRET_KEY="minio12345",
    MINIO_SECURE="false",
    RH_ADMIN_EMAIL="rh@greenhousedf.com.br",
    RH_ADMIN_PASSWORD="senha-teste-123",
    SECRET_KEY="segredo-de-teste",
    BASE_URL="http://localhost:8090",
).items():
    os.environ.setdefault(_chave, _valor)

from fastapi.testclient import TestClient  # noqa: E402

from app.core.db import SessionLocal  # noqa: E402
from app.main import app  # noqa: E402
from app.models.talento import Talento  # noqa: E402

c = TestClient(app)

EMAIL = os.environ["RH_ADMIN_EMAIL"]
SENHA = os.environ["RH_ADMIN_PASSWORD"]
r = c.post("/api/rh/auth/login", json={"email": EMAIL, "senha": SENHA})
assert r.status_code == 200, (
    f"login falhou ({r.status_code}): confira RH_ADMIN_EMAIL/RH_ADMIN_PASSWORD "
    f"— `criar_admin_inicial` só cria o admin com a tabela VAZIA. {r.text}")
RH = {"Authorization": f"Bearer {r.json()['token']}"}

SUF = uuid.uuid4().hex[:8]
falhas: list[str] = []


def checar(cond, msg):
    if cond:
        print(f"  ok   {msg}")
    else:
        print(f"  FALHOU  {msg}")
        falhas.append(msg)


def cadastrar(**campos):
    corpo = {"nome": f"Fulano {SUF}", **campos}
    return c.post("/api/rh/talentos", headers=RH, json=corpo)


# --------------------------------------------------------------------------
print("\n1. a rota existe, exige RH e cria o talento")
# --------------------------------------------------------------------------
checar(c.post("/api/rh/talentos", json={"nome": "X"}).status_code in (401, 403),
       "sem token é recusado (não é rota pública)")

r = cadastrar(email=f"a{SUF}@exemplo.com", telefone="61988887777",
              cargos_interesse=["Recepcionista", "Vigia"],
              origem="Currículo por e-mail", cidade="Taguatinga")
checar(r.status_code == 201, f"POST /rh/talentos responde 201 ({r.text[:100]})")
t = r.json()
tid = t.get("id")

checar(t.get("cargos_interesse") == ["Recepcionista", "Vigia"],
       "os cargos escolhidos são gravados")
checar(t.get("cargo_interesse") == "Recepcionista",
       "o campo legado `cargo_interesse` recebe o 1º cargo (o `converter` usa ele)")

r = cadastrar(nome="   ")
checar(r.status_code == 422, "nome vazio é recusado com 422")

# O schema é herdado do formulário público, então o `capitalizar_nome` vem junto.
# `.title()` produziria "Maria De Fátima" — o defeito que a v2.54 corrigiu.
r = cadastrar(nome=f"maria de fátima souza {SUF}")
checar(r.status_code == 201 and r.json()["nome"].startswith("Maria de Fátima"),
       f"o nome é padronizado sem o 'De' do .title() ({r.json().get('nome')})")

# --------------------------------------------------------------------------
print("\n2. CONSENTIMENTO não é fingido — e quem cadastrou fica registrado")
# --------------------------------------------------------------------------
# ⚠️ Mutações 1 e 2. A primeira é a que mais importa: carimbar o consentimento
# aqui passaria em qualquer revisão de código (o cadastro funciona igual), e o
# que se perde é a verdade de um registro de LGPD.
checar(t.get("consentimento_lgpd_em") is None,
       "o consentimento fica NULO — a pessoa não estava na tela para aceitar")
checar(bool(t.get("cadastrado_por_nome")),
       f"a resposta diz QUEM cadastrou ({t.get('cadastrado_por_nome')!r})")

with SessionLocal() as db:
    reg = db.get(Talento, uuid.UUID(tid))
    checar(reg is not None and reg.consentimento_lgpd_em is None,
           "no BANCO o consentimento também está nulo (não é só omissão do dump)")
    checar(reg is not None and reg.cadastrado_por_id is not None,
           "o id do usuário do RH é gravado (FK)")
    checar(reg is not None and reg.cadastrado_por_nome,
           "o nome fica em SNAPSHOT (não some se o usuário for removido)")

# Contraste com a porta pública: LÁ o carimbo existe, porque houve aceite.
r_pub = c.post("/api/talentos", json={
    "nome": f"Publico {SUF}", "email": f"pub{SUF}@exemplo.com",
    "cargos_interesse": ["Vigia"], "consentimento_lgpd": True})
checar(r_pub.status_code in (200, 201), "o formulário público continua funcionando")
with SessionLocal() as db:
    pub = db.scalar(
        __import__("sqlalchemy").select(Talento)
        .where(Talento.email == f"pub{SUF}@exemplo.com"))
    checar(pub is not None and pub.consentimento_lgpd_em is not None,
           "no cadastro PÚBLICO o consentimento É carimbado (houve aceite de verdade)")
    checar(pub is not None and pub.cadastrado_por_nome is None,
           "e ninguém do RH aparece como responsável por ele")

# --------------------------------------------------------------------------
print("\n3. duplicata AVISA, dizendo quem já existe")
# --------------------------------------------------------------------------
# ⚠️ Mutações 3 e 5.
r = cadastrar(nome="Outra Pessoa", email=f"a{SUF}@exemplo.com")
checar(r.status_code == 409, f"mesmo e-mail dá 409 ({r.status_code})")
d = (r.json() or {}).get("detail") or {}
checar(isinstance(d, dict) and d.get("erro") == "talento_ja_existe",
       "o erro é estruturado (o front precisa dele para montar o aviso)")
checar(d.get("nome") and d.get("id"),
       f"o 409 DIZ QUEM já existe — 'já existe' sem nome faz procurar na lista "
       f"({d.get('nome')!r})")
checar(d.get("por") == "email", "e diz por que casou (e-mail)")

# Sem e-mail, casa por nome + telefone — a mesma regra da importação de planilha:
# duas portas para o mesmo banco não podem discordar sobre o que é a mesma pessoa.
r = cadastrar(nome=f"Fulano {SUF}", telefone="61988887777")
checar(r.status_code == 409 and (r.json()["detail"] or {}).get("por") == "nome_telefone",
       "mesmo nome + mesmo telefone também é duplicata")

# Telefone com máscara diferente é a MESMA pessoa (comparação por dígitos).
r = cadastrar(nome=f"Fulano {SUF}", telefone="(61) 98888-7777")
checar(r.status_code == 409,
       "a máscara do telefone não engana a checagem (compara só os dígitos)")

# Nome parecido NÃO é duplicata: o sistema não adivinha.
r = cadastrar(nome=f"Fulano {SUF} Silva", telefone="61911112222")
checar(r.status_code == 201, "nome diferente com telefone diferente entra normalmente")

# --------------------------------------------------------------------------
print("\n4. `forcar` existe para o homônimo real")
# --------------------------------------------------------------------------
# ⚠️ Mutação 4. Numa base de 1.171 pessoas homônimo acontece — mas é o caminho
# secundário, escolhido depois do aviso, e fica na auditoria.
r = cadastrar(nome="Outra Pessoa", email=f"a{SUF}@exemplo.com", forcar=True)
checar(r.status_code == 201, "com `forcar` o cadastro entra mesmo com duplicata")
checar(r.json().get("consentimento_lgpd_em") is None,
       "e continua sem consentimento fingido (forçar não muda isso)")

# --------------------------------------------------------------------------
print("\n5. o talento cadastrado à mão aparece na listagem do RH")
# --------------------------------------------------------------------------
lista = c.get("/api/rh/talentos", headers=RH).json()
achou = [x for x in lista if x["id"] == tid]
checar(bool(achou), "o talento entra na lista (não fica invisível)")
checar(bool(achou) and achou[0].get("cadastrado_por_nome"),
       "a listagem expõe quem cadastrou — a ficha usa isso para explicar o "
       "consentimento vazio em vez de mostrar um travessão")


print()
if falhas:
    print(f"test_talento_cadastro_rh: {len(falhas)} FALHA(S)")
    for f_ in falhas:
        print(f"  - {f_}")
    raise SystemExit(1)
print("test_talento_cadastro_rh: OK")
