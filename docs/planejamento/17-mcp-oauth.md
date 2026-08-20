# MCP remoto com OAuth — desenho ARQUIVADO

> ## ⛔ NÃO IMPLEMENTAR — resolvido de outro jeito (2026-08-20)
>
> Este desenho existiu por algumas horas, entre descobrir que o Claude WEB só
> conecta por OAuth e descobrir que **todos os colaboradores do RH já têm o
> Claude Desktop instalado** (Bruno, 20/08/2026).
>
> Com o Desktop, o token `mcp_…` que já existe (v2.94/v3.01) **funciona sem nada
> disto**: ele roda o servidor por `command` + `args` e passa segredo por
> variável de ambiente. Os dias de trabalho de provedor OAuth — e a superfície
> de segurança nova que vinha junto — deixaram de ser necessários.
>
> **Fica registrado porque o obstáculo é real e volta**: se um dia o uso precisar
> ser pelo NAVEGADOR (alguém sem o Desktop, ou uso pelo celular), o OAuth volta a
> ser o único caminho, e o levantamento abaixo continua valendo.
>
> O que vale hoje: **`18-mcp-servidor.md`**.

---

> Status: **desenhado, não implementado**. Escrito em 2026-08-20, depois que o
> uso mudou e a arquitetura (A) do doc 13 deixou de servir.

## 1. Por que o desenho do doc 13 não serve mais

O doc 13 escolheu **MCP local** (§ 4, opção A): processo no desktop do Bruno,
falando com a API por token. A justificativa continua boa — *"um token vazado
compromete um desktop, não expõe um endpoint público"*.

O que mudou: em 19/08/2026 o Bruno definiu que quem vai usar são **os
colaboradores do RH no Claude Coworking**, pelo navegador. Eles não instalam
processo em máquina nenhuma. A opção (A) deixou de atender o caso de uso — não
por estar errada, mas porque o caso de uso é outro.

## 2. O obstáculo que decidiu o desenho

A ideia natural seria: servidor remoto + cada pessoa cola o token `mcp_…` que a
tela de credenciais já emite (v3.01).

**Isso não funciona no Claude pela web.** O connector remoto na web aceita
apenas **OAuth** (client id/secret); não há campo para `Authorization: Bearer`.
Um pedido exatamente disso — [issue #112 do `anthropics/claude-ai-mcp`] — foi
**fechado como "not planned"** em março/2026.

Consequência: **o token que já existe continua válido**, mas só no Claude
Desktop e no Code, que aceitam headers. Para o Coworking pelo navegador, o
portal precisa falar OAuth.

## 3. O que o portal precisa expor

Pelo [MCP Authorization], o servidor MCP é um **Resource Server** OAuth 2.1. Como
o portal não tem provedor de identidade externo, ele acumula os dois papéis:

| Endpoint | Para quê |
|---|---|
| `/.well-known/oauth-protected-resource` | RFC 9728 — diz ao cliente qual é o authorization server |
| `/.well-known/oauth-authorization-server` | RFC 8414 — anuncia `/authorize`, `/token`, `/register` |
| `POST /register` | RFC 7591 — registro dinâmico: o Claude se cadastra sozinho como cliente |
| `GET /authorize` | a pessoa faz login no portal e autoriza |
| `POST /token` | troca o código por access token (com **PKCE**, obrigatório no 2.1) |

Mais o `WWW-Authenticate` com `resource_metadata` na resposta 401, que é o que
dispara a descoberta automática.

## 4. As decisões que precedem o código

### 4.1 O token OAuth carrega o PAPEL de quem autorizou

A pessoa faz login **no portal** e autoriza. O access token emitido representa
**aquela pessoa**, e a autorização segue pelo `exige(...)` de sempre — a mesma
regra da v2.86 que impede porta paralela.

⚠️ Mas o papel usado **não é o do dia a dia dela**: é o `assistente_rh` (v3.13),
que é mais estreito. Quem no portal pode desligar colaborador continua podendo —
**na tela**, com uma pessoa olhando; pelo assistente, não. A superfície da IA é
deliberadamente menor que a da pessoa, porque a IA executa instrução vinda de
texto e o texto, neste sistema, vem de currículo e campo livre.

### 4.2 O access token é curto e o refresh é revogável

Token de acesso com vida curta (minutos); refresh token guardado só como hash,
revogável na mesma tela das credenciais `mcp_…`. Motivo é o da v2.94: *"se vazar
hoje à noite, como eu corto?"*.

### 4.3 O registro dinâmico não pode virar cadastro aberto

`POST /register` é público por definição do protocolo — qualquer cliente se
registra. Isso é aceitável porque **registrar não dá acesso**: sem uma pessoa
fazer login e autorizar em `/authorize`, o cliente registrado não obtém token
nenhum. Ainda assim: rate limit no `/register`, e o registro **não** é
credencial.

### 4.4 O MCP continua fora da API do humano

O doc 13 § 4 rejeitou "rotas MCP dentro da própria API" para não fundir a
superfície da IA com a do humano. **Isso continua valendo**: as rotas OAuth e o
endpoint `/mcp` vivem em serviço próprio, com container próprio no compose —
mesma regra do `transcricao` (v2.97), e a matriz do `ci.yml` precisa da entrada
(v2.97, o terceiro arquivo).

## 5. Ordem de execução

1. Endpoints de descoberta (`.well-known`) e `/register` — sem eles o Claude nem
   tenta conectar.
2. `/authorize` + `/token` com PKCE, reusando o login do portal.
3. O endpoint `/mcp` (Streamable HTTP) com as ferramentas de LEITURA.
4. As ferramentas de escrita, uma a uma, começando por `cadastrar_talento`.
5. Rate limit por token e por IP; auditoria marcando cada chamada.

## 6. O que este desenho NÃO faz

| Não faz | Por quê |
|---|---|
| Usar o papel do dia a dia da pessoa | A superfície da IA é menor de propósito (§ 4.1) |
| Token longo sem revogação | "Se vazar hoje à noite, como eu corto?" (§ 4.2) |
| Rotas MCP dentro da API do painel | Funde a superfície da IA com a do humano (doc 13 § 4) |
| Ler e-mail | `Mail.Read` alcança a caixa inteira (doc 13 § 2) |

## 7. Alternativa que continua válida

**Claude Desktop com o token `mcp_…`** funciona hoje, sem nada disto. Se o OAuth
se mostrar caro demais, este é o caminho de menor esforço — com o custo de
instalar o app em cada máquina.

[issue #112 do `anthropics/claude-ai-mcp`]: https://github.com/anthropics/claude-ai-mcp/issues/112
[MCP Authorization]: https://modelcontextprotocol.io/docs/tutorials/security/authorization
