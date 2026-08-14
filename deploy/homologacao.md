# Ambiente de homologação na mesma VPS

Uma **segunda stack**, isolada da produção, para validar antes de subir. Nasceu
em 2026-08-13, quando a diarização de entrevistas passou três versões sendo
corrigida às cegas: o único ambiente onde ela rodava era a produção, e testar
significava pedir ao Bruno um deploy e um clique a cada tentativa.

**Decisões tomadas com o Bruno antes de escrever isto:**

- **Dados FICTÍCIOS, criados do zero.** Nenhum CPF, dossiê ou áudio de gente
  real sai da produção. Não é só cuidado com vazamento: é o que permite mexer à
  vontade sem pedir autorização a cada passo — e a única forma de testar
  separação de vozes sem usar a voz de uma candidata real.
- **Subdomínio próprio com HTTPS.** O wizard do candidato pede CÂMERA, e o
  navegador bloqueia `getUserMedia` fora de contexto seguro — sem TLS não dá
  para testar o fluxo que mais importa. Idem a gravação de entrevista.
- **Nginx no HOST** (é como a produção está publicada), **DNS na Cloudflare**.

---

## O que isola uma stack da outra

Vale entender antes de executar, porque é aqui que um erro faz homologação
escrever no banco de produção — e isso não daria erro nenhum, só dado
misturado.

| Recurso | Como se separa |
|---|---|
| **Volumes** (banco, MinIO, logs, modelo) | O Portainer/Compose prefixa os volumes nomeados com o NOME DA STACK. Stack `gestao-rh-homolog` cria `gestao-rh-homolog_postgres-data`, sem tocar em `gestao-rh_postgres-data`. **É por isso que o nome da stack não pode repetir.** |
| **Rede** | A rede `internal` também é prefixada. Os serviços conversam por nome (`db`, `redis`, `minio`) DENTRO da própria stack — o `db` de homologação nunca alcança o de produção. |
| **Porta publicada** | Só o `frontend` publica porta. Produção em `8090`, homologação em `8091`. Duas stacks na mesma porta: a segunda simplesmente não sobe. |
| **`SECRET_KEY`** | **Tem que ser DIFERENTE.** É o que assina token de sessão e link mágico. Iguais, um link emitido em homologação valeria na produção. |
| **Credenciais** | Banco e MinIO com senha própria. Não reaproveite a de produção. |

⚠️ **O que NÃO se separa sozinho:** e-mail. Se você copiar as credenciais SMTP/
M365 da produção, homologação **manda e-mail de verdade** para os endereços que
estiverem no banco — inclusive convite de admissão e código de acesso. Ver a
seção "E-mail" abaixo antes de subir.

---

## Passo 1 — Conferir se a VPS aguenta

```bash
free -h              # RAM livre
df -h /              # disco livre
nproc                # núcleos
```

O que homologação consome, além do que já roda:

- **Disco:** ~4 GB de imagens (a de transcrição sozinha tem 2,17 GB, com o
  modelo `medium` embutido) + o que o banco e o MinIO crescerem.
- **RAM em repouso:** ~1,5 GB (Postgres, Redis, MinIO, API, 4 workers).
- **RAM ao transcrever:** +2 GB enquanto o `medium` está carregado. ⚠️ Se
  produção e homologação transcreverem ao mesmo tempo, são ~4 GB só nisso.

Com folga confortável, siga. Se apertar, a saída é deixar o serviço
`transcricao` de homologação **parado** e ligá-lo só na hora de testar
(`docker start`), ou usar o modelo `small` lá.

---

## Passo 2 — DNS na Cloudflare

Painel da Cloudflare → seu domínio → **DNS** → **Add record**:

- **Type:** `A`
- **Name:** `homolog`
- **IPv4 address:** o IP da VPS (o mesmo da produção)
- **Proxy status:** **DNS only** (nuvem CINZA) — ver o aviso abaixo
- **TTL:** Auto

⚠️ **Deixe a nuvem CINZA, ao menos até o certificado ser emitido.** Com a nuvem
laranja o certbot não consegue validar pelo desafio HTTP (o `.well-known` chega
na Cloudflare, não na sua VPS). E, se você ligar o proxy depois, o modo de SSL
da Cloudflare precisa ser **Full (strict)** — este projeto já pagou por isso: no
modo **Flexible** a Cloudflare fala HTTP com a origem enquanto o app se acha em
HTTPS, e o resultado é **loop de redirecionamento** (registrado no guia do
MinIO/pgAdmin).

Confira a propagação antes de seguir:

```bash
dig +short homolog.SEUDOMINIO      # tem que devolver o IP da VPS
```

---

## Passo 3 — Subir a stack no Portainer

**Stacks → Add stack.**

- **Name:** `gestao-rh-homolog` — ⚠️ diferente do nome da produção; é o que
  separa os volumes.
- **Build method:** *Web editor*
- Cole o conteúdo de **`deploy/portainer-stack.yml`** (o MESMO arquivo da
  produção; nada muda no YAML, tudo muda nas variáveis).

Em **Environment variables → Advanced mode**, cole:

```env
# --- identidade e URL ---------------------------------------------------
ENVIRONMENT=homologacao
BASE_URL=https://homolog.SEUDOMINIO
FRONTEND_PORT=8091

# --- SEGREDO PRÓPRIO (não repita o da produção) -------------------------
# Gere com: openssl rand -hex 32
SECRET_KEY=COLE_AQUI_UM_SEGREDO_NOVO

# --- banco (senha própria) ----------------------------------------------
POSTGRES_USER=admissao
POSTGRES_PASSWORD=COLE_AQUI_OUTRA_SENHA
POSTGRES_DB=admissao

# --- MinIO (senha própria) ----------------------------------------------
MINIO_ROOT_USER=minio
MINIO_ROOT_PASSWORD=COLE_AQUI_OUTRA_SENHA_MINIO
MINIO_BUCKET=admissao

# --- primeiro admin de homologação --------------------------------------
RH_ADMIN_EMAIL=teste@exemplo.com.br
RH_ADMIN_PASSWORD=COLE_AQUI_UMA_SENHA_DE_TESTE

# --- e-mail: DESLIGADO de propósito (ver a seção "E-mail") --------------
SMTP_HOST=
SMTP_PORT=587
SMTP_USER=
SMTP_PASSWORD=
SMTP_FROM=

# --- prazos (iguais aos da produção; ajuste se quiser testar expiração) --
RH_SESSION_TTL_HOURS=12
MAGIC_LINK_TTL_HOURS=72
OTP_TTL_MINUTES=10
RETENTION_DAYS=90
```

Clique em **Deploy the stack** e aguarde. A primeira subida baixa ~4 GB de
imagem; a API só responde depois de aplicar as migrations (é o `entrypoint` que
as roda).

Confira antes de mexer no nginx — ainda pelo IP, sem passar pelo proxy:

```bash
curl -s http://127.0.0.1:8091/api/health
```

Tem que devolver `"status":"ok"` e a versão esperada. Se `migracoes.em_dia` vier
`false`, o schema ficou atrás do código: veja o log da API antes de seguir.

---

## Passo 4 — Nginx no host

Crie `/etc/nginx/sites-available/homolog`:

```nginx
server {
    listen 80;
    server_name homolog.SEUDOMINIO;

    # O certbot acrescenta o bloco de TLS e o redirecionamento sozinho.

    # ⚠️ Áudio de entrevista sobe em blocos de ~10 min; o padrão do nginx é
    # 1 MB e cortaria o envio com um 413 que, na tela, parece internet ruim.
    # 50m para casar com o `client_max_body_size` do nginx DENTRO do container
    # (frontend/nginx.conf): pôr mais aqui não adianta — o corte passaria a
    # acontecer no de dentro, com a mesma cara e um salto a mais para achar.
    client_max_body_size 50m;

    location / {
        proxy_pass http://127.0.0.1:8091;
        proxy_set_header Host              $host;
        proxy_set_header X-Real-IP         $remote_addr;
        proxy_set_header X-Forwarded-For   $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # ⚠️ OCR de comprovante pode levar minutos, e transcrever é assíncrono
        # mas a rota que ENFILEIRA responde na hora. O padrão de 60s cortava o
        # envio de documento e a tela dizia "você está sem internet" para quem
        # estava com a internet boa (v2.31).
        proxy_read_timeout    300s;
        proxy_send_timeout    300s;
        proxy_connect_timeout 60s;
    }
}
```

Ative, teste a sintaxe e recarregue:

```bash
sudo ln -s /etc/nginx/sites-available/homolog /etc/nginx/sites-enabled/
sudo nginx -t          # NÃO recarregue sem isto passar
sudo systemctl reload nginx
```

⚠️ **Não mexa no arquivo da produção.** Se o `nginx -t` acusar erro, é no
arquivo novo — corrija-o em vez de mexer no que está funcionando.

---

## Passo 5 — Certificado HTTPS

```bash
sudo certbot --nginx -d homolog.SEUDOMINIO
```

Escolha redirecionar HTTP → HTTPS quando ele perguntar. O certbot reescreve o
`server` block sozinho, acrescentando o `listen 443 ssl` e o certificado.

Confira que a renovação automática funciona:

```bash
sudo certbot renew --dry-run
```

Agora `https://homolog.SEUDOMINIO` deve abrir a tela de login.

---

## Passo 6 — Dados fictícios

O primeiro admin nasce do `RH_ADMIN_EMAIL`/`RH_ADMIN_PASSWORD` **só com a tabela
vazia** — que é o caso aqui. Entre com ele.

Para popular com dado de teste, o projeto já tem o preparador:

```bash
# <api> = nome do container da API da stack de HOMOLOGAÇÃO
docker cp backend/tests/. <api>:/app/tests
docker exec -e PYTHONPATH=. <api> python tests/preparar_ambiente_local.py
```

⚠️ **Confira o nome do container antes de rodar** (`docker ps | grep homolog`).
Rodar isso contra a API de PRODUÇÃO mexeria em usuário real. O script se
protege — recusa rodar com `ENVIRONMENT=production` —, mas homologação usa
`ENVIRONMENT=homologacao`, então a trava não vale aqui: quem confere o
destino é você.

⚠️ **Ele cria um usuário de senha CONHECIDA** (`teste@exemplo.com.br` /
`senha-teste-123`), escrita num repositório público. Isso é aceitável num
ambiente com dados fictícios e é justamente por isso que o guia insiste em não
restaurar dump da produção: com dado real, esse usuário seria uma porta aberta
documentada na internet.

**Nunca restaure um dump da produção aqui.** Foi decisão explícita: homologação
existe para poder ser destruída e recriada sem consequência, e um banco com
1.171 CPFs reais deixa de ter essa propriedade.

---

## E-mail: por que fica DESLIGADO

O `.env` acima deixa o SMTP vazio de propósito. Com as credenciais da produção,
homologação passaria a **mandar e-mail de verdade**: convite de admissão, código
de acesso, aviso de documento rejeitado. Como os dados são fictícios, os
endereços também são — mas basta um endereço real digitado num teste para uma
pessoa receber um convite que não existe.

O sistema **não quebra sem e-mail**: `enviar_email` devolve `False` e a ação
segue. Para ler o código de acesso ou o link mágico em homologação, use o log:

Configurações → **Logs** → serviço `api` — ou, no terminal:

```bash
docker logs <api-homolog> | grep -i "codigo\|link"
```

Se algum dia precisar testar o envio de verdade, use uma caixa de captura
(Mailtrap, ou uma conta descartável) — **nunca** o M365 da empresa.

---

## Rotina de uso

**Atualizar homologação com o que acabou de ser commitado:**

Portainer → Stacks → `gestao-rh-homolog` → **Update the stack** → marque
**Re-pull image** → *Update*.

O CI publica `:latest` a cada push no `main`, então o re-pull traz a versão mais
recente. Confira depois:

```bash
curl -s https://homolog.SEUDOMINIO/api/health
```

**Recomeçar do zero** (quando o banco de teste ficar bagunçado):

Portainer → Stacks → `gestao-rh-homolog` → **Delete this stack** → marque para
**remover os volumes** → suba de novo pelo Passo 3.

⚠️ Confira DUAS VEZES o nome da stack nessa tela. É a única operação deste guia
que destrói dado, e as duas stacks aparecem lado a lado na mesma lista.

---

## Verificação final

- [ ] `https://homolog.SEUDOMINIO/api/health` responde `ok` e a versão certa
- [ ] `https://SEUDOMINIO/api/health` (produção) **continua** respondendo
- [ ] `docker volume ls | grep homolog` mostra volumes com o prefixo da stack
      nova — e os da produção seguem intactos
- [ ] O login de homologação **não** funciona com a senha da produção
      (`SECRET_KEY` e banco diferentes)
- [ ] O cadeado do navegador aparece (TLS válido)
- [ ] `sudo certbot renew --dry-run` passa
- [ ] Um upload de documento grande passa (valida o `client_max_body_size`)
