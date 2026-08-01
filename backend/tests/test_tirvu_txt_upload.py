"""Subir o .txt do Tirvu em vez de colar o texto (v2.38).

Pedido do Bruno em 2026-08-01: *"quero fazer o mesmo pelo front, de apenas
subir os txts e o sistema entender"*. O Tirvu não tem botão de exportar cargos
nem jornadas — ele seleciona a tela, cola no Bloco de Notas e salva.

O que MUDA é a porta de entrada. O que NÃO muda é a regra da casa: o sistema
**propõe**, o RH confirma. Cargo homônimo com dois IDs ativos e jornada
duplicada continuam fora do lote automático.

O que este teste protege:

1. **A codificação do Bloco de Notas** — UTF-8, UTF-8 com BOM e ANSI (cp1252)
   dão o MESMO resultado. Errar aqui não levanta erro: quebra o acento, e o
   casamento por texto falha calado justamente nos cargos acentuados.
2. **Upload e texto colado produzem o mesmo preview** — se divergirem, a tela
   nova mente sobre o que a antiga faria.
3. **CBO, escala e tratamento são GRAVADOS** — eram lidos pelo parser e
   jogados fora. O CBO é o que distingue os homônimos.
4. **Vazio não apaga o que já existe** — arquivo sem a coluna não pode zerar
   dado bom.
5. **Ambíguo não entra no lote** — nos dados reais são 2 cargos que 87 pessoas
   usam.

Roda com os ARQUIVOS REAIS quando eles existem em `docs/` (não versionados);
sem eles, cai numa amostra equivalente embutida — o teste nunca é pulado em
silêncio, ele diz qual fonte usou.

Rode: PYTHONPATH=. .venv/Scripts/python.exe tests/test_tirvu_txt_upload.py
"""

import os
import pathlib
import uuid

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
from sqlalchemy import select  # noqa: E402

from app.core.db import SessionLocal  # noqa: E402
from app.main import app  # noqa: E402
from app.models.candidato import CargoTirvu, Jornada  # noqa: E402
from app.services.importar_tirvu_txt import (decodificar, parsear_cargos,  # noqa: E402
                                             parsear_jornadas)

FALHAS = []


def checar(condicao, descricao):
    print(("  ok   " if condicao else "  FALHA ") + descricao)
    if not condicao:
        FALHAS.append(descricao)


c = TestClient(app)
H = {"Authorization": f"Bearer {c.post('/api/rh/auth/login', json={'email': 'rh@greenhousedf.com.br', 'senha': 'senha-teste-123'}).json()['token']}"}

DOCS = pathlib.Path(__file__).resolve().parents[2] / "docs" / "modelos de arquivos exportados do tirvu"
ARQ_CARGOS = next(iter(sorted(DOCS.glob("cargos*.txt"))), None)
ARQ_JORNADAS = next(iter(sorted(DOCS.glob("jornadas*.txt"))), None)

# Amostra equivalente ao formato real (linha de registro + 3 linhas de lixo de
# UI: iniciais do avatar, responsável e data), para o CI, que não tem `docs/`.
AMOSTRA_CARGOS = (
    "ID\tStatus\t\tCargo\tCargo Base\tCBO\tResponsável\t\n"
    "85\t  ATIVO\t  \tGERENTE DE RESTAURANTE\tGERENTE DE RESTAURANTE\t141510\t\n"
    "LA\nLAYSA BEATRIZ FERREIRA COSTA\n17/09/2024 às 13:19\n"
    "40\t  INATIVO\t  \tGERENTE FINANCEIRO\tGERENTE FINANCEIRO\t142115\t\n"
    "AD\nADMINISTRADOR\n05/09/2024 às 22:42\n"
    f"91\t  ATIVO\t  \tAUXILIAR DE MANUTENÇÃO {uuid.uuid4().hex[:6]}\tAUX\t514225\t\n"
    "LA\nLAYSA\n01/08/2026 às 09:00\n"
)
AMOSTRA_JORNADAS = (
    "ID\tDescrição\tEscala\tTratamento\tDomingo\tSegunda-Feira\t\n"
    f"323\tCNMP - COPA - 2ª A 5ª - 07H - 12H {uuid.uuid4().hex[:6]}Sem vínculos\tSemanal\tBANCO DE HORAS\t\n"
    "\n07:0012:00\n13:0017:00\n"
)

texto_cargos = decodificar(ARQ_CARGOS.read_bytes()) if ARQ_CARGOS else AMOSTRA_CARGOS
texto_jornadas = decodificar(ARQ_JORNADAS.read_bytes()) if ARQ_JORNADAS else AMOSTRA_JORNADAS
print(f"\n[fonte] cargos: {ARQ_CARGOS.name if ARQ_CARGOS else 'amostra embutida'} · "
      f"jornadas: {ARQ_JORNADAS.name if ARQ_JORNADAS else 'amostra embutida'}")

# ============================================ 1. codificação do Bloco de Notas
print("\n[codificação do arquivo salvo pelo RH]")
original = "GERENTE DE RESTAURAÇÃO"
checar(decodificar(original.encode("utf-8")) == original, "UTF-8 puro")
checar(decodificar(b"\xef\xbb\xbf" + original.encode("utf-8")) == original,
       "UTF-8 com BOM (o padrão do Bloco de Notas do Windows)")
checar(decodificar(original.encode("cp1252")) == original,
       "ANSI/cp1252 — se decodificar errado, o acento quebra e o cargo não casa")
checar(decodificar(b"\xff\xfe\x00abc") is not None, "byte inválido não derruba a importação")

# ================================= 2. upload == texto colado (mesmo preview)
print("\n[a porta de entrada mudou, o resultado não]")
r_arquivo = c.post("/api/rh/tirvu-txt/preview-cargos-arquivo", headers=H,
                   files={"arquivo": ("cargos.txt", texto_cargos.encode("utf-8"), "text/plain")})
checar(r_arquivo.status_code == 200, f"upload de cargos aceito ({r_arquivo.status_code})")
r_texto = c.post("/api/rh/tirvu-txt/preview-cargos", headers=H, json={"texto": texto_cargos})
checar(r_arquivo.json() == r_texto.json(),
       "preview do ARQUIVO é idêntico ao do texto colado")

rj = c.post("/api/rh/tirvu-txt/preview-jornadas-arquivo", headers=H,
            files={"arquivo": ("jornadas.txt", texto_jornadas.encode("utf-8"), "text/plain")})
checar(rj.status_code == 200, f"upload de jornadas aceito ({rj.status_code})")
checar(rj.json() == c.post("/api/rh/tirvu-txt/preview-jornadas", headers=H,
                           json={"texto": texto_jornadas}).json(),
       "preview de jornadas idêntico pelos dois caminhos")

# BOM e cp1252 pela rota (é assim que o arquivo real chega)
r_bom = c.post("/api/rh/tirvu-txt/preview-cargos-arquivo", headers=H,
               files={"arquivo": ("c.txt", b"\xef\xbb\xbf" + texto_cargos.encode("utf-8"), "text/plain")})
checar(r_bom.json() == r_texto.json(), "arquivo com BOM dá o mesmo resultado")

# ============================================= 3. o que o preview enxerga
prev = r_texto.json()
propostas = prev["propostas"]
com_cbo = [p for p in propostas if p.get("cbo")]
print(f"\n[preview] {prev['total']} no arquivo · {prev['ativos']} ativos · "
      f"{prev['homonimos']} homônimos · {len(com_cbo)} com CBO")
checar(len(com_cbo) > 0, "o CBO chega ao preview (é o que distingue homônimo)")
checar(all(p.get("aplicar_sugerido") is False for p in propostas if p.get("homonimo")),
       "cargo homônimo NUNCA entra no lote automático")

# ================================== 4. confirmar GRAVA cbo/escala/tratamento
print("\n[o que se perdia agora é gravado]")
alvo = next((p for p in propostas if p.get("cbo") and p["aplicar_sugerido"]), None)
checar(alvo is not None, "há ao menos um cargo seguro com CBO para gravar")
if alvo:
    rotulo = f"{alvo['cargo']} {uuid.uuid4().hex[:6]}"   # não colide com a base
    r = c.post("/api/rh/tirvu-txt/confirmar-cargos", headers=H, json={"itens": [
        {"tirvu_id": alvo["tirvu_id"], "cargo": rotulo, "cbo": alvo["cbo"], "aplicar": True}]})
    checar(r.status_code == 200, f"gravação aceita ({r.status_code})")
    with SessionLocal() as db:
        from app.services.export_tirvu import normalizar_cargo
        m = db.scalar(select(CargoTirvu).where(
            CargoTirvu.cargo_normalizado == normalizar_cargo(rotulo)))
        checar(m is not None and m.cbo == alvo["cbo"],
               f"CBO gravado no de-para ({m.cbo if m else None})")
        # Reenviar SEM cbo não pode apagar o que já está lá.
        c.post("/api/rh/tirvu-txt/confirmar-cargos", headers=H, json={"itens": [
            {"tirvu_id": alvo["tirvu_id"], "cargo": rotulo, "cbo": "", "aplicar": True}]})
        db.expire_all()
        m2 = db.scalar(select(CargoTirvu).where(
            CargoTirvu.cargo_normalizado == normalizar_cargo(rotulo)))
        checar(m2 is not None and m2.cbo == alvo["cbo"],
               "CBO vazio NÃO apaga o gravado — perder dado por omissão é pior "
               "que não atualizar")

desc = f"TESTE UPLOAD {uuid.uuid4().hex[:8]} - 2ª A 6ª - 08H - 17H"
r = c.post("/api/rh/tirvu-txt/confirmar-jornadas", headers=H, json={"itens": [
    {"tirvu_id": "999", "descricao": desc, "escala": "Semanal",
     "tratamento": "BANCO DE HORAS", "aplicar": True}]})
checar(r.status_code == 200 and r.json()["criadas"] == 1, f"jornada criada ({r.text})")
with SessionLocal() as db:
    j = db.scalar(select(Jornada).where(Jornada.descricao == desc))
    checar(j is not None and j.tirvu_escala == "Semanal"
           and j.tirvu_tratamento == "BANCO DE HORAS",
           f"escala e tratamento do Tirvu gravados ({j.tirvu_escala if j else None} / "
           f"{j.tirvu_tratamento if j else None})")
    checar(j is not None and j.escala is None,
           "o campo `escala` INTERNO do parser continua intocado — são "
           "vocabulários diferentes e fundi-los faria ler um achando que é o outro")

# ============================ 5. os arquivos reais, quando estão disponíveis
if ARQ_CARGOS and ARQ_JORNADAS:
    print("\n[arquivos reais de produção]")
    cargos = parsear_cargos(texto_cargos)
    jornadas = parsear_jornadas(texto_jornadas)
    checar(len(cargos) > 100, f"{len(cargos)} cargos lidos do arquivo real")
    checar(len(jornadas) > 400, f"{len(jornadas)} jornadas lidas do arquivo real")
    checar(all(j.descricao and "vínculos" not in j.descricao.lower() for j in jornadas),
           "a sujeira 'Sem vínculos' da cópia de tela não sobra em descrição nenhuma")
    checar(sum(1 for x in cargos if x.cbo) > len(cargos) * 0.9,
           "praticamente todo cargo real traz CBO")

print()
if FALHAS:
    print(f"test_tirvu_txt_upload: {len(FALHAS)} FALHA(S)")
    for f in FALHAS:
        print(f"  - {f}")
    raise SystemExit(1)
print("test_tirvu_txt_upload: OK")
