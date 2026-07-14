# Portal de Admissão — Green House

Sistema de admissão digital: formulário admissional, geração e assinatura eletrônica das
fichas (Cadastro, Emergência, Termo de VT), envio de documentação por checklist com
"continue de onde parou", revisão pelo RH e geração do dossiê único em PDF.

**Status:** fase de planejamento.

- 📋 [Visão e decisões de arquitetura](docs/planejamento/01-visao-e-decisoes.md)

## Stack

Python/FastAPI · React/Vite · PostgreSQL · MinIO · Redis · SMTP · Docker Compose
(stacks: IP direto, Traefik, Certbot). Configuração via `.env`.

## Como rodar

### Portainer (recomendado na VPS) — arquivo único, sem build
1. Na VPS: `docker login ghcr.io -u SEU_USUARIO -p SEU_TOKEN` (PAT com `read:packages`).
2. Portainer → Stacks → Add stack → cole [deploy/portainer-stack.yml](deploy/portainer-stack.yml).
3. Defina as variáveis de ambiente na tela do Portainer (modo avançado aceita colar o `.env`).
As imagens (`ghcr.io/fontesmidias/admissao-api|frontend`) são publicadas automaticamente
pelo CI a cada push na `main` e a cada tag `v*`.

### Docker Compose (a partir do código-fonte)

```bash
cp .env.example .env   # edite: senhas, SMTP, RH_ADMIN_*, FRONTEND_PORT
# Local / VPS sem domínio (sem HTTPS — apenas validação):
docker compose --env-file .env -f deploy/docker-compose.base.yml -f deploy/docker-compose.ip.yml up -d --build
# VPS com domínio (Traefik, TLS automático):
docker compose --env-file .env -f deploy/docker-compose.base.yml -f deploy/docker-compose.traefik.yml up -d --build
# VPS com certbot/nginx existentes no host:
docker compose --env-file .env -f deploy/docker-compose.base.yml -f deploy/docker-compose.certbot.yml up -d --build
```

Importante: use sempre `--env-file .env` (o compose não procura o `.env` da raiz
porque os arquivos ficam em `deploy/`). Acesse `http://IP:FRONTEND_PORT` — painel
do RH em `/rh` (admin inicial criado a partir de `RH_ADMIN_EMAIL`/`RH_ADMIN_PASSWORD`).
Atualizações: `git pull` + o mesmo comando `up -d --build` — as migrations rodam
sozinhas no start e **preservam os dados** (volumes `postgres-data` e `minio-data`).
