# Voltar a uma versão anterior (rollback)

Guia para quando a versão nova quebrou alguma coisa e é preciso voltar. Escrito
em 19/08/2026, a pedido do Bruno.

> **Antes de tudo:** o rollback devolve o CÓDIGO, **não o banco**. Leia a seção
> "O banco não volta junto" no fim — é onde mora o risco.

---

## 1. Descobrir para qual versão voltar

Cada versão fechada vira uma **tag git** (`v3.09.0`), criada pelo CI **só quando
o pipeline inteiro passa** — testes, smoke e Playwright. Isso importa: uma tag
existir significa que aquele código foi aprovado, não apenas que ele compilou.

**Na tela do GitHub:** Code → Tags, ou a lista de Releases.

> A imagem com o número (`:3.09.0`) é publicada **no mesmo build do `main`**, lendo o `versao.py` — não depende da tag. Isso é deliberado: o push da tag é feito pelo próprio CI, e o GitHub não dispara workflow a partir dele (proteção contra loop). Se dependesse da tag, ela existiria e a imagem não — e este guia mandaria escolher um número que o registro não tem.

**No terminal:**

```bash
git fetch --tags
git tag -l "v3*" --sort=-version:refname | head -10
```

Para ver o que cada uma entregou, o `CHANGELOG.md` tem uma seção por versão,
com o PORQUÊ de cada mudança — é ele que responde *"qual versão ainda não tinha
este problema?"*.

### Se a versão que você quer não tem tag

Aconteceu com as versões intermediárias de 19/08/2026: elas existem no
CHANGELOG mas **não viraram tag**, porque o CI reprovou nelas (um teste E2E
quebrado). Nesse caso use o **SHA do commit**, que sempre existe como tag de
imagem:

```bash
gh run list --limit 20 --json headSha,conclusion,displayTitle \
  --jq '.[] | select(.conclusion=="success") | "\(.headSha[:7])  \(.displayTitle)"'
```

O filtro `conclusion=="success"` é o que importa — commit reprovado publica
imagem do mesmo jeito (o job de imagens roda em paralelo aos testes), e voltar
para ele traria o defeito de volta.

---

## 2. Trocar a imagem no Portainer

Stacks → a stack → **Editor**. Troque `:latest` pela versão:

| Linha | De | Para |
|---|---|---|
| `api`, `worker`, `expurgo`, `alertas` | `gestao-rh-api:latest` | `gestao-rh-api:3.09.0` |
| `frontend` | `gestao-rh-frontend:latest` | `gestao-rh-frontend:3.09.0` |
| `transcricao` | `gestao-rh-transcricao:latest` | `gestao-rh-transcricao:3.09.0` |

⚠️ **São SEIS linhas, não uma.** A imagem da API aparece **quatro vezes** — a
API, o worker da fila, o expurgo e os alertas usam a mesma. Trocar só a primeira
deixa metade da stack numa versão e metade em outra, **sem nada avisando**: o
sintoma seria comportamento inconsistente entre a tela e o que os workers fazem.

Use `:3.09.0` (sem o `v`) — a tag git é `v3.09.0`, mas a tag da imagem sai sem
o prefixo. Com o SHA, é `:1b56ed0`.

Depois: **Update the stack**, sem marcar "Re-pull image" — o pull acontece
sozinho porque a tag mudou, e re-pull em máquina apertada derruba o daemon.

---

## 3. Conferir que voltou

```bash
docker ps --filter name=<sua-stack> --format '{{.Names}}\t{{.Status}}'
curl -s localhost:8090/api/health
```

O `/api/health` responde a versão que está no ar **e** se o banco acompanhou:

```json
{ "status": "ok", "versao": "v3.09.0 — …", "versao_numero": "3.09.0",
  "migracoes": { "em_dia": true, "no_codigo": "b5d9e2a7c134", "no_banco": "b5d9e2a7c134" } }
```

---

## 4. O banco NÃO volta junto

Esta é a parte que exige atenção.

**Trocar a imagem não desfaz migrations.** Se a versão nova criou tabela ou
coluna, o banco continua com elas depois do rollback — e isso **normalmente não
é problema**: a versão antiga simplesmente ignora o que não conhece.

O caso que dá trabalho é o inverso: se o banco estiver numa revisão **mais
nova** que a esperada pelo código antigo, o `alembic upgrade head` do entrypoint
não tem o que fazer e a API sobe assim mesmo (defesa da v2.70 — schema velho no
ar é melhor que tela morta). O `/api/health` vai acusar:

```json
"migracoes": { "em_dia": false, "no_codigo": "<antiga>", "no_banco": "<nova>" }
```

Se a versão nova **destruiu** algo (coluna removida, tipo alterado) e você
precisa reverter o schema:

```bash
# 1. BACKUP PRIMEIRO — sempre, sem exceção
docker exec <container-db> pg_dump -U admissao admissao > backup-$(date +%F).sql

# 2. uma revisão por vez, conferindo entre elas
docker exec -e PYTHONPATH=. <container-api> python -m alembic downgrade -1
```

⚠️ **Migration já aplicada não roda de novo** (lição da v2.70): corrigir o
arquivo de uma migration conserta bancos NOVOS, não o que já a executou. Para
completar algo que ficou faltando, é preciso uma revisão nova e idempotente.

---

## 5. Voltar para o `latest`

Terminado o incidente, devolva as seis linhas para `:latest` e dê Update. Deixar
a versão fixada faz a stack **parar de receber correções** — e ninguém percebe,
porque tudo continua funcionando.
