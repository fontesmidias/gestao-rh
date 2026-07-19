# Migração de domínio (com redirect do domínio antigo)

Guia para trocar o domínio público do sistema **sem quebrar links antigos** que
ainda circulam por e-mail/WhatsApp (convites de candidatos, links de documentos).

> Por segurança, este guia usa placeholders — substitua pelos valores reais,
> que ficam apenas na VPS/Cloudflare (nunca commitados aqui):
>
> - `ANTIGO.exemplo.com` — domínio atual em uso
> - `NOVO.exemplo.com` — domínio de destino

Cenário coberto: variante **certbot** do deploy (`deploy/docker-compose.certbot.yml`) —
o nginx **do host** faz o TLS com certificados do Certbot e repassa para o
container do frontend em `127.0.0.1:${FRONTEND_PORT}`.

## Por que a migração é segura para links antigos

- O backend gera todos os links públicos (link mágico do candidato, reset de
  senha, callbacks) a partir do **Host da requisição**
  (`base_url_publica()` em `backend/app/core/config.py`), não de valor fixo.
  Ou seja: assim que o domínio novo estiver servindo, os **novos convites já
  saem no domínio novo** sem mudar nada no código.
- Quem abrir um link antigo cai no redirect 301 do nginx, que **preserva o
  caminho e a query string** (`$request_uri`) — o token do link mágico continua
  funcionando no domínio novo de forma transparente.

## Passo a passo

### 1. DNS na Cloudflare

Criar (ou conferir) o registro do domínio novo apontando para o mesmo IP da VPS
— igual ao do domínio antigo. **Não remova o registro antigo**: ele precisa
continuar resolvendo enquanto houver links antigos circulando.

Se os registros estiverem com proxy da Cloudflare ativo (nuvem laranja),
confira em *SSL/TLS* que o modo é **Full (strict)** — o certificado na VPS
continua sendo o do Certbot.

### 2. Server block do domínio novo no nginx do host

Copiar o server block do domínio antigo trocando apenas o `server_name`
(o `proxy_pass` continua o mesmo `127.0.0.1:${FRONTEND_PORT}`):

```nginx
server {
    server_name NOVO.exemplo.com;
    listen 80;
    client_max_body_size 50m;
    location / {
        proxy_pass http://127.0.0.1:8090;   # = FRONTEND_PORT
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-Proto https;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

```bash
sudo nginx -t && sudo systemctl reload nginx
```

### 3. Certificado SSL do domínio novo (Certbot)

```bash
sudo certbot --nginx -d NOVO.exemplo.com
```

O Certbot valida o domínio, emite o certificado e reescreve o server block
acima para `listen 443 ssl` com os caminhos em
`/etc/letsencrypt/live/NOVO.exemplo.com/`. A renovação automática já cobre o
certificado novo (conferir com `sudo certbot renew --dry-run`).

Neste ponto o sistema responde **nos dois domínios**. Teste o novo antes de
seguir: login do RH, abertura de um convite, upload de documento.

### 4. Redirect 301 no domínio antigo

Trocar o conteúdo do server block **antigo** (o de `listen 443 ssl`) para
redirecionar tudo, preservando caminho e query:

```nginx
server {
    server_name ANTIGO.exemplo.com;
    listen 443 ssl;
    ssl_certificate     /etc/letsencrypt/live/ANTIGO.exemplo.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/ANTIGO.exemplo.com/privkey.pem;
    return 301 https://NOVO.exemplo.com$request_uri;
}

server {
    server_name ANTIGO.exemplo.com;
    listen 80;
    return 301 https://NOVO.exemplo.com$request_uri;
}
```

```bash
sudo nginx -t && sudo systemctl reload nginx
```

> **Importante: não apagar o certificado do domínio antigo** (`certbot delete`)
> nem o registro DNS dele. O redirect em HTTPS só funciona com o certificado
> antigo válido — sem ele, quem clicar num link antigo vê erro de certificado
> antes mesmo do redirect. Deixe os dois certificados renovando normalmente.

### 5. Ajustes no `.env` da stack

`BASE_URL` é apenas *fallback* (a URL real vem do Host da requisição), mas deve
refletir o domínio novo para os casos sem contexto de requisição:

```
BASE_URL=https://NOVO.exemplo.com
```

Recriar os containers para aplicar (`docker compose ... up -d` ou re-deploy da
stack no Portainer).

## Checklist de validação

- [ ] `https://NOVO.exemplo.com` abre o sistema com cadeado válido.
- [ ] `https://ANTIGO.exemplo.com/qualquer/caminho?x=1` redireciona (301) para
      o mesmo caminho e query no domínio novo, sem aviso de certificado.
- [ ] Um link mágico **antigo** (enviado antes da migração) abre normalmente
      após o redirect e o candidato consegue enviar documento.
- [ ] Um convite **novo** chega por e-mail já com o domínio novo no link.
- [ ] Upload de arquivo grande funciona no domínio novo (`client_max_body_size`).
- [ ] `sudo certbot renew --dry-run` passa para os dois certificados.

## Descontinuação do domínio antigo (futuro)

Manter o redirect **por tempo indeterminado** enquanto houver documentos,
e-mails ou planilhas com o link antigo. Quando decidir desligar de vez:
remover os server blocks antigos, depois `sudo certbot delete --cert-name
ANTIGO.exemplo.com` e por fim o registro DNS na Cloudflare — nessa ordem.

## Alternativa: redirect na Cloudflare

Se preferir tirar o redirect do nginx, dá para fazer o mesmo com uma
*Redirect Rule* na Cloudflare (301, preservando path e query) no domínio
antigo com proxy ativo. A abordagem via nginx foi a escolhida por manter toda
a configuração num lugar só (a VPS) e não depender do proxy da Cloudflare.
