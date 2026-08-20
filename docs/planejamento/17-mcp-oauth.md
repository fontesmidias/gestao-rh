# MCP remoto com OAuth — o caminho escolhido

> ## ✅ DESARQUIVADO — é o caminho escolhido (2026-08-20, à tarde)
>
> Este desenho foi arquivado de manhã e **reaberto no mesmo dia**, e o porquê
> vale mais que o desenho: o arquivamento respondeu à pergunta errada.
>
> **O que arquivou:** todos os colaboradores têm o Claude Desktop, que aceita o
> token `mcp_…` — então o OAuth "não era necessário".
>
> **O que reabriu** (Bruno, olhando o guia de instalação): *"geralmente quando
> vou consumir o mcp de alguma plataforma, só clico dentro da plataforma, ele
> pede para autenticar com o Claude e já funciona. Por que isso não vai no
> nosso?"*
>
> A pergunta de manhã foi *"dá para funcionar?"* — e a resposta era sim. A
> pergunta certa era *"por que a nossa dá trabalho quando nenhuma outra dá?"*.
> O Desktop torna o token VIÁVEL; não torna a instalação BOA. Entre as duas
> perguntas houve um instalador `.mcpb` começado e descartado — ele resolvia o
> terminal e o JSON, e **continuava pedindo que cada pessoa criasse e colasse
> uma credencial**, que é justamente o passo que o padrão de mercado não tem.
>
> ⚠️ **A lição é de escopo, não de OAuth**: "existe uma saída que funciona" não
> é o mesmo que "a saída está boa para quem vai usar". Quando o caminho tem um
> padrão que todo mundo conhece, sair dele precisa de justificativa — e
> "conseguimos contornar" não é uma.
>
> **O que o OAuth entrega e as outras duas não:** ninguém cria nem cola token
> (a pessoa faz login com a conta que já tem); revogar acesso vira desligar o
> usuário; e funciona **pelo navegador e no celular**, sem exigir o Desktop.
>
> O `18-mcp-servidor.md` continua descrevendo o servidor stdio e as ferramentas
> — que são REAPROVEITADAS aqui. O OAuth troca a porta de entrada, não o
> conteúdo.

---

> Status: **IMPLEMENTADO** na v3.15 (20/08/2026). Falta só configurar a
> `MCP_ISSUER` por ambiente e testar na homologação — ver `mcp/CONECTAR.md`.

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
| `POST /register` | RFC 7591 — registro dinâmico. ⚠️ **DEPRECADO na spec atual** (ver § 3.1); continua necessário por compatibilidade |
| `GET /authorize` | a pessoa faz login no portal e autoriza |
| `POST /token` | troca o código por access token (com **PKCE**, obrigatório no 2.1) |

Mais o `WWW-Authenticate` com `resource_metadata` na resposta 401, que é o que
dispara a descoberta automática.

### 3.1 O que mudou na spec desde a 1ª escrita deste doc

Conferido em 20/08/2026 contra a spec de autorização do MCP:

- **Registro dinâmico (RFC 7591) está DEPRECADO**, mantido só para
  compatibilidade. O mecanismo preferido passou a ser **Client ID Metadata
  Documents** (o `client_id` é uma URL https de onde o servidor busca os
  metadados do cliente). Implementar os dois: o `/register` porque clientes
  existentes ainda o usam, e o novo porque é para onde a spec aponta.
- **`resource` (RFC 8707) é obrigatório** no `/authorize` E no `/token`, e o
  servidor **precisa validar que o token foi emitido para ELE** como audiência.
  Sem isso, um token emitido para outro serviço seria aceito aqui — é a mesma
  família do "porta paralela que não passa pela checagem" (v2.86).
- **`iss` na resposta de autorização** (RFC 9207) é SHOULD hoje e a spec avisa
  que vira MUST; quem emitir `iss` deve anunciar
  `authorization_response_iss_parameter_supported: true`. Emitir agora sai mais
  barato que migrar depois.
- **PKCE continua obrigatório** (OAuth 2.1).
- **`offline_access` NÃO entra** no `scopes_supported` nem no
  `WWW-Authenticate` do resource server — refresh token não é exigência do
  recurso.

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
