"""Disparo e gerenciamento do requerimento de creche (v3.16).

Defeito de campo de 26/08/2026, relatado pelo Bruno: *"nos que foram aprovados
e ativados, não chegou para esse pessoal automaticamente o processo de
assinar"*. O roteiro EXISTIA no banco; quem mentia era a consulta.

`tem_roteiro(db, candidato_id)` sem filtro devolve o roteiro mais RECENTE de
qualquer documento da pessoa, ordenado por `criado_em desc`. Quem foi efetivado
tem roteiros de admissão — e assim que um deles ficava mais novo que o do
creche, `_etapa_colaborador` comparava a origem, reprovava, e a sessão do
colaborador respondia `disponivel: false` **com o requerimento pronto ao lado**.
Nada dava erro: a tela do RH dizia "ativo", a do colaborador não mostrava botão
nenhum, e o log registrava um 200.

O que se garante aqui, e por quê:

1. **A consulta filtra a ORIGEM no SQL.** É o defeito acima. Sem isso o roteiro
   de admissão sequestra a resposta do creche.
2. **`criar_roteiro_creche` é idempotente por ORIGEM.** Antes ele comparava a
   origem do roteiro mais recente e, quando ela não batia, caía para criar um
   SEGUNDO roteiro de creche — o colaborador assinaria um e o RH o outro.
3. **A ficha do RH ACUSA o pendente.** Estado que ninguém vê equivale a não
   existir: era exatamente por não aparecer que o defeito durou.
4. **Só o benefício ATIVO dispara.** Disparar num `aguardando_repactuacao`
   mandaria assinar documento cujo valor ainda vai mudar — e a recusa oferece
   a saída, em vez de só bloquear (v2.93).
5. **O lote presta contas.** Lote que só diz "pronto" faz o RH acreditar que
   resolveu o que não resolveu (v2.14).
6. **Roteiro criado NÃO é pessoa avisada** (v3.16.1, defeito de campo visto
   pelo Bruno num print). A v3.16 tratou os dois como um só: quem foi ativado
   ANTES dela ganhou o roteiro sem e-mail nenhum (o aviso não existia), e o
   lote respondia `ja_disparado` e pulava — verdade sobre o roteiro, mentira
   sobre o aviso. O botão da ficha também sumia depois de criado, deixando sem
   saída exatamente esse caso.
7. **O carimbo do aviso só existe se o e-mail SAIU.** Registrar antes faria a
   ficha dizer "avisado em dd/mm" sobre um envio que falhou, e o RH deixaria de
   cobrar justamente quem não recebeu.

Precisa de banco e MinIO. Roda no CI dentro do container da API.
"""
import os
import sys
import uuid as _uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault(
    "DATABASE_URL", "postgresql+psycopg://admissao:admissao@localhost:55432/admissao")
os.environ.setdefault("SECRET_KEY", "teste")
os.environ.setdefault("MINIO_ENDPOINT", "localhost:59000")
os.environ.setdefault("MINIO_ACCESS_KEY", "minio")
os.environ.setdefault("MINIO_SECRET_KEY", "minio12345")

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import select  # noqa: E402

from app.api.auth_rh import requer_rh  # noqa: E402
from app.core.db import SessionLocal  # noqa: E402
from app.main import app  # noqa: E402
from app.models.beneficio import BeneficioCreche, CriancaCreche  # noqa: E402
from app.models.beneficio import StatusBeneficio  # noqa: E402
from app.models.candidato import Candidato, PostoServico  # noqa: E402
from app.models.solicitacao_assinatura import (SolicitacaoAssinatura,  # noqa: E402
                                               StatusSolicitacao)
from app.models.usuario_rh import UsuarioRH  # noqa: E402
from app.services.roteiro_assinatura import (ORIGEM_CRECHE,  # noqa: E402
                                             criar_roteiro_creche, tem_roteiro)

FALHAS = []
db = SessionLocal()

# ---------------------------------------------------------------------------
# SMTP substituído: no CI não há servidor de e-mail, e o sistema — CORRETAMENTE
# — não carimba o aviso nem conta como avisado quando o envio falha. Sem este
# duplo, 9 asserções caem lá e passam aqui, onde o M365 está ligado: é a
# armadilha "passar na sua máquina não prova nada sobre lá" (v2.72.1).
#
# ⚠️ Substituir o LIMITE EXTERNO, nunca as funções do próprio sistema (v2.68):
# o caminho de produção continua sendo percorrido inteiro
# (`_avisar_requerimento` → `_email_requerimento_disponivel` → `enviar_modelo`
# → `enviar_email`); só o último passo é que não abre socket. `_ENVIADOS`
# guarda o que "saiu", para as asserções falarem do e-mail e não da intenção.
# ---------------------------------------------------------------------------
_ENVIADOS = []
_FALHAR_ENVIO = {"ativo": False}


def _envio_falso(destinatario, assunto, corpo_texto, corpo_html=None, *a, **kw):
    if _FALHAR_ENVIO["ativo"] or not destinatario:
        return False
    _ENVIADOS.append({"para": destinatario, "assunto": assunto})
    return True


import app.services.email as _email_mod  # noqa: E402

_email_mod.enviar_email = _envio_falso
# `email_templates` importou o símbolo direto (`from ... import enviar_email`),
# então trocar só no módulo de origem deixaria o envio real de pé — o tipo de
# meia-substituição que faz o teste parecer coberto sem estar.
import app.services.email_templates as _tpl_mod  # noqa: E402

_tpl_mod.enviar_email = _envio_falso

# O usuário do RH precisa existir DE VERDADE no banco: a etapa 2 do roteiro tem
# FK para `usuario_rh`, e um objeto solto estouraria no flush.
_RH = db.scalar(
    __import__("sqlalchemy").select(UsuarioRH).limit(1))
if _RH is None:
    _RH = UsuarioRH(email=f"rh-{_uuid.uuid4().hex[:8]}@teste.com", nome="RH Teste",
                    senha_hash="x", papel="superadmin")
    db.add(_RH)
    db.commit()
app.dependency_overrides[requer_rh] = lambda: _RH
# `raise_server_exceptions=False`: sem isto um 500 sobe como exceção e mata o
# script no meio — a saída fica vazia e passa por sucesso (v2.72.2).
cli = TestClient(app, raise_server_exceptions=False)


def _reportar(texto: str) -> None:
    """Emoji em mensagem de falha quebra o console do Windows (cp1252) e o
    script morre ANTES de mostrar a causa — justamente quando ela importa
    (v3.15)."""
    try:
        print(texto)
    except UnicodeEncodeError:
        print(texto.encode("ascii", "replace").decode("ascii"))


def checar(condicao, descricao):
    _reportar(f"  {'ok  ' if condicao else 'FALHA'}  {descricao}")
    if not condicao:
        FALHAS.append(descricao)


def _cenario(nome: str, status=StatusBeneficio.ativo):
    posto = PostoServico(nome=f"Posto {nome} {_uuid.uuid4().hex[:6]}",
                         da_direito_creche=True, valor_reembolso_creche="R$ 500,00")
    db.add(posto)
    db.flush()
    col = Candidato(nome_completo=nome, cpf=str(_uuid.uuid4().int)[:11],
                    situacao="ativo", posto_servico_id=posto.id,
                    email=f"{_uuid.uuid4().hex[:8]}@exemplo.com.br")
    db.add(col)
    db.flush()
    ben = BeneficioCreche(candidato_id=col.id, status=status,
                          valor_reembolso="R$ 500,00")
    db.add(ben)
    db.flush()
    db.add(CriancaCreche(beneficio_id=ben.id, nome="Filho Um",
                         data_nascimento="2023-05-10", parentesco="filho",
                         tipo_comprovante="declaracao", decisao="deferida"))
    db.commit()
    return col, ben


def _varrer(*beneficios) -> dict:
    """Roda a varredura SÍNCRONA (a função que o worker executa), RECORTADA aos
    benefícios que este teste criou.

    A rota só enfileira; a regra mora aqui. Testar pela rota exigiria Redis +
    worker no CI e ainda assim afirmaria sobre o agendamento, não sobre o que a
    varredura faz.

    ⚠️ O recorte não é conveniência: sem ele a varredura percorre a base
    INTEIRA (157 ativos no banco de desenvolvimento, ~1s de SMTP cada) e o
    teste deixa de terminar — além de mandar e-mail para gente de verdade. É a
    mesma lição da v2.72: a asserção tem de falar dos registros que o teste
    criou, não do tamanho do banco.
    """
    from app.workers.creche_requerimentos import varrer
    return varrer(str(_RH.id), _RH.email,
                  beneficio_ids=[str(b.id) for b in beneficios] or None)


print("\n== 1. roteiro de ADMISSAO nao pode esconder o do creche ==")
col1, ben1 = _cenario("Maria Do Creche")
criar_roteiro_creche(db, ben1, _RH)
db.commit()
# Agora o roteiro de admissão, criado DEPOIS — é o caso real de quem foi
# efetivado e assina contrato pela plataforma. Sem o filtro por origem, é ele
# que a consulta do creche devolve.
admissao = SolicitacaoAssinatura(
    candidato_id=col1.id, titulo_doc="Contrato de trabalho",
    origem=None, status=StatusSolicitacao.aguardando, etapa_atual_ordem=1)
db.add(admissao)
db.commit()

achado = tem_roteiro(db, col1.id, origem=ORIGEM_CRECHE)
checar(achado is not None and achado.origem == ORIGEM_CRECHE,
       "tem_roteiro(origem=creche) acha o do creche mesmo com um de admissao mais novo")
mais_recente = tem_roteiro(db, col1.id)
checar(mais_recente is not None and mais_recente.id == admissao.id,
       "sem o filtro, a consulta devolve MESMO o de admissao (o defeito reproduzido)")

# A prova que importa: a rota que o colaborador enxerga.
from app.api.creche_publico import _etapa_colaborador  # noqa: E402

sol_c, etapa_c = _etapa_colaborador(db, ben1)
checar(sol_c is not None and etapa_c is not None,
       "a sessao do colaborador ENXERGA o requerimento (era o `disponivel: false`)")

print("\n== 2. criar_roteiro_creche e idempotente por origem ==")
antes = db.query(SolicitacaoAssinatura).filter(
    SolicitacaoAssinatura.candidato_id == col1.id,
    SolicitacaoAssinatura.origem == ORIGEM_CRECHE).count()
criar_roteiro_creche(db, ben1, _RH)
db.commit()
depois = db.query(SolicitacaoAssinatura).filter(
    SolicitacaoAssinatura.candidato_id == col1.id,
    SolicitacaoAssinatura.origem == ORIGEM_CRECHE).count()
checar(antes == 1 and depois == 1,
       f"nao cria um SEGUNDO roteiro de creche (antes={antes}, depois={depois})")

print("\n== 3. a ficha do RH ACUSA quem esta pendente ==")
col2, ben2 = _cenario("Joao Sem Requerimento")  # ativo, sem roteiro nenhum
r = cli.get(f"/api/rh/creche/levantamentos/{ben2.id}")
checar(r.status_code == 200, f"detalhe responde 200 (veio {r.status_code})")
req = (r.json() or {}).get("requerimento") or {}
checar(req.get("pendente_disparo") is True,
       "benefício ativo SEM roteiro aparece como pendente_disparo")
r1 = cli.get(f"/api/rh/creche/levantamentos/{ben1.id}").json().get("requerimento") or {}
checar(r1.get("pendente_disparo") is False and r1.get("disparado") is True,
       "quem TEM roteiro nao e acusado (alarme falso ensina a ignorar o alarme)")

print("\n== 4. disparo individual ==")
r = cli.post(f"/api/rh/creche/levantamentos/{ben2.id}/disparar-requerimento")
checar(r.status_code == 200 and r.json().get("disparado") is True,
       f"dispara o pendente (status={r.status_code})")
# ESTADO, nao so o status code: a mutacao que faz a rota nao criar nada
# responderia 200 igual (v2.84).
db.expire_all()
checar(tem_roteiro(db, col2.id, origem=ORIGEM_CRECHE) is not None,
       "o roteiro REALMENTE existe no banco depois do disparo")
r = cli.post(f"/api/rh/creche/levantamentos/{ben2.id}/disparar-requerimento")
# O 2º clique REENVIA o aviso (v3.16.1) em vez de responder "ja_disparado" e
# não fazer nada — mas NÃO cria um segundo roteiro.
checar(r.status_code == 200 and r.json().get("motivo") == "avisado",
       f"segundo clique reenvia o aviso (motivo={r.json().get('motivo')})")
db.expire_all()
_n = db.query(SolicitacaoAssinatura).filter(
    SolicitacaoAssinatura.candidato_id == col2.id,
    SolicitacaoAssinatura.origem == ORIGEM_CRECHE).count()
checar(_n == 1, f"e continua havendo UM unico roteiro (achou {_n})")

print("\n== 5. beneficio NAO ativo recusa, com a saida ==")
col3, ben3 = _cenario("Ana Repactuacao", status=StatusBeneficio.aguardando_repactuacao)
r = cli.post(f"/api/rh/creche/levantamentos/{ben3.id}/disparar-requerimento")
d = r.json().get("detail") if r.status_code == 409 else None
checar(r.status_code == 409, f"recusa quem nao esta ativo (veio {r.status_code})")
# Afirmar sobre o DETAIL, nao so sobre o 409: outro motivo daria 409 igual
# (v2.80).
checar(isinstance(d, dict) and d.get("erro") == "beneficio_nao_ativo",
       "o detail NOMEIA o motivo da recusa")
checar(isinstance(d, dict) and bool(d.get("resolve")),
       "a recusa OFERECE a saida (v2.93), nao so o bloqueio")
db.expire_all()
checar(tem_roteiro(db, col3.id, origem=ORIGEM_CRECHE) is None,
       "e NAO criou roteiro nenhum para ele")

print("\n== 6. lote presta contas ==")
col4, ben4 = _cenario("Pedro Do Lote")
# ⚠️ A rota apenas ENFILEIRA (202): cada aviso custa ~1s de SMTP e o nginx
# corta em 60s, então a varredura roda no worker. A lógica é testada onde ela
# mora — chamar a rota e afirmar sobre o resultado testaria a fila, não a regra.
r = cli.post("/api/rh/creche/requerimentos/disparar-pendentes")
checar(r.status_code in (202, 503),
       f"a rota do lote ENFILEIRA (202) ou recusa honestamente (503): veio {r.status_code}")
if r.status_code == 202:
    prev = r.json()
    checar("a_criar" in prev and "a_avisar" in prev,
           "e devolve a previa do que sera feito (a tela precisa do tamanho)")
corpo = _varrer(ben1, ben2, ben4)
# O resultado separa CRIADOS de AVISADOS — "criei o documento" e "cobrei de
# novo" sao desfechos diferentes e nao podem sair no mesmo numero.
tocados = (corpo.get("criados", []) + corpo.get("avisados", []))
# ⚠️ Casar por ID, nunca por nome: o `_cenario` cria uma pessoa nova a cada
# execucao, entao em banco ja usado ha HOMONIMOS e a asserção por nome fala de
# outro registro (a armadilha do "so passa em banco limpo", v2.14).
ids_lote = {d["id"] for d in tocados}
checar(str(ben4.id) in ids_lote,
       "o lote inclui o beneficio recem-criado (casado por ID)")
checar(any(d["nome"] == "Pedro Do Lote" for d in tocados),
       "o lote NOMEIA quem foi disparado (nao so a contagem)")
checar("falhas" in corpo,
       "o lote sempre reporta o campo de falhas, mesmo vazio")
db.expire_all()
checar(tem_roteiro(db, col4.id, origem=ORIGEM_CRECHE) is not None,
       "e o roteiro do lote REALMENTE existe no banco")
# ⚠️ Esta asserção era o CONTRÁRIO na v3.16 ("quem ja tinha roteiro nao
# aparece") — e era justamente o defeito: quem tem o documento e nunca foi
# avisado PRECISA ser cobrado. O lote agora o inclui, em `avisados`.
checar(str(ben1.id) in {d["id"] for d in corpo.get("avisados", [])},
       "quem ja tinha roteiro mas nao assinou E AVISADO, nao pulado (v3.16.1)")

print("\n== 7. declaracao-modelo tem porta propria ==")
r = cli.post(f"/api/rh/creche/levantamentos/{ben4.id}/enviar-declaracao")
checar(r.status_code == 200 and "enviado_para" in r.json(),
       f"envia a declaracao-modelo (status={r.status_code})")
# Sem e-mail, recusa dizendo o que resolve — nao estoura em 500.
col5, ben5 = _cenario("Sem Email")
col5.email = None
db.commit()
r = cli.post(f"/api/rh/creche/levantamentos/{ben5.id}/enviar-declaracao")
d = r.json().get("detail") if r.status_code == 422 else None
checar(r.status_code == 422 and isinstance(d, dict) and bool(d.get("resolve")),
       "sem e-mail: 422 que diz o que resolve, nunca 500")

print("\n== 9. roteiro criado NAO e pessoa avisada (o caso da Daphne) ==")
# Reproduz o estado real: benefício ativo, roteiro JÁ criado (na ativação, antes
# de existir o e-mail de aviso), colaborador nunca avisado e sem assinar.
col6, ben6 = _cenario("Daphne Do Print")
criar_roteiro_creche(db, ben6, _RH)
db.commit()
est = cli.get(f"/api/rh/creche/levantamentos/{ben6.id}").json().get("requerimento") or {}
checar(est.get("disparado") is True and est.get("pendente_disparo") is False,
       "tem roteiro, entao nao e 'pendente_disparo' (estado correto)")
checar(est.get("nunca_avisado") is True,
       "mas a ficha ACUSA que ele nunca foi avisado")
checar(est.get("pode_avisar") is True,
       "e diz que ainda CABE cobrar (era aqui que o botao sumia)")
checar(est.get("avisado_em") is None, "sem data de aviso, porque nao houve aviso")

r = cli.post(f"/api/rh/creche/levantamentos/{ben6.id}/disparar-requerimento")
corpo = r.json()
checar(r.status_code == 200 and corpo.get("motivo") == "avisado",
       f"reenviar avisa quem JA tem roteiro (motivo={corpo.get('motivo')}, "
       f"status={r.status_code}) — a v3.16 respondia 'ja_disparado' e nao mandava nada")
checar(corpo.get("email_enviado") is True,
       "e o e-mail REALMENTE saiu (a rota reporta o envio, nao so a intencao)")
est2 = corpo.get("requerimento") or {}
checar(est2.get("avisado_em") is not None,
       "depois do envio, a ficha passa a mostrar a data do ultimo aviso")
checar(est2.get("nunca_avisado") is False, "e deixa de acusar 'nunca avisado'")

print("\n== 10. o lote cobre os DOIS casos ==")
col7, ben7 = _cenario("Sem Roteiro Nenhum")            # nao tem roteiro
col8, ben8 = _cenario("Tem Roteiro Sem Aviso")         # tem, nunca avisado
criar_roteiro_creche(db, ben8, _RH)
db.commit()
r = _varrer(ben7, ben8)
criados = {d["id"] for d in r.get("criados", [])}
avisados = {d["id"] for d in r.get("avisados", [])}
checar(str(ben7.id) in criados,
       "quem nao tinha roteiro entra em 'criados'")
checar(str(ben8.id) in avisados,
       "quem TINHA roteiro e nao foi avisado entra em 'avisados' (a correcao)")
# ESTADO, nao so a resposta: prova que o aviso ficou registrado.
db.expire_all()
from app.api.creche import _ultimo_aviso_requerimento  # noqa: E402

checar(_ultimo_aviso_requerimento(db, col8.id) is not None,
       "o aviso do lote foi REGISTRADO na auditoria")
# Quem ja assinou nao e cobrado de novo.
from app.models.solicitacao_assinatura import EtapaAssinatura  # noqa: E402
from datetime import datetime, timezone  # noqa: E402

sol8 = tem_roteiro(db, col8.id, origem=ORIGEM_CRECHE)
et8 = db.scalar(select(EtapaAssinatura).where(
    EtapaAssinatura.solicitacao_id == sol8.id, EtapaAssinatura.ordem == 1))
et8.assinado_em = datetime.now(timezone.utc)
db.commit()
r2 = _varrer(ben8)
checar(str(ben8.id) not in {d["id"] for d in r2.get("avisados", [])},
       "quem JA ASSINOU nao e cobrado de novo")
checar(str(ben8.id) in {d["id"] for d in r2.get("ja_assinados", [])},
       "e aparece na lista de 'ja_assinados' (nao some do relatorio)")
r3 = cli.post(f"/api/rh/creche/levantamentos/{ben8.id}/disparar-requerimento")
d3 = r3.json().get("detail") if r3.status_code == 409 else None
checar(r3.status_code == 409 and isinstance(d3, dict) and d3.get("erro") == "ja_assinado",
       "e o botao individual tambem recusa, dizendo o porque")

print("\n== 11. sem e-mail: NAO conta como avisado ==")
col9, ben9 = _cenario("Sem Email No Lote")
col9.email = None
db.commit()
r = _varrer(ben9)
ids_ok = {d["id"] for d in (r.get("criados", []) + r.get("avisados", []))}
checar(str(ben9.id) not in ids_ok,
       "quem nao tem e-mail NAO entra na conta de avisados")
checar(str(ben9.id) in {d["id"] for d in r.get("sem_email", [])},
       "aparece em 'sem_email', com nome — nao some no total")
db.expire_all()
checar(_ultimo_aviso_requerimento(db, col9.id) is None,
       "e NAO carimba aviso que nao saiu (senao o RH pararia de cobra-lo)")

print("\n== 12. o relatorio da varredura fica GUARDADO ==")
# Sem isso, quem fecha a aba perde a lista de quem foi avisado — e e ela que
# diz para quem NAO cobrar de novo.
#
# ⚠️ Afirmar só `houve is True` NÃO protege: o valor de uma execução ANTERIOR
# fica no banco e a asserção passa mesmo com a gravação removida (foi a mutação
# que escapou da 1ª versão — a v2.67: o estado sobrevive à restauração do
# código). A prova tem de ser que o relatório é DESTE lote.
col10, ben10 = _cenario("Marca Do Relatorio")
_varrer(ben10)
rv = cli.get("/api/rh/creche/requerimentos/varredura")
checar(rv.status_code == 200, f"a rota do relatorio responde 200 (veio {rv.status_code})")
dados_v = rv.json()
checar(dados_v.get("houve") is True, "e diz que houve varredura")
checar("criados" in dados_v and "avisados" in dados_v and "sem_email" in dados_v,
       "com os grupos separados (criado != cobrado de novo)")
checar(dados_v.get("concluido_em") is not None,
       "e a data da conclusao, para o RH saber se o relatorio e recente")
ids_rel = {d["id"] for d in (dados_v.get("criados", []) + dados_v.get("avisados", [])
                             + dados_v.get("sem_email", []) + dados_v.get("ja_assinados", []))}
checar(str(ben10.id) in ids_rel,
       "e o relatorio e o DESTA varredura, nao o de uma execucao anterior")
checar(dados_v.get("total_ativos") == 1,
       f"o recorte chegou ao relatorio (total_ativos={dados_v.get('total_ativos')}, esperado 1)")

print("\n== 8. os templates existem no CATALOGO ==")
from app.services.email_templates import CATALOGO  # noqa: E402

chaves = {m.chave for m in CATALOGO}
for c in ("creche_requerimento_disponivel", "creche_declaracao_modelo"):
    checar(c in chaves, f"template {c} esta no catalogo")

print()
if FALHAS:
    _reportar(f"{len(FALHAS)} FALHA(S):")
    for f in FALHAS:
        _reportar(f"  - {f}")
    sys.exit(1)
_reportar("TODOS OS CENARIOS PASSARAM")
