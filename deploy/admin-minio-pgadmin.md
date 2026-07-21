# Administração: MinIO e pgAdmin 4 atrás do Nginx da VPS

Guia para expor, com segurança, **dois painéis de administração** do Portal de RH:

- **MinIO** (arquivos): API S3 em `s3.SEUDOMINIO` + console em `minio.SEUDOMINIO`.
- **pgAdmin 4** (banco): administração do Postgres em `pgadmin.SEUDOMINIO`.

Ambos sobem como **stacks independentes** (não tocam o stack do app), publicam
apenas no **loopback** (`127.0.0.1`) e são expostos pela internet **só pelo Nginx
da VPS**, com **TLS**. Assim as portas de admin nunca ficam abertas direto.

> Arquivos deste guia:
> - `deploy/pgadmin/docker-compose.pgadmin.yml` + `deploy/pgadmin/.env.example` + `deploy/pgadmin/nginx-pgadmin.conf`
> - `deploy/minio/docker-compose.minio-exposto.yml` + `deploy/minio/.env.example` + `deploy/minio/nginx-minio.conf`

---

## 0. Pré-requisitos

1. O **stack do app já está de pé** (ele cria a rede Docker `deploy_internal`,
   o Postgres `db` e o MinIO `minio`). Confirme o nome da rede:
   ```bash
   docker network ls | grep internal      # normalmente: deploy_internal
   ```
   Se o seu diretório de deploy não for `deploy/`, o prefixo muda (ex.:
   `admissao_internal`) — ajuste `STACK_NETWORK` no `.env` do pgAdmin e `name:`
   no compose.

2. **DNS**: crie os registros A apontando para o IP da VPS:
   ```
   s3.SEUDOMINIO       A   <IP-da-VPS>
   minio.SEUDOMINIO    A   <IP-da-VPS>
   pgadmin.SEUDOMINIO  A   <IP-da-VPS>
   ```

3. **Nginx + Certbot** instalados na VPS (`sudo apt install nginx certbot python3-certbot-nginx`).

---

## 1. pgAdmin 4

### 1.1. Configurar e subir
```bash
cd /caminho/do/repo
cp deploy/pgadmin/.env.example deploy/pgadmin/.env
nano deploy/pgadmin/.env      # defina PGADMIN_DEFAULT_EMAIL e uma senha FORTE

docker compose --env-file deploy/pgadmin/.env \
  -f deploy/pgadmin/docker-compose.pgadmin.yml up -d
```
Sobe em `127.0.0.1:5050` (só loopback). Teste local: `curl -I http://127.0.0.1:5050`.

### 1.2. Nginx + TLS
```bash
sudo cp deploy/pgadmin/nginx-pgadmin.conf /etc/nginx/sites-available/pgadmin
sudo nano /etc/nginx/sites-available/pgadmin      # troque SEUDOMINIO
sudo ln -s /etc/nginx/sites-available/pgadmin /etc/nginx/sites-enabled/
sudo certbot --nginx -d pgadmin.SEUDOMINIO         # emite o certificado
sudo nginx -t && sudo systemctl reload nginx
```

### 1.3. Registrar o servidor Postgres (1ª vez, dentro do pgAdmin)
Acesse `https://pgadmin.SEUDOMINIO`, faça login e **Add New Server**:
| Campo | Valor |
|---|---|
| Name (General) | Portal RH |
| Host (Connection) | `db` |
| Port | `5432` |
| Maintenance database | `admissao` (= `POSTGRES_DB`) |
| Username | `admissao` (= `POSTGRES_USER`) |
| Password | *(o `POSTGRES_PASSWORD` do `.env` do app)* |

> O host é `db` porque o pgAdmin está na MESMA rede Docker do banco. Não use
> `localhost` — dentro do container isso apontaria para o próprio pgAdmin.

---

## 2. MinIO (console + API S3)

Este add-on **expõe o MinIO que já roda** (mesmo volume, mesmos arquivos) — não
cria um segundo. Ele habilita o console (`:9001`) e publica `:9000`/`:9001` no
loopback.

### 2.1. Subir (junto com o base — mesma ordem do deploy do app)
As credenciais do MinIO já estão no `.env` do **app** (raiz):
`MINIO_ROOT_USER` / `MINIO_ROOT_PASSWORD`. Suba combinando os composes:
```bash
docker compose --env-file .env \
  -f deploy/docker-compose.base.yml \
  -f deploy/docker-compose.ip.yml \
  -f deploy/minio/docker-compose.minio-exposto.yml up -d
```
> Se o app usa **traefik** ou **certbot** em vez de `ip.yml`, troque o `-f` do
> meio pela variante que você já usa. O add-on só acrescenta portas+console ao
> serviço `minio` existente.

Teste local: `curl -I http://127.0.0.1:9001` (console) e `http://127.0.0.1:9000/minio/health/live` (API).

### 2.2. Nginx + TLS (dois subdomínios)
```bash
sudo cp deploy/minio/nginx-minio.conf /etc/nginx/sites-available/minio
sudo nano /etc/nginx/sites-available/minio        # troque SEUDOMINIO
sudo ln -s /etc/nginx/sites-available/minio /etc/nginx/sites-enabled/
sudo certbot --nginx -d s3.SEUDOMINIO -d minio.SEUDOMINIO
sudo nginx -t && sudo systemctl reload nginx
```
O bloco do console já inclui os headers de **WebSocket** (o painel do MinIO não
funciona sem eles) e a API S3 já vem com `client_max_body_size 0` e
`proxy_request_buffering off` para uploads grandes.

### 2.3. Acessar
- **Console (admin)**: `https://minio.SEUDOMINIO` — login com `MINIO_ROOT_USER`/`MINIO_ROOT_PASSWORD`.
- **API S3** (para `mc`, SDKs, integrações): endpoint `https://s3.SEUDOMINIO`, `secure=true`.

> O app continua falando com o MinIO **internamente** por `minio:9000` (http na
> rede docker) — nada muda para ele. O `s3.SEUDOMINIO` é só para acesso externo.

---

## 3. Segurança (checklist)

- [ ] As portas de admin (`5050`, `9000`, `9001`) estão publicadas **só em
      `127.0.0.1`** — confirme com `sudo ss -tlnp | grep -E '5050|9001|9000'`
      (devem aparecer como `127.0.0.1:`, nunca `0.0.0.0:`).
- [ ] **Firewall** (ufw) libera só 80/443 (e 22): `sudo ufw allow 'Nginx Full'`.
- [ ] Senhas **fortes e distintas** para pgAdmin e MinIO; nunca reaproveitar a do banco.
- [ ] Os `.env` (`deploy/pgadmin/.env` e o `.env` raiz) **não** vão ao git
      (o `.gitignore` já bloqueia — só os `.env.example` são versionados).
- [ ] Certificados renovam sozinhos (`sudo certbot renew --dry-run` para testar).
- [ ] (Opcional) Restringir por IP no Nginx (`allow <seu-ip>; deny all;`) ou
      colocar Basic Auth extra nos subdomínios de admin.

---

## 4. Operação

**Parar/atualizar o pgAdmin** (não afeta o app):
```bash
docker compose --env-file deploy/pgadmin/.env \
  -f deploy/pgadmin/docker-compose.pgadmin.yml down     # ou pull + up -d p/ atualizar
```
O volume `pgadmin-data` preserva servidores cadastrados e preferências.

**Backup rápido do banco pelo pgAdmin**: botão direito no database → *Backup…*
(formato *Custom*), ou via CLI: `docker exec deploy-db-1 pg_dump -U admissao admissao > backup.sql`.

**Logs**:
```bash
docker logs -f pgadmin-pgadmin-1        # nome pode variar; veja docker ps
docker logs -f deploy-minio-1
```
