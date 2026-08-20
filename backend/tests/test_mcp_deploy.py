"""O serviço existe nos TRÊS arquivos, e o nginx não entrega o site no lugar do JSON.

Dois defeitos silenciosos, ambos já pagos por este projeto:

1. **Serviço declarado em só um dos três arquivos não roda em produção** — e
   não gera erro, gera silêncio (v2.66, v2.97). O aviso de certificação vencendo
   nunca saiu por causa disso, e ninguém soube.

2. **`.well-known` sem `location` próprio cai no SPA.** Medido em 20/08/2026 na
   homologação: `GET /.well-known/oauth-protected-resource` devolvia **200 com o
   HTML do site**. O cliente tenta lê-lo como JSON, falha, e reporta "não foi
   possível conectar" — com o serviço no ar e nada no log parecendo errado,
   porque para o nginx foi um 200 bem-sucedido. É o mesmo mecanismo do incidente
   da tela branca (v2.29).

stdlib pura (lê arquivos), roda no CI.
"""

import pathlib
import re
import sys

RAIZ = pathlib.Path(__file__).resolve().parents[2]
BASE = RAIZ / "deploy" / "docker-compose.base.yml"
STACK = RAIZ / "deploy" / "portainer-stack.yml"
CI = RAIZ / ".github" / "workflows" / "ci.yml"
NGINX = RAIZ / "frontend" / "nginx.conf"
DOCKERFILE = RAIZ / "backend" / "Dockerfile.mcp"
EXEMPLO = RAIZ / ".env.example"

falhas = []


def teste_os_tres_arquivos():
    if not re.search(r"^  mcp:$", BASE.read_text(encoding="utf-8"), re.M):
        falhas.append(
            "o serviço `mcp` não está em deploy/docker-compose.base.yml — a "
            "stack local sobe sem o assistente.")

    stack = STACK.read_text(encoding="utf-8")
    if not re.search(r"^  mcp:$", stack, re.M):
        falhas.append(
            "o serviço `mcp` não está em deploy/portainer-stack.yml. ⚠️ É ESTE "
            "que sobe na VPS: sem ele o assistente nunca roda em produção, e "
            "nada avisa (v2.66).")
    if "gestao-rh-mcp" not in stack:
        falhas.append("o stack não aponta para a imagem `gestao-rh-mcp`.")
    # ⚠️ Procura a DECLARAÇÃO, não a string: `MCP_ISSUER` também aparece nos
    # comentários que explicam a variável, e uma busca livre passaria verde com
    # a linha removida — foi o que aconteceu na primeira versão deste teste
    # (a lição da v2.71, agora numa variante YAML).
    if not re.search(r"^\s+MCP_ISSUER:\s*\$\{MCP_ISSUER\}", stack, re.M):
        falhas.append(
            "`MCP_ISSUER: ${MCP_ISSUER}` não está declarada no bloco do serviço "
            "em portainer-stack.yml. O stack não usa `env_file` — variável que "
            "não está listada ali não chega ao container, e o serviço sobe com "
            "o assistente desligado, sem nada avisando.")

    ci = CI.read_text(encoding="utf-8")
    if "servico: mcp" not in ci:
        falhas.append(
            "falta a entrada `servico: mcp` na matriz de imagens do ci.yml. ⚠️ "
            "Sem ela a imagem nunca é publicada, o stack aponta para algo que "
            "não existe, e o container não sobe.")
    if "Dockerfile.mcp" not in ci:
        falhas.append("a matriz do ci.yml não aponta para o Dockerfile.mcp.")


def teste_nginx_roteia_antes_do_spa():
    """O defeito medido: os `.well-known` caindo no SPA."""
    conf = NGINX.read_text(encoding="utf-8")
    posicoes = {}
    for m in re.finditer(r"^\s*location\s+(\S+)\s*(\S*)\s*\{", conf, re.M):
        alvo = m.group(2) if m.group(1) in ("=", "^~", "~") else m.group(1)
        posicoes.setdefault(alvo, m.start())

    spa = posicoes.get("/")
    if spa is None:
        falhas.append("não achei o `location /` do SPA no nginx.conf.")
        return

    obrigatorios = ("/.well-known/oauth-authorization-server",
                    "/.well-known/oauth-protected-resource",
                    "/authorize", "/token", "/register", "/mcp")
    for alvo in obrigatorios:
        onde = posicoes.get(alvo)
        if onde is None:
            falhas.append(
                f"o nginx não tem `location {alvo}`. Sem ele o pedido cai no "
                "SPA e volta HTML com status 200 — o cliente reporta 'não "
                "consegui conectar' e nada no log parece errado.")
        elif onde > spa:
            falhas.append(
                f"`location {alvo}` está DEPOIS do `location /` do SPA. A "
                "ordem decide quem atende; assim o SPA vence.")

    # O transporte é de longa duração: com buffering o nginx segura a resposta e
    # o cliente vê a conexão travada.
    bloco = conf[posicoes.get("/mcp", 0):]
    bloco = bloco[:bloco.find("}")] if "}" in bloco else bloco
    if "proxy_buffering off" not in bloco:
        falhas.append("`location /mcp` sem `proxy_buffering off` — a resposta "
                      "fica presa no nginx e a conexão parece travada.")
    if "proxy_pass http://mcp:" not in bloco:
        falhas.append("`location /mcp` não aponta para o serviço `mcp`.")


def teste_dockerfile_nao_migra():
    """Só a API roda migration — dois processos migrando é corrida em produção.

    ⚠️ Afirma sobre as INSTRUÇÕES, não sobre o texto do arquivo: procurar
    "alembic upgrade" no conteúdo casaria com o comentário que EXPLICA por que
    ele não está aqui, e o teste reprovaria a própria documentação do acerto
    (a lição da v2.71). O reflexo, então, seria apagar o comentário.
    """
    if not DOCKERFILE.exists():
        falhas.append("backend/Dockerfile.mcp não existe.")
        return
    linhas = [l.strip() for l in DOCKERFILE.read_text(encoding="utf-8").splitlines()
              if l.strip() and not l.strip().startswith("#")]
    instrucoes = "\n".join(linhas)

    if re.search(r"^\s*ENTRYPOINT", instrucoes, re.M):
        falhas.append(
            "o Dockerfile.mcp declara ENTRYPOINT. O entrypoint da API roda "
            "`alembic upgrade`, e dois processos migrando o mesmo banco é "
            "corrida de migration em produção (regra do Dockerfile.transcricao).")
    if "alembic upgrade" in instrucoes:
        falhas.append("o Dockerfile.mcp roda migration. Quem migra é a API.")
    if "python -c" not in instrucoes:
        falhas.append(
            "o Dockerfile.mcp não tem guarda-corpo de import. Módulo faltando "
            "deve reprovar no BUILD, não na cara de quem opera (v3.00.5).")
    if not re.search(r"CMD.*mcp_app", instrucoes):
        falhas.append("o Dockerfile.mcp não sobe o `app.mcp_app`.")


def teste_issuer_documentado():
    if "MCP_ISSUER" not in EXEMPLO.read_text(encoding="utf-8"):
        falhas.append(
            "`MCP_ISSUER` não está no .env.example — quem for instalar não "
            "descobre que precisa configurá-la.")


for t in (teste_os_tres_arquivos, teste_nginx_roteia_antes_do_spa,
          teste_dockerfile_nao_migra, teste_issuer_documentado):
    t()

def _reportar(itens: list[str]) -> None:
    """Imprime as falhas em qualquer console.

    ⚠️ O console do Windows (cp1252) NÃO imprime emoji: um `print` com "⚠️"
    levanta `UnicodeEncodeError` e o teste morre ANTES de mostrar a mensagem —
    justamente quando ela importa, porque o teste está reprovando. O defeito
    aparece como traceback de encoding, que não fala nada sobre a causa real.
    """
    print("FALHOU:")
    for item in itens:
        try:
            print(f"  - {item}")
        except UnicodeEncodeError:
            print("  - " + item.encode("ascii", "replace").decode("ascii"))


if falhas:
    _reportar(falhas)
    sys.exit(1)
print("OK - servico nos tres arquivos, nginx roteando antes do SPA, e o "
      "container nao roda migration.")
